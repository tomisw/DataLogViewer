/**
 * Renderizador WebGL2 de series desde la pirámide (F1-23, ADR-006).
 *
 * LA DECISIÓN QUE HACE ALCANZABLE EL PRESUPUESTO
 * ==============================================
 * §2.6 pide «pan/zoom con 16 canales × 5 M puntos a ≥ 60 fps, sin fotograma
 * > 20 ms». Eso no se consigue dibujando rápido: se consigue **no subiendo
 * datos**. Los cubos de un nivel de pirámide viven en un búfer de la GPU y se
 * quedan ahí; mover o ampliar la vista escribe cuatro flotantes por serie
 * (`u_transformacion`) y vuelve a dibujar los mismos vértices. Un fotograma de
 * pan es, por serie, un `bindVertexArray`, dos `uniform4f` y un `drawArrays`.
 *
 * De ahí que `estadisticas.subidasDeBufer` sea una propiedad pública y que haya
 * un banco que la vigila: es el número que, si empieza a crecer con los
 * fotogramas, avisa de que alguien rompió la arquitectura mucho antes de que se
 * note como tirones en un portátil con GPU integrada.
 *
 * LO QUE ESTE MÓDULO NO SABE
 * ==========================
 * ADR-006: «el renderizador recibe cubos y una escala, y no sabe nada de logs,
 * unidades ni perfiles». No hay conversión de unidades aquí, ni elección de
 * canal, ni ejes: los ejes y la leyenda son SVG (F1-25) porque ahí no hay
 * volumen y sí hay texto que el propietario quiere poder leer y revisar.
 *
 * FUERA DE ALCANCE DE F1-23, A PROPÓSITO
 * ======================================
 * **Huecos y segmentos.** Una serie se dibuja como un único `LINE_STRIP`
 * continuo. Un log con hueco de adquisición (F1-08) o varios segmentos se
 * dibujaría con una recta atravesando el hueco, que es una lectura falsa. El
 * modelo de segmento y el eje X virtual son F2-01; hasta entonces, quien tenga
 * huecos debe subir un tramo por segmento con identificadores distintos. Queda
 * dicho aquí y en el informe de la tarea porque es justo la clase de detalle
 * que se pierde si solo vive en la cabeza de quien escribió el módulo.
 */

import type { ContextoGL } from "./contexto.ts";
import { expandirCubos, transformacion, validarCubos, VERTICES_POR_CUBO } from "./escala.ts";
import { crearProgramaSeries, type ProgramaSeries } from "./programa.ts";
import type { Color, CubosContinuos, Viewport, Vista } from "./tipos.ts";

const FLOTANTES_POR_VERTICE = 2;
const BYTES_POR_FLOTANTE = 4;

/**
 * Contadores de lo que hace el renderizador. Existen para el banco, no para
 * depurar: `subidasDeBufer` es la métrica que decide si la arquitectura sigue
 * siendo la que hace alcanzable §2.6.
 */
export interface Estadisticas {
  readonly fotogramas: number;
  readonly llamadasDeDibujo: number;
  readonly subidasDeBufer: number;
  readonly verticesDibujados: number;
}

interface SerieEnGpu {
  vao: WebGLVertexArrayObject;
  buffer: WebGLBuffer;
  nVertices: number;
  tOrigen: number;
  factor: number;
  color: Color;
}

/** Una serie ya subida, tal y como la ve quien pregunta desde fuera. */
export interface ResumenSerie {
  readonly id: string;
  readonly nVertices: number;
  readonly factor: number;
}

export class Renderizador {
  readonly #gl: ContextoGL;
  readonly #programa: ProgramaSeries;
  readonly #series = new Map<string, SerieEnGpu>();
  #viewport: Viewport = { ancho: 0, alto: 0 };
  #fotogramas = 0;
  #llamadasDeDibujo = 0;
  #subidasDeBufer = 0;
  #verticesDibujados = 0;
  #destruido = false;

  /**
   * Toma un contexto ya creado en vez de crearlo.
   *
   * Así el renderizador se prueba en Node contra un doble (`dobleGL`) sin
   * inventar un modo de pruebas dentro del propio renderizador: el código que
   * corre en la prueba es exactamente el que corre en el navegador. Para el
   * caso normal está `Renderizador.desdeLienzo`.
   */
  constructor(gl: ContextoGL) {
    this.#gl = gl;
    this.#programa = crearProgramaSeries(gl);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  }

  /**
   * Crea el contexto WebGL2 del lienzo y el renderizador sobre él.
   *
   * `antialias: false` y `alpha: false` a propósito: el suavizado del lienzo
   * cuesta relleno en una GPU integrada (la máquina de referencia de §2.6) y no
   * mejora un trazo de un píxel; el canal alfa del lienzo solo hace falta si
   * hay algo detrás, y detrás no hay nada.
   *
   * `desynchronized: true` reduce la latencia entre dibujar y ver, que es
   * exactamente lo que mide el presupuesto de cursor (< 16 ms).
   *
   * Si no hay WebGL2 se lanza con un mensaje que dice qué falta. No hay
   * repliegue a WebGL1 ni a lienzo 2D: ADR-006 elige WebGL2 y un repliegue
   * silencioso a algo diez veces más lento se diagnostica como «va lento a
   * veces», que es peor que un error.
   */
  static desdeLienzo(lienzo: HTMLCanvasElement): Renderizador {
    const gl = lienzo.getContext("webgl2", {
      antialias: false,
      alpha: false,
      depth: false,
      stencil: false,
      desynchronized: true,
      powerPreference: "high-performance",
    });
    if (gl === null) {
      throw new Error(
        "este navegador o esta GPU no ofrecen WebGL2, que es lo que usa el " +
          "renderizador de series (ADR-006). No hay repliegue: un lienzo 2D no " +
          "sostiene los presupuestos de §2.6.",
      );
    }
    return new Renderizador(gl);
  }

  get estadisticas(): Estadisticas {
    return {
      fotogramas: this.#fotogramas,
      llamadasDeDibujo: this.#llamadasDeDibujo,
      subidasDeBufer: this.#subidasDeBufer,
      verticesDibujados: this.#verticesDibujados,
    };
  }

  reiniciarEstadisticas(): void {
    this.#fotogramas = 0;
    this.#llamadasDeDibujo = 0;
    this.#subidasDeBufer = 0;
    this.#verticesDibujados = 0;
  }

  get series(): ResumenSerie[] {
    return [...this.#series].map(([id, s]) => ({
      id,
      nVertices: s.nVertices,
      factor: s.factor,
    }));
  }

  redimensionar(viewport: Viewport): void {
    this.#viewport = viewport;
    this.#gl.viewport(0, 0, viewport.ancho, viewport.alto);
  }

  /**
   * Sube (o vuelve a subir) los cubos de una serie a la GPU.
   *
   * Esto es lo caro y por eso tiene nombre propio y contador propio: pasa
   * cuando cambia el nivel de pirámide o el rango pedido, no cuando se mueve la
   * vista. Volver a llamarla con el mismo `id` reutiliza el búfer y el VAO en
   * vez de crear otros: crear un búfer por cambio de nivel, con pan continuo,
   * es una fuga de memoria de GPU que en un portátil se ve como un cuelgue a
   * los pocos minutos.
   */
  subirSerie(id: string, cubos: CubosContinuos, color: Color): void {
    this.#comprobarVivo();
    validarCubos(cubos);
    const gl = this.#gl;
    const vertices = expandirCubos(cubos);

    let serie = this.#series.get(id);
    if (serie === undefined) {
      const vao = gl.createVertexArray();
      const buffer = gl.createBuffer();
      if (vao === null || buffer === null) {
        gl.deleteVertexArray(vao);
        gl.deleteBuffer(buffer);
        throw new Error(`no se pudo reservar el búfer de la serie «${id}» en la GPU`);
      }
      serie = { vao, buffer, nVertices: 0, tOrigen: cubos.tOrigen, factor: cubos.factor, color };
      this.#series.set(id, serie);

      // El VAO recuerda el enlace del atributo, así que esta configuración se
      // hace UNA vez por serie y no en cada fotograma: dibujar se reduce a
      // `bindVertexArray`.
      gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.enableVertexAttribArray(this.#programa.atributoPunto);
      gl.vertexAttribPointer(
        this.#programa.atributoPunto,
        FLOTANTES_POR_VERTICE,
        gl.FLOAT,
        false,
        FLOTANTES_POR_VERTICE * BYTES_POR_FLOTANTE,
        0,
      );
    } else {
      gl.bindVertexArray(serie.vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, serie.buffer);
    }

    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
    this.#subidasDeBufer += 1;
    serie.nVertices = cubos.t.length * VERTICES_POR_CUBO;
    serie.tOrigen = cubos.tOrigen;
    serie.factor = cubos.factor;
    serie.color = color;
    gl.bindVertexArray(null);
  }

  /**
   * Cambia el color sin volver a subir nada.
   *
   * Existe porque el color es un uniforme, no un atributo: resaltar la serie
   * bajo el cursor no puede costar una subida de 16 KB por fotograma.
   */
  cambiarColor(id: string, color: Color): void {
    const serie = this.#series.get(id);
    if (serie === undefined) {
      throw new Error(`no hay ninguna serie subida con el identificador «${id}»`);
    }
    serie.color = color;
  }

  quitarSerie(id: string): void {
    const serie = this.#series.get(id);
    if (serie === undefined) return;
    this.#gl.deleteBuffer(serie.buffer);
    this.#gl.deleteVertexArray(serie.vao);
    this.#series.delete(id);
  }

  /**
   * Dibuja todas las series subidas con la vista dada.
   *
   * **No sube nada.** Es la propiedad que el banco comprueba y la que hace que
   * el presupuesto sea alcanzable con Python detrás: el pan/zoom que no sale
   * del rango ya cacheado no toca la red ni el bus de la GPU (ADR-007,
   * corolario de la caché de cubos en el frontend, F1-24).
   *
   * `vista` puede traer un rango de valores distinto por serie a través de
   * `vistaPorSerie`; sin él, todas comparten eje Y. Los ejes Y múltiples son
   * F1-27, y esta es la puerta que va a usar.
   */
  dibujar(vista: Vista, vistaPorSerie?: ReadonlyMap<string, Vista>): void {
    this.#comprobarVivo();
    const gl = this.#gl;
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.#programa.programa);

    for (const [id, serie] of this.#series) {
      if (serie.nVertices === 0) continue;
      const vistaSerie = vistaPorSerie?.get(id) ?? vista;
      const t = transformacion(serie.tOrigen, vistaSerie);
      gl.bindVertexArray(serie.vao);
      gl.uniform4f(
        this.#programa.uniformeTransformacion,
        t.escalaX,
        t.despX,
        t.escalaY,
        t.despY,
      );
      gl.uniform4f(
        this.#programa.uniformeColor,
        serie.color.r,
        serie.color.g,
        serie.color.b,
        serie.color.a,
      );
      gl.drawArrays(gl.LINE_STRIP, 0, serie.nVertices);
      this.#llamadasDeDibujo += 1;
      this.#verticesDibujados += serie.nVertices;
    }
    gl.bindVertexArray(null);
    this.#fotogramas += 1;
  }

  get viewport(): Viewport {
    return this.#viewport;
  }

  /**
   * Libera todo lo que hay en la GPU.
   *
   * Hace falta de verdad, no es higiene: §2.6 pide «8 logs × 30 min en paralelo
   * sin degradación perceptible», y ocho lienzos que no liberan sus búferes al
   * cerrarse agotan la memoria de una GPU integrada.
   */
  destruir(): void {
    if (this.#destruido) return;
    for (const id of [...this.#series.keys()]) this.quitarSerie(id);
    this.#gl.deleteProgram(this.#programa.programa);
    this.#destruido = true;
  }

  #comprobarVivo(): void {
    if (this.#destruido) {
      throw new Error("este renderizador ya se destruyó: sus recursos de GPU no existen");
    }
  }
}

/**
 * Ajusta el tamaño del lienzo al de su caja CSS por el ratio de píxeles, y
 * devuelve el viewport resultante.
 *
 * Separado de la clase porque toca el DOM y la clase no: así el renderizador
 * sigue probándose sin navegador. El `Math.max(1, …)` evita un lienzo de 0×0,
 * que en algunos controladores no es un error sino un contexto perdido.
 */
export function ajustarLienzo(lienzo: HTMLCanvasElement, dpr: number): Viewport {
  const caja = lienzo.getBoundingClientRect();
  const ancho = Math.max(1, Math.round(caja.width * dpr));
  const alto = Math.max(1, Math.round(caja.height * dpr));
  if (lienzo.width !== ancho) lienzo.width = ancho;
  if (lienzo.height !== alto) lienzo.height = alto;
  return { ancho, alto };
}
