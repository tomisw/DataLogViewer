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
    de los presupuestos sin implementar todavía.

    La comprobación es sobre el texto del módulo porque lo que se protege es el
    CRITERIO de la puerta, no un resultado concreto: cualquier medición real
    depende de la máquina. La cadena buscada cambió al añadir las desviaciones
    aceptadas (`estado` -> `estado_efectivo`); lo que no puede cambiar es que se
    filtre por un único estado y que ese estado sea INCUMPLE.
    """
    fuente = (RAIZ / "tools" / "banco.py").read_text(encoding="utf-8")
    assert 'm["estado_efectivo"] == "INCUMPLE"' in fuente, (
        "la puerta de CI ya no filtra exclusivamente por INCUMPLE"
    )


# --------------------------------------------------------------------------- #
# Desviaciones aceptadas por el propietario
# --------------------------------------------------------------------------- #
# Lo que se protege aquí es que una aceptación NO se convierta en una barra
# libre. Aceptar un incumplimiento es una decisión legítima del propietario;
# dejar de vigilarlo a partir de ese momento no lo es, porque así es como se
# pierde un presupuesto: no de golpe, sino empeorando un poco cada semana.
def test_una_desviacion_aceptada_no_tumba_la_puerta() -> None:
    assert banco.aplicar_aceptacion("memoria_residente", "INCUMPLE", 4.30) == "ACEPTADO"


def test_pero_si_empeora_vuelve_a_fallar() -> None:
    """El trinquete. Sin esto, aceptar 4,30x autorizaría 8x."""
    assert banco.aplicar_aceptacion("memoria_residente", "INCUMPLE", 4.31) == "INCUMPLE"


def test_la_aceptacion_es_por_presupuesto_y_no_general() -> None:
    """Aceptar la memoria no puede silenciar el parseo."""
    assert banco.aplicar_aceptacion("parseo_nativo", "INCUMPLE", 10.0) == "INCUMPLE"


def test_no_convierte_en_aceptado_lo_que_ya_cumplia() -> None:
    assert banco.aplicar_aceptacion("memoria_residente", "CUMPLE", 3.0) == "CUMPLE"
    assert banco.aplicar_aceptacion("memoria_residente", "NO_MEDIBLE", 0.0) == "NO_MEDIBLE"


def test_el_sentido_de_empeorar_depende_del_comparador() -> None:
    """Para un presupuesto de rendimiento (`>=`) empeorar es BAJAR.

    Cablear «empeorar es subir» habría convertido la aceptación de un
    presupuesto de rendimiento en un permiso permanente: cualquier valor por
    debajo del techo habría contado como aceptado.
    """
    presupuestos_por_id = {p.id: p for p in banco.PRESUPUESTOS}
    assert presupuestos_por_id["memoria_residente"].comparador == "<="
    assert presupuestos_por_id["parseo_nativo"].comparador == ">="

    # Se comprueba con el fichero real: la memoria (`<=`) acepta hasta 4,30 y
    # rechaza 4,31. La rama `>=` se comprueba por construcción del código,
    # porque hoy no hay ninguna desviación aceptada de un presupuesto `>=` — y
    # que no la haya es justo lo que se quiere.
    aceptadas = banco._desviaciones_aceptadas()
    for id_, entrada in aceptadas.items():
        p = presupuestos_por_id[id_]
        techo = float(entrada["peor_aceptado"])
        justo = banco.aplicar_aceptacion(id_, "INCUMPLE", techo)
        peor = techo * (1.01 if p.comparador == "<=" else 0.99)
        assert justo == "ACEPTADO", f"{id_}: el propio techo debería estar aceptado"
        assert banco.aplicar_aceptacion(id_, "INCUMPLE", peor) == "INCUMPLE", (
            f"{id_}: empeorar respecto al techo tiene que volver a fallar"
        )


def test_toda_desviacion_aceptada_esta_documentada() -> None:
    """Una aceptación sin motivo escrito es indistinguible de un descuido.

    Es la misma exigencia que `data/umbrales.toml` para un umbral: el valor sin
    la razón no se puede revisar, y estas entradas las firma el propietario.
    """
    for id_, entrada in banco._desviaciones_aceptadas().items():
        assert id_ in {p.id for p in banco.PRESUPUESTOS}, f"{id_} no es un presupuesto"
        for campo in ("peor_aceptado", "motivo", "fecha", "decidido_por"):
            assert entrada.get(campo), f"{id_}: falta '{campo}'"
        assert len(str(entrada["motivo"]).strip()) > 80, (
            f"{id_}: el motivo es demasiado corto para poder revisarlo"
        )


def test_el_informe_no_enseña_una_desviacion_aceptada_como_verde() -> None:
    """Aceptada no es cumplida.

    El informe es el sitio donde alguien mira para saber cómo va el proyecto;
    si una desviación aceptada saliera con un ✔, en tres meses nadie recordaría
    que sigue incumpliendo el presupuesto de §2.6.
    """
    fuente = (RAIZ / "tools" / "banco.py").read_text(encoding="utf-8")
    assert '"ACEPTADO": "✖"' in fuente, (
        "el informe está a punto de enseñar una desviación aceptada como cumplida"
    )
