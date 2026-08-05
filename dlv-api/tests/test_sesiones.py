"""Recorte de cubos por rango y ciclo de vida de las sesiones.

Se prueba lo que se puede equivocar EN SILENCIO, que aquí es una cosa muy
concreta: que el recorte devuelva los cubos que solapan el rango y ni uno más
ni uno menos. Un cubo de menos por la izquierda es un hueco en el borde del
gráfico que se diagnostica como "el log está cortado"; uno de más es un pico
dibujado fuera de su sitio. Ninguna de las dos cosas revienta nada.

Los casos de rango se construyen sobre una pirámide sintética con instantes
conocidos (`t = 0, 1, 2, ... s`), no sobre un log real: con un log real habría
que deducir a mano qué cubo toca en cada borde, y esa deducción es justo lo
que se está probando.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dlv_api.sesiones import (
    RegistroSesiones,
    huella_descriptor,
    indices_de_rango,
    recortar_nivel,
)
from dlv_core.formatos.haltech import cargar_descriptor
from dlv_core.piramide import construir_piramide_continuo
from dlv_core.unidades import cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
AUTOLOG_REAL = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
UNITS_TOML = RAIZ / "data" / "units.toml"


def _piramide_de_prueba(n: int = 64) -> tuple[np.ndarray, list]:
    """`n` muestras a 1 Hz exacto y su pirámide `CONTINUO` (factores 1, 4, 16…).

    Los valores son `0, 10, 20, …` para que el valor de un cubo diga a qué
    muestra corresponde sin tener que contar.
    """
    t_segundos = np.arange(n, dtype=np.float64)
    valores = (np.arange(n) * 10).astype(np.int32)
    return t_segundos, construir_piramide_continuo(valores)


# --------------------------------------------------------------------------- #
# indices_de_rango: los bordes, que es donde se equivoca
# --------------------------------------------------------------------------- #
def test_el_rango_incluye_el_cubo_que_empieza_antes_del_borde_izquierdo() -> None:
    t, piramide = _piramide_de_prueba()
    nivel = piramide[1]  # factor 4: cubos en t = 0, 4, 8, ...

    # [5, 9] cae dentro de los cubos que empiezan en 4 y en 8.
    inicio, fin = indices_de_rango(t, factor=4, n_cubos=nivel.n_cubos, t0=5.0, t1=9.0)
    assert (inicio, fin) == (1, 3)


def test_un_borde_que_cae_justo_en_el_inicio_de_un_cubo_lo_incluye() -> None:
    t, piramide = _piramide_de_prueba()
    nivel = piramide[1]  # factor 4

    # t0 exactamente en el inicio del cubo 2 (t = 8): ese cubo es el primero,
    # no el anterior.
    inicio, fin = indices_de_rango(t, factor=4, n_cubos=nivel.n_cubos, t0=8.0, t1=8.0)
    assert (inicio, fin) == (2, 3)


def test_un_rango_puntual_devuelve_exactamente_un_cubo() -> None:
    t, piramide = _piramide_de_prueba()
    for indice_nivel, nivel in enumerate(piramide):
        inicio, fin = indices_de_rango(
            t, factor=nivel.factor, n_cubos=nivel.n_cubos, t0=17.5, t1=17.5
        )
        assert fin - inicio == 1, f"nivel {indice_nivel} (factor {nivel.factor})"


def test_un_rango_anterior_al_log_no_devuelve_nada() -> None:
    t, piramide = _piramide_de_prueba()
    nivel = piramide[1]
    assert indices_de_rango(t, factor=4, n_cubos=nivel.n_cubos, t0=-10.0, t1=-1.0) == (0, 0)


def test_un_rango_posterior_al_log_no_devuelve_nada() -> None:
    t, piramide = _piramide_de_prueba()
    nivel = piramide[1]
    assert indices_de_rango(t, factor=4, n_cubos=nivel.n_cubos, t0=1_000.0, t1=2_000.0) == (0, 0)


def test_un_rango_que_empieza_antes_del_log_arranca_en_el_primer_cubo() -> None:
    t, piramide = _piramide_de_prueba()
    nivel = piramide[1]
    inicio, fin = indices_de_rango(t, factor=4, n_cubos=nivel.n_cubos, t0=-100.0, t1=5.0)
    assert (inicio, fin) == (0, 2)


def test_un_rango_que_cubre_todo_devuelve_todos_los_cubos() -> None:
    t, piramide = _piramide_de_prueba()
    for nivel in piramide:
        inicio, fin = indices_de_rango(
            t, factor=nivel.factor, n_cubos=nivel.n_cubos, t0=-1e9, t1=1e9
        )
        assert (inicio, fin) == (0, nivel.n_cubos)


def test_un_rango_invertido_no_devuelve_nada() -> None:
    t, piramide = _piramide_de_prueba()
    nivel = piramide[1]
    assert indices_de_rango(t, factor=4, n_cubos=nivel.n_cubos, t0=20.0, t1=5.0) == (0, 0)


def test_el_conjunto_devuelto_es_exactamente_el_que_solapa() -> None:
    """La prueba de referencia: comparar contra la definición de solape,
    calculada a mano cubo a cubo, para muchos rangos y todos los niveles.

    Es lenta a propósito -- un bucle de Python sobre cubos, que en el código de
    producción estaría prohibido por ADR-009 -- porque una prueba que reusara
    la aritmética de `indices_de_rango` no probaría nada.
    """
    for n_muestras in (64, 70):  # 70 deja cola truncada en los niveles altos
        t, piramide = _piramide_de_prueba(n_muestras)
        for nivel in piramide:
            f, n = nivel.factor, nivel.n_cubos
            if n == 0:
                continue
            for t0 in (-5.0, 0.0, 0.5, 3.0, 7.25, 30.0, 62.0, 63.0, 67.5, 68.0, 100.0):
                for ancho in (0.0, 0.5, 4.0, 25.0):
                    t1 = t0 + ancho
                    esperados = {i for i in range(n) if _solapa(t, f, i, t0, t1)}
                    inicio, fin = indices_de_rango(t, factor=f, n_cubos=n, t0=t0, t1=t1)
                    assert set(range(inicio, fin)) == esperados, (
                        f"{n_muestras} muestras, factor {f}, rango [{t0}, {t1}]: "
                        f"devuelto {list(range(inicio, fin))}, esperado {sorted(esperados)}"
                    )


def _solapa(t: np.ndarray, factor: int, i: int, t0: float, t1: float) -> bool:
    """La definición de solape, escrita a mano y sin reusar nada del código que
    se prueba.

    El cubo `i` agrega las muestras `[i*f, (i+1)*f)` y se dibuja en el instante
    de la primera. Ocupa desde ahí hasta la muestra siguiente al final de su
    grupo (medio abierto), o hasta la última muestra del log si su grupo es el
    último que el nivel cubre (cerrado): un nivel de factor alto deja fuera la
    cola de muestras que no completa un cubo.
    """
    inicio = float(t[i * factor])
    siguiente = (i + 1) * factor
    if siguiente < len(t):
        return inicio <= t1 and float(t[siguiente]) > t0
    return inicio <= t1 and float(t[len(t) - 1]) >= t0


# --------------------------------------------------------------------------- #
# recortar_nivel: los arrays, el origen y los dtypes
# --------------------------------------------------------------------------- #
def test_el_recorte_devuelve_los_valores_del_nivel_sin_desplazamiento() -> None:
    t, piramide = _piramide_de_prueba()
    nivel = piramide[1]  # factor 4
    recorte = recortar_nivel(t, nivel, t0=5.0, t1=9.0)

    assert recorte.factor == 4
    assert recorte.indice_inicio == 1
    assert recorte.n_cubos == 2
    # Cubos 1 y 2 del nivel: muestras 4-7 (valores 40..70) y 8-11 (80..110).
    assert list(recorte.minimo) == [40.0, 80.0]
    assert list(recorte.maximo) == [70.0, 110.0]
    assert list(recorte.primero) == [40.0, 80.0]
    assert list(recorte.ultimo) == [70.0, 110.0]


def test_el_tiempo_del_recorte_es_relativo_a_su_propio_origen() -> None:
    t, piramide = _piramide_de_prueba()
    recorte = recortar_nivel(t, piramide[1], t0=5.0, t1=20.0)

    assert recorte.t_origen == 4.0  # el cubo 1 empieza en t = 4 s
    assert recorte.t[0] == 0.0
    # Cubos cada 4 muestras a 1 Hz: 4 s entre cubos consecutivos.
    assert list(recorte.t) == [0.0, 4.0, 8.0, 12.0, 16.0]


def test_los_cinco_arrays_son_float32_y_miden_lo_mismo() -> None:
    """`CubosContinuos` declara `Float32Array` en los cinco, y `validarCubos`
    del frontend falla si no miden lo mismo."""
    t, piramide = _piramide_de_prueba()
    recorte = recortar_nivel(t, piramide[2], t0=0.0, t1=64.0)
    arrays = (recorte.t, recorte.minimo, recorte.maximo, recorte.primero, recorte.ultimo)
    assert all(a.dtype == np.float32 for a in arrays)
    assert len({len(a) for a in arrays}) == 1


def test_un_recorte_fuera_del_log_devuelve_cero_cubos_sin_lanzar() -> None:
    t, piramide = _piramide_de_prueba()
    recorte = recortar_nivel(t, piramide[1], t0=500.0, t1=600.0)
    assert recorte.n_cubos == 0
    assert recorte.t_origen == 0.0


def test_el_nivel_0_devuelve_las_muestras_tal_cual() -> None:
    """L0 no decima: min = max = primero = ultimo = el valor de la muestra."""
    t, piramide = _piramide_de_prueba()
    recorte = recortar_nivel(t, piramide[0], t0=3.0, t1=5.0)
    assert recorte.factor == 1
    assert list(recorte.minimo) == [30.0, 40.0, 50.0]
    assert list(recorte.maximo) == list(recorte.minimo)
    assert list(recorte.primero) == list(recorte.minimo)


def test_los_niveles_altos_no_inventan_cubos_en_la_cola_truncada() -> None:
    """Un nivel de factor `f` deja fuera las muestras que no completan un cubo
    (`_siguiente_nivel_continuo` trunca). Pedir ese tramo tiene que devolver
    los cubos que sí existen, no extrapolar hasta el final del log."""
    n = 70  # 70 = 4*17 + 2: el nivel de factor 4 solo cubre hasta la muestra 67
    t, piramide = _piramide_de_prueba(n)
    nivel = next(nv for nv in piramide if nv.factor == 4)
    assert nivel.n_cubos == 17

    # El tramo [68, 69] queda fuera de lo que cubre este nivel.
    assert recortar_nivel(t, nivel, t0=68.0, t1=69.0).n_cubos == 0
    # Y un tramo que llega hasta el final del log se para en el último cubo real.
    recorte = recortar_nivel(t, nivel, t0=60.0, t1=69.0)
    assert recorte.indice_inicio + recorte.n_cubos == 17


# --------------------------------------------------------------------------- #
# RegistroSesiones: no reparsear, no crecer sin límite, liberar al cerrar
# --------------------------------------------------------------------------- #
def _registro(tmp_path: Path, *, maximo: int = 8) -> RegistroSesiones:
    with DESCRIPTOR_TOML.open("rb") as fh:
        descriptor = cargar_descriptor(fh)
    with UNITS_TOML.open("rb") as fh:
        catalogo = cargar_catalogo(fh)
    return RegistroSesiones(
        descriptor=descriptor,
        catalogo=catalogo,
        version_descriptor=huella_descriptor(DESCRIPTOR_TOML),
        dir_cache=tmp_path / "cache",
        maximo=maximo,
    )


def test_abrir_dos_veces_el_mismo_log_devuelve_la_misma_sesion(tmp_path: Path) -> None:
    """El caso que este módulo existe para arreglar: la segunda apertura no
    vuelve a parsear NADA -- ni el log ni la caché -- porque la sesión ya está
    en memoria."""
    registro = _registro(tmp_path)
    primera, reutilizada_1 = registro.abrir(AUTOLOG_REAL)
    segunda, reutilizada_2 = registro.abrir(AUTOLOG_REAL)

    assert reutilizada_1 is False
    assert reutilizada_2 is True
    assert primera.id_sesion == segunda.id_sesion
    assert len(registro) == 1
    # Misma sesión = mismos objetos, no una copia equivalente: es lo que
    # garantiza que no se ha duplicado el almacén en memoria.
    assert primera.canales[0].serie is segunda.canales[0].serie


def test_la_segunda_apertura_en_un_registro_nuevo_sale_de_la_cache(tmp_path: Path) -> None:
    """ADR-005: con la sesión ya olvidada, el `.dlvcache` evita reparsear."""
    dir_cache = tmp_path / "cache"
    registro_1 = _registro(tmp_path)
    sesion_1, _ = registro_1.abrir(AUTOLOG_REAL)
    assert sesion_1.desde_cache is False
    assert list(dir_cache.glob("*.dlvcache.json")), "la primera apertura no ha escrito la caché"

    registro_2 = _registro(tmp_path)
    sesion_2, _ = registro_2.abrir(AUTOLOG_REAL)
    assert sesion_2.desde_cache is True

    # Y los datos son los mismos, que es lo que hace útil la caché.
    assert sesion_2.n_canales == sesion_1.n_canales
    canal_1 = sesion_1.canales[0]
    canal_2 = sesion_2.por_id[canal_1.id]
    assert np.array_equal(canal_1.serie.v, canal_2.serie.v)
    assert [n.n_cubos for n in canal_1.niveles] == [n.n_cubos for n in canal_2.niveles]


def test_una_cache_de_otro_fichero_no_se_reutiliza(tmp_path: Path) -> None:
    """La clave de invalidación incluye la ruta, el tamaño y el mtime: dos logs
    distintos no pueden compartir caché aunque se abran en el mismo registro."""
    registro = _registro(tmp_path)
    otro = RAIZ / "samples" / "real" / "20260729_1859_Log2768.csv"
    sesion_a, _ = registro.abrir(AUTOLOG_REAL)
    sesion_b, _ = registro.abrir(otro)
    assert sesion_a.id_sesion != sesion_b.id_sesion
    assert sesion_a.n_canales != sesion_b.n_canales or sesion_a.ruta != sesion_b.ruta


def test_el_tope_desaloja_el_menos_usado(tmp_path: Path) -> None:
    """Sin tope, la memoria del proceso crece hasta donde llegue el usuario
    abriendo ficheros (§2.6 pide aguantar ocho, no infinitos)."""
    registro = _registro(tmp_path, maximo=2)
    a = RAIZ / "samples" / "real" / "20260729_1859_Log2768.csv"
    b = RAIZ / "samples" / "real" / "20260729_1859_Log2769.csv"
    sesion_a, _ = registro.abrir(a)
    sesion_b, _ = registro.abrir(b)

    # Tocar A la vuelve "reciente", así que la tercera apertura desaloja a B.
    registro.obtener(sesion_a.id_sesion)
    sesion_c, _ = registro.abrir(AUTOLOG_REAL)

    assert len(registro) == 2
    assert registro.obtener(sesion_a.id_sesion) is sesion_a
    assert registro.obtener(sesion_c.id_sesion) is sesion_c
    with pytest.raises(LookupError):
        registro.obtener(sesion_b.id_sesion)


def test_cerrar_libera_la_sesion_y_es_idempotente(tmp_path: Path) -> None:
    registro = _registro(tmp_path)
    sesion, _ = registro.abrir(AUTOLOG_REAL)

    assert registro.cerrar(sesion.id_sesion) is True
    assert len(registro) == 0
    with pytest.raises(LookupError):
        registro.obtener(sesion.id_sesion)
    # Cerrar dos veces no es un error: el usuario puede cerrar la pestaña y
    # luego el log.
    assert registro.cerrar(sesion.id_sesion) is False

    # Y reabrir después de cerrar da una sesión NUEVA, no la de antes.
    nueva, reutilizada = registro.abrir(AUTOLOG_REAL)
    assert reutilizada is False
    assert nueva.id_sesion != sesion.id_sesion


def test_un_log_modificado_en_disco_no_se_reutiliza(tmp_path: Path) -> None:
    """Un log que se sigue escribiendo mientras se mira es un caso real en
    banco; servir los cubos viejos como si fueran los de ahora no se nota."""
    copia = tmp_path / "log.csv"
    copia.write_bytes((RAIZ / "samples" / "real" / "20260729_1859_Log2768.csv").read_bytes())

    registro = _registro(tmp_path)
    primera, _ = registro.abrir(copia)

    # Reescribir con otro mtime y otro tamaño (una fila de datos menos).
    contenido = copia.read_bytes()
    copia.write_bytes(contenido[: contenido.rindex(b"\n", 0, len(contenido) - 2)])

    segunda, reutilizada = registro.abrir(copia)
    assert reutilizada is False
    assert segunda.id_sesion != primera.id_sesion
    assert len(registro) == 1
