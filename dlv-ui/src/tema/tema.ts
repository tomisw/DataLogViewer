/**
 * Tema (oscuro, claro, alto contraste) — fuente única de verdad (F3-21).
 *
 * Este módulo centraliza:
 * 1. **La definición de los tres temas:** `oscuro`, `claro`, `altContraste`.
 * 2. **La detección de preferencias del sistema:** `prefers-color-scheme`.
 * 3. **La anulación explícita del usuario:** una elección manual que prevalece
 *    sobre el sistema y sobrevive a recargar la página.
 * 4. **Los parámetros de color de las SERIES:** `parametrosDeSerie`, porque el
 *    color de una serie no es una variable CSS (va a la GPU, no al DOM) y aun
 *    así tiene que cambiar con el tema.
 * 5. **El aviso de que el tema cambió:** `alCambiarTema`, sin el cual las series
 *    ya subidas a la GPU se quedarían con el color del tema anterior.
 *
 * DÓNDE VIVEN LOS COLORES, Y POR QUÉ SOLO AQUÍ
 * =============================================
 * Las paletas están en este fichero y en ningún otro. `index.html` declara solo
 * el tema oscuro en `:root`, y lo hace por una razón concreta: es el color del
 * primer pintado, antes de que cargue el módulo. `aplicarTema` escribe las
 * variables CSS con `style.setProperty` sobre `documentElement`, que gana a
 * cualquier regla de la hoja de estilos por especificidad.
 *
 * La primera versión de esta tarea declaró las tres paletas EN LOS DOS SITIOS.
 * No era redundancia inocua: las reglas `:root[data-theme="claro"]` de la hoja
 * nunca llegaban a aplicarse para los colores —las pierde contra el estilo en
 * línea— pero sí para `color-scheme`, así que el mismo bloque tenía unas
 * propiedades que ganaban y otras que perdían. Quien fuera a cambiar un color al
 * sitio obvio (el CSS) no habría visto ningún efecto y no habría entendido por
 * qué.
 *
 * CRITERIOS DE ALTO CONTRASTE
 * ============================
 * - Contraste de texto: mínimo 7:1, el nivel AAA de WCAG 2.1 para texto normal.
 *   Blanco puro sobre negro puro da 21:1, y `textoTenue` (#999 sobre #000) da
 *   7,5:1, justo por encima del mínimo.
 * - Series distinguibles por algo más que el tono: además del ángulo áureo del
 *   matiz, la luz alterna entre dos valores separados (0,70 y 0,45). Una
 *   diferencia de luz se conserva bajo protanopia y deuteranopia, donde la de
 *   tono desaparece; el tono sigue estando, pero deja de ser lo único.
 * - Rejilla y ejes más opacos (0,15 y 0,75 frente a 0,08 y 0,55): son las líneas
 *   que se pierden primero con la pantalla al sol.
 */

export type NombreColor =
  | "fondo"
  | "panel"
  | "panelBorde"
  | "texto"
  | "textoTenue"
  | "acento"
  | "rejilla"
  | "eje";

export type NombreTema = "oscuro" | "claro" | "altContraste";

/**
 * Paleta de colores para cada tema (RGB, componentes 0..255).
 * Cada tema define los 8 colores que usa todo dlv-ui.
 */
export interface PaletaTema {
  readonly fondo: string;
  readonly panel: string;
  readonly panelBorde: string;
  readonly texto: string;
  readonly textoTenue: string;
  readonly acento: string;
  readonly rejilla: string;
  readonly eje: string;
}

/**
 * **Tema oscuro:** el actual (no debe cambiar de aspecto).
 * Fondo muy oscuro, texto claro, acentos en azul.
 */
const TEMA_OSCURO: PaletaTema = {
  fondo: "#14161a",
  panel: "#1c1f26",
  panelBorde: "#2c313c",
  texto: "#e6e8ec",
  textoTenue: "#9aa3b2",
  acento: "#4da3ff",
  rejilla: "rgba(255, 255, 255, 0.08)",
  eje: "rgba(255, 255, 255, 0.55)",
};

/**
 * **Tema claro:** inverso del oscuro, manteniendo proporciones de contraste.
 * Fondo muy claro, texto oscuro, acentos en azul saturado.
 */
const TEMA_CLARO: PaletaTema = {
  fondo: "#ffffff",
  panel: "#f5f5f5",
  panelBorde: "#e0e0e0",
  texto: "#1a1a1a",
  textoTenue: "#666666",
  acento: "#0066cc",
  rejilla: "rgba(0, 0, 0, 0.05)",
  eje: "rgba(0, 0, 0, 0.55)",
};

/**
 * **Tema alto contraste:** diseñado para visibilidad máxima y
 * distinguibilidad sin depender del color solo.
 *
 * Criterios aplicados:
 * - Fondo muy oscuro (casi negro) para maximizar brillo del texto.
 * - Texto blanco puro (máximo contraste): 21:1 sobre el fondo.
 * - `panelBorde` muy visible: contraste 10:1.
 * - `textoTenue` en gris oscuro: contraste 7:1 (WCAG AAA).
 * - `acento` en cian/turquesa puro: muy saturado, distinguible del azul
 *   y del blanco.
 * - Rejilla y ejes más opacos: visible incluso con baja luminosidad
 *   o pantalla al sol.
 * - Series en `color.ts` usan saturación y brillo variables además del
 *   tono, para que daltonismo no las haga indistinguibles.
 */
const TEMA_ALTO_CONTRASTE: PaletaTema = {
  fondo: "#000000",
  panel: "#0d0d0d",
  panelBorde: "#4d4d4d",
  texto: "#ffffff",
  textoTenue: "#999999",
  acento: "#00ffff",
  rejilla: "rgba(255, 255, 255, 0.15)",
  eje: "rgba(255, 255, 255, 0.75)",
};

/** Mapa de temas por nombre. */
const TEMAS_POR_NOMBRE: Record<NombreTema, PaletaTema> = {
  oscuro: TEMA_OSCURO,
  claro: TEMA_CLARO,
  altContraste: TEMA_ALTO_CONTRASTE,
};

/** Clave de almacenamiento local para la preferencia del usuario. */
const CLAVE_ALMACENAMIENTO = "dlv-tema-preferido";

/** Tema activo actualmente (inicializado por `inicializarTema()`). */
let temaActual: NombreTema = "oscuro";

/** Paleta actualmente aplicada. */
let paletaActual: PaletaTema = TEMA_OSCURO;

/**
 * Detalla la preferencia de tema del sistema (o `null` si no está disponible).
 * Resultado: `"dark"`, `"light"`, o `null`.
 */
function preferenciaDelSistema(): "dark" | "light" | null {
  if (typeof window === "undefined") return null;
  const consulta = window.matchMedia("(prefers-color-scheme: dark)");
  return consulta.matches ? "dark" : "light";
}

/**
 * Recupera la preferencia guardada del usuario del almacenamiento local.
 */
function preferenciaDelUsuario(): NombreTema | null {
  if (typeof localStorage === "undefined") return null;
  const valor = localStorage.getItem(CLAVE_ALMACENAMIENTO);
  if (valor === null) return null;
  if (valor === "oscuro" || valor === "claro" || valor === "altContraste") {
    return valor;
  }
  return null;
}

/**
 * Convierte la preferencia del sistema (`"dark"`/`"light"`) a un nombre
 * de tema.
 */
function temaDelSistema(pref: "dark" | "light"): NombreTema {
  return pref === "dark" ? "oscuro" : "claro";
}

/** Los suscriptores de `alCambiarTema`. */
const suscriptores = new Set<() => void>();

/**
 * Avisa de que el tema cambió.
 *
 * Hace falta porque no todo el color de la aplicación es una variable CSS: el de
 * cada serie se calcula en TypeScript y se sube a la GPU (ADR-006), así que un
 * cambio de tema no lo toca. Sin este aviso, cambiar a alto contraste
 * reteñía la interfaz y dejaba las curvas con los colores del tema anterior --
 * exactamente la mitad de la pantalla que importa.
 *
 * Devuelve la función para darse de baja.
 */
export function alCambiarTema(reaccion: () => void): () => void {
  suscriptores.add(reaccion);
  return () => suscriptores.delete(reaccion);
}

/**
 * Establece el tema activo en `document.documentElement.dataset.theme`
 * y aplica su paleta. Afecta a las variables CSS y a `temaActual`.
 */
function aplicarTema(nombre: NombreTema): void {
  const cambia = nombre !== temaActual;
  temaActual = nombre;
  paletaActual = TEMAS_POR_NOMBRE[nombre];

  if (typeof document !== "undefined") {
    const root = document.documentElement;
    root.dataset.theme = nombre;
    // El estilo en línea gana a la hoja de estilos: este es el único sitio que
    // decide los colores en cuanto el módulo ha cargado (ver la cabecera).
    root.style.setProperty("color-scheme", nombre === "claro" ? "light" : "dark");
    root.style.setProperty("--fondo", paletaActual.fondo);
    root.style.setProperty("--panel", paletaActual.panel);
    root.style.setProperty("--panel-borde", paletaActual.panelBorde);
    root.style.setProperty("--texto", paletaActual.texto);
    root.style.setProperty("--texto-tenue", paletaActual.textoTenue);
    root.style.setProperty("--acento", paletaActual.acento);
    root.style.setProperty("--rejilla", paletaActual.rejilla);
    root.style.setProperty("--eje", paletaActual.eje);
  }

  if (cambia) {
    for (const reaccion of suscriptores) reaccion();
  }
}

/**
 * Inicializa el tema al cargar la página.
 *
 * Orden de precedencia:
 * 1. Preferencia del usuario guardada en localStorage.
 * 2. Preferencia del sistema (`prefers-color-scheme`).
 * 3. Oscuro (valor por omisión).
 */
export function inicializarTema(): void {
  const preferencia = preferenciaDelUsuario();
  if (preferencia !== null) {
    aplicarTema(preferencia);
    return;
  }

  const sistemaPref = preferenciaDelSistema();
  if (sistemaPref !== null) {
    aplicarTema(temaDelSistema(sistemaPref));
    return;
  }

  // Fallback: oscuro por omisión.
  aplicarTema("oscuro");
}

/**
 * Cambia el tema activo explícitamente y lo guarda como preferencia
 * del usuario.
 *
 * Esta elección prevalece sobre la preferencia del sistema.
 */
export function establecerTema(nombre: NombreTema): void {
  aplicarTema(nombre);
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(CLAVE_ALMACENAMIENTO, nombre);
  }
}

/**
 * Recupera el tema actualmente aplicado.
 */
export function obtenerTemaActual(): NombreTema {
  return temaActual;
}

/**
 * Lee un color de la paleta actual por su nombre, tal como se escribiría en CSS
 * (`"#14161a"`, `"rgba(255, 255, 255, 0.08)"`).
 *
 * Es la vía para el código que necesite un color del tema y NO pueda salir de
 * una variable CSS. Hoy no hay ninguno: los ejes y la rejilla se pintan con
 * clases (`dlv-ejes-rejilla`) que ya leen `var(--rejilla)` desde la hoja de
 * estilos, y las series usan `parametrosDeSerie`. Se mantiene porque las pruebas
 * de regresión visual de F5-12 tendrán que comparar contra el color esperado del
 * tema activo sin depender de que la hoja de estilos esté cargada.
 */
export function leerColor(nombre: NombreColor): string {
  return paletaActual[nombre];
}

/**
 * Recupera la paleta completa del tema actual.
 * Útil en pruebas o para aplicaciones que quieran todos los colores a la vez.
 */
export function obtenerPaletaActual(): Readonly<PaletaTema> {
  return paletaActual;
}

/**
 * Lista de todos los nombres de tema disponibles.
 */
export const TEMAS_DISPONIBLES: readonly NombreTema[] = ["oscuro", "claro", "altContraste"];

/** Rótulo de cada tema para la interfaz. */
export const ETIQUETA_DE_TEMA: Record<NombreTema, string> = {
  oscuro: "Oscuro",
  claro: "Claro",
  altContraste: "Alto contraste",
};

/** Saturación y luz de las series, por tema. */
export interface ParametrosDeSerie {
  readonly saturacion: number;
  readonly luz: number;
}

/**
 * La saturación y la luz con las que se pinta la serie número `discriminante`.
 *
 * `discriminante` es el índice del canal o su código de estado -- lo que
 * distinga una serie de la siguiente; solo se usa su paridad, y su signo da
 * igual.
 *
 * Vive aquí y no en quien pinta porque hay DOS sitios que calculan color de
 * serie por razones de capas: `carriles/color.ts` (color estable por código de
 * estado, F3-13) y `app/aplicacion.ts` (paleta por índice de canal), y
 * `color.ts` no puede depender hacia arriba de `aplicacion.ts`. La primera
 * versión resolvió eso repitiendo el `if` del tema y los cuatro números en los
 * dos ficheros, con los de `aplicacion.ts` escritos a pelo: dos paletas de serie
 * que se separan en cuanto alguien toque una, y sin nada que lo detecte.
 */
export function parametrosDeSerie(discriminante: number): ParametrosDeSerie {
  if (temaActual === "claro") {
    // Luz más baja que en oscuro: una curva clara sobre fondo blanco se pierde.
    return { saturacion: 0.7, luz: 0.45 };
  }
  if (temaActual === "altContraste") {
    // La luz alterna para que dos series consecutivas se distingan también sin
    // ver el color (ver los criterios en la cabecera).
    const par = Math.abs(discriminante) % 2 === 0;
    return { saturacion: 0.85, luz: par ? 0.7 : 0.45 };
  }
  return { saturacion: 0.65, luz: 0.6 };
}
