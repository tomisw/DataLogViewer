/**
 * Pruebas del componente `SelectorUnidad` contra el doble de DOM.
 *
 * Igual que `render/renderizador.test.ts` prueba el renderizador contra
 * `doble-gl.ts` sin GPU, este fichero prueba el selector contra
 * `dom-falso.ts` sin jsdom. Lo que se comprueba es exactamente lo que pide
 * el encargo: la precedencia visible a tres niveles, la distinción
 * heredado/fijado, y que ningún cambio de unidad haga nada con canales que
 * no están declarados. No hay banco de rendimiento aquí porque este
 * componente no toca datos (ver la cabecera de `selector-unidad.ts`): el
 * presupuesto de <100 ms de §2.6 es sobre el repintado de cubos, ajeno a
 * este árbol de controles.
 */

import { describe, expect, it, vi } from "vitest";

import type { NodoFalso } from "./dom-falso.ts";
import { crearFabricaDomFalsa, hijosDe } from "./dom-falso.ts";
import type { SelectDom } from "./dom.ts";
import { catalogoDePrueba } from "./fixtures-catalogo.ts";
import { explicacionDeCapa, resolverUnidad } from "./resolucion.ts";
import { SelectorUnidad } from "./selector-unidad.ts";
import type { CanalInfo } from "./tipos.ts";
import { Capa } from "./tipos.ts";

const CANALES: readonly CanalInfo[] = [
  { id: "canal_temp", etiqueta: "Temp. refrigerante", dimensionId: "temperature" },
  { id: "canal_lambda", etiqueta: "Lambda banco 1", dimensionId: "mixture_ratio" },
  { id: "canal_ruido", etiqueta: "Nivel de sonido", dimensionId: "sound_level" },
  { id: "canal_desconocido", etiqueta: "Canal sin confirmar", dimensionId: "unknown" },
];

function construir(opciones?: {
  onCambio?: (cambio: import("./selector-unidad.ts").CambioUnidad) => void;
}) {
  const doble = crearFabricaDomFalsa();
  const selector = new SelectorUnidad(doble.fabrica, {
    catalogo: catalogoDePrueba(),
    canales: CANALES,
    onCambio: opciones?.onCambio,
  });
  return { doble, selector };
}

/** El `<select>` de una fila, identificada por el texto de su etiqueta. */
function selectDeFila(raiz: NodoFalso, etiquetaFila: string): SelectDom {
  for (const fila of hijosDe(raiz)) {
    const etiqueta = hijosDe(fila).find((h) => h.etiquetaTag === "span");
    if (etiqueta?.textContent === etiquetaFila) {
      const select = hijosDe(fila).find((h) => h.etiquetaTag === "select");
      if (select === undefined) {
        throw new Error(`la fila '${etiquetaFila}' no tiene <select> (¿dimensión no convertible?)`);
      }
      return select as unknown as SelectDom;
    }
  }
  throw new Error(`no se encontró una fila con etiqueta '${etiquetaFila}'`);
}

function notaDeFila(raiz: NodoFalso, etiquetaFila: string): string {
  for (const fila of hijosDe(raiz)) {
    const etiqueta = hijosDe(fila).find((h) => h.etiquetaTag === "span");
    if (etiqueta?.textContent === etiquetaFila) {
      const spans = hijosDe(fila).filter((h) => h.etiquetaTag === "span");
      // spans[0] es la etiqueta de la fila; la nota es el último span.
      return spans.at(-1)?.textContent ?? "";
    }
  }
  throw new Error(`no se encontró una fila con etiqueta '${etiquetaFila}'`);
}

describe("SelectorUnidad: construcción", () => {
  it("crea una fila por preset global, por dimensión convertible y por canal", () => {
    const { selector } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    // 1 (global) + 3 dimensiones convertibles (temperature, pressure, mixture_ratio) + 4 canales.
    expect(hijosDe(raiz)).toHaveLength(1 + 3 + 4);
  });

  it("un canal de confianza sin confirmar (`unknown`) se muestra desactivado y en crudo (docs/06 §6.8)", () => {
    const { selector } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    const fila = hijosDe(raiz).find(
      (f) => hijosDe(f).find((h) => h.etiquetaTag === "span")?.textContent === "Canal sin confirmar",
    )!;
    const aviso = hijosDe(fila).find((h) => h.etiquetaTag === "span" && h.textContent.includes("crudo"));
    expect(aviso?.textContent).toContain("sin confirmar");
    expect(hijosDe(fila).some((h) => h.etiquetaTag === "select")).toBe(false);
  });

  it("la dimensión no convertible (sound_level) no aparece como fila de dimensión", () => {
    const { selector } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    expect(() => selectDeFila(raiz, "Nivel de sonido")).toThrow(/no tiene <select>/);
  });

  it("un canal de dimensión no convertible se muestra desactivado, no con una unidad inventada", () => {
    const { selector } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    const filaCanalRuido = hijosDe(raiz).find(
      (fila) => hijosDe(fila).find((h) => h.etiquetaTag === "span")?.textContent === "Nivel de sonido",
    )!;
    const aviso = hijosDe(filaCanalRuido).find((h) => h.etiquetaTag === "span" && h.textContent.includes("sin"));
    expect(aviso).toBeDefined();
    expect(hijosDe(filaCanalRuido).some((h) => h.etiquetaTag === "select")).toBe(false);
  });
});

describe("SelectorUnidad: precedencia visible a tres niveles", () => {
  it("por omisión, un canal hereda del preset por omisión del catálogo", () => {
    const { selector } = construir();
    const r = selector.unidadResueltaDe("canal_temp");
    expect(r.capa).toBe(Capa.PRESET);
    expect(r.unidad.id).toBe("degC"); // preset "metrico" de la fixture
  });

  it("cambiar el preset global cambia la unidad de los canales que heredan de él", () => {
    const { selector, doble } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    const selectPreset = selectDeFila(raiz, "Global");

    selectPreset.value = "imperial";
    doble.disparar(selectPreset, "change");

    expect(selector.estado.preset).toBe("imperial");
    expect(selector.unidadResueltaDe("canal_temp").unidad.id).toBe("degF");
    expect(selector.unidadResueltaDe("canal_temp").capa).toBe(Capa.PRESET);
  });

  it("fijar la dimensión en el perfil gana al preset global", () => {
    const { selector, doble } = construir();
    let raiz = selector.elemento as unknown as NodoFalso;

    selectDeFila(raiz, "Global").value = "imperial";
    doble.disparar(selectDeFila(raiz, "Global"), "change");

    raiz = selector.elemento as unknown as NodoFalso;
    const selectDimension = selectDeFila(raiz, "Temperatura");
    selectDimension.value = "K";
    doble.disparar(selectDimension, "change");

    const r = selector.unidadResueltaDe("canal_temp");
    expect(r.capa).toBe(Capa.PERFIL);
    expect(r.unidad.id).toBe("K");
  });

  it("anular la unidad del canal gana a perfil y a preset", () => {
    const { selector, doble } = construir();
    let raiz = selector.elemento as unknown as NodoFalso;

    // Preset imperial, perfil K, y ahora una anulación de canal en degC.
    selectDeFila(raiz, "Global").value = "imperial";
    doble.disparar(selectDeFila(raiz, "Global"), "change");
    raiz = selector.elemento as unknown as NodoFalso;
    selectDeFila(raiz, "Temperatura").value = "K";
    doble.disparar(selectDeFila(raiz, "Temperatura"), "change");
    raiz = selector.elemento as unknown as NodoFalso;
    const selectCanal = selectDeFila(raiz, "Temp. refrigerante");
    selectCanal.value = "degC";
    doble.disparar(selectCanal, "change");

    const r = selector.unidadResueltaDe("canal_temp");
    expect(r.capa).toBe(Capa.CANAL);
    expect(r.unidad.id).toBe("degC");
  });

  it("volver a «heredar» en el canal descubre lo que hay debajo (perfil)", () => {
    const { selector, doble } = construir();
    let raiz = selector.elemento as unknown as NodoFalso;

    selectDeFila(raiz, "Temperatura").value = "K"; // perfil fija K
    doble.disparar(selectDeFila(raiz, "Temperatura"), "change");
    raiz = selector.elemento as unknown as NodoFalso;
    let selectCanal = selectDeFila(raiz, "Temp. refrigerante");
    selectCanal.value = "degC"; // anulación de canal
    doble.disparar(selectCanal, "change");

    raiz = selector.elemento as unknown as NodoFalso;
    selectCanal = selectDeFila(raiz, "Temp. refrigerante");
    selectCanal.value = ""; // "— heredar —"
    doble.disparar(selectCanal, "change");

    const r = selector.unidadResueltaDe("canal_temp");
    expect(r.capa).toBe(Capa.PERFIL);
    expect(r.unidad.id).toBe("K");
  });

  it("una preferencia de perfil en otra dimensión no afecta a canales de esta", () => {
    const { selector, doble } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    selectDeFila(raiz, "Temperatura").value = "K";
    doble.disparar(selectDeFila(raiz, "Temperatura"), "change");

    const r = selector.unidadResueltaDe("canal_lambda");
    expect(r.capa).toBe(Capa.PRESET);
    expect(r.unidad.id).toBe("lambda");
  });
});

describe("SelectorUnidad: de dónde viene la unidad efectiva (heredado vs. fijado)", () => {
  it("sin anulación, la nota dice «heredado: <explicación de la capa>»", () => {
    const { selector } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    const nota = notaDeFila(raiz, "Temp. refrigerante");
    expect(nota).toContain("heredado");
    expect(nota).toContain(explicacionDeCapa(Capa.PRESET));
  });

  it("con anulación, la nota dice «fijado aquí»", () => {
    const { selector, doble } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    const selectCanal = selectDeFila(raiz, "Temp. refrigerante");
    selectCanal.value = "degF";
    doble.disparar(selectCanal, "change");

    const nuevaRaiz = selector.elemento as unknown as NodoFalso;
    expect(notaDeFila(nuevaRaiz, "Temp. refrigerante")).toContain("fijado aquí");
  });

  it("la nota incluye los decimales de la unidad activa (docs/06 §6.10)", () => {
    const { selector } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    // El canal de lambda hereda "lambda", 3 decimales en la fixture.
    expect(notaDeFila(raiz, "Lambda banco 1")).toContain("3 decimales");
  });
});

describe("SelectorUnidad: callback de cambio", () => {
  it("emite `onCambio` con la unidad resuelta de TODOS los canales declarados", () => {
    const onCambio = vi.fn();
    const { selector, doble } = construir({ onCambio });
    const raiz = selector.elemento as unknown as NodoFalso;

    selectDeFila(raiz, "Global").value = "imperial";
    doble.disparar(selectDeFila(raiz, "Global"), "change");

    expect(onCambio).toHaveBeenCalledTimes(1);
    const cambio = onCambio.mock.calls[0]![0] as import("./selector-unidad.ts").CambioUnidad;
    expect(cambio.estado.preset).toBe("imperial");
    expect(cambio.resueltas.get("canal_temp")?.unidad.id).toBe("degF");
    expect(cambio.resueltas.get("canal_lambda")?.unidad.id).toBe("afr");
    // El canal de una dimensión no convertible también se resuelve (a su canónica).
    expect(cambio.resueltas.get("canal_ruido")?.unidad.id).toBe("dB");
  });

  it("no construir con onCambio no revienta al cambiar nada", () => {
    const { selector, doble } = construir();
    const raiz = selector.elemento as unknown as NodoFalso;
    expect(() => {
      selectDeFila(raiz, "Global").value = "imperial";
      doble.disparar(selectDeFila(raiz, "Global"), "change");
    }).not.toThrow();
    expect(selector.estado.preset).toBe("imperial");
  });
});

describe("SelectorUnidad: no toca datos", () => {
  it("`unidadResueltaDe` de un canal no declarado falla en vez de adivinar", () => {
    const { selector } = construir();
    expect(() => selector.unidadResueltaDe("fantasma")).toThrow(/fantasma/);
  });

  it("resolverUnidad importado sigue siendo la única lógica de precedencia (no hay una copia dentro del componente)", () => {
    const { selector } = construir();
    const catalogo = catalogoDePrueba();
    const directo = resolverUnidad({ dimensionId: "temperature", catalogo, preset: "metrico" });
    expect(selector.unidadResueltaDe("canal_temp")).toEqual(directo);
  });
});
