/**
 * Conversión de unidades en el frontend, con los factores REALES del catálogo.
 *
 * QUÉ SUSTITUYE Y POR QUÉ IMPORTA
 * ===============================
 * Sustituye a `app/conversion-demo.ts`, que era una tabla cableada con tres
 * dimensiones (temperatura, presión, velocidad) y factores «de mentira». El
 * problema no era que fuese pequeña, sino cómo fallaba: `factorDe` devolvía la
 * identidad para cualquier combinación que no estuviera en la tabla, **en
 * silencio**. El selector ya listaba las unidades reales de `data/units.toml`,
 * así que elegir «%» en Throttle Position o «AFR» en la sonda lambda no hacía
 * absolutamente nada, sin error y sin aviso. Un número mostrado en la unidad
 * equivocada es peor que un número ausente: nadie lo comprueba.
 *
 * Ahora las conversiones llegan de `/comandos/unidades`, que las lee de
 * `data/units.toml` (regla 2 de `CLAUDE.md`: los datos del propietario no se
 * trasladan al código). Aquí solo está la aritmética, que es la misma que
 * `dlv_core.unidades` aplica en Python — este módulo es su espejo, y las dos
 * implementaciones tienen que coincidir o los ejes dirán una cosa y el informe
 * otra.
 *
 * POR QUÉ CONVIERTE EL FRONTEND Y NO EL SERVIDOR
 * ==============================================
 * ADR-004: cambiar de unidad es un REPINTADO, no una petición. Los cubos se
 * cachean en canónica (`datos/cache-cubos.ts`) y «cambiar de unidad no invalida
 * nada». Si convirtiera el servidor, cada clic en el selector tiraría la caché
 * y volvería a pedir megabytes por la red para multiplicar por una constante.
 *
 * LA CLASE ES OBLIGATORIA Y NO TIENE VALOR POR OMISIÓN
 * ====================================================
 * Es la regla 4 del proyecto y el motivo de que exista `docs/06` §6.5. Un Δ de
 * 10 K son 10 °C, no −263,15 °C: la diferencia entre las dos respuestas es si
 * se aplica el desplazamiento de origen `b`. Ponerle un valor por omisión a
 * este parámetro convertiría el error en el comportamiento normal, así que va
 * primero y sin omisión, y quien llame tiene que decidir qué está convirtiendo.
 */

import type { CubosContinuos } from "../render/tipos.ts";

/** Espejo de `dlv_core.unidades.Clase` (`docs/06` §6.5). */
export type Clase = "punto" | "intervalo" | "tasa" | "varianza";

/** `mostrado = a · canonica + b`. La mayoría de las unidades. */
export interface ConversionAfin {
  readonly tipo: "afin";
  readonly a: number;
  readonly b: number;
}

/**
 * `mostrado = a / canonica`. λ↔φ, periodo↔frecuencia, L/100 km↔mpg.
 *
 * **No es lineal**, así que una diferencia no se puede convertir con ella.
 */
export interface ConversionReciproca {
  readonly tipo: "reciproca";
  readonly a: number;
}

/**
 * `mostrado = a(p) · canonica`, con `p` fuera del catálogo.
 *
 * El caso es λ→AFR: el factor es la estequiometría del combustible en uso
 * (14,7 en gasolina, 9,77 en E85, 6,4 en metanol). Sin el parámetro, un log de
 * E85 daría un AFR incorrecto **con aspecto de correcto**.
 */
export interface ConversionParametrizada {
  readonly tipo: "parametrizada";
  /** Rol del canal que lleva el parámetro (`stoichiometry`). */
  readonly parametroRol: string;
  readonly aPorOmision: number;
}

export type Conversion = ConversionAfin | ConversionReciproca | ConversionParametrizada;

/** No convertir. Es una conversión afín de verdad, no un caso especial. */
export const IDENTIDAD: ConversionAfin = { tipo: "afin", a: 1, b: 0 };

/**
 * Uso incorrecto del sistema de unidades — no es un fallo de datos.
 *
 * Espejo de `dlv_core.unidades.ErrorDeUnidad`. Se lanza, y no se devuelve un
 * valor aproximado, por lo mismo que en Python: convertir un Δ con una
 * recíproca da un número que parece razonable y no lo es.
 */
export class ErrorDeUnidad extends Error {}

/** `true` si convertir es no hacer nada: permite ahorrarse copiar los arrays. */
export function esIdentidad(conversion: Conversion): boolean {
  return conversion.tipo === "afin" && conversion.a === 1 && conversion.b === 0;
}

/**
 * `true` si esta conversión puede aplicarse a la clase pedida.
 *
 * Sirve para que la interfaz DESACTIVE lo que no se puede hacer en vez de
 * ofrecerlo y fallar: el Δ del doble cursor sobre un canal en φ no tiene
 * respuesta, y enseñarlo en gris es más honesto que enseñar un error al
 * pulsarlo.
 */
export function admiteClase(conversion: Conversion, clase: Clase): boolean {
  return conversion.tipo !== "reciproca" || clase === "punto";
}

function factorParametrizado(
  conversion: ConversionParametrizada,
  parametro: number | undefined,
): number {
  // `undefined` y no `0`: una estequiometría de cero no existe, y dejarla pasar
  // convertiría toda la serie en ceros sin decir por qué.
  return parametro === undefined || parametro === 0 ? conversion.aPorOmision : parametro;
}

/**
 * Convierte un valor de la unidad canónica a la mostrada.
 *
 * `parametro` solo lo usa `parametrizada`; en las demás se ignora. Se pasa
 * siempre desde el mismo sitio (quien conoce el combustible activo) para que no
 * haya dos caminos, uno con estequiometría y otro sin ella.
 */
export function convertirValor(
  valor: number,
  conversion: Conversion,
  clase: Clase,
  parametro?: number,
): number {
  switch (conversion.tipo) {
    case "afin": {
      const { a, b } = conversion;
      if (clase === "punto") return b === 0 ? a * valor : a * valor + b;
      if (clase === "varianza") return a * a * valor;
      // INTERVALO y TASA: solo la parte lineal. Es la regla que evita que un
      // Δ de 10 K se convierta en −263,15 °C.
      return a * valor;
    }
    case "reciproca":
      exigePunto(clase);
      return conversion.a / valor;
    case "parametrizada": {
      const a = factorParametrizado(conversion, parametro);
      return clase === "varianza" ? a * a * valor : a * valor;
    }
  }
}

/** El camino inverso: de la unidad mostrada a la canónica. */
export function aCanonica(
  valor: number,
  conversion: Conversion,
  clase: Clase,
  parametro?: number,
): number {
  switch (conversion.tipo) {
    case "afin": {
      const { a, b } = conversion;
      if (clase === "punto") return b === 0 ? valor / a : (valor - b) / a;
      if (clase === "varianza") return valor / (a * a);
      return valor / a;
    }
    case "reciproca":
      exigePunto(clase);
      return conversion.a / valor;
    case "parametrizada": {
      const a = factorParametrizado(conversion, parametro);
      return clase === "varianza" ? valor / (a * a) : valor / a;
    }
  }
}

/**
 * De la muestra CRUDA del log a la unidad mostrada, en un solo paso.
 *
 * SON DOS CONVERSIONES, NO UNA, Y OLVIDAR LA PRIMERA NO DA ERROR
 * ==============================================================
 * Un canal de Haltech no guarda grados: guarda enteros escalados
 * (`Storage.INT32_SCALED`, ADR-003). La temperatura de refrigerante llega como
 * `3748` con un factor `a = 0,1` propio del canal, que es lo que la lleva a
 * 374,8 K. Ese factor viene del descriptor del formato y es distinto por canal;
 * `data/units.toml` no lo conoce ni tiene por qué.
 *
 * El camino completo es entonces:
 *
 *     crudo --(to_canon del canal)--> canónica --(units.toml)--> mostrada
 *       3748            a=0,1            374,8 K      degC        101,65 °C
 *
 * Saltarse el primer paso no rompe nada visible: el trazo se dibuja, el eje se
 * autoescala, y la temperatura sale como 3 474,85 °C — un número, con su unidad
 * correcta, diez veces más grande. Por eso los dos pasos van juntos en una sola
 * función y no en dos llamadas que alguien pueda encadenar a medias.
 *
 * `aCanonicaDelCanal` es siempre AFÍN: es un `(a, b)` del descriptor. La clase
 * se aplica a los dos pasos, que es lo correcto — un Δ en crudo sigue siendo un
 * Δ en canónica y en la unidad mostrada, y ninguno de los dos desplazamientos
 * de origen debe entrar.
 */
export function convertirDesdeCrudo(
  crudo: number,
  aCanonicaDelCanal: ConversionAfin,
  conversion: Conversion,
  clase: Clase,
  parametro?: number,
): number {
  return convertirValor(
    convertirValor(crudo, aCanonicaDelCanal, clase),
    conversion,
    clase,
    parametro,
  );
}

/**
 * Aplica una conversión a los cuatro arrays de un bloque de cubos.
 *
 * TODO CUBO ES CLASE «PUNTO», INCLUSO DECIMADO
 * ============================================
 * `minimo`, `maximo`, `primero` y `ultimo` son lecturas que la señal alcanzó
 * de verdad, no diferencias — un `maximo` de un cubo de 1024 muestras sigue
 * siendo un valor que el sensor midió. Por eso los cuatro se convierten como
 * `punto`, con `b` incluido. El único Δ de la aplicación es el del doble
 * cursor, y ese lo resuelve `cursor/doble.ts` con la clase `intervalo`.
 *
 * Devuelve arrays NUEVOS: `CacheDeCubos` guarda los cubos en canónica y
 * «cambiar de unidad no invalida nada» (F1-24). Mutarlos aquí rompería esa
 * garantía en cuanto dos paneles enseñaran el mismo canal en dos unidades.
 */
export function convertirCubos(
  cubos: CubosContinuos,
  aCanonicaDelCanal: ConversionAfin,
  conversion: Conversion,
  parametro?: number,
): CubosContinuos {
  if (esIdentidad(aCanonicaDelCanal) && esIdentidad(conversion)) return cubos;
  const n = cubos.t.length;
  const minimo = new Float32Array(n);
  const maximo = new Float32Array(n);
  const primero = new Float32Array(n);
  const ultimo = new Float32Array(n);
  const f = (v: number): number =>
    convertirDesdeCrudo(v, aCanonicaDelCanal, conversion, "punto", parametro);
  for (let i = 0; i < n; i += 1) {
    minimo[i] = f(cubos.minimo[i]!);
    maximo[i] = f(cubos.maximo[i]!);
    primero[i] = f(cubos.primero[i]!);
    ultimo[i] = f(cubos.ultimo[i]!);
  }
  // UNA RECÍPROCA INVIERTE EL ORDEN: `a/x` es decreciente, así que el mínimo en
  // canónica es el MÁXIMO en la unidad mostrada. Sin este intercambio, el
  // relleno del trazo se dibujaría con los extremos cruzados y la autoescala
  // calcularía un rango del revés — un fallo puramente visual, sin error, que
  // solo se ve comparando con el mismo canal en otra unidad.
  const invierte = conversion.tipo === "reciproca";
  return {
    t: cubos.t,
    tOrigen: cubos.tOrigen,
    minimo: invierte ? maximo : minimo,
    maximo: invierte ? minimo : maximo,
    primero,
    ultimo,
    factor: cubos.factor,
  };
}

function exigePunto(clase: Clase): void {
  if (clase !== "punto") {
    throw new ErrorDeUnidad(
      `una conversión recíproca no es lineal: no se puede convertir un valor de ` +
        `clase ${clase}. Convierte los extremos como «punto» y resta después, ` +
        `sabiendo que la diferencia no es lineal.`,
    );
  }
}
