/**
 * Paneles apilados con eje X compartido y arrastre de canales (F1-26).
 *
 * QUÉ HACE Y QUÉ NO (ADR-006, mismo criterio que `render/tipos.ts` y
 * `ejes/tipos.ts`)
 * ======================================================================
 * Este componente coloca N paneles verticales, reparte el alto entre ellos y
 * lleva la cuenta de qué canal está en qué panel. **No dibuja series** (eso
 * es `render/renderizador.ts`, F1-23), **no calcula ejes** (eso es
 * `ejes/geometria.ts`, F1-25) y no sabe qué es un canal más allá de un
 * identificador y una etiqueta (`CanalEnPanel`, `tipos.ts`). Quien monta la
 * aplicación real llama a `contenidoDe(panelId)` para obtener el elemento
 * donde montar el lienzo WebGL2 y el SVG de ejes de ese panel.
 *
 * EL EJE X COMPARTIDO, Y POR QUÉ ES LA PARTE QUE MÁS IMPORTA PROTEGER
 * ======================================================================
 * El requisito central de la tarea es que los N paneles compartan el eje X:
 * es lo que permite leer causa y efecto entre canales apilados (un pico de
 * detonación contra la posición del acelerador, en el ejemplo de la tarea).
 * Si un panel se desincroniza del resto en su mapeo tiempo→píxel, la lectura
 * que se saca de mirar los dos trazos alineados es falsa, y no hay nada en
 * pantalla que lo delate: los dos trazos siguen dibujándose, solo que uno
 * está desplazado un puñado de píxeles respecto al otro.
 *
 * La forma en que esto podría romperse en silencio es medir el ancho de cada
 * panel por separado: una barra de scroll que aparece en uno solo de ellos
 * (por ejemplo, porque su cabecera de canales creció más líneas que la de los
 * demás) le resta ~15 px de ancho útil a ESE panel y a ningún otro. Por eso
 * este componente mide el ancho **una sola vez**, desde el contenedor raíz
 * (`anchoContenidoPx`), y lo aplica como `width` explícito —no como
 * porcentaje ni como resultado del cálculo de caja de flexbox— al elemento de
 * contenido de cada panel, con `overflow: hidden` para que ese ancho no
 * pueda cambiar después por lo que el panel meta dentro. `paneles.test.ts`
 * comprueba que los N paneles reciben exactamente el mismo número tras
 * construirse, tras redimensionar un divisor y tras un cambio de tamaño del
 * contenedor: las tres operaciones que existen en este módulo y que podrían,
 * si algo se rompiera, hacer que un panel se quedara con un ancho distinto.
 *
 * REPARTO DE ALTO Y ARRASTRE DE CANALES
 * ======================================================================
 * La aritmética de alturas vive en `reparto.ts` (pura, probada sin DOM); la
 * de a qué panel apunta el puntero y cómo se mueve un canal de una lista a
 * otra vive en `asignacion.ts` (también pura). Este fichero es la fontanería
 * que conecta *pointer events* reales con esas dos funciones — mismo reparto
 * de responsabilidades que `ejes/geometria.ts` (aritmética) frente a
 * `ejes/ejes.ts` (DOM).
 *
 * *Pointer events* y no `mousedown`/`mousemove` (pide la tarea): un mismo
 * `pointerdown` cubre ratón, lápiz y dedo. `setPointerCapture` sobre el
 * elemento que inicia el arrastre (la ficha del canal o el divisor) es lo
 * que evita tener que escuchar en `document` o `window`: el propio elemento
 * sigue recibiendo `pointermove`/`pointerup` aunque el puntero salga de sus
 * límites, que es exactamente lo que pasa al arrastrar una ficha a un panel
 * de más arriba o más abajo.
 *
 * Antes de soltar, el panel destino se resalta (`dlv-panel--destino-arrastre`)
 * para que se vea dónde va a caer la ficha — lo pide la tarea explícitamente
 * porque un arrastre sin objetivo visible es el tipo de interacción que el
 * propietario no puede validar con un vistazo.
 */

import {
  indiceDeCanal,
  moverCanal as moverCanalPuro,
  panelEnY,
  type PanelRect,
} from "./asignacion.ts";
import {
  contextoDesdeDocumento,
  elementoDesdeHtml,
  type ContextoDOM,
  type ElementoDOM,
  type EventoPuntero,
} from "./contexto-dom.ts";
import { alturaTotal, arrastrarDivisor, reescalarAlturas, repartirAlturasIniciales } from "./reparto.ts";
import type { AlturasPaneles, CambioAsignacion, CanalEnPanel, DefinicionPanel, OpcionesPaneles } from "./tipos.ts";

const ALTURA_MINIMA_PX_DEFECTO = 60;
const ALTO_DIVISOR_PX = 6;

const CLASE_PANEL = "dlv-panel";
const CLASE_PANEL_DESTINO = "dlv-panel--destino-arrastre";
const CLASE_CABECERA = "dlv-panel-cabecera";
const CLASE_CONTENIDO = "dlv-panel-contenido";
const CLASE_DIVISOR = "dlv-panel-divisor";
const CLASE_CHIP = "dlv-panel-chip";
const CLASE_CHIP_ARRASTRANDO = "dlv-panel-chip--arrastrando";

interface ArrastreCanal {
  readonly canalId: string;
  readonly panelOrigen: string;
  readonly chip: ElementoDOM;
  destinoActual: string | null;
}

interface ArrastreDivisor {
  readonly panelSuperior: string;
  readonly panelInferior: string;
  readonly clientYInicial: number;
  readonly alturaSuperiorInicial: number;
  readonly alturaInferiorInicial: number;
}

export class PanelesApilados {
  readonly #ctx: ContextoDOM;
  readonly #contenedor: ElementoDOM;
  readonly #alturaMinimaPx: number;
  readonly #alCambiarAsignacion?: (cambio: CambioAsignacion) => void;
  readonly #alRedimensionar?: (alturasPx: AlturasPaneles) => void;

  #orden: string[];
  #asignaciones: Map<string, readonly CanalEnPanel[]>;
  #alturasPx = new Map<string, number>();
  #anchoContenidoPx = 0;

  readonly #elementoPanel = new Map<string, ElementoDOM>();
  readonly #elementoCabecera = new Map<string, ElementoDOM>();
  readonly #elementoContenido = new Map<string, ElementoDOM>();

  #arrastreCanal: ArrastreCanal | null = null;
  #arrastreDivisor: ArrastreDivisor | null = null;

  /**
   * Construye el componente dentro de `contenedor`, que ya tiene que estar
   * en el documento y con un alto resuelto (el que le dé el layout de la
   * aplicación): este componente reparte ESE alto, no decide el suyo propio.
   *
   * Toma un `ContextoDOM`/`ElementoDOM` ya adaptados en vez de un
   * `HTMLElement` real directamente — mismo motivo que `Renderizador` toma
   * un `ContextoGL` ya creado (F1-23): así se prueba en Node contra el doble
   * (`doble-dom.ts`) sin inventar un modo de pruebas dentro de la propia
   * clase. Para el caso normal está el factory `PanelesApilados.montar`.
   */
  constructor(contenedor: ElementoDOM, definiciones: readonly DefinicionPanel[], opciones: OpcionesPaneles = {}) {
    if (definiciones.length === 0) {
      throw new Error("PanelesApilados necesita al menos una definición de panel");
    }
    const idsVistos = new Set<string>();
    for (const definicion of definiciones) {
      if (idsVistos.has(definicion.id)) {
        throw new Error(`panel duplicado: «${definicion.id}»`);
      }
      idsVistos.add(definicion.id);
    }

    this.#contenedor = contenedor;
    this.#alturaMinimaPx = opciones.alturaMinimaPx ?? ALTURA_MINIMA_PX_DEFECTO;
    this.#alCambiarAsignacion = opciones.alCambiarAsignacion;
    this.#alRedimensionar = opciones.alRedimensionar;
    this.#ctx = opciones.documento ?? contextoDesdeDocumento(document);

    this.#orden = definiciones.map((definicion) => definicion.id);
    this.#asignaciones = new Map(definiciones.map((definicion) => [definicion.id, definicion.canales] as const));

    this.#contenedor.style.setProperty("display", "flex");
    this.#contenedor.style.setProperty("flex-direction", "column");
    this.#contenedor.style.setProperty("overflow", "hidden");

    this.#construirPaneles();
    this.#recalcularDesdeContenedor(repartirAlturasIniciales);
  }

  /**
   * Factory para el caso normal: `contenedor` es un `HTMLElement` de verdad
   * ya en el documento. Ver la nota de cabecera de `contexto-dom.ts` sobre
   * por qué hace falta el adaptador.
   */
  static montar(
    contenedor: HTMLElement,
    definiciones: readonly DefinicionPanel[],
    opciones: OpcionesPaneles = {},
  ): PanelesApilados {
    return new PanelesApilados(elementoDesdeHtml(contenedor), definiciones, opciones);
  }

  /** El elemento donde quien ensambla la aplicación monta el lienzo WebGL2 y el SVG de ejes de `panelId`. */
  contenidoDe(panelId: string): ElementoDOM {
    const elemento = this.#elementoContenido.get(panelId);
    if (elemento === undefined) throw new Error(`no existe el panel «${panelId}»`);
    return elemento;
  }

  /** Los canales asignados a `panelId`, en el orden en que se ven en la cabecera. */
  canalesDe(panelId: string): readonly CanalEnPanel[] {
    const lista = this.#asignaciones.get(panelId);
    if (lista === undefined) throw new Error(`no existe el panel «${panelId}»`);
    return lista;
  }

  /** Copia de las alturas actuales, en píxeles CSS, por identificador de panel. */
  alturasPx(): AlturasPaneles {
    return new Map(this.#alturasPx);
  }

  /**
   * El ancho compartido por el área de contenido de TODOS los paneles. Es el
   * número que hace posible el eje X compartido (ver la cabecera del
   * módulo): quien monta el SVG de ejes (F1-25) y el lienzo WebGL2 (F1-23)
   * de cada panel usa este mismo valor para construir su `Vista`, en vez de
   * medir su propio contenedor.
   */
  anchoContenidoPx(): number {
    return this.#anchoContenidoPx;
  }

  /** Identificadores de panel, de arriba a abajo. */
  ordenPaneles(): readonly string[] {
    return [...this.#orden];
  }

  /**
   * Mueve `canalId` de donde esté a `panelDestino` (o lo reordena, si ya
   * estaba ahí), sin pasar por un arrastre de puntero. Reutiliza el mismo
   * camino que el arrastre (`#confirmarMovimiento`): es la costura para que
   * una futura acción de menú («mover al panel 2») no tenga que duplicar la
   * lógica de reasignación.
   */
  moverCanal(canalId: string, panelDestino: string, indice?: number): void {
    const panelOrigen = this.#orden.find((id) => indiceDeCanal(this.#asignaciones, id, canalId) !== -1);
    if (panelOrigen === undefined) {
      throw new Error(`el canal «${canalId}» no está asignado a ningún panel`);
    }
    this.#confirmarMovimiento(canalId, panelOrigen, panelDestino, indice);
  }

  /**
   * Vuelve a medir el contenedor y reescala alturas y ancho compartido.
   * Quien monta la aplicación la llama tras un `resize` de la ventana (este
   * componente no escucha `window` por su cuenta: no le pertenece decidir
   * cuándo el layout externo cambió, igual que `ajustarLienzo` en
   * `render/renderizador.ts` no se llama a sí mismo).
   */
  redimensionarContenedor(): void {
    this.#recalcularDesdeContenedor((ids, totalPx, minPx) => reescalarAlturas(this.#alturasPx, ids, totalPx, minPx));
  }

  /** Libera los elementos del DOM. No hay recursos de GPU ni temporizadores que limpiar aquí. */
  destruir(): void {
    for (const id of this.#orden) {
      this.#elementoPanel.get(id)?.remove();
    }
    this.#elementoPanel.clear();
    this.#elementoCabecera.clear();
    this.#elementoContenido.clear();
    this.#arrastreCanal = null;
    this.#arrastreDivisor = null;
  }

  // ------------------------------------------------------------------
  // Construcción del árbol DOM
  // ------------------------------------------------------------------

  #construirPaneles(): void {
    this.#orden.forEach((panelId, indice) => {
      const panel = this.#ctx.createElement("div");
      panel.classList.add(CLASE_PANEL);
      panel.setAttribute("data-panel-id", panelId);
      panel.style.setProperty("display", "flex");
      panel.style.setProperty("flex-direction", "column");
      panel.style.setProperty("overflow", "hidden");
      this.#contenedor.appendChild(panel);
      this.#elementoPanel.set(panelId, panel);

      const cabecera = this.#ctx.createElement("div");
      cabecera.classList.add(CLASE_CABECERA);
      cabecera.style.setProperty("display", "flex");
      cabecera.style.setProperty("flex", "0 0 auto");
      cabecera.style.setProperty("flex-wrap", "wrap");
      cabecera.style.setProperty("gap", "4px");
      panel.appendChild(cabecera);
      this.#elementoCabecera.set(panelId, cabecera);

      const contenido = this.#ctx.createElement("div");
      contenido.classList.add(CLASE_CONTENIDO);
      contenido.style.setProperty("flex", "1 1 auto");
      contenido.style.setProperty("min-height", "0");
      contenido.style.setProperty("overflow", "hidden");
      contenido.style.setProperty("position", "relative");
      panel.appendChild(contenido);
      this.#elementoContenido.set(panelId, contenido);

      this.#renderizarCabecera(panelId);

      const panelSiguiente = this.#orden[indice + 1];
      if (panelSiguiente !== undefined) {
        this.#crearDivisor(panelId, panelSiguiente);
      }
    });
  }

  #renderizarCabecera(panelId: string): void {
    const cabecera = this.#elementoCabecera.get(panelId);
    if (cabecera === undefined) return;
    cabecera.textContent = ""; // Igual que en el DOM real: vacía los hijos existentes.
    for (const canal of this.canalesDe(panelId)) {
      const chip = this.#ctx.createElement("div");
      chip.classList.add(CLASE_CHIP);
      chip.setAttribute("data-canal-id", canal.id);
      chip.textContent = canal.etiqueta;
      chip.style.setProperty("cursor", "grab");
      chip.style.setProperty("touch-action", "none"); // sin esto, el navegador puede robarse el gesto para hacer scroll táctil.
      this.#cablearArrastreCanal(chip, canal.id, panelId);
      cabecera.appendChild(chip);
    }
  }

  #crearDivisor(panelSuperior: string, panelInferior: string): void {
    const divisor = this.#ctx.createElement("div");
    divisor.classList.add(CLASE_DIVISOR);
    divisor.setAttribute("data-divisor-entre", `${panelSuperior}|${panelInferior}`);
    divisor.style.setProperty("flex", `0 0 ${ALTO_DIVISOR_PX}px`);
    divisor.style.setProperty("cursor", "row-resize");
    divisor.style.setProperty("touch-action", "none");
    this.#contenedor.appendChild(divisor);
    this.#cablearArrastreDivisor(divisor, panelSuperior, panelInferior);
  }

  // ------------------------------------------------------------------
  // Arrastre de canales entre paneles
  // ------------------------------------------------------------------

  #cablearArrastreCanal(chip: ElementoDOM, canalId: string, panelOrigen: string): void {
    chip.addEventListener("pointerdown", (evento: EventoPuntero) => {
      if (evento.button !== 0) return;
      evento.preventDefault();
      chip.setPointerCapture(evento.pointerId);
      chip.classList.add(CLASE_CHIP_ARRASTRANDO);
      this.#arrastreCanal = { canalId, panelOrigen, chip, destinoActual: null };
    });

    chip.addEventListener("pointermove", (evento: EventoPuntero) => {
      const arrastre = this.#arrastreCanal;
      if (arrastre === null || arrastre.chip !== chip) return;

      const rects: PanelRect[] = [];
      for (const id of this.#orden) {
        const elemento = this.#elementoPanel.get(id);
        if (elemento !== undefined) rects.push({ id, rect: elemento.getBoundingClientRect() });
      }
      const destino = panelEnY(rects, evento.clientY);
      if (destino === arrastre.destinoActual) return;

      if (arrastre.destinoActual !== null) {
        this.#elementoPanel.get(arrastre.destinoActual)?.classList.remove(CLASE_PANEL_DESTINO);
      }
      if (destino !== null) {
        this.#elementoPanel.get(destino)?.classList.add(CLASE_PANEL_DESTINO);
      }
      arrastre.destinoActual = destino;
    });

    const terminar = (evento: EventoPuntero, confirmar: boolean): void => {
      const arrastre = this.#arrastreCanal;
      if (arrastre === null || arrastre.chip !== chip) return;
      chip.releasePointerCapture(evento.pointerId);
      chip.classList.remove(CLASE_CHIP_ARRASTRANDO);
      if (arrastre.destinoActual !== null) {
        this.#elementoPanel.get(arrastre.destinoActual)?.classList.remove(CLASE_PANEL_DESTINO);
      }
      this.#arrastreCanal = null;
      if (confirmar && arrastre.destinoActual !== null) {
        this.#confirmarMovimiento(arrastre.canalId, arrastre.panelOrigen, arrastre.destinoActual);
      }
    };

    chip.addEventListener("pointerup", (evento: EventoPuntero) => terminar(evento, true));
    // `pointercancel` (el sistema interrumpe el gesto, p.ej. un aviso del SO en
    // tableta): se limpia el estado visual pero NO se confirma el movimiento —
    // un arrastre interrumpido a medias no es un "sí" del usuario.
    chip.addEventListener("pointercancel", (evento: EventoPuntero) => terminar(evento, false));
  }

  /** Aplica un cambio de asignación ya decidido (por arrastre o por `moverCanal`) y avisa. */
  #confirmarMovimiento(canalId: string, panelOrigen: string, panelDestino: string, indice?: number): void {
    this.#asignaciones = moverCanalPuro(this.#asignaciones, canalId, panelOrigen, panelDestino, indice);
    this.#renderizarCabecera(panelOrigen);
    if (panelDestino !== panelOrigen) this.#renderizarCabecera(panelDestino);
    const indiceFinal = indiceDeCanal(this.#asignaciones, panelDestino, canalId);
    this.#alCambiarAsignacion?.({ canalId, panelOrigen, panelDestino, indice: indiceFinal });
  }

  // ------------------------------------------------------------------
  // Redimensionado de paneles
  // ------------------------------------------------------------------

  #cablearArrastreDivisor(divisor: ElementoDOM, panelSuperior: string, panelInferior: string): void {
    divisor.addEventListener("pointerdown", (evento: EventoPuntero) => {
      if (evento.button !== 0) return;
      evento.preventDefault();
      divisor.setPointerCapture(evento.pointerId);
      this.#arrastreDivisor = {
        panelSuperior,
        panelInferior,
        clientYInicial: evento.clientY,
        alturaSuperiorInicial: this.#alturasPx.get(panelSuperior) ?? 0,
        alturaInferiorInicial: this.#alturasPx.get(panelInferior) ?? 0,
      };
    });

    divisor.addEventListener("pointermove", (evento: EventoPuntero) => {
      const arrastre = this.#arrastreDivisor;
      if (arrastre === null) return;
      const delta = evento.clientY - arrastre.clientYInicial;
      const resultado = arrastrarDivisor(
        arrastre.alturaSuperiorInicial,
        arrastre.alturaInferiorInicial,
        delta,
        this.#alturaMinimaPx,
      );
      this.#alturasPx.set(arrastre.panelSuperior, resultado.alturaSuperiorPx);
      this.#alturasPx.set(arrastre.panelInferior, resultado.alturaInferiorPx);
      this.#aplicarAlturas();
      this.#alRedimensionar?.(new Map(this.#alturasPx));
    });

    const terminar = (evento: EventoPuntero): void => {
      if (this.#arrastreDivisor === null) return;
      divisor.releasePointerCapture(evento.pointerId);
      this.#arrastreDivisor = null;
    };
    divisor.addEventListener("pointerup", terminar);
    divisor.addEventListener("pointercancel", terminar);
  }

  // ------------------------------------------------------------------
  // Medición del contenedor y aplicación de la geometría
  // ------------------------------------------------------------------

  /**
   * Mide el contenedor y aplica un nuevo reparto de alturas calculado por
   * `calculo` (que decide, según venga de la construcción inicial o de un
   * redimensionado del contenedor, si el reparto es igualitario o
   * proporcional a lo que ya había — ver `repartirAlturasIniciales` vs
   * `reescalarAlturas` en `reparto.ts`). El ancho compartido se recalcula
   * siempre de la misma forma: una única lectura del contenedor.
   */
  #recalcularDesdeContenedor(
    calculo: (ids: readonly string[], totalPx: number, minPx: number) => Map<string, number>,
  ): void {
    const rect = this.#contenedor.getBoundingClientRect();
    const alturaDivisores = Math.max(0, this.#orden.length - 1) * ALTO_DIVISOR_PX;
    const alturaDisponible = Math.max(0, rect.bottom - rect.top - alturaDivisores);

    this.#alturasPx = calculo(this.#orden, alturaDisponible, this.#alturaMinimaPx);
    this.#anchoContenidoPx = Math.max(0, rect.right - rect.left);

    this.#aplicarAlturas();
    this.#aplicarAnchoContenido();
    this.#alRedimensionar?.(new Map(this.#alturasPx));
  }

  #aplicarAlturas(): void {
    for (const id of this.#orden) {
      const panel = this.#elementoPanel.get(id);
      const alturaPx = this.#alturasPx.get(id);
      if (panel === undefined || alturaPx === undefined) continue;
      panel.style.setProperty("flex", `0 0 ${alturaPx}px`);
      panel.style.setProperty("height", `${alturaPx}px`);
    }
  }

  #aplicarAnchoContenido(): void {
    for (const id of this.#orden) {
      const contenido = this.#elementoContenido.get(id);
      if (contenido === undefined) continue;
      contenido.style.setProperty("width", `${this.#anchoContenidoPx}px`);
    }
  }
}

/** Suma de las alturas actuales; utilidad pequeña para quien quiera comprobar que cuadra con el contenedor. */
export function alturaTotalDe(paneles: PanelesApilados): number {
  return alturaTotal(paneles.alturasPx());
}

export type { CambioAsignacion, CanalEnPanel, DefinicionPanel, OpcionesPaneles } from "./tipos.ts";
