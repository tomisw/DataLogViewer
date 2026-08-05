"""Pruebas de las reglas de limpieza sobre el cuerpo parseado (tarea F1-03).

Dos reglas de `docs/01-formato-log.md` §1.13 que `parsear_cuerpo` (F1-02) no
puede aplicar por sí solo: centinelas de desbordamiento (`data/units.toml
[centinelas]`, F0-08) convertidos a nulo, y filas con número de campos
distinto detectadas y reportadas (no solo toleradas en silencio).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, parsear_cuerpo
from dlv_core.formatos.haltech import Descriptor, cargar_descriptor, parsear_cabecera
from dlv_core.formatos.limpieza import detectar_filas_malformadas, nulificar_centinelas
from dlv_core.unidades import Catalogo, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
UNITS_TOML = RAIZ / "data" / "units.toml"
REALES = RAIZ / "samples" / "real"
CORRUPTOS = RAIZ / "samples" / "corrupt"


@pytest.fixture(scope="module")
def desc() -> Descriptor:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return cargar_descriptor(fh)


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with UNITS_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


# --------------------------------------------------------------------------- #
# Centinelas de desbordamiento
# --------------------------------------------------------------------------- #
def test_el_catalogo_trae_los_centinelas_del_autolog(catalogo: Catalogo) -> None:
    # docs/01 §1.13: estos cuatro se observan repetidos en el AutoLog real.
    for centinela in (2147483647, -2147483645, -2147483628, 8388607):
        assert centinela in catalogo.centinelas_i32


def test_nulificar_centinelas_los_convierte_a_nulo_sin_tocar_lo_demas(
    catalogo: Catalogo,
) -> None:
    marca_col = COLUMNA_MARCA
    canal_col = columna_polars(1)
    otro_col = columna_polars(2)
    df = pl.DataFrame(
        {
            marca_col: ["00:00:00.000", "00:00:00.100", "00:00:00.200"],
            canal_col: pl.Series([100, 2147483647, -2147483645], dtype=pl.Int32),
            otro_col: pl.Series([7, 8, 9], dtype=pl.Int32),
        }
    )

    limpio = nulificar_centinelas(df, catalogo)

    assert limpio[canal_col].to_list() == [100, None, None]
    # Una columna sin centinelas no cambia.
    assert limpio[otro_col].to_list() == [7, 8, 9]
    # La marca de tiempo (texto) no se toca.
    assert limpio[marca_col].to_list() == df[marca_col].to_list()


def test_nulificar_centinelas_no_falla_sin_columnas_de_canal(catalogo: Catalogo) -> None:
    df = pl.DataFrame({COLUMNA_MARCA: ["00:00:00.000"]})
    assert nulificar_centinelas(df, catalogo).equals(df)


def test_el_autolog_real_tiene_centinelas_y_quedan_nulos_tras_limpiar(
    desc: Descriptor, catalogo: Catalogo
) -> None:
    """Confirma sobre datos reales, no solo un DataFrame de juguete: el
    hallazgo documentado en docs/01 §1.13 (2147483647 etc. repetidos)."""
    ruta = REALES / "AutoLog_20260729_1830.csv"
    datos = ruta.read_bytes()
    cab = parsear_cabecera(datos, desc)
    crudo = parsear_cuerpo(datos, cab)

    centinelas_antes = 0
    columnas_canal = [c for c in crudo.columns if c != COLUMNA_MARCA]
    for c in columnas_canal:
        centinelas_antes += int(crudo[c].is_in(list(catalogo.centinelas_i32)).sum())
    assert centinelas_antes > 0, "el AutoLog real debería traer al menos un centinela conocido"

    limpio = nulificar_centinelas(crudo, catalogo)
    for c in columnas_canal:
        assert limpio[c].is_in(list(catalogo.centinelas_i32)).sum() == 0


# --------------------------------------------------------------------------- #
# Filas malformadas (docs/01 §1.13, samples/corrupt/README.md casos 02 y 03)
# --------------------------------------------------------------------------- #
def test_fichero_bien_formado_no_produce_avisos(desc: Descriptor) -> None:
    ruta = REALES / "AutoLog_20260729_1830.csv"
    datos = ruta.read_bytes()
    cab = parsear_cabecera(datos, desc)
    assert detectar_filas_malformadas(datos, cab) == []


@pytest.mark.parametrize(
    "nombre",
    ["02-fila-corta.csv", "03-fila-larga.csv"],
)
def test_detecta_exactamente_la_fila_malformada(nombre: str, desc: Descriptor) -> None:
    datos = (CORRUPTOS / nombre).read_bytes()
    cab = parsear_cabecera(datos, desc)

    avisos = detectar_filas_malformadas(datos, cab)

    assert len(avisos) == 1
    assert avisos[0].codigo == "fila_malformada"


def test_muchas_filas_malas_se_resumen_sin_inundar_el_informe(desc: Descriptor) -> None:
    """Construye un cuerpo sintético con 30 filas malformadas para comprobar
    la cota de avisos detallados sin depender de tener un fixture así en el
    repo."""
    cabecera_real = (REALES / "AutoLog_20260729_1830.csv").read_bytes()
    cab = parsear_cabecera(cabecera_real, desc)
    prefijo = cabecera_real[: cab.offset_datos]

    fila_correcta = "00:00:00.000," + ",".join(["1"] * (cab.n_columnas - 1))
    fila_corta = "00:00:00.100," + ",".join(["1"] * (cab.n_columnas - 3))
    cuerpo = "\r\n".join([fila_correcta] + [fila_corta] * 30) + "\r\n"
    datos = prefijo + cuerpo.encode("utf-8")

    avisos = detectar_filas_malformadas(datos, cab)

    assert len(avisos) == 21  # 20 detalladas + 1 resumen
    assert "10 fila" in avisos[-1].mensaje or "más" in avisos[-1].mensaje
