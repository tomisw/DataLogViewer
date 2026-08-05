"""Test funcional del endpoint `/salud` (ADR-007).

Se salta con `importorskip` si `fastapi` no está instalado: en el sandbox
usado para andamiar F0-02 no hay acceso a PyPI (ver informe de la tarea), así
que este test es el que se ejecutará de verdad en un entorno con las
dependencias instaladas (CI normal), sin bloquear `python -m pytest` aquí.
"""

from __future__ import annotations

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from dlv_api.main import crear_app, generar_token_sesion  # noqa: E402


def test_salud_devuelve_version_y_estado() -> None:
    token = generar_token_sesion()
    app = crear_app(token_sesion=token)
    cliente = fastapi_testclient.TestClient(app)

    respuesta = cliente.get("/salud")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ok"
    assert isinstance(cuerpo["version_api"], str) and cuerpo["version_api"]
    assert isinstance(cuerpo["version_core"], str) and cuerpo["version_core"]


def test_salud_no_requiere_token() -> None:
    app = crear_app(token_sesion=generar_token_sesion())
    cliente = fastapi_testclient.TestClient(app)

    respuesta = cliente.get("/salud")

    assert respuesta.status_code == 200
