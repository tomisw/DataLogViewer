/**
 * Vista paralela (F2-04): N segmentos superpuestos en el mismo gráfico,
 * distinguidos por color, para comparar la misma vuelta de dos tiradas.
 *
 * QUÉ HACE ESTE MÓDULO Y QUÉ NO
 * ==============================
 * `dlv_core.tiempo` (F2-01) ya resuelve la aritmética de "dónde cae cada
 * segmento" (`EjeVirtual`, `eje_paralelo`, `locales_en`) y NO se reimplementa
 * aquí — ver la cabecera de `tipos.ts`. Lo que este módulo aporta es
 * exclusivamente la parte de VISTA: convertir un `SegmentoParalelo` ya
 * resuelto (con su `offset` dado) en lo que las piezas de renderizado que YA
 * EXISTEN necesitan para dibujarlo, sin modificar ninguna de ellas:
 *
 *   - `render/renderizador.ts#subirSerie(id, cubos, color)` ya acepta
 *     cualquier número de series coloreadas sobre un `Vista` COMPARTIDO
 *     (`dibujar(vista)`). No hace falta ninguna capacidad nueva del
 *     renderizador: superponer N logs es subir N series con un color cada
 *     una y un `tOrigen` que ya incluye el desfase — `desplazarSerie` es la
 *     única aritmética nueva, y es sumar una constante a un único `number`
 *     (`tOrigen`), no tocar ninguna muestra.
 *   - `cursor/cursor.ts#CursorDeTabla.actualizarCanales` ya acepta una lista
 *     de `CanalCursor` con clave y etiqueta arbitrarias, y ya enseña "sin
 *     datos" cuando el instante pedido cae fuera de lo cacheado para esa
 *     clave (`contenidoDeCelda`, `SIN_DATOS`). Eso es EXACTAMENTE lo que
 *     hace falta para la decisión 2 del informe (la tabla enseña los N
 *     valores, no uno, y "sin datos" en el segmento donde el cursor cae en
 *     un hueco) — ver `vista-paralela.test.ts` para la prueba de integración
 *     que lo demuestra sin tocar `cursor.ts`.
 *   - `datos/cache-cubos.ts#ClaveCubos.canal` es un `string` sin formato
 *     impuesto: componer `"${idSegmento}:${canalId}"` (`idSerieParalela`) le
 *     da a cada (log, canal) su propia entrada de caché sin ampliar
 *     `CacheDeCubos`, que hoy solo conoce "canal" porque el MVP abre un log
 *     a la vez.
 *
 * DECISIÓN 1 — DE DÓNDE SALE EL COLOR DE CADA LOG
 * ====================================================
 * `carriles/color.ts#colorPorCodigo` YA implementa exactamente lo que hace
 * falta: un color estable por un discriminante entero, con matiz de ángulo
 * áureo y saturación/luz de `tema.parametrosDeSerie` (F3-21, alto
 * contraste). La cabecera de `tema.ts#parametrosDeSerie` es explícita sobre
 * el coste de escribir una tercera copia de esa fórmula: las dos que ya
 * existen (`carriles/color.ts` y la privada de `app/aplicacion.ts`) se
 * mantienen sincronizadas SOLO porque las dos leen `parametrosDeSerie` del
 * mismo sitio, y ese fichero cuenta que la primera versión duplicó también
 * los cuatro números del tema y se desincronizó en cuanto alguien tocó uno
 * de los dos. No hay ninguna razón para pagar ese riesgo una tercera vez:
 * `colorPorCodigo` es genérico en su discriminante (el comentario de
 * `color.ts` dice "código de estado", pero la implementación no sabe nada
 * de enums de estado, solo de un `number`), así que aquí se REUTILIZA
 * directamente, con el id de texto del segmento convertido a un entero
 * estable (`codigoDeSegmento`, hash determinista) en vez de con el índice de
 * aparición — para que quitar y volver a añadir un log a la comparación no
 * le cambie el color, igual que la cabecera de `color.ts` exige para los
 * códigos de estado ("sin depender del orden en que aparecieron").
 *
 * DECISIÓN 3 — UNIDADES O DIMENSIONES DISTINTAS EN EL CANAL COMPARADO
 * =========================================================================
 * Dos casos, y son distintos:
 *
 * - **Misma dimensión, unidad de origen distinta** (dos ECUs que escalan la
 *   misma señal de forma distinta, o un canal que el usuario decide ver en
 *   otra unidad): esto NO es un problema de esta vista, es exactamente lo
 *   que ya resuelve el motor de unidades en dos pasos obligatorios —
 *   `unidades/conversion.ts#convertirCubos(cubos, aCanonicaDelCanal,
 *   conversion)` aplica primero el `aCanonica` PROPIO de cada segmento
 *   (crudo → canónica) y LUEGO la `conversion` COMPARTIDA elegida para la
 *   comparación (canónica → mostrada). `prepararSerieParalela` llama a esa
 *   función tal cual, con el `aCanonica` de CADA segmento y la MISMA
 *   `conversion` para todos: es la única forma de que dos logs con distinto
 *   factor de escala terminen en el mismo eje Y sin que ninguno salga
 *   multiplicado.
 * - **Dimensión física distinta** (°C contra kPa): esto SÍ es mentir, y no
 *   hay conversión que lo arregle — no existe ningún `Conversion` que lleve
 *   de una dimensión a otra. `comprobarDimensionesCompatibles` compara
 *   `dimensionId` entre todos los segmentos ANTES de pintar nada y devuelve
 *   `"incompatible"` con un motivo que nombra los dos logs y las dos
 *   dimensiones (mismo patrón que `comparacion/comparar-mallas.ts
 *   #comprobarBordesCompatibles`: rechazar con una explicación, nunca
 *   convertir en silencio ni elegir una de las dos dimensiones al azar).
 *   Quien monta la vista debe llamar a esta comprobación antes de pedir
 *   ninguna serie; `prepararSerieParalela` opera sobre UN segmento cada vez
 *   y no puede, por sí sola, saber si el de al lado es compatible.
 */

import { colorACss, colorPorCodigo } from "../carriles/color.ts";
import type { ClaveCubos } from "../datos/cache-cubos.ts";
import type { CanalCursor } from "../cursor/cursor.ts";
import { t } from "../locale/catalogo.ts";
import type { Color, CubosContinuos } from "../render/tipos.ts";
import { convertirCubos, type Conversion } from "../unidades/conversion.ts";
import type { ResultadoDimension, SegmentoParalelo } from "./tipos.ts";

export type { ResultadoDimension, SegmentoParalelo, EntradaLeyenda } from "./tipos.ts";
export { colorACss };

/**
 * Hash determinista de texto a entero de 32 bits (variante de FNV-1a). No
 * necesita ser criptográfico ni resistir colisiones adversariales — solo
 * estable (mismo id, mismo entero, siempre) y bien repartido para que
 * `colorPorCodigo` no agrupe los ids típicos ("log-1", "log-2"…) en el mismo
 * matiz por compartir prefijo.
 */
export function codigoDeSegmento(id: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < id.length; i += 1) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h;
}

/**
 * Color estable para un segmento (decisión 1 de la cabecera): reutiliza
 * `colorPorCodigo` de `carriles/color.ts`, así que hereda su ángulo áureo y
 * el ajuste de tema/alto contraste sin duplicar ninguno de los dos.
 */
export function colorDeSegmento(idSegmento: string): Color {
  return colorPorCodigo(codigoDeSegmento(idSegmento));
}

/**
 * Clave compuesta `"idSegmento:canalId"` para la caché de cubos y para el id
 * de serie del renderizador. Un único formato para las dos cosas: si
 * discreparan, la serie que ve el renderizador y la fila que lee el cursor
 * podrían apuntar a cachés distintas del mismo segmento sin que nada lo
 * avisara.
 */
export function idSerieParalela(segmento: Pick<SegmentoParalelo, "id" | "canalId">): string {
  return `${segmento.id}:${segmento.canalId}`;
}

/**
 * Decisión 3: todos los segmentos tienen que comparar la MISMA dimensión
 * física. `null`/lista vacía no es un caso de "todo compatible": no hay
 * nada que comparar, así que se trata igual que un fallo de configuración de
 * quien llama, con un `RangeError` (mismo criterio que
 * `comparar-mallas.ts#resolverMapaComparacion` para "número de celdas
 * distinto": no es un dato del log, es un error de quien monta la escena).
 */
export function comprobarDimensionesCompatibles(
  segmentos: readonly SegmentoParalelo[],
): ResultadoDimension {
  if (segmentos.length === 0) {
    throw new RangeError(
      "comprobarDimensionesCompatibles: no hay ningún segmento que comparar",
    );
  }
  const referencia = segmentos[0]!;
  for (const s of segmentos.slice(1)) {
    if (s.dimensionId !== referencia.dimensionId) {
      return {
        tipo: "incompatible",
        motivo: t("paralela.dimensionesIncompatibles", {
          etiquetaA: referencia.etiqueta,
          dimensionA: referencia.dimensionId,
          etiquetaB: s.etiqueta,
          dimensionB: s.dimensionId,
        }),
      };
    }
  }
  return { tipo: "compatible", dimensionId: referencia.dimensionId };
}

/**
 * Aplica el desfase de un segmento a un bloque de cubos YA convertidos a la
 * unidad de presentación. Solo toca `tOrigen` (un único `number`): las
 * cuatro muestras (`minimo`/`maximo`/`primero`/`ultimo`) y el array `t`
 * (relativo a `tOrigen`, `render/tipos.ts`) no cambian, así que esto es O(1)
 * y comparte los mismos `TypedArray` con `cubos` — no hay nada que copiar
 * para desplazar una serie en el eje X.
 */
export function desplazarCubos(cubos: CubosContinuos, offset: number): CubosContinuos {
  if (offset === 0) return cubos;
  return { ...cubos, tOrigen: cubos.tOrigen + offset };
}

/** Lo que hace falta para subir una serie de la vista paralela al renderizador. */
export interface SerieParalela {
  readonly idSerie: string;
  readonly color: Color;
  readonly cubos: CubosContinuos;
}

/**
 * Construye la serie de UN segmento, lista para `Renderizador.subirSerie`.
 *
 * Los dos pasos de conversión obligatorios (regla del proyecto, ver la
 * cabecera del módulo): `aCanonica` PROPIO del segmento primero, la
 * `conversionCompartida` de la comparación después. `parametro` es el mismo
 * para todos los segmentos a propósito (p. ej. una única estequiometría
 * activa) — si cada log necesitara su propio parámetro, ya no sería "el
 * mismo canal" lo que se compara.
 *
 * NO comprueba compatibilidad de dimensión (decisión 3): eso es
 * `comprobarDimensionesCompatibles`, que necesita ver TODOS los segmentos a
 * la vez y por eso es una función aparte, llamada antes que esta.
 */
export function prepararSerieParalela(
  segmento: SegmentoParalelo,
  cubosCrudos: CubosContinuos,
  conversionCompartida: Conversion,
  parametro?: number,
): SerieParalela {
  const cubosMostrados = convertirCubos(
    cubosCrudos,
    segmento.aCanonica,
    conversionCompartida,
    parametro,
  );
  return {
    idSerie: idSerieParalela(segmento),
    color: colorDeSegmento(segmento.id),
    cubos: desplazarCubos(cubosMostrados, segmento.offset),
  };
}

/** El tramo virtual que ocupan todos los segmentos ya desplazados. Espejo trivial de `EjeVirtual.x_min`/`x_max`. */
export function rangoVirtual(segmentos: readonly SegmentoParalelo[]): { t0: number; t1: number } {
  if (segmentos.length === 0) {
    throw new RangeError("rangoVirtual: no hay ningún segmento que ocupe ningún tramo");
  }
  let t0 = Infinity;
  let t1 = -Infinity;
  for (const s of segmentos) {
    t0 = Math.min(t0, s.offset + s.tInicio);
    t1 = Math.max(t1, s.offset + s.tFin);
  }
  return { t0, t1 };
}

/**
 * La fila del cursor para UN segmento, a un factor de pirámide dado.
 *
 * Decisión 2 del informe: `locales_en(x)` de `dlv_core.tiempo` devuelve una
 * TUPLA (N en paralelo) a propósito, para no obligar a la vista a elegir un
 * segmento arbitrario. Esta vista lo resuelve enseñando una FILA POR
 * SEGMENTO en la tabla existente del cursor en vez de un valor único —
 * `CursorDeTabla.actualizarCanales` ya soporta N filas y ya enseña "sin
 * datos" en la fila cuya clave no cubre el instante pedido
 * (`contenidoDeCelda`), así que un segmento fuera de rango para la `x`
 * actual sale como "sin datos" SIN que este módulo tenga que decidir nada:
 * es la caché, no la vista, quien sabe qué cubre y qué no.
 */
export function canalCursorDeSegmento(
  segmento: Pick<SegmentoParalelo, "id" | "canalId" | "etiqueta">,
  factor: number,
): CanalCursor {
  const clave: ClaveCubos = { canal: idSerieParalela(segmento), factor };
  return { clave, etiqueta: segmento.etiqueta };
}

/** Las N filas del cursor para todos los segmentos de la vista paralela. */
export function canalesCursorParalelos(
  segmentos: readonly Pick<SegmentoParalelo, "id" | "canalId" | "etiqueta">[],
  factor: number,
): readonly CanalCursor[] {
  return segmentos.map((s) => canalCursorDeSegmento(s, factor));
}
