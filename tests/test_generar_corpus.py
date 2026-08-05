"""Pruebas del generador de corpus sintético (tarea F0-05).

Deliberadamente rápidas: generan una versión pequeña (--minutos 1 / --logs 2)
en un directorio temporal fuera del repo, nunca el fichero de 66 MB. Solo
biblioteca estándar, igual que el generador.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "tools" / "generar_corpus.py"


def _cargar_modulo():
    spec = importlib.util.spec_from_file_location("generar_corpus", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


gc = _cargar_modulo()


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _parsear_para_test(ruta: Path):
    """Reimplementación mínima e independiente del parseo de cabecera/filas.

    Deliberadamente no reutiliza `gc.parsear_cabecera` para no probar el
    generador contra sí mismo.
    """
    with open(ruta, newline="") as f:
        texto = f.read()
    lineas = texto.replace("\r\n", "\n").split("\n")
    if lineas and lineas[-1] == "":
        lineas.pop()
    assert lineas[0] == "%DataLog%"
    n_canales = sum(1 for ln in lineas if ln.startswith("Channel :"))
    idx_log = next(i for i, ln in enumerate(lineas) if ln.startswith("Log :"))
    filas = lineas[idx_log + 1 :]
    return n_canales, filas


def _tiempos_ms(filas: list[str]) -> list[int]:
    def parse(marca: str) -> int:
        h, m, resto = marca.split(":")
        s, ms = resto.split(".")
        return ((int(h) * 3600 + int(m) * 60 + int(s)) * 1000) + int(ms)

    return [parse(f.split(",", 1)[0]) for f in filas]


# --------------------------------------------------------------------------- #
# autolog-1h
# --------------------------------------------------------------------------- #


def test_autolog_cabecera_y_columnas():
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "autolog-mini.csv"
        gc.generar_autolog_1h(seed=1, filas_objetivo=None, minutos=1.0, salida=salida)

        n_canales, filas = _parsear_para_test(salida)
        assert n_canales == 475
        assert len(filas) > 100  # ~1 minuto de datos, bastantes filas

        for fila in filas[:5] + filas[-5:]:
            n_valores = len(fila.split(",")) - 1  # -1 por la marca de tiempo
            assert n_valores == n_canales


def test_autolog_marcas_monotonas():
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "autolog-mini.csv"
        gc.generar_autolog_1h(seed=2, filas_objetivo=None, minutos=1.0, salida=salida)

        _, filas = _parsear_para_test(salida)
        tiempos = _tiempos_ms(filas)
        assert all(tiempos[i + 1] > tiempos[i] for i in range(len(tiempos) - 1))


def test_autolog_determinismo_misma_semilla():
    # filas_objetivo > nº de filas reales (2636): fuerza a que parte del
    # fichero pase por el paseo aleatorio, no solo por la copia directa.
    with tempfile.TemporaryDirectory() as tmp:
        salida1 = Path(tmp) / "a.csv"
        salida2 = Path(tmp) / "b.csv"
        gc.generar_autolog_1h(seed=42, filas_objetivo=2660, minutos=60.0, salida=salida1)
        gc.generar_autolog_1h(seed=42, filas_objetivo=2660, minutos=60.0, salida=salida2)
        assert _sha256(salida1) == _sha256(salida2)


def test_autolog_semillas_distintas_dan_datos_distintos():
    with tempfile.TemporaryDirectory() as tmp:
        salida1 = Path(tmp) / "a.csv"
        salida2 = Path(tmp) / "b.csv"
        gc.generar_autolog_1h(seed=1, filas_objetivo=2660, minutos=60.0, salida=salida1)
        gc.generar_autolog_1h(seed=2, filas_objetivo=2660, minutos=60.0, salida=salida2)
        assert _sha256(salida1) != _sha256(salida2)


def test_autolog_canales_constantes_siguen_constantes():
    """`Oil Temperature` (constante a 2531 en el real, §1.11) debe seguir constante."""
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "autolog-mini.csv"
        gc.generar_autolog_1h(seed=3, filas_objetivo=None, minutos=1.0, salida=salida)

        with open(salida, newline="") as f:
            texto = f.read()
        lineas = texto.replace("\r\n", "\n").split("\n")
        if lineas and lineas[-1] == "":
            lineas.pop()

        # localizar el índice de columna de "Oil Temperature"
        idx_canal = 0
        col = None
        i = 1
        while not lineas[i].startswith("Channel :"):
            i += 1
        while lineas[i].startswith("Channel :"):
            nombre = lineas[i].split(" : ", 1)[1]
            if nombre == "Oil Temperature":
                col = idx_canal
            idx_canal += 1
            i += 1
            i += 1  # ID
            i += 1  # Type
            if lineas[i].startswith("DisplayMaxMin"):
                i += 1
        assert col is not None, "no se encontró el canal Oil Temperature"

        idx_log = next(j for j, ln in enumerate(lineas) if ln.startswith("Log :"))
        filas = lineas[idx_log + 1 :]
        valores = {fila.split(",")[1 + col] for fila in filas}
        assert valores == {"2531"}


# --------------------------------------------------------------------------- #
# internos
# --------------------------------------------------------------------------- #


def test_internos_genera_n_ficheros_con_25_canales():
    with tempfile.TemporaryDirectory() as tmp:
        salida_dir = Path(tmp) / "internal-x20"
        ficheros = gc.generar_internos(
            seed=5,
            n_logs=2,
            primer_log_number=2800,
            duracion_min_ms=7000,
            duracion_max_ms=15000,
            salida_dir=salida_dir,
        )
        assert len(ficheros) == 2
        for ruta in ficheros:
            assert ruta.exists()
            n_canales, filas = _parsear_para_test(ruta)
            assert n_canales == 25
            assert len(filas) > 0
            for fila in filas:
                n_celdas = len(fila.split(",")) - 1
                assert n_celdas == n_canales


def test_internos_epoch_ficticia_y_log_number():
    with tempfile.TemporaryDirectory() as tmp:
        salida_dir = Path(tmp) / "internal-x20"
        ficheros = gc.generar_internos(
            seed=6,
            n_logs=3,
            primer_log_number=2800,
            duracion_min_ms=7000,
            duracion_max_ms=15000,
            salida_dir=salida_dir,
        )
        numeros_esperados = {2800, 2801, 2802}
        numeros_vistos = set()
        for ruta in ficheros:
            texto = ruta.read_text()
            assert "Log Source : 8" in texto
            assert "Log : 19800101 01:01:01" in texto
            for linea in texto.splitlines():
                if linea.startswith("Log Number :"):
                    numeros_vistos.add(int(linea.split(":", 1)[1].strip()))
        assert numeros_vistos == numeros_esperados


def test_internos_marcas_monotonas_dentro_de_cada_fichero():
    with tempfile.TemporaryDirectory() as tmp:
        salida_dir = Path(tmp) / "internal-x20"
        ficheros = gc.generar_internos(
            seed=7,
            n_logs=2,
            primer_log_number=2800,
            duracion_min_ms=7000,
            duracion_max_ms=15000,
            salida_dir=salida_dir,
        )
        for ruta in ficheros:
            _, filas = _parsear_para_test(ruta)
            tiempos = _tiempos_ms(filas)
            assert all(tiempos[i + 1] > tiempos[i] for i in range(len(tiempos) - 1))


def test_internos_determinismo_misma_semilla():
    with tempfile.TemporaryDirectory() as tmp:
        dir1 = Path(tmp) / "d1"
        dir2 = Path(tmp) / "d2"
        f1 = gc.generar_internos(
            seed=99,
            n_logs=2,
            primer_log_number=2800,
            duracion_min_ms=7000,
            duracion_max_ms=15000,
            salida_dir=dir1,
        )
        f2 = gc.generar_internos(
            seed=99,
            n_logs=2,
            primer_log_number=2800,
            duracion_min_ms=7000,
            duracion_max_ms=15000,
            salida_dir=dir2,
        )
        assert [p.name for p in f1] == [p.name for p in f2]
        for p1, p2 in zip(f1, f2, strict=True):
            assert _sha256(p1) == _sha256(p2)


def test_internos_celdas_vacias_alrededor_del_56_por_ciento():
    with tempfile.TemporaryDirectory() as tmp:
        salida_dir = Path(tmp) / "internal-x20"
        ficheros = gc.generar_internos(
            seed=8,
            n_logs=5,
            primer_log_number=2800,
            duracion_min_ms=7000,
            duracion_max_ms=15000,
            salida_dir=salida_dir,
        )
        for ruta in ficheros:
            info = gc.verificar_fichero(ruta)
            # margen amplio: son logs cortos (7-15s), el % exacto varía por azar
            assert 40.0 <= info["pct_celdas_vacias"] <= 70.0


# --------------------------------------------------------------------------- #
# verificar
# --------------------------------------------------------------------------- #


def test_verificar_reporta_dt_coherente():
    # Una vuelta completa del dt real (2636 filas, sin relleno por paseo
    # aleatorio) reproduce exactamente el perfil temporal medido en §1.7;
    # una fracción arbitraria de esa vuelta (p. ej. solo el primer minuto)
    # no es representativa del perfil global y no tiene por qué cumplirlo.
    with tempfile.TemporaryDirectory() as tmp:
        salida = Path(tmp) / "autolog-mini.csv"
        gc.generar_autolog_1h(seed=9, filas_objetivo=2636, minutos=60.0, salida=salida)
        info = gc.verificar_fichero(salida)
        assert info["canales"] == 475
        assert info["dt_min"] >= 35
        assert info["dt_max"] <= 499
        assert 45 <= info["dt_p50"] <= 65
        assert 9.0 <= info["tasa_media_hz"] <= 12.0
