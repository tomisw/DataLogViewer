"""dlv-api: capa de comandos de DataLogViewer.

FastAPI + uvicorn sobre `127.0.0.1`, con puerto efímero y token de sesión
generado al arrancar (ADR-007, `docs/03-arquitectura.md` §3.2). Depende de
`dlv-core`.

Este `__init__` no importa `dlv_api.main` (que sí necesita `fastapi` y
`uvicorn`) para que `import dlv_api` y su `__version__` sigan funcionando
incluso en un entorno donde esas dependencias todavía no se han instalado.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
