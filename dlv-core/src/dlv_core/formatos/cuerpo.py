"""Parseo del cuerpo del CSV con Polars (tarea F1-02).

Paso 3 de la ruta de ingesta (`docs/03-arquitectura.md` §3.4): `polars.read_csv`
sobre `datos[cabecera.offset_datos:]` con los parámetros resueltos desde la
`Cabecera` que produjo F1-01. Produce un `DataFrame` **crudo**: la marca de
tiempo como texto sin parsear y una columna entera por canal, con las celdas
vacías como nulos (no como 0 — docs/01, "hueco != 0"). La consolidación
(grupos de muestreo, `t` compartido, conversión a canónica) es F1-03; la
construcción de `ChannelSeries` (ADR-003) es F1-05. Este módulo no hace
ninguna de las dos.

POR QUÉ Int32 Y NO EL Int64 POR OMISIÓN DE POLARS
==================================================
Hallazgo del *spike* de F0-01: sobre el sintético de 1 h, un `read_csv` que
deja inferir el tipo numérico da un pico de memoria de 4,42x el tamaño del CSV
(presupuesto `memoria_residente` <= 3,5x). El camino nativo Haltech es en la
práctica `INT32_SCALED` en su totalidad (ADR-003): proyectar explícitamente
cada columna de canal a `Int32` (en vez de dejar que Polars infiera `Int64`,
y sin gastar tiempo en inferir nada, con `infer_schema_length=0` porque aquí
se declara el esquema completo) baja el pico a ~3,3x sin coste de *throughput*
— de hecho lo sube, porque Polars no tiene que muestrear el fichero para
adivinar tipos.

FILAS CON NÚMERO DE CAMPOS DISTINTO
===================================
`samples/corrupt/02-fila-corta.csv` y `03-fila-larga.csv` son parte del
corpus de corruptos (docs/01, `samples/corrupt/README.md`, casos 02 y 03):
"cargar con aviso, ignorar la fila / los campos extra, resto del fichero
válido". `truncate_ragged_lines=True` reproduce exactamente ese
comportamiento en Polars: rellena con nulos las filas cortas y descarta los
campos sobrantes de las largas, sin lanzar excepción y sin bucle de Python.
"""

from __future__ import annotations

import polars as pl

from dlv_core.formatos.haltech import Cabecera

__all__ = ["columna_polars", "esquema", "parsear_cuerpo"]


def columna_polars(indice_de_fila: int) -> str:
    """Nombre que da Polars a una columna cuando se lee con `has_header=False`.

    Polars numera 1-based: la columna 0 de la fila (la marca de tiempo) se
    llama `"column_1"`; un canal con `Canal.columna == 1` (el primero,
    `orden == 0`) se llama `"column_2"`. Quien construya `ChannelSeries` en
    F1-05 usa esta misma función para ir de `Canal.columna` al nombre real.
    """
    return f"column_{indice_de_fila + 1}"


COLUMNA_MARCA: str = columna_polars(0)
"""Nombre de columna de la marca de tiempo (texto `HH:MM:SS.mmm`, sin parsear:
eso es `dlv_core.reloj`, F1-03/F1-04)."""


def esquema(cabecera: Cabecera) -> dict[str, type[pl.DataType]]:
    """`schema_overrides` para `pl.read_csv`: marca en texto, canales en `Int32`.

    Cubre todas las columnas esperadas de la fila (`cabecera.n_columnas`), así
    que `infer_schema_length=0` en `parsear_cuerpo` no pierde nada: no queda
    ninguna columna por inferir.
    """
    overrides: dict[str, type[pl.DataType]] = {COLUMNA_MARCA: pl.Utf8}
    for canal in cabecera.canales:
        overrides[columna_polars(canal.columna)] = pl.Int32
    return overrides


def parsear_cuerpo(datos: bytes, cabecera: Cabecera) -> pl.DataFrame:
    """Parsea el cuerpo (docs/03 §3.4 paso 3) a partir de `cabecera.offset_datos`.

    `datos` son los bytes completos del fichero (los mismos que se pasaron a
    `parsear_cabecera`): este módulo se salta la cabecera con el offset ya
    resuelto, sin volver a recorrerla.

    Se salta la cabecera con `skip_rows` (número de líneas), no cortando
    `datos[offset:]`: `bytes` es inmutable, así que esa porción se copiaría
    entera antes de que Polars viera un solo byte -- con un CSV de 70 MB eso
    es otro tanto de memoria de pico por nada (hallazgo de F0-01/F1-02:
    `datos[offset:]` sube el pico de 4,3x a 5,3x el tamaño del CSV frente al
    presupuesto <=3,5x). Contar saltos de línea solo en la cabecera (unos
    pocos KB) es barato y evita la copia del cuerpo entero.
    """
    n_lineas_cabecera = datos[: cabecera.offset_datos].count(b"\n")
    return pl.read_csv(
        datos,
        skip_rows=n_lineas_cabecera,
        has_header=False,
        separator=",",
        schema_overrides=esquema(cabecera),
        null_values=[""],
        infer_schema_length=0,
        truncate_ragged_lines=True,
    )
