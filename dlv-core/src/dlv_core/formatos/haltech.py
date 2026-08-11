"""Reexport del motor de formatos nativos, por compatibilidad (F1-01 → FG-13).

Aquí vivía el parser de cabecera del formato Haltech NSP `%DataLog% 1.1`. FG-13
lo partió en dos: el motor genérico, que no cita ninguna clave de ningún
fabricante, está en `formatos/nativo.py`, y todo lo que era propio de Haltech
—la clave de versión, los nombres `ID`/`Type`/`DisplayMaxMin` y su papel, el `:`
que separa clave de valor, el orden del rango, la forma de la marca de tiempo— es
ahora una entrada de `data/formats/haltech_nsp.toml`.

**En este fichero no queda lógica.** Solo reexporta, para que el código que hacía
`from dlv_core.formatos.haltech import parsear_cabecera` siga funcionando sin
cambios; es el mismo criterio con el que `informes.py` dejó a este módulo
reexportando `Aviso`. Lo nuevo debe importar de `dlv_core.formatos.nativo`.

Que el nombre siga siendo `haltech` es historia, no diseño: el parser de Haltech
es hoy `nativo.parsear_cabecera` + `data/formats/haltech_nsp.toml`, y añadir otro
formato nativo de texto no toca ninguno de los dos.
"""

from __future__ import annotations

from dlv_core.formatos.nativo import (
    BOM_UTF8,
    Aviso,
    Cabecera,
    Canal,
    Descriptor,
    ErrorDeDescriptor,
    ErrorDeFormato,
    cargar_descriptor,
    parsear_cabecera,
    sondear_formato,
)

__all__ = [
    "BOM_UTF8",
    "Aviso",
    "Cabecera",
    "Canal",
    "Descriptor",
    "ErrorDeDescriptor",
    "ErrorDeFormato",
    "cargar_descriptor",
    "parsear_cabecera",
    "sondear_formato",
]
