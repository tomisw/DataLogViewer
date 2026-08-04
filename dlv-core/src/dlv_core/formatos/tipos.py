"""Inferencia de tipo por columna de un CSV genérico (FG-05).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.10 (la tabla de casos que
no deben abortar la carga) y §7.8 paso 3 (la columna «tipo inferido» de la tabla
de canales del asistente). Cuarto eslabón de la cadena del importador genérico:

    FG-01  ¿cómo se parte cada línea?
    FG-02  ¿qué es un número?
    FG-03  ¿qué línea es qué?
    FG-05  ¿qué clase de dato trae cada columna?          <- esto
    FG-06  ¿qué unidad declara cada columna?

QUÉ DECIDE ESTE MÓDULO Y QUÉ NO
================================
Decide **de qué clase es cada columna**, y con eso el asistente puede decir en
qué se va a convertir cada canal antes de importar nada. No transforma valores:
extraer el número de `12.5 psi`, normalizar `1 234,5` y construir el diccionario
de un enum son FG-07 y FG-08, que se apoyan en lo que este módulo clasifica.

La consecuencia práctica de acertar el tipo es el almacenamiento: una columna
`ENTERO` cabe en un entero y una `DECIMAL` no, y una `CONSTANTE` o una `VACIA`
no se grafica ni alimenta a un detector -- avisarlo en el asistente es más
honesto que dibujar una línea recta y dejar que el usuario deduzca por qué.

LO QUE ES «SIN DATO» NO SE DECIDE AQUÍ: LO DICE `data/units.toml`
==================================================================
Las cadenas que significan «no hay valor» (`NaN`, `#N/A`, `NULL`, `---`, `-`,
vacío...) viven en `[centinelas] texto` de `data/units.toml`, y los centinelas
de desbordamiento enteros en `[centinelas] i32`. Este módulo los recibe en el
`Catalogo` y NO tiene ninguna lista propia: duplicarla en Python sería mover un
dato al código, y entonces añadir el «sin dato» de un exportador nuevo pasaría a
ser un cambio de programa en vez de una línea de TOML.

Los dos se tratan igual para inferir el tipo -- como ausencia -- pero se cuentan
por separado, porque no significan lo mismo para quien lee el informe: una
columna con 900 celdas vacías es un canal a otra frecuencia (el muestreo es
disperso, `docs/01` §1.4), y una con 900 celdas a `2147483647` es un sensor que
estuvo desconectado toda la sesión. La segunda es un problema del coche.

CERO NO ES AUSENCIA, Y ESTE ES EL SITIO DONDE SE PUEDE PERDER
==============================================================
§7.10 lo dice con mayúsculas para los valores ausentes: «**nunca 0**». Aquí eso
se traduce en dos reglas que las pruebas fijan: una celda ausente no cuenta para
el mínimo, el máximo ni los valores distintos de la columna, y una columna sin
ninguna celda con dato es `VACIA` -- no `CONSTANTE` de valor cero, que es lo que
saldría si se contaran las ausencias como ceros.

PRECEDENCIA DE LOS SEIS TIPOS, Y POR QUÉ ESE ORDEN
====================================================
Se comprueban en este orden, y el primero que encaja gana:

1. `VACIA` -- ninguna celda con dato. No hay nada más que decir de la columna.
2. `CONSTANTE` -- todas las celdas con dato valen lo mismo. Va ANTES que el
   tipo numérico a propósito: que una columna de 73 M de muestras sea siempre
   `0` es la información que el asistente tiene que dar, mucho más que si ese 0
   es entero o decimal. Lo numérico no se pierde: `numerica` y `escritura` lo
   siguen contando.
3. `BOOLEANO` -- dos valores distintos que forman una pareja conocida
   (`true/false`, `on/off`, `sí/no`). Es un `ENUM_TEXTO` de dos estados con la
   semántica ya resuelta, así que decirlo es mejor que dejarlo en enum.
4. `ENTERO` -- todas las celdas con dato son números y ninguna está ESCRITA con
   parte fraccionaria ni exponente.
5. `DECIMAL` -- todas son números y alguna trae fracción o exponente.
6. `ENUM_TEXTO` -- queda texto que no es número ni centinela.

ENTERO O DECIMAL SE DECIDE POR CÓMO ESTÁ ESCRITO, NO POR EL VALOR
==================================================================
Una columna de λ que en la muestra inspeccionada trae `1.000`, `1.000`, `1.000`
es `DECIMAL`, no `ENTERO`, aunque los tres valores sean enteros exactos. El
exportador escribió tres decimales porque el canal los tiene: clasificarla como
entero por lo que se ve en 200 filas la truncaría a `1` en cuanto una fila no
inspeccionada trajera `0.997`, y ese redondeo es indetectable después. La regla
inversa no tiene ese riesgo: una columna escrita sin punto en ninguna celda no
puede perder nada por guardarse como entero.

UN 0/1 NO ES UN BOOLEANO
=========================
§7.10 lista tres parejas booleanas y las tres son de texto. `0`/`1` no está, y
no se añade: un canal de 0 y 1 es numéricamente válido tal cual, y convertirlo
en enum sería decidir por el usuario. Lo que sí se hace es exponer
`valores_distintos`, así que FG-08 puede ofrecer el enum de dos estados sin que
esta inferencia se lo imponga.

EL LÍMITE DE MUESTRA ES DEL MISMO TAMAÑO QUE EL DE FG-02
==========================================================
Se clasifica sobre las filas que se le den, que en el asistente son las mismas
`MAX_FILAS_INSPECCIONADAS` que ya usan FG-02 y FG-04. `filas_inspeccionadas`
viaja en el resultado para que ninguna conclusión pueda leerse como si fuera
sobre el fichero entero. Esto NO infringe ADR-009: el bucle es sobre una muestra
acotada del principio del fichero para PROPONER un esquema, no sobre las 73 M
muestras del log -- igual que en FG-01, FG-02 y FG-03. La lectura de verdad, ya
con el esquema decidido, la hace Polars sin pasar por Python.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from dlv_core.formatos.decimal_csv import es_numerica
from dlv_core.informes import Aviso
from dlv_core.unidades import Catalogo

__all__ = [
    "COBERTURA_NUMERICA_MINIMA",
    "MAX_EJEMPLOS",
    "MAX_VALORES_DISTINTOS",
    "PAREJAS_BOOLEANAS",
    "Escritura",
    "ResultadoTipos",
    "TipoColumna",
    "TipoDeColumna",
    "inferir_tipos",
    "inferir_tipos_de_columna",
]

#: Fracción mínima de celdas CON DATO que tienen que ser números para que la
#: columna se considere numérica pese a traer alguna celda de texto que no es
#: centinela. Por debajo de esto es una columna de texto con números dentro.
#:
#: No es un umbral de física (no va a `data/umbrales.toml`, que es de los
#: detectores): es una heurística de formato, del mismo tipo que
#: `sondeo.CONFIANZA_MINIMA`. Se puede pasar otro valor por parámetro.
#:
#: 0,95 y no 1,0 porque el caso que motiva el margen es real y frecuente: un
#: exportador que escribe `ERROR` o `---sin datos---` en un puñado de filas de
#: una columna por lo demás numérica. Tratar esa columna como enum de texto
#: perdería 200 000 números buenos para conservar tres cadenas.
COBERTURA_NUMERICA_MINIMA = 0.95

#: Cuántos valores distintos se guardan antes de dejar de contarlos. Un enum de
#: texto útil tiene unas decenas de estados; una columna de texto libre tiene
#: tantos como filas, y guardarlos todos convertiría este resultado en una copia
#: del fichero.
MAX_VALORES_DISTINTOS = 64

#: Cuántas celdas de ejemplo se guardan por cada anomalía. Los ejemplos son lo
#: que hace revisable un aviso: «no numérica: 'ERROR', '---'» dice más que
#: cualquier porcentaje.
MAX_EJEMPLOS = 5

#: Las tres parejas de §7.10, en minúsculas y sin acentos para comparar. La
#: comparación de booleanos SÍ es insensible a mayúsculas —a diferencia de la de
#: unidades de FG-06—, y la asimetría es deliberada: `TRUE` y `true` son el mismo
#: booleano en todos los exportadores que existen, mientras que `M` y `m` son
#: mega y mili, dos unidades distintas con tres órdenes de magnitud de
#: diferencia. Adivinar cuesta caro en un sitio y nada en el otro.
#:
#: `si` sin tilde está aparte de `sí` porque un exportador que pierde los
#: acentos es más común que uno que los conserva.
PAREJAS_BOOLEANAS: tuple[tuple[str, str], ...] = (
    ("true", "false"),
    ("on", "off"),
    ("sí", "no"),
    ("si", "no"),
    ("verdadero", "falso"),
    ("yes", "no"),
)


def _re_fraccion(decimal: str) -> re.Pattern[str]:
    """¿Está la celda escrita con parte fraccionaria o exponente?

    Se mira la ESCRITURA, no el valor (ver la cabecera). El separador decimal
    entra como parámetro porque `0,5` es un decimal en un fichero y dos campos
    en otro.
    """
    return re.compile(rf"{re.escape(decimal)}\d|[eE][+-]?\d")


_FRACCIONES = {d: _re_fraccion(d) for d in (".", ",")}


class TipoColumna(Enum):
    """Las seis clases de columna de FG-05, en orden de precedencia."""

    VACIA = "vacia"
    """Ninguna celda con dato: todas vacías, centinela de texto o centinela de
    desbordamiento. No se grafica y no alimenta a ningún detector."""

    CONSTANTE = "constante"
    """Todas las celdas con dato traen la MISMA CADENA. Sigue siendo importable
    —puede ser el ajuste de una sesión— pero no tiene nada que dibujar.

    La constancia se juzga por la cadena y no por el valor a propósito: decidir
    que `1.0` y `1.00` son el mismo número exige parsear, y parsear —con su
    separador de miles y su unidad embebida— es FG-07. Con la cadena, una
    columna así se queda en `DECIMAL` en vez de en `CONSTANTE`: se pierde un
    aviso, no un dato, y sigue siendo graficable. Al contrario —declarar
    constante algo que no lo es— se perdería la columna entera."""

    BOOLEANO = "booleano"
    """Dos valores distintos que forman una pareja conocida de §7.10. Se
    convierte en un enum de dos estados (FG-08)."""

    ENTERO = "entero"
    """Todo números, ninguno escrito con fracción ni exponente."""

    DECIMAL = "decimal"
    """Todo números, alguno con fracción o exponente."""

    ENUM_TEXTO = "enum_texto"
    """Queda texto que no es número ni centinela: se convierte en enum con
    diccionario autogenerado (FG-08)."""


class Escritura(Enum):
    """Cómo estaban ESCRITAS las celdas numéricas de la columna.

    Se conserva aparte del tipo porque `CONSTANTE` y `BOOLEANO` ganan a
    `ENTERO`/`DECIMAL` por precedencia, y sin esto se perdería para siempre el
    dato de si aquella constante era `0` o `0.000` -- que es justo lo que
    decide en qué se guarda si la columna deja de ser constante en las filas que
    no se inspeccionaron.
    """

    NINGUNA = "ninguna"
    """No había ninguna celda numérica que mirar."""

    SIN_FRACCION = "sin_fraccion"
    """Ninguna celda numérica traía fracción ni exponente."""

    CON_FRACCION = "con_fraccion"
    """Alguna celda numérica traía fracción o exponente."""


@dataclass(slots=True, frozen=True)
class TipoDeColumna:
    """Lo que se infiere de UNA columna. Una propuesta para el asistente, con el
    recuento que la respalda: §7.8 exige que la tabla de canales sea ordenable
    por «necesita atención», y eso solo se puede hacer con los números delante.
    """

    indice: int
    nombre: str
    tipo: TipoColumna

    celdas: int
    """Celdas inspeccionadas de esta columna, ausencias incluidas."""

    con_dato: int
    """Celdas que no son vacías ni centinela. El denominador de todo lo demás."""

    vacias: int
    centinelas_texto: int
    centinelas_desbordamiento: int
    """Celdas que son un centinela de `[centinelas] i32`. Se cuentan aparte de
    las vacías: una columna llena de `2147483647` no es un canal a otra
    frecuencia, es un sensor que estuvo desconectado."""

    numericas: int
    no_numericas: int
    """Celdas con dato que no son número ni centinela. Cero salvo en columnas de
    texto y en las mixtas."""

    escritura: Escritura
    valores_distintos: tuple[str, ...]
    """Hasta `MAX_VALORES_DISTINTOS` valores distintos, en orden de aparición.
    Vacío si la columna los superó -- lo que ya dice que no es un enum."""

    distintos_truncados: bool
    """`True` si había más valores distintos que `MAX_VALORES_DISTINTOS`. Sin
    esto, una tupla vacía sería ambigua entre «no hay ninguno» y «hay
    demasiados»."""

    ejemplos_no_numericos: tuple[str, ...]
    valor_constante: str | None
    """El valor único de una columna `CONSTANTE`, tal como venía escrito."""

    @property
    def es_numerico(self) -> bool:
        """¿Se puede guardar y graficar como número?

        `CONSTANTE` cuenta como numérico si lo que se repetía era un número: la
        columna es aburrida, no es texto. `BOOLEANO` no, aunque sus dos estados
        fueran `1` y `0`, porque un booleano no puede serlo (ver la cabecera).
        """
        if self.tipo in (TipoColumna.ENTERO, TipoColumna.DECIMAL):
            return True
        if self.tipo is TipoColumna.CONSTANTE:
            return self.numericas == self.con_dato and self.con_dato > 0
        return False

    @property
    def graficable(self) -> bool:
        """`VACIA` no tiene nada que dibujar y `CONSTANTE` dibuja una recta.

        Las dos se pueden importar (§7.8: «se puede importar dejando canales sin
        rol»); esto solo dice si tiene sentido ponerlas en un panel.
        """
        return self.tipo not in (TipoColumna.VACIA, TipoColumna.CONSTANTE)

    @property
    def cobertura_numerica(self) -> float:
        """Fracción de las celdas CON DATO que son números.

        Sobre `con_dato` y no sobre `celdas`: si fuera sobre el total, un canal a
        5 Hz en un fichero a 20 Hz saldría con cobertura 0,25 y parecería un
        problema de tipos cuando es muestreo disperso normal.
        """
        if self.con_dato == 0:
            return 0.0
        return self.numericas / self.con_dato


def _normalizar_booleano(valor: str) -> str:
    return valor.strip().lower()


def _es_pareja_booleana(valores: Sequence[str], parejas: Sequence[tuple[str, str]]) -> bool:
    """¿Forman estos valores distintos una pareja booleana conocida?

    La cuenta de «cuántos valores distintos hay» se hace sobre los valores YA
    normalizados, no sobre las cadenas crudas. Es la diferencia entre reconocer
    `True`/`FALSE`/`true` como un booleano y verlo como un enum de tres estados,
    y un exportador que mezcla mayúsculas en la misma columna no es raro.

    Esa normalización es solo de esta comprobación: `valores_distintos` sigue
    guardando las cadenas tal cual, porque para un enum de texto de verdad
    `Alta` y `alta` pueden ser dos estados que el fichero distingue, y unirlos
    ahí sí perdería información.

    El bucle es sobre las parejas declaradas (media docena), no sobre las
    muestras.
    """
    vistos = {_normalizar_booleano(v) for v in valores}
    if len(vistos) != 2:
        return False
    return any(vistos == {a, b} for a, b in parejas)


def inferir_tipos_de_columna(
    celdas: Sequence[str],
    *,
    indice: int = 0,
    nombre: str = "",
    decimal: str = ".",
    catalogo: Catalogo | None = None,
    centinelas_texto: frozenset[str] | None = None,
    centinelas_desbordamiento: frozenset[str] | None = None,
    parejas_booleanas: Sequence[tuple[str, str]] = PAREJAS_BOOLEANAS,
    cobertura_numerica_minima: float = COBERTURA_NUMERICA_MINIMA,
) -> TipoDeColumna:
    """Infiere el tipo de UNA columna a partir de sus celdas en crudo.

    `catalogo` es la vía normal de pasar los centinelas, porque es donde están
    declarados (`data/units.toml`). `centinelas_texto` y
    `centinelas_desbordamiento` existen para poder probar el módulo sin cargar
    el catálogo entero y para el caso en que quien llama ya los tenga; si no se
    da ninguno de los tres, no hay centinelas y solo la celda vacía cuenta como
    ausencia -- nunca se inventa una lista por omisión, que es lo que haría que
    `NULL` se tratara como texto en un sitio y como ausencia en otro.
    """
    if catalogo is not None:
        if centinelas_texto is None:
            centinelas_texto = frozenset(catalogo.centinelas_texto)
        if centinelas_desbordamiento is None:
            centinelas_desbordamiento = frozenset(str(c) for c in catalogo.centinelas_i32)
    texto_sin_dato = centinelas_texto if centinelas_texto is not None else frozenset()
    desbordamiento = (
        centinelas_desbordamiento if centinelas_desbordamiento is not None else frozenset()
    )
    fraccion = _FRACCIONES[decimal]

    vacias = n_centinelas_texto = n_desbordamiento = 0
    numericas = no_numericas = 0
    con_fraccion = False
    distintos: dict[str, None] = {}
    distintos_truncados = False
    ejemplos: list[str] = []

    for celda in celdas:
        valor = celda.strip()
        if not valor:
            vacias += 1
            continue
        if valor in desbordamiento:
            n_desbordamiento += 1
            continue
        if valor in texto_sin_dato:
            n_centinelas_texto += 1
            continue

        if es_numerica(valor, decimal):
            numericas += 1
            if fraccion.search(valor) is not None:
                con_fraccion = True
        else:
            no_numericas += 1
            if len(ejemplos) < MAX_EJEMPLOS and valor not in ejemplos:
                ejemplos.append(valor)

        if len(distintos) < MAX_VALORES_DISTINTOS:
            distintos[valor] = None
        elif valor not in distintos:
            distintos_truncados = True

    con_dato = numericas + no_numericas
    escritura = (
        Escritura.NINGUNA
        if numericas == 0
        else (Escritura.CON_FRACCION if con_fraccion else Escritura.SIN_FRACCION)
    )
    # Los valores distintos solo son fiables si no se truncaron; con la lista
    # truncada, «cuántos hay» es «al menos MAX_VALORES_DISTINTOS».
    unicos = tuple(distintos) if not distintos_truncados else ()
    cobertura = numericas / con_dato if con_dato else 0.0

    if con_dato == 0:
        tipo = TipoColumna.VACIA
    elif not distintos_truncados and len(distintos) == 1:
        tipo = TipoColumna.CONSTANTE
    elif not distintos_truncados and _es_pareja_booleana(tuple(distintos), parejas_booleanas):
        tipo = TipoColumna.BOOLEANO
    elif cobertura >= cobertura_numerica_minima:
        tipo = TipoColumna.DECIMAL if con_fraccion else TipoColumna.ENTERO
    else:
        tipo = TipoColumna.ENUM_TEXTO

    return TipoDeColumna(
        indice=indice,
        nombre=nombre,
        tipo=tipo,
        celdas=len(celdas),
        con_dato=con_dato,
        vacias=vacias,
        centinelas_texto=n_centinelas_texto,
        centinelas_desbordamiento=n_desbordamiento,
        numericas=numericas,
        no_numericas=no_numericas,
        escritura=escritura,
        valores_distintos=unicos,
        distintos_truncados=distintos_truncados,
        ejemplos_no_numericos=tuple(ejemplos),
        valor_constante=next(iter(distintos)) if tipo is TipoColumna.CONSTANTE else None,
    )


@dataclass(slots=True, frozen=True)
class ResultadoTipos:
    """Un `TipoDeColumna` por columna, en el orden del fichero."""

    columnas: tuple[TipoDeColumna, ...]
    filas_inspeccionadas: int
    """Cuántas filas de datos se miraron. Ninguna conclusión de aquí es sobre el
    fichero entero, y este número es lo que lo dice."""

    avisos: tuple[Aviso, ...] = ()

    def por_nombre(self, nombre: str) -> TipoDeColumna | None:
        for c in self.columnas:
            if c.nombre == nombre:
                return c
        return None


def inferir_tipos(
    filas: Sequence[Sequence[str]],
    nombres: Sequence[str],
    *,
    decimal: str = ".",
    catalogo: Catalogo | None = None,
    parejas_booleanas: Sequence[tuple[str, str]] = PAREJAS_BOOLEANAS,
    cobertura_numerica_minima: float = COBERTURA_NUMERICA_MINIMA,
) -> ResultadoTipos:
    """Infiere el tipo de cada columna de un bloque de filas ya partidas.

    `filas` son las filas de DATOS (sin preámbulo, sin fila de nombres ni de
    unidades: lo que FG-03 delimitó) ya partidas en campos por FG-01. `nombres`
    es `Estructura.nombres_o_posicionales()`, así que una cabecera ausente da
    `col_1…col_n` en vez de columnas sin nombre.

    Las filas de longitud distinta a `len(nombres)` NO abortan nada (§7.10): las
    celdas que faltan se tratan como ausentes y las que sobran se ignoran, y las
    dos cosas se avisan una vez con el recuento. Es la misma regla de «se rellena
    con vacío y se registra» que aplicará FG-14 al leer de verdad.
    """
    n = len(nombres)
    avisos: list[Aviso] = []
    columnas_de_celdas: list[list[str]] = [[] for _ in range(n)]

    filas_cortas = filas_largas = 0
    for fila in filas:
        if len(fila) < n:
            filas_cortas += 1
        elif len(fila) > n:
            filas_largas += 1
        for i in range(n):
            columnas_de_celdas[i].append(fila[i] if i < len(fila) else "")

    if filas_cortas:
        avisos.append(
            Aviso(
                "filas_cortas",
                f"{filas_cortas} de {len(filas)} filas inspeccionadas traen menos de "
                f"{n} campos; las celdas que faltan se cuentan como ausentes, no como 0",
            )
        )
    if filas_largas:
        avisos.append(
            Aviso(
                "filas_largas",
                f"{filas_largas} de {len(filas)} filas inspeccionadas traen más de "
                f"{n} campos; los campos de sobra no se han mirado. Suele ser un "
                "delimitador dentro de un campo sin comillas: revisa el paso de formato",
            )
        )

    # Sin ninguna fila, TODAS las columnas salen `VACIA` y avisar de cada una
    # serían 476 avisos idénticos en el AutoLog -- un informe que nadie lee. El
    # hecho es uno solo y del fichero, no de cada columna.
    if not filas:
        avisos.append(
            Aviso(
                "sin_filas_de_datos",
                f"la muestra inspeccionada no trae ninguna fila de datos, así que no se "
                f"sabe nada del tipo de las {n} columnas. Revisa dónde empiezan los datos "
                "en el paso de formato",
            )
        )

    columnas: list[TipoDeColumna] = []
    for i, nombre in enumerate(nombres):
        col = inferir_tipos_de_columna(
            columnas_de_celdas[i],
            indice=i,
            nombre=nombre,
            decimal=decimal,
            catalogo=catalogo,
            parejas_booleanas=parejas_booleanas,
            cobertura_numerica_minima=cobertura_numerica_minima,
        )
        columnas.append(col)

        if not filas:
            continue
        if col.tipo is TipoColumna.VACIA:
            detalle = (
                f"{col.centinelas_desbordamiento} de sus {col.celdas} celdas son un "
                "centinela de desbordamiento de data/units.toml, así que el sensor "
                "pudo estar desconectado"
                if col.centinelas_desbordamiento
                else f"sus {col.celdas} celdas están vacías o son un centinela de texto"
            )
            avisos.append(
                Aviso(
                    "columna_sin_datos",
                    f"la columna '{nombre}' no tiene ningún valor en las filas "
                    f"inspeccionadas: {detalle}. Se puede importar, pero no hay nada "
                    "que graficar",
                )
            )
        elif col.tipo is TipoColumna.CONSTANTE:
            avisos.append(
                Aviso(
                    "columna_constante",
                    f"la columna '{nombre}' vale siempre {col.valor_constante!r} en las "
                    f"{col.celdas} filas inspeccionadas. Puede ser un ajuste de la sesión; "
                    "como canal no tiene nada que dibujar",
                )
            )
        elif col.no_numericas and col.es_numerico:
            avisos.append(
                Aviso(
                    "columna_mixta",
                    f"la columna '{nombre}' es numérica en {col.numericas} de sus "
                    f"{col.con_dato} celdas con dato, y trae texto en las otras "
                    f"{col.no_numericas} (por ejemplo {list(col.ejemplos_no_numericos)}). "
                    "Se propone como numérica; esas celdas quedarían ausentes, nunca 0",
                )
            )
        elif col.tipo is TipoColumna.ENUM_TEXTO and col.distintos_truncados:
            # Va antes que `enum_con_numeros` porque es el hallazgo más grave de
            # los dos: con tantos estados no hay diccionario utilizable, y eso
            # importa más que la mezcla de tipos que además pueda tener.
            avisos.append(
                Aviso(
                    "texto_libre",
                    f"la columna '{nombre}' tiene más de {MAX_VALORES_DISTINTOS} valores "
                    "distintos, así que es texto libre y no un enum de estados. Se puede "
                    "importar, pero un diccionario de tantos estados no es utilizable",
                )
            )
        elif col.tipo is TipoColumna.ENUM_TEXTO and col.numericas:
            # El caso de la columna de marcha con `N` de punto muerto: 34 celdas
            # numéricas y 16 de texto. Clasificarla como enum es lo correcto
            # —tratarla como numérica perdería todas las muestras en punto
            # muerto— pero es justo la columna que hay que mirar primero, y sin
            # este aviso era la única del fichero de la que el informe no decía
            # nada.
            avisos.append(
                Aviso(
                    "enum_con_numeros",
                    f"la columna '{nombre}' mezcla {col.numericas} celdas numéricas con "
                    f"{col.no_numericas} de texto (por ejemplo "
                    f"{list(col.ejemplos_no_numericos)}), así que se propone como enum y "
                    "no como número. Es lo correcto para una marcha con 'N' de punto "
                    "muerto; si el texto era basura del exportador, revísala en el paso "
                    "de canales",
                )
            )

    return ResultadoTipos(
        columnas=tuple(columnas),
        filas_inspeccionadas=len(filas),
        avisos=tuple(avisos),
    )
