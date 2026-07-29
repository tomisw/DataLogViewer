"""Punto de entrada de `dlv-app`: contenedor `pywebview` (ADR-002).

Arranca el servidor de `dlv-api` en un hilo de fondo (puerto efímero y token
de sesión, ADR-007) y abre una ventana apuntando al frontend `dlv-ui`.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request

import webview

from dlv_api.main import ServidorArrancado, preparar_servidor

HOST_LOCAL = "127.0.0.1"


def _esperar_servidor(info: ServidorArrancado, *, timeout_s: float = 5.0) -> None:
    """Sondea `/salud` hasta que el servidor responde, o hasta agotar `timeout_s`.

    `/salud` no exige el token de sesión (ver `dlv_api.main.crear_app`), así
    que este sondeo no necesita conocerlo todavía.
    """
    limite = time.monotonic() + timeout_s
    url = f"http://{info.host}:{info.puerto}/salud"
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.05)
    raise TimeoutError(f"dlv-api no respondio en {url} tras {timeout_s} s")


def iniciar_api_en_hilo(*, host: str = HOST_LOCAL) -> ServidorArrancado:
    """Arranca `dlv-api` en un hilo de fondo (daemon) y devuelve dónde escucha."""
    servidor, sock, info = preparar_servidor(host=host)
    hilo = threading.Thread(target=servidor.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    _esperar_servidor(info)
    return info


def main(*, url_frontend: str = "http://localhost:5173") -> None:
    """Arranca `dlv-api` y abre la ventana de `pywebview` sobre `url_frontend`.

    `url_frontend` apunta al servidor de desarrollo de `dlv-ui` (Vite) en
    desarrollo; en el paquete final apuntará al `index.html` estático
    empaquetado junto al ejecutable (`docs/03-arquitectura.md` §3.10). El
    puerto y el token de `dlv-api` se pasan como parámetros de consulta para
    que el frontend sepa a qué backend conectarse (ADR-007).
    """
    info = iniciar_api_en_hilo(host=HOST_LOCAL)
    url = f"{url_frontend}?puerto_api={info.puerto}&token={info.token_sesion}"
    webview.create_window("DataLogViewer", url=url)
    webview.start()


if __name__ == "__main__":
    main()
