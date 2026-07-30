"""Pruebas del informe de importación acumulativo y no bloqueante (F1-12).

Estilo igual que `test_limpieza.py`: casos de juguete para las reglas del
acumulador en sí, y un caso de integración contra logs reales y del corpus de
`samples/corrupt/` para comprobar que las etapas que ya producen `Aviso`
(`Cabecera`, `detectar_filas_malformadas`, `Reconciliacion`) se pueden juntar
sin ningún adaptador.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dlv_core.formatos.haltech import Descriptor, cargar_descriptor, parsear_cabecera
from dlv_core.formatos.limpieza import detectar_filas_malformadas
from dlv_core.informe_importacion import (
    CODIGO_SIN_ESPECIFICAR,
    SEVERIDAD_ADVERTENCIA,
    SEVERIDAD_INFORMATIVA,
    GrupoDeAvisos,
    InformeImportacion,
    aviso_de_retrocesos_anomalos,
    severidad_de_codigo,
)
from dlv_core.informes import Aviso
from dlv_core.reloj import Desenrollado, PoliticaReloj, reconciliar

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
REALES = RAIZ / "samples" / "real"
CORRUPTOS = RAIZ / "samples" / "corrupt"


@pytest.fixture(scope="module")
def desc() -> Descriptor:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return cargar_descriptor(fh)


# --------------------------------------------------------------------------- #
# Informe vacío
# --------------------------------------------------------------------------- #
def test_informe_recien_creado_esta_vacio() -> None:
    informe = InformeImportacion()
    assert informe.vacio
    assert informe.total == 0
    assert informe.todos() == ()
    assert informe.por_codigo() == {}
    assert informe.resumen() == ()
    assert informe.elementos_descartados == 0


def test_a_lineas_vacio_dice_que_no_hay_anomalias() -> None:
    informe = InformeImportacion()
    lineas = informe.a_lineas()
    assert len(lineas) == 1
    assert "sin" in lineas[0].lower() or "ningun" in lineas[0].lower()


def test_agregar_una_lista_vacia_sigue_vacio() -> None:
    informe = InformeImportacion()
    informe.agregar([])
    assert informe.vacio


# --------------------------------------------------------------------------- #
# Acumulación: literal, de varias etapas, en cualquier orden
# --------------------------------------------------------------------------- #
def test_agregar_una_etapa() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("tipo_desconocido", "canal X en crudo")])
    assert informe.total == 1
    assert not informe.vacio


def test_agregar_varias_etapas_por_separado_se_acumula() -> None:
    """No se sabe de antemano cuántas etapas van a aportar avisos: cada una
    llama a `agregar` con lo que tenga, y el total es la suma."""
    informe = InformeImportacion()
    informe.agregar([Aviso("tipo_desconocido", "de la cabecera")])
    informe.agregar([Aviso("fila_malformada", "fila 12"), Aviso("fila_malformada", "fila 40")])
    informe.agregar((Aviso("reloj_sin_metadato", "sin Log"),))  # tupla, no lista
    assert informe.total == 4


def test_aceptar_tupla_y_lista_sin_ceremonia() -> None:
    """`Cabecera.avisos` es `list[Aviso]`; `Reconciliacion.avisos` es
    `tuple[Aviso, ...]`. `agregar` no debe distinguir."""
    informe = InformeImportacion()
    informe.agregar([Aviso("a", "de lista")])
    informe.agregar((Aviso("b", "de tupla"),))
    assert {a.codigo for a in informe.todos()} == {"a", "b"}


def test_todos_preserva_el_orden_de_llegada() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("uno", "1"), Aviso("dos", "2")])
    informe.agregar([Aviso("tres", "3")])
    assert [a.codigo for a in informe.todos()] == ["uno", "dos", "tres"]


def test_el_orden_de_las_llamadas_a_agregar_no_importa_para_el_resumen() -> None:
    a = InformeImportacion()
    a.agregar([Aviso("x", "1")])
    a.agregar([Aviso("y", "1"), Aviso("y", "2")])

    b = InformeImportacion()
    b.agregar([Aviso("y", "1"), Aviso("y", "2")])
    b.agregar([Aviso("x", "1")])

    assert a.resumen() == b.resumen()


# --------------------------------------------------------------------------- #
# Agrupamiento por código
# --------------------------------------------------------------------------- #
def test_por_codigo_agrupa_correctamente() -> None:
    informe = InformeImportacion()
    informe.agregar(
        [
            Aviso("escala_sin_confirmar", "canal 1"),
            Aviso("escala_sin_confirmar", "canal 2"),
            Aviso("escala_sin_confirmar", "canal 3"),
            Aviso("nombre_duplicado", "canal 4"),
        ]
    )
    agrupado = informe.por_codigo()
    assert set(agrupado) == {"escala_sin_confirmar", "nombre_duplicado"}
    assert len(agrupado["escala_sin_confirmar"]) == 3
    assert len(agrupado["nombre_duplicado"]) == 1


def test_resumen_no_repite_300_veces_el_mismo_aviso() -> None:
    """El caso motivador de la tarea: 300 canales con el mismo código deben
    resumirse en un único grupo, no en 300 líneas."""
    informe = InformeImportacion()
    informe.agregar(Aviso("escala_sin_confirmar", f"canal {i}") for i in range(300))
    resumen = informe.resumen()
    assert len(resumen) == 1
    assert resumen[0].codigo == "escala_sin_confirmar"
    assert resumen[0].cantidad == 300
    # El detalle completo sigue disponible para quien lo quiera.
    assert informe.total == 300


def test_resumen_ordena_por_cantidad_descendente_luego_por_codigo() -> None:
    informe = InformeImportacion()
    informe.agregar(
        [
            Aviso("b_codigo", "1"),
            Aviso("a_codigo", "1"),
            Aviso("a_codigo", "2"),
            Aviso("c_codigo", "1"),
            Aviso("c_codigo", "2"),
        ]
    )
    codigos_en_orden = [g.codigo for g in informe.resumen()]
    # a_codigo y c_codigo empatan a 2: desempate alfabético.
    assert codigos_en_orden == ["a_codigo", "c_codigo", "b_codigo"]


def test_grupo_de_avisos_es_coherente() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("id_duplicado", "1"), Aviso("id_duplicado", "2")])
    (grupo,) = informe.resumen()
    assert isinstance(grupo, GrupoDeAvisos)
    assert grupo.cantidad == len(grupo.avisos) == 2


# --------------------------------------------------------------------------- #
# Severidad derivada del código
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "codigo",
    [
        "tipo_desconocido",
        "escala_sin_confirmar",
        "id_duplicado",
        "fila_malformada",
        "reloj_no_fiable",
        "reloj_sin_orden",
    ],
)
def test_codigos_de_perdida_o_ambiguedad_son_advertencia(codigo: str) -> None:
    assert severidad_de_codigo(codigo) == SEVERIDAD_ADVERTENCIA


@pytest.mark.parametrize(
    "codigo",
    [
        "nombre_duplicado",
        "displaymaxmin_invalida",
        "reloj_sin_metadato",
        "reloj_metadato_ilegible",
        "epoca_ficticia",
        "cabecera_antes_de_medianoche",
        "descarga_anterior_al_log",
    ],
)
def test_codigos_de_degradacion_conocida_son_informativa(codigo: str) -> None:
    assert severidad_de_codigo(codigo) == SEVERIDAD_INFORMATIVA


def test_codigo_desconocido_se_clasifica_como_advertencia_por_omision() -> None:
    """Mejor visible de más que oculto de menos ante un código que este módulo
    todavía no conoce."""
    assert severidad_de_codigo("codigo_que_no_existe_todavia") == SEVERIDAD_ADVERTENCIA


def test_resumen_lleva_la_severidad_de_cada_grupo() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("epoca_ficticia", "..."), Aviso("reloj_no_fiable", "...")])
    por_codigo = {g.codigo: g.severidad for g in informe.resumen()}
    assert por_codigo["epoca_ficticia"] == SEVERIDAD_INFORMATIVA
    assert por_codigo["reloj_no_fiable"] == SEVERIDAD_ADVERTENCIA


# --------------------------------------------------------------------------- #
# No bloqueante: nunca lanza, incluso con avisos "raros"
# --------------------------------------------------------------------------- #
def test_codigo_vacio_se_normaliza_y_no_se_pierde_el_mensaje() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("", "un aviso sin código asignado")])
    assert informe.total == 1
    (aviso,) = informe.todos()
    assert aviso.codigo == CODIGO_SIN_ESPECIFICAR
    assert aviso.mensaje == "un aviso sin código asignado"


def test_codigo_en_blanco_tambien_se_normaliza() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("   ", "mensaje")])
    assert informe.todos()[0].codigo == CODIGO_SIN_ESPECIFICAR


def test_mensaje_vacio_se_tolera_sin_lanzar() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("codigo_valido", "")])
    assert informe.total == 1
    assert informe.todos()[0].mensaje == ""


def test_ambos_vacios_no_lanza_y_se_cuenta() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("", "")])
    assert informe.total == 1
    assert informe.todos()[0].codigo == CODIGO_SIN_ESPECIFICAR


def test_elemento_que_no_es_aviso_se_descarta_sin_lanzar() -> None:
    """Ceder a pesar del tipado: si algo que no es un `Aviso` se cuela en el
    iterable, este módulo no debe ser la causa de que la importación falle."""
    informe = InformeImportacion()
    objetos_raros: list[Any] = [object(), None, 42, "no soy un aviso", {"codigo": "x"}]
    informe.agregar(objetos_raros)  # type: ignore[arg-type]
    assert informe.vacio
    assert informe.elementos_descartados == len(objetos_raros)


def test_mezcla_de_avisos_validos_y_elementos_raros() -> None:
    informe = InformeImportacion()
    mezcla: list[Any] = [Aviso("valido", "ok"), object(), Aviso("otro_valido", "ok también")]
    informe.agregar(mezcla)  # type: ignore[arg-type]
    assert informe.total == 2
    assert informe.elementos_descartados == 1


# --------------------------------------------------------------------------- #
# Representaciones textual y serializable
# --------------------------------------------------------------------------- #
def test_a_lineas_incluye_resumen_y_detalle() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("fila_malformada", "fila 7", 7), Aviso("fila_malformada", "fila 9", 9)])
    lineas = informe.a_lineas()
    texto = "\n".join(lineas)
    assert "2 aviso" in texto
    assert "fila_malformada" in texto
    assert "fila 7" in texto and "fila 9" in texto


def test_a_dict_es_serializable_y_completo() -> None:
    informe = InformeImportacion()
    informe.agregar([Aviso("epoca_ficticia", "sin reloj", None)])
    datos = informe.a_dict()
    assert datos["total"] == 1
    assert datos["vacio"] is False
    assert datos["elementos_descartados"] == 0
    assert datos["resumen"] == [
        {"codigo": "epoca_ficticia", "cantidad": 1, "severidad": SEVERIDAD_INFORMATIVA}
    ]
    assert datos["avisos"] == [{"codigo": "epoca_ficticia", "mensaje": "sin reloj", "linea": None}]

    import json

    json.dumps(datos)  # no debe lanzar: es JSON-friendly de verdad


def test_a_dict_vacio() -> None:
    assert InformeImportacion().a_dict()["avisos"] == []


# --------------------------------------------------------------------------- #
# `Desenrollado.retrocesos_anomalos` envuelto en `Aviso`
# --------------------------------------------------------------------------- #
def test_sin_retrocesos_no_hay_aviso() -> None:
    d = Desenrollado(t=[0.0, 1.0], cruces_de_medianoche=0, retrocesos_anomalos=0)
    assert aviso_de_retrocesos_anomalos(d) is None


def test_cruce_de_medianoche_normal_no_produce_aviso() -> None:
    """Un cruce genuino se desenrolla y queda resuelto: no es una anomalía que
    el usuario deba revisar, a diferencia de un retroceso que no se corrige."""
    d = Desenrollado(t=[0.0, 1.0], cruces_de_medianoche=3, retrocesos_anomalos=0)
    assert aviso_de_retrocesos_anomalos(d) is None


def test_retrocesos_anomalos_produce_un_aviso_con_el_conteo() -> None:
    d = Desenrollado(t=[0.0, 1.0], cruces_de_medianoche=0, retrocesos_anomalos=5)
    aviso = aviso_de_retrocesos_anomalos(d)
    assert aviso is not None
    assert aviso.codigo == "retroceso_anomalo"
    assert "5" in aviso.mensaje


def test_el_aviso_de_retrocesos_se_puede_agregar_al_informe() -> None:
    informe = InformeImportacion()
    d = Desenrollado(t=[0.0, 1.0], cruces_de_medianoche=1, retrocesos_anomalos=2)
    aviso = aviso_de_retrocesos_anomalos(d)
    assert aviso is not None
    informe.agregar([aviso])
    assert informe.total == 1
    assert severidad_de_codigo(informe.todos()[0].codigo) == SEVERIDAD_ADVERTENCIA


# --------------------------------------------------------------------------- #
# Integración: etapas reales de la ruta de ingesta, sin adaptador
# --------------------------------------------------------------------------- #
def test_integra_avisos_reales_de_cabecera_cuerpo_y_reloj(desc: Descriptor) -> None:
    """El caso que de verdad importa: `Cabecera.avisos` (`list`),
    `detectar_filas_malformadas` (`list`) y `Reconciliacion.avisos` (`tuple`)
    se pasan tal cual a `agregar`, sin envolver nada."""
    informe = InformeImportacion()

    # Etapa 1: cabecera del AutoLog real (tiene canales sin escala confirmada).
    datos_autolog = (REALES / "AutoLog_20260729_1830.csv").read_bytes()
    cab = parsear_cabecera(datos_autolog, desc)
    informe.agregar(cab.avisos)
    assert any(a.codigo == "escala_sin_confirmar" for a in cab.avisos), (
        "si esto falla, el fixture ya no ejercita el caso que se quería probar"
    )

    # Etapa 2: filas malformadas de dos ficheros del corpus de corruptos.
    for nombre in ("02-fila-corta.csv", "03-fila-larga.csv"):
        datos = (CORRUPTOS / nombre).read_bytes()
        cab_corrupta = parsear_cabecera(datos, desc)
        informe.agregar(detectar_filas_malformadas(datos, cab_corrupta))

    # Etapa 3: reconciliación de reloj de los dos logs internos (época ficticia).
    with DESCRIPTOR_TOML.open("rb") as fh:
        import tomllib

        politica = PoliticaReloj.desde_mapa(tomllib.load(fh)["reloj"])
    for numero in ("2768", "2769"):
        r = reconciliar(
            {"Log": "19800101 01:01:01", "Log Number": numero},
            3661.005,
            politica=politica,
        )
        informe.agregar(r.avisos)

    assert not informe.vacio
    codigos = set(informe.por_codigo())
    assert "escala_sin_confirmar" in codigos
    assert "fila_malformada" in codigos
    assert "epoca_ficticia" in codigos

    # Dos logs con época ficticia: el grupo agrupa los dos avisos idénticos.
    grupo_epoca = next(g for g in informe.resumen() if g.codigo == "epoca_ficticia")
    assert grupo_epoca.cantidad == 2
    assert grupo_epoca.severidad == SEVERIDAD_INFORMATIVA

    grupo_filas = next(g for g in informe.resumen() if g.codigo == "fila_malformada")
    assert grupo_filas.severidad == SEVERIDAD_ADVERTENCIA

    # Nada de esto debió requerir descartar ningún elemento.
    assert informe.elementos_descartados == 0


def test_fichero_bien_formado_aporta_pocos_o_ningun_aviso_de_filas(desc: Descriptor) -> None:
    """Complemento del caso de integración: un fichero sano no debe inflar el
    informe con avisos de filas malformadas."""
    datos = (REALES / "AutoLog_20260729_1830.csv").read_bytes()
    cab = parsear_cabecera(datos, desc)
    informe = InformeImportacion()
    informe.agregar(detectar_filas_malformadas(datos, cab))
    assert informe.vacio
