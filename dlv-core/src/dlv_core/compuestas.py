"""Dimensiones compuestas derivadas (tarea F1-16, `docs/06` §6.7).

Los tipos `PercentPerRpm`, `PercentPerKPa` y `PercentPerLambda` del formato
Haltech son **cocientes de dimensiones**, no dimensiones propias. Su unidad
mostrada se **deriva** de las unidades activas del numerador y del
denominador: si el usuario pone la presión en psi, `%/kPa` pasa a mostrarse
como `%/psi` con el factor recalculado. Fijarlas a mano produciría
incoherencias dentro del mismo panel -- el eje de presión en psi y la
pendiente por kPa, en el mismo gráfico.

Las compuestas son datos (`data/units.toml [compuestas.*]`, cada una con
`numerador`, `denominador` y `etiqueta`), no una tabla en el código.

LA ARITMÉTICA, Y POR QUÉ NO ES `a_num * a_den`
===============================================
Un valor compuesto en canónica es `Δnumerador_canónico / Δdenominador_
canónico`. Al pasar el numerador a su unidad activa se multiplica por
`a_num`, y al pasar el denominador a la suya, el propio denominador se
multiplica por `a_den` -- pero está DIVIDIENDO, así que el cociente se
multiplica por `1/a_den`:

    mostrado = (a_num * Δnum) / (a_den * Δden) = (a_num / a_den) * canónico

De ahí que el factor derivado sea `a_num / a_den` y no el producto. El error
de signo aquí (multiplicar en vez de dividir) da un número con la forma
correcta y la magnitud equivocada, que es exactamente la clase de fallo que
llega a una decisión de tuning sin que nadie lo note: 14,5 veces de más en
`%/psi` en vez de 14,5 veces de menos.

Solo se usa la parte LINEAL (`a`), nunca el desplazamiento `b`: una
pendiente "por grado" vale lo mismo en °C que en K, igual que un intervalo.
Es la misma regla que `Clase.TASA` de `unidades.py` (F1-13) aplica al
numerador; esta tarea la completa añadiendo el denominador, que `Clase.TASA`
por sí sola no puede conocer.

QUÉ NO SE DERIVA
================
Si el numerador o el denominador usan una conversión que no es afín
—`Reciproca` (λ -> φ) o `Parametrizada` (λ -> AFR)—, el cociente **no** es un
factor constante y no se puede derivar así. Se rechaza con `ErrorDeUnidad`
explícito en vez de devolver un número plausible: `pct_per_lambda` mostrado
"por φ" no es la pendiente escalada, es otra función.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import IO, Any

from dlv_core.unidades import Afin, Catalogo, ErrorDeUnidad

__all__ = [
    "Compuesta",
    "UnidadCompuesta",
    "cargar_compuestas",
    "derivar_unidad_compuesta",
]


@dataclass(slots=True, frozen=True)
class Compuesta:
    """Una entrada de `data/units.toml [compuestas.*]`."""

    id: str
    numerador: str
    denominador: str
    etiqueta: str


@dataclass(slots=True, frozen=True)
class UnidadCompuesta:
    """El resultado de derivar: cómo mostrar y con qué factor convertir."""

    etiqueta: str
    """Etiqueta derivada de las unidades activas, p. ej. `%/psi`."""

    factor: float
    """`a_num / a_den`: multiplica el valor canónico para obtener el mostrado."""

    unidad_numerador: str
    unidad_denominador: str

    def desde_canonica(self, valores: Any) -> Any:
        """Canónica -> unidad compuesta mostrada. Vectorizado si `valores` es
        un array (la misma aritmética escalar vale para un `ndarray`, ADR-009).

        No hay parámetro `clase`: una dimensión compuesta ES una tasa, así que
        la única clase que le aplica es la lineal. No hay un "punto" de una
        pendiente al que se le pudiera sumar un desplazamiento.
        """
        return valores * self.factor

    def a_canonica(self, valores: Any) -> Any:
        """Inversa exacta de `desde_canonica`."""
        return valores / self.factor


def cargar_compuestas(fuente: IO[bytes]) -> Mapping[str, Compuesta]:
    """Carga la sección `[compuestas.*]` de `data/units.toml` ya abierto.

    Va aparte de `unidades.cargar_catalogo` a propósito: `Catalogo` describe
    dimensiones simples y no debería crecer un concepto nuevo por una tarea
    posterior. Quien necesite las dos cosas abre el fichero dos veces o pasa
    el mismo contenido.
    """
    bruto = tomllib.load(fuente)
    compuestas: dict[str, Compuesta] = {}
    for id_, d in bruto.get("compuestas", {}).items():
        compuestas[id_] = Compuesta(
            id=id_,
            numerador=str(d["numerador"]),
            denominador=str(d["denominador"]),
            etiqueta=str(d.get("etiqueta", id_)),
        )
    return compuestas


def _factor_lineal(catalogo: Catalogo, dimension_id: str, unidad_id: str, papel: str) -> float:
    """La parte lineal `a` de la conversión de una unidad, o un error claro si
    esa conversión no es afín (ver "QUÉ NO SE DERIVA" en la cabecera)."""
    dimension = catalogo.dimension(dimension_id)
    unidad = dimension.unidad(unidad_id)
    conversion = unidad.conversion
    if not isinstance(conversion, Afin):
        raise ErrorDeUnidad(
            f"la unidad '{unidad_id}' de la dimensión '{dimension_id}' ({papel} de una "
            f"dimensión compuesta) usa una conversión {type(conversion).__name__}, no afín: "
            "el cociente no es un factor constante y no se puede derivar"
        )
    return conversion.a


def derivar_unidad_compuesta(
    compuesta: Compuesta,
    *,
    catalogo: Catalogo,
    unidad_numerador: str,
    unidad_denominador: str,
) -> UnidadCompuesta:
    """Deriva la unidad mostrada de `compuesta` a partir de las unidades
    activas de su numerador y su denominador.

    Quien llama obtiene esas dos unidades activas de la precedencia de F1-17
    (`resolucion_unidad.resolver_unidad`), una por dimensión: así el `%/psi`
    del panel sale de la MISMA decisión que puso el eje de presión en psi, y
    no pueden discrepar.
    """
    a_num = _factor_lineal(catalogo, compuesta.numerador, unidad_numerador, "numerador")
    a_den = _factor_lineal(catalogo, compuesta.denominador, unidad_denominador, "denominador")

    etiqueta_num = catalogo.dimension(compuesta.numerador).unidad(unidad_numerador).etiqueta
    etiqueta_den = catalogo.dimension(compuesta.denominador).unidad(unidad_denominador).etiqueta

    return UnidadCompuesta(
        etiqueta=f"{etiqueta_num}/{etiqueta_den}",
        factor=a_num / a_den,
        unidad_numerador=unidad_numerador,
        unidad_denominador=unidad_denominador,
    )
