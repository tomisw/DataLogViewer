"""Fuzzing del importador de CSV genérico sobre el corpus y sus mutaciones (FG-15).

QUÉ AÑADE ESTO A LO QUE YA HAY
==============================
`test_fuzzing_formato.py` (F1-36) hace lo mismo para el formato NATIVO y fija el
contrato que este fichero extiende al importador genérico. Y las suites de FG-01 a
FG-08 y FG-14 comprueban cada eslabón contra ficheros elegidos por una persona que
ya sabía qué podía salir mal.

Lo que ninguna de las dos cubre es la **cadena completa sobre entradas que a nadie
se le ocurrieron**: un fichero cuyo delimitador propuesto deja una sola columna,
una fila de unidades que también parece una fila de datos, un `\\x00` en mitad de
un nombre de canal, una comilla sin cerrar que se come el resto del fichero, o
bytes latin-1 en un fichero que declara un BOM de UTF-8.

EL CONTRATO QUE SE FUZZEA, Y POR QUÉ ES EL QUE IMPORTA
=======================================================
`docs/02` §2.5 (regla E1.7) dice que el importador **avisa y sigue** siempre que
pueda producir datos utilizables, y **rechaza** solo cuando seguir daría
resultados silenciosamente equivocados. Para cualquier entrada, eso deja
exactamente dos salidas legítimas:

    1. un resultado válido, con los avisos que hagan falta, o
    2. uno de los errores declarados de `formatos/` — `ErrorDeSondeo`,
       `ErrorDeDecimal`, `ErrorDeEstructura`, `ErrorDeTiempoCsv`,
       `ErrorDeRobustez` — que son rechazos explicados.

Cualquier otra excepción es un fallo del contrato, no un detalle: la capa de
arriba no puede distinguir un `IndexError` de un defecto interno, y acabará
enseñando una traza donde tenía que enseñar «este fichero no se puede leer, y por
esto». El asistente de importación de §7.8 se apoya en esa distinción.

`UnicodeDecodeError` HAY QUE RECHAZARLO A MANO
==============================================
`UnicodeDecodeError` hereda de `UnicodeError`, que hereda de `ValueError`. Un
`except ValueError` que comprobara solo «es un ValueError» daría por bueno un
fallo de decodificación sin tocar, que es justo uno de los defectos que esta
suite tiene que encontrar: el sondeo promete decidir la codificación y no
propagar el fallo de decodificar. Por eso la comprobación es por tipo exacto
contra `ERRORES_DECLARADOS` y `UnicodeDecodeError` está fuera a propósito.

POR QUÉ EL GENERADOR ES DE BIBLIOTECA ESTÁNDAR Y CON SEMILLA
=============================================================
Hypothesis es una dependencia del proyecto y F1-36 la usa, así que aquí también
se usa **cuando está instalada**: da reducción del caso mínimo, que es lo que
convierte un fallo en un informe legible. Pero el barrido principal es un
generador propio de biblioteca estándar con semilla fija, por dos razones:

1. Un fichero que importa Hypothesis en su cabecera no se puede ni recolectar sin
   ella, y entonces en un entorno sin red —el mismo en el que se escribió esta
   cadena de importación— la suite no se ejecutaría en absoluto. Aquí el barrido
   corre siempre y las propiedades de Hypothesis se añaden si se puede.
2. Con semilla fija, un fallo se reproduce con el número que imprime el propio
   aserto. No hace falta base de datos de ejemplos.

LO QUE NO SE FUZZEA, Y POR QUÉ
==============================
La conversión de valores de una columna completa (`formatos/valores_csv.py`,
FG-07) y la de enums (`formatos/enums_csv.py`, FG-08) operan sobre `polars.Series`.
Fuzzearlas con bytes arbitrarios probaría el manejo de errores de Polars, no el
contrato de este proyecto — es la misma exclusión que F1-36 hizo con
`parsear_cuerpo`, y por el mismo motivo. Lo que sí se fuzzea de FG-07 es
`separar_numero_y_unidad`, que es una función de celda y pura.
"""

from __future__ import annotations

import random
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from dlv_core.formatos.decimal_csv import (
    ErrorDeDecimal,
    detectar_separador_decimal,
    es_numerica,
)
from dlv_core.formatos.estructura import (
    ErrorDeEstructura,
    analizar_estructura,
    parece_marca_de_tiempo,
)
from dlv_core.formatos.sondeo import ErrorDeSondeo, dividir_campos, sondear_csv
from dlv_core.formatos.tiempo_csv import ErrorDeTiempoCsv, detectar_columna_de_tiempo
from dlv_core.formatos.tipos import inferir_tipos
from dlv_core.unidades import Catalogo, cargar_catalogo

# `robustez_csv` (FG-14) y `valores_csv` (FG-07) importan Polars en su cabecera, no
# de forma diferida como `reloj.py` y `malla.py`, así que sin Polars el módulo
# entero es inimportable. Se importan aquí de forma tolerante para que el barrido
# —que no necesita Polars para nada— se pueda ejecutar igual, y se anota en el
# informe de la suite lo que quedó fuera. La alternativa era que esta suite no
# corriera en absoluto en el mismo entorno donde se escribió la cadena.
try:
    from dlv_core.formatos.robustez_csv import ErrorDeRobustez, leer_bloque_de_datos

    HAY_ROBUSTEZ = True
except ImportError:  # pragma: no cover — depende del entorno, no del código
    HAY_ROBUSTEZ = False

    class ErrorDeRobustez(ValueError):  # type: ignore[no-redef]
        """Sustituto para que el contrato de excepciones siga nombrándolo."""


try:
    from dlv_core.formatos.valores_csv import separar_numero_y_unidad

    HAY_VALORES = True
except ImportError:  # pragma: no cover — depende del entorno, no del código
    HAY_VALORES = False

RAIZ = Path(__file__).resolve().parents[2]
MUESTRAS = RAIZ / "samples"

with (RAIZ / "data" / "units.toml").open("rb") as _fh:
    CATALOGO: Catalogo = cargar_catalogo(_fh)

#: Las únicas excepciones que el importador tiene derecho a lanzar. Se comprueba
#: por pertenencia a esta tupla y NO por «es un ValueError», porque
#: `UnicodeDecodeError` también lo es (ver la cabecera).
ERRORES_DECLARADOS = (
    ErrorDeSondeo,
    ErrorDeDecimal,
    ErrorDeEstructura,
    ErrorDeTiempoCsv,
    ErrorDeRobustez,
)

#: Semilla del barrido. Fija a propósito: un fallo se reproduce con este número.
SEMILLA = 20260810

#: Cuántas entradas genera el barrido. Suficientes para que las mutaciones se
#: combinen, y bastante rápido para correr en cada `verificar.py`.
N_CASOS = 600

#: Trozos con los que se construyen los ficheros sintéticos. Cada uno está aquí
#: porque rompió algo en alguna de las tareas FG-01 a FG-14, no por variedad.
FRAGMENTOS: tuple[str, ...] = (
    "",
    "\n",
    "\r\n",
    "\r",
    ",",
    ";",
    "\t",
    "|",
    '"',
    '"sin cerrar',
    '""',
    "Time,RPM,MAP",
    "s,rpm,kPa",
    "0.000,850,32.6",
    "0,000;850;32,6",
    "1.234.567,89",
    "1,234,567.89",
    "1 234,5",
    "1 234,5",  # espacio duro: lo usan exportadores europeos
    "1 234,5",  # espacio fino
    "12.5 psi",
    "92,4 °C",
    "850rpm",
    "1e-3",
    "-0",
    "NaN",
    "#N/A",
    "---",
    "-",
    "NULL",
    "2147483647",
    "true,false",
    "on,off",
    "sí,no",
    "N",
    "Log : 20260729 06:30:35",
    "notas: cambios, y una vuelta",
    "λ",
    "°",
    "%",
    "\x00",
    "\x1b[31m",
    "col,col,col",  # nombres duplicados
    "0.000,850",  # fila corta
    "0.000,850,32.6,de sobra",  # fila larga
    "18:30:35.506,1456",
    "2026-07-29T18:30:35Z,1456",
    "1753812635,1456",
    "﻿Time,RPM",
    "a" * 300,
    "0." + "0" * 40 + "1",
    "9" * 40,
)


def _generador() -> random.Random:
    return random.Random(SEMILLA)


def _fichero_sintetico(aleatorio: random.Random) -> bytes:
    """Un fichero construido pegando fragmentos, con mutaciones de bytes.

    No pretende ser un CSV plausible: pretende ser lo que llega cuando el usuario
    arrastra el fichero equivocado, un log a medio escribir o un CSV exportado por
    una herramienta que nadie ha visto.
    """
    n = aleatorio.randint(0, 14)
    lineas = [aleatorio.choice(FRAGMENTOS) for _ in range(n)]
    texto = aleatorio.choice(("\n", "\r\n", "\r", "")).join(lineas)

    if aleatorio.random() < 0.25:
        texto = unicodedata.normalize("NFD", texto)

    codificacion = aleatorio.choice(("utf-8", "latin-1", "utf-16"))
    try:
        datos = texto.encode(codificacion)
    except UnicodeEncodeError:
        datos = texto.encode("utf-8", errors="replace")

    # Mutaciones a nivel de byte: es lo que produce las secuencias que ninguna
    # codificación explica, y el caso que el sondeo tiene que resolver sin
    # propagar el fallo de decodificar.
    if datos and aleatorio.random() < 0.4:
        for _ in range(aleatorio.randint(1, 3)):
            i = aleatorio.randrange(len(datos))
            datos = datos[:i] + bytes([aleatorio.randrange(256)]) + datos[i + 1 :]
    if datos and aleatorio.random() < 0.2:
        datos = datos[: aleatorio.randrange(len(datos))]  # truncado
    if aleatorio.random() < 0.15:
        datos = b"\xef\xbb\xbf" + datos  # BOM de UTF-8 sobre contenido que no lo es

    return datos


def _cadena_completa(datos: bytes) -> dict[str, Any]:
    """La cadena de decisiones del importador, de bytes a tipos por columna.

    Devuelve lo que produjo cada eslabón para que las invariantes se comprueben
    sobre el conjunto y no eslabón a eslabón: varios de los defectos que se
    encontraron al construir FG-03 y FG-04 solo aparecen cuando la salida de uno
    entra en el siguiente.
    """
    sondeo = sondear_csv(datos)
    texto = datos.decode(sondeo.codificacion, errors="replace")
    decimales = detectar_separador_decimal(sondeo, texto)
    estructura = analizar_estructura(sondeo, decimales, texto)
    filas, nombres = _bloque_de_datos(texto, sondeo, estructura)
    _comprobar_robustez(texto, sondeo, estructura, "cadena")
    tiempo = detectar_columna_de_tiempo(sondeo, decimales, estructura, texto)
    tipos = inferir_tipos(filas, nombres, decimal=decimales.separador, catalogo=CATALOGO)
    return {
        "sondeo": sondeo,
        "texto": texto,
        "decimales": decimales,
        "estructura": estructura,
        "filas": filas,
        "nombres": nombres,
        "tiempo": tiempo,
        "tipos": tipos,
    }


def _bloque_de_datos(
    texto: str, sondeo: Any, estructura: Any
) -> tuple[list[list[str]], tuple[str, ...]]:
    """Las filas de la MUESTRA inspeccionada y los nombres, para `inferir_tipos`.

    Se parten con `dividir_campos` y no con `robustez_csv.leer_bloque_de_datos`
    (FG-14), y no es una concesión al entorno: FG-14 devuelve un
    `polars.DataFrame` y `inferir_tipos` consume filas de cadenas, así que
    encadenarlos exigiría recorrer el DataFrame fila a fila en Python, que es
    justo lo que prohíbe ADR-009. La muestra acotada es además lo que la cabecera
    de `tipos.py` declara consumir.

    Las invariantes propias de FG-14 se comprueban aparte, en
    `_comprobar_robustez`, sobre su `tabla` y sus recuentos.
    """
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    filas = [
        dividir_campos(ln, sondeo.delimitador or ",", sondeo.comilla)
        for ln in lineas[estructura.linea_inicio_datos :]
    ]
    return filas, estructura.nombres_o_posicionales()


def _comprobar_robustez(texto: str, sondeo: Any, estructura: Any, etiqueta: str) -> None:
    """Las invariantes de FG-14, cuando Polars permite ejecutarlo.

    Se llama desde `_ejecutar` para que un fallo suyo cuente igual que uno de
    cualquier otro eslabón: FG-14 promete no abortar por una fila de longitud
    variable, por columnas duplicadas ni por una cabecera sin nombres.
    """
    if not HAY_ROBUSTEZ:
        return
    lectura = leer_bloque_de_datos(texto, sondeo, estructura)
    assert len(set(lectura.nombres)) == len(lectura.nombres), (
        f"{etiqueta}: FG-14 devolvió nombres duplicados: {lectura.nombres}"
    )
    assert len(lectura.nombres) == len(lectura.tabla.columns), (
        f"{etiqueta}: {len(lectura.nombres)} nombres para "
        f"{len(lectura.tabla.columns)} columnas de la tabla"
    )
    assert lectura.filas_de_datos >= 0
    assert lectura.filas_cortas >= 0
    assert lectura.filas_largas >= 0


def _ejecutar(datos: bytes, etiqueta: str) -> dict[str, Any] | None:
    """La cadena, con el contrato de excepciones aplicado.

    Devuelve el resultado, o `None` si el importador rechazó la entrada con uno
    de sus errores declarados —que es una salida legítima—.
    """
    try:
        return _cadena_completa(datos)
    except ERRORES_DECLARADOS:
        return None
    except UnicodeDecodeError as exc:
        raise AssertionError(
            f"{etiqueta}: se propagó un UnicodeDecodeError ({exc}). El sondeo decide "
            f"la codificación, así que decodificar no puede fallar hacia arriba. "
            f"Entrada: {datos!r}"
        ) from exc
    except Exception as exc:
        raise AssertionError(
            f"{etiqueta}: {type(exc).__name__}: {exc}. Solo se admiten "
            f"{[e.__name__ for e in ERRORES_DECLARADOS]} o un resultado válido "
            f"(docs/02 §2.5, regla E1.7). Entrada: {datos!r}"
        ) from exc


def _comprobar_invariantes(r: dict[str, Any], etiqueta: str) -> None:
    """Lo que tiene que cumplir cualquier resultado, sea el fichero lo que sea."""
    sondeo, estructura, nombres, tipos = (
        r["sondeo"],
        r["estructura"],
        r["nombres"],
        r["tipos"],
    )
    lineas_utiles = [ln for ln in r["texto"].splitlines() if ln.strip()]

    assert sondeo.n_campos >= 1, f"{etiqueta}: se propuso un formato de 0 campos"
    assert 0 <= estructura.linea_inicio_datos <= len(lineas_utiles), (
        f"{etiqueta}: los datos empiezan en la línea {estructura.linea_inicio_datos} "
        f"de {len(lineas_utiles)}"
    )
    assert estructura.n_columnas >= 1, f"{etiqueta}: estructura con 0 columnas"

    # Una columna por nombre, siempre: es lo que permite que la tabla de canales
    # del asistente (§7.8) no tenga huecos ni columnas sin rótulo.
    assert len(tipos.columnas) == len(nombres), (
        f"{etiqueta}: {len(tipos.columnas)} columnas tipadas para {len(nombres)} nombres"
    )

    for col in tipos.columnas:
        # El recuento tiene que cerrar. Si no cierra, alguna celda se contó dos
        # veces o ninguna, y entonces las fracciones del informe mienten.
        suma = (
            col.vacias
            + col.centinelas_texto
            + col.centinelas_desbordamiento
            + col.numericas
            + col.no_numericas
        )
        assert suma == col.celdas, (
            f"{etiqueta}: la columna {col.nombre!r} suma {suma} celdas de {col.celdas}"
        )
        assert 0.0 <= col.cobertura_numerica <= 1.0, f"{etiqueta}: cobertura fuera de rango"
        # La regla de §7.10 que más caro sale romper: una columna sin ningún dato
        # no puede acabar con un valor constante, que es lo que pasaría si las
        # ausencias se contaran como ceros.
        if col.con_dato == 0:
            assert col.valor_constante is None, (
                f"{etiqueta}: la columna {col.nombre!r} no tiene datos y declara "
                f"la constante {col.valor_constante!r}"
            )


# --------------------------------------------------------------------------- #
# El barrido: entradas sintéticas
# --------------------------------------------------------------------------- #
def test_barrido_sintetico_respeta_el_contrato_de_excepciones() -> None:
    """`N_CASOS` ficheros generados con `SEMILLA`: ninguno puede salirse de las
    dos salidas legítimas, y los que se completan cumplen las invariantes."""
    aleatorio = _generador()
    completados = rechazados = 0
    for i in range(N_CASOS):
        datos = _fichero_sintetico(aleatorio)
        r = _ejecutar(datos, f"caso {i} (semilla {SEMILLA})")
        if r is None:
            rechazados += 1
        else:
            completados += 1
            _comprobar_invariantes(r, f"caso {i} (semilla {SEMILLA})")

    # Que el barrido esté haciendo algo: si TODO se rechaza, la suite pasaría sin
    # ejercitar ninguna invariante, y si nada se rechaza, el generador no está
    # produciendo basura de verdad.
    assert completados > 0, "ningún caso llegó a completar la cadena"
    assert rechazados > 0, "ningún caso fue rechazado: el generador no genera basura"


def test_el_barrido_es_reproducible() -> None:
    """Dos barridos con la misma semilla generan exactamente las mismas entradas.

    Sin esto, un fallo del barrido anterior no se podría reproducir y el número de
    caso del mensaje de error no significaría nada.
    """
    a = [_fichero_sintetico(_generador()) for _ in range(5)]
    b = [_fichero_sintetico(_generador()) for _ in range(5)]
    assert a == b


def test_la_cadena_es_determinista() -> None:
    """La misma entrada da el mismo resultado dos veces.

    Parece obvio y no lo es: cualquier recorrido de un `set` o de un diccionario
    por orden de hash podría colarse en una decisión —el delimitador elegido, el
    orden de los avisos— y entonces el mismo fichero se importaría distinto en dos
    ejecuciones, que es de los defectos más difíciles de diagnosticar.
    """
    aleatorio = _generador()
    for i in range(60):
        datos = _fichero_sintetico(aleatorio)
        primero = _ejecutar(datos, f"caso {i} (1.ª vez)")
        segundo = _ejecutar(datos, f"caso {i} (2.ª vez)")
        if primero is None or segundo is None:
            assert primero is None and segundo is None, (
                f"caso {i}: la cadena rechazó la entrada solo una de las dos veces"
            )
            continue
        assert primero["sondeo"] == segundo["sondeo"], f"caso {i}: sondeo no determinista"
        assert primero["estructura"] == segundo["estructura"], f"caso {i}: estructura"
        assert [c.tipo for c in primero["tipos"].columnas] == [
            c.tipo for c in segundo["tipos"].columnas
        ], f"caso {i}: tipos por columna no deterministas"


# --------------------------------------------------------------------------- #
# El corpus real y sus mutaciones (el «sobre el corpus» del título de la tarea)
# --------------------------------------------------------------------------- #
def _ficheros_del_corpus() -> list[Path]:
    return sorted(
        p
        for carpeta in ("generico", "corrupt", "dos-formatos")
        for p in (MUESTRAS / carpeta).glob("*.csv")
    )


def test_el_corpus_entero_pasa_la_cadena() -> None:
    """Todos los CSV de `samples/` recorren la cadena sin excepción inesperada.

    Los de `samples/corrupt/` están ahí para ser rechazados o tolerados con aviso;
    lo que ninguno puede hacer es reventar con una excepción que no sea del
    contrato.
    """
    ficheros = _ficheros_del_corpus()
    assert ficheros, "no se encontró el corpus de CSV en samples/"
    for ruta in ficheros:
        r = _ejecutar(ruta.read_bytes(), f"corpus {ruta.name}")
        if r is not None:
            _comprobar_invariantes(r, f"corpus {ruta.name}")


def test_los_genericos_bien_formados_no_se_rechazan() -> None:
    """`samples/generico/` son ficheros legítimos, algunos raros pero válidos: la
    cadena tiene que completarlos, no rechazarlos. Un importador que rechaza un
    CSV correcto es tan inútil como uno que acepta basura."""
    for ruta in sorted((MUESTRAS / "generico").glob("*.csv")):
        r = _ejecutar(ruta.read_bytes(), f"genérico {ruta.name}")
        assert r is not None, f"{ruta.name} es un CSV genérico legítimo y la cadena lo rechazó"
        assert r["tipos"].columnas, f"{ruta.name}: ninguna columna tipada"


def test_mutaciones_del_corpus_no_rompen_el_contrato() -> None:
    """Cada fichero del corpus, mutado: truncado en un punto cualquiera, con
    bytes cambiados y con una línea repetida o borrada.

    Es el caso realista de un log a medio escribir cuando se corta la
    alimentación de la ECU, y el de un fichero copiado con un error de un byte.
    """
    aleatorio = _generador()
    for ruta in _ficheros_del_corpus():
        original = ruta.read_bytes()
        for k in range(6):
            datos = original
            modo = aleatorio.randrange(4)
            if modo == 0 and len(datos) > 1:
                datos = datos[: aleatorio.randrange(1, len(datos))]
            elif modo == 1 and datos:
                for _ in range(aleatorio.randint(1, 5)):
                    i = aleatorio.randrange(len(datos))
                    datos = datos[:i] + bytes([aleatorio.randrange(256)]) + datos[i + 1 :]
            elif modo == 2:
                lineas = datos.split(b"\n")
                if len(lineas) > 2:
                    i = aleatorio.randrange(len(lineas))
                    del lineas[i]
                    datos = b"\n".join(lineas)
            else:
                lineas = datos.split(b"\n")
                if len(lineas) > 2:
                    i = aleatorio.randrange(len(lineas))
                    lineas.insert(i, lineas[i])
                    datos = b"\n".join(lineas)

            etiqueta = f"{ruta.name} mutado (modo {modo}, {k})"
            r = _ejecutar(datos, etiqueta)
            if r is not None:
                _comprobar_invariantes(r, etiqueta)


# --------------------------------------------------------------------------- #
# Funciones de celda, que son puras y se pueden fuzzear una a una
# --------------------------------------------------------------------------- #
def test_funciones_de_celda_no_lanzan_con_cualquier_cadena() -> None:
    """`es_numerica`, `parece_marca_de_tiempo`, `dividir_campos` y
    `separar_numero_y_unidad` se llaman una vez por celda del bloque
    inspeccionado. Ninguna puede lanzar: si lanzan, tumban la importación entera
    por una celda rara, que es lo contrario de «avisa y sigue»."""
    aleatorio = _generador()
    for i in range(400):
        celda = aleatorio.choice(FRAGMENTOS)
        if aleatorio.random() < 0.5:
            celda += aleatorio.choice(FRAGMENTOS)
        for decimal in (".", ","):
            assert isinstance(es_numerica(celda, decimal), bool), f"caso {i}"
            if HAY_VALORES:
                numero, unidad = separar_numero_y_unidad(celda, decimal)
                assert numero is None or isinstance(numero, str), f"caso {i}"
                assert unidad is None or isinstance(unidad, str), f"caso {i}"
        assert isinstance(parece_marca_de_tiempo(celda), bool), f"caso {i}"
        for delimitador in (",", ";", "\t", "|"):
            for comilla in ('"', "'", None):
                campos = dividir_campos(celda, delimitador, comilla)
                assert isinstance(campos, list), f"caso {i}"
                assert campos, "dividir_campos nunca devuelve una lista vacía"


@pytest.mark.skipif(not HAY_VALORES, reason="valores_csv (FG-07) necesita Polars")
def test_separar_numero_y_unidad_nunca_devuelve_cero_por_una_celda_vacia() -> None:
    """La regla de §7.10 en la función que más fácil la rompe: una celda sin
    número no da «0», da «no hay número». Un 0 inventado aquí se convierte en un
    punto en el gráfico y en un mínimo falso en la tabla."""
    for celda in ("", "   ", "psi", "---", "#N/A", "-", "NaN"):
        numero, _unidad = separar_numero_y_unidad(celda, ".")
        assert numero is None or numero.strip() not in ("0", "0.0", ""), (
            f"{celda!r} produjo el número {numero!r}"
        )


# --------------------------------------------------------------------------- #
# Propiedades con Hypothesis, cuando está instalada
# --------------------------------------------------------------------------- #
# Se importa de forma condicional a propósito: en la cabecera haría que el
# fichero entero no se pudiera recolectar sin Hypothesis, y entonces el barrido
# de arriba —que no necesita nada— tampoco se ejecutaría. F1-36 la importa en la
# cabecera porque allí Polars ya es obligatorio de todas formas.
try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st

    HAY_HYPOTHESIS = True
except ImportError:  # pragma: no cover — depende del entorno, no del código
    HAY_HYPOTHESIS = False

if HAY_HYPOTHESIS:

    @given(st.binary(max_size=4096))
    @settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_bytes_arbitrarios_respetan_el_contrato(datos: bytes) -> None:
        """Lo que aporta Hypothesis sobre el barrido: si falla, reduce la entrada
        al mínimo que sigue fallando, y eso convierte un `bytes` de 4 kB en un
        caso de dos bytes que se puede leer."""
        r = _ejecutar(datos, "hypothesis binary")
        if r is not None:
            _comprobar_invariantes(r, "hypothesis binary")

    @given(
        st.lists(st.sampled_from(FRAGMENTOS), max_size=12),
        st.sampled_from(("\n", "\r\n", "\r")),
    )
    @settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_combinaciones_de_fragmentos_respetan_el_contrato(lineas: list[str], fin: str) -> None:
        """El mismo contrato sobre ficheros que SÍ parecen CSV: es donde la cadena
        toma decisiones de verdad en vez de rechazar por el primer eslabón."""
        datos = fin.join(lineas).encode("utf-8", errors="replace")
        r = _ejecutar(datos, "hypothesis fragmentos")
        if r is not None:
            _comprobar_invariantes(r, "hypothesis fragmentos")


def test_se_declara_si_hypothesis_no_estaba() -> None:
    """No es una comprobación del código: es que el informe de la suite diga si
    las propiedades con reducción se ejecutaron o no. Un verde que en realidad no
    ejecutó la mitad de la suite es peor que un rojo."""
    ausentes = [
        nombre
        for nombre, presente in (
            ("Hypothesis (propiedades con reducción de caso mínimo)", HAY_HYPOTHESIS),
            ("robustez_csv de FG-14 (necesita Polars)", HAY_ROBUSTEZ),
            ("valores_csv de FG-07 (necesita Polars)", HAY_VALORES),
        )
        if not presente
    ]
    if ausentes:
        pytest.skip(
            "el barrido con semilla y el corpus SÍ se han ejecutado; quedó fuera: "
            + "; ".join(ausentes)
        )
