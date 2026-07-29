"""Verifica que el log de verdad de referencia cumple sus propias anotaciones (F0-07).

Un fichero de verdad de referencia que no coincide con sus datos es peor que no
tener ninguno: valida detectores contra una realidad inventada. Estas pruebas
leen `verdad.csv`, aplican las escalas de `data/formats/haltech_nsp.toml` y
comprueban, evento por evento, que la condición que el JSON afirma **se cumple
de verdad** en los positivos y **no se cumple** en los negativos.

Solo biblioteca estándar.
"""

from __future__ import annotations

import json
import re
import statistics
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
DIR = RAIZ / "samples" / "verdad"
LOG = DIR / "verdad.csv"
VERDAD = DIR / "verdad.json"
DESCRIPTOR = RAIZ / "data" / "formats" / "haltech_nsp.toml"
ROLES = RAIZ / "data" / "roles.toml"


def _toml(ruta: Path) -> dict:
    with ruta.open("rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def verdad() -> dict:
    return json.loads(VERDAD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def log() -> tuple[list[dict], list[tuple[int, list[str]]]]:
    """(bloques de canal, [(marca_ms, campos crudos)])."""
    # `newline=""` desactiva la traducción de saltos de línea de Python: sin él,
    # `read_text` convierte el CRLF nativo del formato en LF y partir por "\r\n"
    # no encuentra nada. El fichero es CRLF a propósito (docs/01 §1.13).
    with LOG.open("r", encoding="utf-8", newline="") as fh:
        texto = fh.read()
    canales: list[dict] = []
    cur: dict | None = None
    filas: list[tuple[int, list[str]]] = []
    for linea in texto.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^(\d\d):(\d\d):(\d\d)\.(\d\d\d),(.*)$", linea)
        if m:
            h, mi, s, ms, resto = m.groups()
            t = (int(h) - 18) * 3_600_000 + int(mi) * 60_000 + int(s) * 1000 + int(ms)
            filas.append((t, resto.split(",")))
            continue
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        clave, valor = clave.strip(), valor.strip()
        if clave == "Channel":
            if cur:
                canales.append(cur)
            cur = {"nombre": valor}
        elif cur is not None and clave in ("ID", "Type", "DisplayMaxMin"):
            cur[clave] = valor
    if cur:
        canales.append(cur)
    return canales, filas


@pytest.fixture(scope="module")
def serie(log) -> dict:
    """Devuelve un acceso `serie(nombre)[i]` con el valor ya en unidad canónica."""
    canales, filas = log
    desc = _toml(DESCRIPTOR)["tipos"]
    idx = {c["nombre"]: i for i, c in enumerate(canales)}
    escalas = {c["nombre"]: float(desc[c["Type"]]["a_canonica"]) for c in canales}

    datos: dict[str, list[float]] = {n: [] for n in idx}
    marcas: list[int] = []
    for t, campos in filas:
        marcas.append(t)
        for n, i in idx.items():
            datos[n].append(int(campos[i]) * escalas[n])
    return {"datos": datos, "marcas": marcas, "idx": idx}


def ventana(serie: dict, t0: int, t1: int) -> list[int]:
    """Índices de las filas cuya marca cae en [t0, t1)."""
    return [i for i, t in enumerate(serie["marcas"]) if t0 <= t < t1]


def vals(serie: dict, canal: str, t0: int, t1: int) -> list[float]:
    return [serie["datos"][canal][i] for i in ventana(serie, t0, t1)]


def eventos_de(verdad: dict, detector: str, disparar: bool) -> list[dict]:
    return [
        e for e in verdad["eventos"] if e["detector"] == detector and e["debe_disparar"] is disparar
    ]


# --------------------------------------------------------------------------- #
# Estructura
# --------------------------------------------------------------------------- #
def test_ficheros_existen() -> None:
    for n in ("verdad.csv", "verdad.json", "README.md"):
        assert (DIR / n).exists(), f"falta {n}"


def test_el_log_es_un_haltech_valido(log) -> None:
    canales, filas = log
    assert LOG.read_bytes().startswith(b"%DataLog%\r\n")
    assert len(canales) == 20
    assert len(filas) == 1200
    for _t, campos in filas:
        assert len(campos) == len(canales), "número de columnas inconsistente"


def test_los_canales_declarados_coinciden_con_el_json(verdad: dict, log) -> None:
    canales, _ = log
    del_log = [(c["nombre"], int(c["ID"]), c["Type"]) for c in canales]
    del_json = [(c["nombre"], c["id"], c["type"]) for c in verdad["canales"]]
    assert del_log == del_json


def test_los_roles_citados_existen(verdad: dict) -> None:
    roles = _toml(ROLES)["roles"]
    for c in verdad["canales"]:
        if c["rol"]:
            assert c["rol"] in roles, f"{c['nombre']}: rol '{c['rol']}' no existe"


def test_el_resumen_del_json_cuadra(verdad: dict) -> None:
    r = verdad["resumen"]
    ev = verdad["eventos"]
    assert len(ev) == r["eventos_totales"]
    assert sum(1 for e in ev if e["debe_disparar"]) == r["deben_disparar"]
    assert sum(1 for e in ev if not e["debe_disparar"]) == r["no_deben_disparar"]
    assert sorted({e["detector"] for e in ev}) == r["detectores_cubiertos"]


def test_hay_casos_negativos_suficientes(verdad: dict) -> None:
    """Si no hay negativos, el corpus no puede demostrar ausencia de falsos
    positivos, que es la mitad del trabajo de un detector."""
    neg = [e for e in verdad["eventos"] if not e["debe_disparar"]]
    assert len(neg) >= 5, f"solo {len(neg)} casos negativos"
    # Cada detector con negativo debe tener también un positivo con el que
    # contrastar, o el negativo no prueba nada.
    pos_por_det = {e["detector"] for e in verdad["eventos"] if e["debe_disparar"]}
    for e in neg:
        assert e["detector"] in pos_por_det, (
            f"{e['detector']} tiene caso negativo pero ningún positivo con el que contrastar"
        )


def test_los_contadores_acumulados_no_decrecen(serie: dict) -> None:
    """Requisito de `monotono = no_decreciente` en roles.toml."""
    for canal in ("Knock Sensor 1 Knock Count", "Knock Sensor 2 Knock Count"):
        v = serie["datos"][canal]
        for i in range(1, len(v)):
            assert v[i] >= v[i - 1], f"{canal} decrece en la fila {i}"


# --------------------------------------------------------------------------- #
# Cada evento anotado se cumple de verdad
# --------------------------------------------------------------------------- #
def test_d1_los_eventos_de_knock_incrementan_el_contador(verdad: dict, serie: dict) -> None:
    cuenta = serie["datos"]["Knock Sensor 1 Knock Count"]
    for e in eventos_de(verdad, "D1", True):
        idxs = ventana(serie, e["t_inicio_ms"], e["t_fin_ms"])
        assert idxs, f"D1 en {e['t_inicio_ms']} ms: sin filas en la ventana"
        i = idxs[0]
        assert cuenta[i] > cuenta[i - 1], (
            f"D1 en {e['t_inicio_ms']} ms: el contador no se incrementa "
            f"({cuenta[i - 1]} -> {cuenta[i]})"
        )
        # La severidad crítica exige contexto de carga (docs/04 §4.3).
        if e["severidad_esperada"] == "critica":
            assert serie["datos"]["RPM"][i] > 4000
            assert serie["datos"]["Manifold Pressure"][i] > 150


def test_d2_positivo_knock_sostenido_sobre_umbral(verdad: dict, serie: dict) -> None:
    for e in eventos_de(verdad, "D2", True):
        nivel = vals(serie, "Knock Sensor 1 Knock Level", e["t_inicio_ms"], e["t_fin_ms"])
        umbral = vals(serie, "Knock Threshold", e["t_inicio_ms"], e["t_fin_ms"])
        assert len(nivel) >= 3, "una ventana de knock sostenido necesita varias muestras"
        for n, u in zip(nivel, umbral, strict=True):
            assert n > u, f"nivel {n} dB no supera el umbral {u} dB"
        duracion = e["t_fin_ms"] - e["t_inicio_ms"]
        assert duracion >= 100, "la ventana no llega a la permanencia mínima de 100 ms"


def test_d2_negativo_el_pico_aislado_dura_una_sola_muestra(verdad: dict, serie: dict) -> None:
    """El caso que separa un detector usable de uno que grita: un pico de ruido
    de una muestra no puede generar una incidencia."""
    for e in eventos_de(verdad, "D2", False):
        idxs = ventana(serie, e["t_inicio_ms"], e["t_fin_ms"])
        assert len(idxs) == 1, f"el pico aislado abarca {len(idxs)} muestras, debería ser 1"
        i = idxs[0]
        nivel = serie["datos"]["Knock Sensor 1 Knock Level"]
        umbral = serie["datos"]["Knock Threshold"]
        assert nivel[i] > umbral[i], "el pico debe estar sobre el umbral"
        # Y las muestras de alrededor, por debajo: si no, no es un pico aislado.
        assert nivel[i - 1] < umbral[i - 1]
        assert nivel[i + 1] < umbral[i + 1]
        assert e["t_fin_ms"] - e["t_inicio_ms"] < 100, (
            "el caso negativo debe durar menos que la permanencia mínima"
        )


def test_d4_positivo_mezcla_pobre_en_carga(verdad: dict, serie: dict) -> None:
    for e in eventos_de(verdad, "D4", True):
        med = vals(serie, "Wideband O2 1", e["t_inicio_ms"], e["t_fin_ms"])
        obj = vals(serie, "Target Lambda", e["t_inicio_ms"], e["t_fin_ms"])
        tps = vals(serie, "Throttle Position", e["t_inicio_ms"], e["t_fin_ms"])
        rpm = vals(serie, "RPM", e["t_inicio_ms"], e["t_fin_ms"])
        assert med, "ventana vacía"
        for m, o, tp, r in zip(med, obj, tps, rpm, strict=True):
            assert m / o - 1 > 0.04, f"desviación {m / o - 1:.4f} no supera el 4 %"
            assert tp > 0.70, f"TPS {tp} no cumple la condición de carga"
            assert r > 3000, f"RPM {r} no cumple la condición de régimen"


def test_d4_negativo_desviacion_por_debajo_del_umbral(verdad: dict, serie: dict) -> None:
    for e in eventos_de(verdad, "D4", False):
        med = vals(serie, "Wideband O2 1", e["t_inicio_ms"], e["t_fin_ms"])
        obj = vals(serie, "Target Lambda", e["t_inicio_ms"], e["t_fin_ms"])
        assert med, "ventana vacía"
        for m, o in zip(med, obj, strict=True):
            assert m / o - 1 < 0.04, (
                f"desviación {m / o - 1:.4f} SÍ supera el 4 %: el caso negativo es inválido"
            )


def test_d8_duty_de_inyeccion(verdad: dict, serie: dict) -> None:
    for e in eventos_de(verdad, "D8", True):
        duty = vals(serie, "Injection Stage 1 Average Duty Cycle", e["t_inicio_ms"], e["t_fin_ms"])
        assert duty, "ventana vacía"
        limite = 0.95 if e["severidad_esperada"] == "critica" else 0.85
        for d in duty:
            assert d > limite, f"duty {d} no supera {limite}"
    for e in eventos_de(verdad, "D8", False):
        duty = vals(serie, "Injection Stage 1 Average Duty Cycle", e["t_inicio_ms"], e["t_fin_ms"])
        for d in duty:
            assert d < 0.85, f"duty {d} SÍ supera el 85 %: el caso negativo es inválido"


def test_d9_sobretemperatura_y_su_permanencia(verdad: dict, serie: dict) -> None:
    UMBRAL_K = 105.0 + 273.15
    for e in eventos_de(verdad, "D9", True):
        temp = vals(serie, "Coolant Temperature", e["t_inicio_ms"], e["t_fin_ms"])
        assert temp, "ventana vacía"
        for t in temp:
            assert t > UMBRAL_K, f"{t - 273.15:.1f} °C no supera el umbral"
        assert e["t_fin_ms"] - e["t_inicio_ms"] >= 3000, (
            "el positivo debe superar la permanencia de 3 s"
        )
    for e in eventos_de(verdad, "D9", False):
        assert e["t_fin_ms"] - e["t_inicio_ms"] < 3000, (
            "el negativo debe durar MENOS que la permanencia de 3 s"
        )
        temp = vals(serie, "Coolant Temperature", e["t_inicio_ms"], e["t_fin_ms"])
        # Sí está por encima del umbral: lo que lo salva es la duración, y eso es
        # exactamente lo que la prueba tiene que fijar.
        assert all(t > UMBRAL_K for t in temp)


def test_d10_presion_de_aceite_contra_la_curva(verdad: dict, serie: dict) -> None:
    """El caso que justifica que el umbral sea una curva y no un valor fijo."""

    def minima(rpm: float) -> float:
        return 101.3 + 100.0 + (rpm / 1000.0) * 100.0

    for e in eventos_de(verdad, "D10", True):
        idxs = ventana(serie, e["t_inicio_ms"], e["t_fin_ms"])
        assert idxs, "ventana vacía"
        for i in idxs:
            p = serie["datos"]["Oil Pressure"][i]
            r = serie["datos"]["RPM"][i]
            assert p < minima(r), f"{p} kPa a {r} rpm NO está bajo la curva ({minima(r):.0f})"
    for e in eventos_de(verdad, "D10", False):
        idxs = ventana(serie, e["t_inicio_ms"], e["t_fin_ms"])
        assert idxs, "ventana vacía"
        for i in idxs:
            p = serie["datos"]["Oil Pressure"][i]
            r = serie["datos"]["RPM"][i]
            assert p >= minima(r), (
                f"{p} kPa a {r} rpm sí está bajo la curva: el caso negativo es inválido"
            )
            # Y debe ser un valor BAJO en términos absolutos, o no prueba nada:
            # el punto es que un umbral plano lo marcaría en falso.
            assert p < 400.0, f"{p} kPa no es lo bastante bajo para ser un casi-positivo"


def test_d11_baja_tension_con_motor_en_marcha(verdad: dict, serie: dict) -> None:
    for e in eventos_de(verdad, "D11", True):
        idxs = ventana(serie, e["t_inicio_ms"], e["t_fin_ms"])
        assert idxs, "ventana vacía"
        for i in idxs:
            assert serie["datos"]["Battery Voltage"][i] < 11.5
            assert serie["datos"]["RPM"][i] > 500, "el motor debe estar en marcha"


def test_d12_bit_de_error_de_trigger(verdad: dict, serie: dict) -> None:
    for e in eventos_de(verdad, "D12", True):
        v = vals(serie, "Trigger System Errors", e["t_inicio_ms"], e["t_fin_ms"])
        assert v and all(x != 0 for x in v), "la máscara de trigger no tiene ningún bit activo"
    # Fuera de las ventanas anotadas la máscara debe estar limpia, o el detector
    # generaría incidencias que la verdad de referencia no declara.
    ventanas = [(e["t_inicio_ms"], e["t_fin_ms"]) for e in eventos_de(verdad, "D12", True)]
    for i, t in enumerate(serie["marcas"]):
        if any(t0 <= t < t1 for t0, t1 in ventanas):
            continue
        assert serie["datos"]["Trigger System Errors"][i] == 0, (
            f"bit de trigger activo en {t} ms, fuera de toda ventana anotada"
        )


def test_d13_y_d14_proteccion_y_corte(verdad: dict, serie: dict) -> None:
    for e in eventos_de(verdad, "D13", True):
        v = vals(serie, "Engine Protection Severity Level", e["t_inicio_ms"], e["t_fin_ms"])
        assert v and all(x > 0 for x in v)
    for e in eventos_de(verdad, "D14", True):
        v = vals(serie, "Cut Percentage", e["t_inicio_ms"], e["t_fin_ms"])
        assert v and all(x > 0 for x in v)


def test_d18_hueco_de_muestreo(verdad: dict, serie: dict) -> None:
    marcas = serie["marcas"]
    dts = [marcas[i + 1] - marcas[i] for i in range(len(marcas) - 1)]
    mediana = statistics.median(dts)
    huecos = [marcas[i] for i, d in enumerate(dts) if d > 3 * mediana]
    anotados = [e["t_inicio_ms"] for e in eventos_de(verdad, "D18", True)]
    assert len(huecos) == len(anotados), (
        f"{len(huecos)} huecos reales frente a {len(anotados)} anotados: {huecos}"
    )
    for h, a in zip(sorted(huecos), sorted(anotados), strict=True):
        assert abs(h - a) <= 50, f"hueco real en {h} ms, anotado en {a} ms"


def test_d3_retardo_por_knock_activo(verdad: dict, serie: dict) -> None:
    for e in eventos_de(verdad, "D3", True):
        v = vals(serie, "Knock Control Bank 1 Ignition Correction", e["t_inicio_ms"], e["t_fin_ms"])
        assert v, "ventana vacía"
        assert min(v) < -1.0, f"la corrección mínima es {min(v)}°, no llega a −1°"


# --------------------------------------------------------------------------- #
# Coherencia física general
# --------------------------------------------------------------------------- #
def test_los_valores_caen_en_los_rangos_plausibles_de_sus_roles(verdad: dict, serie: dict) -> None:
    """El mismo cruce que hace la prueba de F0-10, ahora sobre este fixture."""
    roles = _toml(ROLES)["roles"]
    for c in verdad["canales"]:
        rol = c["rol"]
        if not rol or rol not in roles:
            continue
        p = roles[rol]["plausible"]
        for v in serie["datos"][c["nombre"]]:
            assert p["min"] <= v <= p["max"], (
                f"{c['nombre']} -> {rol}: {v} fuera de [{p['min']}, {p['max']}]"
            )


def test_el_escenario_tiene_ralenti_y_plena_carga(serie: dict) -> None:
    rpm = serie["datos"]["RPM"]
    tps = serie["datos"]["Throttle Position"]
    assert min(rpm) < 1000, "no hay ralentí"
    assert max(rpm) > 6000, "no hay plena carga"
    assert min(tps) == 0.0
    assert max(tps) == 1.0
