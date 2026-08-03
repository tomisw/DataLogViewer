/**
 * Pruebas de `asignacion.ts`: a qué panel apunta un punto del puntero, y qué
 * pasa exactamente con la lista de canales de origen y destino al mover uno.
 */

import { describe, expect, it } from "vitest";

import { indiceDeCanal, moverCanal, panelEnY, type PanelRect } from "./asignacion.ts";
import type { CanalEnPanel } from "./tipos.ts";

const canal = (id: string): CanalEnPanel => ({ id, etiqueta: id });

describe("panelEnY", () => {
  const paneles: PanelRect[] = [
    { id: "sup", rect: { top: 0, bottom: 100 } },
    { id: "medio", rect: { top: 100, bottom: 250 } },
    { id: "inf", rect: { top: 250, bottom: 400 } },
  ];

  it("encuentra el panel que contiene la coordenada", () => {
    expect(panelEnY(paneles, 50)).toBe("sup");
    expect(panelEnY(paneles, 150)).toBe("medio");
    expect(panelEnY(paneles, 399)).toBe("inf");
  });

  it("el borde compartido entre dos paneles pertenece al de abajo, nunca a los dos", () => {
    expect(panelEnY(paneles, 100)).toBe("medio");
    expect(panelEnY(paneles, 250)).toBe("inf");
  });

  it("fuera de todos los rectángulos da null", () => {
    expect(panelEnY(paneles, -10)).toBeNull();
    expect(panelEnY(paneles, 500)).toBeNull();
  });

  it("lista vacía siempre da null", () => {
    expect(panelEnY([], 50)).toBeNull();
  });
});

describe("moverCanal", () => {
  function asignacionesIniciales(): Map<string, readonly CanalEnPanel[]> {
    return new Map([
      ["p1", [canal("rpm"), canal("map")]],
      ["p2", [canal("tps")]],
    ]);
  }

  it("quita el canal de origen y lo añade al final del destino por omisión", () => {
    const resultado = moverCanal(asignacionesIniciales(), "map", "p1", "p2");
    expect(resultado.get("p1")?.map((c) => c.id)).toEqual(["rpm"]);
    expect(resultado.get("p2")?.map((c) => c.id)).toEqual(["tps", "map"]);
  });

  it("inserta en el índice pedido, no siempre al final", () => {
    const resultado = moverCanal(asignacionesIniciales(), "map", "p1", "p2", 0);
    expect(resultado.get("p2")?.map((c) => c.id)).toEqual(["map", "tps"]);
  });

  it("mover al mismo panel reordena en vez de duplicar", () => {
    const resultado = moverCanal(asignacionesIniciales(), "map", "p1", "p1", 0);
    expect(resultado.get("p1")?.map((c) => c.id)).toEqual(["map", "rpm"]);
    expect(resultado.get("p1")?.length).toBe(2);
  });

  it("no muta el mapa de entrada", () => {
    const original = asignacionesIniciales();
    const antes = original.get("p1")?.map((c) => c.id);
    moverCanal(original, "map", "p1", "p2");
    expect(original.get("p1")?.map((c) => c.id)).toEqual(antes);
  });

  it("lanza si el canal no está en el panel de origen declarado", () => {
    expect(() => moverCanal(asignacionesIniciales(), "map", "p2", "p1")).toThrow();
  });

  it("lanza si el panel de origen o destino no existe", () => {
    expect(() => moverCanal(asignacionesIniciales(), "map", "fantasma", "p2")).toThrow();
    expect(() => moverCanal(asignacionesIniciales(), "map", "p1", "fantasma")).toThrow();
  });
});

describe("indiceDeCanal", () => {
  it("devuelve la posición del canal en el panel", () => {
    const asignaciones = new Map([["p1", [canal("rpm"), canal("map")]]]);
    expect(indiceDeCanal(asignaciones, "p1", "map")).toBe(1);
  });

  it("devuelve -1 si el canal no está, o si el panel no existe", () => {
    const asignaciones = new Map([["p1", [canal("rpm")]]]);
    expect(indiceDeCanal(asignaciones, "p1", "tps")).toBe(-1);
    expect(indiceDeCanal(asignaciones, "fantasma", "rpm")).toBe(-1);
  });
});
