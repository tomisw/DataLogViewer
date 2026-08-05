import { describe, expect, it } from "vitest";

import {
  elegirProtagonistas,
  rolFiable,
  tieneSenal,
  type CanalCandidato,
} from "./protagonistas.ts";

function canal(
  idNativo: string,
  rol: string | null = null,
  extra: Partial<CanalCandidato> = {},
): CanalCandidato {
  return {
    idNativo,
    rol,
    confianzaRol: rol === null ? null : "EXACTA",
    clasificacion: { vacio: false, constante: false },
    ...extra,
  };
}

/**
 * Los ocho primeros canales de un `AutoLog` de Haltech, tal como los devuelve
 * `/comandos/abrir-log` sobre `samples/real/AutoLog_20260729_1830.csv`: puros
 * diagnósticos de arranque, tres de ellos constantes (comprobado contra el
 * log real). Es el caso que hacía parecer vacía la aplicación.
 */
const CABECERA_HALTECH_REAL: CanalCandidato[] = [
  canal("14210", null, { clasificacion: { vacio: false, constante: true } }), // Bootmode Reason
  canal("13", null, { clasificacion: { vacio: false, constante: true } }), // Reset Required
  canal("23", null, { clasificacion: { vacio: false, constante: true } }), // Memory Writes Pending
  canal("5267"), // Diagnostic ratiometric voltage reference error
  canal("5268"), // Diagnostic absolute voltage reference error
  canal("5269"), // Diagnostic absolute-ratiometric discrepancy
  canal("6278"), // Diagnostic Analogue 5V rail
  canal("5841"), // Engine State
];

const ORDEN = ["engine_speed", "manifold_pressure", "coolant_temp"];

describe("elegir los canales con los que abrir un log", () => {
  it("prefiere los roles pedidos aunque estén al final del fichero", () => {
    const canales = [
      ...CABECERA_HALTECH_REAL,
      canal("100", "coolant_temp"),
      canal("101", "engine_speed"),
      canal("102", "manifold_pressure"),
    ];

    expect(elegirProtagonistas(canales, ORDEN, 3)).toEqual(["101", "102", "100"]);
  });

  it("respeta el orden de preferencia, no el orden del fichero", () => {
    const canales = [canal("a", "coolant_temp"), canal("b", "engine_speed")];
    expect(elegirProtagonistas(canales, ORDEN, 2)).toEqual(["b", "a"]);
  });

  it("no marca canales constantes ni vacíos", () => {
    const canales = [
      canal("plano", "engine_speed", { clasificacion: { vacio: false, constante: true } }),
      canal("sinDatos", "manifold_pressure", { clasificacion: { vacio: true, constante: false } }),
      canal("bueno", "coolant_temp"),
    ];
    expect(elegirProtagonistas(canales, ORDEN, 8)).toEqual(["bueno"]);
  });

  it("descarta un rol DIFUSO para protagonista, pero no el canal", () => {
    // El canal sigue estando disponible por el repliegue (es la única entrada
    // con señal): lo que no se acepta es CREERLE el rol. Ver `rolFiable`.
    const canales = [canal("dudoso", "engine_speed", { confianzaRol: "DIFUSA" })];
    expect(rolFiable(canales[0]!)).toBeNull();
    expect(elegirProtagonistas(canales, ORDEN, 8)).toEqual(["dudoso"]);
  });

  it("acepta INDEXADA: «Injector 3 Duty Cycle» es una coincidencia, no un parecido", () => {
    const canales = [canal("inj", "engine_speed", { confianzaRol: "INDEXADA" })];
    expect(rolFiable(canales[0]!)).toBe("engine_speed");
  });

  it("coge UN canal por rol y no los ocho inyectores", () => {
    const canales = [
      canal("inj1", "injector_duty"),
      canal("inj2", "injector_duty"),
      canal("inj3", "injector_duty"),
      canal("rpm", "engine_speed"),
    ];
    expect(elegirProtagonistas(canales, ["injector_duty", "engine_speed"], 4)).toEqual([
      "inj1",
      "rpm",
      "inj2",
      "inj3",
    ]);
  });

  it("nunca devuelve más de `maximo`", () => {
    const canales = Array.from({ length: 40 }, (_, i) => canal(`c${i}`));
    expect(elegirProtagonistas(canales, ORDEN, 8)).toHaveLength(8);
  });

  it("no repite un canal que ya entró por su rol", () => {
    const canales = [canal("rpm", "engine_speed"), canal("otro")];
    expect(elegirProtagonistas(canales, ORDEN, 8)).toEqual(["rpm", "otro"]);
  });

  describe("el repliegue, que es lo que evita la ventana en blanco", () => {
    it("sin ningún rol reconocido, marca los primeros canales CON SEÑAL", () => {
      // Un CSV genérico cuyos nombres no reconoce el catálogo de roles. Sin
      // repliegue esto devolvería [] y la ventana saldría vacía.
      expect(elegirProtagonistas(CABECERA_HALTECH_REAL, ORDEN, 4)).toEqual([
        "5267",
        "5268",
        "5269",
        "6278",
      ]);
    });

    it("un log entero de canales planos devuelve la lista vacía, sin inventar", () => {
      const planos = [
        canal("a", null, { clasificacion: { vacio: false, constante: true } }),
        canal("b", null, { clasificacion: { vacio: true, constante: false } }),
      ];
      expect(planos.some(tieneSenal)).toBe(false);
      expect(elegirProtagonistas(planos, ORDEN, 8)).toEqual([]);
    });

    it("una lista vacía no revienta", () => {
      expect(elegirProtagonistas([], ORDEN, 8)).toEqual([]);
    });
  });
});
