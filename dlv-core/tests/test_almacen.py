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

from dlv_core.almacen import Storage, construir_desde_polars
from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, parsear_cuerpo
from dlv_core.formatos.haltech import (
    Cabecera,
    Canal,
    Descriptor,
    cargar_descriptor,
    parsear_cabecera,
)

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
REALES = RAIZ / "samples" / "real"


@pytest.fixture(scope="module")
def desc() -> Descriptor:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return cargar_descriptor(fh)


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
