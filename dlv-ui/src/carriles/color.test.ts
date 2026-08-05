/**
 * Pruebas de `color.ts`: estabilidad del color por código, no por orden de
 * aparición, y la conversión a CSS que usa `carril-estado.ts`.
 */

import { describe, expect, it } from "vitest";

import { colorACss, colorPorCodigo } from "./color.ts";

describe("colorPorCodigo", () => {
  it("es determinista: el mismo código siempre da el mismo color", () => {
    expect(colorPorCodigo(3)).toEqual(colorPorCodigo(3));
    expect(colorPorCodigo(-101)).toEqual(colorPorCodigo(-101));
  });

  it("no depende del orden de las llamadas anteriores (estabilidad frente a otros códigos)", () => {
    const antes = colorPorCodigo(7);
    colorPorCodigo(1);
    colorPorCodigo(2);
    colorPorCodigo(3);
    const despues = colorPorCodigo(7);
    expect(despues).toEqual(antes);
  });

  it("da componentes válidos en [0, 1] con alfa opaco", () => {
    for (const codigo of [-101, -1, 0, 1, 3, 6, 255, 100000]) {
      const color = colorPorCodigo(codigo);
      for (const canal of [color.r, color.g, color.b]) {
        expect(canal).toBeGreaterThanOrEqual(0);
        expect(canal).toBeLessThanOrEqual(1);
      }
      expect(color.a).toBe(1);
    }
  });

  it("distingue códigos distintos (no todos caen en el mismo matiz)", () => {
    const colores = [0, 1, 2, 3, 4, 5].map((c) => colorPorCodigo(c));
    const distintos = new Set(colores.map((c) => `${c.r},${c.g},${c.b}`));
    expect(distintos.size).toBeGreaterThan(1);
  });

  it("acepta códigos negativos sin NaN (p. ej. Launch Control State, -101..1)", () => {
    for (let codigo = -101; codigo <= 1; codigo += 1) {
      const color = colorPorCodigo(codigo);
      expect(Number.isNaN(color.r)).toBe(false);
      expect(Number.isNaN(color.g)).toBe(false);
      expect(Number.isNaN(color.b)).toBe(false);
    }
  });
});

describe("colorACss", () => {
  it("convierte componentes 0..1 a rgba() con enteros 0..255", () => {
    expect(colorACss({ r: 1, g: 0, b: 0.5, a: 1 })).toBe("rgba(255, 0, 128, 1)");
  });

  it("recorta componentes fuera de [0, 1]", () => {
    expect(colorACss({ r: -1, g: 2, b: 0, a: 1 })).toBe("rgba(0, 255, 0, 1)");
  });
});
