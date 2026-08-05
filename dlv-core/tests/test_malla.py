"""Pruebas de la malla RPM x MAP (tarea F4-01, `docs/04` §4.6).

Lo que hay que proteger, en orden de gravedad si se rompe:

1. **Una celda sin muestras es NaN, nunca 0,0** (`media`, `desviacion_tipica`,
   `minimo`, `maximo`). Es la propiedad más fácil de romper por accidente --
   basta con que la división "segura" se filtre sin la máscara final -- y la
   más cara si se rompe: un 0,0 con pinta de λ real es peor que no tener nada.
2. **`cuenta` sí es 0 de verdad**, no NaN: es la excepción documentada.
3. **Mínimo/máximo son correctos por celda**, no solo "no revientan": se
   comprueban contra una referencia calculada a mano, celda a celda, con
   varias muestras por celda y alguna fuera de rango.
4. **El binning coloca cada muestra en la celda correcta**, con el convenio
   de bordes semiabiertos salvo el último (inclusivo por los dos lados).
5. **`bordes_por_omision` incluye siempre el máximo real**, pese al redondeo
   de coma flotante de la acumulación.

Como en `test_reloj.py`, las pruebas de agregación usan `XpVec`, una
implementación de biblioteca estándar del protocolo `Vectorial`. No es un
simulacro: ejercita exactamente el mismo código de `construir_malla` que
correrá con NumPy, cuyas siete funciones son las que el protocolo declara.
"""

from __future__ import annotations

import bisect
import math
from typing import Any

import pytest

from dlv_core.malla import (
    ErrorDeMalla,
    Malla,
    bordes_en_unidad_activa,
    bordes_por_omision,
    construir_malla,
)
from dlv_core.unidades import Afin, Dimension, Unidad


# --------------------------------------------------------------------------- #
# Implementación de `Vectorial` con biblioteca estándar
# --------------------------------------------------------------------------- #
class Vec(list[Any]):
    """Vector de biblioteca estándar con la aritmética elemento a elemento
    que necesita `construir_malla`.

    Los bucles están AQUÍ, en la prueba -- igual que `ListaV` en
    `test_reloj.py` -- que es donde ADR-009 permite que estén: lo que prohíbe
    es que estén en `dlv-core`. Con NumPy, cada uno de estos métodos es una
    pasada en C sobre el array completo.

    Distingue indexado por MÁSCARA booleana de indexado por posiciones
    enteras mirando el tipo del primer elemento de la clave: `bool` es un
    tipo de Python distinto de `int` (aunque sea su subclase), así que un
    índice `0`/`1` de verdad nunca se confunde con una máscara.
    """

    def __getitem__(self, clave: Any) -> Any:  # type: ignore[override]
        if isinstance(clave, slice):
            return Vec(list.__getitem__(self, clave))
        if isinstance(clave, (Vec, list, tuple)):
            claves = list(clave)
            if claves and isinstance(claves[0], bool):
                return Vec(v for v, m in zip(self, claves, strict=True) if m)
            return Vec(list.__getitem__(self, int(i)) for i in claves)
        return list.__getitem__(self, clave)

    def __setitem__(self, clave: Any, valor: Any) -> None:
        if isinstance(clave, (Vec, list, tuple)):
            claves = list(clave)
            if claves and isinstance(claves[0], bool):
                for i, m in enumerate(claves):
                    if m:
                        list.__setitem__(self, i, valor)
                return
        list.__setitem__(self, clave, valor)

    def _cmp(self, otro: Any, op: Any) -> Vec:
        if isinstance(otro, list):
            return Vec(op(a, b) for a, b in zip(self, otro, strict=True))
        return Vec(op(a, otro) for a in self)

    def __ge__(self, otro: Any) -> Any:
        return self._cmp(otro, lambda a, b: a >= b)

    def __le__(self, otro: Any) -> Any:
        return self._cmp(otro, lambda a, b: a <= b)

    def __gt__(self, otro: Any) -> Any:
        return self._cmp(otro, lambda a, b: a > b)

    def __eq__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._cmp(otro, lambda a, b: a == b)

    def __and__(self, otro: Any) -> Any:
        return Vec(bool(a) and bool(b) for a, b in zip(self, otro, strict=True))

    def _op(self, otro: Any, op: Any) -> Vec:
        if isinstance(otro, list):
            return Vec(op(a, b) for a, b in zip(self, otro, strict=True))
        return Vec(op(a, otro) for a in self)

    def __add__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a + b)

    def __sub__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a - b)

    def __mul__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a * b)

    __rmul__ = __mul__

    def __truediv__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a / b)

    def __bool__(self) -> bool:
        # Igual que NumPy: el valor de verdad de un vector de longitud != 1 es
        # ambiguo. Sin esto, un `assert vec_a == vec_b` accidental (en vez de
        # `list(vec_a) == pytest.approx(list(vec_b))`) compararía elemento a
        # elemento y luego evaluaría la lista resultante como verdadera por
        # ser no vacía, sin comprobar nada -- exactamente el error que NumPy
        # evita lanzando en vez de dejar pasar un `if array:` silencioso.
        if len(self) == 1:
            return bool(list.__getitem__(self, 0))
        raise ValueError("el valor de verdad de un Vec de longitud != 1 es ambiguo")


class XpVec:
    """Las siete funciones del protocolo `Vectorial`, con los nombres de NumPy."""

    def searchsorted(self, a: Any, v: Any, side: str) -> Any:
        hallar = bisect.bisect_right if side == "right" else bisect.bisect_left
        a_lista = list(a)
        return Vec(hallar(a_lista, x) for x in v)

    def argsort(self, a: Any) -> Any:
        indices = list(range(len(a)))
        indices.sort(key=lambda i: a[i])
        return Vec(indices)

    def cumsum(self, a: Any) -> Any:
        total = 0
        salida: Vec = Vec()
        for x in a:
            total += x
            salida.append(total)
        return salida

    def bincount(self, x: Any, weights: Any, minlength: int) -> Any:
        x_lista = list(x)
        n = max(minlength, (max(x_lista) + 1) if x_lista else 0)
        if weights is None:
            salida: Vec = Vec([0] * n)
            for i in x_lista:
                salida[i] += 1
            return salida
        salida = Vec([0.0] * n)
        for i, w in zip(x_lista, list(weights), strict=True):
            salida[i] += w
        return salida

    def sqrt(self, a: Any) -> Any:
        return Vec(math.sqrt(x) for x in a)

    def min(self, a: Any) -> Any:
        return min(a)

    def max(self, a: Any) -> Any:
        return max(a)


@pytest.fixture
def xp() -> XpVec:
    return XpVec()


def _es_nan(x: Any) -> bool:
    return isinstance(x, float) and math.isnan(x)


# --------------------------------------------------------------------------- #
# Bordes
# --------------------------------------------------------------------------- #
def test_bordes_por_omision_cubre_el_rango_exacto(xp: XpVec) -> None:
    bordes = bordes_por_omision(Vec([1000.0, 4500.0, 2200.0, 7000.0]), 4, xp=xp)
    assert bordes[0] == pytest.approx(1000.0)
    assert bordes[-1] == pytest.approx(7000.0)
    assert len(bordes) == 5


def test_bordes_por_omision_el_ultimo_borde_es_el_maximo_exacto(xp: XpVec) -> None:
    """El redondeo de la acumulación no puede dejar el máximo real fuera de rango.

    Con un paso irracional (rango que no divide exacto entre `n_bins`), sumar
    `paso * i` en coma flotante puede quedarse una fracción de unidad por
    debajo del máximo verdadero. Si eso ocurriera, la propia muestra que
    definió el rango se marcaría como inválida al construir la malla.
    """
    valores = Vec([0.0, 1.0, 100.0 / 3.0])
    bordes = bordes_por_omision(valores, 7, xp=xp)
    assert bordes[-1] == 100.0 / 3.0


def test_bordes_por_omision_rechaza_n_bins_no_positivo(xp: XpVec) -> None:
    with pytest.raises(ErrorDeMalla, match="n_bins"):
        bordes_por_omision(Vec([1.0, 2.0]), 0, xp=xp)


def test_bordes_por_omision_rechaza_rango_degenerado(xp: XpVec) -> None:
    """Un canal constante no da bordes: inventar un ancho sería un dato falso."""
    with pytest.raises(ErrorDeMalla, match="degenerado"):
        bordes_por_omision(Vec([5.0, 5.0, 5.0]), 4, xp=xp)


def test_bordes_por_omision_rechaza_un_canal_todo_nan(xp: XpVec) -> None:
    """Sin ninguna muestra válida no hay rango que deducir, y devolver uno
    inventado es peor que parar."""
    with pytest.raises(ErrorDeMalla, match="sin ninguna muestra válida"):
        bordes_por_omision(Vec([float("nan"), float("nan")]), 4, xp=xp)


def test_bordes_por_omision_rechaza_un_canal_vacio(xp: XpVec) -> None:
    with pytest.raises(ErrorDeMalla, match="sin ninguna muestra válida"):
        bordes_por_omision(Vec([]), 4, xp=xp)


def test_bordes_por_omision_ignora_los_huecos_del_canal(xp: XpVec) -> None:
    """Un canal con huecos es lo NORMAL: el muestreo es disperso y
    multifrecuencia (`docs/01` §1.4), así que un canal a 5 Hz tiene NaN en la
    mayoría de las marcas de tiempo. El rango es el de las muestras que SÍ hay;
    los huecos no lo invalidan ni lo estiran."""
    nan = float("nan")
    bordes = bordes_por_omision(Vec([nan, 1000.0, nan, 7000.0, nan, 2200.0]), 4, xp=xp)
    assert bordes[0] == pytest.approx(1000.0)
    assert bordes[-1] == pytest.approx(7000.0)
    assert len(bordes) == 5


def test_bordes_por_omision_no_depende_de_donde_este_el_hueco(xp: XpVec) -> None:
    """La versión anterior tomaba el min/max sin filtrar, y entonces el
    resultado dependía de la implementación de `Vectorial` y de la POSICIÓN del
    NaN: `numpy.min` de un array con NaN es NaN, y el `min` de la biblioteca
    estándar devuelve el primer elemento o el NaN según el orden. Un módulo cuyo
    resultado depende de eso no es comprobable."""
    nan = float("nan")
    referencia = bordes_por_omision(Vec([1000.0, 4000.0, 7000.0]), 4, xp=xp)
    for con_hueco in (
        Vec([nan, 1000.0, 4000.0, 7000.0]),
        Vec([1000.0, nan, 4000.0, 7000.0]),
        Vec([1000.0, 4000.0, 7000.0, nan]),
    ):
        assert bordes_por_omision(con_hueco, 4, xp=xp) == pytest.approx(referencia)


def test_valida_bordes_rechaza_menos_de_dos() -> None:
    with pytest.raises(ErrorDeMalla, match="al menos dos bordes"):
        construir_malla(
            Vec([1.0]), Vec([1.0]), Vec([1.0]), bordes_rpm=[1000.0], bordes_map=[0.0, 200.0]
        )


def test_valida_bordes_rechaza_no_creciente() -> None:
    with pytest.raises(ErrorDeMalla, match="estrictamente creciente"):
        construir_malla(
            Vec([1.0]),
            Vec([1.0]),
            Vec([1.0]),
            bordes_rpm=[1000.0, 900.0, 2000.0],
            bordes_map=[0.0, 200.0],
        )


def test_construir_malla_rechaza_longitudes_distintas() -> None:
    with pytest.raises(ErrorDeMalla, match="misma longitud"):
        construir_malla(
            Vec([1.0, 2.0]),
            Vec([1.0]),
            Vec([1.0, 2.0]),
            bordes_rpm=[0.0, 10.0],
            bordes_map=[0.0, 10.0],
        )


# --------------------------------------------------------------------------- #
# Agregación: la propiedad central -- celda vacía es NaN, no 0,0
# --------------------------------------------------------------------------- #
def test_celda_sin_muestras_es_nan_no_cero(xp: XpVec) -> None:
    """La prueba que protege la regla más cara de romper de §4.6.

    Una sola celda (bordes de un solo bin en cada eje) con una muestra cuyo
    valor de canal es exactamente 0,0 (un λ de error plausible): la celda
    tiene datos y su media debe ser 0,0 de verdad. Con dos celdas, la vacía
    debe salir NaN, nunca 0,0 -- que sería indistinguible del caso anterior.
    """
    malla = construir_malla(
        Vec([1000.0, 1000.0]),
        Vec([50.0, 50.0]),
        Vec([0.0, 0.0]),
        bordes_rpm=[0.0, 2000.0, 4000.0],  # dos bins de RPM: [0,2000) y [2000,4000]
        bordes_map=[0.0, 100.0],  # un bin de MAP
        xp=xp,
    )
    # Celda (0, 0): las dos muestras caen aquí, valor 0.0 -- media real 0,0.
    assert malla.cuenta[0] == 2
    assert malla.media[0] == pytest.approx(0.0)
    assert not _es_nan(malla.media[0])
    # Celda (1, 0): ninguna muestra -- NaN, no 0,0.
    assert malla.cuenta[1] == 0
    assert _es_nan(malla.media[1])
    assert _es_nan(malla.desviacion_tipica[1])
    assert _es_nan(malla.minimo[1])
    assert _es_nan(malla.maximo[1])


def test_toda_la_malla_vacia_no_revienta(xp: XpVec) -> None:
    """Ninguna muestra cae dentro del rango configurado: todo NaN, cero avisos
    de división, ningún fallo."""
    malla = construir_malla(
        Vec([9000.0, 9500.0]),
        Vec([50.0, 60.0]),
        Vec([1.0, 2.0]),
        bordes_rpm=[0.0, 1000.0],
        bordes_map=[0.0, 100.0],
        xp=xp,
    )
    assert malla.cuenta[0] == 0
    assert _es_nan(malla.media[0])
    assert _es_nan(malla.minimo[0])
    assert _es_nan(malla.maximo[0])


def test_muestra_con_valor_nan_no_cuenta(xp: XpVec) -> None:
    """Una lectura inválida del canal (p. ej. λ de error del sensor) no debe
    contarse como "cero muestras válidas": se excluye de la agregación."""
    malla = construir_malla(
        Vec([1000.0, 1000.0, 1000.0]),
        Vec([50.0, 50.0, 50.0]),
        Vec([1.0, float("nan"), 3.0]),
        bordes_rpm=[0.0, 2000.0],
        bordes_map=[0.0, 100.0],
        xp=xp,
    )
    assert malla.cuenta[0] == 2
    assert malla.media[0] == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# Agregación: valores correctos, no solo "no revienta"
# --------------------------------------------------------------------------- #
def test_agregacion_completa_contra_referencia_a_mano(xp: XpVec) -> None:
    """Malla de 2x2 celdas con varias muestras por celda, calculada a mano.

    RPM: bordes [0, 3000, 6000] -> bin 0 = [0,3000), bin 1 = [3000,6000].
    MAP: bordes [0, 100, 200]   -> bin 0 = [0,100),  bin 1 = [100,200].

    Celda (0,0) (rpm<3000, map<100): valores [10.0, 20.0]  -> media 15, cuenta 2
    Celda (0,1) (rpm<3000, map>=100): valor [5.0]            -> media 5,  cuenta 1
    Celda (1,0) (rpm>=3000, map<100): sin muestras           -> NaN
    Celda (1,1) (rpm>=3000, map>=100): valores [1.0, 2.0, 9.0] -> cuenta 3
    """
    rpm = Vec([1000.0, 2000.0, 1500.0, 4000.0, 5000.0, 4500.0])
    presion = Vec([50.0, 90.0, 150.0, 100.0, 199.0, 150.0])
    valor = Vec([10.0, 20.0, 5.0, 1.0, 2.0, 9.0])
    malla = construir_malla(
        rpm, presion, valor, bordes_rpm=[0.0, 3000.0, 6000.0], bordes_map=[0.0, 100.0, 200.0], xp=xp
    )
    assert malla.forma == (2, 2)
    # Orden de fila: (0,0)->0, (0,1)->1, (1,0)->2, (1,1)->3.
    assert list(malla.cuenta) == [2, 1, 0, 3]
    assert malla.media[0] == pytest.approx(15.0)
    assert malla.media[1] == pytest.approx(5.0)
    assert _es_nan(malla.media[2])
    assert malla.media[3] == pytest.approx(4.0)

    assert malla.minimo[0] == pytest.approx(10.0)
    assert malla.maximo[0] == pytest.approx(20.0)
    assert malla.minimo[1] == pytest.approx(5.0)
    assert malla.maximo[1] == pytest.approx(5.0)
    assert malla.minimo[3] == pytest.approx(1.0)
    assert malla.maximo[3] == pytest.approx(9.0)

    # Desviación típica poblacional de [10, 20]: media 15, var ((5^2+5^2)/2)=25.
    assert malla.desviacion_tipica[0] == pytest.approx(5.0)
    # Una sola muestra: varianza 0, desviación 0 (no NaN: sí hay dato).
    assert malla.desviacion_tipica[1] == pytest.approx(0.0)
    # [1, 2, 9]: media 4; varianza = mean((1-4)^2,(2-4)^2,(9-4)^2) = (9+4+25)/3.
    assert malla.desviacion_tipica[3] == pytest.approx(math.sqrt(38 / 3))


def test_muestras_fuera_de_rango_se_excluyen(xp: XpVec) -> None:
    """Una muestra por debajo del mínimo o por encima del máximo configurado
    no se cuela en el bin extremo: se descarta, no se recorta."""
    malla = construir_malla(
        Vec([-500.0, 1000.0, 20000.0]),
        Vec([50.0, 50.0, 50.0]),
        Vec([1.0, 2.0, 3.0]),
        bordes_rpm=[0.0, 5000.0],
        bordes_map=[0.0, 100.0],
        xp=xp,
    )
    assert malla.cuenta[0] == 1
    assert malla.media[0] == pytest.approx(2.0)


def test_borde_superior_exacto_cae_en_el_ultimo_bin(xp: XpVec) -> None:
    """El último bin es cerrado por los dos lados: una muestra exactamente en
    el borde superior del rango no se pierde."""
    malla = construir_malla(
        Vec([2000.0, 4000.0]),
        Vec([50.0, 50.0]),
        Vec([1.0, 2.0]),
        bordes_rpm=[0.0, 2000.0, 4000.0],
        bordes_map=[0.0, 100.0],
        xp=xp,
    )
    # 2000.0 cae en el bin 1 (borde compartido: el bin superior lo reclama),
    # 4000.0 también cae en el bin 1 (es el borde superior absoluto).
    assert list(malla.cuenta) == [0, 2]
    assert malla.media[1] == pytest.approx(1.5)


def test_borde_interior_exacto_va_al_bin_superior(xp: XpVec) -> None:
    """Convenio de bin semiabierto: `bordes[i]` pertenece al bin `i`, no al
    `i - 1`, salvo que sea el borde superior absoluto (probado aparte)."""
    malla = construir_malla(
        Vec([2000.0]),
        Vec([50.0]),
        Vec([7.0]),
        bordes_rpm=[0.0, 2000.0, 4000.0],
        bordes_map=[0.0, 100.0],
        xp=xp,
    )
    assert malla.cuenta[0] == 0
    assert malla.cuenta[1] == 1


def test_un_hueco_en_rpm_o_en_map_excluye_la_muestra(xp: XpVec) -> None:
    """El docstring de `_indices_de_bin` dice que un NaN en los EJES sale como no
    válido sin ningún caso especial, porque `nan >= x` y `nan <= x` son los dos
    falsos. Es la otra mitad del muestreo disperso: no solo el canal agregado
    tiene huecos, también los ejes. Una muestra sin RPM no puede ir a ninguna
    celda, y colarla en la celda 0 sería inventar dónde estaba el motor."""
    nan = float("nan")
    malla = construir_malla(
        Vec([1000.0, nan, 1000.0]),
        Vec([50.0, 50.0, nan]),
        Vec([10.0, 20.0, 30.0]),
        bordes_rpm=[0.0, 2000.0],
        bordes_map=[0.0, 100.0],
        xp=xp,
    )
    assert malla.cuenta[0] == 1
    assert malla.media[0] == pytest.approx(10.0)


def test_con_bordes_deducidos_no_se_pierde_ninguna_muestra(xp: XpVec) -> None:
    """La razón de ser de `bordes[-1] = maximo` en `bordes_por_omision`, extremo
    a extremo: si el último borde saliera de acumular `mínimo + paso·i`, el
    redondeo podría dejarlo por debajo del máximo real y la propia muestra que
    definió el rango quedaría fuera. Con los bordes deducidos del canal, la suma
    de las cuentas tiene que ser el número de muestras: ni una menos."""
    rpm = Vec([float(800 + 137 * i) for i in range(50)])
    presion = Vec([float(20 + 3.7 * i) for i in range(50)])
    valor = Vec([float(i) for i in range(50)])
    malla = construir_malla(
        rpm,
        presion,
        valor,
        bordes_rpm=bordes_por_omision(rpm, 7, xp=xp),
        bordes_map=bordes_por_omision(presion, 11, xp=xp),
        xp=xp,
    )
    assert sum(malla.cuenta) == 50


# --------------------------------------------------------------------------- #
# Unidad activa
# --------------------------------------------------------------------------- #
def _dimension_presion() -> Dimension:
    kpa = Unidad(id="kPa", etiqueta="kPa", conversion=Afin(a=1.0, b=0.0), decimales=0)
    bar = Unidad(id="bar", etiqueta="bar", conversion=Afin(a=0.01, b=0.0), decimales=2)
    return Dimension(
        id="pressure",
        etiqueta="Presión",
        unidad_canonica="kPa",
        unidades={"kPa": kpa, "bar": bar},
        admite_referencia=True,
    )


def _dimension_rpm() -> Dimension:
    rpm = Unidad(id="rpm", etiqueta="rpm", conversion=Afin(a=1.0, b=0.0), decimales=0)
    return Dimension(
        id="angular_speed", etiqueta="Régimen", unidad_canonica="rpm", unidades={"rpm": rpm}
    )


def test_bordes_en_unidad_activa_convierte_presion_a_bar() -> None:
    bordes = bordes_en_unidad_activa(
        [0.0, 100.0, 200.0], dimension=_dimension_presion(), unidad="bar"
    )
    assert bordes == pytest.approx([0.0, 1.0, 2.0])


def test_bordes_en_unidad_activa_rpm_es_identidad() -> None:
    bordes = bordes_en_unidad_activa(
        [0.0, 1000.0, 6000.0], dimension=_dimension_rpm(), unidad="rpm"
    )
    assert bordes == pytest.approx([0.0, 1000.0, 6000.0])


def test_bordes_en_unidad_activa_aplica_referencia_solo_como_punto() -> None:
    """Los bordes son PUNTOS: la referencia de presión SÍ se resta (es un
    cambio de origen para un valor absoluto), a diferencia de un INTERVALO.
    """
    bordes = bordes_en_unidad_activa(
        [101.325, 201.325], dimension=_dimension_presion(), unidad="kPa", referencia_kpa=101.325
    )
    assert bordes == pytest.approx([0.0, 100.0])


def test_bordes_en_unidad_activa_funciona_con_una_malla_de_verdad(xp: XpVec) -> None:
    malla = construir_malla(
        Vec([1000.0]),
        Vec([150.0]),
        Vec([1.0]),
        bordes_rpm=[0.0, 2000.0],
        bordes_map=[0.0, 100.0, 200.0],
        xp=xp,
    )
    bordes_map_bar = bordes_en_unidad_activa(
        malla.bordes_map, dimension=_dimension_presion(), unidad="bar"
    )
    assert bordes_map_bar == pytest.approx([0.0, 1.0, 2.0])


# --------------------------------------------------------------------------- #
# ADR-009 comprobado por conducta, no solo por el patrón de `banco.py`
# --------------------------------------------------------------------------- #
def test_el_bucle_de_min_max_no_crece_con_las_muestras(xp: XpVec) -> None:
    """La propiedad que importa: el número de llamadas a `min`/`max` es el
    número de CELDAS con datos, no el número de muestras.

    Se comprueba con dos tamaños de entrada muy distintos (30 y 3000 muestras)
    sobre la MISMA malla de 3x1 celdas: si `construir_malla` recorriera las
    muestras en vez de las celdas, las llamadas a `min`/`max` crecerían con la
    longitud de la entrada. Con el diseño de `argsort` + bucle sobre celdas,
    se quedan fijas en 3 (una por celda, todas con datos) sea cual sea `n`.
    """

    class XpQueCuenta(XpVec):
        def __init__(self) -> None:
            self.llamadas_min = 0
            self.llamadas_max = 0

        def min(self, a: Any) -> Any:
            self.llamadas_min += 1
            return super().min(a)

        def max(self, a: Any) -> Any:
            self.llamadas_max += 1
            return super().max(a)

    for n in (30, 3000):
        contador = XpQueCuenta()
        rpm = Vec([float(1000 + (i % 3) * 2000) for i in range(n)])
        presion = Vec([50.0] * n)
        valor = Vec([float(i) for i in range(n)])
        malla = construir_malla(
            rpm,
            presion,
            valor,
            bordes_rpm=[0.0, 2000.0, 4000.0, 6000.0],
            bordes_map=[0.0, 100.0],
            xp=contador,
        )
        assert list(malla.cuenta) == [n // 3, n // 3, n // 3], "n es múltiplo de 3 a propósito"
        assert contador.llamadas_min == 3, f"n={n}: {contador.llamadas_min} llamadas a min"
        assert contador.llamadas_max == 3, f"n={n}: {contador.llamadas_max} llamadas a max"


# --------------------------------------------------------------------------- #
# Contratos de tipo
# --------------------------------------------------------------------------- #
def test_malla_es_inmutable() -> None:
    assert Malla.__dataclass_params__.frozen
