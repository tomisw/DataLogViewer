/**
 * Escala de color SECUENCIAL, sin cero especial, para un valor numérico
 * cualquiera entre un mínimo y un máximo (F4-07).
 *
 * POR QUÉ ESTO SÍ VIVE EN EL MÓDULO GENÉRICO, A DIFERENCIA DE LO QUE DECÍA
 * `escala-divergente.ts` CUANDO SE ESCRIBIÓ
 * ============================================================================
 * La cabecera de `escala-divergente.ts` (F4-04) dice, sobre F4-07: «esa escala
 * NO va aquí: cada tarea decide su propia escala secuencial cuando le toque».
 * Ese comentario habla de la escala DIVERGENTE (centrada en cero) — no la
 * ofrece porque un avance de encendido o una densidad de knock no tienen un
 * cero especial que centrar, y forzarlos por esa escala sugeriría un punto
 * neutro que no existe. Pero una vez que le toca a F4-07 decidir «su propia
 * escala secuencial», el resultado es exactamente del mismo tipo que
 * `escalaDivergente`: aritmética de interpolación de color que no sabe nada
 * de λ, de grados de avance ni de eventos de knock — solo de un valor, un
 * rango y dos colores. Copiarla dentro de `encendido/` y otra vez dentro de
 * `knock/` habría sido la «segunda implementación que se puede desincronizar
 * de la primera» que la cabecera de `geometria.ts` señala para
 * `xAPixel`/`yAPixel`, con el mismo remedio: una sola función aquí, y que
 * cada tarea (F4-07 hoy; cualquier mapa de una LECTURA sin cero especial,
 * mañana) la parametrice con sus propios colores y su propio rango.
 *
 * A DIFERENCIA DE `escalaDivergente`, LOS COLORES NO ESTÁN FIJADOS AQUÍ
 * ========================================================================
 * `escalaDivergente` fija azul/blanco/rojo porque esos tres tonos tienen un
 * significado universal en la app (déficit/cero/exceso) que vale igual para
 * el error de λ (F4-04) y para la diferencia de dos logs (F4-08). Una escala
 * secuencial no tiene ese significado compartido: el avance de encendido no
 * es "peligroso" al crecer y la densidad de knock sí, así que un mismo par de
 * colores cableado aquí sería una opinión de dominio disfrazada de aritmética
 * — exactamente lo que este módulo, por construcción, no debe decidir. Cada
 * color de los dos extremos es un parámetro, igual que `escalaMaxima` en
 * `escalaDivergente` es un parámetro y no una constante.
 *
 * SIN LIBRERÍA DE COLOR (regla del proyecto: cero dependencias)
 * ================================================================
 * Misma interpolación lineal en RGB que `escala-divergente.ts`, y por el
 * mismo motivo no se comparte esa función auxiliar entre los dos ficheros:
 * es una línea de aritmética (`a + (b - a) * f`), y una función `export` más
 * en `escala-divergente.ts` sería tocar un fichero que otra tarea (F4-08)
 * puede estar editando a la vez por algo que cuesta menos duplicar que
 * coordinar.
 */

import type { Color } from "../render/tipos.ts";

function mezclar(a: Color, b: Color, fraccion: number): Color {
  const f = Math.min(1, Math.max(0, fraccion));
  return {
    r: a.r + (b.r - a.r) * f,
    g: a.g + (b.g - a.g) * f,
    b: a.b + (b.b - a.b) * f,
    a: a.a + (b.a - a.a) * f,
  };
}

/** El rango `[minimo, maximo]` de una escala secuencial. `maximo` tiene que ser estrictamente mayor que `minimo`. */
export interface RangoSecuencial {
  readonly minimo: number;
  readonly maximo: number;
}

/**
 * Construye una función `valor -> Color`, secuencial (sin cero especial),
 * interpolando linealmente entre `colorMinimo` (en `rango.minimo`) y
 * `colorMaximo` (en `rango.maximo`), saturada fuera de esos límites.
 *
 * `rango` es OBLIGATORIO y sin valor por omisión, mismo motivo que
 * `escalaMaxima` en `escalaDivergente` y que `umbralConfianza` en
 * `malla/tipos.ts`: un rango "típico" cableado aquí sería una opinión sobre
 * el motor disfrazada de física. Quien llama lo calcula (p. ej. con
 * `rangoSecuencialDesdeDatos`) o lo recibe de la configuración del
 * propietario.
 *
 * Lanza si `rango.maximo` no es estrictamente mayor que `rango.minimo`: un
 * rango degenerado o invertido no tiene ninguna interpolación que pintar.
 *
 * Un `valor` no finito (`NaN`) devuelve `colorMinimo`: no debería llegar
 * aquí -- `geometria.ts` no llama a `colorDeValor` para celdas vacías --,
 * pero, igual que en `escalaDivergente`, una función expuesta fuera de este
 * módulo no puede confiar en que su único llamante actual siga siendo el
 * único mañana. `colorMinimo` (el extremo "menos") es el valor por defecto
 * más razonable de los dos: para una densidad de knock, por ejemplo, es el
 * mismo color que "cero eventos", nunca el de mayor alarma.
 *
 * En los dos extremos exactos (`valor === rango.minimo`/`rango.maximo`) y al
 * saturar por fuera, se devuelve el color literal (`colorMinimo`/
 * `colorMaximo`), no el resultado de interpolar con fracción 0 o 1: la resta
 * en coma flotante de `mezclar` puede dejar un componente como
 * `0.09999999999999998` en vez de `0.1` exactos, y "el color EN el extremo es
 * el extremo" es una garantía que no debería depender del redondeo.
 */
export function escalaSecuencial(
  colorMinimo: Color,
  colorMaximo: Color,
  rango: RangoSecuencial,
): (valor: number) => Color {
  if (!(rango.maximo > rango.minimo)) {
    throw new RangeError(
      `rango.maximo (${rango.maximo}) tiene que ser > rango.minimo (${rango.minimo})`,
    );
  }
  const anchura = rango.maximo - rango.minimo;
  return (valor: number): Color => {
    if (!Number.isFinite(valor) || valor <= rango.minimo) return colorMinimo;
    if (valor >= rango.maximo) return colorMaximo;
    const fraccion = (valor - rango.minimo) / anchura;
    return mezclar(colorMinimo, colorMaximo, fraccion);
  };
}

/**
 * `RangoSecuencial` razonable a partir de los propios datos: el menor y el
 * mayor valor finito de `valores`. Mismo criterio que
 * `dlv_core.malla.bordes_por_omision` y que `escalaMaximaDesdeDatos` de
 * `escala-divergente.ts`: "el rango que el log recorrió, ni más ni menos",
 * nunca un rango típico cableado.
 *
 * Si ningún valor es finito, o si todos son idénticos (rango degenerado, la
 * misma situación que `bordes_por_omision` trata como error), devuelve
 * `null`: no hay rango que deducir, y quien llama decide qué hacer -- mismo
 * criterio que `escalaMaximaDesdeDatos` con una malla sin ninguna celda con
 * datos.
 */
export function rangoSecuencialDesdeDatos(valores: Iterable<number>): RangoSecuencial | null {
  let minimo = Infinity;
  let maximo = -Infinity;
  let huboFinito = false;
  for (const v of valores) {
    if (!Number.isFinite(v)) continue;
    huboFinito = true;
    if (v < minimo) minimo = v;
    if (v > maximo) maximo = v;
  }
  if (!huboFinito || !(maximo > minimo)) return null;
  return { minimo, maximo };
}
