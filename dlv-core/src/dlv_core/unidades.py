"""Sistema de unidades: valor canónico, conversión solo en presentación.

ADR-004 (`docs/03-arquitectura.md` §3.2) y `docs/06-sistema-de-unidades.md`:
lo que se persiste (caché, umbrales, perfiles, mallas, anotaciones) está
siempre en la unidad canónica de cada dimensión. La conversión a la unidad
elegida por el usuario (°C/°F, kPa/bar/psi, λ/AFR, km/h/mph...) se aplica solo
a los cubos visibles en el momento de dibujar, nunca al dato persistido.

Este módulo está vacío de implementación (F0-02 es andamiaje): fija los tipos
y las firmas que usará el resto de `dlv-core`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


@dataclass(slots=True, frozen=True)
class Afin:
    """Conversión afín `y = a*x + b` entre una representación y la canónica.

    Cubre los casos `INT32_SCALED -> canónica` de ADR-003 y la mayoría de
    conversiones de unidad de `docs/06-sistema-de-unidades.md`. Las
    conversiones no afines (recíprocas, parametrizadas) tienen su propio tipo,
    añadido cuando se implemente ese documento.
    """

    a: float
    b: float

    def a_canonica(self, valores: np.ndarray) -> np.ndarray:
        """Aplica la conversión a canónica sobre el array completo (sin bucle)."""
        raise NotImplementedError

    def desde_canonica(self, valores: np.ndarray) -> np.ndarray:
        """Aplica la conversión inversa (canónica -> representación) sobre el array."""
        raise NotImplementedError


@dataclass(slots=True, frozen=True)
class Dimension:
    """Una dimensión física (temperatura, presión, ...) con unidad canónica.

    `unidades.toml` (dato versionado, ADR-008) es la fuente real; este tipo es
    la forma en memoria que consumirá el resto del núcleo.
    """

    id: str
    unidad_canonica: str
    unidades_disponibles: tuple[str, ...]


def cargar_dimensiones(fuente: object) -> dict[str, Dimension]:
    """Carga el catálogo de dimensiones desde `units.toml` ya abierto.

    `fuente` es un objeto de lectura de texto (`dlv-core` no abre ficheros por
    su cuenta); el tipo real (`IO[str]` o `TomlDecoder`) se ajustará cuando se
    implemente `docs/06-sistema-de-unidades.md`.
    """
    raise NotImplementedError


def convertir(
    valores: np.ndarray, *, origen: str, destino: str, dimension: Dimension
) -> np.ndarray:
    """Convierte un array completo entre dos unidades de la misma dimensión.

    Operación vectorizada de NumPy sobre el array entero (ADR-009): nunca un
    bucle por muestra, ni siquiera para las conversiones no afines.
    """
    raise NotImplementedError
