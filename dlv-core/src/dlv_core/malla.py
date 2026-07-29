"""Malla RPM x MAP para análisis tabular y tablas de corrección (F4, epica de
`docs/02-alcance-y-plan.md`).

Construye una tabla 2D (bins de RPM x bins de MAP/carga) con una estadística
agregada por celda (media, percentil, cuenta) sobre un rol tercero (p. ej.
lambda, knock count). La construcción es un `histogram2d`/`groupby` vectorizado
de NumPy o Polars, nunca una asignación celda a celda en Python (ADR-009).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


@dataclass(slots=True, frozen=True)
class Malla:
    """Una malla RPM x MAP ya agregada."""

    bins_rpm: np.ndarray
    bins_map: np.ndarray
    valores: np.ndarray  # forma (len(bins_rpm)-1, len(bins_map)-1)
    estadistica: str  # "media" | "percentil_95" | "cuenta" | ...


def construir_malla(
    rpm: np.ndarray,
    presion_map: np.ndarray,
    valor: np.ndarray,
    *,
    bins_rpm: np.ndarray,
    bins_map: np.ndarray,
    estadistica: str,
) -> Malla:
    """Agrega `valor` en la malla RPM x MAP con la estadística indicada."""
    raise NotImplementedError
