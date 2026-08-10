"""Pruebas del índice de carpeta del explorador de logs (FE-01).

Especificación: `docs/02-alcance-y-plan.md` §2.5 (E15.6, E15.7) y R14/R15.

QUÉ PROTEGE ESTA SUITE, POR CONSECUENCIA SI SE ROMPE
=====================================================
1. **Un fichero reescrito se recalcula.** La ECU reutiliza nombres de log entre
   sesiones. Si el índice se fiara del nombre, la tabla enseñaría el resumen del
   log anterior bajo el nombre del nuevo: la fila parece correcta, los números
   son plausibles y no hay forma de notarlo. Es el peor de los tres fallos.
2. **Un fichero borrado desaparece de la tabla** (R15): si no, el usuario hace
   doble clic en un log que ya no existe.
3. **El orden no cambia entre aperturas.** El sistema de ficheros no garantiza
   orden de enumeración; una tabla que se reordena sola no se puede leer.
4. **Un índice corrupto no rompe la apertura de la carpeta.** Es una caché
   reconstruible: se descarta y se recalcula.

Nada de esto toca el disco: `planificar_indexado` recibe las entradas ya leídas
(ADR-002), así que se pueden construir carpetas que sería incómodo crear de
verdad — una con miles de ficheros, o una donde el `mtime` va hacia atrás.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from dlv_core.explorador.indice import (
    VERSION_ESQUEMA_INDICE,
    Descarte,
    EntradaDeCarpeta,
    Indice,
    aplicar_resumenes,
    escribir_indice,
    leer_indice,
    planificar_indexado,
    separar_candidatos,
)

VERSIONES: dict[str, str] = {
    "version_parser": "1.0",
    "version_descriptor_formato": "haltech-nsp-1",
}


def entrada(nombre: str, *, tamano: int = 1000, mtime: int = 111) -> EntradaDeCarpeta:
    return EntradaDeCarpeta(ruta=Path("/logs") / nombre, tamano_bytes=tamano, mtime_ns=mtime)


def indexar(entradas: list[EntradaDeCarpeta], **resumen: Any) -> Indice:
    """Un índice ya construido para esas entradas, con un resumen de relleno."""
    plan = planificar_indexado(entradas, None, **VERSIONES)
    return aplicar_resumenes(
        plan,
        {e.ruta: (resumen or {"rpm_max": 6500.0}) for e in entradas},
        **VERSIONES,
    )


# --------------------------------------------------------------------------- #
# La primera apertura y la reapertura
# --------------------------------------------------------------------------- #
def test_sin_indice_todo_esta_por_calcular() -> None:
    plan = planificar_indexado([entrada("a.csv"), entrada("b.csv")], None, **VERSIONES)
    assert [e.ruta.name for e in plan.a_calcular] == ["a.csv", "b.csv"]
    assert plan.reutilizables == ()
    assert plan.a_descartar == ()
    assert plan.hay_trabajo
    assert plan.total_de_filas == 2


def test_la_reapertura_no_recalcula_nada() -> None:
    """Es lo que hace alcanzable el presupuesto de 500 ms de §2.6: la segunda vez
    no se abre ningún log."""
    entradas = [entrada("a.csv"), entrada("b.csv")]
    plan = planificar_indexado(entradas, indexar(entradas), **VERSIONES)
    assert plan.a_calcular == ()
    assert [e.ruta.name for e in plan.reutilizables] == ["a.csv", "b.csv"]
    assert not plan.hay_trabajo
    assert plan.total_de_filas == 2


def test_el_total_de_filas_se_conoce_antes_de_calcular_nada() -> None:
    """E15.7 pide enseñar «37 de 200» desde la primera fila, y para eso el
    denominador tiene que estar disponible antes de resumir ningún log."""
    viejas = [entrada("a.csv"), entrada("b.csv")]
    indice = indexar(viejas)
    plan = planificar_indexado([*viejas, entrada("c.csv")], indice, **VERSIONES)
    assert plan.total_de_filas == 3
    assert len(plan.a_calcular) == 1


# --------------------------------------------------------------------------- #
# Lo que invalida una entrada
# --------------------------------------------------------------------------- #
def test_un_fichero_reescrito_con_el_mismo_nombre_se_recalcula() -> None:
    """El caso de la ECU: mismo nombre, otro contenido. Si esto fallara, la fila
    tendría el nombre del log nuevo y los números del viejo, y nada en la tabla
    lo delataría."""
    indice = indexar([entrada("Log2768.csv", tamano=1000, mtime=111)])
    plan = planificar_indexado(
        [entrada("Log2768.csv", tamano=2500, mtime=222)], indice, **VERSIONES
    )
    assert [e.ruta.name for e in plan.a_calcular] == ["Log2768.csv"]
    assert plan.reutilizables == ()


def test_basta_con_que_cambie_el_mtime() -> None:
    """Un fichero reescrito con exactamente el mismo tamaño es plausible: la ECU
    escribe logs de duración fija. El tamaño solo no bastaría."""
    indice = indexar([entrada("a.csv", tamano=1000, mtime=111)])
    plan = planificar_indexado([entrada("a.csv", tamano=1000, mtime=999)], indice, **VERSIONES)
    assert len(plan.a_calcular) == 1


def test_basta_con_que_cambie_el_tamano() -> None:
    """Y al revés: copiar un fichero puede preservar el mtime y cambiar el
    tamaño."""
    indice = indexar([entrada("a.csv", tamano=1000, mtime=111)])
    plan = planificar_indexado([entrada("a.csv", tamano=1001, mtime=111)], indice, **VERSIONES)
    assert len(plan.a_calcular) == 1


def test_cambiar_la_version_del_parser_invalida_todo() -> None:
    """El fichero no ha cambiado, pero su resumen sí: si el parser reinterpreta
    una escala, los números guardados son de otra época. Es la razón por la que
    las versiones están en la huella de `cache.py` y no solo el `stat()`."""
    entradas = [entrada("a.csv"), entrada("b.csv")]
    indice = indexar(entradas)
    plan = planificar_indexado(
        entradas,
        indice,
        version_parser="2.0",
        version_descriptor_formato=VERSIONES["version_descriptor_formato"],
    )
    assert len(plan.a_calcular) == 2
    assert plan.reutilizables == ()


def test_cambiar_la_version_del_descriptor_invalida_todo() -> None:
    entradas = [entrada("a.csv")]
    plan = planificar_indexado(
        entradas,
        indexar(entradas),
        version_parser=VERSIONES["version_parser"],
        version_descriptor_formato="haltech-nsp-2",
    )
    assert len(plan.a_calcular) == 1


# --------------------------------------------------------------------------- #
# R15: lo que ya no está
# --------------------------------------------------------------------------- #
def test_un_fichero_borrado_se_descarta_y_no_sobrevive_al_indice() -> None:
    """R15. La tabla no puede describir una carpeta que ya no existe."""
    indice = indexar([entrada("a.csv"), entrada("borrado.csv")])
    plan = planificar_indexado([entrada("a.csv")], indice, **VERSIONES)
    assert [e.ruta.name for e in plan.a_descartar] == ["borrado.csv"]
    assert plan.total_de_filas == 1

    nuevo = aplicar_resumenes(plan, {}, **VERSIONES)
    assert [e.ruta.name for e in nuevo.entradas] == ["a.csv"]


def test_las_tres_listas_del_plan_son_una_particion() -> None:
    """Cada ruta cae en exactamente una lista, y entre las tres está todo lo que
    había antes más todo lo que hay ahora. Sin esta propiedad una entrada podría
    quedarse en el limbo (ni se recalcula ni se muestra) o contarse dos veces."""
    antes = [entrada("igual.csv"), entrada("cambia.csv", mtime=1), entrada("se_va.csv")]
    indice = indexar(antes)
    ahora = [entrada("igual.csv"), entrada("cambia.csv", mtime=2), entrada("nuevo.csv")]
    plan = planificar_indexado(ahora, indice, **VERSIONES)

    calculo = {e.ruta for e in plan.a_calcular}
    reuso = {e.ruta for e in plan.reutilizables}
    descarte = {e.ruta for e in plan.a_descartar}
    assert calculo == {Path("/logs/cambia.csv"), Path("/logs/nuevo.csv")}
    assert reuso == {Path("/logs/igual.csv")}
    assert descarte == {Path("/logs/se_va.csv")}
    assert calculo & reuso == set()
    assert calculo & descarte == set()
    assert reuso & descarte == set()
    assert calculo | reuso | descarte == {e.ruta for e in antes} | {e.ruta for e in ahora}


# --------------------------------------------------------------------------- #
# Orden estable
# --------------------------------------------------------------------------- #
def test_el_orden_no_depende_del_orden_de_enumeracion() -> None:
    """`os.scandir` no garantiza orden. Si el plan lo propagara, la misma carpeta
    daría la tabla con las filas en otro sitio en cada apertura."""
    nombres = ["c.csv", "a.csv", "b.csv"]
    plan = planificar_indexado([entrada(n) for n in nombres], None, **VERSIONES)
    assert [e.ruta.name for e in plan.a_calcular] == ["a.csv", "b.csv", "c.csv"]

    al_reves = planificar_indexado([entrada(n) for n in reversed(nombres)], None, **VERSIONES)
    assert [e.ruta for e in al_reves.a_calcular] == [e.ruta for e in plan.a_calcular]


def test_el_indice_resultante_tambien_esta_ordenado() -> None:
    indice = indexar([entrada("z.csv"), entrada("a.csv"), entrada("m.csv")])
    assert [e.ruta.name for e in indice.entradas] == ["a.csv", "m.csv", "z.csv"]


# --------------------------------------------------------------------------- #
# Escaneo cancelable: resúmenes incompletos
# --------------------------------------------------------------------------- #
def test_un_escaneo_a_medias_guarda_lo_calculado_y_no_inventa_el_resto() -> None:
    """E15.7: el escaneo es cancelable. Lo que se alcanzó a calcular se guarda,
    y lo demás vuelve a salir en `a_calcular` la próxima vez.

    Lo que NO puede pasar es que un fichero sin resumen entre en el índice con un
    resumen vacío: sería indistinguible de un log cuyo resumen salió de verdad sin
    datos, que es la confusión que R14 prohíbe."""
    entradas = [entrada("a.csv"), entrada("b.csv"), entrada("c.csv")]
    plan = planificar_indexado(entradas, None, **VERSIONES)
    indice = aplicar_resumenes(plan, {Path("/logs/a.csv"): {"rpm_max": 6000.0}}, **VERSIONES)

    assert [e.ruta.name for e in indice.entradas] == ["a.csv"]

    # La próxima apertura pide justo los dos que faltaban.
    siguiente = planificar_indexado(entradas, indice, **VERSIONES)
    assert [e.ruta.name for e in siguiente.a_calcular] == ["b.csv", "c.csv"]
    assert [e.ruta.name for e in siguiente.reutilizables] == ["a.csv"]


def test_un_resumen_de_un_fichero_que_no_se_pidio_se_ignora() -> None:
    """Defensa contra un desajuste entre quien planifica y quien resume: colar en
    el índice una entrada que no estaba en la carpeta pondría en la tabla una fila
    de un fichero que nadie ha visto."""
    plan = planificar_indexado([entrada("a.csv")], None, **VERSIONES)
    indice = aplicar_resumenes(
        plan,
        {Path("/logs/a.csv"): {"x": 1}, Path("/otro/intruso.csv"): {"x": 2}},
        **VERSIONES,
    )
    assert [e.ruta.name for e in indice.entradas] == ["a.csv"]


def test_un_resumen_vacio_explicito_si_se_guarda() -> None:
    """Un resumen que salió sin ninguna métrica es un HECHO sobre el log (no
    tenía ninguno de los roles configurados), no una ausencia de cálculo. Se
    guarda, para no volver a resumirlo en cada apertura."""
    plan = planificar_indexado([entrada("a.csv")], None, **VERSIONES)
    indice = aplicar_resumenes(plan, {Path("/logs/a.csv"): {}}, **VERSIONES)
    assert len(indice.entradas) == 1
    assert indice.entradas[0].resumen == {}
    assert not planificar_indexado([entrada("a.csv")], indice, **VERSIONES).hay_trabajo


# --------------------------------------------------------------------------- #
# Serialización: ida y vuelta, y lo que se descarta
# --------------------------------------------------------------------------- #
def test_ida_y_vuelta_conserva_huella_y_resumen() -> None:
    indice = indexar([entrada("a.csv", tamano=42, mtime=7)], rpm_max=6500.0, lambda_min=0.74)
    buffer = io.BytesIO()
    escribir_indice(indice, buffer)
    leido = leer_indice(io.BytesIO(buffer.getvalue()))

    assert leido is not None
    assert leido.entradas == indice.entradas
    # Y la consecuencia que importa: tras la ida y vuelta, nada se recalcula.
    plan = planificar_indexado([entrada("a.csv", tamano=42, mtime=7)], leido, **VERSIONES)
    assert not plan.hay_trabajo


@pytest.mark.parametrize(
    ("etiqueta", "contenido"),
    [
        ("json inválido", b"{no es json"),
        ("vacío", b""),
        ("truncado", b'{"version_esquema": "1", "entra'),
        ("no es un objeto", b"[1, 2, 3]"),
        ("versión desconocida", b'{"version_esquema": "99", "entradas": []}'),
        ("entradas no es lista", b'{"version_esquema": "1", "entradas": {}}'),
        ("entrada sin clave", b'{"version_esquema": "1", "entradas": [{"resumen": {}}]}'),
        (
            "resumen no es objeto",
            b'{"version_esquema": "1", "entradas": [{"clave": {}, "resumen": 3}]}',
        ),
    ],
)
def test_un_indice_inservible_se_descarta_sin_lanzar(etiqueta: str, contenido: bytes) -> None:
    """El índice es una caché reconstruible: hacer fallar la apertura de una
    carpeta por un fichero de caché corrupto sería castigar al usuario por un
    problema que el programa arregla solo recalculando.

    Es la diferencia deliberada con `proyecto.py`, que sí lanza: allí hay trabajo
    del usuario y perderlo en silencio no es aceptable."""
    assert leer_indice(io.BytesIO(contenido)) is None, etiqueta


def test_lo_escrito_es_json_legible_por_una_persona() -> None:
    """El formato es JSON a propósito (ver la cabecera del módulo): un índice que
    se puede abrir con un editor cuando algo va mal vale más que los kilobytes
    que ahorraría un formato binario."""
    indice = indexar([entrada("a.csv")], rpm_max=6500.0)
    buffer = io.BytesIO()
    escribir_indice(indice, buffer)
    documento = json.loads(buffer.getvalue().decode("utf-8"))
    assert documento["version_esquema"] == VERSION_ESQUEMA_INDICE
    assert documento["entradas"][0]["resumen"] == {"rpm_max": 6500.0}
    assert documento["entradas"][0]["clave"]["mtime_ns"] == 111


def test_un_indice_sin_entradas_es_valido_y_no_es_lo_mismo_que_ninguno() -> None:
    """Una carpeta vacía ya indexada da un índice sin entradas, y eso NO puede
    leerse como «no hay índice»: si se confundieran, una carpeta vacía se
    reindexaría en cada apertura para siempre."""
    buffer = io.BytesIO()
    escribir_indice(Indice(), buffer)
    leido = leer_indice(io.BytesIO(buffer.getvalue()))
    assert leido is not None
    assert leido.entradas == ()


def test_las_rutas_con_caracteres_no_ascii_sobreviven() -> None:
    """Los logs del propietario están en carpetas en castellano; un índice que
    los machacara al serializar los recalcularía todos en cada apertura."""
    ruta = Path("/logs/Sesión pista — día 1/Log2768.csv")
    plan = planificar_indexado(
        [EntradaDeCarpeta(ruta=ruta, tamano_bytes=1, mtime_ns=1)], None, **VERSIONES
    )
    indice = aplicar_resumenes(plan, {ruta: {"x": 1}}, **VERSIONES)
    buffer = io.BytesIO()
    escribir_indice(indice, buffer)
    leido = leer_indice(io.BytesIO(buffer.getvalue()))
    assert leido is not None
    assert leido.entradas[0].ruta == ruta


# --------------------------------------------------------------------------- #
# Qué ficheros de la carpeta son candidatos
# --------------------------------------------------------------------------- #
def test_se_separan_los_candidatos_de_lo_que_no_es_un_log() -> None:
    rutas = [
        Path("/logs/a.csv"),
        Path("/logs/notas.pdf"),
        Path("/logs/b.CSV"),
        Path("/logs/proyecto.dlvproj"),
        Path("/logs/sin_extension"),
    ]
    candidatas, descartes = separar_candidatos(rutas)
    assert [p.name for p in candidatas] == ["a.csv", "b.CSV"]
    assert [d.ruta.name for d in descartes] == ["notas.pdf", "proyecto.dlvproj", "sin_extension"]


def test_la_extension_no_distingue_mayusculas() -> None:
    """Windows las escribe indistintamente: la misma carpeta copiada de un
    sistema a otro no puede dar tablas distintas."""
    candidatas, _ = separar_candidatos([Path("/l/A.CSV"), Path("/l/b.Csv")])
    assert len(candidatas) == 2


def test_cada_descarte_dice_por_que() -> None:
    """Si el usuario apunta el explorador a la carpeta equivocada y la tabla sale
    vacía, la diferencia entre «no hay logs» y «hay 40 ficheros y ninguno tiene
    extensión de log» es lo único que le dice qué hacer."""
    _, descartes = separar_candidatos([Path("/logs/notas.pdf")])
    assert len(descartes) == 1
    assert isinstance(descartes[0], Descarte)
    assert ".pdf" in descartes[0].motivo
    assert ".csv" in descartes[0].motivo


def test_una_carpeta_grande_se_planifica_sin_tocar_el_disco() -> None:
    """El presupuesto de §2.6 habla de 200 logs; aquí se planifican 5 000 para
    que quede claro que la parte de decisión no es la que cuesta, y que se puede
    probar con carpetas que sería incómodo crear de verdad."""
    entradas = [entrada(f"log{i:05d}.csv", mtime=i) for i in range(5000)]
    indice = indexar(entradas)
    plan = planificar_indexado(entradas, indice, **VERSIONES)
    assert plan.total_de_filas == 5000
    assert not plan.hay_trabajo
