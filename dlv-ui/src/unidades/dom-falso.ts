/**
 * Un doble de `FabricaDom` que registra hijos, valores y manejadores.
 *
 * Mismo motivo que `render/doble-gl.ts`: `vitest.config.ts` corre en
 * `environment: "node"` (sin `document` global) y este proyecto no tiene
 * jsdom/happy-dom instalados — son `peerDependencies` opcionales de vitest,
 * no dependencias reales (`node_modules/jsdom` no existe). Añadir una de las
 * dos sería meter una dependencia nueva para un componente de 5 puntos, así
 * que en vez de eso el componente depende de `FabricaDom` (`dom.ts`), una
 * interfaz mínima, y este fichero implementa esa interfaz con objetos planos.
 *
 * No emula el DOM entero: emula lo justo para que `SelectorUnidad` funcione y
 * para que una prueba pueda inspeccionar qué se construyó y simular un
 * `change`. Vive en `src/` y no en un directorio de pruebas porque
 * `tsconfig.json` solo incluye `src` (misma nota que en `doble-gl.ts`).
 */

import type { FabricaDom, NodoDom, OptionDom, SelectDom } from "./dom.ts";

/** Lo que una prueba necesita mirar de un nodo, además de la interfaz pública. */
export interface NodoFalso extends NodoDom {
  readonly etiquetaTag: string;
  readonly hijos: readonly NodoDom[];
}

type Manejador = (evento: Event) => void;

function nodoBase(etiquetaTag: string): NodoFalso {
  const hijos: NodoDom[] = [];
  return {
    etiquetaTag,
    hijos,
    classList: { add: () => {} },
    textContent: "",
    appendChild(hijo: NodoDom): NodoDom {
      hijos.push(hijo);
      return hijo;
    },
    replaceChildren(...nuevos: NodoDom[]): void {
      hijos.length = 0;
      hijos.push(...nuevos);
    },
  };
}

const MANEJADORES = new WeakMap<NodoDom, Map<string, Manejador[]>>();

function crearSelectFalso(): SelectDom {
  // OJO: se aumenta `base` en el sitio en vez de esparcirla (`{...base}`) en
  // un objeto nuevo. Un `{...base, ...}` crearía una copia con otra
  // identidad, y `disparar()` busca en `MANEJADORES` por identidad: si la
  // clave no fuera el mismo objeto que se devuelve (y que el componente
  // guarda y las pruebas reciben), ningún evento encontraría sus manejadores.
  const select = nodoBase("select") as unknown as SelectDom;
  const manejadoresPorTipo = new Map<string, Manejador[]>();
  select.value = "";
  select.disabled = false;
  select.addEventListener = (tipo: "change", manejador: Manejador): void => {
    const lista = manejadoresPorTipo.get(tipo) ?? [];
    lista.push(manejador);
    manejadoresPorTipo.set(tipo, lista);
  };
  MANEJADORES.set(select, manejadoresPorTipo);
  return select;
}

function crearOptionFalsa(): OptionDom {
  return { ...nodoBase("option"), value: "" };
}

export interface FabricaDomFalsa {
  readonly fabrica: FabricaDom;
  /** Simula que el usuario disparó `tipo` (habitualmente "change") sobre `nodo`. */
  disparar(nodo: SelectDom, tipo: string): void;
}

export function crearFabricaDomFalsa(): FabricaDomFalsa {
  return {
    fabrica: {
      crearDiv: () => nodoBase("div"),
      crearSpan: () => nodoBase("span"),
      crearSelect: crearSelectFalso,
      crearOption: crearOptionFalsa,
    },
    disparar(nodo: SelectDom, tipo: string): void {
      const manejadoresPorTipo = MANEJADORES.get(nodo);
      const evento = { type: tipo, target: nodo } as unknown as Event;
      for (const manejador of manejadoresPorTipo?.get(tipo) ?? []) manejador(evento);
    },
  };
}

/** Los hijos de un nodo construido por la fábrica falsa, tipados para inspección. */
export function hijosDe(nodo: NodoDom): readonly NodoFalso[] {
  return (nodo as NodoFalso).hijos as readonly NodoFalso[];
}
