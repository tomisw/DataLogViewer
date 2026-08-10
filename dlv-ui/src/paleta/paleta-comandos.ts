/**
 * Paleta de comandos: se abre con teclado, filtra por texto difuso entre las
 * acciones registradas y ejecuta la elegida (F5-09).
 *
 * POR QUÉ EXISTE
 * ================
 * docs/02 §2.5, E9.3: «Paleta de comandos y búsqueda difusa de canales entre
 * 475 (sin ella, el selector es inservible)». Con 475 canales,
 * `selector-canales.ts` (F1-33) ya resuelve "encontrar un canal en la barra
 * lateral", pero eso exige tener la barra lateral visible y desplazarse hasta
 * ella. La paleta es la vía que funciona desde cualquier sitio de la ventana,
 * sin soltar el teclado, y por eso es un componente propio y no un modo del
 * selector: uno vive siempre en la barra lateral, el otro aparece encima de
 * todo y desaparece.
 *
 * DOM DIRECTO, SIN FRAMEWORK, IGUAL QUE `selector-canales.ts`
 * ===============================================================
 * Este módulo es la parte IMPURA: construye el diálogo, cablea teclado y
 * ratón, y pinta la lista. La parte que decide QUÉ acciones hay y en qué
 * orden —`RegistroComandos`, `filtrarComandos`— vive en `comandos.ts` y no
 * toca el DOM; por eso tiene pruebas de `vitest` y este fichero no las tiene,
 * exactamente el reparto que ya explica la cabecera de `selector-canales.ts`:
 * hace falta un navegador de verdad para decir algo útil sobre pintar un
 * `<li>` y moverle el foco.
 *
 * UN REGISTRO, NO UNA LISTA CABLEADA AQUÍ DENTRO
 * =================================================
 * Este componente no conoce ni un solo comando por su nombre: recibe
 * `obtenerComandos`, una función que llama cada vez que hace falta la lista
 * vigente (al abrir y en cada tecla). Quien construye la paleta (`Aplicacion`)
 * es quien registra qué puede hacer -- ver `comandos.ts` para el porqué del
 * registro por grupos. Añadir una acción nueva el día de mañana es registrar
 * un `Comando` más en `Aplicacion`, nunca tocar este fichero.
 *
 * ACCESIBILIDAD: EL PATRÓN "COMBOBOX CON LISTBOX EMERGENTE"
 * =============================================================
 * Es el mismo patrón ARIA que recomienda WAI-ARIA APG para un buscador con
 * sugerencias (y el que usan las paletas de comando de los editores de
 * código), no uno inventado aquí:
 * - El diálogo entero: `role="dialog"` + `aria-modal="true"` + `aria-label`
 *   propio, porque es una ventana flotante que sustituye temporalmente al
 *   resto de la interfaz (igual de espíritu que el `<select>` de
 *   `selector-tema.ts` es accesible por construcción, pero aquí no hay
 *   elemento nativo que sirva: no existe un `<dialog>` con lista de opciones
 *   integrada).
 * - La entrada de texto: `role="combobox"`, `aria-expanded="true"` mientras el
 *   diálogo está abierto (la lista emergente siempre está visible en esta
 *   paleta, nunca colapsada), `aria-controls` apuntando al `<ul>` y
 *   `aria-autocomplete="list"`.
 * - `aria-activedescendant` en la propia entrada, no `tabindex` en cada fila:
 *   el FOCO del teclado se queda siempre en la entrada de texto (por eso
 *   `Tab` no hace nada dentro del diálogo, ver `#onTeclaEntrada`) y es
 *   `aria-activedescendant` quien le dice al lector de pantalla cuál fila
 *   está "resaltada" sin moverlo de verdad. Mover el foco real a cada `<li>`
 *   obligaría a re-enfocar la entrada en cada tecla para seguir pudiendo
 *   escribir, y es exactamente el motivo por el que este patrón existe.
 * - La lista: `role="listbox"`; cada fila: `role="option"` + `aria-selected`.
 * - El aviso de "sin resultados": `role="status"` (equivale a
 *   `aria-live="polite"`), para que se anuncie solo, sin que quien usa lector
 *   de pantalla tenga que ir a buscarlo.
 *
 * LO QUE NO HACE
 * ================
 * No pone `aria-hidden` en el resto de la página ni usa `inert`: son APIs que
 * exigirían que este componente conociera y tocara el árbol de `Aplicacion`
 * por fuera de su propio DOM, algo que ningún otro componente de `dlv-ui`
 * hace (cada uno posee su propio fragmento, ver la cabecera de
 * `selector-canales.ts`). El diálogo sigue siendo utilizable con teclado y
 * lector de pantalla sin esto -- es la mitigación habitual en componentes que
 * no controlan el documento entero -- y queda anotado en el informe de la
 * tarea como la salvedad que es.
 */

import { filtrarComandos, type Comando, type ComandoFiltrado } from "./comandos.ts";

export interface OpcionesPaletaComandos {
  /** Dónde se cuelga el diálogo. Normalmente la raíz de `Aplicacion`. */
  readonly contenedor: HTMLElement;
  /**
   * Se llama al abrir y en cada tecla de la búsqueda: la paleta nunca guarda
   * su propia copia de "qué comandos hay", para no poder quedarse con una
   * lista vieja si `Aplicacion` registra un canal nuevo mientras la paleta
   * sigue en memoria (aunque cerrada).
   */
  readonly obtenerComandos: () => readonly Comando[];
  /** Superficie mínima de `Document`, inyectable por las pruebas de otros módulos que sí lo hacen (ver `selector-canales.ts`). */
  readonly documento?: Pick<Document, "createElement" | "createTextNode">;
}

const CLASE_RAIZ = "dlv-paleta";
const CLASE_ABIERTA = "dlv-paleta--abierta";
const ID_LISTA = "dlv-paleta-lista";

/**
 * Lo mínimo que hace falta del elemento que tenía el foco antes de abrir la
 * paleta, para poder devolvérselo al cerrar. No es `HTMLElement` completo a
 * propósito: cualquier cosa con `.focus()` vale, y así el tipo no arrastra
 * toda la superficie de `HTMLElement` a una sola llamada.
 */
interface ElementoEnfocable {
  focus(): void;
}

/** El elemento con el foco ahora mismo, o `null` si no hay ninguno que merezca recuperarse. */
function elementoConFocoActual(): ElementoEnfocable | null {
  if (typeof document === "undefined") return null;
  const activo = document.activeElement;
  // `document.body` (o `null`, sin nada enfocado) no es un sitio al que
  // "devolver" el foco: dejarlo tal cual es lo correcto, no un caso a tratar.
  if (activo === null || activo === document.body) return null;
  return activo as unknown as ElementoEnfocable;
}

/**
 * Diálogo modal de acciones con filtrado difuso.
 *
 * Se construye UNA vez (normalmente al montar `Aplicacion`) y queda colgado
 * del contenedor, oculto por CSS (`.dlv-paleta` sin `--abierta`) hasta que
 * `abrir()` lo muestra. No se reconstruye por log ni por cambio de tema: solo
 * el REGISTRO de comandos cambia con esas cosas, no la paleta.
 */
export class PaletaComandos {
  readonly #obtenerComandos: () => readonly Comando[];
  readonly #documento: Pick<Document, "createElement" | "createTextNode">;

  readonly #overlay: HTMLElement;
  readonly #entrada: HTMLInputElement;
  readonly #lista: HTMLElement;
  readonly #vacio: HTMLElement;

  #visibles: ComandoFiltrado[] = [];
  /** Las filas pintadas para `#visibles`, en el mismo orden. Se guardan al construirlas para no tener que volver a recorrer el DOM al mover la selección. */
  #filas: HTMLLIElement[] = [];
  #indiceActivo = 0;
  #abierta = false;
  #elementoAnterior: ElementoEnfocable | null = null;

  constructor(opciones: OpcionesPaletaComandos) {
    this.#obtenerComandos = opciones.obtenerComandos;
    this.#documento = opciones.documento ?? globalThis.document;

    this.#overlay = this.#documento.createElement("div");
    this.#overlay.className = CLASE_RAIZ;
    // Clic fuera de la caja = cerrar, igual que la mayoría de diálogos
    // modales. Comprobar `evento.target === overlay` (y no "cualquier clic
    // dentro de la paleta") es lo que evita que un clic en una fila la cierre
    // antes de que el manejador de esa fila llegue a ejecutar el comando.
    this.#overlay.addEventListener("mousedown", (evento) => {
      if (evento.target === this.#overlay) this.cerrar();
    });

    const caja = this.#documento.createElement("div");
    caja.className = `${CLASE_RAIZ}__caja`;
    caja.setAttribute("role", "dialog");
    caja.setAttribute("aria-modal", "true");
    caja.setAttribute("aria-label", "Paleta de comandos");

    this.#entrada = this.#documento.createElement("input");
    this.#entrada.type = "text";
    this.#entrada.placeholder = "Escribe una acción o el nombre de un canal…";
    this.#entrada.className = `${CLASE_RAIZ}__entrada`;
    this.#entrada.setAttribute("role", "combobox");
    this.#entrada.setAttribute("aria-expanded", "true");
    this.#entrada.setAttribute("aria-controls", ID_LISTA);
    this.#entrada.setAttribute("aria-autocomplete", "list");
    this.#entrada.setAttribute("aria-label", "Buscar un comando");
    this.#entrada.addEventListener("input", () => {
      this.#indiceActivo = 0;
      this.#filtrarYRenderizar();
    });
    this.#entrada.addEventListener("keydown", (evento) => this.#onTeclaEntrada(evento));

    this.#lista = this.#documento.createElement("ul");
    this.#lista.id = ID_LISTA;
    this.#lista.className = `${CLASE_RAIZ}__lista`;
    this.#lista.setAttribute("role", "listbox");
    this.#lista.setAttribute("aria-label", "Comandos disponibles");

    this.#vacio = this.#documento.createElement("p");
    this.#vacio.className = `${CLASE_RAIZ}__vacio`;
    this.#vacio.setAttribute("role", "status");
    this.#vacio.textContent = "Sin resultados";

    caja.append(this.#entrada, this.#lista, this.#vacio);
    this.#overlay.append(caja);
    opciones.contenedor.append(this.#overlay);
  }

  estaAbierta(): boolean {
    return this.#abierta;
  }

  /** Abre el diálogo, recuerda qué tenía el foco y deja la búsqueda en blanco. */
  abrir(): void {
    if (this.#abierta) return;
    this.#abierta = true;
    this.#elementoAnterior = elementoConFocoActual();
    this.#overlay.classList.add(CLASE_ABIERTA);
    this.#entrada.value = "";
    this.#indiceActivo = 0;
    this.#filtrarYRenderizar();
    this.#entrada.focus();
  }

  /** Cierra el diálogo y devuelve el foco a donde estaba antes de `abrir()`. */
  cerrar(): void {
    if (!this.#abierta) return;
    this.#abierta = false;
    this.#overlay.classList.remove(CLASE_ABIERTA);
    this.#elementoAnterior?.focus();
    this.#elementoAnterior = null;
  }

  /**
   * Atajo global para abrir/cerrar: Ctrl+K (Windows/Linux) o ⌘K (macOS).
   *
   * Se ofrece como método y no como oyente propio porque el atajo tiene que
   * funcionar viniendo de CUALQUIER punto de la ventana, incluso con el foco
   * fuera de este componente (p. ej. dentro de un `<input>` del selector de
   * canales) -- y ese `keydown` global es responsabilidad de quien monta la
   * ventana entera (`Aplicacion`, sobre `entorno.ventana.addEventListener`),
   * no de este diálogo, que solo existe cuando está abierto.
   *
   * Alterna: si está cerrada la abre, si está abierta la cierra. `Escape`
   * (`#onTeclaEntrada`) es el cierre "de verdad" cuando ya se está dentro; este
   * atajo es además el interruptor desde fuera.
   */
  manejarAtajoGlobal(evento: KeyboardEvent): void {
    const esK = evento.key === "k" || evento.key === "K";
    const esAtajo = esK && (evento.ctrlKey || evento.metaKey) && !evento.altKey;
    if (!esAtajo) return;
    // Sin esto, Ctrl+K se va al cuadro de direcciones en Firefox/Chrome, que
    // es justo la tecla que se le está quitando al navegador para dársela a
    // la paleta.
    evento.preventDefault();
    if (this.#abierta) this.cerrar();
    else this.abrir();
  }

  /** Quita el diálogo del DOM. No se puede seguir usando la instancia tras esto. */
  destruir(): void {
    this.#overlay.remove();
  }

  /**
   * Teclado DENTRO de la entrada de texto, mientras el diálogo está abierto.
   *
   * `Tab` se traga a propósito (`preventDefault`, sin hacer nada más): la
   * única cosa focable de este diálogo es la propia entrada (las filas se
   * seleccionan por `aria-activedescendant`, no por foco real -- ver la
   * cabecera), así que sin esto `Tab` sacaría el foco del diálogo hacia lo
   * que sea que hubiera detrás en el documento, que sigue en el árbol aunque
   * esté visualmente debajo. Es la manera barata de no dejar salir el foco de
   * un diálogo modal sin tener que hacer un `inert` del resto de la página
   * (ver "LO QUE NO HACE" en la cabecera del fichero).
   */
  #onTeclaEntrada(evento: KeyboardEvent): void {
    switch (evento.key) {
      case "Escape":
        evento.preventDefault();
        this.cerrar();
        return;
      case "Tab":
        evento.preventDefault();
        return;
      case "ArrowDown":
        evento.preventDefault();
        this.#moverSeleccion(1);
        return;
      case "ArrowUp":
        evento.preventDefault();
        this.#moverSeleccion(-1);
        return;
      case "Enter":
        evento.preventDefault();
        this.#ejecutarActiva();
        return;
      default:
        return;
    }
  }

  /**
   * Sube o baja la fila resaltada, dando la vuelta en los extremos.
   *
   * Da la vuelta (de la última a la primera y viceversa) porque es lo que ya
   * hacen las paletas de comando de referencia (VS Code, Sublime): con una
   * lista larga y filtrada, negarse a "dar la vuelta" no protege de nada --
   * quien llega al final y sigue pulsando abajo sabe perfectamente que quiere
   * volver arriba -- y solo obliga a una pulsada de más en la dirección
   * contraria.
   */
  #moverSeleccion(delta: 1 | -1): void {
    const n = this.#visibles.length;
    if (n === 0) return;
    this.#indiceActivo = (this.#indiceActivo + delta + n) % n;
    this.#actualizarSeleccionVisual();
  }

  /** Cierra (con su devolución de foco) y LUEGO ejecuta: la acción no tiene que pelear con un diálogo que sigue en pantalla. */
  #ejecutarActiva(): void {
    const activa = this.#visibles[this.#indiceActivo];
    if (activa === undefined) return;
    this.cerrar();
    activa.comando.ejecutar();
  }

  #filtrarYRenderizar(): void {
    this.#visibles = filtrarComandos(this.#obtenerComandos(), this.#entrada.value);
    if (this.#indiceActivo >= this.#visibles.length) this.#indiceActivo = 0;
    this.#renderizarLista();
  }

  #renderizarLista(): void {
    this.#filas = this.#visibles.map((cf, indice) => this.#filaComando(cf, indice));
    this.#lista.replaceChildren(...this.#filas);
    const hayResultados = this.#visibles.length > 0;
    this.#lista.style.setProperty("display", hayResultados ? "" : "none");
    this.#vacio.style.setProperty("display", hayResultados ? "none" : "");
    this.#actualizarSeleccionVisual();
  }

  /** Repinta qué fila está marcada como activa sin reconstruir la lista entera. */
  #actualizarSeleccionVisual(): void {
    this.#filas.forEach((fila, indice) => {
      const activa = indice === this.#indiceActivo;
      fila.classList.toggle(`${CLASE_RAIZ}__fila--activa`, activa);
      fila.setAttribute("aria-selected", activa ? "true" : "false");
    });
    const activa = this.#visibles[this.#indiceActivo];
    this.#entrada.setAttribute(
      "aria-activedescendant",
      activa === undefined ? "" : `${ID_LISTA}-${this.#indiceActivo}`,
    );
  }

  #filaComando(cf: ComandoFiltrado, indice: number): HTMLLIElement {
    const fila = this.#documento.createElement("li");
    fila.id = `${ID_LISTA}-${indice}`;
    fila.className = `${CLASE_RAIZ}__fila`;
    fila.setAttribute("role", "option");
    fila.setAttribute("aria-selected", "false");

    const etiqueta = this.#documento.createElement("span");
    etiqueta.className = `${CLASE_RAIZ}__etiqueta`;
    etiqueta.textContent = cf.comando.etiqueta;
    fila.append(etiqueta);

    if (cf.comando.categoria !== undefined) {
      const categoria = this.#documento.createElement("span");
      categoria.className = `${CLASE_RAIZ}__categoria`;
      categoria.textContent = cf.comando.categoria;
      fila.append(categoria);
    }

    // `mousedown` y no `click`: dispara antes de cualquier `blur` de la
    // entrada, así que el foco no llega a saltar a ningún sitio raro entre el
    // clic y `#ejecutarActiva()` moviéndolo de vuelta con `cerrar()`.
    fila.addEventListener("mousedown", (evento) => {
      evento.preventDefault();
      this.#indiceActivo = indice;
      this.#ejecutarActiva();
    });

    return fila;
  }
}
