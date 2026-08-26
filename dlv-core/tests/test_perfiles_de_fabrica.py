"""Pruebas de los diez `.dlvprofile` de fábrica de `data/perfiles/` (F3-03).

QUÉ PROTEGE ESTA SUITE
======================
Los diez ficheros son datos, generados por
`tools/generar_perfiles_de_fabrica.py` a partir de
`docs/04-perfiles-motorsport.md` §4.2 y del catálogo VIGENTE de
`data/roles.toml`. Un perfil de fábrica que no carga es un fallo de arranque
de la aplicación (el selector de perfiles de E4.5 los lista todos al abrir un
log), no un fallo de "faltan datos" -- por eso esta suite, y no solo el
generador, es la que cierra la puerta G1 de la tarea:

1. **Los diez cargan con el lector real de F3-01** (`Perfil.desde_texto_json`)
   sin que salte `ErrorDePerfil`. Es la comprobación que pide la tarea:
   «un perfil de fábrica roto es un fallo de arranque, no de datos».
2. **Cada `rol` que declaran existe en `data/roles.toml`.** Un rol mal escrito
   (`"boost_presure_actual"` en vez de `"boost_pressure_actual"`) no lanzaría
   `ErrorDePerfil` -- el esquema no valida contra el catálogo (ADR-002,
   `perfil.py` decisión 1) -- así que sin esta prueba un typo pasaría
   silencioso hasta que alguien abriera un log de verdad y viera un panel
   vacío sin saber por qué.
3. **Cada `id_nativo` que declaran es un canal real** del AutoLog de muestra
   (`samples/real/AutoLog_20260729_1830.csv`), salvo la única excepción
   documentada (`lambda_error`, el canal MATEMÁTICO de docs/04 §4.5, que no es
   un canal de ningún formato). Es la comprobación contra la trampa que
   `docs/09` §9.10 ya pagó una vez: «citar un número de otra evidencia» -- aquí
   sería citar un nombre de canal que nadie verificó.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlv_core.formatos.haltech import Cabecera, Descriptor, cargar_descriptor, parsear_cabecera
from dlv_core.perfil import Perfil
from dlv_core.roles import Rol, cargar_catalogo_roles

RAIZ = Path(__file__).resolve().parents[2]
PERFILES_DIR = RAIZ / "data" / "perfiles"
ROLES_TOML = RAIZ / "data" / "roles.toml"
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
AUTOLOG = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"

# Los diez de docs/04 §4.2, en el orden del documento. Una lista explícita (en
# vez de "todo lo que haya en el directorio") para que si un fichero
# desaparece o se renombra sin querer, la prueba lo diga por su nombre y no
# con un "9 != 10" genérico.
NOMBRES_DE_FABRICA = (
    "p01_fuel_lambda",
    "p02_knock",
    "p03_boost_control",
    "p04_ignition",
    "p05_transient_tip_in",
    "p06_idle_control",
    "p07_trigger",
    "p08_salud_motor",
    "p09_diagnostico_sensores",
    "p10_launch_control",
)

# El único id_nativo que NO es un canal de ningún formato: es el marcador de
# posición del canal MATEMÁTICO "λ error" (docs/04 §4.5), documentado en la
# cabecera de `tools/generar_perfiles_de_fabrica.py`.
ID_NATIVO_NO_ES_CANAL_DE_LOG = frozenset({"lambda_error"})


@pytest.fixture(scope="module")
def catalogo_de_roles() -> dict[str, Rol]:
    with ROLES_TOML.open("rb") as fh:
        return cargar_catalogo_roles(fh)


@pytest.fixture(scope="module")
def cabecera_autolog() -> Cabecera:
    with DESCRIPTOR_TOML.open("rb") as fh:
        descriptor: Descriptor = cargar_descriptor(fh)
    datos = AUTOLOG.read_bytes()
    return parsear_cabecera(datos, descriptor)


def test_hay_exactamente_los_diez_ficheros_de_fabrica() -> None:
    encontrados = {p.stem for p in PERFILES_DIR.glob("*.dlvprofile")}
    assert encontrados == set(NOMBRES_DE_FABRICA), (
        "data/perfiles/ tiene que contener exactamente los diez perfiles de "
        f"docs/04 §4.2, ni más ni menos. Encontrados: {sorted(encontrados)}"
    )


@pytest.mark.parametrize("nombre", NOMBRES_DE_FABRICA)
def test_el_perfil_de_fabrica_carga_sin_error(nombre: str) -> None:
    """Un perfil de fábrica que no carga es un fallo de arranque, no de
    datos: por eso esta prueba deja que `ErrorDePerfil` se propague tal cual
    -- no se atrapa ni se convierte en un aviso -- y pytest lo cuenta como un
    fallo de la suite."""
    ruta = PERFILES_DIR / f"{nombre}.dlvprofile"
    texto = ruta.read_text(encoding="utf-8")
    perfil = Perfil.desde_texto_json(texto)
    assert isinstance(perfil, Perfil)
    assert perfil.paneles  # ya lo exige Perfil.__post_init__, ancla explícita
    # Ida y vuelta: el fichero en disco es exactamente lo que produce el
    # esquema, no algo tocado a mano después de generarlo.
    assert Perfil.desde_texto_json(perfil.a_texto_json()).a_dict() == perfil.a_dict()


@pytest.mark.parametrize("nombre", NOMBRES_DE_FABRICA)
def test_todos_los_roles_del_perfil_existen_en_el_catalogo(
    nombre: str, catalogo_de_roles: dict[str, Rol]
) -> None:
    """`perfil.py` no valida `rol` contra `data/roles.toml` (ADR-002): esta
    prueba es la que cierra ese hueco para los diez de fábrica. Un rol mal
    escrito no lanza `ErrorDePerfil`, así que sin esto pasaría silencioso
    hasta que alguien viera un panel vacío en un log real sin saber por qué."""
    ruta = PERFILES_DIR / f"{nombre}.dlvprofile"
    perfil = Perfil.desde_texto_json(ruta.read_text(encoding="utf-8"))
    desconocidos = perfil.roles_referenciados - catalogo_de_roles.keys()
    assert not desconocidos, (
        f"{nombre}: roles que no existen en data/roles.toml: {sorted(desconocidos)}"
    )


@pytest.mark.parametrize("nombre", NOMBRES_DE_FABRICA)
def test_todos_los_id_nativo_son_canales_reales_del_autolog(
    nombre: str, cabecera_autolog: Cabecera
) -> None:
    """Cada `id_nativo` de los diez perfiles se verificó contra
    `grep "^Channel : "` sobre el AutoLog real antes de escribirse en
    `tools/generar_perfiles_de_fabrica.py` (ver la cabecera de ese script).
    Esta prueba automatiza esa verificación para que no se deshaga en el
    próximo cambio: un `id_nativo` que no está en el log real es una
    adivinanza con forma de dato (docs/09 §9.7 regla 5)."""
    ruta = PERFILES_DIR / f"{nombre}.dlvprofile"
    perfil = Perfil.desde_texto_json(ruta.read_text(encoding="utf-8"))
    ids_nativos = {
        elemento.id_nativo
        for panel in perfil.paneles
        for elemento in panel.elementos
        if elemento.id_nativo is not None
    } - ID_NATIVO_NO_ES_CANAL_DE_LOG
    desconocidos = {id_ for id_ in ids_nativos if cabecera_autolog.por_nombre(id_) is None}
    assert not desconocidos, (
        f"{nombre}: id_nativo que no aparece como 'Channel : ...' en "
        f"samples/real/AutoLog_20260729_1830.csv: {sorted(desconocidos)}"
    )


def test_p3_boost_es_totalmente_portable_por_rol() -> None:
    """Hallazgo de la tarea: a diferencia de F3-01 (catálogo de 58 roles), con
    los 112 roles de la ampliación 2026-08-26 el perfil de boost ya no
    necesita NINGÚN `id_nativo`. Ancla explícita para que una regresión del
    catálogo (o del propio perfil) se note por su nombre."""
    ruta = PERFILES_DIR / "p03_boost_control.dlvprofile"
    perfil = Perfil.desde_texto_json(ruta.read_text(encoding="utf-8"))
    con_id_nativo = [
        e for panel in perfil.paneles for e in panel.elementos if e.id_nativo is not None
    ]
    assert con_id_nativo == []


def test_p5_transient_sigue_siendo_el_mas_dependiente_de_id_nativo() -> None:
    """Lo contrario del caso anterior: P5 sigue dependiendo casi por completo
    de `id_nativo` porque los canales de "Transient Throttle" son diagnóstico
    interno de Haltech sin equivalente universal (docs/07 §7.12). Ancla
    explícita, mismo criterio que dejó `test_p7_trigger_...` en F3-01."""
    ruta = PERFILES_DIR / "p05_transient_tip_in.dlvprofile"
    perfil = Perfil.desde_texto_json(ruta.read_text(encoding="utf-8"))
    (panel,) = perfil.paneles
    con_id_nativo = [e for e in panel.elementos if e.id_nativo is not None]
    con_rol = [e for e in panel.elementos if e.rol is not None]
    assert len(con_id_nativo) == 7
    assert len(con_rol) == 3
