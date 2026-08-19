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

Como se detecta -- MEDIDO contra un Windows real
==================================================
El metodo es el que documenta Microsoft para instalaciones "Evergreen" del
runtime: WebView2 se registra como un "cliente" de EdgeUpdate, con un GUID de
producto fijo, bajo una de estas claves de registro (segun se instalara a
nivel de maquina o de usuario):

    HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{GUID}
    HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{GUID}
    HKEY_CURRENT_USER\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{GUID}

con un valor `pv` (REG_SZ) que es la version instalada; ausente, vacio o
`0.0.0.0` significa "no instalado".

La version anterior de este docstring decia "confianza alta, pero no
verificada contra un Windows real". Ya no: la escribio un agente sin Windows
y se ha comprobado despues en la maquina del propietario -- Windows 11 Pro
10.0.26100 (x64), Python 3.14.6 de 64 bits, Edge/WebView2 151. Lo medido,
punto por punto:

- La clave existe donde el codigo la busca primero: `HKLM\\SOFTWARE\\
  WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-...}` con
  `pv = "151.0.4129.86"`, tipo `REG_SZ` (1). Las variantes sin
  `WOW6432Node` y en `HKCU` no existen en esta maquina.
- `detectar_webview2()` ejecutada en ese interprete devuelve `PRESENTE`, y
  `_version_desde_registro` devuelve esa misma cadena. O sea: la funcion
  publica funciona de extremo a extremo, no solo la clave suelta.
- La vista de registro (`KEY_WOW64_64KEY`/`KEY_WOW64_32KEY`) NO es un
  problema, y se comprobo explicitamente en vez de suponerlo, porque este
  codigo no pasa ningun flag de vista y eso es exactamente lo que podia
  fallar. Medido en las cuatro combinaciones: la ruta con `WOW6432Node` se
  lee igual desde las dos vistas (Windows no vuelve a redirigir una ruta que
  ya la contiene), y la ruta sin `WOW6432Node` falla en la vista de 64 bits
  y se resuelve en la de 32. Consecuencia: un proceso de 64 bits acierta por
  la PRIMERA ubicacion de la lista y uno de 32 bits (que ve la vista de 32
  por omision) acertaria por la SEGUNDA. Las dos primeras ubicaciones no son
  redundantes: son la misma clave vista desde los dos tipos de proceso.
- El propio `pywebview` (6.2.1, el que usa esta app) hace lo mismo. Su
  `webview/platforms/winforms.py::_is_chromium`, leido en esta maquina, abre
  `SOFTWARE\\...\\EdgeUpdate\\Clients\\<GUID>` y lee `pv`, con el MISMO GUID
  del runtime estable y la misma eleccion de `WOW6432Node` segun la
  arquitectura del proceso. Ya no es "varias fuentes de terceros coinciden":
  es la biblioteca que abre la ventana comprobandolo igual.

Falso negativo corregido con esa lectura: `_is_chromium` acepta ademas los
GUID de los canales Beta, Dev y Canary del runtime, y este modulo solo miraba
el estable. Una maquina con solo un canal de vista previa instalado habria
recibido "falta WebView2, descargalo" y el arranque BLOQUEADO (es la unica
rama que devuelve `False`), mientras `pywebview` habria abierto la ventana
sin problema. Los cuatro GUID estan ahora en `_GUIDS_WEBVIEW2`.

Dos cosas de `_is_chromium` que este modulo NO copia, a proposito: exige
tambien .NET Framework >= 4.6.2 y una version de runtime >= 86.0.622.0, y
acepta la anulacion `settings['WEBVIEW2_RUNTIME_PATH']`. Anadirlas aqui
convertiria mas casos en `AUSENTE` (bloqueantes) por criterios que no se han
podido medir contra ninguna maquina que los incumpla, y la regla F5-03 #4
dice que la duda no bloquea. Si alguna vez aparece una maquina donde este
modulo diga PRESENTE y `pywebview` falle igualmente, ahi estan las tres
diferencias por las que empezar a mirar.

Alternativa considerada y descartada: llamar directamente a
`webview.platforms.winforms._is_chromium()` en vez de leer el registro por
cuenta propia. Descartada por un motivo ahora medido y no supuesto: ese
modulo NO se puede importar sin efectos: al importarse ejecuta
`is_chromium = ... _is_chromium() ...` a nivel de modulo y, segun el
resultado, importa el backend (`from . import edgechromium`), que carga el
puente .NET (`clr`). Es decir, para preguntar "puedo abrir una ventana?"
habria que arrancar justo la maquinaria que puede fallar, que es lo que este
modulo existe para evitar. Ademas `_is_chromium` es privada (guion bajo) y
no forma parte de ninguna API estable de `pywebview`.

Que hace en Linux/macOS (regla F5-03 #2)
==========================================
Nada. `detectar_webview2()` devuelve `DESCONOCIDO` sin tocar el registro (que
ademas no existe fuera de Windows) en cuanto `sys.platform != "win32"`, y
`verificar_webview2_y_avisar()` trata `DESCONOCIDO` igual que "no lo se, no
bloqueo" (regla F5-03 #4).

La rama de WebView2 AUSENTE, medida sin desinstalar nada
==========================================================
Era la unica que importaba de verdad y la unica que nunca se habia ejecutado.
Se ejercito en la maquina del propietario sin tocar el sistema: apuntando las
subclaves a un GUID que no existe (`_GUIDS_WEBVIEW2` es sustituible, ver
`tests/test_webview2.py::test_ausente_contra_el_registro_real_de_windows`).
El `winreg` y el registro son los de verdad, las tres lecturas dan el
`FileNotFoundError` de verdad y el resultado es `AUSENTE`. En una pasada
aparte, `verificar_webview2_y_avisar()` devolvio `False` y `MessageBoxW`
pinto un cuadro de dialogo real de Windows (clase `#32770`, titulo
"DataLogViewer") cuyo texto se leyo con `GetDlgItemTextW` y coincidia con
`mensaje_runtime_ausente()`. Lo unico simulado es a que clave se apunta.
"""

from __future__ import annotations

import ctypes
import sys
from enum import Enum, auto
from typing import Any

NOMBRE_RUNTIME = "Microsoft Edge WebView2 Runtime"

# Pagina oficial de descarga (bootstrapper "Evergreen", instala/actualiza el
# runtime compartido -- no el "runtime fijo" para una sola app, que tambien
# existe pero no aplica aqui). NO verificada en vivo: el texto del aviso se
# ha leido de un MessageBoxW real (ver el docstring del modulo), pero que esa
# URL siga sirviendo el instalador es lo unico de este fichero que sigue sin
# medirse -- comprobarlo exige abrirla en un navegador, no ejecutar codigo.
URL_DESCARGA_WEBVIEW2 = "https://developer.microsoft.com/en-us/microsoft-edge/webview2"

# GUID de producto de WebView2 en EdgeUpdate, en el orden en que conviene
# probarlos: primero el runtime estable (el que instala el 99 % de la gente),
# luego los canales de vista previa. Los cuatro son los mismos que usa
# `webview/platforms/winforms.py::_is_chromium` de pywebview 6.2.1, leido en
# la maquina del propietario -- ver "Falso negativo corregido" en el docstring
# del modulo para por que los tres ultimos NO son opcionales. El registro de
# Windows no distingue mayusculas de minusculas en los nombres de clave, pero
# se conservan tal cual por trazabilidad frente a la fuente.
_GUIDS_WEBVIEW2 = (
    "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",  # Runtime estable ("Evergreen")
    "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",  # Beta
    "{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}",  # Dev
    "{65C35B14-6C1D-4122-AC46-7148CC9D6497}",  # Canary
)

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

    Los `type: ignore[attr-defined, unused-ignore]` de mas abajo son el mismo
    caso que el de `_mostrar_aviso_nativo` con `ctypes.windll` (ver su
    docstring): los stubs de `winreg` que usa `mypy` declaran
    `OpenKey`/`QueryValueEx`/`REG_SZ` bajo `sys.platform == "win32"`, asi que
    un `mypy --strict` ejecutado en Linux no los ve, aunque en tiempo de
    ejecucion en Windows si existan.

    El segundo codigo, `unused-ignore`, es el arreglo de un fallo MEDIDO en
    esta sesion, no una precaucion: `mypy --strict` ejecutado en Windows
    resuelve esos atributos perfectamente y por tanto declaraba los cuatro
    `type: ignore` como «Unused "type: ignore" comment» -- cuatro errores,
    comprobacion en rojo. Es decir, la anotacion que hacia falta en Linux
    rompia Windows y viceversa, y como `.github/workflows/ci.yml` corre la
    matriz en ubuntu/windows/macos, no habia forma de tener las tres en
    verde eligiendo una de las dos. `unused-ignore` en la lista es la unica
    combinacion que vale en las dos plataformas: silencia el atributo donde
    falta y silencia la queja por el ignore sobrante donde no. El propio
    `import winreg` no necesita ignorarse: `mypy` sabe que el modulo existe
    (esta en la lista de la stdlib), solo desconoce estos atributos concretos
    con la plataforma objetivo con la que corre alli.

    No se pasa ningun flag de vista de registro (`KEY_WOW64_64KEY`/
    `KEY_WOW64_32KEY`) a proposito: medido en un Windows 11 x64 real, la
    lista de `_ubicaciones` cubre las dos vistas por construccion (ver el
    docstring del modulo), asi que forzar una vista solo quitaria casos.
    """
    import winreg

    try:
        with winreg.OpenKey(hive, subclave) as clave:  # type: ignore[attr-defined, unused-ignore]
            valor, tipo = winreg.QueryValueEx(clave, "pv")  # type: ignore[attr-defined, unused-ignore]
    except FileNotFoundError:
        return None
    except OSError as error:
        # P. ej. `PermissionError`: la clave existe pero no se pudo abrir/leer.
        raise _RegistroIlegible(str(error)) from error
    if tipo != winreg.REG_SZ or not isinstance(valor, str):  # type: ignore[attr-defined, unused-ignore]
        raise _RegistroIlegible(f"tipo de valor inesperado para 'pv': {tipo!r}")
    return valor


def _ubicaciones(winreg: Any) -> tuple[tuple[int, str], ...]:
    """Las (hive, subclave) a probar, en orden, para todos los canales.

    Tres ubicaciones por GUID de `_GUIDS_WEBVIEW2`:

    1. Instalacion de maquina bajo `WOW6432Node` -- donde cae EdgeUpdate en
       un Windows de 64 bits visto por un proceso de 64 bits. Es la que
       acierta en la maquina del propietario (medido, ver el docstring del
       modulo).
    2. Instalacion de maquina "nativa". No es un caso residual de Windows de
       32 bits: medido, es TAMBIEN por donde acierta un proceso de 32 bits en
       un Windows de 64 bits, porque el redirector del registro le traduce
       esta ruta a la anterior.
    3. Instalacion de solo el usuario actual, posible sin permisos de
       administrador.

    Recibe `winreg` como argumento en vez de importarlo aqui por el mismo
    motivo que `_version_desde_registro` lo importa de forma perezosa: este
    modulo tiene que poder importarse en Linux/macOS, donde `winreg` no
    existe. `Any` porque el modulo llega desde un `import` perezoso del
    llamante.
    """
    ubicaciones: list[tuple[int, str]] = []
    for guid in _GUIDS_WEBVIEW2:
        nativa = rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"
        wow64 = rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"
        ubicaciones += [
            (winreg.HKEY_LOCAL_MACHINE, wow64),
            (winreg.HKEY_LOCAL_MACHINE, nativa),
            (winreg.HKEY_CURRENT_USER, nativa),
        ]
    return tuple(ubicaciones)


def detectar_webview2() -> EstadoWebView2:
    """Comprueba si el runtime de WebView2 esta instalado, SIN crear ninguna
    ventana ni importar `pywebview`/`webview`.

    Fuera de Windows devuelve `DESCONOCIDO` sin tocar el registro (regla
    F5-03 #2: esta comprobacion no aplica a Linux/macOS). En Windows,
    `AUSENTE` se devuelve cuando TODAS las ubicaciones de `_ubicaciones` se
    comprobaron con exito y NINGUNA tiene una version instalada (clave
    inexistente, o presente con `pv=0.0.0.0`) -- ver `_version_desde_registro`
    para la distincion entre "la clave no existe" (conclusivo) y "la clave
    existe pero no se pudo leer" (`_RegistroIlegible`, no conclusivo). Si
    CUALQUIERA cae en ese segundo caso, el resultado es `DESCONOCIDO`, no
    `AUSENTE`: "no pude leer el registro" y "lei el registro y no esta" son
    conclusiones distintas (regla F5-03 #4).

    Medido en Windows 11 Pro 10.0.26100 con WebView2 151.0.4129.86 instalado:
    devuelve `PRESENTE` por la primera ubicacion. Medido tambien el camino
    contrario contra el registro real, sin desinstalar nada: `AUSENTE` (ver
    "La rama de WebView2 AUSENTE" en el docstring del modulo).
    """
    if sys.platform != "win32":
        return EstadoWebView2.DESCONOCIDO

    import winreg

    for hive, subclave in _ubicaciones(winreg):
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

    MEDIDO en Windows 11 Pro 10.0.26100: esta funcion se ejecuto de verdad
    --forzando la rama `AUSENTE` contra el registro real, sin desinstalar
    nada (ver el docstring del modulo)-- y pinto un cuadro de dialogo nativo
    de clase `#32770` con titulo "DataLogViewer" y el texto de
    `mensaje_runtime_ausente()`. Hasta esta sesion, ni una sola linea de
    aqui se habia ejecutado nunca.

    Nunca se llama fuera de Windows (ver `verificar_webview2_y_avisar`, que
    solo llega aqui cuando `detectar_webview2()` ya devolvio `AUSENTE`, y eso
    solo pasa en Windows). El modulo `ctypes` es de la stdlib y se importa
    igual en cualquier plataforma, pero su atributo `windll` SOLO existe en
    la build Windows de Python -- el `type: ignore` de la linea de abajo es
    por eso: los stubs de `ctypes` que usa `mypy` declaran `windll` bajo
    `sys.platform == "win32"`, y `mypy` corre tambien en Linux en la CI de
    este proyecto, asi que alli no ve ese atributo aunque en tiempo de
    ejecucion en Windows si exista. El codigo `unused-ignore` que lo
    acompana es por el motivo contrario y esta explicado en
    `_version_desde_registro`. Esta funcion no se ejecuta nunca en
    Linux/macOS (la unica llamada esta detras del `is not EstadoWebView2.
    AUSENTE` de `verificar_webview2_y_avisar`, y ese estado nunca se produce
    fuera de Windows), asi que el `type: ignore` no oculta un fallo real.

    Bloquea hasta que alguien cierra el dialogo, que es lo que se quiere al
    arrancar: si no bloqueara, `main()` seguiria y abriria la ventana que no
    puede abrirse. En la prueba automatica de Windows el aviso se sustituye
    por un doble (`monkeypatch`) justo por eso -- un modal real colgaria
    `pytest` hasta el timeout.
    """
    MB_ICONERROR = 0x10
    ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined, unused-ignore]
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
