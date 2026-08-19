"""Pruebas de `dlv_app.webview2` (F5-03).

Este modulo NO importa `webview`/`pywebview` (la deteccion es independiente
de esa dependencia, ver su docstring), asi que estas pruebas no necesitan
`pytest.importorskip("webview")` como `test_main.py`: corren siempre, incluso
en este sandbox sin `pywebview` instalado.

Este fichero lo escribio un agente que solo tenia Linux, y lo daba por
supuesto: `test_detectar_webview2_fuera_de_windows_no_toca_nada` empezaba con
`assert sys.platform != "win32"`, asi que en Windows la prueba FALLABA -- no
se saltaba, fallaba. Como la matriz de `.github/workflows/ci.yml` incluye
`windows-latest`, ese trabajo estaba en rojo. Ahora la plataforma decide que
se ejecuta de verdad y que se simula, en las dos direcciones:

- La rama "no es Windows" corre contra el interprete real en Linux/macOS y se
  simula con `monkeypatch` en Windows.
- La rama Windows (lectura de registro) se simula con un modulo `winreg`
  falso en Linux/macOS -- `detectar_webview2`/`_version_desde_registro`
  importan `winreg` de forma perezosa justo para permitir esto -- y en
  Windows hay ademas dos pruebas que NO simulan nada: leen el registro de
  verdad, tanto para el caso instalado como para el ausente (este ultimo
  apuntando a un GUID inexistente, sin desinstalar nada del sistema).
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from dlv_app import webview2
from dlv_app.webview2 import (
    NOMBRE_RUNTIME,
    URL_DESCARGA_WEBVIEW2,
    EstadoWebView2,
    detectar_webview2,
    mensaje_runtime_ausente,
    verificar_webview2_y_avisar,
)

ES_WINDOWS = sys.platform == "win32"

# Cualquier cadena que no sea "win32" sirve para la rama "no es Windows"; se
# usa "linux" por ser la plataforma donde esa rama corre de verdad.
_PLATAFORMA_NO_WINDOWS = "linux"


class _WinregProhibido:
    """Modulo `winreg` que estalla al primer acceso a cualquier atributo.

    En la rama "no es Windows" la afirmacion no es solo "devuelve
    DESCONOCIDO", es "no toca el registro". En Linux eso se cumple por
    construccion (no hay `winreg` que importar). En Windows si lo hay, asi que
    la unica forma de comprobar lo mismo es poner en su sitio algo que falle
    ruidosamente si alguien lo usa.
    """

    def __getattr__(self, nombre: str) -> object:
        raise AssertionError(f"no se debe tocar el registro fuera de Windows (winreg.{nombre})")


def _simular_no_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", _PLATAFORMA_NO_WINDOWS)
    monkeypatch.setitem(sys.modules, "winreg", _WinregProhibido())


def test_detectar_webview2_fuera_de_windows_no_toca_nada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regla F5-03 #2: en una plataforma que no es Windows la comprobacion no
    debe hacer nada ni fallar -- "no hacer nada" significa no intentar
    `import winreg` y devolver `DESCONOCIDO`.

    En Linux/macOS corre contra `sys.platform` de verdad. En Windows se
    simula la plataforma (y se sabotea `winreg`, ver `_WinregProhibido`)
    porque no hay otra forma de ejercitar esa rama ahi -- lo que NO se hace es
    lo que hacia la version anterior de esta prueba: dar por sentado que el
    entorno es Linux y fallar en Windows.
    """
    if ES_WINDOWS:
        _simular_no_windows(monkeypatch)
    assert sys.platform != "win32"

    assert detectar_webview2() is EstadoWebView2.DESCONOCIDO


def test_verificar_webview2_y_avisar_fuera_de_windows_devuelve_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El llamante (`dlv_app.main.main`) debe poder seguir arrancando: un
    resultado no concluyente nunca bloquea (regla F5-03 #4).
    """
    if ES_WINDOWS:
        _simular_no_windows(monkeypatch)

    assert verificar_webview2_y_avisar() is True


class _ClaveFalsa:
    """Contexto de `winreg.OpenKey` falso: no guarda nada por si mismo, el
    valor a devolver ya se resolvio en `_open_key` (ver `_winreg_falso`).
    """

    def __enter__(self) -> _ClaveFalsa:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


# Lo que puede pasar al intentar leer una ubicacion del registro:
# - `None`: la clave no existe -- `winreg.OpenKey` real lanza
#   `FileNotFoundError` (subclase de `OSError`) en este caso.
# - una `OSError` (p. ej. `PermissionError(...)`): la clave existe pero no se
#   pudo abrir/leer -- se relanza tal cual.
# - `(version, tipo)`: lectura correcta, como devolveria `QueryValueEx` real.
_ResultadoUbicacion = tuple[str, int] | OSError | None

# Nombre logico de hive (para que las pruebas no dependan de los valores
# numericos exactos de HKEY_LOCAL_MACHINE/HKEY_CURRENT_USER) mas la subclave.
# Hace falta indexar por LOS DOS, no solo por subclave: `_SUBCLAVE_MAQUINA` y
# `_SUBCLAVE_USUARIO` (ver `dlv_app.webview2`) son la MISMA cadena de subclave
# -- solo difieren en el hive (HKLM vs HKCU) -- asi que un diccionario
# indexado solo por subclave colapsaria esas dos ubicaciones en una.
_Ubicacion = tuple[str, str]


def _winreg_falso(valores_por_ubicacion: dict[_Ubicacion, _ResultadoUbicacion]) -> Any:
    """Construye un modulo `winreg` falso cuyo `OpenKey`/`QueryValueEx`
    devuelven o lanzan lo indicado en `valores_por_ubicacion` (ver
    `_ResultadoUbicacion`/`_Ubicacion`).

    Solo implementa lo que `dlv_app.webview2` usa: `OpenKey`, `QueryValueEx`,
    `REG_SZ`, `HKEY_LOCAL_MACHINE`, `HKEY_CURRENT_USER`. Cualquier ubicacion
    no listada en absoluto tambien se trata como inexistente
    (`FileNotFoundError`), igual que `None` explicito.
    """
    modulo = types.ModuleType("winreg")
    modulo.REG_SZ = 1  # type: ignore[attr-defined]
    modulo.HKEY_LOCAL_MACHINE = 0x80000002  # type: ignore[attr-defined]
    modulo.HKEY_CURRENT_USER = 0x80000001  # type: ignore[attr-defined]

    _nombres_hive = {
        modulo.HKEY_LOCAL_MACHINE: "HKLM",  # type: ignore[attr-defined]
        modulo.HKEY_CURRENT_USER: "HKCU",  # type: ignore[attr-defined]
    }

    # `OpenKey` devuelve un contexto vacio y deja el resultado (version,
    # tipo) guardado aqui para que `QueryValueEx` -- que en la API real de
    # `winreg` no recibe la ubicacion, solo el objeto de clave ya abierto --
    # lo pueda devolver sin necesitar mas estado que este cierre.
    resultado_activo: list[tuple[str, int]] = []

    def _open_key(hive: int, subclave: str) -> _ClaveFalsa:
        ubicacion = (_nombres_hive[hive], subclave)
        resultado = valores_por_ubicacion.get(ubicacion)
        if resultado is None:
            raise FileNotFoundError(f"clave no encontrada (simulada): {ubicacion}")
        if isinstance(resultado, OSError):
            raise resultado
        resultado_activo.append(resultado)
        return _ClaveFalsa()

    def _query_value_ex(_clave: _ClaveFalsa, nombre: str) -> tuple[str, int]:
        assert nombre == "pv"
        return resultado_activo.pop()

    modulo.OpenKey = _open_key  # type: ignore[attr-defined]
    modulo.QueryValueEx = _query_value_ex  # type: ignore[attr-defined]
    return modulo


def _simular_windows(
    monkeypatch: pytest.MonkeyPatch, valores_por_ubicacion: dict[_Ubicacion, _ResultadoUbicacion]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", _winreg_falso(valores_por_ubicacion))


# Las tres ubicaciones que `dlv_app.webview2` consulta, en el orden en que las
# consulta -- la subclave se repite aqui literalmente (no se importa del
# modulo) para que la prueba tambien detecte si alguien la cambia sin
# querer. `_SUBCLAVE_MAQUINA` y `_SUBCLAVE_USUARIO` son la misma cadena en el
# modulo real (solo cambia el hive), asi que aqui basta una constante para
# las dos y se distinguen por el nombre de hive en la tupla `_Ubicacion`.
_SUBCLAVE = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_MAQUINA_WOW64: _Ubicacion = (
    "HKLM",
    r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
)
_MAQUINA: _Ubicacion = ("HKLM", _SUBCLAVE)
_USUARIO: _Ubicacion = ("HKCU", _SUBCLAVE)


def test_detectar_webview2_presente_por_clave_de_maquina(monkeypatch: pytest.MonkeyPatch) -> None:
    _simular_windows(
        monkeypatch,
        {_MAQUINA_WOW64: ("120.0.2210.144", 1), _MAQUINA: None, _USUARIO: None},
    )

    assert detectar_webview2() is EstadoWebView2.PRESENTE


def test_detectar_webview2_presente_solo_por_clave_de_usuario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Instalacion solo-usuario (sin permisos de administrador): las dos
    claves de maquina no existen, pero la de usuario si tiene una version.
    """
    _simular_windows(
        monkeypatch,
        {_MAQUINA_WOW64: None, _MAQUINA: None, _USUARIO: ("121.0.0.0", 1)},
    )

    assert detectar_webview2() is EstadoWebView2.PRESENTE


def test_detectar_webview2_ausente_si_ninguna_clave_tiene_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ninguna de las tres claves existe -- el caso normal cuando el runtime
    nunca se instalo. Las tres lecturas son concluyentes (`FileNotFoundError`
    en cada una), asi que el resultado es `AUSENTE`, no `DESCONOCIDO`.
    """
    _simular_windows(
        monkeypatch,
        {_MAQUINA_WOW64: None, _MAQUINA: None, _USUARIO: None},
    )

    assert detectar_webview2() is EstadoWebView2.AUSENTE


def test_detectar_webview2_ausente_si_la_clave_dice_0_0_0_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`0.0.0.0` es lo que EdgeUpdate deja cuando la clave existe pero el
    producto no esta instalado -- una lectura concluyente, no un fallo.
    """
    _simular_windows(
        monkeypatch,
        {_MAQUINA_WOW64: ("0.0.0.0", 1), _MAQUINA: None, _USUARIO: ("0.0.0.0", 1)},
    )

    assert detectar_webview2() is EstadoWebView2.AUSENTE


def test_detectar_webview2_desconocido_si_una_clave_existe_pero_no_se_puede_leer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regla F5-03 #4: `PermissionError` (clave que SI existe pero no se
    pudo abrir, p. ej. por politica de grupo) es un caso genuinamente no
    concluyente -- distinto de que las tres claves no existan (esa es la
    prueba `..._ausente_si_ninguna_clave_tiene_version` de arriba, que SI da
    `AUSENTE`). Basta con que UNA de las tres sea ilegible para que el
    resultado global sea `DESCONOCIDO`, aunque las otras dos si se pudieran
    leer y dijeran "no instalado".
    """
    _simular_windows(
        monkeypatch,
        {
            _MAQUINA_WOW64: None,
            _MAQUINA: PermissionError("acceso denegado (simulado)"),
            _USUARIO: None,
        },
    )

    assert detectar_webview2() is EstadoWebView2.DESCONOCIDO


def test_detectar_webview2_desconocido_si_el_tipo_de_valor_es_inesperado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`pv` deberia ser siempre `REG_SZ` (una cadena de version), pero si
    algo deja un tipo distinto (`REG_DWORD`, tipo 4) no hay que interpretarlo
    como "instalado" ni como "no instalado": es un dato que no se entiende.
    """
    _simular_windows(
        monkeypatch,
        {_MAQUINA_WOW64: ("120", 4), _MAQUINA: None, _USUARIO: None},
    )

    assert detectar_webview2() is EstadoWebView2.DESCONOCIDO


def test_verificar_webview2_y_avisar_llama_al_aviso_nativo_si_esta_ausente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _simular_windows(
        monkeypatch,
        {_MAQUINA_WOW64: None, _MAQUINA: None, _USUARIO: None},
    )
    llamadas: list[str] = []
    monkeypatch.setattr(
        "dlv_app.webview2._mostrar_aviso_nativo", lambda mensaje: llamadas.append(mensaje)
    )

    assert verificar_webview2_y_avisar() is False
    assert len(llamadas) == 1
    assert NOMBRE_RUNTIME in llamadas[0]


def test_verificar_webview2_y_avisar_no_llama_al_aviso_si_esta_presente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _simular_windows(
        monkeypatch,
        {_MAQUINA_WOW64: ("120.0.0.0", 1), _MAQUINA: None, _USUARIO: None},
    )
    monkeypatch.setattr(
        "dlv_app.webview2._mostrar_aviso_nativo",
        lambda mensaje: pytest.fail("no deberia avisar si el runtime esta presente"),
    )

    assert verificar_webview2_y_avisar() is True


_GUID_QUE_NO_EXISTE = "{00000000-0000-0000-0000-0000DEADBEEF}"


@pytest.mark.skipif(not ES_WINDOWS, reason="lee el registro real de Windows")
def test_deteccion_real_en_windows_es_concluyente() -> None:
    """Sin simular NADA: `winreg` de verdad, registro de verdad.

    No afirma `PRESENTE`, que dependeria de que la maquina tenga WebView2
    instalado (lo tiene la del propietario, no necesariamente un runner de
    CI). Afirma lo que si debe cumplirse en cualquier Windows sano: que la
    lectura llega a una CONCLUSION. `DESCONOCIDO` aqui significaria que
    alguna clave existe pero no se pudo leer, y eso es lo que dejaria a un
    usuario con WebView2 ausente arrancando hacia la ventana en blanco que
    este modulo existe para evitar.

    Medido al escribir esta prueba (Windows 11 Pro 10.0.26100, Python 3.14.6
    x64): `PRESENTE`, con `pv = "151.0.4129.86"` en
    `HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\
    {F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}`.
    """
    assert detectar_webview2() in (EstadoWebView2.PRESENTE, EstadoWebView2.AUSENTE)


@pytest.mark.skipif(not ES_WINDOWS, reason="lee el registro real de Windows")
def test_ausente_contra_el_registro_real_de_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """La rama que de verdad importa, ejercitada sin desinstalar nada.

    Es la unica que devuelve `False` y por tanto la unica que BLOQUEA el
    arranque, y hasta esta prueba nunca se habia ejecutado con WebView2
    realmente ausente -- solo con un `winreg` simulado, que es tambien probar
    la simulacion. Aqui el modulo `winreg`, el registro y el
    `FileNotFoundError` son los de verdad; lo unico sustituido es a que GUID
    se apunta, por uno que no existe en ninguna maquina.

    `_mostrar_aviso_nativo` si se sustituye, y no por comodidad: `MessageBoxW`
    es modal y bloquearia `pytest` hasta el timeout. Que el dialogo real se
    pinta y con que texto se comprobo aparte, fuera de la suite (ver el
    docstring de `dlv_app.webview2._mostrar_aviso_nativo`).
    """
    monkeypatch.setattr(webview2, "_GUIDS_WEBVIEW2", (_GUID_QUE_NO_EXISTE,))
    avisos: list[str] = []
    monkeypatch.setattr(webview2, "_mostrar_aviso_nativo", avisos.append)

    assert detectar_webview2() is EstadoWebView2.AUSENTE
    assert verificar_webview2_y_avisar() is False
    assert len(avisos) == 1
    assert URL_DESCARGA_WEBVIEW2 in avisos[0]


def test_mensaje_runtime_ausente_incluye_nombre_y_url() -> None:
    mensaje = mensaje_runtime_ausente()

    assert NOMBRE_RUNTIME in mensaje
    assert URL_DESCARGA_WEBVIEW2 in mensaje
