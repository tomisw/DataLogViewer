/**
 * Pruebas del historial de navegación (F1-28).
 *
 * La que de verdad protege el requisito de la tarea es «una ráfaga de
 * eventos rápidos es un solo paso»: sin ella, un historial correcto en el
 * papel sería inutilizable en la práctica (pulsar deshacer 40 veces para
 * volver al principio de un solo gesto de rueda).
 */

import { describe, expect, it } from "vitest";

import { HistorialDeVista } from "./historial.ts";
import type { Vista } from "../render/tipos.ts";

function vista(t0: number): Vista {
  return { t0, t1: t0 + 10, v0: 0, v1: 1 };
}

describe("agrupación de gestos", () => {
  it("una ráfaga de eventos separados por menos del umbral es un solo paso", () => {
    const h = new HistorialDeVista(vista(0), { umbralGestoMs: 400 });
    let t = 0;
    for (let i = 1; i <= 40; i += 1) {
      t += 5; // muy por debajo de los 400 ms del umbral
      h.registrar(vista(i), t);
    }
    expect(h.actual).toEqual(vista(40));
    expect(h.puedeDeshacer).toBe(true);
    h.deshacer();
    // Un solo deshacer basta para volver al principio: los 40 eventos eran un paso.
    expect(h.actual).toEqual(vista(0));
    expect(h.puedeDeshacer).toBe(false);
  });

  it("una pausa más larga que el umbral abre un paso nuevo", () => {
    const h = new HistorialDeVista(vista(0), { umbralGestoMs: 100 });
    h.registrar(vista(1), 0);
    h.registrar(vista(2), 500); // 500 ms > 100 ms de umbral: gesto nuevo
    expect(h.actual).toEqual(vista(2));
    h.deshacer();
    expect(h.actual).toEqual(vista(1));
    h.deshacer();
    expect(h.actual).toEqual(vista(0));
    expect(h.puedeDeshacer).toBe(false);
  });
});

describe("deshacer / rehacer", () => {
  it("deshacer y rehacer se quedan quietos en los extremos, sin lanzar", () => {
    const h = new HistorialDeVista(vista(0));
    expect(h.deshacer()).toEqual(vista(0));
    expect(h.puedeDeshacer).toBe(false);

    h.registrar(vista(1), 0);
    h.deshacer();
    expect(h.puedeRehacer).toBe(true);
    expect(h.rehacer()).toEqual(vista(1));
    expect(h.rehacer()).toEqual(vista(1)); // ya no hay más que rehacer
    expect(h.puedeRehacer).toBe(false);
  });

  it("registrar después de deshacer descarta el rehacer pendiente", () => {
    const h = new HistorialDeVista(vista(0), { umbralGestoMs: 50 });
    h.registrar(vista(1), 0);
    h.registrar(vista(2), 1000);
    h.deshacer(); // vuelve a vista(1); vista(2) queda como "rehacer"
    expect(h.puedeRehacer).toBe(true);

    h.registrar(vista(3), 2000);
    expect(h.actual).toEqual(vista(3));
    expect(h.puedeRehacer).toBe(false);
    expect(h.rehacer()).toEqual(vista(3)); // vista(2) ya no es alcanzable
  });
});

describe("tope de pasos", () => {
  it("olvida el paso más antiguo al superar maxPasos", () => {
    const h = new HistorialDeVista(vista(0), { maxPasos: 3, umbralGestoMs: 50 });
    h.registrar(vista(1), 0);
    h.registrar(vista(2), 1000);
    h.registrar(vista(3), 2000); // cuatro candidatos (0..3), tope 3: se olvida vista(0)

    h.deshacer();
    h.deshacer();
    expect(h.actual).toEqual(vista(1));
    expect(h.puedeDeshacer).toBe(false); // vista(0) ya no está
  });

  it("`maxPasos` menor que 1 se rechaza al construir", () => {
    expect(() => new HistorialDeVista(vista(0), { maxPasos: 0 })).toThrow(/al menos 1/);
  });
});
