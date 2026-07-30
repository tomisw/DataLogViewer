"""Pruebas de la caché Parquet con pirámide persistida (tarea F1-11, ADR-005).

Cubre: round-trip completo (escribir + leer reconstruye lo mismo, para las
cuatro variantes de pirámide y para varios grupos de muestreo a la vez),
invalidación por cambio del fichero de origen, invalidación por cambio de
versión de esquema, y que la comprobación barata (`leer_metadatos`/
`es_valida`) no falla cuando la caché todavía no existe.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from dlv_core.almacen import ChannelSeries, Storage
from dlv_core.cache import (
    ClaveInvalidacion,
    construir_clave,
    es_valida,
    escribir,
    generar_series_sinteticas,
    leer,
    leer_metadatos,
    medir_ciclo_escritura_lectura,
)
from dlv_core.piramide import (
    NivelBits,
    NivelContador,
    NivelEnum,
    NivelPiramide,
    TipoCanalPiramide,
    construir_piramide,
)
from dlv_core.roles import ChannelKey
from dlv_core.unidades import Afin


def _clave(ruta: Path, **overrides: object) -> ClaveInvalidacion:
    base: dict[str, object] = {
        "tamano_bytes": 1234,
        "mtime_ns": 111,
        "version_parser": "1.0",
        "version_descriptor_formato": "haltech_nsp@1.1",
    }
    base.update(overrides)
    return construir_clave(ruta, **base)  # type: ignore[arg-type]


def _serie_continua(t: np.ndarray, valores: list[int], *, id_nativo: str = "1") -> ChannelSeries:
    v = np.array(valores, dtype=np.int32)
    return ChannelSeries(
        key=ChannelKey(
            rol="rpm", formato="haltech_nsp", id_nativo=id_nativo, nombre_normalizado="RPM"
        ),
        role="rpm",
        t=t,
        v=v,
        storage=Storage.INT32_SCALED,
        to_canon=Afin(0.1, 5.0),
        dimension="angular_speed",
    )


def _serie_enum(t: np.ndarray, valores: list[int]) -> ChannelSeries:
    v = np.array(valores, dtype=np.uint16)
    return ChannelSeries(
        key=ChannelKey(rol=None, formato="haltech_nsp", id_nativo="2", nombre_normalizado=None),
        role=None,
        t=t,
        v=v,
        storage=Storage.ENUM_U16,
        to_canon=Afin(1.0),
        dimension=None,
    )


def _serie_bits(t: np.ndarray, valores: list[int]) -> ChannelSeries:
    v = np.array(valores, dtype=np.uint32)
    return ChannelSeries(
        key=ChannelKey(rol=None, formato="haltech_nsp", id_nativo="3", nombre_normalizado=None),
        role=None,
        t=t,
        v=v,
        storage=Storage.BITS_U32,
        to_canon=Afin(1.0),
        dimension=None,
    )


# --------------------------------------------------------------------------- #
# Round-trip: las cuatro variantes a la vez, dos grupos de muestreo
# --------------------------------------------------------------------------- #
def test_round_trip_completo_cuatro_variantes_dos_grupos(tmp_path: Path) -> None:
    t_a = np.arange(37, dtype=np.uint32) * 100
    t_b = np.arange(20, dtype=np.uint32) * 50  # grupo de muestreo distinto (otra tasa)

    continuo = _serie_continua(t_a, list(range(37)))
    contador = ChannelSeries(
        key=ChannelKey(rol=None, formato="haltech_nsp", id_nativo="4", nombre_normalizado=None),
        role=None,
        t=t_a,  # mismo array que `continuo`: mismo grupo de muestreo
        v=np.cumsum(np.arange(37, dtype=np.int64)).astype(np.int32),
        storage=Storage.INT32_SCALED,
        to_canon=Afin(1.0),
        dimension=None,
    )
    enum_ = _serie_enum(t_b, [(i * 3) % 5 for i in range(20)])
    bits = _serie_bits(t_b, [1 << (i % 8) for i in range(20)])

    assert continuo.t is contador.t  # confirma que comparten grupo antes de escribir
    assert enum_.t is bits.t

    series = [continuo, contador, enum_, bits]
    piramides = [
        construir_piramide(continuo.v, tipo=TipoCanalPiramide.CONTINUO, factor_base=4),
        construir_piramide(contador.v, tipo=TipoCanalPiramide.CONTADOR, factor_base=4),
        construir_piramide(enum_.v, tipo=TipoCanalPiramide.ENUM, factor_base=4),
        construir_piramide(bits.v, tipo=TipoCanalPiramide.BITS, factor_base=4),
    ]

    destino = tmp_path / "log.dlvcache"
    clave = _clave(tmp_path / "log.csv")
    escribir(destino, clave, series, piramides)

    series_leidas, piramides_leidas, metadatos = leer(destino)

    assert len(series_leidas) == 4
    assert metadatos.clave == clave

    # Los dos primeros canales comparten grupo de muestreo: deben compartir
    # el array `t` reconstruido por referencia, igual que en memoria (ADR-003).
    assert series_leidas[0].t is series_leidas[1].t
    assert series_leidas[2].t is series_leidas[3].t
    assert series_leidas[0].t is not series_leidas[2].t

    for original, reconstruida in zip(series, series_leidas, strict=True):
        assert np.array_equal(reconstruida.t, original.t)
        assert np.array_equal(reconstruida.v, original.v)
        assert reconstruida.v.dtype == original.v.dtype
        assert reconstruida.storage is original.storage
        assert reconstruida.dimension == original.dimension
        assert reconstruida.role == original.role
        assert reconstruida.key == original.key
        assert reconstruida.to_canon.a == pytest.approx(original.to_canon.a)
        assert reconstruida.to_canon.b == pytest.approx(original.to_canon.b)

    for original, reconstruida in zip(piramides, piramides_leidas, strict=True):
        assert len(original) == len(reconstruida)
        for nivel_orig, nivel_leido in zip(original, reconstruida, strict=True):
            assert nivel_orig.factor == nivel_leido.factor
            if isinstance(nivel_orig, NivelPiramide):
                assert isinstance(nivel_leido, NivelPiramide)
                assert np.array_equal(nivel_orig.minimo, nivel_leido.minimo)
                assert np.array_equal(nivel_orig.maximo, nivel_leido.maximo)
                assert np.array_equal(nivel_orig.primero, nivel_leido.primero)
                assert np.array_equal(nivel_orig.ultimo, nivel_leido.ultimo)
            elif isinstance(nivel_orig, NivelContador):
                assert isinstance(nivel_leido, NivelContador)
                assert np.array_equal(nivel_orig.suma_delta, nivel_leido.suma_delta)
                assert np.array_equal(nivel_orig.primero, nivel_leido.primero)
                assert np.array_equal(nivel_orig.ultimo, nivel_leido.ultimo)
            elif isinstance(nivel_orig, NivelEnum):
                assert isinstance(nivel_leido, NivelEnum)
                assert np.array_equal(nivel_orig.moda, nivel_leido.moda)
                assert np.array_equal(nivel_orig.hubo_transicion, nivel_leido.hubo_transicion)
            elif isinstance(nivel_orig, NivelBits):
                assert isinstance(nivel_leido, NivelBits)
                assert np.array_equal(nivel_orig.or_bits, nivel_leido.or_bits)


def test_round_trip_de_una_sola_serie_pequena(tmp_path: Path) -> None:
    """Caso mínimo: un solo canal, pocas muestras (menos que `factor_base`,
    para que la pirámide se quede solo en L0)."""
    t = np.array([0, 10, 20], dtype=np.uint32)
    serie = _serie_continua(t, [5, -3, 100])
    piramide = construir_piramide(serie.v, tipo=TipoCanalPiramide.CONTINUO)

    destino = tmp_path / "mini.dlvcache"
    clave = _clave(tmp_path / "mini.csv")
    escribir(destino, clave, [serie], [piramide])

    (serie_leida,), (piramide_leida,), _ = leer(destino)

    assert np.array_equal(serie_leida.v, serie.v)
    assert np.array_equal(serie_leida.t, serie.t)
    assert len(piramide_leida) == 1  # solo L0: 3 muestras < factor_base=4


# --------------------------------------------------------------------------- #
# Invalidación
# --------------------------------------------------------------------------- #
def test_es_valida_con_la_misma_clave_es_verdadero(tmp_path: Path) -> None:
    clave = _clave(tmp_path / "log.csv")
    assert es_valida(clave, clave) is True


def test_es_valida_detecta_cambio_de_tamano_o_mtime_del_fichero_origen(tmp_path: Path) -> None:
    guardada = _clave(tmp_path / "log.csv")
    actual_tamano_distinto = replace(guardada, tamano_bytes=guardada.tamano_bytes + 1)
    actual_mtime_distinto = replace(guardada, mtime_ns=guardada.mtime_ns + 1)

    assert es_valida(guardada, actual_tamano_distinto) is False
    assert es_valida(guardada, actual_mtime_distinto) is False


def test_es_valida_detecta_cambio_de_version_de_esquema_de_cache(tmp_path: Path) -> None:
    """Simula una caché escrita por una versión anterior de dlv-core: aunque
    el fichero de origen no haya cambiado en absoluto, un cambio de
    `version_esquema_cache` debe invalidar (la FORMA de `ChannelSeries`/
    `NivelPiramide` pudo cambiar entre versiones del programa)."""
    guardada = replace(_clave(tmp_path / "log.csv"), version_esquema_cache="0")
    actual = _clave(tmp_path / "log.csv")  # versión de esquema actual

    assert guardada.version_esquema_cache != actual.version_esquema_cache
    assert es_valida(guardada, actual) is False


def test_es_valida_detecta_cambio_de_version_de_parser_o_descriptor(tmp_path: Path) -> None:
    guardada = _clave(tmp_path / "log.csv")
    otro_parser = _clave(tmp_path / "log.csv", version_parser="2.0")
    otro_descriptor = _clave(tmp_path / "log.csv", version_descriptor_formato="haltech_nsp@1.2")

    assert es_valida(guardada, otro_parser) is False
    assert es_valida(guardada, otro_descriptor) is False


def test_es_valida_no_falla_si_la_cache_no_existe_todavia(tmp_path: Path) -> None:
    destino = tmp_path / "nunca_escrita.dlvcache"

    metadatos = leer_metadatos(destino)
    assert metadatos is None

    clave_actual = _clave(tmp_path / "log.csv")
    assert es_valida(metadatos.clave if metadatos else None, clave_actual) is False


def test_leer_metadatos_tras_escribir_devuelve_la_clave_guardada(tmp_path: Path) -> None:
    t = np.array([0, 1], dtype=np.uint32)
    serie = _serie_continua(t, [1, 2])
    piramide = construir_piramide(serie.v, tipo=TipoCanalPiramide.CONTINUO)
    destino = tmp_path / "log.dlvcache"
    clave = _clave(tmp_path / "log.csv")

    escribir(destino, clave, [serie], [piramide])
    metadatos = leer_metadatos(destino)

    assert metadatos is not None
    assert es_valida(metadatos.clave, clave) is True
    assert es_valida(metadatos.clave, replace(clave, tamano_bytes=999)) is False


def test_leer_sin_cache_lanza_filenotfounderror(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        leer(tmp_path / "no_existe.dlvcache")


# --------------------------------------------------------------------------- #
# escribir/leer validan que series y pirámides tengan la misma longitud
# --------------------------------------------------------------------------- #
def test_escribir_con_longitudes_distintas_lanza_valueerror(tmp_path: Path) -> None:
    t = np.array([0, 1], dtype=np.uint32)
    serie = _serie_continua(t, [1, 2])
    piramide = construir_piramide(serie.v, tipo=TipoCanalPiramide.CONTINUO)

    with pytest.raises(ValueError):
        escribir(
            tmp_path / "log.dlvcache", _clave(tmp_path / "log.csv"), [serie], [piramide, piramide]
        )


# --------------------------------------------------------------------------- #
# Banco: datos sintéticos + medición (funciones públicas de librería, F1-11)
# --------------------------------------------------------------------------- #
def test_generar_series_sinteticas_cubre_las_cuatro_variantes(tmp_path: Path) -> None:
    series, piramides = generar_series_sinteticas(n_canales=8, n_muestras=1000, semilla=1)

    assert len(series) == 8
    assert len(piramides) == 8
    tipos_vistos = set()
    for serie, piramide in zip(series, piramides, strict=True):
        assert len(serie.t) == 1000
        assert len(serie.v) == 1000
        if isinstance(piramide[0], NivelPiramide):
            tipos_vistos.add(TipoCanalPiramide.CONTINUO)
        elif isinstance(piramide[0], NivelContador):
            tipos_vistos.add(TipoCanalPiramide.CONTADOR)
        elif isinstance(piramide[0], NivelEnum):
            tipos_vistos.add(TipoCanalPiramide.ENUM)
        elif isinstance(piramide[0], NivelBits):
            tipos_vistos.add(TipoCanalPiramide.BITS)
    assert tipos_vistos == set(TipoCanalPiramide)


def test_medir_ciclo_escritura_lectura_hace_round_trip_correcto(tmp_path: Path) -> None:
    """No juzga el presupuesto de 700 ms (eso lo mide el banco con datos
    grandes de verdad, ver informe de la tarea): con datos pequeños solo
    comprueba que la medición hace un ciclo de escribir+leer que en efecto
    reconstruye los datos, y que devuelve tiempos no negativos."""
    series, piramides = generar_series_sinteticas(n_canales=4, n_muestras=2000, semilla=2)
    destino = tmp_path / "banco.dlvcache"
    clave = _clave(tmp_path / "banco.csv")

    tiempos = medir_ciclo_escritura_lectura(destino, clave, series, piramides)

    assert tiempos["escritura_ms"] >= 0.0
    assert tiempos["lectura_ms"] >= 0.0
    assert tiempos["total_ms"] == pytest.approx(tiempos["escritura_ms"] + tiempos["lectura_ms"])

    series_leidas, _, _ = leer(destino)
    assert len(series_leidas) == 4
    for original, reconstruida in zip(series, series_leidas, strict=True):
        assert np.array_equal(reconstruida.v, original.v)
