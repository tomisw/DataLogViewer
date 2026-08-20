"""Sistema de unidades: valor canónico, conversión solo en presentación.

ADR-004 (`docs/03-arquitectura.md` §3.2) y `docs/06-sistema-de-unidades.md`:
lo que se persiste —caché, umbrales, perfiles, mallas, anotaciones— está siempre
en la unidad canónica de cada dimensión. La conversión a la unidad elegida por el
usuario (°C/°F, kPa/bar/psi, λ/AFR, km/h/mph…) se aplica solo a los cubos
visibles en el momento de dibujar, nunca al dato persistido. Por eso cambiar de
unidad es un repintado y no una recarga, y por eso no invalida la caché ni
reescribe un umbral.

ADR-009 — CERO BUCLES POR MUESTRA
=================================
Las conversiones se expresan como aritmética sobre el valor entero: `a * x + b`,
`a / x`. Esas expresiones funcionan igual sobre un `float` que sobre un
`numpy.ndarray` completo, así que **el mismo código es escalar y vectorizado**
según lo que se le pase. Este módulo no importa numpy a propósito: no lo
necesita, y así se puede probar sin dependencias instaladas.

Nunca se debe escribir aquí un bucle sobre los elementos de una serie. Si hiciera
falta una operación que no se pueda expresar así, va a Numba, no a un `for`.

LA TRAMPA DEL DELTA
===================
El fallo más caro de un sistema de unidades es aplicar el desplazamiento de
origen a una diferencia: un Δ de 10 K son 10 °C y 18 °F, nunca −263,15 °C. De
ahí que toda conversión exija una `Clase`, y que no haya valor por omisión: quien
convierte tiene que declarar si lo que tiene entre manos es un punto o un
intervalo (`docs/06-sistema-de-unidades.md` §6.5).

POR QUÉ EL RMS ES `INTERVALO` Y NO `PUNTO` (F4-10)
====================================================
`docs/06` §6.5 ya lo declara en su tabla («RMS» en la fila de `INTERVALO`,
junto a la desviación típica), pero merece la razón por escrito porque un RMS
no es evidentemente una diferencia -- `sqrt(mean(x²))` de una temperatura en
Kelvin PARECE una lectura absoluta, no un Δ. No lo es, y la prueba es
algebraica, no de estilo.

Sea `X` la serie canónica y `mostrado = a·X + b` la conversión afín de su
unidad de destino (el único caso con `b ≠ 0` en el catálogo es la
temperatura). El cuadrado medio de la serie CONVERTIDA es:

    E[(aX + b)²] = a²·E[X²] + 2ab·E[X] + b²
                 = a²·(σ² + μ²) + 2ab·μ + b²          (con μ = E[X], σ² = Var(X))
                 = a²·RMS(X)² + 2ab·μ + b²

Es decir, `RMS(a·X + b) = sqrt(a²·RMS(X)² + 2ab·μ + b²)`, que depende de `μ`
-- la MEDIA de `X` -- y no es una función de `RMS(X)` por sí solo salvo que
`b = 0`. Con `b = 0` el término cruzado desaparece y queda exactamente
`RMS(a·X) = a·RMS(X)`: la misma regla de solo-la-parte-lineal que ya aplica
`INTERVALO` a la desviación típica y al rango.

Dos consecuencias, no una sola:

1. **`RMS` nunca puede ser `Clase.PUNTO`.** Sumarle `b` (como si fuera una
   lectura absoluta) no solo está mal por la misma razón de siempre --
   desplazar un ancho de banda no tiene sentido físico --, sino que además
   NO reconstruye el RMS que se obtendría convirtiendo cada muestra cruda a
   la unidad de destino y volviendo a calcular el RMS ahí: esa reconstrucción
   exacta necesitaría conocer también `μ`, que un RMS no lleva consigo. La
   única conversión que este motor puede ofrecer con la información que
   tiene -- el propio valor de RMS, sin la media que lo acompañaba -- es la
   lineal, `a·RMS(X)`, que es justo lo que hace `Clase.INTERVALO`.
2. **Por eso un RMS solo tiene sentido, en este sistema, sobre una magnitud
   que YA es una diferencia** (una desviación respecto a un objetivo, no una
   lectura cruda del canal) -- exactamente el caso de §4.2 P6, «desviación
   RMS respecto al objetivo» en el lazo de ralentí: se calcula sobre
   `medida − objetivo`, que ya no tiene el desplazamiento de origen del
   canal, así que la homogeneidad `RMS(k·d) = |k|·RMS(d)` (válida para
   cualquier `k`, sin excepción, porque el valor absoluto sale de la raíz)
   es exacta y `Clase.INTERVALO` es la conversión correcta y no una
   aproximación. Un RMS calculado sobre la lectura absoluta del canal --sin
   restarle nada-- no es una magnitud que este sistema sepa convertir de
   forma exacta, y no se debe fingir que sí con `Clase.PUNTO`.

Ver `dlv-core/tests/test_trampa_del_delta.py`,
`test_el_rms_es_homogeneo_bajo_escala_pero_no_bajo_desplazamiento`, para la
comprobación numérica de las dos propiedades.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import IO, Any, Protocol, TypeVar


class Numerico(Protocol):
    """Lo que este módulo necesita de un valor: aritmética elemental.

    Lo cumplen `float`, `int` y `numpy.ndarray`. Es lo que permite que el mismo
    código sirva para el valor bajo el cursor y para un array de cinco millones
    de muestras, sin ramificar.
    """

    def __add__(self, otro: Any, /) -> Any: ...
    def __mul__(self, otro: Any, /) -> Any: ...
    def __rmul__(self, otro: Any, /) -> Any: ...
    def __truediv__(self, otro: Any, /) -> Any: ...
    def __rtruediv__(self, otro: Any, /) -> Any: ...
    def __sub__(self, otro: Any, /) -> Any: ...


V = TypeVar("V", bound=Numerico)


class Clase(Enum):
    """Qué representa el valor que se convierte (`docs/06` §6.5).

    Determina si se aplica el desplazamiento de origen, y es obligatoria.
    """

    PUNTO = "punto"
    """Valor absoluto: se aplican `a` y `b`. Cursor, media, mínimo, umbral."""

    INTERVALO = "intervalo"
    """Diferencia: solo `a`. Δ del doble cursor, rango, desviación típica, RMS.

    El RMS entra en esta clase y NUNCA en `PUNTO`: ver «POR QUÉ EL RMS ES
    INTERVALO Y NO PUNTO (F4-10)» en la cabecera del módulo para la
    justificación algebraica -- no es una convención arbitraria, es lo único
    que se puede calcular sin conocer la media de la serie original."""

    TASA = "tasa"
    """Cociente por unidad de otra magnitud: solo la parte lineal. Derivadas."""

    VARIANZA = "varianza"
    """Cuadrática: se aplica `a²`."""


class ErrorDeUnidad(ValueError):
    """Uso incorrecto del sistema de unidades. No es un fallo de datos."""


# --------------------------------------------------------------------------- #
# Conversiones
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class Afin:
    """Conversión afín `mostrado = a * canonica + b`.

    Cubre la mayoría de las unidades. El caso con `b != 0` es la temperatura, y
    es el que obliga a distinguir punto de intervalo.
    """

    a: float
    b: float = 0.0

    def __post_init__(self) -> None:
        if self.a == 0.0:
            raise ErrorDeUnidad("una conversión afín con a=0 no es invertible")

    @property
    def desplaza_origen(self) -> bool:
        return self.b != 0.0

    def desde_canonica(self, x: Any, clase: Clase, param: float | None = None) -> Any:
        if clase is Clase.PUNTO:
            # El `+ b` se omite cuando b == 0, que es la mayoría de las unidades.
            # Sumar cero no cambia el resultado, pero sobre un array de cinco
            # millones de muestras es una pasada completa por memoria en cada
            # fotograma. La comparación de un float es despreciable al lado.
            return self.a * x + self.b if self.b else self.a * x
        if clase is Clase.VARIANZA:
            return (self.a * self.a) * x
        # INTERVALO y TASA: solo la parte lineal. Es la regla que evita que un
        # Δ de 10 K se convierta en −263,15 °C.
        return self.a * x

    def a_canonica(self, y: Any, clase: Clase, param: float | None = None) -> Any:
        if clase is Clase.PUNTO:
            return (y - self.b) / self.a if self.b else y / self.a
        if clase is Clase.VARIANZA:
            return y / (self.a * self.a)
        return y / self.a


@dataclass(slots=True, frozen=True)
class Reciproca:
    """Conversión recíproca `mostrado = a / canonica`.

    λ ↔ φ, periodo ↔ frecuencia, L/100 km ↔ mpg. **No es lineal**, así que una
    diferencia no se puede convertir: pedirlo es un error de uso, no un valor que
    devolver aproximado y dejar que el usuario lo interprete mal.
    """

    a: float
    desplaza_origen: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.a == 0.0:
            raise ErrorDeUnidad("una conversión recíproca con a=0 no es invertible")

    def desde_canonica(self, x: Any, clase: Clase, param: float | None = None) -> Any:
        self._exige_punto(clase)
        return self.a / x

    def a_canonica(self, y: Any, clase: Clase, param: float | None = None) -> Any:
        self._exige_punto(clase)
        return self.a / y

    @staticmethod
    def _exige_punto(clase: Clase) -> None:
        if clase is not Clase.PUNTO:
            raise ErrorDeUnidad(
                "una conversión recíproca no es lineal: no se puede convertir un "
                f"valor de clase {clase.value}. Convierte los extremos como PUNTO "
                "y resta después, sabiendo que la diferencia no es lineal."
            )


@dataclass(slots=True, frozen=True)
class Parametrizada:
    """Conversión `mostrado = a(p) * canonica`, con `p` tomado de un canal.

    El caso es λ → AFR: el factor es la estequiometría del combustible en uso,
    que viene en un canal del propio log. Sin esto, un log de E85 o de metanol
    daría un AFR incorrecto con aspecto de correcto.
    """

    parametro_rol: str
    a_por_omision: float
    desplaza_origen: bool = field(default=False, init=False)

    def _factor(self, param: float | None) -> float:
        return self.a_por_omision if param is None else param

    def desde_canonica(self, x: Any, clase: Clase, param: float | None = None) -> Any:
        a = self._factor(param)
        if clase is Clase.VARIANZA:
            return (a * a) * x
        return a * x

    def a_canonica(self, y: Any, clase: Clase, param: float | None = None) -> Any:
        a = self._factor(param)
        if clase is Clase.VARIANZA:
            return y / (a * a)
        return y / a


Conversion = Afin | Reciproca | Parametrizada


# --------------------------------------------------------------------------- #
# Catálogo
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class Unidad:
    id: str
    etiqueta: str
    conversion: Conversion
    decimales: int
    alias: tuple[str, ...] = ()

    def formatea(self, valor: float, *, separador_decimal: str = ",") -> str:
        """Valor ya convertido -> cadena, con los decimales de la unidad.

        Los decimales son parte de la definición de la unidad porque no son un
        detalle estético: mostrar λ 0,995 con un decimal (1,0) destruye la
        información que el tuner necesita.
        """
        texto = f"{valor:.{self.decimales}f}"
        if separador_decimal != ".":
            texto = texto.replace(".", separador_decimal)
        return f"{texto} {self.etiqueta}" if self.etiqueta else texto


@dataclass(slots=True, frozen=True)
class Dimension:
    id: str
    etiqueta: str
    unidad_canonica: str
    unidades: Mapping[str, Unidad]
    convertible: bool = True
    admite_referencia: bool = False
    mostrar_en_crudo: bool = False
    render: str | None = None
    alias: Mapping[str, str] = field(default_factory=dict)

    @property
    def unidades_disponibles(self) -> tuple[str, ...]:
        return tuple(self.unidades)

    def unidad(self, id_o_alias: str) -> Unidad:
        clave = self.alias.get(id_o_alias, id_o_alias)
        try:
            return self.unidades[clave]
        except KeyError:
            raise ErrorDeUnidad(
                f"'{id_o_alias}' no es una unidad de la dimensión '{self.id}'. "
                f"Disponibles: {', '.join(self.unidades)}"
            ) from None


@dataclass(slots=True, frozen=True)
class Catalogo:
    """El catálogo completo, tal como lo define `data/units.toml`."""

    dimensiones: Mapping[str, Dimension]
    presets: Mapping[str, Mapping[str, Any]]
    centinelas_i32: frozenset[int]
    centinelas_texto: frozenset[str]
    referencia_presion_por_omision_kpa: float

    def dimension(self, id_: str) -> Dimension:
        try:
            return self.dimensiones[id_]
        except KeyError:
            raise ErrorDeUnidad(f"dimensión desconocida: '{id_}'") from None

    @property
    def preset_por_omision(self) -> str:
        for nombre, p in self.presets.items():
            if p.get("por_omision"):
                return nombre
        raise ErrorDeUnidad("el catálogo no declara ningún preset por omisión")


def _conversion_desde_toml(bruto: Mapping[str, Any], donde: str) -> Conversion:
    tipo = bruto.get("tipo")
    if tipo == "afin":
        return Afin(a=float(bruto["a"]), b=float(bruto["b"]))
    if tipo == "reciproca":
        return Reciproca(a=float(bruto["a"]))
    if tipo == "parametrizada":
        return Parametrizada(
            parametro_rol=str(bruto["parametro_rol"]),
            a_por_omision=float(bruto["a_por_omision"]),
        )
    raise ErrorDeUnidad(f"{donde}: tipo de conversión desconocido: {tipo!r}")


def _resolver_canonica(
    declarada: str, id_dim: str, unidades: Mapping[str, Unidad], alias: Mapping[str, str]
) -> str:
    """La `canonica` de una dimensión, traducida a la clave REAL de sus unidades.

    `data/units.toml` escribe la canónica en su forma legible y la clave de la
    unidad con `_` en lugar de `/`, porque una clave TOML con barra hay que
    entrecomillarla: `canonica = "m/s2"` con `[...unidades.m_s2]`, y lo mismo en
    `density` (`kg/m3` -> `kg_m3`). Es la convención que ya fija la puerta del
    propio catálogo (`tests/test_units_catalogo.py`), y traducirla aquí —una vez,
    al cargar— es lo que garantiza que `dimension.unidad(dim.unidad_canonica)`
    funcione siempre.

    Sin esta traducción, `unidad_canonica` guardaba un id que no existía entre
    las unidades de su propia dimensión. Las consecuencias, por orden: el último
    recurso de la cadena de resolución (`resolucion_unidad.py`, canal > perfil >
    usuario > fichero > CANÓNICA) lanzaba `ErrorDeUnidad` en vez de devolver la
    unidad para todo canal de aceleración o densidad sin unidad declarada; y el
    desempate por canónica de `formatos/unidades_declaradas.py` no podía ganar
    nunca en esas dos dimensiones. Ninguna de las dos fallaba en el catálogo
    entero, solo en las dos dimensiones cuya canónica lleva barra, que es
    justo por lo que no se vio antes.

    Si tras la traducción sigue sin existir, es un fallo del catálogo y se dice
    al cargarlo, no meses después al graficar un canal.
    """
    if declarada in unidades:
        return declarada
    if declarada in alias:
        return alias[declarada]
    normalizada = declarada.replace("/", "_").replace("·", "")
    if normalizada in unidades:
        return normalizada
    raise ErrorDeUnidad(
        f"{id_dim}: la canónica declarada {declarada!r} no está entre sus unidades "
        f"{sorted(unidades)} ni entre sus alias, ni con la barra normalizada "
        f"({normalizada!r}). Una dimensión sin canónica real deja sin último recurso "
        "a la cadena de resolución de unidad"
    )


def cargar_catalogo(fuente: IO[bytes]) -> Catalogo:
    """Carga el catálogo desde `units.toml` ya abierto en binario.

    `dlv-core` no abre ficheros por su cuenta (ADR-002): recibe el objeto de
    lectura. Es lo que permite usarlo desde un cuaderno, con el catálogo
    empotrado en el paquete, o desde un origen que no sea el disco.
    """
    bruto = tomllib.load(fuente)

    dimensiones: dict[str, Dimension] = {}
    for id_dim, d in bruto["dimensiones"].items():
        unidades: dict[str, Unidad] = {}
        alias: dict[str, str] = {}
        for id_uni, u in d["unidades"].items():
            conv = _conversion_desde_toml(u["desde_canonica"], f"{id_dim}.{id_uni}")
            # Coherencia del catálogo, comprobada al cargar y no más tarde: la
            # marca `origen_desplazado` debe estar exactamente donde b != 0. Si
            # no, el motor podría aplicar el desplazamiento a un delta creyendo
            # que no hay ninguno.
            declarado = bool(u.get("origen_desplazado", False))
            if isinstance(conv, Afin) and conv.desplaza_origen != declarado:
                raise ErrorDeUnidad(
                    f"{id_dim}.{id_uni}: b={conv.b} pero origen_desplazado={declarado}"
                )
            alias_uni = tuple(str(a) for a in u.get("alias", ()))
            unidades[id_uni] = Unidad(
                id=id_uni,
                etiqueta=str(u["etiqueta"]),
                conversion=conv,
                decimales=int(u["decimales"]),
                alias=alias_uni,
            )
            for a in alias_uni:
                alias[a] = id_uni

        dimensiones[id_dim] = Dimension(
            id=id_dim,
            etiqueta=str(d.get("etiqueta", id_dim)),
            unidad_canonica=_resolver_canonica(str(d["canonica"]), id_dim, unidades, alias),
            unidades=unidades,
            convertible=bool(d.get("convertible", True)),
            admite_referencia=bool(d.get("admite_referencia", False)),
            mostrar_en_crudo=bool(d.get("mostrar_en_crudo", False)),
            render=d.get("render"),
            alias=alias,
        )

    centinelas = bruto.get("centinelas", {})
    presion = bruto.get("presion_referencia", {})
    return Catalogo(
        dimensiones=dimensiones,
        presets=bruto.get("presets", {}),
        centinelas_i32=frozenset(int(x) for x in centinelas.get("i32", ())),
        centinelas_texto=frozenset(str(x) for x in centinelas.get("texto", ())),
        referencia_presion_por_omision_kpa=float(presion.get("constante_por_omision_kPa", 101.325)),
    )


# --------------------------------------------------------------------------- #
# Conversión
# --------------------------------------------------------------------------- #
def desde_canonica(
    valores: Any,
    *,
    dimension: Dimension,
    unidad: str,
    clase: Clase,
    param: float | None = None,
    referencia_kpa: float | None = None,
) -> Any:
    """Canónica -> unidad mostrada. Vectorizado si `valores` es un array.

    `clase` es obligatoria: ver la nota sobre la trampa del delta en la cabecera
    del módulo.

    `referencia_kpa` pasa la presión a relativa. No es una unidad, es un cambio
    de origen (`docs/06` §6.6), y por eso se resta **solo** a los puntos: un Δ de
    50 kPa vale lo mismo en absoluto que en relativo.
    """
    uni = dimension.unidad(unidad)
    if referencia_kpa is not None:
        if not dimension.admite_referencia:
            raise ErrorDeUnidad(
                f"la dimensión '{dimension.id}' no admite referencia de origen; "
                "solo la presión la admite"
            )
        if clase is Clase.PUNTO:
            valores = valores - referencia_kpa
    return uni.conversion.desde_canonica(valores, clase, param)


def a_canonica(
    valores: Any,
    *,
    dimension: Dimension,
    unidad: str,
    clase: Clase,
    param: float | None = None,
    referencia_kpa: float | None = None,
) -> Any:
    """Unidad mostrada -> canónica. Inversa exacta de `desde_canonica`.

    Es la que usa el editor de umbrales: el usuario escribe en la unidad activa y
    se guarda en canónica (`docs/06` §6.11), de modo que cambiar de unidad no
    reescribe ningún límite ni invalida la caché.
    """
    uni = dimension.unidad(unidad)
    canon = uni.conversion.a_canonica(valores, clase, param)
    if referencia_kpa is not None:
        if not dimension.admite_referencia:
            raise ErrorDeUnidad(f"la dimensión '{dimension.id}' no admite referencia de origen")
        if clase is Clase.PUNTO:
            canon = canon + referencia_kpa
    return canon


def etiqueta_de(dimension: Dimension, unidad: str, *, relativa: bool = False) -> str:
    """Etiqueta para el eje o la leyenda.

    Marca explícitamente si la presión es absoluta o relativa: «2 bar» sin más es
    la fuente de error más común al comparar logs de dos herramientas distintas.
    """
    uni = dimension.unidad(unidad)
    if dimension.admite_referencia:
        return f"{uni.etiqueta} ({'rel' if relativa else 'abs'})"
    return uni.etiqueta
