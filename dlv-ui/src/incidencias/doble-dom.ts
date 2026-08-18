/**
 * Un doble de `ContextoDOM` (`contexto-dom.ts`) para probar
 * `panel-incidencias.ts` sin navegador.
 *
 * Mismo motivo y mismo patrón que `cursor/doble-dom.ts` y
 * `paneles/doble-dom.ts`: `vitest.config.ts` corre en `environment: "node"`
 * y este paquete no tiene jsdom/happy-dom instalado (ni se añade sin
 * preguntar, regla de `docs/09` §9.11). Este doble implementa
 * `ElementoDOM` con objetos planos: registra clases, texto y manejadores de
 * clic, sin ninguna capa de `layout` ni `paint` — lo que un doble nunca
 * puede decir es si la fila SE VE distinguible; eso es un juicio visual y
 * queda fuera de una prueba unitaria (misma nota que `cursor/doble-dom.ts`).
 *
 * Vive en `src/` y no en un directorio de pruebas: `tsconfig.json` solo
 * incluye `src`, así que un doble en `tests/` no pasaría `tsc --noEmit`
 * (misma nota que en `doble-gl.ts`).
 */

import type { ClaseCSS, ContextoDOM, ElementoDOM, EstiloCSS } from "./contexto-dom.ts";

function claseCSSFalsa(clases: Set<string>): ClaseCSS {
  return {
    add: (...nuevas: string[]): void => {
      for (const c of nuevas) clases.add(c);
    },
  };
}

function estiloCSSFalso(propiedades: Map<string, string>): EstiloCSS {
  return {
    setProperty: (nombre: string, valor: string): void => {
      propiedades.set(nombre, valor);
    },
  };
}

/**
 * Un nodo falso. Expone lo mismo que `ElementoDOM` más lo que las pruebas
 * necesitan leer (`clases`, `atributos`, `hijos`) y disparar (`clic`).
 */
export class ElementoFalso implements ElementoDOM {
  readonly etiqueta: string;
  readonly clases = new Set<string>();
  readonly propiedadesDeEstilo = new Map<string, string>();
  readonly atributos = new Map<string, string>();
  readonly hijos: ElementoFalso[] = [];
  readonly classList: ClaseCSS;
  readonly style: EstiloCSS;
  textContent = "";
  title = "";
  #alClic: (() => void) | null = null;

  constructor(etiqueta: string) {
    this.etiqueta = etiqueta;
    this.classList = claseCSSFalsa(this.clases);
    this.style = estiloCSSFalso(this.propiedadesDeEstilo);
  }

  appendChild<T extends ElementoDOM>(hijo: T): T {
    this.hijos.push(hijo as unknown as ElementoFalso);
    return hijo;
  }

  replaceChildren(...hijos: readonly ElementoDOM[]): void {
    this.hijos.length = 0;
    for (const hijo of hijos) this.hijos.push(hijo as unknown as ElementoFalso);
  }

  setAttribute(nombre: string, valor: string): void {
    this.atributos.set(nombre, valor);
  }

  addEventListener(tipo: "click", manejador: () => void): void {
    if (tipo === "click") this.#alClic = manejador;
  }

  /** Simula un clic del usuario sobre este nodo. No-op si nadie escucha. */
  clic(): void {
    this.#alClic?.();
  }
}

/** Un `ContextoDOM` falso que crea `ElementoFalso`. */
export function crearContextoDomFalso(): ContextoDOM {
  return {
    createElement: (etiqueta: string): ElementoDOM => new ElementoFalso(etiqueta),
  };
}
