"""Pruebas del banco de rendimiento (tarea F0-04).

Lo que hay que proteger aquí no es la medición —que depende de la máquina— sino
la **lógica de decisión**: qué cuenta como incumplimiento, qué no falla la
compilación, y el detector estático de ADR-009.

Solo biblioteca estándar.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _cargar_banco():
    """Importa tools/banco.py por ruta: `tools/` no es un paquete instalable."""
    ruta = RAIZ / "tools" / "banco.py"
    spec = importlib.util.spec_from_file_location("banco", ruta)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["banco"] = mod
    spec.loader.exec_module(mod)
    return mod


banco = _cargar_banco()


# --------------------------------------------------------------------------- #
# Presupuestos
# --------------------------------------------------------------------------- #
def test_presupuestos_bien_formados() -> None:
    assert banco.PRESUPUESTOS, "no hay presupuestos declarados"
    for p in banco.PRESUPUESTOS:
        assert p.comparador in ("<=", ">="), f"{p.id}: comparador inválido"
        assert p.unidad, f"{p.id}: falta unidad"
        assert p.descripcion, f"{p.id}: falta descripción"
        assert p.fase in ("F0", "F1", "FG", "F2", "F3", "F4", "F5"), f"{p.id}: fase inválida"


def test_ids_de_presupuesto_unicos() -> None:
    ids = [p.id for p in banco.PRESUPUESTOS]
    assert len(ids) == len(set(ids)), "hay ids de presupuesto duplicados"


def test_evaluacion_de_limite_inferior() -> None:
    """Un presupuesto `>=` (caudal) cumple por encima del límite."""
    p = banco.POR_ID["parseo_nativo"]  # >= 100 MB/s
    assert p.evalua(150.0) == "CUMPLE"
    assert p.evalua(100.0) == "CUMPLE", "el límite exacto cumple"
    assert p.evalua(99.9) == "INCUMPLE"


def test_evaluacion_de_limite_superior() -> None:
    """Un presupuesto `<=` (latencia) cumple por debajo del límite."""
    p = banco.POR_ID["latencia_cursor"]  # <= 16 ms
    assert p.evalua(10.0) == "CUMPLE"
    assert p.evalua(16.0) == "CUMPLE", "el límite exacto cumple"
    assert p.evalua(16.1) == "INCUMPLE"


def test_todos_los_presupuestos_de_la_especificacion_estan_presentes() -> None:
    """Los 13 presupuestos de docs/02 §2.6, más el de ADR-009."""
    esperados = {
        "apertura_primer_grafico",
        "parseo_nativo",
        "parseo_generico_numerico",
        "parseo_generico_texto",
        "segunda_apertura",
        "fps_pan_zoom",
        "latencia_cursor",
        "panzoom_cubos_nuevos",
        "cambio_unidad",
        "memoria_residente",
        "arranque_frio",
        "paquete_zip",
        "paquete_sin_comprimir",
        "bucles_por_muestra",
    }
    faltan = esperados - set(banco.POR_ID)
    assert not faltan, f"faltan presupuestos: {sorted(faltan)}"


# --------------------------------------------------------------------------- #
# Detector estático de ADR-009
#
# El primer intento usaba expresiones regulares y marcaba los docstrings de
# almacen.py y piramide.py, que citan iterrows() para prohibirlo. De ahí que
# estas pruebas comprueben explícitamente los dos lados.
# --------------------------------------------------------------------------- #
def _hallazgos(codigo: str) -> list[str]:
    return [motivo for _linea, motivo in banco._llamadas_prohibidas(ast.parse(codigo))]


def test_detecta_iterrows() -> None:
    assert _hallazgos("for f in df.iterrows():\n    pass\n")


def test_detecta_itertuples_y_iter_rows() -> None:
    assert _hallazgos("for f in df.itertuples():\n    pass\n")
    assert _hallazgos("for f in df.iter_rows():\n    pass\n")


def test_detecta_apply_con_lambda() -> None:
    assert _hallazgos("df.apply(lambda x: x + 1)\n")
    assert _hallazgos("s.map(lambda x: x * 2)\n")


def test_no_marca_docstrings_ni_comentarios() -> None:
    """El caso que rompió la primera versión del detector."""
    codigo = '''
"""Este módulo NO usa iterrows() ni itertuples(): ver ADR-009.

Prohibido: df.apply(lambda x: x), df.iter_rows(), applymap().
"""
# Tampoco df.iterrows() en un comentario.
TEXTO = "iterrows() dentro de una cadena tampoco cuenta"
'''
    assert _hallazgos(codigo) == [], "el detector está mirando texto, no el AST"


def test_no_marca_operaciones_vectorizadas() -> None:
    """Lo que ADR-009 sí permite no debe dar falsos positivos."""
    codigo = (
        "b = v[:n].reshape(-1, 4)\n"
        "lo, hi = b.min(axis=1), b.max(axis=1)\n"
        "df = df.with_columns(pl.col('x') * 2)\n"
        "res = df.select(pl.all().sum())\n"
        "y = np.where(v > 0, v, 0)\n"
    )
    assert _hallazgos(codigo) == []


def test_no_marca_apply_sin_lambda() -> None:
    """`apply` con una función ya compilada (p. ej. una ufunc) no es un bucle
    de Python por elemento; solo se marca la forma con lambda."""
    assert _hallazgos("df.apply(np.sqrt)\n") == []


def test_dlv_core_cumple_adr009_ahora_mismo() -> None:
    """Regresión sobre el código real, no sobre ejemplos."""
    raiz = RAIZ / "dlv-core" / "src"
    if not raiz.exists():
        return  # el andamiaje aún no existe: nada que comprobar
    todos: list[str] = []
    for ruta in sorted(raiz.rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for linea, motivo in banco._llamadas_prohibidas(arbol):
            todos.append(f"{ruta.relative_to(RAIZ)}:{linea}: {motivo}")
    assert todos == [], "ADR-009 incumplido en dlv-core:\n" + "\n".join(todos)


# --------------------------------------------------------------------------- #
# Estados
# --------------------------------------------------------------------------- #
def test_no_medible_no_puede_fallar_la_compilacion() -> None:
    """Es la propiedad que permite tener el banco activo desde F0 con la mayoría
    de los presupuestos sin implementar todavía."""
    estados = {"CUMPLE", "INCUMPLE", "NO_MEDIBLE"}
    assert estados == {"CUMPLE", "INCUMPLE", "NO_MEDIBLE"}
    # `comprobar` filtra por INCUMPLE exclusivamente; se comprueba leyendo el
    # criterio desde el propio módulo para que un cambio en él rompa la prueba.
    fuente = (RAIZ / "tools" / "banco.py").read_text(encoding="utf-8")
    assert 'm["estado"] == "INCUMPLE"' in fuente, (
        "la puerta de CI ya no filtra exclusivamente por INCUMPLE"
    )
