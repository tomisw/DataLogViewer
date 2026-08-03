/**
 * Pruebas de `geometria.ts`: la integración de ticks, formato y coordenadas.
 *
 * Lo que importa comprobar aquí no está en ninguno de los tres módulos por
 * separado: que el píxel de un tick de la rejilla es EXACTAMENTE el mismo
 * número que decide dónde va su etiqueta (la garantía de alineación que pide
 * la tarea), y que la vista completa se comporta bien de punta a punta con
 * los rangos raros, no solo con el caso normal.
 */

import { describe, expect, it } from "vitest";

import { calcularGeometriaEjes, MARGEN_EJES } from "./geometria.ts";
import { xAPixel, yAPixel } from "./coordenadas.ts";
import type { ConfiguracionEjes } from "./tipos.ts";
import type { Vista } from "../render/tipos.ts";

function config(parcial: Partial<ConfiguracionEjes> = {}): ConfiguracionEjes {
  return {
    vista: { t0: 0, t1: 1800, v0: 0, v1: 100 },
    anchoPx: 800,
    altoPx: 400,
    unidadY: "°C",
    series: [],
    ...parcial,
  };
}

describe("calcularGeometriaEjes", () => {
  it("cada tick de la rejilla usa exactamente el mismo píxel que su etiqueta", () => {
    const geometria = calcularGeometriaEjes(config());
    for (const tick of geometria.ticksX) {
      expect(tick.pixel).toBe(xAPixel(tick.valor, config().vista, geometria.area.ancho));
    }
    for (const tick of geometria.ticksY) {
      expect(tick.pixel).toBe(yAPixel(tick.valor, config().vista, geometria.area.alto));
    }
  });

  it("el área de dibujo respeta los márgenes fijos", () => {
    const geometria = calcularGeometriaEjes(config({ anchoPx: 800, altoPx: 400 }));
    expect(geometria.area.x).toBe(MARGEN_EJES.izquierda);
    expect(geometria.area.y).toBe(MARGEN_EJES.arriba);
    expect(geometria.area.ancho).toBe(800 - MARGEN_EJES.izquierda - MARGEN_EJES.derecha);
    expect(geometria.area.alto).toBe(400 - MARGEN_EJES.arriba - MARGEN_EJES.abajo);
  });

  it("un panel más pequeño que los márgenes no da un área negativa", () => {
    const geometria = calcularGeometriaEjes(config({ anchoPx: 10, altoPx: 10 }));
    expect(geometria.area.ancho).toBeGreaterThan(0);
    expect(geometria.area.alto).toBeGreaterThan(0);
  });

  it("el eje Y no se invierte: un tick de valor mayor cae en un píxel menor", () => {
    const geometria = calcularGeometriaEjes(config());
    const ordenados = [...geometria.ticksY].sort((a, b) => a.valor - b.valor);
    for (let i = 1; i < ordenados.length; i += 1) {
      expect(ordenados[i]!.pixel).toBeLessThanOrEqual(ordenados[i - 1]!.pixel);
    }
  });

  it("el eje X no se invierte: un tick de tiempo mayor cae en un píxel mayor", () => {
    const geometria = calcularGeometriaEjes(config());
    const ordenados = [...geometria.ticksX].sort((a, b) => a.valor - b.valor);
    for (let i = 1; i < ordenados.length; i += 1) {
      expect(ordenados[i]!.pixel).toBeGreaterThanOrEqual(ordenados[i - 1]!.pixel);
    }
  });

  it("una vista degenerada en ambos ejes (t0===t1, v0===v1) no revienta", () => {
    const vista: Vista = { t0: 5, t1: 5, v0: 7, v1: 7 };
    const geometria = calcularGeometriaEjes(config({ vista }));
    expect(geometria.ticksX).toHaveLength(1);
    expect(geometria.ticksY).toHaveLength(1);
    expect(Number.isFinite(geometria.ticksX[0]!.pixel)).toBe(true);
    expect(Number.isFinite(geometria.ticksY[0]!.pixel)).toBe(true);
  });

  it("pasa el nombre de unidad y el título tal cual, sin inventar conversión", () => {
    const geometria = calcularGeometriaEjes(config({ unidadY: "psi", tituloY: "Boost" }));
    expect(geometria.unidadY).toBe("psi");
    expect(geometria.tituloY).toBe("Boost");
    expect(geometria.unidadX).toBe("s"); // por omisión, Vista.t0/t1 son segundos
  });

  it("el título Y por omisión es el nombre de la unidad", () => {
    const geometria = calcularGeometriaEjes(config({ unidadY: "bar", tituloY: undefined }));
    expect(geometria.tituloY).toBe("bar");
  });

  it("propaga la lista de series a la leyenda sin transformarla", () => {
    const series = [
      { id: "rpm", nombre: "Régimen", color: { r: 1, g: 0, b: 0, a: 1 }, unidad: "rpm" },
      { id: "map", nombre: "Presión de colector", color: { r: 0, g: 1, b: 0, a: 1 }, unidad: "kPa" },
    ];
    const geometria = calcularGeometriaEjes(config({ series }));
    expect(geometria.leyenda).toEqual(series);
  });

  it("una vista muy ampliada en el tiempo (20 ms a las 8 h) da ticks dentro del área", () => {
    const centro = 8 * 3600;
    const vista: Vista = { t0: centro, t1: centro + 0.02, v0: 0, v1: 1 };
    const geometria = calcularGeometriaEjes(config({ vista }));
    for (const tick of geometria.ticksX) {
      expect(tick.pixel).toBeGreaterThanOrEqual(-1e-6);
      expect(tick.pixel).toBeLessThanOrEqual(geometria.area.ancho + 1e-6);
    }
  });
});
