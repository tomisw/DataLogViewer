/**
 * Pruebas de la escena sintética y su oráculo de posición. Deterministas,
 * sin GPU: verifican que la geometría de la escena (`escenas.ts`) y la
 * conversión HSL→RGB son correctas ANTES de confiar en ellas para juzgar un
 * render real (`suite-navegador.ts`).
 */

import { describe, expect, it } from "vitest";

import {
  colorARgb255,
  colorDeSerieParaTema,
  cubosDeControl,
  hslARgb,
  longitudPixelesDeSerie,
  pixelEsperado,
  PUNTOS_PARALELA,
  PUNTOS_RECTA,
  VISTA_PRUEBA,
  VIEWPORT_PRUEBA,
} from "./escenas.ts";

describe("PUNTOS_RECTA / PUNTOS_PARALELA", () => {
  it("las dos series no se cruzan nunca dentro del dominio de t", () => {
    for (let i = 0; i < PUNTOS_RECTA.length; i += 1) {
      const recta = PUNTOS_RECTA[i]!;
      const paralela = PUNTOS_PARALELA[i]!;
      expect(paralela.tAbs).toBe(recta.tAbs);
      expect(recta.valor).toBeGreaterThan(paralela.valor);
    }
  });

  it("el punto 'centro' de la recta es el centro exacto de VISTA_PRUEBA", () => {
    const centro = PUNTOS_RECTA.find((p) => p.nombre === "centro")!;
    expect(centro.tAbs).toBe((VISTA_PRUEBA.t0 + VISTA_PRUEBA.t1) / 2);
    expect(centro.valor).toBe((VISTA_PRUEBA.v0 + VISTA_PRUEBA.v1) / 2);
  });

  it("las dos series dejan un margen de al menos el 10% en X con el borde de la vista", () => {
    // El margen en X (no en Y) es lo que garantiza que las dos esquinas de
    // fondo (`puntoDeFondoSeguro`/`puntoDeFondoSeguroOpuesto`) queden libres
    // de AMBAS series, sea cual sea su valor en Y — ver el comentario de
    // `PUNTOS_PARALELA` en `escenas.ts`.
    const anchoT = VISTA_PRUEBA.t1 - VISTA_PRUEBA.t0;
    for (const p of [...PUNTOS_RECTA, ...PUNTOS_PARALELA]) {
      expect(p.tAbs - VISTA_PRUEBA.t0).toBeGreaterThanOrEqual(anchoT * 0.1);
      expect(VISTA_PRUEBA.t1 - p.tAbs).toBeGreaterThanOrEqual(anchoT * 0.1);
    }
  });

  it("'recta' además deja margen en Y (usa sus puntos para la comprobación de posición)", () => {
    const altoV = VISTA_PRUEBA.v1 - VISTA_PRUEBA.v0;
    for (const p of PUNTOS_RECTA) {
      expect(p.valor - VISTA_PRUEBA.v0).toBeGreaterThanOrEqual(altoV * 0.1);
      expect(VISTA_PRUEBA.v1 - p.valor).toBeGreaterThanOrEqual(altoV * 0.1);
    }
  });
});

describe("cubosDeControl", () => {
  it("cada cubo colapsa a un único punto (primero=ultimo=minimo=maximo)", () => {
    const cubos = cubosDeControl(PUNTOS_RECTA, 0);
    expect(cubos.t.length).toBe(PUNTOS_RECTA.length);
    for (let i = 0; i < PUNTOS_RECTA.length; i += 1) {
      expect(cubos.minimo[i]).toBe(PUNTOS_RECTA[i]!.valor);
      expect(cubos.maximo[i]).toBe(PUNTOS_RECTA[i]!.valor);
      expect(cubos.primero[i]).toBe(PUNTOS_RECTA[i]!.valor);
      expect(cubos.ultimo[i]).toBe(PUNTOS_RECTA[i]!.valor);
    }
  });

  it("resta tOrigen de los tiempos absolutos", () => {
    const cubos = cubosDeControl(PUNTOS_RECTA, 2);
    expect(cubos.tOrigen).toBe(2);
    expect(cubos.t[0]).toBe(PUNTOS_RECTA[0]!.tAbs - 2);
  });
});

describe("pixelEsperado", () => {
  it("el centro de la vista cae en el centro exacto del viewport", () => {
    const centro = PUNTOS_RECTA.find((p) => p.nombre === "centro")!;
    const px = pixelEsperado(centro.tAbs, centro.valor, VISTA_PRUEBA, VIEWPORT_PRUEBA);
    expect(px.columna).toBe(VIEWPORT_PRUEBA.ancho / 2);
    expect(px.filaDesdeAbajo).toBe(VIEWPORT_PRUEBA.alto / 2);
  });

  it("t0,v0 (esquina inferior izquierda de la vista) cae en (0,0)", () => {
    const px = pixelEsperado(VISTA_PRUEBA.t0, VISTA_PRUEBA.v0, VISTA_PRUEBA, VIEWPORT_PRUEBA);
    expect(px.columna).toBe(0);
    expect(px.filaDesdeAbajo).toBe(0);
  });

  it("t1,v1 (esquina superior derecha de la vista) cae en (ancho,alto)", () => {
    const px = pixelEsperado(VISTA_PRUEBA.t1, VISTA_PRUEBA.v1, VISTA_PRUEBA, VIEWPORT_PRUEBA);
    expect(px.columna).toBe(VIEWPORT_PRUEBA.ancho);
    expect(px.filaDesdeAbajo).toBe(VIEWPORT_PRUEBA.alto);
  });

  it("es lineal: el punto al 25% del dominio cae al 25% del viewport", () => {
    const t25 = VISTA_PRUEBA.t0 + (VISTA_PRUEBA.t1 - VISTA_PRUEBA.t0) * 0.25;
    const v25 = VISTA_PRUEBA.v0 + (VISTA_PRUEBA.v1 - VISTA_PRUEBA.v0) * 0.25;
    const px = pixelEsperado(t25, v25, VISTA_PRUEBA, VIEWPORT_PRUEBA);
    expect(px.columna).toBe(Math.round(VIEWPORT_PRUEBA.ancho * 0.25));
    expect(px.filaDesdeAbajo).toBe(Math.round(VIEWPORT_PRUEBA.alto * 0.25));
  });

  it("es independiente del tamaño del viewport (misma fracción, viewport distinto)", () => {
    const otroViewport = { ancho: 800, alto: 100 };
    const centro = PUNTOS_RECTA.find((p) => p.nombre === "centro")!;
    const px = pixelEsperado(centro.tAbs, centro.valor, VISTA_PRUEBA, otroViewport);
    expect(px.columna).toBe(otroViewport.ancho / 2);
    expect(px.filaDesdeAbajo).toBe(otroViewport.alto / 2);
  });
});

describe("longitudPixelesDeSerie", () => {
  it("da 0 con un único punto (sin segmentos)", () => {
    expect(longitudPixelesDeSerie([PUNTOS_RECTA[0]!], VISTA_PRUEBA, VIEWPORT_PRUEBA)).toBe(0);
  });

  it("suma la distancia de Chebyshev de cada segmento", () => {
    const total = longitudPixelesDeSerie(PUNTOS_RECTA, VISTA_PRUEBA, VIEWPORT_PRUEBA);
    // La recta va de (t=2,v=20) a (t=18,v=180): en el viewport de prueba
    // (400×300) eso es una diagonal de 320 px en X y 240 px en Y — la
    // distancia de Chebyshev del tramo completo es max(320,240) = 320, y la
    // suma de los cuatro segmentos intermedios no puede ser menor (la
    // desigualdad triangular garantiza `total >= tramo completo`).
    expect(total).toBeGreaterThanOrEqual(320);
    // Tampoco puede ser mucho mayor: son cuatro segmentos de una única recta,
    // no un zigzag.
    expect(total).toBeLessThan(340);
  });
});

describe("hslARgb", () => {
  it("reproduce los seis colores puros conocidos", () => {
    const casos: readonly [number, { r: number; g: number; b: number }][] = [
      [0, { r: 255, g: 0, b: 0 }], // rojo
      [60, { r: 255, g: 255, b: 0 }], // amarillo
      [120, { r: 0, g: 255, b: 0 }], // verde
      [180, { r: 0, g: 255, b: 255 }], // cian
      [240, { r: 0, g: 0, b: 255 }], // azul
      [300, { r: 255, g: 0, b: 255 }], // magenta
    ];
    for (const [tono, esperado] of casos) {
      const rgb = colorARgb255(hslARgb(tono, 1, 0.5));
      expect(rgb).toEqual(esperado);
    }
  });

  it("saturación 0 da gris, independiente del tono", () => {
    const gris = colorARgb255(hslARgb(123, 0, 0.5));
    expect(gris).toEqual({ r: 128, g: 128, b: 128 });
  });

  it("alfa siempre 1", () => {
    expect(hslARgb(210, 0.5, 0.5).a).toBe(1);
  });
});

describe("colorDeSerieParaTema", () => {
  it("da colores distintos entre oscuro y claro (regresión de contraste)", () => {
    const oscuro = colorARgb255(colorDeSerieParaTema("oscuro", 0));
    const claro = colorARgb255(colorDeSerieParaTema("claro", 0));
    // No exige un valor exacto (eso ya lo cubre `tema.test.ts`, fuera de este
    // carril): exige que se puedan distinguir, que es lo mínimo para que la
    // comprobación de tema de F5-12 tenga algo que cazar.
    const distancia =
      Math.abs(oscuro.r - claro.r) + Math.abs(oscuro.g - claro.g) + Math.abs(oscuro.b - claro.b);
    expect(distancia).toBeGreaterThan(10);
  });

  it("alto contraste alterna luz por paridad del discriminante", () => {
    const par = colorARgb255(colorDeSerieParaTema("altContraste", 0));
    const impar = colorARgb255(colorDeSerieParaTema("altContraste", 1));
    const distancia =
      Math.abs(par.r - impar.r) + Math.abs(par.g - impar.g) + Math.abs(par.b - impar.b);
    expect(distancia).toBeGreaterThan(10);
  });

  it("es determinista: mismo tema y discriminante dan el mismo color", () => {
    const a = colorARgb255(colorDeSerieParaTema("claro", 3));
    const b = colorARgb255(colorDeSerieParaTema("claro", 3));
    expect(a).toEqual(b);
  });
});
