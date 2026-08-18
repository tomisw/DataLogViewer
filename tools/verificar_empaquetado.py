#!/usr/bin/env python3
"""Comprueba `dlv-app/dlv_app.spec` sin PyInstaller instalado (tarea F5-01).

    python tools/verificar_empaquetado.py

POR QUÉ EXISTE ESTE GUION
==========================
PyInstaller no está instalado en el entorno donde se escribió F5-01 (PyPI da
403 ahí) y no se puede instalar, así que no hay forma de generar el paquete
real ni de medir su tamaño o su arranque en frío. Eso no es excusa para
entregar un `.spec` sin comprobar nada: "no digas verde de nada que no hayas
ejecutado tú" es la regla del proyecto (`docs/09` §9.4), así que este guion
SÍ ejecuta algo, aunque no sea PyInstaller.

QUÉ HACE
========
1. `python -m py_compile` sobre el `.spec`: que sea Python sintácticamente
   válido (ya lo hace `.github/workflows/ci.yml`, se repite aquí para tener
   todo en un solo sitio y con más detalle).
2. Ejecuta el `.spec` DE VERDAD, con `Analysis`/`PYZ`/`EXE`/`COLLECT`
   sustituidos por comprobantes que solo registran con qué argumentos se les
   llamó (no construyen ningún paquete). Como el `.spec` sigue siendo el
   código real -- las mismas rutas, la misma comprobación de `dlv-ui/dist`,
   los mismos `RAIZ_REPO.parent / "data"` -- esto no es "confiar en lo que
   dice el fichero": es la única forma disponible aquí de comprobar que cada
   ruta que declara `datas` resuelve a algo que existe de verdad en el
   repositorio, sin necesitar PyInstaller instalado para evaluarla.
3. Para cada entrada de `datas` que sea una ruta literal del repositorio
   (tupla `(origen, destino)`), comprueba que `origen` existe en disco.
4. Para las entradas que NO son rutas literales -- aquí solo
   `collect_data_files("webview")`, que necesita el paquete `webview`
   instalado para poder ejecutarse -- se marca explícitamente como NO
   VERIFICABLE en este entorno, en vez de darla por buena o por mala.
5. Comprueba que `samples/real/` (los tres logs del propietario, que
   `CLAUDE.md` prohíbe tocar y que no son material de distribución) NO
   aparece en ninguna ruta de `datas`.
6. Contrasta la lista de ficheros de `data/*.toml` que el código de
   `dlv-api`/`dlv-core` abre de verdad (grep de `.toml"` sobre los fuentes)
   contra lo que hay físicamente en `data/`, para que el informe de la tarea
   pueda decir con qué se comprobó "la lista está completa" en vez de decirlo
   de memoria.

QUÉ NO HACE (y por qué no puede)
==================================
No construye el paquete, no mide su tamaño ni el arranque en frío contra los
presupuestos de `docs/02-alcance-y-plan.md` §2.6, y no puede confirmar que
`hiddenimports`/`excludes` sean correctos: eso exige un build real por
plataforma con `pyinstaller` instalado, que no está disponible aquí.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SPEC = RAIZ / "dlv-app" / "dlv_app.spec"

NEGRITA, VERDE, ROJO, AMARILLO, FIN = (
    ("\033[1m", "\033[32m", "\033[31m", "\033[33m", "\033[0m")
    if sys.stdout.isatty()
    else ("", "", "", "", "")
)


def _titulo(t: str) -> None:
    print(f"\n{NEGRITA}=== {t} ==={FIN}")


# --------------------------------------------------------------------------- #
# 1. Sintaxis
# --------------------------------------------------------------------------- #


def comprobar_sintaxis() -> bool:
    _titulo("1. Sintaxis del .spec (python -m py_compile)")
    r = subprocess.run([sys.executable, "-m", "py_compile", str(SPEC)], cwd=RAIZ)
    ok = r.returncode == 0
    print(f"{VERDE if ok else ROJO}{'OK' if ok else 'FALLA'}{FIN}: {SPEC.relative_to(RAIZ)}")
    return ok


# --------------------------------------------------------------------------- #
# 2. Ejecutar el .spec de verdad, con Analysis/PYZ/EXE/COLLECT como
#    comprobantes que solo registran sus argumentos.
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _LlamadaCapturada:
    datas: list[object] = field(default_factory=list)
    hiddenimports: list[object] = field(default_factory=list)
    excludes: list[object] = field(default_factory=list)


class _AnalysisFalsa:
    """Sustituye a `Analysis(...)` de PyInstaller: captura los kwargs y no
    construye nada. `a.pure` / `a.scripts` / `a.binaries` / `a.datas` (que
    `PYZ`/`EXE`/`COLLECT` leen después en el `.spec` real) se dejan vacíos:
    no hace falta que tengan contenido real para que el `.spec` termine de
    ejecutarse, solo que existan como atributos.
    """

    ultima: _LlamadaCapturada | None = None

    def __init__(self, *_args: object, **kwargs: object) -> None:
        capturada = _LlamadaCapturada(
            datas=list(kwargs.get("datas") or []),
            hiddenimports=list(kwargs.get("hiddenimports") or []),
            excludes=list(kwargs.get("excludes") or []),
        )
        _AnalysisFalsa.ultima = capturada
        self.pure: list[object] = []
        self.scripts: list[object] = []
        self.binaries: list[object] = []
        self.datas: list[object] = []


def _pyz_falsa(*_a: object, **_k: object) -> object:
    return object()


def _exe_falsa(*_a: object, **_k: object) -> object:
    return object()


def _collect_falsa(*_a: object, **_k: object) -> object:
    return object()


def _collect_data_files_falsa(paquete: str, *_a: object, **_k: object) -> list[object]:
    """Sustituye a `PyInstaller.utils.hooks.collect_data_files`.

    Necesitaría el paquete (`webview`) instalado de verdad para devolver algo
    con sentido, y no lo está aquí. Se registra la llamada (ver
    `PAQUETES_COLLECT_DATA_FILES`) para que el resumen la marque como NO
    VERIFICABLE en vez de fingir que devolvió una lista vacía y por tanto
    "sin problema".
    """
    PAQUETES_COLLECT_DATA_FILES.append(paquete)
    return []


PAQUETES_COLLECT_DATA_FILES: list[str] = []


def ejecutar_spec_con_comprobantes() -> _LlamadaCapturada | None:
    """Ejecuta el `.spec` real con nombres de PyInstaller sustituidos.

    `SPECPATH` es la única variable que PyInstaller inyecta y que el `.spec`
    usa (`RAIZ_REPO = Path(SPECPATH).resolve().parent`): se fija a la carpeta
    real de `dlv-app/`, igual que haría PyInstaller.
    """
    modulo_hooks = type(sys)("PyInstaller.utils.hooks")
    modulo_hooks.collect_data_files = _collect_data_files_falsa  # type: ignore[attr-defined]
    modulo_pyinstaller = type(sys)("PyInstaller")
    modulo_utils = type(sys)("PyInstaller.utils")
    sys.modules["PyInstaller"] = modulo_pyinstaller
    sys.modules["PyInstaller.utils"] = modulo_utils
    sys.modules["PyInstaller.utils.hooks"] = modulo_hooks

    espacio_global = {
        "__name__": "__main__",
        "__file__": str(SPEC),
        "SPECPATH": str(SPEC.parent),
        "Analysis": _AnalysisFalsa,
        "PYZ": _pyz_falsa,
        "EXE": _exe_falsa,
        "COLLECT": _collect_falsa,
    }
    codigo = SPEC.read_text(encoding="utf-8")
    try:
        exec(compile(codigo, str(SPEC), "exec"), espacio_global)
    except SystemExit as e:
        # El propio `.spec` aborta así si `dlv-ui/dist` no existe (ver su
        # docstring): es una FALLA de esta comprobación, no una excepción
        # inesperada, porque significa que el .spec real no llegaría a
        # `Analysis()` en esta máquina.
        print(f"{ROJO}el .spec abortó con SystemExit: {e}{FIN}")
        return None
    except Exception as e:  # queremos capturar cualquier fallo del .spec real, sea el que sea
        print(f"{ROJO}el .spec lanzó {type(e).__name__}: {e}{FIN}")
        return None
    return _AnalysisFalsa.ultima


# --------------------------------------------------------------------------- #
# 3-5. Inspección de las rutas capturadas
# --------------------------------------------------------------------------- #


def comprobar_datas(capturada: _LlamadaCapturada) -> bool:
    _titulo("2-5. Rutas de `datas` (ejecutando el .spec real, sin construir nada)")
    ok = True
    if not capturada.datas:
        print(f"{ROJO}FALLA{FIN}: `datas` llegó vacía a Analysis() -- no se capturó nada")
        return False

    for entrada in capturada.datas:
        if not (isinstance(entrada, (tuple, list)) and len(entrada) == 2):
            print(f"{AMARILLO}? {FIN} entrada de `datas` con forma inesperada: {entrada!r}")
            ok = False
            continue
        origen, destino = entrada
        ruta = Path(str(origen))
        existe = ruta.exists()
        marca = f"{VERDE}OK{FIN}" if existe else f"{ROJO}FALTA{FIN}"
        print(f"  {marca}  {origen}  ->  {destino}")
        if not existe:
            ok = False

        # Requisito explícito de la tarea: samples/real/ no debe entrar en
        # el paquete.
        try:
            partes_relativas = ruta.resolve().relative_to(RAIZ).parts
        except ValueError:
            partes_relativas = ()
        if "samples" in partes_relativas:
            print(f"{ROJO}FALLA{FIN}: {ruta} está bajo samples/ -- no debe empaquetarse")
            ok = False

    if PAQUETES_COLLECT_DATA_FILES:
        for paquete in PAQUETES_COLLECT_DATA_FILES:
            print(
                f"{AMARILLO}NO VERIFICABLE{FIN}: collect_data_files({paquete!r}) necesita "
                f"el paquete {paquete!r} instalado; no lo está en este entorno (PyPI "
                "bloqueado). No se puede confirmar ni negar qué ficheros añadiría."
            )
    return ok


def comprobar_samples_fuera_del_arbol_analizado() -> bool:
    """Repite la comprobación de samples/real/ leyendo el .spec como texto,
    como red de seguridad si algún día se añade una ruta que la ejecución de
    la sección anterior no llegase a capturar (p. ej. dentro de un `if` que
    no se ejecuta con las condiciones de esta máquina).
    """
    _titulo("Red de seguridad: 'samples' no aparece como texto en el .spec")
    codigo = SPEC.read_text(encoding="utf-8")
    if "samples" in codigo:
        print(f"{ROJO}FALLA{FIN}: la palabra 'samples' aparece en el .spec")
        return False
    print(f"{VERDE}OK{FIN}: 'samples' no aparece en ningún sitio del .spec")
    return True


# --------------------------------------------------------------------------- #
# 6. data/*.toml declarados vs. abiertos de verdad por el código
# --------------------------------------------------------------------------- #

# El código nunca escribe la ruta completa como una sola cadena litera
# (`_RAIZ_REPO / "data" / "formats" / "haltech_nsp.toml"`, con "data" y
# "formats" como segmentos `Path` separados): lo que aparece como cadena es
# solo el NOMBRE del fichero. Por eso este patrón busca el nombre suelto, no
# "data/<nombre>", y por eso `comprobar_cobertura_de_datos` empareja por
# nombre de fichero, no por ruta relativa completa.
_PATRON_NOMBRE_TOML = re.compile(r'"([A-Za-z0-9_.-]+\.toml)"')
# Solo cuenta como "abierto de verdad" si el mismo fichero fuente también
# llama a `.open(` en algún sitio (no solo lo menciona en una docstring o un
# comentario de prosa, p. ej. "no va a `data/umbrales.toml`").
_PATRON_OPEN = re.compile(r"\.open\(")


def _rutas_data_citadas_en(ruta_py: Path) -> set[str]:
    texto = ruta_py.read_text(encoding="utf-8")
    if not _PATRON_OPEN.search(texto):
        return set()
    return {m.group(1) for m in _PATRON_NOMBRE_TOML.finditer(texto)}


def comprobar_cobertura_de_datos() -> bool:
    """`datas` copia TODO `data/` (ver el propio `.spec`), así que por
    construcción no puede faltar un fichero de `data/` en el paquete. Esta
    comprobación es sobre lo CONTRARIO -- qué de `data/` abre de verdad el
    código hoy -- para que el informe de la tarea pueda citar cómo se llegó
    a esa lista en vez de repetirla de memoria.
    """
    _titulo("6. data/*.toml: declarados en pyproject vs. abiertos por el código")
    dirs_codigo = [
        RAIZ / "dlv-api" / "src",
        RAIZ / "dlv-core" / "src",
        RAIZ / "dlv-app" / "src",
    ]
    citados: dict[str, list[str]] = {}
    for d in dirs_codigo:
        for f in d.rglob("*.py"):
            for nombre in _rutas_data_citadas_en(f):
                citados.setdefault(nombre, []).append(str(f.relative_to(RAIZ)))

    existentes = sorted(str(p.relative_to(RAIZ / "data")) for p in (RAIZ / "data").rglob("*.toml"))

    print("Ficheros bajo data/ (todos van dentro del paquete: se copia el directorio entero):")
    for nombre in existentes:
        base = Path(nombre).name
        if base in citados:
            ficheros = ", ".join(sorted(set(citados[base])))
            print(f"  {VERDE}abierto por código{FIN}  data/{nombre}  <- {ficheros}")
        else:
            print(f"  {AMARILLO}sin `open()` en dlv-api/dlv-core/dlv-app hoy{FIN}  data/{nombre}")
    print(
        f"\n{AMARILLO}Nota{FIN}: 'sin open() hoy' no es un error de este .spec -- el "
        "directorio se copia entero igualmente -- pero sí importa para el informe de la "
        "tarea: confirma con qué código YA existe la ruta de carga de cada .toml y con "
        "qué todavía no (p. ej. umbrales.toml/formulas.toml, ver el .spec)."
    )
    return True


# --------------------------------------------------------------------------- #


def main() -> int:
    resultados = [comprobar_sintaxis()]

    capturada = ejecutar_spec_con_comprobantes()
    if capturada is None:
        resultados.append(False)
    else:
        resultados.append(comprobar_datas(capturada))

    resultados.append(comprobar_samples_fuera_del_arbol_analizado())
    resultados.append(comprobar_cobertura_de_datos())

    _titulo("RESUMEN")
    fallos = resultados.count(False)
    if fallos:
        print(f"{ROJO}{fallos} comprobacion(es) en rojo.{FIN}")
    else:
        print(f"{VERDE}Todo lo comprobable en este entorno está en verde.{FIN}")
        print(
            f"{AMARILLO}Pero esto NO sustituye a un build real: hiddenimports/excludes, "
            f"tamaño del ZIP y arranque en frío siguen sin medirse (PyInstaller no "
            f"instalado aquí).{FIN}"
        )
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
