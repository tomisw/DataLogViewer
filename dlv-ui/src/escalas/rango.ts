/**
 * Aritmética de rangos de valor para los ejes Y de F1-27: combinar el rango
 * visible de varias series y añadirle margen.
 *
 * Igual que `ejes/ticks.ts` y `render/escala.ts`, esto es aritmética pura sin
 * DOM ni WebGL — se prueba en Node — y separa lo que se puede equivocar en
 * silencio (un margen que da cero, un rango que combina mal) de la fontanería
 * que usa el resultado (`gestor.ts`).
 *
 * Este módulo NO decide qué está "visible": eso depende de la ventana de
 * tiempo actual y de qué serie hay en cada cubo, algo que solo sabe quien
 * conoce el log (F1-24, la caché de cubos). Aquí solo entran ya los
 * `RangoValor` calculados por quien llama, y lo que sale es cómo combinarlos y
 * cómo darles aire.
 */

/** Un rango de valores, en la unidad ya mostrada (sin convertir aquí). */
export interface RangoValor {
  readonly min: number;
  readonly max: number;
}

/**
 * Fracción de margen añadida a cada lado del rango visible por omisión: el
 * trazo queda a un 5 % del ancho del borde en vez de tocarlo. Configurable por
 * eje (`OpcionesEje.fraccionMargen` en `gestor.ts`) — no es un umbral físico
 * de `data/umbrales.toml` (regla 3 de `CLAUDE.md`), es una preferencia de
 * dibujo, así que vive aquí como constante con posibilidad de anularla, igual
 * que `CacheDeCubos` hace con su propio `margen`.
 */
export const FRACCION_MARGEN_DEFECTO = 0.05;

/**
 * Fracción del orden de magnitud usada para el margen de un rango DEGENERADO
 * (`min === max`, canal constante). Deliberadamente una constante propia y no
 * `fraccionMargen`: un margen proporcional al ancho da cero cuando el ancho ya
 * es cero, así que el caso degenerado necesita su propia regla — ver
 * `conMargen`.
 */
const FRACCION_MARGEN_DEGENERADO = 0.1;

/**
 * Margen absoluto para el caso más degenerado posible: un canal constante en
 * exactamente cero, que no tiene orden de magnitud del que partir (`log10(0)`
 * no está definido). Un valor arbitrario pero documentado, igual que el
 * margen de 56 px de `ejes/geometria.ts#MARGEN_EJES`: sin él, un canal a cero
 * se enseñaría con `v0 === v1 === 0`.
 */
export const MARGEN_ABSOLUTO_VALOR_CERO = 1;

/**
 * ¿Es un `RangoValor` utilizable? Filtra `null`/`undefined` (serie sin datos
 * visibles esta actualización) y `NaN`/`Infinity` (canal TODO nulo: reducir
 * un array vacío o de puros `NaN` da exactamente eso). Ambos casos son "no hay
 * nada que autoescalar", y se tratan igual en `combinarRangos`.
 */
export function esRangoValido(rango: RangoValor | null | undefined): rango is RangoValor {
  return (
    rango !== null &&
    rango !== undefined &&
    Number.isFinite(rango.min) &&
    Number.isFinite(rango.max)
  );
}

/**
 * Combina el rango visible de varias series en el rango único de su eje: el
 * mínimo de los mínimos y el máximo de los máximos, como corresponde a un eje
 * que varias series comparten.
 *
 * `undefined` — no `{min: Infinity, max: -Infinity}` ni ningún otro centinela
 * numérico — si NINGUNO de los rangos de entrada es válido (todas las series
 * del eje están sin datos, el caso "canal todo nulo" de la tarea). Un
 * centinela numérico se cuela en un cálculo posterior sin avisar; `undefined`
 * obliga a quien llama (`gestor.ts#actualizar`) a decidir explícitamente qué
 * hacer, que es conservar el último rango bueno.
 */
export function combinarRangos(
  rangos: readonly (RangoValor | null | undefined)[],
): RangoValor | undefined {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  let algunoValido = false;
  for (const rango of rangos) {
    if (!esRangoValido(rango)) continue;
    algunoValido = true;
    if (rango.min < min) min = rango.min;
    if (rango.max > max) max = rango.max;
  }
  return algunoValido ? { min, max } : undefined;
}

/**
 * Añade margen a un rango para que el trazo no toque el borde del panel.
 *
 * CASO DEGENERADO — canal constante (`rango.min === rango.max`), uno de los
 * dos que pide explícitamente la tarea: un margen proporcional al ancho da
 * cero (el 5 % de 0 es 0), así que la `Vista` resultante tendría
 * `v0 === v1` y produciría exactamente la división por cero aguas abajo de la
 * que avisan `render/escala.ts#transformacion` y `ejes/coordenadas.ts#yAPixel`
 * — ambos la tratan colapsando al centro, pero aquí es mejor no dejar que
 * ocurra: un margen absoluto derivado del orden de magnitud del propio valor
 * (mismo criterio que `ejes/ticks.ts#pasoParaDegenerado`) hace que un canal
 * constante a 90 se enseñe con algo de aire alrededor de 90, con la línea
 * visible en medio del panel en vez de en su borde exacto.
 *
 * Ese margen degenerado usa `FRACCION_MARGEN_DEGENERADO`, NO el parámetro
 * `fraccion`: si se usara `fraccion` y quien llama pidiera `fraccion = 0`
 * ("sin margen"), un canal constante volvería a colapsar a `v0 === v1`. El
 * caso degenerado nunca debe depender de un margen que puede ser cero.
 */
export function conMargen(rango: RangoValor, fraccion = FRACCION_MARGEN_DEFECTO): RangoValor {
  if (!Number.isFinite(fraccion) || fraccion < 0) {
    throw new Error(
      `conMargen: la fracción de margen tiene que ser >= 0 y finita, llegó ${fraccion}`,
    );
  }
  const ancho = rango.max - rango.min;
  const margen = ancho > 0 ? ancho * fraccion : margenDegenerado(rango.min);
  return { min: rango.min - margen, max: rango.max + margen };
}

function margenDegenerado(valor: number): number {
  if (valor === 0) return MARGEN_ABSOLUTO_VALOR_CERO;
  const orden = 10 ** Math.floor(Math.log10(Math.abs(valor)));
  return orden * FRACCION_MARGEN_DEGENERADO;
}
