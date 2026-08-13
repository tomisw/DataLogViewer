"""Marcha estimada por agrupación velocidad/régimen (tarea F3-20).

Especificación: `docs/04-perfiles-motorsport.md` §4.5.

QUÉ PROTEGE
===========
Que una marcha detectada sea una marcha, y que lo que no lo es se quede sin
asignar CON su motivo. Una marcha inventada en medio de un cambio es peor que un
hueco, porque los detectores que la usen como contexto se la creerán.

Los umbrales salen de `data/umbrales.toml`, no del código, y hay dos guardas que
lo comprueban (firma sin valores por omisión y escaneo AST del módulo), igual que
en `primitivas.py` y `plausibilidad.py`.

Solo biblioteca estándar: el doble `Vec`/`XpVec` implementa el protocolo
`Vectorial` con los bucles AQUÍ, que es donde ADR-009 los permite.
"""

from __future__ import annotations

import ast
import bisect
import inspect
import tomllib
from pathlib import Path
from typing import Any

import pytest

from dlv_core.marcha import (
    ErrorDeMarcha,
    MotivoSinMarcha,
    UmbralesDeMarcha,
    detectar_marchas,
)
from dlv_core.primitivas import Serie
from dlv_core.unidades import Clase

RAIZ = Path(__file__).resolve().parents[2]
MODULO = RAIZ / "dlv-core" / "src" / "dlv_core" / "marcha.py"
UMBRALES_TOML = RAIZ / "data" / "umbrales.toml"


class Vec(list[Any]):
    """Vector de biblioteca estándar con la aritmética que el módulo le pide."""

    def _op(self, otro: Any, f: Any) -> Vec:
        if isinstance(otro, (list, Vec)):
            return Vec(f(a, b) for a, b in zip(self, otro, strict=True))
        return Vec(f(a, otro) for a in self)

    def __add__(self, otro: Any) -> Vec:  # type: ignore[override]
        return self._op(otro, lambda a, b: a + b)

    def __sub__(self, otro: Any) -> Vec:
        return self._op(otro, lambda a, b: a - b)

    def __mul__(self, otro: Any) -> Vec:  # type: ignore[override]
        return self._op(otro, lambda a, b: a * b)

    __rmul__ = __mul__

    def __truediv__(self, otro: Any) -> Vec:
        return self._op(otro, lambda a, b: a / b)

    def __floordiv__(self, otro: Any) -> Vec:
        return self._op(otro, lambda a, b: a // b)

    def __mod__(self, otro: Any) -> Vec:
        return self._op(otro, lambda a, b: a % b)

    def __ge__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a >= b)

    def __le__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a <= b)

    def __gt__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a > b)

    def __lt__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a < b)

    def __hash__(self) -> int:  # type: ignore[override]
        return id(self)


class XpVec:
    """El protocolo `Vectorial` sobre listas. Los bucles viven aquí."""

    def searchsorted(self, a: Any, v: Any, side: str, /) -> Any:
        f = bisect.bisect_left if side == "left" else bisect.bisect_right
        return Vec(f(list(a), x) for x in v)

    def argsort(self, a: Any, /) -> Any:
        return Vec(sorted(range(len(a)), key=lambda i: a[i]))

    def cumsum(self, a: Any, /) -> Any:
        total = 0.0
        salida = []
        for x in a:
            total += x
            salida.append(total)
        return Vec(salida)

    def bincount(self, x: Any, weights: Any, minlength: int, /) -> Any:
        cuentas = [0.0] * max(minlength, (max(x) + 1) if len(x) else 0)
        for i, celda in enumerate(x):
            cuentas[int(celda)] += 1.0 if weights is None else float(weights[i])
        return Vec(cuentas)

    def min(self, a: Any, /) -> Any:
        return min(a)

    def max(self, a: Any, /) -> Any:
        return max(a)


@pytest.fixture
def xp() -> XpVec:
    return XpVec()


@pytest.fixture(scope="module")
def umbrales() -> UmbralesDeMarcha:
    """Los del fichero de datos, no unos inventados para que salga bien."""
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    return UmbralesDeMarcha.desde_mapa(
        {
            **bruto["marcha"],
            "ventana_validez_ms": bruto["motor_de_deteccion"]["ventana_validez_ms"],
        }
    )


def _serie(valores: list[float], dt_ms: float = 50.0) -> Serie:
    return Serie(
        t_ms=Vec([i * dt_ms for i in range(len(valores))]),
        v=Vec(valores),
        clase=Clase.PUNTO,
    )


def _en_marcha(cociente: float, n: int, rpm: float = 4000.0) -> tuple[Serie, Serie]:
    """`n` muestras a régimen constante con el cociente pedido (km/h por 1000 rpm)."""
    return _serie([rpm] * n), _serie([cociente * rpm / 1000.0] * n)


# --------------------------------------------------------------------------- #
# Lo que tiene que detectar
# --------------------------------------------------------------------------- #
def test_una_marcha_constante_es_una_marcha(umbrales: UmbralesDeMarcha, xp: XpVec) -> None:
    reg, vel = _en_marcha(15.4, 100)
    inf = detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)
    assert len(inf.marchas) == 1
    assert inf.marchas[0].cociente == pytest.approx(15.4, abs=umbrales.ancho_de_celda)
    assert inf.marchas[0].n_muestras == 100
    assert inf.fraccion_asignada == pytest.approx(1.0)


def test_tres_marchas_dan_tres_acumulaciones(umbrales: UmbralesDeMarcha, xp: XpVec) -> None:
    """Y ordenadas de la más corta a la más larga, que es lo que fija el índice."""
    # 30 por marcha, por encima de `muestras_minimas_por_marcha` (25 en el
    # fichero). Con 20 las tres se descartaban, que es lo que debe pasar.
    cocientes = [7.8] * 30 + [11.7] * 30 + [15.4] * 30
    reg = _serie([4000.0] * len(cocientes))
    vel = _serie([c * 4.0 for c in cocientes])
    inf = detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)
    assert [m.indice for m in inf.marchas] == [1, 2, 3]
    obtenidos = [m.cociente for m in inf.marchas]
    for esperado, obtenido in zip([7.8, 11.7, 15.4], obtenidos, strict=True):
        assert obtenido == pytest.approx(esperado, abs=umbrales.ancho_de_celda)


def test_las_separaciones_son_las_relaciones_de_la_caja(
    umbrales: UmbralesDeMarcha, xp: XpVec
) -> None:
    """Lo único de este informe que se puede confrontar con una ficha técnica.

    El grupo final y el desarrollo del neumático se cancelan al dividir dos
    cocientes consecutivos, así que lo que queda son las relaciones de la caja. Con
    los cuatro cocientes medidos en el AutoLog real salen 1,66 · 1,50 · 1,32, y la
    caja de un R33 GTR da 1,670 · 1,479 · 1,302.
    """
    cocientes = [4.7] * 30 + [7.8] * 30 + [11.7] * 30 + [15.4] * 30
    reg = _serie([4000.0] * 120)
    vel = _serie([c * 4.0 for c in cocientes])
    inf = detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)
    assert len(inf.marchas) == 4
    esperadas = (7.8 / 4.7, 11.7 / 7.8, 15.4 / 11.7)
    for esperada, obtenida in zip(esperadas, inf.separaciones, strict=True):
        assert obtenida == pytest.approx(esperada, rel=0.05)


# --------------------------------------------------------------------------- #
# Lo que NO tiene que inventar
# --------------------------------------------------------------------------- #
def test_el_coche_parado_no_tiene_marcha(umbrales: UmbralesDeMarcha, xp: XpVec) -> None:
    """Ralentí en punto muerto: el cociente sería 0 y no significa nada."""
    reg = _serie([900.0] * 50)
    vel = _serie([0.0] * 50)
    inf = detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)
    assert inf.marchas == ()
    assert inf.motivos[MotivoSinMarcha.PARADO_O_EMBRAGUE] == 50
    assert inf.n_utiles == 0


def test_el_cambio_de_marcha_se_queda_sin_asignar(umbrales: UmbralesDeMarcha, xp: XpVec) -> None:
    """Durante el cambio el cociente pasa por todos los valores intermedios, y
    ninguno es una marcha. Forzarlo a la más cercana daría una marcha falsa justo
    donde un detector de sobre-régimen se fija."""
    # 40 muestras en una marcha, 6 de transición, 40 en la otra.
    cocientes = [7.8] * 40 + [8.8, 9.6, 10.2, 10.8, 11.2, 11.5] + [11.7] * 40
    reg = _serie([4000.0] * len(cocientes))
    vel = _serie([c * 4.0 for c in cocientes])
    inf = detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)
    assert len(inf.marchas) == 2
    # Las de transición no se asignan a ninguna de las dos.
    assert inf.motivos[MotivoSinMarcha.ENTRE_MARCHAS] >= 4
    assert sum(m.n_muestras for m in inf.marchas) < inf.n_utiles


def test_un_hueco_de_datos_no_es_una_marcha(umbrales: UmbralesDeMarcha, xp: XpVec) -> None:
    reg = Serie(
        t_ms=Vec([i * 50.0 for i in range(6)]),
        v=Vec([4000.0] * 6),
        clase=Clase.PUNTO,
        valido=Vec([True, True, False, False, True, True]),
    )
    vel = _serie([61.6] * 6)
    inf = detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)
    assert inf.motivos[MotivoSinMarcha.SIN_DATOS] == 2
    assert inf.n_utiles == 4


def test_una_acumulacion_pequena_no_es_una_marcha(umbrales: UmbralesDeMarcha, xp: XpVec) -> None:
    """Menos muestras que el mínimo es un tramo de cambio que se quedó quieto."""
    pocas = umbrales.muestras_minimas_por_marcha - 1
    cocientes = [15.4] * 80 + [9.0] * pocas
    reg = _serie([4000.0] * len(cocientes))
    vel = _serie([c * 4.0 for c in cocientes])
    inf = detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)
    assert [m.indice for m in inf.marchas] == [1]
    assert inf.marchas[0].cociente == pytest.approx(15.4, abs=umbrales.ancho_de_celda)


def test_los_indices_quedan_consecutivos_tras_descartar(
    umbrales: UmbralesDeMarcha, xp: XpVec
) -> None:
    """Si se descarta una acumulación de en medio, los índices se renumeran.

    Un `indice` con un hueco (1, 3) haría que quien pinte el carril de estado
    reserve un carril vacío, y que «la marcha 3» de un log no sea comparable con
    «la marcha 3» de otro.
    """
    pocas = umbrales.muestras_minimas_por_marcha - 1
    cocientes = [4.7] * 60 + [7.8] * pocas + [15.4] * 60
    reg = _serie([4000.0] * len(cocientes))
    vel = _serie([c * 4.0 for c in cocientes])
    inf = detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)
    assert [m.indice for m in inf.marchas] == list(range(1, len(inf.marchas) + 1))
    assert max(inf.indice_por_muestra) == len(inf.marchas)


def test_el_indice_por_muestra_cuadra_con_las_cuentas(
    umbrales: UmbralesDeMarcha, xp: XpVec
) -> None:
    """Las dos salidas del informe tienen que decir lo mismo.

    `indice_por_muestra` es lo que consume el carril de estado y `n_muestras` lo
    que se lee en el resumen; si divergen, uno de los dos miente y no hay forma de
    saber cuál.
    """
    cocientes = [7.8] * 50 + [15.4] * 70
    reg = _serie([4000.0] * len(cocientes))
    vel = _serie([c * 4.0 for c in cocientes])
    inf = detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)
    for m in inf.marchas:
        assert sum(1 for i in inf.indice_por_muestra if i == m.indice) == m.n_muestras


# --------------------------------------------------------------------------- #
# El contrato de entrada
# --------------------------------------------------------------------------- #
def test_una_tasa_no_se_acepta_como_entrada(umbrales: UmbralesDeMarcha, xp: XpVec) -> None:
    """El régimen y la velocidad son PUNTOS; el cociente que sale es una TASA."""
    reg = Serie(t_ms=Vec([0.0, 50.0]), v=Vec([4000.0, 4000.0]), clase=Clase.TASA)
    vel = _serie([61.6, 61.6])
    with pytest.raises(ErrorDeMarcha, match="TASA"):
        detectar_marchas(reg, vel, umbrales=umbrales, xp=xp)


def test_demasiadas_acumulaciones_es_un_error_explicado(
    umbrales: UmbralesDeMarcha, xp: XpVec
) -> None:
    """Antes que devolver veinte marchas inventadas, decir que la configuración no
    vale para este log."""
    apretados = UmbralesDeMarcha.desde_mapa(
        {
            "rpm_minimo": umbrales.rpm_minimo,
            "velocidad_minima_kmh": umbrales.velocidad_minima_kmh,
            "ancho_de_celda": 0.05,
            "muestras_minimas_por_marcha": 1,
            "tolerancia_relativa": 0.001,
            "separacion_minima_relativa": 0.002,
            "marchas_maximas": 3,
            "ventana_validez_ms": umbrales.ventana_validez_ms,
        }
    )
    cocientes = [4.0 + 0.5 * i for i in range(30)]
    reg = _serie([4000.0] * len(cocientes))
    vel = _serie([c * 4.0 for c in cocientes])
    with pytest.raises(ErrorDeMarcha, match="acumulaciones"):
        detectar_marchas(reg, vel, umbrales=apretados, xp=xp)


# --------------------------------------------------------------------------- #
# Los umbrales no viven en el código
# --------------------------------------------------------------------------- #
def test_los_umbrales_no_tienen_valor_por_omision() -> None:
    """Ni uno. Es la regla 3 de `CLAUDE.md` comprobada sobre la firma."""
    for nombre, p in inspect.signature(UmbralesDeMarcha).parameters.items():
        assert p.default is inspect.Parameter.empty, (
            f"{nombre} tiene un valor por omisión en el código; su sitio es data/umbrales.toml"
        )


def test_falta_una_clave_y_no_carga() -> None:
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    completo = {**bruto["marcha"], "ventana_validez_ms": 250.0}
    for clave in completo:
        parcial = {k: v for k, v in completo.items() if k != clave}
        with pytest.raises(ErrorDeMarcha, match=clave):
            UmbralesDeMarcha.desde_mapa(parcial)


def test_el_modulo_no_contiene_los_umbrales_cableados() -> None:
    """Ninguna constante del módulo coincide con un valor de `[marcha]`.

    Una copia del fichero en el código se desincroniza sin que nada se ponga en
    rojo, que es la única forma en que un umbral configurable deja de serlo.
    """
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    prohibidos = {float(v) for v in bruto["marcha"].values() if isinstance(v, (int, float))}
    # 0, 1 y 2 son índices y factores de estructura, no umbrales.
    prohibidos -= {0.0, 1.0, 2.0}
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"), filename=str(MODULO))
    encontrados = sorted(
        {
            float(n.value)
            for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
            if not isinstance(n.value, bool) and float(n.value) in prohibidos
        }
    )
    assert not encontrados, f"umbrales de [marcha] cableados en el módulo: {encontrados}"


def test_bandas_que_se_solaparian_no_se_aceptan() -> None:
    """Con la tolerancia por encima de la separación mínima, una muestra caería en
    dos marchas a la vez. Se rechaza al construir, no al usar."""
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    malo = {**bruto["marcha"], "ventana_validez_ms": 250.0, "tolerancia_relativa": 0.2}
    with pytest.raises(ErrorDeMarcha, match="solapar"):
        UmbralesDeMarcha.desde_mapa(malo)
