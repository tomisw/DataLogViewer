/**
 * Desfase manual arrastrando el segmento (F2-06), modo **Manual** de la tabla
 * «Vista paralela» de `docs/03-arquitectura.md` (`x = t_local + offset`).
 *
 * ESTO NO ES EL CÁLCULO DEL DESFASE, ES SU ÚNICA FORMA MANUAL DE PRODUCIRLO
 * ==========================================================================
 * `paralela/tipos.ts` ya deja escrito que `SegmentoParalelo.offset` es un
 * dato de ENTRADA, resuelto por uno de los cinco modos de la tabla de
 * `docs/03`, y que los otros cuatro (reloj absoluto/relativo F2-05, evento
 * F2-07, correlación F2-08) son tareas separadas. Este módulo es el modo
 * Manual: convierte un arrastre de ratón, en píxeles, en el `offset` nuevo
 * que ese modo produce. `docs/02` §2.10 (E2.4) llama a esto «obligatorio con
 * epoch ficticia»: cuando el reloj del log declara una época de fábrica que
 * no es real, ningún modo automático puede alinear nada, y arrastrar a mano
 * es la ÚNICA salida que le queda al usuario — no es un modo secundario.
 *
 * PÍXELES Y SEGUNDOS NO SON LA MISMA UNIDAD
 * ==========================================
 * El arrastre llega del navegador en píxeles de pantalla; `offset` es un
 * INTERVALO en segundos (regla del proyecto: la clase de conversión importa,
 * y un intervalo de tiempo no lleva el `aCanonica` de ningún canal — es ya la
 * unidad canónica, igual que `tInicio`/`tFin` en `tipos.ts`). La escala
 * píxel→segundo depende de la vista vigente en el instante en que EMPIEZA el
 * gesto (`segundosPorPixel`), exactamente como `navegacion/aritmetica.ts
 * #desplazarPx` usa el ancho del panel para lo mismo.
 *
 * EL SIGNO ES EL OPUESTO AL DE `desplazarPx`, Y ES A PROPÓSITO
 * ==============================================================
 * `desplazarPx` mueve la VENTANA sobre un contenido fijo (arrastrar el mapa):
 * arrastrar a la derecha adelanta lo que estaba fuera por la izquierda, así
 * que `t0` RETROCEDE. Aquí se arrastra el CONTENIDO de un único segmento
 * sobre un eje fijo (`x = t_local + offset`): arrastrar el segmento
 * `deltaXPx` a la derecha tiene que AVANZAR su `offset` esa misma cantidad de
 * segundos, para que el trazo se mueva hacia donde lo lleva el puntero. Con
 * el signo de `desplazarPx` (negado) el usuario arrastraría a la derecha y
 * el log se iría a la izquierda — exactamente el error que `arrastre.test.ts`
 * comprueba explícitamente.
 *
 * PÍXELES → SEGUNDOS, ACUMULACIÓN Y CANCELACIÓN, SEPARADOS DE LOS EVENTOS
 * ==========================================================================
 * `vitest.config.ts` corre en `environment: "node"`: sin DOM. Por eso, igual
 * que `navegacion/aritmetica.ts` frente a `navegacion/controlador.ts`, toda
 * la aritmética (`segundosPorPixel`, `offsetTrasArrastre`) es un puñado de
 * funciones puras sin ningún evento de por medio, probables con números a
 * secas. `ArrastreDeSegmento` es la mitad fina que traduce
 * `pointerdown`/`pointermove`/`pointerup`/`Escape` en llamadas a esas
 * funciones, reutilizando `navegacion/elemento.ts#ElementoNavegable` (la
 * misma interfaz mínima de DOM, no una tercera copia) para poder cablearse
 * sobre un `HTMLElement` real sin adaptador y probarse con el mismo tipo de
 * doble que ya usa `navegacion/controlador.test.ts`.
 *
 * El desfase, como el arrastre de `ControladorDeNavegacion`, se recalcula
 * SIEMPRE desde `offsetInicial` y `xInicialPx` (el estado al pulsar), nunca
 * sumando deltas incrementales fotograma a fotograma: eso es lo que evita
 * que un arrastre largo derive por acumulación de error de punto flotante.
 * La cancelación (`Escape`, o que el navegador cancele el puntero a media
 * acción) restaura ese mismo `offsetInicial` en vez de dejar el segmento a
 * medio mover.
 *
 * QUÉ NO DECIDE ESTE MÓDULO
 * ==========================
 * No hay zona muerta de arrastre ni paso de imantación: la tarea pide
 * arrastre libre («arrastrado por el usuario», `docs/03`), no una regla de
 * snapping que nadie ha pedido todavía. Si algún día hace falta, es un
 * umbral configurable nuevo (regla del proyecto: nada de números cableados
 * disfrazados de física), no algo que este módulo deba inventar hoy.
 *
 * QUÉ LE FALTA A ESTO PARA VERSE FUNCIONANDO EN LA APLICACIÓN
 * ===============================================================
 * Este módulo no decide QUÉ elemento del DOM dispara el arrastre de qué
 * segmento (el «asa»): eso depende de cómo `app/` dibuje la vista paralela
 * (¿la propia curva en el lienzo, con hit-testing por proximidad? ¿una fila
 * de la leyenda? Ninguna de las dos existe todavía) y de cómo decida
 * persistir el `offset` resultante en el `SegmentoParalelo` que consume
 * `vista-paralela.ts`. Ese cableado es trabajo de quien monte la vista
 * paralela completa en `app/aplicacion.ts` — explícitamente fuera de
 * alcance aquí (la tarea prohíbe tocar `app/`, y F2-04/F2-06 son piezas de
 * `dlv-ui/src/paralela/`, no la integración final).
 */

import type { ElementoNavegable, OyenteDeEvento } from "../navegacion/elemento.ts";
import type { Vista } from "../render/tipos.ts";

/** Lo único del eje temporal que hace falta para la escala píxel→segundo. */
export type RangoTemporal = Pick<Vista, "t0" | "t1">;

/**
 * Segundos que representa un solo píxel de ancho de panel, a la escala de
 * `rango`. Mismo cálculo que `navegacion/aritmetica.ts#desplazarPx` para su
 * eje temporal (`ancho / anchoPx`), factorizado aparte porque aquí hace falta
 * también fuera de esa función (ver `offsetTrasArrastre`).
 *
 * Un `anchoPanelPx` no positivo (panel de tamaño 0, a mitad de un
 * redimensionado) da `0` en vez de dividir por cero o por un negativo: sin
 * escala válida, ningún arrastre debe mover el segmento.
 */
export function segundosPorPixel(rango: RangoTemporal, anchoPanelPx: number): number {
  if (anchoPanelPx <= 0) return 0;
  return (rango.t1 - rango.t0) / anchoPanelPx;
}

/**
 * El `offset` nuevo tras arrastrar `deltaXPx` píxeles desde el inicio del
 * gesto, partiendo siempre de `offsetInicial` (nunca de un acumulado
 * incremental — ver la cabecera del módulo).
 *
 * SIGNO: positivo, sin negar. Arrastrar a la derecha (`deltaXPx > 0`) AUMENTA
 * el offset, así que el segmento se mueve a la derecha con el puntero — ver
 * la cabecera del módulo para por qué esto es lo contrario de
 * `desplazarPx` y no un error.
 */
export function offsetTrasArrastre(
  offsetInicial: number,
  deltaXPx: number,
  rango: RangoTemporal,
  anchoPanelPx: number,
): number {
  return offsetInicial + deltaXPx * segundosPorPixel(rango, anchoPanelPx);
}

/** Lo que `ArrastreDeSegmento` entrega cada vez que el offset visible cambia. */
export interface InfoArrastreDeSegmento {
  /** `SegmentoParalelo.id` del segmento que se está arrastrando. */
  readonly idSegmento: string;
  /** El `offset` (segundos) que debería aplicarse ahora mismo a ese segmento. */
  readonly offset: number;
}

export interface OpcionesArrastreDeSegmento {
  /** Programador de fotograma. Inyectable por las pruebas (sin `requestAnimationFrame` en `node`). */
  readonly programarFotograma?: (resolver: () => void) => number;
  readonly cancelarFotograma?: (id: number) => void;
}

interface EstadoArrastre {
  readonly pointerId: number;
  readonly xInicialPx: number;
  readonly offsetInicial: number;
  readonly rango: RangoTemporal;
  readonly anchoPanelPx: number;
}

/**
 * Cablea el arrastre manual de UN segmento sobre un elemento del DOM (el
 * «asa»: quien monte la vista decide qué elemento es — ver la cabecera del
 * módulo, «QUÉ LE FALTA A ESTO»). Un `ArrastreDeSegmento` por segmento, igual
 * que `LeyendaSegmentos` no es singleton por vista sino que cada entrada es
 * la suya.
 *
 * Sigue el mismo patrón de fotograma único que `ControladorDeNavegacion`:
 * cada `pointermove` actualiza el estado interno al instante, pero
 * `alCambiar` se pospone a un `requestAnimationFrame` por fotograma, así que
 * un arrastre con cientos de eventos por segundo no repinta más veces de las
 * que hay fotogramas.
 */
export class ArrastreDeSegmento {
  readonly #asa: ElementoNavegable;
  readonly #idSegmento: string;
  readonly #obtenerOffsetActual: () => number;
  readonly #obtenerRangoVisible: () => RangoTemporal;
  readonly #obtenerAnchoPanelPx: () => number;
  readonly #alCambiar: (info: InfoArrastreDeSegmento) => void;
  readonly #programarFotograma: (resolver: () => void) => number;
  readonly #cancelarFotograma: (id: number) => void;

  #arrastre: EstadoArrastre | null = null;
  #offsetPendiente = 0;
  #idFotograma: number | null = null;

  readonly #onPointerDown: OyenteDeEvento = (evento) =>
    this.#manejarPointerDown(evento as PointerEvent);
  readonly #onPointerMove: OyenteDeEvento = (evento) =>
    this.#manejarPointerMove(evento as PointerEvent);
  readonly #onPointerFin: OyenteDeEvento = (evento) => this.#manejarPointerFin(evento as PointerEvent);
  readonly #onTecla: OyenteDeEvento = (evento) => this.#manejarTecla(evento as KeyboardEvent);

  constructor(
    asa: ElementoNavegable,
    idSegmento: string,
    obtenerOffsetActual: () => number,
    obtenerRangoVisible: () => RangoTemporal,
    obtenerAnchoPanelPx: () => number,
    alCambiar: (info: InfoArrastreDeSegmento) => void,
    opciones: OpcionesArrastreDeSegmento = {},
  ) {
    this.#asa = asa;
    this.#idSegmento = idSegmento;
    this.#obtenerOffsetActual = obtenerOffsetActual;
    this.#obtenerRangoVisible = obtenerRangoVisible;
    this.#obtenerAnchoPanelPx = obtenerAnchoPanelPx;
    this.#alCambiar = alCambiar;
    this.#programarFotograma =
      opciones.programarFotograma ?? ((resolver) => requestAnimationFrame(() => resolver()));
    this.#cancelarFotograma = opciones.cancelarFotograma ?? ((id) => cancelAnimationFrame(id));

    this.#asa.addEventListener("pointerdown", this.#onPointerDown);
    this.#asa.addEventListener("pointermove", this.#onPointerMove);
    this.#asa.addEventListener("pointerup", this.#onPointerFin);
    this.#asa.addEventListener("pointercancel", this.#onPointerFin);
    this.#asa.addEventListener("keydown", this.#onTecla);
  }

  /** Hay un gesto de arrastre en curso (el puntero está pulsado sobre el asa). */
  get enCurso(): boolean {
    return this.#arrastre !== null;
  }

  /** Retira los oyentes y cancela el fotograma pendiente, si lo hay. */
  destruir(): void {
    this.#asa.removeEventListener("pointerdown", this.#onPointerDown);
    this.#asa.removeEventListener("pointermove", this.#onPointerMove);
    this.#asa.removeEventListener("pointerup", this.#onPointerFin);
    this.#asa.removeEventListener("pointercancel", this.#onPointerFin);
    this.#asa.removeEventListener("keydown", this.#onTecla);
    if (this.#idFotograma !== null) {
      this.#cancelarFotograma(this.#idFotograma);
      this.#idFotograma = null;
    }
    this.#arrastre = null;
  }

  #manejarPointerDown(evento: PointerEvent): void {
    if (evento.button > 0) return; // botón secundario/auxiliar: no es un gesto de arrastre
    this.#asa.setPointerCapture(evento.pointerId);
    this.#arrastre = {
      pointerId: evento.pointerId,
      xInicialPx: evento.clientX,
      offsetInicial: this.#obtenerOffsetActual(),
      // Instantánea de la escala vigente al EMPEZAR el gesto: si la vista
      // cambia de zoom a mitad de un arrastre (poco probable, pero posible
      // con teclado en otro panel), el gesto en curso sigue siendo
      // coherente consigo mismo en vez de cambiar de escala a mitad de
      // camino, el mismo criterio que `vistaInicial` en
      // `ControladorDeNavegacion`.
      rango: this.#obtenerRangoVisible(),
      anchoPanelPx: this.#obtenerAnchoPanelPx(),
    };
  }

  #manejarPointerMove(evento: PointerEvent): void {
    const arrastre = this.#arrastre;
    if (arrastre === null || evento.pointerId !== arrastre.pointerId) return;
    const deltaXPx = evento.clientX - arrastre.xInicialPx;
    const offset = offsetTrasArrastre(
      arrastre.offsetInicial,
      deltaXPx,
      arrastre.rango,
      arrastre.anchoPanelPx,
    );
    this.#pedirNotificacion(offset);
  }

  #manejarPointerFin(evento: PointerEvent): void {
    const arrastre = this.#arrastre;
    if (arrastre === null || evento.pointerId !== arrastre.pointerId) return;
    this.#asa.releasePointerCapture(evento.pointerId);
    this.#arrastre = null;
    // El último `pointermove` ya dejó pedida (o aplicada) la notificación con
    // el offset final: soltar el puntero no cambia el valor, solo cierra el
    // gesto. No hace falta un evento de "confirmado" aparte.
  }

  /**
   * Cancela el gesto en curso y restaura `offsetInicial`: usado por `Escape`
   * y disponible también para que quien monte la vista cancele desde fuera
   * (p. ej. si el panel pierde el foco a media acción).
   */
  cancelar(): void {
    const arrastre = this.#arrastre;
    if (arrastre === null) return;
    this.#asa.releasePointerCapture(arrastre.pointerId);
    this.#arrastre = null;
    this.#pedirNotificacion(arrastre.offsetInicial);
  }

  #manejarTecla(evento: KeyboardEvent): void {
    if (evento.key !== "Escape" || this.#arrastre === null) return;
    evento.preventDefault();
    this.cancelar();
  }

  #pedirNotificacion(offset: number): void {
    this.#offsetPendiente = offset;
    if (this.#idFotograma !== null) return;
    this.#idFotograma = this.#programarFotograma(() => {
      this.#idFotograma = null;
      this.#alCambiar({ idSegmento: this.#idSegmento, offset: this.#offsetPendiente });
    });
  }
}
