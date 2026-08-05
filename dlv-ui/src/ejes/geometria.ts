/**
 * Geometría de los ejes: la aritmética que decide dónde cae cada tick, cada
 * línea de rejilla y cada entrada de leyenda (F1-25).
 *
 * Separado de `ejes.ts` por la misma razón que `render/escala.ts` está
 * separado de `render/renderizador.ts`: esto es una función pura que se
 * prueba en Node sin abrir un navegador, y `ejes.ts` es la fontanería de
 * `document.createElementNS` que solo copia estos números a atributos SVG.
 * Si la rejilla y los ticks alguna vez no coincidieran en el dibujo, el fallo
 * solo podría estar en `ejes.ts` — aquí ambos salen del mismo array.
 */

import { decimalesParaPaso, formatearNumero, formatearTiempo } from "./formato.ts";
import { ticksTiempo, ticksValor } from "./ticks.ts";
import { xAPixel, yAPixel } from "./coordenadas.ts";
import type { AreaDibujo, ConfiguracionEjes, GeometriaEjes, TickResuelto } from "./tipos.ts";

/**
 * Márgenes fijos alrededor del área de dibujo, en píxeles CSS.
 *
 * Fijos y no calculados a partir del ancho de las etiquetas a propósito: medir
 * texto exige un `canvas` o un DOM real (`getBBox`), justo lo que este módulo
 * no tiene ni necesita para ser una función pura y comprobable. 56 px a la
 * izquierda da sitio de sobra a "12345" con signo y coma; si un valor
 * necesitara más algún día, es un ajuste de una constante, no de la fórmula.
 */
export const MARGEN_EJES = {
  izquierda: 56,
  derecha: 16,
  arriba: 12,
  abajo: 28,
} as const;

/** Nunca por debajo de esto, para que un panel diminuto no dé un área negativa. */
const AREA_MINIMA_PX = 1;

/**
 * Calcula toda la geometría de los ejes a partir de la configuración.
 *
 * El orden de las operaciones importa para la garantía de alineación: los
 * ticks se generan primero (`ticksTiempo`/`ticksValor`, sobre el rango de la
 * `Vista`) y **el mismo valor** de cada tick es el que se usa para calcular su
 * píxel (`xAPixel`/`yAPixel`) y su etiqueta (`formatearTiempo`/
 * `formatearNumero`). No hay un segundo cálculo de posiciones para la rejilla:
 * `ejes.ts` dibuja la línea de rejilla en `tick.pixel`, el mismo número que ya
 * decidió dónde va la etiqueta.
 */
export function calcularGeometriaEjes(config: ConfiguracionEjes): GeometriaEjes {
  const area: AreaDibujo = {
    x: MARGEN_EJES.izquierda,
    y: MARGEN_EJES.arriba,
    ancho: Math.max(AREA_MINIMA_PX, config.anchoPx - MARGEN_EJES.izquierda - MARGEN_EJES.derecha),
    alto: Math.max(AREA_MINIMA_PX, config.altoPx - MARGEN_EJES.arriba - MARGEN_EJES.abajo),
  };

  const { vista } = config;
  const objetivoX = config.objetivoTicksX ?? 6;
  const objetivoY = config.objetivoTicksY ?? 5;

  const ticksTiempoBrutos = ticksTiempo(vista.t0, vista.t1, objetivoX);
  const ticksValorBrutos = ticksValor(vista.v0, vista.v1, objetivoY);

  const decimalesTiempo = decimalesParaPaso(ticksTiempoBrutos.paso);
  const decimalesValor = decimalesParaPaso(ticksValorBrutos.paso);
  // Formato uniforme en TODO el eje de tiempo: si se decidiera tick a tick, una
  // vista que cruza 1:00 mezclaría «58», «1:00» en la misma rejilla. Ver la
  // nota de `formatearTiempo` en `formato.ts`.
  const magnitudEjeTiempo = Math.max(Math.abs(vista.t0), Math.abs(vista.t1));

  const ticksX: TickResuelto[] = ticksTiempoBrutos.valores.map((valor) => ({
    valor,
    pixel: xAPixel(valor, vista, area.ancho),
    etiqueta: formatearTiempo(valor, decimalesTiempo, magnitudEjeTiempo),
  }));

  const ticksY: TickResuelto[] = ticksValorBrutos.valores.map((valor) => ({
    valor,
    pixel: yAPixel(valor, vista, area.alto),
    etiqueta: formatearNumero(valor, decimalesValor),
  }));

  return {
    anchoPx: config.anchoPx,
    altoPx: config.altoPx,
    area,
    ticksX,
    ticksY,
    unidadX: config.unidadX ?? "s",
    unidadY: config.unidadY,
    tituloY: config.tituloY ?? config.unidadY,
    leyenda: config.series,
  };
}
