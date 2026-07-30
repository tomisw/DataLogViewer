"""Resolución de rutas arrastradas y soltadas; apertura múltiple (tarea F1-34).

Qué hace y qué no hace
======================
Este módulo NO captura el evento de arrastrar y soltar -- eso es `dlv-ui`
(frontend) y es una tarea aparte. Lo que hace es la lógica de después: dado el
conjunto de rutas que el sistema operativo ya entregó (ficheros y carpetas
mezclados, en cualquier orden), decide qué abrir, qué es candidato al camino
de CSV genérico (fase FG, todavía no implementada) y qué descartar -- avisando
siempre, sin lanzar nunca por una ruta individual mala (E1.7, "avisa y
sigue": una carpeta con 3 logs válidos y 1 fichero basura debe abrir los 3 y
avisar del cuarto, no fallar entera).

Por qué vive en `dlv-api` y no en `dlv-core`
=============================================
El paso 1, "expandir una carpeta a los ficheros que contiene", es
inequívocamente acceso al sistema de ficheros: hay que listar un directorio y
decidir qué hay dentro, no solo leer bytes que alguien ya abrió. ADR-002 traza
la frontera exactamente ahí -- `dlv_core.__init__` lo dice explícito: "no
accede al sistema de ficheros por su cuenta: toda función que necesite leer
algo recibe un objeto de lectura (`IO[bytes]`, ruta ya resuelta, etc.) como
parámetro". `dlv_core.formatos.haltech.sondear_formato` es la prueba en el
propio código: recibe `bytes`, no una ruta, y mucho menos un directorio.
`dlv-api` es la capa que sí tiene ese permiso (`dlv_api.main.abrir_cabecera`
ya hace `Path.read_bytes()`), así que es donde encaja "recorrer una carpeta
buscando logs". Este módulo reutiliza `sondear_formato` (que sí es de
`dlv-core`, y con razón: reconocer una firma en unos bytes no toca disco) para
la parte de clasificación, y aporta solo la parte de sistema de ficheros que
`dlv-core` no puede tener.

Decisiones de diseño
=====================
**Recursividad**: se recorre cada carpeta soltada recursivamente
(`Path.rglob`), no solo un nivel. Motivo: una carpeta de sesión de banco de
pruebas típica organiza los logs por día o por tanda en subcarpetas
(`2026-07-29/`, `tanda_3/`...); limitarse a un nivel dejaría fuera justo los
logs más recientes sin avisar de nada, que es la clase de pérdida silenciosa
que E1.7 prohíbe. El coste (recorrer subcarpetas irrelevantes) es barato
comparado con el de no encontrar un log que el usuario esperaba ver. Se
excluyen las entradas ocultas (cualquier componente de la ruta relativa que
empiece por `.`, tipo `.git/`) para no arrastrar metadatos de control de
versiones que nadie suelta a propósito.

**Sondeo, no lectura completa**: se leen como máximo los primeros
`TAMANO_SONDEO` bytes (64 kB, docs/03 §3.4 paso 1) de cada fichero para
decidir su formato con `sondear_formato`. Un log real puede pesar decenas de
MB; leerlo entero solo para clasificarlo sería trabajo desperdiciado que
adelanta un paso (parsear cabecera y cuerpo) que no toca en este módulo.

**Ficheros propios de la aplicación** (`.dlvproj`, `.dlvprofile`,
`.dlvimport`, `.dlvcache`, docs/03 §3.9): nunca son un log que abrir, así que
se descartan siempre, se reconozcan o no como CSV. Se avisa (no se ignoran en
silencio) porque soltar un `.dlvproj` junto con logs es un caso plausible
-- el usuario reabre una sesión completa arrastrando la carpeta del proyecto
-- y merece decir explícitamente "esto no es un log, es un fichero de
proyecto" en vez de dejar que parezca que se ha perdido sin más.

**CSV no reconocido vs. "otra cosa"**: un fichero con extensión `.csv` que
`sondear_formato` no reconoce es candidato al camino de CSV genérico (fase
FG, docs/07): no es un error, es justo el caso para el que existe esa fase.
Cualquier otra extensión (`.png`, `.exe`, sin extensión...) no es un log
plausible y se descarta con aviso.

**Deduplicación**: si el usuario suelta una carpeta y, además, un fichero que
ya está dentro de ella (o la misma carpeta dos veces, o dos rutas que
resuelven al mismo fichero por symlink o ruta relativa distinta), ese log no
se abre dos veces. La clave de deduplicación es `Path.resolve()`: convierte
cada ruta a su forma absoluta y canónica antes de comparar. No hace falta
normalizar mayúsculas/minúsculas a mano -- `pathlib` ya compara e indexa
`WindowsPath` sin distinguir caja (respeta la semántica del sistema de
ficheros de cada SO), así que el mismo `Path` sirve como clave de `dict` en
Windows y en POSIX sin código adicional.

**Orden de salida**: alfabético por ruta resuelta (`Path.resolve()`), no el
orden en que el usuario soltó las rutas ni el que devuelve el recorrido del
sistema de ficheros. El orden de llegada de `iterdir`/`rglob` no está
garantizado por el sistema operativo y el orden de arrastre depende de cómo
el usuario seleccionó los ficheros en su gestor de ficheros; un orden
alfabético es el único de los tres que es estable frente a soltar el mismo
conjunto de rutas en distinto orden o momento, que es la condición para que
la lista en la interfaz no "baile" entre una apertura y la siguiente.

**Nunca lanza por una ruta individual mala**: ninguna excepción de una ruta
concreta (no existe, no se puede leer, cabecera corrupta detectada por
`sondear_formato` -- que ya de por sí no lanza, ver su docstring) se propaga
fuera de `resolver_rutas_soltadas`. Todo error de E/S puntual (`OSError`) se
convierte en un `Aviso` y se continúa con las demás rutas.

Sin dependencias nuevas: solo `pathlib` y lo que ya trae `dlv-core`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dlv_core.formatos.haltech import Descriptor, sondear_formato
from dlv_core.informe_importacion import InformeImportacion
from dlv_core.informes import Aviso

__all__ = [
    "EXTENSIONES_PROPIAS",
    "TAMANO_SONDEO",
    "LogNativo",
    "ResolucionArrastre",
    "resolver_rutas_soltadas",
]

TAMANO_SONDEO = 64 * 1024
"""Bytes que se leen de cada fichero para sondear su formato (docs/03 §3.4,
paso 1: "primeros 64 kB"). Ni una firma de formato nativo ni la detección
genérica de la fase FG necesitan el fichero completo para esta decisión."""

EXTENSIONES_PROPIAS = frozenset({".dlvproj", ".dlvprofile", ".dlvimport", ".dlvcache"})
"""Extensiones de fichero de la propia aplicación (docs/03 §3.9). Nunca son un
log que abrir, se reconozcan o no como CSV por su contenido."""


@dataclass(slots=True, frozen=True)
class LogNativo:
    """Un fichero que `sondear_formato` reconoce como un formato nativo conocido."""

    ruta: Path
    """Ruta absoluta y canónica (`Path.resolve()`) del fichero."""
    formato: str
    """`Descriptor.formato` del formato reconocido (p. ej. `"haltech_nsp"`)."""


@dataclass(slots=True, frozen=True)
class ResolucionArrastre:
    """Resultado de clasificar un conjunto de rutas soltadas (ficheros y/o carpetas).

    `nativos` y `genericos` son, juntos, "lo que hay que abrir"; todo lo demás
    -- rutas inexistentes, carpetas vacías, ficheros de la propia aplicación,
    ficheros que no parecen un log -- está en `informe`, no en una lista
    tipada aparte: es exactamente el mismo patrón que ya usa el resto de la
    ruta de ingesta (`docs/03` §3.4 paso 9) para lo que no bloquea la carga
    pero el usuario debe poder ver.
    """

    nativos: tuple[LogNativo, ...]
    """Logs en un formato nativo reconocido, listos para `parsear_cabecera`."""
    genericos: tuple[Path, ...]
    """CSV que no se reconocen como ningún formato nativo: candidatos al
    camino de CSV genérico (fase FG, docs/07), todavía no implementado."""
    informe: InformeImportacion
    """Avisos de todo lo que se descartó y por qué (rutas inexistentes,
    carpetas vacías, ficheros de la aplicación, ficheros no reconocibles)."""

    @property
    def total_para_abrir(self) -> int:
        """Cuántos logs (nativos + genéricos) hay que abrir en total."""
        return len(self.nativos) + len(self.genericos)


def resolver_rutas_soltadas(
    rutas: Iterable[Path | str],
    descriptores: tuple[Descriptor, ...],
) -> ResolucionArrastre:
    """Resuelve un conjunto de rutas soltadas (ficheros y/o carpetas, mezclados)
    en la lista de logs que hay que abrir.

    `descriptores` son los descriptores de formato nativo contra los que
    sondear cada fichero (los mismos que recibiría `sondear_formato`);
    cargarlos es responsabilidad de quien llama (en `dlv-api`, ya cacheados
    -- ver `dlv_api.main._descriptor_haltech`), no de este módulo.

    No lanza por ninguna ruta individual: ver la sección "Nunca lanza..." del
    docstring del módulo.
    """
    avisos: list[Aviso] = []
    nativos: dict[Path, LogNativo] = {}
    genericos: set[Path] = set()

    for entrada in rutas:
        ruta = Path(entrada)
        if not ruta.exists():
            avisos.append(Aviso("ruta_no_encontrada", f"no existe la ruta: {ruta}"))
            continue

        if ruta.is_dir():
            ficheros = _expandir_carpeta(ruta, avisos)
            if not ficheros:
                avisos.append(
                    Aviso("carpeta_vacia", f"la carpeta no contiene ningún fichero: {ruta}")
                )
                continue
        else:
            ficheros = (ruta,)

        for fichero in ficheros:
            _clasificar_fichero(fichero, descriptores, nativos, genericos, avisos)

    informe = InformeImportacion()
    informe.agregar(avisos)

    return ResolucionArrastre(
        nativos=tuple(sorted(nativos.values(), key=lambda ln: ln.ruta)),
        genericos=tuple(sorted(genericos)),
        informe=informe,
    )


def _expandir_carpeta(carpeta: Path, avisos: list[Aviso]) -> tuple[Path, ...]:
    """Ficheros que contiene `carpeta`, recursivamente (ver docstring del módulo).

    Se excluye cualquier entrada bajo un componente oculto (empieza por `.`,
    p. ej. `.git/`). Un error de E/S al recorrer (permisos, dispositivo
    desconectado a mitad de recorrido) se avisa y se sigue con lo que ya se
    había encontrado, en vez de perder también las rutas soltadas después de
    la que falla.
    """
    ficheros: list[Path] = []
    try:
        for entrada in carpeta.rglob("*"):
            relativa = entrada.relative_to(carpeta)
            if any(parte.startswith(".") for parte in relativa.parts):
                continue
            if entrada.is_file():
                ficheros.append(entrada)
    except OSError as e:
        avisos.append(Aviso("carpeta_no_legible", f"no se puede recorrer {carpeta}: {e}"))
    return tuple(ficheros)


def _clasificar_fichero(
    fichero: Path,
    descriptores: tuple[Descriptor, ...],
    nativos: dict[Path, LogNativo],
    genericos: set[Path],
    avisos: list[Aviso],
) -> None:
    """Clasifica un único fichero ya existente y añade el resultado a
    `nativos`/`genericos`, o un `Aviso` a `avisos` si se descarta.

    La clave de deduplicación es la ruta resuelta (`Path.resolve()`): si este
    fichero ya está en `nativos` o en `genericos` -- porque llegó por otra
    ruta directa o por la expansión de otra carpeta -- no se procesa de
    nuevo. Un `OSError` al abrir o leer (permisos, fichero borrado entre el
    listado y la lectura) se convierte en aviso, nunca en excepción.
    """
    resuelto = fichero.resolve()
    if resuelto in nativos or resuelto in genericos:
        return

    sufijo = resuelto.suffix.lower()
    if sufijo in EXTENSIONES_PROPIAS:
        avisos.append(
            Aviso(
                "fichero_de_aplicacion",
                f"{resuelto} es un fichero de la propia aplicación ({sufijo}), no un log: se omite",
            )
        )
        return

    try:
        with resuelto.open("rb") as fh:
            cabecera = fh.read(TAMANO_SONDEO)
    except OSError as e:
        avisos.append(Aviso("fichero_no_legible", f"no se puede leer {resuelto}: {e}"))
        return

    if not cabecera:
        avisos.append(Aviso("fichero_vacio", f"{resuelto} está vacío: no hay nada que abrir"))
        return

    descriptor = sondear_formato(cabecera, descriptores)
    if descriptor is not None:
        nativos[resuelto] = LogNativo(ruta=resuelto, formato=descriptor.formato)
        return

    if sufijo == ".csv":
        # No reconocido como ningún formato nativo, pero es un CSV: candidato
        # al camino genérico (fase FG), no un error (docstring de
        # `sondear_formato`).
        genericos.add(resuelto)
        return

    avisos.append(
        Aviso(
            "fichero_no_reconocido",
            f"{resuelto} no es un log reconocido (ni formato nativo ni CSV): se omite",
        )
    )
