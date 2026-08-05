/**
 * La superficie de WebGL2 que usa el renderizador. Nada más.
 *
 * ADR-006 pide «una superficie de API deliberadamente pequeña» porque es la
 * compensación por no poder revisar cómodamente esta parte. Este fichero es esa
 * superficie hecha explícita: si `renderizador.ts` necesitara un `texImage2D` o
 * un `readPixels`, tendría que añadirlo aquí primero, y el `diff` lo enseñaría.
 *
 * `WebGL2RenderingContext` cumple esta interfaz estructuralmente —las constantes
 * viven en su prototipo— así que el contexto real se pasa sin adaptador. La
 * ventaja es la otra dirección: un doble de pruebas también la cumple, y eso
 * permite probar en Node, sin GPU, la única propiedad del renderizador que
 * decide si el presupuesto de 60 fps es alcanzable (cuántas veces se sube un
 * búfer por fotograma).
 */

export interface ContextoGL {
  readonly ARRAY_BUFFER: number;
  readonly BLEND: number;
  readonly COLOR_BUFFER_BIT: number;
  readonly COMPILE_STATUS: number;
  readonly FLOAT: number;
  readonly FRAGMENT_SHADER: number;
  readonly LINE_STRIP: number;
  readonly LINK_STATUS: number;
  readonly ONE_MINUS_SRC_ALPHA: number;
  readonly SRC_ALPHA: number;
  readonly STATIC_DRAW: number;
  readonly VERTEX_SHADER: number;

  createShader(tipo: number): WebGLShader | null;
  shaderSource(shader: WebGLShader, fuente: string): void;
  compileShader(shader: WebGLShader): void;
  getShaderParameter(shader: WebGLShader, parametro: number): unknown;
  getShaderInfoLog(shader: WebGLShader): string | null;
  deleteShader(shader: WebGLShader | null): void;

  createProgram(): WebGLProgram | null;
  attachShader(programa: WebGLProgram, shader: WebGLShader): void;
  linkProgram(programa: WebGLProgram): void;
  getProgramParameter(programa: WebGLProgram, parametro: number): unknown;
  getProgramInfoLog(programa: WebGLProgram): string | null;
  deleteProgram(programa: WebGLProgram | null): void;
  useProgram(programa: WebGLProgram | null): void;
  getAttribLocation(programa: WebGLProgram, nombre: string): number;
  getUniformLocation(programa: WebGLProgram, nombre: string): WebGLUniformLocation | null;

  createBuffer(): WebGLBuffer | null;
  bindBuffer(destino: number, buffer: WebGLBuffer | null): void;
  // `ArrayBufferView` y no `BufferSource`: desde TypeScript 5.7 los arrays
  // tipados llevan el tipo de su búfer como parámetro genérico, y `BufferSource`
  // fija `ArrayBuffer`, así que un `Float32Array` declarado sin parámetro —el
  // que devuelve `expandirCubos`— deja de encajar. `ArrayBufferView` acepta
  // ambos y `WebGL2RenderingContext` sigue cumpliendo esta interfaz.
  bufferData(destino: number, datos: ArrayBufferView, uso: number): void;
  deleteBuffer(buffer: WebGLBuffer | null): void;

  createVertexArray(): WebGLVertexArrayObject | null;
  bindVertexArray(vao: WebGLVertexArrayObject | null): void;
  deleteVertexArray(vao: WebGLVertexArrayObject | null): void;
  enableVertexAttribArray(indice: number): void;
  vertexAttribPointer(
    indice: number,
    tamano: number,
    tipo: number,
    normalizado: boolean,
    paso: number,
    desplazamiento: number,
  ): void;

  uniform4f(sitio: WebGLUniformLocation | null, a: number, b: number, c: number, d: number): void;

  viewport(x: number, y: number, ancho: number, alto: number): void;
  clearColor(r: number, g: number, b: number, a: number): void;
  clear(mascara: number): void;
  enable(capacidad: number): void;
  blendFunc(origen: number, destino: number): void;
  drawArrays(modo: number, primero: number, cuenta: number): void;
}
