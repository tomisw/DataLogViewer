/**
 * La aritmética del renderizador, separada del contexto WebGL a propósito.
 *
 * Todo lo que se puede equivocar en silencio —elegir el nivel de pirámide
 * equivocado, perder un pico al decimar, invertir un eje— vive aquí, en
 * funciones puras que se prueban sin GPU. Lo que queda en `renderizador.ts` es
 * la fontanería de OpenGL, que falla ruidosamente cuando falla.
 *
 * Es la respuesta concreta al problema que ADR-006 admite: el renderizador es
 * «la única parte del código que el propietario no puede revisar con
 * comodidad». Un shader no se revisa leyendo; una función que convierte
 * segundos en coordenadas de recorte, sí.
 */

import type { CubosContinuos, Vista } from "./tipos.ts";

/**
 * Los cuatro números que llevan un punto de datos a coordenadas de recorte:
 * `x = t_relativo * escalaX + despX`, `y = valor * escalaY + despY`.
 *
 * Que la transformación quepa en un `vec4` es lo que hace alcanzable el
 * presupuesto de §2.6 («pan/zoom con 16 canales × 5 M puntos ≥ 60 fps»):
 * mover la vista es escribir cuatro flotantes por serie, no volver a subir
 * datos a la GPU. Los datos se suben una vez por nivel de pirámide y se
 * quedan ahí.
 */
export interface Transformacion {
  readonly escalaX: number;
  readonly despX: number;
  readonly escalaY: number;
  readonly despY: number;
}

/** Un nivel de la pirámide visto por `elegirNivel`: solo lo que necesita. */
export interface ResumenNivel {
  /** Factor de decimación acumulado (1, 4, 16, …). */
  readonly factor: number;
  /** Cuántos cubos tiene el nivel en TODO el log, no en la vista. */
  readonly nCubos: number;
}

/**
 * Transformación de datos a coordenadas de recorte para una serie concreta.
 *
 * Recibe `tOrigen` suelto y no el cubo entero porque el renderizador la llama
 * una vez por serie y por fotograma, cuando ya no tiene los arrays a mano
 * —solo el origen que guardó al subirlos—. Pedirle el cubo obligaría a
 * conservar una referencia a datos que ya viven en la GPU.
 *
 * `tOrigen` entra en la cuenta en doble precisión y sale ya convertido a un
 * desplazamiento pequeño, que es justo lo que evita el temblor al ampliar
 * mucho: si el shader recibiera el instante absoluto en `float32` y le restara
 * `t0` también en `float32`, la resta de dos números grandes y parecidos se
 * comería los dígitos que importan.
 *
 * Un rango degenerado (`t1 === t0` o `v1 === v0`) daría infinito. Se trata como
 * lo que es —una vista sin anchura— y devuelve escala 0: la serie se colapsa a
 * una línea en el centro en vez de desaparecer con `NaN`, que en WebGL no da
 * error, solo un lienzo en blanco inexplicable.
 */
export function transformacion(tOrigen: number, vista: Vista): Transformacion {
  const anchoT = vista.t1 - vista.t0;
  const altoV = vista.v1 - vista.v0;
  const escalaX = anchoT === 0 ? 0 : 2 / anchoT;
  const escalaY = altoV === 0 ? 0 : 2 / altoV;
  return {
    escalaX,
    despX: (tOrigen - vista.t0) * escalaX - 1,
    escalaY,
    despY: -vista.v0 * escalaY - 1,
  };
}

/**
 * Elige el nivel de pirámide más barato que todavía no pierde detalle visible.
 *
 * El criterio es «al menos un cubo por píxel»: por debajo de eso se pierden
 * picos que la pantalla sí podría mostrar, y ese es exactamente el defecto que
 * la pirámide de `min/max` existe para no tener. Por encima se paga ancho de
 * banda y memoria de GPU sin que se vea nada nuevo.
 *
 * Se recorre de más grueso a más fino y se devuelve el PRIMERO que cumple, así
 * que el resultado es el nivel con menos cubos de entre los suficientes. Si
 * ninguno llega (vista muy ampliada), gana el más fino, que es lo correcto: no
 * hay más detalle que dar.
 *
 * `fraccionVisible` sale del reloj del log, no del renderizador — otra vez
 * ADR-006: aquí no se sabe qué es un log, solo cuánta parte de él se ve.
 */
export function elegirNivel(
  niveles: readonly ResumenNivel[],
  fraccionVisible: number,
  anchoPx: number,
): number {
  if (niveles.length === 0) {
    throw new Error("elegirNivel: no hay niveles de pirámide entre los que elegir");
  }
  const fraccion = Math.min(Math.max(fraccionVisible, 0), 1);
  // Índice del más fino: el de mayor número de cubos. No se asume que la lista
  // venga ordenada, porque el orden es una convención de quien la construye y
  // una lista al revés daría el nivel opuesto sin que nada lo dijera.
  let masFino = 0;
  for (let i = 1; i < niveles.length; i += 1) {
    if (niveles[i]!.nCubos > niveles[masFino]!.nCubos) masFino = i;
  }
  if (fraccion === 0) return masFino;

  let elegido = masFino;
  let cubosDelElegido = Number.POSITIVE_INFINITY;
  for (let i = 0; i < niveles.length; i += 1) {
    const visibles = niveles[i]!.nCubos * fraccion;
    if (visibles >= anchoPx && niveles[i]!.nCubos < cubosDelElegido) {
      elegido = i;
      cubosDelElegido = niveles[i]!.nCubos;
    }
  }
  return elegido;
}

/** Cuántos vértices genera `expandirCubos` por cada cubo. */
export const VERTICES_POR_CUBO = 4;

/**
 * Convierte los cuatro arrays del cubo en un búfer entrelazado `(x, y)` listo
 * para `gl.LINE_STRIP`.
 *
 * Cuatro vértices por cubo —`primero`, los dos extremos, `ultimo`— y no dos:
 * con solo `min`/`max` cada cubo sería una barra vertical suelta y el trazo se
 * vería como una valla, no como una señal. `primero` y `ultimo` son los que
 * cosen cada cubo con el siguiente, y son la razón de que
 * `dlv_core.piramide._siguiente_nivel_continuo` se moleste en propagarlos.
 *
 * El orden de los dos extremos depende de la pendiente del cubo (`ultimo` vs.
 * `primero`). Con un orden fijo `min, max`, un tramo descendente dibujaría
 * bajar-subir-bajar dentro de cada cubo: un zigzag que no está en los datos y
 * que a cierto zoom parece ruido de señal. Con el orden por pendiente, el trazo
 * recorre el cubo en su sentido real y sigue tocando ambos extremos, así que no
 * se pierde ningún pico.
 *
 * El bucle es por CUBO (miles), no por muestra (millones), y se ejecuta una vez
 * por subida de nivel, no por fotograma. Es la misma disciplina que ADR-009
 * impone en `dlv-core`, aplicada donde aquí importa.
 */
export function expandirCubos(cubos: CubosContinuos): Float32Array {
  const n = cubos.t.length;
  const salida = new Float32Array(n * VERTICES_POR_CUBO * 2);
  for (let i = 0; i < n; i += 1) {
    const x = cubos.t[i]!;
    const primero = cubos.primero[i]!;
    const ultimo = cubos.ultimo[i]!;
    const minimo = cubos.minimo[i]!;
    const maximo = cubos.maximo[i]!;
    const sube = ultimo >= primero;
    const j = i * VERTICES_POR_CUBO * 2;
    salida[j] = x;
    salida[j + 1] = primero;
    salida[j + 2] = x;
    salida[j + 3] = sube ? minimo : maximo;
    salida[j + 4] = x;
    salida[j + 5] = sube ? maximo : minimo;
    salida[j + 6] = x;
    salida[j + 7] = ultimo;
  }
  return salida;
}

/**
 * Comprueba que los cinco arrays de un cubo miden lo mismo.
 *
 * Un `minimo` más corto que `t` no revienta: produce `undefined` que en un
 * `Float32Array` se guarda como `NaN`, y un `NaN` en WebGL no da error, solo
 * un hueco en el trazo. Fallar aquí, con el nombre del array descuadrado,
 * cuesta una comparación y ahorra la peor clase de depuración que tiene este
 * módulo (mirar un lienzo y adivinar).
 */
export function validarCubos(cubos: CubosContinuos): void {
  const n = cubos.t.length;
  const arrays: readonly [string, Float32Array][] = [
    ["minimo", cubos.minimo],
    ["maximo", cubos.maximo],
    ["primero", cubos.primero],
    ["ultimo", cubos.ultimo],
  ];
  for (const [nombre, array] of arrays) {
    if (array.length !== n) {
      throw new Error(
        `cubos incoherentes: \`t\` tiene ${n} entradas y \`${nombre}\` tiene ${array.length}`,
      );
    }
  }
}
