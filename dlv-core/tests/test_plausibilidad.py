"""Pruebas del informe de plausibilidad (tarea FG-10, `docs/07` §7.7).

Lo que hay que proteger, en orden de gravedad si se rompe:

1. **Un canal con la escala mal no puede pasar por bueno.** Es el fallo entero
   que esta tarea existe para cazar: nombre bien mapeado, escala equivocada,
   número plausible, decisión de tuning tomada sobre él. Se comprueba con un
   canal a factor 100 y con el caso AFR-en-vez-de-λ que `data/roles.toml` pide
   literalmente en `[roles.lambda_measured]`.
2. **Un canal correcto no puede generar nada.** Un informe que avisa siempre no
   se lee, y entonces el punto 1 tampoco sirve. De ahí la excursión corta, que
   NO debe salir como defecto, y los centinelas, que no se cuentan como
   muestras fuera de rango.
3. **Los umbrales no pueden estar cableados** (regla 3 de `CLAUDE.md`). Se
   comprueba de dos formas: la firma no tiene valores por omisión, y los
   números de `data/umbrales.toml [plausibilidad]` no aparecen como literales en
   el módulo. La segunda es deliberadamente literal, como
   `test_el_generador_no_contiene_umbrales_cableados`: un umbral cableado no
   rompe ninguna prueba funcional, así que lo único que lo detecta es buscarlo.
4. **Un canal que no se puede juzgar se dice, no se omite.** Un canal ausente
   del informe es indistinguible de un canal aprobado.
5. **La amplitud observada es un INTERVALO, no un punto.** La trampa del delta
   (F1-13) llegando por la puerta del informe: una amplitud de 10 K son 10 °C,
   no −263,15 °C.

Como `test_malla.py` y `test_reloj.py`, las pruebas usan `XpVec`, una
implementación de biblioteca estándar del protocolo `Vectorial`. No es un
simulacro: ejercita exactamente el mismo código de `evaluar_canal` que correrá
con NumPy, cuyas tres funciones son las que el protocolo declara.

Solo biblioteca estándar.
"""

from __future__ import annotations

import ast
import inspect
import math
import tomllib
from pathlib import Path
from typing import Any

import pytest

from dlv_core.informe_importacion import InformeImportacion
from dlv_core.plausibilidad import (
    CanalJuzgable,
    Diagnostico,
    ErrorDePlausibilidad,
    Hipotesis,
    UmbralesPlausibilidad,
    evaluar_canal,
    informe_de_plausibilidad,
    rango_en_unidad_activa,
)
from dlv_core.roles import Asignacion, Confianza, Rol, cargar_catalogo_roles
from dlv_core.unidades import (
    Afin,
    Catalogo,
    Dimension,
    Parametrizada,
    Unidad,
    cargar_catalogo,
)

RAIZ = Path(__file__).resolve().parents[2]
UMBRALES_TOML = RAIZ / "data" / "umbrales.toml"
ROLES_TOML = RAIZ / "data" / "roles.toml"
UNITS_TOML = RAIZ / "data" / "units.toml"
MODULO = RAIZ / "dlv-core" / "src" / "dlv_core" / "plausibilidad.py"


# --------------------------------------------------------------------------- #
# Implementación de `Vectorial` con biblioteca estándar
# --------------------------------------------------------------------------- #
class Vec(list[Any]):
    """Vector de biblioteca estándar con lo que `evaluar_canal` le pide.

    Los bucles están AQUÍ, en la prueba —igual que `Vec` en `test_malla.py`—
    que es donde ADR-009 permite que estén: lo que prohíbe es que estén en
    `dlv-core`. Con NumPy, cada uno de estos métodos es una pasada en C sobre el
    array completo.

    Distingue indexado por MÁSCARA booleana de indexado por posiciones enteras
    mirando el tipo del primer elemento de la clave: `bool` es un tipo de Python
    distinto de `int` (aunque sea su subclase), así que un índice `0`/`1` de
    verdad nunca se confunde con una máscara.
    """

    def __getitem__(self, clave: Any) -> Any:  # type: ignore[override]
        if isinstance(clave, slice):
            return Vec(list.__getitem__(self, clave))
        if isinstance(clave, (Vec, list, tuple)):
            claves = list(clave)
            if claves and isinstance(claves[0], bool):
                return Vec(v for v, m in zip(self, claves, strict=True) if m)
            return Vec(list.__getitem__(self, int(i)) for i in claves)
        return list.__getitem__(self, clave)

    def _cmp(self, otro: Any, op: Any) -> Vec:
        if isinstance(otro, list):
            return Vec(op(a, b) for a, b in zip(self, otro, strict=True))
        return Vec(op(a, otro) for a in self)

    def __eq__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._cmp(otro, lambda a, b: a == b)

    def __ne__(self, otro: Any) -> Any:  # type: ignore[override]
        # Explícito a propósito: el `__ne__` que Python deriva de `__eq__`
        # negaría el `Vec` resultante, y negar un `Vec` pasa por `__bool__`, que
        # lanza. Es el mismo motivo por el que NumPy define los dos.
        return self._cmp(otro, lambda a, b: a != b)

    def __lt__(self, otro: Any) -> Any:
        return self._cmp(otro, lambda a, b: a < b)

    def __gt__(self, otro: Any) -> Any:
        return self._cmp(otro, lambda a, b: a > b)

    def __and__(self, otro: Any) -> Any:
        return Vec(bool(a) and bool(b) for a, b in zip(self, otro, strict=True))

    def __or__(self, otro: Any) -> Any:
        return Vec(bool(a) or bool(b) for a, b in zip(self, otro, strict=True))

    def _op(self, otro: Any, op: Any) -> Vec:
        if isinstance(otro, list):
            return Vec(op(a, b) for a, b in zip(self, otro, strict=True))
        return Vec(op(a, otro) for a in self)

    def __add__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a + b)

    def __radd__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: b + a)

    def __sub__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a - b)

    def __mul__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a * b)

    __rmul__ = __mul__

    def __truediv__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a / b)

    def __rtruediv__(self, otro: Any) -> Any:
        # Las conversiones recíprocas de `units.toml` (φ, km/L) hacen `a / y`.
        return self._op(otro, lambda a, b: b / a)

    def __hash__(self) -> int:  # type: ignore[override]
        raise TypeError("un Vec no es hashable, igual que un array de NumPy")

    def __bool__(self) -> bool:
        # Igual que NumPy: el valor de verdad de un vector de longitud != 1 es
        # ambiguo. Sin esto, un `assert vec_a == vec_b` accidental compararía
        # elemento a elemento y luego evaluaría la lista como verdadera por ser
        # no vacía, sin comprobar nada.
        if len(self) == 1:
            return bool(list.__getitem__(self, 0))
        raise ValueError("el valor de verdad de un Vec de longitud != 1 es ambiguo")


class XpVec:
    """Las tres funciones del protocolo `Vectorial`, con los nombres de NumPy."""

    def sum(self, a: Any) -> Any:
        return sum(1 if x is True else (0 if x is False else x) for x in a)

    def min(self, a: Any) -> Any:
        return min(a)

    def max(self, a: Any) -> Any:
        return max(a)


@pytest.fixture
def xp() -> XpVec:
    return XpVec()


# --------------------------------------------------------------------------- #
# Catálogos mínimos, escritos a mano (aislados de los ficheros de `data/`)
# --------------------------------------------------------------------------- #
def _umbrales(**anulaciones: Any) -> UmbralesPlausibilidad:
    """Los umbrales de las pruebas unitarias, explícitos y no los del fichero.

    Deliberadamente NO se leen de `data/umbrales.toml`: una prueba que dependa
    de los valores por omisión cambiaría de veredicto si el propietario los
    ajusta, y entonces el rojo no diría nada sobre el código. Que el fichero
    real cargue y sea coherente se comprueba aparte, más abajo.
    """
    base = UmbralesPlausibilidad(
        fraccion_maxima_excursion=0.02,
        fraccion_maxima_tras_corregir=0.02,
        muestras_minimas=10,
        factores_candidatos=(-1.0, 10.0, 0.1, 100.0, 0.01, 1000.0, 0.001),
    )
    return base.fusionar(anulaciones)


def _rol_temperatura(critico: bool = True) -> Rol:
    return Rol(
        id="coolant_temp",
        dimension="temperature",
        sinonimos=("Coolant Temperature",),
        plausible_min=233.15,
        plausible_max=423.15,
        critico=critico,
    )


def _rol_lambda() -> Rol:
    return Rol(
        id="lambda_measured",
        dimension="mixture_ratio",
        sinonimos=("Wideband O2",),
        plausible_min=0.4,
        plausible_max=1.6,
        indexado=True,
        critico=True,
    )


def _rol_duty() -> Rol:
    return Rol(
        id="injector_duty",
        dimension="ratio",
        sinonimos=("Injector Duty Cycle",),
        plausible_min=0.0,
        plausible_max=1.2,
        critico=True,
    )


def _rol_sin_rango() -> Rol:
    return Rol(id="protection_cause", dimension="bitmask", sinonimos=("Protection Cause",))


def _catalogo_roles() -> dict[str, Rol]:
    return {r.id: r for r in (_rol_temperatura(), _rol_lambda(), _rol_duty(), _rol_sin_rango())}


def _catalogo_unidades() -> Catalogo:
    """Tres dimensiones con las unidades que importan para el diagnóstico.

    `mixture_ratio.afr` es `Parametrizada` con `parametro_rol =
    "stoichiometry"`, igual que en `data/units.toml`: es lo que el módulo
    reconoce por su ESTRUCTURA para diagnosticar «esta columna trae AFR».
    """
    temperatura = Dimension(
        id="temperature",
        etiqueta="Temperatura",
        unidad_canonica="K",
        unidades={
            "K": Unidad(id="K", etiqueta="K", conversion=Afin(a=1.0, b=0.0), decimales=1),
            "C": Unidad(id="C", etiqueta="°C", conversion=Afin(a=1.0, b=-273.15), decimales=1),
        },
    )
    mezcla = Dimension(
        id="mixture_ratio",
        etiqueta="Mezcla",
        unidad_canonica="lambda",
        unidades={
            "lambda": Unidad(id="lambda", etiqueta="λ", conversion=Afin(a=1.0, b=0.0), decimales=3),
            "afr": Unidad(
                id="afr",
                etiqueta="AFR",
                conversion=Parametrizada(parametro_rol="stoichiometry", a_por_omision=14.7),
                decimales=2,
            ),
        },
    )
    ratio = Dimension(
        id="ratio",
        etiqueta="Proporción",
        unidad_canonica="frac",
        unidades={
            "frac": Unidad(id="frac", etiqueta="", conversion=Afin(a=1.0, b=0.0), decimales=3),
            "pct": Unidad(id="pct", etiqueta="%", conversion=Afin(a=100.0, b=0.0), decimales=1),
        },
    )
    return Catalogo(
        dimensiones={"temperature": temperatura, "mixture_ratio": mezcla, "ratio": ratio},
        presets={},
        centinelas_i32=frozenset(),
        centinelas_texto=frozenset(),
        referencia_presion_por_omision_kpa=101.325,
    )


def _exacta(rol: str) -> Asignacion:
    return Asignacion(rol=rol, confianza=Confianza.EXACTA, sinonimo=rol)


def _difusa(rol: str) -> Asignacion:
    return Asignacion(rol=rol, confianza=Confianza.DIFUSA, sinonimo=rol, parecido=0.88)


def _evaluar(canal: CanalJuzgable, xp: XpVec, **kwargs: Any) -> Any:
    return evaluar_canal(
        canal,
        _catalogo_roles(),
        umbrales=kwargs.pop("umbrales", _umbrales()),
        catalogo_unidades=kwargs.pop("catalogo_unidades", _catalogo_unidades()),
        xp=xp,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# 1. Un canal correcto no genera nada
# --------------------------------------------------------------------------- #
def test_un_canal_correcto_sale_plausible_y_sin_defecto(xp: XpVec) -> None:
    """El caso que tiene que ser silencioso: refrigerante subiendo de 20 a 93 °C."""
    valores = Vec([293.15 + i * 0.5 for i in range(150)])
    h = _evaluar(CanalJuzgable("Coolant Temperature", valores, _exacta("coolant_temp")), xp)
    assert h.diagnostico is Diagnostico.PLAUSIBLE
    assert not h.diagnostico.es_defecto
    assert h.n_fuera == 0
    assert h.fraccion_fuera == 0.0
    assert h.severidad == "informativa"
    assert h.factor_que_arregla is None
    assert h.minimo_observado == pytest.approx(293.15)
    assert h.maximo_observado == pytest.approx(293.15 + 149 * 0.5)


def test_el_informe_de_un_log_bien_importado_no_tiene_defectos(xp: XpVec) -> None:
    canales = [
        CanalJuzgable(
            "Coolant Temperature",
            Vec([350.0 + i * 0.1 for i in range(200)]),
            _exacta("coolant_temp"),
        ),
        CanalJuzgable(
            "Wideband O2",
            Vec([0.85 + (i % 20) * 0.005 for i in range(200)]),
            _exacta("lambda_measured"),
        ),
    ]
    informe = informe_de_plausibilidad(
        canales,
        _catalogo_roles(),
        umbrales=_umbrales(),
        catalogo_unidades=_catalogo_unidades(),
        xp=xp,
    )
    assert informe.defectos == ()
    assert len(informe.plausibles) == 2
    assert informe.avisos() == ()
    assert "Todos los canales" in informe.a_lineas()[-1]


# --------------------------------------------------------------------------- #
# 2. Un canal con la escala mal: el defecto que justifica la tarea
# --------------------------------------------------------------------------- #
def test_un_factor_100_se_diagnostica_y_dice_el_factor_que_lo_arregla(xp: XpVec) -> None:
    """Refrigerante en centikelvin: 36 600 en vez de 366,0.

    Ninguna unidad de la dimensión lo explica (ni °C ni K), así que el
    diagnóstico tiene que ser el factor desnudo, y el informe tiene que decir
    cuál: sin eso, quien revisa tiene que volver al log a deducirlo.
    """
    valores = Vec([36000.0 + i * 10.0 for i in range(100)])
    h = _evaluar(CanalJuzgable("Coolant Temperature", valores, _exacta("coolant_temp")), xp)
    assert h.diagnostico is Diagnostico.ESCALA_ERRONEA
    assert h.diagnostico.es_defecto
    assert h.fraccion_fuera == 1.0
    assert h.factor_que_arregla == pytest.approx(0.01)
    assert h.fraccion_fuera_corregida == 0.0
    # El factor tiene que estar EN LA FRASE, en las dos direcciones: es lo que
    # lee una persona, y «0,01» a secas se confunde con un umbral.
    assert "0,01" in h.detalle
    assert "100" in h.detalle
    # Rol crítico + defecto = lo primero que hay que mirar.
    assert h.severidad == "critica"


def test_un_porcentaje_leido_como_fraccion_nombra_la_unidad_culpable(xp: XpVec) -> None:
    """El duty de inyección al 0-100 en vez de 0-1.

    Aquí SÍ hay una unidad que lo explica (`pct`), y nombrarla es mejor que
    proponer un factor: «declara que esa columna viene en %» es una acción, y
    «multiplica por 0,01» es un parche que alguien tendrá que justificar
    después.
    """
    valores = Vec([float(i % 90) + 5.0 for i in range(100)])
    h = _evaluar(CanalJuzgable("Injector Duty Cycle", valores, _exacta("injector_duty")), xp)
    assert h.diagnostico is Diagnostico.UNIDAD_EQUIVOCADA
    assert h.unidad_probable == "pct"
    assert h.factor_que_arregla == pytest.approx(0.01)
    assert "pct" in h.detalle


def test_el_canal_de_lambda_que_trae_afr_se_diagnostica_como_tal(xp: XpVec) -> None:
    """El caso que `data/roles.toml` pide cazar en `[roles.lambda_measured]`.

    Y el que explica por qué las hipótesis con nombre se prueban ANTES que los
    factores desnudos: 14,7 / 10 = 1,47, que cae dentro del rango de λ, así que
    un informe que probara primero los factores diría «divide entre 10» sobre un
    canal cuyo problema es que trae AFR. Sería un número plausible y una
    explicación falsa, exactamente el tipo de error que esta tarea persigue.
    """
    valores = Vec([14.0 + (i % 8) * 0.15 for i in range(120)])
    h = _evaluar(CanalJuzgable("Wideband O2", valores, _exacta("lambda_measured")), xp)
    assert h.diagnostico is Diagnostico.AFR_EN_VEZ_DE_LAMBDA
    assert h.unidad_probable == "afr"
    assert h.factor_que_arregla == pytest.approx(1.0 / 14.7)
    assert "AFR" in h.detalle
    assert h.severidad == "critica"


def test_la_estequiometria_del_log_manda_sobre_la_de_por_omision(xp: XpVec) -> None:
    """Un log de E85: los valores rondan 9,77, no 14,7.

    Con la estequiometría del propio log (rol `stoichiometry`, resuelto por
    F1-14) el canal se explica; el 14,7 de `data/units.toml` es solo el valor
    por omisión y este módulo no lleva ninguna copia de ninguno de los dos.
    """
    valores = Vec([9.3 + (i % 10) * 0.1 for i in range(120)])
    h = _evaluar(
        CanalJuzgable("Wideband O2", valores, _exacta("lambda_measured")),
        xp,
        estequiometria=9.77,
    )
    assert h.diagnostico is Diagnostico.AFR_EN_VEZ_DE_LAMBDA
    assert h.factor_que_arregla == pytest.approx(1.0 / 9.77)


def test_un_canal_con_el_signo_invertido_se_diagnostica_como_signo(xp: XpVec) -> None:
    """La corrección más pequeña que encaja es la que se propone: entre invertir
    el signo y desplazar tres órdenes de magnitud, lo primero."""
    valores = Vec([-0.3 - (i % 50) * 0.01 for i in range(100)])
    h = _evaluar(CanalJuzgable("Injector Duty Cycle", valores, _exacta("injector_duty")), xp)
    assert h.diagnostico is Diagnostico.SIGNO_INVERTIDO
    assert h.factor_que_arregla == -1.0
    assert "signo" in h.detalle


def test_sin_catalogo_de_unidades_el_informe_sigue_dando_el_factor(xp: XpVec) -> None:
    """El catálogo de unidades es opcional: sin él se pierde el NOMBRE de la
    unidad culpable, no la detección."""
    valores = Vec([float(i % 90) + 5.0 for i in range(100)])
    h = _evaluar(
        CanalJuzgable("Injector Duty Cycle", valores, _exacta("injector_duty")),
        xp,
        catalogo_unidades=None,
    )
    assert h.diagnostico is Diagnostico.ESCALA_ERRONEA
    assert h.unidad_probable is None
    assert h.factor_que_arregla == pytest.approx(0.01)


def test_fuera_de_rango_sin_explicacion_no_inventa_un_factor(xp: XpVec) -> None:
    """La mitad del log con el sensor desconectado a 500 K.

    Ni una unidad ni un factor pueden explicar la mitad de un canal, y proponer
    uno sería inventar. La respuesta honesta es decir cuánto está fuera y que
    hace falta mirarlo.
    """
    valores = Vec([360.0] * 60 + [500.0] * 60)
    h = _evaluar(CanalJuzgable("Coolant Temperature", valores, _exacta("coolant_temp")), xp)
    assert h.diagnostico is Diagnostico.FUERA_DE_RANGO_SIN_EXPLICAR
    assert h.factor_que_arregla is None
    assert h.fraccion_fuera == pytest.approx(0.5)
    assert h.n_fuera == 60


def test_un_rol_difuso_fuera_de_rango_avisa_de_mirar_el_rol_primero(xp: XpVec) -> None:
    """Mitigación de R10 (docs/07 §7.15) en el informe: si el rol se asignó por
    parecido de nombre, un canal fuera de rango es antes un rol mal asignado que
    una escala mal puesta, y el orden de comprobación importa."""
    valores = Vec([36000.0 + i * 10.0 for i in range(100)])
    h = _evaluar(CanalJuzgable("Coolant Temp Sensor", valores, _difusa("coolant_temp")), xp)
    assert h.rol_sin_confirmar
    assert "PRIMERO" in h.detalle


def test_una_dimension_distinta_de_la_del_rol_gana_a_cualquier_rango(xp: XpVec) -> None:
    """El caso real que obliga a que esta comprobación exista.

    `Fuel Flow Estimated` del AutoLog viene en L/h (dimensión `volume_flow`, el
    tipo `Flow` del descriptor) y el rol `fuel_flow` espera kg/h (`mass_flow`).
    Sus 17,7 L/h caen DENTRO del rango de 0 a 500 kg/h del rol, así que el
    rango solo lo aprobaría: un número plausible en la magnitud equivocada, que
    es exactamente el error que este informe existe para cazar. Aquí se
    reproduce con el rol de temperatura y un canal declarado en presión.
    """
    valores = Vec([360.0 + (i % 10) for i in range(100)])  # dentro del rango del rol
    h = _evaluar(
        CanalJuzgable(
            "Presion disfrazada",
            valores,
            _exacta("coolant_temp"),
            dimension_declarada="pressure",
        ),
        xp,
    )
    assert h.diagnostico is Diagnostico.DIMENSION_DISTINTA_DEL_ROL
    assert h.diagnostico.es_defecto
    assert h.n_fuera == 0  # el rango lo habría aprobado, y ese es el punto
    assert "pressure" in h.detalle
    assert "temperature" in h.detalle
    assert h.factor_que_arregla is None
    assert h.severidad == "critica"  # `coolant_temp` es un rol crítico


def test_la_dimension_declarada_coincidente_no_estorba(xp: XpVec) -> None:
    valores = Vec([360.0 + (i % 10) for i in range(100)])
    h = _evaluar(
        CanalJuzgable(
            "Coolant Temperature",
            valores,
            _exacta("coolant_temp"),
            dimension_declarada="temperature",
        ),
        xp,
    )
    assert h.diagnostico is Diagnostico.PLAUSIBLE


def test_una_dimension_desconocida_no_choca_con_nada(xp: XpVec) -> None:
    """Los tipos `confianza = "unknown"` de `data/formats/haltech_nsp.toml` se
    declaran con dimensión `unknown` a propósito (mitigación de R1). Eso es la
    AUSENCIA de una dimensión, no una dimensión distinta, y tratarlo como choque
    llenaría el informe de falsos defectos en los canales que el descriptor ya
    marca como no interpretables.

    Quedan cinco tipos así tras F1-38, que cerró dos de los siete. El canal de
    ejemplo era `Angular Velocity` precisamente hasta esa tarea: ahora tiene
    dimensión `angular_speed`, así que se usa uno de los que siguen abiertos.
    """
    valores = Vec([360.0 + (i % 10) for i in range(100)])
    h = _evaluar(
        CanalJuzgable(
            "Vehicle Speed 0 Calculated Rate",
            valores,
            _exacta("coolant_temp"),
            dimension_declarada="unknown",
        ),
        xp,
    )
    assert h.diagnostico is Diagnostico.PLAUSIBLE


def test_el_choque_de_dimension_no_espera_a_tener_muestras_suficientes(xp: XpVec) -> None:
    """Es estructural, no estadístico: se sabe con tres muestras igual que con
    tres mil, y mientras esté ahí el rango del rol compara magnitudes
    distintas."""
    h = _evaluar(
        CanalJuzgable(
            "Presion disfrazada",
            Vec([360.0, 361.0, 362.0]),
            _exacta("coolant_temp"),
            dimension_declarada="pressure",
        ),
        xp,
    )
    assert h.diagnostico is Diagnostico.DIMENSION_DISTINTA_DEL_ROL


def test_el_choque_de_dimension_tambien_se_ve_sin_rango_declarado(xp: XpVec) -> None:
    """Un rol sin rango plausible no se puede juzgar por rango, pero sí por
    dimensión: son dos comprobaciones independientes y la segunda sigue
    disponible."""
    h = _evaluar(
        CanalJuzgable(
            "Protection Cause",
            Vec([float(i % 7) for i in range(100)]),
            _exacta("protection_cause"),
            dimension_declarada="pressure",
        ),
        xp,
    )
    assert h.diagnostico is Diagnostico.DIMENSION_DISTINTA_DEL_ROL


# --------------------------------------------------------------------------- #
# 3. Excursión contra canal desplazado
# --------------------------------------------------------------------------- #
def test_una_excursion_corta_no_es_un_defecto(xp: XpVec) -> None:
    """Dos muestras de 200 fuera de rango (1 %): el arranque, no la escala.

    Es el falso positivo más caro que puede tener este informe: si una excursión
    de arranque saliera como defecto, cada canal del log tendría su aviso y la
    lista entera se ignoraría.
    """
    valores = Vec([230.0, 231.0] + [360.0 + (i % 10) for i in range(198)])
    h = _evaluar(CanalJuzgable("Coolant Temperature", valores, _exacta("coolant_temp")), xp)
    assert h.diagnostico is Diagnostico.EXCURSION
    assert not h.diagnostico.es_defecto
    assert h.n_fuera == 2
    assert h.fraccion_fuera == pytest.approx(0.01)
    assert h.factor_que_arregla is None
    # Rol crítico: la excursión se ve, pero por debajo de cualquier defecto.
    assert h.severidad == "media"


def test_la_excursion_se_decide_antes_de_buscar_hipotesis(xp: XpVec) -> None:
    """El orden que evita el falso positivo más sutil de todos.

    `injector_duty` admite 0 a 1,2. Un canal correcto que llega a 1,3 en una
    muestra de 200 está bien; pero dividirlo entre 10 también lo metería
    «dentro» del rango, así que un informe que probara hipótesis antes de
    comprobar la fracción propondría corregir la escala de un canal
    perfectamente escalado. Un canal con la inmensa mayoría de sus muestras
    dentro de su rango tiene, por definición, la escala correcta.
    """
    valores = Vec([1.3] + [0.4 + (i % 40) * 0.01 for i in range(199)])
    h = _evaluar(CanalJuzgable("Injector Duty Cycle", valores, _exacta("injector_duty")), xp)
    assert h.diagnostico is Diagnostico.EXCURSION
    assert h.factor_que_arregla is None


def test_el_umbral_de_excursion_es_configurable(xp: XpVec) -> None:
    """El mismo canal, dos veredictos, según el umbral: es la propiedad que pide
    la regla 3 de `CLAUDE.md`."""
    valores = Vec([230.0, 231.0] + [360.0 + (i % 10) for i in range(198)])
    canal = CanalJuzgable("Coolant Temperature", valores, _exacta("coolant_temp"))
    tolerante = _evaluar(canal, xp, umbrales=_umbrales(fraccion_maxima_excursion=0.02))
    estricto = _evaluar(canal, xp, umbrales=_umbrales(fraccion_maxima_excursion=0.0))
    assert tolerante.diagnostico is Diagnostico.EXCURSION
    assert estricto.diagnostico is not Diagnostico.EXCURSION


# --------------------------------------------------------------------------- #
# 4. Los centinelas no son medidas
# --------------------------------------------------------------------------- #
def test_los_centinelas_no_se_cuentan_como_fuera_de_rango(xp: XpVec) -> None:
    """`docs/01` §1.13: −2147483639 en un canal de resistencia es «sin dato».

    Sin excluirlos, este canal saldría con el 25 % de sus muestras fuera y una
    hipótesis de factor absurda: el informe entero se convertiría en ruido.
    """
    valores = Vec([360.0 + (i % 10) for i in range(150)] + [-2147483639.0] * 50)
    h = _evaluar(
        CanalJuzgable(
            "Coolant Temperature",
            valores,
            _exacta("coolant_temp"),
            centinelas=(-2147483639.0, 2147483647.0),
        ),
        xp,
    )
    assert h.diagnostico is Diagnostico.PLAUSIBLE
    assert h.n_muestras == 200
    assert h.n_validas == 150
    assert h.n_centinelas == 50
    assert h.n_fuera == 0
    # El mínimo observado es del dato real, no del centinela.
    assert h.minimo_observado == pytest.approx(360.0)


def test_un_canal_entero_de_centinelas_es_un_hallazgo_no_un_silencio(xp: XpVec) -> None:
    """El canal 3 de `Resistance` del AutoLog real: todo centinela.

    `data/formats/haltech_nsp.toml` lo escribe al lado del tipo. No mide nada, y
    decirlo importa: un detector que dependa de él está apagado.
    """
    valores = Vec([-2147483639.0] * 80)
    h = _evaluar(
        CanalJuzgable(
            "Coolant Temperature", valores, _exacta("coolant_temp"), centinelas=(-2147483639.0,)
        ),
        xp,
    )
    assert h.diagnostico is Diagnostico.SIN_DATOS
    assert h.n_validas == 0
    assert h.n_centinelas == 80
    assert "centinelas" in h.detalle
    # Rol crítico sin datos: un detector crítico apagado sin que nadie lo decida.
    assert h.severidad == "media"


def test_los_huecos_no_cuentan_como_muestras(xp: XpVec) -> None:
    """El muestreo es disperso y multifrecuencia (`docs/01` §1.4): un canal a
    5 Hz tiene hueco en la mayoría de las marcas de tiempo, y eso es normal, no
    una anomalía. Un NaN no es un valor fuera de rango."""
    nan = float("nan")
    valores = Vec([360.0, nan, 361.0, nan] * 50)
    h = _evaluar(CanalJuzgable("Coolant Temperature", valores, _exacta("coolant_temp")), xp)
    assert h.diagnostico is Diagnostico.PLAUSIBLE
    assert h.n_muestras == 200
    assert h.n_validas == 100
    assert h.n_huecos == 100
    assert h.n_centinelas == 0


# --------------------------------------------------------------------------- #
# 5. Lo que no se puede juzgar se dice
# --------------------------------------------------------------------------- #
def test_un_canal_sin_rol_aparece_en_el_informe(xp: XpVec) -> None:
    """No se omite en silencio: un canal ausente del informe es indistinguible
    de un canal aprobado."""
    valores = Vec([float(i) for i in range(100)])
    h = _evaluar(CanalJuzgable("Angular Velocity", valores, None), xp)
    assert h.diagnostico is Diagnostico.SIN_ROL
    assert not h.diagnostico.es_defecto
    assert not h.diagnostico.es_juzgable
    assert h.rol is None
    assert "sin rol" in h.detalle
    # Aun sin poder juzgarlo, el rango observado se informa: es lo que permite
    # asignarle un rol a mano con criterio.
    assert h.minimo_observado == 0.0
    assert h.maximo_observado == 99.0


def test_un_rol_sin_rango_declarado_no_se_juzga(xp: XpVec) -> None:
    valores = Vec([float(i % 7) for i in range(100)])
    h = _evaluar(CanalJuzgable("Protection Cause", valores, _exacta("protection_cause")), xp)
    assert h.diagnostico is Diagnostico.SIN_RANGO
    assert not h.diagnostico.es_juzgable
    assert h.rango_plausible is None


def test_pocas_muestras_no_se_juzgan(xp: XpVec) -> None:
    """Con menos muestras que 1/fraccion_maxima_excursion, una sola fuera de
    rango ya supera el umbral: la fracción no distingue nada."""
    valores = Vec([36000.0] * 5)
    h = _evaluar(CanalJuzgable("Coolant Temperature", valores, _exacta("coolant_temp")), xp)
    assert h.diagnostico is Diagnostico.POCAS_MUESTRAS
    assert not h.diagnostico.es_juzgable


def test_un_canal_vacio_no_revienta(xp: XpVec) -> None:
    h = _evaluar(CanalJuzgable("Coolant Temperature", Vec([]), _exacta("coolant_temp")), xp)
    assert h.diagnostico is Diagnostico.SIN_DATOS
    assert h.n_muestras == 0


# --------------------------------------------------------------------------- #
# 6. El informe: orden por consecuencia
# --------------------------------------------------------------------------- #
def test_el_informe_se_ordena_por_consecuencia_no_por_aparicion(xp: XpVec) -> None:
    """Regla 6 de `CLAUDE.md` para una puerta G1: primero lo que más duele si el
    número está mal. Un rol `critico = true` con la escala equivocada va antes
    que uno accesorio, y las dos cosas antes que una excursión."""
    canales = [
        CanalJuzgable("Sin rol", Vec([float(i) for i in range(100)]), None),
        CanalJuzgable(
            "Excursion critica",
            Vec([230.0, 231.0] + [360.0] * 198),
            _exacta("coolant_temp"),
        ),
        CanalJuzgable(
            "Escala accesoria",
            Vec([float(i % 90) + 5.0 for i in range(100)]),
            _exacta("protection_cause"),
        ),
        CanalJuzgable(
            "Escala critica", Vec([36000.0 + i for i in range(100)]), _exacta("coolant_temp")
        ),
        CanalJuzgable("Plausible", Vec([360.0] * 100), _exacta("coolant_temp")),
    ]
    informe = informe_de_plausibilidad(
        canales,
        _catalogo_roles(),
        umbrales=_umbrales(),
        catalogo_unidades=_catalogo_unidades(),
        xp=xp,
    )
    assert informe.hallazgos[0].canal == "Escala critica"
    assert informe.hallazgos[0].severidad == "critica"
    severidades = [h.severidad for h in informe.hallazgos]
    orden = ["critica", "alta", "media", "baja", "informativa"]
    assert severidades == sorted(severidades, key=orden.index)
    assert len(informe.defectos) == 1
    assert len(informe.excursiones) == 1
    assert len(informe.no_juzgables) == 2  # el sin rol y el rol sin rango


def test_el_informe_solo_detalla_lo_que_hay_que_mirar(xp: XpVec) -> None:
    """Los canales plausibles se cuentan pero no se listan: 300 líneas de «está
    bien» esconden las 3 que importan. La cuenta sí sale, porque es lo que dice
    que el informe ha mirado de verdad."""
    canales = [
        CanalJuzgable(f"Bueno {i}", Vec([360.0] * 100), _exacta("coolant_temp")) for i in range(20)
    ]
    canales.append(
        CanalJuzgable("Malo", Vec([36000.0 + i for i in range(100)]), _exacta("coolant_temp"))
    )
    informe = informe_de_plausibilidad(
        canales,
        _catalogo_roles(),
        umbrales=_umbrales(),
        catalogo_unidades=_catalogo_unidades(),
        xp=xp,
    )
    lineas = informe.a_lineas()
    assert "20 plausibles" in lineas[0]
    assert sum(1 for line in lineas if "Bueno" in line) == 0
    assert sum(1 for line in lineas if "Malo" in line) == 1


def test_los_defectos_se_pueden_agregar_al_informe_de_importacion(xp: XpVec) -> None:
    """F1-12: el informe de importación es donde el usuario ve los avisos de la
    carga, y los defectos de plausibilidad son avisos de la carga."""
    canales = [
        CanalJuzgable("Malo", Vec([36000.0 + i for i in range(100)]), _exacta("coolant_temp")),
        CanalJuzgable("Bueno", Vec([360.0] * 100), _exacta("coolant_temp")),
    ]
    informe = informe_de_plausibilidad(
        canales,
        _catalogo_roles(),
        umbrales=_umbrales(),
        catalogo_unidades=_catalogo_unidades(),
        xp=xp,
    )
    importacion = InformeImportacion()
    importacion.agregar(informe.avisos())
    assert importacion.total == 1
    assert importacion.todos()[0].codigo == "escala_erronea"


def test_el_informe_es_serializable(xp: XpVec) -> None:
    canales = [
        CanalJuzgable("Malo", Vec([36000.0 + i for i in range(100)]), _exacta("coolant_temp"))
    ]
    informe = informe_de_plausibilidad(
        canales,
        _catalogo_roles(),
        umbrales=_umbrales(),
        catalogo_unidades=_catalogo_unidades(),
        xp=xp,
    )
    d = informe.a_dict()
    assert d["total"] == 1
    assert d["defectos"] == 1
    assert d["hallazgos"][0]["factor_que_arregla"] == pytest.approx(0.01)
    assert d["hallazgos"][0]["rango_plausible"] == [233.15, 423.15]


# --------------------------------------------------------------------------- #
# 7. La amplitud observada es un INTERVALO
# --------------------------------------------------------------------------- #
def test_el_rango_observado_se_convierte_con_la_clase_correcta(xp: XpVec) -> None:
    """La trampa del delta (F1-13) llegando por la puerta del informe.

    El mínimo y el máximo son PUNTOS y llevan el −273,15; la amplitud es un
    INTERVALO y NO lo lleva. Con la clase equivocada, una amplitud de 70 K
    saldría como −203,15 °C, que es el síntoma más reconocible del defecto.
    """
    valores = Vec([293.15 + i for i in range(71)])
    h = _evaluar(CanalJuzgable("Coolant Temperature", valores, _exacta("coolant_temp")), xp)
    mostrado = rango_en_unidad_activa(
        h, dimension=_catalogo_unidades().dimension("temperature"), unidad="C"
    )
    assert mostrado is not None
    assert mostrado.minimo == pytest.approx(20.0)
    assert mostrado.maximo == pytest.approx(90.0)
    assert mostrado.amplitud == pytest.approx(70.0)
    assert mostrado.etiqueta_unidad == "°C"


def test_el_rango_observado_de_un_canal_sin_datos_es_none(xp: XpVec) -> None:
    h = _evaluar(CanalJuzgable("Coolant Temperature", Vec([]), _exacta("coolant_temp")), xp)
    assert (
        rango_en_unidad_activa(
            h, dimension=_catalogo_unidades().dimension("temperature"), unidad="C"
        )
        is None
    )


# --------------------------------------------------------------------------- #
# 8. Los umbrales no están cableados (regla 3 de CLAUDE.md)
# --------------------------------------------------------------------------- #
def test_los_umbrales_no_tienen_valor_por_omision() -> None:
    """La decisión de diseño que hace improbable el defecto, no solo detectable.

    Un valor por omisión en el código es una copia del fichero de datos que se
    puede desincronizar sin que nada se ponga en rojo. Se comprueba sobre la
    firma real, igual que `test_no_hay_clase_por_omision` en
    `test_trampa_del_delta.py`.
    """
    for nombre, p in inspect.signature(UmbralesPlausibilidad).parameters.items():
        assert p.default is inspect.Parameter.empty, (
            f"UmbralesPlausibilidad.{nombre} tiene valor por omisión: eso es una copia "
            "del umbral de data/umbrales.toml que puede desincronizarse en silencio"
        )


def test_el_modulo_no_contiene_los_umbrales_cableados() -> None:
    """Inspección de los literales del módulo, deliberadamente literal.

    Un umbral cableado no rompe ninguna prueba funcional —el módulo sigue siendo
    coherente consigo mismo— así que lo único que lo detecta es buscarlo. Se
    hace sobre el AST y no sobre el texto para no marcar los números que
    aparecen en los comentarios y en los docstrings explicando de dónde salen
    (la trampa que ya se pagó con el detector de ADR-009).
    """
    with UMBRALES_TOML.open("rb") as fh:
        plausibilidad = tomllib.load(fh)["plausibilidad"]
    prohibidos = {
        float(plausibilidad["fraccion_maxima_excursion"]),
        float(plausibilidad["fraccion_maxima_tras_corregir"]),
        float(plausibilidad["muestras_minimas"]),
        *(float(f) for f in plausibilidad["factores_candidatos"]),
    }
    # 1 y −1 no cuentan: el módulo los usa para validar (un factor de 1 no
    # corrige nada) y para nombrar la inversión de signo, no como umbral.
    prohibidos -= {1.0, -1.0}
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"), filename=str(MODULO))
    encontrados = sorted(
        {
            float(n.value)
            for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
            if not isinstance(n.value, bool) and float(n.value) in prohibidos
        }
    )
    assert not encontrados, (
        f"umbrales de data/umbrales.toml [plausibilidad] cableados en el módulo: {encontrados}"
    )


def test_falta_una_clave_de_umbral_y_falla_en_vez_de_suponerla() -> None:
    with pytest.raises(ErrorDePlausibilidad, match="muestras_minimas"):
        UmbralesPlausibilidad.desde_mapa(
            {
                "fraccion_maxima_excursion": 0.02,
                "fraccion_maxima_tras_corregir": 0.02,
                "factores_candidatos": [10.0],
            }
        )


def test_una_anulacion_mal_escrita_no_se_ignora_en_silencio() -> None:
    """Una anulación por canal con el nombre mal escrito seguiría usando el valor
    por omisión sin decir nada, y quien la escribió creería que está activa."""
    with pytest.raises(ErrorDePlausibilidad, match="desconocidas"):
        _umbrales(fracion_maxima_excursion=0.5)


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("fraccion_maxima_excursion", 1.0),
        ("fraccion_maxima_excursion", -0.1),
        ("fraccion_maxima_tras_corregir", 2.0),
        ("muestras_minimas", 0),
        ("factores_candidatos", (1.0,)),
        ("factores_candidatos", (0.0,)),
    ],
)
def test_un_umbral_absurdo_se_rechaza(clave: str, valor: Any) -> None:
    with pytest.raises(ErrorDePlausibilidad):
        _umbrales(**{clave: valor})


def test_una_hipotesis_declara_exactamente_una_cosa() -> None:
    with pytest.raises(ErrorDePlausibilidad, match="exactamente una"):
        Hipotesis(unidad="pct", factor=0.01)
    with pytest.raises(ErrorDePlausibilidad, match="exactamente una"):
        Hipotesis()


def test_los_umbrales_por_canal_ganan_a_los_del_fichero(xp: XpVec) -> None:
    """Primer nivel de la precedencia de `data/umbrales.toml`: anulación por
    canal."""
    valores = Vec([230.0, 231.0] + [360.0] * 198)
    canal = CanalJuzgable("Coolant Temperature", valores, _exacta("coolant_temp"))
    informe = informe_de_plausibilidad(
        [canal],
        _catalogo_roles(),
        umbrales=_umbrales(),
        catalogo_unidades=_catalogo_unidades(),
        umbrales_por_canal={"Coolant Temperature": _umbrales(fraccion_maxima_excursion=0.0)},
        xp=xp,
    )
    assert informe.hallazgos[0].diagnostico is not Diagnostico.EXCURSION


# --------------------------------------------------------------------------- #
# 9. Contra los catálogos reales de `data/`
# --------------------------------------------------------------------------- #
def test_los_umbrales_reales_cargan_y_son_coherentes() -> None:
    """Que el fichero de datos y el módulo encajen, y que el umbral de muestras
    mínimas siga significando lo que su comentario dice.

    La invariante, no el valor: con menos muestras que `1 /
    fraccion_maxima_excursion`, una sola muestra fuera de rango ya supera el
    umbral de excursión y la fracción deja de distinguir un canal desplazado de
    un pico aislado.
    """
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    u = UmbralesPlausibilidad.desde_mapa(bruto["plausibilidad"])
    assert u.fraccion_maxima_excursion > 0.0
    assert u.muestras_minimas >= math.ceil(1.0 / u.fraccion_maxima_excursion), (
        "muestras_minimas tiene que ser al menos 1/fraccion_maxima_excursion: "
        "por debajo, una sola muestra fuera ya supera el umbral de excursión"
    )
    assert u.factores_candidatos


def test_el_catalogo_real_de_unidades_identifica_la_unidad_de_afr(xp: XpVec) -> None:
    """La detección de AFR-en-vez-de-λ se apoya en la ESTRUCTURA de
    `data/units.toml` (una unidad de la dimensión de mezcla parametrizada por el
    rol `stoichiometry`), no en que la unidad se llame «afr».

    Esta prueba usa los tres catálogos reales, sin sustitutos, porque es la
    única forma de comprobar que el reconocimiento estructural funciona sobre el
    fichero que se va a usar de verdad.
    """
    with ROLES_TOML.open("rb") as fh:
        roles = cargar_catalogo_roles(fh)
    with UNITS_TOML.open("rb") as fh:
        unidades = cargar_catalogo(fh)
    with UMBRALES_TOML.open("rb") as fh:
        umbrales = UmbralesPlausibilidad.desde_mapa(tomllib.load(fh)["plausibilidad"])

    valores = Vec([14.0 + (i % 8) * 0.15 for i in range(120)])
    h = evaluar_canal(
        CanalJuzgable("Wideband O2 1", valores, _exacta("lambda_measured")),
        roles,
        umbrales=umbrales,
        catalogo_unidades=unidades,
        xp=xp,
    )
    assert h.diagnostico is Diagnostico.AFR_EN_VEZ_DE_LAMBDA
    assert h.unidad_probable == "afr"
    assert h.severidad == "critica"


def test_una_presion_relativa_se_reconoce_con_el_catalogo_real(xp: XpVec) -> None:
    """`docs/06` §6.6: la canónica de presión es ABSOLUTA, y «2 bar» sin más es
    la fuente de error más común al comparar logs de dos herramientas. Un MAP en
    manométrico tiene vacío negativo, que ninguna unidad ni ningún factor
    explican: solo la referencia de origen."""
    with ROLES_TOML.open("rb") as fh:
        roles = cargar_catalogo_roles(fh)
    with UNITS_TOML.open("rb") as fh:
        unidades = cargar_catalogo(fh)
    with UMBRALES_TOML.open("rb") as fh:
        umbrales = UmbralesPlausibilidad.desde_mapa(tomllib.load(fh)["plausibilidad"])

    valores = Vec([-70.0 + (i % 100) * 2.0 for i in range(200)])
    h = evaluar_canal(
        CanalJuzgable("Manifold Pressure", valores, _exacta("manifold_pressure")),
        roles,
        umbrales=umbrales,
        catalogo_unidades=unidades,
        xp=xp,
    )
    assert h.diagnostico is Diagnostico.PRESION_RELATIVA_SIN_REFERENCIA
    assert "relativa" in h.detalle
