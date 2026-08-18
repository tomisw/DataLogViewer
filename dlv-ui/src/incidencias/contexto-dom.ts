/**
 * La superficie de `document` que usa `panel-incidencias.ts`. Nada más.
 *
 * Mismo motivo que `cursor/contexto-dom.ts` y `paneles/contexto-dom.ts`
 * (ADR-006: «una superficie de API deliberadamente pequeña»): `document` y
 * `HTMLElement` reales cumplen esta interfaz estructuralmente, así que se
 * pasan sin adaptador; un doble de pruebas (`doble-dom.ts`) también la
 * cumple, y eso permite probar en Node —sin navegador, que es el entorno de
 * `vitest.config.ts`— qué nodos se crean, qué clases y texto se les pone, y
 * qué detector se pidió saltar al pulsar una fila.
 *
 * Deliberadamente duplicado en vez de importado de `paneles/contexto-dom.ts`
 * o `cursor/contexto-dom.ts`: cada componente de `dlv-ui` declara la suya
 * (ver la cabecera de `cursor/contexto-dom.ts`), y las tres difieren en la
 * superficie exacta que necesitan — esta es la única que necesita
 * `replaceChildren` (para rehacer la lista completa en cada `actualizar`,
 * ver la cabecera de `panel-incidencias.ts`) y un `addEventListener` de solo
 * `"click"`, sin *pointer events* de arrastre.
 */

/** Lo mínimo de `DOMTokenList` que usa este componente. */
export interface ClaseCSS {
  add(...clases: string[]): void;
}

/** Lo mínimo de `CSSStyleDeclaration` que usa este componente. */
export interface EstiloCSS {
  setProperty(nombre: string, valor: string): void;
}

/** El subconjunto de `HTMLElement` que usa `panel-incidencias.ts`. */
export interface ElementoDOM {
  readonly classList: ClaseCSS;
  readonly style: EstiloCSS;
  textContent: string;
  title: string;
  appendChild<T extends ElementoDOM>(hijo: T): T;
  replaceChildren(...hijos: readonly ElementoDOM[]): void;
  setAttribute(nombre: string, valor: string): void;
  addEventListener(tipo: "click", manejador: () => void): void;
}

export interface ContextoDOM {
  createElement(etiqueta: string): ElementoDOM;
}

/**
 * Adaptador sobre un `Document` de verdad. Mismo `as unknown as` que
 * `paneles/contexto-dom.ts#contextoDesdeDocumento` y por el mismo motivo:
 * `HTMLElement` cumple `ElementoDOM` de sobra, pero algunas de sus firmas
 * reales son más genéricas de lo que TypeScript puede derivar sin ayuda
 * (`addEventListener` acepta cualquier nombre de evento, no solo
 * `"click"`). Es el único sitio del módulo que lo necesita.
 */
export function contextoDesdeDocumento(documento: Pick<Document, "createElement">): ContextoDOM {
  return {
    createElement: (etiqueta: string): ElementoDOM =>
      documento.createElement(etiqueta) as unknown as ElementoDOM,
  };
}

/**
 * Igual que `elementoDesdeHtml` de `paneles/contexto-dom.ts`: adapta el
 * contenedor que ya existe y que pasa quien monta el panel en la aplicación
 * real (`montar`, más abajo en `panel-incidencias.ts`).
 */
export function elementoDesdeHtml(elemento: HTMLElement): ElementoDOM {
  return elemento as unknown as ElementoDOM;
}
