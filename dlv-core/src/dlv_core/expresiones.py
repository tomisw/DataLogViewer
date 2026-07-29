"""Canales matemáticos: series derivadas por expresión sobre otros canales.

`docs/04-perfiles-motorsport.md`: un canal matemático (p. ej. potencia
estimada, slip de embrague) se define como una expresión sobre roles y se
evalúa como operación vectorizada de NumPy/Polars sobre las series completas
implicadas, nunca elemento a elemento en Python (ADR-009).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from dlv_core.almacen import ChannelSeries


@dataclass(slots=True, frozen=True)
class ExpresionCanal:
    """Definición de un canal matemático: fórmula + roles que consume."""

    id: str
    formula: str
    roles_entrada: tuple[str, ...]
    dimension_resultado: str | None


def compilar(expresion: ExpresionCanal) -> "object":
    """Compila la fórmula a una forma evaluable (AST propio o `numexpr`).

    La representación compilada real se decide al implementar este módulo;
    de momento solo se fija que compilar es un paso previo y separado de
    evaluar.
    """
    raise NotImplementedError


def evaluar(compilada: "object", series_por_rol: dict[str, "ChannelSeries"]) -> "np.ndarray":
    """Evalúa una expresión compilada sobre las series de entrada, vectorizado."""
    raise NotImplementedError
