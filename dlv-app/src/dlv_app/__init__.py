"""dlv-app: contenedor pywebview de DataLogViewer.

Arranca el servidor de `dlv-api` en un hilo de fondo y abre una ventana
apuntando al frontend `dlv-ui` (ADR-002). Se empaqueta después con PyInstaller
en modo `onedir` (`docs/03-arquitectura.md` §3.10).

Este `__init__` no importa `dlv_app.main` (que sí necesita `pywebview`) para
que `import dlv_app` y su `__version__` sigan funcionando incluso en un
entorno donde esa dependencia todavía no se ha instalado.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
