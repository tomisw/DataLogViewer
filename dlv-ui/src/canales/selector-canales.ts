/**
 * Selector de canales con búsqueda difusa y ocultación de inactivos (F1-33).
 *
 * DOM directo, sin framework (regla del propio proyecto, ADR-006 para el
 * lienzo se extiende aquí por la misma razón: nada de dependencias nuevas
 * para pintar una lista). Esta clase posee un fragmento del árbol del
 * documento y lo mantiene sincronizado a mano.
 *
 * LA MISMA PARTICIÓN QUE `render/escala.ts` FRENTE A `render/renderizador.ts`
 * =============================================================================
 * QUÉ se ve -- filtrado, puntuación difusa, motivo de ocultación -- vive en
 * `filtro.ts` y `difuso.ts`, que no tocan el DOM y por eso son los ficheros
 * con pruebas (`vitest.config.ts` usa `environment: "node"`: no hay
 * `document` en las pruebas, igual que no hay WebGL2). Este módulo es la
 * parte impura que coge ese resultado ya calculado y lo pinta; no se prueba
 * con vitest por el mismo motivo que `main.ts` no lo tiene: hace falta un
 * navegador de verdad para decir algo útil sobre él.
 *
 * LO QUE ESTE COMPONENTE NO HACE
 * ===============================
 * No dibuja series, no conoce la pirámide ni `dlv_core.almacen`: recibe una
 * lista de `CanalInfo` ya resuelta -- quien la construye es quien sabe
 * traducir `IndiceCanal`/`ChannelKey` del backend a estos campos (`tipos.ts`)
 * -- y solo emite QUÉ canales están seleccionados. Pintar la serie o no es
 * decisión de quien escucha `onSeleccionCambia`.
 */

import { filtrarCanales } from "./filtro.ts";
import type { CanalFiltrado, ResumenOcultos } from "./filtro.ts";
import type { CanalInfo, MotivoOculto } from "./tipos.ts";

export interface OpcionesSelectorCanales {
  readonly contenedor: HTMLElement;
  readonly canales: readonly CanalInfo[];
  /**
   * Se llama tras cada cambio de selección (marcar o desmarcar una fila) con
   * el conjunto COMPLETO ya actualizado, no solo el canal que cambió: así
   * quien escucha no tiene que llevar su propio acumulado ni puede
   * desincronizarse de él.
   */
  readonly onSeleccionCambia: (seleccionados: ReadonlySet<string>) => void;
  /**
   * Superficie minima de `Document`. Por omision el global, igual que en el
   * resto de componentes (`unidades/dom.ts`, `cursor/contexto-dom.ts`).
   *
   * Existe para que `Aplicacion` pueda montarse en una prueba: sin ella este
   * constructor tocaba `document` directamente y el ensamblado entero no se
   * podia construir en Node (`vitest.config.ts`, `environment: "node"`).
   */
  readonly documento?: Pick<Document, "createElement" | "createTextNode">;
}

const ETIQUETA_MOTIVO: Record<MotivoOculto, string> = {
  constante: "constante: no cambia en todo el log",
  vacio: "vacío: el canal no se activó en este log",
};

/**
 * El texto que explica por qué un canal está marcado como inactivo. Pura y
 * sin DOM -- por eso se prueba, aunque solo la use este módulo -- para que
 * "oculto porque está constante" (la frase que pide F1-33) no quede
 * enterrada dentro de una función que no se puede invocar sin navegador.
 */
export function textoMotivo(motivo: MotivoOculto | null): string {
  return motivo === null ? "" : ETIQUETA_MOTIVO[motivo];
}

/** El texto del resumen de ocultos, o cadena vacía si no hay nada que decir. */
export function textoResumenOcultos(ocultos: ResumenOcultos, mostrarInactivos: boolean): string {
  const total = ocultos.constante + ocultos.vacio;
  if (mostrarInactivos || total === 0) return "";
  const partes: string[] = [];
  if (ocultos.constante > 0) partes.push(`${ocultos.constante} constante(s)`);
  if (ocultos.vacio > 0) partes.push(`${ocultos.vacio} vacío(s)`);
  return `${total} canal(es) oculto(s): ${partes.join(", ")}. Actívalo con «mostrar inactivos».`;
}

export class SelectorCanales {
  readonly #contenedor: HTMLElement;
  readonly #onSeleccionCambia: (seleccionados: ReadonlySet<string>) => void;
  readonly #documento: Pick<Document, "createElement" | "createTextNode">;
  readonly #seleccionados = new Set<string>();

  readonly #entradaBusqueda: HTMLInputElement;
  readonly #casillaInactivos: HTMLInputElement;
  readonly #resumen: HTMLElement;
  readonly #lista: HTMLElement;

  #canales: readonly CanalInfo[];
  #consulta = "";
  #mostrarInactivos = false;

  constructor(opciones: OpcionesSelectorCanales) {
    this.#contenedor = opciones.contenedor;
    this.#canales = opciones.canales;
    this.#onSeleccionCambia = opciones.onSeleccionCambia;
    this.#documento = opciones.documento ?? globalThis.document;

    const raiz = this.#documento.createElement("div");
    raiz.className = "selector-canales";

    this.#entradaBusqueda = this.#documento.createElement("input");
    this.#entradaBusqueda.type = "text";
    this.#entradaBusqueda.placeholder = "Buscar por nombre, rol semántico o ID…";
    this.#entradaBusqueda.className = "selector-canales__busqueda";
    this.#entradaBusqueda.addEventListener("input", () => {
      this.#consulta = this.#entradaBusqueda.value;
      this.#renderizarLista();
    });

    const etiquetaCasilla = this.#documento.createElement("label");
    etiquetaCasilla.className = "selector-canales__toggle";
    this.#casillaInactivos = this.#documento.createElement("input");
    this.#casillaInactivos.type = "checkbox";
    this.#casillaInactivos.addEventListener("change", () => {
      this.#mostrarInactivos = this.#casillaInactivos.checked;
      this.#renderizarLista();
    });
    etiquetaCasilla.append(this.#casillaInactivos, this.#documento.createTextNode(" mostrar inactivos"));

    this.#resumen = this.#documento.createElement("p");
    this.#resumen.className = "selector-canales__resumen";

    this.#lista = this.#documento.createElement("ul");
    this.#lista.className = "selector-canales__lista";

    raiz.append(this.#entradaBusqueda, etiquetaCasilla, this.#resumen, this.#lista);
    this.#contenedor.append(raiz);

    this.#renderizarLista();
  }

  get seleccionados(): ReadonlySet<string> {
    return this.#seleccionados;
  }

  /**
   * Sustituye la lista de canales (log nuevo, o el mismo recargado).
   *
   * La selección se conserva solo para los `idNativo` que sigan existiendo:
   * un canal seleccionado que desaparece de la lista nueva no puede quedarse
   * "seleccionado" sin que nadie pueda verlo ni desmarcarlo, y el callback se
   * vuelve a llamar si la selección efectiva cambió por esto.
   */
  actualizarCanales(canales: readonly CanalInfo[]): void {
    this.#canales = canales;
    const idsVigentes = new Set(canales.map((c) => c.idNativo));
    let cambio = false;
    for (const id of [...this.#seleccionados]) {
      if (!idsVigentes.has(id)) {
        this.#seleccionados.delete(id);
        cambio = true;
      }
    }
    this.#renderizarLista();
    if (cambio) this.#onSeleccionCambia(new Set(this.#seleccionados));
  }

  /**
   * Fija la selección por programa, en una sola operación.
   *
   * POR QUÉ ESTO EXISTE
   * ===================
   * Al abrir un log hay que dejar marcados unos pocos canales: una ventana con
   * 475 casillas y ninguna marcada no enseña nada. Sin este método, la única
   * vía era simular clics sobre las casillas del DOM, y eso trae dos problemas
   * que no son de estilo:
   *
   * - Encontrar la casilla de un canal concreto exigía asumir su POSICIÓN en
   *   la lista, porque las filas no llevan el `idNativo` en ningún atributo.
   *   Esa posición depende del filtro de búsqueda y de «mostrar inactivos», y
   *   basta con que uno de los dos esté activo para marcar otros canales.
   * - Cada clic emitía `onSeleccionCambia`, y quien escucha reconstruye los
   *   paneles: ocho clics eran ocho reconstrucciones de tamaño creciente, cada
   *   una creando un `WebGL2RenderingContext` por panel. Un navegador solo
   *   garantiza un puñado de contextos vivos (Chrome/Edge: 16) y empezaba a
   *   descartar los antiguos («Too many active WebGL contexts»).
   *
   * Aquí la selección se fija de una vez y el callback se emite UNA vez, y
   * solo si algo cambió de verdad.
   *
   * Los ids que no existan en la lista actual se ignoran en silencio: quien
   * llama propone canales por rol semántico (`rol`), y que un log no tenga
   * sensor de presión de aceite es lo normal, no un error que deba propagarse.
   */
  preseleccionar(ids: Iterable<string>): void {
    const vigentes = new Set(this.#canales.map((c) => c.idNativo));
    const nueva = new Set([...ids].filter((id) => vigentes.has(id)));
    const igual =
      nueva.size === this.#seleccionados.size && [...nueva].every((id) => this.#seleccionados.has(id));
    if (igual) return;
    this.#seleccionados.clear();
    for (const id of nueva) this.#seleccionados.add(id);
    this.#renderizarLista();
    this.#onSeleccionCambia(new Set(this.#seleccionados));
  }

  /** Quita el fragmento del DOM. No se puede seguir usando la instancia tras esto. */
  destruir(): void {
    this.#contenedor.replaceChildren();
  }

  #alternarSeleccion(idNativo: string, marcado: boolean): void {
    if (marcado) this.#seleccionados.add(idNativo);
    else this.#seleccionados.delete(idNativo);
    this.#onSeleccionCambia(new Set(this.#seleccionados));
  }

  #renderizarLista(): void {
    const resultado = filtrarCanales(this.#canales, {
      consulta: this.#consulta,
      mostrarInactivos: this.#mostrarInactivos,
    });

    this.#resumen.textContent = textoResumenOcultos(resultado.ocultos, this.#mostrarInactivos);
    this.#lista.replaceChildren(...resultado.visibles.map((f) => this.#filaCanal(f)));
  }

  #filaCanal(filtrado: CanalFiltrado): HTMLLIElement {
    const { canal, motivoInactivo } = filtrado;
    const fila = this.#documento.createElement("li");
    fila.className = "selector-canales__fila";
    if (motivoInactivo !== null) fila.classList.add("selector-canales__fila--inactivo");

    const casilla = this.#documento.createElement("input");
    casilla.type = "checkbox";
    casilla.checked = this.#seleccionados.has(canal.idNativo);
    casilla.addEventListener("change", () =>
      this.#alternarSeleccion(canal.idNativo, casilla.checked),
    );

    const nombre = this.#documento.createElement("span");
    nombre.className = "selector-canales__nombre";
    nombre.textContent = canal.nombre;

    const partes: Node[] = [casilla, nombre];

    if (canal.rol !== null) {
      const rol = this.#documento.createElement("span");
      rol.className = "selector-canales__rol";
      rol.textContent = canal.rol;
      partes.push(rol);
    }

    if (motivoInactivo !== null) {
      const texto = textoMotivo(motivoInactivo);
      const motivo = this.#documento.createElement("span");
      motivo.className = "selector-canales__motivo";
      motivo.textContent = texto;
      motivo.title = texto;
      partes.push(motivo);
    }

    fila.append(...partes);
    return fila;
  }
}
