#!/usr/bin/env python3
"""Generador del corpus sintético de logs (tarea F0-05).

Produce, a partir de los tres logs reales de `samples/real/`, dos artefactos:

1. `samples/synth/autolog-1h.csv` — el AutoLog real extendido a ~1 hora,
   conservando su cabecera de 475 canales y su perfil temporal de tasa
   variable (docs/01-formato-log.md §1.7).
2. `samples/synth/internal-x20/` — 20 logs internos consecutivos al estilo
   `Log2768/2769`, con epoch ficticia y muestreo disperso multi-tasa
   (docs/01-formato-log.md §1.5, §1.6).

Solo biblioteca estándar: no depende de `numpy` ni `polars`, a propósito,
para que se pueda ejecutar sin instalar nada (es lo que desbloquea el resto
de F0 antes de que exista un entorno con dependencias).

Determinismo: toda la aleatoriedad pasa por un único `random.Random(seed)`
consumido en un orden fijo; dos ejecuciones con la misma semilla producen
ficheros idénticos byte a byte (se comprueba en `tests/test_generar_corpus.py`).

Uso:
    python tools/generar_corpus.py autolog-1h
    python tools/generar_corpus.py internos
    python tools/generar_corpus.py verificar samples/synth/autolog-1h.csv
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constantes y rutas
# --------------------------------------------------------------------------- #

RAIZ = Path(__file__).resolve().parent.parent
REAL_AUTOLOG = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"
REAL_LOG2768 = RAIZ / "samples" / "real" / "20260729_1859_Log2768.csv"
REAL_LOG2769 = RAIZ / "samples" / "real" / "20260729_1859_Log2769.csv"
SYNTH_DIR = RAIZ / "samples" / "synth"

# Centinelas de desbordamiento/saturación observados en el AutoLog real
# (docs/01-formato-log.md §1.13, último punto). No son medidas: son "sin dato".
SENTINELS = (2147483647, -2147483645, -2147483628, 8388607)

# Tamaño por defecto de la semilla: fijo para que el corpus sea reproducible
# sin que nadie tenga que acordarse de pasar --seed.
DEFAULT_SEED = 20260729

CRLF = "\r\n"

# Tasas nominales de los 3 grupos de muestreo disperso multi-tasa de los logs
# internos (docs/01-formato-log.md §1.6), como rango de dt en ms medido sobre
# los dos logs reales (20260729_1859_Log2768/2769.csv): G0 ~18.9 Hz (dt 50-56
# ms), G1 ~9.8 Hz (dt 100-105 ms), G2 ~5.0 Hz (dt 200-205 ms).
GROUP_DT_RANGES = ((50, 56), (100, 105), (200, 205))
GROUP_SIZES = (13, 8, 4)  # nº de canales de cada grupo, en el orden de cabecera


# --------------------------------------------------------------------------- #
# Utilidades de fichero / cabecera, compartidas por los dos flavors del
# formato (docs/01-formato-log.md §1.2).
# --------------------------------------------------------------------------- #


def leer_texto(ruta: Path) -> str:
    with open(ruta, newline="") as f:
        return f.read()


def separar_lineas(texto: str) -> list[str]:
    """Normaliza CRLF/LF y descarta la línea vacía final de un `\\n` de cierre."""
    lineas = texto.replace("\r\n", "\n").split("\n")
    if lineas and lineas[-1] == "":
        lineas.pop()
    return lineas


def parsear_cabecera(lineas: list[str]):
    """Parsea la cabecera `%DataLog%` genérica (§1.3).

    Devuelve (meta_global, canales, log_source, log_number, log_valor, idx_datos)
    donde `idx_datos` es el índice de la primera línea de datos.
    """
    if not lineas or lineas[0] != "%DataLog%":
        raise ValueError("firma %DataLog% ausente o inválida")
    meta_global: dict[str, str] = {}
    i = 1
    while i < len(lineas) and not lineas[i].startswith("Channel :"):
        clave, valor = lineas[i].split(" : ", 1)
        meta_global[clave] = valor
        i += 1
    canales: list[dict] = []
    while i < len(lineas) and lineas[i].startswith("Channel :"):
        nombre = lineas[i].split(" : ", 1)[1]
        i += 1
        cid = lineas[i].split(" : ", 1)[1]
        i += 1
        tipo = lineas[i].split(" : ", 1)[1]
        i += 1
        dispmaxmin = None
        if i < len(lineas) and lineas[i].startswith("DisplayMaxMin"):
            dispmaxmin = lineas[i].split(" : ", 1)[1]
            i += 1
        canales.append({"name": nombre, "id": cid, "type": tipo, "dispmaxmin": dispmaxmin})
    log_source = lineas[i].split(" : ", 1)[1]
    i += 1
    log_number = lineas[i].split(" : ", 1)[1]
    i += 1
    log_valor = lineas[i].split(" : ", 1)[1]
    i += 1
    return meta_global, canales, log_source, log_number, log_valor, i


def construir_cabecera(
    meta_global: dict, canales: list[dict], log_source: str, log_number: str, log_valor: str
) -> list[str]:
    lineas = [
        "%DataLog%",
        f"DataLogVersion : {meta_global['DataLogVersion']}",
        f"Software : {meta_global['Software']}",
        f"SoftwareVersion : {meta_global['SoftwareVersion']}",
        f"DownloadDateTime : {meta_global['DownloadDateTime']}",
    ]
    for ch in canales:
        lineas.append(f"Channel : {ch['name']}")
        lineas.append(f"ID : {ch['id']}")
        lineas.append(f"Type : {ch['type']}")
        if ch["dispmaxmin"] is not None:
            lineas.append(f"DisplayMaxMin : {ch['dispmaxmin']}")
    lineas.append(f"Log Source : {log_source}")
    lineas.append(f"Log Number : {log_number}")
    lineas.append(f"Log : {log_valor}")
    return lineas


def parsear_reloj_ms(marca: str) -> int:
    """`HH:MM:SS.mmm` -> milisegundos desde medianoche."""
    h, m, resto = marca.split(":")
    seg, ms = resto.split(".")
    return ((int(h) * 3600 + int(m) * 60 + int(seg)) * 1000) + int(ms)


def formatear_reloj_ms(total_ms: int) -> str:
    """Milisegundos desde medianoche -> `HH:MM:SS.mmm`, con vuelta de medianoche."""
    total_ms %= 86_400_000
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = (total_m // 60) % 24
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def formatear_reloj_cabecera(fecha: str, ms_de_dia: int) -> str:
    """Formatea un instante como hora de cabecera en 12 h sin AM/PM (§1.4).

    Trunca a segundos (la cabecera no lleva milisegundos) y reduce la hora
    módulo 12, reproduciendo deliberadamente la ambigüedad del formato real.
    """
    ms_de_dia %= 86_400_000
    total_s = ms_de_dia // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = (total_m // 60) % 24
    h12 = h % 12
    return f"{fecha} {h12:02d}:{m:02d}:{s:02d}"


# --------------------------------------------------------------------------- #
# Modelo de canal: clasifica cada columna real como constante / con
# centinelas / con paseo aleatorio acotado, y genera el siguiente valor.
# --------------------------------------------------------------------------- #


class ModeloCanal:
    """Extiende los valores observados de un canal más allá de los datos reales.

    - Canal constante (§1.11, p. ej. `Oil Temperature`): sigue constante.
    - Canal con centinelas de desbordamiento (§1.13): reproduce la misma
      frecuencia de aparición del centinela que en los datos reales.
    - Canal normal: paseo aleatorio con pasos remuestreados de las diferencias
      reales observadas, acotado (con reflexión en el límite) al rango
      `DisplayMaxMin` cuando existe, o al rango observado en su defecto.
    """

    __slots__ = (
        "centinelas",
        "constante",
        "diffs",
        "estado",
        "frecuencia_centinela",
        "max_",
        "min_",
        "valor_constante",
    )

    def __init__(self, dispmaxmin: str | None, valores: list[int]):
        valores = list(valores)
        distintos = set(valores)
        self.constante = len(distintos) <= 1
        self.valor_constante = valores[-1] if valores else 0

        centinelas_presentes = sorted(distintos & set(SENTINELS))
        self.centinelas = centinelas_presentes
        if centinelas_presentes and valores:
            self.frecuencia_centinela = sum(1 for v in valores if v in SENTINELS) / len(valores)
        else:
            self.frecuencia_centinela = 0.0

        no_centinela = [v for v in valores if v not in SENTINELS]

        # El rango "blando" del paseo es el rango realmente observado en el
        # log real (con un margen de holgura), no el `DisplayMaxMin` teórico.
        # Muchos canales (derivadas, errores, salidas de control) declaran un
        # `DisplayMaxMin` simétrico enorme que casi nunca se alcanza en la
        # práctica: acotar el paseo a ese rango completo lo convierte en un
        # paseo aleatorio ~uniforme sobre todo el intervalo en unos pocos
        # miles de pasos, perdiendo el carácter "casi siempre cerca de cero"
        # del canal real y engordando el CSV (más dígitos por celda).
        # `DisplayMaxMin`, cuando existe, actúa solo como límite duro de
        # seguridad que nunca se cruza.
        if no_centinela:
            obs_min, obs_max = min(no_centinela), max(no_centinela)
        else:
            obs_min, obs_max = 0, 0
        span = obs_max - obs_min
        margen = max(1, round(span * 0.15)) if span > 0 else max(1, abs(obs_min) // 10)
        blando_min, blando_max = obs_min - margen, obs_max + margen

        if dispmaxmin:
            mx_s, mn_s = dispmaxmin.split(",")
            duro_max, duro_min = int(mx_s), int(mn_s)
            if duro_min > duro_max:
                duro_min, duro_max = duro_max, duro_min
            mn, mx = max(blando_min, duro_min), min(blando_max, duro_max)
            if mn > mx:  # el margen blando cayó fuera del rango declarado
                mn, mx = duro_min, duro_max
        else:
            mn, mx = blando_min, blando_max
        if mn > mx:
            mn, mx = mx, mn
        self.min_, self.max_ = mn, mx

        diffs = []
        anterior = None
        for v in valores:
            if v in SENTINELS:
                anterior = None
                continue
            if anterior is not None:
                diffs.append(v - anterior)
            anterior = v
        self.diffs = diffs or [0]

        self.estado = no_centinela[-1] if no_centinela else (valores[-1] if valores else mn)

    def siguiente(self, rng: random.Random) -> int:
        if self.constante:
            return self.valor_constante
        if self.centinelas and rng.random() < self.frecuencia_centinela:
            return rng.choice(self.centinelas)
        paso = rng.choice(self.diffs)
        v = self.estado + paso
        lo, hi = self.min_, self.max_
        if hi > lo:
            # Reflexión en los límites en vez de recorte seco: evita que el
            # paseo se quede "pegado" al borde cuando el paso es grande.
            while v > hi or v < lo:
                if v > hi:
                    v = hi - (v - hi)
                elif v < lo:
                    v = lo + (lo - v)
        else:
            v = lo
        self.estado = v
        return v


# --------------------------------------------------------------------------- #
# autolog-1h
# --------------------------------------------------------------------------- #


def _cargar_autolog_real():
    lineas = separar_lineas(leer_texto(REAL_AUTOLOG))
    meta_global, canales, log_source, log_number, log_valor, idx_datos = parsear_cabecera(lineas)
    lineas_datos = lineas[idx_datos:]
    filas_crudas = [dl.split(",") for dl in lineas_datos]
    tiempos_ms = [parsear_reloj_ms(f[0]) for f in filas_crudas]
    valores = [[int(x) for x in f[1:]] for f in filas_crudas]
    return meta_global, canales, log_source, log_number, log_valor, tiempos_ms, valores


def generar_autolog_1h(seed: int, filas_objetivo: int | None, minutos: float, salida: Path) -> Path:
    rng = random.Random(seed)
    meta_global, canales, log_source, log_number, log_valor, tiempos_ms, valores = (
        _cargar_autolog_real()
    )

    n_canales = len(canales)
    n_filas_reales = len(valores)
    duracion_real_ms = tiempos_ms[-1] - tiempos_ms[0]
    dts_reales = [tiempos_ms[i + 1] - tiempos_ms[i] for i in range(n_filas_reales - 1)]

    if filas_objetivo is None:
        filas_objetivo = max(
            2,
            round((n_filas_reales - 1) * (minutos * 60_000) / duracion_real_ms) + 1,
        )

    # Marcas de tiempo: se reutiliza el dt real cíclicamente (§1.7: bimodal,
    # p50 54 ms / p90 163 ms / p99 221 ms / min 35 ms / max 499 ms). Repetir el
    # mismo vector de dt observado reproduce exactamente esas percentiles,
    # sin asumir muestreo uniforme en ningún momento.
    tiempos = [0] * filas_objetivo
    tiempos[0] = tiempos_ms[0]
    n_dts = len(dts_reales)
    for i in range(1, filas_objetivo):
        tiempos[i] = tiempos[i - 1] + dts_reales[(i - 1) % n_dts]

    # Modelo por canal (constante / centinela / paseo acotado), a partir de
    # las columnas reales.
    columnas = list(zip(*valores, strict=True))
    modelos = [ModeloCanal(canales[c]["dispmaxmin"], columnas[c]) for c in range(n_canales)]

    filas_salida: list[str] = []
    for i in range(filas_objetivo):
        fila_valores = valores[i] if i < n_filas_reales else [m.siguiente(rng) for m in modelos]
        marca = formatear_reloj_ms(tiempos[i])
        filas_salida.append(marca + "," + ",".join(map(str, fila_valores)))

    # Cabecera: se reutiliza tal cual, ajustando solo `Log` y
    # `DownloadDateTime` para reflejar la nueva duración (§1.4). La fecha se
    # mantiene: no depende del reloj de la máquina, para que el fichero sea
    # reproducible con la misma semilla en cualquier día.
    fecha = log_valor.split(" ")[0]

    dl_hora = meta_global["DownloadDateTime"].split(" ")[1]
    dl_h, dl_m, dl_s = (int(x) for x in dl_hora.split(":"))
    # La cabecera real está desfasada +12 h respecto al reloj verdadero de
    # las filas (§1.4); se asume el mismo desfase para DownloadDateTime y se
    # conserva el margen entre el fin del log real y su descarga.
    descarga_real_ms = ((dl_h + 12) % 24 * 3600 + dl_m * 60 + dl_s) * 1000
    margen_descarga_ms = descarga_real_ms - tiempos_ms[-1]

    log_nuevo = formatear_reloj_cabecera(fecha, tiempos[0])
    descarga_nueva = formatear_reloj_cabecera(fecha, tiempos[-1] + margen_descarga_ms)

    meta_global_nuevo = dict(meta_global)
    meta_global_nuevo["DownloadDateTime"] = descarga_nueva

    cabecera = construir_cabecera(meta_global_nuevo, canales, log_source, log_number, log_nuevo)

    salida.parent.mkdir(parents=True, exist_ok=True)
    with open(salida, "w", newline="") as f:
        f.write(CRLF.join(cabecera))
        f.write(CRLF)
        f.write(CRLF.join(filas_salida))
        f.write(CRLF)

    return salida


# --------------------------------------------------------------------------- #
# internos (internal-x20)
# --------------------------------------------------------------------------- #


def _cargar_internos_real(ruta: Path):
    lineas = separar_lineas(leer_texto(ruta))
    meta_global, canales, log_source, log_number, log_valor, idx_datos = parsear_cabecera(lineas)
    lineas_datos = lineas[idx_datos:]
    filas = []
    for dl in lineas_datos:
        partes = dl.split(",")
        t = parsear_reloj_ms(partes[0])
        filas.append((t, partes[1:]))
    return meta_global, canales, log_source, filas


def _generar_tiempos_grupo(
    dt_lo: int, dt_hi: int, duracion_ms: int, rng: random.Random
) -> list[int]:
    tiempos = [0]
    t = 0
    while True:
        t += rng.randint(dt_lo, dt_hi)
        if t > duracion_ms:
            break
        tiempos.append(t)
    return tiempos


def generar_internos(
    seed: int,
    n_logs: int,
    primer_log_number: int,
    duracion_min_ms: int,
    duracion_max_ms: int,
    salida_dir: Path,
) -> list[Path]:
    rng = random.Random(seed)

    meta1, canales, log_source_real, filas1 = _cargar_internos_real(REAL_LOG2768)
    _, _, _, filas2 = _cargar_internos_real(REAL_LOG2769)

    n_canales = len(canales)
    assert sum(GROUP_SIZES) == n_canales, "el reparto de grupos no cuadra con el nº de canales"

    grupo_de_canal = []
    for gi, tam in enumerate(GROUP_SIZES):
        grupo_de_canal += [gi] * tam

    # Modelo por canal a partir de las muestras no vacías combinadas de los
    # dos logs reales (más muestras -> mejor caracterización del paseo).
    muestras_por_canal: list[list[int]] = [[] for _ in range(n_canales)]
    for filas in (filas1, filas2):
        for _t, vals in filas:
            for c in range(n_canales):
                v = vals[c] if c < len(vals) else ""
                if v != "":
                    muestras_por_canal[c].append(int(v))
    modelos = [
        ModeloCanal(canales[c]["dispmaxmin"], muestras_por_canal[c]) for c in range(n_canales)
    ]

    fecha = (
        "20260729"  # misma fecha que el corpus real; determinista, no usa el reloj de la máquina
    )
    ancla_descarga_ms = parsear_reloj_ms(
        "18:59:00.000"
    )  # ancla arbitraria pero fija (mismo estilo que el real "1859")
    ancla_h = ancla_descarga_ms // 3_600_000
    ancla_m = (ancla_descarga_ms // 60_000) % 60
    etiqueta_lote = f"{ancla_h:02d}{ancla_m:02d}"

    # Desplazamientos de descarga deliberadamente no monótonos respecto al
    # Log Number (§1.5: en los reales, 2768 se descarga *después* que 2769).
    desplazamientos = []
    acumulado = 0
    for _ in range(n_logs):
        acumulado += rng.randint(5, 40) * 1000
        jitter = rng.randint(-25, 25) * 1000
        desplazamientos.append(acumulado + jitter)
    if n_logs > 1 and desplazamientos == sorted(desplazamientos):
        desplazamientos[0], desplazamientos[1] = desplazamientos[1], desplazamientos[0]

    base_epoch_ms = parsear_reloj_ms("01:01:01.005")  # epoch ficticia (§1.5)

    ficheros: list[Path] = []
    salida_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(n_logs):
        log_number = primer_log_number + idx
        duracion_ms = rng.randint(duracion_min_ms, duracion_max_ms)

        tiempos_por_grupo = [
            _generar_tiempos_grupo(lo, hi, duracion_ms, rng) for (lo, hi) in GROUP_DT_RANGES
        ]
        fusion: dict[int, set[int]] = {}
        for g, tiempos in enumerate(tiempos_por_grupo):
            for t in tiempos:
                fusion.setdefault(t, set()).add(g)

        filas_salida: list[str] = []
        for t in sorted(fusion):
            grupos_presentes = fusion[t]
            celdas = []
            for c in range(n_canales):
                if grupo_de_canal[c] in grupos_presentes:
                    celdas.append(str(modelos[c].siguiente(rng)))
                else:
                    celdas.append("")
            marca = formatear_reloj_ms(base_epoch_ms + t)
            filas_salida.append(marca + "," + ",".join(celdas))

        descarga_nueva = formatear_reloj_cabecera(
            fecha, (ancla_descarga_ms + desplazamientos[idx]) % 86_400_000
        )
        meta_global_nuevo = dict(meta1)
        meta_global_nuevo["DownloadDateTime"] = descarga_nueva

        cabecera = construir_cabecera(
            meta_global_nuevo, canales, log_source_real, str(log_number), "19800101 01:01:01"
        )

        nombre = f"{fecha}_{etiqueta_lote}_Log{log_number}.csv"
        ruta = salida_dir / nombre
        with open(ruta, "w", newline="") as f:
            f.write(CRLF.join(cabecera))
            f.write(CRLF)
            if filas_salida:
                f.write(CRLF.join(filas_salida))
                f.write(CRLF)
        ficheros.append(ruta)

    return ficheros


# --------------------------------------------------------------------------- #
# verificar
# --------------------------------------------------------------------------- #


def verificar_fichero(ruta: Path) -> dict:
    lineas = separar_lineas(leer_texto(ruta))
    meta_global, canales, log_source, log_number, log_valor, idx_datos = parsear_cabecera(lineas)
    lineas_datos = lineas[idx_datos:]

    n_filas = len(lineas_datos)
    n_canales = len(canales)

    tiempos_ms = []
    total_celdas = 0
    celdas_vacias = 0
    for dl in lineas_datos:
        partes = dl.split(",")
        tiempos_ms.append(parsear_reloj_ms(partes[0]))
        vals = partes[1:]
        total_celdas += len(vals)
        celdas_vacias += sum(1 for v in vals if v == "")

    dts = [tiempos_ms[i + 1] - tiempos_ms[i] for i in range(len(tiempos_ms) - 1)]
    # tolera cruce de medianoche por si se verifica un corte deliberado (§1.13)
    dts = [d + 86_400_000 if d < 0 else d for d in dts]
    dts_ordenados = sorted(dts)

    def percentil(p: float):
        if not dts_ordenados:
            return None
        idx = min(int(p * len(dts_ordenados)), len(dts_ordenados) - 1)
        return dts_ordenados[idx]

    duracion_s = (sum(dts) / 1000) if dts else 0.0
    dt_medio = (sum(dts) / len(dts)) if dts else 0.0
    tasa_media = (1000 / dt_medio) if dt_medio else 0.0
    pct_vacias = (100 * celdas_vacias / total_celdas) if total_celdas else 0.0

    return {
        "fichero": str(ruta),
        "canales": n_canales,
        "filas": n_filas,
        "duracion_s": duracion_s,
        "tamano_bytes": os.path.getsize(ruta),
        "dt_p50": percentil(0.5),
        "dt_p90": percentil(0.9),
        "dt_p99": percentil(0.99),
        "dt_min": min(dts) if dts else None,
        "dt_max": max(dts) if dts else None,
        "tasa_media_hz": tasa_media,
        "pct_celdas_vacias": pct_vacias,
    }


def imprimir_verificacion(info: dict) -> None:
    print(f"Fichero: {info['fichero']}")
    print(f"Canales: {info['canales']}")
    print(f"Filas: {info['filas']}")
    print(f"Duración: {info['duracion_s']:.3f} s")
    print(f"Tamaño: {info['tamano_bytes']} bytes ({info['tamano_bytes'] / 1_000_000:.2f} MB)")
    print(f"dt p50: {info['dt_p50']} ms")
    print(f"dt p90: {info['dt_p90']} ms")
    print(f"dt p99: {info['dt_p99']} ms")
    print(f"dt min: {info['dt_min']} ms")
    print(f"dt max: {info['dt_max']} ms")
    print(f"Tasa media efectiva: {info['tasa_media_hz']:.2f} Hz")
    print(f"Celdas vacías: {info['pct_celdas_vacias']:.2f} %")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generar_corpus.py",
        description="Genera el corpus sintético de logs de DataLogViewer (F0-05).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Semilla del generador (por omisión {DEFAULT_SEED}; "
        "misma semilla -> ficheros idénticos byte a byte).",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_auto = sub.add_parser("autolog-1h", help="Genera samples/synth/autolog-1h.csv")
    p_auto.add_argument(
        "--minutos",
        type=float,
        default=60.0,
        help="Duración objetivo en minutos (por omisión 60). Ignorado si se pasa --filas.",
    )
    p_auto.add_argument(
        "--filas", type=int, default=None, help="Nº de filas de datos exacto (invalida --minutos)."
    )
    p_auto.add_argument("--salida", type=Path, default=SYNTH_DIR / "autolog-1h.csv")

    p_int = sub.add_parser("internos", help="Genera samples/synth/internal-x20/")
    p_int.add_argument(
        "--logs", type=int, default=20, help="Nº de logs a generar (por omisión 20)."
    )
    p_int.add_argument("--primer-log-number", type=int, default=2800)
    p_int.add_argument("--duracion-min-s", type=float, default=7.0)
    p_int.add_argument("--duracion-max-s", type=float, default=15.0)
    p_int.add_argument("--salida-dir", type=Path, default=SYNTH_DIR / "internal-x20")

    p_ver = sub.add_parser("verificar", help="Reporta estadísticas de un fichero generado.")
    p_ver.add_argument("fichero", type=Path)

    args = parser.parse_args(argv)

    if args.comando == "autolog-1h":
        ruta = generar_autolog_1h(args.seed, args.filas, args.minutos, args.salida)
        print(f"Generado: {ruta}")
        return 0

    if args.comando == "internos":
        ficheros = generar_internos(
            args.seed,
            args.logs,
            args.primer_log_number,
            int(args.duracion_min_s * 1000),
            int(args.duracion_max_s * 1000),
            args.salida_dir,
        )
        for f in ficheros:
            print(f"Generado: {f}")
        return 0

    if args.comando == "verificar":
        info = verificar_fichero(args.fichero)
        imprimir_verificacion(info)
        return 0

    parser.error("comando desconocido")
    return 2


if __name__ == "__main__":
    sys.exit(main())
