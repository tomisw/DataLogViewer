/**
 * Geometría del carril de estado: la aritmética que decide dónde empieza y
 * acaba cada banda de color y cada marca de transición (F3-13).
 *
 * Separado de `carril-estado.ts` por la misma razón que `ejes/geometria.ts`
 * está separado de `ejes/ejes.ts`: esto es una función pura que se prueba en
 * Node sin abrir un navegador, y `carril-estado.ts` es la fontanería de
 * `document.createElementNS` que solo copia estos números a atributos SVG.
 *
 * LA DECISIÓN QUE HACE LEGIBLE EL CARRIL
 * =======================================
 * Un cubo por rectángulo sería tan ilegible como la línea que este componente
 * viene a reemplazar (a nivel L6 hay decenas de miles de cubos en pantalla,
 * la mayoría con el mismo código que su vecino). En vez de eso, los cubos
 * CONSECUTIVOS con la misma moda se fusionan en una sola banda: es la lectura
 * "el motor estuvo en 3ª desde el segundo 12 hasta el 18", no "aquí hay 400
 * segmentos que dicen 3".
 *
 * LO QUE NO SE FUSIONA NUNCA
 * ===========================
 * `NivelEnum.hubo_transicion` (`piramide.py`): si dos cubos vecinos tienen la
 * MISMA moda pero uno de ellos tuvo una transición real por debajo (varios
 * valores distintos que decimaron a la misma moda), la banda de color los
 * fusiona igualmente —eso es correcto, la moda dominante es la misma—, pero
 * la marca de transición de ESE cubo se conserva. Por eso `transiciones` se
 * calcula cubo a cubo, nunca banda a banda: fusionar también las marcas sería
 * exactamente el parpadeo que la variante ENUM de la pirámide existe para
 * evitar mostrar, aplicado al revés (esconder un cambio real detrás de una
 * banda tranquila).
 */

import { colorPorCodigo } from "./color.ts";
import type {
  BandaCarril,
  ConfiguracionCarril,
  CubosEnum,
  GeometriaCarril,
  MarcaTransicion,
  RangoTiempo,
} from "./tipos.ts";

/** Alto de banda por omisión, en píxeles CSS, si `ConfiguracionCarril.altoPx` no se da. */
export const ALTO_BANDA_DEFECTO = 24;

/** Ancho fijo de una marca de transición, en píxeles CSS: un trazo fino, no otra banda. */
export const ANCHO_MARCA_TRANSICION = 2;

/**
 * Píxel X (desde la izquierda del carril) de un instante `t`, dado el rango
 * visible y el ancho del área. Misma fórmula que `ejes/coordenadas.ts#xAPixel`
 * pero reimplementada aquí en vez de importada: esa función exige un `Vista`
 * completo (con `v0`/`v1`), y un carril de estado no tiene eje de valores —
 * pedirle un rango de valores de mentira solo para satisfacer el tipo sería
 * la clase de acoplamiento que ADR-006 pide evitar entre módulos que no se
 * necesitan.
 *
 * Un rango degenerado (`t1 === t0`) colapsa al centro en vez de dar
 * `Infinity`/`NaN`, mismo criterio que `xAPixel`.
 */
function tAPixel(t: number, vista: RangoTiempo, anchoPx: number): number {
  const ancho = vista.t1 - vista.t0;
  if (ancho === 0) return anchoPx / 2;
  return ((t - vista.t0) / ancho) * anchoPx;
}

/**
 * Comprueba que los arrays de `CubosEnum` miden lo mismo. Mismo motivo que
 * `render/escala.ts#validarCubos`: un array descuadrado no revienta al leerlo
 * (da `undefined`/`NaN`), se ve como un carril con bandas en sitios
 * incoherentes, y eso es mucho más caro de depurar que un error con nombres.
 */
function validarCubos(cubos: CubosEnum): void {
  const n = cubos.t.length;
  if (cubos.moda.length !== n) {
    throw new Error(
      `cubos incoherentes: \`t\` tiene ${n} entradas y \`moda\` tiene ${cubos.moda.length}`,
    );
  }
  if (cubos.huboTransicion.length !== n) {
    throw new Error(
      `cubos incoherentes: \`t\` tiene ${n} entradas y \`huboTransicion\` tiene ` +
        `${cubos.huboTransicion.length}`,
    );
  }
}

/** El límite derecho en píxeles del cubo `indice` (el límite izquierdo del siguiente, o el borde del carril si es el último). */
function finPixelDe(
  indice: number,
  pixelesInicio: readonly number[],
  vista: RangoTiempo,
  anchoPx: number,
): number {
  const siguiente = pixelesInicio[indice + 1];
  if (siguiente !== undefined) return siguiente;
  return tAPixel(vista.t1, vista, anchoPx);
}

/**
 * Calcula toda la geometría del carril a partir de la configuración.
 *
 * Cubos vacíos (`cubos.t.length === 0`) dan un carril sin bandas ni
 * transiciones — no es un error, es un canal sin datos en el rango pedido.
 */
export function calcularGeometriaCarril(config: ConfiguracionCarril): GeometriaCarril {
  const { cubos, etiquetas, vista, anchoPx } = config;
  const altoPx = config.altoPx ?? ALTO_BANDA_DEFECTO;
  validarCubos(cubos);

  const n = cubos.t.length;
  if (n === 0) return { anchoPx, altoPx, bandas: [], transiciones: [] };

  const pixelesInicio: number[] = [];
  for (let i = 0; i < n; i += 1) {
    pixelesInicio.push(tAPixel(cubos.tOrigen + cubos.t[i]!, vista, anchoPx));
  }

  const bandas: BandaCarril[] = [];
  let inicioTramo = 0;
  for (let i = 1; i <= n; i += 1) {
    const cambia = i === n || cubos.moda[i] !== cubos.moda[inicioTramo];
    if (!cambia) continue;
    const codigo = cubos.moda[inicioTramo]!;
    const xPx = pixelesInicio[inicioTramo]!;
    const xFin = finPixelDe(i - 1, pixelesInicio, vista, anchoPx);
    const tieneEtiqueta = etiquetas.has(codigo);
    bandas.push({
      codigo,
      etiqueta: tieneEtiqueta ? etiquetas.get(codigo)! : String(codigo),
      etiquetaFaltante: !tieneEtiqueta,
      color: colorPorCodigo(codigo),
      xPx,
      anchoPx: Math.max(0, xFin - xPx),
    });
    inicioTramo = i;
  }

  const transiciones: MarcaTransicion[] = [];
  for (let i = 0; i < n; i += 1) {
    if (cubos.huboTransicion[i] === 0) continue;
    const xPx = pixelesInicio[i]!;
    const xFinCubo = finPixelDe(i, pixelesInicio, vista, anchoPx);
    // Ancho fijo pequeño, anclado al inicio del cubo: una marca se lee como
    // marca solo si es más fina que la banda que la contiene. Si el cubo es
    // más estrecho que la marca (zoom muy alejado, muchos cubos por píxel),
    // se recorta al ancho real del cubo para no invadir el vecino.
    const anchoDisponible = Math.max(0, xFinCubo - xPx);
    transiciones.push({ xPx, anchoPx: Math.min(ANCHO_MARCA_TRANSICION, anchoDisponible) });
  }

  return { anchoPx, altoPx, bandas, transiciones };
}
