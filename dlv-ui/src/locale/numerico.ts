/**
 * Formateo de números con locale numérico (F1-32).
 *
 * Separador decimal y agrupación de miles en español (1.234,5) o inglés (1,234.5).
 * Se usa `Intl.NumberFormat` del entorno: es nativo, no una dependencia.
 *
 * Estos números importan en el visor: un motor ECU interpretará 1.234 como "mil
 * doscientos treinta y cuatro" en ESP y "uno coma doscientos treinta y cuatro"
 * en EN. Una mala lectura en una tabla de tuning es una decisión mal tomada.
 *
 * El número de decimales lo decide quien llama (ya viene de F1-31: resolucion.ts),
 * no este módulo. La única responsabilidad de este módulo es poner el separador
 * decimal correcto y agrupar los miles en el locale pedido.
 */

export type Locale = "es" | "en";

/**
 * Formatea un número con separador decimal y agrupación de miles según el locale.
 *
 * @param valor número a formatear
 * @param decimales número de decimales (decidido por la unidad, no por este módulo)
 * @param locale 'es' para españo (1.234,5), 'en' para inglés (1,234.5)
 * @returns número formateado con el separador decimal y la agrupación correcta
 *
 * @example
 * formatearNumeroConLocale(1234.5, 1, 'es')   // "1.234,5"
 * formatearNumeroConLocale(1234.5, 1, 'en')   // "1,234.5"
 * formatearNumeroConLocale(0.02, 2, 'es')     // "0,02"
 * formatearNumeroConLocale(0.02, 2, 'en')     // "0.02"
 */
export function formatearNumeroConLocale(
  valor: number,
  decimales: number,
  locale: Locale = "es",
): string {
  const localeString = locale === "es" ? "es-ES" : "en-US";

  // Corrige el "-0" que produce Intl.NumberFormat cuando un número
  // negativo muy pequeño redondea a cero. Igual que `formatearNumero`
  // en F1-25: un usuario que lee "-0,0" piensa que hay un signo con
  // significado y no lo hay (trampa pagada en docs/09 §9.10).
  const valorAFormato = valor === 0 && Object.is(valor, -0) ? 0 : valor;

  return new Intl.NumberFormat(localeString, {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
    useGrouping: true,
  }).format(valorAFormato);
}

/**
 * Formatea un número en español (1.234,5).
 * Atajo para `formatearNumeroConLocale(valor, decimales, 'es')`.
 */
export function formatearNumeroES(valor: number, decimales: number): string {
  return formatearNumeroConLocale(valor, decimales, "es");
}

/**
 * Formatea un número en inglés (1,234.5).
 * Atajo para `formatearNumeroConLocale(valor, decimales, 'en')`.
 */
export function formatearNumeroEN(valor: number, decimales: number): string {
  return formatearNumeroConLocale(valor, decimales, "en");
}
