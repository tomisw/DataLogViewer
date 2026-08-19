/**
 * Geometría de los topes: a qué píxel cae cada límite, en la unidad activa
 * (F3-11).
 *
 * Separado de `topes.ts` por la misma razón que `ejes/geometria.ts` está
 * separado de `ejes/ejes.ts`: esto es una función pura, comprobable en Node
 * sin abrir un navegador, y `topes.ts` es la fontanería SVG que copia estos
 * números a atributos `x1`/`y1`/`points`… Si alguna vez una línea de tope no
 * coincidiera con lo que dice su etiqueta, el fallo solo puede estar en
 * `topes.ts` — aquí sale todo del mismo cálculo.
 *
 * DOS REGLAS DISTINTAS PARA "FUERA DE RANGO", Y POR QUÉ NO SON LA MISMA
 * =========================================================================
 * Cuando la autoescala del panel deja un tope fuera de `[vista.v0, vista.v1]`
 * hay dos casos, y este módulo los trata distinto a propósito:
 *
 * 1. **Línea plana** (un número: D6, D8, D9, D11…): es UNA alerta, un único
 *    valor. Dibujarla fuera de la pantalla —o mejor, no dibujarla— sería
 *    exactamente el fallo que este componente existe para evitar: el aviso de
 *    «crítico a 110 °C» se vuelve invisible justo cuando el usuario ha hecho
 *    zoom para mirar el detalle de una zona que ya lo ha superado. Por eso se
 *    ANCLA AL BORDE con una marca (`PosicionLinea` con `"fuera-arriba"` o
 *    `"fuera-abajo"`): `topes.ts` la pinta como un indicador compacto en el
 *    borde correspondiente, con la etiqueta del valor, en vez de una línea
 *    invisible en algún punto fuera del SVG.
 * 2. **Banda o curva** (dos bordes, o un valor que varía con el tiempo: la
 *    banda de λ, D10): no es una alerta puntual, es una REGIÓN. Igual que la
 *    rejilla de `ejes.ts` no dibuja una marca por cada línea que "se sale"
 *    del área — simplemente no se ve más allá del borde—, un borde de banda o
 *    un tramo de curva que se sale de la vista se RECORTA a
 *    `[0, area.alto]`, no se marca. La lectura correcta al ver el borde
 *    recortado pegado al techo del panel es "estás por debajo de la banda
 *    entera", que ya es la información completa: no hace falta una marca
 *    adicional para un borde que, a diferencia de un tope plano, ya es
 *    visible como forma.
 *
 * Esta asimetría es la decisión con más consecuencia del módulo, así que va
 * aquí y no en un comentario suelto — el mismo criterio que usa
 * `dlv_core.topes` para justificar el recorte de una curva por puntos en vez
 * de extrapolarla.
 */

import { xAPixel, yAPixel } from "../ejes/coordenadas.ts";
import { formatearNumero } from "../ejes/formato.ts";
import { convertirValor, type Clase } from "../unidades/conversion.ts";
import type {
  BandaResuelta,
  BandaTope,
  ConfiguracionTopes,
  FormaResuelta,
  GeometriaTopes,
  LimiteResuelto,
  LineaResuelta,
  LineaTope,
  PosicionLinea,
  PuntoPixel,
} from "./tipos.ts";

/** `dlv_core.topes`: un tope siempre es `Clase.PUNTO` (ver la cabecera de `tipos.ts`). */
const CLASE_DE_TOPE: Clase = "punto";

const DECIMALES_POR_OMISION = 2;

function recortar(valor: number, minimo: number, maximo: number): number {
  return Math.min(Math.max(valor, minimo), maximo);
}

/** El valor canónico de un tope, ya en la unidad mostrada del canal. */
function aMostrado(config: ConfiguracionTopes, valorCanonico: number): number {
  return convertirValor(valorCanonico, config.conversion, CLASE_DE_TOPE, config.parametro);
}

function etiquetaConValor(base: string | undefined, valorMostrado: number, decimales: number): string {
  const numero = formatearNumero(valorMostrado, decimales);
  return base === undefined || base === "" ? numero : `${base} ${numero}`;
}

/**
 * Los puntos de una curva ya evaluada, filtrados al tramo de tiempo visible y
 * convertidos a píxeles del área, con la `y` RECORTADA a `[0, area.alto]`
 * (regla 2 de la cabecera del módulo).
 *
 * Un punto fuera del rango de tiempo visible no aporta nada al trazo — ni
 * `xAPixel` lo necesita, que solo interpola dentro de `[t0, t1]` — y arrastrar
 * puntos invisibles solo complica lo que pinta `topes.ts` después.
 */
function puntosDeCurva(config: ConfiguracionTopes, puntos: Extract<LimiteResuelto, { tipo: "curva" }>): PuntoPixel[] {
  const { vista, area } = config;
  const tMin = Math.min(vista.t0, vista.t1);
  const tMax = Math.max(vista.t0, vista.t1);
  return puntos.puntos
    .filter((p) => p.t >= tMin && p.t <= tMax)
    .map((p) => ({
      x: xAPixel(p.t, vista, area.ancho),
      y: recortar(yAPixel(aMostrado(config, p.valorCanonico), vista, area.alto), 0, area.alto),
    }));
}

/**
 * Un borde de banda (`minimo` o `maximo`), como lista de puntos de píxel.
 *
 * Si es constante, son dos puntos que cubren todo el ancho del área a la
 * misma `y` (ya recortada): la representación mínima de una línea horizontal
 * que `topes.ts` puede pintar exactamente igual que un tramo de curva, sin
 * necesitar dos caminos de dibujo distintos para "banda plana" y "banda en
 * curva".
 */
function bordeDeBanda(config: ConfiguracionTopes, limite: LimiteResuelto): PuntoPixel[] {
  if (limite.tipo === "curva") return puntosDeCurva(config, limite);
  const y = recortar(yAPixel(aMostrado(config, limite.valorCanonico), config.vista, config.area.alto), 0, config.area.alto);
  return [
    { x: 0, y },
    { x: config.area.ancho, y },
  ];
}

/** La forma resuelta de un `LimiteResuelto` cuando es el lado único de una `LineaTope` (regla 1 de la cabecera: plana ancla, curva recorta). */
function formaDeLinea(config: ConfiguracionTopes, limite: LimiteResuelto): FormaResuelta {
  if (limite.tipo === "curva") {
    return { tipo: "curva", puntos: puntosDeCurva(config, limite) };
  }
  const valorMostrado = aMostrado(config, limite.valorCanonico);
  const pixelY = yAPixel(valorMostrado, config.vista, config.area.alto);
  const posicion: PosicionLinea =
    pixelY < 0
      ? { tipo: "fuera-arriba" }
      : pixelY > config.area.alto
        ? { tipo: "fuera-abajo" }
        : { tipo: "dentro", pixelY };
  return { tipo: "plano", posicion };
}

/** El valor mostrado de un `LimiteResuelto` para la etiqueta de texto: el valor constante, o el primero visible de la curva. */
function valorParaEtiqueta(config: ConfiguracionTopes, limite: LimiteResuelto): number | null {
  if (limite.tipo === "constante") return aMostrado(config, limite.valorCanonico);
  const primero = limite.puntos[0];
  return primero === undefined ? null : aMostrado(config, primero.valorCanonico);
}

function resolverLinea(config: ConfiguracionTopes, linea: LineaTope): LineaResuelta {
  const decimales = config.decimales ?? DECIMALES_POR_OMISION;
  const valor = valorParaEtiqueta(config, linea.limite);
  const etiqueta = valor === null ? (linea.etiqueta ?? "") : etiquetaConValor(linea.etiqueta, valor, decimales);
  return {
    id: linea.id,
    nivel: linea.nivel,
    etiqueta,
    forma: formaDeLinea(config, linea.limite),
  };
}

function resolverBanda(config: ConfiguracionTopes, banda: BandaTope): BandaResuelta {
  const decimales = config.decimales ?? DECIMALES_POR_OMISION;
  const vMin = valorParaEtiqueta(config, banda.minimo);
  const vMax = valorParaEtiqueta(config, banda.maximo);
  const etiquetaValores =
    vMin === null || vMax === null
      ? ""
      : `${formatearNumero(vMin, decimales)}…${formatearNumero(vMax, decimales)}`;
  const etiqueta =
    banda.etiqueta === undefined || banda.etiqueta === ""
      ? etiquetaValores
      : etiquetaValores === ""
        ? banda.etiqueta
        : `${banda.etiqueta} ${etiquetaValores}`;
  return {
    id: banda.id,
    nivel: banda.nivel,
    etiqueta,
    bordeMinimo: bordeDeBanda(config, banda.minimo),
    bordeMaximo: bordeDeBanda(config, banda.maximo),
  };
}

/**
 * Calcula toda la geometría de los topes a partir de la configuración.
 *
 * Cada `LineaTope` y cada `BandaTope` de la entrada produce EXACTAMENTE una
 * salida, en el mismo orden: `topes.ts` no filtra nada, así que un tope que no
 * deba verse (por ejemplo, uno desactivado) se decide ANTES de llamar aquí, no
 * dejando que la geometría lo descarte en silencio.
 */
export function calcularGeometriaTopes(config: ConfiguracionTopes): GeometriaTopes {
  return {
    area: config.area,
    lineas: config.lineas.map((linea) => resolverLinea(config, linea)),
    bandas: config.bandas.map((banda) => resolverBanda(config, banda)),
  };
}
