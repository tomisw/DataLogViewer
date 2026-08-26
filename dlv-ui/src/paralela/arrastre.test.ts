/**
 * Pruebas de F2-06 (desfase manual arrastrando el segmento).
 *
 * Dos capas, igual que `navegacion/controlador.test.ts` para el mismo tipo de
 * problema:
 *
 *   - `segundosPorPixel`/`offsetTrasArrastre` son aritmética pura: se prueban
 *     con números a secas, sin ningún evento ni elemento de por medio. Aquí
 *     es donde se comprueba EXPLÍCITAMENTE el signo del arrastre (la
 *     advertencia de la tarea: al revés, el usuario arrastra a la derecha y
 *     el log se va a la izquierda).
 *   - `ArrastreDeSegmento` es el cableado de eventos. `vitest.config.ts` corre
 *     en `environment: "node"` (sin DOM ni jsdom instalado), así que el doble
 *     de `ElementoNavegable` es un objeto plano que guarda oyentes en un
 *     `Map` y los dispara a mano — el mismo doble, calcado, que ya usa
 *     `navegacion/controlador.test.ts` para el mismo tipo de interfaz. Lo que
 *     se prueba no es "funciona en un navegador" (eso no se puede sin uno)
 *     sino el contrato: qué evento produce qué offset, cuántas veces se
 *     notifica por fotograma, y que cancelar restaura el valor de partida.
 */

import { describe, expect, it, vi } from "vitest";

import {
  ArrastreDeSegmento,
  offsetTrasArrastre,
  segundosPorPixel,
  type InfoArrastreDeSegmento,
  type RangoTemporal,
} from "./arrastre.ts";
import type { ElementoNavegable, OyenteDeEvento } from "../navegacion/elemento.ts";

const RANGO: RangoTemporal = { t0: 100, t1: 200 }; // 100 s visibles
const ANCHO_PANEL_PX = 800; // 0.125 s/px

/** Doble de `ElementoNavegable`, calcado de `navegacion/controlador.test.ts`. */
function crearAsaFalsa() {
  const oyentesPorTipo = new Map<string, Set<OyenteDeEvento>>();
  const capturas: number[] = [];
  const liberaciones: number[] = [];

  const asa: ElementoNavegable = {
    addEventListener(tipo, oyente) {
      if (!oyentesPorTipo.has(tipo)) oyentesPorTipo.set(tipo, new Set());
      oyentesPorTipo.get(tipo)!.add(oyente);
    },
    removeEventListener(tipo, oyente) {
      oyentesPorTipo.get(tipo)?.delete(oyente);
    },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: ANCHO_PANEL_PX, height: 400 }),
    setPointerCapture: (id) => capturas.push(id),
    releasePointerCapture: (id) => liberaciones.push(id),
  };

  return {
    asa,
    capturas,
    liberaciones,
    numeroDeOyentes: (tipo: string) => oyentesPorTipo.get(tipo)?.size ?? 0,
    disparar(tipo: string, datos: Record<string, unknown>) {
      const preventDefault = vi.fn();
      const evento = { preventDefault, ...datos } as unknown as Event;
      for (const oyente of oyentesPorTipo.get(tipo) ?? []) oyente(evento);
      return { preventDefault };
    },
  };
}

/** Programador de fotograma controlado a mano, igual que en `controlador.test.ts`. */
function crearFotogramaFalso() {
  let siguienteId = 1;
  let vecesProgramado = 0;
  const resolutores = new Map<number, () => void>();
  const orden: number[] = [];
  return {
    programar: (resolver: () => void): number => {
      const id = siguienteId;
      siguienteId += 1;
      vecesProgramado += 1;
      resolutores.set(id, resolver);
      orden.push(id);
      return id;
    },
    cancelar: (id: number) => resolutores.delete(id),
    numeroDeProgramaciones: () => vecesProgramado,
    ejecutarUno(): void {
      while (orden.length > 0) {
        const id = orden.shift()!;
        const resolver = resolutores.get(id);
        resolutores.delete(id);
        if (resolver !== undefined) {
          resolver();
          return;
        }
      }
    },
  };
}

function crearArrastre(offsetInicial = 0) {
  const falsa = crearAsaFalsa();
  const fotograma = crearFotogramaFalso();
  const cambios: InfoArrastreDeSegmento[] = [];
  let offsetActual = offsetInicial;
  const arrastre = new ArrastreDeSegmento(
    falsa.asa,
    "log-a",
    () => offsetActual,
    () => RANGO,
    () => ANCHO_PANEL_PX,
    (info) => {
      cambios.push(info);
      offsetActual = info.offset;
    },
    { programarFotograma: fotograma.programar, cancelarFotograma: fotograma.cancelar },
  );
  return { arrastre, falsa, fotograma, cambios, obtenerOffsetActual: () => offsetActual };
}

describe("segundosPorPixel", () => {
  it("es el ancho visible entre el ancho del panel", () => {
    expect(segundosPorPixel(RANGO, ANCHO_PANEL_PX)).toBeCloseTo(0.125);
  });

  it("da 0 con un panel de ancho no positivo, en vez de dividir por cero o negativo", () => {
    expect(segundosPorPixel(RANGO, 0)).toBe(0);
    expect(segundosPorPixel(RANGO, -10)).toBe(0);
  });
});

describe("offsetTrasArrastre — signo del arrastre", () => {
  it("arrastrar a la DERECHA (deltaXPx > 0) AUMENTA el offset (el segmento sigue al puntero)", () => {
    const nuevo = offsetTrasArrastre(10, 80, RANGO, ANCHO_PANEL_PX);
    // 80 px * 0.125 s/px = 10 s. El log tiene que moverse a la derecha, es
    // decir, offset creciente: 10 + 10 = 20, nunca 10 - 10 = 0.
    expect(nuevo).toBeCloseTo(20);
    expect(nuevo).toBeGreaterThan(10);
  });

  it("arrastrar a la IZQUIERDA (deltaXPx < 0) DISMINUYE el offset", () => {
    const nuevo = offsetTrasArrastre(10, -80, RANGO, ANCHO_PANEL_PX);
    expect(nuevo).toBeCloseTo(0);
    expect(nuevo).toBeLessThan(10);
  });

  it("deltaXPx = 0 no cambia el offset", () => {
    expect(offsetTrasArrastre(42, 0, RANGO, ANCHO_PANEL_PX)).toBe(42);
  });

  it("se recalcula siempre desde offsetInicial, no por acumulación incremental", () => {
    // Tres "fotogramas" del mismo gesto, cada uno con el delta TOTAL desde el
    // inicio (que es como lo usa `ArrastreDeSegmento`, no sumando deltas
    // parciales): el resultado del último tiene que ser exacto, sin arrastre
    // de error de los pasos intermedios.
    const a = offsetTrasArrastre(5, 40, RANGO, ANCHO_PANEL_PX);
    const b = offsetTrasArrastre(5, 80, RANGO, ANCHO_PANEL_PX);
    const c = offsetTrasArrastre(5, 160, RANGO, ANCHO_PANEL_PX);
    expect(a).toBeCloseTo(10);
    expect(b).toBeCloseTo(15);
    expect(c).toBeCloseTo(25);
  });

  it("con otra escala (vista más ancha), el mismo píxel vale más segundos", () => {
    const rangoAmplio: RangoTemporal = { t0: 0, t1: 1000 }; // 1.25 s/px
    const nuevo = offsetTrasArrastre(0, 80, rangoAmplio, ANCHO_PANEL_PX);
    expect(nuevo).toBeCloseTo(100);
  });
});

describe("ArrastreDeSegmento — cableado de eventos", () => {
  it("registra un oyente por tipo de evento y los retira en destruir()", () => {
    const { arrastre, falsa } = crearArrastre();
    expect(falsa.numeroDeOyentes("pointerdown")).toBe(1);
    expect(falsa.numeroDeOyentes("pointermove")).toBe(1);
    expect(falsa.numeroDeOyentes("pointerup")).toBe(1);
    expect(falsa.numeroDeOyentes("pointercancel")).toBe(1);
    expect(falsa.numeroDeOyentes("keydown")).toBe(1);

    arrastre.destruir();
    expect(falsa.numeroDeOyentes("pointerdown")).toBe(0);
    expect(falsa.numeroDeOyentes("pointermove")).toBe(0);
    expect(falsa.numeroDeOyentes("pointerup")).toBe(0);
    expect(falsa.numeroDeOyentes("pointercancel")).toBe(0);
    expect(falsa.numeroDeOyentes("keydown")).toBe(0);
  });

  it("un arrastre completo (down, move, up) notifica el offset final con la identidad del segmento", () => {
    const { falsa, fotograma, cambios } = crearArrastre(10);

    falsa.disparar("pointerdown", { pointerId: 1, button: 0, clientX: 300 });
    expect(falsa.capturas).toEqual([1]);

    falsa.disparar("pointermove", { pointerId: 1, clientX: 380 }); // +80px = +10s
    expect(fotograma.numeroDeProgramaciones()).toBe(1);
    fotograma.ejecutarUno();

    expect(cambios).toHaveLength(1);
    expect(cambios[0]).toEqual({ idSegmento: "log-a", offset: 20 });

    falsa.disparar("pointerup", { pointerId: 1 });
    expect(falsa.liberaciones).toEqual([1]);
    // Soltar no dispara una notificación aparte: el último valor pedido ya es
    // el definitivo.
    expect(cambios).toHaveLength(1);
  });

  it("varios pointermove en el mismo fotograma solo notifican una vez, con el último valor", () => {
    const { falsa, fotograma, cambios } = crearArrastre(0);

    falsa.disparar("pointerdown", { pointerId: 1, button: 0, clientX: 0 });
    falsa.disparar("pointermove", { pointerId: 1, clientX: 40 });
    falsa.disparar("pointermove", { pointerId: 1, clientX: 80 });
    falsa.disparar("pointermove", { pointerId: 1, clientX: 160 });
    expect(fotograma.numeroDeProgramaciones()).toBe(1); // un solo fotograma pedido

    fotograma.ejecutarUno();
    expect(cambios).toHaveLength(1);
    expect(cambios[0]!.offset).toBeCloseTo(20); // 160px * 0.125 s/px, no la suma de los tres
  });

  it("ignora pointermove/pointerup de un pointerId distinto (otro dedo/puntero)", () => {
    const { falsa, fotograma, cambios } = crearArrastre(5);

    falsa.disparar("pointerdown", { pointerId: 1, button: 0, clientX: 0 });
    falsa.disparar("pointermove", { pointerId: 2, clientX: 500 }); // puntero ajeno
    expect(fotograma.numeroDeProgramaciones()).toBe(0);
    expect(cambios).toHaveLength(0);

    falsa.disparar("pointerup", { pointerId: 2 }); // tampoco cierra el gesto de 1
    falsa.disparar("pointermove", { pointerId: 1, clientX: 80 });
    fotograma.ejecutarUno();
    expect(cambios).toHaveLength(1);
    expect(cambios[0]!.offset).toBeCloseTo(15);
  });

  it("ignora pointerdown con botón secundario/auxiliar", () => {
    const { falsa, fotograma } = crearArrastre();
    falsa.disparar("pointerdown", { pointerId: 1, button: 2, clientX: 100 });
    falsa.disparar("pointermove", { pointerId: 1, clientX: 500 });
    expect(fotograma.numeroDeProgramaciones()).toBe(0);
    expect(falsa.capturas).toEqual([]);
  });

  it("Escape cancela el gesto y restaura offsetInicial", () => {
    const { arrastre, falsa, fotograma, cambios } = crearArrastre(30);

    falsa.disparar("pointerdown", { pointerId: 1, button: 0, clientX: 0 });
    falsa.disparar("pointermove", { pointerId: 1, clientX: 400 }); // +50s en curso
    fotograma.ejecutarUno();
    expect(cambios[0]!.offset).toBeCloseTo(80);
    expect(arrastre.enCurso).toBe(true);

    const { preventDefault } = falsa.disparar("keydown", { key: "Escape" });
    expect(preventDefault).toHaveBeenCalled();
    expect(falsa.liberaciones).toEqual([1]);
    expect(arrastre.enCurso).toBe(false);

    fotograma.ejecutarUno();
    expect(cambios).toHaveLength(2);
    expect(cambios[1]).toEqual({ idSegmento: "log-a", offset: 30 }); // vuelve al inicial

    // Un pointermove después de cancelar no reabre el gesto.
    falsa.disparar("pointermove", { pointerId: 1, clientX: 9999 });
    expect(fotograma.numeroDeProgramaciones()).toBe(2);
  });

  it("Escape sin gesto en curso no hace nada", () => {
    const { falsa, fotograma, cambios } = crearArrastre(7);
    falsa.disparar("keydown", { key: "Escape" });
    expect(fotograma.numeroDeProgramaciones()).toBe(0);
    expect(cambios).toHaveLength(0);
  });

  it("otra tecla que no sea Escape no interfiere con el gesto en curso", () => {
    const { falsa, fotograma, cambios } = crearArrastre(0);
    falsa.disparar("pointerdown", { pointerId: 1, button: 0, clientX: 0 });
    falsa.disparar("keydown", { key: "a" });
    falsa.disparar("pointermove", { pointerId: 1, clientX: 80 });
    fotograma.ejecutarUno();
    expect(cambios).toHaveLength(1);
    expect(cambios[0]!.offset).toBeCloseTo(10);
  });

  it("pointercancel también cancela y restaura offsetInicial", () => {
    const { falsa, fotograma, cambios } = crearArrastre(12);
    falsa.disparar("pointerdown", { pointerId: 1, button: 0, clientX: 0 });
    falsa.disparar("pointermove", { pointerId: 1, clientX: 80 });
    fotograma.ejecutarUno();
    expect(cambios[0]!.offset).toBeCloseTo(22);

    // `pointercancel` usa el mismo manejador que `pointerup` (fin del
    // puntero): cierra el gesto sin restaurar por sí solo. Es `Escape` (o
    // `cancelar()` desde fuera) quien decide "deshacer lo arrastrado" — un
    // `pointercancel` del navegador no siempre significa que el usuario
    // quisiera deshacer, así que este módulo no asume esa intención por él.
    falsa.disparar("pointercancel", { pointerId: 1 });
    expect(cambios).toHaveLength(1);
    expect(cambios[0]!.offset).toBeCloseTo(22);
  });

  it("cancelar() público permite deshacer el gesto desde fuera (p. ej. al perder el foco)", () => {
    const { arrastre, falsa, fotograma, cambios } = crearArrastre(-5);
    falsa.disparar("pointerdown", { pointerId: 1, button: 0, clientX: 0 });
    falsa.disparar("pointermove", { pointerId: 1, clientX: -40 });
    fotograma.ejecutarUno();
    expect(cambios[0]!.offset).toBeCloseTo(-10);

    arrastre.cancelar();
    fotograma.ejecutarUno();
    expect(cambios).toHaveLength(2);
    expect(cambios[1]!.offset).toBeCloseTo(-5);
    expect(falsa.liberaciones).toEqual([1]);
  });

  it("un segundo gesto tras soltar el primero parte del offset ya confirmado", () => {
    const { falsa, fotograma, cambios } = crearArrastre(0);

    falsa.disparar("pointerdown", { pointerId: 1, button: 0, clientX: 0 });
    falsa.disparar("pointermove", { pointerId: 1, clientX: 80 });
    fotograma.ejecutarUno();
    falsa.disparar("pointerup", { pointerId: 1 });
    expect(cambios[0]!.offset).toBeCloseTo(10);

    falsa.disparar("pointerdown", { pointerId: 2, button: 0, clientX: 1000 });
    falsa.disparar("pointermove", { pointerId: 2, clientX: 1080 });
    fotograma.ejecutarUno();
    expect(cambios).toHaveLength(2);
    expect(cambios[1]!.offset).toBeCloseTo(20); // 10 (confirmado) + 10 (nuevo delta)
  });
});
