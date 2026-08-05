"""Preset de usuario: la pieza que falta para «el usuario puede crear el suyo».

`docs/06-sistema-de-unidades.md` §6.9, línea 194:

    «Un preset es un fichero de datos y el usuario puede crear el suyo. Cubrir
    el caso "tuner estadounidense que quiere psi, °F y AFR de un clic" con un
    preset, en lugar de con 20 selectores, es la diferencia entre una función
    usada y una función ignorada.»

Los cinco presets de fábrica (SI, Métrico, Imperial, Motorsport EU, Motorsport
US) viven en `data/units.toml [presets.*]` y ya están completos (F0-08); este
módulo no los toca ni añade presets de fábrica nuevos, ni datos de catálogo de
ningún tipo. Lo que faltaba, y que el párrafo de arriba promete, es la pieza
que permite que un tuner construya el suyo sin editar `units.toml`.

Un preset de usuario es, a propósito, la misma forma que
`resolucion_unidad.resolver_unidad` ya espera en su parámetro
`preferencias_perfil`: un `Mapping[str, str]` de `dimension_id -> unidad_id`.
`PresetUsuario` no inventa un tercer concepto que esa función tenga que
aprender a leer: es una etiqueta (nombre + validación + serialización) puesta
encima de la misma forma de datos. `PresetUsuario.a_mapeo()` se pasa
directamente como `preferencias_perfil` sin ninguna conversión intermedia, y
en esa precedencia gana al preset global pero pierde frente a una anulación de
canal explícita — exactamente como cualquier otra fuente de
`preferencias_perfil` (docs/06 §6.9).

`dlv-core` no toca el sistema de ficheros por su cuenta (ADR-002): la
(de)serialización de este módulo es solo a/desde estructuras en memoria
(`dict` / cadena JSON). El día que exista `.dlvprofile`
(`docs/03-arquitectura.md` §3.9), su capa de persistencia puede envolver
`a_dict()` / `desde_dict()` sin que este módulo cambie.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dlv_core.unidades import Catalogo, ErrorDeUnidad


@dataclass(slots=True, frozen=True)
class PresetUsuario:
    """Un preset de unidades definido por el usuario, no uno de fábrica.

    `unidades` tiene exactamente la forma que
    `resolucion_unidad.resolver_unidad` espera en `preferencias_perfil`:
    `dimension_id -> unidad_id`. No hay traducción que hacer entre ambos: es
    la misma forma de datos con una etiqueta encima.

    El constructor NO valida contra ningún catálogo: validar exige un
    `Catalogo` (para saber qué dimensiones y unidades existen de verdad), y
    este tipo tiene que poder representar también un preset ya validado que se
    reconstruye desde disco (p. ej. un futuro `.dlvprofile`) antes de que haya
    un catálogo a mano. Llama a `validar()` en cuanto tengas uno, o usa
    `crear_preset_usuario()`, que hace ambos pasos de una vez.
    """

    nombre: str
    unidades: Mapping[str, str]

    def validar(self, catalogo: Catalogo) -> None:
        """Comprueba el preset contra `catalogo`; lanza `ErrorDeUnidad` si algo no encaja.

        Reutiliza `Catalogo.dimension()` y `Dimension.unidad()` a propósito:
        los mensajes de error (dimensión desconocida, unidad no disponible)
        son exactamente los que ya lanza el resto del motor de unidades, no
        una validación paralela con su propio vocabulario y sus propios
        mensajes que mantener sincronizados.
        """
        if not self.nombre.strip():
            raise ErrorDeUnidad("un preset de usuario necesita un nombre no vacío")
        for dimension_id, id_unidad in self.unidades.items():
            dimension = catalogo.dimension(dimension_id)
            dimension.unidad(id_unidad)

    def a_mapeo(self) -> Mapping[str, str]:
        """La forma exacta que espera `resolver_unidad(..., preferencias_perfil=...)`.

        No hay conversión: este preset YA ES esa forma. El método existe para
        que quien lo llama no tenga que saber que `unidades` es públicamente
        el mismo campo.
        """
        return self.unidades

    def a_dict(self) -> dict[str, Any]:
        """Serializa a un `dict` plano, listo para JSON o para un `.dlvprofile` futuro."""
        return {"nombre": self.nombre, "unidades": dict(self.unidades)}

    def a_json(self) -> str:
        """Serializa a JSON. `desde_json` es su inversa exacta."""
        return json.dumps(self.a_dict(), ensure_ascii=False, sort_keys=True)

    @staticmethod
    def desde_dict(bruto: Mapping[str, Any]) -> PresetUsuario:
        """Reconstruye un `PresetUsuario` desde la forma de `a_dict()`.

        No valida contra ningún catálogo (ver la nota del constructor): llama a
        `validar()` después si el catálogo puede haber cambiado desde que se
        guardó el preset.
        """
        try:
            nombre = bruto["nombre"]
            unidades_brutas = bruto["unidades"]
        except KeyError as exc:
            raise ErrorDeUnidad(f"preset de usuario incompleto: falta la clave {exc}") from None
        if not isinstance(unidades_brutas, Mapping):
            raise ErrorDeUnidad(
                "preset de usuario: 'unidades' debe ser un mapeo dimension_id -> unidad_id"
            )
        unidades = {str(clave): str(valor) for clave, valor in unidades_brutas.items()}
        return PresetUsuario(nombre=str(nombre), unidades=unidades)

    @staticmethod
    def desde_json(texto: str) -> PresetUsuario:
        """Reconstruye un `PresetUsuario` desde la forma de `a_json()`."""
        try:
            bruto = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise ErrorDeUnidad(f"preset de usuario: JSON inválido: {exc}") from None
        if not isinstance(bruto, Mapping):
            raise ErrorDeUnidad("preset de usuario: la raíz del JSON debe ser un objeto")
        return PresetUsuario.desde_dict(bruto)


def crear_preset_usuario(
    nombre: str, unidades: Mapping[str, str], *, catalogo: Catalogo
) -> PresetUsuario:
    """Construye y valida un `PresetUsuario` en un solo paso.

    Es el camino recomendado al crear un preset nuevo desde la interfaz —a
    diferencia de `PresetUsuario.desde_dict` / `desde_json`, pensados para
    reconstruir uno que ya se guardó y que puede validarse por separado.
    """
    preset = PresetUsuario(nombre=nombre, unidades=dict(unidades))
    preset.validar(catalogo)
    return preset
