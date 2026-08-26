/**
 * Pruebas de `ConmutadorDeVistas` (docs/02 §2.10): el ciclo montar/desmontar/volver a
 * montar tiene que ser estable -docs/02 §2.10- y eso significa, en concreto,
 * dos cosas que se prueban aquí con dobles y no con GPU:
 *
 * 1. Nunca hay dos vistas montadas a la vez: `irAVista` desmonta la activa
 *    ANTES de montar la nueva.
 * 2. Repetir el ciclo muchas veces no acumula contextos WebGL vivos: cada
 *    vista saliente pierde el suyo (una vez, ni cero ni dos) y cada vista
 *    entrante trae uno nuevo -nunca reutiliza el de una vista anterior.
 *
 * Las vistas de aquí son dobles deliberadamente tontos (una con "GPU" de
 * mentira vía `render/doble-gl.ts`, otra sin nada), no `Aplicacion` ni
 * `PanelDeIncidencias`: lo que se prueba es el CONMUTADOR, no lo que
 * conmuta. `vista-series.test.ts` y `vista-incidencias.test.ts` prueban las
 * vistas de verdad por separado.
 */

import { describe, expect, it } from "vitest";

import { crearDocumentoFalso, type ElementoFalso } from "../dom/doble-documento.ts";
import type { DobleGL } from "../render/doble-gl.ts";
import { ConmutadorDeVistas, type DefinicionVista, type OpcionesActivacion } from "./vistas.ts";

/**
 * Una vista con un `<canvas>` y un contexto WebGL2 de mentira, igual que hace
 * `app/aplicacion.ts` para cada panel. `desmontar()` reproduce EXACTAMENTE su
 * línea de liberación (`getContext(...)?.getExtension(...)?.loseContext()`)
 * para que esta prueba viva o muera con el mismo patrón que el código real.
 */
function crearVistaConGL(
  id: string,
  documento: Pick<Document, "createElement">,
): { definicion: DefinicionVista; contextos: DobleGL[]; opcionesRecibidas: OpcionesActivacion[] } {
  const contextos: DobleGL[] = [];
  const opcionesRecibidas: OpcionesActivacion[] = [];
  const definicion: DefinicionVista = {
    id,
    etiqueta: `Vista ${id}`,
    montar(contenedor, _contexto, opciones) {
      opcionesRecibidas.push(opciones);
      const canvas = documento.createElement("canvas") as unknown as ElementoFalso;
      (contenedor as unknown as ElementoFalso).appendChild(canvas);
      const gl = canvas.getContext("webgl2") as DobleGL;
      contextos.push(gl);
      return {
        desmontar(): void {
          canvas.getContext("webgl2")?.getExtension("WEBGL_lose_context")?.loseContext();
        },
      };
    },
  };
  return { definicion, contextos, opcionesRecibidas };
}

/** Una vista sin GPU ni temporizadores: solo cuenta cuántas veces se montó/desmontó. */
function crearVistaSimple(
  id: string,
): { definicion: DefinicionVista; contador: { montajes: number; desmontajes: number } } {
  const contador = { montajes: 0, desmontajes: 0 };
  const definicion: DefinicionVista = {
    id,
    etiqueta: `Vista ${id}`,
    montar() {
      contador.montajes += 1;
      return {
        desmontar(): void {
          contador.desmontajes += 1;
        },
      };
    },
  };
  return { definicion, contador };
}

describe("ConmutadorDeVistas: construcción", () => {
  it("monta la PRIMERA vista de la lista sin que nadie tenga que pedirlo", () => {
    const documento = crearDocumentoFalso();
    const raiz = documento.createElement("div") as unknown as HTMLElement;
    const documentoPick = documento as unknown as Pick<Document, "createElement">;
    const { definicion, contextos } = crearVistaConGL("series", documentoPick);
    new ConmutadorDeVistas(raiz, documentoPick, [definicion]);
    expect(contextos).toHaveLength(1);
  });

  it("rechaza una lista de vistas vacía", () => {
    const documento = crearDocumentoFalso();
    const raiz = documento.createElement("div") as unknown as HTMLElement;
    expect(
      () => new ConmutadorDeVistas(raiz, documento as unknown as Pick<Document, "createElement">, []),
    ).toThrow();
  });
});

describe("ConmutadorDeVistas: nunca hay dos vistas vivas a la vez", () => {
  it("conmutar desmonta la activa ANTES de montar la nueva", () => {
    const documento = crearDocumentoFalso();
    const raiz = documento.createElement("div") as unknown as HTMLElement;
    const orden: string[] = [];
    const a: DefinicionVista = {
      id: "a",
      etiqueta: "A",
      montar: () => ({ desmontar: () => orden.push("desmontar-a") }),
    };
    const b: DefinicionVista = {
      id: "b",
      etiqueta: "B",
      montar: () => {
        orden.push("montar-b");
        return { desmontar: () => orden.push("desmontar-b") };
      },
    };
    orden.push("montar-a"); // el constructor monta "a" (primera de la lista); se anota a mano porque el `montar` de "a" no lo hace
    const conmutador = new ConmutadorDeVistas(raiz, documento as unknown as Pick<Document, "createElement">, [
      a,
      b,
    ]);
    conmutador.irAVista("b");
    expect(orden).toEqual(["montar-a", "desmontar-a", "montar-b"]);
  });

  it("un ciclo de montar/desmontar/volver a montar repetido no acumula contextos WebGL", () => {
    const documento = crearDocumentoFalso();
    const raiz = documento.createElement("div") as unknown as HTMLElement;
    const documentoPick = documento as unknown as Pick<Document, "createElement">;
    const serie = crearVistaConGL("series", documentoPick);
    const otra = crearVistaConGL("otra", documentoPick);
    const conmutador = new ConmutadorDeVistas(raiz, documentoPick, [serie.definicion, otra.definicion]);

    for (let i = 0; i < 6; i += 1) {
      conmutador.irAVista("otra");
      conmutador.irAVista("series");
    }

    // Un contexto por cada montaje de "series": el primero del constructor
    // más seis del bucle.
    expect(serie.contextos).toHaveLength(7);
    // TODOS menos el último (el vigente) tienen que estar perdidos EXACTAMENTE
    // una vez: ni sin perder (fuga) ni perdidos dos veces (doble liberación).
    for (const gl of serie.contextos.slice(0, -1)) {
      expect(gl.contextosPerdidos).toBe(1);
    }
    expect(serie.contextos.at(-1)!.contextosPerdidos).toBe(0);

    // Misma cuenta para "otra": seis montajes, los cinco primeros perdidos,
    // el último vigente en el momento del último cambio (ver la nota abajo).
    // El bucle termina en "series", así que el último `otra` también está
    // desmontado y perdido.
    expect(otra.contextos).toHaveLength(6);
    for (const gl of otra.contextos) {
      expect(gl.contextosPerdidos).toBe(1);
    }
  });

  it("cada conmutación descarta el <div> de la vista saliente: el contenido nunca acumula nodos", () => {
    const documento = crearDocumentoFalso();
    const raiz = documento.createElement("div") as unknown as HTMLElement;
    const documentoPick = documento as unknown as Pick<Document, "createElement">;
    const serie = crearVistaConGL("series", documentoPick);
    const otra = crearVistaConGL("otra", documentoPick);
    const conmutador = new ConmutadorDeVistas(raiz, documentoPick, [serie.definicion, otra.definicion]);

    for (let i = 0; i < 4; i += 1) conmutador.irAVista(i % 2 === 0 ? "otra" : "series");

    const contenido = (raiz as unknown as ElementoFalso).buscarPorClase("dlv-vistas__contenido")!;
    // Un único hijo -el `<div>` de la vista activa AHORA MISMO-, no uno por
    // cada conmutación pasada.
    expect(contenido.hijos).toHaveLength(1);
  });
});

describe("ConmutadorDeVistas: la barra de pestañas", () => {
  it("pulsar la pestaña de otra vista conmuta; pulsar la ya activa no remonta", () => {
    const documento = crearDocumentoFalso();
    const raiz = documento.createElement("div") as unknown as HTMLElement;
    const documentoPick = documento as unknown as Pick<Document, "createElement">;
    const a = crearVistaSimple("a");
    const b = crearVistaSimple("b");
    new ConmutadorDeVistas(raiz, documentoPick, [a.definicion, b.definicion]);
    expect(a.contador.montajes).toBe(1);

    const botones = (raiz as unknown as ElementoFalso).buscarTodosPorClase("dlv-vistas__boton");
    expect(botones).toHaveLength(2);
    const botonB = botones.find((btn) => btn.textContent === "Vista b")!;
    botonB.disparar("click");
    expect(b.contador.montajes).toBe(1);
    expect(a.contador.desmontajes).toBe(1);

    // Pulsar la pestaña de "b" otra vez, ya activa: no la vuelve a montar.
    botonB.disparar("click");
    expect(b.contador.montajes).toBe(1);
  });
});

describe("ConmutadorDeVistas: opciones de activación", () => {
  it("irAVista propaga `opciones` a `montar`, incluido un `instanteS`", () => {
    const documento = crearDocumentoFalso();
    const raiz = documento.createElement("div") as unknown as HTMLElement;
    const documentoPick = documento as unknown as Pick<Document, "createElement">;
    const serie = crearVistaConGL("series", documentoPick);
    const otra = crearVistaConGL("otra", documentoPick);
    const conmutador = new ConmutadorDeVistas(raiz, documentoPick, [serie.definicion, otra.definicion]);

    conmutador.irAVista("otra");
    conmutador.irAVista("series", { instanteS: 42 });

    expect(serie.opcionesRecibidas.at(-1)).toEqual({ instanteS: 42 });
  });

  it("re-activar la MISMA vista con un `instanteS` nuevo SÍ remonta (no es un no-op)", () => {
    const documento = crearDocumentoFalso();
    const raiz = documento.createElement("div") as unknown as HTMLElement;
    const documentoPick = documento as unknown as Pick<Document, "createElement">;
    const serie = crearVistaConGL("series", documentoPick);
    const conmutador = new ConmutadorDeVistas(raiz, documentoPick, [serie.definicion]);

    conmutador.irAVista("series", { instanteS: 10 });

    expect(serie.contextos).toHaveLength(2);
    expect(serie.contextos[0]!.contextosPerdidos).toBe(1);
    expect(serie.opcionesRecibidas).toEqual([{}, { instanteS: 10 }]);
  });
});

describe("ConmutadorDeVistas: destruir", () => {
  it("desmonta la vista activa", () => {
    const documento = crearDocumentoFalso();
    const raiz = documento.createElement("div") as unknown as HTMLElement;
    const documentoPick = documento as unknown as Pick<Document, "createElement">;
    const serie = crearVistaConGL("series", documentoPick);
    const conmutador = new ConmutadorDeVistas(raiz, documentoPick, [serie.definicion]);

    conmutador.destruir();

    expect(serie.contextos[0]!.contextosPerdidos).toBe(1);
  });
});
