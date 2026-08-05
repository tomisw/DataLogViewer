/**
 * Pruebas de la precedencia del factor de estequiometría (λ → AFR).
 *
 * Es el riesgo real de este componente, tal y como lo fijó el propietario: el
 * usuario gana siempre que elige; si no, se lee del log; si el log no lo trae,
 * se asume gasolina y ESO se distingue de un dato real. Sin esta precedencia
 * exacta, un log de E85 sin el canal de estequiometría podría acabar
 * mostrando un AFR calculado con 14,7 sin que nadie lo note.
 */

import { describe, expect, it } from "vitest";

import { catalogoDeCombustiblesDePrueba } from "./fixtures-catalogo.ts";
import {
  analizarEstequiometriaTecleada,
  buscarCombustible,
  combustiblePorOmision,
  ErrorDeCombustible,
  explicacionDeOrigen,
  resolverFactorEstequiometrico,
} from "./resolucion.ts";
import { OrigenFactor } from "./tipos.ts";

describe("resolverFactorEstequiometrico: precedencia usuario > log > supuesto", () => {
  const catalogo = catalogoDeCombustiblesDePrueba();

  it("sin nada más, se asume el combustible por omisión (gasolina) y se marca SUPUESTO", () => {
    const r = resolverFactorEstequiometrico({ catalogo });
    expect(r.origen).toBe(OrigenFactor.SUPUESTO);
    expect(r.estequiometria).toBe(14.7);
    expect(r.combustibleId).toBe("gasolina");
  });

  it("si el log trae el canal de estequiometría, se usa y se marca LOG", () => {
    const r = resolverFactorEstequiometrico({ catalogo, estequiometriaDelLog: 9.77 });
    expect(r.origen).toBe(OrigenFactor.LOG);
    expect(r.estequiometria).toBe(9.77);
    expect(r.combustibleId).toBe("e85"); // coincide con un combustible del catálogo
  });

  it("un valor de log que no coincide con ningún combustible del catálogo no tiene `combustibleId`", () => {
    const r = resolverFactorEstequiometrico({ catalogo, estequiometriaDelLog: 11.3 });
    expect(r.origen).toBe(OrigenFactor.LOG);
    expect(r.combustibleId).toBeUndefined();
  });

  it("la elección del usuario gana al valor del log", () => {
    const r = resolverFactorEstequiometrico({
      catalogo,
      estequiometriaDelLog: 14.7, // el log dice gasolina...
      eleccionUsuario: { combustibleId: "metanol", estequiometria: 6.4 }, // ...pero el usuario corrige
    });
    expect(r.origen).toBe(OrigenFactor.USUARIO);
    expect(r.estequiometria).toBe(6.4);
    expect(r.combustibleId).toBe("metanol");
  });

  it("la elección del usuario gana también cuando no hay dato de log en absoluto", () => {
    const r = resolverFactorEstequiometrico({
      catalogo,
      eleccionUsuario: { combustibleId: "e85", estequiometria: 9.77 },
    });
    expect(r.origen).toBe(OrigenFactor.USUARIO);
  });

  it("un valor manual del usuario que no está en el catálogo no tiene `combustibleId`", () => {
    const r = resolverFactorEstequiometrico({
      catalogo,
      eleccionUsuario: { estequiometria: 12.1 },
    });
    expect(r.origen).toBe(OrigenFactor.USUARIO);
    expect(r.combustibleId).toBeUndefined();
    expect(r.estequiometria).toBe(12.1);
  });

  it("un valor manual del usuario que SÍ coincide con el catálogo se reconoce igualmente", () => {
    const r = resolverFactorEstequiometrico({
      catalogo,
      eleccionUsuario: { estequiometria: 14.5 }, // igual al diésel de la fixture, tecleado a mano
    });
    expect(r.combustibleId).toBe("diesel");
  });
});

describe("combustiblePorOmision", () => {
  it("encuentra el único combustible marcado `porOmision`", () => {
    expect(combustiblePorOmision(catalogoDeCombustiblesDePrueba()).id).toBe("gasolina");
  });

  it("lanza si ninguno está marcado por omisión", () => {
    const sinOmision = catalogoDeCombustiblesDePrueba().map((c) => ({ ...c, porOmision: false }));
    expect(() => combustiblePorOmision(sinOmision)).toThrow(ErrorDeCombustible);
    expect(() => combustiblePorOmision(sinOmision)).toThrow(/ningún combustible por omisión/);
  });

  it("lanza si hay más de uno marcado por omisión (catálogo mal formado)", () => {
    const catalogo = catalogoDeCombustiblesDePrueba();
    const dosOmisiones = catalogo.map((c) => (c.id === "e85" ? { ...c, porOmision: true } : c));
    expect(() => combustiblePorOmision(dosOmisiones)).toThrow(/más de un combustible por omisión/);
  });
});

describe("buscarCombustible", () => {
  it("lanza con los ids disponibles en el mensaje", () => {
    expect(() => buscarCombustible(catalogoDeCombustiblesDePrueba(), "fantasma")).toThrow(
      /gasolina, e85, etanol, metanol, diesel/,
    );
  });
});

describe("explicacionDeOrigen", () => {
  it("da un texto distinto para cada uno de los tres orígenes", () => {
    const textos = new Set(
      [OrigenFactor.LOG, OrigenFactor.USUARIO, OrigenFactor.SUPUESTO].map(explicacionDeOrigen),
    );
    expect(textos.size).toBe(3);
  });

  it("el texto de SUPUESTO deja claro que es una suposición, no un dato medido", () => {
    expect(explicacionDeOrigen(OrigenFactor.SUPUESTO)).toMatch(/asume/);
  });
});

describe("analizarEstequiometriaTecleada", () => {
  it("acepta coma decimal (locale español, docs/06 §6.10)", () => {
    expect(analizarEstequiometriaTecleada("9,77")).toBe(9.77);
  });

  it("acepta punto decimal", () => {
    expect(analizarEstequiometriaTecleada("9.77")).toBe(9.77);
  });

  it("ignora espacios sueltos", () => {
    expect(analizarEstequiometriaTecleada("  14,7  ")).toBe(14.7);
  });

  it("rechaza texto vacío", () => {
    expect(analizarEstequiometriaTecleada("")).toBeUndefined();
    expect(analizarEstequiometriaTecleada("   ")).toBeUndefined();
  });

  it("rechaza cero y negativos: una estequiometría no invertible no es un valor razonable", () => {
    expect(analizarEstequiometriaTecleada("0")).toBeUndefined();
    expect(analizarEstequiometriaTecleada("-5")).toBeUndefined();
  });

  it("rechaza texto que no es un número", () => {
    expect(analizarEstequiometriaTecleada("abc")).toBeUndefined();
  });
});
