/**
 * Pruebas de `comparar-mallas.ts` (F4-08): las cuatro decisiones de la
 * cabecera del módulo — clase INTERVALO siempre, bordes incompatibles se
 * rechazan, celda vacía en un lado no es diferencia cero, y la confianza se
 * combina con el mínimo.
 */

import { describe, expect, it } from "vitest";

import type { Conversion } from "../unidades/conversion.ts";
import { convertirValor, ErrorDeUnidad } from "../unidades/conversion.ts";
import type { UnidadInfo } from "../unidades/tipos.ts";
import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Color } from "../render/tipos.ts";
import type { CeldaEstadisticas, MallaResuelta } from "../malla/tipos.ts";
import { calcularGeometriaMapaDeCalor } from "../malla/geometria.ts";
import {
  comprobarBordesCompatibles,
  compararMallas,
  resolverMapaComparacion,
  type ConfiguracionComparacionMallas,
} from "./comparar-mallas.ts";

const AREA: AreaDibujo = { x: 0, y: 0, ancho: 100, alto: 100 };
const GRIS: Color = { r: 0.5, g: 0.5, b: 0.5, a: 1 };

function celda(parcial: Partial<CeldaEstadisticas> = {}): CeldaEstadisticas {
  return { cuenta: 0, media: NaN, desviacionTipica: NaN, minimo: NaN, maximo: NaN, ...parcial };
}

/** Malla 1×2: bordesFila = [0, 1], bordesColumna = [0, 1, 2]. */
function malla(celdas: readonly CeldaEstadisticas[], bordesColumna: readonly number[] = [0, 1, 2]): MallaResuelta {
  return { bordesFila: [0, 1], bordesColumna, celdas };
}

const UNIDAD_IDENTIDAD: UnidadInfo = {
  id: "grados",
  etiqueta: "°",
  decimales: 2,
  conversion: { tipo: "afin", a: 1, b: 0 },
};

const UNIDAD_K_A_DEGC: UnidadInfo = {
  id: "degc",
  etiqueta: "°C",
  decimales: 2,
  conversion: { tipo: "afin", a: 1, b: -273.15 },
};

const UNIDAD_PHI: UnidadInfo = {
  id: "phi",
  etiqueta: "φ",
  decimales: 3,
  conversion: { tipo: "reciproca", a: 1 } as Conversion,
};

function config(parcial: Partial<ConfiguracionComparacionMallas> = {}): ConfiguracionComparacionMallas {
  return {
    area: AREA,
    // Medias distintas a propósito: si antes y después coincidieran en las dos
    // celdas, la diferencia sería uniformemente 0 y `escalaMaximaDesdeDatos`
    // no tendría rango que deducir (0 es un rango degenerado, ver la cabecera
    // de `escala-divergente.ts`) — el caso "activo" por omisión necesita algo
    // que colorear.
    mallaAntes: malla([celda({ cuenta: 10, media: 8 }), celda({ cuenta: 10, media: 5 })]),
    mallaDespues: malla([celda({ cuenta: 10, media: 5 }), celda({ cuenta: 10, media: 5 })]),
    forma: { filas: 1, columnas: 2 },
    unidadActiva: UNIDAD_IDENTIDAD,
    umbralConfianza: 5,
    colorSinDatos: GRIS,
    ...parcial,
  };
}

describe("comprobarBordesCompatibles — decisión 2: bordes distintos se rechazan", () => {
  it("los mismos bordes (misma referencia de valores) son compatibles", () => {
    const a = malla([celda()]);
    const b = malla([celda()]);
    expect(comprobarBordesCompatibles(a, b)).toEqual({ tipo: "compatibles" });
  });

  it("bordesColumna (MAP) con un valor distinto: incompatibles, y el motivo menciona MAP", () => {
    const a = malla([celda(), celda()], [0, 1, 2]);
    const b = malla([celda(), celda()], [0, 1, 3]); // el último borde difiere
    const resultado = comprobarBordesCompatibles(a, b);
    expect(resultado.tipo).toBe("incompatibles");
    if (resultado.tipo !== "incompatibles") throw new Error("se esperaba incompatibles");
    expect(resultado.motivo).toContain("MAP");
  });

  it("bordesFila (RPM) con distinta longitud: incompatibles, y el motivo menciona RPM", () => {
    const a: MallaResuelta = { bordesFila: [0, 1, 2], bordesColumna: [0, 1], celdas: [celda(), celda()] };
    const b: MallaResuelta = { bordesFila: [0, 2], bordesColumna: [0, 1], celdas: [celda()] };
    const resultado = comprobarBordesCompatibles(a, b);
    expect(resultado.tipo).toBe("incompatibles");
    if (resultado.tipo !== "incompatibles") throw new Error("se esperaba incompatibles");
    expect(resultado.motivo).toContain("RPM");
  });

  it("bordes que solo se parecen (deducidos por separado, muy cerca pero no iguales) SÍ son incompatibles: sin tolerancia", () => {
    const a = malla([celda()], [0, 1, 9.999999]);
    const b = malla([celda()], [0, 1, 10.0]);
    expect(comprobarBordesCompatibles(a, b).tipo).toBe("incompatibles");
  });
});

describe("compararMallas — decisión 1: la diferencia es antes - despues, celda a celda", () => {
  it("resta media, desviacionTipica, minimo y maximo; cuenta es el mínimo de las dos", () => {
    const antes = malla([
      celda({ cuenta: 20, media: 10, desviacionTipica: 2, minimo: 5, maximo: 15 }),
    ], [0, 1]);
    const despues = malla([
      celda({ cuenta: 8, media: 7, desviacionTipica: 1, minimo: 4, maximo: 9 }),
    ], [0, 1]);
    const diferencia = compararMallas(antes, despues)!;
    expect(diferencia).not.toBeNull();
    const c = diferencia.celdas[0]!;
    expect(c.cuenta).toBe(8); // min(20, 8)
    expect(c.media).toBeCloseTo(3); // 10 - 7
    expect(c.desviacionTipica).toBeCloseTo(1); // 2 - 1
    expect(c.minimo).toBeCloseTo(1); // 5 - 4
    expect(c.maximo).toBeCloseTo(6); // 15 - 9
  });

  it("bordes incompatibles: devuelve null en vez de comparar celdas que no son la misma región", () => {
    const antes = malla([celda(), celda()], [0, 1, 2]);
    const despues = malla([celda(), celda()], [0, 1, 3]);
    expect(compararMallas(antes, despues)).toBeNull();
  });

  it("la malla de diferencia conserva los bordes originales (son los mismos en las dos entradas)", () => {
    const antes = malla([celda()], [0, 5]);
    const despues = malla([celda()], [0, 5]);
    const diferencia = compararMallas(antes, despues)!;
    expect(diferencia.bordesColumna).toEqual([0, 5]);
    expect(diferencia.bordesFila).toEqual([0, 1]);
  });
});

describe("compararMallas — decisión 3: celda vacía en UN log no es una diferencia de cero", () => {
  it("mallaAntes sin datos en una celda, mallaDespues con datos: la diferencia sale NaN (no 0), y cuenta es 0", () => {
    const antes = malla([celda(), celda({ cuenta: 10, media: 5 })], [0, 1, 2]);
    const despues = malla([celda({ cuenta: 10, media: 3 }), celda({ cuenta: 10, media: 5 })], [0, 1, 2]);
    const diferencia = compararMallas(antes, despues)!;
    const celdaSinAntes = diferencia.celdas[0]!;
    const celdaConLosDos = diferencia.celdas[1]!;
    expect(celdaSinAntes.cuenta).toBe(0); // min(0, 10)
    expect(Number.isNaN(celdaSinAntes.media)).toBe(true); // NO es 0: no hay comparación posible
    expect(celdaConLosDos.cuenta).toBe(10);
    expect(celdaConLosDos.media).toBeCloseTo(0); // ESTA sí es una diferencia real de cero
  });

  it("las dos mallas vacías en la misma celda: sigue siendo NaN y cuenta 0, no una coincidencia de valor", () => {
    const antes = malla([celda()], [0, 1]);
    const despues = malla([celda()], [0, 1]);
    const diferencia = compararMallas(antes, despues)!;
    expect(diferencia.celdas[0]!.cuenta).toBe(0);
    expect(Number.isNaN(diferencia.celdas[0]!.media)).toBe(true);
  });
});

describe("compararMallas — decisión 4: la confianza combinada es el mínimo, no la suma", () => {
  it("200 muestras antes y 2 después: la cuenta combinada es 2, no 202", () => {
    const antes = malla([celda({ cuenta: 200, media: 10 })], [0, 1]);
    const despues = malla([celda({ cuenta: 2, media: 9 })], [0, 1]);
    const diferencia = compararMallas(antes, despues)!;
    expect(diferencia.celdas[0]!.cuenta).toBe(2);
  });
});

describe("resolverMapaComparacion — flujo completo", () => {
  it("bordes incompatibles: «incompatibles» con un motivo, antes de mirar la unidad activa", () => {
    const resultado = resolverMapaComparacion(
      config({
        mallaAntes: malla([celda(), celda()], [0, 1, 2]),
        mallaDespues: malla([celda(), celda()], [0, 1, 3]),
        unidadActiva: UNIDAD_PHI, // aunque la unidad también sería un problema, el motivo tiene que ser el de los bordes
      }),
    );
    expect(resultado.tipo).toBe("incompatibles");
  });

  it("bordes compatibles pero unidad recíproca (φ): «deshabilitado», mismo criterio que mapa-error.ts", () => {
    const resultado = resolverMapaComparacion(config({ unidadActiva: UNIDAD_PHI }));
    expect(resultado.tipo).toBe("deshabilitado");
    if (resultado.tipo !== "deshabilitado") throw new Error("se esperaba deshabilitado");
    expect(resultado.motivo).toContain("φ");
  });

  it("unidad afín (no recíproca): «activo», y claseValor de la configuración es SIEMPRE intervalo", () => {
    const resultado = resolverMapaComparacion(config());
    expect(resultado.tipo).toBe("activo");
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    expect(resultado.configuracion.claseValor).toBe("intervalo");
  });

  it("la trampa de clase: una diferencia de 10 K convertida como intervalo NO lleva el desplazamiento de K→°C", () => {
    const resultado = resolverMapaComparacion(
      config({
        mallaAntes: malla([celda({ cuenta: 10, media: 20 })], [0, 1]),
        mallaDespues: malla([celda({ cuenta: 10, media: 10 })], [0, 1]),
        forma: { filas: 1, columnas: 1 },
        unidadActiva: UNIDAD_K_A_DEGC,
        umbralConfianza: 1,
      }),
    );
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    // Mismo tipo de prueba que "la trampa de clase" de `geometria.test.ts`
    // (F4-04): se pinta de verdad y se lee el texto formateado, no solo el
    // color. 20 - 10 = 10 K de diferencia = 10 °C de diferencia; si se
    // hubiera aplicado "punto" habría salido -263,15 (le resta el origen a
    // una diferencia, el disparate que la decisión 1 evita).
    const geometria = calcularGeometriaMapaDeCalor(resultado.configuracion);
    expect(geometria.celdas[0]!.detalle.mediaTexto).toBe("10,00");
  });

  it("sin ninguna celda con datos en los dos logs a la vez: «deshabilitado», no hay escala que deducir", () => {
    const resultado = resolverMapaComparacion(
      config({
        mallaAntes: malla([celda()], [0, 1]),
        mallaDespues: malla([celda({ cuenta: 10, media: 5 })], [0, 1]), // el otro lado SÍ tiene datos, pero no coinciden
        forma: { filas: 1, columnas: 1 },
      }),
    );
    expect(resultado.tipo).toBe("deshabilitado");
  });

  it("con escalaMaximaDiferencia explícita, se usa esa y no la deducida de los datos", () => {
    const resultado = resolverMapaComparacion(config({ escalaMaximaDiferencia: 1 }));
    if (resultado.tipo !== "activo") throw new Error("se esperaba activo");
    const colorCercaDeCero = resultado.configuracion.colorDeValor(0.05, celda());
    const colorSaturado = resultado.configuracion.colorDeValor(1, celda());
    expect(colorCercaDeCero).not.toEqual(colorSaturado);
  });
});

describe("resolverMapaComparacion — la clase intervalo con unidad recíproca no inventa un número", () => {
  it("por qué admiteClase existe: convertir directamente una diferencia con una recíproca lanza ErrorDeUnidad", () => {
    // Es la razón real detrás de la decisión 1: sin el filtro de `admiteClase`
    // en `resolverMapaComparacion`, este es el error que llegaría a pintarse.
    const RECIPROCA: Conversion = { tipo: "reciproca", a: 1 };
    expect(() => convertirValor(5, RECIPROCA, "intervalo")).toThrow(ErrorDeUnidad);
  });
});
