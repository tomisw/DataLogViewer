"""Servidor de comandos de `dlv-api` (ADR-007).

El frontend (`dlv-ui`) habla con `dlv-core` por HTTP sobre `127.0.0.1`, con un
puerto efímero elegido al arrancar y un token de sesión aleatorio que las
peticiones subsiguientes deberán presentar. `/salud` es una excepción
deliberada: no exige el token, porque es el endpoint que un contenedor
(`dlv-app`) o un script de arranque usan para saber si el servidor ya está
listo, antes incluso de haber leído el token.

COMANDOS TIPADOS (tarea F1-21)
===============================
`/comandos/abrir-cabecera` es el primer comando protegido por token, y
demuestra el patrón que seguirán los demás: cuerpo y respuesta son modelos de
Pydantic (`ComandoAbrirCabecera`/`RespuestaAbrirCabecera`), no JSON sin
tipar. Deliberadamente NO envía series de datos (ADR-007: "las series nunca
viajan en JSON"; eso es F1-22, transporte binario Arrow IPC/`TypedArray`) --
solo metadatos de cabecera (canales, avisos), que por volumen (kilobytes, no
73 M muestras) sí encajan en JSON según la propia ADR-007.

`dlv-api` sí puede tocar el sistema de ficheros (a diferencia de `dlv-core`,
ADR-002): es la capa de comandos, y "abrir un fichero que me pide el
frontend" es exactamente su trabajo. `dlv-core` sigue recibiendo bytes ya
leídos, nunca una ruta.

El descriptor de formato (`data/formats/haltech_nsp.toml`) se localiza hoy
relativo a este fichero fuente (`_RAIZ_REPO`), que funciona en el repositorio
de desarrollo pero no en un paquete `dlv-app` ya empaquetado (F5-01): cuando
llegue el empaquetado, ese dato tendrá que venir embebido en el ZIP portable
en vez de localizarse por ruta relativa al código fuente. Se deja anotado
aquí a propósito para que esa tarea no lo redescubra desde cero.
"""

from __future__ import annotations

import secrets
import socket
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from dlv_api import __version__ as version_dlv_api
from dlv_core import __version__ as version_dlv_core
from dlv_core.formatos.haltech import (
    Descriptor,
    ErrorDeFormato,
    cargar_descriptor,
    parsear_cabecera,
)
from dlv_core.informe_importacion import InformeImportacion

_RAIZ_REPO = Path(__file__).resolve().parents[3]
_DESCRIPTOR_HALTECH = _RAIZ_REPO / "data" / "formats" / "haltech_nsp.toml"


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


def verificar_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Dependencia de FastAPI: exige `Authorization: Bearer <token_sesion>`.

    Compara contra `request.app.state.token_sesion` (fijado en `crear_app`).
    `/salud` no usa esta dependencia a propósito (ver docstring del módulo);
    cualquier comando nuevo que toque datos del usuario sí debería.
    """
    esperado = f"Bearer {request.app.state.token_sesion}"
    if authorization != esperado:
        raise HTTPException(status_code=401, detail="token de sesión inválido o ausente")


@lru_cache(maxsize=1)
def _descriptor_haltech() -> Descriptor:
    """El único descriptor de formato nativo soportado hoy. Cacheado: es un
    TOML pequeño pero no hay motivo para reparsearlo en cada petición."""
    with _DESCRIPTOR_HALTECH.open("rb") as fh:
        return cargar_descriptor(fh)


class InfoCanal(BaseModel):
    """Metadatos de un canal (sin sus muestras: eso es F1-22, binario)."""

    id: int
    nombre: str
    dimension: str | None
    confianza: str


class RespuestaAbrirCabecera(BaseModel):
    """Respuesta tipada de `/comandos/abrir-cabecera`."""

    formato: str
    version: str
    n_canales: int
    canales: list[InfoCanal]
    avisos: list[str]


class ComandoAbrirCabecera(BaseModel):
    """Cuerpo tipado de `/comandos/abrir-cabecera`: qué fichero abrir."""

    ruta: str


def abrir_cabecera(comando: ComandoAbrirCabecera) -> RespuestaAbrirCabecera:
    """Parsea la cabecera de `comando.ruta` y devuelve sus metadatos.

    Solo la cabecera (F1-01), no el cuerpo: es el primer paso de la ruta de
    ingesta (docs/03 §3.4) y ya es útil por sí solo para que el frontend
    muestre qué canales tiene un log antes de pedir sus datos.
    """
    ruta = Path(comando.ruta)
    if not ruta.is_file():
        raise HTTPException(status_code=404, detail=f"no existe el fichero: {comando.ruta}")

    datos = ruta.read_bytes()
    try:
        cabecera = parsear_cabecera(datos, _descriptor_haltech())
    except ErrorDeFormato as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    informe = InformeImportacion()
    informe.agregar(cabecera.avisos)

    return RespuestaAbrirCabecera(
        formato=cabecera.formato,
        version=cabecera.version,
        n_canales=cabecera.n_canales,
        canales=[
            InfoCanal(id=c.id, nombre=c.nombre, dimension=c.dimension, confianza=c.confianza)
            for c in cabecera.canales
        ],
        avisos=informe.a_lineas(),
    )


def crear_app(*, token_sesion: str) -> FastAPI:
    """Construye la app de FastAPI.

    `token_sesion` se guarda en `app.state` para que futuros endpoints
    autenticados puedan comprobarlo; `/salud` no lo requiere.

    Registra las rutas con `add_api_route` en vez de `@app.get(...)`: es
    equivalente en FastAPI, y evita depender de la forma exacta del tipo del
    decorador, que solo se resuelve del todo cuando `fastapi` está instalado.
    """
    app = FastAPI(title="dlv-api")
    app.state.token_sesion = token_sesion
    app.add_api_route("/salud", salud, methods=["GET"])
    app.add_api_route(
        "/comandos/abrir-cabecera",
        abrir_cabecera,
        methods=["POST"],
        response_model=RespuestaAbrirCabecera,
        dependencies=[Depends(verificar_token)],
    )
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
