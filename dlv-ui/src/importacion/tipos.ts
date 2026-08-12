/**
 * Tipos del asistente de importación de CSV genérico (FG-11).
 *
 * `docs/07-formatos-y-csv-generico.md` §7.8 pide tres pasos —formato, tiempo,
 * canales— con previsualización viva en todos ellos, y §7.15 pone una regla
 * dura encima: una deducción y una confirmación del usuario NO son el mismo
 * dato. Este fichero es el vocabulario compartido de los tres pasos, y está
 * construido alrededor de esa distinción, no alrededor de la forma más cómoda
 * de pintar una tabla.
 *
 * DOS DISTINCIONES QUE NO SE MEZCLAN, AUNQUE SE PAREZCAN
 * =======================================================
 * 1. `Campo<T>.origen` — «deducido» / «confirmado» — se aplica a CUALQUIER
 *    valor que el sondeo propuso y el usuario puede corregir: el delimitador,
 *    la codificación, la columna de tiempo, la unidad de origen de un canal.
 *    Es genérico porque la regla es la misma en los tres pasos: mientras nadie
 *    lo haya tocado, es una propuesta, no un hecho (§7.4).
 * 2. `RolPropuesto.confianza` — `Confianza` de `dlv_core.roles`, espejo textual
 *    del mismo vocabulario que ya usa `datos/fuente.ts#CanalDeFuente.
 *    confianzaRol` — es específico de la asignación de ROL, y lleva su propio
 *    `confirmado` en vez de un `Campo<string>` genérico porque §7.15 exige una
 *    regla adicional que no aplica a los demás campos: una asignación `DIFUSA`
 *    no solo se muestra distinta, sino que APAGA los detectores críticos que
 *    dependan de ese rol hasta que alguien la confirme (`deduccion.ts`).
 *
 * Confundir las dos —tratar una `DIFUSA` sin confirmar como un `Campo`
 * cualquiera con `origen: "deducido"`— perdería precisamente el matiz que
 * hace falta: un delimitador deducido y sin confirmar es solo una propuesta
 * visual; un rol `DIFUSA` sin confirmar es una propuesta que además tiene que
 * poder desactivar una alerta de seguridad aguas abajo.
 */

/** Espejo textual de `dlv_core.roles.Confianza`. Mismo vocabulario que ya usa
 * `datos/fuente.ts#CanalDeFuente.confianzaRol` para no inventar un segundo. */
export type Confianza = "EXACTA" | "INDEXADA" | "DIFUSA";

/**
 * Espejo de `dlv_core.formatos.tiempo_csv.ClaseDeTiempo` (docs/10 §10.3): el
 * mismo vocabulario que usa un descriptor de formato nativo para declarar
 * `[cuerpo].clase_de_tiempo`, así que no hay dos sistemas paralelos para "qué
 * es la columna de tiempo".
 */
export type ClaseDeTiempo =
  | "hora_del_dia"
  | "iso8601"
  | "epoch_segundos"
  | "epoch_milisegundos"
  | "relativo"
  | "contador_de_muestras"
  | "fecha_y_hora_separadas"
  | "ausente";

/** `true` si esta clase no puede construir un eje sin que el usuario declare
 * la frecuencia de muestreo (docs/07 §7.5; espejo de
 * `ClaseDeTiempo.necesita_frecuencia_del_usuario`). */
export function necesitaFrecuenciaDelUsuario(clase: ClaseDeTiempo): boolean {
  return clase === "contador_de_muestras" || clase === "ausente";
}

/** «Propuesta del sondeo» o «decisión del usuario». Ver la cabecera del módulo. */
export type Origen = "deducido" | "confirmado";

/**
 * Un valor editable del asistente, con quién decidió el valor actual.
 *
 * Es el tipo que hace posible la regla no negociable de la tarea: la interfaz
 * NUNCA pinta un valor sin saber si viene del sondeo o de una corrección del
 * usuario, porque el dato mismo lleva esa marca. No hay manera de renderizar
 * un campo "a secas" y olvidarse — el tipo no tiene un valor pelado, solo esto.
 */
export interface Campo<T> {
  readonly valor: T;
  readonly origen: Origen;
}

/**
 * El resultado de `dlv_core.roles.asignar_rol` en forma de UI, con la marca de
 * confirmación que pide `docs/07` §7.15.
 *
 * `confirmado` es independiente de `confianza`: una asignación `EXACTA` o
 * `INDEXADA` no necesita confirmación (son firmes por construcción, docs/10
 * §10.4), así que `confirmado` empieza en `true` para ellas y en `false` para
 * `DIFUSA`. Ver `deduccion.ts#propuestaInicialDeRol`.
 */
export interface RolPropuesto {
  readonly rol: string;
  readonly confianza: Confianza;
  /** El sinónimo del catálogo que disparó la asignación (docs/07 §7.7). */
  readonly sinonimo: string;
  readonly indice: number | null;
  /** 1,0 en exacta e indexada; el ratio de `difflib` en las difusas. */
  readonly parecido: number;
  readonly confirmado: boolean;
}

/** Paso 1: formato del fichero (`docs/07` §7.8, paso 1). */
export interface PropuestaFormato {
  readonly codificacion: Campo<string>;
  /** `null` = el sondeo no propone ninguno (ver `Sondeo.delimitador`); el
   * usuario tiene que elegirlo para poder avanzar. */
  readonly delimitador: Campo<string | null>;
  readonly comilla: Campo<string | null>;
  readonly decimal: Campo<"." | ",">;
  /** Índice de línea (0-based) de la fila de nombres, o `null` si no hay. */
  readonly filaCabecera: Campo<number | null>;
  /** Índice de línea de la fila de unidades declaradas, o `null` si no hay
   * (docs/07 §7.6, §7.4 paso 6). */
  readonly filaUnidades: Campo<number | null>;
  /** Índice de línea donde empiezan los datos. */
  readonly filaDatos: Campo<number>;
}

/** Paso 2: columna de tiempo (`docs/07` §7.8, paso 2, y §7.5). */
export interface PropuestaTiempo {
  readonly clase: Campo<ClaseDeTiempo>;
  /** `null` en `ausente`, o si `clase` es `fecha_y_hora_separadas` y esta es
   * la columna de HORA. */
  readonly columna: Campo<number | null>;
  /** Solo relevante con `fecha_y_hora_separadas`. */
  readonly columnaFecha: Campo<number | null>;
  /** Hz declarados por el usuario; obligatorio para `contador_de_muestras` y
   * `ausente` (`necesitaFrecuenciaDelUsuario`). `null` mientras no se declare. */
  readonly frecuenciaHz: Campo<number | null>;
  /** 1,0 para segundos, 0,001 para milisegundos; 1,0 si no aplica. */
  readonly factorASegundos: number;
}

/** Tipo inferido de una columna (`docs/07` §7.4 paso 9, y §7.10). */
export type TipoInferido = "entero" | "decimal" | "enum" | "booleano" | "constante" | "vacio" | "texto";

/** Paso 3, una fila de la tabla de canales (`docs/07` §7.8, paso 3). */
export interface CanalPropuesto {
  readonly columna: number;
  readonly nombreOriginal: string;
  readonly tipoInferido: TipoInferido;
  /** Id de dimensión del catálogo de unidades, o `"unknown"` si no se pudo
   * resolver — nunca la ausencia de dimensión (mismo criterio que
   * `datos/fuente.ts#CanalDeFuente.dimensionId`). */
  readonly dimensionId: Campo<string>;
  /** Texto de unidad tal como se extrajo del fichero (`docs/07` §7.6):
   * `null` si no hay ninguna forma de unidad reconocible en la cabecera. */
  readonly unidadOrigen: Campo<string | null>;
  readonly rol: RolPropuesto | null;
  /** «Columna de avisos» de §7.8 paso 3, en prosa. */
  readonly avisos: readonly string[];
}

/**
 * Una celda de la previsualización, YA analizada (dividida en campos y
 * clasificada), pero SIN convertir a ninguna unidad todavía.
 *
 * La distinción `hueco` / `texto` / `numero` es la que exige la regla de
 * `docs/07` §7.10: «celda vacía, NUNCA 0». Un hueco no es un número de valor
 * cero, y por eso no comparte forma con `numero` — no hay un campo `valor:
 * number | null` donde `null` y `0` puedan confundirse aguas abajo por un
 * `??` descuidado.
 */
export type CeldaPrevia =
  | { readonly tipo: "hueco" }
  | { readonly tipo: "texto"; readonly texto: string }
  | { readonly tipo: "numero"; readonly texto: string; readonly valor: number };

export type FilaPrevia = readonly CeldaPrevia[];
