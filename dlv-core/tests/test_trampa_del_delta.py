"""La trampa del delta y la tabla de casos conocidos (tarea F1-20).

Especificación: `docs/06-sistema-de-unidades.md` §6.5, §6.6 y §6.12.

QUÉ PROTEGE ESTA SUITE
======================
El fallo más caro del subsistema de unidades es aplicar el desplazamiento de
origen a una diferencia: un Δ de 10 K son 10 °C y 18 °F, nunca −263,15 °C. No es
un fallo hipotético, es *la* regresión probable, porque la conversión correcta
para un punto y la correcta para un intervalo se escriben casi igual y solo una
de las dos lleva el `+ b`.

Y es un fallo silencioso en el peor sentido: −263,15 °C se ve raro, pero
−271,15 °C como desviación típica de 2 K se ve exactamente igual que cualquier
otro número negativo grande, y un doble cursor sobre dos temperaturas cercanas da
un delta plausible aunque esté 273 grados desplazado. Nadie lo nota leyendo la
pantalla; se nota cuando alguien toma una decisión de mapa con él.

De ahí la estrategia de esta suite, en tres capas:

1. **La tabla de casos conocidos** vive en `data/casos_de_unidades.toml`, fuera de
   este fichero, para que se pueda auditar sin leer Python (puerta G1). Aquí solo
   está el motor que la recorre.
2. **Puntos y deltas se cruzan a propósito.** No basta con que cada conversión
   salga bien por separado: se comprueba que la MISMA unidad con el MISMO número
   da resultados distintos según la clase, y que difieren exactamente en `b`.
3. **Propiedades algebraicas** que tienen que valer para todas las unidades del
   catálogo, no solo para las de la tabla: ida y vuelta exacta, aditividad del
   intervalo, coherencia entre varianza e intervalo, y linealidad.

Solo biblioteca estándar.
"""

from __future__ import annotations

import math
import tomllib
from pathlib import Path
from typing import Any

import pytest

from dlv_core.unidades import (
    Afin,
    Catalogo,
    Clase,
    Dimension,
    ErrorDeUnidad,
    Reciproca,
    a_canonica,
    cargar_catalogo,
    desde_canonica,
)

RAIZ = Path(__file__).resolve().parents[2]
CATALOGO_TOML = RAIZ / "data" / "units.toml"
CASOS_TOML = RAIZ / "data" / "casos_de_unidades.toml"

CLASES_POR_NOMBRE = {c.value: c for c in Clase}


@pytest.fixture(scope="module")
def cat() -> Catalogo:
    with CATALOGO_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


@pytest.fixture(scope="module")
def casos() -> dict[str, Any]:
    with CASOS_TOML.open("rb") as fh:
        return tomllib.load(fh)


def _ids(entradas: list[dict[str, Any]]) -> list[str]:
    return [str(e["caso"]) for e in entradas]


def _tabla(seccion: str) -> list[dict[str, Any]]:
    """Lee la tabla en tiempo de recolección, para parametrizar caso a caso.

    Un solo test que recorra la tabla en un bucle diría «falla la tabla»; así dice
    «falla el cero Celsius en Fahrenheit», que es la diferencia entre depurar en
    un minuto y en media hora.
    """
    with CASOS_TOML.open("rb") as fh:
        return list(tomllib.load(fh).get(seccion, []))


PUNTOS = _tabla("punto")
DELTAS = _tabla("delta")
VARIANZAS = _tabla("varianza")
REFERENCIAS = _tabla("referencia")
RECHAZOS = _tabla("rechazo")


# --------------------------------------------------------------------------- #
# La tabla de casos conocidos
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("caso", PUNTOS, ids=_ids(PUNTOS))
def test_caso_conocido_como_punto(cat: Catalogo, caso: dict[str, Any]) -> None:
    obtenido = desde_canonica(
        float(caso["canonica"]),
        dimension=cat.dimension(str(caso["dimension"])),
        unidad=str(caso["unidad"]),
        clase=Clase.PUNTO,
    )
    assert obtenido == pytest.approx(float(caso["esperado"]), abs=float(caso["tolerancia"])), (
        f"{caso['caso']}: {caso['canonica']} canónicas deberían ser "
        f"{caso['esperado']} {caso['unidad']} ({caso['origen']})"
    )


@pytest.mark.parametrize("caso", DELTAS, ids=_ids(DELTAS))
def test_caso_conocido_como_delta(cat: Catalogo, caso: dict[str, Any]) -> None:
    obtenido = desde_canonica(
        float(caso["canonica"]),
        dimension=cat.dimension(str(caso["dimension"])),
        unidad=str(caso["unidad"]),
        clase=Clase.INTERVALO,
    )
    assert obtenido == pytest.approx(float(caso["esperado"]), abs=float(caso["tolerancia"])), (
        f"{caso['caso']}: un Δ de {caso['canonica']} canónicas deberían ser "
        f"{caso['esperado']} {caso['unidad']} ({caso['origen']})"
    )


@pytest.mark.parametrize("caso", VARIANZAS, ids=_ids(VARIANZAS))
def test_caso_conocido_como_varianza(cat: Catalogo, caso: dict[str, Any]) -> None:
    obtenido = desde_canonica(
        float(caso["canonica"]),
        dimension=cat.dimension(str(caso["dimension"])),
        unidad=str(caso["unidad"]),
        clase=Clase.VARIANZA,
    )
    assert obtenido == pytest.approx(float(caso["esperado"]), abs=float(caso["tolerancia"])), (
        f"{caso['caso']} ({caso['origen']})"
    )


@pytest.mark.parametrize("caso", REFERENCIAS, ids=_ids(REFERENCIAS))
def test_caso_conocido_con_referencia_de_presion(cat: Catalogo, caso: dict[str, Any]) -> None:
    """El cambio de origen combinado con cualquier unidad de presión (§6.6)."""
    obtenido = desde_canonica(
        float(caso["canonica"]),
        dimension=cat.dimension("pressure"),
        unidad=str(caso["unidad"]),
        clase=CLASES_POR_NOMBRE[str(caso["clase"])],
        referencia_kpa=float(caso["referencia_kpa"]),
    )
    assert obtenido == pytest.approx(float(caso["esperado"]), abs=float(caso["tolerancia"])), (
        f"{caso['caso']} ({caso['origen']})"
    )


@pytest.mark.parametrize("caso", RECHAZOS, ids=_ids(RECHAZOS))
def test_caso_de_rechazo(cat: Catalogo, caso: dict[str, Any]) -> None:
    """Lo que el motor tiene que negarse a hacer.

    Devolver un número aproximado y equivocado es peor que fallar: el usuario no
    tiene forma de saber que lo que ve no significa lo que cree.
    """
    extra: dict[str, Any] = {}
    if "referencia_kpa" in caso:
        extra["referencia_kpa"] = float(caso["referencia_kpa"])
    with pytest.raises(ErrorDeUnidad):
        desde_canonica(
            1.0,
            dimension=cat.dimension(str(caso["dimension"])),
            unidad=str(caso["unidad"]),
            clase=CLASES_POR_NOMBRE[str(caso["clase"])],
            **extra,
        )


def test_la_tabla_cubre_lo_que_exige_la_documentacion(casos: dict[str, Any]) -> None:
    """§6.12 nombra cuatro casos conocidos por su valor. Tienen que estar.

    Es la prueba que impide que la tabla se quede corta sin que nadie lo note: si
    alguien borra el caso de λ 0,850 = φ 1,176, esto falla en vez de pasar con una
    tabla más pequeña.
    """
    exigidos = {
        ("temperature", "degC", 273.15, 0.0),
        ("temperature", "degF", 273.15, 32.0),
        ("pressure", "bar", 100.0, 1.0),
        ("mixture_ratio", "afr_gasolina", 1.0, 14.7),
        ("mixture_ratio", "phi", 0.85, 1.1764706),
    }
    presentes = {
        (str(c["dimension"]), str(c["unidad"]), float(c["canonica"]), float(c["esperado"]))
        for c in casos["punto"]
    }
    faltan = {e for e in exigidos if not any(_casi(e, p) for p in presentes)}
    assert not faltan, f"casos exigidos por docs/06 §6.12 ausentes de la tabla: {sorted(faltan)}"

    # Y los dos deltas que la documentación fija por su número.
    deltas = {
        (str(c["unidad"]), float(c["canonica"]), float(c["esperado"]))
        for c in casos["delta"]
        if c["dimension"] == "temperature"
    }
    assert ("degC", 10.0, 10.0) in deltas, "falta Δ10 K = 10 °C"
    assert ("degF", 10.0, 18.0) in deltas, "falta Δ10 K = 18 °F"


def _casi(a: tuple[Any, ...], b: tuple[Any, ...]) -> bool:
    return (
        a[0] == b[0]
        and a[1] == b[1]
        and math.isclose(a[2], b[2], abs_tol=1e-9)
        and math.isclose(a[3], b[3], rel_tol=1e-6, abs_tol=1e-9)
    )


# --------------------------------------------------------------------------- #
# El cruce: la misma unidad, el mismo número, clases distintas
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("unidad", "punto", "intervalo"),
    [("degC", -263.15, 10.0), ("degF", -441.67, 18.0), ("degR", 18.0, 18.0), ("K", 10.0, 10.0)],
)
def test_diez_kelvin_como_punto_y_como_delta(
    cat: Catalogo, unidad: str, punto: float, intervalo: float
) -> None:
    """El corazón de F1-20, unidad por unidad de temperatura.

    Se afirman los DOS valores, incluido el del punto. Afirmar solo el intervalo
    dejaría pasar una implementación que devolviera 10,0 siempre —correcta para el
    delta y catastrófica para el cursor—, y este subsistema tiene que estar bien en
    las dos direcciones.

    Rankine y kelvin están en la lista porque su `b` es cero: ahí punto e
    intervalo COINCIDEN, y esa coincidencia también es una propiedad que puede
    romperse.
    """
    temp = cat.dimension("temperature")
    como_punto = desde_canonica(10.0, dimension=temp, unidad=unidad, clase=Clase.PUNTO)
    como_delta = desde_canonica(10.0, dimension=temp, unidad=unidad, clase=Clase.INTERVALO)
    assert como_punto == pytest.approx(punto, abs=1e-9)
    assert como_delta == pytest.approx(intervalo, abs=1e-9)


def test_la_diferencia_entre_punto_y_delta_es_exactamente_b(cat: Catalogo) -> None:
    """La propiedad general, sobre TODAS las unidades afines del catálogo.

    `punto(x) − intervalo(x) = b` para cualquier x. Es más fuerte que cualquier
    caso concreto: no hay unidad, presente o futura, que pueda escapar.
    """
    comprobadas = 0
    for dim in cat.dimensiones.values():
        if not dim.convertible:
            continue
        for uni in dim.unidades.values():
            conv = uni.conversion
            if not isinstance(conv, Afin):
                continue
            for x in (0.0, 1.0, -7.5, 1234.5):
                p = conv.desde_canonica(x, Clase.PUNTO)
                i = conv.desde_canonica(x, Clase.INTERVALO)
                assert p - i == pytest.approx(conv.b, abs=1e-9), (
                    f"{dim.id}.{uni.id} con x={x}: punto−intervalo={p - i}, b={conv.b}"
                )
            comprobadas += 1
    assert comprobadas > 40, (
        f"solo se han comprobado {comprobadas} unidades; ¿se cargó el catálogo?"
    )


def test_solo_la_temperatura_desplaza_el_origen(cat: Catalogo) -> None:
    """Delimita el alcance del problema, y es una afirmación auditable.

    Si algún día otra dimensión estrena una unidad con `b != 0` —presión en psig
    cableada como unidad, por ejemplo, en vez de como cambio de origen—, esta
    prueba lo saca a la luz en vez de dejar que herede una trampa nueva.
    """
    con_desplazamiento = {
        (dim.id, uni.id)
        for dim in cat.dimensiones.values()
        for uni in dim.unidades.values()
        if isinstance(uni.conversion, Afin) and uni.conversion.desplaza_origen
    }
    assert con_desplazamiento == {("temperature", "degC"), ("temperature", "degF")}


# --------------------------------------------------------------------------- #
# Propiedades algebraicas, sobre todo el catálogo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("clase", [Clase.PUNTO, Clase.INTERVALO, Clase.TASA, Clase.VARIANZA])
def test_ida_y_vuelta_en_todo_el_catalogo(cat: Catalogo, clase: Clase) -> None:
    """§6.12: canónica → mostrada → canónica sin pérdida apreciable.

    Es lo que sostiene el editor de umbrales: el usuario escribe en la unidad
    activa, se guarda en canónica y al volver a mostrarlo tiene que salir lo que
    escribió. Si esto se rompe, cada apertura del diálogo desplaza el límite un
    poco más.
    """
    for dim in cat.dimensiones.values():
        if not dim.convertible:
            continue
        for uni in dim.unidades.values():
            if isinstance(uni.conversion, Reciproca) and clase is not Clase.PUNTO:
                continue  # no es lineal: se rechaza a propósito, ver [[rechazo]]
            for x in (0.5, 1.0, 273.15, 6715.0):
                mostrado = desde_canonica(x, dimension=dim, unidad=uni.id, clase=clase)
                vuelta = a_canonica(mostrado, dimension=dim, unidad=uni.id, clase=clase)
                assert vuelta == pytest.approx(x, rel=1e-12, abs=1e-12), (
                    f"{dim.id}.{uni.id} clase {clase.value} con x={x}: vuelve {vuelta}"
                )


def test_el_delta_es_aditivo_y_el_punto_no(cat: Catalogo) -> None:
    """La razón física de que existan las dos clases.

    `punto(x₂) − punto(x₁) = intervalo(x₂ − x₁)` es la identidad que hace correcto
    al doble cursor. Se comprueba en °F, donde falla de las dos maneras posibles si
    la clase se ignora.
    """
    temp = cat.dimension("temperature")
    x1, x2 = 293.15, 303.15  # 20 °C y 30 °C
    p1 = desde_canonica(x1, dimension=temp, unidad="degF", clase=Clase.PUNTO)
    p2 = desde_canonica(x2, dimension=temp, unidad="degF", clase=Clase.PUNTO)
    delta = desde_canonica(x2 - x1, dimension=temp, unidad="degF", clase=Clase.INTERVALO)
    assert p2 - p1 == pytest.approx(delta, abs=1e-9)
    assert delta == pytest.approx(18.0, abs=1e-9)
    # Y el punto NO es aditivo: es justo lo que distingue las dos clases.
    assert desde_canonica(
        x2 - x1, dimension=temp, unidad="degF", clase=Clase.PUNTO
    ) != pytest.approx(delta, abs=1.0)


def test_la_varianza_es_el_cuadrado_del_intervalo(cat: Catalogo) -> None:
    """Coherencia entre las dos clases cuadráticas.

    `√varianza(σ²) = intervalo(σ)`. Si la varianza usara `a` en vez de `a²`, la
    desviación típica mostrada saldría por la raíz de 1,8 en Fahrenheit: un 34 %
    de error, del tamaño justo para parecer plausible.
    """
    temp = cat.dimension("temperature")
    sigma_canonica = 2.0
    var_mostrada = desde_canonica(
        sigma_canonica**2, dimension=temp, unidad="degF", clase=Clase.VARIANZA
    )
    sigma_mostrada = desde_canonica(
        sigma_canonica, dimension=temp, unidad="degF", clase=Clase.INTERVALO
    )
    assert math.sqrt(var_mostrada) == pytest.approx(sigma_mostrada, abs=1e-9)
    assert sigma_mostrada == pytest.approx(3.6, abs=1e-9)


def test_el_rms_es_homogeneo_bajo_escala_pero_no_bajo_desplazamiento(cat: Catalogo) -> None:
    """La justificación algebraica de por qué un RMS es SIEMPRE `Clase.INTERVALO`
    (F4-10), nunca `Clase.PUNTO` -- ver «POR QUÉ EL RMS ES INTERVALO Y NO PUNTO»
    en la cabecera de `unidades.py` para la derivación completa.

    Serie sintética con media != 0 (7 muestras, RMS y media a mano, sin NumPy:
    es código de prueba sobre un puñado de números, no el camino caliente que
    prohíbe ADR-009). Se comprueban las dos propiedades que sostienen la
    decisión:

    1. **Homogeneidad bajo escala pura**: `RMS(k·X) = |k|·RMS(X)` para
       cualquier `k` (incluido uno negativo), exacta -- es un hecho del
       operador RMS en sí, no de este catálogo.
    2. **Para toda unidad REAL del catálogo, `Clase.INTERVALO` reproduce esa
       homogeneidad exactamente.** Ninguna unidad de `data/units.toml` tiene
       `a` negativo (comprobado sobre las mismas unidades que recorre
       `test_la_diferencia_entre_punto_y_delta_es_exactamente_b`), así que
       `a·RMS(X)` y `|a|·RMS(X)` coinciden siempre en la práctica -- si algún
       día se diera de alta una unidad con `a < 0`, esta prueba seguiría
       demostrando la propiedad 1 sobre el operador matemático, aunque
       `Afin.desde_canonica(rms, INTERVALO)` perdería el signo del valor
       absoluto en ESE caso hipotético, algo que no le corresponde arreglar a
       esta tarea porque hoy no existe ninguna unidad así.
    3. **No homogeneidad bajo desplazamiento**: `RMS(a·X + b) != a·RMS(X) + b`
       en general. Es la prueba de que `Clase.PUNTO` -- que sumaría `b` -- no
       reconstruye el RMS que se obtendría convirtiendo la serie entera y
       volviendo a calcular el RMS ahí: esa reconstrucción exacta necesitaría
       la media de la serie, que un RMS no lleva consigo.
    """
    xs = [10.0, 12.0, 9.0, 15.0, 11.0, 8.0, 13.0]  # media 11.14..., no cero
    rms = math.sqrt(sum(x * x for x in xs) / len(xs))

    # Propiedad 1: el operador RMS en sí es homogéneo bajo escala, con signo
    # incluido -- esto no depende del catálogo, es aritmética pura.
    for k in (2.0, 0.5, -3.0):
        escalados = [k * x for x in xs]
        rms_escalado = math.sqrt(sum(x * x for x in escalados) / len(escalados))
        assert rms_escalado == pytest.approx(abs(k) * rms, rel=1e-12), (
            f"RMS({k}·X) debería ser |k|·RMS(X)={abs(k) * rms}, salió {rms_escalado}"
        )

    # Propiedad 2: sobre toda unidad REAL y afín del catálogo (todas con
    # `a > 0`: `docs/06` no modela unidades de escala negativa), la conversión
    # de un RMS con `Clase.INTERVALO` coincide exactamente con el RMS que daría
    # convertir la serie entera y volver a calcularlo -- sin recorrer ninguna
    # muestra, un solo número basta.
    comprobadas = 0
    for dim in cat.dimensiones.values():
        if not dim.convertible:
            continue
        for uni in dim.unidades.values():
            if not isinstance(uni.conversion, Afin):
                continue
            a = uni.conversion.a
            assert a > 0, f"{dim.id}.{uni.id}: unidad con a<=0, la propiedad 2 no cubre este caso"
            rms_de_la_serie_escalada = math.sqrt(sum((a * x) ** 2 for x in xs) / len(xs))
            convertido = uni.conversion.desde_canonica(rms, Clase.INTERVALO)
            assert convertido == pytest.approx(rms_de_la_serie_escalada, rel=1e-9), (
                f"{dim.id}.{uni.id}: RMS convertido no coincide con el de la serie escalada"
            )
            comprobadas += 1
    assert comprobadas > 40, (
        f"solo se han comprobado {comprobadas} unidades; ¿se cargó el catálogo?"
    )

    # Propiedad 3: con un desplazamiento de origen real (K -> °F, a=1.8,
    # b=-459.67), el RMS de la serie CONVERTIDA no es `a·rms` ni `a·rms + b`:
    # ninguna de las dos clases lo reconstruye, y `Clase.PUNTO` en particular
    # es la trampa que este test existe para que nadie vuelva a cometer.
    temp = cat.dimension("temperature")
    conv_f = temp.unidad("degF").conversion
    assert isinstance(conv_f, Afin)
    convertidos = [conv_f.a * x + conv_f.b for x in xs]
    rms_de_la_serie_convertida = math.sqrt(sum(x * x for x in convertidos) / len(convertidos))

    rms_como_punto = conv_f.desde_canonica(rms, Clase.PUNTO)  # LA TRAMPA: suma b
    rms_como_intervalo = conv_f.desde_canonica(rms, Clase.INTERVALO)  # LO CORRECTO

    assert rms_como_punto != pytest.approx(rms_de_la_serie_convertida, rel=1e-6), (
        "si `Clase.PUNTO` reconstruyera el RMS real aquí sería casualidad: la "
        "derivación algebraica dice que solo coincide cuando la media de la "
        "serie es cero, y aquí no lo es"
    )
    # `Clase.INTERVALO` tampoco pretende reconstruir el RMS de la serie
    # convertida -- eso exigiría la media, que el RMS no lleva consigo -- pero
    # es la única conversión LINEAL que este motor puede dar con la
    # información que tiene, y es la que declara `docs/06` §6.5.
    assert rms_como_intervalo == pytest.approx(conv_f.a * rms, rel=1e-12)
    assert rms_como_intervalo != pytest.approx(rms_de_la_serie_convertida, rel=1e-6)


def test_la_tasa_no_desplaza_el_origen(cat: Catalogo) -> None:
    """Una derivada de temperatura se mide en °C/s, y 10 K/s son 10 °C/s.

    `TASA` existe aparte de `INTERVALO` porque su denominador puede tener su propia
    unidad (§6.5), pero en el numerador se comporta igual: sin `b`.
    """
    temp = cat.dimension("temperature")
    for unidad, esperado in (("degC", 10.0), ("degF", 18.0)):
        assert desde_canonica(
            10.0, dimension=temp, unidad=unidad, clase=Clase.TASA
        ) == pytest.approx(esperado, abs=1e-9)


def test_el_intervalo_es_lineal(cat: Catalogo) -> None:
    """`intervalo(k·x) = k·intervalo(x)`, que es lo que un punto NO cumple."""
    temp = cat.dimension("temperature")
    base = desde_canonica(1.0, dimension=temp, unidad="degF", clase=Clase.INTERVALO)
    for k in (0.0, 2.0, -3.0, 100.0):
        assert desde_canonica(
            k, dimension=temp, unidad="degF", clase=Clase.INTERVALO
        ) == pytest.approx(k * base, abs=1e-9)


def test_un_delta_de_cero_es_cero_en_toda_unidad(cat: Catalogo) -> None:
    """El caso de borde que delata el `+ b` de un golpe de vista.

    Un Δ de 0 tiene que ser 0 en cualquier unidad. Con el desplazamiento aplicado
    por error, en °C daría −273,15, que es el síntoma más reconocible del defecto.
    """
    for dim in cat.dimensiones.values():
        if not dim.convertible:
            continue
        for uni in dim.unidades.values():
            if isinstance(uni.conversion, Reciproca):
                continue  # 1/0: no está definido y se rechaza para intervalos
            obtenido = desde_canonica(0.0, dimension=dim, unidad=uni.id, clase=Clase.INTERVALO)
            assert obtenido == pytest.approx(0.0, abs=1e-12), f"{dim.id}.{uni.id} → {obtenido}"


# --------------------------------------------------------------------------- #
# La clase es obligatoria
# --------------------------------------------------------------------------- #
def test_no_hay_clase_por_omision() -> None:
    """La decisión de diseño que hace improbable el defecto, no solo detectable.

    `Clase` no tiene valor por omisión en ninguna firma: quien convierte está
    obligado a declarar si tiene un punto o una diferencia. Se comprueba sobre la
    firma real, porque un valor por omisión añadido «por comodidad» es exactamente
    cómo volvería el defecto.
    """
    import inspect

    for funcion in (desde_canonica, a_canonica):
        p = inspect.signature(funcion).parameters["clase"]
        assert p.default is inspect.Parameter.empty, (
            f"{funcion.__name__} tiene un valor por omisión para `clase`: "
            "eso hace que olvidarla no dé error"
        )
        assert p.kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{funcion.__name__}: `clase` debe ser solo por nombre, para que no se "
            "pueda pasar por posición sin querer"
        )


def test_la_referencia_de_presion_no_se_aplica_a_los_intervalos(cat: Catalogo) -> None:
    """§6.6, comprobado también en la vuelta.

    La ida y la vuelta tienen que tratar la referencia igual; si solo una de las
    dos la aplicara a los intervalos, un umbral editado en relativo se guardaría
    desplazado 101,325 kPa y dispararía donde no debe.
    """
    presion = cat.dimension("pressure")
    ref = 101.325
    for clase, esperado_ida in ((Clase.PUNTO, (227.2 - ref) * 0.01), (Clase.INTERVALO, 0.5)):
        x = 227.2 if clase is Clase.PUNTO else 50.0
        ida = desde_canonica(x, dimension=presion, unidad="bar", clase=clase, referencia_kpa=ref)
        assert ida == pytest.approx(esperado_ida, abs=1e-9)
        vuelta = a_canonica(ida, dimension=presion, unidad="bar", clase=clase, referencia_kpa=ref)
        assert vuelta == pytest.approx(x, abs=1e-9), f"clase {clase.value}: vuelve {vuelta}"


def test_la_etiqueta_dice_si_la_presion_es_absoluta_o_relativa(cat: Catalogo) -> None:
    """«2 bar» sin más es la fuente de error más común al comparar herramientas."""
    from dlv_core.unidades import etiqueta_de

    presion = cat.dimension("pressure")
    assert etiqueta_de(presion, "bar", relativa=False) == "bar (abs)"
    assert etiqueta_de(presion, "bar", relativa=True) == "bar (rel)"
    # Y las dimensiones que no admiten referencia no se marcan.
    assert "abs" not in etiqueta_de(cat.dimension("temperature"), "degC")


# --------------------------------------------------------------------------- #
# Coherencia de la propia tabla
# --------------------------------------------------------------------------- #
def test_la_tabla_esta_bien_formada(cat: Catalogo, casos: dict[str, Any]) -> None:
    """Cada fila cita una dimensión y una unidad que existen, y explica su origen.

    `origen` no es documentación decorativa: es lo que permite que la puerta G1
    signifique algo. Un número esperado sin procedencia no se puede revisar.
    """
    assert casos["meta"]["version"] == 1
    for seccion in ("punto", "delta", "varianza"):
        for c in casos[seccion]:
            dim: Dimension = cat.dimension(str(c["dimension"]))
            dim.unidad(str(c["unidad"]))  # lanza si no pertenece a la dimensión
            assert str(c["origen"]).strip(), f"{seccion}/{c['caso']}: falta `origen`"
            assert float(c["tolerancia"]) >= 0.0
    for c in casos["referencia"]:
        cat.dimension("pressure").unidad(str(c["unidad"]))
        assert str(c["clase"]) in CLASES_POR_NOMBRE
    for c in casos["rechazo"]:
        assert str(c["motivo"]).strip(), f"rechazo/{c['caso']}: falta `motivo`"


def test_la_tabla_no_esta_vacia_ni_es_testimonial() -> None:
    """Una tabla de tres filas cumpliría todas las pruebas anteriores.

    El número exacto no importa; el suelo sí, porque una tabla que se vacía por un
    error de edición pasaría el resto de esta suite en silencio.
    """
    assert len(PUNTOS) >= 20, f"solo {len(PUNTOS)} casos punto"
    assert len(DELTAS) >= 5, f"solo {len(DELTAS)} casos delta"
    assert len(REFERENCIAS) >= 4, f"solo {len(REFERENCIAS)} casos de referencia"
    assert len(RECHAZOS) >= 4, f"solo {len(RECHAZOS)} casos de rechazo"


def test_todas_las_dimensiones_convertibles_tienen_algun_caso(
    cat: Catalogo, casos: dict[str, Any]
) -> None:
    """Informativo y con dientes: enumera lo que la tabla aún no cubre.

    No exige cobertura total —hay dimensiones que nadie va a mirar nunca— pero sí
    que las que un tuner usa a diario estén todas.
    """
    cubiertas = {str(c["dimension"]) for s in ("punto", "delta", "varianza") for c in casos[s]}
    imprescindibles = {
        "temperature",
        "pressure",
        "mixture_ratio",
        "ratio",
        "angular_speed",
        "speed",
        "angle",
        "voltage",
    }
    faltan = imprescindibles - cubiertas
    assert not faltan, f"dimensiones de uso diario sin ningún caso conocido: {sorted(faltan)}"
