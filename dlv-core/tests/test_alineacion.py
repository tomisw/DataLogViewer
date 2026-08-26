"""Pruebas de la alineación por reloj absoluto y por relativo (tarea F2-05).

Especificación: `docs/03-arquitectura.md` §3.6, tabla «Vista paralela».

QUÉ PROTEGE ESTA SUITE
======================
1. **Pedir reloj absoluto con un reloj no fiable es un error, siempre**, nunca
   un repliegue silencioso a relativo. `alinear` no captura el `ErrorDeTiempo`
   de `tiempo._desfases_por_reloj`: lo deja pasar tal cual. El caso real es
   `Log2768`/`Log2769` de `samples/real/`, que declaran los dos
   `19800101 01:01:01` (época de fábrica, §1.5): alinearlos por reloj los
   superpondría en el mismo instante de 1980.
2. **La puerta de `dlv_core.alineacion` es más estrecha que la de `tiempo.py`**:
   solo dos de los cinco modos pasan. `MANUAL` (F2-06) se rechaza aquí aunque
   `tiempo.py` sepa calcularlo, y `POR_EVENTO`/`CORRELACION` (F2-07/F2-08) se
   rechazan con `ErrorDeTiempo` citando su tarea, no con el `NotImplementedError`
   que lanzaría `tiempo.py` si llegaran hasta allí.
3. **`disponibilidad` nunca lanza** y su motivo, cuando no está disponible, es
   exactamente el mensaje que `alinear` lanzaría: no hay dos redacciones del
   mismo diagnóstico que puedan divergir con el tiempo.

Solo biblioteca estándar: este módulo no importa NumPy.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from dlv_core import tiempo as tiempo_mod
from dlv_core.alineacion import (
    Disponibilidad,
    EjeVirtual,
    ErrorDeTiempo,
    ModoDesfase,
    Segmento,
    alinear,
    disponibilidad,
)
from dlv_core.tiempo import FiabilidadReloj, eje_paralelo


def seg(
    id_: str,
    *,
    duracion: float = 60.0,
    t0: datetime | None = None,
    fiabilidad: FiabilidadReloj = FiabilidadReloj.DESCONOCIDA,
    orden: int = 0,
    etiqueta: str | None = None,
) -> Segmento:
    return Segmento(
        id=id_,
        t_inicio=0.0,
        t_fin=duracion,
        t0_absoluto=t0,
        fiabilidad_reloj=fiabilidad,
        orden=orden,
        etiqueta=etiqueta,
    )


def fiable(id_: str, cuando: datetime, *, duracion: float = 60.0) -> Segmento:
    return seg(id_, duracion=duracion, t0=cuando, fiabilidad=FiabilidadReloj.FIABLE)


# --------------------------------------------------------------------------- #
# Los reexports son los mismos objetos, no copias
# --------------------------------------------------------------------------- #
def test_los_tipos_reexportados_son_los_de_tiempo_py() -> None:
    """Para que capturar `alineacion.ErrorDeTiempo` o `tiempo.ErrorDeTiempo`
    sea indistinguible: son la misma clase, no dos jerarquías paralelas."""
    assert ErrorDeTiempo is tiempo_mod.ErrorDeTiempo
    assert ModoDesfase is tiempo_mod.ModoDesfase
    assert Segmento is tiempo_mod.Segmento
    assert EjeVirtual is tiempo_mod.EjeVirtual


# --------------------------------------------------------------------------- #
# alinear: los dos modos que entrega esta tarea
# --------------------------------------------------------------------------- #
def test_alinear_relativo_coincide_con_eje_paralelo() -> None:
    segmentos = [seg("a", duracion=60.0), seg("b", duracion=90.0)]
    esperado = eje_paralelo(segmentos, modo=ModoDesfase.RELATIVO)
    obtenido = alinear(segmentos, modo=ModoDesfase.RELATIVO)
    assert obtenido.desfases == esperado.desfases
    assert obtenido.modo is ModoDesfase.RELATIVO


def test_alinear_reloj_absoluto_coincide_con_eje_paralelo() -> None:
    """Misma aritmética que `tiempo.py`: dos tiradas separadas 5 min quedan a
    300 s en el eje. `alinear` no recalcula nada, solo delega."""
    segmentos = [
        fiable("a", datetime(2026, 7, 29, 18, 30, 0)),
        fiable("b", datetime(2026, 7, 29, 18, 35, 0)),
    ]
    esperado = eje_paralelo(segmentos, modo=ModoDesfase.RELOJ_ABSOLUTO)
    obtenido = alinear(segmentos, modo=ModoDesfase.RELOJ_ABSOLUTO)
    assert obtenido.desfases == esperado.desfases == {"a": 0.0, "b": 300.0}


def test_alinear_reloj_absoluto_es_un_error_si_algun_segmento_no_es_fiable() -> None:
    """LA prueba de esta tarea: reloj absoluto con reloj no fiable NUNCA se
    repliega en silencio a relativo, es un `ErrorDeTiempo` con nombre.

    Caso real de `docs/01` §1.5: `Log2768`/`Log2769` declaran los dos
    `19800101 01:01:01` (época de fábrica, sin reloj de tiempo real).
    Alinearlos por reloj los superpondría en el mismo instante de 1980 y las
    dos tiradas se verían, en silencio, como simultáneas.
    """
    segmentos = [
        fiable("autolog", datetime(2026, 7, 29, 18, 30, 35, 506000)),
        seg("log2768", fiabilidad=FiabilidadReloj.DESCONOCIDA, etiqueta="Log 2768"),
        seg("log2769", fiabilidad=FiabilidadReloj.NO_FIABLE, etiqueta="Log 2769"),
    ]
    with pytest.raises(ErrorDeTiempo) as excinfo:
        alinear(segmentos, modo=ModoDesfase.RELOJ_ABSOLUTO)
    mensaje = str(excinfo.value)
    assert "Log 2768" in mensaje and "desconocida" in mensaje
    assert "Log 2769" in mensaje and "no_fiable" in mensaje
    assert "autolog" not in mensaje, "no se acusa al segmento que sí tiene reloj fiable"


def test_alinear_reloj_absoluto_con_un_solo_segmento_no_fiable_tambien_falla() -> None:
    """No hace falta que haya dos logs: uno solo sin reloj fiable ya basta
    para que el modo sea un error, porque no hay con qué alinear."""
    with pytest.raises(ErrorDeTiempo, match="reloj fiable"):
        alinear(
            [seg("solo", fiabilidad=FiabilidadReloj.DESCONOCIDA)], modo=ModoDesfase.RELOJ_ABSOLUTO
        )


# --------------------------------------------------------------------------- #
# La puerta es más estrecha que la de tiempo.py
# --------------------------------------------------------------------------- #
def test_alinear_rechaza_manual_aunque_tiempo_py_sepa_calcularlo() -> None:
    """`tiempo.eje_paralelo` calcula MANUAL sin problema; `alineacion.alinear`
    lo rechaza porque el arrastre del usuario es la tarea F2-06, no esta."""
    segmentos = [seg("a"), seg("b")]
    # Control: tiempo.py SÍ lo calcula (no está roto, es una decisión de F2-05).
    eje_paralelo(segmentos, modo=ModoDesfase.MANUAL)
    with pytest.raises(ErrorDeTiempo, match="F2-06"):
        alinear(segmentos, modo=ModoDesfase.MANUAL)


@pytest.mark.parametrize(
    ("modo", "tarea"), [(ModoDesfase.POR_EVENTO, "F2-07"), (ModoDesfase.CORRELACION, "F2-08")]
)
def test_alinear_rechaza_lo_pendiente_con_error_de_tiempo_no_not_implemented(
    modo: ModoDesfase, tarea: str
) -> None:
    """Estos modos tampoco existen en `tiempo.py` todavía (lanzan
    `NotImplementedError` si se les llega a preguntar), pero aquí ni siquiera
    llegan: la puerta de esta tarea los para antes, con `ErrorDeTiempo`."""
    with pytest.raises(ErrorDeTiempo, match=tarea):
        alinear([seg("a")], modo=modo)


# --------------------------------------------------------------------------- #
# disponibilidad: la misma respuesta que alinear, sin lanzar
# --------------------------------------------------------------------------- #
def test_disponibilidad_relativo_siempre_disponible() -> None:
    d = disponibilidad([seg("a"), seg("b")], ModoDesfase.RELATIVO)
    assert d == Disponibilidad(disponible=True)


def test_disponibilidad_reloj_absoluto_cuando_todos_son_fiables() -> None:
    segmentos = [
        fiable("a", datetime(2026, 7, 29, 18, 30, 0)),
        fiable("b", datetime(2026, 7, 29, 18, 35, 0)),
    ]
    assert disponibilidad(segmentos, ModoDesfase.RELOJ_ABSOLUTO) == Disponibilidad(disponible=True)


def test_disponibilidad_reloj_absoluto_no_disponible_nombra_el_mismo_motivo_que_alinear() -> None:
    """El `motivo` no es un resumen aparte: es el mensaje real de `alinear`."""
    segmentos = [
        fiable("autolog", datetime(2026, 7, 29, 18, 30, 35)),
        seg("log2768", fiabilidad=FiabilidadReloj.DESCONOCIDA, etiqueta="Log 2768"),
    ]
    d = disponibilidad(segmentos, ModoDesfase.RELOJ_ABSOLUTO)
    assert d.disponible is False
    assert d.motivo is not None and "Log 2768" in d.motivo

    with pytest.raises(ErrorDeTiempo) as excinfo:
        alinear(segmentos, modo=ModoDesfase.RELOJ_ABSOLUTO)
    assert d.motivo == str(excinfo.value)


def test_disponibilidad_no_lanza_nunca_para_los_modos_propios() -> None:
    """Es justo lo que la hace útil para una interfaz: preguntar no puede
    tumbar nada, ni siquiera con un conjunto de segmentos vacío o repetido.

    Delega en `desfase_efectivo`, así que hereda sus propias comprobaciones
    (sin segmentos, id repetido) como «no disponible», no como excepción.
    """
    sin_segmentos = disponibilidad([], ModoDesfase.RELOJ_ABSOLUTO)
    assert sin_segmentos.disponible is False and sin_segmentos.motivo is not None
    assert "ningún segmento" in sin_segmentos.motivo

    repetido = disponibilidad([seg("a"), seg("a")], ModoDesfase.RELATIVO)
    assert repetido.disponible is False and repetido.motivo is not None
    assert "repetido" in repetido.motivo


def test_disponibilidad_rechaza_modos_ajenos_igual_que_alinear() -> None:
    with pytest.raises(ErrorDeTiempo, match="F2-06"):
        disponibilidad([seg("a")], ModoDesfase.MANUAL)
