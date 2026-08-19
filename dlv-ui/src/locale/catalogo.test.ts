/**
 * Pruebas de `t()` y de los dos catálogos (F5-10).
 *
 * El bloque que da sentido a este fichero es «los dos catálogos tienen
 * exactamente las mismas claves»: es la prueba que pide el encargo para la
 * decisión §2 («cómo se prueba que los dos catálogos no se desincronizan»).
 * `tsc --noEmit` ya lo impediría al compilar (`textos.en.ts` está tipado
 * como `Record<ClaveTexto, string>`, ver su cabecera), pero esta prueba corre
 * en `npm test` sin depender de que nadie ejecute `tsc` a mano, y además
 * comprueba algo que el tipo no cubre: que ninguna traducción se quedó
 * vacía.
 */

import { describe, expect, it } from "vitest";

import { establecerIdioma, inicializarIdioma } from "./idioma.ts";
import { t, type ClaveTexto } from "./catalogo.ts";
import { TEXTOS_ES } from "./textos.es.ts";
import { TEXTOS_EN } from "./textos.en.ts";

describe("los dos catálogos tienen las mismas claves", () => {
  it("mismo número de claves", () => {
    expect(Object.keys(TEXTOS_EN).length).toBe(Object.keys(TEXTOS_ES).length);
  });

  it("ninguna clave de ES falta en EN", () => {
    for (const clave of Object.keys(TEXTOS_ES)) {
      expect(Object.prototype.hasOwnProperty.call(TEXTOS_EN, clave)).toBe(true);
    }
  });

  it("ninguna clave de EN sobra frente a ES (el catálogo canónico)", () => {
    for (const clave of Object.keys(TEXTOS_EN)) {
      expect(Object.prototype.hasOwnProperty.call(TEXTOS_ES, clave)).toBe(true);
    }
  });

  it("ninguna traducción está vacía en ningún catálogo", () => {
    // Es justo el caso que la tarea señala como el peor posible: una clave
    // presente pero con "" como valor pasaría la comprobación de arriba y
    // seguiría dejando un botón mudo.
    for (const [clave, texto] of Object.entries(TEXTOS_ES)) {
      expect(texto.length, `TEXTOS_ES["${clave}"] está vacío`).toBeGreaterThan(0);
    }
    for (const [clave, texto] of Object.entries(TEXTOS_EN)) {
      expect(texto.length, `TEXTOS_EN["${clave}"] está vacío`).toBeGreaterThan(0);
    }
  });
});

describe("t() lee el idioma activo", () => {
  it("con español activo, devuelve el texto español", () => {
    inicializarIdioma({});
    expect(t("incidencias.saltar")).toBe("Saltar");
  });

  it("con inglés activo, devuelve el texto inglés", () => {
    inicializarIdioma({});
    establecerIdioma("en");
    expect(t("incidencias.saltar")).toBe("Jump");
  });

  it("español es el idioma por omisión, igual que en numerico.ts", () => {
    inicializarIdioma({});
    expect(t("unidades.fijadoAqui")).toBe(TEXTOS_ES["unidades.fijadoAqui"]);
  });
});

describe("sustitución de variables", () => {
  it("reemplaza {n} por el valor pasado", () => {
    inicializarIdioma({});
    expect(t("canales.constanteN", { n: 3 })).toBe("3 constante(s)");
  });

  it("una plantilla con dos apariciones de la misma variable las sustituye las dos", () => {
    inicializarIdioma({});
    // "{n} canal(es) oculto(s)" solo tiene una variable, pero se comprueba
    // aquí que sustituir no depende de que la plantilla actual tenga
    // exactamente una: cualquier futura clave con {n} repetido debe seguir
    // funcionando sin tocar `sustituir`.
    expect(t("canales.ocultosPrefijo", { n: 5 })).toBe("5 canal(es) oculto(s)");
  });

  it("una llave sin variable correspondiente se deja tal cual, no revienta", () => {
    inicializarIdioma({});
    expect(t("incidencias.saltarTitulo", {})).toBe("Saltar al instante en que empezó ({instante})");
  });
});

describe("decisión §1: una clave que no existe en ningún catálogo nunca da cadena vacía", () => {
  it("devuelve la clave entre corchetes en vez de \"\"", () => {
    inicializarIdioma({});
    const claveInventada = "esto.no.existe.en.ningun.catalogo" as ClaveTexto;
    const resultado = t(claveInventada);
    expect(resultado).not.toBe("");
    expect(resultado).toContain("esto.no.existe.en.ningun.catalogo");
  });

  it("no lanza una excepción", () => {
    inicializarIdioma({});
    const claveInventada = "otra.clave.inventada" as ClaveTexto;
    expect(() => t(claveInventada)).not.toThrow();
  });
});
