/**
 * Pruebas del cableado de eventos (F1-28).
 *
 * `vitest.config.ts` corre en `environment: "node"`, sin DOM ni jsdom
 * instalado (ver el comentario de `unidades/dom-falso.ts`, mismo motivo).
 * Por eso `ElementoNavegable` existe: el doble de aquí es un objeto plano
 * que registra oyentes en un `Map` y los dispara a mano, y el programador de
 * fotograma es una cola controlada por la prueba en vez de
 * `requestAnimationFrame` real. Lo que se prueba no es "funciona en un
 * navegador" (eso no se puede, sin uno) sino el contrato que sí importa
 * aquí: qué evento produce qué `Vista`, y que nunca se notifica más de una
 * vez por fotograma.
 */

import { describe, expect, it, vi } from "vitest";

import { ControladorDeNavegacion, type InfoNavegacion } from "./controlador.ts";
import type { ElementoNavegable, OyenteDeEvento, RectanguloDelElemento } from "./elemento.ts";
import type { Vista } from "../render/tipos.ts";

const VISTA_INICIAL: Vista = { t0: 0, t1: 100, v0: 0, v1: 50 };
const RECT: RectanguloDelElemento = { left: 0, top: 0, width: 800, height: 400 };

/** Doble de `ElementoNavegable`: guarda oyentes y permite dispararlos a mano. */
function crearElementoFalso(rect: RectanguloDelElemento = RECT) {
  const oyentesPorTipo = new Map<string, Set<OyenteDeEvento>>();
  const capturas: number[] = [];
  const liberaciones: number[] = [];

  const elemento: ElementoNavegable = {
    addEventListener(tipo, oyente) {
      if (!oyentesPorTipo.has(tipo)) oyentesPorTipo.set(tipo, new Set());
      oyentesPorTipo.get(tipo)!.add(oyente);
    },
    removeEventListener(tipo, oyente) {
      oyentesPorTipo.get(tipo)?.delete(oyente);
    },
    getBoundingClientRect: () => rect,
    setPointerCapture: (id) => capturas.push(id),
    releasePointerCapture: (id) => liberaciones.push(id),
  };

  return {
    elemento,
    capturas,
    liberaciones,
    numeroDeOyentes: (tipo: string) => oyentesPorTipo.get(tipo)?.size ?? 0,
    /** Devuelve el espía de `preventDefault`, para comprobar que se llamó. */
    disparar(tipo: string, datos: Record<string, unknown>) {
      const preventDefault = vi.fn();
      const evento = { preventDefault, ...datos } as unknown as Event;
      for (const oyente of oyentesPorTipo.get(tipo) ?? []) oyente(evento);
      return { preventDefault };
    },
  };
}

/** Programador de fotograma controlado a mano: nada se resuelve hasta `ejecutarUno()`. */
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
    /**
     * Cuántas veces se PIDIÓ un fotograma en total, se haya resuelto,
     * cancelado o siga pendiente. Un contador aparte de `orden`, que sí se
     * vacía a medida que `ejecutarUno()` consume la cola.
     */
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

function crearControlador(
  opciones: Partial<{
    limites: Vista;
    pasoPanTeclado: number;
    pasoZoomTeclado: number;
    sensibilidadRueda: number;
    umbralGestoMs: number;
  }> = {},
) {
  const falso = crearElementoFalso();
  const fotograma = crearFotogramaFalso();
  let reloj = 0;
  const cambios: InfoNavegacion[] = [];
  const controlador = new ControladorDeNavegacion(
    falso.elemento,
    VISTA_INICIAL,
    (info) => cambios.push(info),
    {
      ...opciones,
      ahora: () => reloj,
      programarFotograma: fotograma.programar,
      cancelarFotograma: fotograma.cancelar,
    },
  );
  return {
    controlador,
    falso,
    fotograma,
    cambios,
    avanzarReloj: (ms: number) => {
      reloj += ms;
    },
  };
}

describe("rueda", () => {
  it("amplía centrado en el puntero, no en el centro del panel", () => {
    const { falso, fotograma, cambios } = crearControlador();
    const { preventDefault } = falso.disparar("wheel", { clientX: 200, clientY: 100, deltaY: -100 });
    expect(preventDefault).toHaveBeenCalled();

    fotograma.ejecutarUno();
    expect(cambios).toHaveLength(1);
    const nueva = cambios[0]!.vista;
    // El puntero está en fracción 200/800 = 0.25 del ancho: ese punto de dato
    // tiene que seguir en la misma fracción tras ampliar.
    const puntoAntes = VISTA_INICIAL.t0 + 0.25 * (VISTA_INICIAL.t1 - VISTA_INICIAL.t0);
    const puntoDespues = nueva.t0 + 0.25 * (nueva.t1 - nueva.t0);
    expect(puntoDespues).toBeCloseTo(puntoAntes, 6);
    expect(nueva.t1 - nueva.t0).toBeLessThan(VISTA_INICIAL.t1 - VISTA_INICIAL.t0);
    // El eje de valores no lo toca la rueda (F1-27 decide su autoescala).
    expect(nueva.v0).toBe(VISTA_INICIAL.v0);
    expect(nueva.v1).toBe(VISTA_INICIAL.v1);
  });

  it("no notifica más de una vez por fotograma aunque lleguen varios eventos", () => {
    const { falso, fotograma, cambios } = crearControlador();
    for (let i = 0; i < 5; i += 1) {
      falso.disparar("wheel", { clientX: 400, clientY: 200, deltaY: -50 });
    }
    // Cinco eventos, pero un solo fotograma pedido: el segundo al quinto
    // evento encontraron ya uno pendiente y no pidieron otro.
    expect(fotograma.numeroDeProgramaciones()).toBe(1);
    expect(cambios).toHaveLength(0); // todavía no se ha resuelto ningún fotograma

    fotograma.ejecutarUno();
    expect(cambios).toHaveLength(1); // y esa única notificación ya trae el último estado
  });
});

describe("arrastre por pointer events", () => {
  it("usa setPointerCapture y no se pierde si el puntero sale del panel", () => {
    const { falso, fotograma, cambios } = crearControlador();
    falso.disparar("pointerdown", { pointerId: 7, button: 0, clientX: 100, clientY: 100 });
    expect(falso.capturas).toEqual([7]);

    // Coordenadas fuera del rectángulo del panel: con `setPointerCapture` el
    // navegador seguiría entregando `pointermove` igualmente.
    falso.disparar("pointermove", { pointerId: 7, clientX: 900, clientY: -50 });
    fotograma.ejecutarUno();
    expect(cambios).toHaveLength(1);
    expect(cambios[0]!.vista).not.toEqual(VISTA_INICIAL);

    falso.disparar("pointerup", { pointerId: 7 });
    expect(falso.liberaciones).toEqual([7]);
  });

  it("un arrastre horizontal puro no cambia el eje de valores", () => {
    const { falso, fotograma, cambios } = crearControlador();
    falso.disparar("pointerdown", { pointerId: 1, button: 0, clientX: 0, clientY: 0 });
    falso.disparar("pointermove", { pointerId: 1, clientX: 80, clientY: 0 });
    fotograma.ejecutarUno();
    expect(cambios[0]!.vista.v0).toBe(VISTA_INICIAL.v0);
    expect(cambios[0]!.vista.v1).toBe(VISTA_INICIAL.v1);
  });

  it("ignora el botón secundario del ratón", () => {
    const { falso, fotograma, cambios } = crearControlador();
    falso.disparar("pointerdown", { pointerId: 2, button: 2, clientX: 0, clientY: 0 });
    falso.disparar("pointermove", { pointerId: 2, clientX: 200, clientY: 0 });
    expect(fotograma.numeroDeProgramaciones()).toBe(0);
    expect(cambios).toHaveLength(0);
  });
});

describe("teclado", () => {
  it("las flechas desplazan; una tras otra actualizan la dirección", () => {
    const { falso, fotograma, cambios, controlador } = crearControlador();
    falso.disparar("keydown", { key: "ArrowRight" });
    fotograma.ejecutarUno();
    expect(cambios[0]!.vista.t0).toBeGreaterThan(VISTA_INICIAL.t0);
    expect(controlador.direccion).toBe(1);

    falso.disparar("keydown", { key: "ArrowLeft" });
    falso.disparar("keydown", { key: "ArrowLeft" });
    fotograma.ejecutarUno();
    expect(controlador.direccion).toBe(-1);
  });

  it("+/- amplían o alejan centrado en el panel, sin tocar el eje de valores", () => {
    const { falso, fotograma, cambios } = crearControlador();
    falso.disparar("keydown", { key: "+" });
    fotograma.ejecutarUno();
    const anchoAmpliado = cambios[0]!.vista.t1 - cambios[0]!.vista.t0;
    expect(anchoAmpliado).toBeLessThan(VISTA_INICIAL.t1 - VISTA_INICIAL.t0);
    expect(cambios[0]!.vista.v0).toBe(VISTA_INICIAL.v0);
  });

  it('"Home" vuelve a los límites fijados; sin límites, no hace nada', () => {
    const sinLimites = crearControlador();
    sinLimites.falso.disparar("keydown", { key: "ArrowRight" });
    sinLimites.fotograma.ejecutarUno();
    sinLimites.falso.disparar("keydown", { key: "Home" });
    expect(sinLimites.fotograma.numeroDeProgramaciones()).toBe(1); // no se pidió un segundo fotograma

    const limites: Vista = { t0: -1000, t1: 1000, v0: -10, v1: 10 };
    const conLimites = crearControlador({ limites });
    conLimites.falso.disparar("keydown", { key: "ArrowRight" });
    conLimites.fotograma.ejecutarUno();
    conLimites.falso.disparar("keydown", { key: "Home" });
    conLimites.fotograma.ejecutarUno();
    expect(conLimites.cambios.at(-1)!.vista).toEqual(limites);
  });

  it("Ctrl+Z deshace y Ctrl+Shift+Z rehace un gesto de teclado", () => {
    const { falso, fotograma, cambios } = crearControlador();
    falso.disparar("keydown", { key: "ArrowRight" });
    fotograma.ejecutarUno();
    const trasMover = cambios[0]!.vista;

    falso.disparar("keydown", { key: "z", ctrlKey: true });
    fotograma.ejecutarUno();
    expect(cambios.at(-1)!.vista).toEqual(VISTA_INICIAL);

    falso.disparar("keydown", { key: "Z", ctrlKey: true, shiftKey: true });
    fotograma.ejecutarUno();
    expect(cambios.at(-1)!.vista).toEqual(trasMover);
  });
});

describe("destruir", () => {
  it("retira los oyentes y cancela el fotograma pendiente", () => {
    const { falso, fotograma, controlador } = crearControlador();
    expect(falso.numeroDeOyentes("wheel")).toBe(1);
    falso.disparar("wheel", { clientX: 0, clientY: 0, deltaY: -10 });
    expect(fotograma.numeroDeProgramaciones()).toBe(1);

    controlador.destruir();
    expect(falso.numeroDeOyentes("wheel")).toBe(0);
    expect(falso.numeroDeOyentes("pointerdown")).toBe(0);
    expect(falso.numeroDeOyentes("keydown")).toBe(0);

    // Un evento disparado después de destruir no encuentra oyentes: no revienta.
    expect(() => falso.disparar("keydown", { key: "ArrowRight" })).not.toThrow();
  });
});
