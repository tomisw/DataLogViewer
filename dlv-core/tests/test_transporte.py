"""Pruebas del transporte binario de series (tarea F1-22, ADR-007).

Cubre el round-trip exacto (lo que sale de `arrow_ipc_a_serie` es
bit a bit lo que entró a `serie_a_arrow_ipc`, sin pérdida de precisión ni
reordenación) y que el resultado es realmente binario, no JSON.
"""

from __future__ import annotations

import numpy as np

from dlv_core.transporte import MEDIA_TYPE_ARROW_IPC, arrow_ipc_a_serie, serie_a_arrow_ipc


def test_round_trip_preserva_los_valores_exactos() -> None:
    t = np.array([0, 54, 108, 500_000], dtype=np.uint32)
    v = np.array([100, -200, 300, 2147483647], dtype=np.int32)

    datos = serie_a_arrow_ipc(t, v)
    t2, v2 = arrow_ipc_a_serie(datos)

    assert np.array_equal(t, t2)
    assert np.array_equal(v, v2)


def test_round_trip_con_muchas_muestras() -> None:
    rng = np.random.default_rng(0)
    t = np.cumsum(rng.integers(1, 500, size=100_000)).astype(np.uint32)
    v = rng.integers(-32768, 32767, size=100_000).astype(np.int32)

    datos = serie_a_arrow_ipc(t, v)
    t2, v2 = arrow_ipc_a_serie(datos)

    assert np.array_equal(t, t2)
    assert np.array_equal(v, v2)


def test_serie_vacia_no_revienta() -> None:
    t = np.array([], dtype=np.uint32)
    v = np.array([], dtype=np.int32)

    datos = serie_a_arrow_ipc(t, v)
    t2, v2 = arrow_ipc_a_serie(datos)

    assert len(t2) == 0
    assert len(v2) == 0


def test_el_resultado_es_binario_no_json() -> None:
    t = np.array([1, 2, 3], dtype=np.uint32)
    v = np.array([10, 20, 30], dtype=np.int32)

    datos = serie_a_arrow_ipc(t, v)

    # Un Arrow IPC stream empieza por una marca de continuación/esquema, no
    # por '[' o '{': confirma que no es JSON "por accidente".
    assert datos[:1] not in (b"[", b"{")
    assert isinstance(datos, bytes)


def test_media_type_declarado_es_el_de_arrow_stream() -> None:
    assert MEDIA_TYPE_ARROW_IPC == "application/vnd.apache.arrow.stream"
