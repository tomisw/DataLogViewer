/**
 * Pruebas de `validarSugerencia` (F5-11): las invariantes de conteo que
 * `contenido.ts` da por hechas antes de construir el texto.
 */

import { describe, expect, it } from "vitest";

import { validarSugerencia, type SugerenciaDePerfil } from "./tipos.ts";

function sugerencia(parcial: Partial<SugerenciaDePerfil> = {}): SugerenciaDePerfil {
  return {
    nombrePerfil: "Knock",
    disponibles: 2,
    total: 3,
    rolesDisponibles: ["a", "b"],
    rolesFaltantes: ["c"],
    ...parcial,
  };
}

describe("validarSugerencia", () => {
  it("acepta una sugerencia consistente", () => {
    expect(() => validarSugerencia(sugerencia())).not.toThrow();
  });

  it("acepta un perfil al 100% (sin roles faltantes)", () => {
    expect(() =>
      validarSugerencia(sugerencia({ disponibles: 3, total: 3, rolesDisponibles: ["a", "b", "c"], rolesFaltantes: [] })),
    ).not.toThrow();
  });

  it("rechaza disponibles negativo", () => {
    expect(() => validarSugerencia(sugerencia({ disponibles: -1 }))).toThrow();
  });

  it("rechaza total negativo", () => {
    expect(() => validarSugerencia(sugerencia({ total: -1 }))).toThrow();
  });

  it("rechaza disponibles > total", () => {
    expect(() => validarSugerencia(sugerencia({ disponibles: 4, total: 3 }))).toThrow();
  });

  it("rechaza rolesDisponibles que no cuadra con disponibles", () => {
    expect(() => validarSugerencia(sugerencia({ rolesDisponibles: ["a"] }))).toThrow();
  });

  it("rechaza rolesFaltantes que no cuadra con total - disponibles", () => {
    expect(() => validarSugerencia(sugerencia({ rolesFaltantes: [] }))).toThrow();
  });
});
