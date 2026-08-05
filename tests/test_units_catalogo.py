"""Validación del catálogo data/units.toml (tarea F0-08).

Estas pruebas son la red de seguridad del riesgo R1 y del riesgo R11: un factor
de escala mal puesto o una conversión aplicada a una diferencia producen un
número plausible y falso, que llega a una decisión de tuning.

Solo biblioteca estándar: `tomllib` es parte de Python desde 3.11.
"""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO = RAIZ / "data" / "units.toml"

TIPOS_VALIDOS = {"afin", "reciproca", "parametrizada"}


@pytest.fixture(scope="module")
def cat() -> dict:
    with CATALOGO.open("rb") as fh:
        return tomllib.load(fh)


# --------------------------------------------------------------------------- #
# Motor de conversión de referencia
#
# Es deliberadamente una reimplementación mínima e independiente de dlv-core:
# si las pruebas usaran el mismo código que se prueba, no probarían nada.
# --------------------------------------------------------------------------- #
def mostrar(conv: dict, x: float, *, clase: str = "punto", param: float | None = None) -> float:
    """Canónica -> mostrada, respetando la clase de magnitud (docs/06 §6.5)."""
    tipo = conv["tipo"]
    if tipo == "afin":
        a, b = conv["a"], conv["b"]
        if clase == "punto":
            return a * x + b
        if clase in ("intervalo", "tasa"):
            return a * x  # sin desplazamiento: la trampa del delta
        if clase == "varianza":
            return a * a * x
        raise ValueError(clase)
    if tipo == "reciproca":
        if clase != "punto":
            raise ValueError("una conversión recíproca no es lineal en diferencias")
        return conv["a"] / x
    if tipo == "parametrizada":
        a = param if param is not None else conv["a_por_omision"]
        return a * x if clase != "varianza" else a * a * x
    raise ValueError(tipo)


def canonica(conv: dict, y: float, *, param: float | None = None) -> float:
    """Mostrada -> canónica. Inversa de `mostrar` para la clase punto."""
    tipo = conv["tipo"]
    if tipo == "afin":
        return (y - conv["b"]) / conv["a"]
    if tipo == "reciproca":
        return conv["a"] / y
    if tipo == "parametrizada":
        a = param if param is not None else conv["a_por_omision"]
        return y / a
    raise ValueError(tipo)


def unidades(cat: dict):
    """Itera (dimensión, unidad, definición) sobre todo el catálogo."""
    for dim, dd in cat["dimensiones"].items():
        for uni, ud in dd["unidades"].items():
            yield dim, uni, ud


# --------------------------------------------------------------------------- #
# Integridad estructural
# --------------------------------------------------------------------------- #
def test_catalogo_existe_y_carga(cat: dict) -> None:
    assert cat["meta"]["version"] == 1
    assert cat["dimensiones"], "el catálogo no tiene dimensiones"


def test_toda_dimension_declara_su_canonica_y_la_contiene(cat: dict) -> None:
    for dim, dd in cat["dimensiones"].items():
        can = dd["canonica"]
        claves = set(dd["unidades"])
        alias = {a for ud in dd["unidades"].values() for a in ud.get("alias", [])}
        # La canónica puede aparecer con su clave literal o normalizada
        # (p. ej. kg/m3 -> kg_m3, m/s2 -> m_s2).
        normalizada = can.replace("/", "_").replace("·", "")
        assert can in claves or normalizada in claves or can in alias, (
            f"{dim}: la canónica '{can}' no está entre sus unidades {sorted(claves)}"
        )


def test_la_unidad_canonica_es_la_identidad(cat: dict) -> None:
    """La canónica debe convertirse en sí misma: a=1, b=0. Si no, todo el
    modelo de tres capas queda descolocado."""
    for dim, dd in cat["dimensiones"].items():
        can = dd["canonica"]
        for clave in (can, can.replace("/", "_").replace("·", "")):
            ud = dd["unidades"].get(clave)
            if ud is None:
                continue
            conv = ud["desde_canonica"]
            assert conv["tipo"] == "afin", f"{dim}.{clave}: la canónica debe ser afín"
            assert conv["a"] == 1.0 and conv["b"] == 0.0, (
                f"{dim}.{clave}: la canónica debe ser identidad, es a={conv['a']} b={conv['b']}"
            )
            break


def test_toda_unidad_esta_bien_formada(cat: dict) -> None:
    for dim, uni, ud in unidades(cat):
        assert "etiqueta" in ud, f"{dim}.{uni}: falta etiqueta"
        assert isinstance(ud.get("decimales"), int), f"{dim}.{uni}: decimales debe ser entero"
        assert 0 <= ud["decimales"] <= 6, f"{dim}.{uni}: decimales fuera de rango"
        conv = ud["desde_canonica"]
        assert conv["tipo"] in TIPOS_VALIDOS, f"{dim}.{uni}: tipo '{conv['tipo']}' desconocido"
        if conv["tipo"] == "afin":
            assert conv["a"] != 0.0, f"{dim}.{uni}: factor a=0 no es invertible"
        elif conv["tipo"] == "reciproca":
            assert conv["a"] != 0.0, f"{dim}.{uni}: recíproca con a=0"
        else:
            assert "parametro_rol" in conv and "a_por_omision" in conv


def test_desplazamiento_marcado_de_forma_coherente(cat: dict) -> None:
    """`origen_desplazado` debe estar puesto exactamente en las unidades con
    b != 0. Es la marca que impide aplicar el desplazamiento a un delta."""
    for dim, uni, ud in unidades(cat):
        conv = ud["desde_canonica"]
        if conv["tipo"] != "afin":
            continue
        tiene_b = conv["b"] != 0.0
        marcado = ud.get("origen_desplazado", False)
        assert tiene_b == marcado, f"{dim}.{uni}: b={conv['b']} pero origen_desplazado={marcado}"


def test_no_hay_alias_ambiguos(cat: dict) -> None:
    for dim, dd in cat["dimensiones"].items():
        vistos: dict[str, str] = {}
        for uni, ud in dd["unidades"].items():
            for nombre in [uni, *ud.get("alias", [])]:
                assert nombre not in vistos or vistos[nombre] == uni, (
                    f"{dim}: '{nombre}' aparece en {vistos.get(nombre)} y en {uni}"
                )
                vistos[nombre] = uni


# --------------------------------------------------------------------------- #
# Ida y vuelta
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("x", [1.0, 42.5, 273.15, 1013.25, 0.85])
def test_ida_y_vuelta_canonica(cat: dict, x: float) -> None:
    for dim, uni, ud in unidades(cat):
        conv = ud["desde_canonica"]
        y = mostrar(conv, x)
        vuelta = canonica(conv, y)
        assert math.isclose(vuelta, x, rel_tol=1e-12, abs_tol=1e-12), (
            f"{dim}.{uni}: {x} -> {y} -> {vuelta}"
        )


# --------------------------------------------------------------------------- #
# Casos conocidos (docs/06 §6.12)
# --------------------------------------------------------------------------- #
def u(cat: dict, dim: str, uni: str) -> dict:
    return cat["dimensiones"][dim]["unidades"][uni]["desde_canonica"]


def test_temperatura_casos_conocidos(cat: dict) -> None:
    assert math.isclose(mostrar(u(cat, "temperature", "degC"), 273.15), 0.0, abs_tol=1e-9)
    assert math.isclose(mostrar(u(cat, "temperature", "degF"), 273.15), 32.0, abs_tol=1e-9)
    assert math.isclose(mostrar(u(cat, "temperature", "degF"), 373.15), 212.0, abs_tol=1e-9)
    # El coolant real del AutoLog: 3663 deciK -> 366,3 K -> 93,15 °C (docs/01 §1.8)
    assert math.isclose(mostrar(u(cat, "temperature", "degC"), 366.3), 93.15, abs_tol=1e-9)


def test_presion_casos_conocidos(cat: dict) -> None:
    assert math.isclose(mostrar(u(cat, "pressure", "bar"), 100.0), 1.0, abs_tol=1e-9)
    assert math.isclose(mostrar(u(cat, "pressure", "psi"), 100.0), 14.5037738, abs_tol=1e-5)
    assert math.isclose(mostrar(u(cat, "pressure", "hPa"), 101.325), 1013.25, abs_tol=1e-6)


def test_mezcla_casos_conocidos(cat: dict) -> None:
    # AFR con la estequiometría del log (14,7 en las muestras de gasolina).
    assert math.isclose(
        mostrar(u(cat, "mixture_ratio", "afr"), 1.0, param=14.7), 14.7, abs_tol=1e-9
    )
    # Con E85 la misma lambda da otro AFR: es el motivo de la conversión parametrizada.
    assert math.isclose(
        mostrar(u(cat, "mixture_ratio", "afr"), 1.0, param=9.77), 9.77, abs_tol=1e-9
    )
    # phi = 1/lambda
    assert math.isclose(mostrar(u(cat, "mixture_ratio", "phi"), 0.850), 1.176470588, abs_tol=1e-8)


def test_velocidad_y_regimen_casos_conocidos(cat: dict) -> None:
    assert math.isclose(mostrar(u(cat, "speed", "mph"), 100.0), 62.13711922, abs_tol=1e-7)
    assert math.isclose(mostrar(u(cat, "angular_speed", "Hz"), 6000.0), 100.0, abs_tol=1e-9)
    assert math.isclose(mostrar(u(cat, "frequency", "rpm"), 100.0), 6000.0, abs_tol=1e-9)


def test_periodo_frecuencia_es_reciproca(cat: dict) -> None:
    # 100 Hz <-> 10 000 µs
    assert math.isclose(mostrar(u(cat, "frequency", "periodo_us"), 100.0), 10000.0, abs_tol=1e-6)


def test_consumo_es_reciproco(cat: dict) -> None:
    # 10 L/100 km = 23,52 mpg (US)
    assert math.isclose(mostrar(u(cat, "fuel_economy", "mpg_us"), 10.0), 23.52145833, abs_tol=1e-7)


# --------------------------------------------------------------------------- #
# LA TRAMPA DEL DELTA — docs/06 §6.5 y §6.12, riesgo R11
# Si esta prueba se rompe, el doble cursor y todas las desviaciones típicas
# están dando números disparatados.
# --------------------------------------------------------------------------- #
def test_delta_de_temperatura(cat: dict) -> None:
    """Un Δ de 10 K son 10 °C y 18 °F. Nunca −263,15 °C."""
    degC = u(cat, "temperature", "degC")
    degF = u(cat, "temperature", "degF")

    assert math.isclose(mostrar(degC, 10.0, clase="intervalo"), 10.0, abs_tol=1e-12)
    assert math.isclose(mostrar(degF, 10.0, clase="intervalo"), 18.0, abs_tol=1e-12)

    # Y la versión equivocada, para dejar constancia de qué se está evitando:
    assert mostrar(degC, 10.0, clase="punto") < -260  # -263,15 °C


def test_desviacion_tipica_de_temperatura(cat: dict) -> None:
    """Una desviación típica de 2 K son 2 °C, no −271,15 °C."""
    degC = u(cat, "temperature", "degC")
    assert math.isclose(mostrar(degC, 2.0, clase="intervalo"), 2.0, abs_tol=1e-12)


def test_varianza_usa_el_factor_al_cuadrado(cat: dict) -> None:
    """Varianza de 4 K² en °F: 4 × 1,8² = 12,96 °F²."""
    degF = u(cat, "temperature", "degF")
    assert math.isclose(mostrar(degF, 4.0, clase="varianza"), 12.96, abs_tol=1e-12)


def test_delta_de_presion_relativa_no_resta_la_referencia(cat: dict) -> None:
    """Pasar a presión relativa resta la referencia solo a los puntos.
    Un Δ de 50 kPa son 50 kPa tanto en absoluto como en relativo."""
    psi = u(cat, "pressure", "psi")
    ref = cat["presion_referencia"]["constante_por_omision_kPa"]
    punto_abs = mostrar(psi, 200.0, clase="punto")
    punto_rel = mostrar(psi, 200.0 - ref, clase="punto")
    assert punto_abs > punto_rel  # el relativo es menor: se ha restado la baro
    # El delta es idéntico en ambos modos.
    assert math.isclose(
        mostrar(psi, 50.0, clase="intervalo"),
        mostrar(psi, 50.0, clase="intervalo"),
        abs_tol=1e-12,
    )
    assert math.isclose(mostrar(psi, 50.0, clase="intervalo"), 7.251886885, abs_tol=1e-8)


def test_reciproca_rechaza_diferencias(cat: dict) -> None:
    """Una conversión recíproca no es lineal: convertir un delta no tiene
    sentido y el motor debe negarse, no devolver un número."""
    phi = u(cat, "mixture_ratio", "phi")
    with pytest.raises(ValueError):
        mostrar(phi, 0.1, clase="intervalo")


# --------------------------------------------------------------------------- #
# Presets, compuestas, centinelas y clases
# --------------------------------------------------------------------------- #
def test_presets_referencian_unidades_existentes(cat: dict) -> None:
    dims = cat["dimensiones"]
    ignorar = {"etiqueta", "por_omision", "pressure_referencia"}
    for nombre, preset in cat["presets"].items():
        for dim, uni in preset.items():
            if dim in ignorar:
                continue
            assert dim in dims, f"preset {nombre}: dimensión '{dim}' desconocida"
            claves = set(dims[dim]["unidades"])
            alias = {a for ud in dims[dim]["unidades"].values() for a in ud.get("alias", [])}
            assert uni in claves or uni in alias, f"preset {nombre}: '{uni}' no es unidad de {dim}"


def test_hay_exactamente_un_preset_por_omision(cat: dict) -> None:
    por_omision = [n for n, p in cat["presets"].items() if p.get("por_omision")]
    assert por_omision == ["metrico"], f"presets por omisión: {por_omision}"


def test_referencia_de_presion_solo_donde_se_admite(cat: dict) -> None:
    assert cat["dimensiones"]["pressure"].get("admite_referencia") is True
    otras = [
        d for d, dd in cat["dimensiones"].items() if d != "pressure" and dd.get("admite_referencia")
    ]
    assert not otras, f"solo la presión admite referencia, no {otras}"


def test_compuestas_referencian_dimensiones_existentes(cat: dict) -> None:
    for nombre, c in cat["compuestas"].items():
        assert c["numerador"] in cat["dimensiones"], f"{nombre}: numerador desconocido"
        assert c["denominador"] in cat["dimensiones"], f"{nombre}: denominador desconocido"


def test_dimensiones_no_convertibles_tienen_una_sola_unidad(cat: dict) -> None:
    """Si el selector de unidad está desactivado, ofrecer varias sería incoherente."""
    for dim, dd in cat["dimensiones"].items():
        if dd.get("convertible") is False:
            assert len(dd["unidades"]) == 1, f"{dim}: no convertible pero tiene varias unidades"


def test_unknown_se_muestra_en_crudo(cat: dict) -> None:
    """Mitigación de R1: un canal sin escala confirmada nunca lleva unidad."""
    unk = cat["dimensiones"]["unknown"]
    assert unk.get("mostrar_en_crudo") is True
    assert unk.get("convertible") is False


def test_centinelas_declarados(cat: dict) -> None:
    i32 = cat["centinelas"]["i32"]
    # Los observados en el AutoLog real (docs/01 §1.13).
    for v in (2147483647, -2147483645, -2147483628, 8388607):
        assert v in i32, f"falta el centinela {v} observado en el log real"
    assert "" in cat["centinelas"]["texto"], "la celda vacía es un centinela de CSV genérico"
    assert "#N/A" in cat["centinelas"]["texto"]


def test_clases_de_magnitud_completas(cat: dict) -> None:
    clases = cat["clases"]
    assert set(clases) == {"punto", "intervalo", "tasa", "varianza"}
    assert clases["punto"]["usa_desplazamiento"] is True
    for c in ("intervalo", "tasa", "varianza"):
        assert clases[c]["usa_desplazamiento"] is False, f"{c} no debe usar desplazamiento"
    assert clases["varianza"].get("factor_al_cuadrado") is True


def test_cobertura_minima_de_dimensiones(cat: dict) -> None:
    """Las 34 `Type` del formato Haltech deben tener destino. El mapeo concreto
    es F0-09; aquí solo se comprueba que las dimensiones necesarias existen."""
    necesarias = {
        "temperature",
        "pressure",
        "mixture_ratio",
        "angular_speed",
        "speed",
        "angle",
        "ratio",
        "voltage",
        "time",
        "frequency",
        "resistance",
        "sound_level",
        "mass_flow",
        "volume_flow",
        "volume",
        "mass",
        "mass_per_cyl",
        "density",
        "distance",
        "fuel_economy",
        "torque",
        "power",
        "acceleration",
        "count",
        "enum",
        "bitmask",
        "unknown",
    }
    faltan = necesarias - set(cat["dimensiones"])
    assert not faltan, f"faltan dimensiones: {sorted(faltan)}"
