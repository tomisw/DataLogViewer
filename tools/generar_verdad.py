#!/usr/bin/env python3
"""Log de verdad de referencia con eventos anotados (tarea F0-07).

Genera un log en formato Haltech `%DataLog% 1.1` con eventos **inyectados en
instantes conocidos**, más un JSON de verdad de referencia que dice qué debe
detectar cada detector de `docs/04-perfiles-motorsport.md` §4.3 y, sobre todo,
**qué NO debe detectar**.

POR QUÉ LOS CASOS NEGATIVOS SON LA MITAD DEL FICHERO

Un detector que dispara siempre tiene cero falsos negativos y es inútil. Lo que
hace que un usuario confíe en el panel de incidencias es que no le avise en
falso, porque una alerta falsa repetida le enseña a ignorar las alertas
(docs/07 §7.15). Por eso cada positivo inyectado va acompañado de un
**casi-positivo** que debe quedarse callado:

    D4  excursión de lambda al 4,1 % (dispara)   y al 3,0 % (no dispara)
    D2  knock sostenido sobre umbral (dispara)   y un pico de una muestra (no)
    D10 presión de aceite baja a 6 000 rpm (sí)  y baja en ralentí (no: la curva
                                                  mínima depende del régimen)
    D8  duty de inyección al 88 % (sí)           y al 83 % (no)
    D9  sobretemperatura sostenida 4 s (sí)      y un pico de 1 s (no)

Todo se escribe con las escalas de origen de `data/formats/haltech_nsp.toml`,
así que el fichero es un log Haltech legítimo y el parser real lo lee sin trato
especial.

Solo biblioteca estándar. Determinista: misma semilla, mismos bytes.

Uso:
    python tools/generar_verdad.py
    python tools/generar_verdad.py --seed 7 --salida samples/verdad
"""

from __future__ import annotations

import argparse
import json
import random
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA_POR_OMISION = RAIZ / "samples" / "verdad"
UMBRALES_TOML = RAIZ / "data" / "umbrales.toml"


def cargar_umbrales() -> dict:
    """Los umbrales son DATOS configurables, no constantes de este guion.

    El fixture coloca cada evento justo a un lado del umbral y cada casi-evento
    justo al otro, así que tiene que leer los mismos valores que leerán los
    detectores. Cablearlos aquí habría creado dos fuentes de verdad que se
    desincronizan en el primer ajuste.
    """
    with UMBRALES_TOML.open("rb") as fh:
        return tomllib.load(fh)


UMBRALES = cargar_umbrales()
DET = UMBRALES["detectores"]

# Derivados de los umbrales configurados: el fixture sitúa cada evento a un lado
# y cada casi-evento al otro, en proporción al umbral y no con números fijos, así
# que sigue siendo válido si el usuario los cambia.
D4_MAX = float(DET["D4"]["desviacion_relativa_max"])
D8_AVISO = float(DET["D8"]["umbral_aviso"])
D8_CRITICO = float(DET["D8"]["umbral_critico"])
D9_MAX_C = float(DET["D9"]["umbral_max_k"]) - 273.15
D11_MIN_V = float(DET["D11"]["umbral_min_v"])

HZ = 20
DT_MS = 1000 // HZ
DURACION_S = 60
N_FILAS = DURACION_S * HZ

# --------------------------------------------------------------------------- #
# Canales: (nombre, ID, Type, DisplayMaxMin, rol)
# Los IDs y los Type son los reales del formato (docs/01 §1.3 y §1.8).
# --------------------------------------------------------------------------- #
CANALES: list[tuple[str, int, str, str, str | None]] = [
    ("RPM", 384, "EngineSpeed", "20000,0", "engine_speed"),
    ("Manifold Pressure", 224, "Pressure", "6013,13", "manifold_pressure"),
    ("Throttle Position", 225, "Percentage", "1000,0", "throttle_position"),
    ("Wideband O2 1", 230, "AFR", "1361,-110", "lambda_measured"),
    ("Target Lambda", 132, "AFR", "1361,476", "lambda_target"),
    ("Fuel Tuning Current Stoichiometry", 14700, "Stoichiometry", "25000,5000", "stoichiometry"),
    ("Knock Sensor 1 Knock Count", 696, "Raw", "50000,0", "knock_count"),
    ("Knock Sensor 2 Knock Count", 697, "Raw", "50000,0", "knock_count"),
    ("Knock Sensor 1 Knock Level", 698, "Decibel", "6000,0", "knock_level"),
    ("Knock Threshold", 699, "Decibel", "6000,0", "knock_threshold"),
    ("Knock Control Bank 1 Ignition Correction", 700, "Angle", "600,-600", "knock_retard"),
    ("Ignition Angle", 518, "Angle", "600,-600", "ignition_advance"),
    ("Injection Stage 1 Average Duty Cycle", 5666, "Percentage", "1000,0", "injector_duty"),
    ("Coolant Temperature", 229, "Temperature", "4731,2331", "coolant_temp"),
    ("Oil Pressure", 236, "Pressure", "31013,1013", "oil_pressure"),
    ("Battery Voltage", 258, "BatteryVoltage", "18000,6500", "battery_voltage"),
    ("Trigger System Errors", 1353, "Raw", "31,0", "trigger_errors"),
    ("Engine Protection Severity Level", 1354, "Raw", "3,0", "protection_level"),
    ("Cut Percentage", 1355, "Percentage", "1000,0", "cut_percentage"),
    ("Boost Control Actual Pressure", 1462, "Pressure", "6013,13", "boost_pressure_actual"),
]

NOMBRE_A_INDICE = {c[0]: i for i, c in enumerate(CANALES)}


@dataclass
class Evento:
    """Un evento anotado de la verdad de referencia."""

    detector: str
    descripcion: str
    t_inicio_ms: int
    t_fin_ms: int
    severidad: str
    debe_disparar: bool
    contexto: dict[str, object] = field(default_factory=dict)


def presion_aceite_minima_kpa(rpm: float) -> float:
    """Curva mínima de presión de aceite en función del régimen (D10).

    Un umbral plano da falsos positivos en ralentí y falsos negativos a alto
    régimen; de ahí que D10 use una curva. Los coeficientes salen de
    `data/umbrales.toml`, que es donde el usuario los puede cambiar.
    """
    c = DET["D10"]["curva_minima"]
    return float(c["base_kpa"]) + (rpm / 1000.0) * float(c["pendiente_kpa_por_1000rpm"])


# --------------------------------------------------------------------------- #
# Escenario
# --------------------------------------------------------------------------- #
def construir(rng: random.Random) -> tuple[list[list[int | None]], list[Evento], list[int]]:
    """Devuelve (filas de valores crudos, eventos anotados, marcas de tiempo ms)."""
    filas: list[list[int | None]] = []
    eventos: list[Evento] = []
    marcas: list[int] = []

    # Contadores acumulados: nunca decrecen (roles.toml, monotono).
    knock1 = 0
    knock2 = 0

    # Tramos: (t_inicio_s, t_fin_s, etiqueta)
    def tramo(t: float) -> str:
        if t < 8:
            return "ralenti"
        if t < 14:
            return "tirada_limpia"
        if t < 18:
            return "decel"
        if t < 26:
            return "tirada_knock"
        if t < 30:
            return "decel"
        if t < 38:
            return "tirada_pobre"
        if t < 42:
            return "decel_casi_pobre"
        if t < 48:
            return "duty_alto"
        if t < 52:
            return "sobretemperatura"
        if t < 55:
            return "baja_tension"
        if t < 58:
            return "fallo_trigger"
        return "ralenti"

    # --- eventos anotados, con sus instantes exactos -----------------------
    # Los tres eventos van en la SEGUNDA MITAD de la tirada, donde el régimen ya
    # pasa de 4 000 rpm y el colector de 150 kPa: es la condición que hace que la
    # severidad de D1 suba a crítica (docs/04 §4.3). Colocarlos antes —como
    # estaban al principio— los dejaba a 2 674 rpm y la anotación de severidad
    # crítica era falsa. Lo cazó tests/test_verdad_referencia.py.
    KNOCK_MS = [21_500, 23_000, 24_500]  # D1: tres eventos en la tirada 2
    KNOCK_PICO_AISLADO_MS = 10_000  # D2 negativo: una sola muestra
    KNOCK_SOSTENIDO_MS = (22_000, 22_600)  # D2 positivo: 600 ms sobre umbral
    POBRE_MS = (32_000, 34_000)  # D4 positivo: +4,1 %
    CASI_POBRE_MS = (39_000, 41_000)  # D4 negativo: +3,0 %
    DUTY_ALTO_MS = (43_000, 45_000)  # D8 positivo: 88 %
    DUTY_CRITICO_MS = (45_000, 46_000)  # D8 crítico: 96 %
    DUTY_CASI_MS = (46_500, 47_500)  # D8 negativo: 83 %
    SOBRETEMP_MS = (48_500, 52_000)  # D9 positivo: 3,5 s por encima
    TEMP_PICO_MS = (12_000, 12_800)  # D9 negativo: 0,8 s, bajo el mínimo
    ACEITE_BAJO_MS = (25_000, 25_600)  # D10 positivo: bajo la curva a alto régimen
    ACEITE_RALENTI_MS = (4_000, 6_000)  # D10 negativo: bajo en ralentí, sobre la curva
    TENSION_BAJA_MS = (52_500, 54_500)  # D11 positivo
    TRIGGER_MS = (55_500, 56_000)  # D12 positivo
    PROTECCION_MS = (56_000, 57_000)  # D13 positivo
    HUECO_MS = 58_000  # D18: hueco de muestreo

    t_ms = 0
    for _ in range(N_FILAS):
        # Hueco de muestreo deliberado: un salto de 400 ms (docs/01 §1.7).
        if t_ms == HUECO_MS:
            t_ms += 400 - DT_MS
        t = t_ms / 1000.0
        et = tramo(t)
        marcas.append(t_ms)

        # --- régimen y carga por tramo ---
        if et == "ralenti":
            rpm = 900 + rng.randint(-20, 20)
            tps = 0
            map_kpa = 33.0 + rng.uniform(-0.5, 0.5)
        elif et.startswith("tirada"):
            inicio = {"tirada_limpia": 8.0, "tirada_knock": 18.0, "tirada_pobre": 30.0}[et]
            frac = min(1.0, (t - inicio) / 7.0)
            rpm = 2000 + frac * 4700 + rng.randint(-15, 15)
            tps = 1000
            map_kpa = 120.0 + frac * 110.0 + rng.uniform(-1.0, 1.0)
        elif et.startswith("decel"):
            rpm = 3000 + rng.randint(-40, 40)
            tps = 0
            map_kpa = 30.0 + rng.uniform(-1.0, 1.0)
        else:
            rpm = 4200 + rng.randint(-40, 40)
            tps = 850
            map_kpa = 190.0 + rng.uniform(-2.0, 2.0)

        # --- objetivo y medida de lambda ---
        target = 0.88 if tps > 700 else 1.00
        lam = target + rng.uniform(-0.004, 0.004)
        if POBRE_MS[0] <= t_ms < POBRE_MS[1]:
            lam = target * (1.0 + D4_MAX * 1.025)  # justo por encima: D4 dispara
        elif CASI_POBRE_MS[0] <= t_ms < CASI_POBRE_MS[1]:
            lam = target * (1.0 + D4_MAX * 0.75)  # justo por debajo: D4 NO dispara

        # --- knock ---
        umbral_db = 34.0 + (map_kpa - 33.0) * 0.07
        nivel_db = umbral_db - 12.0 + rng.uniform(-1.5, 1.5)
        if any(abs(t_ms - k) < DT_MS for k in KNOCK_MS):
            knock1 += 1 + rng.randint(0, 2)
            knock2 += 1
            nivel_db = umbral_db + 6.0
        if t_ms == KNOCK_PICO_AISLADO_MS:
            nivel_db = umbral_db + 8.0  # una sola muestra: D2 NO dispara
        if KNOCK_SOSTENIDO_MS[0] <= t_ms < KNOCK_SOSTENIDO_MS[1]:
            nivel_db = umbral_db + 3.0  # 600 ms seguidos: D2 dispara
        retardo_deg = -3.5 if any(abs(t_ms - k) < 600 for k in KNOCK_MS) else 0.0

        # --- duty de inyección ---
        duty_pct = 18.0 if tps == 0 else 30.0 + (map_kpa / 230.0) * 45.0
        if DUTY_ALTO_MS[0] <= t_ms < DUTY_ALTO_MS[1]:
            duty_pct = (D8_AVISO + 0.03) * 100.0
        elif DUTY_CRITICO_MS[0] <= t_ms < DUTY_CRITICO_MS[1]:
            duty_pct = (D8_CRITICO + 0.01) * 100.0
        elif DUTY_CASI_MS[0] <= t_ms < DUTY_CASI_MS[1]:
            duty_pct = (D8_AVISO - 0.02) * 100.0

        # --- refrigerante ---
        coolant_c = 92.0 + rng.uniform(-0.3, 0.3)
        if SOBRETEMP_MS[0] <= t_ms < SOBRETEMP_MS[1]:
            coolant_c = D9_MAX_C + 2.5
        elif TEMP_PICO_MS[0] <= t_ms < TEMP_PICO_MS[1]:
            coolant_c = 106.5  # solo 0,8 s: D9 NO dispara

        # --- presión de aceite ---
        aceite_kpa = presion_aceite_minima_kpa(rpm) + 120.0
        if ACEITE_BAJO_MS[0] <= t_ms < ACEITE_BAJO_MS[1]:
            aceite_kpa = presion_aceite_minima_kpa(rpm) - 40.0  # bajo la curva: D10 sí
        elif ACEITE_RALENTI_MS[0] <= t_ms < ACEITE_RALENTI_MS[1]:
            aceite_kpa = presion_aceite_minima_kpa(rpm) + 15.0  # baja pero sobre la curva: no

        # --- tensión, trigger, protección, corte ---
        vbat = 13.9 + rng.uniform(-0.05, 0.05)
        if TENSION_BAJA_MS[0] <= t_ms < TENSION_BAJA_MS[1]:
            vbat = D11_MIN_V - 0.3
        trig = 1 if TRIGGER_MS[0] <= t_ms < TRIGGER_MS[1] else 0
        prot = 2 if PROTECCION_MS[0] <= t_ms < PROTECCION_MS[1] else 0
        corte_pct = 25.0 if prot else 0.0
        avance_deg = 8.0 if tps == 0 else 22.0 - (map_kpa / 230.0) * 8.0
        avance_deg += retardo_deg

        # --- a enteros crudos, con las escalas del descriptor -------------
        fila: list[int | None] = [0] * len(CANALES)

        def pon(nombre: str, valor: int, fila: list[int | None] = fila) -> None:
            # `fila` ligada por argumento: no se captura la del bucle (B023).
            fila[NOMBRE_A_INDICE[nombre]] = valor

        pon("RPM", round(rpm))
        pon("Manifold Pressure", round(map_kpa * 10))
        pon("Throttle Position", tps)
        pon("Wideband O2 1", round(lam * 1000))
        pon("Target Lambda", round(target * 1000))
        pon("Fuel Tuning Current Stoichiometry", 14700)
        pon("Knock Sensor 1 Knock Count", knock1)
        pon("Knock Sensor 2 Knock Count", knock2)
        pon("Knock Sensor 1 Knock Level", round(nivel_db * 100))
        pon("Knock Threshold", round(umbral_db * 100))
        pon("Knock Control Bank 1 Ignition Correction", round(retardo_deg * 10))
        pon("Ignition Angle", round(avance_deg * 10))
        pon("Injection Stage 1 Average Duty Cycle", round(duty_pct * 10))
        pon("Coolant Temperature", round((coolant_c + 273.15) * 10))
        pon("Oil Pressure", round(aceite_kpa * 10))
        pon("Battery Voltage", round(vbat * 1000))
        pon("Trigger System Errors", trig)
        pon("Engine Protection Severity Level", prot)
        pon("Cut Percentage", round(corte_pct * 10))
        pon("Boost Control Actual Pressure", round(map_kpa * 10))

        filas.append(fila)
        t_ms += DT_MS

    # --- verdad de referencia ---------------------------------------------
    for k in KNOCK_MS:
        eventos.append(
            Evento(
                detector="D1",
                descripcion="Evento de knock: incremento del contador",
                t_inicio_ms=k,
                t_fin_ms=k + DT_MS,
                severidad="critica",
                debe_disparar=True,
                contexto={"nota": "RPM > 4000 y MAP > 150 kPa: la severidad sube a crítica"},
            )
        )
    eventos.append(
        Evento(
            "D2",
            "Knock sostenido 600 ms por encima del umbral",
            *KNOCK_SOSTENIDO_MS,
            severidad="media",
            debe_disparar=True,
        )
    )
    eventos.append(
        Evento(
            "D2",
            "Pico de knock de UNA sola muestra: por debajo de la permanencia mínima",
            KNOCK_PICO_AISLADO_MS,
            KNOCK_PICO_AISLADO_MS + DT_MS,
            severidad="ninguna",
            debe_disparar=False,
            contexto={"nota": "50 ms < 100 ms de permanencia mínima (docs/04 §4.3)"},
        )
    )
    eventos.append(
        Evento(
            "D3",
            "Retardo por knock activo: corrección de encendido negativa",
            KNOCK_MS[0],
            KNOCK_MS[-1] + 600,
            severidad="media",
            debe_disparar=True,
        )
    )
    eventos.append(
        Evento(
            "D4",
            "Mezcla pobre en carga: lambda 4,1 % sobre objetivo con TPS 100 %",
            *POBRE_MS,
            severidad="critica",
            debe_disparar=True,
        )
    )
    eventos.append(
        Evento(
            "D4",
            "Lambda 3,0 % sobre objetivo: por debajo del umbral del 4 %",
            *CASI_POBRE_MS,
            severidad="ninguna",
            debe_disparar=False,
            contexto={"nota": "y además con TPS 0: la condición de carga tampoco se cumple"},
        )
    )
    eventos.append(
        Evento(
            "D8", "Duty de inyección al 88 %", *DUTY_ALTO_MS, severidad="alta", debe_disparar=True
        )
    )
    eventos.append(
        Evento(
            "D8",
            "Duty de inyección al 96 %",
            *DUTY_CRITICO_MS,
            severidad="critica",
            debe_disparar=True,
        )
    )
    eventos.append(
        Evento(
            "D8",
            "Duty al 83 %: por debajo del umbral del 85 %",
            *DUTY_CASI_MS,
            severidad="ninguna",
            debe_disparar=False,
        )
    )
    eventos.append(
        Evento(
            "D9",
            "Sobretemperatura de refrigerante 107,5 °C durante 3,5 s",
            *SOBRETEMP_MS,
            severidad="alta",
            debe_disparar=True,
        )
    )
    eventos.append(
        Evento(
            "D9",
            "Pico de 106,5 °C durante 0,8 s: por debajo de la permanencia de 3 s",
            *TEMP_PICO_MS,
            severidad="ninguna",
            debe_disparar=False,
        )
    )
    eventos.append(
        Evento(
            "D10",
            "Presión de aceite bajo la curva mínima a alto régimen",
            *ACEITE_BAJO_MS,
            severidad="critica",
            debe_disparar=True,
            contexto={"nota": "la curva es 1 bar + 1 bar/1000 rpm; aquí queda 40 kPa por debajo"},
        )
    )
    eventos.append(
        Evento(
            "D10",
            "Presión de aceite baja en ralentí pero SOBRE la curva",
            *ACEITE_RALENTI_MS,
            severidad="ninguna",
            debe_disparar=False,
            contexto={"nota": "el caso que un umbral plano marcaría en falso"},
        )
    )
    eventos.append(
        Evento(
            "D11",
            "Tensión de batería 11,2 V con el motor en marcha",
            *TENSION_BAJA_MS,
            severidad="media",
            debe_disparar=True,
        )
    )
    eventos.append(
        Evento(
            "D12",
            "Bit de error de trigger activo",
            *TRIGGER_MS,
            severidad="critica",
            debe_disparar=True,
        )
    )
    eventos.append(
        Evento(
            "D13",
            "Protección de motor en nivel 2",
            *PROTECCION_MS,
            severidad="alta",
            debe_disparar=True,
        )
    )
    eventos.append(
        Evento(
            "D14",
            "Corte activo al 25 % durante la protección",
            *PROTECCION_MS,
            severidad="media",
            debe_disparar=True,
        )
    )
    eventos.append(
        Evento(
            "D18",
            "Hueco de muestreo de 400 ms",
            HUECO_MS,
            HUECO_MS + 400,
            severidad="informativa",
            debe_disparar=True,
            contexto={"nota": "8x el dt nominal de 50 ms"},
        )
    )

    return filas, eventos, marcas


# --------------------------------------------------------------------------- #
# Escritura
# --------------------------------------------------------------------------- #
def escribir_log(ruta: Path, filas: list[list[int | None]], marcas: list[int]) -> None:
    lineas: list[str] = [
        "%DataLog%",
        "DataLogVersion : 1.1",
        "Software : Haltech NSP",
        "SoftwareVersion : 999.999.999.999",
        "DownloadDateTime : 20260729 06:00:00",
    ]
    for nombre, canal_id, tipo, maxmin, _rol in CANALES:
        lineas.append(f"Channel : {nombre}")
        lineas.append(f"ID : {canal_id}")
        lineas.append(f"Type : {tipo}")
        lineas.append(f"DisplayMaxMin : {maxmin}")
    lineas.append("Log Source : 0")
    lineas.append("Log Number : 0")
    # Hora de cabecera en 12 h, como el formato real (docs/01 §1.4).
    lineas.append("Log : 20260729 06:00:00")

    for marca, fila in zip(marcas, filas, strict=True):
        h, resto = divmod(marca, 3_600_000)
        m, resto = divmod(resto, 60_000)
        s, ms = divmod(resto, 1000)
        sello = f"{18 + h:02d}:{m:02d}:{s:02d}.{ms:03d}"
        valores = ",".join("" if v is None else str(v) for v in fila)
        lineas.append(f"{sello},{valores}")

    # CRLF: es el final de línea nativo del formato (docs/01 §1.13).
    ruta.write_bytes(("\r\n".join(lineas) + "\r\n").encode("utf-8"))


def escribir_verdad(ruta: Path, eventos: list[Evento], filas: list[list[int | None]]) -> None:
    positivos = [e for e in eventos if e.debe_disparar]
    negativos = [e for e in eventos if not e.debe_disparar]
    datos = {
        "tarea": "F0-07",
        "especificacion": "docs/04-perfiles-motorsport.md §4.3",
        "log": "verdad.csv",
        "formato": "haltech_nsp",
        "muestreo_hz": HZ,
        "n_filas": len(filas),
        "duracion_s": DURACION_S,
        "canales": [{"nombre": n, "id": i, "type": t, "rol": r} for n, i, t, _mm, r in CANALES],
        "umbrales": {
            "origen": "data/umbrales.toml",
            "nota": (
                "Los umbrales son configurables (perfil > usuario > por omisión). "
                "El fixture sitúa cada evento a un lado del umbral vigente y cada "
                "casi-evento al otro, en proporción, no con valores fijos."
            ),
            "vigentes": {
                "D4_desviacion_relativa_max": D4_MAX,
                "D8_umbral_aviso": D8_AVISO,
                "D8_umbral_critico": D8_CRITICO,
                "D9_umbral_max_c": round(D9_MAX_C, 2),
                "D11_umbral_min_v": D11_MIN_V,
                "D10_curva": DET["D10"]["curva_minima"],
            },
        },
        "resumen": {
            "eventos_totales": len(eventos),
            "deben_disparar": len(positivos),
            "no_deben_disparar": len(negativos),
            "detectores_cubiertos": sorted({e.detector for e in eventos}),
        },
        "eventos": [
            {
                "detector": e.detector,
                "descripcion": e.descripcion,
                "t_inicio_ms": e.t_inicio_ms,
                "t_fin_ms": e.t_fin_ms,
                "severidad_esperada": e.severidad,
                "debe_disparar": e.debe_disparar,
                "contexto": e.contexto,
            }
            for e in sorted(eventos, key=lambda x: (x.t_inicio_ms, x.detector))
        ],
    }
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def escribir_readme(ruta: Path, eventos: list[Evento]) -> None:
    pos = [e for e in eventos if e.debe_disparar]
    neg = [e for e in eventos if not e.debe_disparar]
    L = [
        "# Log de verdad de referencia (F0-07)",
        "",
        "`verdad.csv` es un log Haltech legítimo con eventos inyectados en instantes",
        "conocidos. `verdad.json` dice qué debe detectar cada detector de",
        "`docs/04-perfiles-motorsport.md` §4.3 **y qué no debe detectar**.",
        "",
        "Sin este fichero no se puede afirmar que los detectores funcionan. La tarea",
        "F3-09 lo consume para validarlos, en formato nativo y en CSV genérico.",
        "",
        "## Por qué la mitad son casos negativos",
        "",
        "Un detector que dispara siempre tiene cero falsos negativos y es inútil. Lo",
        "que hace que un usuario confíe en el panel de incidencias es que no le avise",
        "en falso: una alerta falsa repetida le enseña a ignorar las alertas. Por eso",
        "cada positivo lleva su casi-positivo, situado justo al otro lado del umbral.",
        "",
        f"## Deben disparar ({len(pos)})",
        "",
        "| Detector | t (s) | Severidad | Descripción |",
        "|---|---|---|---|",
    ]
    for e in sorted(pos, key=lambda x: x.t_inicio_ms):
        L.append(
            f"| {e.detector} | {e.t_inicio_ms / 1000:.2f}–{e.t_fin_ms / 1000:.2f} "
            f"| {e.severidad} | {e.descripcion} |"
        )
    L += [
        "",
        f"## NO deben disparar ({len(neg)})",
        "",
        "| Detector | t (s) | Por qué no |",
        "|---|---|---|",
    ]
    for e in sorted(neg, key=lambda x: x.t_inicio_ms):
        motivo = e.contexto.get("nota", e.descripcion)
        L.append(
            f"| {e.detector} | {e.t_inicio_ms / 1000:.2f}–{e.t_fin_ms / 1000:.2f} | {motivo} |"
        )
    L += [
        "",
        "## Tramos del escenario",
        "",
        "| t (s) | Tramo |",
        "|---|---|",
        "| 0–8 | ralentí caliente |",
        "| 8–14 | tirada a plena carga limpia |",
        "| 18–26 | tirada con tres eventos de knock |",
        "| 30–38 | tirada con excursión de mezcla pobre |",
        "| 42–48 | duty de inyección alto |",
        "| 48–52 | sobretemperatura de refrigerante |",
        "| 52–55 | baja tensión de batería |",
        "| 55–58 | error de trigger y protección de motor |",
        "| 58 | hueco de muestreo de 400 ms |",
        "",
    ]
    ruta.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--seed", type=int, default=20260729)
    p.add_argument("--salida", type=Path, default=SALIDA_POR_OMISION)
    args = p.parse_args()

    args.salida.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    filas, eventos, marcas = construir(rng)

    escribir_log(args.salida / "verdad.csv", filas, marcas)
    escribir_verdad(args.salida / "verdad.json", eventos, filas)
    escribir_readme(args.salida / "README.md", eventos)

    pos = sum(1 for e in eventos if e.debe_disparar)
    neg = len(eventos) - pos
    print(f"{args.salida.relative_to(RAIZ)}/")
    print(f"  verdad.csv   {len(filas)} filas, {len(CANALES)} canales, {DURACION_S} s a {HZ} Hz")
    print(f"  verdad.json  {len(eventos)} eventos: {pos} deben disparar, {neg} no deben")
    print(f"  detectores cubiertos: {', '.join(sorted({e.detector for e in eventos}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
