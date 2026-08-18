/**
 * Formateo de texto para el panel de incidencias. Reutiliza
 * `locale/numerico.ts#formatearNumero`, que es —dice su propia cabecera—
 * «el único sitio del frontend que convierte un número en texto»: antes de
 * que existiera había cuatro implementaciones que no coincidían entre sí
 * (punto vs. coma decimal, con y sin agrupación de miles), y este módulo no
 * añade una quinta.
 */

import { formatearNumero as formatearNumeroLocale } from "../locale/numerico.ts";

/** Instante en segundos, con 3 decimales (milisegundo) y coma decimal en `es`. */
export function formatearInstanteS(instanteS: number): string {
  return `${formatearNumeroLocale(instanteS, 3)} s`;
}

/** Duración en segundos, o el guion de «no observada» cuando la incidencia no tiene fin. */
export function formatearDuracionS(duracionS: number | null): string {
  if (duracionS === null) return "—";
  return `${formatearNumeroLocale(duracionS, 3)} s`;
}
