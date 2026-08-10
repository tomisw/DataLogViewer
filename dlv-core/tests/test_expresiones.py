"""Pruebas del evaluador de expresiones de canal (F3-18).

Especificación: `docs/04-perfiles-motorsport.md` §4.5.

QUÉ PROTEGE ESTA SUITE, POR CONSECUENCIA SI SE ROMPE
=====================================================
1. **No hay `eval()`.** Una fórmula puede venir en un `.dlvprofile` descargado.
   La lista blanca de nodos se prueba con las formas que de verdad se usarían
   para salirse: atributos, subíndices, llamadas, `lambda`, `:=`, cadenas. F5-13
   audita este módulo, y estas pruebas son lo que esa auditoría tendrá delante.
2. **La retención tiene límite.** Es la regla explícita de §4.5: un canal que
   dejó de emitir retenido sin límite dibuja una recta perfecta que parece un
   dato bueno. Con límite sale hueco.
3. **Un hueco en un operando es un hueco en el resultado**, no «el otro
   término». Si λ falta, el λ error no es −1: no existe.
4. **Ni un bucle por muestra** (ADR-009), comprobado por conducta y no solo por
   el patrón que vigila `banco.py`.

Como en `test_reloj.py` y `test_malla.py`, la evaluación se prueba con `XpLista`,
una implementación del protocolo `Vectorial` con biblioteca estándar. No es un
simulacro: ejercita el MISMO código que correrá con NumPy.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from dlv_core.expresiones import (
    ErrorDeExpresion,
    ExpresionCanal,
    Operando,
    Referencia,
    alinear_por_retencion,
    compilar,
    evaluar,
)


# --------------------------------------------------------------------------- #
# El protocolo `Vectorial` con biblioteca estándar
# --------------------------------------------------------------------------- #
class Vec(list[Any]):
    """Vector con la aritmética elemento a elemento que necesita el evaluador.

    Los bucles están AQUÍ, en la prueba, que es donde ADR-009 los permite: lo que
    prohíbe es que estén en `dlv-core`. Con NumPy cada uno de estos métodos es una
    pasada en C sobre el array completo.
    """

    def __getitem__(self, clave: Any) -> Any:  # type: ignore[override]
        if isinstance(clave, slice):
            return Vec(list.__getitem__(self, clave))
        if isinstance(clave, (Vec, list, tuple)):
            claves = list(clave)
            if claves and isinstance(claves[0], bool):
                return Vec(v for v, m in zip(self, claves, strict=True) if m)
            return Vec(list.__getitem__(self, int(i)) for i in claves)
        return list.__getitem__(self, clave)

    def _op(self, otro: Any, f: Any) -> Vec:
        if isinstance(otro, list):
            return Vec(f(a, b) for a, b in zip(self, otro, strict=True))
        return Vec(f(a, otro) for a in self)

    def __add__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a + b)

    def __radd__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: b + a)

    def __sub__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a - b)

    def __rsub__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: b - a)

    def __mul__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a * b)

    __rmul__ = __mul__

    def __truediv__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a / b)

    def __rtruediv__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: b / a)

    def __pow__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a**b)

    def __neg__(self) -> Vec:
        return Vec(-a for a in self)

    def __lt__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a < b)

    def __le__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a <= b)

    def __gt__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a > b)

    def __eq__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a == b)

    def __and__(self, otro: Any) -> Any:
        return Vec(bool(a) and bool(b) for a, b in zip(self, otro, strict=True))

    def __hash__(self) -> int:  # type: ignore[override]
        raise TypeError("un Vec no es hashable, igual que un ndarray")


class XpLista:
    """Las dos funciones del protocolo `Vectorial`, con los nombres de NumPy."""

    def __init__(self) -> None:
        self.llamadas_searchsorted = 0

    def searchsorted(self, a: Any, v: Any, side: str) -> Any:
        import bisect

        self.llamadas_searchsorted += 1
        hallar = bisect.bisect_right if side == "right" else bisect.bisect_left
        lista = list(a)
        return Vec(hallar(lista, x) for x in v)

    def abs(self, a: Any) -> Any:
        if isinstance(a, list):
            return Vec(abs(x) for x in a)
        return abs(a)


@pytest.fixture
def xp() -> XpLista:
    return XpLista()


# --------------------------------------------------------------------------- #
# Compilación: la lista blanca
# --------------------------------------------------------------------------- #
def test_compila_las_formulas_de_la_biblioteca() -> None:
    """Las de §4.5, tal como están escritas en el documento."""
    for formula in (
        "{Wideband O2 1} / {Target Lambda} - 1",
        "{Driven Wheel Speed} - {Vehicle Speed}",
        "{Boost Control Actual Pressure} - {Boost Control Target Pressure}",
        "{Manifold Pressure} / 101.325",
        "abs({Wideband O2 1} - {Target Lambda})",
        "{Manifold Pressure}@A - {Manifold Pressure}@B",
    ):
        compilada = compilar(formula)
        assert compilada.formula == formula
        assert compilada.referencias, formula


def test_las_referencias_salen_en_orden_y_sin_repetir() -> None:
    c = compilar("{a} - {b} + {a}")
    assert c.referencias == (Referencia("a"), Referencia("b"))
    assert c.canales == ("a", "b")


def test_una_referencia_con_log_es_distinta_de_la_misma_sin_log() -> None:
    """`{x}@A - {x}@B` son dos operandos, no uno: es el caso de comparar dos
    logs de §4.5. Si se confundieran, la resta daría cero siempre."""
    c = compilar("{x}@A - {x}@B")
    assert c.referencias == (Referencia("x", "A"), Referencia("x", "B"))
    assert c.canales == ("x",)


def test_acepta_una_expresion_canal_completa() -> None:
    e = ExpresionCanal(
        id="lambda_error",
        formula="{Wideband O2 1} / {Target Lambda} - 1",
        roles_entrada=("lambda_medida", "lambda_objetivo"),
        dimension_resultado="ratio",
    )
    assert compilar(e).canales == ("Wideband O2 1", "Target Lambda")


@pytest.mark.parametrize(
    "formula",
    [
        "{a}.__class__",
        "{a}[0]",
        "open('/etc/passwd')",
        "__import__('os')",
        "(lambda: 1)()",
        "[x for x in {a}]",
        "'texto'",
        "f'{1}'",
        "{a} if {b} else 1",
        "{a} and {b}",
        "{a} > {b}",
        "(y := {a})",
        "{a}; {b}",
        "print({a})",
        "{a}.real",
        "globals()",
        "{a} @ {b}",
    ],
)
def test_la_lista_blanca_rechaza_lo_que_no_es_aritmetica(formula: str) -> None:
    """Cada una de estas es una forma real de salirse de una expresión
    aritmética. La comprobación es por tipo de nodo PERMITIDO, así que una
    sintaxis nueva de Python se rechaza sin haber previsto que existiría."""
    with pytest.raises(ErrorDeExpresion):
        compilar(formula)


def test_una_formula_vacia_se_rechaza() -> None:
    for formula in ("", "   ", "\n"):
        with pytest.raises(ErrorDeExpresion, match="vacía"):
            compilar(formula)


def test_un_nombre_suelto_no_es_un_canal() -> None:
    """Un canal se escribe entre llaves. Sin esta comprobación, `rpm * 2` se
    compilaría y fallaría al evaluar con un mensaje sobre un operando que falta,
    en vez de decir lo que de verdad pasa."""
    with pytest.raises(ErrorDeExpresion, match="entre llaves"):
        compilar("rpm * 2")


def test_el_error_de_sintaxis_dice_que_hacer() -> None:
    with pytest.raises(ErrorDeExpresion, match="entre llaves"):
        compilar("{a} +")


def test_una_funcion_no_permitida_se_rechaza_con_la_lista() -> None:
    with pytest.raises(ErrorDeExpresion, match="sqrt"):
        compilar("sqrt({a})")


def test_los_argumentos_con_nombre_se_rechazan() -> None:
    with pytest.raises(ErrorDeExpresion, match="posicionales"):
        compilar("abs({a}, x=1)")


# --------------------------------------------------------------------------- #
# Retención con límite de validez: la regla de §4.5
# --------------------------------------------------------------------------- #
def test_retiene_el_ultimo_valor_conocido(xp: XpLista) -> None:
    valores, valido = alinear_por_retencion(
        Vec([0, 100, 200]),
        Vec([1.0, 2.0, 3.0]),
        Vec([0, 50, 100, 150, 200]),
        ventana_validez_ms=100,
        xp=xp,
    )
    assert list(valores) == [1.0, 1.0, 2.0, 2.0, 3.0]
    assert list(valido) == [True, True, True, True, True]


def test_pasada_la_ventana_de_validez_hay_hueco(xp: XpLista) -> None:
    """El ejemplo literal de §4.5: canal a 200 ms de periodo con ventana de
    100 ms. Las marcas a más de 100 ms de su última muestra son hueco, no el
    valor retenido."""
    valores, valido = alinear_por_retencion(
        Vec([0, 400]),
        Vec([10.0, 20.0]),
        Vec([0, 100, 150, 300, 400]),
        ventana_validez_ms=100,
        xp=xp,
    )
    assert list(valido) == [True, True, False, False, True]
    # El valor retenido sigue estando en las posiciones inválidas: no se toca,
    # porque quien consume decide cómo representa el hueco. Lo que no puede es
    # leerse como bueno, y para eso está la máscara.
    assert list(valores) == [10.0, 10.0, 10.0, 10.0, 20.0]


def test_antes_de_la_primera_muestra_no_se_extrapola(xp: XpLista) -> None:
    """No hay nada que retener antes del primer dato del canal, y extrapolar
    hacia atrás sería inventar su pasado."""
    _valores, valido = alinear_por_retencion(
        Vec([500]), Vec([7.0]), Vec([0, 100, 500, 600]), ventana_validez_ms=1000, xp=xp
    )
    assert list(valido) == [False, False, True, True]


def test_una_serie_sin_muestras_es_todo_hueco(xp: XpLista) -> None:
    valores, valido = alinear_por_retencion(
        Vec([]), Vec([]), Vec([0, 100]), ventana_validez_ms=100, xp=xp
    )
    assert list(valido) == [False, False]
    assert len(list(valores)) == 2


def test_el_borde_de_la_ventana_es_inclusivo(xp: XpLista) -> None:
    """Exactamente en el límite el valor vale. Elegir el otro lado dejaría un
    canal a 20 Hz con ventana de 50 ms lleno de huecos de un milisegundo."""
    _v, valido = alinear_por_retencion(
        Vec([0]), Vec([1.0]), Vec([50, 51]), ventana_validez_ms=50, xp=xp
    )
    assert list(valido) == [True, False]


def test_una_ventana_no_positiva_se_rechaza(xp: XpLista) -> None:
    for ventana in (0, -10):
        with pytest.raises(ErrorDeExpresion, match="positiva"):
            alinear_por_retencion(Vec([0]), Vec([1.0]), Vec([0]), ventana_validez_ms=ventana, xp=xp)


def test_marcas_y_valores_descuadrados_se_rechazan(xp: XpLista) -> None:
    with pytest.raises(ErrorDeExpresion, match="marcas de tiempo"):
        alinear_por_retencion(Vec([0, 1]), Vec([1.0]), Vec([0]), ventana_validez_ms=10, xp=xp)


# --------------------------------------------------------------------------- #
# Evaluación
# --------------------------------------------------------------------------- #
def test_lambda_error_sobre_dos_canales_a_la_misma_tasa(xp: XpLista) -> None:
    """El canal central del perfil P1: λ real contra λ objetivo, en tanto por
    uno."""
    compilada = compilar("{Wideband O2 1} / {Target Lambda} - 1")
    medida = Operando(t_ms=Vec([0, 50, 100]), v_canonica=Vec([0.90, 1.00, 1.10]))
    objetivo = Operando(t_ms=Vec([0, 50, 100]), v_canonica=Vec([1.00, 1.00, 1.00]))
    resultado, valido = evaluar(
        compilada,
        {Referencia("Wideband O2 1"): medida, Referencia("Target Lambda"): objetivo},
        Vec([0, 50, 100]),
        ventana_validez_ms=100,
        xp=xp,
    )
    assert list(valido) == [True, True, True]
    assert list(resultado) == pytest.approx([-0.10, 0.0, 0.10])


def test_dos_canales_a_tasas_distintas_se_alinean(xp: XpLista) -> None:
    """El caso normal de un log Haltech: 20 Hz contra 5 Hz. El lento se retiene
    sobre la rejilla del rápido."""
    compilada = compilar("{rapido} - {lento}")
    rapido = Operando(t_ms=Vec([0, 50, 100, 150]), v_canonica=Vec([10.0, 11.0, 12.0, 13.0]))
    lento = Operando(t_ms=Vec([0, 200]), v_canonica=Vec([1.0, 2.0]))
    resultado, valido = evaluar(
        compilada,
        {Referencia("rapido"): rapido, Referencia("lento"): lento},
        Vec([0, 50, 100, 150]),
        ventana_validez_ms=200,
        xp=xp,
    )
    assert list(valido) == [True, True, True, True]
    assert list(resultado) == pytest.approx([9.0, 10.0, 11.0, 12.0])


def test_un_hueco_en_un_operando_es_un_hueco_en_el_resultado(xp: XpLista) -> None:
    """Si λ objetivo falta, el λ error no es −1: no existe. Esta es la propiedad
    que impide que una resta con un término ausente se lea como un valor."""
    compilada = compilar("{a} - {b}")
    a = Operando(t_ms=Vec([0, 100, 200]), v_canonica=Vec([1.0, 2.0, 3.0]))
    b = Operando(t_ms=Vec([0]), v_canonica=Vec([1.0]))  # deja de emitir en 0
    _resultado, valido = evaluar(
        compilada,
        {Referencia("a"): a, Referencia("b"): b},
        Vec([0, 100, 200]),
        ventana_validez_ms=100,
        xp=xp,
    )
    assert list(valido) == [True, True, False]


def test_una_referencia_sin_operando_se_rechaza_al_evaluar(xp: XpLista) -> None:
    compilada = compilar("{a} + {b}")
    a = Operando(t_ms=Vec([0]), v_canonica=Vec([1.0]))
    with pytest.raises(ErrorDeExpresion, match=r"\{b\}"):
        evaluar(compilada, {Referencia("a"): a}, Vec([0]), ventana_validez_ms=100, xp=xp)


def test_el_mismo_canal_de_dos_logs_no_se_confunde(xp: XpLista) -> None:
    """El delta entre logs de §4.5. Cada `@` es un operando propio, así que la
    resta compara dos series distintas y no una consigo misma."""
    compilada = compilar("{MAP}@A - {MAP}@B")
    a = Operando(t_ms=Vec([0, 100]), v_canonica=Vec([150.0, 160.0]))
    b = Operando(t_ms=Vec([0, 100]), v_canonica=Vec([100.0, 100.0]))
    resultado, _valido = evaluar(
        compilada,
        {Referencia("MAP", "A"): a, Referencia("MAP", "B"): b},
        Vec([0, 100]),
        ventana_validez_ms=100,
        xp=xp,
    )
    assert list(resultado) == pytest.approx([50.0, 60.0])


def test_los_operadores_y_las_funciones(xp: XpLista) -> None:
    a = Operando(t_ms=Vec([0]), v_canonica=Vec([3.0]))
    b = Operando(t_ms=Vec([0]), v_canonica=Vec([2.0]))
    ops = {Referencia("a"): a, Referencia("b"): b}
    casos = {
        "{a} + {b}": 5.0,
        "{a} - {b}": 1.0,
        "{a} * {b}": 6.0,
        "{a} / {b}": 1.5,
        "{a} ** {b}": 9.0,
        "-{a}": -3.0,
        "+{a}": 3.0,
        "abs({b} - {a})": 1.0,
        "min({a}, {b})": 2.0,
        "max({a}, {b})": 3.0,
        "2 * {a} + 1": 7.0,
    }
    for formula, esperado in casos.items():
        resultado, _ = evaluar(compilar(formula), ops, Vec([0]), ventana_validez_ms=100, xp=xp)
        assert next(iter(resultado)) == pytest.approx(esperado), formula


def test_una_formula_sin_canales_es_valida_en_todas_las_marcas(xp: XpLista) -> None:
    """`2 * 3` no depende de ningún canal, así que no puede tener huecos. Sin
    este caso, `valido` se quedaría en `None` y reventaría al consumirse."""
    resultado, valido = evaluar(
        compilar("2 * 3"), {}, Vec([0, 100, 200]), ventana_validez_ms=100, xp=xp
    )
    assert resultado == pytest.approx(6.0)
    assert list(valido) == [True, True, True]


def test_min_y_max_eligen_elemento_a_elemento(xp: XpLista) -> None:
    a = Operando(t_ms=Vec([0, 100]), v_canonica=Vec([1.0, 9.0]))
    b = Operando(t_ms=Vec([0, 100]), v_canonica=Vec([5.0, 5.0]))
    ops = {Referencia("a"): a, Referencia("b"): b}
    menor, _ = evaluar(compilar("min({a}, {b})"), ops, Vec([0, 100]), ventana_validez_ms=100, xp=xp)
    mayor, _ = evaluar(compilar("max({a}, {b})"), ops, Vec([0, 100]), ventana_validez_ms=100, xp=xp)
    assert list(menor) == pytest.approx([1.0, 5.0])
    assert list(mayor) == pytest.approx([5.0, 9.0])


def test_abs_con_mas_de_un_argumento_se_rechaza(xp: XpLista) -> None:
    a = Operando(t_ms=Vec([0]), v_canonica=Vec([1.0]))
    ops = {Referencia("a"): a}
    with pytest.raises(ErrorDeExpresion, match="un argumento"):
        evaluar(compilar("abs({a}, {a})"), ops, Vec([0]), ventana_validez_ms=100, xp=xp)
    with pytest.raises(ErrorDeExpresion, match="dos argumentos"):
        evaluar(compilar("min({a})"), ops, Vec([0]), ventana_validez_ms=100, xp=xp)


# --------------------------------------------------------------------------- #
# ADR-009 por conducta
# --------------------------------------------------------------------------- #
def test_el_coste_no_crece_con_el_numero_de_muestras(xp: XpLista) -> None:
    """La propiedad que importa: `searchsorted` se llama una vez por OPERANDO,
    no una vez por muestra. Con 20 y con 2000 marcas, las llamadas son las
    mismas — si el evaluador recorriera las muestras en Python, crecerían con la
    longitud de la entrada."""
    compilada = compilar("{a} - {b}")
    for n in (20, 2000):
        contador = XpLista()
        t = Vec(list(range(0, n * 50, 50)))
        a = Operando(t_ms=t, v_canonica=Vec([float(i) for i in range(n)]))
        b = Operando(t_ms=t, v_canonica=Vec([1.0] * n))
        evaluar(
            compilada,
            {Referencia("a"): a, Referencia("b"): b},
            t,
            ventana_validez_ms=100,
            xp=contador,
        )
        assert contador.llamadas_searchsorted == 2, f"n={n}"


def test_no_se_usa_eval_ni_compile_en_el_modulo() -> None:
    """La propiedad de seguridad que audita F5-13, comprobada sobre el árbol
    sintáctico del propio módulo y no por texto: buscar la cadena «eval» la
    encontraría en `mode="eval"` y en los comentarios que explican por qué no se
    usa. Es la misma lección que ya pagó el detector de ADR-009 de `banco.py`."""
    import ast as ast_modulo
    from pathlib import Path

    fuente = Path(__file__).resolve().parents[1] / "src" / "dlv_core" / "expresiones.py"
    arbol = ast_modulo.parse(fuente.read_text(encoding="utf-8"))
    prohibidas = {"eval", "exec", "compile", "__import__", "getattr", "setattr"}
    for nodo in ast_modulo.walk(arbol):
        if isinstance(nodo, ast_modulo.Call) and isinstance(nodo.func, ast_modulo.Name):
            assert nodo.func.id not in prohibidas, (
                f"{fuente.name}:{nodo.lineno} llama a {nodo.func.id}()"
            )


def test_una_formula_hostil_no_ejecuta_nada() -> None:
    """La comprobación de conducta de lo anterior: si hubiera un `eval` en algún
    sitio, esta fórmula tendría efecto. Se rechaza al compilar, así que no llega
    a evaluarse nunca."""
    testigo: list[str] = []

    with pytest.raises(ErrorDeExpresion):
        compilar("__import__('sys').exit(1)")
    with pytest.raises(ErrorDeExpresion):
        compilar("{a}.__class__.__mro__[1].__subclasses__()")
    assert testigo == []


def test_nan_en_los_valores_no_rompe_la_alineacion(xp: XpLista) -> None:
    """Un canal con huecos propios (celda vacía del log, `docs/07` §7.10) llega
    con NaN en los valores. La alineación no los mira: opera sobre las marcas de
    tiempo, así que un NaN se retiene como cualquier otro valor y sale NaN en el
    resultado, que es lo correcto — no se convierte en 0 por el camino."""
    compilada = compilar("{a} + 1")
    nan = float("nan")
    a = Operando(t_ms=Vec([0, 100]), v_canonica=Vec([nan, 5.0]))
    resultado, valido = evaluar(
        compilada, {Referencia("a"): a}, Vec([0, 100]), ventana_validez_ms=100, xp=xp
    )
    assert list(valido) == [True, True]
    valores = list(resultado)
    assert math.isnan(valores[0])
    assert valores[1] == pytest.approx(6.0)
