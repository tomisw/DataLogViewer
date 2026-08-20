/**
 * Pruebas de `resolverMapaAvance`: la pieza específica de F4-07 que decide
 * clase, escala y si el mapa se puede pintar.
 *
 * A DIFERENCIA DE `mapa-error.test.ts`: NO HAY CASO DE UNIDAD RECÍPROCA
 * ==========================================================================
 * El avance de encendido es `Clase.PUNTO` (ver la cabecera de
 * `mapa-avance.ts`), y `admiteClase` siempre admite `"punto"` sea cual sea el
 * tipo de conversión — así que no existe, para este mapa, el caso
 * "deshabilitado por unidad recíproca" que sí prueba `mapa-error.test.ts`
 * para φ. La prueba de abajo lo comprueba con una conversión recíproca de
 * mentira, precisamente para dejar constancia de que el mapa se activa
 * incluso ahí.
 */

import { describe, expect, it } from "vitest";

import type { Conversion } from "../unidades/conversion.ts";
import type { UnidadInfo } from "../unidades/tipos.ts";
import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Color } from "../render/tipos.ts";
import { resolverMapaAvance, type ConfiguracionMapaAvance } from "./mapa-avance.ts";
import type { CeldaEstadisticas, MallaResuelta } from "../malla/tipos.ts";

const AREA: AreaDibujo = { x: 0, y: 0, ancho: 100, alto: 100 };
const GRIS: Color = { r: 0.5, g: 0.5, b: 0.5, a: 1 };

function celda(parcial: Partial<CeldaEstadisticas> = {}): CeldaEstadisticas {
  return { cuenta: 0, media: NaN, desviacionTipica: NaN, minimo: NaN, maximo: NaN, ...parcial };
}

function malla(celdas: readonly CeldaEstadisticas[]): MallaResuelta {
  return { bordesFila: [0, 1], bordesColumna: [0, 1], celdas };
}

const UNIDAD_DEG: UnidadInfo = {
  id: "deg",
  etiqueta: "°",
  decimales: 1,
  conversion: { tipo: "afin", a: 1, b: 0 },
};

const UNIDAD_DEG_CAM: UnidadInfo = {
  id: "deg_cam",
  etiqueta: "° árbol",
  decimales: 1,
  conversion: { tipo: "afin", a: 0.5, b: 0 },
};

/** No existe hoy en `data/units.toml` para `angle`, pero sirve para probar que el mapa NO se desactiva por esto. */
const UNIDAD_RECIPROCA_DE_MENTIRA: UnidadInfo = {
  id: "reciproca-de-mentira",
  etiqueta: "1/°",
  decimales: 1,
  conversion: { tipo: "reciproca", a: 1 } as Conversion,
};

function config(parcial: Partial<ConfiguracionMapaAvance> = {}): ConfiguracionMapaAvance {
  return {
    area: AREA,
    malla: malla([celda({ cuenta: 10, media: 15, minimo: 5, maximo: 22 })]),
    forma: { filas: 1, columnas: 1 },
    unidadActiva: UNIDAD_DEG,
    umbralConfianza: 5,
    colorSinDatos: GRIS,
    // Rango explícito por omisión: una malla de una sola celda no da ningún
    // rango deducible (mínimo === máximo, degenerado — ver la prueba
    // dedicada más abajo), y la mayoría de estas pruebas no quieren
    // acoplarse a esa escala para comprobar otra cosa (clase, decimales...).
    rangoAvance: { minimo: 0, maximo: 30 },
    ...parcial,
  };
}

describe("resolverMapaAvance — clase fija, no negociable", () => {
  it("claseValor de la configuración resultante es SIEMPRE «punto», nunca «intervalo»", () => {
    const resultado = resolverMapaAvance(config());
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    expect(resultado.configuracion.claseValor).toBe("punto");
  });

  it("los decimales de la configuración resultante vienen de la unidad activa, no de un número cableado aquí", () => {
    const resultado = resolverMapaAvance(config({ unidadActiva: UNIDAD_DEG_CAM }));
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    expect(resultado.configuracion.decimales).toBe(UNIDAD_DEG_CAM.decimales);
  });
});

describe("resolverMapaAvance — sin caso de unidad recíproca, a diferencia del error de λ", () => {
  it("incluso con una conversión recíproca, el mapa SÍ se activa: el avance es una lectura (clase punto)", () => {
    const resultado = resolverMapaAvance(config({ unidadActiva: UNIDAD_RECIPROCA_DE_MENTIRA }));
    expect(resultado.tipo).toBe("activo");
  });
});

describe("resolverMapaAvance — escala secuencial", () => {
  it("con `rangoAvance` explícito, se usa ese y no el deducido de los datos", () => {
    const resultado = resolverMapaAvance(config({ rangoAvance: { minimo: 0, maximo: 30 } }));
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    const colorBajo = resultado.configuracion.colorDeValor(0, celda());
    const colorAlto = resultado.configuracion.colorDeValor(30, celda());
    expect(colorBajo).not.toEqual(colorAlto);
  });

  it("sin `rangoAvance` y sin ningún dato finito en la malla, se desactiva: no hay escala que deducir", () => {
    const resultado = resolverMapaAvance(
      config({ malla: malla([celda()]), rangoAvance: undefined }), // única celda vacía: media = NaN
    );
    expect(resultado.tipo).toBe("deshabilitado");
    if (resultado.tipo !== "deshabilitado") throw new Error("se esperaba deshabilitado");
    expect(resultado.motivo.length).toBeGreaterThan(0);
  });

  it("sin `rangoAvance` pero con una sola celda con dato, también se desactiva: un rango de anchura cero no se pinta", () => {
    // Un único valor no da ningún rango [min, max] con anchura: no hay
    // gradiente que interpolar, mismo criterio que `rangoSecuencialDesdeDatos`
    // trata "todos los valores idénticos" como degenerado.
    const resultado = resolverMapaAvance(
      config({ malla: malla([celda({ cuenta: 10, media: 15 })]), rangoAvance: undefined }),
    );
    expect(resultado.tipo).toBe("deshabilitado");
  });

  it("sin `rangoAvance`, se deduce del menor y mayor avance medio de la malla", () => {
    const resultado = resolverMapaAvance(
      config({
        malla: malla([celda({ cuenta: 10, media: 5 }), celda({ cuenta: 10, media: 25 })]),
        forma: { filas: 1, columnas: 2 },
        rangoAvance: undefined,
      }),
    );
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    // El rango deducido es [5, 25]: los dos extremos tienen que saturar a colores distintos.
    const enElMinimo = resultado.configuracion.colorDeValor(5, celda());
    const enElMaximo = resultado.configuracion.colorDeValor(25, celda());
    const masAlla = resultado.configuracion.colorDeValor(1000, celda());
    expect(enElMinimo).not.toEqual(enElMaximo);
    expect(enElMaximo).toEqual(masAlla); // saturado por encima del máximo deducido
  });
});
