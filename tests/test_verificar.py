"""Pruebas de `tools/verificar.py`, la puerta que decide si algo está terminado.

Es la herramienta con más responsabilidad del repositorio: si dice «todo en verde»
cuando no lo está, todo el protocolo de §8.10 deja de valer. Lo que se protege es
exactamente eso —que no pueda dar un verde falso— y no el formato de su salida.

Tres propiedades:

1. **Las seis comprobaciones están todas.** Si alguien quita una del listado, aquí
   se ve; en la salida del guion, no, porque un resumen de cinco líneas parece
   igual de completo que uno de seis.
2. **Una herramienta ausente cuenta como fallo.** Es la lección de «el informe de
   un agente no es evidencia»: no haber podido mirar no es estar en verde.
3. **El sustituto de `pytest` cubre las cuatro rutas de pruebas.** Si `testpaths`
   crece y la lista del sustituto no, el verde sin red se vuelve mentira. Es
   literalmente el defecto que ya ocurrió al integrar F0-02, cuando `pytest` solo
   recogía 4 pruebas porque faltaba `tests/` en `testpaths`.

Solo biblioteca estándar.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parent.parent
VERIFICAR = RAIZ / "tools" / "verificar.py"


@pytest.fixture(scope="module")
def mod() -> Any:
    spec = importlib.util.spec_from_file_location("verificar", VERIFICAR)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules["verificar"] = m
    spec.loader.exec_module(m)
    return m


def test_estan_las_seis_comprobaciones(mod: Any) -> None:
    etiquetas = [e for e, _ in mod.COMPROBACIONES]
    assert etiquetas == [
        "ruff check",
        "ruff format --check",
        "mypy --strict",
        "pytest",
        "ADR-009",
        "presupuestos",
    ], etiquetas


def test_una_herramienta_ausente_es_un_fallo(mod: Any) -> None:
    """El punto de la herramienta: no puede dar verde por no haber mirado.

    Se acepta cualquiera de los dos motivos, porque dependen del entorno: o no se
    encuentra el ejecutable, o se encuentra y no se puede lanzar. Lo que no
    depende del entorno, y es lo que se comprueba, es que el resultado sea rojo y
    que no se propague la excepción: una puerta que revienta no informa.
    """
    entorno: dict[str, str] = {}
    r = mod._ejecutar("mypy --strict", ["no-existe-esta-herramienta", "algo"], entorno)
    assert r.ok is False
    assert "no disponible" in r.detalle or "no ejecutable" in r.detalle


def test_un_ejecutable_que_no_se_puede_lanzar_pone_rojo_y_no_revienta(
    mod: Any, tmp_path: Path
) -> None:
    """`shutil.which` puede encontrar algo que luego no arranca.

    Pasó en el propio contenedor: `uv` estaba en el PATH pero pertenecía a otro
    usuario, y `subprocess` lanzaba `FileNotFoundError` en lugar de devolver un
    código de salida. La primera versión de `verificar.py` moría con traza en vez
    de marcar la comprobación en rojo, que es lo único que un guion de puerta
    tiene prohibido hacer.
    """
    falso = tmp_path / "herramienta-no-ejecutable"
    falso.write_text("no soy un binario\n", encoding="utf-8")  # sin permiso de ejecución
    r = mod._ejecutar("prueba", [str(falso)], {})
    assert r.ok is False


def test_pytest_ausente_cae_en_el_sustituto_y_lo_declara(mod: Any) -> None:
    """`pytest` es la única con sustituto, y el resumen tiene que decirlo.

    Un verde silencioso con el sustituto sería peor que no tenerlo: haría creer
    que la suite corrió tal cual está definida en `pyproject.toml`.
    """
    # No se ejecuta de verdad (sería recursivo y lento): se comprueba que la orden
    # de sustitución se construye y que apunta a `pytest_minimo`.
    orden = mod._pytest_de_sustitucion()
    assert orden[1].endswith("pytest_minimo.py")
    assert len(orden) > 2, "el sustituto no recibió ningún fichero de pruebas"


def test_el_sustituto_cubre_las_rutas_de_testpaths(mod: Any) -> None:
    """Las rutas duplicadas de `pyproject.toml` no pueden quedarse atrás."""
    with (RAIZ / "pyproject.toml").open("rb") as fh:
        testpaths = tomllib.load(fh)["tool"]["pytest"]["ini_options"]["testpaths"]
    assert set(mod.RUTAS_DE_PRUEBAS) == set(testpaths), (
        "`RUTAS_DE_PRUEBAS` de tools/verificar.py y `testpaths` de pyproject.toml "
        "han divergido: el verde sin `pytest` dejaría de cubrir todo"
    )


def test_el_sustituto_recoge_todos_los_ficheros_de_prueba(mod: Any) -> None:
    orden = mod._pytest_de_sustitucion()
    recogidos = {Path(p).name for p in orden[2:]}
    esperados = {p.name for ruta in mod.RUTAS_DE_PRUEBAS for p in (RAIZ / ruta).glob("test_*.py")}
    assert recogidos == esperados
    assert len(recogidos) >= 10, f"solo {len(recogidos)} ficheros de prueba recogidos"


def test_el_pythonpath_del_sustituto_lleva_los_tres_src(mod: Any) -> None:
    """Sin esto el sustituto no puede importar `dlv_core` y todo falla."""
    assert set(mod.RUTAS_SRC) == {"dlv-core/src", "dlv-api/src", "dlv-app/src"}


def test_el_guion_de_bash_delega_en_el_de_python() -> None:
    """Una sola implementación, dos entradas.

    `bash tools/verificar.sh` es lo que dice el protocolo y lo que está escrito en
    los informes de tareas ya cerradas; `python tools/verificar.py` es lo que
    funciona en Windows. Si se duplicaran las comprobaciones, una de las dos
    entradas se quedaría desactualizada sin que nada lo dijera.
    """
    texto = (RAIZ / "tools" / "verificar.sh").read_text(encoding="utf-8")
    assert "tools/verificar.py" in texto
    for herramienta in ("ruff check .", "mypy dlv-core", "pytest -q"):
        assert herramienta not in texto, (
            f"tools/verificar.sh vuelve a ejecutar '{herramienta}' por su cuenta; "
            "la implementación tiene que estar solo en verificar.py"
        )
