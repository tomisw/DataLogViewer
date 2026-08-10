"""Huella de invalidación de un resultado derivado de un fichero (ADR-005).

Nació dentro de `cache.py` (F1-11), que es quien primero necesitó decidir «¿este
`.dlvcache` sigue valiendo para este log?». Se le da un sitio propio al llegar el
segundo consumidor —el índice de carpeta del explorador,
`explorador/indice.py` (FE-01)—, por la misma razón por la que `Aviso` salió de
`formatos/haltech.py` a `informes.py`: dos definiciones de «este fichero ha
cambiado» que divergieran producirían el peor fallo del explorador, que su tabla
y el log abierto discrepen (riesgo R14 de `docs/02` §2.8).

Y hay un segundo motivo, más prosaico y igual de importante: `cache.py` importa
NumPy y Polars en su cabecera, así que reutilizar la huella desde allí arrastraba
las dos dependencias a un módulo que solo compara enteros y cadenas. Aquí no hay
ninguna: solo biblioteca estándar, así que la huella se puede usar y probar en
cualquier entorno.

`cache.py` sigue reexportando los tres nombres, así que el código que los
importaba de allí no cambia.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "VERSION_ESQUEMA_CACHE",
    "ClaveInvalidacion",
    "construir_clave",
    "es_valida",
]

# --------------------------------------------------------------------------- #
VERSION_ESQUEMA_CACHE = "1"


@dataclass(slots=True, frozen=True)
class ClaveInvalidacion:
    """Clave de invalidación de caché (ADR-005): ruta, tamaño, mtime y versiones.

    `ruta` se compara por igualdad de valor (dos `Path` iguales si su
    representación en texto lo es): quien llama es responsable de pasar
    siempre la misma forma (resuelta/absoluta o relativa, pero consistente)
    tanto al escribir como al comprobar, o la invalidación disparará en falso
    por una diferencia puramente cosmética de la ruta.
    """

    ruta: Path
    tamano_bytes: int
    mtime_ns: int
    version_parser: str
    version_descriptor_formato: str
    # Ver docstring del módulo: no estaba en el stub original.
    version_esquema_cache: str = VERSION_ESQUEMA_CACHE


def construir_clave(
    ruta: Path,
    *,
    tamano_bytes: int,
    mtime_ns: int,
    version_parser: str,
    version_descriptor_formato: str,
) -> ClaveInvalidacion:
    """Fábrica de `ClaveInvalidacion` que fija `version_esquema_cache` al
    valor que entiende ESTE código (`VERSION_ESQUEMA_CACHE`), para que quien
    llama no tenga que conocer ni propagar ese detalle interno del módulo.

    `ruta`/`tamano_bytes`/`mtime_ns` los obtiene quien llama (p. ej. `dlv-api`
    con `Path.stat()`): este módulo no toca el sistema de ficheros por su
    cuenta para construir la clave (ADR-002), solo empaqueta los valores que
    se le dan.
    """
    return ClaveInvalidacion(
        ruta=ruta,
        tamano_bytes=tamano_bytes,
        mtime_ns=mtime_ns,
        version_parser=version_parser,
        version_descriptor_formato=version_descriptor_formato,
        version_esquema_cache=VERSION_ESQUEMA_CACHE,
    )


def es_valida(clave_almacenada: ClaveInvalidacion | None, clave_actual: ClaveInvalidacion) -> bool:
    """Compara dos claves de invalidación campo a campo, sin tocar disco (ni
    siquiera necesita que el JSON de metadatos exista más allá de haberse
    leído antes: esta función en sí no hace E/S).

    `clave_almacenada` es `None` cuando todavía no hay caché (primera
    apertura, o el JSON de metadatos se ha borrado/corrompido): en ese caso
    la función NO lanza, responde `False` ("hace falta reconstruir"), que es
    la respuesta correcta para "no hay nada que invalidar todavía".
    """
    if clave_almacenada is None:
        return False
    return clave_almacenada == clave_actual


# --------------------------------------------------------------------------- #
# Esquema físico
# --------------------------------------------------------------------------- #
