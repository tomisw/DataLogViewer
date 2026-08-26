/**
 * Pruebas de la política de edición por origen (F3-05, decisión 3). Ver la
 * cabecera de `permisos.ts` para las tres opciones consideradas y por qué se
 * eligió "bloquear y ofrecer duplicar".
 */

import { describe, expect, it } from "vitest";

import { puedeEditarDirectamente, puedeSobrescribir } from "./permisos.ts";

describe("puedeEditarDirectamente", () => {
  it("un perfil de fábrica no se edita en el sitio", () => {
    expect(puedeEditarDirectamente("fabrica")).toBe(false);
  });

  it("un perfil de usuario sí se edita en el sitio", () => {
    expect(puedeEditarDirectamente("usuario")).toBe(true);
  });
});

describe("puedeSobrescribir", () => {
  it("un perfil de fábrica no se sobrescribe: guardar es siempre 'guardar como'", () => {
    expect(puedeSobrescribir("fabrica")).toBe(false);
  });

  it("un perfil de usuario se sobrescribe en su propio sitio", () => {
    expect(puedeSobrescribir("usuario")).toBe(true);
  });

  it("las dos políticas coinciden siempre (misma protección vista dos veces)", () => {
    for (const origen of ["fabrica", "usuario"] as const) {
      expect(puedeSobrescribir(origen)).toBe(puedeEditarDirectamente(origen));
    }
  });
});
