#!/usr/bin/env python3
"""Generador del fixture de dos formatos equivalentes (tarea F0-13).

Produce, a partir de un único vector de valores canónicos, dos ficheros con
el **mismo contenido físico**:

1. `samples/dos-formatos/nativo.csv` — formato Haltech `%DataLog% 1.1`
   (docs/01-formato-log.md §1.3), enteros crudos con la escala de origen de
   cada `Type` (docs/01 §1.8).
2. `samples/dos-formatos/generico.csv` — CSV «cualquiera»: delimitador `;`,
   decimal coma, fila de unidades, nombres distintos a los de Haltech, tiempo
   relativo en segundos, valores ya en unidades de ingeniería
   (docs/07-formatos-y-csv-generico.md §7.6).

Junto con `anotaciones.json` (verdad de referencia para
`tests/test_dos_formatos.py` y para la fase FG) y `README.md`.

El motivo de existir de esta tarea es demostrar que la indirección por roles
semánticos (docs/07 §7.7, §7.11) hace que perfiles y detectores funcionen
igual sobre cualquier CSV: el mismo contenido, en dos formatos, debe dar los
mismos valores canónicos.

Solo biblioteca estándar. Determinista: `--seed` fijo, sin reloj de pared en
el contenido de ningún fichero (ni siquiera en README.md, que también se
genera aquí para que no pueda desincronizarse de los datos reales).

Los factores de escala del lado nativo son los de docs/01-formato-log.md
§1.8 (tabla «Confirmados»); no viven en `data/formats/<formato>.toml` porque
esa tarea (F0-09) es de otro agente y este script no debe tocar `data/`. Las
unidades canónicas y las conversiones afines del lado genérico sí se leen de
`data/units.toml` (F0-08, ya aprobado): es la referencia pedida por la propia
tarea, y evita duplicar constantes que ya viven en un fichero de datos
versionado.

Uso:
    python tools/generar_dos_formatos.py
    python tools/generar_dos_formatos.py --seed 20260729 --output samples/dos-formatos
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
UNITS_TOML = RAIZ / "data" / "units.toml"
OUT_DIR_DEFAULT = RAIZ / "samples" / "dos-formatos"

# Semilla fija por defecto: no depende de la fecha de ejecución a propósito,
# para que el fixture no cambie sola con el paso de los días.
SEED_DEFAULT = 20260729

N_ROWS = 300
HZ = 20
DT_MS = 1000 // HZ  # 50 ms, 20 Hz
DURACION_S = (N_ROWS - 1) * DT_MS / 1000

# Hora de inicio de las filas de datos: la misma epoch ficticia 19800101
# 01:01:01 de los logs internos reales de muestra (docs/01 §1.5), a propósito,
# para que este fixture encaje en la misma familia que `samples/real/` y
# `samples/synth/internal-x20/`.
START_H, START_M, START_S, START_MS = 1, 1, 1, 5
START_TOTAL_MS = ((START_H * 60 + START_M) * 60 + START_S) * 1000 + START_MS

LOG_SOURCE = 8
LOG_NUMBER = 9013  # arbitrario, fuera del rango 2768/2769 de las muestras reales

CRLF = "\r\n"


# --------------------------------------------------------------------------- #
# Catálogo de canales: rol semántico, identidad nativa Haltech, columna
# genérica. El orden de la lista fija el orden de columnas en ambos ficheros
# (docs/01-formato-log.md §1.3: el orden de los bloques Channel define el
# orden de las columnas de datos).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Canal:
    rol: str
    dimension: str  # clave en data/units.toml -> dimensiones.<dimension>
    # --- lado nativo (Haltech) ---
    nativo_nombre: str
    nativo_id: int
    nativo_type: str
    nativo_display_max_min: str
    divisor_nativo: int  # canonica = raw_entero / divisor_nativo
    # --- lado genérico ---
    generico_nombre: str
    generico_unidad: str  # clave en dimensiones.<dimension>.unidades
    generico_decimales: int  # precisión de escritura elegida para ida y vuelta exacta


CANALES: tuple[Canal, ...] = (
    Canal(
        rol="engine_speed",
        dimension="angular_speed",
        nativo_nombre="RPM",
        nativo_id=384,
        nativo_type="EngineSpeed",
        nativo_display_max_min="20000,0",
        divisor_nativo=1,
        generico_nombre="Régimen",
        generico_unidad="rpm",
        generico_decimales=0,
    ),
    Canal(
        rol="manifold_pressure",
        dimension="pressure",
        nativo_nombre="Manifold Pressure",
        nativo_id=224,
        nativo_type="Pressure",
        nativo_display_max_min="6013,13",
        divisor_nativo=10,
        generico_nombre="Presión colector",
        generico_unidad="kPa",
        generico_decimales=1,
    ),
    Canal(
        rol="throttle_position",
        dimension="ratio",
        nativo_nombre="Throttle Position",
        nativo_id=225,
        nativo_type="Percentage",
        nativo_display_max_min="1000,0",
        divisor_nativo=1000,  # canónica = fracción (0..1); ver docs/01 §1.8 + tarea
        generico_nombre="Mariposa",
        generico_unidad="pct",
        generico_decimales=1,
    ),
    Canal(
        rol="coolant_temp",
        dimension="temperature",
        nativo_nombre="Coolant Temperature",
        nativo_id=229,
        nativo_type="Temperature",
        nativo_display_max_min="4731,2331",
        divisor_nativo=10,  # canónica K = raw / 10 (deciKelvin)
        generico_nombre="Temp. refrigerante",
        generico_unidad="degC",
        generico_decimales=2,
    ),
    Canal(
        rol="intake_air_temp",
        dimension="temperature",
        nativo_nombre="Intake Air Temperature",
        nativo_id=228,
        nativo_type="Temperature",
        nativo_display_max_min="4731,2331",
        divisor_nativo=10,
        generico_nombre="Temp. aire",
        generico_unidad="degC",
        generico_decimales=2,
    ),
    Canal(
        rol="lambda_measured",
        dimension="mixture_ratio",
        nativo_nombre="Wideband O2 1",
        nativo_id=230,
        nativo_type="AFR",  # el tipo se llama AFR pero contiene lambda (docs/01 §1.8)
        nativo_display_max_min="1361,-110",
        divisor_nativo=1000,
        generico_nombre="Lambda",
        generico_unidad="lambda",
        generico_decimales=3,
    ),
    Canal(
        rol="lambda_target",
        dimension="mixture_ratio",
        nativo_nombre="Target Lambda",
        nativo_id=132,
        nativo_type="AFR",
        nativo_display_max_min="1361,476",
        divisor_nativo=1000,
        generico_nombre="Lambda objetivo",
        generico_unidad="lambda",
        generico_decimales=3,
    ),
    Canal(
        rol="ignition_advance",
        dimension="angle",
        nativo_nombre="Ignition Angle",
        nativo_id=518,
        nativo_type="Angle",
        nativo_display_max_min="600,-600",
        divisor_nativo=10,
        generico_nombre="Avance",
        generico_unidad="deg",
        generico_decimales=1,
    ),
    Canal(
        rol="oil_pressure",
        dimension="pressure",
        nativo_nombre="Oil Pressure",
        nativo_id=236,
        nativo_type="Pressure",
        nativo_display_max_min="31013,1013",
        divisor_nativo=10,
        generico_nombre="Presión aceite",
        generico_unidad="kPa",
        generico_decimales=1,
    ),
    Canal(
        rol="battery_voltage",
        dimension="voltage",
        nativo_nombre="Battery Voltage",
        nativo_id=258,
        nativo_type="BatteryVoltage",
        nativo_display_max_min="18000,6500",
        divisor_nativo=1000,
        generico_nombre="Tensión batería",
        generico_unidad="V",
        generico_decimales=3,
    ),
)

# Canales cuya conversión declarada del lado genérico encadena dos
# operaciones decimales (escala + desplazamiento, o escala != 1) en vez de
# ser la canónica cruda. Ida y vuelta exacta en `decimal.Decimal` (lo que
# hace este generador); en coma flotante IEEE-754 de doble precisión puede
# aparecer un error de redondeo de un ULP (~1e-13 en estas magnitudes) al
# encadenar dos redondeos independientes. Ver README.md y
# `tests/test_dos_formatos.py`.
ROLES_CON_CONVERSION_ENCADENADA = frozenset(
    {"throttle_position", "coolant_temp", "intake_air_temp"}
)


# --------------------------------------------------------------------------- #
# Catálogo de unidades (data/units.toml, F0-08) — solo lectura.
# --------------------------------------------------------------------------- #


def cargar_catalogo_unidades() -> dict[str, Any]:
    with UNITS_TOML.open("rb") as fh:
        return tomllib.load(fh)


def afin_desde_canonica(
    catalogo: dict[str, Any], dimension: str, unidad: str
) -> tuple[Decimal, Decimal]:
    """(a, b) de `desde_canonica` para dimension.unidad: mostrado = a * canonica + b."""
    conv = catalogo["dimensiones"][dimension]["unidades"][unidad]["desde_canonica"]
    if conv["tipo"] != "afin":
        raise ValueError(f"{dimension}.{unidad} no es una conversión afín: {conv}")
    # str(...) recupera el decimal exacto tal como está escrito en el TOML: los
    # valores de esta tabla son literales limpios (273.15, 100.0, ...), y el
    # repr más corto de Python para el float que produce tomllib coincide con
    # ese literal. Pasar por Decimal(a_float) directamente arrastraría el
    # error de redondeo binario del float.
    return Decimal(str(conv["a"])), Decimal(str(conv["b"]))


# --------------------------------------------------------------------------- #
# Física sintética: perfil ralentí -> plena carga -> sostenido, con ruido
# determinista. Todo el ruido se consume de un único `random.Random(seed)`,
# en un orden fijo (fila por fila, canal por canal en el orden de `CANALES`),
# para que dos ejecuciones con la misma semilla sean idénticas.
# --------------------------------------------------------------------------- #


def carga(t_s: float) -> float:
    """Fracción de carga L(t) en [0, 1]: ralentí (0-2 s) -> rampa (2-12 s) -> WOT (12-15 s)."""
    if t_s < 2.0:
        return 0.0
    if t_s < 12.0:
        return (t_s - 2.0) / 10.0
    return 1.0


def generar_crudos(rng: random.Random) -> dict[str, list[int]]:
    """Genera, en el orden fijo fila/canal, los 300 valores enteros crudos de cada rol."""
    crudos: dict[str, list[int]] = {c.rol: [] for c in CANALES}

    for i in range(N_ROWS):
        t = i * DT_MS / 1000.0
        carga_t = carga(t)

        rpm = 900.0 + carga_t * (6000.0 - 900.0) + rng.uniform(-15.0, 15.0)
        rpm = max(700.0, rpm)
        crudos["engine_speed"].append(round(rpm))

        map_kpa = 33.0 + carga_t * (220.0 - 33.0) + rng.uniform(-0.6, 0.6)
        map_kpa = max(15.0, map_kpa)
        crudos["manifold_pressure"].append(round(map_kpa * 10))

        tps_pct = carga_t * 100.0  # entrada de conductor: sin ruido, escalón limpio
        crudos["throttle_position"].append(round(tps_pct * 10))

        clt_c = 85.0 + 3.0 * (t / DURACION_S) + rng.uniform(-0.08, 0.08)
        crudos["coolant_temp"].append(round((clt_c + 273.15) * 10))

        iat_c = 35.0 + 7.0 * (t / DURACION_S) + rng.uniform(-0.1, 0.1)
        crudos["intake_air_temp"].append(round((iat_c + 273.15) * 10))

        lambda_medido = 1.00 - 0.15 * carga_t + rng.uniform(-0.01, 0.01)
        lambda_medido = min(1.05, max(0.80, lambda_medido))
        crudos["lambda_measured"].append(round(lambda_medido * 1000))

        lambda_obj = 1.00 - 0.14 * carga_t  # canal comandado: sin ruido de sensor
        crudos["lambda_target"].append(round(lambda_obj * 1000))

        avance_deg = 10.0 + 15.0 * carga_t + rng.uniform(-0.3, 0.3)
        crudos["ignition_advance"].append(round(avance_deg * 10))

        oil_kpa = 150.0 + carga_t * 250.0 + rng.uniform(-3.0, 3.0)
        oil_kpa = max(50.0, oil_kpa)
        crudos["oil_pressure"].append(round(oil_kpa * 10))

        vbat = 14.0 - 0.15 * carga_t + rng.uniform(-0.05, 0.05)
        crudos["battery_voltage"].append(round(vbat * 1000))

    return crudos


# --------------------------------------------------------------------------- #
# Crudo -> canónica (Decimal exacto: el divisor siempre es una potencia de 10).
# --------------------------------------------------------------------------- #


def crudo_a_canonica(raw: int, divisor: int) -> Decimal:
    return Decimal(raw) / Decimal(divisor)


# --------------------------------------------------------------------------- #
# Escritura de `nativo.csv`
# --------------------------------------------------------------------------- #


def formatear_tiempo_nativo(indice_fila: int) -> str:
    total_ms = START_TOTAL_MS + indice_fila * DT_MS
    h, resto = divmod(total_ms, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, ms = divmod(resto, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def escribir_nativo(ruta: Path, crudos: dict[str, list[int]]) -> None:
    lineas: list[str] = [
        "%DataLog%",
        "DataLogVersion : 1.1",
        "Software : Haltech NSP",
        "SoftwareVersion : 999.999.999.999",
        "DownloadDateTime : 19800101 01:02:00",
    ]
    for c in CANALES:
        lineas.append(f"Channel : {c.nativo_nombre}")
        lineas.append(f"ID : {c.nativo_id}")
        lineas.append(f"Type : {c.nativo_type}")
        lineas.append(f"DisplayMaxMin : {c.nativo_display_max_min}")
    lineas.append(f"Log Source : {LOG_SOURCE}")
    lineas.append(f"Log Number : {LOG_NUMBER}")
    lineas.append("Log : 19800101 01:01:01")

    for i in range(N_ROWS):
        valores = ",".join(str(crudos[c.rol][i]) for c in CANALES)
        lineas.append(f"{formatear_tiempo_nativo(i)},{valores}")

    # El formato nativo es CRLF (docs/01-formato-log.md §1.13), con CRLF final.
    ruta.write_text(CRLF.join(lineas) + CRLF, encoding="ascii")


# --------------------------------------------------------------------------- #
# Escritura de `generico.csv`
# --------------------------------------------------------------------------- #


def formatear_decimal_coma(valor: Decimal, decimales: int) -> str:
    cuantizado = valor.quantize(Decimal(1).scaleb(-decimales))
    texto = f"{cuantizado:f}"
    return texto.replace(".", ",")


def escribir_generico(
    ruta: Path,
    catalogo: dict[str, Any],
    crudos: dict[str, list[int]],
) -> None:
    nombres = ["Tiempo"] + [c.generico_nombre for c in CANALES]
    unidades_por_canal = []
    for c in CANALES:
        etiqueta = catalogo["dimensiones"][c.dimension]["unidades"][c.generico_unidad]["etiqueta"]
        unidades_por_canal.append(etiqueta if etiqueta else c.generico_unidad)
    unidades = ["s", *unidades_por_canal]

    lineas = [";".join(nombres), ";".join(unidades)]

    afines = {c.rol: afin_desde_canonica(catalogo, c.dimension, c.generico_unidad) for c in CANALES}

    for i in range(N_ROWS):
        t_s = Decimal(i) * Decimal("0.05")
        campos = [formatear_decimal_coma(t_s, 3)]
        for c in CANALES:
            canonica = crudo_a_canonica(crudos[c.rol][i], c.divisor_nativo)
            a, b = afines[c.rol]
            mostrado = a * canonica + b
            campos.append(formatear_decimal_coma(mostrado, c.generico_decimales))
        lineas.append(";".join(campos))

    # LF: el genérico representa "un CSV cualquiera" ajeno a la convención
    # CRLF del formato nativo Haltech.
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Vector canónico esperado + hash de verificación para FG-16.
# --------------------------------------------------------------------------- #

# Nº de decimales usados al formatear el vector canónico para el hash: más
# que suficiente para las tres cifras significativas de mayor precisión de
# este fixture (lambda y tensión, /1000) sin arrastrar ruido de Decimal.
HASH_DECIMALES = 6


def canonicas_todas(crudos: dict[str, list[int]]) -> dict[str, list[Decimal]]:
    return {c.rol: [crudo_a_canonica(v, c.divisor_nativo) for v in crudos[c.rol]] for c in CANALES}


def calcular_hash(canonicas: dict[str, list[Decimal]]) -> str:
    """sha256 de las 10x300 canónicas, en el orden fijo de `CANALES`.

    Receta (reproducible sin este script, ver README.md):
    para cada rol en el orden de `CANALES`, cada valor formateado con
    `HASH_DECIMALES` decimales (punto, sin agrupador de miles), los 300
    valores de un rol unidos por ',', los roles unidos por '|'.
    """
    partes = []
    for c in CANALES:
        valores = canonicas[c.rol]
        cuantizados = [str(v.quantize(Decimal(1).scaleb(-HASH_DECIMALES))) for v in valores]
        partes.append(",".join(cuantizados))
    cadena = "|".join(partes)
    return hashlib.sha256(cadena.encode("ascii")).hexdigest()


# --------------------------------------------------------------------------- #
# `anotaciones.json`
# --------------------------------------------------------------------------- #


def escribir_anotaciones(
    ruta: Path,
    canonicas: dict[str, list[Decimal]],
    hash_hex: str,
) -> None:
    columna_nativa = {c.rol: i + 1 for i, c in enumerate(CANALES)}  # 0 = tiempo
    columna_generica = {c.rol: i + 1 for i, c in enumerate(CANALES)}  # 0 = Tiempo

    canales_json = []
    for c in CANALES:
        tolerancia = 1e-9 if c.rol in ROLES_CON_CONVERSION_ENCADENADA else 0.0
        canales_json.append(
            {
                "rol": c.rol,
                "dimension": c.dimension,
                "nativo": {
                    "columna": columna_nativa[c.rol],
                    "nombre": c.nativo_nombre,
                    "id": c.nativo_id,
                    "type": c.nativo_type,
                    "display_max_min": c.nativo_display_max_min,
                    "escala_origen": f"canonica = crudo / {c.divisor_nativo}",
                },
                "generico": {
                    "columna": columna_generica[c.rol],
                    "nombre": c.generico_nombre,
                    "unidad_declarada": c.generico_unidad,
                    "decimales_escritura": c.generico_decimales,
                },
                "tolerancia_canonica": tolerancia,
            }
        )

    # Vector completo de valores canónicos esperados para 3 canales
    # representativos (uno de cada "familia" de escala: entero directo,
    # división simple, división + desplazamiento), más el hash de los 10.
    vectores_ejemplo = {
        rol: [float(v) for v in canonicas[rol]]
        for rol in ("engine_speed", "manifold_pressure", "lambda_measured")
    }

    contenido = {
        "tarea": "F0-13",
        "n_filas": N_ROWS,
        "muestreo_hz": HZ,
        "duracion_s": DURACION_S,
        "roles": [c.rol for c in CANALES],
        "canales": canales_json,
        "canonicas_esperadas": {
            "vectores_ejemplo": vectores_ejemplo,
            "hash_sha256_todos_los_roles": hash_hex,
            "hash_receta": (
                "sha256 de, para cada rol en el orden de la lista `roles` de este "
                "fichero: los 300 valores canonicos formateados con "
                f"{HASH_DECIMALES} decimales (punto decimal, sin separador de miles), "
                "unidos por ',', y los roles unidos por '|'; ver "
                "`calcular_hash()` en tools/generar_dos_formatos.py."
            ),
        },
    }
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# `README.md`
# --------------------------------------------------------------------------- #


def escribir_readme(ruta: Path, hash_hex: str) -> None:
    filas_crosswalk = "\n".join(
        f"| `{c.rol}` | {c.nativo_nombre} (ID {c.nativo_id}, `{c.nativo_type}`) | "
        f"col. {i + 1} nativa: crudo÷{c.divisor_nativo} | "
        f"{c.generico_nombre} | col. {i + 1} genérica: `{c.generico_unidad}`, "
        f"{c.generico_decimales} dec. |"
        for i, c in enumerate(CANALES)
    )

    exactos = ", ".join(
        f"`{c.rol}`" for c in CANALES if c.rol not in ROLES_CON_CONVERSION_ENCADENADA
    )
    encadenados = ", ".join(
        f"`{c.rol}`" for c in CANALES if c.rol in ROLES_CON_CONVERSION_ENCADENADA
    )

    contenido = f"""# Log equivalente en dos formatos — fixture de independencia de fabricante (F0-13)

## Qué demuestra este par de ficheros

`nativo.csv` (Haltech `%DataLog% 1.1`) y `generico.csv` (CSV `;`, decimal
coma, nombres distintos, tiempo relativo) codifican el **mismo contenido
físico**: {N_ROWS} filas a {HZ} Hz (~{DURACION_S:.2f} s) de una tirada
ralentí → plena carga → sostenido, en 10 canales.

La afirmación que este fixture pone a prueba (docs/07-formatos-y-csv-generico.md
§7.7, §7.11) es que perfiles y detectores funcionan igual sobre cualquiera de
los dos, porque el emparejamiento es por **rol semántico**, no por nombre ni
por `ID` de fabricante. `tests/test_dos_formatos.py` (fase FG-16) aplica la
escala de origen del nativo y la unidad declarada del genérico y comprueba
que ambos caminos llegan al **mismo valor canónico**, canal por canal y fila
por fila.

Los nombres del genérico son deliberadamente distintos de los de Haltech
(`Régimen` vs. `RPM`, `Mariposa` vs. `Throttle Position`...): si el
emparejamiento dependiera del nombre, este fixture lo pondría de manifiesto.

## Generación

```bash
python tools/generar_dos_formatos.py [--seed {SEED_DEFAULT}] [--output samples/dos-formatos]
```

Determinista: el `random.Random(seed)` se consume en un orden fijo (fila por
fila, canal por canal) y ningún fichero contiene la hora de generación real,
así que dos ejecuciones son **idénticas byte a byte** (verificable con
`sha256sum samples/dos-formatos/*`). Los cuatro ficheros —`nativo.csv`,
`generico.csv`, `anotaciones.json` y este `README.md`— los escribe el mismo
script, a partir de un único vector de valores canónicos: los dos CSV se
**derivan** de ahí, no se generan por separado.

## Tabla de correspondencia canal ↔ rol ↔ columna

| Rol semántico | Canal nativo | Escala nativa (docs/01 §1.8) | Canal genérico | Unidad / precisión genérica |
|---|---|---|---|---|
{filas_crosswalk}

Columna 0 en ambos ficheros es la marca de tiempo (nativo: `HH:MM:SS.mmm`
absoluto con epoch ficticia 19800101, igual que `samples/real/*Log276{{8,9}}*`;
genérico: segundos relativos `0,000`, `0,050`, ...).

## Escalas aplicadas

**Lado nativo.** `canonica = crudo_entero / divisor`, con el divisor de la
tabla «Confirmados» de docs/01-formato-log.md §1.8 (no vive en
`data/formats/<formato>.toml` porque F0-09 es tarea de otro agente; aquí está
como constante documentada, y es exactamente la tabla del enunciado de F0-13).
El tipo `AFR` de Haltech contiene lambda, no relación aire-combustible
(docs/01 §1.8): por eso `lambda_measured` y `lambda_target` llevan
`Type: AFR` pero su rol y su dimensión son `mixture_ratio`/`lambda`.

**Lado genérico.** `mostrado = a · canonica + b`, con `(a, b)` leídos de
`data/units.toml` (F0-08, catálogo ya aprobado) para la unidad declarada de
cada columna — no están re-tecleados aquí. Salvo mariposa (`pct`) y
temperatura (`degC`), todas las columnas genéricas muestran la unidad
canónica directamente (`a=1, b=0`): rpm, kPa, λ, ° y V son ya sus propias
canónicas.

## Precisión de escritura del genérico y tolerancias

El enunciado pide elegir la precisión de escritura para que la ida y vuelta
sea exacta, no simplemente redondear a los decimales por omisión del
catálogo. Hay dos canales donde eso importa:

- **Presión** (`manifold_pressure`, `oil_pressure`): `data/units.toml` fija
  `decimales = 0` para `kPa`, pero eso es una preferencia de **presentación**
  del renderizador (redondear a kPa entero es cómodo de leer), no una cota de
  precisión de un fichero fuente. La canónica del nativo ya tiene 1 decimal
  (`crudo ÷ 10`), así que el genérico escribe kPa con **1 decimal**: con 0
  decimales se perdería información real y la ida y vuelta dejaría de ser
  exacta.
- **Temperatura** (`coolant_temp`, `intake_air_temp`): `data/units.toml` fija
  `decimales = 1` para `degC`, pero `°C = K − 273,15` necesita **2
  decimales** para ser exacto cuando K solo tiene 1 (p. ej. 366,3 K − 273,15 =
  93,15 °C, no 93,2 °C — el ejemplo exacto que pone el enunciado). El
  genérico escribe temperatura con 2 decimales.

El resto de columnas (`rpm`, `pct`, `lambda`, `deg`, `V`) coincide con el
`decimales` del catálogo porque la canónica nativa ya tiene, de fábrica,
justo esa cantidad de decimales significativos.

### Canales con ida y vuelta bit-exacta incluso en coma flotante

{exactos}.

Su conversión declarada es `mostrado = 1 · canonica + 0`: la cadena escrita
en el genérico es la representación decimal más corta del mismo valor exacto
que produce `crudo / divisor` en el nativo, y tanto el parseo de una cadena
decimal como una única división son operaciones **correctamente redondeadas**
en IEEE-754 — llegan al mismo `double` más cercano por construcción.
`tolerancia_canonica = 0.0` en `anotaciones.json` para estos 7 canales, y es
literal, no un margen de seguridad.

### Canales que SÍ necesitan un margen de punto flotante

{encadenados}.

Estos tres encadenan **dos** redondeos independientes del lado genérico
(parsear la cadena decimal, y luego sumar `273,15` o dividir entre `100`),
frente a la única división del lado nativo. En aritmética decimal exacta
(`decimal.Decimal`, que es lo que usa este generador para escribir las
cadenas) el resultado es matemáticamente idéntico — por eso el fixture en sí
**sí es exacto**, es una propiedad real del contenido, no un artefacto de la
prueba. Pero una comparación hecha en `float` de doble precisión (lo que hará
en la práctica cualquier importador basado en `polars`/`numpy`, ver docs/01
§1.12) puede acumular hasta **1 ULP** de diferencia entre los dos caminos —
del orden de 1e-13 en estas magnitudes. `anotaciones.json` declara
`tolerancia_canonica = 1e-9` para estos tres canales: dos órdenes de magnitud
de margen sobre el error esperado, para blindar la prueba sin esconder que
"exacto" y "bit-exacto en float" no son la misma afirmación.

**Esto es la información que la revisión humana necesita**: la igualdad
física es exacta en los 10 canales; la igualdad *en punto flotante* solo lo
es garantizadamente en 7 de los 10, y en los otros 3 hace falta una
tolerancia (pequeñísima, pero no nula) por cómo redondea IEEE-754, no por
ningún defecto del formato ni del emparejamiento por rol.

## Restricciones de formato verificadas

- `generico.csv` no contiene ni un solo `.` en ninguna celda numérica
  (delimitador `;`, decimal `,`).
- `nativo.csv` usa CRLF (docs/01 §1.13); `generico.csv` usa LF, a propósito,
  para no dar ninguna pista de que ambos vienen del mismo fabricante.
- Denso: 300 filas × 10 canales, sin celdas vacías — la dispersión
  multi-tasa de docs/01 §1.6 es una prueba distinta, no la de esta tarea.

## Verificación sin regenerar

`anotaciones.json` incluye el vector canónico completo de 3 canales
representativos (`engine_speed`, `manifold_pressure`, `lambda_measured` — uno
de cada familia de escala: entero directo, división simple, división de
mayor precisión) y el hash `sha256` de los 10 canales completos, con la
receta exacta para recalcularlo. `hash_sha256_todos_los_roles` de esta
generación: `{hash_hex}`.
"""
    ruta.write_text(contenido, encoding="utf-8")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera el fixture de dos formatos equivalentes (F0-13)"
    )
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT, help="Semilla RNG determinista")
    parser.add_argument("--output", type=Path, default=OUT_DIR_DEFAULT, help="Directorio de salida")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    catalogo = cargar_catalogo_unidades()
    rng = random.Random(args.seed)
    crudos = generar_crudos(rng)
    canonicas = canonicas_todas(crudos)
    hash_hex = calcular_hash(canonicas)

    escribir_nativo(args.output / "nativo.csv", crudos)
    escribir_generico(args.output / "generico.csv", catalogo, crudos)
    escribir_anotaciones(args.output / "anotaciones.json", canonicas, hash_hex)
    escribir_readme(args.output / "README.md", hash_hex)

    print(f"Generados 4 ficheros en {args.output} (seed={args.seed}, hash={hash_hex[:12]}...)")


if __name__ == "__main__":
    main()
