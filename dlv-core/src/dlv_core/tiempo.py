"""Motor de tiempo multi-log: segmentos, vista paralela y concatenada (§3.6).

Cada log cargado es un segmento con su propio reloj (absoluto, relativo,
manual, por evento o por correlación). Este módulo no lee ficheros ni conoce
formatos: recibe segmentos y series ya construidas por `almacen.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from dlv_core.almacen import ChannelSeries


class FiabilidadReloj(Enum):
    """Fiabilidad del `t0_absoluto` de un segmento (§3.6)."""

    FIABLE = auto()
    NO_FIABLE = auto()
    DESCONOCIDA = auto()


class ModoDesfase(Enum):
    """Modo de cálculo de `offset_efectivo` en la vista paralela (§3.6)."""

    RELOJ_ABSOLUTO = auto()
    RELATIVO = auto()
    MANUAL = auto()
    POR_EVENTO = auto()
    CORRELACION = auto()


@dataclass(slots=True)
class Segmento:
    """Un log cargado, con su identidad temporal (§3.6)."""

    id: str
    t0_absoluto: datetime | None
    offset_usuario: float
    fiabilidad_reloj: FiabilidadReloj
    orden: int


def desfase_efectivo(
    segmentos: list[Segmento], *, modo: ModoDesfase, rol_referencia: str | None = None
) -> dict[str, float]:
    """Calcula el `offset_efectivo` de cada segmento para la vista paralela."""
    raise NotImplementedError


def correlacionar(
    referencia: ChannelSeries, candidata: ChannelSeries, *, nivel_piramide: int
) -> float:
    """Argmáx de la correlación cruzada sobre niveles L4-L6 de la pirámide (§3.6).

    Se calcula con `numpy.correlate`/FFT sobre la pirámide, no sobre L0; el
    refinamiento en L0 alrededor del máximo encontrado es un paso posterior,
    también vectorizado.
    """
    raise NotImplementedError


def concatenar(
    segmentos: list[Segmento], series_por_segmento: dict[str, list[ChannelSeries]]
) -> np.ndarray:
    """Coloca los segmentos consecutivamente con hueco explícito (vista concatenada).

    Reglas duras de §3.6: nunca se dibuja una línea que cruce una frontera de
    segmento, y un canal ausente en un segmento produce hueco, no ceros.
    """
    raise NotImplementedError
