"""Estructura de un CSV genérico: preámbulo, nombres, unidades y datos (FG-03).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.4, pasos 6 y 7. Cierra la
cadena de sondeo que empieza en FG-01 (delimitador y comillas) y sigue en FG-02
(separador decimal): sin saber qué es un número no se puede decir dónde empiezan
los datos, así que este módulo consume los dos anteriores en vez de repetir su
trabajo.

    FG-01  ¿cómo se parte cada línea?
    FG-02  ¿qué es un número?
    FG-03  ¿qué línea es qué?          ← esto

QUÉ DECIDE Y QUÉ NO
===================
Decide **qué papel tiene cada línea**: cuáles son preámbulo, cuál trae los
nombres, si hay fila de unidades y dónde empiezan los datos. **No resuelve las
unidades**: extraer `°C` de `CLT (°C)` y traducirlo contra el catálogo de alias es
FG-06, y meterlo aquí lo dejaría sin el diccionario de alias que esa tarea
aporta. Aquí las unidades declaradas salen **en crudo**, tal como están escritas.

LA REGLA DE §7.4 PASO 6, Y POR QUÉ NO BASTA LA DEL SONDEO
=========================================================
FG-01 ya devuelve `linea_inicio_datos`: dónde empieza el bloque de líneas con el
mismo número de campos. **Eso no es el inicio de los datos.** La fila de nombres
tiene el mismo número de campos que los datos —para eso es una cabecera— así que
cae dentro del mismo bloque. En `02-puntoycoma-coma.csv` el bloque consistente
empieza en la línea 0, que es `Time;RPM;MAP;…`.

La regla que sí separa es la del paso 6: la primera línea de datos es la primera
**cuyos campos son mayoritariamente numéricos**, y la anterior son los nombres.
Es una regla sobre el CONTENIDO de las celdas, no sobre cuántas hay, y por eso
necesita el separador decimal de FG-02: con la interpretación equivocada,
`0,050;1456` no es numérico y la primera fila de datos parecería otra cabecera.

LA FILA DE UNIDADES ES UNA HEURÍSTICA, Y SE DICE
================================================
§7.4: «si entre nombres y datos hay una línea no numérica y corta, es fila de
unidades». Corta es la clave: `s,rpm,kPa,%,C,ratio` son unidades;
`Notas del piloto,Vuelta de calentamiento,…` no lo es, aunque también sea texto.
Aquí «corta» es `MAX_LARGO_UNIDAD` caracteres por celda, y cuando una línea entra
por los pelos se avisa: es la decisión menos fundada de este módulo y el usuario
tiene que poder discrepar en el asistente.

Solo biblioteca estándar. Este módulo no abre ficheros.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from dlv_core.formatos.decimal_csv import Decimales, es_numerica
from dlv_core.formatos.sondeo import Sondeo, dividir_campos
from dlv_core.informes import Aviso

__all__ = [
    "FRACCION_NUMERICA_MINIMA",
    "MAX_LARGO_UNIDAD",
    "ErrorDeEstructura",
    "Estructura",
    "analizar_estructura",
]

#: Fracción de celdas que tienen que ser numéricas para que una línea sea de
#: datos. No es 1,0 a propósito: `11-valores-ausentes.csv` trae `#N/A` en medio de
#: filas de datos perfectamente buenas, y una fila con un centinela de texto sigue
#: siendo una fila de datos. Tampoco es 0,5: con la mitad de las celdas numéricas
#: una fila puede ser todavía una cabecera con columnas numeradas
#: (`Tiempo,1,2,3`).
FRACCION_NUMERICA_MINIMA = 0.7

#: Longitud máxima de una celda para que la línea pueda ser fila de unidades.
#: `s`, `rpm`, `kPa`, `%`, `C`, `ratio`, `deg/s`, `L/100km` caben de sobra; una
#: frase, no.
MAX_LARGO_UNIDAD = 12

#: `clave: valor` o `clave = valor` en el preámbulo (§7.4 paso 7). Se busca sobre
#: la línea CRUDA y no sobre los campos ya partidos: `notes: cambios, y más` tiene
#: una coma dentro y partirla por el delimitador rompería el valor.
_METADATO = re.compile(r"^\s*([^:=]{1,60}?)\s*[:=]\s*(.*?)\s*$")


class ErrorDeEstructura(ValueError):
    """No se puede reconocer la estructura de este fichero sin inventar."""


@dataclass(slots=True, frozen=True)
class Estructura:
    """Qué papel tiene cada línea del fichero. Una propuesta para el asistente."""

    linea_inicio_datos: int
    """Índice (0-based, sobre las líneas no vacías) de la primera fila de datos."""

    linea_nombres: int | None
    """La línea anterior a los datos, o `None` si los datos empiezan en la
    primera línea del fichero. `None` **no** significa «no la he buscado»."""

    linea_unidades: int | None
    nombres: tuple[str, ...]
    unidades_declaradas: tuple[str, ...]
    """Las celdas de la fila de unidades, **en crudo**: `('s', 'rpm', 'kPa', …)`.
    Resolverlas contra el catálogo de alias es FG-06."""

    preambulo: tuple[str, ...]
    """Las líneas anteriores a los nombres, crudas y en orden."""

    metadatos: Mapping[str, str]
    """Las líneas del preámbulo que tienen forma `clave: valor` o `clave = valor`.
    Las que no la tienen se quedan solo en `preambulo`: inventarles una clave
    sería fabricar metadatos que el fichero no declara."""

    n_columnas: int
    filas_de_datos_vistas: int
    avisos: tuple[Aviso, ...] = ()

    @property
    def tiene_nombres(self) -> bool:
        return self.linea_nombres is not None

    @property
    def tiene_fila_de_unidades(self) -> bool:
        return self.linea_unidades is not None

    def nombres_o_posicionales(self, prefijo: str = "col") -> tuple[str, ...]:
        """Los nombres, o `col_1…col_N` si el fichero no traía ninguno.

        Fabricar nombres es una decisión del que llama, no de este módulo, y por
        eso hay que pedirla explícitamente en vez de recibirla en `nombres`. Un
        `nombres` relleno de `col_3` sería indistinguible de un fichero que de
        verdad llama `col_3` a una columna.
        """
        if self.nombres:
            return self.nombres
        return tuple(f"{prefijo}_{i + 1}" for i in range(self.n_columnas))


@dataclass(slots=True)
class _Acumulador:
    avisos: list[Aviso] = field(default_factory=list)

    def avisa(self, codigo: str, mensaje: str) -> None:
        self.avisos.append(Aviso(codigo, mensaje))


def _fraccion_numerica(campos: Sequence[str], decimal: str) -> float:
    """Fracción de celdas NO VACÍAS que son números.

    Las vacías se excluyen del denominador en vez de contarlas como numéricas:
    una fila con tres celdas vacías y una `0.5` es de datos, pero una fila
    completamente vacía no tiene por qué serlo, y contando las vacías como
    numéricas saldría 1,0.
    """
    llenas = [c for c in campos if c.strip()]
    if not llenas:
        return 0.0
    return sum(1 for c in llenas if es_numerica(c, decimal)) / len(llenas)


def _parece_fila_de_unidades(campos: Sequence[str], decimal: str) -> bool:
    """§7.4: «una línea no numérica y corta» entre los nombres y los datos."""
    llenas = [c.strip() for c in campos if c.strip()]
    if not llenas:
        return False
    if any(es_numerica(c, decimal) for c in llenas):
        # Una unidad no es un número. `s,rpm,2,kPa` es otra cosa.
        return False
    return all(len(c) <= MAX_LARGO_UNIDAD for c in llenas)


def analizar_estructura(sondeo: Sondeo, decimales: Decimales, texto: str) -> Estructura:
    """Reparte las líneas en preámbulo, nombres, unidades y datos (§7.4 pasos 6-7).

    `sondeo` y `decimales` son los resultados de FG-01 y FG-02 sobre el mismo
    `texto`. Se reciben en vez de recalcularse para que cada decisión se tome en
    un solo sitio: si este módulo volviera a elegir el delimitador, un día
    elegiría otro distinto que el que se usó para leer el fichero.
    """
    if sondeo.delimitador is None:
        raise ErrorDeEstructura(
            "el sondeo no propuso delimitador, así que no hay campos que repartir. "
            "Hay que elegirlo en el asistente antes de reconocer la estructura"
        )
    lineas = [linea for linea in texto.splitlines() if linea.strip()]
    if not lineas:
        raise ErrorDeEstructura("el fichero no tiene ninguna línea con contenido")

    ac = _Acumulador()
    campos_por_linea = [
        dividir_campos(linea, sondeo.delimitador, sondeo.comilla) for linea in lineas
    ]

    # Paso 6: la primera línea mayoritariamente numérica. Se busca DESDE el
    # principio y no desde `sondeo.linea_inicio_datos`: ese es el inicio del
    # bloque con el mismo número de campos, que incluye la fila de nombres.
    inicio: int | None = None
    for i, campos in enumerate(campos_por_linea):
        if _fraccion_numerica(campos, decimales.separador) >= FRACCION_NUMERICA_MINIMA:
            inicio = i
            break

    if inicio is None:
        raise ErrorDeEstructura(
            "ninguna línea tiene mayoritariamente celdas numéricas, así que no se "
            f"reconoce dónde empiezan los datos (separador decimal supuesto: "
            f"{decimales.separador!r}). Puede ser un fichero de texto, o el separador "
            "decimal puede estar mal propuesto"
        )

    # Paso 6, segunda mitad: la fila de unidades, entre los nombres y los datos.
    #
    # «No numérica y corta» NO basta, y este fue un defecto propio: una fila de
    # NOMBRES es también no numérica y corta (`Time,RPM,MAP,TPS,CLT,Lambda`), así
    # que la cabecera se tomaba por fila de unidades y la última línea del
    # preámbulo pasaba a ser «los nombres». En `14-preambulo-largo.csv` los
    # nombres salían de `notes: Practice session with setup changes`.
    #
    # La condición que sí separa es estructural, no de longitud: una fila de
    # unidades está DENTRO del bloque consistente, y por encima tiene que haber
    # OTRA línea del bloque (los nombres). Un `boost: 1.6 bar` del preámbulo tiene
    # un campo, no seis, así que no puede hacer de fila de nombres. La longitud se
    # queda como segunda guarda: con dos líneas de texto en el bloque —una nota
    # del piloto encima de los datos— es lo único que distingue unidades de prosa.
    n_columnas_datos = len(campos_por_linea[inicio])
    linea_unidades: int | None = None
    unidades: tuple[str, ...] = ()
    if (
        inicio >= 2
        and len(campos_por_linea[inicio - 1]) == n_columnas_datos
        and len(campos_por_linea[inicio - 2]) == n_columnas_datos
        and _parece_fila_de_unidades(campos_por_linea[inicio - 1], decimales.separador)
        # Y la línea que haría de NOMBRES no puede tener forma de metadato. Es la
        # tercera condición, y también salió de un fallo: `notes: cambios de
        # reglaje, y una vuelta de calentamiento` tiene dos campos con delimitador
        # `,`, igual que los datos, así que pasaba las dos condiciones anteriores y
        # `Time,RPM` acababa siendo la «fila de unidades». Una línea con forma
        # `clave: valor` es preámbulo (§7.4 paso 7), no una cabecera.
        and _METADATO.match(lineas[inicio - 2]) is None
        and _METADATO.match(lineas[inicio - 1]) is None
    ):
        candidata = inicio - 1
        linea_unidades = candidata
        unidades = tuple(c.strip() for c in campos_por_linea[candidata])
        largo_max = max((len(c.strip()) for c in campos_por_linea[candidata]), default=0)
        if largo_max > MAX_LARGO_UNIDAD // 2:
            ac.avisa(
                "fila_de_unidades_dudosa",
                f"la línea {candidata + 1} se ha tomado por fila de unidades porque está "
                f"en el bloque de datos, no es numérica y sus celdas son cortas, pero la "
                f"más larga tiene {largo_max} caracteres. Es la decisión menos fundada "
                "del sondeo: confírmala en el asistente",
            )
    elif (
        inicio == 1
        and len(campos_por_linea[0]) == n_columnas_datos
        and _parece_fila_de_unidades(campos_por_linea[0], decimales.separador)
    ):
        # Solo hay una línea delante de los datos y podría ser de unidades. Gana
        # «nombres»: sin nombres no hay selector de canales, así que unos nombres
        # raros son más útiles que unas unidades sin nombres a las que pegarlas.
        # Solo se avisa cuando de verdad parecen unidades y no nombres, para no
        # avisar en el caso normal (una cabecera es siempre corta y no numérica).
        if all(len(c.strip()) <= MAX_LARGO_UNIDAD // 2 for c in campos_por_linea[0] if c.strip()):
            ac.avisa(
                "unidades_o_nombres_ambiguo",
                "la única línea antes de los datos es corta y no numérica, así que podría "
                "ser una fila de unidades o la de nombres. Se toma como nombres: sin "
                "nombres no hay selector de canales",
            )

    candidato_nombres = (linea_unidades - 1) if linea_unidades is not None else inicio - 1
    linea_nombres: int | None = candidato_nombres
    if candidato_nombres < 0:
        linea_nombres = None  # los datos empiezan en la primera línea
        ac.avisa(
            "sin_fila_de_nombres",
            "los datos empiezan en la primera línea del fichero: no hay fila de nombres. "
            "Las columnas se identificarán por posición hasta que el usuario les ponga "
            "nombre",
        )
    elif (
        _METADATO.match(lineas[candidato_nombres]) is not None
        and len(campos_por_linea[candidato_nombres]) != n_columnas_datos
    ):
        # Una línea con forma `clave: valor` y un número de campos distinto al de
        # los datos es preámbulo, no una cabecera — aunque esté pegada a los datos.
        # Es el caso del formato nativo por el camino genérico: la última línea
        # antes de los datos del AutoLog es `Log : 20260729 06:30:35`, y tomarla
        # por cabecera dejaba un solo «nombre» para 476 columnas.
        #
        # Se exige que el número de campos NO cuadre porque una cabecera puede
        # llevar dos puntos legítimamente (`Time:s,RPM:rpm`), y ahí la forma de
        # metadato es casualidad.
        linea_nombres = None
        ac.avisa(
            "sin_fila_de_nombres",
            f"la línea anterior a los datos ({lineas[candidato_nombres][:40]!r}) tiene "
            "forma de metadato y no cuadra con el número de columnas: se trata como "
            "preámbulo y el fichero se queda sin fila de nombres. Las columnas se "
            "identificarán por posición",
        )

    nombres = (
        tuple(c.strip() for c in campos_por_linea[linea_nombres])
        if linea_nombres is not None
        else ()
    )
    # El preámbulo llega hasta los nombres si los hay; si no, hasta la fila de
    # unidades, y si tampoco, hasta los datos.
    fin_preambulo = (
        linea_nombres
        if linea_nombres is not None
        else (linea_unidades if linea_unidades is not None else inicio)
    )
    preambulo = tuple(lineas[:fin_preambulo])
    metadatos = _metadatos_de(preambulo, ac)

    _avisos_de_coherencia(nombres, unidades, n_columnas_datos, inicio, len(lineas), ac)

    return Estructura(
        linea_inicio_datos=inicio,
        linea_nombres=linea_nombres,
        linea_unidades=linea_unidades,
        nombres=nombres,
        unidades_declaradas=unidades,
        preambulo=preambulo,
        metadatos=metadatos,
        n_columnas=n_columnas_datos,
        filas_de_datos_vistas=len(lineas) - inicio,
        avisos=tuple(ac.avisos),
    )


def _metadatos_de(preambulo: Sequence[str], ac: _Acumulador) -> dict[str, str]:
    """`clave: valor` y `clave = valor` del preámbulo (§7.4 paso 7)."""
    metadatos: dict[str, str] = {}
    sueltas = 0
    for linea in preambulo:
        m = _METADATO.match(linea)
        if m is None:
            sueltas += 1
            continue
        clave, valor = m.group(1).strip(), m.group(2).strip()
        if clave in metadatos:
            ac.avisa(
                "metadato_repetido",
                f"el metadato '{clave}' aparece más de una vez en el preámbulo; se queda el último",
            )
        metadatos[clave] = valor
    if sueltas:
        ac.avisa(
            "preambulo_sin_forma_de_metadato",
            f"{sueltas} línea(s) del preámbulo no tienen forma 'clave: valor' ni "
            "'clave = valor'; se conservan como texto pero no se les inventa una clave",
        )
    return metadatos


def _avisos_de_coherencia(
    nombres: Sequence[str],
    unidades: Sequence[str],
    n_columnas: int,
    inicio: int,
    total_lineas: int,
    ac: _Acumulador,
) -> None:
    if nombres and len(nombres) != n_columnas:
        ac.avisa(
            "nombres_descuadrados",
            f"la fila de nombres tiene {len(nombres)} celdas y las de datos "
            f"{n_columnas}. Las columnas sin nombre se identificarán por posición",
        )
    if unidades and len(unidades) != n_columnas:
        ac.avisa(
            "unidades_descuadradas",
            f"la fila de unidades tiene {len(unidades)} celdas y las de datos {n_columnas}",
        )
    if nombres:
        vistos: dict[str, int] = {}
        repetidos: list[str] = []
        for i, nombre in enumerate(nombres):
            if nombre in vistos:
                repetidos.append(f"'{nombre}' (columnas {vistos[nombre] + 1} y {i + 1})")
            vistos[nombre] = i
        if repetidos:
            # No se renombra: §1.3 dice que la identidad del canal no es el
            # nombre. Renombrar a `RPM_2` inventaría un nombre que el fichero no
            # tiene y que el usuario no reconocería.
            ac.avisa(
                "nombres_duplicados",
                f"hay nombres de columna repetidos: {', '.join(repetidos)}. No se "
                "renombran; la identidad de la columna es su posición",
            )
        vacios = [i + 1 for i, nombre in enumerate(nombres) if not nombre]
        if vacios:
            ac.avisa(
                "nombres_vacios",
                f"las columnas {vacios} no tienen nombre en la fila de cabecera",
            )
    if total_lineas - inicio < 2:
        ac.avisa(
            "muy_pocas_filas_de_datos",
            f"solo se ha visto {total_lineas - inicio} fila(s) de datos en la muestra: "
            "la estructura propuesta se apoya en muy poca evidencia",
        )
