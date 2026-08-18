/**
 * Pruebas de `severidad.ts`. El invariante que importa: el orden es
 * exactamente el de `dlv_core.plausibilidad.SEVERIDADES` (crítica > alta >
 * media > baja > informativa), y la marca de severidad no depende de ningún
 * literal de color.
 */

import { describe, expect, it } from "vitest";

import {
  compararSeveridad,
  etiquetaDeSeveridad,
  etiquetaDeSeveridadCatalogo,
  marcaDeSeveridad,
  rangoDeSeveridad,
} from "./severidad.ts";
import { SEVERIDADES_CONCRETAS } from "./tipos.ts";

describe("rangoDeSeveridad / compararSeveridad", () => {
  it("crítica es la más grave y informativa la menos, en ese orden exacto", () => {
    expect(rangoDeSeveridad("critica")).toBe(0);
    expect(rangoDeSeveridad("alta")).toBe(1);
    expect(rangoDeSeveridad("media")).toBe(2);
    expect(rangoDeSeveridad("baja")).toBe(3);
    expect(rangoDeSeveridad("informativa")).toBe(4);
  });

  it("compararSeveridad ordena crítica antes que informativa, sin mirar el tiempo", () => {
    expect(compararSeveridad("critica", "informativa")).toBeLessThan(0);
    expect(compararSeveridad("informativa", "critica")).toBeGreaterThan(0);
    expect(compararSeveridad("media", "media")).toBe(0);
  });

  it("las cinco severidades declaradas tienen rango único y contiguo (0..4)", () => {
    const rangos = [...SEVERIDADES_CONCRETAS.map(rangoDeSeveridad)].sort((a, b) => a - b);
    expect(rangos).toEqual([0, 1, 2, 3, 4]);
  });
});

describe("etiquetaDeSeveridad / etiquetaDeSeveridadCatalogo", () => {
  it("capitaliza el literal tal cual, sin tabla de traducción aparte", () => {
    expect(etiquetaDeSeveridad("critica")).toBe("Critica");
    expect(etiquetaDeSeveridad("informativa")).toBe("Informativa");
  });

  it("D13 (\"segun_nivel\") tiene su propia etiqueta y no rompe la capitalización de las otras", () => {
    expect(etiquetaDeSeveridadCatalogo("segun_nivel")).toBe("Según nivel");
    expect(etiquetaDeSeveridadCatalogo("critica")).toBe(etiquetaDeSeveridad("critica"));
  });
});

describe("marcaDeSeveridad", () => {
  it("crítica llena las 5 marcas; informativa llena solo 1", () => {
    expect(marcaDeSeveridad("critica")).toEqual({ llenos: 5, total: 5 });
    expect(marcaDeSeveridad("informativa")).toEqual({ llenos: 1, total: 5 });
  });

  it("el número de marcas llenas decrece exactamente al pasar a la siguiente severidad", () => {
    const llenos = SEVERIDADES_CONCRETAS.map((s) => marcaDeSeveridad(s).llenos);
    expect(llenos).toEqual([5, 4, 3, 2, 1]);
  });
});
