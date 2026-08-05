import { describe, expect, it } from "vitest";

import {
  aCanonica,
  admiteClase,
  convertirCubos,
  convertirDesdeCrudo,
  convertirValor,
  ErrorDeUnidad,
  esIdentidad,
  IDENTIDAD,
  type Conversion,
  type ConversionAfin,
} from "./conversion.ts";
import type { CubosContinuos } from "../render/tipos.ts";

// Factores reales de `data/units.toml`, copiados aquí SOLO como datos de
// prueba: el código no los lleva (regla 2 de CLAUDE.md), llegan por HTTP.
const DEG_C: ConversionAfin = { tipo: "afin", a: 1, b: -273.15 };
const DEG_F: ConversionAfin = { tipo: "afin", a: 1.8, b: -459.67 };
const PSI: ConversionAfin = { tipo: "afin", a: 0.14503773773, b: 0 };
const PCT: ConversionAfin = { tipo: "afin", a: 100, b: 0 };
const PHI: Conversion = { tipo: "reciproca", a: 1 };
const AFR: Conversion = { tipo: "parametrizada", parametroRol: "stoichiometry", aPorOmision: 14.7 };

function cubos(valores: number[]): CubosContinuos {
  const f = new Float32Array(valores);
  return {
    t: new Float32Array(valores.map((_, i) => i)),
    tOrigen: 0,
    minimo: f,
    maximo: f.map((v) => v + 10),
    primero: f,
    ultimo: f,
    factor: 1,
  };
}

describe("conversión afín", () => {
  it("convierte un punto con el desplazamiento de origen", () => {
    expect(convertirValor(293.15, DEG_C, "punto")).toBeCloseTo(20, 10);
    expect(convertirValor(293.15, DEG_F, "punto")).toBeCloseTo(68, 10);
  });

  it("psi: 1,3 psi se muestran como 1,3 psi", () => {
    // El requisito del propietario, literal. 1,3 psi son 8,9632 kPa en canónica.
    const enCanonica = aCanonica(1.3, PSI, "punto");
    expect(convertirValor(enCanonica, PSI, "punto")).toBeCloseTo(1.3, 10);
  });

  it("ida y vuelta sin pérdida", () => {
    for (const c of [DEG_C, DEG_F, PSI, PCT]) {
      expect(aCanonica(convertirValor(300, c, "punto"), c, "punto")).toBeCloseTo(300, 8);
    }
  });
});

describe("la trampa del delta (regla 4, docs/06 §6.5)", () => {
  it("un Δ de 10 K son 10 °C, NO −263,15 °C", () => {
    expect(convertirValor(10, DEG_C, "intervalo")).toBe(10);
    // Lo que pasaría si alguien lo convirtiera como punto:
    expect(convertirValor(10, DEG_C, "punto")).toBeCloseTo(-263.15, 10);
  });

  it("un Δ de 10 K son 18 °F", () => {
    expect(convertirValor(10, DEG_F, "intervalo")).toBeCloseTo(18, 10);
  });

  it("una tasa usa solo la parte lineal", () => {
    expect(convertirValor(2, DEG_C, "tasa")).toBe(2);
  });

  it("una varianza usa a²", () => {
    expect(convertirValor(4, DEG_F, "varianza")).toBeCloseTo(4 * 1.8 * 1.8, 10);
    expect(aCanonica(convertirValor(4, DEG_F, "varianza"), DEG_F, "varianza")).toBeCloseTo(4, 10);
  });
});

describe("conversión recíproca (λ ↔ φ)", () => {
  it("invierte el valor", () => {
    expect(convertirValor(0.8, PHI, "punto")).toBeCloseTo(1.25, 10);
  });

  it("se niega a convertir una diferencia en vez de dar un número plausible", () => {
    expect(() => convertirValor(0.1, PHI, "intervalo")).toThrow(ErrorDeUnidad);
    expect(() => convertirValor(0.1, PHI, "varianza")).toThrow(ErrorDeUnidad);
    expect(admiteClase(PHI, "intervalo")).toBe(false);
    expect(admiteClase(PHI, "punto")).toBe(true);
  });

  it("intercambia mínimo y máximo al convertir cubos", () => {
    // `a/x` es decreciente: el mínimo en canónica es el máximo en φ. Sin el
    // intercambio, el relleno del trazo saldría con los extremos cruzados.
    const convertidos = convertirCubos(cubos([1, 2]), IDENTIDAD, PHI);
    expect(convertidos.minimo[0]).toBeCloseTo(1 / 11, 6); // era el `maximo` (1+10)
    expect(convertidos.maximo[0]).toBeCloseTo(1 / 1, 6); // era el `minimo`
    expect(convertidos.minimo[0]!).toBeLessThan(convertidos.maximo[0]!);
  });
});

describe("conversión parametrizada (λ → AFR)", () => {
  it("sin parámetro usa la estequiometría por omisión de la gasolina", () => {
    expect(convertirValor(1, AFR, "punto")).toBeCloseTo(14.7, 10);
  });

  it("con E85 el mismo λ da otro AFR, que es justo el motivo de que exista", () => {
    expect(convertirValor(1, AFR, "punto", 9.77)).toBeCloseTo(9.77, 10);
    expect(convertirValor(0.85, AFR, "punto", 6.4)).toBeCloseTo(5.44, 10);
  });

  it("una estequiometría de cero no se acepta: daría toda la serie a cero", () => {
    expect(convertirValor(1, AFR, "punto", 0)).toBeCloseTo(14.7, 10);
  });

  it("un Δ de λ sí se puede convertir: es lineal, a diferencia de φ", () => {
    expect(convertirValor(0.1, AFR, "intervalo", 9.77)).toBeCloseTo(0.977, 10);
  });
});

describe("identidad", () => {
  it("no copia los arrays cuando no hay nada que convertir", () => {
    const originales = cubos([1, 2, 3]);
    expect(convertirCubos(originales, IDENTIDAD, IDENTIDAD)).toBe(originales);
    expect(esIdentidad(IDENTIDAD)).toBe(true);
    expect(esIdentidad(DEG_C)).toBe(false);
    expect(esIdentidad(PHI)).toBe(false);
  });
});

describe("cubos", () => {
  it("convierte los cuatro arrays como punto y no toca el tiempo", () => {
    const original = cubos([273.15, 373.15]);
    const c = convertirCubos(original, IDENTIDAD, DEG_C);
    // La tolerancia es de `Float32Array`, no de la conversión: 273,15 no es
    // representable en float32, así que restarle 273,15 deja −6,1e−6 en vez de
    // cero exacto (cancelación catastrófica cerca del origen desplazado). Son
    // 0,00001 °C; se documenta para que nadie lo lea como un error de factor.
    expect(c.minimo[0]).toBeCloseTo(0, 4);
    expect(c.minimo[1]).toBeCloseTo(100, 4);
    expect(c.t).toBe(original.t);
    expect(c.tOrigen).toBe(original.tOrigen);
    expect(c.factor).toBe(original.factor);
  });

  it("no muta la entrada, que está cacheada en canónica", () => {
    const original = cubos([273.15]);
    convertirCubos(original, IDENTIDAD, DEG_C);
    expect(original.minimo[0]).toBeCloseTo(273.15, 4);
  });
});

describe("los DOS pasos: crudo → canónica → mostrada", () => {
  // El caso literal del AutoLog del propietario: `Coolant Temperature` llega
  // como el entero 3748 con `to_canon` a=0,1 (comprobado contra
  // /comandos/abrir-log). Sin el primer paso, la app enseñaba 3 474,85 °C.
  const A_CANONICA_REFRIGERANTE: ConversionAfin = { tipo: "afin", a: 0.1, b: 0 };

  it("3748 crudo son 374,8 K y 101,65 °C, no 3 474,85 °C", () => {
    expect(convertirDesdeCrudo(3748, A_CANONICA_REFRIGERANTE, IDENTIDAD, "punto")).toBeCloseTo(
      374.8,
      6,
    );
    expect(convertirDesdeCrudo(3748, A_CANONICA_REFRIGERANTE, DEG_C, "punto")).toBeCloseTo(
      101.65,
      6,
    );
    // Lo que salía antes de aplicar el escalado del canal:
    expect(convertirValor(3748, DEG_C, "punto")).toBeCloseTo(3474.85, 6);
  });

  it("un Δ ignora los DOS desplazamientos de origen, el del canal y el de la unidad", () => {
    // 100 crudo = 10 K de diferencia = 10 °C de diferencia.
    expect(convertirDesdeCrudo(100, A_CANONICA_REFRIGERANTE, DEG_C, "intervalo")).toBeCloseTo(
      10,
      6,
    );
  });

  it("Manifold Pressure: 2190 crudo con a=0,1 son 219 kPa y 31,76 psi", () => {
    const aCanon: ConversionAfin = { tipo: "afin", a: 0.1, b: 0 };
    expect(convertirDesdeCrudo(2190, aCanon, PSI, "punto")).toBeCloseTo(31.763, 3);
  });

  it("Throttle Position: 1000 crudo con a=0,001 son 100 %", () => {
    const aCanon: ConversionAfin = { tipo: "afin", a: 0.001, b: 0 };
    expect(convertirDesdeCrudo(1000, aCanon, PCT, "punto")).toBeCloseTo(100, 6);
  });

  it("λ 1535 crudo con a=0,001 son 1,535 λ y 22,56 AFR de gasolina", () => {
    const aCanon: ConversionAfin = { tipo: "afin", a: 0.001, b: 0 };
    expect(convertirDesdeCrudo(1535, aCanon, IDENTIDAD, "punto")).toBeCloseTo(1.535, 6);
    expect(convertirDesdeCrudo(1535, aCanon, AFR, "punto")).toBeCloseTo(22.5645, 4);
    expect(convertirDesdeCrudo(1535, aCanon, AFR, "punto", 9.77)).toBeCloseTo(14.9970, 4);
  });

  it("convertirCubos aplica los dos pasos", () => {
    const aCanon: ConversionAfin = { tipo: "afin", a: 0.1, b: 0 };
    const c = convertirCubos(cubos([3748]), aCanon, DEG_C);
    expect(c.minimo[0]).toBeCloseTo(101.65, 2);
  });
});
