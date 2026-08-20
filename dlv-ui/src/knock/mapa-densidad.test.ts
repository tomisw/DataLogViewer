/**
 * Pruebas de `resolverMapaDensidadKnock`: la pieza específica de F4-07 que
 * decide clase, escala y si el mapa se puede pintar.
 *
 * LA CELDA DE PRUEBA REPRESENTA EL DELTA, NO EL CONTADOR ACUMULATIVO
 * =======================================================================
 * `celda({ media: 0.02 })` significa "0,02 eventos de knock por muestra en
 * esta celda" (2 de cada 100 muestras), no "el contador de knock valía 0,02
 * de media" — ver la cabecera de `mapa-densidad.ts` para por qué la
 * diferencia importa. Las pruebas no repiten ese razonamiento, solo usan
 * números coherentes con él.
 */

import { describe, expect, it } from "vitest";

import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Color } from "../render/tipos.ts";
import { resolverMapaDensidadKnock, type ConfiguracionMapaDensidadKnock } from "./mapa-densidad.ts";
import type { CeldaEstadisticas, MallaResuelta } from "../malla/tipos.ts";

const AREA: AreaDibujo = { x: 0, y: 0, ancho: 100, alto: 100 };
const GRIS: Color = { r: 0.5, g: 0.5, b: 0.5, a: 1 };

function celda(parcial: Partial<CeldaEstadisticas> = {}): CeldaEstadisticas {
  return { cuenta: 0, media: NaN, desviacionTipica: NaN, minimo: NaN, maximo: NaN, ...parcial };
}

function malla(celdas: readonly CeldaEstadisticas[]): MallaResuelta {
  return { bordesFila: [0, 1], bordesColumna: [0, 1], celdas };
}

function config(parcial: Partial<ConfiguracionMapaDensidadKnock> = {}): ConfiguracionMapaDensidadKnock {
  return {
    area: AREA,
    malla: malla([celda({ cuenta: 200, media: 0.02, minimo: 0, maximo: 1 })]),
    forma: { filas: 1, columnas: 1 },
    umbralConfianza: 20,
    colorSinDatos: GRIS,
    // Rango explícito por omisión: una malla de una sola celda no da ningún
    // rango deducible (mínimo === máximo, degenerado — ver la prueba
    // dedicada más abajo), y la mayoría de estas pruebas no quieren
    // acoplarse a esa escala para comprobar otra cosa (clase, decimales...).
    rangoDensidad: { minimo: 0, maximo: 1 },
    ...parcial,
  };
}

describe("resolverMapaDensidadKnock — clase fija, no negociable", () => {
  it("claseValor de la configuración resultante es SIEMPRE «punto»: es una tasa, no una diferencia", () => {
    const resultado = resolverMapaDensidadKnock(config());
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    expect(resultado.configuracion.claseValor).toBe("punto");
  });

  it("sin conversión de unidad: es la identidad, `count`/`sound_level` no son convertibles", () => {
    const resultado = resolverMapaDensidadKnock(config());
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    expect(resultado.configuracion.conversion).toEqual({ tipo: "afin", a: 1, b: 0 });
  });

  it("los decimales, si se pasan, viajan tal cual a la configuración", () => {
    const resultado = resolverMapaDensidadKnock(config({ decimales: 3 }));
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    expect(resultado.configuracion.decimales).toBe(3);
  });
});

describe("resolverMapaDensidadKnock — escala secuencial", () => {
  it("con `rangoDensidad` explícito, se usa ese y no el deducido de los datos", () => {
    const resultado = resolverMapaDensidadKnock(config({ rangoDensidad: { minimo: 0, maximo: 1 } }));
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    const colorBajo = resultado.configuracion.colorDeValor(0, celda());
    const colorAlto = resultado.configuracion.colorDeValor(1, celda());
    expect(colorBajo).not.toEqual(colorAlto);
  });

  it("sin `rangoDensidad` y sin ningún dato finito en la malla, se desactiva: no hay escala que deducir", () => {
    const resultado = resolverMapaDensidadKnock(
      config({ malla: malla([celda()]), rangoDensidad: undefined }), // única celda vacía: media = NaN
    );
    expect(resultado.tipo).toBe("deshabilitado");
    if (resultado.tipo !== "deshabilitado") throw new Error("se esperaba deshabilitado");
    expect(resultado.motivo.length).toBeGreaterThan(0);
  });

  it("sin `rangoDensidad`, se deduce de la menor y mayor densidad media de la malla", () => {
    const resultado = resolverMapaDensidadKnock(
      config({
        malla: malla([celda({ cuenta: 200, media: 0 }), celda({ cuenta: 200, media: 0.1 })]),
        forma: { filas: 1, columnas: 2 },
        rangoDensidad: undefined,
      }),
    );
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    // El rango deducido es [0, 0,1]: una celda sin ningún evento (densidad 0)
    // tiene que dar el color "sin knock", distinto del de la celda más densa.
    const sinEventos = resultado.configuracion.colorDeValor(0, celda());
    const masDensa = resultado.configuracion.colorDeValor(0.1, celda());
    expect(sinEventos).not.toEqual(masDensa);
  });

  it("la densidad alta usa el mismo rojo que el resto de indicadores críticos de la app", () => {
    const resultado = resolverMapaDensidadKnock(config({ rangoDensidad: { minimo: 0, maximo: 1 } }));
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    const colorSaturado = resultado.configuracion.colorDeValor(1, celda());
    // Mismo tono que `.dlv-topes-linea--critico` / `escalaDivergente` POSITIVO: rojo, no azul.
    expect(colorSaturado.r).toBeGreaterThan(colorSaturado.b);
    expect(colorSaturado.r).toBeGreaterThan(colorSaturado.g);
  });
});
