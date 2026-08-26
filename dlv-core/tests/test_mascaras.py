"""Pruebas de `dlv_core.mascaras` (F3-14).

Como en `test_piramide.py`, la propiedad que importa es que el desempaquetado
sea EXACTO frente a una referencia independiente (aquí, `bin()`/desplazamiento
a mano sobre enteros de Python, no reutilizando `decodificar_bits`), y que un
bit activado una sola vez entre miles de muestras no se pierda ni se
confunda con otro bit.
"""

from __future__ import annotations

import numpy as np
import pytest

from dlv_core.mascaras import (
    BitDecodificado,
    ancho_de_bits,
    decodificar_bits,
    decodificar_mascara,
)


def _bit_de_referencia(valores: np.ndarray, bit: int) -> np.ndarray:
    """Referencia independiente: Python puro sobre enteros, no NumPy vectorizado."""
    return np.array([(int(v) >> bit) & 1 for v in valores], dtype=np.uint8)


def test_decodificar_bits_extrae_cada_bit_de_forma_independiente() -> None:
    rng = np.random.default_rng(7)
    v = rng.integers(0, 2**16, size=5_000, dtype=np.uint32)

    bits = decodificar_bits(v, n_bits=16)

    assert bits.shape == (16, 5_000)
    for i in range(16):
        assert np.array_equal(bits[i], _bit_de_referencia(v, i))


def test_decodificar_bits_bit_menos_significativo_y_mas_significativo() -> None:
    v = np.array([0b0001, 0b1000, 0b1001, 0b0000], dtype=np.uint32)
    bits = decodificar_bits(v, n_bits=4)

    assert np.array_equal(bits[0], [1, 0, 1, 0])  # bit 0
    assert np.array_equal(bits[3], [0, 1, 1, 0])  # bit 3


def test_decodificar_bits_un_bit_activado_una_sola_vez_no_se_pierde() -> None:
    v = np.zeros(20_000, dtype=np.uint32)
    v[12345] = 1 << 5  # una única muestra, un único bit, en medio de la serie

    bits = decodificar_bits(v, n_bits=6)

    assert bits[5].sum() == 1
    assert bits[5][12345] == 1
    # Los demás bits nunca se activan: no se contamina un bit con otro.
    for i in range(6):
        if i != 5:
            assert bits[i].sum() == 0


def test_decodificar_bits_no_confunde_bits_vecinos() -> None:
    # Un valor con varios bits a la vez: cada fila debe leer SOLO su propio bit.
    v = np.array([0b0110_1101], dtype=np.uint32)  # bits 0,2,3,5,6 a 1
    bits = decodificar_bits(v, n_bits=8)
    esperado = [1, 0, 1, 1, 0, 1, 1, 0]
    for i, valor_esperado in enumerate(esperado):
        assert bits[i][0] == valor_esperado


def test_decodificar_bits_rechaza_n_bits_invalido() -> None:
    v = np.zeros(10, dtype=np.uint32)
    with pytest.raises(ValueError):
        decodificar_bits(v, n_bits=0)
    with pytest.raises(ValueError):
        decodificar_bits(v, n_bits=65)


def test_decodificar_mascara_conserva_la_anchura_completa_aunque_un_bit_nunca_se_active() -> None:
    # Decisión 2 del informe de F3-14: un bit siempre a 0 sigue declarado,
    # no desaparece de la lista -- solo se marca `activo=False`.
    v = np.zeros(1_000, dtype=np.uint32)
    v[:] = 0b1  # solo el bit 0 se activa, en TODAS las muestras

    resultado = decodificar_mascara(v, n_bits=5)

    assert len(resultado) == 5
    assert [b.indice for b in resultado] == [0, 1, 2, 3, 4]
    assert resultado[0].activo is True
    for b in resultado[1:]:
        assert b.activo is False
        assert b.valores.sum() == 0


def test_decodificar_mascara_activo_es_true_con_un_pulso_de_una_sola_muestra() -> None:
    v = np.zeros(50_000, dtype=np.uint32)
    v[30_000] = 1 << 10

    resultado = decodificar_mascara(v, n_bits=16)

    bit_10 = next(b for b in resultado if b.indice == 10)
    assert bit_10.activo is True
    assert bit_10.valores.sum() == 1


def test_decodificar_mascara_devuelve_bitdecodificado() -> None:
    v = np.array([1, 0, 1], dtype=np.uint32)
    resultado = decodificar_mascara(v, n_bits=2)
    assert all(isinstance(b, BitDecodificado) for b in resultado)


# --------------------------------------------------------------------------- #
# ancho_de_bits
# --------------------------------------------------------------------------- #
def test_ancho_de_bits_deriva_las_dos_mascaras_conocidas_del_formato() -> None:
    # docs/01-formato-log.md §1.10: Trigger System Errors 0..31 (5 bits),
    # Engine Protection Cause 0..65535 (16 bits). No se copian estos números
    # al código de producción -- aquí solo se comprueba la DERIVACIÓN.
    assert ancho_de_bits(31) == 5
    assert ancho_de_bits(65535) == 16


def test_ancho_de_bits_potencias_de_dos_menos_uno() -> None:
    assert ancho_de_bits(1) == 1
    assert ancho_de_bits(3) == 2
    assert ancho_de_bits(7) == 3
    assert ancho_de_bits(255) == 8


def test_ancho_de_bits_rechaza_un_maximo_que_no_es_2n_menos_1() -> None:
    with pytest.raises(ValueError):
        ancho_de_bits(30)  # 31 sí, 30 no: no hay anchura limpia que derivar
    with pytest.raises(ValueError):
        ancho_de_bits(100)


def test_ancho_de_bits_rechaza_maximo_no_positivo() -> None:
    with pytest.raises(ValueError):
        ancho_de_bits(0)
