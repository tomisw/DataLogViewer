/**
 * Pruebas de `filtrarCanales` (F1-33): identidad en capas (ADR-008) y
 * ocultación de inactivos (F1-07).
 */

import { describe, expect, it } from "vitest";

import { filtrarCanales } from "./filtro.ts";
import type { CanalInfo, ClasificacionCanal } from "./tipos.ts";

function clasificacion(parcial: Partial<ClasificacionCanal> = {}): ClasificacionCanal {
  return { vacio: false, constante: false, ...parcial };
}

function canal(parcial: Partial<CanalInfo> & { idNativo: string; nombre: string }): CanalInfo {
  return {
    formato: "haltech_nsp",
    rol: null,
    clasificacion: clasificacion(),
    ...parcial,
  };
}

// Un puñado de canales reales del AutoLog (docs/01 §1.4 / §1.3), más un rol
// asignado a mano en dos de ellos para poder probar la búsqueda por rol.
const CANALES: CanalInfo[] = [
  canal({ idNativo: "3", nombre: "RPM", rol: "engine_speed" }),
  canal({ idNativo: "12", nombre: "Coolant Temperature", rol: "coolant_temp" }),
  canal({ idNativo: "45", nombre: "Manifold Pressure" }),
  canal({
    idNativo: "696",
    nombre: "Knock Sensor 1/2 Knock Count",
    rol: "knock_count",
  }),
  canal({
    idNativo: "88",
    nombre: "Boost Control State",
    clasificacion: clasificacion({ constante: true }),
  }),
  canal({
    idNativo: "91",
    nombre: "Launch Control State",
    clasificacion: clasificacion({ vacio: true }),
  }),
];

describe("filtrarCanales: sin consulta", () => {
  it("sin consulta ni mostrarInactivos, oculta constante y vacío pero cuenta ambos", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "", mostrarInactivos: false });
    const nombres = resultado.visibles.map((f) => f.canal.nombre);
    expect(nombres).not.toContain("Boost Control State");
    expect(nombres).not.toContain("Launch Control State");
    expect(nombres).toHaveLength(4);
    expect(resultado.ocultos).toEqual({ constante: 1, vacio: 1 });
  });

  it("con mostrarInactivos, aparecen todos y ocultos queda a cero", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "", mostrarInactivos: true });
    expect(resultado.visibles).toHaveLength(CANALES.length);
    expect(resultado.ocultos).toEqual({ constante: 0, vacio: 0 });
  });

  it("los canales mostrados por el toggle llevan su motivo, no null", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "", mostrarInactivos: true });
    const boost = resultado.visibles.find((f) => f.canal.nombre === "Boost Control State")!;
    const launch = resultado.visibles.find((f) => f.canal.nombre === "Launch Control State")!;
    expect(boost.motivoInactivo).toBe("constante");
    expect(launch.motivoInactivo).toBe("vacio");
  });

  it("un canal activo lleva motivoInactivo null", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "", mostrarInactivos: true });
    const rpm = resultado.visibles.find((f) => f.canal.nombre === "RPM")!;
    expect(rpm.motivoInactivo).toBeNull();
  });

  it("sin consulta, la puntuación es null (no hay relevancia que ordenar)", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "", mostrarInactivos: false });
    expect(resultado.visibles.every((f) => f.puntuacion === null)).toBe(true);
  });
});

describe("filtrarCanales: identidad en capas (ADR-008)", () => {
  it("busca por nombre", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "cltmp", mostrarInactivos: false });
    expect(resultado.visibles[0]!.canal.nombre).toBe("Coolant Temperature");
  });

  it("busca por rol semántico, aunque el nombre nativo no lo diga", () => {
    // Quien piensa en roles busca "coolant_temp" literalmente, no el nombre
    // Haltech: docs/07 §7.11, la identidad en capas existe justo para esto.
    const resultado = filtrarCanales(CANALES, {
      consulta: "coolant_temp",
      mostrarInactivos: false,
    });
    expect(resultado.visibles.map((f) => f.canal.nombre)).toContain("Coolant Temperature");
  });

  it("busca por ID nativo", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "696", mostrarInactivos: false });
    expect(resultado.visibles.map((f) => f.canal.idNativo)).toContain("696");
  });

  it("un canal sin rol asignado no revienta la búsqueda por rol de otros", () => {
    // "Manifold Pressure" tiene `rol: null`; buscar un rol no debe lanzar.
    expect(() =>
      filtrarCanales(CANALES, { consulta: "engine_speed", mostrarInactivos: false }),
    ).not.toThrow();
  });

  it("una consulta que no coincide con ningún campo no devuelve nada", () => {
    const resultado = filtrarCanales(CANALES, {
      consulta: "zzzzzznoexiste",
      mostrarInactivos: true,
    });
    expect(resultado.visibles).toHaveLength(0);
  });
});

describe("filtrarCanales: consulta + ocultación combinadas", () => {
  it("un canal inactivo que coincide con la búsqueda se cuenta como oculto, no como 'no encontrado'", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "boost", mostrarInactivos: false });
    expect(resultado.visibles).toHaveLength(0);
    expect(resultado.ocultos).toEqual({ constante: 1, vacio: 0 });
  });

  it("el mismo canal aparece si se activa mostrarInactivos", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "boost", mostrarInactivos: true });
    expect(resultado.visibles.map((f) => f.canal.nombre)).toEqual(["Boost Control State"]);
  });

  it("con consulta, el orden es por puntuación descendente", () => {
    const resultado = filtrarCanales(CANALES, { consulta: "temperature", mostrarInactivos: false });
    const puntuaciones = resultado.visibles.map((f) => f.puntuacion!);
    const ordenadas = [...puntuaciones].sort((a, b) => b - a);
    expect(puntuaciones).toEqual(ordenadas);
  });
});

describe("filtrarCanales: rendimiento no cuadrático", () => {
  it("475 canales (el tamaño real del AutoLog) se filtran sin problema por pulsación", () => {
    const muchos: CanalInfo[] = Array.from({ length: 475 }, (_, i) =>
      canal({ idNativo: String(i), nombre: `Canal Genérico ${i}`, rol: i % 7 === 0 ? "engine_speed" : null }),
    );
    const inicio = performance.now();
    for (const letra of "cltmp") {
      filtrarCanales(muchos, { consulta: letra, mostrarInactivos: false });
    }
    const duracion = performance.now() - inicio;
    // Umbral generoso a propósito: esto no es un banco de rendimiento (eso
    // es `*.banco.test.ts`, con `npm run banco`), es una red de seguridad
    // contra una regresión que convirtiera el filtrado en O(n²).
    expect(duracion).toBeLessThan(500);
  });
});
