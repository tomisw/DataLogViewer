/**
 * Un doble de `Document` y de `HTMLElement`, suficiente para montar la
 * aplicación entera en Node.
 *
 * EL HUECO QUE ESTO CIERRA
 * ========================
 * `vitest.config.ts` corre con `environment: "node"` y este paquete no tiene
 * dependencias, así que no hay `document` global. La consecuencia no era
 * teórica: **todo el código de montaje de la interfaz —crear elementos,
 * engancharlos al árbol, resolver la unidad activa de un canal— no se
 * ejecutaba en ninguna prueba.** Tres fallos reales salieron de ahí y los
 * encontró el propietario abriendo la ventana, no la suite:
 *
 * 1. Un factor de diez en la temperatura, por no aplicar el escalado del canal.
 * 2. La etiqueta de la unidad congelada al crear el panel: «92,05» con una «K»
 *    al lado después de conmutar a °C.
 * 3. Un único formateador para toda la tabla del cursor, atado al primer canal
 *    del panel.
 *
 * Ninguno lo ve `tsc` (son valores leídos demasiado pronto, no tipos mal) ni
 * `pytest` (se detiene en el backend).
 *
 * POR QUÉ ESTO Y NO jsdom
 * =======================
 * jsdom parece la respuesta obvia y no lo es: **no implementa WebGL**, ni
 * WebGL2. `Renderizador.desdeLienzo` fallaría igual bajo jsdom, así que haría
 * falta de todas formas el doble de contexto GL que ya existe
 * (`render/doble-gl.ts`). Sería una dependencia nueva —que en este proyecto no
 * se añade sin preguntar— que no resuelve el problema por el que se añadiría.
 *
 * Este fichero, en cambio, es la continuación del patrón que el resto de
 * `dlv-ui` ya usa: `render/doble-gl.ts`, `paneles/doble-dom.ts`,
 * `unidades/dom-falso.ts`, `cursor/doble-dom.ts` y `combustible/dom-falso.ts`.
 * La diferencia es el alcance: esos cubren un componente cada uno, y este cubre
 * el ensamblado, que es donde estaban los fallos.
 *
 * QUÉ IMPLEMENTA, Y POR QUÉ SOLO ESO
 * ==================================
 * Exactamente la superficie que la aplicación usa, medida sobre el código y no
 * adivinada: `style`, `appendChild`, `textContent`, `className`, `id`,
 * `addEventListener`, `classList`, `append`, `setAttribute`, `value`, `title`,
 * `remove`, `type`, `getBoundingClientRect`, `checked`, `replaceChildren`,
 * `firstChild`, `dataset`, `width`/`height` y `getContext`. No hay
 * `querySelector` porque la aplicación no lo usa (`main.ts` sí, para encontrar
 * `#app`, y eso queda fuera de `Aplicacion`).
 *
 * Un doble que implementara «el DOM» sería una reimplementación del navegador
 * sin pruebas propias; uno que implementa lo que se usa falla en cuanto alguien
 * usa algo nuevo, que es justo el aviso que hace falta.
 *
 * Vive en `src/` y no en un directorio de pruebas porque `tsconfig.json` solo
 * incluye `src` — misma nota que en `doble-gl.ts` y `paneles/doble-dom.ts`.
 */

import { crearDobleGL, type DobleGL } from "../render/doble-gl.ts";

export interface RectanguloPx {
  readonly top: number;
  readonly bottom: number;
  readonly left: number;
  readonly right: number;
  readonly width: number;
  readonly height: number;
}

/** Un elemento falso, con lo que además hace falta para inspeccionarlo en una prueba. */
export interface ElementoFalso {
  readonly etiqueta: string;
  className: string;
  id: string;
  title: string;
  type: string;
  value: string;
  checked: boolean;
  disabled: boolean;
  selected: boolean;
  width: number;
  height: number;
  /**
   * `style` con las dos formas que usa la aplicación: propiedades por nombre
   * (`style.width = "10px"`) y `setProperty`/`removeProperty`, que es la vía por
   * la que se enseña y se esconde el mensaje de «selecciona canales».
   */
  readonly style: Record<string, string> & {
    setProperty(nombre: string, valor: string): void;
    removeProperty(nombre: string): void;
    getPropertyValue(nombre: string): string;
  };
  readonly dataset: Record<string, string>;
  readonly classList: {
    add(...clases: string[]): void;
    remove(...clases: string[]): void;
    contains(clase: string): boolean;
    toggle(clase: string, fuerza?: boolean): void;
  };
  textContent: string;
  readonly hijos: readonly ElementoFalso[];
  readonly firstChild: ElementoFalso | null;
  readonly atributos: ReadonlyMap<string, string>;
  /** El documento que lo creo. `ejes.ts` lo usa para crear nodos SVG hermanos. */
  ownerDocument: DocumentoFalso | null;

  append(...nodos: ElementoFalso[]): void;
  appendChild(nodo: ElementoFalso): ElementoFalso;
  removeChild(nodo: ElementoFalso): ElementoFalso;
  replaceChildren(...nodos: ElementoFalso[]): void;
  remove(): void;
  setAttribute(nombre: string, valor: string): void;
  getAttribute(nombre: string): string | null;
  addEventListener(tipo: string, manejador: (evento: unknown) => void): void;
  removeEventListener(tipo: string, manejador: (evento: unknown) => void): void;
  getBoundingClientRect(): RectanguloPx;
  getContext(tipo: string): DobleGL | null;

  // ---- Utilidades solo para las pruebas ---- //
  /** Node no puede calcular layout: la prueba dice qué geometría tiene. */
  fijarRectangulo(rectangulo: RectanguloPx): void;
  /** Dispara un evento en ESTE elemento (no burbujea: nadie lo necesita todavía). */
  disparar(tipo: string, evento?: unknown): void;
  /** Todo el texto del subárbol, para comprobar qué se ve sin recorrerlo a mano. */
  textoDelArbol(): string;
  /** Primer descendiente (o él mismo) con esa clase. Solo para aserciones. */
  buscarPorClase(clase: string): ElementoFalso | null;
  /** Todos los descendientes con esa clase, en orden de documento. */
  buscarTodosPorClase(clase: string): ElementoFalso[];
  /** Primer descendiente con esa etiqueta. Solo para aserciones. */
  buscarPorEtiqueta(etiqueta: string): ElementoFalso | null;
}

const RECTANGULO_VACIO: RectanguloPx = {
  top: 0,
  bottom: 0,
  left: 0,
  right: 0,
  width: 0,
  height: 0,
};

export function crearElementoFalso(etiqueta: string): ElementoFalso {
  const clases = new Set<string>();
  const hijos: ElementoFalso[] = [];
  const atributos = new Map<string, string>();
  const manejadores = new Map<string, Array<(evento: unknown) => void>>();
  let texto = "";
  let rectangulo = RECTANGULO_VACIO;
  let gl: DobleGL | null = null;
  const estilo: Record<string, string> = {};
  const style = Object.assign(estilo, {
    setProperty: (nombre: string, valor: string): void => {
      estilo[nombre] = valor;
    },
    removeProperty: (nombre: string): void => {
      delete estilo[nombre];
    },
    getPropertyValue: (nombre: string): string => estilo[nombre] ?? "",
  });
  let padre: ElementoFalso | null = null;

  const enlazar = (nodo: ElementoFalso): void => {
    // `appendChild` mueve el nodo si ya tenía padre, igual que el DOM real. Sin
    // esto, un elemento reinsertado aparecería en dos sitios y una prueba de
    // reconstrucción de paneles contaría el doble.
    const interno = nodo as ElementoInterno;
    interno.__padre?.quitarSinDesenlazar(nodo);
    interno.__padre = elemento as ElementoInterno;
    hijos.push(nodo);
  };

  interface ElementoInterno extends ElementoFalso {
    __padre: ElementoInterno | null;
    quitarSinDesenlazar(nodo: ElementoFalso): void;
  }

  const elemento: ElementoInterno = {
    etiqueta,
    className: "",
    id: "",
    title: "",
    type: "",
    value: "",
    checked: false,
    disabled: false,
    selected: false,
    width: 0,
    height: 0,
    style,
    dataset: {},
    classList: {
      add: (...nuevas) => nuevas.forEach((c) => clases.add(c)),
      remove: (...quitadas) => quitadas.forEach((c) => clases.delete(c)),
      contains: (c) => clases.has(c),
      toggle: (c, fuerza) => {
        const poner = fuerza ?? !clases.has(c);
        if (poner) clases.add(c);
        else clases.delete(c);
      },
    },
    get textContent(): string {
      // Semántica del DOM real: el texto de TODO el subárbol, no solo el
      // propio. El doble de `incidencias/` tenía esto como campo plano y por
      // eso `panel-incidencias.test.ts` llevaba dos pruebas en rojo desde que
      // se escribió: una fila construida con `<span>` dentro no tiene texto
      // propio, así que `fila.textContent` devolvía cadena vacía y una prueba
      // correcta parecía equivocada. Este doble tenía el mismo defecto sin que
      // hubiera mordido todavía, porque sus pruebas usan `textoDelArbol()`.
      return texto + hijos.map((h) => h.textContent).join("");
    },
    set textContent(valor: string) {
      // En el DOM real, asignar `textContent` BORRA los hijos. Es la vía que
      // usa la aplicación para vaciar un contenedor (`contenedor.textContent =
      // ""`), así que un doble que no lo hiciera dejaría el árbol creciendo y
      // las aserciones sobre "cuántos paneles hay" saldrían mal.
      hijos.length = 0;
      texto = valor;
    },
    get hijos(): readonly ElementoFalso[] {
      return hijos;
    },
    get firstChild(): ElementoFalso | null {
      return hijos[0] ?? null;
    },
    get atributos(): ReadonlyMap<string, string> {
      return atributos;
    },
    __padre: null,
    ownerDocument: null,

    append: (...nodos) => nodos.forEach(enlazar),
    appendChild: (nodo) => {
      enlazar(nodo);
      return nodo;
    },
    removeChild: (nodo) => {
      elemento.quitarSinDesenlazar(nodo);
      (nodo as ElementoInterno).__padre = null;
      return nodo;
    },
    quitarSinDesenlazar: (nodo) => {
      const i = hijos.indexOf(nodo);
      if (i >= 0) hijos.splice(i, 1);
    },
    replaceChildren: (...nodos) => {
      for (const h of [...hijos]) (h as ElementoInterno).__padre = null;
      hijos.length = 0;
      texto = "";
      nodos.forEach(enlazar);
    },
    remove: () => {
      padre = (elemento as ElementoInterno).__padre;
      padre?.removeChild(elemento);
    },
    setAttribute: (nombre, valor) => atributos.set(nombre, valor),
    getAttribute: (nombre) => atributos.get(nombre) ?? null,
    addEventListener: (tipo, manejador) => {
      const lista = manejadores.get(tipo) ?? [];
      lista.push(manejador);
      manejadores.set(tipo, lista);
    },
    removeEventListener: (tipo, manejador) => {
      const lista = manejadores.get(tipo);
      if (lista === undefined) return;
      const i = lista.indexOf(manejador);
      if (i >= 0) lista.splice(i, 1);
    },
    getBoundingClientRect: () => rectangulo,
    getContext: (tipo) => {
      if (tipo !== "webgl2") return null;
      gl ??= crearDobleGL();
      return gl;
    },

    fijarRectangulo: (r) => {
      rectangulo = r;
    },
    disparar: (tipo, evento) => {
      for (const m of manejadores.get(tipo) ?? []) m(evento ?? {});
    },
    textoDelArbol: () => {
      const partes = [texto];
      for (const h of hijos) partes.push(h.textoDelArbol());
      return partes.filter((p) => p !== "").join(" ");
    },
    buscarPorClase: (clase) => elemento.buscarTodosPorClase(clase)[0] ?? null,
    buscarTodosPorClase: (clase) => {
      const encontrados: ElementoFalso[] = [];
      const visitar = (n: ElementoFalso): void => {
        const suyas = n.className.split(/\s+/);
        if (suyas.includes(clase) || n.classList.contains(clase)) encontrados.push(n);
        for (const h of n.hijos) visitar(h);
      };
      for (const h of hijos) visitar(h);
      return encontrados;
    },
    buscarPorEtiqueta: (etiquetaBuscada) => {
      const visitar = (n: ElementoFalso): ElementoFalso | null => {
        if (n.etiqueta === etiquetaBuscada) return n;
        for (const h of n.hijos) {
          const r = visitar(h);
          if (r !== null) return r;
        }
        return null;
      };
      for (const h of hijos) {
        const r = visitar(h);
        if (r !== null) return r;
      }
      return null;
    },
  };
  return elemento;
}

/** Lo que hace falta de `Document`. */
export interface DocumentoFalso {
  createElement(etiqueta: string): ElementoFalso;
  createElementNS(ns: string, etiqueta: string): ElementoFalso;
  /**
   * Un nodo de texto. Se modela como un elemento con la etiqueta `#text`, que
   * es lo que hace falta para que `textoDelArbol` lo recoja: `SelectorCanales`
   * mete asi el rotulo «mostrar inactivos» dentro de su `<label>`.
   */
  createTextNode(texto: string): ElementoFalso;
  /** Todos los elementos creados, en orden. Útil para depurar una prueba. */
  readonly creados: readonly ElementoFalso[];
}

export function crearDocumentoFalso(): DocumentoFalso {
  const creados: ElementoFalso[] = [];
  const crear = (etiqueta: string): ElementoFalso => {
    const e = crearElementoFalso(etiqueta);
    e.ownerDocument = documento;
    creados.push(e);
    return e;
  };
  const documento: DocumentoFalso = {
    createElement: crear,
    createElementNS: (_ns, etiqueta) => crear(etiqueta),
    createTextNode: (texto) => {
      const n = crear("#text");
      n.textContent = texto;
      return n;
    },
    get creados(): readonly ElementoFalso[] {
      return creados;
    },
  };
  return documento;
}

/** Lo que hace falta de `window`, con el bucle de fotogramas bajo control. */
export interface VentanaFalsa {
  devicePixelRatio: number;
  addEventListener(tipo: string, manejador: (evento: unknown) => void): void;
  requestAnimationFrame(callback: () => void): number;
  cancelAnimationFrame(id: number): void;
  /**
   * Ejecuta los fotogramas pendientes, UNA vez cada uno.
   *
   * El bucle del cursor se reprograma solo (`requestAnimationFrame` dentro del
   * propio callback), así que un doble que ejecutara la cola hasta vaciarla no
   * terminaría nunca. La prueba decide cuántos fotogramas pasan.
   */
  correrFotogramas(cuantos?: number): void;
  disparar(tipo: string, evento?: unknown): void;
}

export function crearVentanaFalsa(): VentanaFalsa {
  const manejadores = new Map<string, Array<(evento: unknown) => void>>();
  let pendientes: Array<() => void> = [];
  let siguienteId = 1;
  const cancelados = new Set<number>();
  const ids = new Map<() => void, number>();

  return {
    devicePixelRatio: 1,
    addEventListener: (tipo, manejador) => {
      const lista = manejadores.get(tipo) ?? [];
      lista.push(manejador);
      manejadores.set(tipo, lista);
    },
    requestAnimationFrame: (callback) => {
      const id = siguienteId++;
      ids.set(callback, id);
      pendientes.push(callback);
      return id;
    },
    cancelAnimationFrame: (id) => {
      cancelados.add(id);
    },
    correrFotogramas: (cuantos = 1) => {
      for (let i = 0; i < cuantos; i += 1) {
        const cola = pendientes;
        pendientes = [];
        for (const cb of cola) {
          const id = ids.get(cb);
          if (id !== undefined && cancelados.has(id)) continue;
          cb();
        }
      }
    },
    disparar: (tipo, evento) => {
      for (const m of manejadores.get(tipo) ?? []) m(evento ?? {});
    },
  };
}
