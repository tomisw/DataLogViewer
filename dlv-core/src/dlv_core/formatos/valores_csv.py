"""Valores de celda: ausencia real, unidad embebida y separador de miles (FG-07).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.10, tres filas de la tabla
de robustez:

    `NaN`, `inf`, `-inf`, `#N/A`, `NULL`, `---`, `n/a`, celda vacía -> ausente, NUNCA 0
    Valor con unidad embebida (`12.5 psi`)                          -> número + unidad
    Separador de miles (`1 234,5` / `1,234.5`)                      -> según el decimal ya detectado

Quinto eslabón de la cadena del importador genérico:

    FG-01  ¿cómo se parte cada línea?
    FG-02  ¿qué es un número?
    FG-03  ¿qué línea es qué?
    FG-05  ¿qué clase de dato trae cada columna?
    FG-07  ¿qué VALOR real hay en cada celda?              <- esto

QUÉ DECIDE ESTE MÓDULO Y QUÉ NO
================================
FG-05 (`tipos.py`) ya decide de qué CLASE es una columna, mirando la ESCRITURA
de las celdas; no convierte nada. Este módulo hace la conversión de verdad:
celda cruda -> `float | None`, con la unidad embebida aparte si la hay. Una
columna que FG-05 clasificó como `ENUM_TEXTO` porque el 100 % de sus celdas
traen "3,2 bar" detrás del número es precisamente el caso que este módulo
resuelve — la relación entre las dos tareas es esa, no una dependencia de
código: este módulo no importa nada de `tipos.py` salvo la constante
`MAX_EJEMPLOS`, para no inventar un segundo "cuántos ejemplos se enseñan".

No resuelve la unidad embebida contra el catálogo de `data/units.toml` /
`data/alias_unidades.toml` — eso es exactamente lo que ya hace FG-06
(`unidades_declaradas.py`) para la unidad DECLARADA EN LA COLUMNA (nombre o
fila de unidades). Aquí la unidad sale de DENTRO DE LA CELDA, columna por
columna de dato, no de la cabecera, así que es una fuente distinta que FG-06
no ve; pero una vez extraída como cadena cruda, resolverla contra el catálogo
es el mismo problema que FG-06 ya resuelve, y duplicar ese índice aquí sería
exactamente el error que este proyecto ya pagó una vez (ver el docstring de
`unidades_declaradas.py`). Se deja la cadena cruda en `unidad_embebida` para
que quien orqueste la importación se la pase a `resolver_unidades_declaradas`
si quiere resolverla — eso es trabajo posterior a FG-07, no de FG-07.

POR QUÉ ESTE MÓDULO SÍ TRABAJA SOBRE LA COLUMNA COMPLETA, NO SOBRE UNA MUESTRA
================================================================================
FG-01, FG-02, FG-03 y FG-05 proponen un ESQUEMA a partir de las primeras filas
del fichero: uno o dos bucles de Python sobre una muestra acotada no infringen
ADR-009 porque la muestra tiene un tamaño fijo, no crece con el fichero. Este
módulo es distinto: produce el VALOR que se va a graficar y a alimentar a los
detectores, así que corre sobre las 73 M de muestras del log, no sobre 200
filas. Por eso todo aquí es Polars vectorizado (`str.extract`, `str.replace_all`,
`is_in`, `cast(..., strict=False)`) y no hay un solo bucle de Python por celda.

CERO NO ES AUSENCIA, OTRA VEZ
==============================
La misma regla que FG-05 protege con mayúsculas en §7.10 se protege aquí en el
sitio donde de verdad se puede perder: el número final. Una celda ausente
—vacía, o un centinela de `data/units.toml`— tiene que salir `null` en la
columna resultado, nunca `0.0`, y nunca el propio centinela convertido
literalmente a número (un centinela de desbordamiento como `2147483647` ES un
número válido para el analizador de expresiones regulares, así que hay que
anularlo EXPLÍCITAMENTE después de parsear, no confiar en que "no parezca
numérico").

UNIDAD EMBEBIDA: SOLO SE ACEPTA SI ES CONSISTENTE EN LA COLUMNA
==================================================================
`12.5 psi`, `13.0 psi`, `11.8 psi` en la misma columna son inequívocamente la
misma unidad repetida — el caso normal de un exportador que escribe la unidad
en cada celda. Pero si una columna trae `14 psi` en una fila y `1.1 bar` en
otra, no hay una unidad de columna que asumir: son ~14x de diferencia y
mezclarlas en silencio es exactamente el riesgo R1 (`docs/07` §7.15) con otra
puerta de entrada. Aquí se distingue con `OrigenUnidadEmbebida`: `CONSISTENTE`
cuando hay una sola unidad no vacía en toda la columna, `MEZCLADA` cuando hay
más de una -- y en `MEZCLADA` el número se sigue extrayendo (celda a celda,
sin perder datos) pero `unidad_embebida` queda en `None` y se avisa con
severidad, porque ahí es donde un tuner puede tomar una decisión sobre un
número que no tiene la unidad que cree que tiene.

SEPARADOR DE MILES: EL DECIMAL YA ESTÁ DECIDIDO, NO SE VUELVE A ADIVINAR
==========================================================================
`decimal_csv.py` (FG-02) ya decidió el separador decimal del fichero por
verificación cruzada sobre una muestra, y ese resultado se recibe aquí como
parámetro. Con el decimal fijo, el CARÁCTER CONTRARIO dentro de una celda ya
NO puede ser un decimal de ese fichero -- solo puede ser agrupación de miles,
así que no hay nada que adivinar en cada celda individual (a diferencia de
`decimal_csv.detectar_separador_decimal`, que sí tiene que decidir el
carácter en sí). Lo único que añade este módulo sobre lo que ya sabe
`decimal_csv` es el ESPACIO como agrupador (`1 234,5`), porque
`decimal_csv._patron_numerico` no lo contempla -- ese módulo compara
interpretaciones de decimal, no formatos de agrupación, y el espacio nunca
podría ser decimal así que no le hacía falta.

Solo Polars además de la biblioteca estándar (regex de `re`, usada para
compilar el mismo patrón que después se pasa a Polars: un patrón, dos
motores, para que "qué es un número con unidad" no tenga dos definiciones que
puedan divergir -- ese fue precisamente el defecto que pagó `decimal_csv.py`
la primera vez, ver su docstring).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import polars as pl

from dlv_core.formatos.tipos import MAX_EJEMPLOS
from dlv_core.informes import Aviso
from dlv_core.unidades import Catalogo

__all__ = [
    "OrigenUnidadEmbebida",
    "ResultadoValores",
    "ValoresDeColumna",
    "convertir_valores",
    "convertir_valores_de_columna",
    "extraer_numero_y_unidad",
    "normalizar_separador_de_miles",
    "separar_numero_y_unidad",
]


def _cuerpo_numero(decimal: str) -> str:
    """El núcleo (sin anclas) de un número válido para este `decimal`.

    Mismo razonamiento que `decimal_csv._patron_numerico`, con un añadido: el
    grupo de miles admite también el ESPACIO como agrupador (`1 234,5`), que
    `decimal_csv` no cubre porque allí el espacio nunca podría confundirse con
    un decimal. La agrupación exige empezar por `1-9` -- la agrupación de
    millares nunca produce un grupo con ceros a la izquierda -- así que `0,050`
    sigue leyéndose como decimal puro y no como un intento de agrupación.
    """
    otro = "," if decimal == "." else "."
    g = re.escape(otro)
    d = re.escape(decimal)
    return rf"[+-]?(?:[1-9]\d{{0,2}}(?:[{g} ]\d{{3}})+|\d+)(?:{d}\d+)?(?:[eE][+-]?\d+)?"


#: Forma de una unidad embebida en la celda: empieza por letra o símbolo de
#: unidad real (nunca por dígito, coma, punto o signo -- esos ya los consume el
#: número), y puede seguir con dígitos para unidades como `m/s2` o `cm3`. Deja
#: fuera `,`/`.` a propósito: sin esa exclusión, un número mal agrupado como
#: `12,34` (dos cifras tras la coma en un fichero de coma decimal) se leería
#: como "número 12 con unidad ',34'", que es peor que dejarlo sin parsear.
_UNIDAD_CHARS = "A-Za-zµΩλφ°%/"
_UNIDAD = rf"[{_UNIDAD_CHARS}][{_UNIDAD_CHARS}0-9]*"


def _patron_valor(decimal: str) -> str:
    """Celda completa: número obligatorio + unidad opcional, ancorado."""
    return rf"^\s*({_cuerpo_numero(decimal)})\s*({_UNIDAD})?\s*$"


#: Un patrón por separador decimal posible, compartido entre el motor de `re`
#: (para la función escalar) y Polars (regex de Rust) -- la misma cadena de
#: texto para los dos, así que no hay dos definiciones de "número con unidad"
#: que puedan divergir.
_PATRONES: dict[str, str] = {d: _patron_valor(d) for d in (".", ",")}
_PATRONES_COMPILADOS = {d: re.compile(p) for d, p in _PATRONES.items()}


class OrigenUnidadEmbebida(Enum):
    """De dónde sale (o no) la unidad embebida de una columna."""

    NINGUNA = "ninguna"
    """Ninguna celda con dato trae una unidad pegada al número."""

    CONSISTENTE = "consistente"
    """Todas las celdas que traen unidad traen LA MISMA. Es la unidad de la
    columna: `unidad_embebida` la lleva como cadena cruda, sin resolver."""

    MEZCLADA = "mezclada"
    """Hay más de una unidad distinta en la misma columna (p. ej. `psi` y
    `bar`). No se puede asumir ninguna: `unidad_embebida` queda en `None` y se
    avisa con severidad, porque mezclar unidades en silencio es el riesgo R1
    de `docs/07` §7.15."""


def separar_numero_y_unidad(celda: str, decimal: str) -> tuple[str | None, str | None]:
    """`"12.5 psi"` -> `("12.5", "psi")`; `"850"` -> `("850", None)`.

    Escalar, sobre `re` de la biblioteca estándar: existe para poder probar el
    patrón sin montar una `Series` de Polars por cada caso, y porque
    `dlv_core.unidades` u otro módulo que reciba una sola celda (no una
    columna) puede necesitar la misma pregunta. Comparte el patrón exacto de
    `extraer_numero_y_unidad`, así que las dos vías dan siempre la misma
    respuesta para la misma celda.

    `None, None` si la celda no tiene forma de número (con o sin unidad):
    quien llama decide si eso es ausencia, centinela o texto libre -- esta
    función no lo sabe, porque no conoce los centinelas del catálogo.
    """
    m = _PATRONES_COMPILADOS[decimal].match(celda.strip())
    if m is None:
        return None, None
    return m.group(1), m.group(2)


def extraer_numero_y_unidad(valores: pl.Series, decimal: str) -> tuple[pl.Series, pl.Series]:
    """La versión vectorizada de `separar_numero_y_unidad`, sobre una columna
    entera. Devuelve `(numero_crudo, unidad_cruda)`, dos `Series` de texto con
    `null` donde la celda no encajó en absoluto en la forma "número [unidad]".

    `numero_crudo` sigue en crudo -- con su separador de miles si lo tenía --
    porque separar la extracción de la normalización es lo que permite probar
    cada paso por separado (`normalizar_separador_de_miles` es la que limpia).
    """
    patron = _PATRONES[decimal]
    limpio = valores.cast(pl.Utf8).fill_null("").str.strip_chars()
    numero = limpio.str.extract(patron, 1)
    unidad = limpio.str.extract(patron, 2)
    return numero, unidad


def normalizar_separador_de_miles(numeros_crudos: pl.Series, decimal: str) -> pl.Series:
    """`"1 234,5"` / `"1.234,5"` (decimal `,`) o `"1,234.5"` (decimal `.`) ->
    cadena lista para `cast(pl.Float64)`.

    El carácter que NO es el decimal de este fichero, y el espacio, se borran
    por completo -- no hace falta comprobar que de verdad forman grupos de
    tres, porque `extraer_numero_y_unidad` ya filtró con el mismo patrón que
    exige esa forma antes de que una celda llegue aquí. Si el decimal es la
    coma, la coma que queda se convierte en punto para que `cast` la entienda;
    si es el punto, ya está en la forma que `cast` espera.

    Los `null` de entrada (celda sin forma de número) se conservan `null`:
    Polars propaga `null` a través de las operaciones de cadena, así que no
    hace falta una comprobación aparte.
    """
    otro = "," if decimal == "." else "."
    limpio = numeros_crudos.str.replace_all(otro, "", literal=True)
    limpio = limpio.str.replace_all(r"\s+", "", literal=False)
    if decimal != ".":
        limpio = limpio.str.replace_all(decimal, ".", literal=True)
    return limpio


@dataclass(slots=True, frozen=True)
class ValoresDeColumna:
    """Lo que sale de convertir UNA columna cruda a valores reales.

    Es al valor lo que `TipoDeColumna` (FG-05) es al tipo y `UnidadDeColumna`
    (FG-06) es a la unidad declarada en la cabecera: una propuesta con el
    recuento que la respalda, no solo el resultado final.
    """

    indice: int
    nombre: str

    numeros: pl.Series
    """La columna convertida a `Float64`. Las celdas ausentes -- vacías o
    centinela, de cualquier clase -- son `null`, NUNCA `0.0` (§7.10)."""

    celdas: int
    """Celdas de entrada, ausencias incluidas."""

    con_dato: int
    """Celdas que no son vacías ni centinela. El denominador de `numericas`."""

    vacias: int
    centinelas_texto: int
    centinelas_desbordamiento: int
    """Igual que en `TipoDeColumna`: aparte de las vacías, porque una columna
    llena de un centinela de desbordamiento es un sensor desconectado, no un
    canal a otra frecuencia."""

    numericas: int
    """Celdas con dato que SÍ se convirtieron a un `float` real."""

    no_numericas: int
    """Celdas con dato que no se pudieron interpretar como número, ni siquiera
    con una unidad embebida delante o detrás. Ejemplos en `ejemplos_no_numericos`."""

    ejemplos_no_numericos: tuple[str, ...]

    origen_unidad: OrigenUnidadEmbebida
    unidad_embebida: str | None
    """La unidad cruda de la columna si `origen_unidad` es `CONSISTENTE`, sin
    resolver contra el catálogo (eso es tarea de quien orqueste, con FG-06)."""

    celdas_con_unidad: int
    unidades_distintas: tuple[str, ...]
    """Todas las unidades crudas distintas vistas, en orden alfabético. Con
    `origen_unidad == CONSISTENTE` tiene un solo elemento; con `MEZCLADA`,
    más de uno -- son las que hay que enseñar en el aviso."""

    avisos: tuple[Aviso, ...] = ()

    @property
    def cobertura_numerica(self) -> float:
        """Fracción de las celdas CON DATO que se convirtieron a número.

        Sobre `con_dato`, no sobre `celdas`: igual que en FG-05, un canal a
        menor frecuencia que el fichero no es un problema de conversión.
        """
        if self.con_dato == 0:
            return 0.0
        return self.numericas / self.con_dato


def convertir_valores_de_columna(
    valores: Sequence[str] | pl.Series,
    *,
    indice: int = 0,
    nombre: str = "",
    decimal: str = ".",
    catalogo: Catalogo | None = None,
    centinelas_texto: frozenset[str] | None = None,
    centinelas_desbordamiento: frozenset[str] | None = None,
) -> ValoresDeColumna:
    """Convierte UNA columna cruda a `ValoresDeColumna`.

    `catalogo` es la vía normal de dar los centinelas (salen de
    `data/units.toml`, no de una lista propia de este módulo -- mismo
    razonamiento que `inferir_tipos_de_columna`). `centinelas_texto` y
    `centinelas_desbordamiento` existen para probar sin cargar el catálogo
    entero; si no se da ninguno de los tres, no hay centinelas y solo la celda
    vacía cuenta como ausencia.

    Acepta `Sequence[str]` además de `pl.Series` para que una prueba pueda
    pasar una lista de Python directamente (como ya hace
    `inferir_tipos_de_columna`); internamente se envuelve en una `Series` una
    sola vez, no celda a celda.
    """
    if catalogo is not None:
        if centinelas_texto is None:
            centinelas_texto = frozenset(catalogo.centinelas_texto)
        if centinelas_desbordamiento is None:
            centinelas_desbordamiento = frozenset(str(c) for c in catalogo.centinelas_i32)
    texto_sin_dato = list(centinelas_texto) if centinelas_texto is not None else []
    desbordamiento = (
        list(centinelas_desbordamiento) if centinelas_desbordamiento is not None else []
    )

    serie = (
        valores
        if isinstance(valores, pl.Series)
        else pl.Series(nombre or "valor", list(valores), dtype=pl.Utf8)
    )
    nombre_final = nombre or serie.name or "valor"
    celdas = serie.len()
    otro = "," if decimal == "." else "."
    patron = _PATRONES[decimal]

    # Todo el trabajo por celda vive en estas expresiones de Polars: ni una
    # sola de ellas recorre la columna en el intérprete de Python (ADR-009).
    df = pl.DataFrame({"v": serie.cast(pl.Utf8).fill_null("").str.strip_chars()})
    df = df.with_columns(vacia=(pl.col("v") == ""))
    df = df.with_columns(
        desbordamiento=(~pl.col("vacia") & pl.col("v").is_in(desbordamiento)),
    )
    df = df.with_columns(
        centinela_texto=(
            ~pl.col("vacia") & ~pl.col("desbordamiento") & pl.col("v").is_in(texto_sin_dato)
        ),
    )
    df = df.with_columns(
        ausente=(pl.col("vacia") | pl.col("desbordamiento") | pl.col("centinela_texto")),
        numero_crudo=pl.col("v").str.extract(patron, 1),
        unidad_cruda=pl.col("v").str.extract(patron, 2),
    )
    numero_limpio = pl.col("numero_crudo").str.replace_all(otro, "", literal=True)
    numero_limpio = numero_limpio.str.replace_all(r"\s+", "", literal=False)
    if decimal != ".":
        numero_limpio = numero_limpio.str.replace_all(decimal, ".", literal=True)
    df = df.with_columns(numero_parseado=numero_limpio.cast(pl.Float64, strict=False))
    df = df.with_columns(
        numero_final=pl.when(pl.col("ausente")).then(None).otherwise(pl.col("numero_parseado")),
        tiene_agrupacion=(
            ~pl.col("ausente")
            & (
                pl.col("numero_crudo").str.contains(otro, literal=True)
                | pl.col("numero_crudo").str.contains(r"\s", literal=False)
            ).fill_null(False)
        ),
        con_unidad=(
            ~pl.col("ausente")
            & pl.col("unidad_cruda").is_not_null()
            & (pl.col("unidad_cruda") != "")
        ),
    )
    df = df.with_columns(
        no_numerica=(~pl.col("ausente") & pl.col("numero_final").is_null()),
    )

    vacias = int(df["vacia"].sum())
    n_desbordamiento = int(df["desbordamiento"].sum())
    n_centinela_texto = int(df["centinela_texto"].sum())
    con_dato = celdas - vacias - n_desbordamiento - n_centinela_texto
    no_numericas = int(df["no_numerica"].sum())
    numericas = con_dato - no_numericas
    n_agrupacion = int(df["tiene_agrupacion"].sum())
    celdas_con_unidad = int(df["con_unidad"].sum())

    ejemplos_no_numericos = tuple(
        df.filter(pl.col("no_numerica"))["v"].unique().sort().to_list()[:MAX_EJEMPLOS]
    )
    unidades_distintas = tuple(
        df.filter(pl.col("con_unidad"))["unidad_cruda"].unique().drop_nulls().sort().to_list()
    )

    if celdas_con_unidad == 0:
        origen_unidad = OrigenUnidadEmbebida.NINGUNA
        unidad_embebida = None
    elif len(unidades_distintas) == 1:
        origen_unidad = OrigenUnidadEmbebida.CONSISTENTE
        unidad_embebida = unidades_distintas[0]
    else:
        origen_unidad = OrigenUnidadEmbebida.MEZCLADA
        unidad_embebida = None

    avisos: list[Aviso] = []
    if no_numericas:
        avisos.append(
            Aviso(
                "valores_no_numericos",
                f"la columna '{nombre_final}' tiene {no_numericas} de sus {con_dato} celdas "
                f"con dato que no se pueden interpretar como número (por ejemplo "
                f"{list(ejemplos_no_numericos)}); se guardan como ausentes, nunca como 0",
            )
        )
    if origen_unidad is OrigenUnidadEmbebida.MEZCLADA:
        avisos.append(
            Aviso(
                "unidad_embebida_mezclada",
                f"la columna '{nombre_final}' trae más de una unidad embebida en sus celdas "
                f"({', '.join(unidades_distintas)}); no se puede asumir una sola unidad para "
                "toda la columna, así que el número se extrae pero la unidad se deja sin "
                "resolver. Mezclar por ejemplo psi y bar en la misma columna es un factor de "
                "~14x: revisa el fichero de origen antes de dar por buenos estos valores",
            )
        )
    elif origen_unidad is OrigenUnidadEmbebida.CONSISTENTE and celdas_con_unidad < con_dato:
        avisos.append(
            Aviso(
                "unidad_embebida_parcial",
                f"la columna '{nombre_final}' declara la unidad {unidad_embebida!r} en "
                f"{celdas_con_unidad} de {con_dato} celdas con dato; el resto no trae unidad "
                "y se asume la misma",
            )
        )
    if n_agrupacion:
        avisos.append(
            Aviso(
                "separador_de_miles_normalizado",
                f"la columna '{nombre_final}' trae separador de miles en {n_agrupacion} de "
                f"sus {con_dato} celdas con dato ({otro!r} o espacio como agrupador); se ha "
                f"normalizado según el decimal ya detectado ({decimal!r}), sin volver a "
                "adivinarlo",
            )
        )

    return ValoresDeColumna(
        indice=indice,
        nombre=nombre_final,
        numeros=df["numero_final"].rename(nombre_final),
        celdas=celdas,
        con_dato=con_dato,
        vacias=vacias,
        centinelas_texto=n_centinela_texto,
        centinelas_desbordamiento=n_desbordamiento,
        numericas=numericas,
        no_numericas=no_numericas,
        ejemplos_no_numericos=ejemplos_no_numericos,
        origen_unidad=origen_unidad,
        unidad_embebida=unidad_embebida,
        celdas_con_unidad=celdas_con_unidad,
        unidades_distintas=unidades_distintas,
        avisos=tuple(avisos),
    )


@dataclass(slots=True, frozen=True)
class ResultadoValores:
    """Un `ValoresDeColumna` por columna, en el orden del fichero. El
    equivalente de `ResultadoTipos` (FG-05) para valores reales."""

    columnas: tuple[ValoresDeColumna, ...]

    @property
    def avisos(self) -> tuple[Aviso, ...]:
        return tuple(a for c in self.columnas for a in c.avisos)

    def por_nombre(self, nombre: str) -> ValoresDeColumna | None:
        for c in self.columnas:
            if c.nombre == nombre:
                return c
        return None


def convertir_valores(
    columnas: Sequence[Sequence[str] | pl.Series],
    nombres: Sequence[str],
    *,
    decimal: str = ".",
    catalogo: Catalogo | None = None,
) -> ResultadoValores:
    """Convierte varias columnas crudas a la vez, una llamada por columna a
    `convertir_valores_de_columna` (todas comparten el mismo `decimal`: es una
    propiedad del FICHERO, no de la columna -- `docs/07` §7.4 paso 4).

    El bucle de aquí es sobre COLUMNAS (unas pocas decenas en el CSV más
    ancho del corpus), no sobre celdas: no infringe ADR-009 por la misma razón
    que no lo infringe el bucle equivalente de `inferir_tipos`.
    """
    resultado = tuple(
        convertir_valores_de_columna(
            columna, indice=i, nombre=nombre, decimal=decimal, catalogo=catalogo
        )
        for i, (columna, nombre) in enumerate(zip(columnas, nombres, strict=True))
    )
    return ResultadoValores(columnas=resultado)
