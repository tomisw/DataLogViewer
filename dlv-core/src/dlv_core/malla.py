"""Malla RPM x MAP y agregación por celda (tareas F4-01 y F4-02, `docs/04` §4.6).

«La entrega de mayor valor para tuning»: una tabla 2D (bins de RPM x bins de
MAP/carga) con la agregación por celda de un canal tercero (λ, densidad de
knock, avance de encendido...). Este módulo construye la malla y agrega
--`cuenta`, `media`, `desviacion_tipica`, `minimo`, `maximo`, la lista exacta
de F4-02--; el componente de mapa de calor, la tabla de corrección de
combustible, el filtrado por calidad (transitorio, corte, protección de
motor, retardo de transporte del sensor de λ) y la comparación de dos logs
celda a celda son F4-03, F4-04, F4-05, F4-07 y F4-08 -- NO están aquí.

ADR-009 -- CÓMO SE EVITA RECORRER 73 M DE MUESTRAS EN PYTHON
=============================================================
Dos técnicas distintas, una por grupo de estadísticas, y las dos evitan tocar
cada muestra más que una vez desde Python:

1. **`cuenta`, `media`, `desviacion_tipica`** salen de tres `bincount`
   (cuenta, suma, suma de cuadrados) -- el "histogram2d/groupby vectorizado"
   del docstring original de este módulo. Es una sola pasada por el array
   completo, en C, sin ningún bucle de Python de por medio: la media y la
   varianza de un grupo se recuperan de sus sumas (`E[X]` y `E[X²]-E[X]²`)
   sin tener que volver a visitar las muestras una vez agregadas.

2. **`minimo` y `maximo`** no tienen ese atajo: `bincount` solo suma, y NumPy
   no ofrece una reducción de mínimo/máximo agrupada como función de nivel de
   módulo (`numpy.minimum.at` existe, pero es un método de un `ufunc`, no un
   atributo del módulo, y ese es justo el requisito que hace que `numpy` en
   sí mismo satisfaga `Vectorial` sin adaptador -- ver más abajo). La solución:
   un `argsort` (una sola pasada O(N log N) sobre el array completo) coloca
   las muestras válidas contiguas por celda, y luego SÍ hay un `for` -- pero
   sobre las CELDAS (unas decenas a unos pocos cientos, fijo por configuración
   de la malla), nunca sobre las muestras. Cada iteración llama a `xp.min`/
   `xp.max` -- vectorizado -- sobre el tramo contiguo de esa celda. La suma de
   los tamaños de todos los tramos es exactamente el número de muestras
   válidas: cada una se toca una sola vez, dentro de una operación de C, en el
   tramo al que pertenece. El coste no depende de cuántas celdas tenga la
   malla, solo de cuántas muestras haya -- que es la propiedad que pide
   ADR-009, no "cero bucles" a secas.

   Regla para quien toque este módulo: un bucle sobre `range(n_celdas)` está
   bien. Un bucle sobre `range(len(rpm))`, o un `for` que indexe una muestra
   cada vez, no lo está NUNCA, y es lo que `tools/banco.py adr009` vigila por
   patrón además de por revisión.

PROTOCOLO `Vectorial`: SOLO SIETE FUNCIONES, Y POR QUÉ
=======================================================
Mismo patrón que `reloj.py` (léelo si esto no es familiar): un `Protocol`
con los nombres exactos de NumPy, para que el propio módulo `numpy` lo
satisfaga sin ningún adaptador -- `_numpy()` hace `cast("Vectorial", numpy)` y
ya. Eso es lo que permite probar este módulo con una implementación de
biblioteca estándar (`tests/test_malla.py`) sin que el código bajo prueba sea
distinto del que corre con NumPy de verdad.

Las siete, y para qué hace falta cada una (ninguna se usa "por si acaso"):

* `searchsorted(bordes, valores, side)` -- coloca cada muestra en su bin. Es
  lo único que necesita saber DÓNDE cae un valor en un eje ordenado.
* `argsort(a)` -- ordena las muestras válidas por celda, paso previo
  indispensable para el mínimo/máximo agrupado del punto 2 de más arriba.
* `cumsum(a)` -- convierte las cuentas por celda en los límites de cada tramo
  contiguo del array ordenado (mismo uso que en `reloj.py`, con otro
  propósito: aquí no desenrolla tiempo, delimita grupos).
* `bincount(x, weights, minlength)` -- la agregación de verdad: cuenta, suma y
  suma de cuadrados por celda en una sola pasada cada una.
* `sqrt(a)` -- de la varianza (`E[X²]-E[X]²`) a la desviación típica.
* `min(a)`, `max(a)` -- la reducción vectorizada dentro de cada tramo
  contiguo del punto 2. No son `numpy.ndarray.min()`/`.max()` (eso sería un
  método del array, no del módulo) sino `numpy.min`/`numpy.max`, que SÍ son
  funciones de nivel de módulo y hacen exactamente lo mismo.

Ni `digitize`, ni `histogram2d`, ni `unique`, ni `where`, ni ningún método de
`ufunc` (`.at`, `.reduceat`): cuantas menos funciones tenga que reimplementar
quien cambie de motor de cómputo, menos superficie de error.

CELDAS SIN DATOS: NaN, NUNCA 0,0 -- Y `cuenta` ES LA EXCEPCIÓN
================================================================
§4.6 es explícito: «un valor calculado con 2 muestras es peor que ninguno».
Aquí la barra es más baja (0 muestras, no un umbral de N mínimas -- ese umbral,
por omisión 20, es de la tabla de corrección de combustible de F4-05, no de
esta malla), pero el principio es el mismo y más grave todavía: si una celda sin ninguna muestra
saliera con `media = 0.0`, sería indistinguible de una celda con datos reales
cuyo canal (p. ej. λ de error, avance de 0°) vale legítimamente cero. Por eso
`media`, `desviacion_tipica`, `minimo` y `maximo` llevan NaN en las celdas
vacías -- comprobable con `math.isnan`/`numpy.isnan`, nunca con `== 0`.

`cuenta` es la única estadística que NO sigue esta regla, a propósito: un
recuento de muestras es siempre un entero exacto y bien definido, incluso
cuando vale 0 -- "0 muestras" no es una laguna de información, es la respuesta
completa a la pregunta "¿cuántas muestras hay aquí?". Envolverlo también en NaN
obligaría a convertir un entero en `float` sin ninguna ganancia.

QUÉ VIVE EN CANÓNICA, QUÉ ES SOLO PRESENTACIÓN (ADR-004)
=========================================================
`Malla.bordes_rpm` y `Malla.bordes_map` son PUNTOS en canónica (rpm; kPa
absolutos) -- lo mismo que se persistiría en caché o en un perfil. La unidad
activa del usuario entra en juego solo al pintar el eje, con
`bordes_en_unidad_activa`, que delega toda la aritmética en
`unidades.desde_canonica` (no la reimplementa) y declara `Clase.PUNTO` porque
un borde es un valor absoluto del eje, no una anchura de celda -- una anchura
sería `Clase.INTERVALO`, y confundir las dos es la trampa del delta de
`unidades.py`.

QUÉ NO HACE ESTE MÓDULO (deliberado, no un olvido)
====================================================
* No excluye muestras por calidad (transitorio, corte, protección de motor,
  retardo del sensor de λ) -- eso es la regla 2 de §4.6, y es F4-03.
* No aplica el umbral de "menos de N muestras no se rellena" de la tabla de
  corrección de combustible (por omisión 20) -- eso es F4-05: aquí una celda
  con 1 muestra sí lleva su media, solo que con `cuenta == 1` para que quien
  consuma la malla decida si es suficiente para SU propósito.
* No calcula el mapa de knock, el avance de encendido como caso especial, ni
  compara dos logs -- F4-07 y F4-08.
* No exporta a CSV ni al portapapeles -- eso es de la capa de presentación
  (`dlv-ui`/`dlv-api`), que este paquete no toca (ADR-002).

CLASE DE MAGNITUD DE CADA ESTADÍSTICA (F4-02, regla 4 de `CLAUDE.md`)
=======================================================================
`construir_malla` no convierte nada -- todo lo que devuelve está en canónica
(ADR-004) -- pero las cinco estadísticas NO son todas de la misma clase
(`docs/06` §6.5), y quien algún día las convierta (F4-10, todavía sin hacer)
no debería tener que adivinarlo ni volver a leer este docstring:

* `media`, `minimo`, `maximo` son `Clase.PUNTO` -- valores absolutos del
  canal, se les aplican `a` y `b` al convertir.
* `desviacion_tipica` es `Clase.INTERVALO` -- es una dispersión, no una
  lectura. Convertirla como PUNTO le sumaría el desplazamiento de origen: la
  desviación de una temperatura en K no se convierte a °C restándole 273,15.
* `cuenta` no tiene clase -- es un recuento sin unidad, no se convierte
  nunca.

`CLASE_DE_ESTADISTICA` deja esto declarado y consultable por nombre de campo
en vez de dejarlo solo en prosa. Si alguna vez se añade `varianza` como campo
propio de `Malla` (hoy es un paso intermedio que no se expone), le
correspondería `Clase.VARIANZA` (`a²`), no `Clase.INTERVALO`: son cosas
distintas (`docs/06` §6.5) y confundirlas es la misma trampa del delta,
elevada al cuadrado.

Este módulo declara la clase; no la aplica -- eso es exactamente el alcance
que deja pendiente para F4-10 y no antes de tiempo.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from dlv_core.unidades import Clase, Dimension, desde_canonica

__all__ = [
    "CLASE_DE_ESTADISTICA",
    "ErrorDeMalla",
    "Malla",
    "Vectorial",
    "bordes_en_unidad_activa",
    "bordes_por_omision",
    "construir_malla",
]


class ErrorDeMalla(ValueError):
    """Configuración de malla que no se puede construir sin inventar datos.

    Bordes con menos de dos elementos, no crecientes, o un rango degenerado
    (mínimo == máximo, o NaN) al deducirlos del log: en los tres casos, seguir
    adelante exigiría inventar un valor, y eso es justo lo que este módulo no
    hace (regla 6 de `CLAUDE.md`: si el número está mal, se para y se dice qué
    revisar, no se rellena con algo plausible)."""


class Vectorial(Protocol):
    """Lo que este módulo necesita de NumPy, y nada más (ver cabecera).

    Los nombres y las firmas son los de NumPy, así que el propio módulo
    `numpy` satisface el protocolo sin adaptador. Los parámetros son
    posicionales para que cualquier implementación pueda nombrarlos como
    quiera -- mismo criterio que en `reloj.Vectorial`.
    """

    def searchsorted(self, a: Any, v: Any, side: str, /) -> Any: ...
    def argsort(self, a: Any, /) -> Any: ...
    def cumsum(self, a: Any, /) -> Any: ...
    def bincount(self, x: Any, weights: Any, minlength: int, /) -> Any: ...
    def sqrt(self, a: Any, /) -> Any: ...
    def min(self, a: Any, /) -> Any: ...
    def max(self, a: Any, /) -> Any: ...


def _numpy() -> Vectorial:
    """Importa NumPy en el momento de usarlo (mismo motivo que en `reloj.py`:
    el módulo se puede importar y probar sin NumPy instalado)."""
    import numpy

    return cast("Vectorial", numpy)


# --------------------------------------------------------------------------- #
# Bordes
# --------------------------------------------------------------------------- #
def _valida_bordes(bordes: Any, nombre: str) -> None:
    """Al menos dos bordes y estrictamente crecientes.

    El bucle es sobre los BORDES (una decena o unas pocas decenas: la
    resolución de la malla, nunca el número de muestras), así que comprobarlos
    uno a uno en Python no infringe ADR-009.
    """
    n = len(bordes)
    if n < 2:
        raise ErrorDeMalla(f"{nombre} necesita al menos dos bordes (un bin); tiene {n}")
    for i in range(n - 1):
        if not bordes[i + 1] > bordes[i]:
            raise ErrorDeMalla(
                f"{nombre} no es estrictamente creciente en la posición {i}: "
                f"{bordes[i]!r} >= {bordes[i + 1]!r}"
            )


def bordes_por_omision(valores: Any, n_bins: int, *, xp: Vectorial | None = None) -> list[float]:
    """`n_bins + 1` bordes canónicos, equiespaciados entre el mínimo y el
    máximo de `valores`.

    Es el valor por omisión de §4.6: «configurable, y por defecto la deducida
    de los rangos del log». La malla se ajusta exactamente al rango que el
    log recorrió, ni más ni menos -- no un rango "típico" de motor cableado en
    este módulo, que sería justo la clase de opinión disfrazada de física que
    prohíbe la regla 3 de `CLAUDE.md` (ahí habla de umbrales, pero el
    principio -- no cablear un número que depende del motor o de la sesión --
    es el mismo).

    El último borde se fija exactamente en el máximo medido en vez de dejar
    que salga de la acumulación `mínimo + paso·i`: con `n_bins` grande, el
    redondeo de coma flotante puede dejarlo una fracción de unidad por debajo
    del máximo real, y entonces la propia muestra que definió el rango
    quedaría fuera de él por su culpa (ver `_indices_de_bin`, que exige
    `valores <= bordes[-1]`).

    El bucle que construye la lista es sobre `n_bins` (la resolución de la
    malla), nunca sobre las muestras de `valores`: es aritmética escalar
    repetida a partir de dos números -- el mínimo y el máximo --, no una
    operación sobre el array completo.

    LOS HUECOS DEL CANAL SE IGNORAN, NO INVALIDAN EL RANGO
    ------------------------------------------------------
    Las muestras NaN se descartan antes de medir el rango, con el mismo
    `valores == valores` que usa `construir_malla` (falso solo para NaN, IEEE
    754) y por la misma razón: no meter `isnan` en el protocolo por una
    comprobación. Un canal con huecos es lo NORMAL aquí, no una anomalía --
    el muestreo es disperso y multifrecuencia (`docs/01` §1.4), así que un
    canal a 5 Hz tiene hueco en la mayoría de las marcas de tiempo. Sin este
    filtro, el camino por omisión de §4.6 («los bordes deducidos de los rangos
    del log») se caía con cualquier canal que no fuera el más rápido, y
    encima de forma distinta según el motor de cómputo: `numpy.min` de un
    array con NaN es NaN -> `ErrorDeMalla` culpando al canal, mientras que el
    `min` de la biblioteca estándar de las pruebas devuelve un resultado que
    depende de en qué posición esté el NaN. Un módulo cuyo resultado depende de
    con qué implementación de `Vectorial` corre no es comprobable.

    Sigue siendo un error que NO quede ninguna muestra válida, o que todas
    valgan lo mismo: ahí no hay rango que deducir, y devolver uno inventado es
    peor que parar.
    """
    if n_bins < 1:
        raise ErrorDeMalla(f"n_bins tiene que ser >= 1, se dio {n_bins}")
    xp = xp if xp is not None else _numpy()
    con_dato = valores[valores == valores]
    if len(con_dato) == 0:
        raise ErrorDeMalla(
            "no se pueden deducir bordes de un canal sin ninguna muestra válida (vacío o todo NaN)"
        )
    minimo = float(xp.min(con_dato))
    maximo = float(xp.max(con_dato))
    if not maximo > minimo:
        raise ErrorDeMalla(
            f"no se pueden deducir bordes de un rango degenerado "
            f"(mínimo={minimo!r}, máximo={maximo!r}): ¿canal constante?"
        )
    paso = (maximo - minimo) / n_bins
    bordes = [minimo + paso * i for i in range(n_bins + 1)]
    bordes[-1] = maximo
    return bordes


def bordes_en_unidad_activa(
    bordes_canonicos: Any,
    *,
    dimension: Dimension,
    unidad: str,
    referencia_kpa: float | None = None,
) -> list[float]:
    """Bordes canónicos (rpm o kPa absolutos) -> unidad activa, para pintar
    el eje.

    Los bordes son PUNTOS (`Clase.PUNTO`, `unidades.py`): son valores
    concretos del eje -- un régimen, una presión --, no anchuras de celda. La
    anchura de un bin sí sería `Clase.INTERVALO`, pero eso no es lo que este
    módulo entrega. Toda la aritmética de conversión vive en
    `unidades.desde_canonica`; esta función no la reimplementa, solo declara
    la clase correcta y la aplica borde a borde.

    El bucle es sobre los bordes (unas decenas), nunca sobre las muestras:
    misma distinción que en `bordes_por_omision`. Es deliberadamente escalar
    -- no vectorizado sobre `bordes_canonicos` de una vez -- porque los bordes
    pueden llegar como una lista corriente de Python (los que devuelve
    `bordes_por_omision`) que no soporta la aritmética de array que
    `unidades.py` necesita; escalar a escalar funciona igual con esa lista,
    con un array de NumPy o con cualquier otra cosa iterable, sin que este
    módulo tenga que saber cuál es.
    """
    return [
        float(
            desde_canonica(
                b,
                dimension=dimension,
                unidad=unidad,
                clase=Clase.PUNTO,
                referencia_kpa=referencia_kpa,
            )
        )
        for b in bordes_canonicos
    ]


def _indices_de_bin(valores: Any, bordes: Any, *, xp: Vectorial) -> tuple[Any, Any]:
    """Índice de bin en `[0, n_bins - 1]` para cada valor, y máscara de
    validez (`True` si cae dentro de `[bordes[0], bordes[-1]]`).

    Los bins son semiabiertos por la izquierda -- `[bordes[i], bordes[i+1])`
    -- salvo el último, cerrado por los dos lados para no perder las muestras
    que caen justo en el borde superior del rango (mismo convenio que
    `numpy.histogram`).

    Buscar solo en los bordes INTERIORES (`bordes[1:-1]`) es lo que hace que
    el índice salga ya en rango sin que haga falta recortarlo: un valor por
    debajo del primer borde interior cae en el bin 0, uno por encima o igual
    al último cae en el bin `n_bins - 1` -- incluido exactamente `bordes[-1]`,
    porque no está entre los bordes buscados y por tanto nunca se desborda a
    `n_bins`. Es lo que evita tener que meter `minimum`/`clip` en el
    protocolo `Vectorial` solo para este detalle de borde.

    Las comparaciones (`>=`, `<=`, `&`) se hacen directamente sobre los
    arrays, sin pasar por `xp`: son operadores, no funciones con nombre, y
    NumPy y cualquier implementación mínima los da gratis (mismo estilo que
    `reloj.py`, que hace lo mismo con `diff(...) < -UMBRAL`). Como beneficio
    colateral, un NaN en `valores` (canal con huecos) sale como no válido sin
    ningún caso especial: `nan >= x` y `nan <= x` son `False` los dos.
    """
    interiores = bordes[1:-1]
    idx = xp.searchsorted(interiores, valores, "right")
    valido = (valores >= bordes[0]) & (valores <= bordes[-1])
    return idx, valido


# --------------------------------------------------------------------------- #
# Clase de magnitud de cada estadística (F4-02, regla 4 de `CLAUDE.md`)
# --------------------------------------------------------------------------- #
# Nombre de campo de `Malla` -> `Clase` de conversión (`docs/06` §6.5), o
# `None` para el campo que no tiene ninguna porque no lleva unidad. `None`
# se guarda EXPLÍCITAMENTE en vez de omitir la clave: así un consumidor que
# recorra `CLASE_DE_ESTADISTICA` no tiene que distinguir "no está en el mapa"
# de "está, y no tiene clase" -- las cinco estadísticas de F4-02 están todas
# aquí, sin excepción, y ese es justo el punto: nadie tiene que adivinar la
# de ninguna. Ver la cabecera del módulo para el porqué de cada asignación.
CLASE_DE_ESTADISTICA: Mapping[str, Clase | None] = {
    "cuenta": None,
    "media": Clase.PUNTO,
    "desviacion_tipica": Clase.INTERVALO,
    "minimo": Clase.PUNTO,
    "maximo": Clase.PUNTO,
}


# --------------------------------------------------------------------------- #
# Malla
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class Malla:
    """Una malla RPM x MAP con la agregación de un canal tercero por celda.

    Todo en unidad CANÓNICA (ADR-004): `bordes_rpm` en rpm, `bordes_map` en
    kPa absolutos. La conversión a la unidad activa es solo de presentación y
    la hace `bordes_en_unidad_activa`; este módulo nunca convierte al
    construir. `CLASE_DE_ESTADISTICA` declara, por nombre de campo, la clase
    de conversión de cada estadística (`Clase.PUNTO`/`INTERVALO`, o sin clase
    para `cuenta`) para quien sí convierta -- ver la cabecera del módulo.

    Las cinco estadísticas son arrays PLANOS de longitud `n_rpm * n_map`
    (`n_rpm = len(bordes_rpm) - 1`, `n_map = len(bordes_map) - 1`), en orden
    "de fila" -- la celda `(i, j)` (bin `i` de RPM, bin `j` de MAP) está en la
    posición `i * n_map + j`. No se devuelven ya como matriz `(n_rpm, n_map)`
    a propósito: remodelar (`reshape`) es una operación sobre un array del
    tamaño de la malla (unas decenas o cientos de elementos), no de las
    muestras, así que no tiene ningún coste que justificar aquí -- pero SÍ es
    una función más que este módulo tendría que pedirle al protocolo
    `Vectorial` solo para un cambio de forma que quien consuma la malla (con
    NumPy de verdad, no con la implementación mínima de las pruebas) hace en
    una línea con `.reshape(malla.forma)`. Mantener el protocolo en las siete
    funciones que necesita la agregación de verdad pesa más que ahorrarle esa
    línea a quien la use.

    Celdas sin ninguna muestra válida: `media`, `desviacion_tipica`, `minimo`
    y `maximo` llevan NaN (ver la cabecera del módulo, «CELDAS SIN DATOS»).
    `cuenta` es siempre un entero válido, 0 incluido.
    """

    bordes_rpm: Any
    bordes_map: Any
    cuenta: Any
    media: Any
    desviacion_tipica: Any
    minimo: Any
    maximo: Any

    @property
    def forma(self) -> tuple[int, int]:
        """`(n_rpm, n_map)`: cómo remodelar los arrays planos si hiciera falta."""
        return (len(self.bordes_rpm) - 1, len(self.bordes_map) - 1)


def construir_malla(
    rpm: Any,
    presion_map: Any,
    valor: Any,
    *,
    bordes_rpm: Any,
    bordes_map: Any,
    xp: Vectorial | None = None,
) -> Malla:
    """Agrega `valor` (rol tercero: λ, densidad de knock, avance...) en la
    malla RPM x MAP definida por `bordes_rpm`/`bordes_map`.

    `rpm`, `presion_map` y `valor` son tres arrays canónicos de la misma
    longitud (una muestra cada uno). Los bordes también están en canónica
    (ADR-004): rpm y kPa absolutos, ya sea puestos a mano o deducidos con
    `bordes_por_omision`.

    Ver la cabecera del módulo para el porqué de las dos técnicas de
    agregación (`bincount` para cuenta/media/desviación, `argsort` + bucle
    sobre celdas para mínimo/máximo) y para qué representa una celda sin
    datos.
    """
    if not (len(rpm) == len(presion_map) == len(valor)):
        raise ErrorDeMalla(
            f"rpm ({len(rpm)}), presion_map ({len(presion_map)}) y valor "
            f"({len(valor)}) tienen que tener la misma longitud"
        )
    _valida_bordes(bordes_rpm, "bordes_rpm")
    _valida_bordes(bordes_map, "bordes_map")
    xp = xp if xp is not None else _numpy()

    n_map = len(bordes_map) - 1
    n_celdas = (len(bordes_rpm) - 1) * n_map

    idx_rpm, valido_rpm = _indices_de_bin(rpm, bordes_rpm, xp=xp)
    idx_map, valido_map = _indices_de_bin(presion_map, bordes_map, xp=xp)
    # Válida si cae dentro de las dos mallas Y su valor no es NaN. `valor ==
    # valor` es falso solo para NaN (IEEE 754): es el mismo truco que evita
    # tener que meter `isnan` en el protocolo `Vectorial` por una sola
    # comprobación. Una muestra con `valor` NaN (p. ej. lectura de λ inválida)
    # no debe contar como "cero muestras válidas aquí", así se excluye antes
    # de agregar en vez de colar un NaN que contaminaría toda la celda.
    valido = valido_rpm & valido_map & (valor == valor)

    idx_plano = idx_rpm * n_map + idx_map
    idx_validos = idx_plano[valido]
    valor_validos = valor[valido]

    cuenta = xp.bincount(idx_validos, None, n_celdas)
    suma = xp.bincount(idx_validos, valor_validos, n_celdas)
    suma2 = xp.bincount(idx_validos, valor_validos * valor_validos, n_celdas)

    sin_datos = cuenta == 0
    # Divisor "seguro": una celda vacía divide por 1 en vez de por 0. No es
    # una aproximación que cambie el resultado -- ese resultado se descarta
    # dos líneas más abajo, machacado por NaN -- es solo evitar depender de
    # que `0/0` y `x/0` den NaN/inf de forma consistente entre implementaciones
    # (y evitar el aviso de "división por cero" que NumPy emitiría de otro
    # modo).
    divisor = cuenta + sin_datos
    media = suma / divisor
    # `E[X²] - E[X]²` en UNA pasada. Es la forma numéricamente inestable de
    # calcular una varianza —cancelación catastrófica cuando la media es grande
    # frente a la dispersión— así que la pregunta no es si lo es en teoría, sino
    # si lo es para los canales que esta malla agrega. MEDIDO (F4-02, revisión
    # G2), error relativo contra `np.std` sobre 20 000 muestras en float64:
    #
    #     RPM              (media 5e3,   sigma 30)   4e-12
    #     Presión colector (media 219,   sigma 8)    7e-14
    #     Distance Traveled(media 1,2e5, sigma 2)    1e-07
    #     Knock Count      (media 4,5e4, sigma 3)    8e-09
    #     Epoch en ms      (media 1,7e12,sigma 5)    4e+03   <-- ROTO
    #
    # Aguanta con holgura para todo lo que tiene sentido agregar sobre una
    # malla RPM×MAP, incluidos los canales ACUMULATIVOS, que son los de peor
    # relación media/dispersión del log real. Se rompe a partir de magnitudes
    # de ~1e12, es decir una marca de tiempo epoch — que no es un canal que se
    # agregue por celda de RPM y presión.
    #
    # Se deja así a propósito, en vez de cambiarlo por la versión desplazada
    # (restar una constante antes de elevar al cuadrado, que la arregla del
    # todo): este código venía de F4-01 con su puerta cerrada, y reescribir
    # código aprobado por un riesgo que se ha medido y no se materializa es
    # churn. Lo que faltaba era el número, no el cambio. Si algún día se
    # agrega un canal de magnitud ~1e12, la vía es desplazar por la media
    # global; la varianza es invariante a esa traslación.
    varianza = suma2 / divisor - media * media
    # El redondeo de coma flotante puede dejar la varianza ligeramente
    # negativa cuando todas las muestras de la celda son casi idénticas (la
    # varianza real es 0). Se recorta a 0 antes de la raíz: es una
    # aproximación distinta y mucho más pequeña que la NaN de "no hay datos".
    varianza_no_negativa = varianza * (varianza > 0)
    desviacion = xp.sqrt(varianza_no_negativa)

    # Mínimo y máximo por celda (ver la cabecera del módulo): las muestras
    # válidas se ordenan por celda con un solo `argsort` sobre el array
    # completo, y el bucle que sigue recorre las CELDAS (n_celdas, fijo por la
    # resolución de la malla) para tomar el `min`/`max` vectorizado de cada
    # tramo contiguo -- nunca las muestras. `limites[k]` es la posición, en el
    # array ordenado, donde termina el tramo de la celda `k` (y donde empieza
    # el de la `k + 1`), porque `cumsum` de las cuentas por celda es
    # exactamente eso.
    orden = xp.argsort(idx_validos)
    valor_ordenado = valor_validos[orden]
    limites = xp.cumsum(cuenta)

    minimo = cuenta * 0.0 + float("nan")
    maximo = cuenta * 0.0 + float("nan")
    inicio = 0
    for celda in range(n_celdas):  # bucle sobre CELDAS, no sobre muestras (ADR-009)
        fin = int(limites[celda])
        if fin > inicio:
            tramo = valor_ordenado[inicio:fin]
            minimo[celda] = xp.min(tramo)
            maximo[celda] = xp.max(tramo)
        inicio = fin

    media[sin_datos] = float("nan")
    desviacion[sin_datos] = float("nan")

    return Malla(
        bordes_rpm=bordes_rpm,
        bordes_map=bordes_map,
        cuenta=cuenta,
        media=media,
        desviacion_tipica=desviacion,
        minimo=minimo,
        maximo=maximo,
    )
