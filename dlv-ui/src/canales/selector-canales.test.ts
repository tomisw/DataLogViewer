/**
 * Pruebas de las funciones puras de `selector-canales.ts` (F1-33).
 *
 * La clase `SelectorCanales` en sí toca `document` y por eso no se prueba
 * aquí: `vitest.config.ts` corre en `environment: "node"`, sin DOM, la misma
 * razón por la que `main.ts` y `Renderizador.desdeLienzo` tampoco tienen
 * prueba directa. Lo que SÍ se puede y se debe probar sin navegador son los
 * dos trocitos de texto que explican una fila -- "oculto porque está
 * constante" es justo la frase que pide el enunciado de F1-33, y una frase
 * mal armada no lanza ninguna excepción que la detecte.
 */

import { describe, expect, it } from "vitest";

import { textoMotivo, textoResumenOcultos } from "./selector-canales.ts";

describe("textoMotivo", () => {
  it("explica por qué, no solo lanza una etiqueta seca", () => {
    expect(textoMotivo("constante")).toMatch(/constante/);
    expect(textoMotivo("vacio")).toMatch(/vac[ií]o/);
  });

  it("un canal activo no lleva texto", () => {
    expect(textoMotivo(null)).toBe("");
  });
});

describe("textoResumenOcultos", () => {
  it("sin ocultos, no hay nada que decir", () => {
    expect(textoResumenOcultos({ constante: 0, vacio: 0 }, false)).toBe("");
  });

  it("con mostrarInactivos activado, tampoco (nada está oculto)", () => {
    expect(textoResumenOcultos({ constante: 3, vacio: 2 }, true)).toBe("");
  });

  it("menciona el total y desglosa por motivo", () => {
    const texto = textoResumenOcultos({ constante: 3, vacio: 2 }, false);
    expect(texto).toMatch(/5/);
    expect(texto).toMatch(/3 constante/);
    expect(texto).toMatch(/2 vac[ií]o/);
  });

  it("no menciona un motivo con cero canales", () => {
    const texto = textoResumenOcultos({ constante: 4, vacio: 0 }, false);
    expect(texto).not.toMatch(/vac[ií]o/);
  });
});
