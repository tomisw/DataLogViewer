"""Validación del catálogo data/roles.toml (tarea F0-10).

La prueba de valor es la última: coge los canales REALES del AutoLog, les aplica
la escala de origen del descriptor Haltech y comprueba que caen dentro del rango
plausible del rol que les corresponde. Eso valida a la vez tres ficheros —
units.toml, haltech_nsp.toml y roles.toml — contra datos de verdad, que es la
única forma de saber si los rangos sirven para algo.

Solo biblioteca estándar.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
ROLES = RAIZ / "data" / "roles.toml"
UNIDADES = RAIZ / "data" / "units.toml"
DESCRIPTOR = RAIZ / "data" / "formats" / "haltech_nsp.toml"
LOG_REAL = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"


def _toml(ruta: Path) -> dict:
    with ruta.open("rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def roles() -> dict:
    return _toml(ROLES)


@pytest.fixture(scope="module")
def unidades() -> dict:
    return _toml(UNIDADES)


@pytest.fixture(scope="module")
def desc() -> dict:
    return _toml(DESCRIPTOR)


# --------------------------------------------------------------------------- #
# Estructura
# --------------------------------------------------------------------------- #
def test_catalogo_carga(roles: dict) -> None:
    assert roles["meta"]["version"] == 1
    assert roles["roles"], "el catálogo no tiene roles"


def test_todo_rol_esta_bien_formado(roles: dict) -> None:
    for nombre, r in roles["roles"].items():
        assert re.fullmatch(r"[a-z][a-z0-9_]*", nombre), f"{nombre}: nombre no canónico"
        assert "dimension" in r, f"{nombre}: falta dimension"
        assert "plausible" in r, f"{nombre}: falta rango plausible"
        assert "sinonimos" in r and r["sinonimos"], f"{nombre}: sin sinónimos"
        p = r["plausible"]
        assert p["min"] < p["max"], f"{nombre}: rango invertido ({p['min']} >= {p['max']})"


def test_las_dimensiones_existen_en_el_catalogo_de_unidades(roles: dict, unidades: dict) -> None:
    validas = set(unidades["dimensiones"]) | set(unidades["compuestas"])
    for nombre, r in roles["roles"].items():
        assert r["dimension"] in validas, (
            f"{nombre}: dimensión '{r['dimension']}' no existe en units.toml"
        )


def test_los_sinonimos_no_colisionan_entre_roles(roles: dict) -> None:
    """Un mismo sinónimo en dos roles hace ambigua la asignación automática.

    La comparación es la misma que usará el importador: minúsculas, sin
    separadores y con el marcador de índice `{n}` eliminado.
    """

    def normaliza(s: str) -> str:
        s = s.lower().replace("{n}", "")
        return re.sub(r"[^a-z0-9áéíóúñ]", "", s)

    visto: dict[str, str] = {}
    colisiones: list[str] = []
    for nombre, r in roles["roles"].items():
        for sin in r["sinonimos"]:
            clave = normaliza(sin)
            if clave in visto and visto[clave] != nombre:
                colisiones.append(f"'{sin}' en {visto[clave]} y en {nombre}")
            visto[clave] = nombre
    assert not colisiones, "sinónimos ambiguos:\n  " + "\n  ".join(colisiones)


def test_los_indexados_declaran_el_marcador(roles: dict) -> None:
    """Si un rol admite índice, al menos un sinónimo debe llevar `{n}`; si no, la
    asignación automática no sabría dónde va el número."""
    for nombre, r in roles["roles"].items():
        if not r.get("indexado"):
            continue
        assert any("{n}" in s for s in r["sinonimos"]), (
            f"{nombre}: indexado pero ningún sinónimo lleva {{n}}"
        )


def test_los_acumulados_solo_en_dimensiones_que_lo_admiten(roles: dict) -> None:
    """`monotono` habilita el canal delta automático. Solo tiene sentido en
    contadores y distancias, no en una temperatura."""
    admitidas = {"count", "distance"}
    for nombre, r in roles["roles"].items():
        if r.get("monotono"):
            assert r["monotono"] == "no_decreciente", f"{nombre}: valor no reconocido"
            assert r["dimension"] in admitidas, (
                f"{nombre}: monótono pero dimensión '{r['dimension']}'"
            )


def test_las_mascaras_de_bits_tienen_rango_de_potencia_de_dos(roles: dict) -> None:
    """Una máscara de N bits llega como máximo a 2^N − 1."""
    for nombre, r in roles["roles"].items():
        if r["dimension"] != "bitmask":
            continue
        mx = int(r["plausible"]["max"])
        assert mx > 0 and (mx + 1) & mx == 0, (
            f"{nombre}: max {mx} no es 2^N − 1, sospechoso para una máscara"
        )


def test_los_roles_criticos_de_los_detectores_existen(roles: dict) -> None:
    """Los detectores de severidad crítica de docs/04 §4.3 dependen de estos
    roles. Si falta uno, el detector no se puede definir."""
    necesarios = {
        "knock_count",           # D1
        "lambda_measured",       # D4
        "lambda_target",         # D4
        "throttle_position",     # D4
        "engine_speed",          # D4, contexto de casi todos
        "boost_pressure_actual",  # D6
        "injector_duty",         # D8
        "coolant_temp",          # D9
        "oil_pressure",          # D10
        "battery_voltage",       # D11
        "trigger_errors",        # D12
        "protection_level",      # D13
    }
    faltan = necesarios - set(roles["roles"])
    assert not faltan, f"faltan roles de detectores críticos: {sorted(faltan)}"
    for n in necesarios:
        assert roles["roles"][n].get("critico") is True, (
            f"{n}: alimenta un detector crítico pero no está marcado `critico`"
        )


def test_el_resumen_cuadra(roles: dict) -> None:
    r = roles["roles"]
    s = roles["resumen"]
    assert len(r) == s["roles_totales"], f"{len(r)} roles vs resumen {s['roles_totales']}"
    assert sum(1 for x in r.values() if x.get("indexado")) == s["indexados"]
    assert sum(1 for x in r.values() if x.get("critico")) == s["criticos"]
    assert sum(1 for x in r.values() if x.get("monotono")) == s["con_contador_acumulado"]


# --------------------------------------------------------------------------- #
# La prueba de valor: rangos contra datos reales
# --------------------------------------------------------------------------- #
# Canal del AutoLog -> rol. Es un subconjunto deliberado: los canales que un
# perfil de fábrica usa y cuyo rol es inequívoco.
CANAL_A_ROL = {
    "RPM": "engine_speed",
    "Throttle Position": "throttle_position",
    "Manifold Pressure": "manifold_pressure",
    "Coolant Temperature": "coolant_temp",
    "Intake Air Temperature": "intake_air_temp",
    "ECU Temperature": "ecu_temp",
    "Wideband O2 1": "lambda_measured",
    "Target Lambda": "lambda_target",
    "Fuel Tuning Current Stoichiometry": "stoichiometry",
    "Ignition Angle": "ignition_advance",
    "Base Ignition Angle": "ignition_advance_base",
    "Oil Pressure": "oil_pressure",
    "Battery Voltage": "battery_voltage",
    "Vehicle Speed": "vehicle_speed",
    "Knock Threshold": "knock_threshold",
    "Knock Sensor 1 Knock Level": "knock_level",
    "Knock Sensor 1 Knock Count": "knock_count",
    "Injection Stage 1 Average Duty Cycle": "injector_duty",
    "Injector 1 On Time": "injector_pulsewidth",
    "Trigger System Errors": "trigger_errors",
    "Engine Protection Severity Level": "protection_level",
    "Boost Control Actual Pressure": "boost_pressure_actual",
    "Boost Control Target Pressure": "boost_pressure_target",
    "Cut Percentage": "cut_percentage",
}

# `Oil Temperature` queda fuera a propósito: en el AutoLog está pegada en
# 253,1 K (−20 °C) con el motor a 93 °C porque el sensor no está instalado
# (docs/01 §1.11). Su rango plausible la aceptaría, pero incluirla aquí daría a
# entender que el dato es bueno. Lo que tiene que cazarla es el clasificador de
# canal muerto, no el informe de plausibilidad.


@pytest.fixture(scope="module")
def muestras() -> dict[str, list[int]]:
    """Valores crudos de los canales de interés, sobre las primeras 800 filas."""
    texto = LOG_REAL.read_text(encoding="utf-8", errors="replace")
    canales: list[str] = []
    tipos: dict[str, str] = {}
    cur: str | None = None
    filas: list[str] = []
    en_datos = False
    for linea in texto.split("\n"):
        if re.match(r"^\d\d:\d\d:\d\d\.\d\d\d,", linea):
            en_datos = True
        if en_datos:
            if linea.strip():
                filas.append(linea)
            continue
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        clave, valor = clave.strip(), valor.strip()
        if clave == "Channel":
            cur = valor
            canales.append(cur)
        elif clave == "Type" and cur:
            tipos[cur] = valor

    idx = {n: i for i, n in enumerate(canales)}
    out: dict[str, list[int]] = {n: [] for n in CANAL_A_ROL if n in idx}
    for linea in filas[:800]:
        campos = linea.split(",")
        if len(campos) <= len(canales):
            continue
        for n in out:
            crudo = campos[1 + idx[n]].strip()
            if crudo:
                try:
                    out[n].append(int(crudo))
                except ValueError:
                    pass
    out["__tipos__"] = tipos  # type: ignore[assignment]
    return out


def test_los_canales_reales_caen_en_su_rango_plausible(
    roles: dict, desc: dict, muestras: dict
) -> None:
    """El cruce de los tres catálogos contra el log de verdad.

    Si esto falla, o el rango del rol está mal, o la escala del descriptor está
    mal. Las dos posibilidades son defectos que hay que corregir.
    """
    tipos = muestras["__tipos__"]
    centinelas = set(_toml(UNIDADES)["centinelas"]["i32"])
    problemas: list[str] = []
    comprobados = 0

    for canal, rol in CANAL_A_ROL.items():
        vals = muestras.get(canal)
        if not vals:
            continue
        tipo = tipos.get(canal)
        entrada = desc["tipos"].get(tipo)
        if entrada is None:
            problemas.append(f"{canal}: tipo '{tipo}' no está en el descriptor")
            continue
        a = float(entrada["a_canonica"])
        p = roles["roles"][rol]["plausible"]
        for v in vals:
            if v in centinelas:
                continue  # no es una medida (docs/01 §1.13)
            canon = v * a
            if not (p["min"] <= canon <= p["max"]):
                problemas.append(
                    f"{canal} -> {rol}: crudo {v} x {a} = {canon:g}, "
                    f"fuera de [{p['min']:g}, {p['max']:g}]"
                )
                break
        comprobados += 1

    assert comprobados >= 20, f"solo se han comprobado {comprobados} canales"
    assert not problemas, "valores reales fuera del rango plausible:\n  " + "\n  ".join(problemas)


def test_el_mapeo_de_prueba_usa_roles_que_existen(roles: dict) -> None:
    faltan = set(CANAL_A_ROL.values()) - set(roles["roles"])
    assert not faltan, f"el mapeo de prueba cita roles inexistentes: {sorted(faltan)}"
