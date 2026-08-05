"""Informe de importación acumulativo, no bloqueante (tarea F1-12).

`docs/03-arquitectura.md` §3.4 lo pone como el paso 9, el último de la ruta de
ingesta: "Informe de importación — avisos, sin bloquear". Y `docs/02` §2.5
(regla E1.7) es la filosofía que este módulo hace visible al usuario: "se
avisa y se sigue siempre que se puedan producir datos utilizables". Cada
etapa de la ruta ya decide por su cuenta cuándo avisar y con qué `Aviso`
(`formatos/haltech.py` en la cabecera, `formatos/limpieza.py` en el cuerpo,
`reloj.py` en la reconciliación de tiempo...); lo que faltaba era un sitio
donde juntarlos para enseñarlos de una vez al final de la carga, sin que se
repita 300 veces el mismo mensaje si afecta a 300 canales.

Por qué no vive en `informes.py`
=================================
`informes.py` define `Aviso` a propósito sin conocer ningún formato ni ningún
otro módulo de `dlv-core` -- es justo lo que le permite que `reloj.py` (que no
debe depender de un formato concreto) y `formatos/haltech.py` compartan el
mismo tipo sin que ninguno importe al otro. `aviso_de_retrocesos_anomalos`
(más abajo) necesita conocer la forma de `Desenrollado`, que es un concepto de
`reloj.py`; meter eso en `informes.py` obligaría a `informes.py` a importar
`reloj.py`, y `reloj.py` ya importa `informes.py` -- un ciclo. Este módulo, en
cambio, puede depender de `informes.py` y (solo para tipos) de `reloj.py` sin
que ninguno de los dos necesite saber que existe.

No bloqueante, en serio
========================
`InformeImportacion.agregar` no lanza. Los avisos ya existentes son
`dataclass(frozen=True)` con campos `str`/`int | None`, así que el acceso a
sus atributos no puede fallar por sí solo; lo único "raro" que puede pasar es
semántico (un código vacío) o que alguien pase, por descuido y a pesar del
tipado, algo que no es un `Aviso`. Lo primero se normaliza a
`CODIGO_SIN_ESPECIFICAR` en vez de descartarse -- perder el mensaje sería
justo lo contrario de "avisa y sigue". Lo segundo se cuenta aparte
(`elementos_descartados`) y se ignora: este módulo no es quien debe inventar
una excepción nueva que el dominio no tiene.

Severidad
=========
`Aviso` no lleva severidad -- añadírsela habría que hacerlo en `informes.py`,
y de nada serviría: los productores ya existentes (`haltech.py`, `reloj.py`,
`limpieza.py`) no se pueden tocar en esta tarea, así que seguirían creando
`Aviso` sin ese campo y quedaría siempre en su valor por omisión. En su lugar,
la severidad es una función de `codigo` (`severidad_de_codigo`), igual que
`detectores.Incidencia.severidad` ya es un `str` simple (`"informativa"`,
etc., ver `huecos.py`) y no un enum: se sigue esa misma convención en vez de
inventar un tipo nuevo. Un código que este módulo no reconoce (uno nuevo que
se añada mañana en otro sitio) se clasifica `SEVERIDAD_ADVERTENCIA` por
omisión: mejor visible de más que oculto de menos.

Solo biblioteca estándar.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dlv_core.informes import Aviso

if TYPE_CHECKING:
    # Solo para el tipo del parámetro de `aviso_de_retrocesos_anomalos`: ver la
    # nota "Por qué no vive en informes.py" más arriba. En tiempo de ejecución
    # esta función no necesita importar `reloj.py`, porque solo lee un atributo
    # entero (duck typing), igual que `huecos.py` hace con `ChannelSeries`.
    from dlv_core.reloj import Desenrollado

__all__ = [
    "CODIGO_SIN_ESPECIFICAR",
    "SEVERIDAD_ADVERTENCIA",
    "SEVERIDAD_INFORMATIVA",
    "GrupoDeAvisos",
    "InformeImportacion",
    "aviso_de_retrocesos_anomalos",
    "severidad_de_codigo",
]

CODIGO_SIN_ESPECIFICAR = "aviso_sin_codigo"
"""Código de repuesto para un `Aviso` cuyo `codigo` llega vacío. No se
descarta el aviso -- el mensaje puede seguir siendo útil -- solo se agrupa
aparte en vez de bajo `""`, que sería un código fantasma en el resumen."""

SEVERIDAD_INFORMATIVA = "informativa"
SEVERIDAD_ADVERTENCIA = "advertencia"
"""Mismos dos niveles y misma forma (`str`) que `detectores.Incidencia.severidad`
(`huecos.py`), para no introducir una segunda taxonomía en el paquete."""

#: Clasificación de los códigos que ya existen en el repo (grep en
#: `formatos/haltech.py`, `formatos/limpieza.py` y `reloj.py`). El criterio:
#: informativa cuando el dato sigue siendo utilizable y la degradación es
#: conocida y esperada (p. ej. época de fábrica, DisplayMaxMin ignorada);
#: advertencia cuando algo se pierde, queda ambiguo, o exige intervención del
#: usuario (fila descartada, IDs duplicados, reloj no fiable u sin orden).
_SEVERIDAD_POR_CODIGO: dict[str, str] = {
    # formatos/haltech.py (F1-01)
    "nombre_duplicado": SEVERIDAD_INFORMATIVA,
    "id_duplicado": SEVERIDAD_ADVERTENCIA,
    "tipo_desconocido": SEVERIDAD_ADVERTENCIA,
    "escala_sin_confirmar": SEVERIDAD_ADVERTENCIA,
    "displaymaxmin_invalida": SEVERIDAD_INFORMATIVA,
    # formatos/limpieza.py (F1-03)
    "fila_malformada": SEVERIDAD_ADVERTENCIA,
    # reloj.py (F1-04)
    "reloj_sin_metadato": SEVERIDAD_INFORMATIVA,
    "reloj_metadato_ilegible": SEVERIDAD_INFORMATIVA,
    "epoca_ficticia": SEVERIDAD_INFORMATIVA,
    "reloj_sin_primera_fila": SEVERIDAD_INFORMATIVA,
    "reloj_no_fiable": SEVERIDAD_ADVERTENCIA,
    "reloj_sin_orden": SEVERIDAD_ADVERTENCIA,
    "cabecera_antes_de_medianoche": SEVERIDAD_INFORMATIVA,
    "descarga_anterior_al_log": SEVERIDAD_INFORMATIVA,
    # Este módulo (F1-12), ver `aviso_de_retrocesos_anomalos`.
    "retroceso_anomalo": SEVERIDAD_ADVERTENCIA,
    CODIGO_SIN_ESPECIFICAR: SEVERIDAD_ADVERTENCIA,
}


def severidad_de_codigo(codigo: str) -> str:
    """`SEVERIDAD_INFORMATIVA` o `SEVERIDAD_ADVERTENCIA` para `codigo`.

    Un código no reconocido (de un productor futuro que este módulo no conoce
    todavía) se clasifica como advertencia: mejor visible de más que oculto de
    menos, y evita que este módulo tenga que cambiar cada vez que otra parte
    del código añade un `Aviso` nuevo.
    """
    return _SEVERIDAD_POR_CODIGO.get(codigo, SEVERIDAD_ADVERTENCIA)


def aviso_de_retrocesos_anomalos(desenrollado: Desenrollado) -> Aviso | None:
    """Envuelve `Desenrollado.retrocesos_anomalos` (F1-04, `reloj.py`) en un
    `Aviso`, o `None` si no hubo ninguno.

    `Desenrollado` no produce `Aviso` directamente -- `retrocesos_anomalos` es
    un entero -- pero su propio docstring en `reloj.py` dice que "se cuentan
    para el informe de importación", así que es precisamente este informe
    quien debe convertir el conteo en algo que `InformeImportacion.agregar`
    pueda aceptar. `cruces_de_medianoche` queda deliberadamente fuera: un
    cruce de medianoche genuino se desenrolla y se resuelve, no es una
    anomalía que el usuario deba revisar; solo lo que "no se corrige" (los
    retrocesos que no llegan a ser cruce) encaja en la forma `Aviso`.
    """
    if desenrollado.retrocesos_anomalos <= 0:
        return None
    n = desenrollado.retrocesos_anomalos
    return Aviso(
        "retroceso_anomalo",
        f"{n} marca(s) de tiempo retroceden sin llegar a ser un cruce de "
        "medianoche; no se corrigen (docs/01 §1.13)",
    )


@dataclass(slots=True, frozen=True)
class GrupoDeAvisos:
    """Todos los avisos con el mismo `codigo`, para el resumen del informe."""

    codigo: str
    severidad: str
    avisos: tuple[Aviso, ...]

    @property
    def cantidad(self) -> int:
        return len(self.avisos)


@dataclass(slots=True)
class InformeImportacion:
    """Acumulador del informe de importación (F1-12).

    "Acumulativo" es literal: no se conoce de antemano cuántas etapas de la
    ruta de ingesta van a aportar avisos ni en qué orden llegan, así que la
    única forma de construirlo es dejar que cada etapa llame a `agregar` con
    lo que tenga en el momento en que lo tenga. Cualquier iterable de `Aviso`
    sirve sin adaptador: `Cabecera.avisos` (`list[Aviso]`),
    `Reconciliacion.avisos` (`tuple[Aviso, ...]`) y lo que devuelve
    `detectar_filas_malformadas` (`list[Aviso]`) se pasan tal cual.

    "No bloqueante" es igual de literal: nada en esta clase lanza una
    excepción por construir el informe. Ver el docstring del módulo.
    """

    _avisos: list[Aviso] = field(default_factory=list)
    _elementos_descartados: int = 0

    def agregar(self, avisos: Iterable[Aviso]) -> None:
        """Añade los avisos de una etapa. Se puede llamar tantas veces como
        etapas produzcan avisos, en cualquier orden; el orden de llegada se
        conserva en `todos()`."""
        for aviso in avisos:
            self._agregar_uno(aviso)

    def _agregar_uno(self, aviso: Aviso) -> None:
        try:
            codigo = aviso.codigo
            mensaje = aviso.mensaje
            linea = aviso.linea
        except AttributeError:
            # No es un `Aviso` (ni nada con su forma) a pesar del tipado
            # estático: se cuenta y se ignora, no se inventa una excepción
            # que el dominio no tiene.
            self._elementos_descartados += 1
            return

        if not isinstance(codigo, str) or not isinstance(mensaje, str):
            self._elementos_descartados += 1
            return

        codigo_normalizado = codigo.strip() or CODIGO_SIN_ESPECIFICAR
        if codigo_normalizado != codigo:
            # Un código en blanco no se descarta -- el mensaje puede seguir
            # siendo útil -- se reetiqueta para que el resumen no agrupe bajo
            # un código fantasma "".
            aviso = Aviso(codigo_normalizado, mensaje, linea)
        self._avisos.append(aviso)

    @property
    def vacio(self) -> bool:
        return not self._avisos

    @property
    def total(self) -> int:
        return len(self._avisos)

    @property
    def elementos_descartados(self) -> int:
        """Cuántos elementos pasados a `agregar` no tenían forma de `Aviso` y
        se ignoraron. Debería ser 0 en cualquier uso normal; existe para que
        un test o un log de diagnóstico lo pueda comprobar sin que el propio
        informe deje de construirse."""
        return self._elementos_descartados

    def todos(self) -> tuple[Aviso, ...]:
        """Todos los avisos, en el orden en que llegaron a `agregar`."""
        return tuple(self._avisos)

    def por_codigo(self) -> dict[str, tuple[Aviso, ...]]:
        """Avisos agrupados por `codigo`, en el orden de primera aparición de
        cada código."""
        agrupado: dict[str, list[Aviso]] = {}
        for aviso in self._avisos:
            agrupado.setdefault(aviso.codigo, []).append(aviso)
        return {codigo: tuple(lista) for codigo, lista in agrupado.items()}

    def resumen(self) -> tuple[GrupoDeAvisos, ...]:
        """Un `GrupoDeAvisos` por código, para no repetir 300 veces el mismo
        mensaje si afecta a 300 canales: "3 avisos de tipo X, 1 de tipo Y".

        Ordenado por cantidad descendente y, a igualdad, por código
        alfabético: lo que más se repite (y probablemente más quiere ver el
        usuario primero) encabeza la lista.
        """
        grupos = [
            GrupoDeAvisos(codigo=codigo, severidad=severidad_de_codigo(codigo), avisos=avisos)
            for codigo, avisos in self.por_codigo().items()
        ]
        grupos.sort(key=lambda g: (-g.cantidad, g.codigo))
        return tuple(grupos)

    def a_lineas(self) -> list[str]:
        """Representación textual simple: resumen por código y detalle
        completo, lista para que una consola, un log o (más adelante) un
        informe HTML la muestren sin que este módulo tenga que saber nada de
        HTML ni de ficheros (ADR-002: `dlv-core` no toca el sistema de
        ficheros por su cuenta)."""
        if self.vacio:
            return ["Sin avisos: la importación no encontró ninguna anomalía."]

        lineas = [f"{self.total} aviso(s) en {len(self.por_codigo())} categoría(s):"]
        for grupo in self.resumen():
            lineas.append(f"  - {grupo.cantidad} de tipo '{grupo.codigo}' [{grupo.severidad}]")
        lineas.append("")
        lineas.append("Detalle:")
        for aviso in self._avisos:
            lineas.append(f"  {aviso}")
        return lineas

    def a_dict(self) -> dict[str, Any]:
        """Estructura serializable (JSON-friendly) del informe completo, para
        que un consumidor futuro (informe HTML de E8.1, la API de `dlv-api`)
        lo muestre sin depender de los tipos de `dlv-core`."""
        return {
            "total": self.total,
            "vacio": self.vacio,
            "elementos_descartados": self.elementos_descartados,
            "resumen": [
                {
                    "codigo": grupo.codigo,
                    "cantidad": grupo.cantidad,
                    "severidad": grupo.severidad,
                }
                for grupo in self.resumen()
            ],
            "avisos": [
                {"codigo": aviso.codigo, "mensaje": aviso.mensaje, "linea": aviso.linea}
                for aviso in self._avisos
            ],
        }
