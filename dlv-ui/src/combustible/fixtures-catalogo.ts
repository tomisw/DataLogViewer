/**
 * Catálogo de combustibles de ejemplo, para pruebas y para quien integre el
 * componente antes de que exista una fuente de datos definitiva.
 *
 * Son valores ILUSTRATIVOS, no un fichero de datos del propietario: los tres
 * primeros (gasolina, E85, metanol) coinciden con los que ya aparecen citados
 * en `data/roles.toml` [roles.stoichiometry] (comentario: "14,7 gasolina ·
 * 9,77 E85 · 6,4 metanol") y con `data/formats/haltech_nsp.toml`
 * [tipos.Stoichiometry] (evidencia: "14700 -> 14,7 (gasolina)"); etanol puro y
 * diésel son cifras de estequiometría de combustión de uso general, no
 * medidas en un log del propietario. Si este catálogo pasa a ser el real, es
 * `data/` quien debe declararlo (ver el informe de esta tarea) — este fichero
 * solo sirve para que `resolucion.test.ts` y `selector-combustible.test.ts` no
 * dependan de esa decisión pendiente.
 */

import type { CombustibleInfo } from "./tipos.ts";

export function catalogoDeCombustiblesDePrueba(): readonly CombustibleInfo[] {
  return [
    { id: "gasolina", etiqueta: "Gasolina", estequiometria: 14.7, porOmision: true },
    { id: "e85", etiqueta: "E85", estequiometria: 9.77 },
    { id: "etanol", etiqueta: "Etanol (E100)", estequiometria: 9.0 },
    { id: "metanol", etiqueta: "Metanol", estequiometria: 6.4 },
    { id: "diesel", etiqueta: "Diésel", estequiometria: 14.5 },
  ];
}
