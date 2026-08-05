"""Test funcional de `/comandos/abrir-cabecera` (tarea F1-21, ADR-007).

Primer comando protegido por token: cubre que sin token/con token incorrecto
se rechaza (401), que con el token correcto y una ruta real funciona, que un
fichero inexistente da 404 y que una cabecera con firma inválida da 422 --
sin reventar el proceso en ningún caso, que es justo lo que hace útil un
comando "tipado" frente a dejar que la excepción se propague sin control.

Se salta con `importorskip` si `fastapi` no está instalado, mismo patrón que
`test_salud.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from dlv_api.main import crear_app, generar_token_sesion  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
AUTOLOG_REAL = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"


def _cliente_y_token() -> tuple[object, str]:
    token = generar_token_sesion()
    app = crear_app(token_sesion=token)
    return fastapi_testclient.TestClient(app), token


def test_sin_token_devuelve_401() -> None:
    cliente, _token = _cliente_y_token()
    respuesta = cliente.post("/comandos/abrir-cabecera", json={"ruta": str(AUTOLOG_REAL)})
    assert respuesta.status_code == 401


def test_con_token_incorrecto_devuelve_401() -> None:
    cliente, _token = _cliente_y_token()
    respuesta = cliente.post(
        "/comandos/abrir-cabecera",
        json={"ruta": str(AUTOLOG_REAL)},
        headers={"Authorization": "Bearer no-es-el-token"},
    )
    assert respuesta.status_code == 401


def test_con_token_correcto_abre_el_autolog_real() -> None:
    cliente, token = _cliente_y_token()
    respuesta = cliente.post(
        "/comandos/abrir-cabecera",
        json={"ruta": str(AUTOLOG_REAL)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["formato"] == "haltech_nsp"
    assert cuerpo["n_canales"] == 475
    assert len(cuerpo["canales"]) == 475
    assert cuerpo["canales"][0]["id"] > 0
    assert isinstance(cuerpo["avisos"], list)


def test_fichero_inexistente_devuelve_404() -> None:
    cliente, token = _cliente_y_token()
    respuesta = cliente.post(
        "/comandos/abrir-cabecera",
        json={"ruta": str(RAIZ / "no-existe-de-verdad.csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 404


def test_fichero_con_firma_invalida_devuelve_422(tmp_path: Path) -> None:
    ruta = tmp_path / "no-es-un-log.csv"
    ruta.write_bytes(b"esto no es un log Haltech\n")

    cliente, token = _cliente_y_token()
    respuesta = cliente.post(
        "/comandos/abrir-cabecera",
        json={"ruta": str(ruta)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 422


def test_salud_sigue_sin_requerir_token() -> None:
    """No es una regresión de esta tarea: confirma que añadir un comando
    protegido no cambió `/salud`, que sigue siendo la excepción a propósito."""
    cliente, _token = _cliente_y_token()
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
