/**
 * `PuertoImportacion`: la frontera entre el asistente y "quién sondea el
 * fichero de verdad" — mismo papel que `datos/fuente.ts#FuenteDeDatos` para
 * abrir un log, aplicado al camino de CSV genérico (`docs/07` §7.3, nivel 2).
 *
 * POR QUÉ ESTA INTERFAZ EXISTE Y POR QUÉ SU IMPLEMENTACIÓN REAL FALTA
 * ======================================================================
 * El encargo de esta tarea es explícito: "si hace falta un endpoint que no
 * existe, dilo en vez de inventarlo". Se ha comprobado leyendo
 * `dlv-api/src/dlv_api/main.py` entero (`crear_app`, la lista de
 * `add_api_route`) que HOY solo existen `/comandos/abrir-cabecera`,
 * `/comandos/serie`, `/comandos/abrir-log`, `/comandos/cubos`,
 * `/comandos/sesiones`, `/comandos/cerrar-log`, `/comandos/unidades` y
 * `/comandos/exportar-datos` — los ocho de siempre, todos sobre EL FORMATO
 * NATIVO de Haltech (`_descriptor_haltech`, cableado a una ruta fija). No hay
 * ninguna ruta que sondee un CSV arbitrario: ni delimitador/codificación
 * (FG-01/02, `dlv_core.formatos.sondeo.sondear_csv`), ni estructura
 * (FG-03, `estructura.py`), ni columna de tiempo (FG-04, `tiempo_csv.py`), ni
 * tipos de columna (FG-05, `tipos.py`), ni unidades declaradas en cabecera
 * (FG-06, `unidades_declaradas.py`), ni asignación de rol (FG-09,
 * `dlv_core.roles.asignar_rol`) — y tampoco hay una ruta que sirva el
 * catálogo `data/roles.toml` (sinónimos y rangos plausibles) como
 * `/comandos/unidades` sirve `units.toml`.
 *
 * Todo ESE código Python existe y tiene pruebas (docs/10 §10.6: FG-01…09 y
 * FG-14 "tienen código escrito y pruebas en verde"). Lo que falta es
 * EXCLUSIVAMENTE el cableado de `dlv-api` que lo sirva por HTTP — el mismo
 * hueco que `docs/10` §10.11 punto 6 señala para el descubrimiento de
 * formatos nativos, aplicado aquí al camino genérico. Inventar la forma de
 * ese JSON sin que exista el endpoint sería exactamente lo que
 * `datos/fuente-api.ts` explica que se evitó la primera vez con
 * `/comandos/cubos`: alguien tendría que descubrir después qué parte del
 * contrato era real y cuál una suposición de este agente.
 *
 * QUÉ SÍ SE HA PODIDO CONSTRUIR SIN ESE ENDPOINT
 * ================================================
 * Todo lo que el asistente hace con datos que YA tiene en memoria — repartir
 * de nuevo una fila cuando cambia el delimitador (`celdas.ts`), recalcular la
 * duración cuando cambia la clase de tiempo (`tiempo.ts`), convertir una
 * celda cuando cambia la unidad de origen (`previsualizacion.ts`), decidir si
 * un rol difuso bloquea un detector (`deduccion.ts`) — es lógica pura, no
 * necesita red, y por eso está completo y probado con casos reales (ver el
 * informe de la tarea). Lo que este puerto representa es solo la PRIMERA
 * llamada, la que convierte "he elegido un fichero" en una propuesta inicial.
 */

import type { CanalPropuesto, PropuestaFormato, PropuestaTiempo } from "./tipos.ts";

/** Una fila de muestra, ya como texto — nunca una serie completa (ADR-007). */
export type FilaCruda = string;

export interface ResultadoSondeoFormato {
  readonly propuesta: PropuestaFormato;
  /** Primeras filas crudas, sin partir — el paso 1 las repropone en vivo con
   * `celdas.ts#analizarFila` cada vez que el usuario toca un desplegable. */
  readonly filasPrevia: readonly FilaCruda[];
  readonly avisos: readonly string[];
}

export interface ResultadoSondeoTiempo {
  readonly propuesta: PropuestaTiempo;
  /** Valores crudos de la(s) columna(s) de tiempo en las filas de muestra,
   * para que `tiempo.ts#calcularResumenTiempo` los recalcule en vivo. */
  readonly valoresBrutos: readonly string[];
  readonly avisos: readonly string[];
}

export interface ResultadoSondeoCanales {
  readonly canales: readonly CanalPropuesto[];
  readonly avisos: readonly string[];
}

/** Una entrada de `data/roles.toml`, en la forma que necesita un desplegable
 * "asignar rol a mano" y el informe de plausibilidad (`docs/07` §7.7). */
export interface RolDeCatalogo {
  readonly id: string;
  readonly dimensionId: string | null;
  readonly plausibleMin: number | null;
  readonly plausibleMax: number | null;
  readonly critico: boolean;
}

/**
 * Contrato único de sondeo de CSV genérico. El asistente (`asistente-
 * importacion.ts`) solo conoce esto — igual que `app/aplicacion.ts` solo
 * conoce `FuenteDeDatos`.
 */
export interface PuertoImportacion {
  readonly nombre: string;
  sondearFormato(referenciaFichero: string): Promise<ResultadoSondeoFormato>;
  sondearTiempo(
    referenciaFichero: string,
    formatoConfirmado: PropuestaFormato,
  ): Promise<ResultadoSondeoTiempo>;
  sondearCanales(
    referenciaFichero: string,
    formatoConfirmado: PropuestaFormato,
    tiempoConfirmado: PropuestaTiempo,
  ): Promise<ResultadoSondeoCanales>;
  catalogoRoles(): Promise<readonly RolDeCatalogo[]>;
}

/**
 * Lo que pasa al llamar HOY a cualquier método: dice exactamente qué falta en
 * `dlv-api` y por qué, en vez de fingir una respuesta. Ver la cabecera del
 * módulo — no es un placeholder olvidado, es la constancia deliberada de un
 * hueco de backend para quien retome FG-11/FG-12.
 */
export class PuertoImportacionSinImplementar extends Error {
  constructor(operacion: string, endpointQueFalta: string) {
    super(
      `${operacion}: dlv-api todavía no tiene ${endpointQueFalta}. La lógica de ` +
        "dlv-core existe (docs/10 §10.6); falta cablearla en dlv_api.main.crear_app, " +
        "igual que docs/10 §10.11 punto 6 señala para el descubrimiento de formatos " +
        "nativos. No se inventa la forma de esa respuesta aquí.",
    );
    this.name = "PuertoImportacionSinImplementar";
  }
}

/**
 * Adaptador contra `dlv-api` — deliberadamente incompleto, como el primer
 * esbozo de `FuenteApi` antes de que existiera `/comandos/abrir-log` con
 * sesión. Cuando `dlv-api` tenga las cuatro rutas, esta clase es donde se
 * cablean: la forma de `PuertoImportacion` ya está pensada para no cambiar al
 * hacerlo (mismo patrón de `referencia` opaca que `FuenteDeDatos#abrirLog`).
 */
export class PuertoImportacionApi implements PuertoImportacion {
  readonly nombre = "dlv-api";

  // eslint-disable-next-line @typescript-eslint/require-await
  async sondearFormato(): Promise<ResultadoSondeoFormato> {
    throw new PuertoImportacionSinImplementar(
      "sondearFormato",
      "un endpoint que sirva dlv_core.formatos.sondeo.sondear_csv + estructura.py (FG-01/02/03)",
    );
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async sondearTiempo(): Promise<ResultadoSondeoTiempo> {
    throw new PuertoImportacionSinImplementar(
      "sondearTiempo",
      "un endpoint que sirva dlv_core.formatos.tiempo_csv.detectar_columna_de_tiempo (FG-04)",
    );
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async sondearCanales(): Promise<ResultadoSondeoCanales> {
    throw new PuertoImportacionSinImplementar(
      "sondearCanales",
      "un endpoint que sirva dlv_core.formatos.tipos + unidades_declaradas + " +
        "dlv_core.roles.asignar_rol (FG-05/06/09)",
    );
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async catalogoRoles(): Promise<readonly RolDeCatalogo[]> {
    throw new PuertoImportacionSinImplementar(
      "catalogoRoles",
      "un endpoint que sirva data/roles.toml, análogo a /comandos/unidades para units.toml",
    );
  }
}
