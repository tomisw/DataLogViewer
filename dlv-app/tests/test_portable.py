"""Modo portable (F5-02): la promesa de SS3.10 MEDIDA, no razonada.

La afirmacion que hay que sostener es «con un `portable.txt` junto al
ejecutable, la app no escribe nada fuera de su carpeta». Un docstring que lo
diga no vale nada: lo que vale es una prueba que ejecute la cadena real y
falle si aparece una escritura fuera. Eso es
`test_una_sesion_completa_no_escribe_nada_fuera_de_la_carpeta`, y el resto de
este fichero existe sobre todo para que esa prueba sea creible:

- `test_el_auditor_ve_una_escritura_deliberada_fuera` inyecta una infraccion
  real y comprueba que el auditor la caza. Es la leccion de `docs/09` SS9.10
  («detector de patrones por regex»): un detector que nunca se ha visto
  detectar algo no es un detector, es una decoracion.
- `test_el_auditor_no_marca_las_lecturas` cierra el fallo simetrico: un
  auditor que marcara tambien las lecturas se pondria rojo por abrir el log
  del usuario, y el arreglo obvio --relajarlo-- dejaria de medir.
- `test_la_sesion_completa_escribe_de_verdad_en_la_cache_portable` evita el
  peor resultado posible: que la prueba principal pase porque no se escribio
  NADA en ningun sitio (un fallo silencioso al abrir el log daria verde).

Lo que estas pruebas NO pueden ver son los procesos hijos: WebView2 corre en
`msedgewebview2.exe`, que no pasa por el gancho de auditoria de Python. Para
eso esta `test_ejecucion_real_no_deja_rastro_fuera`, que abre la aplicacion
DE VERDAD con ventana y compara instantaneas de directorios; necesita sesion
grafica, asi que se ejecuta bajo `DLV_PRUEBA_PORTABLE_REAL=1` y no en la
suite normal. El resultado de haberla ejecutado en esta maquina esta en el
informe de la tarea.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from dlv_app.portable import (
    NOMBRE_MARCA,
    NOMBRE_SUBCARPETA_DATOS,
    CarpetaPortableNoEscribible,
    Escritura,
    RutasPortables,
    activar_modo_portable,
    auditar_escrituras,
    carpeta_de_la_app,
    comprobar_escritura,
    diferencias_de_instantanea,
    escrituras_fuera_de,
    instantanea_superficial,
    modo_portable_activo,
    raices_candidatas,
)

RAIZ = Path(__file__).resolve().parents[2]
AUTOLOG_REAL = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"


@pytest.fixture
def entorno_aislado() -> Iterator[None]:
    """Devuelve `os.environ` y `tempfile.tempdir` a su estado original.

    `activar_modo_portable` muta los dos a proposito (es su trabajo), y sin
    esto una prueba dejaria a las siguientes escribiendo su cache en un
    `tmp_path` ya borrado.
    """
    tempdir_previo = tempfile.tempdir
    with mock.patch.dict(os.environ, clear=False):
        try:
            yield
        finally:
            tempfile.tempdir = tempdir_previo


def _carpeta_portable(base: Path, *, con_marca: bool = True) -> Path:
    """Una carpeta de app con (o sin) su `portable.txt`."""
    carpeta = base / "dlv-app"
    carpeta.mkdir(exist_ok=True)
    if con_marca:
        (carpeta / NOMBRE_MARCA).write_text(
            "Modo portable: DataLogViewer no escribira fuera de esta carpeta.\n",
            encoding="utf-8",
        )
    return carpeta


# --------------------------------------------------------------------------- #
# Que se considera «su carpeta»
# --------------------------------------------------------------------------- #
def test_en_el_arbol_de_desarrollo_la_carpeta_es_la_raiz_del_repositorio() -> None:
    """Sin `sys.frozen`, `sys.executable` es el interprete del entorno
    virtual y no dice nada de la app; la referencia es el repositorio."""
    assert carpeta_de_la_app() == RAIZ
    assert (carpeta_de_la_app() / "dlv-app" / "dlv_app.spec").is_file()


def test_en_un_paquete_congelado_la_carpeta_es_la_del_ejecutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La decision que mas consecuencia tiene de toda la tarea: en `onedir`,
    `sys._MEIPASS` es `_internal/`, una subcarpeta de tripas. Si la marca se
    buscara ahi, el `portable.txt` que el usuario deja junto al `.exe` --que
    es lo que promete SS3.10 y lo unico que se le puede pedir-- no activaria
    nada, y la app escribiria en `~/.dlv` creyendose portable.
    """
    ejecutable = tmp_path / "dist" / "dlv-app" / "dlv-app.exe"
    ejecutable.parent.mkdir(parents=True)
    ejecutable.write_bytes(b"")
    (ejecutable.parent / "_internal").mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(ejecutable.parent / "_internal"), raising=False)
    monkeypatch.setattr(sys, "executable", str(ejecutable))

    assert carpeta_de_la_app() == ejecutable.parent


# --------------------------------------------------------------------------- #
# Activacion: la marca, y solo la marca
# --------------------------------------------------------------------------- #
def test_sin_portable_txt_no_se_activa_ni_se_toca_el_entorno(
    tmp_path: Path, entorno_aislado: None
) -> None:
    carpeta = _carpeta_portable(tmp_path, con_marca=False)
    entorno_previo = dict(os.environ)

    assert modo_portable_activo(carpeta) is False
    assert activar_modo_portable(carpeta) is None
    assert dict(os.environ) == entorno_previo
    assert not (carpeta / NOMBRE_SUBCARPETA_DATOS).exists()


def test_un_portable_txt_vacio_basta(tmp_path: Path, entorno_aislado: None) -> None:
    """El contenido no se lee (ver `NOMBRE_MARCA`): quien crea el fichero lo
    hace con el explorador de Windows y no va a escribir nada dentro."""
    carpeta = _carpeta_portable(tmp_path, con_marca=False)
    (carpeta / NOMBRE_MARCA).write_bytes(b"")

    assert activar_modo_portable(carpeta) is not None


def test_una_carpeta_llamada_portable_txt_no_activa_nada(tmp_path: Path) -> None:
    carpeta = _carpeta_portable(tmp_path, con_marca=False)
    (carpeta / NOMBRE_MARCA).mkdir()

    assert modo_portable_activo(carpeta) is False


def test_activar_redirige_cache_temporales_y_perfil_de_webview(
    tmp_path: Path, entorno_aislado: None
) -> None:
    from dlv_api.main import VARIABLE_DIR_CACHE, directorio_cache_por_omision

    carpeta = _carpeta_portable(tmp_path)
    rutas = activar_modo_portable(carpeta)

    assert rutas is not None
    assert rutas.datos == carpeta / NOMBRE_SUBCARPETA_DATOS
    for destino in (rutas.datos, rutas.cache, rutas.temporales, rutas.webview):
        assert destino.is_dir(), f"{destino} tendria que existir ya creado"

    # No basta con que la variable este puesta: lo que importa es que la
    # funcion de `dlv-api` que decide donde va la cache devuelva esta ruta.
    assert os.environ[VARIABLE_DIR_CACHE] == str(rutas.cache)
    assert directorio_cache_por_omision() == rutas.cache

    # Y que `tempfile` --no solo el entorno-- haya cambiado de sitio: cachea
    # el directorio la primera vez que lo calcula.
    assert Path(tempfile.gettempdir()) == rutas.temporales
    for nombre in ("TMPDIR", "TEMP", "TMP"):
        assert os.environ[nombre] == str(rutas.temporales)


def test_el_modo_portable_pisa_una_dir_cache_puesta_desde_fuera(
    tmp_path: Path, entorno_aislado: None
) -> None:
    """Una variable de entorno es una preferencia; el `portable.txt` es una
    promesa. Si ganara la variable, un `DLV_DIR_CACHE` heredado del entorno
    del usuario romperia la promesa sin que nadie lo viera."""
    from dlv_api.main import VARIABLE_DIR_CACHE

    os.environ[VARIABLE_DIR_CACHE] = str(tmp_path / "fuera")
    rutas = activar_modo_portable(_carpeta_portable(tmp_path))

    assert rutas is not None
    assert os.environ[VARIABLE_DIR_CACHE] == str(rutas.cache)


# --------------------------------------------------------------------------- #
# Carpeta de solo lectura: fallar, nunca caer al modo no portable
# --------------------------------------------------------------------------- #
def test_una_carpeta_de_solo_lectura_falla_y_no_cae_al_modo_no_portable(
    tmp_path: Path, entorno_aislado: None
) -> None:
    """El caso de pista: el ZIP en una unidad de red de solo lectura o un USB
    con la pestana puesta. Lo que NO puede pasar es que arranque escribiendo
    en `~/.dlv`, que seria incumplir el `portable.txt` en silencio.

    La denegacion es real (ACL en Windows, permisos en POSIX), no un doble:
    lo que se quiere comprobar es precisamente que el sistema de ficheros
    dice que no, no que una funcion simulada lance.
    """
    carpeta = _carpeta_portable(tmp_path)
    entorno_previo = dict(os.environ)
    with _denegar_escritura(carpeta) as denegada:
        if not denegada:
            pytest.skip("no se pudo denegar la escritura en esta maquina (¿sesion elevada?)")
        with pytest.raises(CarpetaPortableNoEscribible) as fallo:
            activar_modo_portable(carpeta)

    assert str(carpeta) in str(fallo.value)
    assert NOMBRE_MARCA in str(fallo.value), "el mensaje tiene que decir como salir del modo"
    assert dict(os.environ) == entorno_previo, "no se redirige nada si no se puede cumplir"


def test_os_access_no_sirve_para_esto_en_windows(tmp_path: Path) -> None:
    """Justifica que `comprobar_escritura` escriba un fichero de sonda.

    MEDIDO, no citado de la documentacion: en Windows `os.access(..., W_OK)`
    solo mira el atributo de solo-lectura y no consulta las ACL, asi que
    sobre una carpeta con la escritura denegada por ACL sigue diciendo que
    si. Si esta prueba se pusiera roja algun dia, `comprobar_escritura`
    podria simplificarse; mientras diga esto, no.
    """
    carpeta = _carpeta_portable(tmp_path, con_marca=False)
    with _denegar_escritura(carpeta) as denegada:
        if not denegada:
            pytest.skip("no se pudo denegar la escritura en esta maquina")
        acceso_dice = os.access(carpeta, os.W_OK)
        with pytest.raises(CarpetaPortableNoEscribible):
            comprobar_escritura(carpeta)

    if sys.platform == "win32":
        assert acceso_dice is True, "si esto cambia, revisar el porque de comprobar_escritura"


class _Denegacion:
    """Contexto que quita el permiso de escritura de una carpeta y lo repone.

    Repone SIEMPRE, incluso si la prueba falla: una carpeta de `tmp_path` sin
    permiso de escritura hace que la limpieza de `pytest` falle mas tarde, en
    otra prueba, y ese rojo no se parece en nada a su causa.
    """

    def __init__(self, carpeta: Path) -> None:
        self._carpeta = carpeta
        self._modo_previo = carpeta.stat().st_mode

    def __enter__(self) -> bool:
        if sys.platform == "win32":
            usuario = os.environ.get("USERNAME", "")
            orden = ["icacls", str(self._carpeta), "/deny", f"{usuario}:(WD,AD)"]
            hecho = subprocess.run(orden, capture_output=True, text=True, check=False)
            if hecho.returncode != 0:
                return False
        else:
            os.chmod(self._carpeta, 0o500)
        try:
            descriptor, sonda = tempfile.mkstemp(dir=self._carpeta, prefix=".sonda-")
        except OSError:
            return True
        os.close(descriptor)
        os.unlink(sonda)
        return False  # la denegacion no ha surtido efecto (sesion elevada)

    def __exit__(self, *_excepcion: object) -> None:
        if sys.platform == "win32":
            usuario = os.environ.get("USERNAME", "")
            subprocess.run(
                ["icacls", str(self._carpeta), "/remove:d", usuario],
                capture_output=True,
                check=False,
            )
        else:
            os.chmod(self._carpeta, self._modo_previo)


def _denegar_escritura(carpeta: Path) -> _Denegacion:
    return _Denegacion(carpeta)


# --------------------------------------------------------------------------- #
# El auditor: probar que detecta antes de fiarse de que no detecta
# --------------------------------------------------------------------------- #
def test_el_auditor_ve_una_escritura_deliberada_fuera(tmp_path: Path) -> None:
    dentro = tmp_path / "dentro"
    fuera = tmp_path / "fuera"
    dentro.mkdir()
    fuera.mkdir()

    with auditar_escrituras() as escrituras:
        (dentro / "legitimo.txt").write_text("ok", encoding="utf-8")
        (fuera / "infraccion.txt").write_text("mal", encoding="utf-8")
        os.mkdir(fuera / "subcarpeta")

    infracciones = escrituras_fuera_de(escrituras, [dentro])
    rutas = {escritura.ruta.name for escritura in infracciones}
    assert "infraccion.txt" in rutas
    assert "subcarpeta" in rutas
    assert "legitimo.txt" not in rutas
    assert {"open", "os.mkdir"} <= {escritura.evento for escritura in infracciones}


def test_el_auditor_no_marca_las_lecturas(tmp_path: Path) -> None:
    """Abrir el log del usuario --que esta fuera de la carpeta portable, y
    tiene que estarlo-- no es una infraccion. Un auditor que lo marcara se
    pondria rojo siempre y acabaria relajado hasta no medir nada."""
    ajeno = tmp_path / "log-del-usuario.csv"
    ajeno.write_text("tiempo,rpm\n0,800\n", encoding="utf-8")

    with auditar_escrituras() as escrituras:
        ajeno.read_text(encoding="utf-8")
        with open(ajeno, "rb") as fichero:
            fichero.read()
        descriptor = os.open(ajeno, os.O_RDONLY)
        os.close(descriptor)

    assert escrituras_fuera_de(escrituras, [tmp_path / "no-existe"]) == []


def test_dos_auditorias_a_la_vez_fallan_en_vez_de_repartirse_los_eventos() -> None:
    with auditar_escrituras(), pytest.raises(RuntimeError), auditar_escrituras():
        pass  # pragma: no cover - el segundo `auditar_escrituras` ya ha lanzado


def test_el_auditor_queda_inerte_al_salir_del_bloque(tmp_path: Path) -> None:
    """`sys.addaudithook` no se puede desinstalar; el interruptor es la
    variable de modulo. Si se quedara encendido, el gancho seguiria corriendo
    en cada `open` del resto de la suite."""
    with auditar_escrituras() as escrituras:
        pass
    (tmp_path / "despues.txt").write_text("x", encoding="utf-8")

    assert escrituras == []


# --------------------------------------------------------------------------- #
# La medicion: una sesion real con el log real del propietario
# --------------------------------------------------------------------------- #
def _sesion_completa(dir_cache: Path | None) -> int:
    """Abre `AutoLog_20260729_1830.csv` por HTTP y recorre la cadena entera.

    Es el camino que de verdad escribe cosas: `abrir-log` parsea y deja el
    `.dlvcache` (ADR-005), `cubos` sirve la piramide, `exportar-datos` pasa
    por Polars para producir CSV y Parquet, y `cerrar-log` suelta la sesion.
    Devuelve el numero de canales, solo para que quien llama pueda comprobar
    que se abrio algo de verdad.

    `dir_cache=None` es lo que ejercita el cableado real del modo portable:
    `crear_app` cae entonces en `directorio_cache_por_omision()`, que lee
    `DLV_DIR_CACHE`.
    """
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from dlv_api.main import crear_app, generar_token_sesion

    token = generar_token_sesion()
    cabeceras = {"Authorization": f"Bearer {token}"}
    app = crear_app(token_sesion=token, dir_cache=dir_cache)
    with fastapi_testclient.TestClient(app) as http:

        def post(ruta: str, cuerpo: dict[str, Any]) -> Any:
            respuesta = http.post(ruta, json=cuerpo, headers=cabeceras)
            assert respuesta.status_code == 200, f"{ruta}: {respuesta.text}"
            return respuesta

        abierto = post("/comandos/abrir-log", {"ruta": str(AUTOLOG_REAL)}).json()
        id_sesion = abierto["id_sesion"]
        canal = next(c for c in abierto["canales"] if len(c["niveles"]) >= 2)
        for nivel in (0, 1):
            post(
                "/comandos/cubos",
                {
                    "id_sesion": id_sesion,
                    "canal_id": canal["id"],
                    "nivel": nivel,
                    "t0": abierto["t_inicio"],
                    "t1": abierto["t_fin"],
                },
            )
        # `/comandos/serie` se pide por RUTA, no por sesion (ver
        # `ComandoSerie`): es otro camino de lectura del fichero, y por eso
        # entra en la medicion aunque `abrir-log` ya haya pasado.
        post("/comandos/serie", {"ruta": str(AUTOLOG_REAL), "canal_id": canal["id"]})
        for formato in ("csv", "parquet"):
            post(
                "/comandos/exportar-datos",
                {
                    "id_sesion": id_sesion,
                    "canales_ids": [canal["id"]],
                    "formato": formato,
                },
            )
        post("/comandos/cerrar-log", {"id_sesion": id_sesion})
    return int(abierto["n_canales"])


@pytest.fixture(scope="module")
def calentamiento() -> int:
    """Ejecuta la cadena una vez ANTES de medir, con la cache aparte.

    Sin esto la medicion saldria llena de ruido que no es del modo portable:
    la primera pasada escribe los `.pyc` de todo lo que Polars, FastAPI y
    uvicorn importan de forma diferida (dentro de una funcion, no en la
    cabecera del modulo), y esos `__pycache__` caen en el entorno virtual,
    fuera de la carpeta portable. En el paquete congelado no existen --el
    bytecode va dentro del `PYZ`--, asi que descontarlos aqui no esconde
    ningun fallo real del producto; dejarlos, en cambio, obligaria a
    perdonarlos con una regla generica de «ignora los .pyc», que es la clase
    de excepcion que luego se traga una infraccion de verdad.
    """
    with tempfile.TemporaryDirectory(prefix="dlv-calentamiento-") as temporal:
        return _sesion_completa(Path(temporal))


def test_una_sesion_completa_no_escribe_nada_fuera_de_la_carpeta(
    tmp_path: Path, entorno_aislado: None, calentamiento: int
) -> None:
    """LA prueba de esta tarea (SS3.10, E10.1).

    Abre el log real del propietario, construye la piramide, exporta a CSV y
    a Parquet y cierra, con el modo portable activo y LOS DOS instrumentos
    puestos a la vez:

    1. el gancho de auditoria, que ve toda escritura de Python en cualquier
       punto del disco (incluidos los que nadie enumeró: escribir la cache al
       lado del log, en `samples/real/`, saldria aqui);
    2. la instantanea de las raices candidatas, que ve las entradas nuevas
       las escriba quien las escriba -- y es la unica que cubre los 18
       Parquet que Polars escribe desde Rust sin pasar por Python.

    Ninguno de los dos basta solo; el porque de cada uno esta en la tabla del
    docstring de `dlv_app.portable`.
    """
    carpeta = _carpeta_portable(tmp_path)
    rutas = activar_modo_portable(carpeta)
    assert rutas is not None

    raices = raices_candidatas()
    antes = {raiz: instantanea_superficial(raiz) for raiz in raices}
    with auditar_escrituras() as escrituras:
        n_canales = _sesion_completa(None)
    despues = {raiz: instantanea_superficial(raiz) for raiz in raices}

    assert n_canales > 0
    fuera = escrituras_fuera_de(escrituras, rutas.como_tupla())
    assert not fuera, "el modo portable escribio fuera de su carpeta:\n" + "\n".join(
        f"  {escritura.evento}: {escritura.ruta}" for escritura in fuera
    )

    nuevas = diferencias_de_instantanea(antes, despues)
    assert not nuevas, "aparecieron entradas nuevas fuera de la carpeta portable:\n" + "\n".join(
        f"  {raiz}: {sorted(entradas)}" for raiz, entradas in nuevas.items()
    )


def test_la_sesion_completa_escribe_de_verdad_en_la_cache_portable(
    tmp_path: Path, entorno_aislado: None, calentamiento: int
) -> None:
    """La prueba de arriba pasaria tambien si no se escribiera NADA --por
    ejemplo si abrir el log fallara en silencio--, y ese verde seria el peor
    resultado posible. Esta comprueba que el auditor ve escrituras reales y
    que el `.dlvcache` acaba dentro de la carpeta portable.
    """
    carpeta = _carpeta_portable(tmp_path)
    rutas = activar_modo_portable(carpeta)
    assert rutas is not None

    with auditar_escrituras() as escrituras:
        _sesion_completa(None)

    dentro = [e for e in escrituras if e.dentro_de([rutas.cache])]
    assert dentro, "no se observo ninguna escritura: la medicion no estaba midiendo"
    assert list(rutas.cache.glob("*.dlvcache*")), "el .dlvcache no acabo en la carpeta portable"


def test_sin_modo_portable_esa_misma_medicion_se_pone_roja(
    tmp_path: Path, entorno_aislado: None, calentamiento: int
) -> None:
    """Control negativo de la prueba principal, y la unica forma de saber que
    su verde significa algo.

    Se ejecuta la MISMA sesion completa con la cache apuntando fuera de la
    carpeta --que es exactamente lo que hace la app sin `portable.txt`, solo
    que hacia `~/.dlv/cache` en vez de hacia un directorio de prueba-- y se
    exige que el auditor la marque. Si esto saliera verde, la prueba de
    arriba no estaria comprobando nada.

    La cache se apunta a `tmp_path` y no a `~/.dlv` a proposito: el control
    negativo no tiene por que ensuciar la carpeta del propietario para
    demostrar lo que demuestra.
    """
    from dlv_api.main import VARIABLE_DIR_CACHE

    carpeta = _carpeta_portable(tmp_path, con_marca=False)
    os.environ[VARIABLE_DIR_CACHE] = str(tmp_path / "cache-fuera-de-la-carpeta")

    with auditar_escrituras() as escrituras:
        _sesion_completa(None)

    fuera = escrituras_fuera_de(escrituras, [carpeta])
    assert fuera, "la medicion no distingue una cache fuera de la carpeta: no mide nada"
    assert any("cache-fuera-de-la-carpeta" in str(escritura.ruta) for escritura in fuera)


def test_la_instantanea_ve_los_parquet_que_el_gancho_de_python_no_ve(
    tmp_path: Path, entorno_aislado: None, calentamiento: int
) -> None:
    """Control negativo del SEGUNDO instrumento, y la justificacion de que
    existan dos.

    MEDIDO: una sesion completa deja 20 ficheros en la cache y el gancho de
    auditoria registra solo dos eventos --el `os.mkdir` del directorio y el
    `open` del `.dlvcache.json`--, porque los 18 Parquet de la piramide los
    escribe Polars desde Rust, sin pasar por la maquina virtual de Python.
    Esta prueba fija ese hecho: si algun dia Polars escribiera a traves de un
    objeto fichero de Python, el gancho pasaria a verlos y esto se pondria
    rojo, que es justo cuando conviene releer la tabla de instrumentos.

    La cache se apunta a `tmp_path`, que YA existe en la instantanea, para
    que lo que aparezca de nuevo en el primer nivel sean los ficheros que
    escribe Rust y no un directorio creado por Python.
    """
    from dlv_api.main import VARIABLE_DIR_CACHE

    os.environ[VARIABLE_DIR_CACHE] = str(tmp_path)
    antes = {tmp_path: instantanea_superficial(tmp_path)}
    with auditar_escrituras() as escrituras:
        _sesion_completa(None)
    nuevas = diferencias_de_instantanea(antes, {tmp_path: instantanea_superficial(tmp_path)})

    aparecidos = nuevas.get(tmp_path, frozenset())
    parquet = {nombre for nombre in aparecidos if nombre.endswith(".parquet")}
    assert len(parquet) >= 10, f"la instantanea no vio los Parquet de la piramide: {aparecidos}"

    vistos_por_el_gancho = {escritura.ruta.name for escritura in escrituras}
    assert not (parquet & vistos_por_el_gancho), (
        "el gancho de Python ha empezado a ver los Parquet de Polars: revisar la "
        "tabla de instrumentos del docstring de dlv_app.portable"
    )


# --------------------------------------------------------------------------- #
# Medicion por instantanea: la unica que ve a los procesos hijos
# --------------------------------------------------------------------------- #
def test_las_raices_candidatas_incluyen_los_sitios_que_nombra_el_codigo() -> None:
    raices = raices_candidatas()

    assert Path.home() / ".dlv" in raices, "es donde va la cache sin modo portable"
    assert Path.home() / ".dlv" / "cache" in raices, (
        "la instantanea es de primer nivel: sin esta raiz, un .dlvcache nuevo "
        "dentro de una carpeta 'cache' que ya existia no se veria"
    )
    if sys.platform == "win32":
        assert any("Temp" in str(raiz) for raiz in raices), (
            "el perfil de WebView2 cae en %TEMP% con el private_mode por omision"
        )


def test_diferencias_de_instantanea_solo_reporta_lo_nuevo(tmp_path: Path) -> None:
    antes = {tmp_path: instantanea_superficial(tmp_path)}
    (tmp_path / "aparecido.txt").write_text("x", encoding="utf-8")
    despues = {tmp_path: instantanea_superficial(tmp_path)}

    assert diferencias_de_instantanea(antes, antes) == {}
    assert diferencias_de_instantanea(antes, despues) == {tmp_path: frozenset({"aparecido.txt"})}


@pytest.mark.skipif(
    os.environ.get("DLV_PRUEBA_PORTABLE_REAL") != "1",
    reason="abre una ventana real: hace falta sesion grafica. Ver el docstring del modulo.",
)
def test_ejecucion_real_no_deja_rastro_fuera(tmp_path: Path) -> None:
    """Arranca la aplicacion DE VERDAD (ventana incluida) con el log real y
    compara instantaneas de `~/.dlv`, `%APPDATA%`, `%LOCALAPPDATA%`, `%TEMP%`
    y el perfil del usuario antes y despues.

    Es la unica medicion que ve lo que hacen los procesos hijos de WebView2,
    que el gancho de auditoria de Python no puede ver por definicion. Se
    ejecuta con `DLV_PRUEBA_PORTABLE_REAL=1 python -m pytest
    dlv-app/tests/test_portable.py -k real`.

    La marca `portable.txt` va en la raiz del repositorio porque en el arbol
    de desarrollo esa es la carpeta de la app (`carpeta_de_la_app`), y se
    borra al terminar pase lo que pase: dejarla puesta cambiaria en silencio
    el comportamiento de la siguiente ejecucion de cualquiera.
    """
    marca = RAIZ / NOMBRE_MARCA
    datos = RAIZ / NOMBRE_SUBCARPETA_DATOS
    marca.write_text("prueba F5-02\n", encoding="utf-8")
    try:
        raices = raices_candidatas()
        antes = {raiz: instantanea_superficial(raiz) for raiz in raices}
        proceso = subprocess.Popen(
            [sys.executable, "-m", "dlv_app", str(AUTOLOG_REAL)],
            cwd=RAIZ,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            # Tiempo para arrancar dlv-api, abrir la ventana, cargar el
            # frontend y pedir los cubos del log. No hay forma de cerrar la
            # ventana desde fuera sin instrumentar `main()`, asi que se le da
            # margen y se termina el proceso.
            proceso.wait(timeout=float(os.environ.get("DLV_SEGUNDOS_PORTABLE", "25")))
        except subprocess.TimeoutExpired:
            proceso.terminate()
            proceso.wait(timeout=15)
        despues = {raiz: instantanea_superficial(raiz) for raiz in raices}
    finally:
        marca.unlink(missing_ok=True)

    nuevas = diferencias_de_instantanea(antes, despues)
    assert datos.is_dir(), "la app no llego a crear su carpeta de datos portable"
    assert not nuevas, "la ejecucion real dejo entradas nuevas fuera de la carpeta:\n" + "\n".join(
        f"  {raiz}: {sorted(entradas)}" for raiz, entradas in nuevas.items()
    )


def test_rutas_portables_declara_todas_sus_carpetas_como_dentro(tmp_path: Path) -> None:
    """`como_tupla` es lo que la auditoria considera «dentro». Si se anadiera
    un campo nuevo a `RutasPortables` y no se anadiera ahi, la prueba
    principal empezaria a marcar como infraccion algo que si es legitimo."""
    rutas = RutasPortables(
        carpeta=tmp_path,
        datos=tmp_path / "d",
        cache=tmp_path / "d" / "c",
        temporales=tmp_path / "d" / "t",
        webview=tmp_path / "d" / "w",
    )

    campos = {getattr(rutas, nombre) for nombre in RutasPortables.__dataclass_fields__}
    assert campos == set(rutas.como_tupla())
    assert Escritura(evento="open", ruta=tmp_path / "d" / "c" / "x").dentro_de(rutas.como_tupla())
