"""Qué detectores se desactivan porque su rol es una conjetura (tarea F3-08).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.15, mitigación 4, y la
sección `[desactivacion_automatica]` de `data/umbrales.toml`, que F3-07 dejó
declarada:

    severidades_afectadas = ["critica"]
    motivo = "rol asignado por parecido de nombre y sin confirmar"

EL RIESGO QUE MITIGA, Y POR QUÉ LA MITIGACIÓN ES CALLARSE
==========================================================
Un importador genérico puede acertar en la sintaxis y equivocarse en el
significado: emparejar `Oil Temp` con el rol `oil_pressure` porque los nombres se
parecen, y presentar un número plausible y falso. Cuando eso alimenta un detector
crítico, el resultado no es un hueco en la interfaz: es una alerta roja que dice
«presión de aceite crítica» sobre un canal que mide otra cosa.

§7.15 elige explícitamente no avisar antes que avisar en falso, y el motivo está
escrito allí: «una alerta falsa repetida enseña al usuario a ignorar las
alertas». Ese es el daño real y es acumulativo — se paga la próxima vez, en el
detector que sí tenía razón. Este módulo es esa decisión aplicada.

LO QUE NO HACE, A PROPÓSITO
============================
No decide nada sobre los detectores NO críticos. Un detector de severidad media
con un rol difuso sigue activo: el coste de equivocarse es una fila más en el
panel, no una alerta roja, y ahí sí compensa avisar. La política de qué
severidades se ven afectadas vive en `data/umbrales.toml` y no aquí, así que
cambiar ese criterio es editar un dato con su comentario, no este código.

Tampoco decide si un rol es difuso: eso lo trae `roles.Asignacion`
(`requiere_confirmacion`, FG-09) y viaja hasta aquí a través de
`identidad.CanalDeLog.requiere_confirmacion`. Este módulo solo recibe la lista de
roles que no están confirmados y la cruza con el catálogo.

TRES ESTADOS, NO DOS
=====================
La distinción que hace útil el resultado es que «desactivado por precaución» y
«no se puede ejecutar» no son lo mismo, y ninguno de los dos es «todo bien»:

* **Activo.** Todos sus roles están en el log y confirmados.
* **Desactivado por rol sin confirmar.** El detector podría ejecutarse, y no se
  ejecuta a propósito. Es una decisión, y el usuario puede revertirla
  confirmando el rol: el motivo tiene que decirle QUÉ rol confirmar.
* **No ejecutable por rol ausente.** El log no trae el canal. No hay nada que
  confirmar y no es una precaución; es una carencia del log.

Colapsar los dos últimos en un «desactivado» genérico dejaría al usuario sin
saber si le falta un canal o le falta un clic, que son dos acciones distintas.
Por eso `EstadoDetector` lleva las dos listas de roles por separado y no solo un
booleano con un texto.

SOBRE LA CLASE DE CONVERSIÓN (regla 4 de `CLAUDE.md`)
=====================================================
Aquí no hay ninguna. Este módulo no produce ni convierte ninguna magnitud: sus
salidas son identificadores de detector, nombres de rol y severidades, que son
etiquetas. La regla aplica a los números, y aquí no hay números. Se deja escrito
para que la ausencia sea deliberada y no un olvido.

ADR-009 no entra en juego por la misma razón: se recorren 18 detectores y sus
roles, no 73 millones de muestras.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import IO, Any

from dlv_core.plausibilidad import SEVERIDADES


class ErrorDeActivacion(ValueError):
    """El catálogo de detectores o la política de desactivación no son usables."""


@dataclass(slots=True, frozen=True)
class DetectorDeclarado:
    """Lo que `[detectores.DN]` dice de un detector, para decidir su activación.

    Solo la parte que importa aquí: su identificador, su etiqueta para mostrar,
    los roles que necesita y las severidades que PUEDE emitir. Los umbrales de
    cada detector no se leen: no influyen en si se ejecuta.
    """

    id: str
    etiqueta: str
    roles: tuple[str, ...]
    severidades_posibles: tuple[str, ...]
    """Todas las que el detector puede emitir, no solo la declarada.

    D13 («Protección de motor activa») no tiene `severidad` sino
    `severidad_por_nivel = {1 = "media", 2 = "alta", 3 = "critica"}`: su
    severidad depende del dato. Un detector así puede emitir una crítica, y
    tratarlo por su severidad «declarada» —que no existe— lo habría dejado fuera
    de la mitigación. Ver `esta_afectado`.
    """

    @property
    def severidad_maxima(self) -> str:
        """La más grave de las que puede emitir, según el orden de `SEVERIDADES`."""
        return min(self.severidades_posibles, key=SEVERIDADES.index)

    def esta_afectado(self, severidades_afectadas: frozenset[str]) -> bool:
        """`True` si ALGUNA severidad que puede emitir está en la política.

        «Alguna» y no «la declarada» es la decisión de fondo de este módulo, y
        cambia el resultado: con `severidades_afectadas = ["critica"]` el
        criterio afecta a D4, D10 y D12 —los tres que docs/07 §7.15 enumera entre
        paréntesis— y TAMBIÉN a D13, que solo es crítico en su nivel 3.

        Lo hace a propósito. Si el rol `protection_level` de D13 se emparejó por
        parecido, una crítica de nivel 3 dice «la ECU está protegiendo el motor»
        sobre un canal que igual mide otra cosa, que es exactamente el aviso
        falso que §7.15 quiere evitar y encima el de mayor consecuencia del
        catálogo. Tratar a D13 por «no tiene severidad crítica declarada» habría
        sido cierto en la letra y falso en el efecto.
        """
        return any(s in severidades_afectadas for s in self.severidades_posibles)


@dataclass(slots=True, frozen=True)
class PoliticaDesactivacion:
    """`[desactivacion_automatica]` de `data/umbrales.toml`, ya validada."""

    severidades_afectadas: frozenset[str]
    motivo: str


@dataclass(slots=True, frozen=True)
class EstadoDetector:
    """Si un detector se ejecuta en este log, y si no, por qué exactamente.

    Es lo que consume el panel de incidencias (F3-12, `dlv-ui/src/incidencias`):
    un detector desactivado tiene fila igual, con el motivo, para que «apagado»
    no se confunda con «sin incidencias».
    """

    detector_id: str
    activo: bool
    motivo: str | None
    """`None` si está activo. Si no, un texto que nombra los roles implicados:
    el usuario no puede actuar sobre «detector desactivado» y sí sobre «confirma
    el rol oil_pressure»."""
    roles_sin_confirmar: tuple[str, ...]
    roles_ausentes: tuple[str, ...]


def cargar_politica(fh: IO[bytes]) -> PoliticaDesactivacion:
    """Lee `[desactivacion_automatica]` y la valida.

    LA VALIDACIÓN NO ES CEREMONIA. El fallo que hay que impedir es una errata en
    `severidades_afectadas`: con `["critico"]` en vez de `["critica"]` no coincide
    con ninguna severidad del catálogo, no se desactiva ningún detector, y NO
    FALLA NADA. La mitigación de R10 quedaría apagada en silencio y el síntoma
    sería una alerta crítica falsa meses después. Por eso una severidad que no
    esté en `plausibilidad.SEVERIDADES` es un error y no un aviso.
    """
    datos = tomllib.load(fh)
    seccion = datos.get("desactivacion_automatica")
    if seccion is None:
        raise ErrorDeActivacion(
            "no hay sección [desactivacion_automatica] en el fichero de umbrales; "
            "sin ella no se sabe qué severidades se desactivan y no se puede "
            "suponer ninguna (mitigación de R10, docs/07 §7.15)"
        )
    return _politica_de(seccion)


def _politica_de(seccion: dict[str, Any]) -> PoliticaDesactivacion:
    faltan = [c for c in ("severidades_afectadas", "motivo") if c not in seccion]
    if faltan:
        raise ErrorDeActivacion(
            f"[desactivacion_automatica] no declara {', '.join(faltan)}: "
            "no se rellena con un valor por omisión porque cuál sea decide si un "
            "detector crítico avisa o se calla"
        )

    crudo = seccion["severidades_afectadas"]
    if not isinstance(crudo, list) or not all(isinstance(s, str) for s in crudo):
        raise ErrorDeActivacion(
            f"severidades_afectadas tiene que ser una lista de cadenas, no {crudo!r}"
        )
    desconocidas = [s for s in crudo if s not in SEVERIDADES]
    if desconocidas:
        raise ErrorDeActivacion(
            f"severidades_afectadas nombra severidades que no existen: {desconocidas}. "
            f"Las válidas son {list(SEVERIDADES)}. Una errata aquí no desactivaría "
            "ningún detector y no daría ningún error: dejaría apagada la mitigación "
            "de R10 sin que nadie se enterase"
        )
    if not crudo:
        raise ErrorDeActivacion(
            "severidades_afectadas está vacía. Si de verdad se quiere desactivar la "
            "mitigación de R10, tiene que ser una decisión escrita y visible en el "
            "fichero de datos, no una lista vacía que parece un descuido"
        )

    motivo = seccion["motivo"]
    if not isinstance(motivo, str) or not motivo.strip():
        raise ErrorDeActivacion(f"motivo tiene que ser un texto no vacío, no {motivo!r}")
    return PoliticaDesactivacion(severidades_afectadas=frozenset(crudo), motivo=motivo)


def cargar_catalogo_detectores(fh: IO[bytes]) -> dict[str, DetectorDeclarado]:
    """Lee `[detectores]` de `data/umbrales.toml`.

    Es el primer consumidor de esa sección: F3-07 la declaró y hasta ahora nadie
    la leía. Un detector sin `roles` declarados no es un error —D16, D17 y D18
    son informativos sobre el muestreo, no sobre un rol— pero sí lo es uno sin
    ninguna severidad: sin ella no se puede decidir si le afecta la política, y
    suponer «informativa» sería suponer justo el lado que no desactiva nada.
    """
    datos = tomllib.load(fh)
    seccion = datos.get("detectores")
    if not isinstance(seccion, dict) or not seccion:
        raise ErrorDeActivacion("no hay sección [detectores] en el fichero de umbrales")

    catalogo: dict[str, DetectorDeclarado] = {}
    for id_detector, crudo in seccion.items():
        if not isinstance(crudo, dict):
            raise ErrorDeActivacion(f"[detectores.{id_detector}] no es una tabla")
        catalogo[id_detector] = _detector_de(id_detector, crudo)
    return catalogo


def _detector_de(id_detector: str, crudo: dict[str, Any]) -> DetectorDeclarado:
    severidades = _severidades_de(id_detector, crudo)
    roles = crudo.get("roles", ())
    if not isinstance(roles, (list, tuple)) or not all(isinstance(r, str) for r in roles):
        raise ErrorDeActivacion(
            f"[detectores.{id_detector}].roles tiene que ser una lista de cadenas, no {roles!r}"
        )
    etiqueta = crudo.get("etiqueta")
    if not isinstance(etiqueta, str) or not etiqueta.strip():
        raise ErrorDeActivacion(
            f"[detectores.{id_detector}] no tiene `etiqueta`: el panel de incidencias "
            "necesita un nombre que mostrar, y el identificador «D10» no le dice nada "
            "a quien lee el log"
        )
    return DetectorDeclarado(
        id=id_detector,
        etiqueta=etiqueta,
        roles=tuple(roles),
        severidades_posibles=severidades,
    )


def _severidades_de(id_detector: str, crudo: dict[str, Any]) -> tuple[str, ...]:
    """`severidad`, o todas las de `severidad_por_nivel`. Una de las dos, no ninguna."""
    fija = crudo.get("severidad")
    por_nivel = crudo.get("severidad_por_nivel")
    if fija is not None and por_nivel is not None:
        raise ErrorDeActivacion(
            f"[detectores.{id_detector}] declara `severidad` y `severidad_por_nivel` a "
            "la vez: no se puede saber cuál manda"
        )

    if fija is not None:
        candidatas = (fija,)
    elif isinstance(por_nivel, dict):
        candidatas = tuple(por_nivel.values())
    else:
        raise ErrorDeActivacion(
            f"[detectores.{id_detector}] no declara `severidad` ni "
            "`severidad_por_nivel`. No se supone ninguna: suponer «informativa» sería "
            "suponer precisamente el lado que no desactiva nada, y un detector crítico "
            "mal declarado seguiría avisando sobre un rol adivinado"
        )

    malas = [s for s in candidatas if s not in SEVERIDADES]
    if malas:
        raise ErrorDeActivacion(
            f"[detectores.{id_detector}] declara severidades desconocidas {malas}; "
            f"las válidas son {list(SEVERIDADES)}"
        )
    return tuple(candidatas)


def evaluar_activacion(
    catalogo: dict[str, DetectorDeclarado],
    politica: PoliticaDesactivacion,
    *,
    roles_sin_confirmar: frozenset[str],
    roles_presentes: frozenset[str] | None = None,
) -> dict[str, EstadoDetector]:
    """El estado de cada detector del catálogo para un log concreto.

    :param roles_sin_confirmar: roles asignados por parecido y no confirmados por
        el usuario (`roles.Asignacion.requiere_confirmacion`, FG-09).
    :param roles_presentes: los roles que el log trae resueltos. `None` significa
        «no se sabe», y entonces NO se juzga la ausencia de ningún rol: es la
        diferencia entre no tener el dato y tener el dato de que falta. Pasar un
        conjunto vacío sí afirma que no hay ningún rol.

    Un detector puede estar desactivado por las dos razones a la vez —un rol
    ausente y otro sin confirmar—; el motivo las nombra las dos, porque arreglar
    solo una no lo enciende y decir solo una haría creer lo contrario.
    """
    salida: dict[str, EstadoDetector] = {}
    for id_detector, detector in catalogo.items():
        ausentes = (
            tuple(r for r in detector.roles if r not in roles_presentes)
            if roles_presentes is not None
            else ()
        )
        # Un rol ausente no está «sin confirmar»: no está. Contarlo en las dos
        # listas haría que el motivo pidiera confirmar un rol que no existe.
        sin_confirmar = tuple(
            r for r in detector.roles if r in roles_sin_confirmar and r not in ausentes
        )

        afectado = detector.esta_afectado(politica.severidades_afectadas)
        desactiva_por_difuso = afectado and bool(sin_confirmar)
        motivo = _motivo(
            detector=detector,
            politica=politica,
            sin_confirmar=sin_confirmar if desactiva_por_difuso else (),
            ausentes=ausentes,
        )
        salida[id_detector] = EstadoDetector(
            detector_id=id_detector,
            activo=motivo is None,
            motivo=motivo,
            roles_sin_confirmar=sin_confirmar,
            roles_ausentes=ausentes,
        )
    return salida


def _motivo(
    *,
    detector: DetectorDeclarado,
    politica: PoliticaDesactivacion,
    sin_confirmar: tuple[str, ...],
    ausentes: tuple[str, ...],
) -> str | None:
    """El texto que ve el usuario, o `None` si el detector está activo.

    Nombra los roles porque es lo único que convierte el aviso en algo que se
    puede arreglar: «confirma el rol oil_pressure» es una acción, «detector
    desactivado» es un callejón sin salida.
    """
    partes: list[str] = []
    if ausentes:
        partes.append(
            f"el log no trae {_lista(ausentes)}, así que este detector no se puede "
            "ejecutar (no es una precaución: falta el canal)"
        )
    if sin_confirmar:
        partes.append(
            f"{_lista(sin_confirmar)}: {politica.motivo}. Un detector de severidad "
            f"{detector.severidad_maxima} no avisa sobre un rol adivinado; confírmalo "
            "para activarlo (docs/07 §7.15)"
        )
    return " Y ".join(partes) if partes else None


def _lista(nombres: tuple[str, ...]) -> str:
    """«el rol x» o «los roles x, y», para que el motivo se lea como una frase."""
    if len(nombres) == 1:
        return f"el rol {nombres[0]}"
    return f"los roles {', '.join(nombres)}"
