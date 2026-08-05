/**
 * La superficie de `document` que usa el cursor. Nada más.
 *
 * Mismo motivo que `render/contexto.ts` (ADR-006 lo llama «una superficie de
 * API deliberadamente pequeña»): `document` real cumple esta interfaz
 * estructuralmente —`createElement(etiqueta: string): HTMLElement` es
 * literalmente su firma general—, así que se pasa sin adaptador. La ventaja es
 * la otra dirección: un doble de pruebas (`doble-dom.ts`) también la cumple, y
 * eso permite probar en Node, sin navegador, la parte que SÍ se puede probar
 * sin uno: cuántos nodos se crean y cuántas propiedades se escriben por
 * fotograma. Lo que un doble nunca puede decir es el coste de `layout`/`paint`
 * de un navegador real; ese límite está escrito en `cursor.banco.test.ts`.
 */

export interface ContextoDOM {
  createElement(etiqueta: string): HTMLElement;
}
