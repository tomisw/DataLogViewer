"""Pruebas del modelo de perfil de análisis `.dlvprofile` (F3-01).

Especificación: `docs/02-alcance-y-plan.md` E4.1 y
`docs/04-perfiles-motorsport.md` §4.2. Lo que protege esta suite, por orden de
consecuencia (docs/09 §9.9):

1. **Identidad por rol, nunca por ID nativo como requisito.** Es la razón de
   existir del perfil (docs/07 §7.12): `test_rol_e_id_nativo_son_mutuamente_excluyentes`
   y `test_un_id_nativo_no_puede_ser_requerido` comprueban que el esquema lo
   hace estructuralmente imposible, no solo "mal visto".
2. **Requerido/opcional se agrega correctamente para calcular cobertura**
   (E4.5): `test_roles_requeridos_y_referenciados_de_un_panel` y su equivalente
   a nivel de perfil.
3. **Las unidades por dimensión viajan sin traducción** hacia
   `resolucion_unidad.resolver_unidad(preferencias_perfil=...)`:
   `test_a_preferencias_unidad_es_la_forma_exacta_del_precedente`.
4. **Los límites de alerta reutilizan `dlv_core.topes`** (Tope/TopeDeBanda/
   Curva) en vez de duplicarlos, incluida la curva de D10 (presión de aceite
   en función del régimen): `test_limite_con_curva_ida_y_vuelta`.
5. **Versión desconocida se rechaza entera**, igual que `.dlvimport`:
   `test_version_desconocida_se_rechaza`.
6. **Un perfil corrupto se rechaza con un mensaje que dice qué falta**, nunca
   con un `KeyError`/`TypeError` desnudo: la sección "perfil corrupto".
7. **Ida y vuelta exacta por `dict` y por texto JSON.**
8. **Los diez perfiles de fábrica de docs/04 §4.2 son expresables** con este
   esquema: `test_los_diez_perfiles_de_fabrica_son_expresables` construye una
   versión representativa de cada uno (paneles y roles reales del documento,
   con reserva a `id_nativo` donde `data/roles.toml` no tiene rol universal) y
   comprueba que ninguno lanza `ErrorDePerfil`.

Solo biblioteca estándar (`pytest` aparte, ya usado en todo `dlv-core`).
"""

from __future__ import annotations

import pytest

from dlv_core.perfil import (
    VERSION_ESQUEMA_PERFIL,
    ElementoDePanel,
    ErrorDePerfil,
    ErrorDeVersionDePerfilDesconocida,
    LimiteDeAlerta,
    Panel,
    Perfil,
)
from dlv_core.primitivas import Direccion
from dlv_core.topes import CurvaLineal, CurvaPorPuntos, NivelDeTope, Tope, TopeDeBanda

# --------------------------------------------------------------------------- #
# Fábricas de prueba
# --------------------------------------------------------------------------- #


def _elemento(rol: str, *, requerido: bool = True, indice: int | None = None) -> ElementoDePanel:
    return ElementoDePanel(rol=rol, id_nativo=None, requerido=requerido, indice=indice)


def _panel_carga() -> Panel:
    return Panel(
        titulo="Carga",
        elementos=(
            _elemento("engine_speed"),
            _elemento("throttle_position"),
            _elemento("manifold_pressure"),
        ),
    )


def _panel_mezcla() -> Panel:
    return Panel(
        titulo="Mezcla",
        elementos=(
            _elemento("lambda_measured"),
            _elemento("lambda_target"),
        ),
    )


def _perfil_minimo(**overrides: object) -> Perfil:
    base: dict[str, object] = {
        "nombre": "P1 — Fuel / Lambda",
        "descripcion": "Cierre del lazo de mezcla",
        "paneles": (_panel_carga(), _panel_mezcla()),
        "unidades": {"pressure": "kpa", "temperature": "celsius"},
        "limites": (),
        "detectores_activos": ("D4", "D5"),
        "eje_x_preferido": None,
    }
    base.update(overrides)
    return Perfil(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Decisión 1 — identidad por rol, reserva estrecha a ID nativo
# --------------------------------------------------------------------------- #
def test_rol_e_id_nativo_son_mutuamente_excluyentes() -> None:
    with pytest.raises(ErrorDePerfil, match="EXACTAMENTE UNO"):
        ElementoDePanel(rol="engine_speed", id_nativo="Haltech-123", requerido=False)
    with pytest.raises(ErrorDePerfil, match="EXACTAMENTE UNO"):
        ElementoDePanel(rol=None, id_nativo=None, requerido=False)


def test_un_id_nativo_no_puede_ser_requerido() -> None:
    """El caso de P5 (Transient Throttle) y de los términos PID de boost de
    P3: canales muy específicos de Haltech sin rol universal (docs/07 §7.12).
    Marcarlos requeridos rompería el perfil en cualquier otro formato."""
    with pytest.raises(ErrorDePerfil, match="no puede ser"):
        ElementoDePanel(
            rol=None, id_nativo="Transient Throttle Enrichment Start Load", requerido=True
        )

    # No requerido sí es válido: el elemento se dibuja solo si el formato es
    # Haltech y trae ese ID; en cualquier otro formato, simplemente no aparece.
    elemento = ElementoDePanel(
        rol=None, id_nativo="Transient Throttle Enrichment Start Load", requerido=False
    )
    assert elemento.requerido is False
    assert elemento.clave == ("Transient Throttle Enrichment Start Load", None)


def test_panel_rechaza_elementos_duplicados() -> None:
    with pytest.raises(ErrorDePerfil, match="repite el elemento"):
        Panel(
            titulo="Knock",
            elementos=(_elemento("knock_level", indice=1), _elemento("knock_level", indice=1)),
        )


def test_panel_admite_el_mismo_rol_con_indices_distintos() -> None:
    """`knock_level` sensor 1 y sensor 2 en el mismo panel (P2): mismo rol,
    índice distinto, no es una colisión."""
    panel = Panel(
        titulo="Knock",
        elementos=(_elemento("knock_level", indice=1), _elemento("knock_level", indice=2)),
    )
    assert len(panel.elementos) == 2


# --------------------------------------------------------------------------- #
# Decisión 2 — requerido/opcional por panel, cobertura por perfil
# --------------------------------------------------------------------------- #
def test_roles_requeridos_y_referenciados_de_un_panel() -> None:
    panel = Panel(
        titulo="Carga",
        elementos=(
            _elemento("engine_speed", requerido=True),
            _elemento("manifold_pressure", requerido=False),
        ),
    )
    assert panel.roles_requeridos == frozenset({"engine_speed"})
    assert panel.roles_opcionales == frozenset({"manifold_pressure"})
    assert panel.roles_referenciados == frozenset({"engine_speed", "manifold_pressure"})


def test_roles_requeridos_del_perfil_es_la_union_de_sus_paneles() -> None:
    perfil = _perfil_minimo()
    # Los dos paneles de _perfil_minimo marcan todo requerido=True (por
    # omisión de _elemento), así que la unión son los 5 roles de sus paneles.
    assert perfil.roles_requeridos == frozenset(
        {
            "engine_speed",
            "throttle_position",
            "manifold_pressure",
            "lambda_measured",
            "lambda_target",
        }
    )


def test_roles_referenciados_incluye_los_de_los_limites_y_sus_curvas() -> None:
    """El denominador de "7 de 9 roles disponibles" (E4.5) tiene que incluir
    también el rol de referencia de una curva (p. ej. `engine_speed` para la
    curva de presión de aceite de D10), no solo lo que hay en los paneles."""
    limite = LimiteDeAlerta(
        rol="oil_pressure",
        topes=(
            Tope(
                nivel=NivelDeTope.CRITICO,
                direccion=Direccion.ABAJO,
                valor=CurvaLineal(
                    rol_referencia="engine_speed",
                    base=201.3,
                    pendiente=100.0,
                    divisor_referencia=1000.0,
                ),
            ),
        ),
    )
    panel = Panel(titulo="Presiones", elementos=(_elemento("oil_pressure"),))
    perfil = _perfil_minimo(paneles=(panel,), limites=(limite,))
    assert "engine_speed" in perfil.roles_referenciados
    assert "oil_pressure" in perfil.roles_referenciados


def test_un_panel_sin_elementos_se_rechaza() -> None:
    with pytest.raises(ErrorDePerfil, match="no tiene ningún elemento"):
        Panel(titulo="Vacío", elementos=())


def test_un_perfil_sin_paneles_se_rechaza() -> None:
    with pytest.raises(ErrorDePerfil, match="no tiene ningún panel"):
        _perfil_minimo(paneles=())


# --------------------------------------------------------------------------- #
# Decisión 3 — unidades por dimensión, canónica, mismo contrato que
# resolucion_unidad.resolver_unidad
# --------------------------------------------------------------------------- #
def test_a_preferencias_unidad_es_la_forma_exacta_del_precedente() -> None:
    """`resolucion_unidad.py` (F1-17) dejó escrito: «cuando exista un modelo
    de perfil de verdad (F3-01), su capa de dimensiones puede pasarse aquí
    tal cual». Esta prueba comprueba justamente eso: sin conversión."""
    perfil = _perfil_minimo(unidades={"pressure": "psi", "temperature": "fahrenheit"})
    assert perfil.a_preferencias_unidad() == {"pressure": "psi", "temperature": "fahrenheit"}
    assert perfil.a_preferencias_unidad() is perfil.unidades


def test_unidades_con_entrada_vacia_se_rechaza() -> None:
    with pytest.raises(ErrorDePerfil, match="entrada vacía"):
        _perfil_minimo(unidades={"pressure": ""})


def test_limite_con_curva_ida_y_vuelta() -> None:
    """El caso D10 (docs/04 §4.2 P8): presión de aceite mínima en función del
    régimen. `base_kpa`/`pendiente` en canónica (kPa, rpm), tal como los usa
    `data/umbrales.toml` para el mismo detector."""
    curva = CurvaLineal(
        rol_referencia="engine_speed", base=201.3, pendiente=100.0, divisor_referencia=1000.0
    )
    tope = Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=curva)
    limite = LimiteDeAlerta(rol="oil_pressure", topes=(tope,))
    panel = Panel(titulo="Presiones", elementos=(_elemento("oil_pressure"),))
    perfil = _perfil_minimo(paneles=(panel,), limites=(limite,))

    reconstruido = Perfil.desde_dict(perfil.a_dict())
    assert len(reconstruido.limites) == 1
    (limite_reconstruido,) = reconstruido.limites
    (tope_reconstruido,) = limite_reconstruido.topes
    assert isinstance(tope_reconstruido.valor, CurvaLineal)
    assert tope_reconstruido.valor.rol_referencia == "engine_speed"
    assert tope_reconstruido.valor.base == 201.3
    assert tope_reconstruido.valor.pendiente == 100.0
    assert tope_reconstruido.direccion is Direccion.ABAJO
    assert tope_reconstruido.nivel is NivelDeTope.CRITICO


def test_limite_con_banda_de_puntos_ida_y_vuelta() -> None:
    banda = TopeDeBanda(
        nivel=NivelDeTope.AVISO,
        minimo=CurvaPorPuntos(rol_referencia="engine_load", puntos=((0.0, 0.9), (1.0, 0.95))),
        maximo=1.05,
    )
    limite = LimiteDeAlerta(rol="lambda_measured", banda=banda)
    perfil = _perfil_minimo(limites=(limite,))

    reconstruido = Perfil.desde_dict(perfil.a_dict())
    (limite_reconstruido,) = reconstruido.limites
    assert limite_reconstruido.banda is not None
    assert isinstance(limite_reconstruido.banda.minimo, CurvaPorPuntos)
    assert limite_reconstruido.banda.maximo == 1.05


def test_limite_no_puede_declarar_topes_y_banda_a_la_vez() -> None:
    tope = Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ARRIBA, valor=1.0)
    banda = TopeDeBanda(nivel=NivelDeTope.AVISO, minimo=0.0, maximo=1.0)
    with pytest.raises(ErrorDePerfil, match="topes unidireccionales Y una banda"):
        LimiteDeAlerta(rol="x", topes=(tope,), banda=banda)


def test_limite_sin_tope_ni_banda_se_rechaza() -> None:
    with pytest.raises(ErrorDePerfil, match="no declara ningún tope ni banda"):
        LimiteDeAlerta(rol="x")


def test_limite_con_dos_topes_del_mismo_nivel_se_rechaza() -> None:
    with pytest.raises(ErrorDePerfil, match="más de un tope del mismo nivel"):
        LimiteDeAlerta(
            rol="coolant_temp",
            topes=(
                Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ARRIBA, valor=1.0),
                Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ARRIBA, valor=2.0),
            ),
        )


def test_limite_reutiliza_validar_pareja_de_topes() -> None:
    """Aviso por ENCIMA del crítico (en dirección ARRIBA) es la contradicción
    que `topes.validar_pareja` ya detecta: el crítico saltaría antes y el
    aviso no avisaría de nada. Este esquema no reimplementa la comprobación,
    la reutiliza."""
    with pytest.raises(ErrorDePerfil, match="tiene que ser menor o igual"):
        LimiteDeAlerta(
            rol="coolant_temp",
            topes=(
                Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ARRIBA, valor=400.0),
                Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ARRIBA, valor=390.0),
            ),
        )


def test_perfil_rechaza_dos_limites_para_el_mismo_rol() -> None:
    limite_a = LimiteDeAlerta(
        rol="oil_pressure", topes=(Tope(NivelDeTope.AVISO, Direccion.ABAJO, 300.0),)
    )
    limite_b = LimiteDeAlerta(
        rol="oil_pressure", topes=(Tope(NivelDeTope.CRITICO, Direccion.ABAJO, 250.0),)
    )
    with pytest.raises(ErrorDePerfil, match="más de un límite de alerta"):
        _perfil_minimo(limites=(limite_a, limite_b))


def test_perfil_rechaza_detectores_activos_repetidos() -> None:
    with pytest.raises(ErrorDePerfil, match="repite un detector"):
        _perfil_minimo(detectores_activos=("D1", "D1"))


# --------------------------------------------------------------------------- #
# Decisión 4 — versionado
# --------------------------------------------------------------------------- #
def test_version_desconocida_se_rechaza() -> None:
    bruto = _perfil_minimo().a_dict()
    bruto["version_esquema"] = 99
    with pytest.raises(ErrorDeVersionDePerfilDesconocida, match="versión de esquema"):
        Perfil.desde_dict(bruto)


def test_falta_version_se_rechaza() -> None:
    bruto = _perfil_minimo().a_dict()
    del bruto["version_esquema"]
    with pytest.raises(ErrorDePerfil, match="falta la clave"):
        Perfil.desde_dict(bruto)


def test_version_esquema_actual_es_1() -> None:
    """Ancla explícita: si esto cambia sin querer, algo movió la versión sin
    que nadie lo decidiera."""
    assert VERSION_ESQUEMA_PERFIL == 1


# --------------------------------------------------------------------------- #
# Perfil corrupto: mensajes que dicen QUÉ falta y DÓNDE
# --------------------------------------------------------------------------- #
def test_perfil_corrupto_nombre_vacio() -> None:
    bruto = _perfil_minimo().a_dict()
    bruto["nombre"] = "   "
    with pytest.raises(ErrorDePerfil, match="nombre"):
        Perfil.desde_dict(bruto)


def test_perfil_corrupto_paneles_no_es_lista() -> None:
    bruto = _perfil_minimo().a_dict()
    bruto["paneles"] = "no es una lista"
    with pytest.raises(ErrorDePerfil, match="paneles"):
        Perfil.desde_dict(bruto)


def test_perfil_corrupto_elemento_sin_requerido_dice_donde() -> None:
    bruto = _perfil_minimo().a_dict()
    del bruto["paneles"][0]["elementos"][0]["requerido"]
    with pytest.raises(ErrorDePerfil, match=r"paneles\[0\]\.elementos\[0\]"):
        Perfil.desde_dict(bruto)


def test_perfil_no_es_un_objeto_json() -> None:
    with pytest.raises(ErrorDePerfil, match="raíz del JSON"):
        Perfil.desde_texto_json("[1, 2, 3]")


def test_json_invalido_se_rechaza() -> None:
    with pytest.raises(ErrorDePerfil, match="JSON inválido"):
        Perfil.desde_texto_json("{no es json")


# --------------------------------------------------------------------------- #
# Ida y vuelta
# --------------------------------------------------------------------------- #
def test_ida_y_vuelta_por_dict() -> None:
    original = _perfil_minimo()
    reconstruido = Perfil.desde_dict(original.a_dict())
    assert reconstruido.a_dict() == original.a_dict()


def test_ida_y_vuelta_por_texto_json() -> None:
    original = _perfil_minimo()
    reconstruido = Perfil.desde_texto_json(original.a_texto_json())
    assert reconstruido.a_dict() == original.a_dict()


def test_eje_x_preferido_viaja_ida_y_vuelta() -> None:
    perfil = _perfil_minimo(eje_x_preferido="engine_speed")
    reconstruido = Perfil.desde_texto_json(perfil.a_texto_json())
    assert reconstruido.eje_x_preferido == "engine_speed"


def test_escala_manual_de_un_elemento_viaja_ida_y_vuelta() -> None:
    elemento = ElementoDePanel(
        rol="coolant_temp", id_nativo=None, requerido=True, escala_min=253.15, escala_max=423.15
    )
    panel = Panel(titulo="Térmico", elementos=(elemento,))
    perfil = _perfil_minimo(paneles=(panel,))
    reconstruido = Perfil.desde_dict(perfil.a_dict())
    (elemento_reconstruido,) = reconstruido.paneles[0].elementos
    assert elemento_reconstruido.escala_min == 253.15
    assert elemento_reconstruido.escala_max == 423.15


def test_escala_min_debe_ser_menor_que_escala_max() -> None:
    with pytest.raises(ErrorDePerfil, match="menor que"):
        ElementoDePanel(
            rol="coolant_temp", id_nativo=None, requerido=True, escala_min=400.0, escala_max=300.0
        )


# --------------------------------------------------------------------------- #
# Comprobación contra los diez perfiles de fábrica de docs/04 §4.2
# --------------------------------------------------------------------------- #
def _e(
    rol: str | None = None,
    id_nativo: str | None = None,
    *,
    requerido: bool = True,
    indice: int | None = None,
) -> ElementoDePanel:
    return ElementoDePanel(rol=rol, id_nativo=id_nativo, requerido=requerido, indice=indice)


def _perfil_p1_fuel_lambda() -> Perfil:
    return Perfil(
        nombre="P1 — Fuel / Lambda",
        descripcion="Cierre del lazo de mezcla",
        unidades={},
        paneles=(
            Panel("Carga", (_e("engine_speed"), _e("throttle_position"), _e("manifold_pressure"))),
            Panel(
                "Mezcla",
                (
                    _e("lambda_measured"),
                    _e("lambda_target"),
                    # "λ error" es un canal matemático (docs/04 §4.5), no un rol
                    # de catálogo: se referencia como reserva nativa hasta que
                    # exista un rol de biblioteca para canales calculados.
                    _e(id_nativo="lambda_error", requerido=False),
                ),
            ),
            Panel(
                "Correcciones",
                (
                    _e("fuel_trim_short", indice=1, requerido=False),
                    _e("fuel_trim_long", indice=1, requerido=False),
                    _e(id_nativo="Fuel MAP Correction", requerido=False),
                    _e(id_nativo="Fuel Coolant Temperature Correction", requerido=False),
                ),
            ),
            Panel(
                "Inyección",
                (
                    _e("injector_duty", indice=1),
                    _e("injector_pulsewidth", indice=1, requerido=False),
                    _e("fuel_pressure_differential", requerido=False),
                    _e("fuel_pressure", requerido=False),
                ),
            ),
            Panel(
                "Estado",
                (
                    _e(id_nativo="Decel Cut State", requerido=False),
                    _e("protection_cause", requerido=False),
                ),
            ),
        ),
        limites=(
            LimiteDeAlerta(
                rol="injector_duty",
                topes=(Tope(NivelDeTope.AVISO, Direccion.ARRIBA, 0.85),),
            ),
        ),
        detectores_activos=("D4", "D5", "D8"),
    )


def _perfil_p2_knock() -> Perfil:
    return Perfil(
        nombre="P2 — Knock / detonación",
        descripcion="No perder ni un evento",
        unidades={},
        paneles=(
            Panel("Carga", (_e("engine_speed"), _e("manifold_pressure"), _e("throttle_position"))),
            Panel(
                "Knock",
                (
                    _e("knock_level", indice=1),
                    _e("knock_level", indice=2, requerido=False),
                    _e("knock_threshold"),
                ),
            ),
            Panel(
                "Conteos",
                (_e("knock_count", indice=1), _e("knock_count", indice=2, requerido=False)),
            ),
            Panel(
                "Respuesta",
                (
                    _e("knock_retard", indice=1),
                    _e("knock_retard", indice=2, requerido=False),
                    _e("ignition_advance", requerido=False),
                ),
            ),
            Panel(
                "Contexto",
                (
                    _e("intake_air_temp", requerido=False),
                    _e("coolant_temp", requerido=False),
                    _e("lambda_measured", requerido=False),
                ),
            ),
            # "Knock State" / "Knock Detection Active State" no tienen rol
            # universal en data/roles.toml: se referencian por id_nativo.
            Panel(
                "Estado",
                (
                    _e(id_nativo="Knock State", requerido=False),
                    _e(id_nativo="Knock Detection Active State", requerido=False),
                ),
            ),
        ),
        limites=(
            LimiteDeAlerta(
                rol="knock_count", topes=(Tope(NivelDeTope.AVISO, Direccion.ARRIBA, 0.0),)
            ),
        ),
        detectores_activos=("D1", "D2", "D3"),
    )


def _perfil_p3_boost() -> Perfil:
    return Perfil(
        nombre="P3 — Boost control",
        descripcion="Presión",
        unidades={},
        paneles=(
            Panel(
                "Presión",
                (
                    _e("boost_pressure_actual"),
                    _e("boost_pressure_target"),
                    _e(id_nativo="Boost Control Target Pressure (Corrected)", requerido=False),
                ),
            ),
            Panel("Salida", (_e("boost_output"), _e("wastegate_duty", requerido=False))),
            # Los términos PID de boost: sin rol universal (docs/07 §7.12).
            Panel(
                "Términos PID",
                (
                    _e(id_nativo="Boost Control Proportional Output", requerido=False),
                    _e(id_nativo="Boost Control Integral Output", requerido=False),
                    _e(id_nativo="Boost Control Derivative Output", requerido=False),
                ),
            ),
            Panel(
                "Estado",
                (_e(id_nativo="Boost Control State", requerido=False),),
            ),
        ),
        limites=(
            LimiteDeAlerta(
                rol="boost_pressure_actual",
                topes=(Tope(NivelDeTope.CRITICO, Direccion.ARRIBA, 350.0),),
            ),
        ),
        detectores_activos=("D6", "D7"),
    )


def _perfil_p4_ignition() -> Perfil:
    return Perfil(
        nombre="P4 — Ignition",
        descripcion="Avance de encendido",
        unidades={},
        paneles=(
            Panel(
                "Encendido",
                (
                    _e("ignition_advance"),
                    _e("ignition_advance_base", requerido=False),
                    _e("ignition_correction_total", requerido=False),
                    # correcciones específicas sin rol universal (docs/07 §7.12)
                    _e(id_nativo="Coolant Temperature Ignition Correction", requerido=False),
                    _e(id_nativo="Air Temperature Ignition Correction", requerido=False),
                    _e("dwell_time", indice=1, requerido=False),
                ),
            ),
        ),
        limites=(),
        detectores_activos=(),
    )


def _perfil_p5_transient() -> Perfil:
    return Perfil(
        nombre="P5 — Transient / tip-in",
        descripcion="Excursión de λ tras un tip-in",
        unidades={},
        paneles=(
            Panel(
                "Transitorio",
                (
                    _e(id_nativo="Throttle Position Derivative", requerido=False),
                    _e(id_nativo="Transient Throttle Load Derivative", requerido=False),
                    _e(id_nativo="Transient Throttle Fuel Enrichment Rate", requerido=False),
                    _e(id_nativo="Transient Throttle Fuel Disenrichment Rate", requerido=False),
                    _e(id_nativo="Transient Throttle Enrichment Start Load", requerido=False),
                    _e("lambda_measured"),
                    _e("lambda_target"),
                ),
            ),
        ),
        limites=(),
        detectores_activos=("D15",),
    )


def _perfil_p6_idle() -> Perfil:
    return Perfil(
        nombre="P6 — Idle control",
        descripcion="Control de ralentí",
        unidades={},
        paneles=(
            Panel(
                "Ralentí",
                (
                    _e("engine_speed"),
                    _e(id_nativo="Idle Control target RPM", requerido=False),
                    _e(id_nativo="Idle Control RPM error", requerido=False),
                    _e(id_nativo="Idle Control Output", requerido=False),
                ),
            ),
            Panel("Estado", (_e("idle_state", requerido=False),)),
        ),
        limites=(),
        detectores_activos=(),
    )


def _perfil_p7_trigger() -> Perfil:
    """El perfil más dependiente de `id_nativo`: la mayoría de sus canales son
    diagnóstico interno de Haltech sin equivalente universal (docs/04 §4.2 P7).
    Solo `trigger_errors` tiene rol de catálogo."""
    return Perfil(
        nombre="P7 — Trigger / salud de sincronización",
        descripcion="Diagnóstico de sincronización",
        unidades={},
        paneles=(
            Panel(
                "Trigger",
                (
                    _e("trigger_errors", requerido=False),
                    _e(id_nativo="Trigger System Error Count", requerido=False),
                    _e(id_nativo="Trigger Synchronisation Level", requerido=False),
                    _e(id_nativo="Trigger Sync Offset", requerido=False),
                    _e(id_nativo="Trigger Tooth Count", requerido=False),
                ),
            ),
        ),
        limites=(),
        detectores_activos=("D12",),
    )


def _perfil_p8_salud_motor() -> Perfil:
    return Perfil(
        nombre="P8 — Salud del motor y protecciones",
        descripcion="Protecciones",
        unidades={},
        paneles=(
            Panel(
                "Térmico y presiones",
                (
                    _e("coolant_temp"),
                    _e("oil_temp", requerido=False),
                    _e("oil_pressure"),
                    _e("intake_air_temp", requerido=False),
                    _e("ecu_temp", requerido=False),
                    _e("battery_voltage"),
                ),
            ),
            Panel(
                "Estado",
                (
                    _e("protection_level", requerido=False),
                    _e("protection_cause", requerido=False),
                    _e("cut_percentage", requerido=False),
                    _e("limiter_active", requerido=False),
                ),
            ),
        ),
        limites=(
            LimiteDeAlerta(
                rol="oil_pressure",
                topes=(
                    Tope(
                        nivel=NivelDeTope.CRITICO,
                        direccion=Direccion.ABAJO,
                        valor=CurvaLineal(
                            rol_referencia="engine_speed",
                            base=201.3,
                            pendiente=100.0,
                            divisor_referencia=1000.0,
                        ),
                    ),
                ),
            ),
            LimiteDeAlerta(
                rol="coolant_temp",
                topes=(Tope(NivelDeTope.AVISO, Direccion.ARRIBA, 378.15),),
            ),
        ),
        detectores_activos=("D9", "D10", "D11", "D13", "D14"),
    )


def _perfil_p9_diagnostico() -> Perfil:
    return Perfil(
        nombre="P9 — Diagnóstico de sensores",
        descripcion="Canales pegados, saturación, ruido",
        unidades={},
        paneles=(
            Panel(
                "Sensores",
                (
                    _e("sensor_voltage", indice=1, requerido=False),
                    _e("sensor_voltage", indice=2, requerido=False),
                    _e(id_nativo="Diagnostic Analogue 5V rail", requerido=False),
                    _e("battery_voltage"),
                ),
            ),
        ),
        limites=(),
        detectores_activos=("D16", "D17"),
    )


def _perfil_p10_launch() -> Perfil:
    return Perfil(
        nombre="P10 — Launch control",
        descripcion="Control de salida",
        unidades={},
        paneles=(
            Panel(
                "Launch",
                (
                    _e("launch_state", requerido=False),
                    _e(id_nativo="Launch Control RPM Error", requerido=False),
                    _e(id_nativo="Launch Control End RPM", requerido=False),
                    _e("cut_percentage", requerido=False),
                    _e("engine_speed"),
                    _e("vehicle_speed", requerido=False),
                    _e("driven_wheel_speed", requerido=False),
                ),
            ),
        ),
        limites=(),
        detectores_activos=(),
    )


_PERFILES_DE_FABRICA = (
    _perfil_p1_fuel_lambda,
    _perfil_p2_knock,
    _perfil_p3_boost,
    _perfil_p4_ignition,
    _perfil_p5_transient,
    _perfil_p6_idle,
    _perfil_p7_trigger,
    _perfil_p8_salud_motor,
    _perfil_p9_diagnostico,
    _perfil_p10_launch,
)


@pytest.mark.parametrize(
    "fabrica", _PERFILES_DE_FABRICA, ids=[f.__name__ for f in _PERFILES_DE_FABRICA]
)
def test_los_diez_perfiles_de_fabrica_son_expresables(fabrica: object) -> None:
    """Construye una versión representativa de cada uno de los diez perfiles
    de `docs/04-perfiles-motorsport.md` §4.2 con este esquema, y comprueba
    ida y vuelta por JSON. No transcribe cada canal citado en el documento
    (serían más de cien elementos): basta con que la FORMA de cada perfil —
    sus paneles, sus roles críticos, sus reservas a id_nativo, sus curvas y
    sus detectores— sea representativa y no lance `ErrorDePerfil`."""
    perfil = fabrica()  # type: ignore[operator]
    assert isinstance(perfil, Perfil)
    reconstruido = Perfil.desde_texto_json(perfil.a_texto_json())
    assert reconstruido.a_dict() == perfil.a_dict()


def test_p7_trigger_depende_casi_por_completo_de_id_nativo() -> None:
    """Hallazgo del informe de la tarea: de los canales de P7 solo
    `trigger_errors` tiene rol universal en `data/roles.toml`; el resto son
    diagnóstico interno de Haltech. No es un fallo del esquema -- es la
    reserva de §7.12 funcionando como se espera -- pero es una limitación
    real de portabilidad que F3-03 tiene que conocer al escribir el perfil
    de verdad."""
    perfil = _perfil_p7_trigger()
    elementos = perfil.paneles[0].elementos
    con_id_nativo = [e for e in elementos if e.id_nativo is not None]
    con_rol = [e for e in elementos if e.rol is not None]
    assert len(con_id_nativo) == 4
    assert len(con_rol) == 1
