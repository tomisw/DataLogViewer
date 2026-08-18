# -*- mode: python ; coding: utf-8 -*-
"""Especificacion de PyInstaller para `dlv-app`, modo `onedir` (ADR-002,
`docs/03-arquitectura.md` SS3.10): una carpeta con el ejecutable y sus
dependencias, distribuida como ZIP -- deliberadamente NO `onefile`.
`onefile` se descomprime en un directorio temporal en cada arranque (segundos
de mas, y escribe fuera de la carpeta del programa), lo que rompe el modo
portable que exige SS3.10 ("con un portable.txt junto al ejecutable, la app
no escribe nada fuera de su carpeta"). `onedir` no descomprime nada al
arrancar y es igual de portable distribuido en ZIP.

Estado de este fichero (tarea F5-01, sobre la base de F1-35)
================================================================
Esta tarea sigue sin poder producir el binario: PyInstaller no esta
instalado en el entorno donde se escribio este fichero (PyPI da 403 aqui) y
no se puede instalar, asi que **nada de lo de abajo se ha ejecutado con un
build real** -- ver el informe de la tarea para el detalle de que se
comprobo en su lugar (AST del propio fichero, existencia de cada ruta de
`datas`, `python -m py_compile`) y que se dio explicitamente por NO MEDIDO
(arranque en frio, tamano del ZIP contra `docs/02-alcance-y-plan.md` SS2.6).

Lo que SI cambia respecto a F1-35 en este fichero:
- `datas` ahora incluye `dlv-ui/dist` (antes solo `data/`), con una
  comprobacion que aborta el build con un mensaje claro si no existe --
  ver mas abajo. Sin el, el paquete abriria la pagina placeholder
  PROVISIONAL de `dlv_app.main` en vez del frontend real.
- `excludes` pasa de una sola entrada (`pyarrow`) a una lista mas larga,
  cada una con su motivo (ver comentarios en la lista). Ninguna se ha
  confirmado contra un build real: la unica forma de confirmar que una
  exclusion no rompe nada es un build real por plataforma con el log de
  advertencias (`build/dlv-app/warn-dlv-app.txt`) y una prueba manual de
  humo abriendo un log real, que es trabajo pendiente de quien tenga
  acceso a PyPI.
- `hiddenimports` anade los modulos que `uvicorn.Config(app, host=host,
  log_level="info")` (`dlv_api/main.py`, sin `loop=`/`http=`/`ws=`
  explicitos) resuelve en tiempo de ejecucion por nombre segun lo que haya
  instalado (`uvicorn/config.py`, tablas `LOOP_SETUPS`/`HTTP_PROTOCOLS` con
  la clave `"auto"`), no por un `import` estatico: el mismo patron por el
  que F1-35 ya declaraba a mano los backends de `pywebview`.

Problema conocido, SIGUE sin resolverse aqui (fuera del carril de F5-01)
==========================================================================
`dlv_api.main` localiza el descriptor de formato Haltech y el catalogo de
unidades por ruta relativa al propio fichero fuente:

    _RAIZ_REPO = Path(__file__).resolve().parents[3]
    _DESCRIPTOR_HALTECH = _RAIZ_REPO / "data" / "formats" / "haltech_nsp.toml"
    _UNITS_TOML = _RAIZ_REPO / "data" / "units.toml"

Bajo PyInstaller `onedir` con `noarchive=False` (ver `PYZ` mas abajo), el
bytecode puro de `dlv_api.main` vive dentro del archivo `PYZ`, no como
fichero suelto en disco: `__file__` ya no aterriza en una ruta real del
arbol de codigo, y `.parents[3]` no tiene un equivalente valido en el
paquete congelado. `dlv_app/src/dlv_app/main.py` tenia el MISMO problema
para localizar `dlv-ui/dist` y esta tarea SI lo arregla ahi
(`_raiz_datos_de_la_app`, que distingue `sys.frozen` de arbol de
desarrollo) porque `dlv-app/*` esta en el carril de F5-01.

`dlv-api/*` NO esta en el carril de F5-01 (restriccion explicita de la
tarea: "NO toques ... dlv-api/"), asi que el cambio equivalente en
`dlv_api.main` --el mismo patron `sys.frozen`/`sys._MEIPASS` que ya usa
`dlv_app.main._raiz_datos_de_la_app`-- queda pendiente de otra tarea/agente
con `dlv-api/*` en su carril. Este `.spec` SI copia `data/` dentro del
bundle (mas abajo, en `datas`) para que los ficheros EXISTAN fisicamente en
el paquete, pero eso no arregla la ruta que calcula `dlv_api.main`: **sin
ese cambio en `dlv-api`, un `dlv-app` empaquetado con este `.spec` arranca
pero falla al abrir cualquier log real**, porque no encuentra el descriptor
Haltech ni el catalogo de unidades. Ver el informe de la tarea F5-01 para
el detalle completo.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

# `SPECPATH` lo inyecta PyInstaller al ejecutar este fichero (no existe fuera
# de ese contexto): es la carpeta donde vive este `.spec`, es decir `dlv-app/`.
# `RAIZ_REPO` es su PADRE -- la raiz del repositorio, donde `dlv-app/`,
# `dlv-api/`, `dlv-core/` y `data/` son hermanos --, asi que toda ruta de
# aqui en adelante cuelga de `RAIZ_REPO` directamente (NUNCA
# `RAIZ_REPO.parent`, que se saldria del repositorio) y `dlv-app/` en si
# mismo hay que nombrarlo explicitamente cuando haga falta (`ENTRADA`,
# `pathex[0]` mas abajo).
#
# Bug real de F1-35 corregido en F5-01 (herramienta de verificacion:
# `tools/verificar_empaquetado.py`, que ejecuta este `.spec` de verdad con
# `Analysis`/`PYZ`/`EXE`/`COLLECT` sustituidos por comprobantes -- ver su
# docstring): la version anterior de este fichero usaba `RAIZ_REPO / "src"`
# para `ENTRADA`/`pathex[0]` (un nivel de MENOS: le faltaba `dlv-app`) y
# `RAIZ_REPO.parent / ...` para `data/`, `dlv-api/src` y `dlv-core/src` (un
# nivel de MAS: se salia del repositorio). Ninguna de las cuatro rutas
# apuntaba a algo que existiera; un build real habria fallado en el primer
# `Analysis()` con "no such file". Ver el informe de la tarea F5-01 para el
# detalle completo de como se detecto sin tener PyInstaller instalado.
RAIZ_REPO = Path(SPECPATH).resolve().parent  # type: ignore[name-defined]  # noqa: F821

ENTRADA = RAIZ_REPO / "dlv-app" / "src" / "dlv_app" / "main.py"

# `dlv-ui/dist` lo genera `npm run build` (workflow "frontend" de
# `.github/workflows/ci.yml`) y NO se versiona. Un `.spec` que lo omitiera en
# silencio produciria un paquete que arranca -- y hasta parece funcionar,
# porque `dlv_app.main` cae a la pagina placeholder PROVISIONAL en vez de
# fallar -- pero sin el frontend real: exactamente el fallo "arranca en tu
# maquina, falla en la del usuario" que describe el informe de F5-01, solo
# que aqui "la maquina" es cualquiera, incluida la de quien empaqueta. Se
# aborta pronto y con un mensaje que dice el comando que falta, en vez de
# dejar que alguien descubra la pagina PROVISIONAL en el paquete final.
_DIST_UI_ORIGEN = RAIZ_REPO / "dlv-ui" / "dist"
if not (_DIST_UI_ORIGEN / "index.html").is_file():
    raise SystemExit(
        f"dlv_app.spec: no existe {_DIST_UI_ORIGEN / 'index.html'}. "
        "Ejecuta 'npm ci && npm run build' en dlv-ui/ antes de empaquetar "
        "-- ver el workflow 'frontend' de .github/workflows/ci.yml."
    )

a = Analysis(  # type: ignore[name-defined]  # noqa: F821
    [str(ENTRADA)],
    pathex=[
        # Los tres paquetes del workspace se resuelven normalmente via el
        # entorno virtual de `uv sync --all-packages` (instalados editables),
        # pero se declaran aqui tambien como red de seguridad: los finders de
        # instalacion editable de `hatchling` son un punto conocido de friccion
        # con el analisis estatico de modulos de PyInstaller.
        str(RAIZ_REPO / "dlv-app" / "src"),
        str(RAIZ_REPO / "dlv-api" / "src"),
        str(RAIZ_REPO / "dlv-core" / "src"),
    ],
    binaries=[],
    datas=[
        # Descriptores de formato y catalogos de datos: TODO `data/`, no una
        # lista de ficheros escogidos a mano. La tarea F5-01 pedia comprobar
        # que la lista de `data/*.toml` embebidos esta completa; copiar el
        # directorio entero por construccion la deja completa (incluye
        # tambien lo que todavia no carga ningun `import` de hoy, p. ej.
        # `umbrales.toml`/`formulas.toml` -- ver el informe de la tarea sobre
        # por que ninguno de los dos lo abre hoy ni `dlv-api` ni `dlv-core`)
        # y evita que un fichero nuevo en `data/` se quede fuera del paquete
        # sin que nadie actualice este `.spec`. Ver "Problema conocido"
        # arriba: los ficheros SI estan en el bundle, pero `dlv_api.main`
        # todavia no los encuentra ahi bajo PyInstaller -- pendiente de un
        # cambio en `dlv-api`, fuera del carril de F5-01.
        (str(RAIZ_REPO / "data"), "data"),
        # El build de produccion de `dlv-ui` (`npm run build`, no se
        # versiona). Comprobado que existe mas arriba, antes de llamar a
        # `Analysis()`, con un mensaje claro si falta en vez de empaquetar en
        # silencio la pagina placeholder PROVISIONAL de `dlv_app.main`.
        (str(_DIST_UI_ORIGEN), "dlv-ui/dist"),
        # Activos JS que `pywebview` necesita para el puente con el navegador
        # embebido (`webview/js/*.js`: api.js, polyfill.js, etc.). PyInstaller
        # no los detecta por analisis estatico de imports porque no son
        # codigo Python; sin ellos la ventana se abriria pero el puente
        # `js_api`/eventos de pywebview no funcionaria.
        *collect_data_files("webview"),
    ],
    hiddenimports=[
        # `pywebview` elige el backend grafico en tiempo de ejecucion segun
        # la plataforma (`webview/guilib.py`, funcion `initialize()`), no por
        # un `import` estatico que PyInstaller pueda seguir. Hay que declarar
        # a mano los backends candidatos. Lista NO verificada con un build
        # real de PyInstaller (no instalado en este entorno): revisarla en
        # F5-01 con un build real por plataforma, y recortar los que sobren.
        "webview.platforms.winforms",  # Windows sin WebView2 (.NET/WinForms)
        "webview.platforms.edgechromium",  # Windows con WebView2 (el caso
        # comprometido por ADR-002/docs SS3.10: "presente por omision en
        # Windows 10/11 actualizado")
        "webview.platforms.cocoa",  # macOS (WKWebView)
        "webview.platforms.gtk",  # Linux (WebKitGTK)
        "clr_loader",  # puente .NET que usa el backend `edgechromium`/`winforms`
        "bottle",  # servidor HTTP local que usa pywebview para `html=`/`js_api=`
        # `dlv_api.main.preparar_servidor` construye `uvicorn.Config(app,
        # host=host, log_level="info")` sin `loop=`/`http=`/`ws=`: uvicorn
        # los resuelve el con la clave "auto" de `LOOP_SETUPS`/
        # `HTTP_PROTOCOLS`/`WS_PROTOCOLS` (`uvicorn/config.py`), que hace
        # `importlib.import_module(nombre)` con un nombre de cadena, no un
        # `import` estatico que PyInstaller pueda seguir -- mismo patron que
        # los backends de `pywebview` arriba. Tampoco verificado con un build
        # real; los candidatos ausentes en una plataforma (p. ej. `uvloop`
        # en Windows, donde `uvicorn[standard]` no lo instala) deberian
        # quedar como advertencia inocua en el analisis, igual que ya pasa
        # con `webview.platforms.winforms` en Linux/macOS -- a confirmar con
        # el log de advertencias de un build real.
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.loops.uvloop",  # Unix; ausente en Windows a proposito
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",  # puro Python, siempre disponible
        "uvicorn.protocols.http.httptools_impl",  # viene con uvicorn[standard]
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Cada exclusion lleva su motivo a proposito (informe de F5-01): "una
    # exclusion equivocada produce un paquete que arranca en tu maquina y
    # falla en la del usuario" es el fallo tipico de esta tarea, y la unica
    # defensa es poder releer, para cada entrada, POR QUE se cree que nada
    # del arbol de importacion real (`dlv-core` -> polars/numpy, `dlv-api` ->
    # fastapi/uvicorn[standard], `dlv-app` -> pywebview/bottle) la necesita.
    # Ninguna se ha confirmado contra un build real (PyInstaller no esta
    # instalado aqui, ver el docstring del modulo): son exclusiones por
    # ausencia de dependencia declarada, no por haber visto un build que las
    # arrastraba y sobraban. Repasarlas contra el log de advertencias
    # (`build/dlv-app/warn-dlv-app.txt`) de un build real es trabajo
    # pendiente de quien tenga acceso a PyPI.
    excludes=[
        # ADR-001/docs SS3.1: Polars ya evita PyArrow como dependencia
        # directa (lee/escribe Parquet y Arrow IPC por si mismo). Excluirlo
        # aqui es cinturon y tirantes si algun modulo transitivo lo
        # arrastrara igualmente: es la mayor reduccion de tamano disponible
        # para el presupuesto de `docs/02-alcance-y-plan.md` SS2.6 (< 60 MB
        # en ZIP).
        "pyarrow",
        # Interfaces grafica alternativas: ninguna esta en el arbol de
        # dependencias declarado (`dlv-core/pyproject.toml`,
        # `dlv-api/pyproject.toml`, `dlv-app/pyproject.toml`). `pywebview`
        # puede usar un backend Qt (`webview.platforms.qt`), pero esta
        # deliberadamente fuera de `hiddenimports` arriba -- solo se declaran
        # winforms/edgechromium/cocoa/gtk -- asi que Qt no deberia entrar por
        # analisis estatico; se excluye tambien aqui por si algun hook de
        # PyInstaller lo arrastrara de todos modos.
        "tkinter",  # pywebview no tiene backend tkinter; stdlib, pesa por Tcl/Tk
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        # Pila científica/gráfica que ningún paquete del workspace declara.
        # Polars no depende de pandas/scipy; NumPy no depende de matplotlib.
        # Si algo transitivo las arrastrara pese a no estar declaradas, es
        # justo el caso que esta exclusión existe para cortar.
        "matplotlib",
        "pandas",
        "scipy",
        # Notebooks/REPL enriquecido: no hay ningún camino de ejecución de
        # `dlv-app` que los toque (no es un contenedor de notebook).
        "IPython",
        "ipykernel",
        "jupyter",
        "jupyter_client",
        "notebook",
        # Herramientas de test/lint/tipos: dependencias de `[dependency-groups]
        # dev` en el `pyproject.toml` raíz (`pytest`, `hypothesis`, `mypy`,
        # `ruff`), nunca importadas desde código de producción de
        # `dlv-core`/`dlv-api`/`dlv-app`.
        "pytest",
        "_pytest",
        "py",
        "pluggy",
        "hypothesis",
        "mypy",
        "ruff",
        # Utilidades de desarrollo de la propia stdlib: herramientas de
        # migración de código y el IDE incluido, nunca importados por una
        # app en ejecución.
        "lib2to3",
        "idlelib",
        "turtledemo",
        "pydoc_data",  # datos de `pydoc`/`help()` interactivo
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # type: ignore[name-defined]  # noqa: F821

exe = EXE(  # type: ignore[name-defined]  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: los binarios van en COLLECT, no en el exe
    name="dlv-app",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX complica firma/notarizacion (macOS/Windows) para el
    # ahorro de tamano que da aqui; no vale la pena para este paquete
    console=False,  # ventana de escritorio, sin consola (docs SS3.10).
    # Cambiar a True temporalmente al depurar un build real en F5-01.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # type: ignore[name-defined]  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="dlv-app",  # onedir: la carpeta de salida es `dist/dlv-app/`, que
    # luego se comprime a ZIP para distribuirla (nunca `onefile`).
)
