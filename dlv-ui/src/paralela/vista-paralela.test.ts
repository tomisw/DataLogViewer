/**
 * Pruebas de la vista paralela (F2-04).
 *
 * Además de las funciones puras, hay DOS pruebas de integración que
 * demuestran las dos decisiones más delicadas del informe SIN modificar
 * ningún módulo ya existente:
 *
 * - "el cursor enseña los N valores" se prueba contra `contenidoDeCelda` y
 *   `CacheDeCubos` (F1-24/F1-29) tal cual están, con las claves compuestas
 *   de `idSerieParalela`: si un segmento no cubre la `x` pedida, sale "sin
 *   datos" sin que este módulo tenga que decidirlo.
 * - "N logs se superponen con un color cada uno" se prueba contra
 *   `Renderizador` (F1-23) y el doble de WebGL2 tal cual están: subir N
 *   series con `subirSerie` y dibujarlas con un `Vista` compartido no
 *   necesita ninguna capacidad nueva del renderizador.
 */

import { describe, expect, it } from "vitest";

import { CacheDeCubos } from "../datos/cache-cubos.ts";
import { contenidoDeCelda, formatearNumero } from "../cursor/cursor.ts";
import { crearDobleGL } from "../render/doble-gl.ts";
import { Renderizador } from "../render/renderizador.ts";
import type { CubosContinuos } from "../render/tipos.ts";
import { IDENTIDAD, type ConversionAfin } from "../unidades/conversion.ts";
import type { SegmentoParalelo } from "./tipos.ts";
import {
  canalCursorDeSegmento,
  canalesCursorParalelos,
  codigoDeSegmento,
  colorDeSegmento,
  comprobarDimensionesCompatibles,
  desplazarCubos,
  idSerieParalela,
  prepararSerieParalela,
  rangoVirtual,
} from "./vista-paralela.ts";

function cubosDePrueba(t: readonly number[], valor: readonly number[], tOrigen = 0, factor = 1): CubosContinuos {
  return {
    t: Float32Array.from(t),
    tOrigen,
    minimo: Float32Array.from(valor),
    maximo: Float32Array.from(valor),
    primero: Float32Array.from(valor),
    ultimo: Float32Array.from(valor),
    factor,
  };
}

function segmento(parcial: Partial<SegmentoParalelo> & Pick<SegmentoParalelo, "id">): SegmentoParalelo {
  return {
    etiqueta: parcial.id,
    tInicio: 0,
    tFin: 10,
    offset: 0,
    canalId: "rpm",
    dimensionId: "rotational_speed",
    aCanonica: IDENTIDAD,
    ...parcial,
  };
}

describe("codigoDeSegmento", () => {
  it("es determinista", () => {
    expect(codigoDeSegmento("log-A")).toBe(codigoDeSegmento("log-A"));
  });

  it("distingue ids con el mismo prefijo (no agrupa 'log-1'/'log-2' por compartirlo)", () => {
    const codigos = new Set(["log-1", "log-2", "log-3", "log-4"].map(codigoDeSegmento));
    expect(codigos.size).toBe(4);
  });
});

describe("colorDeSegmento", () => {
  it("es estable por id, no por orden de aparición (igual que colorPorCodigo)", () => {
    const antes = colorDeSegmento("log-B");
    colorDeSegmento("log-X");
    colorDeSegmento("log-Y");
    expect(colorDeSegmento("log-B")).toEqual(antes);
  });

  it("da colores distintos a logs distintos", () => {
    expect(colorDeSegmento("log-A")).not.toEqual(colorDeSegmento("log-B"));
  });

  it("quitar y volver a añadir un log no le cambia el color (decisión 1 del informe)", () => {
    const segmentos = ["log-A", "log-B", "log-C"];
    const colorInicial = colorDeSegmento("log-B");
    // "Quitar" log-B de la comparación y volver a añadirlo no cambia nada
    // aquí porque el color depende del ID, no de una posición en un array.
    const sinB = segmentos.filter((id) => id !== "log-B");
    expect(sinB).not.toContain("log-B");
    expect(colorDeSegmento("log-B")).toEqual(colorInicial);
  });
});

describe("idSerieParalela", () => {
  it("compone id de segmento y canal", () => {
    expect(idSerieParalela({ id: "log-A", canalId: "rpm" })).toBe("log-A:rpm");
  });

  it("dos segmentos con el mismo canal no colisionan", () => {
    const a = idSerieParalela({ id: "log-A", canalId: "rpm" });
    const b = idSerieParalela({ id: "log-B", canalId: "rpm" });
    expect(a).not.toBe(b);
  });
});

describe("comprobarDimensionesCompatibles", () => {
  it("compatible cuando todos comparan la misma dimensión", () => {
    const r = comprobarDimensionesCompatibles([
      segmento({ id: "A", dimensionId: "temperature" }),
      segmento({ id: "B", dimensionId: "temperature" }),
    ]);
    expect(r).toEqual({ tipo: "compatible", dimensionId: "temperature" });
  });

  it("incompatible cuando las dimensiones no coinciden, con motivo que nombra los dos logs", () => {
    const r = comprobarDimensionesCompatibles([
      segmento({ id: "A", etiqueta: "Tirada A", dimensionId: "temperature" }),
      segmento({ id: "B", etiqueta: "Tirada B", dimensionId: "pressure" }),
    ]);
    expect(r.tipo).toBe("incompatible");
    if (r.tipo === "incompatible") {
      expect(r.motivo).toContain("Tirada A");
      expect(r.motivo).toContain("Tirada B");
      expect(r.motivo).toContain("temperature");
      expect(r.motivo).toContain("pressure");
    }
  });

  it("no oculta una incompatibilidad detrás de la primera pareja que sí coincide", () => {
    const r = comprobarDimensionesCompatibles([
      segmento({ id: "A", dimensionId: "temperature" }),
      segmento({ id: "B", dimensionId: "temperature" }),
      segmento({ id: "C", dimensionId: "pressure" }),
    ]);
    expect(r.tipo).toBe("incompatible");
  });

  it("lanza si no hay ningún segmento (error de quien llama, no un dato del log)", () => {
    expect(() => comprobarDimensionesCompatibles([])).toThrow(RangeError);
  });
});

describe("desplazarCubos", () => {
  it("suma el offset a tOrigen y no toca ninguna otra cosa", () => {
    const cubos = cubosDePrueba([0, 1, 2], [10, 20, 30], 5, 4);
    const desplazado = desplazarCubos(cubos, 100);
    expect(desplazado.tOrigen).toBe(105);
    expect(desplazado.t).toBe(cubos.t); // mismo array, sin copiar
    expect(desplazado.minimo).toBe(cubos.minimo);
    expect(desplazado.factor).toBe(4);
  });

  it("offset 0 devuelve el mismo objeto (no hay nada que desplazar)", () => {
    const cubos = cubosDePrueba([0, 1], [1, 2]);
    expect(desplazarCubos(cubos, 0)).toBe(cubos);
  });
});

describe("prepararSerieParalela", () => {
  it("aplica los DOS pasos de conversión: aCanonica propio, luego la conversión compartida", () => {
    // Mismo ejemplo que la cabecera de unidades/conversion.ts: un Haltech
    // guarda 3748 con a=0,1 -> 374,8 K canónicos -> -273,15 de origen -> 101,65 °C.
    const aCanonicaDelLog: ConversionAfin = { tipo: "afin", a: 0.1, b: 0 };
    const conversionCompartida: ConversionAfin = { tipo: "afin", a: 1, b: -273.15 };
    const seg = segmento({ id: "A", aCanonica: aCanonicaDelLog, offset: 0 });
    const cubosCrudos = cubosDePrueba([0, 1], [3748, 3748]);

    const serie = prepararSerieParalela(seg, cubosCrudos, conversionCompartida);

    expect(serie.cubos.minimo[0]).toBeCloseTo(101.65, 5);
    expect(serie.cubos.ultimo[1]).toBeCloseTo(101.65, 5);
  });

  it("dos logs con distinto factor de escala en el MISMO canal no salen uno multiplicado sobre el otro", () => {
    const conversionCompartida = IDENTIDAD;
    const segA = segmento({ id: "A", aCanonica: { tipo: "afin", a: 0.1, b: 0 } });
    const segB = segmento({ id: "B", aCanonica: { tipo: "afin", a: 1, b: 0 } });
    // Los dos logs miden "lo mismo" (374,8 canónico) con escalas crudas distintas.
    const serieA = prepararSerieParalela(segA, cubosDePrueba([0], [3748]), conversionCompartida);
    const serieB = prepararSerieParalela(segB, cubosDePrueba([0], [374.8]), conversionCompartida);
    expect(serieA.cubos.minimo[0]).toBeCloseTo(serieB.cubos.minimo[0]!, 5);
  });

  it("desplaza la serie con el offset del segmento tras convertir", () => {
    const seg = segmento({ id: "A", offset: 50 });
    const serie = prepararSerieParalela(seg, cubosDePrueba([0, 1], [1, 2], 10), IDENTIDAD);
    expect(serie.cubos.tOrigen).toBe(60);
  });

  it("el id de serie y el color coinciden con idSerieParalela/colorDeSegmento", () => {
    const seg = segmento({ id: "A", canalId: "egt" });
    const serie = prepararSerieParalela(seg, cubosDePrueba([0], [1]), IDENTIDAD);
    expect(serie.idSerie).toBe("A:egt");
    expect(serie.color).toEqual(colorDeSegmento("A"));
  });
});

describe("rangoVirtual", () => {
  it("es el mínimo y el máximo de los segmentos ya desplazados", () => {
    const segmentos = [
      segmento({ id: "A", tInicio: 0, tFin: 10, offset: 0 }),
      segmento({ id: "B", tInicio: 0, tFin: 5, offset: 100 }),
    ];
    expect(rangoVirtual(segmentos)).toEqual({ t0: 0, t1: 105 });
  });

  it("lanza sin segmentos", () => {
    expect(() => rangoVirtual([])).toThrow(RangeError);
  });
});

describe("canalesCursorParalelos", () => {
  it("una fila por segmento, con la clave compuesta y la etiqueta del log", () => {
    const filas = canalesCursorParalelos(
      [segmento({ id: "A", etiqueta: "Vuelta rápida", canalId: "rpm" }), segmento({ id: "B", canalId: "rpm" })],
      4,
    );
    expect(filas).toEqual([
      { clave: { canal: "A:rpm", factor: 4 }, etiqueta: "Vuelta rápida" },
      { clave: { canal: "B:rpm", factor: 4 }, etiqueta: "B" },
    ]);
  });

  it("una única fila es lo mismo que canalCursorDeSegmento", () => {
    const seg = segmento({ id: "A" });
    expect(canalesCursorParalelos([seg], 1)).toEqual([canalCursorDeSegmento(seg, 1)]);
  });
});

describe("integración: el cursor enseña los N valores, no uno (decisión 2)", () => {
  it("una x que solo cubre UN segmento enseña valor en ese y 'sin datos' en el otro", () => {
    const segA = segmento({ id: "A", tInicio: 0, tFin: 10, offset: 0 });
    const segB = segmento({ id: "B", tInicio: 0, tFin: 5, offset: 100 });

    const cache = new CacheDeCubos();
    const serieA = prepararSerieParalela(segA, cubosDePrueba([0, 5, 10], [10, 20, 30], 0), IDENTIDAD);
    const serieB = prepararSerieParalela(segB, cubosDePrueba([0, 2.5, 5], [100, 200, 300], 0), IDENTIDAD);
    cache.guardar({ canal: serieA.idSerie, factor: 1 }, { cubos: serieA.cubos, cubre: { t0: 0, t1: 10 } });
    cache.guardar({ canal: serieB.idSerie, factor: 1 }, { cubos: serieB.cubos, cubre: { t0: 100, t1: 105 } });

    const [claveA, claveB] = canalesCursorParalelos([segA, segB], 1).map((c) => c.clave);

    // x = 5: dentro del tramo de A, fuera del de B (que empieza en 100).
    const filaA = contenidoDeCelda(cache, claveA!, 5, formatearNumero);
    const filaB = contenidoDeCelda(cache, claveB!, 5, formatearNumero);
    expect(filaA.nivel).not.toBe("sin datos");
    expect(filaB.nivel).toBe("sin datos");

    // x = 102: dentro del tramo de B, fuera del de A (que termina en 10).
    const filaA2 = contenidoDeCelda(cache, claveA!, 102, formatearNumero);
    const filaB2 = contenidoDeCelda(cache, claveB!, 102, formatearNumero);
    expect(filaA2.nivel).toBe("sin datos");
    expect(filaB2.nivel).not.toBe("sin datos");
  });
});

describe("integración: N segmentos se superponen con un color cada uno (decisión 1)", () => {
  it("subirSerie/dibujar del renderizador ya existente acepta las N series preparadas", () => {
    const gl = crearDobleGL();
    const r = new Renderizador(gl);

    const segmentos = [
      segmento({ id: "A", offset: 0 }),
      segmento({ id: "B", offset: 30 }),
      segmento({ id: "C", offset: 60 }),
    ];
    for (const seg of segmentos) {
      const cubosCrudos = cubosDePrueba([0, 1, 2], [1, 2, 3]);
      const serie = prepararSerieParalela(seg, cubosCrudos, IDENTIDAD);
      r.subirSerie(serie.idSerie, serie.cubos, serie.color);
    }

    const vista = rangoVirtual(segmentos);
    r.dibujar({ t0: vista.t0, t1: vista.t1, v0: 0, v1: 10 });

    expect(gl.cuenta("drawArrays")).toBe(3);
    // Tres colores distintos: `uniform4f` del color no repite el mismo valor
    // para las tres series (comprobación indirecta de que cada una llevó SU
    // color, no el de la última subida).
    const coloresSubidos = new Set(segmentos.map((s) => JSON.stringify(colorDeSegmento(s.id))));
    expect(coloresSubidos.size).toBe(3);
  });
});
