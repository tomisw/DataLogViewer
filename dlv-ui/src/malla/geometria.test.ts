/**
 * Pruebas de `calcularGeometriaMapaDeCalor`: geometría de celdas, estado de
 * confianza y la trampa de clase de F4-04 (ver la cabecera de `tipos.ts`).
 *
 * EL CASO QUE JUSTIFICA TODA LA TAREA
 * ======================================
 * Un canal de error de 10 K convertido como `Clase.PUNTO` con una conversión
 * K→°C da −263,15 (le resta el origen a una diferencia); convertido como
 * `Clase.INTERVALO` da 10 (correcto: 10 K de diferencia son 10 °C de
 * diferencia). Es la prueba `"la trampa..."` de abajo, y es la que un fallo
 * de `claseValor` rompería en silencio: el número seguiría siendo un número,
 * solo que un disparate.
 */

import { describe, expect, it } from "vitest";

import { xAPixel, yAPixel } from "../ejes/coordenadas.ts";
import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Vista, Color } from "../render/tipos.ts";
import { ErrorDeUnidad, type Conversion } from "../unidades/conversion.ts";
import { calcularGeometriaMapaDeCalor } from "./geometria.ts";
import type { CeldaEstadisticas, ConfiguracionMapaDeCalor, MallaResuelta } from "./tipos.ts";

const AREA: AreaDibujo = { x: 0, y: 0, ancho: 200, alto: 100 };
const IDENTIDAD: Conversion = { tipo: "afin", a: 1, b: 0 };
const K_A_DEGC: Conversion = { tipo: "afin", a: 1, b: -273.15 };
const ROJO: Color = { r: 1, g: 0, b: 0, a: 1 };
const GRIS_SIN_DATOS: Color = { r: 0.5, g: 0.5, b: 0.5, a: 1 };

function celda(parcial: Partial<CeldaEstadisticas> = {}): CeldaEstadisticas {
  return { cuenta: 0, media: NaN, desviacionTipica: NaN, minimo: NaN, maximo: NaN, ...parcial };
}

/** Malla 2×2: bordesColumna = [0, 10, 20], bordesFila = [100, 200, 300]. */
function mallaBase(celdas: readonly CeldaEstadisticas[]): MallaResuelta {
  return { bordesFila: [100, 200, 300], bordesColumna: [0, 10, 20], celdas };
}

function config(parcial: Partial<ConfiguracionMapaDeCalor> = {}): ConfiguracionMapaDeCalor {
  return {
    area: AREA,
    malla: mallaBase([celda(), celda(), celda(), celda()]),
    forma: { filas: 2, columnas: 2 },
    conversion: IDENTIDAD,
    claseValor: "punto",
    umbralConfianza: 5,
    colorDeValor: () => ROJO,
    colorSinDatos: GRIS_SIN_DATOS,
    ...parcial,
  };
}

describe("calcularGeometriaMapaDeCalor — geometría de las celdas", () => {
  it("cuatro celdas de una malla 2×2 caen en los cuatro cuadrantes del área, sin solaparse", () => {
    const geometria = calcularGeometriaMapaDeCalor(
      config({ malla: mallaBase([celda({ cuenta: 5, media: 1 }), celda({ cuenta: 5, media: 1 }), celda({ cuenta: 5, media: 1 }), celda({ cuenta: 5, media: 1 })]) }),
    );
    expect(geometria.celdas).toHaveLength(4);
    // fila 0 (bordesFila [100,200], la de ABAJO) cae en el semiplano inferior del área.
    const fila0col0 = geometria.celdas.find((c) => c.fila === 0 && c.columna === 0)!;
    const fila1col0 = geometria.celdas.find((c) => c.fila === 1 && c.columna === 0)!;
    expect(fila0col0.y).toBeGreaterThan(fila1col0.y); // fila 0 está más abajo en píxeles (y mayor)
    expect(fila0col0.x).toBe(0);
    expect(fila0col0.ancho).toBe(100);
    expect(fila0col0.alto).toBe(50);

    const vista: Vista = { t0: 0, t1: 20, v0: 100, v1: 300 };
    expect(fila0col0.x).toBe(xAPixel(0, vista, AREA.ancho));
    expect(fila0col0.y).toBe(yAPixel(200, vista, AREA.alto)); // el borde de ARRIBA de la fila 0
  });

  it("las columnas cubren el ancho del área exactamente, sin huecos ni solapes", () => {
    const geometria = calcularGeometriaMapaDeCalor(config());
    const col0 = geometria.celdas.find((c) => c.fila === 0 && c.columna === 0)!;
    const col1 = geometria.celdas.find((c) => c.fila === 0 && c.columna === 1)!;
    expect(col0.x + col0.ancho).toBe(col1.x);
    expect(col1.x + col1.ancho).toBe(AREA.ancho);
  });
});

describe("calcularGeometriaMapaDeCalor — estado de confianza", () => {
  it("cuenta === 0 es «vacia»: usa colorSinDatos, NUNCA colorDeValor", () => {
    let llamadoColorDeValor = false;
    const geometria = calcularGeometriaMapaDeCalor(
      config({
        colorDeValor: () => {
          llamadoColorDeValor = true;
          return ROJO;
        },
      }),
    );
    for (const c of geometria.celdas) {
      expect(c.estado).toBe("vacia");
      expect(c.color).toEqual(GRIS_SIN_DATOS);
    }
    expect(llamadoColorDeValor).toBe(false);
  });

  it("cuenta >= umbralConfianza es «confiable»: opacidad íntegra, sin atenuar", () => {
    const geometria = calcularGeometriaMapaDeCalor(
      config({
        umbralConfianza: 5,
        malla: mallaBase([celda({ cuenta: 5, media: 1 }), celda(), celda(), celda()]),
      }),
    );
    const confiable = geometria.celdas.find((c) => c.fila === 0 && c.columna === 0)!;
    expect(confiable.estado).toBe("confiable");
    expect(confiable.color.a).toBe(1);
  });

  it("0 < cuenta < umbralConfianza es «pocaConfianza»: la opacidad se atenúa a menos cuenta, no se oculta", () => {
    const geometria = calcularGeometriaMapaDeCalor(
      config({
        umbralConfianza: 5,
        malla: mallaBase([
          celda({ cuenta: 1, media: 1 }), // mínima confianza posible
          celda({ cuenta: 3, media: 1 }), // a mitad de camino
          celda(),
          celda(),
        ]),
      }),
    );
    const unaMuestra = geometria.celdas.find((c) => c.fila === 0 && c.columna === 0)!;
    const tresMuestras = geometria.celdas.find((c) => c.fila === 0 && c.columna === 1)!;
    expect(unaMuestra.estado).toBe("pocaConfianza");
    expect(tresMuestras.estado).toBe("pocaConfianza");
    // Sigue siendo el color de la escala (rojo), pero ni una ni otra están del todo opacas...
    expect(unaMuestra.color.a).toBeGreaterThan(0);
    expect(unaMuestra.color.a).toBeLessThan(1);
    // ...y más muestras es más opacidad: una celda con más confianza no se pinta igual que una con menos.
    expect(tresMuestras.color.a).toBeGreaterThan(unaMuestra.color.a);
    expect(tresMuestras.color.a).toBeLessThan(1);
  });
});

describe("calcularGeometriaMapaDeCalor — la trampa de clase (F4-04)", () => {
  it("la trampa: un canal de error convertido como INTERVALO no lleva el desplazamiento de origen; como PUNTO sí (y da un disparate)", () => {
    const malla = mallaBase([celda({ cuenta: 10, media: 10, minimo: 5, maximo: 15 }), celda(), celda(), celda()]);

    const comoIntervalo = calcularGeometriaMapaDeCalor(
      config({ malla, conversion: K_A_DEGC, claseValor: "intervalo", umbralConfianza: 1 }),
    );
    const comoPunto = calcularGeometriaMapaDeCalor(
      config({ malla, conversion: K_A_DEGC, claseValor: "punto", umbralConfianza: 1 }),
    );

    const celdaIntervalo = comoIntervalo.celdas.find((c) => c.fila === 0 && c.columna === 0)!;
    const celdaPunto = comoPunto.celdas.find((c) => c.fila === 0 && c.columna === 0)!;

    expect(celdaIntervalo.detalle.mediaTexto).toBe("10,00"); // 10 K de diferencia = 10 °C de diferencia
    expect(celdaPunto.detalle.mediaTexto).toBe("-263,15"); // el disparate: le resta el origen a una diferencia
  });

  it("desviacionTipica es SIEMPRE intervalo, incluso cuando claseValor es punto", () => {
    const malla = mallaBase([
      celda({ cuenta: 10, media: 10, desviacionTipica: 2, minimo: 5, maximo: 15 }),
      celda(),
      celda(),
      celda(),
    ]);
    const geometria = calcularGeometriaMapaDeCalor(
      config({ malla, conversion: K_A_DEGC, claseValor: "punto", umbralConfianza: 1 }),
    );
    const c = geometria.celdas.find((x) => x.fila === 0 && x.columna === 0)!;
    expect(c.detalle.desviacionTipicaTexto).toBe("2,00"); // NO "-271,15": una dispersión no lleva el origen
    expect(c.detalle.mediaTexto).toBe("-263,15"); // la media sí, porque aquí claseValor = "punto"
  });
});

describe("calcularGeometriaMapaDeCalor — detalle por celda", () => {
  it("una celda vacía muestra «—» en las cuatro estadísticas, pero la cuenta es «0», no «—»", () => {
    const geometria = calcularGeometriaMapaDeCalor(config());
    const c = geometria.celdas[0]!;
    expect(c.detalle.cuentaTexto).toBe("0");
    expect(c.detalle.mediaTexto).toBe("—");
    expect(c.detalle.desviacionTipicaTexto).toBe("—");
    expect(c.detalle.minimoTexto).toBe("—");
    expect(c.detalle.maximoTexto).toBe("—");
  });

  it("respeta el número de decimales pedido", () => {
    const malla = mallaBase([celda({ cuenta: 10, media: 1.23456 }), celda(), celda(), celda()]);
    const geometria = calcularGeometriaMapaDeCalor(config({ malla, umbralConfianza: 1, decimales: 1 }));
    expect(geometria.celdas[0]!.detalle.mediaTexto).toBe("1,2");
  });
});

describe("calcularGeometriaMapaDeCalor — φ (unidad recíproca) y clase intervalo, la decisión de F4-04", () => {
  const RECIPROCA: Conversion = { tipo: "reciproca", a: 1 };

  it("una celda CON datos, clase intervalo y conversión recíproca: lanza ErrorDeUnidad (no inventa un número)", () => {
    const malla = mallaBase([celda({ cuenta: 10, media: 1 }), celda(), celda(), celda()]);
    expect(() =>
      calcularGeometriaMapaDeCalor(config({ malla, conversion: RECIPROCA, claseValor: "intervalo", umbralConfianza: 1 })),
    ).toThrow(ErrorDeUnidad);
  });

  it("una malla ENTERAMENTE vacía con clase intervalo y conversión recíproca NO lanza: nunca hay un valor finito que convertir", () => {
    const geometria = calcularGeometriaMapaDeCalor(
      config({ conversion: RECIPROCA, claseValor: "intervalo" }),
    );
    expect(geometria.celdas.every((c) => c.estado === "vacia")).toBe(true);
  });
});

describe("calcularGeometriaMapaDeCalor — validación de la configuración", () => {
  it("umbralConfianza <= 0 lanza: no hay un umbral sin sentido válido", () => {
    expect(() => calcularGeometriaMapaDeCalor(config({ umbralConfianza: 0 }))).toThrow(RangeError);
  });

  it("un número de celdas que no coincide con `forma` lanza en vez de ignorar las que sobran o faltan", () => {
    expect(() =>
      calcularGeometriaMapaDeCalor(config({ malla: mallaBase([celda()]), forma: { filas: 2, columnas: 2 } })),
    ).toThrow(RangeError);
  });

  it("unos bordesFila/bordesColumna que no coinciden con `forma` lanzan", () => {
    const mallaMal: MallaResuelta = {
      bordesFila: [100, 200, 300],
      bordesColumna: [0, 10], // debería tener 3 elementos para 2 columnas
      celdas: [celda(), celda(), celda(), celda()],
    };
    expect(() => calcularGeometriaMapaDeCalor(config({ malla: mallaMal }))).toThrow(RangeError);
  });
});
