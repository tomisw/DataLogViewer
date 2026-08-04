"""Sondeo de un CSV desconocido: codificación, fin de línea, delimitador y
comillas (tarea FG-01).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.4, pasos 1, 2, 3 y 5.
Los pasos 4 (separador decimal), 6-7 (estructura) y 8-10 (tiempo, tipos, roles)
son FG-02, FG-03, FG-04, FG-05 y FG-09: este módulo se para justo antes, y lo
dice para que nadie lo amplíe por conveniencia.

QUÉ ES ESTE MÓDULO Y QUÉ NO
===========================
Es lo que hace que el proyecto sirva para cualquier CSV y no solo para el
Haltech. Y es **una propuesta, no un hecho**: §7.4 lo dice explícitamente, todo
pasa por el asistente de importación antes de cargarse. De ahí que `Sondeo`
devuelva la puntuación de cada candidato y no solo el ganador — el asistente
tiene que poder enseñar por qué propone `;` y no `,`, y el usuario tiene que
poder discrepar con información delante.

NO SE USA `csv.Sniffer`
=======================
§7.4 lo descarta por nombre: es poco fiable con estos ficheros. Puntúa por
frecuencia de caracteres, así que un CSV con coma decimal y `;` de delimitador
—el CSV español típico— le sale con delimitador `,`, y entonces `12,5` se parte
en dos columnas. Aquí se puntúa por **consistencia del número de campos entre
líneas**, que es una propiedad estructural del fichero y no una estadística de
caracteres. Hay una prueba literal que comprueba que `Sniffer` no ha vuelto.

CÓMO SE PUNTÚA UN DELIMITADOR
=============================
Para cada combinación de (delimitador, comilla) se cuentan los campos de cada
línea y se busca la **racha más larga de líneas seguidas con el mismo número de
campos**. La puntuación es la longitud de esa racha dividida por las líneas que
había disponibles desde donde empieza.

La racha, y no la moda de todas las líneas, es la decisión de fondo del módulo.
Un CSV es siempre una cola contigua de filas con el mismo número de campos, con
cero o más líneas de otra cosa delante: preámbulo de metadatos
(`samples/generico/14-preambulo-largo.csv`), o la cabecera del formato nativo.
Puntuar por la moda global se rompe en cuanto lo de delante es más largo que la
muestra de datos, y eso pasa con un caso real: la cabecera de un Haltech son más
de cien líneas de `Channel : RPM`, así que en los primeros 64 kB hay más líneas
de cabecera que de datos y la moda de campos con `,` es 1. **La primera versión
de este módulo puntuaba por la moda y no sabía leer el formato nativo del
propietario por el camino genérico**, que es justo la red de seguridad que §7.15
pide para cuando un descriptor no reconoce una variante.

Como efecto secundario útil, `PuntuacionCandidato.linea_inicio` dice dónde
empieza el bloque de datos. Aquí no se interpreta —separar preámbulo, nombres y
unidades es FG-03— pero se informa, porque ya está calculado.

El recuento es **consciente de las comillas**: sin eso, un campo entrecomillado
que contenga el delimitador rompe el conteo de esa línea, y una sola línea así
basta para cambiar el ganador en un fichero corto. Por eso se puntúan las
combinaciones y no el delimitador por su cuenta: qué comilla hay y qué
delimitador hay son la misma pregunta, y resolverlas por separado obliga a
adivinar una para averiguar la otra.

LA TRUNCACIÓN NO PUEDE CAMBIAR LA CODIFICACIÓN DETECTADA
========================================================
El sondeo mira los primeros 64 kB, y ese corte puede caer en medio de un
carácter multibyte. Decodificar en estricto fallaría y el fichero se declararía
latin-1 por un byte cortado, no por su contenido. `_decodificar` recorta la cola
incompleta antes de decidir.

Solo biblioteca estándar. Este módulo no abre ficheros: recibe los bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dlv_core.informes import Aviso

__all__ = [
    "BYTES_DE_SONDEO",
    "CANDIDATOS_COMILLA",
    "CANDIDATOS_DELIMITADOR",
    "CONFIANZA_MINIMA",
    "RACHA_MINIMA",
    "ErrorDeSondeo",
    "Escape",
    "FinDeLinea",
    "PuntuacionCandidato",
    "Sondeo",
    "sondear_csv",
]

#: Los primeros 64 kB, como dice §7.4. Bastan para el preámbulo, la cabecera y
#: decenas de filas de datos, y no obligan a leer un fichero de 500 MB para
#: proponer un delimitador.
BYTES_DE_SONDEO = 65536

#: Los cinco de §7.4. El orden es el de desempate cuando dos candidatos puntúan
#: exactamente igual, y va de más específico a más ambiguo: el espacio es el
#: último porque cualquier texto lo tiene.
CANDIDATOS_DELIMITADOR = (",", ";", "\t", "|", " ")

#: `None` primero: un fichero sin comillas es lo normal, y probar `"` antes haría
#: que un fichero con una comilla suelta en un nombre de canal («Sensor "A"») se
#: interpretara como entrecomillado.
CANDIDATOS_COMILLA: tuple[str | None, ...] = (None, '"', "'")

#: Por debajo de esto el sondeo no propone delimitador: prefiere decir que no
#: sabe antes que proponer uno que parte los datos de forma equivocada.
CONFIANZA_MINIMA = 0.6

#: Líneas seguidas que tiene que tener una racha para contar. Con cinco
#: delimitadores candidatos, dos líneas coincidiendo por casualidad es corriente.
RACHA_MINIMA = 3

_BOMS: tuple[tuple[bytes, str], ...] = (
    # UTF-32 antes que UTF-16: su BOM empieza por el de UTF-16 LE.
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


class ErrorDeSondeo(ValueError):
    """No se puede sondear estos bytes sin inventar."""


class FinDeLinea(Enum):
    CRLF = "\r\n"
    LF = "\n"
    CR = "\r"

    @property
    def etiqueta(self) -> str:
        return self.name


class Escape(Enum):
    """Cómo se escapa la comilla dentro de un campo entrecomillado (§7.4 paso 5)."""

    DOBLADA = "doblada"
    """`""` — lo que hace Excel y lo que dice RFC 4180."""

    BARRA = "barra"
    """`\\"` — lo que hacen algunos exportadores de herramientas Unix."""

    NINGUNO = "ninguno"
    """No hay comillas, o no se ha visto ninguna escapada."""


@dataclass(slots=True, frozen=True)
class PuntuacionCandidato:
    """Una combinación de (delimitador, comilla) y cómo de bien explica el fichero.

    Se devuelve al asistente entera, no solo la ganadora: proponer `;` sin poder
    enseñar que `,` dejaba el 40 % de las líneas descuadradas no es una propuesta,
    es una imposición.
    """

    delimitador: str
    comilla: str | None
    n_campos: int
    """Campos de la mejor RACHA (ver `consistencia`), no de la línea más común."""

    lineas_consistentes: int
    """Longitud de la racha: líneas seguidas con `n_campos` campos."""

    linea_inicio: int
    """Índice (0-based, sobre las líneas no vacías) donde empieza la racha.

    Mayor que cero significa que hay algo delante de los datos: preámbulo de
    metadatos, normalmente. Aquí no se interpreta —eso es FG-03— pero se informa,
    porque es la mitad del trabajo que esa tarea tiene que hacer y ya está
    calculado."""

    lineas_examinadas: int

    @property
    def consistencia(self) -> float:
        """Qué fracción de las líneas **desde el inicio de la racha** explica.

        La racha y no la moda global, y esto es la decisión de fondo del módulo.
        Un CSV es siempre una cola contigua de filas con el mismo número de
        campos, con cero o más líneas de otra cosa delante. Puntuar por la moda de
        todas las líneas se rompe en cuanto lo de delante es más largo que la
        muestra de datos, y eso pasa con un caso real y no hipotético: la cabecera
        de un Haltech son más de cien líneas de `Channel : RPM`, así que en los
        primeros 64 kB hay más líneas de cabecera que de datos y la moda de campos
        con `,` es 1. Con la moda, el sondeo genérico no sabía leer el formato
        nativo del propietario.
        """
        disponibles = self.lineas_examinadas - self.linea_inicio
        if disponibles <= 0:
            return 0.0
        return self.lineas_consistentes / disponibles

    @property
    def cobertura(self) -> float:
        """Fracción del total que ocupa la racha. Es lo que delata un preámbulo:
        consistencia 1,0 con cobertura 0,7 significa «perfecto, pero hay un 30 %
        de líneas delante que no son datos»."""
        if self.lineas_examinadas == 0:
            return 0.0
        return self.lineas_consistentes / self.lineas_examinadas

    @property
    def clave_de_orden(self) -> tuple[float, int, int, int]:
        """Consistencia, racha más larga, más campos, preferencia del candidato.

        «Más campos» desempata a favor de la interpretación más informativa: en
        `Time;RPM` leído con `,` sale 1 campo perfectamente consistente, y con `;`
        salen 2. Las dos son «consistentes»; solo una separa los datos.
        """
        return (
            self.consistencia,
            self.lineas_consistentes,
            self.n_campos,
            -CANDIDATOS_DELIMITADOR.index(self.delimitador),
        )


@dataclass(slots=True, frozen=True)
class Sondeo:
    """Lo que el sondeo propone. **Una propuesta, no un hecho** (§7.4)."""

    codificacion: str
    tiene_bom: bool
    fin_de_linea: FinDeLinea
    finales_mezclados: bool
    delimitador: str | None
    """`None` cuando ninguna combinación llega a `CONFIANZA_MINIMA`. No es un
    fallo: un fichero de una sola columna existe, y proponer un delimitador que
    parte los datos mal es peor que admitir que no se sabe."""

    comilla: str | None
    escape: Escape
    n_campos: int
    candidatos: tuple[PuntuacionCandidato, ...]
    elegido: PuntuacionCandidato | None
    """La combinación que se propone, o `None` si ninguna llegó al mínimo.

    Se guarda aparte en vez de asumir que es `candidatos[0]`: los candidatos
    vienen ordenados por puntuación, pero el primero puede ser uno descartado por
    no separar nada (`n_campos == 1` puntúa perfecto y no dice nada). La primera
    versión leía `candidatos[0]` y devolvía la confianza de un candidato que no
    era el elegido."""

    lineas_examinadas: int
    truncado: bool
    """`True` si el sondeo vio solo una parte del fichero: lo normal con un log
    de verdad, y lo que explica que la propuesta pueda fallar más adelante."""

    avisos: tuple[Aviso, ...] = ()

    @property
    def confianza(self) -> float:
        return self.elegido.consistencia if self.elegido is not None else 0.0

    @property
    def linea_inicio_datos(self) -> int:
        """Dónde empieza el bloque consistente. Lo aprovecha FG-03."""
        return self.elegido.linea_inicio if self.elegido is not None else 0

    @property
    def parametros_de_lectura(self) -> dict[str, object]:
        """Lo que hace falta pasarle a un lector de CSV.

        Se devuelve como diccionario y no como argumentos concretos de Polars a
        propósito: `dlv-core` no conoce el motor de lectura, y ADR-002 dice que
        no debe. Quien lea traduce.
        """
        return {
            "codificacion": self.codificacion,
            "delimitador": self.delimitador,
            "comilla": self.comilla,
            "fin_de_linea": self.fin_de_linea.value,
        }


# --------------------------------------------------------------------------- #
# Codificación
# --------------------------------------------------------------------------- #
def _bom(datos: bytes) -> tuple[str, int] | None:
    for firma, codificacion in _BOMS:
        if datos.startswith(firma):
            # `utf-8-sig`, `utf-16` y `utf-32` consumen su propio BOM al
            # decodificar, así que no se descuenta aquí.
            return codificacion, len(firma)
    return None


def _recortar_cola_incompleta(datos: bytes, codificacion: str, avisos: list[Aviso]) -> str:
    """Decodifica descartando los bytes de un carácter partido por el corte.

    Se prueban hasta 4 bytes menos, que es el carácter más largo de UTF-8. Sin
    esto, un fichero UTF-8 perfectamente válido cuyo byte 65 536 cae en medio de
    una «ñ» se declararía latin-1 por el corte y no por su contenido, y todos los
    nombres de canal con acentos saldrían mal.
    """
    for recorte in range(5):
        fin = len(datos) - recorte
        try:
            return datos[:fin].decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(codificacion, datos, 0, 1, "no decodificable")


def _decodificar(datos: bytes, avisos: list[Aviso]) -> tuple[str, str, bool]:
    """(texto, codificación, tiene_bom), siguiendo el paso 1 de §7.4."""
    encontrado = _bom(datos)
    if encontrado is not None:
        codificacion, _ = encontrado
        try:
            return _recortar_cola_incompleta(datos, codificacion, avisos), codificacion, True
        except UnicodeDecodeError:
            avisos.append(
                Aviso(
                    "bom_incoherente",
                    f"el fichero declara un BOM de {codificacion} pero su contenido no "
                    "decodifica con esa codificación; se sigue por el camino sin BOM",
                )
            )

    try:
        return _recortar_cola_incompleta(datos, "utf-8", avisos), "utf-8", False
    except UnicodeDecodeError:
        pass

    # Latin-1 nunca falla —los 256 bytes son válidos— así que es el último
    # recurso por definición, y por eso se avisa: no es una detección, es una
    # rendición. Un nombre de canal con acentos puede salir mal y el usuario
    # tiene que poder cambiarlo en el asistente.
    avisos.append(
        Aviso(
            "codificacion_supuesta",
            "el fichero no es UTF-8 válido y no trae BOM: se lee como latin-1. Los "
            "nombres de canal con acentos pueden salir mal; confírmalo en el asistente",
        )
    )
    return datos.decode("latin-1"), "latin-1", False


# --------------------------------------------------------------------------- #
# Fin de línea
# --------------------------------------------------------------------------- #
def _fin_de_linea(texto: str, avisos: list[Aviso]) -> tuple[FinDeLinea, bool]:
    crlf = texto.count("\r\n")
    lf_solos = texto.count("\n") - crlf
    cr_solos = texto.count("\r") - crlf
    cuenta = {FinDeLinea.CRLF: crlf, FinDeLinea.LF: lf_solos, FinDeLinea.CR: cr_solos}
    presentes = {k: v for k, v in cuenta.items() if v > 0}

    if not presentes:
        # Una sola línea sin salto final: válido (docs/01 §1.13). Se propone LF
        # porque es lo que produce cualquier escritor moderno, y da igual: sin
        # saltos no hay nada que partir.
        return FinDeLinea.LF, False

    mezclados = len(presentes) > 1
    if mezclados:
        detalle = ", ".join(f"{k.etiqueta}={v}" for k, v in sorted(presentes.items(), key=str))
        avisos.append(
            Aviso(
                "finales_de_linea_mezclados",
                f"el fichero mezcla finales de línea ({detalle}). Se usa el mayoritario; "
                "suele significar que el log se editó con dos herramientas distintas",
            )
        )
    return max(presentes.items(), key=lambda kv: kv[1])[0], mezclados


# --------------------------------------------------------------------------- #
# Delimitador y comillas
# --------------------------------------------------------------------------- #
def _contar_campos(linea: str, delimitador: str, comilla: str | None) -> int:
    """Campos de una línea, respetando las comillas.

    No usa `csv.reader` porque hace falta contar con combinaciones que pueden ser
    absurdas —parte del trabajo es descubrir que lo son— y `csv` lanza o
    normaliza en casos que aquí solo tienen que puntuar mal.
    """
    if comilla is None:
        return linea.count(delimitador) + 1

    campos = 1
    dentro = False
    i = 0
    n = len(linea)
    while i < n:
        c = linea[i]
        if c == "\\" and dentro and i + 1 < n:
            i += 2  # escape por barra: el siguiente carácter no cuenta
            continue
        if c == comilla:
            if dentro and i + 1 < n and linea[i + 1] == comilla:
                i += 2  # comilla doblada dentro del campo
                continue
            dentro = not dentro
        elif not dentro and linea.startswith(delimitador, i):
            campos += 1
            i += len(delimitador)
            continue
        i += 1
    return campos


def _puntuar(lineas: list[str], delimitador: str, comilla: str | None) -> PuntuacionCandidato:
    """La racha más larga de líneas seguidas con el mismo número de campos.

    Con empate en longitud gana la racha que empieza ANTES: si dos bloques del
    fichero tienen la misma longitud, el de arriba es el que incluye la fila de
    nombres, y perderla haría que FG-03 buscara los nombres dentro de los datos.
    """
    campos = [_contar_campos(linea, delimitador, comilla) for linea in lineas]
    mejor = PuntuacionCandidato(
        delimitador=delimitador,
        comilla=comilla,
        n_campos=campos[0],
        lineas_consistentes=0,
        linea_inicio=0,
        lineas_examinadas=len(lineas),
    )
    inicio = 0
    for i in range(1, len(campos) + 1):
        if i < len(campos) and campos[i] == campos[inicio]:
            continue
        largo = i - inicio
        if largo > mejor.lineas_consistentes:
            mejor = PuntuacionCandidato(
                delimitador=delimitador,
                comilla=comilla,
                n_campos=campos[inicio],
                lineas_consistentes=largo,
                linea_inicio=inicio,
                lineas_examinadas=len(lineas),
            )
        inicio = i
    return mejor


def _escape_detectado(lineas: list[str], comilla: str | None) -> Escape:
    if comilla is None:
        return Escape.NINGUNO
    doblada = comilla * 2
    for linea in lineas:
        if f"\\{comilla}" in linea:
            return Escape.BARRA
        if doblada in linea:
            return Escape.DOBLADA
    return Escape.NINGUNO


def _lineas_utiles(texto: str) -> list[str]:
    """Las líneas no vacías de la muestra, sin la última si está cortada.

    NO hay límite de número de líneas, y quitarlo fue un arreglo, no una omisión.
    La primera versión se quedaba con las 200 primeras «porque con más no se
    decide mejor», y con eso el AutoLog real era indetectable: sus 475 canales dan
    1 895 líneas de cabecera, así que las 200 primeras son todas cabecera y en la
    muestra no entraba ni una fila de datos. Los datos empiezan en el byte 42 345,
    dentro de los 64 kB; era el límite de líneas, no el de bytes, el que los
    escondía.

    El coste ya está acotado por los 64 kB de la muestra, que es el límite que de
    verdad importa: un fichero de 500 MB se sondea igual de rápido que uno de 50 kB.

    La última línea de un sondeo truncado casi siempre está a medias, y una línea a
    medias tiene menos campos de los que le tocan: dejarla dentro penalizaría al
    delimitador correcto justo en los ficheros grandes, que son todos los reales.
    """
    crudas = texto.splitlines()
    if len(crudas) > 1 and not texto.endswith(("\n", "\r")):
        crudas = crudas[:-1]
    return [linea for linea in crudas if linea.strip()]


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def sondear_csv(datos: bytes, *, max_bytes: int = BYTES_DE_SONDEO) -> Sondeo:
    """Propone cómo leer estos bytes como CSV (§7.4, pasos 1-3 y 5).

    `datos` puede ser el fichero completo o solo su principio. Lo que se decida
    aquí es una propuesta para el asistente de §7.8; nada se carga sin que el
    usuario lo confirme.
    """
    if not datos:
        raise ErrorDeSondeo("no hay bytes que sondear: el fichero está vacío")

    truncado = len(datos) > max_bytes
    muestra = datos[:max_bytes]
    avisos: list[Aviso] = []

    texto, codificacion, tiene_bom = _decodificar(muestra, avisos)
    fin, mezclados = _fin_de_linea(texto, avisos)
    lineas = _lineas_utiles(texto)
    if not lineas:
        raise ErrorDeSondeo(
            "el fichero no tiene ninguna línea con contenido: no hay nada que sondear"
        )

    # Solo se prueban las comillas que APARECEN en la muestra. No es una
    # aproximación: si el carácter no está en el fichero, la interpretación
    # entrecomillada y la no entrecomillada dan exactamente el mismo recuento, así
    # que la combinación es redundante. Y sí importa para el presupuesto: el
    # recuento consciente de comillas es un bucle de caracteres en Python, mientras
    # que el no entrecomillado es un `str.count` en C. Con el AutoLog real —1 909
    # líneas en los primeros 64 kB— probar las 15 combinaciones costaba 94 ms;
    # probar solo las que pueden cambiar algo lo baja a una fracción de eso.
    comillas = (None, *(c for c in CANDIDATOS_COMILLA if c is not None and c in texto))
    candidatos = sorted(
        (
            _puntuar(lineas, delimitador, comilla)
            for delimitador in CANDIDATOS_DELIMITADOR
            for comilla in comillas
        ),
        key=lambda p: p.clave_de_orden,
        reverse=True,
    )
    # Dos filtros, y los dos hacen falta:
    #  - `n_campos > 1`: con un campo el delimitador no aparece en el fichero, y
    #    una consistencia perfecta ahí no dice absolutamente nada.
    #  - racha de al menos `RACHA_MINIMA`: con cinco delimitadores candidatos, dos
    #    líneas seguidas coincidiendo por casualidad es corriente, y una racha de
    #    dos al final del fichero daría consistencia 1,0.
    # La racha mínima se acota por el número de líneas disponibles: un fichero de
    # una o dos líneas —una cabecera sin datos todavía— no puede tener una racha de
    # tres, y rechazarlo por eso dejaría sin delimitador a un `Time,RPM,MAP` que
    # cualquiera lee de un vistazo. La guarda sigue entera para los ficheros
    # normales, que son los que pueden engañarla.
    racha_minima = min(RACHA_MINIMA, len(lineas))
    utiles = [p for p in candidatos if p.n_campos > 1 and p.lineas_consistentes >= racha_minima]
    mejor = utiles[0] if utiles else None

    if mejor is None or mejor.consistencia < CONFIANZA_MINIMA:
        motivo = (
            "ninguno de los delimitadores candidatos aparece en el fichero"
            if mejor is None
            else (
                f"el mejor candidato ({mejor.delimitador!r}) solo explica el "
                f"{mejor.consistencia:.0%} de las líneas, por debajo del "
                f"{CONFIANZA_MINIMA:.0%} exigido"
            )
        )
        avisos.append(
            Aviso(
                "delimitador_sin_determinar",
                f"{motivo}. Puede ser un fichero de una sola columna, o un formato que "
                "el sondeo no cubre; hay que elegir el delimitador en el asistente",
            )
        )
        return Sondeo(
            codificacion=codificacion,
            tiene_bom=tiene_bom,
            fin_de_linea=fin,
            finales_mezclados=mezclados,
            delimitador=None,
            comilla=None,
            escape=Escape.NINGUNO,
            n_campos=1,
            candidatos=tuple(candidatos),
            elegido=None,
            lineas_examinadas=len(lineas),
            truncado=truncado,
            avisos=tuple(avisos),
        )

    if mejor.cobertura < 1.0:
        sueltas = mejor.lineas_examinadas - mejor.lineas_consistentes
        avisos.append(
            Aviso(
                "campos_inconsistentes",
                f"con delimitador {mejor.delimitador!r} hay {sueltas} de "
                f"{mejor.lineas_examinadas} líneas examinadas que no tienen "
                f"{mejor.n_campos} campos; el bloque consistente empieza en la línea "
                f"{mejor.linea_inicio + 1}. Suele ser el preámbulo de metadatos o la "
                "cabecera del formato (los separa FG-03), o filas malformadas (FG-01 no "
                "las juzga)",
            )
        )

    return Sondeo(
        codificacion=codificacion,
        tiene_bom=tiene_bom,
        fin_de_linea=fin,
        finales_mezclados=mezclados,
        delimitador=mejor.delimitador,
        comilla=mejor.comilla,
        escape=_escape_detectado(lineas, mejor.comilla),
        n_campos=mejor.n_campos,
        candidatos=tuple(candidatos),
        elegido=mejor,
        lineas_examinadas=len(lineas),
        truncado=truncado,
        avisos=tuple(avisos),
    )
