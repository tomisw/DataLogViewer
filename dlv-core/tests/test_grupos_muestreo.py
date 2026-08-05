"""Pruebas de la detección vectorizada de grupos de muestreo (tarea F1-06).

Cubre lo mismo que ya probaba F1-05 sobre `construir_desde_polars` --dos
columnas con la misma máscara van juntas, dos con el mismo recuento pero
filas distintas no se confunden-- pero contra la función aislada, más un caso
que antes no se ejercitaba en solitario: muchas columnas con solo un puñado
de patrones distintos, para comprobar que `numpy.unique` agrupa todas a la
vez sin perder ninguna.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from dlv_core.grupos_muestreo import detectar_grupos_de_muestreo


def test_columnas_sin_nulos_van_todas_al_mismo_grupo() -> None:
    df = pl.DataFrame(
        {
            "a": pl.Series([1, 2, 3], dtype=pl.Int32),
            "b": pl.Series([4, 5, 6], dtype=pl.Int32),
            "c": pl.Series([7, 8, 9], dtype=pl.Int32),
        }
    )
    grupos = detectar_grupos_de_muestreo(df, ["a", "b", "c"])

    assert len(grupos) == 1
    mascara, columnas = grupos[0]
    assert mascara.tolist() == [True, True, True]
    assert sorted(columnas) == ["a", "b", "c"]


def test_patrones_distintos_no_se_confunden_aunque_tengan_el_mismo_recuento() -> None:
    df = pl.DataFrame(
        {
            "a": pl.Series([1, 2, None], dtype=pl.Int32),  # activo en filas 0,1
            "b": pl.Series([None, 2, 3], dtype=pl.Int32),  # activo en filas 1,2
        }
    )
    grupos = detectar_grupos_de_muestreo(df, ["a", "b"])

    assert len(grupos) == 2
    por_columna = {col: mascara for mascara, cols in grupos for col in cols}
    assert por_columna["a"].tolist() == [True, True, False]
    assert por_columna["b"].tolist() == [False, True, True]


def test_muchas_columnas_con_pocos_patrones_se_agrupan_correctamente() -> None:
    """20 columnas, 3 patrones distintos repartidos entre ellas: comprueba que
    numpy.unique no pierde ni mezcla ninguna."""
    n_filas = 50
    rng = np.random.default_rng(7)
    patron_a = rng.random(n_filas) > 0.5
    patron_b = rng.random(n_filas) > 0.5
    patron_c = np.ones(n_filas, dtype=bool)

    columnas: dict[str, pl.Series] = {}
    asignacion: dict[str, np.ndarray] = {}
    patrones_disponibles = [patron_a, patron_b, patron_c]
    for i in range(20):
        patron = patrones_disponibles[i % 3]
        valores = [i if activo else None for activo in patron]
        columnas[f"col_{i}"] = pl.Series(valores, dtype=pl.Int32)
        asignacion[f"col_{i}"] = patron

    df = pl.DataFrame(columnas)
    grupos = detectar_grupos_de_muestreo(df, list(columnas.keys()))

    assert len(grupos) == 3
    for mascara, cols in grupos:
        for c in cols:
            assert mascara.tolist() == asignacion[c].tolist()
    # Ninguna columna se pierde ni se duplica.
    todas = sorted(c for _, cols in grupos for c in cols)
    assert todas == sorted(columnas.keys())


def test_sin_columnas_devuelve_lista_vacia() -> None:
    df = pl.DataFrame({"a": pl.Series([1], dtype=pl.Int32)})
    assert detectar_grupos_de_muestreo(df, []) == []
