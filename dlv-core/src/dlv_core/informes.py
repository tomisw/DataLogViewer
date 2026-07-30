"""Piezas del informe de importación, compartidas por toda la ruta de ingesta.

`Aviso` nació en `formatos/haltech.py` (F1-01) porque el parser de cabecera fue
el primero en necesitarlo. Al llegar el segundo productor de avisos —la
reconciliación de reloj (F1-04)— hacía falta decidir entre duplicar el tipo o
darle un sitio propio. Se le da un sitio propio: el «Informes» de §3.3 es un
componente de `dlv-core`, y un módulo genérico como `reloj.py` no debe depender
de un formato concreto para poder avisar.

`formatos/haltech.py` sigue reexportando `Aviso`, así que el código que lo
importaba de allí no cambia.

Solo biblioteca estándar.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Aviso"]


@dataclass(slots=True, frozen=True)
class Aviso:
    """Anomalía que no impide cargar. Va al informe de importación (E1.7).

    La regla de `docs/02` §2.5: se avisa y se sigue siempre que se puedan
    producir datos utilizables, y se rechaza solo cuando seguir daría
    resultados silenciosamente equivocados.
    """

    codigo: str
    mensaje: str
    linea: int | None = None

    def __str__(self) -> str:
        donde = f" (línea {self.linea})" if self.linea is not None else ""
        return f"[{self.codigo}]{donde} {self.mensaje}"
