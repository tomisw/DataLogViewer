"""Pruebas del modelo de segmento y del eje X virtual (tarea F2-01).

Especificación: `docs/03-arquitectura.md` §3.6.

QUÉ PROTEGE ESTA SUITE
======================
Esta es la pieza de la prioridad número uno del propietario —comparar varias
tiradas— y su fallo característico no es una excepción: es **una comparación
desplazada que parece correcta**. Dos vueltas dibujadas con medio segundo de
desfase se ven perfectamente normales, y el tuner concluye que un cambio de mapa
hizo algo que no hizo.

De ahí que las pruebas se agrupen por la consecuencia de romper cada regla:

1. **El reloj absoluto no se puede usar con un log sin reloj.** Los dos logs
   internos reales declaran los dos `19800101 01:01:01`, así que alinearlos por
   reloj los superpondría en el mismo instante de 1980. Tiene que ser un error
   con nombre, y jamás un repliegue silencioso a relativo.
2. **En el hueco de la vista concatenada no hay dato.** Si `locales_en` devolviera
   el segmento anterior, el cursor rellenaría el hueco por retención y el usuario
   leería el final de una tirada como si fuera el principio de la siguiente.
3. **La ida y la vuelta son exactas.** `a_local(a_virtual(t)) == t`. Es lo que
   sostiene el cursor, el doble cursor y cualquier detector que respete
   fronteras.
4. **El orden de la vista concatenada es reproducible**: lo da `Log Number`, no
   el recorrido de un diccionario.

Solo biblioteca estándar: este módulo no importa NumPy.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from dlv_core.tiempo import (
    HUECO_CONCATENADO_S,
    ErrorDeTiempo,
    FiabilidadReloj,
    ModoDesfase,
    Segmento,
    concatenar,
    correlacionar,
    desfase_efectivo,
    eje_concatenado,
    eje_paralelo,
)


def seg(
    id_: str,
    *,
    duracion: float = 60.0,
    t0: datetime | None = None,
    fiabilidad: FiabilidadReloj = FiabilidadReloj.DESCONOCIDA,
    orden: int = 0,
    offset: float = 0.0,
    t_inicio: float = 0.0,
    etiqueta: str | None = None,
) -> Segmento:
    return Segmento(
        id=id_,
        t_inicio=t_inicio,
        t_fin=t_inicio + duracion,
        t0_absoluto=t0,
        fiabilidad_reloj=fiabilidad,
        orden=orden,
        offset_usuario=offset,
        etiqueta=etiqueta,
    )


def fiable(id_: str, cuando: datetime, *, duracion: float = 60.0, orden: int = 0) -> Segmento:
    return seg(id_, duracion=duracion, t0=cuando, fiabilidad=FiabilidadReloj.FIABLE, orden=orden)


# --------------------------------------------------------------------------- #
# El modelo de segmento
# --------------------------------------------------------------------------- #
def test_duracion_y_nombre() -> None:
    s = seg("a", duracion=245.1, etiqueta="Tirada 3")
    assert s.duracion == pytest.approx(245.1)
    assert s.nombre == "Tirada 3"
    assert seg("b").nombre == "b", "sin etiqueta, el nombre es el id"


def test_un_segmento_de_duracion_negativa_se_rechaza() -> None:
    """Desplazaría todo lo que vaya detrás en la vista concatenada."""
    with pytest.raises(ErrorDeTiempo, match="anterior a t_inicio"):
        Segmento(
            id="malo",
            t_inicio=10.0,
            t_fin=5.0,
            t0_absoluto=None,
            fiabilidad_reloj=FiabilidadReloj.DESCONOCIDA,
            orden=0,
        )


def test_fiable_sin_t0_absoluto_se_rechaza() -> None:
    """La combinación que pasaría la comprobación de reloj y luego no tendría
    con qué alinear: hay que cazarla al construir, no al usar."""
    with pytest.raises(ErrorDeTiempo, match="sin `t0_absoluto`"):
        Segmento(
            id="malo",
            t_inicio=0.0,
            t_fin=60.0,
            t0_absoluto=None,
            fiabilidad_reloj=FiabilidadReloj.FIABLE,
            orden=0,
        )


def test_un_segmento_de_duracion_cero_es_valido() -> None:
    """Un log de una sola muestra existe (un AutoLog que se cortó al arrancar)."""
    assert seg("a", duracion=0.0).duracion == 0.0


def test_con_offset_no_muta_el_original() -> None:
    """El segmento es inmutable: `con_offset` da una copia.

    Si mutara, dos vistas que compartieran el mismo objeto empezarían a
    discrepar en cuanto el usuario arrastrara una de ellas.
    """
    original = seg("a", offset=0.0)
    movido = original.con_offset(12.5)
    assert original.offset_usuario == 0.0
    assert movido.offset_usuario == 12.5
    assert movido.id == original.id and movido.t_fin == original.t_fin


# --------------------------------------------------------------------------- #
# Desfases
# --------------------------------------------------------------------------- #
def test_relativo_pone_todos_a_cero() -> None:
    segmentos = [seg("a", duracion=60.0), seg("b", duracion=90.0)]
    assert desfase_efectivo(segmentos, modo=ModoDesfase.RELATIVO) == {"a": 0.0, "b": 0.0}


def test_manual_usa_el_offset_del_usuario_normalizado() -> None:
    """El mínimo siempre queda en 0: el eje no empieza en un número arbitrario."""
    segmentos = [seg("a", offset=10.0), seg("b", offset=25.0)]
    assert desfase_efectivo(segmentos, modo=ModoDesfase.MANUAL) == {"a": 0.0, "b": 15.0}


def test_manual_con_offsets_negativos() -> None:
    segmentos = [seg("a", offset=0.0), seg("b", offset=-4.0)]
    d = desfase_efectivo(segmentos, modo=ModoDesfase.MANUAL)
    assert d == {"a": 4.0, "b": 0.0}


def test_reloj_absoluto_calcula_la_separacion_real() -> None:
    """Dos tiradas separadas 5 min quedan a 300 s en el eje."""
    segmentos = [
        fiable("a", datetime(2026, 7, 29, 18, 30, 0)),
        fiable("b", datetime(2026, 7, 29, 18, 35, 0)),
    ]
    assert desfase_efectivo(segmentos, modo=ModoDesfase.RELOJ_ABSOLUTO) == {"a": 0.0, "b": 300.0}


def test_el_reloj_absoluto_no_pierde_los_milisegundos() -> None:
    """La normalización existe justo para esto (ver el docstring de `desfase_efectivo`).

    Sin restar la referencia, un `t0` de 2026 en segundos desde la época son
    ~1,8 × 10⁹, y en `float32` el siguiente valor representable está a más de
    100 s: la resolución de milisegundos del log desaparecería al llegar al
    renderizador.
    """
    segmentos = [
        fiable("a", datetime(2026, 7, 29, 18, 30, 0)),
        fiable("b", datetime(2026, 7, 29, 18, 30, 0, 506000)),
    ]
    d = desfase_efectivo(segmentos, modo=ModoDesfase.RELOJ_ABSOLUTO)
    assert d["b"] == pytest.approx(0.506, abs=1e-9)
    # Y sobrevive a pasar por float32, que es lo que hace el renderizador.
    import struct

    en_f32 = struct.unpack("f", struct.pack("f", d["b"]))[0]
    assert en_f32 == pytest.approx(0.506, abs=1e-6)


def test_el_reloj_absoluto_se_niega_si_algun_segmento_no_lo_tiene_fiable() -> None:
    """LA prueba de esta tarea, con el caso real de §1.5.

    `Log2768` y `Log2769` declaran los dos `19800101 01:01:01`. Si el modo de
    reloj aceptara segmentos con fiabilidad DESCONOCIDA, las dos tiradas
    quedarían superpuestas en el mismo instante de 1980 y el usuario las vería
    como simultáneas. El error tiene que nombrar a los culpables: «no se puede
    alinear» sin decir cuál de los ocho logs lo impide no es accionable.
    """
    segmentos = [
        fiable("autolog", datetime(2026, 7, 29, 18, 30, 35, 506000)),
        seg("log2768", fiabilidad=FiabilidadReloj.DESCONOCIDA, etiqueta="Log 2768"),
        seg("log2769", fiabilidad=FiabilidadReloj.NO_FIABLE, etiqueta="Log 2769"),
    ]
    with pytest.raises(ErrorDeTiempo) as excinfo:
        desfase_efectivo(segmentos, modo=ModoDesfase.RELOJ_ABSOLUTO)
    mensaje = str(excinfo.value)
    assert "Log 2768" in mensaje and "desconocida" in mensaje
    assert "Log 2769" in mensaje and "no_fiable" in mensaje
    assert "autolog" not in mensaje, "no se acusa al que sí tiene reloj fiable"


@pytest.mark.parametrize(
    ("modo", "tarea"), [(ModoDesfase.POR_EVENTO, "F2-07"), (ModoDesfase.CORRELACION, "F2-08")]
)
def test_los_modos_no_implementados_lanzan_y_no_caen_a_relativo(
    modo: ModoDesfase, tarea: str
) -> None:
    """Un desfase de 0 tiene el mismo aspecto que uno bien calculado.

    Es la razón de que esto no devuelva ceros: el usuario habría pedido
    alineación por evento y estaría mirando otra cosa sin saberlo.
    """
    with pytest.raises(NotImplementedError, match=tarea):
        desfase_efectivo([seg("a")], modo=modo)


def test_sin_segmentos_no_hay_eje() -> None:
    with pytest.raises(ErrorDeTiempo, match="ningún segmento"):
        desfase_efectivo([], modo=ModoDesfase.RELATIVO)


def test_un_id_repetido_se_rechaza() -> None:
    """Los desfases se indexan por id: uno repetido haría que un segmento
    heredara el desfase del otro en silencio."""
    with pytest.raises(ErrorDeTiempo, match="repetido"):
        desfase_efectivo([seg("a"), seg("a", offset=99.0)], modo=ModoDesfase.MANUAL)


# --------------------------------------------------------------------------- #
# Vista paralela
# --------------------------------------------------------------------------- #
def test_paralelo_superpone_y_no_tiene_fronteras() -> None:
    eje = eje_paralelo(
        [seg("a", duracion=60.0), seg("b", duracion=90.0)], modo=ModoDesfase.RELATIVO
    )
    assert eje.concatenado is False
    assert eje.fronteras == (), "en paralelo no hay ninguna unión que cortar"
    assert (eje.x_min, eje.x_max) == (0.0, 90.0)
    assert eje.duracion == pytest.approx(90.0)


def test_paralelo_una_x_puede_pertenecer_a_varios_segmentos() -> None:
    """Es el objeto de la vista, no un caso de borde."""
    eje = eje_paralelo(
        [seg("a", duracion=60.0), seg("b", duracion=90.0)], modo=ModoDesfase.RELATIVO
    )
    en_30 = eje.locales_en(30.0)
    assert {p.id_segmento for p in en_30} == {"a", "b"}
    assert all(p.t_local == pytest.approx(30.0) for p in en_30)
    # A los 75 s solo queda el segundo: el primero ya terminó.
    assert [p.id_segmento for p in eje.locales_en(75.0)] == ["b"]
    assert eje.locales_en(120.0) == ()


def test_paralelo_con_desfase_manual_traduce_bien() -> None:
    eje = eje_paralelo(
        [seg("a", duracion=60.0), seg("b", duracion=60.0, offset=10.0)], modo=ModoDesfase.MANUAL
    )
    # x = 15 es t=15 en 'a' y t=5 en 'b'.
    puntos = {p.id_segmento: p.t_local for p in eje.locales_en(15.0)}
    assert puntos["a"] == pytest.approx(15.0)
    assert puntos["b"] == pytest.approx(5.0)


def test_ida_y_vuelta_exacta() -> None:
    """`a_local(a_virtual(t)) == t` para todos los segmentos y modos.

    Es lo que sostiene el cursor y el doble cursor: si esta identidad se rompe,
    el valor que se lee bajo el cursor no es el del instante que se señala.
    """
    segmentos = [
        fiable("a", datetime(2026, 7, 29, 18, 30, 0), duracion=60.0),
        fiable("b", datetime(2026, 7, 29, 18, 32, 30), duracion=90.0),
    ]
    for modo in (ModoDesfase.RELATIVO, ModoDesfase.MANUAL, ModoDesfase.RELOJ_ABSOLUTO):
        eje = eje_paralelo(segmentos, modo=modo)
        for s in segmentos:
            for t in (0.0, 0.001, 13.7, s.t_fin):
                assert eje.a_local(s.id, eje.a_virtual(s.id, t)) == pytest.approx(t, abs=1e-12)


def test_preguntar_por_un_segmento_ajeno_es_un_error_con_nombre() -> None:
    eje = eje_paralelo([seg("a")], modo=ModoDesfase.RELATIVO)
    with pytest.raises(ErrorDeTiempo, match="no está en este eje"):
        eje.a_virtual("no-existe", 0.0)


# --------------------------------------------------------------------------- #
# Vista concatenada
# --------------------------------------------------------------------------- #
def test_concatenado_coloca_los_segmentos_seguidos_con_hueco() -> None:
    eje = eje_concatenado(
        [seg("a", duracion=60.0, orden=1), seg("b", duracion=90.0, orden=2)], hueco_s=2.0
    )
    assert eje.concatenado is True
    assert eje.desfase_de("a") == pytest.approx(0.0)
    assert eje.desfase_de("b") == pytest.approx(62.0)
    assert (eje.x_min, eje.x_max) == (0.0, 152.0)


def test_el_hueco_por_omision_no_es_cero() -> None:
    """Un hueco de 0 haría indistinguible «el log siguió» de «empieza otro log»."""
    assert HUECO_CONCATENADO_S > 0.0
    eje = eje_concatenado([seg("a", duracion=10.0, orden=1), seg("b", duracion=10.0, orden=2)])
    assert eje.desfase_de("b") == pytest.approx(10.0 + HUECO_CONCATENADO_S)


def test_en_el_hueco_no_hay_dato() -> None:
    """La regla 2 de esta suite.

    Si esto devolviera el segmento anterior, el cursor rellenaría el hueco por
    retención de último valor y el usuario leería el final de una tirada como si
    fuera el principio de la siguiente. Fingir continuidad está prohibido (§1.5).
    """
    eje = eje_concatenado(
        [seg("a", duracion=60.0, orden=1), seg("b", duracion=60.0, orden=2)], hueco_s=2.0
    )
    assert [p.id_segmento for p in eje.locales_en(60.0)] == ["a"], "el borde sí es del segmento"
    assert eje.locales_en(61.0) == (), "dentro del hueco: nada"
    assert [p.id_segmento for p in eje.locales_en(62.0)] == ["b"]


def test_concatenado_una_x_nunca_pertenece_a_dos_segmentos() -> None:
    segmentos = [seg(f"s{i}", duracion=30.0, orden=i) for i in range(4)]
    eje = eje_concatenado(segmentos)
    x = eje.x_min
    while x <= eje.x_max:
        assert len(eje.locales_en(x)) <= 1, f"x={x} pertenece a más de un segmento"
        x += 0.5


def test_el_orden_lo_da_log_number_no_el_orden_de_carga() -> None:
    """§1.5: con época ficticia, `Log Number` es lo único monótono que hay."""
    eje = eje_concatenado(
        [
            seg("log2769", duracion=60.0, orden=2769),
            seg("log2768", duracion=60.0, orden=2768),
        ]
    )
    assert [s.id for s in eje.segmentos] == ["log2768", "log2769"]
    assert eje.desfase_de("log2768") == pytest.approx(0.0)


def test_el_orden_es_reproducible_con_orden_empatado() -> None:
    """Un orden que dependa del recorrido de un diccionario abriría el mismo
    proyecto distinto dos veces."""
    a = eje_concatenado([seg("zzz", orden=0), seg("aaa", orden=0)])
    b = eje_concatenado([seg("aaa", orden=0), seg("zzz", orden=0)])
    assert [s.id for s in a.segmentos] == [s.id for s in b.segmentos] == ["aaa", "zzz"]


def test_las_fronteras_estan_donde_empieza_y_acaba_el_hueco() -> None:
    eje = eje_concatenado(
        [seg("a", duracion=60.0, orden=1), seg("b", duracion=60.0, orden=2)], hueco_s=2.0
    )
    assert len(eje.fronteras) == 1
    f = eje.fronteras[0]
    assert (f.id_anterior, f.id_siguiente) == ("a", "b")
    assert f.x_fin_anterior == pytest.approx(60.0)
    assert f.x_inicio_siguiente == pytest.approx(62.0)
    assert f.x_centro == pytest.approx(61.0)


def test_hay_una_frontera_menos_que_segmentos() -> None:
    eje = eje_concatenado([seg(f"s{i}", orden=i) for i in range(5)])
    assert len(eje.fronteras) == 4
    assert len(eje_concatenado([seg("solo")]).fronteras) == 0


def test_frontera_entre_dice_si_hay_que_cortar_el_trazo() -> None:
    """Lo que consulta quien dibuja un tramo: si devuelve algo, se parte la línea."""
    eje = eje_concatenado([seg(f"s{i}", duracion=10.0, orden=i) for i in range(3)], hueco_s=1.0)
    assert eje.frontera_entre(0.0, 5.0) == (), "dentro de un segmento no hay frontera"
    assert len(eje.frontera_entre(0.0, 12.0)) == 1
    assert len(eje.frontera_entre(0.0, 30.0)) == 2
    # El orden de los extremos no importa: el zoom puede pedirlos al revés.
    assert eje.frontera_entre(12.0, 0.0) == eje.frontera_entre(0.0, 12.0)


@pytest.mark.parametrize("hueco", [0.0, -1.0])
def test_un_hueco_no_positivo_se_rechaza(hueco: float) -> None:
    """El cero también, y no por purismo.

    Con hueco 0 la x de la unión sería a la vez el `t_fin` de un segmento y el
    `t_inicio` del siguiente, así que `locales_en` devolvería DOS puntos y se
    rompería el invariante de la vista concatenada. Lo descubrí escribiendo
    `test_concatenado_una_x_nunca_pertenece_a_dos_segmentos`: pasaba con el hueco
    por omisión y habría fallado con 0. Y §3.6 exige marcar siempre la frontera,
    así que un hueco invisible tampoco valdría.
    """
    with pytest.raises(ErrorDeTiempo, match="mayor que cero"):
        eje_concatenado([seg("a", orden=1), seg("b", orden=2)], hueco_s=hueco)


def test_la_x_de_la_union_pertenece_solo_al_segmento_anterior() -> None:
    """El borde exacto, que es donde el invariante se juega."""
    eje = eje_concatenado(
        [seg("a", duracion=60.0, orden=1), seg("b", duracion=60.0, orden=2)], hueco_s=2.0
    )
    f = eje.fronteras[0]
    assert [p.id_segmento for p in eje.locales_en(f.x_fin_anterior)] == ["a"]
    assert [p.id_segmento for p in eje.locales_en(f.x_inicio_siguiente)] == ["b"]
    assert eje.locales_en(f.x_centro) == ()


def test_el_concatenado_no_deja_elegir_modo_de_desfase() -> None:
    """En concatenado el desfase lo impone la colocación, no el usuario: editar
    el hueco es F2-10, elegir el desfase cambiaría el orden."""
    eje = eje_concatenado([seg("a", orden=1), seg("b", orden=2)])
    assert eje.modo is ModoDesfase.RELATIVO


def test_concatenado_respeta_un_t_inicio_distinto_de_cero() -> None:
    """`t_inicio` se recibe en vez de asumirse 0 (ver el campo en `Segmento`).

    Un segmento que empiece en 100 s locales tiene que quedar pegado al
    anterior en el eje, no desplazado 100 s.
    """
    eje = eje_concatenado(
        [
            seg("a", duracion=60.0, orden=1),
            seg("b", duracion=60.0, orden=2, t_inicio=100.0),
        ],
        hueco_s=1.0,
    )
    assert eje.a_virtual("b", 100.0) == pytest.approx(61.0), "el primer instante de 'b'"
    assert [p.id_segmento for p in eje.locales_en(61.0)] == ["b"]


# --------------------------------------------------------------------------- #
# Lo que todavía no es de esta tarea
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("funcion", "tarea"), [(correlacionar, "F2-08"), (concatenar, "F2-09")])
def test_lo_pendiente_cita_su_tarea(funcion: object, tarea: str) -> None:
    """Un `NotImplementedError` sin número de tarea obliga a buscar en el backlog."""
    assert callable(funcion)
    assert funcion.__doc__ is not None and tarea in funcion.__doc__
