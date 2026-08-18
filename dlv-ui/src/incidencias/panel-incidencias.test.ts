/**
 * Pruebas de cableado de `panel-incidencias.ts`, con el doble de
 * `contexto-dom.ts` (`doble-dom.ts`). Lo que se prueba aquí es lo que un
 * doble puede decir de verdad: qué nodos se crean, qué texto llevan, y qué
 * instante llega a `alSaltarAInstante` al simular un clic — NO si la fila se
 * ve distinguible (eso es un juicio visual, fuera de una prueba unitaria,
 * misma nota que `cursor/doble-dom.ts`).
 */

import { describe, expect, it } from "vitest";

import { crearContextoDomFalso, ElementoFalso } from "./doble-dom.ts";
import { PanelDeIncidencias } from "./panel-incidencias.ts";
import type { DetectorCatalogo, EstadoDetector, IncidenciaPanel } from "./tipos.ts";

function incidencia(parcial: Partial<IncidenciaPanel> & Pick<IncidenciaPanel, "id">): IncidenciaPanel {
  return {
    detectorId: "D1",
    severidad: "media",
    tInicioMs: 0,
    tFinMs: null,
    detalle: {},
    ...parcial,
  };
}

const CATALOGO: readonly DetectorCatalogo[] = [
  { id: "D4", etiqueta: "Mezcla pobre en carga", severidad: "critica" },
  { id: "D9", etiqueta: "Sobretemperatura de refrigerante", severidad: "alta" },
];

/** Recoge todos los descendientes (incluido el propio nodo) con una clase. */
function buscarPorClase(raiz: ElementoFalso, clase: string): ElementoFalso[] {
  const encontrados: ElementoFalso[] = [];
  if (raiz.clases.has(clase)) encontrados.push(raiz);
  for (const hijo of raiz.hijos) encontrados.push(...buscarPorClase(hijo, clase));
  return encontrados;
}

function montarPanel(): { contenedor: ElementoFalso; panel: PanelDeIncidencias; saltos: number[] } {
  const contenedor = new ElementoFalso("div");
  const saltos: number[] = [];
  const panel = new PanelDeIncidencias(contenedor, {
    documento: crearContextoDomFalso(),
    alSaltarAInstante: (instanteS) => saltos.push(instanteS),
  });
  return { contenedor, panel, saltos };
}

describe("PanelDeIncidencias: banner de detectores desactivados", () => {
  it("no aparece cuando todos los detectores están activos", () => {
    const { contenedor, panel } = montarPanel();
    panel.actualizar({ catalogo: CATALOGO, estados: [], incidencias: [] });
    expect(buscarPorClase(contenedor, "panel-incidencias__banner")).toHaveLength(0);
  });

  it("aparece con el motivo cuando un detector crítico está desactivado, aunque no haya incidencias", () => {
    const estados: readonly EstadoDetector[] = [
      { detectorId: "D4", activo: false, motivo: "rol lambda_measured sin confirmar (asignación difusa)" },
    ];
    const { contenedor, panel } = montarPanel();
    panel.actualizar({ catalogo: CATALOGO, estados, incidencias: [] });

    const banners = buscarPorClase(contenedor, "panel-incidencias__banner");
    expect(banners).toHaveLength(1);
    const lineas = buscarPorClase(contenedor, "panel-incidencias__banner-linea");
    expect(lineas).toHaveLength(1);
    expect(lineas[0]?.textContent).toContain("Mezcla pobre en carga");
    expect(lineas[0]?.textContent).toContain("asignación difusa sin confirmar");
  });

  it("un detector desactivado NO se pinta como la lista vacía de \"sin incidencias\"", () => {
    const estados: readonly EstadoDetector[] = [{ detectorId: "D4", activo: false, motivo: "motivo" }];
    const { contenedor, panel } = montarPanel();
    panel.actualizar({ catalogo: CATALOGO, estados, incidencias: [] });

    // Hay banner (desactivado) Y la lista, aparte, sigue diciendo que no hay
    // incidencias en los ACTIVOS -- son dos afirmaciones distintas y las dos
    // tienen que estar.
    expect(buscarPorClase(contenedor, "panel-incidencias__banner")).toHaveLength(1);
    expect(buscarPorClase(contenedor, "panel-incidencias__vacio")).toHaveLength(1);
  });
});

describe("PanelDeIncidencias: lista ordenada por consecuencia", () => {
  it("pinta las filas en orden de severidad, no de llegada", () => {
    const incidencias = [
      incidencia({ id: "tarde-informativa", detectorId: "D9", severidad: "informativa", tInicioMs: 200_000 }),
      incidencia({ id: "temprana-critica", detectorId: "D4", severidad: "critica", tInicioMs: 0 }),
    ];
    const { contenedor, panel } = montarPanel();
    panel.actualizar({ catalogo: CATALOGO, estados: [], incidencias });

    const filas = buscarPorClase(contenedor, "panel-incidencias__fila");
    expect(filas).toHaveLength(2);
    expect(filas[0]?.textContent).toContain("Mezcla pobre en carga");
    expect(filas[1]?.textContent).toContain("Sobretemperatura de refrigerante");
  });

  it("sin incidencias y sin desactivados, dice explícitamente que no hay ninguna", () => {
    const { contenedor, panel } = montarPanel();
    panel.actualizar({ catalogo: CATALOGO, estados: [], incidencias: [] });

    const vacios = buscarPorClase(contenedor, "panel-incidencias__vacio");
    expect(vacios).toHaveLength(1);
    expect(vacios[0]?.textContent).toMatch(/sin incidencias/i);
  });

  it("pulsar \"Saltar\" llama a alSaltarAInstante con el instante de INICIO, en segundos", () => {
    const incidencias = [incidencia({ id: "a", detectorId: "D4", severidad: "critica", tInicioMs: 12_345 })];
    const { contenedor, saltos, panel } = montarPanel();
    panel.actualizar({ catalogo: CATALOGO, estados: [], incidencias });

    const botones = buscarPorClase(contenedor, "panel-incidencias__salto");
    expect(botones).toHaveLength(1);
    botones[0]?.clic();

    expect(saltos).toEqual([12.345]);
  });

  it("una incidencia de un detector no listado en el catálogo usa su id como etiqueta, no revienta", () => {
    const incidencias = [incidencia({ id: "a", detectorId: "D999", severidad: "media" })];
    const { contenedor, panel } = montarPanel();
    expect(() => panel.actualizar({ catalogo: CATALOGO, estados: [], incidencias })).not.toThrow();

    const filas = buscarPorClase(contenedor, "panel-incidencias__fila");
    expect(filas[0]?.textContent).toContain("D999");
  });

  it("actualizar dos veces reemplaza el contenido en vez de acumularlo", () => {
    const { contenedor, panel } = montarPanel();
    panel.actualizar({
      catalogo: CATALOGO,
      estados: [],
      incidencias: [incidencia({ id: "a", detectorId: "D4", severidad: "critica" })],
    });
    panel.actualizar({ catalogo: CATALOGO, estados: [], incidencias: [] });

    expect(buscarPorClase(contenedor, "panel-incidencias__fila")).toHaveLength(0);
    expect(buscarPorClase(contenedor, "panel-incidencias__vacio")).toHaveLength(1);
  });
});

describe("PanelDeIncidencias: resumen", () => {
  it("cuenta las incidencias por severidad en el texto del resumen", () => {
    const incidencias = [
      incidencia({ id: "a", detectorId: "D4", severidad: "critica" }),
      incidencia({ id: "b", detectorId: "D4", severidad: "critica" }),
      incidencia({ id: "c", detectorId: "D9", severidad: "alta" }),
    ];
    const { contenedor, panel } = montarPanel();
    panel.actualizar({ catalogo: CATALOGO, estados: [], incidencias });

    const resumen = buscarPorClase(contenedor, "panel-incidencias__resumen");
    expect(resumen).toHaveLength(1);
    expect(resumen[0]?.textContent).toContain("2 critica");
    expect(resumen[0]?.textContent).toContain("1 alta");
    // Las severidades sin incidencias no aparecen en el resumen: cinco
    // números vacíos no ayudan a leer "¿ha ido todo bien?" en 5 segundos.
    expect(resumen[0]?.textContent).not.toContain("informativa");
  });
});
