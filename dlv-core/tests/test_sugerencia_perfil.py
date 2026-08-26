"""Pruebas de la autosugerencia de perfil por cobertura de roles (F3-04).

Especificación: `docs/02-alcance-y-plan.md` E4.5: «perfil Knock: 7 de 9 roles
disponibles». Lo que protege esta suite, por orden de consecuencia (docs/09
§9.9):

1. **Un canal vacío no cuenta como disponible**, aunque resuelva su rol sobre
   el papel: `test_un_canal_vacio_no_cuenta_para_la_cobertura`. Es la decisión
   central de la tarea -- si se rompe, la autosugerencia recomienda un perfil
   que se abre en blanco.
2. **Requerido pesa más que opcional, por panel**: perder un requerido pierde
   el panel ENTERO, incluidos los opcionales que sí se habían resuelto:
   `test_un_panel_sin_su_requerido_no_aporta_ninguno_de_sus_roles`.
3. **Una asignación DIFUSA no basta para recomendar**, aunque sí bastara para
   dibujar en `aplicar_perfil`: `test_un_rol_difuso_no_cuenta_para_recomendar`.
4. **Empates deterministas y "ninguno encaja"**:
   `test_el_orden_es_determinista_con_el_mismo_empate`,
   `test_mejor_sugerencia_devuelve_none_si_nadie_llega_al_minimo`.

Solo biblioteca estándar (`pytest` aparte).
"""

from __future__ import annotations

from dlv_core.aplicar_perfil import CanalDeLogResuelto
from dlv_core.perfil import ElementoDePanel, Panel, Perfil
from dlv_core.roles import Asignacion, Confianza
from dlv_core.sugerencia_perfil import (
    CanalParaSugerencia,
    mejor_sugerencia,
    sugerir_perfiles,
)

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
    rol: str | None = None,
    id_nativo: str | None = None,
    confianza: Confianza = Confianza.EXACTA,
    vacio: bool = False,
) -> CanalParaSugerencia:
    asignacion = None if rol is None else Asignacion(rol=rol, confianza=confianza, sinonimo=rol)
    return CanalParaSugerencia(
        canal=CanalDeLogResuelto(id_nativo=id_nativo, asignacion=asignacion),
        vacio=vacio,
    )


def _perfil(nombre: str, paneles: tuple[Panel, ...]) -> Perfil:
    return Perfil(nombre=nombre, descripcion="", paneles=paneles, unidades={})


# --------------------------------------------------------------------------- #
# 1. Un canal vacío no cuenta como disponible
# --------------------------------------------------------------------------- #


def test_un_canal_vacio_no_cuenta_para_la_cobertura() -> None:
    panel = Panel(
        titulo="Knock",
        elementos=(
            _elemento(rol="knock_count", requerido=False),
            _elemento(rol="engine_speed", requerido=False),
        ),
    )
    perfil = _perfil("Knock", (panel,))

    # engine_speed tiene rol asignado pero el canal está vacío: no debería
    # contar, aunque sobre el papel el elemento se pueda montar.
    canales = [
        _canal(rol="knock_count"),
        _canal(rol="engine_speed", vacio=True),
    ]

    (sugerencia,) = sugerir_perfiles([perfil], canales)

    assert sugerencia.disponibles == 1
    assert sugerencia.total == 2


def test_un_canal_no_vacio_si_cuenta() -> None:
    panel = Panel(titulo="Motor", elementos=(_elemento(rol="engine_speed", requerido=False),))
    perfil = _perfil("Motor", (panel,))
    canales = [_canal(rol="engine_speed", vacio=False)]

    (sugerencia,) = sugerir_perfiles([perfil], canales)

    assert sugerencia.disponibles == 1
    assert sugerencia.total == 1


# --------------------------------------------------------------------------- #
# 2. Requerido pesa más que opcional, por panel
# --------------------------------------------------------------------------- #


def test_un_panel_sin_su_requerido_no_aporta_ninguno_de_sus_roles() -> None:
    """knock_count (opcional) SÍ está disponible, pero engine_speed
    (requerido) no. El panel entero se oculta y ninguno de los dos cuenta,
    ni siquiera el opcional que sí se había resuelto."""
    panel = Panel(
        titulo="Knock",
        elementos=(
            _elemento(rol="knock_count", requerido=False),
            _elemento(rol="engine_speed", requerido=True),
        ),
    )
    perfil = _perfil("Knock", (panel,))
    canales = [_canal(rol="knock_count")]  # falta engine_speed

    (sugerencia,) = sugerir_perfiles([perfil], canales)

    assert sugerencia.disponibles == 0
    assert sugerencia.total == 2


def test_perder_un_opcional_no_oculta_el_panel_ni_penaliza_al_resto() -> None:
    panel = Panel(
        titulo="Mezcla",
        elementos=(
            _elemento(rol="engine_speed", requerido=True),
            _elemento(rol="lambda_1", requerido=False),
        ),
    )
    perfil = _perfil("Mezcla", (panel,))
    canales = [_canal(rol="engine_speed")]  # falta el opcional lambda_1

    (sugerencia,) = sugerir_perfiles([perfil], canales)

    # El panel sigue visible (el requerido está), así que engine_speed cuenta.
    assert sugerencia.disponibles == 1
    assert sugerencia.total == 2


def test_dos_paneles_uno_oculto_y_otro_visible() -> None:
    panel_oculto = Panel(titulo="Knock", elementos=(_elemento(rol="knock_count", requerido=True),))
    panel_visible = Panel(
        titulo="Motor", elementos=(_elemento(rol="engine_speed", requerido=True),)
    )
    perfil = _perfil("Mixto", (panel_oculto, panel_visible))
    canales = [_canal(rol="engine_speed")]  # falta knock_count

    (sugerencia,) = sugerir_perfiles([perfil], canales)

    assert sugerencia.disponibles == 1  # solo engine_speed, del panel visible
    assert sugerencia.total == 2


# --------------------------------------------------------------------------- #
# 3. DIFUSA no basta para recomendar
# --------------------------------------------------------------------------- #


def test_un_rol_difuso_no_cuenta_para_recomendar() -> None:
    panel = Panel(titulo="Refrigeración", elementos=(_elemento(rol="coolant_temp"),))
    perfil = _perfil("Refrigeración", (panel,))
    canales = [_canal(rol="coolant_temp", confianza=Confianza.DIFUSA)]

    (sugerencia,) = sugerir_perfiles([perfil], canales)

    # El rol es requerido y solo llega difuso: para RECOMENDAR, el panel se
    # trata como si no tuviera el rol -- se oculta y no aporta nada.
    assert sugerencia.disponibles == 0
    assert sugerencia.total == 1


def test_confianza_indexada_es_igual_de_firme_que_exacta() -> None:
    panel = Panel(titulo="Knock", elementos=(_elemento(rol="knock_count", requerido=False),))
    perfil = _perfil("Knock", (panel,))
    canales = [_canal(rol="knock_count", confianza=Confianza.INDEXADA)]

    (sugerencia,) = sugerir_perfiles([perfil], canales)

    assert sugerencia.disponibles == 1


# --------------------------------------------------------------------------- #
# Roles solo referenciados en límites de alerta (sin elemento de panel)
# --------------------------------------------------------------------------- #


def test_rol_solo_en_id_nativo_da_cero_de_cero() -> None:
    panel = Panel(
        titulo="Trigger",
        elementos=(_elemento(id_nativo="Trigger Tooth Count", requerido=False),),
    )
    perfil = _perfil("Trigger", (panel,))

    (sugerencia,) = sugerir_perfiles([perfil], canales=[])

    assert sugerencia.disponibles == 0
    assert sugerencia.total == 0
    assert sugerencia.proporcion == 0.0


# --------------------------------------------------------------------------- #
# 4. Orden determinista, empates y "ninguno encaja"
# --------------------------------------------------------------------------- #


def test_los_perfiles_se_ordenan_por_cobertura_descendente() -> None:
    panel_completo = Panel(
        titulo="Motor", elementos=(_elemento(rol="engine_speed", requerido=False),)
    )
    panel_incompleto = Panel(
        titulo="Knock",
        elementos=(
            _elemento(rol="knock_count", requerido=False),
            _elemento(rol="map", requerido=False),
        ),
    )
    perfil_completo = _perfil("Motor", (panel_completo,))
    perfil_incompleto = _perfil("Knock", (panel_incompleto,))
    canales = [_canal(rol="engine_speed"), _canal(rol="knock_count")]

    resultado = sugerir_perfiles([perfil_incompleto, perfil_completo], canales)

    assert [s.perfil.nombre for s in resultado] == ["Motor", "Knock"]
    assert resultado[0].proporcion == 1.0
    assert resultado[1].proporcion == 0.5


def test_el_orden_es_determinista_con_el_mismo_empate() -> None:
    """Dos perfiles con exactamente la misma cobertura (1 de 1) se ordenan
    alfabéticamente, sin importar en qué orden se pasaron."""
    panel_a = Panel(titulo="A", elementos=(_elemento(rol="engine_speed", requerido=False),))
    panel_b = Panel(titulo="B", elementos=(_elemento(rol="map", requerido=False),))
    perfil_zeta = _perfil("Zeta", (panel_a,))
    perfil_alfa = _perfil("Alfa", (panel_b,))
    canales = [_canal(rol="engine_speed"), _canal(rol="map")]

    resultado_1 = sugerir_perfiles([perfil_zeta, perfil_alfa], canales)
    resultado_2 = sugerir_perfiles([perfil_alfa, perfil_zeta], canales)

    assert [s.perfil.nombre for s in resultado_1] == ["Alfa", "Zeta"]
    assert [s.perfil.nombre for s in resultado_2] == ["Alfa", "Zeta"]


def test_mejor_sugerencia_devuelve_none_si_nadie_llega_al_minimo() -> None:
    panel = Panel(
        titulo="Knock",
        elementos=(
            _elemento(rol="knock_count", requerido=False),
            _elemento(rol="engine_speed", requerido=False),
            _elemento(rol="map", requerido=False),
            _elemento(rol="lambda_1", requerido=False),
        ),
    )
    perfil = _perfil("Knock", (panel,))
    # Solo 1 de 4: muy por debajo del mínimo por omisión (0.5).
    canales = [_canal(rol="knock_count")]

    assert mejor_sugerencia([perfil], canales) is None


def test_mejor_sugerencia_devuelve_el_primero_si_llega_al_minimo() -> None:
    panel = Panel(titulo="Motor", elementos=(_elemento(rol="engine_speed", requerido=False),))
    perfil = _perfil("Motor", (panel,))
    canales = [_canal(rol="engine_speed")]

    sugerencia = mejor_sugerencia([perfil], canales)

    assert sugerencia is not None
    assert sugerencia.perfil.nombre == "Motor"
    assert sugerencia.frase() == "perfil Motor: 1 de 1 roles disponibles"


def test_sugerir_perfiles_sin_perfiles_da_tupla_vacia() -> None:
    assert sugerir_perfiles([], canales=[]) == ()
    assert mejor_sugerencia([], canales=[]) is None
