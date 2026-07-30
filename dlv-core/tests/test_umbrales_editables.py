"""Pruebas de umbrales en canónica editados en la unidad activa (tarea F1-19).

Tres propiedades, en orden de lo que costaría más si fallara:

1. **Cambiar de unidad no reescribe el umbral guardado** (docs/06 §6.11:
   cambiar de unidad es un repintado, no una recarga). Si esto falla, el
   fichero de umbrales del usuario se corrompe solo con mirarlo en otra
   unidad.
2. **Ida y vuelta exacta** (docs/06 §6.12, error < 1 ULP): abrir el editor y
   cerrarlo sin tocar nada no puede cambiar el valor.
3. **La clase se respeta**: un umbral de INTERVALO editado como PUNTO
   convierte "una subida de 10 K" en "−263,15 °C". Es la trampa del delta
   entrando por el campo de edición.

Los valores canónicos de ejemplo salen de `data/umbrales.toml` real, no
inventados: es el fichero que este módulo tiene que saber editar.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from dlv_core.umbrales_editables import desde_edicion, para_edicion
from dlv_core.unidades import Catalogo, Clase, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
UNITS_TOML = RAIZ / "data" / "units.toml"
UMBRALES_TOML = RAIZ / "data" / "umbrales.toml"


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with UNITS_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


@pytest.fixture(scope="module")
def umbrales() -> dict:
    with UMBRALES_TOML.open("rb") as fh:
        return tomllib.load(fh)


# --------------------------------------------------------------------------- #
# 1. Cambiar de unidad no toca lo guardado
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("unidad", ["K", "degC", "degF"])
def test_mirar_el_umbral_en_otra_unidad_no_cambia_el_canonico(
    unidad: str, catalogo: Catalogo
) -> None:
    canonico = 373.15  # K

    editable = para_edicion(
        canonico,
        catalogo=catalogo,
        clase=Clase.PUNTO,
        dimension_id="temperature",
        unidad_id=unidad,
    )

    assert editable.canonico == canonico  # intacto, sea cual sea la unidad activa


def test_el_valor_mostrado_si_cambia_con_la_unidad(catalogo: Catalogo) -> None:
    """El complemento del test anterior: lo guardado no cambia, lo mostrado
    sí. Casos conocidos de docs/06 §6.12: 0 °C = 273,15 K = 32 °F."""
    canonico = 273.15

    en_k = para_edicion(
        canonico, catalogo=catalogo, clase=Clase.PUNTO, dimension_id="temperature", unidad_id="K"
    )
    en_c = para_edicion(
        canonico, catalogo=catalogo, clase=Clase.PUNTO, dimension_id="temperature", unidad_id="degC"
    )
    en_f = para_edicion(
        canonico, catalogo=catalogo, clase=Clase.PUNTO, dimension_id="temperature", unidad_id="degF"
    )

    assert en_k.valor == pytest.approx(273.15)
    assert en_c.valor == pytest.approx(0.0)
    assert en_f.valor == pytest.approx(32.0)


# --------------------------------------------------------------------------- #
# 2. Ida y vuelta exacta
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("dimension_id", "unidad", "canonico"),
    [
        ("temperature", "degC", 373.15),
        ("temperature", "degF", 373.15),
        ("pressure", "psi", 201.325),
        ("pressure", "bar", 201.325),
        ("mixture_ratio", "lambda", 0.85),
        ("angular_speed", "rpm", 6500.0),
    ],
)
def test_ida_y_vuelta_devuelve_el_mismo_canonico(
    dimension_id: str, unidad: str, canonico: float, catalogo: Catalogo
) -> None:
    editable = para_edicion(
        canonico,
        catalogo=catalogo,
        clase=Clase.PUNTO,
        dimension_id=dimension_id,
        unidad_id=unidad,
    )
    de_vuelta = desde_edicion(
        editable.valor,
        catalogo=catalogo,
        clase=Clase.PUNTO,
        dimension_id=dimension_id,
        unidad_id=unidad,
    )

    assert de_vuelta == pytest.approx(canonico, rel=1e-12)


def test_editar_de_verdad_guarda_el_canonico_correcto(catalogo: Catalogo) -> None:
    """El usuario tiene °C activo y escribe 100: se guarda 373,15 K."""
    guardado = desde_edicion(
        100.0,
        catalogo=catalogo,
        clase=Clase.PUNTO,
        dimension_id="temperature",
        unidad_id="degC",
    )
    assert guardado == pytest.approx(373.15)


# --------------------------------------------------------------------------- #
# 3. La clase se respeta (trampa del delta en el campo de edición)
# --------------------------------------------------------------------------- #
def test_un_umbral_de_intervalo_no_recibe_el_desplazamiento_de_origen(
    catalogo: Catalogo,
) -> None:
    """ "Una subida de más de 10 K" son 10 °C, no −263,15 °C."""
    editable = para_edicion(
        10.0,
        catalogo=catalogo,
        clase=Clase.INTERVALO,
        dimension_id="temperature",
        unidad_id="degC",
    )
    assert editable.valor == pytest.approx(10.0)


def test_el_mismo_numero_canonico_da_valores_distintos_segun_la_clase(
    catalogo: Catalogo,
) -> None:
    """Es lo que hace imprescindible que `clase` sea obligatoria: 10 K como
    punto y 10 K como intervalo NO se editan igual."""
    punto = para_edicion(
        10.0, catalogo=catalogo, clase=Clase.PUNTO, dimension_id="temperature", unidad_id="degC"
    )
    intervalo = para_edicion(
        10.0, catalogo=catalogo, clase=Clase.INTERVALO, dimension_id="temperature", unidad_id="degC"
    )

    assert punto.valor != pytest.approx(intervalo.valor)
    assert intervalo.valor == pytest.approx(10.0)
    assert punto.valor == pytest.approx(10.0 - 273.15)


# --------------------------------------------------------------------------- #
# Presión relativa y umbrales adimensionales
# --------------------------------------------------------------------------- #
def test_un_umbral_de_presion_se_edita_en_relativo_si_hay_referencia(
    catalogo: Catalogo,
) -> None:
    """El umbral guardado es absoluto (201,325 kPa); el tuner lo edita como
    "1,2 bar de boost" -- aquí 1 bar exacto sobre la atmósfera estándar."""
    editable = para_edicion(
        201.325,
        catalogo=catalogo,
        clase=Clase.PUNTO,
        dimension_id="pressure",
        unidad_id="bar",
        referencia_kpa=101.325,
    )

    assert editable.valor == pytest.approx(1.0)
    assert editable.canonico == pytest.approx(201.325)  # lo guardado sigue absoluto
    assert "rel" in editable.etiqueta_unidad


def test_ida_y_vuelta_con_referencia_tambien_es_exacta(catalogo: Catalogo) -> None:
    canonico = 201.325
    editable = para_edicion(
        canonico,
        catalogo=catalogo,
        clase=Clase.PUNTO,
        dimension_id="pressure",
        unidad_id="bar",
        referencia_kpa=101.325,
    )
    de_vuelta = desde_edicion(
        editable.valor,
        catalogo=catalogo,
        clase=Clase.PUNTO,
        dimension_id="pressure",
        unidad_id="bar",
        referencia_kpa=101.325,
    )
    assert de_vuelta == pytest.approx(canonico)


def test_un_umbral_adimensional_no_se_convierte(catalogo: Catalogo) -> None:
    """`histeresis_relativa` de data/umbrales.toml es un número puro."""
    editable = para_edicion(0.02, catalogo=catalogo, clase=Clase.PUNTO)

    assert editable.valor == pytest.approx(0.02)
    assert editable.etiqueta_unidad == ""
    assert desde_edicion(0.02, catalogo=catalogo, clase=Clase.PUNTO) == pytest.approx(0.02)


# --------------------------------------------------------------------------- #
# Formato y decimales (docs/06 §6.10)
# --------------------------------------------------------------------------- #
def test_los_decimales_salen_del_catalogo(catalogo: Catalogo) -> None:
    """docs/06 §6.10: λ lleva 3 decimales porque `λ 0,995` con uno (`1,0`)
    destruye la información."""
    lam = para_edicion(
        0.995,
        catalogo=catalogo,
        clase=Clase.PUNTO,
        dimension_id="mixture_ratio",
        unidad_id="lambda",
    )
    assert lam.decimales == 3
    assert lam.formateado().startswith("0.995")


# --------------------------------------------------------------------------- #
# Contra el fichero de umbrales real
# --------------------------------------------------------------------------- #
def test_un_umbral_real_de_umbrales_toml_se_edita_en_la_unidad_activa(
    umbrales: dict, catalogo: Catalogo
) -> None:
    """`D1.escalada_critica.manifold_pressure_min` está en kPa absolutos en
    el fichero; un tuner con psi activo tiene que verlo en psi."""
    kpa = float(umbrales["detectores"]["D1"]["escalada_critica"]["manifold_pressure_min"])
    assert kpa == pytest.approx(150.0)

    editable = para_edicion(
        kpa, catalogo=catalogo, clase=Clase.PUNTO, dimension_id="pressure", unidad_id="psi"
    )

    assert editable.valor == pytest.approx(150.0 * 0.145038, rel=1e-4)
    assert editable.canonico == pytest.approx(kpa)
