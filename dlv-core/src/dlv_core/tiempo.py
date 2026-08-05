"""Motor de tiempo multi-log: segmentos y eje X virtual (tarea F2-01).

Especificación: `docs/03-arquitectura.md` §3.6. Es la pieza que sostiene la
**prioridad número uno** del propietario —ver varios logs en paralelo y
concatenados—, así que las reglas de §3.6 se implementan aquí como errores, no
como recomendaciones.

Cada log cargado es un **segmento** con su propio reloj. Este módulo no lee
ficheros ni conoce formatos: recibe segmentos ya construidos (los produce
`reloj.Reconciliacion.a_segmento`, F1-04) y calcula dónde cae cada uno en el eje
X compartido.

QUÉ ES EL EJE VIRTUAL Y POR QUÉ HACE FALTA
==========================================
Los instantes de un log son locales: empiezan en 0 y no dicen nada de los demás
logs. Para dibujar dos tiradas en el mismo gráfico hace falta una coordenada
común, y esa coordenada no es «el tiempo»: es una construcción que depende de
cómo el usuario quiera comparar.

    x = t_local + desfase(segmento)

`EjeVirtual` es esa función y su inversa, junto con el rango que ocupa y las
fronteras que nadie debe cruzar dibujando. Todo lo que pinta, mide o detecta
pregunta aquí en vez de calcular su propio desfase: si hubiera dos sitios que
calculan la x, un día darían dos respuestas distintas y el usuario compararía
señales desplazadas sin enterarse.

DOS VISTAS, LA MISMA ARITMÉTICA
===============================
- **Paralela** (`eje_paralelo`): los segmentos se superponen. Un mismo `x` puede
  pertenecer a varios segmentos a la vez, y eso es justo el punto: comparar la
  misma vuelta de dos tiradas.
- **Concatenada** (`eje_concatenado`): los segmentos van uno detrás de otro con
  un **hueco explícito** entre ellos. Un `x` pertenece a un segmento o a ningún
  segmento; nunca a dos.

`locales_en(x)` devuelve una tupla en los dos casos: N elementos en paralelo,
cero o uno en concatenado. Es la razón de que sea una tupla y no un valor
opcional: una API que devolviera «el segmento» obligaría a la vista paralela a
elegir uno arbitrariamente, que es cómo se pierde la mitad de la comparación.

TRES REGLAS QUE SON ERRORES, NO AVISOS
======================================
1. **El reloj absoluto exige que TODOS los segmentos lo tengan fiable.** §3.6 lo
   dice para el modo, y aquí se comprueba antes de calcular nada. Alinear por
   reloj un log con época ficticia —los dos `Log2768/2769` de `samples/real/`
   declaran los dos `19800101 01:01:01`— los superpondría en el mismo instante
   de 1980 y las dos tiradas se verían como simultáneas. Un repliegue silencioso
   a relativo sería peor todavía: el usuario habría pedido reloj y estaría
   mirando otra cosa.
2. **En el hueco no hay dato.** `locales_en` de una `x` que cae entre dos
   segmentos concatenados devuelve la tupla vacía. Es lo que impide que el
   cursor invente un valor por retención del último punto del segmento
   anterior, que es exactamente «fingir continuidad» (§1.5).
3. **`POR_EVENTO` y `CORRELACION` todavía no existen** (F2-07 y F2-08). Piden
   datos que este módulo no recibe: el ancla de un evento y las series de la
   pirámide. Lanzan `NotImplementedError` citando su tarea en vez de caer a
   relativo, porque un desfase de 0 tiene el mismo aspecto que un desfase bien
   calculado.

ADR-009
=======
Este módulo recorre **segmentos**, no muestras: el banco del caso peor son 8
logs (`docs/05` F2-15), así que un bucle de Python sobre esa lista cuesta
microsegundos y es lo legible. Lo que ADR-009 prohíbe es recorrer las 73 M de
muestras, y aquí no se toca ni una: el desfase se aplica a los vectores de
instantes con una suma vectorizada en quien dibuja, no elemento a elemento aquí.
No hay nada que optimizar en este fichero.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from dlv_core.almacen import ChannelSeries

__all__ = [
    "HUECO_CONCATENADO_S",
    "EjeVirtual",
    "ErrorDeTiempo",
    "FiabilidadReloj",
    "Frontera",
    "ModoDesfase",
    "PuntoLocal",
    "Segmento",
    "concatenar",
    "correlacionar",
    "desfase_efectivo",
    "eje_concatenado",
    "eje_paralelo",
]

#: Hueco por omisión entre dos segmentos concatenados, en segundos. No es
#: cosmético: es lo que hace visible la frontera sin necesidad de mirar la
#: leyenda, y lo que garantiza que dos segmentos nunca compartan una `x`. Un
#: hueco de 0 haría indistinguible «el log siguió» de «aquí empieza otro log».
HUECO_CONCATENADO_S = 1.0


class ErrorDeTiempo(ValueError):
    """Se ha pedido una alineación que no se puede calcular sin inventar."""


class FiabilidadReloj(Enum):
    """Fiabilidad del `t0_absoluto` de un segmento (§3.6).

    La produce la reconciliación de reloj (`reloj.reconciliar`, F1-04).
    """

    FIABLE = auto()
    NO_FIABLE = auto()
    """Hay una marca de tiempo absoluta pero no cuadra con las filas: se puede
    enseñar, no se puede usar para alinear."""

    DESCONOCIDA = auto()
    """No existe tiempo absoluto (época ficticia, o el log no lo declara)."""


class ModoDesfase(Enum):
    """Cómo se calcula el desfase de cada segmento en la vista paralela (§3.6)."""

    RELOJ_ABSOLUTO = auto()
    """Del `t0_absoluto`. Exige `FIABLE` en todos los segmentos."""

    RELATIVO = auto()
    """Todos empiezan en 0: la comparación «desde el principio de la tirada»."""

    MANUAL = auto()
    """El `offset_usuario` que el usuario arrastró (F2-06)."""

    POR_EVENTO = auto()
    """Alineado por un ancla (primer WOT, primer corte, launch). Tarea F2-07."""

    CORRELACION = auto()
    """Argmáx de la correlación cruzada del rol de referencia. Tarea F2-08."""


@dataclass(slots=True, frozen=True)
class Segmento:
    """Un log cargado, con su identidad temporal (§3.6).

    Inmutable a propósito: el desfase efectivo NO es un campo de esta clase,
    porque depende del modo de alineación y del conjunto de segmentos abiertos.
    Guardarlo aquí obligaría a recalcularlo por mutación cada vez que el usuario
    cambia de modo, y ese es el camino a que dos vistas discrepen. Lo que el
    usuario arrastra a mano —`offset_usuario`— sí es del segmento, y para
    cambiarlo está `con_offset`.
    """

    id: str
    t_inicio: float
    """Primer instante del log, en segundos locales. Es 0,0 por construcción en
    el camino nativo (`SesionLog.t_inicio` resta `t0`), pero se recibe en vez de
    asumirse: cablear un 0 sería un error mudo el día que un formato traiga su
    propio origen."""

    t_fin: float
    """Último instante, en segundos locales. El máximo entre grupos de muestreo,
    que no terminan a la vez (docs/01 §1.6)."""

    t0_absoluto: datetime | None
    fiabilidad_reloj: FiabilidadReloj
    orden: int
    """Lo que ordena este segmento frente a los demás: `Log Number` cuando el
    reloj no es fiable (§1.5), u orden de carga. Es la clave de la vista
    concatenada."""

    offset_usuario: float = 0.0
    etiqueta: str | None = None
    """Nombre para la leyenda. `None` usa el `id`."""

    def __post_init__(self) -> None:
        if self.t_fin < self.t_inicio:
            raise ErrorDeTiempo(
                f"segmento '{self.id}': t_fin ({self.t_fin}) es anterior a t_inicio "
                f"({self.t_inicio}). Un segmento de duración negativa desplazaría todo "
                "lo que vaya detrás en la vista concatenada"
            )
        if self.fiabilidad_reloj is FiabilidadReloj.FIABLE and self.t0_absoluto is None:
            raise ErrorDeTiempo(
                f"segmento '{self.id}': fiabilidad FIABLE sin `t0_absoluto`. La "
                "combinación haría que el modo de reloj absoluto pasara la comprobación "
                "y luego no tuviera con qué alinear"
            )

    @property
    def duracion(self) -> float:
        return self.t_fin - self.t_inicio

    @property
    def nombre(self) -> str:
        return self.etiqueta if self.etiqueta is not None else self.id

    def con_offset(self, offset_usuario: float) -> Segmento:
        """Copia con otro `offset_usuario` (lo que hace F2-06 al arrastrar)."""
        return Segmento(
            id=self.id,
            t_inicio=self.t_inicio,
            t_fin=self.t_fin,
            t0_absoluto=self.t0_absoluto,
            fiabilidad_reloj=self.fiabilidad_reloj,
            orden=self.orden,
            offset_usuario=offset_usuario,
            etiqueta=self.etiqueta,
        )


@dataclass(slots=True, frozen=True)
class PuntoLocal:
    """Una `x` del eje virtual traducida al reloj local de un segmento."""

    id_segmento: str
    t_local: float


@dataclass(slots=True, frozen=True)
class Frontera:
    """Una unión entre dos segmentos concatenados.

    §3.6: «las fronteras se marcan siempre, no como opción», y ninguna línea las
    cruza. `x_fin_anterior` y `x_inicio_siguiente` delimitan el hueco, así que
    quien dibuja tiene los dos bordes sin tener que recalcularlos.
    """

    x_fin_anterior: float
    x_inicio_siguiente: float
    id_anterior: str
    id_siguiente: str

    @property
    def x_centro(self) -> float:
        """Dónde poner la marca de la frontera."""
        return (self.x_fin_anterior + self.x_inicio_siguiente) / 2.0


@dataclass(slots=True, frozen=True)
class EjeVirtual:
    """El eje X compartido: el desfase de cada segmento y su geometría.

    Es el único sitio que traduce entre el reloj local de un segmento y la
    coordenada que se dibuja. Todo lo que pinta, mide o detecta pregunta aquí.
    """

    modo: ModoDesfase
    segmentos: tuple[Segmento, ...]
    desfases: Mapping[str, float]
    concatenado: bool
    fronteras: tuple[Frontera, ...] = ()

    @property
    def x_min(self) -> float:
        return min(self.desfases[s.id] + s.t_inicio for s in self.segmentos)

    @property
    def x_max(self) -> float:
        return max(self.desfases[s.id] + s.t_fin for s in self.segmentos)

    @property
    def duracion(self) -> float:
        return self.x_max - self.x_min

    def desfase_de(self, id_segmento: str) -> float:
        try:
            return self.desfases[id_segmento]
        except KeyError:
            raise ErrorDeTiempo(
                f"el segmento '{id_segmento}' no está en este eje "
                f"(hay: {', '.join(s.id for s in self.segmentos)})"
            ) from None

    def a_virtual(self, id_segmento: str, t_local: float) -> float:
        """Reloj local → coordenada del eje. Es la fórmula `x = t + desfase`."""
        return t_local + self.desfase_de(id_segmento)

    def a_local(self, id_segmento: str, x: float) -> float:
        """Inversa exacta de `a_virtual` para un segmento dado.

        No comprueba que la `x` caiga dentro del segmento: eso es lo que decide
        `locales_en`, y separar las dos cosas permite pedir el instante local de
        una `x` fuera de rango (lo necesita el zoom, que extrapola los bordes).
        """
        return x - self.desfase_de(id_segmento)

    def contiene(self, id_segmento: str, x: float) -> bool:
        seg = self.segmento(id_segmento)
        t = self.a_local(id_segmento, x)
        return seg.t_inicio <= t <= seg.t_fin

    def segmento(self, id_segmento: str) -> Segmento:
        for s in self.segmentos:
            if s.id == id_segmento:
                return s
        raise ErrorDeTiempo(f"el segmento '{id_segmento}' no está en este eje")

    def locales_en(self, x: float) -> tuple[PuntoLocal, ...]:
        """Qué segmentos cubren esta `x`, y en qué instante local de cada uno.

        - Vista paralela: puede devolver varios. Es el objeto de la vista.
        - Vista concatenada: cero o uno. **Cero cuando la `x` cae en un hueco**,
          y eso es información, no un caso de borde: es lo que impide que el
          cursor rellene el hueco con el último valor del segmento anterior.
        """
        return tuple(
            PuntoLocal(s.id, self.a_local(s.id, x))
            for s in self.segmentos
            if self.contiene(s.id, x)
        )

    def frontera_entre(self, x0: float, x1: float) -> tuple[Frontera, ...]:
        """Las fronteras que caen en `[x0, x1]`.

        Lo que necesita quien dibuja un tramo para saber si tiene que cortar la
        línea: si esto devuelve algo, hay que partir el trazo (§3.6).
        """
        lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
        return tuple(f for f in self.fronteras if lo <= f.x_centro <= hi)


# --------------------------------------------------------------------------- #
# Desfases
# --------------------------------------------------------------------------- #
def _comprobar_ids_unicos(segmentos: Sequence[Segmento]) -> None:
    vistos: set[str] = set()
    for s in segmentos:
        if s.id in vistos:
            raise ErrorDeTiempo(
                f"el id de segmento '{s.id}' está repetido. Los desfases se indexan por "
                "id, así que uno repetido haría que un segmento heredara el desfase del "
                "otro sin que nada lo dijera"
            )
        vistos.add(s.id)


def _no_vacio(segmentos: Sequence[Segmento]) -> None:
    if not segmentos:
        raise ErrorDeTiempo("no hay ningún segmento: no hay eje que construir")


def desfase_efectivo(
    segmentos: Sequence[Segmento],
    *,
    modo: ModoDesfase,
    rol_referencia: str | None = None,
) -> dict[str, float]:
    """El desfase de cada segmento para la vista paralela (§3.6).

    El resultado está **normalizado**: el desfase mínimo es siempre 0, así que
    el eje empieza donde empieza el primer segmento y no en una fecha absoluta
    de 1970. Sin normalizar, el modo de reloj daría coordenadas del orden de
    1,7 × 10⁹ y un `float32` en el renderizador perdería la resolución de
    milisegundos (7 dígitos significativos no llegan). Es una decisión de
    precisión, no de estética.
    """
    _no_vacio(segmentos)
    _comprobar_ids_unicos(segmentos)

    if modo is ModoDesfase.RELATIVO:
        crudos = {s.id: 0.0 for s in segmentos}
    elif modo is ModoDesfase.MANUAL:
        crudos = {s.id: s.offset_usuario for s in segmentos}
    elif modo is ModoDesfase.RELOJ_ABSOLUTO:
        crudos = _desfases_por_reloj(segmentos)
    elif modo is ModoDesfase.POR_EVENTO:
        ancla = f", rol {rol_referencia}" if rol_referencia else ""
        raise NotImplementedError(
            "la alineación por evento es la tarea F2-07: necesita el ancla "
            f"(primer WOT, primer corte, launch{ancla}) y este módulo no recibe "
            "series. No se cae a RELATIVO a propósito: un desfase de 0 tiene el "
            "mismo aspecto que uno bien calculado"
        )
    elif modo is ModoDesfase.CORRELACION:
        raise NotImplementedError(
            "la autoalineación por correlación cruzada es la tarea F2-08: necesita los "
            "niveles L4-L6 de la pirámide, que este módulo no recibe. No se cae a "
            "RELATIVO a propósito"
        )
    else:  # pragma: no cover - el enum está cerrado
        raise ErrorDeTiempo(f"modo de desfase no contemplado: {modo}")

    minimo = min(crudos[s.id] + s.t_inicio for s in segmentos)
    return {id_: valor - minimo for id_, valor in crudos.items()}


def _desfases_por_reloj(segmentos: Sequence[Segmento]) -> dict[str, float]:
    """Desfases en segundos desde el `t0_absoluto` de cada segmento.

    Exige `FIABLE` en todos, y el mensaje nombra a los culpables con su motivo:
    «no se puede alinear por reloj» sin decir cuál de los ocho logs lo impide es
    un error que el usuario no puede resolver.
    """
    problematicos = [s for s in segmentos if s.fiabilidad_reloj is not FiabilidadReloj.FIABLE]
    if problematicos:
        detalle = ", ".join(
            f"'{s.nombre}' ({s.fiabilidad_reloj.name.lower()})" for s in problematicos
        )
        raise ErrorDeTiempo(
            "el modo de reloj absoluto exige que TODOS los segmentos tengan reloj fiable, "
            f"y estos no lo tienen: {detalle}. Alinearlos por reloj los superpondría en "
            "un instante inventado (los logs internos de una ECU sin reloj de tiempo real "
            "declaran todos la misma época de fábrica). Usa el modo relativo, el manual, "
            "o alinea por evento cuando F2-07 esté"
        )
    # `t0_absoluto` no es None aquí: `Segmento.__post_init__` ya lo garantiza para
    # los FIABLE, y acabamos de descartar el resto.
    referencia = min(s.t0_absoluto for s in segmentos if s.t0_absoluto is not None)
    return {
        s.id: (s.t0_absoluto - referencia).total_seconds()
        for s in segmentos
        if s.t0_absoluto is not None
    }


# --------------------------------------------------------------------------- #
# Ejes
# --------------------------------------------------------------------------- #
def eje_paralelo(
    segmentos: Sequence[Segmento],
    *,
    modo: ModoDesfase,
    rol_referencia: str | None = None,
) -> EjeVirtual:
    """Los N segmentos superpuestos sobre un eje X común (§3.6).

    No hay fronteras: en paralelo los segmentos se solapan a propósito, así que
    no hay ninguna unión que cortar. Es la diferencia de fondo con
    `eje_concatenado`, y la razón de que `fronteras` sea `()` y no una lista
    vacía por descuido.
    """
    desfases = desfase_efectivo(segmentos, modo=modo, rol_referencia=rol_referencia)
    return EjeVirtual(
        modo=modo,
        segmentos=tuple(segmentos),
        desfases=desfases,
        concatenado=False,
    )


def eje_concatenado(
    segmentos: Sequence[Segmento], *, hueco_s: float = HUECO_CONCATENADO_S
) -> EjeVirtual:
    """Los segmentos uno detrás de otro, con hueco explícito entre ellos (§3.6).

    El orden lo da `Segmento.orden` —`Log Number` cuando el reloj no es fiable,
    que es el caso de los logs internos de una ECU (§1.5)— y no el reloj: es lo
    único monótono que hay en ese caso. Con `orden` empatado se desempata por
    `id` para que el resultado sea reproducible entre ejecuciones; un orden que
    depende del recorrido de un diccionario haría que el mismo proyecto se
    abriera distinto dos veces.

    El modo del eje resultante es `RELATIVO`: en concatenado el desfase no lo
    elige el usuario, lo impone la colocación. Que el usuario pueda editar el
    hueco es F2-10; que pueda elegir el desfase, no, porque cambiaría el orden.
    """
    _no_vacio(segmentos)
    _comprobar_ids_unicos(segmentos)
    if hueco_s <= 0.0:
        # Estrictamente mayor que cero, no «no negativo». Con hueco 0 la x de la
        # unión sería a la vez el t_fin de un segmento y el t_inicio del
        # siguiente, así que `locales_en` devolvería dos puntos y se rompería el
        # invariante que este módulo declara: en concatenado una x pertenece a un
        # segmento o a ninguno. Y §3.6 exige que la frontera se marque siempre,
        # así que un hueco invisible tampoco es una opción legítima.
        raise ErrorDeTiempo(
            f"el hueco entre segmentos tiene que ser mayor que cero ({hueco_s} s): con "
            "hueco cero o negativo la frontera deja de ser visible y una misma x "
            "pertenecería a dos logs a la vez"
        )

    ordenados = sorted(segmentos, key=lambda s: (s.orden, s.id))
    desfases: dict[str, float] = {}
    fronteras: list[Frontera] = []
    cursor = 0.0
    anterior: Segmento | None = None
    for s in ordenados:
        desfases[s.id] = cursor - s.t_inicio
        if anterior is not None:
            fronteras.append(
                Frontera(
                    x_fin_anterior=desfases[anterior.id] + anterior.t_fin,
                    x_inicio_siguiente=cursor,
                    id_anterior=anterior.id,
                    id_siguiente=s.id,
                )
            )
        cursor += s.duracion + hueco_s
        anterior = s

    return EjeVirtual(
        modo=ModoDesfase.RELATIVO,
        segmentos=tuple(ordenados),
        desfases=desfases,
        concatenado=True,
        fronteras=tuple(fronteras),
    )


# --------------------------------------------------------------------------- #
# Pendiente de fases posteriores
# --------------------------------------------------------------------------- #
def correlacionar(
    referencia: ChannelSeries, candidata: ChannelSeries, *, nivel_piramide: int
) -> float:
    """Argmáx de la correlación cruzada sobre niveles L4-L6 de la pirámide (§3.6).

    Tarea **F2-08**. Se calcula con `numpy.correlate`/FFT sobre la pirámide, no
    sobre L0; el refinamiento en L0 alrededor del máximo encontrado es un paso
    posterior, también vectorizado.
    """
    raise NotImplementedError("autoalineación por correlación cruzada: tarea F2-08")


def concatenar(
    segmentos: Sequence[Segmento], series_por_segmento: Mapping[str, Iterable[ChannelSeries]]
) -> np.ndarray:
    """Une las series de varios segmentos en una sola (vista concatenada).

    Tarea **F2-09**. `eje_concatenado` (F2-01) ya da la geometría —el desfase de
    cada segmento y las fronteras—; lo que falta aquí es la unión de los datos,
    que necesita la identidad de canal en capas de F2-02 para saber qué serie de
    un log es «la misma» que la de otro.

    Reglas duras de §3.6 que esta función tendrá que cumplir: nunca se dibuja una
    línea que cruce una frontera, y un canal ausente en un segmento produce
    hueco, no ceros.
    """
    raise NotImplementedError("unión de series de la vista concatenada: tarea F2-09")
