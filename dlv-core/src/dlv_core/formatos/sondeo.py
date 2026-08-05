"""Sondeo del formato de un fichero de texto: codificación, fin de línea,
delimitador y comillas (tarea FG-01).

Es el paso 1 del importador de CSV genérico, `docs/07-formatos-y-csv-generico.md`
§7.4 pasos 1, 2, 3 y 5. Los pasos 4 (separador decimal), 6 (estructura) y
siguientes son FG-02 y FG-03 y **no** se hacen aquí: este módulo se queda en la
tipografía del fichero, sin interpretar ni un solo número.

Como el resto de `dlv-core` (ADR-002), no abre ficheros: recibe los primeros
bytes ya leídos por quien llama. `LIMITE_MUESTRA` (64 kB, §7.4) es lo máximo que
mira, aunque le pasen el fichero entero.

EL VEREDICTO NO BASTA: HAY QUE PODER REVISARLO
==============================================
Cada aspecto se devuelve como una `Deteccion` con tres cosas —valor, `confianza`
y `evidencia`—, y el vocabulario de `confianza` es el mismo de
`data/formats/haltech_nsp.toml`, para que no haya dos escalas en el proyecto:

    confirmed  la estructura del fichero lo decide sin ambigüedad
    inferred   plausible y sin contraejemplo, pero hay otra lectura posible
    unknown    no deducible con la muestra disponible

`unknown` **no es un fallo**: es la señal de que el asistente de importación
(§7.8) tiene que preguntar en vez de dar por bueno. La detección es «una
propuesta, no un hecho» (§7.4), así que este módulo nunca lanza excepciones:
para cualquier secuencia de bytes devuelve un `Sondeo`, con los avisos que hagan
falta. Es la misma regla E1.7 que cumple el parser nativo —avisa y sigue—, solo
que aquí no queda ni un caso de rechazo: un fichero indescifrable se sondea con
confianza `unknown`, y quien decide es la persona.

EL DELIMITADOR SE DECIDE POR CONSISTENCIA, NO POR FRECUENCIA
===========================================================
Es la única decisión de este módulo que se hace mal a menudo, y el motivo por el
que §7.4 prohíbe expresamente `csv.Sniffer`. Contar separadores y quedarse con
el más frecuente falla en los dos casos que más aparecen en Europa:

    nombre;nota;rpm              8 comas y 6 puntos y coma, y el delimitador
    "a,b,c";"d,e";100            es el punto y coma
    "f,g,h";"i,j";200

    Time;RPM;MAP                 la coma decimal produce 5 comas por fila, más
    0,050;4107;56,38             que puntos y coma, y el delimitador sigue
    0,100;5873;48,04             siendo el punto y coma

Lo que sí distingue al delimitador de verdad es que **parte todas las líneas en
el mismo número de campos**. Se puntúa cada candidato por el número de líneas
que coinciden con su recuento de campos más repetido (la moda), exigiendo moda
≥ 2 —un solo campo por línea no es una partición, es no haber partido nada— y
se desempata por la moda mayor, nunca por cuántas veces aparece el carácter.

El segundo ejemplo de arriba es el que obliga a ser honesto: la coma también es
consistente ahí (5 comas en todas las filas de datos), y solo pierde por la
línea de cabecera, que no lleva ninguna. Cuando el segundo candidato queda a
menos del 10 % del mejor, el veredicto baja a `inferred` y se emite el aviso
`delimitador_ambiguo`: quien lo resuelve del todo es FG-02, que mira si los
tokens `\\d+,\\d+` son números y no columnas.

El espacio, quinto candidato de §7.4, se puntúa aparte y solo si ninguno de los
otros cuatro parte la muestra: el motivo, medido sobre `samples/real/`, está en
el comentario de `DELIMITADOR_ULTIMO_RECURSO`.

Las comillas se puntúan **a la vez** que el delimitador, no después, porque las
dos decisiones dependen la una de la otra: un campo entrecomillado con el
delimitador dentro solo se cuenta bien si ya se sabe cuál es la comilla. Para
cada hipótesis (delimitador, comilla) se recuenta el fichero entero y gana la
que produce una partición más consistente; ante empate gana la hipótesis sin
comillas, que es la que menos supone.

LA CODIFICACIÓN SE DECIDE POR ESTRUCTURA
========================================
Nada de frecuencias de letras ni de tablas por idioma. Por orden: BOM (decide
solo), patrón de bytes nulos en posiciones pares o impares (UTF-16 sin BOM, que
es estructura pura), validez estricta de UTF-8 (una secuencia multibyte válida
no sale por casualidad) y, si todo lo anterior falla, latin-1 con `unknown`,
porque latin-1 no puede fallar nunca y por tanto tampoco puede confirmar nada:
ninguna estructura distingue latin-1 de cp1252 ni de las demás ISO-8859.

ADR-009
=======
No hay bucles por muestra. El sondeo trabaja sobre una muestra acotada a 64 kB y
todo el recuento —líneas, campos, comillas— se hace con máscaras de NumPy sobre
el buffer completo: `cumsum` para la paridad de comillas y `searchsorted` para
repartir los delimitadores entre líneas. Los únicos bucles de Python recorren
las 15 hipótesis (5 delimitadores × 3 comillas), no los datos.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from typing import Final

import numpy as np

from dlv_core.informes import Aviso

__all__ = [
    "CANDIDATOS_COMILLA",
    "CANDIDATOS_DELIMITADOR",
    "LIMITE_MUESTRA",
    "Deteccion",
    "PuntuacionDelimitador",
    "Sondeo",
    "sondear",
]

# §7.4: «sobre los primeros 64 kB». Es a la vez el techo de coste del sondeo
# (todo lo de aquí es lineal sobre la muestra) y el motivo de que la confianza
# de la codificación distinga entre muestra completa y muestra truncada.
LIMITE_MUESTRA: Final = 64 * 1024

# Orden de preferencia ante empate absoluto, de más a menos frecuente en logs de
# ECU (§7.4 paso 3).
DELIMITADORES_PRINCIPALES: Final = (",", ";", "\t", "|")

# El espacio es el quinto candidato de §7.4, pero **solo se prueba si ninguno de
# los cuatro anteriores parte la muestra**, y aun entonces su veredicto no pasa
# de `inferred`. El motivo está medido sobre `samples/real/`: la cabecera de un
# log Haltech son líneas `Channel : Coolant Temperature`, y en el AutoLog de 475
# canales los primeros 64 kB son cabecera entera. Puntuando el espacio de igual
# a igual, ese fichero salía con delimitador ' ' y 3 campos —1415 líneas de
# acuerdo— porque «clave : valor» es, tipográficamente, un fichero de tres
# columnas separadas por espacios. Cualquier CSV con preámbulo de metadatos
# tiene el mismo problema, y es el falso positivo más caro de este paso: un
# delimitador equivocado no rompe nada visible, produce columnas que no son.
DELIMITADOR_ULTIMO_RECURSO: Final = " "
CANDIDATOS_DELIMITADOR: Final = (*DELIMITADORES_PRINCIPALES, DELIMITADOR_ULTIMO_RECURSO)
CANDIDATOS_COMILLA: Final = ('"', "'")

CONFIRMADA: Final = "confirmed"
INFERIDA: Final = "inferred"
DESCONOCIDA: Final = "unknown"

BOM_UTF8: Final = b"\xef\xbb\xbf"
BOM_UTF16_LE: Final = b"\xff\xfe"
BOM_UTF16_BE: Final = b"\xfe\xff"
BOM_UTF32_LE: Final = b"\xff\xfe\x00\x00"
BOM_UTF32_BE: Final = b"\x00\x00\xfe\xff"

_LF: Final = 0x0A
_CR: Final = 0x0D

# Fracción de bytes nulos en posiciones alternas a partir de la cual se acepta
# UTF-16 sin BOM. Texto ASCII en UTF-16 da ~1,0; un CSV latin-1 da 0. El umbral
# es bajo porque el otro lado de la comprobación (ninguno en las posiciones
# contrarias) es el que de verdad excluye los falsos positivos.
_UMBRAL_NULOS: Final = 0.3

# El segundo candidato a delimitador tiene que quedar por debajo de esta
# fracción del mejor para que el veredicto se dé por confirmado.
_MARGEN_AMBIGUEDAD: Final = 0.9


@dataclass(slots=True, frozen=True)
class Deteccion:
    """Un aspecto del formato, con por qué se decidió así.

    `evidencia` está redactada para que se lea en el informe de importación y en
    la revisión de la puerta G1 sin abrir el código: dice qué se contó, no qué
    se concluyó.
    """

    aspecto: str
    valor: str | None
    confianza: str
    evidencia: str

    @property
    def es_fiable(self) -> bool:
        """`True` si el asistente puede precargar el valor sin preguntar.

        `inferred` también lo es: la propuesta se muestra rellena y el usuario
        la confirma o la cambia (§7.8). Con `unknown` el asistente tiene que
        pedirlo, porque proponer un valor que nadie ha podido deducir es
        exactamente el fallo de R1 por otra puerta.
        """
        return self.confianza in (CONFIRMADA, INFERIDA)

    def __str__(self) -> str:
        valor = "—" if self.valor is None else repr(self.valor)
        return f"{self.aspecto}: {valor} [{self.confianza}] — {self.evidencia}"


@dataclass(slots=True, frozen=True)
class PuntuacionDelimitador:
    """Lo que puntuó una hipótesis (delimitador, comilla) sobre la muestra.

    Es la evidencia del veredicto del delimitador, y se devuelve entera —las 15
    hipótesis, ordenadas— porque lo que hay que poder revisar en la puerta G1 no
    es el ganador sino la distancia con el segundo.
    """

    delimitador: str
    comilla: str | None
    n_campos: int
    """Recuento de campos más repetido entre las líneas no vacías (la moda)."""
    lineas_de_acuerdo: int
    """Cuántas líneas se parten exactamente en `n_campos` campos."""
    lineas_examinadas: int

    @property
    def cobertura(self) -> float:
        if self.lineas_examinadas == 0:
            return 0.0
        return self.lineas_de_acuerdo / self.lineas_examinadas

    def __str__(self) -> str:
        comilla = "sin comillas" if self.comilla is None else f"comilla {self.comilla!r}"
        return (
            f"{self.delimitador!r} ({comilla}): {self.lineas_de_acuerdo} de "
            f"{self.lineas_examinadas} líneas con {self.n_campos} campos"
        )


@dataclass(slots=True, frozen=True)
class Sondeo:
    """Resultado del sondeo. Ningún campo es una orden: todos son propuestas."""

    codificacion: Deteccion
    fin_de_linea: Deteccion
    delimitador: Deteccion
    comillas: Deteccion
    texto: str
    """La muestra ya decodificada y **sin BOM**.

    Se devuelve para que FG-02 y FG-03 no tengan que volver a decidir la
    codificación ni acordarse de descontar el BOM. Es la lección de
    `docs/09` §9.10: un contrato que obliga a recordar un desplazamiento falla
    por tres bytes y en silencio.
    """
    bytes_de_bom: int
    """Cuántos bytes de BOM se descontaron: `datos[bytes_de_bom:]` es lo que se
    decodificó. Lo necesita quien tenga que volver a los bytes originales."""
    muestra_truncada: bool
    """`True` si la muestra no es el fichero entero. Baja la confianza de la
    codificación cuando lo visto es solo ASCII."""
    puntuaciones: tuple[PuntuacionDelimitador, ...]
    """Las hipótesis con moda ≥ 2, de mejor a peor. Vacía si ninguna partió el
    fichero en más de una columna."""
    avisos: tuple[Aviso, ...]

    @property
    def n_campos(self) -> int | None:
        """Campos por línea según la hipótesis ganadora, o `None` si no hay."""
        return self.puntuaciones[0].n_campos if self.puntuaciones else None

    def resumen(self) -> str:
        """Las cuatro decisiones y su evidencia, una por línea.

        Es lo que se enseña en la revisión de la puerta G1 y lo que se pega en
        el informe de importación.
        """
        lineas = [
            str(self.codificacion),
            str(self.fin_de_linea),
            str(self.delimitador),
            str(self.comillas),
        ]
        lineas.extend(f"aviso: {a}" for a in self.avisos)
        return "\n".join(lineas)


def sondear(datos: bytes, *, tamano_total: int | None = None) -> Sondeo:
    """Sonda los primeros bytes de un fichero de texto. Nunca lanza excepciones.

    `datos` son los primeros bytes del fichero, ya leídos por quien llama; de
    ellos solo se miran `LIMITE_MUESTRA`. `tamano_total`, si se conoce, sirve
    para saber si la muestra es el fichero entero: sin él se supone truncada en
    cuanto llega al límite, que es el supuesto prudente.
    """
    muestra = datos[:LIMITE_MUESTRA]
    if tamano_total is None:
        truncada = len(datos) >= LIMITE_MUESTRA
    else:
        truncada = tamano_total > len(muestra)

    avisos: list[Aviso] = []

    if not muestra:
        vacio = "la muestra no tiene ni un byte"
        nada = Deteccion("delimitador", None, DESCONOCIDA, vacio)
        avisos.append(Aviso("muestra_vacia", "no hay bytes que sondear"))
        return Sondeo(
            codificacion=Deteccion("codificacion", None, DESCONOCIDA, vacio),
            fin_de_linea=Deteccion("fin_de_linea", None, DESCONOCIDA, vacio),
            delimitador=nada,
            comillas=Deteccion("comillas", None, DESCONOCIDA, vacio),
            texto="",
            bytes_de_bom=0,
            muestra_truncada=truncada,
            puntuaciones=(),
            avisos=tuple(avisos),
        )

    texto, bytes_de_bom, codificacion = _decodificar(muestra, truncada, avisos)
    fin_de_linea = _detectar_fin_de_linea(texto, avisos)
    delimitador, comillas, puntuaciones = _detectar_delimitador_y_comillas(
        texto, truncada=truncada, avisos=avisos
    )

    return Sondeo(
        codificacion=codificacion,
        fin_de_linea=fin_de_linea,
        delimitador=delimitador,
        comillas=comillas,
        texto=texto,
        bytes_de_bom=bytes_de_bom,
        muestra_truncada=truncada,
        puntuaciones=puntuaciones,
        avisos=tuple(avisos),
    )


# --------------------------------------------------------------------------- #
# Paso 1: codificación
# --------------------------------------------------------------------------- #
def _decodifica_o_none(datos: bytes, codec: str, truncada: bool) -> str | None:
    """Decodifica en estricto, o `None` si esos bytes no son de ese codec.

    Se usa un decodificador incremental con `final=False` cuando la muestra está
    truncada: así una secuencia multibyte partida por el corte de los 64 kB se
    queda en el buffer en vez de contar como error de codificación. Sin esto, un
    UTF-8 perfectamente válido se degradaría a latin-1 una de cada pocas veces,
    según dónde cayera el corte.
    """
    decodificador = codecs.getincrementaldecoder(codec)("strict")
    try:
        return decodificador.decode(datos, not truncada)
    except UnicodeDecodeError:
        return None


def _evidencia_utf16(nulos: int, total: int, orden: str, codec: str) -> str:
    porcentaje = 100.0 * nulos / total if total else 0.0
    return (
        f"sin BOM, pero el {porcentaje:.0f} % de los bytes en posición {orden} son nulos "
        f"y ninguno en las contrarias: es el patrón de {codec}"
    )


def _utf16_sin_bom(muestra: bytes, truncada: bool) -> tuple[str, str, str] | None:
    """(codec, texto, evidencia) si el patrón de nulos delata UTF-16, o `None`.

    Es estructura, no estadística de letras: en UTF-16 el texto ASCII deja un
    byte nulo por carácter, siempre en las posiciones impares (LE) o siempre en
    las pares (BE). Ninguna otra codificación de las que se ven en un CSV mete
    bytes nulos, así que el patrón contrario —cero nulos en las posiciones que
    no tocan— es lo que hace fiable la detección.

    LÍMITE CONOCIDO: un UTF-16 **sin BOM** cuyo texto no sea mayoritariamente
    ASCII (un CSV con cabeceras en japonés, por ejemplo) no deja ese patrón y no
    se detecta; se leería como latin-1 y saldría con confianza `unknown`, que es
    lo que hace que el asistente pregunte en vez de dar por bueno. Un UTF-16 con
    BOM no tiene este problema, y es lo que exporta Excel.
    """
    arr = np.frombuffer(muestra, dtype=np.uint8)
    pares, impares = arr[0::2], arr[1::2]
    if pares.size == 0 or impares.size == 0:
        return None
    nulos_pares = int(np.count_nonzero(pares == 0))
    nulos_impares = int(np.count_nonzero(impares == 0))

    if nulos_impares / impares.size >= _UMBRAL_NULOS and nulos_pares == 0:
        texto = _decodifica_o_none(muestra, "utf-16-le", truncada)
        if texto is not None:
            return (
                "utf-16-le",
                texto,
                _evidencia_utf16(nulos_impares, impares.size, "impar", "utf-16-le"),
            )
    if nulos_pares / pares.size >= _UMBRAL_NULOS and nulos_impares == 0:
        texto = _decodifica_o_none(muestra, "utf-16-be", truncada)
        if texto is not None:
            return (
                "utf-16-be",
                texto,
                _evidencia_utf16(nulos_pares, pares.size, "par", "utf-16-be"),
            )
    return None


def _decodificar(muestra: bytes, truncada: bool, avisos: list[Aviso]) -> tuple[str, int, Deteccion]:
    """(texto sin BOM, bytes de BOM descontados, detección de la codificación)."""
    # 1. BOM. Decide solo y sin discusión, y es lo primero porque el de UTF-32 LE
    #    empieza por el de UTF-16 LE: mirarlos en el otro orden leería un fichero
    #    UTF-32 como UTF-16 y produciría texto plausible lleno de nulos.
    boms = (
        (BOM_UTF32_LE, "utf-32-le"),
        (BOM_UTF32_BE, "utf-32-be"),
        (BOM_UTF8, "utf-8"),
        (BOM_UTF16_LE, "utf-16-le"),
        (BOM_UTF16_BE, "utf-16-be"),
    )
    for bom, codec in boms:
        if not muestra.startswith(bom):
            continue
        texto = _decodifica_o_none(muestra[len(bom) :], codec, truncada)
        if texto is not None:
            return (
                texto,
                len(bom),
                Deteccion(
                    "codificacion",
                    codec,
                    CONFIRMADA,
                    f"BOM de {codec} ({len(bom)} bytes) al principio del fichero",
                ),
            )
        # BOM que miente sobre lo que viene detrás. Raro, pero pasa con ficheros
        # concatenados a mano; se sigue por el camino normal y se avisa, porque
        # el fichero es utilizable y quien lo mire tiene que saber esto.
        avisos.append(
            Aviso(
                "bom_incoherente",
                f"el fichero lleva BOM de {codec} pero los bytes siguientes no son "
                f"{codec} válido; se ignora el BOM y se detecta por estructura",
            )
        )
        break

    # 2. UTF-16 sin BOM, por el patrón de bytes nulos.
    utf16 = _utf16_sin_bom(muestra, truncada)
    if utf16 is not None:
        codec, texto, evidencia = utf16
        return texto, 0, Deteccion("codificacion", codec, INFERIDA, evidencia)

    if b"\x00" in muestra:
        avisos.append(
            Aviso(
                "bytes_nulos",
                f"la muestra tiene {muestra.count(0)} bytes nulos sin el patrón regular "
                "de UTF-16; puede ser un fichero binario o un texto dañado",
            )
        )

    # 3. UTF-8 estricto. Una secuencia multibyte válida no aparece por
    #    casualidad, así que validar es decidir; no hace falta puntuar nada.
    texto = _decodifica_o_none(muestra, "utf-8", truncada)
    if texto is not None:
        no_ascii = int(np.count_nonzero(np.frombuffer(muestra, dtype=np.uint8) >= 0x80))
        if no_ascii:
            return (
                texto,
                0,
                Deteccion(
                    "codificacion",
                    "utf-8",
                    CONFIRMADA,
                    f"{no_ascii} bytes ≥ 0x80 y todos forman secuencias UTF-8 válidas",
                ),
            )
        # Solo ASCII: utf-8, latin-1 y cp1252 dan exactamente el mismo texto, así
        # que la elección no puede equivocarse... sobre lo que se ha visto. Si la
        # muestra está truncada, el primer acento del fichero está más allá.
        return (
            texto,
            0,
            Deteccion(
                "codificacion",
                "utf-8",
                INFERIDA if truncada else CONFIRMADA,
                "solo ASCII: utf-8, latin-1 y cp1252 coinciden byte a byte"
                + (
                    f" en los primeros {len(muestra)} bytes, que no son el fichero entero"
                    if truncada
                    else " en todo el fichero"
                ),
            ),
        )

    # 4. Ni UTF-8 ni UTF-16: latin-1, que no puede fallar y por eso tampoco puede
    #    confirmar nada. §7.4 paso 1 lo llama «latin-1 con aviso».
    arr = np.frombuffer(muestra, dtype=np.uint8)
    altos = int(np.count_nonzero(arr >= 0x80))
    c1 = int(np.count_nonzero((arr >= 0x80) & (arr <= 0x9F)))
    pista = (
        f"; {c1} de ellos entre 0x80 y 0x9F, que en latin-1 son controles sin "
        "representación: es más probable que el fichero sea cp1252"
        if c1
        else ""
    )
    avisos.append(
        Aviso(
            "codificacion_no_utf8",
            f"la muestra no es UTF-8 válido; se lee como latin-1{pista}. "
            "Confirma la codificación en el asistente si aparecen caracteres raros",
        )
    )
    return (
        muestra.decode("latin-1"),
        0,
        Deteccion(
            "codificacion",
            "latin-1",
            DESCONOCIDA,
            f"{altos} bytes ≥ 0x80 que no son UTF-8 válido; latin-1 decodifica "
            "cualquier byte, así que no distingue entre latin-1, cp1252 y las "
            "demás ISO-8859",
        ),
    )


# --------------------------------------------------------------------------- #
# Paso 2: fin de línea
# --------------------------------------------------------------------------- #
def _detectar_fin_de_linea(texto: str, avisos: list[Aviso]) -> Deteccion:
    """CRLF / LF / CR / mixto, contando sobre el texto ya decodificado.

    Se cuenta sobre el texto y no sobre los bytes por UTF-16: ahí un CRLF son
    cuatro bytes con nulos intercalados y buscar `b"\\r\\n"` no encuentra nada.
    """
    crlf = texto.count("\r\n")
    lf = texto.count("\n") - crlf
    cr = texto.count("\r") - crlf
    evidencia = f"{crlf} CRLF, {lf} LF sueltos, {cr} CR sueltos"

    presentes = [nombre for nombre, n in (("CRLF", crlf), ("LF", lf), ("CR", cr)) if n]
    if not presentes:
        avisos.append(
            Aviso(
                "sin_fin_de_linea",
                "la muestra no tiene ningún salto de línea: el fichero es de una sola "
                "línea o el corte de la muestra cayó dentro de la primera",
            )
        )
        return Deteccion("fin_de_linea", None, DESCONOCIDA, evidencia)

    if len(presentes) > 1:
        avisos.append(
            Aviso(
                "fin_de_linea_mixto",
                f"el fichero mezcla finales de línea ({evidencia}); se parte por "
                "cualquiera de ellos, pero suele indicar un fichero editado o "
                "concatenado a mano",
            )
        )
        return Deteccion("fin_de_linea", "mixto", CONFIRMADA, evidencia)

    return Deteccion("fin_de_linea", presentes[0], CONFIRMADA, evidencia)


# --------------------------------------------------------------------------- #
# Pasos 3 y 5: delimitador y comillas
# --------------------------------------------------------------------------- #
def _mascara_dentro_de_comillas(arr: np.ndarray, comilla: str | None) -> np.ndarray:
    """Máscara de «esta posición está dentro de un campo entrecomillado».

    Paridad acumulada de comillas, que también resuelve gratis el escape por
    doblado (`""` dentro de un campo): dos comillas seguidas cambian el estado
    dos veces y lo dejan como estaba.
    """
    if comilla is None:
        return np.zeros(arr.size, dtype=np.bool_)
    q = arr == ord(comilla)
    # Prefijo exclusivo: la comilla que abre no está «dentro», la que cierra sí,
    # y ninguna de las dos es un delimitador, así que da igual para el recuento.
    return ((np.cumsum(q, dtype=np.int64) - q) % 2).astype(np.bool_)


def _lineas(arr: np.ndarray, dentro: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(inicios, finales) de cada línea, partiendo solo por LF fuera de comillas.

    Un salto de línea dentro de un campo entrecomillado es parte del valor, no
    un fin de registro: partir por él inventaría una fila corta y dejaría a la
    siguiente con campos de menos.
    """
    cortes = np.flatnonzero((arr == _LF) & ~dentro)
    inicios = np.concatenate((np.zeros(1, dtype=np.int64), cortes + 1))
    finales = np.concatenate((cortes, np.array([arr.size], dtype=np.int64)))
    return inicios, finales


def _puntuar(
    arr: np.ndarray,
    dentro: np.ndarray,
    inicios: np.ndarray,
    finales: np.ndarray,
    delimitador: str,
    comilla: str | None,
) -> PuntuacionDelimitador | None:
    """Puntúa una hipótesis, o `None` si no parte el fichero en ≥ 2 columnas.

    Todo el recuento es vectorizado: las posiciones de los delimitadores fuera
    de comillas se reparten entre líneas con `searchsorted`, sin recorrer ni una
    línea en Python (ADR-009).
    """
    if arr.size == 0:
        return None
    posiciones = np.flatnonzero((arr == ord(delimitador)) & ~dentro)
    n_campos = (
        np.searchsorted(posiciones, finales) - np.searchsorted(posiciones, inicios) + 1
    ).astype(np.int64)

    # Las líneas vacías no dicen nada del delimitador y hundirían la cobertura de
    # cualquier fichero con una línea en blanco al final. «Vacía» incluye la que
    # solo trae el CR de un CRLF.
    longitudes = finales - inicios
    primera = arr[np.minimum(inicios, arr.size - 1)]
    vacias = (longitudes <= 0) | ((longitudes == 1) & (primera == _CR))
    n_campos = n_campos[~vacias]
    if n_campos.size == 0:
        return None

    conteos = np.bincount(n_campos)
    # Un solo campo por línea no es una partición: es el candidato que no
    # aparece. Se anula para que no gane por mayoría en un fichero donde ningún
    # delimitador sirve.
    conteos[: min(2, conteos.size)] = 0
    if conteos.size < 2 or conteos.max() == 0:
        return None
    moda = int(conteos.argmax())
    return PuntuacionDelimitador(
        delimitador=delimitador,
        comilla=comilla,
        n_campos=moda,
        lineas_de_acuerdo=int(conteos[moda]),
        lineas_examinadas=int(n_campos.size),
    )


def _puntuar_todas(
    arr: np.ndarray, texto: str, delimitadores: tuple[str, ...]
) -> list[PuntuacionDelimitador]:
    """Las hipótesis (delimitador, comilla) que parten la muestra, de mejor a peor."""
    puntuaciones: list[PuntuacionDelimitador] = []
    for comilla in (None, *CANDIDATOS_COMILLA):
        # Una comilla que no aparece en el texto da exactamente la misma
        # partición que la hipótesis sin comillas; puntuarla otra vez solo
        # llenaría la tabla de evidencia de filas repetidas.
        if comilla is not None and comilla not in texto:
            continue
        dentro = _mascara_dentro_de_comillas(arr, comilla)
        inicios, finales = _lineas(arr, dentro)
        for delimitador in delimitadores:
            p = _puntuar(arr, dentro, inicios, finales, delimitador, comilla)
            if p is not None:
                puntuaciones.append(p)
    puntuaciones.sort(key=_clave, reverse=True)
    return puntuaciones


def _clave(p: PuntuacionDelimitador) -> tuple[int, int, bool, int]:
    """Orden de las hipótesis: consistencia primero, frecuencia nunca.

    1. cuántas líneas coinciden con la moda —esto es «consistencia»—;
    2. cuántos campos produce, que desempata a favor de la partición más fina
       cuando dos candidatos son igual de consistentes (un CSV de comas donde
       cada fila lleva además un punto y coma dentro de un texto);
    3. sin comillas antes que con comillas, que es la hipótesis que menos supone;
    4. el orden de `CANDIDATOS_DELIMITADOR` como último recurso.
    """
    return (
        p.lineas_de_acuerdo,
        p.n_campos,
        p.comilla is None,
        -CANDIDATOS_DELIMITADOR.index(p.delimitador),
    )


def _fronteras_de_comilla(arr: np.ndarray, delimitador: str, comilla: str) -> tuple[int, int]:
    """(aperturas, cierres): comillas pegadas a un delimitador o a un fin de línea.

    Es lo que distingue una comilla que **delimita campos** de una que forma
    parte del texto (`12" de llanta`, `O'Brien`). Sin esta comprobación, un
    apóstrofo suelto en una columna de notas convertiría a `'` en la comilla del
    fichero y desplazaría todo lo que viniera detrás.
    """
    if arr.size == 0:
        return 0, 0
    q = arr == ord(comilla)
    if not q.any():
        return 0, 0
    cod = ord(delimitador)
    anterior = np.empty(arr.size, dtype=arr.dtype)
    anterior[0] = _LF
    anterior[1:] = arr[:-1]
    siguiente = np.empty(arr.size, dtype=arr.dtype)
    siguiente[-1] = _LF
    siguiente[:-1] = arr[1:]
    frontera_izq = (anterior == cod) | (anterior == _LF) | (anterior == _CR)
    frontera_der = (siguiente == cod) | (siguiente == _LF) | (siguiente == _CR)
    return int(np.count_nonzero(q & frontera_izq)), int(np.count_nonzero(q & frontera_der))


def _recortar_linea_incompleta(texto: str, truncada: bool) -> str:
    """Quita la última línea si el corte de la muestra la dejó a medias.

    Una línea cortada por la mitad tiene menos campos de los que le tocan y
    contaría como desacuerdo, bajando la confianza de un fichero perfectamente
    regular. Solo se recorta cuando de verdad puede estar cortada.
    """
    if not truncada or texto.endswith("\n"):
        return texto
    corte = texto.rfind("\n")
    return texto if corte == -1 else texto[: corte + 1]


def _detectar_delimitador_y_comillas(
    texto: str, *, truncada: bool, avisos: list[Aviso]
) -> tuple[Deteccion, Deteccion, tuple[PuntuacionDelimitador, ...]]:
    # Se trabaja sobre los bytes UTF-8 del texto ya decodificado: en UTF-8 ningún
    # byte de continuación coincide con un ASCII, así que buscar `,` o `"` en el
    # buffer de bytes no puede casar con el trozo de un carácter multibyte. Es
    # más rápido y más simple que trabajar sobre puntos de código.
    analizado = _recortar_linea_incompleta(texto, truncada)
    arr = np.frombuffer(analizado.encode("utf-8"), dtype=np.uint8)

    puntuaciones = _puntuar_todas(arr, analizado, DELIMITADORES_PRINCIPALES)
    ultimo_recurso = not puntuaciones
    if ultimo_recurso:
        puntuaciones = _puntuar_todas(arr, analizado, (DELIMITADOR_ULTIMO_RECURSO,))

    if not puntuaciones:
        n_lineas = len([ln for ln in analizado.splitlines() if ln.strip()])
        avisos.append(
            Aviso(
                "sin_delimitador",
                "ningún delimitador candidato parte la muestra en dos o más columnas; "
                "se trata como fichero de una sola columna",
            )
        )
        evidencia = (
            f"ninguno de {', '.join(repr(c) for c in CANDIDATOS_DELIMITADOR)} "
            f"aparece de forma consistente en las {n_lineas} líneas no vacías"
        )
        return (
            Deteccion("delimitador", None, DESCONOCIDA, evidencia),
            Deteccion("comillas", None, DESCONOCIDA, "no se ha podido decidir el delimitador"),
            (),
        )

    mejor = puntuaciones[0]
    delimitador = mejor.delimitador
    comillas, comilla_elegida = _decidir_comillas(arr, analizado, delimitador, puntuaciones, avisos)

    # El veredicto que se devuelve es el de la pareja finalmente elegida, no el
    # de la hipótesis que ganó la carrera: si el paso de comillas ha descartado
    # una comilla suelta, el recuento de campos cambia y la evidencia tiene que
    # ser la del recuento de verdad.
    elegida = next(
        (p for p in puntuaciones if p.delimitador == delimitador and p.comilla == comilla_elegida),
        mejor,
    )
    if elegida is not mejor:
        puntuaciones.remove(elegida)
        puntuaciones.insert(0, elegida)

    rival = next((p for p in puntuaciones if p.delimitador != delimitador), None)
    ambiguo = (
        rival is not None
        and rival.lineas_de_acuerdo >= _MARGEN_AMBIGUEDAD * elegida.lineas_de_acuerdo
    )
    if ambiguo and rival is not None:
        avisos.append(
            Aviso(
                "delimitador_ambiguo",
                f"{delimitador!r} y {rival.delimitador!r} parten la muestra de forma casi "
                f"igual de consistente ({elegida.lineas_de_acuerdo} frente a "
                f"{rival.lineas_de_acuerdo} líneas); si el fichero trae coma decimal, "
                "quien lo resuelve es la detección del separador decimal",
            )
        )

    desacuerdo = elegida.lineas_examinadas - elegida.lineas_de_acuerdo
    if desacuerdo:
        avisos.append(
            Aviso(
                "lineas_de_longitud_distinta",
                f"{desacuerdo} de {elegida.lineas_examinadas} líneas no tienen "
                f"{elegida.n_campos} campos con el delimitador {delimitador!r}; "
                "suele ser un preámbulo de metadatos, una fila mal formada o texto "
                "con saltos de línea sin entrecomillar",
            )
        )

    evidencia = (
        f"{elegida.lineas_de_acuerdo} de {elegida.lineas_examinadas} líneas se parten en "
        f"{elegida.n_campos} campos"
    )
    if rival is not None:
        evidencia += (
            f"; el segundo candidato, {rival.delimitador!r}, llega a "
            f"{rival.lineas_de_acuerdo} líneas con {rival.n_campos} campos"
        )
    else:
        evidencia += "; ningún otro candidato parte la muestra en más de una columna"

    if elegida.lineas_examinadas < 2:
        confianza = DESCONOCIDA
        avisos.append(
            Aviso(
                "sin_evidencia_de_consistencia",
                "la muestra tiene una sola línea: el delimitador se propone por lo que "
                "hay en ella, pero no hay ninguna segunda línea con la que comprobar "
                "que el número de campos se mantiene",
            )
        )
    elif elegida.cobertura < 0.5:
        # Más líneas en desacuerdo que de acuerdo: el delimitador propuesto es el
        # mejor de los candidatos, pero eso no es lo mismo que ser el del
        # fichero. El asistente tiene que preguntar (§7.8), no precargar.
        confianza = DESCONOCIDA
    elif ambiguo or ultimo_recurso or elegida.cobertura < 1.0 or elegida.lineas_examinadas < 3:
        # `ultimo_recurso`: el espacio nunca pasa de `inferred`, por muy
        # consistente que sea. Es el carácter que separa palabras dentro de un
        # campo de texto, y ninguna cantidad de consistencia distingue un fichero
        # separado por espacios de una tabla alineada a mano.
        confianza = INFERIDA
    else:
        confianza = CONFIRMADA

    return (
        Deteccion("delimitador", delimitador, confianza, evidencia),
        comillas,
        tuple(puntuaciones),
    )


def _decidir_comillas(
    arr: np.ndarray,
    texto: str,
    delimitador: str,
    puntuaciones: list[PuntuacionDelimitador],
    avisos: list[Aviso],
) -> tuple[Deteccion, str | None]:
    """Qué comilla usa el fichero, ya fijado el delimitador."""
    presentes = [c for c in CANDIDATOS_COMILLA if c in texto]
    if not presentes:
        return (
            Deteccion(
                "comillas",
                None,
                CONFIRMADA,
                "no aparece ninguna de las comillas candidatas "
                f"({', '.join(repr(c) for c in CANDIDATOS_COMILLA)}) en la muestra",
            ),
            None,
        )

    por_comilla = {p.comilla: p for p in puntuaciones if p.delimitador == delimitador}
    sin_comillas = por_comilla.get(None)
    base = sin_comillas.lineas_de_acuerdo if sin_comillas is not None else 0

    mejor: tuple[int, int, int, str] | None = None  # (campos, aperturas, cierres, comilla)
    for comilla in presentes:
        aperturas, cierres = _fronteras_de_comilla(arr, delimitador, comilla)
        campos = min(aperturas, cierres)
        p = por_comilla.get(comilla)
        # Se exige que tratarla como comilla no EMPEORE la partición. Una comilla
        # sin pareja —la típica de `12" de llanta`— desplaza el estado del resto
        # del fichero, y eso se ve como una caída del número de líneas de
        # acuerdo. Es la comprobación que evita el fallo más caro de este paso.
        if campos >= 1 and p is not None and p.lineas_de_acuerdo >= base:
            candidato = (campos, aperturas, cierres, comilla)
            if mejor is None or candidato > mejor:
                mejor = candidato

    if mejor is None:
        avisos.append(
            Aviso(
                "comillas_sueltas",
                f"aparecen comillas ({', '.join(repr(c) for c in presentes)}) que no "
                "delimitan campos; se leen como texto normal",
            )
        )
        return (
            Deteccion(
                "comillas",
                None,
                INFERIDA,
                f"las comillas {', '.join(repr(c) for c in presentes)} aparecen en la "
                "muestra, pero no pegadas a un delimitador ni a un fin de línea: son "
                "parte del texto",
            ),
            None,
        )

    campos, aperturas, cierres, comilla = mejor
    equilibradas = aperturas == cierres
    return (
        Deteccion(
            "comillas",
            comilla,
            CONFIRMADA if equilibradas else INFERIDA,
            f"{campos} campos empiezan y acaban con {comilla!r} pegada a un "
            f"delimitador o a un fin de línea ({aperturas} aperturas, {cierres} cierres)"
            + ("" if equilibradas else "; el desequilibrio apunta a una comilla sin cerrar"),
        ),
        comilla,
    )
