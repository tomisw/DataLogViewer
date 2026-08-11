"""Informe de plausibilidad por rango declarado de cada rol (tarea FG-10).

`docs/07-formatos-y-csv-generico.md` §7.7, punto 2 de «tres cosas que este
esquema habilita»: «si una columna asignada a `coolant_temp` tiene valores
entre 0 y 1, el asistente lo señala antes de importar. Esto atrapa el fallo
típico del importador genérico —mapear bien el nombre y mal la escala— antes
de que llegue a una decisión de tuning».

Y `docs/09` §9.9 dice para qué sirve de verdad: es el **escalón 2** del método
de reducción de revisiones («contrastar con el dato real»). Un factor de escala
equivocado no revienta nada: produce un número plausible que llega a una
decisión de puesta a punto. Este módulo es lo que convierte «revísame estos 34
factores» en «estos tres canales no cuadran con su rango declarado, y este es
el factor que los arreglaría».

LO QUE HACE ÚTIL AL INFORME NO ES «FUERA DE RANGO», ES EL DIAGNÓSTICO
=====================================================================
Decir que un canal está fuera de rango no ayuda a nadie: la pregunta siguiente
es siempre «¿y entonces qué le pasa?». Cada `Diagnostico` de este módulo es
una causa distinta con una acción distinta:

* `EXCURSION` — el canal está bien; unas pocas muestras salen del rango
  (sonda de λ fría al arrancar, presión de aceite que todavía no ha subido).
  No hay nada que arreglar. Distinguirlo de un canal mal escalado es la razón
  de ser de `fraccion_maxima_excursion` (ver más abajo).
* `UNIDAD_EQUIVOCADA` — los valores encajan si se interpretan como si ya
  vinieran en OTRA unidad de su propia dimensión: el `%` leído como fracción,
  el °C leído como kelvin. Es el fallo de §7.6 (unidad declarada en el
  fichero) y el informe nombra la unidad culpable.
* `AFR_EN_VEZ_DE_LAMBDA` — el caso que `data/roles.toml` pide cazar
  literalmente en `[roles.lambda_measured]`: «fuera de él suele significar
  sonda fría, desconectada, o que la columna trae AFR en lugar de lambda».
* `PRESION_RELATIVA_SIN_REFERENCIA` — una presión que encaja al sumarle la
  atmosférica: el canal viene en manométrico y la canónica es absoluta
  (`docs/06` §6.6, «2 bar sin más es la fuente de error más común»).
* `SIGNO_INVERTIDO` — el canal es el negativo de lo plausible (el retardo por
  knock de un fabricante que lo publica en positivo).
* `ESCALA_ERRONEA` — no hay unidad que lo explique, pero un factor decimal sí:
  el canal está 10, 100 o 1000 veces desplazado. **El informe dice qué factor
  lo arreglaría**, que es lo único que permite decidir sin volver al log.
* `FUERA_DE_RANGO_SIN_EXPLICAR` — está fuera y ninguna hipótesis lo explica.
  Es el más importante de todos precisamente porque no se puede automatizar:
  o el rol está mal asignado, o el sensor está roto, o el rango declarado en
  `roles.toml` es demasiado estrecho. Las tres exigen una persona.
* `DIMENSION_DISTINTA_DEL_ROL` — el formato declara el canal en una dimensión
  y el rol espera otra. Es el diagnóstico más concluyente de todos y el único
  que no necesita ni una muestra: si el canal mide presión y el rol espera una
  proporción, compararlo con el rango del rol no significa nada. Los dos casos
  que lo motivan salieron de ejecutar este informe contra `samples/real/`, y el
  segundo es el que obliga a que exista: `Fuel Flow Estimated` viene en L/h
  (`volume_flow`) y el rol `fuel_flow` espera kg/h, pero 17,7 L/h caen DENTRO
  del rango de 0 a 500 kg/h, así que el rango solo lo habría aprobado.
* `SIN_ROL` — un canal sin rol **no se puede juzgar**, y se dice en el
  informe en vez de omitirlo en silencio: un canal ausente del informe es
  indistinguible de un canal aprobado.
* `SIN_RANGO`, `SIN_DATOS`, `POCAS_MUESTRAS` — las otras tres formas de «no
  se puede juzgar», también explícitas y por el mismo motivo.

EXCURSIÓN CONTRA CANAL DESPLAZADO: EL CRITERIO Y POR QUÉ ES ESE
================================================================
Unas muestras fuera de rango al arrancar el motor no son lo mismo que el canal
entero desplazado, y confundirlos arruina el informe en las dos direcciones:
tratar toda excursión como defecto produce un aviso por canal y el usuario
aprende a ignorarlos; tratar todo defecto como excursión deja pasar
exactamente el error que esta tarea existe para cazar.

El criterio, en dos partes, y las dos declaradas en `data/umbrales.toml`:

1. **La fracción de muestras fuera** (`fraccion_maxima_excursion`). Por debajo
   o igual, es una excursión y no se propone ninguna corrección. Es la
   comprobación que va PRIMERO, antes de buscar hipótesis, y el orden no es
   casual: en un canal cuyo rango plausible es ancho (p. ej.
   `injector_duty`, 0 a 1,2) una hipótesis de factor 0,1 «arregla» un canal
   que ya estaba bien en el 99 % de sus muestras. Un canal con la inmensa
   mayoría de sus valores dentro de su rango tiene, por definición, la escala
   correcta; lo que le pasa está en otro sitio (un pico, un centinela que
   nadie limpió, un sensor que se despega un instante).

2. **Que la corrección propuesta deje el canal DENTRO**
   (`fraccion_maxima_tras_corregir`). Una hipótesis no se acepta porque
   «mejore» el canal, sino porque lo explica: tras aplicarla, la fracción
   fuera tiene que caer por debajo de este umbral. Un error de escala real es
   exacto —el factor 100 o explica el canal completo o no explica nada—, así
   que este umbral no está para dar margen al factor, sino para tolerar que el
   canal ya correctamente escalado siga teniendo su excursión de arranque.

Lo que queda en medio —mucho más que una excursión, y sin hipótesis que lo
explique— sale como `FUERA_DE_RANGO_SIN_EXPLICAR` con su fracción exacta, que
es la respuesta honesta: media hora de sensor desconectado no es un error de
escala y proponer un factor sería inventar.

El criterio NO usa la contigüidad temporal de las muestras fuera, que sería el
refinamiento evidente («las 98 muestras fuera son los primeros 5 s del log»).
Se ha dejado fuera a propósito: exigiría el eje de tiempo del canal
(`ChannelSeries.t`, F1-05) y con él NumPy de verdad, y no cambia ninguna de las
decisiones que el informe tiene que tomar hoy. Cuando el asistente de
importación (FG-11) muestre el informe, «dónde» empieza a importar y ese es su
sitio.

LOS CENTINELAS NO SON MEDIDAS
==============================
`docs/01` §1.13 y `data/units.toml [centinelas]` los declaran: `2147483647`,
`-2147483645`, `-2147483639`... El propio descriptor del formato lo escribe al
lado del tipo `Resistance`: «el canal 3 vale −2147483639, que es un CENTINELA de
sin dato, no una medida». Un centinela contado como valor fuera de rango
convierte el informe en ruido —el canal aparecería con el 100 % de sus muestras
fuera y una hipótesis de factor absurda— así que se excluyen antes de contar
nada, y se informa de cuántos había: un canal que es todo centinelas es un
hallazgo (`SIN_DATOS`), no un silencio.

El sitio natural para quitarlos es antes, sobre los enteros crudos
(`formatos/limpieza.nulificar_centinelas`, que los convierte en nulos). Este
módulo los vuelve a excluir porque no puede dar por hecho que esa etapa haya
corrido: el camino del CSV genérico tiene centinelas de TEXTO y otro
recorrido (`formatos/valores_csv.py`), y un informe cuya corrección dependa de
qué etapas previas se ejecutaron no es un informe en el que apoyar una
decisión. Se comparan por igualdad exacta y eso es correcto aquí a pesar de ser
coma flotante: el valor canónico del centinela se obtiene de la misma
multiplicación (`crudo * a_canonica`) que produjo las muestras, así que los dos
redondeos son el mismo (IEEE 754 es determinista para la misma operación con
los mismos operandos).

ADR-009: CERO BUCLES POR MUESTRA
=================================
Mismo patrón que `malla.py` y `reloj.py`: un `Protocol` `Vectorial` con los
nombres exactos de NumPy, de modo que el propio módulo `numpy` lo satisface sin
adaptador (`cast("Vectorial", numpy)`) y las pruebas pueden ejercitar ESTE
código con una implementación de biblioteca estándar. Solo tres funciones
—`sum`, `min`, `max`— porque todo lo demás son operadores (`<`, `>`, `&`, `|`,
`!=`, `[]`, aritmética), que cualquier implementación mínima da gratis y NumPy
también.

Los `for` de este módulo recorren canales (unos cientos), centinelas (una
docena) e hipótesis (una docena). Ninguno recorre muestras: cada hipótesis se
evalúa con dos comparaciones y una suma sobre el array completo, en C. El coste
es `n_hipotesis` pasadas por canal, no `n_muestras` iteraciones de Python.

Y no reimplementa ninguna conversión: las hipótesis de unidad se evalúan
llamando a `unidades.a_canonica` con `Clase.PUNTO` —una muestra es un punto,
no una diferencia—, que es la misma función que usa el resto del sistema y la
que ya sabe tratar las conversiones afines, recíprocas y parametrizadas.

LO QUE ESTE MÓDULO NO HACE (deliberado)
========================================
* **No corrige nada.** Produce la evidencia; aplicar un factor a
  `data/formats/*.toml` o a un perfil de importación es una decisión del
  propietario (`docs/09` §9.11: «rellenar un `confianza = "unknown"` con un
  valor plausible» es justo lo que no se hace sin preguntar).
* **No abre ficheros** (ADR-002): recibe los valores, el catálogo de roles, el
  de unidades y los umbrales ya cargados por quien llama.
* **No juzga la puesta a punto del motor.** Los rangos de `roles.toml` son
  anchos a propósito («detecta errores de escala, no de puesta a punto»); un
  motor mal afinado pero con canales bien escalados no genera ni un hallazgo.
  De eso se ocupan los detectores de `docs/04` §4.3, que son otra cosa.
* **No detecta un canal muerto ni uno pegado** (D16) ni los huecos (D18): eso
  es `huecos.py` y los detectores, y un canal pegado en un valor plausible es
  invisible para este informe por construcción.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, cast

from dlv_core.informes import Aviso
from dlv_core.roles import Asignacion, Confianza, Rol
from dlv_core.unidades import (
    Catalogo,
    Clase,
    Dimension,
    Parametrizada,
    Reciproca,
    a_canonica,
    desde_canonica,
    etiqueta_de,
)

__all__ = [
    "DIMENSION_DESCONOCIDA",
    "CanalJuzgable",
    "Diagnostico",
    "ErrorDePlausibilidad",
    "Hallazgo",
    "Hipotesis",
    "InformePlausibilidad",
    "RangoMostrado",
    "UmbralesPlausibilidad",
    "Vectorial",
    "evaluar_canal",
    "informe_de_plausibilidad",
    "rango_en_unidad_activa",
]

ROL_DE_ESTEQUIOMETRIA = "stoichiometry"
"""El rol cuyo valor parametriza la conversión λ -> AFR.

No es un umbral ni un número: es el NOMBRE con el que `data/units.toml` declara
la parametrización (`parametro_rol = "stoichiometry"`) y `data/roles.toml` el
rol. Se cita aquí para reconocer la hipótesis «esta columna trae AFR» sin
cablear el identificador de la unidad `afr`: la unidad de la dimensión de
mezcla que se parametriza por la estequiometría del combustible ES la de AFR,
por definición del propio catálogo. Reconocerla por su estructura y no por su
nombre es lo que hace que un catálogo que llame `afr_real` a esa unidad siga
funcionando.
"""

DIMENSION_DESCONOCIDA = "unknown"
"""Lo que un descriptor de formato escribe cuando NO sabe qué magnitud es un
canal (`data/formats/haltech_nsp.toml`, los 7 tipos `confianza = "unknown"`, que
se muestran en crudo y sin unidad como mitigación de R1). No es una dimensión:
es la ausencia de una, y por eso no puede chocar con la del rol."""

SEVERIDADES = ("critica", "alta", "media", "baja", "informativa")
"""Mismo vocabulario y mismo tipo (`str`) que `detectores.Incidencia.severidad`
y que `data/umbrales.toml`, para no introducir una segunda taxonomía en el
paquete. El orden de la tupla ES el orden de consecuencia."""

_ORDEN_DE_SEVERIDAD = {s: i for i, s in enumerate(SEVERIDADES)}


class ErrorDePlausibilidad(ValueError):
    """Uso incorrecto de este módulo, o umbrales que no se pueden interpretar.

    No es un hallazgo: un canal raro sale por `Hallazgo`, porque el informe
    tiene que poder enseñarse completo (E1.7 de `docs/02` §2.5: se avisa y se
    sigue). Esto otro —un umbral ausente, una fracción fuera de `(0, 1)`, un
    factor candidato de 0— es un fallo de quien llama.
    """


class Vectorial(Protocol):
    """Lo que este módulo necesita de NumPy, y nada más.

    Los nombres y las firmas son los de NumPy, así que el propio módulo
    `numpy` satisface el protocolo sin adaptador (mismo criterio que
    `malla.Vectorial` y `reloj.Vectorial`). Los parámetros son posicionales
    para que cualquier implementación pueda nombrarlos como quiera.

    * `sum(a)` — cuántas muestras cumplen una máscara booleana. Es la única
      reducción que hace falta para contar, y `bincount` sería excesivo: no hay
      grupos, hay un total.
    * `min(a)`, `max(a)` — el mínimo y el máximo observados, que son la mitad
      del valor del informe (`docs/01` §1.8 deduce escalas comparando el rango
      observado con el declarado, y esto es lo mismo automatizado). Son
      `numpy.min`/`numpy.max`, funciones de nivel de módulo, no los métodos
      `ndarray.min()`/`.max()`.
    """

    def sum(self, a: Any, /) -> Any: ...
    def min(self, a: Any, /) -> Any: ...
    def max(self, a: Any, /) -> Any: ...


def _numpy() -> Vectorial:
    """Importa NumPy en el momento de usarlo (mismo motivo que en `malla.py`:
    el módulo se puede importar y probar sin NumPy instalado)."""
    import numpy

    return cast("Vectorial", numpy)


# --------------------------------------------------------------------------- #
# Umbrales (configurables: data/umbrales.toml [plausibilidad])
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class UmbralesPlausibilidad:
    """Los cuatro umbrales del informe. **Sin valores por omisión en el código.**

    Regla 3 de `CLAUDE.md`: «un umbral cableado es una opinión disfrazada de
    física». Aquí se lleva al extremo de no tener valor por omisión ninguno:
    `desde_mapa` exige las cuatro claves y falla si falta alguna, igual que el
    motor de formatos exige `clave_tipo` en vez de suponer que se llama `Type`
    (FG-13). Un valor por omisión en el código es una copia que se puede
    desincronizar del fichero sin que nada se ponga en rojo; una excepción no.

    Su sitio es `data/umbrales.toml [plausibilidad]`, con la precedencia de
    siempre —anulación por canal > perfil activo > preferencias de usuario >
    fichero—, que resuelve quien llama y se aplica con `fusionar`.
    """

    fraccion_maxima_excursion: float
    """Hasta qué fracción de muestras fuera de rango se considera una excursión
    legítima del canal y no un defecto. Ver «EXCURSIÓN CONTRA CANAL
    DESPLAZADO» en la cabecera del módulo."""

    fraccion_maxima_tras_corregir: float
    """Fracción fuera que se tolera DESPUÉS de aplicar una hipótesis para
    aceptarla como explicación del canal."""

    muestras_minimas: int
    """Por debajo de esto no se juzga el canal (`POCAS_MUESTRAS`): una fracción
    calculada sobre menos muestras que `1 / fraccion_maxima_excursion` no puede
    distinguir una excursión de un defecto, porque una sola muestra fuera ya
    supera el umbral."""

    factores_candidatos: tuple[float, ...]
    """Factores de corrección a probar cuando ninguna unidad explica el canal.
    Son datos: el fichero decide si se buscan errores de 10, de 100, de 1000 o
    de signo. Se prueban de menor a mayor corrección (`|ln f|`), para que la
    explicación propuesta sea siempre la más pequeña que encaja."""

    def __post_init__(self) -> None:
        for nombre in ("fraccion_maxima_excursion", "fraccion_maxima_tras_corregir"):
            valor = float(getattr(self, nombre))
            if not 0.0 <= valor < 1.0:
                raise ErrorDePlausibilidad(
                    f"[plausibilidad].{nombre} = {valor!r} tiene que ser una fracción "
                    "en [0, 1); un umbral de 1 aceptaría cualquier canal"
                )
        if self.muestras_minimas < 1:
            raise ErrorDePlausibilidad(
                f"[plausibilidad].muestras_minimas = {self.muestras_minimas!r} tiene que ser >= 1"
            )
        for f in self.factores_candidatos:
            if f == 0.0 or f == 1.0:
                raise ErrorDePlausibilidad(
                    f"[plausibilidad].factores_candidatos contiene {f!r}: un factor de 0 no es "
                    "invertible y uno de 1 no corrige nada"
                )

    @classmethod
    def desde_mapa(cls, mapa: Mapping[str, Any]) -> UmbralesPlausibilidad:
        """Construye los umbrales desde el `[plausibilidad]` de
        `data/umbrales.toml` ya parseado por quien llama (ADR-002).

        Una clave ausente es un error, no un valor por omisión: ver el
        docstring de la clase.
        """
        faltan = [
            c
            for c in (
                "fraccion_maxima_excursion",
                "fraccion_maxima_tras_corregir",
                "muestras_minimas",
                "factores_candidatos",
            )
            if c not in mapa
        ]
        if faltan:
            raise ErrorDePlausibilidad(
                "data/umbrales.toml [plausibilidad] no declara: "
                + ", ".join(faltan)
                + "; son umbrales configurables y este módulo no lleva copia de ellos"
            )
        return cls(
            fraccion_maxima_excursion=float(mapa["fraccion_maxima_excursion"]),
            fraccion_maxima_tras_corregir=float(mapa["fraccion_maxima_tras_corregir"]),
            muestras_minimas=int(mapa["muestras_minimas"]),
            factores_candidatos=tuple(float(f) for f in mapa["factores_candidatos"]),
        )

    def fusionar(self, anulaciones: Mapping[str, Any]) -> UmbralesPlausibilidad:
        """Estos umbrales con las claves de `anulaciones` sustituidas.

        Es la pieza de la precedencia de `data/umbrales.toml` que le
        corresponde a este módulo: quien conoce el perfil activo, las
        preferencias del usuario y las anulaciones por canal las va aplicando
        de menor a mayor prioridad. Este módulo no decide de dónde sale cada
        capa —no las conoce— solo sabe combinarlas sin perder la validación.
        """
        if not anulaciones:
            return self
        base: dict[str, Any] = {
            "fraccion_maxima_excursion": self.fraccion_maxima_excursion,
            "fraccion_maxima_tras_corregir": self.fraccion_maxima_tras_corregir,
            "muestras_minimas": self.muestras_minimas,
            "factores_candidatos": self.factores_candidatos,
        }
        desconocidas = set(anulaciones) - set(base)
        if desconocidas:
            raise ErrorDePlausibilidad(
                f"anulaciones de umbral desconocidas: {sorted(desconocidas)}; "
                "un nombre mal escrito se ignoraría en silencio y el umbral seguiría "
                "siendo el de por omisión"
            )
        base.update(anulaciones)
        return UmbralesPlausibilidad.desde_mapa(base)


# --------------------------------------------------------------------------- #
# Entrada y salida
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class CanalJuzgable:
    """Un canal listo para juzgar: sus valores CANÓNICOS y su rol, si tiene.

    `asignacion` es exactamente lo que devuelve `roles.asignar_rol` (FG-09),
    `None` incluido. Se transporta el objeto entero y no solo el identificador
    del rol a propósito: `Confianza.DIFUSA` cambia la lectura del hallazgo por
    completo —si el rol se asignó por parecido de nombre, un canal fuera de
    rango es antes un rol mal asignado que una escala mal puesta— y el informe
    lo dice.

    `centinelas` son los valores centinela **en la misma unidad que
    `valores`** (canónica), no los enteros crudos de `data/units.toml`: quien
    llama conoce el `a_canonica` del tipo del canal y es el único que puede
    hacer esa multiplicación. Ver «LOS CENTINELAS NO SON MEDIDAS» en la
    cabecera.

    `dimension_declarada` es la dimensión que el FORMATO dice que tiene el
    canal (`formatos.nativo.Canal.dimension`, o la unidad declarada del CSV
    genérico de FG-06), y sirve para la comprobación más barata y más
    concluyente de todas: si el formato dice «presión» y el rol dice
    «proporción», compararlo con el rango del rol no significa nada. `None` y
    `"unknown"` valen lo mismo aquí —el formato no lo sabe— y desactivan la
    comprobación en vez de inventarse un choque.
    """

    nombre: str
    valores: Any
    asignacion: Asignacion | None = None
    centinelas: tuple[float, ...] = ()
    dimension_declarada: str | None = None


class Diagnostico(Enum):
    """Por qué el canal está (o no está) donde su rol dice que debería.

    Ver la cabecera del módulo para qué acción implica cada uno.
    """

    PLAUSIBLE = "plausible"
    EXCURSION = "excursion"
    DIMENSION_DISTINTA_DEL_ROL = "dimension_distinta_del_rol"
    UNIDAD_EQUIVOCADA = "unidad_equivocada"
    AFR_EN_VEZ_DE_LAMBDA = "afr_en_vez_de_lambda"
    PRESION_RELATIVA_SIN_REFERENCIA = "presion_relativa_sin_referencia"
    SIGNO_INVERTIDO = "signo_invertido"
    ESCALA_ERRONEA = "escala_erronea"
    FUERA_DE_RANGO_SIN_EXPLICAR = "fuera_de_rango_sin_explicar"
    SIN_ROL = "sin_rol"
    SIN_RANGO = "sin_rango"
    SIN_DATOS = "sin_datos"
    POCAS_MUESTRAS = "pocas_muestras"

    @property
    def es_defecto(self) -> bool:
        """¿Hay algo que corregir en la importación de este canal?

        `EXCURSION` no lo es (el canal está bien) y los cuatro «no se puede
        juzgar» tampoco: no afirman que haya un defecto, afirman que el informe
        no puede pronunciarse, que es una cosa distinta y se cuenta aparte.
        """
        return self in _DEFECTOS

    @property
    def es_juzgable(self) -> bool:
        """`False` en los cuatro casos en que el informe no puede pronunciarse."""
        return self not in _NO_JUZGABLES


_DEFECTOS = frozenset(
    {
        Diagnostico.DIMENSION_DISTINTA_DEL_ROL,
        Diagnostico.UNIDAD_EQUIVOCADA,
        Diagnostico.AFR_EN_VEZ_DE_LAMBDA,
        Diagnostico.PRESION_RELATIVA_SIN_REFERENCIA,
        Diagnostico.SIGNO_INVERTIDO,
        Diagnostico.ESCALA_ERRONEA,
        Diagnostico.FUERA_DE_RANGO_SIN_EXPLICAR,
    }
)

_NO_JUZGABLES = frozenset(
    {
        Diagnostico.SIN_ROL,
        Diagnostico.SIN_RANGO,
        Diagnostico.SIN_DATOS,
        Diagnostico.POCAS_MUESTRAS,
    }
)


@dataclass(slots=True, frozen=True)
class Hipotesis:
    """Una explicación candidata de por qué el canal está fuera de rango.

    O es una **unidad** de la dimensión del rol (los valores encajarían si ya
    vinieran en ella, y se comprueba con `unidades.a_canonica`), o es un
    **factor** desnudo de `factores_candidatos` (no hay unidad que lo explique
    pero el canal está 100 veces desplazado), o es la **referencia de presión**
    (el canal viene en manométrico). Nunca dos cosas a la vez.
    """

    unidad: str | None = None
    factor: float | None = None
    referencia_kpa: float | None = None
    diagnostico: Diagnostico = Diagnostico.ESCALA_ERRONEA

    def __post_init__(self) -> None:
        declarados = sum(
            1 for x in (self.unidad, self.factor, self.referencia_kpa) if x is not None
        )
        if declarados != 1:
            raise ErrorDePlausibilidad(
                "una hipótesis declara exactamente una de `unidad`, `factor` o "
                f"`referencia_kpa`; se declararon {declarados}"
            )


@dataclass(slots=True, frozen=True)
class Hallazgo:
    """Lo que el informe dice de UN canal. Uno por canal, siempre.

    Los canales plausibles también producen su `Hallazgo`
    (`Diagnostico.PLAUSIBLE`): un canal ausente del informe es indistinguible
    de un canal que nadie miró, y el informe tiene que poder decir «se
    juzgaron 320 canales, 3 no cuadran» sin que quien lo lee tenga que
    contar.

    Todos los valores numéricos están en unidad CANÓNICA (ADR-004). Pasarlos a
    la unidad activa es presentación y la hace `rango_en_unidad_activa`.
    """

    canal: str
    rol: str | None
    diagnostico: Diagnostico
    severidad: str
    detalle: str
    """Frase en español, lista para mostrar, que dice qué le pasa al canal y
    qué haría falta para arreglarlo. Es el campo que se lee; los demás son para
    ordenar, filtrar y comprobar."""

    n_muestras: int
    n_validas: int
    n_centinelas: int
    n_huecos: int
    n_fuera: int
    fraccion_fuera: float
    minimo_observado: float | None
    maximo_observado: float | None
    rango_plausible: tuple[float | None, float | None] | None
    rol_critico: bool = False
    rol_sin_confirmar: bool = False
    """El rol vino de una coincidencia difusa (`Confianza.DIFUSA`, FG-09). Si
    además el canal está fuera de rango, lo primero que hay que comprobar es el
    ROL, no la escala."""

    factor_que_arregla: float | None = None
    """El **multiplicador** que hay que aplicar a los valores para que el canal
    caiga dentro de su rango: 0,01 si los valores son 100 veces mayores de lo
    plausible. Se expresa como multiplicador y no como «divisor entre 100»
    porque es lo que se compone con el `a_canonica` del descriptor de formato
    sin darle la vuelta a nada; `detalle` lo dice además en las dos
    direcciones, que es como lo lee una persona."""

    unidad_probable: str | None = None
    """Identificador de la unidad de `data/units.toml` que explicaría el canal,
    si es de las hipótesis con nombre."""

    fraccion_fuera_corregida: float | None = None
    """Qué queda fuera después de aplicar la hipótesis. Es la evidencia de que
    la corrección propuesta explica el canal y no solo lo mejora."""

    @property
    def amplitud_observada(self) -> float | None:
        """`maximo - minimo` en canónica. Es un INTERVALO, no un punto: ver
        `rango_en_unidad_activa`."""
        if self.minimo_observado is None or self.maximo_observado is None:
            return None
        return self.maximo_observado - self.minimo_observado


@dataclass(slots=True, frozen=True)
class RangoMostrado:
    """El rango observado de un canal en la unidad activa, para enseñarlo.

    Las tres cifras NO se convierten igual, y esa es la razón de que esta clase
    exista en vez de dejar que quien pinta multiplique por un factor:

    * `minimo` y `maximo` son PUNTOS (`Clase.PUNTO`): valores absolutos del
      canal, les corresponde el desplazamiento de origen.
    * `amplitud` es un INTERVALO (`Clase.INTERVALO`): una diferencia entre dos
      valores del canal. Convertida como punto, una amplitud de 10 K saldría
      como −263,15 °C, que es la trampa del delta de `unidades.py` (F1-13)
      llegando por la puerta del informe.
    """

    minimo: float
    maximo: float
    amplitud: float
    etiqueta_unidad: str


def rango_en_unidad_activa(
    hallazgo: Hallazgo,
    *,
    dimension: Dimension,
    unidad: str,
    referencia_kpa: float | None = None,
) -> RangoMostrado | None:
    """El mínimo, el máximo y la amplitud observados, en la unidad activa.

    `None` si el canal no llegó a tener ningún valor válido (no hay rango que
    mostrar). Toda la aritmética la hace `unidades.desde_canonica`; esta
    función no la reimplementa, solo declara la clase correcta para cada una de
    las tres cifras (ver `RangoMostrado`).
    """
    if hallazgo.minimo_observado is None or hallazgo.maximo_observado is None:
        return None
    amplitud = hallazgo.maximo_observado - hallazgo.minimo_observado
    return RangoMostrado(
        minimo=float(
            desde_canonica(
                hallazgo.minimo_observado,
                dimension=dimension,
                unidad=unidad,
                clase=Clase.PUNTO,
                referencia_kpa=referencia_kpa,
            )
        ),
        maximo=float(
            desde_canonica(
                hallazgo.maximo_observado,
                dimension=dimension,
                unidad=unidad,
                clase=Clase.PUNTO,
                referencia_kpa=referencia_kpa,
            )
        ),
        amplitud=float(
            desde_canonica(
                amplitud,
                dimension=dimension,
                unidad=unidad,
                clase=Clase.INTERVALO,
                referencia_kpa=referencia_kpa,
            )
        ),
        etiqueta_unidad=etiqueta_de(dimension, unidad, relativa=referencia_kpa is not None),
    )


# --------------------------------------------------------------------------- #
# Máscaras (todo vectorizado; ver ADR-009 en la cabecera)
# --------------------------------------------------------------------------- #
def _mascara_finito(valores: Any) -> Any:
    """Máscara de las muestras que no son hueco.

    `valores == valores` es falso solo para NaN (IEEE 754): el mismo truco que
    `malla.py`, y por el mismo motivo -- evita meter `isnan` en el protocolo
    `Vectorial` por una sola comprobación. Un canal con huecos es lo normal en
    este dominio, no una anomalía (`docs/01` §1.4: muestreo disperso y
    multifrecuencia).
    """
    return valores == valores


def _excluir_centinelas(finito: Any, valores: Any, centinelas: Sequence[float]) -> Any:
    """`finito` menos las muestras que son un centinela de «sin dato».

    El bucle recorre los CENTINELAS (una docena en `data/units.toml`), no las
    muestras: cada iteración es una comparación vectorizada sobre el array
    completo. Ver «LOS CENTINELAS NO SON MEDIDAS» en la cabecera para por qué
    la igualdad exacta es correcta aquí.
    """
    util = finito
    for c in centinelas:
        util = util & (valores != c)
    return util


def _mascara_fuera(valores: Any, minimo: float | None, maximo: float | None) -> Any:
    """Máscara de las muestras fuera de `[minimo, maximo]`, cada extremo
    opcional (un rol puede declarar solo uno de los dos).

    Se construye siempre a partir de una comparación, nunca de un «array de
    falsos» inventado: así no hace falta pedirle al protocolo `Vectorial` una
    función para crear arrays. `valores != valores` es todo falso salvo en los
    NaN, y los NaN ya se han excluido antes de llegar aquí.
    """
    fuera = valores != valores
    if minimo is not None:
        fuera = fuera | (valores < minimo)
    if maximo is not None:
        fuera = fuera | (valores > maximo)
    return fuera


def _fraccion_fuera(
    valores: Any, rango: tuple[float | None, float | None], *, xp: Vectorial
) -> float:
    n = len(valores)
    if n == 0:
        return 0.0
    return float(int(xp.sum(_mascara_fuera(valores, rango[0], rango[1])))) / n


# --------------------------------------------------------------------------- #
# Hipótesis
# --------------------------------------------------------------------------- #
def _es_unidad_de_estequiometria(dimension: Dimension, unidad_id: str) -> bool:
    """¿Es la unidad que se parametriza con la estequiometría del combustible?

    Estructural, no por nombre: ver `ROL_DE_ESTEQUIOMETRIA`.
    """
    conversion = dimension.unidad(unidad_id).conversion
    return (
        isinstance(conversion, Parametrizada) and conversion.parametro_rol == ROL_DE_ESTEQUIOMETRIA
    )


def _hipotesis_de_unidad(dimension: Dimension) -> list[Hipotesis]:
    """Una hipótesis por unidad de la dimensión, salvo la canónica.

    La canónica se salta porque «los valores ya están en canónica» es la
    premisa, no una hipótesis: probarla siempre saldría dentro o fuera igual
    que el diagnóstico de partida.

    La unidad parametrizada por la estequiometría va PRIMERA cuando existe.
    No es una preferencia estética: en la dimensión de mezcla, `afr` y
    `afr_gasolina` explican los mismos valores, y la primera usa la
    estequiometría del combustible del propio log mientras la segunda cablea la
    de la gasolina. Si el orden dependiera de cómo estén escritas en
    `units.toml`, el diagnóstico de un log de E85 cambiaría al reordenar un
    fichero de datos.
    """
    candidatas = [u for u in dimension.unidades_disponibles if u != dimension.unidad_canonica]
    candidatas.sort(key=lambda u: not _es_unidad_de_estequiometria(dimension, u))
    hipotesis = []
    for u in candidatas:
        if _es_unidad_de_estequiometria(dimension, u):
            diagnostico = Diagnostico.AFR_EN_VEZ_DE_LAMBDA
        else:
            diagnostico = Diagnostico.UNIDAD_EQUIVOCADA
        hipotesis.append(Hipotesis(unidad=u, diagnostico=diagnostico))
    return hipotesis


def _hipotesis(
    dimension: Dimension | None,
    umbrales: UmbralesPlausibilidad,
    referencia_kpa: float | None,
) -> list[Hipotesis]:
    """Las hipótesis a probar, en orden de preferencia.

    Primero las que tienen NOMBRE —una unidad concreta, la referencia de
    presión—, porque explican el canal además de arreglarlo: «la columna viene
    en %» es una acción («declara la unidad de esa columna»), mientras que
    «multiplica por 0,01» solo es un parche que alguien tendrá que justificar
    después. Los factores desnudos van al final y ordenados por corrección
    creciente (`|ln f|`), de modo que la explicación propuesta sea siempre la
    más pequeña que encaja: entre «el signo está invertido» y «está 1000 veces
    desplazado», la primera es más probable y más fácil de comprobar.
    """
    hipotesis: list[Hipotesis] = []
    if dimension is not None and dimension.convertible:
        hipotesis += _hipotesis_de_unidad(dimension)
        if dimension.admite_referencia and referencia_kpa is not None:
            hipotesis.append(
                Hipotesis(
                    referencia_kpa=referencia_kpa,
                    diagnostico=Diagnostico.PRESION_RELATIVA_SIN_REFERENCIA,
                )
            )
    factores = sorted(umbrales.factores_candidatos, key=lambda f: abs(math.log(abs(f))))
    for f in factores:
        diagnostico = Diagnostico.SIGNO_INVERTIDO if abs(f) == 1.0 else Diagnostico.ESCALA_ERRONEA
        hipotesis.append(Hipotesis(factor=f, diagnostico=diagnostico))
    return hipotesis


def _aplicar(
    hipotesis: Hipotesis,
    valores: Any,
    *,
    dimension: Dimension | None,
    estequiometria: float | None,
) -> Any:
    """Los valores reinterpretados según la hipótesis.

    Las hipótesis con nombre delegan en `unidades.a_canonica` con
    `Clase.PUNTO` -- una muestra es un valor absoluto, no una diferencia -- y
    así este módulo no reimplementa ninguna aritmética de conversión y hereda
    gratis el tratamiento de las conversiones afines, recíprocas y
    parametrizadas.
    """
    if hipotesis.factor is not None:
        return valores * hipotesis.factor
    if dimension is None:  # pragma: no cover - lo garantiza `_hipotesis`
        raise ErrorDePlausibilidad("una hipótesis con nombre necesita la dimensión del rol")
    if hipotesis.referencia_kpa is not None:
        return a_canonica(
            valores,
            dimension=dimension,
            unidad=dimension.unidad_canonica,
            clase=Clase.PUNTO,
            referencia_kpa=hipotesis.referencia_kpa,
        )
    return a_canonica(
        valores,
        dimension=dimension,
        unidad=str(hipotesis.unidad),
        clase=Clase.PUNTO,
        param=estequiometria,
    )


def _factor_equivalente(
    hipotesis: Hipotesis,
    *,
    dimension: Dimension | None,
    estequiometria: float | None,
) -> float | None:
    """El multiplicador equivalente a la hipótesis, o `None` si no lo tiene.

    Una unidad que solo escala (`%`, `bar`, `AFR`) equivale a un factor, y
    decirlo es la mitad del valor del informe. Una que desplaza el origen
    (`°C`) o que es recíproca (`φ`, `km/L`) NO equivale a ningún factor, y
    devolver uno aproximado sería inventar: el informe dice la unidad y se
    calla el factor.
    """
    if hipotesis.factor is not None:
        return hipotesis.factor
    if hipotesis.unidad is None or dimension is None:
        return None
    conversion = dimension.unidad(hipotesis.unidad).conversion
    if conversion.desplaza_origen or isinstance(conversion, Reciproca):
        return None
    return float(conversion.a_canonica(1.0, Clase.PUNTO, estequiometria))


# --------------------------------------------------------------------------- #
# Prosa del diagnóstico
# --------------------------------------------------------------------------- #
def _numero(x: float) -> str:
    """Número con coma decimal, que es el separador de este proyecto en prosa."""
    return f"{x:.6g}".replace(".", ",")


def _frase_factor(factor: float) -> str:
    if factor == -1.0:
        return "invertir el signo"
    if abs(factor) < 1.0:
        return f"multiplicar por {_numero(factor)} (dividir entre {_numero(1.0 / factor)})"
    return f"multiplicar por {_numero(factor)}"


def _frase_rango(rango: tuple[float | None, float | None]) -> str:
    minimo, maximo = rango
    if minimo is None:
        return f"<= {_numero(float(maximo or 0.0))}"
    if maximo is None:
        return f">= {_numero(minimo)}"
    return f"[{_numero(minimo)}, {_numero(maximo)}]"


def _detalle(
    *,
    diagnostico: Diagnostico,
    rol: str | None,
    fraccion: float,
    n_fuera: int,
    n_validas: int,
    minimo: float | None,
    maximo: float | None,
    rango: tuple[float | None, float | None] | None,
    dimension_declarada: str | None,
    hipotesis: Hipotesis | None,
    factor: float | None,
    dimension_id: str | None,
    n_centinelas: int,
    sin_confirmar: bool,
) -> str:
    """La frase que se lee. Es el campo con el que el informe se usa."""
    observado = (
        f"observado [{_numero(minimo)}, {_numero(maximo)}]"
        if minimo is not None and maximo is not None
        else "sin valores observados"
    )
    esperado = f"esperado {_frase_rango(rango)}" if rango is not None else "sin rango declarado"
    # La cuenta absoluta y la fracción juntas, y no un porcentaje: quien revisa
    # el informe necesita saber si «fuera de rango» son 12 muestras de arranque
    # o 2 600 de 2 610, y un «0,46 %» no lo dice.
    cuantas = f"{n_fuera} de {n_validas} muestras válidas (fracción {_numero(fraccion)})"

    if diagnostico is Diagnostico.DIMENSION_DISTINTA_DEL_ROL:
        return (
            f"el formato declara este canal en la dimensión '{dimension_declarada}' y el rol "
            f"'{rol}' espera '{dimension_id}': el rango del rol no se le puede aplicar, porque "
            f"no mide la misma magnitud ({observado}, {esperado}). O el rol está mal asignado, o "
            f"data/roles.toml da como sinónimo de '{rol}' un nombre que en este formato es otra "
            f"cosa. Mientras no se resuelva, cualquier veredicto sobre su escala sería casual."
        )
    if diagnostico is Diagnostico.SIN_ROL:
        return (
            f"canal sin rol asignado: no hay rango declarado contra el que juzgarlo "
            f"({observado}). Asígnale un rol si debe participar en perfiles y detectores."
        )
    if diagnostico is Diagnostico.SIN_RANGO:
        return (
            f"el rol '{rol}' no declara rango plausible en data/roles.toml: el canal no se "
            f"puede juzgar ({observado})."
        )
    if diagnostico is Diagnostico.SIN_DATOS:
        if n_centinelas > 0:
            return (
                f"ninguna muestra utilizable: las {n_centinelas} que hay son centinelas de "
                "«sin dato» (docs/01 §1.13). El canal no mide nada en este log."
            )
        return "ninguna muestra utilizable: el canal está vacío o es todo huecos."
    if diagnostico is Diagnostico.POCAS_MUESTRAS:
        return (
            f"demasiadas pocas muestras válidas para juzgar la fracción fuera de rango "
            f"({observado}, {esperado})."
        )
    if diagnostico is Diagnostico.PLAUSIBLE:
        return f"todas las muestras dentro del rango del rol '{rol}' ({observado}, {esperado})."
    if diagnostico is Diagnostico.EXCURSION:
        return (
            f"excursión: {cuantas} salen del rango del rol '{rol}' "
            f"({observado}, {esperado}). La escala es correcta; suele ser el arranque del "
            "motor, un sensor frío o un pico aislado."
        )

    aviso_rol = (
        " El rol se asignó por parecido de nombre y sin confirmar: comprueba PRIMERO que el "
        "rol es el correcto, antes de tocar ninguna escala."
        if sin_confirmar
        else ""
    )
    cabeza = f"{cuantas} salen del rango del rol '{rol}' ({observado}, {esperado})"

    if diagnostico is Diagnostico.FUERA_DE_RANGO_SIN_EXPLICAR:
        return (
            f"{cabeza}, y ninguna unidad ni factor candidato lo explica. Puede ser el rol mal "
            f"asignado, el sensor averiado o el rango de data/roles.toml demasiado estrecho: "
            f"exige mirarlo.{aviso_rol}"
        )
    if hipotesis is None:  # pragma: no cover - los defectos siempre traen hipótesis
        return f"{cabeza}.{aviso_rol}"

    arreglo = ""
    if factor is not None:
        arreglo = f" {_frase_factor(factor).capitalize()} lo sitúa dentro."
    if diagnostico is Diagnostico.AFR_EN_VEZ_DE_LAMBDA:
        return (
            f"{cabeza}. Los valores encajan si la columna trae AFR y no λ: la unidad "
            f"'{hipotesis.unidad}' de '{dimension_id}' se parametriza con la estequiometría del "
            f"combustible, y con ella el canal cae dentro.{arreglo}{aviso_rol}"
        )
    if diagnostico is Diagnostico.UNIDAD_EQUIVOCADA:
        return (
            f"{cabeza}. Los valores encajan si la columna ya viene en la unidad "
            f"'{hipotesis.unidad}' de '{dimension_id}' en vez de la canónica.{arreglo}{aviso_rol}"
        )
    if diagnostico is Diagnostico.PRESION_RELATIVA_SIN_REFERENCIA:
        return (
            f"{cabeza}. Los valores encajan al sumarles la presión de referencia "
            f"({_numero(float(hipotesis.referencia_kpa or 0.0))} kPa): el canal parece venir en "
            f"presión relativa y la canónica es absoluta (docs/06 §6.6).{aviso_rol}"
        )
    if diagnostico is Diagnostico.SIGNO_INVERTIDO:
        return (
            f"{cabeza}. El canal es el negativo de lo plausible: invertir el signo lo sitúa "
            f"dentro.{aviso_rol}"
        )
    return (
        f"{cabeza}, de forma consistente: no hay unidad que lo explique, pero un factor de "
        f"escala sí.{arreglo}{aviso_rol}"
    )


def _severidad(diagnostico: Diagnostico, critico: bool) -> str:
    """La severidad, ordenada por CONSECUENCIA si el número está mal.

    Un rol `critico = true` de `data/roles.toml` alimenta un detector de
    severidad crítica (`docs/04` §4.3), así que un defecto de escala en él no
    solo da un número raro: hace que ese detector avise donde no debe o se
    calle donde debe avisar. Por eso el mismo diagnóstico sube un escalón
    cuando el rol es crítico, y por eso `SIN_DATOS` en un rol crítico no es
    informativo: un detector crítico sin datos es un detector apagado sin que
    nadie lo haya decidido.

    El mapa no es un umbral configurable: no hay ningún número en él. Sale de
    combinar un dato (`critico`, de `roles.toml`) con el diagnóstico.
    """
    if diagnostico.es_defecto:
        return "critica" if critico else "alta"
    if diagnostico is Diagnostico.EXCURSION:
        return "media" if critico else "baja"
    if diagnostico is Diagnostico.SIN_DATOS:
        return "media" if critico else "informativa"
    return "informativa"


# --------------------------------------------------------------------------- #
# Evaluación de un canal
# --------------------------------------------------------------------------- #
def evaluar_canal(
    canal: CanalJuzgable,
    catalogo_roles: Mapping[str, Rol],
    *,
    umbrales: UmbralesPlausibilidad,
    catalogo_unidades: Catalogo | None = None,
    estequiometria: float | None = None,
    xp: Vectorial | None = None,
) -> Hallazgo:
    """Juzga UN canal contra el rango plausible de su rol.

    `catalogo_unidades` es opcional y lo que aporta son las hipótesis con
    nombre: sin él el informe sigue funcionando, pero solo puede proponer
    factores desnudos («está 100 veces desplazado») en vez de nombrar la unidad
    culpable («viene en %»).

    `estequiometria` es el parámetro de la conversión λ -> AFR. Lo resuelve
    `parametros_conversion.resolver_parametro_de_canal` (F1-14) sobre el canal
    de rol `stoichiometry` del propio log; si no se pasa, `unidades.py` usa el
    `a_por_omision` que declara `data/units.toml`, que es el sitio donde vive
    ese número. Este módulo no lleva ninguna copia de él.
    """
    xp = xp if xp is not None else _numpy()
    valores = canal.valores
    n_muestras = len(valores)

    finito = _mascara_finito(valores)
    util = _excluir_centinelas(finito, valores, canal.centinelas)
    n_finito = int(xp.sum(finito)) if n_muestras else 0
    n_validas = int(xp.sum(util)) if n_muestras else 0
    validos = valores[util]

    asignacion = canal.asignacion
    rol = catalogo_roles.get(asignacion.rol) if asignacion is not None else None
    rol_id = asignacion.rol if asignacion is not None else None
    critico = bool(rol is not None and rol.critico)
    sin_confirmar = bool(asignacion is not None and asignacion.confianza is Confianza.DIFUSA)
    rango: tuple[float | None, float | None] | None = None
    if rol is not None and (rol.plausible_min is not None or rol.plausible_max is not None):
        rango = (rol.plausible_min, rol.plausible_max)

    minimo = float(xp.min(validos)) if n_validas else None
    maximo = float(xp.max(validos)) if n_validas else None

    dimension: Dimension | None = None
    if rol is not None and rol.dimension is not None and catalogo_unidades is not None:
        dimension = catalogo_unidades.dimensiones.get(rol.dimension)

    def hallazgo(
        diagnostico: Diagnostico,
        *,
        n_fuera: int = 0,
        fraccion: float = 0.0,
        hipotesis: Hipotesis | None = None,
        factor: float | None = None,
        fraccion_corregida: float | None = None,
    ) -> Hallazgo:
        return Hallazgo(
            canal=canal.nombre,
            rol=rol_id,
            diagnostico=diagnostico,
            severidad=_severidad(diagnostico, critico),
            detalle=_detalle(
                diagnostico=diagnostico,
                rol=rol_id,
                fraccion=fraccion,
                n_fuera=n_fuera,
                n_validas=n_validas,
                minimo=minimo,
                maximo=maximo,
                rango=rango,
                dimension_declarada=canal.dimension_declarada,
                hipotesis=hipotesis,
                factor=factor,
                dimension_id=rol.dimension if rol is not None else None,
                n_centinelas=n_finito - n_validas,
                sin_confirmar=sin_confirmar,
            ),
            n_muestras=n_muestras,
            n_validas=n_validas,
            n_centinelas=n_finito - n_validas,
            n_huecos=n_muestras - n_finito,
            n_fuera=n_fuera,
            fraccion_fuera=fraccion,
            minimo_observado=minimo,
            maximo_observado=maximo,
            rango_plausible=rango,
            rol_critico=critico,
            rol_sin_confirmar=sin_confirmar,
            factor_que_arregla=factor,
            unidad_probable=hipotesis.unidad if hipotesis is not None else None,
            fraccion_fuera_corregida=fraccion_corregida,
        )

    # Los cuatro «no se puede juzgar», en este orden a propósito: se informa de
    # la razón MÁS CONCRETA de las que se cumplen. «Este canal no trae ninguna
    # medida en este log» es una afirmación sobre el dato y se puede comprobar;
    # «no tiene rol» es una afirmación sobre la configuración de la importación.
    # Un canal sin rol Y sin datos tiene los dos problemas, pero el que
    # bloquea al otro es el primero: asignarle un rol no lo arreglaría.
    if n_validas == 0:
        return hallazgo(Diagnostico.SIN_DATOS)
    if rol is None:
        return hallazgo(Diagnostico.SIN_ROL)

    # La cuenta de muestras fuera se calcula aquí porque los diagnósticos
    # estructurales que siguen la usan como CONTEXTO (para que el informe diga
    # qué se observó), no como criterio.
    n_fuera = int(xp.sum(_mascara_fuera(validos, rango[0], rango[1]))) if rango else 0
    fraccion = n_fuera / n_validas

    # El choque de dimensión va antes que el rango, y antes incluso que «el rol
    # no declara rango» y «pocas muestras»: es estructural, no estadístico. Se
    # sabe con una muestra o con ninguna, y mientras esté ahí el rango del rol
    # compara magnitudes distintas -- kPa contra una fracción -- así que
    # cualquier veredicto sobre la escala sería casual. Los dos casos que lo
    # motivan salieron de los logs reales: `Ignition - Load` (el formato dice
    # `pressure`, el rol `engine_load` dice `ratio`) y `Fuel Flow Estimated`
    # (`volume_flow` contra el `mass_flow` de `fuel_flow`). El segundo es el que
    # obliga a que esta comprobación exista: 17,7 L/h caen DENTRO del rango de
    # 0 a 500 kg/h, así que el informe lo habría aprobado.
    declarada = canal.dimension_declarada
    if (
        declarada is not None
        and declarada != DIMENSION_DESCONOCIDA
        and rol.dimension is not None
        and declarada != rol.dimension
    ):
        return hallazgo(Diagnostico.DIMENSION_DISTINTA_DEL_ROL, n_fuera=n_fuera, fraccion=fraccion)

    if rango is None:
        return hallazgo(Diagnostico.SIN_RANGO)
    if n_validas < umbrales.muestras_minimas:
        return hallazgo(Diagnostico.POCAS_MUESTRAS)

    if n_fuera == 0:
        return hallazgo(Diagnostico.PLAUSIBLE)
    # La excursión se decide ANTES de buscar hipótesis: ver «EXCURSIÓN CONTRA
    # CANAL DESPLAZADO» en la cabecera. Un canal con el 99 % de sus muestras
    # dentro tiene la escala bien, y proponerle un factor sería un aviso falso.
    if fraccion <= umbrales.fraccion_maxima_excursion:
        return hallazgo(Diagnostico.EXCURSION, n_fuera=n_fuera, fraccion=fraccion)

    referencia = (
        catalogo_unidades.referencia_presion_por_omision_kpa
        if catalogo_unidades is not None
        else None
    )
    for h in _hipotesis(dimension, umbrales, referencia):
        try:
            corregidos = _aplicar(h, validos, dimension=dimension, estequiometria=estequiometria)
        except (ZeroDivisionError, ArithmeticError, ValueError):
            # Una hipótesis que no se puede evaluar sobre estos valores se
            # descarta: es una hipótesis menos, no un informe menos (E1.7: se
            # avisa y se sigue).
            #
            # El caso es una unidad RECÍPROCA (φ, km/L) sobre un canal que pasa
            # por cero, y ahí los dos motores de cómputo se comportan distinto:
            # con la implementación de biblioteca estándar de las pruebas salta
            # `ZeroDivisionError` y esta rama lo recoge, mientras que NumPy
            # devuelve `inf` con un aviso y no lanza. El resultado del informe es
            # el mismo por los dos caminos —`inf` queda fuera de cualquier rango
            # plausible, así que la hipótesis se rechaza igual— y esa
            # equivalencia es deliberada: un módulo cuyo veredicto dependa de con
            # qué implementación de `Vectorial` corre no es comprobable (la
            # lección de `malla.py`, donde `numpy.min` y el `min` de la
            # biblioteca estándar SÍ discrepaban ante un NaN).
            continue
        fraccion_corregida = _fraccion_fuera(corregidos, rango, xp=xp)
        if fraccion_corregida <= umbrales.fraccion_maxima_tras_corregir:
            return hallazgo(
                h.diagnostico,
                n_fuera=n_fuera,
                fraccion=fraccion,
                hipotesis=h,
                factor=_factor_equivalente(h, dimension=dimension, estequiometria=estequiometria),
                fraccion_corregida=fraccion_corregida,
            )

    return hallazgo(Diagnostico.FUERA_DE_RANGO_SIN_EXPLICAR, n_fuera=n_fuera, fraccion=fraccion)


# --------------------------------------------------------------------------- #
# El informe
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class InformePlausibilidad:
    """Los hallazgos de todos los canales, ORDENADOS POR CONSECUENCIA.

    El orden es el que pide la regla 6 de `CLAUDE.md` para una puerta G1:
    «ordenada por consecuencia si el número está mal», no por orden de
    aparición. Primero la severidad (un rol crítico con la escala mal va antes
    que uno accesorio), luego la fracción fuera de rango descendente y, a
    igualdad, el nombre del canal, para que dos ejecuciones sobre el mismo log
    den exactamente el mismo informe.
    """

    hallazgos: tuple[Hallazgo, ...]

    @property
    def defectos(self) -> tuple[Hallazgo, ...]:
        """Los canales con algo que corregir en la importación."""
        return tuple(h for h in self.hallazgos if h.diagnostico.es_defecto)

    @property
    def no_juzgables(self) -> tuple[Hallazgo, ...]:
        """Los canales sobre los que el informe no se puede pronunciar: sin
        rol, sin rango declarado, sin datos o con demasiadas pocas muestras. Se
        cuentan aparte porque su número mide la COBERTURA del informe, no la
        calidad del log."""
        return tuple(h for h in self.hallazgos if not h.diagnostico.es_juzgable)

    @property
    def excursiones(self) -> tuple[Hallazgo, ...]:
        return tuple(h for h in self.hallazgos if h.diagnostico is Diagnostico.EXCURSION)

    @property
    def plausibles(self) -> tuple[Hallazgo, ...]:
        return tuple(h for h in self.hallazgos if h.diagnostico is Diagnostico.PLAUSIBLE)

    def por_diagnostico(self) -> dict[Diagnostico, tuple[Hallazgo, ...]]:
        agrupado: dict[Diagnostico, list[Hallazgo]] = {}
        for h in self.hallazgos:
            agrupado.setdefault(h.diagnostico, []).append(h)
        return {d: tuple(v) for d, v in agrupado.items()}

    def avisos(self) -> tuple[Aviso, ...]:
        """Los defectos como `Aviso`, para `InformeImportacion.agregar` (F1-12).

        Solo los defectos: una excursión no es un aviso —el canal está bien— y
        un canal sin rol es información del asistente de importación, no una
        anomalía de la carga. Los códigos son los valores de `Diagnostico`;
        `informe_importacion.severidad_de_codigo` no los conoce y los
        clasificará como advertencia, que es su comportamiento documentado para
        un código nuevo y es el correcto aquí.
        """
        return tuple(Aviso(h.diagnostico.value, f"{h.canal}: {h.detalle}") for h in self.defectos)

    def a_lineas(self) -> list[str]:
        """Representación textual: el resumen y solo lo que hay que mirar.

        Los canales plausibles no se listan uno a uno —serían cientos y son
        justo los que no piden nada— pero sí se cuentan: «320 canales
        plausibles» es la cifra que dice que el informe ha mirado de verdad.
        """
        total = len(self.hallazgos)
        lineas = [
            f"Informe de plausibilidad: {total} canal(es), "
            f"{len(self.defectos)} con defecto, {len(self.excursiones)} con excursión, "
            f"{len(self.plausibles)} plausibles, {len(self.no_juzgables)} sin juzgar."
        ]
        pendientes = [h for h in self.hallazgos if h.diagnostico is not Diagnostico.PLAUSIBLE]
        if not pendientes:
            return [*lineas, "Todos los canales con rol caen dentro de su rango declarado."]
        lineas.append("")
        for h in pendientes:
            lineas.append(f"  [{h.severidad}] {h.canal} ({h.diagnostico.value}): {h.detalle}")
        return lineas

    def a_dict(self) -> dict[str, Any]:
        """Estructura serializable, para `dlv-api` y el asistente de
        importación (FG-11), sin que dependan de los tipos de `dlv-core`."""
        return {
            "total": len(self.hallazgos),
            "defectos": len(self.defectos),
            "excursiones": len(self.excursiones),
            "plausibles": len(self.plausibles),
            "no_juzgables": len(self.no_juzgables),
            "hallazgos": [
                {
                    "canal": h.canal,
                    "rol": h.rol,
                    "diagnostico": h.diagnostico.value,
                    "severidad": h.severidad,
                    "detalle": h.detalle,
                    "n_muestras": h.n_muestras,
                    "n_validas": h.n_validas,
                    "n_centinelas": h.n_centinelas,
                    "n_huecos": h.n_huecos,
                    "n_fuera": h.n_fuera,
                    "fraccion_fuera": h.fraccion_fuera,
                    "minimo_observado": h.minimo_observado,
                    "maximo_observado": h.maximo_observado,
                    "rango_plausible": list(h.rango_plausible)
                    if h.rango_plausible is not None
                    else None,
                    "rol_critico": h.rol_critico,
                    "rol_sin_confirmar": h.rol_sin_confirmar,
                    "factor_que_arregla": h.factor_que_arregla,
                    "unidad_probable": h.unidad_probable,
                    "fraccion_fuera_corregida": h.fraccion_fuera_corregida,
                }
                for h in self.hallazgos
            ],
        }


def _clave_de_orden(h: Hallazgo) -> tuple[int, float, str]:
    return (_ORDEN_DE_SEVERIDAD[h.severidad], -h.fraccion_fuera, h.canal)


def informe_de_plausibilidad(
    canales: Iterable[CanalJuzgable],
    catalogo_roles: Mapping[str, Rol],
    *,
    umbrales: UmbralesPlausibilidad,
    catalogo_unidades: Catalogo | None = None,
    estequiometria: float | None = None,
    umbrales_por_canal: Mapping[str, UmbralesPlausibilidad] | None = None,
    xp: Vectorial | None = None,
) -> InformePlausibilidad:
    """El informe completo, un hallazgo por canal, ordenado por consecuencia.

    `umbrales_por_canal` es el primer nivel de la precedencia de
    `data/umbrales.toml` («anulación por canal»): ya resuelto por quien llama,
    que es el único que sabe de qué perfil o de qué preferencia de usuario sale
    cada capa (mismo criterio que `conflictos.py` con su razón de amplitud).

    El bucle recorre CANALES —unos cientos en el log más grande de
    `samples/real/`—, no muestras: ADR-009 vive dentro de `evaluar_canal`.
    """
    por_canal = umbrales_por_canal or {}
    hallazgos = [
        evaluar_canal(
            canal,
            catalogo_roles,
            umbrales=por_canal.get(canal.nombre, umbrales),
            catalogo_unidades=catalogo_unidades,
            estequiometria=estequiometria,
            xp=xp,
        )
        for canal in canales
    ]
    hallazgos.sort(key=_clave_de_orden)
    return InformePlausibilidad(hallazgos=tuple(hallazgos))
