"""Permite `python -m dlv_app` (verificado al confirmar que la app arranca).

`dlv_app.main` ya tenia `if __name__ == "__main__": main()`, pero eso solo
dispara al ejecutar `main.py` como script (`python dlv-app/src/dlv_app/
main.py`), no con `python -m dlv_app`: `-m` busca `dlv_app/__main__.py`, que
no existia. Sin este fichero, `python -m dlv_app` fallaba con
`No module named dlv_app.__main__; 'dlv_app' is a package and cannot be
directly executed` -- el primer sintoma real al intentar arrancar la app tal
como la documentacion de la tarea sugiere invocarla.
"""

from __future__ import annotations

from dlv_app.main import main

if __name__ == "__main__":
    main()
