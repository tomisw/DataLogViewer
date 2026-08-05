/**
 * Un doble de `FabricaSvg` que registra hijos, atributos y clases.
 *
 * Mismo motivo que `unidades/dom-falso.ts`: sin él, probar qué dibuja
 * `pintarCarril` (cuántas bandas, con qué color, con qué etiqueta, dónde caen
 * las marcas de transición) exigiría un navegador de verdad. No emula el DOM
 * entero — emula lo justo para inspeccionar el árbol que construye
 * `carril-estado.ts`. Vive en `src/` y no en un directorio de pruebas porque
 * `tsconfig.json` solo incluye `src` (misma nota que en `dom-falso.ts` de
 * `unidades/` y `render/doble-gl.ts`).
 */

import type { ElementoSvg, FabricaSvg } from "./dom.ts";

/** Lo que una prueba necesita mirar de un nodo, además de la interfaz pública. */
export interface NodoSvgFalso extends ElementoSvg {
  readonly etiquetaTag: string;
  readonly atributos: ReadonlyMap<string, string>;
  readonly clases: readonly string[];
  readonly hijos: readonly NodoSvgFalso[];
}

function nodoBase(etiquetaTag: string): NodoSvgFalso {
  const atributos = new Map<string, string>();
  const clases: string[] = [];
  const hijos: NodoSvgFalso[] = [];
  return {
    etiquetaTag,
    atributos,
    clases,
    hijos,
    textContent: "",
    classList: {
      add(...nuevas: string[]): void {
        for (const clase of nuevas) if (!clases.includes(clase)) clases.push(clase);
      },
    },
    setAttribute(nombre: string, valor: string): void {
      atributos.set(nombre, valor);
    },
    appendChild(hijo: ElementoSvg): ElementoSvg {
      hijos.push(hijo as NodoSvgFalso);
      return hijo;
    },
    replaceChildren(...nuevos: ElementoSvg[]): void {
      hijos.length = 0;
      hijos.push(...(nuevos as NodoSvgFalso[]));
    },
  };
}

export function crearFabricaSvgFalsa(): FabricaSvg {
  return {
    crearG: () => nodoBase("g"),
    crearRect: () => nodoBase("rect"),
    crearText: () => nodoBase("text"),
  };
}

/** El `<svg>` contenedor falso donde `pintarCarril` cuelga el árbol, para pasar a las pruebas. */
export function crearContenedorSvgFalso(): NodoSvgFalso {
  return nodoBase("svg");
}
