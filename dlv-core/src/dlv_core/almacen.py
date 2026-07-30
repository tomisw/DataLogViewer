"""Almacén columnar: representación en memoria de cada canal (ADR-003).

Regla de disciplina de rendimiento (ADR-009, `docs/03-arquitectura.md` §3.2):

    Ninguna ruta que se ejecute una vez por muestra puede estar escrita en
    Python interpretado. Todo cálculo sobre series es una operación de NumPy
    o Polars sobre el array completo: `for` sobre muestras, `.apply()`,
    `.iterrows()` y `map()` por elemento están prohibidos en `dlv-core`. Lo
    que no se puede vectorizar (histéresis, decimación por moda con longitud
    de racha, autómatas de estado) se implementa en Numba `@njit`, no en
    Python puro.

Este módulo no accede al sistema de ficheros por su cuenta: todo lo que
necesita como entrada (arrays ya materializados, un `polars.DataFrame`, un
lector) llega como parámetro desde quien lo llama.

`construir_desde_polars` agrupa columnas por patrón de nulos --el "grupo de
muestreo" de docs/03 §3.4 paso 4-- delegando en
`dlv_core.grupos_muestreo.detectar_grupos_de_muestreo` (F1-06), que compara
las máscaras de todas las columnas de una vez con `numpy.unique(axis=0)` en
vez de un bucle de Python acumulando en un `dict`.

POR QUÉ `indexar` NO DEVUELVE `np.ndarray` (F1-07)
===================================================
El stub original de esta función (dejado por una tarea anterior) prometía
`indexar(serie: ChannelSeries) -> np.ndarray`. Un único array no puede cargar
lo que pide docs/03 §3.4 paso 5: mín, máx, un conjunto de percentiles Y una
clasificación categórica (`activo/constante/vacío/fuera de rango`) son cosas
de naturaleza distinta -- escalares, un vector de percentiles y booleanos --
que forzar dentro de un `np.ndarray` obligaría a inventar una codificación
posicional sin nombre ("la posición 7 es `constante`") que cualquier lector
tendría que memorizar. Se sustituye por `IndiceCanal`, un `dataclass` con un
campo por concepto, igual que se sustituyó la firma de `construir_desde_polars`
en F1-05 cuando el stub original no podía recibir lo que necesitaba para
hacer su trabajo. El cálculo NumPy que sí produce cada campo (mín, máx,
percentiles) sigue siendo vectorizado (ADR-009); lo que cambia es solo cómo
se empaqueta el resultado.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np
import polars as pl

from dlv_core.formatos.cuerpo import columna_polars
from dlv_core.formatos.haltech import Cabecera
from dlv_core.grupos_muestreo import detectar_grupos_de_muestreo
from dlv_core.reloj import desenrollar_medianoche
from dlv_core.roles import ChannelKey
from dlv_core.unidades import Afin


class Storage(Enum):
    """Representación de almacenamiento de un canal (ADR-003)."""

    INT32_SCALED = auto()  # entero crudo + (a, b) a canónica — camino nativo
    FLOAT32 = auto()  # decimal de origen, precisión suficiente
    FLOAT64 = auto()  # decimal que necesita precisión (tiempo, GPS)
    ENUM_U16 = auto()  # estado con diccionario de códigos
    BITS_U32 = auto()  # máscara de bits


@dataclass(slots=True)
class ChannelSeries:
    """Una serie temporal de canal, tal como vive en el almacén (ADR-003).

    `t` se comparte por referencia entre canales del mismo grupo de muestreo
    (§3.2 ADR-003): construir `ChannelSeries` no copia `t`.
    """

    key: ChannelKey
    role: str | None
    t: np.ndarray  # uint32, ms desde t0 del segmento, compartido por grupo
    v: np.ndarray  # según `storage`
    storage: Storage
    to_canon: Afin
    dimension: str | None  # None => se muestra en crudo, sin unidad


def construir_desde_polars(
    df: pl.DataFrame,
    cabecera: Cabecera,
    *,
    columna_tiempo: str,
    storage_por_columna: Mapping[str, Storage],
) -> list[ChannelSeries]:
    """Construye una `ChannelSeries` por canal de la cabecera (F1-01/F1-02).

    `df` es el `DataFrame` crudo de `dlv_core.formatos.cuerpo.parsear_cuerpo`,
    ya limpio de centinelas (`dlv_core.formatos.limpieza.nulificar_centinelas`,
    F1-03) si procede. `cabecera` da la identidad de cada columna (`Canal.id`,
    `.dimension`, `.a_canonica`) que el `DataFrame` por sí solo no lleva.

    Agrupa canales por patrón de nulos exacto (§3.4 paso 4, "grupos de
    muestreo"): dos canales con el mismo NÚMERO de muestras pero en filas
    distintas van a grupos distintos, porque comparten cuántas, no cuáles.
    Dentro de cada grupo, `t` es el mismo array de NumPy por referencia para
    todos los canales -- no se copia (ADR-003) -- y tanto `t` como `v` ya
    vienen sin las filas nulas del grupo: guardar el hueco como parte de `v`
    obligaría a un centinela dentro de un entero sin signo de por sí, y el
    propio hueco ya lo dice la ausencia de la fila en `t`.

    `to_numpy()` se deja con su `allow_copy=True` por omisión (ADR-001: lo
    que importa es "sin bucle de Python fila a fila", no "cero bytes
    copiados nunca"). Un `filter()` sobre un `DataFrame` leído en varios
    trozos internos por Polars puede quedar en más de un *chunk*, y entonces
    ni siquiera un `Series` sin nulos admite una vista sin copia -- exigir
    `allow_copy=False` aquí rompería sobre datos reales sin motivo: la copia
    la hace Polars de una vez, vectorizada, no esta función fila a fila.

    La lista devuelta respeta el orden de `cabecera.canales`, aunque
    `detectar_grupos_de_muestreo` (F1-06) no lo garantice internamente: agrupa
    por patrón, no por columna, así que el orden de salida de esa función
    depende de cómo `numpy.unique` ordene los patrones, no de en qué orden se
    le pasaron las columnas.
    """
    marca = df[columna_tiempo]
    segundos_del_dia = marca.str.strptime(pl.Time, "%H:%M:%S%.f").cast(pl.Int64).to_numpy() / 1e9
    desenrollado = desenrollar_medianoche(segundos_del_dia)
    t_ms_absoluto = desenrollado.t * 1000.0
    t0 = float(t_ms_absoluto[0]) if t_ms_absoluto.size else 0.0
    t_relativo = (t_ms_absoluto - t0).astype(np.uint32)

    columnas_por_canal = {columna_polars(c.columna): c for c in cabecera.canales}
    columnas_presentes = [c for c in columnas_por_canal if c in df.columns]
    grupos = detectar_grupos_de_muestreo(df, columnas_presentes)

    por_columna: dict[str, ChannelSeries] = {}
    for mascara, columnas in grupos:
        t_grupo = t_relativo[mascara]
        mascara_pl = pl.Series(mascara)
        for columna in columnas:
            canal = columnas_por_canal[columna]
            valores = df[columna].filter(mascara_pl).to_numpy()
            key = ChannelKey(
                rol=None,
                formato=cabecera.formato,
                id_nativo=str(canal.id),
                nombre_normalizado=None,
            )
            por_columna[columna] = ChannelSeries(
                key=key,
                role=None,
                t=t_grupo,
                v=valores,
                storage=storage_por_columna[columna],
                to_canon=Afin(canal.a_canonica),
                dimension=canal.dimension,
            )

    # `detectar_grupos_de_muestreo` no promete el orden de entrada (agrupa por
    # patrón, no por columna): se reordena aquí para que la salida sea
    # predecible, en el mismo orden que `cabecera.canales`.
    return [por_columna[c] for c in columnas_presentes]


#: p1/p5/p50/p95/p99: par simétrico de colas (1/99, 5/95) más la mediana. No
#: son "los percentiles que trae `numpy` por omisión" (no hay tal cosa): se
#: eligen para que un panel pueda mostrar de un vistazo "el rango típico"
#: (p5-p95, que ignora los picos puntuales que sí se ven en mín/máx) y "hasta
#: dónde llega la cola" (p1/p99) sin tener que dibujar el histograma completo.
#: p50 (mediana) se añade porque para un canal con distribución muy asimétrica
#: (p. ej. un sensor que pasa la mayor parte del tiempo en un valor de reposo)
#: la media aritmética -- que este módulo no calcula -- engañaría más que
#: informaría; la mediana no.
PERCENTILES_POR_OMISION: tuple[float, ...] = (1.0, 5.0, 50.0, 95.0, 99.0)


@dataclass(slots=True, frozen=True)
class IndiceCanal:
    """Estadísticas de un canal para vista rápida (§3.4 paso 5, F1-07).

    Ver el docstring del módulo para por qué esto reemplaza al `np.ndarray`
    del stub original de `indexar`.

    La clasificación NO es excluyente por diseño: `constante` y
    `fuera_de_rango` pueden ser ambas verdaderas a la vez (un canal atascado
    en un valor que además está fuera de su rango de display es información
    real, y sería peor perderla forzando "una sola etiqueta gana"). Por eso
    cada categoría es su propio booleano en vez de un único campo tipo enum;
    `activo` es la única que se define como "ninguna de las otras tres", así
    que se calcula sola (propiedad) en vez de guardarse, para que nunca pueda
    quedar desincronizada de las demás.
    """

    minimo: float | None
    """`None` solo cuando `vacio` (no hay valor que devolver)."""

    maximo: float | None
    """`None` solo cuando `vacio`."""

    percentiles: Mapping[float, float]
    """Percentil -> valor, en las unidades crudas de `serie.v` (sin pasar por
    `to_canon`: ver la nota de `fuera_de_rango` sobre por qué este módulo
    trabaja en crudo). Diccionario vacío cuando `vacio`."""

    vacio: bool
    """`len(serie.v) == 0`: el canal nunca se activó en este log/segmento.
    Ocurre de verdad -- no es un caso hipotético -- porque un log puede
    incluir canales de un módulo que no estaba presente en esa tirada."""

    constante: bool
    """Todas las muestras comparten el mismo valor (`v.min() == v.max()`), y
    la serie no está vacía. Un canal vacío no es "constante": no hay ningún
    valor que se esté repitiendo, así que forzar `constante=True` cuando
    `vacio=True` sería una afirmación sin contenido."""

    fuera_de_rango: bool
    """Alguna muestra cae fuera de `[display_min, display_max]` del canal
    (`dlv_core.formatos.haltech.Canal`). Ver `indexar` para cómo se pasan esos
    límites y qué pasa cuando faltan (13 de 475 canales del AutoLog real no
    los traen, docs/01 §1.3): en ese caso esta categoría es simplemente
    `False`, no "desconocido" -- no hay rango declarado que violar."""

    @property
    def activo(self) -> bool:
        """Ni vacío, ni constante, ni fuera de rango: tiene datos, varían, y
        (si había límites que comprobar) están dentro de ellos.

        Se calcula, no se guarda, para que no pueda contradecir a los otros
        tres campos por un descuido de quien construye `IndiceCanal` a mano
        (p. ej. en un test).
        """
        return not (self.vacio or self.constante or self.fuera_de_rango)


def indexar(
    serie: ChannelSeries,
    *,
    display_min: float | None = None,
    display_max: float | None = None,
    percentiles: Sequence[float] = PERCENTILES_POR_OMISION,
) -> IndiceCanal:
    """Mín/máx/percentiles y clasificación activo/constante/vacío/fuera de
    rango (§3.4 paso 5) sobre `serie.v` completo, sin bucle por muestra.

    `display_min`/`display_max` son opcionales y en las unidades CRUDAS de
    `serie.v` (no canónicas): `docs/01-formato-log.md` §1.3 confirma que
    `DisplayMaxMin` se define en la escala nativa del canal antes de aplicar
    `a_canonica` (p. ej. `Angle` declara `DisplayMaxMin 600,...` para un rango
    real de 60°, con factor ÷10) -- así que comparar directamente contra
    `serie.v` sin pasar por `serie.to_canon` es lo correcto, no un atajo: pasar
    ambos por `to_canon` primero daría el mismo resultado para una conversión
    afín monótona creciente, pero obligaría a decidir aquí la `Clase`
    (`dlv_core.unidades.Clase`) de un límite que es un punto, no un intervalo,
    para ninguna ganancia real.

    Se reciben como dos flotantes sueltos y no como el `Canal` completo de
    `dlv_core.formatos.haltech` a propósito: `ChannelSeries` (F1-05) ya es
    agnóstica de qué formato la produjo -- solo `construir_desde_polars` conoce
    `Canal` -- y atar la firma de `indexar` a un tipo específico de un formato
    concreto rompería esa frontera para el día en que exista un segundo
    formato con su propio tipo de canal. Quien llama (que sí tiene el `Canal`
    a mano, típicamente el mismo código que llamó a `construir_desde_polars`)
    extrae `canal.display_min`/`canal.display_max` y los pasa aquí. Ambos
    `None` (el valor por omisión) es exactamente el caso real de los 13
    canales del AutoLog sin `DisplayMaxMin`: entonces `fuera_de_rango` es
    siempre `False`, porque no hay límite que se pueda violar.

    Vectorizado (ADR-009): `v.min()`/`v.max()`/comparaciones son reducciones
    de NumPy sobre el array completo, no un bucle por muestra; los
    percentiles se calculan de una vez con `numpy.percentile` sobre `serie.v`
    completo.
    """
    v = serie.v
    if v.size == 0:
        # Vacío: no hay mínimo, máximo ni percentil que calcular, y ninguna de
        # las otras categorías tiene sentido sobre cero muestras (ver el
        # docstring de `IndiceCanal.constante`).
        return IndiceCanal(
            minimo=None,
            maximo=None,
            percentiles={},
            vacio=True,
            constante=False,
            fuera_de_rango=False,
        )

    minimo = float(v.min())
    maximo = float(v.max())
    constante = minimo == maximo

    fuera_de_rango = (display_min is not None and minimo < display_min) or (
        display_max is not None and maximo > display_max
    )

    valores_percentil = np.percentile(v, list(percentiles)) if percentiles else np.array([])
    tabla_percentiles = {
        float(p): float(x) for p, x in zip(percentiles, valores_percentil, strict=True)
    }

    return IndiceCanal(
        minimo=minimo,
        maximo=maximo,
        percentiles=tabla_percentiles,
        vacio=False,
        constante=constante,
        fuera_de_rango=fuera_de_rango,
    )
