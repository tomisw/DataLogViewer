/**
 * Pruebas de `escalaDivergente` y `escalaMaximaDesdeDatos` (F4-04).
 *
 * Esta escala es GENÉRICA (ver la cabecera de `escala-divergente.ts`): las
 * pruebas usan números sueltos, no λ, a propósito — es exactamente la
 * garantía que F4-08 (comparación de dos logs) necesita para poder reutilizar
 * este módulo sin que nadie tenga que releer un docstring de mezcla de
 * combustible primero.
 */

import { describe, expect, it } from "vitest";

import { escalaDivergente, escalaMaximaDesdeDatos } from "./escala-divergente.ts";

describe("escalaDivergente", () => {
  it("cero da el color central, sea cual sea la escala máxima", () => {
    const escala = escalaDivergente(10);
    const color = escala(0);
    // El centro es el mismo para +0 y -0, y es un gris neutro, no transparente.
    expect(color.a).toBe(1);
    expect(color.r).toBeCloseTo(color.g, 5);
    expect(color.g).toBeCloseTo(color.b, 5);
  });

  it("un valor positivo y su opuesto dan colores distintos: la escala es sensible al signo", () => {
    const escala = escalaDivergente(10);
    const positivo = escala(5);
    const negativo = escala(-5);
    expect(positivo).not.toEqual(negativo);
  });

  it("un valor en la escala máxima está más saturado que uno a mitad de camino", () => {
    const escala = escalaDivergente(10);
    const mitad = escala(5);
    const extremo = escala(10);
    const centro = escala(0);
    // Distancia del centro: el extremo se aleja más que la mitad en el canal que domina (rojo, para positivo).
    const distanciaMitad = Math.abs(mitad.r - centro.r);
    const distanciaExtremo = Math.abs(extremo.r - centro.r);
    expect(distanciaExtremo).toBeGreaterThan(distanciaMitad);
  });

  it("un valor por encima de la escala máxima se satura, no se sale de [0,1]", () => {
    const escala = escalaDivergente(10);
    const dentro = escala(10);
    const fuera = escala(1000);
    expect(fuera).toEqual(dentro);
  });

  it("un valor no finito (NaN) da el color central: no debería llegar aquí, pero no revienta si lo hace", () => {
    const escala = escalaDivergente(10);
    const centro = escala(0);
    expect(escala(NaN)).toEqual(centro);
  });

  it("escalaMaxima <= 0 lanza: una escala sin anchura no se puede pintar", () => {
    expect(() => escalaDivergente(0)).toThrow(RangeError);
    expect(() => escalaDivergente(-5)).toThrow(RangeError);
  });
});

describe("escalaMaximaDesdeDatos", () => {
  it("el mayor valor absoluto finito, sea positivo o negativo", () => {
    expect(escalaMaximaDesdeDatos([1, -5, 3, -2])).toBe(5);
  });

  it("ignora los NaN, no los trata como el mayor valor posible", () => {
    expect(escalaMaximaDesdeDatos([1, NaN, -3, NaN])).toBe(3);
  });

  it("sin ningún valor finito, devuelve null: no hay escala que deducir", () => {
    expect(escalaMaximaDesdeDatos([NaN, NaN])).toBeNull();
    expect(escalaMaximaDesdeDatos([])).toBeNull();
  });

  it("todos los valores exactamente en cero: null, un rango degenerado no se inventa", () => {
    expect(escalaMaximaDesdeDatos([0, 0, 0])).toBeNull();
  });
});
