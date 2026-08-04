/**
 * Pruebas del selector de tema (F3-21).
 *
 * Lo que protegen: que el modo de alto contraste se pueda ELEGIR. La primera
 * versión de la tarea definió los tres temas sin ningún control, y como
 * `prefers-color-scheme` solo distingue claro de oscuro, el alto contraste era
 * inalcanzable: la mitad del título de la tarea no existía en la interfaz.
 */

import { describe, expect, it, beforeEach } from "vitest";

import { CLASE_SELECTOR_TEMA, montarSelectorDeTema } from "./selector-tema.ts";
import { establecerTema, obtenerTemaActual, TEMAS_DISPONIBLES } from "./tema.ts";

function selectorDe(elemento: HTMLElement): HTMLSelectElement {
  const select = elemento.querySelector("select");
  if (select === null) throw new Error("el selector de tema no tiene <select>");
  return select as HTMLSelectElement;
}

beforeEach(() => {
  establecerTema("oscuro");
});

describe("selector de tema", () => {
  it("ofrece los tres temas, alto contraste incluido", () => {
    const select = selectorDe(montarSelectorDeTema());
    const valores = [...select.options].map((o) => o.value);
    expect(valores).toEqual([...TEMAS_DISPONIBLES]);
    expect(valores).toContain("altContraste");
  });

  it("muestra rótulos legibles y no los identificadores internos", () => {
    const select = selectorDe(montarSelectorDeTema());
    const etiquetas = [...select.options].map((o) => o.textContent);
    expect(etiquetas).toContain("Alto contraste");
    expect(etiquetas).not.toContain("altContraste");
  });

  it("arranca mostrando el tema activo, no el primero de la lista", () => {
    establecerTema("altContraste");
    expect(selectorDe(montarSelectorDeTema()).value).toBe("altContraste");
  });

  it("cambiar la selección aplica el tema", () => {
    const select = selectorDe(montarSelectorDeTema());
    select.value = "altContraste";
    select.dispatchEvent(new Event("change"));
    expect(obtenerTemaActual()).toBe("altContraste");
  });

  it("una opción con un valor que no es un tema no aplica nada", () => {
    /* `HTMLSelectElement.value` es un `string` para el tipo, así que la
       comprobación no es decorativa: sin ella, una opción añadida desde fuera
       dejaría `temaActual` con un nombre que no tiene paleta. */
    const elemento = montarSelectorDeTema();
    const select = selectorDe(elemento);
    const intrusa = document.createElement("option");
    intrusa.value = "morado";
    select.appendChild(intrusa);
    select.value = "morado";
    select.dispatchEvent(new Event("change"));
    expect(obtenerTemaActual()).toBe("oscuro");
  });

  it("lleva la clase que la hoja de estilos espera y una etiqueta accesible", () => {
    const elemento = montarSelectorDeTema();
    expect(elemento.className).toBe(CLASE_SELECTOR_TEMA);
    expect(selectorDe(elemento).getAttribute("aria-label")).toBeTruthy();
  });
});
