/**
 * Conversión de coordenadas de datos a píxeles del DOM (F1-25).
 *
 * `programa.ts` lo deja dicho para quien escriba esta capa: «el eje Y no se
 * invierte [en el shader] porque las coordenadas de recorte de OpenGL ya
 * crecen hacia arriba (...); el que crece hacia abajo es el sistema del DOM,
 * y esa conversión es problema de la capa SVG (F1-25), no de esta». Esta es
 * esa conversión, y está aislada en su propio módulo puro porque es
 * exactamente el punto en el que «los datos están del revés» se cuela: si
 * `yAPixel` no invierte y `xAPixel` sí, o al revés, el trazo de WebGL2 y la
 * rejilla SVG dibujan cada uno una idea distinta de dónde está "arriba", y el
 * síntoma no es un error, es un dibujo que parece casi correcto.
 *
 * Ambas funciones toman `Vista` tal cual la define `render/tipos.ts`, sin
 * reinterpretarla: el mismo objeto que recibe el renderizador WebGL2 decide
 * dónde caen los ticks, así que no hay dos nociones de "la vista actual" que
 * puedan desincronizarse.
 */

import type { Vista } from "../render/tipos.ts";

/**
 * Píxel X (desde la izquierda del área de dibujo) de un instante `t`.
 *
 * No asume `vista.t0 < vista.t1`: igual que `transformacion()` en
 * `render/escala.ts`, `t0` siempre cae en el borde izquierdo y `t1` en el
 * derecho, sea cual sea el orden numérico. Un ancho de vista nulo (`t0 ===
 * t1`, zoom horizontal degenerado) colapsa al centro del área en vez de dar
 * `Infinity`/`NaN` — mismo criterio que la transformación WebGL: diagnosticable
 * antes que invisible.
 */
export function xAPixel(t: number, vista: Vista, anchoAreaPx: number): number {
  const ancho = vista.t1 - vista.t0;
  if (ancho === 0) return anchoAreaPx / 2;
  return ((t - vista.t0) / ancho) * anchoAreaPx;
}

/**
 * Píxel Y (desde arriba del área de dibujo) de un valor `v`.
 *
 * Aquí es donde ocurre la inversión que este módulo existe para aislar:
 * `vista.v1` (el valor "de arriba" en la vista, el que en el shader recibe
 * `escalaY` positiva y clip-Y `+1`) tiene que caer en el píxel **más
 * pequeño**, porque en el DOM el 0 está arriba. Si aquí se usara la misma
 * fórmula que en X sin invertir, la rejilla saldría al revés del trazo: el
 * fallo de silencio que describe la tarea.
 *
 * Alto nulo (`v0 === v1`) colapsa al centro, igual que `xAPixel`.
 */
export function yAPixel(v: number, vista: Vista, altoAreaPx: number): number {
  const alto = vista.v1 - vista.v0;
  if (alto === 0) return altoAreaPx / 2;
  return (1 - (v - vista.v0) / alto) * altoAreaPx;
}
