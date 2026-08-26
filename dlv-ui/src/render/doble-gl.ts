/**
 * Un doble de `WebGL2RenderingContext` que registra lo que se le pide.
 *
 * Por qué existe: la propiedad del renderizador que decide si §2.6 es
 * alcanzable no es visual, es de contabilidad —«un fotograma de pan no sube
 * datos a la GPU»—, y eso se puede comprobar sin GPU, en cada `npm test`, en
 * milisegundos. Esperar a la regresión visual (F5-12) para enterarse de que
 * alguien metió un `bufferData` dentro del bucle de dibujo sería enterarse
 * tarde y por el síntoma equivocado.
 *
 * No emula OpenGL: emula lo justo para que el renderizador funcione y para
 * poder afirmar en qué orden hizo las llamadas. Lo que este doble NO puede
 * decir es si el resultado se ve bien; eso es F5-12, con navegador de verdad,
 * y es obligatorio por ADR-006 precisamente porque esto no lo cubre.
 *
 * Vive en `src/` y no en un directorio de pruebas porque `tsconfig.json` solo
 * incluye `src`, y un doble sin comprobación de tipos estricta es un doble que
 * deja de parecerse a la interfaz real sin avisar.
 */

import type { ContextoGL } from "./contexto.ts";

export interface Llamada {
  readonly nombre: string;
  readonly argumentos: readonly unknown[];
}

export interface DobleGL extends ContextoGL {
  /** Todas las llamadas, en orden. */
  readonly llamadas: Llamada[];
  /** Cuántas veces se llamó a `nombre`. */
  cuenta(nombre: string): number;
  /** Vacía el registro; útil para medir "por fotograma" y no acumulado. */
  olvidar(): void;
  /**
   * Hace que el siguiente `getShaderParameter`/`getProgramParameter` diga que
   * falló, para probar la ruta de error sin un shader roto de verdad.
   */
  fallarCompilacion: boolean;
  fallarEnlace: boolean;
  /**
   * Cuántas veces se llamó a `loseContext()` de `WEBGL_lose_context` sobre
   * ESTE contexto. Es lo que prueba que conmutar de vista (`app/vistas.ts`)
   * libera de verdad lo que reservó, sin GPU: cada `Aplicacion.destruir()` /
   * `#reconstruir(null)` tiene que dejar este contador en 1, nunca en 0
   * (fuga) y el ciclo de montar/desmontar repetido nunca debería volver a
   * subir sobre el MISMO doble (cada vista nueva trae un doble nuevo).
   */
  contextosPerdidos: number;
  /**
   * Solo `"WEBGL_lose_context"` (F5-11): `app/aplicacion.ts#reconstruir`
   * la pide sobre CADA canvas que destruye, para liberar el contexto antes de
   * agotar el puñado que un navegador garantiza vivos a la vez (16 en
   * Chrome/Edge). Ninguna prueba había reconstruido paneles dos veces sobre
   * el mismo `Aplicacion` hasta la propuesta de perfil de F5-11 -- aceptarla o
   * descartarla cambia la selección de canales después del montaje inicial,
   * que es justo el camino que llama a esto -- así que el hueco (`ContextoGL`
   * no la declaraba: `Renderizador` nunca la necesita) estaba sin avisar.
   * Cualquier otro nombre de extensión devuelve `null`, como el navegador real
   * cuando no la reconoce.
   *
   * Ojo con el `?.` de esa línea: protege el OBJETO devuelto por `getContext`,
   * NO un método que ese objeto no tenga. Mientras el doble no implementaba
   * esto, la llamada lanzaba `TypeError` bajo prueba.
   */
  getExtension(nombre: string): { loseContext(): void } | null;
}

/**
 * Constantes de WebGL2. Los valores son los reales del estándar, no inventados:
 * si el doble usara valores propios, una prueba podría pasar con un `gl.FLOAT`
 * donde el código real necesita `gl.LINE_STRIP` y nadie se enteraría.
 */
const CONSTANTES = {
  ARRAY_BUFFER: 0x8892,
  BLEND: 0x0be2,
  COLOR_BUFFER_BIT: 0x00004000,
  COMPILE_STATUS: 0x8b81,
  FLOAT: 0x1406,
  FRAGMENT_SHADER: 0x8b30,
  LINE_STRIP: 0x0003,
  LINK_STATUS: 0x8b82,
  ONE_MINUS_SRC_ALPHA: 0x0303,
  SRC_ALPHA: 0x0302,
  STATIC_DRAW: 0x88e4,
  VERTEX_SHADER: 0x8b31,
} as const;

export function crearDobleGL(): DobleGL {
  const llamadas: Llamada[] = [];
  let siguienteObjeto = 1;

  function registrar(nombre: string, ...argumentos: unknown[]): void {
    llamadas.push({ nombre, argumentos });
  }
  function objeto<T>(etiqueta: string): T {
    return { __doble: etiqueta, __id: siguienteObjeto++ } as unknown as T;
  }

  const doble: DobleGL = {
    ...CONSTANTES,
    llamadas,
    fallarCompilacion: false,
    fallarEnlace: false,
    contextosPerdidos: 0,
    cuenta: (nombre) => llamadas.filter((l) => l.nombre === nombre).length,
    olvidar: () => {
      llamadas.length = 0;
    },
    getExtension: (nombre) => {
      registrar("getExtension", nombre);
      if (nombre !== "WEBGL_lose_context") return null;
      return {
        loseContext: () => {
          registrar("loseContext");
          doble.contextosPerdidos += 1;
        },
      };
    },

    createShader: (tipo) => {
      registrar("createShader", tipo);
      return objeto<WebGLShader>("shader");
    },
    shaderSource: (s, fuente) => registrar("shaderSource", s, fuente),
    compileShader: (s) => registrar("compileShader", s),
    getShaderParameter: (s, p) => {
      registrar("getShaderParameter", s, p);
      return !doble.fallarCompilacion;
    },
    getShaderInfoLog: () => "registro simulado del doble",
    deleteShader: (s) => registrar("deleteShader", s),

    createProgram: () => {
      registrar("createProgram");
      return objeto<WebGLProgram>("programa");
    },
    attachShader: (p, s) => registrar("attachShader", p, s),
    linkProgram: (p) => registrar("linkProgram", p),
    getProgramParameter: (p, n) => {
      registrar("getProgramParameter", p, n);
      return !doble.fallarEnlace;
    },
    getProgramInfoLog: () => "registro simulado del doble",
    deleteProgram: (p) => registrar("deleteProgram", p),
    useProgram: (p) => registrar("useProgram", p),
    getAttribLocation: (p, nombre) => {
      registrar("getAttribLocation", p, nombre);
      return 0;
    },
    getUniformLocation: (p, nombre) => {
      registrar("getUniformLocation", p, nombre);
      return objeto<WebGLUniformLocation>(`uniforme:${nombre}`);
    },

    createBuffer: () => {
      registrar("createBuffer");
      return objeto<WebGLBuffer>("buffer");
    },
    bindBuffer: (destino, b) => registrar("bindBuffer", destino, b),
    bufferData: (destino, datos, uso) => registrar("bufferData", destino, datos, uso),
    deleteBuffer: (b) => registrar("deleteBuffer", b),

    createVertexArray: () => {
      registrar("createVertexArray");
      return objeto<WebGLVertexArrayObject>("vao");
    },
    bindVertexArray: (v) => registrar("bindVertexArray", v),
    deleteVertexArray: (v) => registrar("deleteVertexArray", v),
    enableVertexAttribArray: (i) => registrar("enableVertexAttribArray", i),
    vertexAttribPointer: (i, tam, tipo, norm, paso, desp) =>
      registrar("vertexAttribPointer", i, tam, tipo, norm, paso, desp),

    uniform4f: (sitio, a, b, c, d) => registrar("uniform4f", sitio, a, b, c, d),

    viewport: (x, y, ancho, alto) => registrar("viewport", x, y, ancho, alto),
    clearColor: (r, g, b, a) => registrar("clearColor", r, g, b, a),
    clear: (m) => registrar("clear", m),
    enable: (c) => registrar("enable", c),
    blendFunc: (o, d) => registrar("blendFunc", o, d),
    drawArrays: (modo, primero, cuenta) => registrar("drawArrays", modo, primero, cuenta),
  };
  return doble;
}
