/**
 * Contrato de datos de los topes (límites de alerta) dibujados sobre un panel
 * (F3-11, depende de F3-10 `dlv_core.topes` y de F1-25 `ejes/`).
 *
 * QUÉ MODELA Y QUÉ NO
 * ====================
 * El modelo del tope en sí —aviso, crítico, banda, curva en función de otro
 * canal— ya existe en `dlv_core.topes` (F3-10) y NO se reimplementa aquí: este
 * módulo solo sabe convertir un tope YA RESUELTO a coordenadas de píxel, igual
 * que `ejes/geometria.ts` no sabe nada de logs y solo convierte una `Vista` a
 * ticks. Un límite resuelto es un `LimiteResuelto`: un número constante (la
 * mayoría de los casos: D6, D8, D9, D11…) o una curva ya evaluada punto a
 * punto por quien llama (una curva depende de OTRO canal —D10, presión de
 * aceite en función del régimen— y leer y alinear ese canal es trabajo de
 * quien orquesta, no de este módulo: el mismo criterio por el que
 * `dlv_core.topes.evaluar_curva` exige la serie de referencia ya alineada en
 * vez de leerla él mismo).
 *
 * EL BACKEND TODAVÍA NO SIRVE TOPES
 * ===================================
 * `dlv-api` no expone hoy los topes de un canal: no hay endpoint sobre
 * `data/umbrales.toml` con la precedencia canal > perfil > usuario > fichero
 * (esa resolución es F3-10 del lado Python, y su exposición HTTP no está
 * hecha). Este módulo recibe los límites como dato de entrada, exactamente
 * como `pintarEjes` recibe su `ConfiguracionEjes`, así que se puede construir
 * y probar hoy y conectar el día que ese endpoint exista, sin cambiar el
 * contrato de este fichero.
 *
 * UN TOPE SE GUARDA EN CANÓNICA, NO EN CRUDO
 * =============================================
 * `docs/06` §6.11 y la cabecera de `dlv_core.topes` (sección "sobre presión")
 * son explícitos: un tope no es una muestra cruda del canal como lo son los
 * cubos de la pirámide, YA está en canónica. Convertirlo a la unidad mostrada
 * es UN solo paso —`convertirValor(valorCanonico, conversion, "punto")`— y NO
 * dos: aplicarle primero un `to_canon` de canal (como exige
 * `convertirDesdeCrudo` para los cubos, que sí nacen crudos) sería inventarle
 * al tope un origen que no tiene y desplazaría la línea del sitio que le
 * corresponde. Es la misma trampa del factor de diez que ya costó días en
 * `unidades/conversion.ts`, pero al revés: aquí el error sería aplicar UN paso
 * de más, no de menos.
 *
 * LA CLASE ES SIEMPRE PUNTO
 * ==========================
 * `dlv_core.topes.evaluar_curva` lo deja escrito: la serie de un tope es
 * `Clase.PUNTO` porque es un valor absoluto del canal al que se compara,
 * nunca una diferencia entre dos. Por eso este módulo no expone un parámetro
 * de clase — habría una sola respuesta correcta posible, y un parámetro con
 * una sola respuesta correcta es una forma de dejar que alguien lo cambie por
 * error (la regla 4 de `CLAUDE.md` sin valor por omisión, aplicada aquí como
 * "sin parámetro en absoluto").
 */

import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Vista } from "../render/tipos.ts";
import type { Conversion } from "../unidades/conversion.ts";

/** Espejo de `dlv_core.topes.NivelDeTope`: el orden ES el de gravedad. */
export type NivelTope = "aviso" | "critico";

/** Un punto de una curva ya evaluada: instante absoluto (mismo eje que `Vista.t0`/`t1`) y valor CANÓNICO. */
export interface PuntoCurvaTope {
  readonly t: number;
  readonly valorCanonico: number;
}

/**
 * Un límite ya resuelto a números: constante en toda la vista, o una curva
 * evaluada punto a punto (el caso de D10). Las dos formas de
 * `dlv_core.topes.Curva` (`CurvaLineal` y `CurvaPorPuntos`) llegan aquí ya
 * reducidas a la misma representación — evaluarlas es trabajo de F3-10, no de
 * este módulo, que solo sabe convertir números canónicos a píxeles.
 */
export type LimiteResuelto =
  | { readonly tipo: "constante"; readonly valorCanonico: number }
  | { readonly tipo: "curva"; readonly puntos: readonly PuntoCurvaTope[] };

/** Un tope de un lado (espejo de `dlv_core.topes.Tope`): aviso o crítico, plano o en curva. */
export interface LineaTope {
  readonly id: string;
  readonly nivel: NivelTope;
  readonly limite: LimiteResuelto;
  /** Texto opcional para la etiqueta, p. ej. "aceite mínimo". Por omisión, solo el valor formateado. */
  readonly etiqueta?: string;
}

/**
 * Un tope de dos lados (espejo de `dlv_core.topes.TopeDeBanda`). `minimo` y
 * `maximo` pueden ser cada uno constante o curva de forma independiente — el
 * caso de la banda de λ, donde el objetivo se mueve con la carga.
 */
export interface BandaTope {
  readonly id: string;
  readonly nivel: NivelTope;
  readonly minimo: LimiteResuelto;
  readonly maximo: LimiteResuelto;
  readonly etiqueta?: string;
}

/** Un punto ya en píxeles del área de dibujo (mismo sistema que `ejes/coordenadas.ts`). */
export interface PuntoPixel {
  readonly x: number;
  readonly y: number;
}

/**
 * Dónde cae una línea de tope PLANA respecto al área visible.
 *
 * Es la decisión central del módulo (ver cabecera de `geometria.ts` para el
 * razonamiento completo): un tope constante fuera del rango que la autoescala
 * eligió para esta vista no desaparece — se ancla al borde con una marca. La
 * alternativa, omitirlo en silencio, es exactamente el fallo que
 * `docs/04-perfiles-motorsport.md` §4.3 dice que un detector no se puede
 * permitir ("el perfil que evita motores rotos... no perder ni un evento").
 */
export type PosicionLinea =
  | { readonly tipo: "dentro"; readonly pixelY: number }
  | { readonly tipo: "fuera-arriba" }
  | { readonly tipo: "fuera-abajo" };

/** La forma resuelta de un borde: una línea plana (con su posición) o una curva (con sus puntos, ya recortados). */
export type FormaResuelta =
  | { readonly tipo: "plano"; readonly posicion: PosicionLinea }
  | { readonly tipo: "curva"; readonly puntos: readonly PuntoPixel[] };

export interface LineaResuelta {
  readonly id: string;
  readonly nivel: NivelTope;
  readonly etiqueta: string;
  readonly forma: FormaResuelta;
}

export interface BandaResuelta {
  readonly id: string;
  readonly nivel: NivelTope;
  readonly etiqueta: string;
  /**
   * Borde de `minimo`, ya en píxeles del área. Si el límite es constante, son
   * dos puntos que cubren todo el ancho a la misma `y`; si es curva, un punto
   * por muestra visible. En los dos casos la `y` ya está RECORTADA a
   * `[0, area.alto]` — ver la cabecera de `geometria.ts` para por qué una
   * banda se recorta y una línea plana se ancla con marca, en vez de la misma
   * regla para las dos.
   */
  readonly bordeMinimo: readonly PuntoPixel[];
  /** Borde de `maximo`, igual que `bordeMinimo`. */
  readonly bordeMaximo: readonly PuntoPixel[];
}

/** Lo que necesita `calcularGeometriaTopes` para decidir dónde va cada tope. */
export interface ConfiguracionTopes {
  /** MISMA vista que recibió `pintarEjes`: `v0`/`v1` ya en la unidad MOSTRADA, no canónica (`render/tipos.ts#Vista`). */
  readonly vista: Vista;
  /** MISMA área que calculó `calcularGeometriaEjes` (`GeometriaEjes.area`): sin ella, los topes no alinean con la rejilla. */
  readonly area: AreaDibujo;
  /** La conversión activa del canal (canónica → mostrada). Clase PUNTO siempre, ver cabecera del módulo. */
  readonly conversion: Conversion;
  /** Parámetro de una conversión `parametrizada` (p. ej. estequiometría de λ→AFR), si aplica. */
  readonly parametro?: number;
  /** Cuántos decimales usar al formatear el valor de la etiqueta. Por omisión 2, igual que `formatearValorDeCanal`. */
  readonly decimales?: number;
  readonly lineas: readonly LineaTope[];
  readonly bandas: readonly BandaTope[];
}

/** Salida de `calcularGeometriaTopes`: todo lo que `topes.ts` necesita para pintar, ya resuelto a píxeles. */
export interface GeometriaTopes {
  readonly area: AreaDibujo;
  readonly lineas: readonly LineaResuelta[];
  readonly bandas: readonly BandaResuelta[];
}
