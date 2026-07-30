"""Test funcional de `/comandos/serie` (tarea F1-22, ADR-007).

Cubre que la respuesta es binaria (Arrow IPC), no JSON, que sus bytes se
decodifican con `dlv_core.transporte.arrow_ipc_a_serie` a los mismos `t`/`v`
que produce el pipeline en memoria, que las cabeceras de metadatos llegan, y
los casos de error (token, fichero, canal).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from dlv_api.main import crear_app, generar_token_sesion  # noqa: E402
from dlv_core.almacen import Storage, construir_desde_polars  # noqa: E402
from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, parsear_cuerpo  # noqa: E402
from dlv_core.formatos.haltech import cargar_descriptor, parsear_cabecera  # noqa: E402
from dlv_core.formatos.limpieza import nulificar_centinelas  # noqa: E402
from dlv_core.transporte import arrow_ipc_a_serie  # noqa: E402
from dlv_core.unidades import cargar_catalogo  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
AUTOLOG_REAL = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
UNITS_TOML = RAIZ / "data" / "units.toml"


def _cliente_y_token() -> tuple[object, str]:
    token = generar_token_sesion()
    app = crear_app(token_sesion=token)
    return fastapi_testclient.TestClient(app), token


def _primer_canal_id() -> int:
    with DESCRIPTOR_TOML.open("rb") as fh:
        desc = cargar_descriptor(fh)
    cab = parsear_cabecera(AUTOLOG_REAL.read_bytes(), desc)
    return cab.canales[0].id


def test_sin_token_devuelve_401() -> None:
    cliente, _token = _cliente_y_token()
    respuesta = cliente.post(
        "/comandos/serie", json={"ruta": str(AUTOLOG_REAL), "canal_id": _primer_canal_id()}
    )
    assert respuesta.status_code == 401


def test_la_respuesta_es_binaria_y_coincide_con_el_pipeline_en_memoria() -> None:
    canal_id = _primer_canal_id()
    cliente, token = _cliente_y_token()

    respuesta = cliente.post(
        "/comandos/serie",
        json={"ruta": str(AUTOLOG_REAL), "canal_id": canal_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/vnd.apache.arrow.stream"
    # No es JSON: el cuerpo no puede decodificarse como tal.
    with pytest.raises(Exception):  # noqa: B017 - solo confirma que NO es JSON válido
        respuesta.json()

    t_http, v_http = arrow_ipc_a_serie(respuesta.content)

    # Referencia: el mismo pipeline, en memoria, sin pasar por HTTP.
    with DESCRIPTOR_TOML.open("rb") as fh:
        desc = cargar_descriptor(fh)
    with UNITS_TOML.open("rb") as fh:
        catalogo = cargar_catalogo(fh)
    datos = AUTOLOG_REAL.read_bytes()
    cab = parsear_cabecera(datos, desc)
    crudo = parsear_cuerpo(datos, cab)
    limpio = nulificar_centinelas(crudo, catalogo)
    storage = {columna_polars(c.columna): Storage.INT32_SCALED for c in cab.canales}
    series = construir_desde_polars(
        limpio, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )
    esperado = next(s for s in series if s.key.id_nativo == str(canal_id))

    assert np.array_equal(t_http, esperado.t)
    assert np.array_equal(v_http, esperado.v)
    assert respuesta.headers["x-muestras"] == str(len(esperado.t))
    assert respuesta.headers["x-storage"] == esperado.storage.name


def test_fichero_inexistente_devuelve_404() -> None:
    cliente, token = _cliente_y_token()
    respuesta = cliente.post(
        "/comandos/serie",
        json={"ruta": str(RAIZ / "no-existe.csv"), "canal_id": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 404


def test_canal_inexistente_devuelve_404() -> None:
    cliente, token = _cliente_y_token()
    respuesta = cliente.post(
        "/comandos/serie",
        json={"ruta": str(AUTOLOG_REAL), "canal_id": 999_999_999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 404
