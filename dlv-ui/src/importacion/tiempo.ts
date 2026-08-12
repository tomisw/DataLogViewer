/**
 * Resumen en vivo del paso 2 del asistente: duración, número de muestras y
 * tasa media (`docs/07` §7.8, paso 2: "para que un valor absurdo se vea al
 * instante").
 *
 * QUÉ SE REIMPLEMENTA AQUÍ Y QUÉ NO
 * ==================================
 * Interpretar un valor crudo de columna de tiempo en segundos es
 * `dlv_core.formatos.tiempo_csv.parsear_instante`, y ESE parseo se porta aquí
 * a propósito, por el mismo motivo que `celdas.ts` porta `dividir_campos`:
 * tiene que poder recalcularse en cada tecla que cambia la clase de tiempo o
 * la columna elegida, sobre las pocas filas de muestra que ya están en
 * memoria, sin una ida y vuelta HTTP (§7.8 pide "al instante").
 *
 * Lo que NO se reimplementa es la CLASIFICACIÓN — decidir qué clase de tiempo
 * es más probable mirando la columna entera (`_clase_de_columna`,
 * `detectar_columna_de_tiempo`) sigue siendo trabajo exclusivo del sondeo en
 * `dlv-core`, servido por el endpoint que falta (ver `puerto.ts`). Este
 * módulo no propone nada: solo mide la consecuencia de la clase que YA está
 * propuesta o ya ha confirmado el usuario, sobre la muestra que hay.
 *
 * Por eso el resultado siempre dice, explícitamente, si la duración es del
 * FICHERO COMPLETO o solo una ESTIMACIÓN sobre la previsualización — nunca
 * se finge la precisión que `docs/07` §7.5 prohíbe fingir para el propio eje
 * de tiempo, y la misma prohibición aplica al resumen que lo describe.
 */

import type { ClaseDeTiempo } from "./tipos.ts";
import { necesitaFrecuenciaDelUsuario } from "./tipos.ts";

export class ErrorDeTiempoPrevio extends Error {}

/**
 * `18:30:35.506` → 66 635,506 s desde la medianoche. Espejo de
 * `tiempo_csv._hora_a_segundos`: valida los rangos, no solo la forma, porque
 * `25:99:99` encaja en una expresión regular ingenua y no es una hora.
 */
function horaDelDiaASegundos(texto: string, decimal: "." | ","): number {
  const normalizado = decimal === "," ? texto.replace(",", ".") : texto;
  const m = /^(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$/.exec(normalizado.trim());
  if (m === null) throw new ErrorDeTiempoPrevio(`'${texto}' no tiene la forma HH:MM:SS[.fff]`);
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  const ss = Number(m[3]);
  if (mm > 59 || ss >= 60) {
    throw new ErrorDeTiempoPrevio(`'${texto}' está fuera de rango: minutos o segundos > 59`);
  }
  return hh * 3600 + mm * 60 + ss;
}

function numeroConDecimal(texto: string, decimal: "." | ","): number {
  const normalizado = decimal === "," ? texto.replace(",", ".") : texto;
  const numero = Number(normalizado.trim());
  if (!Number.isFinite(numero)) {
    throw new ErrorDeTiempoPrevio(`'${texto}' no es un número`);
  }
  return numero;
}

/**
 * Un valor crudo de la columna de tiempo -> segundos. Espejo reducido de
 * `parsear_instante`: cubre las clases que dependen solo de la propia celda
 * (`hora_del_dia`, `relativo`, `epoch_*`, `contador_de_muestras` con
 * frecuencia). `iso8601` se apoya en `Date.parse`, que entiende el mismo
 * subconjunto de ISO-8601 que trae un exportador real; `fecha_y_hora_
 * separadas` exige combinar dos columnas y no se resuelve aquí con un solo
 * valor (ver `calcularResumenTiempo`, que la trata aparte).
 */
export function instanteEnSegundos(
  valor: string,
  clase: ClaseDeTiempo,
  opciones: { readonly decimal: "." | ","; readonly factorASegundos: number; readonly frecuenciaHz?: number | null },
): number {
  const texto = valor.trim();
  switch (clase) {
    case "hora_del_dia":
      return horaDelDiaASegundos(texto, opciones.decimal);
    case "iso8601": {
      const ms = Date.parse(texto.replace(",", "."));
      if (Number.isNaN(ms)) throw new ErrorDeTiempoPrevio(`'${valor}' no es una fecha ISO-8601 válida`);
      return ms / 1000;
    }
    case "epoch_segundos":
    case "epoch_milisegundos":
    case "relativo":
      return numeroConDecimal(texto, opciones.decimal) * opciones.factorASegundos;
    case "contador_de_muestras": {
      const frecuencia = opciones.frecuenciaHz;
      if (frecuencia === null || frecuencia === undefined || frecuencia <= 0) {
        throw new ErrorDeTiempoPrevio(
          "un contador de muestras no es tiempo hasta que se declara la frecuencia",
        );
      }
      return numeroConDecimal(texto, opciones.decimal) / frecuencia;
    }
    case "fecha_y_hora_separadas":
      throw new ErrorDeTiempoPrevio(
        "fecha_y_hora_separadas combina dos columnas: usa calcularResumenTiempo, no esta función",
      );
    case "ausente":
      throw new ErrorDeTiempoPrevio("no hay columna de tiempo: no hay valor que interpretar");
  }
}

export interface ResumenTiempo {
  /** Cuántas filas de la MUESTRA se pudieron interpretar. */
  readonly muestras: number;
  readonly pasoMedianoS: number | null;
  readonly frecuenciaHz: number | null;
  /** Duración; `null` si no se pudo calcular ningún paso. */
  readonly duracionS: number | null;
  /**
   * `false` cuando `duracionS` es sobre el fichero completo (se dio
   * `muestrasTotales`); `true` cuando es una extrapolación desde la muestra
   * de previsualización nada más. `docs/07` §7.5: nunca se finge precisión
   * que no existe, y este campo es cómo la interfaz lo dice sin ambigüedad.
   */
  readonly esEstimacion: boolean;
  readonly avisos: readonly string[];
}

function mediana(valores: readonly number[]): number | null {
  if (valores.length === 0) return null;
  const ordenados = [...valores].sort((a, b) => a - b);
  const mitad = Math.floor(ordenados.length / 2);
  return ordenados.length % 2 === 0
    ? (ordenados[mitad - 1]! + ordenados[mitad]!) / 2
    : ordenados[mitad]!;
}

export interface ParametrosResumenTiempo {
  readonly clase: ClaseDeTiempo;
  /** Los valores crudos de la columna de tiempo, en el orden del fichero. */
  readonly valoresBrutos: readonly string[];
  readonly decimal: "." | ",";
  readonly factorASegundos?: number;
  /** Obligatorio si `necesitaFrecuenciaDelUsuario(clase)`. */
  readonly frecuenciaHz?: number | null;
  /** Si se conoce el total de filas del fichero (no solo la muestra), la
   * duración se calcula sobre el total y `esEstimacion` sale en `false`. */
  readonly muestrasTotales?: number | null;
}

/**
 * El resumen que pide `docs/07` §7.8 paso 2: duración, muestras y tasa media,
 * recalculado sobre lo que haya en memoria cada vez que cambia la propuesta.
 */
export function calcularResumenTiempo(parametros: ParametrosResumenTiempo): ResumenTiempo {
  const avisos: string[] = [];
  const factorASegundos = parametros.factorASegundos ?? 1;

  if (necesitaFrecuenciaDelUsuario(parametros.clase)) {
    const frecuencia = parametros.frecuenciaHz;
    if (frecuencia === null || frecuencia === undefined || frecuencia <= 0) {
      avisos.push(
        "sin columna de tiempo fiable: declara la frecuencia de muestreo para poder " +
          "calcular la duración (el eje quedará marcado como tiempo sintético, docs/07 §7.5)",
      );
      return {
        muestras: parametros.valoresBrutos.length,
        pasoMedianoS: null,
        frecuenciaHz: null,
        duracionS: null,
        esEstimacion: true,
        avisos,
      };
    }
    const muestras = parametros.muestrasTotales ?? parametros.valoresBrutos.length;
    return {
      muestras,
      pasoMedianoS: 1 / frecuencia,
      frecuenciaHz: frecuencia,
      duracionS: muestras > 0 ? (muestras - 1) / frecuencia : 0,
      esEstimacion: parametros.muestrasTotales === undefined || parametros.muestrasTotales === null,
      avisos,
    };
  }

  if (parametros.clase === "fecha_y_hora_separadas") {
    avisos.push("fecha + hora combinadas: previsualiza tras combinar las dos columnas");
    return { muestras: 0, pasoMedianoS: null, frecuenciaHz: null, duracionS: null, esEstimacion: true, avisos };
  }

  const segundos: number[] = [];
  let descartadas = 0;
  for (const bruto of parametros.valoresBrutos) {
    if (bruto.trim() === "") continue;
    try {
      segundos.push(
        instanteEnSegundos(bruto, parametros.clase, {
          decimal: parametros.decimal,
          factorASegundos,
          frecuenciaHz: parametros.frecuenciaHz,
        }),
      );
    } catch {
      descartadas += 1;
    }
  }
  if (descartadas > 0) {
    avisos.push(`${descartadas} de ${parametros.valoresBrutos.length} valores de la muestra no se pudieron interpretar como ${parametros.clase}`);
  }

  const pasos: number[] = [];
  for (let i = 1; i < segundos.length; i += 1) {
    const paso = segundos[i]! - segundos[i - 1]!;
    if (paso > 0) pasos.push(paso);
  }
  if (pasos.length < segundos.length - 1 && segundos.length > 1) {
    avisos.push("hay marcas de tiempo no crecientes en la muestra (docs/07 §7.10): se ignoran para la tasa media");
  }

  const pasoMedianoS = mediana(pasos);
  const frecuenciaHz = pasoMedianoS !== null && pasoMedianoS > 0 ? 1 / pasoMedianoS : null;
  const muestrasTotales = parametros.muestrasTotales ?? null;
  const muestras = muestrasTotales ?? segundos.length;
  const duracionS =
    muestrasTotales !== null
      ? pasoMedianoS !== null
        ? (muestrasTotales - 1) * pasoMedianoS
        : null
      : segundos.length > 0
        ? segundos[segundos.length - 1]! - segundos[0]!
        : null;

  return {
    muestras,
    pasoMedianoS,
    frecuenciaHz,
    duracionS,
    esEstimacion: muestrasTotales === null,
    avisos,
  };
}
