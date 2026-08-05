"""Pruebas del modelo de tramos y del eje X virtual (tarea F2-01).

QUÉ PROTEGE ESTA SUITE
======================
Todas las pruebas de aquí atacan errores que **no se ven en pantalla**, que es
la razón de ser de la tarea: hoy un hueco de adquisición se dibuja como una
recta perfectamente creíble.

1. **Ninguna muestra se pierde al partir.** Un hueco entre las dos PRIMERAS
   muestras (o entre las dos ÚLTIMAS) deja un tramo de una sola muestra. Un
   `+1` mal puesto lo descartaría, y descartar una muestra de los extremos no
   rompe ninguna otra prueba: la suma de `n_muestras` es la red.
2. **Un tramo de una muestra no es un tramo dibujable.** `LINE_STRIP` con un
   vértice no pinta nada; `es_punto` existe para que quien dibuja lo sepa.
3. **Ningún hueco puede quedar invisible.** En las tres políticas, la anchura
   virtual de un hueco es > 0, y las políticas que comprimen exigen un número
   positivo en vez de aceptar 0 y volver a pegar los dos bordes.
4. **Dentro de un tramo la pendiente es 1.** Comprimir un hueco no puede
   deformar los datos que lo rodean, o las pendientes leídas en pantalla
   dejarían de ser las reales.
5. **La ida y vuelta píxel -> instante es exacta en los bordes del hueco**, que
   es justo donde el cursor y el doble cursor se equivocarían de instante.
6. **Dos segmentos que se solapan no rompen la monotonía del eje**: la vista
   paralela de §3.6 es exactamente ese caso, y un eje no monótono no se puede
   invertir.
7. **Contra logs reales** (`samples/real/`): el AutoLog tiene huecos por encima
   del umbral (docs/01 §1.7, dt máx 499 ms frente a 54 de mediana), así que hoy
   se está dibujando con rectas que no están en los datos; los dos logs
   internos son de tasa fija y deben dar un único tramo por grupo, es decir,
   ningún corte inventado.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dlv_core.almacen import ChannelSeries, Storage, construir_desde_polars
from dlv_core.eje_virtual import (
    EjeVirtual,
    MotivoRuptura,
    PoliticaHueco,
    Tramo,
    Zona,
    construir_eje_virtual,
    desplazar_tramos,
    partir_en_tramos,
    partir_serie_en_tramos,
    rupturas_entre,
)
from dlv_core.formatos.cuerpo import COLUMNA_MARCA, columna_polars, parsear_cuerpo
from dlv_core.formatos.haltech import Cabecera, Descriptor, cargar_descriptor, parsear_cabecera
from dlv_core.huecos import detectar_huecos
from dlv_core.roles import ChannelKey
from dlv_core.unidades import Afin

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
REALES = RAIZ / "samples" / "real"

MINUTO_MS = 60_000


@pytest.fixture(scope="module")
def desc() -> Descriptor:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return cargar_descriptor(fh)


def _serie(t: np.ndarray) -> ChannelSeries:
    """`ChannelSeries` mínima: aquí solo importa `t`."""
    return ChannelSeries(
        key=ChannelKey(rol=None, formato=None, id_nativo="1", nombre_normalizado=None),
        role=None,
        t=t,
        v=np.zeros(len(t), dtype=np.int32),
        storage=Storage.INT32_SCALED,
        to_canon=Afin(1.0),
        dimension=None,
    )


def _tramo(t_inicio: int, t_fin: int, *, id_segmento: str = "", orden: int = 0) -> Tramo:
    """Un tramo construido a mano por sus instantes; los índices de muestra no
    importan en las pruebas del eje, solo que sean una rebanada válida."""
    return Tramo(
        id_segmento=id_segmento,
        orden=orden,
        inicio=0,
        fin=2,
        t_inicio=t_inicio,
        t_fin=t_fin,
    )


# --------------------------------------------------------------------------- #
# partir_en_tramos
# --------------------------------------------------------------------------- #
def test_una_serie_continua_es_un_solo_tramo() -> None:
    t = np.array([0, 100, 200, 300], dtype=np.uint32)
    (tramo,) = partir_en_tramos(t)

    assert (tramo.inicio, tramo.fin) == (0, 4)
    assert (tramo.t_inicio, tramo.t_fin) == (0, 300)
    assert tramo.n_muestras == 4
    assert tramo.duracion_ms == 300
    assert not tramo.es_punto


def test_serie_vacia_no_da_ningun_tramo() -> None:
    assert partir_en_tramos(np.array([], dtype=np.uint32)) == []


def test_una_sola_muestra_da_un_tramo_punto() -> None:
    (tramo,) = partir_en_tramos(np.array([7], dtype=np.uint32))

    assert tramo.n_muestras == 1
    assert tramo.duracion_ms == 0
    assert tramo.es_punto


def test_un_hueco_parte_la_serie_en_dos_sin_perder_ni_repetir_muestras() -> None:
    t = np.array([0, 100, 200, 2000, 2100], dtype=np.uint32)
    primero, segundo = partir_en_tramos(t, periodo_ms=100.0)

    assert (primero.inicio, primero.fin) == (0, 3)
    assert (segundo.inicio, segundo.fin) == (3, 5)
    assert (primero.t_inicio, primero.t_fin) == (0, 200)
    assert (segundo.t_inicio, segundo.t_fin) == (2000, 2100)
    assert primero.n_muestras + segundo.n_muestras == t.size
    assert [tr.orden for tr in (primero, segundo)] == [0, 1]


def test_un_hueco_al_principio_no_descarta_la_primera_muestra() -> None:
    """El `+1` del corte se equivoca en silencio justo aquí: el primer tramo
    tiene una sola muestra, y perderla no rompe ninguna otra prueba."""
    t = np.array([0, 100_000, 100_050, 100_100], dtype=np.uint32)
    primero, segundo = partir_en_tramos(t, periodo_ms=50.0)

    assert (primero.inicio, primero.fin) == (0, 1)
    assert primero.es_punto
    assert primero.t_inicio == primero.t_fin == 0
    assert (segundo.inicio, segundo.fin) == (1, 4)
    assert primero.n_muestras + segundo.n_muestras == t.size


def test_un_hueco_al_final_no_descarta_la_ultima_muestra() -> None:
    t = np.array([0, 50, 100, 100_000], dtype=np.uint32)
    primero, segundo = partir_en_tramos(t, periodo_ms=50.0)

    assert (primero.inicio, primero.fin) == (0, 3)
    assert (segundo.inicio, segundo.fin) == (3, 4)
    assert segundo.es_punto
    assert segundo.t_inicio == segundo.t_fin == 100_000
    assert primero.n_muestras + segundo.n_muestras == t.size


def test_varios_huecos_dan_tramos_contiguos_que_cubren_toda_la_serie() -> None:
    t = np.array([0, 100, 200, 2000, 2100, 2200, 9000], dtype=np.uint32)
    tramos = partir_en_tramos(t, periodo_ms=100.0)

    assert [(tr.inicio, tr.fin) for tr in tramos] == [(0, 3), (3, 6), (6, 7)]
    assert sum(tr.n_muestras for tr in tramos) == t.size
    # Contiguos: el fin de cada uno es el inicio del siguiente, sin solapes.
    assert all(a.fin == b.inicio for a, b in zip(tramos[:-1], tramos[1:], strict=True))


def test_un_retroceso_tambien_parte_aunque_t_sea_uint32() -> None:
    """La trampa del `uint32` (F1-05): `100 - 200` sin signo no da -100,
    envuelve a 4 294 967 196. Si el corte se calculara sin castear, este
    retroceso se leería como un hueco gigante --- y partiría igual, por
    casualidad --- pero el tramo resultante tendría `t_fin < t_inicio` y
    `Tramo` lo rechazaría. Que esto pase es la prueba de que se castea."""
    t = np.array([0, 100, 200, 100, 200, 300], dtype=np.uint32)
    primero, segundo = partir_en_tramos(t)

    assert (primero.inicio, primero.fin) == (0, 3)
    assert (segundo.inicio, segundo.fin) == (3, 6)
    assert segundo.t_inicio == 100
    assert all(tr.t_fin >= tr.t_inicio for tr in (primero, segundo))


def test_el_umbral_de_corte_es_el_de_f1_08_y_sigue_siendo_configurable() -> None:
    """No se reimplementa el criterio: un `Δt` que `detectar_huecos` no
    considera hueco tampoco parte el tramo, y al revés."""
    t = np.array([0, 100, 450], dtype=np.uint32)  # último Δt: 350 ms

    assert detectar_huecos(t, periodo_ms=100.0) != []
    assert len(partir_en_tramos(t, periodo_ms=100.0)) == 2
    assert detectar_huecos(t, periodo_ms=200.0) == []
    assert len(partir_en_tramos(t, periodo_ms=200.0)) == 1
    assert len(partir_en_tramos(t, periodo_ms=100.0, factor_umbral=10.0)) == 1


def test_partir_serie_en_tramos_delega_en_t() -> None:
    serie = _serie(np.array([0, 100, 200, 2000, 2100], dtype=np.uint32))
    esperado = partir_en_tramos(serie.t, periodo_ms=100.0, id_segmento="log-a")
    assert partir_serie_en_tramos(serie, periodo_ms=100.0, id_segmento="log-a") == esperado


def test_los_tramos_llevan_el_id_de_su_segmento() -> None:
    t = np.array([0, 100, 200, 2000, 2100], dtype=np.uint32)
    tramos = partir_en_tramos(t, periodo_ms=100.0, id_segmento="Log2768")
    assert {tr.id_segmento for tr in tramos} == {"Log2768"}


def test_un_tramo_sin_muestras_o_que_retrocede_es_un_error() -> None:
    with pytest.raises(ValueError, match="al menos una muestra"):
        Tramo(id_segmento="", orden=0, inicio=3, fin=3, t_inicio=0, t_fin=0)
    with pytest.raises(ValueError, match="retroceder"):
        Tramo(id_segmento="", orden=0, inicio=0, fin=2, t_inicio=100, t_fin=50)


# --------------------------------------------------------------------------- #
# rupturas_entre
# --------------------------------------------------------------------------- #
def test_la_ruptura_entre_dos_tramos_del_mismo_log_es_un_hueco() -> None:
    tramos = partir_en_tramos(np.array([0, 100, 200, 2000, 2100], dtype=np.uint32), periodo_ms=100.0)
    (ruptura,) = rupturas_entre(tramos)

    assert ruptura.motivo is MotivoRuptura.HUECO
    assert (ruptura.anterior, ruptura.siguiente) == (0, 1)
    assert (ruptura.t_fin_anterior, ruptura.t_inicio_siguiente) == (200, 2000)
    assert ruptura.duracion_ms == 1800


def test_la_ruptura_de_un_retroceso_tiene_duracion_negativa() -> None:
    tramos = partir_en_tramos(np.array([0, 100, 200, 100, 200], dtype=np.uint32))
    (ruptura,) = rupturas_entre(tramos)

    assert ruptura.motivo is MotivoRuptura.RETROCESO
    assert ruptura.duracion_ms == -100


def test_dos_logs_que_se_tocan_siguen_teniendo_frontera() -> None:
    """§3.6: «las fronteras se marcan siempre, no como opción». El caso
    peligroso es 2768 + 2769 concatenados, donde el segundo empieza justo
    donde acaba el primero y nada delataría la unión."""
    tramos = [_tramo(0, 1000, id_segmento="Log2768"), _tramo(1000, 2000, id_segmento="Log2769")]
    (ruptura,) = rupturas_entre(tramos)

    assert ruptura.motivo is MotivoRuptura.FRONTERA_SEGMENTO
    assert ruptura.duracion_ms == 0


def test_la_frontera_de_segmento_gana_al_solape() -> None:
    """Dos logs solapados en el tiempo no se unen con una línea por mucho que
    el segundo empiece «antes» de que acabe el primero: eso sería un retroceso
    dentro de un log, no entre dos."""
    tramos = [_tramo(0, 1000, id_segmento="a"), _tramo(500, 1500, id_segmento="b")]
    (ruptura,) = rupturas_entre(tramos)

    assert ruptura.motivo is MotivoRuptura.FRONTERA_SEGMENTO


def test_un_solo_tramo_no_tiene_rupturas() -> None:
    assert rupturas_entre([_tramo(0, 1000)]) == []


# --------------------------------------------------------------------------- #
# desplazar_tramos
# --------------------------------------------------------------------------- #
def test_desplazar_mueve_los_instantes_y_no_los_indices() -> None:
    original = partir_en_tramos(np.array([0, 100, 200, 2000], dtype=np.uint32), periodo_ms=100.0)
    movidos = desplazar_tramos(original, -50_000)

    assert [(tr.inicio, tr.fin) for tr in movidos] == [(a.inicio, a.fin) for a in original]
    assert [tr.t_inicio for tr in movidos] == [a.t_inicio - 50_000 for a in original]
    assert [tr.duracion_ms for tr in movidos] == [a.duracion_ms for a in original]


# --------------------------------------------------------------------------- #
# EjeVirtual: geometría
# --------------------------------------------------------------------------- #
def test_sin_tramos_no_hay_eje() -> None:
    with pytest.raises(ValueError, match="sin ningún tramo"):
        construir_eje_virtual([])


def test_la_politica_real_es_la_identidad_desplazada_al_origen() -> None:
    tramos = [_tramo(10_000, 20_000), _tramo(80_000, 90_000)]
    eje = construir_eje_virtual(tramos)

    t = np.array([10_000, 15_000, 20_000, 80_000, 90_000], dtype=np.float64)
    assert eje.a_x(t) == pytest.approx(t - 10_000)
    assert eje.x_total == pytest.approx(80_000)


def test_un_hueco_de_40_minutos_se_come_la_pantalla_si_no_se_comprime() -> None:
    """La motivación de `PoliticaHueco`, escrita como número: dos tiradas de
    10 s separadas por 40 min de pausa dejan el 99 % del eje en blanco."""
    tramos = [_tramo(0, 10_000), _tramo(40 * MINUTO_MS + 10_000, 40 * MINUTO_MS + 20_000)]
    eje = construir_eje_virtual(tramos)

    (hueco,) = eje.huecos
    assert hueco.ancho_x / eje.x_total > 0.9
    assert not hueco.comprimido


def test_el_tope_recorta_el_hueco_grande_y_deja_intacto_el_pequeno() -> None:
    tramos = [_tramo(0, 10_000), _tramo(20_000, 30_000), _tramo(40 * MINUTO_MS, 40 * MINUTO_MS)]
    eje = construir_eje_virtual(tramos, politica=PoliticaHueco.TOPE, tope_hueco_ms=5_000.0)

    pequeno, grande = eje.huecos
    assert pequeno.duracion_ms == 10_000
    assert pequeno.ancho_x == pytest.approx(5_000.0)  # recortado al tope
    assert grande.duracion_ms == 40 * MINUTO_MS - 30_000
    assert grande.ancho_x == pytest.approx(5_000.0)
    assert grande.comprimido


def test_el_tope_no_estira_un_hueco_mas_pequeno_que_el_tope() -> None:
    tramos = [_tramo(0, 10_000), _tramo(11_000, 20_000)]
    eje = construir_eje_virtual(tramos, politica=PoliticaHueco.TOPE, tope_hueco_ms=5_000.0)

    (hueco,) = eje.huecos
    assert hueco.ancho_x == pytest.approx(1_000.0)
    assert not hueco.comprimido


def test_la_politica_fija_da_la_misma_anchura_a_huecos_muy_distintos() -> None:
    tramos = [_tramo(0, 1_000), _tramo(2_000, 3_000), _tramo(40 * MINUTO_MS, 40 * MINUTO_MS + 1000)]
    eje = construir_eje_virtual(tramos, politica=PoliticaHueco.FIJO, ancho_hueco_ms=500.0)

    assert [h.ancho_x for h in eje.huecos] == pytest.approx([500.0, 500.0])
    # 3 tramos de 1 s + 2 huecos de 0,5 s
    assert eje.x_total == pytest.approx(3 * 1_000.0 + 2 * 500.0)


def test_comprimir_un_hueco_no_deforma_los_tramos() -> None:
    """La pendiente dentro de un tramo es 1 en todas las políticas: un
    segundo de datos mide lo mismo antes y después de un hueco comprimido, o
    las pendientes leídas en pantalla dejarían de ser las reales."""
    tramos = [_tramo(0, 10_000), _tramo(40 * MINUTO_MS, 40 * MINUTO_MS + 10_000)]
    eje = construir_eje_virtual(tramos, politica=PoliticaHueco.FIJO, ancho_hueco_ms=100.0)

    for tramo in eje.tramos:
        x0, x1 = eje.rango_x(tramo)
        assert x1 - x0 == pytest.approx(float(tramo.duracion_ms))


@pytest.mark.parametrize(
    ("politica", "kwargs"),
    [
        (PoliticaHueco.REAL, {}),
        (PoliticaHueco.TOPE, {"tope_hueco_ms": 1.0}),
        (PoliticaHueco.FIJO, {"ancho_hueco_ms": 1.0}),
    ],
)
def test_ningun_hueco_puede_tener_anchura_cero(
    politica: PoliticaHueco, kwargs: dict[str, float]
) -> None:
    """La invariante de la tarea: «lo que no puede pasar es que un hueco quede
    invisible». Un hueco de anchura 0 volvería a pegar los dos bordes."""
    tramos = [_tramo(0, 1_000), _tramo(1_001, 2_000), _tramo(40 * MINUTO_MS, 40 * MINUTO_MS)]
    eje = construir_eje_virtual(tramos, politica=politica, **kwargs)

    assert len(eje.huecos) == 2
    assert all(h.ancho_x > 0.0 for h in eje.huecos)
    assert all(h.x_fin > h.x_inicio for h in eje.huecos)


@pytest.mark.parametrize(
    ("politica", "kwargs"),
    [
        (PoliticaHueco.TOPE, {}),
        (PoliticaHueco.TOPE, {"tope_hueco_ms": 0.0}),
        (PoliticaHueco.TOPE, {"tope_hueco_ms": -1.0}),
        (PoliticaHueco.FIJO, {}),
        (PoliticaHueco.FIJO, {"ancho_hueco_ms": 0.0}),
        (PoliticaHueco.FIJO, {"ancho_hueco_ms": -1.0}),
    ],
)
def test_comprimir_a_cero_o_sin_decir_cuanto_es_un_error(
    politica: PoliticaHueco, kwargs: dict[str, float]
) -> None:
    tramos = [_tramo(0, 1_000), _tramo(2_000, 3_000)]
    with pytest.raises(ValueError):
        construir_eje_virtual(tramos, politica=politica, **kwargs)


def test_dos_tramos_que_se_tocan_no_generan_hueco() -> None:
    """Entre `t_fin == t_inicio` no hay ni un milisegundo sin datos: enseñar
    un hueco ahí sería inventarse tiempo muerto. Que no se puedan dibujar
    unidos lo dice la lista de tramos, que sigue teniendo dos."""
    eje = construir_eje_virtual(
        [_tramo(0, 1_000, id_segmento="a"), _tramo(1_000, 2_000, id_segmento="b")]
    )

    assert eje.huecos == ()
    assert len(eje.tramos) == 2
    assert eje.x_total == pytest.approx(2_000.0)


# --------------------------------------------------------------------------- #
# EjeVirtual: solape (vista paralela)
# --------------------------------------------------------------------------- #
def test_dos_segmentos_solapados_dan_un_eje_monotono_sin_hueco_falso() -> None:
    """La vista paralela de §3.6 es exactamente este caso: N logs sobre el
    mismo eje, con sus rangos de tiempo pisándose. Si cada tramo reclamara su
    propio trozo de coordenada, el eje no sería invertible y el cursor
    devolvería instantes imposibles."""
    tramos = [_tramo(0, 60_000, id_segmento="a"), _tramo(30_000, 90_000, id_segmento="b")]
    eje = construir_eje_virtual(tramos)

    assert eje.huecos == ()
    assert eje.t_minimo == 0
    assert eje.t_maximo == 90_000
    assert eje.x_total == pytest.approx(90_000.0)

    t = np.linspace(0.0, 90_000.0, 1000)
    x = eje.a_x(t)
    assert np.all(np.diff(x) > 0.0)
    assert eje.a_t(x) == pytest.approx(t, abs=1e-6)


def test_el_solape_no_funde_los_tramos_solo_la_cobertura() -> None:
    tramos = [_tramo(0, 60_000, id_segmento="a"), _tramo(30_000, 90_000, id_segmento="b")]
    eje = construir_eje_virtual(tramos)

    assert len(eje.tramos) == 2  # dos LINE_STRIP, no uno
    assert eje.t_cobertura_inicio.tolist() == [0]  # una sola cobertura
    assert eje.t_cobertura_fin.tolist() == [90_000]
    assert eje.tramos_en(45_000.0) == [0, 1]  # los dos logs cubren ese instante


def test_los_tramos_del_eje_salen_ordenados_por_instante() -> None:
    tarde = _tramo(50_000, 60_000, id_segmento="tarde")
    pronto = _tramo(0, 10_000, id_segmento="pronto")
    eje = construir_eje_virtual([tarde, pronto])

    assert [tr.id_segmento for tr in eje.tramos] == ["pronto", "tarde"]


# --------------------------------------------------------------------------- #
# EjeVirtual: ida y vuelta (cursor y doble cursor)
# --------------------------------------------------------------------------- #
def _eje_con_hueco_comprimido() -> EjeVirtual:
    """Dos tiradas de 10 s separadas por 40 minutos, con el hueco recortado a
    2 s. Es el caso que motiva la tarea."""
    tramos = [
        _tramo(0, 10_000, id_segmento="a"),
        _tramo(40 * MINUTO_MS, 40 * MINUTO_MS + 10_000, id_segmento="a", orden=1),
    ]
    return construir_eje_virtual(tramos, politica=PoliticaHueco.TOPE, tope_hueco_ms=2_000.0)


def test_los_bordes_del_hueco_vuelven_al_instante_real_exacto() -> None:
    """El caso que el cursor se come en silencio: el píxel de la izquierda del
    hueco es el ÚLTIMO instante con datos, y el de la derecha es el primero de
    la reanudación, 40 minutos después. Un error aquí no se ve: los dos
    píxeles están pegados."""
    eje = _eje_con_hueco_comprimido()
    (hueco,) = eje.huecos

    assert eje.instante_de_x(hueco.x_inicio) == pytest.approx(10_000.0)
    assert eje.instante_de_x(hueco.x_fin) == pytest.approx(40 * MINUTO_MS)
    assert eje.x_de_instante(10_000.0) == pytest.approx(hueco.x_inicio)
    assert eje.x_de_instante(float(40 * MINUTO_MS)) == pytest.approx(hueco.x_fin)
    assert hueco.x_fin - hueco.x_inicio == pytest.approx(2_000.0)


def test_los_bordes_del_hueco_pertenecen_a_los_tramos_no_al_hueco() -> None:
    eje = _eje_con_hueco_comprimido()
    (hueco,) = eje.huecos

    assert eje.posicion(hueco.x_inicio).zona is Zona.TRAMO
    assert eje.posicion(hueco.x_fin).zona is Zona.TRAMO
    assert eje.posicion(hueco.x_inicio).indice_cobertura == 0
    assert eje.posicion(hueco.x_fin).indice_cobertura == 1


def test_en_mitad_del_hueco_el_cursor_sabe_que_no_hay_datos() -> None:
    eje = _eje_con_hueco_comprimido()
    (hueco,) = eje.huecos
    medio = (hueco.x_inicio + hueco.x_fin) / 2.0

    posicion = eje.posicion(medio)
    assert posicion.zona is Zona.HUECO
    assert posicion.indice_cobertura == 0  # el hueco 0
    assert 10_000.0 < posicion.t < float(40 * MINUTO_MS)
    assert eje.tramos_en(posicion.t) == []  # y no hay ningún tramo que consultar


def test_fuera_de_los_datos_se_extrapola_con_pendiente_uno() -> None:
    """`numpy.interp` aplastaría contra el extremo, y todas las muestras
    anteriores al primer dato caerían sobre el mismo píxel: una barra vertical
    con aspecto de dato. Extrapolar mantiene además la ida y vuelta."""
    eje = _eje_con_hueco_comprimido()

    assert eje.x_de_instante(-5_000.0) == pytest.approx(-5_000.0)
    assert eje.instante_de_x(-5_000.0) == pytest.approx(-5_000.0)
    assert eje.posicion(-1.0).zona is Zona.FUERA
    assert eje.posicion(-1.0).indice_cobertura is None
    assert eje.posicion(eje.x_total + 1.0).zona is Zona.FUERA


def test_ida_y_vuelta_exacta_sobre_todo_el_eje() -> None:
    eje = _eje_con_hueco_comprimido()
    x = np.linspace(-1_000.0, eje.x_total + 1_000.0, 5_000)

    assert eje.a_x(eje.a_t(x)) == pytest.approx(x, abs=1e-6)


def test_un_tramo_de_una_muestra_sobrevive_al_eje() -> None:
    """El tramo-punto de `test_un_hueco_al_final_...`, ahora en el eje: ocupa
    anchura 0 (no hay duración que repartir) pero sigue teniendo su sitio, y
    la ida y vuelta en él es exacta. Quien dibuje tiene que pintarlo como un
    punto: un `LINE_STRIP` de un vértice no pinta nada."""
    tramos = partir_en_tramos(np.array([0, 50, 100, 100_000], dtype=np.uint32), periodo_ms=50.0)
    eje = construir_eje_virtual(tramos, politica=PoliticaHueco.FIJO, ancho_hueco_ms=1_000.0)

    punto = eje.tramos[1]
    assert punto.es_punto
    assert eje.rango_x(punto) == pytest.approx((1_100.0, 1_100.0))
    assert eje.x_total == pytest.approx(1_100.0)
    assert eje.posicion(1_100.0).zona is Zona.TRAMO
    assert eje.instante_de_x(1_100.0) == pytest.approx(100_000.0)
    assert eje.posicion(600.0).zona is Zona.HUECO


def test_un_eje_de_un_solo_punto_no_revienta() -> None:
    """Caso degenerado real: un canal que solo se activó una vez. `x_total`
    es 0 y quien escale por él tiene que saberlo; el eje, al menos, no
    miente."""
    eje = construir_eje_virtual([Tramo("", 0, 0, 1, 500, 500)])

    assert eje.x_total == pytest.approx(0.0)
    assert eje.instante_de_x(0.0) == pytest.approx(500.0)
    assert eje.posicion(0.0).zona is Zona.TRAMO


# --------------------------------------------------------------------------- #
# Contra logs reales (samples/real/)
# --------------------------------------------------------------------------- #
def _construir_series(desc: Descriptor, ruta: Path) -> list[ChannelSeries]:
    datos = ruta.read_bytes()
    cab: Cabecera = parsear_cabecera(datos, desc)
    df = parsear_cuerpo(datos, cab)
    storage = {columna_polars(c.columna): Storage.INT32_SCALED for c in cab.canales}
    return construir_desde_polars(
        df, cab, columna_tiempo=COLUMNA_MARCA, storage_por_columna=storage
    )


def test_el_autolog_real_no_es_una_sola_linea(desc: Descriptor) -> None:
    """docs/01 §1.7: dt máximo 499 ms frente a 54 ms de mediana. Con el umbral
    por omisión hay huecos, así que el AutoLog se está dibujando HOY con
    rectas que no están en los datos. El número de tramos es el de huecos más
    uno, y entre todos cubren la serie entera."""
    series = _construir_series(desc, REALES / "AutoLog_20260729_1830.csv")
    (t,) = {id(s.t): s.t for s in series}.values()

    tramos = partir_en_tramos(t, id_segmento="AutoLog")
    huecos = detectar_huecos(t)

    assert len(tramos) == len(huecos) + 1 > 1
    assert sum(tr.n_muestras for tr in tramos) == t.size
    assert all(r.motivo is MotivoRuptura.HUECO for r in rupturas_entre(tramos))


def test_el_eje_del_autolog_real_es_invertible_en_todos_sus_huecos(desc: Descriptor) -> None:
    series = _construir_series(desc, REALES / "AutoLog_20260729_1830.csv")
    (t,) = {id(s.t): s.t for s in series}.values()
    eje = construir_eje_virtual(
        partir_en_tramos(t, id_segmento="AutoLog"),
        politica=PoliticaHueco.FIJO,
        ancho_hueco_ms=200.0,
    )

    assert len(eje.huecos) > 0
    assert all(h.ancho_x == pytest.approx(200.0) for h in eje.huecos)

    x = eje.a_x(t.astype(np.int64))
    assert np.all(np.diff(x) >= 0.0)
    assert eje.a_t(x) == pytest.approx(t.astype(np.float64), abs=1e-6)
    # Ninguna muestra real cae DENTRO de un hueco: los huecos son, por
    # construcción, exactamente el tiempo donde no hay nada que dibujar.
    for hueco in eje.huecos:
        assert not np.any((x > hueco.x_inicio) & (x < hueco.x_fin))


@pytest.mark.parametrize("nombre", ["20260729_1859_Log2768.csv", "20260729_1859_Log2769.csv"])
def test_los_logs_internos_de_tasa_fija_dan_un_unico_tramo_por_grupo(
    desc: Descriptor, nombre: str
) -> None:
    """docs/01 §1.6: tasas fijas sin huecos ni retrocesos. Ningún corte
    inventado: un solo tramo por grupo de muestreo, y por tanto ninguna
    frontera falsa que romper la línea sin motivo."""
    series = _construir_series(desc, REALES / nombre)
    grupos_t = {id(s.t): s.t for s in series}
    assert len(grupos_t) == 3  # G0/G1/G2 de §1.6

    for t in grupos_t.values():
        (tramo,) = partir_en_tramos(t, id_segmento=nombre)
        assert tramo.n_muestras == t.size


def test_2768_y_2769_concatenados_conservan_su_frontera(desc: Descriptor) -> None:
    """El hito M2 pide «2768 + 2769 concatenados». Los dos logs empiezan en el
    mismo instante relativo, así que sin desplazar el segundo se solaparían
    enteros: se coloca detrás, y la frontera se marca aunque los dos tramos se
    toquen exactamente."""

    def grupo_mayor(nombre: str) -> np.ndarray:
        grupos = {id(s.t): s.t for s in _construir_series(desc, REALES / nombre)}
        return max(grupos.values(), key=len)

    t_2768 = grupo_mayor("20260729_1859_Log2768.csv")
    t_2769 = grupo_mayor("20260729_1859_Log2769.csv")

    tramos_2768 = partir_en_tramos(t_2768, id_segmento="Log2768")
    desfase = int(tramos_2768[-1].t_fin)
    tramos_2769 = desplazar_tramos(partir_en_tramos(t_2769, id_segmento="Log2769"), desfase)

    tramos = tramos_2768 + tramos_2769
    (ruptura,) = rupturas_entre(tramos)
    assert ruptura.motivo is MotivoRuptura.FRONTERA_SEGMENTO
    assert ruptura.duracion_ms == 0

    eje = construir_eje_virtual(tramos)
    assert eje.huecos == ()  # no hay tiempo muerto: se tocan
    assert len(eje.tramos) == 2  # pero siguen siendo dos LINE_STRIP
    assert eje.x_total == pytest.approx(float(tramos_2769[-1].t_fin))
