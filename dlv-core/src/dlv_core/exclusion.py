"""Filtros de exclusión para agregados: transitorio, corte, protección de motor
y retardo de transporte del sensor de λ (tarea F4-03).

Especificación: `docs/04-perfiles-motorsport.md` §4.6, segundo punto de la
«Tabla de corrección de combustible»:

    Se excluyen las muestras en transitorio, en corte, en protección de motor y
    durante el retardo de transporte del sensor de λ (configurable, por
    omisión 150 ms tras un cambio brusco de carga). Sin este filtro, la tabla
    generada es basura y este es el error más común en herramientas que
    ofrecen esta función.

POR QUÉ EXISTE ESTE MÓDULO
===========================
Un agregado (media de λ, tabla de corrección de combustible) calculado sobre
TODO el log miente en tres sitios a la vez: el corte de combustible en
deceleración (λ se va a pobre porque no hay inyección, no porque la mezcla
esté mal calibrada), el transitorio de un tip-in (la ECU está aplicando una
corrección deliberada de enriquecimiento, no la tabla base) y la ventana en la
que el sensor de λ todavía está leyendo la mezcla de ANTES del cambio de
carga (retardo de transporte físico del sensor). Promediar esas muestras con
las de régimen estacionario no es un error de redondeo: es un número con
aspecto de dato y calidad de basura, literalmente la frase de §4.6.

Este módulo SOLO calcula la máscara, por muestra y por motivo. No decide qué
se hace con ella: eso es de quien consume el informe (F4-05, la tabla de
corrección, que pasa `valor` a NaN donde `InformeDeExclusion.excluir.activa`
antes de llamar a `malla.construir_malla`, exactamente como esa función ya
descarta un NaN de `valor` sin que este módulo tenga que saber que existe
`malla.py`).

LOS CUATRO MOTIVOS, Y DE DÓNDE SALE CADA UMBRAL (regla 3 de CLAUDE.md)
========================================================================
«Un umbral cableado es una opinión disfrazada de física». Los TRES primeros
motivos no declaran un umbral propio en `data/umbrales.toml [exclusion]`:
reutilizan el que ya existe para el detector equivalente, con el mismo
razonamiento por el que `segmentacion.py` reutiliza
`[motor_de_deteccion].ventana_validez_ms` en vez de declararla otra vez --dos
copias del mismo número se pueden desincronizar sin que nada se ponga en
rojo--. `UmbralesDeExclusion.desde_mapa` documenta de qué sección de
`data/umbrales.toml` sale cada campo.

* **CORTE** -- el umbral de `[detectores.D14]` («Corte activo»,
  `cut_percentage > umbral_min`, 0,01). A diferencia de D14, aquí NO se
  excluye el matiz «fuera del limitador esperado»: D14 lo usa para no
  ALERTAR sobre un corte esperado (un limitador de revoluciones no es una
  anomalía que avisar), pero para excluir de un promedio da igual POR QUÉ hay
  corte -- durante cualquier corte, esperado o no, la lectura no representa
  la mezcla de la tabla y hay que descartarla igual. Aplicar el matiz de D14
  aquí dejaría dentro del promedio justo las muestras de rev-limiter, que son
  las de mezcla más extrema del log.
* **PROTECCIÓN DE MOTOR** -- el umbral de `[detectores.D13]`
  (`protection_level > umbral_min`, 1,0). Cualquier nivel de protección activo
  cambia lo que la ECU está haciendo (retardo de encendido, corrección de
  boost, enriquecimiento de λ -- las tres listadas en `[detectores.D13]` como
  las causas que ese nivel puede representar), así que la muestra no
  representa el mapa base que la tabla quiere describir.
* **TRANSITORIO** -- el disparo es el mismo que D15 («excursión de λ en
  tip-in»): la derivada de `throttle_position` por encima de
  `[detectores.D15].derivada_tps_min_por_s` (2,0 fracción/s), calculada con la
  ventana de suavizado de `[segmentacion].ventana_derivada_s` (0,25 s --
  medida sobre el dt p99 del AutoLog real, un número de MUESTREO y no de RPM,
  así que reutilizarlo para derivar mariposa en vez de régimen no cambia su
  procedencia). La exclusión dura `[detectores.D15].ventana_s` (0,5 s)
  DESPUÉS de que la derivada cruza el umbral: es la ventana en la que §4.2 P5
  documenta que las correcciones de enriquecimiento/empobrecimiento
  transitorio («Transient Throttle Fuel Enrichment/Disenrichment Rate») siguen
  activas.
* **RETARDO DE TRANSPORTE DEL SENSOR DE λ** -- el ÚNICO umbral genuinamente
  nuevo de esta tarea: `[exclusion].retardo_transporte_lambda_ms` (150 ms),
  cita literal de `docs/04` §4.6. Ese párrafo no dice qué cuenta como «cambio
  brusco de carga», así que este módulo reutiliza el MISMO disparo que
  TRANSITORIO (la derivada de mariposa sobre el umbral de D15): es la única
  definición de «cambio brusco» que el proyecto ya tiene escrita, y basar este
  motivo en otro canal (por ejemplo la derivada de `manifold_pressure`) sin
  que ningún documento lo pida sería inventar un segundo criterio para la
  misma frase de la especificación, no derivarlo de ella. Si el propietario
  prefiere basarlo en la carga (MAP) en vez de en la mariposa, es un cambio
  de una línea con su propio motivo escrito, no una corrección de un error.

  Confianza de `retardo_transporte_lambda_ms`: es una cita textual de
  `docs/04-perfiles-motorsport.md` §4.6, no una medición ni una suposición de
  quien escribe este módulo, así que NO lleva `confianza = "unknown"` -- el
  propio documento de especificación del propietario es la procedencia.

QUÉ PASA SI EL CANAL QUE DELATA LA EXCLUSIÓN NO EXISTE
========================================================
NO se aproxima con otro canal. Mismo criterio que
`segmentacion.ClaseNoCalculable` y `plausibilidad.Diagnostico.SIN_ROL`: un
motivo que no se puede calcular se declara `FiltroNoAplicado` con el rol que
falta, y NO se cuenta como «cero muestras excluidas por este motivo» -- eso
sería indistinguible de «este log no tiene cortes» y llevaría a creer que la
tabla está limpia de corte cuando el filtro nunca se pudo evaluar. La máscara
combinada (`InformeDeExclusion.excluir`) solo combina los motivos calculables
Y con rol confirmado: un filtro que silenciosamente no excluye nada es peor
que uno ausente, y `no_aplicadas` es la forma de no serlo en silencio.

CONFIANZA DEL ROL: UNA COINCIDENCIA DIFUSA NO ACTIVA UN FILTRO POR SU CUENTA
==============================================================================
`docs/07` §7.15 y F3-08 (`activacion_detectores.py`) desactivan un detector
CRÍTICO cuando el rol que lo alimenta viene de una coincidencia difusa sin
confirmar: prefieren no avisar a avisar en falso, porque una alerta falsa
enseña al usuario a ignorar las alertas. Este módulo no es un detector -- no
genera una alarma de la que el usuario pueda desconfiar-- pero el riesgo de
fondo es EL MISMO con el signo cambiado: si `cut_percentage` se emparejó por
parecido con un canal que en realidad mide otra cosa, usarlo para EXCLUIR
muestras de la tabla de corrección de combustible (F4-05, cuyo resultado
llega a ajustes de motor -- `segmentacion.py` dice lo mismo de dejar pasar una
muestra de deceleración a esa misma tabla) corrompe un número que el tuner va
a usar, y lo hace EN SILENCIO: no hay ninguna alerta roja de la que
desconfiar, así que este fallo es MÁS difícil de descubrir que el de un
detector, no menos.

Por eso `excluir` acepta `roles_sin_confirmar` y aplica el mismo criterio de
TRES estados que `activacion_detectores.evaluar_activacion`: activo,
desactivado por rol sin confirmar (el usuario lo arregla confirmando el rol,
`FiltroNoAplicado.roles_sin_confirmar`) y no calculable por rol ausente (no
hay nada que confirmar, `FiltroNoAplicado.roles_ausentes`). Es una EXTENSIÓN
del criterio de F3-08 a un módulo nuevo, no algo que F3-08 ya decidiera:
F3-08 solo mira los 18 detectores de `[detectores]`, y `segmentacion.py`
(F3-16) decide explícitamente NO mirar la confianza del rol porque no es su
responsabilidad («no sabe de confianza de asignación»; esa desactivación es
según su propio docstring de quien construye el mapa de roles antes de
llamarlo). Aquí sí me pareció necesario mirarla, precisamente porque el
consumidor de este filtro concreto (F4-05) es una tabla que se usa para
tocar el motor y no un panel de lectura. Si el propietario prefiere que esta
capa de confianza se resuelva en F4-05 en vez de aquí, es una decisión suya:
`roles_sin_confirmar` por omisión es un conjunto vacío, así que no mirarla es
tan simple como no pasarla.

ADR-009
=======
Los únicos bucles de este módulo recorren los CUATRO motivos
(`RazonDeExclusion`), nunca las muestras. El «sostenido durante N segundos
tras el disparo» de TRANSITORIO y RETARDO_TRANSPORTE_LAMBDA se apoya en
`primitivas.extremo_en_ventana` -- que ya resuelve «¿hubo una muestra activa
en los últimos N ms?» con una tabla dispersa por duplicación (bucle sobre
NIVELES, media docena, no sobre muestras)-- en vez de reinventar la ventana
con desplazamientos de array y un bucle propio.

LA CLASE DE CONVERSIÓN (regla 4 de CLAUDE.md)
===============================================
Las tres series de entrada (`throttle_position`, `cut_percentage`,
`protection_level`) tienen que llegar como `Clase.PUNTO`, igual que
`segmentacion._series_en_la_rejilla`: lo que sale del almacén es un canal, no
una derivada. La derivada de mariposa que usan TRANSITORIO y
RETARDO_TRANSPORTE_LAMBDA es interna a este módulo (vía `primitivas.derivada`,
que ya marca `Clase.TASA`) y nunca sale de aquí como si fuera un punto.

LO QUE ESTE MÓDULO NO HACE
============================
* No abre ficheros (ADR-002): recibe las series y los umbrales ya cargados.
* No convierte unidades (ADR-004): todo entra y sale en canónica.
* No genera una `Incidencia` ni decide severidad: esto no es un detector de
  §4.3, es un filtro de calidad para un agregado, y su salida es una máscara,
  no una lista de eventos para un panel.
* No sabe de `manifold_pressure` ni de ningún otro canal de carga: el «cambio
  brusco de carga» de §4.6 se implementa con mariposa por las razones de
  arriba, no porque MAP esté descartado para siempre.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from dlv_core.primitivas import (
    Condicion,
    Direccion,
    Extremo,
    Serie,
    Vectorial,
    alinear,
    derivada,
    extremo_en_ventana,
    umbral_con_histeresis,
)
from dlv_core.segmentacion import ROL_MARIPOSA
from dlv_core.unidades import Clase

__all__ = [
    "ROL_CORTE",
    "ROL_MARIPOSA",
    "ROL_PROTECCION",
    "ErrorDeExclusion",
    "FiltroNoAplicado",
    "InformeDeExclusion",
    "RazonDeExclusion",
    "UmbralesDeExclusion",
    "excluir",
]

MS_POR_S = 1000.0

ROL_CORTE = "cut_percentage"
"""El rol de `data/roles.toml` para el porcentaje de corte de encendido o
inyección (dimensión `ratio`, D14)."""

ROL_PROTECCION = "protection_level"
"""El rol de `data/roles.toml` para el nivel de protección de motor
(dimensión `enum`, D13)."""


class ErrorDeExclusion(ValueError):
    """Uso incorrecto del módulo, o una configuración que no se puede aplicar.

    Un log raro no produce excepciones: produce un `InformeDeExclusion`, con
    los motivos que no se pudieron calcular explicados en `no_aplicadas`. Esto
    otro -- una serie que no es `Clase.PUNTO`, un umbral que falta o es
    negativo donde no puede serlo-- es un fallo de quien llama o de este
    módulo, y callarlo produciría una exclusión plausible y falsa.
    """


# --------------------------------------------------------------------------- #
# Los cuatro motivos
# --------------------------------------------------------------------------- #
class RazonDeExclusion(Enum):
    """Los cuatro motivos de exclusión de `docs/04` §4.6, ninguno con
    prioridad sobre otro: no son excluyentes, se combinan con OR
    (`InformeDeExclusion.excluir`), porque una muestra en corte Y en
    protección de motor a la vez sigue siendo una muestra que hay que excluir,
    no dos veces más excluida."""

    TRANSITORIO = "transitorio"
    CORTE = "corte"
    PROTECCION_MOTOR = "proteccion_motor"
    RETARDO_TRANSPORTE_LAMBDA = "retardo_transporte_lambda"

    @property
    def roles_requeridos(self) -> tuple[str, ...]:
        """Los roles sin los cuales este motivo NO se puede calcular.

        Sin ellos el motivo no se aproxima con otro canal: se declara
        `FiltroNoAplicado` (ver la cabecera del módulo, «Qué pasa si el canal
        que delata la exclusión no existe»).
        """
        return _ROLES_REQUERIDOS[self]


_ROLES_REQUERIDOS: dict[RazonDeExclusion, tuple[str, ...]] = {
    RazonDeExclusion.TRANSITORIO: (ROL_MARIPOSA,),
    RazonDeExclusion.CORTE: (ROL_CORTE,),
    RazonDeExclusion.PROTECCION_MOTOR: (ROL_PROTECCION,),
    RazonDeExclusion.RETARDO_TRANSPORTE_LAMBDA: (ROL_MARIPOSA,),
}

_CLAVES_ESCALARES: tuple[str, ...] = (
    "transitorio_derivada_tps_min_por_s",
    "transitorio_ventana_s",
    "retardo_transporte_lambda_ms",
    "corte_umbral_min",
    "proteccion_umbral_min",
    "ventana_derivada_tps_s",
    "ventana_validez_ms",
)
"""Las siete claves escalares que `desde_mapa` exige y que `fusionar` admite.
Una sola lista para las dos, mismo motivo que `segmentacion._CLAVES_ESCALARES`:
si estuvieran escritas dos veces, una anulación de una clave nueva se
aceptaría en un sitio y se rechazaría en el otro."""


# --------------------------------------------------------------------------- #
# Umbrales configurables
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class UmbralesDeExclusion:
    """Los umbrales de los cuatro filtros. **Sin valores por omisión en el
    código** (regla 3 de `CLAUDE.md`): `desde_mapa` exige las siete claves y
    falla si falta alguna.

    Quien construye el mapa que se le pasa a `desde_mapa` es responsable de
    fusionar estas SIETE claves desde CUATRO secciones distintas de
    `data/umbrales.toml`, con la precedencia de siempre (canal > perfil >
    usuario > fichero) resuelta ya antes de llegar aquí -- ver la cabecera del
    módulo para el porqué de cada reutilización:

        transitorio_derivada_tps_min_por_s <- [detectores.D15].derivada_tps_min_por_s
        transitorio_ventana_s              <- [detectores.D15].ventana_s
        corte_umbral_min                   <- [detectores.D14].umbral_min
        proteccion_umbral_min              <- [detectores.D13].umbral_min
        ventana_derivada_tps_s             <- [segmentacion].ventana_derivada_s
        ventana_validez_ms                 <- [motor_de_deteccion].ventana_validez_ms
        retardo_transporte_lambda_ms       <- [exclusion].retardo_transporte_lambda_ms

    Los nombres de campo NO coinciden con los nombres de clave de origen a
    propósito: `[detectores.D13]` y `[detectores.D14]` declaran los dos un
    `umbral_min`, y fusionar dos secciones con la misma clave en un solo mapa
    perdería una de las dos. Renombrar al fusionar es responsabilidad de quien
    llama, documentada aquí para que no haga falta leer el código para
    hacerlo bien.

    Todos los valores están en unidad CANÓNICA (ADR-004): fracción de mariposa
    por segundo, segundos, milisegundos, fracción de corte, nivel de
    protección (adimensional).
    """

    transitorio_derivada_tps_min_por_s: float
    """Derivada de mariposa (fracción/s) por encima de la cual se considera un
    cambio brusco de carga. Dispara TRANSITORIO y RETARDO_TRANSPORTE_LAMBDA."""

    transitorio_ventana_s: float
    """Cuánto dura la exclusión de TRANSITORIO después del disparo."""

    retardo_transporte_lambda_ms: float
    """Cuánto dura la exclusión de RETARDO_TRANSPORTE_LAMBDA después del
    disparo. En milisegundos, no en segundos, porque así lo cita `docs/04`
    §4.6 («150 ms») y convertirlo al declarar la constante sería una
    oportunidad más de invertir el factor 1000 sin que nada lo compruebe."""

    corte_umbral_min: float
    """`cut_percentage` por encima del cual se considera que hay corte."""

    proteccion_umbral_min: float
    """`protection_level` por encima del cual se considera protección activa."""

    ventana_derivada_tps_s: float
    """Ventana de suavizado con la que se calcula la derivada de mariposa
    (`primitivas.derivada`). No es una ventana de exclusión: es cuánta
    historia mira la derivada antes de decidir la pendiente."""

    ventana_validez_ms: float
    """Multi-tasa (`docs/04` §4.5): cuánto sigue valiendo el último valor
    conocido de un canal al llevarlo a la rejilla de referencia con
    `alinear`."""

    def __post_init__(self) -> None:
        if self.transitorio_derivada_tps_min_por_s <= 0.0:
            raise ErrorDeExclusion(
                "transitorio_derivada_tps_min_por_s = "
                f"{self.transitorio_derivada_tps_min_por_s!r} tiene que ser positiva: un "
                "umbral de disparo en 0 o negativo dispararía siempre"
            )
        if self.transitorio_ventana_s <= 0.0:
            raise ErrorDeExclusion(
                f"transitorio_ventana_s = {self.transitorio_ventana_s!r} tiene que ser "
                "positiva: sin ventana no hay nada que sostener tras el disparo"
            )
        if self.retardo_transporte_lambda_ms < 0.0:
            raise ErrorDeExclusion(
                f"retardo_transporte_lambda_ms = {self.retardo_transporte_lambda_ms!r} no "
                "puede ser negativo"
            )
        if not 0.0 <= self.corte_umbral_min <= 1.0:
            raise ErrorDeExclusion(
                f"corte_umbral_min = {self.corte_umbral_min!r} tiene que ser una FRACCIÓN "
                "en [0, 1]: `cut_percentage` es de dimensión `ratio` (data/roles.toml), no "
                "un porcentaje"
            )
        if self.proteccion_umbral_min <= 0.0:
            raise ErrorDeExclusion(
                f"proteccion_umbral_min = {self.proteccion_umbral_min!r} tiene que ser "
                "positivo: el nivel 0 es «sin protección» y no puede ser el umbral de "
                "activación"
            )
        if self.ventana_derivada_tps_s <= 0.0:
            raise ErrorDeExclusion(
                f"ventana_derivada_tps_s = {self.ventana_derivada_tps_s!r} tiene que ser "
                "positiva: sin ventana no hay derivada"
            )
        if self.ventana_validez_ms < 0.0:
            raise ErrorDeExclusion(
                f"ventana_validez_ms = {self.ventana_validez_ms!r} no puede ser negativo"
            )

    @classmethod
    def desde_mapa(cls, mapa: Mapping[str, Any]) -> UmbralesDeExclusion:
        """Construye los umbrales desde un mapa ya fusionado por quien llama
        (ADR-002), con las claves renombradas como documenta la clase.

        Una clave ausente es un error, no un valor por omisión: un umbral de
        exclusión que faltara en silencio dejaría pasar al agregado
        exactamente las muestras que esta tarea existe para descartar.
        """
        faltan = [c for c in _CLAVES_ESCALARES if c not in mapa]
        if faltan:
            raise ErrorDeExclusion(
                "el mapa de umbrales de exclusión no declara: "
                + ", ".join(faltan)
                + "; ver `UmbralesDeExclusion` para de qué sección de data/umbrales.toml "
                "sale cada una (D13, D14, D15, [segmentacion], [motor_de_deteccion] y "
                "[exclusion])"
            )
        valores = {nombre: float(mapa[nombre]) for nombre in _CLAVES_ESCALARES}
        return cls(**valores)

    def fusionar(self, anulaciones: Mapping[str, Any]) -> UmbralesDeExclusion:
        """Estos umbrales con las claves de `anulaciones` sustituidas.

        La pieza de la precedencia (canal > perfil > usuario > fichero) que le
        toca a este módulo. Una clave desconocida es un error: un nombre mal
        escrito se ignoraría en silencio y el umbral seguiría siendo el de por
        omisión sin que nadie se enterara.
        """
        if not anulaciones:
            return self
        base: dict[str, Any] = {nombre: getattr(self, nombre) for nombre in _CLAVES_ESCALARES}
        desconocidas = set(anulaciones) - set(base)
        if desconocidas:
            raise ErrorDeExclusion(
                f"anulaciones de exclusión desconocidas: {sorted(desconocidas)}; un nombre "
                "mal escrito se ignoraría en silencio y el umbral seguiría siendo el de por "
                "omisión"
            )
        base.update(anulaciones)
        return UmbralesDeExclusion.desde_mapa(base)


# --------------------------------------------------------------------------- #
# Resultado
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class FiltroNoAplicado:
    """Un motivo que no se calculó, con el porqué exacto.

    TRES estados, no dos -- mismo criterio que
    `activacion_detectores.EstadoDetector` (F3-08, `docs/07` §7.15):
    `roles_ausentes` (el log no trae el canal; no hay nada que confirmar) y
    `roles_sin_confirmar` (el rol está y no está confirmado; un clic lo
    arregla) son dos acciones distintas para el usuario, y colapsarlas en un
    «no aplicado» genérico se lo escondería.
    """

    razon: RazonDeExclusion
    roles_ausentes: tuple[str, ...]
    roles_sin_confirmar: tuple[str, ...]

    @property
    def motivo(self) -> str:
        """Frase lista para el informe de importación, con los roles por nombre."""
        partes: list[str] = []
        if self.roles_ausentes:
            partes.append(
                f"el log no trae {_lista(self.roles_ausentes)}: el filtro de "
                f"{self.razon.value} no se puede calcular, no se aproxima con otro canal"
            )
        if self.roles_sin_confirmar:
            partes.append(
                f"{_lista(self.roles_sin_confirmar)} viene de una coincidencia sin "
                f"confirmar: el filtro de {self.razon.value} no se aplica hasta que se "
                "confirme el rol, para no excluir muestras de un agregado basándose en "
                "una conjetura (docs/07 §7.15)"
            )
        return " Y ".join(partes)


def _lista(nombres: tuple[str, ...]) -> str:
    """«el rol x» o «los roles x, y», para que el motivo se lea como una frase.

    Copiado y no importado de `activacion_detectores._lista`: es una función
    privada de ese módulo y las dos son ayudantes de formato de texto sin
    ninguna decisión compartida que desincronizar."""
    if len(nombres) == 1:
        return f"el rol {nombres[0]}"
    return f"los roles {', '.join(nombres)}"


@dataclass(slots=True, frozen=True)
class InformeDeExclusion:
    """Lo que devuelve `excluir`: la máscara combinada, la máscara por motivo y
    lo que no se pudo calcular.

    Los tres van juntos porque las tres respuestas se leen a la vez: una tabla
    de corrección de combustible con el 90 % excluido no significa lo mismo si
    el filtro de corte nunca se pudo calcular que si de verdad hay corte en el
    90 % del log.
    """

    t_ms: Any
    """La rejilla de referencia que pasó quien llama a `excluir`."""

    por_razon: Mapping[RazonDeExclusion, Condicion]
    """Solo los motivos calculables Y con todos sus roles confirmados. Un
    motivo ausente de este mapa está en `no_aplicadas`, nunca con una
    `Condicion` de puro `False`: eso sería indistinguible de «se calculó y no
    hay ninguna muestra que excluir por este motivo»."""

    no_aplicadas: tuple[FiltroNoAplicado, ...]

    excluir: Condicion
    """OR (Kleene) de todos los motivos calculables. Si `no_aplicadas` no está
    vacío, esta máscara NO es «excluir todo lo que hay que excluir»: es
    «excluir todo lo que se pudo calcular», y la diferencia es exactamente lo
    que dice `no_aplicadas`."""

    def es_calculable(self, razon: RazonDeExclusion) -> bool:
        return razon in self.por_razon

    def fraccion_excluida(self, *, xp: Vectorial | None = None) -> float:
        """Fracción de la rejilla de referencia marcada para excluir por AL
        MENOS un motivo calculable.

        Sobre una rejilla vacía o sin ningún motivo calculable es 0,0 y no un
        error, con el mismo criterio que `segmentacion.Cobertura.
        fraccion_cubierta`: no hay nada que repartir.
        """
        xp = _xp(xp)
        n = len(self.t_ms)
        if n == 0:
            return 0.0
        return float(xp.sum(self.excluir.activa & self.excluir.valido)) / n


# --------------------------------------------------------------------------- #
# Cálculo
# --------------------------------------------------------------------------- #
def _numpy() -> Vectorial:
    """Importa NumPy en el momento de usarlo y no al importar el módulo, igual
    que `primitivas._numpy` y `segmentacion._numpy`: así este módulo se puede
    importar y probar sin NumPy instalado."""
    import numpy

    return cast("Vectorial", numpy)


def _xp(xp: Vectorial | None) -> Vectorial:
    return xp if xp is not None else _numpy()


def _alinear_punto(
    serie: Serie, t_referencia_ms: Any, umbrales: UmbralesDeExclusion, *, xp: Vectorial
) -> Serie:
    """Comprueba la clase de conversión y lleva la serie a la rejilla de
    referencia (regla 4 y `docs/04` §4.5).

    Un canal tal como sale del almacén es `Clase.PUNTO`; aceptar otra clase
    aquí dejaría comparar una derivada ya calculada con un umbral de canal, la
    trampa del delta con otro disfraz (mismo criterio que
    `segmentacion._series_en_la_rejilla`).
    """
    if serie.clase is not Clase.PUNTO:
        raise ErrorDeExclusion(
            f"la serie es de clase {serie.clase.value} y tiene que ser PUNTO: un canal tal "
            "como sale del almacén es un punto, y compararlo ya derivado sería la trampa "
            "del delta"
        )
    return alinear(serie, t_referencia_ms, ventana_validez_ms=umbrales.ventana_validez_ms, xp=xp)


def _condicion_corte(
    serie: Serie, t_referencia_ms: Any, umbrales: UmbralesDeExclusion, *, xp: Vectorial
) -> Condicion:
    """CORTE: `cut_percentage` por encima de `corte_umbral_min`, muestra a
    muestra y sin permanencia.

    A propósito, sin la permanencia mínima de 100 ms que D14 aplica como
    DETECTOR (`[detectores.D14].permanencia_s`): esa permanencia existe para
    no generar una incidencia por un pico de una sola muestra, pero
    `cut_percentage` es una salida directa de la ECU y no una lectura
    analógica ruidosa -- si dice que hubo corte en una muestra, lo hubo, y
    aplicar aquí la misma permanencia dejaría dentro del promedio muestras
    individuales de corte real.
    """
    alineada = _alinear_punto(serie, t_referencia_ms, umbrales, xp=xp)
    return umbral_con_histeresis(
        alineada,
        entrada=umbrales.corte_umbral_min,
        salida=umbrales.corte_umbral_min,
        direccion=Direccion.ARRIBA,
        xp=xp,
    )


def _condicion_proteccion(
    serie: Serie, t_referencia_ms: Any, umbrales: UmbralesDeExclusion, *, xp: Vectorial
) -> Condicion:
    """PROTECCION_MOTOR: `protection_level` por encima de `proteccion_umbral_min`,
    muestra a muestra y sin permanencia (mismo motivo que `_condicion_corte`:
    es un nivel que publica la ECU, no una señal analógica)."""
    alineada = _alinear_punto(serie, t_referencia_ms, umbrales, xp=xp)
    return umbral_con_histeresis(
        alineada,
        entrada=umbrales.proteccion_umbral_min,
        salida=umbrales.proteccion_umbral_min,
        direccion=Direccion.ARRIBA,
        xp=xp,
    )


def _disparo_cambio_de_carga(
    mariposa: Serie, t_referencia_ms: Any, umbrales: UmbralesDeExclusion, *, xp: Vectorial
) -> Condicion:
    """«Cambio brusco de carga»: `|derivada(mariposa)| > transitorio_derivada_tps_min_por_s`.

    Valor absoluto porque tanto un tip-in (mariposa abriendo) como un tip-out
    o un DFCO (mariposa cerrando de golpe) perturban la mezcla y el sensor de
    λ igual de bruscamente; §4.2 P5 lista enriquecimiento Y empobrecimiento
    transitorio como las dos mitades del mismo fenómeno.
    """
    alineada = _alinear_punto(mariposa, t_referencia_ms, umbrales, xp=xp)
    tasa = derivada(alineada, ventana_s=umbrales.ventana_derivada_tps_s, xp=xp)
    activa = xp.abs(tasa.v) > umbrales.transitorio_derivada_tps_min_por_s
    return Condicion(t_ms=tasa.t_ms, activa=activa, valido=tasa.valido)


def _sostener_tras_disparo(disparo: Condicion, ventana_s: float, *, xp: Vectorial) -> Condicion:
    """«¿Hubo un disparo en los últimos `ventana_s` segundos, incluyendo
    ahora?», vectorizado con `primitivas.extremo_en_ventana`.

    Es equivalente a "flanco de subida + sostenido `ventana_s` después" sin
    tener que extraer los flancos: el máximo de una serie 0/1 en la ventana
    `[-ventana_s, 0]` es 1 si y solo si `disparo` fue verdadero en algún
    instante de esa ventana, ya fuera un pulso aislado o un tramo entero por
    encima del umbral -- que es exactamente «sostenido desde el último
    disparo», incluyendo el caso de disparos que se solapan y se reinician
    unos a otros sin ningún caso especial.

    `disparo.activa` viaja como si fuera `Clase.PUNTO` aunque no es una
    magnitud física: es un indicador 0/1 interno a este módulo que nunca sale
    de aquí, así que no hay ninguna conversión de unidad que pueda leerlo mal.
    """
    indicador = Serie(t_ms=disparo.t_ms, v=disparo.activa, clase=Clase.PUNTO, valido=disparo.valido)
    ventana = extremo_en_ventana(
        indicador, desde_s=-ventana_s, hasta_s=0.0, extremo=Extremo.MAXIMO, xp=xp
    )
    return Condicion(t_ms=ventana.t_ms, activa=ventana.v > 0, valido=ventana.valido)


def _combinar(
    condiciones: Mapping[RazonDeExclusion, Condicion], t_referencia_ms: Any, *, xp: Vectorial
) -> Condicion:
    """OR (Kleene) de todos los motivos calculables.

    Sin ningún motivo calculable, el resultado es «no se sabe» en toda la
    rejilla (mismo recurso que `segmentacion._cobertura`: `t != t` da el
    vector de `False` de la longitud correcta) y no «no excluir nada», que
    afirmaría justamente lo que no se pudo comprobar.
    """
    valores = list(condiciones.values())
    if not valores:
        vacio = t_referencia_ms != t_referencia_ms
        return Condicion(t_ms=t_referencia_ms, activa=vacio, valido=vacio)
    acumulada = valores[0]
    for condicion in valores[1:]:
        acumulada = acumulada.o(condicion, xp=xp)
    return acumulada


def excluir(
    series: Mapping[str, Serie],
    t_referencia_ms: Any,
    *,
    umbrales: UmbralesDeExclusion,
    roles_sin_confirmar: frozenset[str] = frozenset(),
    xp: Vectorial | None = None,
) -> InformeDeExclusion:
    """Calcula los cuatro motivos de exclusión de `docs/04` §4.6 sobre la
    rejilla de referencia `t_referencia_ms`.

    :param series: mapa de **rol semántico** a serie en unidad canónica, ya
        resuelto por `identidad.py`: este módulo no sabe de nombres de canal.
        Los roles que usa son `throttle_position` (TRANSITORIO y
        RETARDO_TRANSPORTE_LAMBDA), `cut_percentage` (CORTE) y
        `protection_level` (PROTECCION_MOTOR); cualquier otro se ignora.
    :param t_referencia_ms: la rejilla sobre la que se alinean las series y
        sobre la que se devuelve el informe -- típicamente la misma que
        `rpm`/`presion_map` de `malla.construir_malla`, para que la máscara se
        pueda aplicar directamente a `valor` antes de agregar. Este módulo no
        exige que sea la del régimen: a diferencia de la segmentación, ninguno
        de los cuatro motivos necesita `engine_speed`.
    :param roles_sin_confirmar: roles asignados por parecido y no confirmados
        por el usuario (`roles.Asignacion.requiere_confirmacion`, FG-09). Ver
        la cabecera del módulo, «Confianza del rol», para el porqué de mirarla
        aquí y no dejarlo a F4-05. Por omisión, un conjunto vacío: no
        desactiva nada si quien llama no lo pide.

    No lanza excepción por un log raro: un rol ausente o sin confirmar hace
    que su motivo aparezca en `InformeDeExclusion.no_aplicadas` en vez de
    participar en la máscara combinada.
    """
    xp = _xp(xp)
    condiciones: dict[RazonDeExclusion, Condicion] = {}
    no_aplicadas: list[FiltroNoAplicado] = []
    disparo_carga: Condicion | None = None  # TRANSITORIO y RETARDO comparten el disparo

    for razon in RazonDeExclusion:  # bucle sobre MOTIVOS, no sobre muestras
        ausentes = tuple(r for r in razon.roles_requeridos if r not in series)
        # Un rol ausente no está «sin confirmar»: no está. Contarlo en las dos
        # listas pediría confirmar un rol que no existe (mismo criterio que
        # `activacion_detectores.evaluar_activacion`).
        sin_confirmar = tuple(
            r for r in razon.roles_requeridos if r in roles_sin_confirmar and r not in ausentes
        )
        if ausentes or sin_confirmar:
            no_aplicadas.append(
                FiltroNoAplicado(
                    razon=razon, roles_ausentes=ausentes, roles_sin_confirmar=sin_confirmar
                )
            )
            continue

        if razon is RazonDeExclusion.CORTE:
            condiciones[razon] = _condicion_corte(
                series[ROL_CORTE], t_referencia_ms, umbrales, xp=xp
            )
        elif razon is RazonDeExclusion.PROTECCION_MOTOR:
            condiciones[razon] = _condicion_proteccion(
                series[ROL_PROTECCION], t_referencia_ms, umbrales, xp=xp
            )
        else:
            if disparo_carga is None:
                disparo_carga = _disparo_cambio_de_carga(
                    series[ROL_MARIPOSA], t_referencia_ms, umbrales, xp=xp
                )
            ventana_s = (
                umbrales.transitorio_ventana_s
                if razon is RazonDeExclusion.TRANSITORIO
                else umbrales.retardo_transporte_lambda_ms / MS_POR_S
            )
            condiciones[razon] = _sostener_tras_disparo(disparo_carga, ventana_s, xp=xp)

    combinada = _combinar(condiciones, t_referencia_ms, xp=xp)
    return InformeDeExclusion(
        t_ms=t_referencia_ms,
        por_razon=condiciones,
        no_aplicadas=tuple(no_aplicadas),
        excluir=combinada,
    )
