"""Asociacion opcional y reversible de extensiones con DataLogViewer (F5-17).

Cubre E10.4 de `docs/02-alcance-y-plan.md`: "Asociacion de extension
`.csv`/`.dlv` opcional y reversible". Depende de F5-01 (empaquetado): solo
tiene sentido asociar una extension con un ejecutable que ya existe como tal.

Las dos palabras del titulo son las que mandan, y son las dos que decide este
modulo:

**Opcional.** Ninguna funcion de aqui se llama desde `dlv_app.main` ni desde
ningun sitio del arranque. Igual que `dlv_app.actualizador` (F5-05, mismo
espiritu): una aplicacion portable que se apropia de una extension solo por
abrirse es lo contrario de portable. Asociar o desasociar es una accion que
alguien pide explicitamente -- hoy, quien importe este modulo a mano o desde
una consola; el dia que exista un panel de preferencias en `dlv-ui`, ese panel
llamara a `registrar_extension`/`desregistrar_extension` con un boton, nunca
al arrancar.

**Reversible.** Es la decision central de la tarea y merece razonarse por
escrito, no solo implementarse:

Al registrar, si la extension YA tenia una asociacion (otro ProgID, p. ej.
Excel para `.csv`), este modulo la GUARDA antes de sobreescribirla y la
RESTAURA al desregistrar -- no se niega a tocar una extension con dueno. Se
eligio guardar-y-restaurar en vez de negarse por dos motivos:

1. Negarse dejaria la funcion inutil para el caso que E10.4 nombra en primer
   lugar: `.csv` casi siempre tiene ya un dueno (Excel, LibreOffice, otro
   visor), y ese es precisamente el caso de uso que un boton "asociar .csv
   con DataLogViewer" existe para resolver. Si la funcion se niega en cuanto
   hay un dueno previo, solo sirve para `.dlv`, que hoy no lo usa nadie mas
   -- la mitad de E10.4 quedaria sin implementar en la practica, aunque el
   codigo "funcione".
2. Guardar-y-restaurar es exactamente lo que hacen los instaladores de
   escritorio de toda la vida al asociarse con un tipo de fichero y
   desinstalarse despues, asi que no es una tecnica nueva ni arriesgada: el
   respaldo se escribe ANTES de sobreescribir nada (`registrar_extension`),
   bajo una clave propia (`_ruta_respaldo`) que sobrevive a que la aplicacion
   se cierre y vuelva a abrirse en otra sesion, y `desregistrar_extension` no
   hace nada mas que leer ese respaldo y volver a escribir lo que habia.

Limite conocido, y se deja escrito en vez de fingir que no existe: si algo
DISTINTO de este modulo cambia la asociacion despues de `registrar_extension`
(el usuario reasocia `.csv` a mano desde el Explorador de Windows), un
`desregistrar_extension` posterior pisa ese cambio manual con el respaldo
antiguo, porque el respaldo no se actualiza mas que la primera vez (ver el
docstring de `registrar_extension`). Es el mismo limite que tiene cualquier
instalador que guarda un unico valor "de antes de mi": no hay forma de saber,
solo mirando el registro, si un cambio posterior fue "el usuario decidio otra
cosa" o "otro programa se registro tambien". Resolverlo exigiria un historial
completo de cambios, que es mas maquinaria de la que 3 puntos justifican.

Que NO hace este modulo, a proposito
======================================
- No toca `HKEY_LOCAL_MACHINE`. Solo `HKEY_CURRENT_USER`, sin privilegios de
  administrador -- es una limitacion real (no afecta a otras cuentas de la
  misma maquina) y una decision deliberada: `HKLM` exige elevacion y una
  desinstalacion torpe ahi afecta a todo el mundo, no solo a quien instalo la
  app.
- No toca `...\\Explorer\\FileExts\\<ext>\\UserChoice`. Es el mecanismo con el
  que Windows 8+ protege la eleccion explicita del usuario hecha desde el
  cuadro "Abrir con..." (un hash que solo el propio Explorer sabe calcular
  correctamente); escribir ahi sin la formula correcta de Microsoft -- que
  cambia entre versiones de Windows y no esta documentada oficialmente -- es
  la tecnica que usa el malware de secuestro de asociaciones, y por eso
  Microsoft la endurece activamente. Consecuencia MEDIDA y no supuesta de
  omitirlo: si el usuario ya eligio explicitamente otra app para `.csv` desde
  el Explorador, este modulo puede hacer que DataLogViewer aparezca en "Abrir
  con" y quede registrado como el ProgID por omision bajo la clave de clases
  de HKCU, pero mientras exista esa eleccion protegida, Windows seguira
  abriendo con el la primera vez que se haga doble clic -- el cambio
  se nota inmediatamente solo cuando NO habia un `UserChoice` previo (el caso
  normal: extension nunca usada, o `.dlv` porque no la usa nada mas todavia).
- No llama a `SHChangeNotify` para refrescar el Explorador al instante.
  Se considero (es una llamada estandar de Microsoft, sin efectos de
  escritura) pero anadirla sin poder medir su efecto en esta sesion --
  refrescar el icono de un tipo de fichero no es algo que una prueba
  automatica pueda comprobar sin capturar la pantalla del Explorador -- iba
  contra el mismo principio que documenta `dlv_app.webview2`: no afirmar lo
  que no se ha medido. Sin ella, el cambio se ve igual, solo que puede hacer
  falta cerrar y volver a abrir el Explorador (o iniciar sesion de nuevo) para
  verlo en el icono; el comportamiento real de apertura (que app abre el
  fichero) no depende de esto.
- No decide QUE extensiones ofrecer. `registrar_extension`/
  `desregistrar_extension` funcionan con cualquier cadena que empiece por
  `.`; que un futuro panel de preferencias solo ofrezca `.csv` y `.dlv` (las
  dos que nombra E10.4) es una decision de esa interfaz, no de este modulo.

Modo portable (F5-02): se niega, en las dos direcciones
==========================================================
`dlv_app.portable` ya lo dice en su propio docstring: "el registro de
Windows... las asociaciones de fichero son la tarea F5-17 y no estan
autorizadas aqui". La promesa de SS3.10 es literal -- "la app no escribe nada
fuera de su carpeta (ni configuracion, ni cache, ni registro)" -- y el
registro esta fuera de cualquier carpeta por definicion, asi que
`registrar_extension` y `desregistrar_extension` se niegan igual con
`portable.txt` presente (`_comprobar_no_portable`, ver su docstring para por
que tambien se bloquea desregistrar, que a primera vista parece inofensivo).

Como se prueba (costura inyectable, mismo patron que `dlv_app.webview2`)
============================================================================
`winreg` solo existe en la distribucion Windows de Python; un `import winreg`
a nivel de modulo romperia `import dlv_app.asociaciones` -- y con el, pytest
-- en Linux/macOS. Se importa de forma perezosa dentro de `_almacen_real`.

La logica de decision (que ProgID escribir, cuando hay que respaldar, que
restaurar) esta separada de la lectura/escritura real del registro detras del
protocolo `AlmacenDeRegistro`: `registrar_extension`/`desregistrar_extension`
reciben una implementacion por el parametro `almacen`, y las pruebas pueden
pasar una implementacion en memoria (`tests/test_asociaciones.py`) para
comprobar toda la logica sin tocar el registro ni depender de Windows. Solo
un punado de pruebas, marcadas `skipif` fuera de Windows, ejercitan
`_AlmacenWinreg` contra el HKCU de verdad -- con una extension de usar y
tirar, nunca `.csv` ni `.dlv`.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

# Prefijo de todos los ProgID que registra este modulo. `progid_de(".csv")`
# da "DataLogViewer.csv" -- sigue la convencion habitual `Vendor.Tipo` de
# ProgID de Windows (la extension ya trae el punto separador).
_PREFIJO_PROGID = "DataLogViewer"

# Marcador que se guarda en la clave de respaldo cuando la extension NO tenia
# ninguna asociacion previa (para distinguirlo de "todavia no hay respaldo
# guardado", que es `None`, ver `AlmacenDeRegistro.leer_valor_por_omision`).
# Un ProgID real de COM no puede contener ':' (regla del propio formato
# ProgID), asi que esta cadena nunca puede colisionar con un valor legitimo
# que ya hubiera en el registro.
_MARCADOR_SIN_ASOCIACION_PREVIA = "DataLogViewer:sin-asociacion-previa"


class PlataformaNoSoportada(RuntimeError):
    """La asociacion de extensiones solo esta implementada para Windows
    (`HKEY_CURRENT_USER`). En Linux/macOS no hay equivalente directo -- cada
    escritorio tiene su propio mecanismo (`.desktop` + `xdg-mime`, Launch
    Services) y anadirlos esta fuera del alcance de 3 puntos de esta tarea.
    """


class ModoPortableActivo(RuntimeError):
    """Se pidio registrar o desregistrar con `portable.txt` presente.

    Ver la seccion "Modo portable" del docstring del modulo para el porque
    se bloquea tambien desregistrar.
    """


class NoHayAsociacionQueDesregistrar(RuntimeError):
    """`desregistrar_extension` para una extension sin respaldo guardado --
    o nunca se llamo a `registrar_extension` para ella, o ya se desregistro
    antes. No hay nada seguro que restaurar: intentarlo igualmente
    escribiria una asociacion inventada, que es peor que no hacer nada.
    """


def progid_de(extension: str) -> str:
    """El ProgID que este modulo usa para `extension` (p. ej. ".dlv" ->
    "DataLogViewer.dlv"). Funcion pura, sin tocar el registro -- expuesta
    para que quien llame pueda mostrar el nombre sin necesidad de invocar
    ninguna funcion que si lo toque.
    """
    return f"{_PREFIJO_PROGID}{_normalizar_extension(extension)}"


def _normalizar_extension(extension: str) -> str:
    if not extension.startswith("."):
        raise ValueError(f"la extension debe empezar por un punto: {extension!r}")
    if len(extension) < 2:
        raise ValueError(f"extension vacia: {extension!r}")
    return extension


def _ruta_clases(sufijo: str) -> str:
    return rf"Software\Classes\{sufijo}"


def _ruta_extension(extension: str) -> str:
    return _ruta_clases(_normalizar_extension(extension))


def _ruta_progid(progid: str) -> str:
    return _ruta_clases(progid)


def _ruta_comando(progid: str) -> str:
    return _ruta_progid(progid) + r"\shell\open\command"


def _ruta_respaldo(extension: str) -> str:
    # Bajo una clave propia de la aplicacion, NO bajo `Software\Classes`: el
    # respaldo no es una asociacion, es un dato nuestro, y mezclarlo con
    # `Classes` lo haria aparecer -- por error -- como un ProgID mas.
    return rf"Software\DataLogViewer\AsociacionesRespaldo\{_normalizar_extension(extension)}"


# Los dos contenedores propios que `registrar_extension` crea de forma
# implicita (via `CreateKeyEx` de `_ruta_respaldo`) y que NADIE mas que este
# modulo tiene motivo para crear: si al desregistrar la ultima extension
# quedan vacios, hay que borrarlos tambien -- si no, "reversible" seria
# aproximado: el registro quedaria con una clave `Software\DataLogViewer`
# vacia que no existia antes de la primera llamada a `registrar_extension`.
# MEDIDO en esta sesion contra el HKCU real: sin esta limpieza, un ciclo
# completo registrar/desregistrar deja exactamente este contenedor huerfano.
_RUTA_CONTENEDOR_RESPALDOS = r"Software\DataLogViewer\AsociacionesRespaldo"
_RUTA_CONTENEDOR_APLICACION = r"Software\DataLogViewer"


def _comando_de_apertura(ejecutable: Path) -> str:
    """La linea de `shell\\open\\command`: el ejecutable, entre comillas por si
    la ruta tiene espacios (`Archivos de programa`, o cualquier ruta de
    usuario), seguido de `"%1"` -- el marcador que Windows sustituye por la
    ruta del fichero con el que se hizo doble clic, tambien entre comillas
    por el mismo motivo.
    """
    return f'"{ejecutable}" "%1"'


class AlmacenDeRegistro(Protocol):
    """Costura inyectable: todo el acceso real a `HKEY_CURRENT_USER` pasa por
    aqui. `registrar_extension`/`desregistrar_extension` no conocen `winreg`
    directamente -- solo este protocolo -- asi que su logica de decision (que
    hay que escribir, en que orden, cuando hay que respaldar o restaurar) se
    puede probar entera con una implementacion en memoria, sin tocar el
    registro ni depender de estar en Windows.
    """

    def leer_valor_por_omision(self, ruta: str) -> str | None:
        """El valor `(Predeterminado)` de `ruta` bajo HKCU.

        `None` si la clave no existe O si existe pero no tiene valor por
        omision (tratadas igual a proposito: para decidir que respaldar o
        restaurar, las dos significan "aqui no habia nada que guardar").
        """
        ...

    def escribir_valor_por_omision(self, ruta: str, valor: str) -> None:
        """Crea `ruta` (y las claves intermedias que hagan falta) si no
        existe, y fija su valor `(Predeterminado)` a `valor`."""
        ...

    def borrar_arbol(self, ruta: str) -> None:
        """Borra `ruta` y todo lo que cuelgue de ella. No falla si `ruta` ya
        no existe -- desregistrar debe poder repetirse sin excepciones
        sorpresa si algo a medio camino ya se habia borrado."""
        ...

    def borrar_si_vacia(self, ruta: str) -> None:
        """Borra `ruta` SOLO si existe y no tiene ninguna subclave.

        Para limpiar contenedores propios (`_RUTA_CONTENEDOR_RESPALDOS`,
        `_RUTA_CONTENEDOR_APLICACION`) sin arriesgarse a borrar algo que
        otra extension todavia este usando como respaldo, o que otro
        programa (improbable, pero no imposible) haya colgado de la misma
        clave. No falla si `ruta` no existe."""
        ...


@dataclass(slots=True)
class _AlmacenWinreg:
    """Implementacion real de `AlmacenDeRegistro`, sobre `HKEY_CURRENT_USER`.

    Recibe el modulo `winreg` ya importado (por `_almacen_real`, que lo
    importa de forma perezosa) en vez de importarlo aqui: mantiene esta clase
    definible -- aunque nunca instanciable con provecho -- en cualquier
    plataforma, y es el mismo motivo por el que `dlv_app.webview2.
    _ubicaciones` recibe `winreg` como argumento.
    """

    _winreg: Any

    def leer_valor_por_omision(self, ruta: str) -> str | None:
        try:
            with self._winreg.OpenKey(self._winreg.HKEY_CURRENT_USER, ruta) as clave:
                valor, tipo = self._winreg.QueryValueEx(clave, "")
        except FileNotFoundError:
            return None
        if tipo != self._winreg.REG_SZ or not isinstance(valor, str):
            # Tipo inesperado (p. ej. REG_DWORD): no es un valor que este
            # modulo haya podido escribir nunca, asi que se trata igual que
            # "no hay nada util que leer aqui" en vez de fallar.
            return None
        return valor

    def escribir_valor_por_omision(self, ruta: str, valor: str) -> None:
        with self._winreg.CreateKeyEx(self._winreg.HKEY_CURRENT_USER, ruta) as clave:
            self._winreg.SetValueEx(clave, "", 0, self._winreg.REG_SZ, valor)

    def borrar_arbol(self, ruta: str) -> None:
        self._borrar_recursivo(ruta)

    def borrar_si_vacia(self, ruta: str) -> None:
        subclaves = self._subclaves_de(ruta)
        if subclaves is None or subclaves:
            # `None`: la clave no existe, nada que borrar. No vacia: hay
            # algo mas colgando de ella (otro respaldo pendiente, u otro
            # programa), y borrar ahi se llevaria eso por delante.
            return
        self._winreg.DeleteKey(self._winreg.HKEY_CURRENT_USER, ruta)

    def _subclaves_de(self, ruta: str) -> list[str] | None:
        """Nombres de las subclaves directas de `ruta`, o `None` si `ruta`
        no existe. Compartido por `_borrar_recursivo` y `borrar_si_vacia`."""
        try:
            with self._winreg.OpenKey(self._winreg.HKEY_CURRENT_USER, ruta) as clave:
                subclaves: list[str] = []
                indice = 0
                while True:
                    try:
                        subclaves.append(self._winreg.EnumKey(clave, indice))
                    except OSError:
                        break
                    indice += 1
                return subclaves
        except FileNotFoundError:
            return None

    def _borrar_recursivo(self, ruta: str) -> None:
        """Recorre y borra en profundidad primero: `winreg.DeleteKey` solo
        borra una clave SIN subclaves, y una asociacion completa tiene
        subclaves (`<progid>\\shell\\open\\command`). El numero de subclaves
        por nivel aqui es siempre pequeno (1-2, las que este modulo mismo
        crea) -- no es el tipo de recorrido que ADR-009 prohibe, que es sobre
        muestras de un log, no sobre claves de registro.
        """
        subclaves = self._subclaves_de(ruta)
        if subclaves is None:
            return
        for subclave in subclaves:
            self._borrar_recursivo(f"{ruta}\\{subclave}")
        self._winreg.DeleteKey(self._winreg.HKEY_CURRENT_USER, ruta)


def _almacen_real() -> AlmacenDeRegistro:
    """Construye el almacen que habla con el HKCU de verdad.

    Importa `winreg` de forma perezosa, dentro de la funcion -- el mismo
    motivo que `dlv_app.webview2._version_desde_registro`: `winreg` solo
    existe en la distribucion Windows de Python, y un `import winreg` a nivel
    de modulo romperia `import dlv_app.asociaciones` (y con el, pytest) en
    Linux/macOS. Los llamantes (`_requerir_almacen_real`) ya comprueban
    `sys.platform == "win32"` antes de invocar esta funcion.
    """
    import winreg

    return _AlmacenWinreg(winreg)


def _requerir_almacen_real() -> AlmacenDeRegistro:
    if sys.platform != "win32":
        raise PlataformaNoSoportada(
            "la asociacion de extensiones solo esta implementada en Windows "
            f"(HKEY_CURRENT_USER); esta plataforma es {sys.platform!r}."
        )
    return _almacen_real()


def _comprobar_no_portable() -> None:
    """Se niega si el modo portable esta activo, en las DOS direcciones
    (registrar Y desregistrar).

    docs/03-arquitectura.md SS3.10, literal: con `portable.txt` junto al
    ejecutable "la app no escribe nada fuera de su carpeta (ni
    configuracion, ni cache, ni registro)". `dlv_app.portable` ya lo dice en
    su propio docstring: "las asociaciones de fichero son la tarea F5-17 y no
    estan autorizadas aqui". Esta funcion es la parte con codigo detras de
    esa frase -- sin ella la promesa de SS3.10 seria un docstring sin nada
    que la haga cumplirse.

    Se bloquea TAMBIEN `desregistrar_extension`, aunque desregistrar solo
    deshace lo que este modulo escribio y a primera vista parece inofensivo
    incluso en modo portable. Se descarta esa excepcion a proposito: abrir un
    hueco "se permite escribir en el registro, pero solo para deshacer lo que
    hice yo" convierte "modo portable = cero escritura" en una promesa mas
    debil y mas dificil de razonar -- la primera vez que alguien necesite
    "deshacer lo que hizo OTRA cosa" el limite ya no estara claro. Quien
    necesite deshacer una asociacion desde una copia portable tiene dos
    salidas sin tocar este modulo: quitar temporalmente `portable.txt`, o
    editar el registro a mano.
    """
    from dlv_app.portable import modo_portable_activo

    if not modo_portable_activo():
        return
    raise ModoPortableActivo(
        "DataLogViewer esta en modo portable (hay un 'portable.txt' junto al "
        "ejecutable) y este modulo no toca el registro de Windows en ese "
        "modo: la promesa del modo portable es no escribir nada fuera de su "
        "carpeta, y el registro esta fuera de cualquier carpeta. Quita "
        "'portable.txt' si quieres asociar una extension, o edita el "
        "registro a mano si necesitas deshacer una asociacion hecha por una "
        "copia no portable."
    )


def _notificar_shell() -> None:
    """Avisa al Explorador de que las asociaciones cambiaron, con la llamada
    que documenta Microsoft para esto (`SHChangeNotify`, sin efectos de
    escritura -- solo difunde un mensaje).

    Esfuerzo best-effort a proposito: la asociacion en si ya quedo escrita
    correctamente antes de llegar aqui, y fallar por un detalle cosmetico
    (el icono no se refresca al instante) seria peor que ignorarlo. Nunca se
    llama fuera de Windows (unica invocacion, al final de `registrar_
    extension`/`desregistrar_extension`, detras de la comprobacion de
    plataforma de `_requerir_almacen_real`).
    """
    SHCNE_ASSOCCHANGED = 0x08000000
    SHCNF_IDLIST = 0x0000
    with contextlib.suppress(OSError):
        ctypes.windll.shell32.SHChangeNotify(  # type: ignore[attr-defined, unused-ignore]
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None
        )


@dataclass(frozen=True, slots=True)
class ResultadoRegistro:
    """Lo que hizo `registrar_extension`, para que quien llama (y las
    pruebas) lo puedan comprobar sin releer el registro."""

    extension: str
    progid: str
    ya_estaba_asociada: bool
    """`True` si `extension` ya apuntaba a este `progid` antes de la llamada
    -- la llamada fue, en la practica, una actualizacion del ejecutable
    registrado (p. ej. la app se movio de carpeta) y no una asociacion
    nueva."""


def registrar_extension(
    extension: str,
    ejecutable: Path,
    *,
    descripcion: str | None = None,
    almacen: AlmacenDeRegistro | None = None,
) -> ResultadoRegistro:
    """Asocia `extension` (p. ej. ".csv") con `ejecutable` para el usuario
    actual (`HKEY_CURRENT_USER`, sin privilegios de administrador).

    Si `extension` ya tenia una asociacion distinta, se GUARDA antes de
    sobreescribirla (ver la seccion "Reversible" del docstring del modulo) --
    pero solo la PRIMERA vez: si ya hay un respaldo guardado para esta
    extension (de una llamada anterior a `registrar_extension` sin su
    `desregistrar_extension` correspondiente), no se vuelve a leer ni
    sobreescribir ese respaldo. Sin esta regla, llamar dos veces seguidas
    perderia el valor original: la segunda llamada leeria como "valor previo"
    el ProgID que la primera llamada acaba de escribir.

    Lanza `PlataformaNoSoportada` fuera de Windows (si `almacen` es `None`;
    con un `almacen` inyectado la funcion no mira la plataforma, para que las
    pruebas puedan ejercitar la logica en cualquier sistema operativo) y
    `ModoPortableActivo` si hay un `portable.txt` junto al ejecutable
    (`_comprobar_no_portable`).
    """
    extension = _normalizar_extension(extension)
    _comprobar_no_portable()
    almacen_efectivo = almacen if almacen is not None else _requerir_almacen_real()

    progid = progid_de(extension)
    texto_descripcion = (
        descripcion if descripcion is not None else f"Registro DataLogViewer ({extension})"
    )

    ruta_ext = _ruta_extension(extension)
    ruta_resp = _ruta_respaldo(extension)

    valor_actual = almacen_efectivo.leer_valor_por_omision(ruta_ext)
    ya_estaba_asociada = valor_actual == progid

    if almacen_efectivo.leer_valor_por_omision(ruta_resp) is None:
        almacen_efectivo.escribir_valor_por_omision(
            ruta_resp,
            valor_actual if valor_actual is not None else _MARCADOR_SIN_ASOCIACION_PREVIA,
        )

    almacen_efectivo.escribir_valor_por_omision(_ruta_progid(progid), texto_descripcion)
    almacen_efectivo.escribir_valor_por_omision(
        _ruta_comando(progid), _comando_de_apertura(ejecutable)
    )
    almacen_efectivo.escribir_valor_por_omision(ruta_ext, progid)

    if almacen is None and sys.platform == "win32":
        _notificar_shell()

    return ResultadoRegistro(
        extension=extension, progid=progid, ya_estaba_asociada=ya_estaba_asociada
    )


def desregistrar_extension(
    extension: str,
    *,
    almacen: AlmacenDeRegistro | None = None,
) -> None:
    """Deshace `registrar_extension` para `extension`: restaura lo que habia
    antes (o borra la clave entera si no habia nada) y limpia el ProgID y el
    respaldo propios.

    Lanza `NoHayAsociacionQueDesregistrar` si no hay ningun respaldo
    guardado para `extension` -- nunca se llamo a `registrar_extension` para
    ella, o ya se desregistro. Se rechaza a proposito en vez de no hacer
    nada en silencio: un desregistro que no puede confirmar que hay algo que
    deshacer no deberia fingir que lo hizo.

    Mismas reglas de plataforma y modo portable que `registrar_extension`.
    """
    extension = _normalizar_extension(extension)
    _comprobar_no_portable()
    almacen_efectivo = almacen if almacen is not None else _requerir_almacen_real()

    ruta_resp = _ruta_respaldo(extension)
    valor_previo = almacen_efectivo.leer_valor_por_omision(ruta_resp)
    if valor_previo is None:
        raise NoHayAsociacionQueDesregistrar(
            f"no hay ningun respaldo guardado para {extension!r}: no se llamo "
            "antes a registrar_extension() para esta extension, o ya se "
            "desregistro."
        )

    ruta_ext = _ruta_extension(extension)
    if valor_previo == _MARCADOR_SIN_ASOCIACION_PREVIA:
        # No habia ninguna asociacion antes de que este modulo escribiera:
        # se borra la clave entera, no solo el valor, para dejar el registro
        # exactamente como estaba (una `.ext` que no existia).
        almacen_efectivo.borrar_arbol(ruta_ext)
    else:
        almacen_efectivo.escribir_valor_por_omision(ruta_ext, valor_previo)

    almacen_efectivo.borrar_arbol(_ruta_progid(progid_de(extension)))
    almacen_efectivo.borrar_arbol(ruta_resp)

    # Limpieza de los contenedores propios que `registrar_extension` crea de
    # forma implicita (ver `_RUTA_CONTENEDOR_RESPALDOS`): si esta era la
    # ultima extension con respaldo pendiente, no dejar una clave vacia que
    # no existia antes de la primera asociacion. El orden importa -- primero
    # el hijo, luego el padre -- y `borrar_si_vacia` no toca nada si otra
    # extension todavia tiene su respaldo ahi.
    almacen_efectivo.borrar_si_vacia(_RUTA_CONTENEDOR_RESPALDOS)
    almacen_efectivo.borrar_si_vacia(_RUTA_CONTENEDOR_APLICACION)

    if almacen is None and sys.platform == "win32":
        _notificar_shell()


def esta_asociada_a_datalogviewer(
    extension: str,
    *,
    almacen: AlmacenDeRegistro | None = None,
) -> bool:
    """`True` si `extension` esta HOY asociada al ProgID de DataLogViewer.

    Consulta sin efectos secundarios -- util para que un futuro panel de
    preferencias muestre el estado actual de un interruptor antes de que el
    usuario lo toque. Mismas reglas de plataforma que `registrar_extension`
    (pero NO las de modo portable: leer el registro no escribe nada, asi que
    no hay promesa de SS3.10 que romper).
    """
    extension = _normalizar_extension(extension)
    almacen_efectivo = almacen if almacen is not None else _requerir_almacen_real()
    valor_actual = almacen_efectivo.leer_valor_por_omision(_ruta_extension(extension))
    return valor_actual == progid_de(extension)
