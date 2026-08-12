/**
 * Convierte una `CeldaPrevia` ya analizada (`celdas.ts`) en lo que se pinta en
 * la tabla del paso 3, aplicando la unidad de origen propuesta o confirmada
 * del canal — sin reimplementar la aritmética de unidades.
 *
 * REUTILIZA EL MOTOR DE CUATRO CLASES, NO LO DUPLICA
 * ====================================================
 * `docs/09` §9.7 regla 4 y el encargo de la tarea son explícitos: la clase de
 * conversión es obligatoria y sin valor por omisión. Toda muestra que se
 * previsualiza aquí es una LECTURA puntual del sensor en esa fila —nunca una
 * diferencia entre dos filas—, así que la clase que corresponde es siempre
 * `"punto"`, y se pasa por NOMBRE en cada llamada a `unidades/conversion.ts`
 * para que quede explícito en cada sitio, en vez de dejar que un valor por
 * omisión lo decida por callar.
 *
 * El camino es el de `docs/07` §7.6: para un CSV genérico, la celda YA está
 * en la unidad de origen declarada (no hay factor de canal como en Haltech,
 * `unidades/conversion.ts#convertirDesdeCrudo`) — así que aquí basta con
 * `aCanonica(valor, conversionDeOrigen, "punto")` seguido de
 * `convertirValor(canonica, conversionDeMostrada, "punto")`, los dos usando
 * exactamente el mismo catálogo (`/comandos/unidades`) que ya usa el resto de
 * la aplicación (`unidades/resolucion.ts#buscarUnidad`, que además resuelve
 * alias — "degC", "C", "Celsius" — sin que este módulo tenga que saber de
 * alias).
 *
 * SIN DIMENSIÓN RESUELTA, SE MUESTRA EN CRUDO — NUNCA SE INVENTA UNA
 * =====================================================================
 * `docs/07` §7.15, mitigación 3: "los canales sin dimensión resuelta se
 * muestran en crudo, sin unidad y sin selector". Aquí eso es simplemente NO
 * llamar a la conversión cuando no hay unidad de origen resuelta: la celda se
 * muestra con el número tal cual llegó, marcada como cruda para que la
 * interfaz pueda pintarla distinta (sin la unidad al lado).
 */

import { aCanonica, convertirValor, type Conversion } from "../unidades/conversion.ts";
import { formatearNumero, type Locale } from "../locale/numerico.ts";
import type { CeldaPrevia } from "./tipos.ts";

/** Lo que hace falta para convertir una columna: las dos conversiones afines
 * (origen->canónica, canónica->mostrada) y cuántos decimales mostrar. `null`
 * en cualquiera de las dos conversiones significa "no se pudo resolver": la
 * celda se muestra en crudo (§7.15 mitigación 3). */
export interface ConversionDeColumna {
  /** La `Conversion` de la UNIDAD DE ORIGEN (la misma forma que
   * `UnidadInfo.conversion` del catálogo): se aplica con `aCanonica` para
   * pasar del valor crudo, ya en esa unidad, a canónica. */
  readonly conversionDeOrigen: Conversion | null;
  /** La `Conversion` de la unidad EN LA QUE SE MUESTRA: se aplica con
   * `convertirValor` para pasar de canónica a la unidad mostrada. */
  readonly conversionDeMostrada: Conversion | null;
  readonly decimales: number;
}

/** Rango plausible en unidad CANÓNICA (`dlv_core.roles.Rol.plausible_min/max`,
 * `data/roles.toml`). `null` = sin rango declarado, todo es plausible. */
export interface RangoPlausible {
  readonly min: number | null;
  readonly max: number | null;
}

function esPlausible(valorCanonico: number, rango: RangoPlausible | null | undefined): boolean {
  if (rango === null || rango === undefined) return true;
  if (rango.min !== null && valorCanonico < rango.min) return false;
  if (rango.max !== null && valorCanonico > rango.max) return false;
  return true;
}

/** Cómo se pinta una celda ya lista para la tabla del paso 3. */
export interface CeldaMostrada {
  /** Texto final, o `""` para un hueco (nunca "0"). */
  readonly texto: string;
  readonly esHueco: boolean;
  /** El valor no se pudo convertir (sin dimensión resuelta): se muestra
   * crudo, sin unidad y con la marca visual de §7.15 mitigación 3. */
  readonly esCrudo: boolean;
  /** El valor convertido cae fuera del rango plausible del rol asignado
   * (§7.7 punto 2, el informe de plausibilidad). `false` si no hay rol o no
   * hay rango declarado: no se juzga lo que no se puede comparar. */
  readonly esSospechosa: boolean;
}

const HUECO: CeldaMostrada = { texto: "", esHueco: true, esCrudo: false, esSospechosa: false };

/**
 * Convierte UNA celda ya analizada. `celda.tipo === "texto"` (enums, texto
 * libre) pasa sin tocar: la conversión de unidades no tiene nada que decir
 * sobre un valor que no es un número.
 */
export function celdaMostrada(
  celda: CeldaPrevia,
  conversion: ConversionDeColumna,
  opciones: { readonly rango?: RangoPlausible | null; readonly locale?: Locale } = {},
): CeldaMostrada {
  if (celda.tipo === "hueco") return HUECO;
  if (celda.tipo === "texto") {
    return { texto: celda.texto, esHueco: false, esCrudo: false, esSospechosa: false };
  }

  // celda.tipo === "numero"
  if (conversion.conversionDeOrigen === null || conversion.conversionDeMostrada === null) {
    return {
      texto: formatearNumero(celda.valor, conversion.decimales, { locale: opciones.locale }),
      esHueco: false,
      esCrudo: true,
      esSospechosa: false,
    };
  }

  // La clase es SIEMPRE "punto": cada celda es una lectura puntual del
  // sensor en esa fila, nunca una diferencia entre dos filas (ver la cabecera
  // del módulo). Pasarla como literal, no como parámetro con valor por
  // omisión, es la regla 4 de docs/09 §9.7.
  const canonica = aCanonica(celda.valor, conversion.conversionDeOrigen, "punto");
  const mostrado = convertirValor(canonica, conversion.conversionDeMostrada, "punto");

  return {
    texto: formatearNumero(mostrado, conversion.decimales, { locale: opciones.locale }),
    esHueco: false,
    esCrudo: false,
    esSospechosa: !esPlausible(canonica, opciones.rango),
  };
}

/** La misma conversión aplicada a una fila completa (una columna por celda,
 * con SU PROPIA conversión — columnas distintas casi siempre tienen roles y
 * unidades distintas). */
export function filaMostrada(
  fila: readonly CeldaPrevia[],
  conversionesPorColumna: readonly ConversionDeColumna[],
  opciones: {
    readonly rangosPorColumna?: readonly (RangoPlausible | null)[];
    readonly locale?: Locale;
  } = {},
): readonly CeldaMostrada[] {
  return fila.map((celda, i) =>
    celdaMostrada(celda, conversionesPorColumna[i]!, {
      rango: opciones.rangosPorColumna?.[i] ?? null,
      locale: opciones.locale,
    }),
  );
}
