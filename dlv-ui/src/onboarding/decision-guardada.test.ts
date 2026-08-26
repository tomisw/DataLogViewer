/**
 * Pruebas de `decision-guardada.ts` (F5-11, decisión 2 del informe: "no se le
 * puede volver a preguntar lo mismo").
 */

import { describe, expect, it } from "vitest";

import {
  decisionGuardada,
  guardarDecision,
  type EntornoDecisionPerfil,
} from "./decision-guardada.ts";

function almacenFalso(): { getItem(c: string): string | null; setItem(c: string, v: string): void } {
  const contenido = new Map<string, string>();
  return {
    getItem: (c) => contenido.get(c) ?? null,
    setItem: (c, v) => {
      contenido.set(c, v);
    },
  };
}

describe("decisionGuardada / guardarDecision", () => {
  it("nunca se preguntó: no hay decisión guardada", () => {
    const entorno: EntornoDecisionPerfil = { almacen: almacenFalso() };
    expect(decisionGuardada(entorno, "log-1.csv", "Knock")).toBeNull();
  });

  it("guarda la aceptación y la recupera para la MISMA referencia y perfil", () => {
    const entorno: EntornoDecisionPerfil = { almacen: almacenFalso() };
    guardarDecision(entorno, "log-1.csv", "Knock", "aceptada");
    expect(decisionGuardada(entorno, "log-1.csv", "Knock")).toBe("aceptada");
  });

  it("guarda el rechazo igual que la aceptación", () => {
    const entorno: EntornoDecisionPerfil = { almacen: almacenFalso() };
    guardarDecision(entorno, "log-1.csv", "Knock", "descartada");
    expect(decisionGuardada(entorno, "log-1.csv", "Knock")).toBe("descartada");
  });

  it("no se confunde entre dos logs distintos", () => {
    const entorno: EntornoDecisionPerfil = { almacen: almacenFalso() };
    guardarDecision(entorno, "log-1.csv", "Knock", "aceptada");
    expect(decisionGuardada(entorno, "log-2.csv", "Knock")).toBeNull();
  });

  it("no se confunde entre dos perfiles distintos del mismo log", () => {
    const entorno: EntornoDecisionPerfil = { almacen: almacenFalso() };
    guardarDecision(entorno, "log-1.csv", "Knock", "aceptada");
    expect(decisionGuardada(entorno, "log-1.csv", "Lambda")).toBeNull();
  });

  it("sin almacén (entorno sin persistencia): siempre `null`, nunca lanza", () => {
    const entorno: EntornoDecisionPerfil = {};
    expect(() => guardarDecision(entorno, "log-1.csv", "Knock", "aceptada")).not.toThrow();
    expect(decisionGuardada(entorno, "log-1.csv", "Knock")).toBeNull();
  });
});
