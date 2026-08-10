/**
 * Registro de acciones y filtrado difuso para la paleta de comandos (F5-09).
 *
 * MÓDULO PURO
 * ============
 * Igual que `canales/filtro.ts` frente a `canales/selector-canales.ts`: nada
 * de DOM aquí. `filtrarComandos` es la parte que decide QUÉ se ve y en qué
 * orden; `paleta-comandos.ts` es la parte impura que pinta ese resultado. Por
 * eso este fichero tiene pruebas de `vitest` y el componente DOM no las tiene
 * (misma razón que da la cabecera de `selector-canales.ts`: hace falta un
 * navegador de verdad para decir algo útil sobre pintar un `<li>`).
 *
 * UN REGISTRO POR GRUPOS, NO UNA LISTA CABLEADA
 * ================================================
 * La paleta tiene que poder crecer sin tocar su propio código — el mismo
 * motivo por el que `data/roles.toml` deja añadir un rol sin tocar el
 * importador (docs/07 §7.7). La pieza que lo permite es `RegistroComandos`:
 * quien tiene una fuente de acciones (`Aplicacion`, hoy la única) las declara
 * bajo un nombre de grupo, y la paleta solo conoce `todos()`, nunca de dónde
 * viene cada comando.
 *
 * El grupo, no el `Comando` individual, es la unidad de reemplazo
 * (`registrarGrupo` sustituye TODO lo que hubiera con ese nombre). Es lo que
 * necesita `Aplicacion`: los comandos de "añadir canal X" dependen del log
 * abierto y hay que sustituirlos enteros cada vez que se abre uno nuevo, sin
 * tocar los comandos estáticos (abrir log, cambiar de tema) que viven en otro
 * grupo y no cambian con el log. Es el mismo problema que resuelve
 * `SelectorCanales.actualizarCanales` (reemplazo atómico de una lista
 * completa) aplicado a comandos en vez de a canales.
 *
 * QUÉ ES UN COMANDO
 * ===================
 * Lo mínimo que la paleta necesita para ofrecer una acción y ejecutarla:
 * - `id`: identificador ESTABLE del comando. No lo usa el filtrado (que
 *   compara `etiqueta`) ni lo pinta la paleta: existe para que quien registra
 *   pueda reconocer sus propios comandos más adelante (p. ej. para
 *   depuración, o el día que la paleta necesite recordar "el último comando
 *   ejecutado" por id y no por posición en una lista que cambia de orden).
 * - `etiqueta`: el texto que se busca y se muestra.
 * - `categoria`: opcional, solo para agrupar visualmente ("Canal", "Tema",
 *   "Log"); no participa en la búsqueda ni en el orden.
 * - `ejecutar`: qué hace. Sin argumentos ni valor de vuelta a propósito: el
 *   comando ya lleva todo lo que necesita cerrado en el closure de quien lo
 *   registra (p. ej. el `idNativo` del canal), así que la paleta nunca tiene
 *   que saber qué tipo de acción está lanzando.
 */

import { coincidenciaDifusa } from "../canales/difuso.ts";

export interface Comando {
  readonly id: string;
  readonly etiqueta: string;
  readonly categoria?: string;
  readonly ejecutar: () => void;
}

export interface ComandoFiltrado {
  readonly comando: Comando;
  /** `null` cuando no hay consulta activa: no hay relevancia que ordenar (igual que `CanalFiltrado`). */
  readonly puntuacion: number | null;
}

/**
 * Registro de comandos por grupo. `Aplicacion` es hoy el único que registra
 * (comandos estáticos al construirse, comandos de canal en cada log que se
 * abre), pero la paleta no lo sabe: solo llama a `todos()`.
 */
export class RegistroComandos {
  readonly #porGrupo = new Map<string, readonly Comando[]>();

  /** Sustituye TODOS los comandos que hubiera bajo `grupo` por `comandos`. */
  registrarGrupo(grupo: string, comandos: readonly Comando[]): void {
    this.#porGrupo.set(grupo, comandos);
  }

  /** Quita un grupo entero. No falla si no existía: un log que se cierra sin haber abierto ninguno antes es válido. */
  quitarGrupo(grupo: string): void {
    this.#porGrupo.delete(grupo);
  }

  /**
   * Todos los comandos registrados, de todos los grupos, en el orden en que
   * se registraron sus grupos. La paleta ordena por relevancia sobre este
   * resultado (`filtrarComandos`); este método no ordena nada por sí mismo.
   */
  todos(): readonly Comando[] {
    return [...this.#porGrupo.values()].flat();
  }
}

/**
 * Filtra y ordena comandos por relevancia frente a `consulta`, reutilizando
 * `coincidenciaDifusa` de `canales/difuso.ts` (F1-33) tal cual — el propio
 * enunciado de esta tarea pide no escribir una segunda búsqueda difusa que
 * puntúe distinto y haga que el mismo texto ordene distinto en dos sitios de
 * la misma ventana.
 *
 * Consulta vacía: todos los comandos, con `puntuacion: null`, en el orden que
 * ya traían (normalmente el de registro). Es el estado de "paleta recién
 * abierta": antes de escribir nada tiene más sentido enseñar las acciones en
 * un orden estable que en uno que dependa de una puntuación que no se ha
 * calculado.
 *
 * Desempate alfabético por `etiqueta` a igualdad de puntuación, igual que
 * `filtrarCanales` — mismo motivo: estable y predecible, no "el que se
 * registró antes".
 */
export function filtrarComandos(
  comandos: readonly Comando[],
  consulta: string,
): ComandoFiltrado[] {
  const q = consulta.trim();
  if (q === "") {
    return comandos.map((comando) => ({ comando, puntuacion: null }));
  }

  const resultado: ComandoFiltrado[] = [];
  for (const comando of comandos) {
    const puntuacion = coincidenciaDifusa(q, comando.etiqueta);
    if (puntuacion === null) continue;
    resultado.push({ comando, puntuacion });
  }

  resultado.sort((a, b) => {
    const diferencia = (b.puntuacion ?? 0) - (a.puntuacion ?? 0);
    if (diferencia !== 0) return diferencia;
    return a.comando.etiqueta.localeCompare(b.comando.etiqueta);
  });
  return resultado;
}
