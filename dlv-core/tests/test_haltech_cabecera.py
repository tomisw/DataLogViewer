"""Pruebas del parser de cabecera Haltech (tarea F1-01).

La especificación ejecutable es `samples/corrupt/README.md`: por cada fichero del
corpus de corruptos dice si el parser debe cargar sin aviso, cargar con aviso o
rechazar con error. Estas pruebas comprueban exactamente eso, además de los tres
logs reales.

Solo biblioteca estándar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlv_core.formatos.haltech import (
    BOM_UTF8,
    Aviso,
    Cabecera,
    Descriptor,
    ErrorDeFormato,
    cargar_descriptor,
    parsear_cabecera,
    sondear_formato,
)

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
REALES = RAIZ / "samples" / "real"
CORRUPTOS = RAIZ / "samples" / "corrupt"
VERDAD = RAIZ / "samples" / "verdad" / "verdad.csv"


@pytest.fixture(scope="module")
def desc() -> Descriptor:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return cargar_descriptor(fh)


def leer(ruta: Path) -> bytes:
    return ruta.read_bytes()


def parsea(ruta: Path, desc: Descriptor) -> Cabecera:
    return parsear_cabecera(leer(ruta), desc)


def codigos(cab: Cabecera) -> set[str]:
    return {a.codigo for a in cab.avisos}


# --------------------------------------------------------------------------- #
# Descriptor y sondeo
# --------------------------------------------------------------------------- #
def test_el_descriptor_carga(desc: Descriptor) -> None:
    assert desc.formato == "haltech_nsp"
    assert desc.firma == b"%DataLog%"
    assert "1.1" in desc.versiones_soportadas
    assert len(desc.tipos) == 34


def test_el_sondeo_reconoce_la_firma(desc: Descriptor) -> None:
    assert sondear_formato(b"%DataLog%\r\nDataLogVersion : 1.1\r\n", (desc,)) is desc


def test_el_sondeo_tolera_el_bom(desc: Descriptor) -> None:
    assert sondear_formato(BOM_UTF8 + b"%DataLog%\r\n", (desc,)) is desc


def test_el_sondeo_devuelve_none_para_un_csv_cualquiera(desc: Descriptor) -> None:
    """`None` significa «ve por el camino genérico», no «fichero inválido»."""
    assert sondear_formato(b"Tiempo;RPM;MAP\r\n0,00;900;33,2\r\n", (desc,)) is None


# --------------------------------------------------------------------------- #
# Los tres logs reales
# --------------------------------------------------------------------------- #
def test_autolog_real(desc: Descriptor) -> None:
    cab = parsea(REALES / "AutoLog_20260729_1830.csv", desc)
    assert cab.version == "1.1"
    assert cab.n_canales == 475
    assert cab.n_columnas == 476
    assert cab.metadatos["Software"] == "Haltech NSP"
    assert cab.metadatos["Log Source"] == "0"
    # El orden de los bloques fija la columna (docs/01 §1.3).
    rpm = cab.por_nombre("RPM")
    assert rpm is not None and rpm.id == 384 and rpm.tipo == "EngineSpeed"
    assert cab.por_id(384) is rpm


def test_los_logs_internos_reales(desc: Descriptor) -> None:
    for nombre in ("20260729_1859_Log2768.csv", "20260729_1859_Log2769.csv"):
        cab = parsea(REALES / nombre, desc)
        assert cab.n_canales == 25
        assert cab.metadatos["Log Source"] == "8"
        # Epoch ficticia: la ECU no tiene reloj (docs/01 §1.5).
        assert cab.metadatos["Log"].startswith("19800101")


def test_los_13_canales_sin_displaymaxmin_del_autolog(desc: Descriptor) -> None:
    """La ausencia de DisplayMaxMin es legal y no debe desalinear nada."""
    cab = parsea(REALES / "AutoLog_20260729_1830.csv", desc)
    sin = [c for c in cab.canales if c.display_max is None]
    assert len(sin) == 13
    # Y los órdenes siguen siendo consecutivos: no se ha perdido ni colado nada.
    assert [c.orden for c in cab.canales] == list(range(475))


def test_las_escalas_salen_del_descriptor_no_del_codigo(desc: Descriptor) -> None:
    cab = parsea(REALES / "AutoLog_20260729_1830.csv", desc)
    coolant = cab.por_nombre("Coolant Temperature")
    assert coolant is not None
    assert coolant.dimension == "temperature"
    assert coolant.a_canonica == 0.1  # deciKelvin
    assert coolant.confianza == "confirmed"


def test_los_tipos_sin_escala_confirmada_se_marcan(desc: Descriptor) -> None:
    """Mitigación de R1: sin escala confirmada, en crudo y sin unidad."""
    cab = parsea(REALES / "AutoLog_20260729_1830.csv", desc)
    maf = cab.por_nombre("Mass Air Flow 1")
    assert maf is not None
    assert maf.confianza == "unknown"
    assert maf.se_muestra_en_crudo
    assert "escala_sin_confirmar" in codigos(cab)


def test_el_log_de_verdad_de_referencia(desc: Descriptor) -> None:
    cab = parsear_cabecera(leer(VERDAD), desc)
    assert cab.n_canales == 20
    assert cab.por_nombre("Knock Sensor 1 Knock Count") is not None


# --------------------------------------------------------------------------- #
# Corpus de corruptos: la especificación es samples/corrupt/README.md
# --------------------------------------------------------------------------- #
def test_01_cabecera_truncada_se_rechaza(desc: Descriptor) -> None:
    with pytest.raises(ErrorDeFormato, match="truncada"):
        parsea(CORRUPTOS / "01-cabecera-truncada.csv", desc)


def test_10_version_desconocida_se_rechaza(desc: Descriptor) -> None:
    """Rechazo explícito, no intento de leerlo: la gramática podría haber
    cambiado y el resultado sería silenciosamente equivocado."""
    with pytest.raises(ErrorDeFormato, match=r"2\.0"):
        parsea(CORRUPTOS / "10-version-desconocida.csv", desc)


@pytest.mark.parametrize(
    "fichero",
    [
        "04-sin-displaymaxmin.csv",
        "05-bom-utf8.csv",
        "06-lf-solo.csv",
        "07-sin-salto-final.csv",
        "09-cruce-medianoche.csv",
    ],
)
def test_los_ficheros_validos_cargan_sin_avisos_de_cabecera(fichero: str, desc: Descriptor) -> None:
    """Estos cinco son legales: el parser debe leerlos como el original.

    Se compara contra la cabecera del log real del que derivan, para que la
    prueba falle si alguno deja de ser equivalente.
    """
    cab = parsea(CORRUPTOS / fichero, desc)
    original = parsea(REALES / "20260729_1859_Log2768.csv", desc)
    assert cab.n_canales == original.n_canales == 25
    assert [c.id for c in cab.canales] == [c.id for c in original.canales]
    assert [c.tipo for c in cab.canales] == [c.tipo for c in original.canales]
    # El único aviso admisible es el de escala sin confirmar, que también tiene
    # el original: no es una consecuencia de la corrupción.
    assert codigos(cab) <= codigos(original) | {"escala_sin_confirmar"}


def test_04_sin_displaymaxmin_pierde_exactamente_tres(desc: Descriptor) -> None:
    cab = parsea(CORRUPTOS / "04-sin-displaymaxmin.csv", desc)
    original = parsea(REALES / "20260729_1859_Log2768.csv", desc)
    sin_cab = sum(1 for c in cab.canales if c.display_max is None)
    sin_org = sum(1 for c in original.canales if c.display_max is None)
    assert sin_cab - sin_org == 3


def test_05_el_bom_no_deja_rastro(desc: Descriptor) -> None:
    """El BOM es legítimo y el usuario no puede hacer nada con esa información,
    así que no genera aviso."""
    cab = parsea(CORRUPTOS / "05-bom-utf8.csv", desc)
    assert cab.metadatos["Software"] == "Haltech NSP"
    assert "bom" not in " ".join(codigos(cab))


def test_06_lf_solo_y_el_original_crlf_dan_la_misma_cabecera(desc: Descriptor) -> None:
    """El formato nativo es CRLF; LF aparece cuando algo reescribe el log en
    Unix. Los dos deben dar exactamente lo mismo (docs/01 §1.13)."""
    lf = parsea(CORRUPTOS / "06-lf-solo.csv", desc)
    crlf = parsea(REALES / "20260729_1859_Log2768.csv", desc)
    assert lf.canales == crlf.canales
    assert lf.metadatos == crlf.metadatos


def test_los_ficheros_con_filas_alteradas_tienen_cabecera_intacta(desc: Descriptor) -> None:
    """02, 03, 08 y 11 estropean FILAS, no la cabecera: el parser de cabecera no
    debe verse afectado. Detectar esas anomalías es del parseo del cuerpo."""
    original = parsea(REALES / "20260729_1859_Log2768.csv", desc)
    for fichero in (
        "02-fila-corta.csv",
        "03-fila-larga.csv",
        "08-marcas-no-monotonas.csv",
        "11-centinelas.csv",
    ):
        cab = parsea(CORRUPTOS / fichero, desc)
        assert cab.canales == original.canales, fichero
        assert cab.n_columnas == 26, fichero


# --------------------------------------------------------------------------- #
# Casos límite construidos a mano
# --------------------------------------------------------------------------- #
def cabecera_minima(
    *, version: str = "1.1", extra: str = "", canales: str = "", filas: str = ""
) -> bytes:
    cuerpo = (
        "%DataLog%\r\n"
        f"DataLogVersion : {version}\r\n"
        "Software : Haltech NSP\r\n"
        f"{extra}"
        f"{canales}"
        "Log Source : 0\r\n"
        f"{filas}"
    )
    return cuerpo.encode("utf-8")


CANAL_OK = "Channel : RPM\r\nID : 384\r\nType : EngineSpeed\r\nDisplayMaxMin : 20000,0\r\n"
FILA_OK = "01:01:01.005,900\r\n"


def test_una_cabecera_minima_valida_carga(desc: Descriptor) -> None:
    cab = parsear_cabecera(cabecera_minima(canales=CANAL_OK, filas=FILA_OK), desc)
    assert cab.n_canales == 1
    assert cab.canales[0].nombre == "RPM"


def test_sin_firma_se_rechaza(desc: Descriptor) -> None:
    with pytest.raises(ErrorDeFormato, match="firma"):
        parsear_cabecera(b"Tiempo,RPM\r\n0,900\r\n", desc)


def test_sin_version_se_rechaza(desc: Descriptor) -> None:
    datos = b"%DataLog%\r\nSoftware : Haltech NSP\r\n" + CANAL_OK.encode() + FILA_OK.encode()
    with pytest.raises(ErrorDeFormato, match="DataLogVersion"):
        parsear_cabecera(datos, desc)


def test_sin_canales_se_rechaza(desc: Descriptor) -> None:
    with pytest.raises(ErrorDeFormato, match="ningún canal"):
        parsear_cabecera(cabecera_minima(filas=FILA_OK), desc)


def test_sin_filas_se_rechaza(desc: Descriptor) -> None:
    with pytest.raises(ErrorDeFormato, match="truncada"):
        parsear_cabecera(cabecera_minima(canales=CANAL_OK), desc)


def test_un_bloque_sin_type_se_rechaza(desc: Descriptor) -> None:
    """Sin Type no se puede saber con qué escala leer la columna, así que seguir
    daría datos silenciosamente mal escalados."""
    canal = "Channel : RPM\r\nID : 384\r\n"
    with pytest.raises(ErrorDeFormato, match="no declara Type"):
        parsear_cabecera(cabecera_minima(canales=canal, filas=FILA_OK), desc)


def test_un_bloque_sin_id_se_rechaza(desc: Descriptor) -> None:
    canal = "Channel : RPM\r\nType : EngineSpeed\r\n"
    with pytest.raises(ErrorDeFormato, match="no declara ID"):
        parsear_cabecera(cabecera_minima(canales=canal, filas=FILA_OK), desc)


def test_un_id_no_numerico_se_rechaza(desc: Descriptor) -> None:
    canal = "Channel : RPM\r\nID : trescientos\r\nType : EngineSpeed\r\n"
    with pytest.raises(ErrorDeFormato, match="ID no numérico"):
        parsear_cabecera(cabecera_minima(canales=canal, filas=FILA_OK), desc)


def test_un_tipo_desconocido_avisa_y_sigue(desc: Descriptor) -> None:
    """El parser avisa y carga: el canal se muestra en crudo, sin unidad."""
    canal = "Channel : Algo\r\nID : 9999\r\nType : TipoInventado\r\n"
    cab = parsear_cabecera(cabecera_minima(canales=canal, filas=FILA_OK), desc)
    assert cab.n_canales == 1
    assert cab.canales[0].dimension is None
    assert cab.canales[0].se_muestra_en_crudo
    assert "tipo_desconocido" in codigos(cab)


def test_una_displaymaxmin_mal_formada_avisa_y_sigue(desc: Descriptor) -> None:
    canal = "Channel : RPM\r\nID : 384\r\nType : EngineSpeed\r\nDisplayMaxMin : hola\r\n"
    cab = parsear_cabecera(cabecera_minima(canales=canal, filas=FILA_OK), desc)
    assert cab.n_canales == 1
    assert cab.canales[0].display_max is None
    assert "displaymaxmin_invalida" in codigos(cab)


def test_nombres_duplicados_avisan_pero_no_bloquean(desc: Descriptor) -> None:
    """El formato no garantiza unicidad de nombre; la identidad es el ID."""
    dos = CANAL_OK + "Channel : RPM\r\nID : 385\r\nType : EngineSpeed\r\n"
    cab = parsear_cabecera(cabecera_minima(canales=dos, filas="01:01:01.005,900,901\r\n"), desc)
    assert cab.n_canales == 2
    assert "nombre_duplicado" in codigos(cab)


def test_ids_duplicados_avisan(desc: Descriptor) -> None:
    """Un ID repetido haría ambiguo el emparejamiento entre logs (docs/07 §7.11)."""
    dos = CANAL_OK + "Channel : Otro\r\nID : 384\r\nType : EngineSpeed\r\n"
    cab = parsear_cabecera(cabecera_minima(canales=dos, filas="01:01:01.005,900,901\r\n"), desc)
    assert "id_duplicado" in codigos(cab)


def test_el_offset_de_datos_apunta_a_la_primera_fila(desc: Descriptor) -> None:
    """Lo usa el parseo del cuerpo para saltarse la cabecera sin recorrerla otra
    vez, así que tiene que ser exacto."""
    datos = cabecera_minima(canales=CANAL_OK, filas=FILA_OK)
    cab = parsear_cabecera(datos, desc)
    assert datos[cab.offset_datos :].startswith(b"01:01:01.005,")


def test_el_offset_es_exacto_sobre_el_autolog_real(desc: Descriptor) -> None:
    datos = leer(REALES / "AutoLog_20260729_1830.csv")
    cab = parsear_cabecera(datos, desc)
    assert datos[cab.offset_datos :].startswith(b"18:30:35.506,")


def test_el_offset_es_exacto_con_bom(desc: Descriptor) -> None:
    """El offset es relativo a los bytes que se pasaron, BOM incluido, para que
    `datos[offset:]` funcione sin acordarse del BOM. La primera versión lo
    devolvía relativo a los datos ya despojados del BOM, y eso dejaba a quien
    llamara desplazado tres bytes sin avisar."""
    datos = leer(CORRUPTOS / "05-bom-utf8.csv")
    cab = parsear_cabecera(datos, desc)
    assert datos.startswith(BOM_UTF8)
    assert datos[cab.offset_datos :].startswith(b"01:01:01.005,")
    # Y el offset de la versión con BOM es exactamente 3 bytes mayor que el de
    # la versión sin él: ni más ni menos.
    sin = parsear_cabecera(leer(REALES / "20260729_1859_Log2768.csv"), desc)
    assert cab.offset_datos - sin.offset_datos == len(BOM_UTF8)


def test_el_aviso_se_imprime_de_forma_legible() -> None:
    a = Aviso("tipo_desconocido", "el tipo 'X' no está en el descriptor", 42)
    assert str(a) == "[tipo_desconocido] (línea 42) el tipo 'X' no está en el descriptor"
