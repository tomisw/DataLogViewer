"""Pruebas de la identidad en capas y el emparejamiento entre logs (F2-02).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.11.

QUÉ PROTEGE ESTA SUITE
======================
Emparejar mal no da una excepción: da **dos señales distintas superpuestas con
aspecto de ser la misma**. El tuner ve que el refrigerante del log B va 8 grados
por encima del log A y busca la causa en el motor, cuando la causa es que el
canal del log B era la temperatura de aceite.

Por eso las pruebas se ordenan por la consecuencia de romper cada regla:

1. **Un canal está en exactamente un grupo.** Si estuviera en dos, aparecería
   duplicado en el selector y en la vista concatenada.
2. **La capa nativa no cruza formatos.** Emparejar por ID a secas entre dos
   fabricantes da parejas aleatorias con aspecto de acierto.
3. **Los roles indexados no colapsan.** Los dos sensores de knock de un log
   comparten rol y se distinguen solo por el índice; agruparlos juntos haría
   desaparecer uno y compararía el otro contra el sensor equivocado.
4. **Un grupo ausente en un segmento es un hueco, no un cero** (§3.6).
5. **Dos canales del mismo log en el mismo grupo es un conflicto**, no una
   fusión: promediar dos sensores distintos en silencio es lo peor que se puede
   hacer aquí.

Solo biblioteca estándar.
"""

from __future__ import annotations

import pytest

from dlv_core.identidad import (
    CanalDeLog,
    Capa,
    EmparejamientoManual,
    ErrorDeIdentidad,
    emparejar,
)
from dlv_core.roles import Asignacion, ChannelKey, Confianza, normalizar


def canal(
    segmento: str,
    id_canal: str,
    *,
    rol: str | None = None,
    formato: str | None = "haltech_nsp",
    id_nativo: str | None = None,
    nombre: str | None = None,
    indice: int | None = None,
    difuso: bool = False,
) -> CanalDeLog:
    return CanalDeLog(
        id_segmento=segmento,
        id_canal=id_canal,
        clave=ChannelKey(
            rol=rol,
            formato=formato,
            id_nativo=id_nativo,
            nombre_normalizado=normalizar(nombre) if nombre else None,
        ),
        indice_rol=indice,
        etiqueta=nombre,
        requiere_confirmacion=difuso,
    )


def codigos(resultado: object) -> list[str]:
    return [a.codigo for a in resultado.avisos]  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# El orden de las capas
# --------------------------------------------------------------------------- #
def test_la_prioridad_de_las_capas_es_la_de_la_especificacion() -> None:
    assert [c.name for c in sorted(Capa, key=lambda c: c.prioridad)] == [
        "MANUAL",
        "ROL",
        "NATIVO",
        "NOMBRE",
    ]
    assert Capa.MANUAL.es_automatica is False
    assert Capa.ROL.es_automatica is True


def test_el_rol_empareja_entre_formatos_distintos() -> None:
    """El camino normal de §7.11: un Haltech y un MoTeC con el mismo rol."""
    r = emparejar(
        [
            canal("a", "1", rol="coolant_temp", formato="haltech_nsp", id_nativo="14"),
            canal("b", "9", rol="coolant_temp", formato="motec", id_nativo="207"),
        ],
        segmentos=["a", "b"],
    )
    assert len(r.grupos) == 1
    g = r.grupos[0]
    assert g.id == "rol:coolant_temp"
    assert g.capa is Capa.ROL
    assert g.segmentos == ("a", "b")
    assert g.es_comun


def test_el_rol_gana_al_id_nativo() -> None:
    """Si el rol empareja, el `(formato, ID)` no vuelve a agrupar lo mismo.

    Es el invariante «un canal en exactamente un grupo»: los dos canales tienen
    también el mismo (formato, ID), y aun así solo sale UN grupo, el del rol.
    """
    r = emparejar(
        [
            canal("a", "1", rol="coolant_temp", formato="haltech_nsp", id_nativo="14"),
            canal("b", "1", rol="coolant_temp", formato="haltech_nsp", id_nativo="14"),
        ],
        segmentos=["a", "b"],
    )
    assert len(r.grupos) == 1
    assert r.grupos[0].capa is Capa.ROL


def test_sin_rol_empareja_por_formato_e_id() -> None:
    """El caso Haltech de las muestras: los 25 IDs de los logs internos están
    también en el AutoLog (§1.3)."""
    r = emparejar(
        [
            canal("log2768", "c1", formato="haltech_nsp", id_nativo="14", nombre="RPM"),
            canal("log2769", "c1", formato="haltech_nsp", id_nativo="14", nombre="RPM"),
        ],
        segmentos=["log2768", "log2769"],
    )
    assert [g.id for g in r.grupos] == ["nativo:haltech_nsp:14"]
    assert r.grupos[0].capa is Capa.NATIVO


def test_la_capa_nativa_no_cruza_formatos() -> None:
    """La regla 2 de esta suite.

    El ID 14 de un fabricante no tiene nada que ver con el 14 de otro. Si esto
    emparejara, saldrían parejas aleatorias con aspecto de acierto, que es peor
    que no emparejar: no hay nada en la pantalla que lo delate.
    """
    r = emparejar(
        [
            canal("a", "c1", formato="haltech_nsp", id_nativo="14", nombre="RPM Haltech"),
            canal("b", "c1", formato="motec", id_nativo="14", nombre="Otra cosa"),
        ],
        segmentos=["a", "b"],
    )
    assert len(r.grupos) == 2
    assert {g.id for g in r.grupos} == {"nativo:haltech_nsp:14", "nativo:motec:14"}
    assert all(not g.es_comun for g in r.grupos)


def test_el_nombre_normalizado_es_el_ultimo_recurso_y_se_avisa() -> None:
    r = emparejar(
        [
            canal("a", "c1", formato=None, nombre="Coolant Temperature"),
            canal("b", "c1", formato=None, nombre="coolant_temperature"),
        ],
        segmentos=["a", "b"],
    )
    assert [g.id for g in r.grupos] == ["nombre:coolanttemperature"]
    assert r.grupos[0].capa is Capa.NOMBRE
    assert "emparejado_solo_por_nombre" in codigos(r)


def test_no_se_avisa_de_un_grupo_por_nombre_que_no_empareja_nada() -> None:
    """Un canal solo, identificado por su nombre, no afirma nada sobre nadie."""
    r = emparejar([canal("a", "c1", formato=None, nombre="Solo Yo")], segmentos=["a"])
    assert codigos(r) == []


def test_un_canal_esta_en_exactamente_un_grupo() -> None:
    """La regla 1, comprobada sobre un caso con las cuatro capas a la vez."""
    canales = [
        canal("a", "1", rol="coolant_temp", formato="haltech_nsp", id_nativo="14", nombre="CLT"),
        canal("b", "1", rol="coolant_temp", formato="haltech_nsp", id_nativo="14", nombre="CLT"),
        canal("a", "2", formato="haltech_nsp", id_nativo="20", nombre="Boost"),
        canal("b", "2", formato="haltech_nsp", id_nativo="20", nombre="Boost"),
        canal("a", "3", formato=None, nombre="Raro"),
        canal("b", "3", formato=None, nombre="raro"),
    ]
    r = emparejar(canales, segmentos=["a", "b"])
    apariciones: dict[tuple[str, str], int] = {}
    for g in r.grupos:
        for id_segmento, c in g.miembros.items():
            clave = (id_segmento, c.id_canal)
            apariciones[clave] = apariciones.get(clave, 0) + 1
    assert set(apariciones) == {(c.id_segmento, c.id_canal) for c in canales}
    assert all(n == 1 for n in apariciones.values()), apariciones
    assert {g.capa for g in r.grupos} == {Capa.ROL, Capa.NATIVO, Capa.NOMBRE}


# --------------------------------------------------------------------------- #
# Roles indexados
# --------------------------------------------------------------------------- #
def test_los_roles_indexados_no_colapsan() -> None:
    """La regla 3, y la carencia del modelo que esta tarea rodea.

    Los dos sensores de knock de un log reciben el MISMO rol (`knock_count`) y se
    distinguen solo por el índice que captura la marca `{n}` del sinónimo.
    `ChannelKey` no guarda ese índice, así que agrupar por `ChannelKey.rol` a
    secas colapsaría los dos en un grupo: uno desaparecería de la pantalla y el
    otro se compararía contra el sensor equivocado del otro log.
    """
    r = emparejar(
        [
            canal("a", "k1", rol="knock_count", indice=1, nombre="Knock Sensor 1 Knock Count"),
            canal("a", "k2", rol="knock_count", indice=2, nombre="Knock Sensor 2 Knock Count"),
            canal("b", "k1", rol="knock_count", indice=1, nombre="Knock Sensor 1 Knock Count"),
            canal("b", "k2", rol="knock_count", indice=2, nombre="Knock Sensor 2 Knock Count"),
        ],
        segmentos=["a", "b"],
    )
    assert {g.id for g in r.grupos} == {"rol:knock_count#1", "rol:knock_count#2"}
    assert all(g.segmentos == ("a", "b") for g in r.grupos)
    assert codigos(r) == [], "no hay conflicto: el índice los distingue"


def test_el_sensor_1_no_se_empareja_con_el_sensor_2() -> None:
    r = emparejar(
        [
            canal("a", "k1", rol="knock_count", indice=1),
            canal("b", "k2", rol="knock_count", indice=2),
        ],
        segmentos=["a", "b"],
    )
    assert {g.id for g in r.grupos} == {"rol:knock_count#1", "rol:knock_count#2"}
    assert all(not g.es_comun for g in r.grupos)


def test_un_rol_sin_indice_no_lleva_almohadilla() -> None:
    r = emparejar([canal("a", "c1", rol="coolant_temp")], segmentos=["a"])
    assert r.grupos[0].id == "rol:coolant_temp"


# --------------------------------------------------------------------------- #
# Conflictos y huecos
# --------------------------------------------------------------------------- #
def test_dos_canales_del_mismo_log_en_el_mismo_grupo_es_un_conflicto() -> None:
    """La regla 5: se queda uno y se avisa nombrando a los dos.

    Fusionarlos promediaría dos sensores distintos, y quedarse con uno en
    silencio haría desaparecer un canal del selector sin explicación.
    """
    r = emparejar(
        [
            canal("a", "c1", rol="coolant_temp", nombre="Coolant Temperature"),
            canal("a", "c2", rol="coolant_temp", nombre="Coolant Temperature 2"),
        ],
        segmentos=["a"],
    )
    assert "canales_del_mismo_log_en_el_mismo_grupo" in codigos(r)
    grupo_rol = r.por_capa(Capa.ROL)[0]
    assert list(grupo_rol.miembros) == ["a"]
    assert grupo_rol.miembros["a"].id_canal == "c1", "el primero por id, reproducible"
    # El descartado no desaparece: cae a una capa inferior y sigue siendo visible.
    assert any(
        g.miembros.get("a") is not None and g.miembros["a"].id_canal == "c2" for g in r.grupos
    ), "el canal descartado del grupo de rol tiene que seguir estando en algún grupo"


def test_el_mensaje_del_conflicto_dice_como_arreglarlo() -> None:
    r = emparejar(
        [
            canal("a", "c1", rol="knock_count", nombre="Knock A"),
            canal("a", "c2", rol="knock_count", nombre="Knock B"),
        ],
        segmentos=["a"],
    )
    mensaje = next(
        a.mensaje for a in r.avisos if a.codigo == "canales_del_mismo_log_en_el_mismo_grupo"
    )
    assert "Knock A" in mensaje and "Knock B" in mensaje
    assert "roles.toml" in mensaje or "manual" in mensaje


def test_un_grupo_ausente_en_un_segmento_da_hueco() -> None:
    """La regla 4 (§3.6): hueco, no ceros. Un cero es un valor plausible para
    casi cualquier canal, así que rellenar con ceros es inventar datos."""
    r = emparejar(
        [
            canal("a", "c1", rol="oil_pressure"),
            canal("a", "c2", rol="coolant_temp"),
            canal("b", "c1", rol="coolant_temp"),
        ],
        segmentos=["a", "b"],
    )
    aceite = r.por_id("rol:oil_pressure")
    assert aceite.presente_en("a") and not aceite.presente_en("b")
    assert aceite.ausentes(r.segmentos) == ("b",)
    assert aceite.canal_en("b") is None
    refrigerante = r.por_id("rol:coolant_temp")
    assert refrigerante.ausentes(r.segmentos) == ()


def test_un_segmento_sin_ningun_canal_sigue_contando_para_los_huecos() -> None:
    """Por eso `segmentos` se pide aparte y no se deduce de `canales`.

    Un log que se abre y no aporta nada a un grupo tiene que aparecer como hueco;
    si la lista de segmentos saliera de los canales, desaparecería de la cuenta.
    """
    r = emparejar([canal("a", "c1", rol="coolant_temp")], segmentos=["a", "b", "c"])
    assert r.por_id("rol:coolant_temp").ausentes(r.segmentos) == ("b", "c")
    assert r.comunes_a_todos() == ()


def test_comunes_y_comunes_a_todos() -> None:
    r = emparejar(
        [
            canal("a", "c1", rol="coolant_temp"),
            canal("b", "c1", rol="coolant_temp"),
            canal("c", "c1", rol="coolant_temp"),
            canal("a", "c2", rol="oil_temp"),
            canal("b", "c2", rol="oil_temp"),
            canal("a", "c3", rol="oil_pressure"),
        ],
        segmentos=["a", "b", "c"],
    )
    assert {g.id for g in r.comunes} == {"rol:coolant_temp", "rol:oil_temp"}
    assert {g.id for g in r.comunes_a_todos()} == {"rol:coolant_temp"}


def test_un_canal_sin_ninguna_identidad_se_avisa() -> None:
    r = emparejar([canal("a", "c1", formato=None, nombre=None)], segmentos=["a"])
    assert r.grupos == ()
    assert codigos(r) == ["canal_sin_identidad"]


# --------------------------------------------------------------------------- #
# Emparejamiento manual
# --------------------------------------------------------------------------- #
def test_lo_manual_gana_sobre_el_rol() -> None:
    """§7.11 punto 4: prioridad máxima, incluso contra un rol que ya emparejaba."""
    r = emparejar(
        [
            canal("a", "c1", rol="coolant_temp", nombre="CLT A"),
            canal("b", "c1", rol="coolant_temp", nombre="CLT B"),
            canal("b", "c2", rol="oil_temp", nombre="Aceite B"),
        ],
        segmentos=["a", "b"],
        manuales=[EmparejamientoManual("CLT contra aceite", {"a": "c1", "b": "c2"})],
    )
    manual = r.por_capa(Capa.MANUAL)[0]
    assert manual.id == "manual:CLT contra aceite"
    assert manual.miembros["b"].id_canal == "c2"
    # El canal de rol que se quedó suelto sigue existiendo, en su propio grupo.
    assert r.grupo_de("b", "c1").capa is Capa.ROL
    assert "manual_contradice_rol" in codigos(r)


def test_lo_manual_con_el_mismo_rol_no_avisa_de_contradiccion() -> None:
    r = emparejar(
        [canal("a", "c1", rol="coolant_temp"), canal("b", "c9", rol="coolant_temp")],
        segmentos=["a", "b"],
        manuales=[EmparejamientoManual("Refrigerante", {"a": "c1", "b": "c9"})],
    )
    assert codigos(r) == []
    assert r.por_capa(Capa.MANUAL)[0].segmentos == ("a", "b")


def test_un_manual_que_cita_un_canal_inexistente_se_aplica_con_el_resto() -> None:
    r = emparejar(
        [
            canal("a", "c1", rol="coolant_temp"),
            canal("b", "c1", rol="coolant_temp"),
            canal("c", "c1", rol="coolant_temp"),
        ],
        segmentos=["a", "b", "c"],
        manuales=[
            EmparejamientoManual("Tres", {"a": "c1", "b": "c1", "c": "no-existe"}),
        ],
    )
    manual = r.por_capa(Capa.MANUAL)[0]
    assert manual.segmentos == ("a", "b")
    assert "manual_no_aplicable" in codigos(r)
    # El canal del segmento 'c' que no se citó bien sigue emparejándose solo.
    assert r.grupo_de("c", "c1").capa is Capa.ROL


def test_un_manual_que_se_queda_con_un_solo_canal_se_descarta_y_devuelve_el_canal() -> None:
    """No se pierde nada: el canal vuelve al emparejamiento automático.

    Si se quedara en un grupo manual de un miembro, el canal dejaría de
    emparejarse con su rol y el usuario perdería la comparación sin haber pedido
    eso.
    """
    r = emparejar(
        [canal("a", "c1", rol="coolant_temp"), canal("b", "c1", rol="coolant_temp")],
        segmentos=["a", "b"],
        manuales=[EmparejamientoManual("Cojo", {"a": "c1", "b": "no-existe"})],
    )
    assert r.por_capa(Capa.MANUAL) == ()
    assert {"manual_no_aplicable", "manual_descartado"} <= set(codigos(r))
    assert r.por_id("rol:coolant_temp").segmentos == ("a", "b")


def test_dos_manuales_no_se_pelean_por_el_mismo_canal() -> None:
    r = emparejar(
        [
            canal("a", "c1", rol="coolant_temp"),
            canal("b", "c1", rol="coolant_temp"),
            canal("c", "c1", rol="coolant_temp"),
        ],
        segmentos=["a", "b", "c"],
        manuales=[
            EmparejamientoManual("Primero", {"a": "c1", "b": "c1"}),
            EmparejamientoManual("Segundo", {"a": "c1", "c": "c1"}),
        ],
    )
    assert [g.id for g in r.por_capa(Capa.MANUAL)] == ["manual:Primero"]
    assert "manual_no_aplicable" in codigos(r)


def test_un_manual_de_menos_de_dos_miembros_no_se_puede_ni_construir() -> None:
    with pytest.raises(ErrorDeIdentidad, match="al menos dos"):
        EmparejamientoManual("Solo uno", {"a": "c1"})


def test_un_manual_sin_nombre_no_se_puede_construir() -> None:
    with pytest.raises(ErrorDeIdentidad, match="nombre"):
        EmparejamientoManual("   ", {"a": "c1", "b": "c1"})


# --------------------------------------------------------------------------- #
# Confianza difusa
# --------------------------------------------------------------------------- #
def test_un_miembro_difuso_marca_el_grupo_entero() -> None:
    """Mitigación 4 de §7.15: basta un miembro dudoso.

    Un grupo con un miembro asignado por parecido ya no sirve para un detector
    crítico: la comparación entre logs saldría de un canal que puede no ser el
    que se cree.
    """
    r = emparejar(
        [
            canal("a", "c1", rol="coolant_temp", difuso=False),
            canal("b", "c1", rol="coolant_temp", difuso=True),
        ],
        segmentos=["a", "b"],
    )
    assert r.por_id("rol:coolant_temp").requiere_confirmacion is True


def test_un_grupo_sin_difusos_no_pide_confirmacion() -> None:
    r = emparejar(
        [canal("a", "c1", rol="coolant_temp"), canal("b", "c1", rol="coolant_temp")],
        segmentos=["a", "b"],
    )
    assert r.por_id("rol:coolant_temp").requiere_confirmacion is False


def test_desde_asignacion_no_pierde_el_indice_ni_la_confianza() -> None:
    """El puente con FG-09: si el índice se perdiera aquí, los roles indexados
    colapsarían más adelante y el síntoma aparecería lejos de la causa."""
    c = CanalDeLog.desde_asignacion(
        id_segmento="a",
        id_canal="c1",
        nombre="Knock Sensor 2 Knock Count",
        formato="haltech_nsp",
        id_nativo="31",
        asignacion=Asignacion(
            rol="knock_count",
            confianza=Confianza.INDEXADA,
            sinonimo="Knock Sensor {n} Knock Count",
            indice=2,
        ),
    )
    assert c.indice_rol == 2
    assert c.clave.rol == "knock_count"
    assert c.clave.nombre_normalizado == normalizar("Knock Sensor 2 Knock Count")
    assert c.etiqueta == "Knock Sensor 2 Knock Count"
    assert c.requiere_confirmacion is False

    difuso = CanalDeLog.desde_asignacion(
        id_segmento="a",
        id_canal="c2",
        nombre="Temp Agua",
        formato="generico",
        id_nativo=None,
        asignacion=Asignacion(
            rol="coolant_temp", confianza=Confianza.DIFUSA, sinonimo="Coolant Temp", parecido=0.82
        ),
    )
    assert difuso.requiere_confirmacion is True
    assert difuso.indice_rol is None


def test_desde_asignacion_sin_rol() -> None:
    c = CanalDeLog.desde_asignacion(
        id_segmento="a",
        id_canal="c1",
        nombre="Bootmode Reason",
        formato="haltech_nsp",
        id_nativo="99",
        asignacion=None,
    )
    assert c.clave.rol is None and c.indice_rol is None
    assert c.requiere_confirmacion is False


# --------------------------------------------------------------------------- #
# Contratos de entrada y consultas
# --------------------------------------------------------------------------- #
def test_un_canal_de_un_segmento_desconocido_es_un_error() -> None:
    with pytest.raises(ErrorDeIdentidad, match="no está entre los abiertos"):
        emparejar([canal("z", "c1", rol="coolant_temp")], segmentos=["a", "b"])


def test_ids_de_segmento_repetidos_es_un_error() -> None:
    with pytest.raises(ErrorDeIdentidad, match="repetidos"):
        emparejar([], segmentos=["a", "a"])


def test_el_mismo_id_de_canal_dos_veces_en_un_segmento_es_un_error() -> None:
    with pytest.raises(ErrorDeIdentidad, match="dos veces"):
        emparejar(
            [canal("a", "c1", rol="coolant_temp"), canal("a", "c1", rol="oil_temp")],
            segmentos=["a"],
        )


def test_sin_canales_no_hay_grupos_pero_si_segmentos() -> None:
    r = emparejar([], segmentos=["a", "b"])
    assert r.grupos == ()
    assert r.segmentos == ("a", "b")


def test_las_consultas_fallan_con_nombre_y_no_con_keyerror() -> None:
    r = emparejar([canal("a", "c1", rol="coolant_temp")], segmentos=["a"])
    with pytest.raises(ErrorDeIdentidad, match="ningún grupo con id"):
        r.por_id("rol:no-existe")
    with pytest.raises(ErrorDeIdentidad, match="no está en ningún grupo"):
        r.grupo_de("a", "no-existe")


def test_el_orden_de_los_grupos_es_reproducible() -> None:
    """Por capa y luego por id. El frontend guarda estos ids en el proyecto, así
    que un orden que dependa del recorrido de un diccionario abriría el mismo
    proyecto distinto dos veces."""
    canales = [
        canal("a", "c1", rol="oil_temp"),
        canal("a", "c2", rol="coolant_temp"),
        canal("a", "c3", formato="haltech_nsp", id_nativo="7", nombre="Sin rol"),
        canal("a", "c4", formato=None, nombre="Solo nombre"),
    ]
    esperado = [g.id for g in emparejar(canales, segmentos=["a"]).grupos]
    for permutacion in ([1, 0, 3, 2], [3, 2, 1, 0], [2, 3, 0, 1]):
        otros = [canales[i] for i in permutacion]
        assert [g.id for g in emparejar(otros, segmentos=["a"]).grupos] == esperado
    assert esperado == [
        "rol:coolant_temp",
        "rol:oil_temp",
        "nativo:haltech_nsp:7",
        "nombre:solonombre",
    ]


def test_los_dos_logs_internos_y_el_autolog_reales() -> None:
    """El caso de las muestras: los 25 IDs de `Log2768/2769` están también en el
    AutoLog (§1.3), así que emparejan por `(formato, ID)` sin necesitar roles.
    """
    canales = []
    for segmento in ("autolog", "log2768", "log2769"):
        for id_nativo in ("14", "20", "31"):
            canales.append(
                canal(segmento, f"c{id_nativo}", formato="haltech_nsp", id_nativo=id_nativo)
            )
    # El AutoLog trae además canales que los logs internos no tienen.
    canales.append(canal("autolog", "c99", formato="haltech_nsp", id_nativo="99"))

    r = emparejar(canales, segmentos=["autolog", "log2768", "log2769"])
    assert len(r.comunes_a_todos()) == 3
    solo_autolog = r.por_id("nativo:haltech_nsp:99")
    assert solo_autolog.ausentes(r.segmentos) == ("log2768", "log2769")
