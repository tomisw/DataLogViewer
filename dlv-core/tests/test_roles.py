"""Pruebas de la asignación automática de roles (tarea FG-09, docs/07 §7.7).

Lo que más importa proteger, por orden de consecuencia:

1. **Que una asignación DIFUSA nunca se confunda con una firme.** La cuarta
   mitigación de §7.15 (desactivar los detectores críticos D4/D10/D12 cuando
   sus roles vienen de asignación difusa no confirmada) depende enteramente
   de esa distinción. Si `Confianza` se pierde por el camino, la mitigación
   deja de poder implementarse y el sistema avisa en falso -- que es lo que
   §7.15 dice explícitamente que hay que evitar, porque "una alerta falsa
   repetida enseña al usuario a ignorar las alertas".
2. **Que los sinónimos indexados (`{n}`) capturen su índice** y cuenten como
   firmes: el catálogo los declara explícitamente, no son una suposición.
   El fallo aquí no es visible (el rol acaba siendo el correcto), pero
   degrada a DIFUSA algo que no lo es, y con ello desactiva detectores
   críticos sin motivo.
3. Que la normalización sea la de §7.7 (minúsculas, sin acentos, sin
   separadores), para que el catálogo enumere significados y no variantes
   tipográficas.

Todo contra `data/roles.toml` real, no un catálogo de juguete.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlv_core.roles import (
    Confianza,
    Rol,
    asignar_rol,
    cargar_catalogo_roles,
    normalizar,
    resolver_rol,
)

RAIZ = Path(__file__).resolve().parents[2]
ROLES_TOML = RAIZ / "data" / "roles.toml"


@pytest.fixture(scope="module")
def catalogo() -> dict[str, Rol]:
    with ROLES_TOML.open("rb") as fh:
        return cargar_catalogo_roles(fh)


# --------------------------------------------------------------------------- #
# Carga del catálogo real
# --------------------------------------------------------------------------- #
def test_se_cargan_los_roles_del_catalogo_real(catalogo: dict[str, Rol]) -> None:
    assert len(catalogo) == 58  # los 58 roles de F0-10
    assert "meta" not in catalogo  # la sección [meta] no es un rol


def test_los_campos_del_toml_llegan_al_dataclass(catalogo: dict[str, Rol]) -> None:
    rpm = catalogo["engine_speed"]
    assert rpm.dimension == "angular_speed"
    assert rpm.critico is True  # "casi todos los detectores lo usan como contexto"
    assert rpm.plausible_min == pytest.approx(0.0)
    assert rpm.plausible_max == pytest.approx(20000.0)

    knock = catalogo["knock_count"]
    assert knock.indexado is True


def test_el_rango_plausible_detecta_un_error_de_escala(catalogo: dict[str, Rol]) -> None:
    """El fallo que §7.5 quiere atrapar: nombre bien mapeado, escala mal. Un
    régimen de 20 millones no es un motor mal afinado, es un factor
    equivocado."""
    rpm = catalogo["engine_speed"]
    assert rpm.es_plausible(6500.0)
    assert not rpm.es_plausible(20_000_000.0)


def test_un_rol_sin_rango_declarado_acepta_todo(catalogo: dict[str, Rol]) -> None:
    rol = Rol(id="x", dimension=None, sinonimos=())
    assert rol.es_plausible(-1e30)
    assert rol.es_plausible(1e30)


# --------------------------------------------------------------------------- #
# Normalización (§7.7)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Engine Speed", "enginespeed"),
        ("EngineSpeed", "enginespeed"),
        ("engine_speed", "enginespeed"),
        ("ENGINE-SPEED", "enginespeed"),
        ("Régimen", "regimen"),
        ("Inyección", "inyeccion"),
        ("Fuel - Load", "fuelload"),
    ],
)
def test_la_normalizacion_ignora_mayusculas_acentos_y_separadores(
    entrada: str, esperado: str
) -> None:
    assert normalizar(entrada) == esperado


# --------------------------------------------------------------------------- #
# Coincidencia exacta
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("nombre", ["RPM", "Engine Speed", "engine_speed", "Régimen", "rpm"])
def test_sinonimos_del_catalogo_dan_coincidencia_exacta(
    nombre: str, catalogo: dict[str, Rol]
) -> None:
    asignacion = asignar_rol(nombre, catalogo)

    assert asignacion is not None
    assert asignacion.rol == "engine_speed"
    assert asignacion.confianza is Confianza.EXACTA
    assert asignacion.requiere_confirmacion is False


def test_una_variante_tipografica_no_declarada_sigue_siendo_exacta(
    catalogo: dict[str, Rol],
) -> None:
    """ "ENGINE  SPEED" no está en el catálogo, pero normaliza igual que
    "Engine Speed", que sí. Es justo lo que la normalización compra."""
    asignacion = asignar_rol("ENGINE  SPEED", catalogo)

    assert asignacion is not None
    assert asignacion.confianza is Confianza.EXACTA


# --------------------------------------------------------------------------- #
# Sinónimos indexados: `{n}` (el bug que costó una ronda)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("nombre", "rol_esperado", "indice_esperado"),
    [
        ("Knock Sensor 2 Knock Count", "knock_count", 2),
        ("KnockCount3", "knock_count", 3),
        ("Wideband O2 1", "lambda_measured", 1),
    ],
)
def test_los_sinonimos_indexados_capturan_su_indice_y_son_firmes(
    nombre: str, rol_esperado: str, indice_esperado: int, catalogo: dict[str, Rol]
) -> None:
    """INDEXADA, no DIFUSA: la plantilla `{n}` es explícita en el catálogo.
    Degradarla a difusa desactivaría detectores críticos sin motivo."""
    asignacion = asignar_rol(nombre, catalogo)

    assert asignacion is not None
    assert asignacion.rol == rol_esperado
    assert asignacion.confianza is Confianza.INDEXADA
    assert asignacion.indice == indice_esperado
    assert asignacion.requiere_confirmacion is False


def test_el_sinonimo_sin_indice_sigue_funcionando_aparte(catalogo: dict[str, Rol]) -> None:
    """ "Wideband O2" (sin número) y "Wideband O2 1" son ambos válidos y no se
    estorban: uno es exacto, el otro indexado."""
    sin_indice = asignar_rol("Wideband O2", catalogo)
    con_indice = asignar_rol("Wideband O2 1", catalogo)

    assert sin_indice is not None and con_indice is not None
    assert sin_indice.confianza is Confianza.EXACTA
    assert sin_indice.indice is None
    assert con_indice.confianza is Confianza.INDEXADA
    assert con_indice.indice == 1


def test_una_letra_donde_va_el_indice_no_cuenta_como_indexada(
    catalogo: dict[str, Rol],
) -> None:
    """`{n}` captura DÍGITOS. Un canal llamado literalmente "Knock Sensor N
    Knock Count" no es el sensor número N: es otro nombre. Este test es el
    que detecta que se normalice antes de partir por la marca (que
    convertiría `{n}` en una `n` suelta y haría coincidir esto por error)."""
    asignacion = asignar_rol("Knock Sensor N Knock Count", catalogo)

    if asignacion is not None:
        assert asignacion.confianza is not Confianza.INDEXADA


# --------------------------------------------------------------------------- #
# Difuso: el último recurso, y la mitigación de R10
# --------------------------------------------------------------------------- #
def test_un_nombre_con_una_errata_cae_en_difusa_y_pide_confirmacion(
    catalogo: dict[str, Rol],
) -> None:
    asignacion = asignar_rol("Engine Speeed", catalogo)  # errata deliberada

    assert asignacion is not None
    assert asignacion.rol == "engine_speed"
    assert asignacion.confianza is Confianza.DIFUSA
    assert asignacion.requiere_confirmacion is True
    assert 0.85 <= asignacion.parecido < 1.0


def test_un_nombre_sin_nada_que_ver_no_se_asigna(catalogo: dict[str, Rol]) -> None:
    """`Ambient Light Level` existe de verdad en el AutoLog y no es ningún rol
    (docs/01 §1.9 lo cita como el único resultado de buscar "ambiente").
    Inventarle un rol sería peor que dejarlo sin asignar."""
    assert asignar_rol("Ambient Light Level", catalogo) is None


def test_un_nombre_vacio_no_se_asigna(catalogo: dict[str, Rol]) -> None:
    assert asignar_rol("", catalogo) is None
    assert asignar_rol("   ", catalogo) is None


def test_subir_el_umbral_difuso_descarta_la_errata(catalogo: dict[str, Rol]) -> None:
    """El umbral es un parámetro, no una constante escondida."""
    assert asignar_rol("Engine Speeed", catalogo, umbral_difuso=0.99) is None


def test_solo_lo_difuso_requiere_confirmacion(catalogo: dict[str, Rol]) -> None:
    """La propiedad de la que depende la mitigación 4 de §7.15, comprobada
    sobre las tres confianzas a la vez."""
    exacta = asignar_rol("RPM", catalogo)
    indexada = asignar_rol("Knock Sensor 2 Knock Count", catalogo)
    difusa = asignar_rol("Engine Speeed", catalogo)

    assert exacta is not None and indexada is not None and difusa is not None
    assert exacta.requiere_confirmacion is False
    assert indexada.requiere_confirmacion is False
    assert difusa.requiere_confirmacion is True


# --------------------------------------------------------------------------- #
# El atajo `resolver_rol`
# --------------------------------------------------------------------------- #
def test_resolver_rol_devuelve_solo_el_identificador(catalogo: dict[str, Rol]) -> None:
    assert resolver_rol("RPM", catalogo) == "engine_speed"
    assert resolver_rol("Ambient Light Level", catalogo) is None


# --------------------------------------------------------------------------- #
# Contra los nombres de canal reales del AutoLog
# --------------------------------------------------------------------------- #
def test_los_canales_criticos_del_autolog_real_se_asignan_de_forma_firme(
    catalogo: dict[str, Rol],
) -> None:
    """Nombres tomados literalmente de la cabecera de
    samples/real/AutoLog_20260729_1830.csv. Si alguno de estos cayera en
    difusa, los detectores críticos quedarían desactivados en el log del
    propietario."""
    for nombre, rol_esperado in [
        ("RPM", "engine_speed"),
        ("Coolant Temperature", "coolant_temp"),
        ("Fuel Tuning Current Stoichiometry", "stoichiometry"),
    ]:
        asignacion = asignar_rol(nombre, catalogo)
        assert asignacion is not None, f"{nombre!r} quedó sin asignar"
        assert asignacion.rol == rol_esperado
        assert asignacion.requiere_confirmacion is False, (
            f"{nombre!r} cayó en difusa: desactivaría detectores críticos"
        )
