/**
 * Pruebas de `reparto.ts`: el invariante que importa es que la suma de las
 * alturas devueltas cuadra exactamente con el total pedido, y que un
 * arrastre de divisor solo toca a sus dos vecinos.
 */

import { describe, expect, it } from "vitest";

import { alturaTotal, arrastrarDivisor, reescalarAlturas, repartirAlturasIniciales } from "./reparto.ts";

describe("repartirAlturasIniciales", () => {
  it("reparte a partes iguales cuando el total es divisible", () => {
    const alturas = repartirAlturasIniciales(["a", "b", "c", "d"], 400, 60);
    expect([...alturas.values()]).toEqual([100, 100, 100, 100]);
  });

  it("la suma es EXACTAMENTE el total pedido incluso cuando no es divisible", () => {
    const alturas = repartirAlturasIniciales(["a", "b", "c"], 100, 10);
    expect(alturaTotal(alturas)).toBe(100);
  });

  it("con un solo panel, se lleva todo el alto", () => {
    const alturas = repartirAlturasIniciales(["unico"], 250, 60);
    expect(alturas.get("unico")).toBe(250);
  });

  it("lista vacía da un reparto vacío, no un error", () => {
    expect(repartirAlturasIniciales([], 400, 60).size).toBe(0);
  });

  it("un contenedor menor que N * mínimo da al menos el mínimo a cada panel", () => {
    const alturas = repartirAlturasIniciales(["a", "b", "c"], 30, 60);
    for (const valor of alturas.values()) expect(valor).toBeGreaterThanOrEqual(60);
  });
});

describe("arrastrarDivisor", () => {
  it("mover el divisor hacia abajo crece el panel superior y encoge el inferior en la misma medida", () => {
    const resultado = arrastrarDivisor(150, 150, 40, 60);
    expect(resultado.alturaSuperiorPx).toBe(190);
    expect(resultado.alturaInferiorPx).toBe(110);
  });

  it("mover hacia arriba (delta negativo) encoge el superior", () => {
    const resultado = arrastrarDivisor(150, 150, -40, 60);
    expect(resultado.alturaSuperiorPx).toBe(110);
    expect(resultado.alturaInferiorPx).toBe(190);
  });

  it("el total de los dos paneles se conserva siempre, sea cual sea el delta", () => {
    for (const delta of [-500, -80, 0, 25, 500]) {
      const resultado = arrastrarDivisor(150, 150, delta, 60);
      expect(resultado.alturaSuperiorPx + resultado.alturaInferiorPx).toBe(300);
    }
  });

  it("no deja bajar al panel superior por debajo del mínimo", () => {
    const resultado = arrastrarDivisor(150, 150, -1000, 60);
    expect(resultado.alturaSuperiorPx).toBe(60);
    expect(resultado.alturaInferiorPx).toBe(240);
  });

  it("no deja bajar al panel inferior por debajo del mínimo", () => {
    const resultado = arrastrarDivisor(150, 150, 1000, 60);
    expect(resultado.alturaInferiorPx).toBe(60);
    expect(resultado.alturaSuperiorPx).toBe(240);
  });
});

describe("reescalarAlturas", () => {
  it("conserva las proporciones relativas al reescalar", () => {
    const actuales = new Map([
      ["a", 100],
      ["b", 300],
    ]);
    const nuevas = reescalarAlturas(actuales, ["a", "b"], 200, 20);
    // La proporción original es 1:3: 200 repartido en esa proporción es 50:150.
    expect(nuevas.get("a")).toBe(50);
    expect(nuevas.get("b")).toBe(150);
  });

  it("la suma tras reescalar es EXACTAMENTE el nuevo total", () => {
    const actuales = new Map([
      ["a", 111],
      ["b", 222],
      ["c", 333],
    ]);
    const nuevas = reescalarAlturas(actuales, ["a", "b", "c"], 500, 30);
    expect(alturaTotal(nuevas)).toBe(500);
  });

  it("respeta el mínimo aunque la proporción original lo violara al reescalar hacia abajo", () => {
    const actuales = new Map([
      ["a", 500],
      ["b", 10],
    ]);
    const nuevas = reescalarAlturas(actuales, ["a", "b"], 200, 60);
    expect(nuevas.get("b")).toBeGreaterThanOrEqual(60);
  });

  it("orden vacío da un reparto vacío", () => {
    expect(reescalarAlturas(new Map(), [], 400, 60).size).toBe(0);
  });
});
