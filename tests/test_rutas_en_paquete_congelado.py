"""Ninguna ruta de datos se cuenta con `.parents[]` sin mirar si está congelada.

Especificación: `docs/02-alcance-y-plan.md` E10.1 (ZIP portable) y el `.spec` de
`dlv-app`. El defecto que esta prueba impide es de una clase concreta:

    _RAIZ = Path(__file__).resolve().parents[3]
    _UNITS = _RAIZ / "data" / "units.toml"

En el repositorio funciona siempre. Bajo PyInstaller `onedir` no funciona nunca:
el bytecode del módulo vive dentro del archivo `PYZ`, así que `__file__` no
aterriza en ninguna ruta real del disco y contar `.parents[]` desde ahí da un
directorio que no existe. El paquete ARRANCA y falla al abrir el primer log.

POR QUÉ HACE FALTA UNA PRUEBA Y NO BASTA UN COMENTARIO
======================================================
Porque este fallo no puede aparecer en ninguna otra prueba del repositorio: aquí
la ruta relativa siempre acierta. Solo se manifiesta en la máquina de quien
descarga el ZIP, que es el sitio más caro donde puede aparecer y el único donde
nadie lo va a poder depurar. F1-35 lo dejó anotado como comentario en
`dlv_api.main`, y el comentario sobrevivió intacto y sin efecto hasta F5-01.

`dlv-core` no aparece aquí porque no abre ficheros (ADR-002): si algún día lo
hiciera, esta prueba lo cubriría igual sin tocar nada.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PAQUETES = ("dlv-core", "dlv-api", "dlv-app")

#: El proyecto declara `requires-python = ">=3.12"` en los tres paquetes, y usa
#: la sintaxis de genéricos de PEP 695 (`def f[T](...)`, en `piramide.py`). Un
#: intérprete anterior no puede ni parsear esos ficheros, así que esta prueba los
#: deja fuera y lo DICE en vez de contarlos como limpios: en CI, que va con 3.12,
#: se comprueban todos. Un fichero saltado en silencio es peor que no tener la
#: prueba, porque da una garantía que no existe.
INTERPRETE_COMPLETO = sys.version_info >= (3, 12)


def _fuentes() -> list[Path]:
    return sorted(f for paquete in PAQUETES for f in (RAIZ / paquete / "src").rglob("*.py"))


def _usa_parents(nodo: ast.AST) -> bool:
    """`...parents[N]` en cualquier expresión del subárbol."""
    return any(
        isinstance(n, ast.Subscript)
        and isinstance(n.value, ast.Attribute)
        and n.value.attr == "parents"
        for n in ast.walk(nodo)
    )


def _mira_si_esta_congelada(nodo: ast.AST) -> bool:
    """`sys.frozen` (normalmente vía `getattr`) o `sys._MEIPASS` en el subárbol."""
    return any(
        (isinstance(n, ast.Attribute) and n.attr in {"frozen", "_MEIPASS"})
        or (isinstance(n, ast.Constant) and n.value in {"frozen", "_MEIPASS"})
        for n in ast.walk(nodo)
    )


def test_ninguna_raiz_se_cuenta_por_parents_fuera_de_una_funcion_que_mire_sys_frozen() -> None:
    """El patrón permitido es una función que decida entre las dos raíces.

    No se prohíbe `.parents[]` —es la cuenta correcta en el árbol de código—, se
    exige que esté dentro de algo que sepa que hay dos casos. Si esta prueba se
    pone roja, el arreglo es envolver la ruta como
    `dlv_api.main._raiz_de_datos`, no ensanchar la prueba.
    """
    infracciones: list[str] = []
    sin_parsear: list[str] = []
    for fichero in _fuentes():
        try:
            arbol = ast.parse(fichero.read_text(encoding="utf-8"), filename=str(fichero))
        except SyntaxError:
            if INTERPRETE_COMPLETO:
                raise
            sin_parsear.append(str(fichero.relative_to(RAIZ)))
            continue

        funciones = [
            n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        for funcion in funciones:
            if _usa_parents(funcion) and not _mira_si_esta_congelada(funcion):
                infracciones.append(
                    f"{fichero.relative_to(RAIZ)}:{funcion.lineno} `{funcion.name}` cuenta "
                    ".parents[] sin mirar sys.frozen"
                )

        # Y a nivel de módulo, que es donde estaba el defecto original: una
        # constante calculada al importar no tiene ninguna oportunidad de decidir.
        lineas_en_funciones = {
            n.lineno for f in funciones for n in ast.walk(f) if hasattr(n, "lineno")
        }
        for nodo in arbol.body:
            if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            if _usa_parents(nodo) and nodo.lineno not in lineas_en_funciones:
                infracciones.append(
                    f"{fichero.relative_to(RAIZ)}:{nodo.lineno} calcula una raíz con "
                    ".parents[] al importar el módulo, así que no puede distinguir "
                    "el árbol de código del paquete congelado"
                )

    assert not infracciones, "\n".join(infracciones)
    if sin_parsear:
        # No es un fallo: es el aviso de que esta ejecución cubre menos ficheros
        # que la de CI, con los nombres para que se pueda comprobar a mano.
        print(
            f"AVISO: {len(sin_parsear)} fichero(s) no comprobados con Python "
            f"{sys.version_info.major}.{sys.version_info.minor} (el proyecto pide 3.12): "
            + ", ".join(sin_parsear)
        )


@pytest.mark.parametrize(
    ("relativo", "funcion"),
    [
        ("dlv-api/src/dlv_api/main.py", "_raiz_de_datos"),
        ("dlv-app/src/dlv_app/main.py", "_raiz_datos_de_la_app"),
    ],
)
def test_las_dos_mitades_resuelven_su_raiz_con_el_mismo_patron(relativo: str, funcion: str) -> None:
    """`dlv-app` sirve el frontend y `dlv-api` lee los `data/*.toml`.

    Las dos mitades tienen que localizarse igual: un paquete con el frontend
    encontrado y los datos no encontrados arranca y no sirve para nada, que es
    peor que no arrancar, porque el síntoma no señala la causa.
    """
    arbol = ast.parse((RAIZ / relativo).read_text(encoding="utf-8"))
    definiciones = [
        n
        for n in ast.walk(arbol)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == funcion
    ]
    assert definiciones, f"{relativo} ya no define `{funcion}`: actualiza esta prueba"
    assert _mira_si_esta_congelada(definiciones[0])
    assert _usa_parents(definiciones[0]), (
        f"`{funcion}` ya no cuenta `.parents[]`: si la raíz se resuelve de otra "
        "forma, comprueba que sigue funcionando en el árbol de desarrollo"
    )
