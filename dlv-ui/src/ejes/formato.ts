/**
 * Formato de las etiquetas de los ejes (F1-25): números y tiempo.
 *
 * Aritmética pura, igual que `ticks.ts`. Los valores que entran aquí ya están
 * en la unidad mostrada (F1-17 y el backend hacen la conversión); este módulo
 * solo decide cuántos decimales y qué forma (segundos sueltos, `mm:ss` o
 * `h:mm:ss`) sin saber qué es un canal ni una unidad física.
 *
 * Separador decimal: coma, siguiendo el locale de la app (`docs/06` §6.10:
 * «coma decimal en español»). No se usa `Intl.NumberFormat` a propósito: el
 * número de decimales no lo da la unidad (eso es F1-31/F1-32, decimales por
 * unidad y locale ES/EN) sino el paso entre ticks — mostrar más decimales de
 * los que el paso justifica es tan ilegible como mostrar de menos.
 */

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
 * Un número con `decimales` decimales y coma en vez de punto.
 *
 * Corrige el `-0` que produce `toFixed` cuando un valor negativo muy pequeño
 * redondea a cero (por ejemplo, un tick en `-0,0001` con un decimal): un
 * usuario que lee `-0,0` en un eje piensa que hay un signo con significado y
 * no lo hay. Es exactamente la clase de detalle que un rango que cruza el
 * cero saca a la luz y que no se ve en un rango que no lo cruza.
 */
export function formatearNumero(valor: number, decimales: number): string {
  const dec = Number.isFinite(decimales) && decimales >= 0 ? Math.trunc(decimales) : 0;
  let texto = valor.toFixed(dec);
  if (texto.startsWith("-") && Number(texto) === 0) {
    texto = texto.slice(1);
  }
  return texto.replace(".", ",");
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
