"""Los tipos que F1-38 resolvió, y la contabilidad del descriptor.

Especificación: `data/formats/haltech_nsp.toml`, sección `[resumen]` y los tipos
`MassOverTime`, `AngularVelocity`, `FuelVolume` y `PulsesPerLongDistance`.

QUÉ PROTEGE ESTA SUITE
======================
F1-38 tenía que confirmar los tipos marcados `confianza = "unknown"` con análisis
de datos. De los siete que quedaban cerró dos, y lo que hizo posible cerrarlos no
fue una idea nueva: fue medir sobre las 2 636 filas del AutoLog en vez de sobre
la fila de referencia. Dos de las cinco notas que quedan abiertas afirmaban que
su canal valía cero o era constante, y las dos eran falsas por eso mismo.

Cada prueba de aquí fija una de esas afirmaciones contra el log del propietario,
que es el único sitio donde se pueden comprobar. Un fixture con números escritos
a mano probaría la aritmética de la prueba, que no es lo que está en duda.

LO QUE HACE FALSABLE CADA FACTOR
================================
`MassOverTime` — el cociente de los dos canales de caudal de combustible, uno en
volumen (tipo `Flow`, confirmado en F1-47) y otro en masa. Si son la misma
magnitud el cociente es la densidad del combustible y tiene que ser constante:
lo es al 0,18 %. Y el factor que sale de ahí tiene que devolver una densidad de
gasolina, no un múltiplo de diez de una.

`AngularVelocity` — la coincidencia con la parte entera de `RPM x 0,06`. El punto
fino es distinguir un truncamiento de un factor equivocado, y lo que los separa
es la FORMA del sesgo: constante en el primer caso, proporcional al valor en el
segundo. Hay una prueba para eso sola, porque el ajuste por mínimos cuadrados
sugiere 0,059890 y escribir ese número habría sido el error.

Y una prueba que no mide ningún factor pero evita el fallo más caro de todos: que
el `[resumen]` deje de cuadrar con la suma de los tipos. Ya pasó —F1-47 movió la
confianza de 18 canales y no movió el recuento, y estuvo así hasta F1-38—, y un
recuento equivocado es lo que hace que nadie se fíe del resto del fichero.

Solo biblioteca estándar.
"""

from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

import pytest

from dlv_core.formatos.nativo import cargar_descriptor, parsear_cabecera

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR = RAIZ / "data" / "formats" / "haltech_nsp.toml"
AUTOLOG = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"

CANALES = (
    "RPM",
    "Angular Velocity",
    "Fuel Mass Flow",
    "Fuel Flow Estimated",
    "Fuel Mass Per Cylinder",
    "Calculated Air Mass Per Cylinder",
    "Mass Air Flow",
    "Mass Air Flow 1",
    "Mass Air Flow 2",
    "Vehicle Speed",
    "Vehicle Speed 0 Calculated Rate",
    "Transient Throttle Fuel Peak Synchronous Output",
)

#: Centinelas de «sin dato» de la ECU (docs/01 §1.13).
CENTINELAS = frozenset({-2147483639, -2147483648, 2147483647})

#: RB26DETT, seis cilindros. Dato del motor del propietario, no del formato: por
#: eso vive aquí y no en el descriptor, igual que en `test_identidad_inyeccion`.
CILINDROS = 6

#: Gasolina a temperatura ambiente, rango ancho a propósito: la prueba no mide la
#: densidad, comprueba que el número que sale es un combustible y no un metal.
DENSIDAD_GASOLINA = (0.70, 0.80)


@pytest.fixture(scope="module")
def filas() -> list[dict[str, int]]:
    """Los crudos, fila a fila, sin convertir.

    En crudo a propósito: lo que se comprueba son los factores del descriptor, así
    que aplicarlos antes daría por bueno lo que está en duda.
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
    assert len(salida) > 2000, f"solo {len(salida)} filas; el log real tiene ~2 600"
    return salida


@pytest.fixture(scope="module")
def descriptor() -> dict[str, dict[str, object]]:
    with DESCRIPTOR.open("rb") as fh:
        return dict(cargar_descriptor(fh).tipos)


def _cv(valores: list[float]) -> float:
    """Coeficiente de variación en tanto por ciento."""
    return statistics.pstdev(valores) / abs(statistics.fmean(valores)) * 100.0


# --------------------------------------------------------------------------- #
#  La contabilidad. No mide física; evita que el fichero deje de ser auditable.
# --------------------------------------------------------------------------- #


def test_el_resumen_cuadra_con_la_suma_de_los_tipos() -> None:
    """El `[resumen]` tiene que ser la suma de los `canales` de cada tipo.

    Esta prueba existe porque ya falló: F1-47 pasó `Flow`, `InjFuelVolume` y
    `MassPerCyl` a confirmados —18 canales— y dejó el recuento como estaba, así
    que el fichero decía 422 confirmados y 36 inferidos donde la suma daba 440 y
    18. No lo detectó nadie hasta F1-38.

    Si esto se pone en rojo, lo que hay que corregir es el `[resumen]`, no la
    prueba: el recuento es un resumen de los tipos, no una cifra independiente.
    """
    import tomllib

    with DESCRIPTOR.open("rb") as fh:
        crudo = tomllib.load(fh)
    tipos = crudo["tipos"]
    resumen = crudo["resumen"]

    esperado = {
        clave: sum(t.get("canales", 0) for t in tipos.values() if t.get("confianza") == conf)
        for clave, conf in (
            ("canales_confirmados", "confirmed"),
            ("canales_inferidos", "inferred"),
            ("canales_desconocidos", "unknown"),
        )
    }
    for clave, valor in esperado.items():
        assert resumen[clave] == valor, (
            f"{clave}: el resumen dice {resumen[clave]}, la suma da {valor}"
        )

    assert sum(esperado.values()) == resumen["canales_totales"]
    assert sum(t.get("canales", 0) for t in tipos.values()) == resumen["canales_totales"]

    por_confianza = {
        ("confirmados", "confirmed"),
        ("inferidos", "inferred"),
        ("desconocidos", "unknown"),
    }
    for clave, conf in por_confianza:
        cuenta = sum(1 for t in tipos.values() if t.get("confianza") == conf)
        assert resumen[clave] == cuenta, f"{clave}: dice {resumen[clave]}, hay {cuenta}"
    assert len(tipos) == resumen["tipos_totales"]


def test_los_dos_tipos_que_cerro_f1_38_estan_confirmados(
    descriptor: dict[str, dict[str, object]],
) -> None:
    """Con su dimensión y su factor, que es lo que la tarea tenía que entregar."""
    assert descriptor["MassOverTime"]["confianza"] == "confirmed"
    assert descriptor["MassOverTime"]["dimension"] == "mass_flow"
    assert descriptor["MassOverTime"]["a_canonica"] == pytest.approx(0.036)

    assert descriptor["AngularVelocity"]["confianza"] == "confirmed"
    assert descriptor["AngularVelocity"]["dimension"] == "angular_speed"
    # 1 cuenta = 100 grados/s = 50/3 rpm.
    assert descriptor["AngularVelocity"]["a_canonica"] == pytest.approx(50.0 / 3.0)


# --------------------------------------------------------------------------- #
#  MassOverTime
# --------------------------------------------------------------------------- #


def test_los_dos_caudales_de_combustible_son_la_misma_magnitud(
    filas: list[dict[str, int]],
) -> None:
    """`Fuel Flow Estimated` / `Fuel Mass Flow` constante = son el mismo caudal.

    Es la identidad que fija el factor. Uno de los dos canales es de tipo `Flow`,
    ya confirmado, así que el cociente traslada esa escala a este tipo.
    """
    cociente = [
        f["Fuel Flow Estimated"] / f["Fuel Mass Flow"] for f in filas if f["Fuel Mass Flow"] > 100
    ]
    assert len(cociente) > 1000, f"solo {len(cociente)} filas con caudal apreciable"
    assert _cv(cociente) < 0.5, f"cv {_cv(cociente):.2f} %: el cociente no es constante"
    # El valor medido, para que un cambio de log lo delate en vez de pasar callado.
    assert statistics.median(cociente) == pytest.approx(0.8139, rel=0.01)


def test_el_factor_de_massovertime_da_una_densidad_de_combustible(
    filas: list[dict[str, int]],
    descriptor: dict[str, dict[str, object]],
) -> None:
    """La comprobación que decide, la misma que usó F1-47: el número que sale.

    Con el factor del descriptor y el 0,06 de `Flow`, el cociente de los dos
    canales es la densidad del combustible. Un factor diez veces mayor o menor no
    da un log ilegible: da una densidad que no es de ningún líquido.
    """
    factor = float(descriptor["MassOverTime"]["a_canonica"])  # type: ignore[arg-type]
    flow = float(descriptor["Flow"]["a_canonica"])  # type: ignore[arg-type]

    densidad = [
        (f["Fuel Mass Flow"] * factor) / (f["Fuel Flow Estimated"] * flow)
        for f in filas
        if f["Fuel Mass Flow"] > 500 and f["Fuel Flow Estimated"] > 0
    ]
    assert len(densidad) > 500
    media = statistics.fmean(densidad)
    bajo, alto = DENSIDAD_GASOLINA
    assert bajo < media < alto, f"densidad implícita {media:.4f} kg/L: no es un combustible"
    assert _cv(densidad) < 1.0

    # Y los dos vecinos de década, que es lo que el factor tiene que descartar.
    for equivocado in (factor / 10.0, factor * 10.0):
        implicada = media * equivocado / factor
        assert not (bajo < implicada < alto), f"el factor {equivocado} también daría un combustible"


def test_el_caudal_de_combustible_cuadra_con_la_aritmetica_del_motor(
    filas: list[dict[str, int]],
    descriptor: dict[str, dict[str, object]],
) -> None:
    """Tercera pata, sin usar la densidad ni el inyector.

    `Fuel Mass Per Cylinder` está confirmado en mg/cilindro, y un cuatro tiempos
    inyecta una vez por cilindro cada dos vueltas. Eso da el caudal másico sin
    tocar ningún canal de caudal, y lo que importa no es que el cociente valga
    algo bonito: es que sea PLANO en todo el rango de régimen. Un factor
    equivocado no da plano, da una recta con pendiente.
    """
    factor = float(descriptor["MassOverTime"]["a_canonica"])  # type: ignore[arg-type]

    def cociente_en(desde: int, hasta: int) -> float:
        v = [
            (f["Fuel Mass Per Cylinder"] * CILINDROS * (f["RPM"] / 2.0) * 60.0 / 1e6)
            / (f["Fuel Mass Flow"] * factor)
            for f in filas
            if desde <= f["RPM"] < hasta
            and f["Fuel Mass Flow"] > 0
            and f["Fuel Mass Per Cylinder"] > 0
        ]
        assert len(v) > 50, f"solo {len(v)} filas entre {desde} y {hasta} rpm"
        return statistics.median(v)

    bajo = cociente_en(400, 1000)
    alto = cociente_en(6000, 7100)
    # Las dos puntas del rango, a un factor 17 de régimen, dentro del 10 %.
    assert 0.9 < bajo < 1.1, f"a bajo régimen el cociente es {bajo:.4f}, no 1"
    assert 0.9 < alto < 1.1, f"a alto régimen el cociente es {alto:.4f}, no 1"
    assert abs(alto - bajo) < 0.10, f"deriva {abs(alto - bajo):.4f}: hay pendiente, no un factor"


def test_los_canales_de_mass_air_flow_no_los_arregla_ninguna_escala(
    filas: list[dict[str, int]],
) -> None:
    """El aviso del descriptor, convertido en prueba.

    Los cuatro canales de aire comparten tipo con `Fuel Mass Flow`, así que
    comparten factor. Contra el aire que la ECU calcula por cilindro su cociente
    CRECE con el caudal, y un factor de escala es una constante: multiplica igual
    a 400 rpm que a 7 000. Por eso el descriptor confirma la unidad y marca los
    cuatro canales como no fiables en valor absoluto.

    Si esta prueba se pone verde al revés —si el cociente sale plano— entonces el
    problema era de este coche y no del canal, y el aviso hay que reescribirlo.
    """

    def cociente_en(canal: str, desde: int, hasta: int) -> float:
        v = [
            (f["Calculated Air Mass Per Cylinder"] * CILINDROS * (f["RPM"] / 2.0) * 60.0 / 1e6)
            / f[canal]
            for f in filas
            if desde <= f["RPM"] < hasta
            and f[canal] > 0
            and f["Calculated Air Mass Per Cylinder"] > 0
        ]
        assert len(v) > 50, f"solo {len(v)} filas de {canal} entre {desde} y {hasta} rpm"
        return statistics.median(v)

    for canal in ("Mass Air Flow", "Mass Air Flow 1", "Mass Air Flow 2"):
        bajo = cociente_en(canal, 400, 1000)
        alto = cociente_en(canal, 6000, 7100)
        assert alto > 2.0 * bajo, (
            f"{canal}: cociente {bajo:.4f} a bajo régimen y {alto:.4f} a alto. "
            "Si ya no crece, el canal sí sigue al modelo y el aviso del descriptor sobra."
        )

    # Y siguen siendo medidas, no un valor por defecto: la hipótesis (a) que la
    # nota anterior no podía descartar.
    for canal in ("Mass Air Flow 1", "Mass Air Flow 2"):
        distintos = {f[canal] for f in filas}
        assert len(distintos) > 500, f"{canal}: solo {len(distintos)} valores distintos"


# --------------------------------------------------------------------------- #
#  AngularVelocity
# --------------------------------------------------------------------------- #


def test_angular_velocity_es_el_regimen_truncado(
    filas: list[dict[str, int]],
    descriptor: dict[str, dict[str, object]],
) -> None:
    """`Angular Velocity` no es una medida nueva: es `RPM` en otra unidad."""
    factor = float(descriptor["AngularVelocity"]["a_canonica"])  # type: ignore[arg-type]
    por_cuenta = 1.0 / factor  # 0,06 cuentas por rpm

    utiles = [f for f in filas if f["Angular Velocity"] > 0 and f["RPM"] > 400]
    assert len(utiles) > 2000

    exactas = sum(1 for f in utiles if f["Angular Velocity"] == math.floor(f["RPM"] * por_cuenta))
    assert exactas / len(utiles) > 0.95, (
        f"solo {exactas}/{len(utiles)} filas coinciden con la parte entera de RPM x {por_cuenta}"
    )
    # Ninguna fila se desvía más de una cuenta: las que fallan lo hacen por el
    # régimen interno de la ECU, que no es el entero que publica en `RPM`.
    peor = max(abs(f["Angular Velocity"] - f["RPM"] * por_cuenta) for f in utiles)
    assert peor <= 1.0, f"la peor fila se desvía {peor:.2f} cuentas"


def test_el_sesgo_de_angular_velocity_es_constante_y_no_proporcional(
    filas: list[dict[str, int]],
) -> None:
    """Lo que distingue un truncamiento de un factor equivocado.

    El ajuste por mínimos cuadrados de estas filas da 0,059890, un 0,18 % por
    debajo de 0,06, y escribir ese número era el error a evitar. Un factor
    equivocado deja un sesgo PROPORCIONAL al valor; un truncamiento deja media
    cuenta constante. Aquí el sesgo es el mismo a 400 rpm que a 7 000, así que es
    truncamiento y el factor es 0,06 exacto.
    """

    def sesgo_en(desde: int, hasta: int) -> float:
        v = [
            f["Angular Velocity"] - f["RPM"] * 0.06
            for f in filas
            if desde <= f["RPM"] < hasta and f["Angular Velocity"] > 0
        ]
        assert len(v) > 50, f"solo {len(v)} filas entre {desde} y {hasta} rpm"
        return statistics.fmean(v)

    bajo = sesgo_en(400, 1000)
    alto = sesgo_en(6000, 7100)
    assert -0.6 < bajo < -0.3, f"sesgo a bajo régimen {bajo:+.3f}, no es media cuenta"
    assert -0.6 < alto < -0.3, f"sesgo a alto régimen {alto:+.3f}, no es media cuenta"
    assert abs(alto - bajo) < 0.15, (
        f"el sesgo pasa de {bajo:+.3f} a {alto:+.3f}: crece con el valor, así que "
        "es un factor equivocado y no un truncamiento"
    )


# --------------------------------------------------------------------------- #
#  Los que siguen sin fijar: lo que se prueba es que la nota anterior era falsa.
# --------------------------------------------------------------------------- #


def test_los_dos_canales_descartados_por_una_fila_si_varian(
    filas: list[dict[str, int]],
    descriptor: dict[str, dict[str, object]],
) -> None:
    """Las dos notas decían «vale 0» y «es un parámetro de calibración». Ni una.

    Las dos se escribieron mirando la fila de referencia. Los dos canales varían
    sobre el log completo, y esta prueba lo fija para que la evidencia corregida
    no se pueda deshacer sin que algo se ponga rojo.
    """
    transitorio = [f["Transient Throttle Fuel Peak Synchronous Output"] for f in filas]
    no_nulos = [v for v in transitorio if v != 0]
    assert len(no_nulos) > 1000, f"solo {len(no_nulos)} valores no nulos"
    assert min(transitorio) < 0 < max(transitorio), "es un aporte con signo, no una cantidad"

    tasa = [f["Vehicle Speed 0 Calculated Rate"] for f in filas]
    assert len({*tasa}) > 100, "sería un parámetro de calibración si fuese constante"

    # Y los dos siguen sin factor, que es la otra mitad del resultado: medir que
    # varían no es lo mismo que poder fijar su escala.
    for tipo in ("FuelVolume", "PulsesPerLongDistance"):
        assert descriptor[tipo]["confianza"] == "unknown"
        assert descriptor[tipo]["dimension"] == "unknown"


def test_la_tasa_de_pulsos_es_proporcional_a_la_velocidad(
    filas: list[dict[str, int]],
) -> None:
    """Es una medida de frecuencia, y esto es lo único que se puede afirmar.

    Fija la relación entre los dos canales sin fijar la unidad de este: para eso
    haría falta la calibración del sensor en la ECU, que el log no publica.
    """
    cociente = [
        f["Vehicle Speed 0 Calculated Rate"] / f["Vehicle Speed"]
        for f in filas
        if f["Vehicle Speed"] > 200 and f["Vehicle Speed 0 Calculated Rate"] > 0
    ]
    assert len(cociente) > 500, f"solo {len(cociente)} filas con velocidad apreciable"
    assert _cv(cociente) < 1.0, f"cv {_cv(cociente):.2f} %: no es proporcional"
    assert statistics.median(cociente) == pytest.approx(4.082, rel=0.01)


def test_las_nueve_ganancias_de_pid_siguen_sin_fijar(
    descriptor: dict[str, dict[str, object]],
) -> None:
    """Y tienen que seguir así: su escala depende del lazo, que no está en el log.

    Es el caso donde la respuesta correcta de F1-38 es «no». Están puestas como
    dimensiones compuestas, así que la unidad que se muestra se deriva de las
    activas, pero el factor no se puede fijar y por eso se muestran en crudo.
    """
    for tipo in ("PercentPerRpm", "PercentPerKPa", "PercentPerLambda"):
        assert descriptor[tipo]["confianza"] == "unknown", f"{tipo} no se puede confirmar"
        assert descriptor[tipo]["compuesta"] is True
        assert descriptor[tipo]["a_canonica"] == 1.0
