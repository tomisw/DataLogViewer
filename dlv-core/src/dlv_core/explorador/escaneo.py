"""Escaneo incremental y cancelable de un `PlanDeIndexado` (FE-08).

Especificación: `docs/02-alcance-y-plan.md` §2.5, E15.7, y el presupuesto de
§2.6 («200 logs en frío en menos de 60 s, con filas apareciendo desde la
primera»). Sesenta segundos con la pantalla en blanco es una aplicación
colgada; este módulo es lo que convierte «calcular el resumen de 200 logs» en
una secuencia de filas que van llegando, en vez de un resultado que se
entrega todo junto al final.

QUÉ NO RESUELVE ESTE MÓDULO
===========================
`indice.py` (FE-01) ya resuelve la mitad de «incremental»: `planificar_indexado`
decide qué hay que calcular y qué se reutiliza, y `aplicar_resumenes` acepta un
diccionario de resúmenes INCOMPLETO respecto a `plan.a_calcular` sin tratarlo
como error, precisamente para que un escaneo cancelado a mitad deje un índice
coherente (lo calculado se guarda, lo que falta vuelve a salir en
`a_calcular` la próxima vez). Este módulo no toca esa mecánica: solo la
recorre en el orden y con la granularidad que hacen falta para que una
interfaz pueda pintar cada fila según llega.

Quien conserva el estado -acumular `resumenes` según llegan las filas, y
escribir el índice con `aplicar_resumenes` + `escribir_indice` cuando termina
o se cancela- es quien consume este generador (`dlv-api`), no este módulo.

ADR-002: `dlv-core` NO ABRE FICHEROS
=====================================
`calcular_resumen` es un `Callable` que recibe una `EntradaDeCarpeta` y
devuelve un resumen ya calculado (o lanza si el log no se puede leer o
interpretar). Quien lo implementa -`dlv-api`- es quien abre el fichero; este
módulo solo lo invoca una vez por entrada de `plan.a_calcular`, igual que
`aplicar_resumenes` recibe los resúmenes ya calculados en vez de calcularlos.

ORDEN DE LLEGADA: FIJO, Y ELEGIDO PARA QUE NO SE REORDENE (E15.7, regla 2)
============================================================================
Primero se emiten las reutilizables -ya están en caché, no hay nada que
esperar-, en el mismo orden por ruta que trae `plan.reutilizables` (que ya
viene ordenado: ver `planificar_indexado`). Luego se recorre `plan.a_calcular`
-también ya ordenado por ruta- **secuencialmente**, un log detrás de otro, y
cada resultado se emite en cuanto se calcula.

Esto fija el orden de llegada en un valor conocido de antemano
(reutilizables, luego a_calcular, cada grupo por ruta) e independiente de
cuánto tarde cada log: no hay concurrencia que pueda hacer que un log rápido
adelante a otro más lento y cambie de sitio una fila que el usuario ya está
mirando. La alternativa -lanzar el cálculo de varios logs a la vez y emitir
en orden de finalización- sería más rápida en el mejor caso, pero el orden
dependería de la velocidad de cada log y una fila podría aparecer, y con la
siguiente apertura de la misma carpeta salir en otra posición: exactamente lo
que la regla 2 de la tarea prohíbe. El bucle secuencial sobre ficheros no
compromete el presupuesto de ADR-009 (que prohíbe el bucle por MUESTRA, no
por fichero: ver la cabecera de `indice.py`).

CANCELACIÓN: COOPERATIVA, COMPROBADA ENTRE FICHEROS
=====================================================
`cancelado` es un `Callable[[], bool]` que se consulta antes de calcular cada
entrada de `plan.a_calcular` (no antes de emitir las reutilizables: ya están
en caché, emitirlas no cuesta nada y no hay ninguna razón para retenerlas).
En cuanto devuelve `True` el generador termina sin calcular más -`return`, no
excepción-, y lo que ya se había calculado sigue disponible para quien lo
consumió hasta ese punto. No se comprueba a mitad del cálculo de UN log: la
granularidad de cancelación es el fichero, igual que la de ADR-002 es abrir
un fichero de una vez, no en trozos.

UN LOG QUE FALLA NO PARA EL ESCANEO (E15.7, regla 3)
======================================================
Si `calcular_resumen` lanza, la excepción se captura y se emite como
`FilaConError` en vez de propagarse: doscientos logs y uno corrupto no
pueden convertirse en que los otros ciento noventa y nueve no se enseñen.
Deliberadamente no entra en el índice -no hay resumen que guardar-, así que
la próxima apertura lo vuelve a intentar; si el fichero se arregla mientras
tanto (se resube, se repara), no hace falta borrar el índice a mano para que
se recalcule. Es la misma lógica que ya tiene `aplicar_resumenes` para un
resumen ausente, aplicada aquí al caso en que la ausencia es un fallo y no
una cancelación.

Solo biblioteca estándar.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from dlv_core.explorador.indice import EntradaDeCarpeta, EntradaDeIndice, PlanDeIndexado

__all__ = [
    "FilaCalculada",
    "FilaConError",
    "FilaDeEscaneo",
    "FilaReutilizada",
    "escanear_incremental",
]


@dataclass(slots=True, frozen=True)
class FilaReutilizada:
    """Una fila que ya estaba en el índice: se enseña sin recalcular.

    Se emite antes que ninguna `FilaCalculada`, porque no hay nada que
    esperar -el resumen ya estaba en el índice leído de disco-.
    """

    entrada: EntradaDeIndice


@dataclass(slots=True, frozen=True)
class FilaCalculada:
    """Una fila recién resumida en este escaneo."""

    entrada: EntradaDeCarpeta
    resumen: dict[str, Any]


@dataclass(slots=True, frozen=True)
class FilaConError:
    """Un log de `plan.a_calcular` que no se pudo resumir.

    `error` es el texto de la excepción que lanzó `calcular_resumen`, para
    que la fila lo enseñe en la tabla (regla 3 de E15.7). No lleva `resumen`
    a propósito: nunca entra en el índice, así que no hay que distinguirlo
    después de un resumen vacío legítimo (ver `aplicar_resumenes`).
    """

    entrada: EntradaDeCarpeta
    error: str


#: Una fila tal como la ve quien consume `escanear_incremental`: de dónde
#: viene (caché, cálculo nuevo, o cálculo fallido) determina qué hacer con
#: ella -pintarla ya, acumular su resumen para el índice nuevo, o enseñar el
#: error-, así que la unión es explícita en vez de un campo `resumen: dict |
#: None` que obligaría a inventar un tercer significado para `None`.
FilaDeEscaneo = FilaReutilizada | FilaCalculada | FilaConError


def escanear_incremental(
    plan: PlanDeIndexado,
    calcular_resumen: Callable[[EntradaDeCarpeta], dict[str, Any]],
    *,
    cancelado: Callable[[], bool] = lambda: False,
) -> Iterator[FilaDeEscaneo]:
    """Recorre un `PlanDeIndexado` emitiendo una fila a la vez, en orden fijo.

    `plan` es el resultado de `planificar_indexado` (FE-01): ya sabe qué
    reutilizar y qué calcular, y `plan.total_de_filas` da el denominador de
    «37 de 200» desde antes de la primera fila.

    `calcular_resumen` la implementa quien tenga acceso al disco (`dlv-api`,
    ADR-002): recibe la `EntradaDeCarpeta` y devuelve el resumen, o lanza si
    el log no se puede abrir o interpretar.

    `cancelado` se consulta antes de cada entrada de `plan.a_calcular`. En
    cuanto devuelve `True` el generador se agota sin calcular más filas; no
    hace falta capturar ninguna excepción de cancelación porque no se lanza
    ninguna, y lo que ya se había emitido -incluidas todas las
    `FilaReutilizada`- sigue siendo válido: quien consume el generador solo
    tiene que dejar de pedir la siguiente fila.

    No hace ninguna llamada al sistema de ficheros por su cuenta: todo el
    acceso a disco pasa por `calcular_resumen`.
    """
    for reutilizada in plan.reutilizables:
        yield FilaReutilizada(entrada=reutilizada)

    for candidata in plan.a_calcular:
        if cancelado():
            return
        try:
            resumen = calcular_resumen(candidata)
        except Exception as excepcion:
            yield FilaConError(entrada=candidata, error=str(excepcion))
            continue
        yield FilaCalculada(entrada=candidata, resumen=resumen)
