/**
 * Pruebas de `celdas.ts`: partición de campos y la regla dura de `docs/07`
 * §7.10, "celda vacía… NUNCA 0".
 */

import { describe, expect, it } from "vitest";

import { analizarCelda, analizarFila, analizarNumero, dividirCampos } from "./celdas.ts";

describe("dividirCampos", () => {
  it("sin comillas, es un split literal", () => {
    expect(dividirCampos("0.000,850,92.4", ",", null)).toEqual(["0.000", "850", "92.4"]);
  });

  it("caso español: delimitador ; con decimal coma no se parte por la coma", () => {
    expect(dividirCampos("0,050;92,4;32,6", ";", null)).toEqual(["0,050", "92,4", "32,6"]);
  });

  it("respeta un campo entrecomillado que contiene el delimitador", () => {
    expect(dividirCampos('1,"Sensor, roto",3', ",", '"')).toEqual(["1", "Sensor, roto", "3"]);
  });

  it("comilla doblada dentro de un campo entrecomillado", () => {
    expect(dividirCampos('1,"Sensor ""A""",3', ",", '"')).toEqual(["1", 'Sensor "A"', "3"]);
  });

  it("escape por barra invertida dentro de comillas", () => {
    expect(dividirCampos('1,"Sensor \\"A\\"",3', ",", '"')).toEqual(["1", 'Sensor "A"', "3"]);
  });

  it("delimitador multicarácter (tabulación representada como texto)", () => {
    expect(dividirCampos("a\t\tb", "\t\t", null)).toEqual(["a", "b"]);
  });
});

describe("analizarNumero", () => {
  it("decimal punto: un separador de miles con coma no rompe el número", () => {
    expect(analizarNumero("1,234.5", ".")).toBe(1234.5);
  });

  it("decimal coma: el caso español típico", () => {
    expect(analizarNumero("1.234,5", ",")).toBe(1234.5);
    expect(analizarNumero("92,4", ",")).toBeCloseTo(92.4);
  });

  it("texto libre no es un número: null, no NaN y no 0", () => {
    expect(analizarNumero("Bootmode Reason", ".")).toBeNull();
    expect(analizarNumero("", ".")).toBeNull();
  });

  it("negativos y notación científica", () => {
    expect(analizarNumero("-0.5", ".")).toBe(-0.5);
    expect(analizarNumero("1e3", ".")).toBe(1000);
  });
});

describe("analizarCelda: la regla de docs/07 §7.10", () => {
  const opciones = { decimal: "." as const };

  it("celda vacía -> hueco, nunca 0", () => {
    const celda = analizarCelda("", opciones.decimal);
    expect(celda).toEqual({ tipo: "hueco" });
  });

  it("solo espacios -> hueco", () => {
    expect(analizarCelda("   ", opciones.decimal)).toEqual({ tipo: "hueco" });
  });

  it.each(["NaN", "nan", "NULL", "null", "---", "N/A", "n/a", "#N/A", "inf", "-inf"])(
    "centinela textual %s -> hueco",
    (centinela) => {
      expect(analizarCelda(centinela, opciones.decimal)).toEqual({ tipo: "hueco" });
    },
  );

  it("un número válido -> numero, con el texto original conservado", () => {
    expect(analizarCelda("92.4", ".")).toEqual({ tipo: "numero", texto: "92.4", valor: 92.4 });
  });

  it("un número con coma decimal (caso español) -> numero", () => {
    expect(analizarCelda("92,4", ",")).toEqual({ tipo: "numero", texto: "92,4", valor: 92.4 });
  });

  it("un enum de texto libre -> texto, no un hueco y no un número", () => {
    expect(analizarCelda("Idle", ".")).toEqual({ tipo: "texto", texto: "Idle" });
  });

  it("cero de verdad es un número, distinto de un hueco", () => {
    const cero = analizarCelda("0", ".");
    const hueco = analizarCelda("", ".");
    expect(cero).toEqual({ tipo: "numero", texto: "0", valor: 0 });
    expect(cero).not.toEqual(hueco);
  });

  it("acepta un catálogo de centinelas distinto del de omisión", () => {
    const propio = new Set(["DESCONECTADO"]);
    expect(analizarCelda("desconectado", ".", propio)).toEqual({ tipo: "hueco" });
    // Y ya no reconoce los de la lista por omisión.
    expect(analizarCelda("NULL", ".", propio)).toEqual({ tipo: "texto", texto: "NULL" });
  });
});

describe("analizarFila: la unidad de trabajo de la previsualización viva", () => {
  it("caso español completo: ; con coma decimal, con un hueco en medio", () => {
    const fila = analizarFila("0,050;;32,6", { delimitador: ";", comilla: null, decimal: "," });
    expect(fila).toEqual([
      { tipo: "numero", texto: "0,050", valor: 0.05 },
      { tipo: "hueco" },
      { tipo: "numero", texto: "32,6", valor: 32.6 },
    ]);
  });

  it("re-particiona al instante si cambia el delimitador propuesto", () => {
    const linea = "0.000,850,92.4";
    const conComa = analizarFila(linea, { delimitador: ",", comilla: null, decimal: "." });
    const conPuntoYComa = analizarFila(linea, { delimitador: ";", comilla: null, decimal: "." });
    expect(conComa).toHaveLength(3);
    // Con ; como delimitador, la línea entera es un solo campo de texto (no
    // tiene forma numérica con las comas dentro), y por tanto UNA celda.
    expect(conPuntoYComa).toHaveLength(1);
    expect(conPuntoYComa[0]).toEqual({ tipo: "texto", texto: linea });
  });
});

describe("analizarNumero: la agrupación de miles no se inventa", () => {
  /*
   * Esta suite existe porque el fallo que cubre ya se pagó DOS veces: una en
   * `dlv_core.formatos.decimal_csv`, cuyo docstring lo documenta, y otra aquí, al
   * portar aquel módulo «de forma simplificada». La simplificación era justo la
   * parte que importaba.
   *
   * Quitar el carácter contrario y dejar que `Number` opine convierte `0,000` con
   * punto decimal en 0 y `12,34` en 1234. Es un error de factor 100 que no lanza
   * nada, que no se ve en la pantalla, y que además rompe lo que el asistente
   * tiene que medir: si las dos interpretaciones explican el fichero entero, la
   * verificación cruzada del separador decimal no distingue nada.
   */

  it("acepta la agrupación de verdad: grupos de tres empezando por 1-9", () => {
    expect(analizarNumero("1,234", ".")).toBe(1234);
    expect(analizarNumero("1,234.56", ".")).toBe(1234.56);
    expect(analizarNumero("1,000,000.00", ".")).toBe(1000000);
    expect(analizarNumero("1.234,56", ",")).toBe(1234.56);
  });

  it("rechaza la agrupación imposible en vez de inventar un número", () => {
    // El caso que nombra el docstring del módulo Python.
    expect(analizarNumero("0,000", ".")).toBeNull();
    // Un decimal europeo leído con punto decimal: 3,72 NO es 372.
    expect(analizarNumero("3,72", ".")).toBeNull();
    expect(analizarNumero("12,34", ".")).toBeNull();
    expect(analizarNumero("1,23,456", ".")).toBeNull();
    // Y simétrico con la coma decimal.
    expect(analizarNumero("0.000", ",")).toBeNull();
    expect(analizarNumero("3.72", ",")).toBeNull();
  });

  it("un cero de verdad sigue siendo cero, y el texto libre sigue siendo null", () => {
    /* La corrección no puede haberse llevado por delante el caso normal: un 0
       real es un dato, y confundirlo con «sin dato» es la otra mitad de la regla
       de F1-03. */
    expect(analizarNumero("0", ".")).toBe(0);
    expect(analizarNumero("0.0", ".")).toBe(0);
    expect(analizarNumero("0,0", ",")).toBe(0);
    expect(analizarNumero("abc", ".")).toBeNull();
    expect(analizarNumero("", ".")).toBeNull();
  });

  it("coincide con el patrón de `decimal_csv` en notación científica", () => {
    expect(analizarNumero("1.5e-3", ".")).toBe(0.0015);
    expect(analizarNumero("1,5e-3", ",")).toBe(0.0015);
    expect(analizarNumero("1,5e-3", ".")).toBeNull();
  });
});
