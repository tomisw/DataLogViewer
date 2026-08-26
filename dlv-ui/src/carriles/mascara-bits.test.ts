/**
 * Pruebas de `mascara-bits.ts` (F3-14): qué bits se enseñan, la geometría
 * apilada pura y el árbol SVG que produce `pintarMascaraBits` con el doble de
 * `dom-falso.ts` (sin navegador, mismo motivo que `carril-estado.test.ts`).
 */

import { describe, expect, it } from "vitest";

import {
  calcularGeometriaMascaraBits,
  filtrarBits,
  pintarMascaraBits,
  textoResumenBitsOcultos,
} from "./mascara-bits.ts";
import type { ConfiguracionMascaraBits, CubosBit } from "./mascara-bits.ts";
import { crearContenedorSvgFalso, crearFabricaSvgFalsa } from "./dom-falso.ts";
import type { CubosEnum } from "./tipos.ts";
import { ALTO_BANDA_DEFECTO } from "./geometria.ts";

function cubosDeBit(parcial: { t: number[]; moda: number[]; huboTransicion?: number[] }): CubosEnum {
  return {
    t: Float32Array.from(parcial.t),
    tOrigen: 0,
    moda: Int32Array.from(parcial.moda),
    huboTransicion: Uint8Array.from(parcial.huboTransicion ?? parcial.moda.map(() => 0)),
    factor: 1,
  };
}

function bit(indice: number, activo: boolean, parcial?: { t: number[]; moda: number[] }): CubosBit {
  return {
    indice,
    activo,
    cubos: cubosDeBit(parcial ?? { t: [0], moda: [activo ? 1 : 0] }),
  };
}

function config(parcial: Partial<ConfiguracionMascaraBits> & { bits: readonly CubosBit[] }): ConfiguracionMascaraBits {
  return {
    vista: { t0: 0, t1: 100 },
    anchoPx: 1000,
    mostrarInactivos: false,
    ...parcial,
  };
}

describe("filtrarBits", () => {
  it("con mostrarInactivos=false, oculta los bits que nunca se activaron", () => {
    const bits = [bit(0, true), bit(1, false), bit(2, false), bit(3, true)];
    const resultado = filtrarBits(bits, { mostrarInactivos: false });

    expect(resultado.visibles.map((b) => b.indice)).toEqual([0, 3]);
    expect(resultado.ocultos).toBe(2);
    expect(resultado.anchura).toBe(4); // decisión 2: la anchura no se recorta
  });

  it("con mostrarInactivos=true, se ven todos y no hay ocultos", () => {
    const bits = [bit(0, true), bit(1, false), bit(2, false)];
    const resultado = filtrarBits(bits, { mostrarInactivos: true });

    expect(resultado.visibles).toHaveLength(3);
    expect(resultado.ocultos).toBe(0);
    expect(resultado.anchura).toBe(3);
  });

  it("un bit nunca activado sigue contando en la anchura aunque esté oculto", () => {
    const bits = [bit(0, false), bit(1, false), bit(2, false)];
    const resultado = filtrarBits(bits, { mostrarInactivos: false });

    expect(resultado.visibles).toEqual([]);
    expect(resultado.ocultos).toBe(3);
    expect(resultado.anchura).toBe(3); // los 3 bits siguen "existiendo"
  });

  it("con todos activos, no se oculta ninguno", () => {
    const bits = [bit(0, true), bit(1, true)];
    const resultado = filtrarBits(bits, { mostrarInactivos: false });
    expect(resultado.visibles).toHaveLength(2);
    expect(resultado.ocultos).toBe(0);
  });
});

describe("textoResumenBitsOcultos", () => {
  it("cadena vacía si no hay ocultos", () => {
    expect(textoResumenBitsOcultos({ visibles: [], ocultos: 0, anchura: 5 }, false)).toBe("");
  });

  it("cadena vacía si mostrarInactivos está activo, aunque hubiera ocultos calculados antes", () => {
    expect(textoResumenBitsOcultos({ visibles: [], ocultos: 3, anchura: 16 }, true)).toBe("");
  });

  it("con ocultos, menciona cuántos de cuántos", () => {
    const texto = textoResumenBitsOcultos({ visibles: [], ocultos: 3, anchura: 16 }, false);
    expect(texto).toMatch(/3/);
    expect(texto).toMatch(/16/);
  });
});

describe("calcularGeometriaMascaraBits", () => {
  it("apila los bits visibles en Y, uno debajo de otro", () => {
    const geometria = calcularGeometriaMascaraBits(
      config({ bits: [bit(0, true), bit(1, true), bit(2, true)] }),
    );

    expect(geometria.carriles).toHaveLength(3);
    expect(geometria.carriles.map((c) => c.yPx)).toEqual([0, ALTO_BANDA_DEFECTO, ALTO_BANDA_DEFECTO * 2]);
    expect(geometria.altoPx).toBe(ALTO_BANDA_DEFECTO * 3);
    expect(geometria.carriles.map((c) => c.indice)).toEqual([0, 1, 2]);
  });

  it("los bits ocultos no ocupan fila: la pila solo mide lo que se ve", () => {
    const geometria = calcularGeometriaMascaraBits(
      config({ bits: [bit(0, true), bit(1, false), bit(2, true)] }),
    );

    expect(geometria.carriles.map((c) => c.indice)).toEqual([0, 2]);
    expect(geometria.altoPx).toBe(ALTO_BANDA_DEFECTO * 2);
    expect(geometria.ocultos).toBe(1);
    expect(geometria.anchura).toBe(3);
  });

  it("con mostrarInactivos, la pila incluye también los bits nunca activados", () => {
    const geometria = calcularGeometriaMascaraBits(
      config({ bits: [bit(0, true), bit(1, false)], mostrarInactivos: true }),
    );
    expect(geometria.carriles).toHaveLength(2);
    expect(geometria.ocultos).toBe(0);
  });

  it("sin ningún bit visible, la pila queda vacía sin lanzar", () => {
    const geometria = calcularGeometriaMascaraBits(config({ bits: [bit(0, false), bit(1, false)] }));
    expect(geometria.carriles).toEqual([]);
    expect(geometria.altoPx).toBe(0);
  });

  it("respeta `altoPorBitPx`", () => {
    const geometria = calcularGeometriaMascaraBits(
      config({ bits: [bit(0, true), bit(1, true)], altoPorBitPx: 10 }),
    );
    expect(geometria.carriles.map((c) => c.yPx)).toEqual([0, 10]);
    expect(geometria.altoPx).toBe(20);
  });

  it("cada carril trae la geometría real de sus bandas (reutiliza calcularGeometriaCarril)", () => {
    const geometria = calcularGeometriaMascaraBits(
      config({ bits: [bit(0, true, { t: [0, 50], moda: [0, 1] })] }),
    );
    expect(geometria.carriles[0]!.geometria.bandas).toHaveLength(2);
  });
});

describe("pintarMascaraBits", () => {
  it("dimensiona el svg exterior según los bits VISIBLES, no la anchura total", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarMascaraBits(svg, fabrica, config({ bits: [bit(0, true), bit(1, false), bit(2, true)] }));

    expect(svg.atributos.get("height")).toBe(String(ALTO_BANDA_DEFECTO * 2));
    expect(svg.hijos).toHaveLength(2); // solo los 2 bits activos
  });

  it("cada fila es un grupo con la etiqueta de índice y un <svg> anidado con el carril", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarMascaraBits(svg, fabrica, config({ bits: [bit(5, true)] }));

    const fila = svg.hijos[0]!;
    expect(fila.etiquetaTag).toBe("g");
    expect(fila.clases).toContain("dlv-mascara-bits-fila");
    expect(fila.hijos.map((h) => h.etiquetaTag)).toEqual(["text", "svg"]);

    const etiqueta = fila.hijos[0]!;
    expect(etiqueta.textContent).toMatch(/5/); // "bit 5": el índice, nunca un nombre inventado

    const svgBit = fila.hijos[1]!;
    expect(svgBit.clases).toContain("dlv-mascara-bits-carril");
    // El <svg> anidado trae EXACTAMENTE el árbol que pinta pintarCarril (F3-13): [gBandas, gTransiciones].
    expect(svgBit.hijos.map((h) => h.etiquetaTag)).toEqual(["g", "g"]);
    expect(svgBit.hijos[0]!.clases).toContain("dlv-carril-bandas");
  });

  it("un bit oculto no aparece en el árbol, aunque exista en la configuración", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarMascaraBits(svg, fabrica, config({ bits: [bit(0, false)] }));

    expect(svg.hijos).toEqual([]);
  });

  it("mostrarInactivos=true vuelve a pintar los bits ocultos", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarMascaraBits(svg, fabrica, config({ bits: [bit(0, false), bit(1, true)], mostrarInactivos: true }));

    expect(svg.hijos).toHaveLength(2);
  });

  it("las filas se apilan verticalmente con una transformación translate", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarMascaraBits(svg, fabrica, config({ bits: [bit(0, true), bit(1, true)] }));

    expect(svg.hijos[0]!.atributos.get("transform")).toBe("translate(0, 0)");
    expect(svg.hijos[1]!.atributos.get("transform")).toBe(`translate(0, ${ALTO_BANDA_DEFECTO})`);
  });

  it("un pulso de una sola muestra en un bit sigue produciendo una banda encendida (no desaparece)", () => {
    // Simula lo que ya garantiza el OR de NivelBits (piramide.py): al nivel
    // decimado, el cubo que contenía el pulso decodifica a moda=1 entero.
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    const unBit = bit(2, true, { t: [0, 25, 50, 75], moda: [0, 1, 0, 0] });
    pintarMascaraBits(svg, fabrica, config({ bits: [unBit] }));

    const svgBit = svg.hijos[0]!.hijos[1]!;
    const grupoBandas = svgBit.hijos[0]!;
    // 3 bandas: 0, 1, 0 -- el pulso del medio no se funde ni desaparece.
    expect(grupoBandas.hijos.filter((h) => h.etiquetaTag === "rect")).toHaveLength(3);
  });

  it("repintar reemplaza el árbol anterior en vez de acumularlo", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarMascaraBits(svg, fabrica, config({ bits: [bit(0, true), bit(1, true), bit(2, true)] }));
    pintarMascaraBits(svg, fabrica, config({ bits: [bit(0, true)] }));

    expect(svg.hijos).toHaveLength(1);
  });

  it("devuelve la GeometriaMascaraBits coherente con lo pintado", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    const geometria = pintarMascaraBits(svg, fabrica, config({ bits: [bit(0, true), bit(1, true)] }));

    expect(geometria.carriles).toHaveLength(2);
    expect(geometria.altoPx).toBe(ALTO_BANDA_DEFECTO * 2);
  });

  it("sin ningún bit, no lanza y deja el svg sin hijos", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarMascaraBits(svg, fabrica, config({ bits: [] }));
    expect(svg.hijos).toEqual([]);
    expect(svg.atributos.get("height")).toBe("0");
  });
});
