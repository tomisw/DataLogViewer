/**
 * Un doble de `document` que registra lo que se le pide, sin capa alguna de
 * `layout` ni `paint`.
 *
 * Por qué existe: igual que `render/doble-gl.ts` mide la parte del
 * renderizador que se puede medir sin GPU (cuántos búferes se suben), este
 * doble mide la parte del cursor que se puede medir sin navegador: cuántos
 * nodos se crean y cuántas veces se escribe una propiedad (`textContent`,
 * `className`, `title`, un estilo). Es el número que se degrada primero
 * cuando alguien reconstruye la tabla entera en vez de tocar solo la celda que
 * cambió.
 *
 * Lo que este doble NO puede decir es si esa escritura, en un navegador real,
 * fuerza un recálculo de estilo o un repintado — eso depende del motor de
 * layout y no existe en Node. `cursor.banco.test.ts` lo dice explícitamente:
 * el número de este doble es un suelo, no el presupuesto de §2.6 completo.
 *
 * Vive en `src/` y no en un directorio de pruebas por la misma razón que
 * `doble-gl.ts`: `tsconfig.json` solo incluye `src`, y un doble sin
 * comprobación de tipos estricta es un doble que deja de parecerse a la
 * interfaz real sin avisar.
 */

import type { ContextoDOM } from "./contexto-dom.ts";

/** Contador de escrituras de propiedades, compartido por todos los elementos del doble. */
class Contadores {
  nodosCreados = 0;
  escrituras = 0;
}

/**
 * Un nodo falso. Implementa el subconjunto de `HTMLElement` que el cursor usa
 * de verdad (visto en `cursor.ts`): crear, anexar, quitar, y escribir texto,
 * clase, título y una propiedad de estilo. Nada de `nodeType`, `ownerDocument`
 * ni el resto del árbol de `Node` — el cursor no los usa, y la interfaz real
 * (`HTMLElement`) solo entra por el `as unknown as` de `crear()`, así que
 * TypeScript nunca comprueba que este doble sea *de verdad* un `HTMLElement`.
 */
class ElementoFalso {
  readonly etiqueta: string;
  readonly #contadores: Contadores;
  #textContent: string | null = null;
  #className = "";
  #title = "";
  hijos: ElementoFalso[] = [];
  padre: ElementoFalso | null = null;
  readonly atributos = new Map<string, string>();
  readonly propiedadesDeEstilo = new Map<string, string>();
  readonly style: { setProperty(nombre: string, valor: string): void };

  constructor(etiqueta: string, contadores: Contadores) {
    this.etiqueta = etiqueta;
    this.#contadores = contadores;
    contadores.nodosCreados += 1;
    this.style = {
      setProperty: (nombre: string, valor: string) => {
        this.propiedadesDeEstilo.set(nombre, valor);
        this.#contadores.escrituras += 1;
      },
    };
  }

  get textContent(): string | null {
    return this.#textContent;
  }

  set textContent(valor: string | null) {
    this.#textContent = valor;
    this.#contadores.escrituras += 1;
    // Igual que el DOM real: fijar `textContent` sustituye a todos los hijos
    // por un único nodo de texto.
    for (const hijo of this.hijos) hijo.padre = null;
    this.hijos = [];
  }

  get className(): string {
    return this.#className;
  }

  set className(valor: string) {
    this.#className = valor;
    this.#contadores.escrituras += 1;
  }

  get title(): string {
    return this.#title;
  }

  set title(valor: string) {
    this.#title = valor;
    this.#contadores.escrituras += 1;
  }

  appendChild<T>(hijo: T): T {
    const h = hijo as unknown as ElementoFalso;
    h.padre = this;
    this.hijos.push(h);
    return hijo;
  }

  setAttribute(nombre: string, valor: string): void {
    this.atributos.set(nombre, valor);
    this.#contadores.escrituras += 1;
  }

  remove(): void {
    if (this.padre === null) return;
    this.padre.hijos = this.padre.hijos.filter((h) => h !== this);
    this.padre = null;
  }
}

export interface DobleDOM {
  readonly documento: ContextoDOM;
  /** Cuántos elementos se crearon en total desde que existe el doble. */
  nodosCreados(): number;
  /**
   * Cuántas escrituras de propiedad (`textContent`, `className`, `title`,
   * una propiedad de estilo, un atributo) se hicieron. Es el número que
   * `cursor.banco.test.ts` vigila por fotograma: si sube con el número de
   * canales cuando el cursor NO se mueve de cubo, alguien volvió a escribir
   * una celda que no cambió.
   */
  escrituras(): number;
  reiniciarContadores(): void;
}

export function crearDobleDOM(): DobleDOM {
  const contadores = new Contadores();
  const documento: ContextoDOM = {
    createElement: (etiqueta: string): HTMLElement =>
      new ElementoFalso(etiqueta, contadores) as unknown as HTMLElement,
  };
  return {
    documento,
    nodosCreados: () => contadores.nodosCreados,
    escrituras: () => contadores.escrituras,
    reiniciarContadores: () => {
      contadores.nodosCreados = 0;
      contadores.escrituras = 0;
    },
  };
}
