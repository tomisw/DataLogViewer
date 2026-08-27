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

  "mascaraBits.etiquetaBit": "bit {n}",
  "mascaraBits.mostrarInactivos": "mostrar bits inactivos",
  "mascaraBits.ocultosPrefijo": "{n} de {total} bits ocultos: nunca se activaron en este log.",
  "mascaraBits.ocultosSufijo": "Actívalo con «mostrar bits inactivos».",

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

  "encendido.mapaAvance.sinDatosParaEscala":
    "No hay ninguna celda con datos: no hay avance que colorear todavía.",

  "knock.mapaDensidad.sinDatosParaEscala":
    "No hay ninguna celda con datos: no hay densidad de knock que colorear todavía.",

  "informe.tituloDocumento": "Informe de sesión — {nombre}",
  "informe.generadoEl": "Generado el {fecha}",
  "informe.seccionResumen": "Resumen",
  "informe.campoFormato": "Formato",
  "informe.campoDuracion": "Duración",
  "informe.campoMuestras": "Muestras",
  "informe.campoCanales": "Canales",
  "informe.seccionUnidades": "Unidades usadas",
  "informe.preset": "Preset activo: {preset}",
  "informe.columnaDimension": "Dimensión",
  "informe.columnaUnidad": "Unidad",
  "informe.columnaOrigen": "Origen",
  "informe.columnaSeveridad": "Severidad",
  "informe.columnaDetector": "Detector",
  "informe.origenCanal": "anulación de canal",
  "informe.origenPerfil": "preferencia del perfil activo",
  "informe.origenPreset": "preset activo",
  "informe.origenCanonica": "unidad canónica (sin capa más específica)",
  "informe.seccionIncidencias": "Incidencias",
  "informe.seccionTiradas": "Tiradas",
  "informe.tiradasNoDisponibles":
    "La segmentación automática de tiradas (F3-16) todavía no está conectada a esta vista: esta sección se deja así a propósito, en vez de rellenarla con datos inventados.",
  "informe.tiradasSinDatos": "No se detectó ninguna tirada a plena carga, ralentí, arranque, deceleración ni crucero en esta sesión.",
  "informe.columnaClaseTirada": "Clase",
  "informe.columnaInicioTirada": "Inicio",
  "informe.columnaDuracionTirada": "Duración",
  "informe.seccionGraficos": "Gráficos",
  "informe.sinGraficos": "Este informe no incluye gráficos.",
  "informe.pie":
    "Informe autocontenido: no depende de ninguna conexión de red ni de tener DataLogViewer instalado para abrirse.",

  "app.abrirLogSintetico": "Abrir log sintético",
  "app.barraFuente": "fuente",
  "app.barraAbriendo": "abriendo…",
  "app.barraNCanales": "{n} canales",
  "app.mensajeVacio": "Selecciona canales en la izquierda para verlos aquí.",
  "app.dobleCursorTitulo":
    "Doble cursor: haz clic sobre los paneles para fijar el ancla, y otro clic para quitarla.",

  "perfiles.origenFabrica": "de fábrica",
  "perfiles.origenUsuario": "tuyo",
  "perfiles.avisoFabrica":
    "Este perfil es de fábrica: no se puede editar directamente. Duplícalo para personalizarlo — tus cambios sobrevivirán a la próxima actualización.",
  "perfiles.nombre": "Nombre",
  "perfiles.descripcion": "Descripción",
  "perfiles.duplicar": "Duplicar",
  "perfiles.duplicarParaEditar": "Duplicar para editar",
  "perfiles.limites": "Límites de alerta",
  "perfiles.sinLimites": "Este perfil no declara límites de alerta.",
  "perfiles.limiteAviso": "aviso",
  "perfiles.limiteCritico": "crítico",
  "perfiles.limiteBandaCentro": "centro",
  "perfiles.limiteBandaSemiancho": "± ancho",
  "perfiles.limiteBandaMinimo": "mínimo",
  "perfiles.limiteBandaMaximo": "máximo",
  "perfiles.limiteCurvaNoEditable": "curva en función de «{rol}»: no editable aquí",
  "perfiles.importarBoton": "Cargar",
  "perfiles.importarError": "No se puede importar: {mensaje}",
  "perfiles.exportar": "Exportar",
  "perfiles.exportarEtiqueta": "Texto del .dlvprofile (cópialo o guárdalo como fichero suelto)",
  "perfiles.avisoSinGuardar":
    "Esta pestaña no guarda nada por su cuenta: dlv-api todavía no expone un punto para persistir un perfil (falta /comandos/perfil*). Usa «Exportar» para copiar el .dlvprofile resultante y guardarlo tú mismo como fichero; cualquier cambio no exportado se pierde al cambiar de pestaña o cerrar la aplicación.",

  "onboarding.propuestaAviso": "Perfil sugerido: «{perfil}» — {disponibles} de {total} roles disponibles.",
  "onboarding.propuestaFaltan": "Faltan: {roles}.",
  "onboarding.propuestaAceptar": "Usar este perfil",
  "onboarding.propuestaDescartar": "No, gracias",
  "onboarding.sinPerfilAviso":
    "Ningún perfil de fábrica encaja con este log: se muestran los canales habituales.",

  "paralela.dimensionesIncompatibles":
    "«{etiquetaA}» y «{etiquetaB}» no se pueden superponer: son dimensiones físicas distintas ({dimensionA} y {dimensionB}). Elige el mismo canal (o uno de la misma dimensión) en los dos logs antes de compararlos.",
} as const;
