"""Pruebas de la segmentación automática (F3-16, `docs/04` §4.4).

QUÉ PROTEGE ESTA SUITE, ORDENADO POR CONSECUENCIA SI SE ROMPE
=============================================================
1. **No se pierde una tirada.** Es el entregable de §4.4 («sin segmentación el
   usuario busca sus tiradas a mano») y hay tres formas de perderla: sin
   histéresis en la mariposa, partiéndola en el cambio de marcha, o
   absorbiéndola en otra clase. Hay una prueba por cada una, y las tres están
   escritas con los números medidos del AutoLog real.
2. **La partición no se solapa ni deja huecos sin explicar.** `Cobertura` no se
   puede construir si las cuentas no suman, `InformeDeSegmentacion` rechaza dos
   segmentos que se pisen, y hay pruebas que construyen los dos casos malos a
   mano para comprobar que las guardas están vivas y no son decorativas.
3. **La precedencia decide, no el orden de evaluación.** Dos definiciones se
   pisan de verdad en dos sitios (la histéresis de «mariposa cerrada» contra la
   banda de crucero, y el borde de WOT contra el techo de esa banda). Se
   comprueba quién gana, que es la clase declarada, y que el resultado no cambia
   al pasar las clases al revés.
4. **Un rol que falta se dice, no se aproxima.** Sin `throttle_position` cuatro
   clases no se pueden calcular; sin `engine_speed`, ninguna. Las dos veces el
   informe lo dice con el nombre del rol en vez de devolver una lista vacía que
   parecería «este log no tiene tiradas».
5. **Ni un umbral cableado** (regla 3): dos guardas, una sobre las firmas y otra
   sobre los literales del módulo, más la comprobación de que la sección real de
   `data/umbrales.toml` carga y es coherente consigo misma.
6. **Ni un bucle por muestra** (ADR-009), por patrón y por conducta.

Como en `test_primitivas.py`, `test_malla.py` y `test_expresiones.py`, todo se
ejercita con `XpVec`, una implementación del protocolo `Vectorial` hecha con
biblioteca estándar: no es un simulacro, ejecuta el MISMO código que correrá con
NumPy. El doble es el de `test_primitivas.py` **copiado y no importado**, que es
la convención de este repositorio (cuatro suites tienen el suyo), con una prueba
propia de que `&` y `|` siguen siendo bit a bit: esa divergencia con NumPy ya se
pagó una vez y con ella las pruebas validan algo distinto de producción.
"""

from __future__ import annotations

import ast
import bisect
import inspect
import tomllib
from pathlib import Path
from typing import Any

import pytest

from dlv_core.primitivas import Clase, Evento, Permanencia, Serie
from dlv_core.segmentacion import (
    ROL_MARIPOSA,
    ROL_REGIMEN,
    ClaseDeSegmento,
    ClaseNoCalculable,
    Cobertura,
    ErrorDeSegmentacion,
    InformeDeSegmentacion,
    MotivoSinClasificar,
    Segmento,
    UmbralesDeSegmentacion,
    _condiciones_por_clase,
    _resolver_precedencia,
    segmentar,
)

RAIZ = Path(__file__).resolve().parent.parent.parent
UMBRALES_TOML = RAIZ / "data" / "umbrales.toml"
MODULO = RAIZ / "dlv-core" / "src" / "dlv_core" / "segmentacion.py"


# --------------------------------------------------------------------------- #
# El protocolo `Vectorial` con biblioteca estándar
# --------------------------------------------------------------------------- #
class Vec(list[Any]):
    """Vector con la aritmética elemento a elemento que necesita el motor.

    Los bucles están AQUÍ, en la prueba, que es donde ADR-009 los permite: lo que
    prohíbe es que estén en `dlv-core`. Con NumPy cada uno de estos métodos es una
    pasada en C sobre el array completo.
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
    # booleanos coinciden las dos cosas y por eso el error tardó en verse; sobre
    # enteros no. Python ya hace lo correcto en los dos casos: `bool & bool` da
    # `bool` e `int & int` da `int`, igual que NumPy.
    def __and__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a & b)

    def __or__(self, otro: Any) -> Any:
        return self._op(otro, lambda a, b: a | b)

    def __hash__(self) -> int:  # type: ignore[override]
        raise TypeError("un Vec no es hashable, igual que un ndarray")

    def __bool__(self) -> bool:
        if len(self) == 1:
            return bool(list.__getitem__(self, 0))
        raise ValueError("el valor de verdad de un Vec de longitud != 1 es ambiguo")


class XpVec:
    """Las nueve funciones del protocolo `Vectorial`, con los nombres de NumPy.

    Cuenta las llamadas para que las pruebas de ADR-009 puedan comprobar que el
    coste NO crece con el número de muestras.
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


def test_el_doble_hace_el_y_bit_a_bit_como_numpy() -> None:
    """La trampa ya pagada: con `and` lógico en vez de `&` bit a bit, el doble
    dejaría de comportarse como NumPy y las pruebas validarían otro código."""
    assert list(Vec([True, True]) & Vec([True, False])) == [True, False]
    assert list(Vec([6, 6]) & Vec([4, 1])) == [4, 0]
    assert list(Vec([4, 0]) | Vec([2, 0])) == [6, 0]


# --------------------------------------------------------------------------- #
# Utilidades de las pruebas
# --------------------------------------------------------------------------- #
DT_MS = 50.0
"""20 Hz, la tasa del grupo rápido de los logs reales (`docs/01` §1.6). Está aquí
y no en el módulo porque es una propiedad del fixture, no un umbral."""


def _t(n: int, dt_ms: float = DT_MS, t0: float = 0.0) -> Vec:
    return Vec([t0 + i * dt_ms for i in range(n)])


def _serie(valores: list[float], *, dt_ms: float = DT_MS, clase: Clase = Clase.PUNTO) -> Serie:
    return Serie(t_ms=_t(len(valores), dt_ms), v=Vec(valores), clase=clase)


def _rampa(desde: float, hasta: float, n: int) -> list[float]:
    """`n` valores de `desde` a `hasta`, los dos incluidos."""
    if n == 1:
        return [desde]
    paso = (hasta - desde) / (n - 1)
    return [desde + i * paso for i in range(n)]


def _umbrales(**anulaciones: Any) -> UmbralesDeSegmentacion:
    """Umbrales para las pruebas, con los valores de `data/umbrales.toml`.

    Están escritos aquí y no leídos del fichero a propósito: una prueba que lee
    el fichero comprueba el fichero, y estas comprueban el módulo con números
    fijos, de modo que un cambio del valor por omisión no las vuelve verdes o
    rojas por accidente. Las que sí van contra el fichero real están al final y
    comprueban invariantes, no valores.

    Las duraciones mínimas son 0 por omisión —la permanencia neutra deja ver lo
    que hace cada definición— y cada prueba que va de duraciones pone la suya.
    """
    base: dict[str, Any] = {
        "rpm_arranque_min": 50.0,
        "rpm_motor_en_marcha": 500.0,
        "rpm_ralenti_max": 1400.0,
        "rpm_decel_min": 2000.0,
        "rpm_creciente_min_por_s": 100.0,
        "rpm_estable_max_por_s": 300.0,
        "tps_cerrada_entrada": 0.02,
        "tps_cerrada_salida": 0.05,
        "tps_wot_entrada": 0.80,
        "tps_wot_salida": 0.75,
        "ventana_derivada_s": 0.25,
        "ventana_validez_ms": 250.0,
        "histeresis_relativa": 0.02,
        "duracion_minima_s": dict.fromkeys((c.value for c in ClaseDeSegmento), 0.0),
    }
    duraciones = anulaciones.pop("duraciones", None)
    if duraciones is not None:
        base["duracion_minima_s"].update({c.value: d for c, d in duraciones.items()})
    base.update(anulaciones)
    return UmbralesDeSegmentacion.desde_mapa(base)


def _permanencia(*, muestras_minimas: int = 1) -> Permanencia:
    """Permanencia base neutra. La duración mínima por clase la pone
    `UmbralesDeSegmentacion`, así que aquí solo queda el mínimo de muestras."""
    return Permanencia(
        permanencia_s=0.0, muestras_minimas=muestras_minimas, maximo_de_eventos=10_000
    )


def _segmentar(
    regimen: list[float],
    mariposa: list[float] | None,
    xp: XpVec,
    **anulaciones: Any,
) -> InformeDeSegmentacion:
    series = {ROL_REGIMEN: _serie(regimen)}
    if mariposa is not None:
        series[ROL_MARIPOSA] = _serie(mariposa)
    return segmentar(
        series,
        umbrales=_umbrales(**anulaciones),
        permanencia_base=_permanencia(),
        xp=xp,
    )


def _clases(informe: InformeDeSegmentacion) -> list[ClaseDeSegmento]:
    return [s.clase for s in informe.segmentos]


def _clase_de_la_muestra(informe: InformeDeSegmentacion, i: int) -> ClaseDeSegmento | None:
    for s in informe.segmentos:
        if s.evento.i_inicio <= i <= s.evento.i_fin:
            return s.clase
    return None


# --------------------------------------------------------------------------- #
# 1. Las cinco clases, con su caso positivo y su negativo
# --------------------------------------------------------------------------- #
def test_ralenti_positivo(xp: XpVec) -> None:
    """Motor en marcha en la banda de ralentí con la mariposa cerrada: la meseta
    de los primeros 37 s del AutoLog, a la escala de la prueba."""
    informe = _segmentar([950.0] * 20, [0.0] * 20, xp)
    assert _clases(informe) == [ClaseDeSegmento.RALENTI]
    assert informe.segmentos[0].evento.n_muestras == 20
    assert informe.cobertura.fraccion_cubierta == pytest.approx(1.0)


def test_ralenti_negativo_con_la_mariposa_abierta(xp: XpVec) -> None:
    """El mismo régimen con un 10 % de mariposa NO es ralentí: es carga parcial.
    Y como el régimen es estacionario, es crucero -- que es el caso positivo de
    la quinta clase visto desde el otro lado."""
    informe = _segmentar([950.0] * 20, [0.10] * 20, xp)
    assert informe.de_clase(ClaseDeSegmento.RALENTI) == ()
    assert ClaseDeSegmento.CRUCERO in _clases(informe)


def test_wot_positivo(xp: XpVec) -> None:
    """Mariposa a fondo 2 s con el régimen subiendo 500 rpm/s: una tirada.

    El pico es el MÁXIMO del régimen —el número que nombra la tirada— y lleva su
    clase de conversión (`PUNTO`) hasta quien lo pinte.
    """
    n = 40
    informe = _segmentar(
        _rampa(4000.0, 5000.0, n), [0.9] * n, xp, duraciones={ClaseDeSegmento.WOT: 1.5}
    )
    assert _clases(informe) == [ClaseDeSegmento.WOT]
    segmento = informe.segmentos[0]
    assert segmento.evento.n_muestras == n
    assert segmento.regimen_pico == pytest.approx(5000.0)
    assert segmento.evento.clase_valor is Clase.PUNTO
    assert segmento.duracion_s == pytest.approx(1.95)


def test_wot_negativo_por_duracion(xp: XpVec) -> None:
    """La misma tirada de 1 s no llega al «> 1,5 s» de §4.4, y las muestras que
    reclamaba se cuentan como DURACION_INSUFICIENTE en vez de desaparecer."""
    n = 20
    informe = _segmentar(
        _rampa(4000.0, 4500.0, n), [0.9] * n, xp, duraciones={ClaseDeSegmento.WOT: 1.5}
    )
    assert informe.de_clase(ClaseDeSegmento.WOT) == ()
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.DURACION_INSUFICIENTE] == n


def test_wot_negativo_por_pendiente(xp: XpVec) -> None:
    """Mariposa a fondo 2 s con el régimen PLANO: un mantenido en banco, no una
    tirada. §4.4 pide «RPM creciente», y el motivo se separa del de duración
    porque la acción que sugiere es otra."""
    n = 40
    informe = _segmentar([6000.0] * n, [0.9] * n, xp, duraciones={ClaseDeSegmento.WOT: 1.5})
    assert informe.de_clase(ClaseDeSegmento.WOT) == ()
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.PENDIENTE_INSUFICIENTE] == n
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.DURACION_INSUFICIENTE] == 0


def test_una_tirada_no_se_parte_en_el_cambio_de_marcha(xp: XpVec) -> None:
    """La prueba que decide entre encontrar las tiradas y perderlas.

    En la segunda tirada del AutoLog real la derivada del régimen llega a
    −1 238 rpm/s durante tres muestras: un cambio de marcha con la mariposa
    abierta. Con el criterio de régimen creciente aplicado POR MUESTRA, la tirada
    se partiría en dos trozos que la duración mínima descartaría los dos, y la
    tirada —que existe y dura 2,1 s— se perdería entera. Aplicado al tramo, sale
    un solo segmento.
    """
    n = 40
    regimen = _rampa(4700.0, 5400.0, n)
    for i in (18, 19, 20):  # el cambio de marcha: el régimen cae de golpe
        regimen[i] -= 300.0
    informe = _segmentar(regimen, [0.9] * n, xp, duraciones={ClaseDeSegmento.WOT: 1.5})
    assert _clases(informe) == [ClaseDeSegmento.WOT]
    assert informe.segmentos[0].evento.n_muestras == n


def test_deceleracion_positiva(xp: XpVec) -> None:
    """Mariposa cerrada por encima de 2 000 rpm (§4.4). El pico es el MÍNIMO:
    hasta dónde bajó la retención."""
    n = 20
    informe = _segmentar(_rampa(4000.0, 2500.0, n), [0.0] * n, xp)
    assert _clases(informe) == [ClaseDeSegmento.DECELERACION]
    assert informe.segmentos[0].regimen_pico == pytest.approx(2500.0)


def test_deceleracion_negativa_con_la_mariposa_abierta(xp: XpVec) -> None:
    """El mismo régimen cayendo con un 30 % de mariposa no es una retención: el
    conductor tiene el pie puesto. Y tampoco es crucero, porque el régimen se
    mueve 1 500 rpm en un segundo."""
    n = 20
    informe = _segmentar(_rampa(4000.0, 2500.0, n), [0.30] * n, xp)
    assert informe.de_clase(ClaseDeSegmento.DECELERACION) == ()
    assert informe.de_clase(ClaseDeSegmento.CRUCERO) == ()
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.NINGUNA_CLASE] > 0


def test_la_retencion_entera_es_un_segmento_y_entrega_el_relevo_al_ralenti(xp: XpVec) -> None:
    """El umbral de salida de la deceleración es el techo del ralentí, y eso es lo
    que evita un hueco entre las dos clases.

    Una retención de 3 000 a 800 rpm con la mariposa cerrada tiene que salir como
    UNA deceleración hasta el techo del ralentí y UN ralentí a partir de ahí, sin
    ninguna muestra sin clasificar en medio. Con la salida en los mismos 2 000 rpm
    de la entrada, el tramo entre 2 000 y 1 400 no sería de ninguna de las dos.
    """
    n = 45
    informe = _segmentar(_rampa(3000.0, 800.0, n), [0.0] * n, xp)
    assert _clases(informe) == [ClaseDeSegmento.DECELERACION, ClaseDeSegmento.RALENTI]
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.NINGUNA_CLASE] == 0
    assert informe.cobertura.fraccion_cubierta == pytest.approx(1.0)


def test_arranque_positivo(xp: XpVec) -> None:
    """El motor gira por debajo del régimen en que se sostiene solo, y luego
    prende. La primera parte es el arranque; la segunda, el ralentí."""
    regimen = [250.0] * 20 + [900.0] * 20
    informe = _segmentar(
        regimen,
        [0.0] * 40,
        xp,
        duraciones={ClaseDeSegmento.ARRANQUE: 0.5, ClaseDeSegmento.RALENTI: 0.5},
    )
    assert _clases(informe) == [ClaseDeSegmento.ARRANQUE, ClaseDeSegmento.RALENTI]
    assert informe.segmentos[0].evento.n_muestras == 20


def test_arranque_negativo_un_tiron_de_embrague_no_es_un_arranque(xp: XpVec) -> None:
    """El falso positivo medido en el AutoLog real: dos caídas de régimen a 412 y
    471 rpm que entran en la banda de arranque durante 0,17 s y 0,15 s.

    La duración mínima de 0,5 s es lo único que las separa de un arranque de
    verdad, porque `roles.toml` no declara ningún rol de `Fuel Cranking` con el
    que confirmarlo (§4.4 lo pide y el catálogo no lo tiene).
    """
    regimen = [1186.0, 1173.0, 1110.0, 933.0, 579.0, 427.0, 412.0, 1002.0, 1287.0, 1254.0]
    informe = _segmentar(
        regimen, [0.0] * len(regimen), xp, duraciones={ClaseDeSegmento.ARRANQUE: 0.5}
    )
    assert informe.de_clase(ClaseDeSegmento.ARRANQUE) == ()
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.DURACION_INSUFICIENTE] >= 2


def test_crucero_positivo(xp: XpVec) -> None:
    """Carga parcial con el régimen estacionario: el estado que alimenta la tabla
    RPM×MAP de §4.6.

    La primera muestra no puede ser crucero y eso es correcto: la derivada del
    régimen necesita una muestra anterior dentro de su ventana, y sin ella no se
    sabe si el régimen era estacionario. Sale como SIN_DATOS —no se pudo evaluar—
    y no como NINGUNA_CLASE, que afirmaría que se evaluó y no se cumplía.
    """
    n = 60
    informe = _segmentar([3000.0] * n, [0.30] * n, xp)
    assert _clases(informe) == [ClaseDeSegmento.CRUCERO]
    assert informe.segmentos[0].evento.i_inicio == 1
    assert informe.cobertura.por_clase[ClaseDeSegmento.CRUCERO] == n - 1
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.SIN_DATOS] == 1
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.NINGUNA_CLASE] == 0


def test_crucero_negativo_con_el_regimen_subiendo(xp: XpVec) -> None:
    """Carga parcial con el régimen subiendo 1 000 rpm/s no es crucero: es un
    transitorio, y es exactamente lo que §4.6 manda excluir de la tabla."""
    n = 40
    informe = _segmentar(_rampa(3000.0, 5000.0, n), [0.30] * n, xp)
    assert informe.de_clase(ClaseDeSegmento.CRUCERO) == ()
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.NINGUNA_CLASE] > 0


def test_el_motor_parado_no_es_un_hueco_de_cobertura(xp: XpVec) -> None:
    """Régimen 0: no hay nada que segmentar, y eso tiene su propio motivo. Un
    log que empieza con el motor parado no tiene un defecto de segmentación."""
    n = 10
    informe = _segmentar([0.0] * n, [0.0] * n, xp)
    assert informe.segmentos == ()
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.MOTOR_PARADO] == n


# --------------------------------------------------------------------------- #
# 2. La histéresis: un segmento y no doce
# --------------------------------------------------------------------------- #
def test_una_mariposa_que_oscila_en_el_umbral_da_una_tirada_y_no_doce(xp: XpVec) -> None:
    """El problema clásico de §4.3, en la clase donde más cuesta.

    Una mariposa que oscila un punto porcentual alrededor del 80 % con el régimen
    subiendo es UNA tirada. Con el umbral desnudo —la histéresis desactivada a
    propósito, declarando la salida igual que la entrada— son 21 fragmentos de una
    muestra; y con la duración mínima real de 1,5 s encima, no serían 21 tiradas:
    serían NINGUNA. Perder la tirada es peor que contarla veintiuna veces, y por
    eso la histéresis no es un adorno.
    """
    n = 41
    mariposa = [0.81 if i % 2 == 0 else 0.79 for i in range(n)]
    regimen = _rampa(4000.0, 5000.0, n)

    con = _segmentar(regimen, mariposa, xp, duraciones={ClaseDeSegmento.WOT: 1.5})
    assert _clases(con) == [ClaseDeSegmento.WOT]
    assert con.segmentos[0].evento.n_muestras == n

    # Sin histéresis y con las dos duraciones a cero, la fragmentación se ve
    # contada. La pendiente mínima también se relaja: un fragmento de una muestra
    # no tiene pendiente medible, y aquí lo que se está midiendo es el rebote del
    # umbral, no el criterio de tirada.
    sin = _segmentar(regimen, mariposa, XpVec(), tps_wot_salida=0.80, rpm_creciente_min_por_s=0.0)
    assert len(sin.de_clase(ClaseDeSegmento.WOT)) == 21

    sin_y_con_duracion = _segmentar(
        regimen, mariposa, XpVec(), tps_wot_salida=0.80, duraciones={ClaseDeSegmento.WOT: 1.5}
    )
    assert sin_y_con_duracion.de_clase(ClaseDeSegmento.WOT) == ()


def test_una_mariposa_que_oscila_en_el_cero_no_parte_el_ralenti(xp: XpVec) -> None:
    """El mismo problema en la otra punta: un TPS cuyo cero oscila entre el 1 % y
    el 3 % no parte un ralentí en cinco. La histéresis de «mariposa cerrada»
    (entrada 2 %, salida 5 %) es la que lo sostiene."""
    n = 40
    mariposa = [0.01 if i % 2 == 0 else 0.03 for i in range(n)]
    informe = _segmentar([950.0] * n, mariposa, xp)
    assert _clases(informe) == [ClaseDeSegmento.RALENTI]
    assert informe.segmentos[0].evento.n_muestras == n


# --------------------------------------------------------------------------- #
# 3. Solape y precedencia
# --------------------------------------------------------------------------- #
def test_el_solape_entre_ralenti_y_crucero_lo_gana_el_ralenti(xp: XpVec) -> None:
    """El solape ESTRUCTURAL, el que no depende de la configuración.

    Con la mariposa al 3 %, «cerrada» sigue activa por retención (entra al 2 % y
    sale al 5 %) y la banda de crucero ya está dentro (empieza en el 2 %). Las dos
    definiciones se cumplen en la misma muestra, y eso se comprueba aquí sobre las
    condiciones crudas antes de decidir nada. Gana el ralentí, que es la clase de
    mayor prioridad declarada.
    """
    n = 60
    mariposa = [0.0] * 10 + [0.03] * 30 + [0.10] * 20
    regimen = [1000.0] * n
    umbrales = _umbrales()

    # Las dos definiciones se pisan de verdad en la muestra 30.
    condiciones = _condiciones_por_clase(_serie(regimen), _serie(mariposa), umbrales, xp=xp)
    for clase in (ClaseDeSegmento.RALENTI, ClaseDeSegmento.CRUCERO):
        cond = condiciones[clase]
        assert cond.activa[30] and cond.valido[30], f"{clase.value} no está activa en la 30"

    informe = _segmentar(regimen, mariposa, XpVec())
    assert _clase_de_la_muestra(informe, 30) is ClaseDeSegmento.RALENTI
    assert ClaseDeSegmento.RALENTI.prioridad < ClaseDeSegmento.CRUCERO.prioridad
    # Y el crucero no desaparece: se queda con el tramo donde la mariposa ya está
    # abierta de verdad.
    assert _clase_de_la_muestra(informe, 55) is ClaseDeSegmento.CRUCERO


def test_el_solape_entre_wot_y_crucero_lo_gana_wot(xp: XpVec) -> None:
    """El otro solape estructural: la banda de crucero llega hasta el 80 % y su
    histéresis la ensancha por arriba, así que al 81 % de mariposa las dos
    definiciones se cumplen si el régimen sube despacio. Gana WOT, que es la
    tirada, y es la decisión que evita que una tirada se pierda dentro de un
    crucero."""
    n = 50
    mariposa = [0.50] * 10 + [0.81] * 40
    regimen = _rampa(4000.0, 4400.0, n)  # 200 rpm/s: sube y sigue siendo estacionario
    umbrales = _umbrales(duraciones={ClaseDeSegmento.WOT: 1.5})

    condiciones = _condiciones_por_clase(_serie(regimen), _serie(mariposa), umbrales, xp=xp)
    for clase in (ClaseDeSegmento.WOT, ClaseDeSegmento.CRUCERO):
        cond = condiciones[clase]
        assert cond.activa[30] and cond.valido[30], f"{clase.value} no está activa en la 30"

    informe = _segmentar(regimen, mariposa, XpVec(), duraciones={ClaseDeSegmento.WOT: 1.5})
    assert _clase_de_la_muestra(informe, 30) is ClaseDeSegmento.WOT
    assert ClaseDeSegmento.WOT.prioridad < ClaseDeSegmento.CRUCERO.prioridad


def test_la_precedencia_no_depende_del_orden_en_que_llegan_las_clases(xp: XpVec) -> None:
    """Lo que separa una precedencia declarada de un accidente del orden de
    evaluación: resolver las mismas condiciones en orden inverso da lo mismo."""
    n = 60
    mariposa = [0.0] * 10 + [0.03] * 30 + [0.10] * 20
    condiciones = _condiciones_por_clase(_serie([1000.0] * n), _serie(mariposa), _umbrales(), xp=xp)
    directo = _resolver_precedencia(condiciones, xp=xp)
    al_reves = _resolver_precedencia(
        {c: condiciones[c] for c in reversed(list(condiciones))}, xp=XpVec()
    )
    assert set(directo) == set(al_reves)
    for clase, cond in directo.items():
        assert list(cond.activa) == list(al_reves[clase].activa)
        assert list(cond.valido) == list(al_reves[clase].valido)


def test_la_precedencia_declarada_es_un_orden_total(xp: XpVec) -> None:
    """Dos clases con la misma prioridad harían que el solape entre ellas lo
    decidiera el orden de un `sorted`, que es lo que esta tarea no puede tener."""
    prioridades = [c.prioridad for c in ClaseDeSegmento]
    assert len(set(prioridades)) == len(prioridades)
    informe = _segmentar([950.0] * 10, [0.0] * 10, xp)
    assert informe.precedencia == tuple(sorted(ClaseDeSegmento, key=lambda c: c.prioridad))


def test_una_clase_superior_parte_la_inferior_y_se_dice(xp: XpVec) -> None:
    """La consecuencia declarada de aplicar la precedencia por muestra: una
    intrusión parte el tramo de la clase inferior en dos, y los dos trozos pasan
    su duración mínima por separado.

    Un crucero de 3 s con una retención de 1 s en medio son dos cruceros de 1 s,
    no uno de 3. Es lo correcto —y lo que hace que la partición no tenga solapes
    por construcción— pero hay que poder verlo.
    """
    regimen = [3000.0] * 20 + [2900.0] * 20 + [3000.0] * 20
    mariposa = [0.30] * 20 + [0.0] * 20 + [0.30] * 20
    informe = _segmentar(regimen, mariposa, xp)
    assert _clases(informe) == [
        ClaseDeSegmento.CRUCERO,
        ClaseDeSegmento.DECELERACION,
        ClaseDeSegmento.CRUCERO,
    ]


# --------------------------------------------------------------------------- #
# 4. La partición: sin solapes y sin huecos sin explicar
# --------------------------------------------------------------------------- #
def test_los_segmentos_no_se_solapan_ni_se_repiten_muestras(xp: XpVec) -> None:
    """Sobre un log con las cinco clases: ninguna muestra está en dos segmentos, y
    los segmentos vienen ordenados."""
    regimen = (
        [250.0] * 20  # arranque
        + [950.0] * 40  # ralentí
        + _rampa(1000.0, 5000.0, 40)  # subida
        + _rampa(5000.0, 6500.0, 40)  # tirada
        + _rampa(6500.0, 900.0, 60)  # retención hasta el ralentí
        + [3000.0] * 60  # crucero
    )
    mariposa = [0.0] * 60 + [0.30] * 40 + [0.9] * 40 + [0.0] * 60 + [0.30] * 60
    informe = _segmentar(
        regimen,
        mariposa,
        xp,
        duraciones={ClaseDeSegmento.WOT: 1.5, ClaseDeSegmento.ARRANQUE: 0.5},
    )
    vistas: set[int] = set()
    anterior = -1
    for s in informe.segmentos:
        assert s.evento.i_inicio > anterior
        anterior = s.evento.i_fin
        for i in range(s.evento.i_inicio, s.evento.i_fin + 1):
            assert i not in vistas
            vistas.add(i)
    assert len(vistas) == informe.cobertura.muestras_en_segmento


def test_las_cuentas_de_cobertura_cuadran_con_las_muestras(xp: XpVec) -> None:
    """El contrato en forma de aritmética: lo cubierto más los cinco motivos son
    exactamente las muestras de la rejilla. `Cobertura` no se puede construir de
    otra manera, así que esto comprueba además que la construyó con todos los
    trozos."""
    n = 80
    regimen = _rampa(900.0, 6000.0, 40) + _rampa(6000.0, 900.0, 40)
    mariposa = [0.30] * 20 + [0.9] * 20 + [0.0] * 40
    informe = _segmentar(regimen, mariposa, xp)
    cobertura = informe.cobertura
    assert cobertura.muestras == n
    assert cobertura.muestras_en_segmento + sum(cobertura.sin_clasificar.values()) == n
    assert set(cobertura.sin_clasificar) == set(MotivoSinClasificar)


def test_una_cobertura_que_no_cuadra_se_rechaza() -> None:
    """La guarda del contrato, comprobada por mutación: si dos clases reclamaran
    la misma muestra, las cuentas sumarían más que la rejilla y esto tiene que
    fallar. Sin esta prueba, la guarda podría estar mal escrita y nadie lo
    sabría."""
    with pytest.raises(ErrorDeSegmentacion, match="solape"):
        Cobertura(
            muestras=10,
            por_clase={ClaseDeSegmento.RALENTI: 6, ClaseDeSegmento.CRUCERO: 6},
            sin_clasificar=dict.fromkeys(MotivoSinClasificar, 0),
        )
    with pytest.raises(ErrorDeSegmentacion, match="falta un motivo"):
        Cobertura(
            muestras=10,
            por_clase={ClaseDeSegmento.RALENTI: 4},
            sin_clasificar=dict.fromkeys(MotivoSinClasificar, 0),
        )


def test_un_informe_con_segmentos_solapados_se_rechaza() -> None:
    """La otra mitad de la guarda: dos segmentos que comparten muestras no pueden
    salir de este módulo ni por un error interno."""

    def segmento(clase: ClaseDeSegmento, i_inicio: int, i_fin: int) -> Segmento:
        return Segmento(
            clase=clase,
            evento=Evento(
                t_inicio_ms=i_inicio * DT_MS,
                t_fin_ms=i_fin * DT_MS,
                i_inicio=i_inicio,
                i_fin=i_fin,
                n_muestras=i_fin - i_inicio + 1,
            ),
        )

    vacia = Cobertura(
        muestras=0, por_clase={}, sin_clasificar=dict.fromkeys(MotivoSinClasificar, 0)
    )
    with pytest.raises(ErrorDeSegmentacion, match="se solapan"):
        InformeDeSegmentacion(
            segmentos=(
                segmento(ClaseDeSegmento.CRUCERO, 0, 10),
                segmento(ClaseDeSegmento.RALENTI, 10, 20),
            ),
            cobertura=vacia,
            no_calculables=(),
            precedencia=(),
        )


# --------------------------------------------------------------------------- #
# 5. Un rol que falta se dice, no se aproxima
# --------------------------------------------------------------------------- #
def test_sin_mariposa_solo_el_arranque_se_puede_calcular(xp: XpVec) -> None:
    """Cuatro de las cinco clases necesitan `throttle_position`. Sin ese rol no se
    aproximan con la presión de colector ni con la carga: se declaran no
    calculables, con el nombre del rol que falta."""
    informe = _segmentar([250.0] * 20 + [950.0] * 20, None, xp)
    no_calculables = {nc.clase: nc for nc in informe.no_calculables}
    assert set(no_calculables) == {
        ClaseDeSegmento.WOT,
        ClaseDeSegmento.DECELERACION,
        ClaseDeSegmento.RALENTI,
        ClaseDeSegmento.CRUCERO,
    }
    for nc in no_calculables.values():
        assert nc.roles_faltantes == (ROL_MARIPOSA,)
        assert ROL_MARIPOSA in nc.motivo
    assert informe.es_calculable(ClaseDeSegmento.ARRANQUE)
    # Y lo que sí se puede calcular, se calcula: no se apaga la segmentación
    # entera porque falte un rol.
    assert ClaseDeSegmento.ARRANQUE in _clases(informe)


def test_sin_regimen_no_se_puede_calcular_nada_y_se_dice(xp: XpVec) -> None:
    """`engine_speed` lo necesitan las cinco clases y además define la rejilla de
    referencia. Sin él el informe sale vacío pero NO silencioso: cinco clases no
    calculables y cobertura sobre cero muestras.

    La diferencia importa: una lista vacía de segmentos con cobertura del 100 %
    diría «este log no tiene tiradas», y lo que pasa es que no se puede saber.
    """
    informe = segmentar(
        {ROL_MARIPOSA: _serie([0.9] * 20)},
        umbrales=_umbrales(),
        permanencia_base=_permanencia(),
        xp=xp,
    )
    assert informe.segmentos == ()
    assert {nc.clase for nc in informe.no_calculables} == set(ClaseDeSegmento)
    assert informe.cobertura.muestras == 0
    assert informe.cobertura.fraccion_cubierta == 0.0
    for nc in informe.no_calculables:
        assert ROL_REGIMEN in nc.roles_faltantes


def test_una_clase_no_calculable_no_es_una_clase_sin_segmentos(xp: XpVec) -> None:
    """La distinción, comprobada desde la API: `de_clase` vacío y `es_calculable`
    son dos respuestas distintas, y quien lea el informe tiene que poder
    separarlas."""
    informe = _segmentar([950.0] * 20, None, xp)
    assert informe.de_clase(ClaseDeSegmento.WOT) == ()
    assert not informe.es_calculable(ClaseDeSegmento.WOT)
    assert informe.de_clase(ClaseDeSegmento.ARRANQUE) == ()
    assert informe.es_calculable(ClaseDeSegmento.ARRANQUE)
    assert ClaseDeSegmento.WOT not in informe.segundos_por_clase()


# --------------------------------------------------------------------------- #
# 6. Multi-tasa: la rejilla es la del régimen y un hueco es un hueco
# --------------------------------------------------------------------------- #
def test_la_mariposa_lenta_se_alinea_a_la_rejilla_del_regimen(xp: XpVec) -> None:
    """Los canales de los logs reales van a 20, 10 y 5 Hz entrelazados (`docs/01`
    §1.6). La mariposa a 5 Hz se lleva a la rejilla del régimen por retención con
    límite de validez, no se remuestrea el régimen a la tasa lenta."""
    regimen = _serie([950.0] * 20)  # 20 Hz
    mariposa = Serie(t_ms=_t(5, dt_ms=200.0), v=Vec([0.0] * 5), clase=Clase.PUNTO)
    informe = segmentar(
        {ROL_REGIMEN: regimen, ROL_MARIPOSA: mariposa},
        umbrales=_umbrales(),
        permanencia_base=_permanencia(),
        xp=xp,
    )
    assert informe.cobertura.muestras == 20
    assert _clases(informe) == [ClaseDeSegmento.RALENTI]
    assert informe.segmentos[0].evento.n_muestras == 20


def test_un_canal_que_deja_de_emitir_no_se_retiene_sin_limite(xp: XpVec) -> None:
    """§4.5: fuera de la ventana de validez el resultado es hueco y no el último
    valor conocido. Aquí la mariposa deja de emitir a mitad del log, y las
    muestras posteriores salen SIN_DATOS en vez de heredar un ralentí que nadie
    ha visto."""
    regimen = _serie([950.0] * 40)
    mariposa = Serie(t_ms=_t(10, dt_ms=50.0), v=Vec([0.0] * 10), clase=Clase.PUNTO)
    informe = segmentar(
        {ROL_REGIMEN: regimen, ROL_MARIPOSA: mariposa},
        umbrales=_umbrales(),
        permanencia_base=_permanencia(),
        xp=xp,
    )
    assert informe.cobertura.sin_clasificar[MotivoSinClasificar.SIN_DATOS] > 0
    assert informe.cobertura.por_clase[ClaseDeSegmento.RALENTI] < 40


def test_un_hueco_no_apaga_una_clase_que_no_lo_necesita(xp: XpVec) -> None:
    """La lógica de tres valores de `Condicion`, vista desde aquí: el arranque
    solo necesita el régimen, así que un hueco en la mariposa no lo apaga. Con la
    validez estricta, un canal irrelevante ausente habría borrado una clase
    entera."""
    regimen = _serie([250.0] * 20)
    mariposa = Serie(t_ms=_t(2, dt_ms=50.0), v=Vec([0.0, 0.0]), clase=Clase.PUNTO)
    informe = segmentar(
        {ROL_REGIMEN: regimen, ROL_MARIPOSA: mariposa},
        umbrales=_umbrales(duraciones={ClaseDeSegmento.ARRANQUE: 0.5}),
        permanencia_base=_permanencia(),
        xp=xp,
    )
    assert _clases(informe) == [ClaseDeSegmento.ARRANQUE]
    assert informe.segmentos[0].evento.n_muestras == 20


# --------------------------------------------------------------------------- #
# 7. La clase de conversión (regla 4 de CLAUDE.md)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("clase", [Clase.INTERVALO, Clase.TASA, Clase.VARIANZA])
def test_una_serie_que_no_es_un_canal_se_rechaza(clase: Clase, xp: XpVec) -> None:
    """Un canal tal como sale del almacén es `PUNTO`. Aceptar una derivada ya
    hecha dejaría que se comparara con un umbral de régimen, que es la trampa del
    delta con otro disfraz."""
    with pytest.raises(ErrorDeSegmentacion, match="PUNTO"):
        segmentar(
            {ROL_REGIMEN: _serie([950.0] * 10, clase=clase)},
            umbrales=_umbrales(),
            permanencia_base=_permanencia(),
            xp=xp,
        )


def test_el_pico_del_segmento_lleva_su_clase_de_conversion(xp: XpVec) -> None:
    """`Evento.clase_valor` viaja hasta quien lo pinte: un régimen es un PUNTO y
    convertirlo como un intervalo sería la trampa del delta llegando por la puerta
    del panel de tiradas."""
    informe = _segmentar([950.0] * 20, [0.0] * 20, xp)
    for s in informe.segmentos:
        assert s.evento.clase_valor is Clase.PUNTO
        assert s.regimen_pico is not None


def test_el_extremo_del_pico_depende_de_la_clase() -> None:
    """El mínimo de una retención y el máximo de una tirada no son
    intercambiables: el «valor de pico» de una deceleración es hasta dónde
    bajó."""
    from dlv_core.primitivas import Extremo

    assert ClaseDeSegmento.WOT.extremo_del_pico is Extremo.MAXIMO
    assert ClaseDeSegmento.DECELERACION.extremo_del_pico is Extremo.MINIMO
    assert ClaseDeSegmento.RALENTI.extremo_del_pico is Extremo.MINIMO


# --------------------------------------------------------------------------- #
# 8. Los umbrales son configurables (regla 3 de CLAUDE.md)
# --------------------------------------------------------------------------- #
def test_ningun_parametro_numerico_de_la_api_tiene_valor_por_omision() -> None:
    """La decisión de diseño que hace improbable el defecto, no solo detectable.

    Un valor por omisión numérico en el código es una copia de
    `data/umbrales.toml` que se puede desincronizar sin que nada se ponga en
    rojo. Se comprueba sobre las firmas reales, igual que en `test_primitivas.py`
    y `test_plausibilidad.py`.
    """
    publicos = [UmbralesDeSegmentacion, Cobertura, Segmento, ClaseNoCalculable, segmentar]
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
    coherente consigo mismo— así que lo único que lo detecta es buscarlo. Sobre el
    AST y no sobre el texto, para no marcar los números que los comentarios y los
    docstrings citan explicando de dónde salen (la trampa que ya se pagó con el
    detector de ADR-009).
    """
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    seccion = bruto["segmentacion"]
    prohibidos = {float(v) for v in seccion.values() if isinstance(v, (int, float))}
    prohibidos.update(float(v) for v in seccion["duracion_minima_s"].values())
    # 0, 1, 2 y −1 no cuentan, con el mismo motivo que en `test_primitivas.py`: el
    # módulo los usa para contar y para desplazar un índice. Que una duración
    # mínima valga 2 s no puede prohibirle al módulo usar el número 2.
    prohibidos -= {0.0, 1.0, 2.0, -1.0}
    assert len(prohibidos) >= 10, "la sección [segmentacion] ha dejado de declarar sus umbrales"
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
    mapa = {"rpm_arranque_min": 50.0}
    with pytest.raises(ErrorDeSegmentacion, match="rpm_motor_en_marcha"):
        UmbralesDeSegmentacion.desde_mapa(mapa)


def test_falta_la_duracion_minima_de_una_clase_y_falla() -> None:
    """Una clase sin duración mínima tendría que traer un valor por omisión en el
    código, que es justo lo que no puede haber."""
    with pytest.raises(ErrorDeSegmentacion, match="crucero"):
        _umbrales(
            duracion_minima_s={
                c.value: 0.0 for c in ClaseDeSegmento if c is not ClaseDeSegmento.CRUCERO
            }
        )


def test_una_clase_inventada_en_el_fichero_no_se_ignora() -> None:
    """Un nombre de clase mal escrito dejaría la duración mínima de la clase real
    en su valor anterior y quien lo escribió creería que está aplicada."""
    with pytest.raises(ErrorDeSegmentacion, match="no existen"):
        _umbrales(
            duracion_minima_s={
                **dict.fromkeys((c.value for c in ClaseDeSegmento), 0.0),
                "plena_carga": 1.5,
            }
        )


def test_una_anulacion_mal_escrita_no_se_ignora_en_silencio() -> None:
    with pytest.raises(ErrorDeSegmentacion, match="desconocidas"):
        _umbrales().fusionar({"rpm_wot": 0.8})


def test_los_umbrales_por_perfil_ganan_a_los_del_fichero(xp: XpVec) -> None:
    """La precedencia de `data/umbrales.toml`: un equipo que considera tirada
    cualquier cosa por encima del 70 % de mariposa lo pone en su `.dlvprofile` y
    el módulo la aplica sin tocar el fichero por omisión."""
    n = 40
    regimen = _rampa(4000.0, 5000.0, n)
    mariposa = [0.72] * n
    del_fichero = _umbrales(duraciones={ClaseDeSegmento.WOT: 1.5})
    del_perfil = del_fichero.fusionar({"tps_wot_entrada": 0.70, "tps_wot_salida": 0.65})
    series = {ROL_REGIMEN: _serie(regimen), ROL_MARIPOSA: _serie(mariposa)}

    sin_anular = segmentar(series, umbrales=del_fichero, permanencia_base=_permanencia(), xp=xp)
    con_anular = segmentar(series, umbrales=del_perfil, permanencia_base=_permanencia(), xp=XpVec())
    assert sin_anular.de_clase(ClaseDeSegmento.WOT) == ()
    assert len(con_anular.de_clase(ClaseDeSegmento.WOT)) == 1


@pytest.mark.parametrize(
    ("anulacion", "trozo"),
    [
        ({"tps_cerrada_salida": 0.01}, "tps_cerrada_salida"),
        ({"tps_wot_salida": 0.9}, "tps_wot_salida"),
        ({"tps_wot_entrada": 0.01}, "tps_wot_entrada"),
        ({"rpm_motor_en_marcha": 10.0}, "rpm_motor_en_marcha"),
        ({"rpm_ralenti_max": 400.0}, "rpm_ralenti_max"),
        ({"rpm_decel_min": 900.0}, "rpm_decel_min"),
        ({"ventana_derivada_s": 0.0}, "ventana"),
        ({"rpm_arranque_min": -1.0}, "rpm_arranque_min"),
        ({"tps_wot_entrada": 80.0}, "FRACCIÓN"),
    ],
)
def test_una_configuracion_incoherente_se_rechaza_por_su_nombre(
    anulacion: dict[str, float], trozo: str
) -> None:
    """Los umbrales de esta sección no son independientes entre sí —el techo del
    ralentí es la salida de la histéresis de la deceleración, el umbral de WOT es
    el techo de la banda de crucero— así que una combinación incoherente abre un
    hueco o un solape. Se rechaza aquí, con el nombre de la clave, y no dentro de
    una primitiva con un mensaje sobre la histéresis."""
    with pytest.raises(ErrorDeSegmentacion, match=trozo):
        _umbrales(**anulacion)


# --------------------------------------------------------------------------- #
# 9. Contra la sección real de data/umbrales.toml
# --------------------------------------------------------------------------- #
def _seccion_real() -> dict[str, Any]:
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    return {
        **bruto["segmentacion"],
        "ventana_validez_ms": bruto["motor_de_deteccion"]["ventana_validez_ms"],
        "histeresis_relativa": bruto["general"]["histeresis_relativa"],
    }


def test_los_umbrales_reales_cargan_y_son_coherentes() -> None:
    """Que el fichero de datos y el módulo encajen, y las invariantes, no los
    valores.

    Las que se comprueban son las que atan la sección a §4.4 y a los otros
    umbrales del fichero: los tres números que §4.4 escribe literalmente, y que la
    duración mínima de una tirada siga siendo la que dice la especificación. Si
    alguna cambia, es una decisión del propietario y esta prueba la obliga a ser
    explícita.
    """
    umbrales = UmbralesDeSegmentacion.desde_mapa(_seccion_real())
    assert umbrales.rpm_motor_en_marcha == pytest.approx(500.0)  # §4.4
    assert umbrales.rpm_decel_min == pytest.approx(2000.0)  # §4.4
    assert umbrales.tps_wot_entrada == pytest.approx(0.80)  # §4.4
    assert umbrales.duracion_minima_s[ClaseDeSegmento.WOT] == pytest.approx(1.5)  # §4.4
    # La histéresis de la mariposa tiene que ser mayor que la cuantización del
    # canal (0,001 = 0,1 %, tipo Percentage de data/formats/haltech_nsp.toml) o no
    # filtraría nada.
    cuantizacion = 0.001
    assert umbrales.tps_wot_entrada - umbrales.tps_wot_salida > 10 * cuantizacion
    assert umbrales.tps_cerrada_salida - umbrales.tps_cerrada_entrada > 10 * cuantizacion
    # La ventana de la derivada tiene que cubrir el dt p99 del AutoLog (219 ms,
    # docs/01 §1.7) o la derivada sería un hueco en buena parte del log.
    dt_p99_ms = 219.0
    assert umbrales.ventana_derivada_s * 1000.0 > dt_p99_ms


def test_el_regimen_de_motor_en_marcha_es_el_mismo_que_el_de_d11() -> None:
    """La misma frontera física declarada dos veces en el mismo fichero: si se
    separan, la segmentación diría que el motor arranca mientras D11 ya lo
    considera en marcha y avisa por tensión baja."""
    with UMBRALES_TOML.open("rb") as fh:
        bruto = tomllib.load(fh)
    d11 = bruto["detectores"]["D11"]["condiciones"]["engine_speed_min"]
    assert float(bruto["segmentacion"]["rpm_motor_en_marcha"]) == pytest.approx(float(d11))


def test_la_configuracion_real_encuentra_la_tirada_del_autolog(xp: XpVec) -> None:
    """La cuarta tirada del AutoLog real, con los números medidos y los umbrales
    del fichero: 1,29 s de mariposa por encima del 80 % que la histéresis alarga a
    1,66 s y que así llega a la duración mínima de 1,5 s.

    Es la prueba que ata el valor de `tps_wot_salida` a su consecuencia: con la
    salida igual a la entrada, esta tirada NO se encuentra.
    """
    umbrales = UmbralesDeSegmentacion.desde_mapa(_seccion_real())
    # 1,29 s por encima del 80 % (a 20 Hz, 27 muestras) y 8 muestras más entre el
    # 75 % y el 80 %, que es lo que mide la tirada real con la histéresis.
    mariposa = [0.5] * 5 + [0.85] * 27 + [0.78] * 8 + [0.5] * 5
    n = len(mariposa)
    regimen = _rampa(4727.0, 5047.0, n)
    series = {ROL_REGIMEN: _serie(regimen), ROL_MARIPOSA: _serie(mariposa)}
    con = segmentar(series, umbrales=umbrales, permanencia_base=_permanencia(), xp=xp)
    assert len(con.de_clase(ClaseDeSegmento.WOT)) == 1
    assert con.de_clase(ClaseDeSegmento.WOT)[0].duracion_s >= 1.5

    desnudo = umbrales.fusionar({"tps_wot_salida": umbrales.tps_wot_entrada})
    sin = segmentar(series, umbrales=desnudo, permanencia_base=_permanencia(), xp=XpVec())
    assert sin.de_clase(ClaseDeSegmento.WOT) == ()


# --------------------------------------------------------------------------- #
# 10. ADR-009: ni un bucle por muestra
# --------------------------------------------------------------------------- #
def test_el_modulo_no_tiene_bucles_sobre_muestras() -> None:
    """Los `for` y los `while` del módulo, uno por uno, con lo que recorren.

    `tools/banco.py adr009` busca patrones de Pandas/Polars y no un `for`
    corriente, así que esta prueba mira los bucles de verdad: solo se admiten los
    que recorren clases, segmentos o claves de configuración, y ninguno puede
    iterar sobre un `range(len(...))` de una serie.
    """
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"), filename=str(MODULO))
    permitidos = {
        "_CLAVES_NO_NEGATIVAS",
        "_CLAVES_DE_FRACCION",
        "self.duracion_minima_s.items()",
        "(*self.por_clase.items(), *self.sin_clasificar.items())",
        "self.segmentos",
        "_orden_de_precedencia()",
        "exclusivas.items()",
        "exclusivas.values()",
        "candidatas.items()",
        "lista",
    }
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.For, ast.While)):
            recorrido = (
                ast.unparse(nodo.iter) if isinstance(nodo, ast.For) else ast.unparse(nodo.test)
            )
            assert recorrido in permitidos, (
                f"bucle en la línea {nodo.lineno} sobre {recorrido!r}: los bucles de este "
                "módulo solo pueden recorrer clases, segmentos o claves (ADR-009)"
            )
        if isinstance(nodo, ast.comprehension):
            texto = ast.unparse(nodo.iter)
            assert "range(" not in texto and ".v" not in texto, (
                f"comprensión sobre {texto!r}: recorrer las muestras de una serie en Python "
                "es lo que ADR-009 prohíbe, y una comprensión también es un bucle"
            )


def test_el_numero_de_operaciones_de_array_no_depende_de_las_muestras() -> None:
    """La comprobación por CONDUCTA, no por patrón: la misma segmentación sobre 60
    muestras y sobre 6 000 tiene que costar el mismo número de operaciones de
    array. Con un bucle por muestra escondido, subiría cien veces."""

    def coste(n: int) -> int:
        xp = XpVec()
        ralenti = n // 4
        # La pendiente del régimen se declara POR MUESTRA (25 rpm cada 50 ms, o sea
        # 500 rpm/s) y no de extremo a extremo: si la rampa fuera la misma para las
        # dos longitudes, la de 6 000 muestras tendría una pendiente cien veces
        # menor y no sería una tirada, y la prueba compararía dos cosas distintas.
        regimen = [950.0] * ralenti + [4000.0 + 25.0 * i for i in range(n - ralenti)]
        mariposa = [0.0] * ralenti + [0.9] * (n - ralenti)
        informe = _segmentar(regimen, mariposa, xp, duraciones={ClaseDeSegmento.WOT: 1.5})
        assert len(informe.segmentos) == 2
        return xp.total

    assert coste(60) == coste(6_000)


# --------------------------------------------------------------------------- #
# 11. Contrato de la salida
# --------------------------------------------------------------------------- #
def test_los_segundos_por_clase_cuadran_con_los_segmentos(xp: XpVec) -> None:
    """`segundos_por_clase` usa `primitivas.tiempo_acumulado` sobre los mismos
    eventos que están en `segmentos`, y no una suma propia: dos números de la
    misma pantalla que no cuadran son peores que cualquiera de los dos."""
    regimen = [950.0] * 20 + _rampa(2500.0, 4000.0, 20) + [950.0] * 20
    mariposa = [0.0] * 20 + [0.9] * 20 + [0.0] * 20
    informe = _segmentar(regimen, mariposa, xp)
    segundos = informe.segundos_por_clase()
    for clase, total in segundos.items():
        assert total == pytest.approx(sum(s.duracion_s for s in informe.de_clase(clase)))
    assert set(segundos) == set(ClaseDeSegmento)


def test_un_segmento_es_serializable_como_datos_planos(xp: XpVec) -> None:
    """El panel de tiradas (F3-17) y el informe de sesión (F4-11) lo cruzan por la
    frontera de `dlv-api`: nada dentro de un `Segmento` puede ser un array."""
    import dataclasses

    informe = _segmentar([950.0] * 20, [0.0] * 20, xp)
    plano = dataclasses.asdict(informe.segmentos[0])
    assert isinstance(plano["clase"], ClaseDeSegmento)
    assert all(isinstance(v, (int, float, str, Clase)) for v in plano["evento"].values())


def test_una_serie_vacia_no_revienta(xp: XpVec) -> None:
    """Un log sin ninguna muestra del régimen no es un error: es un log sin nada
    que segmentar.

    Con la mariposa AUSENTE, no con la mariposa vacía: una serie de origen de cero
    muestras hace fallar `primitivas.alinear` con un `TypeError`, porque
    `expresiones.alinear_por_retencion` devuelve listas de Python en ese camino y no
    arrays del tipo vectorial. Está anotado en el informe de la tarea como defecto
    de F3-06/F3-18 -- pasa igual con NumPy y no se arregla desde aquí.
    """
    informe = segmentar(
        {ROL_REGIMEN: _serie([])},
        umbrales=_umbrales(),
        permanencia_base=_permanencia(),
        xp=xp,
    )
    assert informe.segmentos == ()
    assert informe.cobertura.muestras == 0
