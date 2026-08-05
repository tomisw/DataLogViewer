"""Fuzzing de propiedad sobre cabecera y filas con Hypothesis (tarea F1-36).

QUÉ AÑADE ESTO A LAS PRUEBAS QUE YA HAY
=======================================
`test_haltech_cabecera.py` comprueba el corpus de `samples/corrupt/`: una
docena de ficheros con una anomalía cada uno, elegidos por una persona que ya
sabía qué podía salir mal. Eso cubre lo previsto. Lo que no cubre —y es lo que
hace este fichero— son las **combinaciones** y los **bytes que a nadie se le
ocurrieron**: una cabecera truncada justo en mitad de un `DisplayMaxMin`, un
nombre de canal que contiene dos puntos, un fichero que empieza con la firma y
sigue con ruido.

Y hay una razón concreta por la que importa aquí más que en otro proyecto. La
regla E1.7 de `docs/02` §2.5 dice que el parser **avisa y sigue** siempre que
pueda producir datos utilizables y **rechaza** solo cuando seguir daría
resultados silenciosamente equivocados. Eso deja exactamente dos salidas
legítimas para cualquier entrada:

    1. una `Cabecera` válida (con avisos si hace falta), o
    2. un `ErrorDeFormato`, que es un rechazo explicado.

Cualquier otra excepción —`UnicodeDecodeError`, `IndexError`, `ValueError`
suelto— es un fallo del contrato, porque la capa de arriba no puede
distinguirla de un defecto interno y acabará enseñando una traza donde tenía
que enseñar «este fichero no se puede leer, y por esto». Esa es la propiedad
principal de este fichero, y es el tipo de cosa que un corpus de ejemplos no
puede demostrar y un generador sí.

LO QUE NO SE FUZZEA, Y POR QUÉ
==============================
`parsear_cuerpo` con bytes arbitrarios **no** se fuzzea: por debajo hay
`polars.read_csv`, y lo que se estaría probando es el manejo de errores de
Polars, no el contrato de este proyecto. Lo que sí se fuzzea del cuerpo son las
anomalías que F1-02 y F1-03 prometen tolerar por escrito (celdas vacías, filas
con campos de más o de menos, centinelas de desbordamiento), y ahí las
propiedades son fuertes: ni una fila inventada, ni una perdida, ni un hueco
convertido en cero.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, parsear_cuerpo
from dlv_core.formatos.haltech import (
    BOM_UTF8,
    Cabecera,
    Descriptor,
    ErrorDeFormato,
    cargar_descriptor,
    parsear_cabecera,
)
from dlv_core.formatos.limpieza import detectar_filas_malformadas, nulificar_centinelas
from dlv_core.unidades import Catalogo, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]

with (RAIZ / "data" / "formats" / "haltech_nsp.toml").open("rb") as _fh:
    DESCRIPTOR: Descriptor = cargar_descriptor(_fh)
with (RAIZ / "data" / "units.toml").open("rb") as _fh:
    CATALOGO: Catalogo = cargar_catalogo(_fh)

TIPOS_CONOCIDOS = sorted(DESCRIPTOR.tipos)

# Perfil por omisión de este fichero. `deadline=None` porque el primer caso de
# cada prueba paga la compilación de Polars y da un falso positivo de lentitud;
# lo que se busca aquí son fallos de corrección, no de tiempo (para el tiempo
# está `tools/banco.py`).
AJUSTES = settings(max_examples=200, deadline=None)


# --------------------------------------------------------------------------- #
# Generadores
# --------------------------------------------------------------------------- #
# Los nombres de canal salen alfanuméricos con espacios a propósito: son los
# que produce Haltech ("Coolant Temperature", "Knock Sensor 2 Knock Count").
# Los caracteres que rompen la GRAMÁTICA —los dos puntos, el salto de línea— se
# prueban aparte y con intención, no mezclados con el caso normal, porque si un
# generador los emite de vez en cuando el fallo aparece y desaparece según la
# semilla y cuesta mucho más de leer.
nombres_de_canal = (
    st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters=" "),
        min_size=1,
        max_size=24,
    )
    .map(str.strip)
    .filter(lambda s: len(s) > 0 and ":" not in s)
)

# Se incluyen tipos que NO están en el descriptor: es el caso "tipo
# desconocido", que E1.7 clasifica como aviso, no como error.
tipos = st.one_of(
    st.sampled_from(TIPOS_CONOCIDOS),
    st.sampled_from(["TIPO_QUE_NO_EXISTE", "XYZZY"]),
)

fines_de_linea = st.sampled_from([b"\r\n", b"\n"])


@dataclass(frozen=True)
class ModeloCanal:
    nombre: str
    id: int
    tipo: str
    display: tuple[int, int] | None


@dataclass(frozen=True)
class ModeloLog:
    canales: tuple[ModeloCanal, ...]
    filas: tuple[tuple[int | None, ...], ...]
    fin_de_linea: bytes
    con_bom: bool
    salto_final: bool

    @property
    def n_columnas(self) -> int:
        return len(self.canales) + 1


@st.composite
def modelos_de_log(
    dibujar: st.DrawFn,
    *,
    min_canales: int = 1,
    max_canales: int = 6,
    min_filas: int = 1,
    max_filas: int = 12,
) -> ModeloLog:
    """Un log Haltech plausible.

    `min_filas = 1` por omisión, y no 0, porque un fichero con cabecera y sin
    ninguna fila de datos **no es un log válido**: `parsear_cabecera` lo rechaza
    con «la cabecera parece truncada», y con razón —una cabecera sin datos
    detrás es indistinguible de una copia interrumpida—. La primera versión de
    este generador permitía cero filas y puso en rojo tres pruebas de ida y
    vuelta; el defecto estaba en el generador, no en el parser. Se deja dicho
    porque la tentación al ver esas tres en rojo es tocar el parser.
    """
    n = dibujar(st.integers(min_canales, max_canales))
    nombres = dibujar(
        st.lists(nombres_de_canal, min_size=n, max_size=n, unique=True),
    )
    ids = dibujar(st.lists(st.integers(0, 5000), min_size=n, max_size=n, unique=True))
    canales = tuple(
        ModeloCanal(
            nombre=nombre,
            id=id_,
            tipo=dibujar(tipos),
            display=dibujar(
                st.one_of(
                    st.none(),
                    st.tuples(st.integers(-32768, 32767), st.integers(-32768, 32767)),
                )
            ),
        )
        for nombre, id_ in zip(nombres, ids, strict=True)
    )
    n_filas = dibujar(st.integers(min_filas, max_filas))
    # `None` es la celda vacía: docs/01 la define como hueco, NO como cero, y
    # esa distinción es la que se comprueba abajo.
    celda = st.one_of(st.none(), st.integers(-2_147_483_648, 2_147_483_647))
    filas = tuple(
        tuple(dibujar(st.lists(celda, min_size=len(canales), max_size=len(canales))))
        for _ in range(n_filas)
    )
    return ModeloLog(
        canales=canales,
        filas=filas,
        fin_de_linea=dibujar(fines_de_linea),
        con_bom=dibujar(st.booleans()),
        salto_final=dibujar(st.booleans()),
    )


def marca(indice: int) -> str:
    """`HH:MM:SS.mmm` a 100 Hz, que es la cadencia del AutoLog real."""
    ms_total = indice * 10
    h, resto = divmod(ms_total, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, ms = divmod(resto, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def render(modelo: ModeloLog) -> bytes:
    """El modelo a bytes de fichero Haltech."""
    lineas: list[str] = ["%DataLog%", "DataLogVersion : 1.1"]
    for canal in modelo.canales:
        lineas.append(f"Channel : {canal.nombre}")
        lineas.append(f"ID : {canal.id}")
        lineas.append(f"Type : {canal.tipo}")
        if canal.display is not None:
            lineas.append(f"DisplayMaxMin : {canal.display[0]},{canal.display[1]}")
    lineas.append("EndHeader : ")
    for i, fila in enumerate(modelo.filas):
        celdas = ",".join("" if v is None else str(v) for v in fila)
        lineas.append(f"{marca(i)},{celdas}")

    eol = modelo.fin_de_linea.decode()
    texto = eol.join(lineas) + (eol if modelo.salto_final else "")
    return (BOM_UTF8 if modelo.con_bom else b"") + texto.encode("utf-8")


# --------------------------------------------------------------------------- #
# Cabecera: ida y vuelta
# --------------------------------------------------------------------------- #
@AJUSTES
@given(modelos_de_log())
def test_la_cabecera_da_la_vuelta_sin_perder_ni_reordenar_canales(modelo: ModeloLog) -> None:
    """Nombre, ID, tipo y ORDEN sobreviven al parseo.

    El orden es el que fija a qué columna corresponde cada canal (docs/01 §1.3):
    una permutación no rompería nada visible, atribuiría cada serie al canal
    equivocado. Es el fallo más caro que puede tener este parser porque el
    resultado sigue pareciendo un log.
    """
    cab = parsear_cabecera(render(modelo), DESCRIPTOR)
    assert cab.n_canales == len(modelo.canales)
    for esperado, obtenido in zip(modelo.canales, cab.canales, strict=True):
        assert obtenido.nombre == esperado.nombre
        assert obtenido.id == esperado.id
        assert obtenido.tipo == esperado.tipo
    assert [c.orden for c in cab.canales] == list(range(len(modelo.canales)))
    assert [c.columna for c in cab.canales] == list(range(1, len(modelo.canales) + 1))


@AJUSTES
@given(modelos_de_log())
def test_offset_datos_apunta_exactamente_a_la_primera_fila(modelo: ModeloLog) -> None:
    """`datos[offset_datos:]` empieza en una fila de datos, BOM o no.

    Es lo que promete el docstring de `Cabecera.offset_datos` y de lo que
    depende `parsear_cuerpo`. Un offset corrido por el BOM o por un CRLF
    metería la última línea de cabecera como si fuera una fila de datos: no
    reventaría, daría una fila de más con valores nulos.
    """
    assume(modelo.filas)
    datos = render(modelo)
    cab = parsear_cabecera(datos, DESCRIPTOR)
    resto = datos[cab.offset_datos :]
    assert resto.startswith(marca(0).encode() + b",")


@AJUSTES
@given(modelos_de_log())
def test_el_bom_y_el_fin_de_linea_no_cambian_lo_que_se_lee(modelo: ModeloLog) -> None:
    """Las cuatro variantes tipográficas del mismo log dan los mismos canales.

    Es la lista de verificación de docs/01 §1.13: BOM sí/no y CRLF/LF son
    accidentes de quién exportó el fichero, no información.
    """
    variantes = [
        ModeloLog(modelo.canales, modelo.filas, eol, bom, modelo.salto_final)
        for eol in (b"\r\n", b"\n")
        for bom in (True, False)
    ]
    lecturas = [parsear_cabecera(render(v), DESCRIPTOR) for v in variantes]
    referencia = [(c.nombre, c.id, c.tipo, c.orden) for c in lecturas[0].canales]
    for lectura in lecturas[1:]:
        assert [(c.nombre, c.id, c.tipo, c.orden) for c in lectura.canales] == referencia


@AJUSTES
@given(modelos_de_log(min_canales=2, max_canales=4))
def test_un_nombre_repetido_avisa_pero_no_rechaza(modelo: ModeloLog) -> None:
    """El formato no prohíbe nombres repetidos, así que E1.7 manda avisar y
    seguir: la identidad interna es el ID (docs/01 §1.3). Rechazar aquí dejaría
    ilegible un log perfectamente utilizable."""
    canales = list(modelo.canales)
    canales[1] = ModeloCanal(canales[0].nombre, canales[1].id, canales[1].tipo, canales[1].display)
    repetido = ModeloLog(
        tuple(canales), modelo.filas, modelo.fin_de_linea, modelo.con_bom, modelo.salto_final
    )
    cab = parsear_cabecera(render(repetido), DESCRIPTOR)
    assert cab.n_canales == len(canales)
    assert "nombre_duplicado" in {a.codigo for a in cab.avisos}


# --------------------------------------------------------------------------- #
# Cabecera: robustez (la propiedad principal del fichero)
# --------------------------------------------------------------------------- #
def solo_salidas_legitimas(datos: bytes) -> Cabecera | None:
    """Llama al parser y falla si escapa algo que no sea `ErrorDeFormato`.

    Devuelve la `Cabecera` si parseó, o `None` si rechazó. Se centraliza aquí
    para que el mensaje de fallo diga siempre qué excepción se escapó y con qué
    bytes, que es lo único que hace útil un contraejemplo de Hypothesis.
    """
    try:
        return parsear_cabecera(datos, DESCRIPTOR)
    except ErrorDeFormato:
        return None
    # `except Exception` amplio a propósito: cazar cualquier excepción que no
    # sea `ErrorDeFormato` ES la prueba, no un descuido.
    except Exception as error:
        raise AssertionError(
            f"parsear_cabecera dejó escapar {type(error).__name__}: {error}\n"
            f"Con estos bytes: {datos[:400]!r}\n"
            "E1.7 solo admite dos salidas: una Cabecera o un ErrorDeFormato. "
            "Cualquier otra excepción llega a la interfaz como una traza donde "
            "tenía que haber un motivo."
        ) from error


@settings(max_examples=400, deadline=None)
@given(st.binary(min_size=0, max_size=400))
def test_bytes_arbitrarios_no_hacen_escapar_nada_raro(datos: bytes) -> None:
    solo_salidas_legitimas(datos)


@settings(max_examples=400, deadline=None)
@given(st.binary(min_size=0, max_size=300))
def test_la_firma_seguida_de_ruido_tampoco(ruido: bytes) -> None:
    """El caso interesante: el fichero SÍ parece del formato, así que el parser
    entra en la gramática en vez de rechazar en la primera línea."""
    solo_salidas_legitimas(b"%DataLog%\r\n" + ruido)


@AJUSTES
@given(modelos_de_log(), st.floats(0, 1))
def test_truncar_un_log_valido_por_cualquier_sitio(modelo: ModeloLog, fraccion: float) -> None:
    """Un fichero cortado a medias —copia interrumpida, tarjeta llena— es el
    corrupto más frecuente del mundo real, y el que más formas distintas tiene.

    Y si a pesar del corte llega a parsear, la cabecera que devuelve tiene que
    seguir siendo coherente: `offset_datos` dentro del fichero y apuntando a
    una fila. Una cabecera "medio válida" con un offset pasado de largo es peor
    que un rechazo.
    """
    datos = render(modelo)
    corte = int(len(datos) * fraccion)
    cab = solo_salidas_legitimas(datos[:corte])
    if cab is not None:
        assert 0 <= cab.offset_datos <= corte
        assert cab.n_canales >= 1


@AJUSTES
@given(modelos_de_log(), st.integers(0, 10_000), st.integers(0, 255))
def test_cambiar_un_byte_de_un_log_valido(modelo: ModeloLog, posicion: int, valor: int) -> None:
    """Corrupción de un solo byte: lo que deja un sector defectuoso."""
    datos = bytearray(render(modelo))
    assume(datos)
    datos[posicion % len(datos)] = valor
    solo_salidas_legitimas(bytes(datos))


# --------------------------------------------------------------------------- #
# Cuerpo
# --------------------------------------------------------------------------- #
@AJUSTES
@given(modelos_de_log())
def test_ni_una_fila_inventada_ni_una_perdida(modelo: ModeloLog) -> None:
    """Es la propiedad que hace confiable cualquier estadística de aguas abajo.

    Una fila de más (la última línea de cabecera leída como dato) o una de
    menos (el último salto de línea mal contado) no rompe nada visible: cambia
    los percentiles y desplaza el eje de tiempo, y eso se descubre semanas
    después comparando con otra herramienta.
    """
    assume(modelo.filas)
    datos = render(modelo)
    cab = parsear_cabecera(datos, DESCRIPTOR)
    df = parsear_cuerpo(datos, cab)
    assert df.height == len(modelo.filas)
    assert df.width == modelo.n_columnas == cab.n_columnas


@AJUSTES
@given(modelos_de_log())
def test_una_celda_vacia_es_un_hueco_y_no_un_cero(modelo: ModeloLog) -> None:
    """«hueco != 0» (docs/01). Un hueco convertido en cero es un dato inventado,
    y en un canal de presión o de lambda un cero es además un valor alarmante:
    dispararía detectores que no tenían que dispararse."""
    assume(any(None in fila for fila in modelo.filas))
    datos = render(modelo)
    cab = parsear_cabecera(datos, DESCRIPTOR)
    df = parsear_cuerpo(datos, cab)
    for i, fila in enumerate(modelo.filas):
        for j, valor in enumerate(fila):
            celda = df[columna_polars(j + 1)][i]
            if valor is None:
                assert celda is None, f"la celda vacía ({i},{j}) se leyó como {celda!r}"
            else:
                assert celda == valor


@AJUSTES
@given(modelos_de_log(min_canales=2), st.integers(0, 50), st.sampled_from([-1, 1]))
def test_una_fila_con_campos_de_mas_o_de_menos_se_registra(
    modelo: ModeloLog, cual: int, delta: int
) -> None:
    """docs/01 §1.13 pide «se registra y se salta», no solo «se salta».

    Una fila corta rellenada con nulos en silencio es indistinguible de un
    hueco de adquisición real, y las dos cosas piden decisiones distintas.
    """
    assume(modelo.filas)
    indice = cual % len(modelo.filas)
    lineas = render(modelo).split(modelo.fin_de_linea)
    # La primera línea de datos es la que empieza por una marca de tiempo.
    primera = next(i for i, ln in enumerate(lineas) if ln.startswith(marca(0).encode()))
    objetivo = primera + indice
    if delta > 0:
        lineas[objetivo] = lineas[objetivo] + b",999"
    else:
        # Al menos dos comas: quitando un campo tiene que quedar una fila que
        # SIGA pareciendo una fila de datos (`HH:MM:SS.mmm,` con coma). Si se
        # quita el único campo, la línea deja de casar con la gramática de fila
        # y el fichero pasa a ser una cabecera sin datos, que es otro defecto
        # distinto —y ya está probado en `test_casos_minimos_reducidos`—.
        assume(lineas[objetivo].count(b",") >= 2)
        lineas[objetivo] = lineas[objetivo].rsplit(b",", 1)[0]

    datos = modelo.fin_de_linea.join(lineas)
    cab = parsear_cabecera(datos, DESCRIPTOR)
    avisos = detectar_filas_malformadas(datos, cab)
    assert avisos, "una fila con campos de más o de menos tiene que dejar constancia"
    assert all(a.codigo == "fila_malformada" for a in avisos)
    assert str(indice + 1) in " ".join(a.mensaje for a in avisos)


@AJUSTES
@given(modelos_de_log())
def test_un_log_limpio_no_produce_avisos_de_fila(modelo: ModeloLog) -> None:
    """La otra mitad de la prueba anterior, y la que de verdad cuesta pasar: un
    detector que avisa de todo no informa de nada. Si esto se pone rojo, el
    informe de importación de un log sano se llena de ruido y el usuario deja
    de mirarlo, que es exactamente lo que E1.7 quiere evitar."""
    assume(modelo.filas)
    datos = render(modelo)
    cab = parsear_cabecera(datos, DESCRIPTOR)
    assert detectar_filas_malformadas(datos, cab) == []


@AJUSTES
@given(
    st.lists(
        st.lists(
            st.one_of(
                st.sampled_from(sorted(CATALOGO.centinelas_i32)),
                st.integers(-100_000, 100_000),
                st.none(),
            ),
            min_size=3,
            max_size=3,
        ),
        min_size=1,
        max_size=30,
    )
)
def test_los_centinelas_se_anulan_y_nada_mas(tabla: list[list[int | None]]) -> None:
    """Ni uno de más ni uno de menos.

    De menos: un `2147483647` contado como medida arrastra cualquier media o
    percentil hasta el absurdo. De más: anular un valor legítimo abre un hueco
    que no existía, y `8388607` —que está en la lista— es un número que un
    canal de 24 bits puede alcanzar de verdad. Por eso la lista vive en
    `data/units.toml` y es revisable, y por eso esta prueba comprueba las dos
    direcciones.
    """
    df = pl.DataFrame(
        {COLUMNA_MARCA: [marca(i) for i in range(len(tabla))]}
        | {columna_polars(j + 1): [fila[j] for fila in tabla] for j in range(3)},
        schema_overrides={columna_polars(j + 1): pl.Int32 for j in range(3)},
    )
    limpio = nulificar_centinelas(df, CATALOGO)

    assert limpio.height == df.height
    assert limpio.columns == df.columns
    assert limpio[COLUMNA_MARCA].to_list() == df[COLUMNA_MARCA].to_list()
    for j in range(3):
        columna = columna_polars(j + 1)
        for i, original in enumerate(df[columna].to_list()):
            obtenido = limpio[columna][i]
            if original is not None and original in CATALOGO.centinelas_i32:
                assert obtenido is None, f"el centinela {original} sobrevivió en ({i},{j})"
            else:
                assert obtenido == original, f"({i},{j}) cambió de {original!r} a {obtenido!r}"


# --------------------------------------------------------------------------- #
# Regresiones encontradas por el generador
# --------------------------------------------------------------------------- #
# Cuando Hypothesis encuentra un contraejemplo, el caso reducido se copia aquí
# como prueba normal. El generador es una red, no un registro: sin esto, una
# regresión ya arreglada solo se vuelve a cazar si sale la misma semilla.
@pytest.mark.parametrize(
    "datos",
    [
        pytest.param(b"", id="fichero-vacio"),
        pytest.param(b"%DataLog%", id="solo-la-firma"),
        pytest.param(b"%DataLog%\r\n", id="firma-y-nada-mas"),
        pytest.param(b"%DataLog%\r\nDataLogVersion : 1.1\r\n", id="sin-canales"),
        pytest.param(b"%DataLog%\r\nDataLogVersion : 1.1\r\nChannel : a\r\n", id="bloque-abierto"),
        pytest.param(BOM_UTF8 + b"%DataLog%\r\n", id="bom-y-firma"),
        pytest.param(b"%DataLog%\r\n\xff\xfe\x00\x01", id="bytes-no-utf8"),
    ],
)
def test_casos_minimos_reducidos(datos: bytes) -> None:
    assert solo_salidas_legitimas(datos) is None
