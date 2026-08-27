/**
 * Pruebas de `crearVistaImportacion` (docs/02 §2.10): el cableado que
 * `importacion/asistente-importacion.ts` pedía y que ningún `app/` montaba
 * todavía. No repite las pruebas de `AsistenteImportacion` en sí (no hay
 * `.test.ts` para ese fichero: su propia cabecera explica que hace falta un
 * navegador de verdad, mismo motivo que `selector-canales.ts` y `main.ts`) ni
 * las de `celdas.ts`/`deduccion.ts`/`tiempo.ts` (ya cubiertas en
 * `importacion/*.test.ts`). Lo que se prueba aquí es la COSTURA: qué pantalla
 * se ve al montar, que pulsar "Sondear" lleva de verdad al asistente real
 * (con `PuertoImportacionApi`, no un doble), que el fallo real de ese puerto
 * -sin endpoint en `dlv-api`- se ve en pantalla con el endpoint que falta, y
 * que `desmontar()` no revienta ni deja nada colgado tras un ciclo de montaje.
 */

import { describe, expect, it, vi } from "vitest";

import { crearDocumentoFalso, type ElementoFalso } from "../dom/doble-documento.ts";
import type {
  CanalDeFuente,
  FuenteDeDatos,
  LogAbierto,
  ResumenNivelFuente,
} from "../datos/fuente.ts";
import type { Rango } from "../datos/cache-cubos.ts";
import type { CubosContinuos } from "../render/tipos.ts";
import type { CatalogoUnidades } from "../unidades/tipos.ts";
import { crearVistaImportacion, ID_VISTA_IMPORTACION } from "./vista-importacion.ts";

const CATALOGO: CatalogoUnidades = {
  dimensiones: [],
  presets: [{ id: "metrico", etiqueta: "Métrico", unidades: {} }],
  presetPorOmision: "metrico",
  combustibles: [],
};

/** Fuente mínima: solo `catalogoUnidades` importa a esta vista; el resto no se usa. */
class FuenteDePrueba implements FuenteDeDatos {
  readonly nombre = "prueba";
  #resolverCatalogo: (() => void) | null = null;
  #promesaCatalogo: Promise<CatalogoUnidades> | null = null;

  /** Deja la promesa de `catalogoUnidades` pendiente hasta que se llame a `resolver()`. */
  controlarCatalogo(): void {
    this.#promesaCatalogo = new Promise<CatalogoUnidades>((resolver) => {
      this.#resolverCatalogo = () => resolver(CATALOGO);
    });
  }

  resolverCatalogoPendiente(): void {
    this.#resolverCatalogo?.();
  }

  catalogoUnidades(): Promise<CatalogoUnidades> {
    return this.#promesaCatalogo ?? Promise.resolve(CATALOGO);
  }

  abrirLog(referencia: string): Promise<LogAbierto> {
    return Promise.resolve({
      logId: "log-1",
      nombre: referencia,
      tInicio: 0,
      tFin: 1,
      canales: [] as CanalDeFuente[],
      avisos: [],
    });
  }

  cerrarLog(): void {}

  nivelesDe(): Promise<readonly ResumenNivelFuente[]> {
    return Promise.resolve([]);
  }

  pedirCubos(_logId: string, _canalId: string, rango: Rango, factor: number): Promise<CubosContinuos> {
    const n = new Float32Array(0);
    return Promise.resolve({ t: n, tOrigen: rango.t0, minimo: n, maximo: n, primero: n, ultimo: n, factor });
  }
}

function crearContenedor(): { documentoPick: Pick<Document, "createElement" | "createTextNode">; contenedor: HTMLElement } {
  const documento = crearDocumentoFalso();
  const contenedor = documento.createElement("div") as unknown as HTMLElement;
  return {
    documentoPick: documento as unknown as Pick<Document, "createElement" | "createTextNode">,
    contenedor,
  };
}

/** Varias vueltas de microtareas: suficiente para que las dos promesas encadenadas
 * (catalogoUnidades -> sondearFormato) terminen de resolver/rechazar. */
async function asentar(vueltas = 6): Promise<void> {
  for (let i = 0; i < vueltas; i += 1) {
    await Promise.resolve();
  }
}

function escribirYSondear(contenedor: HTMLElement, referencia: string): void {
  const el = contenedor as unknown as ElementoFalso;
  const input = el.buscarPorEtiqueta("input");
  expect(input).not.toBeNull();
  input!.value = referencia;
  const boton = el.buscarPorEtiqueta("button");
  expect(boton).not.toBeNull();
  boton!.disparar("click");
}

describe("crearVistaImportacion", () => {
  it("tiene el id ID_VISTA_IMPORTACION", () => {
    const { documentoPick } = crearContenedor();
    const definicion = crearVistaImportacion(new FuenteDePrueba(), documentoPick);
    expect(definicion.id).toBe(ID_VISTA_IMPORTACION);
  });

  it("al montar, enseña el selector de fichero y avisa YA de que dlv-api no sondea CSV genérico", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaImportacion(new FuenteDePrueba(), documentoPick);
    definicion.montar(contenedor, { irAVista: vi.fn() }, {});

    const texto = (contenedor as unknown as ElementoFalso).textoDelArbol();
    expect(texto).toMatch(/no expone el sondeo de csv gen/i);
    expect(texto).toMatch(/nada se importa todavía de verdad/i);
    expect((contenedor as unknown as ElementoFalso).buscarPorEtiqueta("input")).not.toBeNull();
  });

  it("pulsar «Sondear» con el campo vacío no hace nada: sigue en el selector", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaImportacion(new FuenteDePrueba(), documentoPick);
    definicion.montar(contenedor, { irAVista: vi.fn() }, {});

    const boton = (contenedor as unknown as ElementoFalso).buscarPorEtiqueta("button");
    boton!.disparar("click");

    expect((contenedor as unknown as ElementoFalso).buscarPorEtiqueta("input")).not.toBeNull();
  });

  it(
    "pulsar «Sondear» monta el asistente REAL (PuertoImportacionApi) y su fallo real " +
      "-sin endpoint en dlv-api- se ve en pantalla, con el endpoint que falta nombrado",
    async () => {
      const { documentoPick, contenedor } = crearContenedor();
      const definicion = crearVistaImportacion(new FuenteDePrueba(), documentoPick);
      definicion.montar(contenedor, { irAVista: vi.fn() }, {});

      escribirYSondear(contenedor, "C:\\logs\\prueba.csv");
      await asentar();

      const texto = (contenedor as unknown as ElementoFalso).textoDelArbol();
      // Mensaje literal de PuertoImportacionSinImplementar (puerto.ts): nombra
      // el endpoint que falta cablear en dlv_api.main.crear_app.
      expect(texto).toMatch(/dlv-api todavía no tiene/i);
      expect(texto).toContain("dlv_core.formatos.sondeo.sondear_csv");
    },
  );

  it("tras el fallo del asistente, «Cerrar» vuelve al selector de fichero", async () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaImportacion(new FuenteDePrueba(), documentoPick);
    definicion.montar(contenedor, { irAVista: vi.fn() }, {});

    escribirYSondear(contenedor, "C:\\logs\\prueba.csv");
    await asentar();

    // El botón "Cerrar" es el único botón del pie de un asistente en estado de error.
    const el = contenedor as unknown as ElementoFalso;
    const botonCerrar = el.buscarPorEtiqueta("button");
    expect(botonCerrar).not.toBeNull();
    botonCerrar!.disparar("click");

    expect((contenedor as unknown as ElementoFalso).buscarPorEtiqueta("input")).not.toBeNull();
  });

  it("desmontar() no revienta con el selector inicial (sin timers ni oyentes en window/document)", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaImportacion(new FuenteDePrueba(), documentoPick);
    const montada = definicion.montar(contenedor, { irAVista: vi.fn() }, {});
    expect(() => montada.desmontar()).not.toThrow();
  });

  it(
    "desmontar() ANTES de que catalogoUnidades resuelva evita construir el asistente " +
      "sobre un contenedor ya abandonado (mismo patrón que vista-series.ts)",
    async () => {
      const fuente = new FuenteDePrueba();
      fuente.controlarCatalogo();
      const { documentoPick, contenedor } = crearContenedor();
      const definicion = crearVistaImportacion(fuente, documentoPick);
      const montada = definicion.montar(contenedor, { irAVista: vi.fn() }, {});

      escribirYSondear(contenedor, "C:\\logs\\prueba.csv");
      expect(() => montada.desmontar()).not.toThrow();

      fuente.resolverCatalogoPendiente();
      await asentar();

      // No debe haber reconstruido nada sobre el contenedor tras el desmontaje:
      // ni el selector, ni el asistente, ni su aviso de error.
      const texto = (contenedor as unknown as ElementoFalso).textoDelArbol();
      expect(texto).not.toMatch(/dlv-api todavía no tiene/i);
    },
  );

  it("desmontar() con el asistente ya montado no revienta", async () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaImportacion(new FuenteDePrueba(), documentoPick);
    const montada = definicion.montar(contenedor, { irAVista: vi.fn() }, {});

    escribirYSondear(contenedor, "C:\\logs\\prueba.csv");
    await asentar();

    expect(() => montada.desmontar()).not.toThrow();
  });
});
