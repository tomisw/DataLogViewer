/**
 * Un doble de `FabricaDom` (`dom.ts`), en el mismo espíritu que
 * `unidades/dom-falso.ts`: objetos planos que registran hijos, valores y
 * manejadores, sin jsdom/happy-dom.
 */

import type { BotonDom, FabricaDom, InputDom, NodoDom, TextareaDom } from "./dom.ts";

export interface NodoFalso extends NodoDom {
  readonly etiquetaTag: string;
  readonly hijos: readonly NodoDom[];
  /**
   * Solo lo tienen los campos (`input`, `textarea`): `crearCampoFalso` se lo
   * pone y `nodoBase` no. Opcional a proposito y no obligatorio, porque eso es
   * exactamente lo que pasa en el DOM real -- un `<div>` no tiene `value` --
   * y asi una prueba que lea `.value` de un nodo cualquiera tiene que
   * reconocer que puede no estar, en vez de dar por hecho que si.
   */
  readonly value?: string;
}

type Manejador = (evento: Event) => void;

const MANEJADORES = new WeakMap<NodoDom, Map<string, Manejador[]>>();

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

function registrarManejador(nodo: NodoDom, tipo: string, manejador: Manejador): void {
  const porTipo = MANEJADORES.get(nodo) ?? new Map<string, Manejador[]>();
  const lista = porTipo.get(tipo) ?? [];
  lista.push(manejador);
  porTipo.set(tipo, lista);
  MANEJADORES.set(nodo, porTipo);
}

function crearCampoFalso(etiquetaTag: string): InputDom & TextareaDom {
  const campo = nodoBase(etiquetaTag) as unknown as InputDom & TextareaDom;
  campo.value = "";
  campo.disabled = false;
  campo.type = "text";
  campo.placeholder = "";
  campo.addEventListener = (tipo: "change", manejador: Manejador): void => registrarManejador(campo, tipo, manejador);
  return campo;
}

function crearBotonFalso(): BotonDom {
  const boton = nodoBase("button") as unknown as BotonDom;
  boton.disabled = false;
  boton.addEventListener = (tipo: "click", manejador: Manejador): void => registrarManejador(boton, tipo, manejador);
  return boton;
}

export interface FabricaDomFalsa {
  readonly fabrica: FabricaDom;
  /** Simula que el usuario disparó `tipo` sobre `nodo` ("change" o "click"). */
  disparar(nodo: NodoDom, tipo: string): void;
}

export function crearFabricaDomFalsa(): FabricaDomFalsa {
  return {
    fabrica: {
      crearDiv: () => nodoBase("div"),
      crearSpan: () => nodoBase("span"),
      crearInput: () => crearCampoFalso("input"),
      crearTextarea: () => crearCampoFalso("textarea"),
      crearBoton: crearBotonFalso,
    },
    disparar(nodo: NodoDom, tipo: string): void {
      const evento = { type: tipo, target: nodo } as unknown as Event;
      for (const manejador of MANEJADORES.get(nodo)?.get(tipo) ?? []) manejador(evento);
    },
  };
}

/** Los hijos de un nodo construido por la fábrica falsa, tipados para inspección. */
export function hijosDe(nodo: NodoDom): readonly NodoFalso[] {
  return (nodo as NodoFalso).hijos as readonly NodoFalso[];
}

/** Todos los descendientes con esta etiqueta, en orden de documento (para localizar un control sin depender de la posición exacta en el árbol). */
export function buscarTodos(nodo: NodoDom, etiquetaTag: string): NodoFalso[] {
  const encontrados: NodoFalso[] = [];
  const visitar = (n: NodoFalso): void => {
    if (n.etiquetaTag === etiquetaTag) encontrados.push(n);
    for (const hijo of n.hijos) visitar(hijo as NodoFalso);
  };
  visitar(nodo as NodoFalso);
  return encontrados;
}
