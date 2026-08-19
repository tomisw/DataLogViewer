"""Modo portable (F5-02, `docs/02` E10.1, `docs/03-arquitectura.md` SS3.10).

La promesa de SS3.10, literal: «con un `portable.txt` junto al ejecutable, la
app no escribe nada fuera de su carpeta (ni configuracion, ni cache, ni
registro)». Es el requisito de uso en pista desde un pendrive, y es la razon
de que el empaquetado sea `onedir` y no `onefile` (ver el docstring de
`dlv_app.spec`).

Este modulo hace dos cosas, y la segunda es la que da valor a la primera:

1. **Redirige** todo lo que la aplicacion escribe a una subcarpeta propia.
2. **Instrumenta** la comprobacion (`auditar_escrituras`), para que «no
   escribe fuera» sea algo que una prueba MIDE y no algo que un docstring
   AFIRMA. `dlv-app/tests/test_portable.py` ejecuta la cadena real --abrir
   `samples/real/AutoLog_20260729_1830.csv`, piramide, exportacion-- con el
   gancho de auditoria puesto y falla si aparece una sola escritura fuera.

Que se redirige, y por que cada cosa
=====================================
- **Cache `.dlvcache`** (ADR-005), que por omision va a `~/.dlv/cache`: se
  redirige con la variable de entorno `DLV_DIR_CACHE`
  (`dlv_api.main.VARIABLE_DIR_CACHE`).
- **Temporales de Python**, que van a `%TEMP%` o `/tmp`: se redirigen con
  `TMP`/`TEMP`/`TMPDIR` y con `tempfile.tempdir`.
- **Perfil de usuario de WebView2**, que va a un `tmpXXXX` bajo `%TEMP%`
  (ver mas abajo): se redirige con `storage_path=` de `webview.start`.
- **Preferencias, perfiles y eleccion de combustible**: hoy no se persisten
  en ninguna parte. Ver "Lo que hoy no existe".

`DLV_DIR_CACHE` no se inventa aqui: ya existia en `dlv_api.main` y su
docstring dice explicitamente que esta puesta «para que el modo portable de
SS3.10 pueda apuntar la cache dentro del ZIP descomprimido sin tocar codigo».
Esto es ese uso.

El perfil de WebView2, MEDIDO leyendo `pywebview` instalado
============================================================
`webview/platforms/winforms.py::init_storage` decide la `UserDataFolder` que
`edgechromium` pasa a WebView2 (`webview/platforms/edgechromium.py`, linea
`props.UserDataFolder = cache_dir`):

- con `storage_path` puesto -> esa carpeta;
- sin el y sin `private_mode` -> `%APPDATA%\\pywebview`;
- sin el y CON `private_mode` (que es el valor por omision de
  `webview.start`, y por tanto lo que hace la app hoy) ->
  `tempfile.TemporaryDirectory().name`, es decir un `tmpXXXX` bajo `%TEMP%`.

O sea que hoy, sin modo portable, el motor web escribe su perfil en `%TEMP%`,
que esta fuera de la carpeta de la app. Con `storage_path` apuntado aqui, cae
dentro. Ver `RutasPortables.webview`.

Sobre el tema en `localStorage`: con `private_mode=True` --el valor por
omision, que este modulo NO cambia-- WebView2 arranca en modo InPrivate y
`localStorage` no se persiste en disco en ningun modo, portable o no. Es
decir: el tema no se guarda hoy en ninguna parte, ni dentro ni fuera de la
carpeta. Si algun dia se quiere que se guarde (`private_mode=False`), con
este modulo activo caeria dentro de `RutasPortables.webview` y la promesa
seguiria en pie; sin el, caeria en `%APPDATA%\\pywebview`.

Lo que hoy no existe, y por que se menciona igual
==================================================
La tarea pedia buscar activamente donde se persisten preferencias, perfiles y
la eleccion de combustible. **No se persisten en ninguna parte todavia**:
`grep` de `Path.home()`, `expanduser`, `%APPDATA%` y de aperturas en modo
escritura sobre `dlv-core/src`, `dlv-api/src` y `dlv-app/src` da exactamente
dos escrituras a disco en todo el codigo de produccion --
`dlv_api.sesiones` creando el directorio de cache y `dlv_core.cache`
escribiendo el `.dlvcache` y su `.json` de metadatos--, las dos bajo el
directorio de cache. Cuando F4-xx anada preferencias de usuario, el sitio
correcto es `RutasPortables.datos`, y la prueba de auditoria las cazara si se
van a otro lado.

Dos instrumentos, porque ninguno de los dos basta
==================================================
Esto se MIDIO y salio distinto de lo que se esperaba, asi que queda escrito
aqui antes de que alguien vuelva a suponerlo. Una sesion completa sobre
`AutoLog_20260729_1830.csv` deja 20 ficheros en la cache (6,5 MB) y el
gancho de auditoria de Python ve **dos** eventos: el `os.mkdir` del
directorio y el `open` del `.dlvcache.json`. Los 18 Parquet de la piramide
no aparecen: los escribe Polars desde Rust, con las llamadas del sistema
operativo directamente, sin pasar por la maquina virtual de Python. Un
`sys.addaudithook` no puede verlos, y creer que si los ve es la forma mas
facil de tener una medicion que da verde sin mirar nada.

De ahi que haya dos instrumentos, y que se usen juntos:

**`auditar_escrituras`** (gancho de `sys.addaudithook`) ve toda escritura de
Python en CUALQUIER punto del disco, incluidos los sitios que a nadie se le
ocurrio enumerar --escribir la cache al lado del log, dentro de
`samples/real/`, saldria aqui--. No ve lo que escriben Rust o C (Polars) ni
los procesos hijos.

**`instantanea_superficial`** + **`diferencias_de_instantanea`** ven
cualquier entrada nueva, la escriba quien la escriba: Polars, WebView2 o el
propio Windows. Pero solo miran las raices que se les den
(`raices_candidatas`) y solo su primer nivel.

El primero es exhaustivo en cobertura del disco y parcial en cobertura de
codigo; el segundo, al reves. `dlv-app/tests/test_portable.py` los aplica los
dos a la misma sesion, y tiene un control negativo por cada uno --con la
cache apuntando fuera-- para que su verde signifique algo.

Lo que ninguno de los dos garantiza
====================================
WebView2 corre en procesos hijos propios (`msedgewebview2.exe`), que son
codigo ajeno: heredan `TMP`/`TEMP` y reciben la `UserDataFolder` que les
damos, pero lo que hagan por dentro no lo controla este repositorio. La
instantanea los ve **si** escriben en una de las raices candidatas, y no los
ve si escriben en otra parte. Por eso `test_ejecucion_real_no_deja_rastro_
fuera` arranca la aplicacion de verdad, con ventana, y compara instantaneas
alrededor; el resultado de ejecutarla en esta maquina esta en el informe de
la tarea.

Fuera de alcance a proposito: el registro de Windows. SS3.10 lo nombra («ni
registro»), pero las asociaciones de fichero son la tarea F5-17 y no estan
autorizadas aqui; hoy ninguna linea de este repositorio escribe en el
registro (`dlv_app.webview2` solo LEE, para detectar el runtime).
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from collections.abc import Iterator, MutableMapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NOMBRE_MARCA = "portable.txt"
"""Fichero cuya sola presencia junto al ejecutable activa el modo portable.

Su CONTENIDO no se lee: SS3.10 promete «con un `portable.txt` junto al
ejecutable», no «con un portable.txt que diga tal cosa». Un fichero vacio
creado con el explorador de Windows tiene que bastar, porque quien lo va a
crear esta en un box con prisa. Que ademas sirva para dejar escrito ahi por
que se puso es un efecto secundario util, no un formato.
"""

NOMBRE_SUBCARPETA_DATOS = "datos-dlv"
"""Subcarpeta, junto al ejecutable, donde va TODO lo que la app escribe.

No se escribe suelto en la carpeta del ejecutable por dos motivos concretos:
un pendrive con el ZIP descomprimido queda legible (el usuario ve el `.exe` y
una carpeta de datos, no cuarenta ficheros mezclados con `_internal/`), y
«volver a estado de fabrica» es borrar una sola carpeta, sin riesgo de
llevarse por delante un fichero del programa.
"""


class CarpetaPortableNoEscribible(RuntimeError):
    """La carpeta de la app tiene la marca portable pero no admite escritura.

    Es el caso de un ZIP en una unidad de red de solo lectura, un USB con la
    pestana de proteccion puesta o una carpeta bajo `C:\\Program Files` sin
    permisos. **No se cae al comportamiento no portable**: eso escribiria en
    `~/.dlv` y en `%TEMP%` sin decirlo, que es exactamente lo que el
    `portable.txt` pide que no pase. Ver `mensaje_no_escribible`.
    """


@dataclass(slots=True, frozen=True)
class RutasPortables:
    """Las carpetas a las que se ha redirigido todo, ya creadas y comprobadas."""

    carpeta: Path
    """La carpeta de la app: la que contiene el ejecutable y el `portable.txt`."""

    datos: Path
    """`carpeta/datos-dlv`. Raiz de todo lo que la app escribe."""

    cache: Path
    """Donde van los `.dlvcache` (ADR-005). Lo lee `dlv-api` por `DLV_DIR_CACHE`."""

    temporales: Path
    """Lo que Python (y todo proceso hijo) considere `%TEMP%` durante la sesion."""

    webview: Path
    """Perfil de usuario de WebView2 (`storage_path=` de `webview.start`)."""

    def como_tupla(self) -> tuple[Path, ...]:
        """Las carpetas que una auditoria debe considerar «dentro»."""
        return (self.carpeta, self.datos, self.cache, self.temporales, self.webview)


def carpeta_de_la_app() -> Path:
    """Que se considera «su carpeta». Es la decision central de esta tarea.

    - **Paquete congelado** (PyInstaller `onedir`): la carpeta que contiene el
      ejecutable, `Path(sys.executable).parent` -- es decir `dist/dlv-app/`,
      donde estan `dlv-app.exe`, `_internal/` y donde el usuario deja el
      `portable.txt`. **No** `sys._MEIPASS`, que en `onedir` es la subcarpeta
      `_internal/`: usarla obligaria a poner el `portable.txt` dentro de una
      carpeta de tripas del programa, que no es «junto al ejecutable» ni
      nadie lo encontraria.
    - **Arbol de desarrollo**: la raiz del repositorio, `parents[3]` desde
      `dlv-app/src/dlv_app/portable.py` ([0]=dlv_app, [1]=src, [2]=dlv-app,
      [3]=raiz). Aqui `sys.executable` es el interprete del entorno virtual,
      que no tiene nada que ver con la aplicacion. Consecuencia deliberada:
      un `portable.txt` en la raiz del repositorio activa el modo portable
      tambien en desarrollo, que es lo que permite medirlo sin empaquetar.

    MEDIDO CONTRA UN PAQUETE CONGELADO DE VERDAD
    =============================================
    La rama `frozen` de esta funcion es la que decide si el modo portable
    funciona para quien usa el ZIP, y las pruebas de `test_portable.py` solo la
    cubren con `monkeypatch`: fijan `sys.frozen`/`sys.executable` a mano, asi
    que comprueban la aritmetica de la ruta pero no que PyInstaller ponga el
    ejecutable donde aqui se supone. Si esa suposicion fuese falsa, un
    `portable.txt` junto al `.exe` no activaria nada y la aplicacion escribiria
    en `~/.dlv` creyendose portable -- un fallo que no se ve, porque la
    aplicacion funciona igual.

    Se cerro ese hueco ejecutando el binario real (Windows 11, PyInstaller
    6.21, WebView2 151, `dist/dlv-app/dlv-app.exe`, abriendo
    `samples/real/AutoLog_20260729_1830.csv`):

    - CON `portable.txt` junto al `.exe`: aparece `datos-dlv/` al lado con 153
      ficheros, y `~/.dlv/cache` no gana NI UNO.
    - SIN `portable.txt` y con `~/.dlv/cache` vaciada antes: no aparece
      `datos-dlv/`, y la cache del usuario recibe los 19 ficheros esperados.

    El segundo control hubo que repetirlo: la primera vez se hizo sin vaciar la
    cache, y como ya tenia la entrada de ese log de una ejecucion anterior, la
    reutilizo sin escribir nada. Un delta de cero ficheros parecia demostrar lo
    contrario de lo que en realidad demostraba. Vale la pena dejarlo escrito:
    en este proyecto la cache hace que «no se escribio nada» y «no hizo falta
    escribir nada» se parezcan mucho.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def ruta_de_la_marca(carpeta: Path | None = None) -> Path:
    """Donde se busca el `portable.txt`."""
    return (carpeta if carpeta is not None else carpeta_de_la_app()) / NOMBRE_MARCA


def modo_portable_activo(carpeta: Path | None = None) -> bool:
    """`True` si hay un `portable.txt` junto al ejecutable.

    `is_file()` y no `exists()`: un directorio llamado `portable.txt` no
    activa nada, y `is_file()` no lanza si la ruta es inaccesible.
    """
    return ruta_de_la_marca(carpeta).is_file()


def comprobar_escritura(carpeta: Path) -> None:
    """Comprueba que `carpeta` admite escritura ESCRIBIENDO, no preguntando.

    `os.access(carpeta, os.W_OK)` es la via obvia y en Windows es la
    equivocada: la documentacion de la propia stdlib avisa de que en Windows
    solo mira el atributo de solo-lectura y no consulta las ACL, asi que
    devuelve `True` en carpetas donde crear un fichero falla con
    `PermissionError`. Y este es justo el caso en el que un falso `True`
    hace dano: un ZIP portable en una unidad de red compartida en modo
    lectura. Se crea un fichero real, se cierra y se borra.

    Lanza `CarpetaPortableNoEscribible` con el error original encadenado.
    """
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        descriptor, ruta_sonda = tempfile.mkstemp(dir=carpeta, prefix=".dlv-sonda-")
    except OSError as error:
        raise CarpetaPortableNoEscribible(mensaje_no_escribible(carpeta, error)) from error
    os.close(descriptor)
    os.unlink(ruta_sonda)


def mensaje_no_escribible(carpeta: Path, error: OSError) -> str:
    """Texto accionable para el usuario cuando la carpeta portable no admite
    escritura. Funcion aparte para que una prueba pueda comprobarlo sin
    provocar un cuadro de dialogo modal (mismo patron que
    `dlv_app.webview2.mensaje_runtime_ausente`).

    Dice las tres cosas que permiten resolverlo sin adivinar: que se
    intentaba, donde, y cuales son las dos salidas (hacerla escribible, o
    quitar el `portable.txt` y aceptar que se escriba en el perfil del
    usuario).
    """
    return (
        "DataLogViewer esta en modo portable y no puede escribir en su propia "
        f"carpeta.\n\nCarpeta: {carpeta}\nError del sistema: {error}\n\n"
        f"El fichero '{NOMBRE_MARCA}' que hay ahi promete que la aplicacion no "
        "escribira nada fuera de esa carpeta, asi que no se arranca escribiendo "
        "en otro sitio a tus espaldas.\n\n"
        "Dos salidas:\n"
        "  1. Copia la carpeta a un disco donde puedas escribir (o quita la "
        "proteccion de escritura de la unidad).\n"
        f"  2. Borra el fichero '{NOMBRE_MARCA}': la aplicacion volvera a "
        "guardar su cache y sus temporales en tu perfil de usuario."
    )


def activar_modo_portable(
    carpeta: Path | None = None,
    *,
    entorno: MutableMapping[str, str] | None = None,
) -> RutasPortables | None:
    """Si hay `portable.txt`, redirige todo dentro de la carpeta y lo devuelve.

    Devuelve `None` --sin tocar nada-- si no hay marca: el modo no portable
    es el de siempre y esta funcion no debe cambiarlo.

    Lanza `CarpetaPortableNoEscribible` si la marca esta pero la carpeta no
    admite escritura. **Nunca** cae al modo no portable en silencio; el
    porque, en el docstring de esa excepcion.

    Tiene que llamarse ANTES de construir la app de FastAPI: `crear_app` fija
    el directorio de cache en el `RegistroSesiones` en el momento de
    construirse (`dir_cache=... if ... else directorio_cache_por_omision()`),
    asi que una `DLV_DIR_CACHE` puesta despues no la vera nadie.

    Si `DLV_DIR_CACHE` ya venia puesta desde fuera, se PISA. Una variable de
    entorno es una preferencia; el `portable.txt` es una promesa, y la
    promesa gana. `entorno` existe para que las pruebas puedan trabajar sobre
    un diccionario propio.
    """
    carpeta = carpeta if carpeta is not None else carpeta_de_la_app()
    if not modo_portable_activo(carpeta):
        return None

    comprobar_escritura(carpeta)
    datos = carpeta / NOMBRE_SUBCARPETA_DATOS
    rutas = RutasPortables(
        carpeta=carpeta,
        datos=datos,
        cache=datos / "cache",
        temporales=datos / "temp",
        webview=datos / "webview2",
    )
    for destino in (rutas.datos, rutas.cache, rutas.temporales, rutas.webview):
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise CarpetaPortableNoEscribible(mensaje_no_escribible(destino, error)) from error

    # Importacion diferida a proposito: `dlv_app` no deberia arrastrar
    # `dlv_api` --y con el FastAPI, uvicorn y Polars-- solo para leer el
    # nombre de una variable de entorno. Al llamarse desde `main()` el coste
    # es nulo (ya esta importado); en una prueba de este modulo solo, no.
    from dlv_api.main import VARIABLE_DIR_CACHE

    entorno = entorno if entorno is not None else os.environ
    entorno[VARIABLE_DIR_CACHE] = str(rutas.cache)

    # Los tres nombres, no solo el de esta plataforma: `tempfile.gettempdir`
    # mira TMPDIR, TEMP y TMP en ese orden en todas ellas, y los procesos
    # hijos (incluido `msedgewebview2.exe`) heredan el entorno completo. Poner
    # los tres es lo que hace que el motor web tampoco se vaya a `%TEMP%`.
    for nombre in ("TMPDIR", "TEMP", "TMP"):
        entorno[nombre] = str(rutas.temporales)
    if entorno is os.environ:
        # `tempfile` cachea el directorio la primera vez que lo calcula, asi
        # que cambiar el entorno despues de que algo haya usado `tempfile`
        # --y `comprobar_escritura`, aqui arriba, ya lo usa-- no bastaria.
        tempfile.tempdir = str(rutas.temporales)
    return rutas


def avisar_de_carpeta_no_escribible(error: CarpetaPortableNoEscribible) -> None:
    """Ensena el error de `activar_modo_portable` en un cuadro de dialogo nativo.

    Vive aqui y no en `dlv_app.main` para que el arranque solo tenga que
    hacer «intentalo, y si falla avisa y sal», sin conocer ni `ctypes` ni el
    texto. Reutiliza el `MessageBoxW` de `dlv_app.webview2` --ya medido
    contra un dialogo real en Windows 11-- en vez de duplicarlo: es la misma
    situacion (avisar antes de que exista ninguna ventana donde avisar).

    Fuera de Windows escribe en `stderr`. Es lo unico honesto que se puede
    hacer sin arrastrar una dependencia de GUI: en Linux/macOS el paquete se
    lanza tipicamente desde un terminal, y SS3.10 no compromete un dialogo
    nativo por plataforma.
    """
    if sys.platform == "win32":
        from dlv_app.webview2 import _mostrar_aviso_nativo

        _mostrar_aviso_nativo(str(error))
        return
    print(str(error), file=sys.stderr)


# ---------------------------------------------------------------------------
# Instrumentacion: medir las escrituras en vez de razonarlas
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Escritura:
    """Una escritura a disco observada, con el evento que la delato."""

    evento: str
    ruta: Path

    def dentro_de(self, carpetas: Sequence[Path]) -> bool:
        return any(_esta_dentro(self.ruta, carpeta) for carpeta in carpetas)


# Eventos de auditoria de la stdlib que implican MODIFICAR el sistema de
# ficheros, con los indices de sus argumentos que son rutas escritas.
#
# Solo los indices que se escriben: de `shutil.copyfile(origen, destino)` se
# vigila el 1, no el 0, porque leer un fichero de fuera de la carpeta (el log
# del usuario, sin ir mas lejos) es legitimo y marcarlo llenaria la medicion
# de falsos positivos que ocultarian el unico caso que importa.
#
# `os.rename` lleva los dos: renombrar modifica el origen tanto como el
# destino. `open` no esta aqui porque necesita mirar el modo/las banderas
# para distinguir lectura de escritura (ver `_gancho_de_auditoria`).
_EVENTOS_DE_ESCRITURA: dict[str, tuple[int, ...]] = {
    "os.mkdir": (0,),
    "os.rmdir": (0,),
    "os.remove": (0,),  # `os.unlink` emite este mismo evento
    "os.rename": (0, 1),  # `os.replace` emite este mismo evento
    "os.link": (1,),
    "os.symlink": (1,),
    "os.truncate": (0,),
    "os.chmod": (0,),
    "os.chown": (0,),
    "os.utime": (0,),
    "shutil.copyfile": (1,),
    "shutil.copymode": (1,),
    "shutil.copystat": (1,),
    "shutil.move": (1,),
    "shutil.rmtree": (0,),
}

# Banderas de `os.open` que implican intencion de escribir. Se mira esto y no
# solo el modo en texto porque el evento `open` llega con `modo=None` cuando
# la llamada viene de `os.open` (que es por donde pasan `tempfile.mkstemp` y
# buena parte de lo que hace Polars al escribir la cache).
_BANDERAS_DE_ESCRITURA = (
    os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC | getattr(os, "O_EXCL", 0)
)

_registro_activo: list[Escritura] | None = None
_cerrojo_registro = threading.Lock()
_gancho_instalado = False


def _es_apertura_de_escritura(argumentos: tuple[Any, ...]) -> bool:
    """El evento `open` se emite tambien al LEER; esto separa las dos.

    Argumentos del evento: `(ruta, modo, banderas)`. `modo` es la cadena de
    `builtins.open` (`"rb"`, `"w"`, ...) y es `None` cuando la llamada viene
    de `os.open`, en cuyo caso la intencion esta en `banderas`.
    """
    modo = argumentos[1] if len(argumentos) > 1 else None
    banderas = argumentos[2] if len(argumentos) > 2 else 0
    if isinstance(modo, str):
        return any(letra in modo for letra in "wxa+")
    return isinstance(banderas, int) and bool(banderas & _BANDERAS_DE_ESCRITURA)


def _gancho_de_auditoria(evento: str, argumentos: tuple[Any, ...]) -> None:
    """Gancho de `sys.addaudithook`. Inerte salvo dentro de `auditar_escrituras`.

    Corre dentro de cada llamada auditada y en cualquier hilo, asi que hace lo
    minimo posible y sobre todo **no vuelve a auditar**: nada de `open`, nada
    de `Path.resolve()` (que consulta el disco). Normalizar la ruta se deja
    para despues, fuera del camino caliente. Un `sys.addaudithook` no se
    puede desinstalar --es deliberado en CPython, por seguridad--, de ahi que
    el interruptor sea la variable de modulo `_registro_activo`.
    """
    registro = _registro_activo
    if registro is None:
        return
    if evento == "open":
        if not argumentos or not _es_apertura_de_escritura(argumentos):
            return
        indices: tuple[int, ...] = (0,)
    else:
        posibles = _EVENTOS_DE_ESCRITURA.get(evento)
        if posibles is None:
            return
        indices = posibles
    for indice in indices:
        if indice >= len(argumentos):
            continue
        crudo = argumentos[indice]
        if isinstance(crudo, int) or crudo is None:
            continue  # descriptor de fichero, no una ruta
        try:
            texto = os.fspath(crudo)
        except TypeError:
            continue
        if isinstance(texto, bytes):
            texto = texto.decode("utf-8", "replace")
        registro.append(Escritura(evento=evento, ruta=Path(texto)))


@contextmanager
def auditar_escrituras() -> Iterator[list[Escritura]]:
    """Registra toda escritura a disco de ESTE proceso mientras dure el bloque.

    La lista que se cede se va llenando durante el bloque y queda completa al
    salir. Un solo auditor a la vez en el proceso (el cerrojo lo impone): dos
    anidados repartirian los eventos entre ellos y las dos mediciones
    saldrian incompletas, que es peor que no medir.

    Alcance, MEDIDO y no supuesto (ver la tabla del docstring del modulo):
    `sys.addaudithook` ve las llamadas de la maquina virtual de Python de
    este proceso, y solo esas. **Polars no pasa por aqui**: escribe los
    Parquet de la piramide desde Rust y el gancho no los registra. Tampoco ve
    a los procesos hijos (`msedgewebview2.exe`). Lo que si ve --y es su
    valor-- es cualquier escritura de Python en cualquier punto del disco,
    incluidos los que nadie penso en enumerar. Para el resto,
    `instantanea_superficial`.
    """
    global _registro_activo, _gancho_instalado
    with _cerrojo_registro:
        if not _gancho_instalado:
            sys.addaudithook(_gancho_de_auditoria)
            _gancho_instalado = True
        if _registro_activo is not None:
            raise RuntimeError("ya hay una auditoria de escrituras en curso en este proceso")
        registro: list[Escritura] = []
        _registro_activo = registro
    try:
        yield registro
    finally:
        with _cerrojo_registro:
            _registro_activo = None


def _esta_dentro(ruta: Path, carpeta: Path) -> bool:
    """`True` si `ruta` cae dentro de `carpeta`, comparando de forma robusta.

    `os.path.realpath` resuelve enlaces y --en Windows-- la forma corta 8.3
    (`C:\\Users\\TOMAS~1\\...` es el mismo sitio que `C:\\Users\\tomas\\...`,
    y `%TEMP%` se expone a veces asi), y `os.path.normcase` hace la
    comparacion insensible a mayusculas ahi donde el sistema de ficheros lo
    es. Sin las dos, la medicion daria falsos positivos que nadie sabria
    interpretar.
    """
    absoluta = os.path.normcase(os.path.realpath(ruta))
    base = os.path.normcase(os.path.realpath(carpeta))
    return absoluta == base or absoluta.startswith(base + os.sep)


def escrituras_fuera_de(
    escrituras: Sequence[Escritura], carpetas: Sequence[Path]
) -> list[Escritura]:
    """Las escrituras que NO cayeron dentro de ninguna de `carpetas`.

    Es la funcion que convierte la promesa de SS3.10 en un `assert`: si
    devuelve algo, el modo portable esta roto y la lista dice exactamente
    donde y por que evento.
    """
    return [escritura for escritura in escrituras if not escritura.dentro_de(carpetas)]


# ---------------------------------------------------------------------------
# Medicion por instantanea: lo unico que ve a los procesos hijos
# ---------------------------------------------------------------------------


def raices_candidatas(entorno: MutableMapping[str, str] | None = None) -> tuple[Path, ...]:
    """Los sitios de fuera de la carpeta donde esta aplicacion podria escribir.

    No es una lista generica de «sitios donde escribe software»: es la lista
    de los que este repositorio o sus dependencias nombran de verdad.

    - `~/.dlv` y `~/.dlv/cache` -- `dlv_api.main.directorio_cache_por_
      omision`. Las DOS, y no solo la primera: la instantanea es de primer
      nivel (ver `instantanea_superficial`), asi que con `~/.dlv` sola un
      `.dlvcache` nuevo dentro de `cache/` no apareceria como entrada nueva
      --`cache` ya estaba-- y la medicion daria verde sin motivo. Es el falso
      negativo mas facil de tener aqui.
    - `%APPDATA%\\pywebview` -- `webview/platforms/winforms.py::init_storage`
      sin `private_mode`. Cubierto por `%APPDATA%`, que es la raiz.
    - `%TEMP%` -- el `tempfile.TemporaryDirectory()` que esa misma funcion usa
      CON `private_mode`, y cualquier temporal de Python. MEDIDO: sin modo
      portable aparece ahi un `tmpXXXX` en cada arranque.
    - `%LOCALAPPDATA%` -- donde WebView2 deja sus carpetas `*.WebView2` /
      `EBWebView` cuando nadie le fija una `UserDataFolder`.
    - el perfil del usuario -- red de seguridad para lo que no se previo.
    """
    entorno = entorno if entorno is not None else os.environ
    candidatas = [Path.home() / ".dlv" / "cache", Path.home() / ".dlv", Path.home()]
    for nombre in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        valor = entorno.get(nombre)
        if valor:
            candidatas.append(Path(valor))
    vistas: dict[str, Path] = {}
    for candidata in candidatas:
        vistas.setdefault(os.path.normcase(str(candidata)), candidata)
    return tuple(vistas.values())


def instantanea_superficial(raiz: Path) -> frozenset[str]:
    """Nombres de las entradas de primer nivel de `raiz` (vacio si no existe).

    De primer nivel a proposito: `%LOCALAPPDATA%` y `%TEMP%` tienen decenas de
    miles de ficheros en una maquina usada, y recorrerlos enteros convertiria
    la medicion en algo que nadie ejecuta. Todo lo que esta tarea tiene que
    detectar --`~/.dlv`, `pywebview`, `tmpXXXX`, `dlv-app.WebView2`-- aparece
    como una entrada NUEVA de primer nivel, asi que este nivel de detalle es
    suficiente para lo que hay que ver y barato para ejecutarlo de verdad.
    """
    try:
        return frozenset(entrada.name for entrada in raiz.iterdir())
    except OSError:
        return frozenset()


def diferencias_de_instantanea(
    antes: dict[Path, frozenset[str]], despues: dict[Path, frozenset[str]]
) -> dict[Path, frozenset[str]]:
    """Entradas nuevas por raiz, descartando las raices sin novedades."""
    nuevas = {raiz: despues.get(raiz, frozenset()) - entradas for raiz, entradas in antes.items()}
    return {raiz: entradas for raiz, entradas in nuevas.items() if entradas}
