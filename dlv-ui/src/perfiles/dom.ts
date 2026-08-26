/**
 * La superficie de DOM que necesita `EditorPerfil`. Nada más.
 *
 * Mismo motivo que `unidades/dom.ts` (léela primero, es el precedente directo
 * de esta tarea): una interfaz deliberadamente pequeña para que un doble de
 * pruebas la satisfaga sin jsdom/happy-dom, que no están instalados
 * (`vitest.config.ts` corre en `environment: "node"`). No se reutiliza
 * `unidades/dom.ts` tal cual porque le faltan los tres controles que este
 * editor necesita y aquel no: `input` de texto/número, `textarea` y `button`
 * con manejador de `click` (`unidades/dom.ts` solo tiene `select`/`option`,
 * que es lo único que necesita `SelectorUnidad`). Ampliarla allí habría hecho
 * más grande la superficie de un componente que no usa nada de esto.
 */

export interface ClaseCSS {
  add(...clases: string[]): void;
}

export interface NodoDom {
  appendChild(hijo: NodoDom): NodoDom;
  replaceChildren(...hijos: NodoDom[]): void;
  readonly classList: ClaseCSS;
  textContent: string;
}

export interface CampoDom extends NodoDom {
  value: string;
  disabled: boolean;
  addEventListener(tipo: "change", manejador: (evento: Event) => void): void;
}

export interface InputDom extends CampoDom {
  type: string;
  placeholder: string;
}

export type TextareaDom = CampoDom;

export interface BotonDom extends NodoDom {
  disabled: boolean;
  addEventListener(tipo: "click", manejador: (evento: Event) => void): void;
}

/** Los cinco tipos de nodo que construye el editor. Ni uno más. */
export interface FabricaDom {
  crearDiv(): NodoDom;
  crearSpan(): NodoDom;
  crearInput(): InputDom;
  crearTextarea(): TextareaDom;
  crearBoton(): BotonDom;
}

/**
 * Adaptador sobre un `Document` de verdad. Quien monte el editor en la
 * aplicación llama a `fabricaDesdeDocumento(document)` — mismo patrón que
 * `unidades/dom.ts#fabricaDesdeDocumento`, incluida la conversión explícita
 * por la firma genérica de `appendChild` (ver la cabecera de aquel fichero).
 */
export function fabricaDesdeDocumento(documento: Pick<Document, "createElement">): FabricaDom {
  return {
    crearDiv: () => documento.createElement("div") as unknown as NodoDom,
    crearSpan: () => documento.createElement("span") as unknown as NodoDom,
    crearInput: () => documento.createElement("input") as unknown as InputDom,
    crearTextarea: () => documento.createElement("textarea") as unknown as TextareaDom,
    crearBoton: () => {
      const boton = documento.createElement("button") as unknown as BotonDom & { type: string };
      boton.type = "button";
      return boton;
    },
  };
}
