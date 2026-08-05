/**
 * Los dos shaders del renderizador y su compilación, con errores que se leen.
 *
 * Los shaders son minúsculos a propósito. Todo lo que se pueda decidir en la
 * CPU una vez por fotograma (la transformación, el color) entra como uniforme;
 * el shader solo aplica una recta. Un shader con lógica dentro es código que no
 * se puede depurar con un `console.log`, y ADR-006 ya reconoce que esta es la
 * parte que el propietario no puede revisar cómodamente: cuanto menos haya
 * dentro, mejor.
 */

import type { ContextoGL } from "./contexto.ts";

/**
 * `x = t·escalaX + despX`, `y = valor·escalaY + despY`, con los cuatro
 * coeficientes en un solo `vec4`.
 *
 * Ese `vec4` es la clave del presupuesto de §2.6: mover la vista escribe cuatro
 * flotantes, no vuelve a subir datos. El eje Y no se invierte aquí porque las
 * coordenadas de recorte de OpenGL ya crecen hacia arriba, que es lo que se
 * quiere para un valor; el que crece hacia abajo es el sistema del DOM, y esa
 * conversión es problema de la capa SVG (F1-25), no de esta.
 */
export const FUENTE_VERTICE = `#version 300 es
in vec2 a_punto;
uniform vec4 u_transformacion;

void main() {
  gl_Position = vec4(
    a_punto.x * u_transformacion.x + u_transformacion.y,
    a_punto.y * u_transformacion.z + u_transformacion.w,
    0.0,
    1.0
  );
}
`;

export const FUENTE_FRAGMENTO = `#version 300 es
precision highp float;
uniform vec4 u_color;
out vec4 color_salida;

void main() {
  color_salida = u_color;
}
`;

export const ATRIBUTO_PUNTO = "a_punto";
export const UNIFORME_TRANSFORMACION = "u_transformacion";
export const UNIFORME_COLOR = "u_color";

function compilar(gl: ContextoGL, tipo: number, fuente: string, nombre: string): WebGLShader {
  const shader = gl.createShader(tipo);
  if (shader === null) {
    throw new Error(`no se pudo crear el shader de ${nombre} (¿contexto WebGL2 perdido?)`);
  }
  gl.shaderSource(shader, fuente);
  gl.compileShader(shader);
  if (gl.getShaderParameter(shader, gl.COMPILE_STATUS) !== true) {
    // El registro se lee ANTES de borrar el shader: al revés se pierde, y un
    // "no compila" sin el motivo es lo mismo que no tener el error.
    const registro = gl.getShaderInfoLog(shader) ?? "(sin registro del controlador)";
    gl.deleteShader(shader);
    throw new Error(`el shader de ${nombre} no compila:\n${registro}`);
  }
  return shader;
}

/** Programa enlazado y los sitios de sus atributos y uniformes. */
export interface ProgramaSeries {
  readonly programa: WebGLProgram;
  readonly atributoPunto: number;
  readonly uniformeTransformacion: WebGLUniformLocation | null;
  readonly uniformeColor: WebGLUniformLocation | null;
}

/**
 * Compila y enlaza el programa de series.
 *
 * Los shaders se borran en cuanto el programa está enlazado: el programa ya
 * tiene su copia y dejarlos vivos es una fuga que solo se nota con muchos
 * lienzos abiertos, que es exactamente el caso de «8 logs en paralelo» de §2.6.
 */
export function crearProgramaSeries(gl: ContextoGL): ProgramaSeries {
  const vertice = compilar(gl, gl.VERTEX_SHADER, FUENTE_VERTICE, "vértice");
  let fragmento: WebGLShader;
  try {
    fragmento = compilar(gl, gl.FRAGMENT_SHADER, FUENTE_FRAGMENTO, "fragmento");
  } catch (error) {
    gl.deleteShader(vertice);
    throw error;
  }

  const programa = gl.createProgram();
  if (programa === null) {
    gl.deleteShader(vertice);
    gl.deleteShader(fragmento);
    throw new Error("no se pudo crear el programa (¿contexto WebGL2 perdido?)");
  }
  gl.attachShader(programa, vertice);
  gl.attachShader(programa, fragmento);
  gl.linkProgram(programa);
  gl.deleteShader(vertice);
  gl.deleteShader(fragmento);

  if (gl.getProgramParameter(programa, gl.LINK_STATUS) !== true) {
    const registro = gl.getProgramInfoLog(programa) ?? "(sin registro del controlador)";
    gl.deleteProgram(programa);
    throw new Error(`el programa de series no enlaza:\n${registro}`);
  }

  const atributoPunto = gl.getAttribLocation(programa, ATRIBUTO_PUNTO);
  if (atributoPunto < 0) {
    gl.deleteProgram(programa);
    throw new Error(`el programa enlazó pero no expone el atributo \`${ATRIBUTO_PUNTO}\``);
  }

  return {
    programa,
    atributoPunto,
    uniformeTransformacion: gl.getUniformLocation(programa, UNIFORME_TRANSFORMACION),
    uniformeColor: gl.getUniformLocation(programa, UNIFORME_COLOR),
  };
}
