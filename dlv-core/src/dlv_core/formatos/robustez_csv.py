"""Robustez del importador de CSV genérico (tarea FG-14).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.10, las tres primeras
filas de la tabla:

    | Filas de longitud variable | se rellena con vacío y se registra; no se aborta |
    | Columnas duplicadas        | se desambigua con sufijo y se avisa              |
    | Cabecera sin nombres       | se nombran col_1…col_n                           |

Las otras filas de esa tabla (centinelas, unidad embebida, miles, enum...) son
FG-06/07/08. Esta tarea es la última pieza de la cadena de sondeo:

    FG-01  ¿cómo se parte cada línea?
    FG-02  ¿qué es un número?
    FG-03  ¿qué línea es qué?
    FG-05  ¿qué clase de dato trae cada columna?          (sobre una MUESTRA)
    FG-14  leer el bloque de datos DE VERDAD, tolerando lo de arriba  <- esto

`tipos.inferir_tipos` (FG-05) ya aplica la regla de «se rellena con vacío y se
registra» sobre la muestra que inspecciona para proponer el tipo de cada
columna, y su docstring lo dice explícitamente: «Es la misma regla ... que
aplicará FG-14 al leer de verdad». Esta es esa lectura: el mismo criterio,
aplicado con Polars sobre el bloque de datos completo en vez de sobre las
`MAX_FILAS_INSPECCIONADAS` primeras.

POR QUÉ LOS NOMBRES DUPLICADOS SÍ SE RENOMBRAN AQUÍ, Y EN estructura.py NO
============================================================================
`estructura.py` (FG-03) avisa de `nombres_duplicados` y deliberadamente NO
renombra: para `Estructura`, la identidad de una columna de CSV genérico es su
POSICIÓN, el mismo criterio que usa Haltech con su `ID` (`docs/01` §1.3:
«[los nombres] no se deben corregir ni usar para la identidad del canal»). Esa
misma frase de `docs/01` sigue con la frase que resuelve la aparente
contradicción: «se muestran tal cual y **se permite alias en la capa de
presentación**».

Este módulo ES esa capa de presentación, y tiene además una razón práctica y
no solo estética: un `pl.DataFrame` no puede tener dos columnas con el mismo
nombre, así que para materializar la tabla de datos hace falta un nombre único
por columna de todos modos. `nombres_de_presentacion` desambigua con sufijo
(`RPM`, `RPM_2`) y avisa; la identidad interna sigue siendo la posición, y
nada de lo que hay aquí escribe ni reinterpreta `Estructura.nombres`.

FILAS DE LONGITUD VARIABLE: POR QUÉ NO SE REIMPLEMENTA EL LECTOR
==================================================================
`formatos/cuerpo.py` (F1-02) ya resolvió este problema para el camino nativo
con `truncate_ragged_lines=True` de Polars: rellena con nulos las filas
cortas y descarta los campos sobrantes de las largas, sin excepción y sin
bucle de Python. Aquí se usa el mismo parámetro sobre el bloque de datos del
camino genérico -- **no se reimplementa un partidor de campos en Python**,
que es justo lo que ya evitó `dividir_campos` de `sondeo.py` para el caso
general y lo que aquí evitaría un recorrido de millones de filas a 100 ns por
iteración (ver ADR-009 en `CLAUDE.md`).

Para CONTAR cuántas filas son cortas o largas (Polars no lo dice: solo rellena
o trunca en silencio) se usa el mismo recurso que `formatos/limpieza.py`
(F1-03) para el camino nativo: contar el delimitador por línea con
`pl.Expr.str.count_matches`, vectorizado en Rust, no con un bucle Python fila
a fila. La diferencia con `limpieza.py` es que aquí el delimitador no es
siempre `,` y puede haber comillas, así que el contenido citado se retira antes
de contar (`_quitar_contenido_citado`): un delimitador dentro de un campo
citado no es un campo de más.

QUÉ NO HACE ESTE MÓDULO
========================
No decide tipos (FG-05), no extrae unidades (FG-06), no limpia valores no
numéricos ni separadores de miles (FG-07), no construye enums (FG-08) y no
convierte a canónica. Devuelve un `pl.DataFrame` de texto (`Utf8` en todas las
columnas) tal cual viene en el fichero, más los avisos de robustez -- lo que
las tareas siguientes de la cadena ya esperan recibir (`tipos.inferir_tipos`
trabaja igual sobre filas de texto ya partidas).

Solo se opera sobre `bytes`/`str` que ya están en memoria (ADR-002: `dlv-core`
no toca el sistema de ficheros).
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from dlv_core.formatos.estructura import Estructura
from dlv_core.formatos.sondeo import Sondeo
from dlv_core.informes import Aviso

__all__ = [
    "ErrorDeRobustez",
    "LecturaRobusta",
    "leer_bloque_de_datos",
    "nombres_de_presentacion",
]


class ErrorDeRobustez(ValueError):
    """No se puede leer el bloque de datos sin inventar un delimitador."""


def _columna_polars(indice: int) -> str:
    """Nombre que da Polars a una columna leída con `has_header=False`.

    Misma convención 1-based que `formatos/cuerpo.columna_polars`: la columna
    0 se llama `"column_1"`. Se reimplementa en vez de importarse porque la de
    `cuerpo.py` está atada a `Cabecera` (formato nativo) y esta solo necesita
    el índice.
    """
    return f"column_{indice + 1}"


def nombres_de_presentacion(
    estructura: Estructura, *, prefijo: str = "col"
) -> tuple[tuple[str, ...], list[Aviso]]:
    """Nombres de columna únicos y sin huecos, para mostrar y para Polars.

    Combina los dos casos de §7.10 que son responsabilidad de esta tarea:

    1. **Cabecera sin nombres** (ninguna fila de nombres en absoluto):
       `Estructura.nombres_o_posicionales(prefijo)` ya lo resuelve (FG-03) con
       `col_1…col_n`; aquí solo se reutiliza.
    2. **Huecos individuales** dentro de una cabecera que SÍ existe
       (`Time,,MAP`): `nombres_o_posicionales` no los toca -- si `nombres` no
       está vacío, lo devuelve tal cual, huecos incluidos -- así que se
       rellenan aquí con la misma regla posicional.
    3. **Columnas duplicadas**: se desambigua con sufijo `_2`, `_3`... La
       primera aparición conserva el nombre; si el sufijo generado choca con
       un nombre que el fichero ya trae (`RPM` y `RPM_2` a la vez, caso raro
       pero posible), se sigue incrementando hasta encontrar uno libre.

    Ninguno de los dos avisos que puede emitir sustituye a los de FG-03
    (`estructura.avisos` sigue avisando `nombres_duplicados` / `nombres_vacios`
    con su propio código): estos son avisos de la CAPA DE PRESENTACIÓN, no de
    la estructura del fichero, y por eso llevan códigos distintos.
    """
    avisos: list[Aviso] = []
    base = list(estructura.nombres_o_posicionales(prefijo))

    huecos = [i for i, nombre in enumerate(base) if not nombre.strip()]
    if huecos:
        for i in huecos:
            base[i] = f"{prefijo}_{i + 1}"
        avisos.append(
            Aviso(
                "nombre_de_columna_generado",
                f"las columnas {[i + 1 for i in huecos]} no traían nombre en la fila "
                f"de cabecera; se etiquetan por posición ('{prefijo}_N') solo para "
                "mostrarlas. No cambia la identidad de la columna, que sigue siendo "
                "su posición",
            )
        )

    usados: set[str] = set()
    finales: list[str] = []
    cambios: list[str] = []
    for i, nombre in enumerate(base):
        candidato = nombre
        sufijo = 2
        while candidato in usados:
            candidato = f"{nombre}_{sufijo}"
            sufijo += 1
        if candidato != nombre:
            cambios.append(f"'{nombre}' -> '{candidato}' (columna {i + 1})")
        usados.add(candidato)
        finales.append(candidato)

    if cambios:
        avisos.append(
            Aviso(
                "columna_duplicada_desambiguada",
                "hay nombres de columna repetidos; se desambiguan con sufijo solo "
                f"para esta vista: {', '.join(cambios)}. La identidad de cada columna "
                "sigue siendo su posición, no este nombre (docs/01 §1.3)",
            )
        )

    return tuple(finales), avisos


def _quitar_contenido_citado(serie: pl.Series, comilla: str) -> pl.Series:
    """Retira lo que hay entre comillas, para no contar un delimitador citado.

    `1,"2,3",4` tiene 2 campos con `,` de delimitador, no 4: la coma de dentro
    de `"2,3"` no separa nada. Sin esto, una sola celda citada que contenga el
    delimitador se contaría como filas de más.

    Vectorizado (`str.replace_all`, Rust), no un bucle por línea. Se ignora el
    escapado de comillas dobladas (`""`) dentro del campo -- una aproximación
    igual de buena que la que ya acepta `sondeo._contar_campos` para puntuar
    delimitadores, y suficiente para CONTAR, que es todo lo que se necesita
    aquí: la lectura de verdad la hace el `quote_char` de Polars más abajo, que
    sí entiende el escapado.
    """
    patron = f"{comilla}[^{comilla}]*{comilla}"
    return serie.str.replace_all(patron, "")


def _contar_campos(serie: pl.Series, delimitador: str, comilla: str | None) -> pl.Series:
    """Campos por línea: ocurrencias del delimitador fuera de comillas, más uno."""
    base = serie if comilla is None else _quitar_contenido_citado(serie, comilla)
    return base.str.count_matches(delimitador, literal=True) + 1


@dataclass(slots=True, frozen=True)
class LecturaRobusta:
    """El bloque de datos ya leído, tolerando los tres casos de §7.10 de FG-14."""

    tabla: pl.DataFrame
    """Todas las columnas en `Utf8`, tal como venían escritas. Convertir a
    número, extraer unidades o construir enums es FG-05/06/07/08, no esto."""

    nombres: tuple[str, ...]
    """Los nombres de `tabla.columns`, ya desambiguados (`nombres_de_presentacion`)."""

    filas_de_datos: int
    """Cuántas líneas del bloque de datos se han leído (fichero completo, no
    la muestra de FG-01/02/03/05)."""

    filas_cortas: int
    filas_largas: int
    avisos: tuple[Aviso, ...]


def leer_bloque_de_datos(
    texto: str,
    sondeo: Sondeo,
    estructura: Estructura,
    *,
    prefijo: str = "col",
) -> LecturaRobusta:
    """Lee el bloque de datos de un CSV genérico, tolerando §7.10 (FG-14).

    `texto` es el fichero YA DECODIFICADO (con `sondeo.codificacion`, que es
    quien decidió la codificación -- FG-01). Puede ser el fichero completo o
    solo la muestra que vieron FG-01/02/03; con la muestra se puede probar el
    módulo sin datos sintéticos de millones de filas, y con el fichero
    completo es como lo usará el asistente de verdad (FG-11).

    `sondeo` y `estructura` son los resultados YA CALCULADOS de FG-01 y FG-03
    sobre esos mismos bytes: igual que en `estructura.analizar_estructura`, se
    reciben en vez de recalcularse para que el delimitador, la comilla y el
    inicio del bloque de datos se decidan en un solo sitio.
    """
    if sondeo.delimitador is None:
        raise ErrorDeRobustez(
            "el sondeo no propuso delimitador, así que no hay campos que leer. Hay "
            "que elegirlo en el asistente antes de leer el bloque de datos"
        )

    nombres, avisos = nombres_de_presentacion(estructura, prefijo=prefijo)
    n = estructura.n_columnas

    # Mismo criterio de «línea en blanco» que FG-03 (estructura.py): si
    # divergiera, `estructura.linea_inicio_datos` dejaría de apuntar a la
    # misma línea aquí que allí en cuanto el fichero trajera una línea vacía
    # de verdad, y el bloque de datos se leería desplazado.
    lineas = [linea for linea in texto.splitlines() if linea.strip()]
    lineas_datos = lineas[estructura.linea_inicio_datos :]

    if not lineas_datos:
        avisos.append(
            Aviso(
                "sin_filas_de_datos",
                "no hay ninguna línea de datos que leer a partir de la fila "
                f"{estructura.linea_inicio_datos + 1}",
            )
        )
        return LecturaRobusta(
            tabla=pl.DataFrame(schema=dict.fromkeys(nombres, pl.Utf8)),
            nombres=nombres,
            filas_de_datos=0,
            filas_cortas=0,
            filas_largas=0,
            avisos=tuple(avisos),
        )

    # Cuántas filas son cortas o largas: Polars las rellena/trunca en
    # silencio (más abajo), así que el recuento se hace aparte, vectorizado,
    # ANTES de leer. Es la misma idea que `limpieza.detectar_filas_malformadas`
    # para el camino nativo, generalizada a un delimitador y una comilla
    # cualquiera en vez de la coma fija del formato Haltech.
    conteo = _contar_campos(pl.Series("linea", lineas_datos), sondeo.delimitador, sondeo.comilla)
    filas_cortas = int((conteo < n).sum())
    filas_largas = int((conteo > n).sum())

    if filas_cortas:
        avisos.append(
            Aviso(
                "filas_cortas",
                f"{filas_cortas} de {len(lineas_datos)} filas de datos traen menos de "
                f"{n} campos; las celdas que faltan se guardan como ausentes -- nunca "
                "como 0 (§7.10) -- y no se aborta la carga",
            )
        )
    if filas_largas:
        avisos.append(
            Aviso(
                "filas_largas",
                f"{filas_largas} de {len(lineas_datos)} filas de datos traen más de "
                f"{n} campos; los campos de sobra se descartan (mismo criterio que "
                "`formatos/cuerpo.py` en el camino nativo) y no se aborta la carga",
            )
        )

    # `truncate_ragged_lines=True` es la pieza que de verdad resuelve la fila
    # larga y la corta -- ver la cabecera del módulo, «por qué no se
    # reimplementa el lector» -- y `null_values=[""]` es lo que hace que el
    # hueco de una fila corta llegue como ausente y no como cadena vacía
    # indistinguible de un cero (docs/01: "hueco != 0").
    #
    # Se reconstruye el bloque como bytes UTF-8 en vez de pasar `texto`
    # decodificado directamente: `pl.read_csv` solo decodifica "utf8" o
    # "utf8-lossy" (no admite latin-1), y `texto` ya viene decodificado con
    # la codificación que detectó FG-01 -- re-codificarlo a UTF-8 es válido
    # sea cual sea el origen, porque un `str` de Python no recuerda de qué
    # bytes vino.
    cuerpo = ("\n".join(lineas_datos) + "\n").encode("utf-8")
    esquema = {_columna_polars(i): pl.Utf8 for i in range(n)}
    tabla = pl.read_csv(
        cuerpo,
        has_header=False,
        separator=sondeo.delimitador,
        quote_char=sondeo.comilla,
        infer_schema_length=0,
        schema_overrides=esquema,
        null_values=[""],
        truncate_ragged_lines=True,
        new_columns=list(nombres),
    )

    return LecturaRobusta(
        tabla=tabla,
        nombres=nombres,
        filas_de_datos=len(lineas_datos),
        filas_cortas=filas_cortas,
        filas_largas=filas_largas,
        avisos=tuple(avisos),
    )
