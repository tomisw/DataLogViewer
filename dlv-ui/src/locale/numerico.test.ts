/**
 * Pruebas de `numerico.ts`: formateo de números con locale ES/EN.
 *
 * El caso que de verdad importa: en un visor de ECU, 1.234 significa
 * "mil doscientos treinta y cuatro" en ES y "uno coma doscientos treinta
 * y cuatro" en EN. Un número mal interpretado en una tabla de tuning es
 * una decisión de motor mal tomada. Las pruebas lo cubren explícitamente
 * en las dos direcciones.
 */

import { describe, expect, it } from "vitest";

import {
  formatearNumeroConLocale,
  formatearNumeroEN,
  formatearNumeroES,
} from "./numerico.ts";

describe("formatearNumeroConLocale", () => {
  describe("en español (es-ES)", () => {
    it("un número entero con separador decimal desaparece", () => {
      expect(formatearNumeroES(1234, 0)).toBe("1.234");
      expect(formatearNumeroES(42, 0)).toBe("42");
    });

    it("un número con decimales usa coma como separador decimal", () => {
      expect(formatearNumeroES(1.5, 1)).toBe("1,5");
      expect(formatearNumeroES(1234.5, 1)).toBe("1.234,5");
    });

    it("agrupa miles correctamente: punto cada tres dígitos en la parte entera", () => {
      expect(formatearNumeroES(1000, 0)).toBe("1.000");
      expect(formatearNumeroES(1000000, 0)).toBe("1.000.000");
      expect(formatearNumeroES(123456789.12, 2)).toBe("123.456.789,12");
    });

    it("respeta el número de decimales solicitado", () => {
      expect(formatearNumeroES(1.5, 0)).toBe("2"); // redondea
      expect(formatearNumeroES(1.5, 1)).toBe("1,5");
      expect(formatearNumeroES(1.5, 2)).toBe("1,50");
      expect(formatearNumeroES(1.5, 3)).toBe("1,500");
    });

    it("maneja números muy pequeños", () => {
      expect(formatearNumeroES(0.02, 2)).toBe("0,02");
      expect(formatearNumeroES(0.001, 3)).toBe("0,001");
      expect(formatearNumeroES(0.0001, 4)).toBe("0,0001");
    });

    it("maneja números negativos", () => {
      expect(formatearNumeroES(-1.5, 1)).toBe("-1,5");
      expect(formatearNumeroES(-1234.5, 1)).toBe("-1.234,5");
      expect(formatearNumeroES(-123456.78, 2)).toBe("-123.456,78");
    });

    it("cero se formatea correctamente", () => {
      expect(formatearNumeroES(0, 0)).toBe("0");
      expect(formatearNumeroES(0, 1)).toBe("0,0");
      expect(formatearNumeroES(0, 2)).toBe("0,00");
      expect(formatearNumeroES(-0, 1)).toBe("0,0");
    });
  });

  describe("en inglés (en-US)", () => {
    it("un número entero sin separador decimal", () => {
      expect(formatearNumeroEN(1234, 0)).toBe("1,234");
      expect(formatearNumeroEN(42, 0)).toBe("42");
    });

    it("un número con decimales usa punto como separador decimal", () => {
      expect(formatearNumeroEN(1.5, 1)).toBe("1.5");
      expect(formatearNumeroEN(1234.5, 1)).toBe("1,234.5");
    });

    it("agrupa miles correctamente: coma cada tres dígitos en la parte entera", () => {
      expect(formatearNumeroEN(1000, 0)).toBe("1,000");
      expect(formatearNumeroEN(1000000, 0)).toBe("1,000,000");
      expect(formatearNumeroEN(123456789.12, 2)).toBe("123,456,789.12");
    });

    it("respeta el número de decimales solicitado", () => {
      expect(formatearNumeroEN(1.5, 0)).toBe("2"); // redondea
      expect(formatearNumeroEN(1.5, 1)).toBe("1.5");
      expect(formatearNumeroEN(1.5, 2)).toBe("1.50");
      expect(formatearNumeroEN(1.5, 3)).toBe("1.500");
    });

    it("maneja números muy pequeños", () => {
      expect(formatearNumeroEN(0.02, 2)).toBe("0.02");
      expect(formatearNumeroEN(0.001, 3)).toBe("0.001");
      expect(formatearNumeroEN(0.0001, 4)).toBe("0.0001");
    });

    it("maneja números negativos", () => {
      expect(formatearNumeroEN(-1.5, 1)).toBe("-1.5");
      expect(formatearNumeroEN(-1234.5, 1)).toBe("-1,234.5");
      expect(formatearNumeroEN(-123456.78, 2)).toBe("-123,456.78");
    });

    it("cero se formatea correctamente", () => {
      expect(formatearNumeroEN(0, 0)).toBe("0");
      expect(formatearNumeroEN(0, 1)).toBe("0.0");
      expect(formatearNumeroEN(0, 2)).toBe("0.00");
      expect(formatearNumeroEN(-0, 1)).toBe("0.0");
    });
  });

  describe("diferencia crítica entre ES y EN (motor ECU)", () => {
    it("1.234 en ES es mil doscientos treinta y cuatro", () => {
      // En una tabla de tuning, 1234 (milisegundos para inyector, etc.)
      // se escribe en ES como "1.234" (punto como agrupador)
      expect(formatearNumeroES(1234, 0)).toBe("1.234");
    });

    it("1.234 en EN es uno coma doscientos treinta y cuatro", () => {
      // El mismo número en EN se vería como "1,234" (coma como agrupador)
      expect(formatearNumeroEN(1234, 0)).toBe("1,234");
    });

    it("son representaciones distintas del MISMO número", () => {
      const numero = 1234;
      const es = formatearNumeroES(numero, 0);
      const en = formatearNumeroEN(numero, 0);
      // Mismo número, representaciones distintas
      expect(es).toBe("1.234");
      expect(en).toBe("1,234");
      // Un usuario que confunde el formato leeería 1.234 en EN como 1,234...
      // (uno coma doscientos treinta y cuatro = 1.234 decimal), que está MAL.
    });
  });

  describe("parámetro locale explícito", () => {
    it("formatearNumeroConLocale(valor, decimales, 'es') es igual a formatearNumeroES", () => {
      expect(formatearNumeroConLocale(1234.5, 1, "es")).toBe(formatearNumeroES(1234.5, 1));
      expect(formatearNumeroConLocale(42, 0, "es")).toBe(formatearNumeroES(42, 0));
    });

    it("formatearNumeroConLocale(valor, decimales, 'en') es igual a formatearNumeroEN", () => {
      expect(formatearNumeroConLocale(1234.5, 1, "en")).toBe(formatearNumeroEN(1234.5, 1));
      expect(formatearNumeroConLocale(42, 0, "en")).toBe(formatearNumeroEN(42, 0));
    });

    it("el locale por omisión es 'es'", () => {
      expect(formatearNumeroConLocale(1234.5, 1)).toBe(formatearNumeroES(1234.5, 1));
      expect(formatearNumeroConLocale(1234.5, 1)).toBe("1.234,5");
    });
  });
});
