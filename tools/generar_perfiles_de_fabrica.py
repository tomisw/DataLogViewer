#!/usr/bin/env python3
"""Genera los diez perfiles de fábrica de `docs/04-perfiles-motorsport.md`
§4.2 (tarea F3-03), como diez ficheros `.dlvprofile` en `data/perfiles/`.

POR QUÉ UN GENERADOR Y NO DIEZ JSON ESCRITOS A MANO
====================================================
`.dlvprofile` es JSON versionado (F3-01, `dlv_core.perfil`), y JSON no admite
comentarios. La regla del proyecto -- «los comentarios son lo que hace
revisable la puerta G1» -- no puede cumplirse dentro del propio `.dlvprofile`,
así que este script es donde vive el PORQUÉ de cada elección; los diez
ficheros de `data/perfiles/` son su salida determinista. Además, construir los
perfiles con `dlv_core.perfil.Perfil` en vez de escribir el JSON a mano da ida
y vuelta gratis: si un perfil no es serializable, este script falla antes de
escribir nada (ver `_escribir`).

Se ejecuta una sola vez por cambio; no es parte del paquete instalado, igual
que `generar_verdad.py` o `generar_corpus.py`.

    python tools/generar_perfiles_de_fabrica.py

CONTRA QUÉ CATÁLOGO SE CONSTRUYÓ
=================================
`data/roles.toml` en su versión de 112 roles (ampliación 2026-08-26, F0-10),
NO la de 58 roles que tenía `dlv-core/tests/test_perfil.py` cuando F3-01
construyó sus versiones "representativas" de estos mismos diez perfiles. Ese
detalle importa: varios perfiles que en F3-01 dependían casi enteros de
`id_nativo` (P3, P4, la mitad de P6, la mayoría de P7) tienen ahora rol
universal para la mayoría de sus canales. Este script recoge esa mejora; el
informe de la tarea F3-03 cuantifica cuánto cambió.

CADA `id_nativo` DE ESTE FICHERO ES UN CANAL REAL, VERIFICADO
================================================================
Ninguno se inventa: cada cadena de `id_nativo` se comprobó contra
`grep "^Channel : "` sobre `samples/real/AutoLog_20260729_1830.csv` antes de
escribirse aquí. Es la misma exigencia que `docs/09` §9.7 regla 5 protege para
`samples/real/`: ese log es la evidencia, y un `id_nativo` que no está en él es
una adivinanza con forma de dato.

TRES COSAS QUE ESTE CATÁLOGO TODAVÍA NO RESUELVE, Y QUE F3-03 NO ARREGLA
==========================================================================
(no se toca `data/roles.toml` en esta tarea -- eso es F0-10 -- pero hay que
dejarlas escritas para que la ampliación futura sepa qué mirar)

1. ROLES QUE COLAPSAN DOS CANALES REALES DISTINTOS EN UNO
   Varios roles nuevos de la ampliación 2026-08-26 tienen, entre sus propios
   sinónimos, DOS nombres de canal que existen los dos a la vez en el AutoLog
   real -- no son alias del mismo canal en fabricantes distintos, son dos
   canales *de Haltech* con papeles distintos que cayeron en el mismo rol:

     - `boost_pressure_target`: "Boost Control Target Pressure" Y
       "...Target Pressure (Corrected)"
     - `boost_output`: "Boost Control Output" Y
       "...Solenoid Duty Cycle"
     - `ignition_correction_transient`: "Transient Throttle Ignition
       Correction" Y "...Current Ignition Correction"
     - `trigger_sync_state`: "Trigger Sync Level Status" Y
       "Trigger Synchronisation State"
     - `trigger_tooth_period_error`: "Tooth Period At Error" Y
       "Previous Tooth Period At Error"
     - `home_travel_pct`: "Home percentage of valid travel" Y
       "Worst Home percentage of valid travel"
     - `limiter_active`: "RPM Limiter Active" Y "Engine Limiter Active"
     - `knock_level`: "Knock Sensor N Knock Level" Y
       "Knock Sensor N Knock Signal"
     - `vehicle_speed`: "Vehicle Speed" Y "Vehicle Speed Drive Train Sensor"

   `ElementoDePanel` prohíbe dos elementos con la misma clave (rol, índice)
   dentro de un panel, así que estos perfiles solo pueden declarar UN
   elemento por rol -- el importador elige cuál de los dos canales reales lo
   resuelve, y `_indexar_asignaciones` (aplicar_perfil.py) desempata por
   `Confianza` y, si empatan, por orden de llegada. No es un defecto de esta
   tarea: es un defecto potencial del catálogo de roles que esta tarea
   DESCUBRE al intentar expresar los diez perfiles con roles reales, y que
   corresponde arreglar a quien mantenga `data/roles.toml` (separar cada par
   en dos roles, o documentar cuál de los dos es el preferido).

2. CANALES SIN ROL UNIVERSAL TODAVÍA (LA RESERVA A id_nativo SIGUE VIVA AQUÍ)
   Quedan tras la ampliación 2026-08-26, agrupados por perfil -- es la lista
   que alimenta la próxima ronda de F0-10 (nombre del rol propuesto entre
   paréntesis, a discreción de quien amplíe el catálogo):

     P1  "Fuel MAP Correction", "Fuel Coolant Temperature Correction",
         "Decel Cut State" (enum)
     P2  "Knock Control Bank {n} Long Term Trim" (indexado),
         "Knock State" (enum), "Knock Detection Active State" (enum)
     P3  ninguno -- portable al 100 % con el catálogo actual
     P4  "Ignition {n} Duty Cycle" (indexado; distinto de injector_duty)
     P5  "Throttle Position Derivative", "Transient Throttle Load
         Derivative", "...Fuel Enrichment Rate", "...Fuel Disenrichment
         Rate", "...Enrichment Load Derivative", "...Disenrichment Load
         Derivative", "...Enrichment Start Load" -- siete canales, el
         perfil más dependiente de id_nativo que queda
     P6  "Idle Control Proportional/Integral/Derivative Output" (los
         TÉRMINOS del lazo; las GANANCIAS ya tienen rol: idle_gain_*),
         "Thermofan {n} Idle Up Active" (indexado), "Air Con Idle Up Active"
     P7  "Sync Offset Difference At Error", "Home Tooth Count At Error" --
         de trece canales que citaba F3-01 como dependientes de id_nativo,
         quedan DOS: es el perfil que más mejoró con la ampliación
     P8  "Engine Protection Ignition Retard", "...Boost Correction",
         "...Lambda Fuel Enrichment" (los tres desgloses de la causa de
         protección; el nivel y la máscara sí tienen rol)
     P9  "Synced Pulse Input {n} Voltage" (indexado, 4 canales)
     P10 "Launch Control Fuel Correction"

3. UN CANAL MATEMÁTICO NO ES UN CANAL DE FORMATO
   «λ error» (docs/04 §4.5) no es un canal de ningún log: lo calcula la propia
   app. No hay mecanismo de rol para un canal calculado (eso es de la
   biblioteca de canales matemáticos, fuera del alcance de F3-01/F3-02/F3-03),
   así que P1 lo referencia con `id_nativo="lambda_error"` como marcador de
   posición hasta que exista ese mecanismo. Es una reserva DISTINTA de la de
   `id_nativo` para canales de fabricante: aquí no hay ningún fabricante que
   vaya a escribir jamás un canal con ese nombre.

QUÉ VALORES DE §4.2 NO SE EXPRESARON, Y POR QUÉ
==================================================
`docs/04` §4.2 describe alertas y métricas para varios perfiles sin darles un
número de detector (D1..D18) ni un valor en `data/umbrales.toml`: la alerta de
P4 («avance total distinto de base + suma de correcciones»), las métricas de
P3 por tirada (sobreoscilación, tiempo de establecimiento, error estacionario,
saturación -- estas SÍ tienen números en `[boost_pid]` de
`data/umbrales.toml`, pero son parámetros de un algoritmo de F4-09, no un
límite de un rol) y las de P6 (RMS, tiempo de recuperación, oscilación). Nada
de eso se declara en `limites` ni en `detectores_activos`: no hay número que
citar sin inventarlo, y `docs/09` §9.11 prohíbe justamente eso.

Los ÚNICOS dos `limites` (`LimiteDeAlerta`) de los diez perfiles son:

  - P1 `injector_duty` aviso 0,85 -- literal de docs/04 §4.2 P1 («duty de
    inyección > 85 %») y coincide con el valor por omisión de D8. Fracción:
    `ratio` ya es la canónica, no hace falta convertir.
  - P8 `oil_pressure` crítico, curva `base=201.3 kPa, pendiente=100 kPa por
    cada 1000 rpm` -- literal del ejemplo de docs/04 §4.2 P8 («1 bar de
    margen sobre la atmosférica, más 1 bar por cada 1 000 rpm») y coincide
    con `[detectores.D10.curva_minima]` de `data/umbrales.toml`.

En los dos casos el número YA estaba aprobado como valor por omisión de un
detector: aquí se repite solo para que el panel dibuje la línea, no para
fijar un límite nuevo. Es una duplicación de dato consciente (dos ficheros,
el mismo número) y el riesgo que abre -- que uno cambie sin el otro -- se deja
escrito en el informe de la tarea para que quien revise la puerta G1 lo sepa.

Solo biblioteca estándar más `dlv_core.perfil` / `dlv_core.primitivas` /
`dlv_core.topes`, ya en el árbol de dependencias del paquete.
"""

from __future__ import annotations

import pathlib

from dlv_core.perfil import ElementoDePanel, LimiteDeAlerta, Panel, Perfil
from dlv_core.primitivas import Direccion
from dlv_core.topes import CurvaLineal, NivelDeTope, Tope

RAIZ_DEL_REPOSITORIO = pathlib.Path(__file__).resolve().parents[1]
DESTINO = RAIZ_DEL_REPOSITORIO / "data" / "perfiles"


def _e(
    rol: str | None = None,
    id_nativo: str | None = None,
    *,
    requerido: bool = False,
    indice: int | None = None,
) -> ElementoDePanel:
    return ElementoDePanel(rol=rol, id_nativo=id_nativo, requerido=requerido, indice=indice)


# --------------------------------------------------------------------------- #
# P1 — Fuel / Lambda
# --------------------------------------------------------------------------- #
def _p1() -> Perfil:
    return Perfil(
        nombre="P1 — Fuel / Lambda",
        descripcion=(
            "Cierre del lazo de mezcla: ¿sigue la mezcla al objetivo? El perfil "
            "más usado (docs/04 §4.2 P1)."
        ),
        unidades={},
        paneles=(
            Panel(
                "Carga",
                (
                    _e("engine_speed", requerido=True),
                    _e("throttle_position", requerido=True),
                    _e("manifold_pressure"),
                ),
            ),
            Panel(
                "Mezcla",
                (
                    _e("lambda_measured", requerido=True, indice=1),  # Wideband O2 1
                    _e("lambda_target", requerido=True),  # Target Lambda
                    # "Wideband O2 Overall": mismo rol, SIN índice -- la
                    # lectura agregada del sensor de banda ancha, distinta de
                    # la instancia 1.
                    _e("lambda_measured", indice=None),
                    # λ error es el canal MATEMÁTICO de docs/04 §4.5, no un
                    # canal de ningún formato (ver cabecera del módulo,
                    # punto 3): reserva de posición, no reserva de fabricante.
                    _e(id_nativo="lambda_error"),
                ),
            ),
            Panel(
                "Correcciones",
                (
                    _e("fuel_trim_short", indice=1),  # O2 Control Bank 1 STFT
                    _e("fuel_trim_long", indice=1),  # O2 Control Bank 1 LTFT
                    _e(id_nativo="Fuel MAP Correction"),
                    _e(id_nativo="Fuel Coolant Temperature Correction"),
                ),
            ),
            Panel(
                "Inyección",
                (
                    _e("injector_duty", requerido=True, indice=1),  # Injection Stage 1 ADC
                    _e("injector_pulsewidth", indice=1),  # Injector 1 On Time
                    _e("fuel_pressure_differential"),  # Injector Pressure Differential
                    _e("fuel_pressure"),  # Fuel Pressure Expected
                ),
            ),
            Panel(
                "Estado",
                (
                    _e(id_nativo="Decel Cut State"),
                    _e("protection_cause"),
                ),
            ),
        ),
        limites=(
            LimiteDeAlerta(
                rol="injector_duty",
                topes=(Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ARRIBA, valor=0.85),),
            ),
        ),
        detectores_activos=("D4", "D5", "D8"),
    )


# --------------------------------------------------------------------------- #
# P2 — Knock / detonación
# --------------------------------------------------------------------------- #
def _p2() -> Perfil:
    return Perfil(
        nombre="P2 — Knock / detonación",
        descripcion="No perder ni un evento de detonación (docs/04 §4.2 P2).",
        unidades={},
        paneles=(
            Panel(
                "Carga",
                (
                    _e("engine_speed", requerido=True),
                    _e("manifold_pressure", requerido=True),
                    _e("throttle_position"),
                ),
            ),
            Panel(
                "Knock",
                (
                    _e("knock_level", requerido=True, indice=1),
                    _e("knock_level", indice=2),
                    _e("knock_threshold"),
                ),
            ),
            Panel(
                "Conteos",
                (
                    # ACUMULADO (monotono=no_decreciente): el canal delta lo
                    # crea automáticamente el motor a partir de este rol.
                    _e("knock_count", requerido=True, indice=1),
                    _e("knock_count", indice=2),
                ),
            ),
            Panel(
                "Respuesta",
                (
                    _e("knock_retard", indice=1),  # Knock Control Bank 1 Ignition Correction
                    _e("knock_retard", indice=2),
                    _e(id_nativo="Knock Control Bank 1 Long Term Trim"),
                    _e(id_nativo="Knock Control Bank 2 Long Term Trim"),
                    _e("ignition_advance"),
                ),
            ),
            Panel(
                "Contexto",
                (
                    _e("intake_air_temp"),
                    _e("coolant_temp"),
                    _e("lambda_measured", indice=1),
                ),
            ),
            Panel(
                "Estado",
                (
                    _e(id_nativo="Knock State"),
                    _e(id_nativo="Knock Detection Active State"),
                ),
            ),
        ),
        limites=(),
        detectores_activos=("D1", "D2", "D3"),
    )


# --------------------------------------------------------------------------- #
# P3 — Boost control
# --------------------------------------------------------------------------- #
def _p3() -> Perfil:
    return Perfil(
        nombre="P3 — Boost control",
        descripcion="Presión de sobrealimentación y el lazo que la controla (docs/04 §4.2 P3).",
        unidades={},
        paneles=(
            Panel(
                "Presión",
                (
                    _e("boost_pressure_actual", requerido=True),
                    _e("boost_pressure_target", requerido=True),
                    _e("boost_pressure_error"),
                ),
            ),
            Panel("Salida", (_e("boost_output"),)),
            Panel(
                "Términos PID",
                (
                    _e("boost_output_proporcional"),
                    _e("boost_output_integral"),
                    _e("boost_output_derivativo"),
                    _e("boost_output_base"),
                ),
            ),
            Panel(
                "Trims",
                (
                    _e("boost_trim_corto"),
                    _e("boost_trim_largo"),
                ),
            ),
            Panel(
                "Estado",
                (
                    _e("boost_state"),
                    _e("overboost_cut_pressure"),
                ),
            ),
        ),
        limites=(),
        detectores_activos=("D6", "D7"),
    )


# --------------------------------------------------------------------------- #
# P4 — Ignition
# --------------------------------------------------------------------------- #
def _p4() -> Perfil:
    return Perfil(
        nombre="P4 — Ignition",
        descripcion="Avance de encendido y sus correcciones (docs/04 §4.2 P4).",
        unidades={},
        paneles=(
            Panel(
                "Encendido",
                (
                    _e("ignition_advance", requerido=True),
                    _e("ignition_advance_base"),
                    _e("ignition_correction_total"),
                    _e("ignition_correction_coolant"),
                    _e("ignition_correction_air_temp"),
                    _e("ignition_correction_post_start"),
                    _e("ignition_correction_transient"),
                    _e("knock_retard", indice=1),
                    _e(id_nativo="Ignition 1 Duty Cycle"),
                    _e("dwell_time", indice=1),  # Ignition 1 On Time
                    _e("ignition_coil_supply"),
                ),
            ),
        ),
        limites=(),
        detectores_activos=(),
    )


# --------------------------------------------------------------------------- #
# P5 — Transient / tip-in
# --------------------------------------------------------------------------- #
def _p5() -> Perfil:
    return Perfil(
        nombre="P5 — Transient / tip-in",
        descripcion="Excursión de lambda tras una apertura brusca de mariposa (docs/04 §4.2 P5).",
        unidades={},
        paneles=(
            Panel(
                "Transitorio",
                (
                    _e(id_nativo="Throttle Position Derivative"),
                    _e(id_nativo="Transient Throttle Load Derivative"),
                    _e(id_nativo="Transient Throttle Fuel Enrichment Rate"),
                    _e(id_nativo="Transient Throttle Fuel Disenrichment Rate"),
                    _e(id_nativo="Transient Throttle Enrichment Load Derivative"),
                    _e(id_nativo="Transient Throttle Disenrichment Load Derivative"),
                    _e(id_nativo="Transient Throttle Enrichment Start Load"),
                    _e("ignition_correction_transient"),
                    _e("lambda_measured", requerido=True, indice=1),
                    _e("lambda_target", requerido=True),
                ),
            ),
        ),
        limites=(),
        detectores_activos=("D15",),
    )


# --------------------------------------------------------------------------- #
# P6 — Idle control
# --------------------------------------------------------------------------- #
def _p6() -> Perfil:
    return Perfil(
        nombre="P6 — Idle control",
        descripcion=(
            "Control de ralentí: error, salida del lazo y su recuperación (docs/04 §4.2 P6)."
        ),
        unidades={},
        paneles=(
            Panel(
                "Ralentí",
                (
                    _e("engine_speed", requerido=True),
                    _e("idle_target_rpm"),
                    _e("idle_rpm_error"),
                    _e("idle_output"),
                    _e(id_nativo="Idle Control Proportional Output"),
                    _e(id_nativo="Idle Control Integral Output"),
                    _e(id_nativo="Idle Control Derivative Output"),
                    _e("idle_trim_corto"),
                    _e("idle_trim_largo"),
                    _e("ignition_correction_idle"),
                    _e("idle_min_output"),
                ),
            ),
            Panel(
                "Estado",
                (
                    _e("idle_state"),
                    _e(id_nativo="Thermofan 1 Idle Up Active"),
                    _e(id_nativo="Air Con Idle Up Active"),
                ),
            ),
        ),
        limites=(),
        detectores_activos=(),
    )


# --------------------------------------------------------------------------- #
# P7 — Trigger / salud de sincronización
# --------------------------------------------------------------------------- #
def _p7() -> Perfil:
    return Perfil(
        nombre="P7 — Trigger / salud de sincronización",
        descripcion=(
            "Diagnóstico de sincronización: el perfil que resuelve los "
            "intermitentes (docs/04 §4.2 P7)."
        ),
        unidades={},
        paneles=(
            Panel(
                "Trigger",
                (
                    _e("trigger_errors", requerido=True),
                    _e("trigger_error_count"),
                    _e("trigger_sync_level"),
                    _e("trigger_sync_state"),
                    _e("trigger_sync_offset"),
                    _e("trigger_tooth_count"),
                    _e("trigger_tooth_period_error"),
                    _e(id_nativo="Sync Offset Difference At Error"),
                    _e(id_nativo="Home Tooth Count At Error"),
                    _e("trigger_voltage"),
                    _e("home_voltage"),
                    _e("home_travel_pct"),
                ),
            ),
        ),
        limites=(),
        detectores_activos=("D12",),
    )


# --------------------------------------------------------------------------- #
# P8 — Salud del motor y protecciones
# --------------------------------------------------------------------------- #
def _p8() -> Perfil:
    return Perfil(
        nombre="P8 — Salud del motor y protecciones",
        descripcion="Térmico, presiones y protecciones activas del motor (docs/04 §4.2 P8).",
        unidades={},
        paneles=(
            Panel(
                "Térmico y presiones",
                (
                    _e("coolant_temp", requerido=True),
                    _e("oil_temp"),
                    _e("oil_pressure", requerido=True),
                    _e("intake_air_temp"),
                    _e("ecu_temp"),
                    _e("battery_voltage", requerido=True),
                    _e("fuel_pressure"),
                ),
            ),
            Panel(
                "Estado",
                (
                    _e("protection_level"),
                    _e("protection_cause"),
                    _e(id_nativo="Engine Protection Ignition Retard"),
                    _e(id_nativo="Engine Protection Boost Correction"),
                    _e(id_nativo="Engine Protection Lambda Fuel Enrichment"),
                    _e("cut_percentage"),
                    _e("limiter_active"),
                ),
            ),
        ),
        limites=(
            LimiteDeAlerta(
                rol="oil_pressure",
                topes=(
                    Tope(
                        nivel=NivelDeTope.CRITICO,
                        direccion=Direccion.ABAJO,
                        valor=CurvaLineal(
                            rol_referencia="engine_speed",
                            base=201.3,
                            pendiente=100.0,
                            divisor_referencia=1000.0,
                        ),
                    ),
                ),
            ),
        ),
        detectores_activos=("D9", "D10", "D11", "D13", "D14"),
    )


# --------------------------------------------------------------------------- #
# P9 — Diagnóstico de sensores
# --------------------------------------------------------------------------- #
def _p9() -> Perfil:
    entradas_analogicas = tuple(_e("sensor_voltage", indice=i) for i in range(1, 11))
    entradas_sincronas = tuple(_e(id_nativo=f"Synced Pulse Input {i} Voltage") for i in range(1, 5))
    return Perfil(
        nombre="P9 — Diagnóstico de sensores",
        descripcion=(
            "Canales pegados, saturación y ruido de las entradas analógicas (docs/04 §4.2 P9)."
        ),
        unidades={},
        paneles=(
            Panel(
                "Sensores",
                entradas_analogicas
                + entradas_sincronas
                + (
                    _e("ref_voltage_5v"),
                    _e("diag_ref_ratiometrico"),
                    _e("diag_ref_absoluto"),
                    _e("diag_ref_discrepancia"),
                    _e("battery_voltage", requerido=True),
                ),
            ),
        ),
        limites=(),
        detectores_activos=("D16", "D17"),
    )


# --------------------------------------------------------------------------- #
# P10 — Launch control
# --------------------------------------------------------------------------- #
def _p10() -> Perfil:
    return Perfil(
        nombre="P10 — Launch control",
        descripcion="Control de salida en línea de largada (docs/04 §4.2 P10).",
        unidades={},
        paneles=(
            Panel(
                "Launch",
                (
                    _e("launch_state", requerido=True),
                    _e("launch_rpm_error"),
                    _e("launch_end_rpm"),
                    _e(id_nativo="Launch Control Fuel Correction"),
                    _e("ignition_correction_launch"),
                    _e("cut_percentage"),
                    _e("engine_speed", requerido=True),
                    _e("vehicle_speed"),
                    _e("driven_wheel_speed"),
                ),
            ),
        ),
        limites=(),
        detectores_activos=(),
    )


PERFILES_DE_FABRICA = {
    "p01_fuel_lambda": _p1,
    "p02_knock": _p2,
    "p03_boost_control": _p3,
    "p04_ignition": _p4,
    "p05_transient_tip_in": _p5,
    "p06_idle_control": _p6,
    "p07_trigger": _p7,
    "p08_salud_motor": _p8,
    "p09_diagnostico_sensores": _p9,
    "p10_launch_control": _p10,
}


def _escribir(nombre_fichero: str, perfil: Perfil, *, destino: pathlib.Path) -> None:
    """Ida y vuelta ANTES de escribir: un perfil que no se puede releer no
    llega a disco (mismo criterio que un `assert` de prueba, pero en la
    propia herramienta que produce el dato)."""
    texto = perfil.a_texto_json()
    reconstruido = Perfil.desde_texto_json(texto)
    if reconstruido.a_dict() != perfil.a_dict():
        raise AssertionError(f"{nombre_fichero}: la ida y vuelta por JSON no es exacta")
    ruta = destino / f"{nombre_fichero}.dlvprofile"
    ruta.write_text(texto + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nombre_fichero, fabrica in PERFILES_DE_FABRICA.items():
        perfil = fabrica()
        _escribir(nombre_fichero, perfil, destino=DESTINO)
        print(
            f"{nombre_fichero}.dlvprofile: {len(perfil.paneles)} paneles, "
            f"{len(perfil.roles_requeridos)} roles requeridos, "
            f"{len(perfil.roles_referenciados)} roles referenciados"
        )


if __name__ == "__main__":
    main()
