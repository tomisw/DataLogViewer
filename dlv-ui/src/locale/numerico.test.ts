/**
 * Pruebas del formateo numérico con locale (F1-32).
 *
 * El caso que da sentido a este módulo está en `describe("la trampa de leer un
 * número en el locale equivocado")`: `1.234` significa mil doscientos treinta y
 * cuatro en español y uno coma doscientos treinta y cuatro en inglés. En una
 * tabla de tuning eso no es una errata de estilo, es una decisión mal tomada.
 *
 * Y el segundo bloque que importa es `describe("un solo formateador")`: este
 * módulo existe porque había cuatro implementaciones que no coincidían entre
 * sí, y lo que impide que vuelvan a divergir es que las capas de arriba den
 * exactamente el mismo texto para el mismo número.
 */

import { describe, expect, it } from "vitest";

import { formatearNumero as formatearEnEje } from "../ejes/formato.ts";
import { formatearNumero, separadorDecimal } from "./numerico.ts";

describe("separador decimal y locale", () => {
  it("español usa coma", () => {
    expect(formatearNumero(1.5, 1)).toBe("1,5");
    expect(formatearNumero(0.02, 2)).toBe("0,02");
    expect(separadorDecimal("es")).toBe(",");
  });

  it("inglés usa punto", () => {
    expect(formatearNumero(1.5, 1, { locale: "en" })).toBe("1.5");
    expect(formatearNumero(0.02, 2, { locale: "en" })).toBe("0.02");
    expect(separadorDecimal("en")).toBe(".");
  });

  it("español es el locale por omisión", () => {
    expect(formatearNumero(1.5, 1)).toBe(formatearNumero(1.5, 1, { locale: "es" }));
  });
});

describe("la trampa de leer un número en el locale equivocado", () => {
  it("mil doscientos treinta y cuatro no se escribe igual en los dos", () => {
    // Con agrupación, `1.234` en español y `1,234` en inglés son EL MISMO
    // número; leídos con el locale contrario, uno vale mil y el otro vale uno.
    expect(formatearNumero(1234, 0, { agrupar: true })).toBe("1.234");
    expect(formatearNumero(1234, 0, { locale: "en", agrupar: true })).toBe("1,234");
  });

  it("y uno coma doscientos treinta y cuatro, tampoco", () => {
    expect(formatearNumero(1.234, 3)).toBe("1,234");
    expect(formatearNumero(1.234, 3, { locale: "en" })).toBe("1.234");
  });

  it("por eso NO se agrupa por omisión", () => {
    // La colisión de arriba solo existe si se agrupa. Sin agrupar, el punto y
    // la coma solo pueden significar «decimal», y una lectura cruzada de
    // locales cambia como mucho la elegancia, nunca la magnitud. En un visor
    // de datos de motor casi todo tiene entre tres y cinco cifras, así que
    // agrupar aporta poco y arriesga bastante.
    expect(formatearNumero(1234, 0)).toBe("1234");
    expect(formatearNumero(40000, 0)).toBe("40000");
    expect(formatearNumero(40000, 0, { locale: "en" })).toBe("40000");
  });

  it("pero se puede pedir cuando el locale del lector es conocido", () => {
    expect(formatearNumero(40000, 0, { agrupar: true })).toBe("40.000");
  });
});

describe("decimales", () => {
  it("son exactamente los que se piden, ni uno más ni uno menos", () => {
    // Ni uno menos: es la diferencia entre λ 0,995 y destruir esa información
    // como λ 1,0 (docs/06 §6.10). Ni uno más: 250 kPa no son 250,000 kPa.
    expect(formatearNumero(0.995, 3)).toBe("0,995");
    expect(formatearNumero(250.4, 0)).toBe("250");
    expect(formatearNumero(4, 2)).toBe("4,00");
  });

  it("redondea, no trunca", () => {
    expect(formatearNumero(42.7, 0)).toBe("43");
    expect(formatearNumero(4.5678, 2)).toBe("4,57");
  });

  it("un número de decimales absurdo se trata como cero en vez de reventar", () => {
    expect(formatearNumero(3.7, -1)).toBe("4");
    expect(formatearNumero(3.7, Number.NaN)).toBe("4");
  });
});

describe("el cero negativo", () => {
  it("no se enseña con signo", () => {
    // Un usuario que lee `-0,0` piensa que ese signo significa algo. No
    // significa nada.
    expect(formatearNumero(-0, 2)).toBe("0,00");
    expect(formatearNumero(-0, 0)).toBe("0");
  });

  it("tampoco cuando viene de un negativo pequeño que redondea a cero", () => {
    // Este es el caso que aparece de verdad: un tick en -0,0001 de un eje que
    // cruza el cero. Comprobar solo `Object.is(valor, -0)` lo dejaría pasar.
    expect(formatearNumero(-0.0001, 2)).toBe("0,00");
    expect(formatearNumero(-0.4, 0)).toBe("0");
  });

  it("pero un negativo de verdad conserva su signo", () => {
    expect(formatearNumero(-12.345, 1)).toBe("-12,3");
    expect(formatearNumero(-0.01, 2)).toBe("-0,01");
  });
});

describe("un solo formateador", () => {
  it("el eje y el módulo de locale dan el mismo texto para el mismo número", () => {
    // Es lo que impide que vuelvan a divergir. Antes de unificarlos, la tabla
    // del cursor enseñaba `101.2` y el eje de al lado `101,2`, en la misma
    // ventana: ninguna prueba se ponía roja y el usuario lo veía.
    for (const [valor, decimales] of [
      [101.23, 1],
      [4.5678, 2],
      [-0.0001, 2],
      [40000, 0],
      [0.995, 3],
    ] as const) {
      expect(formatearEnEje(valor, decimales)).toBe(formatearNumero(valor, decimales));
    }
  });
});
