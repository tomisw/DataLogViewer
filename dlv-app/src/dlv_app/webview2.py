"""Deteccion del runtime de WebView2 en Windows, ANTES de abrir la ventana
(F5-03, depende de F5-01/`dlv_app.spec`).

El problema real
=================
`pywebview` en Windows usa el backend `edgechromium` (`webview.platforms.
edgechromium`, ya declarado en `hiddenimports` de `dlv_app.spec`), que
necesita el runtime de WebView2 instalado en la maquina. Si falta, dos cosas
malas pasan a la vez:

1. `webview.create_window()`/`webview.start()` fallan con una excepcion de
   pywebview/`clr_loader` que habla de COM o de un DLL que no carga -- no
   dice "falta WebView2" en ningun sitio legible.
2. La app se empaqueta con `console=False` (`dlv_app.spec`): no hay consola
   donde esa excepcion pudiera verse aunque dijera algo util. El usuario ve
   una ventana en blanco, o nada.

Este modulo comprueba el runtime ANTES de intentar crear la ventana, para
poder avisar con un mensaje que si dice que falta, por que, y de donde se
descarga -- y para avisar con un cuadro de dialogo nativo de Windows
(`ctypes`/`MessageBoxW`), no con una ventana `pywebview`: abrir una ventana
`pywebview` es precisamente lo que no funciona sin este runtime, asi que no
sirve como canal para el propio aviso.

Como se detecta (confianza: alta, pero no verificada contra un Windows real)
==============================================================================
El metodo es el que documenta Microsoft para instalaciones "Evergreen" del
runtime: WebView2 se registra como un "cliente" de EdgeUpdate, con un GUID de
producto fijo, bajo una de estas claves de registro (segun se instalara a
nivel de maquina o de usuario):

    HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{GUID}
    HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{GUID}
    HKEY_CURRENT_USER\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{GUID}

con un valor `pv` (REG_SZ) que es la version instalada; ausente, vacio o
`0.0.0.0` significa "no instalado". El GUID (`_GUID_PRODUCTO_WEBVIEW2` mas
abajo) es el mismo para todo el mundo -- lo usa Microsoft internamente para
identificar el producto "WebView2 Runtime", no algo especifico de esta app.

Esto NO se ha podido confirmar contra una maquina Windows real ni contra la
documentacion oficial en vivo (`learn.microsoft.com` esta bloqueado por el
proxy de salida de este entorno, ver el informe de la tarea). Se confirmo por
busqueda contra paginas de terceros que citan la misma clave/GUID/valor
(incluyendo hilos del propio repositorio oficial `MicrosoftEdge/
WebView2Feedback` en GitHub) y contra multiples fuentes independientes que
coinciden en el mismo GUID, asi que la confianza es alta pero no total. Si
una maquina real contradice esto, es una pista sobre la clave/valor exactos,
no sobre si el enfoque general (registro de EdgeUpdate) es el correcto.

Alternativa considerada y descartada: preguntarle a `pywebview` (p. ej. su
modulo `webview.platforms.edgechromium`) si el runtime esta presente, en vez
de leer el registro por cuenta propia. Se descarta porque ese modulo no
existe en este entorno (sin PyPI, `pywebview` no esta instalado, ver el
informe de F5-01) y por tanto no se pudo leer su codigo para confirmar que
exponga una comprobacion asi ni como se llama.

Que hace en Linux/macOS (regla F5-03 #2)
==========================================
Nada. `detectar_webview2()` devuelve `DESCONOCIDO` sin tocar el registro (que
ademas no existe fuera de Windows) en cuanto `sys.platform != "win32"`, y
`verificar_webview2_y_avisar()` trata `DESCONOCIDO` igual que "no lo se, no
bloqueo" (regla F5-03 #4). Este modulo se importa y se ejecuta en este mismo
entorno (Linux) precisamente para probar esa rama de verdad, no simulada.
"""

from __future__ import annotations

import ctypes
import sys
from enum import Enum, auto

NOMBRE_RUNTIME = "Microsoft Edge WebView2 Runtime"

# Pagina oficial de descarga (bootstrapper "Evergreen", instala/actualiza el
# runtime compartido -- no el "runtime fijo" para una sola app, que tambien
# existe pero no aplica aqui). Confirmada por busqueda coincidente en varias
# fuentes independientes; no verificada en vivo (ver docstring del modulo).
URL_DESCARGA_WEBVIEW2 = "https://developer.microsoft.com/en-us/microsoft-edge/webview2"

# GUID de producto fijo de "WebView2 Runtime" en EdgeUpdate (ver docstring del
# modulo). Iguales mayusculas/formato que Microsoft usa en su documentacion y
# en los ejemplos de deteccion que circulan; el registro de Windows no
# distingue mayusculas de minusculas para nombres de clave, pero se conserva
# tal cual por trazabilidad frente a la fuente.
_GUID_PRODUCTO_WEBVIEW2 = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

# Tres ubicaciones posibles, en el orden en que tiene sentido comprobarlas:
# instalacion de maquina (vista de 32 bits en un Windows de 64 bits, que es
# donde cae EdgeUpdate normalmente), instalacion de maquina "nativa" (Windows
# de 32 bits, minoritario hoy pero sin coste comprobarlo), e instalacion de
# solo el usuario actual (posible sin permisos de administrador).
_SUBCLAVE_MAQUINA_WOW64 = (
    rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_GUID_PRODUCTO_WEBVIEW2}"
)
_SUBCLAVE_MAQUINA = rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_GUID_PRODUCTO_WEBVIEW2}"
_SUBCLAVE_USUARIO = rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_GUID_PRODUCTO_WEBVIEW2}"

_VERSION_NO_INSTALADO = "0.0.0.0"


class EstadoWebView2(Enum):
    """Resultado de `detectar_webview2()`.

    Deliberadamente NO hay un valor "no aplica" separado de `DESCONOCIDO`:
    ambos casos ("esto no es Windows" y "es Windows pero no se pudo leer el
    registro") significan lo mismo para quien llama -- no bloquear el
    arranque (regla F5-03 #4, "no lo se" no es "no lo tengo") -- y separarlos
    solo anadiria un estado mas que comprobar sin cambiar ninguna decision.
    """

    PRESENTE = auto()
    AUSENTE = auto()
    DESCONOCIDO = auto()


class _RegistroIlegible(Exception):
    """La clave de registro EXISTE pero no se pudo interpretar su valor
    (permiso denegado, tipo inesperado) -- deliberadamente distinta de
    "la clave no existe" (`FileNotFoundError`, ver `_version_desde_registro`):
    esta segunda es una lectura concluyente ("el producto no esta instalado
    en esta ubicacion"), la primera no lo es. Confundirlas es exactamente el
    error que la regla F5-03 #4 pide evitar -- una version anterior de este
    modulo las trataba igual y por tanto devolvia `DESCONOCIDO` en el caso
    mas comun de todos (ninguna de las tres claves existe porque el runtime
    nunca se instalo), en vez de `AUSENTE`.
    """


def _version_desde_registro(hive: int, subclave: str) -> str | None:
    """Lee el valor `pv` de `subclave` bajo `hive`.

    Devuelve `None` si la clave sencillamente no existe -- el caso normal
    cuando WebView2 no esta instalado en ESA ubicacion concreta (puede
    seguir estandolo en otra de las tres, o en ninguna). Lanza
    `_RegistroIlegible` si la clave SI existe pero no se pudo interpretar
    (permiso denegado, o el valor `pv` no es la cadena `REG_SZ` esperada):
    eso es lo que de verdad no se puede concluir.

    Importa `winreg` de forma perezosa (dentro de la funcion, no a nivel de
    modulo) porque ese modulo solo existe en la distribucion Windows de
    Python: un `import winreg` a nivel de modulo romperia `import dlv_app.
    webview2` -- y con el, `pytest` -- en Linux/macOS. Quien llama a esta
    funcion (`detectar_webview2`) ya garantiza `sys.platform == "win32"`
    antes de invocarla.

    Los `type: ignore[attr-defined]` de mas abajo son el mismo caso que el de
    `_mostrar_aviso_nativo` con `ctypes.windll` (ver su docstring): los stubs
    de `winreg` que usa `mypy` declaran `OpenKey`/`QueryValueEx`/`REG_SZ`
    bajo `sys.platform == "win32"`, y `mypy --strict` corre en Linux en este
    proyecto (ver el informe de la tarea), asi que no los ve -- aunque en
    tiempo de ejecucion en Windows si existan. El propio `import winreg` de
    la linea de arriba no necesita ignorarse: `mypy` sabe que el modulo
    `winreg` existe (esta en la lista de la stdlib), solo desconoce estos
    atributos concretos con la plataforma objetivo con la que corre aqui.
    """
    import winreg

    try:
        with winreg.OpenKey(hive, subclave) as clave:  # type: ignore[attr-defined]
            valor, tipo = winreg.QueryValueEx(clave, "pv")  # type: ignore[attr-defined]
    except FileNotFoundError:
        return None
    except OSError as error:
        # P. ej. `PermissionError`: la clave existe pero no se pudo abrir/leer.
        raise _RegistroIlegible(str(error)) from error
    if tipo != winreg.REG_SZ or not isinstance(valor, str):  # type: ignore[attr-defined]
        raise _RegistroIlegible(f"tipo de valor inesperado para 'pv': {tipo!r}")
    return valor


def detectar_webview2() -> EstadoWebView2:
    """Comprueba si el runtime de WebView2 esta instalado, SIN crear ninguna
    ventana ni importar `pywebview`/`webview`.

    Fuera de Windows devuelve `DESCONOCIDO` sin tocar el registro (regla
    F5-03 #2: esta comprobacion no aplica a Linux/macOS). En Windows,
    `AUSENTE` se devuelve cuando las tres ubicaciones se comprobaron con
    exito y NINGUNA tiene una version instalada (clave inexistente, o
    presente con `pv=0.0.0.0`) -- ver `_version_desde_registro` para la
    distincion entre "la clave no existe" (conclusivo) y "la clave existe
    pero no se pudo leer" (`_RegistroIlegible`, no conclusivo). Si CUALQUIERA
    de las tres cae en ese segundo caso, el resultado es `DESCONOCIDO`, no
    `AUSENTE`: "no pude leer el registro" y "lei el registro y no esta" son
    conclusiones distintas (regla F5-03 #4).
    """
    if sys.platform != "win32":
        return EstadoWebView2.DESCONOCIDO

    import winreg

    ubicaciones = (
        (winreg.HKEY_LOCAL_MACHINE, _SUBCLAVE_MAQUINA_WOW64),
        (winreg.HKEY_LOCAL_MACHINE, _SUBCLAVE_MAQUINA),
        (winreg.HKEY_CURRENT_USER, _SUBCLAVE_USUARIO),
    )
    for hive, subclave in ubicaciones:
        try:
            version = _version_desde_registro(hive, subclave)
        except _RegistroIlegible:
            return EstadoWebView2.DESCONOCIDO
        if version is not None and version != _VERSION_NO_INSTALADO:
            return EstadoWebView2.PRESENTE
        # `version is None` (clave inexistente en esta ubicacion) o
        # `version == "0.0.0.0"` (clave presente, sin producto instalado):
        # las dos son lecturas concluyentes de "aqui no esta"; sigue
        # probando las demas ubicaciones antes de concluir AUSENTE.

    return EstadoWebView2.AUSENTE


def mensaje_runtime_ausente() -> str:
    """Mensaje accionable: que falta, por que, y de donde se descarga (regla
    F5-03 #3). Funcion aparte de `verificar_webview2_y_avisar` para que las
    pruebas puedan comprobar el texto sin tener que simular un `MessageBoxW`.
    """
    return (
        f"No se encontro el {NOMBRE_RUNTIME}.\n\n"
        "DataLogViewer necesita este componente de Windows para mostrar su "
        "interfaz (usa el motor de Microsoft Edge integrado en el sistema, "
        "no incluye uno propio).\n\n"
        f"Descargalo desde la pagina oficial de Microsoft:\n{URL_DESCARGA_WEBVIEW2}\n\n"
        "El instalador 'Evergreen Bootstrapper' de esa pagina basta: es "
        "pequeno y descarga el resto. Tras instalarlo, vuelve a abrir "
        "DataLogViewer."
    )


def _mostrar_aviso_nativo(mensaje: str) -> None:
    """Muestra `mensaje` en un cuadro de dialogo nativo de Windows via
    `ctypes`/`user32.MessageBoxW`, sin pasar por `pywebview`.

    Nunca se llama fuera de Windows (ver `verificar_webview2_y_avisar`, que
    solo llega aqui cuando `detectar_webview2()` ya devolvio `AUSENTE`, y eso
    solo pasa en Windows). El modulo `ctypes` es de la stdlib y se importa
    igual en cualquier plataforma, pero su atributo `windll` SOLO existe en
    la build Windows de Python -- el `type: ignore` de la linea de abajo es
    por eso: los stubs de `ctypes` que usa `mypy` declaran `windll` bajo
    `sys.platform == "win32"`, y este comando corre en Linux (ver el informe
    de la tarea), asi que `mypy` no ve ese atributo aunque en tiempo de
    ejecucion en Windows si exista. Esta funcion no se ejecuta nunca en
    Linux/macOS (la unica llamada esta detras del `is not EstadoWebView2.
    AUSENTE` de `verificar_webview2_y_avisar`, y ese estado nunca se produce
    fuera de Windows), asi que el `type: ignore` no oculta un fallo real.
    """
    MB_ICONERROR = 0x10
    ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
        None, mensaje, "DataLogViewer", MB_ICONERROR
    )


def verificar_webview2_y_avisar() -> bool:
    """Comprueba el runtime de WebView2 (solo en Windows, ver
    `detectar_webview2`) y, si se CONFIRMA que falta, muestra el aviso
    nativo (`_mostrar_aviso_nativo`) con `mensaje_runtime_ausente()`.

    Devuelve `False` solo en ese caso confirmado -- quien llama (`dlv_app.
    main.main`) debe entonces NO crear ninguna ventana, porque ya se
    avisaria de nuevo con una excepcion sin contexto. Devuelve `True` en
    cualquier otro caso (`PRESENTE`, `DESCONOCIDO`, o plataforma distinta de
    Windows): un resultado no concluyente nunca debe impedir el arranque de
    una app que podria funcionar perfectamente (regla F5-03 #4).
    """
    if detectar_webview2() is not EstadoWebView2.AUSENTE:
        return True
    _mostrar_aviso_nativo(mensaje_runtime_ausente())
    return False
