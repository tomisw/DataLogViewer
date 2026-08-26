/**
 * `SugerenciaDePerfil`: el dato de entrada de `PropuestaPerfil` (F5-11, E9.6).
 *
 * ESPEJO ENRIQUECIDO DE `dlv_core.sugerencia_perfil.SugerenciaPerfil`, NO UNA
 * COPIA LITERAL
 * ============================================================================
 * `SugerenciaPerfil` (F3-04, `dlv-core/src/dlv_core/sugerencia_perfil.py`)
 * solo lleva `disponibles`/`total` -- dos enteros, suficientes para su propio
 * trabajo, que es ORDENAR perfiles por cobertura. La decisión 3 del encargo
 * de F5-11 pide algo que esos dos enteros no pueden dar por sí solos: "si
 * faltan roles, decir CUÁLES", no solo cuántos. Por eso este tipo añade
 * `rolesDisponibles`/`rolesFaltantes` -- los NOMBRES, no la cuenta --, con
 * `disponibles === rolesDisponibles.length` y
 * `total === rolesDisponibles.length + rolesFaltantes.length` como invariante
 * (`validarSugerencia` la comprueba).
 *
 * QUIEN LA CONSTRUYE TIENE QUE HACER ALGO MÁS QUE `sugerencia_perfil.py` HACE
 * HOY
 * ============================================================================
 * `_cobertura_de` (en el módulo de F3-04) calcula un `frozenset[str]` interno
 * de roles disponibles por panel y lo REDUCE a un entero antes de devolver
 * `SugerenciaPerfil` -- el conjunto con los nombres nunca sale de la función.
 * Producir este tipo enriquecido pide exponer ese conjunto (y su
 * complementario contra `Perfil.roles_referenciados`) en vez de descartarlo.
 * Es trabajo pendiente de quien conecte esto a un endpoint real de
 * `dlv-api` -- ver la cabecera de `datos/fuente.ts` (`FuenteDeDatos.sugerirPerfil`)
 * para por qué ese endpoint no existe todavía y qué hace mientras tanto
 * `app/aplicacion.ts`.
 */

/** Un perfil candidato, con su cobertura de roles ya resuelta contra UN log. */
export interface SugerenciaDePerfil {
  /** `Perfil.nombre` (`perfiles/perfil.ts`): el nombre tal como lo declara el `.dlvprofile`. */
  readonly nombrePerfil: string;
  /** `SugerenciaPerfil.disponibles` (F3-04): roles con canal resuelto, no vacío, confianza firme. */
  readonly disponibles: number;
  /** `SugerenciaPerfil.total` (F3-04): `Perfil.roles_referenciados`, el denominador completo. */
  readonly total: number;
  /** Los roles de `total` que SÍ tienen canal disponible. Longitud == `disponibles`. */
  readonly rolesDisponibles: readonly string[];
  /** Los roles de `total` que NO tienen canal disponible. Longitud == `total - disponibles`. */
  readonly rolesFaltantes: readonly string[];
}

/**
 * Comprueba las invariantes de conteo antes de pintar nada.
 *
 * Mismo criterio que `SugerenciaPerfil.__post_init__` en Python: un dato de
 * entrada que no cuadra es un error de quien lo construyó (una futura
 * integración con `dlv-api`), no una `null`/`undefined` silenciosa que
 * `PropuestaPerfil` tendría que adivinar cómo pintar.
 */
export function validarSugerencia(sugerencia: SugerenciaDePerfil): void {
  const { disponibles, total, rolesDisponibles, rolesFaltantes } = sugerencia;
  if (disponibles < 0 || total < 0) {
    throw new Error("SugerenciaDePerfil: `disponibles` y `total` no pueden ser negativos");
  }
  if (disponibles > total) {
    throw new Error(
      `SugerenciaDePerfil '${sugerencia.nombrePerfil}': disponibles (${disponibles}) no puede superar total (${total})`,
    );
  }
  if (rolesDisponibles.length !== disponibles) {
    throw new Error(
      `SugerenciaDePerfil '${sugerencia.nombrePerfil}': rolesDisponibles tiene ${rolesDisponibles.length} nombres pero disponibles dice ${disponibles}`,
    );
  }
  if (rolesFaltantes.length !== total - disponibles) {
    throw new Error(
      `SugerenciaDePerfil '${sugerencia.nombrePerfil}': rolesFaltantes tiene ${rolesFaltantes.length} nombres pero total-disponibles dice ${total - disponibles}`,
    );
  }
}
