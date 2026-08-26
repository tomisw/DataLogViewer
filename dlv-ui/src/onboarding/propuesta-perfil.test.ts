/**
 * Pruebas de `PropuestaPerfil`, con el doble de `dom/doble-documento.ts`
 * (F5-11) -- el mismo que usa `app/aplicacion.test.ts` para montar la
 * aplicación entera en Node (`vitest.config.ts` corre en
 * `environment: "node"`, sin `document`).
 *
 * Lo que NO se prueba aquí es qué texto sale en cada caso -- eso es
 * `contenido.test.ts`, puro y sin DOM. Esto prueba lo que solo un DOM (aunque
 * sea falso) puede decir: que el texto YA RESUELTO llega al árbol, que los
 * botones existen solo cuando toca, y que pulsarlos dispara el callback
 * correcto y ninguno más.
 */

import { describe, expect, it, vi } from "vitest";

import { crearDocumentoFalso, type ElementoFalso } from "../dom/doble-documento.ts";
import { PropuestaPerfil } from "./propuesta-perfil.ts";
import type { SugerenciaDePerfil } from "./tipos.ts";

const SUGERENCIA: SugerenciaDePerfil = {
  nombrePerfil: "Knock",
  disponibles: 7,
  total: 9,
  rolesDisponibles: [
    "engine_speed",
    "knock_level",
    "lambda_measured",
    "manifold_pressure",
    "coolant_temp",
    "oil_pressure",
    "ignition_advance",
  ],
  rolesFaltantes: ["boost_pressure_actual", "injector_duty"],
};

function montarEnContenedor(): { documento: Pick<Document, "createElement">; contenedor: ElementoFalso } {
  const documento = crearDocumentoFalso();
  const contenedor = documento.createElement("div");
  return { documento: documento as unknown as Pick<Document, "createElement">, contenedor };
}

describe("PropuestaPerfil, sin sugerencia", () => {
  it("pinta el aviso de que ningún perfil encajó y no monta ningún botón", () => {
    const { documento, contenedor } = montarEnContenedor();
    new PropuestaPerfil({
      contenedor: contenedor as unknown as HTMLElement,
      sugerencia: null,
      documento,
    });
    expect(contenedor.textoDelArbol()).toMatch(/ning[uú]n perfil/i);
    expect(contenedor.buscarTodosPorClase("dlv-propuesta-perfil__acciones")).toHaveLength(0);
    expect(contenedor.buscarPorClase("dlv-propuesta-perfil--sin-perfil")).not.toBeNull();
  });
});

describe("PropuestaPerfil, con sugerencia", () => {
  it("enseña el nombre del perfil, la cobertura y los roles que faltan", () => {
    const { documento, contenedor } = montarEnContenedor();
    new PropuestaPerfil({
      contenedor: contenedor as unknown as HTMLElement,
      sugerencia: SUGERENCIA,
      documento,
    });
    const texto = contenedor.textoDelArbol();
    expect(texto).toContain("Knock");
    expect(texto).toContain("7");
    expect(texto).toContain("9");
    expect(texto).toContain("boost_pressure_actual");
    expect(texto).toContain("injector_duty");
  });

  it("pulsar «usar este perfil» llama a onAceptar y no a onDescartar", () => {
    const { documento, contenedor } = montarEnContenedor();
    const onAceptar = vi.fn();
    const onDescartar = vi.fn();
    new PropuestaPerfil({
      contenedor: contenedor as unknown as HTMLElement,
      sugerencia: SUGERENCIA,
      documento,
      onAceptar,
      onDescartar,
    });
    const boton = contenedor.buscarPorClase("dlv-propuesta-perfil__aceptar");
    expect(boton).not.toBeNull();
    boton?.disparar("click");
    expect(onAceptar).toHaveBeenCalledTimes(1);
    expect(onDescartar).not.toHaveBeenCalled();
  });

  it("pulsar «no, gracias» llama a onDescartar y no a onAceptar", () => {
    const { documento, contenedor } = montarEnContenedor();
    const onAceptar = vi.fn();
    const onDescartar = vi.fn();
    new PropuestaPerfil({
      contenedor: contenedor as unknown as HTMLElement,
      sugerencia: SUGERENCIA,
      documento,
      onAceptar,
      onDescartar,
    });
    const boton = contenedor.buscarPorClase("dlv-propuesta-perfil__descartar");
    boton?.disparar("click");
    expect(onDescartar).toHaveBeenCalledTimes(1);
    expect(onAceptar).not.toHaveBeenCalled();
  });

  it("un perfil al 100% no pinta la línea de roles que faltan", () => {
    const { documento, contenedor } = montarEnContenedor();
    new PropuestaPerfil({
      contenedor: contenedor as unknown as HTMLElement,
      sugerencia: { ...SUGERENCIA, disponibles: 9, total: 9, rolesDisponibles: [...SUGERENCIA.rolesDisponibles, "x", "y"], rolesFaltantes: [] },
      documento,
    });
    expect(contenedor.buscarTodosPorClase("dlv-propuesta-perfil__faltan")).toHaveLength(0);
  });

  it("destruir() vacía el contenedor", () => {
    const { documento, contenedor } = montarEnContenedor();
    const propuesta = new PropuestaPerfil({
      contenedor: contenedor as unknown as HTMLElement,
      sugerencia: SUGERENCIA,
      documento,
    });
    expect(contenedor.hijos.length).toBeGreaterThan(0);
    propuesta.destruir();
    expect(contenedor.hijos.length).toBe(0);
  });

  it("una segunda sugerencia reemplaza la primera en vez de acumularse", () => {
    const { documento, contenedor } = montarEnContenedor();
    new PropuestaPerfil({ contenedor: contenedor as unknown as HTMLElement, sugerencia: SUGERENCIA, documento });
    new PropuestaPerfil({
      contenedor: contenedor as unknown as HTMLElement,
      sugerencia: { ...SUGERENCIA, nombrePerfil: "Lambda" },
      documento,
    });
    expect(contenedor.hijos.length).toBe(1);
    expect(contenedor.textoDelArbol()).toContain("Lambda");
    expect(contenedor.textoDelArbol()).not.toContain("Knock");
  });
});
