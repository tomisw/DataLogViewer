/**
 * Contrato de datos del informe de sesión HTML autocontenido (F4-11, E8.1).
 *
 * NINGÚN NÚMERO LLEGA SIN CONVERTIR NI SIN FORMATEAR — ES LA DECISIÓN CENTRAL
 * =============================================================================
 * Este módulo no importa `unidades/conversion.ts` ni decide nunca una `Clase`.
 * No es un olvido: es la manera de no poder caer en la trampa del delta (regla
 * 4 de `CLAUDE.md`, `docs/06` §6.5) desde este fichero. `dlv_core.malla.
 * CLASE_DE_ESTADISTICA` existe precisamente porque «media»/«mínimo»/«máximo»
 * son `Clase.PUNTO` pero «desviación típica» es `Clase.INTERVALO» — y un
 * informe que mostrara esas cinco estadísticas como números crudos con una
 * sola conversión aplicada a las cinco repetiría exactamente ese error. La
 * salida de este módulo es texto para leer, no aritmética: todo campo
 * numérico de `DatosInformeSesion` que representa una magnitud física llega
 * YA convertido, YA formateado y YA con su unidad en el propio texto —el
 * mismo patrón que `malla/tipos.ts#DetalleCelda` (`mediaTexto`,
 * `desviacionTipicaTexto`, ...) y que `dlv_api.exportacion.ColumnaPreparada`
 * (`encabezado` lleva la unidad, `preparar_columna` ya hizo los dos pasos de
 * conversión antes de que el número llegue aquí). Los únicos campos `number`
 * de este fichero son CUENTAS (`muestras`, `canales`): no tienen clase de
 * conversión porque no son una magnitud, son un cardinal.
 *
 * DÓNDE VIVE, Y POR QUÉ (mismo criterio que F4-12, ver `exportar/exportar-imagen.ts`)
 * ======================================================================================
 * Un informe con gráficos es de la VISTA: los gráficos que incrusta son el
 * mismo SVG autocontenido que ya produce `exportar/exportar-imagen.ts`
 * (trazo WebGL2 rasterizado + ejes vectoriales), y ese módulo vive en
 * `dlv-ui` por el mismo motivo que este. `dlv-core` no toca el sistema de
 * ficheros (ADR-002) y este módulo tampoco: `generarInformeSesionHtml`
 * devuelve una cadena, `informeComoBlob` la envuelve en un `Blob` — ninguno
 * de los dos escribe nada. Quien escriba el `.html` de verdad es la capa de
 * comandos que monte la aplicación (`app/aplicacion.ts` o quien lo llame),
 * fuera del alcance de esta tarea.
 *
 * QUÉ SE QUEDA FUERA, Y POR QUÉ (segunda decisión del encargo)
 * ================================================================
 * Las series completas NO entran: un log de 73 M de muestras en 475 canales
 * son cientos de megabytes, y un `.html` de ese tamaño no lo abre ningún
 * navegador con comodidad — el propio objetivo de «autocontenido, se abre en
 * cualquier sitio dentro de seis meses» se rompería. Lo que entra son
 * `GraficoInforme`: gráficos YA renderizados a un tamaño de pantalla
 * razonable, la misma composición PNG-rasterizado-más-SVG-vectorial que ya
 * usa la exportación de F4-12. Cuántos gráficos y de qué canales lo decide
 * quien arma `DatosInformeSesion`, no este módulo.
 *
 * QUÉ HACE ESTE MÓDULO CON «TIRADAS» (F3-16), QUE NO ESTÁ CABLEADA AL FRONTEND
 * =================================================================================
 * `dlv_core.segmentacion` (F3-16) existe y está cerrada, pero no hay ningún
 * endpoint de `dlv-api` que sirva sus tiradas al frontend todavía — se
 * comprobó al escribir esta tarea (`grep` de "segmentacion"/"Tirada" en
 * `dlv-api/src/dlv_api/*.py` no encuentra nada). Así que, HOY, quien arme
 * `DatosInformeSesion` no tiene de dónde sacar tiradas reales, y la tarea es
 * explícita: no se inventan. `SeccionTiradas` modela las tres respuestas
 * honestas posibles, para que ni este módulo ni quien lo llame tengan que
 * fingir una que no tienen:
 *
 * - `"no_disponible"`: la sesión que genera este informe no tiene datos de
 *   segmentación en absoluto (el caso de HOY, sin el endpoint). El informe lo
 *   DICE, no omite la sección en silencio — omitir sin más sería indistinguible
 *   de «se comprobó y no hay tiradas», que es una afirmación distinta y falsa.
 * - `"vacia"`: SÍ hubo segmentación, y no encontró ninguna tirada en esta
 *   sesión (un log de ralentí puro, por ejemplo). Es una respuesta real, no
 *   la ausencia de una.
 * - `"con_datos"`: la lista de tiradas detectadas, ya con su clase, inicio y
 *   duración como texto formateado (ver la nota de arriba sobre por qué nunca
 *   `number` crudo).
 */

import type { DetectorCatalogo, EstadoDetector, IncidenciaPanel } from "../incidencias/tipos.ts";
import type { Capa } from "../unidades/tipos.ts";

export type { Capa };

/** Metadatos de cabecera del informe. Ver la cabecera del módulo: sin cifras físicas sin formatear. */
export interface ResumenSesionInforme {
  readonly nombreFichero: string;
  readonly formato: string;
  /** Ya formateada con su unidad (p. ej. «245,100 s»): duración es un INTERVALO, no un punto. */
  readonly duracionTexto: string;
  /** Cardinal, no magnitud: sin clase de conversión. */
  readonly muestras: number;
  /** Cardinal, no magnitud: sin clase de conversión. */
  readonly canales: number;
  /** Ya formateada en el locale e idioma del informe. */
  readonly generadoEnTexto: string;
}

/** Una dimensión con la unidad que se usó para mostrarla en ESTE informe, y por qué esa y no otra. */
export interface DimensionConUnidad {
  readonly dimensionEtiqueta: string;
  /** Etiqueta de la unidad YA resuelta (p. ej. "°C", "λ", "bar (rel)"). */
  readonly unidadEtiqueta: string;
  /** Capa de precedencia que decidió esta unidad (`docs/06` §6.9). Ver `plantilla.ts` para el texto. */
  readonly capa: Capa;
}

/** «Con las unidades usadas declaradas» — la mitad del título de la tarea que esto resuelve. */
export interface UnidadesUsadasInforme {
  /** Etiqueta del preset activo al generar el informe (`PresetInfo.etiqueta`). */
  readonly presetEtiqueta: string;
  readonly porDimension: readonly DimensionConUnidad[];
}

/**
 * Un gráfico ya renderizado, autocontenido: el mismo SVG (trazo PNG +
 * ejes vectoriales) que produce `exportar/exportar-imagen.ts#exportarComoSVG`.
 * Este módulo no dibuja nada — lo incrusta tal cual, como marcado inline. Ver
 * la cabecera del módulo, sección «dónde vive».
 */
export interface GraficoInforme {
  readonly titulo: string;
  /** Salida de `XMLSerializer.serializeToString` sobre un `<svg>` ya compuesto. Empieza por `<svg`. */
  readonly svgTexto: string;
}

/** Mismo contrato que consume `PanelDeIncidencias.actualizar` (F3-12): no se reinventa. */
export interface DatosIncidenciasInforme {
  readonly catalogo: readonly DetectorCatalogo[];
  readonly estados: readonly EstadoDetector[];
  readonly incidencias: readonly IncidenciaPanel[];
}

/** Una tirada ya resuelta a texto (F3-16). Ver la cabecera del módulo sobre `SeccionTiradas`. */
export interface TiradaInforme {
  /** Etiqueta de la clase YA traducida por quien llama (wot/ralentí/arranque/deceleración/crucero). */
  readonly clase: string;
  /** Instante de inicio, ya formateado (PUNTO en el eje de tiempo). */
  readonly inicioTexto: string;
  /** Duración, ya formateada (INTERVALO, no punto: ver la cabecera del módulo). */
  readonly duracionTexto: string;
}

/** Las tres respuestas honestas sobre tiradas. Ver la cabecera del módulo. */
export type SeccionTiradas =
  | { readonly tipo: "no_disponible" }
  | { readonly tipo: "vacia" }
  | { readonly tipo: "con_datos"; readonly tiradas: readonly TiradaInforme[] };

/** Todo lo que necesita `generarInformeSesionHtml` para componer el documento entero. */
export interface DatosInformeSesion {
  readonly resumen: ResumenSesionInforme;
  readonly unidades: UnidadesUsadasInforme;
  readonly incidencias: DatosIncidenciasInforme;
  readonly tiradas: SeccionTiradas;
  /** Vacío es válido: un informe sin gráficos sigue siendo un informe. */
  readonly graficos: readonly GraficoInforme[];
}
