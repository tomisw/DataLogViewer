"""Pruebas de `dlv_app.actualizador` (F5-05).

Ninguna prueba de este fichero abre una conexion de red real -- ni siquiera
`consulta_por_red`, la implementacion real con `urllib`, se llama desde aqui
(regla explicita de la tarea F5-05: nada de peticiones reales, ni en las
pruebas ni fuera de ellas). Todo lo que necesita una "respuesta del
servidor" usa una funcion `consulta` falsa, inyectada -- mismo patron que
`test_webview2.py` inyecta un `winreg` falso en vez de tocar el registro de
verdad.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from dlv_app.actualizador import (
    URL_COMPROBACION_PENDIENTE,
    ConsultaVersion,
    EstadoActualizacion,
    _es_mas_reciente,
    _url_con_version,
    _version_como_tupla,
    comprobar_actualizacion,
)


def _consulta_prohibida(url: str) -> bytes:
    """Funcion de consulta que estalla si se llega a invocar.

    Se usa para comprobar `desactivado=True`: la afirmacion no es solo "el
    resultado es DESACTIVADO", es "no se ha intentado ninguna consulta" --
    igual que `_WinregProhibido` en `test_webview2.py` comprueba que la rama
    "no es Windows" no toca el registro.
    """
    raise AssertionError(f"no deberia consultarse nada estando desactivado (url={url!r})")


def _consulta_fija(cuerpo: bytes | Exception) -> ConsultaVersion:
    """Construye una `ConsultaVersion` que devuelve `cuerpo` siempre, o que
    lanza `cuerpo` si es una excepcion -- para simular una respuesta buena,
    una corrupta, o un fallo de red segun lo que se le pase.
    """

    def _consulta(url: str) -> bytes:
        if isinstance(cuerpo, Exception):
            raise cuerpo
        return cuerpo

    return _consulta


def _respuesta_json(version: str, url: str = "https://example.invalid/descarga") -> bytes:
    return json.dumps({"version": version, "url": url}).encode("utf-8")


# ---------------------------------------------------------------------------
# Regla 2: desactivado se respeta sin excepciones, y sin tocar la red
# ---------------------------------------------------------------------------


def test_desactivado_no_consulta_nada() -> None:
    resultado = comprobar_actualizacion(desactivado=True, consulta=_consulta_prohibida)

    assert resultado.estado is EstadoActualizacion.DESACTIVADO
    assert resultado.version_disponible is None
    assert resultado.url_descarga is None


def test_desactivado_gana_aunque_la_consulta_tambien_fuera_a_fallar() -> None:
    """`desactivado=True` no es "intentalo y si falla, no importa": ni
    siquiera se llega a construir la URL de consulta. Se comprueba con
    `_consulta_prohibida`, que haria fallar la prueba si se invocara.
    """
    resultado = comprobar_actualizacion(
        desactivado=True, consulta=_consulta_prohibida, url="https://cualquier-cosa.invalid"
    )

    assert resultado.estado is EstadoActualizacion.DESACTIVADO


# ---------------------------------------------------------------------------
# Regla 3: falla en silencio hacia el lado seguro
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "excepcion",
    [
        urllib.error.URLError("sin red (simulado)"),
        TimeoutError("agotado (simulado)"),
        ConnectionError("servidor caido (simulado)"),
        OSError("fallo generico de socket (simulado)"),
    ],
)
def test_fallo_de_red_es_desconocido_no_una_excepcion(excepcion: Exception) -> None:
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(excepcion),
        version_instalada="1.0.0",
    )

    assert resultado.estado is EstadoActualizacion.DESCONOCIDO


def test_json_invalido_es_desconocido() -> None:
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(b"esto no es json{{{"),
        version_instalada="1.0.0",
    )

    assert resultado.estado is EstadoActualizacion.DESCONOCIDO


def test_json_sin_los_campos_esperados_es_desconocido() -> None:
    cuerpo = json.dumps({"algo_distinto": "1.2.3"}).encode("utf-8")

    resultado = comprobar_actualizacion(
        desactivado=False, consulta=_consulta_fija(cuerpo), version_instalada="1.0.0"
    )

    assert resultado.estado is EstadoActualizacion.DESCONOCIDO


def test_version_remota_no_numerica_es_desconocido() -> None:
    """Una respuesta "bien formada" en JSON pero con una version que no se
    puede comparar (p. ej. "v2-beta") tampoco debe bloquear ni adivinar.
    """
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(_respuesta_json("v2-beta")),
        version_instalada="1.0.0",
    )

    assert resultado.estado is EstadoActualizacion.DESCONOCIDO


def test_version_instalada_no_numerica_es_desconocido() -> None:
    """Simetrico al de arriba: si la version LOCAL no se puede interpretar
    (p. ej. un `__version__` de desarrollo roto), tampoco se puede concluir
    nada -- no se asume "hay actualizacion" solo porque la remota si parseo.
    """
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(_respuesta_json("2.0.0")),
        version_instalada="no-es-una-version",
    )

    assert resultado.estado is EstadoActualizacion.DESCONOCIDO


# ---------------------------------------------------------------------------
# Comparacion de versiones y resultado normal
# ---------------------------------------------------------------------------


def test_version_remota_mayor_es_disponible() -> None:
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(_respuesta_json("2.0.0", "https://example.invalid/v2")),
        version_instalada="1.0.0",
    )

    assert resultado.estado is EstadoActualizacion.DISPONIBLE
    assert resultado.version_disponible == "2.0.0"
    assert resultado.url_descarga == "https://example.invalid/v2"


def test_version_remota_igual_es_al_dia() -> None:
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(_respuesta_json("1.0.0")),
        version_instalada="1.0.0",
    )

    assert resultado.estado is EstadoActualizacion.AL_DIA


def test_version_remota_menor_es_al_dia() -> None:
    """P. ej. un despliegue que se adelanto en local a lo publicado: no se
    debe ofrecer "actualizar" a una version mas vieja.
    """
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(_respuesta_json("0.9.0")),
        version_instalada="1.0.0",
    )

    assert resultado.estado is EstadoActualizacion.AL_DIA


def test_comparacion_es_numerica_no_de_texto() -> None:
    """`"9" < "10"` como texto pero `(9,) < (10,)` como version -- si la
    comparacion fuera por cadenas, "1.9.0" > "1.10.0" saldria mal.
    """
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(_respuesta_json("1.10.0")),
        version_instalada="1.9.0",
    )

    assert resultado.estado is EstadoActualizacion.DISPONIBLE
    assert resultado.version_disponible == "1.10.0"


# ---------------------------------------------------------------------------
# "No vuelve a insistir": version_descartada
# ---------------------------------------------------------------------------


def test_version_descartada_no_vuelve_a_avisar_de_la_misma_version() -> None:
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(_respuesta_json("2.0.0")),
        version_instalada="1.0.0",
        version_descartada="2.0.0",
    )

    assert resultado.estado is EstadoActualizacion.DESCARTADA
    assert resultado.version_disponible == "2.0.0"
    assert resultado.url_descarga is None


def test_version_descartada_no_silencia_una_version_mas_nueva_todavia() -> None:
    """Descartar 2.0.0 no debe silenciar 2.1.0: "no vuelve a insistir" es
    sobre ESA version concreta, no un apagado permanente.
    """
    resultado = comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_fija(_respuesta_json("2.1.0")),
        version_instalada="1.0.0",
        version_descartada="2.0.0",
    )

    assert resultado.estado is EstadoActualizacion.DISPONIBLE
    assert resultado.version_disponible == "2.1.0"


# ---------------------------------------------------------------------------
# Decision 2: que se envia -- solo la version instalada, nada mas
# ---------------------------------------------------------------------------


def test_la_url_de_consulta_solo_anade_la_version() -> None:
    urls_vistas: list[str] = []

    def _consulta_que_registra(url: str) -> bytes:
        urls_vistas.append(url)
        return _respuesta_json("1.0.0")

    comprobar_actualizacion(
        desactivado=False,
        consulta=_consulta_que_registra,
        version_instalada="1.2.3",
        url="https://example.invalid/comprobar",
    )

    assert urls_vistas == ["https://example.invalid/comprobar?version=1.2.3"]


def test_url_con_version_preserva_parametros_existentes_y_no_anade_nada_mas() -> None:
    url = _url_con_version("https://example.invalid/x?ya=aqui", "1.2.3")

    assert url == "https://example.invalid/x?ya=aqui&version=1.2.3"


def test_url_comprobacion_pendiente_no_es_una_url_real() -> None:
    """Marcador deliberado (ver el docstring del modulo): no tiene esquema
    http(s), para que un uso accidental sin configurar no parezca un
    servidor real.
    """
    assert not URL_COMPROBACION_PENDIENTE.startswith(("http://", "https://"))


# ---------------------------------------------------------------------------
# Funciones internas de comparacion de versiones, probadas por separado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cadena", "esperado"),
    [
        ("1.2.3", (1, 2, 3)),
        ("0.1.0", (0, 1, 0)),
        ("10", (10,)),
        ("", None),
        ("1.2.beta", None),
        ("v1.2.3", None),
        ("1..3", None),
    ],
)
def test_version_como_tupla(cadena: str, esperado: tuple[int, ...] | None) -> None:
    assert _version_como_tupla(cadena) == esperado


def test_es_mas_reciente_none_si_alguna_version_no_se_interpreta() -> None:
    assert _es_mas_reciente("2.0.0", "no-parseable") is None
    assert _es_mas_reciente("no-parseable", "1.0.0") is None


def test_es_mas_reciente_compara_como_version() -> None:
    assert _es_mas_reciente("2.0.0", "1.9.9") is True
    assert _es_mas_reciente("1.0.0", "1.0.0") is False
    assert _es_mas_reciente("1.0.0", "1.0.1") is False
