"""Capa de formatos en dos niveles (ADR-008, `docs/07-formatos-y-csv-generico.md`).

Responsabilidades futuras de este subpaquete:

- Sondeo de los primeros bytes de un fichero para distinguir un formato nativo
  conocido (firma de cabecera) de un CSV genérico.
- Carga de descriptores de formato nativo desde TOML versionado (dato, no
  código: ADR-008) y su gramática de cabecera.
- Detección propuesta para CSV genérico (separador, decimal, nulos, columna de
  tiempo) cuando no hay firma nativa.

Como el resto de `dlv-core`, este subpaquete no abre ficheros por su cuenta:
recibe objetos de lectura (`IO[bytes]`) o los primeros bytes ya leídos, nunca
una ruta que abra él mismo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import IO


@dataclass(slots=True, frozen=True)
class DescriptorFormato:
    """Descriptor de un formato nativo cargado desde `formats/*.toml`.

    Los campos reales (gramática de cabecera, mapa de canales, factores de
    escala) se añaden cuando se implemente la carga; de momento solo fija la
    identidad del formato para que el resto del andamiaje pueda referenciarlo.
    """

    id: str
    version: str


def sondear_formato(cabecera: bytes) -> str | None:
    """Devuelve el `id` de formato nativo detectado por firma, o `None`.

    `cabecera` son los primeros bytes del fichero (p. ej. 64 kB, §3.4 paso 1),
    ya leídos por quien llama. Esta función no abre ni lee ficheros.
    """
    raise NotImplementedError


def cargar_descriptor(fuente: IO[str], *, formato_id: str) -> DescriptorFormato:
    """Parsea un descriptor TOML de formato nativo desde `fuente`.

    `fuente` es un objeto de lectura de texto ya abierto por quien llama
    (`dlv-core` no accede al sistema de ficheros por su cuenta).
    """
    raise NotImplementedError
