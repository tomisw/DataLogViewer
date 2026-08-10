"""Exportación de datos a CSV/Parquet con unidad declarada por columna (F4-12, E8.2).

DÓNDE VIVE Y POR QUÉ (`docs/02` E8.2, ADR-002, ADR-006)
========================================================
PNG y SVG son de la VISTA (canvas WebGL2 + overlay SVG) y viven en `dlv-ui`
(`dlv-ui/src/exportar/exportar-imagen.ts`). CSV y Parquet son de los DATOS, y
Parquet no se escribe desde el navegador: van aquí, en `dlv-api`, que es quien
ya tiene Polars detrás (`dlv_core.transporte` la usa igual para Arrow IPC).

`dlv-core` no abre ficheros por su cuenta (ADR-002) y este módulo respeta la
misma regla aunque viva en `dlv-api`: no toca el disco ni una ruta, recibe
arrays ya en memoria y devuelve `bytes`. Quien escribe el fichero de verdad es
el endpoint HTTP de `dlv_api.main`, que es la capa a la que ADR-002 sí permite
tocar el sistema de ficheros.

EL TÍTULO DE LA TAREA ES LA PARTE QUE SE REVISA: «UNIDAD DECLARADA POR COLUMNA»
================================================================================
Un CSV sin unidad por columna es una trampa silenciosa: una columna de
temperatura es un número igual de plausible en °C que en K, y quien lo abra en
Excel dentro de seis meses no tiene forma de saber cuál es. Este módulo hace
dos cosas para que eso no pueda pasar:

1. **El nombre de columna lleva la unidad**, en los dos formatos: "temp_agua
   [°C]", "boost [bar (rel)]", "modo_arranque [sin unidad]". Es legible sin
   abrir nada más que el propio fichero, y es lo mismo que ya hace
   `dlv_core.unidades.etiqueta_de` para la leyenda (`abs`/`rel` incluido).
2. **Parquet además lo guarda estructurado**, en los metadatos del propio
   fichero (`escribir_parquet`, más abajo) — no en un `.json` al lado, que se
   puede perder o desincronizar del `.parquet` que acompaña.

LA CLASE DE CONVERSIÓN, OTRA VEZ, Y EN DOS SITIOS
==================================================
`docs/06-sistema-de-unidades.md` §6.5 y la trampa del delta
(`dlv-core/tests/test_trampa_del_delta.py`, F1-20) ya bastan para el paso
canónica -> unidad mostrada (`dlv_core.unidades.desde_canonica`, que exige
`Clase` sin valor por omisión). Este módulo tiene un segundo paso, ANTES de
ese: bruto del almacén -> canónica, con el `Afin` que ya trae cada canal
(`ChannelSeries.to_canon`, el mismo objeto que sirve `/comandos/serie`).

Ese primer paso normalmente decodifica un PUNTO (una muestra del log es una
medida absoluta), pero no siempre: si algún día se exporta una columna que ya
es una amplitud en bruto — por ejemplo, máximo-mínimo de un cubo de pirámide
sin decodificar — decodificarla con el `b` de su escala aplicaría el mismo
desplazamiento que la trampa del delta, solo que un paso más atrás. Por eso
`ColumnaAExportar.clase` gobierna LOS DOS pasos, no solo el segundo:
`preparar_columna` reutiliza `Afin.desde_canonica` (el mismo código que usa
`dlv_core.unidades.desde_canonica` internamente) para el paso bruto ->
canónica, en vez de escribir un `a * x + b` suelto que se olvide de la regla
la próxima vez que alguien tenga que tocar esto.

QUÉ SE EXPORTA EN CRUDO, Y POR QUÉ NO SE INVENTA UNA UNIDAD (R1)
=================================================================
Tres motivos posibles, los tres ya modelados en el resto del sistema y
reutilizados aquí, no reinventados:

- `dimension_id is None` — el `Type` de origen no está en el descriptor de
  formato (`Canal.dimension is None` en `dlv_core.formatos.haltech`).
- `confianza == "unknown"` — la escala no está confirmada
  (`Canal.confianza`, `docs/06` §6.8): mostrarla convertida sería un número
  con aspecto de correcto y origen dudoso.
- `Dimension.mostrar_en_crudo` — la dimensión entera es "no es una magnitud"
  (contadores, enumerados, máscaras de bits: la dimensión literal `unknown`
  de `data/units.toml`, no el `None` de arriba).

En los tres casos la columna sale con el valor tal cual está en el almacén,
sin aplicar ni `to_canon` ni ninguna unidad, y el encabezado lo dice.

Solo biblioteca estándar en la parte que decide (`preparar_columna`): Polars
se importa DENTRO de `exportar_csv`/`exportar_parquet`, no en la cabecera del
módulo, a propósito — el mismo motivo por el que `dlv_api/__init__.py` no
importa `dlv_api.main`. Así, en un entorno sin Polars instalado, `import
dlv_api.exportacion` sigue funcionando y la lógica de qué unidad y qué clase
le toca a cada columna se puede probar sin la dependencia — que es exactamente
la situación de quien revisó esta tarea (ver el informe de F4-12).
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from dlv_core.unidades import Afin, Catalogo, Clase, Dimension, desde_canonica, etiqueta_de

__all__ = [
    "MEDIA_TYPE_CSV",
    "MEDIA_TYPE_PARQUET",
    "ColumnaAExportar",
    "ColumnaPreparada",
    "ErrorDeExportacion",
    "exportar_csv",
    "exportar_parquet",
    "preparar_columna",
    "preparar_columnas",
]

MEDIA_TYPE_CSV = "text/csv"
"""Tipo MIME de `/comandos/exportar-datos` cuando `formato == "csv"`."""

MEDIA_TYPE_PARQUET = "application/vnd.apache.parquet"
"""Tipo MIME registrado en IANA para Parquet. No es Arrow IPC (ADR-007 solo
manda ese binario para las series que dibuja el renderizador); un `.parquet`
exportado lo abre el usuario en otra herramienta, así que aquí el tipo MIME sí
importa para que el navegador lo trate como descarga y no como texto."""


class ErrorDeExportacion(RuntimeError):
    """La exportación no se puede completar por el entorno, no por los datos.

    Se distingue de `ErrorDeUnidad` a propósito: aquel dice «lo que has pedido no
    tiene sentido» (dimensión o unidad inexistente) y se traduce a un 422; este
    dice «lo que has pedido tiene sentido y esta instalación no puede hacerlo».
    """


@dataclass(slots=True, frozen=True)
class ColumnaAExportar:
    """Una columna a exportar, en la escala BRUTA del almacén.

    `valores` es lo mismo que `ChannelSeries.v` / `CanalSesion.serie.v`: el
    entero (o flotante) tal cual está en memoria, antes de `to_canon`. Este
    módulo hace los dos pasos de conversión completos —bruto -> canónica ->
    unidad de destino— con la misma aritmética que usa el resto del sistema,
    para que la unidad que declara el encabezado sea la que de verdad se
    aplicó a los números de la columna.

    `valores` es `Any` a propósito (ADR-009): puede ser un `float` (una
    prueba con un escalar), una `list[float]` o un `numpy.ndarray` de varios
    millones de muestras — el mismo código de `preparar_columna` sirve para
    los tres, porque la aritmética de `Afin`/`desde_canonica` tampoco
    distingue. No hay ningún bucle por muestra en este módulo.
    """

    nombre: str
    valores: Any
    clase: Clase
    """Obligatorio y sin valor por omisión, a propósito: es el mismo campo, y
    la misma regla (`docs/06` §6.5), que `dlv_core.unidades.desde_canonica`.
    Gobierna TANTO el paso bruto -> canónica como el canónica -> destino (ver
    la cabecera del módulo)."""
    dimension_id: str | None
    """`None` si el tipo de origen no está en el descriptor de formato
    (`Canal.dimension`, `dlv_core.formatos.haltech`): la columna se exporta en
    crudo, sin intentar resolver nada más."""
    confianza: str = "confirmed"
    """`Canal.confianza` / `CanalSesion.confianza`. Con `"unknown"` la columna
    se exporta en crudo aunque `dimension_id` esté informado (R1, `docs/06`
    §6.8): la escala no está confirmada, así que no hay factor del que fiarse."""
    to_canon: Afin = field(default_factory=lambda: Afin(1.0, 0.0))
    """Bruto -> canónica (`ChannelSeries.to_canon`). La identidad por omisión
    es la de una columna que YA está en canónica —un canal matemático o una
    métrica derivada, por ejemplo—, no la de un canal del almacén: quien pasa
    un canal real del almacén tiene que pasar su `to_canon` de verdad."""
    unidad_destino: str | None = None
    """`None` exporta en la unidad CANÓNICA de la dimensión. Con un id (o
    alias) de unidad, exporta en esa — `docs/06` §6.11: «se puede exportar en
    canónica o en la unidad mostrada, y la elección se registra en el
    fichero» (el propio encabezado es ese registro)."""
    parametro: float | None = None
    """Para una conversión `Parametrizada` (λ -> AFR): la estequiometría del
    combustible en uso. `None` usa el valor por omisión del catálogo."""
    referencia_kpa: float | None = None
    """Solo para `pressure`: pasa a relativo (`docs/06` §6.6). `None` exporta
    en absoluto. Se aplica solo a los PUNTOS, igual que en
    `dlv_core.unidades.desde_canonica` — un Δ de presión no cambia con el
    origen."""


@dataclass(slots=True, frozen=True)
class ColumnaPreparada:
    """Una columna ya resuelta: su encabezado (con la unidad), sus valores ya
    convertidos y los metadatos que `exportar_parquet` guarda en el fichero."""

    encabezado: str
    valores: Any
    metadatos: dict[str, Any]
    """Lo que declara esta columna, en forma de datos y no solo de texto:
    `exportar_parquet` lo serializa a JSON y lo guarda en los metadatos del
    fichero (ver su docstring). `exportar_csv` no lo usa —un CSV no tiene
    metadatos propios— pero vive aquí y no en `exportar_parquet` porque es
    parte de lo que decide `preparar_columna`, no de cómo se escribe cada
    formato."""


def _etiqueta_y_metadatos_en_crudo(
    columna: ColumnaAExportar, *, dimension: Dimension | None, motivo: str, etiqueta_unidad: str
) -> tuple[str, dict[str, Any]]:
    metadatos: dict[str, Any] = {
        "dimension": dimension.id if dimension is not None else None,
        "unidad": None,
        "etiqueta_unidad": etiqueta_unidad,
        "clase": columna.clase.value,
        "crudo": True,
        "motivo_crudo": motivo,
    }
    return f"{columna.nombre} [{etiqueta_unidad}]", metadatos


def preparar_columna(columna: ColumnaAExportar, *, catalogo: Catalogo) -> ColumnaPreparada:
    """Decide la unidad de una columna y convierte sus valores (o los deja en
    crudo), sin escribir nada: es la mitad de este módulo que no necesita
    Polars y que se puede probar sin él (ver la cabecera del módulo).

    Lanza `ErrorDeUnidad` (`dlv_core.unidades`) si `dimension_id` no es una
    dimensión del catálogo, o si `unidad_destino` no es una unidad (o alias)
    de esa dimensión — los mismos casos, con el mismo mensaje, que lanzaría
    `Catalogo.dimension` / `Dimension.unidad` directamente. Quien llama desde
    HTTP (`dlv_api.main`) la convierte en una respuesta 422.
    """
    if columna.dimension_id is None:
        encabezado, metadatos = _etiqueta_y_metadatos_en_crudo(
            columna,
            dimension=None,
            motivo="tipo_desconocido: el tipo de origen no está en el descriptor de formato",
            etiqueta_unidad="sin unidad",
        )
        return ColumnaPreparada(encabezado=encabezado, valores=columna.valores, metadatos=metadatos)

    dimension = catalogo.dimension(columna.dimension_id)

    if columna.confianza == "unknown":
        encabezado, metadatos = _etiqueta_y_metadatos_en_crudo(
            columna,
            dimension=dimension,
            motivo="escala_sin_confirmar: la escala de este canal no está confirmada (R1)",
            etiqueta_unidad="sin confirmar",
        )
        return ColumnaPreparada(encabezado=encabezado, valores=columna.valores, metadatos=metadatos)

    if dimension.mostrar_en_crudo or not dimension.convertible:
        # La dimensión entera es "no es una magnitud" (contadores, enumerados,
        # máscaras de bits: la dimensión `unknown` de `data/units.toml`). Su
        # propia unidad canónica ya trae la etiqueta correcta ("(crudo)"), así
        # que no hay que inventar un texto aquí.
        etiqueta_unidad = dimension.unidad(dimension.unidad_canonica).etiqueta
        encabezado, metadatos = _etiqueta_y_metadatos_en_crudo(
            columna,
            dimension=dimension,
            motivo="dimension_no_convertible: la dimensión no representa una magnitud continua",
            etiqueta_unidad=etiqueta_unidad,
        )
        return ColumnaPreparada(encabezado=encabezado, valores=columna.valores, metadatos=metadatos)

    # Caso general: bruto -> canónica -> unidad de destino, con la MISMA clase
    # en los dos pasos. Ver la cabecera del módulo sobre por qué el primer paso
    # también necesita la clase y no solo el segundo.
    canonico = columna.to_canon.desde_canonica(columna.valores, columna.clase, columna.parametro)
    unidad_id = (
        columna.unidad_destino if columna.unidad_destino is not None else dimension.unidad_canonica
    )
    mostrado = desde_canonica(
        canonico,
        dimension=dimension,
        unidad=unidad_id,
        clase=columna.clase,
        param=columna.parametro,
        referencia_kpa=columna.referencia_kpa,
    )
    unidad = dimension.unidad(unidad_id)
    etiqueta_unidad = etiqueta_de(dimension, unidad_id, relativa=columna.referencia_kpa is not None)
    metadatos = {
        "dimension": dimension.id,
        "unidad": unidad.id,
        "etiqueta_unidad": etiqueta_unidad,
        "clase": columna.clase.value,
        "crudo": False,
        "motivo_crudo": None,
        "referencia_kpa": columna.referencia_kpa,
    }
    return ColumnaPreparada(
        encabezado=f"{columna.nombre} [{etiqueta_unidad}]", valores=mostrado, metadatos=metadatos
    )


def preparar_columnas(
    columnas: Sequence[ColumnaAExportar], *, catalogo: Catalogo
) -> list[ColumnaPreparada]:
    """`preparar_columna` sobre una lista. El bucle es sobre COLUMNAS (unas
    pocas decenas como mucho), no sobre muestras: no lo alcanza ADR-009, que
    prohíbe el bucle por muestra, no el bucle por canal."""
    return [preparar_columna(c, catalogo=catalogo) for c in columnas]


def exportar_csv(columnas: Sequence[ColumnaAExportar], *, catalogo: Catalogo) -> bytes:
    """CSV con la unidad de cada columna en su propio encabezado.

    `import polars` está DENTRO de esta función, no en la cabecera del módulo:
    ver la nota al final de la cabecera del módulo sobre por qué.
    """
    import polars as pl

    preparadas = preparar_columnas(columnas, catalogo=catalogo)
    tabla = pl.DataFrame({p.encabezado: p.valores for p in preparadas})
    # La anotación explícita (y no `Any` vía `polars.*` en `ignore_missing_imports`)
    # es lo que permite declarar este módulo `bytes` bajo `mypy --strict`.
    texto_csv: str = tabla.write_csv()
    return texto_csv.encode("utf-8")


def exportar_parquet(columnas: Sequence[ColumnaAExportar], *, catalogo: Catalogo) -> bytes:
    """Parquet con la unidad de cada columna en su encabezado Y en los
    metadatos del propio fichero.

    POR QUÉ LOS METADATOS SON UN JSON EN UNA CLAVE DE FICHERO, NO METADATOS
    POR CAMPO DE ARROW
    =========================================================================
    Metadatos de CAMPO (por columna, en el esquema Arrow) exigirían construir
    el esquema con PyArrow (`pyarrow.field(..., metadata=...)`): Polars no lo
    ofrece con su propio escritor sin pasar por ahí. `pyarrow` no está en
    `pyproject.toml` y esta tarea tiene prohibido añadir dependencias, así que
    no se añade para esto.

    Lo que Polars SÍ ofrece de forma nativa es metadato a nivel de FICHERO:
    `write_parquet(..., metadata=...)`, un `dict[str, str]` que queda en el
    `key_value_metadata` del propio Parquet (legible con
    `polars.read_parquet_metadata` sin abrir los datos). Este módulo guarda
    ahí un único JSON, `dlv:unidades`, con la unidad y la clase de CADA
    columna indexadas por su encabezado — sigue siendo metadato "de columna"
    en el sentido que pide la tarea (qué unidad tiene cada columna, dentro del
    propio fichero, no en un `.json` aparte que se pueda perder o
    desincronizar), solo que la clave que lo aloja es del fichero entero y no
    del campo. Ver el informe de F4-12 para la comprobación de que la versión
    de Polars instalada admite este parámetro: no se pudo ejecutar en este
    entorno (sin Polars instalado) y se confirmó por documentación, no por
    prueba.
    """
    import polars as pl

    preparadas = preparar_columnas(columnas, catalogo=catalogo)
    tabla = pl.DataFrame({p.encabezado: p.valores for p in preparadas})
    metadatos_por_columna = {p.encabezado: p.metadatos for p in preparadas}
    buffer = io.BytesIO()
    try:
        tabla.write_parquet(
            buffer,
            metadata={
                "dlv:version": "1",
                "dlv:unidades": json.dumps(metadatos_por_columna, ensure_ascii=False),
            },
        )
    except TypeError as exc:
        # `metadata=` es reciente en Polars, y `pyproject.toml` declara `>=1.9`,
        # donde no existe. Con una versión antigua, `write_parquet` levanta un
        # `TypeError` por argumento inesperado que no dice nada útil, y el
        # exportador entero falla. Se traduce a un error con nombre para que el
        # mensaje diga qué pasa y qué hacer, en vez de dejar la traza cruda de
        # Polars llegando al usuario a través de una respuesta HTTP.
        raise ErrorDeExportacion(
            "la versión de Polars instalada no admite `write_parquet(metadata=...)`, "
            "así que no se puede escribir la unidad de cada columna en los metadatos "
            "del Parquet. Actualiza Polars (`uv sync --all-packages`) o exporta a CSV, "
            f"que lleva la unidad en el propio encabezado. Detalle: {exc}"
        ) from exc
    return buffer.getvalue()
