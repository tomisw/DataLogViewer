/**
 * Pruebas de `ticks.ts`: la elección de ticks "bonitos".
 *
 * El foco, como pide la tarea, son los rangos raros — muy pequeño, negativo,
 * que cruza el cero, degenerado (`t0 === t1`) — porque son los que producen un
 * eje ilegible o un `NaN` sin que ninguna prueba "del caso normal" lo note.
 */

import { describe, expect, it } from "vitest";

import { pasoBonito, pasoTiempoBonito, ticksTiempo, ticksValor } from "./ticks.ts";

describe("pasoBonito", () => {
  it("redondea al 1/2/5/10 × 10ⁿ más cercano en escala logarítmica", () => {
    expect(pasoBonito(1)).toBe(1);
    expect(pasoBonito(1.3)).toBe(1);
    expect(pasoBonito(1.5)).toBe(2);
    expect(pasoBonito(2)).toBe(2);
    // 3 está más cerca de 2 que de 5 en escala logarítmica (log3-log2 < log5-log3).
    expect(pasoBonito(3)).toBe(2);
    expect(pasoBonito(4)).toBe(5);
    expect(pasoBonito(5)).toBe(5);
    expect(pasoBonito(8)).toBe(10);
    expect(pasoBonito(9.9)).toBe(10);
  });

  it("es invariante a la potencia de diez", () => {
    expect(pasoBonito(0.03)).toBeCloseTo(0.02, 12);
    expect(pasoBonito(300)).toBeCloseTo(200, 12);
    expect(pasoBonito(30_000)).toBeCloseTo(20_000, 12);
  });

  it("rechaza un paso no positivo o no finito en vez de inventar un número", () => {
    expect(() => pasoBonito(0)).toThrow(/positivo/);
    expect(() => pasoBonito(-5)).toThrow(/positivo/);
    expect(() => pasoBonito(Number.NaN)).toThrow(/positivo/);
    expect(() => pasoBonito(Number.POSITIVE_INFINITY)).toThrow(/positivo/);
  });
});

describe("ticksValor", () => {
  it("da un paso 1/2/5×10ⁿ y ticks dentro del rango en el caso normal", () => {
    const { paso, valores } = ticksValor(0, 100, 5);
    expect(paso).toBeCloseTo(20, 12);
    expect(valores).toEqual([0, 20, 40, 60, 80, 100]);
  });

  it("funciona igual con un rango completamente negativo", () => {
    const { valores } = ticksValor(-100, -20, 4);
    for (const v of valores) {
      expect(v).toBeGreaterThanOrEqual(-100);
      expect(v).toBeLessThanOrEqual(-20);
    }
    expect(valores.length).toBeGreaterThan(0);
  });

  it("un rango que cruza el cero incluye el cero sin `-0`", () => {
    const { valores } = ticksValor(-50, 50, 5);
    expect(valores).toContain(0);
    // `Object.is(-0, 0)` es `false`: si se colara un -0 esta prueba lo vería.
    for (const v of valores) expect(Object.is(v, -0)).toBe(false);
  });

  it("un rango muy pequeño no colapsa a un único paso sin decimales", () => {
    const { paso, valores } = ticksValor(0.001, 0.002, 5);
    expect(paso).toBeLessThan(0.001);
    expect(valores.length).toBeGreaterThanOrEqual(2);
    const EPS = 1e-9;
    for (const v of valores) {
      expect(v).toBeGreaterThanOrEqual(0.001 - EPS);
      expect(v).toBeLessThanOrEqual(0.002 + EPS);
    }
  });

  it("un rango degenerado (v0 === v1) da un único tick, no NaN ni excepción", () => {
    const { valores } = ticksValor(42, 42);
    expect(valores).toEqual([42]);
  });

  it("no depende de que v0 < v1: acepta la vista al revés", () => {
    const normal = ticksValor(0, 100, 5);
    const alReves = ticksValor(100, 0, 5);
    expect(alReves.valores).toEqual(normal.valores);
  });

  it("no revienta con un objetivo de ticks absurdo (0 o negativo)", () => {
    expect(() => ticksValor(0, 100, 0)).not.toThrow();
    expect(() => ticksValor(0, 100, -3)).not.toThrow();
  });
});

describe("pasoTiempoBonito", () => {
  it("usa la escala decimal por debajo de 1 s", () => {
    expect(pasoTiempoBonito(0.03)).toBeCloseTo(0.02, 12);
    expect(pasoTiempoBonito(0.2)).toBeCloseTo(0.2, 12);
  });

  it("elige de la tabla de pasos de tiempo entre 1 s y 1 día", () => {
    expect(pasoTiempoBonito(1)).toBe(1);
    expect(pasoTiempoBonito(58)).toBe(60);
    expect(pasoTiempoBonito(3 * 60)).toBe(2 * 60); // más cerca de 2 min que de 5 min
    expect(pasoTiempoBonito(3600)).toBe(3600);
  });

  it("más allá de un día extrapola en múltiplos del propio día", () => {
    const paso = pasoTiempoBonito(10 * 24 * 3600);
    expect(paso % (24 * 3600)).toBe(0);
    expect(paso).toBeGreaterThan(24 * 3600);
  });

  it("rechaza un paso no positivo o no finito", () => {
    expect(() => pasoTiempoBonito(0)).toThrow(/positivo/);
    expect(() => pasoTiempoBonito(Number.NaN)).toThrow(/positivo/);
  });
});

describe("ticksTiempo", () => {
  it("caso normal: un log de media hora da ticks en minutos redondos", () => {
    const { paso, valores } = ticksTiempo(0, 1800, 6);
    expect(paso).toBeGreaterThan(0);
    expect(valores[0]).toBeGreaterThanOrEqual(0);
    expect(valores.at(-1)).toBeLessThanOrEqual(1800);
  });

  it("una ventana de 20 ms a las 8 horas de log sigue dando ticks correctos", () => {
    // El caso límite que describe la tarea: rango minúsculo, magnitud grande.
    const centro = 8 * 3600;
    const { paso, valores } = ticksTiempo(centro, centro + 0.02, 4);
    expect(paso).toBeLessThan(0.02);
    const EPS = 1e-9;
    for (const v of valores) {
      expect(v).toBeGreaterThanOrEqual(centro - EPS);
      expect(v).toBeLessThanOrEqual(centro + 0.02 + EPS);
    }
  });

  it("un rango negativo (tiempo antes de un evento) funciona igual", () => {
    const { valores } = ticksTiempo(-10, 5, 5);
    for (const v of valores) {
      expect(v).toBeGreaterThanOrEqual(-10);
      expect(v).toBeLessThanOrEqual(5);
    }
    expect(valores.some((v) => v < 0)).toBe(true);
  });

  it("un rango degenerado (t0 === t1) da un único tick, no NaN ni excepción", () => {
    const { valores } = ticksTiempo(123.456, 123.456);
    expect(valores).toEqual([123.456]);
  });

  it("no depende de que t0 < t1", () => {
    const normal = ticksTiempo(0, 1800, 6);
    const alReves = ticksTiempo(1800, 0, 6);
    expect(alReves.valores).toEqual(normal.valores);
  });

  it("nunca genera una cantidad de ticks desbocada", () => {
    // Cinturón de seguridad: ni con un objetivo de ticks absurdamente alto.
    const { valores } = ticksTiempo(0, 3600, 100_000);
    expect(valores.length).toBeLessThanOrEqual(1000);
  });
});
