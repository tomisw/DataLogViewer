"""Emparejamientos manuales del proyecto (`.dlvproj`), tarea F2-03.

`docs/07-formatos-y-csv-generico.md` §7.11 punto 4: «Emparejamiento manual del
usuario, que se guarda en el proyecto y tiene prioridad sobre todo lo
anterior.» `docs/03-arquitectura.md` §3.9 sitúa ese emparejamiento dentro de
`.dlvproj` («espacio de trabajo: logs, desfases, perfil activo, zoom,
marcadores, emparejamientos manuales»), JSON versionado.

QUÉ HACE ESTE MÓDULO Y QUÉ NO
=============================
`dlv_core.identidad` (F2-02) ya sabe qué es un `EmparejamientoManual` y cómo
aplicarlo (`emparejar(..., manuales=...)`); avisa de un canal repetido entre
dos emparejamientos, pero solo **después** de intentar aplicarlos, porque a
esa función no le corresponde decidir qué se guarda. Este módulo es la capa
de antes: la colección que vive en el proyecto, con la validación que permite
rechazar un emparejamiento manual en el momento en que el usuario todavía
puede corregirlo, no cuando ya está guardado en el `.dlvproj` y el aviso
aparece la próxima vez que se abre.

`EmparejamientosManuales.a_secuencia()` es la forma exacta que espera
`identidad.emparejar(..., manuales=...)`: no hay conversión que hacer, igual
que `PresetUsuario.a_mapeo()` (F1-18) para `preferencias_perfil`. Si aquí
hiciera falta traducir algo, sería señal de que el modelo está mal elegido.

POR QUÉ ES INMUTABLE
=====================
El resto de la capa de identidad (`CanalDeLog`, `EmparejamientoManual`,
`GrupoDeCanales`, `Emparejamiento`) son `dataclass(frozen=True)`. Esta
colección sigue el mismo patrón a propósito: `agregar()` y `quitar()`
devuelven una colección nueva en vez de mutar la existente, así que una
referencia ya entregada a la interfaz (p. ej. para dibujar la lista actual)
no cambia por debajo de los pies si el usuario deshace la operación.

VALIDACIÓN EAGER, NO DIFERIDA
==============================
A diferencia de `PresetUsuario` (que no puede validar sin un `Catalogo` a
mano y por eso separa construcción de `validar()`), la única validación que
le corresponde a esta colección -- nombres únicos y que un canal no esté en
dos emparejamientos manuales a la vez -- no necesita nada externo. Por eso se
hace en el momento: en el constructor y en `agregar()`, no en un paso aparte
que alguien podría olvidar llamar antes de guardar.

VERSIÓN DE ESQUEMA
===================
`.dlvproj` es JSON versionado (§3.9). El campo `version_esquema` de
`a_dict()`/`a_json()` es la versión de ESTE bloque (los emparejamientos
manuales), no la del fichero `.dlvproj` completo, que es responsabilidad de
quien componga las demás secciones (logs, desfases, perfil activo...). Una
versión desconocida lanza `ErrorDeVersionDesconocida` en vez de leerse a
medias: un campo renombrado o movido en una versión futura del esquema, leído
con las claves de hoy, produciría un emparejamiento manual que parece válido
y no lo es -- justo el error silencioso que la puerta G1 de docs/08 no puede
dejar pasar.

ADR-002 / ADR-009
=================
Ni este módulo ni sus pruebas tocan el sistema de ficheros: solo `dict` y
cadenas JSON en memoria (ADR-002). No hay muestras que recorrer -- unas
decenas de emparejamientos por proyecto como mucho -- así que ADR-009 no
aplica en la práctica, pero tampoco hay ningún bucle sobre series de datos
aquí.

Solo biblioteca estándar.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from dlv_core.identidad import EmparejamientoManual

__all__ = [
    "VERSION_ESQUEMA_EMPAREJAMIENTOS",
    "EmparejamientosManuales",
    "ErrorDeProyecto",
    "ErrorDeVersionDesconocida",
]


VERSION_ESQUEMA_EMPAREJAMIENTOS = 1
"""Versión del bloque `{"version_esquema": ..., "emparejamientos": [...]}`.

Sube este número solo cuando cambie la FORMA del bloque (una clave que se
renombra, un campo nuevo obligatorio). Un `EmparejamientoManual` nuevo con
los mismos campos de siempre no lo necesita."""


class ErrorDeProyecto(ValueError):
    """Un emparejamiento manual del proyecto que no se puede guardar o leer sin
    que el usuario lo corrija primero: nombre repetido, canal en dos
    emparejamientos a la vez, o un bloque de `.dlvproj` incompleto o mal
    formado."""


class ErrorDeVersionDesconocida(ErrorDeProyecto):
    """El bloque de emparejamientos manuales declara una versión de esquema
    que este `dlv-core` no sabe leer.

    Deliberadamente no se intenta "leer lo que se pueda": un `.dlvproj` de una
    versión futura con una forma distinta produciría, leído con las claves de
    hoy, un emparejamiento manual que parece correcto y no lo es. Mejor un
    error claro que abrir el proyecto en una versión de DataLogViewer que sí
    lo entienda.
    """


def _validar_sin_duplicados(emparejamientos: Sequence[EmparejamientoManual]) -> None:
    """Nombres únicos y ningún canal repetido entre emparejamientos distintos.

    `identidad.emparejar` ya avisa de un canal que aparece en dos
    emparejamientos manuales (se queda con el primero y avisa del segundo),
    pero eso pasa al aplicar el emparejamiento, no al guardarlo. Aquí se
    rechaza directamente, que es cuando el usuario todavía está mirando el
    diálogo y puede corregirlo en el sitio.
    """
    nombres_vistos: set[str] = set()
    canales_vistos: dict[tuple[str, str], str] = {}
    for emparejamiento in emparejamientos:
        if emparejamiento.nombre in nombres_vistos:
            raise ErrorDeProyecto(
                f"ya hay un emparejamiento manual llamado '{emparejamiento.nombre}' en este "
                "proyecto: cada emparejamiento manual necesita un nombre único. Renómbralo o "
                "quita el anterior antes de guardar"
            )
        nombres_vistos.add(emparejamiento.nombre)

        for id_segmento, id_canal in emparejamiento.miembros.items():
            clave = (id_segmento, id_canal)
            anterior = canales_vistos.get(clave)
            if anterior is not None:
                raise ErrorDeProyecto(
                    f"el canal '{id_canal}' del segmento '{id_segmento}' ya está en el "
                    f"emparejamiento manual '{anterior}': no puede estar también en "
                    f"'{emparejamiento.nombre}'. Un canal pertenece a un único emparejamiento "
                    "manual a la vez; quita uno de los dos o edítalo para que no se solapen"
                )
            canales_vistos[clave] = emparejamiento.nombre


@dataclass(slots=True, frozen=True)
class EmparejamientosManuales:
    """La colección de `EmparejamientoManual` de un proyecto (`.dlvproj`).

    Validada en todo momento: no existe un estado intermedio de esta
    colección con nombres repetidos o con un canal en dos emparejamientos a
    la vez (ver `_validar_sin_duplicados`). Eso es justo lo que permite que
    `a_secuencia()` se pueda pasar a `identidad.emparejar(..., manuales=...)`
    sin que esa función tenga que repetir la comprobación por su cuenta --
    aunque, por si llega una instancia mal construida por otro camino, sigue
    avisando ella también.
    """

    emparejamientos: tuple[EmparejamientoManual, ...] = ()

    def __post_init__(self) -> None:
        _validar_sin_duplicados(self.emparejamientos)

    # --------------------------------------------------------------------- #
    # Consulta
    # --------------------------------------------------------------------- #
    def __len__(self) -> int:
        return len(self.emparejamientos)

    def __iter__(self) -> Iterator[EmparejamientoManual]:
        return iter(self.emparejamientos)

    @property
    def nombres(self) -> tuple[str, ...]:
        return tuple(e.nombre for e in self.emparejamientos)

    def existe(self, nombre: str) -> bool:
        return any(e.nombre == nombre for e in self.emparejamientos)

    def obtener(self, nombre: str) -> EmparejamientoManual:
        for emparejamiento in self.emparejamientos:
            if emparejamiento.nombre == nombre:
                return emparejamiento
        raise ErrorDeProyecto(
            f"no hay ningún emparejamiento manual llamado '{nombre}' en este proyecto"
        )

    # --------------------------------------------------------------------- #
    # Modificación (funcional: devuelve una colección nueva)
    # --------------------------------------------------------------------- #
    def agregar(self, nuevo: EmparejamientoManual) -> EmparejamientosManuales:
        """Colección con `nuevo` añadido, o lanza `ErrorDeProyecto` sin tocar
        `self` si contradice un invariante (nombre repetido, canal ya en otro
        emparejamiento manual). Es la comprobación previa al guardado que pide
        la tarea: se hace aquí, antes de serializar nada."""
        return EmparejamientosManuales((*self.emparejamientos, nuevo))

    def quitar(self, nombre: str) -> EmparejamientosManuales:
        """Colección sin el emparejamiento `nombre`. Lanza `ErrorDeProyecto` si
        no existe, para no dejar pasar en silencio un nombre mal escrito."""
        if not self.existe(nombre):
            raise ErrorDeProyecto(
                f"no hay ningún emparejamiento manual llamado '{nombre}' que quitar"
            )
        return EmparejamientosManuales(tuple(e for e in self.emparejamientos if e.nombre != nombre))

    # --------------------------------------------------------------------- #
    # Integración con `identidad.emparejar`
    # --------------------------------------------------------------------- #
    def a_secuencia(self) -> Sequence[EmparejamientoManual]:
        """La forma exacta que espera `identidad.emparejar(..., manuales=...)`.

        Sin conversión: este campo YA ES esa secuencia. El método existe para
        que quien lo llama no tenga que saber que `emparejamientos` es
        públicamente el mismo campo (mismo motivo que `PresetUsuario.a_mapeo()`).
        """
        return self.emparejamientos

    # --------------------------------------------------------------------- #
    # Serialización
    # --------------------------------------------------------------------- #
    def a_dict(self) -> dict[str, Any]:
        """Serializa a un `dict` plano, listo para JSON o para componerse dentro
        del `.dlvproj` completo. Orden estable por nombre: dos guardados
        seguidos sin cambios producen el mismo texto."""
        return {
            "version_esquema": VERSION_ESQUEMA_EMPAREJAMIENTOS,
            "emparejamientos": [
                {"nombre": e.nombre, "miembros": dict(e.miembros)}
                for e in sorted(self.emparejamientos, key=lambda e: e.nombre)
            ],
        }

    def a_json(self) -> str:
        """Serializa a JSON. `desde_json` es su inversa exacta."""
        return json.dumps(self.a_dict(), ensure_ascii=False, sort_keys=True)

    @staticmethod
    def desde_dict(bruto: Mapping[str, Any]) -> EmparejamientosManuales:
        """Reconstruye desde la forma de `a_dict()`.

        Comprueba `version_esquema` antes de mirar nada más: una versión
        desconocida lanza `ErrorDeVersionDesconocida` sin intentar interpretar
        el resto del bloque (ver la nota de cabecera del módulo).
        """
        try:
            version = bruto["version_esquema"]
        except KeyError as exc:
            raise ErrorDeProyecto(
                f"bloque de emparejamientos manuales incompleto: falta la clave {exc}"
            ) from None
        if version != VERSION_ESQUEMA_EMPAREJAMIENTOS:
            raise ErrorDeVersionDesconocida(
                f"el bloque de emparejamientos manuales declara la versión de esquema "
                f"{version!r}, y este dlv-core solo sabe leer la versión "
                f"{VERSION_ESQUEMA_EMPAREJAMIENTOS}. Abre este proyecto con una versión de "
                "DataLogViewer que reconozca esa versión de esquema"
            )

        try:
            brutos = bruto["emparejamientos"]
        except KeyError as exc:
            raise ErrorDeProyecto(
                f"bloque de emparejamientos manuales incompleto: falta la clave {exc}"
            ) from None
        if not isinstance(brutos, Sequence) or isinstance(brutos, (str, bytes)):
            raise ErrorDeProyecto(
                "bloque de emparejamientos manuales: 'emparejamientos' debe ser una lista"
            )

        emparejamientos: list[EmparejamientoManual] = []
        for item in brutos:
            if not isinstance(item, Mapping):
                raise ErrorDeProyecto(
                    "bloque de emparejamientos manuales: cada emparejamiento debe ser un "
                    "objeto con 'nombre' y 'miembros'"
                )
            try:
                nombre = item["nombre"]
                miembros_brutos = item["miembros"]
            except KeyError as exc:
                raise ErrorDeProyecto(
                    f"un emparejamiento manual del proyecto no tiene la clave {exc}"
                ) from None
            if not isinstance(miembros_brutos, Mapping):
                raise ErrorDeProyecto(
                    f"el emparejamiento manual '{nombre}': 'miembros' debe ser un mapeo "
                    "id_segmento -> id_canal"
                )
            miembros = {str(k): str(v) for k, v in miembros_brutos.items()}
            emparejamientos.append(EmparejamientoManual(nombre=str(nombre), miembros=miembros))

        return EmparejamientosManuales(tuple(emparejamientos))

    @staticmethod
    def desde_json(texto: str) -> EmparejamientosManuales:
        """Reconstruye desde la forma de `a_json()`."""
        try:
            bruto = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise ErrorDeProyecto(
                f"bloque de emparejamientos manuales: JSON inválido: {exc}"
            ) from None
        if not isinstance(bruto, Mapping):
            raise ErrorDeProyecto(
                "bloque de emparejamientos manuales: la raíz del JSON debe ser un objeto"
            )
        return EmparejamientosManuales.desde_dict(bruto)
