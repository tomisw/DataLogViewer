/**
 * Formateo de texto para el panel de incidencias. Reutiliza
 * `locale/numerico.ts#formatearNumero`, que es —dice su propia cabecera—
 * «el único sitio del frontend que convierte un número en texto»: antes de
 * que existiera había cuatro implementaciones que no coincidían entre sí
 * (punto vs. coma decimal, con y sin agrupación de miles), y este módulo no
 * añade una quinta.
 *
 * POR QUÉ EL LOCALE DEL NÚMERO SALE DE `idioma.ts` (F5-10)
 * ============================================================
 * Antes se llamaba a `formatearNumeroLocale` sin `locale`, así que el número
 * salía siempre en español aunque el resto de la interfaz cambiara a inglés.
 * `panel-incidencias.ts` ya pasa el texto de este módulo por `t()`; si el
 * número no siguiera al mismo idioma activo, un panel en inglés enseñaría
 * `Jump to the instant it started (12,345 s)` -- la coma decimal española
 * delante de un botón en inglés, el mismo defecto de coherencia que la tarea
 * F5-10 tiene que evitar (ver la cabecera de `locale/idioma.ts`).
 */

import { formatearNumero as formatearNumeroLocale } from "../locale/numerico.ts";
import { obtenerIdiomaActual } from "../locale/idioma.ts";

/** Instante en segundos, con 3 decimales (milisegundo) y el separador del idioma activo. */
export function formatearInstanteS(instanteS: number): string {
  return `${formatearNumeroLocale(instanteS, 3, { locale: obtenerIdiomaActual() })} s`;
}

/** Duración en segundos, o el guion de «no observada» cuando la incidencia no tiene fin. */
export function formatearDuracionS(duracionS: number | null): string {
  if (duracionS === null) return "—";
  return `${formatearNumeroLocale(duracionS, 3, { locale: obtenerIdiomaActual() })} s`;
}
