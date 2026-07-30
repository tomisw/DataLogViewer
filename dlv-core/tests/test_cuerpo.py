"""Pruebas del parseo del cuerpo con Polars (tarea F1-02).

Cubre el presupuesto de memoria (F0-01: proyectar a `Int32` en vez de dejar
que Polars infiera `Int64`), el mapeo de columnas Polars <-> `Canal.columna`,
las celdas vacías como nulos (no como 0) y los dos casos del corpus de
corruptos que le tocan a este módulo (docs/01, `samples/corrupt/README.md`,
casos 02 y 03: fila corta / fila larga, "cargar con aviso, resto válido").
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, esquema, parsear_cuerpo
from dlv_core.formatos.haltech import Cabecera, Descriptor, cargar_descriptor, parsear_cabecera

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
REALES = RAIZ / "samples" / "real"
CORRUPTOS = RAIZ / "samples" / "corrupt"

LOGS_REALES = (
    REALES / "AutoLog_20260729_1830.csv",
    REALES / "20260729_1859_Log2768.csv",
    REALES / "20260729_1859_Log2769.csv",
)


@pytest.fixture(scope="module")
def desc() -> Descriptor:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return cargar_descriptor(fh)


def cabecera_de(ruta: Path, desc: Descriptor) -> tuple[bytes, Cabecera]:
    datos = ruta.read_bytes()
    return datos, parsear_cabecera(datos, desc)


# --------------------------------------------------------------------------- #
# Mapeo de columnas
# --------------------------------------------------------------------------- #
def test_columna_polars_es_1_based() -> None:
    assert columna_polars(0) == "column_1"
    assert columna_polars(1) == "column_2"
    assert COLUMNA_MARCA == "column_1"


def test_esquema_cubre_marca_y_todos_los_canales(desc: Descriptor) -> None:
    _, cab = cabecera_de(LOGS_REALES[0], desc)
    ov = esquema(cab)

    assert ov[COLUMNA_MARCA] == pl.Utf8
    assert len(ov) == cab.n_columnas
    for canal in cab.canales:
        assert ov[columna_polars(canal.columna)] == pl.Int32


# --------------------------------------------------------------------------- #
# Los tres logs reales
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ruta", LOGS_REALES, ids=lambda p: p.name)
def test_parsea_los_logs_reales_sin_excepcion(ruta: Path, desc: Descriptor) -> None:
    datos, cab = cabecera_de(ruta, desc)
    df = parsear_cuerpo(datos, cab)

    assert df.width == cab.n_columnas
    assert df.height > 0
    assert df.schema[COLUMNA_MARCA] == pl.Utf8
    for canal in cab.canales:
        assert df.schema[columna_polars(canal.columna)] == pl.Int32


def test_la_marca_de_tiempo_tiene_la_forma_esperada(desc: Descriptor) -> None:
    datos, cab = cabecera_de(LOGS_REALES[0], desc)
    df = parsear_cuerpo(datos, cab)

    primera = df[COLUMNA_MARCA][0]
    assert primera is not None
    assert primera.count(":") == 2
    assert "." in primera


def test_las_celdas_vacias_son_nulas_no_cero(desc: Descriptor) -> None:
    """Los logs internos (a diferencia del AutoLog) son multi-tasa: la mayoría
    de canales tienen huecos en la mayoría de filas. Un hueco leído como 0
    sería un valor inventado (docs/01: "hueco != 0")."""
    datos, cab = cabecera_de(REALES / "20260729_1859_Log2768.csv", desc)
    df = parsear_cuerpo(datos, cab)

    nulos_totales = df.null_count().sum_horizontal().item()
    assert nulos_totales > 0


# --------------------------------------------------------------------------- #
# Corpus de corruptos: casos 02 y 03 (docs/01, samples/corrupt/README.md)
# --------------------------------------------------------------------------- #
def test_fila_corta_se_rellena_con_nulos_y_no_revienta(desc: Descriptor) -> None:
    datos, cab = cabecera_de(CORRUPTOS / "02-fila-corta.csv", desc)
    df = parsear_cuerpo(datos, cab)

    assert df.width == cab.n_columnas
    # La especificación dice "solo 5 en lugar de 26": la fila truncada debe
    # quedar con el resto de columnas a null, no desplazar ni corromper filas
    # vecinas.
    nulos_por_fila = df.select(pl.sum_horizontal(pl.all().is_null()).alias("n")).to_series()
    assert nulos_por_fila.max() >= cab.n_columnas - 5


def test_fila_larga_ignora_los_campos_extra_y_no_revienta(desc: Descriptor) -> None:
    datos, cab = cabecera_de(CORRUPTOS / "03-fila-larga.csv", desc)
    df = parsear_cuerpo(datos, cab)

    assert df.width == cab.n_columnas
    assert df.height > 0
