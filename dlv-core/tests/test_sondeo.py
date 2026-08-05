"""Pruebas del sondeo de CSV desconocido (tarea FG-01).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.4, pasos 1, 2, 3 y 5.

QUÉ PROTEGE ESTA SUITE
======================
El paso 4 de §7.4 —el separador decimal— es de FG-02, pero su fallo empieza
aquí: si el sondeo propone `,` para un CSV español que usa `;` con coma decimal,
`12,5` se parte en dos columnas y el log entero sale con el doble de canales y
la mitad de los valores. §7.4 dice que es «el que más a menudo se hace mal y el
más importante en Europa».

De ahí el orden de las pruebas:

1. **El corpus real de `samples/generico/`**, los 14 ficheros, uno por uno. Es
   la prueba que ata el módulo a ficheros que existen en el repositorio.
2. **El CSV español** (`;` + coma decimal) tiene que dar `;`. Es el caso que
   `csv.Sniffer` falla y por el que §7.4 lo descarta por nombre.
3. **El preámbulo no puede cambiar el ganador.** Cinco líneas de `clave: valor`
   delante de los datos son un bloque de una sola columna: puntuar por
   uniformidad global penalizaría al delimitador correcto.
4. **La truncación no puede cambiar la codificación.** Un corte en medio de una
   «ñ» declararía latin-1 un fichero UTF-8 válido, y todos los nombres con
   acentos saldrían mal.
5. **Antes «no sé» que una propuesta que parte mal los datos.**

Solo biblioteca estándar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlv_core.formatos.sondeo import (
    CONFIANZA_MINIMA,
    ErrorDeSondeo,
    Escape,
    FinDeLinea,
    sondear_csv,
)

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
DOS_FORMATOS = RAIZ / "samples" / "dos-formatos"
REALES = RAIZ / "samples" / "real"


def bytes_de(ruta: Path) -> bytes:
    return ruta.read_bytes()


# --------------------------------------------------------------------------- #
# El corpus real, fichero por fichero
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("fichero", "delimitador", "n_campos"),
    [
        ("01-coma-punto.csv", ",", 6),
        ("02-puntoycoma-coma.csv", ";", 6),
        ("03-tabulaciones.csv", "\t", 6),
        ("04-fila-de-unidades.csv", ",", 6),
        ("05-unidad-en-el-nombre.csv", ",", 6),
        ("06-sin-columna-de-tiempo.csv", ",", 6),
        ("07-epoch-segundos.csv", ",", 6),
        ("08-epoch-milisegundos.csv", ",", 6),
        ("09-iso8601.csv", ",", 6),
        ("10-latin1.csv", ",", 6),
        ("11-valores-ausentes.csv", ",", 6),
        ("12-texto-y-booleanos.csv", ",", 6),
        ("13-columnas-duplicadas.csv", ",", 6),
        ("14-preambulo-largo.csv", ",", 6),
    ],
)
def test_corpus_generico(fichero: str, delimitador: str, n_campos: int) -> None:
    """Los 14 ficheros de `samples/generico/`, con su delimitador esperado.

    Si uno falla, el módulo ha dejado de servir para un caso que el propietario
    ya tiene en el repositorio, no para uno hipotético.
    """
    s = sondear_csv(bytes_de(GENERICOS / fichero))
    assert s.delimitador == delimitador, f"{fichero}: candidatos {s.candidatos[:3]}"
    assert s.n_campos == n_campos, fichero


def test_el_csv_espanol_da_puntoycoma_y_no_coma() -> None:
    """El caso que §7.4 llama «el más importante en Europa».

    `02-puntoycoma-coma.csv` es `;` con coma decimal. Leído con `,`, la cabecera
    tiene 6 campos y cada fila de datos 11, porque cada `0,050` se parte en dos.
    Es lo que `csv.Sniffer` hace mal y por lo que §7.4 lo descarta.
    """
    s = sondear_csv(bytes_de(GENERICOS / "02-puntoycoma-coma.csv"))
    assert s.delimitador == ";"
    assert s.n_campos == 6
    assert s.confianza == 1.0

    # Este fichero es más traicionero de lo que parece, y por eso es el bueno para
    # esta prueba. La coma aparece MÁS veces que el punto y coma —una por cada
    # decimal— y además, por casualidad de este fixture, cada fila de datos tiene
    # cinco decimales, así que leída con `,` da SEIS campos: exactamente los mismos
    # que la lectura correcta. Las dos interpretaciones dan 6 campos y las dos
    # tienen consistencia 1,0.
    #
    # Lo único que las distingue es que la racha de la coma **empieza en la línea
    # 1**: deja la cabecera fuera, porque `Time;RPM;...` no tiene ninguna coma. La
    # del punto y coma empieza en la 0 e incluye la fila de nombres. La
    # interpretación correcta es la que hace que la cabecera cuadre con los datos, y
    # eso es lo que mide la longitud de la racha. Ni la frecuencia de caracteres ni
    # el número de campos habrían decidido este caso.
    por_coma = next(c for c in s.candidatos if c.delimitador == "," and c.comilla is None)
    por_puntoycoma = next(c for c in s.candidatos if c.delimitador == ";")
    assert por_coma.n_campos == por_puntoycoma.n_campos == 6, "las dos dan 6 campos"
    assert por_coma.consistencia == 1.0, "y las dos son perfectamente consistentes"
    assert por_coma.linea_inicio == 1, "la racha de la coma empieza DESPUÉS de la cabecera"
    assert por_puntoycoma.linea_inicio == 0, "la del punto y coma incluye la cabecera"
    assert por_puntoycoma.lineas_consistentes == por_coma.lineas_consistentes + 1
    assert por_coma.clave_de_orden < s.candidatos[0].clave_de_orden


def test_el_preambulo_no_cambia_el_ganador() -> None:
    """Doce líneas de `clave: valor` delante de los datos (§7.4 paso 7).

    Son un bloque de una sola columna. Puntuar por la moda global penalizaría al
    delimitador correcto por culpa del preámbulo, que es justo lo que FG-03 va a
    separar después. La puntuación por racha lo resuelve: consistencia 1,0 desde
    donde empiezan los datos, y la cobertura por debajo de 1 es lo que delata que
    hay algo delante.
    """
    s = sondear_csv(bytes_de(GENERICOS / "14-preambulo-largo.csv"))
    assert s.delimitador == ","
    assert s.n_campos == 6
    assert s.confianza == 1.0, "desde donde empiezan los datos, es perfecto"
    assert s.elegido is not None and s.elegido.cobertura < 1.0, "y hay algo delante"
    assert s.linea_inicio_datos == 12, "las 12 líneas de metadatos del fichero"
    assert "campos_inconsistentes" in {a.codigo for a in s.avisos}
    assert "FG-03" in next(a.mensaje for a in s.avisos if a.codigo == "campos_inconsistentes"), (
        "el aviso tiene que decir qué tarea separa el preámbulo"
    )


@pytest.mark.parametrize(
    ("fichero", "n_campos", "inicio"),
    [("20260729_1859_Log2768.csv", 26, 108), ("AutoLog_20260729_1830.csv", 476, 1895)],
)
def test_los_logs_nativos_reales_se_sondean_por_el_camino_generico(
    fichero: str, n_campos: int, inicio: int
) -> None:
    """El camino genérico tiene que funcionar sobre un Haltech real.

    No es su camino —para eso está el descriptor de F1-01— pero es la red de
    seguridad de §7.15: si algún día el descriptor no reconoce una variante, el
    fichero sigue siendo un CSV con comas.

    El AutoLog es el caso que rompió la primera versión: sus 475 canales dan 1 895
    líneas de cabecera, así que con un límite de 200 líneas la muestra era toda
    cabecera y el sondeo decía «no sé». Los datos empiezan en el byte 42 345,
    dentro de los 64 kB: era el límite de líneas, no el de bytes.
    """
    s = sondear_csv(bytes_de(REALES / fichero))
    assert s.delimitador == ","
    assert s.n_campos == n_campos, "la marca de tiempo más los canales"
    assert s.linea_inicio_datos == inicio, "dónde acaba la cabecera del formato"
    assert s.confianza == 1.0
    assert s.fin_de_linea is FinDeLinea.CRLF, "el formato nativo es CRLF (§1.13)"


def test_truncado_dice_si_el_sondeo_vio_todo_el_fichero() -> None:
    """De los tres logs reales solo el AutoLog (4,5 MB) pasa de 64 kB.

    `truncado` es lo que explica que una propuesta pueda fallar más adelante: con
    el fichero entero delante, lo que el sondeo dice es lo que hay.
    """
    assert sondear_csv(bytes_de(REALES / "AutoLog_20260729_1830.csv")).truncado is True
    assert sondear_csv(bytes_de(REALES / "20260729_1859_Log2768.csv")).truncado is False


def test_el_par_de_f0_13_se_sondea_cada_uno_con_su_delimitador() -> None:
    """El mismo log en dos formatos: el nativo es `,` y el genérico es `;`.

    Es la prueba de independencia de fabricante en miniatura: dos ficheros con los
    mismos datos y convenciones distintas, y el sondeo acierta con los dos sin que
    nadie le diga cuál es cuál.
    """
    nativo = sondear_csv(bytes_de(DOS_FORMATOS / "nativo.csv"))
    generico = sondear_csv(bytes_de(DOS_FORMATOS / "generico.csv"))
    assert nativo.delimitador == ","
    assert generico.delimitador == ";"
    assert nativo.n_campos == generico.n_campos, "los mismos datos, los mismos campos"


# --------------------------------------------------------------------------- #
# Codificación
# --------------------------------------------------------------------------- #
def test_utf8_sin_bom() -> None:
    s = sondear_csv("Tiempo,Régimen\n0.0,1000\n".encode())
    assert (s.codificacion, s.tiene_bom) == ("utf-8", False)
    assert s.avisos == ()


def test_bom_utf8() -> None:
    s = sondear_csv(b"\xef\xbb\xbf" + b"Time,RPM\n0.0,1000\n")
    assert (s.codificacion, s.tiene_bom) == ("utf-8-sig", True)
    assert s.delimitador == ","


def test_bom_utf16() -> None:
    """Sin detectar el BOM, un UTF-16 se leería como latin-1 y cada carácter
    saldría seguido de un byte nulo: el delimitador no aparecería nunca."""
    s = sondear_csv("Time,RPM\n0.0,1000\n".encode("utf-16"))
    assert s.codificacion == "utf-16" and s.tiene_bom
    assert s.delimitador == ","
    assert s.n_campos == 2


def test_latin1_se_lee_y_se_avisa() -> None:
    """El fichero 10 del corpus tiene nombres con acentos en latin-1.

    Latin-1 nunca falla —los 256 bytes son válidos— así que no es una detección,
    es una rendición, y el usuario tiene que enterarse para poder cambiarla.
    """
    s = sondear_csv(bytes_de(GENERICOS / "10-latin1.csv"))
    assert s.codificacion == "latin-1"
    assert "codificacion_supuesta" in {a.codigo for a in s.avisos}
    assert s.delimitador == ","


def test_la_truncacion_no_cambia_la_codificacion_detectada() -> None:
    """La regla 4 de esta suite.

    Se corta a propósito por la mitad de una «ñ» (dos bytes en UTF-8). Sin
    recortar la cola incompleta, el fichero se declararía latin-1 por el corte y
    no por su contenido, y todos los nombres de canal con acentos saldrían mal.
    """
    contenido = "Tiempo,Presión\n" + "".join(f"{i / 10:.1f},1.0\n" for i in range(50))
    crudo = contenido.encode("utf-8")
    # Buscar un corte que caiga en medio del carácter multibyte de «Presión».
    posicion = crudo.index("ó".encode()) + 1
    with pytest.raises(UnicodeDecodeError):
        crudo[:posicion].decode("utf-8")

    s = sondear_csv(crudo, max_bytes=posicion)
    assert s.codificacion == "utf-8", "el corte no puede decidir la codificación"
    assert s.truncado is True
    assert "codificacion_supuesta" not in {a.codigo for a in s.avisos}


def test_un_fichero_vacio_es_un_error_con_nombre() -> None:
    with pytest.raises(ErrorDeSondeo, match="vacío"):
        sondear_csv(b"")


def test_un_fichero_de_solo_saltos_es_un_error_con_nombre() -> None:
    with pytest.raises(ErrorDeSondeo, match="ninguna línea con contenido"):
        sondear_csv(b"\n\n   \n\n")


# --------------------------------------------------------------------------- #
# Fin de línea
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("salto", "esperado"),
    [("\r\n", FinDeLinea.CRLF), ("\n", FinDeLinea.LF), ("\r", FinDeLinea.CR)],
)
def test_los_tres_finales_de_linea(salto: str, esperado: FinDeLinea) -> None:
    datos = salto.join(["Time,RPM", "0.0,1000", "0.1,1100", ""]).encode()
    s = sondear_csv(datos)
    assert s.fin_de_linea is esperado
    assert s.finales_mezclados is False
    assert s.delimitador == ","


def test_finales_mezclados_se_avisan_y_gana_el_mayoritario() -> None:
    """Suele significar que el log se editó con dos herramientas distintas."""
    datos = b"Time,RPM\r\n0.0,1000\r\n0.1,1100\n0.2,1200\r\n"
    s = sondear_csv(datos)
    assert s.fin_de_linea is FinDeLinea.CRLF
    assert s.finales_mezclados is True
    assert "finales_de_linea_mezclados" in {a.codigo for a in s.avisos}


def test_una_sola_linea_sin_salto_final() -> None:
    """Caso válido de §1.13: no hay saltos, así que no hay nada que partir."""
    s = sondear_csv(b"Time,RPM,MAP")
    assert s.fin_de_linea is FinDeLinea.LF
    assert s.finales_mezclados is False
    assert s.delimitador == "," and s.n_campos == 3


def test_la_ultima_linea_cortada_no_penaliza_al_delimitador() -> None:
    """Un sondeo truncado casi siempre corta la última línea a medias, y una
    línea a medias tiene menos campos: dejarla dentro penalizaría al delimitador
    correcto justo en los ficheros grandes, que son todos los reales."""
    completo = "Time,RPM,MAP\n" + "".join(f"{i / 10:.1f},1000,50.0\n" for i in range(30))
    cortado = completo[: completo.index("\n", 200) + 8]  # se para en mitad de una fila
    s = sondear_csv(cortado.encode())
    assert s.delimitador == ","
    assert s.n_campos == 3
    assert s.confianza == 1.0, "la línea a medias no debería contar"


# --------------------------------------------------------------------------- #
# Comillas y escapes
# --------------------------------------------------------------------------- #
def test_un_campo_entrecomillado_con_el_delimitador_dentro() -> None:
    """Sin conteo consciente de comillas, esta línea tendría 4 campos y una sola
    línea así basta para cambiar el ganador en un fichero corto."""
    datos = (
        b"Time,Nombre,RPM\n"
        b'0.0,"Sensor A, trasero",1000\n'
        b'0.1,"Sensor B, delantero",1100\n'
        b'0.2,"Sensor C, lateral",1200\n'
    )
    s = sondear_csv(datos)
    assert s.delimitador == ","
    assert s.comilla == '"'
    assert s.n_campos == 3
    assert s.confianza == 1.0


def test_comilla_simple() -> None:
    datos = (
        b"Time,Nombre,RPM\n"
        b"0.0,'Sensor A, trasero',1000\n"
        b"0.1,'Sensor B, delantero',1100\n"
        b"0.2,'Sensor C, lateral',1200\n"
    )
    s = sondear_csv(datos)
    assert (s.delimitador, s.comilla, s.n_campos) == (",", "'", 3)


def test_escape_por_comilla_doblada() -> None:
    datos = b'Time,Nombre\n0.0,"Sensor ""A"", trasero"\n0.1,"Sensor ""B"", delantero"\n'
    s = sondear_csv(datos)
    assert s.comilla == '"'
    assert s.escape is Escape.DOBLADA
    assert s.n_campos == 2


def test_escape_por_barra_invertida() -> None:
    datos = b'Time,Nombre\n0.0,"Sensor \\"A\\", trasero"\n0.1,"Sensor \\"B\\", lateral"\n'
    s = sondear_csv(datos)
    assert s.comilla == '"'
    assert s.escape is Escape.BARRA


def test_sin_comillas_el_escape_es_ninguno() -> None:
    s = sondear_csv(bytes_de(GENERICOS / "01-coma-punto.csv"))
    assert s.comilla is None
    assert s.escape is Escape.NINGUNO


def test_una_comilla_suelta_en_un_nombre_no_convierte_el_fichero_en_entrecomillado() -> None:
    """Por eso `None` va primero en los candidatos de comilla.

    «Sensor "A"» en un nombre de canal es texto, no un campo entrecomillado: si el
    sondeo propusiera comillas, el nombre perdería las suyas al leerlo.
    """
    datos = b'Time,Sensor "A",RPM\n0.0,1.0,1000\n0.1,2.0,1100\n0.2,3.0,1200\n'
    s = sondear_csv(datos)
    assert s.delimitador == "," and s.n_campos == 3
    assert s.comilla is None


# --------------------------------------------------------------------------- #
# Antes «no sé» que una propuesta equivocada
# --------------------------------------------------------------------------- #
def test_un_fichero_de_una_sola_columna_no_propone_delimitador() -> None:
    """La regla 5. Proponer un delimitador que parte los datos mal es peor que
    admitir que no se sabe: el asistente puede preguntar, un dato partido no."""
    datos = b"Valor\n1000\n1100\n1200\n1300\n"
    s = sondear_csv(datos)
    assert s.delimitador is None
    assert s.n_campos == 1
    assert "delimitador_sin_determinar" in {a.codigo for a in s.avisos}
    assert s.confianza >= 0.0


def test_un_fichero_incoherente_no_propone_delimitador() -> None:
    datos = b"a,b\nc,d,e\nf,g,h,i\nj\nk,l,m,n,o\n"
    s = sondear_csv(datos)
    assert s.delimitador is None or s.confianza < CONFIANZA_MINIMA
    assert "delimitador_sin_determinar" in {a.codigo for a in s.avisos}


def test_mas_campos_desempata_a_favor_de_la_interpretacion_informativa() -> None:
    """`Time;RPM` con `,` da 1 campo perfectamente consistente y con `;` da 2.

    Las dos son «consistentes»; solo una separa los datos. Sin el desempate por
    número de campos, el sondeo podría quedarse con la que no separa nada.
    """
    datos = b"Time;RPM\n0.0;1000\n0.1;1100\n"
    s = sondear_csv(datos)
    assert s.delimitador == ";" and s.n_campos == 2


def test_los_candidatos_se_devuelven_para_que_el_asistente_los_ensene() -> None:
    """§7.4: «la detección es una propuesta, no un hecho».

    El asistente tiene que poder enseñar por qué propone `;` y no `,`, y el
    usuario tiene que poder discrepar con información delante.
    """
    s = sondear_csv(bytes_de(GENERICOS / "02-puntoycoma-coma.csv"))
    # Cinco y no quince: el fichero no tiene ninguna comilla, así que las
    # combinaciones entrecomilladas darían exactamente el mismo recuento y no se
    # calculan. No es una poda heurística, es que son redundantes.
    assert len(s.candidatos) == 5, "los 5 delimitadores, sin variantes de comilla"
    assert s.candidatos[0].delimitador == ";"
    ordenadas = [c.clave_de_orden for c in s.candidatos]
    assert ordenadas == sorted(ordenadas, reverse=True), "vienen ya ordenadas"


def test_el_resultado_es_reproducible() -> None:
    """Dos sondeos del mismo fichero dan exactamente lo mismo, candidatos
    incluidos: nada puede depender del orden de un diccionario."""
    datos = bytes_de(GENERICOS / "14-preambulo-largo.csv")
    a, b = sondear_csv(datos), sondear_csv(datos)
    assert a == b


def test_los_parametros_de_lectura_no_mencionan_ningun_motor() -> None:
    """ADR-002: `dlv-core` no conoce Polars. Quien lea traduce."""
    s = sondear_csv(bytes_de(GENERICOS / "01-coma-punto.csv"))
    p = s.parametros_de_lectura
    assert set(p) == {"codificacion", "delimitador", "comilla", "fin_de_linea"}
    assert p["delimitador"] == "," and p["fin_de_linea"] == "\n"


# --------------------------------------------------------------------------- #
# Lo que §7.4 descarta por nombre
# --------------------------------------------------------------------------- #
def test_el_modulo_no_usa_csv_sniffer() -> None:
    """§7.4 lo descarta por nombre: es poco fiable con estos ficheros.

    Usar `Sniffer` no rompería ninguna prueba funcional con el corpus de hoy
    —acierta en los casos fáciles— y solo fallaría con el CSV español de un
    usuario. Lo único que lo detecta es buscarlo.

    Se busca sobre el ÁRBOL SINTÁCTICO y no sobre el texto, y es la misma lección
    que ya se pagó con el detector de ADR-009: la primera versión de esta prueba
    quitaba los comentarios `#` a mano y fallaba contra el propio módulo, porque su
    docstring cita `csv.Sniffer` justamente para explicar por qué no se usa. Un
    detector que se marca a sí mismo se acaba desactivando.
    """
    import ast

    fuente = (RAIZ / "dlv-core" / "src" / "dlv_core" / "formatos" / "sondeo.py").read_text(
        encoding="utf-8"
    )
    arbol = ast.parse(fuente)
    nombres = {
        nodo.attr if isinstance(nodo, ast.Attribute) else nodo.id
        for nodo in ast.walk(arbol)
        if isinstance(nodo, (ast.Attribute, ast.Name))
    }
    assert "Sniffer" not in nombres, "§7.4 descarta csv.Sniffer: puntúa por frecuencia"
    importados = {
        alias.name.split(".")[0]
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Import)
        for alias in nodo.names
    } | {
        nodo.module.split(".")[0]
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom) and nodo.module is not None
    }
    assert "csv" not in importados, "el módulo `csv` no hace falta y su Sniffer está vetado"


def test_el_modulo_no_decide_el_separador_decimal() -> None:
    """El paso 4 de §7.4 es FG-02, y colarlo aquí lo dejaría sin la verificación
    cruzada de interpretaciones que esa tarea exige."""
    s = sondear_csv(bytes_de(GENERICOS / "02-puntoycoma-coma.csv"))
    assert not hasattr(s, "separador_decimal")
    assert "decimal" not in s.parametros_de_lectura
