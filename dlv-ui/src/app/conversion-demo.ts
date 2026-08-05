/**
 * Conversión afín TEMPORAL para pintar cubos en la unidad elegida — un
 * sustituto deliberadamente pequeño de `dlv_core.unidades` mientras esa
 * conversión no llega por HTTP (ver `datos/fuente-api.ts`).
 *
 * POR QUÉ EXISTE ESTO Y POR QUÉ NO ESTÁ EN `src/unidades/`
 * ==========================================================
 * `src/unidades/resolucion.ts` dice, en su propia cabecera, que NO lleva
 * factores de conversión a propósito: «la aritmética de la conversión en sí
 * sigue siendo exclusiva de `dlv_core.unidades`, en el backend o en quien
 * repinte los cubos». Con `FuenteApi` sin terminar, "quien repinte los
 * cubos" es este MVP, así que este módulo es exactamente esa pieza — y por
 * eso vive en `app/`, junto a quien pinta, y no en `src/unidades/`, cuyo
 * contrato deliberadamente no incluye `a`/`b`.
 *
 * Los factores de abajo son de mentira, coherentes con el catálogo
 * ilustrativo de `datos/fuente-sintetica.ts` (mismos ids de dimensión y
 * unidad) y NO con `data/units.toml` (regla 2 de `CLAUDE.md`: ese fichero es
 * dato del propietario, no se traslada al código). Cuando `FuenteApi` sirva
 * conversión real, este fichero se sustituye por lo que venga del backend —
 * probablemente ya aplicada allí, según ADR-007 — y deja de hacer falta.
 *
 * SOLO AFÍN, SOLO CLASE PUNTO
 * ============================
 * Cada valor de un cubo (`minimo`, `maximo`, `primero`, `ultimo`) es una
 * lectura puntual — incluso decimado, un `maximo` es un valor que la señal
 * alcanzó de verdad, no una diferencia — así que aplicar `a·x + b` a los
 * cuatro es correcto (Clase `PUNTO`, `docs/06` §6.5). Lo que este módulo NO
 * hace es convertir un Δ: eso ya lo resuelve `cursor/doble.ts` con la clase
 * `INTERVALO` (solo el factor `a`, nunca `b`), y esa lógica no se toca ni se
 * repite aquí.
 */

import type { CubosContinuos } from "../render/tipos.ts";

/** Factor afín `valor_destino = a * valor_canonico + b`. */
export interface FactorAfin {
  readonly a: number;
  readonly b: number;
}

/** `dimensionId -> unidadId -> factor` desde la unidad CANÓNICA de esa dimensión. */
const FACTORES: Readonly<Record<string, Readonly<Record<string, FactorAfin>>>> = {
  temperature: {
    K: { a: 1, b: 0 },
    degC: { a: 1, b: -273.15 },
    degF: { a: 1.8, b: -459.67 },
  },
  pressure: {
    kPa: { a: 1, b: 0 },
    bar: { a: 0.01, b: 0 },
    psi: { a: 0.14503773773, b: 0 },
  },
  speed: {
    "km/h": { a: 1, b: 0 },
    mph: { a: 0.62137119224, b: 0 },
  },
};

const IDENTIDAD: FactorAfin = { a: 1, b: 0 };

/**
 * El factor afín de `dimensionId -> unidadId`, o la identidad si la
 * combinación no está en la tabla (dimensiones no convertibles: `rpm`,
 * `voltage`, `percentage`, `mixture_ratio`, `angle`, `unknown` en el catálogo
 * ilustrativo — todas de una sola unidad, así que "convertir" es no tocar
 * nada). Nunca lanza: una dimensión sin factor no es un error aquí, es
 * exactamente lo que `DimensionInfo.convertible === false` ya declaró.
 */
export function factorDe(dimensionId: string, unidadId: string): FactorAfin {
  return FACTORES[dimensionId]?.[unidadId] ?? IDENTIDAD;
}

/**
 * Aplica un factor afín a los cuatro arrays de un cubo. Devuelve arrays
 * NUEVOS: `CacheDeCubos` guarda los cubos en canónica y "cambiar de unidad no
 * invalida nada" (F1-24) — mutar la entrada cacheada in situ rompería esa
 * garantía en cuanto hubiera dos paneles mostrando el mismo canal en dos
 * unidades a la vez.
 */
export function convertirCubos(cubos: CubosContinuos, factor: FactorAfin): CubosContinuos {
  if (factor.a === 1 && factor.b === 0) return cubos;
  const aplicar = (valor: number): number => valor * factor.a + factor.b;
  const n = cubos.t.length;
  const minimo = new Float32Array(n);
  const maximo = new Float32Array(n);
  const primero = new Float32Array(n);
  const ultimo = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    minimo[i] = aplicar(cubos.minimo[i]!);
    maximo[i] = aplicar(cubos.maximo[i]!);
    primero[i] = aplicar(cubos.primero[i]!);
    ultimo[i] = aplicar(cubos.ultimo[i]!);
  }
  return { t: cubos.t, tOrigen: cubos.tOrigen, minimo, maximo, primero, ultimo, factor: cubos.factor };
}

/** Convierte un único valor puntual (para el cursor: min/max ya elegidos, no un Δ). */
export function convertirValor(valor: number, factor: FactorAfin): number {
  return valor * factor.a + factor.b;
}
