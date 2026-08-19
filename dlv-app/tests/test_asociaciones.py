"""Pruebas de `dlv_app.asociaciones` (F5-17).

Dos grupos, con la misma division que documenta `dlv_app.asociaciones`:

1. **Logica de decision** (la mayoria): usan `_AlmacenFalso`, una
   implementacion en memoria de `AlmacenDeRegistro`. Corren en cualquier
   plataforma, no importan `winreg` y no tocan el registro de Windows para
   nada -- comprueban que registrar respalda antes de sobreescribir, que
   desregistrar restaura o borra segun corresponda, que el modo portable
   bloquea las dos direcciones, etc.
2. **Contra el registro real** (`skipif` fuera de Windows, al final del
   fichero): ejercitan `_AlmacenWinreg` de verdad contra `HKEY_CURRENT_USER`,
   pero SOLO con una extension de usar y tirar generada por prueba
   (`.dlvtest-<hex aleatorio>`) -- nunca `.csv` ni `.dlv`, y nunca `HKLM`.
   Cada una limpia sus claves en un `finally`, incluso si una asercion falla
   a mitad, con un borrado recursivo escrito de forma independiente al
   modulo bajo prueba (`_borrar_arbol_de_verdad`): si `_AlmacenWinreg.
   borrar_arbol` estuviera roto, la limpieza no deberia depender de el.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from dlv_app.asociaciones import (
    _MARCADOR_SIN_ASOCIACION_PREVIA,
    _RUTA_CONTENEDOR_APLICACION,
    _RUTA_CONTENEDOR_RESPALDOS,
    ModoPortableActivo,
    NoHayAsociacionQueDesregistrar,
    PlataformaNoSoportada,
    _comando_de_apertura,
    _ruta_comando,
    _ruta_extension,
    _ruta_progid,
    _ruta_respaldo,
    desregistrar_extension,
    esta_asociada_a_datalogviewer,
    progid_de,
    registrar_extension,
)

ES_WINDOWS = sys.platform == "win32"


# --------------------------------------------------------------------------- #
# Funciones puras: sin almacen de ningun tipo
# --------------------------------------------------------------------------- #


def test_progid_de_antepone_el_prefijo_a_la_extension() -> None:
    assert progid_de(".dlv") == "DataLogViewer.dlv"
    assert progid_de(".csv") == "DataLogViewer.csv"


def test_progid_de_exige_extension_con_punto() -> None:
    with pytest.raises(ValueError):
        progid_de("dlv")


def test_progid_de_rechaza_extension_vacia() -> None:
    with pytest.raises(ValueError):
        progid_de(".")


def test_comando_de_apertura_cita_el_ejecutable_y_el_argumento() -> None:
    comando = _comando_de_apertura(Path(r"C:\Archivos de programa\DataLogViewer\dlv-app.exe"))

    assert comando == '"C:\\Archivos de programa\\DataLogViewer\\dlv-app.exe" "%1"'


# --------------------------------------------------------------------------- #
# Almacen en memoria: la costura inyectable, sin tocar winreg
# --------------------------------------------------------------------------- #


class _AlmacenFalso:
    """Implementacion de `AlmacenDeRegistro` en un diccionario de Python.

    No simula ningun comportamiento raro de `winreg` a proposito: solo lo
    minimo del contrato del protocolo (leer/escribir/borrar el valor por
    omision de una ruta, `borrar_arbol` elimina la ruta y sus descendientes).
    Es exactamente lo que necesitan las pruebas de logica de decision.
    """

    def __init__(self) -> None:
        self.valores: dict[str, str] = {}
        self.llamadas_borrar_si_vacia: list[str] = []

    def leer_valor_por_omision(self, ruta: str) -> str | None:
        return self.valores.get(ruta)

    def escribir_valor_por_omision(self, ruta: str, valor: str) -> None:
        self.valores[ruta] = valor

    def borrar_arbol(self, ruta: str) -> None:
        prefijo = ruta + "\\"
        for clave in [c for c in self.valores if c == ruta or c.startswith(prefijo)]:
            del self.valores[clave]

    def borrar_si_vacia(self, ruta: str) -> None:
        # Este almacen falso nunca da valor propio a un contenedor (solo a
        # las hojas que `registrar_extension`/`desregistrar_extension`
        # escriben de verdad), asi que no hay nada que este metodo pueda
        # quitar de `self.valores` sin arriesgarse a borrar una hoja de otra
        # extension -- `borrar_arbol` ya limpia las hojas propias. Lo que SI
        # registra es que se le llamo, y con que ruta y en que orden -- ver
        # `test_desregistrar_extension_limpia_los_contenedores_propios`, que
        # es la parte de la logica de decision que si se puede comprobar sin
        # un almacen que modele contenedores vacios de verdad (eso lo
        # comprueban las pruebas contra el registro real, mas abajo).
        self.llamadas_borrar_si_vacia.append(ruta)


class _AlmacenProhibido:
    """Un `AlmacenDeRegistro` que estalla en cuanto se le llama a algo.

    Mismo patron que `_WinregProhibido` de `test_webview2.py`: para las
    pruebas de modo portable, la afirmacion no es solo "lanza la excepcion
    correcta", es "no ha tocado el almacen para nada" -- y la unica forma
    ruidosa de comprobarlo es poner en su sitio algo que falle si se usa.
    """

    def __getattr__(self, nombre: str) -> Any:
        raise AssertionError(f"no se debe tocar el almacen en modo portable ({nombre})")


_EXT_PRUEBA = ".dlvtest-logica"
_EJECUTABLE_PRUEBA = Path(r"C:\dist\dlv-app\dlv-app.exe")


def test_registrar_extension_sin_asociacion_previa(monkeypatch: pytest.MonkeyPatch) -> None:
    _permitir_no_portable(monkeypatch)
    almacen = _AlmacenFalso()

    resultado = registrar_extension(_EXT_PRUEBA, _EJECUTABLE_PRUEBA, almacen=almacen)

    progid = progid_de(_EXT_PRUEBA)
    assert resultado.extension == _EXT_PRUEBA
    assert resultado.progid == progid
    assert resultado.ya_estaba_asociada is False
    assert almacen.valores[_ruta_extension(_EXT_PRUEBA)] == progid
    assert almacen.valores[_ruta_comando(progid)] == _comando_de_apertura(_EJECUTABLE_PRUEBA)
    # Sin asociacion previa: el respaldo guarda el marcador, no un ProgID.
    assert almacen.valores[_ruta_respaldo(_EXT_PRUEBA)] == _MARCADOR_SIN_ASOCIACION_PREVIA


def test_registrar_extension_guarda_la_asociacion_previa(monkeypatch: pytest.MonkeyPatch) -> None:
    _permitir_no_portable(monkeypatch)
    almacen = _AlmacenFalso()
    almacen.valores[_ruta_extension(".csv")] = "Excel.CSV"

    registrar_extension(".csv", _EJECUTABLE_PRUEBA, almacen=almacen)

    assert almacen.valores[_ruta_respaldo(".csv")] == "Excel.CSV"
    assert almacen.valores[_ruta_extension(".csv")] == progid_de(".csv")


def test_registrar_extension_es_idempotente_y_no_pisa_el_respaldo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registrar dos veces seguidas no debe sustituir el respaldo original
    por el propio ProgID de DataLogViewer -- ver la seccion correspondiente
    del docstring de `registrar_extension`."""
    _permitir_no_portable(monkeypatch)
    almacen = _AlmacenFalso()
    almacen.valores[_ruta_extension(".csv")] = "Excel.CSV"

    registrar_extension(".csv", _EJECUTABLE_PRUEBA, almacen=almacen)
    resultado_segunda_vez = registrar_extension(
        ".csv", Path(r"D:\otra\ruta\dlv-app.exe"), almacen=almacen
    )

    assert almacen.valores[_ruta_respaldo(".csv")] == "Excel.CSV"
    assert resultado_segunda_vez.ya_estaba_asociada is True
    # La segunda llamada SI actualiza el comando (ejecutable movido).
    assert almacen.valores[_ruta_comando(progid_de(".csv"))] == _comando_de_apertura(
        Path(r"D:\otra\ruta\dlv-app.exe")
    )


def test_desregistrar_extension_restaura_el_valor_previo(monkeypatch: pytest.MonkeyPatch) -> None:
    _permitir_no_portable(monkeypatch)
    almacen = _AlmacenFalso()
    almacen.valores[_ruta_extension(".csv")] = "Excel.CSV"
    registrar_extension(".csv", _EJECUTABLE_PRUEBA, almacen=almacen)

    desregistrar_extension(".csv", almacen=almacen)

    assert almacen.valores[_ruta_extension(".csv")] == "Excel.CSV"
    assert _ruta_progid(progid_de(".csv")) not in almacen.valores
    assert _ruta_comando(progid_de(".csv")) not in almacen.valores
    assert _ruta_respaldo(".csv") not in almacen.valores


def test_desregistrar_extension_limpia_los_contenedores_propios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`desregistrar_extension` no solo borra el respaldo de ESTA extension:
    intenta tambien quitar los contenedores propios que `registrar_extension`
    crea de forma implicita (`Software\\DataLogViewer\\AsociacionesRespaldo` y
    `Software\\DataLogViewer`), primero el hijo y luego el padre, para no
    dejar una clave vacia que no existia antes de la primera asociacion --
    ver el comentario de `_RUTA_CONTENEDOR_RESPALDOS` en el modulo para el
    caso MEDIDO que motivo esto."""
    _permitir_no_portable(monkeypatch)
    almacen = _AlmacenFalso()
    registrar_extension(_EXT_PRUEBA, _EJECUTABLE_PRUEBA, almacen=almacen)

    desregistrar_extension(_EXT_PRUEBA, almacen=almacen)

    assert almacen.llamadas_borrar_si_vacia == [
        _RUTA_CONTENEDOR_RESPALDOS,
        _RUTA_CONTENEDOR_APLICACION,
    ]


def test_desregistrar_extension_sin_asociacion_previa_borra_la_clave_entera(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _permitir_no_portable(monkeypatch)
    almacen = _AlmacenFalso()
    registrar_extension(_EXT_PRUEBA, _EJECUTABLE_PRUEBA, almacen=almacen)

    desregistrar_extension(_EXT_PRUEBA, almacen=almacen)

    # No solo "sin valor": la clave no debe quedar ni vacia, igual que antes
    # de que `registrar_extension` la hubiera creado.
    assert _ruta_extension(_EXT_PRUEBA) not in almacen.valores
    assert _ruta_progid(progid_de(_EXT_PRUEBA)) not in almacen.valores
    assert _ruta_respaldo(_EXT_PRUEBA) not in almacen.valores


def test_desregistrar_extension_sin_respaldo_lanza_y_no_toca_nada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _permitir_no_portable(monkeypatch)
    almacen = _AlmacenFalso()

    with pytest.raises(NoHayAsociacionQueDesregistrar):
        desregistrar_extension(_EXT_PRUEBA, almacen=almacen)

    assert almacen.valores == {}


def test_esta_asociada_a_datalogviewer_refleja_el_estado_actual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _permitir_no_portable(monkeypatch)
    almacen = _AlmacenFalso()
    assert esta_asociada_a_datalogviewer(_EXT_PRUEBA, almacen=almacen) is False

    registrar_extension(_EXT_PRUEBA, _EJECUTABLE_PRUEBA, almacen=almacen)
    assert esta_asociada_a_datalogviewer(_EXT_PRUEBA, almacen=almacen) is True

    desregistrar_extension(_EXT_PRUEBA, almacen=almacen)
    assert esta_asociada_a_datalogviewer(_EXT_PRUEBA, almacen=almacen) is False


# --------------------------------------------------------------------------- #
# Modo portable: se niega en las dos direcciones, sin tocar el almacen
# --------------------------------------------------------------------------- #


def _permitir_no_portable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dlv_app.portable.modo_portable_activo", lambda: False)


def _forzar_portable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dlv_app.portable.modo_portable_activo", lambda: True)


def test_registrar_extension_se_niega_en_modo_portable(monkeypatch: pytest.MonkeyPatch) -> None:
    _forzar_portable(monkeypatch)

    with pytest.raises(ModoPortableActivo):
        registrar_extension(_EXT_PRUEBA, _EJECUTABLE_PRUEBA, almacen=_AlmacenProhibido())


def test_desregistrar_extension_se_niega_en_modo_portable(monkeypatch: pytest.MonkeyPatch) -> None:
    _forzar_portable(monkeypatch)

    with pytest.raises(ModoPortableActivo):
        desregistrar_extension(_EXT_PRUEBA, almacen=_AlmacenProhibido())


# --------------------------------------------------------------------------- #
# Plataforma: sin almacen inyectado y fuera de Windows, se niega sin winreg
# --------------------------------------------------------------------------- #


def test_registrar_extension_sin_almacen_fuera_de_windows_lanza(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _permitir_no_portable(monkeypatch)
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(PlataformaNoSoportada):
        registrar_extension(_EXT_PRUEBA, _EJECUTABLE_PRUEBA)


def test_esta_asociada_a_datalogviewer_sin_almacen_fuera_de_windows_lanza(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(PlataformaNoSoportada):
        esta_asociada_a_datalogviewer(_EXT_PRUEBA)


# --------------------------------------------------------------------------- #
# Contra el registro real de Windows -- solo con extensiones de usar y tirar
# --------------------------------------------------------------------------- #


def _borrar_arbol_de_verdad(ruta: str) -> None:
    """Borrado recursivo bajo HKCU, escrito de forma independiente al modulo
    bajo prueba: la limpieza de estas pruebas no debe depender de que
    `_AlmacenWinreg.borrar_arbol` este bien -- si lo estuviera roto, querer
    detectarlo con la misma funcion que hace la limpieza esconderia el fallo.
    No falla si `ruta` no existe.
    """
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta) as clave:
            subclaves = []
            indice = 0
            while True:
                try:
                    subclaves.append(winreg.EnumKey(clave, indice))
                except OSError:
                    break
                indice += 1
    except FileNotFoundError:
        return
    for subclave in subclaves:
        _borrar_arbol_de_verdad(f"{ruta}\\{subclave}")
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, ruta)


def _leer_valor_por_omision_de_verdad(ruta: str) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta) as clave:
            valor, _tipo = winreg.QueryValueEx(clave, "")
    except FileNotFoundError:
        return None
    assert isinstance(valor, str)
    return valor


def _clave_existe_de_verdad(ruta: str) -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta):
            return True
    except FileNotFoundError:
        return False


def _borrar_si_vacia_de_verdad(ruta: str) -> None:
    """Igual que `_borrar_arbol_de_verdad`, pero solo si `ruta` no tiene
    subclaves -- para limpiar en la propia prueba los contenedores
    (`_RUTA_CONTENEDOR_RESPALDOS`, `_RUTA_CONTENEDOR_APLICACION`) sin
    arriesgarse a borrarlos con contenido de otra prueba o de otra extension
    todavia pendiente, y sin depender de `AlmacenDeRegistro.borrar_si_vacia`
    del propio modulo bajo prueba (mismo motivo que `_borrar_arbol_de_verdad`
    es independiente de `_AlmacenWinreg.borrar_arbol`)."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta) as clave:
            try:
                winreg.EnumKey(clave, 0)
                return  # tiene al menos una subclave: no tocar
            except OSError:
                pass  # sin subclaves: se puede borrar
    except FileNotFoundError:
        return
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, ruta)


@pytest.fixture
def extension_desechable() -> Any:
    """Una extension unica por ejecucion (`.dlvtest-<hex>`), con limpieza
    incondicional del registro real al terminar -- incluso si la prueba
    falla a mitad. Nunca `.csv` ni `.dlv`."""
    extension = f".dlvtest-{uuid.uuid4().hex[:12]}"
    try:
        yield extension
    finally:
        progid = progid_de(extension)
        _borrar_arbol_de_verdad(_ruta_extension(extension))
        _borrar_arbol_de_verdad(_ruta_progid(progid))
        _borrar_arbol_de_verdad(_ruta_respaldo(extension))
        # Los contenedores propios (ver `_RUTA_CONTENEDOR_RESPALDOS` en el
        # modulo): el codigo bajo prueba ya deberia haberlos dejado vacios y
        # borrados si la prueba llego a llamar a `desregistrar_extension`,
        # pero si la prueba fallo ANTES de esa llamada, esta es la red de
        # seguridad -- solo actua si de verdad estan vacios.
        _borrar_si_vacia_de_verdad(_RUTA_CONTENEDOR_RESPALDOS)
        _borrar_si_vacia_de_verdad(_RUTA_CONTENEDOR_APLICACION)


@pytest.mark.skipif(not ES_WINDOWS, reason="lee y escribe el registro real de Windows")
def test_ciclo_completo_contra_el_registro_real_sin_asociacion_previa(
    monkeypatch: pytest.MonkeyPatch, extension_desechable: str
) -> None:
    """Registra y desregistra una extension SIN dueno previo contra el HKCU
    de verdad. Es la rama que E10.4 cubre para `.dlv` (nadie mas la usa hoy).
    """
    _permitir_no_portable(monkeypatch)
    extension = extension_desechable
    progid = progid_de(extension)
    ejecutable = Path(r"C:\dist\dlv-app\dlv-app.exe")

    assert not _clave_existe_de_verdad(_ruta_extension(extension))

    resultado = registrar_extension(extension, ejecutable, almacen=None)
    assert resultado.progid == progid
    assert resultado.ya_estaba_asociada is False
    assert _leer_valor_por_omision_de_verdad(_ruta_extension(extension)) == progid
    comando_esperado = _comando_de_apertura(ejecutable)
    assert _leer_valor_por_omision_de_verdad(_ruta_comando(progid)) == comando_esperado

    desregistrar_extension(extension, almacen=None)

    assert not _clave_existe_de_verdad(_ruta_extension(extension))
    assert not _clave_existe_de_verdad(_ruta_progid(progid))
    assert not _clave_existe_de_verdad(_ruta_respaldo(extension))
    # Si esta era la unica extension con respaldo pendiente (lo normal en
    # una ejecucion aislada de esta prueba), los contenedores propios deben
    # haber desaparecido tambien -- ver `_RUTA_CONTENEDOR_RESPALDOS`.
    assert not _clave_existe_de_verdad(_RUTA_CONTENEDOR_RESPALDOS)
    assert not _clave_existe_de_verdad(_RUTA_CONTENEDOR_APLICACION)


@pytest.mark.skipif(not ES_WINDOWS, reason="lee y escribe el registro real de Windows")
def test_ciclo_completo_contra_el_registro_real_con_asociacion_previa(
    monkeypatch: pytest.MonkeyPatch, extension_desechable: str
) -> None:
    """Registra y desregistra una extension que YA tenia un dueno (simulado
    con un ProgID inventado, sin tocar `.csv` de verdad) contra el HKCU real.
    Es la rama que E10.4 cubre para `.csv` en la maquina de la mayoria de la
    gente: la que demuestra que "reversible" restaura, no borra sin mas.
    """
    _permitir_no_portable(monkeypatch)
    extension = extension_desechable
    progid = progid_de(extension)
    dueno_previo_simulado = "AplicacionFicticia.PruebaF5-17"

    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _ruta_extension(extension)) as clave:
        winreg.SetValueEx(clave, "", 0, winreg.REG_SZ, dueno_previo_simulado)

    registrar_extension(extension, Path(r"C:\dist\dlv-app\dlv-app.exe"), almacen=None)
    assert _leer_valor_por_omision_de_verdad(_ruta_extension(extension)) == progid
    assert _leer_valor_por_omision_de_verdad(_ruta_respaldo(extension)) == dueno_previo_simulado

    desregistrar_extension(extension, almacen=None)

    assert _leer_valor_por_omision_de_verdad(_ruta_extension(extension)) == dueno_previo_simulado
    assert not _clave_existe_de_verdad(_ruta_progid(progid))
    assert not _clave_existe_de_verdad(_ruta_respaldo(extension))
    assert not _clave_existe_de_verdad(_RUTA_CONTENEDOR_RESPALDOS)
    assert not _clave_existe_de_verdad(_RUTA_CONTENEDOR_APLICACION)

    # Limpieza extra: la clave `.ext` sigue existiendo (se restauro el valor
    # ficticio, no se borro), asi que el fixture por si solo no la quitaria
    # -- `_borrar_arbol_de_verdad` de la clave `.ext` en el fixture ya cubre
    # esto, pero se deja expresado aqui por que hace falta: sin esta prueba
    # dejando el dueno ficticio, el fixture solo tendria que limpiar cosas
    # que el propio modulo crea, y aqui la propia prueba anadio la clave
    # `.ext` con un valor ajeno antes de que el modulo la tocara.
