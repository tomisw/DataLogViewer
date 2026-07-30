# -*- mode: python ; coding: utf-8 -*-
"""Especificacion de PyInstaller para `dlv-app`, modo `onedir` (ADR-002,
`docs/03-arquitectura.md` SS3.10): una carpeta con el ejecutable y sus
dependencias, distribuida como ZIP -- deliberadamente NO `onefile`.
`onefile` se descomprime en un directorio temporal en cada arranque (segundos
de mas, y escribe fuera de la carpeta del programa), lo que rompe el modo
portable que exige SS3.10 ("con un portable.txt junto al ejecutable, la app
no escribe nada fuera de su carpeta"). `onedir` no descomprime nada al
arrancar y es igual de portable distribuido en ZIP.

Estado de este fichero (tarea F1-35)
=====================================
Esta tarea entrega la CONFIGURACION, no el binario: PyInstaller no esta
instalado en el entorno donde se escribio este fichero (es una dependencia de
empaquetado/desarrollo; ver el informe de la tarea -- se necesita decision de
si anadirla a `dlv-app/pyproject.toml` como grupo de dependencias de
desarrollo). Ejecutar `pyinstaller dlv_app.spec` de verdad, medir el arranque
en frio y el tamano del paquete contra los presupuestos de
`docs/02-alcance-y-plan.md` SS2.6 y ajustar `hiddenimports`/`excludes` con un
build real es trabajo de F5-01, no de esta tarea. Este fichero solo se
comprobo sintacticamente (es un modulo Python valido); no se genero ningun
`build/`/`dist/` con el.

Problema conocido, NO resuelto aqui (para F5-01)
==================================================
`dlv_api.main` localiza el descriptor de formato Haltech y el catalogo de
unidades por ruta relativa al propio fichero fuente:

    _RAIZ_REPO = Path(__file__).resolve().parents[3]
    _DESCRIPTOR_HALTECH = _RAIZ_REPO / "data" / "formats" / "haltech_nsp.toml"
    _UNITS_TOML = _RAIZ_REPO / "data" / "units.toml"

Bajo PyInstaller `onedir`, `__file__` apunta dentro de la carpeta de
extraccion del paquete (tipicamente `_internal/dlv_api/main.py`), y
`.parents[3]` ya NO coincide con la raiz del repositorio ni con la carpeta
del ejecutable: la cuenta de niveles que funciona en el arbol de desarrollo
no tiene un equivalente valido en el arbol congelado. El propio
`dlv-api/src/dlv_api/main.py` deja esto anotado como pendiente de F5-01.

Este `.spec` copia `data/` dentro del bundle (mas abajo, en `datas`) para que
los ficheros EXISTAN fisicamente en el paquete, pero **eso no arregla la ruta
que calcula `dlv_api.main`**: hace falta un cambio en `dlv-api` (p. ej.
resolver la raiz de datos via `sys._MEIPASS` cuando `sys.frozen` es verdadero,
en vez de contar `.parents[]` desde `__file__`) que no es responsabilidad de
esta tarea -- no se toca `dlv-api/*` aqui (ver restricciones de F1-35) -- y
que F5-01 debe abordar de forma explicita. Sin ese cambio, un `dlv-app`
empaquetado con este `.spec` arrancaria pero fallaria al abrir cualquier log
real, porque no encontraria el descriptor Haltech ni el catalogo de unidades.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

# `SPECPATH` lo inyecta PyInstaller al ejecutar este fichero (no existe fuera
# de ese contexto): es la carpeta donde vive este `.spec`, es decir `dlv-app/`.
RAIZ_REPO = Path(SPECPATH).resolve().parent  # type: ignore[name-defined]  # noqa: F821

ENTRADA = RAIZ_REPO / "src" / "dlv_app" / "main.py"

a = Analysis(  # type: ignore[name-defined]  # noqa: F821
    [str(ENTRADA)],
    pathex=[
        # Los tres paquetes del workspace se resuelven normalmente via el
        # entorno virtual de `uv sync --all-packages` (instalados editables),
        # pero se declaran aqui tambien como red de seguridad: los finders de
        # instalacion editable de `hatchling` son un punto conocido de friccion
        # con el analisis estatico de modulos de PyInstaller.
        str(RAIZ_REPO / "src"),
        str(RAIZ_REPO.parent / "dlv-api" / "src"),
        str(RAIZ_REPO.parent / "dlv-core" / "src"),
    ],
    binaries=[],
    datas=[
        # Descriptores de formato y catalogos de datos (ver "Problema
        # conocido" arriba: estan en el bundle, pero `dlv_api.main` todavia
        # no los encuentra ahi -- pendiente de F5-01).
        (str(RAIZ_REPO.parent / "data"), "data"),
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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ADR-001/docs SS3.1: Polars ya evita PyArrow como dependencia
        # directa (lee/escribe Parquet y Arrow IPC por si mismo). Excluirlo
        # aqui es cinturon y tirantes si algun modulo transitivo lo
        # arrastrara igualmente: es la mayor reduccion de tamano disponible
        # para el presupuesto de `docs/02-alcance-y-plan.md` SS2.6 (< 60 MB
        # en ZIP).
        "pyarrow",
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
