#!/usr/bin/env python3
"""Verificación completa del repositorio (docs/08 §8.10, docs/09 §9.4).

Ejecuta las seis comprobaciones que tienen que estar en verde antes de cerrar
cualquier tarea, y devuelve código de salida distinto de cero si algo falla.

    python tools/verificar.py

POR QUÉ EXISTE ESTE GUION
========================
Leer la salida de las herramientas «a ojo» ya dejó pasar dos commits con el lint
en rojo, las dos veces por la misma razón: `ruff check` imprime «No fixes
available…» DESPUÉS de «Found N errors», así que mirar la última línea engaña.
Aquí se usan códigos de salida, que no se pueden malinterpretar.

POR QUÉ EN PYTHON Y NO SOLO EN BASH
===================================
`tools/verificar.sh` sigue existiendo y llama a este fichero, pero la
implementación es Python para que la comprobación obligatoria funcione también en
Windows sin Git Bash. Una regla que no se puede ejecutar en la máquina del
propietario no es una regla: es una recomendación.

CÓMO ENCUENTRA LAS HERRAMIENTAS
===============================
Para cada herramienta se prueba, en orden:

    1. el ejecutable en el PATH          (contenedor de desarrollo, venv activo)
    2. `uv run <herramienta>`            (local tras `uv sync`, sin activar nada)
    3. solo para pytest: `tools/pytest_minimo.py`   (entorno sin red ni PyPI)

Una herramienta que no se encuentra cuenta como FALLO, no como comprobación
omitida. Es la misma lección que «el informe de un agente no es evidencia»: no
haber podido mirar no es lo mismo que estar en verde.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable

# Las seis comprobaciones, en el orden en que conviene verlas: primero las que
# fallan rápido y son mecánicas, luego las pruebas, luego las puertas propias.
COMPROBACIONES: list[tuple[str, list[str]]] = [
    ("ruff check", ["ruff", "check", "."]),
    ("ruff format --check", ["ruff", "format", "--check", "."]),
    ("mypy --strict", ["mypy", "dlv-core", "dlv-api"]),
    ("pytest", ["pytest", "-q"]),
    ("ADR-009", [PY, "tools/banco.py", "adr009"]),
    ("presupuestos", [PY, "tools/banco.py", "comprobar"]),
]

# Rutas de pruebas, duplicadas de `[tool.pytest.ini_options].testpaths` porque el
# sustituto de pytest no lee pyproject.toml. Si se añade un paquete con pruebas,
# hay que tocar los dos sitios; la alternativa —parsear el TOML aquí— añade más
# de lo que ahorra para tres rutas.
RUTAS_DE_PRUEBAS = ("dlv-core/tests", "dlv-api/tests", "dlv-app/tests", "tests")
RUTAS_SRC = ("dlv-core/src", "dlv-api/src", "dlv-app/src")

NEGRITA, VERDE, ROJO, AMARILLO, FIN = (
    ("\033[1m", "\033[32m", "\033[31m", "\033[33m", "\033[0m")
    if sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    else ("", "", "", "", "")
)


@dataclass(slots=True)
class Resultado:
    etiqueta: str
    ok: bool
    detalle: str = ""

    def __str__(self) -> str:
        if self.ok:
            marca = f"{VERDE}OK   {FIN}" if not self.detalle else f"{AMARILLO}OK   {FIN}"
        else:
            marca = f"{ROJO}FALLA{FIN}"
        return f"  {marca} {self.etiqueta}" + (f"  ({self.detalle})" if self.detalle else "")


def _resolver(orden: list[str]) -> list[str] | None:
    """Devuelve la orden ejecutable, o `None` si la herramienta no está."""
    if Path(orden[0]) == Path(PY) or shutil.which(orden[0]):
        return orden
    if shutil.which("uv"):
        return ["uv", "run", *orden]
    return None


def _pytest_de_sustitucion() -> list[str]:
    """`tools/pytest_minimo.py` sobre todas las rutas de pruebas del proyecto.

    Se le pasan los ficheros explícitamente porque no lee `pyproject.toml`, y con
    `PYTHONPATH` porque tampoco aplica `pythonpath` de pytest.
    """
    ficheros: list[str] = []
    for ruta in RUTAS_DE_PRUEBAS:
        ficheros.extend(str(p.relative_to(RAIZ)) for p in sorted((RAIZ / ruta).glob("test_*.py")))
    return [PY, "tools/pytest_minimo.py", *ficheros]


def _ejecutar(etiqueta: str, orden: list[str], entorno: dict[str, str]) -> Resultado:
    print(f"\n{NEGRITA}=== {etiqueta} ==={FIN}", flush=True)
    resuelta = _resolver(orden)
    detalle = ""

    if resuelta is None and etiqueta == "pytest":
        # El único sustituto legítimo: sin PyPI no hay pytest, y quedarse sin
        # ejecutar ninguna prueba sería peor que ejecutarlas con el sustituto.
        # Se marca en el resumen: un verde con sustituto NO es equivalente.
        resuelta = _pytest_de_sustitucion()
        detalle = "con tools/pytest_minimo.py, no con pytest"
    if resuelta is None:
        print(f"{ROJO}no se encuentra '{orden[0]}' ni en el PATH ni vía `uv run`{FIN}")
        return Resultado(etiqueta, ok=False, detalle=f"'{orden[0]}' no disponible")

    if resuelta[:2] == ["uv", "run"]:
        detalle = detalle or "vía `uv run`"
    try:
        completado = subprocess.run(resuelta, cwd=RAIZ, env=entorno, check=False)
    except OSError as e:
        # `shutil.which` puede encontrar un ejecutable que luego no se puede
        # lanzar (permisos, un enlace roto, un `uv` de otro usuario). Una puerta
        # nunca debe reventar: tiene que ponerse roja.
        print(f"{ROJO}no se pudo ejecutar {resuelta[0]!r}: {e}{FIN}")
        return Resultado(etiqueta, ok=False, detalle=f"{resuelta[0]!r} no ejecutable")
    return Resultado(etiqueta, ok=completado.returncode == 0, detalle=detalle)


def main() -> int:
    entorno = dict(os.environ)
    # Para el sustituto de pytest, y sin estorbar a pytest de verdad.
    previo = entorno.get("PYTHONPATH", "")
    rutas = [str(RAIZ / r) for r in RUTAS_SRC]
    entorno["PYTHONPATH"] = os.pathsep.join([*rutas, previo]) if previo else os.pathsep.join(rutas)

    resultados = [_ejecutar(e, o, entorno) for e, o in COMPROBACIONES]

    print(f"\n{NEGRITA}=== RESUMEN ==={FIN}")
    for r in resultados:
        print(r)

    fallos = sum(1 for r in resultados if not r.ok)
    if fallos:
        print(f"\n{ROJO}{fallos} comprobacion(es) en rojo. NO commitear.{FIN}")
    else:
        print(f"\n{VERDE}Todo en verde.{FIN}")
        if any(r.detalle for r in resultados):
            print(
                f"{AMARILLO}Aviso: alguna comprobación usó un sustituto o `uv run`. "
                f"Mira el detalle del resumen antes de dar el verde por definitivo.{FIN}"
            )
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
