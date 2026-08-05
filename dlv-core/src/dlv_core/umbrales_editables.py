"""Umbrales en canónica, editados en la unidad activa (tarea F1-19).

`docs/06-sistema-de-unidades.md` §6.11: «Umbrales y alertas: se guardan en
canónica y se editan en la unidad activa; el campo de entrada muestra la
unidad junto al valor». Y la consecuencia que lo hace valioso, del mismo
documento: cambiar de unidad es **un repintado, no una reescritura** -- no
invalida la caché ni toca ningún umbral guardado.

`data/umbrales.toml` ya está escrito así ("Todos los valores están en unidad
canónica... es lo que permite editarlos en la unidad que el usuario tenga
activa sin reescribir nada"). Lo que faltaba es el par de funciones que
cruzan esa frontera en los dos sentidos, sin que quien las use tenga que
acordarse de la clase de magnitud ni de los decimales.

POR QUÉ `clase` ES OBLIGATORIA AQUÍ TAMBIÉN
============================================
Un umbral puede ser un PUNTO ("temperatura por encima de 373,15 K") o un
INTERVALO ("una subida de más de 10 K"). Editar el segundo como si fuera el
primero convierte "10 K de subida" en "−263,15 °C", que es la trampa del
delta de `unidades.py` (F1-13) llegando por otra puerta: el campo de
edición. Por eso `clase` no tiene valor por omisión, igual que en el motor
de conversión.

UMBRALES ADIMENSIONALES
=======================
Varios valores de `data/umbrales.toml` no tienen dimensión: `permanencia_s`
es tiempo (sí la tiene), pero `histeresis_relativa`, `delta_minimo` de un
contador o `muestras_minimas` son números puros. Para esos, `dimension` es
`None` y no se convierte nada -- pero se sigue formateando, porque el campo
de edición los muestra igual.
"""

from __future__ import annotations

from dataclasses import dataclass

from dlv_core.unidades import (
    Catalogo,
    Clase,
    Dimension,
    a_canonica,
    desde_canonica,
    etiqueta_de,
)

__all__ = ["UmbralEditable", "desde_edicion", "para_edicion"]


@dataclass(slots=True, frozen=True)
class UmbralEditable:
    """Un umbral tal como se presenta en el campo de edición.

    `valor` está en la unidad activa; `canonico` es lo que sigue guardado sin
    tocar. Llevar los dos juntos es lo que permite a la interfaz mostrar el
    número editable y, a la vez, no perder de vista que lo persistido es
    otra cosa.
    """

    valor: float
    etiqueta_unidad: str
    decimales: int
    canonico: float

    def formateado(self) -> str:
        """El texto del campo: valor con sus decimales y la unidad al lado.

        Los decimales salen de `data/units.toml` (docs/06 §6.10): mostrar
        `λ 0,995` con un decimal (`1,0`) destruye la información. El
        separador decimal es el del locale de la interfaz, no cosa de este
        módulo (docs/06 §6.10 lo remite a la capa de presentación).
        """
        return f"{self.valor:.{self.decimales}f} {self.etiqueta_unidad}".strip()


def _dimension_y_unidad(
    catalogo: Catalogo, dimension_id: str | None, unidad_id: str | None
) -> tuple[Dimension, str] | None:
    """`None` para un umbral adimensional (ver cabecera del módulo)."""
    if dimension_id is None or unidad_id is None:
        return None
    return catalogo.dimension(dimension_id), unidad_id


def para_edicion(
    canonico: float,
    *,
    catalogo: Catalogo,
    clase: Clase,
    dimension_id: str | None = None,
    unidad_id: str | None = None,
    referencia_kpa: float | None = None,
    decimales_sin_dimension: int = 3,
) -> UmbralEditable:
    """Canónica -> lo que ve el usuario en el campo de edición.

    `referencia_kpa` (de `presion_referencia.resolver_referencia`, F1-15)
    pasa un umbral de presión a relativo, para que "1,2 bar de boost" se
    edite como 1,2 y no como 202,5 kPa absolutos. Solo se aplica a los
    PUNTOS, como en el resto del sistema.
    """
    par = _dimension_y_unidad(catalogo, dimension_id, unidad_id)
    if par is None:
        return UmbralEditable(
            valor=canonico,
            etiqueta_unidad="",
            decimales=decimales_sin_dimension,
            canonico=canonico,
        )

    dimension, unidad_id_real = par
    valor = desde_canonica(
        canonico,
        dimension=dimension,
        unidad=unidad_id_real,
        clase=clase,
        referencia_kpa=referencia_kpa,
    )
    unidad = dimension.unidad(unidad_id_real)
    return UmbralEditable(
        valor=float(valor),
        etiqueta_unidad=etiqueta_de(dimension, unidad_id_real, relativa=referencia_kpa is not None),
        decimales=unidad.decimales,
        canonico=canonico,
    )


def desde_edicion(
    valor_editado: float,
    *,
    catalogo: Catalogo,
    clase: Clase,
    dimension_id: str | None = None,
    unidad_id: str | None = None,
    referencia_kpa: float | None = None,
) -> float:
    """Lo que el usuario acaba de escribir -> canónica, para guardarlo.

    Inversa exacta de `para_edicion` con los mismos argumentos: es la
    propiedad que hace que abrir el editor y cerrarlo sin tocar nada no
    cambie el fichero de umbrales (docs/06 §6.12 pide ida y vuelta con error
    menor que 1 ULP para todas las unidades del catálogo).
    """
    par = _dimension_y_unidad(catalogo, dimension_id, unidad_id)
    if par is None:
        return valor_editado

    dimension, unidad_id_real = par
    return float(
        a_canonica(
            valor_editado,
            dimension=dimension,
            unidad=unidad_id_real,
            clase=clase,
            referencia_kpa=referencia_kpa,
        )
    )
