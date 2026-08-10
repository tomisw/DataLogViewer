"""Columnas de texto y booleanas -> canal enum con diccionario autogenerado
(tarea FG-08).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.10:

    | Columna de texto libre | -> canal enum con diccionario autogenerado |
    | Booleanos (`true/false`, `on/off`, `sí/no`) | -> canal enum de 2 estados |

Quinto eslabón de la cadena del importador genérico, apoyado en el cuarto:

    FG-01  ¿cómo se parte cada línea?
    FG-02  ¿qué es un número?
    FG-03  ¿qué línea es qué?
    FG-05  ¿qué clase de dato trae cada columna?
    FG-08  columna ENUM_TEXTO/BOOLEANO -> códigos + diccionario   <- esto

FG-05 (`dlv_core.formatos.tipos`) YA decidió que una columna es
`TipoColumna.ENUM_TEXTO` o `TipoColumna.BOOLEANO`. Este módulo no vuelve a
inferir eso: recibe la columna completa y produce la CONVERSIÓN -- un código
`uint16` por celda con dato y el diccionario código -> etiqueta que la
acompaña, listo para `Storage.ENUM_U16` (`dlv_core.almacen`).

LA DIFERENCIA DE FONDO CON FG-05: MUESTRA FRENTE A FICHERO COMPLETO
=====================================================================
`inferir_tipos_de_columna` mira como mucho `MAX_FILAS_INSPECCIONADAS` filas
del principio del fichero -- y lo dice explícitamente en su docstring: «se
clasifica sobre las filas que se le den [...] ninguna conclusión de aquí es
sobre el fichero entero». Por eso su bucle de Python es aceptable pese a
ADR-009 (unas pocas decenas/centenas de filas de MUESTRA, nunca 73 M).

Este módulo hace lo contrario a propósito: construye el diccionario y asigna
el código a **todas** las filas del canal, porque es la conversión de verdad,
no una propuesta para el asistente. Un `for` por celda aquí SÍ sería un bucle
por muestra en el sentido de ADR-009, así que la asignación de código se hace
con expresiones de Polars (`is_in`, `when/then/otherwise`,
`Series.replace_strict`) sobre la columna completa. El único bucle de Python
que queda es sobre los VALORES DISTINTOS (como mucho
`LIMITE_CARDINALIDAD_ENUM`, no una fila) para construir el diccionario -- la
misma categoría de bucle acotado que ya usa `tipos._es_pareja_booleana` sobre
las parejas declaradas, y que el comprobador de `tools/banco.py adr009`
tampoco marca: no llama a `iterrows`/`itertuples`/`iter_rows`/`apply(lambda)`.

DECISIÓN 1 -- LA ESTABILIDAD DEL CÓDIGO ASIGNADO
==================================================
Si el código de cada etiqueta saliera del ORDEN DE APARICIÓN en el fichero
("la primera etiqueta vista es 0, la segunda 1..."), dos logs de la misma
sesión -- misma ECU, mismo canal, mismos estados posibles -- podrían asignar
códigos distintos a la misma etiqueta solo porque el coche arrancó en marcha
1 en un log y en marcha 2 en el otro. Dos logs así ya no se pueden comparar
por código sin traducir cada uno con su propio diccionario, que es
precisamente el problema que un canal enum "estable" tiene que evitar
(`docs/07` §7.11: la identidad de canal entre logs es lo que hace útil la
capa de roles, y un enum cuyo código no es estable rompe esa comparación por
debajo).

El criterio elegido es el **orden alfabético de la etiqueta** (orden de
código Unicode, el mismo que usa `sorted()` de Python y `Series.sort()` de
Polars sobre `Utf8` -- se comprobó que coinciden, incluidas letras
acentuadas: los dos comparan por punto de código, no por colación de un
locale concreto que podría variar entre máquinas). Con esto, dos logs que
observan el MISMO conjunto de etiquetas -- aunque en orden distinto, aunque
uno vea una etiqueta que el otro no -- asignan el mismo código a cada
etiqueta que SÍ comparten, porque "primero alfabéticamente" no depende de en
qué fila apareció ni de qué fichero se está leyendo. Es una propiedad que el
orden de aparición no tiene y que no exige mantener un registro externo de
"qué etiqueta tuvo qué código la última vez" (eso sería la vía completa --
persistir el diccionario en el perfil `.dlvimport` de §7.9 -- y queda fuera
del alcance de este módulo, que convierte una columna, no coordina varios
ficheros).

Excepción deliberada: los **booleanos**. Para los dos estados de una pareja
de §7.10 (`true/false`, `on/off`, `sí/no`...) no se usa el orden alfabético
sino un código semántico fijo -- **0 = negativo, 1 = positivo** -- tomado de
`tipos.PAREJAS_BOOLEANAS`, donde el primer elemento de cada pareja es siempre
el positivo y el segundo el negativo. Se prefiere a lo alfabético porque
"positivo/negativo" es la lectura que cualquiera espera de una columna
booleana (un limitador activo es más natural como 1 que como el resultado de
comparar "activo" con "inactivo" letra a letra), y es igual de estable: la
pareja sale de una lista fija en código (`tipos.PAREJAS_BOOLEANAS`), no del
orden de aparición en el fichero.

DECISIÓN 2 -- EL LÍMITE DE CARDINALIDAD
=========================================
Una columna de texto con un valor distinto por fila (un identificador único,
una marca de tiempo de texto libre, un comentario) NO es un enum: es texto
libre, y convertirla generaría un diccionario tan grande como el fichero.
`LIMITE_CARDINALIDAD_ENUM` pone la frontera.

El valor elegido, 512, sale de dos referencias, no de una intuición:

- Por arriba: `data/enums.toml` (el catálogo de canales enumerados del
  propio Haltech, F0-11) es la evidencia real de qué aspecto tiene un enum
  de ECU genuino. Su canal de rango más ancho que de verdad es un enum (no
  un `bitmask`, que es otra cosa) llega a 15 estados (`Data Log Memory
  State`, rango 0..15). 512 es más de 30 veces ese máximo observado, margen
  de sobra para un fabricante distinto con una tabla de códigos de fallo
  larga, sin acercarse al límite real del almacenamiento.
- Por abajo: `Storage.ENUM_U16` (`dlv_core.almacen`) exige que el código
  quepa en un entero sin signo de 16 bits -- 65 536 posibles. 512 dista
  todavía dos órdenes de magnitud de ese techo, así que el límite lo pone la
  semántica (qué es razonable llamar "enum"), no la capacidad de
  almacenamiento.

Por debajo del límite, la columna se convierte igual que un texto libre real
(FG-05 ya la habrá clasificado `ENUM_TEXTO` con `distintos_truncados=True`
sobre la MUESTRA, y aquí, sobre el fichero completo, se confirma o se
descarta esa sospecha con el dato de verdad). Cuando se supera, la regla de
`docs/07` §7.10/E1.7 es "avisa y sigue", no "aborta": se devuelve
`convertido=False` con un `Aviso` que explica por qué, y la columna queda sin
convertir -- sigue siendo importable como texto en crudo y sin rol (§7.8: "se
puede importar dejando canales sin rol"), simplemente no se le construye un
diccionario de miles de entradas que ninguna leyenda de gráfico puede
mostrar.

UNA COLUMNA "BOOLEANA" EN LA MUESTRA PUEDE NO SERLO EN EL FICHERO ENTERO
==========================================================================
FG-05 clasifica `BOOLEANO` mirando solo la muestra. Es perfectamente posible
que las primeras `MAX_FILAS_INSPECCIONADAS` filas solo muestren `true`/
`false` y una fila 50 000 traiga un tercer estado (`unknown`, un error de
exportación, lo que sea). Si eso pasa, este módulo NO fuerza la pareja
booleana sobre datos que ya no la cumplen: cae al criterio general
(alfabético) y avisa, en vez de fingir que sigue siendo una columna de dos
estados. Ver `_mapa_booleano` y el aviso `booleano_no_confirmado_en_
columna_completa`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import polars as pl

from dlv_core.formatos.tipos import PAREJAS_BOOLEANAS
from dlv_core.informes import Aviso
from dlv_core.unidades import Catalogo

__all__ = [
    "LIMITE_CARDINALIDAD_ENUM",
    "ResultadoEnum",
    "convertir_a_enum",
]

#: Ver "DECISIÓN 2" en la cabecera del módulo: 512 es ~30x el enum genuino
#: más ancho observado en `data/enums.toml` (15 estados) y todavía dos
#: órdenes de magnitud por debajo del techo real de `Storage.ENUM_U16`
#: (65 536). No es un umbral de física -- no vive en `data/umbrales.toml`,
#: que es de los detectores -- es una heurística de formato, del mismo tipo
#: que `tipos.COBERTURA_NUMERICA_MINIMA` o `sondeo.CONFIANZA_MINIMA`. Se
#: puede pasar otro valor por parámetro.
LIMITE_CARDINALIDAD_ENUM = 512

#: Los elementos NEGATIVOS de cada pareja de `tipos.PAREJAS_BOOLEANAS`
#: (segundo elemento: "false", "off", "no", "no", "falso", "no") ya
#: normalizados (minúsculas). Código 0.
_NEGATIVOS = frozenset(negativo for _, negativo in PAREJAS_BOOLEANAS)

#: Los elementos POSITIVOS (primer elemento de cada pareja: "true", "on",
#: "sí", "si", "verdadero", "yes"). Código 1.
_POSITIVOS = frozenset(positivo for positivo, _ in PAREJAS_BOOLEANAS)


@dataclass(slots=True, frozen=True)
class ResultadoEnum:
    """Resultado de convertir UNA columna de texto/booleano a canal enum.

    `codigos` y `mascara_presente` siguen el mismo patrón que
    `dlv_core.almacen.construir_desde_polars`: la ausencia se representa con
    una MÁSCARA, no con un centinela dentro del valor (ADR-003: "el propio
    hueco ya lo dice la ausencia de la fila"). `mascara_presente` tiene la
    longitud de la columna original; `codigos` solo trae los códigos de las
    celdas CON DATO, en el mismo orden relativo -- así que
    `mascara_presente` es exactamente lo que hay que aplicar a la marca de
    tiempo del grupo de muestreo para que ambos arrays queden alineados,
    igual que `t_grupo = t_relativo[mascara]` en `construir_desde_polars`.
    """

    convertido: bool
    """`False` cuando la columna no se ha convertido -- hoy, solo por
    cardinalidad excesiva (`LIMITE_CARDINALIDAD_ENUM`, "DECISIÓN 2"). La
    columna sigue siendo importable como texto en crudo y sin rol (§7.8);
    lo que no se hace es fingir un enum con un diccionario inservible."""

    diccionario: Mapping[int, str]
    """Código -> etiqueta, tal como aparece en el fichero (recortada de
    espacios en los extremos, no de los internos: "Punto Muerto " y "Punto
    Muerto" son la misma etiqueta, pero "Punto  Muerto" con doble espacio
    interno sigue siendo una etiqueta distinta -- ese doble espacio puede ser
    justo el error de exportación que el informe tiene que poder señalar).
    Vacío si `convertido` es `False`."""

    codigos: np.ndarray
    """`uint16`, una por celda CON DATO, en el mismo orden relativo que la
    columna original. Longitud == `mascara_presente.sum()`."""

    mascara_presente: np.ndarray
    """`bool`, longitud igual a la columna original. `True` donde había un
    valor -- ni vacío, ni nulo, ni un centinela de `data/units.toml`."""

    n_valores_distintos: int
    """Cuántas etiquetas distintas tiene la columna COMPLETA -- a diferencia
    de `TipoDeColumna.valores_distintos` (FG-05), que es sobre una muestra y
    puede estar truncado. Se guarda incluso cuando `convertido` es `False`,
    porque es precisamente el número que explica por qué no se convirtió."""

    avisos: tuple[Aviso, ...] = ()


def _mapa_booleano(distintos: list[str]) -> dict[str, int] | None:
    """Código 0 = negativo, 1 = positivo, según `tipos.PAREJAS_BOOLEANAS`.

    `None` si `distintos` no son exactamente dos etiquetas que formen una
    pareja conocida -- entonces quien llama cae al criterio alfabético
    general (ver "UNA COLUMNA BOOLEANA EN LA MUESTRA..." en la cabecera).

    El bucle es sobre `distintos` (aquí siempre 2 elementos si llega a
    ejecutarse, nunca una vez por fila): ADR-009 no aplica, igual que en
    `tipos._es_pareja_booleana`, que recorre la misma clase de colección
    pequeña.
    """
    if len(distintos) != 2:
        return None
    normalizados = {etiqueta: etiqueta.strip().lower() for etiqueta in distintos}
    negativo = next((e for e, n in normalizados.items() if n in _NEGATIVOS), None)
    positivo = next((e for e, n in normalizados.items() if n in _POSITIVOS), None)
    if negativo is None or positivo is None or negativo == positivo:
        return None
    return {negativo: 0, positivo: 1}


def convertir_a_enum(
    serie: pl.Series,
    *,
    booleano: bool = False,
    centinelas_texto: frozenset[str] | None = None,
    catalogo: Catalogo | None = None,
    limite_cardinalidad: int = LIMITE_CARDINALIDAD_ENUM,
    nombre_columna: str = "",
) -> ResultadoEnum:
    """Convierte una columna de texto en crudo a códigos `uint16` + diccionario.

    `serie` es la columna COMPLETA (`pl.Utf8`, nulos donde no había celda),
    no una muestra: es la misma columna que ya pasó por
    `tipos.inferir_tipos_de_columna` (sobre una muestra) y salió
    `TipoColumna.ENUM_TEXTO` o `TipoColumna.BOOLEANO`. Este módulo no repite
    esa clasificación; asume que quien llama ya la hizo y solo pasa `True` en
    `booleano` cuando FG-05 propuso `BOOLEANO` para esta columna.

    `catalogo` es la vía normal de pasar los centinelas de texto (los mismos
    de `data/units.toml [centinelas] texto` que ya usa FG-05), para que
    `NULL`, `#N/A`, `---`... cuenten como ausencia y no como una etiqueta más
    del diccionario -- si aquí se contaran como estado, un canal con cinco
    filas de `#N/A` saldría con un estado "#N/A" en la leyenda, que no es un
    dato del coche. `centinelas_texto` existe para probar el módulo sin
    cargar el catálogo entero; si no se da ninguno de los dos, solo la celda
    vacía y el nulo de Polars cuentan como ausencia.

    Vectorizado por completo sobre `serie` (ADR-009): recorte de espacios,
    máscara de ausencia y asignación de código son expresiones de Polars. El
    único trabajo en Python puro es sobre el conjunto de etiquetas
    DISTINTAS, acotado por `limite_cardinalidad` -- ver la cabecera del
    módulo.
    """
    centinelas: frozenset[str] = (
        centinelas_texto
        if centinelas_texto is not None
        else (frozenset(catalogo.centinelas_texto) if catalogo is not None else frozenset())
    )

    marco = pl.DataFrame({"bruto": serie}).with_columns(
        pl.col("bruto").str.strip_chars().alias("recortado")
    )
    ausente = pl.col("recortado").is_null() | (pl.col("recortado") == "")
    if centinelas:
        ausente = ausente | pl.col("recortado").is_in(list(centinelas))
    marco = marco.with_columns(
        pl.when(ausente).then(None).otherwise(pl.col("recortado")).alias("valor")
    )
    valor = marco["valor"]

    etiqueta_columna = f"la columna {nombre_columna!r}" if nombre_columna else "la columna"
    n = valor.len()
    vacio_codigos = np.array([], dtype=np.uint16)
    vacia_mascara = np.zeros(n, dtype=bool)

    distintos_serie = valor.drop_nulls().unique().sort()
    n_distintos = distintos_serie.len()

    if n_distintos == 0:
        # Ninguna celda con dato: no hay nada que enumerar. FG-05 ya la
        # habrá marcado `VACIA`; aquí no es un error, solo no hay trabajo.
        return ResultadoEnum(
            convertido=True,
            diccionario={},
            codigos=vacio_codigos,
            mascara_presente=vacia_mascara,
            n_valores_distintos=0,
        )

    if n_distintos > limite_cardinalidad:
        ejemplos = distintos_serie.head(5).to_list()
        aviso = Aviso(
            "enum_cardinalidad_excesiva",
            f"{etiqueta_columna} tiene al menos {n_distintos} valores distintos en "
            f"el fichero completo (por ejemplo {ejemplos}), por encima del límite de "
            f"{limite_cardinalidad} (ver LIMITE_CARDINALIDAD_ENUM). No es un enum de "
            "estados, es texto libre -- típico de un identificador único por fila. "
            "No se convierte: se importa en crudo y sin rol, para no generar un "
            "diccionario que ninguna leyenda puede mostrar",
        )
        return ResultadoEnum(
            convertido=False,
            diccionario={},
            codigos=vacio_codigos,
            mascara_presente=vacia_mascara,
            n_valores_distintos=n_distintos,
            avisos=(aviso,),
        )

    avisos: list[Aviso] = []
    distintos = distintos_serie.to_list()  # a lo sumo `limite_cardinalidad` etiquetas
    mapa: dict[str, int] | None = _mapa_booleano(distintos) if booleano else None

    if booleano and mapa is None:
        avisos.append(
            Aviso(
                "booleano_no_confirmado_en_columna_completa",
                f"{etiqueta_columna} se propuso como booleano a partir de una muestra "
                f"(FG-05), pero sobre el fichero completo tiene {n_distintos} valor(es) "
                f"distinto(s) {distintos[:5]}, no dos, o no forman una pareja conocida "
                "de PAREJAS_BOOLEANAS. Se trata como enum de texto general (código por "
                "orden alfabético) en vez de forzar 0/1",
            )
        )

    if mapa is None:
        # Orden alfabético (código Unicode): ver "DECISIÓN 1" en la cabecera
        # del módulo. `distintos` ya viene de `distintos_serie.sort()`, así
        # que `enumerate` alcanza para asignar el código -- no hace falta
        # volver a ordenar en Python.
        mapa = {etiqueta_valor: codigo for codigo, etiqueta_valor in enumerate(distintos)}

    codigos_serie = valor.replace_strict(mapa, default=None, return_dtype=pl.UInt16)
    mascara_presente = codigos_serie.is_not_null().to_numpy()
    codigos = codigos_serie.drop_nulls().to_numpy().astype(np.uint16)
    diccionario = {codigo: etiqueta_valor for etiqueta_valor, codigo in mapa.items()}

    return ResultadoEnum(
        convertido=True,
        diccionario=diccionario,
        codigos=codigos,
        mascara_presente=mascara_presente,
        n_valores_distintos=n_distintos,
        avisos=tuple(avisos),
    )
