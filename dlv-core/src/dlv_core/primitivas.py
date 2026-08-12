"""Motor de detectores: las nueve primitivas de `docs/04` §4.3 (tarea F3-06).

Esta es la capa sobre la que se construyen los 18 detectores de §4.3 (F3-07),
los topes de alerta (F3-10) y la segmentación automática (F3-16). Aquí no hay
ni un detector: hay las piezas con las que se escriben, y una sola forma de
componerlas. Que la API se vaya a usar 18 veces es lo que decide su forma: si
un detector se pudiera expresar de dos maneras distintas, dos detectores
equivalentes darían resultados distintos y nadie sabría cuál creer.

LO QUE DE VERDAD SE JUEGA: EL FALSO POSITIVO
=============================================
«Un detector que salta cuando no debe se apaga y no se vuelve a mirar; uno que
no salta cuando debe deja pasar una detonación.» La histéresis y la permanencia
mínima son lo único que separa las dos cosas, y son la parte que este tipo de
motor hace mal: un umbral desnudo sobre una señal ruidosa a 20 Hz produce
cientos de eventos de un ciclo (§4.3, «el problema clásico»). Por eso en este
módulo:

* **La histéresis no es opcional.** `umbral_con_histeresis` exige `entrada` y
  `salida` por separado. Quien quiera el umbral desnudo declara `salida ==
  entrada` y queda escrito en la configuración, no escondido en el código.
* **La permanencia tampoco.** `eventos` exige una `Permanencia`, y no tiene
  valor por omisión: los suyos viven en `data/umbrales.toml` (regla 3 de
  `CLAUDE.md`).
* **Y ninguna de las dos se reimplementa por primitiva.** Hay UNA función que
  aplica la histéresis (`_estado_con_histeresis`) y UNA que convierte una
  condición en eventos (`eventos`). `banda` no tiene su propia histéresis:
  usa la misma. Diecisiete detectores no pueden compartir un motor si cada
  primitiva trae su propia versión del mismo autómata.

TRES FAMILIAS, Y UNA SOLA TUBERÍA
==================================
Las nueve primitivas de §4.3 no son nueve cosas del mismo tipo, y tratarlas
como si lo fueran es lo que produce las dos formas de expresar un detector. Se
reparten en tres familias con tipos de entrada y salida distintos, de modo que
solo encajan en un orden:

    Serie ──transformación──▶ Serie ──primitiva──▶ Condicion ──reducción──▶ Evento
                                                       │
                                                  y / o / no  (Compuesto)

1. **Transformaciones** (`Serie` -> `Serie`): `alinear` (multi-tasa),
   `derivada`, `delta_de_contador`, `extremo_en_ventana`. No deciden nada;
   producen otra serie, y **declaran su clase de conversión** (regla 4).
2. **Primitivas de condición** (`Serie` -> `Condicion`):
   `umbral_con_histeresis`, `banda`, `pico_local`, `fuera_de_mascara`. Una
   `Condicion` es «esto se cumple aquí», muestra a muestra, con su máscara de
   validez. `Condicion.y`, `.o` y `.no` son el «Compuesto» de §4.3.
3. **Reducciones** (`Condicion` -> eventos y números): `eventos`,
   `tiempo_acumulado`, `conteo_de_cruces`.

Correspondencia literal con la tabla de §4.3:

| §4.3 | aquí |
|---|---|
| Umbral con histéresis (entrada, salida, permanencia) | `umbral_con_histeresis` + `Permanencia` |
| Pico local (prominencia, ventana) | `pico_local` |
| Derivada (ventana, umbral) | `derivada` (ventana) + `umbral_con_histeresis` (umbral) |
| Tiempo por encima (umbral, acumulado) | `tiempo_acumulado(eventos(...))` |
| Conteo de cruces (umbral) | `conteo_de_cruces` |
| Delta de contador | `delta_de_contador` |
| Banda (mín, máx) | `banda` |
| Compuesto (AND/OR) | `Condicion.y`, `.o`, `.no` |
| Fuera de máscara (bits de interés) | `fuera_de_mascara` |

La «Derivada» de §4.3 lleva dos parámetros —ventana y umbral— que aquí quedan
en dos piezas distintas a propósito: el umbral de una derivada es un umbral
como cualquier otro y merece la misma histéresis. Si `derivada` disparara por
sí sola, un tip-in ruidoso volvería a dar la ráfaga de eventos que §4.3
describe, y habría dos implementaciones del mismo umbral.

MULTI-TASA: UN HUECO ES UN HUECO
=================================
El log es disperso: 20 / 10 / 5 Hz entrelazados, y los grupos de muestreo se
intercalan (`docs/01` §1.6). Dos canales casi nunca comparten marcas de tiempo,
así que toda primitiva que compare dos canales tiene que decir qué hace con los
huecos. Este módulo no inventa un criterio nuevo: usa el de F3-18
(`expresiones.alinear_por_retencion`), **retención del último valor con límite
de validez**, y llama a esa función en vez de reimplementarla.

De ahí salen dos reglas que atraviesan el módulo entero:

* Toda `Serie` y toda `Condicion` llevan una máscara `valido`. Una muestra no
  válida no es `False`: es «no se sabe».
* **Una muestra no válida interrumpe una carrera de eventos.** No la puentea
  (eso sería afirmar que la condición seguía cumpliéndose sin haberlo visto) ni
  la cuenta como incumplimiento. La consecuencia se paga y está medida: si un
  canal deja de emitir dos décimas en medio de un evento de tres segundos, D5
  («> 2 s») ve dos eventos cortos en lugar de uno largo, y no dispara. La
  alternativa —puentear el hueco— es inventar el dato justo donde no lo hay, y
  es el fallo que `docs/04` §4.5 prohíbe explícitamente.
* La composición usa **lógica de tres valores** (Kleene), no `valido_a &
  valido_b`. `A o B` con `A` cierta y válida es cierta aunque `B` falte: el
  régimen del motor no deja de estar por encima de 4 000 rpm porque el sensor
  de temperatura de aceite tenga un hueco. Con la validez estricta, un hueco en
  un canal irrelevante apagaría una detección segura, que es la forma más
  tonta de perder un evento.

ADR-009: CERO BUCLES POR MUESTRA, INCLUIDAS LA HISTÉRESIS Y LAS VENTANAS
========================================================================
`detectores.py` daba por hecho que la histéresis y los autómatas de estado
tendrían que ir a Numba. **No ha hecho falta, y en el informe de la tarea está
el porqué.** Las tres piezas que parecían exigir un `for`:

1. **La histéresis** (un Schmitt trigger: dos umbrales y memoria) se resuelve
   con la misma idea que el multi-tasa: *retención*. El estado en cada muestra
   es el de la última muestra que DECIDIÓ algo —la última que cruzó el umbral
   de entrada o el de salida—, y «la última decisiva hasta aquí» es
   `cumsum(decisiva) - 1` usado como índice sobre las decisivas compactadas.
   Dos pasadas en C, sin memoria explícita. Ver `_estado_con_histeresis`.
2. **La permanencia mínima** exige delimitar las carreras de muestras
   consecutivas. Los índices de inicio y fin de cada carrera salen de comparar
   la máscara con su propia versión desplazada (`e != e[previo]`), y el filtro
   por duración y por número de muestras se aplica **antes** de construir
   ningún objeto Python, sobre el array de carreras. El único `for` recorre los
   eventos que sobreviven al filtro, y cada iteración hace un `max`/`min`
   vectorizado sobre el tramo contiguo del evento: exactamente el patrón que
   `malla.py` documenta para el mínimo/máximo por celda, y por la misma razón
   (NumPy no tiene una reducción agrupada como función de nivel de módulo).
   `Permanencia.maximo_de_eventos` es lo que mantiene ese bucle acotado.
3. **Las ventanas temporales** sobre una rejilla irregular —`docs/01` §1.7 es
   explícito: «no se debe asumir muestreo uniforme para ningún cálculo
   (derivadas, FFT, integrales, remuestreo)»— se resuelven con `searchsorted`:
   los límites exactos de la ventana de cada muestra en una sola pasada. Para
   la derivada eso basta. Para el extremo en una ventana de anchura variable
   hace falta además una **tabla dispersa de extremos** por duplicación
   (`_tabla_de_extremos`): `log2(anchura)` pasadas vectorizadas, y un bucle
   sobre NIVELES (media docena), nunca sobre muestras. Ver
   `extremo_en_ventana`.

El protocolo `Vectorial` declara las nueve funciones de NumPy que hacen falta,
con los nombres de NumPy, así que el propio módulo `numpy` lo satisface sin
adaptador y las pruebas ejercitan ESTE código con una implementación de
biblioteca estándar (mismo patrón que `reloj.py`, `malla.py`,
`expresiones.py` y `plausibilidad.py`).

LA CLASE DE CONVERSIÓN VIAJA CON LA SERIE (regla 4)
====================================================
`Serie.clase` no tiene valor por omisión, igual que en `unidades.py`. No es
ceremonia: las transformaciones de este módulo CAMBIAN la clase, y es
exactamente donde vuelve la trampa del delta.

* la derivada de un canal es `TASA` (grados por segundo, no grados);
* el delta de un contador es `INTERVALO` (un incremento, no un valor);
* el mínimo o el máximo de una ventana siguen siendo `PUNTO` —son valores del
  canal—, mientras que la *amplitud* de esa ventana sería `INTERVALO`;
* la `prominencia_minima` de `pico_local` es un `INTERVALO`: es la única
  magnitud de la tabla de §4.3 que no es un punto, junto con el delta de
  contador. Una prominencia de 10 K mostrada como punto sale como −263,15 °C.

Y `Evento.clase_valor` lleva la clase de `valor_pico` hasta quien lo pinte, por
el mismo motivo: el pico de un evento de derivada es una tasa, y convertirlo
como punto es la trampa del delta llegando por la puerta del panel de
incidencias.

LO QUE ESTE MÓDULO NO HACE (deliberado)
========================================
* **No es ningún detector concreto.** No sabe qué es el knock ni el boost, no
  conoce los roles y no asigna severidades: `Evento` no tiene `tipo` ni
  `severidad` porque las dos son decisiones de la configuración de F3-07, que
  además necesita canales de contexto que este módulo no recibe (la escalada a
  crítica de D1 mira régimen y presión). `detectores.Incidencia` = `Evento` +
  tipo + severidad + contexto, y esa suma la hace F3-07.
* **No abre ficheros** (ADR-002): recibe series y umbrales ya cargados. Ni
  `data/umbrales.toml` ni ningún otro.
* **No convierte unidades.** Todo entra y sale en canónica (ADR-004); un umbral
  se declara en canónica y se muestra en la unidad activa con
  `umbrales_editables.py`, nunca al revés.
* **No decide de qué canal sale cada serie.** Eso es `identidad.py` (por rol) y
  `expresiones.py` (canales derivados como el λ error o el error de boost).
* **No tiene un umbral por omisión.** Ni uno. Todos los de este módulo son
  parámetros obligatorios, y los valores por omisión viven en
  `data/umbrales.toml` (`[general]` y `[motor_de_deteccion]`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, cast

from dlv_core.expresiones import alinear_por_retencion
from dlv_core.unidades import Clase

__all__ = [
    "Condicion",
    "Direccion",
    "ErrorDePrimitiva",
    "Evento",
    "Extremo",
    "Permanencia",
    "Pico",
    "Serie",
    "SerieDeBits",
    "Vectorial",
    "alinear",
    "banda",
    "conteo_de_cruces",
    "delta_de_contador",
    "derivada",
    "eventos",
    "extremo_en_ventana",
    "fuera_de_mascara",
    "pico_local",
    "tiempo_acumulado",
    "umbral_con_histeresis",
]

MS_POR_S = 1000.0
"""Milisegundos por segundo. No es un umbral: `t` está en ms desde el t0 del
segmento (`almacen.ChannelSeries.t`, uint32) y los umbrales de
`data/umbrales.toml` están en segundos, que es la unidad canónica de tiempo
(`docs/06`). El factor es una definición, no una opinión."""


class ErrorDePrimitiva(ValueError):
    """Uso incorrecto del motor, o una configuración que no se puede aplicar.

    No es una detección: un canal raro no produce excepciones, produce (o no)
    eventos. Esto otro —una histéresis al revés, dos series en rejillas
    distintas, una clase de conversión imposible, un umbral que falta— es un
    fallo de quien llama, y callarlo produciría detecciones plausibles y
    falsas, que es el peor resultado posible aquí.
    """


# --------------------------------------------------------------------------- #
# El protocolo `Vectorial`
# --------------------------------------------------------------------------- #
class Vectorial(Protocol):
    """Lo que este módulo necesita de NumPy, y nada más.

    Los nombres y las firmas son los de NumPy, así que el propio módulo `numpy`
    satisface el protocolo sin adaptador (`cast("Vectorial", numpy)`) y las
    pruebas pueden ejercitar este mismo código con una implementación de
    biblioteca estándar. Los parámetros son posicionales para que cualquier
    implementación pueda nombrarlos como quiera.

    Nueve funciones, y ninguna «por si acaso»:

    * `searchsorted(a, v, side)` — los límites exactos de una ventana temporal
      sobre una rejilla irregular, y el nivel de la tabla de extremos. Es la
      función que evita asumir muestreo uniforme (`docs/01` §1.7).
    * `abs(a)` — la necesita `expresiones.alinear_por_retencion`, a la que este
      módulo delega el multi-tasa en vez de reimplementarlo.
    * `cumsum(a)` — «cuántas muestras decisivas hasta aquí»: el índice de la
      retención con la que se vectoriza la histéresis.
    * `arange(n)` — las posiciones de las muestras. Con ella se construyen los
      desplazamientos (`v[previo]`) y se extraen los índices de inicio y fin de
      cada carrera (`idx[mascara]`), sin pedirle al protocolo ni un
      `flatnonzero` ni un `concatenate`.
    * `sum(a)` — contar: cruces, huecos y comprobaciones de rejilla.
    * `min(a)`, `max(a)` — REDUCCIÓN: el valor de pico dentro del tramo
      contiguo de un evento. Son `numpy.min`/`numpy.max`, funciones de nivel de
      módulo, no los métodos `ndarray.min()`/`.max()`.
    * `maximum(a, b)`, `minimum(a, b)` — ELEMENTO A ELEMENTO, entre dos arrays:
      es la operación con la que se duplica la tabla de extremos de
      `extremo_en_ventana`. La confusión con las dos anteriores es un riesgo
      real y por eso están documentadas juntas: `max` reduce un array a un
      escalar, `maximum` combina dos arrays. `expresiones.py` evita `maximum`
      con una máscara (`a * menor + b * (1 - menor)`) para no ampliar su
      protocolo; aquí no se hace lo mismo porque son cuatro operaciones de
      array en el camino más caliente del módulo (`log2(anchura)` pasadas) y
      porque esa máscara elige `b` cuando `a` es NaN, mientras que
      `numpy.maximum` propaga el NaN, que es lo honesto.

    Ni `where`, ni `clip`, ni `median`, ni ningún método de `ufunc` (`.at`,
    `.accumulate`, `.reduceat`): el acumulado máximo habría simplificado la
    histéresis, pero `numpy.maximum.accumulate` es un método de un `ufunc` y no
    un atributo del módulo, y ese es justo el requisito que hace que `numpy` en
    sí mismo satisfaga este protocolo (mismo razonamiento que en `malla.py`).
    """

    def searchsorted(self, a: Any, v: Any, side: str, /) -> Any: ...
    def abs(self, a: Any, /) -> Any: ...
    def cumsum(self, a: Any, /) -> Any: ...
    def arange(self, n: int, /) -> Any: ...
    def sum(self, a: Any, /) -> Any: ...
    def min(self, a: Any, /) -> Any: ...
    def max(self, a: Any, /) -> Any: ...
    def maximum(self, a: Any, b: Any, /) -> Any: ...
    def minimum(self, a: Any, b: Any, /) -> Any: ...


def _numpy() -> Vectorial:
    """Importa NumPy en el momento de usarlo, no al importar el módulo (mismo
    motivo que en `malla.py` y `expresiones.py`: el módulo se puede importar y
    probar sin NumPy instalado)."""
    import numpy

    return cast("Vectorial", numpy)


def _xp(xp: Vectorial | None) -> Vectorial:
    return xp if xp is not None else _numpy()


def _no(mascara: Any) -> Any:
    """Negación elemento a elemento de una máscara booleana.

    `mascara == 0` y no `~mascara`: el operador `~` obligaría a que toda
    implementación de `Vectorial` lo definiera (y sobre un `int` de Python
    significa otra cosa), mientras que la comparación con cero la dan gratis
    NumPy y cualquier vector mínimo. `== False` diría lo mismo pero lo prohíbe
    `ruff` (E712), con razón: en Python `1 == True`.
    """
    return mascara == 0


# --------------------------------------------------------------------------- #
# Datos de entrada y salida
# --------------------------------------------------------------------------- #
class Direccion(Enum):
    """De qué lado del umbral está la condición.

    No hay valor por omisión y no se deduce del orden de `entrada` y `salida`:
    deducirla haría que una configuración con los dos umbrales iguales
    (histéresis desactivada a propósito) fuera ambigua justo en el caso en que
    el usuario más quiere saber qué está pidiendo.
    """

    ARRIBA = "arriba"
    """Se entra al alcanzar `entrada` por arriba y se sale al bajar de `salida`
    (`salida <= entrada`). Sobretemperatura, duty alto, sobrepresión."""

    ABAJO = "abajo"
    """Se entra al bajar de `entrada` y se sale al subir de `salida`
    (`salida >= entrada`). Presión de aceite baja, tensión de batería baja."""


class Extremo(Enum):
    """Qué extremo de un tramo interesa: el máximo o el mínimo.

    Sin valor por omisión, porque el pico de un evento de presión de aceite
    baja es su MÍNIMO, y suponer el máximo daría un «valor de pico» que es el
    momento menos grave del evento.
    """

    MAXIMO = "maximo"
    MINIMO = "minimo"


@dataclass(slots=True, frozen=True)
class Serie:
    """Una serie de canal en unidad CANÓNICA, con su clase de conversión.

    `t_ms` son las marcas de tiempo de ESTA serie (ms desde el t0 del segmento,
    como `almacen.ChannelSeries.t`), que no tienen por qué coincidir con las de
    otro canal: eso es lo que resuelve `alinear`.

    `clase` NO tiene valor por omisión (regla 4 de `CLAUDE.md`). Un canal
    tal como sale del almacén es `Clase.PUNTO`; las transformaciones de este
    módulo devuelven otra clase (`derivada` -> `TASA`, `delta_de_contador` ->
    `INTERVALO`) y la comprueban al comparar contra un umbral: comparar un
    canal `PUNTO` con un umbral declarado sobre un `INTERVALO` es la trampa del
    delta con otro disfraz.

    `valido` es `None` en el caso normal —un canal en su propia rejilla no
    tiene huecos, porque un hueco es una marca de tiempo que no existe
    (`docs/01` §1.6)— y lleva máscara cuando la serie viene de `alinear` o de
    una transformación que no puede pronunciarse en todas las muestras.
    """

    t_ms: Any
    v: Any
    clase: Clase
    valido: Any = None

    def __post_init__(self) -> None:
        if len(self.t_ms) != len(self.v):
            raise ErrorDePrimitiva(
                f"la serie tiene {len(self.t_ms)} marcas de tiempo y {len(self.v)} valores"
            )
        if self.valido is not None and len(self.valido) != len(self.v):
            raise ErrorDePrimitiva(
                f"la máscara de validez tiene {len(self.valido)} elementos y la serie "
                f"{len(self.v)} valores"
            )

    def __len__(self) -> int:
        return len(self.t_ms)


@dataclass(slots=True, frozen=True)
class SerieDeBits:
    """Una máscara de bits por muestra (`Engine Protection Cause`, `Trigger
    System Errors`).

    Es un tipo aparte y **no tiene `clase` de conversión**, a propósito: una
    máscara de bits no es una medida y no se convierte nunca. Darle una clase
    sería afirmar que sus tres bits son tres kPa, y el sistema de unidades
    aceptaría la afirmación sin poder desmentirla.

    `bits` tiene que ser un array de enteros (`Storage.BITS_U32`), no de coma
    flotante: el `&` de la máscara no está definido sobre `float` ni en NumPy ni
    en Python, y eso es una ventaja, no un estorbo -- delata que alguien pasó
    un canal escalado donde iba uno crudo.
    """

    t_ms: Any
    bits: Any
    valido: Any = None

    def __post_init__(self) -> None:
        if len(self.t_ms) != len(self.bits):
            raise ErrorDePrimitiva(
                f"la serie tiene {len(self.t_ms)} marcas de tiempo y {len(self.bits)} máscaras"
            )

    def __len__(self) -> int:
        return len(self.t_ms)


@dataclass(slots=True, frozen=True)
class Condicion:
    """«Esto se cumple aquí», muestra a muestra, con lo que no se sabe aparte.

    Es la moneda común de las nueve primitivas: todas las que deciden algo
    devuelven una `Condicion`, y todo lo que produce eventos parte de una. Es lo
    que hace que el «Compuesto» de §4.3 sea una sola operación y no una por
    combinación de primitivas.

    `activa` y `valido` son dos máscaras y no una tercera etiqueta con tres
    valores porque las dos se combinan con operadores de array (`&`, `|`) y así
    la lógica de Kleene son cuatro líneas vectorizadas en vez de una tabla.
    Donde `valido` es falso, el valor de `activa` no significa nada.
    """

    t_ms: Any
    activa: Any
    valido: Any

    def __post_init__(self) -> None:
        if not len(self.t_ms) == len(self.activa) == len(self.valido):
            raise ErrorDePrimitiva(
                f"condición incoherente: {len(self.t_ms)} marcas, {len(self.activa)} "
                f"valores y {len(self.valido)} elementos de validez"
            )

    def __len__(self) -> int:
        return len(self.t_ms)

    def y(self, otra: Condicion, *, xp: Vectorial | None = None) -> Condicion:
        """AND de tres valores (Kleene): el «Compuesto» de §4.3.

        Cierta donde las dos son ciertas. Y —esto es lo que la validez estricta
        haría mal— **falsa con certeza donde una de las dos es falsa con
        certeza**, aunque la otra sea un hueco: si el régimen es de 800 rpm, «λ
        pobre Y rpm > 3000» no se cumple, y no hace falta saber cuánto valía λ
        para afirmarlo. Sin esto, D4 (cuatro roles, cada uno con su tasa) sería
        «no se sabe» en casi todo el log y su histéresis no serviría de nada.
        """
        xp = _xp(xp)
        _misma_rejilla(self.t_ms, otra.t_ms, xp=xp)
        activa = self.activa & otra.activa
        cierto_falso = (self.valido & _no(self.activa)) | (otra.valido & _no(otra.activa))
        return Condicion(
            t_ms=self.t_ms,
            activa=activa,
            valido=(self.valido & otra.valido) | cierto_falso,
        )

    def o(self, otra: Condicion, *, xp: Vectorial | None = None) -> Condicion:
        """OR de tres valores (Kleene). Cierta con certeza donde una de las dos
        lo es, aunque la otra falte."""
        xp = _xp(xp)
        _misma_rejilla(self.t_ms, otra.t_ms, xp=xp)
        activa = self.activa | otra.activa
        cierto_cierto = (self.valido & self.activa) | (otra.valido & otra.activa)
        return Condicion(
            t_ms=self.t_ms,
            activa=activa,
            valido=(self.valido & otra.valido) | cierto_cierto,
        )

    def no(self) -> Condicion:
        """Negación. Lo que no se sabe sigue sin saberse: `no` de un hueco es un
        hueco, nunca `True`.

        Es lo que convierte `banda` (§4.3 la define como «λ dentro de
        ventana») en el detector que hace falta, que es λ FUERA de la ventana,
        sin necesidad de una segunda primitiva que signifique lo contrario de
        la primera.
        """
        return Condicion(t_ms=self.t_ms, activa=_no(self.activa), valido=self.valido)


@dataclass(slots=True, frozen=True)
class Evento:
    """Un intervalo en el que la condición se cumplió el tiempo suficiente.

    Es la mitad del modelo de resultado de §4.3 —`{ tipo, severidad, t_inicio,
    t_fin, valor_pico, contexto }`— sin `tipo`, `severidad` ni `contexto`, que
    son de la configuración del detector (F3-07) y no del motor. Convertir un
    `Evento` en `detectores.Incidencia` es sumarle esas tres cosas.

    `t_inicio_ms` y `t_fin_ms` son las marcas de la PRIMERA y la ÚLTIMA muestra
    en que se observó la condición. La duración es la diferencia entre las dos,
    así que un evento de una sola muestra dura 0 s: no se le atribuye el
    intervalo hasta la muestra siguiente porque en ese intervalo no se observó
    nada (mismo criterio que la ventana de validez de la retención). La
    consecuencia, medida: un umbral con permanencia de 3 s sobre un canal a
    5 Hz necesita 16 muestras y no 15, y dispara un dt más tarde que un motor
    que contara el intervalo posterior. Errar del lado de avisar tarde, y no
    del de avisar antes de haberlo visto, es la única de las dos que no inventa.

    Un evento **no contiene huecos** por construcción: una muestra no válida
    interrumpe la carrera (ver la cabecera del módulo).
    """

    t_inicio_ms: float
    t_fin_ms: float
    i_inicio: int
    i_fin: int
    n_muestras: int
    valor_pico: float | None = None
    clase_valor: Clase | None = None
    """La clase de conversión de `valor_pico`, para que quien lo pinte lo
    convierta como lo que es. `None` cuando no se pidió pico. Va aquí y no en
    un `dict[str, float]` porque un diccionario de números no puede llevar la
    clase de cada número, y ese es exactamente el camino por el que la trampa
    del delta llega al panel de incidencias."""

    @property
    def duracion_s(self) -> float:
        """Segundos observados entre la primera y la última muestra del evento."""
        return (self.t_fin_ms - self.t_inicio_ms) / MS_POR_S


@dataclass(slots=True, frozen=True)
class Pico:
    """De dónde sale el `valor_pico` de un evento, y qué extremo es.

    Es un parámetro explícito y no «el canal de la condición» porque una
    condición compuesta no tiene un canal: D4 mezcla λ, objetivo, mariposa y
    régimen, y el número que el tuner quiere ver es el λ, no el régimen. El
    criterio: **el canal que el usuario lee**, que es también el que da sentido
    a la unidad del evento.
    """

    serie: Serie
    extremo: Extremo


# --------------------------------------------------------------------------- #
# Umbrales configurables (data/umbrales.toml)
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class Permanencia:
    """Cuánto tiene que durar una condición para ser un evento. **Sin valores
    por omisión en el código.**

    Regla 3 de `CLAUDE.md`: los valores viven en `data/umbrales.toml`
    (`[general].permanencia_s`, `[general].muestras_minimas` y
    `[motor_de_deteccion].maximo_de_eventos`), con la precedencia de siempre
    —anulación por canal > perfil activo > preferencias de usuario > fichero—,
    que resuelve quien llama y se aplica con `fusionar`. `desde_mapa` exige las
    tres claves y falla si falta alguna: un valor por omisión en el código es
    una copia del fichero que puede desincronizarse sin que nada se ponga en
    rojo, y una excepción no.

    Las DOS condiciones se exigen a la vez, que es lo que §4.3 quiere decir con
    «3 muestras o 100 ms, el mayor de los dos»: sobre un canal a 20 Hz manda el
    número de muestras (3 muestras son 106 ms) y sobre uno a 5 Hz manda también
    (3 muestras son 606 ms), mientras que sobre un canal rápido de 100 Hz
    mandarían los 100 ms. Exigir solo el mayor de los dos *valores* no se puede:
    uno está en segundos y el otro en muestras, y la equivalencia depende de la
    tasa del canal, que cambia entre grupos de muestreo dentro del mismo log.
    """

    permanencia_s: float
    muestras_minimas: int
    maximo_de_eventos: int
    """Tope de eventos que una sola llamada puede devolver. No es un umbral de
    física: es lo que mantiene acotado el único bucle de Python de este módulo
    (ver ADR-009 en la cabecera) y lo que convierte «una configuración que
    genera ruido» en un error explicado en vez de en 200 000 filas que nadie
    va a leer."""

    def __post_init__(self) -> None:
        if self.permanencia_s < 0.0:
            raise ErrorDePrimitiva(
                f"permanencia_s = {self.permanencia_s!r} no puede ser negativa; "
                "0 significa «sin permanencia», que es lo que piden los detectores de "
                "contador (D1, D12)"
            )
        if self.muestras_minimas < 1:
            raise ErrorDePrimitiva(
                f"muestras_minimas = {self.muestras_minimas!r} tiene que ser >= 1: con 0 "
                "una condición que no se cumple en ninguna muestra sería un evento"
            )
        if self.maximo_de_eventos < 1:
            raise ErrorDePrimitiva(
                f"maximo_de_eventos = {self.maximo_de_eventos!r} tiene que ser >= 1"
            )

    @property
    def permanencia_ms(self) -> float:
        """La permanencia en ms, que es la unidad de `t` (`docs/01` §1.6)."""
        return self.permanencia_s * MS_POR_S

    @classmethod
    def desde_mapa(cls, mapa: Mapping[str, Any]) -> Permanencia:
        """Construye la permanencia desde `data/umbrales.toml` ya parseado por
        quien llama (ADR-002), con las capas de precedencia ya fusionadas.

        Una clave ausente es un error, no un valor por omisión: ver el docstring
        de la clase.
        """
        claves = ("permanencia_s", "muestras_minimas", "maximo_de_eventos")
        faltan = [c for c in claves if c not in mapa]
        if faltan:
            raise ErrorDePrimitiva(
                "data/umbrales.toml no declara: "
                + ", ".join(faltan)
                + "; son umbrales configurables y este módulo no lleva copia de ellos "
                "([general] da los dos primeros y [motor_de_deteccion] el tercero)"
            )
        return cls(
            permanencia_s=float(mapa["permanencia_s"]),
            muestras_minimas=int(mapa["muestras_minimas"]),
            maximo_de_eventos=int(mapa["maximo_de_eventos"]),
        )

    def fusionar(self, anulaciones: Mapping[str, Any]) -> Permanencia:
        """Esta permanencia con las claves de `anulaciones` sustituidas.

        Es la pieza de la precedencia de `data/umbrales.toml` que le
        corresponde a este módulo: quien conoce el perfil activo, las
        preferencias del usuario y las anulaciones por canal las aplica de menor
        a mayor prioridad. Una clave desconocida es un error, porque un nombre
        mal escrito se ignoraría en silencio y el umbral seguiría siendo el de
        por omisión sin que nadie se enterara.
        """
        if not anulaciones:
            return self
        base: dict[str, Any] = {
            "permanencia_s": self.permanencia_s,
            "muestras_minimas": self.muestras_minimas,
            "maximo_de_eventos": self.maximo_de_eventos,
        }
        desconocidas = set(anulaciones) - set(base)
        if desconocidas:
            raise ErrorDePrimitiva(
                f"anulaciones de permanencia desconocidas: {sorted(desconocidas)}; "
                "un nombre mal escrito se ignoraría en silencio y el umbral seguiría "
                "siendo el de por omisión"
            )
        base.update(anulaciones)
        return Permanencia.desde_mapa(base)


# --------------------------------------------------------------------------- #
# Piezas internas compartidas
# --------------------------------------------------------------------------- #
def _misma_rejilla(a_t: Any, b_t: Any, *, xp: Vectorial) -> None:
    """Dos series solo se combinan si están en la misma rejilla de tiempo.

    La longitud no basta: dos canales de grupos de muestreo distintos pueden
    tener el mismo número de muestras en instantes distintos
    (`grupos_muestreo.py` lo dice explícitamente: «comparten cuántas, no
    cuáles»), y combinarlos daría una detección plausible y falsa. Cuando los
    dos arrays no son el mismo objeto —dentro de un grupo de muestreo `t` se
    comparte por referencia (ADR-003), así que el caso normal se resuelve sin
    comparar nada— se comparan de verdad, en una pasada de C que no se nota al
    lado del resto del cálculo.
    """
    if len(a_t) != len(b_t):
        raise ErrorDePrimitiva(
            f"las dos series están en rejillas distintas ({len(a_t)} y {len(b_t)} "
            "muestras); alinéalas antes con `alinear`"
        )
    if a_t is b_t:
        return
    if int(xp.sum(a_t != b_t)) != 0:
        raise ErrorDePrimitiva(
            "las dos series tienen el mismo número de muestras pero en instantes "
            "distintos (grupos de muestreo distintos); alinéalas antes con `alinear`"
        )


def _valido_de(serie: Serie | SerieDeBits) -> Any:
    """La máscara de validez de una serie, materializada.

    `t == t` es un vector de `True` de la longitud correcta sin pedirle `ones`
    al protocolo: `t` son milisegundos enteros desde el t0 del segmento y nunca
    es NaN. Es el mismo truco que `malla.py` usa con el signo cambiado
    (`valores == valores` para detectar NaN sin `isnan`).
    """
    if serie.valido is not None:
        return serie.valido
    return serie.t_ms == serie.t_ms


def _operando(limite: float | Serie, serie: Serie, *, xp: Vectorial) -> tuple[Any, Any]:
    """Un umbral, sea escalar o canal, como `(valores, valido)`.

    Un umbral escalar es un número en canónica y vale en todas las muestras. Un
    umbral que es OTRO CANAL —el `Knock Threshold` de la ECU en D2, el
    `Overboost Cut Max Pressure` en D6, el objetivo de λ en D4— tiene que estar
    ya en la rejilla de la serie (con `alinear`) y aporta su propia validez: si
    el umbral falta en una muestra, la comparación no se puede hacer ahí, y
    decidir con el último umbral conocido sin límite de validez es exactamente
    lo que §4.5 prohíbe.

    La clase de conversión del umbral tiene que coincidir con la de la serie.
    Comparar un canal `PUNTO` con un umbral declarado sobre un `INTERVALO` es
    la trampa del delta: «la temperatura ha subido más de 10 K» y «la
    temperatura pasa de 10 K» son dos frases distintas y las dos se escriben
    con el mismo número. Un umbral escalar hereda la clase de la serie: no hay
    dónde declararla y no hace falta, porque el escalar solo se compara con
    esta serie.
    """
    if isinstance(limite, Serie):
        _misma_rejilla(limite.t_ms, serie.t_ms, xp=xp)
        if limite.clase is not serie.clase:
            raise ErrorDePrimitiva(
                f"el umbral es una serie de clase {limite.clase.value} y el canal es de "
                f"clase {serie.clase.value}: comparar un punto con un intervalo (o al "
                "revés) es la trampa del delta"
            )
        return limite.v, _valido_de(limite)
    return float(limite), None


def _y_valido(base: Any, otro: Any) -> Any:
    """`base & otro`, tolerando que `otro` sea `None` (un umbral escalar)."""
    return base if otro is None else base & otro


def _viola_el_orden(entrada: Any, salida: Any, direccion: Direccion, *, xp: Vectorial) -> bool:
    """¿La histéresis está al revés en alguna muestra?

    Con `salida` por encima de `entrada` en un umbral `ARRIBA`, la condición
    entra y no puede salir nunca: un evento que empieza y no termina, que en el
    panel de incidencias aparece como «desde el minuto 3 hasta el final del
    log». Es un fallo de configuración silencioso y por eso se comprueba, tanto
    si el umbral es un escalar como si es otro canal.
    """
    peor = (salida > entrada) if direccion is Direccion.ARRIBA else (salida < entrada)
    if isinstance(peor, bool):
        return peor
    return int(xp.sum(peor)) != 0


def _estado_con_histeresis(
    v: Any,
    valido: Any,
    entrada: Any,
    salida: Any,
    direccion: Direccion,
    *,
    xp: Vectorial,
) -> Any:
    """El autómata de dos umbrales (Schmitt trigger), vectorizado.

    CÓMO SE VECTORIZA UNA MEMORIA
    -----------------------------
    El estado en la muestra `i` depende de la historia, así que no sale de una
    comparación elemento a elemento. Pero solo depende de UNA cosa de la
    historia: de la última muestra que decidió algo. Una muestra decide cuando
    alcanza el umbral de entrada o el de salida; entre los dos umbrales —la
    zona de histéresis— no decide nada y el estado se mantiene.

    Así que el estado es una RETENCIÓN, el mismo problema que el multi-tasa de
    §4.5, y se resuelve igual: `cumsum(decisiva)` dice cuántas muestras
    decisivas hay hasta cada posición, así que `cumsum - 1` es el índice, dentro
    de las decisivas compactadas, de la última que decidió. Dos pasadas en C y
    ninguna variable de estado.

    Antes de la primera muestra decisiva el estado es «fuera». Es la única
    respuesta que no inventa: un evento no empieza hasta que la señal alcanza
    de verdad el umbral de entrada, y suponer lo contrario haría que un log que
    empieza con el motor ya caliente abriera un evento en la muestra 0 sin
    haber visto ningún cruce.

    EMPATE: MANDA LA ENTRADA
    ------------------------
    Con `salida == entrada` (histéresis desactivada a propósito) una muestra
    exactamente en el umbral cumple las dos condiciones. Gana la entrada, así
    que el umbral desnudo se comporta como `v >= entrada`, que es lo que
    cualquiera espera al leer la configuración. Sale gratis: `compacta` guarda
    el valor de `entra`.

    Una muestra no válida no decide: no se sabe cuánto valía, y dejar que un
    hueco cierre o abra un evento sería inventar el cruce.
    """
    if direccion is Direccion.ARRIBA:
        entra = v >= entrada
        sale = v <= salida
    else:
        entra = v <= entrada
        sale = v >= salida
    entra = entra & valido
    sale = sale & valido
    decisiva = entra | sale

    orden = xp.cumsum(decisiva)
    hay = orden > 0
    if int(xp.sum(decisiva)) == 0:
        # Ninguna muestra llegó a decidir: `hay` ya es el vector de `False` de
        # la longitud correcta, y compactar un array vacío no tendría índice
        # válido que consultar.
        return hay
    compacta = entra[decisiva]
    # El índice -1 de las muestras anteriores a la primera decisiva se lleva a 0
    # sumando la propia máscara (mismo recurso que en `alinear_por_retencion`):
    # el valor leído ahí se descarta con `hay`, así que da igual cuál sea.
    indice = orden - 1 + (orden == 0)
    return hay & compacta[indice]


def _condicion_de_umbral(
    serie: Serie,
    *,
    entrada: Any,
    valido_entrada: Any,
    salida: Any,
    valido_salida: Any,
    direccion: Direccion,
    xp: Vectorial,
) -> Condicion:
    """El cuerpo compartido de `umbral_con_histeresis` y `banda`.

    Existe para que la histéresis tenga UNA implementación. `banda` es dos
    umbrales con histéresis compuestos con `y`, y si tuviera su propio autómata
    habría dos formas de expresar «λ fuera de la ventana» que podrían
    divergir.
    """
    if _viola_el_orden(entrada, salida, direccion, xp=xp):
        flecha = "<=" if direccion is Direccion.ARRIBA else ">="
        raise ErrorDePrimitiva(
            f"histéresis al revés: con dirección {direccion.value} tiene que cumplirse "
            f"salida {flecha} entrada. Un umbral que se abre y no se cierra produce un "
            "evento que dura hasta el final del log"
        )
    valido = _y_valido(_y_valido(_valido_de(serie), valido_entrada), valido_salida)
    activa = _estado_con_histeresis(serie.v, valido, entrada, salida, direccion, xp=xp)
    return Condicion(t_ms=serie.t_ms, activa=activa, valido=valido)


# --------------------------------------------------------------------------- #
# Transformaciones: Serie -> Serie
# --------------------------------------------------------------------------- #
def alinear(
    serie: Serie,
    t_destino: Any,
    *,
    ventana_validez_ms: float,
    xp: Vectorial | None = None,
) -> Serie:
    """Lleva una serie a otra rejilla de tiempo por retención del último valor.

    Es el multi-tasa de `docs/01` §1.6 y `docs/04` §4.5, y NO se reimplementa
    aquí: delega en `expresiones.alinear_por_retencion` (F3-18), que ya tomó la
    decisión y la argumentó. Un canal a 5 Hz comparado con uno a 20 Hz se
    retiene, con límite de validez, y fuera de ese límite el resultado es hueco
    en lugar de un número inventado.

    La retención NO cambia la clase de conversión: sostener un punto da un
    punto. Y la validez del valor retenido es la del valor que se retiene, así
    que la máscara de la serie de origen se alinea también —retener un valor
    que ya era un hueco no lo convierte en dato— con una segunda llamada a la
    misma función. Son dos `searchsorted` donde uno bastaría; se prefiere
    reutilizar la función que ya está probada a escribir una versión propia
    para ahorrar una pasada.
    """
    xp = _xp(xp)
    valores, dentro_de_ventana = alinear_por_retencion(
        serie.t_ms, serie.v, t_destino, ventana_validez_ms=ventana_validez_ms, xp=xp
    )
    validez_origen, _ = alinear_por_retencion(
        serie.t_ms,
        _valido_de(serie),
        t_destino,
        ventana_validez_ms=ventana_validez_ms,
        xp=xp,
    )
    return Serie(
        t_ms=t_destino,
        v=valores,
        clase=serie.clase,
        valido=dentro_de_ventana & validez_origen,
    )


def derivada(serie: Serie, *, ventana_s: float, xp: Vectorial | None = None) -> Serie:
    """Derivada sobre una ventana temporal, en canónica por segundo.

    §4.3 la usa para el tip-in (`Throttle Position Derivative`), la caída de
    presión y la subida de temperatura. La ventana la exige la propia naturaleza
    del dato: la diferencia entre dos muestras consecutivas de un canal a 20 Hz
    amplifica el ruido de cuantización por 20, y sobre el AutoLog —que es
    bimodal, con dt de 35 a 499 ms (`docs/01` §1.7)— ni siquiera es la misma
    magnitud de una muestra a la siguiente.

    QUÉ DERIVADA, EXACTAMENTE
    -------------------------
    Diferencia entre el valor actual y el de la primera muestra que todavía cae
    dentro de la ventana, dividida por el tiempo real transcurrido entre las
    dos. Los límites de la ventana salen de un `searchsorted` sobre `t`, así que
    **no se asume muestreo uniforme** en ningún punto (`docs/01` §1.7 lo
    prohíbe explícitamente para las derivadas).

    Es una derivada HACIA ATRÁS, no centrada, y es una decisión: un detector
    tiene que dispararse cuando la evidencia existe, no media ventana antes. Con
    una derivada centrada, el flanco de un tip-in aparecería fechado antes del
    tip-in, y la «ventana siguiente» de D15 empezaría a contar sobre muestras
    anteriores al propio flanco.

    No es un ajuste por mínimos cuadrados sobre la ventana, que sería más
    robusto al ruido. Se ha dejado fuera a propósito: exige sumas móviles de
    productos (vectorizables con `cumsum`, pero con su propia aritmética) y
    §4.3 no lo pide. Si el banco demuestra que la derivada de dos puntos
    produce falsos positivos en el tip-in, ese es el refinamiento, y cambia
    esta función sin cambiar la API.

    LA CLASE CAMBIA: `TASA`
    -----------------------
    Una derivada es una tasa (regla 4 de `CLAUDE.md`), y por eso el resultado no
    se puede volver a derivar: `Clase` no tiene un miembro para la segunda
    derivada, y devolver `TASA` otra vez sería mentir sobre lo que hay en el
    array. La `VARIANZA` queda fuera por lo mismo.
    """
    xp = _xp(xp)
    if serie.clase not in (Clase.PUNTO, Clase.INTERVALO):
        raise ErrorDePrimitiva(
            f"no se puede derivar una serie de clase {serie.clase.value}: el resultado "
            "no tendría una clase de conversión que declarar (`Clase` no tiene segunda "
            "derivada), y devolver TASA otra vez sería mentir sobre lo que hay en el array"
        )
    if ventana_s <= 0.0:
        raise ErrorDePrimitiva(
            f"la ventana de la derivada tiene que ser positiva, se dio {ventana_s!r}"
        )
    t = serie.t_ms
    # `- ventana_s * MS_POR_S` es un `float` de Python a propósito: `t` es
    # uint32 (ms desde el t0 del segmento) y la promoción de tipos de NumPy lo
    # lleva a float64 antes de restar. Sin eso, una ventana mayor que el
    # instante actual daría la vuelta al entero sin signo y las primeras
    # muestras del log buscarían su origen al final.
    inicio = xp.searchsorted(t, t - ventana_s * MS_POR_S, "left")
    dt_s = (t - t[inicio]) / MS_POR_S
    hay_ventana = dt_s > 0
    # Divisor seguro: donde no hay ninguna muestra anterior dentro de la ventana
    # se divide por 1 en vez de por 0. El resultado se descarta con `valido`
    # (mismo recurso que el divisor de `malla.construir_malla`).
    divisor = dt_s + _no(hay_ventana)
    validez = _valido_de(serie)
    return Serie(
        t_ms=t,
        v=(serie.v - serie.v[inicio]) / divisor,
        clase=Clase.TASA,
        valido=validez & validez[inicio] & hay_ventana,
    )


def delta_de_contador(serie: Serie, *, xp: Vectorial | None = None) -> Serie:
    """Incremento por muestra de un contador acumulado.

    Es la primitiva de D1 y de la mitad de D12: `Knock Sensor N Knock Count`
    llega hasta 50 000 y «un gráfico de la señal cruda es una escalera
    ilegible» (§4.2 P2). Lo que hay que ver, y sobre lo que dispara el detector,
    es el delta.

    DOS MUESTRAS SIN DELTA MEDIBLE, Y LAS DOS SON HUECO
    ---------------------------------------------------
    * **La primera muestra del log.** No hay anterior, así que no hay
      incremento. Cero sería una afirmación («aquí no hubo knock») que nadie ha
      observado.
    * **Un contador que baja.** La ECU se reinició, el log se cortó o el
      contador dio la vuelta. El incremento real es desconocido —al menos el
      valor actual, y quizá 50 000 más— y un delta negativo no es un evento de
      knock. El valor se deja tal cual, negativo y a la vista, con la validez a
      falso: sustituirlo por 0 escondería el reinicio, y saber que el contador
      se reinició es información de diagnóstico, no ruido.

    LA CLASE CAMBIA: `INTERVALO`
    ----------------------------
    Un incremento es una diferencia (regla 4). Sobre un contador de knock, que
    es adimensional, dará igual; sobre un contador con unidad —un totalizador de
    combustible— convertir el delta como punto es la trampa del delta exacta.
    """
    xp = _xp(xp)
    if serie.clase is not Clase.PUNTO:
        raise ErrorDePrimitiva(
            f"el delta de un contador se toma sobre una serie de clase PUNTO, no "
            f"{serie.clase.value}: un contador acumulado es un valor absoluto"
        )
    n = len(serie)
    idx = xp.arange(n)
    primera = idx == 0
    anterior = idx - 1 + primera
    delta = serie.v - serie.v[anterior]
    validez = _valido_de(serie)
    return Serie(
        t_ms=serie.t_ms,
        v=delta,
        clase=Clase.INTERVALO,
        valido=validez & validez[anterior] & _no(primera) & (delta >= 0),
    )


def extremo_en_ventana(
    serie: Serie,
    *,
    desde_s: float,
    hasta_s: float,
    extremo: Extremo,
    xp: Vectorial | None = None,
) -> Serie:
    """El máximo (o el mínimo) del canal en una ventana temporal relativa a cada
    muestra.

    La ventana va de `t + desde_s` a `t + hasta_s`, los dos inclusive, y los dos
    pueden ser negativos: `desde_s=-0.25, hasta_s=+0.25` es una ventana centrada
    de medio segundo, y `desde_s=0.0, hasta_s=0.5` es «los próximos 500 ms»,
    que es la ventana que pide el detector de excursión de λ en tip-in (P5 y
    D15: «se mide la desviación máxima de λ en la ventana siguiente»).

    Es la maquinaria de ventana de `pico_local`, expuesta porque es también la
    de D15, y porque una segunda implementación de lo mismo dentro del detector
    sería la puerta a que un pico signifique dos cosas distintas. No es una
    décima primitiva: devuelve una `Serie`, no una `Condicion`, así que no
    decide nada por sí sola.

    CÓMO SE VECTORIZA UNA VENTANA DE ANCHURA VARIABLE
    -------------------------------------------------
    Los límites exactos de la ventana de cada muestra salen de dos
    `searchsorted` sobre `t`: una pasada en C, sin asumir muestreo uniforme
    (`docs/01` §1.7). Lo que no sale de ahí es el extremo dentro de esos
    límites, porque cada muestra tiene su propia anchura.

    La solución es una **tabla dispersa de extremos** construida por
    duplicación: `tabla[p][i]` es el extremo de `v[i : i + 2**p]`, y cada nivel
    se obtiene del anterior con un `maximum`/`minimum` elemento a elemento entre
    dos vistas desplazadas. Con la tabla, el extremo de cualquier rango se
    resuelve con DOS consultas solapadas de anchura `2**p`, siendo `p` el mayor
    entero con `2**p <= anchura` -- que es lo que devuelve un `searchsorted`
    sobre las potencias de dos.

    Coste: `log2(anchura)` pasadas para construir la tabla y un bucle sobre
    NIVELES (media docena; para una ventana de medio segundo a 20 Hz son cuatro)
    para consultarla. Ni un bucle sobre muestras, y el coste no depende de la
    anchura de la ventana más que logarítmicamente. La memoria sí: `log2(a)`
    arrays del tamaño del canal, que para un canal de un log de 40 min a 20 Hz
    (48 000 muestras) son cuatro arrays de 48 000, no de los 73 M de muestras
    del log entero -- un canal no es el log.

    UNA VENTANA RECORTADA ES UN HUECO
    ---------------------------------
    En las muestras cuya ventana se sale del log —las primeras si `desde_s` es
    negativo, las últimas si `hasta_s` es positivo— el extremo se calcularía
    sobre una ventana más corta, y eso no es lo mismo: el valor que falta podría
    ser mayor. Salen como hueco, con el mismo criterio que la retención («antes
    de la primera muestra no hay nada que retener»). Lo mismo para las ventanas
    que no contienen ninguna muestra, que pueden aparecer cuando `desde_s` es
    positivo.
    """
    xp = _xp(xp)
    if hasta_s < desde_s:
        raise ErrorDePrimitiva(
            f"la ventana va de desde_s={desde_s!r} a hasta_s={hasta_s!r}, que está antes"
        )
    n = len(serie)
    t = serie.t_ms
    validez = _valido_de(serie)
    if n == 0:
        return Serie(t_ms=t, v=serie.v, clase=serie.clase, valido=validez)

    # Los dos desplazamientos son `float` de Python (ver la nota de `derivada`):
    # `t` es uint32 y una ventana que empieza antes del t0 daría la vuelta al
    # entero sin signo.
    t_desde = t + desde_s * MS_POR_S
    t_hasta = t + hasta_s * MS_POR_S
    inicio = xp.searchsorted(t, t_desde, "left")
    fin = xp.searchsorted(t, t_hasta, "right")  # exclusivo
    anchura = fin - inicio
    hay_muestras = anchura > 0
    completa = (t_desde >= t[0]) & (t_hasta <= t[n - 1])

    # Índices seguros para las ventanas vacías o que se salen por el final: el
    # resultado de esas muestras se descarta con `valido`, pero la consulta a la
    # tabla tiene que caer dentro del array de todas formas.
    anchura_segura = anchura + _no(hay_muestras)
    inicio_seguro = inicio - (inicio == n)
    fin_seguro = inicio_seguro + anchura_segura

    ancho_maximo = int(xp.max(anchura_segura))
    tabla = _tabla_de_extremos(serie.v, ancho_maximo, extremo, xp=xp)
    potencias = [1 << p for p in range(len(tabla))]
    nivel = xp.searchsorted(potencias, anchura_segura, "right") - 1

    combinar = xp.maximum if extremo is Extremo.MAXIMO else xp.minimum
    salida = anchura * 0.0 + float("nan")
    for p, bloque in enumerate(potencias):  # bucle sobre NIVELES, no sobre muestras
        elegidas = nivel == p
        if int(xp.sum(elegidas)) == 0:
            continue
        izquierda = tabla[p][inicio_seguro[elegidas]]
        derecha = tabla[p][fin_seguro[elegidas] - bloque]
        salida[elegidas] = combinar(izquierda, derecha)

    return Serie(
        t_ms=t,
        v=salida,
        clase=serie.clase,
        valido=validez & hay_muestras & completa,
    )


def _tabla_de_extremos(v: Any, ancho_maximo: int, extremo: Extremo, *, xp: Vectorial) -> list[Any]:
    """`tabla[p][i]` = extremo de `v[i : i + 2**p]`, para `2**p <= ancho_maximo`.

    Cada nivel sale del anterior combinando dos vistas desplazadas
    (`maximum(m[:-paso], m[paso:])`), así que el nivel `p` tiene
    `n - 2**p + 1` elementos y la consulta nunca se sale: una ventana de
    anchura `a >= 2**p` empieza como muy tarde en `n - a <= n - 2**p`.

    El bucle es sobre NIVELES (`log2(ancho_maximo)`, media docena), no sobre
    muestras. Cada iteración es una operación de array completa.
    """
    combinar = xp.maximum if extremo is Extremo.MAXIMO else xp.minimum
    tabla = [v]
    paso = 1
    while paso * 2 <= ancho_maximo:
        anterior = tabla[-1]
        tabla.append(combinar(anterior[:-paso], anterior[paso:]))
        paso *= 2
    return tabla


# --------------------------------------------------------------------------- #
# Primitivas de condición: Serie -> Condicion
# --------------------------------------------------------------------------- #
def umbral_con_histeresis(
    serie: Serie,
    *,
    entrada: float | Serie,
    salida: float | Serie,
    direccion: Direccion,
    xp: Vectorial | None = None,
) -> Condicion:
    """Umbral con histéresis: la primitiva de la que cuelgan doce de los 18
    detectores.

    `entrada` es el valor que abre la condición y `salida` el que la cierra, los
    dos en unidad CANÓNICA. Con `direccion=ARRIBA` tiene que cumplirse
    `salida <= entrada`; con `ABAJO`, `salida >= entrada`. Declarar los dos
    iguales desactiva la histéresis a propósito y queda escrito en la
    configuración, que es donde se puede discutir.

    POR QUÉ LOS DOS UMBRALES SON ABSOLUTOS Y NO UNO MÁS UNA FRACCIÓN
    ----------------------------------------------------------------
    `data/umbrales.toml` declara `[general].histeresis_relativa = 0,02` como
    «fracción del umbral que hay que recorrer de vuelta». Sobre una magnitud sin
    origen desplazado —una fracción de duty, una presión absoluta— eso está bien
    definido. Sobre una temperatura NO: el 2 % del umbral canónico de D9
    (378,15 K) son 7,6 K, así que la alarma de refrigerante no se cerraría hasta
    los 97,4 °C, mientras que el 2 % del mismo umbral leído en °C serían 2,1 K.
    El número depende de la unidad en la que se mire, y eso es la definición de
    un número mal especificado.

    Así que esta función no acepta fracciones: acepta el umbral de salida, en
    canónica, y quien configure el detector decide de dónde sale. `banda` sí
    puede usar la fracción, porque una banda tiene una anchura propia —un
    INTERVALO— y una fracción de una anchura no depende del origen.

    UN UMBRAL PUEDE SER OTRO CANAL
    ------------------------------
    `entrada` y `salida` aceptan una `Serie` ya alineada, y es lo que hace falta
    en cuatro detectores: D2 compara el nivel de knock con el umbral de la
    propia ECU («comparar contra un valor fijo daría falsos positivos a alta
    carga, porque el umbral de la ECU sube con la carga»), D4 y D5 con el
    objetivo de λ, D6 con el corte por sobrepresión, D10 con la curva de presión
    mínima en función del régimen.

    El criterio para elegir entre umbral-canal y canal derivado, cuando las dos
    cosas dan el mismo veredicto: **la serie es lo que el usuario lee y el
    umbral es lo que dice la configuración**. D2 se escribe con el nivel de
    knock como serie y el umbral de la ECU como umbral, no con la diferencia
    entre los dos como serie, porque el `valor_pico` del evento tiene que ser el
    nivel de knock en dB —el número que el tuner reconoce— y no un exceso sobre
    un umbral que se mueve. Cuando la magnitud de interés SÍ es la derivada
    (el λ error, el error de boost, el delta de un contador), entonces la
    serie es la derivada y el umbral un escalar.
    """
    xp = _xp(xp)
    v_entrada, valido_entrada = _operando(entrada, serie, xp=xp)
    v_salida, valido_salida = _operando(salida, serie, xp=xp)
    return _condicion_de_umbral(
        serie,
        entrada=v_entrada,
        valido_entrada=valido_entrada,
        salida=v_salida,
        valido_salida=valido_salida,
        direccion=direccion,
        xp=xp,
    )


def banda(
    serie: Serie,
    *,
    minimo: float | Serie,
    maximo: float | Serie,
    histeresis_relativa: float,
    xp: Vectorial | None = None,
) -> Condicion:
    """Condición «el canal está DENTRO de la banda `[minimo, maximo]`».

    Dentro, como en §4.3 («λ dentro de ventana»), y no fuera: el detector que
    hace falta casi siempre es el contrario, y se escribe `.no()`. Tener las dos
    como primitivas distintas sería tener dos sitios donde equivocarse con la
    histéresis.

    `minimo` y `maximo` pueden ser canales ya alineados, que es el caso de la
    banda de mezcla: el objetivo de λ se mueve con la carga, así que la banda es
    `objetivo x 0,93` a `objetivo x 1,04` y no dos números.

    LA HISTÉRESIS DE UNA BANDA SÍ PUEDE SER RELATIVA
    ------------------------------------------------
    Es la única de las nueve primitivas donde `[general].histeresis_relativa`
    está bien definida, y por eso es la única que la acepta: la fracción se
    aplica a la ANCHURA de la banda (`maximo - minimo`), que es un INTERVALO, y
    una fracción de un intervalo no depende de dónde esté el origen de la escala
    —el 2 % de una banda de 10 K son 0,2 K se mire en kelvin o en grados
    Celsius—. Aplicarla al valor del umbral, como haría un umbral simple, sí
    depende (ver `umbral_con_histeresis`).

    El margen ENSANCHA la banda al salir: una vez dentro, hay que rebasar
    `minimo - margen` o `maximo + margen` para salir. Es lo que evita la ráfaga
    de eventos de una λ que roza el borde de su banda objetivo.
    """
    xp = _xp(xp)
    if not 0.0 <= histeresis_relativa < 1.0:
        raise ErrorDePrimitiva(
            f"histeresis_relativa = {histeresis_relativa!r} tiene que ser una fracción "
            "en [0, 1) de la anchura de la banda; con 1 el margen sería la banda entera"
        )
    v_min, valido_min = _operando(minimo, serie, xp=xp)
    v_max, valido_max = _operando(maximo, serie, xp=xp)
    # Mismo comprobante que la histéresis al revés, con los papeles cambiados:
    # `salida > entrada` con entrada = máximo y salida = mínimo es «el mínimo
    # está por encima del máximo».
    if _viola_el_orden(v_max, v_min, Direccion.ARRIBA, xp=xp):
        raise ErrorDePrimitiva(
            "la banda tiene el mínimo por encima del máximo en alguna muestra: "
            "no hay ningún valor dentro de ella"
        )
    margen = (v_max - v_min) * histeresis_relativa
    por_encima_del_minimo = _condicion_de_umbral(
        serie,
        entrada=v_min,
        valido_entrada=valido_min,
        salida=v_min - margen,
        valido_salida=valido_min,
        direccion=Direccion.ARRIBA,
        xp=xp,
    )
    por_debajo_del_maximo = _condicion_de_umbral(
        serie,
        entrada=v_max,
        valido_entrada=valido_max,
        salida=v_max + margen,
        valido_salida=valido_max,
        direccion=Direccion.ABAJO,
        xp=xp,
    )
    return por_encima_del_minimo.y(por_debajo_del_maximo, xp=xp)


def pico_local(
    serie: Serie,
    *,
    prominencia_minima: float,
    ventana_s: float,
    xp: Vectorial | None = None,
) -> Condicion:
    """Picos reales, no ruido: máximos locales con prominencia mínima.

    Una muestra es pico si es el máximo de su ventana centrada de `ventana_s` y
    si sobresale al menos `prominencia_minima` por encima del mínimo de esa
    misma ventana. Las dos condiciones son necesarias: sin la segunda, cualquier
    diente de sierra del ruido de cuantización es un máximo local; sin la
    primera, un tramo en subida cumpliría la prominencia sin haber llegado a
    ningún pico.

    `prominencia_minima` es un INTERVALO, no un punto (regla 4): es una
    diferencia entre dos valores del canal. Es, junto con el delta de contador,
    la única magnitud de la tabla de §4.3 que no es un valor absoluto, y quien
    la edite en la unidad activa tiene que declarar `Clase.INTERVALO` o una
    prominencia de 10 K aparecerá como −263,15 °C.

    QUÉ PROMINENCIA, EXACTAMENTE
    ----------------------------
    La prominencia de este módulo se mide **dentro de la ventana**, no
    buscando hacia fuera la primera muestra más alta (que es lo que hace
    `scipy.signal.peak_prominences`). La definición de fuera es mejor y no
    tiene ventana que elegir, pero exige recorrer las muestras hacia los lados
    una a una hasta encontrar una mayor, y eso es un bucle por muestra en
    Python: ADR-009 lo prohíbe y no hay forma de vectorizarlo sin una pila
    monótona, que es el mismo bucle con otro nombre. Con ventana el resultado
    depende de la ventana, y por eso la ventana es configurable y explícita en
    vez de estar cableada.

    Un tramo plano en el máximo produce varias muestras «pico» consecutivas, y
    eso es correcto: `eventos` las agrupa en UN evento, que es lo que se quiere
    -- una meseta no son cinco picos.

    Las muestras cuya ventana se sale del log salen como hueco (ver
    `extremo_en_ventana`): un pico junto al borde no se puede afirmar, porque el
    valor que falta podría ser mayor.
    """
    xp = _xp(xp)
    if ventana_s <= 0.0:
        raise ErrorDePrimitiva(f"la ventana del pico tiene que ser positiva, se dio {ventana_s!r}")
    if prominencia_minima < 0.0:
        raise ErrorDePrimitiva(
            f"la prominencia mínima no puede ser negativa, se dio {prominencia_minima!r}; "
            "0 significa «cualquier máximo local», que es lo que §4.3 quiere evitar pero "
            "es una decisión de la configuración, no de este módulo"
        )
    mitad = ventana_s / 2.0
    maximos = extremo_en_ventana(
        serie, desde_s=-mitad, hasta_s=mitad, extremo=Extremo.MAXIMO, xp=xp
    )
    minimos = extremo_en_ventana(
        serie, desde_s=-mitad, hasta_s=mitad, extremo=Extremo.MINIMO, xp=xp
    )
    es_maximo = serie.v >= maximos.v
    sobresale = (serie.v - minimos.v) >= prominencia_minima

    # UNA MESETA EN EL MÁXIMO ES UN PICO, NO DOS
    # ------------------------------------------
    # Con la prominencia medida dentro de la ventana, el INTERIOR de una meseta
    # se descarta solo: en `[1, 5, 5, 5, 1]` la ventana de la muestra central son
    # tres cincos, así que su mínimo es 5, la prominencia sale 0 y esa muestra no
    # es pico — mientras que las dos de los bordes sí lo son. El resultado son
    # dos eventos de una muestra donde físicamente hay un pico de tres, y los
    # detectores que cuentan eventos (§4.3) contarían el doble.
    #
    # No es un caso raro: una señal que satura, un limitador que corta y
    # cualquier canal cuantizado en su tope producen mesetas exactas.
    #
    # La corrección: una muestra que está en el máximo local pertenece al pico si
    # ALGUNA muestra de su ventana está en el máximo Y tiene la prominencia
    # exigida. Es una dilatación del núcleo del pico sobre la misma ventana que
    # ya está configurada, así que no añade un parámetro que ajustar ni un bucle
    # por muestra: es otra pasada de `extremo_en_ventana`.
    #
    # Lo que NO cambia, a propósito: una muestra que no está en el máximo local
    # sigue sin ser pico, así que la dilatación no ensancha un pico de verdad
    # hacia sus laderas. Y si ninguna muestra tiene prominencia —el diente de
    # sierra del ruido de cuantización— no hay nada que dilatar y el resultado
    # sigue siendo vacío.
    #
    # Sigue habiendo un límite, y conviene dejarlo dicho: una meseta MÁS ANCHA
    # que la ventana no se une entera, porque sus muestras centrales no ven
    # ningún borde. La salida es la misma que para todo lo demás en esta
    # primitiva —elegir una ventana acorde a la señal— y por eso la ventana es
    # explícita y configurable.
    # `* 1.0` en vez de `xp.where`: el booleano a flotante es la misma operación
    # en NumPy y en el doble, y no obliga a ampliar el Protocol `Vectorial` por
    # una conversión de tipo. El Protocol declara solo lo que hace falta.
    nucleo = Serie(
        t_ms=serie.t_ms,
        v=(es_maximo & sobresale) * 1.0,
        clase=serie.clase,
        valido=serie.valido,
    )
    cerca_del_nucleo = extremo_en_ventana(
        nucleo, desde_s=-mitad, hasta_s=mitad, extremo=Extremo.MAXIMO, xp=xp
    )

    return Condicion(
        t_ms=serie.t_ms,
        activa=es_maximo & (cerca_del_nucleo.v > 0.0),
        valido=_valido_de(maximos) & _valido_de(minimos),
    )


def fuera_de_mascara(
    serie: SerieDeBits,
    *,
    bits_de_interes: int | None,
) -> Condicion:
    """Algún bit de interés activo en una máscara (`Engine Protection Cause`,
    `Trigger System Errors`).

    `bits_de_interes` es la máscara de bits que importan; `None` significa
    «todos», que es lo que `data/umbrales.toml` escribe como
    `bits_de_interes = "todos"` para D12 («cualquier bit activo»). Traducir esa
    cadena a `None` es de quien lee la configuración (F3-07): este módulo no
    interpreta vocabulario de fichero.

    No lleva histéresis ni la necesita: un bit no oscila por ruido de
    cuantización, porque no hay cuantización -- o está puesto o no. La
    permanencia sigue teniendo sentido y la aporta `eventos`, con el valor que
    diga la configuración (para D12 es 0: un solo error de trigger importa).
    """
    if bits_de_interes is not None and bits_de_interes <= 0:
        raise ErrorDePrimitiva(
            f"bits_de_interes = {bits_de_interes!r} no puede ser 0 ni negativo: una "
            "máscara de cero bits no se activaría nunca y el detector estaría apagado "
            "sin decirlo. Para «todos los bits» se pasa None"
        )
    bits = serie.bits
    activa = bits != 0 if bits_de_interes is None else (bits & bits_de_interes) != 0
    return Condicion(t_ms=serie.t_ms, activa=activa, valido=_valido_de(serie))


# --------------------------------------------------------------------------- #
# Reducciones: Condicion -> eventos y números
# --------------------------------------------------------------------------- #
def eventos(
    condicion: Condicion,
    *,
    permanencia: Permanencia,
    pico: Pico | None = None,
    xp: Vectorial | None = None,
) -> list[Evento]:
    """Los intervalos de la condición que duran lo suficiente.

    Es la ÚNICA forma de convertir una condición en eventos, y por eso la
    permanencia mínima se aplica en un solo sitio para las nueve primitivas.
    Una carrera de muestras consecutivas sobrevive si cumple las dos
    condiciones de `Permanencia` (ver su docstring); si no, no existe -- no se
    devuelve marcada, se descarta, porque el sentido de la permanencia es no
    inundar el panel de incidencias.

    `pico` dice de qué canal sale `valor_pico` y qué extremo es. Sin él, los
    eventos salen sin valor de pico, que es lo correcto para una condición
    compuesta cuyo canal principal no está claro: mejor sin número que con el
    número de otro canal.

    ADR-009
    -------
    El filtro por duración y por número de muestras se aplica sobre el array de
    carreras, vectorizado, ANTES de construir ningún objeto de Python. El único
    bucle recorre los eventos que sobreviven —acotados por
    `permanencia.maximo_de_eventos`— y cada iteración hace una reducción
    vectorizada sobre el tramo contiguo de su evento, así que cada muestra se
    toca una sola vez y dentro de una operación de C. Es el patrón de
    `malla.py` para el mínimo/máximo por celda, con la misma justificación.

    Si la condición produce más eventos que el tope, se lanza
    `ErrorDePrimitiva` en vez de devolver una lista inmensa: una configuración
    que genera un evento cada tres muestras no es un log con muchos problemas,
    es una histéresis o una permanencia mal puestas, y el mensaje lo dice.
    """
    xp = _xp(xp)
    n = len(condicion)
    if n == 0:
        return []
    if pico is not None:
        _misma_rejilla(pico.serie.t_ms, condicion.t_ms, xp=xp)

    t = condicion.t_ms
    # Una muestra no válida no cumple la condición: no se sabe cuánto valía, así
    # que interrumpe la carrera (ver la cabecera del módulo).
    activa = condicion.activa & condicion.valido

    idx = xp.arange(n)
    es_primera = idx == 0
    es_ultima = idx == n - 1
    anterior = idx - 1 + es_primera
    siguiente = idx + 1 - es_ultima
    # Una carrera empieza donde el valor cambia respecto a la muestra anterior
    # (y en la muestra 0), y termina donde cambia respecto a la siguiente (y en
    # la última). Comparar la máscara con su propia versión desplazada evita
    # tener que pedirle al protocolo un `flatnonzero` o un `concatenate` para
    # pegar los extremos.
    empieza = (activa != activa[anterior]) | es_primera
    termina = empieza[siguiente] | es_ultima

    inicios = idx[empieza]
    finales = idx[termina]
    activa_en_carrera = activa[inicios]
    duracion_ms = t[finales] - t[inicios]
    muestras = finales - inicios + 1
    sobrevive = (
        activa_en_carrera
        & (duracion_ms >= permanencia.permanencia_ms)
        & (muestras >= permanencia.muestras_minimas)
    )
    inicios_buenos = inicios[sobrevive]
    finales_buenos = finales[sobrevive]

    total = len(inicios_buenos)
    if total > permanencia.maximo_de_eventos:
        raise ErrorDePrimitiva(
            f"la condición produce {total} eventos y el tope es "
            f"{permanencia.maximo_de_eventos}: eso no es un log con muchos problemas, es "
            "una histéresis demasiado estrecha o una permanencia demasiado corta. Sube "
            "`salida` (más histéresis), sube `permanencia_s`, o sube el tope si de "
            "verdad hacen falta tantos"
        )

    salida: list[Evento] = []
    for k in range(total):  # bucle sobre EVENTOS, no sobre muestras (ADR-009)
        i_inicio = int(inicios_buenos[k])
        i_fin = int(finales_buenos[k])
        valor_pico: float | None = None
        if pico is not None:
            tramo = pico.serie.v[i_inicio : i_fin + 1]
            reducir = xp.max if pico.extremo is Extremo.MAXIMO else xp.min
            valor_pico = float(reducir(tramo))
        salida.append(
            Evento(
                t_inicio_ms=float(t[i_inicio]),
                t_fin_ms=float(t[i_fin]),
                i_inicio=i_inicio,
                i_fin=i_fin,
                n_muestras=i_fin - i_inicio + 1,
                valor_pico=valor_pico,
                clase_valor=None if pico is None else pico.serie.clase,
            )
        )
    return salida


def tiempo_acumulado(lista_de_eventos: Sequence[Evento]) -> float:
    """«45 s por encima de 105 °C»: el tiempo total de los eventos, en segundos.

    Recibe los eventos y no la condición, a propósito. Es lo que garantiza que
    «tiempo por encima» signifique exactamente la suma de los eventos que el
    panel de incidencias enseña: si esta función sumara la máscara por su
    cuenta, contaría también las muestras aisladas que la permanencia mínima
    descartó, y el total no cuadraría con la lista que el usuario tiene delante.
    Que no cuadren dos números de la misma pantalla es peor que cualquiera de
    los dos.

    El tiempo de un evento es lo observado entre su primera y su última muestra
    (ver `Evento`), así que un evento de una sola muestra suma 0 s.

    El bucle es sobre eventos, que ya están acotados por
    `Permanencia.maximo_de_eventos`.
    """
    return sum(e.duracion_s for e in lista_de_eventos)


def conteo_de_cruces(condicion: Condicion, *, xp: Vectorial | None = None) -> int:
    """Cuántas veces la condición cambia de estado: la medida de oscilación.

    §4.3 la usa para responder «¿hay ciclo límite?» en el control de ralentí
    (§4.2 P6) y para ver si un PID de boost oscila. Cuenta los cambios de la
    condición TAL CUAL, sin filtrar por permanencia: es una medida distinta de
    `len(eventos(...))`, y las dos hacen falta.

    * `conteo_de_cruces` cuenta ida y vuelta, incluidos los cruces demasiado
      breves para ser un evento. Una señal que oscila en el umbral tiene muchos
      cruces y ningún evento, y eso es precisamente el hallazgo: el lazo está
      inestable aunque no haya nada que alarme.
    * `len(eventos(...))` cuenta problemas que duraron lo suficiente para ser
      un problema.

    La histéresis ya está aplicada, porque la condición viene de una primitiva
    que la lleva dentro: contar cruces sobre un umbral desnudo (declarando
    `salida == entrada`) cuenta también el ruido, y eso es una decisión de la
    configuración, no de esta función.

    Un cambio de estado en el que alguna de las dos muestras es un hueco no se
    cuenta: no se sabe si hubo cruce.
    """
    xp = _xp(xp)
    n = len(condicion)
    if n < 2:
        return 0
    activa = condicion.activa
    valido = condicion.valido
    cambia = (activa[1:] != activa[:-1]) & valido[1:] & valido[:-1]
    return int(xp.sum(cambia))
