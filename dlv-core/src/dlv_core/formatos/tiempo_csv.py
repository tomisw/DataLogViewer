"""La columna de tiempo de un CSV genérico, en sus ocho variantes (tarea FG-04).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.5. Los ocho casos están
todos vistos en logs reales, así que ninguno es hipotético:

    hora del día          18:30:35.506
    ISO-8601              2026-07-29T18:30:35.506Z
    epoch en segundos     1785000635.506
    epoch en milisegundos 1785000635506
    relativo              0.000, 0.050, …
    contador de muestras  0, 1, 2, …
    varias columnas       date + time
    sin columna de tiempo el usuario declara la frecuencia

LA REGLA DURA DE §7.5
=====================
    «Si el eje es sintético o el reloj no es fiable, el log se marca igual que los
    logs internos de la ECU (§1.5) y la vista concatenada exige desfase manual.
    **Nunca se finge precisión temporal que no existe.**»

Esa frase es la razón de que este módulo devuelva una `Fiabilidad` junto con el
eje, y de que reutilice `FiabilidadReloj` de `tiempo.py` en vez de inventar su
propio vocabulario: un CSV con eje sintético y un `Log2768` sin reloj de tiempo
real tienen exactamente el mismo problema, y el motor de tiempo multi-log ya sabe
qué hacer con él. Un tipo nuevo obligaría a traducir, y una traducción es donde se
pierde el matiz.

EPOCH EN SEGUNDOS O EN MILISEGUNDOS: SE DISTINGUE POR MAGNITUD
=============================================================
§7.5 lo dice y no hay alternativa: `1785000635` y `1785000635506` son los dos
enteros perfectamente válidos. Lo que los separa es que un epoch en segundos de
una fecha plausible cabe en 10 cifras y en milisegundos necesita 13. Confundirlos
es un factor 1 000 en el eje X: un log de cinco minutos se dibujaría como uno de
tres días, o al revés.

EL PASO NO DECIDE SI ES TIEMPO, DECIDE LA UNIDAD
================================================
Con una columna relativa —`0`, `50`, `100`, …— no se sabe si son segundos o
milisegundos mirando un valor: se sabe mirando el PASO. Un paso de 50 con logging
de ECU son 50 ms; un paso de 0,05 son 50 ms también. La regla: si el paso mediano
es menor que `PASO_MAXIMO_SEGUNDOS_S` la columna está en segundos, y si es mayor,
en milisegundos. Es una heurística y se avisa, porque un log de una hora muestreado
cada 2 s tiene un paso de 2 y también sería válido en segundos.

UN CONTADOR DE MUESTRAS NO ES TIEMPO
====================================
`0, 1, 2, 3, …` es indistinguible de un eje relativo en segundos muestreado a
1 Hz. La diferencia es que un contador es un entero que sube exactamente de uno en
uno, y eso es lo bastante específico como para reconocerlo. Pero no se convierte a
tiempo sin que el usuario declare la frecuencia: convertirlo asumiendo 1 Hz sería
inventar la escala del eje X entero.

Solo biblioteca estándar. Este módulo no abre ficheros.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from itertools import pairwise
from statistics import median

from dlv_core.formatos.decimal_csv import Decimales, es_numerica
from dlv_core.formatos.estructura import Estructura
from dlv_core.formatos.sondeo import Sondeo, dividir_campos
from dlv_core.informes import Aviso
from dlv_core.tiempo import FiabilidadReloj

__all__ = [
    "EPOCH_MAXIMO_S",
    "EPOCH_MINIMO_S",
    "MAX_FILAS_INSPECCIONADAS",
    "PASO_MAXIMO_SEGUNDOS_S",
    "ClaseDeTiempo",
    "ColumnaDeTiempo",
    "ErrorDeTiempoCsv",
    "detectar_columna_de_tiempo",
    "parsear_instante",
]

MAX_FILAS_INSPECCIONADAS = 200

#: Ventana de epoch que se considera plausible para un log de ECU, en segundos.
#: 2000-01-01 a 2100-01-01. Fuera de ahí, un entero grande es un contador, un
#: identificador o una distancia, no una fecha.
EPOCH_MINIMO_S = 946_684_800.0
EPOCH_MAXIMO_S = 4_102_444_800.0

#: Paso mediano por encima del cual una columna relativa se interpreta en
#: milisegundos. Un logging de ECU va de 5 a 100 Hz, así que su paso en segundos
#: está entre 0,01 y 0,2: un paso de 5 o de 50 solo tiene sentido en milisegundos.
#: Se avisa siempre que se use esta regla: es una heurística, no una medida.
PASO_MAXIMO_SEGUNDOS_S = 2.0

#: `HH:MM:SS` con fracción opcional. La misma forma que el formato nativo
#: (`reloj.parsear_marca_de_fila`), y por eso este módulo NO la reimplementa para
#: el cálculo: solo la reconoce para clasificar la columna.
_RE_HORA = re.compile(r"^\d{1,2}:\d{2}:\d{2}([.,]\d+)?$")

#: ISO-8601 con o sin zona: `2026-07-29T18:30:35.506Z`, `2026-07-29 18:30:35`.
_RE_ISO = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})([.,]\d+)?(Z|[+-]\d{2}:?\d{2})?$"
)

#: Solo fecha: `2026-07-29`, `20260729`, `29/07/2026`.
_RE_SOLO_FECHA = re.compile(r"^(\d{4}-\d{2}-\d{2}|\d{8}|\d{1,2}/\d{1,2}/\d{4})$")


class ErrorDeTiempoCsv(ValueError):
    """No se puede construir un eje temporal con esta columna sin inventar."""


class ClaseDeTiempo(Enum):
    """Qué es la columna de tiempo (§7.5). El orden es el de la tabla de §7.5."""

    HORA_DEL_DIA = "hora_del_dia"
    """`18:30:35.506`. Como el formato nativo: la fecha sale de los metadatos."""

    ISO8601 = "iso8601"
    """`2026-07-29T18:30:35.506Z`. Lo único que trae fecha y hora completas."""

    EPOCH_SEGUNDOS = "epoch_segundos"
    EPOCH_MILISEGUNDOS = "epoch_milisegundos"

    RELATIVO = "relativo"
    """`0.000`, `0.050`, … Segundos o milisegundos desde el inicio; la unidad se
    deduce del paso."""

    CONTADOR_DE_MUESTRAS = "contador_de_muestras"
    """`0, 1, 2, …`. No es tiempo hasta que el usuario declare la frecuencia."""

    FECHA_Y_HORA_SEPARADAS = "fecha_y_hora_separadas"
    """Dos columnas, `date` + `time`, que hay que combinar."""

    AUSENTE = "ausente"
    """No hay ninguna columna de tiempo: el eje será sintético."""

    @property
    def tiene_fecha(self) -> bool:
        return self in {ClaseDeTiempo.ISO8601, ClaseDeTiempo.FECHA_Y_HORA_SEPARADAS}

    @property
    def es_absoluta(self) -> bool:
        """¿Sitúa el log en el calendario, o solo mide desde su propio inicio?"""
        return self in {
            ClaseDeTiempo.ISO8601,
            ClaseDeTiempo.EPOCH_SEGUNDOS,
            ClaseDeTiempo.EPOCH_MILISEGUNDOS,
            ClaseDeTiempo.FECHA_Y_HORA_SEPARADAS,
        }

    @property
    def necesita_frecuencia_del_usuario(self) -> bool:
        """§7.5: sin esto el eje no se puede construir, y no se inventa."""
        return self in {ClaseDeTiempo.CONTADOR_DE_MUESTRAS, ClaseDeTiempo.AUSENTE}


@dataclass(slots=True, frozen=True)
class ColumnaDeTiempo:
    """Qué columna es el tiempo, de qué tipo, y con cuánta confianza."""

    clase: ClaseDeTiempo
    indice: int | None
    """Columna donde está el tiempo, o `None` si no hay ninguna."""

    indice_fecha: int | None
    """La columna de fecha, cuando `clase` es `FECHA_Y_HORA_SEPARADAS`."""

    factor_a_segundos: float
    """Cuánto multiplicar el valor crudo para tener segundos. 1,0 para segundos,
    0,001 para milisegundos. Para las clases con fecha no aplica y vale 1,0."""

    fiabilidad: FiabilidadReloj
    """El mismo vocabulario que el motor de tiempo multi-log (`tiempo.py`), a
    propósito: un CSV con eje sintético tiene el mismo problema que un log interno
    de ECU sin reloj de tiempo real, y §7.5 dice que se marque igual."""

    t0_absoluto: datetime | None
    """Instante de la primera muestra, si la columna lo sitúa en el calendario.
    `None` con eje relativo, contador o ausente: ahí no hay tiempo absoluto y no
    se inventa uno."""

    paso_mediano_s: float | None
    frecuencia_hz: float | None
    """Frecuencia deducida del paso, para enseñarla. `None` cuando no hay paso que
    medir (contador sin frecuencia declarada, eje ausente, una sola fila)."""

    nombre: str | None
    avisos: tuple[Aviso, ...] = ()

    @property
    def eje_sintetico(self) -> bool:
        """§7.5: «si el eje es sintético […] nunca se finge precisión temporal»."""
        return self.clase.necesita_frecuencia_del_usuario

    @property
    def exige_desfase_manual(self) -> bool:
        """§7.5: la vista concatenada no puede colocar este log por su cuenta."""
        return self.eje_sintetico or self.fiabilidad is not FiabilidadReloj.FIABLE


@dataclass(slots=True)
class _Acumulador:
    avisos: list[Aviso] = field(default_factory=list)

    def avisa(self, codigo: str, mensaje: str) -> None:
        self.avisos.append(Aviso(codigo, mensaje))


# --------------------------------------------------------------------------- #
# Reconocimiento de un valor suelto
# --------------------------------------------------------------------------- #
def parsear_instante(
    valor: str,
    clase: ClaseDeTiempo,
    *,
    factor_a_segundos: float = 1.0,
    decimal: str = ".",
) -> float:
    """Un valor crudo de la columna de tiempo → **segundos**, siempre.

    Para las clases absolutas devuelve segundos desde la época Unix; para las
    relativas, segundos desde el inicio del log. Lanza `ErrorDeTiempoCsv` si el
    valor no encaja con la clase: quien parsea el cuerpo decide si descarta la
    fila o aborta.

    `factor_a_segundos` se aplica AQUÍ y en ningún otro sitio, y eso fue un
    arreglo. La primera versión dividía por mil dentro de esta función para el
    epoch en milisegundos Y volvía a multiplicar por el factor en el llamador: el
    `t0` del fichero `08-epoch-milisegundos.csv` salía en 1970 en vez de 2026, con
    la escala dividida dos veces. Con el factor como parámetro no hay ningún caso
    especial de milisegundos que recordar: la clasificación decide el factor y esta
    función lo aplica.
    """
    texto = valor.strip()
    if clase is ClaseDeTiempo.ISO8601:
        return _iso_a_segundos(texto)
    if clase in {ClaseDeTiempo.HORA_DEL_DIA, ClaseDeTiempo.FECHA_Y_HORA_SEPARADAS}:
        return _hora_a_segundos(texto, decimal)
    numero = _a_float(texto, decimal)
    if numero is None:
        raise ErrorDeTiempoCsv(f"'{valor}' no es un número, y {clase.value} exige uno")
    return numero * factor_a_segundos


def _a_float(texto: str, decimal: str) -> float | None:
    if not es_numerica(texto, decimal):
        return None
    agrupador = "," if decimal == "." else "."
    try:
        return float(texto.replace(agrupador, "").replace(decimal, "."))
    except ValueError:  # pragma: no cover - `es_numerica` ya lo ha filtrado
        return None


def _hora_a_segundos(texto: str, decimal: str) -> float:
    """`18:30:35.506` → 66 635,506 s desde la medianoche.

    Se validan los rangos y no solo la forma: `25:99:99` encaja en la expresión
    regular y no es una hora. Es la misma regla que `reloj.parsear_marca_de_fila`
    del formato nativo —minutos y segundos por encima de 59 son inequívocamente
    una marca corrupta—, con la misma tolerancia con las horas: hay registradores
    que emiten horas acumuladas (`25:00:00`) en vez de dar la vuelta.
    """
    if _RE_HORA.match(texto) is None:
        raise ErrorDeTiempoCsv(f"'{texto}' no tiene la forma HH:MM:SS[.fff]")
    partes = texto.replace(",", ".").split(":")
    hh, mm, ss = int(partes[0]), int(partes[1]), float(partes[2])
    if mm > 59 or ss >= 60.0:
        raise ErrorDeTiempoCsv(f"'{texto}' está fuera de rango: minutos o segundos > 59")
    return hh * 3600.0 + mm * 60.0 + ss


def _iso_a_segundos(texto: str) -> float:
    m = _RE_ISO.match(texto)
    if m is None:
        raise ErrorDeTiempoCsv(f"'{texto}' no tiene la forma ISO-8601")
    # `fromisoformat` de 3.11+ acepta la `Z`, pero no la coma decimal ni una
    # fracción de más de 6 cifras, y las dos aparecen en exportadores reales.
    normalizado = texto.replace(",", ".")
    if normalizado.endswith("Z"):
        normalizado = normalizado[:-1] + "+00:00"
    fraccion = re.search(r"\.(\d+)", normalizado)
    if fraccion is not None and len(fraccion.group(1)) > 6:
        normalizado = normalizado.replace(fraccion.group(0), "." + fraccion.group(1)[:6])
    try:
        instante = datetime.fromisoformat(normalizado)
    except ValueError as e:
        # `2026-13-45` encaja en la expresión regular y no es una fecha. El error
        # tiene que ser del módulo, no un ValueError de la biblioteca: quien parsea
        # el cuerpo captura `ErrorDeTiempoCsv` para descartar la fila.
        raise ErrorDeTiempoCsv(f"'{texto}' no es una fecha válida: {e}") from None
    if instante.tzinfo is None:
        # Sin zona no se inventa una: se trata como UTC para tener un número, y
        # quien clasifica la columna ya ha avisado de que la zona falta.
        instante = instante.replace(tzinfo=UTC)
    return instante.timestamp()


# --------------------------------------------------------------------------- #
# Clasificación de una columna
# --------------------------------------------------------------------------- #
def _clase_de_columna(valores: list[str], decimal: str) -> tuple[ClaseDeTiempo | None, float]:
    """(clase, factor a segundos) de una columna, o `(None, _)` si no es tiempo.

    Se decide sobre TODOS los valores de la muestra y no sobre el primero: en
    `09-iso8601.csv` la primera fila es `2026-07-29T18:30:00Z`, sin fracción, y la
    segunda `…:00.050000Z`. Clasificar por el primero funciona por casualidad
    hasta que un exportador omite la fracción cuando es cero, que es lo normal.
    """
    llenos = [v.strip() for v in valores if v.strip()]
    if not llenos:
        return None, 1.0

    if all(_RE_ISO.match(v) for v in llenos):
        return ClaseDeTiempo.ISO8601, 1.0
    if all(_RE_HORA.match(v) for v in llenos):
        return ClaseDeTiempo.HORA_DEL_DIA, 1.0

    numeros = [_a_float(v, decimal) for v in llenos]
    if any(n is None for n in numeros):
        return None, 1.0
    limpios = [n for n in numeros if n is not None]

    # Epoch: por magnitud, que es lo único que separa `1785000635` de
    # `1785000635506` (§7.5).
    if all(EPOCH_MINIMO_S <= n <= EPOCH_MAXIMO_S for n in limpios):
        return ClaseDeTiempo.EPOCH_SEGUNDOS, 1.0
    if all(EPOCH_MINIMO_S * 1000 <= n <= EPOCH_MAXIMO_S * 1000 for n in limpios):
        return ClaseDeTiempo.EPOCH_MILISEGUNDOS, 0.001

    if not _es_creciente(limpios):
        return None, 1.0

    # Contador de muestras: entero que sube exactamente de uno en uno. Se
    # comprueba antes que el relativo porque un contador ES un caso particular de
    # columna creciente, y tratarlo como tiempo inventaría la escala del eje.
    if _es_contador(limpios):
        return ClaseDeTiempo.CONTADOR_DE_MUESTRAS, 1.0

    paso = _paso_mediano(limpios)
    if paso is None:
        return ClaseDeTiempo.RELATIVO, 1.0
    return ClaseDeTiempo.RELATIVO, (1.0 if paso <= PASO_MAXIMO_SEGUNDOS_S else 0.001)


def _es_creciente(valores: list[float]) -> bool:
    return all(b >= a for a, b in pairwise(valores))


def _es_contador(valores: list[float]) -> bool:
    if len(valores) < 3:
        return False
    if any(v != int(v) for v in valores):
        return False
    return all(b - a == 1.0 for a, b in pairwise(valores))


def _paso_mediano(valores: list[float]) -> float | None:
    pasos = [b - a for a, b in pairwise(valores) if b > a]
    return median(pasos) if pasos else None


def _instante(fecha: date, segundos_del_dia: float) -> datetime:
    """Fecha + segundos desde la medianoche → instante en UTC."""
    base = datetime(fecha.year, fecha.month, fecha.day, tzinfo=UTC)
    return datetime.fromtimestamp(base.timestamp() + segundos_del_dia, tz=UTC)


def _primera_fecha(valores: list[str]) -> date | None:
    """La primera fecha legible de una columna de solo fechas."""
    for v in valores:
        texto = v.strip()
        if _RE_SOLO_FECHA.match(texto) is None:
            continue
        try:
            if "-" in texto:
                return date.fromisoformat(texto)
            if "/" in texto:
                d, m, a = (int(x) for x in texto.split("/"))
                return date(a, m, d)
            return date(int(texto[:4]), int(texto[4:6]), int(texto[6:8]))
        except ValueError:
            continue
    return None


def _columna_de_fecha(columnas: list[list[str]]) -> int | None:
    for i, valores in enumerate(columnas):
        llenos = [v.strip() for v in valores if v.strip()]
        if llenos and all(_RE_SOLO_FECHA.match(v) for v in llenos):
            return i
    return None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def detectar_columna_de_tiempo(
    sondeo: Sondeo,
    decimales: Decimales,
    estructura: Estructura,
    texto: str,
    *,
    frecuencia_declarada_hz: float | None = None,
    fecha_de_metadatos: date | None = None,
) -> ColumnaDeTiempo:
    """Encuentra y clasifica la columna de tiempo (§7.5, las ocho variantes).

    `frecuencia_declarada_hz` es lo que el usuario declara cuando no hay columna
    de tiempo o cuando lo que hay es un contador de muestras. Sin ella el eje no
    se construye: §7.5 dice que el usuario la declara, y suponer 1 Hz o 20 Hz
    sería inventar la escala del eje X completo.

    `fecha_de_metadatos` sitúa en el calendario una columna de hora del día, igual
    que hace el formato nativo con su metadato `Log` (§1.4). Sin fecha, la hora
    del día es un eje relativo con una hora de inicio.
    """
    if sondeo.delimitador is None:
        raise ErrorDeTiempoCsv("el sondeo no propuso delimitador: no hay columnas que mirar")

    ac = _Acumulador()
    lineas = [linea for linea in texto.splitlines() if linea.strip()]
    filas = [
        dividir_campos(linea, sondeo.delimitador, sondeo.comilla)
        for linea in lineas[estructura.linea_inicio_datos :][:MAX_FILAS_INSPECCIONADAS]
    ]
    if not filas:
        raise ErrorDeTiempoCsv("no hay filas de datos con las que clasificar el tiempo")

    n = estructura.n_columnas
    columnas = [[fila[i] if i < len(fila) else "" for fila in filas] for i in range(n)]
    nombres = estructura.nombres_o_posicionales()

    # Se recorren las columnas en orden y gana la primera que sea tiempo: en los
    # ocho casos de §7.5 el tiempo es la primera columna, y una columna posterior
    # que también lo parezca (un `lap_time`) no es el eje del log.
    for i, valores in enumerate(columnas):
        clase, factor = _clase_de_columna(valores, decimales.separador)
        if clase is None:
            continue
        return _resolver(
            clase=clase,
            factor=factor,
            indice=i,
            nombre=nombres[i] if i < len(nombres) else None,
            valores=valores,
            columnas=columnas,
            decimal=decimales.separador,
            frecuencia_declarada_hz=frecuencia_declarada_hz,
            fecha_de_metadatos=fecha_de_metadatos,
            ac=ac,
        )

    # Caso 6 de §7.5: no hay columna de tiempo. El eje se sintetiza con la
    # frecuencia que declare el usuario, y el log queda marcado.
    return _sin_columna(len(filas), frecuencia_declarada_hz, ac)


def _resolver(
    *,
    clase: ClaseDeTiempo,
    factor: float,
    indice: int,
    nombre: str | None,
    valores: list[str],
    columnas: list[list[str]],
    decimal: str,
    frecuencia_declarada_hz: float | None,
    fecha_de_metadatos: date | None,
    ac: _Acumulador,
) -> ColumnaDeTiempo:
    indice_fecha: int | None = None

    if clase is ClaseDeTiempo.HORA_DEL_DIA:
        indice_fecha = _columna_de_fecha(columnas)
        if indice_fecha is not None:
            # Caso 7 de §7.5: `date` + `time` en dos columnas.
            clase = ClaseDeTiempo.FECHA_Y_HORA_SEPARADAS

    segundos = [
        parsear_instante(v, clase, factor_a_segundos=factor, decimal=decimal)
        for v in valores
        if v.strip()
    ]
    paso = _paso_mediano(segundos) if len(segundos) > 1 else None
    frecuencia = (1.0 / paso) if paso else None

    if clase is ClaseDeTiempo.CONTADOR_DE_MUESTRAS:
        if frecuencia_declarada_hz is None:
            ac.avisa(
                "contador_sin_frecuencia",
                f"la columna '{nombre}' es un contador de muestras (0, 1, 2, …), no una "
                "medida de tiempo. Hace falta que declares la frecuencia de muestreo: "
                "suponer una inventaría la escala del eje X completo",
            )
            return ColumnaDeTiempo(
                clase=clase,
                indice=indice,
                indice_fecha=None,
                factor_a_segundos=1.0,
                fiabilidad=FiabilidadReloj.DESCONOCIDA,
                t0_absoluto=None,
                paso_mediano_s=None,
                frecuencia_hz=None,
                nombre=nombre,
                avisos=tuple(ac.avisos),
            )
        ac.avisa(
            "eje_sintetico_desde_contador",
            f"la columna '{nombre}' es un contador de muestras; el eje se construye con "
            f"la frecuencia declarada de {frecuencia_declarada_hz} Hz. El log queda "
            "marcado como de reloj desconocido y la vista concatenada exigirá desfase "
            "manual (§7.5)",
        )
        return ColumnaDeTiempo(
            clase=clase,
            indice=indice,
            indice_fecha=None,
            factor_a_segundos=1.0 / frecuencia_declarada_hz,
            fiabilidad=FiabilidadReloj.DESCONOCIDA,
            t0_absoluto=None,
            paso_mediano_s=1.0 / frecuencia_declarada_hz,
            frecuencia_hz=frecuencia_declarada_hz,
            nombre=nombre,
            avisos=tuple(ac.avisos),
        )

    if clase is ClaseDeTiempo.RELATIVO:
        unidad = "segundos" if factor == 1.0 else "milisegundos"
        ac.avisa(
            "unidad_del_eje_relativo_por_el_paso",
            f"la columna '{nombre}' es un eje relativo y se interpreta en {unidad} "
            f"porque su paso mediano es {paso:.4g}"
            if paso is not None
            else f"la columna '{nombre}' es un eje relativo en {unidad}",
        )

    t0: datetime | None = None
    fiabilidad = FiabilidadReloj.DESCONOCIDA
    if clase is ClaseDeTiempo.FECHA_Y_HORA_SEPARADAS and indice_fecha is not None:
        # La hora sale de su columna y la fecha de la otra; combinarlas es lo que
        # pide el caso 7 de §7.5.
        fecha = _primera_fecha(columnas[indice_fecha])
        if fecha is not None and segundos:
            t0 = _instante(fecha, segundos[0])
            fiabilidad = FiabilidadReloj.FIABLE
    elif clase.es_absoluta and segundos:
        t0 = datetime.fromtimestamp(segundos[0], tz=UTC)
        fiabilidad = FiabilidadReloj.FIABLE
    elif clase is ClaseDeTiempo.HORA_DEL_DIA:
        if fecha_de_metadatos is not None and segundos:
            t0 = _instante(fecha_de_metadatos, segundos[0])
            fiabilidad = FiabilidadReloj.FIABLE
        else:
            ac.avisa(
                "hora_sin_fecha",
                f"la columna '{nombre}' da la hora del día pero el fichero no declara la "
                "fecha en ningún metadato: el log no se puede situar en el calendario y "
                "queda como relativo con hora de inicio (§7.5)",
            )

    return ColumnaDeTiempo(
        clase=clase,
        indice=indice,
        indice_fecha=indice_fecha,
        factor_a_segundos=factor,
        fiabilidad=fiabilidad,
        t0_absoluto=t0,
        paso_mediano_s=paso,
        frecuencia_hz=frecuencia,
        nombre=nombre,
        avisos=tuple(ac.avisos),
    )


def _sin_columna(
    n_filas: int, frecuencia_declarada_hz: float | None, ac: _Acumulador
) -> ColumnaDeTiempo:
    if frecuencia_declarada_hz is None:
        ac.avisa(
            "sin_columna_de_tiempo",
            "ninguna columna sirve como eje temporal. Hace falta que declares la "
            "frecuencia de muestreo para sintetizar el eje; el log quedará marcado como "
            "de tiempo sintético y la vista concatenada exigirá desfase manual (§7.5)",
        )
        return ColumnaDeTiempo(
            clase=ClaseDeTiempo.AUSENTE,
            indice=None,
            indice_fecha=None,
            factor_a_segundos=1.0,
            fiabilidad=FiabilidadReloj.DESCONOCIDA,
            t0_absoluto=None,
            paso_mediano_s=None,
            frecuencia_hz=None,
            nombre=None,
            avisos=tuple(ac.avisos),
        )
    if frecuencia_declarada_hz <= 0.0:
        raise ErrorDeTiempoCsv(
            f"la frecuencia declarada tiene que ser positiva, y es {frecuencia_declarada_hz}"
        )
    dt = 1.0 / frecuencia_declarada_hz
    ac.avisa(
        "eje_sintetico",
        f"no hay columna de tiempo: el eje se sintetiza a {frecuencia_declarada_hz} Hz "
        f"({n_filas} filas, {n_filas * dt:.3g} s). Es un eje SINTÉTICO, así que el log se "
        "marca igual que un log interno de ECU sin reloj de tiempo real y la vista "
        "concatenada exigirá desfase manual (§7.5)",
    )
    return ColumnaDeTiempo(
        clase=ClaseDeTiempo.AUSENTE,
        indice=None,
        indice_fecha=None,
        factor_a_segundos=dt,
        fiabilidad=FiabilidadReloj.DESCONOCIDA,
        t0_absoluto=None,
        paso_mediano_s=dt,
        frecuencia_hz=frecuencia_declarada_hz,
        nombre=None,
        avisos=tuple(ac.avisos),
    )
