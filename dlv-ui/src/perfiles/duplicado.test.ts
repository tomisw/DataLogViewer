/**
 * Pruebas de duplicar perfil (F3-05, decisión 1). Ver la cabecera de
 * `duplicado.ts` para el porqué de que "crear" y "duplicar" sean la misma
 * operación en este editor.
 */

import { describe, expect, it } from "vitest";

import { construirElementoDePanel, construirPanel, construirPerfil } from "./perfil.ts";
import { duplicarPerfil, sugerirNombreDuplicado } from "./duplicado.ts";

function perfilDePrueba(nombre: string) {
  return construirPerfil({
    nombre,
    descripcion: "de fábrica",
    paneles: [construirPanel({ titulo: "P", elementos: [construirElementoDePanel({ rol: "engine_rpm", requerido: true })] })],
  });
}

describe("sugerirNombreDuplicado", () => {
  it("la primera copia no lleva número", () => {
    expect(sugerirNombreDuplicado("Circuito", [])).toBe("Circuito (copia)");
  });

  it("evita colisionar con un nombre ya existente", () => {
    expect(sugerirNombreDuplicado("Circuito", ["Circuito (copia)"])).toBe("Circuito (copia 2)");
  });

  it("sigue incrementando hasta encontrar hueco", () => {
    const existentes = ["Circuito (copia)", "Circuito (copia 2)", "Circuito (copia 3)"];
    expect(sugerirNombreDuplicado("Circuito", existentes)).toBe("Circuito (copia 4)");
  });

  it("acepta un Set además de un array", () => {
    expect(sugerirNombreDuplicado("Circuito", new Set(["Circuito (copia)"]))).toBe("Circuito (copia 2)");
  });
});

describe("duplicarPerfil", () => {
  it("produce un nombre distinto y conserva el resto del contenido", () => {
    const original = perfilDePrueba("Knock");
    const copia = duplicarPerfil(original, [original.nombre]);
    expect(copia.nombre).toBe("Knock (copia)");
    expect(copia.paneles).toEqual(original.paneles);
    expect(copia.limites).toEqual(original.limites);
    expect(copia.unidades).toEqual(original.unidades);
  });

  it("nunca coincide con un nombre ya existente, aunque haya varias copias", () => {
    const original = perfilDePrueba("Knock");
    const nombres = new Set([original.nombre, "Knock (copia)", "Knock (copia 2)"]);
    const copia = duplicarPerfil(original, nombres);
    expect(copia.nombre).toBe("Knock (copia 3)");
    expect(nombres.has(copia.nombre)).toBe(false);
  });

  it("respeta un nombre sugerido por el usuario si no colisiona", () => {
    const original = perfilDePrueba("Knock");
    const copia = duplicarPerfil(original, [original.nombre], "Mi Knock");
    expect(copia.nombre).toBe("Mi Knock");
  });

  it("si el nombre sugerido por el usuario colisiona, cae al derivado automáticamente", () => {
    const original = perfilDePrueba("Knock");
    const copia = duplicarPerfil(original, [original.nombre, "Mi Knock"], "Mi Knock");
    expect(copia.nombre).toBe("Knock (copia)");
  });

  it("el duplicado es un Perfil válido por derecho propio (pasa construirPerfil)", () => {
    const original = perfilDePrueba("Knock");
    // Si duplicarPerfil no re-validara, un perfil corrupto se propagaría sin darse cuenta.
    expect(() => duplicarPerfil(original, [])).not.toThrow();
  });
});
