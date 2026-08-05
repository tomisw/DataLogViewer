#!/usr/bin/env python3
"""Ejecutor de pruebas mínimo para entornos sin `pytest` instalado.

Motivo: el contenedor de desarrollo puede no tener red, y sin red no hay `pip`.
Las pruebas del proyecto se escriben para `pytest` de verdad (es lo que corre en
CI); este módulo inyecta un `pytest` de mentira lo bastante completo para
ejecutarlas y así poder verificar el trabajo sin conexión.

Soporta el subconjunto que usan las pruebas del proyecto:

    @pytest.fixture             con scope (ignorado) y con fixtures encadenadas
    @pytest.mark.parametrize    nombres en cadena o en tupla, con `ids=`
    pytest.approx               escalares y secuencias, con `rel=` y `abs=`
    pytest.raises               con `match=`
    pytest.skip / pytest.fail / pytest.importorskip
    tmp_path                    la única fixture de pytest que se provee

Con esto recoge y ejecuta los mismos ficheros de prueba que `pytest` —comprobado
en `tests/test_verificar.py`— y salta la de `dlv-api`, que exige FastAPI.

Aun así, **un verde aquí no equivale a un verde con `pytest`**: hay comportamientos
que no se reproducen. `tools/verificar.py` lo marca en el resumen cuando ha tenido
que usar el sustituto, en vez de dar un verde indistinguible del de verdad.

Uso:
    python tools/pytest_minimo.py tests/test_units_catalogo.py [...]

Normalmente no se invoca a mano: lo hace `tools/verificar.py` cuando no encuentra
`pytest`. Si `pytest` está disponible, se usa ese y este fichero no interviene.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class _Saltar(Exception):
    pass


class _Aprox:
    # Los nombres de los parámetros son los de pytest (`rel` y `abs`), no unos
    # propios: las pruebas se escriben para pytest de verdad y este módulo solo
    # las ejecuta. `abs` tapa el builtin dentro del `__init__` y da igual; que la
    # firma sea la misma, no.
    def __init__(self, valor, rel: float = 1e-6, abs: float = 1e-12) -> None:
        self.valor, self.rel, self.abs = valor, rel, abs

    def __eq__(self, otro: object) -> bool:
        import math

        # `approx` de pytest compara también secuencias elemento a elemento. Sin
        # esto, una prueba que compara dos series (p. ej. el eje desenrollado de
        # F1-04) fallaba con un TypeError en vez de comparar.
        if isinstance(self.valor, (list, tuple)):
            if not isinstance(otro, (list, tuple)) or len(otro) != len(self.valor):
                return False
            return all(
                math.isclose(float(b), float(a), rel_tol=self.rel, abs_tol=self.abs)
                for a, b in zip(self.valor, otro, strict=True)
            )
        return math.isclose(float(otro), self.valor, rel_tol=self.rel, abs_tol=self.abs)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        return f"approx({self.valor})"


class _Raises:
    def __init__(
        self,
        esperada: type[BaseException] | tuple[type[BaseException], ...],
        match: str | None = None,
    ) -> None:
        self.esperada = esperada
        self.match = match
        self.value: BaseException | None = None

    def __enter__(self) -> _Raises:
        return self

    def __exit__(self, tipo, valor, tb) -> bool:
        if tipo is None:
            raise AssertionError(f"no se lanzó {self.esperada}")
        if not issubclass(tipo, self.esperada):
            return False
        if self.match is not None:
            import re

            if not re.search(self.match, str(valor)):
                raise AssertionError(f"{valor!r} no encaja con el patrón {self.match!r}")
        self.value = valor
        return True


def _construir_pytest() -> types.ModuleType:
    mod = types.ModuleType("pytest")

    def fixture(func=None, **_kw):
        def envolver(f):
            f.__es_fixture__ = True
            return f

        return envolver(func) if func is not None else envolver

    class _Mark:
        @staticmethod
        def parametrize(nombres, valores, ids=None):
            # `ids` importa cuando el caso es un diccionario leído de un TOML (la
            # tabla de F1-20): sin él, la etiqueta del fallo es el `repr` entero
            # de la fila y no se lee.
            def envolver(f):
                f.__parametrize__ = (nombres, list(valores), list(ids) if ids else None)
                return f

            return envolver

        def __getattr__(self, _nombre):  # skipif, xfail, etc.: no-op
            def deco(*_a, **_k):
                return lambda f: f

            return deco

    def saltar(motivo: str = "") -> None:
        raise _Saltar(motivo)

    def fallar(motivo: str = "") -> None:
        raise AssertionError(motivo)

    def importorskip(nombre: str, *_a, **_k):
        """Salta el fichero entero si el módulo no está instalado.

        Es como `dlv-api/tests/test_salud.py` evita fallar sin FastAPI. Al
        lanzarse durante la importación del fichero, `ejecutar` lo cuenta como
        fichero saltado y no como fallo.
        """
        try:
            return importlib.import_module(nombre)
        except ImportError as e:
            raise _Saltar(f"no está instalado: {nombre} ({e})") from None

    mod.importorskip = importorskip  # type: ignore[attr-defined]
    mod.fixture = fixture  # type: ignore[attr-defined]
    mod.mark = _Mark()  # type: ignore[attr-defined]
    mod.raises = _Raises  # type: ignore[attr-defined]
    mod.approx = _Aprox  # type: ignore[attr-defined]
    mod.skip = saltar  # type: ignore[attr-defined]
    mod.fail = fallar  # type: ignore[attr-defined]
    mod.Saltar = _Saltar  # type: ignore[attr-defined]
    return mod


def _cargar(ruta: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(ruta.stem, ruta)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ruta.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def ejecutar(ruta: Path) -> tuple[int, int, int, list[str]]:
    try:
        mod = _cargar(ruta)
    except _Saltar as e:
        # `pytest.importorskip` en el ámbito del módulo: el fichero entero se
        # salta. Sin esto, un fichero que exige FastAPI tumbaba toda la ejecución.
        return 0, 0, 1, [f"SALTADO {ruta}: {e}"]
    fixtures = {
        n: f for n, f in vars(mod).items() if callable(f) and getattr(f, "__es_fixture__", False)
    }
    cache: dict[str, object] = {}

    def resolver(nombre: str):
        # `tmp_path` es de pytest, no del proyecto, así que hay que proveerla. No
        # se cachea: cada prueba tiene que recibir un directorio propio, o dos
        # pruebas que escriban el mismo nombre de fichero se pisarían y el fallo
        # dependería del orden.
        if nombre == "tmp_path":
            import tempfile

            return Path(tempfile.mkdtemp(prefix="dlv-prueba-"))
        if nombre not in cache:
            if nombre not in fixtures:
                raise KeyError(
                    f"fixture desconocida: {nombre}. `tools/pytest_minimo.py` solo "
                    "provee las fixtures del propio fichero de pruebas y `tmp_path`; "
                    "con pytest de verdad instalado esto no ocurre."
                )
            # Una fixture puede pedir otras fixtures, y pytest las encadena. Sin
            # esto, `fila_de_referencia(log)` fallaba por falta de argumento.
            dependencias = {p: resolver(p) for p in inspect.signature(fixtures[nombre]).parameters}
            cache[nombre] = fixtures[nombre](**dependencias)
        return cache[nombre]

    pruebas = [
        (n, f) for n, f in sorted(vars(mod).items()) if n.startswith("test_") and callable(f)
    ]

    ok = fallos = saltadas = 0
    errores: list[str] = []

    for nombre, func in pruebas:
        params = inspect.signature(func).parameters
        pnombres, pvalores, pids = getattr(func, "__parametrize__", (None, [(None,)], None))
        if pnombres:
            # `parametrize` acepta los nombres como cadena separada por comas o
            # como tupla/lista, y pytest trata las dos igual. La forma de tupla
            # es la que ruff (RUF captura los argumentos sueltos) y la propia
            # documentación de pytest prefieren cuando hay más de un parámetro.
            claves = (
                [str(c).strip() for c in pnombres]
                if isinstance(pnombres, (tuple, list))
                else [c.strip() for c in pnombres.split(",")]
            )
            # Con UN solo nombre, el valor se pasa entero aunque sea una lista o
            # una tupla: `parametrize("celdas", [["a", "b"], ["c"]])` da dos
            # casos con una lista cada uno, no un caso de dos argumentos. Sin
            # esta distinción, este sustituto reventaba con `zip(strict=True)`
            # justo en las pruebas que parametrizan una lista, que es la forma
            # natural de probar una función que recibe una secuencia.
            casos = [
                {claves[0]: v} if len(claves) == 1 else dict(zip(claves, v, strict=True))
                for v in pvalores
            ]
        else:
            casos = [{}]

        for indice, caso in enumerate(casos):
            kwargs = dict(caso)
            for p in params:
                if p not in kwargs:
                    kwargs[p] = resolver(p)
            if pids and indice < len(pids):
                etiqueta = f"{nombre}[{pids[indice]}]"
            else:
                etiqueta = nombre + (f"[{','.join(map(str, caso.values()))}]" if caso else "")
            try:
                func(**kwargs)
                ok += 1
            except _Saltar as e:
                saltadas += 1
                errores.append(f"SALTADA {etiqueta}: {e}")
            except Exception:
                fallos += 1
                errores.append(f"FALLO {etiqueta}\n{traceback.format_exc()}")

    return ok, fallos, saltadas, errores


def main(argv: list[str]) -> int:
    if "pytest" not in sys.modules:
        sys.modules["pytest"] = _construir_pytest()

    rutas = [Path(a) for a in argv[1:]] or sorted((RAIZ / "tests").glob("test_*.py"))
    if not rutas:
        print("No hay pruebas que ejecutar.")
        return 0

    total_ok = total_fallos = total_saltadas = 0
    for ruta in rutas:
        if not ruta.exists():
            print(f"  no existe: {ruta}")
            total_fallos += 1
            continue
        ok, fallos, saltadas, errores = ejecutar(ruta)
        estado = "OK " if fallos == 0 else "FAL"
        print(f"[{estado}] {ruta}  {ok} pasan, {fallos} fallan, {saltadas} saltadas")
        for e in errores:
            print("   " + e.replace("\n", "\n   "))
        total_ok += ok
        total_fallos += fallos
        total_saltadas += saltadas

    print(f"\nTotal: {total_ok} pasan · {total_fallos} fallan · {total_saltadas} saltadas")
    return 1 if total_fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
