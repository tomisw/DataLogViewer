#!/usr/bin/env python3
"""Convierte los datos de una puerta G1 en afirmaciones físicas revisables.

POR QUÉ EXISTE
==============
Las puertas G1 de este proyecto no protegen código: protegen NÚMEROS. Un factor
de unidad mal puesto no revienta —produce un valor plausible que llega a una
decisión de puesta a punto— y por eso `CLAUDE.md` dice que no las cierra un
modelo. Pero pedir «lee el diff» convierte un juicio de dominio, que el
propietario puede hacer en segundos, en una lectura de Python, que no puede
hacer sin tiempo.

`data/casos_de_unidades.toml` (F1-20) ya lo dice en su propia cabecera: «se puede
revisar sin leer Python; nadie va a auditar aserciones enterradas en un fichero
de pruebas». Esta herramienta generaliza eso a los demás datos G1.

QUÉ HACE, Y LO QUE LO HACE ÚTIL
================================
Las afirmaciones NO se leen del fichero: se generan **ejecutando el motor de
conversión** sobre el dato. Si el factor de psi estuviera mal, la línea que sale
por pantalla estaría visiblemente mal («1 bar = 12,3 psi»), y eso se ve sin
mirar el TOML. Leer el número del fichero y volver a imprimirlo no comprobaría
nada: solo confirmaría que el fichero dice lo que dice.

Y separa lo comprobable de lo que exige criterio:

  - **Con comprobación independiente**: el dato lo respalda algo que no es él
    mismo — un caso de `casos_de_unidades.toml` con su `origen` citado, una
    identidad de ida y vuelta, o una relación entre dos unidades de la misma
    dimensión. Estos no necesitan ojos.
  - **Sin comprobación**: afirmaciones desnudas. Son las únicas que hay que
    revisar de verdad, y saber CUÁNTAS son es la diferencia entre «revisa 147
    puntos» y «contesta a estas N preguntas».

Uso:
    python tools/revisar.py                # el informe entero
    python tools/revisar.py unidades       # solo data/units.toml
    python tools/revisar.py descriptor     # solo data/formats/haltech_nsp.toml
    python tools/revisar.py --solo-dudosas # solo lo que no tiene respaldo

LO QUE ESTA HERRAMIENTA **NO** HACE
====================================
Usa un valor bruto fijo de ejemplo para ilustrar cada escala, así que en los
canales cuyo rango real es muy distinto la línea sale con un valor absurdo
(«Mileage: 4731 L/100 km») sin que el factor esté mal: lo absurdo es el valor de
ejemplo, no el dato. Sirve para ver un factor equivocado por ÓRDENES DE MAGNITUD
—que es el error que importa— y no para validar un factor fino.

La versión buena de esto es FG-10, el informe de plausibilidad: comprueba los
valores REALES de cada canal contra el rango plausible que `roles.toml` declara
para su rol, y eso sí caza «nombre correcto con la escala equivocada» sin que
nadie mire nada. Mientras FG-10 no exista, esto es lo que hay.

Solo biblioteca estándar más `dlv-core`: ni NumPy ni Polars, así que corre en
cualquier entorno.
"""

from __future__ import annotations

import argparse
import math
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dlv-core" / "src"))

from dlv_core.unidades import (  # noqa: E402 — tras ajustar sys.path
    Afin,
    Catalogo,
    Clase,
    ErrorDeUnidad,
    cargar_catalogo,
    desde_canonica,
)

NEGRITA, VERDE, ROJO, AMARILLO, TENUE, FIN = (
    ("\033[1m", "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m")
    if sys.stdout.isatty()
    else ("", "", "", "", "", "")
)


@dataclass(slots=True)
class Afirmacion:
    """Una cosa que el dato afirma sobre el mundo, en términos físicos."""

    donde: str
    """Qué entrada del fichero la produce, para poder ir a corregirla."""

    texto: str
    """La afirmación, generada ejecutando el motor. Legible sin abrir el TOML."""

    respaldo: str | None = None
    """Qué la comprueba, si algo lo hace. `None` = afirmación desnuda."""

    aviso: str | None = None
    """Un problema detectado por la propia herramienta."""


@dataclass(slots=True)
class Informe:
    titulo: str
    afirmaciones: list[Afirmacion] = field(default_factory=list)

    @property
    def desnudas(self) -> list[Afirmacion]:
        return [a for a in self.afirmaciones if a.respaldo is None]

    @property
    def avisos(self) -> list[Afirmacion]:
        return [a for a in self.afirmaciones if a.aviso is not None]


# --------------------------------------------------------------------------- #
# Qué respalda un dato
# --------------------------------------------------------------------------- #
def _casos_conocidos() -> dict[tuple[str, str], list[str]]:
    """`(dimension, unidad) -> orígenes citados` de `casos_de_unidades.toml`.

    Es el respaldo más fuerte que hay: cada caso trae un campo `origen` con la
    fuente de la que sale el número (una definición del SI, una norma), así que
    el dato no se apoya en sí mismo.
    """
    ruta = RAIZ / "data" / "casos_de_unidades.toml"
    if not ruta.exists():
        return {}
    with ruta.open("rb") as fh:
        bruto = tomllib.load(fh)
    respaldos: dict[tuple[str, str], list[str]] = {}
    for seccion in ("punto", "delta", "tasa", "varianza"):
        for caso in bruto.get(seccion, []):
            clave = (str(caso.get("dimension")), str(caso.get("unidad")))
            origen = str(caso.get("origen", "sin origen citado"))
            respaldos.setdefault(clave, []).append(f"{seccion}: {origen}")

    # F1-46: el respaldo más fuerte de todos, porque no es un ejemplo sino una
    # derivación. `definiciones_de_unidades.toml` declara de qué constantes
    # exactas sale el factor, y `test_definiciones_de_unidades.py` ejecuta la
    # cuenta y la compara con `units.toml`. Un factor así no necesita ojos: si no
    # cuadra con su definición, la suite está en rojo.
    definiciones = RAIZ / "data" / "definiciones_de_unidades.toml"
    if definiciones.exists():
        with definiciones.open("rb") as fh:
            bruto_def = tomllib.load(fh)
        for caso in bruto_def.get("definicion", []):
            clave = (str(caso.get("dimension")), str(caso.get("unidad")))
            respaldos.setdefault(clave, []).insert(
                0, f"derivado de su definición — {caso.get('derivacion', '')}"
            )
    return respaldos


def _ida_y_vuelta_exacta(cat: Catalogo, dim_id: str, uni_id: str) -> bool:
    """¿Convertir a la unidad y volver da el valor de partida?

    Es un respaldo débil pero real: no dice que el factor sea el correcto, dice
    que el motor es consistente consigo mismo y que la unidad no es degenerada
    (un factor 0, que convertiría cualquier valor en cero, no sobrevive a esto).
    """
    from dlv_core.unidades import a_canonica

    dim = cat.dimension(dim_id)
    for prueba in (1.0, 137.0, -42.5):
        try:
            ida = desde_canonica(prueba, dimension=dim, unidad=uni_id, clase=Clase.PUNTO)
            vuelta = a_canonica(ida, dimension=dim, unidad=uni_id, clase=Clase.PUNTO)
        except (ErrorDeUnidad, ZeroDivisionError, ValueError):
            return False
        if not math.isfinite(float(vuelta)) or not math.isclose(
            float(vuelta), prueba, rel_tol=1e-9, abs_tol=1e-9
        ):
            return False
    return True


# --------------------------------------------------------------------------- #
# units.toml
# --------------------------------------------------------------------------- #
def informe_de_unidades(cat: Catalogo) -> Informe:
    """Cada unidad, expresada como «1 canónica = X unidad» ejecutando el motor."""
    inf = Informe("data/units.toml — el catálogo de unidades (F0-08)")
    casos = _casos_conocidos()

    for dim_id, dim in sorted(cat.dimensiones.items()):
        canonica = dim.unidad_canonica
        for uni_id, unidad in sorted(dim.unidades.items()):
            donde = f"[dimensiones.{dim_id}.unidades.{uni_id}]"
            if uni_id == canonica:
                # La canónica tiene que ser la identidad, y eso se comprueba
                # solo: no es una afirmación sobre el mundo.
                continue

            try:
                uno = float(desde_canonica(1.0, dimension=dim, unidad=uni_id, clase=Clase.PUNTO))
                cien = float(desde_canonica(100.0, dimension=dim, unidad=uni_id, clase=Clase.PUNTO))
            except (ErrorDeUnidad, ZeroDivisionError, ValueError) as exc:
                inf.afirmaciones.append(
                    Afirmacion(donde, f"NO SE PUEDE CONVERTIR: {exc}", aviso="conversión falla")
                )
                continue

            # Que una recíproca (φ, mpg, periodo) se niegue a convertir un
            # INTERVALO no es un fallo: es el requisito de §6.5, y lo fija la
            # sección [[rechazo]] de `casos_de_unidades.toml`. La primera versión
            # de esta herramienta pedía el delta junto con los puntos y perdía la
            # línea entera de cinco unidades, presentando como cinco avisos lo que
            # era el motor haciendo exactamente lo que se le pide.
            delta: float | None
            try:
                delta = float(
                    desde_canonica(100.0, dimension=dim, unidad=uni_id, clase=Clase.INTERVALO)
                )
            except (ErrorDeUnidad, ZeroDivisionError, ValueError):
                delta = None

            conv = unidad.conversion
            desplazada = isinstance(conv, Afin) and conv.b != 0.0
            cabeza = (
                f"{dim_id}: 1 {canonica} = {uno:.6g} {unidad.etiqueta or uni_id}   ·   "
                f"100 {canonica} = {cien:.6g}"
            )
            if desplazada and delta is not None:
                texto = f"{cabeza}   ·   un Δ de 100 {canonica} = {delta:.6g} (origen desplazado)"
            elif delta is None:
                texto = f"{cabeza}   ·   un Δ NO se convierte (recíproca, correcto)"
            else:
                texto = cabeza

            respaldo: str | None = None
            if (dim_id, uni_id) in casos:
                origenes = casos[(dim_id, uni_id)]
                respaldo = f"{len(origenes)} caso(s) conocido(s) — {origenes[0]}"
            elif _ida_y_vuelta_exacta(cat, dim_id, uni_id):
                respaldo = None  # la ida y vuelta NO respalda el factor, ver abajo

            aviso = None
            if desplazada and (dim_id, uni_id) not in casos:
                # Una unidad con origen desplazado y sin caso conocido es la
                # combinación exacta de la trampa del delta sin red debajo.
                aviso = "origen desplazado y sin caso conocido: es la trampa del delta sin red"
            if not _ida_y_vuelta_exacta(cat, dim_id, uni_id):
                aviso = "la ida y vuelta no es exacta: el motor no es consistente aquí"

            inf.afirmaciones.append(Afirmacion(donde, texto, respaldo, aviso))

    return inf


# --------------------------------------------------------------------------- #
# El descriptor del formato nativo
# --------------------------------------------------------------------------- #
#: Valor bruto de ejemplo con el que se ilustra cada escala. 4731 es el que usa
#: `docs/01` §1.8 para el deciKelvin, así que la línea de temperatura se puede
#: comparar con el documento sin cuentas.
BRUTO_DE_EJEMPLO = 4731


def informe_del_descriptor(cat: Catalogo) -> Informe:
    """Cada tipo del formato Haltech, con lo que su escala implica de verdad."""
    from dlv_core.compuestas import cargar_compuestas, derivar_unidad_compuesta
    from dlv_core.formatos.haltech import cargar_descriptor

    inf = Informe("data/formats/haltech_nsp.toml — los 34 tipos (F0-09)")
    # Las dimensiones COMPUESTAS (`%/kPa`, F1-16) viven en `[compuestas]` de
    # units.toml, que es otra sección distinta de `[dimensiones]`. Mirar solo las
    # dimensiones hacía que esta herramienta declarara «dimensión desconocida»
    # tres tipos perfectamente declarados: un falso positivo en la herramienta
    # cuyo trabajo es no dar falsos positivos.
    with (RAIZ / "data" / "units.toml").open("rb") as fh:
        compuestas = cargar_compuestas(fh)
    ruta = RAIZ / "data" / "formats" / "haltech_nsp.toml"
    with ruta.open("rb") as fh:
        descriptor = cargar_descriptor(fh)

    for nombre, tipo in sorted(descriptor.tipos.items()):
        donde = f"[tipos.{nombre}]"
        # `descriptor.tipos` son diccionarios, no objetos: un `getattr` aquí
        # devolvía None en los 34 tipos y el informe salía diciendo que ninguno
        # afirma nada, que es el peor error posible en una herramienta cuyo
        # trabajo es contar cuántas afirmaciones hay sin respaldo.
        dim_id = tipo.get("dimension")
        a = tipo.get("a_canonica")
        confianza = str(tipo.get("confianza", "?"))
        evidencia = str(tipo.get("evidencia", "")).strip()
        canales = tipo.get("canales")

        if dim_id is None or a is None:
            inf.afirmaciones.append(
                Afirmacion(
                    donde,
                    f"{nombre}: sin dimensión — se muestra en crudo, sin unidad",
                    respaldo="no afirma nada sobre el mundo: no hay factor que revisar",
                )
            )
            continue

        if dim_id in compuestas:
            compuesta = compuestas[dim_id]
            num = cat.dimension(compuesta.numerador)
            den = cat.dimension(compuesta.denominador)
            derivada = derivar_unidad_compuesta(
                compuesta,
                catalogo=cat,
                unidad_numerador=num.unidad_canonica,
                unidad_denominador=den.unidad_canonica,
            )
            canonico_c = float(a) * BRUTO_DE_EJEMPLO
            inf.afirmaciones.append(
                Afirmacion(
                    donde,
                    f"{nombre}: un bruto de {BRUTO_DE_EJEMPLO} son {canonico_c:.6g} "
                    f"{derivada.etiqueta}   [compuesta {compuesta.numerador}/"
                    f"{compuesta.denominador}]",
                    respaldo=(
                        "dimensión compuesta: su unidad se DERIVA de las activas del "
                        "numerador y del denominador, así que no hay factor propio que revisar"
                    ),
                )
            )
            continue

        try:
            dim = cat.dimension(dim_id)
        except ErrorDeUnidad as exc:
            inf.afirmaciones.append(
                Afirmacion(donde, f"{nombre}: dimensión desconocida", aviso=str(exc))
            )
            continue

        canonico = float(a) * BRUTO_DE_EJEMPLO
        # Se muestra en la unidad que un tuner reconoce, no en la canónica.
        preferida = {
            "temperature": "degC",
            "pressure": "kPa",
            "angular_speed": "rpm",
            "speed": "km/h",
            "ratio": "pct",
        }.get(dim_id, dim.unidad_canonica)
        try:
            mostrado = float(
                desde_canonica(canonico, dimension=dim, unidad=preferida, clase=Clase.PUNTO)
            )
            etiqueta = dim.unidad(preferida).etiqueta or preferida
        except ErrorDeUnidad:
            mostrado, etiqueta = canonico, dim.unidad_canonica

        sufijo = f" · {canales} canales" if canales else ""
        texto = (
            f"{nombre}: un bruto de {BRUTO_DE_EJEMPLO} son {canonico:.6g} "
            f"{dim.unidad_canonica} = {mostrado:.6g} {etiqueta}   [{dim_id}{sufijo}]"
        )

        respaldo: str | None = None
        aviso: str | None = None
        if confianza == "confirmed":
            primera = evidencia.split("\n")[0] if evidencia else "sin evidencia citada"
            respaldo = f"`confirmed` — {primera}"
            if not evidencia:
                aviso = "declarado `confirmed` pero SIN evidencia citada en el descriptor"
        elif confianza == "unknown":
            respaldo = "declarado `unknown`: NO se convierte, se muestra en crudo (R1)"
        else:
            aviso = (
                f"confianza = {confianza!r}: el factor está deducido, no confirmado. "
                "Si el valor de arriba no es físicamente plausible, el factor está mal"
            )

        inf.afirmaciones.append(Afirmacion(donde, texto, respaldo, aviso))

    return inf


# --------------------------------------------------------------------------- #
# Salida
# --------------------------------------------------------------------------- #
def imprimir(inf: Informe, *, solo_dudosas: bool) -> None:
    print(f"\n{NEGRITA}{inf.titulo}{FIN}")
    print("─" * min(len(inf.titulo), 78))

    mostrar = (
        inf.afirmaciones
        if not solo_dudosas
        else [a for a in inf.afirmaciones if a.respaldo is None or a.aviso is not None]
    )
    for a in mostrar:
        marca = (
            f"{ROJO}✱{FIN}"
            if a.aviso
            else (f"{VERDE}·{FIN}" if a.respaldo else f"{AMARILLO}?{FIN}")
        )
        print(f" {marca} {a.texto}")
        if a.aviso:
            print(f"     {ROJO}{a.aviso}{FIN}")
        if a.respaldo:
            print(f"     {TENUE}respaldo: {a.respaldo}{FIN}")
        else:
            print(f"     {TENUE}{a.donde} — sin respaldo independiente{FIN}")

    n, d, av = len(inf.afirmaciones), len(inf.desnudas), len(inf.avisos)
    print(
        f"\n  {n} afirmaciones · {VERDE}{n - d} con respaldo{FIN} · "
        f"{AMARILLO}{d} solo tu criterio{FIN} · {ROJO}{av} con aviso{FIN}"
    )


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("que", nargs="?", choices=["unidades", "descriptor", "todo"], default="todo")
    p.add_argument(
        "--solo-dudosas",
        action="store_true",
        help="solo lo que no tiene respaldo independiente o tiene un aviso",
    )
    args = p.parse_args(argv[1:])

    with (RAIZ / "data" / "units.toml").open("rb") as fh:
        cat = cargar_catalogo(fh)

    informes = []
    if args.que in ("unidades", "todo"):
        informes.append(informe_de_unidades(cat))
    if args.que in ("descriptor", "todo"):
        informes.append(informe_del_descriptor(cat))

    for inf in informes:
        imprimir(inf, solo_dudosas=args.solo_dudosas)

    total = sum(len(i.afirmaciones) for i in informes)
    desnudas = sum(len(i.desnudas) for i in informes)
    avisos = sum(len(i.avisos) for i in informes)
    print(f"\n{NEGRITA}═══ lo que de verdad hay que revisar ═══{FIN}")
    print(f"  {total} afirmaciones físicas en total.")
    print(f"  {VERDE}{total - desnudas}{FIN} las respalda algo que no es el propio fichero.")
    print(f"  {AMARILLO}{desnudas}{FIN} dependen solo de tu criterio.")
    if avisos:
        print(f"  {ROJO}{avisos}{FIN} llevan un aviso de esta herramienta: míralas primero.")
    print(
        f"\n{TENUE}  Las líneas se generan EJECUTANDO el motor de conversión sobre el dato,\n"
        f"  no leyéndolo del TOML: si un factor está mal, la línea está visiblemente mal.{FIN}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
