/**
 * La superficie del DOM que usa este módulo. Nada más.
 *
 * Mismo motivo que `render/contexto.ts` (WebGL2) y `cursor/contexto-dom.ts`
 * (`document`): una interfaz deliberadamente pequeña que un
 * `HTMLElement`/`HTMLCanvasElement` real cumple estructuralmente sin
 * adaptador — `addEventListener(tipo: string, oyente: (evento: Event) =>
 * void, opciones?)` es, salvo por las sobrecargas por nombre de evento que
 * aquí no hacen falta, literalmente su firma general—, así que se pasa sin
 * envoltorio. La ventaja es la otra dirección: un doble de pruebas (objeto
 * plano) también la cumple, y eso permite probar el cableado de eventos en
 * Node —el entorno de `vitest` en este proyecto, sin jsdom instalado— sin un
 * navegador real.
 *
 * `OyenteDeEvento` se tipa sobre `Event`, no sobre `WheelEvent` /
 * `PointerEvent` / `KeyboardEvent`: son las sobrecargas que el DOM real
 * resuelve por el literal de `tipo`, y replicarlas aquí obligaría a un doble
 * de pruebas a implementarlas todas para poder pasar por esta interfaz. La
 * conversión al tipo concreto vive en el único sitio que la necesita,
 * `controlador.ts`, con el mismo patrón que ya usa `unidades/dom-falso.ts`
 * para sus eventos simulados.
 */

export type OyenteDeEvento = (evento: Event) => void;

/** Lo que hace falta de un `DOMRect`: nada de `x`/`y`/`toJSON`. */
export interface RectanguloDelElemento {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

export interface ElementoNavegable {
  addEventListener(
    tipo: string,
    oyente: OyenteDeEvento,
    opciones?: AddEventListenerOptions | boolean,
  ): void;
  removeEventListener(
    tipo: string,
    oyente: OyenteDeEvento,
    opciones?: EventListenerOptions | boolean,
  ): void;
  getBoundingClientRect(): RectanguloDelElemento;
  /**
   * Ata el arrastre al elemento aunque el puntero salga de él (p. ej. un
   * arrastre rápido que se sale del panel): sin esto, `pointermove` deja de
   * llegar en cuanto el cursor cruza el borde y el arrastre "se pierde" a
   * media acción, justo el defecto que la tarea pide evitar.
   */
  setPointerCapture(pointerId: number): void;
  releasePointerCapture(pointerId: number): void;
}
