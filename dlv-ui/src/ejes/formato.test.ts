/**
 * Pruebas de `formato.ts`: decimales por paso, coma decimal y las tres formas
 * del eje de tiempo (segundos sueltos, `m:ss`, `h:mm:ss`).
 */

import { describe, expect, it } from "vitest";

import { decimalesParaPaso, formatearNumero, formatearTiempo } from "./formato.ts";

describe("decimalesParaPaso", () => {
  it("un paso entero no necesita decimales", () => {
    expect(decimalesParaPaso(5)).toBe(0);
    expect(decimalesParaPaso(20)).toBe(0);
    expect(decimalesParaPaso(500)).toBe(0);
  });

  it("un paso fraccionario necesita tantos decimales como su orden de magnitud", () => {
    expect(decimalesParaPaso(0.5)).toBe(1);
    expect(decimalesParaPaso(0.2)).toBe(1);
    expect(decimalesParaPaso(0.02)).toBe(2);
    expect(decimalesParaPaso(0.0002)).toBe(4);
  });

  it("un paso no positivo o no finito no revienta: da 0 decimales", () => {
    expect(decimalesParaPaso(0)).toBe(0);
    expect(decimalesParaPaso(-1)).toBe(0);
    expect(decimalesParaPaso(Number.NaN)).toBe(0);
  });
});

describe("formatearNumero", () => {
  it("usa coma decimal, no punto", () => {
    expect(formatearNumero(1.5, 1)).toBe("1,5");
    expect(formatearNumero(0.02, 2)).toBe("0,02");
  });

  it("respeta el número de decimales pedido, incluido cero", () => {
    expect(formatearNumero(42, 0)).toBe("42");
    expect(formatearNumero(42.7, 0)).toBe("43");
  });

  it("un negativo que redondea a cero no se muestra como «-0»", () => {
    expect(formatearNumero(-0.0001, 2)).toBe("0,00");
    expect(formatearNumero(-0, 2)).toBe("0,00");
  });

  it("un negativo que no redondea a cero conserva el signo", () => {
    expect(formatearNumero(-12.345, 1)).toBe("-12,3");
  });
});

describe("formatearTiempo", () => {
  it("por debajo de 60 s (magnitud del eje) muestra segundos sueltos", () => {
    expect(formatearTiempo(12.5, 1, 12.5)).toBe("12,5");
    expect(formatearTiempo(0, 0, 12.5)).toBe("0");
    expect(formatearTiempo(-3.2, 1, 12.5)).toBe("-3,2");
  });

  it("entre 60 s y 1 h (magnitud) usa m:ss", () => {
    // 90 s con magnitud de eje 1800 (una vista de media hora) -> 1:30.
    expect(formatearTiempo(90, 0, 1800)).toBe("1:30");
    expect(formatearTiempo(0, 0, 1800)).toBe("0:00");
  });

  it("a partir de 1 h (magnitud) usa h:mm:ss", () => {
    // 1834,7 s ≈ 30 min 34,7 s, con magnitud de eje de varias horas.
    const etiqueta = formatearTiempo(1834.7, 1, 4 * 3600);
    expect(etiqueta).toBe("0:30:34,7");
  });

  it("8 h exactas con magnitud de varias horas", () => {
    expect(formatearTiempo(8 * 3600, 0, 8 * 3600)).toBe("8:00:00");
  });

  it("la magnitud decide el formato de TODOS los ticks del eje, no el valor de cada uno", () => {
    // Una vista que cruza el minuto 1:00 (55 s a 65 s): con magnitud 65 (>= 60),
    // el tick de 55 s se muestra en m:ss igual que el de 65 s, no como "55" suelto.
    const magnitud = 65;
    expect(formatearTiempo(55, 0, magnitud)).toBe("0:55");
    expect(formatearTiempo(65, 0, magnitud)).toBe("1:05");
  });

  it("una ventana de 20 ms a las 8 horas de log se lee con hora absoluta, no en crudo", () => {
    const centro = 8 * 3600;
    const magnitud = centro + 0.02;
    const etiqueta = formatearTiempo(centro, 3, magnitud);
    expect(etiqueta).toBe("8:00:00,000");
    const etiquetaFin = formatearTiempo(centro + 0.02, 3, magnitud);
    expect(etiquetaFin).toBe("8:00:00,020");
  });

  it("un instante negativo (antes del origen) lleva el signo delante", () => {
    expect(formatearTiempo(-90, 0, 1800)).toBe("-1:30");
  });
});
