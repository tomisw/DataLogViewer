"""Pruebas del separador decimal por verificación cruzada (tarea FG-02).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.4, paso 4 — el que la
propia especificación llama «el que más a menudo se hace mal y el más importante
en Europa».

QUÉ PROTEGE ESTA SUITE
======================
Equivocarse aquí no da un error: da un log con el doble de canales y la mitad de
los valores, o —peor— un log con los canales correctos y los valores multiplicados
por mil. Un `1.234` leído como 1,234 en vez de 1234 en un canal de presión es la
diferencia entre 1,2 kPa y 1,2 bar, y las dos son cifras perfectamente creíbles.

Cuatro reglas, por consecuencia:

1. **No se decide por el delimitador.** «Si es `;`, el decimal es coma» es una
   correlación: hay exportadores que escriben `;` con punto decimal, y con la
   regla del delimitador esos se leen mal en silencio.
2. **Tres resultados, no dos.** Evidencia para coma, evidencia para punto, o
   ninguna evidencia. Sin el tercero, un fichero de enteros se declara resuelto y
   la fila 50 000 se lee con el separador equivocado.
3. **La ambigüedad de los tres dígitos se reconoce como ambigüedad.** `1.234` no
   se puede resolver mirando: el dato no lo dice.
4. **Un fichero contradictorio se declara contradictorio**, no se resuelve por
   mayoría en silencio.

Solo biblioteca estándar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlv_core.formatos.decimal_csv import (
    ErrorDeDecimal,
    MotivoDecimal,
    SeparadorDecimal,
    detectar_separador_decimal,
)
from dlv_core.formatos.sondeo import sondear_csv

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
DOS_FORMATOS = RAIZ / "samples" / "dos-formatos"


def analizar(datos: bytes) -> object:
    """Sondea y detecta, que es como se usan las dos tareas juntas."""
    s = sondear_csv(datos)
    return detectar_separador_decimal(s, datos.decode(s.codificacion))


def de(ruta: Path) -> object:
    return analizar(ruta.read_bytes())


def codigos(d: object) -> set[str]:
    return {a.codigo for a in d.avisos}  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# El corpus real
# --------------------------------------------------------------------------- #
def test_el_csv_espanol() -> None:
    """`;` con coma decimal: el caso más importante de §7.4.

    Con punto decimal, `0,050` y `217,300` no son números. La coma explica celdas
    que el punto no, y eso es la verificación cruzada.
    """
    d = de(GENERICOS / "02-puntoycoma-coma.csv")
    assert d.separador == SeparadorDecimal.COMA
    assert d.motivo is MotivoDecimal.VERIFICACION_CRUZADA
    assert d.ambiguo is False
    assert d.agrupacion is None

    por_punto = next(i for i in d.interpretaciones if i.decimal == ".")
    assert por_punto.cobertura < 1.0, "con punto quedan celdas sin parsear"
    assert por_punto.ejemplos_no_numericos, "y se enseñan, para que se pueda revisar"


def test_el_csv_anglosajon() -> None:
    """Con delimitador `,` el motivo es el DELIMITADOR, no la verificación cruzada.

    Y eso es certeza, no falta de evidencia: una coma decimal habría partido el
    número en dos campos y el fichero no sería consistente. La primera versión
    devolvía `hay_evidencia=False` para el caso más común de todos, y con eso el
    asistente habría avisado de una duda que no existe.
    """
    d = de(GENERICOS / "01-coma-punto.csv")
    assert d.separador == SeparadorDecimal.PUNTO
    assert d.motivo is MotivoDecimal.DELIMITADOR
    assert d.hay_evidencia is True
    assert d.ambiguo is False


def test_el_csv_de_tabulaciones_con_punto() -> None:
    """Con delimitador `\\t` las dos comas y puntos son posibles, así que el caso
    depende por completo de la verificación cruzada."""
    d = de(GENERICOS / "03-tabulaciones.csv")
    assert d.separador == SeparadorDecimal.PUNTO
    assert d.motivo is MotivoDecimal.VERIFICACION_CRUZADA


def test_el_generico_de_f0_13() -> None:
    """El gemelo europeo del log nativo: `;` y coma decimal."""
    d = de(DOS_FORMATOS / "generico.csv")
    assert d.separador == SeparadorDecimal.COMA
    assert d.hay_evidencia is True


def test_el_nativo_de_f0_13_es_punto() -> None:
    d = de(DOS_FORMATOS / "nativo.csv")
    assert d.separador == SeparadorDecimal.PUNTO


@pytest.mark.parametrize(
    "fichero",
    [
        "01-coma-punto.csv",
        "04-fila-de-unidades.csv",
        "05-unidad-en-el-nombre.csv",
        "06-sin-columna-de-tiempo.csv",
        "07-epoch-segundos.csv",
        "09-iso8601.csv",
        "11-valores-ausentes.csv",
        "12-texto-y-booleanos.csv",
        "13-columnas-duplicadas.csv",
        "14-preambulo-largo.csv",
    ],
)
def test_los_ficheros_de_coma_del_corpus_dan_punto(fichero: str) -> None:
    """Con delimitador `,` la coma decimal es IMPOSIBLE, no improbable: habría
    partido el número en dos campos y el fichero no sería consistente."""
    d = de(GENERICOS / fichero)
    assert d.separador == SeparadorDecimal.PUNTO
    assert d.motivo is MotivoDecimal.DELIMITADOR
    assert len(d.interpretaciones) == 1, "solo hay una lectura posible"


def test_el_preambulo_no_contamina_la_decision() -> None:
    """Las 12 líneas de `clave: valor` traen texto (`Spa Francorchamps`, `98 RON`)
    que no es número en ninguna interpretación. Se descartan porque el sondeo ya
    dijo dónde empiezan los datos."""
    d = de(GENERICOS / "14-preambulo-largo.csv")
    assert d.separador == SeparadorDecimal.PUNTO
    por_punto = next(i for i in d.interpretaciones if i.decimal == ".")
    assert "Spa Francorchamps" not in por_punto.ejemplos_no_numericos


# --------------------------------------------------------------------------- #
# La regla que NO se usa: el delimitador
# --------------------------------------------------------------------------- #
def test_punto_y_coma_con_punto_decimal_se_lee_bien() -> None:
    """La regla 1 de esta suite, y el caso que la justifica.

    Hay exportadores que escriben `;` con punto decimal, porque el `;` lo eligió
    el usuario en un diálogo y el punto lo puso la biblioteca. La regla «si es `;`
    entonces coma» leería `217.300` como 217300 y multiplicaría la presión por mil
    sin que nada fallara.
    """
    datos = b"Time;RPM;MAP\n0.000;1456;217.300\n0.050;4107;56.380\n0.100;5873;48.040\n"
    d = analizar(datos)
    assert d.separador == SeparadorDecimal.PUNTO
    assert d.hay_evidencia is True
    por_coma = next(i for i in d.interpretaciones if i.decimal == ",")
    assert por_coma.cobertura < 1.0


def test_la_verificacion_cruzada_se_explica_en_un_aviso() -> None:
    """El asistente tiene que poder enseñar por qué, con ejemplos."""
    d = de(GENERICOS / "02-puntoycoma-coma.csv")
    assert "decimal_por_verificacion_cruzada" in codigos(d)
    mensaje = next(a.mensaje for a in d.avisos if a.codigo == "decimal_por_verificacion_cruzada")
    assert "','" in mensaje and "celdas no numéricas" in mensaje


# --------------------------------------------------------------------------- #
# Tres resultados, no dos
# --------------------------------------------------------------------------- #
def test_un_fichero_de_solo_enteros_no_tiene_evidencia() -> None:
    """La regla 2. Las dos lecturas dan los MISMOS valores para lo visto, así que
    hoy da igual; pero la fila 50 000 puede traer decimales, y declararlo resuelto
    sería fingir certeza."""
    datos = b"Time;RPM;Marcha\n0;1456;3\n1;4107;4\n2;5873;5\n3;6000;6\n"
    d = analizar(datos)
    assert d.motivo is MotivoDecimal.SIN_EVIDENCIA
    assert d.hay_evidencia is False
    assert d.separador == SeparadorDecimal.PUNTO, "se propone, no se afirma"
    assert "decimal_sin_evidencia" in codigos(d)
    assert "no hay nada en el fichero que lo respalde" in next(
        a.mensaje for a in d.avisos if a.codigo == "decimal_sin_evidencia"
    )


def test_las_celdas_vacias_no_cuentan_como_no_numericas() -> None:
    """F1-03: una celda vacía no es 0 ni un error, es ausencia. No puede
    desequilibrar la comparación entre interpretaciones."""
    datos = b"Time;RPM;MAP\n0,000;;217,300\n0,050;4107;\n0,100;5873;48,040\n"
    d = analizar(datos)
    assert d.separador == SeparadorDecimal.COMA
    por_coma = next(i for i in d.interpretaciones if i.decimal == ",")
    por_punto = next(i for i in d.interpretaciones if i.decimal == ".")
    # La cobertura no llega a 1 porque la fila de nombres es texto (la separa
    # FG-03); lo que importa es que las celdas VACÍAS no penalizan a ninguna, así
    # que la diferencia entre las dos interpretaciones sale solo de los decimales.
    assert por_coma.cobertura > por_punto.cobertura


def test_el_texto_de_los_nombres_no_desequilibra() -> None:
    """La fila de nombres es texto en las DOS interpretaciones, así que resta lo
    mismo a ambas y no cambia el ganador. Separarla es FG-03."""
    datos = b"Time;RPM;MAP\n0,000;1456;217,300\n0,050;4107;56,380\n0,100;5873;48,040\n"
    d = analizar(datos)
    assert d.separador == SeparadorDecimal.COMA
    for i in d.interpretaciones:
        assert i.celdas_totales == d.celdas_inspeccionadas


# --------------------------------------------------------------------------- #
# Ambigüedades que se declaran ambigüedades
# --------------------------------------------------------------------------- #
def test_tres_digitos_sin_desambiguar_es_ambiguo() -> None:
    """La regla 3. `1.234` es 1234 o 1,234: el dato no lo dice, y la diferencia
    es un factor 1 000."""
    datos = b"Time;Presion\n1;1.234\n2;5.678\n3;9.012\n"
    d = analizar(datos)
    assert d.ambiguo is True
    assert "agrupacion_o_decimal_ambiguo" in codigos(d)
    mensaje = next(a.mensaje for a in d.avisos if a.codigo == "agrupacion_o_decimal_ambiguo")
    assert "factor 1 000" in mensaje


def test_una_celda_clara_desambigua_a_las_de_tres_digitos() -> None:
    """Con `0,05` en el fichero, la coma es el decimal y `217,300` deja de ser
    ambiguo: es un decimal con tres cifras, no un millar."""
    datos = b"Time;MAP\n0,05;217,300\n0,10;56,380\n0,15;48,040\n"
    d = analizar(datos)
    assert d.separador == SeparadorDecimal.COMA
    assert d.ambiguo is False
    assert "agrupacion_o_decimal_ambiguo" not in codigos(d)


def test_agrupacion_inequivoca_con_los_dos_separadores() -> None:
    """`1.234,56`: el que agrupa de tres en tres es la agrupación y el otro el
    decimal. No hay otra lectura posible."""
    datos = b"Time;Potencia\n1;1.234,56\n2;2.345,67\n3;3.456,78\n"
    d = analizar(datos)
    assert d.separador == SeparadorDecimal.COMA
    assert d.agrupacion == SeparadorDecimal.PUNTO
    assert d.ambiguo is False


def test_agrupacion_inequivoca_por_repeticion() -> None:
    """`1.234.567`: un número no tiene dos comas decimales, así que el punto
    agrupa y el decimal es el otro carácter."""
    datos = b"Time;Cuenta\n1;1.234.567\n2;2.345.678\n3;3.456.789\n"
    d = analizar(datos)
    assert d.agrupacion == SeparadorDecimal.PUNTO
    assert d.separador == SeparadorDecimal.COMA


def test_un_fichero_contradictorio_se_declara_contradictorio() -> None:
    """La regla 4. Celdas que solo explica el punto Y celdas que solo explica la
    coma: cualquier elección deja parte mal leída, y hay que decirlo en vez de
    resolver por mayoría en silencio."""
    datos = b"Time;A;B\n1;1.5;2,5\n2;3.5;4,5\n3;5.5;6,5\n"
    d = analizar(datos)
    assert d.ambiguo is True
    assert "decimal_contradictorio" in codigos(d)
    mensaje = next(a.mensaje for a in d.avisos if a.codigo == "decimal_contradictorio")
    assert "dos fuentes" in mensaje


# --------------------------------------------------------------------------- #
# Contratos
# --------------------------------------------------------------------------- #
def test_sin_delimitador_no_se_puede_decidir() -> None:
    """Un sondeo que no propuso delimitador no deja campos que interpretar, y
    adivinar el decimal sobre líneas enteras no significaría nada."""
    datos = b"Valor\n1000\n1100\n1200\n1300\n"
    s = sondear_csv(datos)
    assert s.delimitador is None
    with pytest.raises(ErrorDeDecimal, match="no propuso delimitador"):
        detectar_separador_decimal(s, datos.decode(s.codificacion))


def test_las_dos_interpretaciones_se_devuelven_cuando_las_dos_son_posibles() -> None:
    datos = b"Time;RPM\n0,000;1456\n0,050;4107\n0,100;5873\n"
    d = analizar(datos)
    assert {i.decimal for i in d.interpretaciones} == {".", ","}
    assert d.elegida is not None and d.elegida.decimal == ","


def test_la_elegida_apunta_a_la_interpretacion_del_separador() -> None:
    d = de(GENERICOS / "02-puntoycoma-coma.csv")
    assert d.elegida is not None
    assert d.elegida.decimal == d.separador
    peor = min(d.interpretaciones, key=lambda i: i.cobertura)
    assert d.elegida.cobertura > peor.cobertura, "la elegida explica más que la otra"


def test_el_resultado_es_reproducible() -> None:
    datos = (GENERICOS / "02-puntoycoma-coma.csv").read_bytes()
    assert analizar(datos) == analizar(datos)


def test_se_inspeccionan_las_celdas_de_verdad_no_una_muestra_simbolica() -> None:
    """Una implementación que mirara solo la primera fila pasaría casi todas las
    pruebas de arriba y fallaría con un fichero cuyos decimales empiezan más
    abajo."""
    d = de(GENERICOS / "02-puntoycoma-coma.csv")
    assert d.filas_inspeccionadas > 10
    assert d.celdas_inspeccionadas > 50


def test_los_decimales_empiezan_en_la_fila_veinte_y_se_detectan() -> None:
    """El caso que caza a quien solo mire el principio: veinte filas de enteros
    y luego decimales con coma."""
    filas = [f"{i};{i * 100}" for i in range(20)] + [f"{i},5;{i * 100}" for i in range(20, 40)]
    datos = ("Time;RPM\n" + "\n".join(filas) + "\n").encode()
    d = analizar(datos)
    assert d.separador == SeparadorDecimal.COMA
    assert d.hay_evidencia is True
