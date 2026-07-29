"""Validación del descriptor data/formats/haltech_nsp.toml (tarea F0-09).

Dos cosas que proteger:

1. **Coherencia con el catálogo de unidades**: cada dimensión que el descriptor
   nombra debe existir en `data/units.toml`. Un typo aquí produce un canal sin
   unidad, silenciosamente.
2. **Las identidades aritméticas** que justifican las escalas marcadas
   `confirmed`. Si alguien cambia un factor, estas pruebas lo cazan contra los
   valores reales del log, no contra una constante copiada.

Solo biblioteca estándar.
"""

from __future__ import annotations

import math
import re
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
DESCRIPTOR = RAIZ / "data" / "formats" / "haltech_nsp.toml"
UNIDADES = RAIZ / "data" / "units.toml"
LOG_REAL = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"

CONFIANZAS = {"confirmed", "inferred", "unknown"}


@pytest.fixture(scope="module")
def desc() -> dict:
    with DESCRIPTOR.open("rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def unidades() -> dict:
    with UNIDADES.open("rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def log() -> tuple[list[dict], list[str]]:
    """Canales y filas de datos del AutoLog real."""
    texto = LOG_REAL.read_text(encoding="utf-8", errors="replace")
    canales: list[dict] = []
    cur: dict | None = None
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
            if cur:
                canales.append(cur)
            cur = {"name": valor}
        elif cur is not None and clave in ("ID", "Type", "DisplayMaxMin"):
            cur[clave] = valor
    if cur:
        canales.append(cur)
    return canales, filas


@pytest.fixture(scope="module")
def fila_de_referencia(log: tuple[list[dict], list[str]]) -> dict[str, int]:
    """La fila de MAP máximo: 6715 rpm a plena carga. Es la que sostiene las
    identidades documentadas en el descriptor."""
    canales, filas = log
    idx = {c["name"]: i for i, c in enumerate(canales)}
    mejor: list[str] | None = None
    mx = 0
    for linea in filas:
        campos = linea.split(",")
        if len(campos) <= len(canales):
            continue
        try:
            rpm = int(campos[1 + idx["RPM"]])
            mp = int(campos[1 + idx["Manifold Pressure"]])
        except (ValueError, IndexError):
            continue
        if rpm > 2500 and mp > mx:
            mx, mejor = mp, campos
    assert mejor is not None, "no se encontró fila con motor en carga"
    return {nombre: int(mejor[1 + i]) for nombre, i in idx.items() if mejor[1 + i].strip()}


# --------------------------------------------------------------------------- #
# Estructura
# --------------------------------------------------------------------------- #
def test_descriptor_carga(desc: dict) -> None:
    assert desc["meta"]["formato"] == "haltech_nsp"
    assert desc["meta"]["firma"] == "%DataLog%"
    assert "1.1" in desc["deteccion"]["version_soportada"]


def test_los_34_tipos_del_formato_estan_mapeados(desc: dict, log) -> None:
    """Ningún `Type` del log real puede quedarse sin entrada: si falta uno, ese
    canal no tendría ni dimensión ni escala."""
    canales, _ = log
    del_log = {c["Type"] for c in canales if "Type" in c}
    del_descriptor = set(desc["tipos"])
    faltan = del_log - del_descriptor
    assert not faltan, f"tipos del log sin mapear: {sorted(faltan)}"
    assert len(del_log) == 34, f"el log tiene {len(del_log)} tipos, no 34"


def test_toda_entrada_esta_bien_formada(desc: dict) -> None:
    for nombre, t in desc["tipos"].items():
        assert "dimension" in t, f"{nombre}: falta dimension"
        assert "a_canonica" in t, f"{nombre}: falta a_canonica"
        assert t["a_canonica"] != 0, f"{nombre}: a_canonica = 0 no es invertible"
        assert t["confianza"] in CONFIANZAS, f"{nombre}: confianza '{t['confianza']}'"
        assert t.get("evidencia", "").strip(), f"{nombre}: sin evidencia documentada"


def test_las_dimensiones_existen_en_el_catalogo_de_unidades(desc: dict, unidades: dict) -> None:
    """El cruce que evita el typo silencioso."""
    validas = set(unidades["dimensiones"]) | set(unidades["compuestas"])
    for nombre, t in desc["tipos"].items():
        assert t["dimension"] in validas, (
            f"{nombre}: dimensión '{t['dimension']}' no existe en units.toml"
        )


def test_los_desconocidos_apuntan_a_la_dimension_unknown(desc: dict) -> None:
    """Mitigación de R1: sin escala confirmada no se promete una unidad.

    Las compuestas son la excepción: su dimensión es real (el cociente existe),
    lo que se desconoce es el factor, y units.toml no les da unidades propias.
    """
    for nombre, t in desc["tipos"].items():
        if t["confianza"] != "unknown" or t.get("compuesta"):
            continue
        assert t["dimension"] == "unknown", (
            f"{nombre}: confianza unknown pero dimensión '{t['dimension']}'; "
            "un canal sin escala confirmada debe mostrarse en crudo"
        )


def test_el_resumen_cuadra_con_las_entradas(desc: dict) -> None:
    r = desc["resumen"]
    tipos = desc["tipos"]
    cuenta = {c: sum(1 for t in tipos.values() if t["confianza"] == c) for c in CONFIANZAS}
    assert len(tipos) == r["tipos_totales"], f"{len(tipos)} tipos vs resumen {r['tipos_totales']}"
    assert cuenta["confirmed"] == r["confirmados"]
    assert cuenta["inferred"] == r["inferidos"]
    assert cuenta["unknown"] == r["desconocidos"]


def test_el_recuento_de_canales_por_tipo_cuadra_con_el_log(desc: dict, log) -> None:
    canales, _ = log
    real: dict[str, int] = {}
    for c in canales:
        if "Type" in c:
            real[c["Type"]] = real.get(c["Type"], 0) + 1
    for nombre, t in desc["tipos"].items():
        if "canales" not in t:
            continue
        assert t["canales"] == real.get(nombre), (
            f"{nombre}: el descriptor dice {t['canales']} canales, el log tiene {real.get(nombre)}"
        )


# --------------------------------------------------------------------------- #
# Identidades que justifican las escalas `confirmed`
# --------------------------------------------------------------------------- #
def a(desc: dict, tipo: str) -> float:
    return float(desc["tipos"][tipo]["a_canonica"])


def test_identidad_abspressure_es_una_diferencia(desc: dict, fila_de_referencia: dict) -> None:
    """La identidad que descubrió que `AbsPressure` NO es la presión absoluta:
    es la diferencia entre dos canales de tipo `Pressure`."""
    f = fila_de_referencia
    diferencia = (f["Fuel Pressure Expected"] - f["Manifold Pressure"]) * a(desc, "Pressure")
    declarada = f["Injector Pressure Differential"] * a(desc, "AbsPressure")
    assert math.isclose(diferencia, declarada, abs_tol=0.2), (
        f"{diferencia} kPa calculados vs {declarada} kPa del canal diferencial"
    )
    assert desc["tipos"]["AbsPressure"]["referencia"] == "ninguna"
    assert desc["tipos"]["AbsPressure"]["clase"] == "intervalo", (
        "una diferencia de presión nunca debe llevar el desplazamiento de origen"
    )
    assert desc["tipos"]["Pressure"]["referencia"] == "absoluta"


def test_identidad_time_us_via_periodo_de_ciclo(desc: dict, fila_de_referencia: dict) -> None:
    """2 vueltas de cigüeñal a las rpm de la fila deben dar el Engine Cycle Period."""
    f = fila_de_referencia
    rpm = f["RPM"]
    segundos_declarados = f["Engine Cycle Period"] * a(desc, "Time_us")
    segundos_teoricos = 2 * 60 / rpm
    error = abs(segundos_declarados - segundos_teoricos) / segundos_teoricos
    assert error < 0.005, f"error del {error:.2%} entre {segundos_declarados} y {segundos_teoricos}"


def test_el_periodo_de_cilindro_revela_seis_cilindros(fila_de_referencia: dict) -> None:
    """Consecuencia de la identidad anterior, y dato útil del vehículo."""
    f = fila_de_referencia
    cilindros = f["Engine Cycle Period"] / f["Cylinder Period"]
    assert math.isclose(cilindros, 6.0, abs_tol=0.05), f"salen {cilindros} cilindros"


def test_identidad_frequency_via_disparo_de_inyector(desc: dict, fila_de_referencia: dict) -> None:
    """Un inyector de cuatro tiempos dispara una vez cada dos vueltas."""
    f = fila_de_referencia
    hz_declarados = f["Injector 1 Frequency"] * a(desc, "Frequency")
    hz_teoricos = f["RPM"] / 2 / 60
    # El canal viene truncado a entero, así que 1 Hz de margen es correcto.
    assert abs(hz_declarados - hz_teoricos) < 1.5, f"{hz_declarados} Hz vs {hz_teoricos:.2f} Hz"


def test_temperatura_en_decikelvin(desc: dict, fila_de_referencia: dict) -> None:
    kelvin = fila_de_referencia["Coolant Temperature"] * a(desc, "Temperature")
    celsius = kelvin - 273.15
    assert 60.0 < celsius < 120.0, f"refrigerante a {celsius:.1f} °C, fuera de lo plausible"


def test_presion_de_colector_en_carga(desc: dict, fila_de_referencia: dict) -> None:
    kpa = fila_de_referencia["Manifold Pressure"] * a(desc, "Pressure")
    assert 150.0 < kpa < 350.0, f"MAP de {kpa} kPa absolutos a plena carga, implausible"


def test_lambda_en_rango_fisico(desc: dict, fila_de_referencia: dict) -> None:
    lam = fila_de_referencia["Wideband O2 1"] * a(desc, "AFR")
    assert 0.5 < lam < 1.4, f"lambda {lam} fuera del rango del sensor"


def test_estequiometria_de_gasolina(desc: dict, fila_de_referencia: dict) -> None:
    stq = fila_de_referencia["Fuel Tuning Current Stoichiometry"] * a(desc, "Stoichiometry")
    assert math.isclose(stq, 14.7, abs_tol=0.05), f"estequiometría {stq}"


def test_bytecount_es_potencia_de_dos(desc: dict, fila_de_referencia: dict) -> None:
    """8 388 608 = 2^23 = 8 MiB. Es lo que confirma que el tipo son bytes."""
    total = int(fila_de_referencia["Data Log Total Memory"] * a(desc, "ByteCount"))
    assert total == 8 * 1024 * 1024, f"{total} bytes no son 8 MiB"


def test_percentage_da_fraccion_no_porcentaje(desc: dict, fila_de_referencia: dict) -> None:
    """La canónica de `ratio` es la fracción: 1000 crudo = 1,0, no 100."""
    tps = fila_de_referencia["Throttle Position"] * a(desc, "Percentage")
    assert 0.0 <= tps <= 1.0, f"TPS canónico {tps} debería ser una fracción"
    assert math.isclose(tps, fila_de_referencia["Throttle Position"] / 1000.0)


def test_masa_por_cilindro_da_la_relacion_de_mezcla(desc: dict, fila_de_referencia: dict) -> None:
    """La evidencia con la que se marcó MassPerCyl como `inferred`: el factor
    absoluto no está probado, pero la RELACIÓN entre aire y combustible debe
    aproximar el AFR que implica la lambda medida."""
    f = fila_de_referencia
    relacion = f["Calculated Air Mass Per Cylinder"] / f["Fuel Mass Per Cylinder"]
    lam = f["Wideband O2 1"] * a(desc, "AFR")
    stq = f["Fuel Tuning Current Stoichiometry"] * a(desc, "Stoichiometry")
    afr_esperado = lam * stq
    error = abs(relacion - afr_esperado) / afr_esperado
    assert error < 0.15, f"relación {relacion:.2f} vs AFR esperado {afr_esperado:.2f}"
    assert desc["tipos"]["MassPerCyl"]["confianza"] == "inferred", (
        "la relación cuadra pero el factor absoluto sigue sin probarse"
    )


def test_massovertime_sigue_siendo_desconocido(desc: dict) -> None:
    """Regresión deliberada: si alguien le pone una escala a MassOverTime sin
    resolver la contradicción documentada, esta prueba lo para."""
    t = desc["tipos"]["MassOverTime"]
    assert t["confianza"] == "unknown"
    assert t["dimension"] == "unknown"
    assert "no cuadra" in t["evidencia"].lower()
