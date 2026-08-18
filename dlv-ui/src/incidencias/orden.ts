/**
 * Lógica pura del panel de incidencias (F3-12): orden por consecuencia,
 * duración y las filas por detector que distinguen «desactivado» de «activo
 * sin incidencias». Nada de DOM aquí — eso es `panel-incidencias.ts` —, así
 * que todo esto se puede probar con `node --experimental-transform-types`
 * sin levantar un navegador (ver el informe de la tarea).
 */

import { compararSeveridad, rangoDeSeveridad } from "./severidad.ts";
import { SEVERIDADES_CONCRETAS, type DetectorCatalogo, type EstadoDetector, type IncidenciaPanel, type SeveridadConcreta } from "./tipos.ts";

/** Mismo nombre que `primitivas.py#MS_POR_S`, mismo valor, mismo motivo. */
const MS_POR_S = 1000;

/**
 * Ordena por CONSECUENCIA, no por tiempo: criterio #1 de la tarea.
 *
 * Primero por severidad (`compararSeveridad`, más grave primero); dentro de
 * la misma severidad, por instante de inicio ascendente — leer una tanda de
 * críticas en el orden en que ocurrieron es más útil que leerlas de la más
 * reciente a la más antigua, porque es el orden en que un tuner reproduciría
 * el log. `Array.prototype.sort` es estable desde ES2019 (todos los motores
 * que ejecutan esto), así que dos incidencias con la misma severidad y el
 * mismo `tInicioMs` conservan el orden de llegada en vez de barajarse en
 * cada llamada.
 *
 * No muta `incidencias`: devuelve una copia. El array que entra puede ser el
 * mismo que ya se está pintando en otra vista (p. ej. una lista cronológica
 * futura), y ordenar en el sitio lo rompería en silencio.
 */
export function ordenarPorConsecuencia(
  incidencias: readonly IncidenciaPanel[],
): readonly IncidenciaPanel[] {
  return [...incidencias].sort((a, b) => {
    const porSeveridad = compararSeveridad(a.severidad, b.severidad);
    if (porSeveridad !== 0) return porSeveridad;
    return a.tInicioMs - b.tInicioMs;
  });
}

/**
 * Duración observada en segundos, o `null` cuando la incidencia no tiene fin
 * (misma condición que `Evento.duracion_s` en Python, que exige `t_fin_ms`).
 * Una incidencia de una sola muestra tiene `tFinMs === tInicioMs` y dura 0 s,
 * no `null` — igual que en el motor: no haber visto el intervalo posterior
 * no es lo mismo que no tener fin.
 */
export function duracionS(incidencia: IncidenciaPanel): number | null {
  if (incidencia.tFinMs === null) return null;
  return (incidencia.tFinMs - incidencia.tInicioMs) / MS_POR_S;
}

/**
 * El instante (segundos absolutos) al que debe saltar la vista al pulsar
 * esta incidencia — la unidad de `render/tipos.ts#Vista.t0`/`t1`, que es la
 * que de verdad consume la navegación. Se salta al INICIO, no al pico ni al
 * fin: es el primer instante en que la condición se cumplió, y es a partir
 * de ahí desde donde tiene sentido examinar la traza.
 */
export function instanteDeSalto(incidencia: IncidenciaPanel): number {
  return incidencia.tInicioMs / MS_POR_S;
}

/** Cuenta y duración total (segundos) de un grupo de incidencias del mismo detector. */
export interface ResumenDetector {
  readonly conteo: number;
  /** Suma de `duracionS`; las incidencias sin fin no aportan (no `null`, tampoco 0 fingido). */
  readonly duracionTotalS: number;
  /** `true` si al menos una incidencia del grupo no tiene fin observado. */
  readonly conIncidenciasSinFin: boolean;
}

function resumirIncidencias(incidencias: readonly IncidenciaPanel[]): ResumenDetector {
  let duracionTotalS = 0;
  let conIncidenciasSinFin = false;
  for (const incidencia of incidencias) {
    const d = duracionS(incidencia);
    if (d === null) {
      conIncidenciasSinFin = true;
    } else {
      duracionTotalS += d;
    }
  }
  return { conteo: incidencias.length, duracionTotalS, conIncidenciasSinFin };
}

/**
 * Una fila del catálogo de detectores: su identidad, si está activo (y por
 * qué no, si no lo está) y el resumen de SUS incidencias.
 *
 * Es la pieza que hace el criterio #3 de la tarea posible: un detector
 * desactivado y uno activo sin incidencias tienen el mismo `resumen.conteo
 * === 0`, y lo único que los distingue es `estado`. Quien pinte esta fila
 * tiene que mirar `estado.activo` ANTES de decidir si «0» significa «todo
 * bien» o «no se sabe, y aquí está por qué».
 */
export interface FilaDetector {
  readonly detector: DetectorCatalogo;
  readonly estado: EstadoDetector;
  readonly incidencias: readonly IncidenciaPanel[];
  readonly resumen: ResumenDetector;
}

/**
 * Construye una fila por detector del catálogo, cruzando su estado
 * (activo/desactivado) con las incidencias que le pertenecen.
 *
 * Recorre `catalogo`, no `incidencias`: un detector desactivado no produce
 * incidencias (docs/07 §7.15), así que si se recorriera `incidencias` para
 * decidir qué filas existen, un detector desactivado simplemente no
 * aparecería — vacío, indistinguible de «todo bien», que es la trampa que la
 * tarea prohíbe explícitamente. Recorriendo el catálogo, el detector
 * desactivado tiene fila igual, con `incidencias: []` y `estado.activo ===
 * false`.
 *
 * Un detector sin entrada en `estados` se trata como activo: es la posición
 * que ya tenía antes de que existiera la desactivación de §7.15 (la mayoría
 * de los 18 detectores no tiene condición de desactivación), y tratarlo como
 * desactivado por omisión escondería incidencias reales de un backend que
 * simplemente no manda `estados` todavía (ver el informe de la tarea).
 */
export function construirFilasDeDetector(
  catalogo: readonly DetectorCatalogo[],
  estados: readonly EstadoDetector[],
  incidencias: readonly IncidenciaPanel[],
): readonly FilaDetector[] {
  const estadoPorId = new Map(estados.map((e) => [e.detectorId, e]));
  const incidenciasPorDetector = new Map<string, IncidenciaPanel[]>();
  for (const incidencia of incidencias) {
    const grupo = incidenciasPorDetector.get(incidencia.detectorId);
    if (grupo === undefined) {
      incidenciasPorDetector.set(incidencia.detectorId, [incidencia]);
    } else {
      grupo.push(incidencia);
    }
  }

  return catalogo.map((detector) => {
    const estado = estadoPorId.get(detector.id) ?? { detectorId: detector.id, activo: true as const };
    const propias = incidenciasPorDetector.get(detector.id) ?? [];
    return {
      detector,
      estado,
      incidencias: propias,
      resumen: resumirIncidencias(propias),
    };
  });
}

/**
 * Rango de una fila para el catálogo por consecuencia: por debajo de 0 (el
 * más grave posible entre las cinco severidades) para que un detector
 * DESACTIVADO encabece siempre el catálogo — «no se sabe si hay knock» pesa
 * más que cualquier severidad concreta, porque es la que se puede estar
 * perdiendo. Dentro de los activos, el rango es el de su incidencia MÁS
 * grave (mínimo de `rangoDeSeveridad`); un detector activo sin incidencias
 * no tiene ninguna severidad que mostrar y va al final, con
 * `Number.POSITIVE_INFINITY`.
 *
 * Nótese que esto NO necesita ordenar por `SeveridadCatalogo` (que admitiría
 * `"segun_nivel"`, sin rango definido): usa las severidades YA RESUELTAS de
 * las incidencias reales, que siempre son una de las cinco concretas.
 */
function rangoDeFila(fila: FilaDetector): number {
  if (!fila.estado.activo) return -1;
  if (fila.incidencias.length === 0) return Number.POSITIVE_INFINITY;
  return Math.min(...fila.incidencias.map((i) => rangoDeSeveridad(i.severidad)));
}

/**
 * Ordena las filas del catálogo por consecuencia: desactivados primero,
 * luego los activos con incidencias (el de peor severidad antes), luego los
 * activos sin incidencias. Dentro del mismo rango, por etiqueta para que el
 * orden sea determinista y no dependa de en qué posición llegó cada
 * detector del catálogo.
 */
export function ordenarFilasDeDetector(filas: readonly FilaDetector[]): readonly FilaDetector[] {
  return [...filas].sort((a, b) => {
    const rangoA = rangoDeFila(a);
    const rangoB = rangoDeFila(b);
    // Comparación explícita y no `rangoA - rangoB`: dos filas activas sin
    // incidencias tienen AMBAS `Number.POSITIVE_INFINITY`, y
    // `Infinity - Infinity` es `NaN` — un comparador de `sort` que devuelve
    // `NaN` no tiene un resultado garantizado por la especificación, y es
    // justo el caso más común (la mayoría de los 18 detectores no dispara
    // nunca en un log sin problemas).
    const porRango = rangoA === rangoB ? 0 : rangoA - rangoB;
    if (porRango !== 0) return porRango;
    return a.detector.etiqueta.localeCompare(b.detector.etiqueta);
  });
}

/**
 * Cuenta de incidencias por severidad, en el orden de `SEVERIDADES_CONCRETAS`
 * (así que iterar las claves del resultado ya sale en orden de consecuencia).
 * Es el resumen de «¿ha ido todo bien?» que pide `docs/04` §4.3 para el panel:
 * cinco números que se leen en un vistazo, antes de bajar a la lista.
 */
export function contarPorSeveridad(
  incidencias: readonly IncidenciaPanel[],
): Readonly<Record<SeveridadConcreta, number>> {
  const conteo = Object.fromEntries(SEVERIDADES_CONCRETAS.map((s) => [s, 0])) as Record<
    SeveridadConcreta,
    number
  >;
  for (const incidencia of incidencias) {
    conteo[incidencia.severidad] += 1;
  }
  return conteo;
}
