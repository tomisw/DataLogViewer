"""Sesiones de log abierto y recorte de cubos por rango (hueco de M1).

POR QUÉ EXISTE ESTE MÓDULO
==========================
Hasta aquí `dlv-api` tenía `/comandos/serie`, que devuelve la serie COMPLETA
de un canal y **vuelve a parsear el fichero entero en cada petición**. Las dos
cosas hacen inalcanzable el hito M1:

1. El renderizador (F1-23) no dibuja series, dibuja **cubos de un nivel de
   pirámide para un rango visible**. Pedir 5 M puntos para pintar 2 000
   columnas de píxeles tira por tierra el diseño de la pirámide entera.
2. Con 8 canales en pantalla, reparsear son 8 pipelines completos sobre el
   mismo fichero, contra un presupuesto de apertura de < 4 s **en total**
   (`docs/02` §2.6).

Este módulo pone lo que falta: un log se abre **una vez**, se queda en memoria
identificado por un `id_sesion`, y las peticiones siguientes son un *slice* de
NumPy sobre datos que ya están construidos.

DÓNDE ENCAJA EN LAS ADR
=======================
- **ADR-002**: todo el acceso al sistema de ficheros (leer el log, leer y
  escribir el `.dlvcache`) vive aquí, en `dlv-api`. `dlv-core` sigue
  recibiendo bytes y rutas ya resueltas, nunca decidiendo qué abrir.
- **ADR-005**: la segunda apertura no reparsea: lee el `.dlvcache` (Parquet +
  JSON) que escribió la primera, con la clave de invalidación de F1-11.
- **ADR-007**: los cubos salen en Arrow IPC binario; por aquí no pasa JSON de
  series.
- **ADR-009**: el recorte por rango es **una búsqueda binaria más un *slice***,
  no un `for` sobre muestras. Ver `indices_de_rango`.

LAS CUATRO DECISIONES QUE TIENE DENTRO
======================================
1. **La identidad de una sesión es la ruta resuelta, no el `id_sesion`.**
   Abrir dos veces el mismo fichero devuelve la MISMA sesión (y el mismo
   `id_sesion`), sin volver a parsear. Si fuese al revés, arrastrar dos veces
   la misma carpeta duplicaría en memoria un log de cientos de MB sin que
   nadie lo pidiera.
2. **Tope de sesiones abiertas, con desalojo del menos usado.** §2.6 pide «8
   logs × 30 min en paralelo sin degradación perceptible», así que ocho es el
   número que hay que aguantar; sin tope, la memoria del proceso crece hasta
   donde llegue el usuario abriendo ficheros. Se desaloja el menos usado
   recientemente, no el más antiguo: el criterio de "cuál sobra" es cuál no se
   está mirando.
3. **La cabecera se parsea sobre un PREFIJO del fichero, no sobre el fichero
   entero.** `parsear_cabecera` recorre todas las líneas de lo que se le pasa
   para localizar la primera fila de datos; con 70 MB eso es un bucle de
   Python sobre ~10^5 líneas *antes* de que Polars entre en escena. La
   cabecera real ocupa unas decenas de kB (475 canales), así que un prefijo de
   1 MB la contiene de sobra. En el camino de caché válida ese prefijo es
   **todo** lo que se lee del log, y es lo que hace alcanzable el presupuesto
   de segunda apertura (< 700 ms).
4. **Un único cerrojo para todo el registro.** Abrir un log tarda segundos y
   con el cerrojo tomado bloquea a las peticiones de cubos. Es deliberado y es
   el intercambio correcto hoy: sin él, dos peticiones simultáneas de apertura
   del mismo fichero lo parsearían dos veces (justo lo que este módulo existe
   para evitar) y se pisarían al escribir el mismo `.dlvcache`. Si algún día
   hace falta abrir un log mientras se navega por otro, lo que toca es un
   cerrojo por ruta, no quitar este.

LO QUE NO HACE, Y ES DELIBERADO
===============================
- **Solo pirámides `CONTINUO`.** Todos los canales se tratan como
  `INT32_SCALED`/`CONTINUO`, igual que ya hacía `/comandos/serie`. Los
  carriles de estado (`ENUM`, `BITS`) y los contadores tienen agregaciones de
  otra naturaleza -- moda, OR de bits, suma de delta -- y por tanto otras
  columnas: necesitan su propio endpoint, no una columna `minimo` que
  signifique algo distinto según el canal. Eso es E3.5, no esto.
- **No convierte a unidad canónica ni a la unidad elegida.** Los valores
  viajan en crudo con su `(a, b)` en cabeceras HTTP, exactamente igual que en
  `/comandos/serie`. Es lo que pide ADR-004: cambiar de °C a °F tiene que ser
  un repintado sobre los cubos que ya están en el frontend, no una petición
  nueva; si el backend ya hubiera aplicado la unidad, cada cambio de unidad
  invalidaría la caché de cubos y el presupuesto de 100 ms se caería solo.
- **No cose rangos ni cachea recortes.** Cada petición recorta desde los
  arrays completos de la sesión, que ya están en memoria. Quien cachea es el
  frontend (F1-24, `dlv-ui/src/datos/cache-cubos.ts`), que es donde ADR-007
  dice que tiene que estar.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from secrets import token_urlsafe
from typing import cast

import numpy as np

from dlv_core import __version__ as version_dlv_core
from dlv_core.almacen import ChannelSeries, Storage, construir_desde_polars
from dlv_core.cache import ClaveInvalidacion, Piramide, construir_clave, es_valida
from dlv_core.cache import escribir as escribir_cache
from dlv_core.cache import leer as leer_cache
from dlv_core.cache import leer_metadatos as leer_metadatos_cache
from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, parsear_cuerpo
from dlv_core.formatos.haltech import Cabecera, Descriptor, ErrorDeFormato, parsear_cabecera
from dlv_core.formatos.limpieza import nulificar_centinelas
from dlv_core.piramide import NivelPiramide, construir_piramide_continuo
from dlv_core.unidades import Catalogo

__all__ = [
    "MAXIMO_SESIONES",
    "TAMANO_PREFIJO_CABECERA",
    "CanalSesion",
    "RecorteCubos",
    "RegistroSesiones",
    "ResumenNivel",
    "SesionLog",
    "SesionNoEncontrada",
    "indices_de_rango",
    "recortar_nivel",
]

MAXIMO_SESIONES = 8
"""Logs abiertos a la vez antes de empezar a desalojar. El número sale de
`docs/02` §2.6 («8 logs × 30 min en paralelo»): es el escenario declarado, así
que es el que hay que aguantar, y a la vez es el techo que impide que la
memoria del proceso crezca sin límite."""

TAMANO_PREFIJO_CABECERA = 1024 * 1024
"""Bytes que se leen del log para parsear solo la cabecera. La cabecera del
AutoLog real (475 canales) ocupa unas decenas de kB, así que 1 MB la contiene
con dos órdenes de magnitud de margen; si aun así no cupiera, `_leer_cabecera`
reintenta con el fichero entero, de modo que el valor es una optimización, no
un límite del formato."""


class SesionNoEncontrada(LookupError):
    """No hay ninguna sesión abierta con ese `id_sesion` (nunca se abrió, o se
    cerró, o la desalojó el tope de `MAXIMO_SESIONES`)."""


@dataclass(slots=True, frozen=True)
class ResumenNivel:
    """Un nivel de pirámide visto desde fuera: `(factor, n_cubos)`.

    Es exactamente lo que `elegirNivel` necesita en el frontend
    (`dlv-ui/src/render/escala.ts`, interfaz `ResumenNivel`), y nada más: el
    frontend elige nivel con el número de cubos de TODO el log y la fracción
    visible, sin tener que pedir datos para decidir qué datos pedir.
    """

    factor: int
    n_cubos: int


@dataclass(slots=True, frozen=True)
class RecorteCubos:
    """Los cubos de un nivel que solapan un rango de tiempo, listos para
    serializar. Los cinco arrays son `float32` y tienen la misma longitud."""

    factor: int
    indice_inicio: int
    """Índice del primer cubo DENTRO del nivel. No lo necesita el dibujo; lo
    necesita cualquiera que quiera comprobar que el recorte cayó donde debía,
    que es la primera pregunta cuando un pico no aparece."""
    t_origen: float
    """Segundos absolutos a los que corresponde `t[0] == 0` (doble, no
    `float32`: ver el comentario de `CubosContinuos.t` en el frontend)."""
    t: np.ndarray
    minimo: np.ndarray
    maximo: np.ndarray
    primero: np.ndarray
    ultimo: np.ndarray

    @property
    def n_cubos(self) -> int:
        return len(self.t)


@dataclass(slots=True, frozen=True)
class CanalSesion:
    """Un canal ya abierto: sus metadatos, su serie y su pirámide.

    `t_segundos` es el eje de tiempo del GRUPO DE MUESTREO al que pertenece el
    canal (ADR-003: los canales de un mismo grupo comparten `t` por
    referencia), en segundos y en doble precisión, ya convertido una sola vez
    al abrir. Se guarda en segundos y no en los milisegundos de
    `ChannelSeries.t` porque segundos es la unidad del contrato del frontend
    (`Vista.t0`/`t1`, `CubosContinuos.tOrigen`) y convertir en cada petición
    sería trabajo por muestra repetido, justo lo que ADR-009 prohíbe.
    """

    id: int
    nombre: str
    dimension: str | None
    confianza: str
    serie: ChannelSeries
    piramide: list[NivelPiramide]
    t_segundos: np.ndarray

    @property
    def niveles(self) -> tuple[ResumenNivel, ...]:
        return tuple(ResumenNivel(factor=n.factor, n_cubos=n.n_cubos) for n in self.piramide)

    @property
    def n_muestras(self) -> int:
        return len(self.serie.t)


@dataclass(slots=True)
class SesionLog:
    """Un log abierto: cabecera + almacén + pirámides, vivos en memoria."""

    id_sesion: str
    ruta: Path
    formato: str
    version: str
    canales: tuple[CanalSesion, ...]
    por_id: dict[int, CanalSesion]
    avisos: tuple[str, ...]
    desde_cache: bool
    """`True` si esta sesión se reconstruyó desde el `.dlvcache` en vez de
    reparsear el log. Es lo que hay que mirar cuando la segunda apertura no
    cumple el presupuesto: si sale `False`, la caché se está invalidando."""
    clave: ClaveInvalidacion
    abierta_en: float = field(default_factory=time.time)

    @property
    def n_canales(self) -> int:
        return len(self.canales)

    @property
    def t_inicio(self) -> float:
        """Primer instante del log, en segundos. Es 0,0 por construcción
        (`construir_desde_polars` resta `t0`), pero se devuelve calculado y no
        cableado: el día que haya segmentos con desfase, cablear un 0 sería un
        error mudo."""
        for canal in self.canales:
            if canal.t_segundos.size:
                return float(canal.t_segundos[0])
        return 0.0

    @property
    def t_fin(self) -> float:
        """Último instante del log, en segundos: el máximo entre los grupos de
        muestreo (que pueden no terminar a la vez)."""
        fin = 0.0
        for canal in self.canales:
            if canal.t_segundos.size:
                fin = max(fin, float(canal.t_segundos[-1]))
        return fin


# --------------------------------------------------------------------------- #
# Recorte por rango: búsqueda binaria + slice, sin bucle por muestra (ADR-009)
# --------------------------------------------------------------------------- #
def indices_de_rango(
    t_segundos: np.ndarray, *, factor: int, n_cubos: int, t0: float, t1: float
) -> tuple[int, int]:
    """`[inicio, fin)` de los cubos del nivel que SOLAPAN `[t0, t1]`.

    QUÉ CUENTA COMO SOLAPAR
    -----------------------
    El cubo `i` de un nivel de factor `f` agrega las muestras `[i*f, (i+1)*f)`
    y se dibuja en el instante de la primera de ellas, `t[i*f]`. El frontend lo
    trata igual (`indiceEn` en `cache-cubos.ts`: «un cubo empieza en su
    instante y dura hasta el siguiente»), así que el cubo `i` ocupa el
    intervalo `[t[i*f], t[(i+1)*f])`. Solapan con `[t0, t1]` exactamente los
    cubos con `t_cubo[i] <= t1` y `t_cubo[i+1] > t0`.

    Eso incluye **el cubo que empieza antes de `t0`**, y tiene que incluirlo:
    sin él, el trazo empezaría en el primer cubo posterior al borde izquierdo y
    el gráfico aparecería con un hueco en el borde que se diagnostica como
    "faltan datos" en vez de como "falta un cubo".

    DÓNDE TERMINA EL ÚLTIMO CUBO
    ----------------------------
    Un nivel de factor `f` cubre las muestras `[0, n_cubos*f)` y **no todas las
    del log**: los niveles altos truncan la cola que no completa un cubo (ver
    `_siguiente_nivel_continuo`). Así que el último cubo del nivel termina en
    la primera muestra que el nivel ya no cubre, si la hay, y en la última
    muestra del log si el nivel llega hasta el final. Sin esa distinción, un
    rango entero situado en la cola truncada devolvería el último cubo -- datos
    de otro tramo -- en vez de nada.

    POR QUÉ NO HAY BÚSQUEDA SOBRE LOS CUBOS
    ---------------------------------------
    La búsqueda binaria se hace **una sola vez, sobre el eje de muestras
    completo**, que es contiguo; el índice de cubo sale dividiendo por el
    factor. Buscar sobre `t_segundos[::factor]` habría sido lo obvio, pero esa
    vista es no contigua y `searchsorted` la materializa: una copia de hasta
    varios MB por petición y por canal, para ahorrar una división entera.

    Devuelve `(0, 0)` -- rango vacío -- cuando no hay ningún cubo que solape:
    nivel vacío, rango invertido, `t1` anterior al primer cubo, o `t0`
    posterior al final de lo que ESTE nivel cubre.
    """
    if n_cubos <= 0 or t1 < t0 or t_segundos.size == 0:
        return (0, 0)

    primera_no_cubierta = n_cubos * factor
    if primera_no_cubierta < t_segundos.size:
        fuera_por_la_derecha = t0 >= float(t_segundos[primera_no_cubierta])
    else:
        fuera_por_la_derecha = t0 > float(t_segundos[-1])
    if fuera_por_la_derecha:
        return (0, 0)

    # `side="right"` menos uno = índice de la última muestra con `t <= valor`,
    # que es la definición de "la muestra vigente en ese instante".
    ultima_hasta_t1 = int(np.searchsorted(t_segundos, t1, side="right")) - 1
    if ultima_hasta_t1 < 0:
        return (0, 0)  # todo el nivel es posterior al rango pedido

    ultima_hasta_t0 = max(int(np.searchsorted(t_segundos, t0, side="right")) - 1, 0)
    return (ultima_hasta_t0 // factor, min(ultima_hasta_t1 // factor + 1, n_cubos))


def recortar_nivel(
    t_segundos: np.ndarray, nivel: NivelPiramide, *, t0: float, t1: float
) -> RecorteCubos:
    """Los cubos de `nivel` que solapan `[t0, t1]`, ya en `float32` y con `t`
    relativo a su propio origen.

    Cinco *slices* de NumPy y una resta vectorizada: ninguna operación de esta
    función escala con el número de muestras del log (ADR-009). El `t` se resta
    en doble precisión ANTES de bajar a `float32`, que es lo que evita el
    temblor al ampliar mucho (mismo motivo que documenta `CubosContinuos.t`).
    """
    factor = nivel.factor
    inicio, fin = indices_de_rango(t_segundos, factor=factor, n_cubos=nivel.n_cubos, t0=t0, t1=t1)
    vacio = np.empty(0, dtype=np.float32)
    if fin <= inicio:
        return RecorteCubos(
            factor=factor,
            indice_inicio=0,
            t_origen=0.0,
            t=vacio,
            minimo=vacio,
            maximo=vacio,
            primero=vacio,
            ultimo=vacio,
        )

    # `[inicio*f : fin*f : f]` da exactamente `fin - inicio` elementos, que es
    # el instante de cada cubo del recorte: el de su primera muestra.
    t_cubos = t_segundos[inicio * factor : fin * factor : factor]
    t_origen = float(t_cubos[0])
    return RecorteCubos(
        factor=factor,
        indice_inicio=inicio,
        t_origen=t_origen,
        t=(t_cubos - t_origen).astype(np.float32),
        minimo=nivel.minimo[inicio:fin].astype(np.float32),
        maximo=nivel.maximo[inicio:fin].astype(np.float32),
        primero=nivel.primero[inicio:fin].astype(np.float32),
        ultimo=nivel.ultimo[inicio:fin].astype(np.float32),
    )


# --------------------------------------------------------------------------- #
# Lectura del log y de su caché (ADR-002: el disco se toca aquí, no en dlv-core)
# --------------------------------------------------------------------------- #
def huella_descriptor(ruta_toml: Path) -> str:
    """Hace de «versión del descriptor de formato» en la clave de invalidación
    de ADR-005.

    `Descriptor` no lleva número de versión, y ponérselo al TOML sería inventar
    un campo nuevo en un fichero de `data/` (que son datos, no código, y no se
    reformatean). El hash de su contenido dice lo mismo y no puede quedarse sin
    subir cuando alguien edita el fichero, que es el modo de fallo real de un
    número de versión escrito a mano.
    """
    return hashlib.sha256(ruta_toml.read_bytes()).hexdigest()[:16]


def _leer_cabecera(ruta: Path, descriptor: Descriptor) -> tuple[Cabecera, bytes | None]:
    """Parsea la cabecera leyendo lo menos posible del fichero.

    Devuelve `(cabecera, datos_completos_o_None)`: el segundo elemento es el
    contenido íntegro del log **solo si hubo que leerlo de todas formas**, para
    que quien vaya a parsear el cuerpo no lo lea dos veces.

    Si el prefijo no basta (cabecera enorme o fichero raro), `parsear_cabecera`
    lanza `ErrorDeFormato` -- típicamente "la cabecera parece truncada" -- y se
    reintenta con el fichero entero. Un fichero de verdad inválido pasa por ese
    reintento y vuelve a fallar con el mismo mensaje: se paga una lectura de
    más en el camino de error, no en el camino bueno.
    """
    if ruta.stat().st_size <= TAMANO_PREFIJO_CABECERA:
        datos = ruta.read_bytes()
        return parsear_cabecera(datos, descriptor), datos

    with ruta.open("rb") as fh:
        prefijo = fh.read(TAMANO_PREFIJO_CABECERA)
    try:
        return parsear_cabecera(prefijo, descriptor), None
    except ErrorDeFormato:
        datos = ruta.read_bytes()
        return parsear_cabecera(datos, descriptor), datos


def _construir_series_y_piramides(
    datos: bytes, cabecera: Cabecera, catalogo: Catalogo
) -> tuple[list[ChannelSeries], list[Piramide]]:
    """El pipeline completo de la ruta de ingesta (`docs/03` §3.4 pasos 3-7)
    sobre los bytes ya leídos: cuerpo -> limpieza -> almacén -> pirámide.

    El bucle es por CANAL (cientos), no por muestra (millones): cada iteración
    construye la pirámide entera de un canal con operaciones vectorizadas de
    NumPy (ADR-009).
    """
    crudo = parsear_cuerpo(datos, cabecera)
    limpio = nulificar_centinelas(crudo, catalogo)
    storage_por_columna = {
        columna_polars(c.columna): Storage.INT32_SCALED for c in cabecera.canales
    }
    series = construir_desde_polars(
        limpio, cabecera, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage_por_columna
    )
    piramides: list[Piramide] = [construir_piramide_continuo(s.v) for s in series]
    return series, piramides


def _t_segundos_por_grupo(series: Sequence[ChannelSeries]) -> dict[int, np.ndarray]:
    """Eje de tiempo en segundos (doble) por grupo de muestreo, calculado una
    sola vez.

    La clave es `id(serie.t)`: ADR-003 dice que los canales de un mismo grupo
    comparten el array `t` **por referencia**, así que la identidad del objeto
    ES la identidad del grupo, sin tener que recalcular la agrupación. Las
    referencias viven en `series`, que el llamador conserva, así que ningún
    `id` puede reciclarse mientras el diccionario esté en uso.
    """
    por_grupo: dict[int, np.ndarray] = {}
    for serie in series:
        clave = id(serie.t)
        if clave not in por_grupo:
            por_grupo[clave] = serie.t.astype(np.float64) / 1000.0
    return por_grupo


# --------------------------------------------------------------------------- #
# Registro de sesiones
# --------------------------------------------------------------------------- #
class RegistroSesiones:
    """Los logs abiertos del proceso, con tope y desalojo del menos usado.

    Todo el estado mutable de `dlv-api` vive aquí, detrás de un cerrojo (ver
    la decisión 4 del docstring del módulo). El resto del servidor es sin
    estado.
    """

    def __init__(
        self,
        *,
        descriptor: Descriptor,
        catalogo: Catalogo,
        version_descriptor: str,
        dir_cache: Path,
        maximo: int = MAXIMO_SESIONES,
    ) -> None:
        if maximo < 1:
            raise ValueError(f"el tope de sesiones tiene que ser >= 1, se dio {maximo}")
        self._descriptor = descriptor
        self._catalogo = catalogo
        self._version_descriptor = version_descriptor
        self._dir_cache = dir_cache
        self._maximo = maximo
        self._cerrojo = threading.RLock()
        # `dict` conserva el orden de inserción, que es todo lo que hace falta
        # para un LRU: borrar y reinsertar la clave usada la lleva al final.
        # Mismo truco (y mismo motivo) que la `CacheDeCubos` del frontend.
        self._sesiones: dict[str, SesionLog] = {}
        self._por_ruta: dict[Path, str] = {}

    @property
    def maximo(self) -> int:
        return self._maximo

    def __len__(self) -> int:
        with self._cerrojo:
            return len(self._sesiones)

    def __iter__(self) -> Iterator[SesionLog]:
        with self._cerrojo:
            return iter(list(self._sesiones.values()))

    def abrir(self, ruta: Path) -> tuple[SesionLog, bool]:
        """Abre `ruta` (o devuelve la sesión que ya la tenía abierta).

        Devuelve `(sesion, reutilizada)`. `reutilizada=True` significa que no
        se ha tocado el disco en absoluto: ni el log, ni la caché. Es el caso
        de "el usuario ha vuelto a soltar el mismo fichero", y es lo que evita
        duplicar cientos de MB en memoria.

        Una sesión reutilizada se revalida contra `(tamaño, mtime)` del
        fichero: si el log ha cambiado en disco desde que se abrió, se cierra y
        se vuelve a abrir. Un log que se sigue escribiendo mientras se mira es
        un caso real en banco de pruebas, y servir cubos viejos como si fueran
        los de ahora es la clase de fallo que no se nota.
        """
        resuelta = ruta.resolve()
        with self._cerrojo:
            clave = self._clave_invalidacion(resuelta)
            id_existente = self._por_ruta.get(resuelta)
            if id_existente is not None:
                sesion = self._sesiones[id_existente]
                if sesion.clave == clave:
                    self._marcar_usada(id_existente)
                    return sesion, True
                self._cerrar(id_existente)

            sesion = self._construir(resuelta, clave)
            self._sesiones[sesion.id_sesion] = sesion
            self._por_ruta[resuelta] = sesion.id_sesion
            self._desalojar_hasta_caber()
            return sesion, False

    def obtener(self, id_sesion: str) -> SesionLog:
        """La sesión abierta con ese id, o `SesionNoEncontrada`.

        Consultar una sesión la marca como recién usada: si no lo hiciera, el
        log que se está mirando podría ser justo el que desaloja la apertura
        del siguiente.
        """
        with self._cerrojo:
            sesion = self._sesiones.get(id_sesion)
            if sesion is None:
                raise SesionNoEncontrada(
                    f"no hay ninguna sesión abierta con id {id_sesion!r} "
                    "(¿se cerró, o la desalojó el tope de logs abiertos?)"
                )
            self._marcar_usada(id_sesion)
            return sesion

    def cerrar(self, id_sesion: str) -> bool:
        """Cierra una sesión y libera su memoria. `False` si no existía."""
        with self._cerrojo:
            if id_sesion not in self._sesiones:
                return False
            self._cerrar(id_sesion)
            return True

    def cerrar_todas(self) -> int:
        with self._cerrojo:
            n = len(self._sesiones)
            self._sesiones.clear()
            self._por_ruta.clear()
            return n

    # ----------------------------------------------------------------- #
    # Interno. Todo lo de aquí abajo se llama con el cerrojo ya tomado.
    # ----------------------------------------------------------------- #
    def _marcar_usada(self, id_sesion: str) -> None:
        sesion = self._sesiones.pop(id_sesion)
        self._sesiones[id_sesion] = sesion

    def _cerrar(self, id_sesion: str) -> None:
        sesion = self._sesiones.pop(id_sesion)
        if self._por_ruta.get(sesion.ruta) == id_sesion:
            del self._por_ruta[sesion.ruta]

    def _desalojar_hasta_caber(self) -> None:
        """Desaloja los menos usados hasta cumplir el tope.

        Nunca desaloja la sesión recién insertada: es la última del orden de
        inserción, así que el bucle termina antes de llegar a ella mientras el
        tope sea >= 1 (que lo garantiza el constructor)."""
        while len(self._sesiones) > self._maximo:
            self._cerrar(next(iter(self._sesiones)))

    def _clave_invalidacion(self, ruta: Path) -> ClaveInvalidacion:
        estado = ruta.stat()
        return construir_clave(
            ruta,
            tamano_bytes=estado.st_size,
            mtime_ns=estado.st_mtime_ns,
            version_parser=version_dlv_core,
            version_descriptor_formato=self._version_descriptor,
        )

    def _ruta_cache(self, ruta: Path) -> Path:
        """Dónde vive el `.dlvcache` de un log.

        En una carpeta de caché propia, **no junto al log**: escribir al lado
        del fichero de origen ensucia la carpeta del usuario y, en este
        repositorio, escribiría dentro de `samples/real/`, que no se toca. El
        nombre lleva un hash de la ruta absoluta porque dos logs con el mismo
        nombre en carpetas distintas son un caso normal (una carpeta por día de
        pista) y compartirían fichero de caché.
        """
        marca = hashlib.sha256(str(ruta).encode("utf-8")).hexdigest()[:16]
        return self._dir_cache / f"{ruta.stem}-{marca}.dlvcache"

    def _construir(self, ruta: Path, clave: ClaveInvalidacion) -> SesionLog:
        cabecera, datos = _leer_cabecera(ruta, self._descriptor)
        avisos = [a.mensaje for a in cabecera.avisos]

        series, piramides, desde_cache, avisos_cache = self._series_y_piramides(
            ruta, clave, cabecera, datos
        )
        avisos.extend(avisos_cache)

        t_por_grupo = _t_segundos_por_grupo(series)
        por_id_nativo = {s.key.id_nativo: (s, p) for s, p in zip(series, piramides, strict=True)}

        canales: list[CanalSesion] = []
        for canal in cabecera.canales:
            par = por_id_nativo.get(str(canal.id))
            if par is None:
                # Canal declarado en la cabecera pero sin columna en el cuerpo.
                # No es un error de formato: se avisa y el canal queda en la
                # lista sin niveles, que es como el frontend sabe que no hay
                # nada que pedir de él.
                avisos.append(
                    f"el canal {canal.id} ('{canal.nombre}') no tiene datos en el cuerpo del log"
                )
                continue
            serie, piramide = par
            canales.append(
                CanalSesion(
                    id=canal.id,
                    nombre=canal.nombre,
                    dimension=serie.dimension,
                    confianza=canal.confianza,
                    serie=serie,
                    # `Piramide` es la unión de las cuatro variantes; aquí
                    # siempre es `CONTINUO` porque `_construir_series_y_piramides`
                    # llama a `construir_piramide_continuo` para todos los
                    # canales (ver "lo que no hace" en el docstring del módulo).
                    piramide=cast(list[NivelPiramide], piramide),
                    t_segundos=t_por_grupo[id(serie.t)],
                )
            )

        return SesionLog(
            id_sesion=token_urlsafe(12),
            ruta=ruta,
            formato=cabecera.formato,
            version=cabecera.version,
            canales=tuple(canales),
            por_id={c.id: c for c in canales},
            avisos=tuple(avisos),
            desde_cache=desde_cache,
            clave=clave,
        )

    def _series_y_piramides(
        self, ruta: Path, clave: ClaveInvalidacion, cabecera: Cabecera, datos: bytes | None
    ) -> tuple[list[ChannelSeries], list[Piramide], bool, list[str]]:
        """Series + pirámides desde la caché de F1-11 si sirve, y si no
        parseando el log y dejando la caché escrita para la próxima vez.

        Ni un fallo al leer la caché ni uno al escribirla impiden abrir el log:
        la caché es una optimización, y una caché corrupta o un disco lleno
        tienen que costar tiempo, no la apertura. Los dos casos dejan aviso,
        porque una caché que nunca sirve es un presupuesto de segunda apertura
        incumplido en silencio.
        """
        avisos: list[str] = []
        base = self._ruta_cache(ruta)

        try:
            metadatos = leer_metadatos_cache(base)
        except (OSError, ValueError, KeyError) as e:
            metadatos = None
            avisos.append(f"la caché de parseo no se ha podido leer ({e}); se reparsea el log")

        if metadatos is not None and es_valida(metadatos.clave, clave):
            try:
                series, piramides, _ = leer_cache(base)
                return series, piramides, True, avisos
            except (OSError, ValueError, KeyError) as e:
                avisos.append(
                    f"la caché de parseo está incompleta o corrupta ({e}); se reparsea el log"
                )

        if datos is None:
            datos = ruta.read_bytes()
        series, piramides = _construir_series_y_piramides(datos, cabecera, self._catalogo)

        try:
            self._dir_cache.mkdir(parents=True, exist_ok=True)
            escribir_cache(base, clave, series, piramides)
        except OSError as e:
            avisos.append(
                f"no se ha podido escribir la caché de parseo en {base} ({e}); "
                "la próxima apertura de este log volverá a parsearlo entero"
            )
        return series, piramides, False, avisos
