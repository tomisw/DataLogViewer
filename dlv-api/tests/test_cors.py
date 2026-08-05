"""El contrato con el NAVEGADOR, que no se ve desde ningún cliente Python.

POR QUÉ ESTE FICHERO EXISTE
===========================
`dlv-api` y el frontend viven en dos orígenes HTTP distintos: los dos en
127.0.0.1, pero cada uno en su puerto efímero (ADR-007 para la API;
`dlv_app.main.iniciar_ui_estatica_en_hilo`, o el servidor de Vite en `:5173`,
para `dlv-ui`). Puerto distinto es origen distinto, así que **todo** lo que el
frontend pide pasa por CORS.

Lo que hace esto difícil de detectar es que ningún cliente que no sea un
navegador aplica CORS: `httpx`, `urllib`, `curl` y el `TestClient` de FastAPI
reciben la respuesta entera pase lo que pase. Un fallo de CORS solo se
manifiesta al abrir la aplicación de verdad, y se manifiesta como datos
ausentes, no como un error del servidor: en los registros de `dlv-api` la
petición sale con un 200 impecable.

Estas pruebas comprueban en `TestClient` las dos cabeceras que el navegador sí
mira, para que el fallo salte aquí y no en la ventana del usuario.

LAS DOS FORMAS DE ROMPERSE, Y CÓMO SE VEN
==========================================
1. **Sin preflight.** Los POST de `fuente-api.ts` mandan `Content-Type:
   application/json` y `Authorization: Bearer …`, que no son cabeceras
   "simples", así que el navegador antepone un `OPTIONS`. Sin middleware de
   CORS, FastAPI no tiene ninguna ruta `OPTIONS` registrada y responde 405: la
   petición real **nunca llega a salir**. Se ve como una aplicación que no
   carga nada en absoluto.

2. **Sin `Access-Control-Expose-Headers`.** Esta es la traicionera. La
   respuesta de `/comandos/cubos` es un binario mudo: los cinco arrays y nada
   más. Todo lo necesario para interpretarlo -- cuántos cubos hay
   (`X-Cubos`), dónde empieza el tiempo (`X-T-Origen`), qué factor de
   decimación es (`X-Factor`) -- viaja en cabeceras `X-*`. De una respuesta
   con CORS, el JavaScript solo puede leer siete cabeceras de una lista fija
   del estándar (`Content-Type`, `Content-Length`, …); cualquier otra es
   invisible salvo que el servidor la nombre en `Access-Control-Expose-Headers`.

   Sin esa cabecera, `respuesta.headers.get("X-Cubos")` devuelve `null` en el
   navegador y devuelve `"2636"` en cualquier prueba de Python. El frontend lo
   lee como cero cubos y no dibuja nada: **el log se abre, la lista de 475
   canales se rellena, y los paneles salen vacíos.** El servidor no se entera
   de nada y no hay ningún error que buscar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from dlv_api.main import crear_app, generar_token_sesion  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
LOG_CORTO = RAIZ / "samples" / "real" / "20260729_1859_Log2768.csv"

# Un origen de los que se dan de verdad: el servidor estático de `dlv-ui/dist`
# en un puerto efímero. El puerto cambia en cada arranque, así que lo que se
# comprueba es que la política acepta *cualquier* puerto de loopback.
ORIGEN_FRONTEND = "http://127.0.0.1:54321"


@pytest.fixture
def cliente(tmp_path: Path) -> Any:
    token = generar_token_sesion()
    app = crear_app(token_sesion=token, dir_cache=tmp_path)
    http = fastapi_testclient.TestClient(app)
    http.headers.update({"Authorization": f"Bearer {token}"})
    return http


def test_el_preflight_de_un_post_autenticado_se_responde(cliente: Any) -> None:
    """Sin esto la petición real ni siquiera se envía (forma de rotura 1)."""
    respuesta = cliente.options(
        "/comandos/abrir-log",
        headers={
            "Origin": ORIGEN_FRONTEND,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["access-control-allow-origin"] == ORIGEN_FRONTEND
    permitidas = respuesta.headers["access-control-allow-headers"].lower()
    assert "authorization" in permitidas
    assert "content-type" in permitidas


def test_un_origen_que_no_es_loopback_no_se_acepta(cliente: Any) -> None:
    """ADR-007: la API solo habla con quien corre en esta máquina. El puerto es
    efímero, así que la política no puede fijarlo; el host sí."""
    respuesta = cliente.options(
        "/comandos/abrir-log",
        headers={
            "Origin": "http://ejemplo.invalido",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert "access-control-allow-origin" not in respuesta.headers


def test_todas_las_cabeceras_x_de_cubos_son_legibles_desde_el_navegador(
    cliente: Any,
) -> None:
    """Forma de rotura 2: la que se manifiesta como paneles vacíos.

    No se comprueba una lista escrita a mano de cabeceras, sino que **toda**
    `X-*` que la respuesta traiga esté expuesta. Escrita al revés (una lista
    fija aquí), añadir mañana una cabecera nueva al endpoint la dejaría
    invisible para el navegador sin que ninguna prueba se quejara, que es
    exactamente cómo apareció este fallo.
    """
    abierto = cliente.post("/comandos/abrir-log", json={"ruta": str(LOG_CORTO)}).json()
    canal = next(c for c in abierto["canales"] if c["niveles"])

    respuesta = cliente.post(
        "/comandos/cubos",
        json={
            "id_sesion": abierto["id_sesion"],
            "canal_id": canal["id"],
            "t0": abierto["t_inicio"],
            "t1": abierto["t_fin"],
            "factor": canal["niveles"][-1]["factor"],
            "formato_binario": "crudo",
        },
        headers={"Origin": ORIGEN_FRONTEND},
    )
    assert respuesta.status_code == 200, respuesta.text

    expuestas = {
        c.strip().lower()
        for c in respuesta.headers.get("access-control-expose-headers", "").split(",")
    }
    traidas = {c.lower() for c in respuesta.headers if c.lower().startswith("x-")}
    assert traidas, "la respuesta de cubos tiene que traer cabeceras X-*"
    invisibles = traidas - expuestas
    assert not invisibles, (
        f"el navegador no puede leer {sorted(invisibles)}: el frontend las leería como "
        "ausentes y dibujaría cero cubos sin ningún error"
    )


def test_las_cabeceras_x_de_serie_tambien_son_legibles(cliente: Any) -> None:
    """`/comandos/serie` manda la dimensión y los factores de conversión por
    cabecera igual que cubos. Un factor invisible no vacía el trazo: lo dibuja
    con la escala equivocada, que es peor porque parece un dato."""
    abierto = cliente.post("/comandos/abrir-log", json={"ruta": str(LOG_CORTO)}).json()
    respuesta = cliente.post(
        "/comandos/serie",
        json={"ruta": str(LOG_CORTO), "canal_id": abierto["canales"][0]["id"]},
        headers={"Origin": ORIGEN_FRONTEND},
    )
    assert respuesta.status_code == 200, respuesta.text
    expuestas = {
        c.strip().lower()
        for c in respuesta.headers.get("access-control-expose-headers", "").split(",")
    }
    traidas = {c.lower() for c in respuesta.headers if c.lower().startswith("x-")}
    assert traidas
    assert not traidas - expuestas
