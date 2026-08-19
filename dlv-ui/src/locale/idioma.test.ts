/**
 * Pruebas del idioma activo (F5-10). Mismo enfoque que `tema/tema.test.ts`:
 * entorno inyectable (`EntornoIdioma`) en vez de `localStorage`/`navigator`
 * reales, para que la precedencia (usuario > navegador > español) se pueda
 * probar sin un navegador de verdad.
 */

import { beforeEach, describe, expect, it } from "vitest";

import { alCambiarIdioma, establecerIdioma, inicializarIdioma, obtenerIdiomaActual } from "./idioma.ts";

/** Un `localStorage` de mentira, suficiente para lo que `idioma.ts` le pide. */
function almacenFalso(inicial: Record<string, string> = {}): {
  getItem(clave: string): string | null;
  setItem(clave: string, valor: string): void;
} {
  const datos = new Map(Object.entries(inicial));
  return {
    getItem: (clave) => datos.get(clave) ?? null,
    setItem: (clave, valor) => {
      datos.set(clave, valor);
    },
  };
}

beforeEach(() => {
  // Cada prueba empieza desde un entorno vacío explícito (ni navegador ni
  // almacén), para que el orden de ejecución de las pruebas no importe.
  inicializarIdioma({});
});

describe("precedencia de inicialización", () => {
  it("sin navegador ni preferencia guardada, español", () => {
    inicializarIdioma({});
    expect(obtenerIdiomaActual()).toBe("es");
  });

  it("navigator.language en inglés, sin preferencia guardada: inglés", () => {
    inicializarIdioma({ navegador: { language: "en-US" } });
    expect(obtenerIdiomaActual()).toBe("en");
  });

  it("navigator.language que no es inglés cae a español, no a un tercer idioma", () => {
    inicializarIdioma({ navegador: { language: "fr-FR" } });
    expect(obtenerIdiomaActual()).toBe("es");
  });

  it("la preferencia guardada del usuario gana al navegador", () => {
    const almacen = almacenFalso({ "dlv-idioma-preferido": "es" });
    inicializarIdioma({ navegador: { language: "en-US" }, almacen });
    expect(obtenerIdiomaActual()).toBe("es");
  });

  it("un valor corrupto en el almacén (no 'es'/'en') se ignora, no revienta", () => {
    const almacen = almacenFalso({ "dlv-idioma-preferido": "fr" });
    inicializarIdioma({ navegador: { language: "en-US" }, almacen });
    expect(obtenerIdiomaActual()).toBe("en");
  });
});

describe("establecerIdioma", () => {
  it("cambia el idioma activo y lo persiste en el almacén inyectado", () => {
    const almacen = almacenFalso();
    inicializarIdioma({ almacen });
    establecerIdioma("en");
    expect(obtenerIdiomaActual()).toBe("en");
    expect(almacen.getItem("dlv-idioma-preferido")).toBe("en");
  });

  it("sin almacén no revienta: el cambio en memoria sigue funcionando", () => {
    inicializarIdioma({});
    expect(() => establecerIdioma("en")).not.toThrow();
    expect(obtenerIdiomaActual()).toBe("en");
  });
});

describe("alCambiarIdioma", () => {
  it("avisa a los suscriptores cuando el idioma cambia de verdad", () => {
    inicializarIdioma({});
    let avisos = 0;
    const baja = alCambiarIdioma(() => {
      avisos += 1;
    });
    establecerIdioma("en");
    expect(avisos).toBe(1);
    baja();
  });

  it("NO avisa si se establece el mismo idioma que ya estaba activo", () => {
    inicializarIdioma({});
    let avisos = 0;
    alCambiarIdioma(() => {
      avisos += 1;
    });
    establecerIdioma("es"); // ya era "es": no es un cambio real.
    expect(avisos).toBe(0);
  });

  it("la función devuelta da de baja al suscriptor", () => {
    inicializarIdioma({});
    let avisos = 0;
    const baja = alCambiarIdioma(() => {
      avisos += 1;
    });
    baja();
    establecerIdioma("en");
    expect(avisos).toBe(0);
  });
});
