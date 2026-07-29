"""Identidad de canal en capas y catálogo de roles semánticos (ADR-008).

`docs/07-formatos-y-csv-generico.md`: la identidad de un canal deja de ser solo
el `ID` nativo y pasa a resolverse en capas: rol semántico -> `(formato, ID)`
nativo -> nombre normalizado -> asignación manual del usuario. Los perfiles y
detectores (`dlv-core.detectores`) se definen por rol, no por canal concreto,
para que funcionen igual en un log Haltech que en un CSV genérico.

El catálogo de roles (`roles.toml`) y sus sinónimos son datos versionados, no
código (ADR-008): este módulo solo fija los tipos y las firmas de resolución.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import IO


@dataclass(slots=True, frozen=True)
class ChannelKey:
    """Identidad en capas de un canal (ADR-003, ADR-008).

    Al menos una de `rol`, `nativo` o `nombre_normalizado` debe estar
    presente; la resolución de "cuál gana" para mostrar y para agrupar
    detectores se implementa en `resolver_rol`, no aquí.
    """

    rol: str | None
    formato: str | None
    id_nativo: str | None
    nombre_normalizado: str | None


@dataclass(slots=True, frozen=True)
class Rol:
    """Entrada del catálogo `roles.toml`: un rol semántico y sus sinónimos."""

    id: str
    dimension: str | None
    sinonimos: tuple[str, ...]


def cargar_catalogo_roles(fuente: IO[str]) -> dict[str, Rol]:
    """Carga el catálogo de roles desde `roles.toml` ya abierto por quien llama."""
    raise NotImplementedError


def resolver_rol(nombre_canal: str, catalogo: dict[str, Rol]) -> str | None:
    """Asigna un rol a un nombre de canal por coincidencia de sinónimos.

    Devuelve `None` cuando no hay coincidencia plausible; la calibración de
    qué cuenta como "plausible" es el informe de plausibilidad de §3.4 paso 6.
    """
    raise NotImplementedError
