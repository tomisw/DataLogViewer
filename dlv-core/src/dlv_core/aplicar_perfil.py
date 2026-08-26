"""Aplicación de un `Perfil` (F3-01) contra los canales de un log ya abierto
(tarea F3-02).

`docs/02-alcance-y-plan.md` E4.3: «Aplicación de perfil por rol, con reserva a
`ID` nativo y degradación elegante ocultando los paneles sin datos.» Este
módulo decide, para un perfil y un log concretos, QUÉ panel se muestra, CON
QUÉ elementos y CUÁLES no se pueden montar. No decide nada sobre límites de
alerta ni detectores: `perfil.py` ya deja escrito que esa parte es de
`dlv_core.activacion_detectores` (F3-08) y de quien dibuja los topes (F3-10);
aquí solo hay paneles y elementos.

TRES DECISIONES
================

1. LA RESERVA A `id_nativo` ES UNA COINCIDENCIA EXACTA, NUNCA UN PARECIDO
--------------------------------------------------------------------------
`perfil.py` (decisión 1) hace `rol` e `id_nativo` mutuamente excluyentes
precisamente para que un ID nativo no se cuele como identidad "normal". Aquí
se respeta esa frontera de la única forma que la mantiene: un elemento con
`id_nativo` se busca con `==` contra los identificadores nativos que trae el
log, nunca con `roles.asignar_rol` ni con `difflib`. Si el log es de otro
formato, sus canales no traerán ese identificador exacto —Haltech NSP escribe
`Channel` como texto, y ningún otro formato tiene motivo para coincidir letra
por letra con "Fuel MAP Correction" o "Trigger Tooth Count"— así que el
elemento queda sin montar SOLO, sin que este módulo tenga que saber qué
formato declaró cada `id_nativo`: la propia ausencia de un identificador
idéntico ya es la reserva. Buscarle un parecido sería reintroducir por la
puerta de atrás justo lo que la reserva existe para evitar (`perfil.py`
decisión 1, docs/07 §7.12).

2. LA CONFIANZA VIAJA ENTERA, NUNCA APLANADA A UN BOOLEANO
--------------------------------------------------------------------------
`roles.asignar_rol` no dice solo "sí" o "no": dice `EXACTA`, `INDEXADA` o
`DIFUSA` (docs/07 §7.15). Un rol `DIFUSA` no puede activar un detector crítico
sin que el usuario lo confirme, y esa decisión la toma `activacion_detectores`
(F3-08) — pero solo puede tomarla si le llega la `Confianza` real. Por eso
`EstadoElemento.asignacion` guarda la `Asignacion` completa (no un
`disponible: bool` a secas): un canal montado por un rol `DIFUSA` SÍ se dibuja
—ocultar un panel entero por una confianza baja sería la política de F3-08
aplicada donde no toca, y volvería a un perfil "todo o nada" que la decisión 2
de `perfil.py` rechaza explícitamente— pero quien decide si UN DETECTOR sobre
ese rol puede sonar en rojo tiene, aguas abajo, con qué decidirlo.

3. UN PANEL SIN SUS ROLES REQUERIDOS SE OCULTA, Y SE PUEDE DECIR POR QUÉ
--------------------------------------------------------------------------
`Panel.roles_requeridos` (F3-01) ya declara qué roles bloquean el panel si
faltan. `EstadoPanel.visible` es justo esa comprobación, pero `visible` a
secas es la misma trampa "todo o nada" a otra escala: E4.5 habla de perfiles
—y por extensión de paneles— parcialmente cubiertos, con un número
("7 de 9 roles disponibles"), no con un semáforo. `EstadoPanel.cobertura`
da ese mismo par `(disponibles, total)` a nivel de panel, y `motivo_oculto`
lo convierte en una frase que nombra los roles que faltan — el mismo criterio
de `activacion_detectores._motivo`: nombrar el rol es lo que convierte el
aviso en algo que se puede arreglar. La cobertura del PERFIL entero (la cifra
literal de E4.5) es autosugerencia entre varios perfiles y es F3-04, no esta
tarea (docs/05: F3-04 depende de F3-02); `roles_disponibles` se expone aquí
como la pieza que F3-04 necesita sin repetir la búsqueda.

ADR-002 / ADR-009
==================
Sin E/S: recibe los canales ya resueltos, no abre ningún fichero ni catálogo.
Recorre paneles y canales (unas centenas como mucho, nunca muestras), así que
ADR-009 no exige vectorizar nada aquí — inventar un bucle vectorizado sobre
una docena de paneles sería peor, no mejor.

Solo biblioteca estándar y `dlv_core.perfil` / `dlv_core.roles`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dlv_core.perfil import ElementoDePanel, Panel, Perfil
from dlv_core.roles import Asignacion, Confianza

__all__ = [
    "CanalDeLogResuelto",
    "ErrorDeAplicacion",
    "EstadoElemento",
    "EstadoPanel",
    "aplicar_perfil",
    "roles_disponibles",
]

# El orden de declaración de `Confianza` (roles.py) ES la prioridad: EXACTA
# antes que INDEXADA antes que DIFUSA. Se usa para desempatar el caso raro de
# dos canales del mismo log resolviendo al mismo (rol, índice): ver
# `_indexar_asignaciones`.
_PRIORIDAD_CONFIANZA = {c: i for i, c in enumerate(Confianza)}


class ErrorDeAplicacion(ValueError):
    """Un canal resuelto que no se puede usar sin que alguien lo corrija."""


@dataclass(slots=True, frozen=True)
class CanalDeLogResuelto:
    """Un canal del log ya abierto, tal como lo necesita `aplicar_perfil`.

    Deliberadamente más simple que `identidad.CanalDeLog` (F2-02): ese módulo
    empareja canales ENTRE logs abiertos a la vez y por eso necesita
    `id_segmento`/`id_canal`/`etiqueta`; aquí solo hace falta decidir, dentro
    de UN log, qué elementos de panel se pueden montar. Y deliberadamente NO
    reutiliza `identidad.CanalDeLog` tal cual: ese tipo ya aplana la
    confianza a `requiere_confirmacion: bool`, que es justo la pérdida de
    matiz que la decisión 2 de este módulo evita.
    """

    id_nativo: str | None
    """El identificador nativo del canal, TAL CUAL lo declara su formato de
    origen — para Haltech NSP, el texto exacto de `Channel` (docs/01 §1.3
    dice que la identidad "de verdad" del formato es el `ID` numérico, pero
    aquí no hace falta esa identidad para emparejar logs entre sí: solo hace
    falta poder comparar, letra por letra, contra lo que un `.dlvprofile`
    escribió en `id_nativo` — y `docs/04` §4.2 lo escribe como texto). No
    normalizado: la reserva de la decisión 1 es una coincidencia EXACTA."""

    asignacion: Asignacion | None = None
    """Lo que `roles.asignar_rol` decidió para este canal, o `None` si no se
    le pudo asignar ningún rol. Un canal puede tener las dos cosas a la vez
    (un id_nativo Y un rol): la exclusión mutua es de `ElementoDePanel`, no
    del canal — un mismo canal de Haltech puede alimentar un elemento por rol
    en un panel y un elemento por id_nativo en otro."""

    def __post_init__(self) -> None:
        if self.id_nativo is not None and not self.id_nativo.strip():
            raise ErrorDeAplicacion(
                "`id_nativo` no puede ser una cadena vacía: usa `None` para "
                "«este canal no tiene identificador nativo»"
            )


def _indexar_asignaciones(
    canales: Sequence[CanalDeLogResuelto],
) -> dict[tuple[str, int | None], Asignacion]:
    """`(rol, índice) -> Asignacion`, quedándose con la más confiable si dos
    canales del mismo log resolvieran al mismo par.

    En un log bien formado no debería pasar —cada nombre de canal es único y
    `asignar_rol` es una función, no una relación—, pero un catálogo de roles
    mal escrito sí podría hacer que dos nombres distintos caigan en el mismo
    (rol, índice). Elegir por confianza en vez de por orden de llegada evita
    que ese defecto de datos se manifieste como "qué canal gana" dependiendo
    del orden en que el llamador construyó la lista.
    """
    por_clave: dict[tuple[str, int | None], Asignacion] = {}
    for canal in canales:
        asignacion = canal.asignacion
        if asignacion is None:
            continue
        clave = (asignacion.rol, asignacion.indice)
        actual = por_clave.get(clave)
        if actual is None or (
            _PRIORIDAD_CONFIANZA[asignacion.confianza] < _PRIORIDAD_CONFIANZA[actual.confianza]
        ):
            por_clave[clave] = asignacion
    return por_clave


def roles_disponibles(canales: Sequence[CanalDeLogResuelto]) -> frozenset[str]:
    """Los roles que el log trae resueltos, sin importar su confianza.

    Expuesto para que F3-04 (autosugerencia por cobertura, E4.5) no tenga que
    recorrer los canales otra vez: cruzar esto con `Perfil.roles_referenciados`
    es exactamente la cifra «7 de 9 roles disponibles».
    """
    return frozenset(a.rol for c in canales if (a := c.asignacion) is not None)


@dataclass(slots=True, frozen=True)
class EstadoElemento:
    """Si UN elemento de panel se pudo montar contra el log, y con qué."""

    elemento: ElementoDePanel
    disponible: bool
    asignacion: Asignacion | None = None
    """La asignación que resolvió este elemento -- con su `Confianza` entera
    (decisión 2). `None` si el elemento no se pudo montar, o si es un
    elemento por `id_nativo`: ese camino no pasa por el sistema de roles y no
    tiene una confianza que ofrecer -- coincide exacto o no coincide."""


@dataclass(slots=True, frozen=True)
class EstadoPanel:
    """El resultado de aplicar un `Panel` contra un log: qué se monta y por
    qué se oculta lo que se oculta."""

    panel: Panel
    elementos: tuple[EstadoElemento, ...]
    """En el mismo orden que `panel.elementos`, disponibles o no: quien
    dibuja decide si enseña también los huecos o solo lo disponible."""

    @property
    def roles_requeridos_faltantes(self) -> frozenset[str]:
        """Los roles requeridos del panel que el log NO trae. Vacío si el
        panel se puede montar entero (o si no requiere ningún rol)."""
        return frozenset(
            e.elemento.rol
            for e in self.elementos
            if e.elemento.requerido and e.elemento.rol is not None and not e.disponible
        )

    @property
    def visible(self) -> bool:
        """Decisión 3: un panel se OCULTA si le falta alguno de sus roles
        requeridos. Nunca se muestra vacío en su lugar."""
        return not self.roles_requeridos_faltantes

    @property
    def elementos_disponibles(self) -> tuple[EstadoElemento, ...]:
        """Lo que de verdad se dibuja cuando el panel es `visible`."""
        return tuple(e for e in self.elementos if e.disponible)

    @property
    def elementos_no_disponibles(self) -> tuple[EstadoElemento, ...]:
        return tuple(e for e in self.elementos if not e.disponible)

    @property
    def roles_disponibles_del_panel(self) -> frozenset[str]:
        """Los roles de `panel.roles_referenciados` que el log sí trae."""
        referenciados = self.panel.roles_referenciados
        return frozenset(
            e.elemento.rol
            for e in self.elementos
            if e.disponible and e.elemento.rol is not None and e.elemento.rol in referenciados
        )

    @property
    def cobertura(self) -> tuple[int, int]:
        """`(roles disponibles, roles referenciados)` de ESTE panel, en el
        estilo de E4.5 pero a escala de panel en vez de perfil entero. Un
        panel sin ningún rol (todo por `id_nativo`, como buena parte de P7)
        da `(0, 0)`: no hay roles que contar, no que la cobertura sea cero."""
        referenciados = self.panel.roles_referenciados
        if not referenciados:
            return (0, 0)
        return (len(self.roles_disponibles_del_panel), len(referenciados))

    @property
    def motivo_oculto(self) -> str | None:
        """La frase que explica por qué `visible` es `False`, nombrando los
        roles que faltan -- `None` si el panel es visible. Mismo criterio que
        `activacion_detectores._motivo`: nombrar el rol es lo que convierte
        el hueco en algo que se puede arreglar (importando otro log, o
        editando el perfil)."""
        faltantes = self.roles_requeridos_faltantes
        if not faltantes:
            return None
        disponibles, total = self.cobertura
        return (
            f"el panel '{self.panel.titulo}' se oculta: no llega {_lista(faltantes)} "
            f"({disponibles} de {total} roles del panel disponibles)"
        )


def _lista(nombres: frozenset[str]) -> str:
    """«el rol x» o «los roles x, y», para que el motivo se lea como una
    frase (mismo criterio que `activacion_detectores._lista`)."""
    ordenados = sorted(nombres)
    if len(ordenados) == 1:
        return f"el rol {ordenados[0]}"
    return f"los roles {', '.join(ordenados)}"


def _aplicar_elemento(
    elemento: ElementoDePanel,
    asignaciones: dict[tuple[str, int | None], Asignacion],
    ids_nativos: frozenset[str],
) -> EstadoElemento:
    if elemento.rol is not None:
        asignacion = asignaciones.get((elemento.rol, elemento.indice))
        return EstadoElemento(
            elemento=elemento, disponible=asignacion is not None, asignacion=asignacion
        )
    # Reserva a id_nativo (decisión 1): coincidencia exacta, nunca un parecido.
    # `ElementoDePanel.__post_init__` garantiza que aquí `id_nativo` no es None.
    assert elemento.id_nativo is not None
    return EstadoElemento(elemento=elemento, disponible=elemento.id_nativo in ids_nativos)


def aplicar_perfil(
    perfil: Perfil, canales: Sequence[CanalDeLogResuelto]
) -> tuple[EstadoPanel, ...]:
    """Aplica `perfil` contra los canales de un log ya abierto.

    Devuelve un `EstadoPanel` por cada panel del perfil, EN EL MISMO ORDEN
    (`perfil.paneles`): quien dibuja decide si filtra por `.visible` o
    enseña también lo oculto con su `motivo_oculto`. No se devuelve un
    `dict` por título de panel porque `perfil.py` no exige títulos únicos
    entre paneles -- indexar por título perdería un panel duplicado en
    silencio.
    """
    asignaciones = _indexar_asignaciones(canales)
    ids_nativos = frozenset(c.id_nativo for c in canales if c.id_nativo is not None)
    return tuple(
        EstadoPanel(
            panel=panel,
            elementos=tuple(
                _aplicar_elemento(e, asignaciones, ids_nativos) for e in panel.elementos
            ),
        )
        for panel in perfil.paneles
    )
