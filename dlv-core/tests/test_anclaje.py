"""Pruebas del anclaje por evento (F2-07, `docs/03` §3.6 y `docs/02` §2.10).

QUÉ PROTEGE ESTA SUITE, ORDENADA POR CONSECUENCIA SI SE ROMPE
=============================================================
1. **Un segmento sin el evento no se alinea con un desfase de 0 en silencio.**
   Es la pregunta que decide la tarea: se excluye del eje y se explica en
   `sin_ancla` con `MotivoSinAncla.EVENTO_NO_OCURRIDO`. Hay un caso con datos
   sintéticos que reproducen la propiedad MEDIDA de `Log2768`/`Log2769` en
   `samples/real/` (mariposa máxima 0,558/0,569, nunca llegan a WOT --
   `data/umbrales.toml`, comentario de `[segmentacion]`).
2. **El ancla coincide exactamente en `x = 0`** para todos los segmentos que sí
   la tienen, que es la aritmética que hace útil el modo: dos tiradas que no
   empezaron a la vez quedan superpuestas desde el instante del evento.
3. **Una coincidencia DIFUSA sin confirmar no ancla a ciegas**, y es una
   decisión POR SEGMENTO: un log con el rol confirmado y otro con el mismo rol
   sin confirmar tienen que dar resultados distintos en la misma llamada.
4. **PRIMER_WOT reutiliza `segmentacion.segmentar` tal cual** (no una
   redefinición propia de WOT) y **PRIMER_CORTE reutiliza el umbral de D14**
   sin la permanencia de detector, igual que `exclusion._condicion_corte` y por
   el mismo motivo.
5. **LANZAMIENTO se niega explícitamente sin un umbral**, en vez de adivinar
   uno: no hay ningún documento ni medición de qué código de `launch_state` es
   "activo".
6. **Ni un umbral de `data/umbrales.toml` cableado** (regla 3), comprobado en
   el AST igual que `test_exclusion.py` y `test_segmentacion.py`.
7. **Ni un bucle por muestra** (ADR-009): los únicos `for` recorren segmentos.

Como `test_exclusion.py` (y por el mismo motivo: el tamaño de la tarea), esta
suite se ejercita con NumPy real y no con el doble `XpVec` de
`test_segmentacion.py`/`test_primitivas.py`. Es una divergencia deliberada de
esa convención, documentada aquí como allí: si alguna función de este módulo
usara una operación de NumPy fuera del protocolo `Vectorial`, esta suite no lo
detectaría.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from dlv_core.anclaje import (
    ROL_CORTE,
    ROL_LANZAMIENTO,
    ROL_MARIPOSA,
    ROL_REGIMEN,
    ErrorDeAnclaje,
    MotivoSinAncla,
    TipoAncla,
    UmbralesDeAnclaje,
    ancla_por_evento,
)
from dlv_core.primitivas import Clase, Permanencia, Serie
from dlv_core.segmentacion import ClaseDeSegmento, UmbralesDeSegmentacion
from dlv_core.tiempo import FiabilidadReloj, ModoDesfase
from dlv_core.tiempo import Segmento as SegmentoDeLog

RAIZ = Path(__file__).resolve().parent.parent.parent
UMBRALES_TOML = RAIZ / "data" / "umbrales.toml"
MODULO = RAIZ / "dlv-core" / "src" / "dlv_core" / "anclaje.py"

DT_MS = 50.0  # 20 Hz


def _t(n: int, dt_ms: float = DT_MS) -> np.ndarray:
    return np.arange(n, dtype=np.float64) * dt_ms


def _serie(valores: list[float], *, dt_ms: float = DT_MS, clase: Clase = Clase.PUNTO) -> Serie:
    return Serie(t_ms=_t(len(valores), dt_ms), v=np.asarray(valores, dtype=np.float64), clase=clase)


def _segmento(id_: str, n: int, *, dt_ms: float = DT_MS, orden: int = 0) -> SegmentoDeLog:
    return SegmentoDeLog(
        id=id_,
        t_inicio=0.0,
        t_fin=(n - 1) * dt_ms / 1000.0,
        t0_absoluto=None,
        fiabilidad_reloj=FiabilidadReloj.DESCONOCIDA,
        orden=orden,
    )


def _permanencia_neutra(*, maximo_de_eventos: int = 10_000) -> Permanencia:
    return Permanencia(permanencia_s=0.0, muestras_minimas=1, maximo_de_eventos=maximo_de_eventos)


def _umbrales_segmentacion(**anulaciones: Any) -> UmbralesDeSegmentacion:
    """Copiado (no importado) de `test_segmentacion.py::_umbrales`: valores fijos
    de prueba, no leídos del fichero, para que un cambio del valor por omisión
    no vuelva esta suite verde o roja por accidente."""
    base: dict[str, Any] = {
        "rpm_arranque_min": 50.0,
        "rpm_motor_en_marcha": 500.0,
        "rpm_ralenti_max": 1400.0,
        "rpm_decel_min": 2000.0,
        "rpm_creciente_min_por_s": 100.0,
        "rpm_estable_max_por_s": 300.0,
        "tps_cerrada_entrada": 0.02,
        "tps_cerrada_salida": 0.05,
        "tps_wot_entrada": 0.80,
        "tps_wot_salida": 0.75,
        "ventana_derivada_s": 0.25,
        "ventana_validez_ms": 250.0,
        "histeresis_relativa": 0.02,
        "duracion_minima_s": dict.fromkeys((c.value for c in ClaseDeSegmento), 0.0),
    }
    duraciones = anulaciones.pop("duraciones", None)
    if duraciones is not None:
        base["duracion_minima_s"].update({c.value: d for c, d in duraciones.items()})
    base.update(anulaciones)
    return UmbralesDeSegmentacion.desde_mapa(base)


def _umbrales_anclaje(**over: Any) -> UmbralesDeAnclaje:
    base: dict[str, Any] = {
        "corte_umbral_min": 0.01,
        "maximo_de_eventos": 10_000,
        "umbrales_wot": _umbrales_segmentacion(duraciones={ClaseDeSegmento.WOT: 1.5}),
        "permanencia_wot_base": _permanencia_neutra(),
    }
    base.update(over)
    return UmbralesDeAnclaje(**base)


# --------------------------------------------------------------------------- #
# 1. Un segmento sin el evento no se resuelve con un desfase de 0 en silencio
# --------------------------------------------------------------------------- #
def test_segmento_sin_wot_queda_excluido_del_eje_y_explicado() -> None:
    """`B` reproduce la propiedad medida de `Log2768`/`Log2769`: mariposa que
    nunca supera el umbral de WOT (aquí 0,80), así que jamás hay un segmento
    WOT que anclar."""
    n = 60
    regimen_a = [3000.0] * 20 + list(np.linspace(3000.0, 6000.0, 40))
    mariposa_a = [0.2] * 20 + [0.9] * 40  # WOT desde la muestra 20, 2,0 s

    regimen_b = [3000.0] * n
    mariposa_b = [0.55] * n  # nunca cruza 0,80: sin WOT, como los logs reales

    seg_a, seg_b = _segmento("A", n), _segmento("B", n)
    series = {
        "A": {ROL_REGIMEN: _serie(regimen_a), ROL_MARIPOSA: _serie(mariposa_a)},
        "B": {ROL_REGIMEN: _serie(regimen_b), ROL_MARIPOSA: _serie(mariposa_b)},
    }
    informe = ancla_por_evento(
        [seg_a, seg_b], series, tipo_ancla=TipoAncla.PRIMER_WOT, umbrales=_umbrales_anclaje(), xp=np
    )

    assert informe.tiene_ancla("A")
    assert not informe.tiene_ancla("B")
    assert informe.eje is not None
    assert set(informe.eje.desfases) == {"A"}  # B NO está en el eje, ni con desfase 0
    motivos = {s.id_segmento: s.motivo for s in informe.sin_ancla}
    assert motivos == {"B": MotivoSinAncla.EVENTO_NO_OCURRIDO}
    assert "nunca ocurrió" in informe.sin_ancla[0].descripcion


def test_ningun_segmento_con_ancla_da_eje_none() -> None:
    n = 20
    seg = _segmento("A", n)
    series = {"A": {ROL_REGIMEN: _serie([3000.0] * n), ROL_MARIPOSA: _serie([0.3] * n)}}
    informe = ancla_por_evento(
        [seg], series, tipo_ancla=TipoAncla.PRIMER_WOT, umbrales=_umbrales_anclaje(), xp=np
    )
    assert informe.eje is None
    assert informe.instantes_ancla_ms == {}
    assert len(informe.sin_ancla) == 1
    assert informe.sin_ancla[0].motivo is MotivoSinAncla.EVENTO_NO_OCURRIDO


# --------------------------------------------------------------------------- #
# 2. El ancla cae exactamente en x = 0 para los segmentos incluidos
# --------------------------------------------------------------------------- #
def test_el_ancla_coincide_en_x_cero_en_todos_los_segmentos_incluidos() -> None:
    n = 40
    corte_a = [0.0] * 10 + [0.5] * 30  # primer corte en la muestra 10 (t=500 ms)
    corte_b = [0.0] * 25 + [0.5] * 15  # primer corte en la muestra 25 (t=1250 ms)

    seg_a, seg_b = _segmento("A", n), _segmento("B", n, orden=1)
    series = {"A": {ROL_CORTE: _serie(corte_a)}, "B": {ROL_CORTE: _serie(corte_b)}}
    informe = ancla_por_evento(
        [seg_a, seg_b],
        series,
        tipo_ancla=TipoAncla.PRIMER_CORTE,
        umbrales=_umbrales_anclaje(),
        xp=np,
    )

    assert informe.eje is not None
    assert informe.eje.modo is ModoDesfase.POR_EVENTO
    assert informe.eje.concatenado is False
    assert informe.eje.fronteras == ()
    assert informe.instantes_ancla_ms == {"A": 500.0, "B": 1250.0}
    # x = t_local + desfase: el instante del ancla de CADA segmento tiene que
    # caer en x = 0, que es justo lo que permite superponer dos cortes que
    # ocurrieron en instantes locales distintos.
    assert informe.eje.a_virtual("A", 0.500) == pytest.approx(0.0)
    assert informe.eje.a_virtual("B", 1.250) == pytest.approx(0.0)
    # Y todo lo demás se desplaza igual: 200 ms después del corte, en las dos.
    assert informe.eje.a_virtual("A", 0.700) == pytest.approx(0.2)
    assert informe.eje.a_virtual("B", 1.450) == pytest.approx(0.2)


# --------------------------------------------------------------------------- #
# 3. Confianza DIFUSA: por segmento, no global (docs/07 §7.15)
# --------------------------------------------------------------------------- #
def test_rol_ausente_se_declara_y_no_se_aproxima() -> None:
    n = 10
    seg = _segmento("A", n)
    informe = ancla_por_evento(
        [seg], {"A": {}}, tipo_ancla=TipoAncla.PRIMER_CORTE, umbrales=_umbrales_anclaje(), xp=np
    )
    assert informe.eje is None
    (sin_ancla,) = informe.sin_ancla
    assert sin_ancla.motivo is MotivoSinAncla.ROL_AUSENTE
    assert sin_ancla.roles_ausentes == (ROL_CORTE,)
    assert "no trae" in sin_ancla.descripcion


def test_rol_sin_confirmar_es_por_segmento_y_no_global() -> None:
    """Mismo log, mismo rol -- `cut_percentage` confirmado en `A` y sin
    confirmar en `B` -- y la tarea tiene que tratarlos distinto en la MISMA
    llamada: la confianza es una propiedad de cada log, no del conjunto."""
    n = 20
    corte = [0.0] * 5 + [0.5] * 15
    seg_a, seg_b = _segmento("A", n), _segmento("B", n, orden=1)
    series = {"A": {ROL_CORTE: _serie(corte)}, "B": {ROL_CORTE: _serie(corte)}}
    informe = ancla_por_evento(
        [seg_a, seg_b],
        series,
        tipo_ancla=TipoAncla.PRIMER_CORTE,
        umbrales=_umbrales_anclaje(),
        roles_sin_confirmar={"B": frozenset({ROL_CORTE})},
        xp=np,
    )
    assert informe.tiene_ancla("A")
    assert not informe.tiene_ancla("B")
    (sin_ancla,) = informe.sin_ancla
    assert sin_ancla.id_segmento == "B"
    assert sin_ancla.motivo is MotivoSinAncla.ROL_SIN_CONFIRMAR
    assert sin_ancla.roles_sin_confirmar == (ROL_CORTE,)
    assert "sin confirmar" in sin_ancla.descripcion


def test_rol_ausente_gana_a_sin_confirmar_cuando_no_esta_presente() -> None:
    """Un rol que no está no puede estar "sin confirmar" -- mismo criterio que
    `exclusion.excluir`: no hay nada que confirmar."""
    seg = _segmento("A", 10)
    informe = ancla_por_evento(
        [seg],
        {"A": {}},
        tipo_ancla=TipoAncla.PRIMER_CORTE,
        umbrales=_umbrales_anclaje(),
        roles_sin_confirmar={"A": frozenset({ROL_CORTE})},
        xp=np,
    )
    (sin_ancla,) = informe.sin_ancla
    assert sin_ancla.motivo is MotivoSinAncla.ROL_AUSENTE
    assert sin_ancla.roles_sin_confirmar == ()


# --------------------------------------------------------------------------- #
# 4. Reutilización: WOT es el de `segmentacion.py`, CORTE es el umbral de D14
#    sin la permanencia de detector
# --------------------------------------------------------------------------- #
def test_primer_wot_es_el_primer_segmento_wot_de_segmentacion() -> None:
    """Dos tramos de mariposa a fondo: el primero (15..34, 0,95 s) no llega a
    los 1,5 s mínimos de WOT y se descarta; el segundo (45..79, 1,7 s) sí
    sobrevive. El ancla tiene que ser el SEGUNDO, no el primero."""
    n = 80
    mariposa = [0.2] * 15 + [0.9] * 20 + [0.2] * 10 + [0.9] * 35
    regimen = (
        [3000.0] * 20  # idx 0..19: ralentí/crucero
        + list(np.linspace(3000.0, 4000.0, 20))  # idx 20..39: primer tramo de WOT (descartado)
        + [4000.0] * 5  # idx 40..44: mariposa cerrada de nuevo
        + list(np.linspace(4000.0, 6000.0, 35))  # idx 45..79: segundo tramo de WOT (el ancla)
    )
    assert len(mariposa) == n
    assert len(regimen) == n

    seg = _segmento("A", n)
    series = {"A": {ROL_REGIMEN: _serie(regimen), ROL_MARIPOSA: _serie(mariposa)}}
    informe = ancla_por_evento(
        [seg], series, tipo_ancla=TipoAncla.PRIMER_WOT, umbrales=_umbrales_anclaje(), xp=np
    )
    assert informe.tiene_ancla("A")
    # El primer tramo de WOT (15..34) dura 1,0 s: por debajo de 1,5 s, se
    # descarta. El segundo (45..79) sí sobrevive y empieza en la muestra 45.
    assert informe.instantes_ancla_ms["A"] == pytest.approx(45 * DT_MS)


def test_primer_corte_no_exige_la_permanencia_de_d14_como_detector() -> None:
    """`[detectores.D14].permanencia_s` (100 ms) NO se aplica aquí: una sola
    muestra activa cuenta, mismo motivo que `exclusion._condicion_corte`
    (`cut_percentage` es una salida directa de la ECU, no una lectura
    analógica ruidosa)."""
    n = 10
    # Un único pico de UNA muestra en cut_percentage.
    corte = [0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    seg = _segmento("A", n)
    informe = ancla_por_evento(
        [seg],
        {"A": {ROL_CORTE: _serie(corte)}},
        tipo_ancla=TipoAncla.PRIMER_CORTE,
        umbrales=_umbrales_anclaje(),
        xp=np,
    )
    assert informe.tiene_ancla("A")
    assert informe.instantes_ancla_ms["A"] == pytest.approx(2 * DT_MS)


def test_corte_por_debajo_del_umbral_no_ancla() -> None:
    n = 10
    corte = [0.005] * n  # por debajo de corte_umbral_min = 0,01
    seg = _segmento("A", n)
    informe = ancla_por_evento(
        [seg],
        {"A": {ROL_CORTE: _serie(corte)}},
        tipo_ancla=TipoAncla.PRIMER_CORTE,
        umbrales=_umbrales_anclaje(),
        xp=np,
    )
    assert not informe.tiene_ancla("A")
    assert informe.sin_ancla[0].motivo is MotivoSinAncla.EVENTO_NO_OCURRIDO


# --------------------------------------------------------------------------- #
# 5. LANZAMIENTO: sin umbral no se adivina
# --------------------------------------------------------------------------- #
def test_lanzamiento_sin_umbral_definido_se_rechaza_explicitamente() -> None:
    seg = _segmento("A", 10)
    series = {"A": {ROL_LANZAMIENTO: _serie([0.0] * 10)}}
    with pytest.raises(ErrorDeAnclaje, match="lanzamiento_activo_min"):
        ancla_por_evento(
            [seg], series, tipo_ancla=TipoAncla.LANZAMIENTO, umbrales=_umbrales_anclaje(), xp=np
        )


def test_lanzamiento_con_umbral_explicito_funciona() -> None:
    n = 20
    launch = [-101.0] * 5 + [1.0] * 15  # código "activo" decidido por quien llama, no por el módulo
    seg = _segmento("A", n)
    umbrales = _umbrales_anclaje(lanzamiento_activo_min=1.0)
    informe = ancla_por_evento(
        [seg],
        {"A": {ROL_LANZAMIENTO: _serie(launch)}},
        tipo_ancla=TipoAncla.LANZAMIENTO,
        umbrales=umbrales,
        xp=np,
    )
    assert informe.tiene_ancla("A")
    assert informe.instantes_ancla_ms["A"] == pytest.approx(5 * DT_MS)


def test_lanzamiento_umbral_fuera_de_rango_plausible_se_rechaza() -> None:
    with pytest.raises(ErrorDeAnclaje, match="rango plausible"):
        _umbrales_anclaje(lanzamiento_activo_min=50.0)


# --------------------------------------------------------------------------- #
# 6. Usos incorrectos: excepción, no una alineación plausible y falsa
# --------------------------------------------------------------------------- #
def test_lista_de_segmentos_vacia_es_un_error() -> None:
    with pytest.raises(ErrorDeAnclaje):
        ancla_por_evento(
            [], {}, tipo_ancla=TipoAncla.PRIMER_CORTE, umbrales=_umbrales_anclaje(), xp=np
        )


def test_ids_de_segmento_repetidos_es_un_error() -> None:
    seg_a1 = _segmento("A", 10)
    seg_a2 = _segmento("A", 10, orden=1)
    with pytest.raises(ErrorDeAnclaje, match="repetido"):
        ancla_por_evento(
            [seg_a1, seg_a2],
            {"A": {ROL_CORTE: _serie([0.0] * 10)}},
            tipo_ancla=TipoAncla.PRIMER_CORTE,
            umbrales=_umbrales_anclaje(),
            xp=np,
        )


def test_serie_que_no_es_clase_punto_es_un_error() -> None:
    from dlv_core.primitivas import derivada

    n = 10
    seg = _segmento("A", n)
    tasa = derivada(_serie([0.0] * n), ventana_s=0.1, xp=np)
    with pytest.raises(ErrorDeAnclaje, match="PUNTO"):
        ancla_por_evento(
            [seg],
            {"A": {ROL_CORTE: tasa}},
            tipo_ancla=TipoAncla.PRIMER_CORTE,
            umbrales=_umbrales_anclaje(),
            xp=np,
        )


def test_umbral_de_corte_fuera_de_fraccion_es_un_error() -> None:
    with pytest.raises(ErrorDeAnclaje, match="FRACCIÓN"):
        _umbrales_anclaje(corte_umbral_min=1.5)


# --------------------------------------------------------------------------- #
# 7. Ni un umbral cableado (regla 3 de CLAUDE.md)
# --------------------------------------------------------------------------- #
def test_el_modulo_no_contiene_los_umbrales_cableados() -> None:
    """Inspección de los literales del módulo (mismo procedimiento que
    `test_exclusion.py` y `test_segmentacion.py`): los dos escalares que este
    módulo reutiliza de `data/umbrales.toml` (D14 y `[motor_de_deteccion]`) no
    pueden aparecer como constantes en el código."""
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    prohibidos = {
        float(bruto["detectores"]["D14"]["umbral_min"]),
        float(bruto["motor_de_deteccion"]["maximo_de_eventos"]),
    }
    # 0 y 1 no cuentan: el módulo los usa para `entrada=salida` (histéresis
    # desactivada a propósito), para contar muestras mínimas y para los
    # límites [0, 1] de la validación de fracción -- no como copia de un
    # umbral físico.
    prohibidos -= {0.0, 1.0}
    assert len(prohibidos) == 2, "las secciones reutilizadas han dejado de declarar sus umbrales"
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"), filename=str(MODULO))
    encontrados = sorted(
        {
            float(n.value)
            for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
            if not isinstance(n.value, bool) and float(n.value) in prohibidos
        }
    )
    assert not encontrados, f"umbrales de data/umbrales.toml cableados en el módulo: {encontrados}"


def _mapa_real() -> dict[str, Any]:
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    return {
        "corte_umbral_min": bruto["detectores"]["D14"]["umbral_min"],
        "maximo_de_eventos": bruto["motor_de_deteccion"]["maximo_de_eventos"],
    }


def test_los_umbrales_reales_cargan_y_coinciden_con_d14_y_motor_de_deteccion() -> None:
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    umbrales = UmbralesDeAnclaje.desde_mapa(
        _mapa_real(),
        umbrales_wot=_umbrales_segmentacion(duraciones={ClaseDeSegmento.WOT: 1.5}),
        permanencia_wot_base=_permanencia_neutra(),
    )
    assert umbrales.corte_umbral_min == pytest.approx(bruto["detectores"]["D14"]["umbral_min"])
    assert umbrales.maximo_de_eventos == bruto["motor_de_deteccion"]["maximo_de_eventos"]
    assert umbrales.lanzamiento_activo_min is None  # sin sección [anclaje]: no se adivina


def test_desde_mapa_falla_si_falta_una_clave() -> None:
    with pytest.raises(ErrorDeAnclaje):
        UmbralesDeAnclaje.desde_mapa(
            {"corte_umbral_min": 0.01},
            umbrales_wot=_umbrales_segmentacion(),
            permanencia_wot_base=_permanencia_neutra(),
        )


# --------------------------------------------------------------------------- #
# 8. ADR-009: nada de `for`/`while` sobre muestras
# --------------------------------------------------------------------------- #
def test_adr009_sin_bucle_sobre_muestras() -> None:
    """Los únicos `for` del módulo recorren `segmentos` (unos pocos logs), en
    `_comprobar_ids_unicos` y en `ancla_por_evento`. Comprobado sobre el AST:
    cualquier bucle nuevo que itere sobre un array de datos tiene que declarar
    explícitamente por qué no es sobre muestras, y esta prueba obliga a esa
    revisión."""
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"), filename=str(MODULO))
    bucles = [n for n in ast.walk(arbol) if isinstance(n, (ast.For, ast.While))]
    assert len(bucles) == 2, (
        f"se esperaban dos bucles sobre listas de segmentos, hay {len(bucles)}: revisa que "
        "ninguno itere sobre un array de muestras"
    )
