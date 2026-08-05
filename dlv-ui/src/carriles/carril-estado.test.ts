/**
 * Pruebas de `pintarCarril`: qué árbol SVG construye, con el doble de
 * `dom-falso.ts` (sin navegador — ver la cabecera de `dom.ts`).
 *
 * `geometria.test.ts` ya prueba la aritmética a fondo; aquí lo que importa es
 * que esos números lleguen al nodo correcto con la clase correcta —en
 * particular las dos propiedades que un test de geometría pura no puede
 * atrapar: que un código sin etiqueta lleva la clase que lo marca como tal
 * (no solo el texto), y que la marca de transición no lleva `fill` inline
 * (es puramente semántica, la restila el CSS de tema).
 */

import { describe, expect, it } from "vitest";

import { pintarCarril } from "./carril-estado.ts";
import { crearContenedorSvgFalso, crearFabricaSvgFalsa } from "./dom-falso.ts";
import type { ConfiguracionCarril, CubosEnum } from "./tipos.ts";

function cubos(parcial: {
  t: number[];
  moda: number[];
  huboTransicion?: number[];
}): CubosEnum {
  return {
    t: Float32Array.from(parcial.t),
    tOrigen: 0,
    moda: Int32Array.from(parcial.moda),
    huboTransicion: Uint8Array.from(parcial.huboTransicion ?? parcial.moda.map(() => 0)),
    factor: 1,
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

describe("pintarCarril", () => {
  it("dimensiona el svg y le cuelga dos grupos: bandas y transiciones", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarCarril(svg, fabrica, config({ cubos: cubos({ t: [0], moda: [1] }) }));

    expect(svg.atributos.get("width")).toBe("1000");
    expect(svg.atributos.get("height")).toBe("24"); // ALTO_BANDA_DEFECTO
    expect(svg.atributos.get("viewBox")).toBe("0 0 1000 24");
    expect(svg.hijos.map((h) => h.etiquetaTag)).toEqual(["g", "g"]);
    expect(svg.hijos[0]!.clases).toContain("dlv-carril-bandas");
    expect(svg.hijos[1]!.clases).toContain("dlv-carril-transiciones");
  });

  it("una banda es un rect con su color y un text con su etiqueta", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarCarril(
      svg,
      fabrica,
      config({ cubos: cubos({ t: [0], moda: [3] }), etiquetas: new Map([[3, "3ª"]]) }),
    );

    const grupoBandas = svg.hijos[0]!;
    expect(grupoBandas.hijos.map((h) => h.etiquetaTag)).toEqual(["rect", "text"]);

    const rect = grupoBandas.hijos[0]!;
    expect(rect.clases).toContain("dlv-carril-banda");
    expect(rect.clases).not.toContain("dlv-carril-banda--sin-etiqueta");
    expect(rect.atributos.get("fill")).toMatch(/^rgba\(/);
    expect(rect.atributos.get("width")).toBe("1000");

    const texto = grupoBandas.hijos[1]!;
    expect(texto.clases).toContain("dlv-carril-etiqueta");
    expect(texto.clases).not.toContain("dlv-carril-etiqueta--sin-etiqueta");
    expect(texto.textContent).toBe("3ª");
  });

  it("un código sin etiqueta se ve como el código crudo, con la clase que marca que falta — nunca en blanco", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarCarril(svg, fabrica, config({ cubos: cubos({ t: [0], moda: [42] }) }));

    const grupoBandas = svg.hijos[0]!;
    const rect = grupoBandas.hijos[0]!;
    const texto = grupoBandas.hijos[1]!;

    expect(texto.textContent).toBe("42");
    expect(texto.textContent).not.toBe("");
    expect(texto.clases).toContain("dlv-carril-etiqueta--sin-etiqueta");
    expect(rect.clases).toContain("dlv-carril-banda--sin-etiqueta");
  });

  it("las marcas de transición son rects sin fill, con la clase semántica (la restila el tema)", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarCarril(
      svg,
      fabrica,
      config({ cubos: cubos({ t: [0, 50], moda: [1, 1], huboTransicion: [0, 1] }) }),
    );

    const grupoTransiciones = svg.hijos[1]!;
    expect(grupoTransiciones.hijos).toHaveLength(1);
    const marca = grupoTransiciones.hijos[0]!;
    expect(marca.etiquetaTag).toBe("rect");
    expect(marca.clases).toEqual(["dlv-carril-transicion"]);
    expect(marca.atributos.has("fill")).toBe(false);
  });

  it("una transición dentro de una banda fusionada sigue produciendo su marca", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarCarril(
      svg,
      fabrica,
      config({
        cubos: cubos({ t: [0, 10, 20], moda: [2, 2, 2], huboTransicion: [0, 1, 0] }),
      }),
    );

    const grupoBandas = svg.hijos[0]!;
    // Una sola banda de color (mismos rect+text que un único código)...
    expect(grupoBandas.hijos.map((h) => h.etiquetaTag)).toEqual(["rect", "text"]);
    // ...pero la marca del cubo del medio no desaparece.
    const grupoTransiciones = svg.hijos[1]!;
    expect(grupoTransiciones.hijos).toHaveLength(1);
  });

  it("repintar reemplaza el árbol anterior en vez de acumularlo", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarCarril(svg, fabrica, config({ cubos: cubos({ t: [0, 10], moda: [1, 2] }) }));
    pintarCarril(svg, fabrica, config({ cubos: cubos({ t: [0], moda: [1] }) }));

    expect(svg.hijos).toHaveLength(2); // sigue siendo [grupoBandas, grupoTransiciones]
    expect(svg.hijos[0]!.hijos).toHaveLength(2); // una banda (rect+text), no las dos anteriores
  });

  it("devuelve la GeometriaCarril calculada, coherente con lo pintado", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    const geometria = pintarCarril(
      svg,
      fabrica,
      config({ cubos: cubos({ t: [0, 50], moda: [1, 2] }) }),
    );

    expect(geometria.bandas).toHaveLength(2);
    expect(svg.hijos[0]!.hijos).toHaveLength(4); // 2 bandas x (rect + text)
  });

  it("un carril sin cubos no pinta ninguna banda ni marca", () => {
    const svg = crearContenedorSvgFalso();
    const fabrica = crearFabricaSvgFalsa();
    pintarCarril(svg, fabrica, config({ cubos: cubos({ t: [], moda: [] }) }));

    expect(svg.hijos[0]!.hijos).toEqual([]);
    expect(svg.hijos[1]!.hijos).toEqual([]);
  });
});
