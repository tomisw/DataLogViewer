import { describe, expect, it } from "vitest";

import { aceptarPropuesta, deducido, editar, esConfirmado, esDeducido } from "./campo.ts";

describe("Campo<T>: deducido vs confirmado", () => {
  it("deducido() marca el origen como deducido", () => {
    const campo = deducido(",");
    expect(campo).toEqual({ valor: ",", origen: "deducido" });
    expect(esDeducido(campo)).toBe(true);
    expect(esConfirmado(campo)).toBe(false);
  });

  it("editar() siempre produce confirmado, aunque el campo ya lo fuera", () => {
    const deducidoInicial = deducido(",");
    const tras1 = editar(deducidoInicial, ";");
    expect(tras1).toEqual({ valor: ";", origen: "confirmado" });

    const tras2 = editar(tras1, "\t");
    expect(tras2).toEqual({ valor: "\t", origen: "confirmado" });
  });

  it("aceptarPropuesta() conserva el valor deducido pero cambia el origen", () => {
    const campo = deducido("utf-8");
    const aceptado = aceptarPropuesta(campo);
    expect(aceptado.valor).toBe("utf-8");
    expect(esConfirmado(aceptado)).toBe(true);
    // El original no se muta: son objetos distintos.
    expect(esDeducido(campo)).toBe(true);
  });
});
