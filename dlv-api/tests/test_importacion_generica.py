"""El contrato del sondeo de CSV genérico, sin pasar por HTTP (tarea FG-18).

POR QUÉ ESTE FICHERO NO USA `TestClient`
=========================================
Lo que puede salir mal en FG-18 no es el enrutado, es la **traducción**: qué
nombre tiene cada campo, qué se deja fuera y qué se conserva de lo que
`dlv_core` calculó. Eso vive entero en `dlv_api.importacion`, que no importa
FastAPI, así que se puede probar donde FastAPI no esté instalado — y en el
contenedor de desarrollo no lo está. `test_sondeo_generico_http.py` prueba lo
otro (rutas, token, códigos de estado) y se salta con `importorskip`.

Repartirlo así no es una comodidad: si todo estuviera detrás de `importorskip`,
un entorno sin FastAPI daría «6 skipped» y eso es indistinguible de verde
(`docs/09` §9.10, «fiarse del informe de un agente»).

LO QUE ESTAS PRUEBAS PROTEGEN DE VERDAD
========================================
1. **Que la confianza del rol sobreviva al JSON.** `docs/07` §7.15 desactiva
   los detectores críticos cuando un rol viene de asignación difusa sin
   confirmar. Si la respuesta aplanara la `Asignacion` a una cadena, esa
   mitigación se perdería entera sin que nada fallara: el JSON se vería
   perfecto. Es lo que comprueba `test_un_rol_difuso_...`.
2. **Que los índices de fila signifiquen lo mismo en las dos orillas.** El
   asistente indexa `filasPrevia` con `filaCabecera`, `filaUnidades` y
   `filaDatos`. Si las dos listas no fueran la misma lista, la
   previsualización etiquetaría como «cabecera» una fila de datos y nadie
   vería un error.
3. **Que una deducción no se cuele como una declaración del usuario.**
   `frecuenciaHz` es «Hz declarados por el usuario» y tiene que salir `null`
   aunque FG-04 haya deducido 20 Hz del paso mediano.
4. **Que los nombres de los campos sean los que el consumidor ya espera.**
   `dlv-ui/src/importacion/puerto.ts` y `tipos.ts` están escritos y probados;
   este lado tiene que encajar en ellos, no al revés.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dlv_api.importacion import (
    _TIPO_A_JSON,  # tabla de traducción: se comprueba que cubre el enum entero
    BYTES_DE_MUESTRA,
    FILAS_INSPECCIONADAS,
    ErrorDeEntrada,
    FicheroDemasiadoGrande,
    FicheroNoEncontrado,
    Muestra,
    catalogo_roles_json,
    formato_confirmado,
    leer_muestra,
    sondear_canales,
    sondear_formato,
    sondear_tiempo,
    tiempo_confirmado,
)
from dlv_core.formatos.tipos import TipoColumna
from dlv_core.formatos.unidades_declaradas import cargar_alias
from dlv_core.roles import Rol, cargar_catalogo_roles
from dlv_core.unidades import Catalogo, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
DOS_FORMATOS = RAIZ / "samples" / "dos-formatos"
DATA = RAIZ / "data"

# Los campos que `dlv-ui/src/importacion/tipos.ts` declara para cada estructura.
# Se escriben aquí a mano y no se derivan de nada a propósito: son la copia del
# contrato del otro lado de la frontera, y el único momento en que se pueden
# comparar las dos es en una prueba.
CAMPOS_PROPUESTA_FORMATO = frozenset(
    {
        "codificacion",
        "delimitador",
        "comilla",
        "decimal",
        "filaCabecera",
        "filaUnidades",
        "filaDatos",
    }
)
CAMPOS_PROPUESTA_TIEMPO = frozenset(
    {"clase", "columna", "columnaFecha", "frecuenciaHz", "factorASegundos"}
)
CAMPOS_CANAL = frozenset(
    {"columna", "nombreOriginal", "tipoInferido", "dimensionId", "unidadOrigen", "rol", "avisos"}
)
CAMPOS_ROL_PROPUESTO = frozenset(
    {"rol", "confianza", "sinonimo", "indice", "parecido", "confirmado"}
)
CAMPOS_ROL_DE_CATALOGO = frozenset({"id", "dimensionId", "plausibleMin", "plausibleMax", "critico"})


# --------------------------------------------------------------------------- #
# Catálogos: los mismos ficheros de `data/` que carga `dlv_api.main`
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with (DATA / "units.toml").open("rb") as fh:
        return cargar_catalogo(fh)


@pytest.fixture(scope="module")
def alias() -> dict[str, tuple[str, str]]:
    with (DATA / "alias_unidades.toml").open("rb") as fh:
        return dict(cargar_alias(fh))


@pytest.fixture(scope="module")
def roles() -> dict[str, Rol]:
    with (DATA / "roles.toml").open("rb") as fh:
        return cargar_catalogo_roles(fh)


def _cadena(
    ruta: Path,
    *,
    catalogo: Catalogo,
    alias: dict[str, tuple[str, str]],
    roles: dict[str, Rol],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Los tres pasos del asistente sobre un fichero, encadenados como él.

    Cada paso recibe lo que el anterior devolvió, sin retocarlo: es exactamente
    lo que hace `asistente-importacion.ts#avanzar` cuando el usuario no corrige
    nada. Si la salida de un paso no sirve como entrada del siguiente, esto
    falla, que es la mitad del valor de tenerlo escrito así.
    """
    muestra = leer_muestra(ruta)
    paso1 = sondear_formato(muestra)
    p = paso1["propuesta"]
    formato = formato_confirmado(
        codificacion=p["codificacion"]["valor"],
        delimitador=p["delimitador"]["valor"],
        comilla=p["comilla"]["valor"],
        decimal=p["decimal"]["valor"],
        fila_cabecera=p["filaCabecera"]["valor"],
        fila_unidades=p["filaUnidades"]["valor"],
        fila_datos=p["filaDatos"]["valor"],
    )
    paso2 = sondear_tiempo(muestra, formato)
    t = paso2["propuesta"]
    paso3 = sondear_canales(
        muestra,
        formato,
        tiempo_confirmado(
            clase=t["clase"]["valor"],
            columna=t["columna"]["valor"],
            columna_fecha=t["columnaFecha"]["valor"],
            frecuencia_hz=t["frecuenciaHz"]["valor"],
        ),
        catalogo=catalogo,
        alias=alias,
        catalogo_roles=roles,
    )
    return paso1, paso2, paso3


# --------------------------------------------------------------------------- #
# Paso 1 — formato (FG-01, FG-02, FG-03)
# --------------------------------------------------------------------------- #
def test_el_csv_espanol_sale_con_punto_y_coma_y_coma_decimal() -> None:
    """`02-puntoycoma-coma.csv` es el caso que §7.4 llama «el más importante en
    Europa»: leerlo con la configuración anglosajona parte `12,5` en dos
    columnas. Que llegue bien al JSON es la prueba de que FG-02 está cableada,
    no solo FG-01."""
    paso1 = sondear_formato(leer_muestra(GENERICOS / "02-puntoycoma-coma.csv"))
    p = paso1["propuesta"]
    assert p["delimitador"]["valor"] == ";"
    assert p["decimal"]["valor"] == ","
    assert p["filaCabecera"]["valor"] == 0
    assert p["filaDatos"]["valor"] == 1


def test_la_fila_de_unidades_se_distingue_de_la_de_nombres() -> None:
    """`04-fila-de-unidades.csv` trae `s,rpm,kPa,%,C,ratio` entre los nombres y
    los datos. Es la decisión de FG-03 que más veces se hace mal (su propio
    módulo cuenta que la primera versión tomaba la cabecera por fila de
    unidades), y sin ella FG-06 no tiene de dónde sacar la unidad."""
    p = sondear_formato(leer_muestra(GENERICOS / "04-fila-de-unidades.csv"))["propuesta"]
    assert (p["filaCabecera"]["valor"], p["filaUnidades"]["valor"], p["filaDatos"]["valor"]) == (
        0,
        1,
        2,
    )


def test_el_preambulo_largo_no_se_confunde_con_la_cabecera() -> None:
    """`14-preambulo-largo.csv` tiene doce líneas `clave: valor` delante. Los
    metadatos viajan además de la estructura: son lo que hace falta para situar
    en el calendario un log con hora del día (§7.5), y volver a leer el fichero
    para sacarlos sería absurdo."""
    paso1 = sondear_formato(leer_muestra(GENERICOS / "14-preambulo-largo.csv"))
    p = paso1["propuesta"]
    assert p["filaCabecera"]["valor"] == 12
    assert p["filaDatos"]["valor"] == 13
    assert paso1["metadatos"]["vehicle"] == "Track car - GT"
    assert paso1["metadatos"]["date"] == "2026-07-29"


def test_todo_campo_editable_llega_como_deducido_y_no_como_confirmado() -> None:
    """Ningún endpoint firma en nombre del usuario.

    `Campo.origen` es lo que hace que el asistente no pueda pintar un valor sin
    decir de quién es. Un sondeo que devolviera «confirmado» apagaría todos los
    avisos del paso 1 de golpe y la interfaz seguiría pareciendo correcta.
    """
    paso1 = sondear_formato(leer_muestra(GENERICOS / "01-coma-punto.csv"))
    assert set(paso1["propuesta"]) == CAMPOS_PROPUESTA_FORMATO
    for nombre, campo in paso1["propuesta"].items():
        assert campo["origen"] == "deducido", f"{nombre} llega como confirmado"


def test_los_indices_de_fila_indexan_la_previsualizacion_que_se_devuelve() -> None:
    """La invariante que el asistente da por buena, comprobada en los 17 ficheros.

    `#papelDeLinea` compara el índice de cada línea de `filasPrevia` con
    `filaCabecera`/`filaUnidades`/`filaDatos`, y `#filasDeDatos` hace
    `filasPrevia.slice(filaDatos)`. Si los índices contaran líneas de otra
    lista —por ejemplo incluyendo las vacías— la previsualización marcaría como
    cabecera una fila de datos y no habría ningún error que buscar.
    """
    for ruta in sorted(GENERICOS.glob("*.csv")):
        paso1 = sondear_formato(leer_muestra(ruta))
        p = paso1["propuesta"]
        previa = paso1["filasPrevia"]
        fila_datos = p["filaDatos"]["valor"]
        assert fila_datos < len(previa), f"{ruta.name}: la previa no llega a los datos"
        # Hay al menos una fila de datos que enseñar, y la cabecera es una línea
        # de la propia previa (no un índice al aire).
        assert len(previa) - fila_datos >= 1
        for indice in (p["filaCabecera"]["valor"], p["filaUnidades"]["valor"]):
            if indice is not None:
                assert 0 <= indice < fila_datos, f"{ruta.name}: papel de línea incoherente"
                assert previa[indice].strip(), f"{ruta.name}: la línea {indice} está vacía"


def test_la_previsualizacion_ensena_diez_filas_de_datos_y_no_el_fichero() -> None:
    """§7.8 paso 1 pide «las 10 primeras filas parseadas», no las 20 000 que
    tiene el fichero. Es también lo que mantiene la respuesta en el orden de
    magnitud que ADR-007 reserva para JSON."""
    ruta = GENERICOS / "01-coma-punto.csv"
    paso1 = sondear_formato(leer_muestra(ruta))
    fila_datos = paso1["propuesta"]["filaDatos"]["valor"]
    assert len(paso1["filasPrevia"]) - fila_datos == 10
    assert paso1["filasPreviaTruncada"] is True
    assert paso1["nLineasMuestra"] > len(paso1["filasPrevia"])


def test_los_candidatos_explican_por_que_ese_delimitador_y_no_otro() -> None:
    """`sondeo.py` es explícito: «proponer `;` sin poder enseñar que `,` dejaba
    el 40 % de las líneas descuadradas no es una propuesta, es una
    imposición». Si la respuesta no lleva las puntuaciones, el asistente no
    puede enseñarlas."""
    paso1 = sondear_formato(leer_muestra(GENERICOS / "02-puntoycoma-coma.csv"))
    candidatos = paso1["candidatos"]
    assert candidatos, "hacen falta las puntuaciones de FG-01"
    assert candidatos[0]["delimitador"] == ";"
    # Acotado por construcción (5 delimitadores x 3 comillas), no por un
    # recorte de la capa HTTP.
    assert len(candidatos) <= 15
    assert paso1["confianzaDelimitador"] > 0.9


def test_un_fichero_de_una_sola_columna_no_es_un_error() -> None:
    """§7.4: cuando ninguna combinación llega a la confianza mínima, el sondeo
    dice que no sabe. `PropuestaFormato.delimitador` es `Campo<string | null>`
    justamente para esto, y el asistente no deja avanzar hasta que el usuario
    elija uno. Devolver 422 aquí le quitaría la previsualización, que es lo
    único con lo que puede decidir."""
    paso1 = sondear_formato(_muestra_de(b"RPM\n1000\n2000\n3000\n4000\n"))
    assert paso1["propuesta"]["delimitador"]["valor"] is None
    assert paso1["filasPrevia"][0] == "RPM"
    assert any("delimitador_sin_determinar" in a for a in paso1["avisos"])


def test_una_tabla_de_texto_sin_datos_numericos_se_rechaza() -> None:
    """El caso «esto no es un CSV de un log»: delimitador consistente y ninguna
    fila mayoritariamente numérica. Se rechaza en vez de proponer una
    estructura inventada, y el mensaje de FG-03 llega íntegro porque dice qué
    se ha mirado."""
    agenda = b"nombre,apellido,ciudad\nJuan,Perez,Madrid\nAna,Lopez,Sevilla\nEva,Ruiz,Vigo\n"
    with pytest.raises(ErrorDeEntrada) as caso:
        sondear_formato(_muestra_de(agenda))
    assert "mayoritariamente" in str(caso.value)


def test_un_binario_se_lee_como_latin1_y_se_dice() -> None:
    """Un fichero que no es texto no revienta el sondeo: FG-01 se rinde a
    latin-1 y avisa de que es una rendición y no una detección. Que no lance es
    lo que importa: el usuario que suelta un `.png` por error tiene que ver un
    aviso, no un 500."""
    datos = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + bytes(range(256)) * 4
    paso1 = sondear_formato(_muestra_de(datos))
    assert paso1["propuesta"]["delimitador"]["valor"] is None
    assert any("codificacion_supuesta" in a for a in paso1["avisos"])


# --------------------------------------------------------------------------- #
# Paso 2 — columna de tiempo (FG-04)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("nombre", "clase", "factor", "fiabilidad"),
    [
        ("01-coma-punto.csv", "relativo", 1.0, "DESCONOCIDA"),
        ("07-epoch-segundos.csv", "epoch_segundos", 1.0, "FIABLE"),
        ("08-epoch-milisegundos.csv", "epoch_milisegundos", 0.001, "FIABLE"),
        ("09-iso8601.csv", "iso8601", 1.0, "FIABLE"),
        ("06-sin-columna-de-tiempo.csv", "ausente", 1.0, "DESCONOCIDA"),
    ],
)
def test_las_clases_de_tiempo_de_75_llegan_con_su_factor_y_su_fiabilidad(
    nombre: str, clase: str, factor: float, fiabilidad: str
) -> None:
    """Las variantes de §7.5 que el corpus de F0-12 cubre.

    `factorASegundos` es lo que distingue segundos de milisegundos y va sin
    envolver en `Campo` porque no lo edita el usuario: lo determina la clase.
    `fiabilidad` no la puede calcular el frontend —depende de si la columna
    sitúa el log en el calendario— y es lo que decide si la vista concatenada
    exige desfase manual (§7.5, y `docs/01` §1.5).
    """
    muestra = leer_muestra(GENERICOS / nombre)
    p = sondear_formato(muestra)["propuesta"]
    paso2 = sondear_tiempo(muestra, _formato_de(p))
    assert set(paso2["propuesta"]) == CAMPOS_PROPUESTA_TIEMPO
    assert paso2["propuesta"]["clase"]["valor"] == clase
    assert paso2["propuesta"]["factorASegundos"] == factor
    assert paso2["fiabilidad"] == fiabilidad


def test_la_frecuencia_declarada_por_el_usuario_no_se_rellena_con_la_deducida() -> None:
    """El error de §7.5 que da un número plausible y falso.

    FG-04 deduce ~20 Hz del paso mediano de `01-coma-punto.csv`, y esa cifra es
    útil para ENSEÑARLA. Pero `PropuestaTiempo.frecuenciaHz` son «Hz declarados
    por el usuario», y es lo que se usa para SINTETIZAR el eje cuando la
    columna es un contador de muestras o no hay columna. Rellenarla con la
    deducida inventaría la escala del eje X entero y el asistente lo pintaría
    como una declaración del usuario, con su badge de «confirmado» incluido.
    """
    muestra = leer_muestra(GENERICOS / "01-coma-punto.csv")
    paso2 = sondear_tiempo(muestra, _formato_de(sondear_formato(muestra)["propuesta"]))
    assert paso2["propuesta"]["frecuenciaHz"]["valor"] is None
    assert paso2["frecuenciaDeducidaHz"] == pytest.approx(20.0, abs=1e-6)
    assert paso2["propuesta"]["frecuenciaHz"]["origen"] == "deducido"


def test_sin_columna_de_tiempo_no_se_fabrica_ningun_valor() -> None:
    """`06-sin-columna-de-tiempo.csv`: `valoresBrutos` vacío y no una lista de
    ceros. §7.5 exige que el eje se sintetice con la frecuencia que declare el
    usuario y que el log quede marcado; un `["0", "1", "2"]` fabricado aquí
    sería indistinguible de un contador de muestras que sí estaba en el
    fichero."""
    muestra = leer_muestra(GENERICOS / "06-sin-columna-de-tiempo.csv")
    paso2 = sondear_tiempo(muestra, _formato_de(sondear_formato(muestra)["propuesta"]))
    assert paso2["propuesta"]["clase"]["valor"] == "ausente"
    assert paso2["propuesta"]["columna"]["valor"] is None
    assert paso2["valoresBrutos"] == []
    assert paso2["necesitaFrecuenciaDelUsuario"] is True


def test_los_valores_brutos_estan_acotados_y_no_son_una_serie() -> None:
    """ADR-007: las series nunca viajan en JSON.

    `valoresBrutos` son los valores de la columna de tiempo de la MUESTRA, para
    que el paso 2 recalcule duración y tasa en el cliente sin volver a
    preguntar. El tope es el de `dlv_core` (200 filas), no uno inventado aquí,
    y además está acotado por los 64 kB que se leen del fichero.
    """
    muestra = leer_muestra(RAIZ / "samples" / "dos-formatos" / "generico.csv")
    paso2 = sondear_tiempo(muestra, _formato_de(sondear_formato(muestra)["propuesta"]))
    assert 0 < len(paso2["valoresBrutos"]) <= FILAS_INSPECCIONADAS


def test_el_paso_2_obedece_una_correccion_del_usuario_en_el_paso_1() -> None:
    """§7.4: «la detección es una propuesta, no un hecho».

    Se le dice al paso 2 que los datos empiezan una línea más abajo de lo que
    propuso FG-03. Tiene que obedecer, y se comprueba mirando que el primer
    valor bruto es el de la SEGUNDA fila de datos del fichero. Si el paso 2
    volviera a llamar a `analizar_estructura`, la corrección se perdería en
    silencio y el asistente enseñaría un resumen de tiempo que no corresponde a
    lo que el usuario configuró.
    """
    ruta = GENERICOS / "01-coma-punto.csv"
    muestra = leer_muestra(ruta)
    p = sondear_formato(muestra)["propuesta"]
    normal = sondear_tiempo(muestra, _formato_de(p))
    corregido = sondear_tiempo(muestra, _formato_de(p, fila_datos=p["filaDatos"]["valor"] + 1))
    assert corregido["valoresBrutos"][0] == normal["valoresBrutos"][1]


def test_un_indice_de_fila_imposible_se_rechaza_y_no_revienta() -> None:
    """Los tres índices llegan de un cliente. Sin comprobarlos, `filaDatos`
    fuera de rango sería un `IndexError` y un 500 con traza."""
    muestra = leer_muestra(GENERICOS / "01-coma-punto.csv")
    p = sondear_formato(muestra)["propuesta"]
    with pytest.raises(ErrorDeEntrada) as caso:
        sondear_tiempo(muestra, _formato_de(p, fila_datos=10**9))
    assert "filaDatos" in str(caso.value)

    with pytest.raises(ErrorDeEntrada) as caso:
        # La cabecera no puede estar dentro de los datos: mezclaría los nombres
        # con las muestras sin decir nada.
        sondear_tiempo(muestra, _formato_de(p, fila_cabecera=5))
    assert "filaCabecera" in str(caso.value)


def test_sin_delimitador_confirmado_no_se_puede_avanzar() -> None:
    """El paso 1 puede devolver `delimitador: null`; los pasos 2 y 3 no pueden
    trabajar con eso, y lo dicen con el mismo criterio que `dlv-core`."""
    with pytest.raises(ErrorDeEntrada) as caso:
        formato_confirmado(
            codificacion="utf-8",
            delimitador=None,
            comilla=None,
            decimal=".",
            fila_cabecera=0,
            fila_unidades=None,
            fila_datos=1,
        )
    assert "delimitador" in str(caso.value)


def test_una_clase_de_tiempo_inventada_se_rechaza_con_la_lista_de_las_que_hay() -> None:
    with pytest.raises(ErrorDeEntrada) as caso:
        tiempo_confirmado(clase="cronometro", columna=0, columna_fecha=None, frecuencia_hz=None)
    assert "hora_del_dia" in str(caso.value)


def test_un_separador_decimal_inventado_se_rechaza() -> None:
    with pytest.raises(ErrorDeEntrada):
        formato_confirmado(
            codificacion="utf-8",
            delimitador=",",
            comilla=None,
            decimal="'",
            fila_cabecera=0,
            fila_unidades=None,
            fila_datos=1,
        )


# --------------------------------------------------------------------------- #
# Paso 3 — canales: tipo (FG-05), unidad declarada (FG-06) y rol (FG-09)
# --------------------------------------------------------------------------- #
def test_la_unidad_de_la_fila_de_unidades_llega_resuelta_a_su_dimension(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """`04-fila-de-unidades.csv` declara `rpm,kPa,%,C,ratio`. Resolverlas contra
    `units.toml` + `alias_unidades.toml` es lo que hace que el sistema de
    unidades intercambiables funcione igual que con el formato nativo (§7.6).
    `C` solo resuelve por el fichero de alias, así que si esta prueba pasa es
    que `alias_unidades.toml` está cableado y no solo `units.toml`."""
    _, _, paso3 = _cadena(
        GENERICOS / "04-fila-de-unidades.csv", catalogo=catalogo, alias=alias, roles=roles
    )
    por_nombre = {c["nombreOriginal"]: c for c in paso3["canales"]}
    assert por_nombre["CLT"]["dimensionId"]["valor"] == "temperature"
    assert por_nombre["CLT"]["unidadOrigen"]["valor"] == "C"
    assert por_nombre["MAP"]["dimensionId"]["valor"] == "pressure"
    assert por_nombre["Lambda"]["dimensionId"]["valor"] == "mixture_ratio"


def test_la_unidad_del_nombre_no_estorba_a_la_asignacion_de_rol(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """`05-unidad-en-el-nombre.csv` llama a las columnas `RPM [rpm]` y `CLT (°C)`.

    El rol se busca con el nombre LIMPIO que devuelve FG-06, no con el
    original: `RPM [rpm]` no coincide con ningún sinónimo de `roles.toml` y
    `RPM` sí. Buscarlo antes de quitar la unidad convertiría en difusas
    asignaciones que son exactas, y una difusa apaga detectores críticos
    (§7.15). El nombre original se conserva para mostrarlo.
    """
    _, _, paso3 = _cadena(
        GENERICOS / "05-unidad-en-el-nombre.csv", catalogo=catalogo, alias=alias, roles=roles
    )
    por_nombre = {c["nombreOriginal"]: c for c in paso3["canales"]}
    assert por_nombre["RPM [rpm]"]["nombreLimpio"] == "RPM"
    assert por_nombre["RPM [rpm]"]["rol"]["rol"] == "engine_speed"
    assert por_nombre["RPM [rpm]"]["rol"]["confianza"] == "EXACTA"
    assert por_nombre["CLT (°C)"]["rol"]["rol"] == "coolant_temp"
    assert por_nombre["CLT (°C)"]["dimensionId"]["valor"] == "temperature"


def test_una_columna_sin_dimension_resuelta_llega_como_unknown(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """§7.15 mitigación 3: los canales sin dimensión resuelta se muestran en
    crudo, sin unidad y sin selector. `CanalPropuesto.dimensionId` es
    `Campo<string>` sin nulo, y `"unknown"` es el identificador que ya usa el
    resto del proyecto para «el formato no sabe qué magnitud es esto». Un
    `null` aquí obligaría al frontend a distinguir dos ausencias distintas."""
    _, _, paso3 = _cadena(
        GENERICOS / "01-coma-punto.csv", catalogo=catalogo, alias=alias, roles=roles
    )
    assert all(c["dimensionId"]["valor"] == "unknown" for c in paso3["canales"])
    assert all(c["unidadOrigen"]["valor"] is None for c in paso3["canales"])


def test_los_tipos_de_columna_de_fg05_llegan_traducidos(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """`12-texto-y-booleanos.csv` trae un enum de texto y un booleano.

    `tipos.ts` escribe `"enum"` donde `dlv_core` escribe `"enum_texto"`, así que
    hace falta traducir; esta prueba es la que detecta que la tabla se quedó
    corta.
    """
    _, _, paso3 = _cadena(
        GENERICOS / "12-texto-y-booleanos.csv", catalogo=catalogo, alias=alias, roles=roles
    )
    por_nombre = {c["nombreOriginal"]: c["tipoInferido"] for c in paso3["canales"]}
    assert por_nombre["RPM"] == "entero"
    assert por_nombre["CLT"] == "decimal"
    assert por_nombre["Marcha"] == "enum"
    assert por_nombre["Limitador"] == "booleano"


def test_la_tabla_de_tipos_cubre_el_enum_entero() -> None:
    """Un `TipoColumna` nuevo sin entrada en la tabla daría `KeyError` en
    ejecución, con el fichero de un usuario delante. Aquí falla en la suite."""
    assert set(_TIPO_A_JSON) == set(TipoColumna)
    # Y los seis valores tienen que ser miembros de `TipoInferido` de `tipos.ts`.
    tipo_inferido_ts = {"entero", "decimal", "enum", "booleano", "constante", "vacio", "texto"}
    assert set(_TIPO_A_JSON.values()) <= tipo_inferido_ts


def test_la_columna_de_tiempo_confirmada_no_se_ofrece_como_canal(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """El eje se configura en el paso 2; volver a ofrecerlo en el paso 3 invita
    a asignarle un rol. Es lo que justifica que `puerto.ts#sondearCanales`
    reciba el tiempo confirmado como tercer argumento."""
    _, paso2, paso3 = _cadena(
        GENERICOS / "01-coma-punto.csv", catalogo=catalogo, alias=alias, roles=roles
    )
    columna_tiempo = paso2["propuesta"]["columna"]["valor"]
    assert columna_tiempo == 0
    assert columna_tiempo not in {c["columna"] for c in paso3["canales"]}
    assert paso3["columnasDeTiempo"] == [0]


def test_cada_canal_trae_exactamente_los_campos_que_el_asistente_pinta(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """`CanalPropuesto` tiene siete campos y el asistente pinta los siete
    (`#filaCanal`). Lo que va de más son recuentos para afinar el orden por
    «necesita atención»; lo que faltara dejaría una columna vacía."""
    _, _, paso3 = _cadena(
        GENERICOS / "04-fila-de-unidades.csv", catalogo=catalogo, alias=alias, roles=roles
    )
    for canal in paso3["canales"]:
        assert set(canal) >= CAMPOS_CANAL, f"faltan campos en {canal['nombreOriginal']}"
        assert isinstance(canal["avisos"], list)


# --------------------------------------------------------------------------- #
# La confianza del rol: el punto donde §7.15 se pierde si se hace mal
# --------------------------------------------------------------------------- #
CSV_ROLES_MIXTOS = (
    # Nombres elegidos para que el catálogo real de `data/roles.toml` produzca
    # las tres confianzas y una columna sin rol. No se tocan los ficheros de
    # `samples/`: el corpus de F0-12 no tiene ningún nombre que caiga en difusa,
    # porque está escrito con los sinónimos buenos.
    b"Time,Engine Speed,Coolant Temperatur,Knock Sensor 2 Knock Count,Cosa Rara Del Piloto\n"
    b"0.000,1000,350.5,3,7\n"
    b"0.050,1100,351.0,3,7\n"
    b"0.100,1200,351.5,4,7\n"
    b"0.150,1300,352.0,4,7\n"
)


def test_un_rol_difuso_llega_al_json_con_su_confianza_intacta(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """LA prueba de esta tarea.

    `docs/07` §7.15 mitigación 4: los detectores críticos se desactivan cuando
    un rol viene de asignación difusa no confirmada. Para poder implementar eso
    aguas abajo hace falta que el JSON diga CÓMO se decidió el rol, no solo
    cuál. Si esta respuesta se aplanara a `rol: "coolant_temp"`, la mitigación
    desaparecería entera y no fallaría nada: el JSON se vería perfecto y una
    alerta crítica se activaría sobre un parecido del 97 %.

    Se comprueban las tres confianzas a la vez porque el riesgo no es solo
    perder la difusa: marcar como difusa una `INDEXADA` —que el catálogo
    declara con su plantilla `{n}` explícita— apagaría detectores que sí deben
    funcionar, y eso enseña al usuario a desconfiar de los avisos igual de
    rápido.
    """
    muestra = _muestra_de(CSV_ROLES_MIXTOS)
    p = sondear_formato(muestra)["propuesta"]
    paso3 = sondear_canales(
        muestra,
        _formato_de(p),
        tiempo_confirmado(clase="relativo", columna=0, columna_fecha=None, frecuencia_hz=None),
        catalogo=catalogo,
        alias=alias,
        catalogo_roles=roles,
    )
    por_nombre = {c["nombreOriginal"]: c for c in paso3["canales"]}

    exacta = por_nombre["Engine Speed"]["rol"]
    assert exacta["confianza"] == "EXACTA"
    assert exacta["rol"] == "engine_speed"
    assert exacta["confirmado"] is True

    difusa = por_nombre["Coolant Temperatur"]["rol"]
    assert set(difusa) == CAMPOS_ROL_PROPUESTO
    assert difusa["rol"] == "coolant_temp"
    assert difusa["confianza"] == "DIFUSA"
    assert difusa["sinonimo"] == "Coolant Temperature", "hay que poder enseñar QUÉ lo disparó"
    assert 0.85 <= difusa["parecido"] < 1.0
    assert difusa["confirmado"] is False, (
        "una difusa sin confirmar es lo que desactiva los detectores críticos (§7.15)"
    )
    # Y el usuario tiene que enterarse sin abrir la consola.
    assert any("parecido" in a for a in por_nombre["Coolant Temperatur"]["avisos"])

    indexada = por_nombre["Knock Sensor 2 Knock Count"]["rol"]
    assert indexada["confianza"] == "INDEXADA"
    assert indexada["rol"] == "knock_count"
    assert indexada["indice"] == 2, "el índice del banco/sensor es parte del rol"
    assert indexada["confirmado"] is True

    # Un canal sin rol no es un error (§7.8: «se puede importar dejando canales
    # sin rol: siguen siendo graficables»), y `null` es lo que el frontend
    # espera para eso.
    assert por_nombre["Cosa Rara Del Piloto"]["rol"] is None


def test_confirmado_coincide_con_la_regla_de_deduccion_ts(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """`confirmado` es el único campo del rol que no viene de `dlv-core`.

    La regla está escrita dos veces —aquí y en
    `dlv-ui/src/importacion/deduccion.ts#propuestaInicialDeRol`— y eso es un
    riesgo real de divergencia. Esta prueba es lo que lo vigila: `confirmado`
    tiene que ser exactamente «la confianza no es DIFUSA», para todos los
    canales y sin excepciones.
    """
    muestra = _muestra_de(CSV_ROLES_MIXTOS)
    paso3 = sondear_canales(
        muestra,
        _formato_de(sondear_formato(muestra)["propuesta"]),
        tiempo_confirmado(clase="relativo", columna=0, columna_fecha=None, frecuencia_hz=None),
        catalogo=catalogo,
        alias=alias,
        catalogo_roles=roles,
    )
    for canal in paso3["canales"]:
        rol = canal["rol"]
        if rol is not None:
            assert rol["confirmado"] == (rol["confianza"] != "DIFUSA")


def test_ningun_rol_llega_como_cadena_pelada(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """Escrita al revés que la anterior, y a propósito: la forma de romper §7.15
    no es devolver una confianza equivocada, es devolver un `rol` que sea un
    `str`. Esa refactorización «simplificadora» es la que hay que impedir, y
    solo se detecta comprobando el tipo."""
    for ruta in sorted(GENERICOS.glob("*.csv")):
        muestra = leer_muestra(ruta)
        p = sondear_formato(muestra)["propuesta"]
        if p["delimitador"]["valor"] is None:
            continue
        formato = _formato_de(p)
        paso2 = sondear_tiempo(muestra, formato)
        paso3 = sondear_canales(
            muestra,
            formato,
            tiempo_confirmado(
                clase=paso2["propuesta"]["clase"]["valor"],
                columna=paso2["propuesta"]["columna"]["valor"],
                columna_fecha=paso2["propuesta"]["columnaFecha"]["valor"],
                frecuencia_hz=None,
            ),
            catalogo=catalogo,
            alias=alias,
            catalogo_roles=roles,
        )
        for canal in paso3["canales"]:
            rol = canal["rol"]
            assert rol is None or isinstance(rol, dict), f"{ruta.name}/{canal['nombreOriginal']}"
            if rol is not None:
                assert rol["confianza"] in {"EXACTA", "INDEXADA", "DIFUSA"}


def test_una_dimension_que_contradice_al_rol_se_avisa(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """La comprobación de FG-10 que no necesita ni una muestra: el fichero
    declara una dimensión y el rol espera otra.

    Es el caso de `plausibilidad.Diagnostico.DIMENSION_DISTINTA_DEL_ROL`, «el
    diagnóstico más concluyente de todos»: si el canal mide presión y el rol
    espera una proporción, comparar sus valores con el rango del rol no
    significa nada. Aquí se declara `Lambda` en kPa, que es absurdo y plausible
    a la vez -- es exactamente el error de copiar una fila de unidades de otro
    exportador.
    """
    csv = b"Time,Lambda\ns,kPa\n0.000,0.98\n0.050,0.99\n0.100,1.00\n0.150,1.01\n"
    muestra = _muestra_de(csv)
    p = sondear_formato(muestra)["propuesta"]
    assert p["filaUnidades"]["valor"] == 1
    paso3 = sondear_canales(
        muestra,
        _formato_de(p),
        tiempo_confirmado(clase="relativo", columna=0, columna_fecha=None, frecuencia_hz=None),
        catalogo=catalogo,
        alias=alias,
        catalogo_roles=roles,
    )
    canal = paso3["canales"][0]
    assert canal["dimensionId"]["valor"] == "pressure"
    assert canal["rol"]["rol"] == "lambda_measured"
    assert any("espera" in a for a in canal["avisos"]), canal["avisos"]


# --------------------------------------------------------------------------- #
# Todo el corpus de F0-12 y el log de dos formatos de F0-13
# --------------------------------------------------------------------------- #
def test_los_diecisiete_ficheros_del_corpus_pasan_la_cadena_entera(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """Ninguno de los 17 casos de F0-12 puede reventar los tres pasos.

    Es la comprobación de conjunto: varios de los defectos que aparecieron al
    construir FG-03 y FG-04 solo se ven cuando la salida de un eslabón entra en
    el siguiente, y aquí los eslabones son además la frontera HTTP.
    """
    ficheros = sorted(GENERICOS.glob("*.csv"))
    assert len(ficheros) == 17, "el corpus de F0-12 son 17 ficheros"
    sin_delimitador = 0
    for ruta in ficheros:
        muestra = leer_muestra(ruta)
        paso1 = sondear_formato(muestra)
        if paso1["propuesta"]["delimitador"]["valor"] is None:
            sin_delimitador += 1
            continue
        _, _, paso3 = _cadena(ruta, catalogo=catalogo, alias=alias, roles=roles)
        assert paso3["canales"], f"{ruta.name}: ningún canal"
    assert sin_delimitador == 0, "los 17 del corpus tienen delimitador reconocible"


def test_el_log_de_dos_formatos_da_los_mismos_roles_por_el_camino_generico(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """El fichero genérico de F0-13, con nombres en español (`Régimen`,
    `Presión colector`) y coma decimal.

    Es la prueba de que la indirección de roles cumple lo que promete §7.2: los
    perfiles y detectores no piden «el canal 696», piden un rol, y aquí los
    nombres no se parecen en nada a los del Haltech y los roles salen iguales.
    """
    _, paso2, paso3 = _cadena(
        DOS_FORMATOS / "generico.csv", catalogo=catalogo, alias=alias, roles=roles
    )
    assert paso2["propuesta"]["clase"]["valor"] == "relativo"
    por_rol = {c["rol"]["rol"]: c for c in paso3["canales"] if c["rol"] is not None}
    assert {"engine_speed", "manifold_pressure", "coolant_temp", "lambda_measured"} <= set(por_rol)
    # `Régimen` empareja por sinónimo con acento: la normalización de §7.7
    # (minúsculas, sin acentos, sin separadores) tiene que llegar hasta aquí.
    assert por_rol["engine_speed"]["nombreOriginal"] == "Régimen"
    assert por_rol["engine_speed"]["rol"]["confianza"] == "EXACTA"
    # Y la fila de unidades en español resuelve la dimensión.
    assert por_rol["coolant_temp"]["dimensionId"]["valor"] == "temperature"


def test_el_haltech_por_el_camino_generico_no_inventa_nombres(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """El `nativo.csv` de F0-13 leído por el camino de nivel 2.

    §7.15 quiere el camino genérico como red de seguridad para cuando un
    descriptor no reconoce una variante, así que tiene que no romperse. Y lo
    que hace FG-03 con él es lo correcto y conviene fijarlo: la última línea
    antes de los datos es `Log : 20260729 06:30:35`, un metadato, así que el
    fichero se queda SIN fila de nombres y las columnas se identifican por
    posición (`col_1…col_n`) en vez de meter 476 columnas bajo un solo
    «nombre». Sin nombres no hay roles, y eso es honesto: el camino bueno para
    este fichero es el descriptor nativo.
    """
    muestra = leer_muestra(DOS_FORMATOS / "nativo.csv")
    paso1 = sondear_formato(muestra)
    assert paso1["propuesta"]["filaCabecera"]["valor"] is None
    assert paso1["metadatos"], "el preámbulo del formato nativo son metadatos clave: valor"
    _, _, paso3 = _cadena(DOS_FORMATOS / "nativo.csv", catalogo=catalogo, alias=alias, roles=roles)
    nombres = [c["nombreOriginal"] for c in paso3["canales"]]
    assert all(n.startswith("col_") for n in nombres), nombres[:5]
    assert all(c["rol"] is None for c in paso3["canales"])


def test_las_tres_respuestas_son_json_de_verdad(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]], roles: dict[str, Rol]
) -> None:
    """Nada que no sea JSON puro se cuela en una respuesta.

    Es la comprobación que atrapa lo que se convierte solo y calla: un `Enum`
    sin `.value`, un `datetime` sin `isoformat`, un `Mapping` que no es un
    `dict`. `jsonable_encoder` de FastAPI arregla varios de esos casos por su
    cuenta, y ahí está el problema: los arreglaría de una forma que nadie eligió
    —un `Enum` sale como su valor, un `datetime` como una cadena ISO— y el
    contrato con TypeScript quedaría fijado por una conversión implícita en vez
    de por una decisión. `json.dumps` sin `default=` no perdona ninguno.

    Se comprueba sobre `09-iso8601.csv` porque es el que produce un
    `t0_absoluto` real, que es el único `datetime` de toda la cadena.
    """
    paso1, paso2, paso3 = _cadena(
        GENERICOS / "09-iso8601.csv", catalogo=catalogo, alias=alias, roles=roles
    )
    assert paso2["t0Absoluto"] is not None, "hace falta el caso con instante absoluto"
    for respuesta in (paso1, paso2, paso3, {"roles": catalogo_roles_json(roles)}):
        json.dumps(respuesta, allow_nan=False)


# --------------------------------------------------------------------------- #
# Lectura del fichero: los límites de una entrada no confiable
# --------------------------------------------------------------------------- #
def test_no_se_lee_mas_que_la_muestra_por_grande_que_sea_el_fichero(tmp_path: Path) -> None:
    """El techo que hace que estos endpoints no sean una denegación de servicio.

    Un fichero de 5 MB (y por el mismo mecanismo uno de 2 GB) se sondea leyendo
    64 kB. El número es `dlv_core.formatos.sondeo.BYTES_DE_SONDEO`, o sea el
    «sobre los primeros 64 kB» de `docs/07` §7.4, no una cifra de esta capa.
    """
    ruta = tmp_path / "largo.csv"
    with ruta.open("wb") as fh:
        fh.write(b"Time,RPM,MAP\n")
        for i in range(200_000):
            fh.write(f"{i * 0.05:.3f},{1000 + i % 5000},{50.5 + i % 100}\n".encode())
    assert ruta.stat().st_size > 20 * BYTES_DE_MUESTRA

    muestra = leer_muestra(ruta)
    assert len(muestra.datos) <= BYTES_DE_MUESTRA
    assert muestra.truncada is True
    assert muestra.tamano_fichero == ruta.stat().st_size
    # Y la muestra acaba en un fin de línea, así que ninguna media fila entra en
    # la previsualización ni descuadra el recuento de campos.
    assert muestra.datos.endswith(b"\n")

    paso1 = sondear_formato(muestra)
    assert paso1["muestraTruncada"] is True
    assert paso1["propuesta"]["delimitador"]["valor"] == ","
    # La respuesta no puede llevar más texto del que se leyó.
    assert sum(len(linea) for linea in paso1["filasPrevia"]) <= BYTES_DE_MUESTRA


def test_un_fichero_demasiado_grande_se_rechaza_antes_de_leerlo(tmp_path: Path) -> None:
    """La otra guarda, y no es la del DoS: es la del usuario que elige por error
    un fichero que no es un log.

    El tope es un parámetro —no un umbral de física, no va a
    `data/umbrales.toml`— justamente para poder comprobarlo sin escribir medio
    gigabyte en el disco.
    """
    ruta = tmp_path / "enorme.csv"
    ruta.write_bytes(b"Time,RPM\n0.0,1000\n0.1,2000\n")
    with pytest.raises(FicheroDemasiadoGrande) as caso:
        leer_muestra(ruta, max_bytes_fichero=16)
    assert "16" in str(caso.value)
    # El mensaje tiene que explicar que el límite no es del sondeo, o el
    # siguiente que lo lea creerá que sondear un log grande es caro.
    assert "3,5x" in str(caso.value) or "3,5" in str(caso.value)


def test_un_fichero_que_no_existe_y_uno_vacio_se_distinguen(tmp_path: Path) -> None:
    """Dos ausencias distintas: 404 y 422. Confundirlas haría que el asistente
    dijera «no existe» de un fichero que el usuario está viendo en su carpeta."""
    with pytest.raises(FicheroNoEncontrado):
        leer_muestra(tmp_path / "no-existe.csv")

    vacio = tmp_path / "vacio.csv"
    vacio.write_bytes(b"")
    with pytest.raises(ErrorDeEntrada) as caso:
        leer_muestra(vacio)
    assert not isinstance(caso.value, FicheroNoEncontrado)
    assert "vacío" in str(caso.value)


def test_una_carpeta_no_es_un_fichero(tmp_path: Path) -> None:
    with pytest.raises(FicheroNoEncontrado):
        leer_muestra(tmp_path)


# --------------------------------------------------------------------------- #
# `data/roles.toml` servido, no duplicado
# --------------------------------------------------------------------------- #
def test_el_catalogo_de_roles_sale_del_toml_del_propietario(roles: dict[str, Rol]) -> None:
    """La regla 2 de `CLAUDE.md`: `data/*.toml` son datos, no código.

    Se comprueba con `coolant_temp`, cuyo rango plausible está en KELVIN en el
    fichero (`233.15` a `423.15`, o sea -40 a 150 °C). Si el servicio
    convirtiera a la unidad mostrada, el asistente marcaría como sospechosa
    media columna: los rangos son la mitad de un contrato con
    `previsualizacion.ts` y viajan en canónica, como los declara el fichero.
    """
    servido = catalogo_roles_json(roles)
    por_id = {r["id"]: r for r in servido}
    assert len(servido) == len(roles)
    assert set(servido[0]) >= CAMPOS_ROL_DE_CATALOGO

    clt = por_id["coolant_temp"]
    assert clt["dimensionId"] == "temperature"
    assert clt["plausibleMin"] == roles["coolant_temp"].plausible_min
    assert clt["plausibleMax"] == roles["coolant_temp"].plausible_max
    # No se fijan las CIFRAS aquí: son dato del propietario con puerta G1
    # (`data/roles.toml`), y copiarlas crearía la segunda copia que esta prueba
    # existe para evitar. Lo que se fija es que están en kelvin, que es lo que
    # el contrato con el frontend necesita.
    assert clt["plausibleMin"] > 200.0, "el rango tiene que venir en canónica (K), no en °C"


def test_los_roles_criticos_llegan_marcados(roles: dict[str, Rol]) -> None:
    """`critico` es lo que permite a `deduccion.ts` saber QUÉ detector apagar
    cuando un rol viene de una difusa sin confirmar. Sin este campo, la
    mitigación 4 de §7.15 no sabría a qué aplicarse."""
    servido = {r["id"]: r for r in catalogo_roles_json(roles)}
    criticos = [i for i, r in servido.items() if r["critico"]]
    assert criticos, "data/roles.toml declara roles críticos"
    assert servido["engine_speed"]["critico"] is True


def test_los_sinonimos_y_la_marca_de_indice_llegan_enteros(roles: dict[str, Rol]) -> None:
    """El desplegable de «asignar rol a mano» necesita los sinónimos para ser
    buscable, y `monotono` es lo que hace que el canal delta de knock se cree
    solo en cualquier formato (§7.7 punto 3)."""
    servido = {r["id"]: r for r in catalogo_roles_json(roles)}
    knock = servido["knock_count"]
    assert knock["indexado"] is True
    assert knock["monotono"] == "no_decreciente"
    assert any("{n}" in s for s in knock["sinonimos"]), "la plantilla indexada es parte del dato"


def test_el_catalogo_de_roles_no_sirve_la_seccion_meta(roles: dict[str, Rol]) -> None:
    """`[meta]` es para quien revisa el fichero, no para la interfaz (mismo
    criterio que `evidencia` en los combustibles). `cargar_catalogo_roles` ya la
    ignora; esto lo fija por si alguien la «recupera» pensando que falta."""
    assert "meta" not in {r["id"] for r in catalogo_roles_json(roles)}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _muestra_de(datos: bytes) -> Muestra:
    """Una `Muestra` a partir de bytes, sin pasar por el disco.

    Es lo que permite escribir un caso de una línea sin dejar un fichero
    temporal por medio; `leer_muestra` tiene sus propias pruebas más arriba.
    """
    return Muestra(datos=datos, tamano_fichero=len(datos), truncada=False)


def _formato_de(propuesta: dict[str, Any], **cambios: Any) -> Any:
    """El `FormatoConfirmado` que sale de una propuesta del paso 1.

    `cambios` simula una corrección del usuario en el asistente, que es la
    mitad de lo que hay que probar: los pasos 2 y 3 tienen que obedecerla.
    """
    argumentos: dict[str, Any] = {
        "codificacion": propuesta["codificacion"]["valor"],
        "delimitador": propuesta["delimitador"]["valor"],
        "comilla": propuesta["comilla"]["valor"],
        "decimal": propuesta["decimal"]["valor"],
        "fila_cabecera": propuesta["filaCabecera"]["valor"],
        "fila_unidades": propuesta["filaUnidades"]["valor"],
        "fila_datos": propuesta["filaDatos"]["valor"],
    }
    argumentos.update(cambios)
    return formato_confirmado(**argumentos)
