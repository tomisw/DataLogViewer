"""Decodificación de canales `bitmask` en señales por bit (F3-14).

Contexto: `data/enums.toml` declara dos canales con `clase = "bitmask"`
(`Trigger System Errors`, 0…31 = 5 bits; `Engine Protection Cause`, 0…65535 =
16 bits) pero DEJA SUS CÓDIGOS SIN TRADUCIR a propósito -- la asignación
bit -> significado exige documentación del fabricante que no hay todavía
(tarea F3-15, bloqueada). Este módulo decodifica la ESTRUCTURA del valor
entero (qué bit vale qué, en qué instante) y nada de su significado: la salida
se identifica por ÍNDICE de bit (0 = menos significativo), nunca por un nombre
inventado. Quien pinte esto (`dlv-ui/src/carriles/mascara-bits.ts`) hereda la
misma regla.

Por qué no vive en `piramide.py`: `NivelBits` (F1-10, ya cerrada) construye la
pirámide de UN valor de máscara -- el OR de bits del cubo, todavía empaquetado
en un entero -- y esa tarea sigue intacta aquí, sin tocarla. Lo que falta y
aporta este módulo es el paso siguiente: desempaquetar ESE entero (venga del
canal en bruto o ya de un nivel de la pirámide, es la misma operación) en una
señal 0/1 por bit, que es lo que un carril apilado necesita para dibujar cada
bit como su propia línea de tiempo.

ADR-009: el desempaquetado es enteramente vectorizado con NumPy
(desplazamiento + máscara, `>>`/`&`) sobre el array COMPLETO de cada bit. El
único bucle de Python que hay recorre `n_bits` (como mucho 32, típicamente 5 o
16), nunca las muestras -- misma categoría de bucle acotado que
`piramide._moda_por_fila`, que recorre `factor` y no los cubos.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True, frozen=True)
class BitDecodificado:
    """Un bit ya desempaquetado de una máscara, listo para un carril.

    `indice` es la POSICIÓN del bit (0 = menos significativo), no su
    significado -- eso es F3-15 y sigue bloqueada. `activo` decide si el
    carril de este bit se muestra por omisión (mismo criterio que
    `IndiceCanal.constante`/`vacio` en el selector de canales, F1-33): un bit
    que nunca se puso a 1 en todo el rango decodificado es ruido visual si se
    dibuja siempre, pero SIGUE EXISTIENDO -- la anchura de la máscara no
    cambia porque un bit esté siempre a cero, así que quien consuma esta lista
    conserva los `n_bits` elementos completos y decide la visibilidad con
    `activo`, nunca recortando la lista.
    """

    indice: int
    valores: np.ndarray
    """`uint8`, 0/1, una entrada por muestra de `valores` de entrada, en el mismo orden."""
    activo: bool
    """`True` si el bit estuvo a 1 en AL MENOS una muestra del rango decodificado."""


def decodificar_bits(valores: np.ndarray, *, n_bits: int) -> np.ndarray:
    """Desempaqueta cada uno de los `n_bits` bits menos significativos de `valores`.

    Devuelve un array `(n_bits, len(valores))` de `uint8` (0/1): la fila `i`
    es el bit `i` (menos significativo = 0) de cada elemento de `valores`.

    Vectorizado por completo sobre `valores` (ADR-009): `>>`/`&` son
    operaciones de NumPy sobre el array entero, no por elemento. El `for` es
    sobre `range(n_bits)` -- acotado a 32 como mucho por la anchura máxima de
    una máscara de 32 bits del propio formato (`docs/01` §1.10), nunca sobre
    las muestras.

    `valores` se trata como enteros sin signo (`uint64` internamente, para no
    interpretar el bit más alto como signo si `valores` llegase como `int32`
    con el bit 31 puesto): una máscara de bits no tiene signo, es un conjunto
    de banderas.
    """
    if n_bits < 1:
        raise ValueError(f"n_bits tiene que ser >= 1, se dio {n_bits}")
    if n_bits > 64:
        raise ValueError(
            f"n_bits tiene que ser <= 64 (máscara empaquetada en un entero), se dio {n_bits}"
        )
    v64 = valores.astype(np.uint64, copy=False)
    return np.stack(
        [((v64 >> np.uint64(bit)) & np.uint64(1)).astype(np.uint8) for bit in range(n_bits)]
    )


def decodificar_mascara(valores: np.ndarray, *, n_bits: int) -> list[BitDecodificado]:
    """`decodificar_bits` + la bandera `activo` de cada bit, en un `BitDecodificado` por bit.

    Los `n_bits` elementos de la lista de salida están SIEMPRE presentes, en
    orden de índice, tanto si el bit se activó como si no -- ver el docstring
    de `BitDecodificado.activo`: la anchura declarada de la máscara no se
    recorta aquí, solo se marca qué bits no tuvieron actividad para que quien
    pinte decida si los oculta por omisión.
    """
    bits = decodificar_bits(valores, n_bits=n_bits)
    return [
        BitDecodificado(indice=i, valores=bits[i], activo=bool(bits[i].any()))
        for i in range(n_bits)
    ]


def ancho_de_bits(maximo: int) -> int:
    """Anchura en bits de una máscara declarada por su valor máximo posible.

    `data/enums.toml` da el máximo observado/declarado del canal (`rango.max`:
    31 para `Trigger System Errors`, 65535 para `Engine Protection Cause`), no
    la anchura en bits directamente -- este cálculo es la derivación, no un
    número trasladado del TOML al código (regla 2 de `CLAUDE.md`).

    Asume que `maximo` es exactamente `2**n - 1` (todos los bits hasta `n-1`
    posibles): es lo que declaran las dos máscaras conocidas del formato
    (31 = 2**5 - 1, 65535 = 2**16 - 1) y lo que tiene sentido para "estos son
    los bits que caben en el campo". Si algún día `rango.max` de un canal
    `bitmask` no cumpliera esa forma, es una señal de que el rango declarado
    no es una anchura de bits limpia y hay que mirarlo a mano -- por eso esto
    LANZA en vez de adivinar una anchura con `.bit_length()` a secas, que
    daría un número plausible y silenciosamente incorrecto.
    """
    if maximo < 1:
        raise ValueError(f"maximo tiene que ser >= 1, se dio {maximo}")
    if (maximo + 1) & maximo != 0:
        raise ValueError(
            f"maximo={maximo} no es de la forma 2**n - 1: no se puede derivar una "
            "anchura de bits limpia sin adivinar. Compruébalo a mano contra "
            "data/enums.toml antes de forzar un valor."
        )
    return (maximo + 1).bit_length() - 1
