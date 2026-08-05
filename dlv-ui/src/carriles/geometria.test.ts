/**
 * Pruebas de `geometria.ts`: qué bandas y qué marcas de transición produce
 * `calcularGeometriaCarril`, sin DOM.
 *
 * El foco no es "se ve bonito" (eso es `carril-estado.ts` y, en última
 * instancia, un navegador) sino las tres garantías que pide el enunciado de
 * la tarea:
 *   1. cubos consecutivos con la misma moda se fusionan en una banda,
 *   2. la marca de `hubo_transicion` sobrevive aunque la moda no cambie
 *      (el caso que evita que un cambio de marcha rápido desaparezca),
 *   3. un código sin etiqueta se resuelve al código crudo, marcado como tal.
 */

import { describe, expect, it } from "vitest";

import { ALTO_BANDA_DEFECTO, ANCHO_MARCA_TRANSICION, calcularGeometriaCarril } from "./geometria.ts";
import type { ConfiguracionCarril, CubosEnum } from "./tipos.ts";

function cubos(parcial: {
  t: number[];
  moda: number[];
  huboTransicion?: number[];
  tOrigen?: number;
  factor?: number;
}): CubosEnum {
  return {
    t: Float32Array.from(parcial.t),
    tOrigen: parcial.tOrigen ?? 0,
    moda: Int32Array.from(parcial.moda),
    huboTransicion: Uint8Array.from(parcial.huboTransicion ?? parcial.moda.map(() => 0)),
    factor: parcial.factor ?? 1,
  };
}

function config(parcial: Partial<ConfiguracionCarril> & { cubos: CubosEnum }): ConfiguracionCarril {
  return {
    etiquetas: new Map(),
    vista: { t0: 0, t1: 100 },
    anchoPx: 1000,
    ...parcial,
  };
}

describe("calcularGeometriaCarril — bandas", () => {
  it("cubos vacíos dan un carril sin bandas ni transiciones, sin lanzar", () => {
    const geometria = calcularGeometriaCarril(config({ cubos: cubos({ t: [], moda: [] }) }));
    expect(geometria.bandas).toEqual([]);
    expect(geometria.transiciones).toEqual([]);
  });

  it("un único cubo produce una única banda que cubre todo el ancho", () => {
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0], moda: [3] }) }),
    );
    expect(geometria.bandas).toHaveLength(1);
    expect(geometria.bandas[0]!.codigo).toBe(3);
    expect(geometria.bandas[0]!.xPx).toBe(0);
    expect(geometria.bandas[0]!.anchoPx).toBe(1000);
  });

  it("cubos consecutivos con la misma moda se fusionan en una sola banda", () => {
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0, 25, 50, 75], moda: [2, 2, 2, 2] }) }),
    );
    expect(geometria.bandas).toHaveLength(1);
    expect(geometria.bandas[0]).toMatchObject({ codigo: 2, xPx: 0, anchoPx: 1000 });
  });

  it("un cambio de moda abre una banda nueva exactamente en el límite del cubo", () => {
    // vista 0..100 sobre 1000px: 10 px por segundo de dato.
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0, 50], moda: [1, 2] }) }),
    );
    expect(geometria.bandas).toHaveLength(2);
    expect(geometria.bandas[0]).toMatchObject({ codigo: 1, xPx: 0, anchoPx: 500 });
    expect(geometria.bandas[1]).toMatchObject({ codigo: 2, xPx: 500, anchoPx: 500 });
  });

  it("varias bandas alternadas: cada límite coincide con el cubo que abre la siguiente", () => {
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0, 10, 20, 30, 40], moda: [1, 1, 2, 2, 1] }) }),
    );
    expect(geometria.bandas.map((b) => b.codigo)).toEqual([1, 2, 1]);
    // Los límites de banda son contiguos: el fin de una es el inicio de la siguiente.
    expect(geometria.bandas[0]!.xPx + geometria.bandas[0]!.anchoPx).toBe(geometria.bandas[1]!.xPx);
    expect(geometria.bandas[1]!.xPx + geometria.bandas[1]!.anchoPx).toBe(geometria.bandas[2]!.xPx);
    // Y la última llega hasta el borde del carril.
    expect(geometria.bandas[2]!.xPx + geometria.bandas[2]!.anchoPx).toBe(1000);
  });

  it("respeta `tOrigen`: el instante absoluto es tOrigen + t[i]", () => {
    const geometria = calcularGeometriaCarril(
      config({
        cubos: cubos({ t: [0, 50], moda: [1, 2], tOrigen: 25 }),
        vista: { t0: 25, t1: 125 },
      }),
    );
    // tOrigen=25 + t=[0,50] -> absolutos [25, 75], vista 25..125 sobre 1000px -> 10px/s.
    expect(geometria.bandas[0]).toMatchObject({ xPx: 0, anchoPx: 500 });
    expect(geometria.bandas[1]).toMatchObject({ xPx: 500, anchoPx: 500 });
  });

  it("un rango de vista degenerado (t0 === t1) colapsa al centro en vez de NaN/Infinity", () => {
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0], moda: [1] }), vista: { t0: 10, t1: 10 } }),
    );
    expect(geometria.bandas[0]!.xPx).toBe(500);
    expect(Number.isFinite(geometria.bandas[0]!.xPx)).toBe(true);
  });

  it("usa `altoPx` de la configuración, o el valor por omisión si no se da", () => {
    const base = cubos({ t: [0], moda: [1] });
    expect(calcularGeometriaCarril(config({ cubos: base })).altoPx).toBe(ALTO_BANDA_DEFECTO);
    expect(calcularGeometriaCarril(config({ cubos: base, altoPx: 40 })).altoPx).toBe(40);
  });
});

describe("calcularGeometriaCarril — etiquetas", () => {
  it("un código presente en el diccionario usa su etiqueta y no está marcado como faltante", () => {
    const geometria = calcularGeometriaCarril(
      config({
        cubos: cubos({ t: [0], moda: [3] }),
        etiquetas: new Map([[3, "3ª"]]),
      }),
    );
    expect(geometria.bandas[0]).toMatchObject({ etiqueta: "3ª", etiquetaFaltante: false });
  });

  it("un código ausente del diccionario se enseña como el código crudo, marcado como faltante — nunca en blanco", () => {
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0], moda: [99] }), etiquetas: new Map([[3, "3ª"]]) }),
    );
    expect(geometria.bandas[0]!.etiqueta).toBe("99");
    expect(geometria.bandas[0]!.etiqueta).not.toBe("");
    expect(geometria.bandas[0]!.etiquetaFaltante).toBe(true);
  });

  it("un código negativo ausente también se enseña como su código crudo (Launch Control State)", () => {
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0], moda: [-101] }), etiquetas: new Map() }),
    );
    expect(geometria.bandas[0]!.etiqueta).toBe("-101");
    expect(geometria.bandas[0]!.etiquetaFaltante).toBe(true);
  });

  it("el color es estable por código, no por posición de la banda", () => {
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0, 10, 20], moda: [5, 9, 5] }) }),
    );
    expect(geometria.bandas[0]!.color).toEqual(geometria.bandas[2]!.color);
    expect(geometria.bandas[0]!.color).not.toEqual(geometria.bandas[1]!.color);
  });
});

describe("calcularGeometriaCarril — transiciones", () => {
  it("un cubo con huboTransicion=1 produce una marca; con 0, no produce ninguna", () => {
    const geometria = calcularGeometriaCarril(
      config({
        cubos: cubos({ t: [0, 50], moda: [1, 1], huboTransicion: [0, 1] }),
      }),
    );
    expect(geometria.transiciones).toHaveLength(1);
    expect(geometria.transiciones[0]!.xPx).toBe(500);
  });

  it("la marca de transición SOBREVIVE aunque el cubo se funda en una banda con la misma moda que sus vecinos", () => {
    // Los tres cubos son moda=2 (una sola banda), pero el del medio tuvo
    // huboTransicion=1: por debajo hubo un cambio real que la moda oculta.
    // Es exactamente el caso que evita que "un cambio de marcha rápido
    // desaparezca de la pantalla" (piramide.py, docstring de NivelEnum).
    const geometria = calcularGeometriaCarril(
      config({
        cubos: cubos({ t: [0, 10, 20], moda: [2, 2, 2], huboTransicion: [0, 1, 0] }),
      }),
    );
    expect(geometria.bandas).toHaveLength(1); // una sola banda de color...
    expect(geometria.transiciones).toHaveLength(1); // ...pero la marca no se pierde.
    expect(geometria.transiciones[0]!.xPx).toBe(100); // en el cubo del medio (t=10 -> 100px)
  });

  it("varias transiciones dentro de la misma banda se marcan todas, no solo la primera", () => {
    const geometria = calcularGeometriaCarril(
      config({
        cubos: cubos({ t: [0, 10, 20, 30], moda: [7, 7, 7, 7], huboTransicion: [1, 0, 1, 1] }),
      }),
    );
    expect(geometria.transiciones).toHaveLength(3);
    expect(geometria.transiciones.map((m) => m.xPx)).toEqual([0, 200, 300]);
  });

  it("el ancho de la marca es el fijo por omisión cuando el cubo es ancho", () => {
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0, 50], moda: [1, 1], huboTransicion: [1, 0] }) }),
    );
    expect(geometria.transiciones[0]!.anchoPx).toBe(ANCHO_MARCA_TRANSICION);
  });

  it("el ancho de la marca se recorta si el cubo es más estrecho que el ancho fijo", () => {
    // vista 0..100 sobre 1000px = 10px/s: el cubo del medio (0.1s -> 0.2s)
    // mide 1px de ancho propio, menos que ANCHO_MARCA_TRANSICION (2px).
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0, 0.1, 0.2], moda: [1, 1, 1], huboTransicion: [0, 1, 0] }) }),
    );
    expect(geometria.transiciones[0]!.anchoPx).toBeLessThan(ANCHO_MARCA_TRANSICION);
    expect(geometria.transiciones[0]!.anchoPx).toBeGreaterThanOrEqual(0);
  });

  it("sin ningún hubo_transicion, no hay marcas", () => {
    const geometria = calcularGeometriaCarril(
      config({ cubos: cubos({ t: [0, 10, 20], moda: [1, 2, 3] }) }),
    );
    expect(geometria.transiciones).toEqual([]);
  });
});

describe("calcularGeometriaCarril — validación", () => {
  it("lanza si `moda` no mide lo mismo que `t`", () => {
    const rota: CubosEnum = {
      t: Float32Array.from([0, 10]),
      tOrigen: 0,
      moda: Int32Array.from([1]),
      huboTransicion: Uint8Array.from([0, 0]),
      factor: 1,
    };
    expect(() => calcularGeometriaCarril(config({ cubos: rota }))).toThrow(/moda/);
  });

  it("lanza si `huboTransicion` no mide lo mismo que `t`", () => {
    const rota: CubosEnum = {
      t: Float32Array.from([0, 10]),
      tOrigen: 0,
      moda: Int32Array.from([1, 1]),
      huboTransicion: Uint8Array.from([0]),
      factor: 1,
    };
    expect(() => calcularGeometriaCarril(config({ cubos: rota }))).toThrow(/huboTransicion/);
  });
});
