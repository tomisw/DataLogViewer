#!/usr/bin/env python3
"""Banco de rendimiento de DataLogViewer (tarea F0-04).

Los presupuestos de `docs/02-alcance-y-plan.md` §2.6 son **puertas de CI**, no
aspiraciones. Este banco es lo que las convierte en tales.

Tres estados por presupuesto, y la distinción es lo que hace útil el banco desde
el primer día en lugar de ser un esqueleto:

    CUMPLE       medido y dentro del presupuesto
    INCUMPLE     medido y fuera  -> la compilación falla
    NO_MEDIBLE   la funcionalidad que mide todavía no existe -> no falla nada

Sin el tercer estado habría que elegir entre un banco que siempre falla y un
banco desactivado. Con él, cada presupuesto se activa solo cuando su fase llega.

Uso:
    python tools/banco.py presupuestos              # lista y estado actual
    python tools/banco.py baseline-stdlib           # línea base sin dependencias
    python tools/banco.py spike-polars              # F0-01: exige polars
    python tools/banco.py parseo-cuerpo             # F1-02: mide dlv_core.formatos.cuerpo
    python tools/banco.py comprobar                 # puerta de CI (código != 0 si INCUMPLE)
    python tools/banco.py informe                   # markdown a state/banco/INFORME.md

Solo biblioteca estándar. `polars` y `numpy` son opcionales y su ausencia
produce NO_MEDIBLE, nunca un fallo.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import platform
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

if platform.system() != "Windows":
    import resource
else:
    # La consola de Windows no usa UTF-8 por omisión (cp1252), y este guion
    # imprime ✔/✖/· en `registrar()`.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
BANCO = RAIZ / "state" / "banco"
MEDICIONES = BANCO / "mediciones.json"
INFORME = BANCO / "INFORME.md"

SINTETICO_1H = RAIZ / "samples" / "synth" / "autolog-1h.csv"
REAL_AUTOLOG = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"

Estado = Literal["CUMPLE", "INCUMPLE", "NO_MEDIBLE"]


# --------------------------------------------------------------------------- #
# Presupuestos — transcritos de docs/02-alcance-y-plan.md §2.6
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Presupuesto:
    id: str
    descripcion: str
    unidad: str
    limite: float
    comparador: Literal["<=", ">="]
    fase: str  # fase en la que el presupuesto empieza a ser exigible
    nota: str = ""

    def evalua(self, valor: float) -> Estado:
        ok = valor <= self.limite if self.comparador == "<=" else valor >= self.limite
        return "CUMPLE" if ok else "INCUMPLE"


PRESUPUESTOS: tuple[Presupuesto, ...] = (
    Presupuesto(
        "apertura_primer_grafico",
        "Apertura de log de 66 MB / 475 canales hasta el primer gráfico (p95)",
        "s",
        4.0,
        "<=",
        "F1",
        "el spike de F0-01 mide la parte de parseo; el resto llega con el renderizador",
    ),
    Presupuesto(
        "parseo_nativo",
        "Parseo del camino nativo (enteros, sin comillas), agregado",
        "MB/s",
        100.0,
        ">=",
        "F1",
        "lo mide spike-polars; baseline-stdlib da la referencia a batir",
    ),
    Presupuesto(
        "parseo_generico_numerico", "Parseo genérico numérico, agregado", "MB/s", 60.0, ">=", "FG"
    ),
    Presupuesto(
        "parseo_generico_texto",
        "Parseo genérico con comillas o texto, agregado",
        "MB/s",
        25.0,
        ">=",
        "FG",
    ),
    Presupuesto(
        "segunda_apertura", "Segunda apertura desde la caché Parquet", "ms", 700.0, "<=", "F1"
    ),
    Presupuesto("fps_pan_zoom", "Pan/zoom con 16 canales x 5 M puntos", "fps", 60.0, ">=", "F1"),
    Presupuesto(
        "latencia_cursor", "Cursor hasta tabla de valores actualizada", "ms", 16.0, "<=", "F1"
    ),
    Presupuesto(
        "panzoom_cubos_nuevos",
        "Pan/zoom que requiere cubos nuevos del backend (p95)",
        "ms",
        120.0,
        "<=",
        "F1",
    ),
    Presupuesto("cambio_unidad", "Cambio de unidad con 8 logs abiertos", "ms", 100.0, "<=", "F1"),
    Presupuesto(
        "memoria_residente",
        "Memoria residente con el log de 66 MB abierto",
        "x CSV",
        3.5,
        "<=",
        "F1",
    ),
    Presupuesto(
        "arranque_frio", "Arranque en frío hasta ventana interactiva", "s", 2.5, "<=", "F5"
    ),
    Presupuesto("paquete_zip", "Tamaño del paquete portable comprimido", "MB", 60.0, "<=", "F5"),
    Presupuesto(
        "paquete_sin_comprimir",
        "Tamaño del paquete portable sin comprimir",
        "MB",
        150.0,
        "<=",
        "F5",
    ),
    Presupuesto(
        "bucles_por_muestra",
        "Bucles por muestra en Python dentro de dlv-core (ADR-009)",
        "ocurrencias",
        0.0,
        "<=",
        "F1",
        "se mide por inspección estática, no por tiempo",
    ),
)

POR_ID = {p.id: p for p in PRESUPUESTOS}


# --------------------------------------------------------------------------- #
# Registro de mediciones
# --------------------------------------------------------------------------- #
@dataclass
class Medicion:
    presupuesto: str
    valor: float
    unidad: str
    estado: Estado
    fecha: str
    commit: str
    maquina: dict[str, Any] = field(default_factory=dict)
    detalle: dict[str, Any] = field(default_factory=dict)


def _ahora() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def _commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=True,
        )
        return r.stdout.strip()
    except Exception:
        return "desconocido"


def _maquina() -> dict[str, Any]:
    import os

    return {
        "sistema": platform.system(),
        "maquina": platform.machine(),
        "python": platform.python_version(),
        "nucleos": os.cpu_count(),
    }


def _pico_memoria_mb() -> float:
    """Pico de memoria residente del proceso. `ru_maxrss` está en kB en Linux
    y en bytes en macOS. Windows no tiene `resource`; se usa el contador de
    pico del working set vía `psapi` (solo biblioteca estándar, `ctypes`)."""
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes

        class ContadoresMemoria(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        # `ctypes.windll` no fija argtypes/restype por sí solo, y sin ellos el
        # HANDLE (pseudo-handle de 64 bits) de GetCurrentProcess se trunca a
        # int y GetProcessMemoryInfo falla en silencio (devuelve 0, pico 0 MB).
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ContadoresMemoria),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

        contadores = ContadoresMemoria()
        contadores.cb = ctypes.sizeof(ContadoresMemoria)
        proceso = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(proceso, ctypes.byref(contadores), contadores.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return contadores.PeakWorkingSetSize / (1024 * 1024)

    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return pico / 1024 if platform.system() == "Linux" else pico / (1024 * 1024)


def cargar_mediciones() -> list[dict[str, Any]]:
    if not MEDICIONES.exists():
        return []
    return json.loads(MEDICIONES.read_text(encoding="utf-8"))


def registrar(m: Medicion) -> None:
    BANCO.mkdir(parents=True, exist_ok=True)
    hist = cargar_mediciones()
    hist.append(asdict(m))
    MEDICIONES.write_text(json.dumps(hist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    simbolo = {"CUMPLE": "✔", "INCUMPLE": "✖", "NO_MEDIBLE": "·"}[m.estado]
    p = POR_ID[m.presupuesto]
    print(
        f"  {simbolo} {m.presupuesto}: {m.valor:.2f} {m.unidad} "
        f"(presupuesto {p.comparador} {p.limite}) -> {m.estado}"
    )


def ultima_por_presupuesto() -> dict[str, dict[str, Any]]:
    """La medición más reciente de cada presupuesto."""
    ultima: dict[str, dict[str, Any]] = {}
    for m in cargar_mediciones():
        ultima[m["presupuesto"]] = m
    return ultima


# --------------------------------------------------------------------------- #
# Fichero de trabajo
# --------------------------------------------------------------------------- #
def fichero_grande() -> Path | None:
    """El sintético de 1 h (F0-05) si existe; si no, el AutoLog real, mucho más
    pequeño, que sirve para probar el banco pero no para juzgar presupuestos."""
    if SINTETICO_1H.exists():
        return SINTETICO_1H
    if REAL_AUTOLOG.exists():
        return REAL_AUTOLOG
    return None


def cabecera_y_offset(ruta: Path) -> tuple[int, int]:
    """Devuelve (n_canales, byte de inicio de los datos)."""
    n_canales = 0
    offset = 0
    with ruta.open("rb") as fh:
        for linea in fh:
            if re.match(rb"^\d\d:\d\d:\d\d\.\d\d\d,", linea):
                break
            if linea.startswith(b"Channel"):
                n_canales += 1
            offset += len(linea)
    return n_canales, offset


# --------------------------------------------------------------------------- #
# baseline-stdlib
# --------------------------------------------------------------------------- #
def cmd_baseline_stdlib(_args: argparse.Namespace) -> int:
    """Parsea el fichero grande con el `csv` de la biblioteca estándar.

    No es un candidato de implementación: es la **referencia a batir**. Si
    stdlib tarda N segundos, sabemos cuántas veces más rápido tiene que ser
    Polars para cumplir el presupuesto, que es exactamente la información que
    hace útil el spike de F0-01.
    """
    ruta = fichero_grande()
    if ruta is None:
        print("NO_MEDIBLE: no existe el fichero de trabajo.")
        print("  Genera el sintético con: python tools/generar_corpus.py autolog-1h")
        return 0

    tam_mb = ruta.stat().st_size / 1e6
    n_canales, offset = cabecera_y_offset(ruta)
    print(f"Fichero: {ruta.relative_to(RAIZ)}  ({tam_mb:.2f} MB, {n_canales} canales)")

    t0 = time.perf_counter()
    filas = 0
    celdas = 0
    with ruta.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        fh.seek(0)
        lector = csv.reader(fh)
        for campos in lector:
            if not campos or not re.match(r"^\d\d:\d\d:\d\d\.\d\d\d$", campos[0]):
                continue
            filas += 1
            celdas += len(campos) - 1
    t = time.perf_counter() - t0

    mbs = tam_mb / t
    pico = _pico_memoria_mb()
    print(f"  stdlib csv: {t:.2f} s  ->  {mbs:.1f} MB/s  ({filas} filas, {celdas:,} celdas)")
    print(f"  pico de memoria del proceso: {pico:.0f} MB")

    p = POR_ID["parseo_nativo"]
    factor = p.limite / mbs if mbs > 0 else float("inf")
    print()
    print(f"  Referencia: para cumplir el presupuesto de {p.limite:.0f} MB/s,")
    print(f"  el motor real tiene que ser {factor:.1f}x más rápido que stdlib.")

    registrar(
        Medicion(
            presupuesto="parseo_nativo",
            valor=mbs,
            unidad="MB/s",
            # stdlib no es la implementación: su medición NUNCA juzga el presupuesto.
            estado="NO_MEDIBLE",
            fecha=_ahora(),
            commit=_commit(),
            maquina=_maquina(),
            detalle={
                "motor": "stdlib.csv",
                "es_linea_base": True,
                "fichero": str(ruta.relative_to(RAIZ)),
                "tamano_mb": round(tam_mb, 2),
                "segundos": round(t, 3),
                "filas": filas,
                "celdas": celdas,
                "canales": n_canales,
                "pico_memoria_mb": round(pico, 1),
                "factor_necesario_vs_stdlib": round(factor, 2),
            },
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# spike-polars  (el entregable medible de F0-01)
# --------------------------------------------------------------------------- #
def cmd_spike_polars(args: argparse.Namespace) -> int:
    """F0-01: mide Polars sobre el sintético de 1 h.

    Es la tarea que confirma o refuta la viabilidad de la base Python antes de
    comprometer el resto del plan (docs/02 §2.8, riesgo R9).
    """
    try:
        import polars as pl
    except ImportError:
        print("NO_MEDIBLE: polars no está instalado.")
        print("  Este entorno no tiene red (pip/uv devuelven 403), así que la")
        print("  medición no se puede fabricar. Con red:")
        print("      uv sync --all-packages && python tools/banco.py spike-polars")
        registrar(
            Medicion(
                presupuesto="parseo_nativo",
                valor=0.0,
                unidad="MB/s",
                estado="NO_MEDIBLE",
                fecha=_ahora(),
                commit=_commit(),
                maquina=_maquina(),
                detalle={"motor": "polars", "motivo": "polars no instalado"},
            )
        )
        return 0

    ruta = fichero_grande()
    if ruta is None:
        print("NO_MEDIBLE: falta el fichero de trabajo (genera el sintético de 1 h).")
        return 0

    tam_mb = ruta.stat().st_size / 1e6
    n_canales, offset = cabecera_y_offset(ruta)
    print(f"Fichero: {ruta.relative_to(RAIZ)}  ({tam_mb:.2f} MB, {n_canales} canales)")
    print(f"polars {pl.__version__}")

    tiempos: list[float] = []
    df = None
    pico = 0.0
    for i in range(args.repeticiones):
        t0 = time.perf_counter()
        with ruta.open("rb") as fh:
            fh.seek(offset)
            df = pl.read_csv(
                fh,
                has_header=False,
                separator=",",
                # La columna 0 es HH:MM:SS.mmm; el resto son enteros con hueco.
                schema_overrides={"column_1": pl.Utf8},
                null_values=[""],
                infer_schema_length=2000,
            )
        tiempos.append(time.perf_counter() - t0)
        print(f"  repetición {i + 1}: {tiempos[-1]:.2f} s")
        if i == 0:
            # El pico de memoria del proceso (ru_maxrss / working set) es un
            # máximo histórico que nunca baja: si se mide tras varias
            # repeticiones, la lectura anterior aún no liberada infla el pico
            # muy por encima de lo que cuesta abrir el fichero una vez, que es
            # lo que describe el presupuesto `memoria_residente`. Se captura
            # tras la primera lectura limpia; las repeticiones siguientes solo
            # sirven para el `mejor` tiempo.
            pico = _pico_memoria_mb()

    mejor = min(tiempos)
    mbs = tam_mb / mejor
    filas = 0 if df is None else df.height
    columnas = 0 if df is None else df.width

    print(f"\n  mejor: {mejor:.2f} s -> {mbs:.1f} MB/s  ({filas} filas, {columnas} columnas)")
    print(f"  pico de memoria del proceso: {pico:.0f} MB ({pico / tam_mb:.2f}x el tamaño del CSV)")

    p = POR_ID["parseo_nativo"]
    registrar(
        Medicion(
            presupuesto="parseo_nativo",
            valor=mbs,
            unidad="MB/s",
            estado=p.evalua(mbs),
            fecha=_ahora(),
            commit=_commit(),
            maquina=_maquina(),
            detalle={
                "motor": f"polars {pl.__version__}",
                "es_linea_base": False,
                "fichero": str(ruta.relative_to(RAIZ)),
                "tamano_mb": round(tam_mb, 2),
                "segundos_mejor": round(mejor, 3),
                "segundos_todos": [round(t, 3) for t in tiempos],
                "filas": filas,
                "columnas": columnas,
                "pico_memoria_mb": round(pico, 1),
            },
        )
    )

    # El parseo es la parte dominante de la apertura, así que su tiempo es una
    # cota INFERIOR del presupuesto de apertura: si ya lo incumple aquí, no hay
    # nada que discutir más adelante.
    pa = POR_ID["apertura_primer_grafico"]
    registrar(
        Medicion(
            presupuesto="apertura_primer_grafico",
            valor=mejor,
            unidad="s",
            estado=pa.evalua(mejor) if pa.evalua(mejor) == "INCUMPLE" else "NO_MEDIBLE",
            fecha=_ahora(),
            commit=_commit(),
            maquina=_maquina(),
            detalle={
                "es_cota_inferior": True,
                "nota": "solo parseo; falta indexado, pirámide y primer dibujado",
            },
        )
    )

    memoria = pico / tam_mb
    pm = POR_ID["memoria_residente"]
    registrar(
        Medicion(
            presupuesto="memoria_residente",
            valor=memoria,
            unidad="x CSV",
            estado=pm.evalua(memoria),
            fecha=_ahora(),
            commit=_commit(),
            maquina=_maquina(),
            detalle={"pico_memoria_mb": round(pico, 1), "tamano_csv_mb": round(tam_mb, 2)},
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# parseo-cuerpo  (el entregable medible de F1-02: mide el módulo real, no el
# `read_csv` crudo del spike de F0-01)
# --------------------------------------------------------------------------- #
DESCRIPTOR_HALTECH = RAIZ / "data" / "formats" / "haltech_nsp.toml"


def cmd_parseo_cuerpo(args: argparse.Namespace) -> int:
    """F1-02: mide `dlv_core.formatos.cuerpo.parsear_cuerpo` sobre el sintético de 1 h.

    A diferencia de `spike-polars` (que mide un `pl.read_csv` crudo como techo
    de referencia de F0-01), esto mide la función real que usará el resto del
    pipeline: cabecera vía `dlv_core.formatos.haltech` + proyección a `Int32`
    (la mitigación de memoria que pide la nota de F0-01).
    """
    try:
        import polars as pl  # noqa: F401  (falla aquí si polars no está instalado)

        from dlv_core.formatos.cuerpo import parsear_cuerpo
        from dlv_core.formatos.haltech import cargar_descriptor, parsear_cabecera
    except ImportError as e:
        print(f"NO_MEDIBLE: no se puede importar dlv_core/polars ({e}).")
        return 0

    ruta = fichero_grande()
    if ruta is None:
        print("NO_MEDIBLE: falta el fichero de trabajo (genera el sintético de 1 h).")
        return 0

    with DESCRIPTOR_HALTECH.open("rb") as fh:
        descriptor = cargar_descriptor(fh)

    tam_mb = ruta.stat().st_size / 1e6
    datos = ruta.read_bytes()
    cabecera = parsear_cabecera(datos, descriptor)
    print(f"Fichero: {ruta.relative_to(RAIZ)}  ({tam_mb:.2f} MB, {cabecera.n_canales} canales)")

    tiempos: list[float] = []
    df = None
    pico = 0.0
    for i in range(args.repeticiones):
        t0 = time.perf_counter()
        df = parsear_cuerpo(datos, cabecera)
        tiempos.append(time.perf_counter() - t0)
        print(f"  repetición {i + 1}: {tiempos[-1]:.2f} s")
        if i == 0:
            # Mismo motivo que en spike-polars: el pico de memoria del proceso
            # nunca baja, así que se captura tras la primera lectura limpia.
            pico = _pico_memoria_mb()

    mejor = min(tiempos)
    mbs = tam_mb / mejor
    filas = 0 if df is None else df.height
    columnas = 0 if df is None else df.width

    print(f"\n  mejor: {mejor:.2f} s -> {mbs:.1f} MB/s  ({filas} filas, {columnas} columnas)")
    print(f"  pico de memoria del proceso: {pico:.0f} MB ({pico / tam_mb:.2f}x el tamaño del CSV)")

    p = POR_ID["parseo_nativo"]
    registrar(
        Medicion(
            presupuesto="parseo_nativo",
            valor=mbs,
            unidad="MB/s",
            estado=p.evalua(mbs),
            fecha=_ahora(),
            commit=_commit(),
            maquina=_maquina(),
            detalle={
                "motor": "dlv_core.formatos.cuerpo.parsear_cuerpo",
                "es_linea_base": False,
                "fichero": str(ruta.relative_to(RAIZ)),
                "tamano_mb": round(tam_mb, 2),
                "segundos_mejor": round(mejor, 3),
                "segundos_todos": [round(t, 3) for t in tiempos],
                "filas": filas,
                "columnas": columnas,
                "pico_memoria_mb": round(pico, 1),
            },
        )
    )

    memoria = pico / tam_mb
    pm = POR_ID["memoria_residente"]
    registrar(
        Medicion(
            presupuesto="memoria_residente",
            valor=memoria,
            unidad="x CSV",
            estado=pm.evalua(memoria),
            fecha=_ahora(),
            commit=_commit(),
            maquina=_maquina(),
            detalle={
                "motor": "dlv_core.formatos.cuerpo.parsear_cuerpo",
                "pico_memoria_mb": round(pico, 1),
                "tamano_csv_mb": round(tam_mb, 2),
            },
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# ADR-009: bucles por muestra, por inspección estática
# --------------------------------------------------------------------------- #
# Métodos que recorren los datos elemento a elemento en el intérprete.
#
# La detección es por **AST**, no por texto: un primer intento con expresiones
# regulares marcaba los propios docstrings de `almacen.py` y `piramide.py`, que
# citan `iterrows()` precisamente para prohibirlo. Buscar llamadas en el árbol
# sintáctico ignora por construcción comentarios, docstrings y cadenas.
METODOS_PROHIBIDOS = {
    "iterrows": "iterrows() recorre fila a fila en Python",
    "itertuples": "itertuples() recorre fila a fila en Python",
    "iter_rows": "iter_rows() de Polars recorre fila a fila en Python",
    "applymap": "applymap() aplica una función Python por celda",
}


def _llamadas_prohibidas(arbol: ast.AST) -> list[tuple[int, str]]:
    hallazgos: list[tuple[int, str]] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
            continue
        attr = nodo.func.attr
        if attr in METODOS_PROHIBIDOS:
            hallazgos.append((nodo.lineno, METODOS_PROHIBIDOS[attr]))
        elif attr in ("apply", "map") and any(isinstance(a, ast.Lambda) for a in nodo.args):
            hallazgos.append(
                (nodo.lineno, f"{attr}(lambda) aplica una función Python por elemento")
            )
    return hallazgos


def cmd_adr009(_args: argparse.Namespace) -> int:
    """Comprueba el invariante de ADR-009 sobre `dlv-core`."""
    raiz = RAIZ / "dlv-core" / "src"
    if not raiz.exists():
        print("NO_MEDIBLE: dlv-core/src no existe todavía.")
        return 0

    hallazgos: list[str] = []
    for ruta in sorted(raiz.rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        rel = ruta.relative_to(RAIZ)
        for linea, motivo in _llamadas_prohibidas(arbol):
            hallazgos.append(f"{rel}:{linea}: {motivo}")

    for h in hallazgos:
        print(f"  ✖ {h}")
    if not hallazgos:
        print("  sin patrones de bucle por muestra en dlv-core")

    p = POR_ID["bucles_por_muestra"]
    n = float(len(hallazgos))
    registrar(
        Medicion(
            presupuesto="bucles_por_muestra",
            valor=n,
            unidad="ocurrencias",
            estado=p.evalua(n),
            fecha=_ahora(),
            commit=_commit(),
            maquina=_maquina(),
            detalle={
                "hallazgos": hallazgos,
                "ficheros_inspeccionados": len(list(raiz.rglob("*.py"))),
            },
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# presupuestos / comprobar / informe
# --------------------------------------------------------------------------- #
def _tabla_estado() -> list[tuple[Presupuesto, dict[str, Any] | None]]:
    ultima = ultima_por_presupuesto()
    return [(p, ultima.get(p.id)) for p in PRESUPUESTOS]


def cmd_presupuestos(_args: argparse.Namespace) -> int:
    print(f"{'presupuesto':30s} {'límite':>14s}  {'último':>12s}  estado")
    print("-" * 78)
    for p, m in _tabla_estado():
        lim = f"{p.comparador} {p.limite:g} {p.unidad}"
        if m is None:
            print(f"{p.id:30s} {lim:>14s}  {'—':>12s}  NO_MEDIBLE (sin medir)")
        else:
            val = f"{m['valor']:.2f} {m['unidad']}"
            extra = " (línea base)" if m["detalle"].get("es_linea_base") else ""
            print(f"{p.id:30s} {lim:>14s}  {val:>12s}  {m['estado']}{extra}")
    return 0


def cmd_comprobar(_args: argparse.Namespace) -> int:
    """Puerta de CI. Falla SOLO con INCUMPLE: lo no medible no rompe nada."""
    incumplen = [(p, m) for p, m in _tabla_estado() if m is not None and m["estado"] == "INCUMPLE"]
    for p, m in incumplen:
        print(
            f"✖ {p.id}: {m['valor']:.2f} {m['unidad']}, "
            f"presupuesto {p.comparador} {p.limite:g} — {p.descripcion}"
        )
    if incumplen:
        print(f"\n{len(incumplen)} presupuesto(s) incumplido(s).")
        return 1
    medidos = sum(1 for _, m in _tabla_estado() if m and m["estado"] == "CUMPLE")
    print(f"Sin presupuestos incumplidos. {medidos}/{len(PRESUPUESTOS)} medidos y en verde.")
    return 0


def cmd_informe(_args: argparse.Namespace) -> int:
    L: list[str] = []
    L.append("# Banco de rendimiento")
    L.append("")
    L.append("> Generado por `tools/banco.py informe`. **No editar a mano.**")
    L.append("> Presupuestos: `docs/02-alcance-y-plan.md` §2.6. Historial completo en")
    L.append("> `state/banco/mediciones.json`.")
    L.append("")
    L.append("`NO_MEDIBLE` significa que la funcionalidad que mide todavía no existe;")
    L.append("no falla la compilación. Solo `INCUMPLE` la falla.")
    L.append("")
    L.append("| Presupuesto | Límite | Fase | Última medición | Estado |")
    L.append("|---|---|---|---|---|")
    for p, m in _tabla_estado():
        lim = f"`{p.comparador} {p.limite:g}` {p.unidad}"
        if m is None:
            L.append(f"| {p.descripcion} | {lim} | {p.fase} | — | sin medir |")
        else:
            extra = " *(línea base)*" if m["detalle"].get("es_linea_base") else ""
            simbolo = {"CUMPLE": "✔", "INCUMPLE": "✖", "NO_MEDIBLE": "·"}[m["estado"]]
            L.append(
                f"| {p.descripcion} | {lim} | {p.fase} "
                f"| {m['valor']:.2f} {m['unidad']}{extra} | {simbolo} {m['estado']} |"
            )
    L.append("")

    base = next(
        (m for m in reversed(cargar_mediciones()) if m["detalle"].get("es_linea_base")), None
    )
    if base:
        d = base["detalle"]
        L.append("## Línea base sin dependencias")
        L.append("")
        L.append(
            f"`{d['motor']}` sobre `{d['fichero']}` ({d['tamano_mb']} MB, "
            f"{d.get('canales', '?')} canales): **{d['segundos']} s** "
            f"= {base['valor']:.1f} MB/s."
        )
        L.append("")
        L.append(
            f"Para cumplir el presupuesto de parseo nativo, el motor real debe ser "
            f"**{d['factor_necesario_vs_stdlib']}x más rápido** que la biblioteca "
            f"estándar. Es la cifra que el *spike* de F0-01 tiene que batir."
        )
        L.append("")

    BANCO.mkdir(parents=True, exist_ok=True)
    INFORME.write_text("\n".join(L), encoding="utf-8")
    print(f"→ {INFORME.relative_to(RAIZ)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("presupuestos", help="lista los presupuestos y su estado")
    s.set_defaults(func=cmd_presupuestos)

    s = sub.add_parser("baseline-stdlib", help="línea base de parseo sin dependencias")
    s.set_defaults(func=cmd_baseline_stdlib)

    s = sub.add_parser("spike-polars", help="F0-01: mide Polars (exige polars instalado)")
    s.add_argument("--repeticiones", type=int, default=3)
    s.set_defaults(func=cmd_spike_polars)

    s = sub.add_parser("parseo-cuerpo", help="F1-02: mide dlv_core.formatos.cuerpo.parsear_cuerpo")
    s.add_argument("--repeticiones", type=int, default=3)
    s.set_defaults(func=cmd_parseo_cuerpo)

    s = sub.add_parser("adr009", help="comprueba el invariante de bucles por muestra")
    s.set_defaults(func=cmd_adr009)

    s = sub.add_parser("comprobar", help="puerta de CI: falla si algo INCUMPLE")
    s.set_defaults(func=cmd_comprobar)

    s = sub.add_parser("informe", help="escribe state/banco/INFORME.md")
    s.set_defaults(func=cmd_informe)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
