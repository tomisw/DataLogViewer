/**
 * Pruebas del selector de tema (F3-21) — solo su parte pura.
 *
 * POR QUÉ AQUÍ NO SE CONSTRUYE NINGÚN NODO
 * =========================================
 * `vitest.config.ts` fija `environment: "node"`, sin DOM, y es una decisión del
 * proyecto y no una carencia: los componentes que solo construyen nodos y cablean
 * eventos no se prueban con vitest (`selector-canales.ts` y `paleta-comandos.ts`
 * tampoco tienen fichero de pruebas), y lo que necesita navegador de verdad es la
 * regresión visual de F5-12.
 *
 * La primera versión de este fichero construía un `<select>` con
 * `document.createElement` y le lanzaba eventos. No habría fallado por estar mal
 * escrita: habría fallado por falta de `document`, en CI, después de que esta
 * tarea se diera por terminada.
 *
 * Lo que sí se prueba es la única decisión del componente: qué cadenas son un
 * tema. Es la guarda que impide que una opción añadida desde fuera del selector
 * deje el tema en un nombre que no tiene paleta.
 */

import { describe, expect, it } from "vitest";

import { esNombreDeTema } from "./selector-tema.ts";
import { TEMAS_DISPONIBLES } from "./tema.ts";

describe("selector de tema: qué es un tema", () => {
  it("acepta los tres temas de la tarea, alto contraste incluido", () => {
    for (const tema of TEMAS_DISPONIBLES) {
      expect(esNombreDeTema(tema)).toBe(true);
    }
    expect(esNombreDeTema("altContraste")).toBe(true);
  });

  it("rechaza cualquier otra cosa", () => {
    for (const valor of ["morado", "", "Oscuro", "oscuro ", "dark", "altcontraste"]) {
      expect(esNombreDeTema(valor), valor).toBe(false);
    }
  });

  it("rechaza el rótulo visible, que no es el identificador", () => {
    /* El selector muestra «Alto contraste» y vale `altContraste`: si la guarda
       aceptara el rótulo, un cambio de idioma (F5-10) rompería el selector. */
    expect(esNombreDeTema("Alto contraste")).toBe(false);
  });
});
