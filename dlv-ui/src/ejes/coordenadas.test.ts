/**
 * Pruebas de `coordenadas.ts`: la conversión de datos a píxeles del DOM.
 *
 * El caso que vigilan estas pruebas es exactamente el que describe la tarea:
 * «si la inviertes, rejilla y trazo no coincidirán y el fallo se ve como "los
 * datos están del revés"». `xAPixel` no se invierte (el DOM crece hacia la
 * derecha igual que los datos); `yAPixel` sí, porque el DOM crece hacia abajo
 * y los datos "hacia arriba". Que ambas cosas a la vez es lo que hay que
 * comprobar, no solo una.
 */

import { describe, expect, it } from "vitest";

import { xAPixel, yAPixel } from "./coordenadas.ts";
import type { Vista } from "../render/tipos.ts";

describe("xAPixel", () => {
  const vista: Vista = { t0: 10, t1: 20, v0: 0, v1: 100 };

  it("lleva t0 al borde izquierdo (0) y t1 al derecho (anchoAreaPx)", () => {
    expect(xAPixel(10, vista, 1000)).toBeCloseTo(0, 9);
    expect(xAPixel(20, vista, 1000)).toBeCloseTo(1000, 9);
  });

  it("es lineal en el interior del rango", () => {
    expect(xAPixel(15, vista, 1000)).toBeCloseTo(500, 9);
  });

  it("un ancho de vista nulo (t0 === t1) colapsa al centro, no a Infinity/NaN", () => {
    const degenerada: Vista = { t0: 5, t1: 5, v0: 0, v1: 1 };
    const pixel = xAPixel(5, degenerada, 800);
    expect(Number.isFinite(pixel)).toBe(true);
    expect(pixel).toBeCloseTo(400, 9);
  });

  it("no asume t0 < t1: con la vista al revés, t0 sigue en el píxel 0", () => {
    const alReves: Vista = { t0: 20, t1: 10, v0: 0, v1: 100 };
    expect(xAPixel(20, alReves, 1000)).toBeCloseTo(0, 9);
    expect(xAPixel(10, alReves, 1000)).toBeCloseTo(1000, 9);
  });
});

describe("yAPixel", () => {
  const vista: Vista = { t0: 0, t1: 1, v0: 0, v1: 100 };

  it("lleva v1 (el de arriba en los datos) al píxel 0 (arriba del DOM)", () => {
    expect(yAPixel(100, vista, 500)).toBeCloseTo(0, 9);
  });

  it("lleva v0 (el de abajo en los datos) al píxel altoAreaPx (abajo del DOM)", () => {
    expect(yAPixel(0, vista, 500)).toBeCloseTo(500, 9);
  });

  it("un valor mayor siempre da un píxel menor o igual (la inversión completa)", () => {
    const bajo = yAPixel(20, vista, 500);
    const alto = yAPixel(80, vista, 500);
    expect(alto).toBeLessThan(bajo);
  });

  it("es lineal en el interior del rango", () => {
    expect(yAPixel(50, vista, 500)).toBeCloseTo(250, 9);
  });

  it("un alto de vista nulo (v0 === v1) colapsa al centro, no a Infinity/NaN", () => {
    const degenerada: Vista = { t0: 0, t1: 1, v0: 7, v1: 7 };
    const pixel = yAPixel(7, degenerada, 400);
    expect(Number.isFinite(pixel)).toBe(true);
    expect(pixel).toBeCloseTo(200, 9);
  });

  it("un rango de valores negativo se invierte igual que uno positivo", () => {
    const negativa: Vista = { t0: 0, t1: 1, v0: -100, v1: -50 };
    // v1 (-50, el "de arriba") al píxel 0; v0 (-100, el "de abajo") al fondo.
    expect(yAPixel(-50, negativa, 500)).toBeCloseTo(0, 9);
    expect(yAPixel(-100, negativa, 500)).toBeCloseTo(500, 9);
  });
});

describe("xAPixel y yAPixel juntas: coherencia con la convención del renderizador", () => {
  it("el punto (t0, v0), la esquina inferior izquierda de los datos, cae en la esquina inferior izquierda del DOM", () => {
    const vista: Vista = { t0: 0, t1: 10, v0: 0, v1: 100 };
    const ancho = 800;
    const alto = 400;
    expect(xAPixel(vista.t0, vista, ancho)).toBeCloseTo(0, 9);
    expect(yAPixel(vista.v0, vista, alto)).toBeCloseTo(alto, 9);
  });

  it("el punto (t1, v1), la esquina superior derecha de los datos, cae en la esquina superior derecha del DOM", () => {
    const vista: Vista = { t0: 0, t1: 10, v0: 0, v1: 100 };
    const ancho = 800;
    const alto = 400;
    expect(xAPixel(vista.t1, vista, ancho)).toBeCloseTo(ancho, 9);
    expect(yAPixel(vista.v1, vista, alto)).toBeCloseTo(0, 9);
  });
});
