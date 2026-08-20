/**
 * Pruebas de `resolverMapaErrorLambda`: la pieza específica de F4-04 que
 * decide clase, escala y si el mapa se puede pintar en la unidad activa.
 *
 * EL CASO QUE JUSTIFICA LA DECISIÓN DE LA TAREA
 * =================================================
 * Con la unidad activa en φ (recíproca de λ), el mapa se DESACTIVA con una
 * explicación en vez de fallar o de caer a λ en silencio (ver la cabecera de
 * `mapa-error.ts` para el porqué). Es la prueba `"φ..."` de abajo.
 */

import { describe, expect, it } from "vitest";

import type { Conversion } from "../unidades/conversion.ts";
import type { UnidadInfo } from "../unidades/tipos.ts";
import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Color } from "../render/tipos.ts";
import { resolverMapaErrorLambda, type ConfiguracionMapaErrorLambda } from "./mapa-error.ts";
import type { CeldaEstadisticas, MallaResuelta } from "../malla/tipos.ts";

const AREA: AreaDibujo = { x: 0, y: 0, ancho: 100, alto: 100 };
const GRIS: Color = { r: 0.5, g: 0.5, b: 0.5, a: 1 };

function celda(parcial: Partial<CeldaEstadisticas> = {}): CeldaEstadisticas {
  return { cuenta: 0, media: NaN, desviacionTipica: NaN, minimo: NaN, maximo: NaN, ...parcial };
}

function malla(celdas: readonly CeldaEstadisticas[]): MallaResuelta {
  return { bordesFila: [0, 1], bordesColumna: [0, 1], celdas };
}

const UNIDAD_LAMBDA: UnidadInfo = {
  id: "lambda",
  etiqueta: "λ",
  decimales: 3,
  conversion: { tipo: "afin", a: 1, b: 0 },
};

const UNIDAD_AFR: UnidadInfo = {
  id: "afr",
  etiqueta: "AFR",
  decimales: 1,
  conversion: { tipo: "parametrizada", parametroRol: "stoichiometry", aPorOmision: 14.7 },
};

const UNIDAD_PHI: UnidadInfo = {
  id: "phi",
  etiqueta: "φ",
  decimales: 3,
  conversion: { tipo: "reciproca", a: 1 } as Conversion,
};

function config(parcial: Partial<ConfiguracionMapaErrorLambda> = {}): ConfiguracionMapaErrorLambda {
  return {
    area: AREA,
    malla: malla([celda({ cuenta: 10, media: 0.05, minimo: -0.02, maximo: 0.12 })]),
    forma: { filas: 1, columnas: 1 },
    unidadActiva: UNIDAD_LAMBDA,
    umbralConfianza: 5,
    colorSinDatos: GRIS,
    ...parcial,
  };
}

describe("resolverMapaErrorLambda — unidad recíproca (φ): desactivar, no caer a λ", () => {
  it("con φ como unidad activa, el resultado es «deshabilitado» con un motivo explicando por qué", () => {
    const resultado = resolverMapaErrorLambda(config({ unidadActiva: UNIDAD_PHI }));
    expect(resultado.tipo).toBe("deshabilitado");
    if (resultado.tipo !== "deshabilitado") throw new Error("se esperaba deshabilitado");
    expect(resultado.motivo.length).toBeGreaterThan(0);
    expect(resultado.motivo).toContain("φ");
  });

  it("con λ como unidad activa (afín, no recíproca), el mapa SÍ se activa", () => {
    const resultado = resolverMapaErrorLambda(config());
    expect(resultado.tipo).toBe("activo");
  });

  it("con AFR (parametrizada, lineal) como unidad activa, el mapa SÍ se activa: no es recíproca", () => {
    const resultado = resolverMapaErrorLambda(
      config({ unidadActiva: UNIDAD_AFR, parametro: 14.7 }),
    );
    expect(resultado.tipo).toBe("activo");
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    expect(resultado.configuracion.claseValor).toBe("intervalo");
    expect(resultado.configuracion.parametro).toBe(14.7);
  });
});

describe("resolverMapaErrorLambda — clase fija, no negociable", () => {
  it("claseValor de la configuración resultante es SIEMPRE «intervalo», nunca «punto»", () => {
    const resultado = resolverMapaErrorLambda(config());
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    expect(resultado.configuracion.claseValor).toBe("intervalo");
  });

  it("los decimales de la configuración resultante vienen de la unidad activa, no de un número cableado aquí", () => {
    const resultado = resolverMapaErrorLambda(config({ unidadActiva: UNIDAD_AFR, parametro: 14.7 }));
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    expect(resultado.configuracion.decimales).toBe(UNIDAD_AFR.decimales);
  });
});

describe("resolverMapaErrorLambda — escala de color", () => {
  it("con `escalaMaximaError` explícita, se usa esa y no la deducida de los datos", () => {
    const resultado = resolverMapaErrorLambda(config({ escalaMaximaError: 1 }));
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    // Con una escala de anchura 1, un valor de 0,05 está lejos de saturar: su
    // color no puede coincidir con el de un valor que sí satura (1 o más).
    const colorEnValor = resultado.configuracion.colorDeValor(0.05, celda());
    const colorSaturado = resultado.configuracion.colorDeValor(1, celda());
    expect(colorEnValor).not.toEqual(colorSaturado);
  });

  it("sin `escalaMaximaError` y sin ningún dato finito en la malla, se desactiva: no hay escala que deducir", () => {
    const resultado = resolverMapaErrorLambda(
      config({ malla: malla([celda()]) }), // la única celda está vacía: media = NaN
    );
    expect(resultado.tipo).toBe("deshabilitado");
  });

  it("sin `escalaMaximaError`, se deduce del mayor error absoluto de la malla", () => {
    const resultado = resolverMapaErrorLambda(
      config({ malla: malla([celda({ cuenta: 10, media: 0.08 }), celda({ cuenta: 10, media: -0.2 })]), forma: { filas: 1, columnas: 2 } }),
    );
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    // La escala deducida es 0,2 (el mayor absoluto): un valor de 0,2 tiene que saturar.
    const enElLimite = resultado.configuracion.colorDeValor(0.2, celda());
    const masAlla = resultado.configuracion.colorDeValor(5, celda());
    expect(enElLimite).toEqual(masAlla); // los dos saturados: coinciden
  });
});
