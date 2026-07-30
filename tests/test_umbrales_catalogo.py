"""Validación del catálogo de umbrales data/umbrales.toml.

Los umbrales de los detectores son **configurables**, no constantes: valores por
omisión en un fichero de datos, sustituibles por perfil, por usuario o por canal
(`docs/04-perfiles-motorsport.md` §4.3).

Estas pruebas comprueban tres cosas:

1. Que el catálogo es coherente: los 18 detectores, con roles que existen, en
   unidad canónica y con severidades válidas.
2. Que **nadie los ha vuelto a cablear**. El generador del fixture de verdad de
   referencia y su prueba tienen que leerlos de aquí, no llevar copias. Es la
   prueba que impide que las tres fuentes se desincronicen en el primer ajuste.
3. Que el fixture declara qué umbrales usó, y que coinciden con los vigentes.

Solo biblioteca estándar.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parent.parent
UMBRALES = RAIZ / "data" / "umbrales.toml"
ROLES = RAIZ / "data" / "roles.toml"
VERDAD_JSON = RAIZ / "samples" / "verdad" / "verdad.json"
GENERADOR = RAIZ / "tools" / "generar_verdad.py"

SEVERIDADES = {"critica", "alta", "media", "baja", "informativa"}
DETECTORES_ESPERADOS = {f"D{i}" for i in range(1, 19)}


def _toml(ruta: Path) -> dict:
    with ruta.open("rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def cat() -> dict:
    return _toml(UMBRALES)


@pytest.fixture(scope="module")
def det(cat: dict) -> dict:
    return cat["detectores"]


@pytest.fixture(scope="module")
def generador() -> Any:
    """Importa tools/generar_verdad.py para inspeccionar sus constantes."""
    spec = importlib.util.spec_from_file_location("generar_verdad", GENERADOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["generar_verdad"] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# Coherencia del catálogo
# --------------------------------------------------------------------------- #
def test_el_catalogo_carga(cat: dict) -> None:
    assert cat["meta"]["version"] == 1
    assert cat["meta"]["unidades"].startswith("canónicas")


def test_estan_los_18_detectores(det: dict) -> None:
    faltan = DETECTORES_ESPERADOS - set(det)
    sobran = set(det) - DETECTORES_ESPERADOS
    assert not faltan, f"faltan detectores: {sorted(faltan)}"
    assert not sobran, f"detectores no previstos: {sorted(sobran)}"


def test_todo_detector_esta_bien_formado(det: dict) -> None:
    for nombre, d in det.items():
        assert d.get("etiqueta"), f"{nombre}: falta etiqueta"
        assert d.get("descripcion"), f"{nombre}: falta descripción"
        assert "permanencia_s" in d, f"{nombre}: falta permanencia_s"
        assert float(d["permanencia_s"]) >= 0.0, f"{nombre}: permanencia negativa"
        # D13 usa severidad por nivel en lugar de una sola.
        tiene_sev = "severidad" in d or "severidad_por_nivel" in d
        assert tiene_sev, f"{nombre}: no declara severidad"
        if "severidad" in d:
            assert d["severidad"] in SEVERIDADES, f"{nombre}: severidad '{d['severidad']}'"
        if "severidad_critica" in d:
            assert d["severidad_critica"] in SEVERIDADES


def test_los_roles_citados_existen(det: dict) -> None:
    roles = _toml(ROLES)["roles"]
    for nombre, d in det.items():
        for rol in d.get("roles", ()):
            assert rol in roles, f"{nombre}: el rol '{rol}' no existe en roles.toml"


def test_las_condiciones_citan_roles_existentes(det: dict) -> None:
    """Las condiciones de contexto se nombran `<rol>_min` o `<rol>_max`."""
    roles = _toml(ROLES)["roles"]
    for nombre, d in det.items():
        for bloque in ("condiciones", "escalada_critica"):
            for clave in d.get(bloque, {}):
                rol = re.sub(r"_(min|max)$", "", clave)
                assert rol in roles, f"{nombre}.{bloque}: '{clave}' no alude a un rol conocido"


def test_los_umbrales_estan_en_unidad_canonica(det: dict) -> None:
    """Kelvin, kPa absolutos, fracción en lugar de porcentaje, voltios.

    Un valor en la unidad equivocada aquí sería catastrófico y silencioso: 105 en
    lugar de 378,15 haría que D9 disparara siempre.
    """
    # Temperaturas: en kelvin, así que cualquier valor plausible pasa de 200.
    assert float(det["D9"]["umbral_max_k"]) > 200.0, "D9 parece estar en °C, no en K"
    # Fracciones: nunca porcentajes.
    for clave in ("umbral_aviso", "umbral_critico"):
        v = float(det["D8"][clave])
        assert 0.0 < v <= 1.2, f"D8.{clave} = {v} parece un porcentaje, no una fracción"
    assert 0.0 < float(det["D4"]["desviacion_relativa_max"]) < 1.0
    assert 0.0 < float(det["D4"]["condiciones"]["throttle_position_min"]) <= 1.0
    # Presiones: kPa absolutos, así que el mínimo de aceite pasa de la atmosférica.
    assert float(det["D10"]["curva_minima"]["base_kpa"]) > 101.0
    # Tensión: voltios.
    assert 5.0 < float(det["D11"]["umbral_min_v"]) < 20.0


def test_la_curva_de_presion_de_aceite_es_creciente(det: dict) -> None:
    """El punto de usar una curva: el mínimo exigible sube con el régimen."""
    c = det["D10"]["curva_minima"]
    base = float(c["base_kpa"])
    pendiente = float(c["pendiente_kpa_por_1000rpm"])
    assert pendiente > 0.0, "una curva plana no aporta nada frente a un umbral fijo"
    en_ralenti = base + (900 / 1000) * pendiente
    en_carga = base + (6500 / 1000) * pendiente
    assert en_carga > en_ralenti * 1.5, "la curva apenas discrimina entre ralentí y carga"


def test_los_detectores_criticos_llevan_permanencia_o_son_binarios(det: dict) -> None:
    """Una condición continua necesita permanencia; una binaria (un bit, un
    contador que sube) no, porque no oscila por ruido."""
    binarios = {"D1", "D12", "D13"}
    for nombre, d in det.items():
        if d.get("severidad") != "critica" or nombre in binarios:
            continue
        assert float(d["permanencia_s"]) > 0.0, (
            f"{nombre}: detector crítico continuo sin permanencia mínima; "
            "generaría falsas alertas con ruido"
        )


def test_esta_declarada_la_desactivacion_automatica(cat: dict) -> None:
    """Mitigación de R10: un detector crítico con un rol asignado a ojo se calla."""
    d = cat["desactivacion_automatica"]
    assert "critica" in d["severidades_afectadas"]
    assert d["motivo"]


def test_el_catalogo_documenta_que_son_configurables(cat: dict) -> None:
    """La propiedad que pidió el propietario: valores por omisión, no constantes.

    Se comprueba sobre el texto del fichero porque la precedencia es una decisión
    de diseño que tiene que quedar escrita donde se editan los valores, no solo en
    la documentación.
    """
    texto = UMBRALES.read_text(encoding="utf-8")
    assert "VALORES POR OMISIÓN, NO CONSTANTES" in texto
    for nivel in ("Anulación por canal", "Perfil activo", "Preferencias de usuario"):
        assert nivel in texto, f"la precedencia no menciona '{nivel}'"


# --------------------------------------------------------------------------- #
# Nadie los ha vuelto a cablear
# --------------------------------------------------------------------------- #
def test_el_generador_lee_los_umbrales_del_catalogo(generador: Any, det: dict) -> None:
    """Si alguien vuelve a cablear un umbral en el generador, esto lo caza."""
    assert float(det["D4"]["desviacion_relativa_max"]) == generador.D4_MAX
    assert float(det["D8"]["umbral_aviso"]) == generador.D8_AVISO
    assert float(det["D8"]["umbral_critico"]) == generador.D8_CRITICO
    assert abs(generador.D9_MAX_C - (float(det["D9"]["umbral_max_k"]) - 273.15)) < 1e-9
    assert float(det["D11"]["umbral_min_v"]) == generador.D11_MIN_V


def test_la_curva_del_generador_es_la_del_catalogo(generador: Any, det: dict) -> None:
    c = det["D10"]["curva_minima"]
    base = float(c["base_kpa"])
    pendiente = float(c["pendiente_kpa_por_1000rpm"])
    for rpm in (900.0, 3000.0, 6500.0):
        assert (
            abs(generador.presion_aceite_minima_kpa(rpm) - (base + rpm / 1000 * pendiente)) < 1e-9
        )


def test_el_generador_no_contiene_umbrales_cableados() -> None:
    """Inspección del texto: los números que antes estaban aquí no deben volver.

    Es deliberadamente literal. Un umbral cableado no rompe ninguna prueba
    funcional —el fixture sigue siendo coherente consigo mismo—, así que lo único
    que lo detecta es buscarlo.
    """
    texto = GENERADOR.read_text(encoding="utf-8")
    # Se ignoran comentarios y docstrings: lo que importa es el código.
    codigo = "\n".join(
        linea.split("#", 1)[0] for linea in texto.splitlines() if not linea.strip().startswith("#")
    )
    prohibidos = {
        "1.041": "la desviación de lambda de D4",
        "1.030": "el casi-positivo de lambda de D4",
        "88.0": "el duty de aviso de D8",
        "96.0": "el duty crítico de D8",
        "107.5": "la sobretemperatura de D9",
        "11.2": "la baja tensión de D11",
        "101.3 + 100.0": "la base de la curva de D10",
    }
    encontrados = [f"{v} ({k})" for k, v in prohibidos.items() if k in codigo]
    assert not encontrados, "umbrales cableados de vuelta en el generador: " + ", ".join(
        encontrados
    )


def test_el_fixture_declara_los_umbrales_que_uso(det: dict) -> None:
    """`verdad.json` guarda los umbrales vigentes cuando se generó.

    Si alguien cambia el catálogo y no regenera el fixture, esto lo caza: el
    fixture estaría colocando eventos a un lado de un umbral que ya no es el que
    los detectores van a usar.
    """
    verdad = json.loads(VERDAD_JSON.read_text(encoding="utf-8"))
    u = verdad["umbrales"]
    assert u["origen"] == "data/umbrales.toml"
    v = u["vigentes"]
    assert v["D4_desviacion_relativa_max"] == float(det["D4"]["desviacion_relativa_max"])
    assert v["D8_umbral_aviso"] == float(det["D8"]["umbral_aviso"])
    assert v["D8_umbral_critico"] == float(det["D8"]["umbral_critico"])
    assert v["D11_umbral_min_v"] == float(det["D11"]["umbral_min_v"])
    assert v["D10_curva"] == det["D10"]["curva_minima"]
