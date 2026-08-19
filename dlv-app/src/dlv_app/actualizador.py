"""Comprobador de actualizaciones, opcional y desactivable (F5-05).

Depende de F5-01 (empaquetado): solo tiene sentido preguntar "hay una version
mas nueva" para algo que ya se distribuye como paquete versionado. Cubre la
segunda mitad de E10.3 (`docs/02-alcance-y-plan.md`): "Firma de binarios y
actualizador opcional (desactivable, nunca obligatorio)". La firma de
binarios es un paso de la cadena de empaquetado (firmar el .exe/.app antes de
publicarlo) y no algo que se compruebe en tiempo de ejecucion; este fichero
cubre solo la segunda mitad, el actualizador.

Que hace este modulo, y que NO hace
======================================
Comprueba, contra una URL configurable, si hay una version mas reciente que
la instalada, y devuelve un resultado que quien llama puede mostrar (o
ignorar) en la interfaz. Eso es TODO lo que hace. Explicitamente NO:

- Descarga ningun binario.
- Reemplaza el ejecutable en marcha, ni reinicia la aplicacion.
- Verifica ninguna firma (esa es la otra mitad de E10.3, fuera de aqui).
- Abre ningun navegador por su cuenta: `ResultadoActualizacion.url_descarga`
  es un dato para que quien llama decida si lo abre, no una accion que este
  modulo ejecute.
- Se llama a si mismo desde ningun sitio todavia. Ningun otro modulo de
  `dlv-app` importa esto, y `dlv_app.main` no lo invoca: el entregable de
  F5-05 es "modulo" (ver `docs/05-backlog-y-asignacion-modelos.md`), no
  "integracion en la ventana". Decidir COMO y CUANDO avisar en la interfaz
  -- un globo, un menu, una linea en la barra de estado -- es trabajo de otra
  tarea, con dlv-ui de por medio.

Si el nombre "actualizador" sugiere mas que esto (descargar, verificar firma,
reemplazar, reiniciar), esa promesa NO la hace este modulo. Sustituir un
binario en marcha con permisos correctos y una via de reversion si algo sale
mal es un problema bastante mas grande que comprobar un numero de version, y
mezclarlo aqui habria sido la forma mas rapida de que ninguna de las dos
mitades quedase bien resuelta.

Las tres reglas de seguridad de esta caracteristica (regla F5-05 en el
informe de la tarea, con el mismo espiritu que F5-03 #4 para WebView2):

1. Nunca es obligatoria. No bloquea el arranque de `dlv_app.main` (de hecho
   nadie la llama desde ahi todavia, ver arriba) y nunca instala nada por su
   cuenta.
2. Se puede desactivar del todo, y `desactivado=True` se respeta sin mirar
   nada mas: ni construye la URL de consulta ni llama a `consulta`.
3. Falla en silencio hacia el lado seguro. Sin red, con el servidor caido, o
   con una respuesta corrupta (JSON invalido, campos que faltan, una version
   que no se puede interpretar como numeros), el resultado es
   `EstadoActualizacion.DESCONOCIDO` -- nunca una excepcion que propague hacia
   quien llama. Un actualizador que le impide a alguien abrir un log porque
   no pudo consultar una URL es peor que no tener actualizador.

Decision 1 -- donde vive la preferencia "desactivado" (y el modo portable)
==============================================================================
Este modulo NO lee ni escribe ningun fichero de preferencias. `desactivado`
es un argumento obligatorio de `comprobar_actualizacion` (sin valor por
omision, a proposito, mismo espiritu que la regla 4 de CLAUDE.md sobre la
clase de conversion: nada de "comodidad" que reintroduzca un olvido):
resolver ESE valor -- leyendo lo que el usuario eligio la ultima vez -- es
responsabilidad de quien llama, no de este modulo.

La razon para no decidirlo aqui es F5-02, en curso a la vez que esta tarea:
el modo portable (`portable.txt` junto al ejecutable) va a exigir cero
escritura fuera de la carpeta del programa, y ese contrato -- como se detecta
el modo portable desde codigo, donde vive exactamente "la carpeta del
programa" en un paquete `onedir` -- todavia no existe en el repositorio
mientras se escribe este fichero. Adelantarlo aqui habria significado, con
alta probabilidad, escribir en el sitio equivocado en modo portable o
duplicar la deteccion cuando F5-02 la fije, con las dos copias divergiendo
tarde o temprano.

Lo que SI queda decidido y escrito, para cuando se cablee:

- Modo NO portable: la preferencia va en la carpeta de configuracion de
  usuario del sistema operativo -- en Windows, algo como
  `%APPDATA%\\DataLogViewer\\preferencias.toml` (el analogo en Linux es
  `~/.config/DataLogViewer/` segun XDG, y en macOS
  `~/Library/Application Support/DataLogViewer/`). Es una escritura pequena
  (un punado de claves) y fuera de la carpeta del programa, que es
  exactamente lo que el modo NO portable permite.
- Modo portable: esa misma clave NO puede ir a la carpeta de perfil del
  sistema operativo, porque rompe la garantia de "cero escritura fuera de la
  carpeta" que motiva el modo portable (log en pista, ejecutable en un
  pendrive, sin dejar rastro en la maquina que lo ejecuta). Tiene que vivir
  DENTRO de la carpeta del programa, junto a `portable.txt` -- p. ej. un
  `preferencias.toml` hermano suyo. No se implementa aqui: el mecanismo para
  detectar "estoy en modo portable" y para resolver esa carpeta es contrato
  de F5-02, y este modulo no lo duplica.
- La misma preferencia guarda tambien, si el usuario la rechaza, la ULTIMA
  version que decidio ignorar (`version_descartada` mas abajo): es lo que
  permite "no vuelve a insistir" sin convertir eso en "nunca vuelve a
  avisar", porque una version MAS NUEVA que la descartada si debe notificar
  de nuevo. Vive junto a `desactivado` en el mismo fichero de preferencias,
  no en uno aparte.
- Formato: `.toml`, para quedar en el mismo lenguaje que el resto de
  configuracion legible del proyecto. Esto NO es un `data/*.toml` de datos
  del formato de log (regla 2 de CLAUDE.md no le aplica: es preferencia de
  usuario, no un descriptor de log ni un catalogo de unidades).

Decision 2 -- que se envia al comprobar
===========================================
`comprobar_actualizacion` construye la URL de consulta anadiendo UN solo
parametro a `url`: la version instalada (`?version=0.1.0`, tomada de
`dlv_app.__version__` por omision). Nada mas: ni identificador de maquina, ni
sistema operativo, ni telemetria de uso, ni el contenido o la ruta de ningun
log abierto. Es deliberado, y es la razon completa de por que esta
caracteristica tiene que ser opcional (`docs/03-arquitectura.md` SS3.10: "sin
telemetria, sin comprobacion de licencia, sin red obligatoria"): cualquier
peticion HTTP revela de por si la IP de origen a quien atiende el servidor
-- eso es inherente al protocolo, no algo que se pueda ocultar consultando
una URL -- y por eso la decision correcta no es "mandar menos datos todavia
dentro de la peticion", es "no hacer la peticion si el usuario no quiere ni
siquiera esa exposicion minima". `desactivado=True` es exactamente esa
salida.

Decision 3 -- que NO hace este modulo
=========================================
Ver la seccion de arriba ("Que hace este modulo, y que NO hace"). En una
frase: comprueba un numero de version y devuelve un resultado: nunca
descarga, nunca reemplaza, nunca reinicia.

Como se prueba (patron `FuenteApi` de dlv-ui / lectores de dlv-core, ADR-002)
================================================================================
`comprobar_actualizacion` no llama a `urllib` directamente: recibe `consulta`
-- una funcion `str -> bytes` -- como parametro obligatorio, igual que
`dlv-core` recibe objetos de lectura en vez de rutas de fichero (ADR-002,
para poder probar contra bytes en memoria) y que `FuenteApi` de `dlv-ui`
recibe un `fetch` inyectable. Las pruebas (`tests/test_actualizador.py`)
pasan una funcion falsa que devuelve una respuesta buena, una corrupta, o que
lanza la excepcion que lanzaria `urllib` sin red, con el servidor caido o con
un timeout -- nunca se abre una conexion de red real, ni en las pruebas ni
en ningun otro sitio de este fichero. `consulta_por_red` (mas abajo) es la
implementacion real con `urllib.request` de la biblioteca estandar -- sin
dependencias nuevas -- pero NINGUN test de este modulo la invoca, y tampoco
la llama nada mas en el repositorio todavia (ver "Que hace este modulo"
arriba): existe para que quien cablee esto en `dlv_app.main` no tenga que
volver a escribirla, no para ejecutarse sola en esta tarea.

URL de publicacion: PENDIENTE DE DECISION DEL PROPIETARIO
=============================================================
Hoy no existe ningun servidor que publique versiones de DataLogViewer -- el
proyecto no se ha publicado en ningun sitio todavia. `URL_COMPROBACION_
PENDIENTE` es un marcador reconocible, deliberadamente no parseable como URL
real (no tiene un esquema `http`/`https`), para que nadie lo tome por bueno
sin fijarse ni lo use sin cambiarlo antes. Inventar aqui una URL de un
servicio propio o de terceros habria sido exactamente lo que este fichero
pide no hacer: ver el informe de la tarea F5-05.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

from dlv_app import __version__ as _VERSION_INSTALADA_POR_OMISION

# Ver "URL de publicacion: PENDIENTE DE DECISION DEL PROPIETARIO" arriba. NO
# es una URL real: no tiene esquema `http(s)`, precisamente para que un uso
# accidental sin configurar falle pronto y de forma legible (`urllib` la
# rechazaria con `URLError`, que `comprobar_actualizacion` ya trata como
# DESCONOCIDO) en vez de intentar resolver un dominio que no existe.
URL_COMPROBACION_PENDIENTE = "pendiente-decision-propietario:sin-servidor-de-publicacion-todavia"

# Tiempo de espera por omision de `consulta_por_red`. Corto a proposito: esta
# comprobacion es un extra, nunca debe hacer notar una espera en el arranque
# ni en ningun otro momento (regla 1 del modulo, "nunca es obligatoria").
TIMEOUT_S_POR_OMISION = 3.0

# Firma de la funcion de consulta inyectable: recibe la URL completa (ya con
# la version instalada como parametro de consulta, ver `_url_con_version`) y
# devuelve el cuerpo crudo de la respuesta. Puede lanzar cualquier excepcion
# para representar un fallo de red -- `comprobar_actualizacion` la atrapa de
# forma deliberadamente amplia, ver su docstring.
ConsultaVersion = Callable[[str], bytes]


class EstadoActualizacion(Enum):
    """Resultado de `comprobar_actualizacion`. Cada valor es una conclusion
    distinta y quien llama debe poder distinguirlas: no es lo mismo "no hay
    nada nuevo" que "no lo se" (regla F5-03 #4 de `dlv_app.webview2`, mismo
    espiritu aqui: la duda no se disfraza de una respuesta concreta).
    """

    # `desactivado=True`: no se ha consultado nada, a proposito.
    DESACTIVADO = auto()
    # No se pudo llegar a una conclusion: sin red, servidor caido, timeout,
    # respuesta que no es JSON valido, campos que faltan, o una version (local
    # o remota) que no se pudo interpretar. Nunca bloquea nada (regla 3).
    DESCONOCIDO = auto()
    # La version remota no es mas reciente que la instalada.
    AL_DIA = auto()
    # Hay una version mas reciente, pero coincide con `version_descartada`:
    # el usuario ya dijo que no a ESTA version concreta. Una version mas
    # nueva todavia si notificaria (ver Decision 1 en el docstring).
    DESCARTADA = auto()
    # Hay una version mas reciente y no se ha descartado: es el unico estado
    # en el que `version_disponible`/`url_descarga` tienen sentido mostrar.
    DISPONIBLE = auto()


@dataclass(slots=True, frozen=True)
class ResultadoActualizacion:
    """Salida de `comprobar_actualizacion`. `version_disponible`/
    `url_descarga` solo se rellenan para `DISPONIBLE` y `DESCARTADA` (para
    `DESCARTADA`, `version_disponible` deja constancia de CUAL version es la
    que sigue descartada; `url_descarga` se omite porque nadie deberia
    navegar a partir de un estado que existe justo para no volver a insistir).
    """

    estado: EstadoActualizacion
    version_disponible: str | None = None
    url_descarga: str | None = None


def _version_como_tupla(cadena: str) -> tuple[int, ...] | None:
    """`"1.4.2"` -> `(1, 4, 2)`, o `None` si `cadena` no es una secuencia de
    enteros separados por puntos -- el unico formato de version que compara
    este modulo. `None` es una lectura tan valida como cualquier tupla: es lo
    que hace que una version remota corrupta ("v1.4.2-beta", "", un numero
    con letras) desemboque en DESCONOCIDO en vez de una comparacion que
    adivina.
    """
    partes = cadena.strip().split(".")
    numeros: list[int] = []
    for parte in partes:
        if not parte.isdigit():
            return None
        numeros.append(int(parte))
    return tuple(numeros) if numeros else None


def _es_mas_reciente(remota: str, instalada: str) -> bool | None:
    """`True`/`False` si las dos versiones se pudieron interpretar, `None` si
    cualquiera de las dos (remota O instalada) no se pudo -- ver
    `_version_como_tupla`. Comparacion por tuplas, no por texto: `"9" <
    "10"` como cadenas pero `(9,) < (10,)` como version, y son solo dos o
    tres numeros por version, no una comparacion por muestra (ADR-009 no
    aplica: nada aqui recorre las 73 M de filas de un log).
    """
    tupla_remota = _version_como_tupla(remota)
    tupla_instalada = _version_como_tupla(instalada)
    if tupla_remota is None or tupla_instalada is None:
        return None
    return tupla_remota > tupla_instalada


def _url_con_version(url: str, version_instalada: str) -> str:
    """Anade `version` a `url` como parametro de consulta, preservando los
    que ya tuviera -- mismo patron que `_url_con_credenciales` de
    `dlv_app.main`. Es el UNICO dato que este modulo agrega a la peticion,
    ver Decision 2 en el docstring del modulo.
    """
    partes = urllib.parse.urlsplit(url)
    consulta = urllib.parse.parse_qsl(partes.query)
    consulta.append(("version", version_instalada))
    return urllib.parse.urlunsplit(partes._replace(query=urllib.parse.urlencode(consulta)))


def comprobar_actualizacion(
    *,
    desactivado: bool,
    consulta: ConsultaVersion,
    version_instalada: str = _VERSION_INSTALADA_POR_OMISION,
    url: str = URL_COMPROBACION_PENDIENTE,
    version_descartada: str | None = None,
) -> ResultadoActualizacion:
    """Comprueba si hay una version mas reciente que `version_instalada`,
    usando `consulta` para obtener la respuesta cruda -- nunca `urllib`
    directamente, ver "Como se prueba" en el docstring del modulo.

    `desactivado` no tiene valor por omision a proposito (Decision 1): quien
    llama tiene que decidir explicitamente, cada vez, si esta comprobacion
    puede hacer una peticion o no. Si es `True`, se devuelve DESACTIVADO
    sin construir siquiera la URL ni llamar a `consulta` -- ninguna otra
    rama de esta funcion se ejecuta.

    La respuesta esperada de `consulta` es un cuerpo JSON con al menos
    `{"version": "X.Y.Z", "url": "https://..."}`; cualquier otra forma
    (JSON invalido, claves que faltan, tipos que no son texto) termina en
    DESCONOCIDO, igual que un fallo de red.

    Atrapa `Exception` al llamar a `consulta`, no una lista acotada de tipos
    como el resto del repositorio suele hacer (p. ej. `_esperar_servidor` de
    `dlv_app.main`, que solo espera `URLError`/`OSError`): aqui es
    deliberado. `consulta` es una funcion INYECTADA -- su implementacion real
    es `urllib` (que lanza `URLError`/`OSError`/`TimeoutError`), pero podria
    ser cualquier otra cosa en el futuro, y el contrato de esta funcion es
    "una comprobacion opcional jamas debe propagar una excepcion" (regla 3
    del modulo). Acotar la lista de excepciones aqui cambiaria esa garantia
    por una mas debil ("casi nunca propaga"), que es precisamente el fallo
    que la tarea pide evitar.
    """
    if desactivado:
        return ResultadoActualizacion(estado=EstadoActualizacion.DESACTIVADO)

    try:
        crudo = consulta(_url_con_version(url, version_instalada))
    except Exception:  # ver docstring: deliberadamente amplio, no una lista acotada
        return ResultadoActualizacion(estado=EstadoActualizacion.DESCONOCIDO)

    try:
        datos = json.loads(crudo)
        version_remota = str(datos["version"])
        url_descarga = str(datos["url"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, UnicodeDecodeError):
        return ResultadoActualizacion(estado=EstadoActualizacion.DESCONOCIDO)

    es_mas_reciente = _es_mas_reciente(version_remota, version_instalada)
    if es_mas_reciente is None:
        return ResultadoActualizacion(estado=EstadoActualizacion.DESCONOCIDO)
    if not es_mas_reciente:
        return ResultadoActualizacion(estado=EstadoActualizacion.AL_DIA)
    if version_descartada is not None and version_remota == version_descartada:
        return ResultadoActualizacion(
            estado=EstadoActualizacion.DESCARTADA, version_disponible=version_remota
        )
    return ResultadoActualizacion(
        estado=EstadoActualizacion.DISPONIBLE,
        version_disponible=version_remota,
        url_descarga=url_descarga,
    )


def consulta_por_red(url: str, *, timeout_s: float = TIMEOUT_S_POR_OMISION) -> bytes:
    """Implementacion real de `ConsultaVersion`, con `urllib.request` de la
    biblioteca estandar (regla "no anadas dependencias": nada de `requests`).

    NO la llama ningun test de este modulo ni ningun otro codigo del
    repositorio todavia -- ver "Como se prueba" en el docstring del modulo.
    Existe para que quien cablee este modulo en `dlv_app.main` no tenga que
    escribir su propia funcion de consulta; hasta entonces es codigo muerto
    a proposito, no una llamada de red que se dispare sola.
    """
    with urllib.request.urlopen(url, timeout=timeout_s) as respuesta:
        return respuesta.read()  # type: ignore[no-any-return]
