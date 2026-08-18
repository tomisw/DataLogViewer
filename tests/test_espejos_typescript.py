"""Las listas que existen dos veces, una en Python y otra en TypeScript.

`dlv-ui` no puede importar `dlv_core`: son dos lenguajes y ADR-002 mantiene el
núcleo sin dependencias del transporte. Así que unas pocas listas cerradas están
escritas dos veces a propósito, y cada copia lleva un comentario diciendo a quién
mira. Un comentario no impide que se desincronicen.

POR QUÉ ESTA PRUEBA VIVE EN PYTHON Y NO EN VITEST
==================================================
La comprobación solo se puede hacer desde el lado que puede leer los dos
ficheros. Un test de vitest no puede importar un `Enum` de Python sin arrancar un
intérprete; Python sí puede leer un `.ts` como texto y buscar la lista. Por eso
está aquí y no en `dlv-ui`, aunque lo que protege sea código de `dlv-ui`.

QUÉ PASA SI ESTO SE PONE ROJO
==============================
No hay que relajar la expresión regular: hay que mirar cuál de las dos copias se
ha quedado atrás. Los dos casos son silenciosos y ninguno da un error, que es lo
que los hace peligrosos:

* Si el ORDEN de las severidades difiere, el panel de incidencias ordena por
  consecuencia usando un orden que no es el que el motor de detección aplica, y
  el técnico ve arriba algo que no es lo más grave. No falla nada; solo miente.
* Si los nombres de `Clase` difieren, una clase que Python emite y TypeScript no
  reconoce se convierte con la rama que quede por omisión, y ahí está la trampa
  del delta: un Δ de 10 K mostrado como −263,15 °C.

Solo biblioteca estándar. Lee los `.ts` como texto, sin ejecutarlos.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlv_core.plausibilidad import SEVERIDADES
from dlv_core.unidades import Clase

RAIZ = Path(__file__).resolve().parents[1]
UI = RAIZ / "dlv-ui" / "src"


def _lista_de_cadenas(texto: str, nombre: str) -> list[str]:
    """Las cadenas de un `export const <nombre> = [...]` de TypeScript."""
    m = re.search(rf"{re.escape(nombre)}\s*=\s*\[(.*?)\]", texto, re.S)
    assert m is not None, f"no se encuentra `{nombre}` como lista en el fichero"
    return re.findall(r'"([^"]+)"', m.group(1))


def _union_de_cadenas(texto: str, nombre: str) -> list[str]:
    """Los miembros de un `export type <nombre> = "a" | "b" | ...`."""
    m = re.search(rf"type\s+{re.escape(nombre)}\s*=\s*([^;]+);", texto, re.S)
    assert m is not None, f"no se encuentra `type {nombre}` en el fichero"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_el_orden_de_severidades_es_el_mismo_en_los_dos_lenguajes() -> None:
    """`dlv_core.plausibilidad.SEVERIDADES` y `SEVERIDADES_CONCRETAS` de F3-12.

    El orden ES la semántica: el comentario de la tupla de Python dice que «el
    orden de la tupla ES el orden de consecuencia», y el panel de incidencias
    deriva de él el rango con el que ordena. Aquí no basta con que estén los
    mismos cinco nombres; tienen que estar en el mismo orden.
    """
    fichero = UI / "incidencias" / "tipos.ts"
    assert fichero.exists(), "F3-12 movió `tipos.ts`: actualiza esta prueba"
    en_ts = _lista_de_cadenas(fichero.read_text(encoding="utf-8"), "SEVERIDADES_CONCRETAS")
    assert en_ts == list(SEVERIDADES), (
        f"TypeScript dice {en_ts} y Python {list(SEVERIDADES)}; el panel de "
        "incidencias ordenaría por un orden de consecuencia distinto del que "
        "aplica el motor de detección, y sin fallar por ningún sitio"
    )


def test_las_clases_de_conversion_son_las_mismas_en_los_dos_lenguajes() -> None:
    """`dlv_core.unidades.Clase` y el `type Clase` de `unidades/conversion.ts`.

    Es la regla 4 de `CLAUDE.md` vista desde el otro lado: la clase de conversión
    es obligatoria, y una clase que un lado emita y el otro no reconozca acaba en
    la rama por omisión, que es exactamente cómo un Δ de 10 K sale como
    −263,15 °C.
    """
    fichero = UI / "unidades" / "conversion.ts"
    assert fichero.exists(), "`conversion.ts` se movió: actualiza esta prueba"
    en_ts = _union_de_cadenas(fichero.read_text(encoding="utf-8"), "Clase")
    en_py = [c.value for c in Clase]
    assert sorted(en_ts) == sorted(en_py), (
        f"TypeScript dice {sorted(en_ts)} y Python {sorted(en_py)}; una clase que "
        "un lado no reconoce se convierte con la rama por omisión"
    )


@pytest.mark.parametrize(
    ("relativo", "nombre"),
    [("incidencias/tipos.ts", "SEVERIDADES_CONCRETAS"), ("unidades/conversion.ts", "Clase")],
)
def test_cada_copia_dice_a_quien_mira(relativo: str, nombre: str) -> None:
    """Un espejo sin la referencia escrita al lado es un espejo que nadie sabe
    que lo es. Si alguien añade una tercera copia, que al menos diga de dónde
    viene, porque esta prueba solo cubre las dos que conoce."""
    texto = (UI / relativo).read_text(encoding="utf-8")
    assert "dlv_core" in texto, (
        f"`{relativo}` define `{nombre}` sin citar el módulo de `dlv_core` al que "
        "mira; quien lo edite no tiene forma de saber que hay otra copia"
    )
