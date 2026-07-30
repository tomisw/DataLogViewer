"""Detección de grupos de muestreo, vectorizada con NumPy (tarea F1-06).

`dlv_core.almacen.construir_desde_polars` (F1-05) ya agrupa canales por
patrón de nulos exacto (§3.4 paso 4, "grupos de muestreo") con un método
directo: un `dict` de Python por columna, razonable porque el número de
columnas son unas pocas centenas, no las 38 M de muestras. Esta tarea pide la
versión que compara las máscaras de todas las columnas **de una vez**: en vez
de que Python acumule en un `dict` clave a clave, se apilan las máscaras en
una matriz y `numpy.unique(axis=0)` encuentra los patrones distintos con un
único primitivo vectorizado. El resultado es idéntico; lo que cambia es quién
hace la comparación entre columnas, NumPy en vez de un bucle de Python.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import polars as pl

__all__ = ["detectar_grupos_de_muestreo"]


def detectar_grupos_de_muestreo(
    df: pl.DataFrame, columnas: Sequence[str]
) -> list[tuple[np.ndarray, list[str]]]:
    """Agrupa `columnas` por patrón de nulos EXACTO (misma máscara de filas
    activas, no solo el mismo número de muestras).

    Apila la máscara "no nula" de cada columna en una matriz
    `(n_columnas, n_filas)` y usa `numpy.unique(axis=0, return_inverse=True)`
    para encontrar las filas (patrones) distintas: la comparación entre
    columnas es un único paso vectorizado sobre toda la matriz, no una
    comparación acumulada columna a columna.

    Devuelve una lista de `(mascara, columnas_del_grupo)`, un elemento por
    patrón distinto. El orden de los grupos no coincide necesariamente con el
    de `columnas`: `numpy.unique` ordena los patrones. El orden DENTRO de
    `columnas_del_grupo` sí conserva el de `columnas` de entrada.
    """
    if not columnas:
        return []

    matriz = np.stack([df[c].is_not_null().to_numpy() for c in columnas])
    patrones, inverso = np.unique(matriz, axis=0, return_inverse=True)
    # NumPy >= 2.0 ya da un array plano (n_columnas,) para este caso, pero se
    # homogeneiza por si una versión futura vuelve a la forma (n_columnas, 1).
    inverso = inverso.reshape(-1)

    grupos: list[tuple[np.ndarray, list[str]]] = []
    for indice_patron in range(len(patrones)):
        posiciones = np.flatnonzero(inverso == indice_patron)
        grupos.append((patrones[indice_patron], [columnas[int(i)] for i in posiciones]))
    return grupos
