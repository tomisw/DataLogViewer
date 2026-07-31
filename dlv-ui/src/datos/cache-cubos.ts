/**
 * Caché de cubos en el frontend (F1-24).
 *
 * POR QUÉ ESTO EXISTE
 * ===================
 * ADR-007 lo llama «el corolario que hace viable el presupuesto de cursor con
 * Python detrás»:
 *
 *     «el frontend cachea los cubos visibles, así que mover el cursor es una
 *     búsqueda local en un `TypedArray` sin ida y vuelta al backend. Solo el
 *     pan/zoom que sale del rango cacheado pide datos nuevos, y ese tiene un
 *     presupuesto distinto y más holgado.»
 *
 * Sin esta caché, §2.6 pide dos cosas incompatibles: «latencia del cursor a
 * tabla actualizada < 16 ms» y un backend Python al otro lado de HTTP. 16 ms no
 * dan para una petición HTTP, un `read_ipc` y una respuesta, y menos con 16
 * canales a la vez. Con la caché, mover el cursor no habla con nadie: es una
 * búsqueda binaria sobre un array que ya está en memoria.
 *
 * LAS TRES DECISIONES QUE TIENE DENTRO
 * ====================================
 * 1. **La clave incluye el nivel de pirámide**, no solo el canal. Dos zooms
 *    distintos del mismo canal son datos distintos; mezclarlos daría un cursor
 *    que lee del nivel equivocado y enseña un valor decimado como si fuera el
 *    real —el peor fallo posible en una herramienta de tuning, porque es
 *    plausible—.
 * 2. **Se pide con margen.** Un pan continuo saca la vista del rango cacheado
 *    cada pocos píxeles; pedir exactamente lo visible convertiría cada
 *    fotograma de pan en una petición. Con margen, la mayoría de los pans caen
 *    dentro de lo que ya hay.
 * 3. **Se desaloja por bytes, no por número de entradas.** Lo que se agota es
 *    la memoria, y una entrada puede ser 8 KB o 8 MB. §2.6 pide «8 logs × 30
 *    min en paralelo sin degradación perceptible», y ocho logs × 475 canales
 *    con una caché sin tope es la forma más directa de incumplirlo.
 *
 * LO QUE NO HACE, Y ES DELIBERADO
 * ===============================
 * **No cose rangos parciales.** Si lo cacheado cubre media vista, se vuelve a
 * pedir la vista entera con margen en vez de pedir solo el trozo que falta y
 * concatenarlo. Coser ahorraría tráfico en un pan largo y continuo, pero mete
 * en el frontend una lógica de fusión de rangos con sus propios casos límite
 * (solapes parciales, huecos, niveles distintos) para optimizar un camino que
 * ya tiene un presupuesto holgado (§2.6: «pan/zoom que requiere cubos nuevos
 * del backend < 120 ms p95»). Si ese presupuesto se pone en rojo, coser es lo
 * primero que hay que probar; hasta entonces, el margen es lo que absorbe el
 * pan y es mucho más simple de revisar.
 */

import type { CubosContinuos } from "../render/tipos.ts";

/** Un canal a un nivel de pirámide concreto. Las dos cosas, no solo el canal. */
export interface ClaveCubos {
  readonly canal: string;
  /** Factor de decimación del nivel (1, 4, 16, …). */
  readonly factor: number;
}

/** Un tramo de tiempo en segundos absolutos. */
export interface Rango {
  readonly t0: number;
  readonly t1: number;
}

/** Lo que hay guardado bajo una clave: los cubos y el tramo que cubren. */
export interface EntradaCache {
  readonly cubos: CubosContinuos;
  /** Tramo REALMENTE cubierto, que es lo que se pidió, no lo que se ve. */
  readonly cubre: Rango;
}

export type Resultado =
  | { readonly estado: "acierto"; readonly entrada: EntradaCache }
  /**
   * `pedir` es el rango ya ensanchado con el margen: quien llama lo manda tal
   * cual al backend. Que el ensanchado lo decida la caché y no quien la usa
   * evita que dos sitios distintos elijan márgenes distintos y que el acierto
   * dependa de por dónde se entró.
   */
  | { readonly estado: "fallo"; readonly pedir: Rango };

export interface EstadisticasCache {
  readonly aciertos: number;
  readonly fallos: number;
  readonly desalojos: number;
  readonly entradas: number;
  readonly bytes: number;
}

const BYTES_POR_FLOTANTE = 4;
const ARRAYS_POR_CUBO = 5; // t, minimo, maximo, primero, ultimo

/** Cuánta memoria ocupa una entrada. Es lo que gobierna el desalojo. */
export function bytesDe(cubos: CubosContinuos): number {
  return cubos.t.length * ARRAYS_POR_CUBO * BYTES_POR_FLOTANTE;
}

export interface OpcionesCache {
  /**
   * Tope de memoria. 64 MB por omisión: con cubos de ~2000 entradas (40 KB)
   * caben del orden de mil combinaciones canal×nivel, que es holgado para los
   * 475 canales de un log y para los ocho logs en paralelo de §2.6, y sigue
   * siendo una fracción de lo que ya ocupa el propio log.
   */
  readonly bytesMaximos?: number;
  /**
   * Cuánto se ensancha el rango pedido, en múltiplos del ancho visible y a cada
   * lado. 0,5 por omisión: se piden tres anchos de pantalla, así que un pan
   * puede recorrer una pantalla entera en cualquier dirección sin volver a
   * pedir. Subirlo hace los pans más suaves y las peticiones más caras; es la
   * perilla que se toca si el presupuesto de 120 ms p95 se pone en rojo.
   */
  readonly margen?: number;
}

export class CacheDeCubos {
  readonly #bytesMaximos: number;
  readonly #margen: number;
  /**
   * `Map` y no un objeto: `Map` conserva el orden de inserción, y eso es
   * exactamente lo que hace falta para un LRU —basta con borrar y reinsertar
   * la clave usada para llevarla al final—. Sin estructura extra ni contador
   * de accesos.
   */
  readonly #entradas = new Map<string, EntradaCache>();
  #bytes = 0;
  #aciertos = 0;
  #fallos = 0;
  #desalojos = 0;

  constructor(opciones: OpcionesCache = {}) {
    this.#bytesMaximos = opciones.bytesMaximos ?? 64 * 1024 * 1024;
    this.#margen = opciones.margen ?? 0.5;
    if (this.#bytesMaximos <= 0) {
      throw new Error("`bytesMaximos` tiene que ser positivo: una caché de 0 bytes es no tenerla");
    }
    if (this.#margen < 0) {
      throw new Error("`margen` no puede ser negativo: pediría menos de lo que se ve");
    }
  }

  /**
   * ¿Están ya los cubos que cubren `visible`?
   *
   * Un acierto exige cobertura COMPLETA del rango visible. Devolver una
   * cobertura parcial como acierto dibujaría medio panel y dejaría la otra
   * mitad en blanco sin decir por qué, que se diagnostica como "el log está
   * cortado" en vez de como "falta pedir datos".
   */
  consultar(clave: ClaveCubos, visible: Rango): Resultado {
    const k = claveTexto(clave);
    const entrada = this.#entradas.get(k);
    if (entrada !== undefined && cubre(entrada.cubre, visible)) {
      // Reinsertar = marcar como recién usada (ver el comentario de `#entradas`).
      this.#entradas.delete(k);
      this.#entradas.set(k, entrada);
      this.#aciertos += 1;
      return { estado: "acierto", entrada };
    }
    this.#fallos += 1;
    return { estado: "fallo", pedir: ensanchar(visible, this.#margen) };
  }

  /** Lo que ya está guardado bajo esta clave, sin contar acierto ni fallo. */
  mirar(clave: ClaveCubos): EntradaCache | undefined {
    return this.#entradas.get(claveTexto(clave));
  }

  /**
   * Guarda (o reemplaza) los cubos de una clave.
   *
   * Reemplazar y no acumular: una clave guarda un único tramo contiguo, que es
   * la simplificación que documenta la cabecera del módulo.
   */
  guardar(clave: ClaveCubos, entrada: EntradaCache): void {
    if (entrada.cubre.t1 < entrada.cubre.t0) {
      throw new Error("el tramo cubierto está del revés (`t1` < `t0`)");
    }
    const k = claveTexto(clave);
    const anterior = this.#entradas.get(k);
    if (anterior !== undefined) this.#bytes -= bytesDe(anterior.cubos);
    this.#entradas.delete(k);
    this.#entradas.set(k, entrada);
    this.#bytes += bytesDe(entrada.cubos);
    this.#desalojarHastaCaber(k);
  }

  /**
   * Tira lo de un canal (todos sus niveles) o la caché entera.
   *
   * Hace falta al cerrar un log y al cambiar algo que altera los VALORES, no la
   * vista. Ojo con lo que NO debe invalidar: **cambiar de unidad no invalida
   * nada**. §2.6 lo pide explícitamente («cambio de unidad con 8 logs abiertos
   * < 100 ms, sin recarga ni invalidación de caché») y §6 explica por qué: un
   * cambio de unidad es un repintado con otra escala, no otros datos. Si algún
   * día alguien llama a esto desde el selector de unidad, ese presupuesto se
   * cae de golpe y el síntoma será "la aplicación se congela al cambiar de bar
   * a psi".
   */
  invalidar(canal?: string): void {
    if (canal === undefined) {
      this.#entradas.clear();
      this.#bytes = 0;
      return;
    }
    const prefijo = `${canal} `;
    for (const [k, entrada] of [...this.#entradas]) {
      if (k.startsWith(prefijo)) {
        this.#bytes -= bytesDe(entrada.cubos);
        this.#entradas.delete(k);
      }
    }
  }

  get estadisticas(): EstadisticasCache {
    return {
      aciertos: this.#aciertos,
      fallos: this.#fallos,
      desalojos: this.#desalojos,
      entradas: this.#entradas.size,
      bytes: this.#bytes,
    };
  }

  reiniciarEstadisticas(): void {
    this.#aciertos = 0;
    this.#fallos = 0;
    this.#desalojos = 0;
  }

  /**
   * Desaloja los menos usados hasta caber, sin tirar nunca lo que se acaba de
   * guardar: si una sola entrada ya no cabe, la alternativa a conservarla sería
   * guardarla y borrarla en el mismo acto, y entonces cada consulta sería un
   * fallo y la caché haría más daño que bien. En ese caso se supera el tope y
   * `estadisticas.bytes` lo enseña, que es lo que hay que ver.
   */
  #desalojarHastaCaber(protegida: string): void {
    for (const [k, entrada] of this.#entradas) {
      if (this.#bytes <= this.#bytesMaximos) return;
      if (k === protegida) continue;
      this.#bytes -= bytesDe(entrada.cubos);
      this.#entradas.delete(k);
      this.#desalojos += 1;
    }
  }
}

function claveTexto(clave: ClaveCubos): string {
  // El espacio SÍ aparece en los nombres de canal Haltech ("Coolant
  // Temperature"), así que lo que hace inequívoca esta clave no es que el
  // separador sea raro: es que el factor es un número sin espacios y va al
  // final, de modo que el ÚLTIMO espacio siempre separa canal de factor y dos
  // claves distintas no pueden producir el mismo texto.
  return `${clave.canal} ${clave.factor}`;
}

function cubre(disponible: Rango, pedido: Rango): boolean {
  return disponible.t0 <= pedido.t0 && disponible.t1 >= pedido.t1;
}

function ensanchar(rango: Rango, margen: number): Rango {
  const extra = (rango.t1 - rango.t0) * margen;
  return { t0: rango.t0 - extra, t1: rango.t1 + extra };
}

/**
 * Índice del cubo que contiene `tAbsoluto`, por búsqueda binaria.
 *
 * **Esta función es el presupuesto de cursor.** Mover el cursor con 16 canales
 * son 16 llamadas a esto: unas 11 comparaciones cada una con 2000 cubos, del
 * orden de microsegundos en total, contra los > 16 ms que costaría una ida y
 * vuelta a Python. Por eso está aquí y no en el backend.
 *
 * Devuelve el índice del último cubo cuyo instante es `<= tAbsoluto` (el cubo
 * "vigente"), y `-1` si `tAbsoluto` es anterior al primer cubo. Vigente y no
 * "el más cercano": un cubo empieza en su instante y dura hasta el siguiente,
 * así que el valor que corresponde a un instante es el del cubo que ya empezó.
 * Redondear al más cercano adelantaría el valor hasta medio cubo, y a nivel
 * grueso medio cubo son segundos.
 */
export function indiceEn(cubos: CubosContinuos, tAbsoluto: number): number {
  const objetivo = tAbsoluto - cubos.tOrigen;
  const t = cubos.t;
  let bajo = 0;
  let alto = t.length - 1;
  let respuesta = -1;
  while (bajo <= alto) {
    const medio = (bajo + alto) >> 1;
    if (t[medio]! <= objetivo) {
      respuesta = medio;
      bajo = medio + 1;
    } else {
      alto = medio - 1;
    }
  }
  return respuesta;
}

/** El cubo vigente en un instante, o `null` si el instante cae fuera. */
export interface ValorEnCursor {
  readonly indice: number;
  readonly minimo: number;
  readonly maximo: number;
  readonly primero: number;
  readonly ultimo: number;
}

/**
 * Lo que hay que enseñar en la tabla del cursor para un instante.
 *
 * Devuelve los cuatro números del cubo y no uno solo a propósito: a un nivel
 * decimado, "el valor" no existe —lo que hay es un rango—. Enseñar solo
 * `ultimo` como si fuera "el valor" oculta que en ese píxel hubo un pico de
 * 900 °C, y la tabla del cursor es justo donde se mira para decidir. Quién
 * enseña qué es cosa de F1-29; lo que este módulo garantiza es que la
 * información no se pierde antes de llegar allí.
 */
export function valorEn(cubos: CubosContinuos, tAbsoluto: number): ValorEnCursor | null {
  const i = indiceEn(cubos, tAbsoluto);
  if (i < 0) return null;
  return {
    indice: i,
    minimo: cubos.minimo[i]!,
    maximo: cubos.maximo[i]!,
    primero: cubos.primero[i]!,
    ultimo: cubos.ultimo[i]!,
  };
}
