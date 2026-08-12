/**
 * Partición de una línea en campos y análisis de cada celda, para la
 * previsualización viva del paso 1 y el paso 3 del asistente (`docs/07` §7.4
 * y §7.10).
 *
 * `dividirCampos` ES el mismo algoritmo que `dlv_core.formatos.sondeo.
 * dividir_campos` (comprobado línea a línea contra `dlv-core/src/dlv_core/
 * formatos/sondeo.py`), portado a propósito y no reimplementado a ojo: la
 * previsualización necesita re-partir las filas de muestra CADA VEZ que el
 * usuario mueve el desplegable de delimitador o el de comillas, y hacerlo por
 * HTTP en cada tecla rompería la promesa de "al instante" de §7.8. Partir
 * texto no es la parte de FG-01/FG-02 que hace falta reservar al backend
 * -esa es la DETECCIÓN (qué delimitador puntúa mejor), que sigue viviendo
 * solo en `dlv_core.formatos.sondeo.sondear_csv` y no se duplica aquí (ver
 * `puerto.ts`). Aquí solo se aplica la elección YA hecha -por el sondeo o por
 * el usuario- a las filas de muestra que ya están en memoria.
 *
 * `analizarCelda` es la otra mitad, y la que hace cumplir la regla que más
 * fácil es romper en una tabla de previsualización: `docs/07` §7.10 dice
 * "celda vacía… NUNCA 0", y `tipos.ts#CeldaPrevia` ya lo hace irrepresentable
 * a nivel de tipos (no hay un `numero: 0` que pueda confundirse con un hueco).
 * Esta función es la que decide, para un texto crudo, a cuál de las tres
 * formas de `CeldaPrevia` corresponde.
 */

import type { CeldaPrevia } from "./tipos.ts";

/**
 * Valores centinela de "sin dato" listados en `docs/07` §7.10.
 *
 * NO es el catálogo real: los centinelas de verdad (`centinelas_texto` /
 * `centinelas_i32`) viven en `data/units.toml` y los resuelve
 * `dlv_core.formatos.valores_csv.analizar_columna` contra el catálogo de cada
 * canal (un centinela de desbordamiento es un ENTERO concreto por dimensión,
 * no una palabra). Esta lista es solo el subconjunto textual, universal y sin
 * parámetros que §7.10 nombra explícitamente, para que la previsualización
 * pueda marcar huecos ANTES de que exista un endpoint que sirva el catálogo
 * completo (ver la nota de `puerto.ts`). Comparación insensible a mayúsculas
 * porque los exportadores no son consistentes con el suyo.
 */
export const VALORES_AUSENTES_POR_OMISION: ReadonlySet<string> = new Set([
  "NAN",
  "INF",
  "-INF",
  "+INF",
  "#N/A",
  "NULL",
  "---",
  "N/A",
]);

function normalizarCentinela(texto: string): string {
  return texto.trim().toUpperCase();
}

/**
 * Parte una línea en campos, respetando comillas y sus escapes.
 *
 * Espejo de `dividir_campos` (Python): comilla `null` = partición literal por
 * `split`; con comilla, reconoce el escape por barra invertida (`\"`) y la
 * comilla doblada (`""`) exactamente igual que el original, campo a campo.
 */
export function dividirCampos(linea: string, delimitador: string, comilla: string | null): string[] {
  if (comilla === null) return linea.split(delimitador);
  if (delimitador === "") return [linea];

  const campos: string[] = [];
  let actual = "";
  let dentro = false;
  let i = 0;
  const n = linea.length;

  while (i < n) {
    const c = linea[i];
    if (c === "\\" && dentro && i + 1 < n) {
      actual += linea[i + 1];
      i += 2;
      continue;
    }
    if (c === comilla) {
      if (dentro && linea[i + 1] === comilla) {
        actual += comilla;
        i += 2;
        continue;
      }
      dentro = !dentro;
      i += 1;
      continue;
    }
    if (!dentro && linea.startsWith(delimitador, i)) {
      campos.push(actual);
      actual = "";
      i += delimitador.length;
      continue;
    }
    actual += c;
    i += 1;
  }
  campos.push(actual);
  return campos;
}

/**
 * La forma que un lector de CSV con este separador decimal sabe leer, y solo esa.
 *
 * Espejo FIEL de `_patron_numerico` de `dlv_core.formatos.decimal_csv`. La
 * agrupación con el carácter contrario se acepta —`1,234.56` con punto decimal es
 * legítimo— pero solo en grupos de tres que empiezan por 1-9, que es la única
 * forma que produce un agrupador de verdad.
 *
 * Esa restricción es el módulo entero. Sin ella, quitar el carácter contrario y
 * dejar que `Number` opine convierte `0,000` con punto decimal en `0` y `12,34`
 * en `1234`: un error de factor 100 que no lanza nada y que no se nota mirando la
 * pantalla. El módulo Python lo documenta como una trampa que ya pagó una vez, y
 * esta función la volvió a pagar hasta que se portó el patrón de verdad. Un lector
 * de CSV real con punto decimal NO lee `0,000` como un número: se para en la coma.
 */
function patronNumerico(decimal: "." | ","): RegExp {
  const d = decimal === "." ? "\\." : ",";
  const g = decimal === "." ? "," : "\\.";
  return new RegExp(`^[+-]?([1-9]\\d{0,2}(${g}\\d{3})+|\\d+)(${d}\\d+)?([eE][+-]?\\d+)?$`);
}

/** Notación científica con el separador que toque: `1.5e-3`. */
function patronCientifico(decimal: "." | ","): RegExp {
  const d = decimal === "." ? "\\." : ",";
  return new RegExp(`^[+-]?\\d+(${d}\\d+)?[eE][+-]?\\d+$`);
}

const PATRONES: Record<"." | ",", RegExp> = {
  ".": patronNumerico("."),
  ",": patronNumerico(","),
};
const CIENTIFICOS: Record<"." | ",", RegExp> = {
  ".": patronCientifico("."),
  ",": patronCientifico(","),
};

/**
 * Interpreta un texto como número, con el separador decimal indicado.
 *
 * Devuelve `null`, nunca `NaN` ni `0`, cuando el texto no tiene la forma que un
 * lector con ese separador aceptaría — así ni una celda de texto libre ni una
 * agrupación imposible se cuelan como número.
 */
export function analizarNumero(textoBruto: string, decimal: "." | ","): number | null {
  const texto = textoBruto.trim();
  if (texto === "") return null;
  if (!PATRONES[decimal].test(texto) && !CIENTIFICOS[decimal].test(texto)) return null;
  const agrupador = decimal === "." ? "," : ".";
  const sinMiles = texto.split(agrupador).join("");
  const normalizado = decimal === "." ? sinMiles : sinMiles.replace(",", ".");
  const numero = Number(normalizado);
  return Number.isFinite(numero) ? numero : null;
}

/**
 * Clasifica una celda ya partida: hueco (vacía o centinela), número, o texto.
 *
 * El orden importa: primero se comprueba "sin dato" (regla dura de §7.10),
 * y solo si no lo es se intenta el número. Un centinela como `NULL` tiene
 * forma de texto y nunca de número, así que el orden no cambia el resultado
 * hoy, pero deja explícito cuál de las dos reglas manda si algún día un
 * centinela numérico (p. ej. un desbordamiento de `2147483647`) entrara por
 * aquí: eso exige el catálogo real (ver la nota del módulo) y no esta lista.
 */
export function analizarCelda(
  textoBruto: string,
  decimal: "." | "," = ".",
  centinelas: ReadonlySet<string> = VALORES_AUSENTES_POR_OMISION,
): CeldaPrevia {
  const texto = textoBruto.trim();
  if (texto === "" || centinelas.has(normalizarCentinela(texto))) {
    return { tipo: "hueco" };
  }
  const numero = analizarNumero(texto, decimal);
  if (numero !== null) {
    return { tipo: "numero", texto: textoBruto, valor: numero };
  }
  return { tipo: "texto", texto: textoBruto };
}

export interface OpcionesAnalisisFila {
  readonly delimitador: string;
  readonly comilla: string | null;
  readonly decimal: "." | ",";
  readonly centinelas?: ReadonlySet<string>;
}

/** Parte y clasifica una línea completa: la unidad de trabajo de la previsualización viva. */
export function analizarFila(linea: string, opciones: OpcionesAnalisisFila): readonly CeldaPrevia[] {
  return dividirCampos(linea, opciones.delimitador, opciones.comilla).map((campo) =>
    analizarCelda(campo, opciones.decimal, opciones.centinelas),
  );
}
