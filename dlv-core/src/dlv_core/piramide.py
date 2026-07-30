"""Pirámide de decimación (§3.5 de `docs/03-arquitectura.md`).

Regla de disciplina de rendimiento (ADR-009, la misma que en `almacen.py`):

    Ninguna ruta que se ejecute una vez por muestra puede estar escrita en
    Python interpretado. Todo cálculo sobre series es una operación de NumPy
    o Polars sobre el array completo: `for` sobre muestras, `.apply()`,
    `.iterrows()` y `map()` por elemento están prohibidos en `dlv-core`. Lo
    que no se puede vectorizar (decimación por moda con longitud de racha,
    OR de máscara de bits, suma de delta con racha) se implementa en Numba
    `@njit`, no en Python puro; el banco de rendimiento de F0 decide cuándo
    hace falta (§3.5, última línea).

Niveles con factor 4, cada cubo con `min, max, first, last` (variante
`continuo`); las variantes `contador`, `enum` y `bits` de §3.5 se añaden junto
con Numba cuando el banco lo confirme.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import numpy as np


class TipoCanalPiramide(Enum):
    """Variante de agregación del cubo, según el tipo de canal (§3.5)."""

    CONTINUO = auto()  # min, max, first, last — preserva picos
    CONTADOR = auto()  # suma del delta — un incremento aislado no se pierde
    ENUM = auto()  # moda + marca de transiciones — evita parpadeo
    BITS = auto()  # OR de los bits — un bit activado una vez sigue visible


@dataclass(slots=True, frozen=True)
class NivelPiramide:
    """Un nivel de la pirámide: factor de decimación y los cuatro arrays del cubo."""

    factor: int
    minimo: np.ndarray
    maximo: np.ndarray
    primero: np.ndarray
    ultimo: np.ndarray


def _nivel_l0(valores: np.ndarray) -> NivelPiramide:
    """L0 no decima nada: min = max = first = last = el propio valor. Así
    `elegir_nivel` no necesita un caso especial para "sin decimar"."""
    return NivelPiramide(factor=1, minimo=valores, maximo=valores, primero=valores, ultimo=valores)


def _siguiente_nivel_continuo(anterior: NivelPiramide, *, factor_base: int) -> NivelPiramide:
    """Un nivel a partir del anterior (§3.5): `reshape` + `min/max(axis=1)`.

    Decima sobre los cubos `min`/`max` del nivel anterior, no sobre los datos
    originales: agregar el mínimo de mínimos (y el máximo de máximos) de un
    grupo de cubos es el mínimo (máximo) real del rango que cubren, así que
    el resultado es idéntico a decimar de una vez con un factor mayor, sin
    tener que volver a tocar el array original en cada nivel.
    """
    v_min, v_max = anterior.minimo, anterior.maximo
    n = (len(v_min) // factor_base) * factor_base
    b_min = v_min[:n].reshape(-1, factor_base)
    b_max = v_max[:n].reshape(-1, factor_base)
    # `first`/`last` del nivel nuevo son el primero del primer cubo y el
    # último del último cubo del grupo: no hay que agregarlos, solo tomarlos.
    b_primero = anterior.primero[:n].reshape(-1, factor_base)
    b_ultimo = anterior.ultimo[:n].reshape(-1, factor_base)
    return NivelPiramide(
        factor=anterior.factor * factor_base,
        minimo=b_min.min(axis=1),
        maximo=b_max.max(axis=1),
        primero=b_primero[:, 0],
        ultimo=b_ultimo[:, -1],
    )


def construir_piramide(
    valores: np.ndarray, *, tipo: TipoCanalPiramide, factor_base: int = 4
) -> list[NivelPiramide]:
    """Construye todos los niveles de la pirámide sobre el array completo.

    Para `TipoCanalPiramide.CONTINUO` la construcción de un nivel es la
    operación de tres líneas de §3.5 (`reshape` + `min/max(axis=1)`), repetida
    sobre el nivel anterior hasta que el número de cubos es despreciable (deja
    de haber un grupo completo que decimar). Ningún nivel se calcula muestra a
    muestra: cada nivel decima el nivel anterior, no los datos originales, así
    que el coste total de toda la pirámide es ~1/3 del nivel base (§3.5), no
    un múltiplo de él.

    Las variantes `CONTADOR`, `ENUM` y `BITS` (suma de delta, moda con
    longitud de racha, OR de bits) son la tarea F1-10, que decide además si
    hace falta Numba según lo que mida el banco; aquí solo se declara el tipo,
    para que quien llame no tenga que esperar a F1-10 para tener el `Enum`.
    """
    if tipo is not TipoCanalPiramide.CONTINUO:
        raise NotImplementedError(
            f"{tipo.name}: agregación no continua, es la tarea F1-10 (suma de delta / "
            "moda de enum / OR de bits), todavía no implementada"
        )
    if factor_base < 2:
        raise ValueError(f"factor_base tiene que ser >= 2, se dio {factor_base}")

    niveles = [_nivel_l0(valores)]
    while len(niveles[-1].minimo) >= factor_base:
        niveles.append(_siguiente_nivel_continuo(niveles[-1], factor_base=factor_base))
    return niveles


def elegir_nivel(niveles: list[NivelPiramide], *, ancho_px: int) -> NivelPiramide:
    """Elige el nivel cuyo número de cubos es aproximadamente `ancho_px`.

    "Aproximadamente" es literal: el nivel con menos diferencia absoluta entre
    su número de cubos y `ancho_px`, sin preferencia por quedarse corto o
    largo. `niveles` no vacío (lo construye siempre `construir_piramide`, que
    al menos devuelve L0).
    """
    return min(niveles, key=lambda n: abs(len(n.minimo) - ancho_px))
