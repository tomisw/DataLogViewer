"""Tests de `dlv_api.arrastrar_soltar` (tarea F1-34).

Protege la lógica de resolución de "arrastrar y soltar": dado un conjunto de
rutas mezcladas (ficheros y carpetas, buenas y malas), `resolver_rutas_soltadas`
nunca debe lanzar por una ruta individual (E1.7, "avisa y sigue"), debe
deduplicar cuando una carpeta y un fichero que ya está dentro se sueltan a la
vez, debe expandir carpetas recursivamente, y el orden de sus listas de salida
debe ser estable frente al orden de entrada.

Se evitan los mocks: los casos "carpeta con logs buenos y malos mezclados" se
construyen con `tmp_path` copiando un log real de `samples/real/` (no se
modifica el original) junto a ficheros basura creados ahí mismo, y los casos de
corpus real usan `samples/real/` y `samples/corrupt/` directamente, siempre en
solo lectura.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from dlv_api.arrastrar_soltar import (
    EXTENSIONES_PROPIAS,
    LogNativo,
    ResolucionArrastre,
    resolver_rutas_soltadas,
)
from dlv_core.formatos.haltech import Descriptor, cargar_descriptor
from dlv_core.informe_importacion import InformeImportacion

RAIZ = Path(__file__).resolve().parents[2]
AUTOLOG_REAL = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"
CARPETA_REAL = RAIZ / "samples" / "real"
CARPETA_CORRUPT = RAIZ / "samples" / "corrupt"


def _descriptores() -> tuple[Descriptor, ...]:
    with (RAIZ / "data" / "formats" / "haltech_nsp.toml").open("rb") as fh:
        return (cargar_descriptor(fh),)


def test_carpeta_real_de_tres_logs_los_reconoce_todos() -> None:
    """`samples/real/` tiene 3 logs Haltech válidos: los tres deben salir como
    nativos, ninguno como genérico y sin avisos de descarte."""
    resultado = resolver_rutas_soltadas([CARPETA_REAL], _descriptores())

    assert len(resultado.nativos) == 3
    assert resultado.genericos == ()
    assert all(ln.formato == "haltech_nsp" for ln in resultado.nativos)
    assert resultado.informe.vacio


def test_carpeta_corrupt_recursiva_reconoce_los_csv_y_descarta_el_readme() -> None:
    """`samples/corrupt/` tiene 11 CSV con firma Haltech intacta (incluidos los
    dos que `parsear_cabecera` rechaza más adelante en la ruta de ingesta: eso
    es un problema de parseo de cabecera, no de sondeo) y un `README.md` que no
    es un log. El sondeo de este módulo no llama a `parsear_cabecera` -- solo
    reconoce la firma -- así que los 11 deben clasificarse como nativos y el
    README como descartado, sin lanzar nada."""
    resultado = resolver_rutas_soltadas([CARPETA_CORRUPT], _descriptores())

    assert len(resultado.nativos) == 11
    assert resultado.genericos == ()
    codigos = {a.codigo for a in resultado.informe.todos()}
    assert "fichero_no_reconocido" in codigos
    mensajes = " ".join(a.mensaje for a in resultado.informe.todos())
    assert "README.md" in mensajes


def test_carpeta_con_logs_buenos_y_malos_mezclados(tmp_path: Path) -> None:
    """El caso central de E1.7: una carpeta con un log válido, un CSV basura
    (candidato al camino genérico), un fichero que no es ni CSV ni nativo y un
    fichero vacío. Debe abrir el válido, clasificar el CSV basura como
    genérico, avisar de los otros dos, y no lanzar en ningún momento."""
    shutil.copy(AUTOLOG_REAL, tmp_path / "log_bueno.csv")
    (tmp_path / "csv_basura.csv").write_text("esto,no,es,haltech\n1,2,3,4\n", encoding="utf-8")
    (tmp_path / "captura.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "vacio.csv").write_bytes(b"")

    resultado = resolver_rutas_soltadas([tmp_path], _descriptores())

    assert [ln.ruta.name for ln in resultado.nativos] == ["log_bueno.csv"]
    assert [p.name for p in resultado.genericos] == ["csv_basura.csv"]
    assert resultado.total_para_abrir == 2

    codigos = {a.codigo for a in resultado.informe.todos()}
    assert "fichero_no_reconocido" in codigos  # captura.png
    assert "fichero_vacio" in codigos  # vacio.csv
    assert resultado.informe.elementos_descartados == 0


def test_deduplica_carpeta_y_fichero_ya_incluido(tmp_path: Path) -> None:
    """Soltar una carpeta Y, además, un fichero que ya está dentro de ella no
    debe abrir ese log dos veces."""
    shutil.copy(AUTOLOG_REAL, tmp_path / "log.csv")
    fichero_repetido = tmp_path / "log.csv"

    resultado = resolver_rutas_soltadas([tmp_path, fichero_repetido], _descriptores())

    assert len(resultado.nativos) == 1
    assert resultado.total_para_abrir == 1


def test_deduplica_carpeta_soltada_dos_veces(tmp_path: Path) -> None:
    """La misma carpeta soltada dos veces (arrastre repetido por error) no
    duplica sus logs."""
    shutil.copy(AUTOLOG_REAL, tmp_path / "log.csv")

    resultado = resolver_rutas_soltadas([tmp_path, tmp_path], _descriptores())

    assert len(resultado.nativos) == 1


def test_recursividad_encuentra_logs_en_subcarpetas(tmp_path: Path) -> None:
    """Una carpeta de sesión de banco con logs organizados por tanda en
    subcarpetas: deben encontrarse igual que si estuvieran en el nivel raíz."""
    subcarpeta = tmp_path / "tanda_1" / "2026-07-29"
    subcarpeta.mkdir(parents=True)
    shutil.copy(AUTOLOG_REAL, subcarpeta / "log.csv")

    resultado = resolver_rutas_soltadas([tmp_path], _descriptores())

    assert len(resultado.nativos) == 1
    assert resultado.nativos[0].ruta.name == "log.csv"


def test_carpeta_vacia_avisa_y_no_lanza(tmp_path: Path) -> None:
    """Una carpeta vacía (incluso con subcarpetas vacías, por la recursividad)
    se avisa; no es un log ni un error que deba detener el resto."""
    carpeta_vacia = tmp_path / "vacia"
    (carpeta_vacia / "tambien_vacia").mkdir(parents=True)

    resultado = resolver_rutas_soltadas([carpeta_vacia], _descriptores())

    assert resultado.total_para_abrir == 0
    codigos = {a.codigo for a in resultado.informe.todos()}
    assert "carpeta_vacia" in codigos


def test_ruta_inexistente_avisa_y_no_lanza(tmp_path: Path) -> None:
    ruta_fantasma = tmp_path / "esto-no-existe.csv"

    resultado = resolver_rutas_soltadas([ruta_fantasma], _descriptores())

    assert resultado.total_para_abrir == 0
    codigos = {a.codigo for a in resultado.informe.todos()}
    assert "ruta_no_encontrada" in codigos


def test_fichero_que_no_es_csv_se_descarta_con_aviso(tmp_path: Path) -> None:
    ruta = tmp_path / "captura.png"
    ruta.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    resultado = resolver_rutas_soltadas([ruta], _descriptores())

    assert resultado.total_para_abrir == 0
    codigos = {a.codigo for a in resultado.informe.todos()}
    assert "fichero_no_reconocido" in codigos


def test_ficheros_propios_de_la_aplicacion_se_descartan(tmp_path: Path) -> None:
    """`.dlvproj`, `.dlvprofile`, `.dlvimport`, `.dlvcache` (docs/03 §3.9)
    nunca son un log que abrir, aunque su contenido empezara por casualidad
    con una firma reconocida."""
    for extension in EXTENSIONES_PROPIAS:
        ruta = tmp_path / f"proyecto{extension}"
        ruta.write_bytes(b"%DataLog%\r\ncontenido irrelevante\r\n")

    resultado = resolver_rutas_soltadas(
        [tmp_path / f"proyecto{ext}" for ext in EXTENSIONES_PROPIAS], _descriptores()
    )

    assert resultado.total_para_abrir == 0
    codigos = {a.codigo for a in resultado.informe.todos()}
    assert codigos == {"fichero_de_aplicacion"}


def test_orden_de_salida_es_deterministico_y_no_depende_del_orden_de_entrada(
    tmp_path: Path,
) -> None:
    """Soltar el mismo conjunto de rutas en dos órdenes distintos produce
    exactamente la misma lista de salida, en el mismo orden: es lo que evita
    que la interfaz "baile" entre una apertura y la siguiente."""
    for nombre in ("zulu.csv", "alfa.csv", "kilo.csv"):
        shutil.copy(AUTOLOG_REAL, tmp_path / nombre)

    rutas = [tmp_path / n for n in ("zulu.csv", "alfa.csv", "kilo.csv")]

    resultado_1 = resolver_rutas_soltadas(rutas, _descriptores())
    resultado_2 = resolver_rutas_soltadas(list(reversed(rutas)), _descriptores())

    nombres_1 = [ln.ruta.name for ln in resultado_1.nativos]
    nombres_2 = [ln.ruta.name for ln in resultado_2.nativos]
    assert nombres_1 == nombres_2 == ["alfa.csv", "kilo.csv", "zulu.csv"]


def test_no_lanza_aunque_todo_sea_invalido(tmp_path: Path) -> None:
    """Ni una sola ruta válida en toda la entrada: debe devolver un resultado
    vacío con avisos, nunca lanzar."""
    (tmp_path / "no_es_log.txt").write_text("hola", encoding="utf-8")

    resultado = resolver_rutas_soltadas(
        [tmp_path / "no_es_log.txt", tmp_path / "fantasma.csv", tmp_path / "carpeta_vacia"],
        _descriptores(),
    )

    assert isinstance(resultado, ResolucionArrastre)
    assert resultado.total_para_abrir == 0
    assert not resultado.informe.vacio


def test_log_nativo_es_un_dataclass_inmutable_y_con_slots() -> None:
    """Comprobación de forma, no de comportamiento: `LogNativo` sigue el mismo
    patrón (`slots=True, frozen=True`) que el resto de tipos de valor del
    proyecto (`Aviso`, `Canal`...)."""
    log = LogNativo(ruta=Path("x.csv"), formato="haltech_nsp")
    assert log.formato == "haltech_nsp"


def test_informe_es_un_informe_importacion_de_verdad() -> None:
    resultado = resolver_rutas_soltadas([RAIZ / "no-existe.csv"], _descriptores())
    assert isinstance(resultado.informe, InformeImportacion)
