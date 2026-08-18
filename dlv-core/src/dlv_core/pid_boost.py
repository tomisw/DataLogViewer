"""Métricas de PID de boost por transitorio (tarea F4-09).

Especificación: `docs/04-perfiles-motorsport.md` §4.2 P3 («sobreoscilación,
tiempo de establecimiento al ±3 %, error estacionario») y §4.3, D7
(«sobreoscilación de boost: pico > objetivo + 5 % TRAS UNA SUBIDA»). D7 está
declarado en `data/umbrales.toml` desde F0-07 con
`sobreoscilacion_relativa_max = 0.05`, pero no se podía evaluar: nada delimitaba
qué es «una subida» ni «tras». Este módulo es esa delimitación.

QUÉ ES UN TRANSITORIO, Y POR QUÉ HAY QUE DELIMITARLO ANTES DE MEDIRLO
======================================================================
Sobreoscilación, establecimiento y error en régimen son propiedades de UN
escalón del objetivo (`boost_pressure_target`), no del log entero. Sin
delimitarlo, «el error medio del log» mezcla el propio transitorio —donde el
error es grande por definición— con el régimen permanente, y sale bajo por
promediar lo que no hay que promediar (ver más abajo). Un transitorio es:

1. **Un escalón ascendente del objetivo.** Se detecta la diferencia entre
   muestras consecutivas del objetivo (`_delta_simple`, INTERVALO) y se busca
   dónde esa diferencia supera `escalon_minimo_kpa` con
   `primitivas.umbral_con_histeresis` + `primitivas.eventos`: es la misma
   maquinaria que detecta cualquier otro evento en este proyecto, no una nueva.
   Un escalón DESCENDENTE se detecta igual, con la dirección al revés, pero NO
   se mide: D7 pide «tras una subida», y una sobreoscilación por debajo de un
   objetivo que baja es un fenómeno distinto (una caída de presión, no un
   sobrepaso) que esta tarea no pide. Se cuenta como `BAJADA` en
   `InformeTransitoriosBoost.descartados` para que «cero transitorios» nunca se
   confunda con «no había ningún escalón en el log»: las dos cosas se
   distinguen mirando `n_escalones_totales`.
2. **Acotado por el SIGUIENTE escalón (de cualquier dirección) o por el final
   del segmento.** Es el horizonte de búsqueda: nada de lo que pase después de
   que el objetivo vuelva a cambiar pertenece a ESTE transitorio.
3. **Válido solo si el lazo llega a establecerse dentro de ese horizonte.** Si
   el objetivo cambia otra vez mientras el lazo todavía persigue el anterior —o
   si el segmento se acaba antes de que se establezca—, la medida se descarta
   ENTERA (sobreoscilación incluida), no a medias: medir el error en régimen de
   un transitorio que nunca llegó a régimen es inventar un número con forma de
   dato. `MotivoTransitorioDescartado` dice cuál de las dos cosas pasó.

CÓMO SE DECIDE «ESTABLECIDO»
=============================
El establecimiento se define como en `docs/04` §4.2 P3: la primera vez que la
señal entra en la banda `objetivo ± banda_establecimiento_relativa` y **ya no
vuelve a salir** dentro del horizonte del transitorio. En vez de reimplementar
esa búsqueda a mano, se reutilizan las primitivas que ya la resuelven:

* `primitivas.banda` construye la condición «dentro de la banda», con su propia
  histéresis para no confundir el ruido de cuantización justo en el borde del
  3 % con una salida de verdad.
* `primitivas.eventos`, con una `Permanencia` («al menos
  `permanencia_establecimiento_s` Y `muestras_minimas_establecimiento`»),
  encuentra las carreras de «dentro» que duran lo bastante para no ser un roce.
* El transitorio se considera establecido si y solo si UNA de esas carreras
  llega hasta la ÚLTIMA muestra del horizonte: eso es exactamente «entra y no
  vuelve a salir antes de que el objetivo cambie o el log se acabe». Si ninguna
  carrera llega hasta ahí, no hay establecimiento que afirmar.

Es la misma razón por la que `primitivas.eventos` interrumpe una carrera en un
hueco (`docs/04` §4.5): una carrera de «dentro» que atraviesa un hueco de datos
se rompe en dos, así que el establecimiento que este módulo certifica nunca
tiene un hueco escondido dentro.

POR QUÉ EL ERROR EN RÉGIMEN NO SE PROMEDIA SOBRE TODO EL TRANSITORIO
=====================================================================
El tramo de subida tiene, por construcción, un error grande (todavía no ha
llegado al objetivo) y luego uno que cambia de signo (la sobreoscilación). Un
promedio sobre ESE tramo más el régimen permanente da un número que no es ni lo
uno ni lo otro y que además sale artificialmente bajo -- exactamente la trampa
que la tarea pide evitar. Por eso `error_regimen_kpa` se calcula EXCLUSIVAMENTE
sobre la carrera de «dentro» que certifica el establecimiento: son las muestras
que, ya se ha comprobado, están todas dentro de la banda y sin huecos.

LA CLASE DE MAGNITUD DE CADA NÚMERO
====================================
Regla 4 de `CLAUDE.md`. Cada campo de `TransitorioBoost` dice en su comentario
qué `Clase` le corresponde, siguiendo el mismo criterio que
`marcha.MarchaDetectada.cociente` (un campo documentado, no un envoltorio en
tiempo de ejecución, porque la clase de cada campo es FIJA por construcción y
no varía con el dato como sí varía `Evento.clase_valor`):

* `escalon_kpa`, `sobreoscilacion_absoluta_kpa` y `error_regimen_kpa` son
  DIFERENCIAS de presión → `Clase.INTERVALO`. Confundirlas con `PUNTO` es la
  trampa del delta: 10 kPa de sobreoscilación convertidos como un punto en la
  unidad activa saldrían con el desplazamiento de origen de esa unidad, que
  para la presión relativa (`docs/06` §6.13) no es cero.
* `objetivo_anterior_kpa`, `objetivo_nuevo_kpa` y `pico_actual_kpa` son valores
  absolutos del canal → `Clase.PUNTO`.
* `sobreoscilacion_relativa` y `error_regimen_relativo` son fracciones del
  objetivo, en la dimensión `ratio` de `data/units.toml` (canónica: fracción,
  no porcentaje) → `Clase.PUNTO` sobre esa dimensión: son un valor —«cuánto por
  encima», «qué fracción de error queda»—, no una diferencia entre dos
  fracciones. Es la misma familia que `[detectores.D7].sobreoscilacion_
  relativa_max` en `data/umbrales.toml`, que ya está declarada como fracción.
* `tiempo_establecimiento_s` es una DURACIÓN → `Clase.INTERVALO`. En la
  dimensión de tiempo canónica (segundos) todas las conversiones son lineales
  sin desplazamiento de origen, así que numéricamente PUNTO e INTERVALO
  coinciden hoy -- pero declararlo INTERVALO es lo que no depende de que eso
  siga siendo verdad si algún día se añade una unidad de tiempo con origen
  desplazado, y es lo que pide expresamente esta tarea.

LOS UMBRALES SON CONFIGURABLES (regla 3 de `CLAUDE.md`)
=========================================================
Ninguno vive en este módulo: `UmbralesPidBoost.desde_mapa` exige las siete
claves de `data/umbrales.toml` `[boost_pid]` y falla si falta alguna, con la
derivación de cada una escrita en el propio fichero.

ADR-009: CERO BUCLES POR MUESTRA
==================================
Las dos detecciones de escalón (subida y bajada) son `umbral_con_histeresis` +
`eventos`, vectorizadas por `primitivas.py`. El establecimiento es `banda` +
`eventos` sobre la ventana de CADA transitorio, también vectorizado. El único
bucle de este módulo recorre los ESCALONES detectados —acotado por
`maximo_de_transitorios`—, no las muestras: el mismo patrón, con la misma
justificación, que el bucle sobre eventos de `primitivas.eventos` y el bucle
sobre marchas de `marcha.detectar_marchas`.

Este módulo no abre ficheros (ADR-002) y no conoce D7 ni ningún otro detector:
produce los números que D7 necesita («esto es un transitorio, esto es su
sobreoscilación»); decidir que 0,05 es demasiado y avisar es trabajo de F3-07,
que todavía no está escrito (`detectores.py` solo tiene el contrato `Detector`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from dlv_core.primitivas import (
    Direccion,
    Evento,
    Permanencia,
    Serie,
    Vectorial,
    banda,
    eventos,
    umbral_con_histeresis,
)
from dlv_core.unidades import Clase

__all__ = [
    "ErrorDePidBoost",
    "InformeTransitoriosBoost",
    "MotivoTransitorioDescartado",
    "TransitorioBoost",
    "UmbralesPidBoost",
    "medir_transitorios_boost",
]

MS_POR_S = 1000.0
"""Milisegundos por segundo. Mismo valor y mismo motivo que en `primitivas.py`:
`t_ms` está en milisegundos y los umbrales de tiempo de `data/umbrales.toml`
están en segundos (unidad canónica de tiempo, `docs/06`)."""


class ErrorDePidBoost(ValueError):
    """Uso incorrecto del módulo, o una configuración que no se puede aplicar.

    No es un resultado de la medición -- un log sin transitorios no produce
    esta excepción, produce un `InformeTransitoriosBoost` vacío con el motivo
    escrito. Esto otro (series en rejillas distintas, una clase de conversión
    equivocada, un objetivo que pasa por cero) es un fallo de quien llama.
    """


class MotivoTransitorioDescartado(Enum):
    """Por qué un escalón detectado no produjo una medida. Nunca sin motivo:
    un transitorio descartado en silencio es indistinguible de uno que nunca
    existió, y son dos hechos distintos sobre el log."""

    BAJADA = "bajada"
    """El objetivo bajó, no subió. D7 pide «tras una subida» y una
    sobreoscilación por debajo de un objetivo que cae es un fenómeno físico
    distinto (una caída de presión). No se mide, se cuenta."""

    INTERRUMPIDO_POR_OTRO_ESCALON = "interrumpido_por_otro_escalon"
    """El objetivo volvió a cambiar antes de que el lazo se estableciera sobre
    este escalón. Medir hasta ahí sería medir un régimen que nunca existió."""

    SIN_ESTABLECER_AL_FINAL_DEL_SEGMENTO = "sin_establecer_al_final_del_segmento"
    """El segmento (o el log) terminó antes de que el lazo se estableciera.
    No es necesariamente un fallo del lazo: puede ser, sin más, que el log
    termine a mitad del transitorio."""


# --------------------------------------------------------------------------- #
# Umbrales configurables (data/umbrales.toml, sección [boost_pid])
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class UmbralesPidBoost:
    """Los umbrales de este módulo. **Sin valores por omisión en el código**
    (regla 3 de `CLAUDE.md`): viven en `data/umbrales.toml` `[boost_pid]`.
    `desde_mapa` exige las siete claves y falla si falta alguna."""

    escalon_minimo_kpa: float
    """Diferencia mínima entre dos muestras consecutivas del objetivo para que
    cuente como un escalón (subida o bajada). Por debajo de esto es
    cuantización del canal, no una orden nueva del lazo."""

    banda_establecimiento_relativa: float
    """Semiancho de la banda de establecimiento, en fracción del objetivo
    nuevo. `docs/04` §4.2 P3 lo declara literalmente: «al ±3 %»."""

    histeresis_banda_relativa: float
    """Histéresis de `primitivas.banda` sobre esa banda, en fracción de su
    anchura. Evita que el ruido de cuantización justo en el borde del 3 % se
    cuente como una salida y vuelva a entrar."""

    permanencia_establecimiento_s: float
    """Cuánto tiempo tiene que durar la carrera de «dentro de banda» para
    contar como establecimiento y no como un roce de paso."""

    muestras_minimas_establecimiento: int
    """Y cuántas muestras, como mínimo, para lo mismo. Las dos condiciones a
    la vez, igual que `primitivas.Permanencia`: el objetivo puede estar en
    G1 (9,8 Hz) o en un grupo más lento tras alinear."""

    maximo_de_eventos_internos: int
    """Tope de eventos de las llamadas internas a `primitivas.eventos`
    (detección de escalones, y carreras de «dentro» por transitorio). No es
    física: es la salvaguarda que mantiene acotadas esas llamadas."""

    maximo_de_transitorios: int
    """Tope de escalones (subida + bajada) que este módulo procesa de una sola
    vez. Acota el único bucle de Python del módulo (ADR-009) y convierte una
    configuración que genera ruido -- `escalon_minimo_kpa` demasiado pequeño --
    en un error explicado en vez de en miles de transitorios que nadie mediría."""

    CLAVES = (
        "escalon_minimo_kpa",
        "banda_establecimiento_relativa",
        "histeresis_banda_relativa",
        "permanencia_establecimiento_s",
        "muestras_minimas_establecimiento",
        "maximo_de_eventos_internos",
        "maximo_de_transitorios",
    )

    @classmethod
    def desde_mapa(cls, mapa: Mapping[str, Any]) -> UmbralesPidBoost:
        faltan = [c for c in cls.CLAVES if c not in mapa]
        if faltan:
            raise ErrorDePidBoost(
                "data/umbrales.toml no declara: "
                + ", ".join(faltan)
                + "; son umbrales configurables de [boost_pid] y este módulo no lleva "
                "copia de ellos"
            )
        u = cls(
            escalon_minimo_kpa=float(mapa["escalon_minimo_kpa"]),
            banda_establecimiento_relativa=float(mapa["banda_establecimiento_relativa"]),
            histeresis_banda_relativa=float(mapa["histeresis_banda_relativa"]),
            permanencia_establecimiento_s=float(mapa["permanencia_establecimiento_s"]),
            muestras_minimas_establecimiento=int(mapa["muestras_minimas_establecimiento"]),
            maximo_de_eventos_internos=int(mapa["maximo_de_eventos_internos"]),
            maximo_de_transitorios=int(mapa["maximo_de_transitorios"]),
        )
        u.validar()
        return u

    def validar(self) -> None:
        if self.escalon_minimo_kpa <= 0.0:
            raise ErrorDePidBoost("escalon_minimo_kpa tiene que ser positivo")
        if not 0.0 < self.banda_establecimiento_relativa < 1.0:
            raise ErrorDePidBoost(
                f"banda_establecimiento_relativa = {self.banda_establecimiento_relativa!r} "
                "tiene que estar entre 0 y 1: es una fracción del objetivo"
            )
        if not 0.0 <= self.histeresis_banda_relativa < 1.0:
            raise ErrorDePidBoost(
                f"histeresis_banda_relativa = {self.histeresis_banda_relativa!r} tiene que "
                "ser una fracción en [0, 1) de la anchura de la banda; con 1 el margen sería "
                "la banda entera (mismo motivo que `primitivas.banda`)"
            )
        if self.permanencia_establecimiento_s < 0.0:
            raise ErrorDePidBoost("permanencia_establecimiento_s no puede ser negativa")
        if self.muestras_minimas_establecimiento < 1:
            raise ErrorDePidBoost("muestras_minimas_establecimiento tiene que ser >= 1")
        if self.maximo_de_eventos_internos < 1:
            raise ErrorDePidBoost("maximo_de_eventos_internos tiene que ser >= 1")
        if self.maximo_de_transitorios < 1:
            raise ErrorDePidBoost("maximo_de_transitorios tiene que ser >= 1")


# --------------------------------------------------------------------------- #
# Resultado
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class TransitorioBoost:
    """Un escalón ascendente del objetivo, medido de principio a
    establecimiento. Ver la cabecera del módulo para la clase de cada campo."""

    t_inicio_ms: float
    """Instante de la primera muestra en la que el objetivo empezó a subir."""

    t_fin_ms: float
    """Última muestra del horizonte de búsqueda (el siguiente escalón, o el
    final del segmento)."""

    i_inicio: int
    i_fin: int

    objetivo_anterior_kpa: float
    """`Clase.PUNTO`. El objetivo justo antes de este escalón."""

    objetivo_nuevo_kpa: float
    """`Clase.PUNTO`. El objetivo una vez completado el escalón; es la
    referencia de la sobreoscilación, la banda de establecimiento y el error
    en régimen."""

    escalon_kpa: float
    """`Clase.INTERVALO`. `objetivo_nuevo_kpa - objetivo_anterior_kpa`."""

    pico_actual_kpa: float
    """`Clase.PUNTO`. El máximo de `boost_pressure_actual` observado en todo
    el horizonte de este transitorio."""

    sobreoscilacion_absoluta_kpa: float
    """`Clase.INTERVALO`. `pico_actual_kpa - objetivo_nuevo_kpa`. Puede salir
    negativo -- el pico no llegó a superar el objetivo -- y eso es información
    válida: un lazo que no sobreoscila, no uno que «no se puede medir»."""

    sobreoscilacion_relativa: float
    """`Clase.PUNTO` en la dimensión `ratio` (fracción, no porcentaje).
    `sobreoscilacion_absoluta_kpa / objetivo_nuevo_kpa`. Es la magnitud que
    compara directamente contra `[detectores.D7].sobreoscilacion_relativa_max`."""

    tiempo_establecimiento_s: float
    """`Clase.INTERVALO`. Desde el inicio del escalón hasta la primera muestra
    de la carrera final dentro de la banda de establecimiento."""

    error_regimen_kpa: float
    """`Clase.INTERVALO`. Media de `actual - objetivo` sobre la carrera que
    certifica el establecimiento, y SOLO sobre ella (ver la cabecera:
    promediar el transitorio entero da un número falsamente bajo)."""

    error_regimen_relativo: float
    """`Clase.PUNTO` en la dimensión `ratio`. `error_regimen_kpa /
    objetivo_nuevo_kpa`."""

    n_muestras_regimen: int
    """Cuántas muestras respaldan `error_regimen_kpa`. Con pocas, el número es
    tan bueno como poco robusto frente al ruido -- se reporta para que quien
    lea el informe pueda juzgarlo, no se oculta."""


@dataclass(slots=True, frozen=True)
class InformeTransitoriosBoost:
    """El resultado completo de `medir_transitorios_boost` sobre un segmento."""

    transitorios: tuple[TransitorioBoost, ...]
    """Solo los escalones ascendentes que se pudieron medir de principio a
    establecimiento. Vacía no significa «sin sobreoscilación»: puede significar
    «sin escalones» o «todos descartados» -- mira `n_escalones_totales` y
    `descartados` para distinguirlas."""

    descartados: Mapping[MotivoTransitorioDescartado, int]
    """Cuántos escalones no produjeron una medida, y por qué. Las tres claves
    del enum están siempre presentes, con 0 si no aplican -- igual que
    `marcha.InformeDeMarchas.motivos`."""

    n_escalones_totales: int
    """Escalones detectados en total (ascendentes + descendentes), antes de
    filtrar nada. Es lo que distingue «el objetivo no cambió en todo el
    segmento» (0) de «cambió, pero nada se pudo medir» (> 0 con
    `transitorios` vacío)."""


# --------------------------------------------------------------------------- #
# Piezas internas
# --------------------------------------------------------------------------- #
def _xp(xp: Vectorial | None) -> Vectorial:
    """El doble inyectado, o NumPy. Mismo criterio que `primitivas._xp`: se
    importa NumPy solo si hace falta, para poder probar y usar este módulo sin
    tenerlo instalado."""
    if xp is not None:
        return xp
    import numpy

    return cast("Vectorial", numpy)


def _no(mascara: Any) -> Any:
    """Negación elemento a elemento. `== 0` y no `~`, por el mismo motivo que
    en `primitivas._no`: no todo doble de `Vectorial` define `~`."""
    return mascara == 0


def _valido_de(serie: Serie) -> Any:
    """La máscara de validez de una serie, materializada. Mismo truco que
    `primitivas._valido_de`: `t == t` es todo `True` sin pedirle `ones` al
    protocolo."""
    if serie.valido is not None:
        return serie.valido
    return serie.t_ms == serie.t_ms


def _misma_rejilla(a: Serie, b: Serie, *, xp: Vectorial) -> None:
    """Dos series solo se combinan si están en la misma rejilla de tiempo.
    Mismo criterio que `primitivas._misma_rejilla`: la longitud no basta, dos
    grupos de muestreo distintos pueden compartir cuántas muestras sin
    compartir cuáles."""
    if len(a) != len(b):
        raise ErrorDePidBoost(
            f"actual y objetivo tienen rejillas distintas ({len(a)} y {len(b)} muestras); "
            "alinéalas antes con `primitivas.alinear`"
        )
    if a.t_ms is b.t_ms:
        return
    if int(xp.sum(a.t_ms != b.t_ms)) != 0:
        raise ErrorDePidBoost(
            "actual y objetivo tienen el mismo número de muestras pero en instantes "
            "distintos; alinéalas antes con `primitivas.alinear`"
        )


def _delta_simple(serie: Serie, *, xp: Vectorial) -> Serie:
    """`v[i] - v[i-1]`, sin la semántica de contador de
    `primitivas.delta_de_contador` (que invalida un delta negativo asumiendo un
    contador que solo sube). El objetivo de boost sube y baja los dos con
    sentido físico, así que aquí un delta negativo es un dato, no un reinicio.

    Clase `INTERVALO` (regla 4): es una diferencia entre dos puntos."""
    if serie.clase is not Clase.PUNTO:
        raise ErrorDePidBoost(
            f"el objetivo tiene que ser de clase PUNTO, no {serie.clase.value}: es un "
            "valor absoluto del canal"
        )
    n = len(serie)
    idx = xp.arange(n)
    primera = idx == 0
    anterior = idx - 1 + primera
    delta = serie.v - serie.v[anterior]
    validez = _valido_de(serie)
    return Serie(
        t_ms=serie.t_ms,
        v=delta,
        clase=Clase.INTERVALO,
        valido=validez & validez[anterior] & _no(primera),
    )


def medir_transitorios_boost(
    actual: Serie,
    objetivo: Serie,
    *,
    umbrales: UmbralesPidBoost,
    xp: Vectorial | None = None,
) -> InformeTransitoriosBoost:
    """Delimita y mide los transitorios de un lazo de boost.

    `actual` (`boost_pressure_actual`) y `objetivo` (`boost_pressure_target`)
    tienen que estar en la MISMA rejilla de tiempo -- alineados con
    `primitivas.alinear` por quien llame, igual que exige `primitivas.banda`
    para sus operandos -- y los dos en `Clase.PUNTO`: son valores absolutos del
    canal, no diferencias.

    Ver la cabecera del módulo para la definición completa de transitorio, de
    establecimiento y de por qué el error en régimen no se promedia sobre todo
    el transitorio.
    """
    xp = _xp(xp)
    if actual.clase is not Clase.PUNTO:
        raise ErrorDePidBoost(
            f"boost_pressure_actual tiene que ser de clase PUNTO, no {actual.clase.value}"
        )
    if objetivo.clase is not Clase.PUNTO:
        raise ErrorDePidBoost(
            f"boost_pressure_target tiene que ser de clase PUNTO, no {objetivo.clase.value}"
        )
    _misma_rejilla(actual, objetivo, xp=xp)

    n = len(actual)
    if n == 0:
        return InformeTransitoriosBoost(
            transitorios=(),
            descartados=dict.fromkeys(MotivoTransitorioDescartado, 0),
            n_escalones_totales=0,
        )

    delta = _delta_simple(objetivo, xp=xp)
    permanencia_deteccion = Permanencia(
        permanencia_s=0.0,
        muestras_minimas=1,
        maximo_de_eventos=umbrales.maximo_de_eventos_internos,
    )
    subida = umbral_con_histeresis(
        delta,
        entrada=umbrales.escalon_minimo_kpa,
        salida=umbrales.escalon_minimo_kpa,
        direccion=Direccion.ARRIBA,
        xp=xp,
    )
    bajada = umbral_con_histeresis(
        delta,
        entrada=-umbrales.escalon_minimo_kpa,
        salida=-umbrales.escalon_minimo_kpa,
        direccion=Direccion.ABAJO,
        xp=xp,
    )
    escalones_subida = eventos(subida, permanencia=permanencia_deteccion, xp=xp)
    escalones_bajada = eventos(bajada, permanencia=permanencia_deteccion, xp=xp)

    escalones = sorted(
        [(e.i_inicio, e.i_fin, True) for e in escalones_subida]
        + [(e.i_inicio, e.i_fin, False) for e in escalones_bajada],
        key=lambda tripleta: tripleta[0],
    )
    n_escalones_totales = len(escalones)
    if n_escalones_totales > umbrales.maximo_de_transitorios:
        raise ErrorDePidBoost(
            f"se detectaron {n_escalones_totales} escalones del objetivo y el tope es "
            f"{umbrales.maximo_de_transitorios}: sube `escalon_minimo_kpa` (el umbral está "
            "cazando ruido de cuantización, no órdenes del lazo) o sube el tope si de "
            "verdad hacen falta tantos"
        )

    permanencia_establecida = Permanencia(
        permanencia_s=umbrales.permanencia_establecimiento_s,
        muestras_minimas=umbrales.muestras_minimas_establecimiento,
        maximo_de_eventos=umbrales.maximo_de_eventos_internos,
    )

    transitorios: list[TransitorioBoost] = []
    descartados: dict[MotivoTransitorioDescartado, int] = dict.fromkeys(
        MotivoTransitorioDescartado, 0
    )

    for k in range(n_escalones_totales):  # bucle sobre ESCALONES, no sobre muestras (ADR-009)
        i_inicio, i_fin, es_subida = escalones[k]
        if not es_subida:
            descartados[MotivoTransitorioDescartado.BAJADA] += 1
            continue

        horizonte = escalones[k + 1][0] if k + 1 < n_escalones_totales else n
        ventana_len = horizonte - i_inicio
        if ventana_len < 1:
            # No puede pasar con escalones ordenados y sin solape (el fin de uno
            # es anterior al inicio del siguiente), pero si pasara no hay nada
            # que medir: se cuenta como interrumpido, no como una excepción.
            descartados[MotivoTransitorioDescartado.INTERRUMPIDO_POR_OTRO_ESCALON] += 1
            continue

        objetivo_anterior = float(objetivo.v[i_inicio - 1])
        objetivo_nuevo = float(objetivo.v[i_fin])
        if objetivo_nuevo == 0.0:
            raise ErrorDePidBoost(
                "el objetivo tras el escalón es 0 kPa: la sobreoscilación y el error "
                "relativos no se pueden expresar como fracción de un objetivo nulo"
            )

        t_v = actual.t_ms[i_inicio:horizonte]
        actual_v = actual.v[i_inicio:horizonte]
        objetivo_v = objetivo.v[i_inicio:horizonte]
        valido_v = _valido_de(actual)[i_inicio:horizonte] & _valido_de(objetivo)[i_inicio:horizonte]

        actual_ventana = Serie(t_ms=t_v, v=actual_v, clase=Clase.PUNTO, valido=valido_v)
        minimo_ventana = Serie(
            t_ms=t_v,
            v=objetivo_v * (1.0 - umbrales.banda_establecimiento_relativa),
            clase=Clase.PUNTO,
            valido=valido_v,
        )
        maximo_ventana = Serie(
            t_ms=t_v,
            v=objetivo_v * (1.0 + umbrales.banda_establecimiento_relativa),
            clase=Clase.PUNTO,
            valido=valido_v,
        )
        dentro = banda(
            actual_ventana,
            minimo=minimo_ventana,
            maximo=maximo_ventana,
            histeresis_relativa=umbrales.histeresis_banda_relativa,
            xp=xp,
        )
        establecidos = eventos(dentro, permanencia=permanencia_establecida, xp=xp)

        ultimo_local = ventana_len - 1
        candidato: Evento | None = None
        for establecido in establecidos:  # acotado por maximo_de_eventos_internos
            if establecido.i_fin == ultimo_local:
                candidato = establecido
                break

        if candidato is None:
            motivo = (
                MotivoTransitorioDescartado.INTERRUMPIDO_POR_OTRO_ESCALON
                if k + 1 < n_escalones_totales
                else MotivoTransitorioDescartado.SIN_ESTABLECER_AL_FINAL_DEL_SEGMENTO
            )
            descartados[motivo] += 1
            continue

        asentado_local = candidato.i_inicio
        pico_actual = float(xp.max(actual_v))
        sobreoscilacion_absoluta = pico_actual - objetivo_nuevo

        tramo_error = actual_v[asentado_local:ventana_len] - objetivo_v[asentado_local:ventana_len]
        error_regimen = float(xp.sum(tramo_error)) / candidato.n_muestras

        transitorios.append(
            TransitorioBoost(
                t_inicio_ms=float(t_v[0]),
                t_fin_ms=float(t_v[ultimo_local]),
                i_inicio=i_inicio,
                i_fin=horizonte - 1,
                objetivo_anterior_kpa=objetivo_anterior,
                objetivo_nuevo_kpa=objetivo_nuevo,
                escalon_kpa=objetivo_nuevo - objetivo_anterior,
                pico_actual_kpa=pico_actual,
                sobreoscilacion_absoluta_kpa=sobreoscilacion_absoluta,
                sobreoscilacion_relativa=sobreoscilacion_absoluta / objetivo_nuevo,
                tiempo_establecimiento_s=(float(t_v[asentado_local]) - float(t_v[0])) / MS_POR_S,
                error_regimen_kpa=error_regimen,
                error_regimen_relativo=error_regimen / objetivo_nuevo,
                n_muestras_regimen=candidato.n_muestras,
            )
        )

    return InformeTransitoriosBoost(
        transitorios=tuple(transitorios),
        descartados=descartados,
        n_escalones_totales=n_escalones_totales,
    )
