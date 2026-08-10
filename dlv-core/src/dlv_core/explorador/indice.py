"""Índice de una carpeta de logs, con huella y revalidación (FE-01).

Especificación: `docs/02-alcance-y-plan.md` §2.5 (E15.6 y E15.7) y los riesgos
R14 y R15 de §2.8. Presupuestos aplicables de §2.6: una carpeta de 200 logs en
frío en menos de 60 s, y la reapertura de una ya indexada en menos de 500 ms.

QUÉ RESUELVE ESTE MÓDULO
========================
El presupuesto de reapertura es lo que obliga a que exista un índice: si al
volver a abrir la misma carpeta hubiera que recalcular el resumen de los 200
logs, la tabla tardaría lo mismo que la primera vez. Así que el índice guarda lo
ya calculado y este módulo decide, en cada apertura, **qué hay que recalcular y
qué se puede reutilizar**.

Esa decisión es todo lo que hace FE-01. El resumen de cada log —los agregados por
rol que llenan las columnas de la tabla— es FE-02, y aquí viaja como un valor
opaco (`resumen`) que este módulo guarda y devuelve sin interpretar.

LA HUELLA NO SE INVENTA AQUÍ: ES LA DE `cache.py`
==================================================
`huella.py` (extraída de `cache.py`, F1-11, ADR-005) ya define qué invalida un
resultado derivado de un fichero: `ClaveInvalidacion` con ruta, tamaño, `mtime_ns`
y las versiones del parser, del descriptor de formato y del esquema. Este módulo
**la reutiliza tal cual** en vez de escribir una segunda huella.

Vivía dentro de `cache.py`, que importa NumPy y Polars en su cabecera, así que
reutilizarla desde allí arrastraba las dos dependencias a un planificador que solo
compara enteros y cadenas —y lo hacía inejecutable en un entorno sin ellas—. Se le
dio un módulo propio sin dependencias, igual que `Aviso` salió de
`formatos/haltech.py` a `informes.py` cuando apareció su segundo consumidor.

No es sólo economía: dos definiciones de «este fichero ha cambiado» que
divergieran producirían el peor fallo posible de esta fase, que la tabla del
explorador y el log abierto discrepen (R14). Si mañana hay que añadir un campo a
la huella, se añade en un sitio y las dos capas lo heredan.

`dlv-core` NO RECORRE LA CARPETA (ADR-002)
===========================================
Este módulo no llama a `os.walk`, no hace `Path.stat()` y no abre ficheros. Quien
recorre el disco es la capa de comandos (`dlv-api`), que le pasa las entradas ya
leídas como `EntradaDeCarpeta`. Es la misma frontera que respeta
`cache.construir_clave`, y por el mismo motivo: así el planificador se puede
probar con carpetas que no existen —incluidas las que sería incómodo crear, como
una con 5 000 ficheros o una donde el reloj del sistema va hacia atrás— sin tocar
el disco ni una vez.

EL ÍNDICE ES UNA CACHÉ RECONSTRUIBLE, Y ESO CAMBIA CÓMO SE TRATA UN ERROR
==========================================================================
`proyecto.py` (F2-03) lanza `ErrorDeVersionDesconocida` cuando lee un fichero de
una versión que no entiende, porque ahí hay **trabajo del usuario** —sus
emparejamientos manuales— y perderlo en silencio sería inaceptable.

Aquí es al revés, y la diferencia es deliberada: el índice no contiene nada que
el usuario haya escrito, sólo resultados que se pueden volver a calcular.
Entonces un índice de una versión desconocida, truncado o con JSON inválido se
**descarta** y se recalcula, sin molestar a nadie. `leer_indice` devuelve `None`
en ese caso en vez de lanzar. Borrar el índice a mano nunca pierde datos: sólo
tiempo, y sólo una vez.

TRES COSAS QUE EL PLAN TIENE QUE HACER BIEN, Y LO QUE PASA SI NO
================================================================
1. **Los ficheros que ya no están se van de la tabla.** Es R15: sin esto, la
   tabla describe una carpeta que ya no existe y el usuario hace doble clic en un
   log borrado. Van en `a_descartar` y se pierden del índice nuevo.
2. **Un fichero reescrito con el mismo nombre se recalcula.** La ECU numera sus
   logs por sesión y reutiliza nombres; un índice que se fiara del nombre
   enseñaría el resumen del log anterior con el nombre del nuevo, que es el fallo
   más difícil de detectar de los tres, porque la fila parece correcta.
3. **El orden no cambia entre aperturas.** Las entradas se devuelven ordenadas
   por ruta, no por el orden en que el sistema de ficheros las enumeró. Sin eso,
   la misma carpeta sale con las filas en otro orden cada vez y la tabla no se
   puede leer.

Solo biblioteca estándar: ni Polars ni NumPy. El bucle es sobre FICHEROS de la
carpeta (cientos), no sobre muestras de un log, así que ADR-009 no lo alcanza —
lo que prohíbe es el bucle por muestra, y el resumen que sí las recorre (FE-02)
lo hace con columnas proyectadas.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from dlv_core.huella import ClaveInvalidacion, construir_clave, es_valida

__all__ = [
    "VERSION_ESQUEMA_INDICE",
    "EntradaDeCarpeta",
    "EntradaDeIndice",
    "Indice",
    "PlanDeIndexado",
    "aplicar_resumenes",
    "escribir_indice",
    "leer_indice",
    "planificar_indexado",
]

#: Versión del esquema del índice en disco. Se sube cuando cambia la forma de lo
#: que se guarda; un índice de otra versión se descarta y se recalcula (ver la
#: cabecera), así que subirla es seguro y no rompe nada del usuario.
VERSION_ESQUEMA_INDICE = "1"


@dataclass(slots=True, frozen=True)
class EntradaDeCarpeta:
    """Un fichero tal como lo ve el disco, ya leído por quien recorre la carpeta.

    Los tres campos son exactamente los que necesita la huella de `cache.py`.
    Quien construye esto (`dlv-api`) los saca de un `Path.stat()`; este módulo no
    los obtiene por su cuenta (ADR-002).
    """

    ruta: Path
    tamano_bytes: int
    mtime_ns: int


@dataclass(slots=True, frozen=True)
class EntradaDeIndice:
    """Una fila del índice: la huella del fichero y el resumen ya calculado.

    `resumen` es opaco para este módulo a propósito: lo produce y lo interpreta
    FE-02. Aquí solo se guarda y se devuelve, de modo que cambiar qué métricas
    trae el resumen no obliga a tocar el planificador ni el formato del índice.
    """

    clave: ClaveInvalidacion
    resumen: Mapping[str, Any]

    @property
    def ruta(self) -> Path:
        return self.clave.ruta


@dataclass(slots=True, frozen=True)
class Indice:
    """El índice de una carpeta: una entrada por log, ordenadas por ruta."""

    entradas: tuple[EntradaDeIndice, ...] = ()
    version_esquema: str = VERSION_ESQUEMA_INDICE

    @property
    def por_ruta(self) -> Mapping[Path, EntradaDeIndice]:
        return {e.ruta: e for e in self.entradas}


@dataclass(slots=True, frozen=True)
class PlanDeIndexado:
    """Qué hacer en esta apertura de la carpeta.

    Las tres listas son disjuntas y su unión cubre todo lo que había antes más
    todo lo que hay ahora: es la propiedad que impide que una entrada se quede
    ni en el limbo ni contada dos veces, y hay una prueba que la fija.
    """

    a_calcular: tuple[EntradaDeCarpeta, ...] = ()
    """Ficheros nuevos, o cuya huella ya no cuadra con la del índice."""

    reutilizables: tuple[EntradaDeIndice, ...] = ()
    """Ficheros cuya huella coincide: su resumen se muestra sin recalcular. Es lo
    que hace que la reapertura entre en el presupuesto de 500 ms."""

    a_descartar: tuple[EntradaDeIndice, ...] = ()
    """Estaban en el índice y ya no están en la carpeta. No se muestran (R15)."""

    @property
    def hay_trabajo(self) -> bool:
        return bool(self.a_calcular)

    @property
    def total_de_filas(self) -> int:
        """Cuántas filas tendrá la tabla cuando termine el escaneo.

        Se sabe ANTES de calcular nada, y por eso el escaneo incremental de
        E15.7 puede enseñar «37 de 200» desde la primera fila en vez de una
        barra de progreso que no sabe cuánto queda.
        """
        return len(self.a_calcular) + len(self.reutilizables)


def planificar_indexado(
    entradas: Iterable[EntradaDeCarpeta],
    indice: Indice | None,
    *,
    version_parser: str,
    version_descriptor_formato: str,
) -> PlanDeIndexado:
    """Compara la carpeta con el índice y reparte en calcular / reutilizar / descartar.

    `indice` es `None` la primera vez que se abre la carpeta, o cuando el índice
    en disco se descartó por ser de otra versión o estar corrupto. En los dos
    casos la respuesta correcta es la misma —todo a calcular— así que no se
    distinguen aquí.

    Las versiones del parser y del descriptor entran en la huella, no solo el
    tamaño y la fecha: si el parser cambia cómo interpreta una escala, el fichero
    no ha cambiado pero su resumen sí, y un índice que se fiara solo del `stat()`
    seguiría enseñando los números viejos. Es la misma razón por la que están en
    `cache.ClaveInvalidacion`.
    """
    almacenadas = indice.por_ruta if indice is not None else {}
    vistas: set[Path] = set()
    a_calcular: list[EntradaDeCarpeta] = []
    reutilizables: list[EntradaDeIndice] = []

    for entrada in entradas:
        vistas.add(entrada.ruta)
        clave = construir_clave(
            entrada.ruta,
            tamano_bytes=entrada.tamano_bytes,
            mtime_ns=entrada.mtime_ns,
            version_parser=version_parser,
            version_descriptor_formato=version_descriptor_formato,
        )
        previa = almacenadas.get(entrada.ruta)
        if previa is not None and es_valida(previa.clave, clave):
            reutilizables.append(previa)
        else:
            a_calcular.append(entrada)

    a_descartar = [e for ruta, e in almacenadas.items() if ruta not in vistas]

    return PlanDeIndexado(
        a_calcular=tuple(sorted(a_calcular, key=lambda e: str(e.ruta))),
        reutilizables=tuple(sorted(reutilizables, key=lambda e: str(e.ruta))),
        a_descartar=tuple(sorted(a_descartar, key=lambda e: str(e.ruta))),
    )


def aplicar_resumenes(
    plan: PlanDeIndexado,
    resumenes: Mapping[Path, Mapping[str, Any]],
    *,
    version_parser: str,
    version_descriptor_formato: str,
) -> Indice:
    """El índice nuevo: lo reutilizado más lo que FE-02 acabó de calcular.

    `resumenes` puede estar INCOMPLETO respecto a `plan.a_calcular`, y no es un
    error: el escaneo de E15.7 es cancelable, así que si el usuario cierra la
    carpeta a medias se guarda lo que se alcanzó a calcular y la próxima vez se
    sigue por donde quedó. Un fichero sin resumen simplemente no entra en el
    índice, y volverá a salir en `a_calcular` la próxima apertura.

    Lo que NO se hace es inventar un resumen vacío para completar el plan: una
    entrada con resumen vacío sería indistinguible de un log cuyo resumen salió
    de verdad sin datos, que es justo la confusión que R14 prohíbe.
    """
    entradas = list(plan.reutilizables)
    por_ruta = {e.ruta: e for e in plan.a_calcular}
    for ruta, resumen in resumenes.items():
        entrada = por_ruta.get(ruta)
        if entrada is None:
            continue  # un resumen de un fichero que no se pidió: se ignora
        entradas.append(
            EntradaDeIndice(
                clave=construir_clave(
                    entrada.ruta,
                    tamano_bytes=entrada.tamano_bytes,
                    mtime_ns=entrada.mtime_ns,
                    version_parser=version_parser,
                    version_descriptor_formato=version_descriptor_formato,
                ),
                resumen=dict(resumen),
            )
        )
    return Indice(entradas=tuple(sorted(entradas, key=lambda e: str(e.ruta))))


# --------------------------------------------------------------------------- #
# Serialización
# --------------------------------------------------------------------------- #
def _clave_a_json(c: ClaveInvalidacion) -> dict[str, Any]:
    return {
        "ruta": str(c.ruta),
        "tamano_bytes": c.tamano_bytes,
        "mtime_ns": c.mtime_ns,
        "version_parser": c.version_parser,
        "version_descriptor_formato": c.version_descriptor_formato,
        "version_esquema_cache": c.version_esquema_cache,
    }


def _clave_desde_json(d: Mapping[str, Any]) -> ClaveInvalidacion:
    return ClaveInvalidacion(
        ruta=Path(str(d["ruta"])),
        tamano_bytes=int(d["tamano_bytes"]),
        mtime_ns=int(d["mtime_ns"]),
        version_parser=str(d["version_parser"]),
        version_descriptor_formato=str(d["version_descriptor_formato"]),
        version_esquema_cache=str(d["version_esquema_cache"]),
    )


def escribir_indice(indice: Indice, destino: IO[bytes]) -> None:
    """Serializa el índice como JSON en un objeto de escritura ya abierto.

    Recibe el objeto y no una ruta (ADR-002). JSON y no Parquet a propósito:
    son cientos de entradas con unos pocos números cada una, así que el formato
    legible gana — un índice que se puede abrir con un editor cuando algo va mal
    vale más que unos kilobytes ahorrados.
    """
    documento = {
        "version_esquema": VERSION_ESQUEMA_INDICE,
        "entradas": [
            {"clave": _clave_a_json(e.clave), "resumen": dict(e.resumen)} for e in indice.entradas
        ],
    }
    destino.write(json.dumps(documento, ensure_ascii=False, indent=1).encode("utf-8"))


def leer_indice(fuente: IO[bytes]) -> Indice | None:
    """Lee el índice, o devuelve `None` si no se puede usar.

    `None` significa «hay que recalcular», y cubre los cuatro casos por igual:
    JSON inválido, fichero truncado, versión de esquema desconocida y un
    documento con la forma equivocada. No lanza en ninguno, porque el índice es
    una caché reconstruible y hacer fallar la apertura de una carpeta por un
    fichero de caché corrupto sería castigar al usuario por un problema que el
    programa puede arreglar solo (ver la cabecera).
    """
    try:
        documento = json.loads(fuente.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(documento, dict):
        return None
    if str(documento.get("version_esquema", "")) != VERSION_ESQUEMA_INDICE:
        return None

    brutas = documento.get("entradas")
    if not isinstance(brutas, list):
        return None
    entradas: list[EntradaDeIndice] = []
    for bruta in brutas:
        if not isinstance(bruta, dict):
            return None
        try:
            clave = _clave_desde_json(bruta["clave"])
        except (KeyError, TypeError, ValueError):
            return None
        resumen = bruta.get("resumen")
        if not isinstance(resumen, dict):
            return None
        entradas.append(EntradaDeIndice(clave=clave, resumen=resumen))

    return Indice(entradas=tuple(sorted(entradas, key=lambda e: str(e.ruta))))


# --------------------------------------------------------------------------- #
# Utilidad para quien recorre la carpeta
# --------------------------------------------------------------------------- #
#: Extensiones que el explorador considera candidatas a log. No es una lista de
#: formatos soportados —eso lo decide el importador al abrirlos— sino el filtro
#: que evita resumir un PDF o un `.dlvproj` que estén en la misma carpeta.
EXTENSIONES_CANDIDATAS: tuple[str, ...] = (".csv", ".txt", ".log")


@dataclass(slots=True, frozen=True)
class Descarte:
    """Un fichero de la carpeta que no se va a resumir, y por qué.

    Se devuelve en vez de omitirse en silencio: si el usuario apunta el
    explorador a la carpeta equivocada y la tabla sale vacía, la diferencia
    entre «no hay logs aquí» y «hay 40 ficheros y ninguno tiene extensión de log»
    es lo único que le dice qué hacer a continuación.
    """

    ruta: Path
    motivo: str


def separar_candidatos(
    rutas: Sequence[Path],
    *,
    extensiones: Sequence[str] = EXTENSIONES_CANDIDATAS,
) -> tuple[tuple[Path, ...], tuple[Descarte, ...]]:
    """Reparte las rutas de una carpeta en candidatas a log y descartadas.

    La comparación de extensión es insensible a mayúsculas porque Windows las
    escribe indistintamente y la misma carpeta copiada de un sistema a otro no
    puede dar tablas distintas.
    """
    permitidas = {e.lower() for e in extensiones}
    candidatas: list[Path] = []
    descartes: list[Descarte] = []
    for ruta in rutas:
        if ruta.suffix.lower() in permitidas:
            candidatas.append(ruta)
        else:
            descartes.append(
                Descarte(
                    ruta=ruta,
                    motivo=(
                        f"extensión {ruta.suffix or '(ninguna)'!r} no candidata a log; "
                        f"se esperaba una de {sorted(permitidas)}"
                    ),
                )
            )
    return tuple(sorted(candidatas, key=str)), tuple(sorted(descartes, key=lambda d: str(d.ruta)))
