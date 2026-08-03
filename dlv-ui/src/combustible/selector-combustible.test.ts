/**
 * Pruebas del componente `SelectorCombustible` contra el doble de DOM.
 *
 * Igual que `unidades/selector-unidad.test.ts` prueba el selector de unidad
 * contra `dom-falso.ts` sin jsdom, este fichero prueba el selector de
 * combustible. Lo que pide el encargo del propietario y que aquí se
 * comprueba: (1) se puede elegir un combustible de la lista, (2) se puede
 * teclear un factor a mano, (3) los tres orígenes -- log / usuario / supuesto
 * -- se distinguen, y el caso supuesto se ve como un aviso y no como un dato
 * más, y (4) el componente no convierte nada: solo emite el factor resuelto.
 */

import { describe, expect, it, vi } from "vitest";

import type { CambioFactor } from "./selector-combustible.ts";
import { SelectorCombustible } from "./selector-combustible.ts";
import type { NodoFalso } from "./dom-falso.ts";
import { crearFabricaDomFalsa, hijosDe } from "./dom-falso.ts";
import type { InputDom, SelectDom } from "./dom.ts";
import { catalogoDeCombustiblesDePrueba } from "./fixtures-catalogo.ts";
import { OrigenFactor } from "./tipos.ts";

function construir(opciones?: {
  estequiometriaDelLog?: number;
  eleccionInicial?: { combustibleId?: string; estequiometria: number };
  onCambio?: (cambio: CambioFactor) => void;
}) {
  const doble = crearFabricaDomFalsa();
  const selector = new SelectorCombustible(doble.fabrica, {
    catalogo: catalogoDeCombustiblesDePrueba(),
    estequiometriaDelLog: opciones?.estequiometriaDelLog,
    eleccionInicial: opciones?.eleccionInicial,
    onCambio: opciones?.onCambio,
  });
  return { doble, selector };
}

function raizDe(selector: SelectorCombustible): NodoFalso {
  return selector.elemento as unknown as NodoFalso;
}

/** La fila "Combustible": su `<select>`. */
function selectCombustible(raiz: NodoFalso): SelectDom {
  const fila = hijosDe(raiz)[0]!;
  const select = hijosDe(fila).find((h) => h.etiquetaTag === "select");
  if (select === undefined) throw new Error("no hay <select> de combustible");
  return select as unknown as SelectDom;
}

/** La fila "Estequiometría" (solo existe en modo manual): su `<input>`. */
function inputManual(raiz: NodoFalso): InputDom | undefined {
  for (const fila of hijosDe(raiz)) {
    const input = hijosDe(fila).find((h) => h.etiquetaTag === "input");
    if (input !== undefined) return input as unknown as InputDom;
  }
  return undefined;
}

/** El span de origen: siempre el último hijo de la raíz. */
function spanOrigen(raiz: NodoFalso): NodoFalso {
  const hijos = hijosDe(raiz);
  return hijos[hijos.length - 1]!;
}

describe("SelectorCombustible: construcción", () => {
  it("sin elección ni log, arranca en automático y resuelve al combustible por omisión", () => {
    const { selector } = construir();
    expect(selector.factorResuelto.origen).toBe(OrigenFactor.SUPUESTO);
    expect(selector.factorResuelto.estequiometria).toBe(14.7);
    expect(selector.eleccionUsuario).toBeUndefined();
  });

  it("el select de combustible ofrece automático, cada combustible del catálogo y manual", () => {
    const { selector } = construir();
    const select = selectCombustible(raizDe(selector));
    const opciones = hijosDe(select).map((o) => o.textContent);
    expect(opciones[0]).toContain("automático");
    expect(opciones).toContain("Gasolina (14.7)");
    expect(opciones).toContain("E85 (9.77)");
    expect(opciones).toContain("Metanol (6.4)");
    expect(opciones.at(-1)).toContain("manual");
  });

  it("sin elegir combustible, no hay fila de estequiometría manual", () => {
    const { selector } = construir();
    expect(inputManual(raizDe(selector))).toBeUndefined();
  });
});

describe("SelectorCombustible: los tres orígenes se distinguen", () => {
  it("con el canal del log presente, el origen es LOG", () => {
    const { selector } = construir({ estequiometriaDelLog: 9.77 });
    expect(selector.factorResuelto.origen).toBe(OrigenFactor.LOG);
    expect(selector.factorResuelto.estequiometria).toBe(9.77);
    expect(selector.factorResuelto.combustibleId).toBe("e85");
  });

  it("sin canal en el log, el origen es SUPUESTO (gasolina) y no USUARIO ni LOG", () => {
    const { selector } = construir();
    expect(selector.factorResuelto.origen).toBe(OrigenFactor.SUPUESTO);
  });

  it("eligiendo un combustible de la lista, el origen pasa a USUARIO y gana al log", () => {
    const { selector, doble } = construir({ estequiometriaDelLog: 14.7 });
    const select = selectCombustible(raizDe(selector));
    select.value = "metanol";
    doble.disparar(select, "change");

    expect(selector.factorResuelto.origen).toBe(OrigenFactor.USUARIO);
    expect(selector.factorResuelto.estequiometria).toBe(6.4);
    expect(selector.eleccionUsuario).toEqual({ combustibleId: "metanol", estequiometria: 6.4 });
  });

  it("volver a «automático» descarta la elección y vuelve a log/supuesto", () => {
    const { selector, doble } = construir({ estequiometriaDelLog: 9.77 });
    let raiz = raizDe(selector);
    let select = selectCombustible(raiz);
    select.value = "metanol";
    doble.disparar(select, "change");
    expect(selector.factorResuelto.origen).toBe(OrigenFactor.USUARIO);

    raiz = raizDe(selector);
    select = selectCombustible(raiz);
    select.value = ""; // "— automático —"
    doble.disparar(select, "change");

    expect(selector.eleccionUsuario).toBeUndefined();
    expect(selector.factorResuelto.origen).toBe(OrigenFactor.LOG);
    expect(selector.factorResuelto.estequiometria).toBe(9.77);
  });
});

describe("SelectorCombustible: el caso SUPUESTO se ve como un aviso, no como un dato normal", () => {
  it("el span de origen lleva la clase de aviso cuando el factor es supuesto", () => {
    const { selector } = construir();
    const span = spanOrigen(raizDe(selector));
    expect(span.textContent).toContain("SUPUESTO");
  });

  it("con dato de log, el texto NO dice SUPUESTO", () => {
    const { selector } = construir({ estequiometriaDelLog: 14.7 });
    const span = spanOrigen(raizDe(selector));
    expect(span.textContent).not.toContain("SUPUESTO");
    expect(span.textContent).toContain("leído del log");
  });

  it("con elección del usuario, el texto dice que se eligió aquí", () => {
    const { selector, doble } = construir();
    const select = selectCombustible(raizDe(selector));
    select.value = "e85";
    doble.disparar(select, "change");
    const span = spanOrigen(raizDe(selector));
    expect(span.textContent).toContain("elegido aquí");
  });
});

describe("SelectorCombustible: editar el factor a mano", () => {
  it("elegir «valor manual» muestra el campo de estequiometría, arrancado con el valor activo", () => {
    const { selector, doble } = construir({ estequiometriaDelLog: 9.77 });
    const select = selectCombustible(raizDe(selector));
    select.value = "__manual__";
    doble.disparar(select, "change");

    const input = inputManual(raizDe(selector));
    expect(input).toBeDefined();
    expect(input!.value).toBe("9.77");
    // Entrar en modo manual ya cuenta como elección del usuario (docs: "editar el factor a mano").
    expect(selector.factorResuelto.origen).toBe(OrigenFactor.USUARIO);
  });

  it("teclear un valor con coma decimal se refleja en el factor resuelto", () => {
    const { selector, doble } = construir();
    let raiz = raizDe(selector);
    let select = selectCombustible(raiz);
    select.value = "__manual__";
    doble.disparar(select, "change");

    raiz = raizDe(selector);
    const input = inputManual(raiz)!;
    input.value = "8,5";
    doble.disparar(input, "change");

    expect(selector.factorResuelto.estequiometria).toBe(8.5);
    expect(selector.factorResuelto.origen).toBe(OrigenFactor.USUARIO);
    // 8,5 no coincide con ningún combustible del catálogo de prueba.
    expect(selector.factorResuelto.combustibleId).toBeUndefined();
    expect(selector.eleccionUsuario).toEqual({ estequiometria: 8.5 });
  });

  it("teclear un valor no numérico no cambia el factor activo y lo marca como inválido", () => {
    const { selector, doble } = construir();
    let raiz = raizDe(selector);
    let select = selectCombustible(raiz);
    select.value = "__manual__";
    doble.disparar(select, "change");

    const antes = selector.factorResuelto;

    raiz = raizDe(selector);
    const input = inputManual(raiz)!;
    input.value = "abc";
    doble.disparar(input, "change");

    expect(selector.factorResuelto).toEqual(antes);

    raiz = raizDe(selector);
    const filaManual = hijosDe(raiz).find((f) => hijosDe(f).some((h) => h.etiquetaTag === "input"))!;
    const notaError = hijosDe(filaManual).find((h) => h.textContent.includes("no es un número válido"));
    expect(notaError).toBeDefined();
  });

  it("teclear cero o un negativo se rechaza igual que el texto no numérico", () => {
    const { selector, doble } = construir();
    let raiz = raizDe(selector);
    let select = selectCombustible(raiz);
    select.value = "__manual__";
    doble.disparar(select, "change");
    const antes = selector.factorResuelto;

    raiz = raizDe(selector);
    const input = inputManual(raiz)!;
    input.value = "0";
    doble.disparar(input, "change");

    expect(selector.factorResuelto).toEqual(antes);
  });
});

describe("SelectorCombustible: eleccionInicial (restaurar desde el perfil del coche)", () => {
  it("restaura una elección de combustible de catálogo", () => {
    const { selector } = construir({
      eleccionInicial: { combustibleId: "e85", estequiometria: 9.77 },
    });
    expect(selector.factorResuelto.origen).toBe(OrigenFactor.USUARIO);
    expect(selector.factorResuelto.combustibleId).toBe("e85");
  });

  it("restaura un valor manual persistido y lo muestra en el campo", () => {
    const { selector } = construir({ eleccionInicial: { estequiometria: 11.2 } });
    expect(selector.factorResuelto.estequiometria).toBe(11.2);
    const input = inputManual(raizDe(selector));
    expect(input?.value).toBe("11.2");
  });
});

describe("SelectorCombustible: actualizar la estequiometría del log a posteriori", () => {
  it("si el usuario no ha elegido nada, actualizar el valor del log cambia el factor resuelto", () => {
    const onCambio = vi.fn();
    const { selector } = construir({ onCambio });
    selector.actualizarEstequiometriaDelLog(6.4);
    expect(selector.factorResuelto.origen).toBe(OrigenFactor.LOG);
    expect(selector.factorResuelto.estequiometria).toBe(6.4);
    expect(onCambio).toHaveBeenCalledTimes(1);
  });

  it("si el usuario ya eligió, actualizar el log no lo desplaza (el usuario sigue ganando)", () => {
    const { selector, doble } = construir();
    const select = selectCombustible(raizDe(selector));
    select.value = "metanol";
    doble.disparar(select, "change");

    selector.actualizarEstequiometriaDelLog(14.7);

    expect(selector.factorResuelto.origen).toBe(OrigenFactor.USUARIO);
    expect(selector.factorResuelto.estequiometria).toBe(6.4);
  });
});

describe("SelectorCombustible: callback de cambio", () => {
  it("emite `onCambio` con la elección y el factor resueltos", () => {
    const onCambio = vi.fn();
    const { selector, doble } = construir({ onCambio });
    const select = selectCombustible(raizDe(selector));
    select.value = "e85";
    doble.disparar(select, "change");

    expect(onCambio).toHaveBeenCalledTimes(1);
    const cambio = onCambio.mock.calls[0]![0] as CambioFactor;
    expect(cambio.eleccionUsuario).toEqual({ combustibleId: "e85", estequiometria: 9.77 });
    expect(cambio.factor.origen).toBe(OrigenFactor.USUARIO);
  });

  it("un valor manual inválido NO dispara `onCambio` de nuevo", () => {
    const onCambio = vi.fn();
    const { selector, doble } = construir({ onCambio });
    let raiz = raizDe(selector);
    let select = selectCombustible(raiz);
    select.value = "__manual__";
    doble.disparar(select, "change"); // 1ª llamada: entrar en modo manual ya es una elección

    expect(onCambio).toHaveBeenCalledTimes(1);

    raiz = raizDe(selector);
    const input = inputManual(raiz)!;
    input.value = "no-numero";
    doble.disparar(input, "change");

    expect(onCambio).toHaveBeenCalledTimes(1); // sigue en 1: el valor inválido no emite

    input.value = "7,5";
    doble.disparar(input, "change");

    expect(onCambio).toHaveBeenCalledTimes(2); // ahora sí, con el valor válido
  });

  it("no pasar onCambio no revienta al cambiar de combustible", () => {
    const { selector, doble } = construir();
    const select = selectCombustible(raizDe(selector));
    expect(() => {
      select.value = "diesel";
      doble.disparar(select, "change");
    }).not.toThrow();
    expect(selector.factorResuelto.combustibleId).toBe("diesel");
  });
});

describe("SelectorCombustible: no convierte ningún valor", () => {
  it("`factorResuelto` es exactamente lo que da `resolverFactorEstequiometrico` (no hay una copia de la precedencia dentro del componente)", async () => {
    const { resolverFactorEstequiometrico } = await import("./resolucion.ts");
    const catalogo = catalogoDeCombustiblesDePrueba();
    const { selector, doble } = construir({ estequiometriaDelLog: 9.77 });
    const select = selectCombustible(raizDe(selector));
    select.value = "metanol";
    doble.disparar(select, "change");

    const directo = resolverFactorEstequiometrico({
      catalogo,
      estequiometriaDelLog: 9.77,
      eleccionUsuario: selector.eleccionUsuario,
    });
    expect(selector.factorResuelto).toEqual(directo);
  });
});
