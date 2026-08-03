/**
 * Doble cursor y Δ, con la clase INTERVALO (F1-30). **Puerta G1.**
 *
 * LA TRAMPA QUE ESTE MÓDULO EXISTE PARA NO CAER
 * =============================================
 * `docs/06` §6.5 y §6.6: un Δ de 10 K son 10 °C y 18 °F, **nunca −263,15 °C**.
 * La conversión correcta para un punto y la correcta para una diferencia se
 * escriben casi igual y solo una de las dos lleva el `+ b`. `dlv-core` lo
 * resuelve con la clase obligatoria (`Clase.PUNTO` / `Clase.INTERVALO`); este
 * módulo es la mitad de la misma regla que vive en el frontend.
 *
 * Y es un fallo silencioso en el peor sentido posible. −263,15 °C se ve raro y
 * alguien lo notaría; pero un Δ entre dos temperaturas cercanas sale plausible
 * aunque esté 273 grados desplazado, y nadie lo ve leyendo la pantalla. Se ve
 * cuando alguien toma una decisión de mapa con él.
 *
 * CÓMO SE DEFIENDE, QUE NO ES CON UNA REGLA QUE HAYA QUE RECORDAR
 * ==============================================================
 * El Δ se calcula **restando los dos valores que ya están en la unidad
 * mostrada**. Nunca se convierte un Δ desde la canónica. En una conversión afín
 * eso es exactamente correcto —al restar dos puntos, el `+ b` se cancela solo—
 * y, sobre todo, es correcto *por construcción*: este código no tiene acceso a
 * `b`, así que no puede aplicarlo mal ni olvidarse de no aplicarlo.
 *
 * La única operación que sí toca un Δ es `convertirDelta`, para cuando el
 * usuario cambia de unidad con el doble cursor puesto. Ahí sí hay que elegir, y
 * la elección es INTERVALO: solo el factor, jamás el desplazamiento.
 *
 * LOS TRES CASOS EN LOS QUE UN Δ NO EXISTE, Y NO SE INVENTA
 * ========================================================
 * E1.7 («avisa y sigue», docs/02 §2.5) aplicado a un número que la interfaz no
 * puede dar: se dice que no se puede y por qué, en vez de enseñar algo
 * plausible.
 *
 *   1. **Unidad recíproca** (λ ↔ φ, periodo ↔ frecuencia, L/100 km ↔ mpg). No
 *      es lineal, así que un Δ en una unidad no es un Δ en la otra por ningún
 *      factor. `dlv_core.unidades.Reciproca._exige_punto` lanza un error en
 *      este caso; aquí no se puede lanzar —la interfaz tiene que seguir
 *      pintando— así que se devuelve un Δ indefinido con su motivo.
 *   2. **Unidad parametrizada cuyo parámetro cambió entre los dos cursores**
 *      (λ → AFR con la estequiometría en un canal del propio log). La
 *      conversión es lineal, sí, pero con un factor DISTINTO en cada extremo:
 *      restar los dos valores mostrados da un número que no es el Δ de nada.
 *      Pasa de verdad en un log con cambio de mezcla de combustible.
 *   3. **Uno de los dos cursores sin dato.** Un hueco no es un cero
 *      (docs/01), así que un Δ contra un hueco no es «el otro valor».
 *
 * A NIVEL DECIMADO, EL Δ TAMPOCO ES UN NÚMERO
 * ===========================================
 * F1-29 ya decidió que a `factor > 1` lo que hay en un cubo no es un valor sino
 * un rango. La consecuencia para el Δ es aritmética de intervalos: si A está en
 * `[a₀, a₁]` y B en `[b₀, b₁]`, el Δ está en `[b₀ − a₁, b₁ − a₀]`, y ese rango
 * puede incluir el cero aunque los dos cubos «se vean» distintos. Enseñar un
 * único número (por ejemplo la diferencia de los `último`) sería dar por
 * medido algo que no se midió — el mismo error que da por medido un
 * presupuesto que nadie ejecutó.
 */

import type { CacheDeCubos, ClaveCubos } from "../datos/cache-cubos.ts";
import { valorEn } from "../datos/cache-cubos.ts";

/**
 * Qué representa un valor, y por tanto cómo se convierte (`docs/06` §6.5).
 * Espejo de `dlv_core.unidades.Clase`. Sin valor por omisión, igual que allí:
 * que no se pueda «olvidar» declararla es la mitad de la defensa.
 */
export enum Clase {
  PUNTO = "punto",
  INTERVALO = "intervalo",
  TASA = "tasa",
  VARIANZA = "varianza",
}

/**
 * Forma de la conversión de la unidad mostrada. Es lo mínimo que hace falta
 * saber aquí: no el factor ni el desplazamiento —este módulo no convierte
 * puntos— sino si un Δ tiene sentido y bajo qué condición.
 */
export type FormaConversion =
  | {
      readonly tipo: "afin";
      /** Factor `a`. El desplazamiento `b` NO está aquí: no hace falta y no
       *  poder verlo es lo que impide aplicarlo a un Δ. */
      readonly factor: number;
    }
  | { readonly tipo: "reciproca" }
  | {
      readonly tipo: "parametrizada";
      readonly factor: number;
      /** Rol del canal del que sale el factor (p. ej. la estequiometría). */
      readonly parametroRol: string;
    };

/** Lo que se lee en un instante para un canal: un punto o un rango decimado. */
export type LecturaCursor =
  | { readonly hay: false }
  | {
      readonly hay: true;
      /** `true` si el nivel no decima (`factor === 1`) y esto es una muestra. */
      readonly esMuestra: boolean;
      readonly minimo: number;
      readonly maximo: number;
      /** Valor del parámetro de conversión en ese instante, si la unidad lo usa. */
      readonly parametro?: number;
    };

export type Delta =
  | {
      readonly definido: true;
      readonly clase: Clase.INTERVALO;
      /** Extremo inferior del Δ. Igual a `maximo` cuando los dos extremos son
       *  muestras reales; distinto en cuanto uno de los dos venga decimado. */
      readonly minimo: number;
      readonly maximo: number;
      /** `true` si los dos extremos eran muestras reales: entonces el Δ es un
       *  número, no un rango. Es lo que decide si la interfaz puede escribir
       *  «Δ 10,0 °C» o tiene que escribir «Δ entre 8,0 y 12,0 °C». */
      readonly exacto: boolean;
      /** `true` si el rango del Δ contiene el cero: los dos cubos pueden ser
       *  iguales aunque se vean distintos. Sin esto, un usuario lee una
       *  diferencia donde el dato no la garantiza. */
      readonly incluyeCero: boolean;
    }
  | { readonly definido: false; readonly motivo: string };

/** Tolerancia relativa al comparar el parámetro de conversión en los dos extremos. */
const TOLERANCIA_PARAMETRO = 1e-9;

/**
 * Δ entre dos lecturas del mismo canal, en la unidad que ya se está mostrando.
 *
 * `a` es el cursor de referencia y `b` el móvil: el Δ es `b − a`, con el signo
 * que espera quien lee de izquierda a derecha.
 *
 * **No convierte nada.** Recibe los dos valores ya en la unidad mostrada y
 * resta. Ver la cabecera del módulo: es lo que hace la operación correcta por
 * construcción en vez de por acordarse.
 */
export function deltaEntre(
  a: LecturaCursor,
  b: LecturaCursor,
  conversion: FormaConversion,
): Delta {
  if (!a.hay || !b.hay) {
    return {
      definido: false,
      motivo:
        "uno de los dos cursores cae en un hueco. Un hueco no es un cero " +
        "(docs/01), así que la diferencia contra él no es el otro valor.",
    };
  }

  if (conversion.tipo === "reciproca") {
    return {
      definido: false,
      motivo:
        "la unidad mostrada es recíproca (λ ↔ φ, periodo ↔ frecuencia, " +
        "L/100 km ↔ mpg) y la conversión no es lineal: una diferencia en esta " +
        "unidad no equivale a ninguna diferencia en la otra. Cambia a la " +
        "unidad canónica de la dimensión para leer un Δ.",
    };
  }

  if (conversion.tipo === "parametrizada" && !mismoParametro(a, b)) {
    return {
      definido: false,
      motivo:
        `el factor de conversión sale del canal '${conversion.parametroRol}' y ` +
        "no vale lo mismo en los dos cursores (por ejemplo, un cambio de mezcla " +
        "de combustible entre uno y otro). Restar los dos valores mostrados no " +
        "daría el Δ de nada.",
    };
  }

  // Aritmética de intervalos. Con dos muestras reales (`minimo === maximo` en
  // ambas) degenera en la resta de siempre, así que no hay dos caminos que
  // puedan divergir: hay uno solo que además cubre el caso decimado.
  const minimo = b.minimo - a.maximo;
  const maximo = b.maximo - a.minimo;
  return {
    definido: true,
    clase: Clase.INTERVALO,
    minimo,
    maximo,
    exacto: a.esMuestra && b.esMuestra,
    incluyeCero: minimo <= 0 && maximo >= 0,
  };
}

function mismoParametro(a: LecturaCursor, b: LecturaCursor): boolean {
  if (!a.hay || !b.hay) return false;
  const pa = a.parametro;
  const pb = b.parametro;
  if (pa === undefined || pb === undefined) return pa === pb;
  const escala = Math.max(Math.abs(pa), Math.abs(pb), 1);
  return Math.abs(pa - pb) <= TOLERANCIA_PARAMETRO * escala;
}

/**
 * Δt entre los dos cursores, en segundos.
 *
 * Es INTERVALO por naturaleza y siempre exacto: el tiempo no tiene
 * desplazamiento de origen que se pueda aplicar mal, y los dos instantes son
 * los que el usuario ha puesto, no valores decimados. Existe como función
 * propia y no como una resta suelta para que el `Math.abs` esté en un solo
 * sitio: un Δt negativo porque el usuario arrastró el segundo cursor a la
 * izquierda del primero es un artefacto de la interacción, no un dato.
 */
export function deltaDeTiempo(tA: number, tB: number): number {
  return Math.abs(tB - tA);
}

/**
 * Convierte un Δ que ya existe a otra unidad, cuando el usuario cambia de
 * unidad con el doble cursor puesto.
 *
 * **Esta es la única función del módulo que puede caer en la trampa**, y por
 * eso es la única que recibe factores. La regla es la de `Clase.INTERVALO`:
 * solo el cociente de factores, **jamás el desplazamiento de origen**. Con
 * K → °C el factor es 1 y el Δ no cambia — que es justo el resultado que
 * parece sospechoso y es el correcto: un Δ de 10 K son 10 °C.
 *
 * Se pasa el Δ entero y no cada extremo por separado para que no haya forma de
 * convertir uno con una regla y el otro con otra.
 */
export function convertirDelta(delta: Delta, factorOrigen: number, factorDestino: number): Delta {
  if (!delta.definido) return delta;
  if (factorOrigen === 0) {
    return { definido: false, motivo: "el factor de la unidad de origen es cero: no es invertible" };
  }
  const k = factorDestino / factorOrigen;
  const extremos = [delta.minimo * k, delta.maximo * k];
  // Un factor negativo (no lo hay hoy en `data/units.toml`, pero la firma lo
  // admite) invertiría el orden de los extremos y dejaría un rango del revés.
  const minimo = Math.min(...extremos);
  const maximo = Math.max(...extremos);
  return { ...delta, minimo, maximo, incluyeCero: minimo <= 0 && maximo >= 0 };
}

/**
 * Lee un canal en un instante desde la caché de cubos (F1-24), en la forma que
 * espera `deltaEntre`.
 *
 * Usa `mirar()` y no `consultar()`: mover un cursor no debe disparar una
 * petición al backend, que es de lo que depende el presupuesto de §2.6.
 */
export function leerEn(
  cache: CacheDeCubos,
  clave: ClaveCubos,
  t: number,
  parametro?: number,
): LecturaCursor {
  const entrada = cache.mirar(clave);
  if (entrada === undefined) return { hay: false };
  // `mirar` no comprueba cobertura (eso es `consultar`): fuera del tramo
  // cargado, `valorEn` devolvería el último cubo como si siguiera vigente.
  if (t < entrada.cubre.t0 || t > entrada.cubre.t1) return { hay: false };
  const v = valorEn(entrada.cubos, t);
  if (v === null) return { hay: false };
  return {
    hay: true,
    esMuestra: clave.factor <= 1,
    minimo: v.minimo,
    maximo: v.maximo,
    ...(parametro === undefined ? {} : { parametro }),
  };
}

/** Lo que la interfaz tiene que escribir para un Δ, ya decidido. */
export interface TextoDelta {
  readonly texto: string;
  /** Aviso que acompaña al texto, o cadena vacía. Nunca oculta información. */
  readonly nota: string;
}

/**
 * El Δ como texto, con `formatear` inyectado (el de F1-32 vía F1-29).
 *
 * Tres formas distintas para tres situaciones distintas, y ninguna de las tres
 * finge ser otra: un número cuando el Δ es exacto, un rango cuando viene de
 * cubos decimados, y el motivo cuando no existe.
 */
export function textoDeDelta(
  delta: Delta,
  formatear: (valor: number) => string,
  etiquetaUnidad = "",
): TextoDelta {
  const sufijo = etiquetaUnidad ? ` ${etiquetaUnidad}` : "";
  if (!delta.definido) return { texto: "—", nota: delta.motivo };
  if (delta.exacto) {
    return { texto: `Δ ${formatear(delta.minimo)}${sufijo}`, nota: "" };
  }
  const nota = delta.incluyeCero
    ? "a este nivel de zoom los dos cubos agregan varias muestras y el rango " +
      "del Δ incluye el cero: puede no haber diferencia. Amplía para leerlo exacto."
    : "a este nivel de zoom cada cubo agrega varias muestras, así que el Δ es " +
      "un rango, no un número. Amplía para leerlo exacto.";
  return {
    texto: `Δ ${formatear(delta.minimo)} … ${formatear(delta.maximo)}${sufijo}`,
    nota,
  };
}
