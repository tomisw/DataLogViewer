/**
 * Catálogo de textos en ESPAÑOL (F5-10). Es el catálogo CANÓNICO: el que
 * define qué claves existen (`ClaveTexto` en `catalogo.ts` sale de
 * `keyof typeof TEXTOS_ES`) y el que usa `t()` como último recurso si una
 * clave faltara en otro idioma (ver la cabecera de `catalogo.ts`, decisión
 * §1). Por eso cada valor de aquí es exactamente el texto que ya estaba
 * escrito a mano en cada componente antes de esta tarea -- extraer cadenas no
 * es reescribirlas, y así ninguna prueba que comparara ese texto tiene que
 * cambiar solo porque ahora vive en un catálogo.
 *
 * QUÉ NO ESTÁ AQUÍ, Y POR QUÉ (decisión §3 del informe de la tarea)
 * ====================================================================
 * - Los NOMBRES DE CANAL (`Coolant Temperature`, …): vienen del log tal cual
 *   los escribió la ECU. Traducirlos rompería la correspondencia entre lo que
 *   se ve en pantalla y lo que dice el fichero original -- exactamente lo que
 *   `docs/01-formato-log.md` documenta medido sobre los logs reales.
 * - Los IDENTIFICADORES DE ROL (`coolant_temp`, `oil_pressure`, …) y de UNIDAD
 *   (`degC`, `kPa`, …): son claves técnicas de `data/roles.toml` y
 *   `data/units.toml`. Traducir la clave, no solo su etiqueta, desincroniza
 *   el código de esos ficheros -- que son datos del propietario, no texto de
 *   interfaz (regla 2 de `CLAUDE.md`).
 * - `etiquetaDeSeveridad`/`etiquetaDeSeveridadCatalogo` (`incidencias/
 *   severidad.ts`): capitalizan el literal de severidad SIN tabla de
 *   traducción aparte, a propósito (ver la cabecera de ese módulo y su
 *   prueba «capitaliza el literal tal cual, sin tabla de traducción aparte»).
 *   Añadir aquí una traducción por severidad iría directamente contra esa
 *   decisión ya tomada y ya probada.
 */

export const TEXTOS_ES = {
  "canales.buscarPlaceholder": "Buscar por nombre, rol semántico o ID…",
  "canales.mostrarInactivos": "mostrar inactivos",
  "canales.motivoConstante": "constante: no cambia en todo el log",
  "canales.motivoVacio": "vacío: el canal no se activó en este log",
  "canales.constanteN": "{n} constante(s)",
  "canales.vacioN": "{n} vacío(s)",
  "canales.ocultosPrefijo": "{n} canal(es) oculto(s)",
  "canales.ocultosSufijo": "Actívalo con «mostrar inactivos».",

  "unidades.global": "Global",
  "unidades.heredarDelPreset": "— heredar del preset —",
  "unidades.heredar": "— heredar —",
  "unidades.sinConfirmarCrudo": "sin confirmar: se muestra en crudo, sin unidad",
  "unidades.sinConversion": "sin conversión de unidad (escala logarítmica o adimensional)",
  "unidades.decimalSingular": "decimal",
  "unidades.decimalPlural": "decimales",
  "unidades.siNoSeFijaAqui": "si no se fija aquí,",
  "unidades.fijadoAqui": "fijado aquí",
  "unidades.heredadoPrefijo": "heredado:",

  "combustible.automatico": "— automático (log / supuesto) —",
  "combustible.manual": "— valor manual —",
  "combustible.etiquetaCombustible": "Combustible",
  "combustible.etiquetaEstequiometria": "Estequiometría",
  "combustible.placeholderManual": "p. ej. 9,77",
  "combustible.errorManual": "no es un número válido (> 0): se mantiene el último valor manual válido",
  "combustible.supuestoPrefijo": "SUPUESTO —",
  "combustible.elegidoAqui": "elegido aquí",
  "combustible.leidoDelLog": "leído del log",

  "incidencias.bannerSingular":
    "1 detector desactivado — no se sabe si hay incidencias, no que no las haya",
  "incidencias.bannerPlural":
    "{n} detectores desactivados — no se sabe si hay incidencias, no que no las haya",
  "incidencias.sinIncidencias": "Sin incidencias.",
  "incidencias.sinIncidenciasActivos": "Sin incidencias en los detectores activos.",
  "incidencias.saltar": "Saltar",
  "incidencias.saltarTitulo": "Saltar al instante en que empezó ({instante})",

  "cursor.columnaCanal": "Canal",
  "cursor.columnaValor": "Valor",
  "cursor.columnaNivel": "Nivel",

  "malla.cuenta": "muestras",
  "malla.media": "media",
  "malla.desviacionTipica": "desviación típica",
  "malla.minimo": "mínimo",
  "malla.maximo": "máximo",
  "malla.sinDatos": "sin datos en esta celda",
  "malla.pocaConfianza": "confianza baja: pocas muestras",

  "lambda.mapaError.unidadReciprocaDesactivado":
    "El mapa de error de λ no se puede mostrar en {unidad}: una diferencia no admite una conversión recíproca. Cambia a λ o AFR para verlo.",
  "lambda.mapaError.sinDatosParaEscala":
    "No hay ninguna celda con datos: no hay error que colorear todavía.",

  "comparacion.mapa.bordesIncompatibles":
    "Los dos logs no se agregaron con la misma malla: los bordes de {eje} no coinciden. Vuelve a agregar los dos con los mismos bordes explícitos antes de compararlos.",
  "comparacion.mapa.unidadReciprocaDesactivado":
    "La comparación no se puede mostrar en {unidad}: una diferencia entre dos logs no admite una conversión recíproca. Cambia a una unidad lineal para verla.",
  "comparacion.mapa.sinDatosParaEscala":
    "Ninguna celda tiene datos en los dos logs a la vez: no hay diferencia que colorear todavía.",

  "app.abrirLogSintetico": "Abrir log sintético",
  "app.barraFuente": "fuente",
  "app.barraAbriendo": "abriendo…",
  "app.barraNCanales": "{n} canales",
  "app.mensajeVacio": "Selecciona canales en la izquierda para verlos aquí.",
  "app.dobleCursorTitulo":
    "Doble cursor: haz clic sobre los paneles para fijar el ancla, y otro clic para quitarla.",
} as const;
