"""La biblioteca de fórmulas de §4.5 (tarea F3-19).

Especificación: `docs/04-perfiles-motorsport.md` §4.5.

QUÉ PROTEGE
===========
`data/formulas.toml` es un dato de puerta G1, y lo que hay que revisar en él no es
la fórmula —esa se lee— sino su CLASE DE MAGNITUD. Una clase equivocada no produce
un error: produce un número plausible con la escala o el origen mal. Un boost
relativo marcado PUNTO en vez de INTERVALO da −14,7 psi con el motor parado.

Estas pruebas comprueban lo que se puede comprobar sin criterio humano:

  - que cada fórmula COMPILA con el evaluador de verdad (F3-18), o sea que no hay
    una errata que nadie descubriría hasta usarla;
  - que su clase es una de las cuatro y su dimensión existe en el catálogo;
  - que los roles que declara existen en `roles.toml`;
  - y la regla estructural que más se falla: **una resta de dos canales de la
    misma dimensión tiene que ser INTERVALO**, salvo donde el fichero declare
    explícitamente por qué no.

Lo que NO puede comprobar es si la clase elegida es la correcta cuando la fórmula
no es una resta simple. Eso es criterio, y es lo que la puerta G1 pide mirar.

Solo biblioteca estándar.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from dlv_core.expresiones import ErrorDeExpresion, compilar
from dlv_core.roles import cargar_catalogo_roles
from dlv_core.unidades import cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
FORMULAS_TOML = RAIZ / "data" / "formulas.toml"
UNITS_TOML = RAIZ / "data" / "units.toml"
ROLES_TOML = RAIZ / "data" / "roles.toml"

CLASES = ("punto", "intervalo", "tasa", "varianza")


def _bruto() -> dict[str, Any]:
    with FORMULAS_TOML.open("rb") as fh:
        return tomllib.load(fh)


FORMULAS: list[dict[str, Any]] = list(_bruto().get("formula", []))
IDS = [str(f["id"]) for f in FORMULAS]


@pytest.fixture(scope="module")
def dimensiones() -> frozenset[str]:
    with UNITS_TOML.open("rb") as fh:
        cat = cargar_catalogo(fh)
    return frozenset(cat.dimensiones)


@pytest.fixture(scope="module")
def roles_conocidos() -> frozenset[str]:
    with ROLES_TOML.open("rb") as fh:
        return frozenset(cargar_catalogo_roles(fh))


def test_la_biblioteca_no_esta_vacia() -> None:
    """§4.5 tiene nueve filas; dos NO son expresiones por muestra y se excluyen.

    Marcha estimada es una agrupación sobre todo el log, y el delta de un contador
    necesita la muestra anterior. Las dos están declaradas en
    `[[fuera_de_biblioteca]]` con dónde viven y por qué, porque una fila de §4.5
    que simplemente falte es indistinguible de un olvido.
    """
    assert len(FORMULAS) >= 7
    fuera = _bruto().get("fuera_de_biblioteca", [])
    assert len(fuera) >= 2, "si se excluye una fila de §4.5, hay que decir cuál y por qué"
    for e in fuera:
        assert str(e.get("motivo", "")).strip()
        assert str(e.get("donde", "")).strip()


@pytest.mark.parametrize("f", FORMULAS, ids=IDS)
def test_cada_formula_compila_con_el_evaluador_de_verdad(f: dict[str, Any]) -> None:
    """No se valida con una regex: se compila con `expresiones.compilar`.

    Es la diferencia entre «parece una fórmula» y «el programa la puede evaluar».
    Una llave sin cerrar o una función que no está en la lista blanca no se ve
    leyendo, y aquí revienta.
    """
    compilada = compilar(str(f["formula"]))
    assert compilada.referencias, f"{f['id']} no referencia ningún canal"


@pytest.mark.parametrize("f", FORMULAS, ids=IDS)
def test_cada_formula_declara_una_clase_valida(f: dict[str, Any]) -> None:
    assert f.get("clase") in CLASES, (
        f"{f['id']} declara clase {f.get('clase')!r}; las cuatro son {CLASES}. "
        "La clase NO tiene valor por omisión (regla 4 de CLAUDE.md)"
    )


@pytest.mark.parametrize("f", FORMULAS, ids=IDS)
def test_la_dimension_existe_en_el_catalogo(f: dict[str, Any], dimensiones: frozenset[str]) -> None:
    assert f["dimension"] in dimensiones, (
        f"{f['id']} declara la dimensión {f['dimension']!r}, que no está en units.toml"
    )


@pytest.mark.parametrize("f", FORMULAS, ids=IDS)
def test_los_roles_existen(f: dict[str, Any], roles_conocidos: frozenset[str]) -> None:
    """Una fórmula se define por roles para que funcione en otro fabricante.

    Un rol inventado hace que la fórmula no se pueda instanciar nunca, y el fallo
    aparecería al importar el log de otro, no aquí.
    """
    declarados = [str(r) for r in f.get("roles", [])]
    assert declarados, f"{f['id']} no declara roles"
    faltan = [r for r in declarados if r not in roles_conocidos]
    assert not faltan, f"{f['id']} declara roles que no están en roles.toml: {faltan}"


@pytest.mark.parametrize("f", FORMULAS, ids=IDS)
def test_cada_formula_explica_su_clase(f: dict[str, Any]) -> None:
    """Un comentario no basta: el fichero tiene que decir algo de cada una.

    `nota` es lo que la puerta G1 lee. Una entrada sin nota es un número sin
    justificar, que es exactamente lo que este fichero existe para evitar.
    """
    assert str(f.get("nota", "")).strip(), f"{f['id']} no explica nada"
    assert str(f.get("etiqueta", "")).strip(), f"{f['id']} no tiene etiqueta"


# --------------------------------------------------------------------------- #
# La regla estructural que más se falla
# --------------------------------------------------------------------------- #
#: Fórmulas que son una resta de dos canales y NO son intervalos. Cada una tiene
#: que estar aquí a propósito y con su motivo: la lista es la excepción declarada,
#: no una válvula de escape.
RESTAS_QUE_NO_SON_INTERVALOS = {
    "error_lambda": (
        "resta un 1 adimensional a un cociente lambda/lambda, así que el resultado "
        "es una razón y no una diferencia de la dimensión de los operandos"
    ),
}


def _es_resta_de_canales(formula: str) -> bool:
    """¿La fórmula resta algo? Con `-` fuera de una llave de canal."""
    profundidad = 0
    for c in formula:
        if c == "{":
            profundidad += 1
        elif c == "}":
            profundidad -= 1
        elif c == "-" and profundidad == 0:
            return True
    return False


@pytest.mark.parametrize("f", FORMULAS, ids=IDS)
def test_una_resta_de_la_misma_dimension_es_un_intervalo(f: dict[str, Any]) -> None:
    """La regla que decide, y la que produce la trampa del delta al olvidarla.

    Si una fórmula resta y se marca PUNTO, o está mal o hay una razón. Las razones
    van en `RESTAS_QUE_NO_SON_INTERVALOS`, escritas, y así añadir una excepción es
    un cambio visible en la prueba en vez de un descuido en el dato.
    """
    if not _es_resta_de_canales(str(f["formula"])):
        return
    fid = str(f["id"])
    if fid in RESTAS_QUE_NO_SON_INTERVALOS:
        assert f["clase"] != "intervalo", (
            f"{fid} está en la lista de restas que NO son intervalos, pero se declara "
            "intervalo: sobra de la lista o la clase está mal"
        )
        return
    assert f["clase"] == "intervalo", (
        f"{fid} resta dos canales y se declara {f['clase']!r}. Una diferencia entre dos "
        f"valores de la misma dimensión es un INTERVALO: como PUNTO se le aplicaría el "
        f"desplazamiento de origen y un cero saldría como −273,15 °C o −14,7 psi. Si "
        f"hay un motivo, va en RESTAS_QUE_NO_SON_INTERVALOS con su explicación"
    )


def test_la_lista_de_excepciones_no_tiene_entradas_muertas() -> None:
    """Una excepción para una fórmula que ya no existe es permiso sin uso."""
    huerfanas = [k for k in RESTAS_QUE_NO_SON_INTERVALOS if k not in IDS]
    assert not huerfanas, f"excepciones sin fórmula: {huerfanas}"


def test_ninguna_formula_necesita_la_muestra_anterior() -> None:
    """La frontera del fichero, fijada en vez de asumida.

    Aquí cabe lo que se calcula con la muestra de ESE instante y las constantes.
    Un delta necesita la anterior, así que no cabe — y este fichero lo tuvo escrito
    como `delta({Knock Sensor 1 Knock Count})` hasta que
    `test_cada_formula_compila_con_el_evaluador_de_verdad` lo compiló de verdad y
    saltó: `delta` no está en la lista blanca de `expresiones.py`.

    Lo cómodo habría sido añadir `delta` al evaluador. Habría convertido una lista
    blanca de nodos de AST en un lenguaje con estado, cuando
    `primitivas.delta_de_contador` ya lo hace vectorizado y devolviendo
    `Clase.INTERVALO`. Esta prueba impide que la comodidad gane la próxima vez.
    """
    prohibidas = ("delta(", "derivada(", "media_movil(", "acumulado(")
    for f in FORMULAS:
        formula = str(f["formula"])
        usadas = [p for p in prohibidas if p in formula]
        assert not usadas, (
            f"{f['id']} usa {usadas}, que necesitan más de una muestra. Su sitio es "
            "`primitivas.py`, y la exclusión se declara en [[fuera_de_biblioteca]]"
        )

    # Y la exclusión del delta de knock tiene que seguir declarada, con su destino.
    fuera = {str(e["id"]): e for e in _bruto().get("fuera_de_biblioteca", [])}
    assert "delta_knock" in fuera, "§4.5 tiene el delta de conteo de knock; hay que ubicarlo"
    assert "primitivas" in str(fuera["delta_knock"]["donde"])


def test_los_identificadores_son_unicos() -> None:
    assert len(IDS) == len(set(IDS)), f"identificadores repetidos en {IDS}"


def test_ninguna_formula_cablea_la_estequiometria() -> None:
    """14,7 dentro de una fórmula es un motor de gasolina dado por hecho.

    Con E85 la estequiometría es ~9,77, y un AFR calculado con 14,7 saldría un 50 %
    alto sin que nada avisara. La estequiometría es un CANAL del log
    (`Fuel Tuning Current Stoichiometry`, confirmado en `haltech_nsp.toml`).
    """
    for f in FORMULAS:
        assert "14.7" not in str(f["formula"]) and "14,7" not in str(f["formula"]), (
            f"{f['id']} lleva la estequiometría dentro de la fórmula; tiene que venir "
            "del rol `stoichiometry`"
        )


def test_una_formula_con_una_errata_no_pasaria() -> None:
    """La prueba de la prueba: si `compilar` aceptara cualquier cosa, la suite de
    arriba no comprobaría nada."""
    with pytest.raises(ErrorDeExpresion):
        compilar("{Manifold Pressure} / ")
    with pytest.raises(ErrorDeExpresion):
        compilar("__import__('os').system('rm -rf /')")


# --------------------------------------------------------------------------- #
# Los canales que las fórmulas piden, contra un log de verdad
# --------------------------------------------------------------------------- #
def _canales_del_autolog() -> frozenset[str]:
    from dlv_core.formatos.nativo import cargar_descriptor, parsear_cabecera

    with (RAIZ / "data" / "formats" / "haltech_nsp.toml").open("rb") as fh:
        desc = cargar_descriptor(fh)
    datos = (RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv").read_bytes()
    return frozenset(c.nombre for c in parsear_cabecera(datos, desc).canales)


@pytest.mark.parametrize("f", FORMULAS, ids=IDS)
def test_los_canales_estan_en_el_log_o_la_falta_esta_declarada(f: dict[str, Any]) -> None:
    """Que la fórmula compile no significa que se pueda evaluar.

    `compilar` valida la sintaxis; no sabe si el canal existe. Esta prueba lo
    comprueba contra el AutoLog real, y así encontró que **el log del propietario
    no trae ningún canal de presión atmosférica**: `boost_relativo` y
    `relacion_de_presiones` referenciaban `Barometric Pressure`, que no está entre
    sus 475 canales.

    La salida no es quitar las fórmulas —son las de §4.5 y en otro log el canal sí
    estará— sino declarar de dónde sale el operando que falta, con
    `requiere_referencia`. Un operando ausente y no declarado se descubre al
    evaluar, con un «canal no encontrado» que no dice que haya otro camino.

    El sufijo `@logB` se salta: por definición no está en este log.
    """
    presentes = _canales_del_autolog()
    comp = compilar(str(f["formula"]))
    faltan = [r.canal for r in comp.referencias if r.canal not in presentes and not r.log]
    if not faltan:
        return
    referencia = str(f.get("requiere_referencia", "")).strip()
    assert referencia, (
        f"{f['id']} pide canales que no están en el AutoLog ({faltan}) y no declara "
        "`requiere_referencia`. O el nombre por omisión está mal, o hay que decir de "
        "dónde sale el operando cuando el log no lo trae"
    )
