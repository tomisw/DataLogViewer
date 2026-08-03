/**
 * Pruebas de precedencia y formateo (F1-31).
 *
 * Es el riesgo real de esta tarea, tal y como lo pide el encargo: la
 * precedencia de los tres niveles (canal > perfil > preset > canónica) y el
 * formateo con los decimales de cada unidad, incluida la trampa concreta que
 * `docs/06` §6.10 señala — λ con un decimal de menos destruye la información.
 */

import { describe, expect, it } from "vitest";

import { catalogoDePrueba } from "./fixtures-catalogo.ts";
import { buscarDimension, buscarUnidad, ErrorDeUnidad, formatearValor, resolverUnidad } from "./resolucion.ts";
import { Capa } from "./tipos.ts";

describe("resolverUnidad: precedencia de docs/06 §6.9", () => {
  const catalogo = catalogoDePrueba();

  it("sin nada más, cae a la unidad canónica", () => {
    // La dimensión mixture_ratio no está en el preset "si".
    const r = resolverUnidad({ dimensionId: "mixture_ratio", catalogo, preset: "si" });
    expect(r.capa).toBe(Capa.CANONICA);
    expect(r.unidad.id).toBe("lambda");
  });

  it("el preset activo decide si no hay nada más específico", () => {
    const r = resolverUnidad({ dimensionId: "temperature", catalogo, preset: "imperial" });
    expect(r.capa).toBe(Capa.PRESET);
    expect(r.unidad.id).toBe("degF");
  });

  it("sin pasar `preset`, se usa el preset por omisión del catálogo", () => {
    const r = resolverUnidad({ dimensionId: "temperature", catalogo });
    expect(r.capa).toBe(Capa.PRESET);
    expect(r.unidad.id).toBe("degC"); // "metrico" es el por_omision de la fixture
  });

  it("la preferencia de perfil gana al preset", () => {
    const r = resolverUnidad({
      dimensionId: "temperature",
      catalogo,
      preset: "imperial",
      preferenciasPerfil: { temperature: "K" },
    });
    expect(r.capa).toBe(Capa.PERFIL);
    expect(r.unidad.id).toBe("K");
  });

  it("la anulación de canal gana a todo lo demás", () => {
    const r = resolverUnidad({
      dimensionId: "temperature",
      catalogo,
      preset: "imperial",
      preferenciasPerfil: { temperature: "K" },
      anulacionCanal: "degC",
    });
    expect(r.capa).toBe(Capa.CANAL);
    expect(r.unidad.id).toBe("degC");
  });

  it("la preferencia de perfil de OTRA dimensión no interfiere", () => {
    const r = resolverUnidad({
      dimensionId: "pressure",
      catalogo,
      preset: "imperial",
      preferenciasPerfil: { temperature: "K" },
    });
    expect(r.capa).toBe(Capa.PRESET);
    expect(r.unidad.id).toBe("psi");
  });

  it("dimensión desconocida lanza ErrorDeUnidad", () => {
    expect(() => resolverUnidad({ dimensionId: "fantasma", catalogo })).toThrow(ErrorDeUnidad);
    expect(() => resolverUnidad({ dimensionId: "fantasma", catalogo })).toThrow(/dimensión desconocida/);
  });

  it("preset desconocido lanza ErrorDeUnidad", () => {
    expect(() => resolverUnidad({ dimensionId: "temperature", catalogo, preset: "fantasma" })).toThrow(
      /preset desconocido/,
    );
  });

  it("unidad de anulación que no existe en la dimensión lanza ErrorDeUnidad", () => {
    expect(() =>
      resolverUnidad({ dimensionId: "temperature", catalogo, anulacionCanal: "psi" }),
    ).toThrow(/no es una unidad de la dimensión 'temperature'/);
  });

  it("unidad de preferencia de perfil que no existe lanza ErrorDeUnidad", () => {
    expect(() =>
      resolverUnidad({
        dimensionId: "temperature",
        catalogo,
        preferenciasPerfil: { temperature: "bar" },
      }),
    ).toThrow(ErrorDeUnidad);
  });
});

describe("buscarDimension / buscarUnidad", () => {
  const catalogo = catalogoDePrueba();

  it("buscarUnidad resuelve alias", () => {
    const dimension = buscarDimension(catalogo, "pressure");
    // Añadimos un alias ad-hoc para la prueba sin tocar la fixture del catálogo.
    const conAlias = {
      ...dimension,
      unidades: dimension.unidades.map((u) => (u.id === "kPa" ? { ...u, alias: ["kpa"] } : u)),
    };
    expect(buscarUnidad(conAlias, "kpa").id).toBe("kPa");
  });

  it("buscarUnidad lanza con las unidades disponibles en el mensaje", () => {
    const dimension = buscarDimension(catalogo, "pressure");
    expect(() => buscarUnidad(dimension, "atm")).toThrow(/kPa, bar, psi/);
  });
});

describe("formatearValor: decimales por unidad (docs/06 §6.10)", () => {
  const catalogo = catalogoDePrueba();
  const lambda = buscarUnidad(buscarDimension(catalogo, "mixture_ratio"), "lambda");
  const degC = buscarUnidad(buscarDimension(catalogo, "temperature"), "degC");
  const kPa = buscarUnidad(buscarDimension(catalogo, "pressure"), "kPa");

  it("λ con sus 3 decimales no pierde información (la trampa exacta de §6.10)", () => {
    expect(formatearValor(lambda, 0.995)).toBe("0,995 λ");
  });

  it("si a λ se le dieran los decimales equivocados (1), sí la perdería — demuestra por qué son un dato de entrada", () => {
    const lambdaMalConfigurada = { ...lambda, decimales: 1 };
    expect(formatearValor(lambdaMalConfigurada, 0.995)).toBe("1,0 λ");
  });

  it("respeta 0 decimales (kPa)", () => {
    expect(formatearValor(kPa, 250.4)).toBe("250 kPa");
  });

  it("usa coma decimal por omisión (locale español, docs/06 §6.10)", () => {
    expect(formatearValor(degC, 93.2)).toBe("93,2 °C");
  });

  it("admite punto decimal si se pide explícitamente", () => {
    expect(formatearValor(degC, 93.2, ".")).toBe("93.2 °C");
  });

  it("una unidad sin etiqueta (fracción adimensional) no deja un espacio colgando", () => {
    const sinEtiqueta = { id: "fraccion", etiqueta: "", decimales: 4 };
    expect(formatearValor(sinEtiqueta, 0.5)).toBe("0,5000");
  });
});
