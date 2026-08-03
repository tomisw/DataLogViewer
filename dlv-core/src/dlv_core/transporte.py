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

__all__ = [
    "COLUMNAS_CUBOS",
    "arrow_ipc_a_cubos",
    "arrow_ipc_a_serie",
    "cubos_a_arrow_ipc",
    "serie_a_arrow_ipc",
]

MEDIA_TYPE_ARROW_IPC = "application/vnd.apache.arrow.stream"
"""Tipo MIME de la respuesta binaria; lo usa `dlv-api` en la cabecera HTTP."""

COLUMNAS_CUBOS: tuple[str, ...] = ("t", "minimo", "maximo", "primero", "ultimo")
"""Columnas de un lote de cubos `CONTINUO`, en orden.

Son exactamente los campos de `CubosContinuos` en `dlv-ui/src/render/tipos.ts`
(menos `tOrigen` y `factor`, que son escalares y viajan en cabeceras HTTP, no
en el cuerpo binario). El orden importa: el frontend puede leer las columnas
por posición sin buscarlas por nombre.
"""


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


def cubos_a_arrow_ipc(
    t: np.ndarray,
    minimo: np.ndarray,
    maximo: np.ndarray,
    primero: np.ndarray,
    ultimo: np.ndarray,
) -> bytes:
    """Serializa un lote de cubos `CONTINUO` a bytes Arrow IPC (stream).

    Cinco columnas en el orden de `COLUMNAS_CUBOS`, que es el contrato de
    `CubosContinuos` del frontend. Los dos escalares que ese contrato pide
    además (`tOrigen` y `factor`) NO van aquí: viajan en cabeceras HTTP,
    igual que ya hace `/comandos/serie` con la dimensión y el factor de
    conversión, para no mezclar JSON y binario en un mismo cuerpo (ADR-007).

    Esta función no impone dtypes: los pone quien llama. Lo natural es
    `float32` en las cinco columnas -- es lo que acaba en la GPU y lo que
    `CubosContinuos` declara-- y `t` ya restado su origen, porque un
    `float32` con el instante absoluto de un log de 8 h pierde los dígitos
    que importan (ver el comentario de `CubosContinuos.t`).
    """
    if not (len(t) == len(minimo) == len(maximo) == len(primero) == len(ultimo)):
        raise ValueError(
            "las cinco columnas de cubos deben tener la misma longitud: "
            f"t={len(t)}, minimo={len(minimo)}, maximo={len(maximo)}, "
            f"primero={len(primero)}, ultimo={len(ultimo)}"
        )
    tabla = pl.DataFrame(
        {"t": t, "minimo": minimo, "maximo": maximo, "primero": primero, "ultimo": ultimo}
    )
    buffer = io.BytesIO()
    tabla.write_ipc(buffer)
    return buffer.getvalue()


def arrow_ipc_a_cubos(datos: bytes) -> dict[str, np.ndarray]:
    """Inversa de `cubos_a_arrow_ipc`: bytes Arrow IPC -> columna por nombre.

    Devuelve un diccionario y no una tupla de cinco arrays a propósito: cinco
    posiciones sin nombre son cinco oportunidades de intercambiar `minimo` con
    `maximo` en la línea que las desempaqueta, y ese error no se nota hasta que
    alguien mira un gráfico y lo cree.
    """
    tabla = pl.read_ipc(io.BytesIO(datos))
    return {columna: tabla[columna].to_numpy() for columna in COLUMNAS_CUBOS}
