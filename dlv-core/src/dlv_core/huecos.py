"""Huecos de muestreo y discontinuidades de eje temporal (tarea F1-08).

Especificación: `docs/01-formato-log.md` §1.7 (el AutoLog es "irregular en el
tiempo": dt mediano 54 ms, dt máximo 499 ms, "no se debe asumir muestreo
uniforme") y §1.13 (marcas de tiempo no monótonas, ya detectadas por F1-04) y
`docs/04-perfiles-motorsport.md` §4.3, detector **D18** ("Hueco de muestreo:
dt > 3x mediana, informativa"). Este módulo es la primitiva vectorizada que
alimenta a D18 y a cualquier renderizador que tenga que "romper la línea en
el gráfico" (§1.7) donde el log dejó de grabar.

DOS ANOMALÍAS QUE NO SON LA MISMA
==================================
1. **Hueco de muestreo** (`detectar_huecos`): un intervalo entre dos muestras
   consecutivas de un canal cuyo `Δt` es un múltiplo grande de su periodo
   habitual. `ChannelSeries.t` (F1-05, `almacen.py`) ya viene sin las filas
   donde el canal no se muestreó -- eso es muestreo disperso normal y no
   aparece como hueco en `t` -- así que un `Δt` grande aquí solo puede venir
   de que el propio LOG dejó de grabar (pausa, tarjeta llena, USB
   desconectado) o de que el canal dejó de reportar durante un tramo largo.
   La distinción con el muestreo disperso normal es de magnitud: "periodo
   habitual x 1" no es hueco, "x muchos" sí.

2. **Discontinuidad de reloj** (`detectar_discontinuidades`): un punto donde
   `t` retrocede. `desenrollar_medianoche` (F1-04, `reloj.py`) ya desenrolla
   los cruces de medianoche genuinos (retrocesos > 12 h) antes de que el dato
   llegue a `ChannelSeries.t`; lo que quede retrocediendo en `t` es
   exactamente lo que `Desenrollado.retrocesos_anomalos` cuenta pero no dice
   DÓNDE («no se corrigen: se cuentan para el informe de importación»). Por
   eso `detectar_discontinuidades` no repite el trabajo de `reloj.py`, ni
   necesita su umbral de 12 h: opera directamente sobre `t` con
   `Δt < 0`, sin distinguir magnitudes, porque para cuando los datos llegan
   aquí los cruces de medianoche genuinos ya no existen como retroceso.

EL UMBRAL DE "HUECO ANORMAL"
=============================
`factor_umbral` (por omisión 3,0) se aplica al periodo TÍPICO del canal, y el
periodo típico se estima como la MEDIANA de los `Δt` positivos, no la media:
la mediana es insensible a los propios huecos que se están buscando (una
distribución bimodal de ráfaga/pausa como la del AutoLog real, §1.7, tendría
una media contaminada por las pausas, pero su mediana sigue reflejando la
ráfaga). El valor 3,0 no se inventa aquí: es el mismo que fija D18
(`docs/04-perfiles-motorsport.md` §4.3) y el que cita §1.7 como criterio para
"romper la línea en el gráfico", así que este módulo y el detector que lo use
comparten un único número, no dos que puedan desincronizarse.

ADR-009
=======
Ambas detecciones son `astype` -> `diff` -> comparación -> `flatnonzero`,
todo sobre el array de `t` completo. El único `for` de Python de este módulo
recorre los huecos/discontinuidades ENCONTRADOS -- normalmente unos pocos--,
nunca las muestras.

`t` puede ser `uint32` (el `dtype` real de `ChannelSeries.t`, F1-05): se
convierte explícitamente a `int64` antes de cualquier `diff`. Restar dos
`uint32` cuando el resultado es negativo no lanza un error, envuelve (wraps)
a un entero sin signo enorme -- exactamente el fallo que
`dlv-core/tests/test_almacen.py` ya evita casteando antes de comparar. Un
`Δt` negativo (retroceso) leído sin ese cast parecería un hueco gigantesco en
vez de una discontinuidad; con `int64` de por medio no hay ambigüedad
posible entre las dos anomalías.

Este módulo no importa `numpy` en el ámbito de tipos bajo `TYPE_CHECKING`
(sí en tiempo de ejecución, a diferencia de `reloj.py`): a diferencia de
`desenrollar_medianoche`, esta tarea no tiene que funcionar sin NumPy
instalado, porque F1-05 (su única dependencia) ya lo requiere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from dlv_core.detectores import Incidencia

if TYPE_CHECKING:
    from dlv_core.almacen import ChannelSeries

__all__ = [
    "FACTOR_UMBRAL_HUECO_POR_OMISION",
    "Discontinuidad",
    "Hueco",
    "detectar_discontinuidades",
    "detectar_discontinuidades_de_serie",
    "detectar_huecos",
    "detectar_huecos_de_serie",
    "discontinuidades_a_incidencias",
    "huecos_a_incidencias",
    "periodo_tipico_ms",
]

#: docs/01 §1.7 y docs/04 §4.3 (D18): "dt > 3x mediana" como criterio de
#: hueco anormal, tanto para romper la línea del gráfico como para el
#: detector informativo. Un único número compartido por ambos consumidores.
FACTOR_UMBRAL_HUECO_POR_OMISION = 3.0


@dataclass(slots=True, frozen=True)
class Hueco:
    """Un intervalo `[t[indice], t[indice + 1]]` cuyo `Δt` es anormalmente
    grande frente al periodo típico del canal (§1.7, D18)."""

    indice: int
    """Índice en `t`/`v` de la muestra ANTERIOR al hueco (`t[indice]` es el
    último instante bueno; `t[indice + 1]` es la reanudación)."""

    t_inicio: int
    t_fin: int
    duracion_ms: int
    """`t_fin - t_inicio`. Redundante con los dos anteriores, pero es lo que
    un panel de incidencias quiere mostrar directamente."""

    factor: float
    """`duracion_ms / periodo_tipico_ms` usado para clasificarlo como hueco.
    Se conserva para que el informe pueda decir "12x el periodo habitual" en
    vez de solo la duración absoluta."""


@dataclass(slots=True, frozen=True)
class Discontinuidad:
    """Un punto donde `t` retrocede: `t[indice + 1] < t[indice]`.

    Con `ChannelSeries.t` ya desenrollado de cruces de medianoche (F1-04),
    cualquier retroceso que quede aquí es, por construcción, uno de los
    `retrocesos_anomalos` que `Desenrollado` cuenta sin decir dónde.
    """

    indice: int
    """Índice de la muestra ANTERIOR al retroceso."""

    t_antes: int
    t_despues: int
    delta_ms: int
    """`t_despues - t_antes`, negativo por definición de discontinuidad."""


def periodo_tipico_ms(t: np.ndarray) -> float:
    """Mediana de los `Δt` positivos de `t`, en ms: estimador robusto del
    periodo de muestreo habitual del canal.

    Se filtran los `Δt` no positivos (retrocesos y muestras con la misma
    marca) antes de la mediana: mezclarlos desplazaría el periodo típico
    hacia abajo, y un `Δt` negativo no es "una tasa distinta", es una
    discontinuidad que `detectar_discontinuidades` trata aparte.

    Devuelve `nan` cuando no hay suficientes datos para estimarlo (menos de
    dos muestras, o ningún `Δt` positivo): quien llama a `detectar_huecos`
    interpreta `nan` como "no se puede clasificar", no como "periodo cero".
    """
    if t.size < 2:
        return float("nan")
    deltas = np.diff(t.astype(np.int64))
    positivos = deltas[deltas > 0]
    if positivos.size == 0:
        return float("nan")
    return float(np.median(positivos))


def detectar_huecos(
    t: np.ndarray,
    *,
    factor_umbral: float = FACTOR_UMBRAL_HUECO_POR_OMISION,
    periodo_ms: float | None = None,
) -> list[Hueco]:
    """Huecos de muestreo de `t`: `Δt > factor_umbral * periodo_tipico_ms(t)`.

    `periodo_ms`, si se da, sustituye la estimación automática -- útil cuando
    quien llama ya conoce la tasa nominal del canal (p. ej. "20 Hz" de un
    descriptor de formato) y no quiere depender de la mediana local de un
    segmento corto. Sin periodo utilizable (menos de dos muestras, o mediana
    no positiva: ver `periodo_tipico_ms`) no hay base para distinguir "normal"
    de "anormal", así que se devuelve una lista vacía en vez de arriesgar
    falsos positivos con un periodo inventado.

    Vectorizado (ADR-009): `astype` + `diff` + comparación + `flatnonzero`
    sobre el array completo; el único bucle de Python recorre los huecos
    encontrados (unos pocos), no las muestras.
    """
    if t.size < 2:
        return []
    periodo = periodo_ms if periodo_ms is not None else periodo_tipico_ms(t)
    if not periodo > 0.0:  # también descarta NaN: nan > 0.0 es False
        return []

    t64 = t.astype(np.int64)
    deltas = np.diff(t64)
    indices = np.flatnonzero(deltas > factor_umbral * periodo)

    return [
        Hueco(
            indice=int(i),
            t_inicio=int(t64[i]),
            t_fin=int(t64[i + 1]),
            duracion_ms=int(deltas[i]),
            factor=float(deltas[i]) / periodo,
        )
        for i in indices.tolist()
    ]


def detectar_discontinuidades(t: np.ndarray) -> list[Discontinuidad]:
    """Puntos donde `t` retrocede (`Δt < 0`).

    No aplica ningún umbral de magnitud (a diferencia de `detectar_huecos` y
    del `UMBRAL_RETROCESO_S` de 12 h de `reloj.py`): con `t` ya desenrollado
    de cruces de medianoche antes de llegar aquí (F1-04, `almacen.py`),
    cualquier retroceso que quede -- por pequeño que sea -- es exactamente un
    "retroceso anómalo": el eje no es fiable en ese punto y no se corrige
    (inventar cuál de las dos marcas es la buena no es responsabilidad de
    este módulo).

    Vectorizado (ADR-009), igual que `detectar_huecos`.
    """
    if t.size < 2:
        return []

    t64 = t.astype(np.int64)
    deltas = np.diff(t64)
    indices = np.flatnonzero(deltas < 0)

    return [
        Discontinuidad(
            indice=int(i),
            t_antes=int(t64[i]),
            t_despues=int(t64[i + 1]),
            delta_ms=int(deltas[i]),
        )
        for i in indices.tolist()
    ]


def detectar_huecos_de_serie(
    serie: ChannelSeries,
    *,
    factor_umbral: float = FACTOR_UMBRAL_HUECO_POR_OMISION,
    periodo_ms: float | None = None,
) -> list[Hueco]:
    """Azúcar sobre `detectar_huecos(serie.t, ...)` para quien ya tiene la
    `ChannelSeries` (F1-05, `almacen.py`) a mano."""
    return detectar_huecos(serie.t, factor_umbral=factor_umbral, periodo_ms=periodo_ms)


def detectar_discontinuidades_de_serie(serie: ChannelSeries) -> list[Discontinuidad]:
    """Azúcar sobre `detectar_discontinuidades(serie.t)`."""
    return detectar_discontinuidades(serie.t)


# --------------------------------------------------------------------------- #
# Adaptadores al formato compartido de detectores (`detectores.Incidencia`)
# --------------------------------------------------------------------------- #
def huecos_a_incidencias(
    huecos: list[Hueco], *, detector_id: str = "D18", severidad: str = "informativa"
) -> list[Incidencia]:
    """Convierte `Hueco` al `Incidencia` que comparten todos los detectores
    (`detectores.py`, §4.3): así D18 ("Hueco de muestreo") consume esta
    primitiva sin que este módulo tenga que conocer perfiles, roles ni
    severidades por canal -- eso es responsabilidad de la capa de detectores.
    """
    return [
        Incidencia(
            detector_id=detector_id,
            t_inicio=h.t_inicio,
            t_fin=h.t_fin,
            severidad=severidad,
            detalle={"duracion_ms": float(h.duracion_ms), "factor": h.factor},
        )
        for h in huecos
    ]


def discontinuidades_a_incidencias(
    discontinuidades: list[Discontinuidad],
    *,
    detector_id: str = "discontinuidad_reloj",
    severidad: str = "informativa",
) -> list[Incidencia]:
    """Convierte `Discontinuidad` a `Incidencia`, igual que `huecos_a_incidencias`.

    El intervalo `[t_inicio, t_fin]` de la `Incidencia` se deja en el mismo
    orden que produce `detectar_discontinuidades` (`t_antes`, `t_despues`),
    con `t_fin < t_inicio` cuando el retroceso es real: es la propia
    incidencia la que delata la anomalía, no hay que inventar un intervalo
    "corregido".
    """
    return [
        Incidencia(
            detector_id=detector_id,
            t_inicio=d.t_antes,
            t_fin=d.t_despues,
            severidad=severidad,
            detalle={"delta_ms": float(d.delta_ms)},
        )
        for d in discontinuidades
    ]
