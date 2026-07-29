"""Test del invariante arquitectónico más importante del andamiaje (ADR-002, §3.3):

    `dlv-core` no importa nada de `dlv_api`, `dlv_ui` ni `dlv_app`.

Es la condición que permite probar `dlv-core` sola y reutilizarla en
cualquier contenedor futuro (§3.3, última frase). Se comprueba analizando el
árbol sintáctico (`ast`) de cada fichero fuente en vez de importarlo, así el
test no depende de que `polars`/`numpy` estén instalados: solo necesita poder
*parsear* el código, no ejecutarlo.
"""

from __future__ import annotations

import ast
from pathlib import Path

PAQUETES_PROHIBIDOS = ("dlv_api", "dlv_ui", "dlv_app")

RAIZ_SRC = Path(__file__).resolve().parent.parent / "src" / "dlv_core"


def _nombres_importados(arbol: ast.Module) -> set[str]:
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                nombres.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module is not None:
                nombres.add(nodo.module.split(".")[0])
    return nombres


def _ficheros_python() -> list[Path]:
    ficheros = sorted(RAIZ_SRC.rglob("*.py"))
    assert ficheros, f"no se encontraron ficheros .py bajo {RAIZ_SRC}"
    return ficheros


def test_dlv_core_no_importa_los_otros_paquetes() -> None:
    infracciones: list[str] = []
    for fichero in _ficheros_python():
        arbol = ast.parse(fichero.read_text(encoding="utf-8"), filename=str(fichero))
        for nombre in _nombres_importados(arbol):
            if nombre in PAQUETES_PROHIBIDOS:
                infracciones.append(f"{fichero.relative_to(RAIZ_SRC.parent.parent)} importa '{nombre}'")

    assert not infracciones, "dlv-core no puede importar dlv_api/dlv_ui/dlv_app:\n" + "\n".join(
        infracciones
    )


def test_dlv_core_no_menciona_dlv_ui_ni_dlv_app_como_cadena_de_import() -> None:
    """Comprobación adicional y más laxa: ni siquiera como import dinámico
    (`importlib.import_module("dlv_api...")`) debería aparecer el nombre del
    paquete prohibido en el código fuente de `dlv-core`.
    """
    infracciones: list[str] = []
    for fichero in _ficheros_python():
        texto = fichero.read_text(encoding="utf-8")
        for prohibido in PAQUETES_PROHIBIDOS:
            if prohibido in texto:
                infracciones.append(f"{fichero.name} menciona '{prohibido}'")

    assert not infracciones, "\n".join(infracciones)
