/**
 * Pruebas de `rango.ts`: combinación de rangos y margen.
 *
 * El foco, como en `ejes/ticks.test.ts`, son los casos degenerados que pide
 * la tarea explícitamente — canal constante (rango cero) y canal todo nulo —
 * porque son los que producen una división por cero aguas abajo si nadie los
 * trata a propósito.
 */

import { describe, expect, it } from "vitest";

import {
  combinarRangos,
  conMargen,
  esRangoValido,
  FRACCION_MARGEN_DEFECTO,
  MARGEN_ABSOLUTO_VALOR_CERO,
} from "./rango.ts";

describe("esRangoValido", () => {
  it("acepta un rango con min/max finitos", () => {
    expect(esRangoValido({ min: 0, max: 1 })).toBe(true);
  });

  it("rechaza null y undefined", () => {
    expect(esRangoValido(null)).toBe(false);
    expect(esRangoValido(undefined)).toBe(false);
  });

  it("rechaza NaN e Infinity en cualquiera de los dos extremos", () => {
    expect(esRangoValido({ min: Number.NaN, max: 1 })).toBe(false);
    expect(esRangoValido({ min: 0, max: Number.POSITIVE_INFINITY })).toBe(false);
  });
});

describe("combinarRangos", () => {
  it("da el mínimo de los mínimos y el máximo de los máximos", () => {
    const combinado = combinarRangos([
      { min: 0, max: 10 },
      { min: -5, max: 4 },
      { min: 2, max: 20 },
    ]);
    expect(combinado).toEqual({ min: -5, max: 20 });
  });

  it("ignora las entradas null (serie sin dato visible) sin que rompan el resto", () => {
    const combinado = combinarRangos([{ min: 0, max: 10 }, null, { min: -3, max: 3 }]);
    expect(combinado).toEqual({ min: -3, max: 10 });
  });

  it("caso «canal todo nulo»: si NINGUNA entrada es válida, da `undefined`, no un centinela", () => {
    expect(combinarRangos([null, null, undefined])).toBeUndefined();
    expect(combinarRangos([])).toBeUndefined();
  });

  it("un único rango se combina consigo mismo sin cambiarlo", () => {
    expect(combinarRangos([{ min: 3, max: 7 }])).toEqual({ min: 3, max: 7 });
  });
});

describe("conMargen", () => {
  it("caso normal: añade la fracción pedida a cada lado", () => {
    const conAire = conMargen({ min: 0, max: 100 }, 0.1);
    expect(conAire).toEqual({ min: -10, max: 110 });
  });

  it("usa FRACCION_MARGEN_DEFECTO si no se pasa fracción", () => {
    const conAire = conMargen({ min: 0, max: 100 });
    const esperado = 100 * FRACCION_MARGEN_DEFECTO;
    expect(conAire.min).toBeCloseTo(-esperado, 9);
    expect(conAire.max).toBeCloseTo(100 + esperado, 9);
  });

  it("caso degenerado — canal constante distinto de cero: no da rango cero", () => {
    const conAire = conMargen({ min: 90, max: 90 });
    expect(conAire.max).toBeGreaterThan(conAire.min);
    // Centrado en el valor constante.
    expect((conAire.min + conAire.max) / 2).toBeCloseTo(90, 9);
  });

  it("caso degenerado con fraccion = 0 (\"sin margen\") SIGUE sin dar rango cero", () => {
    // Es la garantía que documenta la cabecera: el caso degenerado no puede
    // depender de un margen que el que llama puso a cero, porque eso
    // reproduciría exactamente la división por cero que existe para evitar.
    const conAire = conMargen({ min: 42, max: 42 }, 0);
    expect(conAire.max).toBeGreaterThan(conAire.min);
  });

  it("caso degenerado en exactamente cero usa el margen absoluto documentado", () => {
    const conAire = conMargen({ min: 0, max: 0 });
    expect(conAire).toEqual({
      min: -MARGEN_ABSOLUTO_VALOR_CERO,
      max: MARGEN_ABSOLUTO_VALOR_CERO,
    });
  });

  it("caso degenerado negativo también queda centrado y con ancho positivo", () => {
    const conAire = conMargen({ min: -50, max: -50 });
    expect(conAire.max).toBeGreaterThan(conAire.min);
    expect((conAire.min + conAire.max) / 2).toBeCloseTo(-50, 9);
  });

  it("rechaza una fracción negativa o no finita en vez de producir un margen sin sentido", () => {
    expect(() => conMargen({ min: 0, max: 1 }, -0.1)).toThrow(/margen/);
    expect(() => conMargen({ min: 0, max: 1 }, Number.NaN)).toThrow(/margen/);
  });
});
