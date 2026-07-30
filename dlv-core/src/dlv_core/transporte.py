"""Transporte binario de series (ADR-007, tarea F1-22).

Regla dura de ADR-007: **las series nunca viajan en JSON.** Un canal de
varios millones de muestras en JSON de coma flotante haría inalcanzable
cualquier presupuesto de latencia; JSON queda para los metadatos (canales,
avisos), de volumen en kilobytes -- eso ya lo hace F1-21
(`/comandos/abrir-cabecera`).

Arrow IPC es lo que sí se transporta: Polars ya sabe escribirlo y leerlo sin
PyArrow como dependencia directa (ADR-005, misma decisión que la caché
Parquet de F1-11), y el frontend lo lee como `TypedArray` sin volver a
parsear texto -- es exactamente la representación en memoria que
`ChannelSeries.t`/`.v` ya tienen, solo que serializada.

Este módulo no accede al sistema de ficheros (ADR-002): trabaja con `bytes`
en memoria, nunca con una ruta. Quien sirve estos bytes por HTTP (`dlv-api`)
decide dónde viven los ficheros.
"""

from __future__ import annotations

import io

import numpy as np
import polars as pl

__all__ = ["arrow_ipc_a_serie", "serie_a_arrow_ipc"]

MEDIA_TYPE_ARROW_IPC = "application/vnd.apache.arrow.stream"
"""Tipo MIME de la respuesta binaria; lo usa `dlv-api` en la cabecera HTTP."""


def serie_a_arrow_ipc(t: np.ndarray, v: np.ndarray) -> bytes:
    """Serializa `(t, v)` de una `ChannelSeries` a bytes Arrow IPC (stream).

    Dos columnas, "t" y "v", en ese orden: es la forma más simple que cubre
    el caso de uso (un canal a la vez) sin inventar un esquema más elaborado
    hasta que haga falta transportar varios canales en una sola respuesta.
    """
    tabla = pl.DataFrame({"t": t, "v": v})
    buffer = io.BytesIO()
    tabla.write_ipc(buffer)
    return buffer.getvalue()


def arrow_ipc_a_serie(datos: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Inversa de `serie_a_arrow_ipc`: bytes Arrow IPC -> `(t, v)`.

    `to_numpy()` sin `allow_copy=False` a propósito (mismo razonamiento que
    `almacen.construir_desde_polars`, F1-05): lo que importa es no iterar
    fila a fila, no garantizar cero copias en todas las circunstancias.
    """
    tabla = pl.read_ipc(io.BytesIO(datos))
    return tabla["t"].to_numpy(), tabla["v"].to_numpy()
