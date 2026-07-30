"""Pruebas de las dimensiones compuestas derivadas (tarea F1-16, docs/06 §6.7).

El fallo que más importa evitar aquí es el de la aritmética invertida:
`a_num * a_den` en vez de `a_num / a_den` da un número con la forma correcta
y la magnitud equivocada por un factor de ~14,5 en `%/psi`, y nada en la
interfaz lo delataría. Por eso los casos se comprueban contra el valor
físico razonado, no contra lo que devuelva la implementación:

    1 psi = 6,894757 kPa, así que una pendiente de 100 %/kPa es 689,48 %/psi
    (por cada psi de presión hay 6,894757 veces más cambio que por cada kPa).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dlv_core.compuestas import Compuesta, cargar_compuestas, derivar_unidad_compuesta
from dlv_core.unidades import Catalogo, ErrorDeUnidad, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
UNITS_TOML = RAIZ / "data" / "units.toml"


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with UNITS_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


@pytest.fixture(scope="module")
def compuestas() -> dict[str, Compuesta]:
    with UNITS_TOML.open("rb") as fh:
        return dict(cargar_compuestas(fh))


# --------------------------------------------------------------------------- #
# Carga desde el catálogo real
# --------------------------------------------------------------------------- #
def test_se_cargan_las_tres_compuestas_del_catalogo(compuestas: dict[str, Compuesta]) -> None:
    """Las tres de docs/06 §6.7: PercentPerRpm, PercentPerKPa, PercentPerLambda."""
    assert set(compuestas) == {"pct_per_rpm", "pct_per_kPa", "pct_per_lambda"}
    assert compuestas["pct_per_kPa"].numerador == "ratio"
    assert compuestas["pct_per_kPa"].denominador == "pressure"


# --------------------------------------------------------------------------- #
# La derivación: %/kPa -> %/psi, el ejemplo del título de la tarea
# --------------------------------------------------------------------------- #
def test_la_etiqueta_se_deriva_de_las_unidades_activas(
    compuestas: dict[str, Compuesta], catalogo: Catalogo
) -> None:
    c = compuestas["pct_per_kPa"]

    en_kpa = derivar_unidad_compuesta(
        c, catalogo=catalogo, unidad_numerador="pct", unidad_denominador="kPa"
    )
    en_psi = derivar_unidad_compuesta(
        c, catalogo=catalogo, unidad_numerador="pct", unidad_denominador="psi"
    )

    assert en_kpa.etiqueta == "%/kPa"
    assert en_psi.etiqueta == "%/psi"


@pytest.mark.parametrize(
    ("unidad_den", "factor_esperado"),
    [
        # 1 fracción/kPa = 100 %/kPa.
        ("kPa", 100.0),
        # 1 psi = 6,894757 kPa: por cada psi hay 6,894757 veces más cambio.
        ("psi", 100.0 * 6.894757),
        # 1 bar = 100 kPa.
        ("bar", 100.0 * 100.0),
    ],
)
def test_el_factor_es_a_num_partido_por_a_den(
    unidad_den: str,
    factor_esperado: float,
    compuestas: dict[str, Compuesta],
    catalogo: Catalogo,
) -> None:
    """Contra el valor físico razonado, no contra la implementación: si
    alguien multiplica donde hay que dividir, esto lo detecta."""
    u = derivar_unidad_compuesta(
        compuestas["pct_per_kPa"],
        catalogo=catalogo,
        unidad_numerador="pct",
        unidad_denominador=unidad_den,
    )
    assert u.factor == pytest.approx(factor_esperado, rel=1e-6)


def test_una_pendiente_en_psi_es_mayor_que_la_misma_en_kpa(
    compuestas: dict[str, Compuesta], catalogo: Catalogo
) -> None:
    """Comprobación de SENTIDO, no solo de número: como 1 psi es más presión
    que 1 kPa, la misma pendiente física expresada "por psi" tiene que dar un
    número MAYOR. Es lo que detecta una división invertida aunque el factor
    concreto cambiara."""
    c = compuestas["pct_per_kPa"]
    en_kpa = derivar_unidad_compuesta(
        c, catalogo=catalogo, unidad_numerador="pct", unidad_denominador="kPa"
    )
    en_psi = derivar_unidad_compuesta(
        c, catalogo=catalogo, unidad_numerador="pct", unidad_denominador="psi"
    )

    assert en_psi.factor > en_kpa.factor


def test_ida_y_vuelta_es_la_identidad(compuestas: dict[str, Compuesta], catalogo: Catalogo) -> None:
    u = derivar_unidad_compuesta(
        compuestas["pct_per_kPa"],
        catalogo=catalogo,
        unidad_numerador="pct",
        unidad_denominador="psi",
    )
    canonico = 0.037
    assert u.a_canonica(u.desde_canonica(canonico)) == pytest.approx(canonico)


def test_es_vectorizado_sobre_un_array(
    compuestas: dict[str, Compuesta], catalogo: Catalogo
) -> None:
    """ADR-009: la misma aritmética escalar vale para un `ndarray` completo."""
    u = derivar_unidad_compuesta(
        compuestas["pct_per_kPa"],
        catalogo=catalogo,
        unidad_numerador="pct",
        unidad_denominador="kPa",
    )
    valores = np.array([0.01, 0.02, 0.03])

    mostrados = u.desde_canonica(valores)

    assert isinstance(mostrados, np.ndarray)
    assert np.allclose(mostrados, [1.0, 2.0, 3.0])


def test_pct_per_rpm_usa_el_denominador_de_regimen(
    compuestas: dict[str, Compuesta], catalogo: Catalogo
) -> None:
    u = derivar_unidad_compuesta(
        compuestas["pct_per_rpm"],
        catalogo=catalogo,
        unidad_numerador="pct",
        unidad_denominador="rpm",
    )
    assert "rpm" in u.etiqueta
    assert u.unidad_denominador == "rpm"


# --------------------------------------------------------------------------- #
# Lo que NO se puede derivar
# --------------------------------------------------------------------------- #
def test_un_denominador_reciproco_se_rechaza_en_vez_de_dar_un_numero_plausible(
    compuestas: dict[str, Compuesta], catalogo: Catalogo
) -> None:
    """λ -> φ es recíproca (1/λ): "por φ" no es la pendiente escalada, es otra
    función. Devolver un factor constante aquí sería inventar."""
    with pytest.raises(ErrorDeUnidad, match=r"no afín|no es un factor constante"):
        derivar_unidad_compuesta(
            compuestas["pct_per_lambda"],
            catalogo=catalogo,
            unidad_numerador="pct",
            unidad_denominador="phi",
        )


def test_pct_per_lambda_si_se_deriva_con_lambda_de_denominador(
    compuestas: dict[str, Compuesta], catalogo: Catalogo
) -> None:
    """El caso que sí es afín: λ consigo misma."""
    u = derivar_unidad_compuesta(
        compuestas["pct_per_lambda"],
        catalogo=catalogo,
        unidad_numerador="pct",
        unidad_denominador="lambda",
    )
    assert u.factor == pytest.approx(100.0)


def test_una_unidad_inexistente_da_el_error_del_motor_de_unidades(
    compuestas: dict[str, Compuesta], catalogo: Catalogo
) -> None:
    with pytest.raises(ErrorDeUnidad):
        derivar_unidad_compuesta(
            compuestas["pct_per_kPa"],
            catalogo=catalogo,
            unidad_numerador="pct",
            unidad_denominador="no_existe",
        )
