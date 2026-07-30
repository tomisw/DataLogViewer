"""Caché de parseo en Parquet, escrita por Polars (ADR-005).

`dlv-core` no decide por su cuenta dónde vive la caché ni qué fichero abrir:
toda ruta y todo objeto de lectura/escritura llega como parámetro desde quien
llama (hoy, `dlv-api`). Este módulo solo sabe cómo se construye la clave de
invalidación y cómo se serializa/deserializa el contenido, no dónde se guarda
la carpeta `.dlvcache` en el disco del usuario. `escribir`/`leer` SÍ derivan
un pequeño conjunto de nombres de fichero hermanos a partir de la ruta que
reciben (ver `_ruta_metadatos`/`_ruta_tiempos`/`_ruta_piramide`): eso no es
"decidir dónde vive la caché" -- esa decisión (carpeta, nombre base) sigue
siendo de quien llama -- es solo el esquema de serialización interno del
`.dlvcache`, igual que un `.docx` es en realidad una carpeta ZIP con varios
ficheros por dentro.

La pirámide de decimación (`piramide.py`) se persiste dentro de la caché:
recalcularla cuesta más que leerla (ADR-005). De hecho, el nivel L0 de
cualquiera de las cuatro variantes ya contiene el valor bruto de cada muestra
sin pérdida (`NivelPiramide.primero`, `NivelContador.primero`,
`NivelEnum.moda`, `NivelBits.or_bits` en L0 son literalmente el array
original), así que este módulo NO persiste `ChannelSeries.v` por separado:
se reconstruye leyendo L0. Esto evita duplicar en disco el volumen de datos
más grande dos veces.

## Esquema físico: ancho, particionado por grupo de muestreo, no "largo"

La primera versión de este módulo usaba una tabla "larga" (una fila por
cubo, con columnas `canal`/`factor`/`cubo` repetidas) para toda la pirámide
de todos los canales a la vez. Es la representación más obvia, pero
`tools/banco.py`-style, medida contra el escenario de referencia de
`docs/02-alcance-y-plan.md` §2.6 ("16 canales × 5 M puntos"), tardaba
~48 s en escribir+leer -- casi 70x el presupuesto de 700 ms de
`segunda_apertura` -- porque (a) construir una columna `canal` de texto
repetida millones de veces por canal es caro, y (b) reagrupar por canal al
leer (`partition_by`/`filter`) es una operación O(filas totales), no O(datos
de este canal).

La representación que sí cumple el presupuesto es **ancha**: un fichero
Parquet **por grupo de muestreo** (normalmente uno solo, ADR-003 dice que en
las muestras reales el 100 % de los canales de un log Haltech caen en un
único grupo), con una columna nativa por `(canal, campo)`
(p. ej. `"3__minimo"`), donde cada columna contiene TODOS los niveles de la
pirámide de ese canal concatenados en orden (L0, L1, L4, ...). Como todos los
canales de un mismo grupo comparten el mismo número de muestras y el mismo
`factor_base`, comparten también la misma longitud total empaquetada, así que
conviven sin problema como columnas de una misma tabla. Los límites de cada
nivel dentro de esa columna se guardan en el JSON de metadatos
(`MetadatosCanal.niveles`, pares `(factor, n_cubos)`), así que leer un nivel
es un simple *slice* de NumPy por offset -- O(tamaño de ese nivel), no una
búsqueda ni una reagrupación.

Diferencias deliberadas frente al stub original de esta tarea (documentadas
aquí porque F1-05 dejó precedente de que a veces el tipo declarado en el stub
no encaja con lo que hace falta, y hay que ajustarlo y decir por qué):

- `escribir`/`leer` ya no reciben/devuelven un único `pl.DataFrame` ("tabla"):
  reciben/devuelven `ChannelSeries` + pirámides, que es lo que de verdad hace
  falta para pintar el primer gráfico sin rehacer los pasos 4-7 de §3.4
  (grupos de muestreo, roles, pirámide). Pedir al llamador que además arme un
  `pl.DataFrame` aparte habría sido trabajo redundante y una fuente de
  desincronización entre "lo que dice la tabla" y "lo que dicen las series".
- `MetadatosCache` ya no tiene los campos sueltos `roles`/`dimensiones`/
  `grupos_muestreo` del stub (tres estructuras paralelas a `canales` que
  había que mantener sincronizadas a mano): se consolidan en
  `canales: tuple[MetadatosCanal, ...]`, un registro por canal con todo lo
  que hace falta para reconstruirlo, en el mismo orden que la lista de
  `ChannelSeries` que se leerá de vuelta.
- `ClaveInvalidacion` gana un campo `version_esquema_cache` que no estaba en
  el stub: ADR-005 pide invalidar por `(ruta, tamaño, mtime, versión del
  parser, versión del descriptor de formato)`, pero ninguno de esos cinco
  campos protege contra un cambio en la FORMA de `ChannelSeries` o de
  `NivelPiramide` (p. ej. una versión futura de dlv-core que añada un campo
  nuevo a un nivel de pirámide). Sin este campo, una caché escrita por una
  versión antigua del programa se leería con una forma distinta a la que
  tiene y probablemente reventaría a medio leer en vez de detectarse como
  obsoleta de entrada.
- `es_valida` acepta `clave_almacenada: ClaveInvalidacion | None` en vez de
  exigir siempre una clave real: `None` representa "todavía no hay caché" (o
  se borró el JSON de metadatos) y la función responde `False` sin lanzar,
  que es justo lo que pide la tarea ("`es_valida` no falla si la caché no
  existe todavía").
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl

from dlv_core.almacen import ChannelSeries, Storage
from dlv_core.piramide import (
    NivelBits,
    NivelContador,
    NivelEnum,
    NivelPiramide,
    TipoCanalPiramide,
    construir_piramide,
)
from dlv_core.roles import ChannelKey
from dlv_core.unidades import Afin

# --------------------------------------------------------------------------- #
# Versión del ESQUEMA de la caché (no la versión del parser/descriptor de
# formato del log de origen, que llega de fuera): sube cuando cambia la FORMA
# de `ChannelSeries`, de alguno de los `NivelXxx` de `piramide.py`, o el
# esquema de columnas Parquet/JSON de este módulo. Cambiar este módulo sin
# subir la versión es un error de revisión, no algo que el código pueda
# detectar por sí solo.
# --------------------------------------------------------------------------- #
VERSION_ESQUEMA_CACHE = "1"

# Unión de las cuatro variantes de pirámide de un solo canal (mismo tipo que
# devuelve `piramide.construir_piramide`, con nombre para no repetir la unión
# en cada firma de este módulo).
Piramide = list[NivelPiramide] | list[NivelContador] | list[NivelEnum] | list[NivelBits]

# Storage -> dtype de NumPy con el que se reconstruyen `v` y los campos "de
# valor" de la pirámide (no `suma_delta`, que siempre es int64 -- ver
# `_nivel_l0_contador` en `piramide.py` -- ni `hubo_transicion`, que es
# `bool`). Al escribir, los arrays de `piramide.py` ya vienen en este dtype
# (Parquet/Arrow lo conserva tal cual, sin necesidad de ensancharlo a
# Float64/Int64 como en un esquema de columnas compartido entre canales); el
# `.astype` de `leer` es una red de seguridad barata, no una conversión que
# haga falta de verdad.
_DTYPE_POR_STORAGE: dict[Storage, type[np.generic]] = {
    Storage.INT32_SCALED: np.int32,
    Storage.FLOAT32: np.float32,
    Storage.FLOAT64: np.float64,
    Storage.ENUM_U16: np.uint16,
    Storage.BITS_U32: np.uint32,
}


@dataclass(slots=True, frozen=True)
class ClaveInvalidacion:
    """Clave de invalidación de caché (ADR-005): ruta, tamaño, mtime y versiones.

    `ruta` se compara por igualdad de valor (dos `Path` iguales si su
    representación en texto lo es): quien llama es responsable de pasar
    siempre la misma forma (resuelta/absoluta o relativa, pero consistente)
    tanto al escribir como al comprobar, o la invalidación disparará en falso
    por una diferencia puramente cosmética de la ruta.
    """

    ruta: Path
    tamano_bytes: int
    mtime_ns: int
    version_parser: str
    version_descriptor_formato: str
    # Ver docstring del módulo: no estaba en el stub original.
    version_esquema_cache: str = VERSION_ESQUEMA_CACHE


def construir_clave(
    ruta: Path,
    *,
    tamano_bytes: int,
    mtime_ns: int,
    version_parser: str,
    version_descriptor_formato: str,
) -> ClaveInvalidacion:
    """Fábrica de `ClaveInvalidacion` que fija `version_esquema_cache` al
    valor que entiende ESTE código (`VERSION_ESQUEMA_CACHE`), para que quien
    llama no tenga que conocer ni propagar ese detalle interno del módulo.

    `ruta`/`tamano_bytes`/`mtime_ns` los obtiene quien llama (p. ej. `dlv-api`
    con `Path.stat()`): este módulo no toca el sistema de ficheros por su
    cuenta para construir la clave (ADR-002), solo empaqueta los valores que
    se le dan.
    """
    return ClaveInvalidacion(
        ruta=ruta,
        tamano_bytes=tamano_bytes,
        mtime_ns=mtime_ns,
        version_parser=version_parser,
        version_descriptor_formato=version_descriptor_formato,
        version_esquema_cache=VERSION_ESQUEMA_CACHE,
    )


@dataclass(slots=True, frozen=True)
class MetadatosCanal:
    """Todo lo que hace falta para reconstruir un `ChannelSeries` y su
    pirámide a partir de las tablas Parquet, aparte de los propios arrays
    numéricos (que viven en el Parquet, no aquí).

    `id_canal` es la clave primaria DENTRO de esta caché (la posición del
    canal en la lista que se escribió, como texto): no es el `ID` nativo del
    formato, que puede repetirse entre formatos distintos o faltar. `grupo`
    identifica qué canales comparten el mismo array `t` por referencia
    (ADR-003) y por tanto el mismo fichero Parquet de pirámide (ver docstring
    del módulo). `niveles` son los pares `(factor, n_cubos)` de cada nivel,
    EN ORDEN, tal como se concatenaron en las columnas empaquetadas de ese
    canal: sin esto no habría forma de saber dónde termina L0 y empieza L1
    dentro de la columna.
    """

    id_canal: str
    grupo: str
    key_rol: str | None
    formato: str | None
    id_nativo: str | None
    nombre_normalizado: str | None
    role: str | None
    storage: str  # nombre de `Storage`, p. ej. "INT32_SCALED"
    dimension: str | None
    to_canon_a: float
    to_canon_b: float
    tipo_piramide: str  # nombre de `TipoCanalPiramide`, p. ej. "CONTINUO"
    niveles: tuple[tuple[int, int], ...]  # (factor, n_cubos) por nivel, L0 primero


@dataclass(slots=True, frozen=True)
class MetadatosCache:
    """El JSON de metadatos que acompaña a los `.parquet` de la caché (ADR-005).

    Ver el docstring del módulo: `canales` sustituye a los campos sueltos
    `roles`/`dimensiones`/`grupos_muestreo` del stub original.
    """

    clave: ClaveInvalidacion
    canales: tuple[MetadatosCanal, ...]


def es_valida(clave_almacenada: ClaveInvalidacion | None, clave_actual: ClaveInvalidacion) -> bool:
    """Compara dos claves de invalidación campo a campo, sin tocar disco (ni
    siquiera necesita que el JSON de metadatos exista más allá de haberse
    leído antes: esta función en sí no hace E/S).

    `clave_almacenada` es `None` cuando todavía no hay caché (primera
    apertura, o el JSON de metadatos se ha borrado/corrompido): en ese caso
    la función NO lanza, responde `False` ("hace falta reconstruir"), que es
    la respuesta correcta para "no hay nada que invalidar todavía".
    """
    if clave_almacenada is None:
        return False
    return clave_almacenada == clave_actual


# --------------------------------------------------------------------------- #
# Esquema físico
# --------------------------------------------------------------------------- #
def _ruta_metadatos(base: Path) -> Path:
    return base.with_name(base.name + ".json")


def _ruta_tiempos(base: Path, grupo: str) -> Path:
    return base.with_name(f"{base.name}.t.{grupo}.parquet")


def _ruta_piramide(base: Path, grupo: str) -> Path:
    return base.with_name(f"{base.name}.piramide.{grupo}.parquet")


def _tipo_de_piramide(piramide: Piramide) -> TipoCanalPiramide:
    if not piramide:
        raise ValueError("una pirámide no puede estar vacía (siempre trae al menos L0)")
    primero = piramide[0]
    if isinstance(primero, NivelPiramide):
        return TipoCanalPiramide.CONTINUO
    if isinstance(primero, NivelContador):
        return TipoCanalPiramide.CONTADOR
    if isinstance(primero, NivelEnum):
        return TipoCanalPiramide.ENUM
    if isinstance(primero, NivelBits):
        return TipoCanalPiramide.BITS
    raise AssertionError(f"tipo de nivel de pirámide no reconocido: {primero!r}")


def _columnas_empaquetadas(
    id_canal: str, tipo: TipoCanalPiramide, piramide: Piramide
) -> dict[str, np.ndarray]:
    """Concatena los niveles de UN canal en una o más columnas anchas
    (`{id_canal}__{campo}`), una por campo relevante de su variante. El
    bucle recorre niveles (~12 para 5 M muestras), no muestras: cada
    `np.concatenate` es una sola operación vectorizada sobre arrays
    completos (ADR-009).
    """
    if tipo is TipoCanalPiramide.CONTINUO:
        niveles_continuo = cast(list[NivelPiramide], piramide)
        return {
            f"{id_canal}__minimo": np.concatenate([n.minimo for n in niveles_continuo]),
            f"{id_canal}__maximo": np.concatenate([n.maximo for n in niveles_continuo]),
            f"{id_canal}__primero": np.concatenate([n.primero for n in niveles_continuo]),
            f"{id_canal}__ultimo": np.concatenate([n.ultimo for n in niveles_continuo]),
        }
    if tipo is TipoCanalPiramide.CONTADOR:
        niveles_contador = cast(list[NivelContador], piramide)
        return {
            f"{id_canal}__suma_delta": np.concatenate([n.suma_delta for n in niveles_contador]),
            f"{id_canal}__primero": np.concatenate([n.primero for n in niveles_contador]),
            f"{id_canal}__ultimo": np.concatenate([n.ultimo for n in niveles_contador]),
        }
    if tipo is TipoCanalPiramide.ENUM:
        niveles_enum = cast(list[NivelEnum], piramide)
        return {
            f"{id_canal}__moda": np.concatenate([n.moda for n in niveles_enum]),
            f"{id_canal}__hubo_transicion": np.concatenate(
                [n.hubo_transicion for n in niveles_enum]
            ),
        }
    if tipo is TipoCanalPiramide.BITS:
        niveles_bits = cast(list[NivelBits], piramide)
        return {f"{id_canal}__or_bits": np.concatenate([n.or_bits for n in niveles_bits])}
    raise AssertionError(f"TipoCanalPiramide no cubierto: {tipo!r}")  # exhaustivo


# --------------------------------------------------------------------------- #
# (De)serialización JSON de los metadatos
# --------------------------------------------------------------------------- #
def _clave_a_dict(c: ClaveInvalidacion) -> dict[str, Any]:
    return {
        "ruta": str(c.ruta),
        "tamano_bytes": c.tamano_bytes,
        "mtime_ns": c.mtime_ns,
        "version_parser": c.version_parser,
        "version_descriptor_formato": c.version_descriptor_formato,
        "version_esquema_cache": c.version_esquema_cache,
    }


def _clave_desde_dict(d: Mapping[str, Any]) -> ClaveInvalidacion:
    return ClaveInvalidacion(
        ruta=Path(d["ruta"]),
        tamano_bytes=int(d["tamano_bytes"]),
        mtime_ns=int(d["mtime_ns"]),
        version_parser=str(d["version_parser"]),
        version_descriptor_formato=str(d["version_descriptor_formato"]),
        version_esquema_cache=str(d["version_esquema_cache"]),
    )


def _canal_a_dict(m: MetadatosCanal) -> dict[str, Any]:
    return {
        "id_canal": m.id_canal,
        "grupo": m.grupo,
        "key_rol": m.key_rol,
        "formato": m.formato,
        "id_nativo": m.id_nativo,
        "nombre_normalizado": m.nombre_normalizado,
        "role": m.role,
        "storage": m.storage,
        "dimension": m.dimension,
        "to_canon_a": m.to_canon_a,
        "to_canon_b": m.to_canon_b,
        "tipo_piramide": m.tipo_piramide,
        "niveles": [list(par) for par in m.niveles],
    }


def _canal_desde_dict(d: Mapping[str, Any]) -> MetadatosCanal:
    return MetadatosCanal(
        id_canal=str(d["id_canal"]),
        grupo=str(d["grupo"]),
        key_rol=d["key_rol"],
        formato=d["formato"],
        id_nativo=d["id_nativo"],
        nombre_normalizado=d["nombre_normalizado"],
        role=d["role"],
        storage=str(d["storage"]),
        dimension=d["dimension"],
        to_canon_a=float(d["to_canon_a"]),
        to_canon_b=float(d["to_canon_b"]),
        tipo_piramide=str(d["tipo_piramide"]),
        niveles=tuple((int(factor), int(n_cubos)) for factor, n_cubos in d["niveles"]),
    )


def _metadatos_a_dict(m: MetadatosCache) -> dict[str, Any]:
    return {
        "clave": _clave_a_dict(m.clave),
        "canales": [_canal_a_dict(c) for c in m.canales],
    }


def _metadatos_desde_dict(d: Mapping[str, Any]) -> MetadatosCache:
    return MetadatosCache(
        clave=_clave_desde_dict(d["clave"]),
        canales=tuple(_canal_desde_dict(c) for c in d["canales"]),
    )


def leer_metadatos(origen: Path) -> MetadatosCache | None:
    """Lee SOLO el JSON de metadatos (nunca los `.parquet`): la comprobación
    barata de "¿sigue viva esta caché?" que pide la tarea, para no tener que
    tocar los datos completos solo para invalidar. Devuelve `None` -- sin
    lanzar -- si el JSON no existe todavía (primera apertura de este log, o
    caché borrada).
    """
    ruta_metadatos = _ruta_metadatos(origen)
    if not ruta_metadatos.exists():
        return None
    contenido: Any = json.loads(ruta_metadatos.read_text(encoding="utf-8"))
    return _metadatos_desde_dict(contenido)


# --------------------------------------------------------------------------- #
# Escritura
# --------------------------------------------------------------------------- #
def escribir(
    destino: Path,
    clave: ClaveInvalidacion,
    series: Sequence[ChannelSeries],
    piramides: Sequence[Piramide],
) -> None:
    """Escribe la caché: `destino` es la ruta al `.dlvcache` ya resuelta por
    quien llama (de ahí cuelgan los ficheros hermanos, ver `_ruta_tiempos`/
    `_ruta_piramide`/`_ruta_metadatos`): un Parquet de tiempos y uno de
    pirámide POR GRUPO de muestreo (normalmente uno solo), más un único JSON
    de metadatos.

    `piramides[i]` es la pirámide ya construida (F1-09/F1-10) de
    `series[i]`: mismo orden, misma longitud. No se recalcula nada aquí --
    calcularla es responsabilidad de quien orquesta el paso 7 de §3.4, este
    módulo solo la persiste (ADR-005: recalcularla cuesta más que leerla).
    """
    if len(series) != len(piramides):
        raise ValueError(
            f"series y piramides deben tener la misma longitud ({len(series)} != {len(piramides)})"
        )

    grupos_por_identidad: dict[int, str] = {}
    t_por_grupo: dict[str, np.ndarray] = {}
    columnas_por_grupo: dict[str, dict[str, np.ndarray]] = {}
    longitud_empaquetada_por_grupo: dict[str, int] = {}
    canales_meta: list[MetadatosCanal] = []

    # Bucle por CANAL (cientos, no millones): cada iteración vectoriza sobre
    # el array completo del canal, ADR-009 no lo prohíbe.
    for indice, (serie, piramide) in enumerate(zip(series, piramides, strict=True)):
        id_canal = str(indice)
        identidad_t = id(serie.t)
        grupo = grupos_por_identidad.get(identidad_t)
        if grupo is None:
            grupo = f"g{len(grupos_por_identidad)}"
            grupos_por_identidad[identidad_t] = grupo
            t_por_grupo[grupo] = serie.t
            columnas_por_grupo[grupo] = {}

        tipo = _tipo_de_piramide(piramide)
        niveles_meta = tuple((n.factor, n.n_cubos) for n in piramide)
        longitud_total = sum(n_cubos for _, n_cubos in niveles_meta)

        longitud_esperada = longitud_empaquetada_por_grupo.get(grupo)
        if longitud_esperada is None:
            longitud_empaquetada_por_grupo[grupo] = longitud_total
        elif longitud_esperada != longitud_total:
            raise ValueError(
                f"canal {id_canal} del grupo '{grupo}' tiene una pirámide de longitud "
                f"empaquetada {longitud_total}, distinta de los {longitud_esperada} de "
                "otros canales del mismo grupo (¿factor_base distinto dentro del grupo?)"
            )

        columnas_por_grupo[grupo].update(_columnas_empaquetadas(id_canal, tipo, piramide))

        canales_meta.append(
            MetadatosCanal(
                id_canal=id_canal,
                grupo=grupo,
                key_rol=serie.key.rol,
                formato=serie.key.formato,
                id_nativo=serie.key.id_nativo,
                nombre_normalizado=serie.key.nombre_normalizado,
                role=serie.role,
                storage=serie.storage.name,
                dimension=serie.dimension,
                to_canon_a=serie.to_canon.a,
                to_canon_b=serie.to_canon.b,
                tipo_piramide=tipo.name,
                niveles=niveles_meta,
            )
        )

    for grupo, t in t_por_grupo.items():
        # `lz4` en vez del `zstd` por omisión de Polars: en el escenario de
        # referencia (66 MB / 475 canales, docs/02 §2.6) `zstd` cumple igual
        # el presupuesto de 700 ms, pero con menos margen (~30-40 % más lento
        # a escribir y leer que `lz4`, medido con el banco de este módulo)
        # solo para ahorrar unas pocas decenas de MB en un fichero de caché
        # local y desechable, no en el ZIP portable (que es donde sí importa
        # el tamaño, §3.10). Prioriza el presupuesto de tiempo, que es el que
        # tiene puerta de CI.
        pl.DataFrame({"t": t.astype(np.uint32)}).write_parquet(
            _ruta_tiempos(destino, grupo), compression="lz4"
        )
        pl.DataFrame(columnas_por_grupo[grupo]).write_parquet(
            _ruta_piramide(destino, grupo), compression="lz4"
        )

    metadatos = MetadatosCache(clave=clave, canales=tuple(canales_meta))
    _ruta_metadatos(destino).write_text(
        json.dumps(_metadatos_a_dict(metadatos), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Lectura
# --------------------------------------------------------------------------- #
def _reconstruir_piramide_empaquetada(
    tipo: TipoCanalPiramide,
    tabla: pl.DataFrame,
    id_canal: str,
    niveles_meta: tuple[tuple[int, int], ...],
    dtype_valor: type[np.generic],
) -> Piramide:
    """Recorta la(s) columna(s) empaquetada(s) de `id_canal` en los niveles
    originales, usando los offsets acumulados de `niveles_meta`: un `slice`
    de NumPy por nivel (~12), O(tamaño del nivel), sin reagrupar ni filtrar
    sobre la tabla completa.
    """
    limites: list[tuple[int, int, int]] = []  # (factor, inicio, n_cubos)
    inicio = 0
    for factor, n_cubos in niveles_meta:
        limites.append((factor, inicio, n_cubos))
        inicio += n_cubos

    if tipo is TipoCanalPiramide.CONTINUO:
        minimo = tabla[f"{id_canal}__minimo"].to_numpy()
        maximo = tabla[f"{id_canal}__maximo"].to_numpy()
        primero = tabla[f"{id_canal}__primero"].to_numpy()
        ultimo = tabla[f"{id_canal}__ultimo"].to_numpy()
        return [
            NivelPiramide(
                factor=factor,
                minimo=minimo[inicio : inicio + n].astype(dtype_valor),
                maximo=maximo[inicio : inicio + n].astype(dtype_valor),
                primero=primero[inicio : inicio + n].astype(dtype_valor),
                ultimo=ultimo[inicio : inicio + n].astype(dtype_valor),
            )
            for factor, inicio, n in limites
        ]
    if tipo is TipoCanalPiramide.CONTADOR:
        suma_delta = tabla[f"{id_canal}__suma_delta"].to_numpy()
        primero = tabla[f"{id_canal}__primero"].to_numpy()
        ultimo = tabla[f"{id_canal}__ultimo"].to_numpy()
        return [
            NivelContador(
                factor=factor,
                suma_delta=suma_delta[inicio : inicio + n].astype(np.int64),
                primero=primero[inicio : inicio + n].astype(dtype_valor),
                ultimo=ultimo[inicio : inicio + n].astype(dtype_valor),
            )
            for factor, inicio, n in limites
        ]
    if tipo is TipoCanalPiramide.ENUM:
        moda = tabla[f"{id_canal}__moda"].to_numpy()
        hubo_transicion = tabla[f"{id_canal}__hubo_transicion"].to_numpy()
        return [
            NivelEnum(
                factor=factor,
                moda=moda[inicio : inicio + n].astype(dtype_valor),
                hubo_transicion=hubo_transicion[inicio : inicio + n].astype(np.bool_),
            )
            for factor, inicio, n in limites
        ]
    if tipo is TipoCanalPiramide.BITS:
        or_bits = tabla[f"{id_canal}__or_bits"].to_numpy()
        return [
            NivelBits(factor=factor, or_bits=or_bits[inicio : inicio + n].astype(dtype_valor))
            for factor, inicio, n in limites
        ]
    raise AssertionError(f"TipoCanalPiramide no cubierto: {tipo!r}")  # exhaustivo


def _valor_bruto_de_nivel0(tipo: TipoCanalPiramide, nivel0: object) -> np.ndarray:
    """El valor bruto (`ChannelSeries.v`) vive sin pérdida en L0, en el campo
    que cada variante usa para "el valor tal cual" (ver docstring del
    módulo)."""
    if isinstance(nivel0, NivelPiramide):
        return nivel0.primero
    if isinstance(nivel0, NivelContador):
        return nivel0.primero
    if isinstance(nivel0, NivelEnum):
        return nivel0.moda
    if isinstance(nivel0, NivelBits):
        return nivel0.or_bits
    raise AssertionError(f"nivel de pirámide no reconocido: {nivel0!r}")


def leer(origen: Path) -> tuple[list[ChannelSeries], list[Piramide], MetadatosCache]:
    """Lee una caché existente desde `origen`, ruta ya resuelta por quien
    llama. Lanza `FileNotFoundError` si no hay caché ahí -- a diferencia de
    `leer_metadatos`/`es_valida`, que están pensadas para el camino barato de
    "¿hace falta releer el log de verdad?" y por eso no lanzan, `leer` es ya
    la reconstrucción completa: quien la llama debe haber comprobado antes
    que la caché es válida.
    """
    metadatos = leer_metadatos(origen)
    if metadatos is None:
        raise FileNotFoundError(f"no hay caché (metadatos) en {origen}")

    t_por_grupo: dict[str, np.ndarray] = {}
    tabla_piramide_por_grupo: dict[str, pl.DataFrame] = {}

    series: list[ChannelSeries] = []
    piramides: list[Piramide] = []

    for m in metadatos.canales:
        if m.grupo not in t_por_grupo:
            tabla_t = pl.read_parquet(_ruta_tiempos(origen, m.grupo))
            t_por_grupo[m.grupo] = tabla_t["t"].to_numpy().astype(np.uint32)
        if m.grupo not in tabla_piramide_por_grupo:
            tabla_piramide_por_grupo[m.grupo] = pl.read_parquet(_ruta_piramide(origen, m.grupo))

        storage = Storage[m.storage]
        dtype_valor = _DTYPE_POR_STORAGE[storage]
        tipo = TipoCanalPiramide[m.tipo_piramide]

        niveles = _reconstruir_piramide_empaquetada(
            tipo, tabla_piramide_por_grupo[m.grupo], m.id_canal, m.niveles, dtype_valor
        )
        piramides.append(niveles)

        v = _valor_bruto_de_nivel0(tipo, niveles[0]).astype(dtype_valor)
        key = ChannelKey(
            rol=m.key_rol,
            formato=m.formato,
            id_nativo=m.id_nativo,
            nombre_normalizado=m.nombre_normalizado,
        )
        series.append(
            ChannelSeries(
                key=key,
                role=m.role,
                t=t_por_grupo[m.grupo],
                v=v,
                storage=storage,
                to_canon=Afin(m.to_canon_a, m.to_canon_b),
                dimension=m.dimension,
            )
        )

    return series, piramides, metadatos


# --------------------------------------------------------------------------- #
# Banco de rendimiento (F1-11): datos sintéticos + medición del ciclo
# escribir+leer, para que `tools/banco.py` mida el presupuesto
# `segunda_apertura` (`docs/02-alcance-y-plan.md` §2.6, <= 700 ms) llamando a
# funciones públicas de este módulo en vez de reimplementar la generación de
# datos. NO se integra aquí con `tools/banco.py` (ver informe de la tarea):
# son funciones de librería, listas para que un subcomando las llame.
# --------------------------------------------------------------------------- #
def _valores_sinteticos(storage: Storage, n: int, rng: np.random.Generator) -> np.ndarray:
    if storage is Storage.INT32_SCALED:
        return rng.integers(-32768, 32767, size=n).astype(np.int32)
    if storage is Storage.FLOAT32:
        return rng.normal(size=n).astype(np.float32)
    if storage is Storage.FLOAT64:
        return rng.normal(size=n).astype(np.float64)
    if storage is Storage.ENUM_U16:
        return rng.integers(0, 8, size=n).astype(np.uint16)
    if storage is Storage.BITS_U32:
        return rng.integers(0, 2**16, size=n, dtype=np.uint32)
    raise AssertionError(f"Storage no cubierto: {storage!r}")  # exhaustivo


def generar_series_sinteticas(
    *, n_canales: int = 16, n_muestras: int = 5_000_000, semilla: int = 0
) -> tuple[list[ChannelSeries], list[Piramide]]:
    """`n_canales` `ChannelSeries` sintéticas de `n_muestras` puntos cada una,
    con su pirámide ya construida, repartidas por igual entre las cuatro
    variantes de `TipoCanalPiramide` (todas comparten el mismo `t`, un único
    grupo de muestreo -- el caso más favorable y también el más común en
    datos reales según `almacen.py`).

    Escenario "16 canales × 5 M puntos" por omisión: el mismo que usa
    `docs/02-alcance-y-plan.md` §2.6 para `fps_pan_zoom`, así que este banco
    mide en el mismo orden de magnitud que le importa al presupuesto de
    segunda apertura, sin depender de un log real ni de las tareas F1-01..
    F1-08 (parseo/roles), que son las que de verdad producen `ChannelSeries`
    en producción.
    """
    rng = np.random.default_rng(semilla)
    t = np.arange(n_muestras, dtype=np.uint32)
    variantes = (
        (Storage.INT32_SCALED, TipoCanalPiramide.CONTINUO),
        (Storage.INT32_SCALED, TipoCanalPiramide.CONTADOR),
        (Storage.ENUM_U16, TipoCanalPiramide.ENUM),
        (Storage.BITS_U32, TipoCanalPiramide.BITS),
    )

    series: list[ChannelSeries] = []
    piramides: list[Piramide] = []
    for i in range(n_canales):
        storage, tipo = variantes[i % len(variantes)]
        valores = _valores_sinteticos(storage, n_muestras, rng)
        key = ChannelKey(rol=None, formato="sintetico", id_nativo=str(i), nombre_normalizado=None)
        series.append(
            ChannelSeries(
                key=key,
                role=None,
                t=t,
                v=valores,
                storage=storage,
                to_canon=Afin(1.0),
                dimension=None,
            )
        )
        piramides.append(construir_piramide(valores, tipo=tipo))
    return series, piramides


def medir_ciclo_escritura_lectura(
    destino: Path,
    clave: ClaveInvalidacion,
    series: Sequence[ChannelSeries],
    piramides: Sequence[Piramide],
) -> dict[str, float]:
    """Mide el tiempo de `escribir` + `leer` sobre datos ya construidos (no
    incluye construir las `ChannelSeries` ni las pirámides -- eso lo miden ya
    los bancos de F1-02/F1-09/F1-10). Es la pieza que un futuro subcomando de
    `tools/banco.py` puede llamar para medir el presupuesto
    `segunda_apertura` (<= 700 ms): mide la parte de E/S de la caché en sí,
    que es la que este módulo controla; el presupuesto completo de "segunda
    apertura" en producción incluye además el resto de la apertura en
    `dlv-api`/`dlv-ui`, fuera del alcance de `dlv-core`.
    """
    t0 = time.perf_counter()
    escribir(destino, clave, series, piramides)
    t_escritura = time.perf_counter() - t0

    t0 = time.perf_counter()
    leer(destino)
    t_lectura = time.perf_counter() - t0

    return {
        "escritura_ms": t_escritura * 1000.0,
        "lectura_ms": t_lectura * 1000.0,
        "total_ms": (t_escritura + t_lectura) * 1000.0,
    }
