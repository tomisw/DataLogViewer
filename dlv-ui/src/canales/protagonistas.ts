/**
 * Con qué canales se abre un log.
 *
 * EL FALLO QUE ESTE MÓDULO EXISTE PARA NO REPETIR
 * ===============================================
 * Un log de Haltech trae unos 475 canales y la ventana solo puede empezar con
 * un puñado. La regla anterior era «los ocho primeros de la lista», que
 * funcionaba con la fuente sintética —pone los interesantes al principio— y
 * fallaba de la peor manera con un log real: las primeras columnas del fichero
 * son diagnósticos de arranque de la ECU (`Bootmode Reason`, `Reset Required`,
 * `Memory Writes Pending`, errores de referencia de tensión), y tres de los
 * ocho son una línea recta. El log se abría bien, la lista de canales se
 * rellenaba bien, y la ventana parecía vacía.
 *
 * La regla vive aquí, separada de `app/aplicacion.ts`, porque es lo único de
 * todo ese camino que se puede comprobar sin un navegador: es una función de
 * una lista de canales a una lista de identificadores, sin DOM y sin WebGL.
 * Dejarla dentro de un método privado de la aplicación la hacía imposible de
 * probar, y es exactamente la clase de decisión que se rompe en silencio.
 */

/** Lo mínimo que hace falta de un canal para decidir si es protagonista. */
export interface CanalCandidato {
  readonly idNativo: string;
  /** Rol semántico (`dlv_core.roles`, FG-09) o `null` si no se asignó ninguno. */
  readonly rol: string | null;
  /** `"EXACTA"`, `"INDEXADA"`, `"DIFUSA"`, o `null`/ausente si no hay rol. */
  readonly confianzaRol?: string | null;
  readonly clasificacion: { readonly vacio: boolean; readonly constante: boolean };
}

/**
 * Un canal `DIFUSA` no puede ser protagonista.
 *
 * Una coincidencia difusa es un parecido de cadenas por encima de un umbral
 * (docs/07 §7.15), no un hecho. Como protagonista, un falso positivo pone en
 * pantalla un canal que no es el que dice ser y nadie lo comprueba, porque
 * viene ya marcado. Enseñar uno menos es más barato que enseñar uno falso.
 */
export function rolFiable(canal: CanalCandidato): string | null {
  if (canal.rol === null) return null;
  return canal.confianzaRol === "DIFUSA" ? null : canal.rol;
}

/**
 * Ni vacío ni constante: dibuja algo.
 *
 * Que un log declare el rol `oil_pressure` no significa que ese sensor
 * estuviera conectado en esa tirada; un canal constante es una recta y ocupa
 * un panel entero para no decir nada.
 */
export function tieneSenal(canal: CanalCandidato): boolean {
  return !canal.clasificacion.vacio && !canal.clasificacion.constante;
}

/**
 * Los identificadores con los que abrir el log, en el orden en que se pedirán.
 *
 * Primero un canal por cada rol de `orden` que exista y tenga señal, en ese
 * orden; después, si no se llegó a `maximo`, se rellena con los primeros
 * canales con señal de la lista.
 *
 * EL REPLIEGUE NO ES UN DETALLE
 * =============================
 * Sin él, un CSV genérico cuyos nombres de columna no reconoce el catálogo de
 * roles (docs/07) abriría con CERO canales marcados: una ventana en blanco,
 * que es justo el síntoma del que viene todo esto. Con él, enseña los primeros
 * canales que tienen señal — el criterio de antes, pero sin las rectas.
 *
 * UN CANAL POR ROL, NO TODOS
 * ==========================
 * `injector_duty` son ocho columnas en un motor de ocho cilindros y
 * `sensor_voltage` diez en un Haltech. Coger todos los del primer rol llenaría
 * la selección entera con el mismo dato repetido ocho veces.
 */
export function elegirProtagonistas(
  canales: readonly CanalCandidato[],
  orden: readonly string[],
  maximo: number,
): string[] {
  const elegidos: string[] = [];
  const puestos = new Set<string>();

  const anadir = (canal: CanalCandidato): void => {
    if (puestos.has(canal.idNativo) || elegidos.length >= maximo) return;
    puestos.add(canal.idNativo);
    elegidos.push(canal.idNativo);
  };

  for (const rol of orden) {
    const candidato = canales.find((c) => tieneSenal(c) && rolFiable(c) === rol);
    if (candidato !== undefined) anadir(candidato);
  }
  for (const canal of canales) {
    if (elegidos.length >= maximo) break;
    if (tieneSenal(canal)) anadir(canal);
  }
  return elegidos;
}
