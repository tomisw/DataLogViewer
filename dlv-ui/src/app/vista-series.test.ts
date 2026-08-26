/**
 * Pruebas de `crearVistaSeries` (docs/02 §2.10): que la vista de series se comporte
 * bien como `DefinicionVista` -abre el log al montar, aplica un salto
 * pendiente cuando lo hay, y `desmontar()` libera de verdad lo que reservó-
 * sin repetir las pruebas de `Aplicacion` en sí (esas son
 * `app/aplicacion.test.ts`; aquí solo se prueba la costura de adaptación).
 */

import { describe, expect, it, vi } from "vitest";

import { crearDocumentoFalso, crearVentanaFalsa, type ElementoFalso } from "../dom/doble-documento.ts";
import { crearDobleGL } from "../render/doble-gl.ts";
import { Renderizador } from "../render/renderizador.ts";
import type { CubosContinuos } from "../render/tipos.ts";
import type { Rango } from "../datos/cache-cubos.ts";
import type { CanalDeFuente, FuenteDeDatos, LogAbierto, ResumenNivelFuente } from "../datos/fuente.ts";
import type { CatalogoUnidades } from "../unidades/tipos.ts";
import { Aplicacion, type EntornoApp } from "./aplicacion.ts";
import { crearVistaSeries, ID_VISTA_SERIES } from "./vista-series.ts";
import type { ContextoDeVistas } from "./vistas.ts";

const CANALES: CanalDeFuente[] = [
  {
    idNativo: "0",
    nombre: "RPM",
    rol: "engine_speed",
    confianzaRol: "EXACTA",
    dimensionId: "rpm",
    clasificacion: { vacio: false, constante: false },
    aCanonica: { a: 1, b: 0 },
  },
];

const CATALOGO: CatalogoUnidades = {
  dimensiones: [
    {
      id: "rpm",
      etiqueta: "Régimen",
      unidadCanonica: "rpm",
      convertible: false,
      unidades: [{ id: "rpm", etiqueta: "rpm", decimales: 0, conversion: { tipo: "afin", a: 1, b: 0 } }],
    },
  ],
  presets: [{ id: "metrico", etiqueta: "Métrico", unidades: {} }],
  presetPorOmision: "metrico",
  combustibles: [],
};

class FuenteDePrueba implements FuenteDeDatos {
  readonly nombre = "prueba";
  fallarAlAbrir = false;

  abrirLog(referencia: string): Promise<LogAbierto> {
    if (this.fallarAlAbrir) return Promise.reject(new Error("fuente de prueba: fallo forzado"));
    return Promise.resolve({
      logId: "log-1",
      nombre: referencia,
      tInicio: 0,
      tFin: 100,
      canales: CANALES,
      avisos: [],
    });
  }

  cerrarLog(): void {}

  catalogoUnidades(): Promise<CatalogoUnidades> {
    return Promise.resolve(CATALOGO);
  }

  nivelesDe(): Promise<readonly ResumenNivelFuente[]> {
    return Promise.resolve([{ factor: 1, nCubos: 4 }]);
  }

  pedirCubos(_logId: string, _canalId: string, rango: Rango, factor: number): Promise<CubosContinuos> {
    const n = 4;
    const t = new Float32Array(n);
    const v = new Float32Array(n).fill(1000);
    return Promise.resolve({ t, tOrigen: rango.t0, minimo: v, maximo: v, primero: v, ultimo: v, factor });
  }
}

function crearContextoDePrueba(): ContextoDeVistas {
  return { irAVista: vi.fn() };
}

function crearEntorno(): { entorno: EntornoApp; ventana: ReturnType<typeof crearVentanaFalsa> } {
  const documento = crearDocumentoFalso();
  const ventana = crearVentanaFalsa();
  return {
    entorno: {
      documento: documento as unknown as Pick<Document, "createElement" | "createElementNS">,
      ventana,
      crearRenderizador: () => new Renderizador(crearDobleGL()),
    },
    ventana,
  };
}

async function asentar(ventana: ReturnType<typeof crearVentanaFalsa>, vueltas = 8): Promise<void> {
  for (let i = 0; i < vueltas; i += 1) {
    await new Promise((listo) => setTimeout(listo, 0));
    ventana.correrFotogramas(1);
  }
}

describe("crearVistaSeries", () => {
  it("tiene el id ID_VISTA_SERIES y abre el log al montar", async () => {
    const { entorno, ventana } = crearEntorno();
    const fuente = new FuenteDePrueba();
    const definicion = crearVistaSeries(fuente, "mi-log", entorno);
    expect(definicion.id).toBe(ID_VISTA_SERIES);

    const documento = crearDocumentoFalso();
    const contenedor = documento.createElement("div") as unknown as HTMLElement;
    definicion.montar(contenedor, crearContextoDePrueba(), {});
    await asentar(ventana);

    expect((contenedor as unknown as ElementoFalso).textoDelArbol()).toContain("RPM");
  });

  it("con `opciones.instanteS`, llama a Aplicacion.irAInstante en cuanto el log abre", async () => {
    const espia = vi.spyOn(Aplicacion.prototype, "irAInstante");
    try {
      const { entorno, ventana } = crearEntorno();
      const fuente = new FuenteDePrueba();
      const definicion = crearVistaSeries(fuente, "mi-log", entorno);

      const documento = crearDocumentoFalso();
      const contenedor = documento.createElement("div") as unknown as HTMLElement;
      definicion.montar(contenedor, crearContextoDePrueba(), { instanteS: 37 });
      await asentar(ventana);

      expect(espia).toHaveBeenCalledWith(37);
    } finally {
      espia.mockRestore();
    }
  });

  it("sin `instanteS`, NO llama a irAInstante (no inventa un salto)", async () => {
    const espia = vi.spyOn(Aplicacion.prototype, "irAInstante");
    try {
      const { entorno, ventana } = crearEntorno();
      const fuente = new FuenteDePrueba();
      const definicion = crearVistaSeries(fuente, "mi-log", entorno);

      const documento = crearDocumentoFalso();
      const contenedor = documento.createElement("div") as unknown as HTMLElement;
      definicion.montar(contenedor, crearContextoDePrueba(), {});
      await asentar(ventana);

      expect(espia).not.toHaveBeenCalled();
    } finally {
      espia.mockRestore();
    }
  });

  it("un instanteS pendiente NO se aplica si la vista ya se desmontó antes de que abrirLog resolviera", async () => {
    const espia = vi.spyOn(Aplicacion.prototype, "irAInstante");
    try {
      const { entorno, ventana } = crearEntorno();
      const fuente = new FuenteDePrueba();
      const definicion = crearVistaSeries(fuente, "mi-log", entorno);

      const documento = crearDocumentoFalso();
      const contenedor = documento.createElement("div") as unknown as HTMLElement;
      const montada = definicion.montar(contenedor, crearContextoDePrueba(), { instanteS: 37 });
      montada.desmontar(); // antes de que la promesa de abrirLog resuelva
      await asentar(ventana);

      expect(espia).not.toHaveBeenCalled();
    } finally {
      espia.mockRestore();
    }
  });

  it("al fallar abrirLog, escribe el aviso en el CONTENEDOR de la vista (E1.7)", async () => {
    const { entorno, ventana } = crearEntorno();
    const fuente = new FuenteDePrueba();
    fuente.fallarAlAbrir = true;
    const definicion = crearVistaSeries(fuente, "mi-log", entorno);

    const documento = crearDocumentoFalso();
    const contenedor = documento.createElement("div") as unknown as HTMLElement;
    definicion.montar(contenedor, crearContextoDePrueba(), {});
    await asentar(ventana);

    const texto = (contenedor as unknown as ElementoFalso).textoDelArbol();
    expect(texto).toContain("mi-log");
    expect(texto).toContain("fallo forzado");
  });

  it("desmontar() llama a Aplicacion.destruir(): libera los contextos WebGL de sus paneles", async () => {
    const { entorno, ventana } = crearEntorno();
    const fuente = new FuenteDePrueba();
    const definicion = crearVistaSeries(fuente, "mi-log", entorno);

    const documento = crearDocumentoFalso();
    const contenedor = documento.createElement("div") as unknown as HTMLElement;
    const montada = definicion.montar(contenedor, crearContextoDePrueba(), {});
    await asentar(ventana);

    const canvas = (contenedor as unknown as ElementoFalso).buscarPorEtiqueta("canvas");
    expect(canvas).not.toBeNull();
    const gl = canvas!.getContext("webgl2");
    expect(gl?.contextosPerdidos).toBe(0);

    montada.desmontar();

    expect(gl?.contextosPerdidos).toBe(1);
  });
});
