/**
 * Pruebas de `orden.ts`. Los tres invariantes que decide si el panel sirve
 * (ver el encargo de F3-12), probados sin ningún DOM:
 *
 * 1. Orden por consecuencia, no por tiempo.
 * 2. `construirFilasDeDetector` no confunde «desactivado» con «activo sin
 *    incidencias».
 * 3. `ordenarFilasDeDetector` no revienta con `NaN` cuando dos detectores
 *    activos no tienen ninguna incidencia (el caso más común).
 */

import { describe, expect, it } from "vitest";

import {
  construirFilasDeDetector,
  contarPorSeveridad,
  duracionS,
  instanteDeSalto,
  ordenarFilasDeDetector,
  ordenarPorConsecuencia,
} from "./orden.ts";
import type { DetectorCatalogo, EstadoDetector, IncidenciaPanel } from "./tipos.ts";

function incidencia(parcial: Partial<IncidenciaPanel> & Pick<IncidenciaPanel, "id">): IncidenciaPanel {
  return {
    detectorId: "D1",
    severidad: "media",
    tInicioMs: 0,
    tFinMs: null,
    detalle: {},
    ...parcial,
  };
}

describe("ordenarPorConsecuencia", () => {
  it("una crítica de hace 200 s va antes que una informativa de hace 2 s", () => {
    const tarde = incidencia({ id: "a", severidad: "informativa", tInicioMs: 198_000 });
    const temprana = incidencia({ id: "b", severidad: "critica", tInicioMs: 0 });
    const resultado = ordenarPorConsecuencia([tarde, temprana]);
    expect(resultado.map((i) => i.id)).toEqual(["b", "a"]);
  });

  it("dentro de la misma severidad, ordena por tiempo ascendente", () => {
    const segunda = incidencia({ id: "segunda", severidad: "alta", tInicioMs: 5000 });
    const primera = incidencia({ id: "primera", severidad: "alta", tInicioMs: 1000 });
    const tercera = incidencia({ id: "tercera", severidad: "alta", tInicioMs: 9000 });
    const resultado = ordenarPorConsecuencia([segunda, tercera, primera]);
    expect(resultado.map((i) => i.id)).toEqual(["primera", "segunda", "tercera"]);
  });

  it("no muta el array de entrada", () => {
    const original = [
      incidencia({ id: "a", severidad: "baja", tInicioMs: 10 }),
      incidencia({ id: "b", severidad: "critica", tInicioMs: 5 }),
    ];
    const copia = [...original];
    ordenarPorConsecuencia(original);
    expect(original).toEqual(copia);
  });

  it("las cinco severidades a la vez quedan en orden crítica..informativa", () => {
    const mezcla = [
      incidencia({ id: "informativa", severidad: "informativa", tInicioMs: 0 }),
      incidencia({ id: "baja", severidad: "baja", tInicioMs: 0 }),
      incidencia({ id: "critica", severidad: "critica", tInicioMs: 0 }),
      incidencia({ id: "alta", severidad: "alta", tInicioMs: 0 }),
      incidencia({ id: "media", severidad: "media", tInicioMs: 0 }),
    ];
    const resultado = ordenarPorConsecuencia(mezcla);
    expect(resultado.map((i) => i.id)).toEqual(["critica", "alta", "media", "baja", "informativa"]);
  });
});

describe("duracionS / instanteDeSalto", () => {
  it("una incidencia sin fin da duración null, no cero", () => {
    expect(duracionS(incidencia({ id: "a", tInicioMs: 1000, tFinMs: null }))).toBeNull();
  });

  it("una incidencia de una sola muestra (tFin === tInicio) dura 0 s, no null", () => {
    expect(duracionS(incidencia({ id: "a", tInicioMs: 1000, tFinMs: 1000 }))).toBe(0);
  });

  it("convierte milisegundos a segundos", () => {
    expect(duracionS(incidencia({ id: "a", tInicioMs: 1000, tFinMs: 4500 }))).toBeCloseTo(3.5, 9);
    expect(instanteDeSalto(incidencia({ id: "a", tInicioMs: 12_345 }))).toBeCloseTo(12.345, 9);
  });
});

const CATALOGO: readonly DetectorCatalogo[] = [
  { id: "D4", etiqueta: "Mezcla pobre en carga", severidad: "critica" },
  { id: "D9", etiqueta: "Sobretemperatura de refrigerante", severidad: "alta" },
  { id: "D13", etiqueta: "Protección de motor activa", severidad: "segun_nivel" },
];

describe("construirFilasDeDetector", () => {
  it("un detector desactivado tiene fila con incidencias:[] y estado.activo === false, no ausente", () => {
    const estados: readonly EstadoDetector[] = [
      { detectorId: "D4", activo: false, motivo: "rol lambda_measured por asignación difusa sin confirmar" },
    ];
    const filas = construirFilasDeDetector(CATALOGO, estados, []);
    const filaD4 = filas.find((f) => f.detector.id === "D4");
    expect(filaD4).toBeDefined();
    expect(filaD4?.estado.activo).toBe(false);
    expect(filaD4?.incidencias).toEqual([]);
    expect(filaD4?.resumen.conteo).toBe(0);
  });

  it("un detector desactivado y uno activo sin incidencias tienen el mismo conteo (0) pero estado distinto", () => {
    const estados: readonly EstadoDetector[] = [
      { detectorId: "D4", activo: false, motivo: "asignación difusa sin confirmar" },
    ];
    const filas = construirFilasDeDetector(CATALOGO, estados, []);
    const filaD4 = filas.find((f) => f.detector.id === "D4")!;
    const filaD9 = filas.find((f) => f.detector.id === "D9")!;
    expect(filaD4.resumen.conteo).toBe(filaD9.resumen.conteo); // los dos son 0
    expect(filaD4.estado.activo).toBe(false);
    expect(filaD9.estado.activo).toBe(true); // sin entrada en `estados` => activo
  });

  it("un detector sin entrada en `estados` se trata como activo, no como desactivado", () => {
    const filas = construirFilasDeDetector(CATALOGO, [], []);
    for (const fila of filas) expect(fila.estado.activo).toBe(true);
  });

  it("agrupa las incidencias por su detector, no las mezcla", () => {
    const incidencias = [
      incidencia({ id: "a", detectorId: "D4", severidad: "critica" }),
      incidencia({ id: "b", detectorId: "D4", severidad: "critica" }),
      incidencia({ id: "c", detectorId: "D9", severidad: "alta" }),
    ];
    const filas = construirFilasDeDetector(CATALOGO, [], incidencias);
    expect(filas.find((f) => f.detector.id === "D4")?.resumen.conteo).toBe(2);
    expect(filas.find((f) => f.detector.id === "D9")?.resumen.conteo).toBe(1);
    expect(filas.find((f) => f.detector.id === "D13")?.resumen.conteo).toBe(0);
  });

  it("D13 (severidad de catálogo \"segun_nivel\") produce una fila sin reventar", () => {
    const filas = construirFilasDeDetector(CATALOGO, [], []);
    const filaD13 = filas.find((f) => f.detector.id === "D13");
    expect(filaD13?.detector.severidad).toBe("segun_nivel");
  });

  it("suma la duración total e ignora las incidencias sin fin en la suma", () => {
    const incidencias = [
      incidencia({ id: "a", detectorId: "D9", tInicioMs: 0, tFinMs: 3000 }),
      incidencia({ id: "b", detectorId: "D9", tInicioMs: 0, tFinMs: 2000 }),
      incidencia({ id: "c", detectorId: "D9", tInicioMs: 0, tFinMs: null }),
    ];
    const filas = construirFilasDeDetector(CATALOGO, [], incidencias);
    const filaD9 = filas.find((f) => f.detector.id === "D9")!;
    expect(filaD9.resumen.conteo).toBe(3);
    expect(filaD9.resumen.duracionTotalS).toBeCloseTo(5, 9);
    expect(filaD9.resumen.conIncidenciasSinFin).toBe(true);
  });
});

describe("ordenarFilasDeDetector", () => {
  it("un detector desactivado encabeza el catálogo aunque otro tenga incidencias críticas", () => {
    const estados: readonly EstadoDetector[] = [
      { detectorId: "D9", activo: false, motivo: "roles no confirmados" },
    ];
    const incidencias = [incidencia({ id: "a", detectorId: "D4", severidad: "critica" })];
    const filas = ordenarFilasDeDetector(construirFilasDeDetector(CATALOGO, estados, incidencias));
    expect(filas[0]?.detector.id).toBe("D9");
  });

  it("entre activos, el que tiene la incidencia más grave va primero", () => {
    const incidencias = [
      incidencia({ id: "a", detectorId: "D9", severidad: "baja" }),
      incidencia({ id: "b", detectorId: "D4", severidad: "critica" }),
    ];
    const filas = ordenarFilasDeDetector(construirFilasDeDetector(CATALOGO, [], incidencias));
    expect(filas[0]?.detector.id).toBe("D4");
  });

  it("dos detectores activos sin incidencias no revientan con NaN (Infinity - Infinity)", () => {
    // Ni D9 ni D13 tienen incidencias aquí: las dos filas caen al mismo
    // rango infinito, y el criterio de desempate (etiqueta) tiene que
    // decidir sin que `sort` reciba un comparador que devuelva `NaN`.
    const filas = ordenarFilasDeDetector(construirFilasDeDetector(CATALOGO, [], []));
    expect(filas.map((f) => f.detector.id)).toEqual(
      [...CATALOGO]
        .map((d) => d.id)
        .sort((a, b) => {
          const ea = CATALOGO.find((d) => d.id === a)!.etiqueta;
          const eb = CATALOGO.find((d) => d.id === b)!.etiqueta;
          return ea.localeCompare(eb);
        }),
    );
  });
});

describe("contarPorSeveridad", () => {
  it("cuenta cada severidad por separado, incluidas las que están a cero", () => {
    const incidencias = [
      incidencia({ id: "a", severidad: "critica" }),
      incidencia({ id: "b", severidad: "critica" }),
      incidencia({ id: "c", severidad: "baja" }),
    ];
    const conteo = contarPorSeveridad(incidencias);
    expect(conteo).toEqual({ critica: 2, alta: 0, media: 0, baja: 1, informativa: 0 });
  });

  it("con cero incidencias, las cinco cuentas son cero", () => {
    expect(contarPorSeveridad([])).toEqual({
      critica: 0,
      alta: 0,
      media: 0,
      baja: 0,
      informativa: 0,
    });
  });
});
