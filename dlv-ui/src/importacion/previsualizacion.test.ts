/**
 * Pruebas de `previsualizacion.ts`: la conversión de la tabla del paso 3, la
 * clase "punto" explícita, y las dos reglas duras de la tarea — hueco nunca
 * es 0, y sin dimensión resuelta se muestra en crudo (`docs/07` §7.15).
 */

import { describe, expect, it } from "vitest";

import type { Conversion } from "../unidades/conversion.ts";
import { celdaMostrada, filaMostrada, type ConversionDeColumna } from "./previsualizacion.ts";
import type { CeldaPrevia } from "./tipos.ts";

// Espejo de las unidades reales de `data/units.toml` para temperatura:
// canónica en K. °C: mostrado = canonica - 273.15. °F: mostrado = canonica *
// 9/5 - 459.67.
const CELSIUS: Conversion = { tipo: "afin", a: 1, b: -273.15 };
const FAHRENHEIT: Conversion = { tipo: "afin", a: 9 / 5, b: -459.67 };
const KELVIN: Conversion = { tipo: "afin", a: 1, b: 0 };

function numero(valor: number): CeldaPrevia {
  return { tipo: "numero", texto: String(valor), valor };
}

describe("celdaMostrada: la regla de las celdas vacías", () => {
  it("un hueco se muestra como hueco, nunca como 0", () => {
    const resultado = celdaMostrada(
      { tipo: "hueco" },
      { conversionDeOrigen: CELSIUS, conversionDeMostrada: CELSIUS, decimales: 1 },
    );
    expect(resultado.esHueco).toBe(true);
    expect(resultado.texto).toBe("");
  });

  it("un texto libre (enum) pasa sin conversión", () => {
    const resultado = celdaMostrada(
      { tipo: "texto", texto: "Idle" },
      { conversionDeOrigen: null, conversionDeMostrada: null, decimales: 0 },
    );
    expect(resultado.texto).toBe("Idle");
    expect(resultado.esCrudo).toBe(false);
  });
});

describe("celdaMostrada: conversión de unidad, siempre como clase punto", () => {
  it("92.4 en la columna de origen ya en °C, mostrada en °C: no cambia", () => {
    const resultado = celdaMostrada(numero(92.4), {
      conversionDeOrigen: CELSIUS,
      conversionDeMostrada: CELSIUS,
      decimales: 1,
    } satisfies ConversionDeColumna);
    expect(resultado.texto).toBe("92,4");
  });

  it("una columna declarada en °F se convierte a °C a través de la canónica (K)", () => {
    // 212 °F = 373,15 K = 100 °C.
    const resultado = celdaMostrada(numero(212), {
      conversionDeOrigen: FAHRENHEIT,
      conversionDeMostrada: CELSIUS,
      decimales: 1,
    });
    expect(resultado.texto).toBe("100,0");
  });

  it("dos logs con el mismo rol y unidades de origen distintas se superponen en canónica (docs/07 §7.11)", () => {
    // 100 °C y 212 °F son la misma temperatura: al convertir los dos a K
    // (canónica) tienen que coincidir exactamente.
    const enCelsius = celdaMostrada(numero(100), {
      conversionDeOrigen: CELSIUS,
      conversionDeMostrada: KELVIN,
      decimales: 4,
    });
    const enFahrenheit = celdaMostrada(numero(212), {
      conversionDeOrigen: FAHRENHEIT,
      conversionDeMostrada: KELVIN,
      decimales: 4,
    });
    expect(enCelsius.texto).toBe(enFahrenheit.texto);
  });

  it("sin dimensión resuelta, se muestra en crudo y marcado como tal (docs/07 §7.15 mitigación 3)", () => {
    const resultado = celdaMostrada(numero(4731), {
      conversionDeOrigen: null,
      conversionDeMostrada: null,
      decimales: 0,
    });
    expect(resultado.esCrudo).toBe(true);
    expect(resultado.texto).toBe("4731");
  });
});

describe("celdaMostrada: informe de plausibilidad (docs/07 §7.7 punto 2)", () => {
  it("un valor fuera del rango canónico declarado se marca sospechoso", () => {
    // Rango plausible del rol coolant_temp: 233,15–423,15 K (-40 a 150 °C).
    // Una columna mal mapeada en °F que en realidad trae 92,4 (grados, no °F
    // de refrigerante) da una canónica absurdamente alta si se lee como °F.
    const resultado = celdaMostrada(
      numero(920),
      { conversionDeOrigen: FAHRENHEIT, conversionDeMostrada: CELSIUS, decimales: 1 },
      { rango: { min: 233.15, max: 423.15 } },
    );
    expect(resultado.esSospechosa).toBe(true);
  });

  it("un valor dentro de rango no se marca", () => {
    const resultado = celdaMostrada(
      numero(90),
      { conversionDeOrigen: CELSIUS, conversionDeMostrada: CELSIUS, decimales: 1 },
      { rango: { min: 233.15, max: 423.15 } },
    );
    expect(resultado.esSospechosa).toBe(false);
  });

  it("sin rango declarado, nada se marca sospechoso", () => {
    const resultado = celdaMostrada(numero(99999), {
      conversionDeOrigen: CELSIUS,
      conversionDeMostrada: CELSIUS,
      decimales: 1,
    });
    expect(resultado.esSospechosa).toBe(false);
  });
});

describe("filaMostrada", () => {
  it("aplica la conversión de cada columna de forma independiente, huecos incluidos", () => {
    const fila: CeldaPrevia[] = [numero(0.05), { tipo: "hueco" }, numero(212)];
    const conversiones: ConversionDeColumna[] = [
      { conversionDeOrigen: KELVIN, conversionDeMostrada: KELVIN, decimales: 3 },
      { conversionDeOrigen: CELSIUS, conversionDeMostrada: CELSIUS, decimales: 1 },
      { conversionDeOrigen: FAHRENHEIT, conversionDeMostrada: CELSIUS, decimales: 1 },
    ];
    const mostrada = filaMostrada(fila, conversiones);
    expect(mostrada[0]!.texto).toBe("0,050");
    expect(mostrada[1]!.esHueco).toBe(true);
    expect(mostrada[2]!.texto).toBe("100,0");
  });
});
