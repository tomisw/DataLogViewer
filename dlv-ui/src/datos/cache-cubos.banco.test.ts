/**
 * Banco de la caché de cubos (F1-24, `npm run banco`).
 *
 * Mide el presupuesto de §2.6 «latencia del cursor a tabla actualizada
 * < 16 ms», que es el que justifica que esta caché exista: con Python al otro
 * lado de HTTP, 16 ms no dan para una petición y una respuesta, así que la
 * única forma de cumplirlo es no preguntar.
 *
 * Lo que se mide aquí es la parte que este módulo controla: **buscar el valor
 * de los 16 canales para un instante**. Lo que falta para el número de §2.6 es
 * pintar la tabla en el DOM, que es F1-29 y tiene su propio banco. Se dice para
 * que nadie lea "0,003 ms" y crea que el presupuesto entero está medido.
 */

import { describe, expect, it } from "vitest";

import type { CubosContinuos } from "../render/tipos.ts";
import { CacheDeCubos, valorEn } from "./cache-cubos.ts";

const CANALES = 16;
const CUBOS = 2000;
const MOVIMIENTOS = 2000;
const PRESUPUESTO_MS = 16;

function cubos(n: number): CubosContinuos {
  const t = new Float32Array(n);
  const v = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = i * 0.005;
    v[i] = Math.sin(i / 50) * 3000 + 4000;
  }
  return { t, tOrigen: 0, minimo: v, maximo: v, primero: v, ultimo: v, factor: 64 };
}

describe("presupuesto de cursor", () => {
  it(`mover el cursor sobre ${CANALES} canales cuesta muy por debajo de ${PRESUPUESTO_MS} ms`, () => {
    const cache = new CacheDeCubos();
    for (let c = 0; c < CANALES; c += 1) {
      cache.guardar({ canal: `canal-${c}`, factor: 64 }, { cubos: cubos(CUBOS), cubre: { t0: 0, t1: 10 } });
    }

    // NADA de `expect` dentro de la región cronometrada. La comparación de
    // vitest cuesta más que la búsqueda binaria que se pretende medir, así que
    // una aserción dentro del bucle mide el marco de pruebas y no el módulo
    // —el mismo error de método que ya se corrigió en `tools/banco.py` al medir
    // la memoria después de tres repeticiones—. Se cuentan los aciertos y se
    // comprueban al final.
    const peores: number[] = [];
    let aciertos = 0;
    let valoresLeidos = 0;
    for (let m = 0; m < MOVIMIENTOS; m += 1) {
      const t = (m / MOVIMIENTOS) * 10;
      const antes = performance.now();
      for (let c = 0; c < CANALES; c += 1) {
        const r = cache.consultar({ canal: `canal-${c}`, factor: 64 }, { t0: t, t1: t });
        if (r.estado === "acierto") {
          aciertos += 1;
          if (valorEn(r.entrada.cubos, t) !== null) valoresLeidos += 1;
        }
      }
      peores.push(performance.now() - antes);
    }
    expect(aciertos).toBe(MOVIMIENTOS * CANALES);
    expect(valoresLeidos).toBe(MOVIMIENTOS * CANALES);

    const media = peores.reduce((a, b) => a + b, 0) / peores.length;
    const peor = Math.max(...peores);
    // eslint-disable-next-line no-console
    console.log(
      `  cursor sobre ${CANALES} canales: media ${media.toFixed(4)} ms · peor ${peor.toFixed(4)} ms ` +
        `(presupuesto ${PRESUPUESTO_MS} ms, y falta el pintado de la tabla: F1-29)`,
    );
    expect(peor).toBeLessThan(PRESUPUESTO_MS);
    // El margen tiene que ser holgado, no ajustado: el resto del presupuesto es
    // para el DOM, que es lo caro de verdad.
    expect(media).toBeLessThan(PRESUPUESTO_MS / 100);
    expect(cache.estadisticas.fallos).toBe(0);
  });

  it("un pan largo y continuo cuesta una petición por medio ancho recorrido", () => {
    // Es la propiedad que convierte el pan en un cambio de uniforme en vez de
    // una petición HTTP por fotograma: 600 fotogramas de pan no son 600
    // peticiones.
    //
    // EL NÚMERO EXACTO, PORQUE NO ES EL QUE PARECE. Con `margen = 0,5` se piden
    // TRES anchos de pantalla (uno visible y medio a cada lado), y es tentador
    // concluir que cada petición compra tres pantallas de pan. Compra media:
    // el margen de la izquierda queda a la espalda de quien se mueve a la
    // derecha y no se usa nunca. Así que un pan de 10 pantallas cuesta
    // 10 / 0,5 = 20 peticiones, no 4.
    //
    // Este banco existió primero con la expectativa equivocada (≤ 12) y lo
    // enseñó. Se deja anotado porque la consecuencia es una perilla concreta:
    // si el presupuesto de §2.6 «pan/zoom que requiere cubos nuevos < 120 ms
    // p95» se pone en rojo, lo que hay que hacer NO es subir el margen —eso
    // dobla el tamaño de cada petición para seguir tirando la mitad— sino
    // sesgar la ventana pedida hacia la dirección del movimiento. Esa dirección
    // la conoce F1-28 (zoom/pan), no esta caché, y por eso no se hace aquí.
    const cache = new CacheDeCubos({ margen: 0.5 });
    const clave = { canal: "rpm", factor: 64 };
    const ancho = 2;
    for (let f = 0; f < 600; f += 1) {
      const t0 = (f / 600) * ancho * 10;
      const visible = { t0, t1: t0 + ancho };
      const r = cache.consultar(clave, visible);
      if (r.estado === "fallo") {
        cache.guardar(clave, { cubos: cubos(CUBOS), cubre: r.pedir });
      }
    }
    const fallos = cache.estadisticas.fallos;
    // eslint-disable-next-line no-console
    console.log(
      `  pan de 600 fotogramas sobre 10 pantallas: ${fallos} peticiones al backend ` +
        "(esperadas ~20 = 10 pantallas / medio ancho por petición)",
    );
    // El techo es la aritmética de arriba con un fotograma de holgura, no un
    // número redondo: si sube, es que el margen dejó de servir para algo.
    expect(fallos).toBeLessThanOrEqual(21);
    // Y el suelo: 600 peticiones sería no tener caché.
    expect(fallos).toBeLessThan(600 / 10);
  });
});
