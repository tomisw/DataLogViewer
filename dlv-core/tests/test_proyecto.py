"""Pruebas de la colección de emparejamientos manuales del proyecto (F2-03).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.11 punto 4 y
`docs/03-arquitectura.md` §3.9 (`.dlvproj`, JSON versionado).

QUÉ PROTEGE ESTA SUITE
======================
1. **Rechazo antes de guardar, no aviso después de aplicar.** `identidad.
   emparejar` ya avisa si un canal cae en dos emparejamientos manuales, pero
   solo al aplicarlos; esta colección tiene que rechazarlo en el momento en
   que el usuario todavía puede corregirlo (al construir o al `agregar()`).
2. **Nombres únicos**, con el mismo motivo: dos emparejamientos con el mismo
   nombre son indistinguibles en la interfaz.
3. **Ida y vuelta exacta por `dict`/JSON**, y una versión de esquema
   desconocida que falla con un error con nombre propio en vez de leerse a
   medias.
4. **`a_secuencia()` es la forma exacta que pide `identidad.emparejar`**: sin
   conversión intermedia, y de verdad produce el emparejamiento esperado
   cuando se le pasan canales reales.

Solo biblioteca estándar.
"""

from __future__ import annotations

import pytest

from dlv_core.identidad import (
    CanalDeLog,
    Capa,
    EmparejamientoManual,
    emparejar,
)
from dlv_core.proyecto import (
    VERSION_ESQUEMA_EMPAREJAMIENTOS,
    EmparejamientosManuales,
    ErrorDeProyecto,
    ErrorDeVersionDesconocida,
)
from dlv_core.roles import ChannelKey, normalizar


def canal(segmento: str, id_canal: str, *, nombre: str | None = None) -> CanalDeLog:
    """Mismo helper que `test_identidad.py`: un canal sin rol ni ID nativo, para
    que lo único que lo pueda emparejar sea lo manual."""
    return CanalDeLog(
        id_segmento=segmento,
        id_canal=id_canal,
        clave=ChannelKey(
            rol=None,
            formato=None,
            id_nativo=None,
            nombre_normalizado=normalizar(nombre) if nombre else None,
        ),
        etiqueta=nombre,
    )


# --------------------------------------------------------------------------- #
# Colección vacía y consulta básica
# --------------------------------------------------------------------------- #
def test_coleccion_vacia_por_omision() -> None:
    coleccion = EmparejamientosManuales()
    assert len(coleccion) == 0
    assert coleccion.nombres == ()
    assert list(coleccion) == []


def test_agregar_y_consultar_por_nombre() -> None:
    e = EmparejamientoManual(nombre="mi pareja", miembros={"a": "1", "b": "2"})
    coleccion = EmparejamientosManuales().agregar(e)
    assert len(coleccion) == 1
    assert coleccion.existe("mi pareja")
    assert coleccion.obtener("mi pareja") is e
    assert coleccion.nombres == ("mi pareja",)


def test_agregar_no_muta_la_coleccion_original() -> None:
    """Inmutable a propósito: una referencia ya entregada no cambia por debajo."""
    original = EmparejamientosManuales()
    nueva = original.agregar(EmparejamientoManual(nombre="x", miembros={"a": "1", "b": "2"}))
    assert len(original) == 0
    assert len(nueva) == 1


def test_obtener_nombre_inexistente_da_error_con_nombre() -> None:
    with pytest.raises(ErrorDeProyecto, match="no hay ningún emparejamiento"):
        EmparejamientosManuales().obtener("fantasma")


def test_quitar_devuelve_coleccion_sin_ese_emparejamiento() -> None:
    e1 = EmparejamientoManual(nombre="uno", miembros={"a": "1", "b": "2"})
    e2 = EmparejamientoManual(nombre="dos", miembros={"a": "3", "b": "4"})
    coleccion = EmparejamientosManuales().agregar(e1).agregar(e2)

    restante = coleccion.quitar("uno")
    assert restante.nombres == ("dos",)
    # La original, sin tocar.
    assert coleccion.nombres == ("uno", "dos")


def test_quitar_nombre_inexistente_da_error_con_nombre() -> None:
    coleccion = EmparejamientosManuales().agregar(
        EmparejamientoManual(nombre="uno", miembros={"a": "1", "b": "2"})
    )
    with pytest.raises(ErrorDeProyecto, match="no hay ningún emparejamiento"):
        coleccion.quitar("fantasma")


# --------------------------------------------------------------------------- #
# Validación: rechazo ANTES de guardar
# --------------------------------------------------------------------------- #
def test_nombre_repetido_se_rechaza_al_agregar() -> None:
    coleccion = EmparejamientosManuales().agregar(
        EmparejamientoManual(nombre="mi pareja", miembros={"a": "1", "b": "2"})
    )
    with pytest.raises(ErrorDeProyecto, match="ya hay un emparejamiento manual llamado"):
        coleccion.agregar(EmparejamientoManual(nombre="mi pareja", miembros={"c": "1", "d": "2"}))


def test_nombre_repetido_se_rechaza_en_el_constructor() -> None:
    """No hace falta pasar por `agregar()` para que se detecte: el invariante
    se comprueba en cualquier construcción, incluida `desde_dict`."""
    e1 = EmparejamientoManual(nombre="x", miembros={"a": "1", "b": "2"})
    e2 = EmparejamientoManual(nombre="x", miembros={"c": "1", "d": "2"})
    with pytest.raises(ErrorDeProyecto, match="ya hay un emparejamiento manual llamado"):
        EmparejamientosManuales((e1, e2))


def test_mismo_canal_en_dos_emparejamientos_se_rechaza() -> None:
    coleccion = EmparejamientosManuales().agregar(
        EmparejamientoManual(nombre="uno", miembros={"seg_a": "canal_1", "seg_b": "canal_2"})
    )
    with pytest.raises(ErrorDeProyecto, match="ya está en el emparejamiento manual 'uno'"):
        coleccion.agregar(
            EmparejamientoManual(nombre="dos", miembros={"seg_a": "canal_1", "seg_c": "canal_9"})
        )


def test_el_mismo_emparejamiento_no_se_rechaza_a_si_mismo() -> None:
    """Dos canales distintos del mismo emparejamiento no son un conflicto."""
    coleccion = EmparejamientosManuales().agregar(
        EmparejamientoManual(nombre="uno", miembros={"seg_a": "canal_1", "seg_b": "canal_2"})
    )
    assert coleccion.existe("uno")


# --------------------------------------------------------------------------- #
# Serialización: dict y JSON, ida y vuelta, versión de esquema
# --------------------------------------------------------------------------- #
def test_a_dict_incluye_la_version_de_esquema_actual() -> None:
    coleccion = EmparejamientosManuales().agregar(
        EmparejamientoManual(nombre="uno", miembros={"a": "1", "b": "2"})
    )
    bruto = coleccion.a_dict()
    assert bruto["version_esquema"] == VERSION_ESQUEMA_EMPAREJAMIENTOS
    assert bruto["emparejamientos"] == [{"nombre": "uno", "miembros": {"a": "1", "b": "2"}}]


def test_round_trip_por_dict_reproduce_la_coleccion() -> None:
    original = (
        EmparejamientosManuales()
        .agregar(EmparejamientoManual(nombre="uno", miembros={"a": "1", "b": "2"}))
        .agregar(EmparejamientoManual(nombre="dos", miembros={"a": "3", "c": "9"}))
    )
    reconstruida = EmparejamientosManuales.desde_dict(original.a_dict())
    assert reconstruida.a_dict() == original.a_dict()
    assert set(reconstruida.nombres) == {"uno", "dos"}


def test_round_trip_por_json_reproduce_la_coleccion() -> None:
    original = EmparejamientosManuales().agregar(
        EmparejamientoManual(nombre="mi pareja", miembros={"haltech": "14", "generico": "coolant"})
    )
    reconstruida = EmparejamientosManuales.desde_json(original.a_json())
    assert reconstruida.a_dict() == original.a_dict()


def test_a_dict_es_json_compatible_con_solo_str_y_dict_y_list() -> None:
    coleccion = EmparejamientosManuales().agregar(
        EmparejamientoManual(nombre="uno", miembros={"a": "1", "b": "2"})
    )
    bruto = coleccion.a_dict()
    assert isinstance(bruto["version_esquema"], int)
    assert isinstance(bruto["emparejamientos"], list)
    for item in bruto["emparejamientos"]:
        assert isinstance(item["nombre"], str)
        assert isinstance(item["miembros"], dict)


def test_desde_dict_con_version_desconocida_da_error_con_nombre_propio() -> None:
    bruto = {
        "version_esquema": VERSION_ESQUEMA_EMPAREJAMIENTOS + 1,
        "emparejamientos": [],
    }
    with pytest.raises(ErrorDeVersionDesconocida, match="versión de esquema"):
        EmparejamientosManuales.desde_dict(bruto)


def test_version_desconocida_es_tambien_un_error_de_proyecto() -> None:
    """`ErrorDeVersionDesconocida` hereda de `ErrorDeProyecto`: quien solo
    quiera atrapar errores de este módulo no necesita conocer el nombre
    específico."""
    bruto = {"version_esquema": 999, "emparejamientos": []}
    with pytest.raises(ErrorDeProyecto):
        EmparejamientosManuales.desde_dict(bruto)


def test_desde_dict_sin_version_esquema_da_error_util() -> None:
    with pytest.raises(ErrorDeProyecto, match="incompleto"):
        EmparejamientosManuales.desde_dict({"emparejamientos": []})


def test_desde_dict_sin_emparejamientos_da_error_util() -> None:
    with pytest.raises(ErrorDeProyecto, match="incompleto"):
        EmparejamientosManuales.desde_dict({"version_esquema": VERSION_ESQUEMA_EMPAREJAMIENTOS})


def test_desde_dict_con_emparejamientos_no_lista_da_error_util() -> None:
    bruto = {"version_esquema": VERSION_ESQUEMA_EMPAREJAMIENTOS, "emparejamientos": "no es lista"}
    with pytest.raises(ErrorDeProyecto, match="debe ser una lista"):
        EmparejamientosManuales.desde_dict(bruto)


def test_desde_dict_con_emparejamiento_sin_miembros_da_error_util() -> None:
    bruto = {
        "version_esquema": VERSION_ESQUEMA_EMPAREJAMIENTOS,
        "emparejamientos": [{"nombre": "uno"}],
    }
    with pytest.raises(ErrorDeProyecto, match="no tiene la clave"):
        EmparejamientosManuales.desde_dict(bruto)


def test_desde_dict_con_conflicto_de_canales_sigue_rechazando() -> None:
    """La validación se aplica también al reconstruir desde disco: un
    `.dlvproj` editado a mano con un canal duplicado no se acepta en
    silencio."""
    bruto = {
        "version_esquema": VERSION_ESQUEMA_EMPAREJAMIENTOS,
        "emparejamientos": [
            {"nombre": "uno", "miembros": {"a": "1", "b": "2"}},
            {"nombre": "dos", "miembros": {"a": "1", "c": "9"}},
        ],
    }
    with pytest.raises(ErrorDeProyecto, match="ya está en el emparejamiento manual"):
        EmparejamientosManuales.desde_dict(bruto)


def test_desde_json_con_json_invalido_da_error_util() -> None:
    with pytest.raises(ErrorDeProyecto, match="JSON inválido"):
        EmparejamientosManuales.desde_json("{ no es json")


def test_desde_json_con_raiz_que_no_es_objeto_da_error_util() -> None:
    with pytest.raises(ErrorDeProyecto, match="objeto"):
        EmparejamientosManuales.desde_json("[1, 2, 3]")


# --------------------------------------------------------------------------- #
# Integración: `a_secuencia()` encaja sin conversión en `identidad.emparejar`
# --------------------------------------------------------------------------- #
def test_a_secuencia_es_el_mismo_campo_sin_conversion() -> None:
    coleccion = EmparejamientosManuales().agregar(
        EmparejamientoManual(nombre="uno", miembros={"a": "1", "b": "2"})
    )
    assert coleccion.a_secuencia() == coleccion.emparejamientos


def test_a_secuencia_produce_el_emparejamiento_manual_esperado() -> None:
    """El caso completo: dos canales sin rol, sin ID nativo y con nombres
    distintos -- lo único que puede unirlos es el emparejamiento manual del
    proyecto, y `identidad.emparejar` tiene que respetarlo tal cual."""
    canales = [
        canal("log_a", "canal_9", nombre="Presion Rara"),
        canal("log_b", "canal_3", nombre="Otra Cosa"),
    ]
    manuales = EmparejamientosManuales().agregar(
        EmparejamientoManual(nombre="mi pareja", miembros={"log_a": "canal_9", "log_b": "canal_3"})
    )

    resultado = emparejar(canales, segmentos=["log_a", "log_b"], manuales=manuales.a_secuencia())

    grupo = resultado.grupo_de("log_a", "canal_9")
    assert grupo.capa is Capa.MANUAL
    assert grupo.id == "manual:mi pareja"
    assert grupo.canal_en("log_b") is not None
    assert grupo.canal_en("log_b").id_canal == "canal_3"  # type: ignore[union-attr]
