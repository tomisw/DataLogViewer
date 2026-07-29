"""Detectores de eventos motorsport (`docs/04-perfiles-motorsport.md`).

Los detectores (picos, topes de alerta, knock, launch, cortes...) se definen
por rol semántico (ADR-008), no por canal concreto, y se ejecutan sobre el
array completo de la serie. La histéresis y los autómatas de estado que no se
pueden vectorizar en NumPy van en Numba (`@njit`), nunca en un bucle Python
(ADR-009).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import numpy as np

    from dlv_core.almacen import ChannelSeries


@dataclass(slots=True, frozen=True)
class Incidencia:
    """Una detección puntual o de intervalo producida por un detector."""

    detector_id: str
    t_inicio: int
    t_fin: int | None
    severidad: str
    detalle: dict[str, float]


class Detector(Protocol):
    """Contrato de un detector: recibe la(s) serie(s) por rol, devuelve incidencias.

    Cualquier implementación (histéresis con Numba, umbral simple con NumPy)
    respeta ADR-009: nada aquí itera muestra a muestra en Python puro.
    """

    id: str
    roles_requeridos: tuple[str, ...]

    def ejecutar(self, series_por_rol: dict[str, "ChannelSeries"]) -> list[Incidencia]: ...


def umbral_simple(valores: "np.ndarray", *, minimo: float | None, maximo: float | None) -> "np.ndarray":
    """Máscara booleana vectorizada de muestras fuera de `[minimo, maximo]`."""
    raise NotImplementedError
