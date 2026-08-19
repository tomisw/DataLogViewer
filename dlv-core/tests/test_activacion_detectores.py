"""Los detectores que se callan cuando su rol es una conjetura (F3-08).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.15 mitigación 4, y
`[desactivacion_automatica]` de `data/umbrales.toml`.

QUÉ SE PRUEBA Y QUÉ NO
======================
Lo que importa aquí no es que la función devuelva un booleano. Es que:

1. El criterio salga del DATO y no del código. La lista de severidades afectadas
   vive en `data/umbrales.toml`; si esta suite pasara con la lista cambiada, el
   dato sería decorativo. Hay una prueba que la cambia y comprueba que el
   resultado cambia con ella.
2. Una errata en esa lista FALLE. Es el fallo más caro posible en este módulo:
   `"critico"` en vez de `"critica"` no coincide con nada, no desactiva ningún
   detector, y no da ningún error. La mitigación de R10 quedaría apagada en
   silencio y se descubriría con una alerta falsa meses más tarde.
3. Los tres estados se distingan. «Desactivado por precaución» y «no ejecutable
   porque falta el canal» piden acciones distintas del usuario —un clic y un
   log mejor—, así que colapsarlos en un «desactivado» es un defecto, no una
   simplificación.
4. El motivo NOMBRE el rol. Un motivo que no dice qué confirmar deja al usuario
   sin salida, y esa es la mitad del valor de la mitigación.

Y una prueba sobre el catálogo real, que es la que puede sorprender: con la
política declarada hoy los detectores afectados son CUATRO, no los tres que
docs/07 enumera entre paréntesis. Ver
`test_la_politica_real_afecta_tambien_a_d13`.

Solo biblioteca estándar.
"""

from __future__ import annotations

import io
import tomllib
from pathlib import Path

import pytest

from dlv_core.activacion_detectores import (
    DetectorDeclarado,
    ErrorDeActivacion,
    PoliticaDesactivacion,
    cargar_catalogo_detectores,
    cargar_politica,
    evaluar_activacion,
)
from dlv_core.plausibilidad import SEVERIDADES

RAIZ = Path(__file__).resolve().parents[2]
UMBRALES = RAIZ / "data" / "umbrales.toml"


@pytest.fixture(scope="module")
def catalogo_real() -> dict[str, DetectorDeclarado]:
    with UMBRALES.open("rb") as fh:
        return cargar_catalogo_detectores(fh)


@pytest.fixture(scope="module")
def politica_real() -> PoliticaDesactivacion:
    with UMBRALES.open("rb") as fh:
        return cargar_politica(fh)


def _toml(texto: str) -> io.BytesIO:
    return io.BytesIO(texto.encode("utf-8"))


_CATALOGO_MINIMO = """
[detectores.DC]
etiqueta = "Crítico de prueba"
roles = ["oil_pressure", "engine_speed"]
severidad = "critica"

[detectores.DM]
etiqueta = "Medio de prueba"
roles = ["oil_pressure"]
severidad = "media"

[desactivacion_automatica]
severidades_afectadas = ["critica"]
motivo = "rol asignado por parecido de nombre y sin confirmar"
"""


@pytest.fixture
def minimo() -> tuple[dict[str, DetectorDeclarado], PoliticaDesactivacion]:
    return (
        cargar_catalogo_detectores(_toml(_CATALOGO_MINIMO)),
        cargar_politica(_toml(_CATALOGO_MINIMO)),
    )


# --------------------------------------------------------------------------- #
#  1. El criterio sale del dato
# --------------------------------------------------------------------------- #


def test_un_critico_con_rol_sin_confirmar_se_desactiva(
    minimo: tuple[dict[str, DetectorDeclarado], PoliticaDesactivacion],
) -> None:
    catalogo, politica = minimo
    estados = evaluar_activacion(
        catalogo, politica, roles_sin_confirmar=frozenset({"oil_pressure"})
    )
    assert estados["DC"].activo is False
    assert estados["DC"].roles_sin_confirmar == ("oil_pressure",)


def test_un_detector_no_critico_con_el_mismo_rol_sigue_activo(
    minimo: tuple[dict[str, DetectorDeclarado], PoliticaDesactivacion],
) -> None:
    """La mitad de §7.15 que es fácil pasar por alto.

    Desactivar todo lo que toque un rol difuso sería «más seguro» y dejaría el
    panel vacío en cualquier CSV importado por parecido, que es otra forma de no
    avisar. El coste de un falso positivo de severidad media es una fila más; el
    de uno crítico es enseñar al usuario a ignorar las alertas rojas.
    """
    catalogo, politica = minimo
    estados = evaluar_activacion(
        catalogo, politica, roles_sin_confirmar=frozenset({"oil_pressure"})
    )
    assert estados["DM"].activo is True
    assert estados["DM"].motivo is None
    # El rol sí se registra: el panel puede querer marcarlo sin desactivar nada.
    assert estados["DM"].roles_sin_confirmar == ("oil_pressure",)


def test_el_criterio_lo_manda_el_fichero_de_datos_y_no_el_codigo() -> None:
    """Si esta prueba pasara con la política cambiada, el dato sería decorativo.

    Con `severidades_afectadas = ["media"]` el que se desactiva es el de severidad
    media y NO el crítico. No es una configuración que nadie querría; es la
    demostración de que el código no lleva «critica» escrito dentro.
    """
    texto = _CATALOGO_MINIMO.replace(
        'severidades_afectadas = ["critica"]', 'severidades_afectadas = ["media"]'
    )
    catalogo = cargar_catalogo_detectores(_toml(texto))
    politica = cargar_politica(_toml(texto))
    estados = evaluar_activacion(
        catalogo, politica, roles_sin_confirmar=frozenset({"oil_pressure"})
    )
    assert estados["DM"].activo is False
    assert estados["DC"].activo is True


def test_un_rol_difuso_que_el_detector_no_usa_no_lo_desactiva(
    minimo: tuple[dict[str, DetectorDeclarado], PoliticaDesactivacion],
) -> None:
    catalogo, politica = minimo
    estados = evaluar_activacion(catalogo, politica, roles_sin_confirmar=frozenset({"knock_count"}))
    assert estados["DC"].activo is True
    assert estados["DM"].activo is True


# --------------------------------------------------------------------------- #
#  2. La errata que apagaría la mitigación en silencio
# --------------------------------------------------------------------------- #


def test_una_severidad_mal_escrita_es_un_error_y_no_un_aviso() -> None:
    """El fallo más caro de este módulo, y el único que no tiene síntoma.

    `"critico"` no coincide con ninguna severidad del catálogo, así que no
    desactivaría ningún detector y no daría ningún error: la mitigación de R10
    quedaría apagada y se descubriría con una alerta falsa meses después. Tiene
    que fallar al cargar.
    """
    texto = _CATALOGO_MINIMO.replace('["critica"]', '["critico"]')
    with pytest.raises(ErrorDeActivacion, match="no existen"):
        cargar_politica(_toml(texto))


def test_una_lista_vacia_de_severidades_tambien_falla() -> None:
    """Desactivar la mitigación tiene que ser una decisión escrita, no un hueco."""
    texto = _CATALOGO_MINIMO.replace('["critica"]', "[]")
    with pytest.raises(ErrorDeActivacion, match="vacía"):
        cargar_politica(_toml(texto))


def test_sin_seccion_de_politica_no_se_supone_ninguna() -> None:
    texto = _CATALOGO_MINIMO.split("[desactivacion_automatica]")[0]
    with pytest.raises(ErrorDeActivacion, match="desactivacion_automatica"):
        cargar_politica(_toml(texto))


def test_un_detector_sin_severidad_declarada_falla_en_vez_de_suponerse_informativo() -> None:
    """Suponer «informativa» sería suponer el lado que no desactiva nada."""
    texto = """
[detectores.DX]
etiqueta = "Sin severidad"
roles = ["oil_pressure"]
"""
    with pytest.raises(ErrorDeActivacion, match="no declara `severidad`"):
        cargar_catalogo_detectores(_toml(texto))


def test_declarar_las_dos_formas_de_severidad_a_la_vez_falla() -> None:
    texto = """
[detectores.DX]
etiqueta = "Ambiguo"
roles = ["oil_pressure"]
severidad = "media"
severidad_por_nivel = { 1 = "critica" }
"""
    with pytest.raises(ErrorDeActivacion, match="a la vez"):
        cargar_catalogo_detectores(_toml(texto))


def test_un_detector_sin_etiqueta_falla() -> None:
    """El panel muestra un nombre, y «D10» no le dice nada a quien lee el log."""
    texto = """
[detectores.DX]
roles = ["oil_pressure"]
severidad = "critica"
"""
    with pytest.raises(ErrorDeActivacion, match="etiqueta"):
        cargar_catalogo_detectores(_toml(texto))


# --------------------------------------------------------------------------- #
#  3. Tres estados, no dos
# --------------------------------------------------------------------------- #


def test_un_rol_ausente_no_es_lo_mismo_que_un_rol_sin_confirmar(
    minimo: tuple[dict[str, DetectorDeclarado], PoliticaDesactivacion],
) -> None:
    """Las dos piden acciones distintas: un clic, o un log con ese canal."""
    catalogo, politica = minimo
    estados = evaluar_activacion(
        catalogo,
        politica,
        roles_sin_confirmar=frozenset(),
        roles_presentes=frozenset({"engine_speed"}),
    )
    dc = estados["DC"]
    assert dc.activo is False
    assert dc.roles_ausentes == ("oil_pressure",)
    assert dc.roles_sin_confirmar == ()
    assert dc.motivo is not None
    assert "no es una precaución" in dc.motivo
    assert "confírmalo" not in dc.motivo, (
        "pide confirmar un rol que el log no trae: no hay nada que confirmar"
    )


def test_no_saber_que_roles_hay_no_es_lo_mismo_que_saber_que_faltan(
    minimo: tuple[dict[str, DetectorDeclarado], PoliticaDesactivacion],
) -> None:
    """`roles_presentes=None` significa «no se sabe» y no juzga ninguna ausencia.

    Es la misma distinción que el descriptor de formato hace entre `unknown` y un
    valor: no tener el dato no es tener el dato de que falta.
    """
    catalogo, politica = minimo
    estados = evaluar_activacion(catalogo, politica, roles_sin_confirmar=frozenset())
    assert all(e.activo for e in estados.values())
    assert all(e.roles_ausentes == () for e in estados.values())

    # Y un conjunto VACÍO sí afirma que no hay ningún rol.
    estados_vacio = evaluar_activacion(
        catalogo, politica, roles_sin_confirmar=frozenset(), roles_presentes=frozenset()
    )
    assert estados_vacio["DC"].roles_ausentes == ("oil_pressure", "engine_speed")


def test_un_rol_ausente_no_se_cuenta_ademas_como_sin_confirmar(
    minimo: tuple[dict[str, DetectorDeclarado], PoliticaDesactivacion],
) -> None:
    """Un rol que no está no puede estar «sin confirmar»: no está."""
    catalogo, politica = minimo
    estados = evaluar_activacion(
        catalogo,
        politica,
        roles_sin_confirmar=frozenset({"oil_pressure"}),
        roles_presentes=frozenset({"engine_speed"}),
    )
    assert estados["DC"].roles_ausentes == ("oil_pressure",)
    assert estados["DC"].roles_sin_confirmar == ()


def test_las_dos_razones_a_la_vez_se_nombran_las_dos(
    minimo: tuple[dict[str, DetectorDeclarado], PoliticaDesactivacion],
) -> None:
    """Arreglar solo una no lo enciende, así que decir solo una engaña."""
    catalogo, politica = minimo
    estados = evaluar_activacion(
        catalogo,
        politica,
        roles_sin_confirmar=frozenset({"engine_speed"}),
        roles_presentes=frozenset({"engine_speed"}),
    )
    dc = estados["DC"]
    assert dc.activo is False
    assert dc.roles_ausentes == ("oil_pressure",)
    assert dc.roles_sin_confirmar == ("engine_speed",)
    assert dc.motivo is not None
    assert "oil_pressure" in dc.motivo and "engine_speed" in dc.motivo


def test_el_motivo_nombra_el_rol_que_hay_que_confirmar(
    minimo: tuple[dict[str, DetectorDeclarado], PoliticaDesactivacion],
) -> None:
    """La mitad del valor de la mitigación: un aviso sobre el que se puede actuar."""
    catalogo, politica = minimo
    estados = evaluar_activacion(
        catalogo, politica, roles_sin_confirmar=frozenset({"oil_pressure"})
    )
    motivo = estados["DC"].motivo
    assert motivo is not None
    assert "oil_pressure" in motivo
    assert politica.motivo in motivo
    assert "7.15" in motivo


# --------------------------------------------------------------------------- #
#  4. El catálogo real
# --------------------------------------------------------------------------- #


def test_la_politica_real_afecta_tambien_a_d13(
    catalogo_real: dict[str, DetectorDeclarado],
    politica_real: PoliticaDesactivacion,
) -> None:
    """El resultado que hay que revisar en la puerta G1.

    docs/07 §7.15 enumera entre paréntesis «(D4, D10, D12)», que son los tres
    detectores con `severidad = "critica"` fija. Con la política declarada en
    `data/umbrales.toml` el criterio afecta a CUATRO: D13 no tiene `severidad`
    sino `severidad_por_nivel`, y su nivel 3 es `"critica"`.

    Está incluido a propósito, no por un descuido del criterio. Si el rol
    `protection_level` se emparejó por parecido, una crítica de nivel 3 afirma que
    la ECU está protegiendo el motor sobre un canal que puede medir otra cosa: el
    aviso falso de mayor consecuencia del catálogo. La enumeración de docs/07 es
    incompleta, no incorrecta.

    Si el propietario decide que D13 debe seguir avisando, esto se cambia en el
    dato —no aquí— dándole una severidad fija o partiendo la política.
    """
    afectados = sorted(
        (
            k
            for k, v in catalogo_real.items()
            if v.esta_afectado(politica_real.severidades_afectadas)
        ),
        key=lambda s: int(s[1:]),
    )
    assert afectados == ["D4", "D10", "D12", "D13"], (
        f"los detectores afectados son {afectados}; si esta lista cambia, hay que "
        "revisar si docs/07 §7.15 sigue diciendo lo mismo que el dato"
    )


def test_los_tres_de_docs_07_estan_entre_los_afectados(
    catalogo_real: dict[str, DetectorDeclarado],
    politica_real: PoliticaDesactivacion,
) -> None:
    """La parte de §7.15 que no admite interpretación: D4, D10 y D12 se desactivan."""
    for id_detector in ("D4", "D10", "D12"):
        detector = catalogo_real[id_detector]
        assert detector.esta_afectado(politica_real.severidades_afectadas), id_detector
        assert detector.roles, f"{id_detector} sin roles declarados: no se podría desactivar"


def test_los_informativos_del_muestreo_no_declaran_roles_y_no_pasa_nada(
    catalogo_real: dict[str, DetectorDeclarado],
    politica_real: PoliticaDesactivacion,
) -> None:
    """D16, D17 y D18 hablan del muestreo, no de un rol: nada que desactivar."""
    estados = evaluar_activacion(
        catalogo_real,
        politica_real,
        roles_sin_confirmar=frozenset({"oil_pressure", "protection_level"}),
        roles_presentes=frozenset(),
    )
    for id_detector in ("D16", "D17", "D18"):
        assert catalogo_real[id_detector].roles == ()
        assert estados[id_detector].activo is True
        assert estados[id_detector].roles_ausentes == ()


def test_el_catalogo_real_se_carga_entero_y_con_severidades_conocidas(
    catalogo_real: dict[str, DetectorDeclarado],
) -> None:
    with UMBRALES.open("rb") as fh:
        crudo = tomllib.load(fh)["detectores"]
    assert set(catalogo_real) == set(crudo)
    assert len(catalogo_real) == 18
    for detector in catalogo_real.values():
        assert detector.severidades_posibles
        assert all(s in SEVERIDADES for s in detector.severidades_posibles)
        assert detector.severidad_maxima in SEVERIDADES


def test_la_severidad_maxima_es_la_mas_grave_no_la_primera() -> None:
    """`severidad_por_nivel` no viene ordenado por gravedad necesariamente."""
    detector = DetectorDeclarado(
        id="DX", etiqueta="X", roles=(), severidades_posibles=("baja", "critica", "media")
    )
    assert detector.severidad_maxima == "critica"
