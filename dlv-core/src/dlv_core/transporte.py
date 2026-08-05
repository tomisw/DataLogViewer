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
    "binario_a_cubos",
    "cubos_a_arrow_ipc",
    "cubos_a_binario",
    "serie_a_arrow_ipc",
]

MEDIA_TYPE_ARROW_IPC = "application/vnd.apache.arrow.stream"
"""Tipo MIME de la respuesta binaria; lo usa `dlv-api` en la cabecera HTTP."""

MEDIA_TYPE_CUBOS_CRUDO = "application/octet-stream"
"""Tipo MIME del búfer de tipado fijo. Ver `cubos_a_binario`."""

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


def cubos_a_binario(
    t: np.ndarray,
    minimo: np.ndarray,
    maximo: np.ndarray,
    primero: np.ndarray,
    ultimo: np.ndarray,
) -> bytes:
    """Las cinco columnas como un búfer de tipado fijo: `float32` seguidos.

    POR QUÉ EXISTE, HABIENDO YA ARROW IPC
    =====================================
    ADR-007 ofrece las dos formas a propósito: «Los cubos visibles se envían
    como **Arrow IPC** o como **búfer de tipado fijo**, que en el frontend se
    lee como `TypedArray` sin parseo». Al cablear `FuenteApi` (el MVP) resultó
    que la segunda no era una alternativa estilística sino la única viable:
    `dlv-ui` no tiene ninguna dependencia y leer Arrow IPC en el navegador
    exige o la librería `apache-arrow` —una dependencia nueva, que no se añade
    sin preguntar (docs/09 §9.11)— o escribir a mano un lector del formato,
    que es mucho código delicado para transportar cinco arrays de números.

    El formato es deliberadamente tonto: `n` valores `float32` de `t`, luego
    `n` de `minimo`, y así con las cinco columnas de `COLUMNAS_CUBOS`, en ese
    orden. Sin cabecera, sin longitudes embebidas: `n` va en la cabecera HTTP
    `X-Cubos`, igual que el resto de metadatos. En el frontend, cada columna es
    un `new Float32Array(buffer, i * n * 4, n)` — cero parseo, que es
    literalmente lo que pide el ADR.

    **Little-endian**, forzado con `<f4` y no dejado al azar del intérprete:
    los `TypedArray` de JavaScript usan el orden del procesador, que hoy es
    little-endian en todo lo que ejecuta este programa, pero un servidor
    big-endian serviría bytes que el navegador leería del revés y produciría
    números absurdos en vez de un error. Fijarlo aquí cuesta nada.

    Arrow IPC no se retira: sigue siendo lo que consumen las pruebas de Python
    y cualquier cliente que ya tenga la librería.
    """
    columnas = (t, minimo, maximo, primero, ultimo)
    n = len(t)
    if any(len(c) != n for c in columnas):
        raise ValueError(
            "las cinco columnas de cubos deben tener la misma longitud: "
            f"t={len(t)}, minimo={len(minimo)}, maximo={len(maximo)}, "
            f"primero={len(primero)}, ultimo={len(ultimo)}"
        )
    return b"".join(np.ascontiguousarray(c, dtype="<f4").tobytes() for c in columnas)


def binario_a_cubos(datos: bytes, n: int) -> dict[str, np.ndarray]:
    """Inversa de `cubos_a_binario`. Existe para poder probar la ida y vuelta.

    `n` no se deduce de `len(datos)`: se pasa, igual que hace el frontend
    leyéndolo de `X-Cubos`. Deducirlo escondería un búfer truncado —que daría
    un `n` menor y plausible— en vez de delatarlo.
    """
    esperado = n * len(COLUMNAS_CUBOS) * 4
    if len(datos) != esperado:
        raise ValueError(
            f"el búfer mide {len(datos)} bytes y para {n} cubos deberían ser {esperado}"
        )
    plano = np.frombuffer(datos, dtype="<f4")
    return {columna: plano[i * n : (i + 1) * n] for i, columna in enumerate(COLUMNAS_CUBOS)}


def arrow_ipc_a_cubos(datos: bytes) -> dict[str, np.ndarray]:
    """Inversa de `cubos_a_arrow_ipc`: bytes Arrow IPC -> columna por nombre.

    Devuelve un diccionario y no una tupla de cinco arrays a propósito: cinco
    posiciones sin nombre son cinco oportunidades de intercambiar `minimo` con
    `maximo` en la línea que las desempaqueta, y ese error no se nota hasta que
    alguien mira un gráfico y lo cree.
    """
    tabla = pl.read_ipc(io.BytesIO(datos))
    return {columna: tabla[columna].to_numpy() for columna in COLUMNAS_CUBOS}
