"""Alineación por reloj absoluto y por relativo (tarea F2-05).

Especificación: `docs/03-arquitectura.md` §3.6, tabla «Vista paralela»
(`x = t_local + offset_efectivo`). Esta tarea entrega DOS de las cinco filas de
esa tabla —reloj absoluto y relativo— y solo esas: manual es F2-06, por evento
es F2-07, correlación es F2-08.

POR QUÉ ESTE MÓDULO NO REPITE LA ARITMÉTICA DE `tiempo.py`
===========================================================
`dlv_core.tiempo` (F2-01) ya implementa las dos reglas que esta tarea tenía que
entregar, porque `eje_paralelo` no se podía construir ni probar sin ellas:
`desfase_efectivo` calcula el desfase de reloj absoluto exigiendo
`FiabilidadReloj.FIABLE` en TODOS los segmentos —y lo hace con un `ErrorDeTiempo`,
no un aviso, nombrando a los segmentos que no lo tienen fiable, exactamente por
la razón que motiva esta tarea: los logs internos de una ECU sin reloj de
tiempo real declaran una época de fábrica que parece una fecha real
(`Log2768`/`Log2769` de `samples/real/`, los dos `19800101 01:01:01`), y
alinearlos por reloj los superpondría en el mismo instante de 1980 en vez de
fallar—, y pone el modo relativo a cero para todos. Reescribir esa lógica aquí
sería exactamente el error que `docs/09` cataloga como «empezar sin comprobar
si ya está hecho»: dos sitios que deciden lo mismo acaban discrepando el día
que uno de los dos cambie.

Lo que SÍ falta y es legítimamente de esta tarea es una puerta de entrada
ESTRECHA: `tiempo.eje_paralelo` acepta los cinco modos del enum (tres ya
resueltos, dos pendientes de F2-07/F2-08) porque es el motor común de toda la
vista paralela. Quien solo tiene el encargo de F2-05 —hoy, este módulo; mañana,
el endpoint de `dlv-api` que construya `SegmentoParalelo.offset` (ver el
comentario de F2-04 en `dlv-ui/src/paralela/tipos.ts`, que sigue sin endpoint)—
no debería poder pasar `ModoDesfase.MANUAL` sin darse cuenta de que ese modo es
el arrastre de F2-06: `alinear` lo rechaza en vez de calcularlo en silencio,
aunque `tiempo.py` sepa hacerlo.

`disponibilidad` es la otra pieza que faltaba: saber SI el reloj absoluto se
puede ofrecer para un conjunto de segmentos, sin necesidad de intentarlo y
capturar `ErrorDeTiempo` como control de flujo. Delega en
`tiempo.desfase_efectivo` en vez de repetir el filtro de `FiabilidadReloj`, así
que el motivo que devuelve es literalmente el mismo mensaje —con los mismos
nombres de segmento— que lanzaría `alinear`: no hay dos redacciones del mismo
diagnóstico que puedan divergir.

ADR-009
=======
Como `tiempo.py`: se recorren segmentos (unos pocos), nunca muestras. No hay
nada que vectorizar en este fichero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dlv_core.tiempo import (
    EjeVirtual,
    ErrorDeTiempo,
    ModoDesfase,
    Segmento,
    desfase_efectivo,
    eje_paralelo,
)

__all__ = [
    "Disponibilidad",
    "EjeVirtual",
    "ErrorDeTiempo",
    "ModoDesfase",
    "Segmento",
    "alinear",
    "disponibilidad",
]

#: Los dos modos que entrega esta tarea. Los otros tres viven en el mismo enum
#: (`dlv_core.tiempo.ModoDesfase`) porque son la misma decisión de dominio,
#: pero esta puerta solo deja pasar los suyos.
_MODOS_DE_ESTA_TAREA = frozenset({ModoDesfase.RELOJ_ABSOLUTO, ModoDesfase.RELATIVO})

#: A qué tarea del backlog pertenece cada modo que esta puerta rechaza. Sirve
#: para que el mensaje de error mande a quien lo pide al sitio correcto en vez
#: de a un «no implementado» genérico.
_TAREA_DEL_MODO: dict[ModoDesfase, str] = {
    ModoDesfase.MANUAL: "F2-06 (arrastre manual del usuario)",
    ModoDesfase.POR_EVENTO: "F2-07 (alineación por evento)",
    ModoDesfase.CORRELACION: "F2-08 (autoalineación por correlación cruzada)",
}


def _comprobar_modo_propio(modo: ModoDesfase) -> None:
    if modo in _MODOS_DE_ESTA_TAREA:
        return
    tarea = _TAREA_DEL_MODO.get(modo, "otra tarea")
    raise ErrorDeTiempo(
        f"el modo {modo.name} no es de esta tarea (F2-05): lo resuelve {tarea}. "
        "`dlv_core.alineacion` solo expone RELOJ_ABSOLUTO y RELATIVO; usa "
        "`dlv_core.tiempo.eje_paralelo` directamente si de verdad necesitas otro modo "
        "y su tarea ya está hecha, o el módulo propio de esa tarea"
    )


@dataclass(slots=True, frozen=True)
class Disponibilidad:
    """Si un modo se puede ofrecer para un conjunto de segmentos, y por qué no.

    Para que quien construye la interfaz pueda deshabilitar «alinear por reloj
    absoluto» y explicar el motivo ANTES de que el usuario lo pida, sin tener
    que llamar a `alinear` y capturar la excepción solo para leer su mensaje.
    """

    disponible: bool
    motivo: str | None = None
    """`None` cuando `disponible` es `True`. El mismo texto que lanzaría
    `alinear` si de todas formas se intentara: no hay una segunda redacción del
    mismo diagnóstico."""


def disponibilidad(segmentos: Sequence[Segmento], modo: ModoDesfase) -> Disponibilidad:
    """Comprueba `modo` para `segmentos` sin lanzar y sin construir el eje.

    Delega en `tiempo.desfase_efectivo`: el diagnóstico es el resultado real de
    intentar el cálculo, no una versión resumida de la regla. Así, si mañana
    `tiempo.py` afina cuándo el reloj absoluto es viable, este módulo no puede
    quedarse con una copia de la regla vieja.
    """
    _comprobar_modo_propio(modo)
    try:
        desfase_efectivo(segmentos, modo=modo)
    except ErrorDeTiempo as exc:
        return Disponibilidad(disponible=False, motivo=str(exc))
    return Disponibilidad(disponible=True)


def alinear(segmentos: Sequence[Segmento], *, modo: ModoDesfase) -> EjeVirtual:
    """Vista paralela alineada por reloj absoluto o por relativo (F2-05).

    Es exactamente `tiempo.eje_paralelo` con la puerta de `_comprobar_modo_propio`
    delante. Con `modo=ModoDesfase.RELOJ_ABSOLUTO` y algún segmento sin
    `FiabilidadReloj.FIABLE`, propaga el `ErrorDeTiempo` de
    `tiempo._desfases_por_reloj` SIN capturarlo: pedir reloj absoluto con un
    reloj no fiable tiene que fallar, nunca replegarse en silencio a relativo
    (§3.6; es la regla que motiva esta tarea).
    """
    _comprobar_modo_propio(modo)
    return eje_paralelo(segmentos, modo=modo)
