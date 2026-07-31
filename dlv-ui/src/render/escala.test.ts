/**
 * Pruebas de la aritmética del renderizador.
 *
 * Aquí está lo que se puede equivocar en silencio. Un shader mal escrito no
 * dibuja nada y se nota; una escala invertida, un nivel de pirámide demasiado
 * grueso o un pico perdido al decimar dibujan algo plausible y equivocado, que
 * en una herramienta de tuning es peor: se decide sobre ello.
 */

import { describe, expect, it } from "vitest";

import {
  elegirNivel,
  expandirCubos,
  transformacion,
  validarCubos,
  VERTICES_POR_CUBO,
} from "./escala.ts";
import type { CubosContinuos, Vista } from "./tipos.ts";

function cubos(parcial: Partial<CubosContinuos> = {}): CubosContinuos {
  return {
    t: new Float32Array([0, 1, 2]),
    tOrigen: 0,
    minimo: new Float32Array([0, 0, 0]),
    maximo: new Float32Array([1, 1, 1]),
    primero: new Float32Array([0, 0, 0]),
    ultimo: new Float32Array([1, 1, 1]),
    factor: 1,
    ...parcial,
  };
}

describe("transformacion", () => {
  const vista: Vista = { t0: 10, t1: 20, v0: 0, v1: 100 };

  it("lleva los extremos de la vista a los extremos del recorte", () => {
    const t = transformacion(0, vista);
    // x = t·escalaX + despX, con t RELATIVO al origen; aquí el origen es 0.
    expect(10 * t.escalaX + t.despX).toBeCloseTo(-1, 12);
    expect(20 * t.escalaX + t.despX).toBeCloseTo(1, 12);
    expect(0 * t.escalaY + t.despY).toBeCloseTo(-1, 12);
    expect(100 * t.escalaY + t.despY).toBeCloseTo(1, 12);
  });

  it("el origen de la serie desplaza sin cambiar la escala", () => {
    // La misma serie descrita con otro origen tiene que caer en el mismo sitio.
    const sinDesplazar = transformacion(0, vista);
    const desplazada = transformacion(10, vista);
    expect(desplazada.escalaX).toBeCloseTo(sinDesplazar.escalaX, 12);
    // t absoluto 15 = relativo 15 con origen 0 = relativo 5 con origen 10.
    expect(5 * desplazada.escalaX + desplazada.despX).toBeCloseTo(
      15 * sinDesplazar.escalaX + sinDesplazar.despX,
      12,
    );
  });

  it("el eje Y crece hacia arriba", () => {
    const t = transformacion(0, vista);
    expect(t.escalaY).toBeGreaterThan(0);
  });

  it("una vista sin anchura da escala 0 en vez de infinito", () => {
    // Un `NaN` en WebGL no da error: da un lienzo en blanco sin explicación.
    // Colapsar a una línea es feo pero diagnosticable.
    const degenerada = transformacion(0, { t0: 5, t1: 5, v0: 3, v1: 3 });
    expect(Number.isFinite(degenerada.escalaX)).toBe(true);
    expect(Number.isFinite(degenerada.despX)).toBe(true);
    expect(Number.isFinite(degenerada.escalaY)).toBe(true);
    expect(Number.isFinite(degenerada.despY)).toBe(true);
  });

  it("mantiene precisión útil en un log largo muy ampliado", () => {
    // 8 h de log, ventana de 20 ms: el caso que rompe si el origen no se resta
    // en doble precisión antes de llegar al `float32` del shader.
    const tOrigen = 0;
    const centro = 28_800;
    const v: Vista = { t0: centro, t1: centro + 0.02, v0: 0, v1: 1 };
    const t = transformacion(tOrigen, v);
    // El vértice guardado en float32 pierde resolución, y esa pérdida es
    // conocida y acotada: lo que no puede pasar es que la transformación en sí
    // introduzca error extra.
    const izquierda = centro * t.escalaX + t.despX;
    const derecha = (centro + 0.02) * t.escalaX + t.despX;
    expect(izquierda).toBeCloseTo(-1, 6);
    expect(derecha).toBeCloseTo(1, 6);
  });
});

describe("elegirNivel", () => {
  // Pirámide de factor 4 sobre 5 M muestras, como el peor caso de §2.6.
  const niveles = [
    { factor: 1, nCubos: 5_000_000 },
    { factor: 4, nCubos: 1_250_000 },
    { factor: 16, nCubos: 312_500 },
    { factor: 64, nCubos: 78_125 },
    { factor: 256, nCubos: 19_531 },
    { factor: 1024, nCubos: 4_882 },
    { factor: 4096, nCubos: 1_220 },
  ];

  it("con el log entero a la vista elige un nivel del orden del ancho en píxeles", () => {
    const i = elegirNivel(niveles, 1, 1920);
    // No se fija el índice exacto a propósito: lo que importa es la propiedad,
    // no qué escalón concreto la cumple. Una prueba que fija el índice se pone
    // roja al añadir un nivel a la pirámide sin que nada esté mal.
    expect(niveles[i]!.nCubos).toBeGreaterThanOrEqual(1920);
    // Y que sea el más barato de los suficientes: el siguiente más grueso ya no
    // llegaría.
    const masGruesos = niveles.filter((n) => n.nCubos < niveles[i]!.nCubos);
    for (const n of masGruesos) expect(n.nCubos).toBeLessThan(1920);
  });

  it("al ampliar mucho baja a un nivel más fino", () => {
    const ancho = elegirNivel(niveles, 1, 1920);
    const estrecho = elegirNivel(niveles, 0.001, 1920);
    expect(niveles[estrecho]!.factor).toBeLessThan(niveles[ancho]!.factor);
  });

  it("nunca devuelve un nivel que pierda detalle visible si hay uno mejor", () => {
    for (const fraccion of [1, 0.5, 0.1, 0.01, 0.001, 0.0001]) {
      const i = elegirNivel(niveles, fraccion, 1920);
      const visibles = niveles[i]!.nCubos * fraccion;
      const hayMasFino = niveles.some((n) => n.nCubos > niveles[i]!.nCubos);
      // O cumple el criterio de un cubo por píxel, o ya es el más fino y no hay
      // más detalle que dar.
      expect(visibles >= 1920 || !hayMasFino).toBe(true);
    }
  });

  it("no depende del orden de la lista", () => {
    const alReves = [...niveles].reverse();
    const i = elegirNivel(niveles, 0.01, 1920);
    const j = elegirNivel(alReves, 0.01, 1920);
    expect(alReves[j]!.factor).toBe(niveles[i]!.factor);
  });

  it("una fracción visible de 0 da el nivel más fino y no revienta", () => {
    expect(niveles[elegirNivel(niveles, 0, 1920)]!.factor).toBe(1);
  });

  it("sin niveles falla en vez de devolver un índice inventado", () => {
    expect(() => elegirNivel([], 1, 1920)).toThrow(/no hay niveles/);
  });
});

describe("expandirCubos", () => {
  it("da cuatro vértices por cubo, todos en el mismo x", () => {
    const salida = expandirCubos(cubos());
    expect(salida.length).toBe(3 * VERTICES_POR_CUBO * 2);
    for (let cubo = 0; cubo < 3; cubo += 1) {
      for (let v = 0; v < VERTICES_POR_CUBO; v += 1) {
        expect(salida[(cubo * VERTICES_POR_CUBO + v) * 2]).toBe(cubo);
      }
    }
  });

  it("nunca pierde un pico: min y max del cubo están siempre en la salida", () => {
    // Es la razón de ser de toda la pirámide. Un pico de un solo sample que
    // desaparece al decimar es un fallo de detonación que no se ve.
    const conPico = cubos({
      minimo: new Float32Array([-40, 0, 0]),
      maximo: new Float32Array([0, 0, 900]),
      primero: new Float32Array([-1, 0, 0]),
      ultimo: new Float32Array([-2, 0, 1]),
    });
    const salida = expandirCubos(conPico);
    const ys = [...salida].filter((_, i) => i % 2 === 1);
    expect(ys).toContain(-40);
    expect(ys).toContain(900);
  });

  it("recorre el cubo en el sentido de su pendiente", () => {
    // Con un orden fijo min→max, un tramo descendente dibujaría un zigzag que
    // no está en los datos y que a cierto zoom se lee como ruido de señal.
    const bajando = cubos({
      t: new Float32Array([0]),
      minimo: new Float32Array([1]),
      maximo: new Float32Array([9]),
      primero: new Float32Array([8]),
      ultimo: new Float32Array([2]),
    });
    const ys = [...expandirCubos(bajando)].filter((_, i) => i % 2 === 1);
    expect(ys).toEqual([8, 9, 1, 2]);

    const subiendo = cubos({
      t: new Float32Array([0]),
      minimo: new Float32Array([1]),
      maximo: new Float32Array([9]),
      primero: new Float32Array([2]),
      ultimo: new Float32Array([8]),
    });
    const ys2 = [...expandirCubos(subiendo)].filter((_, i) => i % 2 === 1);
    expect(ys2).toEqual([2, 1, 9, 8]);
  });

  it("empieza en `primero` y acaba en `ultimo` para coser con el cubo vecino", () => {
    const salida = expandirCubos(cubos());
    // Del cubo 0: primer y último vértice.
    expect(salida[1]).toBe(0); // primero[0]
    expect(salida[7]).toBe(1); // ultimo[0]
  });

  it("un nivel sin cubos da un búfer vacío en vez de fallar", () => {
    const vacio = cubos({
      t: new Float32Array(0),
      minimo: new Float32Array(0),
      maximo: new Float32Array(0),
      primero: new Float32Array(0),
      ultimo: new Float32Array(0),
    });
    expect(expandirCubos(vacio).length).toBe(0);
  });
});

describe("validarCubos", () => {
  it("un array descuadrado falla con el nombre del array", () => {
    // Sin esto, la longitud de menos se convierte en `NaN` dentro del búfer y
    // el síntoma es un hueco en el trazo, que se diagnostica mirando un lienzo.
    expect(() => validarCubos(cubos({ maximo: new Float32Array([1, 1]) }))).toThrow(/maximo/);
  });

  it("acepta cubos coherentes", () => {
    expect(() => validarCubos(cubos())).not.toThrow();
  });
});
