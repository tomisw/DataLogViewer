/**
 * Pruebas de `GestorEscalas`: ejes múltiples, autoescala y bloqueo (F1-27).
 *
 * El foco es lo que pide la tarea de forma explícita: que `vistaPorSerie`
 * produzca lo que espera `Renderizador.dibujar`, que bloquear congele el
 * rango frente a datos nuevos, y los dos casos degenerados (canal constante,
 * canal todo nulo) sin que ninguno produzca una `Vista` con `v0 === v1`.
 */

import { describe, expect, it } from "vitest";

import { GestorEscalas } from "./gestor.ts";

describe("crearEje / asignarSerie", () => {
  it("rechaza crear dos ejes con el mismo id", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm");
    expect(() => gestor.crearEje("rpm", "rpm")).toThrow(/ya existe/);
  });

  it("rechaza asignar una serie a un eje que no existe", () => {
    const gestor = new GestorEscalas();
    expect(() => gestor.asignarSerie("motor.rpm", "rpm")).toThrow(/no existe/);
  });

  it("un eje nuevo empieza en autoescala y con el rango por omisión con margen", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm");
    const eje = gestor.eje("rpm");
    expect(eje.modo).toBe("autoescala");
    expect(eje.rango.max).toBeGreaterThan(eje.rango.min);
  });

  it("el título por omisión es la propia unidad", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm");
    expect(gestor.eje("rpm").titulo).toBe("rpm");
  });
});

describe("actualizar — autoescala", () => {
  it("combina el rango visible de varias series del mismo eje", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("presion", "bar", { fraccionMargen: 0 });
    gestor.asignarSerie("motor.presionAceite", "presion");
    gestor.asignarSerie("motor.presionCombustible", "presion");

    gestor.actualizar(
      new Map([
        ["motor.presionAceite", { min: 1, max: 5 }],
        ["motor.presionCombustible", { min: 2, max: 8 }],
      ]),
    );

    const eje = gestor.eje("presion");
    expect(eje.rango).toEqual({ min: 1, max: 8 });
  });

  it("recalcula cada vez que se llama, siguiendo el rango visible actual", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm", { fraccionMargen: 0 });
    gestor.asignarSerie("motor.rpm", "rpm");

    gestor.actualizar(new Map([["motor.rpm", { min: 800, max: 3000 }]]));
    expect(gestor.eje("rpm").rango).toEqual({ min: 800, max: 3000 });

    gestor.actualizar(new Map([["motor.rpm", { min: 5000, max: 7000 }]]));
    expect(gestor.eje("rpm").rango).toEqual({ min: 5000, max: 7000 });
  });

  it("una serie ausente del mapa de `actualizar` cuenta como sin datos, no como error", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm", { fraccionMargen: 0 });
    gestor.asignarSerie("motor.rpm", "rpm");
    expect(() => gestor.actualizar(new Map())).not.toThrow();
  });
});

describe("actualizar — caso degenerado: canal constante", () => {
  it("un canal constante produce un rango con ancho positivo, no v0 === v1", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("temp", "°C");
    gestor.asignarSerie("motor.temp", "temp");

    gestor.actualizar(new Map([["motor.temp", { min: 90, max: 90 }]]));

    const eje = gestor.eje("temp");
    expect(eje.rango.max).toBeGreaterThan(eje.rango.min);
  });
});

describe("actualizar — caso degenerado: canal todo nulo", () => {
  it("un eje sin ningún dato visible conserva su último rango bueno", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm", { fraccionMargen: 0 });
    gestor.asignarSerie("motor.rpm", "rpm");

    gestor.actualizar(new Map([["motor.rpm", { min: 1000, max: 2000 }]]));
    const antes = gestor.eje("rpm").rango;

    // El canal se queda sin datos visibles (todo nulo en la ventana actual).
    gestor.actualizar(new Map([["motor.rpm", null]]));
    const despues = gestor.eje("rpm").rango;

    expect(despues).toEqual(antes);
  });

  it("un eje que nunca tuvo datos válidos se queda en su rango por omisión, con ancho positivo", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm");
    gestor.asignarSerie("motor.rpm", "rpm");

    gestor.actualizar(new Map([["motor.rpm", null]]));

    const eje = gestor.eje("rpm");
    expect(eje.rango.max).toBeGreaterThan(eje.rango.min);
    expect(Number.isFinite(eje.rango.min)).toBe(true);
    expect(Number.isFinite(eje.rango.max)).toBe(true);
  });
});

describe("bloquear / desbloquear / alternarBloqueo", () => {
  it("bloquear congela el rango: actualizar ya no lo toca", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm", { fraccionMargen: 0 });
    gestor.asignarSerie("motor.rpm", "rpm");
    gestor.actualizar(new Map([["motor.rpm", { min: 1000, max: 2000 }]]));

    gestor.bloquear("rpm");
    gestor.actualizar(new Map([["motor.rpm", { min: 5000, max: 9000 }]]));

    expect(gestor.eje("rpm").rango).toEqual({ min: 1000, max: 2000 });
    expect(gestor.eje("rpm").modo).toBe("bloqueado");
  });

  it("bloquear con un rango explícito lo fija a ESE rango, con margen", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm", { fraccionMargen: 0.1 });
    gestor.asignarSerie("motor.rpm", "rpm");

    gestor.bloquear("rpm", { min: 0, max: 100 });

    expect(gestor.eje("rpm").rango).toEqual({ min: -10, max: 110 });
  });

  it("desbloquear vuelve a dejar que actualizar reescale", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm", { fraccionMargen: 0 });
    gestor.asignarSerie("motor.rpm", "rpm");
    gestor.bloquear("rpm", { min: 0, max: 100 });

    gestor.desbloquear("rpm");
    gestor.actualizar(new Map([["motor.rpm", { min: 500, max: 700 }]]));

    expect(gestor.eje("rpm").modo).toBe("autoescala");
    expect(gestor.eje("rpm").rango).toEqual({ min: 500, max: 700 });
  });

  it("alternarBloqueo cambia de autoescala a bloqueado y viceversa", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm");
    expect(gestor.eje("rpm").modo).toBe("autoescala");
    gestor.alternarBloqueo("rpm");
    expect(gestor.eje("rpm").modo).toBe("bloqueado");
    gestor.alternarBloqueo("rpm");
    expect(gestor.eje("rpm").modo).toBe("autoescala");
  });

  it("lanza sobre un eje que no existe, en las tres operaciones", () => {
    const gestor = new GestorEscalas();
    expect(() => gestor.bloquear("no-existe")).toThrow(/no existe/);
    expect(() => gestor.desbloquear("no-existe")).toThrow(/no existe/);
    expect(() => gestor.alternarBloqueo("no-existe")).toThrow(/no existe/);
  });
});

describe("vistaPorSerie", () => {
  it("produce una Vista por serie con el t0/t1 compartido y el v0/v1 de su eje", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm", { fraccionMargen: 0 });
    gestor.crearEje("temp", "°C", { fraccionMargen: 0 });
    gestor.asignarSerie("motor.rpm", "rpm");
    gestor.asignarSerie("motor.temp", "temp");
    gestor.actualizar(
      new Map([
        ["motor.rpm", { min: 800, max: 7000 }],
        ["motor.temp", { min: 60, max: 105 }],
      ]),
    );

    const vistas = gestor.vistaPorSerie({ t0: 10, t1: 20 });

    expect(vistas.get("motor.rpm")).toEqual({ t0: 10, t1: 20, v0: 800, v1: 7000 });
    expect(vistas.get("motor.temp")).toEqual({ t0: 10, t1: 20, v0: 60, v1: 105 });
  });

  it("dos series en el MISMO eje comparten exactamente el mismo v0/v1", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("presion", "bar", { fraccionMargen: 0 });
    gestor.asignarSerie("a", "presion");
    gestor.asignarSerie("b", "presion");
    gestor.actualizar(new Map([["a", { min: 0, max: 3 }]]));

    const vistas = gestor.vistaPorSerie({ t0: 0, t1: 1 });
    expect(vistas.get("a")).toEqual(vistas.get("b"));
  });

  it("una serie sin eje asignado no aparece en el mapa", () => {
    const gestor = new GestorEscalas();
    const vistas = gestor.vistaPorSerie({ t0: 0, t1: 1 });
    expect(vistas.has("nadie-la-asigno")).toBe(false);
    expect(vistas.size).toBe(0);
  });

  it("ningún eje bloqueado en cero produce v0 === v1 en la Vista resultante", () => {
    // Comprobación de extremo a extremo del requisito de la tarea: el rango
    // cero de un canal constante nunca debe llegar así de lejos.
    const gestor = new GestorEscalas();
    gestor.crearEje("temp", "°C");
    gestor.asignarSerie("motor.temp", "temp");
    gestor.actualizar(new Map([["motor.temp", { min: 0, max: 0 }]]));

    const vista = gestor.vistaPorSerie({ t0: 0, t1: 1 }).get("motor.temp")!;
    expect(vista.v1).not.toBe(vista.v0);
  });
});

describe("ejes (getter)", () => {
  it("enumera todos los ejes dados de alta", () => {
    const gestor = new GestorEscalas();
    gestor.crearEje("rpm", "rpm");
    gestor.crearEje("temp", "°C");
    expect(gestor.ejes.map((e) => e.id).sort()).toEqual(["rpm", "temp"]);
  });
});
