/**
 * Pruebas de `tema.ts` (F3-21).
 *
 * EL ENTORNO SE INYECTA; AQUÍ NO SE TOCA NINGÚN GLOBAL
 * ====================================================
 * `vitest.config.ts` fija `environment: "node"` a propósito, y todo `dlv-ui` se
 * prueba con dobles inyectables (`dom/doble-documento.ts`, `render/doble-gl.ts`).
 * La primera versión de estas pruebas parcheaba `window`, `document` y
 * `localStorage` globales con `Object.defineProperty`: habría fallado en CI por
 * falta de esos globales, y además daba por hecho que el tema inicial es
 * «oscuro» cuando el `matchMedia` de jsdom responde `matches: false` a todo y por
 * tanto habría salido «claro» — media suite afirmando lo contrario de lo que hace
 * el código, incluidas dos comparaciones de la paleta oscura con la clara que en
 * realidad comparaban la clara consigo misma.
 *
 * Con el entorno inyectado, la preferencia del sistema es un dato de la prueba y
 * no una propiedad del entorno de ejecución, así que la precedencia de F3-21
 * —usuario > sistema > oscuro— se puede comprobar de verdad.
 */

import { describe, expect, it, beforeEach } from "vitest";

import {
  alCambiarTema,
  establecerTema,
  inicializarTema,
  leerColor,
  obtenerPaletaActual,
  obtenerTemaActual,
  parametrosDeSerie,
  TEMAS_DISPONIBLES,
  type EntornoTema,
  type NombreColor,
  type NombreTema,
} from "./tema.ts";

/** Doble del `documentElement`: solo `dataset` y `style.setProperty`. */
function crearRaizFalsa(): {
  dataset: Record<string, string | undefined>;
  style: { setProperty(n: string, v: string): void };
  leer(nombre: string): string;
} {
  const propiedades: Record<string, string> = {};
  return {
    dataset: {} as Record<string, string | undefined>,
    style: {
      setProperty: (n: string, v: string): void => {
        propiedades[n] = v;
      },
    },
    leer: (nombre: string): string => propiedades[nombre] ?? "",
  };
}

/** Doble de `localStorage`, con el contenido a la vista de la prueba. */
function crearAlmacenFalso(inicial: Record<string, string> = {}): {
  getItem(c: string): string | null;
  setItem(c: string, v: string): void;
  contenido: Record<string, string>;
} {
  const contenido: Record<string, string> = { ...inicial };
  return {
    contenido,
    getItem: (c: string): string | null => contenido[c] ?? null,
    setItem: (c: string, v: string): void => {
      contenido[c] = v;
    },
  };
}

let raiz: ReturnType<typeof crearRaizFalsa>;
let almacen: ReturnType<typeof crearAlmacenFalso>;

/** El entorno de una prueba: preferencia del sistema explícita, siempre. */
function entornoCon(
  preferencia: "dark" | "light" | null,
  guardado?: string,
): EntornoTema {
  raiz = crearRaizFalsa();
  almacen = crearAlmacenFalso(guardado === undefined ? {} : { "dlv-tema-preferido": guardado });
  return {
    ventana:
      preferencia === null
        ? undefined
        : { matchMedia: (consulta: string) => ({ matches: consulta.includes("dark") && preferencia === "dark" }) },
    documento: { documentElement: raiz },
    almacen,
  };
}

beforeEach(() => {
  // Estado de partida idéntico en cada prueba: `temaActual` es estado de módulo.
  inicializarTema(entornoCon("dark"));
});

describe("tema: precedencia al inicializar", () => {
  it("sin preferencia guardada sigue al sistema en oscuro", () => {
    inicializarTema(entornoCon("dark"));
    expect(obtenerTemaActual()).toBe("oscuro");
    expect(raiz.dataset.theme).toBe("oscuro");
  });

  it("sin preferencia guardada sigue al sistema en claro", () => {
    inicializarTema(entornoCon("light"));
    expect(obtenerTemaActual()).toBe("claro");
  });

  it("la preferencia del usuario gana a la del sistema", () => {
    inicializarTema(entornoCon("light", "altContraste"));
    expect(obtenerTemaActual()).toBe("altContraste");
  });

  it("cae a oscuro si el navegador no expone la preferencia", () => {
    inicializarTema(entornoCon(null));
    expect(obtenerTemaActual()).toBe("oscuro");
  });

  it("ignora un valor inválido en el almacenamiento y no lo aplica", () => {
    inicializarTema(entornoCon("light", "morado"));
    expect(obtenerTemaActual()).toBe("claro");
  });

  it("aplica las variables CSS en línea, que es lo que gana a la hoja", () => {
    inicializarTema(entornoCon("dark"));
    expect(raiz.leer("--fondo")).toBe("#14161a");
  });
});

describe("tema: cambio explícito", () => {
  it("cambia el tema y lo guarda como preferencia", () => {
    establecerTema("altContraste");
    expect(obtenerTemaActual()).toBe("altContraste");
    expect(almacen.contenido["dlv-tema-preferido"]).toBe("altContraste");
    expect(raiz.dataset.theme).toBe("altContraste");
  });

  it("se puede pasar por los tres temas", () => {
    for (const tema of ["oscuro", "claro", "altContraste"] satisfies NombreTema[]) {
      establecerTema(tema);
      expect(obtenerTemaActual()).toBe(tema);
    }
  });

  it("declara color-scheme claro solo en el tema claro", () => {
    establecerTema("claro");
    expect(raiz.leer("color-scheme")).toBe("light");
    establecerTema("altContraste");
    expect(raiz.leer("color-scheme")).toBe("dark");
  });
});

describe("tema: aviso de cambio", () => {
  it("avisa a los suscriptores cuando el tema cambia", () => {
    let avisos = 0;
    const baja = alCambiarTema(() => {
      avisos += 1;
    });
    establecerTema("claro");
    expect(avisos).toBe(1);
    baja();
  });

  it("no avisa si el tema elegido es el que ya estaba", () => {
    /* Sin esto, cada `establecerTema` repetido forzaría volver a subir todas las
       series a la GPU sin que ningún color haya cambiado. */
    establecerTema("claro");
    let avisos = 0;
    const baja = alCambiarTema(() => {
      avisos += 1;
    });
    establecerTema("claro");
    expect(avisos).toBe(0);
    baja();
  });

  it("deja de avisar tras darse de baja", () => {
    let avisos = 0;
    const baja = alCambiarTema(() => {
      avisos += 1;
    });
    baja();
    establecerTema("altContraste");
    expect(avisos).toBe(0);
  });
});

describe("tema: colores de serie", () => {
  it("cambian con el tema", () => {
    establecerTema("oscuro");
    const oscuro = parametrosDeSerie(0);
    establecerTema("claro");
    const claro = parametrosDeSerie(0);
    expect(claro).not.toEqual(oscuro);
  });

  it("en alto contraste la luz alterna, para no depender solo del tono", () => {
    /* Es el criterio de accesibilidad del tema: una diferencia de luz se
       conserva bajo protanopia y deuteranopia, donde la de tono desaparece. */
    establecerTema("altContraste");
    const par = parametrosDeSerie(2);
    const impar = parametrosDeSerie(3);
    expect(par.luz).not.toBe(impar.luz);
    expect(Math.abs(par.luz - impar.luz)).toBeGreaterThanOrEqual(0.2);
  });

  it("un código negativo da los mismos parámetros que su valor absoluto", () => {
    /* Los códigos de estado de F3-13 pueden ser negativos (`Launch Control
       State`), y un `%` de un negativo en JS es negativo. */
    establecerTema("altContraste");
    expect(parametrosDeSerie(-3)).toEqual(parametrosDeSerie(3));
  });

  it("da valores en el rango válido de HSL para los tres temas", () => {
    for (const tema of TEMAS_DISPONIBLES) {
      establecerTema(tema);
      for (const discriminante of [0, 1, 7, -12]) {
        const { saturacion, luz } = parametrosDeSerie(discriminante);
        expect(saturacion).toBeGreaterThan(0);
        expect(saturacion).toBeLessThanOrEqual(1);
        expect(luz).toBeGreaterThan(0);
        expect(luz).toBeLessThan(1);
      }
    }
  });
});

describe("tema: lectura de la paleta", () => {
  const nombres: NombreColor[] = [
    "fondo",
    "panel",
    "panelBorde",
    "texto",
    "textoTenue",
    "acento",
    "rejilla",
    "eje",
  ];

  it("los tres temas definen los ocho colores", () => {
    for (const tema of TEMAS_DISPONIBLES) {
      establecerTema(tema);
      for (const nombre of nombres) {
        expect(leerColor(nombre), `${tema}.${nombre}`).toBeTruthy();
      }
    }
  });

  it("el tema oscuro conserva exactamente los colores que ya tenía", () => {
    /* F3-21 añade temas; no rediseña el que había. Si alguno de estos cambia,
       tiene que ser una decisión explícita y no un efecto colateral. */
    establecerTema("oscuro");
    expect(leerColor("fondo")).toBe("#14161a");
    expect(leerColor("panel")).toBe("#1c1f26");
    expect(leerColor("panelBorde")).toBe("#2c313c");
    expect(leerColor("texto")).toBe("#e6e8ec");
    expect(leerColor("textoTenue")).toBe("#9aa3b2");
    expect(leerColor("acento")).toBe("#4da3ff");
  });

  it("el fondo y el texto se invierten entre oscuro y claro", () => {
    establecerTema("oscuro");
    const oscuro = obtenerPaletaActual();
    establecerTema("claro");
    const claro = obtenerPaletaActual();
    expect(oscuro.fondo).not.toBe(claro.fondo);
    expect(oscuro.texto).not.toBe(claro.texto);
  });

  it("alto contraste lleva el texto y el fondo a los extremos", () => {
    /* El criterio declarado es 7:1 mínimo (WCAG AAA); blanco sobre negro da
       21:1, y comprobar los extremos es lo que impide que alguien «suavice» el
       tema y se lleve por delante su única razón de existir. */
    establecerTema("altContraste");
    expect(leerColor("fondo")).toBe("#000000");
    expect(leerColor("texto")).toBe("#ffffff");
  });

  it("alto contraste hace la rejilla y los ejes más visibles que el oscuro", () => {
    establecerTema("oscuro");
    const oscuro = obtenerPaletaActual();
    establecerTema("altContraste");
    const alto = obtenerPaletaActual();
    expect(alto.rejilla).not.toBe(oscuro.rejilla);
    expect(alto.eje).not.toBe(oscuro.eje);
  });
});

describe("tema: constantes públicas", () => {
  it("hay exactamente los tres temas de la tarea", () => {
    expect([...TEMAS_DISPONIBLES]).toEqual(["oscuro", "claro", "altContraste"]);
  });
});
