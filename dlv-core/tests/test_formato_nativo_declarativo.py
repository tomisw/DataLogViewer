"""Añadir un formato nativo es escribir un descriptor (tarea FG-13).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.3 nivel 1.

QUÉ DECIDE ESTA SUITE
=====================
FG-13 promete una cosa concreta y comprobable: **un formato nativo nuevo se añade
escribiendo un descriptor, sin tocar Python.** Las pruebas que ya existían
(`test_haltech_cabecera.py`) siguen pasando, y eso demuestra que el refactor no
cambió el comportamiento sobre Haltech — pero no demuestra la promesa. Un motor
que siguiera cableando «Type» y «DataLogVersion» pasaría esas 37 pruebas igual de
bien: son el mismo formato de siempre.

Así que aquí se define un formato **inventado**, «TorqueTrace TT-2», que no se
parece a Haltech en ninguna de las decisiones que FG-13 movió al descriptor:

    Haltech                        TorqueTrace TT-2
    ---------------------------    ---------------------------------
    firma `%DataLog%`              firma `#TT-LOG`
    `Clave : Valor`                `Clave= Valor`
    versión en `DataLogVersion`    versión en `Rev`
    tipo en `Type`                 tipo en `Kind`
    identidad en `ID`              identidad en `Idx`
    rango `DisplayMaxMin` máx,mín  rango `Limits` MÍN;MÁX (orden contrario)
    delimitador `,`                delimitador `;`
    marca `HH:MM:SS.mmm`           marca `HH:MM:SS,mm` (dos decimales)

Si alguna de esas ocho decisiones siguiera viviendo en el código, este fichero no
se podría parsear. Ninguna línea de Python de `dlv_core` menciona TorqueTrace: el
descriptor va escrito aquí como texto y se carga por el mismo camino que el de
Haltech.

Y no basta con que parsee: se comprueba que el motor **rechaza** los descriptores
incompletos o incoherentes, porque el modo de fallar importa. Un descriptor al que
le falta la clave de tipo y que se carga adivinando «será `Type`» produce canales
con la escala equivocada y un fichero que parece haberse leído bien — que es
exactamente el fallo silencioso que las puertas G1 de este proyecto existen para
evitar.

Solo biblioteca estándar.
"""

from __future__ import annotations

import io

import pytest

from dlv_core.formatos.nativo import (
    Descriptor,
    ErrorDeDescriptor,
    ErrorDeFormato,
    cargar_descriptor,
    parsear_cabecera,
    sondear_formato,
)

# --------------------------------------------------------------------------- #
# El formato inventado
# --------------------------------------------------------------------------- #
#: Descriptor completo de un formato nativo que no existe. Está aquí y no en
#: `data/formats/` a propósito: `data/` son los formatos que el programa soporta
#: de verdad, y este solo existe para demostrar que la capa declarativa basta.
DESCRIPTOR_TT2 = """
[meta]
formato = "torquetrace_tt2"
software = "TorqueTrace TT-2 (formato inventado para la prueba de FG-13)"

[deteccion]
primera_linea = "#TT-LOG"
version_soportada = ["2", "2.1"]
clave_version = "Rev"
codificacion = "utf-8"

[cabecera]
separador_clave_valor = "="
clave_canal = "Sensor"
claves_bloque = ["Idx", "Kind", "Limits"]
claves_opcionales = ["Limits"]
identidad = "Idx"
clave_tipo = "Kind"
clave_rango = "Limits"
rango_separador = ";"
# Al contrario que Haltech: este formato escribe el mínimo primero.
rango_orden = ["min", "max"]

[cuerpo]
delimitador = ";"
clase_de_tiempo = "hora_del_dia"
patron_marca = "\\\\d\\\\d:\\\\d\\\\d:\\\\d\\\\d,\\\\d\\\\d"

[tipos.Revs]
dimension = "angular_speed"
a_canonica = 1.0
confianza = "confirmed"

[tipos.Kelvins]
dimension = "temperature"
a_canonica = 0.1
confianza = "confirmed"
"""

#: Un log de ese formato. Marca de tiempo con coma decimal y campos con `;`, que
#: es la combinación que obliga a que el delimitador venga del descriptor: con el
#: `,` de Haltech, la marca de tiempo se partiría por la mitad.
LOG_TT2 = (
    b"#TT-LOG\r\n"
    b"Rev= 2.1\r\n"
    b"Vehicle= banco de pruebas\r\n"
    b"Sensor= Engine Revs\r\n"
    b"Idx= 7\r\n"
    b"Kind= Revs\r\n"
    b"Limits= 0;9000\r\n"
    b"Sensor= Coolant\r\n"
    b"Idx= 12\r\n"
    b"Kind= Kelvins\r\n"
    b"Limits= 2331;4731\r\n"
    b"08:15:00,00;1200;3631\r\n"
    b"08:15:00,10;1250;3632\r\n"
)


def _cargar(texto: str) -> Descriptor:
    """El descriptor se escribe como texto y se carga por el mismo camino que el de
    Haltech: `cargar_descriptor` recibe bytes porque un descriptor real es un
    fichero, y aquí se codifica en el momento."""
    return cargar_descriptor(io.BytesIO(texto.encode("utf-8")))


@pytest.fixture(scope="module")
def tt2() -> Descriptor:
    return _cargar(DESCRIPTOR_TT2)


# --------------------------------------------------------------------------- #
# La promesa de FG-13
# --------------------------------------------------------------------------- #
def test_un_formato_nuevo_se_parsea_sin_una_linea_de_python(tt2: Descriptor) -> None:
    """La prueba que distingue «he movido cosas de sitio» de «ya es declarativo»."""
    cab = parsear_cabecera(LOG_TT2, tt2)

    assert cab.formato == "torquetrace_tt2"
    assert cab.version == "2.1"
    assert cab.n_canales == 2
    assert cab.metadatos["Vehicle"] == "banco de pruebas"

    revs = cab.por_nombre("Engine Revs")
    assert revs is not None
    # La identidad es `Idx`, no `ID`: si el motor siguiera citando «ID», el bloque
    # entero se habría descartado por incompleto.
    assert revs.id == 7
    assert revs.tipo == "Revs"
    assert revs.dimension == "angular_speed"

    coolant = cab.por_id(12)
    assert coolant is not None
    assert coolant.nombre == "Coolant"
    assert coolant.dimension == "temperature"


def test_el_orden_del_rango_lo_manda_el_descriptor(tt2: Descriptor) -> None:
    """`Limits= 2331;4731` es MÍN;MÁX, al contrario que `DisplayMaxMin`.

    Es la decisión más fácil de que se cuele al revés, porque un rango invertido
    no rompe nada: sale un eje al revés y un canal que parece medir bien.
    """
    cab = parsear_cabecera(LOG_TT2, tt2)
    coolant = cab.por_id(12)
    assert coolant is not None
    assert coolant.display_min == 2331
    assert coolant.display_max == 4731


def test_el_delimitador_no_parte_la_marca_de_tiempo(tt2: Descriptor) -> None:
    """La marca `08:15:00,00` lleva coma, y el delimitador es `;`.

    Con el delimitador de Haltech cableado, la primera fila de datos no se
    reconocería como tal (o se partiría por la mitad) y la cabecera se comería el
    cuerpo entero sin dar error.
    """
    cab = parsear_cabecera(LOG_TT2, tt2)
    assert cab.delimitador == ";"
    assert LOG_TT2[cab.offset_datos :].startswith(b"08:15:00,00;")


def test_el_sondeo_distingue_los_dos_formatos(tt2: Descriptor) -> None:
    """Dos descriptores cargados a la vez: cada log va al suyo, y un CSV a ninguno."""
    with (RAIZ_DATOS / "haltech_nsp.toml").open("rb") as fh:
        haltech = cargar_descriptor(fh)
    descriptores = (haltech, tt2)

    assert sondear_formato(LOG_TT2, descriptores) is tt2
    assert sondear_formato(b"%DataLog%\r\nDataLogVersion : 1.1\r\n", descriptores) is haltech
    # Un CSV cualquiera no es ninguno de los dos: eso NO es un error, es el
    # camino de CSV genérico de la fase FG.
    assert sondear_formato(b"time,rpm,map\r\n0,800,101\r\n", descriptores) is None


def test_una_version_no_soportada_se_rechaza(tt2: Descriptor) -> None:
    log = LOG_TT2.replace(b"Rev= 2.1", b"Rev= 3.0")
    with pytest.raises(ErrorDeFormato, match=r"3\.0"):
        parsear_cabecera(log, tt2)


# --------------------------------------------------------------------------- #
# El modo de fallar
# --------------------------------------------------------------------------- #
#  Un descriptor incompleto tiene que fallar AL CARGARSE, no producir un log mal
#  leído. Cada caso de aquí es una clave cuya ausencia se pagaría en silencio.
CLAVES_OBLIGATORIAS = [
    ('clave_tipo = "Kind"', "clave_tipo"),
    ('identidad = "Idx"', "identidad"),
    ('clave_canal = "Sensor"', "clave_canal"),
    ('separador_clave_valor = "="', "separador_clave_valor"),
    ('primera_linea = "#TT-LOG"', "primera_linea"),
    ('delimitador = ";"', "delimitador"),
    ('clase_de_tiempo = "hora_del_dia"', "clase_de_tiempo"),
]


@pytest.mark.parametrize(
    ("linea", "clave"), CLAVES_OBLIGATORIAS, ids=[c for _, c in CLAVES_OBLIGATORIAS]
)
def test_sin_una_clave_obligatoria_el_descriptor_no_carga(linea: str, clave: str) -> None:
    assert linea in DESCRIPTOR_TT2, "la prueba quita una línea que ya no existe"
    with pytest.raises(ErrorDeDescriptor) as exc:
        _cargar(DESCRIPTOR_TT2.replace(linea, ""))
    # El mensaje tiene que nombrar la clave y el formato: un «descriptor
    # inválido» a secas obliga a leer el motor para saber qué falta.
    assert clave in str(exc.value)
    assert "torquetrace_tt2" in str(exc.value) or "sin nombre" in str(exc.value)


def test_una_identidad_que_no_es_clave_de_bloque_se_rechaza() -> None:
    """Cargaría, y luego fallaría canal a canal con la cabecera ya medio leída."""
    roto = DESCRIPTOR_TT2.replace('identidad = "Idx"', 'identidad = "Serial"')
    with pytest.raises(ErrorDeDescriptor, match="claves_bloque"):
        _cargar(roto)


def test_una_identidad_declarada_opcional_se_rechaza() -> None:
    roto = DESCRIPTOR_TT2.replace(
        'claves_opcionales = ["Limits"]', 'claves_opcionales = ["Limits", "Idx"]'
    )
    with pytest.raises(ErrorDeDescriptor):
        _cargar(roto)


def test_una_clase_de_tiempo_reconocida_pero_no_interpretable_se_rechaza() -> None:
    """El límite honesto del nivel 1, y tiene que ser un rechazo, no un apaño.

    `iso8601` es una `ClaseDeTiempo` válida del vocabulario de FG-04, pero el
    único intérprete que existe hoy entiende la hora del día. Cargar el descriptor
    y producir después un eje de tiempo inventado es lo que `docs/07` §7.5
    prohíbe, así que el rechazo es al cargar y el mensaje dice por qué.
    """
    roto = DESCRIPTOR_TT2.replace('clase_de_tiempo = "hora_del_dia"', 'clase_de_tiempo = "iso8601"')
    with pytest.raises(ErrorDeDescriptor, match="iso8601"):
        _cargar(roto)


def test_una_clase_de_tiempo_inventada_se_rechaza_enumerando_las_validas() -> None:
    roto = DESCRIPTOR_TT2.replace(
        'clase_de_tiempo = "hora_del_dia"', 'clase_de_tiempo = "cuando_sea"'
    )
    with pytest.raises(ErrorDeDescriptor) as exc:
        _cargar(roto)
    assert "hora_del_dia" in str(exc.value), "el mensaje tiene que decir cuáles valen"


def test_una_codificacion_inexistente_se_rechaza() -> None:
    roto = DESCRIPTOR_TT2.replace('codificacion = "utf-8"', 'codificacion = "utf-42"')
    with pytest.raises(ErrorDeDescriptor, match="utf-42"):
        _cargar(roto)


def test_un_rango_sin_orden_valido_se_rechaza() -> None:
    roto = DESCRIPTOR_TT2.replace('rango_orden = ["min", "max"]', 'rango_orden = ["max", "max"]')
    with pytest.raises(ErrorDeDescriptor):
        _cargar(roto)


def test_sin_seccion_de_tipos_no_carga() -> None:
    """Un descriptor sin `[tipos]` no puede resolver ninguna dimensión."""
    corte = DESCRIPTOR_TT2.index("[tipos.Revs]")
    with pytest.raises(ErrorDeDescriptor, match="tipos"):
        _cargar(DESCRIPTOR_TT2[:corte])


# --------------------------------------------------------------------------- #
# Que el formato de verdad no se haya movido
# --------------------------------------------------------------------------- #
from pathlib import Path  # noqa: E402  (se usa solo aquí abajo, ver comentario)

#: Se importa al final a propósito: lo de arriba es la demostración de que un
#: formato nuevo no necesita nada del repositorio, y tener `data/` a mano desde el
#: principio invitaría a apoyarse en él sin darse cuenta.
RAIZ_DATOS = Path(__file__).resolve().parents[2] / "data" / "formats"


def test_el_descriptor_de_haltech_declara_todo_lo_que_fg13_le_movio() -> None:
    """Las claves nuevas están en el fichero de datos, no en valores por omisión.

    Si el motor las trajese con un valor por omisión igual al de Haltech, quitar
    la sección del descriptor no rompería nada y la migración sería aparente: el
    formato seguiría viviendo en el código. Esta prueba lee el TOML y exige que
    los valores estén escritos.
    """
    import tomllib

    with (RAIZ_DATOS / "haltech_nsp.toml").open("rb") as fh:
        bruto = tomllib.load(fh)

    assert bruto["deteccion"]["clave_version"] == "DataLogVersion"
    cab = bruto["cabecera"]
    assert cab["separador_clave_valor"] == ":"
    assert cab["clave_tipo"] == "Type"
    assert cab["clave_rango"] == "DisplayMaxMin"
    assert cab["rango_separador"] == ","
    # El orden de Haltech es el contrario del intuitivo, y es la evidencia con la
    # que se confirmaron los factores de escala de [tipos].
    assert cab["rango_orden"] == ["max", "min"]
    cue = bruto["cuerpo"]
    assert cue["delimitador"] == ","
    assert cue["clase_de_tiempo"] == "hora_del_dia"
