/**
 * Contrato de datos del panel de incidencias (F3-12, `docs/04` §4.3 in fine:
 * «se resumen en el panel de incidencias: lista ordenada por severidad, con
 * conteo, duración total y salto al instante»).
 *
 * DE DÓNDE SALE ESTE CONTRATO
 * ============================
 * No se inventa aquí: es la traducción a TypeScript de dos cosas que ya
 * existen en `dlv-core` y que este módulo NO puede importar (frontera de
 * paquetes, ADR-006/007):
 *
 * 1. `dlv_core.detectores.Incidencia` — un `Evento` (`primitivas.py`) más
 *    `detector_id`, `severidad` y `detalle`. Sus campos de tiempo son
 *    milisegundos (`t_inicio`/`t_fin`, herencia de `Evento.t_inicio_ms`/
 *    `t_fin_ms`), y así se guardan aquí: `tInicioMs`/`tFinMs`, para no
 *    inventar una unidad que el backend no manda. La conversión a segundos
 *    absolutos de `render/tipos.ts#Vista` (lo que de verdad hace falta para
 *    saltar al instante) es aritmética de quien pinta, en `orden.ts`.
 * 2. `data/umbrales.toml`, secciones `[detectores.D1]`..`[detectores.D18]`:
 *    cada detector declara `etiqueta` y `severidad`. **Los valores concretos
 *    de esas 18 entradas no viven aquí** (regla 2 de `CLAUDE.md`): este
 *    fichero solo declara la FORMA en la que llegan por HTTP.
 *
 * LA TRAMPA DEL DELTA, Y POR QUÉ `DetalleIncidencia` NO ES `Record<string, number>`
 * ===================================================================================
 * El docstring de `Incidencia` en `detectores.py` avisa de un defecto ya
 * identificado y sin resolver todavía en el propio backend: `detalle` es un
 * `dict[str, float]` en Python, y «un diccionario de números no puede llevar
 * la CLASE de conversión de cada número», así que «el panel de incidencias lo
 * convertirá como punto» si no se hace nada — exactamente la trampa que la
 * regla 4 de `CLAUDE.md` prohíbe. Este fichero no puede arreglar el backend
 * (no toco `dlv-core`), pero sí puede negarse a heredar el defecto: en vez de
 * `Record<string, number>`, `DetalleIncidencia` es un mapa de `CampoDetalle`,
 * y cada campo lleva su propia `Clase` **obligatoria, sin valor por
 * omisión**, igual que exige `unidades/conversion.ts#convertirValor`. Si
 * `/comandos/incidencias` no manda la clase de cada campo — hoy no puede,
 * porque `Incidencia.detalle` en Python no la lleva — este tipo no se puede
 * rellenar sin inventarla, y esa es la señal correcta: mejor no mostrar un
 * `valor_pico` que mostrarlo convertido como si fuera un punto cuando es una
 * tasa o un intervalo. Ver el informe de la tarea, sección «qué te ha
 * faltado del backend».
 */

import type { Clase } from "../unidades/conversion.ts";

/**
 * Las cinco severidades del catálogo, en el orden de consecuencia — mismo
 * vocabulario, mismo tipo (`str`) y MISMO ORDEN que
 * `dlv_core.plausibilidad.SEVERIDADES = ("critica", "alta", "media", "baja",
 * "informativa")`, cuyo comentario dice literalmente «el orden de la tupla ES
 * el orden de consecuencia». No se traslada ningún UMBRAL desde
 * `data/umbrales.toml` (regla 2): esto es vocabulario compartido, igual que
 * `Clase` en `unidades/conversion.ts` es el espejo de `dlv_core.unidades.Clase`
 * y no una copia de datos de configuración.
 */
export const SEVERIDADES_CONCRETAS = ["critica", "alta", "media", "baja", "informativa"] as const;

/** Una severidad ya resuelta a un valor concreto — la que lleva CADA incidencia. */
export type SeveridadConcreta = (typeof SEVERIDADES_CONCRETAS)[number];

/**
 * La severidad tal como la declara un detector en el CATÁLOGO (no una
 * incidencia concreta).
 *
 * D13 («Protección de motor activa») es el caso que obliga a este tipo:
 * `data/umbrales.toml` no le da una `severidad` fija, le da
 * `severidad_por_nivel = { 1 = "media", 2 = "alta", 3 = "critica" }` — sale
 * del nivel del canal `protection_level`, no del catálogo. Cada incidencia
 * de D13 que de verdad ocurre SÍ tiene una severidad concreta (la resolvió
 * el backend contra el nivel observado, ver `IncidenciaPanel.severidad`),
 * pero D13 como entrada de catálogo no tiene una única severidad que
 * mostrar junto a su etiqueta: por eso `SeveridadCatalogo` añade el literal
 * `"segun_nivel"` a las cinco concretas, y un tipo que asumiera solo las
 * cinco no tendría dónde poner D13 sin mentir.
 */
export type SeveridadCatalogo = SeveridadConcreta | "segun_nivel";

/**
 * Un campo numérico de `detalle` con su clase de conversión OBLIGATORIA
 * (regla 4 de `CLAUDE.md`, `docs/06` §6.5). Ver la cabecera del módulo: esto
 * es lo que evita la trampa del delta en la puerta de presentación.
 */
export interface CampoDetalle {
  readonly valor: number;
  readonly clase: Clase;
}

/** `Incidencia.detalle`, pero con la clase de cada campo en vez de perderla. */
export type DetalleIncidencia = Readonly<Record<string, CampoDetalle>>;

/**
 * Una incidencia concreta, tal como la sirve el backend para este panel.
 *
 * `severidad` es SIEMPRE una de las cinco concretas, nunca `"segun_nivel"`:
 * ese literal solo tiene sentido para describir el catálogo (§ arriba), no
 * una detección real — el backend ya resolvió el nivel de D13 contra
 * `severidad_por_nivel` antes de mandar la incidencia. Si algún día
 * `/comandos/incidencias` manda `"segun_nivel"` aquí, es un defecto del
 * backend, no un caso que este tipo tenga que aceptar.
 */
export interface IncidenciaPanel {
  /**
   * Identificador ESTABLE de esta incidencia (no del detector): lo que
   * distingue la incidencia n-ésima de D1 de la n+1-ésima. Hace falta para
   * las claves de lista y para que «saltar al instante» sepa a qué fila
   * responde sin depender del índice del array, que cambia con el orden.
   */
  readonly id: string;
  readonly detectorId: string;
  readonly severidad: SeveridadConcreta;
  /** Milisegundos, igual que `Incidencia.t_inicio` / `Evento.t_inicio_ms`. */
  readonly tInicioMs: number;
  /**
   * Milisegundos, igual que `Incidencia.t_fin`. `null` en los mismos casos
   * en que lo es en Python — la incidencia no tiene fin observado todavía o
   * es puntual sin intervalo declarado (ver `Evento`, `primitivas.py`).
   */
  readonly tFinMs: number | null;
  readonly detalle: DetalleIncidencia;
}

/** Un detector tal como lo describe el catálogo (`data/umbrales.toml` vía HTTP). */
export interface DetectorCatalogo {
  readonly id: string;
  readonly etiqueta: string;
  readonly severidad: SeveridadCatalogo;
}

/**
 * Si un detector está activo, y si no, por qué — `docs/07` §7.15: D4, D10 y
 * D12 se desactivan en un log cuyos roles implicados vienen de asignación
 * difusa no confirmada.
 *
 * Unión discriminada a propósito, no `{ activo: boolean; motivo: string |
 * null }`: con un campo opcional, un backend que se olvide de mandar
 * `motivo` en un detector desactivado produce un panel que dice «desactivado»
 * sin decir por qué, que es exactamente lo que la tarea prohíbe («el panel
 * tiene que decir que está desactivado y por qué»). Con la unión, ese estado
 * ni compila: `motivo` es obligatorio en la rama `activo: false` y no existe
 * en la rama `activo: true`.
 */
export type EstadoDetector =
  | { readonly detectorId: string; readonly activo: true }
  | { readonly detectorId: string; readonly activo: false; readonly motivo: string };
