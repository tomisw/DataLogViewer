"""Pruebas de la columna de tiempo del CSV genérico (tarea FG-04).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.5.

QUÉ PROTEGE ESTA SUITE
======================
El eje X es lo único que comparten todos los canales, así que un error aquí no
estropea un canal: estropea el log entero, y de formas que parecen razonables.
Confundir epoch en segundos con epoch en milisegundos dibuja un log de cinco
minutos como uno de tres días. Interpretar un eje relativo en milisegundos como
segundos lo dibuja mil veces más largo. Y tomar un contador de muestras por
segundos inventa la escala del eje sin que nada falle.

Cuatro reglas, por consecuencia:

1. **Epoch en segundos o en milisegundos se distingue por MAGNITUD.** Es lo único
   que los separa: los dos son enteros válidos.
2. **La unidad de un eje relativo la da el PASO, no un valor suelto.**
3. **Un contador de muestras NO es tiempo** hasta que el usuario declara la
   frecuencia. Suponerla inventa la escala del eje X completo.
4. **Nunca se finge precisión temporal que no existe** (§7.5, literal). Un eje
   sintético se marca igual que un log interno de ECU sin reloj de tiempo real, y
   la vista concatenada exige desfase manual.

Solo biblioteca estándar.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from dlv_core.formatos.decimal_csv import detectar_separador_decimal
from dlv_core.formatos.estructura import analizar_estructura
from dlv_core.formatos.sondeo import sondear_csv
from dlv_core.formatos.tiempo_csv import (
    ClaseDeTiempo,
    ErrorDeTiempoCsv,
    detectar_columna_de_tiempo,
    parsear_instante,
)
from dlv_core.tiempo import FiabilidadReloj

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
DOS_FORMATOS = RAIZ / "samples" / "dos-formatos"


def analizar(datos: bytes, **kwargs: object) -> object:
    """La cadena entera: FG-01 → FG-02 → FG-03 → FG-04.

    Se ejercita completa a propósito: un fallo en la costura entre tareas —el
    separador decimal que no llega, el inicio de datos mal calculado— no lo vería
    ninguna prueba que las mirara por separado.
    """
    s = sondear_csv(datos)
    texto = datos.decode(s.codificacion)
    d = detectar_separador_decimal(s, texto)
    e = analizar_estructura(s, d, texto)
    return detectar_columna_de_tiempo(s, d, e, texto, **kwargs)  # type: ignore[arg-type]


def de(ruta: Path, **kwargs: object) -> object:
    return analizar(ruta.read_bytes(), **kwargs)


def codigos(t: object) -> set[str]:
    return {a.codigo for a in t.avisos}  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Las ocho variantes de §7.5, con los ficheros del corpus
# --------------------------------------------------------------------------- #
def test_relativo_en_segundos() -> None:
    """`0.000`, `0.050`, … con paso de 50 ms: segundos."""
    t = de(GENERICOS / "01-coma-punto.csv")
    assert t.clase is ClaseDeTiempo.RELATIVO
    assert t.indice == 0
    assert t.nombre == "Time"
    assert t.factor_a_segundos == 1.0
    assert t.paso_mediano_s == pytest.approx(0.05)
    assert t.frecuencia_hz == pytest.approx(20.0)
    assert t.t0_absoluto is None, "un eje relativo no sitúa el log en el calendario"
    assert t.fiabilidad is FiabilidadReloj.DESCONOCIDA


def test_relativo_con_coma_decimal() -> None:
    """La costura con FG-02: `0,050` solo es un número si el decimal es la coma."""
    t = de(GENERICOS / "02-puntoycoma-coma.csv")
    assert t.clase is ClaseDeTiempo.RELATIVO
    assert t.paso_mediano_s == pytest.approx(0.05)


def test_epoch_en_segundos() -> None:
    t = de(GENERICOS / "07-epoch-segundos.csv")
    assert t.clase is ClaseDeTiempo.EPOCH_SEGUNDOS
    assert t.factor_a_segundos == 1.0
    assert t.clase.es_absoluta
    assert t.fiabilidad is FiabilidadReloj.FIABLE
    assert t.t0_absoluto == datetime(2026, 7, 25, 17, 20, tzinfo=UTC)
    assert t.paso_mediano_s == pytest.approx(0.05)


def test_epoch_en_milisegundos() -> None:
    """La regla 1: `1785000000000` y `1785000000.000` son los dos enteros válidos.

    Lo único que los separa es la magnitud. Confundirlos dibujaría este log de
    unos segundos como uno de semanas.
    """
    t = de(GENERICOS / "08-epoch-milisegundos.csv")
    assert t.clase is ClaseDeTiempo.EPOCH_MILISEGUNDOS
    assert t.factor_a_segundos == 0.001
    assert t.paso_mediano_s == pytest.approx(0.05), "el paso ya viene en segundos"
    assert t.frecuencia_hz == pytest.approx(20.0)


def test_los_dos_epoch_dan_el_mismo_instante() -> None:
    """La comprobación cruzada que hace la regla 1 verificable.

    Los ficheros 07 y 08 del corpus son el mismo instante inicial escrito en dos
    escalas. Si la magnitud se interpretara mal, uno de los dos saldría a miles de
    años del otro.
    """
    en_s = de(GENERICOS / "07-epoch-segundos.csv")
    en_ms = de(GENERICOS / "08-epoch-milisegundos.csv")
    assert en_s.t0_absoluto is not None and en_ms.t0_absoluto is not None
    diferencia = abs((en_s.t0_absoluto - en_ms.t0_absoluto).total_seconds())
    assert diferencia < 1.0, f"difieren {diferencia} s: la magnitud se ha leído mal"


def test_iso8601() -> None:
    t = de(GENERICOS / "09-iso8601.csv")
    assert t.clase is ClaseDeTiempo.ISO8601
    assert t.clase.tiene_fecha
    assert t.fiabilidad is FiabilidadReloj.FIABLE
    assert t.t0_absoluto == datetime(2026, 7, 29, 18, 30, tzinfo=UTC)


def test_iso8601_se_clasifica_con_todas_las_filas_no_con_la_primera() -> None:
    """`09-iso8601.csv` tiene la primera fila SIN fracción (`…T18:30:00Z`) y la
    segunda CON (`…:00.050000Z`).

    Clasificar por el primer valor funciona por casualidad hasta que un exportador
    omite la fracción cuando es cero, que es lo normal.
    """
    lineas = (GENERICOS / "09-iso8601.csv").read_text(encoding="utf-8").splitlines()
    assert lineas[1].startswith("2026-07-29T18:30:00Z"), "sin fracción"
    assert ".050000Z" in lineas[2], "con fracción de seis cifras"
    t = de(GENERICOS / "09-iso8601.csv")
    assert t.clase is ClaseDeTiempo.ISO8601


def test_hora_del_dia_sin_fecha_no_situa_el_log() -> None:
    """Como el formato nativo (§1.4): la hora sin fecha no es tiempo absoluto."""
    datos = b"Time,RPM\n18:30:35.506,1456\n18:30:35.556,4107\n18:30:35.606,5873\n"
    t = analizar(datos)
    assert t.clase is ClaseDeTiempo.HORA_DEL_DIA
    assert t.t0_absoluto is None
    assert t.fiabilidad is FiabilidadReloj.DESCONOCIDA
    assert "hora_sin_fecha" in codigos(t)
    assert t.paso_mediano_s == pytest.approx(0.05)


def test_hora_del_dia_con_fecha_de_metadatos_si_lo_situa() -> None:
    """Igual que el metadato `Log` del formato nativo pone la fecha (§1.4)."""
    datos = b"Time,RPM\n18:30:35.506,1456\n18:30:35.556,4107\n18:30:35.606,5873\n"
    t = analizar(datos, fecha_de_metadatos=date(2026, 7, 29))
    assert t.fiabilidad is FiabilidadReloj.FIABLE
    assert t.t0_absoluto is not None
    assert t.t0_absoluto.date() == date(2026, 7, 29)
    assert t.t0_absoluto.hour == 18 and t.t0_absoluto.minute == 30


def test_fecha_y_hora_en_dos_columnas() -> None:
    """Caso 7 de §7.5: `date` + `time` se combinan."""
    datos = (
        b"Fecha,Hora,RPM\n"
        b"2026-07-29,18:30:35.506,1456\n"
        b"2026-07-29,18:30:35.556,4107\n"
        b"2026-07-29,18:30:35.606,5873\n"
    )
    t = analizar(datos)
    assert t.clase is ClaseDeTiempo.FECHA_Y_HORA_SEPARADAS
    assert t.indice == 1, "la columna de hora"
    assert t.indice_fecha == 0
    assert t.clase.tiene_fecha


def test_contador_de_muestras_sin_frecuencia_no_es_tiempo() -> None:
    """La regla 3, y es la más importante de esta tarea.

    `0, 1, 2, …` es indistinguible de un eje relativo en segundos a 1 Hz. Tratarlo
    como segundos inventaría la escala del eje X completo, y el log se vería con
    una duración inventada sin que nada fallara.
    """
    datos = b"Muestra,RPM\n0,1456\n1,4107\n2,5873\n3,6000\n4,6100\n"
    t = analizar(datos)
    assert t.clase is ClaseDeTiempo.CONTADOR_DE_MUESTRAS
    assert t.clase.necesita_frecuencia_del_usuario
    assert t.frecuencia_hz is None, "no se supone ninguna"
    assert t.paso_mediano_s is None
    assert "contador_sin_frecuencia" in codigos(t)
    assert "inventaría la escala" in next(
        a.mensaje for a in t.avisos if a.codigo == "contador_sin_frecuencia"
    )


def test_contador_de_muestras_con_frecuencia_declarada() -> None:
    datos = b"Muestra,RPM\n0,1456\n1,4107\n2,5873\n3,6000\n4,6100\n"
    t = analizar(datos, frecuencia_declarada_hz=20.0)
    assert t.clase is ClaseDeTiempo.CONTADOR_DE_MUESTRAS
    assert t.factor_a_segundos == pytest.approx(0.05)
    assert t.frecuencia_hz == pytest.approx(20.0)
    assert t.fiabilidad is FiabilidadReloj.DESCONOCIDA, "sigue sin haber reloj"
    assert t.exige_desfase_manual
    assert "eje_sintetico_desde_contador" in codigos(t)


def test_sin_columna_de_tiempo_sin_frecuencia() -> None:
    """Caso 6 de §7.5, con el fichero del corpus que no tiene columna de tiempo."""
    t = de(GENERICOS / "06-sin-columna-de-tiempo.csv")
    assert t.clase is ClaseDeTiempo.AUSENTE
    assert t.indice is None
    assert t.eje_sintetico
    assert t.frecuencia_hz is None
    assert "sin_columna_de_tiempo" in codigos(t)


def test_sin_columna_de_tiempo_con_frecuencia_declarada() -> None:
    t = de(GENERICOS / "06-sin-columna-de-tiempo.csv", frecuencia_declarada_hz=20.0)
    assert t.clase is ClaseDeTiempo.AUSENTE
    assert t.factor_a_segundos == pytest.approx(0.05)
    assert t.eje_sintetico, "sigue siendo sintético aunque haya frecuencia"
    assert t.exige_desfase_manual
    assert "eje_sintetico" in codigos(t)


# --------------------------------------------------------------------------- #
# La regla 2: el paso decide la unidad
# --------------------------------------------------------------------------- #
def test_un_eje_relativo_en_milisegundos_se_reconoce_por_el_paso() -> None:
    """`0, 50, 100, 150` con paso 50: milisegundos, no segundos.

    Mirando un valor suelto no hay forma de saberlo. Mirando el paso, sí: ninguna
    ECU registra cada 50 segundos.
    """
    datos = b"Time,RPM\n0,1456\n50,4107\n100,5873\n150,6000\n200,6100\n"
    t = analizar(datos)
    assert t.clase is ClaseDeTiempo.RELATIVO
    assert t.factor_a_segundos == 0.001
    assert t.paso_mediano_s == pytest.approx(0.05)
    assert "unidad_del_eje_relativo_por_el_paso" in codigos(t)


def test_la_unidad_del_eje_relativo_siempre_se_avisa() -> None:
    """Es una heurística, no una medida: un log de una hora muestreado cada 2 s
    tiene paso 2 y también sería válido en segundos."""
    t = de(GENERICOS / "01-coma-punto.csv")
    assert "unidad_del_eje_relativo_por_el_paso" in codigos(t)
    assert "segundos" in next(
        a.mensaje for a in t.avisos if a.codigo == "unidad_del_eje_relativo_por_el_paso"
    )


def test_un_contador_no_se_confunde_con_un_relativo_de_paso_uno() -> None:
    """Un contador sube exactamente de uno en uno y es entero. Un relativo de paso
    1,0 s con algún hueco, no."""
    contador = b"n,RPM\n0,1456\n1,4107\n2,5873\n3,6000\n"
    relativo = b"t,RPM\n0.0,1456\n1.0,4107\n2.5,5873\n3.5,6000\n"
    assert analizar(contador).clase is ClaseDeTiempo.CONTADOR_DE_MUESTRAS
    assert analizar(relativo).clase is ClaseDeTiempo.RELATIVO


# --------------------------------------------------------------------------- #
# La regla 4: nunca se finge precisión temporal
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("clase", "sintetico"),
    [
        (ClaseDeTiempo.AUSENTE, True),
        (ClaseDeTiempo.CONTADOR_DE_MUESTRAS, True),
        (ClaseDeTiempo.RELATIVO, False),
        (ClaseDeTiempo.ISO8601, False),
        (ClaseDeTiempo.EPOCH_SEGUNDOS, False),
    ],
)
def test_que_clases_necesitan_que_el_usuario_declare_la_frecuencia(
    clase: ClaseDeTiempo, sintetico: bool
) -> None:
    assert clase.necesita_frecuencia_del_usuario is sintetico


def test_un_eje_no_fiable_exige_desfase_manual_en_la_concatenada() -> None:
    """§7.5: se marca igual que un log interno de ECU (§1.5)."""
    relativo = de(GENERICOS / "01-coma-punto.csv")
    absoluto = de(GENERICOS / "09-iso8601.csv")
    assert relativo.exige_desfase_manual, "sin reloj no se puede colocar solo"
    assert not absoluto.exige_desfase_manual, "con reloj fiable sí"


def test_la_fiabilidad_usa_el_vocabulario_del_motor_de_tiempo() -> None:
    """No un tipo nuevo: un CSV con eje sintético tiene el mismo problema que un
    log interno sin reloj de tiempo real, y `tiempo.py` ya sabe qué hacer con él.
    Un tipo propio obligaría a traducir, y en la traducción se pierde el matiz."""
    t = de(GENERICOS / "09-iso8601.csv")
    assert isinstance(t.fiabilidad, FiabilidadReloj)


# --------------------------------------------------------------------------- #
# Parseo de valores sueltos
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("valor", "clase", "esperado"),
    [
        ("18:30:35.506", ClaseDeTiempo.HORA_DEL_DIA, 66635.506),
        ("18:30:35", ClaseDeTiempo.HORA_DEL_DIA, 66635.0),
        ("1785000000.050", ClaseDeTiempo.EPOCH_SEGUNDOS, 1785000000.05),
        ("1785000000050", ClaseDeTiempo.EPOCH_MILISEGUNDOS, 1785000000050.0),
        ("0.050", ClaseDeTiempo.RELATIVO, 0.05),
    ],
)
def test_parsear_instante(valor: str, clase: ClaseDeTiempo, esperado: float) -> None:
    assert parsear_instante(valor, clase) == pytest.approx(esperado)


def test_iso_con_coma_decimal_y_fraccion_larga() -> None:
    """Los dos aparecen en exportadores reales, y `fromisoformat` no los acepta.

    Una coma decimal en la fracción de segundo es lo que produce un exportador
    europeo, y una fracción de más de seis cifras la produce cualquiera que emita
    nanosegundos.
    """
    base = parsear_instante("2026-07-29T18:30:35.506Z", ClaseDeTiempo.ISO8601)
    con_coma = parsear_instante("2026-07-29T18:30:35,506Z", ClaseDeTiempo.ISO8601)
    con_nanos = parsear_instante("2026-07-29T18:30:35.506123456Z", ClaseDeTiempo.ISO8601)
    assert con_coma == pytest.approx(base)
    assert con_nanos == pytest.approx(base, abs=1e-3)


def test_iso_sin_zona_se_trata_como_utc_y_no_se_inventa_una() -> None:
    sin_zona = parsear_instante("2026-07-29T18:30:35", ClaseDeTiempo.ISO8601)
    con_utc = parsear_instante("2026-07-29T18:30:35Z", ClaseDeTiempo.ISO8601)
    assert sin_zona == pytest.approx(con_utc)


@pytest.mark.parametrize(
    ("valor", "clase"),
    [
        ("no es una hora", ClaseDeTiempo.HORA_DEL_DIA),
        ("25:99:99", ClaseDeTiempo.HORA_DEL_DIA),
        ("2026-13-45T00:00:00Z", ClaseDeTiempo.ISO8601),
        ("texto", ClaseDeTiempo.RELATIVO),
    ],
)
def test_un_valor_que_no_encaja_con_su_clase_es_un_error(valor: str, clase: ClaseDeTiempo) -> None:
    with pytest.raises(ErrorDeTiempoCsv):
        parsear_instante(valor, clase)


# --------------------------------------------------------------------------- #
# Contratos
# --------------------------------------------------------------------------- #
def test_gana_la_primera_columna_que_es_tiempo() -> None:
    """En los ocho casos de §7.5 el tiempo es la primera columna, y una posterior
    que también lo parezca (un `lap_time`) no es el eje del log."""
    datos = b"Time,RPM,LapTime\n0.000,1456,12.345\n0.050,4107,12.395\n0.100,5873,12.445\n"
    t = analizar(datos)
    assert t.indice == 0 and t.nombre == "Time"


def test_una_frecuencia_declarada_no_positiva_es_un_error() -> None:
    with pytest.raises(ErrorDeTiempoCsv, match="positiva"):
        de(GENERICOS / "06-sin-columna-de-tiempo.csv", frecuencia_declarada_hz=0.0)


def test_el_generico_de_f0_13() -> None:
    """El gemelo europeo, que además tiene fila de unidades: la costura completa."""
    t = de(DOS_FORMATOS / "generico.csv")
    assert t.clase is ClaseDeTiempo.RELATIVO
    assert t.nombre == "Tiempo"
    assert t.paso_mediano_s == pytest.approx(0.05)


def test_el_resultado_es_reproducible() -> None:
    datos = (GENERICOS / "07-epoch-segundos.csv").read_bytes()
    assert analizar(datos) == analizar(datos)
