"""Resolución de la presión de referencia absoluto -> relativo (tarea F1-15).

El MECANISMO ya existe desde F1-13: `unidades.desde_canonica`/`a_canonica`
aceptan `referencia_kpa`, lo restan (o suman) en canónica ANTES de convertir
la unidad, y **solo a los valores de `Clase.PUNTO`** -- un Δ de 50 kPa vale
lo mismo en absoluto que en relativo. Por eso el cambio de origen es
combinable con cualquier unidad sin escribir una variante "bar relativo"
aparte de "bar": la resta ocurre en kPa canónicos y la conversión a bar/psi
viene después, sobre el resultado.

Lo que faltaba, y hace esta tarea, es de DÓNDE sale ese número. `docs/01-
formato-log.md` §1.9 es tajante: **no hay canal barométrico** en estos logs
(el único resultado de buscar "presión ambiente" es `Ambient Light Level`),
todas las presiones son absolutas, y para mostrar boost en relativo hace
falta una referencia que hay que obtener de otro sitio. Da tres opciones en
orden de preferencia, que son las que implementa `resolver_referencia`:

    1. Declarada por el usuario en el perfil del vehículo.
    2. Autodetección: la presión de colector con el motor parado.
    3. La constante 101,325 kPa, **marcada como estimada**.

Los modos y la constante son datos (`data/units.toml [presion_referencia]`),
no números cableados aquí.

POR QUÉ IMPORTA MARCAR "ESTIMADA"
==================================
Con la constante, un boost de "1,2 bar" puede ser en realidad 1,15 o 1,25
según la altitud y el tiempo del día del registro. Es una diferencia que
llega a una decisión de tuning, así que `ReferenciaPresion.estimada` no es
un detalle cosmético: es lo que permite a la interfaz no presentar como
medido algo que se ha supuesto.

DISCREPANCIA ENTRE ESPECIFICACIONES (para la revisión G1)
=========================================================
`docs/01` §1.9 dice "mediana de `Manifold Pressure` con `RPM = 0` **al
inicio del log**"; `data/units.toml [presion_referencia]` dice solo
`auto_condicion = "engine_speed == 0"`, sin restringir al inicio. Se sigue
el fichero de datos (más amplio) y se documenta aquí: la presión de colector
iguala a la ambiente **siempre** que el motor no gira, no solo al arrancar,
así que la mediana sobre todas las muestras con el motor parado usa más
evidencia y es más robusta que la del arranque -- pero es una decisión, no
una transcripción literal de §1.9, y por eso está escrita.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from dlv_core.informes import Aviso

__all__ = ["ModoReferencia", "ReferenciaPresion", "resolver_referencia"]


class ModoReferencia(Enum):
    """Modos de `data/units.toml [presion_referencia].modos`."""

    NINGUNA = "ninguna"
    """Presión absoluta: no se resta nada. Es lo que declara el preset `si`."""

    CONSTANTE = "constante"
    """Un valor fijo: el que declaró el usuario, o la constante del catálogo."""

    CANAL = "canal"
    """De un canal barométrico del propio log. Estos logs no tienen ninguno
    (docs/01 §1.9), pero el modo existe en el catálogo para formatos que sí."""

    AUTO = "auto"
    """La cascada de §1.9: usuario -> autodetección -> constante estimada.
    Es lo que declaran los presets `metrico`, `imperial` y los de motorsport."""


@dataclass(slots=True, frozen=True)
class ReferenciaPresion:
    """El valor listo para `unidades.desde_canonica(..., referencia_kpa=...)`,
    con la trazabilidad de de dónde salió.
    """

    kpa: float | None
    """`None` solo en `ModoReferencia.NINGUNA`: no hay referencia porque no se
    quiere ninguna, no porque no se haya podido calcular."""

    modo: ModoReferencia
    """El modo que se PIDIÓ. `AUTO` puede acabar resolviendo por
    autodetección o por la constante; `resuelto_por_constante` lo distingue."""

    estimada: bool
    """`True` si el valor no se midió en este log (es decir, salió de la
    constante del catálogo). La interfaz debe marcarlo (§1.9)."""

    aviso: Aviso | None = None

    @property
    def resuelto_por_constante(self) -> bool:
        """Sinónimo legible de `estimada`, para quien lea el flujo de `AUTO`."""
        return self.estimada


def _mediana_con_motor_parado(
    presion_colector_kpa: np.ndarray, regimen_rpm: np.ndarray
) -> float | None:
    """Mediana de la presión de colector en las muestras con el motor parado.

    Devuelve `None` si no hay ninguna muestra con el motor parado (un log que
    empieza con el motor ya en marcha, algo perfectamente normal en una
    sesión de banco): no es un error, es que este log no puede autodetectar.

    Vectorizado (ADR-009): una máscara booleana y una mediana de NumPy sobre
    el array completo, sin recorrer muestras.
    """
    if presion_colector_kpa.shape != regimen_rpm.shape:
        raise ValueError(
            "presion_colector_kpa y regimen_rpm deben tener la misma forma "
            f"({presion_colector_kpa.shape} != {regimen_rpm.shape}); ¿son del mismo "
            "grupo de muestreo?"
        )
    parado = regimen_rpm == 0
    if not parado.any():
        return None
    return float(np.median(presion_colector_kpa[parado]))


def resolver_referencia(
    *,
    modo: ModoReferencia,
    constante_catalogo_kpa: float,
    declarada_kpa: float | None = None,
    presion_colector_kpa: np.ndarray | None = None,
    regimen_rpm: np.ndarray | None = None,
) -> ReferenciaPresion:
    """Resuelve la presión de referencia según `modo` (docs/01 §1.9).

    `constante_catalogo_kpa` viene de
    `Catalogo.referencia_presion_por_omision_kpa` (`data/units.toml`), no de
    una constante en este código.

    `declarada_kpa` es la del perfil del vehículo (opción 1). Los dos arrays
    son para la autodetección (opción 2) y deben pertenecer al MISMO grupo de
    muestreo -- si no, sus índices no se corresponden y la máscara "motor
    parado" señalaría muestras equivocadas; por eso se comprueba la forma.

    Precedencia dentro de `AUTO`, la de §1.9: lo declarado por el usuario gana
    a lo autodetectado, y lo autodetectado gana a la constante. `CONSTANTE`
    sin `declarada_kpa` cae a la del catálogo y se marca estimada.
    """
    if modo is ModoReferencia.NINGUNA:
        return ReferenciaPresion(kpa=None, modo=modo, estimada=False)

    if modo is ModoReferencia.CANAL:
        raise NotImplementedError(
            "modo 'canal': estos logs no traen canal barométrico (docs/01 §1.9); "
            "el modo existe en el catálogo para formatos que sí lo tengan"
        )

    if declarada_kpa is not None:
        # Opción 1 de §1.9, y gana también en modo AUTO: si el propietario del
        # vehículo ha declarado la presión de su taller, sabe más que cualquier
        # inferencia sobre los datos.
        return ReferenciaPresion(kpa=declarada_kpa, modo=modo, estimada=False)

    if modo is ModoReferencia.AUTO and presion_colector_kpa is not None and regimen_rpm is not None:
        medida = _mediana_con_motor_parado(presion_colector_kpa, regimen_rpm)
        if medida is not None:
            return ReferenciaPresion(kpa=medida, modo=modo, estimada=False)
        aviso = Aviso(
            "referencia_presion_sin_motor_parado",
            "el log no tiene ninguna muestra con el motor parado, así que no se "
            f"puede medir la presión ambiente; se usa la constante "
            f"{constante_catalogo_kpa:g} kPa y la presión relativa queda ESTIMADA",
        )
        return ReferenciaPresion(kpa=constante_catalogo_kpa, modo=modo, estimada=True, aviso=aviso)

    # Opción 3: último recurso. Incluye `CONSTANTE` sin valor declarado y
    # `AUTO` sin canales con los que autodetectar.
    aviso = Aviso(
        "referencia_presion_estimada",
        f"no hay presión de referencia declarada ni medible; se usa la constante "
        f"{constante_catalogo_kpa:g} kPa y la presión relativa queda ESTIMADA "
        "(docs/01 §1.9)",
    )
    return ReferenciaPresion(kpa=constante_catalogo_kpa, modo=modo, estimada=True, aviso=aviso)
