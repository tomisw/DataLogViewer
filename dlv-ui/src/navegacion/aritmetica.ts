/**
 * Aritmética pura de navegación (F1-28): la parte que se prueba sin DOM.
 *
 * Todo lo que decide CÓMO cambia una `Vista` vive aquí, separado de QUIÉN la
 * pide (`controlador.ts`, que solo traduce eventos del navegador en llamadas
 * a estas funciones). Es la misma separación que `render/escala.ts` hace para
 * el renderizador y por el mismo motivo: una función que convierte un
 * desplazamiento de rueda en un rectángulo se revisa leyendo; un oyente de
 * eventos, no.
 *
 * Nada de aquí dibuja ni conoce el DOM — coherente con F1-23 (`Vista` es
 * `{t0,t1,v0,v1}` y moverla es solo eso).
 */

import type { Vista } from "../render/tipos.ts";

/**
 * Sentido del último movimiento horizontal aplicado a la vista.
 *
 * `1` si el centro temporal avanzó (t creciente), `-1` si retrocedió, `0` si
 * no hubo cambio horizontal apreciable (un pan solo vertical, por ejemplo).
 *
 * Es la palanca que F1-24 dejó anotada en `cache-cubos.ts`: el margen de
 * prefetch de la caché se ensancha por igual a los dos lados, así que solo
 * aprovecha la mitad cuando el movimiento tiene una dirección clara — y el
 * lado contrario al que se avanza no se llega a usar. Este módulo es quien
 * conoce esa dirección en el instante en que ocurre (la caché y el
 * renderizador no), así que la expone para que quien orqueste ambos pueda
 * sesgar el margen hacia aquí en vez de reservarlo por igual a ciegas.
 */
export type Direccion = -1 | 0 | 1;

/** Cambio relativo mínimo del centro temporal para contar como movimiento. */
const EPSILON_RELATIVO_DIRECCION = 1e-9;

/**
 * Compara dos vistas consecutivas y dice hacia dónde se movió el tiempo.
 *
 * Se compara el CENTRO temporal, no `t0`: un zoom centrado en el puntero
 * (no en el centro del panel) también desplaza `t0` y `t1` de forma
 * asimétrica, y ese desplazamiento es tan real para el prefetch como el de
 * un arrastre. El umbral relativo (y no un `!==` a secas) evita que el ruido
 * de punto flotante de una vista que en la práctica no se movió horizontal-
 * mente (p. ej. solo cambió el eje de valores) se lea como una dirección.
 */
export function direccionDe(anterior: Vista, nueva: Vista): Direccion {
  const anchoRef = Math.max(anterior.t1 - anterior.t0, nueva.t1 - nueva.t0, 0);
  if (anchoRef === 0) return 0;
  const deltaCentro = (nueva.t0 + nueva.t1) / 2 - (anterior.t0 + anterior.t1) / 2;
  if (Math.abs(deltaCentro) <= anchoRef * EPSILON_RELATIVO_DIRECCION) return 0;
  return deltaCentro > 0 ? 1 : -1;
}

/**
 * Recentra el eje temporal de `vista` en `tCentro`, conservando su ancho y su
 * eje de valores tal cual.
 *
 * Es la aritmética de "saltar a un instante" (conmutador de vistas, panel de incidencias):
 * a diferencia de `desplazar` -que mueve por un DELTA- esta función lleva el
 * centro a un instante ABSOLUTO, que es lo que pide
 * `incidencias/panel-incidencias.ts#OpcionesPanelIncidencias.alSaltarAInstante`.
 * No toca `v0`/`v1` por el mismo motivo que la rueda no toca el eje de
 * valores (`controlador.ts`, cabecera): esta función no sabe de autoescala,
 * solo de encuadre temporal.
 */
export function centrarEnT(vista: Vista, tCentro: number): Vista {
  const ancho = vista.t1 - vista.t0;
  return { ...vista, t0: tCentro - ancho / 2, t1: tCentro + ancho / 2 };
}

/** Desplaza la vista por deltas ya expresados en unidades de datos. */
export function desplazar(vista: Vista, deltaT: number, deltaV: number): Vista {
  return {
    t0: vista.t0 + deltaT,
    t1: vista.t1 + deltaT,
    v0: vista.v0 + deltaV,
    v1: vista.v1 + deltaV,
  };
}

/**
 * Desplaza la vista a partir de un arrastre medido en píxeles de panel.
 *
 * El contenido "sigue" al puntero, que es el modelo mental de arrastrar un
 * mapa: mover el puntero `dxPx` hacia la derecha adelanta lo que había fuera
 * de pantalla por la izquierda, así que la vista retrocede en el tiempo
 * (`t0` baja). En el eje de valores el signo se invierte respecto al de X
 * porque el píxel crece hacia abajo y el valor crece hacia arriba — la misma
 * inversión que resuelve `zoomEnPunto` para `fraccionY`.
 *
 * Un `anchoPx`/`altoPx` no positivo (panel de tamaño 0, típico a mitad de un
 * redimensionado) no desplaza ese eje en vez de dividir por cero.
 */
export function desplazarPx(
  vista: Vista,
  deltaXPx: number,
  deltaYPx: number,
  anchoPx: number,
  altoPx: number,
): Vista {
  const ancho = vista.t1 - vista.t0;
  const alto = vista.v1 - vista.v0;
  const deltaT = anchoPx <= 0 ? 0 : -(deltaXPx / anchoPx) * ancho;
  const deltaV = altoPx <= 0 ? 0 : (deltaYPx / altoPx) * alto;
  return desplazar(vista, deltaT, deltaV);
}

/**
 * Suelo de anchura/altura tras un zoom: el menor positivo representable.
 *
 * No es una cota de negocio (no dice "no ampliar más de X"): es la última
 * defensa contra la infrarrepresentación de punto flotante. Miles de zooms
 * de ampliación seguidos harían que `ancho / factor` subrepase hacia 0 en
 * lugar de mantenerse positivo y cada vez más pequeño; sin este suelo, el
 * primer `ancho / factor` que subrepase a 0 exacto invertiría la vista
 * (`t1 === t0`, el caso degenerado que `render/escala.ts` ya documenta) en la
 * siguiente vuelta. Con el suelo, el resultado se queda clavado en el valor
 * positivo más pequeño posible: sigue siendo una vista válida, nunca una
 * invertida.
 */
const ANCHURA_MINIMA = Number.MIN_VALUE;

function factorValido(factor: number): boolean {
  return Number.isFinite(factor) && factor > 0;
}

/**
 * Zoom centrado en un punto del panel, con un factor independiente por eje.
 *
 * `fraccionX`/`fraccionY` son la posición del puntero como fracción del
 * panel, en la misma convención que los píxeles de pantalla: `fraccionX`
 * crece hacia la derecha (0 = borde izquierdo, 1 = borde derecho) y
 * `fraccionY` crece hacia ABAJO (0 = borde superior, 1 = borde inferior). Eso
 * es al revés que el valor de datos, que crece hacia arriba (`v1` es "arriba"
 * en `render/escala.ts`); la inversión se resuelve aquí para que quien llama
 * solo tenga que pasar la posición de pantalla tal cual, sin traducirla.
 *
 * `factorX`/`factorY` > 1 amplía ese eje (la vista se estrecha), < 1 aleja, 1
 * no lo toca. Separarlos por eje es lo que permite que la rueda amplíe solo
 * el tiempo —el eje Y todavía no tiene autoescala ni bloqueo (eso es F1-27,
 * y tocar ese eje aquí sin saber cómo se va a resolver adelantaría una
 * decisión que no es de este módulo)— mientras el teclado usa el mismo
 * primitivo con `factorY = 1`.
 *
 * Nunca invierte la vista: un factor no positivo o no finito es un error de
 * quien llama (no un caso de negocio con el que seguir) y se rechaza aquí en
 * vez de propagar un `NaN` o un `Infinity` silencioso; el ancho/alto
 * resultante nunca baja de `ANCHURA_MINIMA`, así que `t1 > t0` y `v1 > v0` se
 * mantienen siempre, sin excepción.
 */
export function zoomEnPunto(
  vista: Vista,
  factorX: number,
  factorY: number,
  fraccionX: number,
  fraccionY: number,
): Vista {
  if (!factorValido(factorX) || !factorValido(factorY)) {
    throw new Error(
      `zoomEnPunto: factor de zoom inválido (factorX=${factorX}, factorY=${factorY}); ` +
        "tiene que ser finito y positivo",
    );
  }
  const anchoActual = vista.t1 - vista.t0;
  const altoActual = vista.v1 - vista.v0;
  const anchoNuevo = Math.max(anchoActual / factorX, ANCHURA_MINIMA);
  const altoNuevo = Math.max(altoActual / factorY, ANCHURA_MINIMA);

  const puntoT = vista.t0 + fraccionX * anchoActual;
  const t0 = puntoT - fraccionX * anchoNuevo;

  // `fraccionY` es "desde arriba" en píxeles; `v1` es el valor de arriba.
  const puntoV = vista.v1 - fraccionY * altoActual;
  const v1 = puntoV + fraccionY * altoNuevo;

  return { t0, t1: t0 + anchoNuevo, v0: v1 - altoNuevo, v1 };
}
