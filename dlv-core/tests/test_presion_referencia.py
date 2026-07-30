"""Pruebas de la presión de referencia absoluto -> relativo (tarea F1-15).

Dos cosas distintas que proteger:

1. La CASCADA de `docs/01-formato-log.md` §1.9 (usuario -> autodetección ->
   constante estimada) y, sobre todo, que `estimada` sea `True` exactamente
   cuando el valor NO se midió en este log: es lo que impide presentar como
   medido un boost que en realidad se supuso.
2. Que el cambio de origen sea **combinable con cualquier unidad** (el
   título de la tarea): la referencia se resta en kPa canónicos y la
   conversión a bar/psi viene después, así que la misma referencia da el
   mismo boost físico expresado en cualquier unidad de presión. Y que a un
   Δ (`Clase.INTERVALO`) no se le reste nada, que es la trampa del delta
   aplicada al cambio de origen.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dlv_core.presion_referencia import ModoReferencia, ReferenciaPresion, resolver_referencia
from dlv_core.unidades import Catalogo, Clase, cargar_catalogo, desde_canonica

RAIZ = Path(__file__).resolve().parents[2]
UNITS_TOML = RAIZ / "data" / "units.toml"


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with UNITS_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


def _resolver(catalogo: Catalogo, **kwargs: object) -> ReferenciaPresion:
    return resolver_referencia(
        constante_catalogo_kpa=catalogo.referencia_presion_por_omision_kpa,
        **kwargs,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# La cascada de §1.9
# --------------------------------------------------------------------------- #
def test_modo_ninguna_no_da_referencia_y_no_es_estimada(catalogo: Catalogo) -> None:
    """`None` aquí significa "no se quiere referencia" (presión absoluta), no
    "no se pudo calcular": por eso `estimada` es False."""
    r = _resolver(catalogo, modo=ModoReferencia.NINGUNA)
    assert r.kpa is None
    assert r.estimada is False
    assert r.aviso is None


def test_declarada_por_el_usuario_gana_y_no_es_estimada(catalogo: Catalogo) -> None:
    r = _resolver(catalogo, modo=ModoReferencia.AUTO, declarada_kpa=98.5)
    assert r.kpa == pytest.approx(98.5)
    assert r.estimada is False
    assert r.aviso is None


def test_declarada_gana_incluso_habiendo_datos_para_autodetectar(catalogo: Catalogo) -> None:
    """Opción 1 > opción 2 de §1.9: el propietario sabe más de su taller que
    cualquier inferencia sobre los datos."""
    presion = np.array([95.0, 95.0, 95.0, 250.0])
    regimen = np.array([0, 0, 0, 6000])

    r = _resolver(
        catalogo,
        modo=ModoReferencia.AUTO,
        declarada_kpa=98.5,
        presion_colector_kpa=presion,
        regimen_rpm=regimen,
    )
    assert r.kpa == pytest.approx(98.5)  # no 95.0
    assert r.estimada is False


def test_autodeteccion_toma_la_mediana_con_el_motor_parado(catalogo: Catalogo) -> None:
    presion = np.array([100.0, 101.0, 102.0, 250.0, 180.0])
    regimen = np.array([0, 0, 0, 6000, 3000])

    r = _resolver(
        catalogo,
        modo=ModoReferencia.AUTO,
        presion_colector_kpa=presion,
        regimen_rpm=regimen,
    )

    assert r.kpa == pytest.approx(101.0)  # mediana de [100, 101, 102], no de todo
    assert r.estimada is False  # se MIDIÓ en este log
    assert r.aviso is None


def test_sin_muestras_con_motor_parado_cae_a_la_constante_y_avisa(catalogo: Catalogo) -> None:
    """Un log que empieza con el motor ya en marcha: normal en banco, no un
    error. Cae a la constante, pero avisando y marcando estimada."""
    presion = np.array([250.0, 180.0, 220.0])
    regimen = np.array([6000, 3000, 5000])

    r = _resolver(
        catalogo,
        modo=ModoReferencia.AUTO,
        presion_colector_kpa=presion,
        regimen_rpm=regimen,
    )

    assert r.kpa == pytest.approx(catalogo.referencia_presion_por_omision_kpa)
    assert r.estimada is True
    assert r.aviso is not None
    assert r.aviso.codigo == "referencia_presion_sin_motor_parado"


def test_auto_sin_canales_cae_a_la_constante_estimada(catalogo: Catalogo) -> None:
    r = _resolver(catalogo, modo=ModoReferencia.AUTO)
    assert r.kpa == pytest.approx(101.325)
    assert r.estimada is True
    assert r.aviso is not None


def test_la_constante_sale_del_catalogo_no_del_codigo(catalogo: Catalogo) -> None:
    """Si alguien cambia `constante_por_omision_kPa` en data/units.toml, el
    resultado tiene que seguirlo: es un dato, no un número cableado."""
    r = resolver_referencia(modo=ModoReferencia.CONSTANTE, constante_catalogo_kpa=97.0)
    assert r.kpa == pytest.approx(97.0)
    assert r.estimada is True


def test_modo_canal_no_esta_implementado(catalogo: Catalogo) -> None:
    """Estos logs no traen canal barométrico (§1.9); el modo existe en el
    catálogo para formatos que sí."""
    with pytest.raises(NotImplementedError, match="barométrico"):
        _resolver(catalogo, modo=ModoReferencia.CANAL)


def test_arrays_de_distinta_forma_se_rechazan(catalogo: Catalogo) -> None:
    """Dos canales de grupos de muestreo distintos no tienen índices
    comparables: la máscara "motor parado" señalaría muestras equivocadas."""
    with pytest.raises(ValueError, match="misma forma"):
        _resolver(
            catalogo,
            modo=ModoReferencia.AUTO,
            presion_colector_kpa=np.array([100.0, 101.0]),
            regimen_rpm=np.array([0, 0, 0]),
        )


# --------------------------------------------------------------------------- #
# Combinable con cualquier unidad (el título de la tarea)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("unidad", "esperado"),
    [
        ("kPa", 100.0),  # 201,325 abs - 101,325 ref = 100 kPa de boost
        ("bar", 1.0),  # el mismo boost, en bar
        ("psi", 14.5038),  # el mismo boost, en psi
    ],
)
def test_la_misma_referencia_da_el_mismo_boost_en_cualquier_unidad(
    unidad: str, esperado: float, catalogo: Catalogo
) -> None:
    r = _resolver(catalogo, modo=ModoReferencia.AUTO)
    assert r.kpa is not None
    dim = catalogo.dimension("pressure")

    absoluta_kpa = 201.325  # 1 bar de boost sobre la atmósfera estándar
    relativa = desde_canonica(
        absoluta_kpa, dimension=dim, unidad=unidad, clase=Clase.PUNTO, referencia_kpa=r.kpa
    )

    assert relativa == pytest.approx(esperado, rel=1e-4)


def test_a_un_intervalo_no_se_le_resta_la_referencia(catalogo: Catalogo) -> None:
    """La trampa del delta aplicada al cambio de origen: un Δ de 50 kPa vale
    lo mismo en absoluto que en relativo."""
    r = _resolver(catalogo, modo=ModoReferencia.AUTO)
    assert r.kpa is not None
    dim = catalogo.dimension("pressure")

    delta = desde_canonica(
        50.0, dimension=dim, unidad="kPa", clase=Clase.INTERVALO, referencia_kpa=r.kpa
    )

    assert delta == pytest.approx(50.0)


def test_una_dimension_que_no_admite_referencia_se_rechaza(catalogo: Catalogo) -> None:
    """Solo `pressure` declara `admite_referencia` en data/units.toml: restar
    un origen a una temperatura no significa nada."""
    from dlv_core.unidades import ErrorDeUnidad

    dim_temp = catalogo.dimension("temperature")
    with pytest.raises(ErrorDeUnidad, match="referencia"):
        desde_canonica(
            300.0, dimension=dim_temp, unidad="degC", clase=Clase.PUNTO, referencia_kpa=101.325
        )
