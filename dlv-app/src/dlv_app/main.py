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

Que frontend se abre, a falta de `dlv-ui/dist/` (F1-35)
=========================================================
`dlv-ui` es un proyecto Vite/TypeScript y esta maquina no tiene Node/npm
instalados: no hay manera de generar `dist/` ni de levantar `npm run dev`
aqui, y `dlv-ui/index.html` por si solo no sirve como pagina navegable (el
navegador no entiende `<script type="module" src="/src/main.ts">` sin que
Vite lo transpile primero). Con eso, `main()` no tiene ningun frontend real
al que apuntar por omision, asi que:

- Con `url_frontend` explicito (p. ej. `"http://localhost:5173"` una vez haya
  Node y `npm run dev` este corriendo en `dlv-ui/`, o la URL de un futuro
  `dlv-ui/dist/index.html` servido por HTTP), la ventana navega ahi con
  `puerto_api`/`token` en la query string (ver la seccion anterior y
  `_url_con_credenciales`).
- Con `url_frontend=None` (el valor por omision), la ventana carga una
  pagina placeholder embebida en este modulo (`_pagina_placeholder`),
  marcada explicitamente como provisional, que solo demuestra que el
  arranque del servidor y el paso de credenciales al frontend funcionan de
  extremo a extremo. No es el frontend de `dlv-ui` y no debe confundirse con
  el: hay que sustituirlo por la URL real en cuanto haya un entorno con Node.

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

import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

import uvicorn
import webview

from dlv_api.main import ServidorArrancado, preparar_servidor

HOST_LOCAL = "127.0.0.1"

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


def _url_con_credenciales(url_frontend: str, info: ServidorArrancado) -> str:
    """Anade `puerto_api` y `token` a `url_frontend` como parametros de
    consulta, preservando los que ya tuviera la URL.

    Ver la seccion "Donde va el token" en el docstring del modulo para la
    justificacion de esta via y sus implicaciones de seguridad.
    """
    partes = urllib.parse.urlsplit(url_frontend)
    consulta = urllib.parse.parse_qsl(partes.query)
    consulta += [("puerto_api", str(info.puerto)), ("token", info.token_sesion)]
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


def main(*, url_frontend: str | None = None) -> None:
    """Arranca `dlv-api` y abre la ventana de `pywebview`.

    Con `url_frontend=None` (por omision) se usa la pagina placeholder de
    `_pagina_placeholder`. Con una URL explicita (p. ej.
    `"http://localhost:5173"` para el servidor de desarrollo de Vite de
    `dlv-ui`, una vez haya Node en la maquina), la ventana navega ahi con
    `puerto_api`/`token` en la query string (`_url_con_credenciales`).

    El arranque del servidor y `webview.start()` (que bloquea hasta que se
    cierra la ultima ventana) estan en un `try`/`finally` para que
    `detener_servidor_de_fondo` corra tambien si `webview.start()` termina
    por una excepcion, no solo por el cierre normal de la ventana.
    """
    estado = iniciar_api_en_hilo(host=HOST_LOCAL)
    try:
        if url_frontend is None:
            webview.create_window("DataLogViewer", html=_pagina_placeholder(estado.info))
        else:
            webview.create_window(
                "DataLogViewer", url=_url_con_credenciales(url_frontend, estado.info)
            )
        webview.start()
    finally:
        detener_servidor_de_fondo(estado)


if __name__ == "__main__":
    main()
