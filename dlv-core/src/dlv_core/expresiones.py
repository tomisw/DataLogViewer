"""Canales matemáticos: series derivadas por expresión sobre otros canales (F3-18).

Especificación: `docs/04-perfiles-motorsport.md` §4.5 (la biblioteca de fórmulas y
la regla de multi-tasa) y `docs/06-sistema-de-unidades.md` §6.5.

    λ error         {Wideband O2 1} / {Target Lambda} - 1
    deslizamiento   {Driven Wheel Speed} - {Vehicle Speed}
    delta entre logs {Manifold Pressure}@A - {Manifold Pressure}@B

TRES DECISIONES, Y LAS TRES SON DE CORRECCIÓN, NO DE COMODIDAD
===============================================================

1. SE EVALÚA EN CANÓNICA, SIEMPRE
   `Operando.v_canonica` se llama así para que no se pueda pasar otra cosa por
   descuido. Si la resta de `{Driven Wheel Speed} - {Vehicle Speed}` se hiciera
   con los valores brutos del almacén, un log en km/h y otro en mph darían un
   deslizamiento inventado, y con el signo cambiado según cuál fuera cuál. La
   conversión bruto -> canónica la hace quien llama, con `unidades.py` y su
   `Clase` obligatoria; este módulo no reimplementa ninguna aritmética de
   unidades y por eso no importa `unidades`.

   La `dimension_resultado` de la expresión NO se deduce: la declara quien
   escribe la fórmula (F3-19 lo hará en un fichero de datos, con su clase de
   magnitud). Deducir la dimensión de `a / b` exigiría un álgebra de dimensiones
   que este proyecto no tiene, y adivinarla produciría una etiqueta de unidad
   plausible y falsa — exactamente el riesgo R1.

2. EL MULTI-TASA SE RESUELVE POR RETENCIÓN, CON LÍMITE DE VALIDEZ
   Los canales de un log Haltech vienen a 20, 10 y 5 Hz entremezclados
   (`docs/01` §1.4), así que dos operandos casi nunca comparten marcas de
   tiempo. Se retiene el último valor conocido de cada operando en cada marca de
   la rejilla de destino.

   Y aquí está la regla que §4.5 escribe explícitamente: **con límite de
   validez**. «Si el canal más lento tiene 200 ms de periodo y la ventana de
   validez es de 100 ms, el resultado es hueco en lugar de un número inventado.»
   Retener sin límite convierte un canal que dejó de emitir —sensor
   desconectado, hueco de grabación— en una línea recta perfecta que parece un
   dato bueno. La ventana la decide quien llama, porque depende del canal: 100 ms
   de retención en λ es razonable y en temperatura de aceite sobra.

   Antes de la primera muestra de un operando NO hay nada que retener, y eso
   también es hueco. No se extrapola hacia atrás.

3. NO HAY `eval()` EN NINGÚN SITIO
   F5-13 («revisión de seguridad: … evaluador de expresiones») audita este
   módulo, y una fórmula puede llegar de un `.dlvprofile` que el usuario se ha
   descargado. El análisis lo hace `ast.parse` en modo `eval` —el analizador de
   Python, que está mucho mejor probado que cualquiera que se escribiera aquí—
   pero el árbol resultante se **valida contra una lista blanca** antes de
   evaluarse, y se evalúa recorriéndolo a mano. Nunca se llama a `eval` ni a
   `compile` con el resultado.

   Lo que la lista blanca deja pasar: números, referencias a canal, los cuatro
   operadores aritméticos más el unario, la potencia y un puñado de funciones.
   Todo lo demás se rechaza con `ErrorDeExpresion`: atributos, subíndices,
   llamadas a funciones que no están en la lista, comparaciones, comprensiones,
   `lambda`, asignaciones con `:=`, cadenas y f-strings. La comprobación es por
   **tipo de nodo permitido**, no por «buscar cosas peligrosas»: una lista negra
   se queda obsoleta con cada versión de Python y una lista blanca no.

`{...}` Y `@`: POR QUÉ HAY UN PASO PREVIO AL ANALIZADOR
=======================================================
`{Wideband O2 1}` no es Python válido, y `@` en Python es el operador de producto
matricial. Así que antes de `ast.parse` cada referencia se sustituye por un
identificador generado (`_ref0`, `_ref1`, …) y se guarda a qué canal y a qué log
apunta. Es un paso de traducción, no de evaluación: lo que se analiza sigue
siendo una expresión aritmética sobre nombres.

Los nombres de canal se comparan tal cual, sin normalizar: `Wideband O2 1` es lo
que dice el log. Quien quiera resolver un rol a un canal concreto lo hace antes
(`identidad.py`), que es donde vive esa decisión.

ADR-009
=======
Ni un bucle por muestra. El árbol se recorre en Python una vez por NODO (una
docena), y cada nodo aplica una operación sobre el array completo. La alineación
por retención es un `searchsorted` —una pasada en C— y no un bucle que busque el
valor anterior de cada marca.

El protocolo `Vectorial` declara las dos únicas funciones de NumPy que hacen
falta, con los nombres de NumPy, así que el propio módulo `numpy` lo satisface
sin adaptador y las pruebas pueden ejercitar ESTE MISMO código con una
implementación de biblioteca estándar (mismo patrón que `reloj.py` y `malla.py`).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

__all__ = [
    "FUNCIONES_PERMITIDAS",
    "ErrorDeExpresion",
    "ExpresionCanal",
    "ExpresionCompilada",
    "Operando",
    "Referencia",
    "Vectorial",
    "alinear_por_retencion",
    "compilar",
    "evaluar",
]


class ErrorDeExpresion(ValueError):
    """La fórmula no se puede compilar o evaluar sin inventar algo.

    Cubre las dos familias por separado en el mensaje: sintaxis y nodos no
    permitidos (al compilar), y operandos que faltan (al evaluar). Es un rechazo
    explicado, nunca una excepción cruda del analizador de Python filtrándose
    hacia arriba: quien escribe una fórmula en el editor de perfiles tiene que
    leer qué está mal, no una traza.
    """


class Vectorial(Protocol):
    """Lo que este módulo necesita de NumPy, y nada más.

    Los nombres y las firmas son los de NumPy, así que el propio módulo `numpy`
    satisface el protocolo sin adaptador. Los parámetros son posicionales para
    que cualquier implementación pueda nombrarlos como quiera.
    """

    def searchsorted(self, a: Any, v: Any, side: str, /) -> Any: ...
    def abs(self, a: Any, /) -> Any: ...


def _numpy() -> Vectorial:
    """Importa NumPy al usarlo, no al importar el módulo.

    Así `compilar` —que es análisis puro— funciona y se prueba sin NumPy
    instalado. Mismo motivo que en `reloj.py` y `malla.py`.
    """
    import numpy

    return cast("Vectorial", numpy)


#: Funciones que una fórmula puede llamar. Cada una está aquí porque alguna de
#: las de §4.5 la necesita o la necesitará, no por completitud: `abs` para un
#: error en valor absoluto, `min`/`max` para acotar un resultado a un rango
#: físico. Añadir una es una línea aquí más su entrada en `_aplicar_funcion`, y
#: pasa por la revisión de seguridad de F5-13 como cualquier otro cambio de este
#: módulo.
FUNCIONES_PERMITIDAS: frozenset[str] = frozenset({"abs", "min", "max"})

#: `{Nombre de canal}` o `{Nombre de canal}@etiquetaDeLog`. El nombre no puede
#: contener llaves; la etiqueta de log es un identificador simple, porque es un
#: alias que pone la aplicación al abrir varios logs y no un nombre libre.
_RE_REFERENCIA = re.compile(r"\{(?P<canal>[^{}]+)\}(?:@(?P<log>[A-Za-z_][A-Za-z0-9_]*))?")

#: Prefijo de los identificadores que sustituyen a las referencias. Lleva `__`
#: para que no pueda chocar con nada que un humano escriba en una fórmula: las
#: referencias a canal van entre llaves, así que un nombre suelto en la fórmula
#: ya es un error de sintaxis y no un identificador legítimo.
_PREFIJO_REF = "__ref"


@dataclass(slots=True, frozen=True)
class Referencia:
    """A qué canal de qué log apunta un `{...}` de la fórmula.

    `log` es `None` en el caso normal —un canal del log que se está mirando— y
    lleva la etiqueta cuando la fórmula compara dos logs (`{canal}@A - {canal}@B`,
    el último caso de §4.5). Es lo que permite que una misma fórmula sirva para un
    log y para una comparación sin dos lenguajes distintos.
    """

    canal: str
    log: str | None = None

    def __str__(self) -> str:
        return f"{{{self.canal}}}" + (f"@{self.log}" if self.log is not None else "")


@dataclass(slots=True, frozen=True)
class ExpresionCanal:
    """Definición de un canal matemático: fórmula + roles que consume."""

    id: str
    formula: str
    roles_entrada: tuple[str, ...]
    dimension_resultado: str | None
    """La declara quien escribe la fórmula; NO se deduce (ver la cabecera).
    `None` significa «sin dimensión»: el resultado se muestra en crudo."""


@dataclass(slots=True, frozen=True)
class ExpresionCompilada:
    """Una fórmula ya analizada y validada, lista para evaluar muchas veces.

    Compilar y evaluar están separados a propósito: la fórmula de un perfil se
    valida una vez, al cargar el perfil, y se evalúa en cada zoom sobre un rango
    distinto. Así un error de sintaxis se ve al abrir el perfil y no a mitad de
    un desplazamiento.
    """

    formula: str
    arbol: ast.Expression
    referencias: tuple[Referencia, ...]
    """En el orden en que aparecen en la fórmula, sin repetidos: es lo que quien
    llama necesita saber para reunir los operandos antes de evaluar."""

    @property
    def canales(self) -> tuple[str, ...]:
        """Los nombres de canal distintos que la fórmula necesita."""
        vistos: dict[str, None] = {}
        for r in self.referencias:
            vistos[r.canal] = None
        return tuple(vistos)


@dataclass(slots=True, frozen=True)
class Operando:
    """Una serie de entrada, YA en unidad canónica.

    El campo se llama `v_canonica` y no `v` a propósito: es la diferencia entre
    una resta correcta y una que mezcla km/h con mph. Quien construye esto aplica
    `to_canon` con la `Clase` que corresponda (`unidades.py`), y este módulo no
    vuelve a convertir nada.

    `t_ms` son las marcas de tiempo de ESTA serie, que no tienen por qué
    coincidir con las de las demás ni con la rejilla de destino: eso es lo que
    resuelve la retención.
    """

    t_ms: Any
    v_canonica: Any


# --------------------------------------------------------------------------- #
# Compilación: analizar y validar contra la lista blanca
# --------------------------------------------------------------------------- #
#: Nodos que una fórmula puede contener. La comprobación es por pertenencia a
#: este conjunto —lista blanca— y no por buscar nodos peligrosos: una lista negra
#: hay que ampliarla con cada versión de Python que añada sintaxis, y olvidarse
#: de ampliarla no se nota hasta que alguien lo aprovecha.
_NODOS_PERMITIDOS: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Call,
)


def _sustituir_referencias(formula: str) -> tuple[str, tuple[Referencia, ...]]:
    """`{a} - {b}@L` -> (`__ref0 - __ref1`, (Referencia(a), Referencia(b, "L"))).

    Dos apariciones de la MISMA referencia comparten identificador, así que
    `{x} - {x}` compila a `__ref0 - __ref0` y quien llama solo tiene que aportar
    un operando. Sin esto, una fórmula con un canal repetido pediría el mismo
    array dos veces.
    """
    referencias: list[Referencia] = []
    indices: dict[Referencia, int] = {}

    def reemplazo(m: re.Match[str]) -> str:
        ref = Referencia(canal=m.group("canal").strip(), log=m.group("log"))
        if ref not in indices:
            indices[ref] = len(referencias)
            referencias.append(ref)
        return f"{_PREFIJO_REF}{indices[ref]}"

    return _RE_REFERENCIA.sub(reemplazo, formula), tuple(referencias)


def _validar(arbol: ast.AST, permitidos: frozenset[str]) -> None:
    """Recorre el árbol y rechaza todo lo que no esté en la lista blanca."""
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, _NODOS_PERMITIDOS):
            raise ErrorDeExpresion(
                f"la fórmula usa {type(nodo).__name__}, que no está permitido en una "
                "expresión de canal. Solo se admiten números, referencias a canal entre "
                f"llaves, los operadores + - * / ** y las funciones {sorted(permitidos)}"
            )
        if isinstance(nodo, ast.Constant) and not isinstance(nodo.value, (int, float)):
            raise ErrorDeExpresion(
                f"la constante {nodo.value!r} no es un número. Una expresión de canal "
                "opera sobre series numéricas; no hay texto ni booleanos"
            )
        if isinstance(nodo, ast.Call):
            if not isinstance(nodo.func, ast.Name) or nodo.func.id not in permitidos:
                # Sin `getattr`: un módulo que audita F5-13 no debería usarlo, y
                # aquí no hace falta — o el nodo es un `Name` y tiene `id`, o no
                # lo es y su tipo ya describe qué se intentó llamar.
                nombre = (
                    nodo.func.id if isinstance(nodo.func, ast.Name) else type(nodo.func).__name__
                )
                raise ErrorDeExpresion(
                    f"la fórmula llama a {nombre!r}, que no es una función permitida. "
                    f"Las permitidas son {sorted(permitidos)}"
                )
            if nodo.keywords:
                raise ErrorDeExpresion(
                    f"la llamada a {nodo.func.id!r} usa argumentos con nombre, y las "
                    "funciones de una expresión de canal solo toman argumentos posicionales"
                )
        # Un `Name` legítimo es o una referencia sustituida o el nombre de una
        # función permitida (el `abs` de `abs(x)` es un `Name` en el árbol).
        es_referencia = nodo.id.startswith(_PREFIJO_REF) if isinstance(nodo, ast.Name) else True
        if isinstance(nodo, ast.Name) and not es_referencia and nodo.id not in permitidos:
            raise ErrorDeExpresion(
                f"{nodo.id!r} no es ni una función permitida ni una referencia a canal. "
                "Un canal se escribe entre llaves: {Nombre del canal}"
            )


def compilar(
    expresion: ExpresionCanal | str,
    *,
    funciones: frozenset[str] = FUNCIONES_PERMITIDAS,
) -> ExpresionCompilada:
    """Analiza y valida una fórmula. No la evalúa y no toca NumPy.

    Acepta la cadena suelta o la `ExpresionCanal` entera, porque el editor de
    perfiles quiere validar lo que el usuario está escribiendo antes de que exista
    una definición completa.

    Lanza `ErrorDeExpresion` con el motivo: sintaxis inválida, un nodo que no está
    en la lista blanca, una constante que no es un número o una llamada a algo que
    no es una función permitida.
    """
    formula = expresion if isinstance(expresion, str) else expresion.formula
    if not formula.strip():
        raise ErrorDeExpresion("la fórmula está vacía")

    traducida, referencias = _sustituir_referencias(formula)
    try:
        arbol = ast.parse(traducida, mode="eval")
    except SyntaxError as exc:
        raise ErrorDeExpresion(
            f"la fórmula {formula!r} no es una expresión válida: {exc.msg}. "
            "Recuerda que un canal se escribe entre llaves: {Nombre del canal}"
        ) from exc

    _validar(arbol, funciones)
    return ExpresionCompilada(formula=formula, arbol=arbol, referencias=referencias)


# --------------------------------------------------------------------------- #
# Alineación multi-tasa por retención
# --------------------------------------------------------------------------- #
def alinear_por_retencion(
    t_origen: Any,
    v_origen: Any,
    t_destino: Any,
    *,
    ventana_validez_ms: float,
    xp: Vectorial | None = None,
) -> tuple[Any, Any]:
    """Retiene el último valor de una serie en cada marca de `t_destino`.

    Devuelve `(valores, valido)`: los valores retenidos y una máscara booleana de
    dónde ese valor se puede usar. `valido` es `False` en dos sitios, y los dos
    son huecos de verdad y no fallos:

    - **Antes de la primera muestra** del operando: no hay nada que retener, y
      extrapolar hacia atrás sería inventar el pasado del canal.
    - **Cuando la última muestra queda más atrás que `ventana_validez_ms`**: es la
      regla de §4.5. Un canal que dejó de emitir retenido sin límite dibuja una
      recta perfecta que parece un dato bueno; con el límite, sale hueco.

    `searchsorted(..., "right") - 1` da el índice de la última muestra con marca
    MENOR O IGUAL que cada marca de destino, en una sola pasada en C. El `-1`
    resultante para las marcas anteriores a la primera muestra se recorta a 0 —el
    valor no se usa, porque su `valido` es `False`— y así no hace falta pedirle
    `clip` al protocolo.
    """
    xp = xp if xp is not None else _numpy()
    if len(t_origen) != len(v_origen):
        raise ErrorDeExpresion(
            f"la serie tiene {len(t_origen)} marcas de tiempo y {len(v_origen)} valores"
        )
    if ventana_validez_ms <= 0:
        raise ErrorDeExpresion(
            f"la ventana de validez tiene que ser positiva, se dio {ventana_validez_ms!r}. "
            "Sin ventana no hay retención, y con ventana infinita un canal que dejó de "
            "emitir se convierte en una recta"
        )
    if len(t_origen) == 0:
        # Sin ninguna muestra no hay nada que retener en ninguna marca.
        ceros = [0.0] * len(t_destino)
        return ceros, [False] * len(t_destino)

    posterior = xp.searchsorted(t_origen, t_destino, "right")
    indices = posterior - 1
    hay_muestra = posterior > 0
    # El índice -1 (marcas anteriores a la primera muestra) se lleva a 0 sumando
    # la propia máscara: donde no hay muestra, -1 + 1 = 0. El valor leído ahí se
    # descarta por `valido`, así que da igual cuál sea.
    indices_seguros = indices + (posterior == 0)
    valores = v_origen[indices_seguros]
    antiguedad = xp.abs(t_destino - t_origen[indices_seguros])
    valido = hay_muestra & (antiguedad <= ventana_validez_ms)
    return valores, valido


# --------------------------------------------------------------------------- #
# Evaluación
# --------------------------------------------------------------------------- #
def _aplicar_funcion(nombre: str, argumentos: Sequence[Any], xp: Vectorial) -> Any:
    if nombre == "abs":
        if len(argumentos) != 1:
            raise ErrorDeExpresion(f"abs() toma un argumento, se dieron {len(argumentos)}")
        return xp.abs(argumentos[0])
    if nombre in ("min", "max"):
        if len(argumentos) != 2:
            raise ErrorDeExpresion(
                f"{nombre}() toma dos argumentos en una expresión de canal (es el "
                f"mínimo elemento a elemento de dos series), se dieron {len(argumentos)}"
            )
        a, b = argumentos
        # Elección elemento a elemento sin pedirle `where` ni `minimum` al
        # protocolo: la máscara booleana multiplica como 0 y 1, y `1 - mascara`
        # la invierte sin necesitar el operador `~` (que la implementación de
        # biblioteca estándar de las pruebas tendría que reimplementar aparte).
        menor = a < b
        if nombre == "min":
            return a * menor + b * (1 - menor)
        return b * menor + a * (1 - menor)
    raise ErrorDeExpresion(f"función no implementada: {nombre!r}")


def _evaluar_nodo(nodo: ast.AST, valores: Mapping[str, Any], xp: Vectorial) -> Any:
    if isinstance(nodo, ast.Expression):
        return _evaluar_nodo(nodo.body, valores, xp)
    if isinstance(nodo, ast.Constant):
        return nodo.value
    if isinstance(nodo, ast.Name):
        try:
            return valores[nodo.id]
        except KeyError:
            raise ErrorDeExpresion(f"falta el operando {nodo.id!r}") from None
    if isinstance(nodo, ast.UnaryOp):
        operando = _evaluar_nodo(nodo.operand, valores, xp)
        return operando if isinstance(nodo.op, ast.UAdd) else -operando
    if isinstance(nodo, ast.BinOp):
        izquierda = _evaluar_nodo(nodo.left, valores, xp)
        derecha = _evaluar_nodo(nodo.right, valores, xp)
        if isinstance(nodo.op, ast.Add):
            return izquierda + derecha
        if isinstance(nodo.op, ast.Sub):
            return izquierda - derecha
        if isinstance(nodo.op, ast.Mult):
            return izquierda * derecha
        if isinstance(nodo.op, ast.Div):
            return izquierda / derecha
        return izquierda**derecha
    if isinstance(nodo, ast.Call):
        nombre = cast("ast.Name", nodo.func).id
        argumentos = [_evaluar_nodo(a, valores, xp) for a in nodo.args]
        return _aplicar_funcion(nombre, argumentos, xp)
    raise ErrorDeExpresion(f"nodo no evaluable: {type(nodo).__name__}")


def evaluar(
    compilada: ExpresionCompilada,
    operandos: Mapping[Referencia, Operando],
    t_destino: Any,
    *,
    ventana_validez_ms: float,
    xp: Vectorial | None = None,
) -> tuple[Any, Any]:
    """Evalúa la expresión sobre `t_destino`, alineando por retención.

    Devuelve `(valores, valido)`. `valido` es `False` en toda marca donde ALGÚN
    operando estuviera fuera de su ventana de validez: si uno de los términos de
    una resta es un hueco, el resultado es un hueco, no el otro término. Quien
    consuma esto pone NaN, deja de dibujar o lo que corresponda a su capa; este
    módulo no decide cómo se representa un hueco, solo dónde está.

    El resultado se calcula en TODAS las marcas, incluidas las inválidas, y por
    una razón de ADR-009: filtrar antes obligaría a recomponer el array después, y
    una división por cero o un `inf` en una posición que se va a descartar no
    molesta a nadie. Lo que no puede pasar es que un valor inválido se lea como
    bueno, y para eso está la máscara.

    El bucle es sobre OPERANDOS (los canales de la fórmula, dos o tres) y sobre
    NODOS del árbol (una docena), nunca sobre muestras.
    """
    xp = xp if xp is not None else _numpy()
    faltan = [r for r in compilada.referencias if r not in operandos]
    if faltan:
        raise ErrorDeExpresion(
            f"la fórmula {compilada.formula!r} necesita {[str(r) for r in faltan]} y no "
            "se ha aportado su serie"
        )

    valores_por_nombre: dict[str, Any] = {}
    valido: Any = None
    for i, referencia in enumerate(compilada.referencias):
        operando = operandos[referencia]
        alineado, valido_i = alinear_por_retencion(
            operando.t_ms,
            operando.v_canonica,
            t_destino,
            ventana_validez_ms=ventana_validez_ms,
            xp=xp,
        )
        valores_por_nombre[f"{_PREFIJO_REF}{i}"] = alineado
        valido = valido_i if valido is None else valido & valido_i

    resultado = _evaluar_nodo(compilada.arbol, valores_por_nombre, xp)
    if valido is None:
        # Una fórmula sin ninguna referencia (`2 * 3`) es válida en todas las
        # marcas: no depende de ningún canal que pueda faltar.
        valido = [True] * len(t_destino)
    return resultado, valido
