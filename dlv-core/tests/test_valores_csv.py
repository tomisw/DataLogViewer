"""Pruebas de la conversión de valores de celda (FG-07).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.10, las tres filas de
la tabla de robustez que le tocan a esta tarea: valores ausentes (nunca 0),
unidad embebida en la celda, y separador de miles según el decimal ya
detectado.

QUÉ PROTEGE ESTA SUITE, POR CONSECUENCIA SI SE ROMPE
=====================================================
1. **Ausente nunca es 0, ni siquiera el centinela crudo convertido
   literalmente.** Un centinela de desbordamiento (`2147483647`) ES un número
   válido léxicamente, así que si la anulación explícita del final se
   rompiera, un sensor desconectado saldría como un valor de presión enorme
   pero "creíble a primera vista" en vez de un hueco -- el mismo daño que
   describe la cabecera del módulo.
2. **Unidad embebida consistente se extrae; mezclada NO se asume.** Mezclar
   `psi` y `bar` en silencio es un factor ~14x -- si esta prueba se rompiera,
   una columna con dos unidades acabaría con un `unidad_embebida` arbitrario y
   un tuner tomaría una decisión sobre un número mal etiquetado.
3. **El separador de miles se limpia según el decimal YA DADO, sin
   reinterpretarlo.** `1.234` con decimal `,` es 1234, siempre, porque el
   decimal ya fijado excluye que el `.` sea un decimal en ese fichero.
4. **El espacio como agrupador**, que `decimal_csv` no cubre, sí se limpia
   aquí (`1 234,5`).

Se prueba con datos sintéticos y contra `samples/generico/`, incluido el
fichero `17-unidad-embebida-y-miles.csv` añadido para esta tarea porque
ninguno de los ficheros existentes ejercitaba unidad embebida ni separador de
miles a la vez. Numerado `17` y no `15` para no chocar con el corpus de
robustez que añade FG-14 en paralelo.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from dlv_core.formatos.decimal_csv import detectar_separador_decimal
from dlv_core.formatos.estructura import analizar_estructura
from dlv_core.formatos.sondeo import dividir_campos, sondear_csv
from dlv_core.formatos.valores_csv import (
    OrigenUnidadEmbebida,
    convertir_valores_de_columna,
    extraer_numero_y_unidad,
    normalizar_separador_de_miles,
    separar_numero_y_unidad,
)
from dlv_core.unidades import Catalogo, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
DATA = RAIZ / "data"


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with (DATA / "units.toml").open("rb") as fh:
        return cargar_catalogo(fh)


def columna_de(ruta: Path, nombre_columna: str) -> tuple[list[str], str]:
    """La cadena FG-01 -> FG-02 -> FG-03 sobre un fichero de muestra, hasta
    sacar UNA columna de celdas crudas y el separador decimal del fichero --
    los dos argumentos que `convertir_valores_de_columna` necesita para
    reproducir lo que de verdad le llega al importador."""
    datos = ruta.read_bytes()
    s = sondear_csv(datos)
    texto = datos.decode(s.codificacion)
    d = detectar_separador_decimal(s, texto)
    e = analizar_estructura(s, d, texto)
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    filas = [
        dividir_campos(ln, s.delimitador or ",", s.comilla) for ln in lineas[e.linea_inicio_datos :]
    ]
    nombres = e.nombres_o_posicionales()
    i = nombres.index(nombre_columna)
    return [fila[i] if i < len(fila) else "" for fila in filas], d.separador


# --------------------------------------------------------------------------- #
# La regla de §7.10: ausente nunca es 0
# --------------------------------------------------------------------------- #
def test_las_ocho_formas_de_ausencia_de_la_tabla_no_son_cero(catalogo: Catalogo) -> None:
    """Las ocho formas que enumera §7.10, en una sola columna: ninguna es 0."""
    celdas = ["NaN", "inf", "-inf", "#N/A", "NULL", "---", "n/a", ""]
    r = convertir_valores_de_columna(celdas, catalogo=catalogo)
    assert r.con_dato == 0
    assert r.numericas == 0
    assert r.numeros.null_count() == len(celdas)
    assert 0.0 not in r.numeros.to_list()


def test_sin_catalogo_solo_la_celda_vacia_es_ausencia() -> None:
    """Sin centinelas, `NULL` es texto -- no ausencia -- igual que en FG-05:
    la lista de centinelas vive en `data/units.toml`, no en este módulo."""
    r = convertir_valores_de_columna(["1", "2", "NULL", ""])
    assert r.vacias == 1
    assert r.centinelas_texto == 0
    assert r.no_numericas == 1  # "NULL" cuenta como texto, no como ausencia
    assert r.numericas == 2


def test_un_centinela_de_desbordamiento_nunca_se_cuela_como_numero(catalogo: Catalogo) -> None:
    """`2147483647` es un número válido léxicamente -- si la anulación final
    no se aplicara de forma explícita, este es justo el caso que se colaría
    como un valor de presión enorme en vez de un hueco."""
    r = convertir_valores_de_columna(["12.5", "2147483647", "13.1"], catalogo=catalogo)
    assert r.centinelas_desbordamiento == 1
    assert r.numericas == 2
    valores = r.numeros.to_list()
    assert valores[1] is None
    assert 2147483647.0 not in [v for v in valores if v is not None]


def test_una_columna_toda_ausente_no_tiene_ni_un_numero(catalogo: Catalogo) -> None:
    r = convertir_valores_de_columna(["", "NaN", "---"], catalogo=catalogo)
    assert r.numericas == 0
    assert all(v is None for v in r.numeros.to_list())


# --------------------------------------------------------------------------- #
# Unidad embebida
# --------------------------------------------------------------------------- #
def test_unidad_embebida_consistente_se_extrae_y_el_numero_queda_limpio() -> None:
    r = convertir_valores_de_columna(["12.5 psi", "13.0 psi", "11.8 psi"], nombre="Boost")
    assert r.origen_unidad is OrigenUnidadEmbebida.CONSISTENTE
    assert r.unidad_embebida == "psi"
    assert r.numeros.to_list() == pytest.approx([12.5, 13.0, 11.8])
    assert r.numericas == 3
    assert r.no_numericas == 0


def test_unidad_pegada_sin_espacio_tambien_se_extrae() -> None:
    numero, unidad = separar_numero_y_unidad("12.5psi", ".")
    assert numero == "12.5"
    assert unidad == "psi"


def test_columna_sin_unidad_no_declara_ninguna() -> None:
    r = convertir_valores_de_columna(["850", "1200", "1500"])
    assert r.origen_unidad is OrigenUnidadEmbebida.NINGUNA
    assert r.unidad_embebida is None
    assert r.celdas_con_unidad == 0


def test_unidad_mezclada_no_se_asume_una_sola() -> None:
    """`psi` y `bar` en la misma columna son ~14x de diferencia: mezclarlas en
    silencio es el riesgo R1 (`docs/07` §7.15) con otra puerta de entrada.
    El número se sigue extrayendo -- no se pierden datos -- pero la unidad
    queda sin resolver y se avisa con severidad."""
    r = convertir_valores_de_columna(["14 psi", "1.1 bar", "14.2 psi"], nombre="Presion")
    assert r.origen_unidad is OrigenUnidadEmbebida.MEZCLADA
    assert r.unidad_embebida is None
    assert set(r.unidades_distintas) == {"psi", "bar"}
    assert r.numeros.to_list() == pytest.approx([14.0, 1.1, 14.2])  # el número no se pierde
    codigos = {a.codigo for a in r.avisos}
    assert "unidad_embebida_mezclada" in codigos


def test_unidad_embebida_parcial_se_avisa_pero_no_bloquea() -> None:
    r = convertir_valores_de_columna(["12.5 psi", "13.0", "11.8 psi"], nombre="Boost")
    assert r.origen_unidad is OrigenUnidadEmbebida.CONSISTENTE
    assert r.unidad_embebida == "psi"
    assert r.celdas_con_unidad == 2
    assert r.numeros.to_list() == pytest.approx([12.5, 13.0, 11.8])
    codigos = {a.codigo for a in r.avisos}
    assert "unidad_embebida_parcial" in codigos


def test_texto_sin_forma_de_numero_no_se_confunde_con_unidad() -> None:
    """`ERROR` no tiene ningún dígito: no es "número + unidad", es texto libre
    y tiene que contarse como `no_numericas`, no colarse como unidad."""
    r = convertir_valores_de_columna(["12.5 psi", "ERROR", "11.8 psi"], nombre="Boost")
    assert r.no_numericas == 1
    assert "ERROR" in r.ejemplos_no_numericos
    assert r.numeros.to_list()[1] is None


# --------------------------------------------------------------------------- #
# Separador de miles, según el decimal ya detectado
# --------------------------------------------------------------------------- #
def test_separador_de_miles_con_coma_agrupadora_y_punto_decimal() -> None:
    r = convertir_valores_de_columna(["1,234.5", "2,500.0", "999.9"], decimal=".")
    assert r.numeros.to_list() == pytest.approx([1234.5, 2500.0, 999.9])
    codigos = {a.codigo for a in r.avisos}
    assert "separador_de_miles_normalizado" in codigos


def test_separador_de_miles_con_punto_agrupador_y_coma_decimal() -> None:
    r = convertir_valores_de_columna(["1.234,5", "2.500,0", "999,9"], decimal=",")
    assert r.numeros.to_list() == pytest.approx([1234.5, 2500.0, 999.9])


def test_separador_de_miles_con_espacio_agrupador() -> None:
    """El espacio como agrupador (`1 234,5`) es lo que `decimal_csv` (FG-02)
    NO cubre -- ese módulo compara interpretaciones de decimal, no formatos de
    agrupación. Aquí sí, porque hace falta para producir el valor real."""
    r = convertir_valores_de_columna(["1 234,5", "12 345,0"], decimal=",")
    assert r.numeros.to_list() == pytest.approx([1234.5, 12345.0])


def test_el_decimal_ya_fijado_no_se_vuelve_a_adivinar() -> None:
    """Con decimal `,` ya decidido, `1.234` SOLO puede ser agrupación de
    miles (1234): el `.` no puede ser un decimal de este fichero, así que no
    hay ambigüedad que resolver aquí -- a diferencia de `decimal_csv`, que sí
    tiene que decidir el carácter en sí sobre un fichero nuevo."""
    r = convertir_valores_de_columna(["1.234", "0,050"], decimal=",")
    assert r.numeros.to_list() == pytest.approx([1234.0, 0.050])


def test_cero_con_ceros_a_la_izquierda_no_se_confunde_con_agrupacion() -> None:
    """`0,050` no puede ser un grupo de miles (la agrupación nunca tiene
    ceros a la izquierda): sigue siendo un decimal puro."""
    r = convertir_valores_de_columna(["0,050", "0,000"], decimal=",")
    assert r.numeros.to_list() == pytest.approx([0.05, 0.0])
    assert r.no_numericas == 0


def test_numeros_normales_sin_separador_no_se_alteran() -> None:
    r = convertir_valores_de_columna(["850", "1200.5", "-13.2"], decimal=".")
    assert r.numeros.to_list() == pytest.approx([850.0, 1200.5, -13.2])
    codigos = {a.codigo for a in r.avisos}
    assert "separador_de_miles_normalizado" not in codigos


def test_notacion_cientifica_se_conserva() -> None:
    r = convertir_valores_de_columna(["1.5e-3", "2E+2"], decimal=".")
    assert r.numeros.to_list() == pytest.approx([0.0015, 200.0])


# --------------------------------------------------------------------------- #
# Funciones vectorizadas (Polars) por separado
# --------------------------------------------------------------------------- #
def test_extraer_numero_y_unidad_es_vectorizado_y_coincide_con_el_escalar() -> None:
    serie = pl.Series("v", ["12.5 psi", "850", "ERROR", ""])
    numero, unidad = extraer_numero_y_unidad(serie, ".")
    assert numero.to_list() == ["12.5", "850", None, None]
    assert unidad.to_list() == ["psi", None, None, None]
    for celda, n_esperado, u_esperado in zip(
        serie.to_list(), numero.to_list(), unidad.to_list(), strict=True
    ):
        assert separar_numero_y_unidad(celda, ".") == (n_esperado, u_esperado)


def test_normalizar_separador_de_miles_conserva_los_nulos() -> None:
    crudos = pl.Series("v", ["1.234,5", None, "0,050"])
    limpio = normalizar_separador_de_miles(crudos, ",")
    assert limpio.to_list() == ["1234.5", None, "0.050"]


# --------------------------------------------------------------------------- #
# Contra el corpus real de samples/generico/
# --------------------------------------------------------------------------- #
def test_11_valores_ausentes_ninguna_ausencia_es_cero(catalogo: Catalogo) -> None:
    """Contra el fichero real de ausencias variadas: `#N/A`, `NULL`, `---`,
    `n/a` y celda vacía en las mismas columnas que datos numéricos buenos."""
    ruta = GENERICOS / "11-valores-ausentes.csv"
    celdas, decimal = columna_de(ruta, "RPM")
    r = convertir_valores_de_columna(celdas, nombre="RPM", decimal=decimal, catalogo=catalogo)
    assert r.vacias >= 1  # la línea "2.000,,192.380,..." trae RPM vacío
    assert r.centinelas_texto > 0  # y varias celdas "#N/A"
    assert r.numeros.null_count() == r.celdas - r.numericas
    assert 0.0 not in [v for v in r.numeros.to_list() if v is not None]


def test_fixture_15_unidad_embebida_bar(catalogo: Catalogo) -> None:
    ruta = GENERICOS / "17-unidad-embebida-y-miles.csv"
    celdas, decimal = columna_de(ruta, "Presion_Aceite")
    assert decimal == ","
    r = convertir_valores_de_columna(
        celdas, nombre="Presion_Aceite", decimal=decimal, catalogo=catalogo
    )
    assert r.origen_unidad is OrigenUnidadEmbebida.CONSISTENTE
    assert r.unidad_embebida == "bar"
    # NULL, celda vacía y #N/A: tres ausencias, ninguna como 0 ni como número.
    assert r.vacias + r.centinelas_texto == 3
    assert r.numeros.null_count() == 3
    assert 0.0 not in [v for v in r.numeros.to_list() if v is not None]
    assert max(v for v in r.numeros.to_list() if v is not None) < 5.0  # bar, no psi ni kPa


def test_fixture_15_distancia_con_separador_de_miles(catalogo: Catalogo) -> None:
    ruta = GENERICOS / "17-unidad-embebida-y-miles.csv"
    celdas, decimal = columna_de(ruta, "Distancia_Total")
    assert decimal == ","
    r = convertir_valores_de_columna(
        celdas, nombre="Distancia_Total", decimal=decimal, catalogo=catalogo
    )
    assert r.no_numericas == 0
    assert r.numericas == len(celdas)
    valores = r.numeros.to_list()
    assert min(valores) == pytest.approx(1234.5)
    assert max(valores) == pytest.approx(1247.2)
    # Sin la normalización, "1.234,5" con el punto sin quitar habría dado
    # 1.2345 (parseado a lo bruto) o directamente null: cualquiera de los dos
    # es exactamente el defecto que esta tarea evita.
    assert all(v > 1000 for v in valores)
