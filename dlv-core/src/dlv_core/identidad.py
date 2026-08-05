"""Identidad de canal en capas y emparejamiento entre logs (tarea F2-02).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.11 y ADR-008. Es lo que
permite que `coolant_temp` de un Haltech y `coolant_temp` de un MoTeC sean «el
mismo canal» en la vista paralela y en la concatenada (§3.6).

EL PROBLEMA
===========
Con un solo formato, el `ID` nativo bastaba como clave. Con formatos
heterogéneos deja de servir: el ID 14 de un fabricante no tiene nada que ver con
el 14 de otro. La identidad pasa a ser en **capas**, y el orden de §7.11 es una
prioridad, no una lista de alternativas:

    1. MANUAL   lo que el usuario emparejó a mano. Gana sobre todo.
    2. ROL      `coolant_temp` con `coolant_temp`. El camino normal.
    3. NATIVO   `(formato, ID)`, solo DENTRO del mismo formato.
    4. NOMBRE   nombre normalizado. Último recurso, y se avisa.

UN CANAL PERTENECE A EXACTAMENTE UN GRUPO
=========================================
Es el invariante que sostiene todo lo demás. Un canal emparejado por rol no
vuelve a entrar en el grupo de su `(formato, ID)`: si lo hiciera, aparecería dos
veces en el selector y dos veces en la vista concatenada, y el usuario vería la
misma señal duplicada sin entender por qué. Por eso `emparejar` recorre las capas
en orden y va apartando lo ya emparejado, en vez de calcular las cuatro capas por
separado y unirlas después.

LA CAPA NATIVA NO CRUZA FORMATOS
================================
`(formato, ID)` incluye el formato a propósito. Emparejar por ID a secas entre
dos fabricantes distintos produciría parejas aleatorias con aspecto de acierto:
es peor que no emparejar, porque no hay nada en la pantalla que lo delate.

QUÉ ES UN HUECO Y QUÉ ES UN CONFLICTO
=====================================
- **Hueco**: un grupo que existe en un segmento y no en otro. Es normal —un log
  de 25 canales y otro de 475 no traen lo mismo— y §3.6 exige que produzca hueco
  y no ceros. `GrupoDeCanales.ausentes` es lo que hay que preguntar antes de
  dibujar.
- **Conflicto**: dos canales del MISMO segmento que caerían en el mismo grupo.
  Eso no se puede resolver aquí sin inventar, así que se queda uno —el de `id`
  menor, para que el resultado sea reproducible— y se avisa nombrando a los dos.
  Fusionarlos en silencio sería promediar dos sensores distintos.

ROLES INDEXADOS: `ChannelKey.rol` NO BASTA
==========================================
13 roles de `data/roles.toml` están marcados `indexado`, y sus sinónimos llevan
la marca `{n}`: «Knock Sensor {n} Knock Count», «O2 Control Bank {n} Short Term
Fuel Trim». Los dos sensores de knock de un mismo log reciben el MISMO rol
(`knock_count`) y se distinguen solo por el `indice` que devuelve
`roles.Asignacion`, que `ChannelKey` no guarda.

Agrupar por `ChannelKey.rol` a secas colapsaría los dos sensores en un solo
grupo, y entonces uno de los dos desaparecería de la pantalla y el otro se
compararía contra el sensor equivocado del otro log. Por eso `CanalDeLog` recibe
el `indice` aparte y la identidad del grupo es `rol#indice` cuando lo hay. Es una
carencia del modelo de FG-09 que esta tarea rodea sin tocarlo: anotada en la nota
de F2-02 para su puerta G1.

ADR-009
=======
Este módulo recorre **canales**, no muestras: 475 en el peor log real, unos
pocos miles con ocho logs abiertos. Los diccionarios de Python son lo correcto
aquí y no hay nada que vectorizar. Lo que ADR-009 prohíbe es recorrer las
muestras, y aquí no se toca ni una.

Solo biblioteca estándar.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from dlv_core.informes import Aviso
from dlv_core.roles import Asignacion, ChannelKey, normalizar

__all__ = [
    "CanalDeLog",
    "Capa",
    "Emparejamiento",
    "EmparejamientoManual",
    "ErrorDeIdentidad",
    "GrupoDeCanales",
    "emparejar",
]


class ErrorDeIdentidad(ValueError):
    """Un emparejamiento que no se puede construir sin inventar."""


class Capa(Enum):
    """Por qué se emparejaron los canales de un grupo (§7.11).

    El orden de declaración **es** la prioridad: `MANUAL` gana sobre `ROL`, que
    gana sobre `NATIVO`, que gana sobre `NOMBRE`. Se compara con `.prioridad` y
    no con el orden del enum para que añadir una capa en medio no cambie
    silenciosamente la precedencia.
    """

    MANUAL = "manual"
    ROL = "rol"
    NATIVO = "nativo"
    NOMBRE = "nombre"

    @property
    def prioridad(self) -> int:
        return _PRIORIDAD[self]

    @property
    def es_automatica(self) -> bool:
        return self is not Capa.MANUAL


_PRIORIDAD = {Capa.MANUAL: 0, Capa.ROL: 1, Capa.NATIVO: 2, Capa.NOMBRE: 3}


@dataclass(slots=True, frozen=True)
class CanalDeLog:
    """Un canal concreto de un segmento concreto, listo para emparejar.

    `id_canal` es la referencia local con la que se le piden los cubos al
    backend; `clave` es su identidad en capas (ADR-008), e `indice_rol` el
    número que capturó la marca `{n}` del sinónimo, si la había.
    """

    id_segmento: str
    id_canal: str
    clave: ChannelKey
    indice_rol: int | None = None
    etiqueta: str | None = None
    """Nombre original del canal, para mostrar. Nunca para emparejar: los
    nombres del formato Haltech traen erratas del origen (`FuelEcomony`) y
    §1.3 prohíbe usarlos como identidad."""

    requiere_confirmacion: bool = False
    """`True` si el rol se asignó por parecido y el usuario no lo ha confirmado
    (`roles.Asignacion.requiere_confirmacion`). No impide emparejar, pero viaja
    hasta el grupo para que los detectores críticos puedan desactivarse
    (mitigación 4 de §7.15)."""

    @classmethod
    def desde_asignacion(
        cls,
        *,
        id_segmento: str,
        id_canal: str,
        nombre: str,
        formato: str | None,
        id_nativo: str | None,
        asignacion: Asignacion | None,
    ) -> CanalDeLog:
        """Construye el canal a partir de lo que devuelve `roles.asignar_rol`.

        Es el puente entre FG-09 (asignar roles a nombres) y esta tarea
        (emparejar canales entre logs), y existe para que el `indice` de la
        asignación no se pierda por el camino: es lo único que distingue los dos
        sensores de knock de un mismo log.
        """
        return cls(
            id_segmento=id_segmento,
            id_canal=id_canal,
            clave=ChannelKey(
                rol=asignacion.rol if asignacion is not None else None,
                formato=formato,
                id_nativo=id_nativo,
                nombre_normalizado=normalizar(nombre),
            ),
            indice_rol=asignacion.indice if asignacion is not None else None,
            etiqueta=nombre,
            requiere_confirmacion=(
                asignacion.requiere_confirmacion if asignacion is not None else False
            ),
        )


@dataclass(slots=True, frozen=True)
class EmparejamientoManual:
    """Lo que el usuario emparejó a mano; se persiste en el proyecto (F2-03).

    `miembros` es `id_segmento -> id_canal`. Gana sobre cualquier capa
    automática, incluso contradiciéndola: el usuario puede tener razón —dos
    canales mal nombrados que sí son el mismo— y puede estar equivocándose, así
    que se obedece y se avisa.
    """

    nombre: str
    miembros: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise ErrorDeIdentidad("un emparejamiento manual necesita nombre para mostrarse")
        if len(self.miembros) < 2:
            raise ErrorDeIdentidad(
                f"el emparejamiento manual '{self.nombre}' tiene "
                f"{len(self.miembros)} miembro(s): emparejar es unir al menos dos"
            )


@dataclass(slots=True, frozen=True)
class GrupoDeCanales:
    """«El mismo canal» visto en varios segmentos."""

    id: str
    """Identidad estable y legible: `rol:coolant_temp`, `rol:knock_count#2`,
    `nativo:haltech_nsp:14`, `nombre:coolanttemperature`, `manual:Mi pareja`.
    Estable a propósito: el fichero de proyecto y el frontend la guardan, así que
    no puede depender del orden de carga ni de un contador."""

    capa: Capa
    etiqueta: str
    miembros: Mapping[str, CanalDeLog]
    """`id_segmento -> canal`. Un segmento aporta como máximo un canal: ver
    «qué es un hueco y qué es un conflicto» en la cabecera del módulo."""

    @property
    def segmentos(self) -> tuple[str, ...]:
        return tuple(self.miembros)

    @property
    def requiere_confirmacion(self) -> bool:
        """`True` si algún miembro llegó por parecido sin confirmar.

        Basta uno: un grupo con un miembro dudoso ya no sirve para un detector
        crítico, porque la comparación entre logs saldría de un canal que puede
        no ser el que se cree.
        """
        return any(c.requiere_confirmacion for c in self.miembros.values())

    def presente_en(self, id_segmento: str) -> bool:
        return id_segmento in self.miembros

    def canal_en(self, id_segmento: str) -> CanalDeLog | None:
        return self.miembros.get(id_segmento)

    def ausentes(self, segmentos: Iterable[str]) -> tuple[str, ...]:
        """Los segmentos donde este grupo NO existe.

        Es lo que hay que preguntar antes de dibujar la vista concatenada: §3.6
        exige que un canal ausente en un segmento produzca **hueco, no ceros**, y
        un cero es un valor plausible para casi cualquier canal.
        """
        return tuple(s for s in segmentos if s not in self.miembros)

    @property
    def es_comun(self) -> bool:
        """Atajo de legibilidad: ¿hay más de un segmento en el grupo?"""
        return len(self.miembros) > 1


@dataclass(slots=True, frozen=True)
class Emparejamiento:
    """El resultado: los grupos, en qué capa cayó cada uno, y los avisos."""

    grupos: tuple[GrupoDeCanales, ...]
    segmentos: tuple[str, ...]
    avisos: tuple[Aviso, ...] = ()

    def por_id(self, id_grupo: str) -> GrupoDeCanales:
        for g in self.grupos:
            if g.id == id_grupo:
                return g
        raise ErrorDeIdentidad(f"no hay ningún grupo con id '{id_grupo}'")

    def grupo_de(self, id_segmento: str, id_canal: str) -> GrupoDeCanales:
        """A qué grupo fue a parar un canal concreto.

        Lo necesita el selector de canales: el usuario marca un canal de un log y
        hay que enseñar el de los demás.
        """
        for g in self.grupos:
            c = g.miembros.get(id_segmento)
            if c is not None and c.id_canal == id_canal:
                return g
        raise ErrorDeIdentidad(
            f"el canal '{id_canal}' del segmento '{id_segmento}' no está en ningún grupo"
        )

    @property
    def comunes(self) -> tuple[GrupoDeCanales, ...]:
        """Los grupos presentes en más de un segmento: lo que de verdad se puede
        comparar. Es la lista que el selector debería enseñar primero."""
        return tuple(g for g in self.grupos if g.es_comun)

    def comunes_a_todos(self) -> tuple[GrupoDeCanales, ...]:
        """Los grupos presentes en TODOS los segmentos abiertos."""
        return tuple(g for g in self.grupos if len(g.miembros) == len(self.segmentos))

    def por_capa(self, capa: Capa) -> tuple[GrupoDeCanales, ...]:
        return tuple(g for g in self.grupos if g.capa is capa)


# --------------------------------------------------------------------------- #
# Emparejamiento
# --------------------------------------------------------------------------- #
def _id_de_rol(canal: CanalDeLog) -> str | None:
    """`rol:coolant_temp`, o `rol:knock_count#2` para los roles indexados.

    El `#indice` es lo que evita que los dos sensores de knock de un mismo log
    colapsen en un grupo: ver la cabecera del módulo.
    """
    if canal.clave.rol is None:
        return None
    if canal.indice_rol is None:
        return f"rol:{canal.clave.rol}"
    return f"rol:{canal.clave.rol}#{canal.indice_rol}"


def _id_nativo(canal: CanalDeLog) -> str | None:
    """`nativo:<formato>:<id>`. Exige las dos partes: un ID sin formato
    emparejaría entre fabricantes distintos."""
    if canal.clave.formato is None or canal.clave.id_nativo is None:
        return None
    return f"nativo:{canal.clave.formato}:{canal.clave.id_nativo}"


def _id_nombre(canal: CanalDeLog) -> str | None:
    if not canal.clave.nombre_normalizado:
        return None
    return f"nombre:{canal.clave.nombre_normalizado}"


_CLAVES_POR_CAPA = {
    Capa.ROL: _id_de_rol,
    Capa.NATIVO: _id_nativo,
    Capa.NOMBRE: _id_nombre,
}


@dataclass(slots=True)
class _Acumulador:
    avisos: list[Aviso] = field(default_factory=list)

    def avisa(self, codigo: str, mensaje: str) -> None:
        self.avisos.append(Aviso(codigo, mensaje))


def emparejar(
    canales: Sequence[CanalDeLog],
    *,
    segmentos: Sequence[str],
    manuales: Sequence[EmparejamientoManual] = (),
) -> Emparejamiento:
    """Agrupa los canales de varios logs según la identidad en capas de §7.11.

    `segmentos` es la lista de segmentos abiertos, y se pide aparte en vez de
    deducirla de `canales`: un segmento cuyo log no tenga ningún canal en un
    grupo tiene que seguir contando para `GrupoDeCanales.ausentes`, y deducirla
    de los canales lo haría desaparecer de la cuenta de huecos.
    """
    ac = _Acumulador()
    _comprobar_entrada(canales, segmentos, ac)

    pendientes = {(c.id_segmento, c.id_canal): c for c in canales}
    grupos: list[GrupoDeCanales] = []

    # Capa 1: lo manual, que gana sobre todo (§7.11 punto 4).
    for m in manuales:
        grupo = _grupo_manual(m, pendientes, ac)
        if grupo is not None:
            grupos.append(grupo)

    # Capas 2 a 4, en orden de prioridad y apartando lo ya emparejado. El orden
    # importa: es lo que garantiza que un canal esté en exactamente un grupo.
    for capa in (Capa.ROL, Capa.NATIVO, Capa.NOMBRE):
        grupos.extend(_grupos_de_capa(capa, pendientes, ac))

    if pendientes:
        # Un canal sin rol, sin (formato, ID) y sin nombre no se puede identificar
        # de ninguna manera. No es un error de carga —se puede dibujar solo— pero
        # el usuario tiene que saber que no se comparará con nada.
        for c in sorted(pendientes.values(), key=lambda c: (c.id_segmento, c.id_canal)):
            ac.avisa(
                "canal_sin_identidad",
                f"el canal '{c.etiqueta or c.id_canal}' del segmento '{c.id_segmento}' no "
                "declara rol, ni (formato, ID), ni nombre: no se puede emparejar con "
                "ningún otro log",
            )

    _avisar_de_los_nombres(grupos, ac)
    return Emparejamiento(
        grupos=tuple(sorted(grupos, key=lambda g: (g.capa.prioridad, g.id))),
        segmentos=tuple(segmentos),
        avisos=tuple(ac.avisos),
    )


def _comprobar_entrada(
    canales: Sequence[CanalDeLog], segmentos: Sequence[str], ac: _Acumulador
) -> None:
    if len(set(segmentos)) != len(segmentos):
        raise ErrorDeIdentidad(
            "hay ids de segmento repetidos: los grupos se indexan por segmento, así que "
            "uno repetido perdería canales sin decirlo"
        )
    conocidos = set(segmentos)
    vistos: set[tuple[str, str]] = set()
    for c in canales:
        if c.id_segmento not in conocidos:
            raise ErrorDeIdentidad(
                f"el canal '{c.id_canal}' dice ser del segmento '{c.id_segmento}', que no "
                f"está entre los abiertos ({', '.join(segmentos)})"
            )
        if (c.id_segmento, c.id_canal) in vistos:
            raise ErrorDeIdentidad(
                f"el canal '{c.id_canal}' aparece dos veces en el segmento '{c.id_segmento}'"
            )
        vistos.add((c.id_segmento, c.id_canal))


def _grupo_manual(
    m: EmparejamientoManual,
    pendientes: dict[tuple[str, str], CanalDeLog],
    ac: _Acumulador,
) -> GrupoDeCanales | None:
    """Un grupo de la capa MANUAL, avisando de lo que contradice o no existe."""
    miembros: dict[str, CanalDeLog] = {}
    for id_segmento, id_canal in m.miembros.items():
        canal = pendientes.pop((id_segmento, id_canal), None)
        if canal is None:
            # O el canal no existe, o ya lo reclamó otro emparejamiento manual.
            # Las dos cosas son un error del usuario y las dos se avisan igual:
            # el emparejamiento se aplica con lo que sí existe.
            ac.avisa(
                "manual_no_aplicable",
                f"el emparejamiento manual '{m.nombre}' cita el canal '{id_canal}' del "
                f"segmento '{id_segmento}', que no existe o ya está en otro "
                "emparejamiento manual; se ignora esa parte",
            )
            continue
        miembros[id_segmento] = canal

    if len(miembros) < 2:
        for canal in miembros.values():
            pendientes[(canal.id_segmento, canal.id_canal)] = canal
        ac.avisa(
            "manual_descartado",
            f"el emparejamiento manual '{m.nombre}' se queda con menos de dos canales "
            "válidos, así que no empareja nada; sus canales vuelven al emparejamiento "
            "automático",
        )
        return None

    roles = {c.clave.rol for c in miembros.values() if c.clave.rol is not None}
    if len(roles) > 1:
        # El usuario manda (§7.11 punto 4), pero unir dos roles distintos es lo
        # bastante raro como para decirlo: puede ser justo lo que quería —dos
        # canales mal nombrados— o puede ser un despiste.
        ac.avisa(
            "manual_contradice_rol",
            f"el emparejamiento manual '{m.nombre}' une canales con roles distintos "
            f"({', '.join(sorted(roles))}). Se respeta porque lo manual tiene prioridad, "
            "pero comprueba que es lo que querías",
        )

    return GrupoDeCanales(
        id=f"manual:{m.nombre}", capa=Capa.MANUAL, etiqueta=m.nombre, miembros=miembros
    )


def _grupos_de_capa(
    capa: Capa,
    pendientes: dict[tuple[str, str], CanalDeLog],
    ac: _Acumulador,
) -> list[GrupoDeCanales]:
    """Agrupa lo que queda pendiente por la clave de `capa` y lo aparta.

    Recorre los canales en orden determinista: con dos canales del mismo segmento
    en el mismo grupo hay que quedarse con uno, y «el primero» solo significa
    algo si el orden no depende del recorrido de un diccionario.
    """
    clave_de = _CLAVES_POR_CAPA[capa]
    por_clave: dict[str, dict[str, CanalDeLog]] = {}
    etiquetas: dict[str, str] = {}
    reclamados: list[tuple[str, str]] = []

    for canal in sorted(pendientes.values(), key=lambda c: (c.id_segmento, c.id_canal)):
        id_grupo = clave_de(canal)
        if id_grupo is None:
            continue
        miembros = por_clave.setdefault(id_grupo, {})
        anterior = miembros.get(canal.id_segmento)
        if anterior is not None:
            ac.avisa(
                "canales_del_mismo_log_en_el_mismo_grupo",
                f"el segmento '{canal.id_segmento}' tiene dos canales que caen en el mismo "
                f"grupo '{id_grupo}' ({anterior.etiqueta or anterior.id_canal} y "
                f"{canal.etiqueta or canal.id_canal}). Se usa el primero por id; el otro "
                "queda suelto. Si son sensores distintos, el rol necesita índice "
                "(`{n}` en data/roles.toml) o hace falta un emparejamiento manual",
            )
            continue
        miembros[canal.id_segmento] = canal
        etiquetas.setdefault(id_grupo, canal.etiqueta or canal.id_canal)
        reclamados.append((canal.id_segmento, canal.id_canal))

    for clave in reclamados:
        pendientes.pop(clave, None)

    return [
        GrupoDeCanales(id=id_grupo, capa=capa, etiqueta=etiquetas[id_grupo], miembros=miembros)
        for id_grupo, miembros in por_clave.items()
    ]


def _avisar_de_los_nombres(grupos: Sequence[GrupoDeCanales], ac: _Acumulador) -> None:
    """La capa NOMBRE es el último recurso y hay que decirlo (§7.11 punto 3).

    Solo se avisa de los que emparejan de verdad —más de un segmento—, porque un
    grupo de un solo canal identificado por su nombre no afirma nada sobre nadie.
    Dos fabricantes pueden llamar «Oil Temp» a cosas distintas, y ese
    emparejamiento no lo respalda ni un rol ni un ID: lo respalda una cadena de
    texto.
    """
    for g in grupos:
        if g.capa is Capa.NOMBRE and g.es_comun:
            ac.avisa(
                "emparejado_solo_por_nombre",
                f"'{g.etiqueta}' se ha emparejado entre {len(g.miembros)} logs solo por el "
                "nombre, sin rol ni ID en común. Compruébalo antes de comparar: dos "
                "fabricantes pueden usar el mismo nombre para cosas distintas",
            )
