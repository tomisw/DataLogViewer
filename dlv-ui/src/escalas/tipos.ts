/**
 * Contrato de datos de los ejes Y múltiples (F1-27).
 *
 * Misma frontera que `ejes/tipos.ts` marca para la capa SVG: aquí no hay
 * `Canal`, `Log` ni conversión de unidad (eso es F1-17 y el backend); lo que
 * entra y sale es un identificador de eje, un nombre de unidad ya elegido y
 * rangos numéricos. `GestorEscalas` (`gestor.ts`) es la única pieza con
 * estado; este fichero solo nombra sus formas de entrada y salida.
 */

import type { RangoValor } from "./rango.ts";

/**
 * Cómo obtiene su rango un eje:
 *
 * - `"autoescala"`: se recalcula en cada `GestorEscalas#actualizar` a partir
 *   del rango visible de sus series.
 * - `"bloqueado"`: fijo, `actualizar` no lo toca. Es lo que permite comparar
 *   dos tramos del log sin que el ojo se engañe — ver la cabecera de
 *   `gestor.ts` para el porqué.
 */
export type ModoEscala = "autoescala" | "bloqueado";

/**
 * El estado de un eje tal como lo ve quien lo consulta desde fuera
 * (`GestorEscalas#eje`/`#ejes`): de solo lectura, sin métodos.
 *
 * `modo` tiene que ser visible en la UI (requisito explícito de la tarea: «un
 * bloqueo invisible es peor que no tenerlo»). Este módulo no dibuja nada —esa
 * frontera es la misma de ADR-006—, así que el punto de enganche es
 * `etiquetas.ts#tituloConModo`: produce el texto que quien construya el
 * `ConfiguracionEjes.tituloY` de F1-25 debe usar para este eje, y ese título
 * ya lo pinta `ejes.ts` sin que este módulo tenga que tocar el DOM.
 */
export interface EstadoEje {
  readonly id: string;
  readonly unidad: string;
  readonly titulo: string;
  readonly modo: ModoEscala;
  /** El rango YA con margen aplicado: el que se usa para pintar, no el bruto. */
  readonly rango: RangoValor;
}

export type { RangoValor } from "./rango.ts";
