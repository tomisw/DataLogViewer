/**
 * Pruebas de la aritmética de navegación (F1-28).
 *
 * Tres propiedades son las que de verdad importan y las que pide la tarea:
 * el punto bajo el puntero no se mueve al hacer zoom, el zoom nunca invierte
 * la vista por mucho que se repita, y `direccionDe` distingue avance de
 * retroceso sin confundirse con ruido de punto flotante.
 */

import { describe, expect, it } from "vitest";

import { desplazar, desplazarPx, direccionDe, zoomEnPunto } from "./aritmetica.ts";
import type { Vista } from "../render/tipos.ts";

describe("zoomEnPunto", () => {
  const vista: Vista = { t0: 100, t1: 300, v0: 0, v1: 40 };

  it("deja el punto bajo el cursor exactamente donde estaba (ambos ejes)", () => {
    const fraccionX = 0.25;
    const fraccionY = 0.75; // cerca del borde inferior de la pantalla → valor bajo
    const puntoTAntes = vista.t0 + fraccionX * (vista.t1 - vista.t0);
    const puntoVAntes = vista.v1 - fraccionY * (vista.v1 - vista.v0);

    const nueva = zoomEnPunto(vista, 4, 2, fraccionX, fraccionY);

    const puntoTDespues = nueva.t0 + fraccionX * (nueva.t1 - nueva.t0);
    const puntoVDespues = nueva.v1 - fraccionY * (nueva.v1 - nueva.v0);
    expect(puntoTDespues).toBeCloseTo(puntoTAntes, 9);
    expect(puntoVDespues).toBeCloseTo(puntoVAntes, 9);
    // Y de verdad amplió lo que se le pidió, no solo que el punto coincida.
    expect(nueva.t1 - nueva.t0).toBeCloseTo((vista.t1 - vista.t0) / 4, 9);
    expect(nueva.v1 - nueva.v0).toBeCloseTo((vista.v1 - vista.v0) / 2, 9);
  });

  it("centrado en el borde izquierdo/superior deja ese borde fijo", () => {
    const nueva = zoomEnPunto(vista, 10, 10, 0, 0);
    expect(nueva.t0).toBeCloseTo(vista.t0, 9);
    expect(nueva.v1).toBeCloseTo(vista.v1, 9);
  });

  it("centrado en el borde derecho/inferior deja ese borde fijo", () => {
    const nueva = zoomEnPunto(vista, 10, 10, 1, 1);
    expect(nueva.t1).toBeCloseTo(vista.t1, 9);
    expect(nueva.v0).toBeCloseTo(vista.v0, 9);
  });

  it("un factor de 1 en un eje no lo toca", () => {
    const nueva = zoomEnPunto(vista, 3, 1, 0.4, 0.4);
    expect(nueva.v0).toBe(vista.v0);
    expect(nueva.v1).toBe(vista.v1);
  });

  it("nunca invierte la vista aunque se amplíe miles de veces seguidas", () => {
    let v: Vista = { t0: 0, t1: 1, v0: -5, v1: 5 };
    for (let i = 0; i < 2000; i += 1) {
      v = zoomEnPunto(v, 1.5, 1.5, 0.3, 0.7);
      expect(v.t1).toBeGreaterThan(v.t0);
      expect(v.v1).toBeGreaterThan(v.v0);
    }
  });

  it("rechaza un factor no positivo o no finito en vez de propagar NaN/Infinity", () => {
    expect(() => zoomEnPunto(vista, 0, 1, 0.5, 0.5)).toThrow(/inválido/);
    expect(() => zoomEnPunto(vista, -2, 1, 0.5, 0.5)).toThrow(/inválido/);
    expect(() => zoomEnPunto(vista, Number.POSITIVE_INFINITY, 1, 0.5, 0.5)).toThrow(/inválido/);
    expect(() => zoomEnPunto(vista, Number.NaN, 1, 0.5, 0.5)).toThrow(/inválido/);
    expect(() => zoomEnPunto(vista, 1, 0, 0.5, 0.5)).toThrow(/inválido/);
  });
});

describe("desplazar / desplazarPx", () => {
  it("desplazar mueve los dos bordes de cada eje por el mismo delta", () => {
    const vista: Vista = { t0: 0, t1: 10, v0: -1, v1: 1 };
    const nueva = desplazar(vista, 5, -2);
    expect(nueva).toEqual({ t0: 5, t1: 15, v0: -3, v1: -1 });
  });

  it("desplazarPx: arrastrar hacia la derecha retrocede en el tiempo, hacia abajo sube el valor", () => {
    const vista: Vista = { t0: 0, t1: 100, v0: 0, v1: 50 };
    // dx = 10 % del ancho del panel, dy = 10 % del alto.
    const nueva = desplazarPx(vista, 80, 40, 800, 400);
    expect(nueva.t0).toBeCloseTo(-10, 9); // -0.1 * 100
    expect(nueva.t1).toBeCloseTo(90, 9);
    expect(nueva.v0).toBeCloseTo(5, 9); // +0.1 * 50
    expect(nueva.v1).toBeCloseTo(55, 9);
  });

  it("el dato que estaba en un píxel sigue al puntero: aparece dx/dy más allá", () => {
    const vista: Vista = { t0: 0, t1: 100, v0: 0, v1: 50 };
    const ancho = 800;
    const alto = 400;
    const dx = 120;
    const dy = -40;
    const nueva = desplazarPx(vista, dx, dy, ancho, alto);

    // El dato que antes estaba en el borde izquierdo (fracción 0, t0) tiene
    // que reaparecer en la fracción dx/ancho de la vista nueva.
    const fraccionDx = dx / ancho;
    const datoEnNuevaEnFraccionDx = nueva.t0 + fraccionDx * (nueva.t1 - nueva.t0);
    expect(datoEnNuevaEnFraccionDx).toBeCloseTo(vista.t0, 9);

    const fraccionDy = dy / alto;
    const datoEnNuevaEnFraccionDy = nueva.v1 - fraccionDy * (nueva.v1 - nueva.v0);
    expect(datoEnNuevaEnFraccionDy).toBeCloseTo(vista.v1, 9);
  });

  it("un panel de tamaño 0 no desplaza ese eje (no divide por cero)", () => {
    const vista: Vista = { t0: 0, t1: 10, v0: 0, v1: 5 };
    const nueva = desplazarPx(vista, 100, 100, 0, 0);
    expect(nueva).toEqual(vista);
  });
});

describe("direccionDe", () => {
  it("detecta avance y retroceso en el tiempo", () => {
    const a: Vista = { t0: 0, t1: 10, v0: 0, v1: 1 };
    const b: Vista = { t0: 5, t1: 15, v0: 0, v1: 1 }; // el centro pasa de 5 a 10: avanza
    expect(direccionDe(a, b)).toBe(1);
    expect(direccionDe(b, a)).toBe(-1);
  });

  it("un pan solo vertical no cuenta como movimiento horizontal", () => {
    const a: Vista = { t0: 0, t1: 10, v0: 0, v1: 1 };
    const b: Vista = { t0: 0, t1: 10, v0: 5, v1: 6 };
    expect(direccionDe(a, b)).toBe(0);
  });

  it("un cambio horizontal por debajo del umbral relativo cuenta como quieto", () => {
    const a: Vista = { t0: 0, t1: 1000, v0: 0, v1: 1 };
    const b: Vista = { t0: 1e-8, t1: 1000 + 1e-8, v0: 0, v1: 1 };
    expect(direccionDe(a, b)).toBe(0);
  });

  it("un zoom centrado fuera del centro del panel también cuenta como movimiento", () => {
    const a: Vista = { t0: 0, t1: 100, v0: 0, v1: 1 };
    // Ampliar cerca del extremo derecho desplaza el centro hacia la derecha.
    const b = zoomEnPunto(a, 4, 1, 0.9, 0.5);
    expect(direccionDe(a, b)).toBe(1);
  });

  it("vistas sin anchura no producen una dirección (evita 0/0)", () => {
    const a: Vista = { t0: 5, t1: 5, v0: 0, v1: 1 };
    const b: Vista = { t0: 5, t1: 5, v0: 0, v1: 1 };
    expect(direccionDe(a, b)).toBe(0);
  });
});
