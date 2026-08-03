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
from pathlib import Path

import pytest

pytest.importorskip("webview")
pytest.importorskip("fastapi")

from dlv_api.main import ServidorArrancado
from dlv_app.main import (
    _detectar_dist_ui,
    _esperar_servidor,
    _pagina_placeholder,
    _url_con_credenciales,
    detener_servidor_de_fondo,
    detener_servidor_ui_de_fondo,
    iniciar_api_en_hilo,
    iniciar_ui_estatica_en_hilo,
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


def test_servidor_ui_estatica_sirve_el_directorio_y_se_detiene_con_limpieza(
    tmp_path: Path,
) -> None:
    (tmp_path / "index.html").write_text("<html>hola</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('hola')", encoding="utf-8")

    estado = iniciar_ui_estatica_en_hilo(tmp_path)
    try:
        assert estado.hilo.is_alive()
        with urllib.request.urlopen(estado.url_base, timeout=1.0) as respuesta:
            assert b"hola" in respuesta.read()
        with urllib.request.urlopen(estado.url_base + "assets/app.js", timeout=1.0) as respuesta:
            assert b"console.log" in respuesta.read()
    finally:
        detener_servidor_ui_de_fondo(estado)

    # Igual que el servidor de dlv-api: cerrar la ventana no puede dejar un
    # servidor de ficheros estaticos huerfano escuchando en el puerto.
    assert not estado.hilo.is_alive()


def test_detectar_dist_ui_encuentra_index_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr("dlv_app.main._DIST_UI", tmp_path)

    assert _detectar_dist_ui() == tmp_path


def test_detectar_dist_ui_devuelve_none_si_no_hay_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dlv_app.main._DIST_UI", tmp_path / "no-existe")

    assert _detectar_dist_ui() is None
