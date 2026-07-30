"""Pruebas de huecos de muestreo y discontinuidades de reloj (tarea F1-08).

QUÉ PROTEGE ESTA SUITE
======================
1. **La trampa del `uint32`** (docs/03, `ChannelSeries.t`): un retroceso leído
   sin castear a un tipo con signo no da un `Δt` negativo, envuelve (wraps) a
   un entero sin signo enorme. Sin el cast a `int64` que hace `huecos.py`, una
   discontinuidad se confundiría con un hueco gigantesco -- exactamente la
   anomalía equivocada. `test_uint32_no_se_confunde_con_hueco_gigante` es la
   prueba que protege justo esto.
2. **El umbral de hueco es relativo al periodo típico del canal, no un valor
   absoluto**: el mismo `Δt` es "normal" en un canal lento y "un hueco" en uno
   rápido. Se comprueba con dos periodos distintos sobre el mismo `Δt`.
3. **La mediana como estimador del periodo típico ignora los propios huecos**
   (y los retrocesos): con una distribución bimodal ráfaga/pausa como la del
   AutoLog real (docs/01 §1.7), la mediana tiene que seguir viendo la ráfaga,
   no la pausa.
4. **Discontinuidades sin umbral de magnitud**: a diferencia de los huecos,
   cualquier retroceso -- por pequeño que sea -- se marca, porque `t` ya llega
   desenrollado de cruces de medianoche (F1-04) antes de este módulo.
5. **Contra datos reales** (`samples/real/`): el AutoLog es exactamente el
   caso "irregular en el tiempo, sin huecos de reloj" que describe docs/01
   §1.7, y los logs internos (`Log2768/2769`) son el caso "tasas fijas, sin
   huecos" de §1.6. Ninguno de los tres tiene retrocesos, así que también
   sirven para comprobar que `detectar_discontinuidades` no da falsos
   positivos sobre datos limpios.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from dlv_core.almacen import ChannelSeries, Storage, construir_desde_polars
from dlv_core.detectores import Incidencia
from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, parsear_cuerpo
from dlv_core.formatos.haltech import Cabecera, Descriptor, cargar_descriptor, parsear_cabecera
from dlv_core.huecos import (
    FACTOR_UMBRAL_HUECO_POR_OMISION,
    Discontinuidad,
    Hueco,
    detectar_discontinuidades,
    detectar_discontinuidades_de_serie,
    detectar_huecos,
    detectar_huecos_de_serie,
    discontinuidades_a_incidencias,
    huecos_a_incidencias,
    periodo_tipico_ms,
)
from dlv_core.roles import ChannelKey
from dlv_core.unidades import Afin

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
REALES = RAIZ / "samples" / "real"


@pytest.fixture(scope="module")
def desc() -> Descriptor:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return cargar_descriptor(fh)


def _serie(t: np.ndarray) -> ChannelSeries:
    """Una `ChannelSeries` mínima para probar las funciones `_de_serie`: solo
    `t` importa aquí, el resto de campos son valores de relleno válidos."""
    return ChannelSeries(
        key=ChannelKey(rol=None, formato=None, id_nativo="1", nombre_normalizado=None),
        role=None,
        t=t,
        v=np.zeros(len(t), dtype=np.int32),
        storage=Storage.INT32_SCALED,
        to_canon=Afin(1.0),
        dimension=None,
    )


# --------------------------------------------------------------------------- #
# periodo_tipico_ms
# --------------------------------------------------------------------------- #
def test_periodo_tipico_es_la_mediana_de_los_delta_positivos() -> None:
    t = np.array([0, 100, 200, 300, 400], dtype=np.uint32)
    assert periodo_tipico_ms(t) == pytest.approx(100.0)


def test_periodo_tipico_ignora_deltas_no_positivos() -> None:
    """Una muestra repetida (Δt = 0) o un retroceso no cuentan como periodo:
    contaminarían la mediana hacia abajo, y no son "otra tasa", son ruido o
    una discontinuidad que se trata aparte."""
    t = np.array([0, 100, 100, 200, 190, 300, 400], dtype=np.uint32)
    # Deltas: 100, 0, 100, -10, 110, 100 -> positivos: 100, 100, 110, 100
    assert periodo_tipico_ms(t) == pytest.approx(100.0)


def test_periodo_tipico_bimodal_sigue_la_rafaga_no_la_pausa() -> None:
    """El caso real del AutoLog (docs/01 §1.7): ráfagas cortas alternadas con
    pausas largas. La mediana tiene que reflejar la ráfaga, que es la mayoría
    de las muestras, no la pausa minoritaria."""
    rafaga = np.arange(0, 4100, 41, dtype=np.int64)  # 100 muestras a 41 ms
    pausas = rafaga[-1] + np.cumsum(np.full(10, 500, dtype=np.int64))  # 10 a 500 ms
    t = np.concatenate([rafaga, pausas]).astype(np.uint32)
    assert periodo_tipico_ms(t) == pytest.approx(41.0)


@pytest.mark.parametrize("t", [np.array([], dtype=np.uint32), np.array([5], dtype=np.uint32)])
def test_periodo_tipico_nan_con_menos_de_dos_muestras(t: np.ndarray) -> None:
    assert math.isnan(periodo_tipico_ms(t))


def test_periodo_tipico_nan_sin_ningun_delta_positivo() -> None:
    """Todo el eje va hacia atrás o se queda quieto: no hay tasa que estimar."""
    t = np.array([100, 100, 50, 0], dtype=np.uint32)
    assert math.isnan(periodo_tipico_ms(t))


# --------------------------------------------------------------------------- #
# detectar_huecos
# --------------------------------------------------------------------------- #
def test_un_delta_de_una_vez_el_periodo_no_es_hueco() -> None:
    t = np.array([0, 100, 200, 300, 400], dtype=np.uint32)
    assert detectar_huecos(t) == []


def test_un_delta_muy_por_encima_del_periodo_es_hueco() -> None:
    t = np.array([0, 100, 200, 2000, 2100], dtype=np.uint32)  # salto de 1800 ms
    huecos = detectar_huecos(t)

    assert huecos == [Hueco(indice=2, t_inicio=200, t_fin=2000, duracion_ms=1800, factor=18.0)]


def test_el_mismo_delta_es_normal_o_hueco_segun_el_periodo_del_canal() -> None:
    """El umbral es relativo, no un valor absoluto de milisegundos: 350 ms es
    un hueco (3,5x) para un canal a 100 ms de periodo, y no lo es (1,75x)
    para uno a 200 ms de periodo habitual."""
    t = np.array([0, 100, 200, 550], dtype=np.uint32)  # último delta: 350 ms

    assert detectar_huecos(t, periodo_ms=100.0) != []
    assert detectar_huecos(t, periodo_ms=100.0)[0].factor == pytest.approx(3.5)
    assert detectar_huecos(t, periodo_ms=200.0) == []  # 350 / 200 = 1,75 < 3


def test_factor_umbral_es_configurable() -> None:
    t = np.array([0, 100, 100 + 350], dtype=np.uint32)
    assert detectar_huecos(t, periodo_ms=100.0, factor_umbral=3.0) != []
    assert detectar_huecos(t, periodo_ms=100.0, factor_umbral=2.0) != []
    assert detectar_huecos(t, periodo_ms=100.0, factor_umbral=10.0) == []


def test_varios_huecos_se_detectan_todos_con_sus_indices_correctos() -> None:
    t = np.array([0, 100, 200, 2000, 2100, 2200, 9000], dtype=np.uint32)
    huecos = detectar_huecos(t, periodo_ms=100.0)

    assert [h.indice for h in huecos] == [2, 5]
    assert [h.t_inicio for h in huecos] == [200, 2200]
    assert [h.t_fin for h in huecos] == [2000, 9000]


def test_sin_periodo_utilizable_no_hay_huecos_que_afirmar() -> None:
    """Sin una tasa habitual que sirva de referencia (aquí: todo el eje se
    queda plano o retrocede) no se puede decir qué es "anormal": se prefiere
    no afirmar nada a arriesgar un falso positivo con un periodo inventado.
    """
    t = np.array([100, 100, 50, 0], dtype=np.uint32)
    assert detectar_huecos(t) == []


@pytest.mark.parametrize("t", [np.array([], dtype=np.uint32), np.array([5], dtype=np.uint32)])
def test_detectar_huecos_no_revienta_con_menos_de_dos_muestras(t: np.ndarray) -> None:
    assert detectar_huecos(t) == []


# --------------------------------------------------------------------------- #
# detectar_discontinuidades
# --------------------------------------------------------------------------- #
def test_eje_monotono_no_tiene_discontinuidades() -> None:
    t = np.array([0, 100, 200, 300], dtype=np.uint32)
    assert detectar_discontinuidades(t) == []


def test_un_retroceso_pequeno_se_marca_igual_que_uno_grande() -> None:
    """A diferencia de `detectar_huecos`, aquí no hay umbral de magnitud: el
    eje ya llega desenrollado de cruces de medianoche (F1-04), así que
    cualquier retroceso restante es, por definición, anómalo."""
    t = np.array([0, 100, 95, 200], dtype=np.uint32)  # retroceso de solo 5 ms
    discontinuidades = detectar_discontinuidades(t)

    assert discontinuidades == [Discontinuidad(indice=1, t_antes=100, t_despues=95, delta_ms=-5)]


def test_varias_discontinuidades_se_detectan_todas() -> None:
    t = np.array([0, 100, 50, 150, 120, 300], dtype=np.uint32)
    discontinuidades = detectar_discontinuidades(t)

    assert [d.indice for d in discontinuidades] == [1, 3]
    assert [d.delta_ms for d in discontinuidades] == [-50, -30]


def test_uint32_no_se_confunde_con_hueco_gigante() -> None:
    """La trampa central de esta suite: `t` es `uint32` (F1-05). `100 - 200`
    sin signo no da `-100`, envuelve a `4294967196`. Si `huecos.py` no
    casteara a `int64` antes de restar, este retroceso de 100 ms se leería
    como un hueco de ~4 294 967 196 ms en vez de una discontinuidad de -100 ms,
    y además se colaría en la mediana del periodo típico, disparándolo por
    las nubes.
    """
    t = np.array([0, 100, 200, 100, 200, 300, 400], dtype=np.uint32)
    assert t.dtype == np.uint32

    discontinuidades = detectar_discontinuidades(t)
    assert discontinuidades == [Discontinuidad(indice=2, t_antes=200, t_despues=100, delta_ms=-100)]

    # Y el retroceso no debe filtrarse a la estimación de periodo ni disparar
    # un "hueco" fantasma del tamaño del envolvimiento sin signo.
    assert periodo_tipico_ms(t) == pytest.approx(100.0)
    assert detectar_huecos(t) == []


# --------------------------------------------------------------------------- #
# Azúcar sobre ChannelSeries
# --------------------------------------------------------------------------- #
def test_detectar_huecos_de_serie_delega_en_t() -> None:
    serie = _serie(np.array([0, 100, 200, 2000, 2100], dtype=np.uint32))
    esperado = detectar_huecos(serie.t, periodo_ms=100.0)
    assert detectar_huecos_de_serie(serie, periodo_ms=100.0) == esperado


def test_detectar_discontinuidades_de_serie_delega_en_t() -> None:
    serie = _serie(np.array([0, 100, 95, 200], dtype=np.uint32))
    assert detectar_discontinuidades_de_serie(serie) == detectar_discontinuidades(serie.t)


# --------------------------------------------------------------------------- #
# Adaptadores a Incidencia (formato compartido de detectores, §4.3)
# --------------------------------------------------------------------------- #
def test_huecos_a_incidencias_conserva_el_intervalo_y_el_detalle() -> None:
    huecos = [Hueco(indice=2, t_inicio=200, t_fin=2000, duracion_ms=1800, factor=18.0)]
    (incidencia,) = huecos_a_incidencias(huecos)

    assert isinstance(incidencia, Incidencia)
    assert incidencia.detector_id == "D18"
    assert incidencia.severidad == "informativa"
    assert incidencia.t_inicio == 200
    assert incidencia.t_fin == 2000
    assert incidencia.detalle == {"duracion_ms": 1800.0, "factor": 18.0}


def test_huecos_a_incidencias_admite_detector_id_y_severidad_propios() -> None:
    huecos = [Hueco(indice=0, t_inicio=0, t_fin=1000, duracion_ms=1000, factor=10.0)]
    (incidencia,) = huecos_a_incidencias(huecos, detector_id="mi_perfil", severidad="alta")

    assert incidencia.detector_id == "mi_perfil"
    assert incidencia.severidad == "alta"


def test_discontinuidades_a_incidencias_conserva_el_signo_del_retroceso() -> None:
    discontinuidades = [Discontinuidad(indice=1, t_antes=100, t_despues=95, delta_ms=-5)]
    (incidencia,) = discontinuidades_a_incidencias(discontinuidades)

    assert incidencia.detector_id == "discontinuidad_reloj"
    assert incidencia.t_inicio == 100
    assert incidencia.t_fin == 95  # t_fin < t_inicio: el propio dato delata el retroceso
    assert incidencia.detalle == {"delta_ms": -5.0}


# --------------------------------------------------------------------------- #
# Contra logs reales (samples/real/)
# --------------------------------------------------------------------------- #
def _construir_series(desc: Descriptor, ruta: Path) -> list[ChannelSeries]:
    datos = ruta.read_bytes()
    cab: Cabecera = parsear_cabecera(datos, desc)
    df = parsear_cuerpo(datos, cab)
    storage = {columna_polars(c.columna): Storage.INT32_SCALED for c in cab.canales}
    return construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )


def test_autolog_real_no_tiene_discontinuidades(desc: Descriptor) -> None:
    """docs/01 §1.4/§1.13: el AutoLog real no tiene marcas no monótonas."""
    series = _construir_series(desc, REALES / "AutoLog_20260729_1830.csv")
    grupos_t = {id(s.t): s.t for s in series}

    for t in grupos_t.values():
        assert detectar_discontinuidades(t) == []


def test_autolog_real_el_periodo_tipico_coincide_con_el_dt_mediano_documentado(
    desc: Descriptor,
) -> None:
    """docs/01 §1.7: "dt mediano (p50) 54 ms". Es el único grupo de muestreo
    del AutoLog (casi todos los canales comparten tasa, ver `test_almacen.py`).
    """
    series = _construir_series(desc, REALES / "AutoLog_20260729_1830.csv")
    (t,) = {id(s.t): s.t for s in series}.values()

    assert periodo_tipico_ms(t) == pytest.approx(54.0)


def test_autolog_real_tiene_huecos_por_encima_del_umbral_por_omision(desc: Descriptor) -> None:
    """docs/01 §1.7: "irregular en el tiempo... no se debe asumir muestreo
    uniforme", con dt máximo de 499 ms frente a una mediana de 54 ms (~9,2x).
    Con el umbral por omisión (3x) tiene que haber huecos que "rompan la
    línea en el gráfico", y ninguno puede tener un factor menor que 3.
    """
    series = _construir_series(desc, REALES / "AutoLog_20260729_1830.csv")
    (t,) = {id(s.t): s.t for s in series}.values()

    huecos = detectar_huecos(t, factor_umbral=FACTOR_UMBRAL_HUECO_POR_OMISION)

    assert len(huecos) > 0
    assert all(h.factor >= FACTOR_UMBRAL_HUECO_POR_OMISION for h in huecos)
    assert max(h.duracion_ms for h in huecos) == 499  # dt máximo documentado en §1.7


@pytest.mark.parametrize("nombre", ["20260729_1859_Log2768.csv", "20260729_1859_Log2769.csv"])
def test_logs_internos_a_tasa_fija_no_tienen_huecos_ni_discontinuidades(
    desc: Descriptor, nombre: str
) -> None:
    """docs/01 §1.6: tres grupos a tasa fija (20/10/5 Hz nominales), sin
    huecos de reloj ni retrocesos: el jitter de +-5 ms de cada grupo (ver
    §1.6, "dt mediano 53/102/202 ms") no llega ni de lejos a 3x su periodo.
    """
    series = _construir_series(desc, REALES / nombre)
    grupos_t = {id(s.t): s.t for s in series}
    assert len(grupos_t) == 3  # G0/G1/G2 de §1.6

    for t in grupos_t.values():
        assert detectar_huecos(t) == []
        assert detectar_discontinuidades(t) == []
