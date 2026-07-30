"""Identidad de canal en capas y catálogo de roles semánticos (ADR-008).

`docs/07-formatos-y-csv-generico.md`: la identidad de un canal deja de ser solo
el `ID` nativo y pasa a resolverse en capas: rol semántico -> `(formato, ID)`
nativo -> nombre normalizado -> asignación manual del usuario. Los perfiles y
detectores (`dlv-core.detectores`) se definen por rol, no por canal concreto,
para que funcionen igual en un log Haltech que en un CSV genérico.

El catálogo de roles (`roles.toml`) y sus sinónimos son datos versionados, no
código (ADR-008).

LO QUE MÁS IMPORTA DE ESTE MÓDULO (mitigación de R10, docs/07 §7.15)
=====================================================================
Un importador genérico puede **acertar en la sintaxis y equivocarse en el
significado**. Por eso `Asignacion` no devuelve solo "qué rol": devuelve
también CÓMO se decidió (`Confianza`). La cuarta mitigación obligatoria de
§7.15 depende literalmente de esa distinción:

    «Los detectores de severidad crítica (D4, D10, D12) se DESACTIVAN en un
    log cuyos roles implicados provengan de asignación difusa no confirmada
    por el usuario. Preferimos no avisar a avisar en falso, porque una alerta
    falsa repetida enseña al usuario a ignorar las alertas.»

Un `resolver_rol` que devolviera solo `str | None` haría esa mitigación
imposible de implementar aguas abajo: no habría forma de saber si el rol se
sacó de una coincidencia exacta o de un parecido del 82 %. De ahí que la
función rica sea `asignar_rol`, y que `resolver_rol` (la firma del andamiaje
original) se conserve solo como atajo para quien no necesita el matiz.

CAMBIOS DE FIRMA RESPECTO AL ANDAMIAJE
=======================================
- `cargar_catalogo_roles` recibía `IO[str]`; recibe `IO[bytes]`, porque
  `tomllib.load` exige binario (y es lo que ya hacen `unidades.cargar_catalogo`
  y `formatos.haltech.cargar_descriptor`, así que además queda consistente).
- `Rol` tenía solo `id`, `dimension` y `sinonimos`; gana `plausible_min`,
  `plausible_max`, `indexado`, `monotono` y `critico`, que son campos que
  `data/roles.toml` ya declara y sin los cuales no se pueden implementar ni el
  informe de plausibilidad (§7.5) ni la desactivación de detectores críticos.

NORMALIZACIÓN
=============
§7.7: «se comparan normalizados: minúsculas, sin acentos, sin separadores».
Así `Régimen`, `regimen` y `REGIMEN` son el mismo nombre, y `Engine Speed`,
`EngineSpeed` y `engine_speed` también. Sin esto, el catálogo tendría que
enumerar cada variante tipográfica de cada fabricante.
"""

from __future__ import annotations

import difflib
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import IO

__all__ = [
    "Asignacion",
    "ChannelKey",
    "Confianza",
    "Rol",
    "asignar_rol",
    "cargar_catalogo_roles",
    "normalizar",
    "resolver_rol",
]

UMBRAL_DIFUSO_POR_OMISION = 0.85
"""Parecido mínimo para proponer una asignación difusa.

Deliberadamente alto: una propuesta difusa es trabajo de revisión para el
usuario, y una lista larga de propuestas malas se ignora entera (el mismo
razonamiento que `data/roles.toml` da para los rangos plausibles anchos).
Nunca es una asignación firme: ver `Confianza.DIFUSA`.
"""

_SEPARADORES = re.compile(r"[\s_\-./\\()\[\]{}:,;+]+")
_MARCA_INDICE = re.compile(r"\{n\}")


class Confianza(Enum):
    """Cómo se decidió una asignación de rol. Ver la cabecera del módulo."""

    EXACTA = "exacta"
    """El nombre normalizado coincide con un sinónimo del catálogo. Firme."""

    INDEXADA = "indexada"
    """Coincide con un sinónimo con marca `{n}` (p. ej. "Knock Sensor 2 Knock
    Count" contra "Knock Sensor {n} Knock Count"). Igual de firme que la
    exacta: la plantilla es explícita en el catálogo, no una suposición."""

    DIFUSA = "difusa"
    """Solo se parece. **No confirmada**: los detectores críticos que dependan
    de un rol así deben desactivarse hasta que el usuario lo confirme
    (docs/07 §7.15, mitigación 4)."""


@dataclass(slots=True, frozen=True)
class ChannelKey:
    """Identidad en capas de un canal (ADR-003, ADR-008).

    Al menos una de `rol`, `nativo` o `nombre_normalizado` debe estar
    presente; la resolución de "cuál gana" para mostrar y para agrupar
    detectores es el orden de §7.11, no un campo de esta clase.
    """

    rol: str | None
    formato: str | None
    id_nativo: str | None
    nombre_normalizado: str | None


@dataclass(slots=True, frozen=True)
class Rol:
    """Entrada del catálogo `roles.toml`: un rol semántico y sus sinónimos."""

    id: str
    dimension: str | None
    sinonimos: tuple[str, ...]
    plausible_min: float | None = None
    plausible_max: float | None = None
    indexado: bool = False
    monotono: str | None = None
    critico: bool = False

    def es_plausible(self, valor: float) -> bool:
        """¿Cae `valor` (en unidad CANÓNICA) dentro del rango declarado?

        Los rangos de `data/roles.toml` son anchos a propósito: detectan un
        error de escala de uno o más órdenes de magnitud, no juzgan si un
        motor está bien afinado. Un rol sin rango declarado acepta todo.
        """
        if self.plausible_min is not None and valor < self.plausible_min:
            return False
        return not (self.plausible_max is not None and valor > self.plausible_max)


@dataclass(slots=True, frozen=True)
class Asignacion:
    """El resultado de asignar un rol a un nombre de canal."""

    rol: str
    confianza: Confianza
    sinonimo: str
    """El sinónimo del catálogo que disparó la asignación: es lo que se le
    enseña al usuario cuando tiene que confirmar una difusa."""

    indice: int | None = None
    """El número capturado por la marca `{n}`, si el sinónimo la tenía."""

    parecido: float = 1.0
    """1.0 en exacta e indexada; el ratio de `difflib` en las difusas."""

    @property
    def requiere_confirmacion(self) -> bool:
        """Mitigación 4 de §7.15: lo difuso no vale para detectores críticos
        hasta que una persona lo confirme."""
        return self.confianza is Confianza.DIFUSA


def normalizar(nombre: str) -> str:
    """Minúsculas, sin acentos y sin separadores (§7.7).

    `Régimen` -> `regimen`; `Engine Speed`, `EngineSpeed` y `engine_speed` ->
    `enginespeed`. Es lo que permite que el catálogo enumere significados y no
    variantes tipográficas.
    """
    sin_acentos = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return _SEPARADORES.sub("", sin_acentos).lower()


def cargar_catalogo_roles(fuente: IO[bytes]) -> dict[str, Rol]:
    """Carga el catálogo de roles desde `roles.toml` ya abierto por quien llama.

    Binario, no texto: `tomllib.load` lo exige (ver "CAMBIOS DE FIRMA" en la
    cabecera). La sección `[meta]` no es un rol y se ignora.
    """
    bruto = tomllib.load(fuente)
    catalogo: dict[str, Rol] = {}
    for id_, d in bruto.get("roles", {}).items():
        plausible = d.get("plausible", {})
        catalogo[id_] = Rol(
            id=id_,
            dimension=d.get("dimension"),
            sinonimos=tuple(str(s) for s in d.get("sinonimos", ())),
            plausible_min=_flotante_o_none(plausible.get("min")),
            plausible_max=_flotante_o_none(plausible.get("max")),
            indexado=bool(d.get("indexado", False)),
            monotono=d.get("monotono"),
            critico=bool(d.get("critico", False)),
        )
    return catalogo


def _flotante_o_none(valor: float | int | str | None) -> float | None:
    return None if valor is None else float(valor)


def _patron_indexado(sinonimo_bruto: str) -> re.Pattern[str] | None:
    """Convierte un sinónimo con `{n}` en una expresión que captura el índice.
    `None` si el sinónimo no lleva marca.

    Se parte por la marca ANTES de normalizar y se normaliza cada trozo por
    separado, no al revés: `normalizar` quita los separadores y entre ellos
    están las llaves, así que normalizar primero convertiría `{n}` en una `n`
    suelta y el patrón no distinguiría "Knock Sensor {n} Knock Count" de un
    canal que literalmente se llamara "Knock Sensor N Knock Count". El
    síntoma era que todos los canales indexados caían a coincidencia DIFUSA
    (con parecido alto, ~0,95, porque solo sobraba un carácter) en vez de
    INDEXADA, perdiendo el índice y marcando como "requiere confirmación"
    algo que el catálogo declara explícitamente.
    """
    if not _MARCA_INDICE.search(sinonimo_bruto):
        return None
    partes = [re.escape(normalizar(p)) for p in _MARCA_INDICE.split(sinonimo_bruto)]
    return re.compile("^" + r"(\d+)".join(partes) + "$")


def asignar_rol(
    nombre_canal: str,
    catalogo: dict[str, Rol],
    *,
    umbral_difuso: float = UMBRAL_DIFUSO_POR_OMISION,
) -> Asignacion | None:
    """Asigna un rol a `nombre_canal`, diciendo también cómo se decidió.

    Orden de intento (§7.7: sinónimos y normalización primero, difuso «como
    último recurso y siempre confirmado por el usuario»):

        1. Coincidencia exacta del nombre normalizado con un sinónimo.
        2. Coincidencia con un sinónimo con marca `{n}`, capturando el índice.
        3. Parecido por encima de `umbral_difuso`, marcado `DIFUSA`.

    Devuelve `None` si nada supera el umbral. El recorrido del catálogo es por
    ROL (unas decenas), no por muestra: ADR-009 no aplica aquí.
    """
    objetivo = normalizar(nombre_canal)
    if not objetivo:
        return None

    indexados: list[tuple[str, str, re.Pattern[str]]] = []
    candidatos_difusos: dict[str, tuple[str, str]] = {}

    for rol in catalogo.values():
        for sinonimo in rol.sinonimos:
            patron = _patron_indexado(sinonimo)
            if patron is not None:
                indexados.append((rol.id, sinonimo, patron))
                continue
            normalizado = normalizar(sinonimo)
            if normalizado == objetivo:
                return Asignacion(rol=rol.id, confianza=Confianza.EXACTA, sinonimo=sinonimo)
            candidatos_difusos.setdefault(normalizado, (rol.id, sinonimo))

    for rol_id, sinonimo, patron in indexados:
        coincidencia = patron.match(objetivo)
        if coincidencia is not None:
            return Asignacion(
                rol=rol_id,
                confianza=Confianza.INDEXADA,
                sinonimo=sinonimo,
                indice=int(coincidencia.group(1)),
            )

    parecidos = difflib.get_close_matches(objetivo, candidatos_difusos, n=1, cutoff=umbral_difuso)
    if not parecidos:
        return None
    rol_id, sinonimo = candidatos_difusos[parecidos[0]]
    return Asignacion(
        rol=rol_id,
        confianza=Confianza.DIFUSA,
        sinonimo=sinonimo,
        parecido=difflib.SequenceMatcher(None, objetivo, parecidos[0]).ratio(),
    )


def resolver_rol(nombre_canal: str, catalogo: dict[str, Rol]) -> str | None:
    """Atajo de `asignar_rol` que devuelve solo el identificador del rol.

    Para quien no necesita saber CÓMO se decidió. **No lo uses para decidir si
    un detector crítico puede activarse**: eso exige `Asignacion.confianza`
    (docs/07 §7.15, mitigación 4), que este atajo descarta por construcción.
    """
    asignacion = asignar_rol(nombre_canal, catalogo)
    return None if asignacion is None else asignacion.rol
