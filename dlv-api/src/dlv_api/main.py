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

SESIONES DE LOG ABIERTO Y CUBOS (hueco de M1)
=============================================
`/comandos/serie` (F1-22) devuelve la serie COMPLETA de un canal y reparsea el
fichero en cada petición. Las dos cosas hacen inalcanzable el hito M1, así que
se añade el juego de comandos que el renderizador necesita de verdad:

    POST /comandos/abrir-log     abre el log UNA vez y devuelve `id_sesion`,
                                 los canales y, por canal, los `(factor,
                                 n_cubos)` de cada nivel de pirámide
    POST /comandos/cubos         los cubos de un nivel recortados a `[t0, t1]`,
                                 en Arrow IPC binario
    POST /comandos/cerrar-log    libera la memoria de una sesión
    GET  /comandos/sesiones      qué hay abierto y cuál es el tope

El ciclo de vida de "qué logs hay abiertos" vive en `dlv_api.sesiones`, que es
donde está documentado por qué la identidad de una sesión es la ruta y por qué
hay un tope de ocho. `/comandos/serie` se mantiene tal cual: F1-22 está cerrada
y revisada, y sigue siendo la forma más simple de sacar un canal entero para
una exportación o una prueba.

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

import os
import secrets
import socket
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from dlv_api import __version__ as version_dlv_api
from dlv_api.exportacion import (
    MEDIA_TYPE_CSV,
    MEDIA_TYPE_PARQUET,
    ColumnaAExportar,
    ErrorDeExportacion,
    exportar_csv,
    exportar_parquet,
)
from dlv_api.sesiones import (
    MAXIMO_SESIONES,
    CanalSesion,
    RegistroSesiones,
    SesionNoEncontrada,
    huella_descriptor,
    recortar_nivel,
)
from dlv_core import __version__ as version_dlv_core
from dlv_core.almacen import Storage, construir_desde_polars
from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, parsear_cuerpo
from dlv_core.formatos.haltech import (
    Descriptor,
    ErrorDeFormato,
    cargar_descriptor,
    parsear_cabecera,
)
from dlv_core.formatos.limpieza import nulificar_centinelas
from dlv_core.informe_importacion import InformeImportacion
from dlv_core.piramide import NivelPiramide
from dlv_core.roles import Rol, cargar_catalogo_roles
from dlv_core.transporte import (
    MEDIA_TYPE_ARROW_IPC,
    MEDIA_TYPE_CUBOS_CRUDO,
    cubos_a_arrow_ipc,
    cubos_a_binario,
    serie_a_arrow_ipc,
)
from dlv_core.unidades import (
    Afin,
    Catalogo,
    Clase,
    Conversion,
    ErrorDeUnidad,
    Reciproca,
    cargar_catalogo,
)

_RAIZ_REPO = Path(__file__).resolve().parents[3]
_DESCRIPTOR_HALTECH = _RAIZ_REPO / "data" / "formats" / "haltech_nsp.toml"
_UNITS_TOML = _RAIZ_REPO / "data" / "units.toml"
_ROLES_TOML = _RAIZ_REPO / "data" / "roles.toml"
_COMBUSTIBLES_TOML = _RAIZ_REPO / "data" / "combustibles.toml"

CABECERAS_EXPUESTAS = (
    "X-Factor",
    "X-Nivel",
    "X-T-Origen",
    "X-Cubos",
    "X-Indice-Inicio",
    "X-Dimension",
    "X-Storage",
    "X-Factor-A",
    "X-Factor-B",
    "X-Muestras",
)
"""Cabeceras `X-*` que el navegador tiene permiso para leer (ver `crear_app`).

Es la lista que va en `Access-Control-Expose-Headers`. Toda cabecera `X-*` que
cualquier endpoint devuelva tiene que estar aquí: una que falte no da error en
ningún sitio, simplemente llega como ausente al JavaScript. En
`/comandos/cubos` eso significa cero cubos y un panel vacío; en
`/comandos/serie`, un factor de conversión perdido y un trazo con la escala
equivocada. `dlv-api/tests/test_cors.py` compara esta lista contra las
cabeceras que las respuestas traen de verdad, para que añadir una nueva sin
apuntarla aquí falle en las pruebas y no en la ventana del usuario.
"""

VARIABLE_DIR_CACHE = "DLV_DIR_CACHE"
"""Variable de entorno que decide dónde se escriben los `.dlvcache`.

Existe para dos cosas concretas: que las pruebas no ensucien la carpeta del
usuario, y que el modo portable de §3.10 (la app no escribe nada fuera de su
carpeta) pueda apuntar la caché dentro del ZIP descomprimido sin tocar código.
"""


def directorio_cache_por_omision() -> Path:
    """Dónde van los `.dlvcache` si nadie dice otra cosa.

    **No junto al log**: escribir al lado del fichero de origen ensucia la
    carpeta del usuario y, en este repositorio, escribiría dentro de
    `samples/real/`, que no se toca. `~/.dlv/cache` es reversible (borrarla no
    pierde nada, solo tiempo) y no depende de dónde estén los logs.
    """
    del_entorno = os.environ.get(VARIABLE_DIR_CACHE)
    if del_entorno:
        return Path(del_entorno)
    return Path.home() / ".dlv" / "cache"


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


@lru_cache(maxsize=1)
def _catalogo_unidades() -> Catalogo:
    """El catálogo de unidades (F1-13), cacheado por el mismo motivo que el
    descriptor de formato: no cambia entre peticiones."""
    with _UNITS_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


@lru_cache(maxsize=1)
def _catalogo_combustibles() -> list[dict[str, object]]:
    """`data/combustibles.toml` en la forma que pide `SelectorCombustible`.

    Es un TOML plano de tres entradas, así que se lee aquí con `tomllib` en vez
    de dar a `dlv-core` un módulo entero para ello: no hay ninguna decisión que
    tomar sobre estos datos —ni conversión, ni resolución, ni validación
    cruzada— más allá de leerlos. La precedencia (usuario > canal del log >
    `por_omision`) sí es lógica, y ya vive en
    `dlv-ui/src/combustible/resolucion.ts`.

    `evidencia` no se sirve: es para quien revisa el fichero, no para la
    interfaz.
    """
    with _COMBUSTIBLES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    return [
        {
            "id": cid,
            "etiqueta": str(c.get("etiqueta", cid)),
            "estequiometria": float(c["estequiometria"]),
            "porOmision": bool(c.get("por_omision", False)),
        }
        for cid, c in bruto.get("combustibles", {}).items()
    ]


@lru_cache(maxsize=1)
def _catalogo_roles() -> dict[str, Rol]:
    """El catálogo de roles semánticos de `data/roles.toml` (FG-09).

    Se sirve desde aquí, y no se duplica en el frontend, por la regla 2 de
    `CLAUDE.md`: `data/*.toml` son datos del propietario.
    """
    with _ROLES_TOML.open("rb") as fh:
        return cargar_catalogo_roles(fh)


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


class ComandoSerie(BaseModel):
    """Cuerpo tipado de `/comandos/serie`: qué fichero y qué canal."""

    ruta: str
    canal_id: int


def serie(comando: ComandoSerie) -> Response:
    """Devuelve `(t, v)` de un canal como Arrow IPC binario (tarea F1-22).

    ADR-007: las series nunca viajan en JSON. El cuerpo de la respuesta es
    100% binario (`dlv_core.transporte.serie_a_arrow_ipc`); los metadatos que
    el frontend necesita para interpretarlo (dimensión, factor de conversión,
    tipo de almacenamiento, número de muestras) van en cabeceras HTTP, no en
    el cuerpo, para no mezclar JSON y binario en una sola respuesta.

    Repite el *pipeline* completo (cabecera -> cuerpo -> limpieza -> almacén)
    en cada petición, sin caché de log abierto entre peticiones: eso es F1-11
    (caché Parquet) del lado de `dlv-core`, y una futura tarea de sesión de
    servidor si hace falta mantener logs abiertos en memoria entre
    peticiones -- fuera de alcance de F1-22, que es el transporte, no el
    ciclo de vida de qué hay abierto.
    """
    ruta = Path(comando.ruta)
    if not ruta.is_file():
        raise HTTPException(status_code=404, detail=f"no existe el fichero: {comando.ruta}")

    datos = ruta.read_bytes()
    try:
        cabecera = parsear_cabecera(datos, _descriptor_haltech())
    except ErrorDeFormato as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    canal = cabecera.por_id(comando.canal_id)
    if canal is None:
        raise HTTPException(status_code=404, detail=f"no existe el canal {comando.canal_id}")

    crudo = parsear_cuerpo(datos, cabecera)
    limpio = nulificar_centinelas(crudo, _catalogo_unidades())
    storage_por_columna = {
        columna_polars(c.columna): Storage.INT32_SCALED for c in cabecera.canales
    }
    series = construir_desde_polars(
        limpio, cabecera, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage_por_columna
    )
    serie_canal = next((s for s in series if s.key.id_nativo == str(canal.id)), None)
    if serie_canal is None:
        # No debería pasar (el canal existe en la cabecera), pero una fila de
        # datos con menos columnas de las declaradas podría dejarlo sin
        # columna en el cuerpo; mejor un 500 explícito que un StopIteration.
        raise HTTPException(
            status_code=500, detail=f"el canal {comando.canal_id} no tiene datos en el cuerpo"
        )

    cuerpo = serie_a_arrow_ipc(serie_canal.t, serie_canal.v)
    return Response(
        content=cuerpo,
        media_type=MEDIA_TYPE_ARROW_IPC,
        headers={
            "X-Dimension": serie_canal.dimension or "",
            "X-Factor-A": repr(serie_canal.to_canon.a),
            "X-Factor-B": repr(serie_canal.to_canon.b),
            "X-Storage": serie_canal.storage.name,
            "X-Muestras": str(len(serie_canal.t)),
        },
    )


# --------------------------------------------------------------------------- #
# Sesiones de log abierto y cubos por rango
# --------------------------------------------------------------------------- #
class ComandoAbrirLog(BaseModel):
    """Cuerpo de `/comandos/abrir-log`: qué fichero abrir."""

    ruta: str


class NivelCanal(BaseModel):
    """Un nivel de pirámide: `(factor, n_cubos)`.

    Es literalmente la interfaz `ResumenNivel` de
    `dlv-ui/src/render/escala.ts`, que es lo que `elegirNivel` necesita para
    decidir qué nivel pedir sin tener que pedir datos primero.
    """

    factor: int
    n_cubos: int


class InfoCanalSesion(BaseModel):
    """Un canal de un log ya abierto, con lo que hace falta para dibujarlo."""

    id: int
    nombre: str
    dimension: str | None
    confianza: str
    storage: str
    factor_a: float
    """`a` de la conversión afín a unidad canónica (`v_canonica = a*v + b`).
    Va aquí y no aplicado a los datos por el mismo motivo que en
    `/comandos/serie`: ADR-004 quiere que cambiar de unidad sea un repintado."""
    factor_b: float
    n_muestras: int
    niveles: list[NivelCanal]
    """Vacío si el canal está declarado en la cabecera pero no tiene columna en
    el cuerpo: entonces no hay cubos que pedir, y el frontend puede decirlo en
    vez de dibujar un panel vacío sin explicación."""
    rol: str | None
    """Rol semántico asignado por `dlv_core.roles` (FG-09), o `None` si nada
    del catálogo se le parece lo bastante.

    Sirve para que el frontend sepa CUÁLES de los 475 canales de un log real
    son los que alguien quiere ver al abrirlo. Sin esto, el único criterio
    disponible es el orden del fichero, y en un log de Haltech las primeras
    columnas son diagnósticos de arranque (`Bootmode Reason`,
    `Memory Writes Pending`): abrir el log enseñaba ocho líneas rectas.

    **No es una verdad, es una conjetura sobre un nombre de columna**, por eso
    viaja con `confianza_rol` al lado. El propietario decidió que un rol mal
    asignado se corrige a mano y se guarda en un perfil."""
    confianza_rol: str | None
    """`EXACTA`, `INDEXADA` o `DIFUSA` (`dlv_core.roles.Confianza`), o `None`
    si no hay rol.

    Va separado del rol y no plegado dentro de él porque docs/07 §7.15 lo
    exige: una coincidencia DIFUSA es un parecido de cadenas por encima de un
    umbral, y no puede activar un detector crítico sin que el usuario la
    confirme. Quien reciba esto y solo mire `rol` estará tratando una
    corazonada como un hecho."""
    vacio: bool
    """El canal no tiene ni una muestra: estaba declarado en la cabecera pero
    su módulo no estaba presente en esa tirada (`IndiceCanal.vacio`, F1-07)."""
    constante: bool
    """Todas las muestras valen lo mismo. No es un error --un canal atascado en
    un valor es información real-- pero dibuja una línea recta, así que es lo
    que el selector necesita para no ofrecerlo antes que un canal con señal."""


class RespuestaAbrirLog(BaseModel):
    """Respuesta de `/comandos/abrir-log`. Solo metadatos: kilobytes, no
    series (ADR-007). Las series salen por `/comandos/cubos`, en binario."""

    id_sesion: str
    ruta: str
    formato: str
    version: str
    n_canales: int
    t_inicio: float
    t_fin: float
    desde_cache: bool
    """`True` si la sesión se reconstruyó desde el `.dlvcache` sin reparsear el
    log (ADR-005). Es el número que hay que mirar cuando la segunda apertura no
    cumple los 700 ms de §2.6."""
    reutilizada: bool
    """`True` si el log ya estaba abierto y se ha devuelto la misma sesión, sin
    tocar el disco."""
    sesiones_abiertas: int
    maximo_sesiones: int
    canales: list[InfoCanalSesion]
    avisos: list[str]


class ComandoCubos(BaseModel):
    """Cuerpo de `/comandos/cubos`: qué canal, de qué nivel y de qué tramo.

    El nivel se identifica **o** por su índice en la lista `niveles` que
    devolvió `/comandos/abrir-log` (`nivel`, que es justo lo que devuelve
    `elegirNivel` en el frontend) **o** por su factor de decimación (`factor`,
    que es lo que lleva dentro un `CubosContinuos` ya cacheado). Hay que dar
    exactamente uno: aceptar los dos a la vez obligaría a decidir cuál gana
    cuando no coinciden, y esa decisión no la puede acertar el servidor.
    """

    id_sesion: str
    canal_id: int
    t0: float
    """Borde izquierdo del tramo, en segundos desde el inicio del log."""
    t1: float
    """Borde derecho, en segundos. Puede caer fuera del log por los dos lados:
    el frontend pide con margen (F1-24) y eso es normal, no un error."""
    nivel: int | None = None
    factor: int | None = None
    formato_binario: Literal["arrow", "crudo"] = "arrow"
    """Cómo se serializa el cuerpo. ADR-007 admite las dos formas.

    `crudo` es un búfer de tipado fijo (`float32` little-endian, las cinco
    columnas seguidas) y es lo que consume el frontend: `dlv-ui` no tiene
    ninguna dependencia, y leer Arrow IPC en el navegador exigiría o la
    librería `apache-arrow` —una dependencia nueva, que no se añade sin
    preguntar— o un lector escrito a mano. Con `crudo`, cada columna es un
    `new Float32Array(buffer, i * n * 4, n)`: cero parseo.

    `arrow` sigue siendo el valor por omisión para no romper a nadie que ya lo
    consuma. Ver `dlv_core.transporte.cubos_a_binario`.
    """


class InfoSesion(BaseModel):
    """Una sesión abierta, tal como la lista `/comandos/sesiones`."""

    id_sesion: str
    ruta: str
    formato: str
    n_canales: int
    desde_cache: bool
    abierta_en: float


class RespuestaSesiones(BaseModel):
    sesiones: list[InfoSesion]
    maximo_sesiones: int


class ComandoCerrarLog(BaseModel):
    id_sesion: str


class RespuestaCerrarLog(BaseModel):
    cerrado: bool
    """`False` si no había ninguna sesión con ese id. No es un error: cerrar
    dos veces (p. ej. el usuario cierra la pestaña y luego el log) tiene que
    ser idempotente."""
    sesiones_abiertas: int


def _registro(request: Request) -> RegistroSesiones:
    registro: RegistroSesiones = request.app.state.registro_sesiones
    return registro


def _info_canal(canal: CanalSesion) -> InfoCanalSesion:
    """Recibe el canal, no su id: los IDs pueden repetirse dentro de una misma
    cabecera (`parsear_cabecera` avisa de ello, docs/01 §1.3), así que buscarlo
    por id en `por_id` describiría dos canales distintos con los mismos
    metadatos y nadie lo notaría."""
    return InfoCanalSesion(
        id=canal.id,
        nombre=canal.nombre,
        dimension=canal.dimension,
        confianza=canal.confianza,
        storage=canal.serie.storage.name,
        factor_a=canal.serie.to_canon.a,
        factor_b=canal.serie.to_canon.b,
        n_muestras=canal.n_muestras,
        niveles=[NivelCanal(factor=n.factor, n_cubos=n.n_cubos) for n in canal.niveles],
        rol=canal.rol,
        confianza_rol=canal.confianza_rol,
        vacio=canal.vacio,
        constante=canal.constante,
    )


def abrir_log(comando: ComandoAbrirLog, request: Request) -> RespuestaAbrirLog:
    """Abre un log y lo deja en memoria bajo un `id_sesion`.

    Es el comando que sustituye a "reparsear el fichero en cada petición":
    todo lo caro (cabecera, cuerpo, almacén, pirámides) ocurre aquí una vez, y
    `/comandos/cubos` ya solo recorta. Si el log ya estaba abierto y no ha
    cambiado en disco, devuelve la MISMA sesión sin tocar nada
    (`reutilizada=True`).
    """
    ruta = Path(comando.ruta)
    if not ruta.is_file():
        raise HTTPException(status_code=404, detail=f"no existe el fichero: {comando.ruta}")

    try:
        sesion, reutilizada = _registro(request).abrir(ruta)
    except ErrorDeFormato as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return RespuestaAbrirLog(
        id_sesion=sesion.id_sesion,
        ruta=str(sesion.ruta),
        formato=sesion.formato,
        version=sesion.version,
        n_canales=sesion.n_canales,
        t_inicio=sesion.t_inicio,
        t_fin=sesion.t_fin,
        desde_cache=sesion.desde_cache,
        reutilizada=reutilizada,
        sesiones_abiertas=len(_registro(request)),
        maximo_sesiones=_registro(request).maximo,
        canales=[_info_canal(c) for c in sesion.canales],
        avisos=list(sesion.avisos),
    )


def cubos(comando: ComandoCubos, request: Request) -> Response:
    """Los cubos de un nivel de pirámide recortados a `[t0, t1]`, en Arrow IPC.

    Cuerpo: cinco columnas `float32` -- `t, minimo, maximo, primero, ultimo` --
    que son exactamente los arrays de `CubosContinuos`
    (`dlv-ui/src/render/tipos.ts`). Los dos escalares que ese contrato pide
    además viajan en cabeceras, como ya hace `/comandos/serie` con la dimensión
    y el factor:

        X-Factor          factor de decimación del nivel (`CubosContinuos.factor`)
        X-Nivel           índice del nivel en la lista de `/comandos/abrir-log`
        X-T-Origen        segundos absolutos de `t[0] == 0` (`tOrigen`)
        X-Cubos           número de cubos devueltos
        X-Indice-Inicio   índice del primer cubo dentro del nivel completo
        X-Dimension, X-Storage, X-Factor-A, X-Factor-B   como en `/comandos/serie`

    Un recorte vacío (el tramo pedido cae fuera del log) es un 200 con cero
    filas, no un 404: pedir con margen por el borde del log es lo normal
    (F1-24 ensancha el rango visible), y convertirlo en error obligaría al
    frontend a distinguir "me equivoqué de sesión" de "he llegado al final".
    """
    if comando.t1 < comando.t0:
        raise HTTPException(
            status_code=422,
            detail=f"rango invertido: t1 ({comando.t1}) es anterior a t0 ({comando.t0})",
        )
    if (comando.nivel is None) == (comando.factor is None):
        raise HTTPException(
            status_code=422,
            detail="hay que dar exactamente uno de `nivel` (índice) o `factor` (decimación)",
        )

    try:
        sesion = _registro(request).obtener(comando.id_sesion)
    except SesionNoEncontrada as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    canal = sesion.por_id.get(comando.canal_id)
    if canal is None:
        raise HTTPException(
            status_code=404,
            detail=f"la sesión {comando.id_sesion} no tiene el canal {comando.canal_id}",
        )

    indice = _indice_de_nivel(canal.piramide, nivel=comando.nivel, factor=comando.factor)
    recorte = recortar_nivel(canal.t_segundos, canal.piramide[indice], t0=comando.t0, t1=comando.t1)

    columnas = (recorte.t, recorte.minimo, recorte.maximo, recorte.primero, recorte.ultimo)
    if comando.formato_binario == "crudo":
        cuerpo = cubos_a_binario(*columnas)
        media_type = MEDIA_TYPE_CUBOS_CRUDO
    else:
        cuerpo = cubos_a_arrow_ipc(*columnas)
        media_type = MEDIA_TYPE_ARROW_IPC
    return Response(
        content=cuerpo,
        media_type=media_type,
        headers={
            "X-Factor": str(recorte.factor),
            "X-Nivel": str(indice),
            "X-T-Origen": repr(recorte.t_origen),
            "X-Cubos": str(recorte.n_cubos),
            "X-Indice-Inicio": str(recorte.indice_inicio),
            "X-Dimension": canal.dimension or "",
            "X-Storage": canal.serie.storage.name,
            "X-Factor-A": repr(canal.serie.to_canon.a),
            "X-Factor-B": repr(canal.serie.to_canon.b),
        },
    )


def _conversion_json(conversion: Conversion) -> dict[str, object]:
    """La conversión de una unidad, en forma discriminada por `tipo`.

    POR QUÉ VIAJA LA CONVERSIÓN Y NO EL VALOR YA CONVERTIDO
    =======================================================
    ADR-004 quiere que cambiar de unidad sea un REPINTADO, no una petición: los
    cubos se cachean en canónica (`CacheDeCubos`, F1-24) y «cambiar de unidad no
    invalida nada». Si convirtiera el servidor, cada clic en el selector de
    unidad tiraría la caché y volvería a pedir varios megabytes por la red para
    multiplicar por una constante.

    Esta ruta servía hasta ahora la etiqueta y los decimales de cada unidad,
    pero **no** su conversión, así que el frontend tenía las unidades reales en
    el desplegable y ningún factor con el que aplicarlas: usaba una tabla
    cableada de mentira con tres dimensiones, y elegir cualquier otra unidad no
    hacía nada, en silencio. Este campo es el que faltaba.

    Las tres variantes van discriminadas por `tipo` y no aplanadas a un par
    `a`/`b`, porque NO son intercambiables: una recíproca no es lineal y una
    diferencia no se puede convertir con ella (`Reciproca._exige_punto`), y una
    parametrizada necesita un valor que no está en el catálogo sino en un canal
    del log. Aplanarlas obligaría al frontend a adivinar cuál es cuál, y la
    forma de equivocarse —convertir un Δ de λ como si fuera lineal— da un
    número plausible y falso.
    """
    if isinstance(conversion, Afin):
        return {"tipo": "afin", "a": conversion.a, "b": conversion.b}
    if isinstance(conversion, Reciproca):
        return {"tipo": "reciproca", "a": conversion.a}
    return {
        "tipo": "parametrizada",
        # El rol del canal que lleva el parámetro (la estequiometría, para
        # λ→AFR): el frontend lo necesita para saber a qué canal mirar, o para
        # ofrecer el selector de combustible cuando el log no lo trae.
        "parametroRol": conversion.parametro_rol,
        "aPorOmision": conversion.a_por_omision,
    }


def catalogo_unidades() -> dict[str, object]:
    """El catálogo de `data/units.toml` en la forma que pide el frontend.

    JSON y no binario, y eso es coherente con ADR-007, no una excepción: la
    regla dura es que **las series** nunca viajan en JSON. Esto son metadatos
    —unas decenas de dimensiones con sus unidades y presets, kilobytes— y es
    exactamente el caso para el que el ADR reserva JSON.

    Se sirve en vez de duplicar el catálogo en TypeScript porque `data/*.toml`
    son datos del propietario y la regla 2 de `CLAUDE.md` prohíbe trasladar sus
    valores al código. Antes de esta ruta, el frontend solo tenía catálogos
    ilustrativos de prueba; con ella, la aplicación conmuta °C↔°F↔K con los
    factores reales, que es la mitad del hito M1.

    Los nombres de campo se pasan a `camelCase` aquí y no en el frontend: la
    frontera entre `snake_case` de Python y `camelCase` de TypeScript tiene que
    estar en un sitio concreto, y el que serializa es el que la conoce.
    """
    catalogo = _catalogo_unidades()
    dimensiones = [
        {
            "id": d.id,
            "etiqueta": d.etiqueta,
            "unidadCanonica": d.unidad_canonica,
            "convertible": d.convertible,
            "mostrarEnCrudo": d.mostrar_en_crudo,
            "unidades": [
                {
                    "id": u.id,
                    "etiqueta": u.etiqueta,
                    "decimales": u.decimales,
                    "alias": list(u.alias),
                    "conversion": _conversion_json(u.conversion),
                }
                for u in d.unidades.values()
            ],
        }
        for d in catalogo.dimensiones.values()
    ]
    presets = [
        {
            "id": pid,
            "etiqueta": str(p.get("etiqueta", pid)),
            "unidades": dict(p.get("unidades", {})),
        }
        for pid, p in catalogo.presets.items()
    ]
    return {
        "dimensiones": dimensiones,
        "presets": presets,
        # Va aquí y no en una ruta propia porque es parte del mismo sistema: el
        # factor de la conversión `parametrizada` λ→AFR no está en el catálogo
        # de unidades —depende del combustible del depósito, no de la unidad—
        # pero sin él esa conversión no se puede aplicar. Servirlo aparte
        # obligaría a una segunda ida y vuelta para pintar el primer trazo.
        "combustibles": _catalogo_combustibles(),
        # El preset por omisión no lo decide esta ruta: sale del catálogo si lo
        # declara y, si no, del métrico, que es el que corresponde al locale de
        # la aplicación. Inventarlo aquí sería una opinión disfrazada de dato.
        "presetPorOmision": "metrico"
        if "metrico" in catalogo.presets
        else next(iter(catalogo.presets), ""),
    }


def _indice_de_nivel(
    piramide: list[NivelPiramide], *, nivel: int | None, factor: int | None
) -> int:
    """Índice del nivel pedido, o 422 con qué había disponible.

    El bucle recorre niveles (una docena para 5 M muestras), no cubos ni
    muestras. Un `factor` que no existe es un error del llamador que hay que
    enseñar con la lista real: el fallo silencioso alternativo -- coger el
    nivel más cercano -- dibujaría datos de otra escala sin decirlo, que es
    exactamente el defecto que la clave de `CacheDeCubos` incluye el nivel para
    no tener.
    """
    if nivel is not None:
        if not 0 <= nivel < len(piramide):
            raise HTTPException(
                status_code=422,
                detail=f"nivel {nivel} fuera de rango: la pirámide tiene {len(piramide)} niveles",
            )
        return nivel

    for indice, n in enumerate(piramide):
        if n.factor == factor:
            return indice
    disponibles = ", ".join(str(n.factor) for n in piramide)
    raise HTTPException(
        status_code=422,
        detail=f"no hay ningún nivel con factor {factor}; factores disponibles: {disponibles}",
    )


def sesiones_abiertas(request: Request) -> RespuestaSesiones:
    """Qué logs hay abiertos ahora mismo y cuántos caben.

    No lo necesita el dibujo; lo necesita cualquiera que se pregunte por qué la
    memoria del proceso está donde está, y el frontend para reconciliar su
    estado tras recargar la ventana sin volver a abrir ocho logs.
    """
    registro = _registro(request)
    return RespuestaSesiones(
        sesiones=[
            InfoSesion(
                id_sesion=s.id_sesion,
                ruta=str(s.ruta),
                formato=s.formato,
                n_canales=s.n_canales,
                desde_cache=s.desde_cache,
                abierta_en=s.abierta_en,
            )
            for s in registro
        ],
        maximo_sesiones=registro.maximo,
    )


def cerrar_log(comando: ComandoCerrarLog, request: Request) -> RespuestaCerrarLog:
    """Cierra una sesión y suelta su memoria (almacén + pirámides).

    Que no exista la sesión no es un error: ver `RespuestaCerrarLog.cerrado`.
    """
    registro = _registro(request)
    cerrado = registro.cerrar(comando.id_sesion)
    return RespuestaCerrarLog(cerrado=cerrado, sesiones_abiertas=len(registro))


# --------------------------------------------------------------------------- #
# Exportación de datos a CSV/Parquet con unidad declarada por columna (F4-12)
# --------------------------------------------------------------------------- #
class ComandoExportarDatos(BaseModel):
    """Cuerpo de `/comandos/exportar-datos`: qué sesión, qué canales, en qué
    formato y en qué unidad.

    Exporta la serie COMPLETA de cada canal (igual que `/comandos/serie`, no
    recortada a un rango visible): recortar por `[t0, t1]` es una extensión
    razonable pero queda fuera de esta tarea, que es la del módulo de
    exportación, no la del recorte por rango — ver el informe de F4-12.
    """

    id_sesion: str
    canales_ids: list[int]
    formato: Literal["csv", "parquet"]
    unidades: dict[int, str] | None = None
    """`canal_id -> unidad de destino`. Un canal ausente del diccionario (o
    `unidades=None`) se exporta en su unidad CANÓNICA, no en la que esté
    mostrando la interfaz en ese momento: `dlv-api` no sabe qué unidad tiene
    activa el frontend (ADR-004, la conversión de presentación vive en el
    navegador), así que quien pide la exportación es quien tiene que decir en
    qué unidad la quiere, igual que ya decide `canales_ids`."""
    referencia_kpa: float | None = None
    """Pasa a relativo los canales de presión (`docs/06` §6.6). No se aplica a
    ninguna otra dimensión: pedirlo para un canal que no sea `pressure` se
    ignora, no es un error, porque este campo es intencionadamente global a
    la petición y no por canal."""


def exportar_datos(comando: ComandoExportarDatos, request: Request) -> Response:
    """CSV o Parquet de los canales pedidos, con la unidad de cada columna
    declarada en el propio fichero (`dlv_api.exportacion`, ver su docstring
    para el porqué de cada decisión).

    Todos los canales pedidos tienen que compartir el mismo eje de tiempo
    (mismo grupo de muestreo, ADR-003): unir canales de grupos distintos en
    una sola tabla exige una política de interpolación o de unión que este
    comando no toma, porque no es suya la decisión — R4 de `docs/02` §2.8 es
    tajante en que el desfase entre segmentos nunca se interpola en silencio.
    Pedirlo da 422, no una tabla con huecos rellenados a ciegas.
    """
    try:
        sesion = _registro(request).obtener(comando.id_sesion)
    except SesionNoEncontrada as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if not comando.canales_ids:
        raise HTTPException(status_code=422, detail="hay que pedir al menos un canal")

    canales: list[CanalSesion] = []
    for canal_id in comando.canales_ids:
        canal = sesion.por_id.get(canal_id)
        if canal is None:
            raise HTTPException(
                status_code=404,
                detail=f"la sesión {comando.id_sesion} no tiene el canal {canal_id}",
            )
        canales.append(canal)

    primero = canales[0]
    for canal in canales[1:]:
        if canal.t_segundos is not primero.t_segundos:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"el canal {canal.id} no comparte el eje de tiempo del canal "
                    f"{primero.id}: exportar canales de grupos de muestreo distintos "
                    "en una sola tabla exige una política de unión o interpolación "
                    "que este comando no decide"
                ),
            )

    unidades_por_canal = comando.unidades or {}
    columnas = [
        ColumnaAExportar(
            nombre="t",
            valores=primero.t_segundos,
            clase=Clase.PUNTO,
            dimension_id="time",
        ),
        *(
            ColumnaAExportar(
                nombre=canal.nombre,
                valores=canal.serie.v,
                clase=Clase.PUNTO,
                dimension_id=canal.dimension,
                confianza=canal.confianza,
                to_canon=canal.serie.to_canon,
                unidad_destino=unidades_por_canal.get(canal.id),
                # Solo tiene sentido para `pressure`: `ColumnaAExportar` no
                # comprueba la dimensión, así que se filtra aquí y no se
                # cuela un `referencia_kpa` en un canal que no es de presión.
                referencia_kpa=comando.referencia_kpa if canal.dimension == "pressure" else None,
            )
            for canal in canales
        ),
    ]

    catalogo = _catalogo_unidades()
    try:
        if comando.formato == "csv":
            cuerpo = exportar_csv(columnas, catalogo=catalogo)
            media_type = MEDIA_TYPE_CSV
        else:
            cuerpo = exportar_parquet(columnas, catalogo=catalogo)
            media_type = MEDIA_TYPE_PARQUET
    except ErrorDeUnidad as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ErrorDeExportacion as e:
        # 501 y no 422 ni 500: lo que ha pedido el cliente es válido y esta
        # instalación no lo puede hacer (una versión de Polars sin
        # `write_parquet(metadata=...)`). Un 422 diría que la petición está mal y
        # un 500 dejaría llegar la traza al usuario en vez del mensaje que
        # explica qué actualizar.
        raise HTTPException(status_code=501, detail=str(e)) from e

    nombre_fichero = f"{Path(sesion.ruta).stem}.{comando.formato}"
    return Response(
        content=cuerpo,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre_fichero}"'},
    )


def crear_app(
    *,
    token_sesion: str,
    dir_cache: Path | None = None,
    maximo_sesiones: int = MAXIMO_SESIONES,
) -> FastAPI:
    """Construye la app de FastAPI.

    `token_sesion` se guarda en `app.state` para que los endpoints
    autenticados puedan comprobarlo; `/salud` no lo requiere.

    `dir_cache` es dónde se escriben los `.dlvcache` (ADR-005); `None` usa
    `directorio_cache_por_omision()`. Se puede fijar aquí, y no solo por
    variable de entorno, para que una prueba pueda darle un directorio
    temporal sin tocar el entorno del proceso.

    `maximo_sesiones` es el tope de logs abiertos a la vez; el porqué del ocho
    por omisión está en `dlv_api.sesiones`.

    Registra las rutas con `add_api_route` en vez de `@app.get(...)`: es
    equivalente en FastAPI, y evita depender de la forma exacta del tipo del
    decorador, que solo se resuelve del todo cuando `fastapi` está instalado.
    """
    app = FastAPI(title="dlv-api")
    # El frontend vive en un origen HTTP distinto al de esta API (puerto
    # efimero propio en ambos casos: el servidor de desarrollo de Vite en
    # `:5173`, o el servidor estatico efimero de `dlv-ui/dist` que arranca
    # `dlv_app.main.iniciar_ui_estatica_en_hilo`). Los POST autenticados
    # mandan cabeceras `Content-Type`/`Authorization` (`dlv-ui/src/datos/
    # fuente-api.ts`), que no son "simples" para CORS: el navegador antepone
    # un preflight `OPTIONS` que, sin este middleware, FastAPI responde con
    # 405 (no hay ruta `OPTIONS` registrada) y la petición real nunca sale.
    # Restringido a loopback (ADR-007: la API solo escucha en 127.0.0.1) en
    # cualquier puerto, porque el puerto es efimero y distinto cada arranque.
    #
    # `expose_headers` no es un detalle: de una respuesta con CORS, el
    # JavaScript solo puede leer siete cabeceras de una lista fija del
    # estándar. Las `X-*` de `/comandos/cubos` -- que son TODO lo que hace
    # interpretable un cuerpo binario mudo: cuántos cubos, dónde empieza el
    # tiempo, qué factor -- son invisibles sin nombrarlas aquí, y su ausencia
    # no da ningún error: `respuesta.headers.get("X-Cubos")` devuelve `null`,
    # el frontend lee cero cubos y los paneles salen vacíos con un 200 en el
    # registro del servidor. Ver `CABECERAS_EXPUESTAS` y `tests/test_cors.py`.
    #
    # `Content-Disposition` no es una `X-*` (por eso no vive en
    # `CABECERAS_EXPUESTAS`, que es la lista específica de esas) pero tampoco
    # está en las siete cabeceras "simples" que el estándar deja leer sin
    # exponerlas: sin esto, `/comandos/exportar-datos` (F4-12) sirve el
    # nombre de fichero sugerido y el frontend no puede leerlo con
    # `respuesta.headers.get(...)`, aunque la descarga en sí funcione igual.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[*CABECERAS_EXPUESTAS, "Content-Disposition"],
    )
    app.state.token_sesion = token_sesion
    app.state.registro_sesiones = RegistroSesiones(
        descriptor=_descriptor_haltech(),
        catalogo=_catalogo_unidades(),
        version_descriptor=huella_descriptor(_DESCRIPTOR_HALTECH),
        dir_cache=dir_cache if dir_cache is not None else directorio_cache_por_omision(),
        maximo=maximo_sesiones,
        catalogo_roles=_catalogo_roles(),
    )
    app.add_api_route("/salud", salud, methods=["GET"])
    app.add_api_route(
        "/comandos/abrir-cabecera",
        abrir_cabecera,
        methods=["POST"],
        response_model=RespuestaAbrirCabecera,
        dependencies=[Depends(verificar_token)],
    )
    app.add_api_route(
        "/comandos/serie",
        serie,
        methods=["POST"],
        dependencies=[Depends(verificar_token)],
    )
    app.add_api_route(
        "/comandos/abrir-log",
        abrir_log,
        methods=["POST"],
        response_model=RespuestaAbrirLog,
        dependencies=[Depends(verificar_token)],
    )
    app.add_api_route(
        "/comandos/cubos",
        cubos,
        methods=["POST"],
        dependencies=[Depends(verificar_token)],
    )
    app.add_api_route(
        "/comandos/sesiones",
        sesiones_abiertas,
        methods=["GET"],
        response_model=RespuestaSesiones,
        dependencies=[Depends(verificar_token)],
    )
    app.add_api_route(
        "/comandos/cerrar-log",
        cerrar_log,
        methods=["POST"],
        response_model=RespuestaCerrarLog,
        dependencies=[Depends(verificar_token)],
    )
    app.add_api_route(
        "/comandos/unidades",
        catalogo_unidades,
        methods=["GET"],
        dependencies=[Depends(verificar_token)],
    )
    app.add_api_route(
        "/comandos/exportar-datos",
        exportar_datos,
        methods=["POST"],
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
