/**
 * Pruebas de los comparadores puros de F5-12. Deterministas y sin GPU: lo que
 * comprueban aquí es la lógica de comparación en sí, sobre búferes de píxeles
 * fabricados a mano, no un render real (eso es `suite-navegador.ts`, con
 * navegador). Es la parte de la tarea que SÍ se puede ejecutar y comprobar en
 * este entorno.
 */

import { describe, expect, it } from "vitest";

import {
  type BufferDePixeles,
  type ColorRGB,
  colorEnPixel,
  coloresAproximados,
  contarPixelesNoFondo,
  hayColorCerca,
  RADIO_BUSQUEDA_PX,
  TOLERANCIA_CANAL_COLOR,
} from "./invariantes.ts";

const NEGRO: ColorRGB = { r: 0, g: 0, b: 0 };
const AZUL: ColorRGB = { r: 60, g: 140, b: 255 };

/** Un búfer `ancho`×`alto` de color `fondo`, con `puntos` pintados encima. */
function buffer(
  ancho: number,
  alto: number,
  fondo: ColorRGB,
  puntos: readonly { columna: number; filaDesdeAbajo: number; color: ColorRGB }[],
): BufferDePixeles {
  const datos = new Uint8Array(ancho * alto * 4);
  for (let i = 0; i < ancho * alto; i += 1) {
    datos[i * 4] = fondo.r;
    datos[i * 4 + 1] = fondo.g;
    datos[i * 4 + 2] = fondo.b;
    datos[i * 4 + 3] = 255;
  }
  for (const p of puntos) {
    const indice = (p.filaDesdeAbajo * ancho + p.columna) * 4;
    datos[indice] = p.color.r;
    datos[indice + 1] = p.color.g;
    datos[indice + 2] = p.color.b;
    datos[indice + 3] = 255;
  }
  return { datos, ancho, alto };
}

describe("colorEnPixel", () => {
  it("lee el color en una coordenada válida", () => {
    const b = buffer(4, 4, NEGRO, [{ columna: 2, filaDesdeAbajo: 1, color: AZUL }]);
    expect(colorEnPixel(b, 2, 1)).toEqual(AZUL);
    expect(colorEnPixel(b, 0, 0)).toEqual(NEGRO);
  });

  it("devuelve null fuera del búfer en cualquier borde", () => {
    const b = buffer(4, 4, NEGRO, []);
    expect(colorEnPixel(b, -1, 0)).toBeNull();
    expect(colorEnPixel(b, 0, -1)).toBeNull();
    expect(colorEnPixel(b, 4, 0)).toBeNull();
    expect(colorEnPixel(b, 0, 4)).toBeNull();
  });
});

describe("coloresAproximados", () => {
  it("es verdadero con colores idénticos", () => {
    expect(coloresAproximados(AZUL, AZUL)).toBe(true);
  });

  it("acepta una diferencia justo en el límite de la tolerancia", () => {
    const cercano: ColorRGB = {
      r: AZUL.r + TOLERANCIA_CANAL_COLOR,
      g: AZUL.g - TOLERANCIA_CANAL_COLOR,
      b: AZUL.b,
    };
    expect(coloresAproximados(AZUL, cercano)).toBe(true);
  });

  it("rechaza una diferencia de un solo canal por encima de la tolerancia", () => {
    const lejano: ColorRGB = { r: AZUL.r + TOLERANCIA_CANAL_COLOR + 1, g: AZUL.g, b: AZUL.b };
    expect(coloresAproximados(AZUL, lejano)).toBe(false);
  });

  it("respeta una tolerancia distinta pasada explícitamente", () => {
    const lejano: ColorRGB = { r: AZUL.r + 50, g: AZUL.g, b: AZUL.b };
    expect(coloresAproximados(AZUL, lejano, 100)).toBe(true);
  });
});

describe("hayColorCerca — invariante de posición", () => {
  it("encuentra el color exactamente en el punto pedido", () => {
    const b = buffer(20, 20, NEGRO, [{ columna: 10, filaDesdeAbajo: 10, color: AZUL }]);
    expect(hayColorCerca(b, 10, 10, AZUL)).toBe(true);
  });

  it("lo encuentra desplazado dentro del radio (el 'ruido de rasterización')", () => {
    const b = buffer(20, 20, NEGRO, [{ columna: 12, filaDesdeAbajo: 9, color: AZUL }]);
    // A dos píxeles del punto pedido (10, 10): dentro de RADIO_BUSQUEDA_PX.
    expect(hayColorCerca(b, 10, 10, AZUL)).toBe(true);
  });

  it("lo encuentra justo en el borde de RADIO_BUSQUEDA_PX, y no un píxel más allá", () => {
    const b = buffer(30, 30, NEGRO, [
      { columna: 10 + RADIO_BUSQUEDA_PX, filaDesdeAbajo: 10, color: AZUL },
    ]);
    expect(hayColorCerca(b, 10, 10, AZUL)).toBe(true);

    const masAlla = buffer(30, 30, NEGRO, [
      { columna: 10 + RADIO_BUSQUEDA_PX + 1, filaDesdeAbajo: 10, color: AZUL },
    ]);
    expect(hayColorCerca(masAlla, 10, 10, AZUL)).toBe(false);
  });

  it("NO lo encuentra fuera del radio — esto es lo que cazaría un eje desplazado", () => {
    const b = buffer(30, 30, NEGRO, [{ columna: 20, filaDesdeAbajo: 10, color: AZUL }]);
    expect(hayColorCerca(b, 10, 10, AZUL)).toBe(false);
  });

  it("no confunde el color de una serie vecina con el esperado", () => {
    const otraSerie: ColorRGB = { r: 255, g: 60, b: 60 };
    const b = buffer(20, 20, NEGRO, [{ columna: 10, filaDesdeAbajo: 10, color: otraSerie }]);
    expect(hayColorCerca(b, 10, 10, AZUL)).toBe(false);
  });

  it("respeta un radio explícito distinto del de omisión", () => {
    const b = buffer(20, 20, NEGRO, [{ columna: 10, filaDesdeAbajo: 15, color: AZUL }]);
    expect(hayColorCerca(b, 10, 10, AZUL, 5)).toBe(true);
    expect(hayColorCerca(b, 10, 10, AZUL, 2)).toBe(false);
  });
});

describe("contarPixelesNoFondo — invariante de cobertura", () => {
  it("cuenta exactamente los píxeles distintos del fondo en un búfer fabricado", () => {
    const puntos = [
      { columna: 1, filaDesdeAbajo: 1, color: AZUL },
      { columna: 2, filaDesdeAbajo: 1, color: AZUL },
      { columna: 3, filaDesdeAbajo: 1, color: AZUL },
    ];
    const b = buffer(10, 10, NEGRO, puntos);
    expect(contarPixelesNoFondo(b, NEGRO)).toBe(3);
  });

  it("da cero cuando todo el búfer es fondo", () => {
    const b = buffer(8, 8, NEGRO, []);
    expect(contarPixelesNoFondo(b, NEGRO)).toBe(0);
  });

  it("no cuenta un fondo con una diferencia dentro de tolerancia", () => {
    const casiNegro: ColorRGB = { r: 5, g: 5, b: 5 };
    const b = buffer(6, 6, casiNegro, []);
    expect(contarPixelesNoFondo(b, NEGRO)).toBe(0);
  });
});
