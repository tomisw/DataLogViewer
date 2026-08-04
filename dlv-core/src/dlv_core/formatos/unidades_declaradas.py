"""Unidad declarada en el nombre de columna o en la fila de unidades (FG-06).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.6. Cierra la cadena que
empieza en FG-01 (delimitador), sigue en FG-02 (separador decimal) y en FG-03
(qué papel tiene cada línea): `estructura.py` ya reparte `nombres` y
`unidades_declaradas`, pero deja las unidades **en crudo**, tal como están
escritas — su propio docstring dice explícitamente que resolverlas es esta
tarea, y por qué: sin el diccionario de alias que este módulo aporta, meterlo
allí habría dejado una sola tabla de resolución partida en dos sitios.

    FG-01  ¿cómo se parte cada línea?
    FG-02  ¿qué es un número?
    FG-03  ¿qué línea es qué?
    FG-06  ¿qué significa la unidad que trae cada columna?   ← esto

DOS FORMAS DE DECLARAR LA UNIDAD, Y LO QUE LAS DISTINGUE
=========================================================
§7.6 da dos sintaxis:

    RPM [rpm]                     ← unidad dentro del propio nombre
    Time,RPM,MAP                  ← fila de nombres
    s,rpm,kPa                     ← fila de unidades (FG-03 ya la separó)

y una tercera, "tras `_`", que es deliberadamente más débil que las otras dos:
`[...]` y `(...)` son delimitadores que anuncian una unidad, así que se leen como
tal aunque el catálogo no la reconozca después. Un `_` suelto no lo es:
`Fuel_Trim` no declara una unidad "Trim" aunque tenga la misma forma que
`RPM_rpm`. Por eso el nombre solo se separa por `_` cuando el trozo final SÍ
resuelve contra el catálogo; si no resuelve, la columna se trata como si no
hubiera declarado nada por esa vía. Es la aplicación literal de "si es ambiguo,
la opción conservadora": partir un nombre que no era una unidad sería inventar
una unidad allí donde no la había.

UN PARÉNTESIS TAMBIÉN PUEDE SER UN CALIFICADOR, NO UNA UNIDAD
==============================================================
`Lambda (Sensor 1)`, `Boost (gauge)`, `Temp (Bank 1)` son nombres de columna
reales de exportador, y su paréntesis no es una unidad. Que `(...)` anuncie una
unidad no puede convertirse en dos daños cuando el contenido no resuelve:

1. **No se recorta el nombre.** El nombre limpio solo pierde el `[...]`/`(...)`
   cuando lo que había dentro resolvió de verdad. Si no, se queda entero: dos
   columnas `Lambda (Sensor 1)` y `Lambda (Sensor 2)` no pueden acabar las dos
   rotuladas «Lambda», que es lo que pasaba al recortar sin condición — el mismo
   argumento que ya justifica la regla del `_`, aplicado a las otras dos vías.
2. **No se tira la fila de unidades.** Si el nombre declara algo que no resuelve
   y la fila de unidades de esa columna SÍ resuelve, gana la fila. No es
   adivinar: las dos son declaraciones escritas en el fichero, y una de ellas
   apunta a una unidad real. Descartarla dejaría la columna en crudo cuando el
   fichero decía exactamente qué era.

La precedencia "gana el nombre" de §7.6 sigue intacta donde importa: cuando las
dos vías resuelven y discrepan, gana el nombre.

LA REGLA DE R1 ES LA RAZÓN DE SER DE ESTE MÓDULO
=================================================
§7.6, último párrafo: "si la unidad no se puede resolver, la dimensión queda
`unknown`, se muestra el valor en crudo y el selector de unidad se desactiva".
Este módulo NUNCA elige la unidad "que se parece": o la cadena cruda coincide
—exactamente, sensible a mayúsculas— con un id de `data/units.toml` o con un
alias de allí o de `data/alias_unidades.toml`, o se queda sin resolver. Adivinar
aquí es el mismo riesgo R1 que ya protege `roles.toml` con la asignación difusa
(docs/07 §7.15): un tuner que ve un número con la unidad equivocada no tiene
forma de saber que está mal.

LA COLISIÓN QUE HAY QUE DESAMBIGUAR: LA MISMA CADENA EN DOS DIMENSIONES
========================================================================
`rpm` es la unidad canónica de `angular_speed` y también una unidad válida de
`frequency`; `Hz` es al revés. `g` aparece en `mass`, `mass_per_cyl` y
`acceleration` sin ganador claro. La regla: si una cadena cruda resuelve en más
de una dimensión, gana la dimensión para la que esa unidad es su CANÓNICA
(`rpm` → `angular_speed`, `Hz` → `frequency`); si ninguna o más de una dimensión
gana por esa vía —el caso de `g`—, la cadena se trata como no resuelta. Preferir
"no resuelta" a una desambiguación arbitraria es la misma regla de R1 aplicada
a un empate en vez de a un desconocido.

`dlv-core` no abre ficheros por su cuenta (ADR-002): `cargar_alias` recibe el
fichero ya abierto en binario, igual que `unidades.cargar_catalogo`.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import IO

from dlv_core.informes import Aviso
from dlv_core.unidades import Catalogo, ErrorDeUnidad

__all__ = [
    "ErrorDeAliasDeUnidad",
    "OrigenUnidad",
    "ResultadoUnidadesDeclaradas",
    "UnidadDeColumna",
    "cargar_alias",
    "extraer_unidad_de_nombre",
    "resolver_unidades_declaradas",
]

#: Longitud máxima del contenido de `[...]` / `(...)` para que cuente como
#: unidad. Generosa a propósito: `deg C`, `L/100km`, `periodo_us` tienen que
#: caber, y una etiqueta de eje larga («Presión de aceite») no.
_MAX_LARGO_UNIDAD_EN_NOMBRE = 24

#: Longitud máxima del trozo final tras `_` para que se considere candidato.
#: Más corta que la de arriba porque aquí NO hay delimitador que lo marque como
#: unidad: cuanto más corto el candidato, menos probable que sea casualidad
#: («Fuel_Trim» tiene un final de 4 letras; un final de unidad real —rpm, kPa,
#: degC— rara vez pasa de 6).
_MAX_LARGO_CANDIDATO_GUION_BAJO = 8

#: `Nombre [unidad]` — el contenido no puede llevar corchetes propios, y tiene
#: que estar pegado al final tras espacio opcional.
_RE_CORCHETE = re.compile(
    r"^(?P<nombre>.*\S)\s*\[(?P<unidad>[^\[\]]{1," + str(_MAX_LARGO_UNIDAD_EN_NOMBRE) + r"})\]\s*$"
)

#: `Nombre (unidad)` — mismo razonamiento con paréntesis.
_RE_PARENTESIS = re.compile(
    r"^(?P<nombre>.*\S)\s*\((?P<unidad>[^()]{1," + str(_MAX_LARGO_UNIDAD_EN_NOMBRE) + r"})\)\s*$"
)

#: Forma que puede tener el trozo final tras `_` para ser CANDIDATO a unidad.
#: Solo letras, dígitos y los símbolos que de verdad aparecen en unidades
#: (°, %, µ, Ω, λ, φ, ., /). Un candidato puramente numérico se descarta aparte:
#: `Sensor_1` no declara una unidad "1".
_RE_CANDIDATO_GUION_BAJO = re.compile(
    r"^[A-Za-zµΩλφ°%./0-9]{1," + str(_MAX_LARGO_CANDIDATO_GUION_BAJO) + r"}$"
)


class ErrorDeAliasDeUnidad(ValueError):
    """`data/alias_unidades.toml` es incoherente. No es un fallo de datos del
    fichero que se está importando, es un fallo del propio diccionario."""


class OrigenUnidad(Enum):
    """De dónde salió la unidad cruda de una columna (§7.6)."""

    CORCHETE = "corchete"
    """`Nombre [unidad]`."""

    PARENTESIS = "parentesis"
    """`Nombre (unidad)`."""

    GUION_BAJO = "guion_bajo"
    """`Nombre_unidad`, aceptado solo porque el trozo final resolvió."""

    FILA_DE_UNIDADES = "fila_de_unidades"
    """La unidad venía en la fila que FG-03 identificó como tal."""

    NINGUNA = "ninguna"
    """La columna no declara ninguna unidad por ninguna de las vías anteriores."""


@dataclass(slots=True, frozen=True)
class UnidadDeColumna:
    """El resultado de resolver la unidad de UNA columna.

    `nombre_original` se conserva siempre, aunque `nombre_limpio` le haya
    quitado el `[rpm]` o el `(°C)`: es lo que exige §7.6 —"el nombre original
    hay que conservarlo para mostrarlo"— y lo que permite que un fallo de
    resolución nunca se lleve por delante el rótulo que el usuario reconoce.
    """

    nombre_original: str
    nombre_limpio: str
    unidad_cruda: str | None
    origen: OrigenUnidad
    dimension_id: str | None
    unidad_id: str | None

    @property
    def resuelta(self) -> bool:
        """`True` si hay una `(dimension, unidad)` real detrás de la cadena
        cruda. `False` incluye tanto "no declaró unidad" como "declaró una
        que no se reconoce": las dos acaban en la misma regla de R1 —crudo,
        sin selector— así que no hace falta distinguirlas aquí; el aviso sí
        lo distingue, para quien lea el informe de importación."""
        return self.dimension_id is not None and self.unidad_id is not None


@dataclass(slots=True, frozen=True)
class ResultadoUnidadesDeclaradas:
    """Una `UnidadDeColumna` por columna, en el mismo orden que se recibieron."""

    columnas: tuple[UnidadDeColumna, ...]
    avisos: tuple[Aviso, ...] = ()


def extraer_unidad_de_nombre(nombre: str) -> tuple[str, str | None, OrigenUnidad]:
    """`RPM [rpm]` -> (`RPM`, `rpm`, CORCHETE); `CLT (°C)` -> (`CLT`, `°C`, ...).

    Puramente sintáctica: solo mira `[...]` y `(...)`, y devuelve lo que hay
    dentro sin preguntarle al catálogo si eso es una unidad. Quien llama decide
    qué hacer con el nombre recortado — `resolver_unidades_declaradas` solo lo
    adopta si el contenido resuelve, porque `Lambda (Sensor 1)` tiene esta misma
    forma sin declarar ninguna unidad.

    El `_` no se mira aquí a propósito: para saber si el trozo final es de verdad
    una unidad hay que consultar el catálogo, y eso ya no es sintaxis.

    Si no hay corchete ni paréntesis al final, devuelve el nombre intacto y
    `None`: no se inventa una unidad donde no hay marca de que la haya.
    """
    m = _RE_CORCHETE.match(nombre)
    if m is not None:
        unidad = m.group("unidad").strip()
        if unidad:
            return m.group("nombre"), unidad, OrigenUnidad.CORCHETE
    m = _RE_PARENTESIS.match(nombre)
    if m is not None:
        unidad = m.group("unidad").strip()
        if unidad:
            return m.group("nombre"), unidad, OrigenUnidad.PARENTESIS
    return nombre, None, OrigenUnidad.NINGUNA


def _candidato_tras_guion_bajo(nombre: str) -> tuple[str, str] | None:
    """El trozo final tras el último `_`, si tiene FORMA plausible de unidad.

    Es una guarda sintáctica, no una resolución: acepta `RPM_rpm` y también
    `Fuel_Trim` (ambos tienen forma de "prefijo_palabracorta"). Quien llama
    tiene que comprobar además que el trozo resuelve contra el catálogo antes
    de aceptar la partición — si no, `Fuel_Trim` se convertiría en el nombre
    "Fuel" con una unidad inventada "Trim".
    """
    if "_" not in nombre:
        return None
    prefijo, _, sufijo = nombre.rpartition("_")
    if not prefijo or not sufijo:
        return None
    if sufijo.isdigit():
        return None  # `Sensor_1`: el `1` es un índice, no una unidad.
    if _RE_CANDIDATO_GUION_BAJO.match(sufijo) is None:
        return None
    return prefijo, sufijo


def cargar_alias(fuente: IO[bytes]) -> Mapping[str, tuple[str, str]]:
    """Carga `data/alias_unidades.toml` -> `{forma_cruda: (dimension, unidad)}`.

    `dlv-core` no abre ficheros por su cuenta (ADR-002): recibe el objeto de
    lectura ya abierto en binario, igual que `unidades.cargar_catalogo`.

    No valida aquí que `(dimension, unidad)` exista en `data/units.toml` — esa
    comprobación necesita el catálogo cargado y vive en
    `resolver_unidades_declaradas`, que la hace al construir su índice y falla
    con `ErrorDeUnidad` (no con un `KeyError` crudo) si alguien borra una unidad
    de `units.toml` sin actualizar este fichero.
    """
    bruto = tomllib.load(fuente)
    resultado: dict[str, tuple[str, str]] = {}
    grupos = bruto.get("alias", {})
    for dim_id, unidades in grupos.items():
        if not isinstance(unidades, dict):
            continue
        for uni_id, bloque in unidades.items():
            formas = bloque.get("formas", ())
            for forma_bruta in formas:
                forma = str(forma_bruta)
                destino = (str(dim_id), str(uni_id))
                if forma in resultado and resultado[forma] != destino:
                    raise ErrorDeAliasDeUnidad(
                        f"la forma {forma!r} de data/alias_unidades.toml apunta a la vez a "
                        f"{resultado[forma]} y a {destino}: cada forma tiene que resolver a "
                        "una sola unidad, o la resolución sería ambigua por construcción"
                    )
                resultado[forma] = destino
    return resultado


# Un candidato de resolución: la dimensión, la unidad, y si esa unidad es la
# CANÓNICA de esa dimensión (lo que decide el desempate de la colisión, ver
# docstring del módulo).
_Candidato = tuple[str, str, bool]


def _construir_indice(
    catalogo: Catalogo, alias: Mapping[str, tuple[str, str]]
) -> dict[str, list[_Candidato]]:
    """`{cadena_cruda: [(dimension, unidad, es_canonica), ...]}`.

    Fusiona tres fuentes en un único índice de búsqueda: los ids de
    `units.toml`, los alias que YA declara cada unidad de `units.toml`
    (`Dimension.alias`, que `unidades.cargar_catalogo` ya resolvió), y los de
    `data/alias_unidades.toml`. Buscar en un solo índice es lo que garantiza que
    un id y un alias de cualquier procedencia se desambiguan con la MISMA regla.
    """
    indice: dict[str, list[_Candidato]] = {}

    def _anota(cadena: str, dim_id: str, uni_id: str) -> None:
        canon = uni_id == catalogo.dimension(dim_id).unidad_canonica
        indice.setdefault(cadena, []).append((dim_id, uni_id, canon))

    for dim_id, dim in catalogo.dimensiones.items():
        for uni_id in dim.unidades:
            _anota(uni_id, dim_id, uni_id)
        for cadena, uni_id in dim.alias.items():
            _anota(cadena, dim_id, uni_id)

    for cadena, (dim_id, uni_id) in alias.items():
        try:
            catalogo.dimension(dim_id).unidad(uni_id)
        except ErrorDeUnidad as exc:
            raise ErrorDeAliasDeUnidad(
                f"data/alias_unidades.toml declara la forma {cadena!r} hacia "
                f"'{dim_id}.{uni_id}', que no existe en data/units.toml: {exc}"
            ) from exc
        _anota(cadena, dim_id, uni_id)

    return indice


def _resolver_cruda(
    cruda: str, indice: Mapping[str, Sequence[_Candidato]]
) -> tuple[str, str] | None:
    """La cadena cruda -> `(dimension, unidad)`, o `None` si no se puede decidir
    sin adivinar (ni encontrada, ni desambiguada de un empate)."""
    candidatos = indice.get(cruda)
    if not candidatos:
        return None
    if len(candidatos) == 1:
        dim_id, uni_id, _ = candidatos[0]
        return dim_id, uni_id
    canonicos = [(dim_id, uni_id) for dim_id, uni_id, es_canon in candidatos if es_canon]
    if len(canonicos) == 1:
        return canonicos[0]
    return None  # Empate sin desempate posible (el caso de "g"): no se adivina.


def resolver_unidades_declaradas(
    nombres: Sequence[str],
    unidades_declaradas: Sequence[str],
    catalogo: Catalogo,
    alias: Mapping[str, tuple[str, str]],
) -> ResultadoUnidadesDeclaradas:
    """Une nombre-con-unidad-embebida y fila-de-unidades en un resultado por
    columna, resolviendo cada unidad cruda contra `catalogo` + `alias`.

    `nombres` y `unidades_declaradas` son los campos homónimos de
    `formatos.estructura.Estructura` (o `nombres_o_posicionales()` si el
    fichero no traía cabecera: sin nombre no hay `[...]`/`(...)`/`_` que mirar,
    pero la fila de unidades, si existe, sigue siendo válida por columna).
    `unidades_declaradas` puede ser más corta que `nombres` (fichero sin fila de
    unidades) o tener celdas vacías por descuadre; ambos casos se tratan como
    "esta columna no tiene unidad por esa vía", nunca como un error.

    Precedencia cuando las DOS vías resuelven y discrepan: gana la del nombre.
    Es más específica —viene pegada al propio canal— y se avisa de la
    discrepancia en vez de descartarla en silencio. Si la del nombre NO resuelve
    y la de la fila sí, gana la fila (ver el docstring del módulo: un paréntesis
    puede ser un calificador, y tirar la fila dejaría en crudo una columna que el
    fichero sí había declarado).
    """
    indice = _construir_indice(catalogo, alias)
    columnas: list[UnidadDeColumna] = []
    avisos: list[Aviso] = []

    for i, nombre in enumerate(nombres):
        cruda_de_fila = (
            unidades_declaradas[i].strip()
            if i < len(unidades_declaradas) and unidades_declaradas[i].strip()
            else None
        )
        recortado, cruda_de_nombre, origen_de_nombre = extraer_unidad_de_nombre(nombre)
        res_de_nombre = _resolver_cruda(cruda_de_nombre, indice) if cruda_de_nombre else None
        res_de_fila = _resolver_cruda(cruda_de_fila, indice) if cruda_de_fila else None

        nombre_limpio = nombre
        cruda: str | None = None
        origen = OrigenUnidad.NINGUNA
        resolucion: tuple[str, str] | None = None

        if res_de_nombre is not None:
            # El nombre declara una unidad real: es la más específica y gana.
            # Solo aquí se recorta el nombre, porque solo aquí consta que lo
            # recortado era una unidad y no un calificador.
            nombre_limpio, cruda, origen, resolucion = (
                recortado,
                cruda_de_nombre,
                origen_de_nombre,
                res_de_nombre,
            )
            if cruda_de_fila is not None and cruda_de_fila != cruda_de_nombre:
                avisos.append(
                    Aviso(
                        "unidad_declarada_dos_veces",
                        f"la columna '{nombre}' declara la unidad en el nombre "
                        f"({cruda_de_nombre!r}) y también en la fila de unidades "
                        f"({cruda_de_fila!r}); gana la del nombre, más específica",
                    )
                )
        elif cruda_de_nombre is not None and res_de_fila is not None:
            # El paréntesis o corchete del nombre no era una unidad reconocible,
            # pero la fila de unidades de esta columna sí lo es: se usa la fila y
            # el nombre se queda entero.
            cruda, origen, resolucion = cruda_de_fila, OrigenUnidad.FILA_DE_UNIDADES, res_de_fila
            avisos.append(
                Aviso(
                    "unidad_del_nombre_no_resuelta",
                    f"la columna '{nombre}' lleva {cruda_de_nombre!r} entre delimitadores, que "
                    "no es una unidad del catálogo; se usa la de la fila de unidades "
                    f"({cruda_de_fila!r}) y el nombre se conserva completo",
                )
            )
        elif cruda_de_nombre is not None:
            # Ninguna de las dos vías resuelve. Se informa de lo que el nombre
            # decía —es la declaración más específica— sin recortarlo.
            cruda, origen = cruda_de_nombre, origen_de_nombre
        elif cruda_de_fila is not None:
            cruda, origen, resolucion = cruda_de_fila, OrigenUnidad.FILA_DE_UNIDADES, res_de_fila
        else:
            # Último recurso: el trozo final tras `_`, aceptado SOLO si resuelve.
            # Aceptarlo sin esa condición partiría nombres normales con guion
            # bajo que no declaran unidad (`Fuel_Trim`, `Sensor_Voltage_1`).
            candidato = _candidato_tras_guion_bajo(nombre)
            if candidato is not None:
                prefijo, sufijo = candidato
                res_de_sufijo = _resolver_cruda(sufijo, indice)
                if res_de_sufijo is not None:
                    nombre_limpio, cruda, origen, resolucion = (
                        prefijo,
                        sufijo,
                        OrigenUnidad.GUION_BAJO,
                        res_de_sufijo,
                    )

        if cruda is not None and resolucion is None:
            if cruda in indice:
                avisos.append(
                    Aviso(
                        "unidad_ambigua",
                        f"la columna '{nombre}' declara la unidad {cruda!r}, que existe en "
                        "más de una dimensión del catálogo sin una ganadora clara; se deja "
                        "sin resolver en vez de adivinar cuál. La columna se mostrará en "
                        "crudo, sin selector de unidad",
                    )
                )
            else:
                avisos.append(
                    Aviso(
                        "unidad_no_resuelta",
                        f"la columna '{nombre}' declara la unidad {cruda!r}, que no está en "
                        "data/units.toml ni en data/alias_unidades.toml. La columna se "
                        "mostrará en crudo, sin selector de unidad (docs/07 §7.6)",
                    )
                )

        columnas.append(
            UnidadDeColumna(
                nombre_original=nombre,
                nombre_limpio=nombre_limpio,
                unidad_cruda=cruda,
                origen=origen,
                dimension_id=resolucion[0] if resolucion is not None else None,
                unidad_id=resolucion[1] if resolucion is not None else None,
            )
        )

    return ResultadoUnidadesDeclaradas(columnas=tuple(columnas), avisos=tuple(avisos))
