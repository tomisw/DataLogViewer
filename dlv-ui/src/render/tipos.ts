/**
 * El contrato de datos del renderizador (F1-23, ADR-006).
 *
 * ADR-006 lo dice en una línea y es la restricción de diseño más importante de
 * este módulo:
 *
 *     «el renderizador recibe cubos y una escala, y no sabe nada de logs,
 *     unidades ni perfiles»
 *
 * Por eso aquí no aparecen `Canal`, `Log`, `Unidad` ni `Perfil`. Lo que entra
 * son arrays de números y un rectángulo. Esa frontera es lo que hace revisable
 * la única parte del código que el propietario no puede revisar con comodidad
 * (ADR-006 otra vez): si el renderizador supiera de unidades, un fallo de
 * conversión podría esconderse dentro de un shader.
 */

/**
 * Un nivel de la pirámide `CONTINUO` ya en el frontend (`NivelPiramide` de
 * `dlv_core.piramide`, transportado por Arrow IPC según ADR-007).
 *
 * Los cuatro arrays tienen la misma longitud: una entrada por cubo. `primero`
 * y `ultimo` no son adorno — son lo que permite dibujar el cubo como un trazo
 * continuo con el cubo vecino en vez de como una barra vertical suelta, y por
 * eso `dlv_core.piramide` se molesta en propagarlos nivel a nivel.
 */
export interface CubosContinuos {
  /**
   * Instante del cubo, en segundos **relativos a `tOrigen`**.
   *
   * Relativos y no absolutos por precisión: `Float32Array` da unos 7 dígitos
   * significativos, así que un log de 30 min (1800 s) guardado en absoluto
   * resuelve ~0,1 ms, pero uno de 8 h ya resuelve ~0,5 ms y la cosa empeora
   * sola. Restando el origen, el rango que ve el `float32` es la duración del
   * búfer y no la del reloj, que es el truco estándar de "coordenadas
   * relativas al ojo". El origen absoluto viaja aparte, en `number` (doble).
   */
  readonly t: Float32Array;
  /** Segundos absolutos a los que corresponde `t[0] === 0`. Doble, no float32. */
  readonly tOrigen: number;
  readonly minimo: Float32Array;
  readonly maximo: Float32Array;
  readonly primero: Float32Array;
  readonly ultimo: Float32Array;
  /**
   * Factor de decimación del nivel (1 = sin decimar). No lo usa el dibujo:
   * lo usa `elegirNivel` y sirve para que un cubo subido a la GPU sepa decir
   * de qué nivel vino, que es lo primero que se pregunta cuando un pico
   * desaparece a cierto zoom.
   */
  readonly factor: number;
}

/** Rectángulo de datos visible. En unidades de datos, no de píxeles. */
export interface Vista {
  /** Instante izquierdo del eje X, en segundos absolutos. */
  readonly t0: number;
  /** Instante derecho del eje X, en segundos absolutos. */
  readonly t1: number;
  /** Valor inferior del eje Y, en la unidad que ya haya elegido quien llama. */
  readonly v0: number;
  /** Valor superior del eje Y. */
  readonly v1: number;
}

/** Color de trazo, componentes en `[0, 1]`. */
export interface Color {
  readonly r: number;
  readonly g: number;
  readonly b: number;
  readonly a: number;
}

/** Tamaño del lienzo en píxeles de dispositivo (ya multiplicado por el DPR). */
export interface Viewport {
  readonly ancho: number;
  readonly alto: number;
}
