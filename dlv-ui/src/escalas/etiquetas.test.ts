/**
 * Pruebas de `etiquetas.ts`: el texto que hace visible el modo de un eje.
 */

import { describe, expect, it } from "vitest";

import { etiquetaModo, tituloConModo } from "./etiquetas.ts";

describe("etiquetaModo", () => {
  it("distingue los dos modos con palabras distintas", () => {
    expect(etiquetaModo("bloqueado")).toBe("bloqueado");
    expect(etiquetaModo("autoescala")).toBe("autoescala");
    expect(etiquetaModo("bloqueado")).not.toBe(etiquetaModo("autoescala"));
  });
});

describe("tituloConModo", () => {
  it("incluye el modo en el título en los dos sentidos, no solo al bloquear", () => {
    const bloqueado = tituloConModo({ titulo: "RPM", modo: "bloqueado" });
    const autoescala = tituloConModo({ titulo: "RPM", modo: "autoescala" });
    expect(bloqueado).toContain("RPM");
    expect(bloqueado).toContain("bloqueado");
    expect(autoescala).toContain("RPM");
    expect(autoescala).toContain("autoescala");
    // Los dos textos tienen que ser distinguibles: si coincidieran, el
    // bloqueo seguiría siendo invisible aunque el dato `modo` sea correcto.
    expect(bloqueado).not.toBe(autoescala);
  });
});
