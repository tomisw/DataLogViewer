/**
 * Mapa de calor de error de λ (F4-04, `docs/02` §E7.2): la pieza ESPECÍFICA
 * que convierte una `MallaResuelta` de error de λ en una
 * `ConfiguracionMapaDeCalor` genérica (`src/malla/`). F4-07 y F4-08 tendrán
 * su propio fichero equivalente a este —no a `src/malla/`, que ninguno de
 * los dos debería tener que tocar—.
 *
 * QUÉ ES UN «ERROR DE λ», Y POR QUÉ NO ES UNA LECTURA
 * ========================================================
 * El canal que se agrega en la malla no es λ: es λ MEDIDA − λ OBJETIVO
 * (`docs/02` §E6.2, «biblioteca de fórmulas: error de λ»). Es una
 * DIFERENCIA, no una lectura absoluta, y su clase de magnitud es
 * `Clase.INTERVALO` (`docs/06` §6.5, regla 4 de `CLAUDE.md`) — NO
 * `Clase.PUNTO`, que es lo que `dlv_core.malla.CLASE_DE_ESTADISTICA`
 * declararía para `media`/`minimo`/`maximo` si el canal agregado fuera λ a
 * secas (ver la cabecera de `malla/tipos.ts`, sección «LA TRAMPA»). Por eso
 * `CLASE_VALOR_ERROR_LAMBDA` está fijada aquí en `"intervalo"` y NUNCA se
 * deja que la decida quien llama: a diferencia de `umbralConfianza`, esto no
 * es una preferencia, es un hecho sobre qué es un error de λ.
 *
 * LA DECISIÓN DE φ (UNIDAD RECÍPROCA): DESACTIVAR CON EXPLICACIÓN, NO CAER A λ
 * =================================================================================
 * `unidades/conversion.ts#admiteClase` existe exactamente para esto: «Δ del
 * doble cursor sobre un canal en φ no tiene respuesta, y enseñarlo en gris es
 * más honesto que enseñar un error al pulsarlo». Este módulo aplica la MISMA
 * regla y la MISMA razón al mapa de error, y se descartaron dos alternativas:
 *
 * 1. **Caer a λ en silencio cuando la unidad activa es φ**: el resto de la
 *    aplicación (ejes, topes, la tabla del cursor) muestra TODOS los canales
 *    en la unidad que el usuario eligió. Un mapa que de repente cambiara de
 *    unidad por su cuenta —sin decírselo, o diciéndolo con una etiqueta
 *    pequeña que es fácil no ver— es precisamente el error de «un número
 *    mostrado en la unidad equivocada» que la cabecera de `conversion.ts`
 *    señala como «peor que un número ausente: nadie lo comprueba». Y no basta
 *    con rotular el eje: la escala de color también cambiaría de sentido sin
 *    que hubiera ningún gesto del usuario que lo explique.
 * 2. **Convertir el resultado con una resta de extremos** (convertir λ_min y
 *    λ_max de cada celda como PUNTO a φ y restar): es matemáticamente
 *    incorrecto —`1/a − 1/b ≠ 1/(a−b)`— y es exactamente el error que
 *    `exigePunto` en `conversion.ts` existe para impedir. El comentario de esa
 *    función lo deja escrito: «convierte los extremos como puntos y resta
 *    después, sabiendo que la diferencia no es lineal» — sabiéndolo, no
 *    haciéndolo automáticamente y en silencio.
 *
 * La elegida es la que ya usa el doble cursor: **desactivar el mapa con una
 * explicación** (`resultado.tipo === "deshabilitado"`), consistente con el
 * resto de la aplicación y sin inventar una unidad que el usuario no pidió.
 * Quien monte la escena decide qué hacer con `motivo` —un aviso en el panel,
 * un botón para cambiar de unidad— pero el mapa en sí no se pinta.
 */

import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Color } from "../render/tipos.ts";
import { admiteClase, convertirValor, type Clase } from "../unidades/conversion.ts";
import type { UnidadInfo } from "../unidades/tipos.ts";
import { t } from "../locale/catalogo.ts";
import { escalaDivergente, escalaMaximaDesdeDatos } from "../malla/escala-divergente.ts";
import type { ConfiguracionMapaDeCalor, MallaResuelta } from "../malla/tipos.ts";

/** Ver la cabecera del módulo: NUNCA se deja que quien llama la cambie. */
const CLASE_VALOR_ERROR_LAMBDA: Clase = "intervalo";

export interface ConfiguracionMapaErrorLambda {
  readonly area: AreaDibujo;
  /** Malla del error de λ (media, minimo, maximo... YA son λ_medida − λ_objetivo), en CANÓNICA. */
  readonly malla: MallaResuelta;
  readonly forma: { readonly filas: number; readonly columnas: number };
  /** La unidad activa de la dimensión `mixture_ratio` (λ, AFR o φ), con su conversión. */
  readonly unidadActiva: UnidadInfo;
  /** Estequiometría del combustible activo, solo si `unidadActiva` es la conversión `parametrizada` (AFR). */
  readonly parametro?: number;
  /** Cuenta mínima para pintar una celda como confiable. Obligatorio: ver `malla/tipos.ts`. */
  readonly umbralConfianza: number;
  readonly colorSinDatos: Color;
  /**
   * Anchura de la escala divergente, en la unidad de `unidadActiva`. Si se
   * omite, se deduce del propio dato (`escalaMaximaDesdeDatos` sobre las
   * medias de celda ya convertidas) — NUNCA un rango «típico» cableado, mismo
   * criterio que `dlv_core.malla.bordes_por_omision` (ver la cabecera de
   * `escala-divergente.ts`).
   */
  readonly escalaMaximaError?: number;
}

export type ResultadoMapaErrorLambda =
  | { readonly tipo: "activo"; readonly configuracion: ConfiguracionMapaDeCalor }
  | { readonly tipo: "deshabilitado"; readonly motivo: string };

/**
 * Construye la configuración del mapa de calor de error de λ, o explica por
 * qué no se puede pintar en la unidad activa (ver la cabecera del módulo).
 */
export function resolverMapaErrorLambda(config: ConfiguracionMapaErrorLambda): ResultadoMapaErrorLambda {
  const { unidadActiva } = config;

  if (!admiteClase(unidadActiva.conversion, CLASE_VALOR_ERROR_LAMBDA)) {
    return {
      tipo: "deshabilitado",
      motivo: t("lambda.mapaError.unidadReciprocaDesactivado", { unidad: unidadActiva.etiqueta }),
    };
  }

  const mediasMostradas = config.malla.celdas.map((c) =>
    Number.isFinite(c.media)
      ? convertirValor(c.media, unidadActiva.conversion, CLASE_VALOR_ERROR_LAMBDA, config.parametro)
      : NaN,
  );
  const escalaMaxima = config.escalaMaximaError ?? escalaMaximaDesdeDatos(mediasMostradas);
  if (escalaMaxima === null) {
    return { tipo: "deshabilitado", motivo: t("lambda.mapaError.sinDatosParaEscala") };
  }

  return {
    tipo: "activo",
    configuracion: {
      area: config.area,
      malla: config.malla,
      forma: config.forma,
      conversion: unidadActiva.conversion,
      claseValor: CLASE_VALOR_ERROR_LAMBDA,
      parametro: config.parametro,
      umbralConfianza: config.umbralConfianza,
      decimales: unidadActiva.decimales,
      colorDeValor: escalaDivergente(escalaMaxima),
      colorSinDatos: config.colorSinDatos,
    },
  };
}
