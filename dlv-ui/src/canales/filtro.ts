/**
 * Filtrado y orden de la lista de canales para el selector (F1-33).
 *
 * Módulo puro -- nada de DOM aquí, ver `selector-canales.ts` -- que combina
 * dos cosas independientes:
 *
 * 1. La identidad en capas de ADR-008 (docs/07 §7.11): se busca por nombre,
 *    por rol semántico Y por ID nativo, porque quien piensa en roles
 *    ("¿dónde está `coolant_temp`?") no tiene por qué saber el nombre exacto
 *    que trae el fabricante, y viceversa.
 * 2. La clasificación de F1-07 (`IndiceCanal.vacio`/`.constante`): un canal
 *    inactivo se excluye por omisión, pero SIEMPRE se cuenta y se explica por
 *    qué (docs de la tarea: "oculto porque está constante" es información,
 *    "no aparece" es un error aparente).
 */

import { coincidenciaDifusa } from "./difuso.ts";
import type { CanalInfo, MotivoOculto } from "./tipos.ts";
import { motivoOculto } from "./tipos.ts";

export interface OpcionesFiltro {
  readonly consulta: string;
  readonly mostrarInactivos: boolean;
}

export interface CanalFiltrado {
  readonly canal: CanalInfo;
  /** `null` cuando no hay consulta activa: no hay relevancia que ordenar. */
  readonly puntuacion: number | null;
  /**
   * Por qué este canal está marcado como inactivo, o `null` si está activo.
   * Viaja también cuando el canal SÍ se muestra (porque `mostrarInactivos`
   * está activado): es la etiqueta que explica la fila, no solo el motivo de
   * una ausencia.
   */
  readonly motivoInactivo: MotivoOculto | null;
}

export interface ResumenOcultos {
  readonly constante: number;
  readonly vacio: number;
}

export interface ResultadoFiltro {
  readonly visibles: CanalFiltrado[];
  /**
   * Cuántos canales que SÍ coinciden con la búsqueda actual se han quedado
   * fuera de `visibles` por estar inactivos y no tener `mostrarInactivos`
   * activado. Siempre `{ constante: 0, vacio: 0 }` cuando `mostrarInactivos`
   * es `true`, porque entonces nada se oculta.
   */
  readonly ocultos: ResumenOcultos;
}

/**
 * Filtra y ordena los canales de un log para el selector.
 *
 * Coste: un recorrido de la lista (`n` ~ 475 en el AutoLog real) y, dentro de
 * cada canal, como mucho tres llamadas a `coincidenciaDifusa` (nombre, rol,
 * ID nativo) de coste `O(longitud_texto · longitud_consulta)` cada una. Nada
 * de esto compara un canal con otro, así que es lineal en `n` y no cuadrático
 * -- la propiedad que pide F1-33 para que filtrar no se note por pulsación.
 */
export function filtrarCanales(
  canales: readonly CanalInfo[],
  opciones: OpcionesFiltro,
): ResultadoFiltro {
  const consulta = opciones.consulta.trim();
  const hayConsulta = consulta.length > 0;

  const visibles: CanalFiltrado[] = [];
  let ocultosConstante = 0;
  let ocultosVacio = 0;

  for (const canal of canales) {
    const puntuacion = hayConsulta ? mejorPuntuacion(consulta, canal) : null;
    // Sin coincidencia con la consulta, el canal no aparece con o sin el
    // toggle de inactivos: eso no es "ocultar por inactividad", es que no es
    // lo que se está buscando.
    if (hayConsulta && puntuacion === null) continue;

    const motivo = motivoOculto(canal.clasificacion);
    if (motivo !== null && !opciones.mostrarInactivos) {
      if (motivo === "constante") ocultosConstante += 1;
      else ocultosVacio += 1;
      continue;
    }

    visibles.push({ canal, puntuacion, motivoInactivo: motivo });
  }

  if (hayConsulta) {
    visibles.sort((a, b) => {
      // Los dos vienen de `mejorPuntuacion` bajo `hayConsulta`, nunca `null`
      // aquí; `?? 0` es solo para que el tipo cuadre sin un cast.
      const diferencia = (b.puntuacion ?? 0) - (a.puntuacion ?? 0);
      if (diferencia !== 0) return diferencia;
      // Desempate estable y predecible: alfabético, no "el que llegó antes".
      return a.canal.nombre.localeCompare(b.canal.nombre);
    });
  }

  return {
    visibles,
    ocultos: { constante: ocultosConstante, vacio: ocultosVacio },
  };
}

/**
 * La mejor puntuación de `consulta` contra los tres campos buscables de
 * `canal` (identidad en capas, ADR-008), o `null` si no coincide con
 * ninguno. `rol` e `idNativo` pueden ser `null`/cadena vacía -- muchos
 * canales no tienen rol asignado (docs/07 §7.7) -- y se saltan sin más.
 */
function mejorPuntuacion(consulta: string, canal: CanalInfo): number | null {
  const candidatos = [canal.nombre, canal.rol, canal.idNativo];
  let mejor: number | null = null;
  for (const candidato of candidatos) {
    if (candidato === null || candidato === "") continue;
    const puntuacion = coincidenciaDifusa(consulta, candidato);
    if (puntuacion === null) continue;
    if (mejor === null || puntuacion > mejor) mejor = puntuacion;
  }
  return mejor;
}
