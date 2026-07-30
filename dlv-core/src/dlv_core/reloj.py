"""Reconciliación de reloj (tarea F1-04).

Especificación: `docs/01-formato-log.md` §1.4, §1.5 y la lista de verificación de
§1.13. Este módulo produce el `t0_absoluto` y la `fiabilidad_reloj` que consume
el motor de tiempo multi-log (`tiempo.py`, §3.6).

TRES PROBLEMAS QUE SE PARECEN Y NO SON EL MISMO
===============================================
Los tres logs reales de `samples/real/` traen tres averías de reloj distintas, y
la trampa está en que la más grave es la que *aparenta* estar bien.

1. **Hora de cabecera en 12 h** (§1.4). `AutoLog` declara `Log : 20260729
   06:30:35` y su primera fila es `18:30:35.506`: la cabecera va en 12 h sin
   AM/PM y las filas en 24 h. La fecha es fiable, la hora no.

       Regla: la fecha se toma de la cabecera, la hora del día se toma SIEMPRE
       de la primera fila, y la hora de la cabecera solo sirve para validar que
       el desfase es 0 o 12 h. Si no lo es, el reloj no es fiable y se degrada a
       modo relativo.

2. **Época ficticia** (§1.5). `Log2768` y `Log2769` declaran los dos
   `Log : 19800101 01:01:01` y empiezan los dos en `01:01:01.005`. La ECU no
   tiene reloj de tiempo real: **no existe tiempo absoluto**.

       Y aquí está la trampa: 01:01:01 contra 01:01:01.005 da un desfase de
       0,005 s, así que la comprobación de 12 h del punto 1 PASA. Si se
       comprobara solo eso, los dos logs quedarían marcados como fiables, se
       superpondrían en el instante 1980-01-01 01:01:01 y el usuario vería dos
       tiradas distintas como si fueran simultáneas. Por eso la época se
       comprueba ANTES y por separado: no es un desfase mal medido, es la
       ausencia de la magnitud.

       Con época ficticia el orden lo da `Log Number` (2768 → 2769) y el desfase
       entre segmentos es DESCONOCIDO, luego editable por el usuario. Nunca se
       finge continuidad. `DownloadDateTime` no sirve para ordenar: en estos dos
       ficheros está invertido respecto al número de log.

3. **Cruce de medianoche** (§1.13). Las marcas de fila son `HH:MM:SS.mmm` sin
   fecha, así que un log que pasa de `23:59:59.950` a `00:00:00.003` retrocede
   casi 24 h. Sin desenrollar, el eje X va hacia atrás y todo lo que dependa del
   orden temporal —pirámide, detectores, cursor— da resultados absurdos.

       Se distingue del ruido por la magnitud: un retroceso de más de 12 h es un
       cruce de medianoche; uno pequeño es una marca no monótona, que se cuenta
       y se avisa, pero no se «arregla» sumando un día.

QUÉ ES CONFIGURABLE
===================
Los nombres de las claves de metadatos, las épocas de fábrica y la holgura de la
comprobación de 12 h son **datos del descriptor de formato** (ADR-008), no
constantes de este fichero: `[reloj]` en `data/formats/<formato>.toml`. Los
valores por omisión de `PoliticaReloj` son los del Haltech NSP y sirven para que
el camino de CSV genérico (fase FG) funcione sin descriptor.

ADR-009
=======
`desenrollar_medianoche` no recorre las muestras: es `diff` → comparación →
`cumsum` → `concatenate`, cuatro pasadas vectorizadas. El módulo no importa
NumPy en el ámbito global y solo necesita las cuatro funciones del protocolo
`Vectorial`, así que se puede ejercitar con cualquier implementación que las
ofrezca —incluida una de biblioteca estándar en las pruebas— y el código que se
prueba es exactamente el que corre en producción.

Como el resto de `dlv-core`, este módulo no abre ficheros.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum, auto
from typing import Any, Protocol, cast

from dlv_core.informes import Aviso
from dlv_core.tiempo import FiabilidadReloj, ModoDesfase, Segmento

__all__ = [
    "Desenrollado",
    "ErrorDeReloj",
    "OrdenTemporal",
    "PoliticaReloj",
    "Reconciliacion",
    "Vectorial",
    "desenrollar_medianoche",
    "parsear_fecha_hora",
    "parsear_marca_de_fila",
    "reconciliar",
]

SEGUNDOS_POR_DIA = 86400.0

#: Un retroceso mayor que esto es un cruce de medianoche; uno menor es una marca
#: no monótona. El punto medio entre «segundos de ruido» y «casi 24 h» es tan
#: ancho que el valor exacto no es delicado.
UMBRAL_RETROCESO_S = 12 * 3600.0

# `HH:MM:SS.mmm`. Las horas se aceptan hasta 99 a propósito: hay registradores
# que emiten horas acumuladas (`25:00:00.000`) en vez de dar la vuelta, y una
# marca así es inequívoca y monótona, así que se acepta y se convierte en más de
# 86 400 s. Los minutos y los segundos por encima de 59 sí son inequívocamente
# una marca corrupta y se rechazan.
_RE_MARCA = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})\.(\d{1,6})$")

# `YYYYMMDD HH:MM:SS` de los metadatos `Log` y `DownloadDateTime`.
_RE_FECHA_HORA = re.compile(r"^(\d{4})(\d{2})(\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})$")

_EPOCAS_FICTICIAS_POR_OMISION = frozenset({"19800101", "19700101", "20000101", "20010101"})


class ErrorDeReloj(ValueError):
    """Una marca de tiempo que no se puede interpretar sin inventar."""


class OrdenTemporal(Enum):
    """Qué ordena este log respecto a los demás (§3.6, vista concatenada)."""

    RELOJ = auto()
    """Hay tiempo absoluto fiable: los segmentos se ordenan y se alinean por él."""

    NUMERO_DE_LOG = auto()
    """No hay tiempo absoluto utilizable. El orden lo da el número de log y el
    desfase entre segmentos es desconocido, luego editable por el usuario."""

    SIN_ORDEN = auto()
    """Ni reloj ni número: el usuario tiene que colocarlo a mano."""


class Vectorial(Protocol):
    """Lo que este módulo necesita de NumPy, y nada más.

    Los nombres y las firmas son los de NumPy, así que el propio módulo `numpy`
    satisface el protocolo sin adaptador. Los parámetros son posicionales para
    que cualquier implementación pueda nombrarlos como quiera.
    """

    def diff(self, a: Any, /) -> Any: ...
    def cumsum(self, a: Any, /) -> Any: ...
    def concatenate(self, arrays: Any, /) -> Any: ...
    def count_nonzero(self, a: Any, /) -> int: ...


def _numpy() -> Vectorial:
    """Importa NumPy en el momento de usarlo.

    Así el módulo se puede importar y probar en un entorno sin NumPy, que es la
    situación real mientras F0-01 sigue bloqueada por la política de red.
    """
    import numpy

    return cast("Vectorial", numpy)


# --------------------------------------------------------------------------- #
# Marcas de tiempo
# --------------------------------------------------------------------------- #
def parsear_marca_de_fila(marca: str | bytes) -> float:
    """`'18:30:35.506'` → 66 635,506 segundos desde la medianoche del día local.

    Lanza `ErrorDeReloj` si la marca no tiene la forma esperada. Quien parsea el
    cuerpo decide qué hacer con eso: una fila con marca corrupta se descarta con
    aviso, no tumba la carga (docs/02 §2.5).
    """
    texto = marca.decode("ascii", errors="replace") if isinstance(marca, bytes) else marca
    m = _RE_MARCA.match(texto.strip())
    if m is None:
        raise ErrorDeReloj(f"marca de tiempo no reconocida: {texto!r} (se esperaba HH:MM:SS.mmm)")
    hh, mm, ss, frac = (str(g) for g in m.groups())
    if int(mm) > 59 or int(ss) > 59:
        raise ErrorDeReloj(f"marca de tiempo fuera de rango: {texto!r}")
    # La fracción se normaliza por su longitud en vez de asumir milésimas: así
    # `.5`, `.506` y `.506000` valen lo mismo, que es lo que espera cualquiera.
    return int(hh) * 3600.0 + int(mm) * 60.0 + int(ss) + int(frac) / 10.0 ** len(frac)


def parsear_fecha_hora(valor: str) -> tuple[date, float] | None:
    """`'20260729 06:30:35'` → `(date(2026, 7, 29), 23 435,0)`.

    Devuelve `None` en vez de lanzar: es un metadato, y un metadato ilegible es
    un aviso, no un fallo de carga. La hora se devuelve como segundos desde la
    medianoche **sin resolver la ambigüedad de 12 h**: resolverla es
    responsabilidad de `reconciliar`, que tiene la primera fila para compararla.
    """
    m = _RE_FECHA_HORA.match(valor.strip())
    if m is None:
        return None
    aaaa, mes, dia, hh, mm, ss = (int(g) for g in m.groups())
    if hh > 23 or mm > 59 or ss > 59:
        return None
    try:
        f = date(aaaa, mes, dia)
    except ValueError:
        return None
    return f, hh * 3600.0 + mm * 60.0 + ss


# --------------------------------------------------------------------------- #
# Cruce de medianoche
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class Desenrollado:
    """Resultado de `desenrollar_medianoche`."""

    t: Any
    """Segundos monótonos crecientes desde la medianoche del primer día. Puede
    pasar de 86 400 si el log cruzó la medianoche."""

    cruces_de_medianoche: int
    retrocesos_anomalos: int
    """Marcas que van hacia atrás sin llegar a ser un cruce de medianoche. No se
    corrigen: se cuentan para el informe de importación. Corregirlas exigiría
    adivinar qué quiso decir el registrador."""

    @property
    def hay_anomalias(self) -> bool:
        return self.retrocesos_anomalos > 0


def desenrollar_medianoche(segundos_del_dia: Any, *, xp: Vectorial | None = None) -> Desenrollado:
    """Convierte segundos-del-día que dan la vuelta en un eje monótono.

    Suma un día a partir de cada retroceso de más de `UMBRAL_RETROCESO_S`. Un
    log que cruce varias medianoches se desenrolla igual, porque los cruces se
    acumulan.

    Vectorizado (ADR-009): cuatro pasadas de NumPy, ningún bucle de Python.
    """
    xp = xp if xp is not None else _numpy()
    sod = segundos_del_dia
    if len(sod) < 2:
        # No es un caso de borde tonto: un log de una sola muestra existe (un
        # AutoLog que se cortó al arrancar) y `diff` de un elemento da un array
        # vacío con el que `concatenate` no reconstruiría la longitud.
        return Desenrollado(t=sod, cruces_de_medianoche=0, retrocesos_anomalos=0)

    d = xp.diff(sod)
    cruces = d < -UMBRAL_RETROCESO_S
    n_cruces = int(xp.count_nonzero(cruces))
    # Los retrocesos anómalos son todos los retrocesos menos los cruces. Se
    # calcula por resta en vez de con una máscara negada porque así el protocolo
    # `Vectorial` se queda en cuatro funciones.
    n_retrocesos = int(xp.count_nonzero(d < 0.0))

    acumulado = xp.cumsum(cruces)
    # `diff` devuelve n−1 elementos y hacen falta n: la primera muestra nunca
    # lleva días acumulados. `acumulado[:1] * 0` da ese cero con el tipo que ya
    # tiene el array, sin que este módulo tenga que saber cuál es.
    dias = xp.concatenate((acumulado[:1] * 0, acumulado))
    return Desenrollado(
        t=sod + dias * SEGUNDOS_POR_DIA,
        cruces_de_medianoche=n_cruces,
        retrocesos_anomalos=n_retrocesos - n_cruces,
    )


# --------------------------------------------------------------------------- #
# Política y reconciliación
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class PoliticaReloj:
    """Sección `[reloj]` del descriptor de formato, interpretada.

    Los valores por omisión son los del Haltech NSP, para que el camino de CSV
    genérico funcione sin descriptor.
    """

    clave_inicio: str = "Log"
    clave_descarga: str = "DownloadDateTime"
    clave_numero: str = "Log Number"
    hora_en_12h: bool = True
    epocas_ficticias: frozenset[str] = _EPOCAS_FICTICIAS_POR_OMISION
    fecha_minima_plausible: date = date(2005, 1, 1)
    tolerancia_desfase_s: float = 60.0

    @classmethod
    def desde_mapa(cls, m: Any) -> PoliticaReloj:
        """Construye la política desde el `[reloj]` de un descriptor.

        Una sección ausente o vacía deja los valores por omisión: un descriptor
        que no habla de relojes no debe impedir cargar.
        """
        if not m:
            return cls()
        # Los valores por omisión se leen de una instancia, no de `cls`: con
        # `slots=True` los atributos de clase son descriptores, no los valores.
        omision = cls()
        fecha_min = omision.fecha_minima_plausible
        bruto = m.get("fecha_minima_plausible")
        if bruto is not None:
            analizada = parsear_fecha_hora(f"{bruto} 00:00:00")
            if analizada is None:
                raise ErrorDeReloj(
                    f"[reloj].fecha_minima_plausible = {bruto!r} no es una fecha AAAAMMDD"
                )
            fecha_min = analizada[0]
        return cls(
            clave_inicio=str(m.get("clave_inicio", omision.clave_inicio)),
            clave_descarga=str(m.get("clave_descarga", omision.clave_descarga)),
            clave_numero=str(m.get("clave_numero", omision.clave_numero)),
            hora_en_12h=bool(m.get("hora_en_12h", omision.hora_en_12h)),
            epocas_ficticias=frozenset(
                str(e) for e in m.get("epocas_ficticias", omision.epocas_ficticias)
            ),
            fecha_minima_plausible=fecha_min,
            tolerancia_desfase_s=float(m.get("tolerancia_desfase_s", omision.tolerancia_desfase_s)),
        )

    @property
    def periodo_ambiguo_s(self) -> float:
        """12 h si la hora de cabecera va en 12 h; 24 h si va en 24 h."""
        return 12 * 3600.0 if self.hora_en_12h else SEGUNDOS_POR_DIA


@dataclass(slots=True, frozen=True)
class Reconciliacion:
    """Qué se sabe del reloj de un log, y con cuánta confianza."""

    fiabilidad: FiabilidadReloj

    t0_absoluto: datetime | None
    """Instante de la primera muestra. **Solo se rellena si el reloj es fiable.**

    Es deliberado que sea `None` en cualquier otro caso: la alternativa era
    devolver siempre un valor y confiar en que quien llama se acuerde de mirar
    `fiabilidad`, y eso es un fallo esperando a ocurrir. Para mostrarlo como
    dato informativo está `t0_declarado`."""

    t0_declarado: datetime | None
    """Lo que el log dice que es su instante inicial, fiable o no. Para
    enseñarlo en el informe de importación marcado como no verificado. Nunca
    para calcular."""

    fecha: date | None
    numero_de_log: int | None
    fecha_descarga: date | None

    epoca_ficticia: bool
    """La cabecera declara una época de fábrica: no existe tiempo absoluto."""

    desfase_cabecera_s: float | None
    """Residuo del desfase entre la hora de cabecera y la primera fila, una vez
    quitada la ambigüedad de 12 h. Debería ser casi cero (0,506 s en el AutoLog
    real). `None` si no se pudo comprobar."""

    ordenar_por: OrdenTemporal
    modo_desfase_recomendado: ModoDesfase
    avisos: tuple[Aviso, ...] = ()

    def a_segmento(self, id_: str, *, orden: int, offset_usuario: float = 0.0) -> Segmento:
        """Punto de entrega al motor de tiempo multi-log (§3.6)."""
        return Segmento(
            id=id_,
            t0_absoluto=self.t0_absoluto,
            offset_usuario=offset_usuario,
            fiabilidad_reloj=self.fiabilidad,
            orden=orden,
        )


@dataclass(slots=True)
class _Acumulador:
    avisos: list[Aviso] = field(default_factory=list)

    def avisa(self, codigo: str, mensaje: str) -> None:
        self.avisos.append(Aviso(codigo, mensaje))


def reconciliar(
    metadatos: Any,
    primera_marca_s: float | None,
    *,
    politica: PoliticaReloj | None = None,
) -> Reconciliacion:
    """Decide si este log tiene tiempo absoluto y cuál es.

    `metadatos` es el diccionario de `Cabecera.metadatos`. `primera_marca_s` es
    el resultado de `parsear_marca_de_fila` sobre la primera fila de datos, ya
    desenrollada si hiciera falta (para la primera muestra nunca hace falta).
    """
    pol = politica if politica is not None else PoliticaReloj()
    ac = _Acumulador()

    numero = _entero(metadatos.get(pol.clave_numero))
    descarga = parsear_fecha_hora(metadatos.get(pol.clave_descarga, "") or "")
    fecha_descarga = descarga[0] if descarga else None

    orden_sin_reloj = OrdenTemporal.NUMERO_DE_LOG if numero is not None else OrdenTemporal.SIN_ORDEN

    def sin_reloj(
        *, epoca_ficticia: bool = False, fecha: date | None = None, t0: datetime | None = None
    ) -> Reconciliacion:
        if orden_sin_reloj is OrdenTemporal.SIN_ORDEN:
            ac.avisa(
                "reloj_sin_orden",
                f"sin reloj utilizable y sin '{pol.clave_numero}': el log no se puede "
                "ordenar ni alinear automáticamente respecto a otros; habrá que "
                "colocarlo a mano",
            )
        return Reconciliacion(
            fiabilidad=FiabilidadReloj.DESCONOCIDA,
            t0_absoluto=None,
            t0_declarado=t0,
            fecha=fecha,
            numero_de_log=numero,
            fecha_descarga=fecha_descarga,
            epoca_ficticia=epoca_ficticia,
            desfase_cabecera_s=None,
            ordenar_por=orden_sin_reloj,
            modo_desfase_recomendado=ModoDesfase.RELATIVO,
            avisos=tuple(ac.avisos),
        )

    bruto = metadatos.get(pol.clave_inicio)
    if not bruto:
        ac.avisa(
            "reloj_sin_metadato",
            f"la cabecera no declara '{pol.clave_inicio}': no hay tiempo absoluto",
        )
        return sin_reloj()

    analizado = parsear_fecha_hora(str(bruto))
    if analizado is None:
        ac.avisa(
            "reloj_metadato_ilegible",
            f"'{pol.clave_inicio} : {bruto}' no tiene la forma AAAAMMDD HH:MM:SS; "
            "se ignora y el log se trata como relativo",
        )
        return sin_reloj()

    fecha, sod_cabecera = analizado
    t0_declarado = datetime.combine(fecha, datetime.min.time()) + timedelta(seconds=sod_cabecera)

    # ---- 1. La época, ANTES de cualquier comprobación de desfase ------------ #
    # Con época ficticia el desfase de 12 h sale bien (los logs internos declaran
    # 01:01:01 y empiezan en 01:01:01.005), así que comprobarlo primero marcaría
    # como fiable un log que no tiene reloj. Ver §1.5.
    clave_epoca = f"{fecha.year:04d}{fecha.month:02d}{fecha.day:02d}"
    if clave_epoca in pol.epocas_ficticias or fecha < pol.fecha_minima_plausible:
        ac.avisa(
            "epoca_ficticia",
            f"'{pol.clave_inicio} : {bruto}' es una época de fábrica: la ECU no tiene "
            "reloj de tiempo real, así que este log NO tiene tiempo absoluto. Se ordena "
            f"por '{pol.clave_numero}' y el desfase respecto a otros logs queda a "
            "criterio del usuario; no se finge continuidad",
        )
        return sin_reloj(epoca_ficticia=True, fecha=fecha, t0=t0_declarado)

    if primera_marca_s is None:
        ac.avisa(
            "reloj_sin_primera_fila",
            "no hay ninguna fila de datos con la que validar la hora de cabecera; "
            f"la hora de '{pol.clave_inicio}' es ambigua y no se usa",
        )
        return sin_reloj(fecha=fecha, t0=t0_declarado)

    # ---- 2. La ambigüedad de 12 h, y la fecha de la primera muestra --------- #
    # La cabecera y la primera fila son el mismo instante salvo el retardo de
    # escritura, luego basta buscar qué combinación de «AM o PM» y «mismo día o
    # el siguiente» las hace coincidir:
    #
    #     (H + m·12 h)  ≈  (R + d·24 h)      m ∈ {0,1}   d ∈ {0,1}
    #
    # Las dos incógnitas hacen falta las dos. Con solo m, un log cuya cabecera se
    # escribió justo antes de medianoche (cabecera 11:59:30 en 12 h, primera fila
    # 00:00:10) queda a 12 h de distancia y se rechazaría por reloj no fiable, o
    # peor, se fecharía el día anterior. Con las dos, sale d = 1 y la fecha es la
    # correcta. Cuatro candidatos: no hay nada que iterar por muestra.
    #
    # El módulo de 24 h de la hora resuelta NO es cosmético. En notación de 12 h,
    # «12:30» del día D significa 00:30 o 12:30 **de ese mismo día D**: nadie
    # escribe «12:30» del día D para referirse a las 00:30 del D+1. Sin el módulo,
    # m = 1 convertiría 12:30 en 24:30 y una cabecera de medianoche-y-media se
    # fecharía un día tarde.
    horas_posibles = (
        (sod_cabecera, (sod_cabecera + pol.periodo_ambiguo_s) % SEGUNDOS_POR_DIA)
        if pol.hora_en_12h
        else (sod_cabecera,)
    )
    _, dias, residuo = min(
        (
            (h, d, h - (primera_marca_s + d * SEGUNDOS_POR_DIA))
            for h in horas_posibles
            for d in (0, 1)
        ),
        key=lambda c: abs(c[2]),
    )
    t0_real = (
        datetime.combine(fecha, datetime.min.time())
        + timedelta(days=dias)
        + timedelta(seconds=primera_marca_s)
    )

    if abs(residuo) > pol.tolerancia_desfase_s:
        ac.avisa(
            "reloj_no_fiable",
            f"la hora de '{pol.clave_inicio} : {bruto}' no cuadra con la primera fila "
            f"bajo ninguna interpretación de la ambigüedad de "
            f"{pol.periodo_ambiguo_s / 3600:.0f} h "
            f"(mejor desvío {residuo:+.3f} s, tolerancia {pol.tolerancia_desfase_s:.0f} s): "
            "el reloj del registrador no es fiable y el log se alinea en modo relativo",
        )
        return Reconciliacion(
            fiabilidad=FiabilidadReloj.NO_FIABLE,
            t0_absoluto=None,
            t0_declarado=t0_declarado,
            fecha=fecha,
            numero_de_log=numero,
            fecha_descarga=fecha_descarga,
            epoca_ficticia=False,
            desfase_cabecera_s=residuo,
            ordenar_por=orden_sin_reloj,
            modo_desfase_recomendado=ModoDesfase.RELATIVO,
            avisos=tuple(ac.avisos),
        )

    # ---- 3. Avisos de coherencia ------------------------------------------- #
    if dias:
        ac.avisa(
            "cabecera_antes_de_medianoche",
            f"'{pol.clave_inicio} : {bruto}' se escribió antes de medianoche y la primera "
            f"fila ya es del día siguiente: la primera muestra se fecha el "
            f"{t0_real.date().isoformat()}, no el {fecha.isoformat()}",
        )

    # Solo por fecha: `DownloadDateTime` va también en 12 h, así que comparar
    # horas no diría nada. Y no se usa para ordenar (§1.5: está invertido
    # respecto al número de log en los dos logs internos reales).
    if fecha_descarga is not None and fecha_descarga < fecha:
        ac.avisa(
            "descarga_anterior_al_log",
            f"'{pol.clave_descarga}' ({fecha_descarga.isoformat()}) es anterior a "
            f"'{pol.clave_inicio}' ({fecha.isoformat()}): la fecha de la cabecera es "
            "dudosa aunque la hora cuadre",
        )

    return Reconciliacion(
        fiabilidad=FiabilidadReloj.FIABLE,
        t0_absoluto=t0_real,
        t0_declarado=t0_declarado,
        fecha=fecha,
        numero_de_log=numero,
        fecha_descarga=fecha_descarga,
        epoca_ficticia=False,
        desfase_cabecera_s=residuo,
        ordenar_por=OrdenTemporal.RELOJ,
        modo_desfase_recomendado=ModoDesfase.RELOJ_ABSOLUTO,
        avisos=tuple(ac.avisos),
    )


def _entero(valor: str | None) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor.strip())
    except (ValueError, AttributeError):
        return None
