"""Detectores de eventos motorsport (`docs/04-perfiles-motorsport.md`).

Los detectores (picos, topes de alerta, knock, launch, cortes...) se definen
por rol semántico (ADR-008), no por canal concreto, y se ejecutan sobre el
array completo de la serie.

EL MOTOR ESTÁ EN `primitivas.py`
=================================
Las nueve primitivas de §4.3 —umbral con histéresis, pico local, derivada,
tiempo por encima, conteo de cruces, delta de contador, banda, compuesto y
fuera de máscara—, la permanencia mínima y el modelo de `Evento` viven en
`dlv_core.primitivas` (F3-06). Este módulo se queda con el vocabulario
compartido: `Incidencia`, que es un `Evento` más el tipo, la severidad y el
contexto que aporta la configuración del detector (F3-07), y el contrato
`Detector`.

Este docstring decía que «la histéresis y los autómatas de estado que no se
pueden vectorizar en NumPy van en Numba». **No ha hecho falta Numba**: la
histéresis se vectoriza como una retención del último cruce decisivo y las
ventanas temporales con `searchsorted` más una tabla dispersa de extremos (ver
la cabecera de `primitivas.py`). La regla de fondo no cambia: cero bucles por
muestra en Python (ADR-009), y si algún día alguno no se puede vectorizar, va a
Numba y no a un `for`.

El `umbral_simple` que este módulo declaraba como andamiaje ya no está: lo
sustituye `primitivas.umbral_con_histeresis`, que es el mismo umbral con la
histéresis que §4.3 exige. Dos formas de comparar un canal con un umbral —una
con histéresis y otra sin— eran dos formas de escribir el mismo detector con
resultados distintos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from dlv_core.almacen import ChannelSeries


@dataclass(slots=True, frozen=True)
class Incidencia:
    """Una detección puntual o de intervalo producida por un detector.

    Es `primitivas.Evento` más lo que aporta la configuración del detector: el
    identificador, la severidad y el contexto. La conversión la hace F3-07,
    porque es quien conoce el detector; `primitivas.py` no la ofrece a propósito,
    y el motivo está anotado para quien escriba F3-07: `detalle` es un
    `dict[str, float]` y un diccionario de números no puede llevar la CLASE de
    conversión de cada número. `primitivas.Evento.clase_valor` sí la lleva, así
    que un `valor_pico` que sea una tasa (el pico de una derivada) o un
    intervalo (el delta de un contador) se pierde al meterlo aquí y el panel de
    incidencias lo convertirá como punto -- la trampa del delta llegando por la
    puerta de la presentación.
    """

    detector_id: str
    t_inicio: int
    t_fin: int | None
    severidad: str
    detalle: dict[str, float]


class Detector(Protocol):
    """Contrato de un detector: recibe la(s) serie(s) por rol, devuelve incidencias.

    Cualquier implementación respeta ADR-009: nada aquí itera muestra a muestra
    en Python puro. La forma prevista de cumplirlo es componer las primitivas de
    `dlv_core.primitivas`, que ya lo cumplen.
    """

    id: str
    roles_requeridos: tuple[str, ...]

    def ejecutar(self, series_por_rol: dict[str, ChannelSeries]) -> list[Incidencia]: ...
