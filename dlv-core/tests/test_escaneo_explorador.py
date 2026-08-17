"""Pruebas del escaneo incremental y cancelable del explorador (FE-08).

Especificación: `docs/02-alcance-y-plan.md` §2.5, E15.7.

QUÉ PROTEGE ESTA SUITE, POR CONSECUENCIA SI SE ROMPE
=====================================================
1. **Cancelar deja el índice coherente**: lo calculado antes de cancelar se
   conserva, lo que faltaba vuelve a salir en `a_calcular` la próxima vez, y
   no se pierde ni se inventa nada. Sin esto, cerrar la carpeta a mitad de un
   escaneo de 200 logs tiraría el trabajo ya hecho.
2. **El orden de llegada no cambia**: una fila que ya se emitió no se
   recalcula ni cambia de posición cuando llegan más. Sin esto, la tabla
   "baila" mientras el usuario intenta hacer clic en una fila.
3. **Un log corrupto no para el escaneo**: se usa el corpus real de
   `samples/corrupt/` (docs/01 §1.13) contra el parser real de cabecera
   (`dlv_core.formatos.haltech`, que no necesita Polars/NumPy) para
   comprobar el caso con una excepción de verdad, no simulada.
4. **La reapertura solo calcula lo nuevo**: un segundo escaneo sobre la misma
   carpeta con el índice del primero de vuelta, reutiliza lo ya calculado.

Solo biblioteca estándar más `dlv_core.formatos.haltech`, que no importa
Polars ni NumPy (a diferencia de `formatos.cuerpo`, que si los importa y por
tanto no se usa aquí: ver `docs/09` §8.10, PyPI bloqueado en este entorno).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dlv_core.explorador.escaneo import (
    FilaCalculada,
    FilaConError,
    FilaReutilizada,
    escanear_incremental,
)
from dlv_core.explorador.indice import (
    EntradaDeCarpeta,
    aplicar_resumenes,
    planificar_indexado,
)
from dlv_core.formatos.haltech import Descriptor, cargar_descriptor, parsear_cabecera

RAIZ = Path(__file__).resolve().parents[2]
CORRUPTOS = RAIZ / "samples" / "corrupt"
REALES = RAIZ / "samples" / "real"

VERSIONES: dict[str, str] = {
    "version_parser": "1.0",
    "version_descriptor_formato": "haltech-nsp-1",
}


def entrada(nombre: str, *, tamano: int = 1000, mtime: int = 111) -> EntradaDeCarpeta:
    return EntradaDeCarpeta(ruta=Path("/logs") / nombre, tamano_bytes=tamano, mtime_ns=mtime)


# --------------------------------------------------------------------------- #
# Un escaneo completo, sin índice previo
# --------------------------------------------------------------------------- #
def test_un_escaneo_completo_emite_una_fila_calculada_por_entrada() -> None:
    entradas = [entrada("a.csv"), entrada("b.csv"), entrada("c.csv")]
    plan = planificar_indexado(entradas, None, **VERSIONES)

    def calcular(e: EntradaDeCarpeta) -> dict[str, Any]:
        return {"rpm_max": float(len(e.ruta.name))}

    filas = list(escanear_incremental(plan, calcular))

    assert all(isinstance(f, FilaCalculada) for f in filas)
    assert [f.entrada.ruta.name for f in filas if isinstance(f, FilaCalculada)] == [
        "a.csv",
        "b.csv",
        "c.csv",
    ]


def test_las_reutilizables_se_emiten_antes_que_ninguna_calculada() -> None:
    """No hay nada que esperar para una entrada en caché: sale primero, sin
    depender del orden en que se calculen las nuevas."""
    viejas = [entrada("a.csv"), entrada("b.csv")]
    plan_inicial = planificar_indexado(viejas, None, **VERSIONES)
    indice_previo = aplicar_resumenes(
        plan_inicial, {e.ruta: {"rpm_max": 1.0} for e in viejas}, **VERSIONES
    )

    plan = planificar_indexado([*viejas, entrada("c.csv")], indice_previo, **VERSIONES)
    filas = list(escanear_incremental(plan, lambda e: {"rpm_max": 2.0}))

    tipos = [type(f).__name__ for f in filas]
    assert tipos == ["FilaReutilizada", "FilaReutilizada", "FilaCalculada"]
    assert [f.entrada.ruta.name for f in filas if isinstance(f, FilaReutilizada)] == [
        "a.csv",
        "b.csv",
    ]
    assert filas[2].entrada.ruta.name == "c.csv"  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# Cancelación a mitad: el índice queda coherente
# --------------------------------------------------------------------------- #
def test_cancelar_a_mitad_conserva_lo_calculado_y_deja_pendiente_el_resto() -> None:
    entradas = [entrada(f"log{i}.csv") for i in range(5)]
    plan = planificar_indexado(entradas, None, **VERSIONES)

    calculadas: list[str] = []

    def calcular(e: EntradaDeCarpeta) -> dict[str, Any]:
        calculadas.append(e.ruta.name)
        return {"rpm_max": 1.0}

    # Cancela justo después de haber calculado 2 de las 5.
    def cancelado() -> bool:
        return len(calculadas) >= 2

    filas = list(escanear_incremental(plan, calcular, cancelado=cancelado))

    # Estado ANTES de aplicar_resumenes/escribir_indice: solo se calcularon 2.
    assert calculadas == ["log0.csv", "log1.csv"]
    assert [f.entrada.ruta.name for f in filas if isinstance(f, FilaCalculada)] == [
        "log0.csv",
        "log1.csv",
    ]

    resumenes = {f.entrada.ruta: f.resumen for f in filas if isinstance(f, FilaCalculada)}
    indice_tras_cancelar = aplicar_resumenes(plan, resumenes, **VERSIONES)

    # Estado DESPUÉS: el índice solo contiene lo que se alcanzó a calcular.
    # No se perdió (log0, log1 siguen) y no se inventó nada para log2..4.
    assert [e.ruta.name for e in indice_tras_cancelar.entradas] == ["log0.csv", "log1.csv"]

    # Y la siguiente apertura retoma justo donde se quedó: los 3 que faltaban
    # vuelven a `a_calcular`, los 2 ya calculados se reutilizan.
    plan_siguiente = planificar_indexado(entradas, indice_tras_cancelar, **VERSIONES)
    assert [e.ruta.name for e in plan_siguiente.a_calcular] == [
        "log2.csv",
        "log3.csv",
        "log4.csv",
    ]
    assert [e.ruta.name for e in plan_siguiente.reutilizables] == ["log0.csv", "log1.csv"]


def test_cancelado_desde_el_principio_no_calcula_nada_nuevo() -> None:
    """Si ya estaba cancelado al empezar (p. ej. el usuario cerró la carpeta
    antes de que el escaneo arrancara), las reutilizables se siguen viendo
    -son gratis- pero no se calcula ni un log nuevo."""
    viejas = [entrada("a.csv")]
    indice_previo = aplicar_resumenes(
        planificar_indexado(viejas, None, **VERSIONES), {viejas[0].ruta: {"x": 1}}, **VERSIONES
    )
    plan = planificar_indexado([*viejas, entrada("b.csv")], indice_previo, **VERSIONES)

    llamadas = 0

    def calcular(e: EntradaDeCarpeta) -> dict[str, Any]:
        nonlocal llamadas
        llamadas += 1
        return {}

    filas = list(escanear_incremental(plan, calcular, cancelado=lambda: True))

    assert llamadas == 0
    assert [type(f).__name__ for f in filas] == ["FilaReutilizada"]


def test_cancelar_no_impide_seguir_iterando_manualmente_hasta_donde_se_quiera() -> None:
    """El generador no se cancela "desde fuera" cerrándolo: quien lo consume
    simplemente deja de pedir la siguiente fila. Aquí se comprueba que pedir
    solo las N primeras filas con `next()` no dispara ningún cálculo de más."""
    entradas = [entrada(f"log{i}.csv") for i in range(4)]
    plan = planificar_indexado(entradas, None, **VERSIONES)
    vistas: list[str] = []

    def calcular(e: EntradaDeCarpeta) -> dict[str, Any]:
        vistas.append(e.ruta.name)
        return {}

    generador = escanear_incremental(plan, calcular)
    next(generador)
    next(generador)
    assert vistas == ["log0.csv", "log1.csv"]


# --------------------------------------------------------------------------- #
# El orden de las filas ya emitidas no cambia
# --------------------------------------------------------------------------- #
def test_el_orden_de_las_filas_emitidas_es_estable_al_llegar_mas() -> None:
    """Si el escaneo de una carpeta de 3 se amplía a 5 (dos ficheros nuevos
    aparecidos entre una llamada y otra, aunque aquí se simula con dos planes
    sucesivos), el prefijo ya visto no cambia de orden."""
    entradas_3 = [entrada("a.csv"), entrada("b.csv"), entrada("c.csv")]
    plan_3 = planificar_indexado(entradas_3, None, **VERSIONES)
    orden_3 = [f.entrada.ruta.name for f in escanear_incremental(plan_3, lambda e: {})]

    entradas_5 = [*entradas_3, entrada("d.csv"), entrada("e.csv")]
    plan_5 = planificar_indexado(entradas_5, None, **VERSIONES)
    orden_5 = [f.entrada.ruta.name for f in escanear_incremental(plan_5, lambda e: {})]

    assert orden_5[: len(orden_3)] == orden_3
    assert orden_5 == ["a.csv", "b.csv", "c.csv", "d.csv", "e.csv"]


# --------------------------------------------------------------------------- #
# La reapertura: solo se calcula lo nuevo
# --------------------------------------------------------------------------- #
def test_segundo_escaneo_reutiliza_lo_del_primero_y_solo_calcula_lo_nuevo() -> None:
    entradas = [entrada("a.csv"), entrada("b.csv")]
    plan1 = planificar_indexado(entradas, None, **VERSIONES)
    llamadas_1: list[str] = []
    filas1 = list(
        escanear_incremental(plan1, lambda e: llamadas_1.append(e.ruta.name) or {"rpm_max": 1.0})
    )
    indice1 = aplicar_resumenes(
        plan1,
        {f.entrada.ruta: f.resumen for f in filas1 if isinstance(f, FilaCalculada)},
        **VERSIONES,
    )
    assert llamadas_1 == ["a.csv", "b.csv"]

    # Carpeta reabierta: a.csv y b.csv sin cambios, más un log nuevo.
    entradas_2 = [*entradas, entrada("c.csv")]
    plan2 = planificar_indexado(entradas_2, indice1, **VERSIONES)
    llamadas_2: list[str] = []
    filas2 = list(
        escanear_incremental(plan2, lambda e: llamadas_2.append(e.ruta.name) or {"rpm_max": 2.0})
    )

    # Solo se volvió a abrir el log nuevo.
    assert llamadas_2 == ["c.csv"]
    assert [type(f).__name__ for f in filas2] == [
        "FilaReutilizada",
        "FilaReutilizada",
        "FilaCalculada",
    ]
    assert [f.entrada.ruta.name for f in filas2] == ["a.csv", "b.csv", "c.csv"]


# --------------------------------------------------------------------------- #
# Un log corrupto no para el escaneo (corpus real de samples/corrupt/)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def descriptor_haltech() -> Descriptor:
    with (RAIZ / "data" / "formats" / "haltech_nsp.toml").open("rb") as fh:
        return cargar_descriptor(fh)


def _resumen_de_cabecera(
    entrada_carpeta: EntradaDeCarpeta, descriptor: Descriptor
) -> dict[str, Any]:
    """Un `calcular_resumen` real y mínimo: parsea la cabecera del log (sin
    Polars/NumPy, que no están instalables en este entorno -- ver docs/09
    §8.10) y lanza exactamente lo que lanzaría `dlv-api` al intentar abrir un
    log con la cabecera rota o una versión que el descriptor no soporta."""
    datos = entrada_carpeta.ruta.read_bytes()
    cabecera = parsear_cabecera(datos, descriptor)
    return {"n_canales": cabecera.n_canales, "version": cabecera.version}


def test_un_log_corrupto_no_para_el_escaneo_de_los_demas(descriptor_haltech: Descriptor) -> None:
    """01 (cabecera truncada) y 10 (versión desconocida) son, según
    `samples/corrupt/README.md`, los dos únicos casos de rechazo fatal del
    corpus; el resto carga (con o sin aviso). El escaneo tiene que atravesar
    los 11 y enseñar los dos rotos con su error, sin detenerse."""
    nombres = sorted(p.name for p in CORRUPTOS.glob("*.csv"))
    assert len(nombres) == 11  # docs/01 §1.13: once casos

    entradas = [
        EntradaDeCarpeta(
            ruta=CORRUPTOS / n,
            tamano_bytes=(CORRUPTOS / n).stat().st_size,
            mtime_ns=(CORRUPTOS / n).stat().st_mtime_ns,
        )
        for n in nombres
    ]
    plan = planificar_indexado(entradas, None, **VERSIONES)

    filas = list(escanear_incremental(plan, lambda e: _resumen_de_cabecera(e, descriptor_haltech)))

    # Los 11 se atravesaron -ninguno detuvo el escaneo-.
    assert len(filas) == 11

    con_error = {f.entrada.ruta.name for f in filas if isinstance(f, FilaConError)}
    calculadas = {f.entrada.ruta.name for f in filas if isinstance(f, FilaCalculada)}
    assert con_error == {"01-cabecera-truncada.csv", "10-version-desconocida.csv"}
    assert calculadas == set(nombres) - con_error

    error_10 = next(
        f for f in filas if isinstance(f, FilaConError) and "10-" in f.entrada.ruta.name
    )
    assert "2.0" in error_10.error  # el mensaje real del parser cita la versión rechazada

    # Y lo que falló no entra en el índice: la próxima apertura lo reintenta.
    resumenes = {f.entrada.ruta: f.resumen for f in filas if isinstance(f, FilaCalculada)}
    indice = aplicar_resumenes(plan, resumenes, **VERSIONES)
    nombres_en_indice = {e.ruta.name for e in indice.entradas}
    assert nombres_en_indice == calculadas
    assert "01-cabecera-truncada.csv" not in nombres_en_indice
    assert "10-version-desconocida.csv" not in nombres_en_indice


# --------------------------------------------------------------------------- #
# Contra los tres logs reales del propietario (samples/real/, no se tocan)
# --------------------------------------------------------------------------- #
def test_escaneo_de_los_tres_logs_reales(descriptor_haltech: Descriptor) -> None:
    """`samples/real/` no se modifica (regla del proyecto): solo se lee. Sirve
    para medir -ver el informe de la tarea- cuánto tarda de verdad el
    escaneo de cabecera de los tres logs del propietario."""
    nombres = sorted(p.name for p in REALES.iterdir() if p.is_file())
    assert len(nombres) == 3

    entradas = [
        EntradaDeCarpeta(
            ruta=REALES / n,
            tamano_bytes=(REALES / n).stat().st_size,
            mtime_ns=(REALES / n).stat().st_mtime_ns,
        )
        for n in nombres
    ]
    plan = planificar_indexado(entradas, None, **VERSIONES)

    filas = list(escanear_incremental(plan, lambda e: _resumen_de_cabecera(e, descriptor_haltech)))

    assert len(filas) == 3
    assert all(isinstance(f, FilaCalculada) for f in filas)
