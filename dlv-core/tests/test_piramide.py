"""Pruebas de la pirámide de decimación (tarea F1-09, docs/03 §3.5).

La propiedad que importa más que ninguna otra (§3.5): "es exacto en los
extremos, un pico de una sola muestra sigue visible al máximo zoom-out". Un
decimado por muestreo simple lo perdería; estas pruebas comprueban que
`min`/`max` de cada nivel son exactos frente a una referencia de NumPy
calculada de forma independiente (no reutilizando la lógica de producción),
no solo que "el código no revienta".
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from dlv_core.piramide import (
    NivelPiramide,
    TipoCanalPiramide,
    construir_piramide,
    elegir_nivel,
)


def _referencia(
    v: np.ndarray, factor: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Min/max/first/last "a mano", directamente sobre el array original, sin
    pasar por niveles intermedios: la referencia independiente contra la que
    se compara la construcción real (que sí decima nivel sobre nivel)."""
    n = (len(v) // factor) * factor
    b = v[:n].reshape(-1, factor)
    return b.min(axis=1), b.max(axis=1), b[:, 0], b[:, -1]


# --------------------------------------------------------------------------- #
# L0: no decima nada
# --------------------------------------------------------------------------- #
def test_l0_es_el_array_original_sin_decimar() -> None:
    v = np.arange(37, dtype=np.float32)
    (l0,) = construir_piramide(v, tipo=TipoCanalPiramide.CONTINUO)[:1]

    assert l0.factor == 1
    assert np.array_equal(l0.minimo, v)
    assert np.array_equal(l0.maximo, v)
    assert np.array_equal(l0.primero, v)
    assert np.array_equal(l0.ultimo, v)


# --------------------------------------------------------------------------- #
# Niveles: factor correcto y exactitud frente a una referencia independiente
# --------------------------------------------------------------------------- #
def test_los_factores_son_4_16_64_encadenados() -> None:
    v = np.random.default_rng(0).normal(size=5000).astype(np.float32)
    niveles = construir_piramide(v, tipo=TipoCanalPiramide.CONTINUO)

    factores = [n.factor for n in niveles]
    assert factores[:4] == [1, 4, 16, 64]
    # Cada factor es 4x el anterior hasta que se acaban los niveles.
    for anterior, siguiente in pairwise(factores):
        assert siguiente == anterior * 4


def test_min_max_first_last_son_exactos_en_l1_y_l2() -> None:
    rng = np.random.default_rng(42)
    v = rng.integers(-1000, 1000, size=10_000).astype(np.int32)
    niveles = construir_piramide(v, tipo=TipoCanalPiramide.CONTINUO)

    for nivel in niveles[1:3]:
        ref_min, ref_max, ref_first, ref_last = _referencia(v, nivel.factor)
        assert np.array_equal(nivel.minimo, ref_min)
        assert np.array_equal(nivel.maximo, ref_max)
        assert np.array_equal(nivel.primero, ref_first)
        assert np.array_equal(nivel.ultimo, ref_last)


def test_un_pico_de_una_sola_muestra_sigue_visible_en_el_ultimo_nivel() -> None:
    """La propiedad central de §3.5: un pico aislado no puede desaparecer al
    máximo zoom-out, ni en `minimo` ni en `maximo`."""
    v = np.zeros(20_000, dtype=np.float32)
    v[12_345] = 9999.0  # pico positivo aislado
    v[333] = -9999.0  # pico negativo aislado

    niveles = construir_piramide(v, tipo=TipoCanalPiramide.CONTINUO)
    ultimo = niveles[-1]

    assert ultimo.maximo.max() == pytest.approx(9999.0)
    assert ultimo.minimo.min() == pytest.approx(-9999.0)


# --------------------------------------------------------------------------- #
# Parada de la pirámide y casos límite
# --------------------------------------------------------------------------- #
def test_para_cuando_ya_no_hay_un_grupo_completo_que_decimar() -> None:
    v = np.arange(5_000_000, dtype=np.float32)
    niveles = construir_piramide(v, tipo=TipoCanalPiramide.CONTINUO)

    assert len(niveles[-1].minimo) < 4
    # El penúltimo nivel sí tenía un grupo completo (si no, no existiría).
    assert len(niveles[-2].minimo) >= 4


@pytest.mark.parametrize("n", [0, 1, 3])
def test_arrays_mas_cortos_que_el_factor_base_no_revientan(n: int) -> None:
    v = np.arange(n, dtype=np.float32)
    niveles = construir_piramide(v, tipo=TipoCanalPiramide.CONTINUO)

    assert len(niveles) == 1  # solo L0, no hay ni un grupo completo de 4
    assert len(niveles[0].minimo) == n


def test_factor_base_menor_que_2_es_un_error() -> None:
    with pytest.raises(ValueError, match="factor_base"):
        construir_piramide(
            np.arange(10, dtype=np.float32), tipo=TipoCanalPiramide.CONTINUO, factor_base=1
        )


@pytest.mark.parametrize(
    "tipo", [TipoCanalPiramide.CONTADOR, TipoCanalPiramide.ENUM, TipoCanalPiramide.BITS]
)
def test_variantes_no_continuas_no_estan_implementadas_todavia(tipo: TipoCanalPiramide) -> None:
    """Son F1-10 (suma de delta / moda de enum / OR de bits), no F1-09."""
    with pytest.raises(NotImplementedError):
        construir_piramide(np.arange(10, dtype=np.float32), tipo=tipo)


# --------------------------------------------------------------------------- #
# elegir_nivel
# --------------------------------------------------------------------------- #
def test_elegir_nivel_toma_el_mas_cercano_al_ancho_en_pixeles() -> None:
    v = np.arange(5_000_000, dtype=np.float32)
    niveles = construir_piramide(v, tipo=TipoCanalPiramide.CONTINUO)

    elegido = elegir_nivel(niveles, ancho_px=1800)

    # El elegido debe ser al menos tan cercano a 1800 cubos como cualquier otro.
    diferencia_elegido = abs(len(elegido.minimo) - 1800)
    for n in niveles:
        assert diferencia_elegido <= abs(len(n.minimo) - 1800)


def test_elegir_nivel_con_un_unico_nivel_lo_devuelve() -> None:
    l0 = NivelPiramide(
        factor=1,
        minimo=np.array([1.0]),
        maximo=np.array([1.0]),
        primero=np.array([1.0]),
        ultimo=np.array([1.0]),
    )
    assert elegir_nivel([l0], ancho_px=1800) is l0
