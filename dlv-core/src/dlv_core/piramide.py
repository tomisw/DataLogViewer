"""Pirámide de decimación (§3.5 de `docs/03-arquitectura.md`).

Regla de disciplina de rendimiento (ADR-009, la misma que en `almacen.py`):

    Ninguna ruta que se ejecute una vez por muestra puede estar escrita en
    Python interpretado. Todo cálculo sobre series es una operación de NumPy
    o Polars sobre el array completo: `for` sobre muestras, `.apply()`,
    `.iterrows()` y `map()` por elemento están prohibidos en `dlv-core`. Lo
    que no se puede vectorizar (decimación por moda con longitud de racha,
    OR de máscara de bits, suma de delta con racha) se implementa en Numba
    `@njit`, no en Python puro; el banco de rendimiento decide cuándo hace
    falta (§3.5, última línea) -- tarea F1-10: con NumPy puro basta (banco
    en `tools/banco.py piramide --tipo ...`), así que Numba no entra todavía.

Niveles con factor 4. Cuatro variantes de agregación del cubo (§3.5), cada
una con su propio tipo de nivel porque agregan cosas de naturaleza distinta:

    CONTINUO   min, max, first, last     -- preserva picos
    CONTADOR   suma del delta            -- un incremento aislado no se pierde
    ENUM       moda + marca de transición -- evita parpadeo en los carriles
    BITS       OR de los bits            -- un bit activado una vez sigue visible
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

import numpy as np


class _NivelConCubos(Protocol):
    """Lo único que necesita `elegir_nivel`: cuántos cubos tiene el nivel.

    Las cuatro variantes agregan cosas de naturaleza distinta (min/max no es
    lo mismo que una moda o un OR de bits) y por eso son dataclasses
    distintas, pero todas tienen el mismo número de cubos por definición
    (una entrada por cubo en cada uno de sus arrays), así que comparten esta
    forma sin necesidad de heredar de una base común.
    """

    @property
    def n_cubos(self) -> int: ...


class TipoCanalPiramide(Enum):
    """Variante de agregación del cubo, según el tipo de canal (§3.5)."""

    CONTINUO = auto()  # min, max, first, last — preserva picos
    CONTADOR = auto()  # suma del delta — un incremento aislado no se pierde
    ENUM = auto()  # moda + marca de transiciones — evita parpadeo
    BITS = auto()  # OR de los bits — un bit activado una vez sigue visible


@dataclass(slots=True, frozen=True)
class NivelPiramide:
    """Un nivel de la pirámide (variante `CONTINUO`): factor y los cuatro
    arrays del cubo."""

    factor: int
    minimo: np.ndarray
    maximo: np.ndarray
    primero: np.ndarray
    ultimo: np.ndarray

    @property
    def n_cubos(self) -> int:
        return len(self.minimo)


@dataclass(slots=True, frozen=True)
class NivelContador:
    """Un nivel de la pirámide para un canal `CONTADOR` (F1-10).

    `suma_delta` es la suma de los incrementos (`diff`) del canal dentro del
    cubo: exacta y asociativa igual que `min`/`max` en `CONTINUO` (la suma de
    sumas de un grupo de cubos es la suma real del rango que cubren), así que
    un incremento aislado no se diluye al decimar, aunque el resto del cubo
    esté plano. No se maneja desbordamiento/reinicio del contador (wrap): si
    el canal puede reiniciarse a mitad de racha, un `diff` sin corregir da un
    salto negativo grande en ese punto -- fuera de alcance de F1-10, que solo
    pide la agregación, no la detección de wraps.
    """

    factor: int
    suma_delta: np.ndarray
    primero: np.ndarray  # valor crudo (no delta) al principio del cubo
    ultimo: np.ndarray  # valor crudo (no delta) al final del cubo

    @property
    def n_cubos(self) -> int:
        return len(self.suma_delta)


@dataclass(slots=True, frozen=True)
class NivelEnum:
    """Un nivel de la pirámide para un canal `ENUM`/estado (F1-10).

    `moda` es el valor más frecuente del cubo; `hubo_transicion` marca si
    dentro del cubo hubo más de un valor distinto (así el carril de estado
    puede dibujar una marca de "aquí cambió algo" aunque la moda oculte el
    detalle). A partir de L2, la moda se recalcula sobre las modas del nivel
    anterior ("moda de modas"): es una aproximación -- no siempre coincide
    con la moda exacta de todo el rango cubierto -- pero conserva el objetivo
    de la variante (evitar parpadeo mostrando el estado dominante). En
    cambio `hubo_transicion` no se aproxima: se propaga con un OR, así que un
    cambio real detectado en cualquier nivel intermedio nunca se pierde.
    """

    factor: int
    moda: np.ndarray
    hubo_transicion: np.ndarray  # bool

    @property
    def n_cubos(self) -> int:
        return len(self.moda)


@dataclass(slots=True, frozen=True)
class NivelBits:
    """Un nivel de la pirámide para una máscara de bits (F1-10).

    `or_bits` es el OR a nivel de bit de todos los valores del cubo: exacto y
    asociativo (el OR de ORes de un grupo es el OR real del rango), así que
    un bit que se activó una sola vez sigue visible en cualquier nivel.
    """

    factor: int
    or_bits: np.ndarray

    @property
    def n_cubos(self) -> int:
        return len(self.or_bits)


def _nivel_l0(valores: np.ndarray) -> NivelPiramide:
    """L0 no decima nada: min = max = first = last = el propio valor. Así
    `elegir_nivel` no necesita un caso especial para "sin decimar"."""
    return NivelPiramide(factor=1, minimo=valores, maximo=valores, primero=valores, ultimo=valores)


def _siguiente_nivel_continuo(anterior: NivelPiramide, *, factor_base: int) -> NivelPiramide:
    """Un nivel a partir del anterior (§3.5): `reshape` + `min/max(axis=1)`.

    Decima sobre los cubos `min`/`max` del nivel anterior, no sobre los datos
    originales: agregar el mínimo de mínimos (y el máximo de máximos) de un
    grupo de cubos es el mínimo (máximo) real del rango que cubren, así que
    el resultado es idéntico a decimar de una vez con un factor mayor, sin
    tener que volver a tocar el array original en cada nivel.
    """
    v_min, v_max = anterior.minimo, anterior.maximo
    n = (len(v_min) // factor_base) * factor_base
    b_min = v_min[:n].reshape(-1, factor_base)
    b_max = v_max[:n].reshape(-1, factor_base)
    # `first`/`last` del nivel nuevo son el primero del primer cubo y el
    # último del último cubo del grupo: no hay que agregarlos, solo tomarlos.
    b_primero = anterior.primero[:n].reshape(-1, factor_base)
    b_ultimo = anterior.ultimo[:n].reshape(-1, factor_base)
    return NivelPiramide(
        factor=anterior.factor * factor_base,
        minimo=b_min.min(axis=1),
        maximo=b_max.max(axis=1),
        primero=b_primero[:, 0],
        ultimo=b_ultimo[:, -1],
    )


def _nivel_l0_contador(valores: np.ndarray) -> NivelContador:
    """L0: `suma_delta` es el `diff` del propio array (primer valor sin
    incremento previo, `delta[0] = 0`), casteado a `int64` para no envolver
    si `valores` es un entero sin signo estrecho (p. ej. `uint32`)."""
    v64 = valores.astype(np.int64)
    delta = np.diff(v64, prepend=v64[:1]) if v64.size else v64
    return NivelContador(factor=1, suma_delta=delta, primero=valores, ultimo=valores)


def _siguiente_nivel_contador(anterior: NivelContador, *, factor_base: int) -> NivelContador:
    """Suma de sumas de un grupo de cubos = suma real del rango que cubren
    (asociativa, igual que min/max en `CONTINUO`): ningún incremento se
    diluye al decimar, por aislado que esté."""
    n = (len(anterior.suma_delta) // factor_base) * factor_base
    b_delta = anterior.suma_delta[:n].reshape(-1, factor_base)
    b_primero = anterior.primero[:n].reshape(-1, factor_base)
    b_ultimo = anterior.ultimo[:n].reshape(-1, factor_base)
    return NivelContador(
        factor=anterior.factor * factor_base,
        suma_delta=b_delta.sum(axis=1),
        primero=b_primero[:, 0],
        ultimo=b_ultimo[:, -1],
    )


def _moda_por_fila(bloque: np.ndarray) -> np.ndarray:
    """Moda de cada fila de `bloque` (n_cubos, factor), vectorizada sobre las
    filas (cubos): compara cada una de las `factor` columnas contra las
    demás DENTRO de la misma fila y cuenta coincidencias. El bucle de Python
    recorre `factor` (normalmente 4), no las filas -- que pueden ser
    millones -- así que sigue siendo ADR-009.
    """
    factor = bloque.shape[1]
    conteos = np.zeros(bloque.shape, dtype=np.int32)
    for j in range(factor):
        conteos[:, j] = (bloque == bloque[:, j : j + 1]).sum(axis=1)
    indice_moda = conteos.argmax(axis=1)
    return bloque[np.arange(bloque.shape[0]), indice_moda]


def _nivel_l0_enum(valores: np.ndarray) -> NivelEnum:
    return NivelEnum(
        factor=1, moda=valores, hubo_transicion=np.zeros(valores.shape, dtype=np.bool_)
    )


def _siguiente_nivel_enum(anterior: NivelEnum, *, factor_base: int) -> NivelEnum:
    n = (len(anterior.moda) // factor_base) * factor_base
    b_moda = anterior.moda[:n].reshape(-1, factor_base)
    b_trans = anterior.hubo_transicion[:n].reshape(-1, factor_base)
    # Transición real si el cubo ya traía una, o si las modas del nivel
    # anterior dentro de este cubo no son todas iguales entre sí.
    variedad = (b_moda != b_moda[:, :1]).any(axis=1)
    return NivelEnum(
        factor=anterior.factor * factor_base,
        moda=_moda_por_fila(b_moda),
        hubo_transicion=b_trans.any(axis=1) | variedad,
    )


def _nivel_l0_bits(valores: np.ndarray) -> NivelBits:
    return NivelBits(factor=1, or_bits=valores)


def _siguiente_nivel_bits(anterior: NivelBits, *, factor_base: int) -> NivelBits:
    """OR de ORes de un grupo de cubos = OR real del rango que cubren
    (asociativo): un bit activado una sola vez sigue visible en cualquier
    nivel, por lejos que esté en el tiempo."""
    n = (len(anterior.or_bits) // factor_base) * factor_base
    b = anterior.or_bits[:n].reshape(-1, factor_base)
    return NivelBits(factor=anterior.factor * factor_base, or_bits=np.bitwise_or.reduce(b, axis=1))


def _valida_factor_base(factor_base: int) -> None:
    if factor_base < 2:
        raise ValueError(f"factor_base tiene que ser >= 2, se dio {factor_base}")


def construir_piramide_continuo(
    valores: np.ndarray, *, factor_base: int = 4
) -> list[NivelPiramide]:
    """Variante `CONTINUO`: `min, max, first, last` por cubo. Ver `construir_piramide`."""
    _valida_factor_base(factor_base)
    niveles = [_nivel_l0(valores)]
    while niveles[-1].n_cubos >= factor_base:
        niveles.append(_siguiente_nivel_continuo(niveles[-1], factor_base=factor_base))
    return niveles


def construir_piramide_contador(
    valores: np.ndarray, *, factor_base: int = 4
) -> list[NivelContador]:
    """Variante `CONTADOR`: suma del delta por cubo. Ver `construir_piramide`."""
    _valida_factor_base(factor_base)
    niveles = [_nivel_l0_contador(valores)]
    while niveles[-1].n_cubos >= factor_base:
        niveles.append(_siguiente_nivel_contador(niveles[-1], factor_base=factor_base))
    return niveles


def construir_piramide_enum(valores: np.ndarray, *, factor_base: int = 4) -> list[NivelEnum]:
    """Variante `ENUM`: moda + marca de transición por cubo. Ver `construir_piramide`."""
    _valida_factor_base(factor_base)
    niveles = [_nivel_l0_enum(valores)]
    while niveles[-1].n_cubos >= factor_base:
        niveles.append(_siguiente_nivel_enum(niveles[-1], factor_base=factor_base))
    return niveles


def construir_piramide_bits(valores: np.ndarray, *, factor_base: int = 4) -> list[NivelBits]:
    """Variante `BITS`: OR de bits por cubo. Ver `construir_piramide`."""
    _valida_factor_base(factor_base)
    niveles = [_nivel_l0_bits(valores)]
    while niveles[-1].n_cubos >= factor_base:
        niveles.append(_siguiente_nivel_bits(niveles[-1], factor_base=factor_base))
    return niveles


def construir_piramide(
    valores: np.ndarray, *, tipo: TipoCanalPiramide, factor_base: int = 4
) -> list[NivelPiramide] | list[NivelContador] | list[NivelEnum] | list[NivelBits]:
    """Construye todos los niveles de la pirámide sobre el array completo,
    despachando según `tipo` a la variante correspondiente (F1-09: `CONTINUO`;
    F1-10: `CONTADOR`, `ENUM`, `BITS`).

    Cada nivel decima el nivel ANTERIOR, nunca los datos originales, en las
    cuatro variantes: el coste total de toda la pirámide es ~1/3 del nivel
    base (§3.5), no un múltiplo. Se para en cuanto ya no hay un grupo
    completo de `factor_base` cubos que decimar. Ningún nivel se calcula
    muestra a muestra.

    El tipo de retorno es una unión porque cada variante agrega algo de
    naturaleza distinta (no tiene sentido forzar una moda o un OR de bits
    dentro de los campos `minimo`/`maximo` pensados para picos). Quien conoce
    su `tipo` de antemano puede llamar directamente a
    `construir_piramide_continuo` / `_contador` / `_enum` / `_bits` para
    evitar la unión en su propio código.
    """
    if tipo is TipoCanalPiramide.CONTINUO:
        return construir_piramide_continuo(valores, factor_base=factor_base)
    if tipo is TipoCanalPiramide.CONTADOR:
        return construir_piramide_contador(valores, factor_base=factor_base)
    if tipo is TipoCanalPiramide.ENUM:
        return construir_piramide_enum(valores, factor_base=factor_base)
    if tipo is TipoCanalPiramide.BITS:
        return construir_piramide_bits(valores, factor_base=factor_base)
    raise AssertionError(f"TipoCanalPiramide no cubierto: {tipo!r}")  # exhaustivo


def elegir_nivel[T: _NivelConCubos](niveles: list[T], *, ancho_px: int) -> T:
    """Elige el nivel cuyo número de cubos es aproximadamente `ancho_px`.

    "Aproximadamente" es literal: el nivel con menos diferencia absoluta entre
    su número de cubos y `ancho_px`, sin preferencia por quedarse corto o
    largo. `niveles` no vacío (lo construye siempre `construir_piramide*`, que
    al menos devuelve L0). Funciona con cualquiera de las cuatro variantes.
    """
    return min(niveles, key=lambda n: abs(n.n_cubos - ancho_px))
