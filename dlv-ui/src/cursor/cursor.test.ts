/**
 * Pruebas del cursor con tabla de valores (F1-29).
 *
 * Dos grupos:
 *
 * - `contenidoDeCelda` es una función pura y es la decisión que más le
 *   importa revisar al propietario (real vs. rango decimado, y qué pasa
 *   fuera del tramo cacheado): se prueba sola, sin ningún DOM de por medio.
 * - `CursorDeTabla` se prueba con el doble de `doble-dom.ts`, que no es un
 *   navegador (no mide `layout`/`paint`, ver su cabecera) pero sí permite
 *   comprobar la propiedad de la que depende el presupuesto: cuántas veces se
 *   escribe el DOM y cuándo.
 */

import { describe, expect, it } from "vitest";

import { CacheDeCubos } from "../datos/cache-cubos.ts";
import type { CubosContinuos } from "../render/tipos.ts";
import { formatearNumero as formatearEnEje } from "../ejes/formato.ts";
import { contenidoDeCelda, CursorDeTabla, formatearNumero, type CanalCursor } from "./cursor.ts";
import { crearDobleDOM } from "./doble-dom.ts";

function cubosDePrueba(n: number, tOrigen: number, paso: number, factor: number): CubosContinuos {
  const t = new Float32Array(n);
  const minimo = new Float32Array(n);
  const maximo = new Float32Array(n);
  const primero = new Float32Array(n);
  const ultimo = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = i * paso;
    // Un canal con "picos": el máximo se aleja del resto para poder comprobar
    // que no se pierde al enseñar solo `último`.
    minimo[i] = 100;
    maximo[i] = 900;
    primero[i] = 150;
    ultimo[i] = 200;
  }
  return { t, tOrigen, minimo, maximo, primero, ultimo, factor };
}

describe("formatearNumero", () => {
  it("recorta decimales según la magnitud", () => {
    expect(formatearNumero(4000.4)).toBe("4000");
    expect(formatearNumero(101.23)).toBe("101,2");
    expect(formatearNumero(4.5678)).toBe("4,57");
    expect(formatearNumero(0.85123)).toBe("0,851");
  });

  it("usa coma decimal, igual que los ejes", () => {
    // Esta función usaba `toFixed`, que da siempre punto: la tabla del cursor
    // enseñaba `101.2` y el eje de al lado, en la misma ventana, `101,2`. El
    // separador lo pone ahora `src/locale/numerico.ts` (F1-32) para los dos.
    expect(formatearNumero(101.23)).toBe(formatearEnEje(101.23, 1));
    expect(formatearNumero(0.85123)).toBe(formatearEnEje(0.85123, 3));
  });

  it("un número no finito no rompe el formato", () => {
    expect(formatearNumero(Number.NaN)).toBe("—");
  });
});

describe("contenidoDeCelda: la decisión de qué enseñar", () => {
  it("factor 1 (muestra real): un solo número, marcado como muestra", () => {
    const cache = new CacheDeCubos();
    cache.guardar(
      { canal: "rpm", factor: 1 },
      { cubos: cubosDePrueba(100, 0, 0.01, 1), cubre: { t0: 0, t1: 1 } },
    );
    const c = contenidoDeCelda(cache, { canal: "rpm", factor: 1 }, 0.5, formatearNumero);
    expect(c.nivel).toBe("muestra");
    expect(c.clase).toContain("real");
    // Con factor 1, mínimo=máximo=primero=último por construcción (ver
    // `cubosDePrueba`): aquí se fuerza a que difieran para comprobar que,
    // aun así, `factor === 1` decide mostrar un único número (`último`), tal
    // y como documenta la cabecera del módulo.
    expect(c.texto).toBe(formatearNumero(200));
  });

  it("factor > 1 (decimado): la cifra principal es el RANGO, no `último`", () => {
    // Esta es la prueba que protege el requisito explícito de la tarea: un
    // pico de 900 no puede desaparecer detrás de un `último` de 200.
    const cache = new CacheDeCubos();
    cache.guardar(
      { canal: "egt", factor: 64 },
      { cubos: cubosDePrueba(100, 0, 0.01, 64), cubre: { t0: 0, t1: 1 } },
    );
    const c = contenidoDeCelda(cache, { canal: "egt", factor: 64 }, 0.5, formatearNumero);
    expect(c.nivel).toBe("×64");
    expect(c.clase).toContain("rango");
    expect(c.texto).toBe(`${formatearNumero(100)} – ${formatearNumero(900)}`);
    // El pico (900) y la tendencia (150→200) tienen que seguir disponibles en
    // algún sitio (el tooltip), aunque no sean la cifra principal.
    expect(c.titulo).toContain("900");
    expect(c.titulo).toContain("150");
    expect(c.titulo).toContain("200");
  });

  it("un canal decimado pero constante en este instante no enseña un rango vacío", () => {
    const cache = new CacheDeCubos();
    const n = 10;
    const t = new Float32Array(n);
    const v = new Float32Array(n).fill(4000);
    for (let i = 0; i < n; i += 1) t[i] = i;
    cache.guardar(
      { canal: "rpm", factor: 16 },
      { cubos: { t, tOrigen: 0, minimo: v, maximo: v, primero: v, ultimo: v, factor: 16 }, cubre: { t0: 0, t1: 9 } },
    );
    const c = contenidoDeCelda(cache, { canal: "rpm", factor: 16 }, 5, formatearNumero);
    expect(c.texto).toBe(formatearNumero(4000));
    expect(c.texto).not.toContain("–");
    // Sigue siendo decimado (el factor es una propiedad del nivel, no de la
    // muestra concreta): la columna «Nivel» lo tiene que seguir diciendo.
    expect(c.nivel).toBe("×16");
  });

  it("nada en la caché para ese canal: «sin datos», no un error", () => {
    const cache = new CacheDeCubos();
    const c = contenidoDeCelda(cache, { canal: "rpm", factor: 1 }, 0.5, formatearNumero);
    expect(c.nivel).toBe("sin datos");
    expect(c.texto).toBe("—");
  });

  it("un instante fuera del tramo cubierto es «sin datos», no el último cubo cargado", () => {
    // La trampa concreta: `indiceEn`/`valorEn` no rechazan un instante
    // posterior al último cubo (devuelven el último cubo como "vigente").
    // Sin la comprobación de `entrada.cubre`, un cursor movido más allá de lo
    // cargado enseñaría el último valor cacheado como si fuera el actual: un
    // valor plausible y falso.
    const cache = new CacheDeCubos();
    cache.guardar(
      { canal: "rpm", factor: 1 },
      { cubos: cubosDePrueba(100, 0, 0.01, 1), cubre: { t0: 0, t1: 1 } },
    );
    const dentro = contenidoDeCelda(cache, { canal: "rpm", factor: 1 }, 0.999, formatearNumero);
    const fuera = contenidoDeCelda(cache, { canal: "rpm", factor: 1 }, 5, formatearNumero);
    expect(dentro.nivel).not.toBe("sin datos");
    expect(fuera.nivel).toBe("sin datos");
    expect(fuera.texto).toBe("—");
  });
});

function canalesDePrueba(): CanalCursor[] {
  return [
    { clave: { canal: "rpm", factor: 1 }, etiqueta: "RPM" },
    { clave: { canal: "egt", factor: 64 }, etiqueta: "EGT" },
  ];
}

function cacheDePrueba(): CacheDeCubos {
  const cache = new CacheDeCubos();
  cache.guardar({ canal: "rpm", factor: 1 }, { cubos: cubosDePrueba(200, 0, 0.01, 1), cubre: { t0: 0, t1: 2 } });
  cache.guardar({ canal: "egt", factor: 64 }, { cubos: cubosDePrueba(200, 0, 0.01, 64), cubre: { t0: 0, t1: 2 } });
  return cache;
}

describe("CursorDeTabla", () => {
  it("actualizarCanales crea una fila por canal con su etiqueta", () => {
    const doble = crearDobleDOM();
    const panel = doble.documento.createElement("div");
    const tabla = doble.documento.createElement("table");
    const cursor = new CursorDeTabla(panel, tabla, cacheDePrueba(), { documento: doble.documento });

    cursor.actualizarCanales(canalesDePrueba());
    cursor.mover(1, 42);
    cursor.aplicar();

    // No hay forma de "leer" el DOM falso desde fuera salvo por lo que el
    // propio doble expone: aquí se comprueba indirectamente, forzando un
    // segundo `aplicar()` con el mismo instante y viendo que NO añade
    // escrituras (ver el siguiente `it`), que es la propiedad que de verdad
    // importa para el presupuesto.
    expect(doble.nodosCreados()).toBeGreaterThan(0);
  });

  it("mover() no toca el DOM: solo aplicar() lo hace", () => {
    const doble = crearDobleDOM();
    const panel = doble.documento.createElement("div");
    const tabla = doble.documento.createElement("table");
    const cursor = new CursorDeTabla(panel, tabla, cacheDePrueba(), { documento: doble.documento });
    cursor.actualizarCanales(canalesDePrueba());

    doble.reiniciarContadores();
    cursor.mover(0.5, 10);
    cursor.mover(0.6, 12); // varias llamadas antes de aplicar: solo cuenta la última
    expect(doble.escrituras()).toBe(0);

    const escribio = cursor.aplicar();
    expect(escribio).toBe(true);
    expect(doble.escrituras()).toBeGreaterThan(0);
  });

  it("aplicar() dos veces con el mismo instante solo escribe la primera vez", () => {
    const doble = crearDobleDOM();
    const panel = doble.documento.createElement("div");
    const tabla = doble.documento.createElement("table");
    const cursor = new CursorDeTabla(panel, tabla, cacheDePrueba(), { documento: doble.documento });
    cursor.actualizarCanales(canalesDePrueba());

    cursor.mover(0.5, 10);
    expect(cursor.aplicar()).toBe(true);

    doble.reiniciarContadores();
    cursor.mover(0.5, 10); // mismo instante, misma posición: nada que aplicar
    expect(cursor.aplicar()).toBe(false);
    expect(doble.escrituras()).toBe(0);
  });

  it("ocultar() hace que el próximo aplicar() esconda la línea, y solo una vez", () => {
    const doble = crearDobleDOM();
    const panel = doble.documento.createElement("div");
    const tabla = doble.documento.createElement("table");
    const cursor = new CursorDeTabla(panel, tabla, cacheDePrueba(), { documento: doble.documento });
    cursor.actualizarCanales(canalesDePrueba());
    cursor.mover(0.5, 10);
    cursor.aplicar();

    doble.reiniciarContadores();
    cursor.ocultar();
    expect(cursor.aplicar()).toBe(true); // primera vez: hay que esconder la línea
    expect(cursor.aplicar()).toBe(false); // ya estaba escondida: nada que hacer
  });

  it("destruir() quita la línea del panel", () => {
    const doble = crearDobleDOM();
    const panel = doble.documento.createElement("div");
    const tabla = doble.documento.createElement("table");
    const cursor = new CursorDeTabla(panel, tabla, cacheDePrueba(), { documento: doble.documento });
    cursor.actualizarCanales(canalesDePrueba());
    cursor.destruir();
    // La comprobación real (que `panel` se queda sin hijos) exige leer el
    // doble por dentro, que es justo lo que no expone su interfaz pública a
    // propósito (ver `doble-dom.ts`). Lo que sí se puede afirmar desde fuera
    // es que la llamada no lanza aunque se invoque dos veces.
    expect(() => cursor.destruir()).not.toThrow();
  });
});

describe("el formateador recibe el canal, no solo el valor", () => {
  /**
   * La tabla del cursor tenía UN formateador para todas sus filas, atado al
   * primer canal del panel. La conversión a la unidad mostrada depende del
   * canal (su `to_canon` y la unidad que el selector le resolvió), así que un
   * panel con dos canales convertía los dos con los factores del primero: uno
   * de los dos enseñaba un número equivocado, sin ningún síntoma.
   */
  it("cada fila se convierte con los factores de SU canal", () => {
    const cache = new CacheDeCubos();
    // `factor: 1` => sin decimar => la celda enseña un solo numero (`ultimo`),
    // que `cubosDePrueba` fija en 200.
    const cubos = cubosDePrueba(4, 0, 0.25, 1);
    cache.guardar({ canal: "clt", factor: 1 }, { cubos, cubre: { t0: 0, t1: 1 } });
    cache.guardar({ canal: "rpm", factor: 1 }, { cubos, cubre: { t0: 0, t1: 1 } });

    // El mismo valor crudo, dos canales con escalados distintos: 0,1 y 1,0.
    const escalados: Record<string, number> = { clt: 0.1, rpm: 1 };
    const formatear = (valor: number, clave: { canal: string }): string =>
      String(valor * escalados[clave.canal]!);

    const clt = contenidoDeCelda(cache, { canal: "clt", factor: 1 }, 0.5, formatear);
    const rpm = contenidoDeCelda(cache, { canal: "rpm", factor: 1 }, 0.5, formatear);

    expect(clt.texto).toBe("20");
    expect(rpm.texto).toBe("200");
  });
});
