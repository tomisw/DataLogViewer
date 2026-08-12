"""Pruebas del motor de detectores (F3-06, `docs/04` §4.3, «Primitivas»).

QUÉ PROTEGE ESTA SUITE, ORDENADO POR CONSECUENCIA SI SE ROMPE
=============================================================
1. **La histéresis hace su trabajo.** Es la razón de ser del módulo: una señal
   que cruza el umbral arriba y abajo repetidamente tiene que dar UN evento, no
   cien. Hay una prueba por primitiva con umbral (`umbral_con_histeresis`,
   `banda`) y una que compara el mismo ruido con y sin histéresis para que la
   diferencia sea un número y no una impresión.
2. **La permanencia mínima descarta lo breve y conserva lo largo**, con las dos
   condiciones (tiempo y muestras) y sobre canales de tasas distintas, que es
   donde «3 muestras o 100 ms, el mayor de los dos» se vuelve ambiguo.
3. **Un hueco no se puentea ni se inventa.** Multi-tasa por retención con
   límite de validez, huecos que interrumpen carreras, y lógica de tres valores
   en la composición: `A o B` con `A` cierta no se apaga porque `B` falte.
4. **La clase de conversión viaja y cambia** (regla 4): la derivada es TASA, el
   delta es INTERVALO, y comparar clases distintas es un error, no una
   comparación.
5. **Ni un umbral cableado** (regla 3): dos guardas, una sobre las firmas y otra
   sobre los literales del módulo, más la comprobación de que el fichero real
   carga y es coherente.
6. **Ni un bucle por muestra** (ADR-009), comprobado por conducta —contando
   cuántas veces se llama a cada función del protocolo— y no solo por el patrón
   que vigila `tools/banco.py adr009`.

Como en `test_reloj.py`, `test_malla.py` y `test_expresiones.py`, todo se
ejercita con `XpVec`, una implementación del protocolo `Vectorial` hecha con
biblioteca estándar. No es un simulacro: ejecuta el MISMO código que correrá con
NumPy. Y hay una advertencia pagada en este proyecto: esa implementación ya
escondió una vez una diferencia con NumPy (un canal con huecos daba distinto con
`numpy.min` que con el `min` de la biblioteca estándar), así que la pasada con
NumPy de verdad no es una formalidad.
"""

from __future__ import annotations

import ast
import bisect
import inspect
import math
import tomllib
from pathlib import Path
from typing import Any

import pytest

from dlv_core.primitivas import (
    Condicion,
    Direccion,
    ErrorDePrimitiva,
    Evento,
    Extremo,
    Permanencia,
    Pico,
    Serie,
    SerieDeBits,
    alinear,
    banda,
    conteo_de_cruces,
    delta_de_contador,
    derivada,
    eventos,
    extremo_en_ventana,
    fuera_de_mascara,
    pico_local,
    tiempo_acumulado,
    umbral_con_histeresis,
)
from dlv_core.unidades import Clase

RAIZ = Path(__file__).resolve().parent.parent.parent
UMBRALES_TOML = RAIZ / "data" / "umbrales.toml"
MODULO = RAIZ / "dlv-core" / "src" / "dlv_core" / "primitivas.py"


# --------------------------------------------------------------------------- #
# El protocolo `Vectorial` con biblioteca estándar
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Utilidades de las pruebas
# --------------------------------------------------------------------------- #
def _t(n: int, dt_ms: float = 50.0, t0: float = 0.0) -> Vec:
    """Marcas de tiempo regulares. Las irregulares se escriben a mano cuando la
    prueba va justamente de eso."""
    return Vec([t0 + i * dt_ms for i in range(n)])


def _serie(valores: list[float], *, dt_ms: float = 50.0, clase: Clase = Clase.PUNTO) -> Serie:
    return Serie(t_ms=_t(len(valores), dt_ms), v=Vec(valores), clase=clase)


def _permanencia(
    *, permanencia_s: float = 0.0, muestras_minimas: int = 1, maximo_de_eventos: int = 10_000
) -> Permanencia:
    """Permanencia para las pruebas.

    Los valores por omisión están AQUÍ, en la prueba, no en el módulo: la
    permanencia neutra (0 s y 1 muestra) es la que deja ver lo que hace cada
    primitiva sin que el filtro se lleve por delante los eventos cortos que la
    prueba está comprobando.
    """
    return Permanencia(
        permanencia_s=permanencia_s,
        muestras_minimas=muestras_minimas,
        maximo_de_eventos=maximo_de_eventos,
    )


def _condicion(activa: list[bool], *, valido: list[bool] | None = None) -> Condicion:
    n = len(activa)
    return Condicion(
        t_ms=_t(n),
        activa=Vec(activa),
        valido=Vec([True] * n if valido is None else valido),
    )


# --------------------------------------------------------------------------- #
# 1. Umbral con histéresis: dispara, no dispara, y el borde que existe para
#    resolver
# --------------------------------------------------------------------------- #
def test_el_umbral_dispara_cuando_debe(xp: XpVec) -> None:
    serie = _serie([300.0, 300.0, 380.0, 380.0, 380.0, 300.0])
    cond = umbral_con_histeresis(
        serie, entrada=378.15, salida=376.0, direccion=Direccion.ARRIBA, xp=xp
    )
    assert list(cond.activa) == [False, False, True, True, True, False]
    assert len(eventos(cond, permanencia=_permanencia(), xp=xp)) == 1


def test_el_umbral_no_dispara_cuando_no_debe(xp: XpVec) -> None:
    serie = _serie([300.0, 350.0, 370.0, 377.0, 360.0])
    cond = umbral_con_histeresis(
        serie, entrada=378.15, salida=376.0, direccion=Direccion.ARRIBA, xp=xp
    )
    assert not any(cond.activa)
    assert eventos(cond, permanencia=_permanencia(), xp=xp) == []


def test_una_senal_que_oscila_en_el_umbral_da_un_evento_y_no_cien(xp: XpVec) -> None:
    """EL CASO DE BORDE QUE JUSTIFICA LA HISTÉRESIS.

    Un canal ruidoso que roza el umbral: 40 muestras alternando 378,0 y 378,3
    alrededor de una entrada de 378,15. Sin histéresis son veinte eventos —«un
    umbral desnudo genera cientos de falsas alertas y el usuario apaga la
    función», §4.3—; con una banda de histéresis de 2 K, uno solo.

    La comparación entre las dos configuraciones está en la misma prueba a
    propósito: el número que importa no es «1», es la diferencia entre 20 y 1.
    """
    valores = [378.0 if i % 2 == 0 else 378.3 for i in range(40)]
    serie = _serie(valores)

    desnudo = umbral_con_histeresis(
        serie, entrada=378.15, salida=378.15, direccion=Direccion.ARRIBA, xp=xp
    )
    con_histeresis = umbral_con_histeresis(
        serie, entrada=378.15, salida=376.15, direccion=Direccion.ARRIBA, xp=xp
    )

    assert len(eventos(desnudo, permanencia=_permanencia(), xp=xp)) == 20
    assert len(eventos(con_histeresis, permanencia=_permanencia(), xp=xp)) == 1


def test_la_histeresis_mantiene_la_condicion_en_la_zona_intermedia(xp: XpVec) -> None:
    """Lo que hace la zona de histéresis, muestra a muestra: entre `salida` y
    `entrada` el estado se mantiene, y depende de por dónde se entró."""
    serie = _serie([370.0, 380.0, 377.0, 377.0, 374.0, 377.0])
    cond = umbral_con_histeresis(
        serie, entrada=378.0, salida=375.0, direccion=Direccion.ARRIBA, xp=xp
    )
    # 377 mantiene el estado (está en la zona), 374 cierra, y el 377 final ya no
    # reabre porque no ha vuelto a alcanzar 378.
    assert list(cond.activa) == [False, True, True, True, False, False]


def test_el_umbral_hacia_abajo_es_simetrico(xp: XpVec) -> None:
    """D10 (presión de aceite baja) y D11 (tensión baja) miran hacia abajo."""
    serie = _serie([13.5, 13.5, 11.0, 11.3, 11.8, 12.5])
    cond = umbral_con_histeresis(serie, entrada=11.5, salida=11.9, direccion=Direccion.ABAJO, xp=xp)
    assert list(cond.activa) == [False, False, True, True, True, False]


def test_el_estado_inicial_es_fuera_aunque_el_log_empiece_por_encima(xp: XpVec) -> None:
    """Un log que arranca con el motor ya caliente no abre un evento en la
    muestra 0 sin haber visto ningún cruce... pero sí en la muestra 0 si la
    propia muestra 0 alcanza el umbral: eso ES un cruce observado."""
    frio = _serie([300.0, 300.0])
    cond_frio = umbral_con_histeresis(
        frio, entrada=378.0, salida=376.0, direccion=Direccion.ARRIBA, xp=xp
    )
    assert not any(cond_frio.activa)

    caliente = _serie([380.0, 380.0])
    cond_caliente = umbral_con_histeresis(
        caliente, entrada=378.0, salida=376.0, direccion=Direccion.ARRIBA, xp=xp
    )
    assert list(cond_caliente.activa) == [True, True]


def test_una_histeresis_al_reves_es_un_error_no_un_evento_infinito(xp: XpVec) -> None:
    serie = _serie([300.0, 380.0, 300.0])
    with pytest.raises(ErrorDePrimitiva, match="al revés"):
        umbral_con_histeresis(serie, entrada=378.0, salida=380.0, direccion=Direccion.ARRIBA, xp=xp)
    with pytest.raises(ErrorDePrimitiva, match="al revés"):
        umbral_con_histeresis(serie, entrada=11.5, salida=11.0, direccion=Direccion.ABAJO, xp=xp)


def test_el_umbral_puede_ser_otro_canal(xp: XpVec) -> None:
    """D2: el nivel de knock contra el umbral de la propia ECU, que sube con la
    carga. «Comparar contra un valor fijo daría falsos positivos a alta carga.»"""
    nivel = _serie([10.0, 30.0, 30.0, 30.0])
    umbral_ecu = _serie([20.0, 20.0, 40.0, 20.0])
    cond = umbral_con_histeresis(
        nivel, entrada=umbral_ecu, salida=umbral_ecu, direccion=Direccion.ARRIBA, xp=xp
    )
    # La tercera muestra tiene el mismo nivel que la segunda y no dispara,
    # porque el umbral de la ECU subió: eso es lo que un umbral fijo no vería.
    assert list(cond.activa) == [False, True, False, True]


def test_un_umbral_de_otra_clase_de_conversion_es_un_error(xp: XpVec) -> None:
    """Regla 4: «la temperatura ha subido más de 10 K» y «la temperatura pasa de
    10 K» se escriben con el mismo número y no son lo mismo."""
    canal = _serie([300.0, 380.0])
    umbral_intervalo = _serie([10.0, 10.0], clase=Clase.INTERVALO)
    with pytest.raises(ErrorDePrimitiva, match="trampa del delta"):
        umbral_con_histeresis(
            canal,
            entrada=umbral_intervalo,
            salida=umbral_intervalo,
            direccion=Direccion.ARRIBA,
            xp=xp,
        )


def test_dos_series_de_rejillas_distintas_no_se_comparan(xp: XpVec) -> None:
    canal = Serie(t_ms=Vec([0.0, 50.0, 100.0]), v=Vec([1.0, 2.0, 3.0]), clase=Clase.PUNTO)
    otro_grupo = Serie(t_ms=Vec([0.0, 200.0, 400.0]), v=Vec([1.0, 1.0, 1.0]), clase=Clase.PUNTO)
    with pytest.raises(ErrorDePrimitiva, match="instantes"):
        umbral_con_histeresis(
            canal, entrada=otro_grupo, salida=otro_grupo, direccion=Direccion.ARRIBA, xp=xp
        )
    corto = Serie(t_ms=Vec([0.0, 50.0]), v=Vec([1.0, 1.0]), clase=Clase.PUNTO)
    with pytest.raises(ErrorDePrimitiva, match="rejillas distintas"):
        umbral_con_histeresis(canal, entrada=corto, salida=corto, direccion=Direccion.ARRIBA, xp=xp)


# --------------------------------------------------------------------------- #
# 2. Permanencia mínima
# --------------------------------------------------------------------------- #
def test_la_permanencia_descarta_lo_breve_y_conserva_lo_largo(xp: XpVec) -> None:
    # dt = 50 ms: la ráfaga de 2 muestras dura 50 ms, la de 5 dura 200 ms.
    cond = _condicion([False, True, True, False, True, True, True, True, True, False])
    permanencia = _permanencia(permanencia_s=0.1, muestras_minimas=3)
    resultado = eventos(cond, permanencia=permanencia, xp=xp)
    assert len(resultado) == 1
    assert resultado[0].n_muestras == 5
    assert resultado[0].t_inicio_ms == pytest.approx(200.0)
    assert resultado[0].t_fin_ms == pytest.approx(400.0)
    assert resultado[0].duracion_s == pytest.approx(0.2)


def test_las_dos_condiciones_de_permanencia_se_exigen_a_la_vez(xp: XpVec) -> None:
    """«3 muestras o 100 ms, el mayor de los dos» (§4.3).

    Sobre un canal a 5 Hz (dt 200 ms), dos muestras ya son 200 ms y superan la
    permanencia en tiempo, pero no llegan a las 3 muestras. Sobre un canal a
    100 Hz, 3 muestras son 20 ms y no llegan a los 100 ms. Cada canal se queda
    corto por un lado distinto, y en los dos casos no hay evento: eso es lo que
    significa «el mayor de los dos».
    """
    permanencia = _permanencia(permanencia_s=0.1, muestras_minimas=3)

    lento = Condicion(
        t_ms=_t(4, dt_ms=200.0), activa=Vec([False, True, True, False]), valido=Vec([True] * 4)
    )
    assert eventos(lento, permanencia=permanencia, xp=xp) == []

    rapido = Condicion(
        t_ms=_t(5, dt_ms=10.0),
        activa=Vec([False, True, True, True, False]),
        valido=Vec([True] * 5),
    )
    assert eventos(rapido, permanencia=permanencia, xp=xp) == []


def test_una_sola_muestra_es_un_evento_si_la_configuracion_lo_dice(xp: XpVec) -> None:
    """D1 y D12: un solo evento de knock o un solo error de trigger importan, y
    su configuración declara `permanencia_s = 0`. Con `muestras_minimas = 1` el
    evento sale; con 3 no, y eso es un hallazgo sobre la configuración de D1,
    no sobre el motor."""
    cond = _condicion([False, True, False])
    assert len(eventos(cond, permanencia=_permanencia(), xp=xp)) == 1
    assert eventos(cond, permanencia=_permanencia(muestras_minimas=3), xp=xp) == []


def test_un_evento_que_llega_al_final_del_log_se_cierra_en_la_ultima_muestra(
    xp: XpVec,
) -> None:
    cond = _condicion([False, True, True, True])
    (evento,) = eventos(cond, permanencia=_permanencia(), xp=xp)
    assert evento.i_inicio == 1
    assert evento.i_fin == 3
    assert evento.t_fin_ms == pytest.approx(150.0)


def test_un_evento_que_empieza_en_la_muestra_cero_se_detecta(xp: XpVec) -> None:
    cond = _condicion([True, True, False, False])
    (evento,) = eventos(cond, permanencia=_permanencia(), xp=xp)
    assert evento.i_inicio == 0
    assert evento.n_muestras == 2


def test_una_condicion_siempre_activa_es_un_solo_evento(xp: XpVec) -> None:
    cond = _condicion([True] * 20)
    (evento,) = eventos(cond, permanencia=_permanencia(permanencia_s=0.1), xp=xp)
    assert evento.n_muestras == 20


def test_una_serie_vacia_no_revienta(xp: XpVec) -> None:
    cond = Condicion(t_ms=Vec([]), activa=Vec([]), valido=Vec([]))
    assert eventos(cond, permanencia=_permanencia(), xp=xp) == []
    assert conteo_de_cruces(cond, xp=xp) == 0


def test_el_valor_de_pico_sale_del_canal_que_se_lee(xp: XpVec) -> None:
    serie = _serie([1.0, 5.0, 9.0, 4.0, 1.0])
    cond = _condicion([False, True, True, True, False])
    (evento,) = eventos(
        cond,
        permanencia=_permanencia(),
        pico=Pico(serie=serie, extremo=Extremo.MAXIMO),
        xp=xp,
    )
    assert evento.valor_pico == pytest.approx(9.0)
    assert evento.clase_valor is Clase.PUNTO


def test_el_pico_de_un_evento_hacia_abajo_es_el_minimo(xp: XpVec) -> None:
    """La presión de aceite baja: su momento más grave es el MÍNIMO, y suponer
    el máximo daría el instante menos malo del evento."""
    presion = _serie([250.0, 180.0, 120.0, 190.0])
    cond = _condicion([False, True, True, False])
    (evento,) = eventos(
        cond,
        permanencia=_permanencia(),
        pico=Pico(serie=presion, extremo=Extremo.MINIMO),
        xp=xp,
    )
    assert evento.valor_pico == pytest.approx(120.0)


def test_sin_pico_no_se_inventa_un_valor(xp: XpVec) -> None:
    (evento,) = eventos(_condicion([True, True]), permanencia=_permanencia(), xp=xp)
    assert evento.valor_pico is None
    assert evento.clase_valor is None


def test_el_pico_lleva_la_clase_de_la_serie_de_la_que_sale(xp: XpVec) -> None:
    """Regla 4 hasta el final de la tubería: el pico de una derivada es una
    TASA, y quien lo pinte tiene que saberlo o lo convertirá como punto."""
    tps = _serie([0.1, 0.1, 0.9, 0.9])
    tasa = derivada(tps, ventana_s=0.05, xp=xp)
    cond = _condicion([False, False, True, False])
    (evento,) = eventos(
        cond, permanencia=_permanencia(), pico=Pico(serie=tasa, extremo=Extremo.MAXIMO), xp=xp
    )
    assert evento.clase_valor is Clase.TASA
    assert evento.valor_pico == pytest.approx(16.0)


def test_demasiados_eventos_es_un_error_explicado_no_una_lista_infinita(xp: XpVec) -> None:
    cond = _condicion([i % 2 == 0 for i in range(40)])
    with pytest.raises(ErrorDePrimitiva, match="histéresis"):
        eventos(cond, permanencia=_permanencia(maximo_de_eventos=5), xp=xp)


# --------------------------------------------------------------------------- #
# 3. Huecos: multi-tasa, retención y validez
# --------------------------------------------------------------------------- #
def test_un_hueco_interrumpe_la_carrera_y_no_se_puentea(xp: XpVec) -> None:
    """La consecuencia está documentada en la cabecera del módulo: un canal que
    deja de emitir en medio de un evento largo produce dos eventos cortos, no
    uno largo. Puentear el hueco sería afirmar que la condición se cumplía sin
    haberlo visto."""
    cond = _condicion(
        [True] * 9,
        valido=[True, True, True, True, False, True, True, True, True],
    )
    resultado = eventos(cond, permanencia=_permanencia(), xp=xp)
    assert [e.n_muestras for e in resultado] == [4, 4]


def test_el_multitasa_se_resuelve_por_retencion_con_limite_de_validez(xp: XpVec) -> None:
    """Un canal del grupo lento (5 Hz) llevado a la rejilla del rápido (20 Hz).

    Con la ventana de validez de `data/umbrales.toml` (250 ms) el valor
    retenido vale para las cuatro muestras rápidas siguientes. Si el canal lento
    deja de emitir, a partir de los 250 ms el resultado es HUECO y no una recta.
    """
    lento = Serie(t_ms=Vec([0.0, 200.0]), v=Vec([350.0, 360.0]), clase=Clase.PUNTO)
    destino = _t(12, dt_ms=50.0)  # 0..550 ms
    alineado = alinear(lento, destino, ventana_validez_ms=250.0, xp=xp)

    assert alineado.clase is Clase.PUNTO
    # Hasta 200 ms se retiene 350; desde 200 ms, 360; a partir de 450 ms
    # (200 + 250) el último valor conocido caduca.
    assert list(alineado.valido) == [True] * 10 + [False, False]
    # El índice 3 es 150 ms: todavía se retiene el valor de t=0.
    assert alineado.v[3] == pytest.approx(350.0)
    # El 4 es 200 ms EXACTOS, donde el canal lento emite: manda la muestra nueva,
    # no la retenida. La primera versión de esta prueba pedía aquí 350 y se
    # contradecía con su propio comentario («desde 200 ms, 360»).
    assert alineado.v[4] == pytest.approx(360.0)
    assert alineado.v[5] == pytest.approx(360.0)


def test_la_retencion_no_convierte_un_hueco_de_origen_en_dato(xp: XpVec) -> None:
    """Retener un valor que ya era un hueco no lo convierte en medida."""
    origen = Serie(
        t_ms=Vec([0.0, 100.0]),
        v=Vec([350.0, 999.0]),
        clase=Clase.PUNTO,
        valido=Vec([True, False]),
    )
    alineado = alinear(origen, _t(4, dt_ms=50.0), ventana_validez_ms=250.0, xp=xp)
    assert list(alineado.valido) == [True, True, False, False]


def test_antes_de_la_primera_muestra_del_canal_lento_no_hay_nada_que_retener(
    xp: XpVec,
) -> None:
    lento = Serie(t_ms=Vec([100.0]), v=Vec([350.0]), clase=Clase.PUNTO)
    alineado = alinear(lento, _t(4, dt_ms=50.0), ventana_validez_ms=250.0, xp=xp)
    assert list(alineado.valido) == [False, False, True, True]


def test_un_hueco_en_el_umbral_no_decide_nada(xp: XpVec) -> None:
    """Si el umbral (otro canal) falta en una muestra, la comparación no se
    puede hacer ahí, y no se hace con el último umbral conocido."""
    nivel = _serie([10.0, 50.0, 50.0])
    umbral_ecu = Serie(
        t_ms=_t(3), v=Vec([20.0, 20.0, 20.0]), clase=Clase.PUNTO, valido=Vec([True, False, True])
    )
    cond = umbral_con_histeresis(
        nivel, entrada=umbral_ecu, salida=umbral_ecu, direccion=Direccion.ARRIBA, xp=xp
    )
    assert list(cond.valido) == [True, False, True]
    assert eventos(cond, permanencia=_permanencia(), xp=xp)[0].i_inicio == 2


# --------------------------------------------------------------------------- #
# 4. Compuesto: lógica de tres valores
# --------------------------------------------------------------------------- #
def test_el_compuesto_and_exige_las_dos_condiciones(xp: XpVec) -> None:
    """D4: λ pobre Y mariposa > 70 % Y régimen > 3 000."""
    pobre = _condicion([True, True, False, True])
    en_carga = _condicion([False, True, True, True])
    compuesto = pobre.y(en_carga, xp=xp)
    assert list(compuesto.activa) == [False, True, False, True]


def test_el_and_es_falso_con_certeza_aunque_falte_el_otro_operando(xp: XpVec) -> None:
    """Kleene. Si el régimen es de 800 rpm, «λ pobre Y rpm > 3000» no se cumple,
    y no hace falta saber cuánto valía λ para afirmarlo. Con la validez estricta
    esta muestra saldría como «no se sabe» y una condición de contexto lenta
    apagaría el detector en casi todo el log."""
    lambda_desconocida = _condicion([True], valido=[False])
    regimen_bajo = _condicion([False], valido=[True])
    compuesto = lambda_desconocida.y(regimen_bajo, xp=xp)
    assert list(compuesto.valido) == [True]
    assert list(compuesto.activa) == [False]


def test_el_or_es_cierto_con_certeza_aunque_falte_el_otro_operando(xp: XpVec) -> None:
    cierto = _condicion([True], valido=[True])
    desconocido = _condicion([False], valido=[False])
    compuesto = cierto.o(desconocido, xp=xp)
    assert list(compuesto.valido) == [True]
    assert list(compuesto.activa) == [True]


def test_dos_huecos_siguen_siendo_un_hueco(xp: XpVec) -> None:
    a = _condicion([True], valido=[False])
    b = _condicion([True], valido=[False])
    assert list(a.y(b, xp=xp).valido) == [False]
    assert list(a.o(b, xp=xp).valido) == [False]


def test_la_negacion_no_convierte_un_hueco_en_certeza() -> None:
    cond = _condicion([True, False], valido=[True, False])
    negada = cond.no()
    assert list(negada.activa) == [False, True]
    assert list(negada.valido) == [True, False]


def test_dos_condiciones_de_rejillas_distintas_no_se_componen(xp: XpVec) -> None:
    a = Condicion(t_ms=Vec([0.0, 50.0]), activa=Vec([True, True]), valido=Vec([True, True]))
    b = Condicion(t_ms=Vec([0.0, 200.0]), activa=Vec([True, True]), valido=Vec([True, True]))
    with pytest.raises(ErrorDePrimitiva, match="instantes"):
        a.y(b, xp=xp)


# --------------------------------------------------------------------------- #
# 5. Banda
# --------------------------------------------------------------------------- #
def test_la_banda_marca_lo_que_esta_dentro_y_no_al_reves(xp: XpVec) -> None:
    """§4.3 define la banda como «λ dentro de ventana»; el detector que hace
    falta es el contrario y se escribe `.no()`."""
    lam = _serie([0.80, 0.95, 1.00, 1.20])
    dentro = banda(lam, minimo=0.90, maximo=1.05, histeresis_relativa=0.0, xp=xp)
    assert list(dentro.activa) == [False, True, True, False]
    assert list(dentro.no().activa) == [True, False, False, True]


def test_la_banda_puede_seguir_a_un_objetivo_movil(xp: XpVec) -> None:
    """D4 y D5: la banda de mezcla es `objetivo x 0,93` a `objetivo x 1,04`, no
    dos números fijos."""
    objetivo = _serie([1.00, 0.85, 0.85])
    lam = _serie([1.00, 1.00, 0.86])
    minimo = Serie(t_ms=objetivo.t_ms, v=objetivo.v * 0.93, clase=Clase.PUNTO)
    maximo = Serie(t_ms=objetivo.t_ms, v=objetivo.v * 1.04, clase=Clase.PUNTO)
    dentro = banda(lam, minimo=minimo, maximo=maximo, histeresis_relativa=0.0, xp=xp)
    # Con el objetivo en 0,85 la misma λ de 1,00 se sale de la banda: es la
    # mezcla pobre en carga que un par de números fijos no vería.
    assert list(dentro.activa) == [True, False, True]


def test_la_histeresis_de_la_banda_evita_la_rafaga_en_el_borde(xp: XpVec) -> None:
    """EL CASO DE BORDE DE LA BANDA: una λ que roza el borde superior de su
    banda objetivo. Sin margen, un evento por cada oscilación."""
    valores = [1.04 if i % 2 == 0 else 1.06 for i in range(30)]
    lam = _serie(valores)

    sin_margen = banda(lam, minimo=0.90, maximo=1.05, histeresis_relativa=0.0, xp=xp)
    con_margen = banda(lam, minimo=0.90, maximo=1.05, histeresis_relativa=0.2, xp=xp)

    fuera_sin = eventos(sin_margen.no(), permanencia=_permanencia(), xp=xp)
    fuera_con = eventos(con_margen.no(), permanencia=_permanencia(), xp=xp)
    assert len(fuera_sin) == 15
    assert len(fuera_con) == 0


def test_una_banda_del_reves_es_un_error(xp: XpVec) -> None:
    lam = _serie([1.0])
    with pytest.raises(ErrorDePrimitiva, match="mínimo por encima"):
        banda(lam, minimo=1.10, maximo=0.90, histeresis_relativa=0.0, xp=xp)


def test_una_histeresis_relativa_absurda_se_rechaza(xp: XpVec) -> None:
    lam = _serie([1.0])
    with pytest.raises(ErrorDePrimitiva, match="fracción"):
        banda(lam, minimo=0.9, maximo=1.05, histeresis_relativa=1.0, xp=xp)


# --------------------------------------------------------------------------- #
# 6. Derivada
# --------------------------------------------------------------------------- #
def test_la_derivada_es_por_segundo_y_sobre_la_ventana(xp: XpVec) -> None:
    """Un tip-in: la mariposa pasa de 0,10 a 0,90 en 100 ms -> 8 fracción/s.

    Con una ventana de 100 ms la derivada mira dos muestras atrás (dt 50 ms), no
    una, así que el flanco sale completo y no partido en dos mitades.
    """
    tps = _serie([0.10, 0.50, 0.90, 0.90])
    tasa = derivada(tps, ventana_s=0.1, xp=xp)
    assert tasa.clase is Clase.TASA
    assert tasa.v[2] == pytest.approx(8.0)
    assert list(tasa.valido) == [False, True, True, True]


def test_la_derivada_no_asume_muestreo_uniforme(xp: XpVec) -> None:
    """`docs/01` §1.7: el AutoLog es bimodal, con dt de 35 a 499 ms, y «no se
    debe asumir muestreo uniforme para ningún cálculo (derivadas...)». La
    ventana se resuelve sobre `t` de verdad."""
    serie = Serie(
        t_ms=Vec([0.0, 40.0, 300.0, 340.0]),
        v=Vec([0.0, 1.0, 2.0, 3.0]),
        clase=Clase.PUNTO,
    )
    tasa = derivada(serie, ventana_s=0.1, xp=xp)
    # La tercera muestra (300 ms) no tiene ninguna anterior dentro de sus 100 ms:
    # su ventana empieza en 200 ms y la muestra anterior está en 40 ms.
    assert list(tasa.valido) == [False, True, False, True]
    assert tasa.v[1] == pytest.approx(25.0)
    assert tasa.v[3] == pytest.approx(25.0)


def test_una_ventana_mas_larga_que_el_inicio_del_log_no_da_la_vuelta(xp: XpVec) -> None:
    """`t` es uint32 en el almacén: restarle una ventana mayor que el instante
    actual con aritmética de entero sin signo daría un número enorme, y las
    primeras muestras buscarían su origen al final del log."""
    serie = _serie([1.0, 2.0, 3.0], dt_ms=50.0)
    tasa = derivada(serie, ventana_s=10.0, xp=xp)
    assert list(tasa.valido) == [False, True, True]
    assert tasa.v[2] == pytest.approx(20.0)


def test_no_se_deriva_dos_veces(xp: XpVec) -> None:
    """`Clase` no tiene miembro para la segunda derivada, así que devolver TASA
    otra vez sería mentir sobre lo que hay en el array."""
    tasa = derivada(_serie([0.0, 1.0, 2.0]), ventana_s=0.05, xp=xp)
    with pytest.raises(ErrorDePrimitiva, match="segunda"):
        derivada(tasa, ventana_s=0.05, xp=xp)


def test_la_derivada_con_umbral_es_el_tip_in_completo(xp: XpVec) -> None:
    """La «Derivada (ventana, umbral)» de §4.3, montada como manda el módulo:
    la derivada transforma y el umbral dispara, con su histéresis."""
    tps = _serie([0.10, 0.12, 0.60, 0.90, 0.90, 0.88])
    tasa = derivada(tps, ventana_s=0.05, xp=xp)
    cond = umbral_con_histeresis(tasa, entrada=2.0, salida=0.5, direccion=Direccion.ARRIBA, xp=xp)
    resultado = eventos(cond, permanencia=_permanencia(), xp=xp)
    assert len(resultado) == 1
    assert resultado[0].i_inicio == 2


# --------------------------------------------------------------------------- #
# 7. Delta de contador
# --------------------------------------------------------------------------- #
def test_el_delta_de_contador_dispara_con_cualquier_incremento(xp: XpVec) -> None:
    """D1: «cualquier incremento cuenta: un solo evento de knock importa».
    El contador acumulado es «una escalera ilegible» (§4.2 P2); el delta es lo
    que se mira."""
    contador = _serie([0.0, 0.0, 3.0, 3.0, 4.0])
    delta = delta_de_contador(contador, xp=xp)
    assert delta.clase is Clase.INTERVALO
    assert list(delta.v)[1:] == [0.0, 3.0, 0.0, 1.0]
    cond = umbral_con_histeresis(delta, entrada=1.0, salida=1.0, direccion=Direccion.ARRIBA, xp=xp)
    resultado = eventos(cond, permanencia=_permanencia(), xp=xp)
    assert [e.i_inicio for e in resultado] == [2, 4]
    assert resultado[0].valor_pico is None


def test_la_primera_muestra_no_tiene_delta_medible(xp: XpVec) -> None:
    delta = delta_de_contador(_serie([7.0, 7.0]), xp=xp)
    assert list(delta.valido) == [False, True]


def test_un_contador_que_se_reinicia_no_es_un_evento_de_knock(xp: XpVec) -> None:
    """La ECU se reinició, el log se cortó o el contador dio la vuelta: el
    incremento real es desconocido. El valor negativo se deja a la vista —saber
    que hubo un reinicio es diagnóstico— pero marcado como hueco."""
    delta = delta_de_contador(_serie([100.0, 102.0, 0.0, 1.0]), xp=xp)
    assert list(delta.valido) == [False, True, False, True]
    assert delta.v[2] == pytest.approx(-102.0)
    cond = umbral_con_histeresis(delta, entrada=1.0, salida=1.0, direccion=Direccion.ARRIBA, xp=xp)
    assert [e.i_inicio for e in eventos(cond, permanencia=_permanencia(), xp=xp)] == [1, 3]


def test_el_delta_solo_se_toma_de_un_contador_absoluto(xp: XpVec) -> None:
    ya_delta = _serie([1.0, 2.0], clase=Clase.INTERVALO)
    with pytest.raises(ErrorDePrimitiva, match="PUNTO"):
        delta_de_contador(ya_delta, xp=xp)


# --------------------------------------------------------------------------- #
# 8. Extremo en ventana y pico local
# --------------------------------------------------------------------------- #
def test_el_extremo_en_ventana_centrada_es_correcto(xp: XpVec) -> None:
    serie = _serie([1.0, 5.0, 2.0, 9.0, 3.0, 4.0, 1.0], dt_ms=100.0)
    # Ventana centrada de 200 ms: la muestra i y sus dos vecinas.
    maximos = extremo_en_ventana(serie, desde_s=-0.1, hasta_s=0.1, extremo=Extremo.MAXIMO, xp=xp)
    assert list(maximos.v)[1:6] == [5.0, 9.0, 9.0, 9.0, 4.0]
    # Los bordes salen como hueco: su ventana se sale del log.
    assert list(maximos.valido) == [False, True, True, True, True, True, False]


def test_el_extremo_en_ventana_posterior_es_lo_que_pide_d15(xp: XpVec) -> None:
    """P5 y D15: «se mide la desviación máxima de λ en la ventana siguiente».
    La ventana asimétrica es lo que hace que ese detector sea expresable."""
    lam = _serie([1.00, 1.00, 1.09, 1.02, 1.00, 1.00], dt_ms=100.0)
    peor = extremo_en_ventana(lam, desde_s=0.0, hasta_s=0.2, extremo=Extremo.MAXIMO, xp=xp)
    # La ventana es CERRADA en los dos extremos: [t, t+200 ms] incluye la muestra
    # de t+200. Desde t=0 eso alcanza el 1,09 de los 200 ms.
    assert peor.v[0] == pytest.approx(1.09)
    assert peor.v[1] == pytest.approx(1.09)
    # Y desde 300 ms el 1,09 ya ha quedado atrás: es lo que hace que la prueba
    # distinga una ventana posterior de una centrada.
    assert peor.v[3] == pytest.approx(1.02)
    # Las dos últimas no tienen ventana completa dentro del log. Esta aserción es
    # la que fija que el extremo lejano cuenta: con una ventana abierta [t, t+200)
    # la muestra de 400 ms sí tendría ventana y saldría válida. La primera versión
    # de esta prueba pedía las dos cosas a la vez y no podía pasar.
    assert list(peor.valido)[-2:] == [False, False]


def test_el_extremo_en_ventana_respeta_una_rejilla_irregular(xp: XpVec) -> None:
    serie = Serie(
        t_ms=Vec([0.0, 40.0, 80.0, 500.0, 540.0]),
        v=Vec([1.0, 7.0, 2.0, 9.0, 3.0]),
        clase=Clase.PUNTO,
    )
    maximos = extremo_en_ventana(serie, desde_s=-0.1, hasta_s=0.1, extremo=Extremo.MAXIMO, xp=xp)
    # La muestra de 500 ms está sola en su ventana junto con la de 540: el 7 de
    # los 40 ms no entra, aunque en índices sea la penúltima anterior.
    assert maximos.v[3] == pytest.approx(9.0)
    assert maximos.v[1] == pytest.approx(7.0)


def test_el_extremo_en_ventana_de_anchura_grande_usa_todos_los_niveles(xp: XpVec) -> None:
    """La tabla dispersa se construye por duplicación, así que las anchuras que
    no son potencia de dos se resuelven con dos consultas solapadas. Con 11
    muestras y ventana de 11 se ejercitan los cuatro niveles."""
    valores = [float(v) for v in [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5]]
    serie = _serie(valores, dt_ms=10.0)
    maximos = extremo_en_ventana(serie, desde_s=-1.0, hasta_s=1.0, extremo=Extremo.MAXIMO, xp=xp)
    minimos = extremo_en_ventana(serie, desde_s=-1.0, hasta_s=1.0, extremo=Extremo.MINIMO, xp=xp)
    # Ninguna ventana de ±1 s cabe entera en un log de 110 ms: todas son hueco,
    # pero el valor calculado sigue siendo el del rango disponible.
    assert not any(maximos.valido)
    assert maximos.v[5] == pytest.approx(9.0)
    assert minimos.v[5] == pytest.approx(1.0)


def test_el_extremo_de_una_ventana_es_un_punto_no_un_intervalo(xp: XpVec) -> None:
    """Regla 4: el máximo de una ventana es un valor del canal (PUNTO). La
    amplitud de esa ventana sí sería un INTERVALO, y no es lo que se devuelve."""
    serie = _serie([1.0, 2.0, 3.0], clase=Clase.PUNTO)
    maximos = extremo_en_ventana(serie, desde_s=-0.05, hasta_s=0.05, extremo=Extremo.MAXIMO, xp=xp)
    assert maximos.clase is Clase.PUNTO


def test_el_pico_local_encuentra_el_pico_y_no_el_ruido(xp: XpVec) -> None:
    valores = [1.0, 1.1, 1.0, 1.1, 6.0, 1.1, 1.0, 1.1, 1.0]
    serie = _serie(valores, dt_ms=100.0)
    cond = pico_local(serie, prominencia_minima=2.0, ventana_s=0.4, xp=xp)
    resultado = eventos(cond, permanencia=_permanencia(), xp=xp)
    assert len(resultado) == 1
    assert resultado[0].i_inicio == 4


def test_el_pico_local_no_da_picos_donde_no_hay_prominencia(xp: XpVec) -> None:
    """«Picos reales, no ruido»: los dientes de sierra del ruido de
    cuantización son máximos locales y no son picos."""
    valores = [1.0 if i % 2 == 0 else 1.05 for i in range(11)]
    serie = _serie(valores, dt_ms=100.0)
    cond = pico_local(serie, prominencia_minima=0.5, ventana_s=0.4, xp=xp)
    assert not any(a and v for a, v in zip(cond.activa, cond.valido, strict=True))


def test_una_meseta_en_el_maximo_es_un_pico_y_no_cinco(xp: XpVec) -> None:
    valores = [1.0, 1.0, 5.0, 5.0, 5.0, 1.0, 1.0]
    serie = _serie(valores, dt_ms=100.0)
    cond = pico_local(serie, prominencia_minima=2.0, ventana_s=0.2, xp=xp)
    resultado = eventos(cond, permanencia=_permanencia(), xp=xp)
    assert len(resultado) == 1
    assert resultado[0].n_muestras == 3


def test_una_ventana_o_una_prominencia_absurdas_se_rechazan(xp: XpVec) -> None:
    serie = _serie([1.0, 2.0, 3.0])
    with pytest.raises(ErrorDePrimitiva, match="positiva"):
        pico_local(serie, prominencia_minima=1.0, ventana_s=0.0, xp=xp)
    with pytest.raises(ErrorDePrimitiva, match="negativa"):
        pico_local(serie, prominencia_minima=-1.0, ventana_s=0.4, xp=xp)
    with pytest.raises(ErrorDePrimitiva, match="antes"):
        extremo_en_ventana(serie, desde_s=0.2, hasta_s=0.1, extremo=Extremo.MAXIMO, xp=xp)


# --------------------------------------------------------------------------- #
# 9. Fuera de máscara
# --------------------------------------------------------------------------- #
def test_cualquier_bit_activo_dispara_cuando_interesan_todos() -> None:
    """D12: `bits_de_interes = "todos"` en `data/umbrales.toml`."""
    serie = SerieDeBits(t_ms=_t(4), bits=Vec([0, 0, 4, 0]))
    cond = fuera_de_mascara(serie, bits_de_interes=None)
    assert list(cond.activa) == [False, False, True, False]


def test_solo_los_bits_de_interes_disparan() -> None:
    serie = SerieDeBits(t_ms=_t(4), bits=Vec([0, 1, 2, 3]))
    cond = fuera_de_mascara(serie, bits_de_interes=2)
    assert list(cond.activa) == [False, False, True, True]


def test_una_mascara_de_cero_bits_es_un_error_no_un_detector_apagado() -> None:
    serie = SerieDeBits(t_ms=_t(2), bits=Vec([0, 1]))
    with pytest.raises(ErrorDePrimitiva, match="apagado"):
        fuera_de_mascara(serie, bits_de_interes=0)


def test_una_mascara_no_tiene_clase_de_conversion() -> None:
    """Una máscara de bits no es una medida y no se convierte nunca: darle una
    clase sería afirmar que sus tres bits son tres kPa."""
    assert "clase" not in inspect.signature(SerieDeBits).parameters


# --------------------------------------------------------------------------- #
# 10. Tiempo acumulado y conteo de cruces
# --------------------------------------------------------------------------- #
def test_el_tiempo_acumulado_es_la_suma_de_los_eventos_que_se_ensenan(xp: XpVec) -> None:
    """«45 s por encima de 105 °C» (§4.3). El total tiene que cuadrar con la
    lista que el usuario tiene delante: si esta función sumara la máscara por su
    cuenta, contaría también las muestras que la permanencia descartó."""
    cond = _condicion([False] + [True] * 5 + [False, True, False] + [True] * 3)
    permanencia = _permanencia(permanencia_s=0.1, muestras_minimas=3)
    lista = eventos(cond, permanencia=permanencia, xp=xp)
    assert [e.n_muestras for e in lista] == [5, 3]
    assert tiempo_acumulado(lista) == pytest.approx(0.2 + 0.1)


def test_el_tiempo_acumulado_de_nada_es_cero() -> None:
    assert tiempo_acumulado([]) == 0.0


def test_una_serie_de_un_solo_instante_no_acumula_tiempo(xp: XpVec) -> None:
    """Un evento de una muestra dura 0 s: se observó una vez y no se sabe cuánto
    duró. Contar el intervalo hasta la muestra siguiente sería atribuir tiempo a
    un tramo en el que no se observó nada."""
    lista = eventos(_condicion([False, True, False]), permanencia=_permanencia(), xp=xp)
    assert tiempo_acumulado(lista) == 0.0


def test_el_conteo_de_cruces_mide_oscilacion_aunque_no_haya_eventos(xp: XpVec) -> None:
    """§4.2 P6: «¿hay ciclo límite?». Una señal que oscila en el umbral tiene
    muchos cruces y ningún evento, y ese es el hallazgo: el lazo está inestable
    aunque no haya nada que alarme."""
    valores = [900.0 if i % 2 == 0 else 1100.0 for i in range(20)]
    serie = _serie(valores)
    cond = umbral_con_histeresis(
        serie, entrada=1000.0, salida=1000.0, direccion=Direccion.ARRIBA, xp=xp
    )
    assert conteo_de_cruces(cond, xp=xp) == 19
    assert eventos(cond, permanencia=_permanencia(muestras_minimas=3), xp=xp) == []


def test_un_cruce_con_un_hueco_de_por_medio_no_se_cuenta(xp: XpVec) -> None:
    cond = _condicion([False, True, False], valido=[True, False, True])
    assert conteo_de_cruces(cond, xp=xp) == 0


# --------------------------------------------------------------------------- #
# 11. ADR-009: el coste no crece con el número de muestras
# --------------------------------------------------------------------------- #
def test_el_numero_de_operaciones_de_array_no_depende_de_las_muestras() -> None:
    """La comprobación por CONDUCTA, no por patrón (`tools/banco.py adr009` ya
    hace la del patrón).

    Se ejecuta la misma tubería completa —umbral con histéresis, permanencia,
    eventos con pico— sobre 50 muestras y sobre 5 000, y se cuenta cuántas veces
    se llama al protocolo `Vectorial`. Con un bucle por muestra escondido, el
    número crecería cien veces. Aquí es el mismo, salvo el bucle sobre EVENTOS
    (que es el permitido, y que aquí produce un evento en los dos casos).
    """

    def tuberia(n: int) -> int:
        xp = XpVec()
        valores = [300.0] * (n // 2) + [380.0] * (n - n // 2)
        serie = _serie(valores)
        cond = umbral_con_histeresis(
            serie, entrada=378.0, salida=376.0, direccion=Direccion.ARRIBA, xp=xp
        )
        lista = eventos(
            cond,
            permanencia=_permanencia(permanencia_s=0.1, muestras_minimas=3),
            pico=Pico(serie=serie, extremo=Extremo.MAXIMO),
            xp=xp,
        )
        assert len(lista) == 1
        return xp.total

    assert tuberia(50) == tuberia(5_000)


def test_las_ventanas_cuestan_logaritmicamente_en_la_anchura() -> None:
    """La tabla dispersa de extremos: `log2(anchura)` pasadas para construirla y
    un bucle sobre NIVELES para consultarla, nunca sobre muestras.

    Con la anchura de la ventana multiplicada por 16 (cuatro duplicaciones), el
    número de operaciones de array sube en unas pocas unidades, no en
    proporción. Es lo que permite que una ventana de medio segundo a 20 Hz
    cueste cuatro pasadas.
    """

    def coste(ventana_s: float, n: int) -> int:
        xp = XpVec()
        serie = _serie([float(i % 7) for i in range(n)], dt_ms=10.0)
        extremo_en_ventana(
            serie, desde_s=-ventana_s, hasta_s=ventana_s, extremo=Extremo.MAXIMO, xp=xp
        )
        return xp.total

    estrecha = coste(0.02, 2_000)
    ancha = coste(0.32, 2_000)
    assert ancha - estrecha <= 12, (
        f"la ventana 16 veces más ancha cuesta {ancha - estrecha} operaciones más: "
        "eso no es logarítmico"
    )


def test_el_modulo_no_tiene_bucles_sobre_muestras() -> None:
    """Los `for` y los `while` del módulo, uno por uno, con lo que recorren.

    `tools/banco.py adr009` busca patrones de Pandas/Polars (`iterrows`,
    `apply(lambda)`) y no un `for` corriente, así que esta prueba mira los
    bucles de verdad: solo se admiten los que recorren eventos, niveles de la
    tabla de extremos o potencias de dos, y ninguno puede iterar sobre un
    `range(len(...))` de una serie.
    """
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"), filename=str(MODULO))
    bucles = [n for n in ast.walk(arbol) if isinstance(n, (ast.For, ast.While))]
    permitidos = {
        "range(total)",  # eventos que sobreviven a la permanencia
        "enumerate(potencias)",  # niveles de la tabla de extremos
        "range(len(tabla))",  # niveles de la tabla de extremos
        "paso * 2 <= ancho_maximo",  # duplicación de la tabla: log2(anchura)
    }
    for nodo in bucles:
        recorrido = ast.unparse(nodo.iter) if isinstance(nodo, ast.For) else ast.unparse(nodo.test)
        assert recorrido in permitidos, (
            f"bucle en la línea {nodo.lineno} sobre {recorrido!r}: los bucles de este "
            "módulo solo pueden recorrer eventos o niveles, nunca muestras (ADR-009)"
        )


# --------------------------------------------------------------------------- #
# 12. Los umbrales no están cableados (regla 3 de CLAUDE.md)
# --------------------------------------------------------------------------- #
def test_ningun_parametro_numerico_de_la_api_tiene_valor_por_omision() -> None:
    """La decisión de diseño que hace improbable el defecto, no solo detectable.

    Un valor por omisión numérico en el código es una copia de
    `data/umbrales.toml` que se puede desincronizar sin que nada se ponga en
    rojo. Se comprueba sobre las firmas reales, igual que
    `test_los_umbrales_no_tienen_valor_por_omision` en `test_plausibilidad.py` y
    `test_no_hay_clase_por_omision` en `test_trampa_del_delta.py`.

    `None` y `False` no cuentan: `xp=None` significa «usa NumPy» y no es un
    umbral. Lo que no puede aparecer es un número.
    """
    publicos = [
        Permanencia,
        alinear,
        banda,
        conteo_de_cruces,
        delta_de_contador,
        derivada,
        eventos,
        extremo_en_ventana,
        fuera_de_mascara,
        pico_local,
        umbral_con_histeresis,
    ]
    for objeto in publicos:
        for nombre, p in inspect.signature(objeto).parameters.items():
            if p.default is inspect.Parameter.empty:
                continue
            assert not isinstance(p.default, (int, float)) or isinstance(p.default, bool), (
                f"{objeto.__name__}.{nombre} tiene el valor por omisión numérico "
                f"{p.default!r}: eso es una copia de un umbral de data/umbrales.toml "
                "que puede desincronizarse en silencio"
            )


def test_el_modulo_no_contiene_los_umbrales_cableados() -> None:
    """Inspección de los literales del módulo, deliberadamente literal.

    Un umbral cableado no rompe ninguna prueba funcional —el módulo sigue siendo
    coherente consigo mismo— así que lo único que lo detecta es buscarlo. Se
    hace sobre el AST y no sobre el texto para no marcar los números que
    aparecen en los comentarios y en los docstrings explicando de dónde salen
    (la trampa que ya se pagó con el detector de ADR-009).

    Cubre las tres secciones de `data/umbrales.toml` que este módulo consume:
    `[general]`, `[motor_de_deteccion]` y los umbrales de los 18 detectores, que
    son los que F3-07 le pasará y que por tanto tampoco pueden estar aquí.
    """
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    prohibidos: set[float] = set()
    for seccion in (bruto["general"], bruto["motor_de_deteccion"]):
        prohibidos.update(float(v) for v in seccion.values() if isinstance(v, (int, float)))
    for detector in bruto["detectores"].values():
        for valor in detector.values():
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                prohibidos.add(float(valor))
    # 0, 1, 2 y −1 no cuentan: el módulo los usa para contar, para desplazar un
    # índice y para partir una ventana por la mitad, no como umbrales. Que un
    # detector declare `delta_minimo = 1` no puede prohibirle al motor usar el
    # número 1 para nada.
    prohibidos -= {0.0, 1.0, 2.0, -1.0}
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"), filename=str(MODULO))
    encontrados = sorted(
        {
            float(n.value)
            for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
            if not isinstance(n.value, bool) and float(n.value) in prohibidos
        }
    )
    assert not encontrados, f"umbrales de data/umbrales.toml cableados en el módulo: {encontrados}"


def test_falta_una_clave_de_umbral_y_falla_en_vez_de_suponerla() -> None:
    with pytest.raises(ErrorDePrimitiva, match="maximo_de_eventos"):
        Permanencia.desde_mapa({"permanencia_s": 0.1, "muestras_minimas": 3})


def test_una_anulacion_mal_escrita_no_se_ignora_en_silencio() -> None:
    """Una anulación por canal con el nombre mal escrito seguiría usando el
    valor por omisión sin decir nada, y quien la escribió creería que está
    activa."""
    permanencia = _permanencia()
    with pytest.raises(ErrorDePrimitiva, match="desconocidas"):
        permanencia.fusionar({"permanencia": 3.0})


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("permanencia_s", -0.1),
        ("muestras_minimas", 0),
        ("maximo_de_eventos", 0),
    ],
)
def test_una_permanencia_absurda_se_rechaza(clave: str, valor: Any) -> None:
    with pytest.raises(ErrorDePrimitiva):
        _permanencia(**{clave: valor})


def test_los_umbrales_por_canal_ganan_a_los_del_fichero(xp: XpVec) -> None:
    """Primer nivel de la precedencia de `data/umbrales.toml`: anulación por
    canal. El motor no decide de dónde sale cada capa, solo sabe combinarlas sin
    perder la validación."""
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    del_fichero = Permanencia.desde_mapa({**bruto["general"], **bruto["motor_de_deteccion"]})
    del_canal = del_fichero.fusionar({"permanencia_s": 3.0})
    assert del_fichero.permanencia_s == pytest.approx(0.1)
    assert del_canal.permanencia_s == pytest.approx(3.0)
    assert del_canal.muestras_minimas == del_fichero.muestras_minimas

    cond = _condicion([True] * 5)  # 5 muestras a 50 ms = 200 ms
    assert len(eventos(cond, permanencia=del_fichero, xp=xp)) == 1
    assert eventos(cond, permanencia=del_canal, xp=xp) == []


# --------------------------------------------------------------------------- #
# 13. Contra el fichero real de umbrales
# --------------------------------------------------------------------------- #
def test_los_umbrales_reales_cargan_y_son_coherentes() -> None:
    """Que el fichero de datos y el módulo encajen, y que los tres números
    nuevos sigan significando lo que dicen sus comentarios.

    Las invariantes, no los valores: la ventana de validez tiene que estar por
    encima del periodo del grupo más lento (202 ms, `docs/01` §1.6) y por debajo
    del umbral de hueco de muestreo (3x ese periodo, D18), o dejaría de
    distinguir un canal lento de un canal que dejó de emitir.
    """
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    motor = bruto["motor_de_deteccion"]
    dt_mediano_grupo_lento_ms = 202.0
    factor_hueco = float(bruto["detectores"]["D18"]["factor_sobre_dt_mediano"])

    assert motor["ventana_validez_ms"] > dt_mediano_grupo_lento_ms
    assert motor["ventana_validez_ms"] < factor_hueco * dt_mediano_grupo_lento_ms
    assert motor["maximo_de_eventos"] >= 1
    assert motor["ventana_pico_s"] > 0.0

    permanencia = Permanencia.desde_mapa({**bruto["general"], **motor})
    assert permanencia.permanencia_ms == pytest.approx(100.0)
    assert permanencia.muestras_minimas == 3


def test_la_permanencia_del_fichero_filtra_el_ruido_de_un_canal_real(xp: XpVec) -> None:
    """La configuración real, sobre la tasa real del AutoLog (dt mediano 54 ms,
    `docs/01` §1.7): con los valores de `[general]`, un pico de dos muestras no
    es un evento y uno de medio segundo sí."""
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    permanencia = Permanencia.desde_mapa({**bruto["general"], **bruto["motor_de_deteccion"]})
    t = _t(20, dt_ms=54.0)
    breve = Condicion(
        t_ms=t,
        activa=Vec([i in (5, 6) for i in range(20)]),
        valido=Vec([True] * 20),
    )
    largo = Condicion(
        t_ms=t,
        activa=Vec([5 <= i <= 14 for i in range(20)]),
        valido=Vec([True] * 20),
    )
    assert eventos(breve, permanencia=permanencia, xp=xp) == []
    (evento,) = eventos(largo, permanencia=permanencia, xp=xp)
    assert evento.duracion_s == pytest.approx(0.486)


def test_la_histeresis_relativa_del_fichero_sobre_una_temperatura_es_el_hallazgo() -> None:
    """Deja escrito en una prueba lo que el informe de la tarea dice en prosa:
    `[general].histeresis_relativa` NO está bien definida para un umbral con
    origen desplazado.

    El 2 % del umbral canónico de D9 (378,15 K) son 7,6 K, así que la alarma de
    refrigerante no se cerraría hasta los 97,4 °C; el 2 % del mismo umbral leído
    en grados Celsius serían 2,1 K. El número depende de la unidad en la que se
    mire, y por eso `umbral_con_histeresis` exige el umbral de salida absoluto y
    solo `banda` acepta la fracción (donde se aplica a una anchura, que es un
    INTERVALO).

    Si alguien «arregla» esto haciendo que el motor derive la salida de la
    fracción, esta prueba es la que explica por qué no.
    """
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    fraccion = float(bruto["general"]["histeresis_relativa"])
    umbral_k = float(bruto["detectores"]["D9"]["umbral_max_k"])

    banda_en_kelvin = fraccion * umbral_k
    banda_en_celsius = fraccion * (umbral_k - 273.15)
    assert banda_en_kelvin == pytest.approx(7.563, abs=1e-3)
    assert banda_en_celsius == pytest.approx(2.1, abs=1e-3)
    assert banda_en_kelvin / banda_en_celsius > 3.5, (
        "si esto deja de cumplirse es que alguien cambió el umbral de D9; el "
        "argumento sigue siendo el mismo: una fracción de un punto depende del origen"
    )


# --------------------------------------------------------------------------- #
# 14. Los detectores de §4.3 se pueden escribir con estas piezas
# --------------------------------------------------------------------------- #
def test_d9_sobretemperatura_con_permanencia_de_tres_segundos(xp: XpVec) -> None:
    """El detector completo, tal como lo escribirá F3-07: umbral con histéresis
    + permanencia de la configuración de D9 + pico del canal que se lee.

    «Tres segundos: un pico corto al parar el motor es normal y no debe avisar.»
    """
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    d9 = bruto["detectores"]["D9"]
    permanencia = Permanencia.desde_mapa(
        {
            "permanencia_s": d9["permanencia_s"],
            "muestras_minimas": bruto["general"]["muestras_minimas"],
            "maximo_de_eventos": bruto["motor_de_deteccion"]["maximo_de_eventos"],
        }
    )
    umbral_k = float(d9["umbral_max_k"])
    # Canal de refrigerante a 5 Hz (grupo G2 de docs/01 §1.6): 2 s por encima al
    # principio (no avisa) y 4 s por encima después (avisa).
    valores = [370.0] * 5 + [380.0] * 10 + [370.0] * 5 + [380.0] * 21 + [370.0] * 5
    refrigerante = _serie(valores, dt_ms=202.0)
    cond = umbral_con_histeresis(
        refrigerante,
        entrada=umbral_k,
        salida=umbral_k - 2.0,
        direccion=Direccion.ARRIBA,
        xp=xp,
    )
    lista = eventos(
        cond,
        permanencia=permanencia,
        pico=Pico(serie=refrigerante, extremo=Extremo.MAXIMO),
        xp=xp,
    )
    assert len(lista) == 1
    assert lista[0].n_muestras == 21
    assert lista[0].valor_pico == pytest.approx(380.0)
    assert tiempo_acumulado(lista) == pytest.approx(4.04)


def test_d4_mezcla_pobre_en_carga_compone_cuatro_roles(xp: XpVec) -> None:
    """«λ > objetivo x 1,04 AND TPS > 70 % AND RPM > 3000», con el objetivo en su
    propia tasa y el resto en la rápida: es el detector crítico por excelencia y
    el que ejercita la tubería entera (alinear + umbral-canal + compuesto)."""
    t_rapido = _t(8, dt_ms=50.0)
    # Cinco muestras pobres, no cuatro. La permanencia se mide como
    # `t_fin - t_inicio`, que es lo que el contrato de `Permanencia` documenta
    # («3 muestras son 106 ms» sobre un canal a 20 Hz, o sea (3-1) x 53), así que
    # cuatro muestras a 50 ms son 150 ms y NO llegan a los 200 exigidos. La
    # primera versión de esta prueba pedía cuatro y esperaba que pasaran: no
    # comprobaba el detector, comprobaba una aritmética equivocada.
    lam = Serie(
        t_ms=t_rapido,
        v=Vec([0.85, 0.85, 0.95, 0.95, 0.95, 0.95, 0.95, 0.85]),
        clase=Clase.PUNTO,
    )
    tps = Serie(t_ms=t_rapido, v=Vec([0.9] * 8), clase=Clase.PUNTO)
    rpm = Serie(t_ms=t_rapido, v=Vec([4000.0] * 8), clase=Clase.PUNTO)
    objetivo_lento = Serie(t_ms=Vec([0.0, 200.0]), v=Vec([0.86, 0.86]), clase=Clase.PUNTO)

    objetivo = alinear(objetivo_lento, t_rapido, ventana_validez_ms=250.0, xp=xp)
    limite = Serie(t_ms=t_rapido, v=objetivo.v * 1.04, clase=Clase.PUNTO, valido=objetivo.valido)

    pobre = umbral_con_histeresis(
        lam, entrada=limite, salida=limite, direccion=Direccion.ARRIBA, xp=xp
    )
    en_carga = umbral_con_histeresis(
        tps, entrada=0.70, salida=0.70, direccion=Direccion.ARRIBA, xp=xp
    ).y(
        umbral_con_histeresis(
            rpm, entrada=3000.0, salida=3000.0, direccion=Direccion.ARRIBA, xp=xp
        ),
        xp=xp,
    )
    lista = eventos(
        pobre.y(en_carga, xp=xp),
        permanencia=_permanencia(permanencia_s=0.2, muestras_minimas=3),
        pico=Pico(serie=lam, extremo=Extremo.MAXIMO),
        xp=xp,
    )
    assert len(lista) == 1
    assert lista[0].n_muestras == 5  # 5 muestras a 50 ms = 200 ms justos
    assert lista[0].valor_pico == pytest.approx(0.95)


def test_los_eventos_no_contienen_huecos_por_construccion(xp: XpVec) -> None:
    """Propiedad que hace segura la lectura de un `Evento`: entre `i_inicio` e
    `i_fin` todas las muestras son válidas y activas."""
    activa = [True, True, False, True, True, True, True]
    valido = [True, True, True, True, False, True, True]
    cond = _condicion(activa, valido=valido)
    for evento in eventos(cond, permanencia=_permanencia(), xp=xp):
        for i in range(evento.i_inicio, evento.i_fin + 1):
            assert activa[i] and valido[i]


def test_un_evento_es_serializable_como_datos_planos() -> None:
    """El panel de incidencias (F3-12) y el informe de sesión (F4-11) lo cruzan
    por la frontera de `dlv-api`: nada dentro de `Evento` puede ser un array."""
    import dataclasses

    evento = Evento(
        t_inicio_ms=100.0,
        t_fin_ms=400.0,
        i_inicio=2,
        i_fin=8,
        n_muestras=7,
        valor_pico=380.0,
        clase_valor=Clase.PUNTO,
    )
    plano = dataclasses.asdict(evento)
    assert all(isinstance(v, (int, float, str, Clase)) for v in plano.values())
    assert evento.duracion_s == pytest.approx(0.3)


def test_las_marcas_de_tiempo_de_un_evento_no_son_nan(xp: XpVec) -> None:
    """Un `t_inicio_ms` NaN llegaría al «salto al instante» del panel de
    incidencias y no se notaría hasta pulsarlo."""
    for evento in eventos(_condicion([False, True, True]), permanencia=_permanencia(), xp=xp):
        assert not math.isnan(evento.t_inicio_ms)
        assert not math.isnan(evento.t_fin_ms)
