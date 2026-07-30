"""Parser de cabecera del formato Haltech NSP `%DataLog% 1.1` (tarea F1-01).

Dirigido por el descriptor `data/formats/haltech_nsp.toml` (F0-09): la gramática
de la cabecera está aquí, pero las escalas y las dimensiones **no**. Son datos
versionados (ADR-008), así que añadir un tipo o corregir un factor no toca este
fichero.

Especificación: `docs/01-formato-log.md` §1.1 a §1.5 y la lista de verificación
de §1.13. El comportamiento esperado ante cada anomalía está en
`samples/corrupt/README.md`, que es la especificación ejecutable de este módulo.

QUÉ ES UN ERROR Y QUÉ ES UN AVISO
=================================
La regla, de `docs/02` §2.5 (E1.7): el parser **avisa y sigue** siempre que pueda
producir datos utilizables, y **rechaza** solo cuando seguir daría resultados
silenciosamente equivocados.

    Rechaza  cabecera incompleta (no se puede saber qué columna es qué canal)
             versión mayor desconocida (la gramática podría haber cambiado)
    Avisa    tipo desconocido, fila con número de campos distinto, marcas no
             monótonas, escala sin confirmar

Como el resto de `dlv-core`, este módulo no abre ficheros: recibe los bytes.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import IO, Any

FIRMA = b"%DataLog%"
BOM_UTF8 = b"\xef\xbb\xbf"

# Marca de tiempo de una fila de datos: HH:MM:SS.mmm seguida de coma.
_RE_FILA = re.compile(rb"^\d\d:\d\d:\d\d\.\d\d\d,")

# Claves que forman un bloque de canal. `DisplayMaxMin` es opcional: 13 de los
# 475 canales del AutoLog real no la traen (docs/01 §1.3).
_CLAVES_BLOQUE = ("ID", "Type", "DisplayMaxMin")
_OBLIGATORIAS = ("ID", "Type")


class ErrorDeFormato(ValueError):
    """El fichero no se puede leer sin arriesgar resultados equivocados."""


@dataclass(slots=True, frozen=True)
class Aviso:
    """Anomalía que no impide cargar. Va al informe de importación (E1.7)."""

    codigo: str
    mensaje: str
    linea: int | None = None

    def __str__(self) -> str:
        donde = f" (línea {self.linea})" if self.linea is not None else ""
        return f"[{self.codigo}]{donde} {self.mensaje}"


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
class Descriptor:
    """`data/formats/<formato>.toml` en memoria (F0-09)."""

    formato: str
    firma: bytes
    versiones_soportadas: frozenset[str]
    clave_canal: str
    claves_opcionales: frozenset[str]
    tipos: Mapping[str, Mapping[str, Any]]

    def resuelve(self, tipo: str) -> tuple[str | None, float, str]:
        """(dimension, a_canonica, confianza) para un `Type` de la cabecera."""
        t = self.tipos.get(tipo)
        if t is None:
            return None, 1.0, "unknown"
        return str(t["dimension"]), float(t["a_canonica"]), str(t["confianza"])


def cargar_descriptor(fuente: IO[bytes]) -> Descriptor:
    """Carga un descriptor de formato nativo desde su TOML ya abierto."""
    bruto = tomllib.load(fuente)
    meta = bruto["meta"]
    det = bruto["deteccion"]
    cab = bruto.get("cabecera", {})
    return Descriptor(
        formato=str(meta["formato"]),
        firma=str(det["primera_linea"]).encode("utf-8"),
        versiones_soportadas=frozenset(str(v) for v in det["version_soportada"]),
        clave_canal=str(cab.get("clave_canal", "Channel")),
        claves_opcionales=frozenset(str(k) for k in cab.get("claves_opcionales", ())),
        tipos=bruto["tipos"],
    )


@dataclass(slots=True)
class Cabecera:
    """Resultado del parseo de la cabecera."""

    formato: str
    version: str
    metadatos: dict[str, str]
    canales: tuple[Canal, ...]
    offset_datos: int
    """Byte donde empieza la primera fila de datos, relativo a los bytes que se
    pasaron a `parsear_cabecera` (BOM incluido si lo había). Es decir:
    `datos[cab.offset_datos:]` empieza siempre en la primera fila. Lo usa el
    parseo del cuerpo para saltarse la cabecera sin volver a recorrerla."""
    avisos: list[Aviso] = field(default_factory=list)

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
            f"el fichero no empieza por la firma {descriptor.firma.decode()!r} del "
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
        faltan = [k for k in _OBLIGATORIAS if k not in bloque]
        if faltan:
            # Sin ID o sin Type no se puede saber qué columna es qué canal ni
            # con qué escala leerla: seguir daría datos silenciosamente mal
            # atribuidos. Es el caso 01 del corpus de corruptos.
            raise ErrorDeFormato(
                f"bloque de canal incompleto en la línea {linea_bloque}: "
                f"'{nombre_bloque}' no declara {', '.join(faltan)}. "
                "La cabecera parece truncada."
            )
        dm = dn = None
        if "DisplayMaxMin" in bloque:
            partes = bloque["DisplayMaxMin"].split(",")
            if len(partes) == 2:
                try:
                    dm, dn = int(partes[0]), int(partes[1])
                except ValueError:
                    avisos.append(
                        Aviso(
                            "displaymaxmin_invalida",
                            f"'{nombre_bloque}': DisplayMaxMin no numérica "
                            f"({bloque['DisplayMaxMin']!r}); se ignora",
                            linea_bloque,
                        )
                    )
            else:
                avisos.append(
                    Aviso(
                        "displaymaxmin_invalida",
                        f"'{nombre_bloque}': DisplayMaxMin mal formada "
                        f"({bloque['DisplayMaxMin']!r}); se ignora",
                        linea_bloque,
                    )
                )

        tipo = bloque["Type"]
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
            id_ = int(bloque["ID"])
        except ValueError:
            raise ErrorDeFormato(
                f"bloque de canal en la línea {linea_bloque}: ID no numérico ({bloque['ID']!r})"
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
        if _RE_FILA.match(linea):
            offset_datos = offset
            break

        texto = linea.decode("utf-8", errors="replace")
        if ":" not in texto:
            continue
        clave, _, valor = texto.partition(":")
        clave, valor = clave.strip(), valor.strip()

        if clave == descriptor.clave_canal:
            cerrar_bloque(n)
            bloque = {}
            nombre_bloque = valor
            linea_bloque = n
        elif bloque is not None and clave in _CLAVES_BLOQUE:
            bloque[clave] = valor
        else:
            # Metadato global o de cierre. Si aparece uno mientras hay un bloque
            # abierto, el bloque termina ahí.
            if bloque is not None:
                cerrar_bloque(n)
            metadatos[clave] = valor
            if clave == "DataLogVersion":
                version = valor

    # Un bloque abierto al final de los datos disponibles: si no hemos llegado a
    # las filas, la cabecera está truncada.
    if bloque is not None:
        cerrar_bloque(len(datos))

    if version is None:
        raise ErrorDeFormato("la cabecera no declara DataLogVersion")
    if version not in descriptor.versiones_soportadas:
        # Rechazo explícito, no intento de leerlo: la gramática podría haber
        # cambiado y el resultado sería silenciosamente equivocado
        # (docs/01 §1.1, caso 10 del corpus de corruptos).
        raise ErrorDeFormato(
            f"DataLogVersion {version!r} no soportada por el descriptor "
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
        version=version,
        metadatos=metadatos,
        canales=tuple(canales),
        offset_datos=offset_datos + desplazamiento_bom,
        avisos=avisos,
    )
