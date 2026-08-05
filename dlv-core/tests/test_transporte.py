"""Pruebas del transporte binario de series (tarea F1-22, ADR-007).

Cubre el round-trip exacto (lo que sale de `arrow_ipc_a_serie` es
bit a bit lo que entró a `serie_a_arrow_ipc`, sin pérdida de precisión ni
reordenación) y que el resultado es realmente binario, no JSON.
"""

from __future__ import annotations

import numpy as np
import pytest

from dlv_core.transporte import (
    COLUMNAS_CUBOS,
    MEDIA_TYPE_ARROW_IPC,
    arrow_ipc_a_serie,
    binario_a_cubos,
    cubos_a_binario,
    serie_a_arrow_ipc,
)


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


# --------------------------------------------------------------------------- #
# Búfer de tipado fijo (F1-43): la forma que sí puede leer el frontend
# --------------------------------------------------------------------------- #
# `dlv-ui` no tiene dependencias, así que no puede leer Arrow IPC sin añadir
# `apache-arrow` o escribir un lector a mano. ADR-007 ya preveía la
# alternativa: un búfer de tipado fijo que se lee como `TypedArray` sin
# parsear. Lo que estas pruebas protegen es el CONTRATO de ese búfer, porque
# está descrito en dos sitios (aquí y en `dlv-ui/src/datos/fuente-api.ts`) y
# nada del compilador los ata: si el orden de las columnas o el tipo cambian,
# el frontend leería números plausibles y equivocados en vez de fallar.
def test_el_binario_es_cinco_columnas_float32_seguidas() -> None:
    n = 7
    columnas = [np.arange(n, dtype=np.float32) + i * 100 for i in range(5)]
    datos = cubos_a_binario(*columnas)

    assert len(datos) == n * 5 * 4, "cinco columnas de float32, sin cabecera ni relleno"
    plano = np.frombuffer(datos, dtype="<f4")
    for i, esperada in enumerate(columnas):
        assert np.array_equal(plano[i * n : (i + 1) * n], esperada), (
            f"la columna {i} ({COLUMNAS_CUBOS[i]}) no está donde el frontend la busca"
        )


def test_el_binario_es_little_endian_pase_lo_que_pase() -> None:
    """Los `TypedArray` de JavaScript usan el orden del procesador.

    Un servidor big-endian serviría bytes que el navegador leería del revés y
    produciría números absurdos en vez de un error, así que el orden se fija
    aquí en vez de dejarlo al azar del intérprete.
    """
    datos = cubos_a_binario(*[np.array([1.0], dtype=np.float32) for _ in range(5)])
    assert datos[:4] == np.float32(1.0).astype("<f4").tobytes()


def test_ida_y_vuelta_del_binario() -> None:
    columnas = {
        "t": np.array([0.0, 0.5, 1.0], dtype=np.float32),
        "minimo": np.array([10.0, 11.0, 12.0], dtype=np.float32),
        "maximo": np.array([20.0, 21.0, 22.0], dtype=np.float32),
        "primero": np.array([12.0, 13.0, 14.0], dtype=np.float32),
        "ultimo": np.array([18.0, 19.0, 20.0], dtype=np.float32),
    }
    vuelta = binario_a_cubos(cubos_a_binario(*columnas.values()), 3)
    for nombre, esperada in columnas.items():
        assert np.array_equal(vuelta[nombre], esperada)


def test_un_binario_truncado_se_delata_en_vez_de_leerse_a_medias() -> None:
    """Sin esta comprobación, un cuerpo cortado por la red daría `NaN` en las
    últimas columnas, y un `NaN` en WebGL no da error: da un hueco en el trazo
    que solo se diagnostica mirando el lienzo."""
    datos = cubos_a_binario(*[np.zeros(4, dtype=np.float32) for _ in range(5)])
    with pytest.raises(ValueError, match="bytes"):
        binario_a_cubos(datos[:-8], 4)


def test_columnas_descuadradas_se_rechazan_igual_que_en_arrow() -> None:
    with pytest.raises(ValueError, match="misma longitud"):
        cubos_a_binario(
            np.zeros(3, dtype=np.float32),
            np.zeros(2, dtype=np.float32),
            np.zeros(3, dtype=np.float32),
            np.zeros(3, dtype=np.float32),
            np.zeros(3, dtype=np.float32),
        )


def test_cero_cubos_da_un_buffer_vacio_y_no_un_error() -> None:
    """Pedir un rango fuera del log devuelve 0 cubos, y eso es normal: el
    frontend pide con margen (F1-24) y se sale por los bordes constantemente."""
    vacio = [np.zeros(0, dtype=np.float32) for _ in range(5)]
    assert cubos_a_binario(*vacio) == b""
    assert all(len(c) == 0 for c in binario_a_cubos(b"", 0).values())
