/**
 * La superficie de DOM que necesita `SelectorCombustible`. Nada más.
 *
 * Mismo motivo que `unidades/dom.ts` (y, antes, `render/contexto.ts` para
 * WebGL2, ADR-006): una interfaz deliberadamente pequeña, para que un doble de
 * pruebas la pueda satisfacer sin jsdom/happy-dom — no instalados en este
 * proyecto (`vitest.config.ts` corre en `environment: "node"`, sin DOM
 * global). Cada carril de componente con DOM en `dlv-ui/src` define la suya
 * (`cursor/contexto-dom.ts`, `paneles/contexto-dom.ts`, `unidades/dom.ts`) en
 * vez de compartir una sola: la de aquí añade `crearInput`, que ninguna de las
 * otras necesita, para el campo de estequiometría tecleada a mano.
 *
 * `Node.appendChild` de verdad es `<T extends Node>(node: T) => T`, así que un
 * `HTMLElement` real no es estructuralmente asignable a `NodoDom` sin
 * decírselo. `fabricaDesdeDocumento` hace esa conversión explícita en el único
 * sitio que la necesita; el resto del módulo solo ve esta interfaz reducida.
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

export interface SelectDom extends NodoDom {
  value: string;
  addEventListener(tipo: "change", manejador: (evento: Event) => void): void;
}

export interface OptionDom extends NodoDom {
  value: string;
}

/** El campo de texto para la estequiometría tecleada a mano. */
export interface InputDom extends NodoDom {
  value: string;
  type: string;
  placeholder: string;
  addEventListener(tipo: "change" | "input", manejador: (evento: Event) => void): void;
}

/** Los cinco tipos de nodo que construye el selector. Ni uno más. */
export interface FabricaDom {
  crearDiv(): NodoDom;
  crearSpan(): NodoDom;
  crearSelect(): SelectDom;
  crearOption(): OptionDom;
  crearInput(): InputDom;
}

/**
 * Adaptador sobre un `Document` de verdad. Quien monte el componente en la
 * aplicación llama a `fabricaDesdeDocumento(document)` y le pasa el resultado
 * al constructor de `SelectorCombustible` — igual que `main.ts` usa `document`
 * directamente, sin framework.
 */
export function fabricaDesdeDocumento(documento: Pick<Document, "createElement">): FabricaDom {
  return {
    // `as unknown as NodoDom`: ver la nota de cabecera sobre por qué
    // `HTMLElement` no encaja en `NodoDom` sin conversión (la firma genérica
    // de `appendChild`). Los métodos que sí usa el selector existen todos de
    // verdad, así que la conversión no esconde ninguna llamada que vaya a
    // fallar en tiempo real.
    crearDiv: () => documento.createElement("div") as unknown as NodoDom,
    crearSpan: () => documento.createElement("span") as unknown as NodoDom,
    crearSelect: () => documento.createElement("select") as unknown as SelectDom,
    crearOption: () => documento.createElement("option") as unknown as OptionDom,
    crearInput: () => documento.createElement("input") as unknown as InputDom,
  };
}
