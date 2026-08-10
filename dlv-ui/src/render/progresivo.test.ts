/**
 * Pruebas de la decisión del renderizado progresivo (F2-14).
 *
 * Lo que aquí se puede equivocar en silencio es exactamente lo que la tarea
 * viene a evitar: elegir como silueta un nivel que cuesta más que el dato
 * bueno, dibujar un trazo provisional que no se distingue del definitivo, o
 * quedarse con un refinamiento de un encuadre que el usuario ya abandonó. Los
 * tres producen algo plausible en pantalla, que es la peor clase de fallo de
 * este módulo.
 */

import { describe, expect, it } from "vitest";

import {
  ALFA_SILUETA,
  marcaDeSilueta,
  motivoDeAbandono,
  nivelesUtilizables,
  notaCombinada,
  planificar,
  type NivelEnMemoria,
} from "./progresivo.ts";
import type { Color } from "./tipos.ts";

/** Un nivel cacheado que cubre de sobra el tramo de las pruebas. */
function enMemoria(factor: number, t0 = -100, t1 = 100): NivelEnMemoria {
  return { factor, cubre: { t0, t1 } };
}

const VISIBLE = { t0: 10, t1: 20 };

describe("nivelesUtilizables", () => {
  it("solo cuenta lo que cubre el tramo visible ENTERO", () => {
    // Media cobertura dibujaría medio panel: se lee como «el log se corta
    // aquí», que es un diagnóstico falso.
    const niveles = [
      enMemoria(64, 0, 15), // se queda a medias por la derecha
      enMemoria(256, 12, 100), // se queda a medias por la izquierda
      enMemoria(1024, 0, 100), // cubre
    ];
    expect(nivelesUtilizables(niveles, VISIBLE)).toEqual([1024]);
  });

  it("un tramo que encaja justo en los bordes sí cubre", () => {
    expect(nivelesUtilizables([enMemoria(4, 10, 20)], VISIBLE)).toEqual([4]);
  });

  it("devuelve los factores ordenados de fino a grueso", () => {
    const niveles = [enMemoria(256), enMemoria(4), enMemoria(64)];
    expect(nivelesUtilizables(niveles, VISIBLE)).toEqual([4, 64, 256]);
  });

  it("sin nada en memoria devuelve la lista vacía en vez de fallar", () => {
    expect(nivelesUtilizables([], VISIBLE)).toEqual([]);
  });
});

describe("planificar", () => {
  it("si el nivel del zoom ya está en memoria, no hay nada provisional", () => {
    const plan = planificar(16, [enMemoria(16), enMemoria(1024)], VISIBLE);
    expect(plan).toEqual({ tipo: "definitivo", factor: 16 });
  });

  it("con el objetivo ausente coge el más fino de los MÁS GRUESOS", () => {
    // El caso real: se abrió el log con el nivel grueso y ahora se amplía.
    const plan = planificar(16, [enMemoria(64), enMemoria(256), enMemoria(1024)], VISIBLE);
    expect(plan).toEqual({ tipo: "silueta", factor: 64, factorObjetivo: 16 });
  });

  it("nunca elige como silueta un nivel MÁS FINO que el objetivo", () => {
    // Subir un nivel más fino que el objetivo cuesta más que subir el dato
    // bueno: se pagaría dos veces el mismo fotograma, justo en el gesto que
    // esta tarea viene a hacer fluido. Y rompería el significado de la marca.
    const plan = planificar(64, [enMemoria(1), enMemoria(4)], VISIBLE);
    expect(plan).toEqual({ tipo: "a-ciegas", factorObjetivo: 64 });
  });

  it("con el objetivo ausente y solo niveles más finos y más gruesos, gana el grueso", () => {
    const plan = planificar(64, [enMemoria(4), enMemoria(256)], VISIBLE);
    expect(plan).toEqual({ tipo: "silueta", factor: 256, factorObjetivo: 64 });
  });

  it("sin nada que cubra lo visible no se dibuja de mentira", () => {
    // Al abrir un log no hay nada cacheado. Reutilizar lo último que hubiera de
    // OTRO rango de tiempo sería peor que un panel vacío: sería un trazo que no
    // corresponde a los segundos que rotula el eje.
    const plan = planificar(16, [enMemoria(1024, 500, 900)], VISIBLE);
    expect(plan).toEqual({ tipo: "a-ciegas", factorObjetivo: 16 });
  });

  it("un nivel en memoria que no cubre no cuenta ni como definitivo", () => {
    const plan = planificar(16, [enMemoria(16, 0, 15)], VISIBLE);
    expect(plan).toEqual({ tipo: "a-ciegas", factorObjetivo: 16 });
  });
});

describe("marcaDeSilueta", () => {
  const azul: Color = { r: 0.2, g: 0.5, b: 1, a: 1 };

  it("baja la opacidad y no toca el matiz", () => {
    // El matiz identifica el canal (`colorPorIndice`): cambiarlo haría que la
    // silueta de un canal se confundiera con el color de otro.
    const marca = marcaDeSilueta(azul, 256, 16);
    expect(marca.color.r).toBe(azul.r);
    expect(marca.color.g).toBe(azul.g);
    expect(marca.color.b).toBe(azul.b);
    expect(marca.color.a).toBeCloseTo(ALFA_SILUETA, 12);
  });

  it("la opacidad es un factor, no un valor fijo", () => {
    // Una serie que ya venga translúcida no puede volverse más opaca al pasar a
    // provisional, que es lo que haría asignar `a = ALFA_SILUETA` a secas.
    const tenue = marcaDeSilueta({ ...azul, a: 0.5 }, 256, 16);
    expect(tenue.color.a).toBeCloseTo(0.5 * ALFA_SILUETA, 12);
  });

  it("la nota dice el factor de la silueta Y el que tocaría", () => {
    // Es la parte que de verdad impide leer mal un número: la opacidad se nota
    // comparando dos curvas, el factor se lee en una sola.
    const marca = marcaDeSilueta(azul, 256, 16);
    expect(marca.nota).toContain("×256");
    expect(marca.nota).toContain("×16");
    expect(marca.nota).not.toBe("");
  });

  it("la silueta se distingue del definitivo: menos alfa y aviso propio", () => {
    // La propiedad central de la tarea, escrita como propiedad y no como
    // constante: si alguien pone `ALFA_SILUETA = 1` «porque se veía mejor»,
    // esto se pone rojo.
    const marca = marcaDeSilueta(azul, 256, 16);
    expect(marca.color.a).toBeLessThan(azul.a);
    expect(marca.nota.length).toBeGreaterThan(0);
  });
});

describe("notaCombinada", () => {
  it("no repite el mismo aviso una vez por canal", () => {
    const nota = "silueta ×64 · el detalle de este zoom es ×16 · refinando…";
    expect(notaCombinada([nota, nota, nota])).toBe(nota);
  });

  it("junta avisos distintos", () => {
    expect(notaCombinada(["a", "b"])).toContain("a");
    expect(notaCombinada(["a", "b"])).toContain("b");
  });

  it("sin avisos la nota es vacía, para que el adorno desaparezca", () => {
    expect(notaCombinada([])).toBe("");
    expect(notaCombinada(["", ""])).toBe("");
  });
});

describe("motivoDeAbandono", () => {
  it("una reconstrucción por el medio invalida la pasada entera", () => {
    expect(
      motivoDeAbandono({ generacionAlPedir: 3, generacionAhora: 4, hayPasadaPendiente: false }),
    ).toBe("reconstruccion");
  });

  it("la reconstrucción gana a la vista movida", () => {
    // No es un empate estético: con el panel destruido no se puede ni guardar
    // en su caché de subidas, mientras que con la vista movida sí hay que
    // guardar los cubos recién llegados.
    expect(
      motivoDeAbandono({ generacionAlPedir: 3, generacionAhora: 4, hayPasadaPendiente: true }),
    ).toBe("reconstruccion");
  });

  it("si el usuario siguió moviéndose, este encuadre ya no es el suyo", () => {
    expect(
      motivoDeAbandono({ generacionAlPedir: 3, generacionAhora: 3, hayPasadaPendiente: true }),
    ).toBe("vista-movida");
  });

  it("con el gesto parado y los paneles vivos, el refinamiento se aplica", () => {
    expect(
      motivoDeAbandono({ generacionAlPedir: 3, generacionAhora: 3, hayPasadaPendiente: false }),
    ).toBe(null);
  });
});
