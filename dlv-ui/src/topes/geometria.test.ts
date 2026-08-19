/**
 * Pruebas de `calcularGeometriaTopes`: dónde cae cada tope, en la unidad
 * activa, con las dos reglas de "fuera de rango" que documenta la cabecera de
 * `geometria.ts` (línea plana → marca de borde; banda/curva → recorte).
 *
 * EL CASO QUE JUSTIFICA TODA LA TAREA
 * ======================================
 * Un tope de refrigerante crítico a 383,15 K tiene que caer EXACTAMENTE donde
 * caería 110 °C si se dibujara como un dato del canal — no en 383, que es el
 * número canónico sin convertir. Es la prueba `"caso guía..."` de abajo, y es
 * la que un fallo de esta tarea rompería en silencio: la línea seguiría
 * pintándose, solo que fuera de la pantalla o en el sitio equivocado.
 */

import { describe, expect, it } from "vitest";

import { yAPixel } from "../ejes/coordenadas.ts";
import type { Vista } from "../render/tipos.ts";
import type { Conversion } from "../unidades/conversion.ts";
import { calcularGeometriaTopes } from "./geometria.ts";
import type { AreaDibujo } from "../ejes/tipos.ts";
import type { BandaTope, ConfiguracionTopes, LineaTope } from "./tipos.ts";

const AREA: AreaDibujo = { x: 56, y: 12, ancho: 700, alto: 300 };

/** K → °C: `x - 273.15`, la conversión afín con `b ≠ 0` de todo el proyecto. */
const K_A_DEGC: Conversion = { tipo: "afin", a: 1, b: -273.15 };
const IDENTIDAD: Conversion = { tipo: "afin", a: 1, b: 0 };

function config(parcial: Partial<ConfiguracionTopes> = {}): ConfiguracionTopes {
  return {
    vista: { t0: 0, t1: 100, v0: 0, v1: 100 },
    area: AREA,
    conversion: IDENTIDAD,
    lineas: [],
    bandas: [],
    ...parcial,
  };
}

describe("calcularGeometriaTopes — líneas planas", () => {
  it("caso guía: un crítico a 383,15 K cae EXACTAMENTE donde caería 110 °C en el eje", () => {
    // Vista en °C (la unidad mostrada, igual que `pintarEjes` la recibe):
    // 90..130 °C, y el crítico declarado en canónica es 383,15 K = 110 °C.
    const vista: Vista = { t0: 0, t1: 60, v0: 90, v1: 130 };
    const linea: LineaTope = {
      id: "coolant-critico",
      nivel: "critico",
      limite: { tipo: "constante", valorCanonico: 383.15 },
    };
    const geometria = calcularGeometriaTopes(
      config({ vista, conversion: K_A_DEGC, lineas: [linea] }),
    );
    const resuelta = geometria.lineas[0]!;
    expect(resuelta.forma.tipo).toBe("plano");
    if (resuelta.forma.tipo !== "plano" || resuelta.forma.posicion.tipo !== "dentro") {
      throw new Error("se esperaba una línea dentro de rango");
    }
    // El mismo píxel que tendría un dato de 110 °C en este eje.
    expect(resuelta.forma.posicion.pixelY).toBe(yAPixel(110, vista, AREA.alto));
    expect(resuelta.etiqueta).toContain("110");
  });

  it("un tope por encima del rango visible se ancla arriba, no desaparece", () => {
    const vista: Vista = { t0: 0, t1: 60, v0: 0, v1: 50 };
    const linea: LineaTope = {
      id: "x",
      nivel: "aviso",
      limite: { tipo: "constante", valorCanonico: 80 },
    };
    const geometria = calcularGeometriaTopes(config({ vista, lineas: [linea] }));
    expect(geometria.lineas[0]!.forma).toEqual({ tipo: "plano", posicion: { tipo: "fuera-arriba" } });
  });

  it("un tope por debajo del rango visible se ancla abajo, no desaparece", () => {
    const vista: Vista = { t0: 0, t1: 60, v0: 50, v1: 100 };
    const linea: LineaTope = {
      id: "x",
      nivel: "critico",
      limite: { tipo: "constante", valorCanonico: 10 },
    };
    const geometria = calcularGeometriaTopes(config({ vista, lineas: [linea] }));
    expect(geometria.lineas[0]!.forma).toEqual({ tipo: "plano", posicion: { tipo: "fuera-abajo" } });
  });

  it("un tope justo en el borde superior (v1) cuenta como dentro, no fuera", () => {
    const vista: Vista = { t0: 0, t1: 60, v0: 0, v1: 50 };
    const linea: LineaTope = { id: "x", nivel: "aviso", limite: { tipo: "constante", valorCanonico: 50 } };
    const geometria = calcularGeometriaTopes(config({ vista, lineas: [linea] }));
    expect(geometria.lineas[0]!.forma.tipo).toBe("plano");
    if (geometria.lineas[0]!.forma.tipo === "plano") {
      expect(geometria.lineas[0]!.forma.posicion).toEqual({ tipo: "dentro", pixelY: 0 });
    }
  });

  it("la etiqueta sin texto propio es solo el valor formateado", () => {
    const linea: LineaTope = { id: "x", nivel: "aviso", limite: { tipo: "constante", valorCanonico: 12.5 } };
    const geometria = calcularGeometriaTopes(config({ lineas: [linea] }));
    expect(geometria.lineas[0]!.etiqueta).toBe("12,50");
  });

  it("la etiqueta con texto propio antepone el texto al valor", () => {
    const linea: LineaTope = {
      id: "x",
      nivel: "critico",
      etiqueta: "aceite mínimo",
      limite: { tipo: "constante", valorCanonico: 3 },
    };
    const geometria = calcularGeometriaTopes(config({ lineas: [linea] }));
    expect(geometria.lineas[0]!.etiqueta).toBe("aceite mínimo 3,00");
  });

  it("respeta el número de decimales pedido", () => {
    const linea: LineaTope = { id: "x", nivel: "aviso", limite: { tipo: "constante", valorCanonico: 12.345 } };
    const geometria = calcularGeometriaTopes(config({ lineas: [linea], decimales: 0 }));
    expect(geometria.lineas[0]!.etiqueta).toBe("12");
  });

  it("conserva el orden y el `id` de entrada, uno a uno", () => {
    const lineas: LineaTope[] = [
      { id: "a", nivel: "aviso", limite: { tipo: "constante", valorCanonico: 1 } },
      { id: "b", nivel: "critico", limite: { tipo: "constante", valorCanonico: 2 } },
    ];
    const geometria = calcularGeometriaTopes(config({ lineas }));
    expect(geometria.lineas.map((l) => l.id)).toEqual(["a", "b"]);
    expect(geometria.lineas.map((l) => l.nivel)).toEqual(["aviso", "critico"]);
  });
});

describe("calcularGeometriaTopes — curvas (D10: presión de aceite según régimen)", () => {
  it("convierte cada punto con la MISMA conversión canónica→mostrada que una línea plana", () => {
    const vista: Vista = { t0: 0, t1: 10, v0: 0, v1: 200 };
    const linea: LineaTope = {
      id: "d10",
      nivel: "critico",
      limite: {
        tipo: "curva",
        puntos: [
          { t: 0, valorCanonico: 100 },
          { t: 5, valorCanonico: 150 },
          { t: 10, valorCanonico: 200 },
        ],
      },
    };
    const geometria = calcularGeometriaTopes(config({ vista, lineas: [linea] }));
    const forma = geometria.lineas[0]!.forma;
    expect(forma.tipo).toBe("curva");
    if (forma.tipo !== "curva") throw new Error("se esperaba una curva");
    expect(forma.puntos).toHaveLength(3);
    expect(forma.puntos[1]!.y).toBe(yAPixel(150, vista, AREA.alto));
  });

  it("filtra los puntos fuera del tramo de tiempo visible", () => {
    const vista: Vista = { t0: 2, t1: 8, v0: 0, v1: 200 };
    const linea: LineaTope = {
      id: "d10",
      nivel: "critico",
      limite: {
        tipo: "curva",
        puntos: [
          { t: 0, valorCanonico: 100 }, // fuera, antes de t0
          { t: 5, valorCanonico: 150 }, // dentro
          { t: 20, valorCanonico: 200 }, // fuera, después de t1
        ],
      },
    };
    const geometria = calcularGeometriaTopes(config({ vista, lineas: [linea] }));
    const forma = geometria.lineas[0]!.forma;
    if (forma.tipo !== "curva") throw new Error("se esperaba una curva");
    expect(forma.puntos).toHaveLength(1);
  });

  it("una curva SIN ningún punto en el tramo visible no revienta: da un array vacío", () => {
    const vista: Vista = { t0: 100, t1: 200, v0: 0, v1: 200 };
    const linea: LineaTope = {
      id: "d10",
      nivel: "critico",
      limite: { tipo: "curva", puntos: [{ t: 0, valorCanonico: 100 }] },
    };
    const geometria = calcularGeometriaTopes(config({ vista, lineas: [linea] }));
    const forma = geometria.lineas[0]!.forma;
    if (forma.tipo !== "curva") throw new Error("se esperaba una curva");
    expect(forma.puntos).toEqual([]);
  });

  it("un valor de curva fuera del rango Y visible se RECORTA a [0, area.alto], no se ancla", () => {
    // Distinto de una línea plana a propósito (ver cabecera de geometria.ts):
    // una curva es una región continua, así que su excursión se recorta.
    const vista: Vista = { t0: 0, t1: 10, v0: 0, v1: 50 };
    const linea: LineaTope = {
      id: "d10",
      nivel: "aviso",
      limite: {
        tipo: "curva",
        puntos: [
          { t: 0, valorCanonico: -1000 }, // muy por debajo del eje
          { t: 10, valorCanonico: 1000 }, // muy por encima del eje
        ],
      },
    };
    const geometria = calcularGeometriaTopes(config({ vista, lineas: [linea] }));
    const forma = geometria.lineas[0]!.forma;
    if (forma.tipo !== "curva") throw new Error("se esperaba una curva");
    expect(forma.puntos[0]!.y).toBe(AREA.alto); // recortado abajo
    expect(forma.puntos[1]!.y).toBe(0); // recortado arriba
  });
});

describe("calcularGeometriaTopes — bandas", () => {
  it("una banda constante da dos puntos a todo el ancho, en la y del valor convertido", () => {
    const vista: Vista = { t0: 0, t1: 10, v0: 0, v1: 100 };
    const banda: BandaTope = {
      id: "lambda",
      nivel: "aviso",
      minimo: { tipo: "constante", valorCanonico: 20 },
      maximo: { tipo: "constante", valorCanonico: 40 },
    };
    const geometria = calcularGeometriaTopes(config({ vista, bandas: [banda] }));
    const resuelta = geometria.bandas[0]!;
    expect(resuelta.bordeMinimo).toEqual([
      { x: 0, y: yAPixel(20, vista, AREA.alto) },
      { x: AREA.ancho, y: yAPixel(20, vista, AREA.alto) },
    ]);
    expect(resuelta.bordeMaximo).toEqual([
      { x: 0, y: yAPixel(40, vista, AREA.alto) },
      { x: AREA.ancho, y: yAPixel(40, vista, AREA.alto) },
    ]);
  });

  it("un borde de banda fuera de rango se recorta al área, no se ancla con marca", () => {
    const vista: Vista = { t0: 0, t1: 10, v0: 20, v1: 40 };
    const banda: BandaTope = {
      id: "b",
      nivel: "critico",
      minimo: { tipo: "constante", valorCanonico: 0 }, // por debajo de v0
      maximo: { tipo: "constante", valorCanonico: 1000 }, // por encima de v1
    };
    const geometria = calcularGeometriaTopes(config({ vista, bandas: [banda] }));
    const resuelta = geometria.bandas[0]!;
    expect(resuelta.bordeMinimo[0]!.y).toBe(AREA.alto);
    expect(resuelta.bordeMaximo[0]!.y).toBe(0);
  });

  it("la etiqueta de una banda muestra los dos valores convertidos", () => {
    const banda: BandaTope = {
      id: "b",
      nivel: "aviso",
      minimo: { tipo: "constante", valorCanonico: 1 },
      maximo: { tipo: "constante", valorCanonico: 2 },
    };
    const geometria = calcularGeometriaTopes(config({ bandas: [banda] }));
    expect(geometria.bandas[0]!.etiqueta).toBe("1,00…2,00");
  });

  it("una banda puede tener un borde en curva y otro constante, cada uno resuelto por su cuenta", () => {
    const vista: Vista = { t0: 0, t1: 10, v0: 0, v1: 200 };
    const banda: BandaTope = {
      id: "b",
      nivel: "aviso",
      minimo: { tipo: "constante", valorCanonico: 10 },
      maximo: { tipo: "curva", puntos: [{ t: 0, valorCanonico: 50 }, { t: 10, valorCanonico: 150 }] },
    };
    const geometria = calcularGeometriaTopes(config({ vista, bandas: [banda] }));
    const resuelta = geometria.bandas[0]!;
    expect(resuelta.bordeMinimo).toHaveLength(2); // constante: dos puntos a todo el ancho
    expect(resuelta.bordeMaximo).toHaveLength(2); // curva: dos muestras
    expect(resuelta.bordeMaximo[1]!.y).toBe(yAPixel(150, vista, AREA.alto));
  });
});

describe("calcularGeometriaTopes — conversión no afín y parametrizada", () => {
  it("una conversión recíproca (λ↔φ) se aplica igual que a cualquier valor de clase punto", () => {
    // λ 0,8 → φ = a/λ = 1/0,8 = 1,25 (docs/06 §6.7, caso conocido λ↔φ).
    const reciproca: Conversion = { tipo: "reciproca", a: 1 };
    const linea: LineaTope = { id: "x", nivel: "aviso", limite: { tipo: "constante", valorCanonico: 0.8 } };
    const geometria = calcularGeometriaTopes(config({ conversion: reciproca, lineas: [linea] }));
    expect(geometria.lineas[0]!.etiqueta).toBe("1,25");
  });

  it("una conversión parametrizada (λ→AFR) usa el parámetro pasado en la configuración", () => {
    const parametrizada: Conversion = { tipo: "parametrizada", parametroRol: "stoichiometry", aPorOmision: 14.7 };
    const linea: LineaTope = { id: "x", nivel: "aviso", limite: { tipo: "constante", valorCanonico: 1 } };
    const conE85 = calcularGeometriaTopes(
      config({ conversion: parametrizada, parametro: 9.77, lineas: [linea] }),
    );
    expect(conE85.lineas[0]!.etiqueta).toBe("9,77");
  });
});

describe("calcularGeometriaTopes — sin topes", () => {
  it("sin líneas ni bandas devuelve arrays vacíos, sin reventar", () => {
    const geometria = calcularGeometriaTopes(config());
    expect(geometria.lineas).toEqual([]);
    expect(geometria.bandas).toEqual([]);
    expect(geometria.area).toEqual(AREA);
  });
});
