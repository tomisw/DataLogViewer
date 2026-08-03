"""Los comandos de sesión y cubos por HTTP: `/comandos/abrir-log`,
`/comandos/cubos`, `/comandos/sesiones` y `/comandos/cerrar-log`.

Lo que se comprueba aquí es el CONTRATO con el frontend, que es lo que no se
puede verificar desde `dlv-core`: que la respuesta de cubos es binaria y trae
las cinco columnas que `CubosContinuos` declara, que los metadatos que no
caben en el binario llegan en cabeceras `X-*`, que la lista de niveles es la
que `elegirNivel` necesita, y que abrir dos veces el mismo log no lo parsea dos
veces.

Todas las pruebas usan un directorio de caché temporal: sin él escribirían el
`.dlvcache` en la carpeta del usuario que ejecuta `pytest`.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from dlv_api.main import crear_app, generar_token_sesion  # noqa: E402
from dlv_core.transporte import COLUMNAS_CUBOS, arrow_ipc_a_cubos  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
AUTOLOG_REAL = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"
LOG_CORTO = RAIZ / "samples" / "real" / "20260729_1859_Log2768.csv"


class Cliente:
    """Cliente de pruebas con el token ya puesto en cada petición.

    Existe para que las pruebas no repitan la cabecera `Authorization` doce
    veces: repetirla invita a olvidarla en una prueba nueva, y una prueba que
    recibe un 401 por descuido pasa a ser una prueba que no prueba nada.
    """

    def __init__(self, dir_cache: Path, *, maximo_sesiones: int = 8) -> None:
        self.token = generar_token_sesion()
        self.app = crear_app(
            token_sesion=self.token, dir_cache=dir_cache, maximo_sesiones=maximo_sesiones
        )
        self.http = fastapi_testclient.TestClient(self.app)

    def post(self, ruta: str, cuerpo: dict[str, Any]) -> Any:
        return self.http.post(ruta, json=cuerpo, headers={"Authorization": f"Bearer {self.token}"})

    def get(self, ruta: str) -> Any:
        return self.http.get(ruta, headers={"Authorization": f"Bearer {self.token}"})

    def abrir(self, log: Path = AUTOLOG_REAL) -> dict[str, Any]:
        respuesta = self.post("/comandos/abrir-log", {"ruta": str(log)})
        assert respuesta.status_code == 200, respuesta.text
        cuerpo: dict[str, Any] = respuesta.json()
        return cuerpo


def _canal_con_datos(abierto: dict[str, Any]) -> dict[str, Any]:
    """El primer canal que tiene al menos dos niveles de pirámide: uno con un
    solo nivel no permite probar que el nivel pedido es el que se sirve."""
    for canal in abierto["canales"]:
        if len(canal["niveles"]) >= 2:
            return canal
    raise AssertionError("ningún canal del log de prueba tiene pirámide de dos niveles")


# --------------------------------------------------------------------------- #
# abrir-log
# --------------------------------------------------------------------------- #
def test_sin_token_devuelve_401(tmp_path: Path) -> None:
    cliente = Cliente(tmp_path)
    assert (
        cliente.http.post("/comandos/abrir-log", json={"ruta": str(AUTOLOG_REAL)}).status_code
        == 401
    )
    assert cliente.http.post("/comandos/cubos", json={}).status_code == 401
    assert cliente.http.get("/comandos/sesiones").status_code == 401
    assert cliente.http.post("/comandos/cerrar-log", json={}).status_code == 401


def test_abrir_devuelve_los_niveles_que_necesita_elegir_nivel(tmp_path: Path) -> None:
    """`elegirNivel` (dlv-ui/src/render/escala.ts) solo necesita `(factor,
    n_cubos)` por nivel, y los necesita ANTES de pedir datos: sin esto, el
    frontend no puede decidir qué nivel pedir sin pedir algo primero."""
    abierto = Cliente(tmp_path).abrir()

    assert abierto["n_canales"] == len(abierto["canales"]) > 0
    assert abierto["t_fin"] > abierto["t_inicio"]
    canal = _canal_con_datos(abierto)

    factores = [n["factor"] for n in canal["niveles"]]
    cubos = [n["n_cubos"] for n in canal["niveles"]]
    assert factores[0] == 1, "el primer nivel es L0, sin decimar"
    assert factores == sorted(factores) and cubos == sorted(cubos, reverse=True)
    # Factor 4 entre niveles consecutivos (docs/03 §3.5).
    assert all(b == a * 4 for a, b in pairwise(factores))
    assert cubos[0] == canal["n_muestras"]


def test_abrir_dos_veces_reutiliza_la_sesion(tmp_path: Path) -> None:
    """El hueco que este comando cierra: `/comandos/serie` reparseaba el
    fichero de 66 MB en CADA petición."""
    cliente = Cliente(tmp_path)
    primera = cliente.abrir()
    segunda = cliente.abrir()

    assert primera["reutilizada"] is False
    assert segunda["reutilizada"] is True
    assert primera["id_sesion"] == segunda["id_sesion"]
    assert segunda["sesiones_abiertas"] == 1


def test_abrir_un_fichero_inexistente_devuelve_404(tmp_path: Path) -> None:
    cliente = Cliente(tmp_path)
    respuesta = cliente.post("/comandos/abrir-log", {"ruta": str(RAIZ / "no-existe.csv")})
    assert respuesta.status_code == 404


def test_abrir_algo_que_no_es_un_log_devuelve_422(tmp_path: Path) -> None:
    basura = tmp_path / "basura.csv"
    basura.write_text("esto no es un log de Haltech\n", encoding="utf-8")
    cliente = Cliente(tmp_path)
    assert cliente.post("/comandos/abrir-log", {"ruta": str(basura)}).status_code == 422


# --------------------------------------------------------------------------- #
# cubos
# --------------------------------------------------------------------------- #
def test_los_cubos_llegan_en_binario_con_las_cinco_columnas(tmp_path: Path) -> None:
    cliente = Cliente(tmp_path)
    abierto = cliente.abrir()
    canal = _canal_con_datos(abierto)

    respuesta = cliente.post(
        "/comandos/cubos",
        {
            "id_sesion": abierto["id_sesion"],
            "canal_id": canal["id"],
            "nivel": 1,
            "t0": abierto["t_inicio"],
            "t1": abierto["t_fin"],
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"] == "application/vnd.apache.arrow.stream"
    with pytest.raises(Exception):  # noqa: B017 - solo confirma que NO es JSON
        respuesta.json()

    columnas = arrow_ipc_a_cubos(respuesta.content)
    assert set(columnas) == set(COLUMNAS_CUBOS)
    n = int(respuesta.headers["x-cubos"])
    assert n == canal["niveles"][1]["n_cubos"], "el rango completo son todos los cubos del nivel"
    assert all(len(c) == n for c in columnas.values())
    assert all(c.dtype == np.float32 for c in columnas.values())

    # `minimo <= primero/ultimo <= maximo` en todos los cubos: es lo que hace
    # que la pirámide no pierda picos, y una permutación de columnas al
    # serializar lo rompería sin romper nada más.
    assert np.all(columnas["minimo"] <= columnas["maximo"])
    assert np.all(columnas["minimo"] <= columnas["primero"])
    assert np.all(columnas["primero"] <= columnas["maximo"])
    assert np.all(columnas["minimo"] <= columnas["ultimo"])
    assert np.all(columnas["ultimo"] <= columnas["maximo"])


def test_las_cabeceras_traen_lo_que_no_cabe_en_el_binario(tmp_path: Path) -> None:
    """`CubosContinuos` pide dos escalares además de los cinco arrays
    (`tOrigen` y `factor`), y el frontend necesita `(a, b)` para pasar a
    canónica. Todo eso va en cabeceras, como en `/comandos/serie`."""
    cliente = Cliente(tmp_path)
    abierto = cliente.abrir()
    canal = _canal_con_datos(abierto)

    respuesta = cliente.post(
        "/comandos/cubos",
        {
            "id_sesion": abierto["id_sesion"],
            "canal_id": canal["id"],
            "nivel": 1,
            "t0": abierto["t_inicio"],
            "t1": abierto["t_fin"],
        },
    )
    assert respuesta.headers["x-factor"] == str(canal["niveles"][1]["factor"])
    assert respuesta.headers["x-nivel"] == "1"
    assert respuesta.headers["x-indice-inicio"] == "0"
    assert float(respuesta.headers["x-t-origen"]) == pytest.approx(abierto["t_inicio"])
    assert respuesta.headers["x-storage"] == canal["storage"]
    assert float(respuesta.headers["x-factor-a"]) == canal["factor_a"]
    assert float(respuesta.headers["x-factor-b"]) == canal["factor_b"]
    assert respuesta.headers["x-dimension"] == (canal["dimension"] or "")


def test_el_tiempo_es_relativo_al_origen_que_dice_la_cabecera(tmp_path: Path) -> None:
    """`CubosContinuos.t` es relativo a `tOrigen` por precisión de `float32`.
    Si el servidor mandara instantes absolutos, un log largo temblaría al
    ampliar y nadie sabría por qué."""
    cliente = Cliente(tmp_path)
    abierto = cliente.abrir()
    canal = _canal_con_datos(abierto)
    medio = (abierto["t_inicio"] + abierto["t_fin"]) / 2

    respuesta = cliente.post(
        "/comandos/cubos",
        {
            "id_sesion": abierto["id_sesion"],
            "canal_id": canal["id"],
            "nivel": 1,
            "t0": medio,
            "t1": abierto["t_fin"],
        },
    )
    columnas = arrow_ipc_a_cubos(respuesta.content)
    t_origen = float(respuesta.headers["x-t-origen"])

    assert columnas["t"][0] == 0.0
    assert t_origen <= medio, "el primer cubo empieza en o antes del borde izquierdo"
    assert np.all(np.diff(columnas["t"]) > 0)
    # El último cubo servido cae dentro del log.
    assert t_origen + float(columnas["t"][-1]) <= abierto["t_fin"] + 1e-6


def test_pedir_por_factor_y_por_indice_da_lo_mismo(tmp_path: Path) -> None:
    cliente = Cliente(tmp_path)
    abierto = cliente.abrir()
    canal = _canal_con_datos(abierto)
    base = {
        "id_sesion": abierto["id_sesion"],
        "canal_id": canal["id"],
        "t0": abierto["t_inicio"],
        "t1": abierto["t_fin"],
    }
    por_indice = cliente.post("/comandos/cubos", {**base, "nivel": 1})
    por_factor = cliente.post("/comandos/cubos", {**base, "factor": canal["niveles"][1]["factor"]})
    assert por_indice.content == por_factor.content
    assert por_indice.headers["x-nivel"] == por_factor.headers["x-nivel"]


def test_un_rango_estrecho_devuelve_muchos_menos_cubos_que_el_log_entero(tmp_path: Path) -> None:
    """La razón de ser del endpoint: pedir lo visible, no la serie entera."""
    cliente = Cliente(tmp_path)
    abierto = cliente.abrir()
    canal = _canal_con_datos(abierto)
    duracion = abierto["t_fin"] - abierto["t_inicio"]

    entero = cliente.post(
        "/comandos/cubos",
        {
            "id_sesion": abierto["id_sesion"],
            "canal_id": canal["id"],
            "nivel": 0,
            "t0": abierto["t_inicio"],
            "t1": abierto["t_fin"],
        },
    )
    tramo = cliente.post(
        "/comandos/cubos",
        {
            "id_sesion": abierto["id_sesion"],
            "canal_id": canal["id"],
            "nivel": 0,
            "t0": abierto["t_inicio"] + duracion * 0.4,
            "t1": abierto["t_inicio"] + duracion * 0.5,
        },
    )
    n_entero = int(entero.headers["x-cubos"])
    n_tramo = int(tramo.headers["x-cubos"])
    assert 0 < n_tramo < n_entero / 5
    assert int(tramo.headers["x-indice-inicio"]) > 0
    assert len(tramo.content) < len(entero.content)


def test_un_rango_fuera_del_log_devuelve_cero_cubos_no_un_error(tmp_path: Path) -> None:
    """El frontend pide con margen (F1-24), así que salirse por el borde es
    normal. Un 404 aquí obligaría a distinguirlo de "sesión equivocada"."""
    cliente = Cliente(tmp_path)
    abierto = cliente.abrir()
    canal = _canal_con_datos(abierto)

    respuesta = cliente.post(
        "/comandos/cubos",
        {
            "id_sesion": abierto["id_sesion"],
            "canal_id": canal["id"],
            "nivel": 0,
            "t0": abierto["t_fin"] + 1_000.0,
            "t1": abierto["t_fin"] + 2_000.0,
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["x-cubos"] == "0"
    assert all(len(c) == 0 for c in arrow_ipc_a_cubos(respuesta.content).values())


def test_los_errores_del_llamador_son_422_con_lo_que_habia_disponible(tmp_path: Path) -> None:
    cliente = Cliente(tmp_path)
    abierto = cliente.abrir()
    canal = _canal_con_datos(abierto)
    base = {"id_sesion": abierto["id_sesion"], "canal_id": canal["id"], "t0": 0.0, "t1": 10.0}

    sin_nivel = cliente.post("/comandos/cubos", base)
    assert sin_nivel.status_code == 422

    ambos = cliente.post("/comandos/cubos", {**base, "nivel": 0, "factor": 1})
    assert ambos.status_code == 422

    fuera = cliente.post("/comandos/cubos", {**base, "nivel": 999})
    assert fuera.status_code == 422

    # Un factor que no existe se rechaza con la lista real en vez de servir el
    # nivel más cercano: datos de otra escala dibujados como si fueran los
    # pedidos es exactamente el fallo que no se nota.
    factor_falso = cliente.post("/comandos/cubos", {**base, "factor": 7})
    assert factor_falso.status_code == 422
    assert "7" in factor_falso.json()["detail"]

    invertido = cliente.post("/comandos/cubos", {**base, "nivel": 0, "t0": 100.0, "t1": 10.0})
    assert invertido.status_code == 422


def test_sesion_o_canal_inexistentes_devuelven_404(tmp_path: Path) -> None:
    cliente = Cliente(tmp_path)
    abierto = cliente.abrir()

    sin_sesion = cliente.post(
        "/comandos/cubos",
        {"id_sesion": "no-existe", "canal_id": 1, "nivel": 0, "t0": 0.0, "t1": 1.0},
    )
    assert sin_sesion.status_code == 404

    sin_canal = cliente.post(
        "/comandos/cubos",
        {
            "id_sesion": abierto["id_sesion"],
            "canal_id": 999_999_999,
            "nivel": 0,
            "t0": 0.0,
            "t1": 1.0,
        },
    )
    assert sin_canal.status_code == 404


# --------------------------------------------------------------------------- #
# sesiones y cerrar-log
# --------------------------------------------------------------------------- #
def test_cerrar_libera_la_sesion(tmp_path: Path) -> None:
    cliente = Cliente(tmp_path)
    abierto = cliente.abrir()
    canal = _canal_con_datos(abierto)

    cerrado = cliente.post("/comandos/cerrar-log", {"id_sesion": abierto["id_sesion"]})
    assert cerrado.status_code == 200
    assert cerrado.json() == {"cerrado": True, "sesiones_abiertas": 0}

    # Ya no se pueden pedir cubos de ella.
    respuesta = cliente.post(
        "/comandos/cubos",
        {
            "id_sesion": abierto["id_sesion"],
            "canal_id": canal["id"],
            "nivel": 0,
            "t0": 0.0,
            "t1": 1.0,
        },
    )
    assert respuesta.status_code == 404

    # Y cerrar dos veces no es un error.
    assert cliente.post("/comandos/cerrar-log", {"id_sesion": abierto["id_sesion"]}).json() == {
        "cerrado": False,
        "sesiones_abiertas": 0,
    }


def test_las_sesiones_abiertas_se_pueden_listar_y_tienen_tope(tmp_path: Path) -> None:
    """§2.6 pide aguantar 8 logs en paralelo; sin tope, la memoria del proceso
    crece hasta donde llegue el usuario abriendo ficheros."""
    cliente = Cliente(tmp_path, maximo_sesiones=2)
    primera = cliente.abrir(LOG_CORTO)
    segunda = cliente.abrir(RAIZ / "samples" / "real" / "20260729_1859_Log2769.csv")
    tercera = cliente.abrir(AUTOLOG_REAL)

    listado = cliente.get("/comandos/sesiones").json()
    assert listado["maximo_sesiones"] == 2
    ids = [s["id_sesion"] for s in listado["sesiones"]]
    assert len(ids) == 2
    assert primera["id_sesion"] not in ids, "la más antigua es la que se desaloja"
    assert segunda["id_sesion"] in ids
    assert tercera["id_sesion"] in ids


def test_la_segunda_apertura_sale_de_la_cache_parquet(tmp_path: Path) -> None:
    """ADR-005: un cliente nuevo (sin sesiones en memoria) no reparsea el log,
    lo reconstruye del `.dlvcache` que dejó el anterior."""
    primero = Cliente(tmp_path)
    a = primero.abrir()
    assert a["desde_cache"] is False

    segundo = Cliente(tmp_path)
    b = segundo.abrir()
    assert b["desde_cache"] is True
    assert b["n_canales"] == a["n_canales"]
    assert b["t_fin"] == pytest.approx(a["t_fin"])

    # Y los cubos que sirve son los mismos, byte a byte.
    canal = _canal_con_datos(a)
    peticion = {"canal_id": canal["id"], "nivel": 2, "t0": a["t_inicio"], "t1": a["t_fin"]}
    de_a = primero.post("/comandos/cubos", {**peticion, "id_sesion": a["id_sesion"]})
    de_b = segundo.post("/comandos/cubos", {**peticion, "id_sesion": b["id_sesion"]})
    assert de_a.content == de_b.content


def test_una_cache_corrupta_no_impide_abrir_el_log(tmp_path: Path) -> None:
    """Una caché es una optimización: que esté rota tiene que costar tiempo, no
    la apertura."""
    Cliente(tmp_path).abrir(LOG_CORTO)
    metadatos = next(tmp_path.glob("*.dlvcache.json"))
    metadatos.write_text("{ esto no es JSON válido", encoding="utf-8")

    abierto = Cliente(tmp_path).abrir(LOG_CORTO)
    assert abierto["desde_cache"] is False
    assert any("caché" in aviso for aviso in abierto["avisos"])
