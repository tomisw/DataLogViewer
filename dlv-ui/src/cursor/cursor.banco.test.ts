/**
 * Banco del cursor con tabla de valores (F1-29, `npm run banco`).
 *
 * QUÉ CIERRA ESTE BANCO
 * =====================
 * `datos/cache-cubos.banco.test.ts` (F1-24) mide la búsqueda del valor de 16
 * canales (0,0059 ms de media) y dice explícitamente qué falta: «pintar la
 * tabla en el DOM, que es F1-29 y tiene su propio banco». Este es ese banco.
 *
 * QUÉ MIDE Y QUÉ NO — LEER ESTO ANTES DE CREER EL NÚMERO
 * ========================================================
 * `vitest.banco.config.ts` fija `environment: "node"` a propósito (no
 * `jsdom`, ver su cabecera), y añadir `jsdom` como dependencia solo para este
 * banco está fuera de lo permitido en esta tarea (F1-29 no puede tocar
 * `package.json`). Eso significa que **no hay navegador real en este banco**,
 * y por tanto no hay `layout` ni `paint` de verdad: `doble-dom.ts` registra
 * cada `createElement`/`textContent =`/`className =`/`style.setProperty` como
 * una operación en un objeto JavaScript plano, no como una escritura en un
 * árbol de render.
 *
 * Lo que SÍ mide, con código real (no un atajo): el coste en CPU de
 * `CursorDeTabla.aplicar()` —buscar el valor de cada canal en la caché,
 * decidir muestra-real-vs-rango, formatear los números y escribir las
 * propiedades— con el mismo `CursorDeTabla` que se usa en producción. Es la
 * mitad de §2.6 que un banco en Node puede dar honestamente: un SUELO del
 * coste real, no el número completo. La otra mitad —si esa escritura fuerza
 * un recálculo de estilo en un navegador de verdad— no se puede medir aquí, y
 * decirlo es obligatorio (§8.10: «no haber podido mirar no es estar en
 * verde»). Verificarla en un navegador de verdad queda para cuando este
 * componente se integre en un panel real (fuera del alcance de F1-29, que es
 * solo el componente y su banco).
 */

import { describe, expect, it } from "vitest";

import { CacheDeCubos, type ClaveCubos } from "../datos/cache-cubos.ts";
import type { CubosContinuos } from "../render/tipos.ts";
import { CursorDeTabla, type CanalCursor } from "./cursor.ts";
import { crearDobleDOM } from "./doble-dom.ts";

const CANALES = 16;
const CUBOS = 2000;
const FOTOGRAMAS = 2000;
const PRESUPUESTO_MS = 16;

function cubosSinteticos(n: number, semilla: number, factor: number): CubosContinuos {
  const t = new Float32Array(n);
  const minimo = new Float32Array(n);
  const maximo = new Float32Array(n);
  const primero = new Float32Array(n);
  const ultimo = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = i * 0.005;
    const base = Math.sin((i + semilla) / 50) * 3000 + 4000;
    minimo[i] = base - 120;
    maximo[i] = base + 120;
    primero[i] = base - 40;
    ultimo[i] = base + 40;
  }
  return { t, tOrigen: 0, minimo, maximo, primero, ultimo, factor };
}

function prepararCursor(): { cursor: CursorDeTabla; claves: ClaveCubos[] } {
  const cache = new CacheDeCubos();
  const claves: ClaveCubos[] = [];
  const canales: CanalCursor[] = [];
  for (let c = 0; c < CANALES; c += 1) {
    const clave: ClaveCubos = { canal: `canal-${c}`, factor: 64 };
    claves.push(clave);
    canales.push({ clave, etiqueta: `Canal ${c}` });
    cache.guardar(clave, { cubos: cubosSinteticos(CUBOS, c * 97, 64), cubre: { t0: 0, t1: 10 } });
  }

  const doble = crearDobleDOM();
  const panel = doble.documento.createElement("div");
  const tabla = doble.documento.createElement("table");
  const cursor = new CursorDeTabla(panel, tabla, cache, { documento: doble.documento });
  cursor.actualizarCanales(canales);
  return { cursor, claves };
}

function percentil(valores: readonly number[], p: number): number {
  const ordenados = [...valores].sort((a, b) => a - b);
  return ordenados[Math.min(ordenados.length - 1, Math.floor((p / 100) * ordenados.length))]!;
}

describe("presupuesto de `aplicar()`: cursor moviéndose cada fotograma", () => {
  it(`${CANALES} canales × ${FOTOGRAMAS} fotogramas de movimiento continuo`, () => {
    const { cursor } = prepararCursor();

    // Calentamiento del JIT, fuera de la región medida (mismo motivo que
    // `render/renderizador.banco.test.ts`: la primera pasada por un camino de
    // código en V8 es más lenta y no representa el estado estacionario).
    for (let f = 0; f < 60; f += 1) {
      cursor.mover((f / FOTOGRAMAS) * 10, f);
      cursor.aplicar();
    }

    // Nada de `expect` dentro del bucle cronometrado, por la misma razón que
    // en `cache-cubos.banco.test.ts`: la propia aserción cuesta más que lo
    // que se mide.
    const tiempos: number[] = [];
    for (let f = 0; f < FOTOGRAMAS; f += 1) {
      const t = (f / FOTOGRAMAS) * 10;
      cursor.mover(t, f); // barato: no toca el DOM (ver cursor.ts)
      const antes = performance.now();
      cursor.aplicar(); // la parte cara: esto es lo que se mide
      tiempos.push(performance.now() - antes);
    }

    const media = tiempos.reduce((a, b) => a + b, 0) / tiempos.length;
    const p95 = percentil(tiempos, 95);
    const peor = Math.max(...tiempos);
    // eslint-disable-next-line no-console
    console.log(
      `  aplicar()/fotograma con ${CANALES} canales: media ${media.toFixed(4)} ms · ` +
        `p95 ${p95.toFixed(4)} ms · peor ${peor.toFixed(4)} ms ` +
        `(presupuesto ${PRESUPUESTO_MS} ms; NO incluye layout/paint de navegador — ver cabecera)`,
    );

    expect(peor).toBeLessThan(PRESUPUESTO_MS);
    // El margen tiene que ser holgado: esto es una fracción del presupuesto
    // completo (el resto lo consumen la búsqueda, ya medida en F1-24, y el
    // layout/paint reales, que este banco no puede medir).
    expect(media).toBeLessThan(PRESUPUESTO_MS / 20);
  });
});

describe("el cursor casi quieto no repite trabajo", () => {
  it("aplicar() con el mismo instante no vuelve a formatear ni a escribir", () => {
    // La propiedad que hace barato el caso común: un cursor que no se mueve
    // (o un `mousemove` que no cambió de cubo) no tiene que volver a buscar
    // en la caché ni a tocar el DOM. Sin esto, un `mousemove` de alta
    // frecuencia sobre un cursor quieto en los ejes gastaría presupuesto en
    // recomputar exactamente lo mismo 60 veces por segundo.
    const { cursor } = prepararCursor();

    cursor.mover(1, 5);
    cursor.aplicar();

    const tiempos: number[] = [];
    for (let f = 0; f < FOTOGRAMAS; f += 1) {
      cursor.mover(1, 5); // idéntico: mismo instante, mismo píxel
      const antes = performance.now();
      cursor.aplicar();
      tiempos.push(performance.now() - antes);
    }
    const media = tiempos.reduce((a, b) => a + b, 0) / tiempos.length;
    // eslint-disable-next-line no-console
    console.log(`  aplicar()/fotograma con el cursor quieto: media ${media.toFixed(5)} ms`);
    // Muy por debajo del caso en movimiento: si esto sube al mismo orden que
    // el banco anterior, el cortocircuito de `aplicar()` se rompió.
    expect(media).toBeLessThan(PRESUPUESTO_MS / 200);
  });
});

describe("coste de construir la tabla (`actualizarCanales`)", () => {
  it("crear las filas de 16 canales es barato y no compite con el presupuesto de 16 ms", () => {
    // `actualizarCanales` reconstruye el cuerpo de la tabla y NO tiene el
    // presupuesto de cursor (ver la cabecera de `cursor.ts`): cambiar de
    // canal es una acción explícita, no algo que pase por fotograma. Aun así
    // se mide, para que quede escrito que tampoco es un problema si algún
    // día se llama con más frecuencia de la prevista.
    const cache = new CacheDeCubos();
    const canales: CanalCursor[] = Array.from({ length: 475 }, (_, i) => ({
      clave: { canal: `canal-${i}`, factor: 1 },
      etiqueta: `Canal ${i}`,
    }));
    const doble = crearDobleDOM();
    const panel = doble.documento.createElement("div");
    const tabla = doble.documento.createElement("table");
    const cursor = new CursorDeTabla(panel, tabla, cache, { documento: doble.documento });

    const antes = performance.now();
    cursor.actualizarCanales(canales);
    const ms = performance.now() - antes;
    // eslint-disable-next-line no-console
    console.log(`  actualizarCanales con los 475 canales del log real: ${ms.toFixed(2)} ms`);
    expect(ms).toBeLessThan(50);
  });
});
