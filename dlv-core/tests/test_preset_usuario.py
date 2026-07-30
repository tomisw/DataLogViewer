"""Pruebas del preset de usuario (tarea F1-18).

Especificación: `docs/06-sistema-de-unidades.md` §6.9, línea 194 — «un preset
es un fichero de datos y el usuario puede crear el suyo».

QUÉ PROTEGE ESTA SUITE
======================
Los cinco presets de fábrica (SI, Métrico, Imperial, Motorsport EU, Motorsport
US) están en `data/units.toml` y los prueba otra suite; esta protege la pieza
que falta: que un preset construido a mano por el usuario (1) se valide contra
el catálogo real con los mismos errores que el resto del motor de unidades,
(2) sobreviva una vuelta completa por `dict`/JSON sin perder ni cambiar nada,
y (3) encaje sin fricción en `resolucion_unidad.resolver_unidad` como
`preferencias_perfil` — con la misma precedencia que ya prueba
`test_resolucion_unidad.py` (canal > perfil > preset > canónica): aquí solo se
confirma que un `PresetUsuario` real ocupa el lugar de "perfil" sin que haga
falta ninguna conversión.

Solo biblioteca estándar. El catálogo es el real de `data/units.toml`, no un
mock.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dlv_core.preset_usuario import PresetUsuario, crear_preset_usuario
from dlv_core.resolucion_unidad import Capa, resolver_unidad
from dlv_core.unidades import Catalogo, ErrorDeUnidad, cargar_catalogo

CATALOGO_TOML = Path(__file__).resolve().parents[2] / "data" / "units.toml"


@pytest.fixture(scope="module")
def cat() -> Catalogo:
    with CATALOGO_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


# --------------------------------------------------------------------------- #
# Construcción y validación contra el catálogo real
# --------------------------------------------------------------------------- #
def test_preset_de_usuario_valido_se_construye_y_valida(cat: Catalogo) -> None:
    """El ejemplo del propio documento: el tuner estadounidense."""
    preset = crear_preset_usuario(
        "Tuner USA",
        {"temperature": "degF", "pressure": "psi", "mixture_ratio": "afr"},
        catalogo=cat,
    )
    assert preset.nombre == "Tuner USA"
    assert preset.unidades == {"temperature": "degF", "pressure": "psi", "mixture_ratio": "afr"}
    # No debe lanzar: ya se validó en la construcción.
    preset.validar(cat)


def test_preset_vacio_de_unidades_es_valido(cat: Catalogo) -> None:
    """Un preset que no fija ninguna dimensión es degenerado pero no inválido:
    cada dimensión simplemente cae a la capa canónica en `resolver_unidad`."""
    preset = crear_preset_usuario("vacio", {}, catalogo=cat)
    preset.validar(cat)
    assert preset.a_mapeo() == {}


def test_alias_de_unidad_es_valido_en_un_preset_de_usuario(cat: Catalogo) -> None:
    """`Dimension.unidad` resuelve alias; el preset de usuario no debe rechazar
    uno solo porque no es la forma canónica del id (mbar es alias de hPa)."""
    preset = crear_preset_usuario("con_alias", {"pressure": "mbar"}, catalogo=cat)
    preset.validar(cat)  # no lanza


def test_dimension_desconocida_da_el_mismo_error_que_el_catalogo(cat: Catalogo) -> None:
    with pytest.raises(ErrorDeUnidad, match="dimensión desconocida"):
        crear_preset_usuario("malo", {"presion": "bar"}, catalogo=cat)


def test_unidad_invalida_para_la_dimension_da_el_mismo_error_que_el_catalogo(
    cat: Catalogo,
) -> None:
    with pytest.raises(ErrorDeUnidad, match="Disponibles"):
        crear_preset_usuario("malo", {"temperature": "kelvines"}, catalogo=cat)


def test_nombre_vacio_es_invalido(cat: Catalogo) -> None:
    with pytest.raises(ErrorDeUnidad, match="nombre"):
        crear_preset_usuario("   ", {"temperature": "degF"}, catalogo=cat)


CASOS_INVALIDOS: list[dict[str, Any]] = [
    {
        "id": "una_dimension_buena_y_una_desconocida",
        "unidades": {"temperature": "degF", "no_existe": "x"},
        "patron": "dimensión desconocida",
    },
    {
        "id": "una_dimension_buena_y_una_unidad_mala",
        "unidades": {"temperature": "degF", "pressure": "no_es_una_unidad"},
        "patron": "Disponibles",
    },
]


@pytest.mark.parametrize("caso", CASOS_INVALIDOS, ids=[c["id"] for c in CASOS_INVALIDOS])
def test_validacion_revisa_todas_las_entradas_no_solo_la_primera(
    cat: Catalogo, caso: dict[str, Any]
) -> None:
    with pytest.raises(ErrorDeUnidad, match=caso["patron"]):
        crear_preset_usuario("mixto", caso["unidades"], catalogo=cat)


# --------------------------------------------------------------------------- #
# Serialización: dict y JSON, ida y vuelta
# --------------------------------------------------------------------------- #
def test_round_trip_por_dict_reproduce_el_preset(cat: Catalogo) -> None:
    original = crear_preset_usuario(
        "Tuner USA", {"temperature": "degF", "pressure": "psi"}, catalogo=cat
    )
    bruto = original.a_dict()
    reconstruido = PresetUsuario.desde_dict(bruto)
    assert reconstruido == original
    reconstruido.validar(cat)  # sigue siendo válido tras la vuelta


def test_round_trip_por_json_reproduce_el_preset(cat: Catalogo) -> None:
    original = crear_preset_usuario(
        "Tuner USA",
        {"temperature": "degF", "pressure": "psi", "mixture_ratio": "afr"},
        catalogo=cat,
    )
    texto = original.a_json()
    reconstruido = PresetUsuario.desde_json(texto)
    assert reconstruido == original
    assert reconstruido.a_dict() == original.a_dict()


def test_a_dict_es_json_compatible_con_solo_str_y_dict(cat: Catalogo) -> None:
    preset = crear_preset_usuario("x", {"temperature": "degF"}, catalogo=cat)
    bruto = preset.a_dict()
    assert isinstance(bruto["nombre"], str)
    assert isinstance(bruto["unidades"], dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in bruto["unidades"].items())


def test_desde_dict_con_clave_faltante_da_un_error_util() -> None:
    with pytest.raises(ErrorDeUnidad, match="incompleto"):
        PresetUsuario.desde_dict({"nombre": "x"})
    with pytest.raises(ErrorDeUnidad, match="incompleto"):
        PresetUsuario.desde_dict({"unidades": {}})


def test_desde_dict_con_unidades_de_forma_incorrecta_da_un_error_util() -> None:
    with pytest.raises(ErrorDeUnidad, match="mapeo"):
        PresetUsuario.desde_dict({"nombre": "x", "unidades": "no_es_un_mapeo"})


def test_desde_json_con_json_invalido_da_un_error_util() -> None:
    with pytest.raises(ErrorDeUnidad, match="JSON inválido"):
        PresetUsuario.desde_json("{ esto no es json")


def test_desde_json_con_raiz_que_no_es_objeto_da_un_error_util() -> None:
    with pytest.raises(ErrorDeUnidad, match="objeto"):
        PresetUsuario.desde_json("[1, 2, 3]")


def test_desde_dict_no_valida_contra_ningun_catalogo(cat: Catalogo) -> None:
    """Reconstruir desde disco no exige un catálogo a mano; el error solo
    aparece al llamar a `validar()` explícitamente."""
    preset = PresetUsuario.desde_dict({"nombre": "x", "unidades": {"presion": "bar"}})
    assert preset.unidades == {"presion": "bar"}
    with pytest.raises(ErrorDeUnidad, match="dimensión desconocida"):
        preset.validar(cat)


# --------------------------------------------------------------------------- #
# Encaje directo con resolver_unidad: gana al preset, pierde ante el canal
# --------------------------------------------------------------------------- #
def test_preset_de_usuario_como_preferencias_de_perfil_gana_al_preset_global(
    cat: Catalogo,
) -> None:
    mi_preset = crear_preset_usuario("Tuner USA", {"pressure": "psi"}, catalogo=cat)
    resuelta = resolver_unidad(
        "pressure",
        catalogo=cat,
        preset="metrico",  # metrico fija bar: si el preset de usuario no ganara, saldría bar
        preferencias_perfil=mi_preset.a_mapeo(),
    )
    assert resuelta.capa is Capa.PERFIL
    assert resuelta.unidad.id == "psi"


def test_anulacion_de_canal_gana_al_preset_de_usuario(cat: Catalogo) -> None:
    mi_preset = crear_preset_usuario("Tuner USA", {"pressure": "psi"}, catalogo=cat)
    resuelta = resolver_unidad(
        "pressure",
        catalogo=cat,
        preset="metrico",
        preferencias_perfil=mi_preset.a_mapeo(),
        anulacion_canal="bar",
    )
    assert resuelta.capa is Capa.CANAL
    assert resuelta.unidad.id == "bar"


def test_dimension_no_cubierta_por_el_preset_de_usuario_cae_al_preset_global(
    cat: Catalogo,
) -> None:
    """Igual que un perfil de verdad: si el preset de usuario no fija esta
    dimensión, la precedencia sigue bajando, no se rompe."""
    mi_preset = crear_preset_usuario("Solo presion", {"pressure": "psi"}, catalogo=cat)
    resuelta = resolver_unidad(
        "temperature",
        catalogo=cat,
        preset="metrico",
        preferencias_perfil=mi_preset.a_mapeo(),
    )
    assert resuelta.capa is Capa.PRESET
    assert resuelta.unidad.id == "degC"
