"""Pruebas de la conversión de columnas de texto/booleanas a enum (FG-08).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.10.

QUÉ PROTEGE ESTA SUITE, POR CONSECUENCIA SI SE ROMPE
=====================================================
1. **El código es estable frente al orden de aparición.** Es la "DECISIÓN 1"
   del módulo: si dos logs de la misma sesión vieran los mismos estados en
   distinto orden y sacaran códigos distintos, los dos logs dejarían de
   poder compararse por código -- exactamente el problema que un canal enum
   "estable" tiene que evitar (`docs/07` §7.11).
2. **Booleano es 0 = negativo, 1 = positivo: viene de `PAREJAS_BOOLEANAS`,
   no de ordenar las dos etiquetas alfabéticamente.** Para las parejas de
   §7.10, el alfabético y el semántico coinciden por casualidad (`falso` <
   `verdadero`, `no` < `yes`, `off` < `on`): ordenar alfabéticamente daría el
   mismo resultado que el criterio elegido, así que un resultado correcto no
   demuestra por sí solo que el código sea el criterio semántico y no un
   efecto secundario del alfabeto. `test_booleano_no_depende_del_orden_
   alfabetico` deja constancia explícita de que el 0 y el 1 se comprueban
   contra la pareja declarada en `tipos.PAREJAS_BOOLEANAS`, no contra "cuál
   etiqueta es alfabéticamente menor" -- que es lo que de verdad distingue
   los dos criterios si algún día se añadiera una pareja donde diverjan.
3. **Una columna "booleana" que en el fichero completo trae un tercer
   estado no se fuerza a 0/1.** FG-05 clasifica sobre una muestra; el
   fichero completo puede desmentirla.
4. **Cardinalidad excesiva no aborta, avisa y no convierte** (E1.7): la
   columna queda disponible en crudo, no se genera un diccionario de miles
   de entradas.
5. **Los centinelas de texto no son un estado del enum.**
6. **Ausencia se representa con máscara, nunca con un código dentro de
   `codigos`** -- `codigos` y `mascara_presente` tienen que quedar alineados
   exactamente como los usa `dlv_core.almacen.construir_desde_polars`.

Se prueba también contra `samples/generico/12-texto-y-booleanos.csv`, el
fixture que motiva la tarea (columna `Marcha` con `1/2/3/N` y `Limitador`
con `true/false`).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from dlv_core.formatos.enums_csv import (
    LIMITE_CARDINALIDAD_ENUM,
    ResultadoEnum,
    convertir_a_enum,
)
from dlv_core.unidades import Catalogo, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
DATA = RAIZ / "data"


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with (DATA / "units.toml").open("rb") as fh:
        return cargar_catalogo(fh)


def serie(valores: list[str | None]) -> pl.Series:
    return pl.Series("x", valores, dtype=pl.Utf8)


def etiquetas_reconstruidas(r: ResultadoEnum, original: list[str | None]) -> list[str | None]:
    """Recompone, a partir de `codigos` + `mascara_presente` + `diccionario`,
    la lista de etiquetas alineada con `original`. Sirve para comprobar que
    los tres campos encajan exactamente como dice el docstring de
    `ResultadoEnum` -- el mismo patrón que
    `dlv_core.almacen.construir_desde_polars` usa para `t`/`v`.
    """
    reconstruido: list[str | None] = [None] * len(original)
    posiciones = np.flatnonzero(r.mascara_presente)
    assert len(posiciones) == len(r.codigos)
    for pos, codigo in zip(posiciones.tolist(), r.codigos.tolist(), strict=True):
        reconstruido[pos] = r.diccionario[codigo]
    return reconstruido


# --------------------------------------------------------------------------- #
# Decisión 1: estabilidad del código frente al orden de aparición
# --------------------------------------------------------------------------- #
def test_el_codigo_no_depende_del_orden_de_aparicion() -> None:
    """Dos columnas con el MISMO conjunto de etiquetas, en orden de aparición
    distinto (como dos logs de la misma sesión que arrancan en marchas
    distintas), tienen que dar exactamente el mismo diccionario código ->
    etiqueta. Si el criterio fuera "orden de aparición", este assert fallaría.
    """
    a = convertir_a_enum(serie(["3", "1", "N", "2", "N", "1"]))
    b = convertir_a_enum(serie(["N", "N", "2", "1", "3", "1"]))
    assert a.diccionario == b.diccionario
    assert a.diccionario == {0: "1", 1: "2", 2: "3", 3: "N"}


def test_el_codigo_es_alfabetico_incluso_con_un_subconjunto_distinto() -> None:
    """Un log que solo ve {"1", "2", "N"} (nunca metió tercera) sigue dando a
    "1", "2" y "N" el mismo código que un log que sí vio "3": el orden
    alfabético no depende de qué otras etiquetas estén presentes en ESTE
    fichero, salvo por el hueco que deja la etiqueta ausente.
    """
    con_tres = convertir_a_enum(serie(["1", "2", "3", "N"]))
    sin_tres = convertir_a_enum(serie(["1", "2", "N"]))
    assert con_tres.diccionario[0] == "1"  # código 0 -> "1" en ambos
    assert sin_tres.diccionario[0] == "1"
    assert con_tres.diccionario[1] == "2"
    assert sin_tres.diccionario[1] == "2"


# --------------------------------------------------------------------------- #
# Decisión 1: booleanos por semántica (0 = negativo, 1 = positivo), no alfabético
# --------------------------------------------------------------------------- #
def test_booleano_true_false_asigna_negativo_0_positivo_1() -> None:
    r = convertir_a_enum(serie(["true", "false", "true", "true", "false"]), booleano=True)
    assert r.convertido
    assert r.diccionario == {0: "false", 1: "true"}
    assert r.codigos.dtype == np.uint16
    assert etiquetas_reconstruidas(r, ["true", "false", "true", "true", "false"]) == [
        "true",
        "false",
        "true",
        "true",
        "false",
    ]


def test_booleano_normaliza_mayusculas_para_emparejar_pero_no_para_la_etiqueta() -> None:
    """`TRUE`/`False` se reconocen como la pareja conocida (comparación
    insensible a mayúsculas, igual que FG-05), pero la etiqueta que queda en
    el diccionario es la forma tal como aparece en el fichero, no la
    normalizada -- si dos exportadores escriben `TRUE` y `true`, cada uno
    conserva su propia grafía en su propio diccionario.
    """
    r = convertir_a_enum(serie(["TRUE", "False", "TRUE"]), booleano=True)
    assert r.convertido
    assert r.diccionario == {0: "False", 1: "TRUE"}


def test_booleano_no_depende_del_orden_alfabetico() -> None:
    """`verdadero`/`falso`: alfabéticamente "falso" < "verdadero", así que
    ordenar por alfabeto habría dado el mismo 0/1 que el criterio semántico
    por pura coincidencia. Lo que de verdad distingue los dos criterios es
    que el código sale de emparejar cada etiqueta contra
    `tipos.PAREJAS_BOOLEANAS` (`_mapa_booleano`), no de compararlas entre sí:
    si mañana se declarara una pareja donde el positivo fuera
    alfabéticamente menor que el negativo, el criterio semántico seguiría
    dando negativo=0 y el alfabético se rompería. Esta prueba fija ese
    comportamiento con la pareja actual, que es la que hay.
    """
    r = convertir_a_enum(serie(["verdadero", "falso", "verdadero"]), booleano=True)
    assert r.diccionario[0] == "falso"
    assert r.diccionario[1] == "verdadero"
    r2 = convertir_a_enum(serie(["yes", "no", "yes"]), booleano=True)
    assert r2.diccionario[0] == "no"
    assert r2.diccionario[1] == "yes"


def test_booleano_con_tercer_estado_en_el_fichero_completo_cae_a_alfabetico_y_avisa() -> None:
    """FG-05 propuso BOOLEANO mirando una muestra sin `"unknown"`; el fichero
    completo trae un tercer estado. No se fuerza 0/1: se trata como enum de
    texto general y se avisa del porqué (ver la cabecera del módulo, "UNA
    COLUMNA BOOLEANA EN LA MUESTRA...").
    """
    r = convertir_a_enum(serie(["true", "false", "unknown", "true"]), booleano=True)
    assert r.convertido
    assert r.n_valores_distintos == 3
    assert r.diccionario == {0: "false", 1: "true", 2: "unknown"}  # alfabético
    codigos = [a.codigo for a in r.avisos]
    assert "booleano_no_confirmado_en_columna_completa" in codigos


# --------------------------------------------------------------------------- #
# Cardinalidad excesiva: avisa y no convierte, no aborta
# --------------------------------------------------------------------------- #
def test_cardinalidad_excesiva_no_convierte_y_avisa() -> None:
    valores = [f"id_{i}" for i in range(20)]  # 20 distintos, límite de prueba: 10
    r = convertir_a_enum(serie(valores), limite_cardinalidad=10)
    assert not r.convertido
    assert r.diccionario == {}
    assert r.codigos.size == 0
    assert not r.mascara_presente.any()
    assert r.n_valores_distintos == 20
    assert len(r.avisos) == 1
    assert r.avisos[0].codigo == "enum_cardinalidad_excesiva"
    assert "20" in r.avisos[0].mensaje
    assert "10" in r.avisos[0].mensaje


def test_justo_en_el_limite_si_convierte() -> None:
    """El límite es inclusivo: exactamente `limite_cardinalidad` valores
    distintos sí se convierten. Es el primer valor que se descarta el que
    tiene que pasar del límite, no el que lo iguala.
    """
    valores = [f"id_{i}" for i in range(10)]
    r = convertir_a_enum(serie(valores), limite_cardinalidad=10)
    assert r.convertido
    assert len(r.diccionario) == 10


def test_limite_por_omision_es_el_del_modulo() -> None:
    assert LIMITE_CARDINALIDAD_ENUM == 512
    valores = [f"id_{i}" for i in range(LIMITE_CARDINALIDAD_ENUM + 1)]
    r = convertir_a_enum(serie(valores))
    assert not r.convertido


# --------------------------------------------------------------------------- #
# Ausencia: centinelas, vacío y nulo no son un estado del enum
# --------------------------------------------------------------------------- #
def test_los_centinelas_de_texto_no_son_un_estado(catalogo: Catalogo) -> None:
    r = convertir_a_enum(
        serie(["Alta", "NULL", "Media", "#N/A", "Alta"]),
        catalogo=catalogo,
    )
    assert r.convertido
    assert set(r.diccionario.values()) == {"Alta", "Media"}
    assert r.n_valores_distintos == 2
    assert r.mascara_presente.tolist() == [True, False, True, False, True]
    assert r.codigos.size == 3


def test_celda_vacia_y_nula_no_son_un_estado() -> None:
    r = convertir_a_enum(serie(["Alta", "", None, "Media", "  "]))
    assert r.convertido
    assert set(r.diccionario.values()) == {"Alta", "Media"}
    assert r.mascara_presente.tolist() == [True, False, False, True, False]


def test_columna_sin_ningun_dato_no_es_un_error() -> None:
    r = convertir_a_enum(serie(["", None, "  "]))
    assert r.convertido
    assert r.diccionario == {}
    assert r.codigos.size == 0
    assert not r.mascara_presente.any()
    assert r.n_valores_distintos == 0
    assert r.avisos == ()


def test_espacios_en_los_extremos_se_recortan_pero_no_los_internos() -> None:
    """ "Alta" y " Alta " son la misma etiqueta; "Punto  Muerto" con doble
    espacio interior sigue siendo distinta de "Punto Muerto": ese espacio de
    más puede ser justo el error de exportador que el informe debe señalar.
    """
    r = convertir_a_enum(serie([" Alta ", "Alta", "Punto  Muerto", "Punto Muerto"]))
    assert set(r.diccionario.values()) == {"Alta", "Punto  Muerto", "Punto Muerto"}


# --------------------------------------------------------------------------- #
# Alineación de codigos / mascara_presente con la columna original
# --------------------------------------------------------------------------- #
def test_codigos_y_mascara_reconstruyen_exactamente_la_columna_recortada() -> None:
    original = ["3", "1", None, "N", "", "2", "1"]
    r = convertir_a_enum(serie(original))
    esperado = ["3", "1", None, "N", None, "2", "1"]
    assert etiquetas_reconstruidas(r, original) == esperado


# --------------------------------------------------------------------------- #
# Contra el fixture real de la tarea
# --------------------------------------------------------------------------- #
def test_fixture_marcha_es_enum_alfabetico() -> None:
    df = pl.read_csv(GENERICOS / "12-texto-y-booleanos.csv", infer_schema_length=0)
    r = convertir_a_enum(df["Marcha"], nombre_columna="Marcha")
    assert r.convertido
    assert r.diccionario == {0: "1", 1: "2", 2: "3", 3: "N"}
    assert r.mascara_presente.all()  # la columna no trae huecos en el fixture
    assert r.codigos.size == df.height


def test_fixture_limitador_es_booleano_negativo_0_positivo_1() -> None:
    df = pl.read_csv(GENERICOS / "12-texto-y-booleanos.csv", infer_schema_length=0)
    r = convertir_a_enum(df["Limitador"], booleano=True, nombre_columna="Limitador")
    assert r.convertido
    assert r.diccionario == {0: "false", 1: "true"}
    assert r.avisos == ()  # la pareja se confirma en el fichero completo


def test_fixture_dos_lecturas_del_mismo_fichero_dan_el_mismo_diccionario() -> None:
    """No es solo teoría: leer el MISMO fixture dos veces (como si fueran dos
    aperturas del mismo log) tiene que dar el mismo diccionario las dos
    veces -- la propiedad mínima de estabilidad.
    """
    df = pl.read_csv(GENERICOS / "12-texto-y-booleanos.csv", infer_schema_length=0)
    r1 = convertir_a_enum(df["Marcha"])
    r2 = convertir_a_enum(df["Marcha"])
    assert r1.diccionario == r2.diccionario
    assert r1.codigos.tolist() == r2.codigos.tolist()
