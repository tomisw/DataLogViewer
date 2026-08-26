/**
 * "No se le puede volver a preguntar lo mismo": recuerda si el usuario aceptó
 * o descartó la propuesta de un perfil, por log (F5-11, decisión 2 del
 * informe).
 *
 * MISMO PATRÓN QUE `locale/idioma.ts#EntornoIdioma`, A PROPÓSITO
 * =================================================================
 * Entorno inyectable en vez de leer `localStorage` global directamente
 * (`vitest.config.ts` corre en `environment: "node"`, sin él), para que
 * `app/aplicacion.ts` pueda pasar un almacén falso en sus pruebas de montaje
 * -- exactamente el motivo por el que existe `EntornoApp` (ver su cabecera).
 * A diferencia de `idioma.ts`, aquí NO hay estado de módulo mutable
 * (`entorno`/`idiomaActual`): cada función recibe el entorno explícito en
 * cada llamada. `idioma.ts` necesita estado propio porque `t()` lo lee sin
 * que nadie se lo pase; esto no -- `app/aplicacion.ts` ya tiene su propio
 * `EntornoApp` guardado en `this.#entorno` y se lo puede pasar sin más en
 * cada consulta, así que un segundo sitio de estado global solo sería una
 * fuente más de desincronización (dos módulos que podrían no estar de
 * acuerdo sobre qué almacén es "el activo") sin ganar nada a cambio.
 *
 * QUÉ CUENTA COMO "EL MISMO LOG"
 * ================================
 * La clave es `referenciaLog` -- el argumento que ya se le pasó a
 * `FuenteDeDatos.abrirLog` (`datos/fuente.ts`) -- combinado con el nombre del
 * perfil propuesto. Es deliberadamente la MISMA cadena opaca que la fuente ya
 * usa para decidir qué log abrir, y no un id de sesión (`LogAbierto.logId`):
 * `logId` lo asigna la fuente en cada apertura y una `FuenteApi` no promete
 * que sea estable entre dos aperturas del mismo fichero (`fuente.ts` lo deja
 * abierto), así que usarlo aquí habría preguntado lo mismo cada vez que se
 * reabre el log -- justo el fallo que esta decisión evita.
 */

export type DecisionPropuestaPerfil = "aceptada" | "descartada";

/** Lo mínimo de almacenamiento persistente que hace falta. `localStorage` lo cumple tal cual. */
export interface EntornoDecisionPerfil {
  readonly almacen?: {
    getItem(clave: string): string | null;
    setItem(clave: string, valor: string): void;
  };
}

/** El entorno real del navegador, o `almacen` ausente si no hay `localStorage` (p. ej. en pruebas). */
export function entornoDelNavegadorDecisionPerfil(): EntornoDecisionPerfil {
  return { almacen: typeof localStorage === "undefined" ? undefined : localStorage };
}

const PREFIJO_CLAVE = "dlv-propuesta-perfil";

function clave(referenciaLog: string, nombrePerfil: string): string {
  // `::` como separador: ni `referenciaLog` (una ruta de fichero) ni
  // `nombrePerfil` deberían contenerlo, y aunque lo hicieran el peor caso es
  // una clave más larga de lo necesario, no una colisión real entre dos
  // pares (referencia, perfil) distintos con la misma concatenación simple.
  return `${PREFIJO_CLAVE}:${referenciaLog}::${nombrePerfil}`;
}

/** La decisión guardada para (referenciaLog, nombrePerfil), o `null` si nunca se preguntó (o no hay almacén). */
export function decisionGuardada(
  entorno: EntornoDecisionPerfil,
  referenciaLog: string,
  nombrePerfil: string,
): DecisionPropuestaPerfil | null {
  const almacen = entorno.almacen;
  if (almacen === undefined) return null;
  const valor = almacen.getItem(clave(referenciaLog, nombrePerfil));
  return valor === "aceptada" || valor === "descartada" ? valor : null;
}

/** Guarda la decisión. Sin `almacen` (entorno sin persistencia) no hace nada: se preguntará otra vez la próxima vez, que es lo correcto cuando no hay dónde recordar la respuesta. */
export function guardarDecision(
  entorno: EntornoDecisionPerfil,
  referenciaLog: string,
  nombrePerfil: string,
  decision: DecisionPropuestaPerfil,
): void {
  entorno.almacen?.setItem(clave(referenciaLog, nombrePerfil), decision);
}
