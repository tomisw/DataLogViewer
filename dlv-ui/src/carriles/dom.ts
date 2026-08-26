/**
 * La superficie de DOM/SVG que necesita `pintarCarril`. Nada más.
 *
 * Mismo motivo que `unidades/dom.ts` (léase su cabecera primero: es el mismo
 * patrón, aplicado a SVG en vez de a HTML): `vitest.config.ts` corre en
 * `environment: "node"`, sin DOM global, y este proyecto no tiene jsdom ni
 * happy-dom instalados. Añadir uno para un componente de 5 puntos sería meter
 * una dependencia nueva que la tarea prohíbe explícitamente; en vez de eso,
 * `carril-estado.ts` depende de `FabricaSvg`, una interfaz mínima, y
 * `dom-falso.ts` la implementa con objetos planos para las pruebas.
 *
 * Por qué no reutilizar `unidades/FabricaDom` tal cual: sus nodos son
 * `document.createElement("div"/"span"/"select"/"option")`, del espacio de
 * nombres HTML. Un `<rect>` o un `<text>` creados así no son SVG de verdad —
 * `document.createElement("rect")` da un `HTMLUnknownElement` que no se pinta
 * — hace falta `document.createElementNS` con el espacio de nombres SVG, así
 * que la fábrica es otra, aunque la forma sea deliberadamente parecida.
 */

const NS_SVG = "http://www.w3.org/2000/svg";

export interface ClaseCSS {
  add(...clases: string[]): void;
}

export interface ElementoSvg {
  appendChild(hijo: ElementoSvg): ElementoSvg;
  /** Vacía y sustituye los hijos en un solo paso: así se repinta sin acumular nodos de la llamada anterior. */
  replaceChildren(...hijos: ElementoSvg[]): void;
  setAttribute(nombre: string, valor: string): void;
  readonly classList: ClaseCSS;
  textContent: string;
}

/**
 * Las etiquetas SVG que construyen los carriles. `crearSvg` se añadió en
 * F3-14: un carril de máscara de bits apila hasta 32 mini-carriles, y cada
 * uno se pinta con `pintarCarril` (F3-13) SIN modificarlo -- un `<svg>`
 * anidado, posicionado con `x`/`y`, le da a cada bit su propio viewport
 * dentro del carril apilado (`mascara-bits.ts`), que es exactamente lo que
 * permite reutilizar `pintarCarril` entero en vez de duplicar su lógica de
 * bandas y transiciones para el caso "apilado".
 */
export interface FabricaSvg {
  crearG(): ElementoSvg;
  crearRect(): ElementoSvg;
  crearText(): ElementoSvg;
  crearSvg(): ElementoSvg;
}

/**
 * Adaptador sobre un `Document` de verdad. Quien monte el componente en la
 * aplicación llama a `fabricaSvgDesdeDocumento(document)` y a
 * `elementoSvgDesdeNodo(miSvg)` sobre el `<svg>` ya existente en la página —
 * igual que `ejes.ts` recibe un `SVGSVGElement` ya creado por quien monta el
 * panel.
 */
export function fabricaSvgDesdeDocumento(documento: Pick<Document, "createElementNS">): FabricaSvg {
  return {
    // `as unknown as ElementoSvg`: mismo motivo que `unidades/dom.ts` — los
    // métodos que usa este módulo (`appendChild`, `replaceChildren`,
    // `setAttribute`, `classList.add`, `textContent`) existen todos de
    // verdad en un `SVGElement`, pero sus firmas reales son más genéricas de
    // lo que TypeScript deriva sin ayuda.
    crearG: () => documento.createElementNS(NS_SVG, "g") as unknown as ElementoSvg,
    crearRect: () => documento.createElementNS(NS_SVG, "rect") as unknown as ElementoSvg,
    crearText: () => documento.createElementNS(NS_SVG, "text") as unknown as ElementoSvg,
    crearSvg: () => documento.createElementNS(NS_SVG, "svg") as unknown as ElementoSvg,
  };
}

/** Envuelve un `SVGElement` real (el `<svg>` contenedor que ya existe en la página) como `ElementoSvg`. */
export function elementoSvgDesdeNodo(nodo: SVGElement): ElementoSvg {
  return nodo as unknown as ElementoSvg;
}
