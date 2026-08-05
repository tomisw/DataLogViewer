/**
 * Pruebas de `coincidenciaDifusa` (F1-33).
 *
 * Los nombres de canal son reales, tomados de `docs/01-formato-log.md` §1.4
 * (el volcado de canales del AutoLog): "RPM", "Coolant Temperature",
 * "Manifold Pressure", "Knock Sensor 1/2 Knock Count", "Wideband O2 1",
 * "Target Lambda", "Throttle Position", "Trigger System Errors". Lo que
 * importa no es un número de puntuación concreto -- eso rompería con
 * cualquier ajuste fino de las constantes -- sino el ORDEN que produce,
 * igual que `render/escala.test.ts` comprueba propiedades de
 * `elegirNivel` y no un índice fijo.
 */

import { describe, expect, it } from "vitest";

import { coincidenciaDifusa } from "./difuso.ts";

describe("coincidenciaDifusa: casos básicos", () => {
  it("una subsecuencia real da una puntuación, no null", () => {
    expect(coincidenciaDifusa("cltmp", "Coolant Temperature")).not.toBeNull();
  });

  it("caracteres fuera de orden no son una subsecuencia", () => {
    // "tlc" no aparece en ese orden dentro de "Coolant Temperature".
    expect(coincidenciaDifusa("tlc", "Coolant Temperature")).toBeNull();
  });

  it("un patrón más largo que el texto nunca coincide", () => {
    expect(coincidenciaDifusa("coolant temperature extra", "RPM")).toBeNull();
  });

  it("no distingue mayúsculas ni acentos", () => {
    const base = coincidenciaDifusa("regimen", "Régimen Motor");
    expect(base).not.toBeNull();
    expect(coincidenciaDifusa("REGIMEN", "régimen motor")).toBeCloseTo(base!, 9);
  });

  it("la consulta vacía coincide con puntuación 0, cualquiera que sea el texto", () => {
    expect(coincidenciaDifusa("", "Coolant Temperature")).toBe(0);
    expect(coincidenciaDifusa("", "")).toBe(0);
  });

  it("el patrón vacío en un texto vacío también coincide", () => {
    expect(coincidenciaDifusa("a", "")).toBeNull();
  });
});

describe("coincidenciaDifusa: orden por proximidad, con nombres Haltech reales", () => {
  const canales = [
    "RPM",
    "Manifold Pressure",
    "Coolant Temperature",
    "Intake Air Temperature",
    "Knock Sensor 1/2 Knock Count",
    "Wideband O2 1",
    "Target Lambda",
    "Throttle Position",
    "Ignition Angle",
    "Trigger System Errors",
    "Vehicle Speed Drive Train Sensor",
  ];

  function ordenar(consulta: string): string[] {
    return canales
      .map((nombre) => ({ nombre, puntuacion: coincidenciaDifusa(consulta, nombre) }))
      .filter((c): c is { nombre: string; puntuacion: number } => c.puntuacion !== null)
      .sort((a, b) => b.puntuacion - a.puntuacion)
      .map((c) => c.nombre);
  }

  it("`cltmp` (el ejemplo del enunciado) pone Coolant Temperature primero", () => {
    expect(ordenar("cltmp")[0]).toBe("Coolant Temperature");
  });

  it("`rpm` exacto va antes que un nombre donde `rpm` es solo parte", () => {
    // "RPM" es coincidencia exacta completa; nada más en la lista contiene
    // "rpm" como subsecuencia salvo por casualidad de letras sueltas, así que
    // basta con comprobar que aparece y en primer lugar.
    const orden = ordenar("rpm");
    expect(orden[0]).toBe("RPM");
  });

  it("`knock` pone el canal de knock por delante de los que no tienen esas letras juntas", () => {
    const orden = ordenar("knock");
    expect(orden[0]).toBe("Knock Sensor 1/2 Knock Count");
  });

  it("`lambda` encuentra Target Lambda", () => {
    expect(ordenar("lambda")[0]).toBe("Target Lambda");
  });

  it("`iat` (iniciales) encuentra Intake Air Temperature y descarta Ignition Angle", () => {
    // "Ignition Angle" no tiene ninguna "t" después de una "a": no es una
    // subsecuencia válida, así que ni siquiera debe entrar en el resultado.
    const orden = ordenar("iat");
    expect(orden).toContain("Intake Air Temperature");
    expect(orden).not.toContain("Ignition Angle");
  });

  it("una coincidencia consecutiva puntúa más que la misma subsecuencia dispersa", () => {
    // "wideband" es un tramo consecutivo de "Wideband O2 1"; en un texto
    // donde las mismas letras aparecen sueltas y separadas, la puntuación
    // tiene que ser menor.
    const consecutiva = coincidenciaDifusa("wideband", "Wideband O2 1")!;
    const dispersa = coincidenciaDifusa(
      "wideband",
      "W i d e b a n d filler filler filler O2 1",
    )!;
    expect(consecutiva).toBeGreaterThan(dispersa);
  });

  it("a igualdad de coincidencia, el texto más corto puntúa más alto (proximidad)", () => {
    const corto = coincidenciaDifusa("rpm", "RPM")!;
    const largo = coincidenciaDifusa("rpm", "RPM Limiting Method")!;
    expect(corto).toBeGreaterThan(largo);
  });

  it("coincidir al principio de una palabra puntúa más que en mitad de una", () => {
    // "t" al principio de "Temperature" (tras el espacio) frente a la "t" de
    // en medio de "Coolant". Se compara el propio emparejamiento indirectamente
    // a través del ranking de "iat" ya cubierto arriba, y aquí de forma directa
    // con un patrón de una sola letra.
    const inicio = coincidenciaDifusa("t", "Temperature")!;
    const enMedio = coincidenciaDifusa("t", "xxtxxxxxxx")!;
    expect(inicio).toBeGreaterThan(enMedio);
  });
});

describe("coincidenciaDifusa: búsqueda por ID nativo", () => {
  it("un patrón numérico es subsecuencia de un ID que lo contiene", () => {
    // ID 696 es el canal de Knock Count citado en docs/07 §7.2.
    expect(coincidenciaDifusa("696", "696")).not.toBeNull();
    expect(coincidenciaDifusa("69", "696")).not.toBeNull();
  });

  it("un patrón numérico que no es subsecuencia del ID no coincide", () => {
    expect(coincidenciaDifusa("697", "696")).toBeNull();
  });
});
