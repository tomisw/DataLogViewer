/**
 * Comparadores de la regresión visual obligatoria del renderizador (F5-12,
 * ADR-006). Este fichero es donde vive la decisión de diseño que es el 80 %
 * del valor de la tarea: QUÉ se compara y con QUÉ tolerancia, no cómo se
 * hace una captura.
 *
 * POR QUÉ NO SE COMPARAN IMÁGENES PÍXEL A PÍXEL
 * ===============================================
 * La opción obvia —renderizar, guardar un PNG de referencia y comparar byte a
 * byte (o con un `pixelmatch`) contra el siguiente render— es la que este
 * módulo evita a propósito. No por pereza: porque es una prueba que MIENTE.
 *
 * Un `LINE_STRIP` sin `antialias` (el propio `renderizador.ts` lo desactiva,
 * ver su cabecera) sigue sin tener una rasterización única: el estándar de
 * OpenGL deja la «diamond-exit rule» de los segmentos casi horizontales o
 * verticales como zona gris entre implementaciones, y qué píxel exacto gana
 * un empate de cobertura varía de una GPU/controlador a otro sin que nada
 * esté roto. Súmese el redondeo de punto flotante del shader (distinto orden
 * de operaciones en cada compilador de GLSL) y, en portátiles con gestión de
 * color del sistema operativo, una conversión de espacio de color en el
 * compositor que no toca ni un uniforme de este código. El resultado: dos
 * capturas del MISMO fotograma en dos máquinas difieren en un puñado de
 * píxeles de borde SIEMPRE, incluso cuando el renderizador es correcto.
 *
 * Una prueba de píxeles exactos frente a eso tiene un único destino posible:
 * se pone roja en la primera GPU distinta, alguien sube la tolerancia de
 * «0 píxeles distintos» a «un few %» para que pase, alguien más la sube otra
 * vez seis meses después, y al final la prueba compara «¿sigue habiendo una
 * imagen?» en vez de «¿la serie está donde tiene que estar?». Es la prueba
 * que ADR-006 pide y que en la práctica todo el mundo desactiva: exactamente
 * lo que este módulo tiene que no ser.
 *
 * LA ALTERNATIVA: INVARIANTES GEOMÉTRICOS, NO DIFERENCIA DE IMAGEN
 * ===================================================================
 * En vez de «¿es esta imagen igual a esa otra?», cada prueba de F5-12
 * pregunta una cosa concreta y con oráculo independiente:
 *
 *   1. **Posición** (`hayColorCerca`): un punto de datos con coordenadas
 *      conocidas, ¿aparece cerca del píxel que le corresponde por la
 *      geometría de la vista? Esto es justo lo que cambia con un eje
 *      desplazado, una `Vista` mal pasada o un signo invertido en el shader
 *      —el defecto real que ADR-006 quiere cazar—, y es indiferente a qué
 *      píxel exacto ganó el empate de rasterización en el borde del trazo.
 *   2. **Color** (`coloresAproximados`): el color que aparece en ese punto,
 *      ¿es (con tolerancia) el color de token de tema esperado? Esto es lo
 *      que cazaría una regresión de contraste entre temas —un canal
 *      intercambiado, una serie con el color de la anterior—, y absorbe el
 *      redondeo de 8 bits y la gestión de color del sistema sin absorber un
 *      canal mal calculado (la diferencia entre colores de tema reales de
 *      este proyecto es de decenas de unidades, no de un puñado).
 *   3. **Cobertura** (`contarPixelesNoFondo`): cuántos píxeles no son fondo,
 *      en un rango ancho. Es la red más basta de las tres —no distingue un
 *      trazo bien dibujado de otro con el grosor equivocado— y existe solo
 *      para cazar el fallo más tonto y más caro de no coger: «no se dibuja
 *      nada» o «se ha pintado la pantalla entera».
 *
 * Ninguna de las tres necesita una imagen de referencia guardada en el
 * repositorio (que además ADR-009/§9.11 desaconsejarían como el tipo de
 * artefacto binario que nadie revisa en un `diff`). El oráculo es la
 * GEOMETRÍA de la escena de prueba (`escenas.ts`), calculada a mano y
 * verificada por álgebra en sus comentarios, no una captura de una ejecución
 * anterior que podría llevar el propio defecto arrastrado.
 *
 * DÓNDE VIVEN LAS TOLERANCIAS, Y POR QUÉ NO EN `data/umbrales.toml`
 * =====================================================================
 * Este proyecto trata un umbral cableado como "una opinión disfrazada de
 * física" (`data/umbrales.toml`) porque ahí el umbral describe el mundo
 * físico de un motor: un límite de temperatura no es una preferencia de
 * quien programa. Las constantes de aquí abajo son de otra naturaleza: no
 * describen el motor, describen cuánto ruido de rasterización y de color
 * introduce una GPU antes de que dejemos de creer lo que vemos. Por eso NO
 * viven en `data/umbrales.toml` —ese fichero es de dominio, con la
 * precedencia canal > perfil > usuario > fichero de ADR sobre unidades, y
 * meter aquí una tolerancia de prueba de rasterización sería la misma
 * confusión de capas que el proyecto evita en el sentido contrario— pero
 * TAMPOCO se cablean dentro de cada función: son constantes con nombre,
 * exportadas, con la razón de su valor escrita al lado, y cada comparador
 * las acepta como parámetro con esa constante de valor por omisión. Quien
 * ejecute la suite en una GPU más ruidosa (una máquina virtual con
 * renderizado por software, por ejemplo) sube el número en la llamada, no
 * reescribe la función.
 *
 * LO QUE SE HA MEDIDO DE ESAS TOLERANCIAS (2026-08-19)
 * =====================================================
 * Las dos constantes se escribieron razonadas pero sin ejecutar nada. Primera
 * medida real, en Edge 151 sin cabeza sobre Windows 11:
 *
 *   - Con la GPU real de la máquina (ANGLE/D3D11, Intel UHD Graphics 620) las
 *     cuatro comprobaciones pasan con estos valores por omisión, sin tocarlos.
 *   - Con el rasterizador por SOFTWARE (SwiftShader), el resultado es el
 *     MISMO, también sin tocar los valores.
 *
 * Ese segundo punto es el que importaba y es el que justifica a posteriori
 * todo lo razonado arriba: si esta suite comparase imágenes, el umbral
 * calibrado contra software casi seguro no valdría para la GPU —es la
 * advertencia habitual de la regresión visual por captura— y habría hecho
 * falta un umbral por backend. Comparando INVARIANTES GEOMÉTRICOS no hizo
 * falta: los dos backends dan el mismo veredicto con la misma tolerancia,
 * porque lo que se compara (¿está el punto donde toca? ¿de qué color?) es
 * justo lo que no cambia entre rasterizadores.
 *
 * Sigue sin estar medido, y no se puede medir en esta máquina: cómo se
 * comportan estas tolerancias en una GPU de otro fabricante (AMD, NVIDIA) o
 * con otro backend de ANGLE (OpenGL, Metal, Vulkan de escritorio). Lo
 * esperable, por lo anterior, es que no cambie nada; esperable no es medido.
 */

/** Un color RGB de 8 bits por canal, como lo devuelve `gl.readPixels`. */
export interface ColorRGB {
  readonly r: number;
  readonly g: number;
  readonly b: number;
}

/**
 * Un fotograma ya leído de la GPU.
 *
 * `datos` sigue el convenio de `gl.readPixels`: RGBA intercalado, y las
 * FILAS van de ABAJO hacia ARRIBA (el origen de OpenGL está en la esquina
 * inferior izquierda). No se invierte aquí a propósito: invertir en un sitio
 * y no en el oráculo de `escenas.ts` es exactamente la clase de error de
 * "uno de los dos tiene el eje Y al revés" que esta suite existe para no
 * tener ella misma. Todo lo que consume `BufferDePixeles` usa el mismo
 * convenio, documentado en el campo `filaDesdeAbajo` de `escenas.ts`.
 */
export interface BufferDePixeles {
  readonly datos: Uint8Array;
  readonly ancho: number;
  readonly alto: number;
}

/**
 * Tolerancia por canal de color (0..255).
 *
 * 10 sobre 255 (≈ 4 %) cubre el redondeo de cuantización a 8 bits del
 * `framebuffer` y una conversión de espacio de color moderada del sistema
 * operativo o el compositor, sin llegar a confundir dos colores de tema
 * reales de este proyecto: en `tema/tema.ts` el acento oscuro (`#4da3ff`) y
 * el claro (`#0066cc`) difieren en más de 60 unidades en el canal rojo, y
 * `parametrosDeSerie` separa las dos luces de alto contraste (0,70 y 0,45)
 * en una distancia HSL que en RGB nunca baja de varias decenas de unidades.
 * Un fallo real de color no cabe en 10 unidades; ruido de GPU, casi siempre
 * sí.
 */
export const TOLERANCIA_CANAL_COLOR = 10;

/**
 * Radio (en píxeles) de la ventana de búsqueda alrededor de un píxel
 * calculado analíticamente.
 *
 * 3 píxeles (una caja de 7×7) absorbe el desacuerdo entre implementaciones
 * sobre qué píxel gana la "diamond-exit rule" en un segmento casi horizontal
 * o vertical, más un redondeo de escala de dispositivo. No absorbe un eje
 * desplazado de verdad: las escenas de `escenas.ts` separan sus puntos de
 * control por decenas de píxeles a propósito, así que un fallo real —un
 * rango de vista invertido, un `viewport` equivocado— mueve el punto muchas
 * veces este radio y sigue fallando.
 *
 * MEDIDO: con un desplazamiento inyectado de 10 px en el eje X, la
 * comprobación de posición falla. Pero el margen no es holgado para una serie
 * poco inclinada —un desplazamiento en X mueve la serie `d·m/√(1+m²)` px
 * respecto al punto esperado, con `m` su pendiente en píxeles—, y con esos
 * 10 px la serie "paralela" (m = 0,375) quedaba a 3,5 px, al borde de esta
 * caja. El detalle y por qué el conjunto sí lo caza están en la cabecera de
 * `suite-navegador.ts`. Subir este radio "por si acaso" es exactamente lo que
 * volvería ciega la comprobación de posición.
 */
export const RADIO_BUSQUEDA_PX = 3;

/**
 * Lee el color en `(columna, filaDesdeAbajo)`, o `null` si cae fuera del
 * búfer.
 *
 * `null` y no lanzar: quien llama (`hayColorCerca`) recorre una ventana
 * cuadrada alrededor de un punto que puede estar cerca del borde del lienzo
 * (una escena con un punto de control a pocos píxeles del borde es legítima
 * y no debería tirar la prueba entera por un `RangeError`).
 */
export function colorEnPixel(
  buffer: BufferDePixeles,
  columna: number,
  filaDesdeAbajo: number,
): ColorRGB | null {
  if (
    columna < 0 ||
    columna >= buffer.ancho ||
    filaDesdeAbajo < 0 ||
    filaDesdeAbajo >= buffer.alto
  ) {
    return null;
  }
  const indice = (filaDesdeAbajo * buffer.ancho + columna) * 4;
  const r = buffer.datos[indice];
  const g = buffer.datos[indice + 1];
  const b = buffer.datos[indice + 2];
  if (r === undefined || g === undefined || b === undefined) return null;
  return { r, g, b };
}

/** ¿Están `a` y `b` a menos de `tolerancia` en cada canal? */
export function coloresAproximados(
  a: ColorRGB,
  b: ColorRGB,
  tolerancia: number = TOLERANCIA_CANAL_COLOR,
): boolean {
  return (
    Math.abs(a.r - b.r) <= tolerancia &&
    Math.abs(a.g - b.g) <= tolerancia &&
    Math.abs(a.b - b.b) <= tolerancia
  );
}

/**
 * ¿Aparece `esperado` en algún píxel de la caja de `radio` alrededor de
 * `(columna, filaDesdeAbajo)`?
 *
 * Este es el invariante de POSICIÓN (ver la cabecera del fichero): no exige
 * que el píxel exacto calculado lleve el color —eso es justo lo que varía
 * con la rasterización sin AA entre GPUs—, exige que el color esperado esté
 * en algún sitio de la vecindad. Si no está en ningún píxel de una caja de
 * 7×7, no es ruido de borde: la serie no se dibujó donde debía, o no se
 * dibujó en absoluto.
 */
export function hayColorCerca(
  buffer: BufferDePixeles,
  columna: number,
  filaDesdeAbajo: number,
  esperado: ColorRGB,
  radio: number = RADIO_BUSQUEDA_PX,
  tolerancia: number = TOLERANCIA_CANAL_COLOR,
): boolean {
  for (let df = -radio; df <= radio; df += 1) {
    for (let dc = -radio; dc <= radio; dc += 1) {
      const color = colorEnPixel(buffer, columna + dc, filaDesdeAbajo + df);
      if (color !== null && coloresAproximados(color, esperado, tolerancia)) return true;
    }
  }
  return false;
}

/**
 * Cuenta los píxeles del búfer que NO coinciden con `fondo` (con tolerancia).
 *
 * Es el invariante de COBERTURA, el más basto de los tres: sirve para la red
 * de seguridad grosera («¿se dibujó algo? ¿se dibujó demasiado?»), no para
 * distinguir un trazo correcto de uno con el grosor cambiado. Quien llame
 * debe comparar el resultado contra un RANGO ancho, nunca un número exacto —
 * el recuento de píxeles de una línea sin AA varía con la implementación de
 * la "diamond-exit rule" más de lo que varía su posición.
 */
export function contarPixelesNoFondo(
  buffer: BufferDePixeles,
  fondo: ColorRGB,
  tolerancia: number = TOLERANCIA_CANAL_COLOR,
): number {
  let cuenta = 0;
  const total = buffer.ancho * buffer.alto;
  for (let i = 0; i < total; i += 1) {
    const indice = i * 4;
    const r = buffer.datos[indice];
    const g = buffer.datos[indice + 1];
    const b = buffer.datos[indice + 2];
    if (r === undefined || g === undefined || b === undefined) continue;
    if (!coloresAproximados({ r, g, b }, fondo, tolerancia)) cuenta += 1;
  }
  return cuenta;
}
