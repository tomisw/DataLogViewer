/**
 * Formato de las etiquetas de los ejes (F1-25): números y tiempo.
 *
 * Aritmética pura, igual que `ticks.ts`. Los valores que entran aquí ya están
 * en la unidad mostrada (F1-17 y el backend hacen la conversión); este módulo
 * solo decide cuántos decimales y qué forma (segundos sueltos, `mm:ss` o
 * `h:mm:ss`) sin saber qué es un canal ni una unidad física.
 *
 * Separador decimal: lo pone `src/locale/numerico.ts` (F1-32), que es el único
 * sitio del frontend que convierte un número en texto. Lo que decide este
 * módulo es CUÁNTOS decimales, que en un eje los da el paso entre ticks y no
 * la unidad — mostrar más decimales de los que el paso justifica es tan
 * ilegible como mostrar de menos.
 */

import { formatearNumero as formatearNumeroLocale } from "../locale/numerico.ts";

/**
 * Cuántos decimales hacen falta para distinguir ticks separados por `paso`.
 *
 * Un paso de 5 no necesita decimales; uno de 0,02 necesita dos. Es
 * `-floor(log10(paso))` acotado por abajo en 0 — un paso de 20 o de 500 no
 * necesita decimales negativos, que no existen.
 */
export function decimalesParaPaso(paso: number): number {
  if (!Number.isFinite(paso) || paso <= 0) return 0;
  const exponente = Math.floor(Math.log10(paso));
  return Math.max(0, -exponente);
}

/**
 * Un número con `decimales` decimales, en el locale de la aplicación.
 *
 * Delega en `src/locale/numerico.ts` (F1-32), que es el único sitio del
 * frontend que convierte un número en texto. Antes de esa unificación había
 * cuatro implementaciones y no coincidían entre sí: la tabla del cursor ponía
 * punto decimal y este módulo coma, así que el mismo valor salía como `101.2`
 * en la tabla y `101,2` en el eje de al lado.
 *
 * Lo que sigue decidiendo ESTE módulo es **cuántos** decimales, y por eso
 * `decimalesParaPaso` no se ha movido: en un eje los decimales los da el paso
 * entre ticks, no la unidad. Es la parte que no se puede compartir.
 */
export function formatearNumero(valor: number, decimales: number): string {
  return formatearNumeroLocale(valor, decimales);
}

/**
 * Etiqueta de un instante de tiempo (segundos) en la forma que corresponde a
 * la magnitud del eje: segundos sueltos por debajo de un minuto, `m:ss` por
 * debajo de una hora, `h:mm:ss` en adelante.
 *
 * `magnitudEje` — no `segundosAbsolutos` ni el rango visible — es lo que
 * decide la forma, y a propósito: si se decidiera tick a tick, una vista que
 * cruza el minuto 1:00 mostraría «58», «59», «1:00», «1:01» en el mismo eje,
 * un cambio de formato a mitad de rejilla que es más confuso que útil. Con
 * `magnitudEje = max(|t0|, |t1|)` calculado una vez por eje, TODOS los ticks
 * de una vista que cruza esa frontera se muestran ya en `m:ss`.
 *
 * También es lo que resuelve el caso «ventana de 20 ms a las 8 horas de
 * log»: el rango visible es minúsculo, pero el instante absoluto no lo es, y
 * mostrar «0,005» sin más contexto no dice a qué hora del log corresponde.
 * `magnitudEje` grande fuerza `h:mm:ss` aunque el rango sea milisegundos.
 *
 * `decimales` viene de `decimalesParaPaso(paso)`, calculado una vez para todo
 * el eje: es el paso entre ticks, no la magnitud, el que decide cuánta
 * precisión hace falta.
 */
export function formatearTiempo(
  segundos: number,
  decimales: number,
  magnitudEje: number,
): string {
  const signo = segundos < 0 ? "-" : "";
  const totalMilisegundos = Math.round(Math.abs(segundos) * 1000);
  const magnitud = Math.abs(magnitudEje);

  if (magnitud < 60) {
    return `${signo}${formatearNumero(totalMilisegundos / 1000, decimales)}`;
  }

  const minutosTotales = Math.floor(totalMilisegundos / 60_000);
  const milisegundosDelMinuto = totalMilisegundos - minutosTotales * 60_000;
  const anchoSegundos = decimales === 0 ? 2 : decimales + 3; // "SS" o "SS,ddd…"
  const segundosTexto = formatearNumero(milisegundosDelMinuto / 1000, decimales).padStart(
    anchoSegundos,
    "0",
  );

  if (magnitud < 3600) {
    return `${signo}${minutosTotales}:${segundosTexto}`;
  }

  const horas = Math.floor(minutosTotales / 60);
  const minutos = minutosTotales % 60;
  return `${signo}${horas}:${String(minutos).padStart(2, "0")}:${segundosTexto}`;
}
