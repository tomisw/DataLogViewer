/**
 * Un doble de `FabricaDom` que registra hijos, valores y manejadores.
 *
 * Mismo motivo que `unidades/dom-falso.ts`: sin jsdom/happy-dom instalados,
 * `SelectorCombustible` depende de `FabricaDom` (`dom.ts`), una interfaz
 * mínima, y este fichero la implementa con objetos planos. No emula el DOM
 * entero: emula lo justo para que el componente funcione y para que una
 * prueba pueda inspeccionar qué se construyó y simular un `change`/`input`.
 * Vive en `src/` y no en un directorio de pruebas porque `tsconfig.json` solo
 * incluye `src` (misma nota que en `unidades/dom-falso.ts`).
 */

import type { FabricaDom, InputDom, NodoDom, OptionDom, SelectDom } from "./dom.ts";

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

function registrarEventos(nodo: NodoDom): Map<string, Manejador[]> {
  const manejadoresPorTipo = new Map<string, Manejador[]>();
  MANEJADORES.set(nodo, manejadoresPorTipo);
  return manejadoresPorTipo;
}

function crearSelectFalso(): SelectDom {
  // OJO: se aumenta `base` en el sitio en vez de esparcirla (`{...base}`) en
  // un objeto nuevo. `disparar()` busca en `MANEJADORES` por identidad: si la
  // clave no fuera el mismo objeto que se devuelve y que la prueba recibe,
  // ningún evento encontraría sus manejadores (misma nota que en
  // `unidades/dom-falso.ts`).
  const select = nodoBase("select") as unknown as SelectDom;
  select.value = "";
  const manejadoresPorTipo = registrarEventos(select);
  select.addEventListener = (tipo: "change", manejador: Manejador): void => {
    const lista = manejadoresPorTipo.get(tipo) ?? [];
    lista.push(manejador);
    manejadoresPorTipo.set(tipo, lista);
  };
  return select;
}

function crearOptionFalsa(): OptionDom {
  return { ...nodoBase("option"), value: "" };
}

function crearInputFalso(): InputDom {
  const input = nodoBase("input") as unknown as InputDom;
  input.value = "";
  input.type = "text";
  input.placeholder = "";
  const manejadoresPorTipo = registrarEventos(input);
  input.addEventListener = (tipo: "change" | "input", manejador: Manejador): void => {
    const lista = manejadoresPorTipo.get(tipo) ?? [];
    lista.push(manejador);
    manejadoresPorTipo.set(tipo, lista);
  };
  return input;
}

export interface FabricaDomFalsa {
  readonly fabrica: FabricaDom;
  /** Simula que el usuario disparó `tipo` (`"change"` o `"input"`) sobre `nodo`. */
  disparar(nodo: SelectDom | InputDom, tipo: string): void;
}

export function crearFabricaDomFalsa(): FabricaDomFalsa {
  return {
    fabrica: {
      crearDiv: () => nodoBase("div"),
      crearSpan: () => nodoBase("span"),
      crearSelect: crearSelectFalso,
      crearOption: crearOptionFalsa,
      crearInput: crearInputFalso,
    },
    disparar(nodo: SelectDom | InputDom, tipo: string): void {
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
