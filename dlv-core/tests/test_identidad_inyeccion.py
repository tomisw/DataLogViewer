"""La identidad del inyector fija tres factores de escala (tarea F1-47).

Especificación: `docs/01-formato-log.md` §1.3 y `data/formats/haltech_nsp.toml`.

QUÉ PROTEGE ESTA SUITE
======================
Tres tipos del descriptor de Haltech —`Flow`, `InjFuelVolume` y `MassPerCyl`—
estuvieron marcados `confianza = "inferred"` porque su factor se había deducido
cruzándolos entre ellos. Dos de los tres estaban desviados un factor 10, y el
cruce no lo veía: los dos en el mismo sentido, así que el cociente cuadraba.

La propia nota del descriptor lo avisaba —«los dos se apoyan mutuamente, ninguno
se prueba solo»—, y el 7,4 % que sobraba se despachó como «atribuible al tiempo
muerto del inyector». Lo era, literalmente: el log publica el tiempo muerto en
`Injection Stage 1 Dead Time`, y restarlo cierra la identidad al quinto dígito y
deja el factor 10 a la vista.

LA IDENTIDAD
============
    caudal del inyector x (tiempo de apertura - tiempo muerto) = volumen inyectado

Los cuatro términos están en el log del propietario, así que no hay nada que
suponer. Lo que hace que la identidad fije la escala ABSOLUTA y no solo la
relativa es el caudal: `Injection Stage 1 Flow Rate` es constante en las 2 636
filas del AutoLog, o sea que no es una medida sino el inyector configurado en la
ECU, y el propietario declara Bosch EV14 de 640 cc/min. Eso ancla la unidad del
canal en cc/min y con ella toda la cadena.

Y LA COMPROBACIÓN QUE DECIDE
============================
La densidad del combustible que se deduce de dividir `Fuel Mass Per Cylinder`
entre el volumen inyectado. Con los factores corregidos sale 0,741 g/mL, que es
gasolina; con los anteriores salía 7,412 g/mL, que es la densidad del acero.

Esa comprobación es la que convierte esto en una prueba y no en un ajuste. Un
factor de escala equivocado no da un log ilegible: da valores plausibles. Pero
*derivar una densidad* de dos canales independientes sí produce un número que se
puede confrontar con el mundo, y 7,4 g/mL no es un combustible.

POR QUÉ SOBRE EL LOG REAL Y NO SOBRE UN FIXTURE
===============================================
Porque lo que se comprueba es una afirmación sobre el formato de Haltech, no
sobre el código que lo lee. Un fixture con los números escritos a mano probaría
que la aritmética de la prueba es correcta, que no es lo que está en duda.

Solo biblioteca estándar.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

import pytest

from dlv_core.formatos.nativo import cargar_descriptor, parsear_cabecera

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR = RAIZ / "data" / "formats" / "haltech_nsp.toml"
AUTOLOG = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"

#: Los cuatro canales de la identidad, más la masa para la densidad.
CANALES = (
    "Injection Stage 1 Flow Rate",
    "Injection Stage 1 Dead Time",
    "Injector 1 On Time",
    "Injector 1 Volume",
    "Fuel Mass Per Cylinder",
    "Injector 1 Duty Cycle",
)

#: Centinelas de «sin dato» de la ECU (docs/01 §1.13). Un centinela contado como
#: medida convierte cualquier estadístico en ruido.
CENTINELAS = frozenset({-2147483639, -2147483648, 2147483647})

#: Por debajo de este ciclo de trabajo los canales son enteros pequeños y la
#: cuantización domina el cociente. No es un filtro para que salga bien: la
#: mediana sobre TODAS las filas también da 1e-08 (0,009998), solo que con más
#: dispersión en las colas.
DUTY_MINIMO = 0.20

#: Gasolina a temperatura ambiente. El rango es ancho a propósito: la prueba no
#: mide la densidad, comprueba que el número que sale es un combustible líquido y
#: no un múltiplo de diez de uno.
DENSIDAD_GASOLINA = (0.70, 0.80)


@pytest.fixture(scope="module")
def filas() -> list[dict[str, int]]:
    """Los crudos de los seis canales, fila a fila, sin convertir.

    Se trabaja en crudo a propósito: la prueba comprueba los FACTORES del
    descriptor, así que aplicarlos antes de comprobarlos daría por bueno lo que
    está en duda. Los factores se leen aparte y se usan explícitamente.
    """
    datos = AUTOLOG.read_bytes()
    with DESCRIPTOR.open("rb") as fh:
        desc = cargar_descriptor(fh)
    cab = parsear_cabecera(datos, desc)
    columna = {c.nombre: i + 1 for i, c in enumerate(cab.canales) if c.nombre in CANALES}
    assert set(columna) == set(CANALES), f"faltan canales: {set(CANALES) - set(columna)}"

    salida: list[dict[str, int]] = []
    ultimo: dict[str, int] = {}
    texto = datos[cab.offset_datos :].decode("utf-8", "replace")
    for fila in csv.reader(texto.splitlines()):
        # Muestreo disperso: una fila trae solo los canales que tocan a su tasa,
        # así que se arrastra el último valor conocido de cada uno.
        for nombre, j in columna.items():
            if j < len(fila) and fila[j].strip():
                try:
                    valor = int(fila[j])
                except ValueError:
                    continue
                if valor not in CENTINELAS:
                    ultimo[nombre] = valor
        if len(ultimo) == len(CANALES):
            salida.append(dict(ultimo))
    assert len(salida) > 2000, f"solo {len(salida)} filas completas; el log real tiene ~2 600"
    return salida


@pytest.fixture(scope="module")
def factores() -> dict[str, float]:
    with DESCRIPTOR.open("rb") as fh:
        desc = cargar_descriptor(fh)
    return {t: float(desc.tipos[t]["a_canonica"]) for t in ("Flow", "InjFuelVolume", "MassPerCyl")}


def _de_carga(filas: list[dict[str, int]], factores: dict[str, float]) -> list[dict[str, int]]:
    """Las filas con carga apreciable, donde los enteros son grandes."""
    duty = 0.001  # `Percentage`, y su factor lo comprueba `test_haltech_cabecera`
    return [
        f
        for f in filas
        if f["Injector 1 Duty Cycle"] * duty >= DUTY_MINIMO
        and f["Injector 1 On Time"] > f["Injection Stage 1 Dead Time"]
        and f["Injector 1 Volume"] > 0
        and f["Fuel Mass Per Cylinder"] > 0
    ]


def test_el_caudal_configurado_es_constante_y_es_el_inyector_del_coche(
    filas: list[dict[str, int]], factores: dict[str, float]
) -> None:
    """`Injection Stage 1 Flow Rate` no mide: declara el inyector configurado.

    Es lo que ancla toda la cadena. Si algún día un log trae este canal variando,
    la premisa deja de valer y hay que rehacer el razonamiento, no ajustar el
    número: de ahí que la constancia sea una aserción y no un comentario.
    """
    distintos = {f["Injection Stage 1 Flow Rate"] for f in filas}
    assert len(distintos) == 1, f"el caudal varía en el log: {sorted(distintos)[:10]}"

    crudo = distintos.pop()
    # `volume_flow` es canónica en L/h; el inyector se habla en cc/min.
    cc_min = crudo * factores["Flow"] * 1000.0 / 60.0
    assert cc_min == pytest.approx(crudo, rel=1e-9), (
        "con el factor correcto el crudo ESTÁ en cc/min, así que el número no cambia"
    )
    # Bosch EV14 de 640 cc/min declarados por el propietario. La holgura del 10 %
    # cubre que un tuner introduzca el caudal medido en vez del nominal (aquí,
    # 620), y es dos órdenes de magnitud más estrecha que el factor 10 en juego.
    assert 576.0 <= cc_min <= 704.0, (
        f"el inyector configurado sale {cc_min:.0f} cc/min y el coche lleva 640 cc/min. "
        "Con el factor anterior (0,006) salían 62 cc/min, diez veces menos que "
        "cualquier inyector moderno"
    )


def test_la_identidad_del_inyector_es_exacta(
    filas: list[dict[str, int]], factores: dict[str, float]
) -> None:
    """caudal x (apertura - tiempo muerto) = volumen, al quinto dígito.

    No es «cuadra dentro de una tolerancia»: es la misma cuenta. La dispersión
    sobre las filas de carga tiene que ser prácticamente nula, y eso es lo que
    distingue una identidad de una coincidencia afortunada.
    """
    de_carga = _de_carga(filas, factores)
    assert len(de_carga) > 500, f"solo {len(de_carga)} filas de carga"

    us = 1e-6  # `Time_us`, factor comprobado aparte
    razones = []
    for f in de_carga:
        efectivo_s = (f["Injector 1 On Time"] - f["Injection Stage 1 Dead Time"]) * us
        # L/h -> L/s -> L, y de ahí a las cuentas del canal de volumen.
        litros = f["Injection Stage 1 Flow Rate"] * factores["Flow"] / 3600.0 * efectivo_s
        razones.append(litros / (f["Injector 1 Volume"] * factores["InjFuelVolume"]))

    mediana = statistics.median(razones)
    assert mediana == pytest.approx(1.0, rel=0.01), (
        f"la identidad falla por un factor {mediana:.4g}. Si es 10 o 0,1, uno de los "
        "dos factores (Flow, InjFuelVolume) se ha desviado un orden de magnitud"
    )
    assert statistics.stdev(razones) < 0.01, (
        f"dispersión {statistics.stdev(razones):.4g}: la identidad ya no es exacta, "
        "así que la premisa (el caudal declara el inyector) ha dejado de valer"
    )


def test_la_densidad_del_combustible_es_la_de_un_combustible(
    filas: list[dict[str, int]], factores: dict[str, float]
) -> None:
    """La comprobación que decide, y la que fija `MassPerCyl` en absoluto.

    Masa entre volumen es una densidad, y una densidad se puede confrontar con el
    mundo. Con los factores anteriores salían 7,412 g/mL —acero— y nada lo
    señalaba, porque nadie mira la densidad de un combustible que el programa no
    muestra. Es el ejemplo de libro de por qué un factor de escala equivocado es
    un fallo silencioso: los canales de volumen se veían diez veces pequeños y
    ninguna cifra parecía rara.
    """
    de_carga = _de_carga(filas, factores)
    densidades = [
        # mg -> g, entre litros -> mL.
        (f["Fuel Mass Per Cylinder"] * factores["MassPerCyl"] * 1e-3)
        / (f["Injector 1 Volume"] * factores["InjFuelVolume"] * 1e3)
        for f in de_carga
    ]
    mediana = statistics.median(densidades)
    bajo, alto = DENSIDAD_GASOLINA
    assert bajo <= mediana <= alto, (
        f"la densidad implícita del combustible es {mediana:.4g} g/mL, y la gasolina "
        f"está entre {bajo} y {alto}. Un múltiplo de diez de ese valor significa que "
        "MassPerCyl o InjFuelVolume se han desviado un orden de magnitud"
    )
    assert statistics.stdev(densidades) < 0.05, (
        f"dispersión {statistics.stdev(densidades):.4g} g/mL: la densidad de un "
        "combustible no varía a lo largo de un log"
    )


def test_los_tres_tipos_estan_confirmados_en_el_descriptor() -> None:
    """Lo que esta suite demuestra tiene que estar dicho en el dato.

    `confianza` gobierna si un canal se muestra convertido o en crudo (R1), así
    que dejarlo en `inferred` con la prueba en verde sería tan incoherente como lo
    contrario. Y al revés: si alguien pone `confirmed` sin evidencia, esta prueba
    no lo detecta — para eso está la puerta G1.
    """
    with DESCRIPTOR.open("rb") as fh:
        desc = cargar_descriptor(fh)
    for tipo in ("Flow", "InjFuelVolume", "MassPerCyl"):
        entrada = desc.tipos[tipo]
        assert entrada["confianza"] == "confirmed", tipo
        assert "F1-47" in str(entrada.get("evidencia", "")), (
            f"{tipo} está confirmado pero su evidencia no cita la tarea que lo confirmó"
        )
