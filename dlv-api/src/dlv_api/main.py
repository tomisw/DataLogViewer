"""Servidor de comandos de `dlv-api` (ADR-007).

El frontend (`dlv-ui`) habla con `dlv-core` por HTTP sobre `127.0.0.1`, con un
puerto efímero elegido al arrancar y un token de sesión aleatorio que las
peticiones subsiguientes deberán presentar. `/salud` es una excepción
deliberada: no exige el token, porque es el endpoint que un contenedor
(`dlv-app`) o un script de arranque usan para saber si el servidor ya está
listo, antes incluso de haber leído el token.
"""

from __future__ import annotations

import secrets
import socket
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI

from dlv_api import __version__ as version_dlv_api
from dlv_core import __version__ as version_dlv_core


def generar_token_sesion() -> str:
    """Token de sesión aleatorio, generado una vez al arrancar (ADR-007)."""
    return secrets.token_urlsafe(32)


def salud() -> dict[str, str]:
    """Cuerpo del endpoint `/salud`: versión de `dlv-api`, de `dlv-core` y estado."""
    return {
        "estado": "ok",
        "version_api": version_dlv_api,
        "version_core": version_dlv_core,
    }


def crear_app(*, token_sesion: str) -> FastAPI:
    """Construye la app de FastAPI.

    `token_sesion` se guarda en `app.state` para que futuros endpoints
    autenticados puedan comprobarlo; `/salud` no lo requiere.

    Registra la ruta con `add_api_route` en vez de `@app.get(...)`: es
    equivalente en FastAPI, y evita depender de la forma exacta del tipo del
    decorador, que solo se resuelve del todo cuando `fastapi` está instalado.
    """
    app = FastAPI(title="dlv-api")
    app.state.token_sesion = token_sesion
    app.add_api_route("/salud", salud, methods=["GET"])
    return app


@dataclass(slots=True, frozen=True)
class ServidorArrancado:
    """Lo que necesita quien arranca el servidor (p. ej. `dlv-app`) para hablar
    con él: dónde escucha y con qué token de sesión.
    """

    host: str
    puerto: int
    token_sesion: str


def _socket_efimero(host: str) -> socket.socket:
    """Reserva un puerto efímero libre en `host`.

    Se reserva con un socket que luego se le pasa a uvicorn tal cual (en vez
    de cerrarlo y volver a abrir el puerto por número), para no dejar una
    ventana de carrera en la que otro proceso pueda ocupar el mismo puerto.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, 0))
    return sock


def puerto_de(sock: socket.socket) -> int:
    """Puerto efectivamente asignado a un socket ya vinculado con puerto 0."""
    return int(sock.getsockname()[1])


def preparar_servidor(
    *, host: str = "127.0.0.1"
) -> tuple[uvicorn.Server, socket.socket, ServidorArrancado]:
    """Prepara la app, el puerto efímero y el token, sin bloquear.

    Deliberadamente no llama a `servidor.run()`: quien llama decide si lo
    ejecuta en el hilo actual (`servir`, más abajo) o en uno de fondo, que es
    lo que hace `dlv-app` para poder abrir la ventana después de arrancar.
    """
    token = generar_token_sesion()
    app = crear_app(token_sesion=token)
    sock = _socket_efimero(host)
    puerto = puerto_de(sock)
    config = uvicorn.Config(app, host=host, log_level="info")
    servidor = uvicorn.Server(config)
    return servidor, sock, ServidorArrancado(host=host, puerto=puerto, token_sesion=token)


def servir(*, host: str = "127.0.0.1") -> None:
    """Arranca uvicorn en `host` con puerto efímero y token de sesión nuevos.

    Bloquea el hilo actual (`uvicorn.Server.run`); quien quiera arrancarlo en
    segundo plano (`dlv-app`) usa `preparar_servidor` y lo ejecuta en su
    propio hilo.
    """
    servidor, sock, info = preparar_servidor(host=host)
    print(
        f"dlv-api escuchando en http://{info.host}:{info.puerto} - "
        f"token de sesion: {info.token_sesion}"
    )
    servidor.run(sockets=[sock])


if __name__ == "__main__":
    servir()
