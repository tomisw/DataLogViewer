"""Perfil de importación `.dlvimport`, con huella de cabecera y reaplicación
parcial (FG-12).

`docs/07-formatos-y-csv-generico.md` §7.9: cuando el usuario corrige a mano lo
que el sondeo de un CSV genérico dedujo mal —el delimitador, la columna de
tiempo, la unidad de un canal, un rol difuso—, ese trabajo tiene que
sobrevivir a la siguiente importación del mismo origen. Este módulo es la
huella que decide «¿este perfil corresponde a este fichero?» y la mecánica de
reaplicación que decide, columna a columna, qué se hereda y qué se vuelve a
deducir.

LA HUELLA IDENTIFICA UN FORMATO, NO UN FICHERO
================================================
`dlv_core.huella` (F1-11/FE-01, ADR-005) ya resuelve «¿sigue siendo válido este
`.dlvcache`?» con ruta + tamaño + mtime: esa huella identifica UN FICHERO
concreto, y cambia con cada log nuevo aunque venga de la misma ECU. Un perfil
de importación necesita lo contrario: sobrevivir a que el fichero de la semana
que viene traiga otra fecha, otro número de sesión y otro tamaño, y seguir
reconociendo que es «el mismo Haltech configurado igual». Por eso `HuellaCabecera`
no lleva ni ruta ni tamaño ni mtime — lleva exactamente lo que la tarea pide:
los NOMBRES de columna normalizados y su ORDEN, el DELIMITADOR y la
CODIFICACIÓN. Esos cuatro son el contrato de un exportador: cambian cuando
cambia la configuración de exportación (otro perfil de MoTeC i2, otra versión
del firmware que añade una columna), no cuando cambia el contenido del log.

Lo que la huella deliberadamente NO mira: el nombre de fichero, la fecha, el
tamaño, el número de muestras, los VALORES de ninguna columna. Un perfil que
mirara alguno de esos dejaría de reaplicarse la segunda semana (si mira
fecha/nombre) o se reaplicaría a un fichero de otro coche con las mismas
columnas por casualidad y datos completamente distintos (si no mirara nada) —
los dos fallos que describe el encargo de la tarea.

COINCIDENCIA TOTAL, PARCIAL O NINGUNA
=======================================
`reaplicar_perfil` distingue tres resultados, y la frontera entre "parcial" y
"ninguna" es la que de verdad importa (un perfil que se reaplica al fichero
equivocado es peor que no tener perfiles, dice el encargo):

- **`"total"`**: la huella actual coincide EXACTAMENTE con la guardada — mismos
  nombres, mismo orden, mismo delimitador, misma codificación — y todas las
  columnas del perfil siguen presentes. Es el «doble clic» de §7.9: nada queda
  pendiente.
- **`"parcial"`**: el delimitador y la codificación coinciden (mismo
  exportador) y AL MENOS UNA columna del perfil aparece en el fichero nuevo,
  por nombre normalizado, en cualquier posición. Se reaplica lo que coincide;
  las columnas nuevas del fichero quedan en `columnas_nuevas_sin_decidir`
  —visibles, no adivinadas— y las columnas del perfil que ya no aparecen se
  listan en `avisos`.
- **`"ninguna"`**: el delimitador o la codificación difieren (es casi
  seguramente otro exportador, no una reconfiguración del mismo), o ninguna
  columna del perfil aparece en el fichero nuevo. No se reaplica nada en
  absoluto y `motivo` dice por qué, en prosa, para enseñárselo al usuario en
  vez de fallar en silencio con las unidades de otra ECU.

CADA CAMPO SE REAPLICA POR SU CUENTA, SEGÚN QUIÉN LO DECIDIÓ
================================================================
`dlv-ui/src/importacion/tipos.ts` define `Campo<T>` con `origen: "deducido" |
"confirmado"`, y ese matiz —no la forma de pintar una tabla— es lo que hace
que guardar un perfil merezca la pena: **lo que el usuario confirmó sobrevive
a la reaplicación; lo que solo se dedujo se vuelve a deducir**. `Campo` es el
mismo tipo aquí, y `_fusionar_campo` es la única función que decide esa
frontera: si `guardado.origen == "confirmado"`, su valor gana; si no, se
descarta y se conserva el valor recién deducido del fichero nuevo. Sin esta
distinción, un perfil sería indistinguible de "recordar la primera
propuesta del sondeo para siempre", que es exactamente el error que arrastra
una deducción mala de la primera importación a todas las siguientes.

Los roles siguen la misma regla con su propio vocabulario (`RolDeCanal.
confirmado`, espejo de `RolPropuesto.confirmado` / `Asignacion.
requiere_confirmacion` de `dlv_core.roles`): un rol `DIFUSA` sin confirmar en
el perfil no se reaplica — se vuelve a deducir sobre el fichero nuevo, tal
como manda §7.15 mitigación 4 (los detectores críticos no se fían de una
corazonada, ni la de hoy ni la de la semana pasada).

LA COLUMNA DE TIEMPO SE BUSCA POR NOMBRE, NO POR ÍNDICE
==========================================================
`docs/07` §7.9 guarda `[time] column = 0`, un índice puro. Es fràgil frente a
lo que la propia tarea pide soportar: "columnas añadidas o reordenadas". Si el
fichero nuevo tiene una columna más delante de la de tiempo, el índice 0 ya no
apunta a lo mismo y el perfil reaplicaría silenciosamente el eje equivocado —
el fallo más caro de todos, porque no se ve en ninguna tabla de avisos, se ve
en que las curvas no cuadran. Por eso `TiempoImportado` guarda ADEMÁS el
`nombre_columna`/`nombre_columna_fecha` en el momento de confirmar, y
`_fusionar_columna_tiempo` busca ese nombre en el fichero nuevo antes de
reaplicar el índice; si ya no está, no se inventa un índice y se avisa
explícitamente en vez de reaplicar una columna equivocada sin decirlo.

ADR-002: NADA DE E/S AQUÍ
===========================
Este módulo no abre ningún fichero. `PerfilImportacion.a_texto_toml()` /
`.desde_texto_toml()` trabajan sobre texto ya en memoria: quien lee/escribe el
`.dlvimport` de disco es `dlv-api` (regla 2 de la tarea). `.a_dict()` /
`.desde_dict()` son la forma intermedia sin ningún formato de fichero de por
medio, útil para pruebas y para quien prefiera JSON en tránsito.

`.dlvimport` ES TOML, NO JSON, Y ESO ES DELIBERADO
=====================================================
`docs/03-arquitectura.md` §3.9 declara `.dlvimport` "TOML versionado", a
diferencia de `.dlvproj`/`.dlvprofile` (JSON versionado): es justo el fichero
que la regla 5 de la tarea espera que un usuario pueda abrir y tocar a mano
—corregir un rol, arreglar un delimitador— sin herramientas, igual que ya
puede editar `data/roles.toml`. `tomllib` (stdlib) solo LEE TOML; escribirlo
sin añadir una dependencia (regla 6) exige un volcador propio. `_volcar_toml`
es exactamente eso y nada más: no es una biblioteca TOML de propósito
general, es un serializador de la forma FIJA y conocida que produce
`PerfilImportacion.a_dict()` (escalares, tablas de un nivel, tablas en línea
para los `Campo`/`RolDeCanal`, una tabla de arrays para los canales). Cualquier
otra forma de `dict` que se le pase puede no serializar correctamente, y por
eso no se exporta como API pública de propósito general.

CLAVES EN ESPAÑOL, NO EL INGLÉS DEL EJEMPLO DE `docs/07` §7.9
=================================================================
El ejemplo de §7.9 escribe `name`, `delimiter`, `column`, `role`... en
inglés. Es un boceto de cuando `docs/07` se escribió, anterior a `roles.toml`,
`units.toml` y al resto del catálogo de datos del proyecto, que usan claves en
español (`dimension`, `plausible`, `sinonimos`...) porque CLAUDE.md fija el
idioma del proyecto. Este módulo seguiría siendo TOML, hoja de §3.9, con las
claves de `roles.toml` y no las del boceto de §7.9: `nombre`, `delimitador`,
`columna`, `rol`. Queda anotado aquí porque es una desviación deliberada del
literal del documento, no un descuido.

Solo biblioteca estándar (`hashlib`, `json` para escapar cadenas TOML,
`tomllib` para leerlas, `dataclasses`, `typing`).
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Generic, Literal, TypeVar, cast

from dlv_core.roles import normalizar

__all__ = [
    "VERSION_ESQUEMA_PERFIL_IMPORTACION",
    "Campo",
    "CanalImportado",
    "ErrorDePerfilImportacion",
    "ErrorDeVersionDePerfilDesconocida",
    "FormatoImportado",
    "HuellaCabecera",
    "Origen",
    "PerfilImportacion",
    "ResultadoReaplicacion",
    "ResumenHuella",
    "RolDeCanal",
    "TiempoImportado",
    "TipoCoincidencia",
    "construir_huella",
    "crear_perfil",
    "reaplicar_perfil",
]

VERSION_ESQUEMA_PERFIL_IMPORTACION = 1
"""Versión del bloque completo de `PerfilImportacion.a_dict()`. Sube solo si
cambia la FORMA (clave renombrada o movida), no por añadir un campo opcional
nuevo con valor por omisión. Mismo criterio que `VERSION_ESQUEMA_EMPAREJAMIENTOS`
de `dlv_core.proyecto`: una versión desconocida se rechaza entera en vez de
leerse a medias (`ErrorDeVersionDePerfilDesconocida`)."""

Origen = Literal["deducido", "confirmado"]
_ORIGENES: tuple[Origen, ...] = ("deducido", "confirmado")

_T = TypeVar("_T")


class ErrorDePerfilImportacion(ValueError):
    """Un `.dlvimport` que no se puede leer sin que una persona lo corrija:
    falta una clave, un tipo no es el esperado, o el `[huella]`/`[[canales]]`
    no tiene forma de tabla. Regla 5 de la tarea: un perfil es una entrada NO
    CONFIABLE —lo escribe el programa, pero el usuario puede tocarlo a mano y
    puede venir de otro sitio— así que se rechaza con un mensaje que diga QUÉ,
    nunca con un `KeyError`/`TypeError` desnudo."""


class ErrorDeVersionDePerfilDesconocida(ErrorDePerfilImportacion):
    """`version_esquema` no es la que este `dlv-core` sabe leer. Deliberadamente
    no se intenta "leer lo que se pueda": mismo motivo que
    `dlv_core.proyecto.ErrorDeVersionDesconocida`."""


# --------------------------------------------------------------------------- #
# `Campo<T>`: el mismo tipo que `tipos.ts`, para que la distinción
# deducido/confirmado no se pierda al cruzar de TypeScript a Python.
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class Campo(Generic[_T]):  # noqa: UP046 — no PEP 695: ver piramide.py:318 en docs/09 §9 (SyntaxError)
    """Un valor con quién lo decidió. Espejo exacto de `Campo<T>` en
    `dlv-ui/src/importacion/tipos.ts`: el asistente lo produce con
    `origen: "deducido"` para toda propuesta del sondeo, y `"confirmado"`
    solo cuando una persona lo toca (o lo acepta explícitamente)."""

    valor: _T
    origen: Origen


def _campo_a_dict(campo: Campo[object]) -> dict[str, object]:
    """`{origen, valor}`, con `valor` OMITIDO si es `None`.

    La omisión (no un `null`/centinela) es la representación de "sin valor"
    en TOML, que no tiene `null`. Como el escritor y el lector de este módulo
    son la única pareja que produce y consume esta forma, la ausencia de
    'valor' se interpreta sin ambigüedad como `None` en `_campo_*` de lectura.
    """
    bruto: dict[str, object] = {"origen": campo.origen}
    if campo.valor is not None:
        bruto["valor"] = campo.valor
    return bruto


def _origen_desde_bruto(bruto: Mapping[str, object], *, contexto: str) -> Origen:
    origen = bruto.get("origen")
    if origen not in _ORIGENES:
        raise ErrorDePerfilImportacion(
            f"{contexto}: 'origen' debe ser 'deducido' o 'confirmado' y aquí es {origen!r}"
        )
    return cast(Origen, origen)


def _campo_str(bruto: Mapping[str, object], *, contexto: str) -> Campo[str]:
    origen = _origen_desde_bruto(bruto, contexto=contexto)
    valor = bruto.get("valor")
    if not isinstance(valor, str):
        raise ErrorDePerfilImportacion(f"{contexto}: 'valor' debe ser texto y aquí es {valor!r}")
    return Campo(valor=valor, origen=origen)


def _campo_str_o_none(bruto: Mapping[str, object], *, contexto: str) -> Campo[str | None]:
    origen = _origen_desde_bruto(bruto, contexto=contexto)
    valor = bruto.get("valor")
    if valor is not None and not isinstance(valor, str):
        raise ErrorDePerfilImportacion(
            f"{contexto}: 'valor' debe ser texto o estar ausente, y aquí es {valor!r}"
        )
    return Campo(valor=valor, origen=origen)


def _campo_int(bruto: Mapping[str, object], *, contexto: str) -> Campo[int]:
    origen = _origen_desde_bruto(bruto, contexto=contexto)
    valor = bruto.get("valor")
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErrorDePerfilImportacion(
            f"{contexto}: 'valor' debe ser un entero y aquí es {valor!r}"
        )
    return Campo(valor=valor, origen=origen)


def _campo_int_o_none(bruto: Mapping[str, object], *, contexto: str) -> Campo[int | None]:
    origen = _origen_desde_bruto(bruto, contexto=contexto)
    valor = bruto.get("valor")
    if valor is not None and (isinstance(valor, bool) or not isinstance(valor, int)):
        raise ErrorDePerfilImportacion(
            f"{contexto}: 'valor' debe ser un entero o estar ausente, y aquí es {valor!r}"
        )
    return Campo(valor=valor, origen=origen)


def _campo_float_o_none(bruto: Mapping[str, object], *, contexto: str) -> Campo[float | None]:
    origen = _origen_desde_bruto(bruto, contexto=contexto)
    valor = bruto.get("valor")
    if valor is None:
        return Campo(valor=None, origen=origen)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorDePerfilImportacion(
            f"{contexto}: 'valor' debe ser un número o estar ausente, y aquí es {valor!r}"
        )
    return Campo(valor=float(valor), origen=origen)


def _tabla(bruto: Mapping[str, object], clave: str, *, contexto: str) -> Mapping[str, object]:
    valor = bruto.get(clave)
    if not isinstance(valor, Mapping):
        raise ErrorDePerfilImportacion(f"{contexto}: falta '{clave}' (o no es una tabla)")
    return valor


# --------------------------------------------------------------------------- #
# Rol asignado a un canal: espejo de `RolPropuesto` (`tipos.ts`) /
# `Asignacion` (`dlv_core.roles`).
# --------------------------------------------------------------------------- #
_CONFIANZAS: tuple[str, ...] = ("EXACTA", "INDEXADA", "DIFUSA")


@dataclass(slots=True, frozen=True)
class RolDeCanal:
    """El rol asignado a un canal del perfil, con la confianza que lo
    respalda. `confirmado` juega aquí el mismo papel que `origen` en `Campo`:
    es la marca que decide si sobrevive a la reaplicación (§7.15 mitigación
    4) — se guarda aparte y no como un `Campo[str]` genérico por el mismo
    motivo que da `tipos.ts`: una `DIFUSA` sin confirmar además desactiva
    detectores críticos aguas abajo, un matiz que un `Campo` cualquiera no
    transporta."""

    rol: str
    confianza: str
    """`"EXACTA" | "INDEXADA" | "DIFUSA"`, el mismo vocabulario en mayúsculas
    que `Confianza.name` en `dlv_core.roles` y que `RolPropuesto.confianza`
    en `tipos.ts`."""
    sinonimo: str
    indice: int | None
    parecido: float
    confirmado: bool


def _rol_a_dict(rol: RolDeCanal | None) -> dict[str, object] | None:
    if rol is None:
        return None
    bruto: dict[str, object] = {
        "rol": rol.rol,
        "confianza": rol.confianza,
        "sinonimo": rol.sinonimo,
        "parecido": rol.parecido,
        "confirmado": rol.confirmado,
    }
    if rol.indice is not None:
        bruto["indice"] = rol.indice
    return bruto


def _rol_desde_dict(bruto: Mapping[str, object] | None, *, contexto: str) -> RolDeCanal | None:
    if bruto is None:
        return None
    try:
        rol = bruto["rol"]
        confianza = bruto["confianza"]
        sinonimo = bruto["sinonimo"]
        parecido = bruto["parecido"]
        confirmado = bruto["confirmado"]
    except KeyError as exc:
        raise ErrorDePerfilImportacion(f"{contexto}: falta la clave {exc} en el rol") from None
    if not isinstance(rol, str) or not rol:
        raise ErrorDePerfilImportacion(f"{contexto}: 'rol' debe ser texto no vacío")
    if not isinstance(confianza, str) or confianza not in _CONFIANZAS:
        raise ErrorDePerfilImportacion(
            f"{contexto}: 'confianza' debe ser una de {_CONFIANZAS} y aquí es {confianza!r}"
        )
    if not isinstance(sinonimo, str):
        raise ErrorDePerfilImportacion(f"{contexto}: 'sinonimo' debe ser texto")
    if isinstance(parecido, bool) or not isinstance(parecido, (int, float)):
        raise ErrorDePerfilImportacion(f"{contexto}: 'parecido' debe ser un número")
    if not isinstance(confirmado, bool):
        raise ErrorDePerfilImportacion(f"{contexto}: 'confirmado' debe ser verdadero/falso")
    indice_bruto = bruto.get("indice")
    if indice_bruto is not None and (
        isinstance(indice_bruto, bool) or not isinstance(indice_bruto, int)
    ):
        raise ErrorDePerfilImportacion(f"{contexto}: 'indice' debe ser un entero o estar ausente")
    return RolDeCanal(
        rol=rol,
        confianza=confianza,
        sinonimo=sinonimo,
        indice=indice_bruto,
        parecido=float(parecido),
        confirmado=confirmado,
    )


# --------------------------------------------------------------------------- #
# Un canal del perfil
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class CanalImportado:
    """Un canal, tal como lo dejó el asistente (paso 3, `CanalPropuesto` en
    `tipos.ts`) o tal como aparece en un sondeo nuevo.

    `nombre` es la CLAVE de emparejamiento entre perfil y fichero nuevo —
    normalizado con `dlv_core.roles.normalizar`, igual que el catálogo de
    roles empareja sinónimos (§7.7): así "RPM" y "rpm" o "Régimen Motor" y
    "regimen motor" son la misma columna a efectos de reaplicación, sin
    inventar una segunda función de normalización que pudiera divergir de la
    que ya usa `asignar_rol`.

    `columna` es solo informativo (qué índice tenía al guardar el perfil, útil
    para quien lo lee a mano); la reaplicación NUNCA lo usa para emparejar,
    precisamente porque las columnas se pueden reordenar (ver cabecera del
    módulo)."""

    nombre: str
    columna: int | None
    dimension_id: Campo[str]
    unidad_origen: Campo[str | None]
    rol: RolDeCanal | None


def _canal_a_dict(canal: CanalImportado) -> dict[str, object]:
    bruto: dict[str, object] = {
        "nombre": canal.nombre,
        "dimension": _campo_a_dict(cast(Campo[object], canal.dimension_id)),
        "unidad_origen": _campo_a_dict(cast(Campo[object], canal.unidad_origen)),
    }
    if canal.columna is not None:
        bruto["columna"] = canal.columna
    rol = _rol_a_dict(canal.rol)
    if rol is not None:
        bruto["rol"] = rol
    return bruto


def _canal_desde_dict(bruto: Mapping[str, object], *, indice: int) -> CanalImportado:
    contexto = f"canales[{indice}]"
    nombre = bruto.get("nombre")
    if not isinstance(nombre, str) or not nombre:
        raise ErrorDePerfilImportacion(f"{contexto}: 'nombre' debe ser texto no vacío")
    columna = bruto.get("columna")
    if columna is not None and (isinstance(columna, bool) or not isinstance(columna, int)):
        raise ErrorDePerfilImportacion(f"{contexto}: 'columna' debe ser un entero o estar ausente")
    rol_bruto = bruto.get("rol")
    if rol_bruto is not None and not isinstance(rol_bruto, Mapping):
        raise ErrorDePerfilImportacion(f"{contexto}: 'rol' debe ser una tabla o estar ausente")
    return CanalImportado(
        nombre=nombre,
        columna=columna,
        dimension_id=_campo_str(
            _tabla(bruto, "dimension", contexto=contexto), contexto=f"{contexto}.dimension"
        ),
        unidad_origen=_campo_str_o_none(
            _tabla(bruto, "unidad_origen", contexto=contexto), contexto=f"{contexto}.unidad_origen"
        ),
        rol=_rol_desde_dict(rol_bruto, contexto=f"{contexto}.rol"),
    )


# --------------------------------------------------------------------------- #
# Formato (paso 1) y tiempo (paso 2) del asistente
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class FormatoImportado:
    """Espejo de `PropuestaFormato` (`tipos.ts`, paso 1 del asistente)."""

    codificacion: Campo[str]
    delimitador: Campo[str]
    comilla: Campo[str | None]
    decimal: Campo[str]
    fila_cabecera: Campo[int | None]
    fila_unidades: Campo[int | None]
    fila_datos: Campo[int]


def _formato_a_dict(formato: FormatoImportado) -> dict[str, object]:
    return {
        "codificacion": _campo_a_dict(cast(Campo[object], formato.codificacion)),
        "delimitador": _campo_a_dict(cast(Campo[object], formato.delimitador)),
        "comilla": _campo_a_dict(cast(Campo[object], formato.comilla)),
        "decimal": _campo_a_dict(cast(Campo[object], formato.decimal)),
        "fila_cabecera": _campo_a_dict(cast(Campo[object], formato.fila_cabecera)),
        "fila_unidades": _campo_a_dict(cast(Campo[object], formato.fila_unidades)),
        "fila_datos": _campo_a_dict(cast(Campo[object], formato.fila_datos)),
    }


def _formato_desde_dict(bruto: Mapping[str, object]) -> FormatoImportado:
    c = "formato"
    return FormatoImportado(
        codificacion=_campo_str(
            _tabla(bruto, "codificacion", contexto=c), contexto=f"{c}.codificacion"
        ),
        delimitador=_campo_str(
            _tabla(bruto, "delimitador", contexto=c), contexto=f"{c}.delimitador"
        ),
        comilla=_campo_str_o_none(_tabla(bruto, "comilla", contexto=c), contexto=f"{c}.comilla"),
        decimal=_campo_str(_tabla(bruto, "decimal", contexto=c), contexto=f"{c}.decimal"),
        fila_cabecera=_campo_int_o_none(
            _tabla(bruto, "fila_cabecera", contexto=c), contexto=f"{c}.fila_cabecera"
        ),
        fila_unidades=_campo_int_o_none(
            _tabla(bruto, "fila_unidades", contexto=c), contexto=f"{c}.fila_unidades"
        ),
        fila_datos=_campo_int(_tabla(bruto, "fila_datos", contexto=c), contexto=f"{c}.fila_datos"),
    )


@dataclass(slots=True, frozen=True)
class TiempoImportado:
    """Espejo de `PropuestaTiempo` (`tipos.ts`, paso 2), con el nombre de la
    columna guardado ADEMÁS del índice (ver cabecera del módulo: la
    reaplicación busca la columna de tiempo por nombre, no por posición)."""

    clase: Campo[str]
    columna: Campo[int | None]
    nombre_columna: str | None
    columna_fecha: Campo[int | None]
    nombre_columna_fecha: str | None
    frecuencia_hz: Campo[float | None]


def _tiempo_a_dict(tiempo: TiempoImportado) -> dict[str, object]:
    bruto: dict[str, object] = {
        "clase": _campo_a_dict(cast(Campo[object], tiempo.clase)),
        "columna": _campo_a_dict(cast(Campo[object], tiempo.columna)),
        "columna_fecha": _campo_a_dict(cast(Campo[object], tiempo.columna_fecha)),
        "frecuencia_hz": _campo_a_dict(cast(Campo[object], tiempo.frecuencia_hz)),
    }
    if tiempo.nombre_columna is not None:
        bruto["nombre_columna"] = tiempo.nombre_columna
    if tiempo.nombre_columna_fecha is not None:
        bruto["nombre_columna_fecha"] = tiempo.nombre_columna_fecha
    return bruto


def _nombre_o_none(bruto: Mapping[str, object], clave: str, *, contexto: str) -> str | None:
    valor = bruto.get(clave)
    if valor is not None and not isinstance(valor, str):
        raise ErrorDePerfilImportacion(f"{contexto}: '{clave}' debe ser texto o estar ausente")
    return valor


def _tiempo_desde_dict(bruto: Mapping[str, object]) -> TiempoImportado:
    c = "tiempo"
    return TiempoImportado(
        clase=_campo_str(_tabla(bruto, "clase", contexto=c), contexto=f"{c}.clase"),
        columna=_campo_int_o_none(_tabla(bruto, "columna", contexto=c), contexto=f"{c}.columna"),
        nombre_columna=_nombre_o_none(bruto, "nombre_columna", contexto=c),
        columna_fecha=_campo_int_o_none(
            _tabla(bruto, "columna_fecha", contexto=c), contexto=f"{c}.columna_fecha"
        ),
        nombre_columna_fecha=_nombre_o_none(bruto, "nombre_columna_fecha", contexto=c),
        frecuencia_hz=_campo_float_o_none(
            _tabla(bruto, "frecuencia_hz", contexto=c), contexto=f"{c}.frecuencia_hz"
        ),
    )


# --------------------------------------------------------------------------- #
# La huella: identifica el FORMATO, no el fichero (ver cabecera del módulo)
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class HuellaCabecera:
    """Los tres/cuatro rasgos que identifican un formato de CSV genérico:
    los nombres de columna normalizados EN ORDEN, el delimitador y la
    codificación. Se calcula siempre a partir de un fichero real
    (`construir_huella`); nunca se reconstruye desde un `.dlvimport`, porque
    `[huella]` solo guarda su resumen (`ResumenHuella`), no la lista de
    nombres — esos viven en `[[canales]]`, que es de donde sale el
    emparejamiento parcial."""

    nombres_normalizados: tuple[str, ...]
    delimitador: str
    codificacion: str

    @property
    def n_columnas(self) -> int:
        return len(self.nombres_normalizados)

    @property
    def hash_columnas(self) -> str:
        """`sha256` de los nombres normalizados unidos por un separador que no
        puede aparecer en un nombre ya normalizado (`normalizar` quita
        espacios y separadores comunes, pero no bytes de control): evita que
        `["ab", "c"]` y `["a", "bc"]` produzcan el mismo hash por concatenación
        ambigua."""
        cuerpo = "\x1f".join(self.nombres_normalizados)
        return "sha256:" + hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()


def construir_huella(
    nombres: Sequence[str], *, delimitador: str, codificacion: str
) -> HuellaCabecera:
    """La huella de un fichero real: se sondeó, se conocen sus columnas (en
    orden), su delimitador y su codificación confirmados. `nombres` son los
    nombres de columna TAL COMO APARECEN en la cabecera (no normalizados
    todavía); esta función normaliza, no quien la llama, para que la misma
    regla de normalización se aplique siempre (`dlv_core.roles.normalizar`)."""
    return HuellaCabecera(
        nombres_normalizados=tuple(normalizar(n) for n in nombres),
        delimitador=delimitador,
        codificacion=codificacion,
    )


@dataclass(slots=True, frozen=True)
class ResumenHuella:
    """Lo que `[huella]` guarda de una `HuellaCabecera`: el hash y el
    recuento de columnas, no la lista completa de nombres (que ya vive en
    `[[canales]]`, por canal). Es el resumen barato que permite decidir
    "¿es exactamente el mismo formato?" sin recorrer los canales — el camino
    rápido de doble clic que pide §7.9."""

    hash_columnas: str
    n_columnas: int
    delimitador: str
    codificacion: str

    @staticmethod
    def de_huella(huella: HuellaCabecera) -> ResumenHuella:
        return ResumenHuella(
            hash_columnas=huella.hash_columnas,
            n_columnas=huella.n_columnas,
            delimitador=huella.delimitador,
            codificacion=huella.codificacion,
        )

    def coincide_con(self, huella: HuellaCabecera) -> bool:
        """`True` solo si TODO coincide: hash (nombres + orden + recuento),
        delimitador y codificación. Es la condición de `"total"` en
        `reaplicar_perfil`."""
        return (
            self.hash_columnas == huella.hash_columnas
            and self.n_columnas == huella.n_columnas
            and self.delimitador == huella.delimitador
            and self.codificacion == huella.codificacion
        )


def _huella_a_dict(huella: ResumenHuella) -> dict[str, object]:
    return {
        "hash_columnas": huella.hash_columnas,
        "n_columnas": huella.n_columnas,
        "delimitador": huella.delimitador,
        "codificacion": huella.codificacion,
    }


def _huella_desde_dict(bruto: Mapping[str, object]) -> ResumenHuella:
    try:
        hash_columnas = bruto["hash_columnas"]
        n_columnas = bruto["n_columnas"]
        delimitador = bruto["delimitador"]
        codificacion = bruto["codificacion"]
    except KeyError as exc:
        raise ErrorDePerfilImportacion(f"huella: falta la clave {exc}") from None
    if not isinstance(hash_columnas, str) or not hash_columnas:
        raise ErrorDePerfilImportacion("huella: 'hash_columnas' debe ser texto no vacío")
    if isinstance(n_columnas, bool) or not isinstance(n_columnas, int) or n_columnas < 0:
        raise ErrorDePerfilImportacion("huella: 'n_columnas' debe ser un entero >= 0")
    if not isinstance(delimitador, str) or not delimitador:
        raise ErrorDePerfilImportacion("huella: 'delimitador' debe ser texto no vacío")
    if not isinstance(codificacion, str) or not codificacion:
        raise ErrorDePerfilImportacion("huella: 'codificacion' debe ser texto no vacío")
    return ResumenHuella(
        hash_columnas=hash_columnas,
        n_columnas=n_columnas,
        delimitador=delimitador,
        codificacion=codificacion,
    )


# --------------------------------------------------------------------------- #
# El perfil completo
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class PerfilImportacion:
    """Un `.dlvimport` en memoria: nombre, huella resumida, y las decisiones
    de los tres pasos del asistente (`docs/07` §7.8), cada campo con su
    `origen`."""

    nombre: str
    huella: ResumenHuella
    formato: FormatoImportado
    tiempo: TiempoImportado
    canales: tuple[CanalImportado, ...]

    # ----------------------------------------------------------------- #
    # dict <-> TOML: la parte "contenido", sin ningún fichero de por medio
    # (ADR-002; ver cabecera del módulo).
    # ----------------------------------------------------------------- #
    def a_dict(self) -> dict[str, object]:
        return {
            "version_esquema": VERSION_ESQUEMA_PERFIL_IMPORTACION,
            "nombre": self.nombre,
            "huella": _huella_a_dict(self.huella),
            "formato": _formato_a_dict(self.formato),
            "tiempo": _tiempo_a_dict(self.tiempo),
            "canales": [_canal_a_dict(c) for c in self.canales],
        }

    def a_texto_toml(self) -> str:
        """El texto TOML completo del `.dlvimport`. Quien lo escribe a disco
        es `dlv-api` (ADR-002): esta función solo produce el texto."""
        return _volcar_toml(self.a_dict())

    @staticmethod
    def desde_dict(bruto: Mapping[str, object]) -> PerfilImportacion:
        try:
            version = bruto["version_esquema"]
        except KeyError as exc:
            raise ErrorDePerfilImportacion(
                f"perfil de importación incompleto: falta la clave {exc}"
            ) from None
        if version != VERSION_ESQUEMA_PERFIL_IMPORTACION:
            raise ErrorDeVersionDePerfilDesconocida(
                f"este .dlvimport declara la versión de esquema {version!r} y este dlv-core "
                f"solo sabe leer la versión {VERSION_ESQUEMA_PERFIL_IMPORTACION}. Ábrelo con una "
                "versión de DataLogViewer que la reconozca"
            )
        nombre = bruto.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            raise ErrorDePerfilImportacion(
                "perfil de importación: 'nombre' debe ser texto no vacío"
            )

        canales_brutos = bruto.get("canales")
        if not isinstance(canales_brutos, list):
            raise ErrorDePerfilImportacion("perfil de importación: 'canales' debe ser una lista")
        canales: list[CanalImportado] = []
        for indice, canal_bruto in enumerate(canales_brutos):
            if not isinstance(canal_bruto, Mapping):
                raise ErrorDePerfilImportacion(f"canales[{indice}]: debe ser una tabla")
            canales.append(_canal_desde_dict(canal_bruto, indice=indice))

        return PerfilImportacion(
            nombre=nombre,
            huella=_huella_desde_dict(_tabla(bruto, "huella", contexto="perfil de importación")),
            formato=_formato_desde_dict(_tabla(bruto, "formato", contexto="perfil de importación")),
            tiempo=_tiempo_desde_dict(_tabla(bruto, "tiempo", contexto="perfil de importación")),
            canales=tuple(canales),
        )

    @staticmethod
    def desde_texto_toml(texto: str) -> PerfilImportacion:
        try:
            bruto = tomllib.loads(texto)
        except tomllib.TOMLDecodeError as exc:
            raise ErrorDePerfilImportacion(f"perfil de importación: TOML inválido: {exc}") from None
        if not isinstance(bruto, Mapping):
            # No debería poder pasar (tomllib.loads siempre da un dict en la raíz),
            # pero un `.dlvimport` es una entrada no confiable (regla 5): se
            # comprueba en vez de asumirlo.
            raise ErrorDePerfilImportacion(
                "perfil de importación: la raíz del TOML debe ser una tabla"
            )
        return PerfilImportacion.desde_dict(bruto)


def crear_perfil(
    nombre: str,
    *,
    nombres_columnas: Sequence[str],
    formato: FormatoImportado,
    tiempo: TiempoImportado,
    canales: Sequence[CanalImportado],
) -> PerfilImportacion:
    """Construye un `PerfilImportacion` a partir del estado terminado del
    asistente (`ResultadoAsistenteImportacion` en `asistente-importacion.ts`)
    y calcula su huella. Es el camino "Guardar como perfil de importación" de
    §7.8: nada de esto exige ningún catálogo externo, a diferencia de
    `crear_preset_usuario`, así que no hay una validación aparte que llamar
    después.

    `nombres_columnas` es la cabecera COMPLETA del fichero, en orden — con la
    columna de tiempo incluida. NO es lo mismo que `[c.nombre for c in
    canales]`: `dlv_api.importacion.sondear_canales` excluye a propósito la(s)
    columna(s) de tiempo de la lista de canales ("la columna de tiempo
    confirmada en el paso 2 no sale como canal"), así que si la huella se
    calculara solo a partir de `canales`, la columna de tiempo podría cambiar
    de nombre o de posición sin que la huella se enterara — justo el caso que
    `_fusionar_columna_tiempo` necesita poder detectar."""
    if not nombre.strip():
        raise ErrorDePerfilImportacion("un perfil de importación necesita un nombre no vacío")
    huella = construir_huella(
        nombres_columnas,
        delimitador=formato.delimitador.valor,
        codificacion=formato.codificacion.valor,
    )
    return PerfilImportacion(
        nombre=nombre,
        huella=ResumenHuella.de_huella(huella),
        formato=formato,
        tiempo=tiempo,
        canales=tuple(canales),
    )


# --------------------------------------------------------------------------- #
# Reaplicación
# --------------------------------------------------------------------------- #
TipoCoincidencia = Literal["total", "parcial", "ninguna"]


@dataclass(slots=True, frozen=True)
class ResultadoReaplicacion:
    """El resultado de reaplicar un perfil a un sondeo nuevo.

    `canales` tiene SIEMPRE la misma longitud y el mismo orden que los
    `canales_actuales` que se le pasaron a `reaplicar_perfil`: es el estado
    del asistente después de fusionar, listo para pintarse tal cual en el
    paso 3. Un canal cuyo nombre no estaba en el perfil sale IDÉNTICO al que
    entró (recién deducido, `origen == "deducido"` en todos sus campos) y
    además su nombre aparece en `columnas_nuevas_sin_decidir` — la manera de
    que el usuario lo VEA, no de que lo adivine."""

    tipo: TipoCoincidencia
    motivo: str
    formato: FormatoImportado
    tiempo: TiempoImportado
    canales: tuple[CanalImportado, ...]
    columnas_nuevas_sin_decidir: tuple[str, ...]
    avisos: tuple[str, ...]


def _fusionar_campo(actual: Campo[_T], guardado: Campo[_T]) -> Campo[_T]:  # noqa: UP047 — ver Campo
    """La regla central del módulo: lo confirmado sobrevive, lo deducido se
    vuelve a deducir. Si `guardado` no es `"confirmado"`, esta función
    devuelve `actual` sin tocarlo — el valor guardado se descarta entero,
    incluso si por casualidad coincide con el nuevo, porque lo que importa no
    es el valor sino QUIÉN lo decidió."""
    if guardado.origen == "confirmado":
        return Campo(valor=guardado.valor, origen="confirmado")
    return actual


def _fusionar_rol(actual: RolDeCanal | None, guardado: RolDeCanal | None) -> RolDeCanal | None:
    """Mismo criterio que `_fusionar_campo`, con el vocabulario propio del
    rol: una `DIFUSA` sin confirmar en el perfil (`guardado.confirmado is
    False`) no se reaplica — habría estado desactivando un detector crítico
    por una corazonada de la semana pasada en vez de la de hoy."""
    if guardado is not None and guardado.confirmado:
        return guardado
    return actual


def _fusionar_canal(actual: CanalImportado, guardado: CanalImportado) -> CanalImportado:
    return replace(
        actual,
        dimension_id=_fusionar_campo(actual.dimension_id, guardado.dimension_id),
        unidad_origen=_fusionar_campo(actual.unidad_origen, guardado.unidad_origen),
        rol=_fusionar_rol(actual.rol, guardado.rol),
    )


def _fusionar_formato(actual: FormatoImportado, guardado: FormatoImportado) -> FormatoImportado:
    return FormatoImportado(
        codificacion=_fusionar_campo(actual.codificacion, guardado.codificacion),
        delimitador=_fusionar_campo(actual.delimitador, guardado.delimitador),
        comilla=_fusionar_campo(actual.comilla, guardado.comilla),
        decimal=_fusionar_campo(actual.decimal, guardado.decimal),
        fila_cabecera=_fusionar_campo(actual.fila_cabecera, guardado.fila_cabecera),
        fila_unidades=_fusionar_campo(actual.fila_unidades, guardado.fila_unidades),
        fila_datos=_fusionar_campo(actual.fila_datos, guardado.fila_datos),
    )


def _fusionar_columna_tiempo(
    campo_actual: Campo[int | None],
    campo_guardado: Campo[int | None],
    nombre_guardado: str | None,
    nombres_columnas: Sequence[str],
) -> tuple[Campo[int | None], str | None]:
    """Reaplica una columna de tiempo (o de fecha) POR NOMBRE, buscando en LA
    CABECERA COMPLETA (`nombres_columnas`, con la propia columna de tiempo
    incluida — no en los nombres de `canales_actuales`, que la excluyen). Ver
    la cabecera del módulo: reaplicar por índice sería el fallo silencioso
    más caro de todos. Devuelve `(campo_fusionado, aviso_o_none)`."""
    if campo_guardado.origen != "confirmado":
        return campo_actual, None
    if nombre_guardado is None:
        # El usuario confirmó explícitamente "sin columna de tiempo" (eje
        # sintético, §7.5): no hay nombre que buscar, se reaplica tal cual.
        return Campo(valor=campo_guardado.valor, origen="confirmado"), None
    clave = normalizar(nombre_guardado)
    for indice, nombre in enumerate(nombres_columnas):
        if normalizar(nombre) == clave:
            return Campo(valor=indice, origen="confirmado"), None
    return (
        campo_actual,
        f"la columna de tiempo confirmada «{nombre_guardado}» no está en este fichero: "
        "se vuelve a deducir",
    )


def _fusionar_tiempo(
    actual: TiempoImportado, guardado: TiempoImportado, nombres_columnas: Sequence[str]
) -> tuple[TiempoImportado, tuple[str, ...]]:
    columna, aviso_columna = _fusionar_columna_tiempo(
        actual.columna, guardado.columna, guardado.nombre_columna, nombres_columnas
    )
    columna_fecha, aviso_fecha = _fusionar_columna_tiempo(
        actual.columna_fecha,
        guardado.columna_fecha,
        guardado.nombre_columna_fecha,
        nombres_columnas,
    )
    nombre_columna = (
        guardado.nombre_columna if columna.origen == "confirmado" else actual.nombre_columna
    )
    nombre_columna_fecha = (
        guardado.nombre_columna_fecha
        if columna_fecha.origen == "confirmado"
        else actual.nombre_columna_fecha
    )
    avisos = tuple(a for a in (aviso_columna, aviso_fecha) if a is not None)
    fusionado = TiempoImportado(
        clase=_fusionar_campo(actual.clase, guardado.clase),
        columna=columna,
        nombre_columna=nombre_columna,
        columna_fecha=columna_fecha,
        nombre_columna_fecha=nombre_columna_fecha,
        frecuencia_hz=_fusionar_campo(actual.frecuencia_hz, guardado.frecuencia_hz),
    )
    return fusionado, avisos


def _resultado_sin_reaplicar(
    formato: FormatoImportado,
    tiempo: TiempoImportado,
    canales: Sequence[CanalImportado],
    nombres: Sequence[str],
    *,
    motivo: str,
) -> ResultadoReaplicacion:
    """`"ninguna"`: el fichero nuevo se devuelve exactamente como llegó, sin
    tocar un solo campo. Reaplicar algo aquí sería el error que la tarea
    llama "peor que no tener perfiles"."""
    return ResultadoReaplicacion(
        tipo="ninguna",
        motivo=motivo,
        formato=formato,
        tiempo=tiempo,
        canales=tuple(canales),
        columnas_nuevas_sin_decidir=tuple(nombres),
        avisos=(),
    )


def reaplicar_perfil(
    perfil: PerfilImportacion,
    *,
    nombres_columnas: Sequence[str],
    formato_actual: FormatoImportado,
    tiempo_actual: TiempoImportado,
    canales_actuales: Sequence[CanalImportado],
) -> ResultadoReaplicacion:
    """Reaplica `perfil` sobre el sondeo YA DEDUCIDO de un fichero nuevo
    (`formato_actual`/`tiempo_actual`/`canales_actuales`, con
    `origen == "deducido"` en todos sus `Campo`, tal como los produce
    `dlv_api.importacion.sondear_formato/sondear_tiempo/sondear_canales`).

    `nombres_columnas` es la cabecera COMPLETA del fichero nuevo, en orden,
    columna de tiempo incluida — la misma cosa que se le pasa a
    `crear_perfil` al guardar (ver su docstring: no es `[c.nombre for c in
    canales_actuales]`, que excluye la columna de tiempo).

    No vuelve a sondear nada: recibe la propuesta fresca y la fusiona con lo
    que el perfil guardó, campo a campo (`_fusionar_campo`) y canal a canal
    (emparejados por nombre normalizado). Ver la cabecera del módulo para la
    frontera entre `"total"`, `"parcial"` y `"ninguna"`.
    """
    nombres_actuales = tuple(c.nombre for c in canales_actuales)
    huella_actual = construir_huella(
        nombres_columnas,
        delimitador=formato_actual.delimitador.valor,
        codificacion=formato_actual.codificacion.valor,
    )

    if formato_actual.delimitador.valor != perfil.huella.delimitador:
        return _resultado_sin_reaplicar(
            formato_actual,
            tiempo_actual,
            canales_actuales,
            nombres_actuales,
            motivo=(
                f"el perfil «{perfil.nombre}» se guardó con el delimitador "
                f"{perfil.huella.delimitador!r} y este fichero usa "
                f"{formato_actual.delimitador.valor!r}: no es el mismo formato, no se reaplica nada"
            ),
        )
    if formato_actual.codificacion.valor != perfil.huella.codificacion:
        return _resultado_sin_reaplicar(
            formato_actual,
            tiempo_actual,
            canales_actuales,
            nombres_actuales,
            motivo=(
                f"el perfil «{perfil.nombre}» se guardó con la codificación "
                f"{perfil.huella.codificacion!r} y este fichero usa "
                f"{formato_actual.codificacion.valor!r}: no es el mismo formato, "
                "no se reaplica nada"
            ),
        )

    por_nombre_perfil = {normalizar(c.nombre): c for c in perfil.canales}
    n_coincidencias = sum(1 for n in nombres_actuales if normalizar(n) in por_nombre_perfil)
    if n_coincidencias == 0:
        return _resultado_sin_reaplicar(
            formato_actual,
            tiempo_actual,
            canales_actuales,
            nombres_actuales,
            motivo=(
                f"ninguna columna de este fichero coincide con las {len(perfil.canales)} del "
                f"perfil «{perfil.nombre}»: mismo delimitador y codificación, pero no parece "
                "el mismo origen de datos, no se reaplica nada"
            ),
        )

    canales_fusionados: list[CanalImportado] = []
    columnas_nuevas: list[str] = []
    for canal in canales_actuales:
        guardado = por_nombre_perfil.get(normalizar(canal.nombre))
        if guardado is None:
            canales_fusionados.append(canal)
            columnas_nuevas.append(canal.nombre)
        else:
            canales_fusionados.append(_fusionar_canal(canal, guardado))

    nombres_vistos = {normalizar(n) for n in nombres_actuales}
    columnas_perdidas = tuple(
        c.nombre for c in perfil.canales if normalizar(c.nombre) not in nombres_vistos
    )

    formato_fusionado = _fusionar_formato(formato_actual, perfil.formato)
    tiempo_fusionado, avisos_tiempo = _fusionar_tiempo(
        tiempo_actual, perfil.tiempo, nombres_columnas
    )

    avisos: list[str] = list(avisos_tiempo)
    if columnas_nuevas:
        avisos.append(
            f"{len(columnas_nuevas)} columna(s) nueva(s) sin decisión del perfil "
            f"«{perfil.nombre}»: " + ", ".join(columnas_nuevas)
        )
    if columnas_perdidas:
        avisos.append(
            f"{len(columnas_perdidas)} columna(s) del perfil «{perfil.nombre}» no están en este "
            "fichero: " + ", ".join(columnas_perdidas)
        )

    coincide_todo = (
        perfil.huella.coincide_con(huella_actual) and not columnas_nuevas and not columnas_perdidas
    )
    if coincide_todo:
        tipo: TipoCoincidencia = "total"
        motivo = f"huella idéntica a la del perfil «{perfil.nombre}»: se reaplica entero"
    else:
        tipo = "parcial"
        motivo = (
            f"huella compatible en parte con el perfil «{perfil.nombre}» "
            f"({n_coincidencias}/{len(nombres_actuales)} columnas de este fichero coinciden por "
            "nombre): se reaplica lo que coincide"
        )

    return ResultadoReaplicacion(
        tipo=tipo,
        motivo=motivo,
        formato=formato_fusionado,
        tiempo=tiempo_fusionado,
        canales=tuple(canales_fusionados),
        columnas_nuevas_sin_decidir=tuple(columnas_nuevas),
        avisos=tuple(avisos),
    )


# --------------------------------------------------------------------------- #
# Escritor TOML mínimo (ver "`.dlvimport` ES TOML..." en la cabecera: no es
# una biblioteca TOML de propósito general, solo sabe volcar la forma fija
# que produce `PerfilImportacion.a_dict()`).
# --------------------------------------------------------------------------- #
def _valor_toml(valor: object) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        # `repr(float)` en Python >= 3.1 es la representación más corta que
        # vuelve a leerse exactamente igual (round-trip), y esa sintaxis es
        # válida TOML sin cambios.
        return repr(valor)
    if isinstance(valor, str):
        # Las cadenas básicas de TOML usan el mismo juego de escapes que JSON
        # (\" \\ \b \f \n \r \t \uXXXX) con comillas dobles: `json.dumps` de
        # una cadena es, carácter a carácter, una cadena básica TOML válida.
        return json.dumps(valor)
    if isinstance(valor, Mapping):
        interior = ", ".join(f"{k} = {_valor_toml(v)}" for k, v in valor.items() if v is not None)
        return "{ " + interior + " }" if interior else "{ }"
    raise TypeError(f"tipo no soportado al escribir un .dlvimport: {type(valor)!r}")


def _lineas_de_tabla(tabla: Mapping[str, object]) -> list[str]:
    return [
        f"{clave} = {_valor_toml(valor)}" for clave, valor in tabla.items() if valor is not None
    ]


def _volcar_toml(perfil: Mapping[str, object]) -> str:
    lineas: list[str] = []

    escalares = {k: v for k, v in perfil.items() if not isinstance(v, (Mapping, list))}
    lineas.extend(_lineas_de_tabla(escalares))

    for seccion in ("huella", "formato", "tiempo"):
        tabla = perfil.get(seccion)
        if not isinstance(tabla, Mapping):
            continue
        lineas.append("")
        lineas.append(f"[{seccion}]")
        lineas.extend(_lineas_de_tabla(tabla))

    canales = perfil.get("canales")
    if isinstance(canales, list):
        for canal in canales:
            if not isinstance(canal, Mapping):
                continue
            lineas.append("")
            lineas.append("[[canales]]")
            lineas.extend(_lineas_de_tabla(canal))

    return "\n".join(lineas) + "\n"
