/**
 * Tipos de datos del selector de unidad (F1-31).
 *
 * Estos tipos son el «dato de entrada» del que habla el encargo de la tarea:
 * el componente no conoce `data/units.toml`, ni lo lee, ni copia sus números.
 * Recibe una estructura con esta forma —id, etiqueta, decimales— igual que
 * `dlv_core.unidades.cargar_catalogo` la construye a partir del fichero en el
 * backend. Quien conecte este componente a la aplicación real es responsable
 * de traducir el catálogo servido por `dlv-api` a este tipo; ese cableado no
 * es parte de F1-31 (ver el informe de la tarea).
 *
 * Deliberadamente NO hay aquí ningún campo de conversión (`a`, `b`, tipo
 * afín/recíproca/parametrizada): ese es el trabajo de `dlv_core.unidades`, y
 * el comentario de cabecera de `resolucion.ts` explica por qué este módulo no
 * lo reimplementa.
 */

/** Una unidad tal como la necesita el selector: sin conversión, solo lo que se muestra. */
export interface UnidadInfo {
  readonly id: string;
  /** Texto para el desplegable y para `formatearValor` (p. ej. "°C", "λ", ""). */
  readonly etiqueta: string;
  /**
   * Decimales significativos de ESTA unidad (`docs/06` §6.10). Vienen del
   * dato de entrada, nunca de una constante en este fichero: mostrar λ 0,995
   * con un decimal (1,0) es exactamente el fallo que ese apartado describe.
   */
  readonly decimales: number;
  /** Alias reconocidos además de `id` (p. ej. "kph" para "km/h"). */
  readonly alias?: readonly string[];
}

/** Una dimensión física con sus unidades alternativas (`docs/06` §6.7). */
export interface DimensionInfo {
  readonly id: string;
  readonly etiqueta: string;
  readonly unidadCanonica: string;
  readonly unidades: readonly UnidadInfo[];
  /**
   * `false` para dB (logarítmica), contadores, enums, máscaras de bits y la
   * dimensión `unknown` de confianza sin confirmar (`docs/06` §6.8, §9.11 de
   * `docs/09`). El selector debe desactivarse por completo para estas
   * dimensiones: no hay unidad que elegir, y elegir una sería inventarla.
   */
  readonly convertible: boolean;
  /**
   * Espejo de `mostrar_en_crudo` de `units.toml`: el valor se enseña sin
   * convertir y con una marca visual (mitigación del riesgo R1). Solo tiene
   * sentido cuando `convertible` es `false`.
   */
  readonly mostrarEnCrudo?: boolean;
}

/** Un preset de unidades — de fábrica o de usuario (`docs/06` §6.9, F1-17/F1-18). */
export interface PresetInfo {
  readonly id: string;
  readonly etiqueta: string;
  /**
   * `dimension_id -> unidad_id`, solo para las dimensiones que el preset fija.
   * No todos los presets cubren todas las dimensiones (p. ej. `si` no fija
   * `angle`): una dimensión ausente aquí cae a la unidad canónica, exactamente
   * como en `resolucion_unidad.resolver_unidad`.
   */
  readonly unidades: Readonly<Record<string, string>>;
}

/** El catálogo completo que el componente necesita para resolver y pintar. */
export interface CatalogoUnidades {
  readonly dimensiones: readonly DimensionInfo[];
  readonly presets: readonly PresetInfo[];
  /** Preset activo cuando no se pasa `preset` explícito a `resolverUnidad`. */
  readonly presetPorOmision: string;
}

/** Un canal que el nivel «canal» del selector puede anular individualmente. */
export interface CanalInfo {
  readonly id: string;
  readonly etiqueta: string;
  readonly dimensionId: string;
}

/**
 * Capa de precedencia que decidió la unidad activa (`docs/06` §6.9, espejo de
 * `resolucion_unidad.Capa` de F1-17). El orden de los miembros no importa
 * para la lógica —la precedencia la fija `resolverUnidad`—, solo para leer.
 */
export enum Capa {
  /** Anulación explícita para este canal exacto. Gana siempre. */
  CANAL = "canal",
  /** Preferencia de unidad de la dimensión, del perfil activo. */
  PERFIL = "perfil",
  /** Preset global activo. */
  PRESET = "preset",
  /** Ninguna capa más específica aplica: se usa la unidad canónica. */
  CANONICA = "canonica",
}

/** La unidad activa para un canal, y por qué capa se decidió. */
export interface UnidadResuelta {
  readonly unidad: UnidadInfo;
  readonly capa: Capa;
  readonly dimensionId: string;
}
