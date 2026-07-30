"""Pruebas de la reconciliación de reloj (tarea F1-04).

Lo que hay que proteger, en orden de gravedad si se rompe:

1. **La época ficticia gana a la comprobación de 12 h.** Es la trampa real de
   `docs/01` §1.5: los dos logs internos declaran `19800101 01:01:01` y empiezan
   en `01:01:01.005`, así que el desfase sale casi cero y una implementación que
   compruebe el desfase primero los marcaría como fiables. Entonces las dos
   tiradas se superpondrían en el mismo instante de 1980 y el usuario compararía
   dos logs distintos creyendo que son simultáneos.
2. **La hora del día viene de la primera fila, nunca de la cabecera** (§1.4).
   Confundirlas desplaza el AutoLog real 12 h.
3. **El cruce de medianoche** no puede dejar el eje X yendo hacia atrás, y un
   retroceso pequeño no es un cruce: se cuenta y se avisa, no se «arregla».

Las pruebas del desenrollado usan `XpLista`, una implementación de biblioteca
estándar del protocolo `Vectorial`. No es un simulacro: ejercita exactamente el
mismo código de `desenrollar_medianoche` que correrá con NumPy, cuyas cuatro
funciones son las que el protocolo declara. Es lo que permite tener esta parte
probada mientras F0-01 sigue bloqueada sin acceso a PyPI.
"""

from __future__ import annotations

import tomllib
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from dlv_core.formatos.haltech import cargar_descriptor, parsear_cabecera, sondear_formato
from dlv_core.informes import Aviso
from dlv_core.reloj import (
    SEGUNDOS_POR_DIA,
    Desenrollado,
    ErrorDeReloj,
    OrdenTemporal,
    PoliticaReloj,
    Reconciliacion,
    desenrollar_medianoche,
    parsear_fecha_hora,
    parsear_marca_de_fila,
    reconciliar,
)
from dlv_core.tiempo import FiabilidadReloj, ModoDesfase

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
REALES = RAIZ / "samples" / "real"


# --------------------------------------------------------------------------- #
# Implementación de `Vectorial` con biblioteca estándar
# --------------------------------------------------------------------------- #
class ListaV(list[float]):
    """Lista con la aritmética elemento a elemento que usa el desenrollado.

    Los bucles están AQUÍ, en la prueba, que es donde pueden estar: lo que ADR-009
    prohíbe es que estén en `dlv-core`. Con NumPy estas mismas expresiones son
    pasadas en C.
    """

    def __lt__(self, otro: Any) -> Any:  # type: ignore[override]
        return ListaV(float(x < otro) for x in self)

    def __mul__(self, otro: Any) -> Any:  # type: ignore[override]
        return ListaV(x * otro for x in self)

    def __add__(self, otro: Any) -> Any:  # type: ignore[override]
        if isinstance(otro, list):
            assert len(otro) == len(self), "suma de longitudes distintas"
            return ListaV(a + b for a, b in zip(self, otro, strict=True))
        return ListaV(x + otro for x in self)

    def __getitem__(self, i: Any) -> Any:
        r = super().__getitem__(i)
        return ListaV(r) if isinstance(i, slice) else r


class XpLista:
    """Las cuatro funciones del protocolo `Vectorial`, con los nombres de NumPy."""

    def diff(self, a: Any, /) -> Any:
        return ListaV(b - x for x, b in pairwise(a))

    def cumsum(self, a: Any, /) -> Any:
        total = 0.0
        salida = ListaV()
        for x in a:
            total += x
            salida.append(total)
        return salida

    def concatenate(self, arrays: Any, /) -> Any:
        salida = ListaV()
        for a in arrays:
            salida.extend(a)
        return salida

    def count_nonzero(self, a: Any, /) -> int:
        return sum(1 for x in a if x)


@pytest.fixture
def xp() -> XpLista:
    return XpLista()


@pytest.fixture(scope="module")
def politica_haltech() -> PoliticaReloj:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return PoliticaReloj.desde_mapa(tomllib.load(fh)["reloj"])


def _marcas(*textos: str) -> ListaV:
    return ListaV(parsear_marca_de_fila(t) for t in textos)


# --------------------------------------------------------------------------- #
# Marcas de fila
# --------------------------------------------------------------------------- #
def test_marca_de_fila_del_autolog_real() -> None:
    assert parsear_marca_de_fila("18:30:35.506") == pytest.approx(66635.506)


def test_marca_de_fila_acepta_bytes() -> None:
    """El parseo del cuerpo trabaja con bytes; no debe tener que decodificar."""
    assert parsear_marca_de_fila(b"01:01:01.005") == pytest.approx(3661.005)


def test_la_fraccion_se_normaliza_por_su_longitud() -> None:
    """`.5` son cinco décimas, no cinco milésimas."""
    assert parsear_marca_de_fila("00:00:00.5") == pytest.approx(0.5)
    assert parsear_marca_de_fila("00:00:00.500") == pytest.approx(0.5)
    assert parsear_marca_de_fila("00:00:00.500000") == pytest.approx(0.5)


def test_se_aceptan_horas_acumuladas_por_encima_de_23() -> None:
    """Hay registradores que emiten `25:00:00` en vez de dar la vuelta.

    Es inequívoco y monótono, así que aceptarlo evita rechazar un log entero, y
    el desenrollado no tiene nada que corregir.
    """
    assert parsear_marca_de_fila("25:00:00.000") == pytest.approx(90000.0)


@pytest.mark.parametrize(
    "malas",
    ["18:60:00.000", "18:30:60.000", "18:30:35", "", "no es una hora", "18:30:35.", "1830:35.000"],
)
def test_marcas_malformadas_se_rechazan(malas: str) -> None:
    with pytest.raises(ErrorDeReloj):
        parsear_marca_de_fila(malas)


# --------------------------------------------------------------------------- #
# Metadato de fecha y hora
# --------------------------------------------------------------------------- #
def test_metadato_del_autolog_real() -> None:
    resultado = parsear_fecha_hora("20260729 06:30:35")
    assert resultado is not None
    fecha, sod = resultado
    assert fecha == date(2026, 7, 29)
    assert sod == pytest.approx(23435.0)


@pytest.mark.parametrize(
    "malo", ["20260729", "2026-07-29 06:30:35", "20260732 06:30:35", "20260729 25:00:00", ""]
)
def test_metadato_ilegible_devuelve_none_en_vez_de_lanzar(malo: str) -> None:
    """Un metadato ilegible es un aviso, no un fallo de carga (docs/02 §2.5)."""
    assert parsear_fecha_hora(malo) is None


# --------------------------------------------------------------------------- #
# Cruce de medianoche
# --------------------------------------------------------------------------- #
def test_sin_cruce_el_eje_no_se_toca(xp: XpLista) -> None:
    sod = _marcas("18:30:35.506", "18:30:35.556", "18:30:35.606")
    r = desenrollar_medianoche(sod, xp=xp)
    assert list(r.t) == pytest.approx(list(sod))
    assert r.cruces_de_medianoche == 0
    assert r.retrocesos_anomalos == 0


def test_el_cruce_de_medianoche_deja_el_eje_monotono(xp: XpLista) -> None:
    sod = _marcas("23:59:59.900", "23:59:59.950", "00:00:00.003", "00:00:00.053")
    r = desenrollar_medianoche(sod, xp=xp)
    t = list(r.t)
    assert r.cruces_de_medianoche == 1
    assert r.retrocesos_anomalos == 0
    assert all(b > a for a, b in pairwise(t)), t
    # La muestra posterior a medianoche cae 53 ms después de la anterior, no
    # 86 400 s antes.
    assert t[2] - t[1] == pytest.approx(0.053)
    assert t[2] == pytest.approx(SEGUNDOS_POR_DIA + 0.003)


def test_dos_medianoches_se_acumulan(xp: XpLista) -> None:
    """Una sesión de resistencia de más de 24 h da la vuelta dos veces."""
    sod = ListaV([0.0, 86399.0, 1.0, 86399.0, 2.0])
    r = desenrollar_medianoche(sod, xp=xp)
    t = list(r.t)
    assert r.cruces_de_medianoche == 2
    assert all(b > a for a, b in pairwise(t)), t
    assert t[-1] == pytest.approx(2 * SEGUNDOS_POR_DIA + 2.0)


def test_un_retroceso_pequeno_no_es_un_cruce_y_no_se_corrige(xp: XpLista) -> None:
    """La distinción que importa: sumar un día aquí falsearía 24 h de datos.

    Un retroceso de 50 ms es una marca no monótona —el aviso `marcas_no_monotonas`
    de F1-01—, y corregirlo exigiría adivinar qué quiso decir el registrador.
    """
    sod = _marcas("10:00:00.000", "10:00:00.050", "10:00:00.000", "10:00:00.100")
    r = desenrollar_medianoche(sod, xp=xp)
    assert r.cruces_de_medianoche == 0
    assert r.retrocesos_anomalos == 1
    assert r.hay_anomalias
    assert list(r.t) == pytest.approx(list(sod)), "no se debe inventar una corrección"


def test_cruce_y_anomalia_a_la_vez_se_cuentan_por_separado(xp: XpLista) -> None:
    sod = ListaV([86399.0, 0.5, 0.4, 1.0])
    r = desenrollar_medianoche(sod, xp=xp)
    assert (r.cruces_de_medianoche, r.retrocesos_anomalos) == (1, 1)


@pytest.mark.parametrize("n", [0, 1])
def test_series_de_menos_de_dos_muestras(xp: XpLista, n: int) -> None:
    """Un log que se cortó al arrancar existe y no debe reventar el desenrollado."""
    sod = ListaV([1234.5][:n])
    r = desenrollar_medianoche(sod, xp=xp)
    assert list(r.t) == list(sod)
    assert (r.cruces_de_medianoche, r.retrocesos_anomalos) == (0, 0)


def test_el_desenrollado_no_indexa_muestra_a_muestra() -> None:
    """ADR-009 comprobado por conducta, no por inspección estática.

    La propiedad que hay que preservar no es «no hay bucles `for`» —eso ya lo
    mira `tools/banco.py adr009`— sino que el coste no crece con el número de
    muestras en Python. Se comprueba contando: ningún acceso por índice entero
    (que es lo que delata un recorrido) y un número FIJO de operaciones
    vectoriales, cinco, independiente de la longitud de la serie.

    Importa aquí más que en otros sitios: el desenrollado se aplica al vector de
    instantes completo de cada canal, que es lo más grande que hay en memoria.
    """

    class ArrayVigilado(ListaV):
        accesos_por_indice = 0

        def __getitem__(self, i: Any) -> Any:
            if not isinstance(i, slice):
                type(self).accesos_por_indice += 1
            return super().__getitem__(i)

    class XpQueCuenta(XpLista):
        def __init__(self) -> None:
            self.llamadas: list[str] = []

        def diff(self, a: Any, /) -> Any:
            self.llamadas.append("diff")
            return super().diff(a)

        def cumsum(self, a: Any, /) -> Any:
            self.llamadas.append("cumsum")
            return super().cumsum(a)

        def concatenate(self, arrays: Any, /) -> Any:
            self.llamadas.append("concatenate")
            return super().concatenate(arrays)

        def count_nonzero(self, a: Any, /) -> int:
            self.llamadas.append("count_nonzero")
            return super().count_nonzero(a)

    for longitud in (3, 300):
        xp_contador = XpQueCuenta()
        ArrayVigilado.accesos_por_indice = 0
        sod = ArrayVigilado([float(i) for i in range(longitud - 1)] + [0.0])
        r = desenrollar_medianoche(sod, xp=xp_contador)
        assert r.cruces_de_medianoche == 0, "un retroceso pequeño no es medianoche"
        assert ArrayVigilado.accesos_por_indice == 0, (
            f"ADR-009: {ArrayVigilado.accesos_por_indice} accesos por índice con "
            f"{longitud} muestras; alguien está recorriendo la serie"
        )
        assert xp_contador.llamadas == [
            "diff",
            "count_nonzero",
            "count_nonzero",
            "cumsum",
            "concatenate",
        ], xp_contador.llamadas


# --------------------------------------------------------------------------- #
# Política desde el descriptor
# --------------------------------------------------------------------------- #
def test_la_politica_sale_del_descriptor_no_del_codigo(politica_haltech: PoliticaReloj) -> None:
    """ADR-008: las claves y las épocas de fábrica son datos del formato."""
    p = politica_haltech
    assert p.clave_inicio == "Log"
    assert p.clave_numero == "Log Number"
    assert p.hora_en_12h is True
    assert "19800101" in p.epocas_ficticias
    assert p.fecha_minima_plausible == date(2005, 1, 1)
    assert p.periodo_ambiguo_s == 12 * 3600.0


def test_un_descriptor_sin_seccion_reloj_no_impide_cargar() -> None:
    assert PoliticaReloj.desde_mapa({}) == PoliticaReloj()
    assert PoliticaReloj.desde_mapa(None) == PoliticaReloj()


def test_una_fecha_minima_ilegible_en_el_descriptor_se_rechaza() -> None:
    """Un descriptor mal escrito falla al cargarlo, no al usarlo."""
    with pytest.raises(ErrorDeReloj, match="fecha_minima_plausible"):
        PoliticaReloj.desde_mapa({"fecha_minima_plausible": "2005-01-01"})


def test_hora_en_24h_reduce_el_periodo_ambiguo() -> None:
    p = PoliticaReloj.desde_mapa({"hora_en_12h": False})
    assert p.periodo_ambiguo_s == SEGUNDOS_POR_DIA


# --------------------------------------------------------------------------- #
# Reconciliación: el AutoLog real (12 h de cabecera)
# --------------------------------------------------------------------------- #
def test_autolog_real_la_hora_sale_de_la_primera_fila(politica_haltech: PoliticaReloj) -> None:
    """El caso de §1.4, con los valores medidos del fichero real."""
    r = reconciliar(
        {"Log": "20260729 06:30:35", "DownloadDateTime": "20260729 06:58:28", "Log Number": "0"},
        parsear_marca_de_fila("18:30:35.506"),
        politica=politica_haltech,
    )
    assert r.fiabilidad is FiabilidadReloj.FIABLE
    # 18:30, no 06:30. Si esto se rompe, el log se desplaza 12 h.
    assert r.t0_absoluto == datetime(2026, 7, 29, 18, 30, 35, 506000)
    assert r.fecha == date(2026, 7, 29)
    assert r.desfase_cabecera_s == pytest.approx(-0.506)
    assert r.ordenar_por is OrdenTemporal.RELOJ
    assert r.modo_desfase_recomendado is ModoDesfase.RELOJ_ABSOLUTO
    assert r.avisos == ()


def test_la_hora_de_cabecera_nunca_es_el_t0(politica_haltech: PoliticaReloj) -> None:
    """`t0_declarado` es informativo; `t0_absoluto` es lo que se calcula."""
    r = reconciliar(
        {"Log": "20260729 06:30:35"},
        parsear_marca_de_fila("18:30:35.506"),
        politica=politica_haltech,
    )
    assert r.t0_declarado == datetime(2026, 7, 29, 6, 30, 35)
    assert r.t0_absoluto == datetime(2026, 7, 29, 18, 30, 35, 506000)


def test_desfase_de_12h_exacto(politica_haltech: PoliticaReloj) -> None:
    """Cabecera `12:30` con primera fila `00:30`: la ambigüedad es justo 12 h.

    Hora 12 en notación de 12 h es el caso peor, porque «12:30» significa 00:30 o
    12:30 **del mismo día**. Esta prueba cazó un defecto real: la primera versión
    resolvía el PM sumando 12 h sin módulo de 24 h, así que 12:30 se convertía en
    24:30 y la primera muestra quedaba fechada el 30 de julio en vez del 29. Un
    día entero de error, y silencioso: el log seguía marcado como fiable.
    """
    r = reconciliar(
        {"Log": "20260729 12:30:00"},
        parsear_marca_de_fila("00:30:00.000"),
        politica=politica_haltech,
    )
    assert r.fiabilidad is FiabilidadReloj.FIABLE
    assert r.t0_absoluto == datetime(2026, 7, 29, 0, 30, 0)
    assert r.avisos == (), "no hay nada anómalo: es la ambigüedad normal de las 12 h"


def test_un_desfase_que_no_es_0_ni_12h_degrada_a_relativo(
    politica_haltech: PoliticaReloj,
) -> None:
    """La regla de §1.4. El log sigue siendo utilizable, pero en relativo."""
    r = reconciliar(
        {"Log": "20260729 06:30:35", "Log Number": "0"},
        parsear_marca_de_fila("14:12:00.000"),
        politica=politica_haltech,
    )
    assert r.fiabilidad is FiabilidadReloj.NO_FIABLE
    assert r.t0_absoluto is None, "no se puede dar un t0 que no cuadra"
    assert r.t0_declarado is not None, "pero sí se puede enseñar lo que el log dice"
    assert r.modo_desfase_recomendado is ModoDesfase.RELATIVO
    assert [a.codigo for a in r.avisos] == ["reloj_no_fiable"]


def test_la_cabecera_escrita_antes_de_medianoche_fecha_bien_la_primera_muestra(
    politica_haltech: PoliticaReloj,
) -> None:
    """Cabecera `11:59:30` (12 h de 23:59:30) y primera fila `00:00:10`.

    Sin resolver a la vez el AM/PM y el día, este caso se rechazaría por reloj no
    fiable o se fecharía el día anterior.
    """
    r = reconciliar(
        {"Log": "20260729 11:59:30"},
        parsear_marca_de_fila("00:00:10.000"),
        politica=politica_haltech,
    )
    assert r.fiabilidad is FiabilidadReloj.FIABLE
    assert r.t0_absoluto == datetime(2026, 7, 30, 0, 0, 10)
    assert r.desfase_cabecera_s == pytest.approx(-40.0)
    assert [a.codigo for a in r.avisos] == ["cabecera_antes_de_medianoche"]


# --------------------------------------------------------------------------- #
# Reconciliación: época ficticia (los logs internos reales)
# --------------------------------------------------------------------------- #
def test_epoca_ficticia_no_produce_tiempo_absoluto(politica_haltech: PoliticaReloj) -> None:
    """El caso de §1.5, con los valores medidos de `Log2768`."""
    r = reconciliar(
        {
            "Log": "19800101 01:01:01",
            "DownloadDateTime": "20260729 06:59:01",
            "Log Number": "2768",
            "Log Source": "8",
        },
        parsear_marca_de_fila("01:01:01.005"),
        politica=politica_haltech,
    )
    assert r.epoca_ficticia is True
    assert r.fiabilidad is FiabilidadReloj.DESCONOCIDA
    assert r.t0_absoluto is None
    assert r.ordenar_por is OrdenTemporal.NUMERO_DE_LOG
    assert r.numero_de_log == 2768
    assert r.modo_desfase_recomendado is ModoDesfase.RELATIVO
    assert [a.codigo for a in r.avisos] == ["epoca_ficticia"]


def test_la_epoca_se_comprueba_antes_del_desfase(politica_haltech: PoliticaReloj) -> None:
    """LA prueba de esta tarea.

    `01:01:01` de cabecera contra `01:01:01.005` de primera fila da un desvío de
    5 ms: la comprobación de 12 h PASA con nota. Si se hiciera primero, los dos
    logs internos quedarían «fiables» y superpuestos en el mismo instante de
    1980. Se comprueba que el resultado no es fiable *y* que el motivo declarado
    es la época, no el desfase.
    """
    metadatos = {"Log": "19800101 01:01:01", "Log Number": "2768"}
    r = reconciliar(metadatos, parsear_marca_de_fila("01:01:01.005"), politica=politica_haltech)
    assert r.fiabilidad is not FiabilidadReloj.FIABLE
    assert r.epoca_ficticia is True
    assert r.desfase_cabecera_s is None, "no se llega a comprobar el desfase: sobra"
    assert "no tiene reloj de tiempo real" in r.avisos[0].mensaje


def test_los_dos_logs_internos_reales_no_se_superponen_por_reloj(
    politica_haltech: PoliticaReloj,
) -> None:
    """La consecuencia observable: el orden lo da `Log Number`, no el reloj.

    Y `DownloadDateTime` está invertido respecto al número de log (06:59:01 para
    el 2768 y 06:59:00 para el 2769), así que ordenar por él daría la vuelta a
    las dos tiradas.
    """
    comunes = {"Log": "19800101 01:01:01"}
    r2768 = reconciliar(
        {**comunes, "Log Number": "2768", "DownloadDateTime": "20260729 06:59:01"},
        3661.005,
        politica=politica_haltech,
    )
    r2769 = reconciliar(
        {**comunes, "Log Number": "2769", "DownloadDateTime": "20260729 06:59:00"},
        3661.005,
        politica=politica_haltech,
    )
    assert r2768.t0_absoluto is None and r2769.t0_absoluto is None
    assert r2768.numero_de_log is not None and r2769.numero_de_log is not None
    assert r2768.numero_de_log < r2769.numero_de_log


def test_una_fecha_anterior_a_la_minima_plausible_tambien_es_ficticia(
    politica_haltech: PoliticaReloj,
) -> None:
    """Red por debajo de la lista: una época de fábrica no catalogada."""
    r = reconciliar(
        {"Log": "19981231 23:00:00", "Log Number": "5"}, 100.0, politica=politica_haltech
    )
    assert r.epoca_ficticia is True


def test_epoca_ficticia_sin_numero_de_log_se_declara_sin_orden(
    politica_haltech: PoliticaReloj,
) -> None:
    """El peor caso: ni reloj ni número. Hay que decírselo al usuario."""
    r = reconciliar({"Log": "19800101 01:01:01"}, 3661.005, politica=politica_haltech)
    assert r.ordenar_por is OrdenTemporal.SIN_ORDEN
    assert {a.codigo for a in r.avisos} == {"epoca_ficticia", "reloj_sin_orden"}


# --------------------------------------------------------------------------- #
# Reconciliación: metadatos ausentes o corruptos
# --------------------------------------------------------------------------- #
def test_sin_metadato_de_inicio(politica_haltech: PoliticaReloj) -> None:
    r = reconciliar({"Log Number": "12"}, 100.0, politica=politica_haltech)
    assert r.fiabilidad is FiabilidadReloj.DESCONOCIDA
    assert r.ordenar_por is OrdenTemporal.NUMERO_DE_LOG
    assert [a.codigo for a in r.avisos] == ["reloj_sin_metadato"]


def test_metadato_de_inicio_corrupto(politica_haltech: PoliticaReloj) -> None:
    r = reconciliar({"Log": "basura", "Log Number": "12"}, 100.0, politica=politica_haltech)
    assert r.fiabilidad is FiabilidadReloj.DESCONOCIDA
    assert [a.codigo for a in r.avisos] == ["reloj_metadato_ilegible"]


def test_sin_primera_fila_no_se_usa_la_hora_ambigua(politica_haltech: PoliticaReloj) -> None:
    """Sin fila con la que desambiguar, la hora de cabecera no vale para nada."""
    r = reconciliar(
        {"Log": "20260729 06:30:35", "Log Number": "0"}, None, politica=politica_haltech
    )
    assert r.fiabilidad is FiabilidadReloj.DESCONOCIDA
    assert r.t0_absoluto is None
    assert r.fecha == date(2026, 7, 29), "la fecha sí es fiable"
    assert [a.codigo for a in r.avisos] == ["reloj_sin_primera_fila"]


def test_numero_de_log_no_numerico_no_rompe(politica_haltech: PoliticaReloj) -> None:
    r = reconciliar({"Log Number": "  "}, 100.0, politica=politica_haltech)
    assert r.numero_de_log is None
    assert r.ordenar_por is OrdenTemporal.SIN_ORDEN


def test_descarga_anterior_al_log_es_un_aviso(politica_haltech: PoliticaReloj) -> None:
    r = reconciliar(
        {"Log": "20260729 06:30:35", "DownloadDateTime": "20260728 07:00:00"},
        parsear_marca_de_fila("18:30:35.506"),
        politica=politica_haltech,
    )
    assert r.fiabilidad is FiabilidadReloj.FIABLE, "es un aviso, no un rechazo"
    assert [a.codigo for a in r.avisos] == ["descarga_anterior_al_log"]


# --------------------------------------------------------------------------- #
# Entrega al motor de tiempo
# --------------------------------------------------------------------------- #
def test_a_segmento_traslada_la_fiabilidad(politica_haltech: PoliticaReloj) -> None:
    """El punto de entrega a §3.6: el segmento hereda la fiabilidad, no la pierde."""
    fiable = reconciliar(
        {"Log": "20260729 06:30:35"},
        parsear_marca_de_fila("18:30:35.506"),
        politica=politica_haltech,
    ).a_segmento("autolog", orden=0)
    assert fiable.fiabilidad_reloj is FiabilidadReloj.FIABLE
    assert fiable.t0_absoluto == datetime(2026, 7, 29, 18, 30, 35, 506000)

    ficticio = reconciliar(
        {"Log": "19800101 01:01:01", "Log Number": "2768"}, 3661.005, politica=politica_haltech
    ).a_segmento("log2768", orden=1, offset_usuario=12.5)
    assert ficticio.fiabilidad_reloj is FiabilidadReloj.DESCONOCIDA
    assert ficticio.t0_absoluto is None
    assert ficticio.offset_usuario == 12.5


# --------------------------------------------------------------------------- #
# Contra los tres ficheros reales, de punta a punta
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("fichero", "fiable", "epoca_ficticia", "t0_esperado"),
    [
        ("AutoLog_20260729_1830.csv", True, False, datetime(2026, 7, 29, 18, 30, 35, 506000)),
        ("20260729_1859_Log2768.csv", False, True, None),
        ("20260729_1859_Log2769.csv", False, True, None),
    ],
)
def test_los_tres_logs_reales(
    politica_haltech: PoliticaReloj,
    fichero: str,
    fiable: bool,
    epoca_ficticia: bool,
    t0_esperado: datetime | None,
) -> None:
    """De los bytes del fichero al `t0_absoluto`, sin valores escritos a mano.

    Es la prueba que ataría la implementación a la realidad si algún día se
    cambia el parser: los tres ficheros están en el repositorio.
    """
    with DESCRIPTOR_TOML.open("rb") as fh:
        descriptor = cargar_descriptor(fh)
    datos = (REALES / fichero).read_bytes()
    assert sondear_formato(datos[:64], (descriptor,)) is descriptor

    cab = parsear_cabecera(datos, descriptor)
    cuerpo = datos[cab.offset_datos :]
    primera_fila = cuerpo.split(b"\n", 1)[0]
    primera_marca = parsear_marca_de_fila(primera_fila.split(b",", 1)[0])

    r = reconciliar(
        cab.metadatos, primera_marca, politica=PoliticaReloj.desde_mapa(descriptor.reloj)
    )
    assert (r.fiabilidad is FiabilidadReloj.FIABLE) is fiable
    assert r.epoca_ficticia is epoca_ficticia
    assert r.t0_absoluto == t0_esperado


def test_los_dos_logs_internos_reales_declaran_la_misma_epoca_falsa() -> None:
    """La evidencia de §1.5, comprobada sobre los ficheros y no citada de memoria.

    Si esto falla, la premisa de la tarea ha cambiado y hay que releer §1.5, no
    ajustar el número.
    """
    with DESCRIPTOR_TOML.open("rb") as fh:
        descriptor = cargar_descriptor(fh)
    declaradas = set()
    for fichero in ("20260729_1859_Log2768.csv", "20260729_1859_Log2769.csv"):
        cab = parsear_cabecera((REALES / fichero).read_bytes(), descriptor)
        declaradas.add(cab.metadatos["Log"])
    assert declaradas == {"19800101 01:01:01"}


# --------------------------------------------------------------------------- #
# Contratos de tipo
# --------------------------------------------------------------------------- #
def test_los_resultados_son_inmutables() -> None:
    """Nadie debe poder «arreglar» un t0 no fiable escribiéndolo por encima."""
    for tipo in (Reconciliacion, Desenrollado, PoliticaReloj, Aviso):
        assert tipo.__dataclass_params__.frozen, f"{tipo.__name__} debería ser inmutable"
