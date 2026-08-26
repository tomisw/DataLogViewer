"""Anclaje por evento: alinear N segmentos por la posición de un ancla común
(primer WOT, primer corte, activación de launch) — tarea F2-07.

Especificación: `docs/03-arquitectura.md` §3.6, tabla «Vista paralela»
(«Por evento: posición del ancla ... en cada segmento») y `docs/02` §2.10, E2.2:
«anclaje por evento (primer WOT, primer corte, activación de launch)».

QUÉ RESUELVE ESTE MÓDULO Y QUÉ NO
==================================
`tiempo.py` (F2-01) ya sabe construir un eje virtual paralelo a partir de un
`dict[str, float]` de desfases (`tiempo.EjeVirtual`, `tiempo.Segmento`), y ya
declara el hueco a propósito: `tiempo.desfase_efectivo` lanza
`NotImplementedError` para `ModoDesfase.POR_EVENTO` en vez de caer a
`RELATIVO`, precisamente para que nadie confunda «no calculado» con «desfase
cero» (ver su docstring, «un desfase de 0 tiene el mismo aspecto que uno bien
calculado»). Este módulo es lo que faltaba: busca el instante del ancla en la
serie de CADA segmento y calcula el desfase que lo lleva a un punto común.

No toca `tiempo.py` (otros agentes trabajan ahí en paralelo con F2-05/F2-06):
construye su propio `tiempo.EjeVirtual` con `modo=ModoDesfase.POR_EVENTO`
llamando directamente al constructor del dataclass, que no exige pasar por
`eje_paralelo`/`desfase_efectivo`. Es la misma estructura de datos, calculada
por otro camino.

DÓNDE CAE EL ANCLA EN EL EJE VIRTUAL: EN `x = 0`
=================================================
`x = t_local + desfase(segmento)`. Para que el ancla de todos los segmentos
coincida en el mismo `x`, basta una constante compartida `C` y
`desfase(s) = C - t_ancla_local(s)`. Este módulo elige `C = 0`: el instante del
ancla es el origen del eje, con lo anterior en negativo y lo posterior en
positivo. Es una decisión de diseño, no una consecuencia forzada de la
aritmética -- a diferencia de `desfase_efectivo`, aquí NO hace falta normalizar
para evitar coordenadas enormes (los relojes locales ya son pequeños, del orden
de la duración del log), así que la normalización de los otros modos
("el desfase mínimo es siempre 0") no aplica por el mismo motivo. `C = 0` es la
lectura más literal de «posición del ancla ... en cada segmento»: convierte el
eje en «tiempo desde el ancla», que es exactamente lo que hace falta para
superponer dos tiradas que no empezaron a la vez. Si el propietario prefiere
otra convención (por ejemplo normalizar como los demás modos), es un cambio de
la línea que calcula `desfases` en `ancla_por_evento`, no de la arquitectura.

QUÉ PASA CUANDO EL ANCLA NO APARECE EN UN SEGMENTO (la pregunta que decide la
tarea)
==============================================================================
Un log que nunca llegó a WOT no tiene «primer WOT» -- y no es hipotético: los
dos logs internos de la ECU de `samples/real/` (`Log2768`/`Log2769`) tienen
mariposa máxima 0,558 y 0,569, por debajo del umbral de WOT
(`[segmentacion].tps_wot_entrada`, 0,80), así que NUNCA llegan a WOT
(`data/umbrales.toml`, comentario de `[segmentacion]`, línea medida sobre los
tres logs reales).

Ese segmento **no entra en el eje devuelto**. `ancla_por_evento` no completa su
desfase con 0: lo excluye de `InformeDeAnclaje.eje` y lo explica en
`InformeDeAnclaje.sin_ancla` con el motivo exacto
(`MotivoSinAncla.EVENTO_NO_OCURRIDO`). Quien llama decide qué hacer con un log
que se queda fuera del ancla -- enseñarlo sin alinear, ofrecer alinearlo por
otro modo, o simplemente decírselo al usuario--, pero la decisión es visible y
explícita, nunca un `0` silencioso que lo dejaría superpuesto con los demás
como si estuviera alineado.

Si NINGÚN segmento tiene el ancla, `InformeDeAnclaje.eje` es `None`: no hay
nada que alinear, y `None` es la respuesta correcta -- no un eje de longitud
cero, que `tiempo.EjeVirtual` ni siquiera admite (`_no_vacio`).

LOS TRES TIPOS DE ANCLA, Y DE DÓNDE SALE CADA UNO (regla 3 de CLAUDE.md:
reutilizar antes que declarar)
=========================================================================
* **PRIMER_WOT** -- reutiliza `segmentacion.segmentar` (F3-16) TAL CUAL: el
  ancla es literalmente `t_inicio_ms` del primer `segmentacion.Segmento` de
  clase `ClaseDeSegmento.WOT` que ese módulo ya sabe encontrar («TPS > 80 % y
  RPM creciente durante > 1,5 s», con su histéresis y su permanencia). No hay
  ninguna redefinición propia de WOT aquí: `UmbralesDeAnclaje.umbrales_wot` y
  `.permanencia_wot_base` son los MISMOS objetos que ya construye quien llama
  para el panel de tiradas, no una copia.

* **PRIMER_CORTE** -- reutiliza el umbral de `[detectores.D14].umbral_min`
  (0,01, fracción de `cut_percentage`), el mismo número y el mismo motivo que
  `exclusion.UmbralesDeExclusion.corte_umbral_min`. NO existe en el proyecto un
  detector D14 ejecutable que produzca una lista de eventos de corte (D14 solo
  está declarado en `data/umbrales.toml` y usado como número, tanto aquí como
  en `exclusion.py`): este módulo construye la condición con
  `primitivas.umbral_con_histeresis` exactamente como hace
  `exclusion._condicion_corte`, incluida su misma decisión de NO aplicar la
  permanencia de 100 ms que D14 declara como detector (`_instante_primer_evento_ms`
  documenta el motivo, calcado del de `exclusion.py`: es una salida directa de
  la ECU, no una lectura analógica ruidosa).

* **LANZAMIENTO** -- **no existe ningún detector de los 18 de `docs/04` §4.3
  para «activación de lanzamiento»**, launch control no es uno de ellos. El
  rol `launch_state` existe (`data/roles.toml`), pero ni `docs/01` §1.10 ni
  ningún otro documento dicen QUÉ código de ese enum (rango documentado
  −101…1, "códigos negativos amplios") significa «activo», y ninguno de los
  tres logs de `samples/real/` trae ese canal para medirlo. Inventar un umbral
  aquí sería exactamente la «opinión disfrazada de física» de la regla 3:
  `UmbralesDeAnclaje.lanzamiento_activo_min` **no tiene valor por omisión, ni
  en el código ni en `data/umbrales.toml`** (este módulo no añade una sección
  nueva porque no hay ningún número que declarar todavía). Mientras sea
  `None`, `ancla_por_evento` rechaza `TipoAncla.LANZAMIENTO` con un
  `ErrorDeAnclaje` explícito en vez de adivinar. El mecanismo entero está
  escrito y lista para el día en que el propietario mida ese código en un log
  real y lo pase explícitamente (o lo declare en `data/umbrales.toml`, que
  `UmbralesDeAnclaje.desde_mapa` ya sabe leer si aparece).

CONFIANZA DEL ROL: UNA COINCIDENCIA DIFUSA NO ANCLA A CIEGAS (regla 5 de la
tarea, docs/07 §7.15)
=============================================================================
Si el rol del que sale el ancla (`throttle_position`/`engine_speed` para WOT,
`cut_percentage` para CORTE, `launch_state` para LANZAMIENTO) se emparejó por
parecido de nombre y no está confirmado, alinear por él es una mentira
silenciosa con el signo cambiado respecto a `exclusion.py`: en vez de ensuciar
un promedio, desplazaría visualmente un log entero basándose en una conjetura.
Mismo criterio de TRES estados que `exclusion.excluir` y
`activacion_detectores.evaluar_activacion`: rol ausente (no hay nada que
confirmar), rol sin confirmar (el usuario lo arregla con un clic) y rol
confirmado (se calcula). `ancla_por_evento` recibe `roles_sin_confirmar` **por
segmento** (`Mapping[str, frozenset[str]]`) y no una única lista global, porque
la confianza de un rol es una propiedad de CADA log, no del conjunto: el
`cut_percentage` de un log puede estar confirmado y el de otro venir de una
coincidencia difusa.

ADR-009
=======
El único bucle de `ancla_por_evento` recorre los SEGMENTOS pasados (unos pocos
logs abiertos a la vez, nunca muestras). Todo el trabajo por muestra --la
condición de umbral, la búsqueda de eventos, la segmentación de WOT-- lo hacen
`primitivas.umbral_con_histeresis`, `primitivas.eventos` y
`segmentacion.segmentar`, que ya cumplen ADR-009 y no se reimplementan aquí.

LA CLASE DE CONVERSIÓN (regla 4 de CLAUDE.md)
===============================================
Las series de entrada (`cut_percentage`, `launch_state`, y las que necesita
`segmentacion.segmentar`) tienen que llegar como `Clase.PUNTO`: son canales tal
como salen del almacén, no derivadas. El instante de un ancla es un `PUNTO` en
el tiempo (un índice de muestra convertido a milisegundos, no una magnitud
física con clase propia); el desfase que produce este módulo para
`tiempo.EjeVirtual` es un `INTERVALO` (una diferencia de dos instantes), y las
dos cosas no se mezclan: el desfase nunca se compara con un umbral de canal ni
viceversa.

LO QUE ESTE MÓDULO NO HACE
============================
* No abre ficheros (ADR-002): recibe las series y los umbrales ya cargados.
* No decide el modo de alineación por el usuario ni dibuja nada: solo calcula
  `tiempo.EjeVirtual` para el modo `POR_EVENTO`, igual que `tiempo.eje_paralelo`
  lo hace para los demás.
* No inventa un cuarto tipo de ancla. Si hace falta uno nuevo, es una entrada
  más en `TipoAncla` con su propia procedencia documentada, no una extensión
  genérica sin significado.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from dlv_core.exclusion import ROL_CORTE
from dlv_core.primitivas import (
    Direccion,
    Permanencia,
    Serie,
    Vectorial,
    eventos,
    umbral_con_histeresis,
)
from dlv_core.segmentacion import (
    ROL_MARIPOSA,
    ROL_REGIMEN,
    ClaseDeSegmento,
    UmbralesDeSegmentacion,
    segmentar,
)
from dlv_core.tiempo import EjeVirtual, ModoDesfase
from dlv_core.tiempo import Segmento as SegmentoDeLog
from dlv_core.unidades import Clase

__all__ = [
    "ROL_CORTE",
    "ROL_LANZAMIENTO",
    "ROL_MARIPOSA",
    "ROL_REGIMEN",
    "ErrorDeAnclaje",
    "InformeDeAnclaje",
    "MotivoSinAncla",
    "SegmentoSinAncla",
    "TipoAncla",
    "UmbralesDeAnclaje",
    "ancla_por_evento",
]

MS_POR_S = 1000.0

ROL_LANZAMIENTO = "launch_state"
"""El rol de `data/roles.toml` para el estado del control de lanzamiento
(dimensión `enum`, códigos −101…1, `docs/01` §1.10). Ningún documento del
propietario dice qué código es «activo» -- ver la cabecera del módulo,
LANZAMIENTO."""

_LANZAMIENTO_CODIGO_MIN, _LANZAMIENTO_CODIGO_MAX = -101.0, 1.0
"""Citas literales del rango PLAUSIBLE de `data/roles.toml [roles.launch_state]`
(«códigos negativos amplios»). Se usan solo para validar que, SI alguien
proporciona `lanzamiento_activo_min`, el número cae dentro del rango del canal
-- no son un umbral de activación ni una suposición de qué código enciende el
launch."""

# Sin permanencia y sin mínimo de muestras: mismo criterio y mismo motivo que
# `exclusion._condicion_corte` para `cut_percentage` -- es una salida directa
# de la ECU (un código de estado), no una lectura analógica ruidosa. Si dice
# que el canal cruzó el umbral en una muestra, lo cruzó; exigirle sostenerse
# adoptaría la permanencia que D14 aplica como DETECTOR (para no generar una
# incidencia por un pico), y aquí no se genera una incidencia: se busca el
# primer instante real. Vale igual para `launch_state`, que es otro código de
# estado directo y no una magnitud continua. No son valores de
# `data/umbrales.toml`: son una decisión estructural, no un umbral de física.
_PERMANENCIA_CANAL_DE_ESTADO_S = 0.0
_MUESTRAS_MINIMAS_CANAL_DE_ESTADO = 1

_CLAVES_ESCALARES: tuple[str, ...] = ("corte_umbral_min", "maximo_de_eventos")
"""Las claves que `UmbralesDeAnclaje.desde_mapa` exige. Una sola lista, mismo
motivo que `segmentacion._CLAVES_ESCALARES` y `exclusion._CLAVES_ESCALARES`."""


class ErrorDeAnclaje(ValueError):
    """Uso incorrecto del módulo, o una configuración que no se puede aplicar.

    Un log raro no produce esta excepción: produce un `InformeDeAnclaje` con
    los segmentos sin ancla explicados en `sin_ancla`. Esto otro -- pedir
    `TipoAncla.LANZAMIENTO` sin que `lanzamiento_activo_min` esté definido, una
    serie que no es `Clase.PUNTO`, una lista de segmentos vacía-- es un fallo de
    quien llama, y callarlo produciría una alineación plausible y falsa.
    """


# --------------------------------------------------------------------------- #
# Los tres tipos de ancla
# --------------------------------------------------------------------------- #
class TipoAncla(Enum):
    """Los tres anclas de `docs/02` §2.10 y `docs/03` §3.6."""

    PRIMER_WOT = "primer_wot"
    PRIMER_CORTE = "primer_corte"
    LANZAMIENTO = "lanzamiento"

    @property
    def roles_requeridos(self) -> tuple[str, ...]:
        """Los roles sin los cuales este ancla NO se puede buscar en un
        segmento. Sin ellos no se aproxima con otro canal: el segmento se
        declara sin ancla por `MotivoSinAncla.ROL_AUSENTE`."""
        return _ROLES_REQUERIDOS[self]


_ROLES_REQUERIDOS: dict[TipoAncla, tuple[str, ...]] = {
    TipoAncla.PRIMER_WOT: (ROL_REGIMEN, ROL_MARIPOSA),
    TipoAncla.PRIMER_CORTE: (ROL_CORTE,),
    TipoAncla.LANZAMIENTO: (ROL_LANZAMIENTO,),
}


# --------------------------------------------------------------------------- #
# Umbrales configurables
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class UmbralesDeAnclaje:
    """Los umbrales de los tres anclas. **Sin valores por omisión en el
    código** para los dos escalares (regla 3 de `CLAUDE.md`): `desde_mapa`
    exige `corte_umbral_min` y `maximo_de_eventos`, y falla si falta alguno.

    Procedencia de cada campo -- ver la cabecera del módulo para el porqué de
    cada reutilización:

        corte_umbral_min      <- [detectores.D14].umbral_min
        maximo_de_eventos     <- [motor_de_deteccion].maximo_de_eventos
        umbrales_wot          <- objeto ya construido por quien llama con
                                  [segmentacion] (segmentacion.UmbralesDeSegmentacion)
        permanencia_wot_base  <- objeto ya construido por quien llama con
                                  [general] + [motor_de_deteccion]
                                  (primitivas.Permanencia)
        lanzamiento_activo_min <- SIN PROCEDENCIA. Ver LANZAMIENTO en la
                                  cabecera del módulo. `None` por omisión.

    `umbrales_wot` y `permanencia_wot_base` no se aplanan en escalares propios
    (a diferencia de `exclusion.UmbralesDeExclusion`, que sí copia los campos
    de otros detectores): aquí el ancla de WOT es una llamada directa a
    `segmentacion.segmentar`, así que lo que hace falta es EL MISMO objeto que
    ya usa quien llama para segmentar, no una copia que se pueda desincronizar.
    """

    corte_umbral_min: float
    maximo_de_eventos: int
    umbrales_wot: UmbralesDeSegmentacion
    permanencia_wot_base: Permanencia
    lanzamiento_activo_min: float | None = None
    """Código de `launch_state` a partir del cual se considera activo el
    control de lanzamiento. Ver LANZAMIENTO en la cabecera del módulo: no tiene
    procedencia documentada ni medida, así que no tiene valor por omisión.
    Mientras sea `None`, `TipoAncla.LANZAMIENTO` no es utilizable."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.corte_umbral_min <= 1.0:
            raise ErrorDeAnclaje(
                f"corte_umbral_min = {self.corte_umbral_min!r} tiene que ser una FRACCIÓN "
                "en [0, 1]: `cut_percentage` es de dimensión `ratio` (data/roles.toml), no "
                "un porcentaje"
            )
        if self.maximo_de_eventos < 1:
            raise ErrorDeAnclaje(
                f"maximo_de_eventos = {self.maximo_de_eventos!r} tiene que ser >= 1"
            )
        if self.lanzamiento_activo_min is not None and not (
            _LANZAMIENTO_CODIGO_MIN <= self.lanzamiento_activo_min <= _LANZAMIENTO_CODIGO_MAX
        ):
            raise ErrorDeAnclaje(
                f"lanzamiento_activo_min = {self.lanzamiento_activo_min!r} está fuera del "
                f"rango plausible de launch_state ([{_LANZAMIENTO_CODIGO_MIN}, "
                f"{_LANZAMIENTO_CODIGO_MAX}], data/roles.toml [roles.launch_state]); si es un "
                "código real de la ECU, revisa el rango del canal, no este umbral"
            )

    @classmethod
    def desde_mapa(
        cls,
        mapa: Mapping[str, Any],
        *,
        umbrales_wot: UmbralesDeSegmentacion,
        permanencia_wot_base: Permanencia,
    ) -> UmbralesDeAnclaje:
        """Construye los dos escalares desde un mapa ya fusionado por quien
        llama (ADR-002), con las claves renombradas como documenta la clase.

        `umbrales_wot` y `permanencia_wot_base` no salen de `mapa`: son los
        objetos que quien llama ya tiene para la segmentación (ver la clase).

        `lanzamiento_activo_min` se lee de `mapa` SOLO si está presente -- no es
        una de las claves exigidas, así que un mapa sin ella construye el
        umbral con `None` (LANZAMIENTO no calculable) en vez de fallar. El día
        que `data/umbrales.toml` declare una sección `[anclaje]` con ese
        número, funciona sin tocar este módulo.
        """
        faltan = [c for c in _CLAVES_ESCALARES if c not in mapa]
        if faltan:
            raise ErrorDeAnclaje(
                "el mapa de umbrales de anclaje no declara: "
                + ", ".join(faltan)
                + "; ver `UmbralesDeAnclaje` para de qué sección de data/umbrales.toml sale "
                "cada una (D14 y [motor_de_deteccion])"
            )
        lanzamiento = mapa.get("lanzamiento_activo_min")
        return cls(
            corte_umbral_min=float(mapa["corte_umbral_min"]),
            maximo_de_eventos=int(mapa["maximo_de_eventos"]),
            umbrales_wot=umbrales_wot,
            permanencia_wot_base=permanencia_wot_base,
            lanzamiento_activo_min=float(lanzamiento) if lanzamiento is not None else None,
        )


# --------------------------------------------------------------------------- #
# Resultado
# --------------------------------------------------------------------------- #
class MotivoSinAncla(Enum):
    """Por qué un segmento se queda fuera del eje por evento.

    TRES estados, mismo criterio que `exclusion.FiltroNoAplicado` y
    `activacion_detectores.EstadoDetector` (docs/07 §7.15): «rol ausente» y
    «rol sin confirmar» son dos acciones distintas para el usuario, y
    `EVENTO_NO_OCURRIDO` es la tercera cosa que puede pasar y la que esta
    tarea existe para no confundir con un desfase de 0.
    """

    ROL_AUSENTE = "rol_ausente"
    """El segmento no trae el canal. No hay nada que confirmar."""

    ROL_SIN_CONFIRMAR = "rol_sin_confirmar"
    """El rol viene de una coincidencia DIFUSA sin confirmar (docs/07 §7.15).
    El usuario lo arregla confirmando el rol."""

    EVENTO_NO_OCURRIDO = "evento_no_ocurrido"
    """El rol está y está confirmado, pero el evento nunca ocurrió en este
    segmento: el log no llegó a WOT, no tuvo corte, o no activó el
    lanzamiento. Es EL caso que decide la tarea (ver la cabecera del módulo)."""


@dataclass(slots=True, frozen=True)
class SegmentoSinAncla:
    """Un segmento excluido del eje por evento, con el motivo exacto."""

    id_segmento: str
    motivo: MotivoSinAncla
    roles_ausentes: tuple[str, ...] = ()
    roles_sin_confirmar: tuple[str, ...] = ()

    @property
    def descripcion(self) -> str:
        """Frase lista para el informe o el panel, con los roles por nombre."""
        if self.motivo is MotivoSinAncla.ROL_AUSENTE:
            return (
                f"el segmento '{self.id_segmento}' no trae {_lista(self.roles_ausentes)}: el "
                "ancla no se puede buscar, no se aproxima con otro canal"
            )
        if self.motivo is MotivoSinAncla.ROL_SIN_CONFIRMAR:
            return (
                f"en el segmento '{self.id_segmento}', {_lista(self.roles_sin_confirmar)} viene "
                "de una coincidencia sin confirmar: el ancla no se calcula hasta que se "
                "confirme el rol, para no alinear a ciegas por una conjetura (docs/07 §7.15)"
            )
        return (
            f"el segmento '{self.id_segmento}' no tiene el evento: nunca ocurrió en este log. "
            "No se alinea con un desfase de 0 -- eso lo superpondría con los demás como si "
            "estuviera alineado, sin estarlo"
        )


def _lista(nombres: tuple[str, ...]) -> str:
    """«el rol x» o «los roles x, y». Copiado y no importado de
    `exclusion._lista`/`activacion_detectores._lista`: ayudante de formato de
    texto sin ninguna decisión que compartir."""
    if len(nombres) == 1:
        return f"el rol {nombres[0]}"
    return f"los roles {', '.join(nombres)}"


@dataclass(slots=True, frozen=True)
class InformeDeAnclaje:
    """Lo que devuelve `ancla_por_evento`: el eje, los instantes del ancla y lo
    que se quedó fuera."""

    tipo_ancla: TipoAncla

    eje: EjeVirtual | None
    """El eje `POR_EVENTO` de los segmentos que SÍ tienen el ancla. `None`
    cuando ninguno la tiene: no hay nada que alinear, y un eje de longitud
    cero no lo admite `tiempo.EjeVirtual`."""

    instantes_ancla_ms: Mapping[str, float]
    """El instante local del ancla (ms desde el t0 de CADA segmento, la misma
    rejilla que `primitivas.Serie.t_ms`), solo para los segmentos de `eje`."""

    sin_ancla: tuple[SegmentoSinAncla, ...]

    def tiene_ancla(self, id_segmento: str) -> bool:
        return id_segmento in self.instantes_ancla_ms


# --------------------------------------------------------------------------- #
# Cálculo
# --------------------------------------------------------------------------- #
def _numpy() -> Vectorial:
    """Importa NumPy en el momento de usarlo, igual que `primitivas._numpy`,
    `segmentacion._numpy` y `exclusion._numpy`: así este módulo se puede
    importar y probar sin NumPy instalado."""
    import numpy

    return cast("Vectorial", numpy)


def _xp(xp: Vectorial | None) -> Vectorial:
    return xp if xp is not None else _numpy()


def _comprobar_serie_punto(serie: Serie, rol: str) -> None:
    if serie.clase is not Clase.PUNTO:
        raise ErrorDeAnclaje(
            f"la serie del rol {rol} es de clase {serie.clase.value} y tiene que ser PUNTO: "
            "un canal tal como sale del almacén es un punto, y una derivada o un intervalo ya "
            "calculados comparados con un umbral de canal son la trampa del delta"
        )


def _instante_primer_evento_ms(
    serie: Serie, rol: str, umbral_min: float, maximo_de_eventos: int, *, xp: Vectorial
) -> float | None:
    """El `t_inicio_ms` del primer instante en que `serie >= umbral_min`, o
    `None` si nunca ocurre. Vale para CORTE (`cut_percentage`) y LANZAMIENTO
    (`launch_state`): los dos son códigos de estado directos de la ECU, ver
    `_PERMANENCIA_CANAL_DE_ESTADO_S` en la cabecera del módulo.
    """
    _comprobar_serie_punto(serie, rol)
    condicion = umbral_con_histeresis(
        serie, entrada=umbral_min, salida=umbral_min, direccion=Direccion.ARRIBA, xp=xp
    )
    permanencia = Permanencia(
        permanencia_s=_PERMANENCIA_CANAL_DE_ESTADO_S,
        muestras_minimas=_MUESTRAS_MINIMAS_CANAL_DE_ESTADO,
        maximo_de_eventos=maximo_de_eventos,
    )
    lista = eventos(condicion, permanencia=permanencia, xp=xp)
    return lista[0].t_inicio_ms if lista else None


def _instante_primer_wot_ms(
    series: Mapping[str, Serie], umbrales: UmbralesDeAnclaje, *, xp: Vectorial
) -> float | None:
    """El `t_inicio_ms` del primer segmento WOT que encuentra
    `segmentacion.segmentar`, o `None` si el log nunca llega a WOT (los dos
    logs internos de `samples/real/`, ver la cabecera del módulo)."""
    informe = segmentar(
        series,
        umbrales=umbrales.umbrales_wot,
        permanencia_base=umbrales.permanencia_wot_base,
        xp=xp,
    )
    primeros = informe.de_clase(ClaseDeSegmento.WOT)
    return primeros[0].t_inicio_ms if primeros else None


def _instante_ancla_ms(
    tipo_ancla: TipoAncla,
    series: Mapping[str, Serie],
    umbrales: UmbralesDeAnclaje,
    *,
    xp: Vectorial,
) -> float | None:
    if tipo_ancla is TipoAncla.PRIMER_WOT:
        return _instante_primer_wot_ms(series, umbrales, xp=xp)
    if tipo_ancla is TipoAncla.PRIMER_CORTE:
        return _instante_primer_evento_ms(
            series[ROL_CORTE],
            ROL_CORTE,
            umbrales.corte_umbral_min,
            umbrales.maximo_de_eventos,
            xp=xp,
        )
    if tipo_ancla is TipoAncla.LANZAMIENTO:
        # `ancla_por_evento` ya ha comprobado que `lanzamiento_activo_min` no
        # es `None` antes de llegar aquí.
        activo_min = cast("float", umbrales.lanzamiento_activo_min)
        return _instante_primer_evento_ms(
            series[ROL_LANZAMIENTO], ROL_LANZAMIENTO, activo_min, umbrales.maximo_de_eventos, xp=xp
        )
    raise ErrorDeAnclaje(f"tipo de ancla no contemplado: {tipo_ancla}")  # pragma: no cover


def _comprobar_ids_unicos(segmentos: Sequence[SegmentoDeLog]) -> None:
    vistos: set[str] = set()
    for s in segmentos:
        if s.id in vistos:
            raise ErrorDeAnclaje(
                f"el id de segmento '{s.id}' está repetido: un ancla indexada por id "
                "heredaría el instante del otro segmento sin que nada lo dijera"
            )
        vistos.add(s.id)


def ancla_por_evento(
    segmentos: Sequence[SegmentoDeLog],
    series_por_segmento: Mapping[str, Mapping[str, Serie]],
    *,
    tipo_ancla: TipoAncla,
    umbrales: UmbralesDeAnclaje,
    roles_sin_confirmar: Mapping[str, frozenset[str]] | None = None,
    xp: Vectorial | None = None,
) -> InformeDeAnclaje:
    """Busca `tipo_ancla` en cada segmento y calcula el eje `POR_EVENTO`.

    :param segmentos: los `tiempo.Segmento` a alinear (la identidad temporal de
        cada log, F2-01). No vacío.
    :param series_por_segmento: para cada `id` de `segmentos`, el mapa de
        **rol semántico** a serie en unidad canónica de ESE log (ya resuelto
        por `identidad.py`). Un segmento ausente de este mapa se trata como si
        no trajera ningún rol.
    :param roles_sin_confirmar: para cada `id` de `segmentos`, los roles de ESE
        log que vienen de una coincidencia DIFUSA sin confirmar
        (`roles.Asignacion.requiere_confirmacion`, FG-09). Por omisión,
        ninguno. Es por segmento y no una única lista global porque la
        confianza de un rol es una propiedad de cada log (ver la cabecera del
        módulo).

    No lanza excepción por un log raro: un rol ausente, un rol sin confirmar o
    un evento que nunca ocurrió hacen que ese segmento aparezca en
    `InformeDeAnclaje.sin_ancla` en vez de entrar en el eje con un desfase
    inventado. SÍ lanza `ErrorDeAnclaje` por un uso incorrecto: lista de
    segmentos vacía, `TipoAncla.LANZAMIENTO` sin `lanzamiento_activo_min`, o
    una serie que no es `Clase.PUNTO`.
    """
    if not segmentos:
        raise ErrorDeAnclaje("no hay ningún segmento: no hay eje que construir")
    _comprobar_ids_unicos(segmentos)
    if tipo_ancla is TipoAncla.LANZAMIENTO and umbrales.lanzamiento_activo_min is None:
        raise ErrorDeAnclaje(
            "TipoAncla.LANZAMIENTO pide `lanzamiento_activo_min`, y no está definido. El "
            "proyecto no tiene un valor documentado ni medido de qué código de `launch_state` "
            "significa 'activo' (docs/01 §1.10 solo da el rango −101…1); este módulo no lo "
            "adivina (regla 3 de CLAUDE.md). Pásalo explícitamente si conoces el código de tu "
            "ECU en concreto, o declara `[anclaje].lanzamiento_activo_min` en "
            "data/umbrales.toml el día que lo midas."
        )

    xp = _xp(xp)
    confirmaciones = roles_sin_confirmar or {}

    instantes_ms: dict[str, float] = {}
    sin_ancla: list[SegmentoSinAncla] = []
    for s in segmentos:  # bucle sobre SEGMENTOS (unos pocos logs), no sobre muestras
        series = series_por_segmento.get(s.id, {})
        no_confirmados = confirmaciones.get(s.id, frozenset())
        ausentes = tuple(r for r in tipo_ancla.roles_requeridos if r not in series)
        # Un rol ausente no está «sin confirmar»: no está. Mismo criterio que
        # `exclusion.excluir`.
        pendientes = tuple(
            r for r in tipo_ancla.roles_requeridos if r in no_confirmados and r not in ausentes
        )
        if ausentes:
            sin_ancla.append(
                SegmentoSinAncla(s.id, MotivoSinAncla.ROL_AUSENTE, roles_ausentes=ausentes)
            )
            continue
        if pendientes:
            sin_ancla.append(
                SegmentoSinAncla(
                    s.id, MotivoSinAncla.ROL_SIN_CONFIRMAR, roles_sin_confirmar=pendientes
                )
            )
            continue

        instante_ms = _instante_ancla_ms(tipo_ancla, series, umbrales, xp=xp)
        if instante_ms is None:
            sin_ancla.append(SegmentoSinAncla(s.id, MotivoSinAncla.EVENTO_NO_OCURRIDO))
            continue
        instantes_ms[s.id] = instante_ms

    if not instantes_ms:
        return InformeDeAnclaje(
            tipo_ancla=tipo_ancla, eje=None, instantes_ancla_ms={}, sin_ancla=tuple(sin_ancla)
        )

    anclados = tuple(s for s in segmentos if s.id in instantes_ms)
    # x = t_local + desfase; se elige desfase(s) = -t_ancla_local(s) para que
    # el ancla caiga en x = 0 en TODOS los segmentos anclados (ver la cabecera
    # del módulo, «Dónde cae el ancla»).
    desfases = {s.id: -(instantes_ms[s.id] / MS_POR_S) for s in anclados}
    eje = EjeVirtual(
        modo=ModoDesfase.POR_EVENTO, segmentos=anclados, desfases=desfases, concatenado=False
    )
    return InformeDeAnclaje(
        tipo_ancla=tipo_ancla,
        eje=eje,
        instantes_ancla_ms=dict(instantes_ms),
        sin_ancla=tuple(sin_ancla),
    )
