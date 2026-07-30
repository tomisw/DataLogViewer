"""Pruebas del motor de conversión de unidades (tarea F1-13).

Tres cosas que proteger:

1. **La trampa del delta.** Un Δ de 10 K son 10 °C y 18 °F. Si esto se rompe, el
   doble cursor y todas las desviaciones típicas dan números disparatados.
2. **ADR-009.** La conversión no puede recorrer la serie elemento a elemento. Se
   demuestra con un array falso que estalla si alguien lo itera, en lugar de
   confiar solo en la inspección estática de `tools/banco.py adr009`.
3. **La coherencia del catálogo**, comprobada al cargar y no en producción.

Solo biblioteca estándar: sin numpy instalado, el mismo código se ejercita con
`float` y con el array falso.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from dlv_core.unidades import (
    Afin,
    Catalogo,
    Clase,
    ErrorDeUnidad,
    Parametrizada,
    Reciproca,
    a_canonica,
    cargar_catalogo,
    desde_canonica,
    etiqueta_de,
)

# El catálogo real del repositorio. `dlv-core` no abre ficheros por su cuenta
# (ADR-002): es la prueba la que abre y pasa el objeto de lectura.
CATALOGO_TOML = Path(__file__).resolve().parents[2] / "data" / "units.toml"


@pytest.fixture(scope="module")
def cat() -> Catalogo:
    with CATALOGO_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


# --------------------------------------------------------------------------- #
# Conversiones sueltas
# --------------------------------------------------------------------------- #
def test_afin_punto_aplica_el_desplazamiento() -> None:
    c = Afin(a=1.0, b=-273.15)  # K -> °C
    assert math.isclose(c.desde_canonica(273.15, Clase.PUNTO), 0.0, abs_tol=1e-12)
    assert math.isclose(c.desde_canonica(366.3, Clase.PUNTO), 93.15, abs_tol=1e-12)


def test_afin_intervalo_no_aplica_el_desplazamiento() -> None:
    """El corazón de todo: una diferencia usa solo la parte lineal."""
    c = Afin(a=1.0, b=-273.15)
    assert math.isclose(c.desde_canonica(10.0, Clase.INTERVALO), 10.0, abs_tol=1e-12)
    c_f = Afin(a=1.8, b=-459.67)  # K -> °F
    assert math.isclose(c_f.desde_canonica(10.0, Clase.INTERVALO), 18.0, abs_tol=1e-12)


def test_afin_tasa_se_comporta_como_intervalo() -> None:
    """Una derivada de temperatura en °C/s no lleva el −273,15."""
    c = Afin(a=1.0, b=-273.15)
    assert math.isclose(c.desde_canonica(2.5, Clase.TASA), 2.5, abs_tol=1e-12)


def test_afin_varianza_usa_el_factor_al_cuadrado() -> None:
    c = Afin(a=1.8, b=-459.67)
    assert math.isclose(c.desde_canonica(4.0, Clase.VARIANZA), 12.96, abs_tol=1e-12)


def test_afin_con_a_cero_se_rechaza_al_construir() -> None:
    with pytest.raises(ErrorDeUnidad, match="no es invertible"):
        Afin(a=0.0, b=1.0)


@pytest.mark.parametrize("clase", [Clase.PUNTO, Clase.INTERVALO, Clase.TASA, Clase.VARIANZA])
def test_afin_ida_y_vuelta_en_todas_las_clases(clase: Clase) -> None:
    c = Afin(a=1.8, b=-459.67)
    x = 366.3
    assert math.isclose(c.a_canonica(c.desde_canonica(x, clase), clase), x, rel_tol=1e-12)


def test_reciproca_convierte_puntos() -> None:
    c = Reciproca(a=1.0)  # λ -> φ
    assert math.isclose(c.desde_canonica(0.850, Clase.PUNTO), 1.176470588, abs_tol=1e-9)
    assert math.isclose(c.a_canonica(c.desde_canonica(0.85, Clase.PUNTO), Clase.PUNTO), 0.85)


@pytest.mark.parametrize("clase", [Clase.INTERVALO, Clase.TASA, Clase.VARIANZA])
def test_reciproca_rechaza_las_diferencias(clase: Clase) -> None:
    """No es lineal: convertir una diferencia no tiene sentido y el motor debe
    negarse en lugar de devolver un número plausible y falso."""
    c = Reciproca(a=100.0)
    with pytest.raises(ErrorDeUnidad, match="no es lineal"):
        c.desde_canonica(5.0, clase)
    with pytest.raises(ErrorDeUnidad, match="no es lineal"):
        c.a_canonica(5.0, clase)


def test_parametrizada_usa_el_parametro_cuando_se_da() -> None:
    """λ -> AFR con la estequiometría del propio log: 14,7 gasolina, 9,77 E85."""
    c = Parametrizada(parametro_rol="stoichiometry", a_por_omision=14.7)
    assert math.isclose(c.desde_canonica(1.0, Clase.PUNTO), 14.7)
    assert math.isclose(c.desde_canonica(1.0, Clase.PUNTO, param=9.77), 9.77)
    assert math.isclose(c.desde_canonica(0.85, Clase.PUNTO, param=6.4), 5.44, abs_tol=1e-9)


def test_parametrizada_ida_y_vuelta_con_parametro() -> None:
    c = Parametrizada(parametro_rol="stoichiometry", a_por_omision=14.7)
    y = c.desde_canonica(0.88, Clase.PUNTO, param=9.77)
    assert math.isclose(c.a_canonica(y, Clase.PUNTO, param=9.77), 0.88, rel_tol=1e-12)


# --------------------------------------------------------------------------- #
# ADR-009: nada de bucles por muestra
# --------------------------------------------------------------------------- #
class ArrayFalso:
    """Se comporta como un array en la aritmética y estalla si se recorre.

    Es la demostración de que la conversión es vectorizada: si el motor tocara
    los elementos uno a uno, `__iter__`, `__getitem__` o `__len__` saltarían.
    Cuenta además cuántas operaciones sobre el array completo se han aplicado,
    para poder afirmar que son las esperadas y no más.
    """

    def __init__(self, marca: str = "x", operaciones: int = 0) -> None:
        self.marca = marca
        self.operaciones = operaciones

    def _derivado(self) -> ArrayFalso:
        return ArrayFalso(self.marca, self.operaciones + 1)

    # Aritmética: lo único que el motor puede usar.
    def __mul__(self, otro: Any) -> ArrayFalso:
        return self._derivado()

    __rmul__ = __mul__

    def __add__(self, otro: Any) -> ArrayFalso:
        return self._derivado()

    __radd__ = __add__

    def __sub__(self, otro: Any) -> ArrayFalso:
        return self._derivado()

    def __truediv__(self, otro: Any) -> ArrayFalso:
        return self._derivado()

    def __rtruediv__(self, otro: Any) -> ArrayFalso:
        return self._derivado()

    # Acceso por elemento: prohibido (ADR-009).
    def __iter__(self) -> Any:
        raise AssertionError("ADR-009: se ha intentado iterar la serie elemento a elemento")

    def __getitem__(self, i: Any) -> Any:
        raise AssertionError("ADR-009: se ha intentado indexar la serie elemento a elemento")

    def __len__(self) -> int:
        raise AssertionError("ADR-009: se ha intentado tomar la longitud de la serie")


def test_adr009_la_conversion_no_recorre_la_serie(cat: Catalogo) -> None:
    temp = cat.dimension("temperature")
    for clase in (Clase.PUNTO, Clase.INTERVALO, Clase.TASA, Clase.VARIANZA):
        r = desde_canonica(ArrayFalso(), dimension=temp, unidad="degF", clase=clase)
        assert isinstance(r, ArrayFalso)
        # degF tiene b != 0, así que PUNTO son dos pasadas (multiplicar y
        # sumar); las demás clases, una sola.
        esperadas = 2 if clase is Clase.PUNTO else 1
        assert r.operaciones == esperadas, (
            f"{clase.value}: {r.operaciones} operaciones sobre el array, esperadas {esperadas}"
        )


def test_adr009_la_presion_relativa_tampoco_recorre_la_serie(cat: Catalogo) -> None:
    pres = cat.dimension("pressure")
    r = desde_canonica(
        ArrayFalso(), dimension=pres, unidad="psi", clase=Clase.PUNTO, referencia_kpa=101.325
    )
    # psi tiene b = 0, así que son exactamente dos pasadas: restar la referencia
    # y multiplicar por el factor. El `+ b` se omite cuando b == 0 justamente
    # para no gastar una tercera pasada sobre el array.
    assert r.operaciones == 2


def test_adr009_la_reciproca_tampoco(cat: Catalogo) -> None:
    mez = cat.dimension("mixture_ratio")
    r = desde_canonica(ArrayFalso(), dimension=mez, unidad="phi", clase=Clase.PUNTO)
    assert r.operaciones == 1


def test_se_omite_la_suma_cuando_el_desplazamiento_es_cero(cat: Catalogo) -> None:
    """Una unidad con b = 0 no debe gastar una pasada sobre el array en sumar
    cero. Con 5 M de muestras por canal y fotograma, esa pasada sí se nota."""
    rpm = cat.dimension("angular_speed")
    r = desde_canonica(ArrayFalso(), dimension=rpm, unidad="Hz", clase=Clase.PUNTO)
    assert r.operaciones == 1, "una unidad sin desplazamiento debe ser una sola operación"
    # Y con desplazamiento, dos: la optimización no puede saltarse el offset.
    temp = cat.dimension("temperature")
    r2 = desde_canonica(ArrayFalso(), dimension=temp, unidad="degC", clase=Clase.PUNTO)
    assert r2.operaciones == 2


# --------------------------------------------------------------------------- #
# Catálogo real
# --------------------------------------------------------------------------- #
def test_el_catalogo_real_carga(cat: Catalogo) -> None:
    assert len(cat.dimensiones) >= 27
    assert cat.preset_por_omision == "metrico"
    assert 2147483647 in cat.centinelas_i32
    assert "#N/A" in cat.centinelas_texto


def test_casos_conocidos_de_temperatura(cat: Catalogo) -> None:
    d = cat.dimension("temperature")
    assert d.unidad_canonica == "K"
    p = {"dimension": d, "clase": Clase.PUNTO}
    assert math.isclose(desde_canonica(273.15, unidad="degC", **p), 0.0, abs_tol=1e-9)
    assert math.isclose(desde_canonica(273.15, unidad="degF", **p), 32.0, abs_tol=1e-9)
    assert math.isclose(desde_canonica(373.15, unidad="degF", **p), 212.0, abs_tol=1e-9)


def test_casos_conocidos_de_presion(cat: Catalogo) -> None:
    d = cat.dimension("pressure")
    p = {"dimension": d, "clase": Clase.PUNTO}
    assert math.isclose(desde_canonica(100.0, unidad="bar", **p), 1.0, abs_tol=1e-12)
    assert math.isclose(desde_canonica(100.0, unidad="psi", **p), 14.5037738, abs_tol=1e-6)
    # Alias: mbar resuelve a hPa.
    assert math.isclose(desde_canonica(101.325, unidad="mbar", **p), 1013.25, abs_tol=1e-6)


def test_lambda_a_afr_con_la_estequiometria_del_log(cat: Catalogo) -> None:
    d = cat.dimension("mixture_ratio")
    p = {"dimension": d, "clase": Clase.PUNTO, "unidad": "afr"}
    assert math.isclose(desde_canonica(1.0, **p), 14.7, abs_tol=1e-9)
    assert math.isclose(desde_canonica(1.0, param=9.77, **p), 9.77, abs_tol=1e-9)


def test_la_trampa_del_delta_sobre_el_catalogo_real(cat: Catalogo) -> None:
    """Δ de 10 K = 10 °C = 18 °F. La prueba que no se debe romper nunca."""
    d = cat.dimension("temperature")
    assert math.isclose(
        desde_canonica(10.0, dimension=d, unidad="degC", clase=Clase.INTERVALO), 10.0, abs_tol=1e-12
    )
    assert math.isclose(
        desde_canonica(10.0, dimension=d, unidad="degF", clase=Clase.INTERVALO), 18.0, abs_tol=1e-12
    )
    # Y la versión equivocada, para dejar constancia de qué se está evitando.
    assert desde_canonica(10.0, dimension=d, unidad="degC", clase=Clase.PUNTO) < -260


def test_ida_y_vuelta_sobre_todas_las_unidades_del_catalogo(cat: Catalogo) -> None:
    for dim in cat.dimensiones.values():
        for id_uni in dim.unidades:
            for x in (1.0, 42.5, 273.15, 0.85):
                y = desde_canonica(x, dimension=dim, unidad=id_uni, clase=Clase.PUNTO)
                vuelta = a_canonica(y, dimension=dim, unidad=id_uni, clase=Clase.PUNTO)
                assert math.isclose(vuelta, x, rel_tol=1e-12, abs_tol=1e-12), (
                    f"{dim.id}.{id_uni}: {x} -> {y} -> {vuelta}"
                )


# --------------------------------------------------------------------------- #
# Presión absoluta y relativa
# --------------------------------------------------------------------------- #
def test_la_referencia_se_resta_solo_a_los_puntos(cat: Catalogo) -> None:
    d = cat.dimension("pressure")
    ref = cat.referencia_presion_por_omision_kpa
    abs_bar = desde_canonica(200.0, dimension=d, unidad="bar", clase=Clase.PUNTO)
    rel_bar = desde_canonica(
        200.0, dimension=d, unidad="bar", clase=Clase.PUNTO, referencia_kpa=ref
    )
    assert math.isclose(abs_bar, 2.0, abs_tol=1e-12)
    assert math.isclose(rel_bar, (200.0 - ref) / 100.0, abs_tol=1e-12)

    # Un Δ de 50 kPa vale lo mismo en absoluto y en relativo.
    d_abs = desde_canonica(50.0, dimension=d, unidad="psi", clase=Clase.INTERVALO)
    d_rel = desde_canonica(
        50.0, dimension=d, unidad="psi", clase=Clase.INTERVALO, referencia_kpa=ref
    )
    assert math.isclose(d_abs, d_rel, abs_tol=1e-12)
    assert math.isclose(d_abs, 7.251886885, abs_tol=1e-8)


def test_la_referencia_es_reversible(cat: Catalogo) -> None:
    d = cat.dimension("pressure")
    ref = 98.7
    y = desde_canonica(227.2, dimension=d, unidad="psi", clase=Clase.PUNTO, referencia_kpa=ref)
    x = a_canonica(y, dimension=d, unidad="psi", clase=Clase.PUNTO, referencia_kpa=ref)
    assert math.isclose(x, 227.2, rel_tol=1e-12)


def test_la_referencia_se_rechaza_en_dimensiones_que_no_la_admiten(cat: Catalogo) -> None:
    d = cat.dimension("temperature")
    with pytest.raises(ErrorDeUnidad, match="no admite referencia"):
        desde_canonica(300.0, dimension=d, unidad="degC", clase=Clase.PUNTO, referencia_kpa=101.325)


def test_solo_la_presion_admite_referencia(cat: Catalogo) -> None:
    con_ref = [d.id for d in cat.dimensiones.values() if d.admite_referencia]
    assert con_ref == ["pressure"]


# --------------------------------------------------------------------------- #
# Presentación
# --------------------------------------------------------------------------- #
def test_los_decimales_son_los_de_la_unidad(cat: Catalogo) -> None:
    mez = cat.dimension("mixture_ratio")
    # λ con 3 decimales: con uno solo, 0,995 se convertiría en 1,0 y se perdería
    # justo la información que el tuner necesita.
    assert mez.unidad("lambda").formatea(0.995) == "0,995 λ"
    assert mez.unidad("afr").formatea(14.63) == "14,63 AFR"
    rpm = cat.dimension("angular_speed")
    assert rpm.unidad("rpm").formatea(6715.4) == "6715 rpm"


def test_el_separador_decimal_sigue_al_locale(cat: Catalogo) -> None:
    d = cat.dimension("temperature")
    assert d.unidad("degC").formatea(93.15) == "93,2 °C"
    assert d.unidad("degC").formatea(93.15, separador_decimal=".") == "93.2 °C"


def test_la_etiqueta_de_presion_dice_si_es_absoluta_o_relativa(cat: Catalogo) -> None:
    """«2 bar» sin más es la fuente de error más común al comparar herramientas."""
    d = cat.dimension("pressure")
    assert etiqueta_de(d, "bar") == "bar (abs)"
    assert etiqueta_de(d, "bar", relativa=True) == "bar (rel)"
    # Las demás dimensiones no llevan sufijo.
    assert etiqueta_de(cat.dimension("temperature"), "degC") == "°C"


def test_unidad_desconocida_da_un_error_util(cat: Catalogo) -> None:
    d = cat.dimension("temperature")
    with pytest.raises(ErrorDeUnidad, match="Disponibles"):
        d.unidad("kelvines")


def test_dimension_desconocida_da_un_error_util(cat: Catalogo) -> None:
    with pytest.raises(ErrorDeUnidad, match="dimensión desconocida"):
        cat.dimension("presion")


def test_las_dimensiones_no_convertibles_tienen_una_sola_unidad(cat: Catalogo) -> None:
    for d in cat.dimensiones.values():
        if not d.convertible:
            assert len(d.unidades) == 1, f"{d.id}: no convertible con varias unidades"


def test_unknown_se_muestra_en_crudo(cat: Catalogo) -> None:
    """Mitigación de R1: sin escala confirmada, ni unidad ni selector."""
    d = cat.dimension("unknown")
    assert d.mostrar_en_crudo is True
    assert d.convertible is False


# --------------------------------------------------------------------------- #
# Coherencia del catálogo, comprobada al cargar
# --------------------------------------------------------------------------- #
def test_se_rechaza_un_catalogo_con_desplazamiento_mal_marcado(tmp_path: Path) -> None:
    """Si `origen_desplazado` no coincide con b != 0, el motor podría aplicar el
    desplazamiento a un delta creyendo que no hay ninguno. Se detecta al cargar,
    no en producción."""
    malo = tmp_path / "malo.toml"
    malo.write_text(
        "[dimensiones.temperature]\n"
        'canonica = "K"\n'
        "[dimensiones.temperature.unidades.K]\n"
        'etiqueta = "K"\n'
        'desde_canonica = { tipo = "afin", a = 1.0, b = 0.0 }\n'
        "decimales = 1\n"
        "[dimensiones.temperature.unidades.degC]\n"
        'etiqueta = "C"\n'
        'desde_canonica = { tipo = "afin", a = 1.0, b = -273.15 }\n'
        "decimales = 1\n",  # falta origen_desplazado = true
        encoding="utf-8",
    )
    with malo.open("rb") as fh, pytest.raises(ErrorDeUnidad, match="origen_desplazado"):
        cargar_catalogo(fh)


def test_se_rechaza_un_tipo_de_conversion_desconocido(tmp_path: Path) -> None:
    malo = tmp_path / "malo.toml"
    malo.write_text(
        "[dimensiones.x]\n"
        'canonica = "u"\n'
        "[dimensiones.x.unidades.u]\n"
        'etiqueta = "u"\n'
        'desde_canonica = { tipo = "logaritmica", a = 1.0 }\n'
        "decimales = 1\n",
        encoding="utf-8",
    )
    with malo.open("rb") as fh, pytest.raises(ErrorDeUnidad, match="desconocido"):
        cargar_catalogo(fh)
