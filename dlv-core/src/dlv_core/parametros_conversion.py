"""Resolución de parámetros para conversiones parametrizadas (tarea F1-14).

`dlv_core.unidades.Parametrizada` (F1-13) ya sabe HACER la conversión
`mostrado = a(p) * canónica`, dado un `p`; lo que faltaba es de DÓNDE sale
ese `p` para un log concreto. El caso guía es λ → AFR
(`docs/04-perfiles-motorsport.md` §4.5, `data/units.toml`): el factor es la
estequiometría del combustible en uso (rol `stoichiometry`,
`data/roles.toml`), no la constante 14,7 de la gasolina -- un log de E85 o
metanol daría un AFR con aspecto correcto pero equivocado si se ignora
(`data/formats/haltech_nsp.toml [tipos.Stoichiometry]` ya lo deja anotado).

`dlv_core.roles.resolver_rol` sigue sin implementar (STUB, F1-06/FG-09 son
quienes le dan cuerpo): este módulo no espera a esa resolución completa.
Recibe los valores YA identificados como pertenecientes al canal de rol
correspondiente -- los localiza quien llama, hoy por `Canal.id`/nombre exacto
contra el descriptor de formato, mañana por `resolver_rol` cuando exista --
y solo resuelve el escalar a partir de ellos.

Este módulo importa NumPy a propósito (a diferencia de `unidades.py`, que
deliberadamente no lo hace): trabaja con arrays de muestras reales de un
canal, no con la aritmética escalar/vectorizable genérica de `Parametrizada`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dlv_core.informes import Aviso

__all__ = ["ParametroResuelto", "resolver_parametro_de_canal"]


@dataclass(slots=True, frozen=True)
class ParametroResuelto:
    """El escalar listo para pasar a `Parametrizada.desde_canonica`/
    `a_canonica`, más un aviso si los datos no eran tan constantes como se
    esperaba (E1.7: se avisa y se sigue, no se rechaza el log por esto)."""

    valor: float
    aviso: Aviso | None


def resolver_parametro_de_canal(
    valores: np.ndarray, *, rol: str, tolerancia_relativa: float = 0.01
) -> ParametroResuelto:
    """Resuelve el escalar de una conversión `Parametrizada` a partir de los
    valores CANÓNICOS (ya multiplicados por `a_canonica`, no crudos) del
    canal de rol `rol` (p. ej. `stoichiometry`).

    Se asume constante durante todo el log: es una propiedad del combustible
    o del ajuste del motor, no algo que cambie muestra a muestra. Se usa la
    MEDIANA (robusta frente a algún valor suelto de arranque o transición),
    y si la variación observada (`max - min`, relativa a la propia mediana)
    supera `tolerancia_relativa`, se devuelve también un `Aviso` en vez de
    fingir que el valor era estable -- puede ser un cambio real de
    combustible a mitad de log, o el canal equivocado.

    Lanza `ValueError` solo si no hay ninguna muestra: sin al menos un valor
    no hay nada que resolver, y eso sí impide continuar con esta conversión.
    """
    if valores.size == 0:
        raise ValueError(f"el canal de rol '{rol}' no tiene ninguna muestra en este log")

    mediana = float(np.median(valores))
    minimo = float(valores.min())
    maximo = float(valores.max())

    aviso = None
    referencia = abs(mediana) if mediana != 0 else 1.0
    if (maximo - minimo) / referencia > tolerancia_relativa:
        aviso = Aviso(
            "parametro_no_constante",
            f"el canal de rol '{rol}' varía entre {minimo:g} y {maximo:g} en este log "
            f"(se usa la mediana, {mediana:g}); se esperaba un valor constante",
        )
    return ParametroResuelto(valor=mediana, aviso=aviso)
