"""Permite `python -m dlv_app [ruta_del_log]` (verificado arrancando la app).

`dlv_app.main` ya tenia `if __name__ == "__main__": main()`, pero eso solo
dispara al ejecutar `main.py` como script (`python dlv-app/src/dlv_app/
main.py`), no con `python -m dlv_app`: `-m` busca `dlv_app/__main__.py`, que
no existia. Sin este fichero, `python -m dlv_app` fallaba con
`No module named dlv_app.__main__; 'dlv_app' is a package and cannot be
directly executed` -- el primer sintoma real al intentar arrancar la app tal
como la documentacion de la tarea sugiere invocarla.

Los argumentos se leen con `argparse` y no con `sys.argv` a mano para que
`--help` diga que hace falta un log: la diferencia entre abrir la aplicacion
con un log real y abrirla con datos sinteticos es exactamente ese argumento, y
no tenerlo documentado hace que parezca que la aplicacion "no lee logs".
"""

from __future__ import annotations

import argparse

from dlv_app.main import main


def _argumentos() -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        prog="python -m dlv_app",
        description="Abre DataLogViewer. Sin LOG, arranca con datos sinteticos.",
    )
    analizador.add_argument(
        "log",
        nargs="?",
        default=None,
        help="ruta del fichero de log a abrir (p. ej. samples/real/AutoLog_....csv)",
    )
    analizador.add_argument(
        "--url-frontend",
        default=None,
        help=(
            "servidor de desarrollo de Vite, p. ej. http://localhost:5173 con "
            "`npm run dev` corriendo. Sin esto se sirve dlv-ui/dist/."
        ),
    )
    analizador.add_argument(
        "--depurar",
        action="store_true",
        help=(
            "abre las herramientas de desarrollo del motor web. Es la unica via "
            "para ver un error de JavaScript: la suite de dlv-ui corre en Node "
            "sin DOM, asi que el codigo de montaje no se ejecuta en ninguna prueba."
        ),
    )
    return analizador.parse_args()


if __name__ == "__main__":
    args = _argumentos()
    main(url_frontend=args.url_frontend, log=args.log, depurar=args.depurar)
