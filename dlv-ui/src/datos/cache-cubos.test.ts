/**
 * Pruebas de la caché de cubos (F1-24).
 *
 * Dos de estas pruebas protegen presupuestos declarados de §2.6 y no detalles
 * de implementación:
 *
 * - «un pan corto no vuelve a pedir» es lo que convierte el pan en un cambio de
 *   uniforme en vez de una petición HTTP.
 * - «el nivel forma parte de la clave» es lo que evita que el cursor lea de un
 *   nivel decimado distinto del que se está viendo y enseñe un número plausible
 *   y falso, que en tuning es el peor fallo posible.
 */

import { describe, expect, it } from "vitest";

import type { CubosContinuos } from "../render/tipos.ts";
import {
  bytesDe,
  CacheDeCubos,
  indiceEn,
  valorEn,
  type EntradaCache,
} from "./cache-cubos.ts";

function cubos(n: number, tOrigen = 0, paso = 1, factor = 1): CubosContinuos {
  const t = new Float32Array(n);
  const minimo = new Float32Array(n);
  const maximo = new Float32Array(n);
  const primero = new Float32Array(n);
  const ultimo = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = i * paso;
    minimo[i] = i * 10;
    maximo[i] = i * 10 + 5;
    primero[i] = i * 10 + 1;
    ultimo[i] = i * 10 + 4;
  }
  return { t, tOrigen, minimo, maximo, primero, ultimo, factor };
}

function entrada(n: number, t0: number, t1: number, factor = 1): EntradaCache {
  return { cubos: cubos(n, t0, (t1 - t0) / Math.max(1, n - 1), factor), cubre: { t0, t1 } };
}

describe("aciertos y fallos", () => {
  it("un fallo pide el rango visible ensanchado por el margen", () => {
    const cache = new CacheDeCubos({ margen: 0.5 });
    const r = cache.consultar({ canal: "rpm", factor: 1 }, { t0: 10, t1: 20 });
    expect(r.estado).toBe("fallo");
    if (r.estado !== "fallo") return;
    // Tres anchos de pantalla: uno visible y medio a cada lado.
    expect(r.pedir).toEqual({ t0: 5, t1: 25 });
  });

  it("un pan corto dentro del margen no vuelve a pedir", () => {
    // Es el presupuesto de §2.6 hecho prueba: si esto falla, cada fotograma de
    // pan se convierte en una petición HTTP a Python y los 60 fps se acaban.
    const cache = new CacheDeCubos({ margen: 0.5 });
    cache.guardar({ canal: "rpm", factor: 4 }, entrada(2000, 5, 25));
    for (let paso = 0; paso <= 40; paso += 1) {
      const t0 = 10 + paso * 0.1;
      const r = cache.consultar({ canal: "rpm", factor: 4 }, { t0, t1: t0 + 10 });
      expect(r.estado).toBe("acierto");
    }
    expect(cache.estadisticas.fallos).toBe(0);
  });

  it("salirse del tramo cacheado es un fallo, aunque solo sea por un lado", () => {
    // Media cobertura devuelta como acierto dibujaría medio panel en blanco y
    // se diagnosticaría como "el log está cortado".
    const cache = new CacheDeCubos();
    cache.guardar({ canal: "rpm", factor: 1 }, entrada(100, 10, 20));
    expect(cache.consultar({ canal: "rpm", factor: 1 }, { t0: 15, t1: 25 }).estado).toBe("fallo");
    expect(cache.consultar({ canal: "rpm", factor: 1 }, { t0: 5, t1: 15 }).estado).toBe("fallo");
    expect(cache.consultar({ canal: "rpm", factor: 1 }, { t0: 12, t1: 18 }).estado).toBe("acierto");
  });

  it("el nivel de pirámide forma parte de la clave", () => {
    // Sin esto, hacer zoom y mover el cursor leería del nivel anterior: un
    // valor decimado presentado como el real.
    const cache = new CacheDeCubos();
    cache.guardar({ canal: "rpm", factor: 64 }, entrada(100, 0, 100, 64));
    expect(cache.consultar({ canal: "rpm", factor: 1 }, { t0: 10, t1: 20 }).estado).toBe("fallo");
    expect(cache.consultar({ canal: "rpm", factor: 64 }, { t0: 10, t1: 20 }).estado).toBe("acierto");
  });

  it("canales con espacios en el nombre no chocan entre sí", () => {
    // Los nombres Haltech llevan espacios ("Coolant Temperature"), así que la
    // separación de la clave tiene que aguantarlos.
    const cache = new CacheDeCubos();
    cache.guardar({ canal: "Wideband O2 1", factor: 4 }, entrada(10, 0, 10));
    expect(cache.consultar({ canal: "Wideband O2", factor: 14 }, { t0: 1, t1: 2 }).estado).toBe(
      "fallo",
    );
  });
});

describe("desalojo", () => {
  it("desaloja lo menos usado hasta caber en el tope de bytes", () => {
    const unaEntrada = bytesDe(cubos(1000));
    const cache = new CacheDeCubos({ bytesMaximos: unaEntrada * 2 + 1 });
    cache.guardar({ canal: "a", factor: 1 }, { cubos: cubos(1000), cubre: { t0: 0, t1: 10 } });
    cache.guardar({ canal: "b", factor: 1 }, { cubos: cubos(1000), cubre: { t0: 0, t1: 10 } });
    // Usar "a" la pone al final de la cola: la que sobra al entrar "c" es "b".
    cache.consultar({ canal: "a", factor: 1 }, { t0: 0, t1: 10 });
    cache.guardar({ canal: "c", factor: 1 }, { cubos: cubos(1000), cubre: { t0: 0, t1: 10 } });

    expect(cache.mirar({ canal: "b", factor: 1 })).toBeUndefined();
    expect(cache.mirar({ canal: "a", factor: 1 })).toBeDefined();
    expect(cache.mirar({ canal: "c", factor: 1 })).toBeDefined();
    expect(cache.estadisticas.desalojos).toBe(1);
  });

  it("nunca desaloja lo que se acaba de guardar", () => {
    // Guardar y borrar en el mismo acto convertiría cada consulta en un fallo:
    // la caché haría más daño que no tenerla.
    const cache = new CacheDeCubos({ bytesMaximos: 1 });
    cache.guardar({ canal: "a", factor: 1 }, { cubos: cubos(1000), cubre: { t0: 0, t1: 10 } });
    expect(cache.mirar({ canal: "a", factor: 1 })).toBeDefined();
    expect(cache.estadisticas.bytes).toBeGreaterThan(1); // y se ve que se pasó
  });

  it("reemplazar una clave no cuenta su memoria dos veces", () => {
    const cache = new CacheDeCubos();
    cache.guardar({ canal: "a", factor: 1 }, { cubos: cubos(100), cubre: { t0: 0, t1: 1 } });
    cache.guardar({ canal: "a", factor: 1 }, { cubos: cubos(100), cubre: { t0: 0, t1: 2 } });
    expect(cache.estadisticas.entradas).toBe(1);
    expect(cache.estadisticas.bytes).toBe(bytesDe(cubos(100)));
  });

  it("invalidar un canal se lleva todos sus niveles y solo los suyos", () => {
    const cache = new CacheDeCubos();
    cache.guardar({ canal: "rpm", factor: 1 }, entrada(10, 0, 1));
    cache.guardar({ canal: "rpm", factor: 4 }, entrada(10, 0, 1));
    cache.guardar({ canal: "map", factor: 1 }, entrada(10, 0, 1));
    cache.invalidar("rpm");
    expect(cache.estadisticas.entradas).toBe(1);
    expect(cache.mirar({ canal: "map", factor: 1 })).toBeDefined();
    expect(cache.estadisticas.bytes).toBe(bytesDe(cubos(10)));
  });

  it("una caché de tamaño no positivo se rechaza al construirla", () => {
    expect(() => new CacheDeCubos({ bytesMaximos: 0 })).toThrow(/positivo/);
    expect(() => new CacheDeCubos({ margen: -1 })).toThrow(/negativo/);
  });

  it("un tramo del revés se rechaza al guardarlo", () => {
    const cache = new CacheDeCubos();
    expect(() =>
      cache.guardar({ canal: "a", factor: 1 }, { cubos: cubos(10), cubre: { t0: 10, t1: 0 } }),
    ).toThrow(/del revés/);
  });
});

describe("búsqueda del cursor", () => {
  const serie = cubos(1000, 100, 0.01); // 10 s a partir del segundo 100

  it("devuelve el cubo vigente, no el más cercano", () => {
    // Un cubo empieza en su instante y dura hasta el siguiente. Redondear al
    // más cercano adelantaría el valor hasta medio cubo, y a nivel grueso medio
    // cubo son segundos.
    //
    // Las fronteras se leen del propio array y no se escriben como literales
    // (`100 + 5.01`) a propósito: `cubos.t` es `Float32Array`, y 5,01 no tiene
    // representación exacta en float32 —el más cercano es ~5,0100002—, así que
    // un literal cae al otro lado de la frontera por unos 200 ns y la prueba
    // mediría el redondeo de IEEE-754, no la regla de "cubo vigente". Esa
    // cuantización es real y está documentada en `CubosContinuos.t`: es el
    // precio de guardar el tiempo en float32, y a 5 s vale medio microsegundo,
    // cuatro órdenes de magnitud por debajo del presupuesto de cursor.
    const frontera = serie.tOrigen + serie.t[501]!;
    const dentroDelAnterior = serie.tOrigen + serie.t[500]!;
    expect(indiceEn(serie, dentroDelAnterior)).toBe(500);
    expect(indiceEn(serie, (dentroDelAnterior + frontera) / 2)).toBe(500);
    expect(indiceEn(serie, frontera)).toBe(501);
  });

  it("un instante anterior al primer cubo no inventa un valor", () => {
    expect(indiceEn(serie, 99)).toBe(-1);
    expect(valorEn(serie, 99)).toBeNull();
  });

  it("un instante posterior al último cubo se queda en el último", () => {
    expect(indiceEn(serie, 1e9)).toBe(999);
  });

  it("coincide con una búsqueda lineal en todo el rango", () => {
    // La búsqueda binaria es fácil de escribir con un `off-by-one` que solo se
    // nota en los bordes. Comparar contra la versión obvia lo caza entero.
    for (let i = 0; i < 1000; i += 7) {
      for (const desplazamiento of [-0.004, 0, 0.004, 0.009]) {
        const t = 100 + i * 0.01 + desplazamiento;
        let esperado = -1;
        for (let j = 0; j < serie.t.length; j += 1) {
          if (serie.t[j]! <= t - serie.tOrigen) esperado = j;
        }
        expect(indiceEn(serie, t)).toBe(esperado);
      }
    }
  });

  it("devuelve el rango del cubo, no un único número", () => {
    // A nivel decimado "el valor" no existe: lo que hay es un rango. Enseñar
    // solo `ultimo` ocultaría que en ese píxel hubo un pico.
    const v = valorEn(serie, 100 + 3);
    expect(v).not.toBeNull();
    expect(v).toMatchObject({ indice: 300, minimo: 3000, maximo: 3005 });
    expect(v!.maximo).toBeGreaterThan(v!.minimo);
  });

  it("una serie vacía no revienta", () => {
    const vacia: CubosContinuos = {
      t: new Float32Array(0),
      tOrigen: 0,
      minimo: new Float32Array(0),
      maximo: new Float32Array(0),
      primero: new Float32Array(0),
      ultimo: new Float32Array(0),
      factor: 1,
    };
    expect(indiceEn(vacia, 5)).toBe(-1);
    expect(valorEn(vacia, 5)).toBeNull();
  });
});
