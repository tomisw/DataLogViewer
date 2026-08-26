"""Pruebas de los filtros de exclusión para agregados (F4-03, `docs/04` §4.6).

QUÉ PROTEGE ESTA SUITE, ORDENADO POR CONSECUENCIA SI SE ROMPE
=============================================================
1. **Un filtro que no se puede calcular no se cuenta como «nada que excluir»**:
   es la advertencia de la propia tarea («un filtro que silenciosamente no
   excluye nada es peor que uno ausente»), así que `no_aplicadas` tiene que
   aparecer con el rol exacto, tanto por rol ausente como por rol sin
   confirmar, y las dos por separado.
2. **CORTE y PROTECCION_MOTOR no aplican la permanencia mínima de su detector
   equivalente**: una muestra aislada de corte real tiene que excluirse, no
   perderse por debajo de `[detectores.D14].permanencia_s`.
3. **TRANSITORIO y RETARDO_TRANSPORTE_LAMBDA comparten el mismo disparo** (la
   derivada de mariposa) y solo difieren en cuánto dura la exclusión después:
   el segundo tiene que ser un subconjunto temprano del primero cuando
   `retardo_transporte_lambda_ms` < `transitorio_ventana_s` en segundos, que es
   la configuración real del fichero (150 ms contra 500 ms).
4. **Ni un umbral cableado** (regla 3): un umbral de `data/umbrales.toml`
   escrito directamente en el módulo se desincroniza sin que ninguna prueba
   funcional lo note; se busca en el AST, no en el texto.
5. **La sección real de `data/umbrales.toml` (repartida en cuatro secciones)
   carga y coincide con lo que dice cada una**, para que un cambio futuro de
   cualquiera de los cuatro valores reutilizados se note aquí sin tener que
   leer `dlv_core/exclusion.py`.
6. **Ni un bucle por muestra** (ADR-009), por patrón.

Esta suite ejercita el módulo con NumPy real, no con la implementación de
biblioteca estándar del protocolo `Vectorial` que usan `test_primitivas.py`,
`test_malla.py` y `test_segmentacion.py`. Es una divergencia deliberada de esa
convención por el tamaño de la tarea, y está anotada en el informe de F4-03:
si alguna función de este módulo usara una operación de NumPy fuera del
protocolo `Vectorial` documentado, esta suite no lo detectaría.
"""

from __future__ import annotations

import ast
import inspect
import tomllib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from dlv_core.exclusion import (
    ROL_CORTE,
    ROL_MARIPOSA,
    ROL_PROTECCION,
    ErrorDeExclusion,
    FiltroNoAplicado,
    InformeDeExclusion,
    RazonDeExclusion,
    UmbralesDeExclusion,
    excluir,
)
from dlv_core.primitivas import Serie
from dlv_core.unidades import Clase

RAIZ = Path(__file__).resolve().parent.parent.parent
UMBRALES_TOML = RAIZ / "data" / "umbrales.toml"
MODULO = RAIZ / "dlv-core" / "src" / "dlv_core" / "exclusion.py"

PASO_MS = 50.0


def _t(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float64) * PASO_MS


def _serie(v: list[float] | np.ndarray, *, t: np.ndarray | None = None) -> Serie:
    v = np.asarray(v, dtype=np.float64)
    return Serie(t_ms=t if t is not None else _t(len(v)), v=v, clase=Clase.PUNTO)


def _umbrales(**over: float) -> UmbralesDeExclusion:
    base = {
        "transitorio_derivada_tps_min_por_s": 2.0,
        "transitorio_ventana_s": 0.5,
        "retardo_transporte_lambda_ms": 150.0,
        "corte_umbral_min": 0.01,
        "proteccion_umbral_min": 1.0,
        "ventana_derivada_tps_s": 0.25,
        "ventana_validez_ms": 250.0,
    }
    base.update(over)
    return UmbralesDeExclusion.desde_mapa(base)


# --------------------------------------------------------------------------- #
# 1. Un rol que falta, o que llega sin confirmar, se DICE y no se aproxima
# --------------------------------------------------------------------------- #
def test_sin_ningun_rol_los_cuatro_motivos_quedan_no_aplicados() -> None:
    informe = excluir({}, _t(10), umbrales=_umbrales())
    assert informe.por_razon == {}
    assert {na.razon for na in informe.no_aplicadas} == set(RazonDeExclusion)
    for na in informe.no_aplicadas:
        assert na.roles_ausentes and not na.roles_sin_confirmar


def test_falta_solo_cut_percentage_y_solo_corte_queda_no_aplicado() -> None:
    n = 10
    series = {
        ROL_MARIPOSA: _serie([0.2] * n),
        ROL_PROTECCION: _serie([0.0] * n),
    }
    informe = excluir(series, _t(n), umbrales=_umbrales())
    no_aplicados = {na.razon for na in informe.no_aplicadas}
    assert no_aplicados == {RazonDeExclusion.CORTE}
    assert RazonDeExclusion.PROTECCION_MOTOR in informe.por_razon
    assert RazonDeExclusion.TRANSITORIO in informe.por_razon


def test_un_rol_sin_confirmar_desactiva_su_motivo_y_lo_dice(_recwarn: None = None) -> None:
    """Decisión 3 del informe: una coincidencia DIFUSA no activa un filtro por
    su cuenta, ni para excluir ni para dejar de excluir -- mismo criterio de
    tres estados que F3-08 (`activacion_detectores`)."""
    n = 10
    series = {
        ROL_MARIPOSA: _serie([0.2] * n),
        ROL_CORTE: _serie([0.0] * n),
        ROL_PROTECCION: _serie([0.0] * n),
    }
    informe = excluir(
        series, _t(n), umbrales=_umbrales(), roles_sin_confirmar=frozenset({ROL_CORTE})
    )
    afectados = {na.razon: na for na in informe.no_aplicadas}
    assert afectados.keys() == {RazonDeExclusion.CORTE}
    assert afectados[RazonDeExclusion.CORTE].roles_ausentes == ()
    assert afectados[RazonDeExclusion.CORTE].roles_sin_confirmar == (ROL_CORTE,)
    assert "sin confirmar" in afectados[RazonDeExclusion.CORTE].motivo
    # Los otros tres motivos, con sus roles confirmados, se calculan igual.
    assert RazonDeExclusion.PROTECCION_MOTOR in informe.por_razon
    assert RazonDeExclusion.TRANSITORIO in informe.por_razon


def test_rol_ausente_y_sin_confirmar_no_se_cuenta_dos_veces() -> None:
    """Un rol ausente no está «sin confirmar»: no está. Contarlo en las dos
    listas pediría confirmar un rol que el log no trae."""
    informe = excluir({}, _t(5), umbrales=_umbrales(), roles_sin_confirmar=frozenset({ROL_CORTE}))
    corte = next(na for na in informe.no_aplicadas if na.razon is RazonDeExclusion.CORTE)
    assert corte.roles_ausentes == (ROL_CORTE,)
    assert corte.roles_sin_confirmar == ()


def test_un_motivo_no_aplicado_no_se_cuenta_como_nada_que_excluir() -> None:
    """La advertencia de la propia tarea: un filtro que no se pudo calcular no
    puede parecer «se calculó y no hay nada que excluir». Con ÚNICAMENTE
    protección de motor calculable y activa en dos muestras, la máscara
    combinada tiene que reflejar esas dos, no la ausencia de las otras tres."""
    n = 10
    prot = [0.0] * n
    prot[3] = 2.0
    prot[4] = 2.0
    series = {ROL_PROTECCION: _serie(prot)}
    informe = excluir(series, _t(n), umbrales=_umbrales())
    assert len(informe.no_aplicadas) == 3
    activos = np.nonzero(informe.excluir.activa & informe.excluir.valido)[0]
    assert list(activos) == [3, 4]


# --------------------------------------------------------------------------- #
# 2. CORTE y PROTECCION_MOTOR: sin permanencia, muestra a muestra
# --------------------------------------------------------------------------- #
def test_corte_excluye_una_sola_muestra_aislada() -> None:
    """A diferencia de D14 (permanencia 100 ms), aquí un pico de una sola
    muestra se excluye: `cut_percentage` es una salida directa de la ECU, no
    una lectura analógica ruidosa que necesite debounce."""
    n = 10
    cut = [0.0] * n
    cut[5] = 0.5
    series = {ROL_CORTE: _serie(cut)}
    informe = excluir(series, _t(n), umbrales=_umbrales())
    cond = informe.por_razon[RazonDeExclusion.CORTE]
    activos = np.nonzero(cond.activa & cond.valido)[0]
    assert list(activos) == [5]


def test_corte_por_debajo_del_umbral_no_excluye() -> None:
    n = 5
    series = {ROL_CORTE: _serie([0.0, 0.005, 0.0, 0.0, 0.0])}
    informe = excluir(series, _t(n), umbrales=_umbrales())
    cond = informe.por_razon[RazonDeExclusion.CORTE]
    assert not np.any(cond.activa & cond.valido)


def test_proteccion_motor_umbral_es_nivel_uno() -> None:
    n = 6
    prot = [0.0, 0.0, 1.0, 3.0, 0.0, 0.0]
    series = {ROL_PROTECCION: _serie(prot)}
    informe = excluir(series, _t(n), umbrales=_umbrales())
    cond = informe.por_razon[RazonDeExclusion.PROTECCION_MOTOR]
    assert list(np.nonzero(cond.activa & cond.valido)[0]) == [2, 3]


# --------------------------------------------------------------------------- #
# 3. TRANSITORIO y RETARDO_TRANSPORTE_LAMBDA: mismo disparo, distinta ventana
# --------------------------------------------------------------------------- #
def _tps_con_tip_in(n: int, indice_salto: int) -> list[float]:
    tps = [0.2] * n
    for i in range(indice_salto, n):
        tps[i] = 0.9
    return tps


def test_transitorio_dura_mas_que_retardo_de_transporte_con_los_valores_reales() -> None:
    """Con los valores por omisión del fichero (500 ms contra 150 ms), el
    mismo tip-in tiene que dejar TRANSITORIO activo más tiempo que
    RETARDO_TRANSPORTE_LAMBDA, y el segundo tiene que ser un PREFIJO temprano
    del primero: los dos comparten el disparo, solo cambia cuánto se sostiene."""
    n = 60
    salto = 20
    series = {ROL_MARIPOSA: _serie(_tps_con_tip_in(n, salto))}
    informe = excluir(series, _t(n), umbrales=_umbrales())

    transitorio = informe.por_razon[RazonDeExclusion.TRANSITORIO]
    retardo = informe.por_razon[RazonDeExclusion.RETARDO_TRANSPORTE_LAMBDA]
    idx_transitorio = set(np.nonzero(transitorio.activa & transitorio.valido)[0].tolist())
    idx_retardo = set(np.nonzero(retardo.activa & retardo.valido)[0].tolist())

    assert idx_retardo, "el tip-in tiene que disparar el retardo de transporte"
    assert idx_transitorio, "el tip-in tiene que disparar el transitorio"
    assert idx_retardo.issubset(idx_transitorio)
    assert len(idx_transitorio) > len(idx_retardo)
    # Ninguno de los dos puede empezar antes del propio salto: no hay ventana
    # que mire al futuro.
    assert min(idx_transitorio) == salto
    assert min(idx_retardo) == salto


def test_una_mariposa_estable_no_dispara_nada() -> None:
    n = 40
    series = {ROL_MARIPOSA: _serie([0.35] * n)}
    informe = excluir(series, _t(n), umbrales=_umbrales())
    for razon in (RazonDeExclusion.TRANSITORIO, RazonDeExclusion.RETARDO_TRANSPORTE_LAMBDA):
        cond = informe.por_razon[razon]
        assert not np.any(cond.activa & cond.valido)


def test_un_tip_out_dispara_igual_que_un_tip_in() -> None:
    """Valor absoluto de la derivada: un cierre brusco (tip-out, DFCO)
    perturba la mezcla y el sensor de λ igual que una apertura brusca."""
    n = 40
    tps = [0.9] * 15 + [0.1] * 25  # cierre brusco en el índice 15
    series = {ROL_MARIPOSA: _serie(tps)}
    informe = excluir(series, _t(n), umbrales=_umbrales())
    cond = informe.por_razon[RazonDeExclusion.TRANSITORIO]
    assert np.any(cond.activa[15:20] & cond.valido[15:20])


# --------------------------------------------------------------------------- #
# 4. La máscara combinada es un OR de los motivos calculables
# --------------------------------------------------------------------------- #
def test_excluir_combinado_es_la_union_de_los_cuatro_motivos() -> None:
    n = 30
    cut = [0.0] * n
    cut[2] = 1.0
    prot = [0.0] * n
    prot[10] = 2.0
    tps = _tps_con_tip_in(n, 20)
    series = {
        ROL_MARIPOSA: _serie(tps),
        ROL_CORTE: _serie(cut),
        ROL_PROTECCION: _serie(prot),
    }
    informe = excluir(series, _t(n), umbrales=_umbrales())
    assert informe.no_aplicadas == ()
    activos = set(np.nonzero(informe.excluir.activa & informe.excluir.valido)[0].tolist())
    assert 2 in activos
    assert 10 in activos
    assert 20 in activos  # el propio salto de mariposa
    assert informe.fraccion_excluida() == pytest.approx(len(activos) / n)


def test_una_muestra_excluida_por_dos_motivos_a_la_vez_no_se_duplica() -> None:
    n = 10
    cut = [0.0] * n
    cut[4] = 1.0
    prot = [0.0] * n
    prot[4] = 2.0
    series = {ROL_CORTE: _serie(cut), ROL_PROTECCION: _serie(prot)}
    informe = excluir(series, _t(n), umbrales=_umbrales())
    assert list(np.nonzero(informe.excluir.activa & informe.excluir.valido)[0]) == [4]


# --------------------------------------------------------------------------- #
# 5. Configuración: sin valores por omisión, y ninguna clave se ignora
# --------------------------------------------------------------------------- #
def test_falta_una_clave_y_falla_en_vez_de_suponerla() -> None:
    mapa = {"corte_umbral_min": 0.01}
    with pytest.raises(ErrorDeExclusion, match="proteccion_umbral_min"):
        UmbralesDeExclusion.desde_mapa(mapa)


def test_una_anulacion_mal_escrita_no_se_ignora_en_silencio() -> None:
    with pytest.raises(ErrorDeExclusion, match="desconocidas"):
        _umbrales().fusionar({"corte_umbral": 0.02})


def test_la_precedencia_por_canal_gana_al_fichero() -> None:
    del_fichero = _umbrales()
    por_canal = del_fichero.fusionar({"corte_umbral_min": 0.5})
    n = 5
    series = {ROL_CORTE: _serie([0.2, 0.0, 0.0, 0.0, 0.0])}
    informe_fichero = excluir(series, _t(n), umbrales=del_fichero)
    informe_canal = excluir(series, _t(n), umbrales=por_canal)
    assert np.any(
        informe_fichero.por_razon[RazonDeExclusion.CORTE].activa
        & informe_fichero.por_razon[RazonDeExclusion.CORTE].valido
    )
    assert not np.any(
        informe_canal.por_razon[RazonDeExclusion.CORTE].activa
        & informe_canal.por_razon[RazonDeExclusion.CORTE].valido
    )


@pytest.mark.parametrize(
    ("anulacion", "trozo"),
    [
        ({"transitorio_derivada_tps_min_por_s": 0.0}, "transitorio_derivada_tps_min_por_s"),
        ({"transitorio_ventana_s": 0.0}, "transitorio_ventana_s"),
        ({"retardo_transporte_lambda_ms": -1.0}, "retardo_transporte_lambda_ms"),
        ({"corte_umbral_min": 1.5}, "FRACCIÓN"),
        ({"corte_umbral_min": -0.1}, "FRACCIÓN"),
        ({"proteccion_umbral_min": 0.0}, "proteccion_umbral_min"),
        ({"ventana_derivada_tps_s": 0.0}, "ventana_derivada_tps_s"),
        ({"ventana_validez_ms": -1.0}, "ventana_validez_ms"),
    ],
)
def test_una_configuracion_incoherente_se_rechaza_por_su_nombre(
    anulacion: dict[str, float], trozo: str
) -> None:
    with pytest.raises(ErrorDeExclusion, match=trozo):
        _umbrales(**anulacion)


def test_una_serie_ya_derivada_se_rechaza_como_trampa_del_delta() -> None:
    from dlv_core.primitivas import derivada

    n = 10
    mariposa_punto = _serie([0.2] * n)
    ya_derivada = derivada(mariposa_punto, ventana_s=0.25)
    with pytest.raises(ErrorDeExclusion, match="PUNTO"):
        excluir({ROL_MARIPOSA: ya_derivada}, _t(n), umbrales=_umbrales())


# --------------------------------------------------------------------------- #
# 6. Ningún valor por omisión numérico en la API pública (regla 3)
# --------------------------------------------------------------------------- #
def test_ningun_parametro_numerico_de_la_api_tiene_valor_por_omision() -> None:
    publicos = [UmbralesDeExclusion, FiltroNoAplicado, InformeDeExclusion, excluir]
    for objeto in publicos:
        for nombre, p in inspect.signature(objeto).parameters.items():
            if p.default is inspect.Parameter.empty:
                continue
            assert not isinstance(p.default, (int, float)) or isinstance(p.default, bool), (
                f"{objeto.__name__}.{nombre} tiene el valor por omisión numérico "
                f"{p.default!r}: eso es una copia de un umbral de data/umbrales.toml "
                "que puede desincronizarse en silencio"
            )


def test_el_modulo_no_contiene_los_umbrales_cableados() -> None:
    """Inspección de los literales del módulo, deliberadamente literal (mismo
    procedimiento que `test_segmentacion.py`).

    Los umbrales de este módulo están repartidos en CUATRO secciones de
    `data/umbrales.toml` (D13, D14, D15, `[segmentacion]`, `[motor_de_deteccion]`
    y `[exclusion]`), así que la lista de «prohibidos» se construye leyendo las
    seis, no solo `[exclusion]`.
    """
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    prohibidos = {
        float(bruto["detectores"]["D13"]["umbral_min"]),
        float(bruto["detectores"]["D14"]["umbral_min"]),
        float(bruto["detectores"]["D15"]["derivada_tps_min_por_s"]),
        float(bruto["detectores"]["D15"]["ventana_s"]),
        float(bruto["segmentacion"]["ventana_derivada_s"]),
        float(bruto["motor_de_deteccion"]["ventana_validez_ms"]),
        float(bruto["exclusion"]["retardo_transporte_lambda_ms"]),
    }
    # 0 y 1 no cuentan: el módulo los usa para contar, para el `> 0` del
    # indicador sostenido y para los límites [0, 1] de la validación de
    # fracción, no como copia de un umbral físico.
    prohibidos -= {0.0, 1.0}
    assert len(prohibidos) >= 5, "las secciones reutilizadas han dejado de declarar sus umbrales"
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


# --------------------------------------------------------------------------- #
# 7. Contra la sección real de data/umbrales.toml
# --------------------------------------------------------------------------- #
def _mapa_real() -> dict[str, Any]:
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    return {
        "transitorio_derivada_tps_min_por_s": bruto["detectores"]["D15"]["derivada_tps_min_por_s"],
        "transitorio_ventana_s": bruto["detectores"]["D15"]["ventana_s"],
        "corte_umbral_min": bruto["detectores"]["D14"]["umbral_min"],
        "proteccion_umbral_min": bruto["detectores"]["D13"]["umbral_min"],
        "ventana_derivada_tps_s": bruto["segmentacion"]["ventana_derivada_s"],
        "ventana_validez_ms": bruto["motor_de_deteccion"]["ventana_validez_ms"],
        "retardo_transporte_lambda_ms": bruto["exclusion"]["retardo_transporte_lambda_ms"],
    }


def test_los_umbrales_reales_cargan_y_coinciden_con_sus_cuatro_secciones() -> None:
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    umbrales = UmbralesDeExclusion.desde_mapa(_mapa_real())
    assert umbrales.corte_umbral_min == pytest.approx(bruto["detectores"]["D14"]["umbral_min"])
    assert umbrales.proteccion_umbral_min == pytest.approx(bruto["detectores"]["D13"]["umbral_min"])
    assert umbrales.transitorio_derivada_tps_min_por_s == pytest.approx(
        bruto["detectores"]["D15"]["derivada_tps_min_por_s"]
    )
    assert umbrales.transitorio_ventana_s == pytest.approx(bruto["detectores"]["D15"]["ventana_s"])
    assert umbrales.ventana_derivada_tps_s == pytest.approx(
        bruto["segmentacion"]["ventana_derivada_s"]
    )
    assert umbrales.retardo_transporte_lambda_ms == pytest.approx(150.0)  # docs/04 §4.6, literal


# --------------------------------------------------------------------------- #
# 8. ADR-009: nada de `for` sobre muestras
# --------------------------------------------------------------------------- #
def test_adr009_sin_bucle_sobre_muestras() -> None:
    """Los únicos `for`/`while` del módulo recorren `RazonDeExclusion` (cuatro
    elementos) o listas de umbrales/claves de longitud fija, nunca un array de
    muestras. Comprobado sobre el AST: cualquier bucle nuevo que itere sobre un
    array de datos tiene que declarar explícitamente por qué no es sobre
    muestras, y esta prueba obliga a esa revisión."""
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"), filename=str(MODULO))
    bucles = [n for n in ast.walk(arbol) if isinstance(n, (ast.For, ast.While))]
    # Cuatro bucles esperados: sobre RazonDeExclusion (excluir), sobre
    # _CLAVES_ESCALARES (desde_mapa y fusionar, dos veces) y sobre
    # condiciones.values() (_combinar).
    assert 1 <= len(bucles) <= 8, (
        f"se esperaban unos pocos bucles sobre colecciones de tamaño fijo, hay {len(bucles)}: "
        "revisa que ninguno itere sobre un array de muestras"
    )
