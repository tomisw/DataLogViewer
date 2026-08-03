/**
 * Texto que hace visible el modo de un eje (F1-27): «un bloqueo invisible es
 * peor que no tenerlo», dice la tarea, y este módulo es el único punto donde
 * se decide cómo se ve.
 *
 * `GestorEscalas` no toca el DOM (misma frontera que ADR-006 traza para el
 * renderizador: aquí no hay `document`, ni SVG, ni CSS). El enganche con lo
 * que sí pinta —`ejes.ts` de F1-25— es `ConfiguracionEjes.tituloY`: quien
 * ensamble un panel con ejes múltiples debe pasarle `tituloConModo(eje)` en
 * vez de `eje.titulo` a secas, y el estado de bloqueo aparece en el título del
 * eje que `ejes.ts` ya sabe pintar, sin que este módulo tenga que aprender
 * SVG ni que `ejes.ts` tenga que aprender de bloqueos.
 */

import type { EstadoEje, ModoEscala } from "./tipos.ts";

/** Palabra que describe el modo, para componer en un título o en una prueba. */
export function etiquetaModo(modo: ModoEscala): string {
  return modo === "bloqueado" ? "bloqueado" : "autoescala";
}

/**
 * Título de eje con el modo siempre visible, en los dos sentidos: no solo
 * cuando está bloqueado. Si el texto solo cambiara al bloquear, un eje que
 * autoescala y uno que aún no se ha tocado se verían idénticos, y quien mira
 * el panel no podría distinguir "esto se ajusta solo" de "esto no se ha
 * configurado". Mostrar los dos estados es lo que hace que el bloqueo, cuando
 * ocurra, se note como un cambio y no como la aparición de algo que antes no
 * estaba.
 */
export function tituloConModo(eje: Pick<EstadoEje, "titulo" | "modo">): string {
  return `${eje.titulo} (${etiquetaModo(eje.modo)})`;
}
