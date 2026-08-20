/**
 * Comparación de dos logs celda a celda sobre la MISMA malla RPM×MAP (F4-08,
 * `docs/02` §E7.5: «Comparación de dos logs celda a celda (antes/después del
 * cambio)»). Pieza ESPECÍFICA de F4-08, análoga a `lambda/mapa-error.ts`
 * (F4-04): construye una `ConfiguracionMapaDeCalor` genérica (`src/malla/`) a
 * partir de dos `MallaResuelta` ya agregadas — nunca toca las celdas, los
 * ejes ni el color, que son de `src/malla/`, no de aquí.
 *
 * QUÉ ES «ANTES» Y QUÉ ES «DESPUÉS»
 * =====================================
 * `mallaAntes`/`mallaDespues` son dos `Malla` (`dlv_core.malla`) del MISMO
 * canal tercero (λ, avance de encendido, densidad de knock...), una por log,
 * ya resueltas en canónica. Este módulo no las construye — `dlv-api` no
 * expone la malla todavía (ver el informe de F4-04) — solo las compara.
 *
 * DECISIÓN 1 — LA DIFERENCIA ES DE CLASE `INTERVALO`, SIEMPRE
 * =================================================================
 * `diferencia = estadísticaAntes − estadísticaDespués`, celda a celda, para
 * las CUATRO estadísticas con unidad (`media`, `desviacionTipica`, `minimo`,
 * `maximo`). Da igual que el canal comparado sea él mismo `Clase.PUNTO`
 * (avance de encendido, una lectura absoluta) o ya `Clase.INTERVALO` (un
 * error de λ, F4-04): restar dos valores de la misma clase afín cancela
 * SIEMPRE el desplazamiento de origen `b` —`(a·A+b) − (a·B+b) = a·(A−B)`—,
 * así que el resultado nunca lleva ese origen. `CLASE_VALOR_DIFERENCIA` está
 * fijada en `"intervalo"` aquí, igual que `CLASE_VALOR_ERROR_LAMBDA` en
 * `mapa-error.ts`, y por la misma regla (regla 4 de `CLAUDE.md`, `docs/06`
 * §6.5): aplicar `Clase.PUNTO` a una diferencia sumaría un origen que no
 * pertenece a ninguna de las dos lecturas.
 *
 * Y si la unidad activa es RECÍPROCA (φ en `mixture_ratio`), una diferencia
 * no se puede convertir en absoluto —`1/a − 1/b ≠ 1/(a−b)`—, exactamente el
 * caso que `mapa-error.ts` ya resolvió. Este módulo sigue el MISMO criterio:
 * `admiteClase` decide, y si no admite `"intervalo"` el mapa se DESACTIVA con
 * una explicación (`tipo: "deshabilitado"`) en vez de caer a otra unidad en
 * silencio o de lanzar al pulsar una celda.
 *
 * DECISIÓN 2 — DOS MALLAS DE BORDES DISTINTOS: SE RECHAZA, NO SE REAGREGA
 * =============================================================================
 * Comparar celda a celda exige los MISMOS bordes de RPM y de MAP en las dos
 * mallas: la celda `(i, j)` de `mallaAntes` tiene que cubrir EXACTAMENTE el
 * mismo rectángulo RPM×MAP que la celda `(i, j)` de `mallaDespues`, o restar
 * sus estadísticas compara dos regiones del motor distintas con aspecto de
 * comparación válida — el error más caro de los tres posibles, porque no se
 * ve: el mapa se pinta igual de bien con datos incomparables que con datos
 * comparables.
 *
 * Se descartaron las otras dos vías:
 *
 * 1. **Reagregar** (recalcular las dos mallas con unos bordes comunes): exige
 *    las muestras crudas de los dos logs, no solo las `Malla` ya resueltas
 *    que este componente RECIBE (`dlv-api` no expone la malla todavía, y
 *    `construir_malla` es Python/NumPy — no hay ADR-009 que cumplir aquí
 *    porque no hay ninguna muestra que recorrer en TypeScript). Reagregar es
 *    trabajo de quien monte la escena (o de una tarea de `dlv-api` futura),
 *    no de un componente de presentación.
 * 2. **Intersectar** (recortar cada malla a los bordes que ambas comparten):
 *    parece más útil que rechazar, pero solo funciona sin pérdida cuando los
 *    bordes de una malla son un SUBCONJUNTO exacto de los de la otra —si son
 *    equiespaciados con distinto paso (lo normal si cada malla dedujo sus
 *    bordes con `bordes_por_omision` sobre el rango de SU propio log, que es
 *    el caso más común de «dos logs distintos»), ninguna celda de una
 *    coincide con ninguna de la otra y la intersección está vacía en
 *    silencio. Es una solución que funciona en el caso fácil y falla sin
 *    avisar en el caso típico — la misma trampa que "1. Caer a λ en
 *    silencio" descartó en `mapa-error.ts`.
 *
 * La elegida es la más simple y la más honesta: **rechazar con una
 * explicación** que dice cuál de los dos ejes no coincide (`tipo:
 * "incompatibles"`), para que quien montó la escena sepa que tiene que volver
 * a agregar los dos logs con los MISMOS bordes explícitos (`bordes_rpm`/
 * `bordes_map` pasados a `construir_malla`, no los deducidos por omisión de
 * cada log por separado) antes de compararlos — exactamente lo que dice
 * `comparacion.mapa.bordesIncompatibles` en el catálogo.
 *
 * La comprobación es de IGUALDAD EXACTA, no con una tolerancia: los bordes
 * canónicos que llegan aquí son números que, si las dos mallas se
 * construyeron con los mismos `bordes_rpm`/`bordes_map` explícitos, son
 * literalmente los mismos flotantes (mismo array de entrada, ninguna
 * aritmética nueva de por medio) — coinciden bit a bit. Una tolerancia
 * escondería precisamente el caso que hay que atrapar: dos mallas cuyos
 * bordes se DEDUJERON por separado (`bordes_por_omision` sobre el rango de
 * cada log) casi nunca coinciden por accidente, pero SÍ pueden quedar muy
 * cerca si los dos logs cubren un rango de motor parecido — y sería
 * exactamente el caso donde una tolerancia laxa aceptaría comparar dos
 * mallas que en realidad no son la misma rejilla.
 *
 * DECISIÓN 3 — CELDA VACÍA EN UNO DE LOS DOS LOGS: NO ES UNA DIFERENCIA DE CERO
 * ===================================================================================
 * Si `mallaAntes` no pisó una celda (`cuenta === 0`, sus cuatro estadísticas
 * son NaN, ver la cabecera de `dlv_core.malla` y de `malla/tipos.ts`) pero
 * `mallaDespues` sí, restar da NaN de forma natural: `NaN − x` es SIEMPRE NaN
 * (IEEE 754), así que `estadisticaAntes − estadisticaDespues` ya sale «sin
 * dato» sin ningún caso especial. Lo único que este módulo tiene que decidir
 * a propósito es la `cuenta` de la celda de diferencia (ver la decisión 4):
 * con `cuenta = min(cuentaAntes, cuentaDespues)`, una celda vacía en
 * CUALQUIERA de los dos logs sale con `cuenta === 0`, y `geometria.ts` ya
 * sabe pintar `cuenta === 0` como `"vacia"` — `colorSinDatos`, nunca el color
 * de una diferencia de cero. Así «no hay comparación posible aquí» y «la
 * diferencia fue exactamente cero» quedan tan distinguibles en el mapa de
 * comparación como lo son hoy en el mapa de error de λ.
 *
 * DECISIÓN 4 — LA CONFIANZA SE COMBINA CON EL MÍNIMO, NO CON LA SUMA
 * ========================================================================
 * `cuenta` de la celda de diferencia es `min(cuentaAntes, cuentaDespues)`, no
 * la suma. Una comparación con 200 muestras antes y 2 después no es fiable
 * PORQUE el lado de 2 muestras no lo es — sumar (202) escondería justo esa
 * debilidad detrás del lado fuerte, y `umbralConfianza` de `geometria.ts`
 * juzgaría «confiable» una celda cuya mitad «después» no lo es en absoluto.
 * El mínimo es la lectura conservadora y defendible: una comparación nunca
 * puede ser más fiable que el más débil de sus dos lados, exactamente igual
 * que una cadena no es más fuerte que su eslabón más débil. Es también la que
 * ya resuelve, sin caso especial, la decisión 3: `min(0, n) = 0` para
 * cualquier `n`, así que una celda vacía en un lado sale con `cuenta === 0`
 * gratis, sin tener que comprobar «¿está vacía en alguno de los dos?» aparte.
 */

import { admiteClase, convertirValor, type Clase } from "../unidades/conversion.ts";
import type { UnidadInfo } from "../unidades/tipos.ts";
import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Color } from "../render/tipos.ts";
import { t } from "../locale/catalogo.ts";
import { escalaDivergente, escalaMaximaDesdeDatos } from "../malla/escala-divergente.ts";
import type { CeldaEstadisticas, ConfiguracionMapaDeCalor, MallaResuelta } from "../malla/tipos.ts";

/** Ver la decisión 1 de la cabecera: NUNCA se deja que quien llama la cambie. */
const CLASE_VALOR_DIFERENCIA: Clase = "intervalo";

/** `estadistica === NaN` es siempre `false`; esta es la comprobación IEEE 754 correcta ("¿es NaN?"). */
function esNaN(v: number): boolean {
  return v !== v;
}

/**
 * `antes - despues`, con nombre propio para que `celdaDeDiferencia` se lea
 * como la decisión 1 de la cabecera («la diferencia es antes menos después»,
 * no un `-` suelto). Si cualquiera de los dos es NaN (celda vacía en ese
 * log, ver la cabecera de `dlv_core.malla`), el resultado es NaN — IEEE 754
 * ya lo garantiza, sin ningún caso especial (ver la decisión 3).
 */
function diferencia(antes: number, despues: number): number {
  return antes - despues;
}

/**
 * Compara los bordes de un eje de las dos mallas. `null` si coinciden;
 * si no, el índice del primer borde que difiere (para el mensaje de error).
 * Ver la decisión 2: igualdad EXACTA, sin tolerancia.
 */
function primerBordeQueDifiere(a: readonly number[], b: readonly number[]): number | null {
  if (a.length !== b.length) return 0;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return i;
  }
  return null;
}

/**
 * Combina las estadísticas de una celda de `mallaAntes` y su homóloga en
 * `mallaDespues` en una celda de DIFERENCIA (ver las decisiones 1, 3 y 4 de
 * la cabecera). Las cuatro estadísticas con unidad son `antes - despues`,
 * siempre `Clase.INTERVALO`; `cuenta` es el mínimo de las dos cuentas.
 */
function celdaDeDiferencia(antes: CeldaEstadisticas, despues: CeldaEstadisticas): CeldaEstadisticas {
  return {
    cuenta: Math.min(antes.cuenta, despues.cuenta),
    media: diferencia(antes.media, despues.media),
    desviacionTipica: diferencia(antes.desviacionTipica, despues.desviacionTipica),
    minimo: diferencia(antes.minimo, despues.minimo),
    maximo: diferencia(antes.maximo, despues.maximo),
  };
}

/** Resultado de comparar los bordes de dos mallas: coinciden, o no. */
export type ResultadoBordes =
  | { readonly tipo: "compatibles" }
  | { readonly tipo: "incompatibles"; readonly motivo: string };

/**
 * Comprueba que `mallaAntes` y `mallaDespues` comparten exactamente los
 * mismos bordes de fila (RPM) y de columna (MAP) — ver la decisión 2 de la
 * cabecera del módulo. Se expone aparte de `resolverMapaComparacion` porque
 * quien monta la escena puede querer avisar de la incompatibilidad ANTES de
 * tener resuelta la unidad activa (p. ej. deshabilitar el botón "comparar" en
 * cuanto se eligen los dos logs, sin esperar a pintar nada).
 */
export function comprobarBordesCompatibles(
  mallaAntes: MallaResuelta,
  mallaDespues: MallaResuelta,
): ResultadoBordes {
  const difFila = primerBordeQueDifiere(mallaAntes.bordesFila, mallaDespues.bordesFila);
  if (difFila !== null) {
    return {
      tipo: "incompatibles",
      motivo: t("comparacion.mapa.bordesIncompatibles", { eje: "RPM" }),
    };
  }
  const difColumna = primerBordeQueDifiere(mallaAntes.bordesColumna, mallaDespues.bordesColumna);
  if (difColumna !== null) {
    return {
      tipo: "incompatibles",
      motivo: t("comparacion.mapa.bordesIncompatibles", { eje: "MAP" }),
    };
  }
  return { tipo: "compatibles" };
}

/**
 * Combina celda a celda, asumiendo que quien llama YA comprobó que los
 * bordes son compatibles (`comprobarBordesCompatibles`). Privada: la única
 * vía pública para llegar aquí es `compararMallas` o `resolverMapaComparacion`,
 * las dos comprueban los bordes antes de invocarla.
 */
function combinarCeldas(
  mallaAntes: MallaResuelta,
  mallaDespues: MallaResuelta,
): readonly CeldaEstadisticas[] | null {
  if (mallaAntes.celdas.length !== mallaDespues.celdas.length) return null;
  const celdas: CeldaEstadisticas[] = [];
  for (let i = 0; i < mallaAntes.celdas.length; i += 1) {
    celdas.push(celdaDeDiferencia(mallaAntes.celdas[i]!, mallaDespues.celdas[i]!));
  }
  return celdas;
}

/**
 * Construye la `MallaResuelta` de diferencia (`mallaAntes - mallaDespues`,
 * celda a celda), o `null` si las dos mallas no comparten los mismos bordes
 * (ver `comprobarBordesCompatibles`). No convierte nada: la salida sigue en
 * CANÓNICA, igual que sus dos entradas (mismo criterio que `malla/tipos.ts`
 * y `dlv_core.malla`) — la conversión a la unidad activa es responsabilidad
 * de `resolverMapaComparacion`, no de esta función.
 */
export function compararMallas(
  mallaAntes: MallaResuelta,
  mallaDespues: MallaResuelta,
): MallaResuelta | null {
  if (comprobarBordesCompatibles(mallaAntes, mallaDespues).tipo === "incompatibles") return null;
  const celdas = combinarCeldas(mallaAntes, mallaDespues);
  if (celdas === null) return null;
  return { bordesFila: mallaAntes.bordesFila, bordesColumna: mallaAntes.bordesColumna, celdas };
}

export interface ConfiguracionComparacionMallas {
  readonly area: AreaDibujo;
  /** Malla del log "antes" del cambio (p. ej. de tuning), en CANÓNICA. */
  readonly mallaAntes: MallaResuelta;
  /** Malla del log "después", MISMO canal, en CANÓNICA. */
  readonly mallaDespues: MallaResuelta;
  readonly forma: { readonly filas: number; readonly columnas: number };
  /** Unidad activa del canal comparado (la misma dimensión en los dos logs). */
  readonly unidadActiva: UnidadInfo;
  /** Parámetro de una conversión `parametrizada` (p. ej. estequiometría λ→AFR), si aplica. */
  readonly parametro?: number;
  /** Cuenta mínima para pintar una celda como confiable. Obligatorio: ver `malla/tipos.ts`. */
  readonly umbralConfianza: number;
  readonly colorSinDatos: Color;
  /**
   * Anchura de la escala divergente, en la unidad de `unidadActiva`. Si se
   * omite, se deduce del propio dato (`escalaMaximaDesdeDatos` sobre las
   * medias de diferencia ya convertidas) — mismo criterio que
   * `mapa-error.ts` y que `dlv_core.malla.bordes_por_omision`: nunca un rango
   * «típico» cableado.
   */
  readonly escalaMaximaDiferencia?: number;
}

export type ResultadoMapaComparacion =
  | { readonly tipo: "incompatibles"; readonly motivo: string }
  | { readonly tipo: "deshabilitado"; readonly motivo: string }
  | { readonly tipo: "activo"; readonly configuracion: ConfiguracionMapaDeCalor };

/**
 * Construye la configuración del mapa de calor de comparación de dos logs, o
 * explica por qué no se puede pintar (bordes incompatibles, o unidad activa
 * recíproca — ver las decisiones 1 y 2 de la cabecera del módulo).
 */
export function resolverMapaComparacion(config: ConfiguracionComparacionMallas): ResultadoMapaComparacion {
  const { mallaAntes, mallaDespues, unidadActiva } = config;

  const bordes = comprobarBordesCompatibles(mallaAntes, mallaDespues);
  if (bordes.tipo === "incompatibles") return { tipo: "incompatibles", motivo: bordes.motivo };

  const celdas = combinarCeldas(mallaAntes, mallaDespues);
  if (celdas === null) {
    // Bordes compatibles pero número de celdas distinto: no debería pasar si
    // `forma` describe a las dos mallas por igual, pero es un error de
    // configuración de quien llama, no un dato del log — mismo criterio que
    // `calcularGeometriaMapaDeCalor` (regla 6 de `CLAUDE.md`).
    throw new RangeError(
      `mallaAntes tiene ${mallaAntes.celdas.length} celdas y mallaDespues ${mallaDespues.celdas.length}: ` +
        "no se puede comparar celda a celda con bordes compatibles pero número de celdas distinto.",
    );
  }
  const mallaDiferencia: MallaResuelta = {
    bordesFila: mallaAntes.bordesFila,
    bordesColumna: mallaAntes.bordesColumna,
    celdas,
  };

  if (!admiteClase(unidadActiva.conversion, CLASE_VALOR_DIFERENCIA)) {
    return {
      tipo: "deshabilitado",
      motivo: t("comparacion.mapa.unidadReciprocaDesactivado", { unidad: unidadActiva.etiqueta }),
    };
  }

  const mediasMostradas = mallaDiferencia.celdas.map((c) =>
    esNaN(c.media)
      ? NaN
      : convertirValor(c.media, unidadActiva.conversion, CLASE_VALOR_DIFERENCIA, config.parametro),
  );
  const escalaMaxima = config.escalaMaximaDiferencia ?? escalaMaximaDesdeDatos(mediasMostradas);
  if (escalaMaxima === null) {
    return { tipo: "deshabilitado", motivo: t("comparacion.mapa.sinDatosParaEscala") };
  }

  return {
    tipo: "activo",
    configuracion: {
      area: config.area,
      malla: mallaDiferencia,
      forma: config.forma,
      conversion: unidadActiva.conversion,
      claseValor: CLASE_VALOR_DIFERENCIA,
      parametro: config.parametro,
      umbralConfianza: config.umbralConfianza,
      decimales: unidadActiva.decimales,
      colorDeValor: escalaDivergente(escalaMaxima),
      colorSinDatos: config.colorSinDatos,
    },
  };
}
