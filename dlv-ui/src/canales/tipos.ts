/**
 * Contrato de datos del selector de canales (F1-33).
 *
 * Igual que ADR-006 separa el renderizador de "logs, unidades y perfiles"
 * (`render/tipos.ts`), este selector no sabe leer un log ni construir un
 * `IndiceCanal` (`dlv_core.almacen`, F1-07): recibe una lista ya resuelta de
 * `CanalInfo` y no pide nada más. Quien ensambla esa lista -- el código que sí
 * habla con dlv-api -- es responsable de traducir `IndiceCanal.vacio` /
 * `.constante` y `ChannelKey.rol` / `.id_nativo` (docs/07 §7.11, ADR-008) a
 * estos campos.
 */

/**
 * Traducción directa de las dos banderas de `IndiceCanal` (F1-07,
 * `dlv_core.almacen`) que deciden si un canal se oculta por omisión.
 *
 * `fuera_de_rango` NO participa aquí a propósito: el requisito de F1-33 solo
 * pide ocultar "constante" y "vacío" -- un canal fuera de su rango declarado
 * sigue siendo interesante de ver, es literalmente la clase de cosa que
 * alguien abre el log para encontrar.
 */
export interface ClasificacionCanal {
  readonly vacio: boolean;
  readonly constante: boolean;
}

export type MotivoOculto = "constante" | "vacio";

/**
 * Un canal tal como lo necesita el selector: identidad en capas (ADR-008,
 * docs/07 §7.11) más la clasificación de F1-07. Nada de `t`/`v`, nada de
 * pirámide: eso es `ChannelSeries` y no le importa a este módulo.
 */
export interface CanalInfo {
  /**
   * Clave estable dentro de ESTA lista: es lo que se emite en el callback de
   * selección. Si el mismo canal puede aparecer en más de un log a la vez
   * (multi-log), componer la clave para que sea única es responsabilidad de
   * quien construye la lista -- este módulo no la reinterpreta ni la deriva.
   */
  readonly idNativo: string;
  readonly formato: string | null;
  readonly nombre: string;
  /** Rol semántico (docs/07 §7.7), o `null` si no se pudo asignar ninguno. */
  readonly rol: string | null;
  readonly clasificacion: ClasificacionCanal;
}

/**
 * `null` si el canal está activo. `vacío` pesa más que `constante`: un canal
 * vacío no tiene ningún valor que se esté repitiendo (ver el docstring de
 * `IndiceCanal.constante` en `almacen.py`: "un canal vacío no es constante"),
 * así que si algún día ambas banderas llegaran en `true` a la vez por un
 * error de quien ensambla la lista, decir la verdad ("no hay datos") es más
 * útil que decir "constante".
 */
export function motivoOculto(clasificacion: ClasificacionCanal): MotivoOculto | null {
  if (clasificacion.vacio) return "vacio";
  if (clasificacion.constante) return "constante";
  return null;
}
