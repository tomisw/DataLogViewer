/**
 * Cableado de eventos de navegación: rueda, arrastre por *pointer events* y
 * teclado, con historial de deshacer/rehacer (F1-28).
 *
 * Es la mitad "fina" del módulo: traduce eventos del navegador en llamadas a
 * `aritmetica.ts` y `historial.ts`, y no hace nada más. No dibuja —el
 * contrato de `Vista` sigue siendo el de F1-23— y no decide la aritmética del
 * zoom, el pan o el agrupado de gestos, que ya están probados por separado
 * sin DOM.
 *
 * UN SOLO FOTOGRAMA, NO UN EVENTO
 * ================================
 * Cada evento (rueda, `pointermove`, tecla) actualiza el estado interno al
 * instante —es aritmética barata, unas restas y multiplicaciones— pero la
 * notificación a quien escucha (`alCambiar`) se pospone a un único
 * `requestAnimationFrame` por fotograma: si ya hay uno pedido, un evento más
 * no pide otro, solo dejará una vista más reciente para cuando se resuelva.
 * Un arrastre dispara `pointermove` muchas más veces de las que hay
 * fotogramas; notificar en cada uno —y con ello, típicamente, subir cubos y
 * redibujar— haría más trabajo que fotogramas hay, que es justo la
 * advertencia de la tarea. Solo el ÚLTIMO estado de cada fotograma llega a
 * `alCambiar`.
 *
 * QUÉ EJE TOCA CADA ENTRADA
 * =========================
 * La rueda y +/- de teclado amplían solo el eje temporal. El eje de valores
 * todavía no tiene autoescala ni bloqueo —eso es F1-27— y decidir aquí cómo
 * se comporta bajo zoom adelantaría una decisión que no es de este módulo;
 * arrastrar y las flechas arriba/abajo sí lo desplazan, porque desplazar no
 * compite con una autoescala futura del modo en que ampliar sí lo haría.
 */

import { desplazar, desplazarPx, direccionDe, zoomEnPunto, type Direccion } from "./aritmetica.ts";
import type { ElementoNavegable, OyenteDeEvento } from "./elemento.ts";
import { HistorialDeVista } from "./historial.ts";
import type { Vista } from "../render/tipos.ts";

export interface InfoNavegacion {
  readonly vista: Vista;
  readonly direccion: Direccion;
}

export interface OpcionesControlador {
  /** Rango completo del log: lo que deja ver la tecla de "ver todo". */
  readonly limites?: Vista;
  /** Fracción del ancho/alto visible que mueve cada pulsación de flecha. */
  readonly pasoPanTeclado?: number;
  /** Factor de zoom de cada pulsación de +/-. */
  readonly pasoZoomTeclado?: number;
  /** Cuánto zoom produce un "clic" de rueda de ~100 unidades de `deltaY`. */
  readonly sensibilidadRueda?: number;
  /** Ventana de agrupación de gestos, en ms. Ver `historial.ts`. */
  readonly umbralGestoMs?: number;
  /** Tope de pasos del historial. Ver `historial.ts`. */
  readonly maxPasosHistorial?: number;
  /** Fuente de tiempo para agrupar gestos. Inyectable por las pruebas. */
  readonly ahora?: () => number;
  /** Programador de fotograma. Inyectable por las pruebas. */
  readonly programarFotograma?: (resolver: () => void) => number;
  readonly cancelarFotograma?: (id: number) => void;
}

const PASO_PAN_TECLADO_POR_DEFECTO = 0.1;
const PASO_ZOOM_TECLADO_POR_DEFECTO = 1.2;
/**
 * `factor = exp(-deltaY * sensibilidad)`: con `deltaY` típico de ~100 por
 * "clic" de rueda y esta sensibilidad, un clic amplía o aleja en torno a un
 * 15 %, que es perceptible sin ser brusco. La exponencial (y no una resta
 * lineal) es lo que garantiza `factorValido` en `aritmetica.ts` sin tener que
 * comprobarlo aquí: `exp` de cualquier número finito es siempre positivo.
 */
const SENSIBILIDAD_RUEDA_POR_DEFECTO = 0.0015;

function comprobarRectangulo(vista: Vista, contexto: string): void {
  if (!(vista.t1 > vista.t0) || !(vista.v1 > vista.v0)) {
    throw new Error(
      `${contexto}: la vista está del revés o no tiene anchura (${JSON.stringify(vista)})`,
    );
  }
}

/**
 * Cablea rueda, *pointer events* y teclado sobre un elemento y traduce cada
 * gesto en una `Vista` nueva, con historial de deshacer/rehacer.
 *
 * No dibuja ni sabe qué hay pintado en `elemento`: solo necesita su
 * geometría (`getBoundingClientRect`) y sus eventos. Quien construye el
 * controlador decide qué hacer con cada `Vista` que llega por `alCambiar`
 * (normalmente, pedírsela al `Renderizador` de F1-23).
 */
export class ControladorDeNavegacion {
  readonly #elemento: ElementoNavegable;
  readonly #historial: HistorialDeVista;
  readonly #alCambiar: (info: InfoNavegacion) => void;
  readonly #pasoPanTeclado: number;
  readonly #pasoZoomTeclado: number;
  readonly #sensibilidadRueda: number;
  readonly #ahora: () => number;
  readonly #programarFotograma: (resolver: () => void) => number;
  readonly #cancelarFotograma: (id: number) => void;

  #limites: Vista | undefined;
  #vista: Vista;
  #direccion: Direccion = 0;
  #idFotograma: number | null = null;
  #arrastre: { pointerId: number; xInicial: number; yInicial: number; vistaInicial: Vista } | null =
    null;

  // Referencias ligadas una sola vez, para poder retirarlas en `destruir()`
  // con el mismo valor de función con el que se añadieron.
  readonly #onRueda: OyenteDeEvento = (evento) => this.#manejarRueda(evento as WheelEvent);
  readonly #onPointerDown: OyenteDeEvento = (evento) =>
    this.#manejarPointerDown(evento as PointerEvent);
  readonly #onPointerMove: OyenteDeEvento = (evento) =>
    this.#manejarPointerMove(evento as PointerEvent);
  readonly #onPointerFin: OyenteDeEvento = (evento) => this.#manejarPointerFin(evento as PointerEvent);
  readonly #onTecla: OyenteDeEvento = (evento) => this.#manejarTecla(evento as KeyboardEvent);

  constructor(
    elemento: ElementoNavegable,
    vistaInicial: Vista,
    alCambiar: (info: InfoNavegacion) => void,
    opciones: OpcionesControlador = {},
  ) {
    comprobarRectangulo(vistaInicial, "ControladorDeNavegacion");
    this.#elemento = elemento;
    this.#vista = vistaInicial;
    this.#alCambiar = alCambiar;
    this.#limites = opciones.limites;
    this.#pasoPanTeclado = opciones.pasoPanTeclado ?? PASO_PAN_TECLADO_POR_DEFECTO;
    this.#pasoZoomTeclado = opciones.pasoZoomTeclado ?? PASO_ZOOM_TECLADO_POR_DEFECTO;
    this.#sensibilidadRueda = opciones.sensibilidadRueda ?? SENSIBILIDAD_RUEDA_POR_DEFECTO;
    this.#ahora = opciones.ahora ?? (() => performance.now());
    this.#programarFotograma =
      opciones.programarFotograma ?? ((resolver) => requestAnimationFrame(() => resolver()));
    this.#cancelarFotograma = opciones.cancelarFotograma ?? ((id) => cancelAnimationFrame(id));
    this.#historial = new HistorialDeVista(vistaInicial, {
      maxPasos: opciones.maxPasosHistorial,
      umbralGestoMs: opciones.umbralGestoMs,
    });

    // `wheel` con `passive: false`: sin eso, `preventDefault` en el manejador
    // no evita el scroll de la página, y la rueda haría dos cosas a la vez.
    this.#elemento.addEventListener("wheel", this.#onRueda, { passive: false });
    this.#elemento.addEventListener("pointerdown", this.#onPointerDown);
    this.#elemento.addEventListener("pointermove", this.#onPointerMove);
    this.#elemento.addEventListener("pointerup", this.#onPointerFin);
    this.#elemento.addEventListener("pointercancel", this.#onPointerFin);
    this.#elemento.addEventListener("keydown", this.#onTecla);
  }

  /** La vista vigente (la del último fotograma resuelto, no la pendiente). */
  get vista(): Vista {
    return this.#vista;
  }

  /** Dirección del último movimiento horizontal. Ver `direccionDe`. */
  get direccion(): Direccion {
    return this.#direccion;
  }

  get puedeDeshacer(): boolean {
    return this.#historial.puedeDeshacer;
  }

  get puedeRehacer(): boolean {
    return this.#historial.puedeRehacer;
  }

  /** Fija (o cambia) el rango que usa "ver todo". Sin límites, esa tecla no hace nada. */
  establecerLimites(limites: Vista): void {
    comprobarRectangulo(limites, "establecerLimites");
    this.#limites = limites;
  }

  /** Vuelve al rango completo fijado por `establecerLimites`. No-op si no hay ninguno. */
  verTodo(): void {
    if (this.#limites === undefined) return;
    this.#aplicarNueva(this.#limites);
  }

  deshacer(): void {
    this.#actualizarYNotificar(this.#historial.deshacer());
  }

  rehacer(): void {
    this.#actualizarYNotificar(this.#historial.rehacer());
  }

  /** Retira los oyentes y cancela el fotograma pendiente, si lo hay. */
  destruir(): void {
    this.#elemento.removeEventListener("wheel", this.#onRueda);
    this.#elemento.removeEventListener("pointerdown", this.#onPointerDown);
    this.#elemento.removeEventListener("pointermove", this.#onPointerMove);
    this.#elemento.removeEventListener("pointerup", this.#onPointerFin);
    this.#elemento.removeEventListener("pointercancel", this.#onPointerFin);
    this.#elemento.removeEventListener("keydown", this.#onTecla);
    if (this.#idFotograma !== null) {
      this.#cancelarFotograma(this.#idFotograma);
      this.#idFotograma = null;
    }
  }

  /** Vista nueva que SÍ abre (o continúa) un paso de historial. */
  #aplicarNueva(vista: Vista): void {
    this.#historial.registrar(vista, this.#ahora());
    this.#actualizarYNotificar(this.#historial.actual);
  }

  /** Actualiza el estado visible y pide la notificación del fotograma. NO toca el historial. */
  #actualizarYNotificar(vista: Vista): void {
    const anterior = this.#vista;
    this.#vista = vista;
    this.#direccion = direccionDe(anterior, vista);
    this.#pedirNotificacion();
  }

  #pedirNotificacion(): void {
    if (this.#idFotograma !== null) return;
    this.#idFotograma = this.#programarFotograma(() => {
      this.#idFotograma = null;
      this.#alCambiar({ vista: this.#vista, direccion: this.#direccion });
    });
  }

  #manejarRueda(evento: WheelEvent): void {
    evento.preventDefault();
    const rect = this.#elemento.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const fraccionX = (evento.clientX - rect.left) / rect.width;
    const fraccionY = (evento.clientY - rect.top) / rect.height;
    // `deltaY > 0` (rueda "hacia el usuario") aleja; `deltaY < 0` amplía —la
    // misma convención que un mapa. Solo el eje temporal cambia (`factorY = 1`).
    const factorX = Math.exp(-evento.deltaY * this.#sensibilidadRueda);
    this.#aplicarNueva(zoomEnPunto(this.#vista, factorX, 1, fraccionX, fraccionY));
  }

  #manejarPointerDown(evento: PointerEvent): void {
    if (evento.button > 0) return; // botón secundario/auxiliar: no es un arrastre de navegación
    this.#elemento.setPointerCapture(evento.pointerId);
    this.#arrastre = {
      pointerId: evento.pointerId,
      xInicial: evento.clientX,
      yInicial: evento.clientY,
      vistaInicial: this.#vista,
    };
  }

  #manejarPointerMove(evento: PointerEvent): void {
    const arrastre = this.#arrastre;
    if (arrastre === null || evento.pointerId !== arrastre.pointerId) return;
    const rect = this.#elemento.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    // El desplazamiento se calcula SIEMPRE desde la vista de inicio del
    // arrastre, no de forma incremental fotograma a fotograma: acumular
    // cientos de pequeños deltas de punto flotante derivaría con un
    // arrastre largo, y recalcular desde el origen no tiene ese problema.
    const nueva = desplazarPx(
      arrastre.vistaInicial,
      evento.clientX - arrastre.xInicial,
      evento.clientY - arrastre.yInicial,
      rect.width,
      rect.height,
    );
    this.#aplicarNueva(nueva);
  }

  #manejarPointerFin(evento: PointerEvent): void {
    if (this.#arrastre !== null && evento.pointerId === this.#arrastre.pointerId) {
      this.#elemento.releasePointerCapture(evento.pointerId);
      this.#arrastre = null;
    }
  }

  #manejarTecla(evento: KeyboardEvent): void {
    const tieneModificadorDeAtajo = evento.ctrlKey || evento.metaKey;
    if (tieneModificadorDeAtajo && evento.key.toLowerCase() === "z") {
      evento.preventDefault();
      if (evento.shiftKey) this.rehacer();
      else this.deshacer();
      return;
    }
    if (tieneModificadorDeAtajo && evento.key.toLowerCase() === "y") {
      evento.preventDefault();
      this.rehacer();
      return;
    }
    switch (evento.key) {
      case "ArrowLeft":
        evento.preventDefault();
        this.#panTeclado(-1, 0);
        return;
      case "ArrowRight":
        evento.preventDefault();
        this.#panTeclado(1, 0);
        return;
      case "ArrowUp":
        evento.preventDefault();
        this.#panTeclado(0, 1);
        return;
      case "ArrowDown":
        evento.preventDefault();
        this.#panTeclado(0, -1);
        return;
      case "+":
      case "=":
        evento.preventDefault();
        this.#aplicarNueva(zoomEnPunto(this.#vista, this.#pasoZoomTeclado, 1, 0.5, 0.5));
        return;
      case "-":
      case "_":
        evento.preventDefault();
        this.#aplicarNueva(zoomEnPunto(this.#vista, 1 / this.#pasoZoomTeclado, 1, 0.5, 0.5));
        return;
      case "Home":
        evento.preventDefault();
        this.verTodo();
        return;
      default:
        return;
    }
  }

  #panTeclado(signoT: number, signoV: number): void {
    const ancho = this.#vista.t1 - this.#vista.t0;
    const alto = this.#vista.v1 - this.#vista.v0;
    this.#aplicarNueva(
      desplazar(this.#vista, signoT * this.#pasoPanTeclado * ancho, signoV * this.#pasoPanTeclado * alto),
    );
  }
}
