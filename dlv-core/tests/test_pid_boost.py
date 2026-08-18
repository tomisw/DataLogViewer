"""Métricas de PID de boost por transitorio (tarea F4-09).

QUÉ PROTEGE ESTA SUITE, ORDENADO POR CONSECUENCIA SI SE ROMPE
=============================================================
1. **Un transitorio se delimita antes de medirse.** Sin escalón del objetivo no
   hay transitorio (informe vacío, `n_escalones_totales == 0`), no un cero
   fabricado. Un escalón descendente se cuenta pero no se mide (D7 pide «tras
   una subida»).
2. **Un transitorio interrumpido, o que no llega a establecerse, se descarta
   ENTERO.** No se informa media medida: la sobreoscilación de un transitorio
   sin establecer no aparece en absoluto, y el motivo queda contado.
3. **El error en régimen se mide solo sobre la cola ya establecida.** Hay una
   prueba que compara ese número con el promedio ingenuo de todo el
   transitorio para que la diferencia sea visible y no una afirmación.
4. **Ni un umbral cableado** (regla 3 de `CLAUDE.md`): firma sin valores por
   omisión, escaneo AST del módulo, y una prueba de mutación que demuestra que
   el escaneo detecta una infracción real.
5. **Contra el AutoLog real**: `Boost Control Target Pressure` es constante en
   las 2 636 filas, así que el resultado correcto sobre el log real es CERO
   transitorios -- y es exactamente eso lo que se comprueba.

Como en `test_marcha.py` y `test_primitivas.py`, todo se ejercita con `XpVec`,
una implementación del protocolo `Vectorial` con biblioteca estándar. Solo
biblioteca estándar en todo el fichero.
"""

from __future__ import annotations

import ast
import bisect
import inspect
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from dlv_core.pid_boost import (
    ErrorDePidBoost,
    InformeTransitoriosBoost,
    MotivoTransitorioDescartado,
    UmbralesPidBoost,
    medir_transitorios_boost,
)
from dlv_core.primitivas import Serie
from dlv_core.unidades import Clase

RAIZ = Path(__file__).resolve().parents[2]
MODULO = RAIZ / "dlv-core" / "src" / "dlv_core" / "pid_boost.py"
UMBRALES_TOML = RAIZ / "data" / "umbrales.toml"
AUTOLOG = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"


# --------------------------------------------------------------------------- #
# El protocolo `Vectorial` con biblioteca estándar (mismo patrón que
# test_primitivas.py: los bucles viven AQUÍ, que es donde ADR-009 los permite)
# --------------------------------------------------------------------------- #
class Vec(list[Any]):
    def __getitem__(self, clave: Any) -> Any:  # type: ignore[override]
        if isinstance(clave, slice):
            return Vec(list.__getitem__(self, clave))
        if isinstance(clave, (Vec, list, tuple)):
            claves = list(clave)
            if claves and isinstance(claves[0], bool):
                return Vec(v for v, m in zip(self, claves, strict=True) if m)
            return Vec(list.__getitem__(self, int(i)) for i in claves)
        return list.__getitem__(self, clave)

    def _op(self, otro: Any, f: Any) -> Vec:
        if isinstance(otro, list):
            return Vec(f(a, b) for a, b in zip(self, otro, strict=True))
        return Vec(f(a, otro) for a in self)

    def __add__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a + b)

    def __radd__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: b + a)

    def __sub__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a - b)

    def __mul__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a * b)

    __rmul__ = __mul__

    def __truediv__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a / b)

    def __lt__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a < b)

    def __le__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a <= b)

    def __gt__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a > b)

    def __ge__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a >= b)

    def __eq__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a == b)

    def __ne__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a != b)

    def __and__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a & b)

    def __or__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a | b)

    def __hash__(self) -> int:  # type: ignore[override]
        raise TypeError("un Vec no es hashable, igual que un ndarray")

    def __bool__(self) -> bool:
        if len(self) == 1:
            return bool(list.__getitem__(self, 0))
        raise ValueError("el valor de verdad de un Vec de longitud != 1 es ambiguo")


class XpVec:
    """Las funciones del protocolo `Vectorial` que este módulo (y `primitivas`,
    al que delega) necesitan, sobre listas."""

    def searchsorted(self, a: Any, v: Any, side: str) -> Any:
        f = bisect.bisect_right if side == "right" else bisect.bisect_left
        lista = list(a)
        return Vec(f(lista, x) for x in v)

    def abs(self, a: Any) -> Any:
        return Vec(abs(x) for x in a) if isinstance(a, list) else abs(a)

    def cumsum(self, a: Any) -> Any:
        total = 0
        salida: Vec = Vec()
        for x in a:
            total += int(x)
            salida.append(total)
        return salida

    def arange(self, n: int) -> Any:
        return Vec(range(n))

    def sum(self, a: Any) -> Any:
        return sum(a)

    def min(self, a: Any) -> Any:
        return min(a)

    def max(self, a: Any) -> Any:
        return max(a)

    def maximum(self, a: Any, b: Any) -> Any:
        return Vec(max(x, y) for x, y in zip(a, b, strict=True))

    def minimum(self, a: Any, b: Any) -> Any:
        return Vec(min(x, y) for x, y in zip(a, b, strict=True))


@pytest.fixture
def xp() -> XpVec:
    return XpVec()


# --------------------------------------------------------------------------- #
# Utilidades de las pruebas
# --------------------------------------------------------------------------- #
def _t(n: int, dt_ms: float = 100.0) -> Vec:
    return Vec([i * dt_ms for i in range(n)])


def _serie(valores: list[float], *, dt_ms: float = 100.0, clase: Clase = Clase.PUNTO) -> Serie:
    return Serie(t_ms=_t(len(valores), dt_ms), v=Vec(valores), clase=clase)


def _umbrales(
    *,
    escalon_minimo_kpa: float = 5.0,
    banda_establecimiento_relativa: float = 0.05,
    histeresis_banda_relativa: float = 0.1,
    permanencia_establecimiento_s: float = 0.0,
    muestras_minimas_establecimiento: int = 1,
    maximo_de_eventos_internos: int = 1000,
    maximo_de_transitorios: int = 100,
) -> UmbralesPidBoost:
    """Umbrales neutros para las pruebas. Los valores por omisión están AQUÍ,
    no en el módulo (mismo criterio que `_permanencia` en `test_primitivas.py`):
    permanencia y muestras mínimas en el mínimo posible para que la prueba
    aísle lo que quiere comprobar, no lo que el filtro deja pasar."""
    return UmbralesPidBoost(
        escalon_minimo_kpa=escalon_minimo_kpa,
        banda_establecimiento_relativa=banda_establecimiento_relativa,
        histeresis_banda_relativa=histeresis_banda_relativa,
        permanencia_establecimiento_s=permanencia_establecimiento_s,
        muestras_minimas_establecimiento=muestras_minimas_establecimiento,
        maximo_de_eventos_internos=maximo_de_eventos_internos,
        maximo_de_transitorios=maximo_de_transitorios,
    )


def _escenario_subida_con_sobreoscilacion() -> tuple[Serie, Serie]:
    """Un escalón de 100 -> 150 kPa en la muestra 5, con un pico de 165 kPa
    (10 % de sobreoscilación) y un asentamiento en 153 kPa (2 % de error en
    régimen) desde la muestra 9 hasta el final (20 muestras, dt = 100 ms).

    Trazado a mano contra `primitivas.banda` en el informe de la tarea: con
    banda 5 % ([142,5, 157,5]) e histéresis 0,1 (margen 1,5), las muestras 0-8
    quedan fuera (110, 100×5, 140, 165, 158 nunca entran o ya salieron) y la
    9-19 (153 constante) se mantienen dentro sin interrupción.
    """
    objetivo = [100.0] * 5 + [150.0] * 15
    actual = [100.0] * 5 + [110.0, 140.0, 165.0, 158.0] + [153.0] * 11
    assert len(objetivo) == len(actual) == 20
    return _serie(actual), _serie(objetivo)


# --------------------------------------------------------------------------- #
# 1. Delimitación: sin escalón no hay transitorio
# --------------------------------------------------------------------------- #
def test_el_objetivo_constante_no_produce_ningun_transitorio(xp: XpVec) -> None:
    """Regla 1 de la tarea: nunca un cero fabricado."""
    actual = _serie([100.0, 101.0, 99.0, 100.5, 100.0])
    objetivo = _serie([150.0] * 5)
    inf = medir_transitorios_boost(actual, objetivo, umbrales=_umbrales(), xp=xp)
    assert inf.transitorios == ()
    assert inf.n_escalones_totales == 0
    assert all(v == 0 for v in inf.descartados.values())


def test_un_escalon_por_debajo_del_minimo_no_cuenta(xp: XpVec) -> None:
    """Ruido de cuantización del canal, no una orden nueva del lazo."""
    objetivo = _serie([100.0] * 5 + [103.0] * 5)  # delta = 3, umbral = 5
    actual = _serie([100.0] * 10)
    inf = medir_transitorios_boost(actual, objetivo, umbrales=_umbrales(), xp=xp)
    assert inf.n_escalones_totales == 0


def test_un_escalon_descendente_se_cuenta_pero_no_se_mide(xp: XpVec) -> None:
    """D7 pide «tras una subida»: una bajada no es su fenómeno."""
    objetivo = _serie([150.0] * 5 + [100.0] * 10)
    actual = _serie([150.0] * 5 + [100.0] * 10)
    inf = medir_transitorios_boost(actual, objetivo, umbrales=_umbrales(), xp=xp)
    assert inf.n_escalones_totales == 1
    assert inf.transitorios == ()
    assert inf.descartados[MotivoTransitorioDescartado.BAJADA] == 1


# --------------------------------------------------------------------------- #
# 2. La medida en sí: sobreoscilación, establecimiento, error en régimen
# --------------------------------------------------------------------------- #
def test_la_sobreoscilacion_y_el_establecimiento_se_miden_bien(xp: XpVec) -> None:
    actual, objetivo = _escenario_subida_con_sobreoscilacion()
    inf = medir_transitorios_boost(actual, objetivo, umbrales=_umbrales(), xp=xp)
    assert inf.n_escalones_totales == 1
    assert len(inf.transitorios) == 1
    t = inf.transitorios[0]

    assert t.objetivo_anterior_kpa == pytest.approx(100.0)
    assert t.objetivo_nuevo_kpa == pytest.approx(150.0)
    assert t.escalon_kpa == pytest.approx(50.0)

    assert t.pico_actual_kpa == pytest.approx(165.0)
    assert t.sobreoscilacion_absoluta_kpa == pytest.approx(15.0)
    assert t.sobreoscilacion_relativa == pytest.approx(0.10)

    # Establecido en la muestra 9 (dt=100ms), escalón en la muestra 5:
    # 4 muestras x 100 ms = 0,4 s.
    assert t.tiempo_establecimiento_s == pytest.approx(0.4)

    assert t.error_regimen_kpa == pytest.approx(3.0)
    assert t.error_regimen_relativo == pytest.approx(0.02)
    assert t.n_muestras_regimen == 11


def test_el_error_en_regimen_no_es_el_promedio_ingenuo_del_transitorio(xp: XpVec) -> None:
    """LA PRUEBA QUE JUSTIFICA LA REGLA 2 DE LA TAREA.

    Promediar `actual - objetivo` sobre TODO el transitorio (incluida la
    subida y la sobreoscilación) da un número muy distinto -- y falso-- del
    error en régimen real. Aquí la diferencia es el número, no una impresión.
    """
    actual, objetivo = _escenario_subida_con_sobreoscilacion()
    inf = medir_transitorios_boost(actual, objetivo, umbrales=_umbrales(), xp=xp)
    t = inf.transitorios[0]

    errores_transitorio_completo = [
        a - o for a, o in zip(actual.v[5:20], objetivo.v[5:20], strict=True)
    ]
    promedio_ingenuo = sum(errores_transitorio_completo) / len(errores_transitorio_completo)

    assert t.error_regimen_kpa == pytest.approx(3.0)
    assert promedio_ingenuo != pytest.approx(t.error_regimen_kpa)
    # El promedio ingenuo sale 0,4 kPa contra los 3,0 reales: casi ocho veces por
    # debajo. En este escenario el error negativo de la subida (-40, -10) y el
    # positivo de la sobreoscilación (+15, +8) se cancelan CASI del todo, que es
    # justo lo que hace peligrosa a la media: no da un número absurdo que salte a
    # la vista, da uno pequeño y creíble. Un lazo con 3 kPa de error en régimen
    # parecería estar en 0,4 y nadie lo tocaría.
    #
    # La aserción NO es sobre el signo del promedio. Una versión anterior de esta
    # prueba exigía `promedio_ingenuo < 0`, y era una afirmación sobre cómo se
    # cancelan estos números concretos, no sobre la trampa: con otra sobreoscila-
    # ción el promedio sale positivo y la trampa sigue siendo la misma.
    assert abs(promedio_ingenuo) < 0.25 * abs(t.error_regimen_kpa), (
        f"promedio ingenuo {promedio_ingenuo:.3f} kPa contra {t.error_regimen_kpa:.3f} "
        "reales: si dejan de diferir en un factor 4, el escenario ya no ilustra nada"
    )


# --------------------------------------------------------------------------- #
# 3. Lo que se descarta, y por qué
# --------------------------------------------------------------------------- #
def test_un_transitorio_interrumpido_por_otro_escalon_se_descarta_entero(xp: XpVec) -> None:
    """El objetivo cambia otra vez (150 -> 200) antes de que el primer
    escalón (100 -> 150) tuviera ninguna oportunidad de establecerse.
    Ni sobreoscilación ni error: la medida entera se descarta."""
    objetivo = [100.0] * 5 + [150.0, 150.0] + [200.0] * 13
    actual = [100.0] * 5 + [110.0, 130.0] + [195.0] * 13
    inf = medir_transitorios_boost(_serie(actual), _serie(objetivo), umbrales=_umbrales(), xp=xp)
    assert inf.n_escalones_totales == 2
    # El primer escalón (100->150) se descarta por interrupción.
    assert inf.descartados[MotivoTransitorioDescartado.INTERRUMPIDO_POR_OTRO_ESCALON] == 1
    # El segundo (150->200) sí llega a establecerse: dura hasta el final.
    assert len(inf.transitorios) == 1
    assert inf.transitorios[0].objetivo_anterior_kpa == pytest.approx(150.0)
    assert inf.transitorios[0].objetivo_nuevo_kpa == pytest.approx(200.0)


def test_un_transitorio_que_no_se_establece_al_final_del_log_se_descarta(xp: XpVec) -> None:
    """El log se acaba mientras el lazo todavía persigue el objetivo: no hay
    establecimiento que afirmar, así que no hay medida."""
    objetivo = [100.0] * 5 + [150.0] * 10
    # Sigue subiendo lentamente sin llegar nunca a entrar en la banda del 5 %
    # (mínimo 142,5): 110, 115, 120, ..., nunca alcanza 142,5.
    actual = [100.0] * 5 + [110.0 + 3.0 * i for i in range(10)]
    inf = medir_transitorios_boost(_serie(actual), _serie(objetivo), umbrales=_umbrales(), xp=xp)
    assert inf.n_escalones_totales == 1
    assert inf.transitorios == ()
    assert inf.descartados[MotivoTransitorioDescartado.SIN_ESTABLECER_AL_FINAL_DEL_SEGMENTO] == 1


def test_la_permanencia_de_establecimiento_descarta_un_asentamiento_demasiado_corto(
    xp: XpVec,
) -> None:
    """Con `muestras_minimas_establecimiento` alto, entrar en banda dos
    muestras antes del final del log no basta para certificar establecimiento."""
    actual, objetivo = _escenario_subida_con_sobreoscilacion()
    umbrales_exigentes = _umbrales(muestras_minimas_establecimiento=50)
    inf = medir_transitorios_boost(actual, objetivo, umbrales=umbrales_exigentes, xp=xp)
    assert inf.transitorios == ()
    assert inf.descartados[MotivoTransitorioDescartado.SIN_ESTABLECER_AL_FINAL_DEL_SEGMENTO] == 1


# --------------------------------------------------------------------------- #
# 4. El contrato de entrada
# --------------------------------------------------------------------------- #
def test_un_actual_que_no_es_punto_se_rechaza(xp: XpVec) -> None:
    actual = _serie([100.0, 110.0], clase=Clase.INTERVALO)
    objetivo = _serie([100.0, 150.0])
    with pytest.raises(ErrorDePidBoost, match="PUNTO"):
        medir_transitorios_boost(actual, objetivo, umbrales=_umbrales(), xp=xp)


def test_un_objetivo_que_no_es_punto_se_rechaza(xp: XpVec) -> None:
    actual = _serie([100.0, 110.0])
    objetivo = _serie([100.0, 150.0], clase=Clase.TASA)
    with pytest.raises(ErrorDePidBoost, match="PUNTO"):
        medir_transitorios_boost(actual, objetivo, umbrales=_umbrales(), xp=xp)


def test_rejillas_distintas_se_rechazan(xp: XpVec) -> None:
    """Las dos formas de no compartir rejilla, que dan mensajes distintos.

    Importa distinguirlas porque la segunda es la traicionera: mismo número de
    muestras, así que cualquier comprobación por longitud la deja pasar y el
    módulo compararía la presión de un instante con el objetivo de otro.
    """
    # Mismo número de muestras, instantes distintos.
    actual = _serie([100.0, 110.0, 120.0], dt_ms=100.0)
    objetivo = _serie([100.0, 150.0, 150.0], dt_ms=50.0)
    with pytest.raises(ErrorDePidBoost, match="instantes distintos"):
        medir_transitorios_boost(actual, objetivo, umbrales=_umbrales(), xp=xp)

    # Y distinto número de muestras.
    corta = _serie([100.0, 150.0], dt_ms=100.0)
    with pytest.raises(ErrorDePidBoost, match="rejillas distintas"):
        medir_transitorios_boost(actual, corta, umbrales=_umbrales(), xp=xp)


def test_un_objetivo_nuevo_nulo_se_rechaza(xp: XpVec) -> None:
    """Escalón ascendente de -10 a 0 kPa (delta=10, sube): no se puede
    expresar la sobreoscilación como fracción de un objetivo nulo."""
    objetivo = _serie([-10.0] * 5 + [0.0] * 10)
    actual = _serie([-10.0] * 5 + [0.0] * 10)
    with pytest.raises(ErrorDePidBoost, match="nul"):
        medir_transitorios_boost(actual, objetivo, umbrales=_umbrales(), xp=xp)


def test_una_serie_vacia_no_produce_transitorios(xp: XpVec) -> None:
    inf = medir_transitorios_boost(_serie([]), _serie([]), umbrales=_umbrales(), xp=xp)
    assert inf == InformeTransitoriosBoost(
        transitorios=(),
        descartados=dict.fromkeys(MotivoTransitorioDescartado, 0),
        n_escalones_totales=0,
    )


def test_demasiados_escalones_es_un_error_explicado(xp: XpVec) -> None:
    """Antes que procesar miles de transitorios que nadie mediría, decir que
    el umbral está mal puesto."""
    objetivo = []
    actual = []
    v = 100.0
    for _ in range(20):
        objetivo += [v, v + 10.0]
        actual += [v, v + 10.0]
        v += 10.0
    umbrales_estrictos = _umbrales(maximo_de_transitorios=3)
    with pytest.raises(ErrorDePidBoost, match="escalones"):
        medir_transitorios_boost(
            _serie(actual), _serie(objetivo), umbrales=umbrales_estrictos, xp=xp
        )


# --------------------------------------------------------------------------- #
# 5. Los umbrales no viven en el código (regla 3 de CLAUDE.md)
# --------------------------------------------------------------------------- #
def test_ningun_parametro_numerico_de_la_api_tiene_valor_por_omision() -> None:
    publicos = [UmbralesPidBoost, medir_transitorios_boost]
    for objeto in publicos:
        for nombre, p in inspect.signature(objeto).parameters.items():
            if p.default is inspect.Parameter.empty:
                continue
            assert not isinstance(p.default, (int, float)) or isinstance(p.default, bool), (
                f"{objeto.__name__ if hasattr(objeto, '__name__') else objeto}.{nombre} tiene "
                f"el valor por omisión numérico {p.default!r}: eso es una copia de un umbral de "
                "data/umbrales.toml que puede desincronizarse en silencio"
            )


def test_falta_una_clave_de_umbral_y_falla_en_vez_de_suponerla() -> None:
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    completo = bruto["boost_pid"]
    for clave in completo:
        parcial = {k: v for k, v in completo.items() if k != clave}
        with pytest.raises(ErrorDePidBoost, match=clave):
            UmbralesPidBoost.desde_mapa(parcial)


def _literales_prohibidos_de(seccion: Mapping[str, object]) -> set[float]:
    return {float(v) for v in seccion.values() if isinstance(v, (int, float))} - {0.0, 1.0, 2.0}


def _cableados_en(texto_modulo: str, prohibidos: set[float]) -> list[float]:
    """La lógica de detección en sí, factorizada para poder probarla con un
    fragmento fabricado (ver la prueba de mutación más abajo) y con el módulo
    real, sin dos implementaciones que puedan divergir."""
    arbol = ast.parse(texto_modulo)
    return sorted(
        {
            float(n.value)
            for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
            if not isinstance(n.value, bool) and float(n.value) in prohibidos
        }
    )


def test_el_modulo_no_contiene_los_umbrales_de_boost_pid_cableados() -> None:
    """Inspección de los literales del módulo, deliberadamente literal (mismo
    patrón que `test_primitivas.py` y `test_marcha.py`): 0, 1 y 2 no cuentan,
    son índices y factores de estructura (mitad de banda, primera muestra),
    no umbrales -- exactamente el mismo criterio que excluye esos tres números
    en `test_marcha.test_el_modulo_no_contiene_los_umbrales_cableados`."""
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    prohibidos = _literales_prohibidos_de(bruto["boost_pid"])
    encontrados = _cableados_en(MODULO.read_text(encoding="utf-8"), prohibidos)
    assert not encontrados, f"umbrales de [boost_pid] cableados en el módulo: {encontrados}"


def test_el_guard_de_cableado_detecta_una_infraccion_real() -> None:
    """PRUEBA DE MUTACIÓN: si el detector de arriba no detectara nada nunca,
    la prueba anterior pasaría siempre y no protegería nada. Se aplica la
    MISMA función de detección a un fragmento fabricado que SÍ copia uno de
    los umbrales reales de `[boost_pid]` (`escalon_minimo_kpa = 5.0`, cableado
    como si fuera un límite del propio módulo) y se comprueba que lo caza.
    """
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    prohibidos = _literales_prohibidos_de(bruto["boost_pid"])
    assert 5.0 in prohibidos, "escalon_minimo_kpa ya no vale 5.0; actualiza esta prueba"

    fragmento_infractor = "LIMITE_DE_RUIDO_KPA = 5.0  # cableado por error\n"
    encontrados = _cableados_en(fragmento_infractor, prohibidos)
    assert encontrados == [5.0], (
        "el detector de cableado no cazó una copia real de escalon_minimo_kpa en un "
        "fragmento fabricado: la prueba de arriba no protegería nada"
    )

    fragmento_limpio = "FACTOR_DE_MEDIO = 0.5  # no es ninguno de los umbrales\n"
    assert _cableados_en(fragmento_limpio, prohibidos) == []


# --------------------------------------------------------------------------- #
# 6. Contra el fichero real de umbrales
# --------------------------------------------------------------------------- #
def test_los_umbrales_reales_cargan_y_son_coherentes() -> None:
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    boost = bruto["boost_pid"]
    umbrales = UmbralesPidBoost.desde_mapa(boost)

    duracion_minima_wot_s = float(bruto["segmentacion"]["duracion_minima_s"]["wot"])
    assert umbrales.permanencia_establecimiento_s < duracion_minima_wot_s, (
        "el establecimiento tiene que poder ocurrir dentro de una tirada WOT mínima, "
        "o ningún transitorio de una tirada corta llegaría nunca a medirse"
    )
    sobreoscilacion_d7 = float(bruto["detectores"]["D7"]["sobreoscilacion_relativa_max"])
    assert umbrales.banda_establecimiento_relativa < sobreoscilacion_d7, (
        "si la banda de establecimiento fuera más ancha que el umbral de D7, un "
        "transitorio podría certificarse establecido ya en sobreoscilación"
    )


def test_las_metricas_sobre_el_autolog_real_no_encuentran_ningun_escalon(xp: XpVec) -> None:
    """El hallazgo central de la tarea sobre el corpus real: `Boost Control
    Target Pressure` es constante en las 2 636 filas del AutoLog, así que el
    resultado honesto es CERO transitorios -- exactamente el caso que la regla
    1 de la tarea pide no confundir con un cero fabricado.

    Lee el CSV con biblioteca estándar, no con el importador (que necesita
    Polars, no instalable aquí -- `docs/09` §9.2): esto es una prueba, no
    `dlv_core`, así que ADR-002 no aplica. `samples/real/` no se modifica, solo
    se lee.
    """
    if not AUTOLOG.exists():
        pytest.skip("samples/real/AutoLog_20260729_1830.csv no está disponible")

    with AUTOLOG.open("r", encoding="utf-8-sig", newline="") as fh:
        texto = fh.read()
    lineas = texto.split("\r\n")

    canales: list[str] = []
    inicio_datos = None
    for i, linea in enumerate(lineas):
        if linea.startswith("Channel : "):
            canales.append(linea[len("Channel : ") :])
        elif re.match(r"^\d{2}:\d{2}:\d{2}\.\d+,", linea):
            inicio_datos = i
            break
    assert inicio_datos is not None

    idx_actual = canales.index("Boost Control Actual Pressure")
    idx_objetivo = canales.index("Boost Control Target Pressure")

    filas = [linea for linea in lineas[inicio_datos:] if linea.strip()]
    actual_v: list[float] = []
    objetivo_v: list[float] = []
    t_ms: list[float] = []
    t0: float | None = None
    for linea in filas:
        campos = linea.split(",")
        hh, mm, resto = campos[0].split(":")
        ss, ms = resto.split(".")
        instante = int(hh) * 3600.0 + int(mm) * 60.0 + int(ss) + int(ms) / 1000.0
        if t0 is None:
            t0 = instante
        t_ms.append((instante - t0) * 1000.0)
        actual_v.append(int(campos[idx_actual + 1]) / 10.0)
        objetivo_v.append(int(campos[idx_objetivo + 1]) / 10.0)

    assert len(t_ms) == 2636
    assert len(set(objetivo_v)) == 1, "el objetivo dejó de ser constante: revisa este hallazgo"

    actual = Serie(t_ms=Vec(t_ms), v=Vec(actual_v), clase=Clase.PUNTO)
    objetivo = Serie(t_ms=Vec(t_ms), v=Vec(objetivo_v), clase=Clase.PUNTO)

    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    umbrales = UmbralesPidBoost.desde_mapa(bruto["boost_pid"])

    inf = medir_transitorios_boost(actual, objetivo, umbrales=umbrales, xp=xp)
    assert inf.n_escalones_totales == 0
    assert inf.transitorios == ()
