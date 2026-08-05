"""Modelo de segmento (tramos) y eje X virtual (tarea F2-01).

QUÉ AGUJERO TAPA
================
`dlv-ui/src/render/renderizador.ts` lo dice en su propia cabecera, apartado
«FUERA DE ALCANCE DE F1-23, A PROPÓSITO»:

    «Una serie se dibuja como un único `LINE_STRIP` continuo. Un log con
    hueco de adquisición (F1-08) o varios segmentos se dibujaría con una
    recta atravesando el hueco, que es una lectura falsa.»

Una recta que atraviesa un hueco de 40 minutos no es un defecto cosmético:
es un dato que no existe, dibujado con la misma tinta que los que sí. Y no
hay nada en pantalla que lo delate. Este módulo produce las dos cosas que
hacen falta para que eso no pueda pasar:

1. **Tramos** (`partir_en_tramos`): la lista de rebanadas `[inicio, fin)` de
   `t`/`v` que SÍ son continuas. El renderizador sube y dibuja un
   `LINE_STRIP` por tramo, así que no existe ningún vértice que cruce un
   hueco: la recta falsa no se evita pintándola de otro color, se evita
   porque no se genera.
2. **Eje X virtual** (`EjeVirtual`): la correspondencia monótona entre el
   tiempo real (ms) y la coordenada continua con la que se dibuja, más su
   inversa exacta para volver del píxel al instante real (cursor y doble
   cursor, presupuesto de §2.6: < 16 ms).

LAS TRES RESPUESTAS DE DISEÑO
=============================
**Por qué la coordenada virtual está en ms y no normalizada a [0, 1].** El
eje es afín a trozos y **dentro de un tramo su pendiente es exactamente 1**:
un segundo de datos mide lo mismo en el tramo primero que en el último. Solo
los huecos cambian de escala. Así una pendiente leída en pantalla (dλ/dt, la
rampa de un sensor) sigue siendo la pendiente real, que es justo lo que se
perdería si cada tramo se estirara para ocupar su parte de la pantalla.
Normalizar es asunto de quien dibuja: `x_total` está publicado para eso.

**Por qué el hueco se comprime y no se elimina.** `PoliticaHueco` da tres
comportamientos (`REAL`, `TOPE`, `FIJO`), pero ninguno puede producir un
hueco de anchura cero: `construir_eje_virtual` rechaza un tope o una anchura
que no sea > 0. Un hueco de anchura cero volvería a poner en contacto los dos
extremos y devolvería exactamente la lectura falsa que este módulo existe
para impedir, esta vez sin ni siquiera la excusa de una recta larga que
alguien pudiera notar. Comprimir un hueco de 40 min a 2 s es una decisión de
presentación legítima; hacerlo desaparecer es falsificar.

**Por qué la cobertura se funde y los tramos no.** Dos segmentos que se
solapan en el tiempo (la vista paralela de §3.6 es exactamente eso: N logs
sobre el mismo eje) no pueden dar un eje monótono si cada uno reclama su
propio trozo de coordenada. El eje se construye sobre la UNIÓN de los
intervalos ocupados --- que sí es una partición de la recta real --- mientras
que los tramos se conservan intactos y por separado para dibujar. Dicho de
otra forma: fundir intervalos cambia dónde cae la tinta, nunca si dos
muestras se unen con una recta. Eso último lo decide la lista de tramos, y
ahí no se funde nada, ni siquiera entre dos logs que se tocan
(`MotivoRuptura.FRONTERA_SEGMENTO`, regla dura de §3.6: «nunca se dibuja una
línea que cruce una frontera de segmento»).

ADR-009
=======
El corte en tramos delega el trabajo por muestra en `huecos.py` (F1-08), que
es `astype` -> `diff` -> comparación -> `flatnonzero` sobre el array
completo; aquí solo se recorren los cortes ENCONTRADOS, que son unos pocos.
La construcción del eje trabaja sobre un array con dos entradas por tramo
(`argsort`, `maximum.accumulate`, `maximum.reduceat`, `cumsum`), no por
muestra, y la conversión `t <-> x` de una serie entera es un único
`numpy.interp` sobre el array completo.

Un detalle heredado de F1-05 que este módulo también respeta: `t` puede ser
`uint32`, así que se castea a `int64` antes de restar nada. Un retroceso
restado sin signo no da negativo, envuelve a un entero enorme.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np

from dlv_core.huecos import (
    FACTOR_UMBRAL_HUECO_POR_OMISION,
    detectar_discontinuidades,
    detectar_huecos,
)

if TYPE_CHECKING:
    from dlv_core.almacen import ChannelSeries

__all__ = [
    "EjeVirtual",
    "HuecoVirtual",
    "MotivoRuptura",
    "PoliticaHueco",
    "PosicionEje",
    "Ruptura",
    "Tramo",
    "Zona",
    "construir_eje_virtual",
    "desplazar_tramos",
    "partir_en_tramos",
    "partir_serie_en_tramos",
    "rupturas_entre",
]


class MotivoRuptura(Enum):
    """Por qué dos tramos consecutivos no se pueden unir con una línea."""

    HUECO = auto()
    """El log dejó de grabar: `Δt` anormalmente grande frente al periodo
    típico del canal (F1-08, `detectar_huecos`, D18)."""

    RETROCESO = auto()
    """El eje temporal va hacia atrás (F1-08, `detectar_discontinuidades`).
    No es un hueco: es un tramo de eje que no es fiable, y no se corrige
    (inventar cuál de las dos marcas es la buena no es de este módulo)."""

    FRONTERA_SEGMENTO = auto()
    """Los dos tramos vienen de logs distintos. Se marca aunque el segundo
    empiece justo donde acaba el primero: §3.6 pide que las fronteras se
    marquen «siempre, no como opción», precisamente porque el caso peligroso
    es el que no se ve (2768 + 2769 concatenados, hito M2)."""


class PoliticaHueco(Enum):
    """Cuánta coordenada virtual se le da a un hueco.

    Ninguna de las tres puede producir anchura cero: ver el docstring del
    módulo y la validación de `construir_eje_virtual`.
    """

    REAL = auto()
    """El hueco ocupa su duración real: el eje virtual es la identidad
    (`x = t - t_min`). Es el valor por omisión porque es el único que no
    deforma nada; cualquier compresión es una decisión del usuario, no algo
    que este módulo deba aplicar por su cuenta."""

    TOPE = auto()
    """`min(duración real, tope_hueco_ms)`: los huecos pequeños se ven tal
    cual y solo los grandes se recortan. Es la política que responde al «un
    hueco de 40 minutos no ocupa el 90 % de la pantalla» sin cambiar de
    escala los huecos que sí caben."""

    FIJO = auto()
    """Todos los huecos miden `ancho_hueco_ms`, independientemente de su
    duración. Útil para comparar tramos cuando el tiempo muerto entre ellos
    no interesa en absoluto; a cambio, dos huecos de 1 s y de 1 h se ven
    iguales, así que la duración real hay que leerla en `HuecoVirtual`."""


class Zona(Enum):
    """Qué hay bajo una coordenada del eje virtual (`EjeVirtual.posicion`)."""

    TRAMO = auto()
    """Dentro de un intervalo con datos: el instante devuelto es real y hay
    muestras que buscar en él."""

    HUECO = auto()
    """Entre dos intervalos con datos. El instante devuelto sigue siendo un
    instante real --- el eje es invertible también aquí --- pero NO hay
    ninguna muestra en él, y un cursor que muestre un valor ahí estará
    mostrando una interpolación inventada."""

    FUERA = auto()
    """Antes del primer dato o después del último. El instante se extrapola
    con pendiente 1 (ver `EjeVirtual.a_t`)."""


@dataclass(slots=True, frozen=True)
class Tramo:
    """Una rebanada continua de una serie: `t[inicio:fin]`, sin ningún corte
    dentro.

    Es la unidad de dibujo: un `LINE_STRIP` por tramo. Dos convenios que se
    confunden con facilidad y que por eso llevan nombres distintos:

    - `inicio`/`fin` son ÍNDICES de muestra con semántica de rebanada de
      Python (`fin` excluyente): `t[tramo.inicio:tramo.fin]`.
    - `t_inicio`/`t_fin` son INSTANTES en ms, ambos inclusivos:
      `t_fin == t[fin - 1]`, no `t[fin]`.
    """

    id_segmento: str
    """`Segmento.id` (`dlv_core.tiempo`, §3.6) del log del que sale este
    tramo. Cadena vacía cuando se trabaja con un solo log y no hace falta
    distinguir. Es lo que hace que `rupturas_entre` pueda marcar una frontera
    de segmento aunque dos logs se toquen en el tiempo."""

    orden: int
    """Posición del tramo dentro de su segmento, empezando en 0."""

    inicio: int
    fin: int
    """Índice EXCLUYENTE: la rebanada es `t[inicio:fin]`."""

    t_inicio: int
    t_fin: int
    """Instante de la ÚLTIMA muestra del tramo (inclusivo), no el de la
    primera del siguiente."""

    def __post_init__(self) -> None:
        if self.fin <= self.inicio:
            raise ValueError(
                f"un tramo tiene al menos una muestra: inicio={self.inicio}, fin={self.fin}"
            )
        if self.t_fin < self.t_inicio:
            raise ValueError(
                "un tramo no puede retroceder en el tiempo (eso es una ruptura, no un "
                f"tramo): t_inicio={self.t_inicio}, t_fin={self.t_fin}"
            )

    @property
    def n_muestras(self) -> int:
        return self.fin - self.inicio

    @property
    def duracion_ms(self) -> int:
        return self.t_fin - self.t_inicio

    @property
    def es_punto(self) -> bool:
        """Una sola muestra: `LINE_STRIP` con un vértice no dibuja NADA.

        No es un caso de laboratorio: pasa siempre que un hueco cae entre las
        dos primeras (o las dos últimas) muestras de la serie. Quien dibuje
        tiene que tratarlo aparte --- un punto, no una línea --- o esa muestra
        desaparece de la pantalla sin dejar rastro, que es el mismo defecto de
        «datos invisibles» por el otro extremo.
        """
        return self.n_muestras == 1


@dataclass(slots=True, frozen=True)
class Ruptura:
    """La razón por la que dos tramos consecutivos no se cosen."""

    motivo: MotivoRuptura
    anterior: int
    """Índice, en la lista de tramos que se pasó, del tramo que queda antes."""

    siguiente: int
    t_fin_anterior: int
    t_inicio_siguiente: int
    duracion_ms: int
    """`t_inicio_siguiente - t_fin_anterior`. Negativo si `RETROCESO`; puede
    ser 0 en una `FRONTERA_SEGMENTO` donde un log empieza justo donde acaba
    el anterior."""


@dataclass(slots=True, frozen=True)
class HuecoVirtual:
    """Un hueco tal y como queda en el eje virtual: dónde está en pantalla y
    cuánto tiempo real se ha comprimido ahí dentro.

    Es lo que necesita la capa de dibujo para marcarlo (una banda, un zigzag,
    lo que decida F2-09), y lo que necesita un panel para poder escribir «40
    min sin datos» debajo de una banda de 2 s de ancho.
    """

    t_inicio: int
    t_fin: int
    x_inicio: float
    x_fin: float

    @property
    def duracion_ms(self) -> int:
        """Tiempo real sin datos. Siempre > 0."""
        return self.t_fin - self.t_inicio

    @property
    def ancho_x(self) -> float:
        """Anchura en coordenada virtual. **Siempre > 0**, en las tres
        políticas: es la invariante que impide que un hueco quede
        invisible."""
        return self.x_fin - self.x_inicio

    @property
    def comprimido(self) -> bool:
        return self.ancho_x < float(self.duracion_ms)


@dataclass(slots=True, frozen=True)
class PosicionEje:
    """Resultado de volver de una coordenada virtual al tiempo real.

    `zona` no es un adorno: sin ella, `t` por sí solo no distingue «estás
    sobre el instante 12:04:31, que tiene datos» de «estás sobre el instante
    12:04:31, que está en mitad de un hueco de 40 minutos». El cursor que no
    mira `zona` acaba enseñando el valor de la muestra más cercana como si
    fuera el valor en ese instante.
    """

    x: float
    t: float
    zona: Zona
    indice_cobertura: int | None
    """Índice del intervalo de cobertura (`Zona.TRAMO`) o del hueco
    (`Zona.HUECO`) sobre el que cae `x`; `None` si `Zona.FUERA`.

    Es un índice de COBERTURA, no de tramo, y la diferencia importa: en la
    vista paralela varios tramos de logs distintos pueden cubrir el mismo
    instante, así que «qué tramo hay bajo el cursor» no es una pregunta con
    una sola respuesta. Para eso está `EjeVirtual.tramos_en`.
    """


def partir_en_tramos(
    t: np.ndarray,
    *,
    id_segmento: str = "",
    factor_umbral: float = FACTOR_UMBRAL_HUECO_POR_OMISION,
    periodo_ms: float | None = None,
) -> list[Tramo]:
    """Parte `t` en tramos continuos, cortando en huecos y en retrocesos.

    Los dos criterios de corte son literalmente los de F1-08 (`huecos.py`):
    esta función no reimplementa ni el umbral ni la estimación del periodo
    típico, los llama. Es deliberado --- docs/01 §1.7 y el detector D18
    comparten un único número (`3x` la mediana), y dos implementaciones del
    mismo criterio se desincronizan --- y además significa que
    `factor_umbral`/`periodo_ms` siguen siendo configurables aquí con la
    misma semántica de allí.

    Un corte en el índice `i` (entre `t[i]` y `t[i+1]`) cierra un tramo en
    `fin = i + 1` y abre el siguiente en `inicio = i + 1`: ninguna muestra se
    pierde ni se repite, y la suma de `n_muestras` de todos los tramos es
    siempre `len(t)`. Eso incluye los dos casos que se equivocan en silencio:
    un hueco entre las dos PRIMERAS muestras deja un primer tramo de una sola
    muestra (no lo descarta), y uno entre las dos ÚLTIMAS deja un último
    tramo de una sola muestra (no lo pierde). Ver `Tramo.es_punto` para qué
    hacer con ellos al dibujar.

    Devuelve una lista vacía solo si `t` está vacío. Sin periodo utilizable
    (una única muestra, o un eje sin ningún `Δt` positivo) no hay huecos que
    afirmar --- criterio de `detectar_huecos` --- pero los retrocesos sí se
    cortan igual, porque no dependen de ningún umbral.
    """
    if t.size == 0:
        return []

    t64 = t.astype(np.int64)
    cortes = sorted(
        {h.indice for h in detectar_huecos(t64, factor_umbral=factor_umbral, periodo_ms=periodo_ms)}
        | {d.indice for d in detectar_discontinuidades(t64)}
    )
    limites = [0, *(c + 1 for c in cortes), int(t64.size)]

    return [
        Tramo(
            id_segmento=id_segmento,
            orden=orden,
            inicio=inicio,
            fin=fin,
            t_inicio=int(t64[inicio]),
            t_fin=int(t64[fin - 1]),
        )
        for orden, (inicio, fin) in enumerate(zip(limites[:-1], limites[1:], strict=True))
    ]


def partir_serie_en_tramos(
    serie: ChannelSeries,
    *,
    id_segmento: str = "",
    factor_umbral: float = FACTOR_UMBRAL_HUECO_POR_OMISION,
    periodo_ms: float | None = None,
) -> list[Tramo]:
    """Azúcar sobre `partir_en_tramos(serie.t, ...)`, igual que las funciones
    `_de_serie` de `huecos.py`.

    Los índices `inicio`/`fin` de los tramos valen tal cual para `serie.v`:
    `t` y `v` de una `ChannelSeries` tienen la misma longitud por
    construcción (F1-05).
    """
    return partir_en_tramos(
        serie.t, id_segmento=id_segmento, factor_umbral=factor_umbral, periodo_ms=periodo_ms
    )


def rupturas_entre(tramos: list[Tramo]) -> list[Ruptura]:
    """Clasifica lo que separa cada par de tramos consecutivos de la lista.

    Clasifica por lo que se puede ver en los propios tramos --- identidad de
    segmento y orden temporal --- sin volver a mirar los datos ni a aplicar
    ningún umbral: el umbral ya decidió dónde cortar en `partir_en_tramos`.

    El orden de la lista es el que se pasa (típicamente el de
    `partir_en_tramos`, o el de varios segmentos concatenados). Una frontera
    de segmento gana a las demás clasificaciones aunque los dos logs se
    toquen o se solapen en el tiempo: que dos logs distintos compartan
    instante no autoriza a unirlos con una línea.
    """
    rupturas: list[Ruptura] = []
    for i, (anterior, siguiente) in enumerate(zip(tramos[:-1], tramos[1:], strict=True)):
        if anterior.id_segmento != siguiente.id_segmento:
            motivo = MotivoRuptura.FRONTERA_SEGMENTO
        elif siguiente.t_inicio < anterior.t_fin:
            motivo = MotivoRuptura.RETROCESO
        else:
            motivo = MotivoRuptura.HUECO
        rupturas.append(
            Ruptura(
                motivo=motivo,
                anterior=i,
                siguiente=i + 1,
                t_fin_anterior=anterior.t_fin,
                t_inicio_siguiente=siguiente.t_inicio,
                duracion_ms=siguiente.t_inicio - anterior.t_fin,
            )
        )
    return rupturas


def desplazar_tramos(tramos: list[Tramo], desfase_ms: int) -> list[Tramo]:
    """Mueve los tramos de un segmento en el tiempo, sin tocar sus índices.

    Es la pieza que hace componible la vista paralela (§3.6, `x = t_local +
    offset_efectivo`) sin que este módulo tenga que saber de dónde sale el
    desfase: quien lo calcula es `dlv_core.tiempo.desfase_efectivo` (F2-05) o
    la correlación cruzada (F2-08). Aquí solo se aplica.

    Los índices de muestra no cambian porque el desfase no reordena nada
    dentro del segmento: la rebanada `t[inicio:fin]` sigue siendo la misma,
    solo se dibuja en otro sitio.
    """
    return [
        Tramo(
            id_segmento=tr.id_segmento,
            orden=tr.orden,
            inicio=tr.inicio,
            fin=tr.fin,
            t_inicio=tr.t_inicio + desfase_ms,
            t_fin=tr.t_fin + desfase_ms,
        )
        for tr in tramos
    ]


@dataclass(slots=True, frozen=True, eq=False)
class EjeVirtual:
    """La correspondencia afín a trozos entre el tiempo real (ms) y la
    coordenada de dibujo, con su inversa.

    `x` está en las mismas unidades que `t` (ms) y empieza en 0 en el primer
    instante con datos. Dentro de un intervalo con datos la pendiente es
    exactamente 1; solo los huecos cambian de escala (ver el docstring del
    módulo).

    `eq=False` a propósito: los campos son arrays de NumPy y el `__eq__`
    generado por `dataclass` los compararía elemento a elemento, devolviendo
    un array donde quien escribe `a == b` espera un booleano. Comparar dos
    ejes no es una operación que haga falta; que reviente con un
    `ValueError: truth value of an array...` a mitad de una prueba, sí
    estorba.
    """

    politica: PoliticaHueco
    tramos: tuple[Tramo, ...]
    """Los tramos que se pasaron, ORDENADOS por `t_inicio`. Es la lista de
    dibujo: un `LINE_STRIP` por elemento, nunca uno solo para todos."""

    huecos: tuple[HuecoVirtual, ...]
    """Los huecos del eje, de izquierda a derecha. Ninguno tiene anchura
    cero."""

    t_cobertura_inicio: np.ndarray  # int64
    t_cobertura_fin: np.ndarray  # int64
    x_cobertura_inicio: np.ndarray  # float64
    x_cobertura_fin: np.ndarray  # float64
    """Intervalos ocupados (la UNIÓN de los intervalos de los tramos: dos
    tramos que se solapan dan una sola entrada) y su imagen en `x`."""

    t_nodos: np.ndarray  # float64
    x_nodos: np.ndarray  # float64
    """Los mismos intervalos intercalados como nodos de interpolación
    (`[t_ini0, t_fin0, t_ini1, ...]`), que es la forma que consume
    `numpy.interp` sin tener que reconstruirla en cada llamada."""

    @property
    def t_minimo(self) -> int:
        return int(self.t_cobertura_inicio[0])

    @property
    def t_maximo(self) -> int:
        return int(self.t_cobertura_fin[-1])

    @property
    def x_total(self) -> float:
        """Anchura total del eje en coordenada virtual.

        Puede ser 0 si toda la cobertura es un único instante (un solo tramo
        de una muestra): quien vaya a escalar por `x_total` tiene que decidir
        qué hacer con ese caso, porque «un punto» no tiene anchura que
        repartir en la pantalla y no hay valor que este módulo pueda inventar
        que no sea una mentira.
        """
        return float(self.x_cobertura_fin[-1])

    def a_x(self, t: np.ndarray) -> np.ndarray:
        """Tiempo real (ms) -> coordenada virtual, sobre el array completo.

        Un único `numpy.interp` (ADR-009): esto se llama con el `t` de una
        serie entera o con los instantes de un nivel de la pirámide, no
        muestra a muestra.

        Fuera de la cobertura extrapola con pendiente 1 en vez de aplastar
        contra el extremo, que es lo que hace `numpy.interp` por omisión:
        aplastar amontonaría todas las muestras anteriores al primer dato
        sobre un mismo píxel --- una barra vertical que parece un dato --- y
        además rompería la ida y vuelta con `a_t`.
        """
        t64 = np.asarray(t, dtype=np.float64)
        x = np.asarray(np.interp(t64, self.t_nodos, self.x_nodos), dtype=np.float64)
        t_ini, t_fin = self.t_nodos[0], self.t_nodos[-1]
        x_ini, x_fin = self.x_nodos[0], self.x_nodos[-1]
        x = np.where(t64 < t_ini, x_ini + (t64 - t_ini), x)
        return np.asarray(np.where(t64 > t_fin, x_fin + (t64 - t_fin), x), dtype=np.float64)

    def a_t(self, x: np.ndarray) -> np.ndarray:
        """Coordenada virtual -> tiempo real (ms). Inversa exacta de `a_x`.

        Exacta en los nodos, que es donde importa: los bordes de un hueco son
        los dos instantes que lo delimitan y un cursor pegado al borde
        izquierdo tiene que dar el último instante con datos, no un valor
        redondeado hacia dentro del hueco.
        """
        x64 = np.asarray(x, dtype=np.float64)
        t = np.asarray(np.interp(x64, self.x_nodos, self.t_nodos), dtype=np.float64)
        t_ini, t_fin = self.t_nodos[0], self.t_nodos[-1]
        x_ini, x_fin = self.x_nodos[0], self.x_nodos[-1]
        t = np.where(x64 < x_ini, t_ini + (x64 - x_ini), t)
        return np.asarray(np.where(x64 > x_fin, t_fin + (x64 - x_fin), t), dtype=np.float64)

    def x_de_instante(self, t: float) -> float:
        """`a_x` para un único instante (ejes, marcas, un evento suelto)."""
        return float(self.a_x(np.array([t], dtype=np.float64))[0])

    def instante_de_x(self, x: float) -> float:
        """`a_t` para una única coordenada. Ver también `posicion`, que
        además dice si ahí hay datos o no."""
        return float(self.a_t(np.array([x], dtype=np.float64))[0])

    def posicion(self, x: float) -> PosicionEje:
        """De la coordenada virtual (típicamente, de un píxel) al instante
        real Y a qué hay ahí: datos, hueco o nada.

        Esto es lo que consumen el cursor y el doble cursor. La distinción
        entre `TRAMO` y `HUECO` es la que evita que el cursor enseñe el valor
        de la última muestra antes del hueco como si fuera el valor 40
        minutos después.
        """
        t = self.instante_de_x(x)
        if x < float(self.x_cobertura_inicio[0]) or x > float(self.x_cobertura_fin[-1]):
            return PosicionEje(x=x, t=t, zona=Zona.FUERA, indice_cobertura=None)

        i = int(np.searchsorted(self.x_cobertura_fin, x, side="left"))
        if x >= float(self.x_cobertura_inicio[i]):
            return PosicionEje(x=x, t=t, zona=Zona.TRAMO, indice_cobertura=i)
        # Entre el final de la cobertura i-1 y el principio de la i: el hueco
        # i-1, porque hay exactamente un hueco entre cada par de coberturas.
        return PosicionEje(x=x, t=t, zona=Zona.HUECO, indice_cobertura=i - 1)

    def tramos_en(self, t: float) -> list[int]:
        """Índices de los tramos (en `self.tramos`) que contienen el instante
        `t`, extremos incluidos.

        Devuelve una LISTA y no un índice porque en la vista paralela varios
        logs cubren el mismo instante a la vez, y ese es el caso de uso
        entero de la vista paralela. Vacía si `t` cae en un hueco.
        """
        return [i for i, tr in enumerate(self.tramos) if tr.t_inicio <= t <= tr.t_fin]

    def rango_x(self, tramo: Tramo) -> tuple[float, float]:
        """Dónde cae un tramo en la coordenada virtual. Lo que el
        renderizador necesita para subir ese tramo como un `LINE_STRIP` con
        su propio origen (`CubosContinuos.tOrigen` de `dlv-ui`)."""
        return (self.x_de_instante(tramo.t_inicio), self.x_de_instante(tramo.t_fin))


def _anchos_virtuales(
    huecos_reales: np.ndarray,
    *,
    politica: PoliticaHueco,
    ancho_hueco_ms: float | None,
    tope_hueco_ms: float | None,
) -> np.ndarray:
    """Anchura en `x` de cada hueco, según la política. Siempre > 0.

    Ni `ancho_hueco_ms` ni `tope_hueco_ms` tienen valor por omisión: no
    existe un número universalmente correcto de «cuánto debe medir un hueco
    en pantalla» --- depende del ancho del lienzo, del zoom y de para qué se
    esté mirando el log --- y ponerle uno aquí sería cablear una opinión de
    presentación en la biblioteca de datos. Quien elige comprimir, elige
    cuánto.
    """
    if politica is PoliticaHueco.REAL:
        return huecos_reales.astype(np.float64)
    if politica is PoliticaHueco.TOPE:
        if tope_hueco_ms is None or not tope_hueco_ms > 0.0:
            raise ValueError(
                "PoliticaHueco.TOPE exige tope_hueco_ms > 0: un tope de 0 pegaría los "
                "dos bordes del hueco y devolvería la lectura falsa que el eje virtual "
                f"existe para impedir (se dio {tope_hueco_ms})"
            )
        return np.minimum(huecos_reales.astype(np.float64), float(tope_hueco_ms))
    if politica is PoliticaHueco.FIJO:
        if ancho_hueco_ms is None or not ancho_hueco_ms > 0.0:
            raise ValueError(
                "PoliticaHueco.FIJO exige ancho_hueco_ms > 0: una anchura de 0 haría "
                f"invisible el hueco (se dio {ancho_hueco_ms})"
            )
        return np.full(huecos_reales.shape, float(ancho_hueco_ms), dtype=np.float64)
    raise AssertionError(f"PoliticaHueco no cubierta: {politica!r}")  # exhaustivo


def construir_eje_virtual(
    tramos: list[Tramo],
    *,
    politica: PoliticaHueco = PoliticaHueco.REAL,
    ancho_hueco_ms: float | None = None,
    tope_hueco_ms: float | None = None,
) -> EjeVirtual:
    """Construye el eje virtual que cubre todos los tramos dados.

    Los tramos pueden venir de varios segmentos y pueden solaparse en el
    tiempo (vista paralela de §3.6): el eje se construye sobre la unión de
    los intervalos ocupados, que siempre es una sucesión de intervalos
    disjuntos y ordenados, así que la correspondencia `t -> x` es monótona
    creciente y por tanto invertible sea cual sea la disposición de los
    tramos. Dos intervalos que se tocan (`t_fin == t_inicio`) se funden: no
    hay tiempo muerto entre ellos, luego no hay hueco que enseñar --- lo que
    NO significa que se puedan dibujar unidos, eso lo decide la lista de
    tramos, que no se funde nunca.

    Vectorizado sobre un array de dos entradas por tramo (`argsort`,
    `maximum.accumulate`, `maximum.reduceat`, `cumsum`): son unos pocos
    tramos, pero el coste tampoco crece con las muestras.

    Lanza `ValueError` sin tramos: una vista sin datos no necesita un eje, y
    devolver uno vacío obligaría a que todos los consumidores comprobasen un
    caso degenerado que en realidad nunca se dibuja.
    """
    if not tramos:
        raise ValueError("no se puede construir un eje virtual sin ningún tramo")

    t_ini = np.array([tr.t_inicio for tr in tramos], dtype=np.int64)
    t_fin = np.array([tr.t_fin for tr in tramos], dtype=np.int64)

    orden = np.argsort(t_ini, kind="stable")
    ini, fin = t_ini[orden], t_fin[orden]

    # Unión de intervalos: un intervalo nuevo empieza donde su inicio está
    # estrictamente por encima del mayor final visto hasta ese momento. Con
    # `>` (y no `>=`) dos intervalos que se tocan se funden, que es lo
    # correcto: entre ellos no hay ni un milisegundo sin datos.
    tope_previo = np.maximum.accumulate(fin)
    comienza = np.ones(ini.size, dtype=np.bool_)
    comienza[1:] = ini[1:] > tope_previo[:-1]
    arranques = np.flatnonzero(comienza)
    u_ini = ini[arranques]
    u_fin = np.asarray(np.maximum.reduceat(fin, arranques), dtype=np.int64)

    huecos_reales = u_ini[1:] - u_fin[:-1]
    anchos = _anchos_virtuales(
        huecos_reales,
        politica=politica,
        ancho_hueco_ms=ancho_hueco_ms,
        tope_hueco_ms=tope_hueco_ms,
    )

    duraciones = (u_fin - u_ini).astype(np.float64)
    x_ini = np.zeros(u_ini.size, dtype=np.float64)
    x_ini[1:] = np.cumsum(duraciones[:-1] + anchos)
    x_fin = x_ini + duraciones

    t_nodos = np.empty(u_ini.size * 2, dtype=np.float64)
    t_nodos[0::2] = u_ini
    t_nodos[1::2] = u_fin
    x_nodos = np.empty(u_ini.size * 2, dtype=np.float64)
    x_nodos[0::2] = x_ini
    x_nodos[1::2] = x_fin

    huecos = tuple(
        HuecoVirtual(
            t_inicio=int(u_fin[i]),
            t_fin=int(u_ini[i + 1]),
            x_inicio=float(x_fin[i]),
            x_fin=float(x_ini[i + 1]),
        )
        for i in range(u_ini.size - 1)
    )

    return EjeVirtual(
        politica=politica,
        tramos=tuple(tramos[int(i)] for i in orden.tolist()),
        huecos=huecos,
        t_cobertura_inicio=u_ini,
        t_cobertura_fin=u_fin,
        x_cobertura_inicio=x_ini,
        x_cobertura_fin=x_fin,
        t_nodos=t_nodos,
        x_nodos=x_nodos,
    )
