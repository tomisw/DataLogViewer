/**
 * Pruebas del renderizador contra el doble de WebGL2.
 *
 * La prueba que justifica todo este fichero es
 * «dibujar_no_sube_nada_a_la_gpu». El presupuesto de §2.6 —16 canales × 5 M
 * puntos a ≥ 60 fps en una GPU integrada— no se cumple dibujando rápido, se
 * cumple no volviendo a subir datos en cada fotograma. Esa es una propiedad
 * contable, comprobable sin GPU y en milisegundos; esperar a la regresión
 * visual (F5-12) para descubrir un `bufferData` dentro del bucle de dibujo
 * sería enterarse tarde y por el síntoma equivocado (tirones intermitentes).
 */

import { beforeEach, describe, expect, it } from "vitest";

import { crearDobleGL, type DobleGL } from "./doble-gl.ts";
import { Renderizador } from "./renderizador.ts";
import type { Color, CubosContinuos, Vista } from "./tipos.ts";

const AZUL: Color = { r: 0.2, g: 0.5, b: 1, a: 1 };
const VISTA: Vista = { t0: 0, t1: 10, v0: 0, v1: 100 };

function cubosDe(n: number, tOrigen = 0, factor = 1): CubosContinuos {
  const t = new Float32Array(n);
  const minimo = new Float32Array(n);
  const maximo = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = i;
    minimo[i] = Math.sin(i / 10) * 10;
    maximo[i] = minimo[i]! + 5;
  }
  return { t, tOrigen, minimo, maximo, primero: minimo, ultimo: maximo, factor };
}

describe("Renderizador", () => {
  let gl: DobleGL;
  let r: Renderizador;

  beforeEach(() => {
    gl = crearDobleGL();
    r = new Renderizador(gl);
  });

  it("dibujar no sube nada a la GPU", () => {
    r.subirSerie("rpm", cubosDe(2000), AZUL);
    r.reiniciarEstadisticas();
    gl.olvidar();

    for (let f = 0; f < 60; f += 1) {
      r.dibujar({ ...VISTA, t0: VISTA.t0 + f * 0.01, t1: VISTA.t1 + f * 0.01 });
    }

    expect(gl.cuenta("bufferData")).toBe(0);
    expect(r.estadisticas.subidasDeBufer).toBe(0);
    expect(r.estadisticas.fotogramas).toBe(60);
  });

  it("un fotograma cuesta un puñado de llamadas por serie, no una por cubo", () => {
    // 16 canales, el número exacto de §2.6.
    for (let i = 0; i < 16; i += 1) r.subirSerie(`canal-${i}`, cubosDe(2000), AZUL);
    gl.olvidar();
    r.dibujar(VISTA);

    expect(gl.cuenta("drawArrays")).toBe(16);
    // Dos uniformes (transformación y color) y un `bindVertexArray` por serie,
    // más el `bindVertexArray(null)` final: si esto crece con el número de
    // cubos, la arquitectura se rompió.
    expect(gl.cuenta("uniform4f")).toBe(32);
    expect(gl.cuenta("bindVertexArray")).toBe(17);
    expect(gl.llamadas.length).toBeLessThan(100);
  });

  it("dibuja como LINE_STRIP con cuatro vértices por cubo", () => {
    r.subirSerie("rpm", cubosDe(1000), AZUL);
    gl.olvidar();
    r.dibujar(VISTA);
    const dibujo = gl.llamadas.find((l) => l.nombre === "drawArrays");
    expect(dibujo?.argumentos[0]).toBe(gl.LINE_STRIP);
    expect(dibujo?.argumentos[2]).toBe(4000);
  });

  it("volver a subir la misma serie reutiliza el búfer y el VAO", () => {
    // Crear un búfer por cambio de nivel, con pan continuo, es una fuga de
    // memoria de GPU que en un portátil se ve como un cuelgue a los minutos.
    r.subirSerie("rpm", cubosDe(1000, 0, 1), AZUL);
    const buffers = gl.cuenta("createBuffer");
    const vaos = gl.cuenta("createVertexArray");

    r.subirSerie("rpm", cubosDe(250, 0, 4), AZUL);

    expect(gl.cuenta("createBuffer")).toBe(buffers);
    expect(gl.cuenta("createVertexArray")).toBe(vaos);
    expect(r.series).toEqual([{ id: "rpm", nVertices: 1000, factor: 4 }]);
  });

  it("cambiar el color no sube nada", () => {
    // Resaltar la serie bajo el cursor no puede costar 16 KB por fotograma.
    r.subirSerie("rpm", cubosDe(1000), AZUL);
    gl.olvidar();
    r.cambiarColor("rpm", { r: 1, g: 0, b: 0, a: 1 });
    expect(gl.cuenta("bufferData")).toBe(0);
    r.dibujar(VISTA);
    const uniformes = gl.llamadas.filter((l) => l.nombre === "uniform4f");
    expect(uniformes[1]?.argumentos.slice(1)).toEqual([1, 0, 0, 1]);
  });

  it("cambiar el color de una serie que no existe falla en vez de no hacer nada", () => {
    expect(() => r.cambiarColor("fantasma", AZUL)).toThrow(/fantasma/);
  });

  it("quitar una serie libera su búfer y su VAO", () => {
    r.subirSerie("rpm", cubosDe(100), AZUL);
    gl.olvidar();
    r.quitarSerie("rpm");
    expect(gl.cuenta("deleteBuffer")).toBe(1);
    expect(gl.cuenta("deleteVertexArray")).toBe(1);
    expect(r.series).toEqual([]);
  });

  it("quitar una serie que no existe no es un error", () => {
    expect(() => r.quitarSerie("fantasma")).not.toThrow();
  });

  it("destruir libera todo, y §2.6 pide ocho logs a la vez", () => {
    r.subirSerie("a", cubosDe(10), AZUL);
    r.subirSerie("b", cubosDe(10), AZUL);
    gl.olvidar();
    r.destruir();
    expect(gl.cuenta("deleteBuffer")).toBe(2);
    expect(gl.cuenta("deleteVertexArray")).toBe(2);
    expect(gl.cuenta("deleteProgram")).toBe(1);
  });

  it("usar un renderizador destruido falla con un mensaje que lo dice", () => {
    r.destruir();
    expect(() => r.dibujar(VISTA)).toThrow(/ya se destruyó/);
    expect(() => r.subirSerie("x", cubosDe(1), AZUL)).toThrow(/ya se destruyó/);
  });

  it("destruir dos veces no intenta liberar dos veces", () => {
    r.destruir();
    gl.olvidar();
    r.destruir();
    expect(gl.cuenta("deleteProgram")).toBe(0);
  });

  it("una vista por serie permite ejes Y distintos (la puerta de F1-27)", () => {
    r.subirSerie("rpm", cubosDe(10), AZUL);
    r.subirSerie("temp", cubosDe(10), AZUL);
    gl.olvidar();
    const porSerie = new Map<string, Vista>([["temp", { t0: 0, t1: 10, v0: -40, v1: 140 }]]);
    r.dibujar(VISTA, porSerie);

    const transformaciones = gl.llamadas
      .filter((l) => l.nombre === "uniform4f")
      .filter((_, i) => i % 2 === 0);
    // escalaY de rpm (rango 100) y de temp (rango 180) tienen que diferir.
    expect(transformaciones[0]?.argumentos[3]).not.toBe(transformaciones[1]?.argumentos[3]);
  });

  it("una serie vacía no genera llamada de dibujo", () => {
    const vacio: CubosContinuos = {
      t: new Float32Array(0),
      tOrigen: 0,
      minimo: new Float32Array(0),
      maximo: new Float32Array(0),
      primero: new Float32Array(0),
      ultimo: new Float32Array(0),
      factor: 1,
    };
    r.subirSerie("vacia", vacio, AZUL);
    gl.olvidar();
    r.dibujar(VISTA);
    expect(gl.cuenta("drawArrays")).toBe(0);
  });

  it("redimensionar llega al viewport de OpenGL", () => {
    gl.olvidar();
    r.redimensionar({ ancho: 1920, alto: 1080 });
    expect(gl.llamadas.at(-1)).toEqual({
      nombre: "viewport",
      argumentos: [0, 0, 1920, 1080],
    });
    expect(r.viewport).toEqual({ ancho: 1920, alto: 1080 });
  });
});

describe("errores de compilación", () => {
  it("un shader que no compila lleva el registro del controlador en el mensaje", () => {
    // Un «no compila» sin el motivo es lo mismo que no tener el error.
    const gl = crearDobleGL();
    gl.fallarCompilacion = true;
    expect(() => new Renderizador(gl)).toThrow(/no compila[\s\S]*registro simulado/);
  });

  it("un programa que no enlaza también", () => {
    const gl = crearDobleGL();
    gl.fallarEnlace = true;
    expect(() => new Renderizador(gl)).toThrow(/no enlaza[\s\S]*registro simulado/);
  });

  it("un shader roto no deja el shader colgando en la GPU", () => {
    const gl = crearDobleGL();
    gl.fallarCompilacion = true;
    expect(() => new Renderizador(gl)).toThrow();
    expect(gl.cuenta("deleteShader")).toBeGreaterThan(0);
  });
});
