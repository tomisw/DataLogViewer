"""Pruebas de la aplicación de perfil por rol (F3-02).

Especificación: `docs/02-alcance-y-plan.md` E4.3. Lo que protege esta suite,
por orden de consecuencia (docs/09 §9.9):

1. **La reserva a `id_nativo` es una coincidencia exacta, nunca un parecido.**
   `test_id_nativo_no_admite_parecido` es la prueba que de verdad importa: un
   identificador nativo casi idéntico pero no exacto NO monta el elemento. Es
   lo que impide que aplicar un perfil de Haltech a un log de otro formato le
   invente una identidad al canal equivocado.
2. **La confianza del rol viaja entera hasta el resultado.** Un rol `DIFUSA`
   SÍ monta su elemento (degradación elegante != política de detectores) pero
   `EstadoElemento.asignacion.confianza` sigue diciendo `DIFUSA`, no un
   booleano: `test_un_rol_difuso_se_monta_con_su_confianza_intacta`.
3. **Un panel sin sus roles requeridos se oculta, con motivo.**
   `test_panel_se_oculta_si_falta_un_rol_requerido` y
   `test_motivo_oculto_nombra_los_roles_que_faltan`.
4. **Un panel con solo opcionales ausentes se sigue mostrando.**
   `test_elemento_opcional_ausente_no_oculta_el_panel`.
5. **Los roles indexados distinguen instancia por índice**, igual que en
   `identidad.py`: `test_roles_indexados_se_montan_por_separado`.
6. **La cobertura por panel es `(disponibles, total)`, no un booleano**:
   `test_cobertura_de_panel`.

Solo biblioteca estándar (`pytest` aparte).
"""

from __future__ import annotations

from dlv_core.aplicar_perfil import (
    CanalDeLogResuelto,
    aplicar_perfil,
    roles_disponibles,
)
from dlv_core.perfil import ElementoDePanel, Panel, Perfil
from dlv_core.roles import Asignacion, Confianza

# --------------------------------------------------------------------------- #
# Fábricas de prueba
# --------------------------------------------------------------------------- #


def _elemento(
    *,
    rol: str | None = None,
    id_nativo: str | None = None,
    requerido: bool = True,
    indice: int | None = None,
) -> ElementoDePanel:
    return ElementoDePanel(rol=rol, id_nativo=id_nativo, requerido=requerido, indice=indice)


def _canal(
    *,
    id_nativo: str | None = None,
    rol: str | None = None,
    confianza: Confianza = Confianza.EXACTA,
    indice: int | None = None,
) -> CanalDeLogResuelto:
    asignacion = (
        None
        if rol is None
        else Asignacion(rol=rol, confianza=confianza, sinonimo=rol, indice=indice)
    )
    return CanalDeLogResuelto(id_nativo=id_nativo, asignacion=asignacion)


def _perfil_de_un_panel(panel: Panel) -> Perfil:
    return Perfil(
        nombre="Perfil de prueba",
        descripcion="",
        paneles=(panel,),
        unidades={},
    )


# --------------------------------------------------------------------------- #
# 1. La reserva a id_nativo: exacta, nunca por parecido
# --------------------------------------------------------------------------- #


def test_id_nativo_disponible_monta_el_elemento() -> None:
    panel = Panel(
        titulo="Trigger",
        elementos=(_elemento(id_nativo="Trigger Tooth Count", requerido=False),),
    )
    perfil = _perfil_de_un_panel(panel)
    canales = [_canal(id_nativo="Trigger Tooth Count")]

    (estado,) = aplicar_perfil(perfil, canales)

    assert estado.elementos[0].disponible
    assert estado.elementos[0].asignacion is None  # id_nativo no pasa por roles


def test_id_nativo_no_admite_parecido() -> None:
    """El corazón de la reserva: un identificador CASI igual no vale.

    Si `aplicar_perfil` usara `asignar_rol` o `difflib` para esto, "Trigger
    Tooth Count" y "Trigger Tooth Count " (con espacio) o "Trigger Tooth
    Counts" pasarían por parecidos. No deben: la reserva de perfil.py existe
    justo para que un ID nativo no se comporte como un rol difuso.
    """
    panel = Panel(
        titulo="Trigger",
        elementos=(_elemento(id_nativo="Trigger Tooth Count", requerido=False),),
    )
    perfil = _perfil_de_un_panel(panel)
    canales = [_canal(id_nativo="Trigger Tooth Counts")]  # una letra de más

    (estado,) = aplicar_perfil(perfil, canales)

    assert not estado.elementos[0].disponible


def test_id_nativo_de_un_log_de_otro_formato_no_monta_nada() -> None:
    """Simula aplicar un perfil con reserva Haltech a un log que no trae
    ninguno de esos identificadores literales (el caso real: un CSV genérico
    o cualquier otro formato). El elemento se omite, el panel no revienta."""
    panel = Panel(
        titulo="PID de boost",
        elementos=(
            _elemento(id_nativo="Boost Control Proportional Output", requerido=False),
            _elemento(id_nativo="Boost Control Integral Output", requerido=False),
        ),
    )
    perfil = _perfil_de_un_panel(panel)
    # Canales de un log genérico: ni rastro de los nombres nativos de Haltech.
    canales = [
        _canal(rol="engine_speed"),
        _canal(rol="coolant_temp"),
    ]

    (estado,) = aplicar_perfil(perfil, canales)

    assert estado.elementos_disponibles == ()
    assert len(estado.elementos_no_disponibles) == 2
    # Y el panel no se oculta por esto: ningún elemento por id_nativo puede
    # ser `requerido` (perfil.py lo prohíbe en el esquema), así que la
    # ausencia de todos ellos no bloquea nada.
    assert estado.visible


# --------------------------------------------------------------------------- #
# 2. La confianza viaja entera
# --------------------------------------------------------------------------- #


def test_un_rol_difuso_se_monta_con_su_confianza_intacta() -> None:
    panel = Panel(titulo="Refrigeración", elementos=(_elemento(rol="coolant_temp"),))
    perfil = _perfil_de_un_panel(panel)
    canales = [_canal(rol="coolant_temp", confianza=Confianza.DIFUSA)]

    (estado,) = aplicar_perfil(perfil, canales)
    elemento = estado.elementos[0]

    # Se monta -- ocultar por confianza baja es política de F3-08, no de este
    # módulo -- pero la confianza real llega intacta, no aplanada a un booleano.
    assert elemento.disponible
    assert elemento.asignacion is not None
    assert elemento.asignacion.confianza is Confianza.DIFUSA
    assert estado.visible


def test_confianza_exacta_e_indexada_tambien_viajan() -> None:
    panel = Panel(
        titulo="Knock",
        elementos=(
            _elemento(rol="knock_count", indice=1, requerido=False),
            _elemento(rol="engine_speed", requerido=False),
        ),
    )
    perfil = _perfil_de_un_panel(panel)
    canales = [
        _canal(rol="knock_count", confianza=Confianza.INDEXADA, indice=1),
        _canal(rol="engine_speed", confianza=Confianza.EXACTA),
    ]

    (estado,) = aplicar_perfil(perfil, canales)
    por_rol = {e.elemento.rol: e for e in estado.elementos}

    assert por_rol["knock_count"].asignacion is not None
    assert por_rol["knock_count"].asignacion.confianza is Confianza.INDEXADA
    assert por_rol["engine_speed"].asignacion is not None
    assert por_rol["engine_speed"].asignacion.confianza is Confianza.EXACTA


def test_dos_canales_al_mismo_rol_e_indice_gana_el_mas_confiable() -> None:
    """Caso raro y defensivo: si dos canales del mismo log resolvieran al
    mismo (rol, índice) -- un catálogo de roles mal escrito, por ejemplo --
    se queda la asignación más confiable, no la primera que llegue."""
    panel = Panel(titulo="Motor", elementos=(_elemento(rol="engine_speed", requerido=False),))
    perfil = _perfil_de_un_panel(panel)
    canales = [
        _canal(rol="engine_speed", confianza=Confianza.DIFUSA),
        _canal(rol="engine_speed", confianza=Confianza.EXACTA),
    ]

    (estado,) = aplicar_perfil(perfil, canales)

    assert estado.elementos[0].asignacion is not None
    assert estado.elementos[0].asignacion.confianza is Confianza.EXACTA


# --------------------------------------------------------------------------- #
# 3. Un panel sin sus roles requeridos se oculta, con motivo
# --------------------------------------------------------------------------- #


def test_panel_se_oculta_si_falta_un_rol_requerido() -> None:
    panel = Panel(
        titulo="Refrigeración",
        elementos=(_elemento(rol="coolant_temp", requerido=True),),
    )
    perfil = _perfil_de_un_panel(panel)

    (estado,) = aplicar_perfil(perfil, canales=[])

    assert not estado.visible
    assert estado.roles_requeridos_faltantes == frozenset({"coolant_temp"})


def test_motivo_oculto_nombra_los_roles_que_faltan() -> None:
    panel = Panel(
        titulo="Knock",
        elementos=(
            _elemento(rol="knock_count", requerido=True),
            _elemento(rol="engine_speed", requerido=True),
        ),
    )
    perfil = _perfil_de_un_panel(panel)

    (estado,) = aplicar_perfil(perfil, canales=[_canal(rol="engine_speed")])

    assert estado.motivo_oculto is not None
    assert "knock_count" in estado.motivo_oculto
    assert "engine_speed" not in estado.motivo_oculto
    assert "Knock" in estado.motivo_oculto


def test_panel_visible_no_tiene_motivo_oculto() -> None:
    panel = Panel(titulo="Motor", elementos=(_elemento(rol="engine_speed", requerido=True),))
    perfil = _perfil_de_un_panel(panel)

    (estado,) = aplicar_perfil(perfil, canales=[_canal(rol="engine_speed")])

    assert estado.visible
    assert estado.motivo_oculto is None


# --------------------------------------------------------------------------- #
# 4. Opcionales ausentes no ocultan el panel
# --------------------------------------------------------------------------- #


def test_elemento_opcional_ausente_no_oculta_el_panel() -> None:
    panel = Panel(
        titulo="Mezcla",
        elementos=(
            _elemento(rol="engine_speed", requerido=True),
            _elemento(rol="lambda_1", requerido=False),
        ),
    )
    perfil = _perfil_de_un_panel(panel)

    (estado,) = aplicar_perfil(perfil, canales=[_canal(rol="engine_speed")])

    assert estado.visible
    assert [e.disponible for e in estado.elementos] == [True, False]
    assert len(estado.elementos_disponibles) == 1
    assert len(estado.elementos_no_disponibles) == 1


# --------------------------------------------------------------------------- #
# 5. Roles indexados
# --------------------------------------------------------------------------- #


def test_roles_indexados_se_montan_por_separado() -> None:
    panel = Panel(
        titulo="Knock",
        elementos=(
            _elemento(rol="knock_count", indice=1, requerido=False),
            _elemento(rol="knock_count", indice=2, requerido=False),
        ),
    )
    perfil = _perfil_de_un_panel(panel)
    # Solo el sensor 1 está presente en este log.
    canales = [_canal(rol="knock_count", indice=1)]

    (estado,) = aplicar_perfil(perfil, canales)

    disponibles = {e.elemento.indice: e.disponible for e in estado.elementos}
    assert disponibles == {1: True, 2: False}


# --------------------------------------------------------------------------- #
# 6. Cobertura por panel y `roles_disponibles`
# --------------------------------------------------------------------------- #


def test_cobertura_de_panel() -> None:
    panel = Panel(
        titulo="Knock",
        elementos=(
            _elemento(rol="knock_count", requerido=False),
            _elemento(rol="engine_speed", requerido=False),
            _elemento(rol="map", requerido=False),
        ),
    )
    perfil = _perfil_de_un_panel(panel)
    canales = [_canal(rol="knock_count"), _canal(rol="engine_speed")]

    (estado,) = aplicar_perfil(perfil, canales)

    assert estado.cobertura == (2, 3)


def test_cobertura_de_panel_solo_con_id_nativo_es_cero_de_cero() -> None:
    """Un panel sin ningún rol referenciado no tiene "cobertura de roles" que
    contar: `(0, 0)`, distinto de "cobertura cero", que sería `(0, N)`."""
    panel = Panel(
        titulo="Trigger",
        elementos=(_elemento(id_nativo="Trigger Tooth Count", requerido=False),),
    )
    perfil = _perfil_de_un_panel(panel)

    (estado,) = aplicar_perfil(perfil, canales=[])

    assert estado.cobertura == (0, 0)


def test_roles_disponibles_del_log() -> None:
    canales = [
        _canal(rol="engine_speed"),
        _canal(rol="coolant_temp", confianza=Confianza.DIFUSA),
        _canal(id_nativo="Trigger Tooth Count"),  # sin rol: no cuenta
    ]

    assert roles_disponibles(canales) == frozenset({"engine_speed", "coolant_temp"})


# --------------------------------------------------------------------------- #
# Orden y varios paneles
# --------------------------------------------------------------------------- #


def test_el_orden_de_salida_sigue_al_del_perfil() -> None:
    perfil = Perfil(
        nombre="Perfil de prueba",
        descripcion="",
        paneles=(
            Panel(titulo="Uno", elementos=(_elemento(rol="engine_speed", requerido=False),)),
            Panel(titulo="Dos", elementos=(_elemento(rol="coolant_temp", requerido=False),)),
        ),
        unidades={},
    )

    resultado = aplicar_perfil(perfil, canales=[])

    assert [e.panel.titulo for e in resultado] == ["Uno", "Dos"]
