/**
 * Leyenda de la vista paralela: qué color representa a qué log.
 *
 * Sin ella, la decisión 1 del informe (color estable por log) es invisible:
 * un color estable que nadie puede leer no ayuda a comparar dos tiradas. El
 * componente es deliberadamente mínimo, calcado de `cursor/cursor.ts`
 * (F1-29): DOM directo, sin framework, con el documento inyectable para
 * poder montarlo en una prueba de Node (`vitest.config.ts` corre en
 * `environment: "node"`, sin `document`).
 *
 * REUTILIZA `cursor/contexto-dom.ts` EN VEZ DE UN DOBLE NUEVO
 * =================================================================
 * La superficie de DOM que hace falta aquí —crear un elemento, escribir
 * `textContent`/`className`, fijar una propiedad de `style`— es exactamente
 * la misma que ya declara `cursor/contexto-dom.ts#ContextoDOM` y que ya
 * implementa `cursor/doble-dom.ts#crearDobleDOM`. Escribir un tercer doble
 * casi idéntico sería la misma trampa que `tema.ts` ya señala para la
 * paleta de color: dos copias que se desincronizan en cuanto alguien toca
 * una. Este módulo importa el tipo de `cursor/` y las pruebas importan el
 * doble de `cursor/` — cero DOM nuevo que mantener.
 */

import type { ContextoDOM } from "../cursor/contexto-dom.ts";
import { colorACss } from "../carriles/color.ts";
import { colorDeSegmento } from "./vista-paralela.ts";
import type { EntradaLeyenda } from "./tipos.ts";

/**
 * Leyenda de color por log. `montar` crea la lista dentro de `contenedor`
 * (el panel o la barra que decida quien ensambla la vista);
 * `actualizar` la reconstruye por completo cuando cambia la composición de
 * segmentos —igual que `CursorDeTabla.actualizarCanales`, que tampoco tiene
 * presupuesto de 16 ms porque cambiar de log no pasa 60 veces por segundo—.
 */
export class LeyendaSegmentos {
  readonly #documento: ContextoDOM;
  readonly #lista: HTMLElement;

  constructor(contenedor: HTMLElement, documento: ContextoDOM = document) {
    this.#documento = documento;
    this.#lista = documento.createElement("ul");
    this.#lista.className = "leyenda-paralela";
    contenedor.appendChild(this.#lista);
  }

  /** Reemplaza las entradas mostradas. El color de cada una sale de `colorDeSegmento`. */
  actualizar(entradas: readonly EntradaLeyenda[]): void {
    this.#lista.textContent = ""; // Vacía el `<ul>`, como en el DOM real.
    for (const entrada of entradas) {
      const item = this.#documento.createElement("li");
      item.className = "leyenda-paralela-item";

      const muestra = this.#documento.createElement("span");
      muestra.className = "leyenda-paralela-muestra";
      muestra.style.setProperty("background-color", colorACss(colorDeSegmento(entrada.idSegmento)));

      const etiqueta = this.#documento.createElement("span");
      etiqueta.className = "leyenda-paralela-etiqueta";
      etiqueta.textContent = entrada.etiqueta;

      item.appendChild(muestra);
      item.appendChild(etiqueta);
      this.#lista.appendChild(item);
    }
  }

  /** Quita la leyenda del `contenedor`. El contenedor lo gestiona quien lo creó. */
  destruir(): void {
    this.#lista.remove();
  }
}
