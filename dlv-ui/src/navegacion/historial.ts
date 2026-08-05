/**
 * Historial de navegación con deshacer/rehacer (F1-28).
 *
 * La pieza que decide qué es "un paso" cuando el gesto que lo produce no lo
 * es: 40 eventos de rueda en dos segundos son un único gesto de zoom para
 * quien mira la pantalla, y un historial que registrara los 40 obligaría a
 * pulsar deshacer 40 veces para volver al principio — un historial así no se
 * usa, se rodea.
 *
 * La regla de agrupación es de TIEMPO, no de conteo ni de tipo de evento: si
 * dos registros llegan separados por menos de `umbralGestoMs`, el segundo
 * SUSTITUYE al primero en vez de abrir un paso nuevo. Un arrastre entero
 * (`pointerdown` → …→ `pointerup`) cae siempre dentro del umbral porque un
 * fotograma dura ~16 ms, muy por debajo de los 400 ms por omisión; también
 * una tecla de flecha mantenida (que repite cada pocas decenas de ms). Una
 * pausa real entre dos gestos distintos, no.
 */

import type { Vista } from "../render/tipos.ts";

export interface OpcionesHistorial {
  /** Cuántos pasos guarda como máximo antes de olvidar el más antiguo. */
  readonly maxPasos?: number;
  /** Ventana, en ms, dentro de la cual dos registros cuentan como un gesto. */
  readonly umbralGestoMs?: number;
}

/**
 * 200 pasos: cada uno son cuatro números, así que el coste de memoria es
 * irrelevante; el número solo evita que una sesión de horas acumule un
 * array sin límite. Holgado de sobra frente a lo que un tuner deshace de
 * verdad en una sesión (unas pocas decenas de gestos).
 */
const MAX_PASOS_POR_DEFECTO = 200;

/**
 * 400 ms: más que el hueco entre eventos de un gesto continuo (un fotograma,
 * ~16 ms, o la repetición de una tecla mantenida, unas pocas decenas de ms) y
 * menos que el tiempo que tarda una persona en decidir y empezar el
 * siguiente gesto por separado.
 */
const UMBRAL_GESTO_MS_POR_DEFECTO = 400;

export class HistorialDeVista {
  readonly #maxPasos: number;
  readonly #umbralGestoMs: number;
  readonly #pasos: Vista[];
  #indice: number;
  #ultimoRegistro = Number.NEGATIVE_INFINITY;

  constructor(vistaInicial: Vista, opciones: OpcionesHistorial = {}) {
    this.#maxPasos = opciones.maxPasos ?? MAX_PASOS_POR_DEFECTO;
    this.#umbralGestoMs = opciones.umbralGestoMs ?? UMBRAL_GESTO_MS_POR_DEFECTO;
    if (this.#maxPasos < 1) {
      throw new Error("`maxPasos` tiene que ser al menos 1: sin eso no cabe ni el paso inicial");
    }
    this.#pasos = [vistaInicial];
    this.#indice = 0;
  }

  /** La vista vigente: la del paso en el que está el historial ahora mismo. */
  get actual(): Vista {
    return this.#pasos[this.#indice]!;
  }

  get puedeDeshacer(): boolean {
    return this.#indice > 0;
  }

  get puedeRehacer(): boolean {
    return this.#indice < this.#pasos.length - 1;
  }

  /**
   * Registra una vista nueva en el instante `ahora`.
   *
   * `ahora` tiene que venir del mismo reloj en todas las llamadas —en
   * producción, `performance.now()`— porque es la única entrada de la que
   * depende la agrupación en gestos; el historial en sí no lee ningún reloj
   * para poder probarse con marcas de tiempo inventadas.
   *
   * Si había pasos de rehacer pendientes, registrar SIEMPRE los corta y abre
   * un paso propio, sin importar cuán rápido llegue: seguir navegando
   * después de deshacer descarta lo deshecho en cualquier editor, y dejarlo
   * "pendiente de agruparse" con el paso que se acaba de abandonar mezclaría
   * dos ramas de historia distintas en una.
   */
  registrar(vista: Vista, ahora: number): void {
    const habiaRehacer = this.puedeRehacer;
    if (habiaRehacer) this.#pasos.length = this.#indice + 1;

    const esGestoNuevo = habiaRehacer || ahora - this.#ultimoRegistro > this.#umbralGestoMs;
    if (esGestoNuevo) {
      this.#pasos.push(vista);
      this.#indice += 1;
      if (this.#pasos.length > this.#maxPasos) {
        this.#pasos.shift();
        this.#indice -= 1;
      }
    } else {
      this.#pasos[this.#indice] = vista;
    }
    this.#ultimoRegistro = ahora;
  }

  /**
   * Retrocede un paso, o se queda donde está si ya estaba en el primero.
   *
   * No lanza en el límite: deshacer sin nada que deshacer es una acción
   * normal en cualquier interfaz (el botón se deshabilita con
   * `puedeDeshacer`, no falla si se pulsa de todos modos).
   */
  deshacer(): Vista {
    if (this.puedeDeshacer) this.#indice -= 1;
    return this.actual;
  }

  /** Avanza un paso, o se queda donde está si ya estaba en el último. */
  rehacer(): Vista {
    if (this.puedeRehacer) this.#indice += 1;
    return this.actual;
  }
}
