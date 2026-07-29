"""Almacén columnar: representación en memoria de cada canal (ADR-003).

Regla de disciplina de rendimiento (ADR-009, `docs/03-arquitectura.md` §3.2):

    Ninguna ruta que se ejecute una vez por muestra puede estar escrita en
    Python interpretado. Todo cálculo sobre series es una operación de NumPy
    o Polars sobre el array completo: `for` sobre muestras, `.apply()`,
    `.iterrows()` y `map()` por elemento están prohibidos en `dlv-core`. Lo
    que no se puede vectorizar (histéresis, decimación por moda con longitud
    de racha, autómatas de estado) se implementa en Numba `@njit`, no en
    Python puro.

Este módulo no accede al sistema de ficheros por su cuenta: todo lo que
necesita como entrada (arrays ya materializados, un `polars.DataFrame`, un
lector) llega como parámetro desde quien lo llama.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from dlv_core.roles import ChannelKey
from dlv_core.unidades import Afin

if TYPE_CHECKING:
    import numpy as np
    import polars as pl


class Storage(Enum):
    """Representación de almacenamiento de un canal (ADR-003)."""

    INT32_SCALED = auto()  # entero crudo + (a, b) a canónica — camino nativo
    FLOAT32 = auto()  # decimal de origen, precisión suficiente
    FLOAT64 = auto()  # decimal que necesita precisión (tiempo, GPS)
    ENUM_U16 = auto()  # estado con diccionario de códigos
    BITS_U32 = auto()  # máscara de bits


@dataclass(slots=True)
class ChannelSeries:
    """Una serie temporal de canal, tal como vive en el almacén (ADR-003).

    `t` se comparte por referencia entre canales del mismo grupo de muestreo
    (§3.2 ADR-003): construir `ChannelSeries` no copia `t`.
    """

    key: ChannelKey
    role: str | None
    t: np.ndarray  # uint32, ms desde t0 del segmento, compartido por grupo
    v: np.ndarray  # según `storage`
    storage: Storage
    to_canon: Afin
    dimension: str | None  # None => se muestra en crudo, sin unidad


def construir_desde_polars(
    df: pl.DataFrame, *, columna_tiempo: str, storage_por_columna: dict[str, Storage]
) -> list[ChannelSeries]:
    """Construye una `ChannelSeries` por columna de un `DataFrame` ya parseado.

    Usa `to_numpy(zero_copy_only=True)` (ADR-001) para las vistas: no copia ni
    itera fila a fila.
    """
    raise NotImplementedError


def indexar(serie: ChannelSeries) -> np.ndarray:
    """Calcula min/máx/percentiles y clasificación activo/constante/vacío/fuera
    de rango (§3.4 paso 5) sobre el array completo, sin bucle por muestra.
    """
    raise NotImplementedError
