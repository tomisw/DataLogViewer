/**
 * Banco del renderizador (`npm run banco`).
 *
 * QUÉ MIDE ESTO Y QUÉ NO
 * ======================
 * §2.6 pide «pan/zoom con 16 canales × 5 M puntos ≥ 60 fps, sin fotograma
 * > 20 ms». Ese número tiene dos mitades:
 *
 *   1. **Lo que cuesta la GPU** —relleno, ancho de banda, el coste real de
 *      `drawArrays`—. Depende de la máquina y solo se mide con un navegador y
 *      una GPU de verdad: está en `banco-fps.html`, que se abre con
 *      `npm run dev` y da fps medidos.
 *   2. **Lo que cuesta la CPU en JavaScript** —preparar cada fotograma, subir
 *      un nivel nuevo cuando cambia el zoom—. Eso sí se mide aquí, en Node,
 *      sin GPU, en cada `npm run banco`, y es la mitad que se degrada sola
 *      cuando alguien mete trabajo dentro del bucle de dibujo.
 *
 * Este fichero mide (2) y **no pretende medir (1)**. Decirlo importa: un banco
 * que dijera «60 fps» sin haber dibujado un solo píxel sería exactamente el
 * verde falso que §8.10 prohíbe («no haber podido mirar no es estar en
 * verde»). Por eso el nombre de las pruebas dice CPU y por eso el informe de
 * F1-23 declara la mitad que falta.
 *
 * El presupuesto de aquí no es 16,7 ms: es una fracción pequeña de esos, porque
 * el resto es para la GPU. Se fija en 2 ms por fotograma con 16 series, que es
 * generoso a propósito —lo que tiene que cazar es una regresión de orden de
 * magnitud (un `bufferData` colado en el bucle, un recorrido por cubo por
 * fotograma), no una diferencia del 20 % entre dos portátiles—.
 */

import { describe, expect, it } from "vitest";

import { crearDobleGL } from "./doble-gl.ts";
import { expandirCubos } from "./escala.ts";
import { Renderizador } from "./renderizador.ts";
import type { Color, CubosContinuos, Vista } from "./tipos.ts";

const CANALES = 16;
const CUBOS_POR_CANAL = 2000; // ≈ un cubo por píxel en un panel de 1920
const FOTOGRAMAS = 600; // 10 s de pan a 60 fps
const PRESUPUESTO_MEDIA_MS = 2;
const PRESUPUESTO_PEOR_MS = 8;

const COLOR: Color = { r: 1, g: 1, b: 1, a: 1 };

function cubosSinteticos(n: number, semilla: number): CubosContinuos {
  const t = new Float32Array(n);
  const minimo = new Float32Array(n);
  const maximo = new Float32Array(n);
  const primero = new Float32Array(n);
  const ultimo = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = i * 0.001;
    const base = Math.sin((i + semilla) / 37) * 3000 + 3500;
    minimo[i] = base - 120;
    maximo[i] = base + 120;
    primero[i] = base - 40;
    ultimo[i] = base + 40;
  }
  return { t, tOrigen: 0, minimo, maximo, primero, ultimo, factor: 64 };
}

function percentil(valores: number[], p: number): number {
  const ordenados = [...valores].sort((a, b) => a - b);
  const i = Math.min(ordenados.length - 1, Math.floor((p / 100) * ordenados.length));
  return ordenados[i]!;
}

describe("coste de CPU del renderizador", () => {
  it(`pan de ${FOTOGRAMAS} fotogramas con ${CANALES} canales: < ${PRESUPUESTO_MEDIA_MS} ms de CPU por fotograma`, () => {
    const gl = crearDobleGL();
    const r = new Renderizador(gl);
    for (let c = 0; c < CANALES; c += 1) {
      r.subirSerie(`canal-${c}`, cubosSinteticos(CUBOS_POR_CANAL, c * 97), COLOR);
    }
    // El doble guarda cada llamada en una lista; con 600 fotogramas × 16 series
    // eso serían decenas de miles de objetos y estaríamos midiendo el doble,
    // no el renderizador.
    gl.olvidar();

    const tiempos: number[] = [];
    for (let f = 0; f < FOTOGRAMAS; f += 1) {
      const desplazamiento = f * 0.005;
      const vista: Vista = {
        t0: desplazamiento,
        t1: 2 + desplazamiento,
        v0: 0,
        v1: 8000,
      };
      const antes = performance.now();
      r.dibujar(vista);
      tiempos.push(performance.now() - antes);
      gl.olvidar();
    }

    const media = tiempos.reduce((a, b) => a + b, 0) / tiempos.length;
    const p95 = percentil(tiempos, 95);
    const peor = Math.max(...tiempos);
    // eslint-disable-next-line no-console
    console.log(
      `  CPU/fotograma: media ${media.toFixed(3)} ms · p95 ${p95.toFixed(3)} ms · peor ${peor.toFixed(3)} ms`,
    );

    expect(media).toBeLessThan(PRESUPUESTO_MEDIA_MS);
    expect(peor).toBeLessThan(PRESUPUESTO_PEOR_MS);
    r.destruir();
  });

  it("un pan de 600 fotogramas no sube ni un byte a la GPU", () => {
    // El mismo invariante que la suite rápida, pero sostenido en el tiempo:
    // una subida cada N fotogramas (una caché mal invalidada, por ejemplo) pasa
    // desapercibida en una prueba de un fotograma y aquí no.
    const gl = crearDobleGL();
    const r = new Renderizador(gl);
    for (let c = 0; c < CANALES; c += 1) {
      r.subirSerie(`canal-${c}`, cubosSinteticos(CUBOS_POR_CANAL, c), COLOR);
    }
    r.reiniciarEstadisticas();
    for (let f = 0; f < FOTOGRAMAS; f += 1) {
      r.dibujar({ t0: f * 0.005, t1: 2 + f * 0.005, v0: 0, v1: 8000 });
      gl.olvidar();
    }
    expect(r.estadisticas.subidasDeBufer).toBe(0);
    r.destruir();
  });

  it("cambiar de nivel de pirámide en los 16 canales cabe en un fotograma", () => {
    // Este es el caso que SÍ sube datos: el zoom que sale del nivel actual.
    // §2.6 le da un presupuesto propio y más holgado («pan/zoom que requiere
    // cubos nuevos del backend < 120 ms p95»); lo que se mide aquí es solo la
    // parte de CPU del frontend, que tiene que ser una porción pequeña de eso
    // para dejar sitio a la ida y vuelta al backend.
    const gl = crearDobleGL();
    const r = new Renderizador(gl);
    const nuevos = Array.from({ length: CANALES }, (_, c) =>
      cubosSinteticos(CUBOS_POR_CANAL, c * 13),
    );
    for (let c = 0; c < CANALES; c += 1) r.subirSerie(`canal-${c}`, nuevos[c]!, COLOR);
    gl.olvidar();

    const antes = performance.now();
    for (let c = 0; c < CANALES; c += 1) r.subirSerie(`canal-${c}`, nuevos[c]!, COLOR);
    const ms = performance.now() - antes;
    // eslint-disable-next-line no-console
    console.log(`  cambio de nivel en ${CANALES} canales: ${ms.toFixed(2)} ms de CPU`);
    expect(ms).toBeLessThan(30);
    r.destruir();
  });
});

describe("coste de expandirCubos", () => {
  it("expandir un nivel entero es lineal y barato", () => {
    // Es el único recorrido por cubo que hay en el camino caliente. Si esto se
    // vuelve cuadrático (por ejemplo, concatenando arrays en vez de escribir en
    // uno reservado), el síntoma sería un tirón al cambiar de zoom, no al
    // moverse: fácil de achacar a la red y difícil de encontrar.
    const pequeno = cubosSinteticos(10_000, 1);
    const grande = cubosSinteticos(100_000, 1);

    expandirCubos(pequeno); // calentamiento del JIT
    const t1 = performance.now();
    expandirCubos(pequeno);
    const msPequeno = performance.now() - t1;

    expandirCubos(grande);
    const t2 = performance.now();
    expandirCubos(grande);
    const msGrande = performance.now() - t2;

    // eslint-disable-next-line no-console
    console.log(`  expandirCubos: 10 k en ${msPequeno.toFixed(3)} ms · 100 k en ${msGrande.toFixed(3)} ms`);
    // Diez veces los datos no puede costar más de treinta veces el tiempo. El
    // margen es ancho porque a esta escala el ruido de medida es grande; lo que
    // caza es un cambio de orden, no un 50 %.
    expect(msGrande).toBeLessThan(Math.max(msPequeno, 0.05) * 30);
  });
});
