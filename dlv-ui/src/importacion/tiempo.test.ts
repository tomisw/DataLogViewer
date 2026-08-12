/**
 * Pruebas de `tiempo.ts`: el resumen en vivo del paso 2 (`docs/07` §7.8).
 */

import { describe, expect, it } from "vitest";

import { calcularResumenTiempo, instanteEnSegundos } from "./tiempo.ts";

describe("instanteEnSegundos", () => {
  it("hora_del_dia: HH:MM:SS.mmm -> segundos desde medianoche", () => {
    expect(
      instanteEnSegundos("18:30:35.506", "hora_del_dia", { decimal: ".", factorASegundos: 1 }),
    ).toBeCloseTo(66635.506, 3);
  });

  it("hora_del_dia rechaza minutos u segundos fuera de rango", () => {
    expect(() =>
      instanteEnSegundos("12:75:00", "hora_del_dia", { decimal: ".", factorASegundos: 1 }),
    ).toThrow(/fuera de rango/);
  });

  it("relativo: segundos crudos, tal cual", () => {
    expect(instanteEnSegundos("0.050", "relativo", { decimal: ".", factorASegundos: 1 })).toBe(0.05);
  });

  it("epoch_milisegundos aplica el factor a segundos", () => {
    expect(
      instanteEnSegundos("1785000635506", "epoch_milisegundos", {
        decimal: ".",
        factorASegundos: 0.001,
      }),
    ).toBeCloseTo(1785000635.506, 3);
  });

  it("contador_de_muestras exige frecuencia declarada", () => {
    expect(() =>
      instanteEnSegundos("3", "contador_de_muestras", { decimal: ".", factorASegundos: 1 }),
    ).toThrow(/frecuencia/);
    expect(
      instanteEnSegundos("3", "contador_de_muestras", {
        decimal: ".",
        factorASegundos: 1,
        frecuenciaHz: 100,
      }),
    ).toBeCloseTo(0.03, 5);
  });

  it("iso8601 vía Date.parse", () => {
    const s = instanteEnSegundos("2026-07-29T18:30:35.506Z", "iso8601", {
      decimal: ".",
      factorASegundos: 1,
    });
    expect(s).toBeCloseTo(Date.parse("2026-07-29T18:30:35.506Z") / 1000, 3);
  });

  it("ausente y fecha_y_hora_separadas no tienen un valor único que interpretar", () => {
    expect(() => instanteEnSegundos("x", "ausente", { decimal: ".", factorASegundos: 1 })).toThrow();
    expect(() =>
      instanteEnSegundos("x", "fecha_y_hora_separadas", { decimal: ".", factorASegundos: 1 }),
    ).toThrow();
  });
});

describe("calcularResumenTiempo", () => {
  it("relativo con paso constante: duración, muestras y tasa sobre la muestra", () => {
    const resumen = calcularResumenTiempo({
      clase: "relativo",
      valoresBrutos: ["0.000", "0.050", "0.100", "0.150"],
      decimal: ".",
    });
    expect(resumen.pasoMedianoS).toBeCloseTo(0.05, 5);
    expect(resumen.frecuenciaHz).toBeCloseTo(20, 5);
    expect(resumen.duracionS).toBeCloseTo(0.15, 5);
    expect(resumen.esEstimacion).toBe(true); // no se dio muestrasTotales
    expect(resumen.avisos).toEqual([]);
  });

  it("con muestrasTotales, la duración es del fichero completo y no es una estimación", () => {
    const resumen = calcularResumenTiempo({
      clase: "relativo",
      valoresBrutos: ["0.000", "0.050", "0.100", "0.150"],
      decimal: ".",
      muestrasTotales: 100000,
    });
    expect(resumen.frecuenciaHz).toBeCloseTo(20, 5);
    // 99999 pasos de 0.05 s
    expect(resumen.duracionS).toBeCloseTo(99999 * 0.05, 3);
    expect(resumen.esEstimacion).toBe(false);
  });

  it("contador_de_muestras sin frecuencia declarada: avisa y no calcula duración", () => {
    const resumen = calcularResumenTiempo({
      clase: "contador_de_muestras",
      valoresBrutos: ["0", "1", "2", "3"],
      decimal: ".",
    });
    expect(resumen.duracionS).toBeNull();
    expect(resumen.pasoMedianoS).toBeNull();
    expect(resumen.avisos[0]).toMatch(/frecuencia de muestreo/);
  });

  it("contador_de_muestras con frecuencia declarada: sí calcula", () => {
    const resumen = calcularResumenTiempo({
      clase: "contador_de_muestras",
      valoresBrutos: ["0", "1", "2", "3"],
      decimal: ".",
      frecuenciaHz: 200,
      muestrasTotales: 4,
    });
    expect(resumen.frecuenciaHz).toBe(200);
    expect(resumen.duracionS).toBeCloseTo(3 / 200, 5);
    expect(resumen.esEstimacion).toBe(false);
  });

  it("hora_del_dia real, con un valor corrupto que se descarta y se avisa", () => {
    const resumen = calcularResumenTiempo({
      clase: "hora_del_dia",
      valoresBrutos: ["18:30:35.000", "18:30:35.050", "25:99:99", "18:30:35.150"],
      decimal: ".",
    });
    expect(resumen.avisos.some((a) => a.includes("no se pudieron interpretar"))).toBe(true);
    // Los 3 valores válidos (con un paso de 0.05 entre los dos primeros, y un
    // salto grande al último tras descartar el corrupto) siguen dando una
    // mediana razonable.
    expect(resumen.pasoMedianoS).not.toBeNull();
  });

  it("un valor absurdo se ve al instante: paso negativo/no creciente se avisa", () => {
    const resumen = calcularResumenTiempo({
      clase: "relativo",
      valoresBrutos: ["0.000", "0.050", "0.040", "0.150"],
      decimal: ".",
    });
    expect(resumen.avisos.some((a) => a.includes("no crecientes"))).toBe(true);
  });
});
