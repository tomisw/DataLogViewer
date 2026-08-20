/**
 * Catálogo de textos en INGLÉS (F5-10).
 *
 * Tipado como `Record<ClaveTexto, string>` — no como `typeof TEXTOS_ES`, y la
 * diferencia es la que hace efectiva la decisión §1 del informe de la tarea
 * («qué pasa con una clave que falta»): con `Record`, TypeScript aplica
 * comprobación de propiedades exactas sobre este literal de objeto. Si
 * faltara una clave de `TEXTOS_ES`, `tsc --noEmit` falla con «falta la
 * propiedad X»; si sobrara una que `TEXTOS_ES` no tiene, falla con «X no
 * existe en el tipo». Las dos direcciones del desincronismo se detectan en
 * `npx tsc --noEmit`, antes de llegar a una prueba — y `catalogo.test.ts`
 * repite la misma comprobación en tiempo de ejecución (`Object.keys`) como
 * defensa adicional, por si algún día una clave se añadiera con `as` y se
 * saltara el tipo.
 *
 * Las traducciones no persiguen sonar como un hablante nativo en cada
 * matiz -- persiguen ser inequívocas para quien lee el instrumental en
 * inglés. Donde el español usa un guion largo para separar cláusulas (—) se
 * mantiene el mismo carácter: es puntuación, no idioma.
 */

import type { TEXTOS_ES } from "./textos.es.ts";

export const TEXTOS_EN: Record<keyof typeof TEXTOS_ES, string> = {
  "canales.buscarPlaceholder": "Search by name, semantic role, or ID…",
  "canales.mostrarInactivos": "show inactive",
  "canales.motivoConstante": "constant: does not change anywhere in the log",
  "canales.motivoVacio": "empty: the channel was never active in this log",
  "canales.constanteN": "{n} constant",
  "canales.vacioN": "{n} empty",
  "canales.ocultosPrefijo": "{n} channel(s) hidden",
  "canales.ocultosSufijo": "Enable it with “show inactive”.",

  "unidades.global": "Global",
  "unidades.heredarDelPreset": "— inherit from preset —",
  "unidades.heredar": "— inherit —",
  "unidades.sinConfirmarCrudo": "unconfirmed: shown raw, without a unit",
  "unidades.sinConversion": "no unit conversion (logarithmic or dimensionless scale)",
  "unidades.decimalSingular": "decimal",
  "unidades.decimalPlural": "decimals",
  "unidades.siNoSeFijaAqui": "if not set here,",
  "unidades.fijadoAqui": "set here",
  "unidades.heredadoPrefijo": "inherited:",

  "combustible.automatico": "— automatic (log / assumed) —",
  "combustible.manual": "— manual value —",
  "combustible.etiquetaCombustible": "Fuel",
  "combustible.etiquetaEstequiometria": "Stoichiometry",
  "combustible.placeholderManual": "e.g. 9.77",
  "combustible.errorManual": "not a valid number (> 0): the last valid manual value is kept",
  "combustible.supuestoPrefijo": "ASSUMED —",
  "combustible.elegidoAqui": "chosen here",
  "combustible.leidoDelLog": "read from the log",

  "incidencias.bannerSingular":
    "1 detector disabled — it is not known whether there are incidents, not that there are none",
  "incidencias.bannerPlural":
    "{n} detectors disabled — it is not known whether there are incidents, not that there are none",
  "incidencias.sinIncidencias": "No incidents.",
  "incidencias.sinIncidenciasActivos": "No incidents in the active detectors.",
  "incidencias.saltar": "Jump",
  "incidencias.saltarTitulo": "Jump to the instant it started ({instante})",

  "cursor.columnaCanal": "Channel",
  "cursor.columnaValor": "Value",
  "cursor.columnaNivel": "Level",

  "malla.cuenta": "samples",
  "malla.media": "mean",
  "malla.desviacionTipica": "standard deviation",
  "malla.minimo": "minimum",
  "malla.maximo": "maximum",
  "malla.sinDatos": "no data in this cell",
  "malla.pocaConfianza": "low confidence: few samples",

  "lambda.mapaError.unidadReciprocaDesactivado":
    "The λ error map cannot be shown in {unidad}: a difference does not admit a reciprocal conversion. Switch to λ or AFR to see it.",
  "lambda.mapaError.sinDatosParaEscala":
    "No cell has any data yet: there is no error to color.",

  "app.abrirLogSintetico": "Open synthetic log",
  "app.barraFuente": "source",
  "app.barraAbriendo": "opening…",
  "app.barraNCanales": "{n} channels",
  "app.mensajeVacio": "Select channels on the left to see them here.",
  "app.dobleCursorTitulo":
    "Dual cursor: click on the panels to set the anchor, and click again to remove it.",
};
