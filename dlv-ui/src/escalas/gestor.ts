/**
 * Múltiples ejes Y, autoescala y bloqueo de escala (F1-27).
 *
 * POR QUÉ EXISTE EL BLOQUEO
 * =========================
 * Un eje que se reescala solo, al mover la vista, hace que dos picos de
 * tamaño muy distinto se vean iguales — cada uno ocupa el mismo alto de panel
 * porque el eje se ajustó a su propio máximo. Esa es exactamente la lectura
 * falsa que un visor de logs no puede permitirse: comparar un pico de 6000 rpm
 * en la vuelta 3 con uno de 6500 rpm en la vuelta 8 exige que el eje sea el
 * MISMO en ambos tramos. Bloquear un eje es fijar esa vara de medir; sin
 * bloqueo, la autoescala por defecto es la que conviene para explorar un
 * canal nuevo, pero es la que engaña en cuanto se compara.
 *
 * QUÉ NO SABE ESTE MÓDULO
 * =======================
 * Igual que ADR-006 aísla al renderizador de "logs, unidades y perfiles",
 * `GestorEscalas` no sabe leer cubos ni pirámides: `actualizar` recibe ya
 * calculado el rango visible de cada serie (`RangoValor | null`), y quien lo
 * calcula —a partir de `CubosContinuos` de la caché de F1-24, o de lo que sea
 * que tenga la vista actual— es responsabilidad de quien ensambla el panel.
 * Esta frontera es la misma razón por la que `rango.ts` no importa nada de
 * `render/tipos.ts` ni de `datos/cache-cubos.ts`: la aritmética de rangos se
 * prueba sin saber qué es un cubo.
 *
 * LA SALIDA QUE ESPERA EL RENDERIZADOR
 * =====================================
 * `Renderizador.dibujar(vista, vistaPorSerie)` ya acepta un `Vista` por serie
 * — su docstring lo dice: «los ejes Y múltiples son F1-27, y esta es la
 * puerta que va a usar». `vistaPorSerie()` produce exactamente ese
 * `ReadonlyMap<string, Vista>`, combinando el `t0`/`t1` compartido de la
 * ventana de tiempo con el `v0`/`v1` — ya con margen — del eje de cada serie.
 * No hace falta tocar `renderizador.ts` para nada de esto.
 */

import type { Vista } from "../render/tipos.ts";
import {
  combinarRangos,
  conMargen,
  FRACCION_MARGEN_DEFECTO,
  type RangoValor,
} from "./rango.ts";
import type { EstadoEje, ModoEscala } from "./tipos.ts";

/**
 * Rango inicial de un eje recién creado sin `rangoInicial` explícito, antes
 * de la primera `actualizar()`. `[0, 1]` y no `[Infinity, -Infinity]` ni
 * `NaN`: un eje tiene que producir SIEMPRE una `Vista` con ancho finito y no
 * nulo, incluso en el primer fotograma, antes de que llegue ningún dato.
 */
const RANGO_POR_DEFECTO: RangoValor = { min: 0, max: 1 };

interface EjeInterno {
  readonly id: string;
  readonly unidad: string;
  readonly titulo: string;
  modo: ModoEscala;
  readonly fraccionMargen: number;
  /** El rango YA con margen aplicado — lo que de verdad se usa para pintar. */
  rango: RangoValor;
}

export interface OpcionesEje {
  /** Por omisión, la propia unidad — igual que `ConfiguracionEjes.tituloY` en F1-25. */
  readonly titulo?: string;
  /** Ver `FRACCION_MARGEN_DEFECTO` en `rango.ts`. */
  readonly fraccionMargen?: number;
  /** Rango bruto (sin margen) antes de la primera `actualizar()`. */
  readonly rangoInicial?: RangoValor;
  /** `"autoescala"` por omisión: un eje nuevo empieza sin bloquear. */
  readonly modoInicial?: ModoEscala;
}

/**
 * Gestiona los ejes Y de un panel: su rango (autoescalado o bloqueado), qué
 * serie usa cuál, y la `Vista` por serie que necesita el renderizador.
 *
 * Con estado, a propósito y con la misma forma que `CacheDeCubos` (F1-24):
 * una clase con métodos con nombre en vez de funciones puras, porque a
 * diferencia de `rango.ts` esto SÍ acumula algo entre llamadas — el modo de
 * cada eje y su último rango bueno—, que es justo lo que hace falta para que
 * "bloquear" signifique algo (fijar lo que ya había) y para que un canal que
 * se queda sin datos un fotograma no borre el rango del anterior.
 */
export class GestorEscalas {
  readonly #ejes = new Map<string, EjeInterno>();
  readonly #ejeDeSerie = new Map<string, string>();

  /**
   * Da de alta un eje nuevo. `id` es libre (normalmente la unidad, "rpm",
   * "°C" — o un nombre propio si dos ejes comparten unidad pero no rango,
   * como dos sensores de presión con full-scale distinto).
   */
  crearEje(id: string, unidad: string, opciones: OpcionesEje = {}): void {
    if (this.#ejes.has(id)) {
      throw new Error(`crearEje: ya existe un eje con el identificador «${id}»`);
    }
    const fraccionMargen = opciones.fraccionMargen ?? FRACCION_MARGEN_DEFECTO;
    if (!Number.isFinite(fraccionMargen) || fraccionMargen < 0) {
      throw new Error(
        `crearEje: fraccionMargen tiene que ser >= 0 y finita, llegó ${fraccionMargen}`,
      );
    }
    const rangoInicial = opciones.rangoInicial ?? RANGO_POR_DEFECTO;
    this.#ejes.set(id, {
      id,
      unidad,
      titulo: opciones.titulo ?? unidad,
      modo: opciones.modoInicial ?? "autoescala",
      fraccionMargen,
      rango: conMargen(rangoInicial, fraccionMargen),
    });
  }

  /** Asigna una serie a un eje ya existente. Una serie, un eje — no varios a la vez. */
  asignarSerie(serieId: string, ejeId: string): void {
    if (!this.#ejes.has(ejeId)) {
      throw new Error(`asignarSerie: no existe ningún eje con el identificador «${ejeId}»`);
    }
    this.#ejeDeSerie.set(serieId, ejeId);
  }

  /** A qué eje está asignada una serie, o `undefined` si no se ha asignado ninguno. */
  ejeDeSerie(serieId: string): string | undefined {
    return this.#ejeDeSerie.get(serieId);
  }

  /** El estado, de solo lectura, de un eje. Lanza si el `id` no existe. */
  eje(id: string): EstadoEje {
    return congelar(this.#requerirEje(id));
  }

  /** Todos los ejes dados de alta, en el orden en que se crearon. */
  get ejes(): readonly EstadoEje[] {
    return [...this.#ejes.values()].map(congelar);
  }

  /**
   * Bloquea un eje en su rango actual (o en el que se indique), para que
   * `actualizar()` deje de tocarlo hasta `desbloquear()`.
   *
   * `rango`, si se pasa, es BRUTO (sin margen) — se le aplica la misma
   * `fraccionMargen` del eje, igual que a cualquier rango que entra por
   * `actualizar()`, así que fijar un eje a mano y que lo haga la autoescala
   * dan el mismo tipo de resultado.
   */
  bloquear(ejeId: string, rango?: RangoValor): void {
    const eje = this.#requerirEje(ejeId);
    eje.modo = "bloqueado";
    if (rango !== undefined) eje.rango = conMargen(rango, eje.fraccionMargen);
  }

  /**
   * Vuelve a poner un eje en autoescala.
   *
   * No recalcula el rango en este mismo instante: hasta la próxima llamada a
   * `actualizar()` el eje sigue enseñando el rango con el que estaba
   * bloqueado. La alternativa —recalcular aquí mismo— exigiría que
   * `desbloquear()` reciba también el rango visible actual, y ese dato ya
   * llega por `actualizar()` en el ciclo normal de dibujo; pedirlo dos veces
   * solo abriría la puerta a que ambas llamadas discreparan.
   */
  desbloquear(ejeId: string): void {
    this.#requerirEje(ejeId).modo = "autoescala";
  }

  /** Bloquea si estaba en autoescala, desbloquea si estaba bloqueado. */
  alternarBloqueo(ejeId: string): void {
    const eje = this.#requerirEje(ejeId);
    if (eje.modo === "bloqueado") this.desbloquear(ejeId);
    else this.bloquear(ejeId);
  }

  /**
   * Recalcula el rango de los ejes en `"autoescala"` a partir del rango
   * visible de cada serie. Los ejes `"bloqueado"` se ignoran por completo.
   *
   * `rangosVisibles`: una entrada por serie con el rango SIN margen de la
   * parte de sus datos que cae en la ventana de tiempo actual, o `null` si la
   * serie no tiene ningún dato visible ahora mismo (el caso «canal todo
   * nulo», o simplemente un canal cuyo primer valor aparece más adelante en
   * el log). Una serie asignada a un eje pero ausente de este mapa se trata
   * igual que `null`: no aporta nada a la combinación de su eje.
   *
   * CASO «CANAL TODO NULO»: si NINGUNA serie de un eje autoescalado tiene
   * datos visibles esta vez, el eje CONSERVA su último rango bueno (el que
   * traía) en vez de colapsar a `[0, 1]` o a algo inventado. Es la misma
   * filosofía que el rango degenerado de `conMargen`: un dato que falta se
   * trata como "no cambies nada todavía", no como una razón para mostrar un
   * número que nadie midió.
   */
  actualizar(rangosVisibles: ReadonlyMap<string, RangoValor | null>): void {
    const rangosPorEje = new Map<string, (RangoValor | null)[]>();
    for (const [serieId, ejeId] of this.#ejeDeSerie) {
      const lista = rangosPorEje.get(ejeId) ?? [];
      lista.push(rangosVisibles.get(serieId) ?? null);
      rangosPorEje.set(ejeId, lista);
    }
    for (const [ejeId, lista] of rangosPorEje) {
      const eje = this.#ejes.get(ejeId);
      if (eje === undefined || eje.modo === "bloqueado") continue;
      const combinado = combinarRangos(lista);
      if (combinado === undefined) continue; // todas sin datos: se conserva el rango anterior
      eje.rango = conMargen(combinado, eje.fraccionMargen);
    }
  }

  /**
   * Produce el `ReadonlyMap<string, Vista>` que `Renderizador.dibujar` espera
   * como `vistaPorSerie`: el mismo `t0`/`t1` para todas las series —comparten
   * el eje de tiempo del panel, que no es cosa de esta tarea— y el `v0`/`v1`
   * del eje asignado a cada una.
   *
   * Series sin eje asignado (`asignarSerie` nunca llamado para ellas) no
   * aparecen en el mapa devuelto: `Renderizador.dibujar` ya trata la ausencia
   * en `vistaPorSerie` como "usa la vista compartida", así que omitirlas es
   * dejarlas con el comportamiento por omisión en vez de inventarles un eje.
   */
  vistaPorSerie(vistaX: Pick<Vista, "t0" | "t1">): ReadonlyMap<string, Vista> {
    const salida = new Map<string, Vista>();
    for (const [serieId, ejeId] of this.#ejeDeSerie) {
      const eje = this.#ejes.get(ejeId);
      if (eje === undefined) continue;
      salida.set(serieId, {
        t0: vistaX.t0,
        t1: vistaX.t1,
        v0: eje.rango.min,
        v1: eje.rango.max,
      });
    }
    return salida;
  }

  #requerirEje(id: string): EjeInterno {
    const eje = this.#ejes.get(id);
    if (eje === undefined) {
      throw new Error(`no existe ningún eje con el identificador «${id}»`);
    }
    return eje;
  }
}

function congelar(eje: EjeInterno): EstadoEje {
  return { id: eje.id, unidad: eje.unidad, titulo: eje.titulo, modo: eje.modo, rango: eje.rango };
}

export type { EstadoEje, ModoEscala } from "./tipos.ts";
export type { RangoValor } from "./rango.ts";
export { conMargen, combinarRangos, FRACCION_MARGEN_DEFECTO } from "./rango.ts";
export { etiquetaModo, tituloConModo } from "./etiquetas.ts";
