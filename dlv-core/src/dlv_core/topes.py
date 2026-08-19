"""Topes de alerta: aviso, crítico, banda y curva en función de otro canal (F3-10).

Especificación: `docs/04-perfiles-motorsport.md` §4.2 P8 (el caso de D10) y §4.3,
y las secciones `[detectores.*]` de `data/umbrales.toml`, en particular
`[detectores.D10.curva_minima]`, que es el ejemplo que justifica todo el módulo.

LO QUE ESTE MÓDULO NO HACE, Y ES LA MITAD DEL DISEÑO
====================================================
No compara nada con un umbral. Eso ya lo hacen `primitivas.umbral_con_histeresis`
y `primitivas.banda`, y las dos aceptan `float | Serie` como umbral y como borde
de banda. Ahí está la clave: **una curva no es un tipo nuevo de umbral, es un
umbral que ya existe evaluado muestra a muestra.** Este módulo construye esa
`Serie` y delega; escribir aquí una segunda comparación con histéresis habría
sido tener dos sitios donde equivocarse con ella, que es exactamente lo que
`primitivas.banda` explica que no quiere.

Así que lo que hay aquí es: leer la declaración del tope, validarla, y convertir
una curva en la serie de umbral que las primitivas ya saben consumir.

POR QUÉ UN UMBRAL PLANO NO SIRVE PARA D10
==========================================
La presión de aceite mínima aceptable depende del régimen. Un umbral plano da
falsos positivos a ralentí —donde 150 kPa es normal— y falsos negativos a 7 000
rpm, que es justo donde un fallo de presión rompe el motor. Cualquiera de los dos
errores acaba en lo mismo: el usuario deja de mirar la alerta. Por eso el tope de
D10 es `base + pendiente x (rpm / 1000)`, y por eso la curva es una forma de tope
de primera clase y no un caso especial escondido en un detector.

DOS FORMAS DE DECLARAR UNA CURVA, Y LA TABLA GANA
==================================================
`data/umbrales.toml` declara las dos y dice cuál manda: «si `puntos` está
presente, gana sobre la fórmula». Se respeta.

* **Fórmula** (`tipo = "lineal_por_regimen"`): `base_kpa` y
  `pendiente_kpa_por_1000rpm`. Dos números, y una recta sin fin.
* **Tabla** (`puntos = [[rpm, kPa], ...]`): interpolación lineal entre puntos.
  Es la que un afinador puede ajustar mirando su motor.

FUERA DEL RANGO DE LA TABLA SE RECORTA, NO SE EXTRAPOLA
========================================================
Es la decisión con más consecuencia del módulo, así que va escrita aquí y no en
un comentario suelto. Con `puntos = [[0, 201.3], [3000, 501.3], [7000, 901.3]]`,
¿cuál es el mínimo a 9 000 rpm? Extrapolando el último tramo saldrían 1 101 kPa,
un valor que NADIE ha declarado y que en un motor que pasa de vueltas convertiría
una presión perfectamente sana en una alerta crítica. Recortando, el mínimo se
queda en los 901,3 kPa del último punto declarado.

Se recorta porque un tope es una afirmación del usuario sobre su motor, y fuera
del rango que declaró no hay afirmación ninguna. Extrapolar sería inventarla, y
además hacia el lado peligroso: una recta creciente extrapolada hacia arriba
dispara alertas, y hacia abajo (por debajo del primer punto) las silencia. Lo
mismo aplica a la fórmula lineal, que sí es infinita por construcción: si eso
molesta, la respuesta es declarar una tabla, que es la forma acotada.

ADR-009
=======
La interpolación se vectoriza con `searchsorted` más aritmética de arrays, igual
que las ventanas temporales de `primitivas` y el histograma de `marcha`. Los
únicos bucles de Python recorren los PUNTOS de la curva (dos o tres), nunca las
muestras.

LA CLASE DE CONVERSIÓN (regla 4 de `CLAUDE.md`)
================================================
La serie que devuelve `evaluar_curva` es `Clase.PUNTO`: es un valor absoluto del
canal al que se compara, no una diferencia. Y por eso la comprobación de clase de
`primitivas.umbral_con_histeresis` sigue siendo la que protege el conjunto —
comparar un canal `INTERVALO` contra un tope `PUNTO` es la trampa del delta— y no
se duplica aquí.

Sobre presión: la canónica del proyecto es kPa ABSOLUTOS (`data/units.toml`), y
la presión relativa es una transformación de PRESENTACIÓN que resta la referencia
justo antes de convertir la unidad y solo a los valores de clase punto
(`[presion_referencia]`, `docs/06` §6.13). Los topes se declaran y se comparan en
canónica, así que `base_kpa = 201.3` de D10 —101,3 de atmosférica más 100 de
margen— es directamente comparable con el canal. Un tope declarado en relativo
sería un tope que cambia de significado según el modo de referencia activo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import pairwise
from typing import Any

from dlv_core.primitivas import (
    Condicion,
    Direccion,
    Serie,
    Vectorial,
    banda,
    umbral_con_histeresis,
)
from dlv_core.unidades import Clase


class ErrorDeTope(ValueError):
    """La declaración de un tope no es usable, y no se sustituye por una suposición."""


class NivelDeTope(Enum):
    """Aviso o crítico. Sin valor por omisión, y el orden ES el de gravedad.

    Son dos topes sobre el MISMO canal y en la misma dirección: el de aviso se
    alcanza antes. Que sean dos niveles y no dos detectores distintos es lo que
    permite comprobar que están en el orden correcto (`validar_pareja`), que es un
    error de configuración que de otro modo no tiene síntoma.
    """

    AVISO = "aviso"
    CRITICO = "critico"


@dataclass(slots=True, frozen=True)
class CurvaLineal:
    """`base + pendiente x (referencia / divisor)`. La forma de D10.

    `divisor_referencia` existe porque la declaración del dato está en
    kPa por cada 1 000 rpm y no por rpm: escribir la pendiente en unidades por
    rpm daría 0,1 y un cero de más o de menos pasaría desapercibido, mientras que
    «100 kPa por cada 1 000 rpm» se lee y se discute.
    """

    rol_referencia: str
    base: float
    pendiente: float
    divisor_referencia: float

    def __post_init__(self) -> None:
        if self.divisor_referencia == 0.0:
            raise ErrorDeTope("divisor_referencia no puede ser 0")


@dataclass(slots=True, frozen=True)
class CurvaPorPuntos:
    """Interpolación lineal entre puntos declarados, recortada en los extremos.

    `puntos` es una secuencia de `(referencia, valor)` ordenada de forma
    estrictamente creciente en la referencia. Lo de «estrictamente» no es
    pedantería: dos puntos con la misma referencia dan una división por cero al
    interpolar, y el resultado sería un umbral `inf` o `nan` que hace que el
    detector no dispare nunca o dispare siempre, sin ningún error por el camino.
    """

    rol_referencia: str
    puntos: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if len(self.puntos) < 2:
            raise ErrorDeTope(
                f"una curva por puntos necesita al menos 2 puntos, y tiene "
                f"{len(self.puntos)}: con uno solo no hay nada que interpolar (y si "
                "el tope es constante, declara un número y no una curva)"
            )
        refs = [r for r, _ in self.puntos]
        for anterior, siguiente in pairwise(refs):
            if siguiente <= anterior:
                raise ErrorDeTope(
                    f"los puntos tienen que ir en orden estrictamente creciente de "
                    f"referencia, y {siguiente} no es mayor que {anterior}. Dos puntos "
                    "con la misma referencia dividen por cero al interpolar y dejan un "
                    "umbral infinito, que no falla: solo hace que el detector no "
                    "dispare nunca o dispare siempre"
                )


Curva = CurvaLineal | CurvaPorPuntos


@dataclass(slots=True, frozen=True)
class Tope:
    """Un tope de un lado: un valor o una curva, con su nivel y su dirección."""

    nivel: NivelDeTope
    direccion: Direccion
    valor: float | Curva

    @property
    def es_curva(self) -> bool:
        return not isinstance(self.valor, float | int)


@dataclass(slots=True, frozen=True)
class TopeDeBanda:
    """Un tope de dos lados. `minimo` y `maximo` pueden ser curvas cada uno.

    La banda de mezcla es el caso: el objetivo de λ se mueve con la carga, así que
    los dos bordes son curvas del mismo canal de referencia y no dos números.
    """

    nivel: NivelDeTope
    minimo: float | Curva
    maximo: float | Curva


def evaluar_curva(
    curva: Curva,
    referencia: Serie,
    *,
    xp: Vectorial,
) -> Serie:
    """La curva evaluada en la rejilla de `referencia`, como serie de umbral.

    El resultado se pasa tal cual a `primitivas.umbral_con_histeresis` o a
    `primitivas.banda`, que ya aceptan una `Serie` como umbral. La rejilla es la
    de la referencia, así que quien llame tiene que haber alineado antes el canal
    juzgado con su referencia (`primitivas.alinear`): comparar una presión con el
    umbral que le corresponde a OTRO instante es el fallo que ninguna prueba de
    valores medios detecta.

    La clase de la serie devuelta es `PUNTO` porque es un valor absoluto del canal
    al que se va a comparar, no una diferencia entre dos.
    """
    if referencia.clase is not Clase.PUNTO:
        raise ErrorDeTope(
            f"la referencia de una curva tiene que ser de clase PUNTO, no "
            f"{referencia.clase.value}: el régimen al que se evalúa el tope es un "
            "valor del canal, no un delta ni una tasa"
        )

    if isinstance(curva, CurvaLineal):
        v = curva.base + curva.pendiente * (referencia.v / curva.divisor_referencia)
    else:
        v = _interpolar_recortado(curva.puntos, referencia.v, xp=xp)

    return Serie(t_ms=referencia.t_ms, v=v, clase=Clase.PUNTO, valido=referencia.valido)


def _interpolar_recortado(
    puntos: tuple[tuple[float, float], ...],
    x: Any,
    *,
    xp: Vectorial,
) -> Any:
    """Interpolación lineal vectorizada, recortada fuera del rango declarado.

    `searchsorted` da, para cada muestra, en qué tramo de la curva cae; a partir
    de ahí todo es aritmética de arrays. El bucle de Python recorre los tramos de
    la curva (dos o tres), no las muestras (ADR-009).

    El recorte se consigue empujando el índice de tramo dentro de `[0, n-2]` y
    forzando después el valor de los extremos, en vez de con un `if` por muestra.
    """
    refs = [r for r, _ in puntos]
    vals = [v for _, v in puntos]
    n = len(puntos)

    # Tramo de cada muestra: `searchsorted(..., "right") - 1` da el índice del
    # punto izquierdo del tramo, ya recortado a [0, n-2] con max/min sobre el
    # array de índices (aritmética, no ramas por muestra).
    idx = xp.searchsorted(refs, x, "right")

    # Acumulador: se empieza con el valor del primer tramo y se corrige tramo a
    # tramo con un indicador, para no necesitar `where` en el protocolo.
    salida = None
    for k in range(n - 1):
        x0, x1 = refs[k], refs[k + 1]
        y0, y1 = vals[k], vals[k + 1]
        pendiente = (y1 - y0) / (x1 - x0)
        # El tramo k se aplica a las muestras cuyo `idx` es k+1, más las de los
        # extremos: idx == 0 cae en el primer tramo (recortado por abajo) y
        # idx >= n en el último (recortado por arriba).
        en_tramo = idx == (k + 1)
        if k == 0:
            en_tramo = en_tramo | (idx == 0)
        if k == n - 2:
            en_tramo = en_tramo | (idx >= n)
        indicador = en_tramo * 1.0

        # Recortado: fuera del rango se usa el valor del punto extremo, que es lo
        # mismo que evaluar el tramo en su propio borde.
        bajo = x0 if k == 0 else -_INFINITO
        alto = x1 if k == n - 2 else _INFINITO
        x_recortado = _recortar(x, bajo, alto, xp=xp)
        tramo = y0 + pendiente * (x_recortado - x0)
        salida = tramo * indicador if salida is None else salida + tramo * indicador
    return salida


#: El lado que NO recorta de un tramo intermedio. No se usa `math.inf`: el tramo
#: se multiplica después por un indicador 0,0 en las muestras que no le tocan, y
#: `inf * 0,0` es `nan`, que contaminaría la suma de todos los tramos. Un número
#: grande y finito hace el mismo trabajo sin ese riesgo, y ninguna referencia de un
#: log real se le acerca.
_INFINITO = 1e30


def _recortar(x: Any, bajo: float, alto: float, *, xp: Vectorial) -> Any:
    """`minimum(maximum(x, bajo), alto)`, elemento a elemento.

    Las dos están en el protocolo `Vectorial`, así que no hace falta construir el
    recorte con aritmética de valores absolutos ni pedirle un `where` al protocolo.

    Los límites se convierten antes en arrays constantes con `x * 0,0 + limite`.
    `numpy.maximum` difundiría un escalar sin quejarse, pero el protocolo declara
    estas dos como «ELEMENTO A ELEMENTO, entre dos arrays» —es lo que las
    distingue de `min`/`max`, que reducen— y apoyarse en la difusión sería escribir
    código que funciona con NumPy y falla con cualquier otra implementación del
    protocolo. La aritmética no necesita ninguna función nueva del contrato.
    """
    piso = x * 0.0 + bajo
    techo = x * 0.0 + alto
    return xp.minimum(xp.maximum(x, piso), techo)


def validar_pareja(aviso: Tope, critico: Tope) -> None:
    """El de aviso tiene que alcanzarse ANTES que el crítico, o no avisa de nada.

    Es un error de configuración sin síntoma: con el aviso de sobretemperatura a
    120 °C y el crítico a 110 °C, el crítico salta primero y el aviso nunca llega
    a ser un aviso. Nada falla; simplemente el nivel de aviso deja de existir, y
    quien lo configuró cree que lo tiene.

    Solo se puede comprobar entre topes planos: dos curvas pueden cruzarse en
    algún punto de su rango y eso ya no es una comparación de dos números. Cuando
    alguno es curva, se dice que no se ha comprobado en vez de dar por bueno lo
    que no se ha mirado.
    """
    if aviso.direccion is not critico.direccion:
        raise ErrorDeTope(
            f"el tope de aviso va {aviso.direccion.value} y el crítico "
            f"{critico.direccion.value}: son dos alertas distintas, no dos niveles "
            "de la misma"
        )
    if not isinstance(aviso.valor, float | int) or not isinstance(critico.valor, float | int):
        return

    a, c = float(aviso.valor), float(critico.valor)
    if aviso.direccion is Direccion.ARRIBA and a > c:
        raise ErrorDeTope(
            f"con dirección ARRIBA el aviso ({a}) tiene que ser menor o igual que el "
            f"crítico ({c}); así el crítico salta primero y el aviso nunca avisa"
        )
    if aviso.direccion is Direccion.ABAJO and a < c:
        raise ErrorDeTope(
            f"con dirección ABAJO el aviso ({a}) tiene que ser mayor o igual que el "
            f"crítico ({c}); así el crítico salta primero y el aviso nunca avisa"
        )


def aplicar_tope(
    serie: Serie,
    tope: Tope,
    *,
    referencia: Serie | None = None,
    histeresis: float,
    xp: Vectorial,
) -> Condicion:
    """La condición «el canal ha rebasado este tope», con histéresis.

    `histeresis` es la fracción del recorrido de vuelta, tal como la declara
    `[general].histeresis_relativa`, y se traduce aquí a los dos umbrales
    ABSOLUTOS que pide `primitivas.umbral_con_histeresis`. La traducción se hace
    sobre el propio valor del tope y no sobre la magnitud, que es la limitación
    que ese docstring ya documenta para las escalas con origen desplazado: sobre
    una temperatura en kelvin el 2 % son 7,6 K y eso no es una histéresis, es otro
    umbral. Para esas magnitudes hay que declarar `histeresis = 0.0` y una banda.
    """
    entrada: float | Serie
    salida: float | Serie
    if isinstance(tope.valor, float | int):
        entrada = float(tope.valor)
        salida = _con_histeresis_plano(entrada, tope.direccion, histeresis)
    else:
        if referencia is None:
            raise ErrorDeTope(
                "el tope es una curva y no se ha pasado la serie de referencia: sin "
                "ella no hay con qué evaluarlo, y suponer un régimen fijo convertiría "
                "la curva en el umbral plano que la curva existe para no ser"
            )
        curva_evaluada = evaluar_curva(tope.valor, referencia, xp=xp)
        entrada = curva_evaluada
        salida = _con_histeresis_serie(curva_evaluada, tope.direccion, histeresis, xp=xp)

    return umbral_con_histeresis(
        serie, entrada=entrada, salida=salida, direccion=tope.direccion, xp=xp
    )


def _con_histeresis_plano(valor: float, direccion: Direccion, histeresis: float) -> float:
    margen = abs(valor) * histeresis
    return valor - margen if direccion is Direccion.ARRIBA else valor + margen


def _con_histeresis_serie(
    umbral: Serie, direccion: Direccion, histeresis: float, *, xp: Vectorial
) -> Serie:
    margen = xp.abs(umbral.v) * histeresis
    v = umbral.v - margen if direccion is Direccion.ARRIBA else umbral.v + margen
    return Serie(t_ms=umbral.t_ms, v=v, clase=umbral.clase, valido=umbral.valido)


def aplicar_banda(
    serie: Serie,
    tope: TopeDeBanda,
    *,
    referencia: Serie | None = None,
    histeresis_relativa: float,
    xp: Vectorial,
) -> Condicion:
    """La condición «el canal está DENTRO de la banda». Se niega con `.no()`.

    Dentro y no fuera por la misma razón que `primitivas.banda`: el detector que
    hace falta casi siempre es el contrario, y tener las dos como primitivas
    distintas sería tener dos sitios donde equivocarse con la histéresis.
    """
    minimo = _borde(tope.minimo, referencia, xp=xp)
    maximo = _borde(tope.maximo, referencia, xp=xp)
    return banda(
        serie, minimo=minimo, maximo=maximo, histeresis_relativa=histeresis_relativa, xp=xp
    )


def _borde(valor: float | Curva, referencia: Serie | None, *, xp: Vectorial) -> float | Serie:
    if isinstance(valor, float | int):
        return float(valor)
    if referencia is None:
        raise ErrorDeTope(
            "un borde de la banda es una curva y no se ha pasado la serie de "
            "referencia con la que evaluarlo"
        )
    return evaluar_curva(valor, referencia, xp=xp)
