"""Pruebas del reparto de líneas de un CSV genérico (tarea FG-03).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.4, pasos 6 y 7.

QUÉ PROTEGE ESTA SUITE
======================
Confundir la fila de nombres con una fila de datos mete `Time`, `RPM` y `MAP`
como si fueran muestras. Con suerte revienta el parseo; sin suerte, el canal se
queda con una primera muestra basura y un mínimo o un máximo absurdo que
contamina la autoescala, el índice y cualquier detector de picos. Y al revés:
tomar la primera fila de datos por la cabecera pierde una muestra y bautiza todos
los canales con números.

Cuatro reglas, por consecuencia:

1. **El inicio del bloque consistente NO es el inicio de los datos.** FG-01
   devuelve dónde empieza el bloque de líneas con el mismo número de campos, y la
   fila de nombres está DENTRO de ese bloque: para eso es una cabecera.
2. **«Numérico» tiene que significar lo mismo que en FG-02.** Con el separador
   decimal equivocado, `0,050;1456` no es numérico y la primera fila de datos
   parece otra cabecera.
3. **La fila de unidades es una heurística y se declara como tal.**
4. **Los nombres no se inventan ni se renombran.** Un `col_3` en `nombres` sería
   indistinguible de un fichero que llama `col_3` a una columna, y renombrar un
   duplicado a `RPM_2` inventa un nombre que el usuario no reconoce.

Solo biblioteca estándar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlv_core.formatos.decimal_csv import detectar_separador_decimal
from dlv_core.formatos.estructura import (
    FRACCION_NUMERICA_MINIMA,
    ErrorDeEstructura,
    analizar_estructura,
    parece_marca_de_tiempo,
)
from dlv_core.formatos.sondeo import sondear_csv

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
DOS_FORMATOS = RAIZ / "samples" / "dos-formatos"
REALES = RAIZ / "samples" / "real"


def analizar(datos: bytes) -> object:
    """La cadena completa: FG-01, FG-02 y FG-03 sobre los mismos bytes.

    Se ejercita entera a propósito. Las tres tareas se usan siempre juntas, y un
    fallo en la costura entre ellas —el separador decimal que no llega, el
    delimitador que se recalcula— no lo vería ninguna prueba que las mirara por
    separado.
    """
    s = sondear_csv(datos)
    texto = datos.decode(s.codificacion)
    d = detectar_separador_decimal(s, texto)
    return analizar_estructura(s, d, texto)


def de(ruta: Path) -> object:
    return analizar(ruta.read_bytes())


def codigos(e: object) -> set[str]:
    return {a.codigo for a in e.avisos}  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# El caso simple, y la regla 1
# --------------------------------------------------------------------------- #
def test_cabecera_y_datos() -> None:
    e = de(GENERICOS / "01-coma-punto.csv")
    assert e.linea_nombres == 0
    assert e.linea_inicio_datos == 1
    assert e.linea_unidades is None
    assert e.nombres == ("Time", "RPM", "MAP", "TPS", "CLT", "Lambda")
    assert e.preambulo == ()
    assert e.metadatos == {}
    assert e.n_columnas == 6


def test_el_bloque_consistente_del_sondeo_no_es_el_inicio_de_los_datos() -> None:
    """La regla 1, comprobada contra el propio resultado de FG-01.

    En este fichero el bloque consistente empieza en la línea 0 —la cabecera tiene
    los mismos 6 campos que los datos, para eso es una cabecera— y los datos
    empiezan en la 1. Una implementación que se fiara de `linea_inicio_datos` del
    sondeo metería `Time;RPM;MAP` como si fueran muestras.
    """
    datos = (GENERICOS / "02-puntoycoma-coma.csv").read_bytes()
    s = sondear_csv(datos)
    assert s.linea_inicio_datos == 0, "el bloque consistente incluye la cabecera"
    e = analizar(datos)
    assert e.linea_inicio_datos == 1, "los datos, no"
    assert e.nombres[0] == "Time"


def test_la_regla_funciona_con_coma_decimal() -> None:
    """La regla 2: con punto decimal, `0,000;1456` no sería numérico y la primera
    fila de datos parecería otra cabecera."""
    e = de(GENERICOS / "02-puntoycoma-coma.csv")
    assert e.linea_inicio_datos == 1
    assert e.nombres == ("Time", "RPM", "MAP", "TPS", "CLT", "Lambda")


def test_el_generico_de_f0_13() -> None:
    """El gemelo europeo del log nativo trae además fila de unidades.

    `s;rpm;kPa;%;°C;…` entre los nombres y los datos, así que este fichero
    ejercita a la vez el separador decimal de coma y el paso 6 completo.
    """
    e = de(DOS_FORMATOS / "generico.csv")
    assert e.linea_nombres == 0
    assert e.linea_unidades == 1
    assert e.linea_inicio_datos == 2
    assert e.n_columnas == 11
    assert e.nombres[0] == "Tiempo"
    assert e.unidades_declaradas[:3] == ("s", "rpm", "kPa")


# --------------------------------------------------------------------------- #
# Fila de unidades
# --------------------------------------------------------------------------- #
def test_fila_de_unidades() -> None:
    """`s,rpm,kPa,%,C,ratio` entre los nombres y los datos (§7.4 paso 6)."""
    e = de(GENERICOS / "04-fila-de-unidades.csv")
    assert e.linea_nombres == 0
    assert e.linea_unidades == 1
    assert e.linea_inicio_datos == 2
    assert e.nombres == ("Time", "RPM", "MAP", "TPS", "CLT", "Lambda")
    assert e.unidades_declaradas == ("s", "rpm", "kPa", "%", "C", "ratio")
    assert e.tiene_fila_de_unidades


def test_las_unidades_salen_en_crudo_sin_resolver() -> None:
    """Traducir `C` a °C contra el catálogo de alias es FG-06.

    Meterlo aquí lo dejaría sin el diccionario de alias que esa tarea aporta, y
    entonces habría dos sitios resolviendo unidades con dos tablas distintas.
    """
    e = de(GENERICOS / "04-fila-de-unidades.csv")
    assert "C" in e.unidades_declaradas, "en crudo, tal como está escrito"
    assert "degC" not in e.unidades_declaradas
    assert "°C" not in e.unidades_declaradas


def test_la_unidad_en_el_nombre_no_es_fila_de_unidades() -> None:
    """`Time [s],RPM [rpm],…` no tiene fila de unidades: la unidad va dentro del
    nombre y de eso se ocupa FG-06."""
    e = de(GENERICOS / "05-unidad-en-el-nombre.csv")
    assert e.linea_unidades is None
    assert e.unidades_declaradas == ()
    assert e.nombres[0] == "Time [s]", "el nombre se conserva entero"
    assert e.linea_inicio_datos == 1


def test_una_fila_larga_de_texto_no_es_fila_de_unidades() -> None:
    """§7.4 dice «no numérica Y CORTA». Sin la longitud, cualquier segunda línea
    de texto —un comentario, una nota del piloto— se tomaría por unidades y se
    perdería como fila de nombres."""
    datos = (
        b"Time,RPM,MAP\n"
        b"Notas del piloto,Vuelta de calentamiento,Neumaticos frios\n"
        b"0.000,1456,217.300\n0.050,4107,56.380\n"
    )
    e = analizar(datos)
    assert e.linea_unidades is None
    assert e.linea_nombres == 1, "la línea larga se toma como los nombres"
    assert e.linea_inicio_datos == 2


def test_una_fila_de_unidades_al_limite_se_avisa() -> None:
    """La regla 3: cuando la heurística entra por los pelos, hay que decirlo."""
    datos = (
        b"Time,RPM,Presion\nsegundos,rev/min,kilopascal\n0.000,1456,217.300\n0.050,4107,56.380\n"
    )
    e = analizar(datos)
    assert e.linea_unidades == 1
    assert "fila_de_unidades_dudosa" in codigos(e)


def test_la_unica_linea_antes_de_los_datos_se_toma_como_nombres() -> None:
    """Si solo hay una línea delante y parece de unidades, gana «nombres».

    Sin nombres no hay selector de canales, así que unos nombres raros son más
    útiles que unas unidades sin nombres a las que pegarlas.
    """
    datos = b"s,rpm,kPa\n0.000,1456,217.300\n0.050,4107,56.380\n"
    e = analizar(datos)
    assert e.linea_nombres == 0
    assert e.linea_unidades is None
    assert e.nombres == ("s", "rpm", "kPa")
    assert "unidades_o_nombres_ambiguo" in codigos(e)


# --------------------------------------------------------------------------- #
# Preámbulo y metadatos
# --------------------------------------------------------------------------- #
def test_preambulo_largo() -> None:
    """Las 12 líneas de `clave: valor` de `14-preambulo-largo.csv` (§7.4 paso 7)."""
    e = de(GENERICOS / "14-preambulo-largo.csv")
    assert e.linea_nombres == 12
    assert e.linea_inicio_datos == 13
    assert len(e.preambulo) == 12
    assert e.metadatos["vehicle"] == "Track car - GT"
    assert e.metadatos["track"] == "Spa Francorchamps"
    assert e.metadatos["boost"] == "1.6 bar"
    assert e.nombres == ("Time", "RPM", "MAP", "TPS", "CLT", "Lambda")


def test_el_metadato_se_lee_de_la_linea_cruda_no_de_los_campos() -> None:
    """`notes: cambios, y más` tiene una coma dentro.

    Partiendo por el delimitador, el valor se quedaría en `cambios` y se perdería
    la mitad. El preámbulo no es CSV: son líneas de texto.
    """
    datos = (
        b"notes: cambios de reglaje, y una vuelta de calentamiento\n"
        b"Time,RPM\n0.000,1456\n0.050,4107\n"
    )
    e = analizar(datos)
    assert e.metadatos["notes"] == "cambios de reglaje, y una vuelta de calentamiento"


def test_metadatos_con_igual() -> None:
    datos = b"vehiculo = GT\nsesion = Q1\nTime,RPM\n0.000,1456\n0.050,4107\n"
    e = analizar(datos)
    assert e.metadatos == {"vehiculo": "GT", "sesion": "Q1"}


def test_una_linea_de_preambulo_sin_forma_de_metadato_no_se_inventa() -> None:
    """Inventarle una clave sería fabricar un metadato que el fichero no declara."""
    datos = b"Informe de sesion\nvehiculo: GT\nTime,RPM\n0.000,1456\n0.050,4107\n"
    e = analizar(datos)
    assert e.metadatos == {"vehiculo": "GT"}
    assert "Informe de sesion" in e.preambulo, "pero la línea se conserva"
    assert "preambulo_sin_forma_de_metadato" in codigos(e)


def test_metadato_repetido_se_avisa() -> None:
    datos = b"piloto: A\npiloto: B\nTime,RPM\n0.000,1456\n0.050,4107\n"
    e = analizar(datos)
    assert e.metadatos["piloto"] == "B", "se queda el último"
    assert "metadato_repetido" in codigos(e)


# --------------------------------------------------------------------------- #
# Sin nombres, y la regla 4
# --------------------------------------------------------------------------- #
def test_un_fichero_que_empieza_por_datos_no_tiene_nombres() -> None:
    datos = b"0.000,1456,217.300\n0.050,4107,56.380\n0.100,5873,48.040\n"
    e = analizar(datos)
    assert e.linea_nombres is None
    assert e.tiene_nombres is False
    assert e.nombres == (), "no se inventan"
    assert e.linea_inicio_datos == 0
    assert "sin_fila_de_nombres" in codigos(e)


def test_los_nombres_posicionales_hay_que_pedirlos() -> None:
    """La regla 4. Fabricar nombres es decisión del que llama.

    Un `nombres` relleno de `col_3` sería indistinguible de un fichero que de
    verdad llama `col_3` a una columna.
    """
    datos = b"0.000,1456,217.300\n0.050,4107,56.380\n0.100,5873,48.040\n"
    e = analizar(datos)
    assert e.nombres == ()
    assert e.nombres_o_posicionales() == ("col_1", "col_2", "col_3")
    assert e.nombres_o_posicionales("canal") == ("canal_1", "canal_2", "canal_3")


def test_los_nombres_que_existen_no_se_sustituyen_por_posicionales() -> None:
    e = de(GENERICOS / "01-coma-punto.csv")
    assert e.nombres_o_posicionales() == e.nombres


def test_nombres_duplicados_se_avisan_y_no_se_renombran() -> None:
    """`13-columnas-duplicadas.csv` trae `Time,RPM,RPM,MAP,TPS,CLT`.

    Renombrar a `RPM_2` inventaría un nombre que el fichero no tiene y que el
    usuario no reconocería; §1.3 ya dice que la identidad del canal no es el
    nombre.
    """
    e = de(GENERICOS / "13-columnas-duplicadas.csv")
    assert e.nombres == ("Time", "RPM", "RPM", "MAP", "TPS", "CLT")
    assert "nombres_duplicados" in codigos(e)
    mensaje = next(a.mensaje for a in e.avisos if a.codigo == "nombres_duplicados")
    assert "columnas 2 y 3" in mensaje, "hay que decir cuáles, no solo que hay"


def test_una_columna_sin_nombre_se_avisa() -> None:
    datos = b"Time,,MAP\n0.000,1456,217.300\n0.050,4107,56.380\n"
    e = analizar(datos)
    assert e.nombres == ("Time", "", "MAP")
    assert "nombres_vacios" in codigos(e)


def test_cabecera_con_menos_celdas_que_los_datos() -> None:
    datos = b"Time,RPM\n0.000,1456,217.300\n0.050,4107,56.380\n0.100,5873,48.040\n"
    e = analizar(datos)
    assert e.n_columnas == 3
    assert "nombres_descuadrados" in codigos(e)


# --------------------------------------------------------------------------- #
# Filas de datos con celdas que no son números
# --------------------------------------------------------------------------- #
def test_una_fila_con_centinela_de_texto_sigue_siendo_de_datos() -> None:
    """`11-valores-ausentes.csv` trae `#N/A` en medio de filas buenas.

    Por eso el umbral es 0,7 y no 1,0: una fila con un centinela sigue siendo una
    fila de datos, y exigir todas las celdas numéricas habría hecho que los datos
    «empezaran» en la primera fila sin huecos.
    """
    e = de(GENERICOS / "11-valores-ausentes.csv")
    assert e.linea_nombres == 0
    assert e.linea_inicio_datos == 1
    assert FRACCION_NUMERICA_MINIMA < 1.0


def test_columnas_de_texto_y_booleanos_no_impiden_reconocer_los_datos() -> None:
    """`12-texto-y-booleanos.csv` tiene una columna `Limitador` con `true`/`false`:
    una de seis celdas no numérica, por debajo del umbral."""
    e = de(GENERICOS / "12-texto-y-booleanos.csv")
    assert e.linea_nombres == 0
    assert e.linea_inicio_datos == 1
    assert e.nombres == ("Time", "RPM", "Marcha", "Limitador", "CLT", "Lambda")


def test_una_columna_de_marcas_de_tiempo_no_numericas() -> None:
    """`09-iso8601.csv`: la primera columna es `2026-07-29T18:30:35.506Z`, texto
    para cualquier interpretación. Cinco de seis celdas numéricas basta."""
    e = de(GENERICOS / "09-iso8601.csv")
    assert e.linea_nombres == 0
    assert e.linea_inicio_datos == 1


# --------------------------------------------------------------------------- #
# Los logs nativos por el camino genérico
# --------------------------------------------------------------------------- #
def test_el_log_nativo_real_reparte_su_cabecera_como_preambulo() -> None:
    """La red de seguridad de §7.15 sobre un Haltech de verdad.

    Sus 108 líneas de `Channel : RPM` / `ID : 14` son, para el camino genérico,
    un preámbulo de metadatos. Y salen como metadatos de verdad, porque tienen
    forma `clave: valor`.
    """
    e = de(REALES / "20260729_1859_Log2768.csv")
    assert e.linea_inicio_datos == 108
    assert e.linea_nombres is None, "un log nativo no tiene fila de nombres CSV"
    assert len(e.preambulo) == 108, "la cabecera entera es preámbulo"
    assert e.metadatos["DataLogVersion"] == "1.1"
    assert e.metadatos["Log Number"] == "2768"
    assert e.metadatos["Log"] == "19800101 01:01:01"
    assert e.n_columnas == 26


def test_el_autolog_real_tambien() -> None:
    """Y aquí está el defecto que destapó este fichero.

    La última línea antes de los datos es `Log : 20260729 06:30:35`. Tomarla por
    cabecera dejaba UN nombre para 476 columnas, y el aviso de descuadre era el
    único síntoma. Una línea con forma `clave: valor` cuyo número de campos no
    cuadra con los datos es preámbulo, aunque esté pegada a ellos.
    """
    e = de(REALES / "AutoLog_20260729_1830.csv")
    assert e.linea_inicio_datos == 1895
    assert e.linea_nombres is None
    assert e.n_columnas == 476
    assert e.metadatos["Log"] == "20260729 06:30:35"
    assert "sin_fila_de_nombres" in codigos(e)
    assert e.nombres_o_posicionales()[:2] == ("col_1", "col_2")


# --------------------------------------------------------------------------- #
# Contratos
# --------------------------------------------------------------------------- #
def test_sin_delimitador_no_se_puede_repartir() -> None:
    datos = b"Valor\n1000\n1100\n1200\n"
    s = sondear_csv(datos)
    assert s.delimitador is None
    d = None
    with pytest.raises(ErrorDeEstructura, match="no propuso delimitador"):
        from dlv_core.formatos.decimal_csv import Decimales, MotivoDecimal

        d = Decimales(
            separador=".",
            agrupacion=None,
            motivo=MotivoDecimal.SIN_EVIDENCIA,
            ambiguo=False,
            interpretaciones=(),
            celdas_inspeccionadas=0,
            filas_inspeccionadas=0,
        )
        analizar_estructura(s, d, datos.decode("utf-8"))
    assert d is not None


def test_un_fichero_sin_ninguna_linea_numerica_es_un_error_con_nombre() -> None:
    """Y el mensaje dice las dos causas posibles, porque las dos son plausibles:
    o no es un fichero de datos, o el separador decimal está mal propuesto."""
    datos = b"uno,dos,tres\ncuatro,cinco,seis\nsiete,ocho,nueve\n"
    with pytest.raises(ErrorDeEstructura) as excinfo:
        analizar(datos)
    mensaje = str(excinfo.value)
    assert "separador decimal" in mensaje
    assert "fichero de texto" in mensaje


def test_muy_pocas_filas_de_datos_se_avisa() -> None:
    datos = b"Time,RPM\n0.000,1456\n"
    e = analizar(datos)
    assert e.linea_inicio_datos == 1
    assert "muy_pocas_filas_de_datos" in codigos(e)


def test_el_resultado_es_reproducible() -> None:
    datos = (GENERICOS / "14-preambulo-largo.csv").read_bytes()
    assert analizar(datos) == analizar(datos)


def test_las_lineas_vacias_no_desplazan_los_indices() -> None:
    """Los índices son sobre las líneas NO vacías, igual que en FG-01.

    Si una tarea contara las vacías y la otra no, los índices que se pasan entre
    ellas apuntarían a líneas distintas.
    """
    datos = b"vehiculo: GT\n\nTime,RPM\n\n0.000,1456\n0.050,4107\n"
    e = analizar(datos)
    assert e.linea_nombres == 1
    assert e.linea_inicio_datos == 2
    assert e.metadatos == {"vehiculo": "GT"}


# --------------------------------------------------------------------------- #
# Una marca de tiempo es una celda de datos (defecto destapado por FG-04)
# --------------------------------------------------------------------------- #
def test_un_fichero_estrecho_con_columna_de_marca_de_tiempo() -> None:
    """El defecto que destapó FG-04 al usar este módulo.

    La regla del paso 6 es «la primera línea mayoritariamente numérica», y en
    `Time,RPM` con `18:30:35.506,1456` hay una celda numérica de dos: un 50 %, por
    debajo del umbral de 0,7. En un log real con 20 columnas la marca de tiempo es
    una fracción despreciable y no se nota; con dos columnas, el fichero entero se
    declaraba ilegible. Una marca de tiempo NO es un número y sí es un dato.
    """
    datos = b"Time,RPM\n18:30:35.506,1456\n18:30:35.556,4107\n18:30:35.606,5873\n"
    e = analizar(datos)
    assert e.linea_nombres == 0
    assert e.linea_inicio_datos == 1
    assert e.nombres == ("Time", "RPM")


def test_fecha_y_hora_en_dos_columnas_con_una_sola_numerica() -> None:
    """Dos columnas de marca y una numérica: un 33 % de celdas numéricas."""
    datos = b"Fecha,Hora,RPM\n2026-07-29,18:30:35.506,1456\n2026-07-29,18:30:35.556,4107\n"
    e = analizar(datos)
    assert e.linea_inicio_datos == 1


@pytest.mark.parametrize(
    "celda",
    ["18:30:35.506", "18:30", "2026-07-29T18:30:35Z", "2026-07-29", "20260729", "29/07/2026"],
)
def test_formas_que_cuentan_como_marca_de_tiempo(celda: str) -> None:
    assert parece_marca_de_tiempo(celda)


@pytest.mark.parametrize("celda", ["RPM", "s", "kPa", "#N/A", "true", ""])
def test_formas_que_no_son_marca_de_tiempo(celda: str) -> None:
    assert not parece_marca_de_tiempo(celda)


def test_una_fila_de_unidades_no_puede_llevar_marcas_de_tiempo() -> None:
    """`s,18:30:35` es una fila de datos con la marca en otra columna, no unidades."""
    datos = b"Time,RPM\ns,rpm\n18:30:35.506,1456\n18:30:35.556,4107\n"
    e = analizar(datos)
    assert e.linea_unidades == 1, "esta sí es de unidades"
    assert e.unidades_declaradas == ("s", "rpm")
