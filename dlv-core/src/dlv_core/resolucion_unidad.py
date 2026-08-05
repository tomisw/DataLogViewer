"""Precedencia de unidad activa por canal (tarea F1-17).

`docs/06-sistema-de-unidades.md` §6.9 fija, de más a menos específico:

    1. Anulación por canal    — «este canal en psi aunque el resto esté en bar».
    2. Dimensión del perfil   — el perfil «Boost» puede fijar psi para toda la
       dimensión `pressure`, sin tocar canal por canal.
    3. Preset global          — `data/units.toml [presets.*]`, vía `Catalogo`.
    4. Unidad canónica        — último recurso, siempre existe.

Este módulo no decide NADA de datos: resuelve qué `Unidad` usar para pintar un
canal, dada la configuración activa. La conversión propiamente dicha sigue
siendo `unidades.desde_canonica` / `a_canonica`; aquí solo se elige el
parámetro `unidad` que se les pasa.

DECISIONES DE DISEÑO — capas que aún no existen en el resto del código
========================================================================
`F3-01` (perfiles de usuario) y la resolución completa de identidad de canal de
`roles.ChannelKey` son trabajo futuro, hoy sin implementar. Para no bloquear
esta pieza en ese trabajo pendiente:

- El **perfil activo** se modela como la interfaz mínima que necesita: un
  `Mapping[str, str]` de `dimension_id -> unidad_id` («las preferencias de
  unidad del perfil activo»). Cuando exista un modelo de perfil de verdad
  (F3-01), su capa de dimensiones puede pasarse aquí tal cual, o adaptarse con
  una función trivial; esta función no necesita saber nada más del perfil.
- La **anulación de canal** se modela como un `str | None`: el id (o alias) de
  unidad ya resuelto por quien llama para ESE canal exacto. No se pide aquí un
  `ChannelKey` completo porque `roles.py` es hoy un STUB sin resolución real
  (`resolver_rol` y `cargar_catalogo_roles` lanzan `NotImplementedError`); la
  llamada típica es «busca en tu `Mapping[ChannelKey, str]` de anulaciones y
  pásame el resultado», y eso es responsabilidad de quien orquesta canales, no
  de esta función de precedencia.

El resultado no es solo la unidad: es también la capa que ganó
(`UnidadResuelta.capa`), porque la interfaz necesita poder explicar «psi
porque el canal de boost tiene una anulación» en vez de un selector mudo.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from dlv_core.unidades import Catalogo, ErrorDeUnidad, Unidad


class Capa(Enum):
    """Nivel de precedencia por el que se decidió la unidad activa (§6.9).

    El orden de los miembros no importa para la lógica —la precedencia la fija
    `resolver_unidad`, no el `Enum`—, pero sí para la lectura: de más a menos
    específico.
    """

    CANAL = "canal"
    """Anulación explícita para este canal exacto. Gana siempre."""

    PERFIL = "perfil"
    """Preferencia de unidad para la dimensión, del perfil activo."""

    PRESET = "preset"
    """Preset global del usuario (`data/units.toml [presets.*]`)."""

    CANONICA = "canonica"
    """Ninguna capa más específica aplica: se usa la unidad canónica."""


_EXPLICACION_POR_CAPA: Mapping[Capa, str] = {
    Capa.CANAL: "anulación explícita de unidad para este canal",
    Capa.PERFIL: "preferencia de unidad de la dimensión en el perfil activo",
    Capa.PRESET: "preset global activo",
    Capa.CANONICA: "unidad canónica de la dimensión: no hay ninguna capa más específica",
}


@dataclass(slots=True, frozen=True)
class UnidadResuelta:
    """La unidad activa para un canal, y por qué capa se decidió.

    `capa` es lo que permite a la interfaz mostrar de dónde viene la unidad
    activa —útil tanto para depurar como para un tooltip «por qué psi»— sin
    tener que repetir la cadena de precedencia en cada sitio que lo pregunte.
    """

    unidad: Unidad
    capa: Capa
    dimension_id: str

    @property
    def explicacion(self) -> str:
        """Texto en español, listo para depuración o para la interfaz."""
        return _EXPLICACION_POR_CAPA[self.capa]


def resolver_unidad(
    dimension_id: str,
    *,
    catalogo: Catalogo,
    preset: str | None = None,
    preferencias_perfil: Mapping[str, str] | None = None,
    anulacion_canal: str | None = None,
) -> UnidadResuelta:
    """Resuelve qué `Unidad` usar para un canal de la dimensión `dimension_id`.

    Precedencia, de mayor a menor (§6.9):

    1. `anulacion_canal` — si se da, gana siempre, sea cual sea el resto.
    2. `preferencias_perfil[dimension_id]` — si el perfil activo fija una
       unidad para esta dimensión.
    3. El preset (`preset`, o el preset por omisión del catálogo si no se pasa
       ninguno) — si ese preset declara una unidad para esta dimensión. No
       todos los presets cubren todas las dimensiones (p. ej. `si`, `metrico`
       e `imperial` no fijan `angle`): cuando falta, se cae al nivel 4.
    4. La unidad canónica de la dimensión — siempre existe, es el suelo de la
       precedencia.

    `preset=None` no significa «sin preset»: significa «el preset activo del
    usuario no se ha pasado explícito, usa el marcado `por_omision` en el
    catálogo», porque en la práctica siempre hay un preset global vigente.

    Lanza `ErrorDeUnidad` si `dimension_id` es desconocida, si `preset` no
    nombra un preset del catálogo, o si `anulacion_canal` /
    `preferencias_perfil[dimension_id]` / la unidad del preset no son una
    unidad (o alias) válida de la dimensión — los mismos errores, con el mismo
    mensaje, que lanzaría `Dimension.unidad` directamente.
    """
    dimension = catalogo.dimension(dimension_id)

    if anulacion_canal is not None:
        return UnidadResuelta(dimension.unidad(anulacion_canal), Capa.CANAL, dimension_id)

    if preferencias_perfil is not None and dimension_id in preferencias_perfil:
        id_unidad_perfil = preferencias_perfil[dimension_id]
        return UnidadResuelta(dimension.unidad(id_unidad_perfil), Capa.PERFIL, dimension_id)

    nombre_preset = preset if preset is not None else catalogo.preset_por_omision
    try:
        entrada_preset: Mapping[str, object] = catalogo.presets[nombre_preset]
    except KeyError:
        raise ErrorDeUnidad(f"preset desconocido: '{nombre_preset}'") from None
    id_unidad_preset = entrada_preset.get(dimension_id)
    if id_unidad_preset is not None:
        return UnidadResuelta(dimension.unidad(str(id_unidad_preset)), Capa.PRESET, dimension_id)

    return UnidadResuelta(dimension.unidad(dimension.unidad_canonica), Capa.CANONICA, dimension_id)
