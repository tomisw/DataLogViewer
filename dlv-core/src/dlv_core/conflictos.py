"""Conflictos de unidad entre logs para el mismo rol (tarea F2-13).

Especificación: `docs/02-alcance-y-plan.md` §2.5 **E2.7** — «mismo rol con
unidades de origen distintas → ambos a canónica y se comparan; escala incoherente
→ aviso, nunca mezcla silenciosa» — con `docs/06-sistema-de-unidades.md` §6.5
(clases de magnitud), §6.6 (absoluto vs relativo) y §6.8 (`confianza`).

QUÉ DECIDE ESTE MÓDULO Y QUÉ NO
===============================
Recibe el MISMO rol ya emparejado entre varios logs (`identidad.py`, F2-02: aquí
no se vuelve a emparejar nada) y decide **si se pueden superponer y en qué
unidad**. No convierte series, no lee muestras y no elige la unidad de
presentación: eso es `unidades.desde_canonica` y `resolucion_unidad.py`
respectivamente. La cadena canal > perfil > usuario > fichero > canónica responde
«en qué unidad se PINTA»; este módulo responde algo anterior: «¿se puede pintar
junto?».

Toda la aritmética de conversión es de `unidades.py`. Aquí no hay ni un factor.

EL CASO NORMAL NO ES UN CONFLICTO
=================================
Dos logs del mismo rol con unidades de origen distintas —uno en °C y otro en °F—
**se comparan sin fricción y sin aviso**: los dos están en canónica (§6.11,
fila «Multi-log»). Es la razón de ser de la canónica, y avisar de ello sería
enseñar al usuario a ignorar los avisos, que es como se pierde el aviso que sí
importa.

Los casos que SÍ son conflicto se separan en dos familias, y la diferencia
importa porque la consecuencia es distinta:

1. **Un canal sin valor canónico utilizable** — no declara dimensión, la
   dimensión no está en el catálogo, su escala no está confirmada
   (`confianza = "unknown"`, §6.8) o es una presión relativa cuya referencia
   nadie ha resuelto. Ese canal **queda fuera** de la comparación y los demás
   siguen comparándose entre ellos: excluir a quien no tiene número canónico no
   es opinar sobre nadie. Si quedan menos de dos, no hay comparación.
2. **Una contradicción entre logs** — dimensiones distintas para el mismo rol, o
   escalas incoherentes. Ahí **no se compara nada**: no se elige por mayoría cuál
   de las declaraciones es la equivocada. Contar declaraciones sería decidir por
   popularidad qué es física, y ocultaría justo el error que hay que corregir
   (un rol mal asignado o un descriptor mal escrito).

QUÉ ES «ESCALA INCOHERENTE» Y POR QUÉ NO ES LO QUE PARECE
=========================================================
La tentación es comparar los factores: si el `to_canon` de un log y el del otro
difieren en un orden de magnitud, sospechar. **Ese criterio es inservible**, y es
la conclusión más importante de esta tarea:

    `to_canon` va del ENTERO CRUDO a la canónica, así que absorbe la escala de
    ALMACENAMIENTO, no solo la unidad física.

El Haltech guarda la temperatura en deciKelvin (`a = 0,1`, `docs/01` §1.8) y un
CSV genérico puede traerla en Kelvin flotantes (`a = 1,0`). Son un factor 10 de
diferencia y **las dos escalas son correctas**. Lo mismo pasa con la unidad
declarada: dos logs pueden declarar los dos «kPa» y tener factores distintos
—deciKPa contra kPa— sin que ninguno esté mal. Comparar factores, o comparar el
factor contra el que el catálogo da para la unidad declarada, produce falsos
positivos sobre datos perfectamente sanos.

Lo único que en estos metadatos expresa una MAGNITUD FÍSICA independiente de la
escala de almacenamiento es el **rango de presentación declarado** por el propio
fichero (`DisplayMaxMin` de `docs/01` §1.3, ya parseado en
`formatos/haltech.py:Canal.display_max/display_min`). Convertido a canónica, dice
«este canal vive entre −40 °C y 200 °C» sea deciKelvin o Kelvin lo que se guarde.
De ahí los dos criterios, los dos entre logs y ninguno con física cableada:

    (a) AMPLITUD: la razón entre la amplitud canónica mayor y la menor llega a un
        orden de magnitud (`RAZON_DE_AMPLITUD_MAXIMA`, configurable). Es el error
        de factor: kPa contra Pa mal declarado da 1000.
    (b) RANGO DISJUNTO: los rangos canónicos no se solapan en ningún punto. Es el
        error de desplazamiento: un canal en °C declarado como si fuera K deja su
        rango 273 K por debajo del del otro log, con la misma amplitud, así que
        (a) no lo ve y (b) sí.

Por qué el rango y no las muestras: este módulo decide sobre metadatos y no
recorre datos (ADR-009, más abajo). Un criterio sobre percentiles reales sería
más fino, pero exige tener las dos series ya cargadas y decodificadas con la
escala que precisamente se está poniendo en duda.

Los dos criterios exigen que al menos dos logs declaren rango. Cuando no lo
declaran —13 de los 475 canales del AutoLog no traen `DisplayMaxMin`— la escala
**no se puede comprobar** y `ResolucionDeRol.escala_comprobada` lo dice: es una
carencia de evidencia, no un certificado de coherencia, y callarla la convertiría
en lo segundo.

NUNCA MEZCLA SILENCIOSA
=======================
Invariante de este módulo, y lo que sus pruebas fijan:

    `Comparabilidad.COMPARABLE`   =>  no hay ningún aviso.
    cualquier otro resultado      =>  hay al menos un aviso que dice qué logs,
                                      qué rol y por qué.

`CON_RESERVA` es «se puede superponer, pero el usuario tiene que enterarse»: la
interfaz está obligada a marcarlo. Si algún día se pinta un `CON_RESERVA` como si
fuera un `COMPARABLE`, la mezcla vuelve a ser silenciosa aunque este módulo haya
hecho su trabajo; es la parte del contrato que no se puede garantizar desde aquí.

LA CLASE DE MAGNITUD, TAMBIÉN AQUÍ
==================================
Los extremos del rango son PUNTOS y su amplitud es un INTERVALO (§6.5). Si la
amplitud se convirtiera como punto, un canal declarado en °C (`b = 273,15`)
tendría una amplitud de 283 K en lugar de 10 K y el criterio (a) lo denunciaría
por incoherente cuando está perfectamente sano: la trampa del delta de
`tests/test_trampa_del_delta.py` (F1-20), en un sitio nuevo y con una
consecuencia nueva. Por eso aquí no se resta ni se multiplica a mano: se llama a
`Afin.desde_canonica` con la `Clase` correspondiente, explícita en cada llamada.

ADR-009
=======
Este módulo recorre **canales y logs**, no muestras: unas decenas de
declaraciones incluso con ocho logs abiertos, y de cada una solo sus metadatos
(dimensión, unidad de origen, escala, confianza, rango declarado). Los
diccionarios y los bucles de Python son lo correcto a esta escala. Lo que ADR-009
prohíbe es recorrer las 73 M de muestras, y aquí no se toca ni una: la conversión
que se hace es sobre dos números por canal —los extremos de su rango declarado—,
no sobre su serie.

Solo biblioteca estándar. En particular NO se importa `presion_referencia.py`
(que arrastra NumPy y necesita muestras para autodetectar): de la referencia de
presión aquí solo se necesita el número ya resuelto, y quien lo resuelve es esa
otra pieza.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from dlv_core.informes import Aviso
from dlv_core.unidades import Afin, Catalogo, Clase, Dimension, ErrorDeUnidad

__all__ = [
    "CONFIANZA_SIN_CONFIRMAR",
    "RAZON_DE_AMPLITUD_MAXIMA",
    "Comparabilidad",
    "DeclaracionDeCanal",
    "ErrorDeConflicto",
    "InformeDeConflictos",
    "Motivo",
    "OrigenDePresion",
    "RangoDeclarado",
    "ResolucionDeRol",
    "resolver_conflictos",
    "resolver_conflictos_de_rol",
]

#: Valor de `confianza` que marca una escala SIN confirmar (`docs/06` §6.8, y
#: `data/formats/*.toml`, donde el vocabulario es `confirmed` / `inferred` /
#: `unknown`). Solo este valor impide comparar: `inferred` es una escala deducida
#: cruzando `DisplayMaxMin` y plausibilidad física (`docs/01` §1.8), y
#: `formatos/haltech.py` ya la trata como usable —11 de los 34 tipos del AutoLog
#: lo son—. Tratar `inferred` como sospechosa aquí llenaría de avisos la
#: comparación normal y enseñaría a ignorarlos.
CONFIANZA_SIN_CONFIRMAR = "unknown"

#: Razón máxima admitida entre la amplitud canónica declarada mayor y la menor
#: del mismo rol antes de considerar la escala incoherente. Un orden de magnitud:
#: por debajo caben las diferencias legítimas de rango de presentación entre
#: fabricantes (un log de atmosférico 0–100 kPa contra uno de sobrealimentado
#: 0–400 kPa es un 4), y por encima está el error de factor que se busca (kPa
#: contra Pa da 1000; % contra fracción, 100).
#:
#: Es un valor POR OMISIÓN, no una constante: `resolver_conflictos_de_rol` lo
#: acepta por parámetro. Su sitio natural es `data/umbrales.toml` con la
#: precedencia de siempre (canal > perfil > usuario > fichero); no se añade en
#: esta tarea porque `data/` no se toca aquí, y el parámetro deja la puerta
#: abierta a que lo cargue quien llame.
RAZON_DE_AMPLITUD_MAXIMA = 10.0


class ErrorDeConflicto(ValueError):
    """Uso incorrecto de este módulo. No es un conflicto de datos.

    Un conflicto de datos sale por `Aviso`, porque el usuario tiene que poder
    seguir trabajando con los logs que sí se comparan. Esto otro —dos canales del
    mismo segmento en el mismo rol, un origen de presión declarado en una
    dimensión que no admite referencia— es un fallo de quien llama.
    """


class OrigenDePresion(Enum):
    """Origen de una presión declarado por el formato (`docs/06` §6.6).

    No es una unidad: es un cambio de origen, combinable con cualquier unidad de
    presión. Se declara aparte por eso, y `None` («el origen no se declara») es un
    estado distinto de los dos: en los logs analizados todas las presiones son
    absolutas, pero eso lo dice el descriptor del formato (`docs/01` §1.9), no el
    fichero, y un CSV genérico con una columna «Boost [bar]» no dice nada.
    """

    ABSOLUTA = "absoluta"
    RELATIVA = "relativa"


class Comparabilidad(Enum):
    """Qué se puede hacer con el rol una vez examinadas sus declaraciones."""

    COMPARABLE = "comparable"
    """Se superponen en la canónica de su dimensión. Sin nada que advertir."""

    CON_RESERVA = "con_reserva"
    """Se pueden superponer, pero hay algo que el usuario TIENE que saber: un log
    que se ha quedado fuera, una referencia de presión que no venía en el fichero,
    un origen que nadie declara. Lleva siempre aviso, y la interfaz está obligada
    a marcarlo: es la mitad del «nunca mezcla silenciosa» que no depende de este
    módulo."""

    NO_COMPARABLE = "no_comparable"
    """No se superpone nada. O las declaraciones se contradicen y elegir sería
    inventar, o no quedan dos canales con valor canónico."""

    NADA_QUE_COMPARAR = "nada_que_comparar"
    """Menos de dos logs declaran el rol. No es un conflicto: es el hueco normal
    de §3.6 —un log de 25 canales y otro de 475 no traen lo mismo— y lo resuelve
    `identidad.GrupoDeCanales.ausentes`, no este módulo. No genera aviso."""


class Motivo(Enum):
    """Por qué un canal queda fuera o un rol no se puede comparar.

    El valor de cada miembro es el `codigo` del `Aviso` que lo acompaña, para que
    el informe de importación y este enum no puedan desincronizarse.
    """

    SIN_DIMENSION = "canal_sin_dimension"
    """El origen no dice de qué magnitud es: se muestra en crudo, sin unidad
    (mitigación de R1), y en crudo no hay nada que comparar entre logs."""

    DIMENSION_DESCONOCIDA = "dimension_desconocida"
    """La dimensión declarada no está en `data/units.toml`: sin catálogo no hay
    unidad canónica a la que llevar el canal."""

    ESCALA_SIN_CONFIRMAR = "escala_sin_confirmar"
    """`confianza = "unknown"` (§6.8): el canal se muestra en crudo y con el
    selector de unidad desactivado, así que no tiene valor canónico que comparar.
    Compararlo sería apilar una duda sobre otra."""

    UNIDAD_DE_ORIGEN_AJENA = "unidad_de_origen_ajena_a_la_dimension"
    """La unidad de origen declarada no pertenece a la dimensión declarada. Las
    dos declaraciones no pueden ser ciertas a la vez y no se puede saber cuál
    corregir."""

    PRESION_RELATIVA_SIN_REFERENCIA = "presion_relativa_sin_referencia"
    """Presión relativa sin referencia resuelta: la canónica es kPa ABSOLUTOS
    (§6.6), así que sin el origen este canal todavía no está en canónica."""

    DIMENSIONES_DISTINTAS = "rol_con_dimensiones_distintas"
    """El mismo rol declarado con dimensiones distintas por logs distintos. No se
    resuelve convirtiendo: no hay conversión entre presión y temperatura."""

    AMPLITUD_INCOHERENTE = "escala_incoherente_amplitud"
    """Criterio (a): las amplitudes canónicas declaradas difieren en un orden de
    magnitud o más."""

    RANGOS_DISJUNTOS = "escala_incoherente_rangos_disjuntos"
    """Criterio (b): los rangos canónicos declarados no se solapan en ningún
    punto."""

    REFERENCIA_DE_PRESION_APLICADA = "presion_llevada_a_absoluta"
    """Se compara sumando una referencia que no venía en el log. El resultado
    hereda el error de esa referencia (`presion_referencia.ReferenciaPresion`
    marca si es estimada)."""

    ORIGEN_DE_PRESION_SIN_DECLARAR = "origen_de_presion_sin_declarar"
    """Alguna presión no dice si es absoluta o relativa. «2 bar» sin más es la
    fuente de error más común al comparar dos herramientas (§6.6)."""


@dataclass(slots=True, frozen=True)
class RangoDeclarado:
    """Rango de presentación declarado por el fichero, en unidades CRUDAS.

    Es `DisplayMaxMin` de `docs/01` §1.3 (`4731,2331` para la temperatura, es
    decir 200 °C / −40 °C en deciKelvin): números en el mismo dominio que las
    muestras almacenadas, no en canónica. Se pasa tal cual y lo convierte este
    módulo con la escala del canal, que es justo lo que se está poniendo a prueba.
    """

    minimo: float
    maximo: float

    def __post_init__(self) -> None:
        if self.maximo < self.minimo:
            raise ErrorDeConflicto(
                f"rango declarado al revés (mínimo {self.minimo}, máximo {self.maximo}); "
                "`DisplayMaxMin` viene como «max,min» y hay que repartirlo antes"
            )

    def en_canonica(self, escala: Afin) -> tuple[float, float]:
        """Los dos extremos en canónica, ordenados.

        Los extremos son PUNTOS: se les aplica la escala completa, con su `b`.
        Se ordenan después porque una escala con `a < 0` —un sensor invertido—
        intercambia mínimo y máximo, y el resto del módulo compara intervalos.
        """
        lo = float(escala.desde_canonica(self.minimo, Clase.PUNTO))
        hi = float(escala.desde_canonica(self.maximo, Clase.PUNTO))
        return (lo, hi) if lo <= hi else (hi, lo)

    def amplitud_canonica(self, escala: Afin) -> float:
        """La amplitud en canónica. Es un INTERVALO, no un punto.

        Aquí está la trampa del delta (§6.5): con la clase PUNTO, la amplitud de
        un canal declarado en °C saldría desplazada 273,15 K y el criterio de
        coherencia denunciaría un canal sano. Se llama a `Afin.desde_canonica`
        con `Clase.INTERVALO`, que es la que se queda solo con la parte lineal.
        """
        return abs(float(escala.desde_canonica(self.maximo - self.minimo, Clase.INTERVALO)))


@dataclass(slots=True, frozen=True)
class DeclaracionDeCanal:
    """Lo que UN log declara sobre el canal de un rol. Solo metadatos.

    Son los campos que ya produce la ingesta: `formatos/haltech.py:Canal` da
    `dimension`, `a_canonica`, `confianza` y `display_max/display_min`;
    `almacen.ChannelSeries.to_canon` y `cache.to_canon_a/b` dan la escala como
    `Afin`; `formatos/unidades_declaradas.py` da la unidad de origen del CSV
    genérico. Nada de esto se recalcula aquí.
    """

    id_segmento: str
    """El log (o segmento) del que viene, en el mismo espacio de nombres que
    `identidad.CanalDeLog.id_segmento`."""

    id_canal: str
    dimension: str | None
    """Id de dimensión de `data/units.toml`. `None` = el origen no la declara y
    el canal se muestra en crudo."""

    escala: Afin
    """Entero crudo -> canónica (`ChannelSeries.to_canon`). Se aplica llamando a
    `desde_canonica`, que es cómo la usa el resto del código (ver
    `dlv_api/exportacion.py`): el nombre del método describe la dirección
    canónica -> mostrada del catálogo, y esta conversión es la del origen, pero la
    aritmética `a·x + b` y —lo que importa— el tratamiento de la `Clase` son los
    mismos, y no hay una segunda implementación que pueda divergir.

    Se exige `Afin` a propósito: en este proyecto la escala de origen es siempre
    afín (`to_canon: Afin` en el almacén y en la caché). Un formato que guardara
    mpg o un periodo —recíprocos de la canónica— obligaría a revisar este módulo
    en lugar de colarse por una conversión que no es lineal."""

    confianza: str
    """`confirmed` / `inferred` / `unknown` de `data/formats/*.toml` (§6.8). Ver
    `CONFIANZA_SIN_CONFIRMAR`."""

    unidad_origen: str | None = None
    """Id o alias de la unidad física en que el origen expresa el canal, si la
    declara. No determina la escala —el almacenamiento puede estar escalado por
    10 o por 1000 sobre esa unidad— y por eso no se usa para juzgarla: sirve para
    que el aviso diga «uno en °C y otro en °F» y para detectar que la unidad
    declarada no pertenece a la dimensión declarada."""

    rango_declarado: RangoDeclarado | None = None
    """`DisplayMaxMin` (§1.3) si el fichero lo trae. Es la única evidencia de
    magnitud física que hay en estos metadatos; sin él la escala no se puede
    comprobar."""

    origen_presion: OrigenDePresion | None = None
    """Solo para dimensiones con `admite_referencia`. `None` = el origen no lo
    declara."""

    referencia_kpa: float | None = None
    """Referencia ya resuelta (por `presion_referencia.resolver_referencia`, que
    no se llama desde aquí) que hay que SUMAR en canónica para llevar este canal
    de relativo a absoluto. Solo tiene sentido con `origen_presion` relativo."""

    @property
    def escala_confirmada(self) -> bool:
        return self.confianza != CONFIANZA_SIN_CONFIRMAR


@dataclass(slots=True, frozen=True)
class ResolucionDeRol:
    """Qué se puede hacer con un rol y por qué."""

    id_rol: str
    """Identidad del grupo, tal como la da `identidad.GrupoDeCanales.id`
    (`rol:coolant_temp`, `rol:knock_count#2`, `manual:Mi pareja`)."""

    comparabilidad: Comparabilidad
    segmentos: tuple[str, ...]
    """Todos los logs que declaran el rol, ordenados."""

    comparables: tuple[str, ...]
    """Los logs que se pueden superponer en `unidad_canonica`. Vacío cuando no hay
    comparación posible: nunca se ofrece media comparación."""

    excluidos: Mapping[str, Motivo]
    """`id_segmento -> por qué se queda fuera`. Un motivo por canal, el primero
    que aplica."""

    motivos: tuple[Motivo, ...]
    """Motivos del rol entero (contradicciones y reservas), en orden de
    detección. Los de exclusión de un canal concreto están en `excluidos`."""

    avisos: tuple[Aviso, ...]
    dimension: str | None = None
    """La dimensión común, si hay una. `None` si los logs no se ponen de acuerdo o
    si ninguno la declara."""

    unidad_canonica: str | None = None
    """La unidad en la que se comparan: la canónica de `dimension`, que no es
    configurable (§6.3 regla 1). Es la respuesta literal a E2.7."""

    unidades_de_origen: tuple[str, ...] = ()
    """Las unidades de origen distintas que declaran los logs comparables, ya
    normalizadas (los alias resueltos), ordenadas. Más de una es el caso normal de
    E2.7, no un problema: es lo que la interfaz puede mostrar como «se comparan °C
    y °F en K»."""

    referencias_kpa: Mapping[str, float] = field(default_factory=dict)
    """`id_segmento -> kPa que hay que sumar` para llevar ese log de presión
    relativa a la canónica absoluta. Se suma **solo a los valores de
    `Clase.PUNTO`** (§6.6): un Δ de 50 kPa vale lo mismo en absoluto que en
    relativo. `unidades.a_canonica(..., referencia_kpa=...)` ya lo hace así."""

    escala_comprobada: bool = False
    """`True` si había rango declarado en al menos dos logs comparables y por
    tanto la coherencia de escala se pudo comprobar de verdad. `False` significa
    «no se sabe», no «está bien»."""

    @property
    def hay_conflicto(self) -> bool:
        """`True` si algo impide la comparación limpia y hay que decirlo."""
        return self.comparabilidad in (Comparabilidad.CON_RESERVA, Comparabilidad.NO_COMPARABLE)


@dataclass(slots=True, frozen=True)
class InformeDeConflictos:
    """El resultado para todos los roles examinados."""

    resoluciones: tuple[ResolucionDeRol, ...]

    def por_rol(self, id_rol: str) -> ResolucionDeRol:
        for r in self.resoluciones:
            if r.id_rol == id_rol:
                return r
        raise ErrorDeConflicto(f"no se ha examinado ningún rol con id '{id_rol}'")

    @property
    def avisos(self) -> tuple[Aviso, ...]:
        """Todos los avisos, en el orden de los roles: va al informe (E1.7)."""
        return tuple(a for r in self.resoluciones for a in r.avisos)

    @property
    def comparables(self) -> tuple[ResolucionDeRol, ...]:
        """Los roles que se pueden superponer, con o sin reserva. Es la lista que
        la vista paralela puede ofrecer; los demás hay que resolverlos antes."""
        return tuple(
            r
            for r in self.resoluciones
            if r.comparabilidad in (Comparabilidad.COMPARABLE, Comparabilidad.CON_RESERVA)
        )

    @property
    def en_conflicto(self) -> tuple[ResolucionDeRol, ...]:
        return tuple(
            r for r in self.resoluciones if r.comparabilidad is Comparabilidad.NO_COMPARABLE
        )


# --------------------------------------------------------------------------- #
# Acumulador
# --------------------------------------------------------------------------- #
class _Acumulador:
    """Avisos y motivos de un rol, para que ninguno se decida sin quedar escrito.

    Que el `codigo` del aviso salga siempre de `Motivo.value` es lo que impide
    que un motivo nuevo llegue al informe con un código inventado a mano.
    """

    __slots__ = ("avisos", "excluidos", "motivos")

    def __init__(self) -> None:
        self.avisos: list[Aviso] = []
        self.motivos: list[Motivo] = []
        self.excluidos: dict[str, Motivo] = {}

    def avisa(self, motivo: Motivo, mensaje: str) -> None:
        self.avisos.append(Aviso(motivo.value, mensaje))

    def del_rol(self, motivo: Motivo, mensaje: str) -> None:
        self.motivos.append(motivo)
        self.avisa(motivo, mensaje)

    def excluye(self, id_segmento: str, motivo: Motivo, mensaje: str) -> None:
        self.excluidos[id_segmento] = motivo
        self.avisa(motivo, mensaje)


# --------------------------------------------------------------------------- #
# Un rol
# --------------------------------------------------------------------------- #
def resolver_conflictos_de_rol(
    id_rol: str,
    declaraciones: Sequence[DeclaracionDeCanal],
    *,
    catalogo: Catalogo,
    razon_de_amplitud_maxima: float = RAZON_DE_AMPLITUD_MAXIMA,
) -> ResolucionDeRol:
    """Decide si el mismo rol se puede comparar entre logs, y en qué unidad.

    `declaraciones` son los canales YA emparejados por `identidad.emparejar`
    (F2-02), uno por log: aquí no se vuelve a emparejar nada. Con menos de dos, el
    resultado es `NADA_QUE_COMPARAR` sin aviso, porque un rol que solo existe en
    un log es un hueco de §3.6 y no un conflicto.

    Lanza `ErrorDeConflicto` si dos declaraciones vienen del mismo segmento —el
    invariante «un canal por segmento y por grupo» lo garantiza `identidad.py`— o
    si se declara un origen de presión en una dimensión que no admite referencia,
    que es el mismo error que rechaza `unidades.desde_canonica`.
    """
    decls = sorted(declaraciones, key=lambda d: (d.id_segmento, d.id_canal))
    _comprobar_entrada(decls, catalogo)
    segmentos = tuple(d.id_segmento for d in decls)

    if len(decls) < 2:
        return ResolucionDeRol(
            id_rol=id_rol,
            comparabilidad=Comparabilidad.NADA_QUE_COMPARAR,
            segmentos=segmentos,
            comparables=(),
            excluidos={},
            motivos=(),
            avisos=(),
            dimension=decls[0].dimension if decls else None,
        )

    ac = _Acumulador()
    activos = _descartar_las_que_no_tienen_canonica(id_rol, decls, catalogo, ac)

    dimensiones = sorted({d.dimension for d in activos if d.dimension is not None})
    if len(dimensiones) > 1:
        _avisar_de_las_dimensiones(id_rol, activos, dimensiones, ac)
        return _sin_comparacion(id_rol, segmentos, ac)

    if len(activos) < 2:
        # Los avisos de exclusión ya están puestos: no hace falta uno nuevo que
        # repita en abstracto lo que cada uno de ellos ya dijo con nombres.
        return _sin_comparacion(id_rol, segmentos, ac, dimension=_una(dimensiones))

    dimension = catalogo.dimension(dimensiones[0])
    referencias = _resolver_origenes_de_presion(id_rol, activos, dimension, ac)
    activos = [d for d in activos if d.id_segmento not in ac.excluidos]
    if len(activos) < 2:
        return _sin_comparacion(id_rol, segmentos, ac, dimension=dimension.id)

    comprobada = _comprobar_coherencia_de_escala(
        id_rol, activos, dimension, referencias, razon_de_amplitud_maxima, ac
    )
    if any(m in (Motivo.AMPLITUD_INCOHERENTE, Motivo.RANGOS_DISJUNTOS) for m in ac.motivos):
        return _sin_comparacion(
            id_rol, segmentos, ac, dimension=dimension.id, escala_comprobada=comprobada
        )

    comparabilidad = Comparabilidad.COMPARABLE if not ac.avisos else Comparabilidad.CON_RESERVA
    return ResolucionDeRol(
        id_rol=id_rol,
        comparabilidad=comparabilidad,
        segmentos=segmentos,
        comparables=tuple(d.id_segmento for d in activos),
        excluidos=dict(ac.excluidos),
        motivos=tuple(ac.motivos),
        avisos=tuple(ac.avisos),
        dimension=dimension.id,
        unidad_canonica=str(dimension.unidad_canonica),
        unidades_de_origen=_unidades_de_origen(activos, dimension),
        referencias_kpa={s: k for s, k in referencias.items() if s not in ac.excluidos},
        escala_comprobada=comprobada,
    )


def resolver_conflictos(
    declaraciones_por_rol: Mapping[str, Sequence[DeclaracionDeCanal]],
    *,
    catalogo: Catalogo,
    razon_de_amplitud_maxima: float = RAZON_DE_AMPLITUD_MAXIMA,
) -> InformeDeConflictos:
    """`resolver_conflictos_de_rol` para todos los roles emparejados.

    La clave del mapa es la identidad del grupo de `identidad.py`, así que la
    llamada típica desde la vista paralela es:

        resolver_conflictos(
            {g.id: [declaracion_de(c) for c in g.miembros.values()]
             for g in emparejamiento.comunes},
            catalogo=catalogo,
        )

    Los roles se recorren en orden para que el informe sea reproducible: dos
    ejecuciones sobre los mismos logs tienen que dar los mismos avisos en el mismo
    orden, o el informe de importación no se puede comparar entre versiones.
    """
    return InformeDeConflictos(
        resoluciones=tuple(
            resolver_conflictos_de_rol(
                id_rol,
                declaraciones_por_rol[id_rol],
                catalogo=catalogo,
                razon_de_amplitud_maxima=razon_de_amplitud_maxima,
            )
            for id_rol in sorted(declaraciones_por_rol)
        )
    )


# --------------------------------------------------------------------------- #
# Pasos
# --------------------------------------------------------------------------- #
def _una(dimensiones: Sequence[str]) -> str | None:
    return dimensiones[0] if len(dimensiones) == 1 else None


def _comprobar_entrada(decls: Sequence[DeclaracionDeCanal], catalogo: Catalogo) -> None:
    """Lo que es error de quien llama y no conflicto de datos."""
    vistos: set[str] = set()
    for d in decls:
        if d.id_segmento in vistos:
            raise ErrorDeConflicto(
                f"el segmento '{d.id_segmento}' aporta dos canales al mismo rol; "
                "`identidad.emparejar` garantiza uno por segmento y por grupo, así que "
                "esto es un error de quien construye las declaraciones"
            )
        vistos.add(d.id_segmento)

        if d.origen_presion is None:
            continue
        if d.dimension is None:
            raise ErrorDeConflicto(
                f"el canal '{d.id_canal}' del segmento '{d.id_segmento}' declara origen de "
                "presión sin declarar dimensión"
            )
        try:
            admite = bool(catalogo.dimension(d.dimension).admite_referencia)
        except ErrorDeUnidad:
            # Dimensión desconocida: se trata como conflicto de datos más
            # adelante, con su aviso. No es un error de uso.
            continue
        if not admite:
            raise ErrorDeConflicto(
                f"el canal '{d.id_canal}' del segmento '{d.id_segmento}' declara un origen de "
                f"presión, pero la dimensión '{d.dimension}' no admite referencia de origen; "
                "solo la presión la admite (docs/06 §6.6)"
            )


def _descartar_las_que_no_tienen_canonica(
    id_rol: str,
    decls: Sequence[DeclaracionDeCanal],
    catalogo: Catalogo,
    ac: _Acumulador,
) -> list[DeclaracionDeCanal]:
    """Aparta los canales sin valor canónico utilizable, uno a uno y con aviso.

    Excluir aquí no es opinar sobre quién está equivocado: un canal que se muestra
    en crudo no tiene número canónico, así que no hay nada que superponer con él.
    Los demás siguen comparándose entre ellos, que es lo útil para el usuario.
    """
    activos: list[DeclaracionDeCanal] = []
    for d in decls:
        donde = f"el canal '{d.id_canal}' del log '{d.id_segmento}'"

        if d.dimension is None:
            ac.excluye(
                d.id_segmento,
                Motivo.SIN_DIMENSION,
                f"{donde} no declara dimensión para el rol '{id_rol}': se muestra en crudo, "
                "sin unidad, y en crudo no se puede comparar con otro log. Queda fuera de "
                "la comparación",
            )
            continue

        try:
            catalogo.dimension(d.dimension)
        except ErrorDeUnidad:
            ac.excluye(
                d.id_segmento,
                Motivo.DIMENSION_DESCONOCIDA,
                f"{donde} declara la dimensión '{d.dimension}', que no está en el catálogo "
                f"de unidades: sin ella no hay unidad canónica a la que llevar el rol "
                f"'{id_rol}'. Queda fuera de la comparación",
            )
            continue

        if not d.escala_confirmada:
            ac.excluye(
                d.id_segmento,
                Motivo.ESCALA_SIN_CONFIRMAR,
                f"{donde} tiene la escala sin confirmar (confianza "
                f"'{d.confianza}', docs/06 §6.8): se muestra en crudo y con el selector de "
                f"unidad desactivado, así que no hay valor canónico que comparar en el rol "
                f"'{id_rol}'. Compararlo apilaría una duda sobre otra; queda fuera. Para "
                "incluirlo hay que confirmar la escala en el descriptor del formato, no "
                "suponerla aquí",
            )
            continue

        if not _unidad_de_origen_coherente(d, catalogo):
            ac.excluye(
                d.id_segmento,
                Motivo.UNIDAD_DE_ORIGEN_AJENA,
                f"{donde} declara la unidad de origen '{d.unidad_origen}', que no pertenece "
                f"a la dimensión '{d.dimension}' que declara el mismo canal. Las dos cosas "
                "no pueden ser ciertas y no se puede saber cuál corregir: queda fuera de la "
                f"comparación del rol '{id_rol}'",
            )
            continue

        activos.append(d)
    return activos


def _unidad_de_origen_coherente(d: DeclaracionDeCanal, catalogo: Catalogo) -> bool:
    if d.unidad_origen is None or d.dimension is None:
        return True
    try:
        catalogo.dimension(d.dimension).unidad(d.unidad_origen)
    except ErrorDeUnidad:
        return False
    return True


def _avisar_de_las_dimensiones(
    id_rol: str,
    activos: Sequence[DeclaracionDeCanal],
    dimensiones: Sequence[str],
    ac: _Acumulador,
) -> None:
    """El conflicto que no se resuelve convirtiendo.

    No se elige por mayoría: con cinco logs en `pressure` y uno en `temperature`,
    quedarse con los cinco sería decidir por popularidad qué mide el rol y
    esconder el error de verdad —un rol mal asignado o un descriptor mal escrito—.
    El aviso da los nombres para que se pueda corregir en el sitio correcto, o
    rehacer el emparejamiento a mano (§7.11 capa MANUAL).
    """
    por_dimension: dict[str, list[str]] = {}
    for d in activos:
        if d.dimension is not None:
            por_dimension.setdefault(d.dimension, []).append(d.id_segmento)
    detalle = "; ".join(
        f"'{dim}' en {', '.join(repr(s) for s in sorted(por_dimension[dim]))}"
        for dim in dimensiones
    )
    ac.del_rol(
        Motivo.DIMENSIONES_DISTINTAS,
        f"el rol '{id_rol}' se declara con dimensiones distintas según el log ({detalle}). "
        "No es un problema de unidad y no se resuelve convirtiendo: no hay conversión entre "
        "dos magnitudes distintas. No se superpone nada. Revisa la asignación de rol o el "
        "descriptor del formato del log discrepante, o empareja a mano lo que de verdad sea "
        "el mismo canal",
    )


def _resolver_origenes_de_presion(
    id_rol: str,
    activos: Sequence[DeclaracionDeCanal],
    dimension: Dimension,
    ac: _Acumulador,
) -> dict[str, float]:
    """Absoluto contra relativo: cambio de ORIGEN, no de unidad (§6.6).

    La canónica de la presión es kPa **absolutos**, así que un canal relativo no
    está en canónica hasta que se le suma su referencia. Con la referencia ya
    resuelta (`presion_referencia.resolver_referencia`, que necesita muestras y no
    se llama desde aquí) se puede comparar, y se avisa porque la comparación pasa
    a depender de un número que no venía en el fichero. Sin ella, el canal no
    tiene valor canónico y se queda fuera, igual que uno con la escala sin
    confirmar: no se inventa una referencia plausible.
    """
    if not dimension.admite_referencia:
        return {}

    referencias: dict[str, float] = {}
    relativas: list[str] = []
    for d in activos:
        if d.origen_presion is not OrigenDePresion.RELATIVA:
            continue
        if d.referencia_kpa is None:
            ac.excluye(
                d.id_segmento,
                Motivo.PRESION_RELATIVA_SIN_REFERENCIA,
                f"el canal '{d.id_canal}' del log '{d.id_segmento}' declara presión RELATIVA "
                f"y no trae referencia resuelta, mientras el rol '{id_rol}' se compara en "
                "kPa absolutos (docs/06 §6.6): absoluto contra relativo no es un cambio de "
                "unidad, es un cambio de origen, y sin la referencia no hay valor canónico. "
                "Queda fuera. Resuélvela en el perfil del vehículo o con "
                "`presion_referencia.resolver_referencia`; no se supone ninguna aquí",
            )
            continue
        referencias[d.id_segmento] = d.referencia_kpa
        relativas.append(d.id_segmento)

    if relativas:
        ac.del_rol(
            Motivo.REFERENCIA_DE_PRESION_APLICADA,
            f"en el rol '{id_rol}' hay presiones relativas "
            f"({', '.join(repr(s) for s in sorted(relativas))}) "
            "que se llevan a la canónica absoluta sumando su referencia "
            f"({', '.join(f'{referencias[s]:g} kPa en {s!r}' for s in sorted(relativas))}). "
            "La referencia no viene en el log: si es estimada, la comparación hereda su "
            "error (docs/01 §1.9). Se suma solo a los valores absolutos, nunca a un Δ",
        )

    sin_declarar = sorted(d.id_segmento for d in activos if d.origen_presion is None)
    declarados = [d for d in activos if d.origen_presion is not None]
    if sin_declarar and len(sin_declarar) < len(activos):
        conocidos = ", ".join(
            f"{d.id_segmento!r} ({d.origen_presion.value})"
            for d in sorted(declarados, key=lambda d: d.id_segmento)
            if d.origen_presion is not None
        )
        ac.del_rol(
            Motivo.ORIGEN_DE_PRESION_SIN_DECLARAR,
            f"en el rol '{id_rol}', {', '.join(repr(s) for s in sin_declarar)} no declara si su "
            f"presión es absoluta o relativa, y {conocidos} sí. Se compara como está, pero si el "
            "que no "
            "lo declara viniera en relativo la diferencia sería de unos 101 kPa —un boost de "
            "1 bar— sin que nada en la pantalla lo delate (docs/06 §6.6)",
        )
    elif sin_declarar:
        ac.del_rol(
            Motivo.ORIGEN_DE_PRESION_SIN_DECLARAR,
            f"ningún log declara si la presión del rol '{id_rol}' es absoluta o relativa "
            f"({', '.join(repr(s) for s in sin_declarar)}). Se comparan como absolutas, que es "
            "lo que asume la "
            "canónica, pero la etiqueta del eje no puede afirmar «abs» ni «rel»: «2 bar» sin "
            "más es la fuente de error más común al comparar dos herramientas (docs/06 §6.6)",
        )

    return referencias


def _comprobar_coherencia_de_escala(
    id_rol: str,
    activos: Sequence[DeclaracionDeCanal],
    dimension: Dimension,
    referencias: Mapping[str, float],
    razon_maxima: float,
    ac: _Acumulador,
) -> bool:
    """Los dos criterios sobre el rango declarado. Devuelve si se pudo comprobar.

    Ver «qué es escala incoherente» en la cabecera del módulo: los factores no se
    comparan entre sí porque `to_canon` absorbe la escala de almacenamiento y una
    diferencia de mil entre dos factores puede ser perfectamente correcta.

    A los rangos de los canales relativos se les suma su referencia antes de
    comparar: si no, un log en presión de boost (0–200 kPa relativos) y otro
    absoluto se verían desplazados 101 kPa por una razón que ya está resuelta, y
    el criterio (b) los denunciaría por un motivo falso.
    """
    con_rango = [d for d in activos if d.rango_declarado is not None]
    canonicos: dict[str, tuple[float, float]] = {}
    amplitudes: dict[str, float] = {}
    for d in con_rango:
        rango = d.rango_declarado
        if rango is None:  # pragma: no cover - lo garantiza el filtro de arriba
            continue
        lo, hi = rango.en_canonica(d.escala)
        ref = referencias.get(d.id_segmento, 0.0)
        canonicos[d.id_segmento] = (lo + ref, hi + ref)
        amplitud = rango.amplitud_canonica(d.escala)
        if amplitud > 0.0:
            amplitudes[d.id_segmento] = amplitud

    if len(canonicos) < 2:
        # Sin dos rangos declarados no hay nada que cruzar. No se avisa —13 de los
        # 475 canales del AutoLog no traen `DisplayMaxMin` y avisar de todos ellos
        # sería ruido—, pero `escala_comprobada=False` deja dicho que la coherencia
        # no está comprobada, que no es lo mismo que estar bien.
        return False

    etiqueta = str(dimension.unidad_canonica)
    if len(amplitudes) >= 2:
        menor = min(amplitudes, key=lambda s: amplitudes[s])
        mayor = max(amplitudes, key=lambda s: amplitudes[s])
        razon = amplitudes[mayor] / amplitudes[menor]
        if razon >= razon_maxima:
            ac.del_rol(
                Motivo.AMPLITUD_INCOHERENTE,
                f"el rol '{id_rol}' tiene escalas incoherentes entre logs: el rango que "
                f"declara '{mayor}' abarca {amplitudes[mayor]:g} {etiqueta} y el de "
                f"'{menor}' {amplitudes[menor]:g} {etiqueta}, una razón de {razon:g} "
                f"(máxima admitida {razon_maxima:g}). Una diferencia de este tamaño en la "
                "magnitud declarada apunta a un factor mal puesto —kPa contra Pa, "
                "porcentaje contra fracción— y no a dos rangos de presentación distintos. "
                "No se superpone: dos curvas con un factor de por medio parecen "
                "comparables y no lo son. Revisa la escala a canónica de los dos canales",
            )
            return True

    pares = sorted(canonicos)
    for i, sa in enumerate(pares):
        lo_a, hi_a = canonicos[sa]
        for sb in pares[i + 1 :]:
            lo_b, hi_b = canonicos[sb]
            if hi_a < lo_b or hi_b < lo_a:
                ac.del_rol(
                    Motivo.RANGOS_DISJUNTOS,
                    f"el rol '{id_rol}' declara rangos que no se solapan en ningún punto: "
                    f"'{sa}' entre {lo_a:g} y {hi_a:g} {etiqueta}, '{sb}' entre {lo_b:g} y "
                    f"{hi_b:g} {etiqueta}. Dos logs del mismo canal no pueden vivir en "
                    "tramos ajenos de la misma magnitud: apunta a un desplazamiento de "
                    "origen mal declarado (°C tomado por K son 273 K de diferencia con la "
                    "misma amplitud) o a un rol mal asignado. No se superpone",
                )
                return True

    return True


def _unidades_de_origen(
    activos: Sequence[DeclaracionDeCanal], dimension: Dimension
) -> tuple[str, ...]:
    """Las unidades de origen distintas, con los alias ya resueltos.

    Más de una es el caso normal de E2.7 y no lleva aviso. Se normalizan contra el
    catálogo para que «mbar» y «hPa» no se cuenten como dos unidades distintas y
    la interfaz no anuncie una diferencia que no existe.
    """
    ids: set[str] = set()
    for d in activos:
        if d.unidad_origen is None:
            continue
        ids.add(str(dimension.unidad(d.unidad_origen).id))
    return tuple(sorted(ids))


def _sin_comparacion(
    id_rol: str,
    segmentos: tuple[str, ...],
    ac: _Acumulador,
    *,
    dimension: str | None = None,
    escala_comprobada: bool = False,
) -> ResolucionDeRol:
    """`NO_COMPARABLE`: `comparables` vacío, nunca media comparación.

    `unidad_canonica` se queda en `None` a propósito: no hay ninguna unidad en la
    que se comparen estos logs, y rellenarla invitaría a superponerlos igual.
    """
    return ResolucionDeRol(
        id_rol=id_rol,
        comparabilidad=Comparabilidad.NO_COMPARABLE,
        segmentos=segmentos,
        comparables=(),
        excluidos=dict(ac.excluidos),
        motivos=tuple(ac.motivos),
        avisos=tuple(ac.avisos),
        dimension=dimension,
        escala_comprobada=escala_comprobada,
    )
