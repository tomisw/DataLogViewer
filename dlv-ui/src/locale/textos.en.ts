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

  "mascaraBits.etiquetaBit": "bit {n}",
  "mascaraBits.mostrarInactivos": "show inactive bits",
  "mascaraBits.ocultosPrefijo": "{n} of {total} bits hidden: never active in this log.",
  "mascaraBits.ocultosSufijo": "Enable it with “show inactive bits”.",

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

  "comparacion.mapa.bordesIncompatibles":
    "The two logs were not aggregated on the same grid: the {eje} bounds do not match. Re-aggregate both with the same explicit bounds before comparing them.",
  "comparacion.mapa.unidadReciprocaDesactivado":
    "The comparison cannot be shown in {unidad}: a difference between two logs does not admit a reciprocal conversion. Switch to a linear unit to see it.",
  "comparacion.mapa.sinDatosParaEscala":
    "No cell has data in both logs at once: there is no difference to color yet.",

  "encendido.mapaAvance.sinDatosParaEscala":
    "No cell has any data yet: there is no ignition advance to color.",

  "knock.mapaDensidad.sinDatosParaEscala":
    "No cell has any data yet: there is no knock density to color.",

  "informe.tituloDocumento": "Session report — {nombre}",
  "informe.generadoEl": "Generated on {fecha}",
  "informe.seccionResumen": "Summary",
  "informe.campoFormato": "Format",
  "informe.campoDuracion": "Duration",
  "informe.campoMuestras": "Samples",
  "informe.campoCanales": "Channels",
  "informe.seccionUnidades": "Units used",
  "informe.preset": "Active preset: {preset}",
  "informe.columnaDimension": "Dimension",
  "informe.columnaUnidad": "Unit",
  "informe.columnaOrigen": "Source",
  "informe.columnaSeveridad": "Severity",
  "informe.columnaDetector": "Detector",
  "informe.origenCanal": "channel override",
  "informe.origenPerfil": "active profile preference",
  "informe.origenPreset": "active preset",
  "informe.origenCanonica": "canonical unit (no more specific layer)",
  "informe.seccionIncidencias": "Incidents",
  "informe.seccionTiradas": "Runs",
  "informe.tiradasNoDisponibles":
    "Automatic run segmentation (F3-16) is not wired into this view yet: this section is left as-is on purpose, instead of being filled with made-up data.",
  "informe.tiradasSinDatos": "No wide-open-throttle, idle, start-up, deceleration, or cruise run was detected in this session.",
  "informe.columnaClaseTirada": "Class",
  "informe.columnaInicioTirada": "Start",
  "informe.columnaDuracionTirada": "Duration",
  "informe.seccionGraficos": "Charts",
  "informe.sinGraficos": "This report does not include any charts.",
  "informe.pie":
    "Self-contained report: it does not depend on any network connection or on having DataLogViewer installed to open it.",

  "app.abrirLogSintetico": "Open synthetic log",
  "app.barraFuente": "source",
  "app.barraAbriendo": "opening…",
  "app.barraNCanales": "{n} channels",
  "app.mensajeVacio": "Select channels on the left to see them here.",
  "app.dobleCursorTitulo":
    "Dual cursor: click on the panels to set the anchor, and click again to remove it.",

  "perfiles.origenFabrica": "factory",
  "perfiles.origenUsuario": "yours",
  "perfiles.avisoFabrica":
    "This is a factory profile: it can't be edited directly. Duplicate it to customize it — your changes will survive the next update.",
  "perfiles.nombre": "Name",
  "perfiles.descripcion": "Description",
  "perfiles.duplicar": "Duplicate",
  "perfiles.duplicarParaEditar": "Duplicate to edit",
  "perfiles.limites": "Alert limits",
  "perfiles.sinLimites": "This profile declares no alert limits.",
  "perfiles.limiteAviso": "warning",
  "perfiles.limiteCritico": "critical",
  "perfiles.limiteBandaCentro": "center",
  "perfiles.limiteBandaSemiancho": "± width",
  "perfiles.limiteBandaMinimo": "minimum",
  "perfiles.limiteBandaMaximo": "maximum",
  "perfiles.limiteCurvaNoEditable": "curve as a function of “{rol}”: not editable here",
  "perfiles.importarBoton": "Load",
  "perfiles.importarError": "Can't import: {mensaje}",
  "perfiles.exportar": "Export",
  "perfiles.exportarEtiqueta": "The .dlvprofile text (copy it or save it as a standalone file)",

  "onboarding.propuestaAviso": "Suggested profile: “{perfil}” — {disponibles} of {total} roles available.",
  "onboarding.propuestaFaltan": "Missing: {roles}.",
  "onboarding.propuestaAceptar": "Use this profile",
  "onboarding.propuestaDescartar": "No, thanks",
  "onboarding.sinPerfilAviso":
    "No factory profile matches this log: showing the usual channels instead.",
};
