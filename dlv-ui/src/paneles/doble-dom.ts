/**
 * Un doble de `ContextoDOM` (`contexto-dom.ts`) que registra clases, estilos
 * y manejadores de puntero, sin capa alguna de `layout` ni `paint`.
 *
 * Mismo motivo que `render/doble-gl.ts`, `unidades/dom-falso.ts` y
 * `cursor/doble-dom.ts`: `vitest.config.ts` corre en `environment: "node"`
 * (sin `document` global) y este proyecto no tiene jsdom/happy-dom
 * instalados. En vez de añadir uno de los dos para un componente de 5
 * puntos, este fichero implementa `ElementoDOM` con objetos planos y expone
 * `fijarRectangulo`/`disparar` para que las pruebas puedan simular tanto la
 * geometría (`getBoundingClientRect`, que en Node nadie puede calcular de
 * verdad) como los eventos de puntero de un arrastre completo.
 *
 * Vive en `src/` y no en un directorio de pruebas: `tsconfig.json` solo
 * incluye `src` (misma nota que en `doble-gl.ts`), así que un doble en
 * `tests/` no pasaría `tsc --noEmit`.
 */

import type {
  ClaseCSS,
  ContextoDOM,
  ElementoDOM,
  EstiloCSS,
  EventoPuntero,
  RectanguloPx,
  TipoEventoPuntero,
} from "./contexto-dom.ts";

const RECTANGULO_VACIO: RectanguloPx = { top: 0, bottom: 0, left: 0, right: 0 };

function claseCSSFalsa(clases: Set<string>): ClaseCSS {
  return {
    add: (...nuevas: string[]): void => {
      for (const c of nuevas) clases.add(c);
    },
    remove: (...quitadas: string[]): void => {
      for (const c of quitadas) clases.delete(c);
    },
    contains: (clase: string): boolean => clases.has(clase),
  };
}

/** Un elemento falso. Además de `ElementoDOM`, expone lo que las pruebas necesitan inspeccionar. */
export interface ElementoFalso extends ElementoDOM {
  readonly etiquetaTag: string;
  readonly hijos: readonly ElementoFalso[];
  readonly atributos: ReadonlyMap<string, string>;
  readonly propiedadesDeEstilo: ReadonlyMap<string, string>;
  readonly clases: ReadonlySet<string>;
  /** Fija lo que devolverá `getBoundingClientRect()`. Node no puede calcular layout de verdad. */
  fijarRectangulo(rectangulo: RectanguloPx): void;
}

function crearElementoFalso(etiquetaTag: string): ElementoFalso {
  const clases = new Set<string>();
  const propiedadesDeEstilo = new Map<string, string>();
  const atributos = new Map<string, string>();
  const hijos: ElementoFalso[] = [];
  const manejadoresPorTipo = new Map<string, Array<(evento: EventoPuntero) => void>>();
  const capturados = new Set<number>();
  let rectangulo: RectanguloPx = RECTANGULO_VACIO;
  let texto = "";

  const elemento: ElementoFalso = {
    etiquetaTag,
    hijos,
    atributos,
    propiedadesDeEstilo,
    clases,
    classList: claseCSSFalsa(clases),
    style: {
      setProperty: (nombre: string, valor: string): void => {
        propiedadesDeEstilo.set(nombre, valor);
      },
    } satisfies EstiloCSS,
    get textContent(): string {
      return texto;
    },
    set textContent(valor: string) {
      texto = valor;
      // Igual que en el DOM real: fijar `textContent` sustituye a los hijos.
      hijos.length = 0;
    },
    appendChild<T extends ElementoDOM>(hijo: T): T {
      hijos.push(hijo as unknown as ElementoFalso);
      return hijo;
    },
    remove(): void {
      // El doble no mantiene referencia al padre (no la necesita ningún
      // camino de `paneles.ts`, que solo añade, nunca reordena por remoción
      // ajena); se deja como no-op documentado en vez de fingir un padre.
    },
    setAttribute(nombre: string, valor: string): void {
      atributos.set(nombre, valor);
    },
    getBoundingClientRect(): RectanguloPx {
      return rectangulo;
    },
    addEventListener(tipo: TipoEventoPuntero, manejador: (evento: EventoPuntero) => void): void {
      const lista = manejadoresPorTipo.get(tipo) ?? [];
      lista.push(manejador);
      manejadoresPorTipo.set(tipo, lista);
    },
    setPointerCapture(pointerId: number): void {
      capturados.add(pointerId);
    },
    releasePointerCapture(pointerId: number): void {
      capturados.delete(pointerId);
    },
    fijarRectangulo(nuevo: RectanguloPx): void {
      rectangulo = nuevo;
    },
  };

  // Guardado aparte del objeto público para que `disparar()` (función libre,
  // no método) pueda encontrar los manejadores sin ensuciar `ElementoDOM`
  // con un método que la interfaz real no tiene.
  MANEJADORES.set(elemento, manejadoresPorTipo);
  return elemento;
}

const MANEJADORES = new WeakMap<ElementoFalso, Map<string, Array<(evento: EventoPuntero) => void>>>();

export interface DetalleEventoPuntero {
  readonly clientX?: number;
  readonly clientY?: number;
  readonly pointerId?: number;
  readonly button?: number;
}

/**
 * Simula que el usuario disparó `tipo` sobre `elemento` con las coordenadas
 * de `detalle`. `pointerId` por omisión 1 (un único puntero, el caso común de
 * ratón); las pruebas de arrastre con varios punteros a la vez lo fijan
 * explícitamente.
 */
export function disparar(
  elemento: ElementoFalso,
  tipo: TipoEventoPuntero,
  detalle: DetalleEventoPuntero = {},
): void {
  const evento: EventoPuntero = {
    clientX: detalle.clientX ?? 0,
    clientY: detalle.clientY ?? 0,
    pointerId: detalle.pointerId ?? 1,
    button: detalle.button ?? 0,
    preventDefault: () => {},
  };
  const manejadores = MANEJADORES.get(elemento)?.get(tipo) ?? [];
  for (const manejador of manejadores) manejador(evento);
}

export function crearContextoDomFalso(): ContextoDOM {
  return {
    createElement: (etiqueta: string): ElementoDOM => crearElementoFalso(etiqueta),
  };
}
