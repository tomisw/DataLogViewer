"""Marcha estimada por agrupación de velocidad/régimen (tarea F3-20).

Especificación: `docs/04-perfiles-motorsport.md` §4.5, fila «Marcha estimada»:
«agrupación de `{Vehicle Speed}/{RPM}`; no existe canal `Gear` en el log».

POR QUÉ FUNCIONA, Y CUÁNDO NO
=============================
Con el embrague cerrado, el cociente velocidad/régimen es una CONSTANTE de la
marcha: sale de la relación de la caja por el grupo final por el desarrollo del
neumático, y ninguno de los tres cambia mientras se conduce. Así que las marchas
aparecen como acumulaciones estrechas en el histograma del cociente.

Deja de funcionar en tres situaciones, y las tres se excluyen antes de agrupar en
vez de dejar que ensanchen las acumulaciones:

  - **embrague abierto o coche parado**: el cociente no significa nada, y con el
    coche quieto es 0 o una división por casi cero;
  - **cambio de marcha**: el cociente pasa por todos los valores intermedios;
  - **patinada o bloqueo**: la rueda no sigue al motor.

Lo que sobra de esos tres casos NO se fuerza a una marcha: se queda sin asignar,
con su motivo. Una marcha inventada en medio de un cambio es peor que un hueco,
porque los detectores que la usen como contexto la creerán.

LO QUE ESTE MÓDULO NO PUEDE DECIR: QUÉ MARCHA ES
================================================
Puede decir «aquí hay cuatro marchas distintas y esta es la segunda más corta»,
pero no que sea la segunda del coche. Si el conductor no usó la primera en todo el
log, la más corta observada es la segunda. Numerarlas como si fueran absolutas es
inventar, así que `MarchaDetectada.indice` es **ordinal entre las observadas** y
lo dice su docstring.

Lo que sí puede darse, y es lo que permite comprobarlo contra una caja de verdad,
son las SEPARACIONES entre acumulaciones consecutivas: son las relaciones de la
caja, independientes del grupo final y del neumático. Sobre el AutoLog real salen
1,660, 1,500 y 1,316, y la caja de un R33 GTR da 3,214/1,925 = 1,670,
1,925/1,302 = 1,479 y 1,302/1,000 = 1,302. Cuadran al 1,5 %, o sea que las cuatro
acumulaciones son 1ª, 2ª, 3ª y 4ª. Ese cotejo es del propietario, no del módulo:
`informe.separaciones` se lo pone delante y él lo confronta con su caja.

ADR-009
=======
El histograma es un `bincount`, la detección de máximos una comparación con los
vecinos por rodajas, y la asignación un `searchsorted` contra los centros. Cero
bucles por muestra. Hay un bucle sobre las MARCHAS al fusionar centros próximos,
acotado por `marchas_maximas`: es el mismo criterio con el que `primitivas.py`
acota su único bucle, porque su coste no depende del número de muestras.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from itertools import pairwise
from typing import Any, Protocol, cast

from dlv_core.primitivas import Serie, alinear
from dlv_core.primitivas import Vectorial as VectorialDePrimitivas
from dlv_core.unidades import Clase

__all__ = [
    "ErrorDeMarcha",
    "InformeDeMarchas",
    "MarchaDetectada",
    "MotivoSinMarcha",
    "UmbralesDeMarcha",
    "detectar_marchas",
]


class Vectorial(VectorialDePrimitivas, Protocol):
    """Lo que `primitivas` declara, más el `bincount` que la agrupación necesita.

    Se EXTIENDE en vez de redeclararse porque este módulo llama a
    `primitivas.alinear` y tiene que poder pasarle su mismo `xp`. Y se extiende en
    vez de añadir `bincount` a `primitivas.Vectorial` porque ese módulo no lo usa:
    la regla del patrón es que cada protocolo declare solo lo que su dueño
    necesita, y `numpy` satisface todos por ser estructurales.

    Los cinco `Vectorial` del paquete (`expresiones`, `malla`, `plausibilidad`,
    `primitivas`, `reloj`) no son una duplicación por descuido: son cinco contratos
    mínimos distintos. Lo que sí obliga esta composición es que dos módulos que se
    llaman entre sí compartan la raíz, y de ahí la herencia.
    """

    def bincount(self, x: Any, weights: Any, minlength: int, /) -> Any: ...


class ErrorDeMarcha(ValueError):
    """La agrupación no se puede hacer sin inventar algo."""


class MotivoSinMarcha(Enum):
    """Por qué una muestra no tiene marcha. Nunca se deja sin explicar.

    Un canal de marcha con huecos y sin motivo es indistinguible de un canal roto,
    y quien lo pinte no puede decidir si dibujar un hueco o avisar.
    """

    PARADO_O_EMBRAGUE = "parado_o_embrague"
    """Por debajo del régimen o de la velocidad mínimos: el cociente no significa
    nada. Cubre el coche quieto, el ralentí en punto muerto y el embrague abierto."""

    ENTRE_MARCHAS = "entre_marchas"
    """El cociente cae fuera de la tolerancia de cualquier acumulación: un cambio
    en curso, una patinada o un bloqueo de rueda."""

    SIN_DATOS = "sin_datos"
    """Falta el régimen o la velocidad en ese instante, o el valor retenido del
    canal más lento ya ha caducado (`ventana_validez_ms`)."""


@dataclass(slots=True, frozen=True)
class UmbralesDeMarcha:
    """Los umbrales de la agrupación. **Sin valores por omisión en el código.**

    Regla 3 de `CLAUDE.md`: viven en `data/umbrales.toml`, sección `[marcha]`, con
    la precedencia de siempre. `desde_mapa` exige todas las claves y falla si
    falta alguna, porque un valor por omisión en el código es una copia del
    fichero que puede desincronizarse sin que nada se ponga en rojo.
    """

    rpm_minimo: float
    velocidad_minima_kmh: float
    ancho_de_celda: float
    """Anchura de la celda del histograma, en km/h por 1000 rpm."""
    muestras_minimas_por_marcha: int
    tolerancia_relativa: float
    """Cuánto puede alejarse el cociente de un centro y seguir siendo esa marcha,
    en fracción del centro."""
    separacion_minima_relativa: float
    """Dos centros más próximos que esto son la misma marcha vista dos veces."""
    marchas_maximas: int
    """Tope de acumulaciones. Acota el único bucle del módulo y convierte «los
    umbrales generan ruido» en un error explicado en vez de en 200 marchas."""
    ventana_validez_ms: float
    """Para alinear los dos canales cuando van a tasas distintas. Sale de
    `[motor_de_deteccion]`, no de `[marcha]`: es una propiedad del muestreo."""

    CLAVES = (
        "rpm_minimo",
        "velocidad_minima_kmh",
        "ancho_de_celda",
        "muestras_minimas_por_marcha",
        "tolerancia_relativa",
        "separacion_minima_relativa",
        "marchas_maximas",
        "ventana_validez_ms",
    )

    @classmethod
    def desde_mapa(cls, mapa: Mapping[str, Any]) -> UmbralesDeMarcha:
        faltan = [c for c in cls.CLAVES if c not in mapa]
        if faltan:
            raise ErrorDeMarcha(
                f"data/umbrales.toml no declara: {', '.join(faltan)}; son umbrales "
                "configurables y este módulo no lleva copia de ellos ([marcha] da los "
                "suyos y [motor_de_deteccion] la ventana de validez)"
            )
        u = cls(
            rpm_minimo=float(mapa["rpm_minimo"]),
            velocidad_minima_kmh=float(mapa["velocidad_minima_kmh"]),
            ancho_de_celda=float(mapa["ancho_de_celda"]),
            muestras_minimas_por_marcha=int(mapa["muestras_minimas_por_marcha"]),
            tolerancia_relativa=float(mapa["tolerancia_relativa"]),
            separacion_minima_relativa=float(mapa["separacion_minima_relativa"]),
            marchas_maximas=int(mapa["marchas_maximas"]),
            ventana_validez_ms=float(mapa["ventana_validez_ms"]),
        )
        u.validar()
        return u

    def validar(self) -> None:
        if self.ancho_de_celda <= 0.0:
            raise ErrorDeMarcha("ancho_de_celda tiene que ser positivo")
        if self.muestras_minimas_por_marcha < 1:
            raise ErrorDeMarcha("muestras_minimas_por_marcha tiene que ser al menos 1")
        if self.marchas_maximas < 1:
            raise ErrorDeMarcha("marchas_maximas tiene que ser al menos 1")
        if not 0.0 < self.tolerancia_relativa < 1.0:
            raise ErrorDeMarcha(
                f"tolerancia_relativa = {self.tolerancia_relativa!r} tiene que estar entre 0 y 1; "
                "con 0 ninguna muestra se asignaría y con 1 todas caerían en la primera marcha"
            )
        if self.separacion_minima_relativa <= self.tolerancia_relativa:
            # Si dos centros pueden estar más juntos que la tolerancia, sus bandas
            # se solapan y una muestra pertenecería a dos marchas.
            raise ErrorDeMarcha(
                f"separacion_minima_relativa ({self.separacion_minima_relativa!r}) tiene que ser "
                f"mayor que tolerancia_relativa ({self.tolerancia_relativa!r}), o las bandas de "
                "dos marchas consecutivas se solaparían"
            )


@dataclass(slots=True, frozen=True)
class MarchaDetectada:
    indice: int
    """ORDINAL entre las marchas observadas, de la más corta a la más larga,
    empezando en 1. **No es el número de marcha del coche**: si el conductor no
    usó la primera, la más corta de este log es la segunda del cambio. Ver la
    cabecera del módulo."""

    cociente: float
    """Centro de la acumulación, en km/h por 1000 rpm. Es velocidad entre régimen,
    o sea una TASA y no un punto: quien lo convierta a otra unidad tiene que
    declarar `Clase.TASA`."""

    n_muestras: int
    fraccion: float
    """Parte del log útil que se pasó en esta marcha."""


@dataclass(slots=True, frozen=True)
class InformeDeMarchas:
    marchas: tuple[MarchaDetectada, ...]
    motivos: Mapping[MotivoSinMarcha, int]
    n_utiles: int
    """Muestras que entraron en la agrupación, tras excluir las de
    `PARADO_O_EMBRAGUE` y `SIN_DATOS`."""

    indice_por_muestra: Any = field(repr=False)
    """Para cada muestra de la rejilla, el `indice` de su marcha, o 0 si no tiene.
    Es lo que consume un carril de estado (F3-13); 0 y no −1 porque los índices
    empiezan en 1 y así el 0 significa «sin marcha» sin necesidad de un centinela."""

    @property
    def separaciones(self) -> tuple[float, ...]:
        """Cociente entre marchas consecutivas, de la más corta a la más larga.

        Son las relaciones de la caja, y son independientes del grupo final y del
        desarrollo del neumático: los dos se cancelan al dividir. Es lo único de
        este informe que se puede confrontar con una ficha técnica, y por eso está
        aquí y no calculado por quien llame.
        """
        cs = [m.cociente for m in self.marchas]
        return tuple(b / a for a, b in pairwise(cs))

    @property
    def fraccion_asignada(self) -> float:
        if self.n_utiles == 0:
            return 0.0
        return sum(m.n_muestras for m in self.marchas) / self.n_utiles


def _xp(xp: Vectorial | None) -> Vectorial:
    """El doble inyectado, o NumPy. Mismo criterio que `segmentacion.py`."""
    if xp is not None:
        return xp
    import numpy

    return cast("Vectorial", numpy)


#: Auxiliares vectoriales. Existen para que el cuerpo del módulo no tenga una sola
#: comprensión sobre las muestras: todas trabajan sobre el array completo y sirven
#: igual a NumPy que al doble de biblioteca estándar de las pruebas.


def _unos(n: int, x: Vectorial) -> Any:
    """Un array de unos de longitud `n`, construido sin recorrer nada.

    `bincount` con `minlength = n` y todos los índices distintos da exactamente
    eso, y evita tener que añadir `ones` al Protocol por un solo uso.
    """
    return x.bincount(list(range(n)), None, n)


def _suma(a: Any, x: Vectorial) -> float:
    """Suma total. El Protocol no declara `sum`, pero `cumsum` acaba en ella."""
    acumulado = x.cumsum(a)
    return float(acumulado[-1]) if len(acumulado) else 0.0


def _indicador(mascara: Any, x: Vectorial) -> Any:
    """Booleanos -> 1,0 y 0,0, para poder multiplicarlos como pesos."""
    return mascara * 1.0


def _a_entero(a: Any, x: Vectorial) -> Any:
    """Flotantes 0,0/1,0 -> enteros 0/1, para multiplicar índices sin sacar decimales."""
    return a * 1


def _como_flotante(valido: Any, n: int, x: Vectorial) -> Any:
    """La máscara de validez de una `Serie` como pesos, o todo unos si no la trae."""
    if valido is None:
        return _unos(n, x)
    return _indicador(valido, x)


def _centros_de_las_cimas(
    cuentas: Any, umbrales: UmbralesDeMarcha, xp: Vectorial
) -> list[tuple[int, int]]:
    """Celdas del histograma que son cima y llegan al mínimo de muestras.

    Cima es «no menor que sus dos vecinas»: se compara por rodajas, sin recorrer
    nada muestra a muestra. Se admite el empate (`>=`) a propósito, porque una
    acumulación puede repartirse entre dos celdas contiguas con la misma cuenta y
    descartar las dos dejaría la marcha sin detectar; el solape lo resuelve
    después la fusión por `separacion_minima_relativa`.
    """
    n = len(cuentas)
    if n == 0:
        return []
    interior_ok = [
        i
        for i in range(n)
        if cuentas[i] >= umbrales.muestras_minimas_por_marcha
        and cuentas[i] >= (cuentas[i - 1] if i > 0 else 0)
        and cuentas[i] >= (cuentas[i + 1] if i + 1 < n else 0)
    ]
    return [(i, int(cuentas[i])) for i in interior_ok]


def detectar_marchas(
    regimen: Serie,
    velocidad: Serie,
    *,
    umbrales: UmbralesDeMarcha,
    xp: Vectorial | None = None,
) -> InformeDeMarchas:
    """Agrupa el cociente velocidad/régimen y devuelve las marchas observadas.

    `regimen` en rpm canónicos y `velocidad` en km/h canónicos, los dos como
    `Clase.PUNTO`. Si van a tasas distintas se alinean por retención con la
    ventana de validez de `[motor_de_deteccion]`: un valor retenido más allá de
    esa ventana es un hueco, no un dato (`docs/04` §4.5).
    """
    x = _xp(xp)
    if regimen.clase is not Clase.PUNTO or velocidad.clase is not Clase.PUNTO:
        raise ErrorDeMarcha(
            "el régimen y la velocidad son PUNTOS; el cociente que sale de ellos es una "
            "TASA, y esa clase la lleva `MarchaDetectada.cociente`"
        )

    # La rejilla es la del régimen: es el canal rápido en los tres logs reales, y
    # tomar la del más lento perdería resolución en los cambios de marcha, que es
    # justo donde el cociente se mueve deprisa.
    vel = velocidad
    if len(velocidad.t_ms) != len(regimen.t_ms):
        vel = alinear(velocidad, regimen.t_ms, ventana_validez_ms=umbrales.ventana_validez_ms, xp=x)

    v = vel.v
    r = regimen.v
    n = len(r)

    # Máscaras, todas por operadores sobre el array completo (ADR-009).
    unos = _unos(n, x)
    valido = _como_flotante(regimen.valido, n, x) * _como_flotante(vel.valido, n, x)
    sin_datos = round(_suma(unos - valido, x))

    en_marcha = _indicador(r >= umbrales.rpm_minimo, x)
    rodando = _indicador(v >= umbrales.velocidad_minima_kmh, x)
    util = valido * en_marcha * rodando
    n_utiles = round(_suma(util, x))
    parado = n - sin_datos - n_utiles

    if n_utiles == 0:
        return InformeDeMarchas(
            marchas=(),
            motivos={
                MotivoSinMarcha.PARADO_O_EMBRAGUE: parado,
                MotivoSinMarcha.ENTRE_MARCHAS: 0,
                MotivoSinMarcha.SIN_DATOS: sin_datos,
            },
            n_utiles=0,
            indice_por_muestra=[0] * n,
        )

    # El régimen se hace seguro ANTES de dividir, en vez de filtrar: filtrar exige
    # indexado booleano, que no está en el Protocol `Vectorial`, y una división por
    # cero produciría un `inf` que caería en alguna celda del histograma. Donde la
    # muestra no es útil, el cociente sale finito y sin sentido, y no cuenta porque
    # entra como peso 0 en el `bincount`.
    piso = umbrales.rpm_minimo if umbrales.rpm_minimo > 0.0 else 1.0
    r_seguro = r + (unos - util) * piso
    # km/h por 1000 rpm: números de dos cifras, que es lo que hace legible el
    # histograma y el informe.
    cocientes = v / r_seguro * 1000.0

    mayor = float(x.max(cocientes * util))
    if mayor <= 0.0:
        raise ErrorDeMarcha(
            "todas las muestras útiles dan un cociente velocidad/régimen de cero o negativo; "
            "el canal de velocidad no puede ser el que se ha pasado"
        )
    n_celdas = int(mayor / umbrales.ancho_de_celda) + 2
    bordes = [k * umbrales.ancho_de_celda for k in range(1, n_celdas + 1)]
    celdas = x.searchsorted(bordes, cocientes, "left")
    cuentas = x.bincount(celdas, util, n_celdas + 1)
    cimas = _centros_de_las_cimas(cuentas, umbrales, x)
    if len(cimas) > umbrales.marchas_maximas:
        raise ErrorDeMarcha(
            f"salen {len(cimas)} acumulaciones y el tope es {umbrales.marchas_maximas}. O el "
            "ancho_de_celda es demasiado fino para este log, o el canal de velocidad no sigue "
            "al régimen (¿tracción total con sensor en una sola rueda?)"
        )

    # Fusión de centros próximos: bucle sobre MARCHAS, no sobre muestras (ADR-009).
    # Su coste no depende del número de muestras y está acotado por marchas_maximas.
    centros: list[tuple[float, int]] = []
    for celda, cuenta in sorted(cimas):
        centro = (celda + 0.5) * umbrales.ancho_de_celda
        if centros and centro / centros[-1][0] - 1.0 < umbrales.separacion_minima_relativa:
            # La misma marcha repartida en dos celdas: se queda la de más peso.
            anterior, peso = centros[-1]
            mezcla = (anterior * peso + centro * cuenta) / (peso + cuenta)
            centros[-1] = (mezcla, peso + cuenta)
        else:
            centros.append((centro, cuenta))

    # ASIGNACIÓN, sin recorrer las muestras. Cada marcha aporta una banda
    # [centro·(1−tol), centro·(1+tol)], y las bandas van seguidas en una sola lista
    # de bordes: un `searchsorted` coloca cada muestra de golpe. Un índice IMPAR cae
    # dentro de una banda y uno PAR en el hueco entre dos —el cambio de marcha—,
    # que es exactamente la distinción que hace falta.
    #
    # Las bandas no se solapan porque `validar` exige que
    # `separacion_minima_relativa > tolerancia_relativa`.
    solo_centros = [c for c, _ in centros]
    bordes_banda: list[float] = []
    for c in solo_centros:
        bordes_banda.append(c * (1.0 - umbrales.tolerancia_relativa))
        bordes_banda.append(c * (1.0 + umbrales.tolerancia_relativa))
    banda = x.searchsorted(bordes_banda, cocientes, "right")
    peso_por_banda = x.bincount(banda, util, len(bordes_banda) + 1)

    cuenta_por_marcha = [round(float(peso_por_banda[2 * j + 1])) for j in range(len(solo_centros))]
    entre_marchas = n_utiles - sum(cuenta_por_marcha)

    # `indice_por_muestra` sale del mismo `banda`, también sin recorrer nada: un
    # índice impar es la marcha `(banda + 1) // 2` y uno par es 0. El `% 2` hace de
    # interruptor y el `* util` borra las muestras que no entraron en la agrupación.
    indice_por_muestra = (banda + 1) // 2 * (banda % 2) * _a_entero(util, x)

    marchas = tuple(
        MarchaDetectada(
            indice=j + 1,
            cociente=solo_centros[j],
            n_muestras=cuenta_por_marcha[j],
            fraccion=cuenta_por_marcha[j] / n_utiles,
        )
        for j in range(len(solo_centros))
        if cuenta_por_marcha[j] >= umbrales.muestras_minimas_por_marcha
    )
    # Renumerar tras el filtro, para que los índices sigan siendo consecutivos.
    renumerado = {m.indice: k + 1 for k, m in enumerate(marchas)}
    marchas = tuple(
        MarchaDetectada(renumerado[m.indice], m.cociente, m.n_muestras, m.fraccion) for m in marchas
    )
    indice_por_muestra = [renumerado.get(i, 0) for i in indice_por_muestra]
    descartadas = sum(
        cuenta_por_marcha[j] for j in range(len(solo_centros)) if (j + 1) not in renumerado
    )

    return InformeDeMarchas(
        marchas=marchas,
        motivos={
            MotivoSinMarcha.PARADO_O_EMBRAGUE: parado,
            MotivoSinMarcha.ENTRE_MARCHAS: entre_marchas + descartadas,
            MotivoSinMarcha.SIN_DATOS: sin_datos,
        },
        n_utiles=n_utiles,
        indice_por_muestra=indice_por_muestra,
    )
