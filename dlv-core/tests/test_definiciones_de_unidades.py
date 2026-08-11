"""Cada factor de `units.toml` derivado de su definición (tarea F1-46).

Especificación: `docs/06-sistema-de-unidades.md` §6.5.

QUÉ PROBLEMA RESUELVE
=====================
`data/units.toml` es un dato de puerta G1: ~60 factores de conversión, cada uno
una afirmación sobre el mundo. El problema de revisarlos es que un factor
equivocado no se ve. `3.280839895` y `3.280489935` ocupan lo mismo en la pantalla
y el segundo mete un 0,01 % de error en todas las distancias del programa sin que
nada avise; nadie distingue de memoria `0.06242796058` de `0.06427960580`.

Casi todos esos números, sin embargo, no son medidas: son DEFINICIONES. El pie
son 0,3048 m *exactos* desde 1959, y `psi`, `hp`, `lb·ft` y `lb/ft³` salen de
combinar tres o cuatro definiciones así. Una definición se puede derivar, y algo
derivable no hace falta mirarlo: hace falta calcularlo y comparar.

Eso es lo que hace esta suite. `data/definiciones_de_unidades.toml` declara la
derivación de cada unidad como un producto de constantes exactas citadas; aquí se
ejecuta el producto y se compara con lo que guarda `units.toml`.

POR QUÉ LA COMPARACIÓN VALE ALGO
================================
Solo porque los dos ficheros son independientes. `definiciones_de_unidades.toml`
no copia ni un número de `units.toml`: todo sale de `[constantes]`, y
`[constantes]` solo tiene definiciones con su fuente. Si alguien «arregla» un
desajuste copiando el valor de `units.toml` al fichero de definiciones, esta
suite deja de comprobar cualquier cosa — de ahí la nota en su cabecera.

Y la cobertura no se degrada en silencio: `test_cobertura_exhaustiva` obliga a que
toda unidad no canónica esté declarada o excluida con un motivo. Añadir una
unidad nueva sin decir de dónde sale su factor pone la suite en rojo.

LO QUE ESTA SUITE NO PUEDE DECIR
================================
Que la unidad sea la correcta para el canal. Que el `hp` que quiere el usuario
sea el mecánico y no el métrico es una decisión, no una definición; que el factor
de escala de un canal de Haltech sea 0,1 y no 0,01 es una deducción sobre un
formato ajeno. Nada de eso se deriva, y sigue siendo trabajo de una persona: es
lo que enumera la sección `[[sin_definicion]]`.

Solo biblioteca estándar.
"""

from __future__ import annotations

import math
import tomllib
from pathlib import Path
from typing import Any

import pytest

from dlv_core.unidades import Afin, Catalogo, Reciproca, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
CATALOGO_TOML = RAIZ / "data" / "units.toml"
DEFINICIONES_TOML = RAIZ / "data" / "definiciones_de_unidades.toml"

# `units.toml` guarda los factores con diez cifras significativas. La tolerancia
# relativa es dos órdenes más fina que la última cifra que guarda: cualquier
# desajuste que no sea el redondeo de esa décima cifra es un defecto.
TOLERANCIA_RELATIVA = 1e-9


def _bruto() -> dict[str, Any]:
    with DEFINICIONES_TOML.open("rb") as fh:
        return tomllib.load(fh)


def _tabla(seccion: str) -> list[dict[str, Any]]:
    """Lee la tabla en tiempo de recolección, para un test por unidad.

    Un bucle único diría «falla la tabla»; así dice «falla `pressure.psi`», que es
    la única forma en que el fallo apunta al número que hay que mirar.
    """
    return list(_bruto().get(seccion, []))


DEFINICIONES = _tabla("definicion")
SIN_DEFINICION = _tabla("sin_definicion")
CONSTANTES: dict[str, float] = {str(k): float(v) for k, v in _bruto().get("constantes", {}).items()}


def _ids(entradas: list[dict[str, Any]]) -> list[str]:
    return [f"{e['dimension']}.{e['unidad']}" for e in entradas]


@pytest.fixture(scope="module")
def cat() -> Catalogo:
    with CATALOGO_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


# --------------------------------------------------------------------------- #
# El motor de derivación
# --------------------------------------------------------------------------- #
def _escala(valor: Any) -> float:
    """`escala` admite un número o un par `[numerador, denominador]`.

    El par existe porque 1/60 y 5/9 son exactos como fracción y no como decimal:
    escribir `0.01666666667` en el fichero de definiciones metería en la
    referencia el mismo redondeo que se quiere comprobar en `units.toml`.
    """
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, list) and len(valor) == 2:
        return float(valor[0]) / float(valor[1])
    raise AssertionError(f"`escala` no es un número ni un par [num, den]: {valor!r}")


def _derivar(receta: Any) -> float:
    """`escala · Π constante^exponente`, con la receta tal cual sale del TOML.

    Un número suelto es su propio valor: es el caso de las unidades cuyo factor
    es 1 (mismo tamaño de grado que la canónica, como °C sobre K).
    """
    if isinstance(receta, (int, float)):
        return float(receta)
    if not isinstance(receta, dict):
        raise AssertionError(f"receta de derivación no reconocida: {receta!r}")
    valor = _escala(receta["escala"]) if "escala" in receta else 1.0
    for entrada in receta.get("constantes", []):
        nombre, exponente = str(entrada[0]), int(entrada[1])
        assert nombre in CONSTANTES, f"constante no declarada: {nombre}"
        valor *= CONSTANTES[nombre] ** exponente
    return valor


def test_el_motor_de_derivacion_hace_lo_que_dice() -> None:
    """Sin esto, un fallo del propio motor pasaría por «todo cuadra».

    Es la prueba de la prueba: si `_derivar` ignorase los exponentes negativos o
    tratase `[1, 60]` como 1, todas las comparaciones de abajo seguirían pasando
    para las unidades de factor 1 y fallarían por el mismo motivo en las demás,
    que es indistinguible de «el catálogo está mal».
    """
    assert _derivar(1) == 1.0
    assert _derivar({"escala": [1, 60]}) == pytest.approx(1.0 / 60.0)
    assert _derivar({"escala": [5, 9]}) == pytest.approx(5.0 / 9.0)
    assert _derivar({"constantes": [["pie_en_m", 1]]}) == 0.3048
    # Exponente negativo: 1 lb/ft³ en kg/m³.
    assert _derivar({"constantes": [["libra_en_kg", 1], ["pie_en_m", -3]]}) == pytest.approx(
        0.45359237 / 0.3048**3
    )
    # Escala combinada con constantes: 1 psi en kPa.
    assert _derivar(
        {
            "escala": [1, 1000],
            "constantes": [
                ["libra_en_kg", 1],
                ["gravedad_estandar_m_s2", 1],
                ["pulgada_en_m", -2],
            ],
        }
    ) == pytest.approx(6.894757293168361, rel=1e-12)
    with pytest.raises(AssertionError):
        _derivar({"constantes": [["constante_que_no_existe", 1]]})


def test_las_constantes_son_las_definiciones_citadas() -> None:
    """Las constantes base, comprobadas contra su definición y entre ellas.

    Están en un fichero de datos precisamente para poder auditarlas sin leer
    código, pero las relaciones internas del sistema imperial (una milla son
    5 280 pies, un pie son 12 pulgadas, un grano es lb/7 000) son exactas y
    comprobables aquí: si alguien tocase una sola de las tres, dejarían de
    cuadrar entre sí.
    """
    assert CONSTANTES["milla_en_m"] == pytest.approx(5280 * CONSTANTES["pie_en_m"], rel=1e-15)
    assert CONSTANTES["pie_en_m"] == pytest.approx(12 * CONSTANTES["pulgada_en_m"], rel=1e-15)
    assert CONSTANTES["grano_en_mg"] == pytest.approx(
        CONSTANTES["libra_en_kg"] * 1e6 / 7000, rel=1e-15
    )
    assert CONSTANTES["pi"] == pytest.approx(math.pi, rel=1e-15)
    # g_n no es la gravedad local: es una constante convencional exacta.
    assert CONSTANTES["gravedad_estandar_m_s2"] == 9.80665


# --------------------------------------------------------------------------- #
# La comparación con el catálogo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("caso", DEFINICIONES, ids=_ids(DEFINICIONES))
def test_el_factor_del_catalogo_sale_de_su_definicion(cat: Catalogo, caso: dict[str, Any]) -> None:
    dim = cat.dimension(str(caso["dimension"]))
    unidad = dim.unidades[str(caso["unidad"])]
    conv = unidad.conversion

    if "reciproca" in caso:
        esperado = _derivar(caso["reciproca"])
        assert isinstance(conv, Reciproca), (
            f"{caso['dimension']}.{caso['unidad']} está declarada recíproca en las "
            f"definiciones y el catálogo la tiene como {type(conv).__name__}"
        )
        obtenido = conv.a
    else:
        canonicas_por_unidad = _derivar(caso["canonicas_por_unidad"])
        assert canonicas_por_unidad != 0.0, "una unidad con factor 0 anularía todos los valores"
        # `units.toml` va de la canónica a la unidad mostrada; la definición va al
        # revés («cuántas canónicas hay en una de estas»). De ahí la inversa.
        esperado = 1.0 / canonicas_por_unidad
        assert isinstance(conv, Afin), (
            f"{caso['dimension']}.{caso['unidad']} está declarada afín en las "
            f"definiciones y el catálogo la tiene como {type(conv).__name__}"
        )
        obtenido = conv.a

    # Dos unidades del catálogo (`inHg`, `mmHg`) guardan la inversa del valor ya
    # redondeado que imprime la tabla de NIST, no la del producto exacto de la
    # columna de mercurio. La holgura se declara en el propio fichero de
    # definiciones, con su motivo al lado, para que aflojarla sea un cambio
    # visible en un dato y no una constante escondida en una prueba.
    tolerancia = float(caso.get("tolerancia_relativa", TOLERANCIA_RELATIVA))
    if "tolerancia_relativa" in caso:
        assert str(caso.get("motivo_tolerancia", "")).strip(), (
            f"{caso['dimension']}.{caso['unidad']} afloja la tolerancia sin decir por qué"
        )

    assert obtenido == pytest.approx(esperado, rel=tolerancia), (
        f"{caso['dimension']}.{caso['unidad']}: el catálogo guarda {obtenido!r} y la "
        f"definición da {esperado!r}.\n"
        f"  derivación: {caso['derivacion']}\n"
        f"  origen: {caso['origen']}"
    )


DEFINICIONES_CON_B = [c for c in DEFINICIONES if "b" in c]


@pytest.mark.parametrize("caso", DEFINICIONES_CON_B, ids=_ids(DEFINICIONES_CON_B))
def test_el_desplazamiento_de_origen_sale_de_su_definicion(
    cat: Catalogo, caso: dict[str, Any]
) -> None:
    """`b` es el número que hace peligrosa la trampa del delta.

    Solo las tres unidades de temperatura lo tienen distinto de cero, y por eso se
    declara explícitamente en las definiciones: un `b` que apareciese en otra
    dimensión sería un defecto grave y silencioso, y lo caza
    `test_ninguna_otra_unidad_desplaza_el_origen`.
    """
    dim = cat.dimension(str(caso["dimension"]))
    conv = dim.unidades[str(caso["unidad"])].conversion
    assert isinstance(conv, Afin)
    assert conv.b == pytest.approx(float(caso["b"]), abs=1e-9), (
        f"{caso['dimension']}.{caso['unidad']}: desplazamiento {conv.b!r}, "
        f"la definición dice {caso['b']!r} ({caso['origen']})"
    )


def test_ninguna_otra_unidad_desplaza_el_origen(cat: Catalogo) -> None:
    """Fuera de la temperatura, `b` tiene que ser exactamente 0.

    Un `b` de 101,325 en `pressure` (alguien «arreglando» la presión relativa en
    el catálogo en vez de con `referencia_kpa`) haría que todos los deltas de
    presión saliesen desplazados una atmósfera. El cambio de origen de la presión
    es un parámetro de la conversión, no una propiedad de la unidad: §6.6.
    """
    declaradas = {(str(c["dimension"]), str(c["unidad"])) for c in DEFINICIONES_CON_B}
    for dim_id, dim in cat.dimensiones.items():
        for uni_id, unidad in dim.unidades.items():
            conv = unidad.conversion
            if not isinstance(conv, Afin) or (dim_id, uni_id) in declaradas:
                continue
            assert conv.b == 0.0, (
                f"{dim_id}.{uni_id} desplaza el origen en {conv.b!r} sin declararlo "
                f"en data/definiciones_de_unidades.toml"
            )


# --------------------------------------------------------------------------- #
# Que la cobertura no se degrade
# --------------------------------------------------------------------------- #
def test_cobertura_exhaustiva(cat: Catalogo) -> None:
    """Toda unidad no canónica está derivada o excluida con un motivo.

    Es la parte que hace de esto una puerta y no una colección de ejemplos. Sin
    ella, añadir una unidad nueva con un factor inventado no rompería nada, y la
    cobertura bajaría del 100 % sin que se note; con ella, la reacción obligada al
    añadir una unidad es decir de dónde sale su número.
    """
    derivadas = {(str(c["dimension"]), str(c["unidad"])) for c in DEFINICIONES}
    excluidas = {(str(c["dimension"]), str(c["unidad"])) for c in SIN_DEFINICION}

    faltan: list[str] = []
    for dim_id, dim in cat.dimensiones.items():
        for uni_id in dim.unidades:
            if uni_id == dim.unidad_canonica:
                continue  # la canónica es la identidad por construcción
            if (dim_id, uni_id) not in derivadas | excluidas:
                faltan.append(f"{dim_id}.{uni_id}")

    assert not faltan, (
        "unidades de data/units.toml sin decir de dónde sale su factor: "
        + ", ".join(sorted(faltan))
        + ".\nDeclara su derivación en [[definicion]] o justifícala en [[sin_definicion]]."
    )


def test_no_hay_definiciones_de_unidades_que_ya_no_existen(cat: Catalogo) -> None:
    """Y al revés: una definición huérfana es una comprobación que no comprueba nada."""
    huerfanas: list[str] = []
    for caso in DEFINICIONES + SIN_DEFINICION:
        dim_id, uni_id = str(caso["dimension"]), str(caso["unidad"])
        dim = cat.dimensiones.get(dim_id)
        if dim is None or uni_id not in dim.unidades:
            huerfanas.append(f"{dim_id}.{uni_id}")
    assert not huerfanas, "definiciones sin unidad en el catálogo: " + ", ".join(huerfanas)


def test_toda_definicion_cita_su_fuente() -> None:
    """Un número sin `origen` es una opinión, y este fichero no admite opiniones."""
    for caso in DEFINICIONES:
        etiqueta = f"{caso['dimension']}.{caso['unidad']}"
        assert str(caso.get("origen", "")).strip(), f"{etiqueta} no cita su fuente"
        assert str(caso.get("derivacion", "")).strip(), f"{etiqueta} no explica su derivación"
        assert ("canonicas_por_unidad" in caso) != ("reciproca" in caso), (
            f"{etiqueta} tiene que declarar `canonicas_por_unidad` o `reciproca`, no ambas"
        )
    for caso in SIN_DEFINICION:
        etiqueta = f"{caso['dimension']}.{caso['unidad']}"
        assert str(caso.get("motivo", "")).strip(), f"{etiqueta} se excluye sin motivo"


def test_las_definiciones_no_copian_el_catalogo() -> None:
    """El fichero de definiciones no puede contener los factores de `units.toml`.

    Es la salvaguarda contra la forma más natural de romper esta suite sin querer:
    ver un desajuste, copiar el valor del catálogo al fichero de definiciones y
    ver el verde. A partir de ahí las dos fuentes son una sola y la comparación no
    dice nada.

    Se comprueba sobre el texto, no sobre los valores derivados, porque lo que se
    quiere prohibir es literalmente pegar el número.

    Los comentarios se quedan fuera: la cabecera del fichero usa un factor real
    como ejemplo de lo que no se distingue a ojo, y una prosa que explica el
    problema no es una fuente de la que la prueba lea nada.
    """
    texto = "\n".join(
        linea
        for linea in DEFINICIONES_TOML.read_text(encoding="utf-8").splitlines()
        if not linea.lstrip().startswith("#")
    )
    with CATALOGO_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)

    copiados: list[str] = []
    for dim_id, dim in bruto["dimensiones"].items():
        for uni_id, unidad in dim.get("unidades", {}).items():
            conv = unidad.get("desde_canonica", {})
            a = conv.get("a")
            if not isinstance(a, float) or a in (0.0, 1.0):
                continue
            # Solo los factores de diez cifras: los redondos (100, 1000, 0.001) son
            # inevitablemente comunes a los dos ficheros porque son la definición.
            literal = repr(a)
            if len(literal.replace("0.", "").replace(".", "").lstrip("0")) >= 8 and (
                literal in texto
            ):
                copiados.append(f"{dim_id}.{uni_id} = {literal}")

    assert not copiados, (
        "factores de units.toml copiados literalmente en las definiciones: "
        + ", ".join(copiados)
        + ".\nLa derivación tiene que salir de [constantes], no del fichero que comprueba."
    )
