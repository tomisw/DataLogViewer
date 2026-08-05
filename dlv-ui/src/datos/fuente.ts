/**
 * `FuenteDeDatos`: la interfaz que separa "montar la aplicación" de "de dónde
 * salen los datos" (tarea del MVP, ver el encargo en el informe de la rama).
 *
 * POR QUÉ EXISTE ESTA FRONTERA
 * ============================
 * Todo lo que hay en `src/` — renderizador (F1-23), caché de cubos (F1-24),
 * ejes (F1-25), paneles (F1-26), navegación (F1-28), escalas (F1-27), cursor
 * (F1-29), unidades (F1-31) y selector de canales (F1-33) — está construido y
 * probado, pero ninguna pieza sabe abrir un fichero ni hablar con un backend:
 * todas reciben ya los datos resueltos (`CubosContinuos`, `CanalInfo`,
 * `CatalogoUnidades`...). Esta interfaz es el único sitio del frontend que
 * sabe que "abrir un log" es una operación con nombre, y es lo que permite que
 * `app/aplicacion.ts` no necesite saber si esos datos vinieron de memoria o de
 * `dlv-api`.
 *
 * Hay DOS implementaciones:
 *
 * - `FuenteSintetica` (`fuente-sintetica.ts`): genera datos en memoria, sin
 *   backend. Es la que usa `main.ts` hoy y con la que se probó esta tarea.
 * - `FuenteApi` (`fuente-api.ts`): esbozo deliberadamente incompleto. Otro
 *   agente está ampliando `dlv-api` con la sesión de log abierto y el
 *   endpoint de cubos AHORA MISMO, y su forma exacta (¿un `logId` de sesión?
 *   ¿Arrow IPC de un nivel de pirámide completo, o por rango?) no existe
 *   todavía. Adivinar ese contrato aquí sería peor que no tenerlo: alguien
 *   tendría que descubrir más tarde qué parte es real y cuál es una
 *   suposición. Por eso cada método de `FuenteApi` lanza explícitamente en vez
 *   de fingir que habla con algo que no está.
 *
 * QUÉ NO HACE ESTA INTERFAZ
 * =========================
 * No convierte unidades (eso es cosa de quien pinta los cubos, ver la
 * cabecera de `app/conversion-demo.ts`) y no decide qué nivel de pirámide
 * pedir (eso es `render/escala.ts#elegirNivel`, que ya existe y que
 * `app/aplicacion.ts` reutiliza con `nivelesDe`). Esta interfaz solo abre,
 * lista canales, entrega niveles disponibles y sirve cubos para un rango y un
 * nivel — las cuatro operaciones que dice el encargo de la tarea.
 */

import type { CubosContinuos } from "../render/tipos.ts";
import type { CatalogoUnidades } from "../unidades/tipos.ts";
import type { Rango } from "./cache-cubos.ts";

/** Traducción directa de `IndiceCanal.vacio`/`.constante` (F1-07, `dlv_core.almacen`). */
export interface ClasificacionCanalFuente {
  readonly vacio: boolean;
  readonly constante: boolean;
}

/**
 * Un canal tal como lo entrega la fuente: identidad + lo mínimo para que
 * `app/aplicacion.ts` pueda construir el `CanalInfo` que pide CADA módulo de
 * consumo (`canales/tipos.ts`, `unidades/tipos.ts` y `paneles/tipos.ts` tienen
 * cada uno su propio `CanalInfo`/`CanalEnPanel`, con campos distintos — ver el
 * informe de la tarea, es una de las costuras que no se han limado).
 */
export interface CanalDeFuente {
  readonly idNativo: string;
  readonly nombre: string;
  readonly rol: string | null;
  /**
   * Cómo se decidió `rol`: `"EXACTA"`, `"INDEXADA"` o `"DIFUSA"`
   * (`dlv_core.roles.Confianza`), y `null` cuando no hay rol.
   *
   * Va separado de `rol` porque docs/07 §7.15 lo exige: una coincidencia
   * `DIFUSA` es un parecido de cadenas por encima de un umbral, no un hecho, y
   * no puede activar por sí sola nada que dependa del significado del canal.
   * Opcional para que las fuentes que no lo sepan no tengan que mentir.
   */
  readonly confianzaRol?: string | null;
  /**
   * Id de dimensión del catálogo de unidades (`"unknown"` si no se pudo
   * asignar ninguna, igual que `dlv_core.unidades` — nunca `null`: "sin
   * confirmar" es una dimensión más, con su propia entrada en el catálogo,
   * no la ausencia de dimensión).
   */
  readonly dimensionId: string;
  readonly clasificacion: ClasificacionCanalFuente;
}

/** Un nivel de pirámide disponible para un canal, tal y como lo pide `elegirNivel`. */
export interface ResumenNivelFuente {
  readonly factor: number;
  readonly nCubos: number;
}

/** Lo que devuelve `abrirLog`: metadatos, nunca series (ADR-007). */
export interface LogAbierto {
  readonly logId: string;
  readonly nombre: string;
  /** Instante absoluto (segundos) del primer dato del log. */
  readonly tInicio: number;
  /** Instante absoluto (segundos) del último dato del log. */
  readonly tFin: number;
  readonly canales: readonly CanalDeFuente[];
  readonly avisos: readonly string[];
}

/**
 * Contrato único de acceso a datos. `app/aplicacion.ts` solo conoce esto.
 */
export interface FuenteDeDatos {
  /** Nombre corto para diagnóstico en la interfaz ("sintética", "dlv-api"). */
  readonly nombre: string;

  /**
   * Abre un log. `referencia` es deliberadamente opaca (una ruta para
   * `FuenteApi`, un nombre de escenario para `FuenteSintetica`): quien
   * implementa decide qué significa.
   */
  abrirLog(referencia: string): Promise<LogAbierto>;

  /** Libera lo que la fuente tenga reservado para `logId`. Nunca lanza. */
  cerrarLog(logId: string): void;

  /** El catálogo de unidades. Independiente del log (F1-13: es un fichero de datos global). */
  catalogoUnidades(): Promise<CatalogoUnidades>;

  /**
   * Los niveles de pirámide disponibles para un canal, con su `factor` y su
   * `nCubos` TOTAL (todo el log, no la vista) — la forma exacta que pide
   * `render/escala.ts#elegirNivel`.
   */
  nivelesDe(logId: string, canalId: string): Promise<readonly ResumenNivelFuente[]>;

  /**
   * Cubos de `canalId` que cubren (al menos) `rango`, al nivel `factor`.
   * Quien llama ya ha aplicado el margen de `CacheDeCubos#consultar`: esta
   * función no decide cuánto pedir de más, solo sirve lo que se le pide.
   */
  pedirCubos(
    logId: string,
    canalId: string,
    rango: Rango,
    factor: number,
  ): Promise<CubosContinuos>;
}
