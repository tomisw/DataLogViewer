/**
 * Tipos de la vista paralela (F2-04): N segmentos superpuestos en un mismo
 * eje X, uno por log, distinguidos por color.
 *
 * ESTO NO ES UN PUERTO DE `dlv_core.tiempo` A TYPESCRIPT
 * =======================================================
 * `dlv_core/tiempo.py` (F2-01, terminado) es la especificación y NO se
 * reimplementa aquí. En concreto, `desfase_efectivo` —que decide el
 * `offset` de cada segmento según el modo (reloj absoluto, relativo, manual,
 * por evento, correlación) y comprueba `FiabilidadReloj` antes de aceptar el
 * modo de reloj— es una decisión de dominio con reglas propias (§3.6,
 * `docs/03-arquitectura.md`) y es el trabajo de tareas SEPARADAS del backlog:
 * F2-05 (reloj absoluto/relativo), F2-06 (arrastre manual), F2-07 (evento),
 * F2-08 (correlación cruzada). Ninguna de las cuatro está hecha todavía.
 *
 * Lo que esta vista necesita de `EjeVirtual` no es CÓMO se calculó el
 * desfase, sino el resultado ya resuelto: por eso `SegmentoParalelo.offset`
 * es un dato de entrada, no algo que este módulo calcule. Quien construya un
 * `SegmentoParalelo` (`dlv-api`, cuando exponga un endpoint que envuelva
 * `eje_paralelo` — hoy no existe ninguno, ver el informe de la tarea) es
 * quien decide ese número; esta vista solo lo consume, igual que
 * `comparacion/comparar-mallas.ts` consume una `MallaResuelta` ya agregada
 * sin volver a agregar celdas.
 *
 * `tInicio`/`tFin` sí viajan aquí, pero únicamente para que la vista pueda
 * calcular el rango que ocupan los segmentos ya desplazados
 * (`rangoVirtual`, espejo trivial de `EjeVirtual.x_min`/`x_max`: un
 * `Math.min`/`Math.max` sobre, como mucho, ocho números — el mismo caso
 * peor que cita la cabecera de `tiempo.py`, F2-15). No es la aritmética que
 * decide el desfase; es la aritmética que decide dónde cabe un desfase ya
 * decidido, que es justo lo que necesita cualquier vista para poner límites
 * al eje y que ADR-006 exige igualmente al renderizador (recibe un
 * rectángulo, no reglas de negocio).
 */

import type { ConversionAfin } from "../unidades/conversion.ts";

/**
 * Un log, ya resuelto para la vista paralela: su desfase es un HECHO que
 * llega de fuera (ver la cabecera del módulo), no algo que se calcule aquí.
 */
export interface SegmentoParalelo {
  /** Identidad del segmento (`Segmento.id` de `dlv_core.tiempo`). */
  readonly id: string;
  /** Nombre para la leyenda y la tabla del cursor. */
  readonly etiqueta: string;
  /** Primer instante local del log, en segundos. */
  readonly tInicio: number;
  /** Último instante local del log, en segundos. */
  readonly tFin: number;
  /**
   * Desfase ya resuelto: `x = tLocal + offset`. Mismo significado que
   * `EjeVirtual.desfase_de(id)` en `dlv_core.tiempo`, pero como dato de
   * entrada — ver la cabecera del módulo sobre por qué esta vista no lo
   * calcula.
   */
  readonly offset: number;
  /**
   * Canal elegido EN ESTE LOG para la comparación. F2-02 (identidad de canal
   * en capas, para emparejar automáticamente "el mismo canal" entre logs) no
   * está hecho y no es dependencia de F2-04, así que aquí cada segmento
   * declara explícitamente cuál de sus propios canales es el que se
   * compara — no hay adivinación de "el mismo rol" entre logs.
   */
  readonly canalId: string;
  /**
   * Dimensión física del canal elegido (`CanalDeFuente.dimensionId`,
   * `datos/fuente.ts`). Decide si este segmento se puede superponer con los
   * demás: ver `comprobarDimensionesCompatibles` en `vista-paralela.ts`.
   */
  readonly dimensionId: string;
  /**
   * Conversión CRUDO → CANÓNICA de este canal en este log
   * (`CanalDeFuente.aCanonica`). Es propia de cada log — dos ECUs pueden
   * escalar "la misma" señal de forma distinta — y es el primer paso
   * obligatorio de los dos que exige `unidades/conversion.ts#convertirDesdeCrudo`.
   * Sin ella, superponer dos logs con distinto factor de escala daría una de
   * las dos curvas multiplicada, con aspecto de comparación válida.
   */
  readonly aCanonica: ConversionAfin;
}

/** Resultado de comprobar que todos los segmentos comparan la misma dimensión física. */
export type ResultadoDimension =
  | { readonly tipo: "compatible"; readonly dimensionId: string }
  | { readonly tipo: "incompatible"; readonly motivo: string };

/** Una entrada de la leyenda: qué color representa a qué log. */
export interface EntradaLeyenda {
  readonly idSegmento: string;
  readonly etiqueta: string;
}
