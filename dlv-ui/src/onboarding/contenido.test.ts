/**
 * Pruebas de `contenido.ts`: puras, sin `document` (F5-11).
 *
 * Las tres decisiones del encargo, comprobadas aquí porque son texto y
 * aritmética, no DOM:
 *  1. `sugerencia === null` sigue produciendo un texto que decir (nunca "").
 *  2. `tieneAcciones` es la única señal que decide si hay botones -- y solo es
 *     `true` cuando SÍ hubo sugerencia.
 *  3. La cobertura ("N de M") siempre aparece; los roles que faltan solo si
 *     falta alguno.
 */

import { describe, expect, it } from "vitest";

import { contenidoDePropuesta } from "./contenido.ts";
import type { SugerenciaDePerfil } from "./tipos.ts";

function sugerencia(parcial: Partial<SugerenciaDePerfil> = {}): SugerenciaDePerfil {
  return {
    nombrePerfil: "Knock",
    disponibles: 7,
    total: 9,
    rolesDisponibles: ["engine_speed", "knock_level", "lambda_measured", "manifold_pressure", "coolant_temp", "oil_pressure", "ignition_advance"],
    rolesFaltantes: ["boost_pressure_actual", "injector_duty"],
    ...parcial,
  };
}

describe("contenidoDePropuesta", () => {
  it("sin sugerencia: hay texto y no hay acciones (decisión 1 del informe)", () => {
    const contenido = contenidoDePropuesta(null);
    expect(contenido.textoPrincipal).not.toBe("");
    expect(contenido.textoPrincipal).toMatch(/ning[uú]n perfil/i);
    expect(contenido.textoFaltan).toBeNull();
    expect(contenido.tieneAcciones).toBe(false);
  });

  it("con sugerencia: enseña la cifra de cobertura literal de E4.5", () => {
    const contenido = contenidoDePropuesta(sugerencia({ nombrePerfil: "Knock", disponibles: 7, total: 9 }));
    expect(contenido.textoPrincipal).toContain("Knock");
    expect(contenido.textoPrincipal).toContain("7");
    expect(contenido.textoPrincipal).toContain("9");
    expect(contenido.tieneAcciones).toBe(true);
  });

  it("lista los roles que faltan, no solo cuántos", () => {
    const contenido = contenidoDePropuesta(
      sugerencia({ rolesFaltantes: ["boost_pressure_actual", "injector_duty"] }),
    );
    expect(contenido.textoFaltan).toContain("boost_pressure_actual");
    expect(contenido.textoFaltan).toContain("injector_duty");
  });

  it("perfil al 100%: no hay nada que listar", () => {
    const contenido = contenidoDePropuesta(
      sugerencia({ disponibles: 9, total: 9, rolesDisponibles: Array.from({ length: 9 }, (_, i) => `rol${i}`), rolesFaltantes: [] }),
    );
    expect(contenido.textoFaltan).toBeNull();
  });

  it("rechaza una sugerencia con conteos inconsistentes en vez de pintar un número inventado", () => {
    expect(() =>
      contenidoDePropuesta(sugerencia({ disponibles: 7, total: 9, rolesDisponibles: ["solo-uno"] })),
    ).toThrow();
  });
});
