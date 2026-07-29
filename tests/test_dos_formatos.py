"""Prueba de independencia de fabricante del fixture de dos formatos (F0-13).

Es la prueba que demuestra la afirmación central de docs/07-formatos-y-csv-generico.md
§7.7/§7.11: que perfiles y detectores pueden emparejar por **rol semántico**
en vez de por nombre o `ID` de fabricante, porque el mismo contenido físico
en dos formatos distintos convierte al **mismo valor canónico**.

Deliberadamente independiente del generador (`tools/generar_dos_formatos.py`):
lee los CSV como texto plano y reimplementa las conversiones con sus propias
constantes (la escala de origen nativa, sacada de docs/01-formato-log.md §1.8;
las conversiones afines genéricas, leídas de `data/units.toml`). Si esta
prueba importara y reusara las funciones del generador, no probaría nada:
solo confirmaría que el generador está de acuerdo consigo mismo.

Solo biblioteca estándar: `csv` y `tomllib` (sin `polars`, sin `numpy`, y a
propósito sin `decimal`: la comparación se hace en `float` de doble
precisión, que es como lo hará en la práctica cualquier importador real
basado en `polars`/`numpy`). Ver el README.md del fixture para la discusión
de qué canales son bit-exactos en float y cuáles necesitan un margen de
punto flotante.
"""

from __future__ import annotations

import csv
import math
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIXTURE_DIR = RAIZ / "samples" / "dos-formatos"
UNITS_TOML = RAIZ / "data" / "units.toml"
HALTECH_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"

N_ROWS_ESPERADAS = 300

# --------------------------------------------------------------------------- #
# Escala de origen nativa (Haltech), reimplementada de forma independiente a
# partir de docs/01-formato-log.md §1.8. `divisor` es tal que
# canonica = crudo_entero / divisor. `columna` es 1-based, columna 0 del
# fichero es la marca de tiempo.
# --------------------------------------------------------------------------- #
# rol: (columna, divisor, nombre_esperado, id_esperado, type_esperado)
#
# El `divisor` NO se codifica aquí: se sustituye en tiempo de carga por el que
# declara `data/formats/haltech_nsp.toml` (F0-09), de modo que si alguien cambia
# una escala del descriptor y el fixture deja de cuadrar, esta prueba lo caza.
# Los valores literales de abajo son solo el marcador de posición.
_CANALES_NATIVOS_BASE = {
    "engine_speed": (1, 1, "RPM", 384, "EngineSpeed"),
    "manifold_pressure": (2, 10, "Manifold Pressure", 224, "Pressure"),
    "throttle_position": (3, 1000, "Throttle Position", 225, "Percentage"),
    "coolant_temp": (4, 10, "Coolant Temperature", 229, "Temperature"),
    "intake_air_temp": (5, 10, "Intake Air Temperature", 228, "Temperature"),
    "lambda_measured": (6, 1000, "Wideband O2 1", 230, "AFR"),
    "lambda_target": (7, 1000, "Target Lambda", 132, "AFR"),
    "ignition_advance": (8, 10, "Ignition Angle", 518, "Angle"),
    "oil_pressure": (9, 10, "Oil Pressure", 236, "Pressure"),
    "battery_voltage": (10, 1000, "Battery Voltage", 258, "BatteryVoltage"),
}


def _canales_nativos_desde_descriptor() -> dict[str, tuple[int, float, str, int, str]]:
    with HALTECH_TOML.open("rb") as fh:
        desc = tomllib.load(fh)
    salida: dict[str, tuple[int, float, str, int, str]] = {}
    for rol, (col, divisor_literal, nombre, canal_id, tipo) in _CANALES_NATIVOS_BASE.items():
        a = float(desc["tipos"][tipo]["a_canonica"])
        divisor = 1.0 / a
        # Si el descriptor y el marcador no coinciden, es un defecto en uno de
        # los dos y hay que verlo, no absorberlo.
        assert math.isclose(divisor, divisor_literal, rel_tol=1e-12), (
            f"{rol}: el descriptor dice a={a} (divisor {divisor}) y el fixture "
            f"asume divisor {divisor_literal}"
        )
        salida[rol] = (col, divisor, nombre, canal_id, tipo)
    return salida


CANALES_NATIVOS = _canales_nativos_desde_descriptor()

# Columna (1-based, 0 = Tiempo), dimensión y unidad declarada del lado
# genérico, reimplementadas de forma independiente a partir de la cabecera
# real de `generico.csv` (no del `anotaciones.json` del generador, aunque se
# cruzan más abajo como comprobación adicional).
CANALES_GENERICOS = {
    "engine_speed": (1, "angular_speed", "rpm"),
    "manifold_pressure": (2, "pressure", "kPa"),
    "throttle_position": (3, "ratio", "pct"),
    "coolant_temp": (4, "temperature", "degC"),
    "intake_air_temp": (5, "temperature", "degC"),
    "lambda_measured": (6, "mixture_ratio", "lambda"),
    "lambda_target": (7, "mixture_ratio", "lambda"),
    "ignition_advance": (8, "angle", "deg"),
    "oil_pressure": (9, "pressure", "kPa"),
    "battery_voltage": (10, "voltage", "V"),
}

# Canales cuya conversión genérica encadena dos operaciones (no es
# `a=1, b=0`): la tolerancia de comparación en float necesita un margen no
# nulo por acumulación de redondeo IEEE-754. Ver README.md del fixture.
TOLERANCIA_POR_ROL = dict.fromkeys(CANALES_NATIVOS, 0.0)
for _rol in ("throttle_position", "coolant_temp", "intake_air_temp"):
    TOLERANCIA_POR_ROL[_rol] = 1e-9


# --------------------------------------------------------------------------- #
# Lectura de ficheros
# --------------------------------------------------------------------------- #


def leer_nativo(ruta: Path) -> tuple[dict[str, dict], list[list[int]]]:
    """Devuelve (bloques_de_canal_en_orden, filas_de_valores_crudos).

    `bloques_de_canal_en_orden` es una lista de dicts {nombre, id, type,
    display_max_min} en el orden real de los bloques `Channel` del fichero
    -- ese orden es el que define las columnas (docs/01 §1.3), y esta
    función lo lee del propio fichero, no lo asume.
    """
    # `newline=""` es imprescindible: sin él, la traducción universal de
    # saltos de línea de Python convertiría CRLF a LF al leer y la
    # comprobación de abajo nunca fallaría aunque el fichero fuera LF.
    with ruta.open("r", encoding="ascii", newline="") as fh:
        texto = fh.read()
    assert "\r\n" in texto, "nativo.csv debe ser CRLF (docs/01-formato-log.md §1.13)"
    lineas = texto.split("\r\n")
    if lineas and lineas[-1] == "":
        lineas.pop()

    assert lineas[0] == "%DataLog%"
    assert lineas[1] == "DataLogVersion : 1.1"

    bloques = []
    i = 2
    while lineas[i].startswith("Software") or lineas[i].startswith("DownloadDateTime"):
        i += 1
    while lineas[i].startswith("Channel : "):
        nombre = lineas[i].split(":", 1)[1].strip()
        canal_id = int(lineas[i + 1].split(":", 1)[1].strip())
        tipo = lineas[i + 2].split(":", 1)[1].strip()
        dmm = lineas[i + 3].split(":", 1)[1].strip()
        bloques.append({"nombre": nombre, "id": canal_id, "type": tipo, "display_max_min": dmm})
        i += 4

    while not lineas[i].startswith("Log Number"):
        i += 1
    i += 1
    assert lineas[i].startswith("Log : ")
    i += 1

    filas: list[list[int]] = []
    for linea in lineas[i:]:
        celdas = linea.split(",")
        marca_tiempo, valores = celdas[0], celdas[1:]
        assert marca_tiempo, "fixture denso: no debe haber marcas de tiempo vacías"
        assert all(v != "" for v in valores), "fixture denso: no debe haber celdas vacías"
        filas.append([int(v) for v in valores])

    return {"bloques": bloques}, filas


def leer_generico(ruta: Path) -> tuple[list[str], list[str], list[list[str]]]:
    """Devuelve (nombres, unidades, filas_de_celdas_como_texto)."""
    with ruta.open("r", encoding="utf-8", newline="") as fh:
        lector = csv.reader(fh, delimiter=";")
        filas = list(lector)
    nombres, unidades, *datos = filas
    return nombres, unidades, datos


def coma_a_float(celda: str) -> float:
    assert "." not in celda, f"celda genérica con punto decimal, no coma: {celda!r}"
    return float(celda.replace(",", "."))


# --------------------------------------------------------------------------- #
# Conversión a canónica
# --------------------------------------------------------------------------- #


def canonica_desde_nativo(crudo: int, divisor: float) -> float:
    return crudo / divisor


def afines_genericos() -> dict[str, tuple[float, float]]:
    """(a, b) de `desde_canonica` para cada (dimension, unidad) usada, leídas
    del catálogo aprobado `data/units.toml` (F0-08): mostrado = a*canonica + b.
    """
    with UNITS_TOML.open("rb") as fh:
        catalogo = tomllib.load(fh)
    resultado = {}
    for rol, (_col, dimension, unidad) in CANALES_GENERICOS.items():
        conv = catalogo["dimensiones"][dimension]["unidades"][unidad]["desde_canonica"]
        assert conv["tipo"] == "afin"
        resultado[rol] = (conv["a"], conv["b"])
    return resultado


def canonica_desde_generico(mostrado: float, a: float, b: float) -> float:
    return (mostrado - b) / a


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_ficheros_existen() -> None:
    for nombre in ("nativo.csv", "generico.csv", "anotaciones.json", "README.md"):
        assert (FIXTURE_DIR / nombre).exists(), f"falta {nombre}"


def test_nativo_cabecera_coincide_con_catalogo() -> None:
    cabecera, filas = leer_nativo(FIXTURE_DIR / "nativo.csv")
    assert len(filas) == N_ROWS_ESPERADAS
    for rol, (columna, _divisor, nombre, canal_id, tipo) in CANALES_NATIVOS.items():
        bloque = cabecera["bloques"][columna - 1]
        assert bloque["nombre"] == nombre, rol
        assert bloque["id"] == canal_id, rol
        assert bloque["type"] == tipo, rol
    for fila in filas:
        assert len(fila) == len(CANALES_NATIVOS)


def test_generico_sin_puntos_en_celdas_numericas() -> None:
    texto = (FIXTURE_DIR / "generico.csv").read_text(encoding="utf-8")
    nombres, unidades, filas = leer_generico(FIXTURE_DIR / "generico.csv")
    assert len(filas) == N_ROWS_ESPERADAS
    for fila in filas:
        for celda in fila:
            assert "." not in celda, f"celda con punto: {celda!r}"
    # Las únicas apariciones de '.' en todo el fichero son abreviaturas de la
    # fila de nombres ("Temp."), nunca en una celda numérica.
    lineas = texto.split("\n")
    for linea in lineas[2:]:
        assert "." not in linea


def test_generico_delimitador_y_decimal() -> None:
    nombres, unidades, filas = leer_generico(FIXTURE_DIR / "generico.csv")
    assert nombres[0] == "Tiempo"
    assert unidades[0] == "s"
    # Etiqueta de unidad esperada en la fila de unidades para cada clave de
    # `data/units.toml` usada aquí (leída de la propia fila, no adivinada).
    etiquetas_esperadas = {
        "rpm": "rpm",
        "kPa": "kPa",
        "pct": "%",
        "degC": "°C",
        "lambda": "λ",
        "deg": "°",
        "V": "V",
    }
    for rol, (columna, _dim, unidad) in CANALES_GENERICOS.items():
        assert unidades[columna] == etiquetas_esperadas[unidad], rol
    # Nombres distintos a los nativos: el emparejamiento debe ser por rol.
    nombres_nativos = {n for (_c, _d, n, _i, _t) in CANALES_NATIVOS.values()}
    for nombre_generico in nombres[1:]:
        assert nombre_generico not in nombres_nativos


def test_mismo_numero_de_filas() -> None:
    _cabecera, filas_nativo = leer_nativo(FIXTURE_DIR / "nativo.csv")
    _n, _u, filas_generico = leer_generico(FIXTURE_DIR / "generico.csv")
    assert len(filas_nativo) == len(filas_generico) == N_ROWS_ESPERADAS


def test_canonicas_coinciden_canal_por_canal_fila_por_fila() -> None:
    """El corazón de F0-13: nativo y genérico deben dar la misma canónica."""
    _cabecera, filas_nativo = leer_nativo(FIXTURE_DIR / "nativo.csv")
    _n, _u, filas_generico = leer_generico(FIXTURE_DIR / "generico.csv")
    afines = afines_genericos()

    max_error_por_rol: dict[str, float] = {}

    for rol, (col_nat, divisor, *_resto) in CANALES_NATIVOS.items():
        col_gen, _dim, _unidad = CANALES_GENERICOS[rol]
        a, b = afines[rol]
        tolerancia = TOLERANCIA_POR_ROL[rol]

        for fila_idx in range(N_ROWS_ESPERADAS):
            crudo = filas_nativo[fila_idx][col_nat - 1]
            celda_generica = filas_generico[fila_idx][col_gen]

            canonica_nat = canonica_desde_nativo(crudo, divisor)
            canonica_gen = canonica_desde_generico(coma_a_float(celda_generica), a, b)

            error = abs(canonica_nat - canonica_gen)
            max_error_por_rol[rol] = max(max_error_por_rol.get(rol, 0.0), error)

            assert math.isclose(canonica_nat, canonica_gen, rel_tol=0.0, abs_tol=tolerancia), (
                f"{rol} fila {fila_idx}: nativo={canonica_nat!r} genérico={canonica_gen!r} "
                f"error={error!r} > tolerancia={tolerancia!r}"
            )

    # Los 7 canales de conversión directa (a=1, b=0) deben ser bit-exactos:
    # cero diferencia real, no solo "dentro de tolerancia".
    for rol in CANALES_NATIVOS:
        if TOLERANCIA_POR_ROL[rol] == 0.0:
            assert max_error_por_rol[rol] == 0.0, (
                f"{rol} se declaró bit-exacto pero el error observado fue "
                f"{max_error_por_rol[rol]!r}"
            )


def test_tiempo_relativo_generico_coincide_con_muestreo_nativo() -> None:
    _n, _u, filas_generico = leer_generico(FIXTURE_DIR / "generico.csv")
    for i, fila in enumerate(filas_generico):
        t_esperado = round(i * 0.05, 3)
        t_leido = coma_a_float(fila[0])
        assert math.isclose(t_leido, t_esperado, rel_tol=0.0, abs_tol=1e-9)


def test_perfil_fisico_ralenti_a_plena_carga() -> None:
    """Sanity check de la física sintética: ralentí al inicio, plena carga al final."""
    cabecera, filas_nativo = leer_nativo(FIXTURE_DIR / "nativo.csv")
    rpm_inicial = filas_nativo[0][CANALES_NATIVOS["engine_speed"][0] - 1]
    rpm_final = filas_nativo[-1][CANALES_NATIVOS["engine_speed"][0] - 1]
    tps_inicial = filas_nativo[0][CANALES_NATIVOS["throttle_position"][0] - 1]
    tps_final = filas_nativo[-1][CANALES_NATIVOS["throttle_position"][0] - 1]

    assert 700 <= rpm_inicial <= 1100, rpm_inicial
    assert rpm_final > 5000, rpm_final
    assert tps_inicial == 0
    assert tps_final == 1000


def test_anotaciones_json_consistente_con_los_csv() -> None:
    import json

    anotaciones = json.loads((FIXTURE_DIR / "anotaciones.json").read_text(encoding="utf-8"))
    assert anotaciones["n_filas"] == N_ROWS_ESPERADAS
    assert set(anotaciones["roles"]) == set(CANALES_NATIVOS)

    _cabecera, filas_nativo = leer_nativo(FIXTURE_DIR / "nativo.csv")
    vectores = anotaciones["canonicas_esperadas"]["vectores_ejemplo"]
    for rol, vector in vectores.items():
        columna, divisor, *_resto = CANALES_NATIVOS[rol]
        assert len(vector) == N_ROWS_ESPERADAS
        for i, esperado in enumerate(vector):
            real = canonica_desde_nativo(filas_nativo[i][columna - 1], divisor)
            assert math.isclose(real, esperado, rel_tol=0.0, abs_tol=1e-9), (rol, i)

    for entrada in anotaciones["canales"]:
        rol = entrada["rol"]
        assert entrada["tolerancia_canonica"] == TOLERANCIA_POR_ROL[rol]
