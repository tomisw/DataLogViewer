/**
 * Escenas sintéticas y su oráculo de posición para F5-12 (ADR-006).
 *
 * DETERMINISMO
 * ============
 * Nada aquí lee el reloj ni usa `Math.random`. Todos los puntos de control
 * son constantes escritas a mano, y las dos series ("recta" y "paralela")
 * están construidas para no cruzarse nunca dentro de la vista de prueba (ver
 * `PUNTOS_RECTA`/`PUNTOS_PARALELA` más abajo): una escena de prueba con datos
 * que cambian de una ejecución a otra —o cuyo resultado depende de en qué
 * orden termine una carrera— es una suite que unas veces avisa y otras no, y
 * eso, para una comprobación que ya es cara de ejecutar (necesita
 * navegador), es inútil.
 *
 * POR QUÉ `pixelEsperado` NO IMPORTA `render/escala.ts`
 * ========================================================
 * Sería más corto llamar a `transformacion()` de `escala.ts` para calcular el
 * píxel esperado: es la misma cuenta. Deliberadamente no se hace. Si
 * `transformacion()` tuviera un error — un signo cambiado, un eje que no se
 * invierte donde debería — y esta función lo importara, la prueba calcularía
 * el píxel EQUIVOCADO con la misma fórmula equivocada que usa el shader (ver
 * `programa.ts`: la GPU hace literalmente `a_punto·escala + desp` con esos
 * cuatro números) y el fallo desaparecería de los dos lados a la vez. La
 * prueba pasaría con el eje mal.
 *
 * `pixelEsperado` reimplementa las cuatro líneas a partir de la definición de
 * coordenadas de recorte de OpenGL (`x_ndc, y_ndc ∈ [-1, 1]`), no del código
 * de este proyecto. Es barato — son cuatro líneas — y es lo que hace que
 * F5-12 examine la tubería completa (CPU → uniforme → shader → rasterizador)
 * en vez de repetir lo que ya prueba, sin GPU, `escala.test.ts`.
 */

import { establecerTema, parametrosDeSerie, type NombreTema } from "../../tema/tema.ts";
import type { Color, CubosContinuos, Vista, Viewport } from "../tipos.ts";

/** El rectángulo de vista fijo de toda la suite: 20 s de eje X, 0..200 de eje Y. */
export const VISTA_PRUEBA: Vista = { t0: 0, t1: 20, v0: 0, v1: 200 };

/**
 * 400×300: bastante grande para que un fallo real (un eje desplazado, un
 * `viewport` mal pasado) mueva un punto muchas veces `RADIO_BUSQUEDA_PX` —si
 * el lienzo fuera de 8×8, hasta un eje invertido podría caer "cerca" por
 * pura casualidad de escala—, y bastante pequeño para que `contarPixelesNoFondo`
 * (que recorre todo el búfer) sea instantáneo.
 */
export const VIEWPORT_PRUEBA: Viewport = { ancho: 400, alto: 300 };

/** Color de fondo real del lienzo: `renderizador.ts::dibujar` limpia a negro. */
export const FONDO_LIENZO = { r: 0, g: 0, b: 0 };

export interface PuntoDeControl {
  readonly nombre: string;
  readonly tAbs: number;
  readonly valor: number;
}

/**
 * Serie "recta": diagonal creciente `valor = 10·t`, de t=2 a t=18.
 *
 * El punto "centro" (t=10, valor=100) es el CENTRO EXACTO de `VISTA_PRUEBA`
 * — (t0+t1)/2 = 10, (v0+v1)/2 = 100 — así que su píxel esperado es
 * `(ancho/2, alto/2)` por definición de coordenadas de recorte, sin depender
 * de ninguna fórmula de este proyecto: es el único punto de control que se
 * puede verificar a mano sin ni siquiera `pixelEsperado`.
 *
 * El margen t∈[2,18] (10 %–90 % de la vista) y valor∈[20,180] deja al menos
 * un 10 % de la vista —40 px en X, 30 px en Y— entre cualquier punto de
 * control y el borde del lienzo, que es el hueco que usa
 * `puntoDeFondoSeguro` para las comprobaciones de fondo.
 */
export const PUNTOS_RECTA: readonly PuntoDeControl[] = [
  { nombre: "inicio", tAbs: 2, valor: 20 },
  { nombre: "cuarto", tAbs: 5, valor: 50 },
  { nombre: "centro", tAbs: 10, valor: 100 },
  { nombre: "tresCuartos", tAbs: 15, valor: 150 },
  { nombre: "final", tAbs: 18, valor: 180 },
];

/**
 * Serie "paralela": diagonal más plana, `valor = 5·t`, mismo dominio de t.
 * Comparada con "recta" (`valor = 10·t`), la diferencia `5·t` es positiva en
 * todo (0, 18], así que las dos series NUNCA se cruzan dentro de la vista —
 * "recta" queda siempre por encima. Importa: dos series que se cruzasen
 * exactamente en un punto de control harían que "¿qué color se encuentra
 * ahí?" fuera ambiguo por construcción, y esta suite necesita que cada
 * comprobación tenga una única respuesta correcta.
 *
 * No se le exige el mismo margen del 10% respecto a v0/v1 que a "recta": las
 * dos esquinas que usan `puntoDeFondoSeguro`/`puntoDeFondoSeguroOpuesto` están
 * en (t≈t0, v≈v0) y (t≈t1, v≈v1) — la diagonal opuesta —, así que basta con
 * que NINGUNA serie tenga puntos de control cerca de t0 o t1 (el margen en X)
 * para que ambas esquinas queden libres, sea cual sea el valor de Y en ese
 * instante. "paralela" cumple ese margen en X porque comparte el dominio de t
 * con "recta".
 */
export const PUNTOS_PARALELA: readonly PuntoDeControl[] = PUNTOS_RECTA.map((p) => ({
  nombre: p.nombre,
  tAbs: p.tAbs,
  valor: 5 * p.tAbs,
}));

/**
 * Cubos degenerados: cada punto de control es su propio cubo, con
 * `primero = ultimo = minimo = maximo`. `expandirCubos` (`escala.ts`) genera
 * 4 vértices por cubo que, al ser los cuatro iguales, colapsan al mismo
 * punto — así que el `LINE_STRIP` resultante conecta exactamente los puntos
 * de control, sin picos intermedios que compliquen calcular el píxel
 * esperado. Es el mismo aspecto que tendría el nivel más fino de la
 * pirámide (factor 1, un cubo por muestra) para una señal ya muestreada a
 * ese ritmo.
 */
export function cubosDeControl(puntos: readonly PuntoDeControl[], tOrigen: number): CubosContinuos {
  const n = puntos.length;
  const t = new Float32Array(n);
  const valor = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    const punto = puntos[i]!;
    t[i] = punto.tAbs - tOrigen;
    valor[i] = punto.valor;
  }
  return { t, tOrigen, minimo: valor, maximo: valor, primero: valor, ultimo: valor, factor: 1 };
}

export interface PixelEsperado {
  readonly columna: number;
  /**
   * Fila contada desde ABAJO, igual que `gl.readPixels` (origen de OpenGL en
   * la esquina inferior izquierda). Se nombra así y no `filaY` a secas para
   * que quien lo consuma no tenga que recordar el convenio ni invertirlo por
   * su cuenta — la fuente más común de un "eje Y al revés" en este tipo de
   * prueba es justo esa conversión hecha (o no) en el sitio equivocado.
   */
  readonly filaDesdeAbajo: number;
}

/**
 * El oráculo de posición. Ver la cabecera del fichero para por qué NO importa
 * `transformacion()` de `escala.ts` y reimplementa la cuenta.
 */
export function pixelEsperado(
  tAbs: number,
  valor: number,
  vista: Vista,
  viewport: Viewport,
): PixelEsperado {
  const anchoT = vista.t1 - vista.t0;
  const altoV = vista.v1 - vista.v0;
  const xNdc = ((tAbs - vista.t0) / anchoT) * 2 - 1;
  const yNdc = ((valor - vista.v0) / altoV) * 2 - 1;
  return {
    columna: Math.round(((xNdc + 1) / 2) * viewport.ancho),
    filaDesdeAbajo: Math.round(((yNdc + 1) / 2) * viewport.alto),
  };
}

/**
 * Estimación del número de píxeles que ocupa un `LINE_STRIP` que pasa por
 * `puntos`, sumando la distancia de Chebyshev (`max(|dx|, |dy|)`) entre cada
 * par de vértices consecutivos — que es, salvo un píxel de redondeo por
 * segmento, lo que dibuja un algoritmo de Bresenham entre dos puntos.
 *
 * Es una ESTIMACIÓN, no una cuenta exacta, y así se usa siempre: como centro
 * de una banda ancha para el invariante de COBERTURA
 * (`contarPixelesNoFondo`), nunca como número exacto a igualar — ver la
 * cabecera de `invariantes.ts` sobre por qué el recuento de píxeles de una
 * línea sin AA varía entre implementaciones.
 */
export function longitudPixelesDeSerie(
  puntos: readonly PuntoDeControl[],
  vista: Vista,
  viewport: Viewport,
): number {
  let total = 0;
  for (let i = 1; i < puntos.length; i += 1) {
    const anterior = puntos[i - 1]!;
    const actual = puntos[i]!;
    const a = pixelEsperado(anterior.tAbs, anterior.valor, vista, viewport);
    const b = pixelEsperado(actual.tAbs, actual.valor, vista, viewport);
    total += Math.max(Math.abs(b.columna - a.columna), Math.abs(b.filaDesdeAbajo - a.filaDesdeAbajo));
  }
  return total;
}

/**
 * Una coordenada en la esquina inferior izquierda del lienzo, lejos de
 * cualquier punto de control de `PUNTOS_RECTA`/`PUNTOS_PARALELA` (ver el
 * margen de 10 % documentado ahí). Sirve para comprobar el color de fondo
 * real sin arriesgarse a pisar el trazo de una serie.
 */
export function puntoDeFondoSeguro(): { columna: number; filaDesdeAbajo: number } {
  return { columna: 2, filaDesdeAbajo: 2 };
}

/** La esquina opuesta, mismo criterio. */
export function puntoDeFondoSeguroOpuesto(viewport: Viewport): {
  columna: number;
  filaDesdeAbajo: number;
} {
  return { columna: viewport.ancho - 3, filaDesdeAbajo: viewport.alto - 3 };
}

// ---------------------------------------------------------------------------
// Color por tema, para la comprobación de "los dos temas" que pide la tarea.
// ---------------------------------------------------------------------------

/**
 * Tono fijo (grados) para el color de serie sintético de la comprobación de
 * tema. El valor concreto es arbitrario — cualquier tono sirve para separar
 * saturación/luz por tema —, 210° se eligió solo porque cae cerca del azul
 * que ya usa este proyecto para el acento (`tema.ts`), así que un vistazo
 * manual a la escena de prueba se reconoce como "un azul", no como un color
 * aleatorio sin relación con la aplicación real.
 */
const TONO_PRUEBA_GRADOS = 210;

/**
 * Convierte HSL a RGB (0..1 por canal), fórmula estándar sin dependencias.
 * Se reimplementa aquí — no se importa ninguna librería de color, por la
 * regla de no añadir dependencias — y se verifica en `escenas.test.ts` contra
 * los seis colores puros (rojo, verde, azul, y sus tres complementarios) para
 * no confiar a ciegas en la transcripción.
 */
export function hslARgb(tonoGrados: number, saturacion: number, luz: number): Color {
  const h = (((tonoGrados % 360) + 360) % 360) / 360;
  const s = saturacion;
  const l = luz;
  if (s === 0) return { r: l, g: l, b: l, a: 1 };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return {
    r: hueACanal(p, q, h + 1 / 3),
    g: hueACanal(p, q, h),
    b: hueACanal(p, q, h - 1 / 3),
    a: 1,
  };
}

function hueACanal(p: number, q: number, tCrudo: number): number {
  let t = tCrudo;
  if (t < 0) t += 1;
  if (t > 1) t -= 1;
  if (t < 1 / 6) return p + (q - p) * 6 * t;
  if (t < 1 / 2) return q;
  if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
  return p;
}

/** Redondea un `Color` (canales 0..1) a `ColorRGB` de 8 bits (canales 0..255). */
export function colorARgb255(color: Color): { r: number; g: number; b: number } {
  return {
    r: Math.round(color.r * 255),
    g: Math.round(color.g * 255),
    b: Math.round(color.b * 255),
  };
}

/**
 * El color con el que la aplicación real pintaría una serie bajo `tema`, con
 * el mismo `parametrosDeSerie` que usa `carriles/color.ts`/`app/aplicacion.ts`
 * (fuera de este carril, así que no se importan; se replica solo el tono fijo
 * de arriba con la saturación/luz reales del tema, que es lo que hace que
 * esta comprobación detecte una regresión de contraste real y no un color
 * inventado sin relación con la aplicación).
 *
 * EFECTO SECUNDARIO DELIBERADO: `establecerTema` cambia el tema activo del
 * módulo `tema.ts` (estado de módulo compartido). Es lo que hace falta para
 * leer `parametrosDeSerie` del tema pedido, y es aceptable aquí porque esta
 * función SOLO la usa una suite de pruebas que no comparte proceso con la
 * aplicación real; en Node, sin `entorno` inyectado, `establecerTema` no toca
 * ni DOM ni `localStorage` (son opcionales en `EntornoTema`), así que no dejar
 * nada que limpiar entre llamadas.
 */
export function colorDeSerieParaTema(tema: NombreTema, discriminante: number): Color {
  establecerTema(tema);
  const { saturacion, luz } = parametrosDeSerie(discriminante);
  return hslARgb(TONO_PRUEBA_GRADOS, saturacion, luz);
}
