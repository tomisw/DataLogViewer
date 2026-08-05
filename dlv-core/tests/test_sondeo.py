"""Pruebas del sondeo de formato de CSV genérico (tarea FG-01).

Tres capas, y cada una caza lo que las otras no pueden:

1. **El corpus de `samples/generico/`** (14 ficheros, uno por rasgo) es la
   especificación ejecutable: si el sondeo cambia de opinión sobre uno de ellos,
   se entera aquí. Cubre lo previsto por quien escribió el corpus.
2. **Los casos que se equivocan en silencio**, escritos a mano porque no salen
   de un generador: el `;` con coma decimal, las comas dentro de comillas, el
   UTF-16, el fin de línea mixto, la comilla que no delimita nada. Todos tienen
   en común que producen un resultado *plausible* cuando se detectan mal, que es
   lo que los hace caros.
3. **Propiedades con Hypothesis**, en la línea de `test_fuzzing_formato.py`. Dos
   importan de verdad:
   - el sondeo **nunca lanza una excepción**: para cualquier secuencia de bytes
     hay un `Sondeo`, con la confianza que haga falta. Es la regla E1.7 llevada
     hasta el final —aquí ni siquiera queda el caso de rechazo del parser
     nativo—, y una traza escapando de un sondeo llegaría a la interfaz donde
     tenía que haber una propuesta editable.
   - **`confirmed` no miente**: cuando el veredicto del delimitador es
     `confirmed`, es el delimitador de verdad. Un `inferred` equivocado lo
     corrige el usuario en el asistente (§7.8); un `confirmed` equivocado se
     precarga sin que nadie lo mire, y ese es el camino por el que un fichero
     entero se importa con las columnas partidas donde no toca.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from dlv_core.formatos.sondeo import (
    CANDIDATOS_DELIMITADOR,
    LIMITE_MUESTRA,
    Sondeo,
    sondear,
)

RAIZ = Path(__file__).resolve().parents[2]
GENERICO = RAIZ / "samples" / "generico"
REAL = RAIZ / "samples" / "real"

AJUSTES = settings(max_examples=200, deadline=None)


def codigos(sondeo: Sondeo) -> set[str]:
    return {a.codigo for a in sondeo.avisos}


# --------------------------------------------------------------------------- #
# 1. El corpus de samples/generico como especificación ejecutable
# --------------------------------------------------------------------------- #
# (fichero, codificación, fin de línea, delimitador, comilla). Las expectativas
# salen de `samples/generico/README.md`, que es donde el corpus declara qué
# ejercita cada fichero; aquí no se «ajustan a lo que sale».
CORPUS = [
    ("01-coma-punto.csv", "utf-8", "CRLF", ",", None),
    ("02-puntoycoma-coma.csv", "utf-8", "CRLF", ";", None),
    ("03-tabulaciones.csv", "utf-8", "CRLF", "\t", None),
    ("04-fila-de-unidades.csv", "utf-8", "CRLF", ",", None),
    ("05-unidad-en-el-nombre.csv", "utf-8", "CRLF", ",", None),
    ("06-sin-columna-de-tiempo.csv", "utf-8", "CRLF", ",", None),
    ("07-epoch-segundos.csv", "utf-8", "CRLF", ",", None),
    ("08-epoch-milisegundos.csv", "utf-8", "CRLF", ",", None),
    ("09-iso8601.csv", "utf-8", "CRLF", ",", None),
    ("10-latin1.csv", "latin-1", "CRLF", ",", None),
    ("11-valores-ausentes.csv", "utf-8", "CRLF", ",", None),
    ("12-texto-y-booleanos.csv", "utf-8", "CRLF", ",", None),
    ("13-columnas-duplicadas.csv", "utf-8", "CRLF", ",", None),
    ("14-preambulo-largo.csv", "utf-8", "CRLF", ",", None),
]


@pytest.mark.parametrize(("fichero", "codec", "eol", "delim", "comilla"), CORPUS)
def test_el_corpus_generico_se_sondea_entero(
    fichero: str, codec: str, eol: str, delim: str, comilla: str | None
) -> None:
    datos = (GENERICO / fichero).read_bytes()
    s = sondear(datos, tamano_total=len(datos))
    assert s.codificacion.valor == codec, s.resumen()
    assert s.fin_de_linea.valor == eol, s.resumen()
    assert s.delimitador.valor == delim, s.resumen()
    assert s.comillas.valor == comilla, s.resumen()
    # Los 14 ficheros tienen 6 columnas salvo el de la fila de unidades, que
    # también, y el del preámbulo, que también: el corpus es rectangular.
    assert s.n_campos == 6, s.resumen()


def test_el_corpus_generico_no_deja_nada_en_unknown_salvo_la_codificacion_latin1() -> None:
    """Un sondeo que se rinde en un fichero limpio deja al usuario rellenando a
    mano lo que la máquina podía deducir, y el asistente se vuelve un peaje
    (§7.9). El único `unknown` legítimo del corpus es el de la codificación del
    fichero 10: latin-1 no es deducible, solo es lo que queda cuando UTF-8 no
    valida."""
    for fichero, *_ in CORPUS:
        datos = (GENERICO / fichero).read_bytes()
        s = sondear(datos, tamano_total=len(datos))
        assert s.delimitador.es_fiable, f"{fichero}: {s.delimitador}"
        assert s.fin_de_linea.es_fiable, f"{fichero}: {s.fin_de_linea}"
        assert s.comillas.es_fiable, f"{fichero}: {s.comillas}"
        if fichero != "10-latin1.csv":
            assert s.codificacion.es_fiable, f"{fichero}: {s.codificacion}"


def test_el_preambulo_no_impide_ver_el_delimitador_pero_deja_constancia() -> None:
    """§7.4 paso 7: las 12 líneas de metadatos de `14-preambulo-largo.csv` no
    tienen delimitador, así que bajan la cobertura. El veredicto sigue siendo el
    bueno, con confianza `inferred`, y el aviso dice cuántas líneas discrepan
    para que FG-03 sepa que ahí hay un preámbulo que separar."""
    datos = (GENERICO / "14-preambulo-largo.csv").read_bytes()
    s = sondear(datos, tamano_total=len(datos))
    assert s.delimitador.valor == ","
    assert s.delimitador.confianza == "inferred"
    assert "lineas_de_longitud_distinta" in codigos(s)
    assert "12 de 63" in dict((a.codigo, a.mensaje) for a in s.avisos)[
        "lineas_de_longitud_distinta"
    ]


def test_el_fichero_latin1_avisa_y_sigue() -> None:
    """E1.7 en su forma más pura: el fichero se lee entero, con los acentos
    puestos, y lo único que pasa es que la codificación queda `unknown` porque
    ninguna estructura distingue latin-1 de cp1252."""
    datos = (GENERICO / "10-latin1.csv").read_bytes()
    s = sondear(datos, tamano_total=len(datos))
    assert s.codificacion.confianza == "unknown"
    assert "codificacion_no_utf8" in codigos(s)
    assert "Presión_colector" in s.texto


# --------------------------------------------------------------------------- #
# 2. Los casos que se equivocan en silencio
# --------------------------------------------------------------------------- #
def test_el_delimitador_no_es_el_caracter_mas_frecuente() -> None:
    """El ejemplo del enunciado de FG-01, y el motivo de que §7.4 prohíba
    `csv.Sniffer`: hay ocho comas y seis puntos y coma, y el delimitador es el
    punto y coma. Contar caracteres da la respuesta contraria; contar
    consistencia del número de campos da la buena."""
    datos = (
        b'nombre;nota;rpm\r\n"a,b,c";"d,e";100\r\n"f,g,h";"i,j";200\r\n"k,l,m";"n,o";300\r\n'
    )
    s = sondear(datos, tamano_total=len(datos))
    assert datos.count(b",") > datos.count(b";")
    assert s.delimitador.valor == ";", s.resumen()
    assert s.comillas.valor == '"', s.resumen()
    assert s.n_campos == 3


def test_punto_y_coma_con_coma_decimal_no_se_confunde_con_coma() -> None:
    """El CSV español típico (§7.4 paso 4). La coma decimal deja cinco comas por
    fila de datos, MÁS que puntos y coma, y además de forma perfectamente
    consistente: lo único que separa a las dos hipótesis es la línea de
    cabecera, que no lleva ninguna coma.

    Por eso el veredicto es `inferred` y no `confirmed`, y por eso sale el aviso
    `delimitador_ambiguo`: el sondeo acierta, pero no puede demostrarlo con la
    tipografía sola. Quien lo confirma es la detección del separador decimal
    (FG-02). Si esta prueba se pusiera en `confirmed`, el aviso desaparecería y
    con él la única señal de que ese fichero merece una mirada.
    """
    datos = (
        "Time;RPM;MAP;TPS;CLT;Lambda\r\n"
        "0,000;1456;217,300;6,900;72,400;1,009\r\n"
        "0,050;4107;56,380;89,000;78,600;0,928\r\n"
        "0,100;5873;48,040;65,700;89,800;0,845\r\n"
    ).encode()
    s = sondear(datos, tamano_total=len(datos))
    assert s.delimitador.valor == ";", s.resumen()
    assert s.n_campos == 6
    assert s.delimitador.confianza == "inferred"
    assert "delimitador_ambiguo" in codigos(s)


def test_el_delimitador_dentro_de_un_campo_entrecomillado_no_cuenta() -> None:
    """`a,"b,c",d` son tres campos, no cuatro. Contar cuatro no rompe nada
    visible: corre una columna a la derecha y el log se importa con los canales
    desplazados, que es el fallo de importación más caro que hay."""
    datos = b'a,"b,c",d\r\ne,"f,g",h\r\ni,"j,k",l\r\n'
    s = sondear(datos, tamano_total=len(datos))
    assert s.delimitador.valor == ","
    assert s.comillas.valor == '"'
    assert s.n_campos == 3, s.resumen()


def test_un_salto_de_linea_dentro_de_comillas_no_parte_el_registro() -> None:
    """Un valor con salto de línea es un campo, no dos filas. Partir por él
    inventaría una fila corta y dejaría a la siguiente con campos de menos."""
    datos = b'a;b;c\r\n"x\r\ny";2;3\r\nd;e;f\r\n'
    s = sondear(datos, tamano_total=len(datos))
    assert s.delimitador.valor == ";", s.resumen()
    assert s.comillas.valor == '"', s.resumen()
    assert s.n_campos == 3
    assert s.puntuaciones[0].lineas_examinadas == 3


def test_una_comilla_que_no_delimita_campos_no_es_la_comilla_del_fichero() -> None:
    """`12" de llanta` lleva una comilla suelta. Tomarla por comilla de campo
    invertiría el estado «dentro/fuera» a partir de ahí y se comería los
    delimitadores del resto del fichero. Se avisa y se sigue sin comillas."""
    datos = 'rueda,ancho\r\n12" de llanta,205\r\n13" de llanta,215\r\n15,225\r\n'.encode()
    s = sondear(datos, tamano_total=len(datos))
    assert s.delimitador.valor == ","
    assert s.comillas.valor is None, s.resumen()
    assert "comillas_sueltas" in codigos(s)
    assert s.n_campos == 2


def test_un_apostrofo_en_el_texto_no_convierte_la_comilla_simple_en_delimitadora() -> None:
    datos = b"piloto,vuelta\r\nO'Brien,89.4\r\nD'Angelo,90.1\r\nSmith,88.7\r\n"
    s = sondear(datos, tamano_total=len(datos))
    assert s.delimitador.valor == ","
    assert s.comillas.valor is None, s.resumen()
    assert s.n_campos == 2


@pytest.mark.parametrize(
    ("codec", "bom"),
    [
        ("utf-16-le", True),
        ("utf-16-be", True),
        ("utf-16-le", False),
        ("utf-16-be", False),
    ],
)
def test_utf16_con_y_sin_bom(codec: str, bom: bool) -> None:
    """Un UTF-16 leído como latin-1 sale lleno de nulos y no parece un CSV: cero
    columnas y cero avisos útiles. Con BOM lo decide el BOM; sin BOM lo decide el
    patrón de bytes nulos en posiciones alternas, que es estructura pura."""
    texto = "Time,RPM,MAP\r\n0.000,850,32.6\r\n0.050,860,33.1\r\n0.100,870,34.0\r\n"
    boms = {"utf-16-le": b"\xff\xfe", "utf-16-be": b"\xfe\xff"}
    datos = (boms[codec] if bom else b"") + texto.encode(codec)
    s = sondear(datos, tamano_total=len(datos))
    assert s.codificacion.valor == codec, s.resumen()
    assert s.bytes_de_bom == (2 if bom else 0)
    assert s.texto == texto
    assert s.fin_de_linea.valor == "CRLF", s.resumen()
    assert s.delimitador.valor == ",", s.resumen()
    assert s.n_campos == 3


def test_el_bom_utf8_no_se_cuela_en_el_texto() -> None:
    """`docs/09` §9.10, la trampa de los desplazamientos: el contrato no debe
    obligar a acordarse del BOM. `texto` viene ya sin él y `bytes_de_bom` dice
    cuántos se descontaron, para quien tenga que volver a los bytes."""
    texto = "Time,RPM\r\n0.000,850\r\n0.050,860\r\n"
    datos = b"\xef\xbb\xbf" + texto.encode()
    s = sondear(datos, tamano_total=len(datos))
    assert s.codificacion.valor == "utf-8"
    assert s.codificacion.confianza == "confirmed"
    assert s.bytes_de_bom == 3
    assert s.texto == texto
    assert not s.texto.startswith("﻿")


def test_un_bom_utf32_no_se_lee_como_utf16() -> None:
    """El BOM de UTF-32 LE empieza por el de UTF-16 LE. Mirarlos en el orden
    equivocado produce texto plausible lleno de caracteres nulos, que es peor
    que no detectar nada."""
    texto = "a,b\r\n1,2\r\n3,4\r\n"
    datos = b"\xff\xfe\x00\x00" + texto.encode("utf-32-le")
    s = sondear(datos, tamano_total=len(datos))
    assert s.codificacion.valor == "utf-32-le"
    assert s.texto == texto
    assert s.delimitador.valor == ","


@pytest.mark.parametrize(
    ("eol", "esperado"),
    [("\r\n", "CRLF"), ("\n", "LF"), ("\r", "CR")],
)
def test_los_tres_finales_de_linea(eol: str, esperado: str) -> None:
    texto = eol.join(["a,b,c", "1,2,3", "4,5,6", "7,8,9"]) + eol
    datos = texto.encode()
    s = sondear(datos, tamano_total=len(datos))
    assert s.fin_de_linea.valor == esperado
    assert s.fin_de_linea.confianza == "confirmed"


def test_fin_de_linea_mixto_avisa_y_sigue() -> None:
    """Un fichero editado o concatenado a mano. No es motivo para no leerlo,
    pero sí para decirlo: mezclar finales de línea suele venir acompañado de
    otras cosas hechas a mano."""
    datos = b"a,b,c\r\n1,2,3\n4,5,6\r\n7,8,9\n"
    s = sondear(datos, tamano_total=len(datos))
    assert s.fin_de_linea.valor == "mixto"
    assert "fin_de_linea_mixto" in codigos(s)
    assert s.delimitador.valor == ","
    assert s.n_campos == 3


def test_una_sola_linea_propone_pero_no_confirma() -> None:
    """Hay comas, y probablemente el delimitador sea la coma. Pero la evidencia
    de este módulo es la CONSISTENCIA entre líneas, y con una sola línea esa
    evidencia no existe: no hay con qué comprobar que el número de campos se
    mantiene. Confianza `unknown` y que pregunte el asistente."""
    datos = b"a,b,c,d"
    s = sondear(datos, tamano_total=len(datos))
    assert s.delimitador.valor == ","
    assert s.delimitador.confianza == "unknown"
    assert "sin_evidencia_de_consistencia" in codigos(s)
    assert "sin_fin_de_linea" in codigos(s)


def test_un_fichero_de_una_sola_columna_no_inventa_delimitador() -> None:
    """§7.10: se carga igual. Lo que no se puede hacer es elegir el candidato
    «menos malo» y partir en columnas que no existen."""
    datos = b"850\r\n860\r\n870\r\n880\r\n"
    s = sondear(datos, tamano_total=len(datos))
    assert s.delimitador.valor is None
    assert s.delimitador.confianza == "unknown"
    assert "sin_delimitador" in codigos(s)
    assert s.puntuaciones == ()
    assert s.n_campos is None


def test_la_muestra_vacia_no_revienta() -> None:
    s = sondear(b"")
    assert s.texto == ""
    assert s.delimitador.valor is None
    assert "muestra_vacia" in codigos(s)


def test_el_espacio_solo_se_propone_si_no_hay_nada_mejor() -> None:
    """Los dos lados de la regla.

    Un fichero separado por espacios se detecta, con `inferred` porque el
    espacio también separa palabras dentro de un campo. Y un fichero con
    preámbulo `clave : valor` —donde el espacio parece un delimitador de tres
    columnas perfectamente consistente— NO se detecta como separado por
    espacios: gana la coma, que es la que parte las filas de datos.
    """
    espacios = b"t rpm map\r\n0.0 850 32.6\r\n0.1 860 33.1\r\n0.2 870 34.0\r\n"
    s = sondear(espacios, tamano_total=len(espacios))
    assert s.delimitador.valor == " ", s.resumen()
    assert s.delimitador.confianza == "inferred"

    con_preambulo = (
        b"vehicle : Track car\r\nengine : 2000cc turbo\r\ndriver : John Doe\r\n"
        b"t,rpm,map\r\n0.0,850,32.6\r\n0.1,860,33.1\r\n0.2,870,34.0\r\n"
    )
    s = sondear(con_preambulo, tamano_total=len(con_preambulo))
    assert s.delimitador.valor == ",", s.resumen()
    assert s.n_campos == 3


def test_la_cabecera_de_un_haltech_real_no_se_da_por_buena() -> None:
    """Los primeros 64 kB del AutoLog de 475 canales son cabecera ENTERA: no hay
    ni una fila de datos donde mirar. El camino nativo lo resuelve por firma
    (`%DataLog%`) y este módulo no llega a verlo, pero si algún día llegara, lo
    que no puede hacer es proponer un delimitador con confianza alta a partir de
    líneas `Channel : Coolant Temperature`. Con el espacio puntuando de igual a
    igual, ese fichero salía con delimitador ' ' y tres columnas."""
    datos = (REAL / "AutoLog_20260729_1830.csv").read_bytes()
    s = sondear(datos)
    assert s.muestra_truncada
    assert s.delimitador.valor != " ", s.resumen()
    assert not s.delimitador.es_fiable, s.resumen()


def test_una_muestra_truncada_por_la_mitad_de_una_linea_no_pierde_confianza() -> None:
    """El corte de los 64 kB cae donde cae. Si la última línea, cortada a medias,
    contara como línea en desacuerdo, un fichero perfectamente regular saldría
    con confianza rebajada por un accidente del tamaño de la muestra."""
    fichero = ("a,b,c\r\n" + "1,2,3\r\n" * 20_000).encode()
    assert len(fichero) > LIMITE_MUESTRA
    s = sondear(fichero[:LIMITE_MUESTRA], tamano_total=len(fichero))
    assert s.muestra_truncada
    assert s.delimitador.valor == ","
    assert s.delimitador.confianza == "confirmed", s.resumen()
    assert s.n_campos == 3
    # Y la codificación baja a `inferred` justo por lo contrario: solo se ha
    # visto ASCII, y el primer acento del fichero podría estar más allá del corte.
    assert s.codificacion.confianza == "inferred"


def test_el_resumen_lleva_las_cuatro_decisiones_con_su_evidencia() -> None:
    """La puerta es G1: el propietario tiene que poder revisar POR QUÉ se decidió
    cada cosa sin abrir el código."""
    datos = (GENERICO / "02-puntoycoma-coma.csv").read_bytes()
    resumen = sondear(datos, tamano_total=len(datos)).resumen()
    for aspecto in ("codificacion", "fin_de_linea", "delimitador", "comillas"):
        assert aspecto in resumen
    assert "51 de 51 líneas" in resumen
    assert "confirmed" in resumen and "inferred" in resumen


def test_el_sondeo_no_es_un_coste_perceptible() -> None:
    """El presupuesto de apertura es de 4 s (§2.6) y el sondeo es lo primero que
    corre. Con máscaras de NumPy sobre 64 kB son décimas de milisegundo; este
    límite tan holgado no mide rendimiento, solo detecta que alguien haya
    sustituido el recuento vectorizado por un bucle sobre caracteres."""
    fichero = ("a,b,c,d,e,f\r\n" + "1,2,3,4,5,6\r\n" * 20_000).encode()[:LIMITE_MUESTRA]
    inicio = time.perf_counter()
    sondear(fichero)
    assert (time.perf_counter() - inicio) < 0.1


# --------------------------------------------------------------------------- #
# 3. Propiedades
# --------------------------------------------------------------------------- #
@settings(max_examples=500, deadline=None)
@given(st.binary(min_size=0, max_size=600))
def test_bytes_arbitrarios_no_hacen_escapar_nada(datos: bytes) -> None:
    """La propiedad principal. El sondeo es una PROPUESTA (§7.4): no hay ningún
    fichero que pueda rechazar, porque no llega a interpretar ni un valor. Así
    que la única salida legítima es un `Sondeo`, y cualquier excepción que se
    escape llegaría a la interfaz como una traza donde tenía que haber un
    formulario relleno con lo que se ha podido deducir."""
    try:
        s = sondear(datos)
    except Exception as error:  # noqa: BLE001 - cazarlo TODO es la prueba
        raise AssertionError(
            f"sondear dejó escapar {type(error).__name__}: {error}\n"
            f"Con estos bytes: {datos[:200]!r}"
        ) from error
    assert isinstance(s.texto, str)
    assert s.delimitador.valor is None or s.delimitador.valor in CANDIDATOS_DELIMITADOR


@settings(max_examples=300, deadline=None)
@given(st.binary(min_size=0, max_size=400))
def test_el_texto_devuelto_no_lleva_bom(datos: bytes) -> None:
    assume(datos)
    assert not sondear(datos).texto.startswith("﻿")


# --- Generador de CSV bien formados ---------------------------------------- #
# El alfabeto de los campos es ASCII alfanumérico a propósito: sin ninguno de
# los cinco delimitadores candidatos dentro, el fichero generado tiene UNA sola
# lectura posible y la propiedad puede exigir el acierto exacto. Los campos con
# delimitadores dentro se prueban aparte, en la propiedad de `confirmed`, porque
# ahí el fichero SÍ puede ser genuinamente ambiguo y lo que se exige es otra cosa.
campos_sin_delimitadores = st.text(
    alphabet=st.characters(min_codepoint=48, max_codepoint=122, whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=0,
    max_size=8,
)

CODIFICACIONES = ["utf-8", "utf-8-sig", "utf-16-le-bom", "utf-16-be-bom", "utf-16-le"]


@dataclass(frozen=True)
class ModeloCsv:
    filas: tuple[tuple[str, ...], ...]
    delimitador: str
    comilla: str | None
    fin_de_linea: str
    codificacion: str
    salto_final: bool


@st.composite
def modelos_csv(
    dibujar: st.DrawFn,
    *,
    campos: st.SearchStrategy[str] = campos_sin_delimitadores,
    min_filas: int = 3,
) -> ModeloCsv:
    n_columnas = dibujar(st.integers(2, 6))
    n_filas = dibujar(st.integers(min_filas, 10))
    filas = tuple(
        tuple(dibujar(st.lists(campos, min_size=n_columnas, max_size=n_columnas)))
        for _ in range(n_filas)
    )
    return ModeloCsv(
        filas=filas,
        delimitador=dibujar(st.sampled_from(CANDIDATOS_DELIMITADOR)),
        comilla=dibujar(st.sampled_from([None, '"', "'"])),
        fin_de_linea=dibujar(st.sampled_from(["\r\n", "\n"])),
        codificacion=dibujar(st.sampled_from(CODIFICACIONES)),
        salto_final=dibujar(st.booleans()),
    )


def texto_de(modelo: ModeloCsv) -> str:
    def campo(valor: str) -> str:
        return valor if modelo.comilla is None else f"{modelo.comilla}{valor}{modelo.comilla}"

    lineas = [modelo.delimitador.join(campo(v) for v in fila) for fila in modelo.filas]
    return modelo.fin_de_linea.join(lineas) + (modelo.fin_de_linea if modelo.salto_final else "")


def bytes_de(modelo: ModeloCsv) -> bytes:
    texto = texto_de(modelo)
    if modelo.codificacion == "utf-8":
        return texto.encode()
    if modelo.codificacion == "utf-8-sig":
        return b"\xef\xbb\xbf" + texto.encode()
    if modelo.codificacion == "utf-16-le-bom":
        return b"\xff\xfe" + texto.encode("utf-16-le")
    if modelo.codificacion == "utf-16-be-bom":
        return b"\xfe\xff" + texto.encode("utf-16-be")
    return texto.encode("utf-16-le")


@AJUSTES
@given(modelos_csv())
def test_un_csv_bien_formado_se_sondea_exacto(modelo: ModeloCsv) -> None:
    """Ida y vuelta sobre las cinco variables a la vez: delimitador, comilla,
    fin de línea, codificación y salto final. Son accidentes de quién exportó el
    fichero, y ninguna combinación de ellos debe cambiar lo que se lee."""
    datos = bytes_de(modelo)
    s = sondear(datos, tamano_total=len(datos))
    assert s.texto == texto_de(modelo)
    assert s.delimitador.valor == modelo.delimitador, s.resumen()
    assert s.n_campos == len(modelo.filas[0]), s.resumen()
    assert s.fin_de_linea.valor == ("CRLF" if modelo.fin_de_linea == "\r\n" else "LF")


@AJUSTES
@given(modelos_csv())
def test_las_comillas_se_detectan_cuando_delimitan_campos(modelo: ModeloCsv) -> None:
    """Con campos vacíos y comillas puestas, `""` es un campo entrecomillado
    vacío; sin comillas no debe inventarse ninguna."""
    datos = bytes_de(modelo)
    s = sondear(datos, tamano_total=len(datos))
    assert s.comillas.valor == modelo.comilla, s.resumen()


# --- La propiedad que protege al usuario ------------------------------------ #
campos_con_delimitadores = st.text(
    alphabet=st.characters(
        min_codepoint=32,
        max_codepoint=122,
        blacklist_characters="\"'\\",
    ),
    min_size=0,
    max_size=10,
)


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(modelos_csv(campos=campos_con_delimitadores))
def test_confirmed_no_miente_nunca(modelo: ModeloCsv) -> None:
    """Aquí los campos SÍ llevan comas, puntos y coma, tabuladores y espacios
    dentro, así que hay ficheros genuinamente ambiguos: `a,b;a,b` es un fichero
    de dos columnas separadas por `;` o de tres separadas por `,`, y no hay
    forma tipográfica de saberlo.

    Lo que se exige no es acertar siempre —eso no es posible—, sino **no decir
    `confirmed` cuando no se puede demostrar**. Un `inferred` equivocado lo
    corrige el usuario en el paso 1 del asistente, que se lo enseña relleno y
    editable; un `confirmed` equivocado se precarga sin que nadie lo mire.
    """
    assume(modelo.comilla is not None)  # sin comillas, un campo con el delimitador dentro
    # es indistinguible de dos campos, y el fichero deja de tener una lectura verdadera.
    datos = bytes_de(modelo)
    s = sondear(datos, tamano_total=len(datos))
    if s.delimitador.confianza == "confirmed":
        assert s.delimitador.valor == modelo.delimitador, s.resumen()
        assert s.n_campos == len(modelo.filas[0]), s.resumen()
