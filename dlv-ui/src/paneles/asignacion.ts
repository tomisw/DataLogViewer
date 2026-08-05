/**
 * Aritmética pura de la asignación canal → panel y de a qué panel apunta un
 * punto del puntero (F1-26).
 *
 * Mismo criterio que `reparto.ts`: nada de DOM aquí. `paneles.ts` mide
 * rectángulos reales (o el doble de pruebas los simula) y le pasa a
 * `panelEnY` una lista de rectángulos ya leídos; esta función solo decide,
 * dados esos números, cuál gana. Es la mitad de la lógica que hace que
 * "arrastrar canales entre paneles" sea una operación con un resultado
 * predecible y provable sin levantar un navegador.
 */

import type { CanalEnPanel } from "./tipos.ts";

/** Rectángulo en coordenadas de cliente (lo que da `getBoundingClientRect`). */
export interface RectanguloPx {
  readonly top: number;
  readonly bottom: number;
}

export interface PanelRect {
  readonly id: string;
  readonly rect: RectanguloPx;
}

/**
 * Qué panel contiene la coordenada `y` (coordenada de cliente, igual que
 * `PointerEvent.clientY`), o `null` si no cae dentro de ninguno.
 *
 * Compara con `>=` en el borde superior y `<` en el inferior a propósito: dos
 * paneles contiguos comparten un borde (el inferior de uno es el superior del
 * siguiente), y sin esta asimetría ese píxel exacto pertenecería a los dos
 * rectángulos a la vez — o a ninguno, según el orden de la lista.
 */
export function panelEnY(paneles: readonly PanelRect[], y: number): string | null {
  for (const panel of paneles) {
    if (y >= panel.rect.top && y < panel.rect.bottom) return panel.id;
  }
  return null;
}

/**
 * Mueve `canalId` de `panelOrigen` a `panelDestino` (pueden ser el mismo
 * panel, para reordenar), y devuelve un mapa nuevo — no muta `asignaciones`,
 * mismo criterio que `reparto.ts`: una función que se prueba comparando su
 * salida, no inspeccionando efectos secundarios.
 *
 * `indice` es la posición dentro de la lista de destino tras el movimiento;
 * por omisión, al final. Si `panelOrigen === panelDestino` el canal se quita
 * primero de su posición actual y luego se inserta en `indice`, así que
 * mover un canal dos puestos a la izquierda dentro del mismo panel usa el
 * mismo camino que moverlo a otro panel — no hay un caso especial de
 * reordenar que pueda desincronizarse del caso de mover.
 *
 * Lanza si `canalId` no está en `panelOrigen` o si algún identificador de
 * panel no existe en `asignaciones`: un desajuste aquí solo puede venir de
 * quien mantiene el rastro del arrastre en `paneles.ts` perdiendo de vista
 * cuál era el panel de origen, y es mejor que falle ruidosamente a que mueva
 * un canal equivocado en silencio.
 */
export function moverCanal(
  asignaciones: ReadonlyMap<string, readonly CanalEnPanel[]>,
  canalId: string,
  panelOrigen: string,
  panelDestino: string,
  indice?: number,
): Map<string, readonly CanalEnPanel[]> {
  const listaOrigen = asignaciones.get(panelOrigen);
  if (listaOrigen === undefined) {
    throw new Error(`no existe el panel de origen «${panelOrigen}»`);
  }
  const listaDestino = asignaciones.get(panelDestino);
  if (listaDestino === undefined) {
    throw new Error(`no existe el panel de destino «${panelDestino}»`);
  }
  const posicionOrigen = listaOrigen.findIndex((canal) => canal.id === canalId);
  if (posicionOrigen === -1) {
    throw new Error(`el canal «${canalId}» no está asignado al panel «${panelOrigen}»`);
  }
  const canal = listaOrigen[posicionOrigen]!;

  const resultado = new Map(asignaciones);

  if (panelOrigen === panelDestino) {
    const sinCanal = listaOrigen.filter((c) => c.id !== canalId);
    const destinoFinal = Math.min(Math.max(indice ?? sinCanal.length, 0), sinCanal.length);
    const nueva = [...sinCanal.slice(0, destinoFinal), canal, ...sinCanal.slice(destinoFinal)];
    resultado.set(panelOrigen, nueva);
    return resultado;
  }

  const nuevoOrigen = listaOrigen.filter((c) => c.id !== canalId);
  const destinoFinal = Math.min(Math.max(indice ?? listaDestino.length, 0), listaDestino.length);
  const nuevoDestino = [...listaDestino.slice(0, destinoFinal), canal, ...listaDestino.slice(destinoFinal)];
  resultado.set(panelOrigen, nuevoOrigen);
  resultado.set(panelDestino, nuevoDestino);
  return resultado;
}

/** Índice final de `canalId` dentro de `asignaciones.get(panelId)`, o -1 si no está. */
export function indiceDeCanal(
  asignaciones: ReadonlyMap<string, readonly CanalEnPanel[]>,
  panelId: string,
  canalId: string,
): number {
  return (asignaciones.get(panelId) ?? []).findIndex((canal) => canal.id === canalId);
}
