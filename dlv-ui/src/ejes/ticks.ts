/**
 * Elección de ticks "bonitos" para los dos ejes (F1-25).
 *
 * Aritmética pura, sin DOM, con el mismo espíritu que `render/escala.ts`: lo
 * que se puede equivocar en silencio —un paso que no cae en 1/2/5 × 10ⁿ, un
 * rango degenerado que produce `NaN` o un bucle que no termina— vive aquí, en
 * funciones que se prueban sin navegador. `ejes.ts` solo pinta lo que estas
 * funciones deciden.
 *
 * Los ticks se calculan **sobre el rango de la `Vista`**, ya en la unidad
 * mostrada: la conversión de unidad no la hace este módulo (es F1-17 y el
 * backend), así que aquí no hay Kelvin, ni kPa, ni λ — solo números.
 */

/** Nunca se genera más que esto: cinturón de seguridad ante un paso corrupto. */
const MAX_TICKS = 1000;

/**
 * El paso "bonito" más cercano a `pasoBruto`, de la familia 1/2/5 × 10ⁿ.
 *
 * Es el algoritmo clásico de "nice numbers" (Heckbert): se normaliza el paso
 * bruto a `[1, 10)` dividiendo por su potencia de diez y se redondea al más
 * cercano de `{1, 2, 5, 10}` en escala **logarítmica**, no lineal. Los cortes
 * son las medias geométricas entre candidatos consecutivos —`√2 ≈ 1,414`,
 * `√10 ≈ 3,162`, `√50 ≈ 7,071`— y no puntos medios lineales como 1,5/3,5/7,5:
 * en escala logarítmica, 3 está más cerca de 2 que de 5
 * (`log 3 − log 2 ≈ 0,405` frente a `log 5 − log 3 ≈ 0,511`), así que un corte
 * lineal en 3 lo mandaría al hueco equivocado.
 *
 * Lanza en vez de devolver un número inventado si `pasoBruto` no es positivo
 * y finito: un rango invertido o `NaN` que llegara hasta aquí sin avisar
 * produciría una rejilla con ticks en posiciones sin sentido, el tipo de
 * fallo que solo se nota mirando el dibujo.
 */
export function pasoBonito(pasoBruto: number): number {
  if (!Number.isFinite(pasoBruto) || pasoBruto <= 0) {
    throw new Error(`pasoBonito: el paso bruto tiene que ser positivo y finito, llegó ${pasoBruto}`);
  }
  const exponente = Math.floor(Math.log10(pasoBruto));
  const base = pasoBruto / 10 ** exponente;
  const CORTE_1_2 = Math.sqrt(2); // media geométrica de 1 y 2
  const CORTE_2_5 = Math.sqrt(10); // media geométrica de 2 y 5
  const CORTE_5_10 = Math.sqrt(50); // media geométrica de 5 y 10
  let normalizado: number;
  if (base < CORTE_1_2) normalizado = 1;
  else if (base < CORTE_2_5) normalizado = 2;
  else if (base < CORTE_5_10) normalizado = 5;
  else normalizado = 10;
  return normalizado * 10 ** exponente;
}

/** Resultado de calcular los ticks de un eje: el paso elegido y los valores. */
export interface Ticks {
  /** El paso "bonito" entre ticks consecutivos, en la unidad del rango. */
  readonly paso: number;
  /** Valores de los ticks, de menor a mayor, dentro de `[lo, hi]`. */
  readonly valores: readonly number[];
}

/**
 * Genera los ticks del eje de valores (Y), en la unidad ya mostrada.
 *
 * `v0`/`v1` no se asumen ordenados (la `Vista` del renderizador no obliga
 * `v0 < v1`, ver `escala.ts`): se usa `min`/`max` para el cálculo del rango,
 * y quien pinta decide con qué signo recorrer la vista.
 *
 * Rango degenerado (`v0 === v1`, un zoom vertical a un solo valor, o una vista
 * sin datos): en vez de dividir por cero, se devuelve un único tick en ese
 * valor. Es la misma filosofía que `transformacion()` en `escala.ts` — una
 * vista sin anchura colapsa a algo diagnosticable, no a `NaN`.
 */
export function ticksValor(v0: number, v1: number, objetivo = 5): Ticks {
  const lo = Math.min(v0, v1);
  const hi = Math.max(v0, v1);
  const rango = hi - lo;
  if (!Number.isFinite(rango) || rango <= 0) {
    return { paso: pasoParaDegenerado(lo), valores: [lo] };
  }
  const paso = pasoBonito(rango / Math.max(objetivo, 1));
  return { paso, valores: valoresEnRango(lo, hi, paso) };
}

/**
 * Pasos "bonitos" de tiempo, en segundos, para pasos ≥ 1 s.
 *
 * No son 1/2/5 × 10ⁿ porque el tiempo no es decimal a partir del minuto: un
 * paso de 3 s por hora sería tan ilegible como uno de 3,7391 s. La tabla cubre
 * hasta el día; más allá (multi-día, fuera del rango típico de un log) se
 * extrapola escalando por el propio día, ver `pasoTiempoBonito`.
 */
const PASOS_TIEMPO_S: readonly number[] = [
  1, 2, 5, 10, 15, 30,
  60, 2 * 60, 5 * 60, 10 * 60, 15 * 60, 30 * 60,
  3600, 2 * 3600, 3 * 3600, 6 * 3600, 12 * 3600,
  24 * 3600,
];

/**
 * El paso "bonito" de tiempo más cercano a `pasoBruto` (segundos).
 *
 * Por debajo de 1 s se reutiliza `pasoBonito`: milisegundos y microsegundos
 * siguen siendo decimales (0,1 s; 0,02 s; …), el caso de una vista muy
 * ampliada en el tiempo. A partir de 1 s se busca el más cercano de
 * `PASOS_TIEMPO_S` en escala logarítmica, y por encima del día se generaliza
 * con `pasoBonito` sobre el número de días — así una vista de varias semanas
 * no revienta la tabla, aunque no es el caso que este producto espera ver
 * (los logs de motorsport son de minutos u horas).
 */
export function pasoTiempoBonito(pasoBruto: number): number {
  if (!Number.isFinite(pasoBruto) || pasoBruto <= 0) {
    throw new Error(
      `pasoTiempoBonito: el paso bruto tiene que ser positivo y finito, llegó ${pasoBruto}`,
    );
  }
  if (pasoBruto < 1) return pasoBonito(pasoBruto);

  const unDia = 24 * 3600;
  const ultimoDeLaTabla = PASOS_TIEMPO_S[PASOS_TIEMPO_S.length - 1]!;
  if (pasoBruto > ultimoDeLaTabla) {
    return pasoBonito(pasoBruto / unDia) * unDia;
  }

  let mejor = PASOS_TIEMPO_S[0]!;
  let mejorError = Number.POSITIVE_INFINITY;
  for (const candidato of PASOS_TIEMPO_S) {
    const error = Math.abs(Math.log(candidato) - Math.log(pasoBruto));
    if (error < mejorError) {
      mejorError = error;
      mejor = candidato;
    }
  }
  return mejor;
}

/**
 * Genera los ticks del eje de tiempo (X), en segundos.
 *
 * Misma forma que `ticksValor`: rango degenerado (`t0 === t1`, zoom horizontal
 * a un instante) da un único tick en vez de dividir por cero.
 */
export function ticksTiempo(t0: number, t1: number, objetivo = 6): Ticks {
  const lo = Math.min(t0, t1);
  const hi = Math.max(t0, t1);
  const rango = hi - lo;
  if (!Number.isFinite(rango) || rango <= 0) {
    return { paso: pasoParaDegenerado(lo), valores: [lo] };
  }
  const paso = pasoTiempoBonito(rango / Math.max(objetivo, 1));
  return { paso, valores: valoresEnRango(lo, hi, paso) };
}

/**
 * El primer tick `≥ lo` que cae en un múltiplo de `paso`, hasta `hi` inclusive.
 *
 * `Math.round(v / paso) * paso` en cada paso corrige el arrastre de error de
 * coma flotante de `v += paso` — sin él, sumar 0,1 treinta veces no da 3, da
 * 2,9999999999999996, y ese residuo se cuela en la etiqueta. La tolerancia en
 * el límite superior evita perder el último tick cuando `hi` cae justo en un
 * múltiplo de `paso` pero el residuo de coma flotante lo deja una pizca por
 * encima.
 */
function valoresEnRango(lo: number, hi: number, paso: number): number[] {
  const inicio = Math.ceil(lo / paso) * paso;
  const tolerancia = paso * 1e-9;
  const valores: number[] = [];
  let v = inicio;
  let i = 0;
  while (v <= hi + tolerancia && i < MAX_TICKS) {
    valores.push(limpiarCeroNegativo(Math.round(v / paso) * paso));
    i += 1;
    v = inicio + i * paso;
  }
  return valores;
}

/** `-0` no es un valor distinto de `0`, pero se imprime como `-0` si se deja. */
function limpiarCeroNegativo(v: number): number {
  return v === 0 ? 0 : v;
}

/**
 * Paso "nominal" para un rango degenerado: solo decide cuántos decimales
 * mostrará el único tick (vía `decimalesParaPaso` en `formato.ts`), no hay
 * rejilla que alinear. Se deriva del orden de magnitud del propio valor para
 * que un zoom degenerado a 0,003 no se muestre con cero decimales.
 */
function pasoParaDegenerado(valor: number): number {
  if (valor === 0 || !Number.isFinite(valor)) return 1;
  const orden = 10 ** Math.floor(Math.log10(Math.abs(valor)));
  return orden;
}
