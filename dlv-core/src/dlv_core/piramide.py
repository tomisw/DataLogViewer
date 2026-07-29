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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    minimo: "np.ndarray"
    maximo: "np.ndarray"
    primero: "np.ndarray"
    ultimo: "np.ndarray"


def construir_piramide(
    valores: "np.ndarray", *, tipo: TipoCanalPiramide, factor_base: int = 4
) -> list[NivelPiramide]:
    """Construye todos los niveles de la pirámide sobre el array completo.

    Para `TipoCanalPiramide.CONTINUO` la construcción de un nivel es la
    operación de tres líneas de §3.5 (`reshape` + `min/max(axis=1)`), repetida
    sobre el nivel anterior hasta que el número de cubos es despreciable.
    Ningún nivel se calcula muestra a muestra.
    """
    raise NotImplementedError


def elegir_nivel(niveles: list[NivelPiramide], *, ancho_px: int) -> NivelPiramide:
    """Elige el nivel cuyo número de cubos es aproximadamente `ancho_px`."""
    raise NotImplementedError
