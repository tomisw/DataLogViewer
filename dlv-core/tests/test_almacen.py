"""Pruebas del almacén columnar (tarea F1-05, ADR-003).

Cubre lo que dice el docstring de `ChannelSeries.t`: se comparte por
referencia entre canales del **mismo** grupo de muestreo, y grupos distintos
(misma cantidad de muestras, filas distintas) no se confunden. También la
conversión de la marca de tiempo (texto) a `t` relativo a t0, y que
`storage`/`to_canon`/`dimension` vienen de `Canal`, no se inventan.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from dlv_core.almacen import ChannelSeries, IndiceCanal, Storage, construir_desde_polars, indexar
from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, parsear_cuerpo
from dlv_core.formatos.haltech import (
    Cabecera,
    Canal,
    Descriptor,
    cargar_descriptor,
    parsear_cabecera,
)
from dlv_core.formatos.limpieza import nulificar_centinelas
from dlv_core.roles import ChannelKey
from dlv_core.unidades import Afin, Catalogo, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
UNITS_TOML = RAIZ / "data" / "units.toml"
REALES = RAIZ / "samples" / "real"


@pytest.fixture(scope="module")
def desc() -> Descriptor:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return cargar_descriptor(fh)


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with UNITS_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


def _canal(
    orden: int, id_: int, *, dimension: str | None = "angular_speed", a: float = 1.0
) -> Canal:
    return Canal(
        orden=orden,
        nombre=f"Canal {id_}",
        id=id_,
        tipo="EngineSpeed",
        display_max=None,
        display_min=None,
        dimension=dimension,
        a_canonica=a,
        confianza="confirmed",
    )


def _cabecera(canales: tuple[Canal, ...]) -> Cabecera:
    return Cabecera(
        formato="haltech_nsp",
        version="1.1",
        metadatos={},
        canales=canales,
        offset_datos=0,
        avisos=[],
    )


# --------------------------------------------------------------------------- #
# Grupos de muestreo: el caso que importa
# --------------------------------------------------------------------------- #
def test_dos_canales_con_el_mismo_patron_de_nulos_comparten_t_por_referencia() -> None:
    canales = (_canal(0, 100), _canal(1, 101))
    cab = _cabecera(canales)
    df = pl.DataFrame(
        {
            COLUMNA_MARCA: ["00:00:00.000", "00:00:00.100", "00:00:00.200"],
            columna_polars(1): pl.Series([10, 20, 30], dtype=pl.Int32),
            columna_polars(2): pl.Series([1, 2, 3], dtype=pl.Int32),
        }
    )
    storage = {columna_polars(1): Storage.INT32_SCALED, columna_polars(2): Storage.INT32_SCALED}

    series = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )

    assert len(series) == 2
    assert series[0].t is series[1].t, "mismo grupo de muestreo: t debe ser el mismo objeto"
    assert series[0].t.tolist() == [0, 100, 200]
    assert series[0].v.tolist() == [10, 20, 30]
    assert series[1].v.tolist() == [1, 2, 3]


def test_patrones_de_nulos_distintos_van_a_grupos_distintos() -> None:
    canales = (_canal(0, 100), _canal(1, 101))
    cab = _cabecera(canales)
    df = pl.DataFrame(
        {
            COLUMNA_MARCA: ["00:00:00.000", "00:00:00.100", "00:00:00.200"],
            columna_polars(1): pl.Series([10, None, 30], dtype=pl.Int32),
            columna_polars(2): pl.Series([1, 2, None], dtype=pl.Int32),
        }
    )
    storage = {columna_polars(1): Storage.INT32_SCALED, columna_polars(2): Storage.INT32_SCALED}

    series = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )

    por_id = {s.key.id_nativo: s for s in series}
    assert por_id["100"].t.tolist() == [0, 200]  # filas 0 y 2 (la 1 es nula)
    assert por_id["100"].v.tolist() == [10, 30]
    assert por_id["101"].t.tolist() == [0, 100]  # filas 0 y 1 (la 2 es nula)
    assert por_id["101"].v.tolist() == [1, 2]
    assert por_id["100"].t is not por_id["101"].t


def test_mismo_numero_de_muestras_pero_filas_distintas_no_se_confunden() -> None:
    """Dos canales con 2 muestras de 3 cada uno, pero en filas distintas: no
    deben terminar en el mismo grupo solo por tener el mismo recuento."""
    canales = (_canal(0, 100), _canal(1, 101))
    cab = _cabecera(canales)
    df = pl.DataFrame(
        {
            COLUMNA_MARCA: ["00:00:00.000", "00:00:00.100", "00:00:00.200"],
            columna_polars(1): pl.Series([10, 20, None], dtype=pl.Int32),
            columna_polars(2): pl.Series([1, None, 3], dtype=pl.Int32),
        }
    )
    storage = {columna_polars(1): Storage.INT32_SCALED, columna_polars(2): Storage.INT32_SCALED}

    series = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )

    assert series[0].t is not series[1].t
    assert series[0].t.tolist() == [0, 100]
    assert series[1].t.tolist() == [0, 200]


# --------------------------------------------------------------------------- #
# Identidad, storage, conversión y dimensión vienen de Canal
# --------------------------------------------------------------------------- #
def test_key_storage_to_canon_y_dimension_vienen_del_canal() -> None:
    canal = _canal(0, 8953, dimension="pressure", a=0.1)
    cab = _cabecera((canal,))
    df = pl.DataFrame(
        {
            COLUMNA_MARCA: ["00:00:00.000"],
            columna_polars(1): pl.Series([500], dtype=pl.Int32),
        }
    )
    storage = {columna_polars(1): Storage.INT32_SCALED}

    (serie,) = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )

    assert serie.key.id_nativo == "8953"
    assert serie.key.formato == "haltech_nsp"
    assert serie.key.rol is None
    assert serie.storage is Storage.INT32_SCALED
    assert serie.to_canon.a == pytest.approx(0.1)
    assert serie.dimension == "pressure"


def test_canal_en_crudo_sin_dimension_queda_sin_unidad() -> None:
    canal = _canal(0, 1, dimension=None)
    cab = _cabecera((canal,))
    df = pl.DataFrame(
        {COLUMNA_MARCA: ["00:00:00.000"], columna_polars(1): pl.Series([1], dtype=pl.Int32)}
    )
    storage = {columna_polars(1): Storage.INT32_SCALED}

    (serie,) = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )

    assert serie.dimension is None


# --------------------------------------------------------------------------- #
# Contra un log real
# --------------------------------------------------------------------------- #
def test_construye_todas_las_series_del_autolog_real(desc: Descriptor) -> None:
    ruta = REALES / "AutoLog_20260729_1830.csv"
    datos = ruta.read_bytes()
    cab = parsear_cabecera(datos, desc)
    df = parsear_cuerpo(datos, cab)
    storage = {columna_polars(c.columna): Storage.INT32_SCALED for c in cab.canales}

    series = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )

    assert len(series) == cab.n_canales
    for s in series:
        assert s.t.dtype == np.uint32
        assert len(s.t) == len(s.v)
        assert s.t[0] == 0
        # t es relativo a t0 y no decrece salvo un retroceso anómalo puntual
        # (no corregido por diseño, docs/03); en el AutoLog real no los hay.
        assert (np.diff(s.t.astype(np.int64)) >= 0).all()


def test_grupos_de_muestreo_reales_comparten_t_por_referencia(desc: Descriptor) -> None:
    """En el AutoLog real casi todos los canales están a la misma tasa: deben
    terminar todos en un único grupo, compartiendo un único array `t`."""
    ruta = REALES / "AutoLog_20260729_1830.csv"
    datos = ruta.read_bytes()
    cab = parsear_cabecera(datos, desc)
    df = parsear_cuerpo(datos, cab)
    storage = {columna_polars(c.columna): Storage.INT32_SCALED for c in cab.canales}

    series = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )

    arrays_t_unicos = {id(s.t) for s in series}
    assert len(arrays_t_unicos) == 1


# --------------------------------------------------------------------------- #
# Indexado (F1-07): mín/máx/percentiles y clasificación
# --------------------------------------------------------------------------- #
def _serie(valores: list[int]) -> ChannelSeries:
    """`ChannelSeries` mínima para probar `indexar`: solo `v` importa aquí,
    así que `t` se rellena con un contador simple del mismo tamaño."""
    v = np.array(valores, dtype=np.int32)
    t = np.arange(len(valores), dtype=np.uint32)
    return ChannelSeries(
        key=ChannelKey(rol=None, formato="test", id_nativo="1", nombre_normalizado=None),
        role=None,
        t=t,
        v=v,
        storage=Storage.INT32_SCALED,
        to_canon=Afin(1.0),
        dimension=None,
    )


def test_indexar_serie_vacia_es_vacio_y_nada_mas() -> None:
    serie = _serie([])

    indice = indexar(serie)

    assert indice.vacio is True
    assert indice.constante is False
    assert indice.fuera_de_rango is False
    assert indice.activo is False
    assert indice.minimo is None
    assert indice.maximo is None
    assert indice.percentiles == {}


def test_indexar_serie_constante_no_esta_vacia_ni_activa() -> None:
    serie = _serie([42, 42, 42, 42])

    indice = indexar(serie)

    assert indice.constante is True
    assert indice.vacio is False
    assert indice.fuera_de_rango is False
    assert indice.activo is False
    assert indice.minimo == 42.0
    assert indice.maximo == 42.0
    # Todos los percentiles de una constante son la propia constante.
    assert all(x == 42.0 for x in indice.percentiles.values())


def test_indexar_serie_variable_dentro_de_rango_es_activa() -> None:
    serie = _serie(list(range(0, 100)))

    indice = indexar(serie, display_min=0.0, display_max=200.0)

    assert indice.activo is True
    assert indice.vacio is False
    assert indice.constante is False
    assert indice.fuera_de_rango is False


def test_indexar_detecta_fuera_de_rango_por_encima_del_maximo() -> None:
    serie = _serie([0, 50, 99, 9999])  # 9999 excede el display_max

    indice = indexar(serie, display_min=0.0, display_max=100.0)

    assert indice.fuera_de_rango is True
    assert indice.activo is False


def test_indexar_detecta_fuera_de_rango_por_debajo_del_minimo() -> None:
    serie = _serie([-500, 0, 50, 99])  # -500 está por debajo del display_min

    indice = indexar(serie, display_min=0.0, display_max=100.0)

    assert indice.fuera_de_rango is True


def test_indexar_constante_y_fuera_de_rango_a_la_vez_no_son_excluyentes() -> None:
    """Un canal atascado en un valor que además incumple su rango de display:
    ambas categorías deben poder ser verdaderas simultáneamente (docstring de
    `IndiceCanal`)."""
    serie = _serie([5000, 5000, 5000])

    indice = indexar(serie, display_min=0.0, display_max=100.0)

    assert indice.constante is True
    assert indice.fuera_de_rango is True
    assert indice.activo is False


def test_indexar_sin_limites_declarados_nunca_marca_fuera_de_rango() -> None:
    """13 de los 475 canales del AutoLog real no traen `DisplayMaxMin`
    (docs/01 §1.3): sin límite que comprobar, `fuera_de_rango` es `False`, no
    "desconocido", por muy extremos que sean los valores."""
    serie = _serie([-2_000_000_000, 0, 2_000_000_000])

    indice = indexar(serie)  # display_min/display_max por omisión: None

    assert indice.fuera_de_rango is False


def test_indexar_percentiles_por_omision_coinciden_con_numpy() -> None:
    valores = list(range(0, 1000))
    serie = _serie(valores)

    indice = indexar(serie)

    esperados = np.percentile(np.array(valores, dtype=np.int32), [1.0, 5.0, 50.0, 95.0, 99.0])
    obtenidos = [indice.percentiles[p] for p in (1.0, 5.0, 50.0, 95.0, 99.0)]
    assert obtenidos == pytest.approx(esperados.tolist())


def test_indexar_admite_percentiles_personalizados() -> None:
    serie = _serie(list(range(0, 100)))

    indice = indexar(serie, percentiles=(10.0, 90.0))

    assert set(indice.percentiles) == {10.0, 90.0}


# --------------------------------------------------------------------------- #
# Contra un log real, con la limpieza de centinelas de por medio (F1-03/F1-05)
# --------------------------------------------------------------------------- #
def test_indexar_sobre_canal_real_con_rango_declarado(desc: Descriptor, catalogo: Catalogo) -> None:
    """RPM (ID 384) trae `DisplayMaxMin 20000,0` en el AutoLog real: un motor
    de combustión no debería reportar RPM fuera de ese rango, así que se
    espera un canal activo, no vacío ni constante."""
    ruta = REALES / "AutoLog_20260729_1830.csv"
    datos = ruta.read_bytes()
    cab = parsear_cabecera(datos, desc)
    crudo = parsear_cuerpo(datos, cab)
    df = nulificar_centinelas(crudo, catalogo)
    storage = {columna_polars(c.columna): Storage.INT32_SCALED for c in cab.canales}

    series = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )

    canal_rpm = cab.por_id(384)
    assert canal_rpm is not None
    serie_rpm = next(s for s in series if s.key.id_nativo == "384")

    indice = indexar(
        serie_rpm,
        display_min=canal_rpm.display_min,
        display_max=canal_rpm.display_max,
    )

    assert indice.vacio is False
    assert indice.activo is True
    assert indice.fuera_de_rango is False


def test_indexar_sobre_canal_real_sin_display_max_min(desc: Descriptor, catalogo: Catalogo) -> None:
    """'Bootmode Reason' (ID 14210) es uno de los 13 canales del AutoLog real
    sin `DisplayMaxMin` (docs/01 §1.3): `Canal.display_min`/`display_max` son
    `None`, y por tanto `fuera_de_rango` no puede ser otra cosa que `False`."""
    ruta = REALES / "AutoLog_20260729_1830.csv"
    datos = ruta.read_bytes()
    cab = parsear_cabecera(datos, desc)
    crudo = parsear_cuerpo(datos, cab)
    df = nulificar_centinelas(crudo, catalogo)
    storage = {columna_polars(c.columna): Storage.INT32_SCALED for c in cab.canales}

    series = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )

    canal = cab.por_id(14210)
    assert canal is not None
    assert canal.display_min is None
    assert canal.display_max is None
    serie = next(s for s in series if s.key.id_nativo == "14210")

    indice = indexar(serie, display_min=canal.display_min, display_max=canal.display_max)

    assert indice.fuera_de_rango is False


def test_indexar_todos_los_canales_reales_no_lanza_y_clasifica(
    desc: Descriptor, catalogo: Catalogo
) -> None:
    """Barrido de humo sobre los 475 canales reales: `indexar` no debe lanzar
    para ningún canal, incluidos los que resulten vacíos tras nulificar
    centinelas (p. ej. un canal que solo reportó valores centinela)."""
    ruta = REALES / "AutoLog_20260729_1830.csv"
    datos = ruta.read_bytes()
    cab = parsear_cabecera(datos, desc)
    crudo = parsear_cuerpo(datos, cab)
    df = nulificar_centinelas(crudo, catalogo)
    storage = {columna_polars(c.columna): Storage.INT32_SCALED for c in cab.canales}

    series = construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )
    canales_por_id = {c.id: c for c in cab.canales}

    for serie in series:
        assert serie.key.id_nativo is not None
        canal = canales_por_id[int(serie.key.id_nativo)]
        indice = indexar(serie, display_min=canal.display_min, display_max=canal.display_max)
        assert isinstance(indice, IndiceCanal)
        # Exactamente una lectura coherente: vacío excluye a las demás.
        if indice.vacio:
            assert indice.minimo is None and indice.maximo is None
