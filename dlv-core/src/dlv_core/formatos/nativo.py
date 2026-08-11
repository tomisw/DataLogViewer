"""Motor de formatos nativos declarativos (tarea FG-13, `docs/07` §7.3 nivel 1).

Este módulo lee la cabecera de un formato nativo de texto **sin saber de qué
fabricante es**. Todo lo que distingue a un formato de otro vive en su
descriptor, `data/formats/<formato>.toml`, que es un dato versionado (ADR-008):

    «El formato Haltech de 01-formato-log.md es el primer descriptor, y es la
    prueba de que la capa declarativa basta: si añadir Haltech requiere código,
    el diseño ha fallado.»  (docs/07 §7.3)

Hasta FG-13 el parser era `formatos/haltech.py` y quedaban dentro decisiones
que son del formato y no del motor: la clave `DataLogVersion`, los nombres
`ID`/`Type`/`DisplayMaxMin` y su papel, el `:` que separa clave y valor, el
orden «máximo primero» del rango y la forma `HH:MM:SS.mmm,` con la que se
reconoce la primera fila de datos. Ahora son entradas del descriptor y este
módulo no cita ninguna. `formatos/haltech.py` sigue existiendo como reexport
para no romper a quien lo importaba, igual que `informes.py` dejó a `haltech.py`
reexportando `Aviso`.

LA FRONTERA: QUÉ ES DESCRIPTOR Y QUÉ ES MOTOR
=============================================
El criterio, una sola pregunta: **¿otro fabricante lo haría de otra manera?**

    Descriptor   la firma, la clave y las versiones de compatibilidad, el
                 separador de clave y valor, qué clave abre un bloque de canal,
                 qué clave es la identidad, qué clave es el tipo, qué claves son
                 opcionales, qué clave trae el rango declarado y en qué orden,
                 la codificación, el delimitador de campos y la forma de la
                 marca de tiempo.
    Motor        el BOM y los tres finales de línea, el recuento de
                 desplazamientos en bytes, la máquina de estados que abre y
                 cierra bloques, qué es error y qué es aviso (E1.7), la
                 detección de nombres e identidades repetidos, y la mecánica de
                 leer un CSV disperso multi-tasa (que no tiene nada de
                 específico: los grupos de muestreo salen del patrón de nulos,
                 `almacen.py` y `grupos_muestreo.py`).

EL DESCRIPTOR ES ESTRICTO A PROPÓSITO
=====================================
`cargar_descriptor` exige las claves cuya ausencia se pagaría en silencio: si un
descriptor no dice cuál es su clave de tipo, adivinarla («será `Type`») produce
canales con la escala equivocada y un fichero que parece haberse leído bien. Las
que sí se pueden omitir son las que significan «este formato no tiene eso»:
`clave_version` (un formato sin línea de versión) y `clave_rango` (un formato que
no declara rangos). Un descriptor incompleto o incoherente falla al cargarse,
con el nombre del formato y de la clave en el mensaje.

QUÉ SIGUE CABLEADO EN PYTHON, Y POR QUÉ (para FG-17)
====================================================
Lo que este módulo NO sabe expresar todavía. No está escondido: está aquí para
que la guía de FG-17 lo documente como límite del nivel 1.

1. **La marca de tiempo se reconoce, pero solo se sabe interpretar una clase.**
   El descriptor declara `[cuerpo].patron_marca` (con qué forma empieza una fila
   de datos) y `[cuerpo].clase_de_tiempo` con el vocabulario de
   `ClaseDeTiempo` (FG-04), pero el único intérprete que existe es
   `reloj.parsear_marca_de_fila`, que solo entiende la hora del día
   `HH:MM:SS.mmm`. Un descriptor que declare otra clase se **rechaza al
   cargarse** con un mensaje que lo dice, en vez de cargar y producir un eje de
   tiempo inventado.
2. **La marca de tiempo está en la primera columna.** `Canal.columna` es
   `orden + 1` y de ahí depende toda la ruta de cuerpo (`cuerpo.py`,
   `almacen.py`). Un formato que ponga el tiempo en otra columna necesita
   código.
3. **El rango declarado es una pareja de enteros.** Es lo que exige el
   almacenamiento entero de ADR-003 y lo que trae Haltech; un formato con
   rangos decimales perdería la parte fraccionaria, así que hoy se avisa y se
   ignora, no se redondea.
4. **Los metadatos son planos, `clave <sep> valor`, una línea por entrada.** Un
   formato con secciones anidadas, o con la cabecera en una sola línea, no cabe
   en esta gramática. Es el «gancho opcional de código» que docs/07 §7.3 ya
   admite para lo indescriptible.
5. **La política de reloj por omisión sigue siendo la de Haltech.**
   `reloj.PoliticaReloj` da valores por omisión (`Log`, `DownloadDateTime`,
   `Log Number`, hora en 12 h) para que el camino de CSV genérico funcione sin
   descriptor. Consecuencia: un descriptor que se olvide de `[reloj]` hereda en
   silencio los nombres de clave de Haltech. Declararlo siempre.
6. **Descubrir los descriptores no es parte de este módulo.** `dlv-core` no abre
   ficheros (ADR-002): hoy `dlv-api` carga un único `haltech_nsp.toml` por ruta
   fija (`dlv_api.main._descriptor_haltech`). Añadir un formato es escribir un
   descriptor, pero además hay que dárselo a `sondear_formato`.

QUÉ ES UN ERROR Y QUÉ ES UN AVISO
=================================
La regla, de `docs/02` §2.5 (E1.7): el parser **avisa y sigue** siempre que pueda
producir datos utilizables, y **rechaza** solo cuando seguir daría resultados
silenciosamente equivocados.

    Rechaza  cabecera incompleta (no se puede saber qué columna es qué canal)
             versión mayor desconocida (la gramática podría haber cambiado)
    Avisa    tipo desconocido, rango declarado ilegible, nombre o identidad
             repetidos, escala sin confirmar

Como el resto de `dlv-core`, este módulo no abre ficheros: recibe los bytes.
Solo biblioteca estándar.
"""

from __future__ import annotations

import codecs
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import IO, Any

from dlv_core.formatos.tiempo_csv import ClaseDeTiempo
from dlv_core.informes import Aviso

__all__ = [
    "BOM_UTF8",
    "Aviso",
    "Cabecera",
    "Canal",
    "Descriptor",
    "ErrorDeDescriptor",
    "ErrorDeFormato",
    "FormaDelCuerpo",
    "GramaticaCabecera",
    "cargar_descriptor",
    "parsear_cabecera",
    "sondear_formato",
]

BOM_UTF8 = b"\xef\xbb\xbf"

DELIMITADOR_POR_OMISION = ","
"""Delimitador de una `Cabecera` construida a mano, sin descriptor detrás. Es la
coma porque es el candidato base de cualquier CSV (`docs/07` §7.4 paso 3); un
formato nativo real declara el suyo y nunca usa este valor."""

#: Clases de marca de tiempo que la ruta nativa sabe **interpretar** hoy, no
#: solo reconocer. Ver el punto 1 de "QUÉ SIGUE CABLEADO EN PYTHON": el único
#: intérprete es `reloj.parsear_marca_de_fila`.
CLASES_DE_TIEMPO_SOPORTADAS = frozenset({ClaseDeTiempo.HORA_DEL_DIA})

_ORDENES_DE_RANGO = (("max", "min"), ("min", "max"))


class ErrorDeFormato(ValueError):
    """El fichero no se puede leer sin arriesgar resultados equivocados."""


class ErrorDeDescriptor(ErrorDeFormato):
    """El descriptor de formato está incompleto o se contradice.

    Subclase de `ErrorDeFormato` a propósito: quien envuelve la carga de un
    formato nativo en un `except ErrorDeFormato` no tiene que aprender un tipo
    nuevo, y quien quiera distinguir «el fichero está mal» de «el descriptor está
    mal» puede.
    """


@dataclass(slots=True, frozen=True)
class Canal:
    """Un canal de la cabecera, ya resuelto contra el descriptor.

    `orden` es lo que fija a qué columna de datos corresponde: la columna 0 es la
    marca de tiempo y la columna `orden + 1` es este canal (docs/01 §1.3).
    """

    orden: int
    nombre: str
    id: int
    tipo: str
    display_max: int | None
    display_min: int | None
    # Resuelto desde el descriptor. `dimension` None significa que el tipo no
    # está en el descriptor: se muestra en crudo, sin unidad (mitigación de R1).
    dimension: str | None
    a_canonica: float
    confianza: str

    @property
    def columna(self) -> int:
        return self.orden + 1

    @property
    def se_muestra_en_crudo(self) -> bool:
        return self.dimension is None or self.confianza == "unknown"


@dataclass(slots=True, frozen=True)
class GramaticaCabecera:
    """Sección `[cabecera]` del descriptor, interpretada.

    Todos los campos son obligatorios salvo los dos que pueden significar «este
    formato no tiene eso» (`clave_version`, `clave_rango`).
    """

    separador_clave_valor: str
    """El `:` de `Channel : Oil Pressure`. Se recortan los espacios de los dos
    lados, así que `clave : valor` y `clave=valor` se declaran igual de simple."""

    clave_canal: str
    """La clave que ABRE un bloque de canal. El orden de los bloques fija el
    orden de las columnas (docs/01 §1.3)."""

    clave_identidad: str
    """La clave que da la identidad estable del canal entre logs. Nunca el
    nombre (docs/01 §1.3, docs/07 §7.11)."""

    clave_tipo: str
    """La clave cuyo valor se resuelve contra `[tipos]` para dar dimensión y
    escala."""

    claves_bloque: tuple[str, ...]
    """Todas las claves que pertenecen a un bloque de canal. Una clave que no
    esté aquí cierra el bloque y se guarda como metadato."""

    claves_opcionales: frozenset[str]
    """Las de `claves_bloque` que pueden faltar sin desalinear nada. Las demás
    son obligatorias y su ausencia rechaza el fichero."""

    clave_version: str | None
    """La clave que gobierna la compatibilidad. `None` en un formato que no
    versiona su cabecera: entonces no se exige ni se comprueba."""

    clave_rango: str | None
    """La clave que trae el rango declarado del canal (el `DisplayMaxMin` de
    Haltech). `None` en un formato que no declara rangos."""

    rango_separador: str
    rango_orden: tuple[str, str]
    """`("max", "min")` o `("min", "max")`: en qué orden vienen los dos valores
    del rango. Invertirlo no rompe nada visible, deja el máximo en el mínimo."""

    @property
    def claves_obligatorias(self) -> tuple[str, ...]:
        """`claves_bloque` menos las opcionales, en el orden declarado."""
        return tuple(k for k in self.claves_bloque if k not in self.claves_opcionales)


@dataclass(slots=True, frozen=True)
class FormaDelCuerpo:
    """Sección `[cuerpo]` del descriptor, interpretada."""

    delimitador: str
    """Separador de campos de una fila de datos."""

    clase_de_tiempo: ClaseDeTiempo
    """Qué es la primera columna, con el vocabulario de FG-04 (`tiempo_csv`). Se
    reutiliza en vez de inventar otro: un eje sintético de CSV genérico y un log
    interno de ECU sin reloj tienen el mismo problema, y traducir entre dos
    vocabularios es donde se pierde el matiz."""

    patron_marca: str
    """Expresión regular de la marca de tiempo **sin anclas y sin el
    delimitador**: es lo que distingue la primera fila de datos de la última
    línea de cabecera."""


@dataclass(slots=True, frozen=True)
class Descriptor:
    """`data/formats/<formato>.toml` en memoria (F0-09, FG-13)."""

    formato: str
    firma: bytes
    versiones_soportadas: frozenset[str]
    codificacion: str
    cabecera: GramaticaCabecera
    cuerpo: FormaDelCuerpo
    tipos: Mapping[str, Mapping[str, Any]]
    fila_de_datos: re.Pattern[bytes]
    """`patron_marca` + delimitador, compilado sobre bytes y anclado al inicio.
    Se compila al cargar el descriptor y no en cada fichero, y se compila sobre
    bytes para no tener que decodificar cada línea de la cabecera solo para
    saber si es una fila de datos."""

    reloj: Mapping[str, Any] = field(default_factory=dict)
    """Sección `[reloj]` del descriptor, sin interpretar. La interpreta
    `dlv_core.reloj.PoliticaReloj.desde_mapa` (F1-04); aquí solo se transporta,
    para que este módulo no tenga que saber nada de husos ni de épocas."""

    def resuelve(self, tipo: str) -> tuple[str | None, float, str]:
        """(dimension, a_canonica, confianza) para el tipo declarado de un canal."""
        t = self.tipos.get(tipo)
        if t is None:
            return None, 1.0, "unknown"
        return str(t["dimension"]), float(t["a_canonica"]), str(t["confianza"])


# --------------------------------------------------------------------------- #
# Carga del descriptor
# --------------------------------------------------------------------------- #
def _seccion(bruto: Mapping[str, Any], nombre: str, formato: str) -> Mapping[str, Any]:
    valor = bruto.get(nombre)
    if not isinstance(valor, Mapping):
        raise ErrorDeDescriptor(f"el descriptor {formato} no declara la sección [{nombre}]")
    return valor


def _texto(mapa: Mapping[str, Any], clave: str, *, seccion: str, formato: str) -> str:
    valor = mapa.get(clave)
    if not isinstance(valor, str) or not valor:
        raise ErrorDeDescriptor(
            f"el descriptor {formato} no declara [{seccion}].{clave}, y sin ella el "
            "motor tendría que adivinarla"
        )
    return valor


def _texto_opcional(mapa: Mapping[str, Any], clave: str) -> str | None:
    valor = mapa.get(clave)
    return valor if isinstance(valor, str) and valor else None


def _lista_de_textos(
    mapa: Mapping[str, Any], clave: str, *, seccion: str, formato: str
) -> tuple[str, ...]:
    valor = mapa.get(clave)
    if not isinstance(valor, Sequence) or isinstance(valor, str) or not valor:
        raise ErrorDeDescriptor(
            f"el descriptor {formato} no declara [{seccion}].{clave} como una lista no vacía"
        )
    return tuple(str(v) for v in valor)


def _gramatica(bruto: Mapping[str, Any], formato: str) -> GramaticaCabecera:
    cab = _seccion(bruto, "cabecera", formato)
    det = _seccion(bruto, "deteccion", formato)
    claves_bloque = _lista_de_textos(cab, "claves_bloque", seccion="cabecera", formato=formato)
    opcionales = frozenset(str(k) for k in cab.get("claves_opcionales", ()))
    clave_rango = _texto_opcional(cab, "clave_rango")

    gramatica = GramaticaCabecera(
        separador_clave_valor=_texto(
            cab, "separador_clave_valor", seccion="cabecera", formato=formato
        ),
        clave_canal=_texto(cab, "clave_canal", seccion="cabecera", formato=formato),
        # `identidad` es el nombre que esta clave tiene en el descriptor desde
        # F0-09 («la identidad del canal es el ID, nunca el nombre»); se
        # conserva en vez de renombrarla para no reescribir un fichero de datos
        # ya revisado en una puerta G1.
        clave_identidad=_texto(cab, "identidad", seccion="cabecera", formato=formato),
        clave_tipo=_texto(cab, "clave_tipo", seccion="cabecera", formato=formato),
        claves_bloque=claves_bloque,
        claves_opcionales=opcionales,
        clave_version=_texto_opcional(det, "clave_version"),
        clave_rango=clave_rango,
        rango_separador=(
            _texto(cab, "rango_separador", seccion="cabecera", formato=formato)
            if clave_rango is not None
            else ""
        ),
        rango_orden=_orden_de_rango(cab, formato) if clave_rango is not None else ("max", "min"),
    )

    # Coherencia. Un descriptor que nombre como identidad una clave que no es de
    # bloque, o que la declare opcional, cargaría y luego fallaría canal a canal.
    for papel, clave in (
        ("identidad", gramatica.clave_identidad),
        ("clave_tipo", gramatica.clave_tipo),
    ):
        if clave not in gramatica.claves_bloque:
            raise ErrorDeDescriptor(
                f"el descriptor {formato} declara [cabecera].{papel} = {clave!r}, que no "
                "está en claves_bloque"
            )
        if clave in opcionales:
            raise ErrorDeDescriptor(
                f"el descriptor {formato} declara [cabecera].{papel} = {clave!r} como "
                "opcional; sin ella no se puede saber qué columna es qué canal"
            )
    if clave_rango is not None and clave_rango not in gramatica.claves_bloque:
        raise ErrorDeDescriptor(
            f"el descriptor {formato} declara [cabecera].clave_rango = {clave_rango!r}, "
            "que no está en claves_bloque"
        )
    sobran = opcionales - set(gramatica.claves_bloque)
    if sobran:
        raise ErrorDeDescriptor(
            f"el descriptor {formato} declara como opcionales claves que no son de "
            f"bloque: {', '.join(sorted(sobran))}"
        )
    return gramatica


def _orden_de_rango(cab: Mapping[str, Any], formato: str) -> tuple[str, str]:
    orden = _lista_de_textos(cab, "rango_orden", seccion="cabecera", formato=formato)
    if orden not in _ORDENES_DE_RANGO:
        raise ErrorDeDescriptor(
            f"el descriptor {formato} declara [cabecera].rango_orden = {list(orden)!r}; "
            "los únicos valores posibles son ['max', 'min'] y ['min', 'max']"
        )
    return (orden[0], orden[1])


def _cuerpo(bruto: Mapping[str, Any], formato: str) -> FormaDelCuerpo:
    cue = _seccion(bruto, "cuerpo", formato)
    bruta = _texto(cue, "clase_de_tiempo", seccion="cuerpo", formato=formato)
    try:
        clase = ClaseDeTiempo(bruta)
    except ValueError:
        posibles = ", ".join(sorted(c.value for c in ClaseDeTiempo))
        raise ErrorDeDescriptor(
            f"el descriptor {formato} declara [cuerpo].clase_de_tiempo = {bruta!r}, que no "
            f"es una clase de tiempo conocida ({posibles})"
        ) from None
    if clase not in CLASES_DE_TIEMPO_SOPORTADAS:
        # Rechazo explícito en vez de cargar: reconocer la fila es fácil,
        # interpretar la marca no, y el único intérprete que hay hoy es
        # `reloj.parsear_marca_de_fila` (hora del día). Cargar el descriptor y
        # producir después un eje de tiempo inventado es exactamente lo que
        # docs/07 §7.5 prohíbe.
        soportadas = ", ".join(sorted(c.value for c in CLASES_DE_TIEMPO_SOPORTADAS))
        raise ErrorDeDescriptor(
            f"el descriptor {formato} declara [cuerpo].clase_de_tiempo = {clase.value!r}, "
            f"que la ruta nativa reconoce pero todavía no sabe interpretar (soportadas: "
            f"{soportadas}); ver FG-13/FG-17"
        )
    return FormaDelCuerpo(
        delimitador=_texto(cue, "delimitador", seccion="cuerpo", formato=formato),
        clase_de_tiempo=clase,
        patron_marca=_texto(cue, "patron_marca", seccion="cuerpo", formato=formato),
    )


def _compilar_fila(cuerpo: FormaDelCuerpo, codificacion: str, formato: str) -> re.Pattern[bytes]:
    """La forma de una fila de datos, en bytes: marca + delimitador.

    El delimitador se escapa: es un dato, y un formato con `|` de delimitador no
    debe acabar declarando una alternancia sin querer.
    """
    try:
        crudo = cuerpo.patron_marca.encode(codificacion)
        delimitador = re.escape(cuerpo.delimitador.encode(codificacion))
    except (UnicodeEncodeError, LookupError) as error:
        raise ErrorDeDescriptor(
            f"el descriptor {formato} declara un [cuerpo] que no se puede codificar en "
            f"{codificacion}: {error}"
        ) from None
    try:
        return re.compile(b"^" + crudo + delimitador)
    except re.error as error:
        raise ErrorDeDescriptor(
            f"el descriptor {formato} declara [cuerpo].patron_marca = "
            f"{cuerpo.patron_marca!r}, que no es una expresión regular válida: {error}"
        ) from None


def cargar_descriptor(fuente: IO[bytes]) -> Descriptor:
    """Carga un descriptor de formato nativo desde su TOML ya abierto.

    Lanza `ErrorDeDescriptor` si le falta algo que el motor tendría que adivinar.
    """
    bruto = tomllib.load(fuente)
    meta = _seccion(bruto, "meta", "(sin nombre)")
    formato = _texto(meta, "formato", seccion="meta", formato="(sin nombre)")
    det = _seccion(bruto, "deteccion", formato)

    codificacion = str(det.get("codificacion", "utf-8"))
    try:
        codecs.lookup(codificacion)
    except LookupError:
        raise ErrorDeDescriptor(
            f"el descriptor {formato} declara [deteccion].codificacion = {codificacion!r}, "
            "que no es una codificación conocida"
        ) from None

    tipos = bruto.get("tipos")
    if not isinstance(tipos, Mapping):
        raise ErrorDeDescriptor(f"el descriptor {formato} no declara la sección [tipos]")

    cuerpo = _cuerpo(bruto, formato)
    return Descriptor(
        formato=formato,
        firma=_texto(det, "primera_linea", seccion="deteccion", formato=formato).encode(
            codificacion
        ),
        versiones_soportadas=frozenset(str(v) for v in det.get("version_soportada", ())),
        codificacion=codificacion,
        cabecera=_gramatica(bruto, formato),
        cuerpo=cuerpo,
        tipos=tipos,
        fila_de_datos=_compilar_fila(cuerpo, codificacion, formato),
        reloj=bruto.get("reloj", {}),
    )


# --------------------------------------------------------------------------- #
# Cabecera
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Cabecera:
    """Resultado del parseo de la cabecera."""

    formato: str
    version: str
    """Versión declarada, o `""` en un formato que no versiona su cabecera."""
    metadatos: dict[str, str]
    canales: tuple[Canal, ...]
    offset_datos: int
    """Byte donde empieza la primera fila de datos, relativo a los bytes que se
    pasaron a `parsear_cabecera` (BOM incluido si lo había). Es decir:
    `datos[cab.offset_datos:]` empieza siempre en la primera fila. Lo usa el
    parseo del cuerpo para saltarse la cabecera sin volver a recorrerla."""
    avisos: list[Aviso] = field(default_factory=list)
    delimitador: str = DELIMITADOR_POR_OMISION
    """El de `[cuerpo].delimitador` del descriptor. Viaja en la `Cabecera` porque
    es lo que el parseo del cuerpo (`cuerpo.py`, `limpieza.py`) necesita saber y
    ya recibe la `Cabecera`: así no hay una segunda vía por la que enterarse."""

    @property
    def n_canales(self) -> int:
        return len(self.canales)

    @property
    def n_columnas(self) -> int:
        """Columnas esperadas por fila: la marca de tiempo más los canales."""
        return len(self.canales) + 1

    def por_id(self, id_: int) -> Canal | None:
        return next((c for c in self.canales if c.id == id_), None)

    def por_nombre(self, nombre: str) -> Canal | None:
        return next((c for c in self.canales if c.nombre == nombre), None)


def sondear_formato(cabecera: bytes, descriptores: tuple[Descriptor, ...]) -> Descriptor | None:
    """Devuelve el descriptor cuyo formato reconoce estos bytes, o `None`.

    Tolera el BOM UTF-8 y los tres finales de línea. `None` significa que hay que
    ir por el camino de CSV genérico (fase FG), no que el fichero esté mal.
    """
    datos = cabecera[len(BOM_UTF8) :] if cabecera.startswith(BOM_UTF8) else cabecera
    for d in descriptores:
        if datos.startswith(d.firma):
            return d
    return None


def _dividir_lineas(datos: bytes) -> list[tuple[int, bytes, int]]:
    """(offset_de_inicio, contenido_sin_salto, numero_de_linea_1_based).

    Se hace a mano en lugar de con `splitlines()` porque hace falta el offset en
    bytes de cada línea para poder devolver `offset_datos`, y porque hay que
    aceptar CRLF, LF y mixto sin normalizar el fichero en memoria (docs/01 §1.13).
    """
    salida: list[tuple[int, bytes, int]] = []
    inicio = 0
    n = 1
    total = len(datos)
    while inicio <= total:
        fin = datos.find(b"\n", inicio)
        if fin == -1:
            # Última línea sin salto final: es un caso válido (docs/01 §1.13).
            if inicio < total:
                salida.append((inicio, datos[inicio:].rstrip(b"\r"), n))
            break
        salida.append((inicio, datos[inicio:fin].rstrip(b"\r"), n))
        inicio = fin + 1
        n += 1
    return salida


def parsear_cabecera(datos: bytes, descriptor: Descriptor) -> Cabecera:
    """Parsea la cabecera de `datos` (los primeros bytes del fichero bastan).

    Lanza `ErrorDeFormato` si la cabecera está incompleta o la versión no está
    soportada. Cualquier otra anomalía va a `Cabecera.avisos`.
    """
    gram = descriptor.cabecera

    # No es un aviso: un BOM es legítimo y el usuario no puede hacer nada con esa
    # información (samples/corrupt/README.md, caso 05). Se descuenta para
    # parsear, pero `offset_datos` se devuelve relativo a los bytes que ha
    # recibido esta función, BOM incluido, para que quien llame pueda hacer
    # `datos[cab.offset_datos:]` sin acordarse del BOM. La alternativa era una
    # API que obliga a recordarlo, y eso es un fallo esperando a ocurrir.
    desplazamiento_bom = len(BOM_UTF8) if datos.startswith(BOM_UTF8) else 0
    datos = datos[desplazamiento_bom:]

    if not datos.startswith(descriptor.firma):
        raise ErrorDeFormato(
            f"el fichero no empieza por la firma "
            f"{descriptor.firma.decode(descriptor.codificacion, errors='replace')!r} del "
            f"formato {descriptor.formato}"
        )

    avisos: list[Aviso] = []
    metadatos: dict[str, str] = {}
    canales: list[Canal] = []
    bloque: dict[str, str] | None = None
    nombre_bloque: str | None = None
    linea_bloque = 0
    offset_datos: int | None = None
    version: str | None = None

    def cerrar_bloque(linea_actual: int) -> None:
        nonlocal bloque, nombre_bloque
        if bloque is None or nombre_bloque is None:
            return
        faltan = [k for k in gram.claves_obligatorias if k not in bloque]
        if faltan:
            # Sin identidad o sin tipo no se puede saber qué columna es qué canal
            # ni con qué escala leerla: seguir daría datos silenciosamente mal
            # atribuidos. Es el caso 01 del corpus de corruptos.
            raise ErrorDeFormato(
                f"bloque de canal incompleto en la línea {linea_bloque}: "
                f"'{nombre_bloque}' no declara {', '.join(faltan)}. "
                "La cabecera parece truncada."
            )
        dm, dn = _rango_declarado(gram, bloque, nombre_bloque, linea_bloque, avisos)

        tipo = bloque[gram.clave_tipo]
        dimension, a, confianza = descriptor.resuelve(tipo)
        if dimension is None:
            avisos.append(
                Aviso(
                    "tipo_desconocido",
                    f"'{nombre_bloque}': el tipo '{tipo}' no está en el descriptor "
                    f"{descriptor.formato}; el canal se muestra en crudo, sin unidad",
                    linea_bloque,
                )
            )
        elif confianza == "unknown":
            avisos.append(
                Aviso(
                    "escala_sin_confirmar",
                    f"'{nombre_bloque}': la escala del tipo '{tipo}' no está "
                    "confirmada; el canal se muestra en crudo, sin unidad",
                    linea_bloque,
                )
            )

        try:
            id_ = int(bloque[gram.clave_identidad])
        except ValueError:
            raise ErrorDeFormato(
                f"bloque de canal en la línea {linea_bloque}: {gram.clave_identidad} no "
                f"numérico ({bloque[gram.clave_identidad]!r})"
            ) from None

        canales.append(
            Canal(
                orden=len(canales),
                nombre=nombre_bloque,
                id=id_,
                tipo=tipo,
                display_max=dm,
                display_min=dn,
                dimension=dimension,
                a_canonica=a,
                confianza=confianza,
            )
        )
        bloque = None
        nombre_bloque = None

    for offset, linea, n in _dividir_lineas(datos):
        if descriptor.fila_de_datos.match(linea):
            offset_datos = offset
            break

        texto = linea.decode(descriptor.codificacion, errors="replace")
        if gram.separador_clave_valor not in texto:
            continue
        clave, _, valor = texto.partition(gram.separador_clave_valor)
        clave, valor = clave.strip(), valor.strip()

        if clave == gram.clave_canal:
            cerrar_bloque(n)
            bloque = {}
            nombre_bloque = valor
            linea_bloque = n
        elif bloque is not None and clave in gram.claves_bloque:
            bloque[clave] = valor
        else:
            # Metadato global o de cierre. Si aparece uno mientras hay un bloque
            # abierto, el bloque termina ahí.
            if bloque is not None:
                cerrar_bloque(n)
            metadatos[clave] = valor
            if clave == gram.clave_version:
                version = valor

    # Un bloque abierto al final de los datos disponibles: si no hemos llegado a
    # las filas, la cabecera está truncada.
    if bloque is not None:
        cerrar_bloque(len(datos))

    if gram.clave_version is not None:
        if version is None:
            raise ErrorDeFormato(f"la cabecera no declara {gram.clave_version}")
        if version not in descriptor.versiones_soportadas:
            # Rechazo explícito, no intento de leerlo: la gramática podría haber
            # cambiado y el resultado sería silenciosamente equivocado
            # (docs/01 §1.1, caso 10 del corpus de corruptos).
            raise ErrorDeFormato(
                f"{gram.clave_version} {version!r} no soportada por el descriptor "
                f"{descriptor.formato} (soportadas: "
                f"{', '.join(sorted(descriptor.versiones_soportadas))})"
            )
    if not canales:
        raise ErrorDeFormato("la cabecera no declara ningún canal")
    if offset_datos is None:
        raise ErrorDeFormato(
            "no se ha encontrado ninguna fila de datos: la cabecera parece truncada"
        )

    # Los nombres duplicados no los prohíbe el formato, así que se avisa y se
    # sigue: la identidad interna es el ID (docs/01 §1.3).
    vistos: dict[str, int] = {}
    for c in canales:
        if c.nombre in vistos:
            avisos.append(
                Aviso(
                    "nombre_duplicado",
                    f"el nombre '{c.nombre}' aparece en los canales {vistos[c.nombre]} "
                    f"y {c.orden}; la identidad es el ID, no el nombre",
                )
            )
        vistos[c.nombre] = c.orden

    ids: dict[int, int] = {}
    for c in canales:
        if c.id in ids:
            avisos.append(
                Aviso(
                    "id_duplicado",
                    f"el ID {c.id} aparece en los canales {ids[c.id]} y {c.orden}; "
                    "el emparejamiento entre logs será ambiguo",
                )
            )
        ids[c.id] = c.orden

    return Cabecera(
        formato=descriptor.formato,
        version=version if version is not None else "",
        metadatos=metadatos,
        canales=tuple(canales),
        offset_datos=offset_datos + desplazamiento_bom,
        avisos=avisos,
        delimitador=descriptor.cuerpo.delimitador,
    )


def _rango_declarado(
    gram: GramaticaCabecera,
    bloque: Mapping[str, str],
    nombre_bloque: str,
    linea_bloque: int,
    avisos: list[Aviso],
) -> tuple[int | None, int | None]:
    """(máximo, mínimo) del rango declarado del canal, o `(None, None)`.

    Su ausencia es legal y no genera aviso: 13 de los 475 canales del AutoLog
    real no la traen (docs/01 §1.3). Lo que sí avisa es un rango presente e
    ilegible, porque ahí sí se pierde información que el fichero traía.

    El código del aviso, `displaymaxmin_invalida`, conserva el nombre de la clave
    de Haltech aunque el motor ya no la cite: los códigos son un protocolo
    estable —`informe_importacion._SEVERIDAD_POR_CODIGO` los clasifica uno a uno—
    y renombrarlo cambiaría en silencio la severidad del aviso. El MENSAJE sí
    nombra la clave del formato que se esté leyendo.
    """
    if gram.clave_rango is None or gram.clave_rango not in bloque:
        return None, None
    crudo = bloque[gram.clave_rango]
    partes = crudo.split(gram.rango_separador)
    if len(partes) != 2:
        avisos.append(
            Aviso(
                "displaymaxmin_invalida",
                f"'{nombre_bloque}': {gram.clave_rango} mal formada ({crudo!r}); se ignora",
                linea_bloque,
            )
        )
        return None, None
    try:
        primero, segundo = int(partes[0]), int(partes[1])
    except ValueError:
        avisos.append(
            Aviso(
                "displaymaxmin_invalida",
                f"'{nombre_bloque}': {gram.clave_rango} no numérica ({crudo!r}); se ignora",
                linea_bloque,
            )
        )
        return None, None
    return (primero, segundo) if gram.rango_orden[0] == "max" else (segundo, primero)
