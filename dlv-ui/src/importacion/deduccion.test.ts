/**
 * Pruebas de `deduccion.ts`: la mitigación 4 de `docs/07` §7.15 — un rol
 * DIFUSA sin confirmar tiene que poder desactivar un detector crítico.
 */

import { describe, expect, it } from "vitest";

import {
  asignarRolManualmente,
  confirmarRol,
  debeDesactivarDetectorCritico,
  propuestaInicialDeRol,
  requiereConfirmacion,
  resumirConfianza,
  textoPendientesDeConfirmar,
} from "./deduccion.ts";

describe("propuestaInicialDeRol", () => {
  it("EXACTA nace confirmada", () => {
    const rol = propuestaInicialDeRol({ rol: "coolant_temp", confianza: "EXACTA", sinonimo: "CLT" });
    expect(rol.confirmado).toBe(true);
  });

  it("INDEXADA nace confirmada", () => {
    const rol = propuestaInicialDeRol({
      rol: "knock_count",
      confianza: "INDEXADA",
      sinonimo: "Knock Sensor {n} Knock Count",
      indice: 2,
    });
    expect(rol.confirmado).toBe(true);
    expect(rol.indice).toBe(2);
  });

  it("DIFUSA nace SIN confirmar", () => {
    const rol = propuestaInicialDeRol({
      rol: "coolant_temp",
      confianza: "DIFUSA",
      sinonimo: "Water Temp",
      parecido: 0.87,
    });
    expect(rol.confirmado).toBe(false);
  });
});

describe("requiereConfirmacion", () => {
  it("una DIFUSA sin confirmar requiere confirmación", () => {
    const rol = propuestaInicialDeRol({ rol: "oil_temp", confianza: "DIFUSA", sinonimo: "OilTemp2" });
    expect(requiereConfirmacion(rol)).toBe(true);
  });

  it("tras confirmarRol(), ya no la requiere", () => {
    const rol = propuestaInicialDeRol({ rol: "oil_temp", confianza: "DIFUSA", sinonimo: "OilTemp2" });
    expect(requiereConfirmacion(confirmarRol(rol))).toBe(false);
  });

  it("EXACTA e INDEXADA nunca la requieren", () => {
    const exacta = propuestaInicialDeRol({ rol: "engine_speed", confianza: "EXACTA", sinonimo: "RPM" });
    const indexada = propuestaInicialDeRol({
      rol: "knock_count",
      confianza: "INDEXADA",
      sinonimo: "Knock Sensor {n} Knock Count",
      indice: 1,
    });
    expect(requiereConfirmacion(exacta)).toBe(false);
    expect(requiereConfirmacion(indexada)).toBe(false);
  });

  it("un canal sin rol no requiere confirmación (no hay nada que confirmar)", () => {
    expect(requiereConfirmacion(null)).toBe(false);
  });

  it("una asignación manual del usuario no requiere confirmación: ya lo es", () => {
    expect(requiereConfirmacion(asignarRolManualmente("coolant_temp"))).toBe(false);
  });
});

describe("debeDesactivarDetectorCritico: docs/07 §7.15 mitigación 4", () => {
  it("con todos los roles firmes, el detector puede activarse", () => {
    const boost = propuestaInicialDeRol({
      rol: "boost_pressure_actual",
      confianza: "EXACTA",
      sinonimo: "Boost Pressure",
    });
    const wastegate = propuestaInicialDeRol({
      rol: "wastegate_duty",
      confianza: "INDEXADA",
      sinonimo: "Wastegate Duty {n}",
      indice: 1,
    });
    expect(debeDesactivarDetectorCritico([boost, wastegate])).toBe(false);
  });

  it("basta con QUE UNO de los roles implicados sea difuso sin confirmar", () => {
    const boost = propuestaInicialDeRol({
      rol: "boost_pressure_actual",
      confianza: "EXACTA",
      sinonimo: "Boost Pressure",
    });
    const wastegateDifusa = propuestaInicialDeRol({
      rol: "wastegate_duty",
      confianza: "DIFUSA",
      sinonimo: "WG Duty",
    });
    expect(debeDesactivarDetectorCritico([boost, wastegateDifusa])).toBe(true);
  });

  it("confirmar la difusa reactiva el detector", () => {
    const wastegateDifusa = propuestaInicialDeRol({
      rol: "wastegate_duty",
      confianza: "DIFUSA",
      sinonimo: "WG Duty",
    });
    expect(debeDesactivarDetectorCritico([wastegateDifusa])).toBe(true);
    expect(debeDesactivarDetectorCritico([confirmarRol(wastegateDifusa)])).toBe(false);
  });

  it("un canal sin rol asignado no cuenta como difuso: el detector simplemente no tiene datos", () => {
    expect(debeDesactivarDetectorCritico([null])).toBe(false);
  });
});

describe("resumirConfianza y textoPendientesDeConfirmar", () => {
  it("cuenta cada categoría por separado", () => {
    const canales = [
      { rol: propuestaInicialDeRol({ rol: "engine_speed", confianza: "EXACTA", sinonimo: "RPM" }) },
      {
        rol: propuestaInicialDeRol({
          rol: "knock_count",
          confianza: "INDEXADA",
          sinonimo: "Knock Sensor {n} Knock Count",
          indice: 1,
        }),
      },
      { rol: confirmarRol(propuestaInicialDeRol({ rol: "oil_temp", confianza: "DIFUSA", sinonimo: "OilT" })) },
      { rol: propuestaInicialDeRol({ rol: "gearbox_temp", confianza: "DIFUSA", sinonimo: "GbT" }) },
      { rol: null },
    ];
    const resumen = resumirConfianza(canales);
    expect(resumen).toEqual({
      exactas: 1,
      indexadas: 1,
      difusasConfirmadas: 1,
      difusasPendientes: 1,
      sinRol: 1,
    });
    expect(textoPendientesDeConfirmar(resumen)).toContain("1 rol propuesto por parecido, sin confirmar");
  });

  it("sin pendientes, el texto del banner está vacío", () => {
    const resumen = resumirConfianza([
      { rol: propuestaInicialDeRol({ rol: "engine_speed", confianza: "EXACTA", sinonimo: "RPM" }) },
    ]);
    expect(textoPendientesDeConfirmar(resumen)).toBe("");
  });
});
