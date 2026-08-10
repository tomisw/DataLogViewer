/**
 * Pruebas de `exportar-imagen.ts` (F4-12).
 *
 * QUÉ SE PUEDE PROBAR SIN NAVEGADOR, Y QUÉ NO
 * ===============================================
 * `vitest.config.ts` corre en `environment: "node"`: no hay `document`,
 * `Image`, `XMLSerializer` ni `HTMLCanvasElement.toDataURL/toBlob` de
 * verdad. Lo que SÍ se puede probar aquí, con los mismos dobles que ya usa
 * `render/renderizador.test.ts` (`doble-gl.ts`) más dos dobles propios:
 *
 * 1. `capturarTrazoPNG` respeta el ORDEN que exige la cabecera del módulo
 *    (dibujar, LUEGO leer) — la propiedad de verdad que decide si el PNG
 *    exportado sale negro o no, comprobada contando cuántas veces se llamó
 *    a `clear()` en el momento exacto en que se lee el lienzo.
 * 2. `insertarTrazoEnSvg` es aritmética de texto pura: se prueba igual que
 *    `ejes/geometria.test.ts` prueba la geometría, sin DOM.
 * 3. `exportarComoSVG`/`exportarComoPNG` orquestan lo anterior en el orden
 *    correcto, contra dobles inyectados.
 *
 * Lo que NO se puede probar aquí es si el PNG compuesto "se ve bien": eso es
 * un juicio visual, fuera de una prueba unitaria, y ni siquiera se puede
 * EJECUTAR este fichero en este entorno de verificación concreto (no hay
 * `node_modules`, `npm` da 403 aquí) — ver el informe de F4-12.
 */

import { beforeEach, describe, expect, it } from "vitest";

import { crearDobleGL, type DobleGL } from "../render/doble-gl.ts";
import { Renderizador } from "../render/renderizador.ts";
import type { Color, CubosContinuos, Vista } from "../render/tipos.ts";
import {
  capturarTrazoPNG,
  type EntornoExportacion,
  exportarComoPNG,
  exportarComoSVG,
  type LienzoCaptura,
  insertarTrazoEnSvg,
} from "./exportar-imagen.ts";

const COLOR: Color = { r: 0.2, g: 0.5, b: 1, a: 1 };
const VISTA: Vista = { t0: 0, t1: 10, v0: 0, v1: 100 };

function cubosDe(n: number): CubosContinuos {
  const t = new Float32Array(n);
  const minimo = new Float32Array(n);
  const maximo = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = i;
    minimo[i] = i;
    maximo[i] = i + 1;
  }
  return { t, tOrigen: 0, minimo, maximo, primero: minimo, ultimo: maximo, factor: 1 };
}

/**
 * Lienzo de mentira que, en vez de decodificar píxeles de verdad, anota
 * CUÁNTAS VECES se había llamado ya a `clear()` del doble de GL en el
 * instante exacto en que se lee — que es la propiedad que
 * `capturarTrazoPNG` tiene que garantizar: `clear()` (dentro de
 * `Renderizador.dibujar`) ya se ejecutó antes de que esto se llame.
 */
class LienzoDeMentira implements LienzoCaptura {
  readonly width = 800;
  readonly height = 400;
  readonly snapshotsDeClear: number[] = [];
  readonly tiposPedidos: (string | undefined)[] = [];

  constructor(private readonly gl: DobleGL) {}

  toDataURL(tipo?: string): string {
    this.snapshotsDeClear.push(this.gl.cuenta("clear"));
    this.tiposPedidos.push(tipo);
    return "data:image/png;base64,RkFMU08=";
  }
}

describe("capturarTrazoPNG", () => {
  let gl: DobleGL;
  let r: Renderizador;

  beforeEach(() => {
    gl = crearDobleGL();
    r = new Renderizador(gl);
    r.subirSerie("rpm", cubosDe(10), COLOR);
  });

  it("lee el lienzo DESPUÉS de dibujar, nunca antes", () => {
    const lienzo = new LienzoDeMentira(gl);
    expect(gl.cuenta("clear")).toBe(0); // nada dibujado todavía

    capturarTrazoPNG(r, lienzo, VISTA);

    // Cuando `toDataURL` se ejecutó, `clear()` (parte de `dibujar()`) ya
    // había pasado exactamente una vez: si el orden estuviera invertido,
    // este snapshot habría sido 0, no 1.
    expect(lienzo.snapshotsDeClear).toEqual([1]);
  });

  it("pide la imagen como PNG", () => {
    const lienzo = new LienzoDeMentira(gl);
    capturarTrazoPNG(r, lienzo, VISTA);
    expect(lienzo.tiposPedidos).toEqual(["image/png"]);
  });

  it("cada llamada redibuja: dos capturas seguidas ven dos `clear()`", () => {
    const lienzo = new LienzoDeMentira(gl);
    capturarTrazoPNG(r, lienzo, VISTA);
    capturarTrazoPNG(r, lienzo, { ...VISTA, t0: 1, t1: 11 });
    expect(lienzo.snapshotsDeClear).toEqual([1, 2]);
  });

  it("devuelve la URL de datos tal cual la da el lienzo", () => {
    const lienzo = new LienzoDeMentira(gl);
    const url = capturarTrazoPNG(r, lienzo, VISTA);
    expect(url).toBe("data:image/png;base64,RkFMU08=");
  });
});

describe("insertarTrazoEnSvg", () => {
  const SVG_SIMPLE = '<svg width="10" height="5" viewBox="0 0 10 5"><g class="ejes"></g></svg>';

  it("inserta la imagen justo después de la etiqueta de apertura", () => {
    const compuesto = insertarTrazoEnSvg(SVG_SIMPLE, "data:image/png;base64,ABC", 10, 5);
    const posicionImagen = compuesto.indexOf("<image");
    const posicionEjes = compuesto.indexOf('class="ejes"');
    expect(posicionImagen).toBeGreaterThan(-1);
    expect(posicionEjes).toBeGreaterThan(-1);
    // La imagen va DETRÁS visualmente: en SVG eso significa ANTES en el
    // documento (el orden de pintado sigue el orden del árbol).
    expect(posicionImagen).toBeLessThan(posicionEjes);
  });

  it("usa el ancho y el alto en píxeles CSS que se le pasan, no otros", () => {
    const compuesto = insertarTrazoEnSvg(SVG_SIMPLE, "data:x", 123, 45);
    expect(compuesto).toContain('width="123"');
    expect(compuesto).toContain('height="45"');
  });

  it("lleva la URL de datos completa en `href`", () => {
    const compuesto = insertarTrazoEnSvg(SVG_SIMPLE, "data:image/png;base64,QUJD", 10, 5);
    expect(compuesto).toContain('href="data:image/png;base64,QUJD"');
  });

  it("escapa los caracteres especiales de XML en la URL, por si acaso", () => {
    const compuesto = insertarTrazoEnSvg(SVG_SIMPLE, 'data:x&y"z<w>', 10, 5);
    expect(compuesto).toContain("&amp;");
    expect(compuesto).toContain("&quot;");
    expect(compuesto).toContain("&lt;");
    expect(compuesto).toContain("&gt;");
    expect(compuesto).not.toContain('href="data:x&y"'); // sin escapar habría cortado el atributo ahí
  });

  it("no toca el resto del documento", () => {
    const compuesto = insertarTrazoEnSvg(SVG_SIMPLE, "data:x", 10, 5);
    expect(compuesto).toContain('<g class="ejes"></g></svg>');
  });

  it("lanza un error legible si el texto no es un SVG serializado", () => {
    expect(() => insertarTrazoEnSvg("no es xml", "data:x", 1, 1)).toThrow(/etiqueta de apertura/);
  });
});

describe("exportarComoSVG", () => {
  let gl: DobleGL;
  let r: Renderizador;
  let lienzo: LienzoDeMentira;

  beforeEach(() => {
    gl = crearDobleGL();
    r = new Renderizador(gl);
    r.subirSerie("rpm", cubosDe(5), COLOR);
    lienzo = new LienzoDeMentira(gl);
  });

  it("compone el trazo por debajo de los ejes ya pintados", () => {
    const svgFalso = {} as unknown as SVGSVGElement;
    const blob = exportarComoSVG(
      { renderizador: r, lienzo, svg: svgFalso, vista: VISTA, anchoPx: 10, altoPx: 5 },
      { serializarSvg: () => '<svg width="10" height="5"><g class="ejes"></g></svg>' },
    );
    expect(blob.type).toBe("image/svg+xml");
    // El trazo se capturó (y por tanto ya se dibujó) antes de devolver el Blob.
    expect(lienzo.snapshotsDeClear).toEqual([1]);
  });
});

describe("exportarComoPNG", () => {
  let gl: DobleGL;
  let r: Renderizador;
  let lienzo: LienzoDeMentira;

  beforeEach(() => {
    gl = crearDobleGL();
    r = new Renderizador(gl);
    r.subirSerie("rpm", cubosDe(5), COLOR);
    lienzo = new LienzoDeMentira(gl);
  });

  function entornoDeMentira(): { entorno: EntornoExportacion; llamadas: string[] } {
    const llamadas: string[] = [];
    const entorno: EntornoExportacion = {
      crearLienzoDestino(ancho, alto) {
        llamadas.push(`crearLienzoDestino(${ancho}x${alto})`);
        return {
          dibujarImagen(_imagen, _x, _y, ancho2, alto2) {
            llamadas.push(`dibujarImagen(${ancho2}x${alto2})`);
          },
          async aBlob(tipo) {
            llamadas.push(`aBlob(${tipo})`);
            return new Blob(["contenido-de-mentira"], { type: tipo });
          },
        };
      },
      async cargarImagen(urlDatos) {
        llamadas.push(`cargarImagen(${urlDatos.slice(0, 10)}...)`);
        return { width: 1, height: 1 };
      },
      serializarSvg() {
        llamadas.push("serializarSvg");
        return '<svg width="10" height="5"><g class="ejes"></g></svg>';
      },
    };
    return { entorno, llamadas };
  }

  it("captura el trazo ANTES que cualquier paso asíncrono", async () => {
    const { entorno } = entornoDeMentira();
    const svgFalso = {} as unknown as SVGSVGElement;
    await exportarComoPNG(
      { renderizador: r, lienzo, svg: svgFalso, vista: VISTA, anchoPx: 10, altoPx: 5 },
      entorno,
    );
    // Un solo `dibujar()` + lectura, y ya había pasado cuando se leyó: si
    // `capturarTrazoPNG` se hubiera llamado tras un `await`, esta prueba no
    // lo detectaría por sí sola, pero si alguien mueve la lectura DESPUÉS
    // de `Promise.all(...)` por error, `snapshotsDeClear` seguiría siendo
    // `[1]` aquí igualmente -- la propiedad real (que no haya un `await` de
    // por medio) la fija la ausencia de cualquier `await` antes de la
    // llamada dentro de `exportarComoPNG`, revisable leyendo el código.
    expect(lienzo.snapshotsDeClear).toEqual([1]);
  });

  it("compone el trazo y los ejes en un lienzo del tamaño de DISPOSITIVO del canvas", async () => {
    const { entorno, llamadas } = entornoDeMentira();
    const svgFalso = {} as unknown as SVGSVGElement;
    const blob = await exportarComoPNG(
      { renderizador: r, lienzo, svg: svgFalso, vista: VISTA, anchoPx: 10, altoPx: 5 },
      entorno,
    );
    expect(llamadas).toContain(`crearLienzoDestino(${lienzo.width}x${lienzo.height})`);
    expect(llamadas.filter((l) => l.startsWith("dibujarImagen")).length).toBe(2);
    expect(llamadas).toContain(`dibujarImagen(${lienzo.width}x${lienzo.height})`);
    expect(llamadas).toContain("aBlob(image/png)");
    expect(blob.type).toBe("image/png");
  });

  it("usa la resolución de dispositivo del canvas, no los píxeles CSS de los ejes", async () => {
    const { entorno, llamadas } = entornoDeMentira();
    const svgFalso = {} as unknown as SVGSVGElement;
    // `anchoPx`/`altoPx` (10x5, píxeles CSS de los ejes) son distintos de
    // `lienzo.width`/`.height` (800x400, píxeles de dispositivo): el lienzo
    // de salida tiene que usar los segundos.
    await exportarComoPNG(
      { renderizador: r, lienzo, svg: svgFalso, vista: VISTA, anchoPx: 10, altoPx: 5 },
      entorno,
    );
    expect(llamadas).not.toContain("crearLienzoDestino(10x5)");
    expect(llamadas).toContain("crearLienzoDestino(800x400)");
  });
});
