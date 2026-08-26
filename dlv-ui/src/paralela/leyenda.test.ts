/**
 * Pruebas de `LeyendaSegmentos`, con el doble de `cursor/doble-dom.ts`
 * reutilizado tal cual (ver la cabecera de `leyenda.ts`: no hace falta un
 * doble nuevo porque la superficie de DOM que usa este componente es
 * idéntica a la que ya usa `CursorDeTabla`).
 *
 * El doble no expone su árbol por una interfaz pública (solo cuenta nodos y
 * escrituras, ver su cabecera), pero sus nodos SÍ guardan `hijos`,
 * `textContent` y `propiedadesDeEstilo` como campos accesibles en tiempo de
 * ejecución. Se accede a ellos con un `as unknown as NodoFalso` local en vez
 * de ampliar el doble: es la misma información que ya expone, solo que sin
 * tipar formalmente el árbol interno (que `doble-dom.ts` no exporta a
 * propósito, ver su cabecera).
 */

import { describe, expect, it } from "vitest";

import { crearDobleDOM } from "../cursor/doble-dom.ts";
import { colorACss } from "../carriles/color.ts";
import { colorDeSegmento } from "./vista-paralela.ts";
import { LeyendaSegmentos } from "./leyenda.ts";

interface NodoFalso {
  readonly hijos: readonly NodoFalso[];
  readonly textContent: string;
  readonly className: string;
  readonly propiedadesDeEstilo: ReadonlyMap<string, string>;
}

function comoFalso(nodo: unknown): NodoFalso {
  return nodo as unknown as NodoFalso;
}

describe("LeyendaSegmentos", () => {
  it("crea una fila por segmento con su etiqueta y el color de colorDeSegmento", () => {
    const doble = crearDobleDOM();
    const contenedor = doble.documento.createElement("div");
    const leyenda = new LeyendaSegmentos(contenedor, doble.documento);

    leyenda.actualizar([
      { idSegmento: "A", etiqueta: "Tirada A" },
      { idSegmento: "B", etiqueta: "Tirada B" },
    ]);

    const lista = comoFalso(comoFalso(contenedor).hijos[0]);
    expect(lista.className).toBe("leyenda-paralela");
    expect(lista.hijos.length).toBe(2);

    const [filaA, filaB] = lista.hijos.map(comoFalso);
    expect(filaA!.className).toBe("leyenda-paralela-item");

    const muestraA = comoFalso(filaA!.hijos[0]);
    const etiquetaA = comoFalso(filaA!.hijos[1]);
    expect(muestraA.className).toBe("leyenda-paralela-muestra");
    expect(muestraA.propiedadesDeEstilo.get("background-color")).toBe(
      colorACss(colorDeSegmento("A")),
    );
    expect(etiquetaA.className).toBe("leyenda-paralela-etiqueta");
    expect(etiquetaA.textContent).toBe("Tirada A");

    const muestraB = comoFalso(filaB!.hijos[0]);
    const etiquetaB = comoFalso(filaB!.hijos[1]);
    expect(muestraB.propiedadesDeEstilo.get("background-color")).toBe(
      colorACss(colorDeSegmento("B")),
    );
    expect(etiquetaB.textContent).toBe("Tirada B");
    // Dos logs distintos, dos colores distintos en la muestra (decisión 1).
    expect(muestraA.propiedadesDeEstilo.get("background-color")).not.toBe(
      muestraB.propiedadesDeEstilo.get("background-color"),
    );
  });

  it("actualizar() reconstruye por completo: menos entradas no deja restos de las anteriores", () => {
    const doble = crearDobleDOM();
    const contenedor = doble.documento.createElement("div");
    const leyenda = new LeyendaSegmentos(contenedor, doble.documento);

    leyenda.actualizar([
      { idSegmento: "A", etiqueta: "Tirada A" },
      { idSegmento: "B", etiqueta: "Tirada B" },
      { idSegmento: "C", etiqueta: "Tirada C" },
    ]);
    leyenda.actualizar([{ idSegmento: "A", etiqueta: "Tirada A" }]);

    const lista = comoFalso(comoFalso(contenedor).hijos[0]);
    expect(lista.hijos.length).toBe(1);
    expect(comoFalso(comoFalso(lista.hijos[0]).hijos[1]).textContent).toBe("Tirada A");
  });

  it("una lista vacía de segmentos deja la leyenda vacía, no con la última composición", () => {
    const doble = crearDobleDOM();
    const contenedor = doble.documento.createElement("div");
    const leyenda = new LeyendaSegmentos(contenedor, doble.documento);

    leyenda.actualizar([{ idSegmento: "A", etiqueta: "Tirada A" }]);
    leyenda.actualizar([]);

    const lista = comoFalso(comoFalso(contenedor).hijos[0]);
    expect(lista.hijos.length).toBe(0);
  });

  it("destruir() quita la leyenda de su contenedor", () => {
    const doble = crearDobleDOM();
    const contenedor = doble.documento.createElement("div");
    const leyenda = new LeyendaSegmentos(contenedor, doble.documento);

    expect(comoFalso(contenedor).hijos.length).toBe(1); // el <ul> que crea el constructor
    leyenda.destruir();
    expect(comoFalso(contenedor).hijos.length).toBe(0);
  });
});
