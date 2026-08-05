"""Pruebas de la precedencia de unidad activa por canal (tarea F1-17).

Especificación: `docs/06-sistema-de-unidades.md` §6.9.

QUÉ PROTEGE ESTA SUITE
======================
`resolver_unidad` es la pieza que decide, para un canal concreto, en qué
unidad se pinta: la respuesta correcta no es solo «qué unidad» sino «qué
unidad, y por qué capa de precedencia». Un error de orden aquí es silencioso
del peor modo posible: un panel entero se pinta en la unidad equivocada sin que
nada falle a gritos, porque cada capa por separado devuelve una unidad
perfectamente válida — el fallo es cuál de ellas gana.

Tres cosas que proteger:

1. **El orden exacto**: canal > perfil > preset > canónica. Se comprueba
   dando, en cada prueba, capas MÁS ESPECÍFICAS que contradicen a las menos
   específicas, para que un fallo de orden se note en la unidad devuelta y no
   solo en un contador.
2. **Las capas que faltan** se saltan sin romper nada: sin anulación de canal,
   sin perfil activo, o con un perfil que no cubre esa dimensión (varios
   presets de fábrica no fijan `angle`, por ejemplo).
3. **La procedencia** (`UnidadResuelta.capa` / `.explicacion`) es correcta, no
   solo la unidad — es lo que permite a la interfaz explicar la elección.

Solo biblioteca estándar. El catálogo es el real de `data/units.toml`, no un
mock: las combinaciones de presets y dimensiones que se ejercitan aquí son las
de fábrica.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dlv_core.resolucion_unidad import Capa, UnidadResuelta, resolver_unidad
from dlv_core.unidades import Catalogo, ErrorDeUnidad, cargar_catalogo

CATALOGO_TOML = Path(__file__).resolve().parents[2] / "data" / "units.toml"


@pytest.fixture(scope="module")
def cat() -> Catalogo:
    with CATALOGO_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


# --------------------------------------------------------------------------- #
# La escalera de precedencia, capa a capa, con una tabla de escenarios
# --------------------------------------------------------------------------- #
# Cada fila da, a propósito, todas las capas posibles con valores DISTINTOS
# entre sí, para que la unidad devuelta delate por sí sola cuál capa ganó: si
# el orden se rompiera, el test fallaría en la aserción de la unidad, no solo
# en la de `capa`.
ESCALERA: list[dict[str, Any]] = [
    {
        "id": "canal_gana_a_perfil_y_a_preset",
        "dimension_id": "temperature",
        "anulacion_canal": "degF",
        "preferencias_perfil": {"temperature": "degC"},
        "preset": "metrico",
        "capa_esperada": Capa.CANAL,
        "unidad_esperada": "degF",
    },
    {
        "id": "perfil_gana_a_preset_sin_anulacion_de_canal",
        "dimension_id": "temperature",
        "anulacion_canal": None,
        "preferencias_perfil": {"temperature": "K"},
        "preset": "metrico",  # metrico fija degC: si el perfil no ganara, saldría degC
        "capa_esperada": Capa.PERFIL,
        "unidad_esperada": "K",
    },
    {
        "id": "preset_gana_a_canonica_sin_canal_ni_perfil",
        "dimension_id": "pressure",
        "anulacion_canal": None,
        "preferencias_perfil": None,
        "preset": "imperial",  # canónica de presión es kPa; imperial fija psi
        "capa_esperada": Capa.PRESET,
        "unidad_esperada": "psi",
    },
    {
        "id": "perfil_presente_pero_sin_esta_dimension_cae_al_preset",
        "dimension_id": "speed",
        "anulacion_canal": None,
        "preferencias_perfil": {"temperature": "degC"},  # no menciona 'speed'
        "preset": "imperial",
        "capa_esperada": Capa.PRESET,
        "unidad_esperada": "mph",
    },
    {
        "id": "sin_canal_ni_perfil_ni_entrada_de_preset_cae_a_canonica",
        "dimension_id": "torque",  # ningún preset de fábrica fija 'torque'
        "anulacion_canal": None,
        "preferencias_perfil": None,
        "preset": "metrico",
        "capa_esperada": Capa.CANONICA,
        "unidad_esperada": "Nm",
    },
    {
        "id": "dimension_ausente_de_presets_si_metrico_e_imperial_cae_a_canonica",
        "dimension_id": "angle",  # solo los presets motorsport fijan 'angle'
        "anulacion_canal": None,
        "preferencias_perfil": None,
        "preset": "si",
        "capa_esperada": Capa.CANONICA,
        "unidad_esperada": "deg",
    },
    {
        "id": "sin_preset_explicito_usa_el_preset_por_omision_del_catalogo",
        "dimension_id": "pressure",
        "anulacion_canal": None,
        "preferencias_perfil": None,
        "preset": None,  # el catálogo marca 'metrico' como por_omision -> bar
        "capa_esperada": Capa.PRESET,
        "unidad_esperada": "bar",
    },
]


@pytest.mark.parametrize("caso", ESCALERA, ids=[c["id"] for c in ESCALERA])
def test_precedencia(cat: Catalogo, caso: dict[str, Any]) -> None:
    resuelta = resolver_unidad(
        caso["dimension_id"],
        catalogo=cat,
        preset=caso["preset"],
        preferencias_perfil=caso["preferencias_perfil"],
        anulacion_canal=caso["anulacion_canal"],
    )
    assert resuelta.capa is caso["capa_esperada"], (
        f"{caso['id']}: capa {resuelta.capa.value}, esperada {caso['capa_esperada'].value}"
    )
    assert resuelta.unidad.id == caso["unidad_esperada"], (
        f"{caso['id']}: unidad {resuelta.unidad.id}, esperada {caso['unidad_esperada']}"
    )
    assert resuelta.dimension_id == caso["dimension_id"]


# --------------------------------------------------------------------------- #
# Ausencia total de capas activas: solo queda la canónica
# --------------------------------------------------------------------------- #
def test_sin_ninguna_capa_activa_se_usa_la_canonica(cat: Catalogo) -> None:
    """El caso base: ni canal, ni perfil, ni preset explícito.

    Como siempre hay un preset por omisión, esto solo llega a canónica para una
    dimensión que ese preset no cubre.
    """
    resuelta = resolver_unidad("torque", catalogo=cat)
    assert resuelta.capa is Capa.CANONICA
    assert resuelta.unidad.id == cat.dimension("torque").unidad_canonica


def test_preferencias_de_perfil_vacias_se_tratan_como_ausentes(cat: Catalogo) -> None:
    resuelta = resolver_unidad("pressure", catalogo=cat, preset="imperial", preferencias_perfil={})
    assert resuelta.capa is Capa.PRESET
    assert resuelta.unidad.id == "psi"


# --------------------------------------------------------------------------- #
# Errores: mismos mensajes que el resto del motor de unidades
# --------------------------------------------------------------------------- #
def test_dimension_desconocida_da_un_error_util(cat: Catalogo) -> None:
    with pytest.raises(ErrorDeUnidad, match="dimensión desconocida"):
        resolver_unidad("presion", catalogo=cat)


def test_preset_desconocido_da_un_error_util(cat: Catalogo) -> None:
    with pytest.raises(ErrorDeUnidad, match="preset desconocido"):
        resolver_unidad("pressure", catalogo=cat, preset="rally_de_fantasia")


def test_anulacion_de_canal_con_unidad_invalida_da_un_error_util(cat: Catalogo) -> None:
    with pytest.raises(ErrorDeUnidad, match="Disponibles"):
        resolver_unidad("temperature", catalogo=cat, anulacion_canal="kelvines")


def test_preferencia_de_perfil_con_unidad_invalida_da_un_error_util(cat: Catalogo) -> None:
    with pytest.raises(ErrorDeUnidad, match="Disponibles"):
        resolver_unidad(
            "temperature", catalogo=cat, preferencias_perfil={"temperature": "kelvines"}
        )


def test_alias_de_unidad_se_resuelve_igual_en_cualquier_capa(cat: Catalogo) -> None:
    """`Dimension.unidad` resuelve alias; la precedencia no debe repetir esa lógica
    ni romperla: mbar es alias de hPa."""
    resuelta = resolver_unidad("pressure", catalogo=cat, anulacion_canal="mbar")
    assert resuelta.unidad.id == "hPa"
    assert resuelta.capa is Capa.CANAL


# --------------------------------------------------------------------------- #
# La explicación, para la interfaz
# --------------------------------------------------------------------------- #
def test_cada_capa_tiene_una_explicacion_distinta_y_no_vacia() -> None:
    textos = {capa: capa for capa in Capa}  # solo para iterar los cuatro miembros
    explicaciones = set()
    for capa in textos:
        resuelta = UnidadResuelta(unidad=_unidad_de_prueba(), capa=capa, dimension_id="x")
        assert resuelta.explicacion.strip(), f"{capa}: explicación vacía"
        explicaciones.add(resuelta.explicacion)
    assert len(explicaciones) == len(Capa), "dos capas comparten la misma explicación"


def _unidad_de_prueba() -> Any:
    """Evita depender del catálogo real para esta prueba puramente de texto."""
    from dlv_core.unidades import Afin, Unidad

    return Unidad(id="x", etiqueta="x", conversion=Afin(a=1.0), decimales=0)


def test_todos_los_miembros_de_capa_tienen_explicacion_registrada() -> None:
    """Si se añade una capa nueva sin registrar su explicación, esto lo detecta
    en vez de lanzar un `KeyError` la primera vez que la interfaz la pida."""
    for capa in Capa:
        resuelta = UnidadResuelta(unidad=_unidad_de_prueba(), capa=capa, dimension_id="x")
        assert isinstance(resuelta.explicacion, str)
