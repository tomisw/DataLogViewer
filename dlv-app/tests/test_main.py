"""Pruebas de `dlv_app.main` que no requieren abrir una ventana real.

Probar una GUI de verdad no es viable en CI sin pantalla (F1-35), asi que
estas pruebas se centran en lo que si es comprobable sin `pywebview`
abriendo nada: que el servidor de fondo arranca y `/salud` responde, que el
cierre limpio para el hilo, y que la URL/HTML que recibiria el frontend se
construyen bien. Ninguna llama a `webview.create_window` ni a
`webview.start()`.

`pytest.importorskip("webview")` sigue el mismo patron que
`dlv-api/tests/test_salud.py` usa con `fastapi.testclient`: en un sandbox sin
acceso a PyPI estas pruebas se saltan en vez de romper `python -m pytest`.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

pytest.importorskip("webview")
pytest.importorskip("fastapi")

from dlv_api.main import ServidorArrancado
from dlv_app.main import (
    _esperar_servidor,
    _pagina_placeholder,
    _url_con_credenciales,
    detener_servidor_de_fondo,
    iniciar_api_en_hilo,
)


def test_iniciar_api_en_hilo_responde_en_salud_y_se_detiene_con_limpieza() -> None:
    estado = iniciar_api_en_hilo()
    try:
        assert estado.hilo.is_alive()
        with urllib.request.urlopen(
            f"http://{estado.info.host}:{estado.info.puerto}/salud", timeout=1.0
        ) as respuesta:
            cuerpo = json.loads(respuesta.read())
        assert cuerpo["estado"] == "ok"
    finally:
        detener_servidor_de_fondo(estado)

    # El hilo debe haber terminado: cerrar la ventana no puede dejar un
    # servidor huerfano escuchando en el puerto.
    assert not estado.hilo.is_alive()


def test_esperar_servidor_agota_el_timeout_si_no_hay_servidor() -> None:
    # Puerto 1: privilegiado y sin nada escuchando en el entorno de pruebas,
    # asi que la conexion se rechaza enseguida y el sondeo agota el timeout.
    info = ServidorArrancado(host="127.0.0.1", puerto=1, token_sesion="no-usado")

    with pytest.raises(TimeoutError):
        _esperar_servidor(info, timeout_s=0.3)


def test_url_con_credenciales_incluye_puerto_y_token() -> None:
    info = ServidorArrancado(host="127.0.0.1", puerto=54321, token_sesion="abc-token")

    url = _url_con_credenciales("http://localhost:5173", info)

    assert url.startswith("http://localhost:5173?")
    assert "puerto_api=54321" in url
    assert "token=abc-token" in url


def test_url_con_credenciales_preserva_la_query_existente() -> None:
    info = ServidorArrancado(host="127.0.0.1", puerto=1, token_sesion="t")

    url = _url_con_credenciales("http://localhost:5173/?ya=1", info)

    assert "ya=1" in url
    assert "puerto_api=1" in url
    assert "token=t" in url


def test_pagina_placeholder_incluye_token_puerto_y_marca_provisional() -> None:
    info = ServidorArrancado(host="127.0.0.1", puerto=9999, token_sesion="secreto-xyz")

    html = _pagina_placeholder(info)

    assert "secreto-xyz" in html
    assert "9999" in html
    assert "PROVISIONAL" in html
    # El token no debe colarse en ninguna URL/atributo href del placeholder:
    # solo debe aparecer como valor de una variable JS.
    assert 'window.__DLV_TOKEN__ = "secreto-xyz"' in html
