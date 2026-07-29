#!/usr/bin/env python3
"""Ejecutor de pruebas mínimo para entornos sin `pytest` instalado.

Motivo: el contenedor de desarrollo puede no tener red, y sin red no hay `pip`.
Las pruebas del proyecto se escriben para `pytest` de verdad (es lo que corre en
CI); este módulo inyecta un `pytest` de mentira lo bastante completo para
ejecutarlas y así poder verificar el trabajo sin conexión.

Soporta el subconjunto que usan las pruebas del proyecto:
    @pytest.fixture (con scope, ignorado)     pytest.raises
    @pytest.mark.parametrize                  pytest.skip / pytest.fail
    pytest.approx

Uso:
    python tools/pytest_minimo.py tests/test_units_catalogo.py [...]

Si `pytest` está disponible, usa ese en su lugar y no hagas caso de este fichero.
"""

from __future__ import annotations

import importlib.util
import inspect
import itertools
import sys
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class _Saltar(Exception):
    pass


class _Aprox:
    def __init__(self, valor: float, rel: float = 1e-6, abs_: float = 1e-12) -> None:
        self.valor, self.rel, self.abs = valor, rel, abs_

    def __eq__(self, otro: object) -> bool:
        import math

        return math.isclose(float(otro), self.valor, rel_tol=self.rel, abs_tol=self.abs)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        return f"approx({self.valor})"


class _Raises:
    def __init__(self, esperada: type[BaseException] | tuple[type[BaseException], ...]) -> None:
        self.esperada = esperada
        self.value: BaseException | None = None

    def __enter__(self) -> "_Raises":
        return self

    def __exit__(self, tipo, valor, tb) -> bool:
        if tipo is None:
            raise AssertionError(f"no se lanzó {self.esperada}")
        if not issubclass(tipo, self.esperada):
            return False
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
        def parametrize(nombres, valores):
            def envolver(f):
                f.__parametrize__ = (nombres, list(valores))
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

    mod.fixture = fixture                     # type: ignore[attr-defined]
    mod.mark = _Mark()                        # type: ignore[attr-defined]
    mod.raises = _Raises                      # type: ignore[attr-defined]
    mod.approx = _Aprox                       # type: ignore[attr-defined]
    mod.skip = saltar                         # type: ignore[attr-defined]
    mod.fail = fallar                         # type: ignore[attr-defined]
    mod.Saltar = _Saltar                      # type: ignore[attr-defined]
    return mod


def _cargar(ruta: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(ruta.stem, ruta)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ruta.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def ejecutar(ruta: Path) -> tuple[int, int, int, list[str]]:
    mod = _cargar(ruta)
    fixtures = {
        n: f for n, f in vars(mod).items()
        if callable(f) and getattr(f, "__es_fixture__", False)
    }
    cache: dict[str, object] = {}

    def resolver(nombre: str):
        if nombre not in cache:
            if nombre not in fixtures:
                raise KeyError(f"fixture desconocida: {nombre}")
            cache[nombre] = fixtures[nombre]()
        return cache[nombre]

    pruebas = [
        (n, f) for n, f in sorted(vars(mod).items())
        if n.startswith("test_") and callable(f)
    ]

    ok = fallos = saltadas = 0
    errores: list[str] = []

    for nombre, func in pruebas:
        params = inspect.signature(func).parameters
        pnombres, pvalores = getattr(func, "__parametrize__", (None, [(None,)]))
        if pnombres:
            claves = [c.strip() for c in pnombres.split(",")]
            casos = [
                dict(zip(claves, v if isinstance(v, (tuple, list)) else (v,)))
                for v in pvalores
            ]
        else:
            casos = [{}]

        for caso in casos:
            kwargs = dict(caso)
            for p in params:
                if p not in kwargs:
                    kwargs[p] = resolver(p)
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
