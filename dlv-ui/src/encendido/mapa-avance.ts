/**
 * Mapa de calor de avance de encendido (F4-07, `docs/02` §E7.4): la pieza
 * ESPECÍFICA que convierte una `MallaResuelta` de avance de encendido en una
 * `ConfiguracionMapaDeCalor` genérica (`src/malla/`). Mismo patrón que
 * `lambda/mapa-error.ts` (F4-04) para el error de λ — léelo antes de tocar
 * esto si no te resulta familiar el reparto de responsabilidades entre
 * `malla/` (el motor) y este fichero (el dominio).
 *
 * QUÉ ES UN «AVANCE DE ENCENDIDO», Y POR QUÉ NO ES COMO EL ERROR DE λ
 * ========================================================================
 * El canal que se agrega en la malla es directamente `ignition_advance`
 * (`data/roles.toml`): grados de avance de cigüeñal, una LECTURA absoluta —
 * "22° antes del punto muerto superior en esta celda", no una diferencia
 * entre dos cosas. Por eso `CLASE_VALOR_AVANCE` está fijada en
 * `Clase.PUNTO`, NO en `Clase.INTERVALO` como fija `mapa-error.ts` para el
 * error de λ (medida − objetivo): copiar esa constante sin pensar habría sido
 * exactamente el error que `dlv_core.malla.CLASE_DE_ESTADISTICA` documenta
 * como "la trampa" en la cabecera de `malla/tipos.ts` — asumir que el canal
 * agregado es una diferencia cuando en realidad es una lectura, o al revés.
 * Aquí el canal SÍ es una lectura, así que `Clase.PUNTO` es lo correcto y,
 * como en `mapa-error.ts`, no se deja que quien llama la cambie: es un hecho
 * sobre qué es un avance de encendido, no una preferencia.
 *
 * POR QUÉ NO HAY UN CASO "DESHABILITADO POR UNIDAD RECÍPROCA"
 * =================================================================
 * `mapa-error.ts` desactiva el mapa cuando la unidad activa es φ (recíproca)
 * porque `Clase.INTERVALO` no admite una conversión recíproca
 * (`unidades/conversion.ts#exigePunto`). Aquí no hace falta ese caso, por dos
 * motivos que se refuerzan:
 *
 * 1. `admiteClase(conversion, "punto")` es SIEMPRE `true`, sea cual sea el
 *    tipo de conversión (`conversion.ts`: la única condición que puede dar
 *    `false` exige `clase !== "punto"`). Una lectura absoluta nunca choca con
 *    una conversión recíproca.
 * 2. Además, y en la práctica: `dimensiones.angle` de `data/units.toml` no
 *    declara ninguna unidad `reciproca` (solo `afin`: °, rad, ° de árbol), así
 *    que el caso ni siquiera podría darse hoy con el catálogo real. El
 *    módulo no depende de este hecho de los datos —no reformatea ni traslada
 *    `units.toml` (regla 2 de `CLAUDE.md`)—, pero es la razón de que el punto
 *    1 nunca sorprenda en la práctica.
 *
 * El único motivo por el que este mapa SÍ se puede deshabilitar es el mismo
 * que en `mapa-error.ts`: que no haya ninguna celda con dato del que deducir
 * una escala (ver más abajo).
 *
 * LA ESCALA: SECUENCIAL, NO DIVERGENTE — Y POR QUÉ
 * ======================================================
 * Un avance de 22° no es "mejor" ni "peor" que uno de 8° sin contexto de motor
 * (relación de compresión, combustible, RPM, MAP): no hay un cero, ni ningún
 * otro valor, que sea universalmente "neutro" y alrededor del cual leer un
 * signo. La escala divergente de `malla/escala-divergente.ts` existe
 * precisamente para lo contrario —un error de λ SÍ se lee alrededor de cero,
 * rico/pobre— y usarla aquí sugeriría un punto neutro que no existe: la
 * cabecera de `escala-divergente.ts` señala explícitamente que F4-07 "decide
 * su propia escala secuencial cuando le toque". Le toca ahora:
 * `malla/escala-secuencial.ts` (añadido por esta tarea, ver su cabecera para
 * el porqué de vivir en el motor genérico) interpola linealmente entre un
 * color de avance bajo y uno de avance alto, sin ningún centro especial.
 *
 * Los dos colores son fijos aquí (no vienen de `data/*.toml`: son estética de
 * presentación, no física ni un umbral — mismo criterio que
 * `OPACIDAD_MINIMA_POCA_CONFIANZA` en `malla/geometria.ts`) y se ELIGEN
 * deliberadamente distintos de los que usará `knock/mapa-densidad.ts`: el
 * avance no es un indicador de peligro, así que no toma el rojo de
 * `dlv-topes-linea--critico` que sí usa la densidad de knock (ver la cabecera
 * de ese módulo). Se usa el mismo azul de `--acento` (`index.html`), el color
 * de énfasis neutro que ya usan el cursor y la selección de canal — "más
 * avance" se lee como "más intensidad de un dato", no como "más alarma".
 */

import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Color } from "../render/tipos.ts";
import { type Clase } from "../unidades/conversion.ts";
import type { UnidadInfo } from "../unidades/tipos.ts";
import { t } from "../locale/catalogo.ts";
import { escalaSecuencial, rangoSecuencialDesdeDatos, type RangoSecuencial } from "../malla/escala-secuencial.ts";
import type { ConfiguracionMapaDeCalor, MallaResuelta } from "../malla/tipos.ts";
import { convertirValor } from "../unidades/conversion.ts";

/** Ver la cabecera del módulo: el avance es una LECTURA, nunca se deja que quien llama la cambie. */
const CLASE_VALOR_AVANCE: Clase = "punto";

/** Gris neutro (avance bajo) -> azul de `--acento` (avance alto). Ver la cabecera: deliberadamente NO el rojo de knock. */
const COLOR_AVANCE_BAJO: Color = { r: 0.94, g: 0.94, b: 0.94, a: 1 };
const COLOR_AVANCE_ALTO: Color = { r: 0.302, g: 0.639, b: 1.0, a: 1 };

export interface ConfiguracionMapaAvance {
  readonly area: AreaDibujo;
  /** Malla de avance de encendido (rol `ignition_advance`), en CANÓNICA (grados de cigüeñal). */
  readonly malla: MallaResuelta;
  readonly forma: { readonly filas: number; readonly columnas: number };
  /** La unidad activa de la dimensión `angle` (°, rad, ° de árbol), con su conversión. */
  readonly unidadActiva: UnidadInfo;
  /** Cuenta mínima para pintar una celda como confiable. Obligatorio: ver `malla/tipos.ts`. */
  readonly umbralConfianza: number;
  readonly colorSinDatos: Color;
  /**
   * Rango `[avance mínimo, avance máximo]` de la escala secuencial, en la
   * unidad de `unidadActiva`. Si se omite, se deduce del propio dato
   * (`rangoSecuencialDesdeDatos` sobre las medias de celda ya convertidas) —
   * NUNCA un rango "típico" cableado, mismo criterio que
   * `dlv_core.malla.bordes_por_omision` (ver la cabecera de
   * `escala-secuencial.ts`).
   */
  readonly rangoAvance?: RangoSecuencial;
}

export type ResultadoMapaAvance =
  | { readonly tipo: "activo"; readonly configuracion: ConfiguracionMapaDeCalor }
  | { readonly tipo: "deshabilitado"; readonly motivo: string };

/**
 * Construye la configuración del mapa de calor de avance de encendido, o
 * explica por qué no se puede pintar (ver la cabecera del módulo: solo
 * ocurre sin ninguna celda con dato del que deducir el rango de la escala).
 */
export function resolverMapaAvance(config: ConfiguracionMapaAvance): ResultadoMapaAvance {
  const { unidadActiva } = config;

  const mediasMostradas = config.malla.celdas.map((c) =>
    Number.isFinite(c.media) ? convertirValor(c.media, unidadActiva.conversion, CLASE_VALOR_AVANCE) : NaN,
  );
  const rango = config.rangoAvance ?? rangoSecuencialDesdeDatos(mediasMostradas);
  if (rango === null) {
    return { tipo: "deshabilitado", motivo: t("encendido.mapaAvance.sinDatosParaEscala") };
  }

  return {
    tipo: "activo",
    configuracion: {
      area: config.area,
      malla: config.malla,
      forma: config.forma,
      conversion: unidadActiva.conversion,
      claseValor: CLASE_VALOR_AVANCE,
      umbralConfianza: config.umbralConfianza,
      decimales: unidadActiva.decimales,
      colorDeValor: escalaSecuencial(COLOR_AVANCE_BAJO, COLOR_AVANCE_ALTO, rango),
      colorSinDatos: config.colorSinDatos,
    },
  };
}
