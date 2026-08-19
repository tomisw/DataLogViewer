"""Topes de alerta: aviso, crítico, banda y curva (F3-10).

Especificación: `docs/04-perfiles-motorsport.md` §4.2 P8 y
`[detectores.D10.curva_minima]` de `data/umbrales.toml`.

QUÉ PROTEGE ESTA SUITE
======================
El módulo no compara nada con un umbral: construye la serie de umbral y delega en
`primitivas.umbral_con_histeresis` y `primitivas.banda`, que ya aceptan
`float | Serie`. Así que lo que hay que probar no es la comparación —ya tiene su
suite— sino las tres cosas que sí decide este módulo:

1. **Que la curva se evalúe bien**, incluida la interpolación entre puntos y,
   sobre todo, lo que pasa FUERA del rango declarado. Esa es la decisión con más
   consecuencia: extrapolando, la tabla de D10 pediría 1 101 kPa a 9 000 rpm, un
   número que nadie declaró, y convertiría una presión sana en una alerta crítica.
2. **Que una curva sirva de verdad para lo que existe**, o sea que el mismo canal
   dispare a un régimen y no a otro. Un tope plano no puede hacer eso, y es todo
   el motivo de P8. Se comprueba con el caso real de D10.
3. **Que las configuraciones sin síntoma fallen.** Dos puntos con la misma
   referencia dividen por cero y dejan un umbral infinito: el detector no
   dispararía nunca o dispararía siempre, sin error por el camino. Y un aviso
   colocado por detrás del crítico deja de ser un aviso sin que nada falle.

Se reutilizan `Vec` y `XpVec` de `test_primitivas`: los bucles viven en la prueba,
que es donde ADR-009 los permite.
"""

from __future__ import annotations

import bisect
import tomllib
from pathlib import Path
from typing import Any

import pytest

from dlv_core.primitivas import Direccion, Permanencia, Serie, eventos
from dlv_core.topes import (
    CurvaLineal,
    CurvaPorPuntos,
    ErrorDeTope,
    NivelDeTope,
    Tope,
    TopeDeBanda,
    aplicar_banda,
    aplicar_tope,
    evaluar_curva,
    validar_pareja,
)
from dlv_core.unidades import Clase

RAIZ = Path(__file__).resolve().parents[2]
UMBRALES = RAIZ / "data" / "umbrales.toml"


class Vec(list[Any]):
    """Vector con la aritmética elemento a elemento que necesita el motor.

    Los bucles están AQUÍ, en la prueba, que es donde ADR-009 los permite: lo
    que prohíbe es que estén en `dlv-core`. Con NumPy cada uno de estos métodos
    es una pasada en C sobre el array completo.

    Distingue el indexado por MÁSCARA booleana del indexado por posiciones
    mirando el tipo del primer elemento de la clave, igual que `Vec` en
    `test_malla.py`: `bool` es un tipo distinto de `int` aunque sea su subclase,
    así que un índice 0/1 de verdad nunca se confunde con una máscara.
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

    def __setitem__(self, clave: Any, valor: Any) -> None:
        if isinstance(clave, (Vec, list, tuple)):
            claves = list(clave)
            if claves and isinstance(claves[0], bool):
                # Asignación por máscara: el lado derecho puede ser un escalar o
                # un vector COMPACTADO con tantos elementos como posiciones
                # marcadas, que es como se comporta NumPy.
                if isinstance(valor, list):
                    it = iter(valor)
                    for i, m in enumerate(claves):
                        if m:
                            list.__setitem__(self, i, next(it))
                    return
                for i, m in enumerate(claves):
                    if m:
                        list.__setitem__(self, i, valor)
                return
        list.__setitem__(self, clave, valor)

    def _op(self, otro: Any, f: Any) -> Vec:
        if isinstance(otro, list):
            return Vec(f(a, b) for a, b in zip(self, otro, strict=True))
        return Vec(f(a, otro) for a in self)

    def __add__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a + b)

    def __radd__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: b + a)

    def __sub__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a - b)

    def __rsub__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: b - a)

    def __mul__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a * b)

    __rmul__ = __mul__

    def __truediv__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a / b)

    def __neg__(self) -> Vec:
        return Vec(-a for a in self)

    def __lt__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a < b)

    def __le__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a <= b)

    def __gt__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a > b)

    def __ge__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a >= b)

    def __eq__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a == b)

    def __ne__(self, otro: Any) -> Any:  # type: ignore[override]
        return self._op(otro, lambda a, b: a != b)

    # `&` y `|` son BIT A BIT, no lógicos, porque es lo que hace NumPy. Sobre
    # booleanos las dos cosas coinciden y por eso el error tardó en verse; sobre
    # enteros no: `fuera_de_mascara` pide `bits & mascara` sobre una máscara de
    # bits de verdad, y un `bool(a) and bool(b)` convierte «¿está puesto el bit
    # 1?» en «¿hay algún bit puesto?» — un detector que dispara con la causa
    # equivocada. Python ya hace lo correcto en los dos casos: `bool & bool` da
    # `bool` e `int & int` da `int`, igual que NumPy.
    #
    # Es la clase de divergencia que invalida el patrón entero: el doble está
    # aquí para ejercitar el MISMO código que producción, y si no se comporta
    # como NumPy, las pruebas validan otra cosa.
    def __and__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a & b)

    def __or__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a | b)

    def __hash__(self) -> int:  # type: ignore[override]
        raise TypeError("un Vec no es hashable, igual que un ndarray")

    def __bool__(self) -> bool:
        # Igual que NumPy: el valor de verdad de un vector de longitud != 1 es
        # ambiguo. Sin esto, un `assert` sobre un Vec no comprobaría nada.
        if len(self) == 1:
            return bool(list.__getitem__(self, 0))
        raise ValueError("el valor de verdad de un Vec de longitud != 1 es ambiguo")


class XpVec:
    """Las nueve funciones del protocolo `Vectorial`, con los nombres de NumPy.

    Cuenta las llamadas para que las pruebas de ADR-009 puedan comprobar que el
    coste NO crece con el número de muestras: lo que importa no es que no haya
    bucles, es que el número de operaciones de array sea independiente del
    tamaño de la serie.
    """

    def __init__(self) -> None:
        self.llamadas: dict[str, int] = {}

    def _cuenta(self, nombre: str) -> None:
        self.llamadas[nombre] = self.llamadas.get(nombre, 0) + 1

    @property
    def total(self) -> int:
        return sum(self.llamadas.values())

    def searchsorted(self, a: Any, v: Any, side: str) -> Any:
        self._cuenta("searchsorted")
        hallar = bisect.bisect_right if side == "right" else bisect.bisect_left
        lista = list(a)
        return Vec(hallar(lista, x) for x in v)

    def abs(self, a: Any) -> Any:
        self._cuenta("abs")
        if isinstance(a, list):
            return Vec(abs(x) for x in a)
        return abs(a)

    def cumsum(self, a: Any) -> Any:
        self._cuenta("cumsum")
        total = 0
        salida: Vec = Vec()
        for x in a:
            total += int(x)
            salida.append(total)
        return salida

    def arange(self, n: int) -> Any:
        self._cuenta("arange")
        return Vec(range(n))

    def sum(self, a: Any) -> Any:
        self._cuenta("sum")
        return sum(int(x) for x in a)

    def min(self, a: Any) -> Any:
        self._cuenta("min")
        return min(a)

    def max(self, a: Any) -> Any:
        self._cuenta("max")
        return max(a)

    def maximum(self, a: Any, b: Any) -> Any:
        self._cuenta("maximum")
        return Vec(max(x, y) for x, y in zip(a, b, strict=True))

    def minimum(self, a: Any, b: Any) -> Any:
        self._cuenta("minimum")
        return Vec(min(x, y) for x, y in zip(a, b, strict=True))


@pytest.fixture
def xp() -> XpVec:
    return XpVec()


def _serie(valores: list[float], *, dt_ms: float = 100.0, clase: Clase = Clase.PUNTO) -> Serie:
    return Serie(
        t_ms=Vec([i * dt_ms for i in range(len(valores))]),
        v=Vec(valores),
        clase=clase,
    )


@pytest.fixture(scope="module")
def curva_real_d10() -> CurvaLineal:
    """La curva de D10 tal como está declarada en `data/umbrales.toml`.

    Se lee del fichero y no se copia aquí: si alguien cambia la pendiente, esta
    suite tiene que ejercitar la nueva, no la que había cuando se escribió.
    """
    with UMBRALES.open("rb") as fh:
        crudo = tomllib.load(fh)["detectores"]["D10"]["curva_minima"]
    assert crudo["tipo"] == "lineal_por_regimen"
    return CurvaLineal(
        rol_referencia="engine_speed",
        base=float(crudo["base_kpa"]),
        pendiente=float(crudo["pendiente_kpa_por_1000rpm"]),
        divisor_referencia=1000.0,
    )


# --------------------------------------------------------------------------- #
#  1. La curva
# --------------------------------------------------------------------------- #


def test_la_curva_lineal_de_d10_da_los_valores_declarados(
    curva_real_d10: CurvaLineal, xp: XpVec
) -> None:
    """1 bar de margen sobre la atmosférica, más 1 bar por cada 1 000 rpm."""
    rpm = _serie([0.0, 1000.0, 3000.0, 7000.0])
    umbral = evaluar_curva(curva_real_d10, rpm, xp=xp)

    assert umbral.clase is Clase.PUNTO, "un tope es un valor absoluto, no una diferencia"
    assert list(umbral.t_ms) == list(rpm.t_ms), "el umbral tiene que ir en la rejilla del canal"
    assert umbral.v[0] == pytest.approx(201.3)
    assert umbral.v[1] == pytest.approx(301.3)
    assert umbral.v[2] == pytest.approx(501.3)
    assert umbral.v[3] == pytest.approx(901.3)


def test_la_curva_por_puntos_interpola_entre_los_declarados(xp: XpVec) -> None:
    curva = CurvaPorPuntos(
        rol_referencia="engine_speed",
        puntos=((0.0, 201.3), (3000.0, 501.3), (7000.0, 901.3)),
    )
    rpm = _serie([0.0, 1500.0, 3000.0, 5000.0, 7000.0])
    umbral = evaluar_curva(curva, rpm, xp=xp)

    assert umbral.v[0] == pytest.approx(201.3)
    assert umbral.v[1] == pytest.approx(351.3)  # mitad del primer tramo
    assert umbral.v[2] == pytest.approx(501.3)  # el punto declarado
    assert umbral.v[3] == pytest.approx(701.3)  # mitad del segundo tramo
    assert umbral.v[4] == pytest.approx(901.3)


def test_fuera_del_rango_la_tabla_se_recorta_y_no_extrapola(xp: XpVec) -> None:
    """LA DECISIÓN CON MÁS CONSECUENCIA DEL MÓDULO.

    A 9 000 rpm, extrapolando el último tramo saldrían 1 101,3 kPa: un mínimo que
    nadie ha declarado y que en un motor que pasa de vueltas convierte una presión
    sana en una alerta crítica. Y por debajo del primer punto, extrapolar hacia
    abajo bajaría el mínimo y silenciaría una alerta de verdad. Los dos lados se
    recortan al punto extremo declarado.
    """
    curva = CurvaPorPuntos(
        rol_referencia="engine_speed",
        puntos=((0.0, 201.3), (3000.0, 501.3), (7000.0, 901.3)),
    )
    rpm = _serie([-500.0, 9000.0, 20000.0])
    umbral = evaluar_curva(curva, rpm, xp=xp)

    assert umbral.v[0] == pytest.approx(201.3), "por debajo del primer punto se recorta"
    assert umbral.v[1] == pytest.approx(901.3), "por encima del último se recorta"
    assert umbral.v[2] == pytest.approx(901.3)
    # Y explícitamente: NO es la extrapolación.
    assert umbral.v[1] != pytest.approx(1101.3)


def test_una_curva_de_dos_puntos_funciona(xp: XpVec) -> None:
    """El caso límite del bucle de tramos: un solo tramo, recortado por los dos lados."""
    curva = CurvaPorPuntos(rol_referencia="engine_speed", puntos=((1000.0, 100.0), (2000.0, 200.0)))
    umbral = evaluar_curva(curva, _serie([500.0, 1000.0, 1500.0, 2000.0, 2500.0]), xp=xp)
    assert [round(float(v), 6) for v in umbral.v] == [100.0, 100.0, 150.0, 200.0, 200.0]


def test_una_referencia_que_no_es_punto_se_rechaza(curva_real_d10: CurvaLineal, xp: XpVec) -> None:
    """El régimen al que se evalúa el tope es un valor, no un delta ni una tasa.

    Evaluar la curva sobre una DERIVADA del régimen daría un umbral calculado con
    «cuánto sube el régimen» en vez de «a qué régimen va», y el número saldría
    plausible: a 500 rpm/s de subida pediría 251 kPa, que parece un umbral.
    """
    derivada_de_rpm = _serie([0.0, 500.0], clase=Clase.TASA)
    with pytest.raises(ErrorDeTope, match="PUNTO"):
        evaluar_curva(curva_real_d10, derivada_de_rpm, xp=xp)


# --------------------------------------------------------------------------- #
#  2. Que la curva sirva para lo que existe
# --------------------------------------------------------------------------- #


def test_el_mismo_canal_dispara_a_alto_regimen_y_no_a_ralenti(
    curva_real_d10: CurvaLineal, xp: XpVec
) -> None:
    """P8 entera, en una prueba. Es lo que un tope plano no puede hacer.

    400 kPa absolutos de presión de aceite están BIEN a 800 rpm —el mínimo de la
    curva ahí son 281,3— y son una alerta crítica a 6 000 rpm, donde el mínimo son
    801,3. El mismo número, la misma serie, y el veredicto contrario según el
    régimen. Con un umbral plano hay que elegir entre el falso positivo a ralentí y
    el falso negativo a alto régimen, y el de alto régimen es el que rompe el motor.

    Los dos valores salen de la curva declarada en `data/umbrales.toml`:
    201,3 + 100 x (rpm/1000). La primera versión de esta prueba usaba 250 kPa
    creyendo que eran normales a ralentí, y no lo son con esta curva: 250 < 281,3,
    así que el detector saltaba con razón. El error estaba en la prueba.
    """
    presion = _serie([400.0] * 8)
    rpm = _serie([800.0] * 4 + [6000.0] * 4)

    condicion = aplicar_tope(
        presion,
        Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=curva_real_d10),
        referencia=rpm,
        histeresis=0.0,
        xp=xp,
    )
    activa = [bool(a) for a in condicion.activa]
    assert activa[:4] == [False] * 4, "a 800 rpm el mínimo son 281,3 kPa y hay 400"
    assert activa[4:] == [True] * 4, "a 6 000 rpm el mínimo son 801,3 kPa: 400 es crítico"


def test_a_ralenti_de_verdad_no_dispara(curva_real_d10: CurvaLineal, xp: XpVec) -> None:
    """La otra mitad: una presión sana a ralentí tiene que quedarse callada."""
    presion = _serie([320.0] * 4)
    rpm = _serie([800.0] * 4)
    condicion = aplicar_tope(
        presion,
        Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=curva_real_d10),
        referencia=rpm,
        histeresis=0.0,
        xp=xp,
    )
    assert not any(bool(a) for a in condicion.activa)


def test_un_tope_plano_sigue_funcionando(xp: XpVec) -> None:
    """No todo tope es una curva: D9 y D11 son números, y no hay que envolverlos."""
    temperatura = _serie([370.0, 380.0, 385.0, 372.0])
    condicion = aplicar_tope(
        temperatura,
        Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ARRIBA, valor=378.15),
        histeresis=0.0,
        xp=xp,
    )
    assert [bool(a) for a in condicion.activa] == [False, True, True, False]


def test_una_curva_sin_referencia_falla_en_vez_de_suponer_un_regimen(
    curva_real_d10: CurvaLineal, xp: XpVec
) -> None:
    """Suponer un régimen fijo convertiría la curva en el umbral plano que
    la curva existe para no ser, y encima sin decirlo."""
    with pytest.raises(ErrorDeTope, match="referencia"):
        aplicar_tope(
            _serie([250.0]),
            Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=curva_real_d10),
            histeresis=0.0,
            xp=xp,
        )


def test_la_histeresis_de_una_curva_se_aplica_muestra_a_muestra(
    curva_real_d10: CurvaLineal, xp: XpVec
) -> None:
    """Con dirección ABAJO el umbral de salida está POR ENCIMA del de entrada.

    Y siendo el umbral una serie, el margen tiene que seguir a la serie: un margen
    calculado sobre un solo valor del umbral sería una histéresis correcta a un
    régimen y demasiado grande o pequeña en el resto.
    """
    # Entra por debajo de 301,3 (1 000 rpm) y no sale hasta rebasar 301,3 x 1,1.
    presion = _serie([320.0, 290.0, 305.0, 340.0])
    rpm = _serie([1000.0] * 4)
    condicion = aplicar_tope(
        presion,
        Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=curva_real_d10),
        referencia=rpm,
        histeresis=0.10,
        xp=xp,
    )
    activa = [bool(a) for a in condicion.activa]
    assert activa[0] is False
    assert activa[1] is True, "290 < 301,3: entra"
    assert activa[2] is True, "305 pasa el umbral pero no el de salida (331,4): sigue dentro"
    assert activa[3] is False, "340 > 331,4: sale"


def test_los_eventos_de_un_tope_de_curva_se_pueden_contar(
    curva_real_d10: CurvaLineal, xp: XpVec
) -> None:
    """La condición que sale de aquí es una `Condicion` normal: `eventos` la consume.

    Es la comprobación de que el módulo compone con el resto del motor en vez de
    ser un camino paralelo.
    """
    presion = _serie([900.0, 250.0, 250.0, 900.0, 250.0, 900.0])
    rpm = _serie([6000.0] * 6)
    # Permanencia mínima: un evento de una muestra cuenta. Aquí lo que se
    # comprueba es que `eventos` consuma esta condición como cualquier otra, no
    # el filtrado por duración, que tiene su propia suite.
    permanencia = Permanencia(permanencia_s=0.0, muestras_minimas=1, maximo_de_eventos=100)
    condicion = aplicar_tope(
        presion,
        Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=curva_real_d10),
        referencia=rpm,
        histeresis=0.0,
        xp=xp,
    )
    encontrados = eventos(condicion, permanencia=permanencia, xp=xp)
    assert len(encontrados) == 2
    assert encontrados[0].n_muestras == 2
    assert encontrados[1].n_muestras == 1


# --------------------------------------------------------------------------- #
#  3. La banda
# --------------------------------------------------------------------------- #


def test_una_banda_con_los_dos_bordes_en_curva(xp: XpVec) -> None:
    """El caso de la mezcla: la banda sigue al objetivo de λ, no son dos números."""
    objetivo = _serie([1.0, 1.0, 0.85, 0.85])
    lambda_medida = _serie([0.98, 1.20, 0.84, 0.70])
    tope = TopeDeBanda(
        nivel=NivelDeTope.AVISO,
        minimo=CurvaPorPuntos(rol_referencia="lambda_target", puntos=((0.7, 0.651), (1.1, 1.023))),
        maximo=CurvaPorPuntos(rol_referencia="lambda_target", puntos=((0.7, 0.728), (1.1, 1.144))),
    )
    dentro = aplicar_banda(lambda_medida, tope, referencia=objetivo, histeresis_relativa=0.0, xp=xp)
    activa = [bool(a) for a in dentro.activa]
    assert activa == [True, False, True, False]


def test_una_banda_de_numeros_no_necesita_referencia(xp: XpVec) -> None:
    tope = TopeDeBanda(nivel=NivelDeTope.AVISO, minimo=0.9, maximo=1.1)
    dentro = aplicar_banda(_serie([0.8, 1.0, 1.2]), tope, histeresis_relativa=0.0, xp=xp)
    assert [bool(a) for a in dentro.activa] == [False, True, False]


def test_una_banda_con_borde_de_curva_y_sin_referencia_falla(xp: XpVec) -> None:
    tope = TopeDeBanda(
        nivel=NivelDeTope.AVISO,
        minimo=CurvaPorPuntos(rol_referencia="x", puntos=((0.0, 1.0), (1.0, 2.0))),
        maximo=1.1,
    )
    with pytest.raises(ErrorDeTope, match="referencia"):
        aplicar_banda(_serie([1.0]), tope, histeresis_relativa=0.0, xp=xp)


# --------------------------------------------------------------------------- #
#  4. Las configuraciones que no tienen síntoma
# --------------------------------------------------------------------------- #


def test_dos_puntos_con_la_misma_referencia_se_rechazan() -> None:
    """Dividirían por cero y dejarían un umbral infinito, sin fallar.

    El detector no dispararía nunca o dispararía siempre según el signo, y no
    habría ningún error que mirar.
    """
    with pytest.raises(ErrorDeTope, match="estrictamente creciente"):
        CurvaPorPuntos(rol_referencia="engine_speed", puntos=((1000.0, 100.0), (1000.0, 200.0)))


def test_los_puntos_desordenados_se_rechazan() -> None:
    with pytest.raises(ErrorDeTope, match="estrictamente creciente"):
        CurvaPorPuntos(
            rol_referencia="engine_speed",
            puntos=((3000.0, 501.3), (0.0, 201.3)),
        )


def test_una_curva_de_un_solo_punto_se_rechaza() -> None:
    with pytest.raises(ErrorDeTope, match="al menos 2 puntos"):
        CurvaPorPuntos(rol_referencia="engine_speed", puntos=((1000.0, 100.0),))


def test_un_aviso_por_detras_del_critico_se_rechaza() -> None:
    """El error de configuración que deja el nivel de aviso sin existir.

    Con el aviso de sobretemperatura a 120 °C y el crítico a 110 °C, el crítico
    salta primero y el aviso nunca es un aviso. Nada falla, y quien lo configuró
    cree que lo tiene.
    """
    aviso = Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ARRIBA, valor=393.15)
    critico = Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ARRIBA, valor=383.15)
    with pytest.raises(ErrorDeTope, match="nunca avisa"):
        validar_pareja(aviso, critico)


def test_el_mismo_error_al_reves_para_direccion_abajo() -> None:
    """Con ABAJO el aviso tiene que ser el valor MÁS ALTO de los dos."""
    aviso = Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ABAJO, valor=200.0)
    critico = Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=250.0)
    with pytest.raises(ErrorDeTope, match="nunca avisa"):
        validar_pareja(aviso, critico)


def test_una_pareja_bien_ordenada_pasa() -> None:
    validar_pareja(
        Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ABAJO, valor=300.0),
        Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=250.0),
    )


def test_dos_direcciones_distintas_no_son_dos_niveles() -> None:
    with pytest.raises(ErrorDeTope, match="dos alertas distintas"):
        validar_pareja(
            Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ARRIBA, valor=10.0),
            Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=5.0),
        )


def test_con_una_curva_la_pareja_no_se_comprueba_en_vez_de_darse_por_buena(
    curva_real_d10: CurvaLineal,
) -> None:
    """Dos curvas pueden cruzarse en algún punto de su rango, así que compararlas
    no es comparar dos números. Se dice que no se ha comprobado."""
    validar_pareja(
        Tope(nivel=NivelDeTope.AVISO, direccion=Direccion.ABAJO, valor=curva_real_d10),
        Tope(nivel=NivelDeTope.CRITICO, direccion=Direccion.ABAJO, valor=100.0),
    )


def test_un_divisor_de_referencia_nulo_se_rechaza() -> None:
    with pytest.raises(ErrorDeTope, match="divisor_referencia"):
        CurvaLineal(rol_referencia="x", base=1.0, pendiente=1.0, divisor_referencia=0.0)


# --------------------------------------------------------------------------- #
#  5. ADR-009
# --------------------------------------------------------------------------- #


def test_el_coste_de_evaluar_una_curva_no_crece_con_las_muestras(xp: XpVec) -> None:
    """Lo que ADR-009 pide de verdad: el número de operaciones de array no
    depende del número de muestras, solo de los tramos de la curva."""
    curva = CurvaPorPuntos(
        rol_referencia="engine_speed",
        puntos=((0.0, 201.3), (3000.0, 501.3), (7000.0, 901.3)),
    )
    xp_corto = XpVec()
    evaluar_curva(curva, _serie([1000.0] * 10), xp=xp_corto)
    llamadas_cortas = dict(xp_corto.llamadas)

    xp_largo = XpVec()
    evaluar_curva(curva, _serie([1000.0] * 10000), xp=xp_largo)
    assert dict(xp_largo.llamadas) == llamadas_cortas, (
        "el número de operaciones de array cambia con el tamaño de la serie: "
        "hay un bucle por muestra escondido"
    )
