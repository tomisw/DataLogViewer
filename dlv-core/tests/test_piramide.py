"""Pruebas de la pirámide de decimación (tareas F1-09 y F1-10, docs/03 §3.5).

La propiedad que importa más que ninguna otra en `CONTINUO` (§3.5): "es
exacto en los extremos, un pico de una sola muestra sigue visible al máximo
zoom-out". Un decimado por muestreo simple lo perdería; estas pruebas
comprueban que `min`/`max` de cada nivel son exactos frente a una referencia
de NumPy calculada de forma independiente (no reutilizando la lógica de
producción), no solo que "el código no revienta". Las variantes de F1-10
(`CONTADOR`, `ENUM`, `BITS`) tienen la propiedad análoga: la suma de deltas y
el OR de bits son exactos y asociativos por construcción (igual que
min/max), así que se comprueban también contra una referencia independiente.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from dlv_core.piramide import (
    NivelBits,
    NivelContador,
    NivelEnum,
    NivelPiramide,
    TipoCanalPiramide,
    construir_piramide,
    construir_piramide_bits,
    construir_piramide_contador,
    construir_piramide_enum,
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


def test_construir_piramide_despacha_segun_tipo() -> None:
    v_continuo = np.arange(20, dtype=np.float32)
    v_bits = np.arange(20, dtype=np.uint32)

    assert isinstance(
        construir_piramide(v_continuo, tipo=TipoCanalPiramide.CONTINUO)[0], NivelPiramide
    )
    assert isinstance(
        construir_piramide(v_continuo, tipo=TipoCanalPiramide.CONTADOR)[0], NivelContador
    )
    assert isinstance(construir_piramide(v_continuo, tipo=TipoCanalPiramide.ENUM)[0], NivelEnum)
    assert isinstance(construir_piramide(v_bits, tipo=TipoCanalPiramide.BITS)[0], NivelBits)


# --------------------------------------------------------------------------- #
# CONTADOR: suma del delta
# --------------------------------------------------------------------------- #
def test_contador_suma_delta_es_exacta_frente_a_referencia_independiente() -> None:
    rng = np.random.default_rng(1)
    incrementos = rng.integers(0, 5, size=10_000).astype(np.int64)
    v = np.cumsum(incrementos).astype(np.uint32)  # contador monótono creciente

    niveles = construir_piramide_contador(v)

    for nivel in niveles[1:3]:
        factor = nivel.factor
        n = (len(v) // factor) * factor
        # Referencia: suma total de incrementos dentro de cada bloque de
        # `factor` muestras, calculada directamente sobre el array original.
        deltas_originales = np.diff(v[:n].astype(np.int64), prepend=v[:1].astype(np.int64))
        ref_suma = deltas_originales.reshape(-1, factor).sum(axis=1)
        assert np.array_equal(nivel.suma_delta, ref_suma)


def test_contador_un_incremento_aislado_no_se_pierde_en_el_ultimo_nivel() -> None:
    v = np.zeros(20_000, dtype=np.uint32)
    v[5000:] = 1  # un único incremento de +1 en toda la serie, el resto plano

    niveles = construir_piramide_contador(v)

    assert niveles[-1].suma_delta.sum() == 1


def test_contador_uint32_no_envuelve_en_un_delta_negativo() -> None:
    """`v` es uint32: si el `diff` no castea a un tipo con signo antes de
    restar, un descenso (aquí no lo hay, pero el cast tiene que existir para
    cuando SÍ lo haya) envolvería a un entero gigantesco en vez de dar un
    número negativo pequeño."""
    v = np.array([10, 10, 10], dtype=np.uint32)
    (l0,) = construir_piramide_contador(v)[:1]
    assert l0.suma_delta.tolist() == [0, 0, 0]
    assert l0.suma_delta.dtype == np.int64


# --------------------------------------------------------------------------- #
# ENUM: moda + marca de transición
# --------------------------------------------------------------------------- #
def test_enum_moda_es_el_valor_mas_frecuente_del_cubo() -> None:
    v = np.array([1, 1, 1, 2] * 100, dtype=np.int32)  # moda = 1 en cada cubo de 4
    (_l0, l1) = construir_piramide_enum(v)[:2]
    assert l1.factor == 4
    assert (l1.moda == 1).all()


def test_enum_marca_transicion_cuando_el_cubo_no_es_uniforme() -> None:
    v = np.array([5, 5, 5, 5] * 50 + [1, 2, 3, 4] * 50, dtype=np.int32)
    niveles = construir_piramide_enum(v)
    l1 = niveles[1]

    assert not l1.hubo_transicion[:50].any()  # cubos uniformes de 5
    assert l1.hubo_transicion[50:].all()  # cubos con 4 valores distintos


def test_enum_transicion_se_propaga_con_or_aunque_la_moda_no_cambie() -> None:
    """Un cambio real en L0 no debe desaparecer en niveles altos solo porque
    la moda del nivel siguiente vuelva a ser uniforme."""
    v = np.array([7, 7, 7, 9] + [7] * 9996, dtype=np.int32)  # un único "9" al principio
    niveles = construir_piramide_enum(v)
    assert niveles[-1].hubo_transicion.any()


# --------------------------------------------------------------------------- #
# BITS: OR de bits
# --------------------------------------------------------------------------- #
def test_bits_or_es_exacto_frente_a_referencia_independiente() -> None:
    rng = np.random.default_rng(2)
    v = rng.integers(0, 2**16, size=10_000, dtype=np.uint32)

    niveles = construir_piramide_bits(v)

    for nivel in niveles[1:3]:
        factor = nivel.factor
        n = (len(v) // factor) * factor
        ref = np.bitwise_or.reduce(v[:n].reshape(-1, factor), axis=1)
        assert np.array_equal(nivel.or_bits, ref)


def test_bits_un_bit_activado_una_vez_sigue_visible_en_el_ultimo_nivel() -> None:
    v = np.zeros(20_000, dtype=np.uint32)
    v[9999] = 1 << 5  # un único bit, una única muestra, en medio de la serie

    niveles = construir_piramide_bits(v)

    assert (niveles[-1].or_bits & (1 << 5)).any()


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
