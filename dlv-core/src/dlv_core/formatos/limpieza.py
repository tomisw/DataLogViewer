"""Reglas de limpieza sobre el cuerpo ya parseado (tarea F1-03).

Se aplican después de `dlv_core.formatos.cuerpo.parsear_cuerpo` (F1-02) y antes
de la consolidación (F1-05, ADR-003): dos puntos de la lista de verificación de
`docs/01-formato-log.md` §1.13 que el `pl.read_csv` de F1-02 no puede resolver
por sí solo, porque necesitan datos externos (el registro de centinelas) o
inspeccionar las líneas crudas en vez del `DataFrame` ya tipado.

    1. **Centinelas de desbordamiento.** El AutoLog real repite
       `2147483647`, `-2147483645`, `-2147483628`... como marca de «sin
       dato»/saturación, no como medida (docs/01 §1.13). Confundirlos con
       datos reales contamina cualquier media o percentil. La lista vive en
       `data/units.toml [centinelas]` (F0-08) y ya la carga
       `dlv_core.unidades.Catalogo.centinelas_i32`; aquí solo se aplica,
       vectorizado sobre todas las columnas de canal a la vez.
    2. **Filas con número de campos distinto del esperado.**
       `parsear_cuerpo` ya las tolera (`truncate_ragged_lines=True`, F1-02:
       rellena las cortas con nulos, trunca las largas) sin abortar la carga,
       pero sin dejar constancia de cuáles fueron -- docs/01 §1.13 pide "se
       registra y se salta", no solo "se salta". Esta es esa constancia.

       Se cuenta por línea con `pl.Expr.str.count_matches` (Polars/Rust), no
       con un bucle de Python fila a fila: se lee el cuerpo una segunda vez
       con un separador de un solo carácter que no aparece en los datos
       (`\\x01`), así que cada línea completa cae en una única celda de
       texto, y contar comas dentro de esa celda es una operación vectorizada
       de cadena, no una iteración por muestra.
"""

from __future__ import annotations

import polars as pl

from dlv_core.formatos.cuerpo import COLUMNA_MARCA
from dlv_core.formatos.haltech import Cabecera
from dlv_core.informes import Aviso
from dlv_core.unidades import Catalogo

__all__ = ["detectar_filas_malformadas", "nulificar_centinelas"]

_SEPARADOR_LINEA_COMPLETA = "\x01"
"""Carácter que no aparece en un CSV Haltech: fuerza a Polars a leer cada
línea entera como una única celda de texto, sin partirla por comas."""

_MAX_AVISOS_DETALLADOS = 20
"""Cota para no inundar el informe de importación si hay muchas filas
malformadas; el resto se resume en un único aviso agregado."""


def nulificar_centinelas(df: pl.DataFrame, catalogo: Catalogo) -> pl.DataFrame:
    """Convierte a nulo cualquier centinela de `catalogo.centinelas_i32`.

    Vectorizado sobre todas las columnas de canal a la vez.
    `COLUMNA_MARCA` (la marca de tiempo, texto) queda fuera: no puede
    contener un centinela entero.
    """
    if not catalogo.centinelas_i32:
        return df
    centinelas = list(catalogo.centinelas_i32)
    columnas_canal = [c for c in df.columns if c != COLUMNA_MARCA]
    if not columnas_canal:
        return df
    return df.with_columns(
        pl.when(pl.col(c).is_in(centinelas)).then(None).otherwise(pl.col(c)).alias(c)
        for c in columnas_canal
    )


def detectar_filas_malformadas(datos: bytes, cabecera: Cabecera) -> list[Aviso]:
    """Avisos para las filas cuyo número de campos no coincide con
    `cabecera.n_columnas`. Lista vacía si todas las filas son correctas.
    """
    n_lineas_cabecera = datos[: cabecera.offset_datos].count(b"\n")
    lineas = pl.read_csv(
        datos,
        skip_rows=n_lineas_cabecera,
        has_header=False,
        separator=_SEPARADOR_LINEA_COMPLETA,
        quote_char=None,
        infer_schema_length=0,
        schema_overrides={"column_1": pl.Utf8},
        truncate_ragged_lines=True,
    ).to_series()

    esperadas = cabecera.n_columnas - 1
    comas = lineas.str.count_matches(",")
    malas = comas != esperadas
    n_malas = int(malas.sum())
    if n_malas == 0:
        return []

    indices = malas.arg_true().to_list()
    avisos = [
        Aviso(
            "fila_malformada",
            f"la fila de datos {i + 1} tiene {comas[i] + 1} campos, se esperaban "
            f"{cabecera.n_columnas}; se registra y se salta (docs/01 §1.13)",
        )
        for i in indices[:_MAX_AVISOS_DETALLADOS]
    ]
    if n_malas > _MAX_AVISOS_DETALLADOS:
        avisos.append(
            Aviso(
                "fila_malformada",
                f"{n_malas - _MAX_AVISOS_DETALLADOS} fila(s) malformada(s) más, no listadas "
                "individualmente",
            )
        )
    return avisos
