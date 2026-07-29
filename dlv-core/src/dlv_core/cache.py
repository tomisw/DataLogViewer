"""Caché de parseo en Parquet, escrita por Polars (ADR-005).

`dlv-core` no decide por su cuenta dónde vive la caché ni qué fichero abrir:
toda ruta y todo objeto de lectura/escritura llega como parámetro desde quien
llama (hoy, `dlv-api`). Este módulo solo sabe cómo se construye la clave de
invalidación y cómo se serializa/deserializa el contenido, no dónde se guarda
la carpeta `.dlvcache` en el disco del usuario.

La pirámide de decimación (`piramide.py`) se persiste dentro de la caché:
recalcularla cuesta más que leerla (§3.2 ADR-005).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl


@dataclass(slots=True, frozen=True)
class ClaveInvalidacion:
    """Clave de invalidación de caché (ADR-005): ruta, tamaño, mtime y versiones."""

    ruta: Path
    tamano_bytes: int
    mtime_ns: int
    version_parser: str
    version_descriptor_formato: str


@dataclass(slots=True, frozen=True)
class MetadatosCache:
    """El JSON de metadatos que acompaña al `.parquet` de la caché (ADR-005)."""

    clave: ClaveInvalidacion
    canales: tuple[str, ...]
    roles: dict[str, str]
    dimensiones: dict[str, str]
    grupos_muestreo: tuple[str, ...]


def es_valida(clave_almacenada: ClaveInvalidacion, clave_actual: ClaveInvalidacion) -> bool:
    """Compara dos claves de invalidación campo a campo."""
    raise NotImplementedError


def escribir(destino: Path, tabla: pl.DataFrame, metadatos: MetadatosCache) -> None:
    """Escribe la caché: `destino` es la ruta al `.dlvcache` ya resuelta por quien llama."""
    raise NotImplementedError


def leer(origen: Path) -> tuple[pl.DataFrame, MetadatosCache]:
    """Lee una caché existente desde `origen`, ruta ya resuelta por quien llama."""
    raise NotImplementedError
