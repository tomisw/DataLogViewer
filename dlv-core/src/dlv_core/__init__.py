"""dlv-core: núcleo de datos de DataLogViewer.

Biblioteca Python pura (§3.3 de `docs/03-arquitectura.md`, ADR-002 y ADR-008):

- No importa `dlv_api`, `dlv_ui` ni `dlv_app`. Es la condición para poder
  probarla sola y reutilizarla en cualquier contenedor futuro (web, móvil,
  CLI de análisis por lotes).
- No accede al sistema de ficheros por su cuenta: toda función que necesite
  leer algo recibe un objeto de lectura (`IO[bytes]`, ruta ya resuelta, etc.)
  como parámetro. Quien decide qué fichero abrir es la capa que la usa
  (`dlv-api` hoy), no `dlv-core`.

Este módulo `__init__` se mantiene deliberadamente ligero: no importa los
submódulos (`almacen`, `piramide`, ...) para que `import dlv_core` no arrastre
`polars`/`numpy` como efecto secundario y el test de humo (que solo comprueba
`__version__`) sea válido incluso en un entorno donde esas dependencias
todavía no se han instalado.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
