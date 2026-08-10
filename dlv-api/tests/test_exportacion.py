"""Exportación con unidad declarada por columna (tarea F4-12, E8.2).

QUÉ SE PRUEBA SIN POLARS, Y POR QUÉ ES LA MAYORÍA DE ESTE FICHERO
==================================================================
`dlv_api.exportacion.preparar_columna` no importa Polars (solo lo hacen
`exportar_csv`/`exportar_parquet`, y dentro de la propia función: ver la
cabecera de `exportacion.py`). Eso significa que la parte que decide QUÉ
unidad y QUÉ clase le toca a cada columna —que es la parte que de verdad
revisa esta tarea— se puede probar con `float` normales y sin ninguna
dependencia externa, en cualquier entorno, incluido uno sin Polars/NumPy
instalados (que es el de quien ejecutó esta tarea: ver su informe).

Solo los dos tests marcados con `pytest.importorskip("polars")` necesitan la
dependencia de verdad, porque comprueban el fichero de bytes que produce
Polars, no la decisión de unidad.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dlv_api.exportacion import (
    MEDIA_TYPE_CSV,
    MEDIA_TYPE_PARQUET,
    ColumnaAExportar,
    ErrorDeExportacion,
    exportar_csv,
    exportar_parquet,
    preparar_columna,
)
from dlv_core.unidades import Afin, Catalogo, Clase, ErrorDeUnidad, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
UNITS_TOML = RAIZ / "data" / "units.toml"


@pytest.fixture(scope="module")
def cat() -> Catalogo:
    with UNITS_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


def test_tipos_mime_declarados() -> None:
    """No es solo cosmético: `dlv_api.main` los usa para que el navegador
    trate la respuesta como descarga y no como texto plano."""
    assert MEDIA_TYPE_CSV == "text/csv"
    assert "parquet" in MEDIA_TYPE_PARQUET


# --------------------------------------------------------------------------- #
# Los tres motivos para exportar en crudo (R1): ninguno inventa una unidad
# --------------------------------------------------------------------------- #
def test_columna_sin_dimension_se_exporta_en_crudo(cat: Catalogo) -> None:
    """`dimension_id is None`: el tipo de origen no está en el descriptor."""
    columna = ColumnaAExportar(
        nombre="canal_misterioso", valores=[42.0, 43.0], clase=Clase.PUNTO, dimension_id=None
    )
    preparada = preparar_columna(columna, catalogo=cat)
    assert preparada.encabezado == "canal_misterioso [sin unidad]"
    assert preparada.valores == [42.0, 43.0]  # sin tocar, ni con to_canon
    assert preparada.metadatos["crudo"] is True
    assert preparada.metadatos["dimension"] is None
    assert preparada.metadatos["unidad"] is None


def test_columna_con_confianza_desconocida_se_exporta_en_crudo(cat: Catalogo) -> None:
    """`confianza == "unknown"`: la escala existe pero no está confirmada."""
    columna = ColumnaAExportar(
        nombre="temp_dudosa",
        valores=[3663.0],
        clase=Clase.PUNTO,
        dimension_id="temperature",
        confianza="unknown",
        to_canon=Afin(0.1, 0.0),
    )
    preparada = preparar_columna(columna, catalogo=cat)
    assert preparada.encabezado == "temp_dudosa [sin confirmar]"
    # El valor NO se convierte, ni siquiera con `to_canon`: crudo es crudo.
    assert preparada.valores == [3663.0]
    assert preparada.metadatos["crudo"] is True
    assert preparada.metadatos["dimension"] == "temperature"
    assert "escala_sin_confirmar" in str(preparada.metadatos["motivo_crudo"])


def test_dimension_no_convertible_se_exporta_en_crudo(cat: Catalogo) -> None:
    """La dimensión literal `unknown` del catálogo: contadores, enums, máscaras."""
    columna = ColumnaAExportar(
        nombre="modo_arranque", valores=[7, 7, 8], clase=Clase.PUNTO, dimension_id="unknown"
    )
    preparada = preparar_columna(columna, catalogo=cat)
    # La etiqueta sale del propio catálogo (`data/units.toml`), no se inventa aquí.
    assert preparada.encabezado == "modo_arranque [(crudo)]"
    assert preparada.valores == [7, 7, 8]
    assert preparada.metadatos["crudo"] is True
    assert preparada.metadatos["dimension"] == "unknown"


# --------------------------------------------------------------------------- #
# La trampa del delta, otra vez, pero en la capa de exportación
# --------------------------------------------------------------------------- #
def test_trampa_del_delta_en_la_exportacion(cat: Catalogo) -> None:
    """El caso central de F1-20 (`dlv-core/tests/test_trampa_del_delta.py`),
    repetido aquí porque esta capa tiene su PROPIA oportunidad de cometer el
    mismo fallo: un Δ de 10 K exportado como PUNTO da −263,15 °C; exportado
    como INTERVALO da 10 °C. Las dos columnas parten del MISMO valor
    canónico (10.0) y de la MISMA unidad de destino (°C); solo cambia `clase`.
    """
    columna_punto = ColumnaAExportar(
        nombre="temp",
        valores=10.0,
        clase=Clase.PUNTO,
        dimension_id="temperature",
        unidad_destino="degC",
    )
    columna_delta = ColumnaAExportar(
        nombre="delta_temp",
        valores=10.0,
        clase=Clase.INTERVALO,
        dimension_id="temperature",
        unidad_destino="degC",
    )
    preparada_punto = preparar_columna(columna_punto, catalogo=cat)
    preparada_delta = preparar_columna(columna_delta, catalogo=cat)

    assert preparada_punto.valores == pytest.approx(-263.15, abs=1e-9)
    assert preparada_delta.valores == pytest.approx(10.0, abs=1e-9)
    assert preparada_punto.encabezado == "temp [°C]"
    assert preparada_delta.encabezado == "delta_temp [°C]"


def test_trampa_del_delta_tambien_en_el_paso_bruto_a_canonica(cat: Catalogo) -> None:
    """La misma trampa, un paso más atrás: si `to_canon` tuviera un `b != 0`
    (no es el caso de Haltech hoy, pero el modelo lo permite) y la columna
    fuera un INTERVALO, aplicar ese `b` sería el mismo fallo que aplicar el de
    la unidad de presentación. `preparar_columna` reutiliza `Afin.desde_canonica`
    para los dos pasos, así que la propiedad se cumple en los dos por la misma
    razón y no por casualidad.
    """
    bruto_con_offset = Afin(2.0, 100.0)  # canonica = 2*bruto + 100
    columna_punto = ColumnaAExportar(
        nombre="x",
        valores=5.0,
        clase=Clase.PUNTO,
        dimension_id="voltage",
        to_canon=bruto_con_offset,
    )
    columna_delta = ColumnaAExportar(
        nombre="dx",
        valores=5.0,
        clase=Clase.INTERVALO,
        dimension_id="voltage",
        to_canon=bruto_con_offset,
    )
    preparada_punto = preparar_columna(columna_punto, catalogo=cat)
    preparada_delta = preparar_columna(columna_delta, catalogo=cat)
    # canonica(punto) = 2*5+100 = 110; canonica(delta) = 2*5 = 10 (sin +100).
    # `voltage` es unidad canónica V con conversión identidad, así que el
    # valor mostrado es igual al canónico.
    assert preparada_punto.valores == pytest.approx(110.0, abs=1e-9)
    assert preparada_delta.valores == pytest.approx(10.0, abs=1e-9)


def test_un_delta_de_cero_es_cero_tambien_al_exportar(cat: Catalogo) -> None:
    """El caso de borde que delata un `+ b` de un vistazo (mismo espíritu que
    `test_trampa_del_delta.py::test_un_delta_de_cero_es_cero_en_toda_unidad`)."""
    columna = ColumnaAExportar(
        nombre="delta_temp",
        valores=0.0,
        clase=Clase.INTERVALO,
        dimension_id="temperature",
        unidad_destino="degC",
    )
    preparada = preparar_columna(columna, catalogo=cat)
    assert preparada.valores == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------- #
# Casos generales: unidad canónica, unidad de destino, referencia de presión
# --------------------------------------------------------------------------- #
def test_unidad_por_omision_es_la_canonica(cat: Catalogo) -> None:
    # Escalar y no lista: `Afin.desde_canonica` hace `a * x`, y una lista de
    # Python no soporta esa aritmética (a diferencia de un `numpy.ndarray`,
    # que sí es un `Numerico` válido pero no está instalado en este entorno de
    # verificación; ver el informe de F4-12).
    columna = ColumnaAExportar(
        nombre="rpm_motor", valores=3000.0, clase=Clase.PUNTO, dimension_id="angular_speed"
    )
    preparada = preparar_columna(columna, catalogo=cat)
    assert preparada.valores == pytest.approx(3000.0)
    assert preparada.encabezado == "rpm_motor [rpm]"  # rpm es la canónica de angular_speed
    assert preparada.metadatos["unidad"] == "rpm"


def test_referencia_de_presion_solo_afecta_al_punto(cat: Catalogo) -> None:
    """§6.6: pasar a relativo resta la referencia al PUNTO, no al INTERVALO."""
    referencia = 101.325
    columna_punto = ColumnaAExportar(
        nombre="boost",
        valores=227.2,
        clase=Clase.PUNTO,
        dimension_id="pressure",
        unidad_destino="bar",
        referencia_kpa=referencia,
    )
    columna_delta = ColumnaAExportar(
        nombre="delta_boost",
        valores=50.0,
        clase=Clase.INTERVALO,
        dimension_id="pressure",
        unidad_destino="bar",
        referencia_kpa=referencia,
    )
    preparada_punto = preparar_columna(columna_punto, catalogo=cat)
    preparada_delta = preparar_columna(columna_delta, catalogo=cat)
    assert preparada_punto.valores == pytest.approx((227.2 - referencia) * 0.01, abs=1e-9)
    assert preparada_delta.valores == pytest.approx(0.5, abs=1e-9)
    # La etiqueta dice "rel": "2 bar" sin más es la fuente de error más común
    # al comparar logs de dos herramientas distintas (docs/06 §6.6).
    assert "rel" in preparada_punto.encabezado


def test_conversion_parametrizada_lambda_a_afr(cat: Catalogo) -> None:
    """λ -> AFR con la estequiometría de un combustible concreto (E85, no
    gasolina): sin `parametro`, saldría con 14,7 y sería incorrecto."""
    columna = ColumnaAExportar(
        nombre="lambda_medida",
        valores=1.0,
        clase=Clase.PUNTO,
        dimension_id="mixture_ratio",
        unidad_destino="afr",
        parametro=9.8,  # estequiometría aproximada del E85
    )
    preparada = preparar_columna(columna, catalogo=cat)
    assert preparada.valores == pytest.approx(9.8, abs=1e-9)


def test_dimension_desconocida_lanza_error_de_unidad(cat: Catalogo) -> None:
    columna = ColumnaAExportar(
        nombre="x", valores=1.0, clase=Clase.PUNTO, dimension_id="esto_no_existe"
    )
    with pytest.raises(ErrorDeUnidad):
        preparar_columna(columna, catalogo=cat)


def test_unidad_destino_invalida_lanza_error_de_unidad(cat: Catalogo) -> None:
    columna = ColumnaAExportar(
        nombre="x",
        valores=1.0,
        clase=Clase.PUNTO,
        dimension_id="temperature",
        unidad_destino="esto_tampoco_existe",
    )
    with pytest.raises(ErrorDeUnidad):
        preparar_columna(columna, catalogo=cat)


# --------------------------------------------------------------------------- #
# Los dos formatos de salida (necesitan Polars de verdad)
# --------------------------------------------------------------------------- #
def test_exportar_csv_declara_la_unidad_en_la_cabecera(cat: Catalogo) -> None:
    pytest.importorskip("polars")
    columnas = [
        ColumnaAExportar(nombre="t", valores=[0.0, 1.0], clase=Clase.PUNTO, dimension_id="time"),
        ColumnaAExportar(
            nombre="temp_agua",
            valores=[293.15, 303.15],
            clase=Clase.PUNTO,
            dimension_id="temperature",
            unidad_destino="degC",
        ),
        ColumnaAExportar(nombre="modo", valores=[1, 2], clase=Clase.PUNTO, dimension_id="unknown"),
    ]
    crudo = exportar_csv(columnas, catalogo=cat)
    texto = crudo.decode("utf-8")
    primera_linea = texto.splitlines()[0]
    assert "t [s]" in primera_linea
    assert "temp_agua [°C]" in primera_linea
    assert "modo [(crudo)]" in primera_linea
    # Los valores YA convertidos, no los canónicos: 20 y 30 °C.
    assert "20" in texto
    assert "30" in texto


def test_exportar_parquet_declara_la_unidad_en_los_metadatos_del_fichero(cat: Catalogo) -> None:
    pl = pytest.importorskip("polars")
    import io
    import json

    columnas = [
        ColumnaAExportar(
            nombre="temp_agua",
            valores=[293.15],
            clase=Clase.PUNTO,
            dimension_id="temperature",
            unidad_destino="degC",
        ),
    ]
    crudo = exportar_parquet(columnas, catalogo=cat)
    metadatos: dict[str, Any] = pl.read_parquet_metadata(io.BytesIO(crudo))
    assert metadatos["dlv:version"] == "1"
    por_columna = json.loads(metadatos["dlv:unidades"])
    assert por_columna["temp_agua [°C]"]["unidad"] == "degC"
    assert por_columna["temp_agua [°C]"]["dimension"] == "temperature"
    assert por_columna["temp_agua [°C]"]["crudo"] is False

    tabla = pl.read_parquet(io.BytesIO(crudo))
    assert tabla.columns == ["temp_agua [°C]"]
    assert tabla["temp_agua [°C]"][0] == pytest.approx(20.0, abs=1e-9)


def test_un_polars_sin_metadata_da_un_error_con_nombre(cat: Catalogo) -> None:
    """`write_parquet(metadata=...)` es reciente y `pyproject.toml` declara
    `polars>=1.9`, donde no existe. Con una versión antigua, Polars levanta un
    `TypeError` por argumento inesperado que no dice nada útil y que llegaría al
    usuario como una traza a través de la respuesta HTTP. Se traduce a
    `ErrorDeExportacion`, cuyo mensaje dice qué pasa y qué hacer.

    Se simula el `TypeError` en vez de instalar un Polars antiguo: lo que se
    comprueba es la traducción del error, no el comportamiento de Polars.
    """
    pl = pytest.importorskip("polars")

    class TablaVieja:
        def write_parquet(self, _buffer: object, **_kw: object) -> None:
            raise TypeError("write_parquet() got an unexpected keyword argument 'metadata'")

    columnas = [
        ColumnaAExportar(
            nombre="temp",
            valores=[10.0],
            clase=Clase.PUNTO,
            dimension_id="temperature",
            unidad_destino="degC",
        )
    ]
    original = pl.DataFrame
    try:
        pl.DataFrame = lambda *_a, **_k: TablaVieja()  # type: ignore[assignment, misc]
        with pytest.raises(ErrorDeExportacion, match="no admite"):
            exportar_parquet(columnas, catalogo=cat)
    finally:
        pl.DataFrame = original  # type: ignore[misc]
