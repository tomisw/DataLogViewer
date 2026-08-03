/**
 * Contrato de datos de los carriles de estado (F3-13).
 *
 * Un canal enumerado (marcha engranada, estado del motor, modo de mapa) no es
 * una curva: es una secuencia de estados que duran. `docs/03-arquitectura.md`
 * §3.5 lo dice para la variante `ENUM` de la pirámide: «moda + marca de
 * transiciones — evita parpadeo en los carriles». Este fichero es el
 * equivalente, para esa variante, de `render/tipos.ts` para `CONTINUO`: la
 * frontera de lo que entra en el componente y nada de lo que no le hace falta
 * saber (ADR-006 otra vez — un carril no sabe de logs, unidades ni perfiles).
 */

import type { Color } from "../render/tipos.ts";

/**
 * Un nivel de la pirámide `ENUM` ya en el frontend (`NivelEnum` de
 * `dlv_core.piramide`, transportado por Arrow IPC según ADR-007). Mismos
 * campos `t`/`tOrigen`/`factor` que `CubosContinuos` (`render/tipos.ts`), por
 * la misma razón de precisión explicada allí: `t` es relativo a `tOrigen` para
 * no perder resolución en `Float32Array` con logs largos.
 */
export interface CubosEnum {
  /** Instante de inicio de cada cubo, en segundos relativos a `tOrigen`. */
  readonly t: Float32Array;
  /** Segundos absolutos a los que corresponde `t[0] === 0`. Doble, no float32. */
  readonly tOrigen: number;
  /**
   * Código de estado más frecuente del cubo (`NivelEnum.moda`). `Int32Array`
   * y no un entero sin signo: hay canales con códigos negativos (p. ej.
   * `Launch Control State`, códigos −101…1, `docs/04` §4.2).
   */
  readonly moda: Int32Array;
  /**
   * `NivelEnum.hubo_transicion`: 1 si dentro de este cubo hubo más de un
   * código distinto, 0 si no. `Uint8Array` y no `boolean[]` por lo mismo que
   * el resto de `dlv-ui` usa arrays tipados para datos que vienen de la
   * pirámide — es la forma en que Arrow IPC entrega un array de bits.
   *
   * Es la marca que hace posible el carril de estado: a zoom alejado la moda
   * de un cubo puede coincidir con la del cubo vecino y fusionarse en una
   * sola banda de color, pero si CUALQUIERA de los cubos fusionados tenía
   * `huboTransicion`, hubo un cambio real que la moda por sí sola no enseña
   * (`piramide.py`, docstring de `NivelEnum`: «un cambio de marcha rápido
   * desaparece de la pantalla»). El carril tiene que marcarlo aunque la
   * banda de color no cambie.
   */
  readonly huboTransicion: Uint8Array;
  /** Factor de decimación del nivel (1 = sin decimar). */
  readonly factor: number;
}

/**
 * Código de estado → etiqueta legible ("3" → "3ª", "0" → "Neutral"…).
 *
 * Dato de entrada, no de este módulo: el diccionario lo trae el perfil o el
 * canal (p. ej. los códigos de `Launch Control State` de `docs/04` §4.2), y
 * este componente nunca lo inventa ni copia valores de `data/*.toml` — solo
 * dibuja lo que le llega. Un código ausente del diccionario se sigue
 * mostrando (como código crudo, ver `BandaCarril.etiquetaFaltante`), nunca en
 * blanco.
 */
export type DiccionarioCodigos = ReadonlyMap<number, string>;

/** El tramo de tiempo visible. Solo `t0`/`t1`: un carril no tiene eje de valores. */
export interface RangoTiempo {
  readonly t0: number;
  readonly t1: number;
}

/** Lo que necesita `calcularGeometriaCarril` / `pintarCarril` para dibujar un carril. */
export interface ConfiguracionCarril {
  readonly cubos: CubosEnum;
  readonly etiquetas: DiccionarioCodigos;
  readonly vista: RangoTiempo;
  /** Ancho del carril completo, en píxeles CSS. */
  readonly anchoPx: number;
  /** Alto del carril completo, en píxeles CSS. Por omisión `ALTO_BANDA_DEFECTO`. */
  readonly altoPx?: number;
}

/** Una banda de color: un tramo contiguo con el mismo código de estado. */
export interface BandaCarril {
  readonly codigo: number;
  /** `etiquetas.get(codigo)` si existe; si no, el código crudo como texto. */
  readonly etiqueta: string;
  /** `true` si `codigo` no estaba en el diccionario: `etiqueta` es el código crudo. */
  readonly etiquetaFaltante: boolean;
  readonly color: Color;
  readonly xPx: number;
  readonly anchoPx: number;
}

/** Una marca de "aquí hubo una transición" (`NivelEnum.hubo_transicion`). */
export interface MarcaTransicion {
  readonly xPx: number;
  readonly anchoPx: number;
}

/** Salida de `calcularGeometriaCarril`: todo lo que `carril-estado.ts` necesita para pintar. */
export interface GeometriaCarril {
  readonly anchoPx: number;
  readonly altoPx: number;
  readonly bandas: readonly BandaCarril[];
  readonly transiciones: readonly MarcaTransicion[];
}
