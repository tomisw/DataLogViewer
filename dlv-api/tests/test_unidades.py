"""Pruebas de `/comandos/unidades` y del cuerpo `crudo` de `/comandos/cubos`.

Las dos rutas existen por el mismo motivo: **`dlv-ui` no tiene ninguna
dependencia**, y eso decide qué puede consumir.

- El catálogo de unidades no se duplica en TypeScript porque `data/units.toml`
  es dato del propietario y la regla 2 de `CLAUDE.md` prohíbe trasladar sus
  valores al código. Se sirve.
- Los cubos no pueden viajar en Arrow IPC hacia el navegador sin la librería
  `apache-arrow` (dependencia nueva) o un lector escrito a mano, así que se
  sirve además el búfer de tipado fijo que ADR-007 ya contemplaba.

Lo que estas pruebas protegen es el contrato entre los dos lados, que está
descrito en dos ficheros de dos lenguajes y que nada del compilador ata.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from dlv_api.main import crear_app
from dlv_core.transporte import MEDIA_TYPE_ARROW_IPC, binario_a_cubos

RAIZ = Path(__file__).resolve().parents[2]
LOG = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"
TOKEN = "token-de-prueba"


@pytest.fixture
def cliente(tmp_path: Path) -> TestClient:
    app = crear_app(token_sesion=TOKEN, dir_cache=tmp_path)
    return TestClient(app)


def cabeceras() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


# --------------------------------------------------------------------------- #
# Catálogo de unidades
# --------------------------------------------------------------------------- #
def test_el_catalogo_sale_de_units_toml_y_no_de_una_copia(cliente: TestClient) -> None:
    """Los valores tienen que ser los del fichero del propietario.

    Se comprueba con `temperature`, que es la dimensión donde vive la trampa
    del delta: si el catálogo servido no trajera las cuatro unidades reales,
    conmutar °C↔°F↔K —la mitad del hito M1— estaría mintiendo.
    """
    r = cliente.get("/comandos/unidades", headers=cabeceras())
    assert r.status_code == 200
    catalogo = r.json()

    por_id = {d["id"]: d for d in catalogo["dimensiones"]}
    assert "temperature" in por_id, "falta la dimensión de temperatura"
    unidades = {u["id"] for u in por_id["temperature"]["unidades"]}
    assert {"K", "degC", "degF"} <= unidades
    assert por_id["temperature"]["unidadCanonica"] == "K"


def test_el_catalogo_llega_en_camel_case(cliente: TestClient) -> None:
    """La frontera entre `snake_case` de Python y `camelCase` de TypeScript
    tiene que estar en UN sitio, y ese sitio es quien serializa. Si se cruzara
    en el frontend, cada consumidor nuevo tendría que acordarse."""
    catalogo = cliente.get("/comandos/unidades", headers=cabeceras()).json()
    assert "presetPorOmision" in catalogo
    assert "unidadCanonica" in catalogo["dimensiones"][0]
    assert all("decimales" in u for d in catalogo["dimensiones"] for u in d["unidades"])


def test_el_preset_por_omision_existe_de_verdad(cliente: TestClient) -> None:
    """Un preset por omisión que no está en la lista dejaría al selector de
    unidad resolviendo contra algo que no existe."""
    catalogo = cliente.get("/comandos/unidades", headers=cabeceras()).json()
    ids = {p["id"] for p in catalogo["presets"]}
    assert catalogo["presetPorOmision"] in ids


def test_el_catalogo_exige_token(cliente: TestClient) -> None:
    assert cliente.get("/comandos/unidades").status_code == 401


# --------------------------------------------------------------------------- #
# Cuerpo binario `crudo`
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not LOG.is_file(), reason="hace falta el log real")
def test_crudo_y_arrow_llevan_exactamente_los_mismos_numeros(cliente: TestClient) -> None:
    """Es la prueba que importa: dos formatos, un solo dato.

    Si divergieran, el frontend (que lee `crudo`) y las pruebas de Python (que
    leen Arrow) estarían mirando cosas distintas y ninguna de las dos lo diría.
    """
    abrir = cliente.post("/comandos/abrir-log", json={"ruta": str(LOG)}, headers=cabeceras())
    assert abrir.status_code == 200, abrir.text
    sesion = abrir.json()
    canal = sesion["canales"][0]
    peticion = {
        "id_sesion": sesion["id_sesion"],
        "canal_id": canal["id"],
        "t0": sesion["t_inicio"],
        "t1": sesion["t_fin"],
        "nivel": len(canal["niveles"]) - 1,
    }

    en_arrow = cliente.post("/comandos/cubos", json=peticion, headers=cabeceras())
    en_crudo = cliente.post(
        "/comandos/cubos", json={**peticion, "formato_binario": "crudo"}, headers=cabeceras()
    )
    assert en_arrow.status_code == 200 and en_crudo.status_code == 200
    assert en_arrow.headers["content-type"] == MEDIA_TYPE_ARROW_IPC
    assert en_crudo.headers["content-type"] == "application/octet-stream"

    n = int(en_crudo.headers["X-Cubos"])
    assert n > 0
    from dlv_core.transporte import arrow_ipc_a_cubos

    desde_arrow = arrow_ipc_a_cubos(en_arrow.content)
    desde_crudo = binario_a_cubos(en_crudo.content, n)
    for columna, valores in desde_arrow.items():
        assert np.allclose(valores, desde_crudo[columna], equal_nan=True), (
            f"la columna «{columna}» no coincide entre Arrow y crudo"
        )


@pytest.mark.skipif(not LOG.is_file(), reason="hace falta el log real")
def test_el_tamaño_del_crudo_lo_dice_la_cabecera(cliente: TestClient) -> None:
    """El frontend reserva las cinco vistas a partir de `X-Cubos`: si el número
    y el tamaño no cuadran, lee `NaN` en las últimas columnas y en WebGL eso no
    da error, da un hueco en el trazo."""
    sesion = cliente.post(
        "/comandos/abrir-log", json={"ruta": str(LOG)}, headers=cabeceras()
    ).json()
    canal = sesion["canales"][0]
    r = cliente.post(
        "/comandos/cubos",
        json={
            "id_sesion": sesion["id_sesion"],
            "canal_id": canal["id"],
            "t0": sesion["t_inicio"],
            "t1": sesion["t_fin"],
            "nivel": len(canal["niveles"]) - 1,
            "formato_binario": "crudo",
        },
        headers=cabeceras(),
    )
    assert len(r.content) == int(r.headers["X-Cubos"]) * 5 * 4


@pytest.mark.skipif(not LOG.is_file(), reason="hace falta el log real")
def test_arrow_sigue_siendo_lo_que_sale_si_nadie_pide_nada(cliente: TestClient) -> None:
    """F1-22 está cerrada y revisada: añadir un formato no puede cambiar el que
    ya consumía alguien."""
    sesion = cliente.post(
        "/comandos/abrir-log", json={"ruta": str(LOG)}, headers=cabeceras()
    ).json()
    r = cliente.post(
        "/comandos/cubos",
        json={
            "id_sesion": sesion["id_sesion"],
            "canal_id": sesion["canales"][0]["id"],
            "t0": 0.0,
            "t1": 1.0,
            "nivel": 0,
        },
        headers=cabeceras(),
    )
    assert r.headers["content-type"] == MEDIA_TYPE_ARROW_IPC
