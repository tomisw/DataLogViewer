"""Pruebas de robustez del importador de CSV genérico (tarea FG-14).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.10, las tres primeras
filas de la tabla -- filas de longitud variable, columnas duplicadas y
cabecera sin nombres.

QUÉ PROTEGE ESTA SUITE, POR CONSECUENCIA SI SE ROMPE
=====================================================
1. **Nunca se aborta la carga** por una fila corta o larga: es la regla que
   más fácil se rompe si alguien cambia `truncate_ragged_lines` por una
   excepción "más segura". Una carpeta con 3 logs buenos y 1 con una fila
   rota tiene que abrir los 4 (E1.7), no fallar entera.
2. **Un hueco de fila corta NUNCA es 0.** Si `null_values=[""]` se pierde o el
   esquema deja de ser `Utf8`, una `CLT` ausente en la última fila del log
   puede leerse como `CLT=0` y un detector de sobrecalentamiento la
   confundiría con un motor frío en vez de con un sensor sin dato.
3. **Dos columnas duplicadas siguen siendo dos columnas**, no se funden ni se
   pierde una: `RPM` y `RPM_2` tienen que llegar como series independientes,
   con la MISMA cantidad de valores que trae el fichero.
4. **La identidad de FG-03 no cambia.** `estructura.nombres` sigue trayendo
   los duplicados sin renombrar (docs/01 §1.3): lo que este módulo desambigua
   es una vista aparte, y esta suite comprueba que las dos cosas conviven.
5. **Cabecera sin nombres da `col_1…col_n`**, y con nombres parciales
   (huecos sueltos dentro de una cabecera real) también, sin que el fichero
   entero se declare sin cabecera.

Se prueba contra los ficheros de `samples/generico/` (la cadena
FG-01 -> FG-02 -> FG-03 que los lee es la misma que usa el asistente) y con
`Estructura` construida a mano para los casos que no dependen de sondear un
fichero de verdad (huecos de nombre, colisión de sufijo).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import polars as pl
import pytest

from dlv_core.formatos.decimal_csv import detectar_separador_decimal
from dlv_core.formatos.estructura import Estructura, analizar_estructura
from dlv_core.formatos.robustez_csv import (
    ErrorDeRobustez,
    leer_bloque_de_datos,
    nombres_de_presentacion,
)
from dlv_core.formatos.sondeo import Sondeo, sondear_csv

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"


def analizar(datos: bytes) -> tuple[Sondeo, Estructura, str]:
    """La cadena FG-01 -> FG-02 -> FG-03 sobre los mismos bytes, más el texto
    decodificado que necesita `leer_bloque_de_datos` (FG-14)."""
    s = sondear_csv(datos)
    texto = datos.decode(s.codificacion)
    d = detectar_separador_decimal(s, texto)
    e = analizar_estructura(s, d, texto)
    return s, e, texto


def de(ruta: Path) -> tuple[Sondeo, Estructura, str]:
    return analizar(ruta.read_bytes())


def codigos(avisos: object) -> set[str]:
    return {a.codigo for a in avisos}  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Filas de longitud variable (§7.10, regla 1)
# --------------------------------------------------------------------------- #
def test_filas_de_longitud_variable_no_abortan() -> None:
    s, e, texto = de(GENERICOS / "15-filas-longitud-variable.csv")
    resultado = leer_bloque_de_datos(texto, s, e)

    assert resultado.filas_cortas == 1
    assert resultado.filas_largas == 1
    assert resultado.filas_de_datos == 50
    assert resultado.tabla.height == 50
    assert "filas_cortas" in codigos(resultado.avisos)
    assert "filas_largas" in codigos(resultado.avisos)


def test_fila_corta_rellena_con_ausente_no_con_cero() -> None:
    """El hueco de la fila corta (le faltan CLT y Lambda) llega como `null`,
    nunca como cadena vacía indistinguible de 0 (docs/01: "hueco != 0")."""
    s, e, texto = de(GENERICOS / "15-filas-longitud-variable.csv")
    resultado = leer_bloque_de_datos(texto, s, e)

    fila_corta = resultado.tabla.row(45, named=True)  # i == 45 en el generador
    assert fila_corta["CLT"] is None
    assert fila_corta["Lambda"] is None
    # Los campos que SÍ traía la fila corta no se tocan.
    assert fila_corta["Time"] == "2.250"
    assert fila_corta["TPS"] is not None


def test_fila_larga_descarta_el_campo_de_sobra_sin_perder_los_demas() -> None:
    s, e, texto = de(GENERICOS / "15-filas-longitud-variable.csv")
    resultado = leer_bloque_de_datos(texto, s, e)

    fila_larga = resultado.tabla.row(48, named=True)  # i == 48 en el generador
    assert fila_larga["Lambda"] == "0.771"
    assert "col_7" not in resultado.tabla.columns
    assert len(resultado.tabla.columns) == 6


def test_ficheros_sin_filas_ragged_no_avisan_de_longitud() -> None:
    """Control negativo: un fichero normal no dispara `filas_cortas`/`filas_largas`."""
    s, e, texto = de(GENERICOS / "01-coma-punto.csv")
    resultado = leer_bloque_de_datos(texto, s, e)

    assert resultado.filas_cortas == 0
    assert resultado.filas_largas == 0
    assert codigos(resultado.avisos).isdisjoint({"filas_cortas", "filas_largas"})


def test_delimitador_citado_no_cuenta_como_fila_larga() -> None:
    """Una coma DENTRO de un campo citado no es un campo de más.

    Sin `_quitar_contenido_citado`, `"idle, ok"` se contaría como dos campos y
    la fila (con 3 columnas de verdad) parecería tener 4 -- una falsa
    'fila_larga' por cada comentario de piloto con una coma dentro.
    """
    # Cuatro columnas y no tres: con solo "Time,Note,RPM" la fracción numérica
    # de la fila ("0.000", "idle, ok", "900") es 2/3 = 0,67, por debajo de
    # `FRACCION_NUMERICA_MINIMA` (0,7) de FG-03, y el fichero se declararía
    # sin datos reconocibles antes de llegar a esta tarea. Con "MAP" de más
    # sube a 3/4 = 0,75.
    texto = 'Time,Note,RPM,MAP\n0.000,"idle, ok",900,95.500\n0.050,"steady",950,96.000\n'
    s, e, _ = analizar(texto.encode("utf-8"))
    assert s.comilla == '"'

    resultado = leer_bloque_de_datos(texto, s, e)
    assert resultado.filas_largas == 0
    assert resultado.filas_cortas == 0
    assert resultado.tabla.height == 2
    assert resultado.tabla.row(0, named=True)["Note"] == "idle, ok"


def test_error_de_robustez_sin_delimitador() -> None:
    """Sin delimitador propuesto por el sondeo, no hay campos que leer: se
    rechaza explícitamente (E1.7: "un rechazo explicado" es un desenlace
    legítimo), no se inventa uno.

    `sondeo`/`estructura` se calculan sobre un fichero normal -- para que
    `analizar_estructura` no tropiece antes de llegar a esta tarea -- y solo el
    `Sondeo` que se le pasa a `leer_bloque_de_datos` se sustituye por una copia
    sin delimitador (`dataclasses.replace`), que es la situación real que
    dispara esta guarda: el asistente aún no ha confirmado uno.
    """
    s, e, texto = de(GENERICOS / "01-coma-punto.csv")
    sin_delimitador = replace(s, delimitador=None)

    with pytest.raises(ErrorDeRobustez):
        leer_bloque_de_datos(texto, sin_delimitador, e)


# --------------------------------------------------------------------------- #
# Columnas duplicadas (§7.10, regla 2)
# --------------------------------------------------------------------------- #
def test_columnas_duplicadas_se_desambiguan_con_sufijo() -> None:
    s, e, texto = de(GENERICOS / "13-columnas-duplicadas.csv")

    nombres, avisos = nombres_de_presentacion(e)
    assert nombres == ("Time", "RPM", "RPM_2", "MAP", "TPS", "CLT")
    assert "columna_duplicada_desambiguada" in codigos(avisos)

    resultado = leer_bloque_de_datos(texto, s, e)
    assert resultado.nombres == nombres
    assert resultado.tabla.columns == list(nombres)
    assert resultado.tabla.height == 50
    # Las dos columnas RPM siguen siendo dos series independientes, no una
    # fundida con la otra: el fichero trae valores distintos en cada una.
    assert not resultado.tabla["RPM"].equals(resultado.tabla["RPM_2"])


def test_desambiguacion_no_reescribe_la_identidad_de_estructura() -> None:
    """FG-03 (`estructura.py`) sigue avisando de los duplicados con SU propio
    código y sin renombrar `Estructura.nombres`: la identidad de una columna de
    CSV genérico es su posición (docs/01 §1.3), y esta tarea no la cambia,
    solo añade una vista de presentación al lado."""
    _, e, _ = de(GENERICOS / "13-columnas-duplicadas.csv")

    assert e.nombres == ("Time", "RPM", "RPM", "MAP", "TPS", "CLT")
    assert "nombres_duplicados" in codigos(e.avisos)


def test_sufijo_que_choca_con_un_nombre_real_sigue_incrementando() -> None:
    """`RPM`, `RPM_2` y `RPM` a la vez: el tercer `RPM` no puede desambiguarse
    a `RPM_2` porque esa columna ya existe con ese nombre en el fichero."""
    e = Estructura(
        linea_inicio_datos=1,
        linea_nombres=0,
        linea_unidades=None,
        nombres=("RPM", "RPM_2", "RPM"),
        unidades_declaradas=(),
        preambulo=(),
        metadatos={},
        n_columnas=3,
        filas_de_datos_vistas=1,
    )

    nombres, avisos = nombres_de_presentacion(e)
    assert nombres == ("RPM", "RPM_2", "RPM_3")
    assert len(set(nombres)) == 3
    assert "columna_duplicada_desambiguada" in codigos(avisos)


# --------------------------------------------------------------------------- #
# Cabecera sin nombres (§7.10, regla 3)
# --------------------------------------------------------------------------- #
def test_cabecera_sin_nombres_usa_col_n() -> None:
    s, e, texto = de(GENERICOS / "16-cabecera-sin-nombres.csv")
    assert e.linea_nombres is None
    assert e.linea_inicio_datos == 0

    nombres, avisos = nombres_de_presentacion(e)
    assert nombres == ("col_1", "col_2", "col_3", "col_4", "col_5", "col_6")
    # `nombres_o_posicionales` (FG-03) ya cubre este caso entero: no hay
    # huecos que rellenar ni duplicados que desambiguar aquí.
    assert avisos == []

    resultado = leer_bloque_de_datos(texto, s, e)
    assert resultado.tabla.columns == list(nombres)
    assert resultado.tabla.height == 50
    assert resultado.tabla.row(0, named=True)["col_1"] == "0.000"


def test_huecos_individuales_en_una_cabecera_real_se_rellenan() -> None:
    """`Time,,MAP`: la cabecera SÍ existe, pero a la columna 2 le falta el
    nombre. No es el mismo caso que "cabecera sin nombres" -- aquí
    `nombres_o_posicionales` no toca nada porque `nombres` no está vacío --
    así que esta tarea tiene que rellenar el hueco suelto."""
    e = Estructura(
        linea_inicio_datos=1,
        linea_nombres=0,
        linea_unidades=None,
        nombres=("Time", "", "MAP"),
        unidades_declaradas=(),
        preambulo=(),
        metadatos={},
        n_columnas=3,
        filas_de_datos_vistas=1,
    )

    nombres, avisos = nombres_de_presentacion(e)
    assert nombres == ("Time", "col_2", "MAP")
    assert "nombre_de_columna_generado" in codigos(avisos)


def test_hueco_y_duplicado_a_la_vez() -> None:
    """Un hueco que, rellenado por posición, choca con un nombre real que el
    fichero ya trae: primero se rellena el hueco, luego se desambigua todo
    junto, así que el resultado sigue siendo único."""
    e = Estructura(
        linea_inicio_datos=1,
        linea_nombres=0,
        linea_unidades=None,
        nombres=("Time", "", "col_2"),
        unidades_declaradas=(),
        preambulo=(),
        metadatos={},
        n_columnas=3,
        filas_de_datos_vistas=1,
    )

    nombres, avisos = nombres_de_presentacion(e)
    assert len(set(nombres)) == 3
    assert nombres[0] == "Time"
    assert "nombre_de_columna_generado" in codigos(avisos)
    assert "columna_duplicada_desambiguada" in codigos(avisos)


# --------------------------------------------------------------------------- #
# Barrido de regresión sobre el corpus entero
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("nombre_fichero", sorted(p.name for p in GENERICOS.glob("*.csv")))
def test_todo_el_corpus_se_lee_sin_abortar(nombre_fichero: str) -> None:
    """E1.7: cualquier fichero del corpus produce una tabla utilizable o un
    rechazo explicado (`ErrorDeRobustez`/`ErrorDeEstructura`/`ErrorDeSondeo`),
    nunca una excepción no controlada."""
    s, e, texto = de(GENERICOS / nombre_fichero)
    resultado = leer_bloque_de_datos(texto, s, e)

    assert resultado.tabla.height == resultado.filas_de_datos
    assert len(set(resultado.tabla.columns)) == len(resultado.tabla.columns)
    assert isinstance(resultado.tabla, pl.DataFrame)
