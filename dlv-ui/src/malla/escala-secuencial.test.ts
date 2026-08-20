/**
 * Pruebas de `escalaSecuencial` y `rangoSecuencialDesdeDatos` (F4-07).
 *
 * Esta escala es GENÉRICA (ver la cabecera de `escala-secuencial.ts`): las
 * pruebas usan números y colores sueltos, no grados de avance ni eventos de
 * knock, a propósito — mismo criterio que `escala-divergente.test.ts`.
 */

import { describe, expect, it } from "vitest";

import type { Color } from "../render/tipos.ts";
import { escalaSecuencial, rangoSecuencialDesdeDatos } from "./escala-secuencial.ts";

const BAJO: Color = { r: 0.9, g: 0.9, b: 0.9, a: 1 };
const ALTO: Color = { r: 0.8, g: 0.1, b: 0.1, a: 1 };

describe("escalaSecuencial", () => {
  it("en el extremo mínimo del rango da colorMinimo", () => {
    const escala = escalaSecuencial(BAJO, ALTO, { minimo: 0, maximo: 10 });
    expect(escala(0)).toEqual(BAJO);
  });

  it("en el extremo máximo del rango da colorMaximo", () => {
    const escala = escalaSecuencial(BAJO, ALTO, { minimo: 0, maximo: 10 });
    expect(escala(10)).toEqual(ALTO);
  });

  it("a mitad de camino, un color intermedio distinto de los dos extremos", () => {
    const escala = escalaSecuencial(BAJO, ALTO, { minimo: 0, maximo: 10 });
    const medio = escala(5);
    expect(medio).not.toEqual(BAJO);
    expect(medio).not.toEqual(ALTO);
  });

  it("un valor por debajo del mínimo se satura en colorMinimo, no se sale de la interpolación", () => {
    const escala = escalaSecuencial(BAJO, ALTO, { minimo: 0, maximo: 10 });
    expect(escala(-1000)).toEqual(BAJO);
  });

  it("un valor por encima del máximo se satura en colorMaximo", () => {
    const escala = escalaSecuencial(BAJO, ALTO, { minimo: 0, maximo: 10 });
    expect(escala(1000)).toEqual(ALTO);
  });

  it("un valor no finito (NaN) da colorMinimo: no debería llegar aquí, pero no revienta si lo hace", () => {
    const escala = escalaSecuencial(BAJO, ALTO, { minimo: 0, maximo: 10 });
    expect(escala(NaN)).toEqual(BAJO);
  });

  it("el rango no admite anchura cero ni invertida", () => {
    expect(() => escalaSecuencial(BAJO, ALTO, { minimo: 5, maximo: 5 })).toThrow(RangeError);
    expect(() => escalaSecuencial(BAJO, ALTO, { minimo: 10, maximo: 0 })).toThrow(RangeError);
  });

  it("funciona igual con un rango que no empieza en cero (sin cero especial, a diferencia de la divergente)", () => {
    const escala = escalaSecuencial(BAJO, ALTO, { minimo: 8, maximo: 22 });
    expect(escala(8)).toEqual(BAJO);
    expect(escala(22)).toEqual(ALTO);
  });
});

describe("rangoSecuencialDesdeDatos", () => {
  it("el menor y el mayor valor finito", () => {
    expect(rangoSecuencialDesdeDatos([4, -1, 9, 2])).toEqual({ minimo: -1, maximo: 9 });
  });

  it("ignora los NaN", () => {
    expect(rangoSecuencialDesdeDatos([NaN, 3, NaN, 7])).toEqual({ minimo: 3, maximo: 7 });
  });

  it("sin ningún valor finito, devuelve null", () => {
    expect(rangoSecuencialDesdeDatos([NaN, NaN])).toBeNull();
    expect(rangoSecuencialDesdeDatos([])).toBeNull();
  });

  it("todos los valores idénticos: rango degenerado, null", () => {
    expect(rangoSecuencialDesdeDatos([4, 4, 4])).toBeNull();
  });
});
