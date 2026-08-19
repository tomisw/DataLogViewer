# -*- mode: python ; coding: utf-8 -*-
"""Especificacion de PyInstaller para `dlv-app`, modo `onedir` (ADR-002,
`docs/03-arquitectura.md` SS3.10): una carpeta con el ejecutable y sus
dependencias, distribuida como ZIP -- deliberadamente NO `onefile`.
`onefile` se descomprime en un directorio temporal en cada arranque (segundos
de mas, y escribe fuera de la carpeta del programa), lo que rompe el modo
portable que exige SS3.10 ("con un portable.txt junto al ejecutable, la app
no escribe nada fuera de su carpeta"). `onedir` no descomprime nada al
arrancar y es igual de portable distribuido en ZIP.

Estado de este fichero: MEDIDO con un build real en Windows
==============================================================
Este fichero lo escribio un agente sin PyInstaller (PyPI daba 403 en su
entorno), asi que decia que **nada de lo de abajo se habia ejecutado con un
build real**. Ya no es asi: se ha construido de verdad en la maquina del
propietario -- Windows 11 Pro 10.0.26100 x64, Python 3.14.6, PyInstaller
6.21.0, `pyinstaller --noconfirm --clean dlv_app.spec` -- y lo que salio
esta anotado aqui abajo. Lo que se midio:

- El build termina sin errores (~100 s en frio, ~70 s con cache).
- `dist/dlv-app/dlv-app.exe` arranca, `dlv-api` levanta dentro del paquete
  ("Application startup complete") y responde `GET /salud` 200.
- Encuentra sus ficheros de `data/` dentro del paquete. Esto es lo que de
  verdad habia que comprobar y lo que ninguna prueba del repositorio puede
  comprobar (ver `dlv_api.main._raiz_de_datos`): con un log real Haltech
  (copia de `samples/real/AutoLog_20260729_1830.csv`, que no se toca) el log
  de uvicorn del proceso congelado muestra `GET /comandos/unidades` 200 ->
  `data/units.toml` localizado, `POST /comandos/abrir-log` 200 ->
  `data/formats/haltech_nsp.toml` y los catalogos de roles/alias/
  combustibles localizados, y ocho `POST /comandos/cubos` 200 -> la piramide
  sirviendo datos reales al renderizador. La ventana se cierra y el proceso
  sale con codigo 0.
- El backend `edgechromium` de `pywebview` funciona en el paquete: la
  ventana "DataLogViewer" aparece (WebView2 151 instalado en esa maquina).
- `collect_data_files("webview")` aporta 15 ficheros, presentes en
  `dist/dlv-app/_internal/webview/`.

PRESUPUESTO SUPERADO, y no se ajusta el limite (`docs/02` SS2.6)
------------------------------------------------------------------
`python tools/empaquetar.py` sobre ese build, medido:

    onedir sin comprimir: 242,0 MB  (limite 150 MB)
    ZIP:                   83,4 MB  (limite  60 MB)

Un solo directorio explica casi todo: `_internal/_polars_runtime_32` son
176 MB de los 242. Es el binario de Polars (la variante de indices de 32
bits) y entra entero. Lo siguiente ya es pequeno en comparacion:
`numpy.libs` 21 MB, `python314.dll` 7 MB, `numpy` 7 MB, `pydantic_core`
6 MB. Es decir, ni los `excludes` de mas abajo ni `dlv-ui/dist` mueven la
aguja: el presupuesto lo decide Polars. Queda como dato para el propietario,
que es quien decide si el limite era optimista o si hay que empaquetar
Polars de otra forma; aqui no se toca ninguno de los dos numeros.

Lo que sigue SIN medir despues de esta sesion: el build en macOS y en Linux
(los `excludes` y los `hiddenimports` de esas plataformas siguen sin
confirmar), el arranque en frio cronometrado, y si los `excludes` recortan
algo que haga falta en un camino de ejecucion que la prueba de humo no
recorrio.

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

Problema conocido de F5-01: RESUELTO y COMPROBADO en el paquete
=================================================================
La version anterior de este docstring avisaba de que `dlv_api.main`
localizaba el descriptor Haltech y el catalogo de unidades contando
`.parents[3]` desde `__file__`, lo que bajo PyInstaller `onedir` con
`noarchive=False` no tiene equivalente valido (el bytecode vive dentro del
`PYZ`, `__file__` no aterriza en ninguna ruta real), y concluia: **el
paquete arranca pero falla al abrir cualquier log real**. Estaba fuera del
carril de F5-01 y quedo pendiente.

Ya no lo esta: `dlv_api.main._raiz_de_datos` usa el mismo patron
`sys.frozen`/`sys._MEIPASS` que `dlv_app.main._raiz_datos_de_la_app`, y este
`.spec` copia `data/` entero dentro del bundle (ver `datas`). Comprobado con
el build real descrito arriba: el paquete abre un log Haltech real y sirve
sus cubos. Era la afirmacion mas cara de este fichero --describia un fallo
que solo se manifiesta en la maquina de quien usa el ZIP-- y ahora esta
medida en esa clase de maquina.
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

# El script de entrada es `__main__.py`, NO `main.py`. Medido en el build real
# de esta maquina (ver "Estado de este fichero" arriba): con `main.py` como
# entrada, el ejecutable congelado ejecuta su bloque `if __name__ ==
# "__main__": main()`, que llama a `main()` SIN argumentos -- el `argparse` que
# convierte `dlv-app.exe <ruta_del_log>` en `main(log=...)` vive en
# `dlv_app/__main__.py` y no se ejecutaba nunca. Sintoma medido: el paquete
# arrancaba, abria la ventana y `dlv-api` respondia a `/salud`, pero pasarle un
# log real por la linea de ordenes no producia NINGUNA llamada a `/comandos/*`
# en el log de uvicorn -- el frontend caia a su fuente sintetica. Es decir, el
# ZIP arrancaba y no podia abrir un log, que es justo lo que el ZIP existe para
# hacer. `__main__.py` importa `dlv_app.main`, asi que el arbol de modulos que
# analiza PyInstaller es el mismo mas `argparse`.
ENTRADA = RAIZ_REPO / "dlv-app" / "src" / "dlv_app" / "__main__.py"

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
        # a mano los backends candidatos. MEDIDO en el build de Windows: las
        # once entradas de esta lista se resolvieron, PyInstaller no emitio
        # ni un "Hidden import ... not found" para ninguna (los tres que si
        # emitio son `pycparser.lextab`/`yacctab` y `tzdata`, de hooks de
        # terceros, no de aqui), y la ventana abrio con `edgechromium`.
        # Sigue sin medirse en macOS y Linux, donde `cocoa`/`gtk` son los que
        # importan.
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
        # el log de advertencias de un build real. Medido en Windows: el
        # unico ausente es `uvloop`, y aparece solo como modulo transitivo
        # que falta ("imported by uvicorn.loops.uvloop"), inocuo tal como se
        # esperaba; el resto se resolvio.
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
    # Medido en el build real de Windows (ver el docstring del modulo): el
    # paquete construye, arranca y abre un log con esta lista puesta, asi que
    # ninguna de estas exclusiones corta nada que el camino de ejecucion
    # probado necesite. Lo que ese build NO demuestra es que hicieran falta:
    # de los quince nombres, los unicos presentes en el entorno son `pytest`,
    # `hypothesis`, `mypy` y `ruff` (dependencias de desarrollo) y `tkinter`
    # (stdlib); `pyarrow`, `pandas`, `scipy`, `matplotlib`, Qt y la pila de
    # notebooks no estan instalados, asi que sus exclusiones son cinturon y
    # tirantes por si algun dia entraran, no ahorro observado. El log de
    # advertencias del build vive en `build/dlv_app/warn-dlv_app.txt` (con
    # guion BAJO: el nombre lo pone el `.spec`, no el `name=` del `EXE`; la
    # version anterior de este comentario decia `warn-dlv-app.txt`, que no
    # existe). Sin medir en macOS y Linux.
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
    # NO hace falta cambiarlo a True para depurar, contra lo que decia este
    # comentario. Medido con el bootloader `runw.exe` de PyInstaller 6.21 en
    # Windows: si quien lanza el ejecutable le pasa tuberias para stdout/
    # stderr (`subprocess.Popen(..., stderr=subprocess.STDOUT)`), el proceso
    # congelado SI escribe ahi, y se lee el log de uvicorn entero -- que es
    # como se comprobo que el paquete abre un log real (las lineas
    # `POST /comandos/abrir-log 200` del docstring del modulo). Lo que no hay
    # es consola si nadie la proporciona, que es lo que se queria.
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
