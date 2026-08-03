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

    # POR QUÉ NO `np.unique(matriz, axis=0)` (F1-42)
    # ==============================================
    # Era lo que hacía esta función y es lo que parece natural, pero costaba
    # **4,70 s de los 4,79 s** que tardaba abrir el AutoLog sintético de 70 MB
    # y 475 canales: el 98 % del presupuesto de apertura de §2.6 (< 4,0 s) se
    # iba aquí. `np.unique(axis=0)` no compara filas: las reinterpreta como
    # escalares `void` y las ordena lexicográficamente, y con 475 filas de
    # 38 698 bytes eso es una montaña de comparaciones sobre 18 MB.
    #
    # Lo que hace falta no es ordenar los patrones, es saber cuáles son
    # IGUALES. `packbits` comprime cada patrón de 38 698 booleanos a 4 838
    # bytes (×8) y la igualdad byte a byte es exactamente la igualdad de
    # patrón, así que un diccionario resuelve el agrupamiento en una pasada.
    #
    # El bucle recorre CANALES (475), no muestras (17,7 millones): ADR-009
    # prohíbe lo segundo, no lo primero. Todo el trabajo por muestra —el
    # `is_not_null` y el `packbits`— sigue siendo vectorizado.
    #
    # Efecto lateral bueno: el orden de salida pasa a ser el de primera
    # aparición en `columnas`, en vez de depender de cómo `numpy` ordene
    # patrones de bits. `construir_desde_polars` reordena de todas formas, pero
    # un orden que se puede explicar es más fácil de depurar que uno que no.
    empaquetada = np.packbits(matriz, axis=1)

    indice_por_patron: dict[bytes, int] = {}
    grupos: list[tuple[np.ndarray, list[str]]] = []
    for i, columna in enumerate(columnas):
        clave = empaquetada[i].tobytes()
        indice = indice_por_patron.get(clave)
        if indice is None:
            indice_por_patron[clave] = len(grupos)
            grupos.append((matriz[i], [columna]))
        else:
            grupos[indice][1].append(columna)
    return grupos
