/**
 * Color estable por código de estado (F3-13).
 *
 * "Estable" es el requisito literal de la tarea: el mismo código tiene que
 * pintarse siempre del mismo color, sin depender del orden en que aparecieron
 * los cubos ni de cuántos códigos distintos hay en el rango visible — si no,
 * un pan/zoom que saca y vuelve a meter un código en la vista le cambiaría el
 * color, y el propietario perdería la asociación "verde = 3ª" a media
 * sesión.
 *
 * Mismo truco que `colorPorIndice` de `app/aplicacion.ts` (ángulo áureo en
 * HSL: `137.508°` es el ángulo áureo, que reparte matices sin amontonarlos
 * aunque se pidan muchos seguidos), pero aplicado al CÓDIGO en vez de al
 * índice de aparición — es precisamente esa diferencia la que da la
 * estabilidad. Duplicado a propósito en vez de importado: `aplicacion.ts` es
 * la capa de ensamblado (F1) y este componente no depende hacia arriba de
 * ella (mismo motivo por el que `render/tipos.ts` no sabe de logs).
 */

import type { Color } from "../render/tipos.ts";

/** Saturación y luz fijas, altas para leerse bien sobre fondo oscuro (igual que `colorPorIndice`). */
const SATURACION = 0.65;
const LUZ = 0.6;
const ANGULO_AUREO = 137.508;

/** Color estable para `codigo`. Códigos negativos incluidos (p. ej. `Launch Control State`). */
export function colorPorCodigo(codigo: number): Color {
  // `% 360` de un `codigo` negativo puede dar un resultado negativo en JS
  // (a diferencia de Python): `(-101 * 137.508) % 360` es negativo, así que
  // se normaliza a `[0, 360)` con un segundo `% 360` tras sumar 360.
  const matiz = (((codigo * ANGULO_AUREO) % 360) + 360) % 360;
  const { r, g, b } = hslARgb(matiz, SATURACION, LUZ);
  return { r, g, b, a: 1 };
}

function hslARgb(h: number, s: number, l: number): { r: number; g: number; b: number } {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = h / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let r1 = 0;
  let g1 = 0;
  let b1 = 0;
  if (hp < 1) [r1, g1, b1] = [c, x, 0];
  else if (hp < 2) [r1, g1, b1] = [x, c, 0];
  else if (hp < 3) [r1, g1, b1] = [0, c, x];
  else if (hp < 4) [r1, g1, b1] = [0, x, c];
  else if (hp < 5) [r1, g1, b1] = [x, 0, c];
  else [r1, g1, b1] = [c, 0, x];
  const m = l - c / 2;
  return { r: r1 + m, g: g1 + m, b: b1 + m };
}

/** `Color` (componentes 0..1) a `rgba()` CSS. Misma fórmula que `ejes.ts#colorACss`. */
export function colorACss(color: Color): string {
  const canal = (c: number): number => Math.round(Math.max(0, Math.min(1, c)) * 255);
  return `rgba(${canal(color.r)}, ${canal(color.g)}, ${canal(color.b)}, ${color.a})`;
}
