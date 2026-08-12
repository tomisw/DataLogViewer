/**
 * Constructores y consultas puras de `Campo<T>` (ver `tipos.ts`).
 *
 * Deliberadamente diminuto: la regla completa es «un valor deducido y uno
 * confirmado no son el mismo dato», y la forma más fiable de que esa regla no
 * se rompa en un `{ valor, origen: "deducido" }` escrito a mano en tres sitios
 * distintos es que no se escriba a mano en ningún sitio.
 */

import type { Campo, Origen } from "./tipos.ts";

/** Un valor propuesto por el sondeo, todavía sin que el usuario lo mire. */
export function deducido<T>(valor: T): Campo<T> {
  return { valor, origen: "deducido" };
}

/** Un valor que el usuario ha fijado — a mano, o aceptando la propuesta explícitamente. */
export function confirmado<T>(valor: T): Campo<T> {
  return { valor, origen: "confirmado" };
}

export function esConfirmado<T>(campo: Campo<T>): boolean {
  return campo.origen === "confirmado";
}

export function esDeducido<T>(campo: Campo<T>): boolean {
  return campo.origen === "deducido";
}

/**
 * El usuario edita el campo: pasa a `confirmado` con el valor nuevo, sin
 * importar de dónde venía. Es la única vía por la que un `Campo` cambia de
 * `origen` a lo largo de la vida del asistente — nunca al revés: no hay
 * "desconfirmar", porque una vez que una persona ha mirado el valor, no hay
 * manera honesta de volver a llamarlo "todavía no visto".
 */
export function editar<T>(_actual: Campo<T>, valorNuevo: T): Campo<T> {
  return confirmado(valorNuevo);
}

/** Igual que `editar`, pero para "aceptar la propuesta tal cual": el valor no
 * cambia, solo el origen. Usarlo en un botón "confirmar todo" explícito. */
export function aceptarPropuesta<T>(actual: Campo<T>): Campo<T> {
  return confirmado(actual.valor);
}

export function origenDe<T>(campo: Campo<T>): Origen {
  return campo.origen;
}
