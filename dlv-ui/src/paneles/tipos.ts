/**
 * Contrato de datos de los paneles apilados (F1-26).
 *
 * Misma frontera que `render/tipos.ts` (ADR-006) y `ejes/tipos.ts` (F1-25):
 * este módulo coloca paneles, reparte alto entre ellos y dice qué canal está
 * en qué panel. **No dibuja series** (eso es `render/renderizador.ts`), **no
 * calcula ejes** (eso es `ejes/geometria.ts`) y no sabe qué es un canal más
 * allá de un identificador y una etiqueta — igual que `canales/tipos.ts`
 * reduce un canal a `CanalInfo` para el selector, aquí un canal es
 * `CanalEnPanel` y nada más: quien ensambla la lista (código que sí habla con
 * `dlv-api` y con el catálogo de unidades) es responsable de todo lo demás.
 *
 * El eje X compartido (el requisito central de la tarea) no aparece como un
 * campo aquí porque no es un dato que este módulo posea: es una garantía
 * estructural — todos los paneles reciben, del mismo contenedor, el mismo
 * `anchoContenidoPx` — que ofrece la clase de `paneles.ts` y que protege
 * `paneles.compartir-x.test.ts`. Quien dibuja cada panel (F1-23 + F1-25) usa
 * ese ancho para construir su propia `Vista`; si dos paneles calcularan su
 * ancho por separado (midiendo su propio `getBoundingClientRect`), una barra
 * de scroll o un redondeo de subpíxel en uno solo de ellos desincronizaría el
 * mapeo tiempo→píxel sin que nada en pantalla lo delate. Por eso el ancho se
 * mide una vez y se aplica igual a todos.
 */

import type { ContextoDOM } from "./contexto-dom.ts";

/** Un canal ya resuelto, tal como lo necesita la ficha de arrastre. */
export interface CanalEnPanel {
  /** Identificador estable: es lo que viaja en `CambioAsignacion`. */
  readonly id: string;
  /** Texto de la ficha. Ya en la unidad/idioma que decida quien la ensambla. */
  readonly etiqueta: string;
}

/** Definición inicial de un panel: su identidad y los canales que empieza mostrando. */
export interface DefinicionPanel {
  readonly id: string;
  readonly canales: readonly CanalEnPanel[];
}

/**
 * Lo que se informa tras soltar un canal en otro panel (o reordenarlo dentro
 * del mismo). `indice` es la posición final dentro de la lista de
 * `panelDestino`, para que quien escuche pueda reconstruir el orden exacto
 * sin volver a preguntar `canalesDe`.
 */
export interface CambioAsignacion {
  readonly canalId: string;
  readonly panelOrigen: string;
  readonly panelDestino: string;
  readonly indice: number;
}

/** Alturas de todos los paneles, en píxeles CSS, por identificador de panel. */
export type AlturasPaneles = ReadonlyMap<string, number>;

export interface OpcionesPaneles {
  /**
   * Alto mínimo de un panel, en píxeles CSS. Por omisión 60: sitio justo para
   * una cabecera de fichas y una franja de trazo, lo mínimo para que un panel
   * arrastrado casi a cero siga siendo un panel y no una línea invisible.
   */
  readonly alturaMinimaPx?: number;
  /**
   * Por omisión, `document` global (adaptado con `contextoDesdeDocumento`).
   * Inyectable para probar sin navegador con el doble de `doble-dom.ts`
   * (`crearContextoDomFalso`), que ya devuelve un `ContextoDOM`.
   */
  readonly documento?: ContextoDOM;
  /** Se llama tras cada arrastre de canal que termina en una reasignación real. */
  readonly alCambiarAsignacion?: (cambio: CambioAsignacion) => void;
  /** Se llama tras cada cambio de alturas (arrastre de divisor o recálculo de contenedor). */
  readonly alRedimensionar?: (alturasPx: AlturasPaneles) => void;
}
