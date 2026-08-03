/**
 * La superficie de `document` que usa `PanelesApilados`. Nada más.
 *
 * Mismo motivo que `cursor/contexto-dom.ts` y `render/contexto.ts` (ADR-006
 * lo llama «una superficie de API deliberadamente pequeña»): `document` real
 * cumple esta interfaz estructuralmente, así que se pasa sin adaptador, y un
 * doble de pruebas (`doble-dom.ts`) también la cumple — lo que permite
 * probar en Node, sin navegador, la parte que sí se puede probar sin uno: qué
 * nodos se crean, qué clases y estilos se aplican, y qué decide la lógica de
 * arrastre ante una secuencia de eventos de puntero. Lo que un doble nunca
 * puede decir es si el usuario ve de verdad el panel destacado antes de
 * soltar — eso es un juicio visual y queda fuera de una prueba unitaria,
 * igual que `cursor.ts` no prueba si la línea "se ve".
 *
 * A diferencia de `cursor/contexto-dom.ts` (que solo crea nodos: el cursor no
 * escucha al usuario), este componente necesita *pointer events* y
 * `getBoundingClientRect` para resolver el arrastre, así que la interfaz es
 * un poco más ancha. Sigue siendo mucho más pequeña que `HTMLElement`
 * completo: no hay `querySelector`, no hay `innerHTML`, no hay `dataset`
 * tipado — todo lo que este módulo necesita leer o escribir de un elemento ya
 * lo guarda él mismo en sus propias estructuras, nunca lo vuelve a preguntar
 * al DOM.
 */

export interface RectanguloPx {
  readonly top: number;
  readonly bottom: number;
  readonly left: number;
  readonly right: number;
}

/** Los cuatro campos de un `PointerEvent` que usa este módulo. Nada más. */
export interface EventoPuntero {
  readonly clientX: number;
  readonly clientY: number;
  readonly pointerId: number;
  readonly button: number;
  preventDefault(): void;
}

export type TipoEventoPuntero = "pointerdown" | "pointermove" | "pointerup" | "pointercancel";

export interface ClaseCSS {
  add(...clases: string[]): void;
  remove(...clases: string[]): void;
  contains(clase: string): boolean;
}

export interface EstiloCSS {
  setProperty(nombre: string, valor: string): void;
}

/** El subconjunto de `HTMLElement` que usa `paneles.ts`. */
export interface ElementoDOM {
  readonly classList: ClaseCSS;
  readonly style: EstiloCSS;
  textContent: string;
  appendChild<T extends ElementoDOM>(hijo: T): T;
  remove(): void;
  setAttribute(nombre: string, valor: string): void;
  getBoundingClientRect(): RectanguloPx;
  addEventListener(tipo: TipoEventoPuntero, manejador: (evento: EventoPuntero) => void): void;
  setPointerCapture(pointerId: number): void;
  releasePointerCapture(pointerId: number): void;
}

export interface ContextoDOM {
  createElement(etiqueta: string): ElementoDOM;
}

/**
 * Adaptador sobre un `Document` de verdad. `HTMLElement` cumple `ElementoDOM`
 * de sobra —tiene todos estos métodos y más—, pero TypeScript no lo sabe sin
 * ayuda porque algunas firmas reales son más genéricas que las de aquí
 * (`addEventListener` real acepta cualquier nombre de evento). El
 * `as unknown as` es el único sitio de todo el módulo que lo necesita; el
 * resto de `paneles.ts` solo ve `ElementoDOM`.
 */
export function contextoDesdeDocumento(documento: Pick<Document, "createElement">): ContextoDOM {
  return {
    createElement: (etiqueta: string): ElementoDOM =>
      documento.createElement(etiqueta) as unknown as ElementoDOM,
  };
}

/**
 * Igual que `contextoDesdeDocumento`, pero para un único elemento que ya
 * existe (el contenedor que pasa quien monta el componente en la
 * aplicación real, `PanelesApilados.montar`). Mismo motivo del `as unknown
 * as`: un `HTMLElement` real cumple `ElementoDOM` de sobra, pero su
 * `addEventListener` tiene una firma más genérica de la que TypeScript no
 * puede derivar la compatibilidad estructural sin ayuda.
 */
export function elementoDesdeHtml(elemento: HTMLElement): ElementoDOM {
  return elemento as unknown as ElementoDOM;
}
