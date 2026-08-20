/**
 * Escala de color DIVERGENTE, centrada en cero, para un valor numérico
 * cualquiera (F4-04).
 *
 * POR QUÉ ESTO VIVE EN EL MÓDULO GENÉRICO Y NO EN `lambda/`
 * =============================================================
 * Una escala divergente no es una decisión de dominio de λ: es la forma
 * correcta de colorear CUALQUIER magnitud cuyo cero tenga un significado
 * especial —"sin desviación"— y cuyo signo importe tanto como su magnitud.
 * El error de λ (F4-04) es el primer caso, pero la comparación de dos logs
 * celda a celda (F4-08, `dlv_core.malla` lo dice explícitamente en su
 * cabecera) es OTRA diferencia con la misma forma: log A − log B, positivo
 * si A es mayor, negativo si B lo es, cero si coinciden. Poner esta función
 * en `lambda/` la habría dejado atada a λ para una tarea que no tiene nada
 * que ver con mezcla de combustible, obligando a F4-08 a copiarla o a
 * importar «hacia los lados» un módulo con nombre de otra tarea. F4-07
 * (avance de encendido, densidad de knock) SÍ es específico de dominio —esos
 * canales no tienen un cero especial que centrar— así que esa escala NO va
 * aquí: cada tarea decide su propia escala secuencial cuando le toque.
 *
 * SIN LIBRERÍA DE COLOR (regla del proyecto: cero dependencias)
 * ================================================================
 * Interpolación lineal en RGB entre dos extremos y blanco en el centro. No es
 * perceptualmente uniforme (una interpolación en Lab lo sería más), pero es
 * aritmética de una línea que no necesita traer una librería de color para
 * evitar una distorsión que, en un mapa de un puñado de celdas leído por
 * intensidad relativa, no cambia la lectura del dato.
 */

import type { Color } from "../render/tipos.ts";

/** Azul (déficit / negativo) → blanco (cero) → rojo (exceso / positivo). Mismos tonos que `dlv-topes-linea--critico` de `index.html` para el extremo positivo, por coherencia visual con el resto de la app. */
const NEGATIVO: Color = { r: 0.29, g: 0.56, b: 0.89, a: 1 };
const CERO: Color = { r: 0.94, g: 0.94, b: 0.94, a: 1 };
const POSITIVO: Color = { r: 0.87, g: 0.29, b: 0.29, a: 1 };

function mezclar(a: Color, b: Color, fraccion: number): Color {
  const f = Math.min(1, Math.max(0, fraccion));
  return {
    r: a.r + (b.r - a.r) * f,
    g: a.g + (b.g - a.g) * f,
    b: a.b + (b.b - a.b) * f,
    a: a.a + (b.a - a.a) * f,
  };
}

/**
 * Construye una función `valor -> Color`, divergente y centrada en cero,
 * saturada en `±escalaMaxima`.
 *
 * `escalaMaxima` es OBLIGATORIA y sin valor por omisión, mismo motivo que
 * `umbralConfianza` en `malla/tipos.ts`: un rango «típico» de error de λ
 * cableado aquí sería una opinión sobre el motor disfrazada de física — un
 * motor de aspiración natural y uno turbo sobrealimentado no comparten el
 * mismo error tolerable. Quien llama la calcula (p. ej. con
 * `escalaMaximaDesdeDatos`) o la recibe de la configuración del propietario.
 *
 * Un `valor` no finito (`NaN`, una celda vacía que se coló sin pasar por el
 * estado `"vacia"`) devuelve el color CERO: no debería llegar aquí —
 * `geometria.ts` no llama a `colorDeValor` para celdas vacías—, pero una
 * función expuesta fuera de este módulo no puede confiar en que su único
 * llamante actual siga siendo el único mañana.
 */
export function escalaDivergente(escalaMaxima: number): (valor: number) => Color {
  if (!(escalaMaxima > 0)) {
    throw new RangeError(`escalaMaxima tiene que ser > 0, se dio ${escalaMaxima}`);
  }
  return (valor: number): Color => {
    if (!Number.isFinite(valor)) return CERO;
    const fraccion = Math.min(1, Math.abs(valor) / escalaMaxima);
    return valor >= 0 ? mezclar(CERO, POSITIVO, fraccion) : mezclar(CERO, NEGATIVO, fraccion);
  };
}

/**
 * `escalaMaxima` razonable a partir de los propios datos: el mayor valor
 * absoluto finito de `valores`. NO es un valor por omisión escondido — es una
 * FUNCIÓN que quien llama invoca explícitamente si decide que «lo que el log
 * alcanzó» es la escala que quiere (mismo criterio que
 * `dlv_core.malla.bordes_por_omision` usa para los bordes de la malla: «el
 * rango que el log recorrió, ni más ni menos», nunca un rango típico
 * cableado). Si ningún valor es finito, devuelve `null`: no hay escala que
 * deducir, y quien llama decide qué hacer (mismo criterio que
 * `dlv_core.malla.ErrorDeMalla` para un canal sin ninguna muestra válida).
 */
export function escalaMaximaDesdeDatos(valores: Iterable<number>): number | null {
  let maximo = 0;
  let huboFinito = false;
  for (const v of valores) {
    if (!Number.isFinite(v)) continue;
    huboFinito = true;
    const absoluto = Math.abs(v);
    if (absoluto > maximo) maximo = absoluto;
  }
  if (!huboFinito) return null;
  // Un máximo de 0 (todas las celdas exactamente en cero) es un rango
  // degenerado, igual que `bordes_por_omision` lo trata: no hay escala que
  // dibujar sin inventar una anchura.
  return maximo > 0 ? maximo : null;
}
