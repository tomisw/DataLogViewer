"""Punto de entrada de `dlv-app`: contenedor `pywebview` (ADR-002).

Arranca el servidor de `dlv-api` en un hilo de fondo (puerto efimero y token
de sesion, ADR-007) y abre una ventana `pywebview` que apunta al frontend.

Donde va el token (F1-35)
==========================
El token de sesion existe para que un proceso local ajeno no pueda hablar con
`dlv-api` solo por conocer el puerto (ADR-007, docstring de `dlv_api.main`).
Donde se lo pasamos al frontend importa:

- Si la ventana navega a una URL externa (servidor de desarrollo de Vite de
  `dlv-ui`, o el futuro `dlv-ui/dist/index.html` servido por algo que
  entienda HTTP), la unica via sin acoplar el frontend a codigo especifico de
  `pywebview` es la query string: `?puerto_api=...&token=...`. Es lo que ya
  lee `dlv-ui/src/main.ts` para `puerto_api` (ver ese fichero). La
  alternativa que ofrece `pywebview`, `js_api=` (expone un objeto Python
  invocable desde JavaScript sin tocar la URL ni el DOM), es mas segura pero
  solo funciona dentro de la ventana `pywebview`: un frontend abierto en un
  navegador normal -- la via movil que `docs/03-arquitectura.md` SS3.11
  compromete como "opcion A" (el telefono como cliente del backend) -- no
  tiene ese puente. Como esa portabilidad a navegador/movil es un requisito
  de ADR-002 y no solo un detalle de escritorio, este modulo usa la query
  string tambien para el caso `pywebview`, para no bifurcar el contrato del
  frontend segun quien abra la ventana.

  Implicacion de seguridad aceptada: el token queda visible en la URL
  (barra de direcciones si el motor la muestra, historial de navegacion del
  motor web embebido, capturas de pantalla). Se mitiga con lo que ya aporta
  ADR-007: el token es aleatorio, de un solo proceso, deja de servir en
  cuanto se para el servidor de fondo (ver `detener_servidor_de_fondo`), y el
  servidor solo escucha en 127.0.0.1. Si hiciera falta mas endurecimiento,
  `js_api` es la via a evaluar, pero exige que el frontend la use de forma
  explicita -- un cambio en `dlv-ui` fuera de alcance aqui (no hay Node/npm
  en esta maquina para escribirlo y probarlo, ver mas abajo).

- Si no hay ningun frontend externo al que apuntar (el caso por omision hoy,
  ver `_pagina_placeholder`), el token se inyecta directamente en el
  documento HTML servido localmente por `pywebview` (parametro `html=`, no
  `url=` de `webview.create_window`): no pasa por ninguna navegacion, asi que
  la exposicion anterior no aplica. Esta via solo cubre el placeholder de
  hoy, no un frontend real.

Que frontend se abre (F1-35, verificado de arranque en local)
================================================================
La nota original de F1-35 decia que esta maquina no tenia Node/npm y que
por tanto `main()` no tenia ningun frontend real al que apuntar. Eso ya no
es cierto: hay Node en `%LOCALAPPDATA%\\nodejs` y `dlv-ui/dist/` se genera
con `npm run build`. `main()` decide asi, en orden:

1. Con `url_frontend` explicito (p. ej. `"http://localhost:5173"` con
   `npm run dev` corriendo en `dlv-ui/`), la ventana navega ahi con
   `puerto_api`/`token` en la query string (ver la seccion anterior y
   `_url_con_credenciales`). Es el caso de desarrollo con recarga en
   caliente.
2. Si no se da `url_frontend` pero existe `dlv-ui/dist/index.html`
   (`_detectar_dist_ui`), se sirve esa carpeta por HTTP en 127.0.0.1 con
   otro servidor efimero de fondo (`iniciar_ui_estatica_en_hilo`) y la
   ventana navega ahi. Hace falta un servidor -- no basta con `file://`
   porque el `index.html` que genera Vite referencia sus assets con rutas
   absolutas (`/assets/...`), que `file://` no resuelve. Es el caso por
   omision hoy: `python -m dlv_app` sin argumentos sirve el build de
   produccion de `dlv-ui`.
3. Si no hay ni `url_frontend` ni `dlv-ui/dist/index.html` (p. ej. nunca se
   ha ejecutado `npm run build`), la ventana cae a la pagina placeholder
   embebida en este modulo (`_pagina_placeholder`), marcada explicitamente
   como provisional: solo demuestra que el arranque del servidor y el paso
   de credenciales al frontend funcionan de extremo a extremo, no es el
   frontend de `dlv-ui`.

Empaquetado con PyInstaller (F5-01): este modulo localiza `dlv-ui/dist/`
relativo al propio fichero fuente (`_RAIZ_REPO`, igual que `dlv_api.main`
localiza `data/`), lo que no sera valido bajo un `dlv_app.spec` congelado
-- ver el aviso ya anotado en ese fichero. No se toca aqui porque el
paquete congelado esta fuera del alcance de "que la app arranque en esta
maquina" y ya esta marcado como pendiente de F5-01.

Cierre limpio (F1-35)
======================
`preparar_servidor` (`dlv_api.main`) deja explicitamente en manos de quien
llama decidir donde correr el servidor; aqui se elige un hilo de fondo
`daemon=True` para poder abrir la ventana despues de arrancar. Un hilo daemon
no impide que el *proceso* termine, pero mientras el proceso siga vivo (p.
ej. en pruebas, o si `webview.start()` devuelve el control sin que el
proceso termine) dejaria el servidor -- y el puerto -- vivos. Por eso
`detener_servidor_de_fondo` fija `uvicorn.Server.should_exit` (la senal de
parada que uvicorn expone para pararse desde fuera de su propio bucle de
eventos) y espera (`Thread.join`) a que el hilo termine, y `main()` la llama
en un `finally` alrededor de `webview.start()` para que corra tambien si la
ventana se cierra por una excepcion, no solo por el cierre normal.
"""

from __future__ import annotations

import http.server
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
import webview

from dlv_api.main import ServidorArrancado, preparar_servidor

HOST_LOCAL = "127.0.0.1"

# `parents[3]` desde `dlv-app/src/dlv_app/main.py`: [0]=dlv_app, [1]=src,
# [2]=dlv-app, [3]=raiz del repositorio. Misma cuenta que usa
# `dlv_api.main._RAIZ_REPO` para `data/`; ver el aviso de F5-01 en el
# docstring del modulo sobre por que esto no es valido bajo PyInstaller.
_RAIZ_REPO = Path(__file__).resolve().parents[3]
_DIST_UI = _RAIZ_REPO / "dlv-ui" / "dist"

# Plantilla de la pagina placeholder (ver `_pagina_placeholder`). Se sustituye
# con `str.replace` en vez de un f-string para no tener que escapar las llaves
# de JavaScript (`{ }` de los bloques de funcion) como `{{ }}` en cada linea.
_PLANTILLA_PLACEHOLDER = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>DataLogViewer (placeholder provisional)</title>
</head>
<body>
  <h1>dlv-app -- PLACEHOLDER PROVISIONAL (tarea F1-35)</h1>
  <p>
    Esta pagina NO es el frontend de <code>dlv-ui</code>: esta maquina no
    tiene Node/npm instalados, asi que no existe <code>dlv-ui/dist/</code>
    que servir ni forma de levantar <code>npm run dev</code> para probar
    contra el. Solo demuestra que <code>dlv-api</code> arranca en segundo
    plano y que el puerto/token llegan hasta el frontend.
  </p>
  <p>dlv-api escucha en <code>__URL_BASE__</code>.</p>
  <p id="estado">Consultando /salud...</p>
  <script>
    // PROVISIONAL: un frontend real usaria este token como cabecera
    // "Authorization: Bearer <token>" en las llamadas a /comandos/* (ADR-007).
    // Esta pagina no llama a ningun endpoint protegido; solo deja constancia
    // de que el token llega aqui sin pasar por ninguna URL navegable (a
    // diferencia de la via usada para un frontend externo, ver el docstring
    // del modulo).
    window.__DLV_TOKEN__ = "__TOKEN__";
    window.__DLV_PUERTO_API__ = __PUERTO__;

    fetch("__URL_SALUD__")
      .then(function (respuesta) { return respuesta.json(); })
      .then(function (salud) {
        document.getElementById("estado").textContent =
          "dlv-api: " + salud.estado +
          " (api " + salud.version_api + ", core " + salud.version_core + ")";
      })
      .catch(function (error) {
        document.getElementById("estado").textContent =
          "error al consultar /salud: " + error;
      });
  </script>
</body>
</html>
"""


def _esperar_servidor(info: ServidorArrancado, *, timeout_s: float = 5.0) -> None:
    """Sondea `/salud` hasta que el servidor responde, o hasta agotar `timeout_s`.

    `/salud` no exige el token de sesion (ver `dlv_api.main.crear_app`), asi
    que este sondeo no necesita conocerlo todavia.
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


@dataclass(slots=True, frozen=True)
class ServidorDeFondo:
    """Lo que hace falta para hablar con `dlv-api` y para pararlo con limpieza.

    Agrupa `ServidorArrancado` (host/puerto/token: lo que necesita el
    frontend) junto con el objeto `uvicorn.Server` y el `threading.Thread` en
    el que corre -- lo que necesita `detener_servidor_de_fondo` para el
    cierre limpio (ver su docstring).
    """

    info: ServidorArrancado
    servidor: uvicorn.Server
    hilo: threading.Thread


def iniciar_api_en_hilo(*, host: str = HOST_LOCAL) -> ServidorDeFondo:
    """Arranca `dlv-api` en un hilo de fondo (daemon) y espera a que responda.

    Usa `preparar_servidor` (que deliberadamente no bloquea, ver su
    docstring en `dlv_api.main`) y ejecuta `servidor.run(...)` en un hilo
    propio para poder abrir la ventana de `pywebview` despues de arrancar.
    """
    servidor, sock, info = preparar_servidor(host=host)
    hilo = threading.Thread(target=servidor.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    _esperar_servidor(info)
    return ServidorDeFondo(info=info, servidor=servidor, hilo=hilo)


def detener_servidor_de_fondo(estado: ServidorDeFondo, *, timeout_s: float = 5.0) -> None:
    """Para el servidor de fondo con limpieza (ver "Cierre limpio" en el
    docstring del modulo).

    `should_exit` es una simple asignacion de atributo, segura de fijar
    desde un hilo distinto al que corre el bucle de eventos de uvicorn (sin
    necesitar un lock): es la senal de parada que el propio uvicorn sondea
    periodicamente. `hilo.join(timeout_s)` espera a que el bucle la note y
    termine antes de devolver el control a quien llama.
    """
    estado.servidor.should_exit = True
    estado.hilo.join(timeout=timeout_s)


def _url_con_credenciales(
    url_frontend: str, info: ServidorArrancado, log: str | None = None
) -> str:
    """Anade `puerto_api`, `token` y (si lo hay) `log` a `url_frontend` como
    parametros de consulta, preservando los que ya tuviera la URL.

    Ver la seccion "Donde va el token" en el docstring del modulo para la
    justificacion de esta via y sus implicaciones de seguridad.

    `log` es el tercer parametro que `dlv-ui/src/main.ts` necesita para hablar
    con el backend de verdad: con `puerto_api` y `token` pero sin `log`, el
    frontend no sabe QUE abrir y cae a su fuente sintetica. Esa caida es
    deliberada y util (permite trabajar en la interfaz sin log), pero sin este
    parametro seria la unica opcion posible y la ventana nunca ensenaria un log
    real.
    """
    partes = urllib.parse.urlsplit(url_frontend)
    consulta = urllib.parse.parse_qsl(partes.query)
    consulta += [("puerto_api", str(info.puerto)), ("token", info.token_sesion)]
    if log is not None:
        consulta.append(("log", log))
    return urllib.parse.urlunsplit(partes._replace(query=urllib.parse.urlencode(consulta)))


def _pagina_placeholder(info: ServidorArrancado) -> str:
    """Pagina minima y explicitamente PROVISIONAL (ver "Que frontend se abre"
    en el docstring del modulo): no sustituye a `dlv-ui`, solo evita una
    ventana en blanco y demuestra que el arranque del servidor y el paso de
    credenciales al frontend funcionan de extremo a extremo.

    El token se inyecta en el documento via `html=` (no `url=`) de
    `webview.create_window`: no hay ninguna navegacion de por medio, asi que
    no queda expuesto en ninguna URL/historial.
    """
    url_salud = f"http://{info.host}:{info.puerto}/salud"
    return (
        _PLANTILLA_PLACEHOLDER.replace("__URL_BASE__", f"http://{info.host}:{info.puerto}")
        .replace("__URL_SALUD__", url_salud)
        .replace("__PUERTO__", str(info.puerto))
        .replace("__TOKEN__", info.token_sesion)
    )


def _detectar_dist_ui() -> Path | None:
    """`dlv-ui/dist` si `npm run build` ya se ha ejecutado, si no `None`.

    Solo comprueba `index.html`: es el fichero que Vite escribe al final de
    un build correcto, asi que su ausencia cubre tanto "nunca se ha
    compilado" como "el build a medias se interrumpio".
    """
    return _DIST_UI if (_DIST_UI / "index.html").is_file() else None


@dataclass(slots=True, frozen=True)
class ServidorUiDeFondo:
    """Lo que hace falta para hablar con el servidor estatico de `dlv-ui/dist`
    y para pararlo con limpieza -- el equivalente de `ServidorDeFondo` para
    ficheros estaticos en vez de para `dlv-api`.
    """

    host: str
    puerto: int
    servidor: http.server.ThreadingHTTPServer
    hilo: threading.Thread

    @property
    def url_base(self) -> str:
        return f"http://{self.host}:{self.puerto}/"


def _manejador_estatico(directorio: Path) -> type[http.server.SimpleHTTPRequestHandler]:
    """Manejador HTTP fijado a `directorio` sin usar `os.chdir` (que mutaria
    el directorio de trabajo de todo el proceso, no solo del hilo del
    servidor): `SimpleHTTPRequestHandler` acepta `directory=` desde Python
    3.7 justamente para este caso.

    Silencia tambien el log por peticion a stderr: es ruido en una app de
    escritorio sin consola (`console=False` en `dlv_app.spec`).
    """

    class _Manejador(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(directorio), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return _Manejador


def iniciar_ui_estatica_en_hilo(directorio: Path, *, host: str = HOST_LOCAL) -> ServidorUiDeFondo:
    """Sirve `directorio` (se espera `dlv-ui/dist`) por HTTP en un puerto
    efimero, en un hilo de fondo daemon -- mismo patron que
    `iniciar_api_en_hilo`.

    Hace falta un servidor HTTP y no basta `file://` porque el `index.html`
    que genera `vite build` referencia sus assets con rutas absolutas
    (`/assets/index-XXXX.js`), que un motor web solo resuelve contra un
    origen HTTP, no contra el sistema de ficheros.
    """
    servidor = http.server.ThreadingHTTPServer((host, 0), _manejador_estatico(directorio))
    puerto = servidor.server_address[1]
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return ServidorUiDeFondo(host=host, puerto=puerto, servidor=servidor, hilo=hilo)


def detener_servidor_ui_de_fondo(estado: ServidorUiDeFondo, *, timeout_s: float = 5.0) -> None:
    """Para el servidor estatico con limpieza: `shutdown()` (a diferencia de
    `should_exit` de uvicorn) es el mecanismo propio de
    `http.server.ThreadingHTTPServer` para romper `serve_forever()` desde
    otro hilo, y `server_close()` libera el socket para no dejarlo en
    `TIME_WAIT` ocupando el puerto.
    """
    estado.servidor.shutdown()
    estado.hilo.join(timeout=timeout_s)
    estado.servidor.server_close()


def main(*, url_frontend: str | None = None, log: str | None = None) -> None:
    """Arranca `dlv-api` y abre la ventana de `pywebview`.

    `log` es la ruta del fichero a abrir. Sin ella, la ventana arranca con la
    fuente sintetica del frontend: util para trabajar en la interfaz, pero no
    es un log de verdad. Con ella, `dlv-ui` habla con `dlv-api` y abre ese
    fichero -- que es el hito M1.

    Que frontend se abre, en orden (ver "Que frontend se abre" en el
    docstring del modulo para el porque de cada paso):

    1. `url_frontend` explicito -- p. ej. el servidor de desarrollo de Vite,
       `"http://localhost:5173"` con `npm run dev` corriendo.
    2. Si no, `dlv-ui/dist/` si `npm run build` ya se ejecuto: se sirve por
       HTTP en un puerto efimero propio (`iniciar_ui_estatica_en_hilo`).
    3. Si no hay ninguno de los dos, la pagina placeholder provisional
       (`_pagina_placeholder`).

    El arranque de los servidores y `webview.start()` (que bloquea hasta que
    se cierra la ultima ventana) estan en un `try`/`finally` para que los dos
    se paren tambien si `webview.start()` termina por una excepcion, no solo
    por el cierre normal de la ventana.
    """
    estado = iniciar_api_en_hilo(host=HOST_LOCAL)
    estado_ui: ServidorUiDeFondo | None = None
    try:
        if url_frontend is not None:
            webview.create_window(
                "DataLogViewer", url=_url_con_credenciales(url_frontend, estado.info, log)
            )
        else:
            directorio_dist = _detectar_dist_ui()
            if directorio_dist is not None:
                estado_ui = iniciar_ui_estatica_en_hilo(directorio_dist, host=HOST_LOCAL)
                webview.create_window(
                    "DataLogViewer",
                    url=_url_con_credenciales(estado_ui.url_base, estado.info, log),
                )
            else:
                webview.create_window("DataLogViewer", html=_pagina_placeholder(estado.info))
        webview.start()
    finally:
        if estado_ui is not None:
            detener_servidor_ui_de_fondo(estado_ui)
        detener_servidor_de_fondo(estado)


if __name__ == "__main__":
    main()
