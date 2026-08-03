/**
 * Pruebas de `PanelesApilados` contra el doble de `doble-dom.ts` (sin
 * navegador, ver su cabecera y la de `contexto-dom.ts`).
 *
 * Dos grupos con intención distinta:
 *
 * - "eje X compartido" es la prueba que pide la tarea explícitamente: si un
 *   panel se desincroniza del resto en su ancho de contenido, la lectura de
 *   causa/efecto entre canales apilados es falsa y nada en pantalla lo
 *   delata (ver la cabecera de `paneles.ts`). Se comprueba tras construir,
 *   tras arrastrar un divisor y tras un recálculo de contenedor: las tres
 *   operaciones que existen en este módulo y que podrían romper el
 *   invariante si alguien tocara el ancho por panel en vez del compartido.
 * - "arrastrar canales" comprueba la secuencia completa de *pointer events*
 *   de un arrastre: qué se resalta antes de soltar, qué pasa si se suelta
 *   fuera de cualquier panel, y que `pointercancel` no cuenta como un "sí".
 */

import { describe, expect, it } from "vitest";

import { crearContextoDomFalso, disparar, type ElementoFalso } from "./doble-dom.ts";
import type { ElementoDOM } from "./contexto-dom.ts";
import { PanelesApilados } from "./paneles.ts";
import type { CambioAsignacion, DefinicionPanel } from "./tipos.ts";

function comoFalso(elemento: ElementoDOM): ElementoFalso {
  return elemento as unknown as ElementoFalso;
}

/** Busca en `elemento` y sus descendientes todos los que tengan el atributo (con el valor dado, si se pasa). */
function buscar(elemento: ElementoFalso, atributo: string, valor?: string): ElementoFalso[] {
  const encontrados: ElementoFalso[] = [];
  const propio = elemento.atributos.get(atributo);
  if (propio !== undefined && (valor === undefined || propio === valor)) encontrados.push(elemento);
  for (const hijo of elemento.hijos) encontrados.push(...buscar(hijo, atributo, valor));
  return encontrados;
}

function unico(elementos: readonly ElementoFalso[]): ElementoFalso {
  if (elementos.length !== 1) throw new Error(`se esperaba un único elemento, salieron ${elementos.length}`);
  return elementos[0]!;
}

function definiciones(): DefinicionPanel[] {
  return [
    {
      id: "p1",
      canales: [
        { id: "rpm", etiqueta: "RPM" },
        { id: "map", etiqueta: "MAP" },
      ],
    },
    { id: "p2", canales: [{ id: "tps", etiqueta: "TPS" }] },
    { id: "p3", canales: [] },
  ];
}

function montar(altoContenedor = 600, anchoContenedor = 800) {
  const documento = crearContextoDomFalso();
  const contenedor = comoFalso(documento.createElement("div"));
  contenedor.fijarRectangulo({ top: 0, bottom: altoContenedor, left: 0, right: anchoContenedor });
  return { documento, contenedor };
}

/** Simula tres paneles apilados de 200px cada uno: el doble no calcula layout, así que hay que dárselo. */
function prepararRectsDePaneles(contenedorFalso: ElementoFalso, anchoContenedor = 800): void {
  const p1 = unico(buscar(contenedorFalso, "data-panel-id", "p1"));
  const p2 = unico(buscar(contenedorFalso, "data-panel-id", "p2"));
  const p3 = unico(buscar(contenedorFalso, "data-panel-id", "p3"));
  p1.fijarRectangulo({ top: 0, bottom: 200, left: 0, right: anchoContenedor });
  p2.fijarRectangulo({ top: 200, bottom: 400, left: 0, right: anchoContenedor });
  p3.fijarRectangulo({ top: 400, bottom: 600, left: 0, right: anchoContenedor });
}

describe("PanelesApilados: construcción", () => {
  it("crea un panel por definición, en el mismo orden, con sus canales iniciales", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    expect(paneles.ordenPaneles()).toEqual(["p1", "p2", "p3"]);
    expect(paneles.canalesDe("p1").map((c) => c.id)).toEqual(["rpm", "map"]);
    expect(paneles.canalesDe("p2").map((c) => c.id)).toEqual(["tps"]);
    expect(paneles.canalesDe("p3")).toEqual([]);
  });

  it("reparte el alto disponible entre los paneles, descontando los divisores", () => {
    const { documento, contenedor } = montar(600, 800);
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento, alturaMinimaPx: 60 });
    const alturas = paneles.alturasPx();
    const total = [...alturas.values()].reduce((a, b) => a + b, 0);
    // 3 paneles, 2 divisores de 6px: 600 - 12 = 588 disponibles para repartir.
    expect(total).toBe(588);
    for (const valor of alturas.values()) expect(valor).toBeGreaterThanOrEqual(60);
  });

  it("lanza si no hay ninguna definición de panel", () => {
    const { documento, contenedor } = montar();
    expect(() => new PanelesApilados(contenedor, [], { documento })).toThrow();
  });

  it("lanza si hay dos paneles con el mismo id", () => {
    const { documento, contenedor } = montar();
    const conDuplicado: DefinicionPanel[] = [
      { id: "p1", canales: [] },
      { id: "p1", canales: [] },
    ];
    expect(() => new PanelesApilados(contenedor, conDuplicado, { documento })).toThrow();
  });

  it("contenidoDe y canalesDe lanzan para un identificador de panel desconocido", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    expect(() => paneles.contenidoDe("fantasma")).toThrow();
    expect(() => paneles.canalesDe("fantasma")).toThrow();
  });
});

describe("PanelesApilados: eje X compartido", () => {
  it("los N paneles reciben exactamente el mismo ancho de contenido tras construirse", () => {
    const { documento, contenedor } = montar(600, 837);
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    const ancho = paneles.anchoContenidoPx();
    expect(ancho).toBe(837);
    for (const id of paneles.ordenPaneles()) {
      const contenido = comoFalso(paneles.contenidoDe(id));
      expect(contenido.propiedadesDeEstilo.get("width")).toBe(`${ancho}px`);
    }
  });

  it("redimensionar un panel con el divisor NO cambia el ancho compartido de ninguno", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    const divisor = unico(buscar(comoFalso(contenedor), "data-divisor-entre", "p1|p2"));

    disparar(divisor, "pointerdown", { clientY: 100 });
    disparar(divisor, "pointermove", { clientY: 160 });
    disparar(divisor, "pointerup", { clientY: 160 });

    const ancho = paneles.anchoContenidoPx();
    for (const id of paneles.ordenPaneles()) {
      const contenido = comoFalso(paneles.contenidoDe(id));
      expect(contenido.propiedadesDeEstilo.get("width")).toBe(`${ancho}px`);
    }
  });

  it("recalcular tras un cambio de tamaño del contenedor mantiene el ancho igual para todos", () => {
    const { documento, contenedor } = montar(600, 800);
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    comoFalso(contenedor).fijarRectangulo({ top: 0, bottom: 900, left: 0, right: 1200 });
    paneles.redimensionarContenedor();

    expect(paneles.anchoContenidoPx()).toBe(1200);
    for (const id of paneles.ordenPaneles()) {
      const contenido = comoFalso(paneles.contenidoDe(id));
      expect(contenido.propiedadesDeEstilo.get("width")).toBe("1200px");
    }
  });
});

describe("PanelesApilados: redimensionado con el divisor", () => {
  it("arrastrar el divisor entre p1 y p2 solo cambia el alto de esos dos, no el de p3", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    const antes = paneles.alturasPx();

    const divisorP1P2 = unico(buscar(comoFalso(contenedor), "data-divisor-entre", "p1|p2"));
    disparar(divisorP1P2, "pointerdown", { clientY: 0 });
    disparar(divisorP1P2, "pointermove", { clientY: 30 });
    disparar(divisorP1P2, "pointerup", { clientY: 30 });

    const despues = paneles.alturasPx();
    expect(despues.get("p3")).toBe(antes.get("p3"));
    expect(despues.get("p1")).toBe((antes.get("p1") ?? 0) + 30);
    expect(despues.get("p2")).toBe((antes.get("p2") ?? 0) - 30);
  });

  it("un arrastre extremo no baja ningún panel del mínimo configurado", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento, alturaMinimaPx: 60 });
    const divisor = unico(buscar(comoFalso(contenedor), "data-divisor-entre", "p1|p2"));

    disparar(divisor, "pointerdown", { clientY: 0 });
    disparar(divisor, "pointermove", { clientY: -10_000 });
    disparar(divisor, "pointerup", { clientY: -10_000 });

    expect(paneles.alturasPx().get("p1")).toBe(60);
  });

  it("avisa con alRedimensionar en cada cambio de altura, con el mapa completo", () => {
    type AlturasVistas = ReadonlyMap<string, number>;
    const llamadas: AlturasVistas[] = [];
    const { documento, contenedor } = montar();
    new PanelesApilados(contenedor, definiciones(), {
      documento,
      alRedimensionar: (alturas) => llamadas.push(new Map(alturas)),
    });
    expect(llamadas.length).toBeGreaterThan(0);
    expect([...llamadas[0]!.keys()].sort()).toEqual(["p1", "p2", "p3"]);
  });
});

describe("PanelesApilados: arrastrar canales entre paneles", () => {
  it("mueve el canal al panel de destino y avisa con alCambiarAsignacion", () => {
    const cambios: CambioAsignacion[] = [];
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), {
      documento,
      alCambiarAsignacion: (cambio) => cambios.push(cambio),
    });
    prepararRectsDePaneles(comoFalso(contenedor));

    const chipMap = unico(buscar(comoFalso(contenedor), "data-canal-id", "map"));
    disparar(chipMap, "pointerdown", { clientY: 50, pointerId: 7 });
    disparar(chipMap, "pointermove", { clientY: 300, pointerId: 7 }); // dentro del rectángulo de p2
    disparar(chipMap, "pointerup", { clientY: 300, pointerId: 7 });

    expect(paneles.canalesDe("p1").map((c) => c.id)).toEqual(["rpm"]);
    expect(paneles.canalesDe("p2").map((c) => c.id)).toEqual(["tps", "map"]);
    expect(cambios).toEqual([{ canalId: "map", panelOrigen: "p1", panelDestino: "p2", indice: 1 }]);
  });

  it("resalta el panel destino ANTES de soltar, y quita el resalte al soltar", () => {
    const { documento, contenedor } = montar();
    new PanelesApilados(contenedor, definiciones(), { documento });
    prepararRectsDePaneles(comoFalso(contenedor));

    const p2 = unico(buscar(comoFalso(contenedor), "data-panel-id", "p2"));
    const chipMap = unico(buscar(comoFalso(contenedor), "data-canal-id", "map"));

    disparar(chipMap, "pointerdown", { clientY: 50 });
    expect(p2.clases.has("dlv-panel--destino-arrastre")).toBe(false);

    disparar(chipMap, "pointermove", { clientY: 300 });
    expect(p2.clases.has("dlv-panel--destino-arrastre")).toBe(true);

    disparar(chipMap, "pointerup", { clientY: 300 });
    expect(p2.clases.has("dlv-panel--destino-arrastre")).toBe(false);
  });

  it("soltar fuera de cualquier panel cancela el movimiento (no hay destino que confirmar)", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    prepararRectsDePaneles(comoFalso(contenedor));
    const chipMap = unico(buscar(comoFalso(contenedor), "data-canal-id", "map"));

    disparar(chipMap, "pointerdown", { clientY: 50 });
    disparar(chipMap, "pointermove", { clientY: 9_999 }); // fuera de los tres rectángulos (0..600)
    disparar(chipMap, "pointerup", { clientY: 9_999 });

    expect(paneles.canalesDe("p1").map((c) => c.id)).toEqual(["rpm", "map"]);
  });

  it("pointercancel limpia el resalte visual pero NO confirma el movimiento", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    prepararRectsDePaneles(comoFalso(contenedor));
    const p2 = unico(buscar(comoFalso(contenedor), "data-panel-id", "p2"));
    const chipMap = unico(buscar(comoFalso(contenedor), "data-canal-id", "map"));

    disparar(chipMap, "pointerdown", { clientY: 50 });
    disparar(chipMap, "pointermove", { clientY: 300 });
    disparar(chipMap, "pointercancel", { clientY: 300 });

    expect(p2.clases.has("dlv-panel--destino-arrastre")).toBe(false);
    expect(paneles.canalesDe("p1").map((c) => c.id)).toEqual(["rpm", "map"]);
  });

  it("reordenar dentro del mismo panel no cambia el panel del canal", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    prepararRectsDePaneles(comoFalso(contenedor));
    const chipMap = unico(buscar(comoFalso(contenedor), "data-canal-id", "map"));

    // p1 va de 0 a 200: soltar dentro del propio p1 es un arrastre "a sí mismo".
    disparar(chipMap, "pointerdown", { clientY: 50 });
    disparar(chipMap, "pointermove", { clientY: 80 });
    disparar(chipMap, "pointerup", { clientY: 80 });

    expect(paneles.canalesDe("p1").map((c) => c.id).sort()).toEqual(["map", "rpm"]);
  });

  it("moverCanal programático reutiliza el mismo camino que el arrastre", () => {
    const cambios: CambioAsignacion[] = [];
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), {
      documento,
      alCambiarAsignacion: (cambio) => cambios.push(cambio),
    });

    paneles.moverCanal("tps", "p3");

    expect(paneles.canalesDe("p2")).toEqual([]);
    expect(paneles.canalesDe("p3").map((c) => c.id)).toEqual(["tps"]);
    expect(cambios).toEqual([{ canalId: "tps", panelOrigen: "p2", panelDestino: "p3", indice: 0 }]);
  });

  it("moverCanal lanza si el canal no está asignado a ningún panel", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    expect(() => paneles.moverCanal("no-existe", "p1")).toThrow();
  });
});

describe("PanelesApilados: destruir", () => {
  it("no lanza, ni siquiera si se llama dos veces", () => {
    const { documento, contenedor } = montar();
    const paneles = new PanelesApilados(contenedor, definiciones(), { documento });
    expect(() => paneles.destruir()).not.toThrow();
    expect(() => paneles.destruir()).not.toThrow();
  });
});
