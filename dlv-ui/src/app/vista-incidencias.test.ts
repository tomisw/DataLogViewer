/**
 * Pruebas de `crearVistaIncidencias` (docs/02 §2.10): el cableado que
 * `incidencias/panel-incidencias.ts` pedía desde F3-12 y que nunca se hizo —
 * su cabecera lo decía literalmente: cablear "Saltar" a la navegación real
 * "es tarea de quien monte el panel en `app/aplicacion.ts` — fuera de mi
 * carril". Lo único que se prueba aquí es exactamente eso: que pulsar
 * "Saltar" en una fila llama a `contexto.irAVista(ID_VISTA_SERIES,
 * { instanteS })` con el instante correcto, y que el estado inicial (sin
 * datos de backend) es honesto y no una incidencia inventada.
 *
 * CÓMO SE PRUEBA EL CLIC SIN TENER UNA FILA DE VERDAD
 * ======================================================
 * `crearVistaIncidencias` monta el panel con `DATOS_VACIOS` (no hay
 * `/comandos/incidencias` todavía, ver su cabecera): en producción nunca hay
 * una fila que pulsar. Para probar el cableado de verdad —el closure que
 * `montar()` pasa como `alSaltarAInstante`, no una copia suya— se espía
 * `panel-incidencias.ts#montar` con `vi.spyOn`, se deja que se ejecute de
 * verdad (así el panel se monta igual que en producción) y se captura el
 * `alSaltarAInstante` que de verdad recibió. Llamarlo a mano con un instante
 * de prueba es equivalente a que `PanelDeIncidencias` lo hubiera llamado al
 * pulsar "Saltar" -esa ruta interna ya la prueba
 * `incidencias/panel-incidencias.test.ts`- y evita inventar una incidencia
 * falsa solo para tener algo que pulsar.
 */

import { describe, expect, it, vi } from "vitest";

import { crearDocumentoFalso, type ElementoFalso } from "../dom/doble-documento.ts";
import * as panelIncidencias from "../incidencias/panel-incidencias.ts";
import type { ContextoDeVistas } from "./vistas.ts";
import { crearVistaIncidencias, ID_VISTA_INCIDENCIAS } from "./vista-incidencias.ts";
import { ID_VISTA_SERIES } from "./vista-series.ts";

function crearContenedor(): { documentoPick: Pick<Document, "createElement">; contenedor: HTMLElement } {
  const documento = crearDocumentoFalso();
  const contenedor = documento.createElement("div") as unknown as HTMLElement;
  return { documentoPick: documento as unknown as Pick<Document, "createElement">, contenedor };
}

describe("crearVistaIncidencias", () => {
  it("tiene el id ID_VISTA_INCIDENCIAS", () => {
    const { documentoPick } = crearContenedor();
    const definicion = crearVistaIncidencias(documentoPick);
    expect(definicion.id).toBe(ID_VISTA_INCIDENCIAS);
  });

  it("se monta con datos vacíos: dice 'sin incidencias', no inventa ninguna", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaIncidencias(documentoPick);
    definicion.montar(contenedor, { irAVista: vi.fn() }, {});

    const texto = (contenedor as unknown as ElementoFalso).textoDelArbol();
    expect(texto).toMatch(/sin incidencias/i);
  });

  it("sin incidencias no hay ningún botón 'Saltar' (nada que pulsar)", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaIncidencias(documentoPick);
    definicion.montar(contenedor, { irAVista: vi.fn() }, {});

    const botones = (contenedor as unknown as ElementoFalso).buscarTodosPorClase(
      "panel-incidencias__salto",
    );
    expect(botones).toHaveLength(0);
  });

  it("el alSaltarAInstante de verdad llama a irAVista(ID_VISTA_SERIES, {instanteS})", () => {
    const espia = vi.spyOn(panelIncidencias, "montar");
    try {
      const { documentoPick, contenedor } = crearContenedor();
      const irAVista = vi.fn();
      const contexto: ContextoDeVistas = { irAVista };
      const definicion = crearVistaIncidencias(documentoPick);

      definicion.montar(contenedor, contexto, {});

      expect(espia).toHaveBeenCalledTimes(1);
      const opciones = espia.mock.calls[0]![1];
      expect(opciones?.alSaltarAInstante).toBeDefined();

      opciones!.alSaltarAInstante!(12.345);

      expect(irAVista).toHaveBeenCalledWith(ID_VISTA_SERIES, { instanteS: 12.345 });
      expect(ID_VISTA_SERIES).toBe("series"); // documenta el id real que usa el cableado
    } finally {
      espia.mockRestore();
    }
  });

  it("desmontar() no revienta (vista puramente DOM, sin WebGL ni temporizadores)", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaIncidencias(documentoPick);
    const montada = definicion.montar(contenedor, { irAVista: vi.fn() }, {});
    expect(() => montada.desmontar()).not.toThrow();
  });
});
