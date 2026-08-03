/**
 * Formateo numérico con locale (F1-32). **El único sitio del frontend que
 * convierte un número en texto.**
 *
 * POR QUÉ ES UN MÓDULO ÚNICO Y NO UNA UTILIDAD MÁS
 * ================================================
 * Antes de esta unificación había CUATRO implementaciones: los ejes
 * (`src/ejes/formato.ts`), el sistema de unidades (`src/unidades/resolucion.ts`),
 * la tabla del cursor (`src/cursor/cursor.ts`) y este módulo. Cada tarea, en su
 * carril, resolvió el mismo problema por su cuenta — que es lo que pasa cuando
 * varios encargos avanzan en paralelo, y no es culpa de ninguno.
 *
 * El problema no era la duplicación: era que **no coincidían**. La tabla del
 * cursor usaba punto decimal y los ejes coma, así que el mismo valor salía
 * como `101.2` en la tabla y `101,2` en el eje de al lado, en la misma
 * ventana. Y este módulo agrupaba los miles mientras los otros tres no, así
 * que 40000 rpm se leía `40.000` en un sitio y `40000` en otro. Ninguna de las
 * dos cosas rompe una prueba; las dos las ve el usuario.
 *
 * LA DECISIÓN SOBRE LA AGRUPACIÓN DE MILES
 * ========================================
 * Por omisión **no se agrupa**, y el motivo no es estético.
 *
 * En español el separador de miles es el punto: `4.000`. El punto es
 * exactamente el carácter que un lector anglosajón interpreta como separador
 * DECIMAL, así que `4.000` rpm se puede leer como «cuatro». El riesgo es
 * asimétrico: agrupar puede producir una lectura falsa entre locales, mientras
 * que no agrupar solo es un poco menos elegante. En un visor de datos de motor,
 * donde casi todos los valores tienen entre tres y cinco cifras y donde E1.7
 * (docs/02 §2.5) dice que nunca hay que enseñar algo silenciosamente
 * equivocado, la elección está clara.
 *
 * `Intl.NumberFormat` con `minimumGroupingDigits: 2` habría agrupado solo a
 * partir de cinco cifras, que sería el mejor de los dos mundos; se probó y el
 * ICU de Node no lo respeta para `es-ES` (4000 sigue saliendo `4.000`). Por eso
 * la opción existe y está desactivada, en vez de depender de un ajuste que no
 * hace nada.
 *
 * QUÉ NO DECIDE ESTE MÓDULO
 * =========================
 * **Cuántos decimales.** Eso lo decide quien llama, y cada uno por un motivo
 * distinto y legítimo: los ejes por el paso entre ticks (mostrar más decimales
 * de los que el paso justifica es tan ilegible como mostrar de menos), el
 * sistema de unidades por la unidad (`data/units.toml`: es la diferencia entre
 * λ 0,995 y destruir esa información como λ 1,0) y la tabla del cursor por la
 * magnitud del valor. Este módulo solo pone el separador.
 */

export type Locale = "es" | "en";

export interface OpcionesFormato {
  /** `es` (coma decimal) o `en` (punto decimal). Español por omisión. */
  readonly locale?: Locale;
  /**
   * Agrupar los miles. **Desactivado por omisión**: ver la cabecera del
   * módulo. Se deja como opción para una exportación o un informe donde el
   * locale del lector sea conocido y la legibilidad de cifras grandes importe
   * más que la ambigüedad entre locales.
   */
  readonly agrupar?: boolean;
}

const ETIQUETA_BCP47: Record<Locale, string> = { es: "es-ES", en: "en-US" };

/**
 * Los formateadores construidos, por combinación de locale, decimales y
 * agrupación.
 *
 * No es una optimización preventiva: al unificar los cuatro formateadores
 * anteriores en este módulo, el banco del cursor (F1-29) pasó de 138 ms a
 * 5,3 s. Construir un `Intl.NumberFormat` carga datos de ICU y cuesta unos dos
 * órdenes de magnitud más que `format()`; la tabla del cursor lo hace 16 veces
 * por fotograma. Con la caché, el coste vuelve a ser el de `toFixed` sin
 * perder lo que se ganó — que haya un solo sitio donde se decide el separador.
 *
 * El número de combinaciones distintas es minúsculo (dos locales × unos pocos
 * recuentos de decimales × dos), así que no hace falta desalojar nada.
 */
const FORMATEADORES = new Map<string, Intl.NumberFormat>();

function formateador(locale: Locale, decimales: number, agrupar: boolean): Intl.NumberFormat {
  const clave = `${locale}|${decimales}|${agrupar}`;
  let f = FORMATEADORES.get(clave);
  if (f === undefined) {
    f = new Intl.NumberFormat(ETIQUETA_BCP47[locale], {
      minimumFractionDigits: decimales,
      maximumFractionDigits: decimales,
      useGrouping: agrupar,
    });
    FORMATEADORES.set(clave, f);
  }
  return f;
}

/**
 * Un número con exactamente `decimales` decimales, en el locale pedido.
 *
 * Quien llama garantiza que `valor` es finito: qué enseñar para un `NaN` o un
 * infinito es una decisión de presentación distinta en cada sitio (la tabla del
 * cursor pone «—», un eje no llega a tener ticks no finitos), y resolverla aquí
 * obligaría a todos a compartir una convención que no comparten.
 *
 * El `-0` se corrige comparando el resultado YA formateado, no el número de
 * entrada: `Intl` devuelve `-0,00` tanto para `-0` como para `-0,0001`, que
 * redondea a cero pero no ES cero. Mirar solo `Object.is(valor, -0)` deja pasar
 * el segundo caso, y es el que aparece de verdad — un tick en `-0,0001` de un
 * eje que cruza el cero. Un usuario que lee `-0,0` piensa que ese signo
 * significa algo, y no significa nada.
 */
export function formatearNumero(
  valor: number,
  decimales: number,
  opciones: OpcionesFormato = {},
): string {
  const dec = Number.isFinite(decimales) && decimales >= 0 ? Math.trunc(decimales) : 0;
  const texto = formateador(opciones.locale ?? "es", dec, opciones.agrupar ?? false).format(valor);
  // «Empieza por menos y no tiene ninguna cifra distinta de cero» es
  // exactamente «se formateó como cero negativo», sin depender de volver a
  // parsear la cadena en un locale cuyo separador acabamos de elegir nosotros.
  return texto.startsWith("-") && !/[1-9]/.test(texto) ? texto.slice(1) : texto;
}

/** Separador decimal del locale, para quien necesite el carácter suelto. */
export function separadorDecimal(locale: Locale = "es"): string {
  return locale === "es" ? "," : ".";
}
