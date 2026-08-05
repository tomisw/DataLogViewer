"""Pruebas de la inferencia de tipo por columna (FG-05).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.10 y §7.8 paso 3.

QUÉ PROTEGE ESTA SUITE, POR CONSECUENCIA SI SE ROMPE
=====================================================
1. **Un valor ausente nunca cuenta como 0.** Es la regla que §7.10 escribe con
   énfasis, y el sitio donde más fácil se pierde: si las celdas vacías o
   centinela contaran, una columna sin ningún dato saldría como `CONSTANTE` de
   valor cero y el usuario vería una línea recta en el cero que parece un sensor
   pegado a cero en vez de un canal que no existe.
2. **Entero o decimal se decide por la ESCRITURA.** Una columna de λ escrita
   `1.000` es decimal aunque los valores vistos sean enteros exactos; tratarla
   como entera la truncaría en cuanto una fila no inspeccionada trajera `0.997`,
   y ese redondeo no se puede detectar después.
3. **Los centinelas salen de `data/units.toml`, no del código.** Si este módulo
   tuviera su propia lista, añadir el «sin dato» de un exportador nuevo dejaría
   de ser una línea de TOML.
4. **Un 0/1 no es un booleano.** Convertirlo en enum decidiría por el usuario
   sobre un canal que es numéricamente válido tal cual.
5. **Una fila corta o larga no aborta nada** (§7.10), y se avisa con el recuento.

Se prueba contra los ficheros de `samples/generico/` además de con datos
sintéticos: son los que representan lo que de verdad le llega al módulo, y la
cadena FG-01 -> FG-02 -> FG-03 que los lee es la misma que usa el asistente.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlv_core.formatos.decimal_csv import detectar_separador_decimal
from dlv_core.formatos.estructura import analizar_estructura
from dlv_core.formatos.sondeo import dividir_campos, sondear_csv
from dlv_core.formatos.tipos import (
    MAX_VALORES_DISTINTOS,
    Escritura,
    TipoColumna,
    inferir_tipos,
    inferir_tipos_de_columna,
)
from dlv_core.unidades import Catalogo, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
DATA = RAIZ / "data"


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with (DATA / "units.toml").open("rb") as fh:
        return cargar_catalogo(fh)


def de(ruta: Path) -> tuple[list[list[str]], tuple[str, ...], str]:
    """La cadena FG-01 -> FG-02 -> FG-03 sobre un fichero de muestra.

    Devuelve las filas de datos ya partidas, los nombres y el separador decimal:
    exactamente los tres argumentos que `inferir_tipos` necesita.
    """
    datos = ruta.read_bytes()
    s = sondear_csv(datos)
    texto = datos.decode(s.codificacion)
    d = detectar_separador_decimal(s, texto)
    e = analizar_estructura(s, d, texto)
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    filas = [
        dividir_campos(ln, s.delimitador or ",", s.comilla) for ln in lineas[e.linea_inicio_datos :]
    ]
    return filas, e.nombres_o_posicionales(), d.separador


def col(celdas: list[str], **kw: object) -> object:
    return inferir_tipos_de_columna(celdas, **kw)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# La regla de §7.10: ausente no es 0
# --------------------------------------------------------------------------- #
def test_una_columna_toda_vacia_es_vacia_no_constante_cero() -> None:
    """Si las celdas vacías contaran como 0, esta columna saldría `CONSTANTE` de
    valor 0 y el usuario vería una recta en el cero: indistinguible de un sensor
    pegado a cero, que es un problema del coche y no del fichero."""
    r = inferir_tipos_de_columna(["", "  ", ""])
    assert r.tipo is TipoColumna.VACIA
    assert r.con_dato == 0
    assert r.vacias == 3
    assert r.valor_constante is None
    assert not r.graficable
    assert not r.es_numerico


def test_los_centinelas_de_texto_no_cuentan_como_dato(catalogo: Catalogo) -> None:
    """`NaN`, `#N/A`, `NULL`, `---` y `-` están declarados en `[centinelas] texto`
    de `data/units.toml`: son ausencia, no texto que convierta la columna en un
    enum de cinco estados."""
    r = inferir_tipos_de_columna(["NaN", "#N/A", "NULL", "---", "-", "n/a"], catalogo=catalogo)
    assert r.tipo is TipoColumna.VACIA
    assert r.centinelas_texto == 6
    assert r.no_numericas == 0


def test_los_centinelas_se_toman_del_catalogo_y_no_del_codigo(catalogo: Catalogo) -> None:
    """Sin catálogo, `NULL` es texto. Con catálogo, es ausencia. Esa diferencia es
    la prueba de que la lista vive en `data/units.toml` y no en este módulo: si
    hubiera una lista por omisión en Python, las dos llamadas darían lo mismo."""
    sin = inferir_tipos_de_columna(["1", "2", "NULL"])
    con = inferir_tipos_de_columna(["1", "2", "NULL"], catalogo=catalogo)
    assert sin.no_numericas == 1
    assert con.no_numericas == 0
    assert con.centinelas_texto == 1
    assert con.tipo is TipoColumna.ENTERO


def test_un_centinela_de_desbordamiento_se_cuenta_aparte(catalogo: Catalogo) -> None:
    """Una columna llena de `2147483647` no es un canal a otra frecuencia: es un
    sensor que estuvo desconectado toda la sesión. Contarlo con las celdas vacías
    haría que las dos cosas se leyeran igual en el informe."""
    r = inferir_tipos_de_columna(["2147483647", "2147483647", "-2147483648"], catalogo=catalogo)
    assert r.tipo is TipoColumna.VACIA
    assert r.centinelas_desbordamiento == 3
    assert r.vacias == 0
    assert r.centinelas_texto == 0


def test_un_hueco_no_baja_la_cobertura_numerica(catalogo: Catalogo) -> None:
    """La cobertura es sobre las celdas CON DATO. Si fuera sobre el total, un
    canal a 5 Hz en un fichero a 20 Hz saldría al 25 % y parecería un problema de
    tipos cuando es el muestreo disperso normal de `docs/01` §1.4."""
    r = inferir_tipos_de_columna(["1", "", "", "", "2", "", "", ""], catalogo=catalogo)
    assert r.tipo is TipoColumna.ENTERO
    assert r.cobertura_numerica == pytest.approx(1.0)
    assert r.vacias == 6


# --------------------------------------------------------------------------- #
# Entero o decimal: por la escritura, no por el valor
# --------------------------------------------------------------------------- #
def test_una_columna_escrita_con_decimales_enteros_es_decimal() -> None:
    """El caso de λ: valores que son enteros exactos pero están ESCRITOS con tres
    decimales. El exportador los escribió porque el canal los tiene; clasificarla
    entera la truncaría a `1` en cuanto una fila no inspeccionada trajera
    `0.997`, y ese redondeo no se puede detectar después.

    (Con los tres valores iguales ganaría `CONSTANTE` por precedencia, que es
    otra prueba; aquí lo que se mide es entero contra decimal.)"""
    r = inferir_tipos_de_columna(["1.000", "2.000", "3.000"])
    assert r.tipo is TipoColumna.DECIMAL
    assert r.escritura is Escritura.CON_FRACCION


def test_una_columna_sin_ningun_punto_es_entera() -> None:
    r = inferir_tipos_de_columna(["850", "1200", "6500"])
    assert r.tipo is TipoColumna.ENTERO
    assert r.escritura is Escritura.SIN_FRACCION
    assert r.es_numerico


def test_la_notacion_cientifica_es_decimal() -> None:
    """`1e-3` no lleva punto pero no es un entero. Sin el exponente en el patrón,
    una columna de presiones minúsculas se guardaría como entero y se iría toda a
    cero."""
    r = inferir_tipos_de_columna(["1e-3", "5e-4"])
    assert r.tipo is TipoColumna.DECIMAL
    assert r.escritura is Escritura.CON_FRACCION


def test_una_sola_celda_con_fraccion_hace_decimal_la_columna() -> None:
    """La asimetría es deliberada: pasar de decimal a entero pierde precisión sin
    avisar, y al revés no se pierde nada."""
    r = inferir_tipos_de_columna(["1", "2", "3", "4.5"])
    assert r.tipo is TipoColumna.DECIMAL


def test_el_separador_decimal_del_fichero_decide_que_es_fraccion() -> None:
    """`0,5` es un decimal en un fichero con coma decimal y no lo es en uno con
    punto -- ahí ni siquiera es un número."""
    con_coma = inferir_tipos_de_columna(["0,5", "1,25"], decimal=",")
    assert con_coma.tipo is TipoColumna.DECIMAL

    con_punto = inferir_tipos_de_columna(["0,5", "1,25"], decimal=".")
    assert con_punto.tipo is TipoColumna.ENUM_TEXTO


# --------------------------------------------------------------------------- #
# Constante
# --------------------------------------------------------------------------- #
def test_una_columna_con_un_solo_valor_es_constante() -> None:
    r = inferir_tipos_de_columna(["0", "0", "0", "0"])
    assert r.tipo is TipoColumna.CONSTANTE
    assert r.valor_constante == "0"
    assert not r.graficable
    assert r.es_numerico, "aburrida no es lo mismo que no numérica"


def test_una_constante_de_texto_no_es_numerica() -> None:
    r = inferir_tipos_de_columna(["Practica", "Practica"])
    assert r.tipo is TipoColumna.CONSTANTE
    assert not r.es_numerico


def test_la_constante_ignora_las_ausencias(catalogo: Catalogo) -> None:
    """Una columna con un valor y mucho hueco sigue siendo constante: el hueco no
    es un segundo valor."""
    r = inferir_tipos_de_columna(["5", "", "NaN", "5", ""], catalogo=catalogo)
    assert r.tipo is TipoColumna.CONSTANTE
    assert r.valor_constante == "5"
    assert r.con_dato == 2


def test_la_escritura_sobrevive_a_la_precedencia_de_constante() -> None:
    """`CONSTANTE` gana a `DECIMAL` por precedencia, así que sin `escritura` se
    perdería si aquella constante era `0` o `0.000` -- que es lo que decide en qué
    se guarda si deja de ser constante en las filas no inspeccionadas."""
    entera = inferir_tipos_de_columna(["0", "0"])
    decimal = inferir_tipos_de_columna(["0.000", "0.000"])
    assert entera.tipo is decimal.tipo is TipoColumna.CONSTANTE
    assert entera.escritura is Escritura.SIN_FRACCION
    assert decimal.escritura is Escritura.CON_FRACCION


# --------------------------------------------------------------------------- #
# Booleano
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "celdas",
    [
        ["true", "false", "true"],
        ["TRUE", "FALSE"],
        ["on", "off", "on"],
        ["sí", "no"],
        ["si", "no"],
        ["yes", "no"],
        ["verdadero", "falso"],
    ],
)
def test_las_parejas_booleanas_de_la_especificacion(celdas: list[str]) -> None:
    r = inferir_tipos_de_columna(celdas)
    assert r.tipo is TipoColumna.BOOLEANO, celdas
    assert not r.es_numerico


def test_el_booleano_es_insensible_a_mayusculas_a_proposito() -> None:
    """A diferencia de las unidades de FG-06, que son sensibles: `TRUE` y `true`
    son el mismo booleano en todos los exportadores que existen, mientras que `M`
    y `m` son mega y mili. Adivinar cuesta caro en un sitio y nada en el otro."""
    r = inferir_tipos_de_columna(["True", "FALSE", "true"])
    assert r.tipo is TipoColumna.BOOLEANO


def test_un_cero_uno_no_es_booleano() -> None:
    """§7.10 lista tres parejas y las tres son de texto. Un canal de 0 y 1 es
    numéricamente válido tal cual, y convertirlo en enum decidiría por el
    usuario. Lo que sí se da es la lista de valores distintos, para que FG-08
    pueda ofrecer el enum sin que esta inferencia lo imponga."""
    r = inferir_tipos_de_columna(["0", "1", "1", "0"])
    assert r.tipo is TipoColumna.ENTERO
    assert r.es_numerico
    assert set(r.valores_distintos) == {"0", "1"}


def test_dos_valores_de_texto_que_no_son_pareja_conocida_son_enum() -> None:
    """`Alta`/`Baja` son dos estados, pero no una pareja booleana: llamarlos
    verdadero y falso sería inventar cuál es cuál."""
    r = inferir_tipos_de_columna(["Alta", "Baja", "Alta"])
    assert r.tipo is TipoColumna.ENUM_TEXTO


# --------------------------------------------------------------------------- #
# Enum de texto y columnas mixtas
# --------------------------------------------------------------------------- #
def test_una_columna_de_texto_es_enum() -> None:
    r = inferir_tipos_de_columna(["Primera", "Segunda", "Tercera", "Primera"])
    assert r.tipo is TipoColumna.ENUM_TEXTO
    assert r.valores_distintos == ("Primera", "Segunda", "Tercera")
    assert not r.distintos_truncados


def test_una_columna_casi_numerica_se_propone_numerica() -> None:
    """Un exportador que escribe `ERROR` en tres filas de una columna por lo demás
    numérica no la convierte en texto: tratarla como enum perdería los números
    buenos para conservar tres cadenas."""
    celdas = [str(i) for i in range(100)] + ["ERROR", "ERROR"]
    r = inferir_tipos_de_columna(celdas)
    assert r.tipo is TipoColumna.ENTERO
    assert r.no_numericas == 2
    assert r.ejemplos_no_numericos == ("ERROR",)
    assert r.cobertura_numerica == pytest.approx(100 / 102)


def test_una_columna_mitad_texto_es_enum() -> None:
    celdas = [str(i) for i in range(10)] + [f"estado_{i}" for i in range(10)]
    r = inferir_tipos_de_columna(celdas)
    assert r.tipo is TipoColumna.ENUM_TEXTO


def test_la_cobertura_minima_es_configurable() -> None:
    """Es una heurística de formato, no una opinión cableada: quien tenga un
    fichero con más ruido puede bajarla, y quien no quiera ninguna celda de texto
    en una columna numérica puede exigir el 100 %."""
    celdas = [str(i) for i in range(19)] + ["ERROR"]
    assert inferir_tipos_de_columna(celdas).tipo is TipoColumna.ENTERO
    exigente = inferir_tipos_de_columna(celdas, cobertura_numerica_minima=1.0)
    assert exigente.tipo is TipoColumna.ENUM_TEXTO


def test_texto_libre_no_finge_ser_un_enum() -> None:
    """Con más valores distintos que estados posibles de un enum utilizable, la
    lista se trunca y se dice que se truncó: una tupla vacía sin la marca sería
    ambigua entre «no hay ninguno» y «hay demasiados»."""
    celdas = [f"nota del piloto {i}" for i in range(MAX_VALORES_DISTINTOS + 10)]
    r = inferir_tipos_de_columna(celdas)
    assert r.tipo is TipoColumna.ENUM_TEXTO
    assert r.distintos_truncados
    assert r.valores_distintos == ()


def test_muchos_valores_distintos_no_impiden_ser_numerica() -> None:
    """El truncado de la lista de distintos no puede cambiar el tipo de una
    columna numérica: un canal de RPM tiene miles de valores distintos."""
    celdas = [str(i) for i in range(MAX_VALORES_DISTINTOS + 100)]
    r = inferir_tipos_de_columna(celdas)
    assert r.tipo is TipoColumna.ENTERO
    assert r.distintos_truncados


# --------------------------------------------------------------------------- #
# Varias columnas a la vez, y filas de longitud variable (§7.10)
# --------------------------------------------------------------------------- #
def test_inferir_tipos_respeta_el_orden_y_los_nombres() -> None:
    filas = [["0.000", "850", "Primera"], ["0.050", "900", "Segunda"]]
    r = inferir_tipos(filas, ("Tiempo", "RPM", "Marcha"))
    assert [c.nombre for c in r.columnas] == ["Tiempo", "RPM", "Marcha"]
    assert [c.indice for c in r.columnas] == [0, 1, 2]
    assert r.columnas[0].tipo is TipoColumna.DECIMAL
    assert r.columnas[1].tipo is TipoColumna.ENTERO
    assert r.columnas[2].tipo is TipoColumna.ENUM_TEXTO
    assert r.filas_inspeccionadas == 2
    assert r.por_nombre("RPM") is r.columnas[1]


def test_una_fila_corta_no_aborta_y_las_celdas_que_faltan_son_ausentes() -> None:
    """§7.10: «se rellena con vacío y se registra; no se aborta». Que la celda
    ausente sea vacía y no 0 es lo que impide que una fila truncada meta un cero
    falso en medio de un canal."""
    filas = [["1", "2", "3"], ["4", "5"], ["6", "7", "8"]]
    r = inferir_tipos(filas, ("a", "b", "c"))
    assert [a.codigo for a in r.avisos] == ["filas_cortas"]
    assert r.columnas[2].vacias == 1
    assert r.columnas[2].con_dato == 2
    assert r.columnas[2].tipo is TipoColumna.ENTERO


def test_una_fila_larga_se_avisa_sin_perder_las_columnas_conocidas() -> None:
    filas = [["1", "2"], ["3", "4", "sobra"]]
    r = inferir_tipos(filas, ("a", "b"))
    assert [a.codigo for a in r.avisos] == ["filas_largas"]
    assert all(c.tipo is TipoColumna.ENTERO for c in r.columnas)


def test_los_avisos_dicen_que_columna_y_con_que_recuento() -> None:
    filas = [["", "5", "1", "x"], ["", "5", "2", "y"]]
    r = inferir_tipos(filas, ("vacia", "fija", "num", "texto"))
    codigos = [a.codigo for a in r.avisos]
    assert "columna_sin_datos" in codigos
    assert "columna_constante" in codigos
    assert any("'vacia'" in a.mensaje for a in r.avisos)
    assert any("'fija'" in a.mensaje and "'5'" in a.mensaje for a in r.avisos)


def test_el_aviso_de_columna_mixta_lleva_ejemplos() -> None:
    filas = [*([str(i)] for i in range(40)), ["ERROR"]]
    r = inferir_tipos(filas, ("presion",))
    mixto = next(a for a in r.avisos if a.codigo == "columna_mixta")
    assert "ERROR" in mixto.mensaje
    assert "nunca 0" in mixto.mensaje


def test_una_columna_de_desbordamiento_avisa_de_que_es_el_sensor(
    catalogo: Catalogo,
) -> None:
    """El aviso tiene que distinguir «canal a otra frecuencia» de «sensor
    desconectado»: son el mismo tipo `VACIA` y dos problemas muy distintos."""
    filas = [["2147483647"], ["2147483647"]]
    r = inferir_tipos(filas, ("aceite",), catalogo=catalogo)
    aviso = next(a for a in r.avisos if a.codigo == "columna_sin_datos")
    assert "desconectado" in aviso.mensaje


def test_sin_filas_todas_las_columnas_son_vacias() -> None:
    """Un fichero cuya muestra no trae ninguna fila de datos no es un error: se
    dice que no se sabe nada de ninguna columna, con `filas_inspeccionadas` a 0
    para que no se lea como una conclusión."""
    r = inferir_tipos([], ("a", "b"))
    assert r.filas_inspeccionadas == 0
    assert all(c.tipo is TipoColumna.VACIA for c in r.columnas)
    assert all(c.celdas == 0 for c in r.columnas)


def test_sin_filas_se_avisa_una_vez_del_fichero_no_una_por_columna() -> None:
    """En el AutoLog serían 476 avisos idénticos, y un informe con 476 líneas
    iguales no lo lee nadie. El hecho es uno y es del fichero."""
    r = inferir_tipos([], tuple(f"col_{i}" for i in range(476)))
    assert [a.codigo for a in r.avisos] == ["sin_filas_de_datos"]
    assert "476" in r.avisos[0].mensaje


# --------------------------------------------------------------------------- #
# Contra los ficheros de muestra
# --------------------------------------------------------------------------- #
def test_muestra_con_tipos_mezclados(catalogo: Catalogo) -> None:
    """`12-texto-y-booleanos.csv` es el fichero que existe justamente para esto:
    una marcha de texto y un limitador booleano junto a canales numéricos."""
    filas, nombres, decimal = de(GENERICOS / "12-texto-y-booleanos.csv")
    r = inferir_tipos(filas, nombres, decimal=decimal, catalogo=catalogo)
    por = {c.nombre: c for c in r.columnas}
    assert por["Time"].tipo is TipoColumna.DECIMAL
    assert por["RPM"].tipo is TipoColumna.ENTERO
    assert por["CLT"].tipo is TipoColumna.DECIMAL
    assert por["Lambda"].tipo is TipoColumna.DECIMAL
    assert por["Limitador"].tipo is TipoColumna.BOOLEANO

    # La marcha trae `1`, `2`, `3` y `N` de punto muerto: 34 celdas numéricas y
    # 16 de texto. Enum es la respuesta correcta y no un apaño -- proponerla
    # numérica perdería TODAS las muestras en punto muerto, que es justo cuando
    # el piloto está cambiando de marcha.
    marcha = por["Marcha"]
    assert marcha.tipo is TipoColumna.ENUM_TEXTO
    assert "N" in marcha.valores_distintos
    assert marcha.numericas and marcha.no_numericas
    assert "enum_con_numeros" in {a.codigo for a in r.avisos}


def test_la_columna_de_marcha_no_pasa_desapercibida_en_el_informe(
    catalogo: Catalogo,
) -> None:
    """Era la única columna del fichero de la que el informe no decía nada: no es
    `VACIA`, no es `CONSTANTE`, no se propone numérica y no es texto libre, así
    que se colaba por todas las ramas de aviso. Y es la primera que hay que
    mirar."""
    filas, nombres, decimal = de(GENERICOS / "12-texto-y-booleanos.csv")
    r = inferir_tipos(filas, nombres, decimal=decimal, catalogo=catalogo)
    aviso = next(a for a in r.avisos if a.codigo == "enum_con_numeros")
    assert "'Marcha'" in aviso.mensaje
    assert "'N'" in aviso.mensaje or '"N"' in aviso.mensaje


def test_muestra_con_valores_ausentes(catalogo: Catalogo) -> None:
    """`11-valores-ausentes.csv`: los huecos no pueden convertir un canal numérico
    en un enum de texto ni bajar su cobertura."""
    filas, nombres, decimal = de(GENERICOS / "11-valores-ausentes.csv")
    r = inferir_tipos(filas, nombres, decimal=decimal, catalogo=catalogo)
    for c in r.columnas:
        assert c.tipo is not TipoColumna.ENUM_TEXTO, c.nombre
        if c.con_dato:
            assert c.cobertura_numerica == pytest.approx(1.0), c.nombre


def test_muestra_con_coma_decimal_no_confunde_el_decimal_con_texto(
    catalogo: Catalogo,
) -> None:
    """`02-puntoycoma-coma.csv` trae `0,050`: con el decimal que FG-02 detecta,
    esas celdas son números. Con el otro serían texto y todas las columnas
    saldrían como enum -- por eso el separador viaja hasta aquí."""
    filas, nombres, decimal = de(GENERICOS / "02-puntoycoma-coma.csv")
    assert decimal == ","
    r = inferir_tipos(filas, nombres, decimal=decimal, catalogo=catalogo)
    assert all(c.es_numerico for c in r.columnas), [
        c.nombre for c in r.columnas if not c.es_numerico
    ]


def test_muestra_numerica_corriente_no_genera_ningun_aviso(catalogo: Catalogo) -> None:
    """Un CSV normal y sano tiene que pasar sin avisos: si los produce, el
    informe de importación se vuelve ruido y nadie lee el que importa."""
    filas, nombres, decimal = de(GENERICOS / "01-coma-punto.csv")
    r = inferir_tipos(filas, nombres, decimal=decimal, catalogo=catalogo)
    assert r.avisos == ()
    assert all(c.es_numerico for c in r.columnas)
