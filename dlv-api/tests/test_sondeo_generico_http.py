"""Las cuatro rutas del sondeo de CSV genérico, por HTTP (tarea FG-18).

Qué prueba este fichero y qué no
=================================
Aquí solo está lo que **añade el transporte**: que las rutas existen con el
nombre que `dlv-ui/src/importacion/puerto.ts` va a pedir, que exigen el token
de sesión como los otros ocho comandos, que cada forma de rechazar una entrada
sale con su código de estado, y que la petición del paso 2 se puede construir
literalmente con la respuesta del paso 1 sin traducir nada por el camino.

La traducción de `dlv_core` al JSON —qué campo se llama cómo, qué se deja
fuera, y sobre todo que la confianza del rol sobreviva— se prueba en
`test_importacion_generica.py`, que no necesita FastAPI y por tanto se ejecuta
también donde no está instalado. Este fichero se salta con `importorskip`,
mismo patrón que `test_salud.py` y `test_abrir_cabecera.py`.

El viaje de ida y vuelta es el punto más delicado
==================================================
`sondearTiempo(referencia, formatoConfirmado)` manda de vuelta el objeto
`PropuestaFormato` que el paso 1 devolvió, con sus `Campo<T>` envueltos
(`{valor, origen}`) y sus nombres en `camelCase`. Si el servidor no aceptara esa
misma forma, el frontend tendría que desenvolver y volver a envolver cada campo,
y esa asimetría es la clase de detalle que alguien implementa mal una vez y
luego nadie recuerda por qué está. `test_el_paso_2_se_pide_con_la_respuesta_del
_paso_1_tal_cual` es lo que fija que no hace falta ninguna traducción.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from dlv_api.main import crear_app, generar_token_sesion  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
CSV_SIMPLE = GENERICOS / "01-coma-punto.csv"
CSV_ESPANOL = GENERICOS / "02-puntoycoma-coma.csv"
CSV_CON_UNIDADES = GENERICOS / "04-fila-de-unidades.csv"
TOKEN = "token-de-prueba"

RUTAS_DE_SONDEO = (
    "/comandos/sondear-formato",
    "/comandos/sondear-tiempo",
    "/comandos/sondear-canales",
)


@pytest.fixture
def cliente(tmp_path: Path) -> Any:
    app = crear_app(token_sesion=TOKEN, dir_cache=tmp_path)
    http = fastapi_testclient.TestClient(app)
    http.headers.update({"Authorization": f"Bearer {TOKEN}"})
    return http


def _formato(cliente: Any, ruta: Path) -> dict[str, Any]:
    """El paso 1 por HTTP, comprobando que salió bien."""
    respuesta = cliente.post("/comandos/sondear-formato", json={"ruta": str(ruta)})
    assert respuesta.status_code == 200, respuesta.text
    cuerpo: dict[str, Any] = respuesta.json()
    return cuerpo


# --------------------------------------------------------------------------- #
# El token: las cuatro rutas leen un fichero del usuario o un catálogo de `data/`
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ruta_api", RUTAS_DE_SONDEO)
def test_las_tres_rutas_de_sondeo_exigen_el_token(ruta_api: str, tmp_path: Path) -> None:
    """ADR-007. Abren un fichero cuya ruta manda el cliente, o sea que sin token
    serían un lector de ficheros arbitrarios escuchando en 127.0.0.1.

    El cuerpo que se manda es COMPLETO y válido a propósito: si le faltaran
    campos, un 422 de validación podría hacer pasar esta prueba sin que el token
    se estuviera comprobando en absoluto.
    """
    app = crear_app(token_sesion=generar_token_sesion(), dir_cache=tmp_path)
    sin_token = fastapi_testclient.TestClient(app)
    cuerpo = {
        "ruta": str(CSV_SIMPLE),
        "formato": _propuesta_de_formato(),
        "tiempo": _propuesta_de_tiempo(),
    }
    assert sin_token.post(ruta_api, json=cuerpo).status_code == 401


def test_la_ruta_de_roles_exige_el_token(tmp_path: Path) -> None:
    """Mismo criterio que `/comandos/unidades`, que también sirve un catálogo de
    `data/` y también lo exige."""
    app = crear_app(token_sesion=generar_token_sesion(), dir_cache=tmp_path)
    assert fastapi_testclient.TestClient(app).get("/comandos/roles").status_code == 401


# --------------------------------------------------------------------------- #
# Los tres pasos, encadenados como los encadena el asistente
# --------------------------------------------------------------------------- #
def test_el_paso_1_sirve_la_propuesta_y_la_previsualizacion(cliente: Any) -> None:
    cuerpo = _formato(cliente, CSV_ESPANOL)
    assert cuerpo["propuesta"]["delimitador"]["valor"] == ";"
    assert cuerpo["propuesta"]["decimal"]["valor"] == ","
    assert isinstance(cuerpo["filasPrevia"], list)
    assert isinstance(cuerpo["avisos"], list)


def test_el_paso_2_se_pide_con_la_respuesta_del_paso_1_tal_cual(cliente: Any) -> None:
    """Sin desenvolver ni renombrar nada: `formato` es literalmente
    `propuesta`.

    Es el contrato que hace usable `PuertoImportacion`: el frontend guarda la
    `PropuestaFormato` que recibió, deja que el usuario la edite, y la manda de
    vuelta. Si el servidor exigiera otra forma, habría que mantener dos
    conversiones a mano en TypeScript.
    """
    paso1 = _formato(cliente, CSV_SIMPLE)
    respuesta = cliente.post(
        "/comandos/sondear-tiempo",
        json={"ruta": str(CSV_SIMPLE), "formato": paso1["propuesta"]},
    )
    assert respuesta.status_code == 200, respuesta.text
    paso2 = respuesta.json()
    assert paso2["propuesta"]["clase"]["valor"] == "relativo"
    assert paso2["propuesta"]["columna"]["valor"] == 0
    assert paso2["valoresBrutos"][0] == "0.000"


def test_el_paso_3_se_pide_con_las_respuestas_de_los_dos_anteriores(cliente: Any) -> None:
    paso1 = _formato(cliente, CSV_CON_UNIDADES)
    paso2 = cliente.post(
        "/comandos/sondear-tiempo",
        json={"ruta": str(CSV_CON_UNIDADES), "formato": paso1["propuesta"]},
    ).json()
    respuesta = cliente.post(
        "/comandos/sondear-canales",
        json={
            "ruta": str(CSV_CON_UNIDADES),
            "formato": paso1["propuesta"],
            "tiempo": paso2["propuesta"],
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    canales = respuesta.json()["canales"]
    por_nombre = {c["nombreOriginal"]: c for c in canales}
    assert por_nombre["CLT"]["dimensionId"]["valor"] == "temperature"
    assert por_nombre["CLT"]["rol"]["rol"] == "coolant_temp"
    assert por_nombre["CLT"]["rol"]["confianza"] == "EXACTA"


def test_un_rol_difuso_sobrevive_al_json_de_verdad(cliente: Any, tmp_path: Path) -> None:
    """La misma comprobación de §7.15 que `test_importacion_generica.py`, pero
    después de pasar por la serialización de FastAPI.

    Va aquí también porque el riesgo no es solo construir mal el diccionario:
    un `response_model` mal puesto, o un modelo de Pydantic que declarara
    `rol: str | None`, recortaría los campos EN SILENCIO al serializar. Esa
    forma de perder la mitigación no la ve ninguna prueba del módulo puro.
    """
    ruta = tmp_path / "roles-mixtos.csv"
    ruta.write_bytes(
        b"Time,Coolant Temperatur,Knock Sensor 2 Knock Count\n"
        b"0.000,350.5,3\n0.050,351.0,3\n0.100,351.5,4\n0.150,352.0,4\n"
    )
    paso1 = _formato(cliente, ruta)
    paso2 = cliente.post(
        "/comandos/sondear-tiempo", json={"ruta": str(ruta), "formato": paso1["propuesta"]}
    ).json()
    canales = cliente.post(
        "/comandos/sondear-canales",
        json={"ruta": str(ruta), "formato": paso1["propuesta"], "tiempo": paso2["propuesta"]},
    ).json()["canales"]

    por_nombre = {c["nombreOriginal"]: c for c in canales}
    difusa = por_nombre["Coolant Temperatur"]["rol"]
    assert difusa["confianza"] == "DIFUSA"
    assert difusa["confirmado"] is False
    assert difusa["sinonimo"] == "Coolant Temperature"
    assert 0.85 <= difusa["parecido"] < 1.0

    indexada = por_nombre["Knock Sensor 2 Knock Count"]["rol"]
    assert indexada["confianza"] == "INDEXADA"
    assert indexada["indice"] == 2


# --------------------------------------------------------------------------- #
# `/comandos/roles`
# --------------------------------------------------------------------------- #
def test_la_ruta_de_roles_sirve_un_array_como_declara_el_puerto(cliente: Any) -> None:
    """`catalogoRoles(): Promise<readonly RolDeCatalogo[]>`: un array desnudo, no
    un objeto con la lista dentro. Se aparta de la forma de
    `/comandos/unidades` a propósito, porque el consumidor está ya escrito."""
    respuesta = cliente.get("/comandos/roles")
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert isinstance(cuerpo, list)
    assert cuerpo, "data/roles.toml tiene que llegar al frontend"
    por_id = {r["id"]: r for r in cuerpo}
    assert "coolant_temp" in por_id
    assert {"id", "dimensionId", "plausibleMin", "plausibleMax", "critico"} <= set(cuerpo[0])
    # No se comprueban las cifras: son dato del propietario con puerta G1
    # (`data/roles.toml`) y fijarlas aquí sería la segunda copia que esta ruta
    # existe para no tener.
    assert por_id["coolant_temp"]["dimensionId"] == "temperature"


# --------------------------------------------------------------------------- #
# Cada forma de rechazar una entrada, con su código
# --------------------------------------------------------------------------- #
def test_un_fichero_que_no_existe_da_404(cliente: Any) -> None:
    respuesta = cliente.post(
        "/comandos/sondear-formato", json={"ruta": str(RAIZ / "no-existe-de-verdad.csv")}
    )
    assert respuesta.status_code == 404


def test_un_fichero_que_no_es_una_tabla_da_422(cliente: Any, tmp_path: Path) -> None:
    """Delimitador consistente y ninguna fila mayoritariamente numérica: no es
    el CSV de un log. El `detail` conserva el mensaje de FG-03, que dice qué se
    ha mirado; un texto genérico obligaría a abrir los registros del servidor
    para saber qué le pasa al fichero de uno."""
    ruta = tmp_path / "agenda.csv"
    ruta.write_bytes(
        b"nombre,apellido,ciudad\nJuan,Perez,Madrid\nAna,Lopez,Sevilla\nEva,Ruiz,Vigo\n"
    )
    respuesta = cliente.post("/comandos/sondear-formato", json={"ruta": str(ruta)})
    assert respuesta.status_code == 422, respuesta.text
    assert "numéricas" in respuesta.json()["detail"]


def test_un_fichero_vacio_da_422(cliente: Any, tmp_path: Path) -> None:
    ruta = tmp_path / "vacio.csv"
    ruta.write_bytes(b"")
    respuesta = cliente.post("/comandos/sondear-formato", json={"ruta": str(ruta)})
    assert respuesta.status_code == 422


def test_un_fichero_demasiado_grande_da_413(tmp_path: Path) -> None:
    """413 y no 422: la petición está bien formada y lo que sobra es el fichero.

    El tope se le pasa a `crear_app` —es un parámetro, no un umbral cableado—
    para poder comprobar el código de estado sin escribir medio gigabyte.
    """
    app = crear_app(token_sesion=TOKEN, dir_cache=tmp_path, max_bytes_fichero=32)
    http = fastapi_testclient.TestClient(app)
    http.headers.update({"Authorization": f"Bearer {TOKEN}"})

    assert CSV_SIMPLE.stat().st_size > 32, "el corpus tiene que superar el tope de la prueba"
    respuesta = http.post("/comandos/sondear-formato", json={"ruta": str(CSV_SIMPLE)})
    assert respuesta.status_code == 413, respuesta.text
    assert "sondear" in respuesta.json()["detail"]

    # Y las otras dos rutas de sondeo tienen que rechazarlo igual: leer el
    # fichero es lo primero que hacen las tres.
    for ruta_api in RUTAS_DE_SONDEO[1:]:
        cuerpo = {
            "ruta": str(CSV_SIMPLE),
            "formato": _propuesta_de_formato(),
            "tiempo": _propuesta_de_tiempo(),
        }
        assert http.post(ruta_api, json=cuerpo).status_code == 413, ruta_api


def test_un_delimitador_sin_confirmar_da_422_en_los_pasos_2_y_3(
    cliente: Any, tmp_path: Path
) -> None:
    """El paso 1 puede devolver `delimitador: null` con un 200 (§7.4). Mandar
    esa propuesta sin tocarla al paso 2 es un error del cliente, no del
    fichero, y el mensaje dice exactamente qué falta elegir."""
    ruta = tmp_path / "una-columna.csv"
    ruta.write_bytes(b"RPM\n1000\n2000\n3000\n4000\n")
    paso1 = _formato(cliente, ruta)
    assert paso1["propuesta"]["delimitador"]["valor"] is None

    respuesta = cliente.post(
        "/comandos/sondear-tiempo", json={"ruta": str(ruta), "formato": paso1["propuesta"]}
    )
    assert respuesta.status_code == 422, respuesta.text
    assert "delimitador" in respuesta.json()["detail"]


def test_un_cuerpo_mal_formado_da_422_de_pydantic_y_no_un_500(cliente: Any) -> None:
    """Los `Campo<T>` se validan de verdad: un `filaDatos` que no es un número
    tiene que dar 422 en la frontera y no un `TypeError` dentro del sondeo."""
    paso1 = _formato(cliente, CSV_SIMPLE)
    formato = dict(paso1["propuesta"])
    formato["filaDatos"] = {"valor": "la primera", "origen": "confirmado"}
    respuesta = cliente.post(
        "/comandos/sondear-tiempo", json={"ruta": str(CSV_SIMPLE), "formato": formato}
    )
    assert respuesta.status_code == 422


def test_el_origen_confirmado_se_acepta_y_no_cambia_la_respuesta(cliente: Any) -> None:
    """`origen` es estado del asistente: el servidor lo valida y no lo lee.

    Se comprueba mandando la misma propuesta con todo marcado «confirmado»: el
    resultado tiene que ser idéntico. Si el servidor se comportara distinto
    según quién eligió el delimitador, el paso 2 daría un resultado distinto
    antes y después de que el usuario tocara un control sin cambiar el valor.
    """
    paso1 = _formato(cliente, CSV_SIMPLE)
    como_llego = paso1["propuesta"]
    confirmado = {
        nombre: {"valor": campo["valor"], "origen": "confirmado"}
        for nombre, campo in como_llego.items()
    }
    a = cliente.post(
        "/comandos/sondear-tiempo", json={"ruta": str(CSV_SIMPLE), "formato": como_llego}
    ).json()
    b = cliente.post(
        "/comandos/sondear-tiempo", json={"ruta": str(CSV_SIMPLE), "formato": confirmado}
    ).json()
    assert a == b


# --------------------------------------------------------------------------- #
# Que añadir cuatro rutas no ha tocado las ocho que ya había
# --------------------------------------------------------------------------- #
def test_las_rutas_de_haltech_siguen_registradas(tmp_path: Path) -> None:
    """Los ocho comandos anteriores estaban cerrados y revisados. Esta prueba
    es barata y descarta de un golpe que el registro de las cuatro nuevas haya
    desplazado o pisado alguna.

    Se mira `app.routes` directamente y no a través del cliente: la app es lo
    que hay que inspeccionar, y así no se depende de qué atributos expone el
    `TestClient` de la versión de Starlette que haya instalada.
    """
    app = crear_app(token_sesion=TOKEN, dir_cache=tmp_path)
    caminos = {getattr(r, "path", None) for r in app.routes}
    assert {
        "/salud",
        "/comandos/abrir-cabecera",
        "/comandos/serie",
        "/comandos/abrir-log",
        "/comandos/cubos",
        "/comandos/sesiones",
        "/comandos/cerrar-log",
        "/comandos/unidades",
        "/comandos/exportar-datos",
        *RUTAS_DE_SONDEO,
        "/comandos/roles",
    } <= caminos


def test_el_preflight_de_las_rutas_nuevas_se_responde(cliente: Any) -> None:
    """Los POST del asistente mandan `Content-Type` y `Authorization`, que no son
    cabeceras «simples»: sin preflight resuelto la petición real no sale del
    navegador y no se ve ningún error en el servidor (ver `test_cors.py`)."""
    for ruta_api in RUTAS_DE_SONDEO:
        respuesta = cliente.options(
            ruta_api,
            headers={
                "Origin": "http://127.0.0.1:54321",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )
        assert respuesta.status_code == 200, f"{ruta_api}: {respuesta.text}"
        assert respuesta.headers["access-control-allow-origin"] == "http://127.0.0.1:54321"


def _propuesta_de_formato() -> dict[str, Any]:
    """Una `PropuestaFormato` válida en forma, sin sondear nada.

    Sirve para las pruebas en las que la petición se rechaza ANTES de mirar el
    formato —sin token, o fichero demasiado grande—: el cuerpo tiene que pasar
    la validación de Pydantic para que el código que salga sea el que se está
    comprobando y no un 422 de campos que faltan.
    """
    return {
        "codificacion": {"valor": "utf-8", "origen": "confirmado"},
        "delimitador": {"valor": ",", "origen": "confirmado"},
        "comilla": {"valor": None, "origen": "confirmado"},
        "decimal": {"valor": ".", "origen": "confirmado"},
        "filaCabecera": {"valor": 0, "origen": "confirmado"},
        "filaUnidades": {"valor": None, "origen": "confirmado"},
        "filaDatos": {"valor": 1, "origen": "confirmado"},
    }


def _propuesta_de_tiempo() -> dict[str, Any]:
    """Una `PropuestaTiempo` válida en forma, para el mismo uso que la anterior."""
    return {
        "clase": {"valor": "relativo", "origen": "confirmado"},
        "columna": {"valor": 0, "origen": "confirmado"},
        "columnaFecha": {"valor": None, "origen": "confirmado"},
        "frecuenciaHz": {"valor": None, "origen": "confirmado"},
        "factorASegundos": 1.0,
    }
