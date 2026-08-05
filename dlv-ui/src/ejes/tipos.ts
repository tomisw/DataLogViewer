/**
 * Contrato de datos de la capa de ejes (F1-25).
 *
 * Igual que `render/tipos.ts` marca la frontera del renderizador WebGL2, este
 * fichero marca la de la capa SVG: recibe la `Vista` que ya usa el
 * renderizador (mismo objeto, ver `coordenadas.ts`), un rectángulo en píxeles
 * de **CSS**, el nombre de la unidad ya elegida y una lista de series para la
 * leyenda. **No convierte unidades** — eso es F1-17 y el backend — así que
 * aquí no hay `Kelvin`, ni factores, ni clase de conversión.
 *
 * Deliberadamente en píxeles de CSS y no de dispositivo: a diferencia de
 * `render/tipos.ts#Viewport` (píxeles de dispositivo, multiplicados por el
 * DPR, porque así se dimensiona el lienzo WebGL), el SVG se dimensiona en
 * unidades CSS y es el propio navegador quien lo escala al DPR. Reutilizar
 * `Viewport` aquí habría mezclado dos escalas distintas bajo el mismo nombre.
 */

import type { Color, Vista } from "../render/tipos.ts";

/** Una entrada de la leyenda: qué serie es, de qué color y en qué unidad. */
export interface SerieLeyenda {
  readonly id: string;
  readonly nombre: string;
  readonly color: Color;
  readonly unidad: string;
}

/** Lo que necesita `calcularGeometriaEjes` para decidir dónde va cada cosa. */
export interface ConfiguracionEjes {
  readonly vista: Vista;
  /** Ancho del SVG completo, en píxeles CSS (incluye los márgenes de los ejes). */
  readonly anchoPx: number;
  /** Alto del SVG completo, en píxeles CSS. */
  readonly altoPx: number;
  /** Nombre de la unidad del eje X. Por omisión "s": `Vista.t0`/`t1` son segundos. */
  readonly unidadX?: string;
  /** Nombre de la unidad del eje Y, ya la elegida por el usuario (F1-17). */
  readonly unidadY: string;
  /** Título del eje Y. Por omisión, la propia unidad. */
  readonly tituloY?: string;
  /** Series a listar en la leyenda. Vacío si no hace falta leyenda. */
  readonly series: readonly SerieLeyenda[];
  /** Cuántos ticks se buscan en X. Por omisión 6: es una guía, no una cuota. */
  readonly objetivoTicksX?: number;
  /** Cuántos ticks se buscan en Y. Por omisión 5. */
  readonly objetivoTicksY?: number;
}

/** Un tick ya resuelto: su valor de dato, su etiqueta y su píxel. */
export interface TickResuelto {
  readonly valor: number;
  readonly etiqueta: string;
  readonly pixel: number;
}

/** El rectángulo interior donde se dibujan datos, rejilla y ticks. */
export interface AreaDibujo {
  readonly x: number;
  readonly y: number;
  readonly ancho: number;
  readonly alto: number;
}

/**
 * Salida de `calcularGeometriaEjes`: todo lo que `ejes.ts` necesita para
 * pintar, ya resuelto a píxeles. Nada de esto vuelve a decidir nada — es la
 * frontera entre la aritmética (probada sin DOM) y la fontanería SVG (no
 * probada aquí por lo mismo que `programa.ts` no prueba shaders: falla
 * ruidosamente si algo no compila o no se ve).
 */
export interface GeometriaEjes {
  readonly anchoPx: number;
  readonly altoPx: number;
  readonly area: AreaDibujo;
  readonly ticksX: readonly TickResuelto[];
  readonly ticksY: readonly TickResuelto[];
  readonly unidadX: string;
  readonly unidadY: string;
  readonly tituloY: string;
  readonly leyenda: readonly SerieLeyenda[];
}
