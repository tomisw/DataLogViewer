/**
 * Contrato de datos del mapa de calor de una malla RPM×MAP (F4-04, F4-02,
 * `dlv_core.malla`).
 *
 * QUÉ ES GENÉRICO AQUÍ, Y QUÉ NO LO ES
 * =====================================
 * F4-04 es «mapa de calor de λ error», pero **no es la única tarea que va a
 * pintar una malla de celdas**: F4-07 (avance de encendido, densidad de
 * knock) y F4-08 (comparación de dos logs celda a celda) pintan la MISMA
 * rejilla con otro canal. Por eso este módulo no sabe nada de λ, de φ ni de
 * estequiometría — eso vive en `src/lambda/mapa-error.ts`, que es la pieza
 * ESPECÍFICA que construye una `ConfiguracionMapaDeCalor` a partir de una
 * `MallaResuelta` de error de λ. Lo que hay aquí es exactamente lo que
 * `topes/tipos.ts` es para `ejes/tipos.ts`: la forma de un dato ya resuelto,
 * sin la lógica de dominio que lo produjo.
 *
 * `MallaResuelta` es el espejo TypeScript de `dlv_core.malla.Malla`: los
 * mismos cinco campos por celda (`cuenta`, `media`, `desviacionTipica`,
 * `minimo`, `maximo`), en CANÓNICA (ADR-004) — este módulo no convierte nada
 * al construir la malla, igual que `construir_malla` en Python. A diferencia
 * de la `Malla` de Python (arrays planos de NumPy, por rendimiento sobre 73 M
 * de muestras), aquí las celdas ya son el resultado agregado —unas decenas o
 * unos pocos cientos de celdas, nunca muestras— así que un array de objetos
 * es la representación más simple sin que ADR-009 tenga nada que decir: la
 * regla es sobre recorrer MUESTRAS con un `for`, no sobre recorrer celdas.
 *
 * `bordesFila`/`bordesColumna` en cambio llegan YA en la unidad MOSTRADA
 * (como `Vista.t0/t1/v0/v1` en `render/tipos.ts` y como hace
 * `dlv_core.malla.bordes_en_unidad_activa`): son `Clase.PUNTO` sin ambigüedad
 * posible (un borde de bin es un valor absoluto del eje), así que no hay
 * ninguna decisión de clase que dejarle a quien llama, a diferencia de las
 * CINCO ESTADÍSTICAS de cada celda — ver la nota de `claseValor` más abajo.
 *
 * LA TRAMPA: `claseValor` NO ES SIEMPRE «PUNTO»
 * ================================================
 * `dlv_core.malla.CLASE_DE_ESTADISTICA` declara `media`/`minimo`/`maximo`
 * como `Clase.PUNTO` — pero esa tabla asume que el canal `valor` que se
 * agregó en la malla es EN SÍ MISMO un punto (λ, densidad de knock, avance de
 * encendido: lecturas absolutas). Cuando el canal agregado ya es una
 * DIFERENCIA —el caso de F4-04: λ medida − λ objetivo, o el de F4-08: log A
 * − log B—, la media, el mínimo y el máximo de esa diferencia SIGUEN siendo
 * diferencias: `Clase.INTERVALO`, no `Clase.PUNTO`. Aplicarles el
 * desplazamiento de origen `b` de una conversión afín sería exactamente el
 * error que la regla 4 de `CLAUDE.md` prohíbe.
 *
 * Por eso este módulo no asume ninguna clase por las cinco estadísticas: la
 * declara aparte, en `ConfiguracionMapaDeCalor.claseValor`, como parámetro
 * OBLIGATORIO y sin valor por omisión (misma disciplina que `convertirValor`
 * en `unidades/conversion.ts`). `desviacionTipica` es la única que NUNCA es
 * `Clase.PUNTO` — es una dispersión, `Clase.INTERVALO` siempre, sea cual sea
 * la clase del canal agregado — así que no se parametriza: se aplica fija
 * dentro de `geometria.ts`.
 *
 * CUENTA, CONFIANZA Y CELDA VACÍA: TRES CONCEPTOS DISTINTOS
 * =============================================================
 * - `cuenta === 0`: la celda no tiene NINGUNA muestra. `media`, `minimo`,
 *   `maximo` y `desviacionTipica` llegan como `NaN` (igual que en
 *   `dlv_core.malla`, nunca `0`: «una celda sin ninguna muestra... sería
 *   indistinguible de una celda con datos reales cuyo canal vale
 *   legítimamente cero»). Estado `"vacia"`.
 * - `0 < cuenta < umbralConfianza`: hay datos, pero pocos. Un color intenso
 *   sobre `n = 1` es una afirmación que el dato no sostiene (E7.3,
 *   `docs/02`). Estado `"pocaConfianza"`.
 * - `cuenta >= umbralConfianza`: la celda se pinta con toda su intensidad.
 *   Estado `"confiable"`.
 *
 * `umbralConfianza` es OBLIGATORIO y sin valor por omisión, a propósito:
 * regla 3 de `CLAUDE.md` («los umbrales son configurables», precedencia canal
 * > perfil > usuario > fichero, `data/umbrales.toml`). Ese fichero no tiene
 * hoy ninguna entrada para «cuántas muestras hacen confiable una celda de
 * este mapa» — la de 20 muestras que sí existe (`segmentacion.crucero`,
 * comentario de la línea 528) es la de la TABLA DE CORRECCIÓN DE COMBUSTIBLE
 * de F4-05, un umbral distinto para un propósito distinto. Cablear aquí un
 * número «razonable» sería inventar un umbral por omisión sin que el
 * propietario lo haya fijado, justo lo que la regla prohíbe hacer sin
 * preguntar. Quien construya la configuración (hoy, las pruebas; mañana,
 * `dlv-api` cuando exponga la malla) decide el número.
 */

import type { Color, Vista } from "../render/tipos.ts";
import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Clase, Conversion } from "../unidades/conversion.ts";

/** Las cinco estadísticas de una celda (`dlv_core.malla.Malla`), en CANÓNICA. */
export interface CeldaEstadisticas {
  /** Número de muestras agregadas. Sin clase, nunca se convierte (`dlv_core.malla`). */
  readonly cuenta: number;
  /** `NaN` si `cuenta === 0`. Clase: la que declare `claseValor` de la configuración. */
  readonly media: number;
  /** `NaN` si `cuenta === 0`. Clase: SIEMPRE `Clase.INTERVALO` (es una dispersión). */
  readonly desviacionTipica: number;
  /** `NaN` si `cuenta === 0`. Clase: la que declare `claseValor`. */
  readonly minimo: number;
  /** `NaN` si `cuenta === 0`. Clase: la que declare `claseValor`. */
  readonly maximo: number;
}

/**
 * Espejo TypeScript de `dlv_core.malla.Malla`: bordes en CANÓNICA (rpm; kPa
 * absolutos) y las celdas en orden de fila (`fila * columnas + columna`,
 * igual que `Malla.forma` documenta para sus arrays planos).
 *
 * Este tipo es el que produce, mañana, el endpoint de `dlv-api` que hoy NO
 * existe (ver el informe de F4-04): nada en este fichero asume que ya está
 * cableado.
 */
export interface MallaResuelta {
  /** Bordes del eje de filas, CANÓNICOS, longitud `filas + 1`, crecientes. */
  readonly bordesFila: readonly number[];
  /** Bordes del eje de columnas, CANÓNICOS, longitud `columnas + 1`, crecientes. */
  readonly bordesColumna: readonly number[];
  /** Longitud `filas * columnas`, orden de fila. */
  readonly celdas: readonly CeldaEstadisticas[];
}

/** En qué situación de confianza está una celda (ver la cabecera del módulo). */
export type EstadoCelda = "vacia" | "pocaConfianza" | "confiable";

/** Las cinco estadísticas de una celda, ya en la unidad MOSTRADA y formateadas para leer. */
export interface DetalleCelda {
  readonly fila: number;
  readonly columna: number;
  readonly estado: EstadoCelda;
  /** `Malla.celdas[i]` sin convertir: por si quien consume necesita el dato crudo. */
  readonly celda: CeldaEstadisticas;
  /** `cuenta`, formateada («—» no aplica: cuenta siempre es un entero válido). */
  readonly cuentaTexto: string;
  /** `media`/`desviacionTipica`/`minimo`/`maximo` ya convertidas y formateadas; «—» si `NaN`. */
  readonly mediaTexto: string;
  readonly desviacionTipicaTexto: string;
  readonly minimoTexto: string;
  readonly maximoTexto: string;
}

/** Un rectángulo de celda ya resuelto a píxeles del área, con su color y su detalle. */
export interface CeldaPintada {
  readonly fila: number;
  readonly columna: number;
  readonly x: number;
  readonly y: number;
  readonly ancho: number;
  readonly alto: number;
  readonly estado: EstadoCelda;
  /** Color de relleno YA con la opacidad de confianza aplicada (ver `geometria.ts`). */
  readonly color: Color;
  readonly detalle: DetalleCelda;
}

/**
 * Lo que necesita `calcularGeometriaMapaDeCalor` para decidir la geometría,
 * el color y el estado de cada celda.
 *
 * Sin campo de unidad de eje / etiqueta: ESE dibujo (rejilla, ticks, título)
 * ya lo hace `ejes/ejes.ts` sobre el MISMO `AreaDibujo` — igual que
 * `topes/geometria.ts` no repite esa responsabilidad. Quien monte la escena
 * llama primero a `pintarEjes` (con un `ConfiguracionEjes` cuya `vista` cubre
 * `[bordesColumna[0], bordesColumna[-1]] x [bordesFila[0], bordesFila[-1]]`
 * ya en unidad mostrada) y pinta el mapa de calor DEBAJO, con la misma área.
 */
export interface ConfiguracionMapaDeCalor {
  readonly area: AreaDibujo;
  /** Malla en CANÓNICA. Ver la cabecera para el porqué de no convertir aquí. */
  readonly malla: MallaResuelta;
  /** Cuántas filas/columnas tiene `malla.celdas` (`bordesFila.length - 1`, `bordesColumna.length - 1`). */
  readonly forma: { readonly filas: number; readonly columnas: number };
  /** Conversión activa canónica → mostrada del canal agregado (p. ej. λ→AFR). */
  readonly conversion: Conversion;
  /**
   * Clase de `media`/`minimo`/`maximo` — NO necesariamente `Clase.PUNTO`. Ver
   * la cabecera del módulo: es la trampa de esta tarea, y es obligatoria sin
   * valor por omisión (regla 4 de `CLAUDE.md`).
   */
  readonly claseValor: Clase;
  /** Parámetro de una conversión `parametrizada` (p. ej. estequiometría λ→AFR), si aplica. */
  readonly parametro?: number;
  /** Cuenta mínima para el estado `"confiable"`. Obligatorio: ver la cabecera del módulo. */
  readonly umbralConfianza: number;
  /** Decimales al formatear el detalle. Por omisión 2, igual que `topes/geometria.ts`. */
  readonly decimales?: number;
  /**
   * Color de una celda `"confiable"` o `"pocaConfianza"`, a partir de su valor
   * YA CONVERTIDO a la unidad mostrada (`media`, salvo que se indique lo
   * contrario). La escala en sí —divergente para un error, secuencial para un
   * avance de encendido, la que haga falta— es responsabilidad de quien
   * llama: este módulo no sabe qué significa el número, solo dónde pintarlo.
   */
  readonly colorDeValor: (valorMostrado: number, celda: CeldaEstadisticas) => Color;
  /**
   * Color de una celda `"vacia"`. Deliberadamente un parámetro y no una
   * constante: el mismo motivo que `carriles/color.ts` deja los ajustes de
   * tema fuera de este módulo — un mapa de calor en tema oscuro y otro en
   * tema claro no pueden compartir un gris cableado sin que uno de los dos se
   * vea mal.
   */
  readonly colorSinDatos: Color;
}

/** Salida de `calcularGeometriaMapaDeCalor`: todo lo que `mapa-de-calor.ts` necesita para pintar. */
export interface GeometriaMapaDeCalor {
  readonly area: AreaDibujo;
  /** Longitud `forma.filas * forma.columnas`, mismo orden que `malla.celdas`. */
  readonly celdas: readonly CeldaPintada[];
}

export type { AreaDibujo, Color, Vista };
