/**
 * Pruebas de la edición de umbrales en unidad activa (F3-05, decisión 4).
 *
 * La prueba que de verdad importa es la de "el desplazamiento de origen no se
 * cuela en el semiancho": es exactamente el error que la cabecera de
 * `edicion-umbrales.ts` describe (la misma trampa que ya costó días en
 * `unidades/conversion.ts`, pero en el ancho de una banda en vez de en un Δ de
 * cursor). Se usa °C↔K (`a=1, b=-273.15`) porque es la conversión con
 * desplazamiento de origen más simple del catálogo: cualquier error de clase
 * se ve inmediatamente como un número desplazado en 273,15.
 */

import { describe, expect, it } from "vitest";

import type { Conversion } from "../unidades/conversion.ts";
import { construirLimiteDeAlerta } from "./perfil.ts";
import {
  actualizarBandaCentroYAncho,
  actualizarBandaMinMax,
  actualizarValorDeTope,
  bandaACentroYAnchoMostrado,
  bandaAMinMaxMostrado,
  bandaEsEditable,
  bandaEsEditableConSemiancho,
  ErrorDeEdicionDeUmbral,
  topeEsEditable,
  valorDeTopeMostrado,
} from "./edicion-umbrales.ts";

/** K -> °C: resta 273,15. La unidad canónica de temperatura es K (docs/06). */
const K_A_CELSIUS: Conversion = { tipo: "afin", a: 1, b: -273.15 };
/** λ -> φ (razón inversa): no lineal, `admiteClase` la restringe a PUNTO. */
const RECIPROCA: Conversion = { tipo: "reciproca", a: 1 };

describe("valorDeTopeMostrado / actualizarValorDeTope", () => {
  const limite = construirLimiteDeAlerta({
    rol: "coolant_temperature",
    topes: [
      { nivel: "aviso", direccion: "arriba", valor: 373.15 },
      { nivel: "critico", direccion: "arriba", valor: 383.15 },
    ],
  });

  it("convierte un tope PUNTO con desplazamiento de origen (373,15 K = 100 °C)", () => {
    const aviso = limite.topes.find((t) => t.nivel === "aviso")!;
    expect(valorDeTopeMostrado(aviso, K_A_CELSIUS)).toBeCloseTo(100, 9);
  });

  it("actualiza el valor y lo guarda en canónica", () => {
    const nuevo = actualizarValorDeTope(limite, "aviso", 90, K_A_CELSIUS);
    const aviso = nuevo.topes.find((t) => t.nivel === "aviso")!;
    expect(aviso.valor).toBeCloseTo(363.15, 9);
  });

  it("si el nuevo valor deja el aviso detrás del crítico, sale el error real de validar_pareja", () => {
    // 120 °C = 393,15 K, por encima del crítico (383,15 K).
    expect(() => actualizarValorDeTope(limite, "aviso", 120, K_A_CELSIUS)).toThrow(/nunca avisa/);
  });

  it("un tope en curva no se puede leer como valor plano", () => {
    const conCurva = construirLimiteDeAlerta({
      rol: "oil_pressure",
      topes: [{ nivel: "aviso", direccion: "abajo", valor: { forma: "lineal", rolReferencia: "engine_rpm", base: 1, pendiente: 1, divisorReferencia: 1 } }],
    });
    expect(topeEsEditable(conCurva.topes[0]!)).toBe(false);
    expect(() => valorDeTopeMostrado(conCurva.topes[0]!, K_A_CELSIUS)).toThrow(ErrorDeEdicionDeUmbral);
  });
});

describe("banda: mínimo/máximo (siempre PUNTO)", () => {
  const limite = construirLimiteDeAlerta({
    rol: "mixture_ratio",
    banda: { nivel: "aviso", minimo: 353.15, maximo: 363.15 },
  });

  it("bandaEsEditable es true para una banda plana", () => {
    expect(bandaEsEditable(limite.banda!)).toBe(true);
  });

  it("convierte los dos bordes como valores absolutos", () => {
    const mostrada = bandaAMinMaxMostrado(limite.banda!, K_A_CELSIUS);
    expect(mostrada.minimo).toBeCloseTo(80, 9);
    expect(mostrada.maximo).toBeCloseTo(90, 9);
  });

  it("ida y vuelta reproduce la banda original", () => {
    const mostrada = bandaAMinMaxMostrado(limite.banda!, K_A_CELSIUS);
    const actualizado = actualizarBandaMinMax(limite, mostrada, K_A_CELSIUS);
    expect(actualizado.banda!.minimo).toBeCloseTo(353.15, 9);
    expect(actualizado.banda!.maximo).toBeCloseTo(363.15, 9);
  });

  it("rechaza mínimo >= máximo", () => {
    expect(() => actualizarBandaMinMax(limite, { minimo: 90, maximo: 80 }, K_A_CELSIUS)).toThrow(ErrorDeEdicionDeUmbral);
  });
});

describe("banda: centro y semiancho -- LA prueba de la decisión 4", () => {
  // 353,15..363,15 K = 80..90 °C: centro 358,15 K = 85 °C, semiancho 5 K = 5 °C.
  const limite = construirLimiteDeAlerta({
    rol: "mixture_ratio",
    banda: { nivel: "aviso", minimo: 353.15, maximo: 363.15 },
  });

  it("el CENTRO lleva el desplazamiento de origen (PUNTO)", () => {
    const { centro } = bandaACentroYAnchoMostrado(limite.banda!, K_A_CELSIUS);
    expect(centro).toBeCloseTo(85, 9);
  });

  it("el SEMIANCHO NO lleva el desplazamiento de origen (INTERVALO): si lo llevara saldría -268,15, no 5", () => {
    const { semiancho } = bandaACentroYAnchoMostrado(limite.banda!, K_A_CELSIUS);
    expect(semiancho).toBeCloseTo(5, 9);
  });

  it("ida y vuelta por centro/semiancho reproduce la banda original en canónica", () => {
    const mostrada = bandaACentroYAnchoMostrado(limite.banda!, K_A_CELSIUS);
    const actualizado = actualizarBandaCentroYAncho(limite, mostrada, K_A_CELSIUS);
    expect(actualizado.banda!.minimo).toBeCloseTo(353.15, 9);
    expect(actualizado.banda!.maximo).toBeCloseTo(363.15, 9);
  });

  it("un semiancho no positivo se rechaza", () => {
    expect(() => actualizarBandaCentroYAncho(limite, { centro: 85, semiancho: 0 }, K_A_CELSIUS)).toThrow(
      ErrorDeEdicionDeUmbral,
    );
  });

  it("una conversión recíproca no admite el modo centro/semiancho (no es lineal)", () => {
    expect(bandaEsEditableConSemiancho(RECIPROCA)).toBe(false);
    expect(() => bandaACentroYAnchoMostrado(limite.banda!, RECIPROCA)).toThrow(ErrorDeEdicionDeUmbral);
    expect(() => actualizarBandaCentroYAncho(limite, { centro: 1, semiancho: 0.1 }, RECIPROCA)).toThrow(
      ErrorDeEdicionDeUmbral,
    );
  });

  it("una banda con un borde en curva no es editable con valores planos", () => {
    const conCurva = construirLimiteDeAlerta({
      rol: "oil_pressure",
      banda: {
        nivel: "aviso",
        minimo: { forma: "lineal", rolReferencia: "engine_rpm", base: 1, pendiente: 1, divisorReferencia: 1 },
        maximo: 500,
      },
    });
    expect(bandaEsEditable(conCurva.banda!)).toBe(false);
    expect(() => bandaACentroYAnchoMostrado(conCurva.banda!, K_A_CELSIUS)).toThrow(ErrorDeEdicionDeUmbral);
  });
});
