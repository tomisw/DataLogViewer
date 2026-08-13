"""Sondeo de CSV genérico servido por HTTP: la parte que no necesita FastAPI
(tarea FG-18).

QUÉ HACE ESTE MÓDULO Y POR QUÉ ESTÁ SEPARADO DE `main.py`
=========================================================
FG-01 a FG-09 dejaron la cadena entera del importador genérico escrita y
probada en `dlv_core`, y `dlv-api` no la servía por ninguna ruta: sus ocho
comandos eran todos del formato nativo de Haltech. `dlv-ui` llegó a tener el
asistente de importación de §7.8 terminado y sin poder funcionar
(`dlv-ui/src/importacion/puerto.ts`, cuyos cuatro métodos lanzan un error que
nombra el endpoint que falta). Esta tarea cablea exactamente esos cuatro.

Aquí vive **la traducción**, no la lógica: cada función toma bytes ya leídos y
devuelve un `dict` listo para serializar a JSON con la forma que
`puerto.ts`/`tipos.ts` declaran. Ni una sola decisión sobre el fichero se toma
en este módulo: el delimitador lo elige `dlv_core.formatos.sondeo`, el decimal
`decimal_csv`, la estructura `estructura`, la columna de tiempo `tiempo_csv`,
los tipos `tipos`, la unidad `unidades_declaradas` y el rol `dlv_core.roles`.
Lo único que se añade es el nombre de los campos JSON y qué se deja fuera.

Está separado de `main.py` por un motivo práctico: `main.py` importa `fastapi`
y `pydantic`, y así la traducción entera —que es donde de verdad se puede
equivocar uno— se puede probar sin ninguna de las dos. Es lo que permite que
`dlv-api/tests/test_importacion_generica.py` se ejecute en un entorno sin
FastAPI instalado, donde las pruebas de HTTP se saltan con `importorskip`.

LA FRONTERA DE ADR-002 NO SE MUEVE
===================================
`dlv-core` no abre ficheros. Quien lee del disco es `leer_muestra`, aquí, en
`dlv-api`, igual que ya lo hacían `main.abrir_cabecera` y
`arrastrar_soltar._clasificar_fichero`; a `dlv_core` le llegan bytes.

ADR-007 TAMPOCO: AQUÍ NO VIAJA NINGUNA SERIE
=============================================
Todo lo que devuelven estas funciones son metadatos y **unas pocas filas de
texto en crudo** para la previsualización de §7.8: el eje de tiempo y los
valores de los canales no salen por aquí, salen por `/comandos/cubos` en
binario cuando el log ya está importado. El tamaño de las respuestas está
acotado por la muestra de `BYTES_DE_MUESTRA` (64 kB), que es un techo duro:
ninguna respuesta puede contener más texto del que se leyó del fichero. Ver
`FILAS_DE_DATOS_EN_PREVIA` y `FILAS_INSPECCIONADAS`.

UNA DEDUCCIÓN Y UNA CONFIRMACIÓN NO SON EL MISMO DATO
======================================================
Es la regla de fondo del asistente (`tipos.ts` la explica entera) y decide la
forma de estas respuestas en dos sitios distintos:

1. **Cada campo editable viaja envuelto en `{valor, origen}`** (`Campo<T>` de
   `tipos.ts`). Lo que sale de un sondeo sale siempre con
   `origen: "deducido"`: el servidor no confirma nada, porque confirmar es lo
   que hace una persona en el asistente.
2. **La confianza del rol viaja aparte y completa.** `docs/07` §7.15 exige
   desactivar los detectores críticos cuando un rol viene de asignación difusa
   sin confirmar. Si estas respuestas aplanaran la `Asignacion` a
   `rol: "lambda_measured"`, esa mitigación sería imposible de implementar
   aguas abajo y nadie se daría cuenta: el JSON se vería perfecto. Por eso el
   rol viaja como objeto con `confianza`, `sinonimo`, `indice` y `parecido`, y
   nunca como una cadena.

LOS DOS PASOS SIGUIENTES OBEDECEN, NO VUELVEN A DEDUCIR
=======================================================
`sondear_formato` deduce. `sondear_tiempo` y `sondear_canales` reciben el
formato que el usuario ya confirmó y **lo obedecen**: construyen la
`Estructura` a partir de las filas que el usuario señaló en vez de volver a
llamar a `analizar_estructura`. No es un atajo, es la regla de §7.4 («la
detección es una propuesta, no un hecho»): si el paso 2 volviera a deducir la
estructura, una corrección del usuario en el paso 1 podría quedar anulada por
una deducción, o —peor— el paso 2 podría fallar con 422 sobre un fichero cuya
estructura el usuario ya había arreglado a mano.

QUÉ NO SE SIRVE TODAVÍA, Y POR QUÉ
===================================
- **El informe de plausibilidad (FG-10, `dlv_core.plausibilidad`).** §7.7
  punto 2 y §7.15 mitigación 2 lo piden, y el código existe, pero
  `evaluar_canal` juzga los VALORES CANÓNICOS de la columna, no su texto: hace
  falta parsear la columna (FG-07 `valores_csv`) y aplicar la conversión, que
  es otro endpoint y otra tarea. Lo que sí se sirve es el rango declarado de
  cada rol en `/comandos/roles`, que es con lo que el asistente ya marca las
  celdas sospechosas de la previsualización
  (`dlv-ui/src/importacion/previsualizacion.ts`).
- **La fecha de los metadatos para una columna de hora del día.** §7.5 dice
  «fecha desde metadatos o desde el nombre del fichero» y
  `detectar_columna_de_tiempo` acepta `fecha_de_metadatos`, pero NO existe en
  `dlv_core` ninguna función que saque un `date` de `Estructura.metadatos`:
  FG-04 la dejó como parámetro de quien llama. Inventarla aquí sería
  reimplementar en `dlv-api` algo que le toca a `dlv-core`, así que se pasa
  `None` y el aviso `hora_sin_fecha` de FG-04 llega tal cual al asistente. Los
  metadatos crudos sí se sirven (`metadatos` de `sondear_formato`), que es lo
  que hace falta para cerrar el hueco sin volver a leer el fichero.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from dlv_core.formatos.decimal_csv import (
    MAX_FILAS_INSPECCIONADAS,
    Decimales,
    ErrorDeDecimal,
    MotivoDecimal,
    SeparadorDecimal,
    detectar_separador_decimal,
)
from dlv_core.formatos.estructura import (
    ErrorDeEstructura,
    Estructura,
    analizar_estructura,
)
from dlv_core.formatos.sondeo import (
    BYTES_DE_SONDEO,
    ErrorDeSondeo,
    Sondeo,
    dividir_campos,
    sondear_csv,
)
from dlv_core.formatos.tiempo_csv import (
    ClaseDeTiempo,
    ColumnaDeTiempo,
    ErrorDeTiempoCsv,
    detectar_columna_de_tiempo,
)
from dlv_core.formatos.tipos import TipoColumna, TipoDeColumna, inferir_tipos
from dlv_core.formatos.unidades_declaradas import (
    UnidadDeColumna,
    resolver_unidades_declaradas,
)
from dlv_core.informes import Aviso
from dlv_core.plausibilidad import DIMENSION_DESCONOCIDA
from dlv_core.roles import Asignacion, Rol, asignar_rol
from dlv_core.unidades import Catalogo

__all__ = [
    "BYTES_DE_MUESTRA",
    "FILAS_DE_DATOS_EN_PREVIA",
    "FILAS_INSPECCIONADAS",
    "MAX_BYTES_FICHERO",
    "ErrorDeEntrada",
    "FicheroDemasiadoGrande",
    "FicheroNoEncontrado",
    "FormatoConfirmado",
    "Muestra",
    "TiempoConfirmado",
    "catalogo_roles_json",
    "leer_muestra",
    "sondear_canales",
    "sondear_formato",
    "sondear_tiempo",
]

BYTES_DE_MUESTRA = BYTES_DE_SONDEO
"""Cuánto se lee de un fichero para sondearlo: 64 kB.

**El número no es de esta tarea**: es `dlv_core.formatos.sondeo.BYTES_DE_SONDEO`,
que a su vez es el «sobre los primeros 64 kB» literal de `docs/07` §7.4, y el
mismo que ya usa `dlv_api.arrastrar_soltar.TAMANO_SONDEO` citando `docs/03`
§3.4 paso 1. Se reexporta con otro nombre solo porque aquí significa «lo que
esta capa lee del disco» y allí «lo que aquella función puntúa».

Es también el techo que hace que estos endpoints no puedan ser una denegación
de servicio local: un fichero de 2 GB se sondea leyendo 64 kB, decodificando
64 kB y devolviendo como mucho 64 kB de texto. Toda la cadena FG-01…FG-06 está
escrita para trabajar sobre esta muestra —`decimal_csv`, `tiempo_csv` y
`estructura` reciben el mismo `texto`— así que leer más no mejoraría ninguna
decisión, solo el coste.
"""

MAX_BYTES_FICHERO = 512 * 1024 * 1024
"""Tamaño de fichero por encima del cual se rechaza sondear, en bytes.

QUÉ ES ESTE NÚMERO Y QUÉ NO ES
==============================
**No es un umbral de física y no va a `data/umbrales.toml`**, que es el fichero
de los detectores y de sus valores por omisión con la firma del propietario
detrás. Es una guarda sobre una entrada no confiable, de la misma clase que
`sondeo.CONFIANZA_MINIMA` o `tipos.COBERTURA_NUMERICA_MINIMA` —cuya cabecera
dice literalmente «es una heurística de formato, del mismo tipo que
`sondeo.CONFIANZA_MINIMA`. Se puede pasar otro valor por parámetro»— y por eso
es un parámetro de `crear_app`, no una constante cableada.

Y **no es lo que impide la denegación de servicio**: eso lo hace
`BYTES_DE_MUESTRA`, porque el fichero nunca se lee entero. Esta guarda existe
para el otro caso, que es el frecuente: el usuario elige por error un fichero
que no es un log —una imagen de disco, un volcado, un vídeo— y el asistente le
dice eso en vez de proponerle un delimitador para los primeros 64 kB de un
`.iso`.

De dónde sale el 512 MiB: de los presupuestos de `docs/03` §3.8, no de una
preferencia. La memoria residente presupuestada es «≤ 3,5× CSV», así que medio
gigabyte de CSV son ya ~1,8 GB residentes; por encima de eso la aplicación no
puede abrir el log de todas formas, y proponerle una importación al usuario
sería prometer algo que el siguiente paso no cumple. El log real más grande del
propietario son 66 MB (§3.8), así que el margen sobre el caso real es de casi
ocho veces.
"""

FILAS_DE_DATOS_EN_PREVIA = 10
"""Filas de DATOS que se devuelven en la previsualización del paso 1.

`docs/07` §7.8 paso 1: «Previsualización de las 10 primeras filas parseadas».
Las filas de preámbulo, nombres y unidades van además de estas diez, porque el
asistente pinta el papel de cada línea (`#papelDeLinea`) y sin ellas mover
`filaCabecera` o `filaUnidades` no tendría ningún efecto visible.
"""

FILAS_INSPECCIONADAS = MAX_FILAS_INSPECCIONADAS
"""Filas de datos que se miran para inferir tipos y para los valores de la
columna de tiempo.

El número es de `dlv_core`, no de esta tarea:
`decimal_csv.MAX_FILAS_INSPECCIONADAS` y `tiempo_csv.MAX_FILAS_INSPECCIONADAS`
son los dos 200, y `tiempo_csv` ya recorta a ese valor por su cuenta. Se cita
aquí para que las tres cosas que se devuelven de la muestra —tipos, valores de
tiempo y previsualización— estén acotadas por la misma cifra y no por tres.
"""


# --------------------------------------------------------------------------- #
# Errores
# --------------------------------------------------------------------------- #
class ErrorDeEntrada(ValueError):
    """Lo que ha llegado no se puede sondear sin inventar. Se traduce a 422.

    Cubre los tres `ValueError` de `dlv_core` (`ErrorDeSondeo`,
    `ErrorDeEstructura`, `ErrorDeTiempoCsv`) más los índices de fila fuera de
    rango que puede mandar un cliente. El mensaje de `dlv-core` se conserva
    tal cual: explica qué falta y suele decir qué hay que elegir en el
    asistente, que es exactamente lo que el usuario necesita leer.
    """


class FicheroNoEncontrado(ErrorDeEntrada):
    """No existe, o no es un fichero. Se traduce a 404."""


class FicheroDemasiadoGrande(ErrorDeEntrada):
    """Por encima de `MAX_BYTES_FICHERO`. Se traduce a 413."""


# --------------------------------------------------------------------------- #
# Lo que el usuario confirma en cada paso
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class FormatoConfirmado:
    """`PropuestaFormato` de `dlv-ui/src/importacion/tipos.ts`, ya desenvuelta.

    Los `Campo<T>` del asistente llevan además un `origen` («deducido» /
    «confirmado») que **este lado no lee a propósito**: es estado de la sesión
    de importación, vive en el navegador mientras el asistente está abierto, y
    el servidor no toma ninguna decisión distinta según quién eligió el
    delimitador. Lo que sí hace el servidor es obedecer el valor, venga de
    donde venga.
    """

    codificacion: str
    delimitador: str
    """Sin `None` a diferencia de `PropuestaFormato.delimitador`: llegar aquí
    sin delimitador es un 422, porque no hay campos que repartir (es el mismo
    error que lanzan `estructura.analizar_estructura` y
    `decimal_csv.detectar_separador_decimal`). El paso 1 sí puede devolver
    `null`, y entonces el asistente no deja avanzar hasta que el usuario elija
    uno."""

    comilla: str | None
    decimal: str
    fila_cabecera: int | None
    fila_unidades: int | None
    fila_datos: int


@dataclass(slots=True, frozen=True)
class TiempoConfirmado:
    """`PropuestaTiempo` de `tipos.ts`, ya desenvuelta.

    `sondear_canales` la usa para UNA cosa: no ofrecer como canal la columna
    que el paso 2 ya declaró como eje de tiempo (ni la de fecha, cuando son
    dos). Es lo que justifica que `puerto.ts#sondearCanales` reciba el tiempo
    confirmado como tercer argumento.
    """

    clase: ClaseDeTiempo
    columna: int | None
    columna_fecha: int | None
    frecuencia_hz: float | None


@dataclass(slots=True, frozen=True)
class Muestra:
    """Los primeros `BYTES_DE_MUESTRA` de un fichero, y qué se sabe del resto."""

    datos: bytes
    tamano_fichero: int
    truncada: bool
    """`True` si el fichero es más largo que la muestra. Se calcula del tamaño
    real en disco y no de `Sondeo.truncado`: a `sondear_csv` se le entrega una
    muestra ya recortada, así que él ve un fichero completo y devuelve
    `truncado=False`. Que ese matiz llegue bien importa porque es lo que
    explica al usuario que una propuesta pueda fallar más adelante (§7.4)."""


# --------------------------------------------------------------------------- #
# Lectura del disco (la única parte que toca el sistema de ficheros)
# --------------------------------------------------------------------------- #
def leer_muestra(ruta: Path, *, max_bytes_fichero: int = MAX_BYTES_FICHERO) -> Muestra:
    """Los primeros `BYTES_DE_MUESTRA` de `ruta`, cortados en un fin de línea.

    Un fichero que el usuario elige es una entrada no confiable, así que hay
    tres guardas y ninguna es opcional: que exista y sea un fichero (404), que
    no sea absurdamente grande (413) y que no esté vacío (422). Del resto se
    encarga el techo de lectura: nunca se leen más de 64 kB, se pida lo que se
    pida.

    **El corte se hace en el último fin de línea** cuando el fichero es más
    largo que la muestra. No es cosmético: si la muestra acabara en mitad de
    una fila, esa media fila entraría en la previsualización como si fuera un
    dato y podría además descuadrar el recuento de campos. `sondear_csv` ya se
    protege de eso por su cuenta descartando la última línea, pero
    `analizar_estructura`, `decimal_csv` y `tiempo_csv` NO lo hacen: parten
    `texto` por su cuenta y se quedarían la media fila. Cortando aquí, las
    cuatro ven exactamente las mismas líneas, que es la condición para que los
    índices de fila que viajan al asistente signifiquen lo mismo en todas.
    """
    if not ruta.is_file():
        raise FicheroNoEncontrado(f"no existe el fichero: {ruta}")

    tamano = ruta.stat().st_size
    if tamano > max_bytes_fichero:
        raise FicheroDemasiadoGrande(
            f"el fichero mide {tamano} bytes y el máximo para sondear es "
            f"{max_bytes_fichero}. No es un límite del sondeo —que solo lee los "
            f"primeros {BYTES_DE_MUESTRA} bytes— sino de lo que la aplicación puede "
            "abrir después: con la memoria residente presupuestada en 3,5x el CSV "
            "(docs/03 §3.8), un fichero así no se puede cargar. Si de verdad es un "
            "log, hay que partirlo"
        )

    with ruta.open("rb") as fh:
        datos = fh.read(BYTES_DE_MUESTRA)

    if not datos:
        raise ErrorDeEntrada(f"el fichero está vacío: {ruta}")

    truncada = tamano > len(datos)
    if truncada:
        corte = datos.rfind(b"\n")
        # Sin ningún fin de línea en 64 kB no hay nada que cortar: es un
        # fichero de una sola línea larguísima (o no es texto). Se deja la
        # muestra tal cual y que el sondeo diga lo que ve.
        if corte > 0:
            datos = datos[: corte + 1]

    return Muestra(datos=datos, tamano_fichero=tamano, truncada=truncada)


# --------------------------------------------------------------------------- #
# Traducción de vocabulario entre `dlv_core` y `tipos.ts`
# --------------------------------------------------------------------------- #
_TIPO_A_JSON: Mapping[TipoColumna, str] = {
    TipoColumna.VACIA: "vacio",
    TipoColumna.CONSTANTE: "constante",
    TipoColumna.BOOLEANO: "booleano",
    TipoColumna.ENTERO: "entero",
    TipoColumna.DECIMAL: "decimal",
    TipoColumna.ENUM_TEXTO: "enum",
}
"""`TipoColumna` -> `TipoInferido` de `tipos.ts`.

Hace falta una tabla y no `.value` porque los dos vocabularios NO coinciden, y
conviene que eso esté en un sitio en vez de repartido: `tipos.ts` escribe
`"vacio"` donde `dlv_core` escribe `"vacia"`, y `"enum"` donde `dlv_core`
escribe `"enum_texto"`. `tipos.ts` declara además un `"texto"` que ningún
miembro de `TipoColumna` produce (una columna de texto libre es `ENUM_TEXTO`,
con `distintos_truncados`).

`test_importacion_generica.py` comprueba que la tabla cubre los seis miembros:
un `TipoColumna` nuevo sin entrada aquí daría `KeyError` en tiempo de
ejecución, y sería con el fichero de un usuario delante.
"""


def _campo(valor: object) -> dict[str, object]:
    """Un `Campo<T>` de `tipos.ts` con `origen: "deducido"`.

    Siempre «deducido», sin excepción y sin parámetro para cambiarlo: lo que
    sale de un sondeo es una propuesta (§7.4), y «confirmado» solo lo escribe
    el asistente cuando una persona toca el control. Un endpoint que devolviera
    `origen: "confirmado"` estaría firmando en nombre del usuario.
    """
    return {"valor": valor, "origen": "deducido"}


def _avisos_json(*grupos: Sequence[Aviso]) -> list[str]:
    """Los avisos de varios eslabones, como una línea por aviso.

    `[codigo] mensaje` (el `__str__` de `Aviso`) y no `InformeImportacion.
    a_lineas()`, que es lo que usa `/comandos/abrir-cabecera`: `a_lineas`
    intercala un resumen por código y una línea «Detalle:», y estas listas se
    pintan como viñetas en el asistente (`ResultadoSondeoFormato.avisos`), no
    como un informe. El código va delante porque es lo que permite reconocer
    un aviso conocido —`delimitador_sin_determinar`, `hora_sin_fecha`— sin
    leer la prosa.
    """
    return [str(aviso) for grupo in grupos for aviso in grupo]


def _lineas(texto: str) -> list[str]:
    """Las líneas no vacías, que es la unidad en la que cuentan TODOS los
    índices de fila de esta cadena.

    Es literalmente la misma expresión que usan `analizar_estructura`,
    `decimal_csv._filas_de_datos` y `detectar_columna_de_tiempo` por dentro. Se
    repite aquí porque `filaCabecera`, `filaUnidades` y `filaDatos` viajan al
    asistente como índices sobre ESTA lista, y el asistente los usa para
    indexar `filasPrevia`: si las dos listas no fueran la misma, la
    previsualización marcaría como «cabecera» una línea de datos.
    """
    return [linea for linea in texto.splitlines() if linea.strip()]


def _texto(datos: bytes, codificacion: str) -> str:
    """La muestra decodificada, sin lanzar nunca.

    `errors="replace"` es el mismo criterio que ya usa
    `dlv-core/tests/test_fuzzing_generico.py` para esta cadena: una
    codificación mal elegida por el usuario tiene que dar una previsualización
    con caracteres raros —que es lo que le hace corregirla— y no un 500.
    """
    return datos.decode(codificacion, errors="replace")


# --------------------------------------------------------------------------- #
# Paso 1: formato (FG-01 delimitador y codificación, FG-02 decimal, FG-03
# preámbulo / nombres / unidades / inicio de datos)
# --------------------------------------------------------------------------- #
def sondear_formato(muestra: Muestra) -> dict[str, object]:
    """`ResultadoSondeoFormato` de `puerto.ts` para una muestra de bytes.

    Encadena FG-01 -> FG-02 -> FG-03 y devuelve lo que el paso 1 del asistente
    necesita. Cuando FG-01 no llega a proponer delimitador —lo que §7.4 trata
    como un resultado legítimo y no como un fallo— la respuesta es un 200 con
    `delimitador: null` y sin estructura: `PropuestaFormato.delimitador` está
    declarado `Campo<string | null>` justamente para eso, y el asistente no
    deja avanzar hasta que el usuario elija uno. Devolver 422 ahí dejaría al
    usuario sin la previsualización, que es lo único con lo que puede decidir.
    """
    try:
        sondeo = sondear_csv(muestra.datos)
    except ErrorDeSondeo as e:
        raise ErrorDeEntrada(str(e)) from e

    texto = _texto(muestra.datos, sondeo.codificacion)
    lineas = _lineas(texto)

    if sondeo.delimitador is None:
        return _formato_sin_delimitador(sondeo, lineas, muestra)

    try:
        decimales = detectar_separador_decimal(sondeo, texto)
        estructura = analizar_estructura(sondeo, decimales, texto)
    except (ErrorDeDecimal, ErrorDeEstructura) as e:
        # Un fichero de texto que no es una tabla llega hasta aquí: FG-01 le
        # encuentra un delimitador plausible y FG-03 no encuentra ninguna línea
        # mayoritariamente numérica. Es el caso «esto no es un CSV», y el
        # mensaje de `dlv-core` ya explica qué se ha mirado.
        raise ErrorDeEntrada(str(e)) from e

    fin_previa = min(len(lineas), estructura.linea_inicio_datos + FILAS_DE_DATOS_EN_PREVIA)
    return {
        "propuesta": {
            "codificacion": _campo(sondeo.codificacion),
            "delimitador": _campo(sondeo.delimitador),
            "comilla": _campo(sondeo.comilla),
            "decimal": _campo(decimales.separador),
            "filaCabecera": _campo(estructura.linea_nombres),
            "filaUnidades": _campo(estructura.linea_unidades),
            "filaDatos": _campo(estructura.linea_inicio_datos),
        },
        "filasPrevia": lineas[:fin_previa],
        "avisos": _avisos_json(sondeo.avisos, decimales.avisos, estructura.avisos),
        # --- Lo que sigue va por encima de lo que `ResultadoSondeoFormato`
        # --- declara hoy. Un campo de más en el JSON no molesta a TypeScript
        # --- (el tipo es estructural) y cada uno cierra un hueco concreto del
        # --- paso 1; ver el informe de FG-18.
        #
        # `metadatos`: las `clave: valor` del preámbulo (§7.4 paso 7). Van aquí
        # porque son lo que hace falta para situar en el calendario un log con
        # hora del día y sin fecha, y volver a leer el fichero para sacarlas
        # sería absurdo (ver «QUÉ NO SE SIRVE TODAVÍA» en la cabecera).
        "metadatos": dict(estructura.metadatos),
        # `candidatos`: la puntuación de cada combinación (delimitador,
        # comilla). `sondeo.py` insiste en que se devuelvan enteros y no solo
        # el ganador: «proponer `;` sin poder enseñar que `,` dejaba el 40 % de
        # las líneas descuadradas no es una propuesta, es una imposición».
        "candidatos": _candidatos_json(sondeo),
        "confianzaDelimitador": sondeo.confianza,
        "finDeLinea": sondeo.fin_de_linea.etiqueta,
        "finalesMezclados": sondeo.finales_mezclados,
        "tieneBom": sondeo.tiene_bom,
        "nColumnas": estructura.n_columnas,
        "nLineasMuestra": len(lineas),
        "filasPreviaTruncada": fin_previa < len(lineas),
        "muestraTruncada": muestra.truncada,
        "tamanoFichero": muestra.tamano_fichero,
    }


def _candidatos_json(sondeo: Sondeo) -> list[dict[str, object]]:
    """Las puntuaciones de FG-01, para que el paso 1 pueda enseñar POR QUÉ.

    Son como mucho quince (cinco delimitadores por tres comillas), así que la
    lista está acotada por construcción y no por un recorte de esta capa.
    """
    return [
        {
            "delimitador": c.delimitador,
            "comilla": c.comilla,
            "nCampos": c.n_campos,
            "consistencia": c.consistencia,
            "cobertura": c.cobertura,
            "lineasConsistentes": c.lineas_consistentes,
            "lineaInicio": c.linea_inicio,
        }
        for c in sondeo.candidatos
    ]


def _formato_sin_delimitador(
    sondeo: Sondeo, lineas: list[str], muestra: Muestra
) -> dict[str, object]:
    """La respuesta del paso 1 cuando FG-01 no propone delimitador.

    No se deduce nada más: sin campos no hay decimal que verificar (FG-02
    compara dos lecturas de las CELDAS) ni estructura que repartir (FG-03
    lanza), así que lo único honesto es devolver lo que sí se sabe —la
    codificación, los finales de línea, las puntuaciones de cada candidato— y
    las primeras líneas en crudo.

    El decimal se propone `.` porque es lo que propone `dlv-core` cuando no
    tiene evidencia (`decimal_csv`, `MotivoDecimal.SIN_EVIDENCIA`), y se toma
    de su constante en vez de escribir un punto aquí.
    """
    return {
        "propuesta": {
            "codificacion": _campo(sondeo.codificacion),
            "delimitador": _campo(None),
            "comilla": _campo(None),
            "decimal": _campo(SeparadorDecimal.PUNTO),
            "filaCabecera": _campo(None),
            "filaUnidades": _campo(None),
            "filaDatos": _campo(0),
        },
        "filasPrevia": lineas[:FILAS_DE_DATOS_EN_PREVIA],
        "avisos": _avisos_json(sondeo.avisos),
        "metadatos": {},
        "candidatos": _candidatos_json(sondeo),
        "confianzaDelimitador": sondeo.confianza,
        "finDeLinea": sondeo.fin_de_linea.etiqueta,
        "finalesMezclados": sondeo.finales_mezclados,
        "tieneBom": sondeo.tiene_bom,
        "nColumnas": 1,
        "nLineasMuestra": len(lineas),
        "filasPreviaTruncada": len(lineas) > FILAS_DE_DATOS_EN_PREVIA,
        "muestraTruncada": muestra.truncada,
        "tamanoFichero": muestra.tamano_fichero,
    }


# --------------------------------------------------------------------------- #
# El formato ya confirmado: se obedece, no se vuelve a deducir
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class _Estado:
    """Lo que los pasos 2 y 3 necesitan del fichero con el formato confirmado."""

    texto: str
    lineas: list[str]
    sondeo: Sondeo
    decimales: Decimales
    estructura: Estructura


def _estado(muestra: Muestra, formato: FormatoConfirmado) -> _Estado:
    """Reconstruye lo que FG-04/05/06 esperan a partir del formato confirmado.

    Las tres funciones de `dlv_core` que vienen después reciben los objetos de
    FG-01, FG-02 y FG-03 (`Sondeo`, `Decimales`, `Estructura`) y no los
    parámetros pelados, y eso es deliberado en `dlv-core` («se reciben en vez
    de recalcularse para que cada decisión se tome en un solo sitio»). Aquí hay
    que darles esos objetos representando una decisión que ya no es de ningún
    sondeo, sino del usuario. Se hace así:

    * `Sondeo`: se sondea de verdad —cuesta unos milisegundos sobre 64 kB— para
      quedarse con todo lo OBSERVADO (finales de línea, escape, puntuaciones) y
      se sustituye lo DECIDIDO (codificación, delimitador, comilla). Ningún
      campo queda inventado.
    * `Decimales`: aguas abajo solo se lee `.separador`, pero se deduce igual y
      se sustituye solo ese campo, para que `motivo` e `interpretaciones` sigan
      describiendo una deducción real y no un valor de relleno. Si la deducción
      no es posible (no hay filas de datos que mirar), se construye con
      `MotivoDecimal.SIN_EVIDENCIA`, que es exactamente lo que ha pasado.
    * `Estructura`: se construye ENTERA a partir de las filas que el usuario
      señaló, sin llamar a `analizar_estructura`. Es la parte importante: el
      usuario ya corrigió esos tres índices en el paso 1, así que volver a
      deducirlos podría contradecirle, y un `ErrorDeEstructura` dejaría el
      paso 2 en 422 sobre un fichero que el usuario ya había arreglado.

    Lo único que se pierde por no llamar a `analizar_estructura` son los
    `metadatos` del preámbulo, que `dlv_core` solo sabe extraer ahí dentro
    (`_metadatos_de` es privada) y que ninguna de las funciones de los pasos 2
    y 3 lee. El paso 1 sí los devuelve.
    """
    texto = _texto(muestra.datos, formato.codificacion)
    lineas = _lineas(texto)
    _validar_filas(formato, len(lineas))

    try:
        base = sondear_csv(muestra.datos)
    except ErrorDeSondeo as e:  # pragma: no cover - `leer_muestra` ya exige bytes
        raise ErrorDeEntrada(str(e)) from e

    sondeo = dataclasses.replace(
        base,
        codificacion=formato.codificacion,
        delimitador=formato.delimitador,
        comilla=formato.comilla,
        # `elegido` es de dónde saca `Sondeo.linea_inicio_datos` el bloque de
        # datos, y FG-02 lo usa para elegir qué celdas inspecciona. Se alinea
        # con la fila que el usuario confirmó para que la deducción del decimal
        # mire las filas que el usuario llama datos y no otras.
        elegido=(
            None
            if base.elegido is None
            else dataclasses.replace(base.elegido, linea_inicio=formato.fila_datos)
        ),
    )

    try:
        deducidas = detectar_separador_decimal(sondeo, texto)
        decimales = (
            deducidas
            if deducidas.separador == formato.decimal
            else dataclasses.replace(deducidas, separador=formato.decimal, agrupacion=None)
        )
    except ErrorDeDecimal:
        decimales = Decimales(
            separador=formato.decimal,
            agrupacion=None,
            motivo=MotivoDecimal.SIN_EVIDENCIA,
            ambiguo=False,
            interpretaciones=(),
            celdas_inspeccionadas=0,
            filas_inspeccionadas=0,
        )

    return _Estado(
        texto=texto,
        lineas=lineas,
        sondeo=sondeo,
        decimales=decimales,
        estructura=_estructura_confirmada(lineas, formato),
    )


def _validar_filas(formato: FormatoConfirmado, n_lineas: int) -> None:
    """Los tres índices de fila vienen de un cliente: se comprueban.

    Sin esto, un `filaDatos` de 10^9 sería un `IndexError` y un 500 con traza,
    y un `filaCabecera` por debajo de `filaDatos` mezclaría nombres con datos
    sin decir nada. El mensaje dice qué hay en el fichero, que es lo que
    permite corregirlo.
    """
    if not 0 <= formato.fila_datos < n_lineas:
        raise ErrorDeEntrada(
            f"filaDatos={formato.fila_datos} está fuera de la muestra, que tiene "
            f"{n_lineas} líneas con contenido"
        )
    for nombre, indice in (
        ("filaCabecera", formato.fila_cabecera),
        ("filaUnidades", formato.fila_unidades),
    ):
        if indice is None:
            continue
        if not 0 <= indice < n_lineas:
            raise ErrorDeEntrada(
                f"{nombre}={indice} está fuera de la muestra, que tiene {n_lineas} "
                "líneas con contenido"
            )
        if indice >= formato.fila_datos:
            raise ErrorDeEntrada(
                f"{nombre}={indice} no puede estar en los datos o después: los datos "
                f"empiezan en la línea {formato.fila_datos}"
            )


def _estructura_confirmada(lineas: list[str], formato: FormatoConfirmado) -> Estructura:
    """La `Estructura` que describe lo que el usuario confirmó.

    `n_columnas` sale de la PRIMERA FILA DE DATOS y no de la de nombres: §7.10
    admite cabeceras descuadradas y filas de longitud variable, y es el número
    de columnas de los datos el que decide cuántos canales hay. `inferir_tipos`
    trabaja luego sobre `nombres_o_posicionales()`, que rellena con `col_1…n`
    hasta `n_columnas` si la cabecera trae menos nombres.
    """

    def campos(indice: int) -> list[str]:
        partidos: list[str] = dividir_campos(lineas[indice], formato.delimitador, formato.comilla)
        return partidos

    nombres = (
        tuple(c.strip() for c in campos(formato.fila_cabecera))
        if formato.fila_cabecera is not None
        else ()
    )
    unidades = (
        tuple(c.strip() for c in campos(formato.fila_unidades))
        if formato.fila_unidades is not None
        else ()
    )
    filas_con_papel = (formato.fila_cabecera, formato.fila_unidades, formato.fila_datos)
    fin_preambulo = min(i for i in filas_con_papel if i is not None)
    return Estructura(
        linea_inicio_datos=formato.fila_datos,
        linea_nombres=formato.fila_cabecera,
        linea_unidades=formato.fila_unidades,
        nombres=nombres,
        unidades_declaradas=unidades,
        preambulo=tuple(lineas[:fin_preambulo]),
        metadatos={},
        n_columnas=len(campos(formato.fila_datos)),
        filas_de_datos_vistas=len(lineas) - formato.fila_datos,
    )


# --------------------------------------------------------------------------- #
# Paso 2: columna de tiempo (FG-04)
# --------------------------------------------------------------------------- #
def sondear_tiempo(muestra: Muestra, formato: FormatoConfirmado) -> dict[str, object]:
    """`ResultadoSondeoTiempo` de `puerto.ts`.

    LO QUE NO SE RELLENA, Y ES LO IMPORTANTE
    =========================================
    `PropuestaTiempo.frecuenciaHz` es «Hz declarados por el USUARIO», y sale
    `null` incluso cuando FG-04 ha deducido una frecuencia del paso mediano.
    Rellenarla con la deducida sería el error exacto que §7.5 prohíbe: en un
    contador de muestras (`0, 1, 2, …`) o sin columna de tiempo, la frecuencia
    no está en el fichero, y darla por sabida inventa la escala del eje X
    entero. La frecuencia deducida se sirve aparte, en
    `frecuenciaDeducidaHz`, que es un dato informativo del paso 2 y no la
    declaración de nadie.

    `valoresBrutos` son los valores de la columna de tiempo tal como están en
    el fichero, acotados a `FILAS_INSPECCIONADAS`. Van en crudo porque el
    asistente recalcula duración, paso y tasa en el cliente cada vez que el
    usuario cambia la clase o declara una frecuencia
    (`tiempo.ts#calcularResumenTiempo`), sin volver a preguntar al servidor.
    Son unos cientos de cadenas cortas, no una serie: la serie del eje sale del
    transporte binario cuando el log se importa (ADR-007).
    """
    estado = _estado(muestra, formato)
    try:
        tiempo = detectar_columna_de_tiempo(
            estado.sondeo,
            estado.decimales,
            estado.estructura,
            estado.texto,
            # Los dos parámetros que FG-04 deja en manos de quien llama y que
            # aquí no se pueden rellenar: ver la cabecera del módulo.
            frecuencia_declarada_hz=None,
            fecha_de_metadatos=None,
        )
    except ErrorDeTiempoCsv as e:
        raise ErrorDeEntrada(str(e)) from e

    return {
        "propuesta": {
            "clase": _campo(tiempo.clase.value),
            "columna": _campo(tiempo.indice),
            "columnaFecha": _campo(tiempo.indice_fecha),
            "frecuenciaHz": _campo(None),
            "factorASegundos": tiempo.factor_a_segundos,
        },
        "valoresBrutos": _valores_de_tiempo(estado, tiempo),
        "avisos": _avisos_json(tiempo.avisos),
        # --- Por encima de `ResultadoSondeoTiempo`. Los dos primeros no los
        # --- puede calcular el frontend: dependen de la fecha y de la política
        # --- de reloj, no de los valores de la columna.
        "fiabilidad": tiempo.fiabilidad.name,
        "t0Absoluto": None if tiempo.t0_absoluto is None else tiempo.t0_absoluto.isoformat(),
        "nombreColumna": tiempo.nombre,
        "pasoMedianoS": tiempo.paso_mediano_s,
        "frecuenciaDeducidaHz": tiempo.frecuencia_hz,
        "necesitaFrecuenciaDelUsuario": tiempo.clase.necesita_frecuencia_del_usuario,
    }


def _valores_de_tiempo(estado: _Estado, tiempo: ColumnaDeTiempo) -> list[str]:
    """Los valores crudos de la columna de tiempo en las filas de la muestra.

    Lista vacía si no hay columna (`ClaseDeTiempo.AUSENTE`): el eje se
    sintetizará con la frecuencia que declare el usuario, así que no hay
    ningún valor del fichero que enseñar, y devolver ceros fabricados sería
    exactamente lo contrario de lo que pide §7.5.
    """
    if tiempo.indice is None:
        return []
    valores: list[str] = []
    for linea in estado.lineas[estado.estructura.linea_inicio_datos :][:FILAS_INSPECCIONADAS]:
        campos = dividir_campos(linea, estado.sondeo.delimitador or ",", estado.sondeo.comilla)
        valores.append(campos[tiempo.indice] if tiempo.indice < len(campos) else "")
    return valores


# --------------------------------------------------------------------------- #
# Paso 3: canales (FG-05 tipos, FG-06 unidad declarada, FG-09 rol)
# --------------------------------------------------------------------------- #
def sondear_canales(
    muestra: Muestra,
    formato: FormatoConfirmado,
    tiempo: TiempoConfirmado,
    *,
    catalogo: Catalogo,
    alias: Mapping[str, tuple[str, str]],
    catalogo_roles: dict[str, Rol],
) -> dict[str, object]:
    """`ResultadoSondeoCanales` de `puerto.ts`: una fila por canal.

    Encadena FG-05 (tipo de columna), FG-06 (unidad declarada en el nombre o en
    la fila de unidades, resuelta contra `units.toml` + `alias_unidades.toml`) y
    FG-09 (asignación de rol), en ese orden y por ese motivo: el rol se busca
    con el nombre LIMPIO que devuelve FG-06, no con el original. `RPM [rpm]` no
    coincide con ningún sinónimo de `data/roles.toml`; `RPM` sí. Buscar el rol
    antes de quitar la unidad convertía en difusas asignaciones que son
    exactas.

    La columna de tiempo confirmada en el paso 2 no sale como canal: el eje se
    configura en el paso 2 y ofrecerlo otra vez como canal con rol invita a
    asignarle uno.
    """
    estado = _estado(muestra, formato)
    filas = [
        dividir_campos(linea, formato.delimitador, formato.comilla)
        for linea in estado.lineas[formato.fila_datos :][:FILAS_INSPECCIONADAS]
    ]
    nombres = estado.estructura.nombres_o_posicionales()

    tipos = inferir_tipos(filas, nombres, decimal=formato.decimal, catalogo=catalogo)
    unidades = resolver_unidades_declaradas(
        nombres, estado.estructura.unidades_declaradas, catalogo, alias
    )

    del_tiempo = {i for i in (tiempo.columna, tiempo.columna_fecha) if i is not None}
    canales = [
        _canal_json(tipo, unidad, catalogo_roles)
        for tipo, unidad in zip(tipos.columnas, unidades.columnas, strict=True)
        if tipo.indice not in del_tiempo
    ]
    return {
        "canales": canales,
        "avisos": _avisos_json(tipos.avisos, unidades.avisos),
        # --- Por encima de `ResultadoSondeoCanales`.
        "filasInspeccionadas": tipos.filas_inspeccionadas,
        "columnasDeTiempo": sorted(del_tiempo),
    }


def _canal_json(
    tipo: TipoDeColumna,
    unidad: UnidadDeColumna,
    catalogo_roles: dict[str, Rol],
) -> dict[str, object]:
    """Un `CanalPropuesto` de `tipos.ts`."""
    asignacion = asignar_rol(unidad.nombre_limpio, catalogo_roles)
    return {
        "columna": tipo.indice,
        "nombreOriginal": unidad.nombre_original,
        "tipoInferido": _TIPO_A_JSON[tipo.tipo],
        # `"unknown"` y no `null` cuando no se resuelve: `CanalPropuesto.
        # dimensionId` es `Campo<string>` sin nulo a propósito, y `"unknown"`
        # es el identificador que ya usa el resto del proyecto para «el formato
        # no sabe qué magnitud es esto» (`plausibilidad.DIMENSION_DESCONOCIDA`,
        # y los siete tipos `confianza = "unknown"` de `haltech_nsp.toml`). La
        # consecuencia está declarada en §7.15 mitigación 3: se muestra en
        # crudo y sin selector de unidad.
        "dimensionId": _campo(unidad.dimension_id or DIMENSION_DESCONOCIDA),
        "unidadOrigen": _campo(unidad.unidad_cruda),
        "rol": _rol_json(asignacion),
        "avisos": _avisos_de_canal(tipo, unidad, asignacion, catalogo_roles),
        # --- Por encima de `CanalPropuesto`: los recuentos que respaldan el
        # --- tipo inferido. §7.8 paso 3 exige poder ordenar la tabla por
        # --- «necesita atención», y eso solo se puede afinar con los números.
        "nombreLimpio": unidad.nombre_limpio,
        "origenUnidad": unidad.origen.value,
        "unidadResueltaId": unidad.unidad_id,
        "celdas": tipo.celdas,
        "conDato": tipo.con_dato,
        "vacias": tipo.vacias,
        "numericas": tipo.numericas,
        "noNumericas": tipo.no_numericas,
        "centinelasTexto": tipo.centinelas_texto,
        "centinelasDesbordamiento": tipo.centinelas_desbordamiento,
        "valorConstante": tipo.valor_constante,
        "valoresDistintos": list(tipo.valores_distintos),
        "distintosTruncados": tipo.distintos_truncados,
    }


def _rol_json(asignacion: Asignacion | None) -> dict[str, object] | None:
    """`RolPropuesto` de `tipos.ts`, o `null` si nada del catálogo encaja.

    AQUÍ ES DONDE SE PIERDE LA MITIGACIÓN 4 DE §7.15 SI SE HACE MAL
    ===============================================================
    Un canal cuyo rol se dedujo por parecido del 87 % y uno cuyo nombre coincide
    exactamente con un sinónimo del catálogo se ven idénticos si la respuesta
    solo lleva `rol: "lambda_measured"`. Y no da ningún error: da un JSON
    correcto con una alerta crítica activada sobre una corazonada. Por eso
    viajan los cuatro campos de `Asignacion` —`confianza`, el `sinonimo` que la
    disparó, el `indice` capturado y el `parecido`— y no solo el identificador.
    `dlv_core.roles.resolver_rol` existe y devuelve solo el rol; usarlo aquí
    sería el atajo que su propio docstring prohíbe.

    `confirmado` es el único campo que NO viene de `dlv-core`, porque no es un
    dato del fichero sino estado del asistente. Se manda con el mismo criterio
    que `deduccion.ts#propuestaInicialDeRol` aplica en el cliente: `EXACTA` e
    `INDEXADA` nacen confirmadas (son firmes por construcción, la plantilla
    `{n}` está explícita en el catálogo), `DIFUSA` nace sin confirmar. Que la
    regla esté escrita en dos lenguajes es un riesgo real de divergencia y la
    prueba `test_confirmado_coincide_con_la_regla_de_deduccion_ts` es lo que lo
    vigila; la alternativa —no mandar `confirmado` y dejar que el cliente lo
    calcule— exigiría cambiar `CanalPropuesto.rol`, que ya está construido y
    probado.
    """
    if asignacion is None:
        return None
    return {
        "rol": asignacion.rol,
        "confianza": asignacion.confianza.name,
        "sinonimo": asignacion.sinonimo,
        "indice": asignacion.indice,
        "parecido": asignacion.parecido,
        "confirmado": not asignacion.requiere_confirmacion,
    }


def _avisos_de_canal(
    tipo: TipoDeColumna,
    unidad: UnidadDeColumna,
    asignacion: Asignacion | None,
    catalogo_roles: dict[str, Rol],
) -> list[str]:
    """La «columna de avisos» de §7.8 paso 3, en prosa corta.

    Son avisos POR CANAL y por eso no pueden ser los `Aviso` globales de
    `inferir_tipos` ni de `resolver_unidades_declaradas`, que ya viajan en
    `avisos` de la respuesta. Aquí no se decide nada nuevo: cada línea es la
    lectura en prosa de un hecho que FG-05, FG-06 o FG-09 ya calcularon, y el
    asistente las junta con «; » en una celda de la tabla
    (`asistente-importacion.ts#filaCanal`), así que son cortas a propósito.
    """
    avisos: list[str] = []

    if unidad.unidad_cruda is not None and not unidad.resuelta:
        avisos.append(
            f"declara la unidad «{unidad.unidad_cruda}» y no se ha podido resolver: "
            "se mostrará en crudo, sin selector de unidad (§7.6)"
        )

    if tipo.tipo is TipoColumna.VACIA:
        avisos.append("ninguna celda con dato en la muestra: no se puede graficar")
    elif tipo.tipo is TipoColumna.CONSTANTE:
        avisos.append(f"constante en la muestra («{tipo.valor_constante}»)")

    if tipo.no_numericas:
        ejemplos = ", ".join(f"«{e}»" for e in tipo.ejemplos_no_numericos)
        avisos.append(
            f"{tipo.no_numericas} de {tipo.con_dato} celdas con dato no son números"
            + (f" ({ejemplos})" if ejemplos else "")
        )
    if tipo.centinelas_desbordamiento:
        avisos.append(
            f"{tipo.centinelas_desbordamiento} celdas son centinela de desbordamiento: "
            "ausencia, nunca un valor"
        )
    if tipo.distintos_truncados:
        avisos.append("más valores distintos de los que se guardan: parece texto libre")

    if asignacion is not None:
        rol = catalogo_roles.get(asignacion.rol)
        if asignacion.requiere_confirmacion:
            avisos.append(
                f"rol «{asignacion.rol}» propuesto solo por parecido "
                f"({asignacion.parecido:.0%} con «{asignacion.sinonimo}»): confírmalo, "
                "los detectores críticos que lo necesiten quedan desactivados hasta "
                "entonces (§7.15)"
            )
        # La comprobación más barata y más concluyente de FG-10, y la única que
        # no necesita ni una muestra: si la unidad declarada dice una dimensión
        # y el rol espera otra, el rango del rol no significa nada sobre este
        # canal. Se compara lo que declaran los dos catálogos, no se juzga
        # ningún valor: el informe de plausibilidad completo
        # (`dlv_core.plausibilidad`) necesita la columna ya parseada y no es de
        # esta tarea.
        if (
            rol is not None
            and rol.dimension is not None
            and unidad.dimension_id is not None
            and rol.dimension != unidad.dimension_id
        ):
            avisos.append(
                f"el fichero declara la dimensión «{unidad.dimension_id}» y el rol "
                f"«{asignacion.rol}» espera «{rol.dimension}»: o el rol o la unidad "
                "están mal"
            )
    return avisos


# --------------------------------------------------------------------------- #
# El catálogo de roles: `data/roles.toml`, servido como `/comandos/unidades`
# sirve `data/units.toml`
# --------------------------------------------------------------------------- #
def catalogo_roles_json(catalogo: Mapping[str, Rol]) -> list[dict[str, object]]:
    """`RolDeCatalogo[]` de `puerto.ts`, ordenado por identificador.

    Se sirve en vez de duplicar el catálogo en TypeScript por la regla 2 de
    `CLAUDE.md`: `data/roles.toml` es dato del propietario, tiene puerta G1 y
    sus comentarios son lo que lo hace revisable. Trasladar sus 58 entradas al
    frontend crearía una segunda copia que habría que cambiar a la vez, y
    añadir la nomenclatura de otro fabricante dejaría de ser «una entrada de
    fichero» (§7.7).

    Los tres campos que el asistente ya consume son `id` (desplegable de
    «asignar rol a mano»), `plausibleMin`/`plausibleMax` (marca las celdas
    sospechosas de la previsualización, §7.7 punto 2) y `dimensionId`. Van
    además `sinonimos`, `indexado` y `monotono`, que son lo que hace la lista
    buscable y lo que declara que un contador acumulado habilita el canal
    delta. Los rangos van en UNIDAD CANÓNICA, como los declara el fichero: son
    la mitad de un contrato y convertirlos aquí lo rompería.

    `[meta]` no se sirve: es para quien revisa el fichero, no para la interfaz
    (mismo criterio que `evidencia` en `_catalogo_combustibles`).
    """
    return [
        {
            "id": rol.id,
            "dimensionId": rol.dimension,
            "plausibleMin": rol.plausible_min,
            "plausibleMax": rol.plausible_max,
            "critico": rol.critico,
            "sinonimos": list(rol.sinonimos),
            "indexado": rol.indexado,
            "monotono": rol.monotono,
        }
        for rol in sorted(catalogo.values(), key=lambda r: r.id)
    ]


def clase_de_tiempo_desde_json(valor: str) -> ClaseDeTiempo:
    """`"relativo"` -> `ClaseDeTiempo.RELATIVO`, validando.

    El paso 3 recibe la clase de tiempo que el usuario confirmó, y una cadena
    que no sea ninguna de las ocho de §7.5 tiene que dar 422 con la lista de
    las que hay, no un `ValueError` desnudo.
    """
    try:
        return ClaseDeTiempo(valor)
    except ValueError as e:
        validas = ", ".join(c.value for c in ClaseDeTiempo)
        raise ErrorDeEntrada(
            f"clase de tiempo desconocida: {valor!r}. Las de docs/07 §7.5 son: {validas}"
        ) from e


_LITERALES_DECIMAL: tuple[str, ...] = (SeparadorDecimal.PUNTO, SeparadorDecimal.COMA)
"""Los dos separadores decimales, tomados de `dlv-core` y no escritos aquí.

`PropuestaFormato.decimal` es `Campo<"." | ",">` en TypeScript; esta tupla es
el mismo par en Python, y es lo que valida `main.ComandoSondearTiempo`.
"""


def validar_decimal(valor: str) -> str:
    """El separador decimal confirmado, o 422."""
    if valor not in _LITERALES_DECIMAL:
        raise ErrorDeEntrada(
            f"separador decimal desconocido: {valor!r}. Solo hay dos: "
            f"{' y '.join(repr(d) for d in _LITERALES_DECIMAL)}"
        )
    return valor


def formato_confirmado(
    *,
    codificacion: str,
    delimitador: str | None,
    comilla: str | None,
    decimal: str,
    fila_cabecera: int | None,
    fila_unidades: int | None,
    fila_datos: int,
) -> FormatoConfirmado:
    """Valida y construye el `FormatoConfirmado` de una petición.

    Vive aquí y no en `main.py` para que se pueda probar sin FastAPI, y porque
    las dos comprobaciones que hace son sobre el vocabulario de `dlv-core`
    (¿es un separador decimal de los dos que hay? ¿hay delimitador?), no sobre
    HTTP.
    """
    if delimitador is None or delimitador == "":
        raise ErrorDeEntrada(
            "hay que confirmar un delimitador antes de sondear el tiempo o los canales: "
            "sin él no hay campos que repartir. Es el caso que el paso 1 devuelve con "
            "`delimitador: null` (docs/07 §7.4)"
        )
    return FormatoConfirmado(
        codificacion=codificacion,
        delimitador=delimitador,
        comilla=comilla or None,
        decimal=validar_decimal(decimal),
        fila_cabecera=fila_cabecera,
        fila_unidades=fila_unidades,
        fila_datos=fila_datos,
    )


def tiempo_confirmado(
    *,
    clase: str,
    columna: int | None,
    columna_fecha: int | None,
    frecuencia_hz: float | None,
) -> TiempoConfirmado:
    """Valida y construye el `TiempoConfirmado` de una petición."""
    return TiempoConfirmado(
        clase=clase_de_tiempo_desde_json(clase),
        columna=columna,
        columna_fecha=columna_fecha,
        frecuencia_hz=frecuencia_hz,
    )
