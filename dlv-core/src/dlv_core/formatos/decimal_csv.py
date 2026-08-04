"""Separador decimal, con verificación cruzada de interpretaciones (tarea FG-02).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.4, paso 4. La propia
especificación lo llama **«el que más a menudo se hace mal y el más importante en
Europa»**, y con razón: un CSV español típico es `;` con coma decimal, y leerlo
con la configuración anglosajona convierte `12,5` en dos columnas.

POR QUÉ ESTO NO SE DECIDE POR EL DELIMITADOR
============================================
La regla obvia —«si el delimitador es `;`, el decimal es coma»— es una
correlación, no una implicación. Hay exportadores que escriben `;` con punto
decimal (`0.050;1456;217.300`), porque el `;` lo eligió el usuario en un diálogo y
el punto lo puso la biblioteca. Decidir por el delimitador acierta la mayoría de
las veces y falla en silencio el resto, que es el peor reparto posible.

Aquí se decide por **verificación cruzada**: se leen las celdas de datos con cada
interpretación y gana la que deja menos celdas sin parsear. Es lo que pide §7.4
—«se verifica que ninguna interpretación deje campos no numéricos que la otra sí
parsea»— y tiene una propiedad que la regla del delimitador no tiene: cuando no
hay evidencia, se sabe que no hay evidencia.

TRES RESULTADOS, NO DOS
=======================
1. **Evidencia para la coma**: `0,050` no es un número con punto decimal, así que
   la interpretación de coma explica celdas que la otra no.
2. **Evidencia para el punto**: simétrico.
3. **Ninguna evidencia**: todas las celdas son enteras (`0;1456;217`). Las dos
   interpretaciones leen lo mismo y dan los mismos valores, así que **para estas
   celdas la elección es irrelevante**; pero las filas que el sondeo no vio pueden
   traer decimales. Se propone punto y se avisa. Fingir certeza aquí es la vía
   directa a que la fila 50 000 se lea con el separador equivocado.

LA AMBIGÜEDAD DE LOS TRES DÍGITOS
=================================
`1.234` es 1234 con agrupación de millares o 1,234 con punto decimal. Las dos
lecturas son numéricas, así que la verificación cruzada no las distingue: no es
que el módulo no sepa mirar, es que **el dato no lo dice**. Y la diferencia es de
un factor 1 000, que en un canal de presión es la diferencia entre 1,2 kPa y
1,2 bar.

Solo se afirma agrupación cuando es inequívoca: dos separadores del mismo tipo en
la misma celda (`1.234.567`), o un separador de millares acompañado de otro
distinto para los decimales (`1.234,56`). Con `1.234` a secas se marca
`ambiguo=True` y se avisa; el asistente pregunta.

Solo biblioteca estándar. Este módulo no abre ficheros.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from dlv_core.formatos.sondeo import Sondeo, dividir_campos
from dlv_core.informes import Aviso

__all__ = [
    "MAX_FILAS_INSPECCIONADAS",
    "Decimales",
    "ErrorDeDecimal",
    "Interpretacion",
    "MotivoDecimal",
    "SeparadorDecimal",
    "detectar_separador_decimal",
]

#: Filas de datos que se inspeccionan. Con unas decenas ya hay decimales de
#: sobra si los hay, y el sondeo completo tiene que caber en el presupuesto de
#: primera apertura.
MAX_FILAS_INSPECCIONADAS = 200

#: Un entero sin separador: `1456`, `-20`, `+3`. Se lee igual con cualquier
#: interpretación, así que no aporta evidencia.
_ENTERO = re.compile(r"^[+-]?\d+$")

#: Un separador con exactamente tres dígitos detrás Y una parte entera que PODRÍA
#: ser un grupo de millares: `1.234`, `217,300`. Ambiguo — ver «la ambigüedad de
#: los tres dígitos» en la cabecera.
#:
#: El `[1-9]` es la clave y no un detalle: la agrupación de millares nunca produce
#: un grupo con ceros a la izquierda, así que `0,000` y `0,050` NO pueden ser
#: enteros agrupados y son decimales sin ninguna ambigüedad. Sin esa distinción,
#: un CSV europeo normal —lleno de `0,050`— se declaraba ambiguo entero.
_TRES_DIGITOS = re.compile(r"^[+-]?[1-9]\d{0,2}([.,])(\d{3})$")

#: Un decimal inequívoco: un solo separador y, o bien un número de decimales
#: distinto de tres (`0,05`, `1,00925`), o bien una parte entera que no puede ser
#: un grupo de millares porque empieza por cero (`0,000`) o tiene más de tres
#: cifras (`1234,567`).
_DECIMAL_CLARO = re.compile(r"^[+-]?\d+([.,])\d+$")

#: Dos o más grupos del MISMO separador: `1.234.567`. La agrupación es la única
#: lectura posible, porque un número no tiene dos comas decimales.
_AGRUPACION_REPETIDA = re.compile(r"^[+-]?[1-9]\d{0,2}(([.,])\d{3}){2,}$")

#: Los dos separadores a la vez: `1.234,56`. El que agrupa de tres en tres es la
#: agrupación y el otro el decimal, sin ambigüedad posible.
_AMBOS = re.compile(r"^[+-]?[1-9]\d{0,2}(([.,])\d{3})+([.,])(\d+)$")


#: Notación científica, con el separador decimal que toque: `1.5e-3`.
def _cientifico(decimal: str) -> re.Pattern[str]:
    d = re.escape(decimal)
    return re.compile(rf"^[+-]?\d+({d}\d+)?[eE][+-]?\d+$")


#: Lo que una interpretación concreta sabe leer, y solo eso. La agrupación con el
#: OTRO carácter se acepta —`1,234.56` con punto decimal es legítimo— pero solo en
#: grupos de tres empezando por 1-9, que es la única forma que produce un
#: agrupador de verdad.
def _patron_numerico(decimal: str) -> re.Pattern[str]:
    d = re.escape(decimal)
    g = re.escape("," if decimal == "." else ".")
    return re.compile(rf"^[+-]?([1-9]\d{{0,2}}({g}\d{{3}})+|\d+)({d}\d+)?([eE][+-]?\d+)?$")


_PATRONES = {d: _patron_numerico(d) for d in (".", ",")}
_CIENTIFICOS = {d: _cientifico(d) for d in (".", ",")}


class ErrorDeDecimal(ValueError):
    """No se puede decidir el separador decimal sin inventar."""


class MotivoDecimal(Enum):
    """Por qué se propone este separador. Tres estados, no un booleano.

    La diferencia entre los dos primeros y el tercero es la que el asistente tiene
    que enseñar: los dos primeros son certezas, el tercero es una suposición
    razonable sobre datos que aún no se han visto.
    """

    DELIMITADOR = "delimitador"
    """El delimitador hace imposible el otro separador: si los campos se separan
    por comas, una coma decimal habría partido el número en dos campos. Es la
    única implicación de verdad que hay entre delimitador y decimal, y es certeza,
    no correlación."""

    VERIFICACION_CRUZADA = "verificacion_cruzada"
    """Hay celdas que esta interpretación lee y la otra no (§7.4 paso 4)."""

    SIN_EVIDENCIA = "sin_evidencia"
    """Todas las celdas inspeccionadas son enteras: las dos interpretaciones dan
    los mismos valores para lo visto. La propuesta es utilizable y no está
    respaldada, y las filas que no se han mirado pueden traer decimales."""


class SeparadorDecimal:
    """Los dos separadores posibles. No es un `Enum` a propósito: el valor que
    circula por todo el proyecto es el carácter, y envolverlo obligaría a
    desenvolverlo en cada llamada al lector de CSV."""

    PUNTO = "."
    COMA = ","
    TODOS = (".", ",")


@dataclass(slots=True, frozen=True)
class Interpretacion:
    """Cómo le va a una lectura concreta del fichero.

    Se devuelven las dos, no solo la ganadora: el asistente tiene que poder
    enseñar «con punto decimal, 47 de 300 celdas no son números» para que el
    usuario decida con datos delante.
    """

    decimal: str
    celdas_numericas: int
    celdas_totales: int
    ejemplos_no_numericos: tuple[str, ...]
    """Hasta cinco celdas que esta interpretación no sabe leer. Son lo que hace
    revisable la propuesta: `0,050` en la lista dice más que cualquier
    porcentaje."""

    @property
    def cobertura(self) -> float:
        if self.celdas_totales == 0:
            return 0.0
        return self.celdas_numericas / self.celdas_totales


@dataclass(slots=True, frozen=True)
class Decimales:
    """Lo que se propone sobre el formato numérico del fichero."""

    separador: str
    agrupacion: str | None
    """Separador de millares, solo si es inequívoco. `None` es «no hay, o no se
    puede afirmar»: nunca «no lo he mirado»."""

    motivo: MotivoDecimal

    ambiguo: bool
    """`True` cuando el dato admite dos lecturas con valores distintos. No es que
    falte análisis: es que el fichero no lo dice."""

    interpretaciones: tuple[Interpretacion, ...]
    celdas_inspeccionadas: int
    filas_inspeccionadas: int
    avisos: tuple[Aviso, ...] = ()

    @property
    def hay_evidencia(self) -> bool:
        """¿Está respaldada la propuesta por algo del fichero?

        `True` también cuando la fuerza el delimitador: eso es certeza, no falta
        de evidencia. La primera versión devolvía `False` para un CSV con comas
        —el caso más común de todos— porque no tenía con qué comparar, y eso hacía
        que el asistente avisara de una duda que no existe.
        """
        return self.motivo is not MotivoDecimal.SIN_EVIDENCIA

    @property
    def elegida(self) -> Interpretacion | None:
        for i in self.interpretaciones:
            if i.decimal == self.separador:
                return i
        return None


def _clasificar(celda: str) -> tuple[str, str | None, bool]:
    """(clase, separador_implicado, es_ambigua) de una celda de datos.

    El ORDEN de las comprobaciones es la mitad del trabajo: `1.234.567` encaja
    también en el patrón de «los dos separadores» si se mira solo el final, así que
    la agrupación repetida se comprueba antes. Y los tres dígitos se comprueban
    después del decimal claro, porque `0,000` no puede ser un millar.
    """
    texto = celda.strip()
    if not texto:
        return "vacia", None, False
    if _ENTERO.match(texto):
        return "entero", None, False

    if _AGRUPACION_REPETIDA.match(texto) is not None:
        # `1.234.567`: agrupación segura, y el decimal es el OTRO carácter.
        m = _AGRUPACION_REPETIDA.match(texto)
        assert m is not None
        return "agrupado", ("," if m.group(2) == "." else "."), False

    m = _AMBOS.match(texto)
    if m is not None and m.group(2) != m.group(3):
        # `1.234,56`: el que agrupa de tres en tres NO es el decimal.
        return "ambos", m.group(3), False

    m = _TRES_DIGITOS.match(texto)
    if m is not None:
        return "tres_digitos", m.group(1), True

    m = _DECIMAL_CLARO.match(texto)
    if m is not None:
        return "decimal", m.group(1), False

    return "texto", None, False


def _es_numerica(celda: str, decimal: str) -> bool:
    """¿Sabe esta interpretación leer esta celda como número?

    La primera versión quitaba el carácter contrario y probaba `float`, y eso
    destruía justamente lo que esta tarea tiene que medir: `0,000` con punto
    decimal se convertía en `0000` y salía numérico, así que las dos
    interpretaciones explicaban el fichero entero y la verificación cruzada no
    distinguía nada. Un lector de CSV real con punto decimal NO lee `0,000` como un
    número: se para en la coma o falla.

    Se acepta la agrupación con el carácter contrario —`1,234.56` con punto decimal
    es legítimo— pero solo en grupos de tres que empiezan por 1-9, que es la única
    forma que produce un agrupador de verdad. Y la notación científica.
    """
    texto = celda.strip()
    if not texto:
        return True  # una celda vacía no contradice a nadie (F1-03: vacío != 0)
    return (
        _PATRONES[decimal].match(texto) is not None
        or _CIENTIFICOS[decimal].match(texto) is not None
    )


def _filas_de_datos(sondeo: Sondeo, texto: str) -> list[list[str]]:
    """Las filas del bloque consistente, ya partidas en campos.

    Se parte desde `linea_inicio_datos` porque el preámbulo de metadatos no son
    datos y sus `clave: valor` meterían ruido de texto en las dos
    interpretaciones por igual. La fila de nombres queda dentro a propósito: es
    texto en las dos, así que no desequilibra, y separarla es FG-03.
    """
    if sondeo.delimitador is None:
        raise ErrorDeDecimal(
            "el sondeo no propuso delimitador, así que no hay campos que interpretar. "
            "Hay que elegir delimitador en el asistente antes de decidir el decimal"
        )
    lineas = [linea for linea in texto.splitlines() if linea.strip()]
    utiles = lineas[sondeo.linea_inicio_datos :][:MAX_FILAS_INSPECCIONADAS]
    return [dividir_campos(linea, sondeo.delimitador, sondeo.comilla) for linea in utiles]


def detectar_separador_decimal(sondeo: Sondeo, texto: str) -> Decimales:
    """Propone el separador decimal comparando las dos lecturas del fichero.

    `texto` es la muestra ya decodificada con la codificación que el sondeo
    propuso; se pasa aparte en vez de volver a decodificar aquí para que la
    decisión de codificación se tome en un solo sitio (FG-01).
    """
    filas = _filas_de_datos(sondeo, texto)
    if not filas:
        raise ErrorDeDecimal("no hay ninguna fila de datos que inspeccionar")

    celdas = [c for fila in filas for c in fila]
    avisos: list[Aviso] = []

    # El delimitador manda sobre lo posible, no sobre lo probable: si los campos
    # se separan por comas, una coma decimal habría partido el número en dos
    # campos y el fichero no sería consistente. Es la única implicación de verdad
    # que hay entre delimitador y decimal.
    posibles = tuple(d for d in SeparadorDecimal.TODOS if d != sondeo.delimitador)
    if not posibles:  # pragma: no cover - el delimitador nunca es los dos
        raise ErrorDeDecimal(f"delimitador imposible: {sondeo.delimitador!r}")

    interpretaciones = tuple(
        Interpretacion(
            decimal=d,
            celdas_numericas=sum(1 for c in celdas if _es_numerica(c, d)),
            celdas_totales=len(celdas),
            ejemplos_no_numericos=tuple(
                dict.fromkeys(c.strip() for c in celdas if not _es_numerica(c, d))
            )[:5],
        )
        for d in posibles
    )

    clases = [_clasificar(c) for c in celdas]

    # La evidencia sale de la PROPIA prueba numérica, no de un clasificador
    # paralelo: una celda es evidencia de una interpretación cuando esa
    # interpretación la lee y la otra no. Es literalmente lo que pide §7.4
    # —«campos no numéricos que la otra sí parsea»— y así no hay dos definiciones
    # de «numérico» que puedan divergir. La primera versión contaba evidencia
    # desde las clases y se dejaba fuera la notación científica: `1.5e-3` es
    # evidencia clarísima de punto decimal y no la contaba.
    evidencias = dict.fromkeys(posibles, 0)
    if len(posibles) > 1:
        otro = {posibles[0]: posibles[1], posibles[1]: posibles[0]}
        for c in celdas:
            for d in posibles:
                if _es_numerica(c, d) and not _es_numerica(c, otro[d]):
                    evidencias[d] += 1

    ambiguo = False
    agrupacion: str | None = None

    # Agrupación inequívoca: `1.234,56` o `1.234.567`.
    for clase, separador, _ in clases:
        if clase in {"ambos", "agrupado"} and separador is not None:
            agrupacion = "," if separador == "." else "."
            break

    con_evidencia = [d for d, n in evidencias.items() if n > 0]
    if len(con_evidencia) > 1:
        # Las dos lecturas tienen celdas que solo ellas explican: el fichero es
        # incoherente consigo mismo. Pasa con ficheros pegados a mano de dos
        # fuentes distintas, y es lo peor que puede llegar, porque cualquier
        # elección deja la mitad mal.
        detalle = ", ".join(f"{d!r}: {evidencias[d]} celdas" for d in sorted(con_evidencia))
        avisos.append(
            Aviso(
                "decimal_contradictorio",
                f"el fichero tiene celdas que solo se explican con punto decimal y otras "
                f"que solo se explican con coma ({detalle}). Cualquier elección deja parte "
                "de los datos mal leídos; suele ser un CSV montado a partir de dos fuentes",
            )
        )
        ambiguo = True

    if len(posibles) == 1:
        elegido = posibles[0]
        motivo = MotivoDecimal.DELIMITADOR
    elif con_evidencia:
        elegido = max(evidencias.items(), key=lambda kv: (kv[1], kv[0] == "."))[0]
        motivo = MotivoDecimal.VERIFICACION_CRUZADA
    else:
        # Ninguna celda lleva separador: las dos lecturas dan los MISMOS valores
        # para lo que se ha visto. La elección no es arbitraria en su efecto —hoy
        # da igual— pero sí lo es para las filas que no se han mirado.
        elegido = SeparadorDecimal.PUNTO
        motivo = MotivoDecimal.SIN_EVIDENCIA
        avisos.append(
            Aviso(
                "decimal_sin_evidencia",
                f"ninguna de las {len(celdas)} celdas inspeccionadas lleva separador "
                "decimal: todas son enteras. Se propone el punto, pero no hay nada en el "
                "fichero que lo respalde y una fila posterior podría traer decimales",
            )
        )

    # La ambigüedad de los tres dígitos, solo si no la ha resuelto ya una celda
    # inequívoca.
    tres = {sep for clase, sep, amb in clases if amb and sep is not None}
    if tres and agrupacion is None:
        sospechosos = tuple(
            dict.fromkeys(c.strip() for c, (_, _, amb) in zip(celdas, clases, strict=True) if amb)
        )[:5]
        claros = any(clase == "decimal" for clase, _, _ in clases)
        if not claros:
            avisos.append(
                Aviso(
                    "agrupacion_o_decimal_ambiguo",
                    f"hay celdas con exactamente tres dígitos tras el separador "
                    f"({', '.join(sospechosos)}) y ninguna que lo desambigüe. "
                    f"{sospechosos[0] if sospechosos else ''} puede ser un decimal o un "
                    "millar: la diferencia es un factor 1 000. Hay que confirmarlo en el "
                    "asistente",
                )
            )
            ambiguo = True

    peor = min(interpretaciones, key=lambda i: i.cobertura)
    if peor.cobertura < 1.0 and len(interpretaciones) > 1:
        avisos.append(
            Aviso(
                "decimal_por_verificacion_cruzada",
                f"se propone {elegido!r} como separador decimal: con "
                f"{peor.decimal!r} habría {peor.celdas_totales - peor.celdas_numericas} de "
                f"{peor.celdas_totales} celdas no numéricas"
                + (
                    f" (p. ej. {', '.join(peor.ejemplos_no_numericos)})"
                    if peor.ejemplos_no_numericos
                    else ""
                ),
            )
        )

    return Decimales(
        separador=elegido,
        agrupacion=agrupacion,
        motivo=motivo,
        ambiguo=ambiguo,
        interpretaciones=interpretaciones,
        celdas_inspeccionadas=len(celdas),
        filas_inspeccionadas=len(filas),
        avisos=tuple(avisos),
    )
