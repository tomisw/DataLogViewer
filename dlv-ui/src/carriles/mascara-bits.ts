/**
 * Carriles apilados para un canal `bitmask` (F3-14, docs/01 §1.10).
 *
 * DECODIFICAS ESTRUCTURA, NO SIGNIFICADO
 * =========================================
 * `data/enums.toml` declara `Trigger System Errors` (0…31, 5 bits) y
 * `Engine Protection Cause` (0…65535, 16 bits) como `clase = "bitmask"` pero
 * deja sus códigos SIN TRADUCIR a propósito: asignar un nombre a cada bit
 * exige documentación del fabricante que no hay todavía (F3-15, bloqueada).
 * Este módulo identifica cada carril por su ÍNDICE de bit (`InfoBit.indice`,
 * 0 = menos significativo) y nunca por un nombre inventado -- ni aquí ni en
 * `dlv_core.mascaras`, que es quien desempaqueta el entero al otro lado.
 *
 * QUÉ REUTILIZA DE F3-13 Y QUÉ AÑADE
 * =====================================
 * Un bit es, estructuralmente, un enum de dos códigos (0/1): por eso cada
 * carril de bit se pinta con `pintarCarril`/`calcularGeometriaCarril` de
 * `carril-estado.ts`/`geometria.ts` SIN TOCARLOS -- el `CubosEnum` de un bit
 * es literalmente el mismo contrato que ya usa un carril de marcha o de modo
 * de mapa. Lo que este módulo añade es la parte que F3-13 no necesitaba:
 * decidir qué bits se enseñan y apilar hasta 32 de esos carriles uno debajo
 * de otro. El apilado usa un `<svg>` anidado por bit (`FabricaSvg.crearSvg`,
 * añadido en `dom.ts` para esta tarea) en vez de duplicar `pintarBandas`/
 * `pintarTransiciones`: cada bit sigue siendo un carril de F3-13 de verdad,
 * solo que vive dentro de su propio viewport SVG con un desplazamiento en Y.
 *
 * TRES DECISIONES (informe de F3-14)
 * =====================================
 * 1. QUÉ BITS SE ENSEÑAN: mismo criterio que el selector de canales (F1-33,
 *    `canales/filtro.ts`) con los canales `constante`/`vacio` -- un bit que
 *    nunca se activó en todo el rango decodificado (`InfoBit.activo`, que
 *    calcula `dlv_core.mascaras.BitDecodificado` sobre el canal completo, no
 *    sobre la vista actual) se oculta por OMISIÓN para no dibujar hasta 16
 *    carriles vacíos, pero se CUENTA (`ResultadoFiltroBits.ocultos`) y se
 *    puede volver a enseñar con `mostrarInactivos` -- nunca se descarta en
 *    silencio, igual que un canal "constante" sigue en la lista de F1-33.
 * 2. LA ANCHURA NO SE RECORTA: `ResultadoFiltroBits.anchura` es siempre
 *    `config.bits.length`, el número de bits que declara la máscara, se
 *    muestren o no. "Esta protección no saltó en toda la tirada" es un dato
 *    (`docs/01` §1.10), no una ausencia -- ocultar un carril no es lo mismo
 *    que fingir que ese bit no existe, y por eso `anchura` viaja siempre
 *    junto a `ocultos` en vez de que la lista de bits simplemente sea más
 *    corta.
 * 3. UN PULSO DE UNA SOLA MUESTRA NO DESAPARECE: a diferencia de `NivelEnum`
 *    (F1-10), `NivelBits.or_bits` (`piramide.py`) NO necesita un
 *    `huboTransicion` aparte para resolver este problema -- ya lo resuelve
 *    el OR de bits en sí: un bit que se activó en una sola muestra de un
 *    cubo hace que el cubo entero decodifique a 1 en cualquier nivel de la
 *    pirámide (ver el docstring de `NivelBits`), así que la banda de
 *    `calcularGeometriaCarril` para ese cubo sale "encendida" y NUNCA
 *    desaparece por zoom-out. Lo que sí hereda de F3-13 sin cambios es la
 *    fusión de cubos consecutivos con el mismo valor en una sola banda: un
 *    bit que estuvo encendido en dos cubos vecinos se ve como una banda
 *    continua, exactamente igual que un enum. Por eso este módulo NO define
 *    su propio concepto de "transición": pasa `huboTransicion` tal cual
 *    viene en el `CubosEnum` de cada bit (si algún día se decidiera calcular
 *    una marca más fina sobre los bits, ya tiene dónde encajar sin cambiar
 *    este contrato).
 */

import { ALTO_BANDA_DEFECTO, calcularGeometriaCarril } from "./geometria.ts";
import { pintarCarril } from "./carril-estado.ts";
import type { ElementoSvg, FabricaSvg } from "./dom.ts";
import type { CubosEnum, DiccionarioCodigos, GeometriaCarril, RangoTiempo } from "./tipos.ts";
import { t } from "../locale/catalogo.ts";

/**
 * Un bit nunca tiene diccionario de códigos: 0/1 se enseñan crudos, marcados
 * con la clase `dlv-carril-*-sin-etiqueta` que ya pinta `carril-estado.ts`
 * para cualquier código ausente del diccionario. Es la lectura correcta para
 * un bit sin significado asignado (F3-15 bloqueada): "código sin traducir",
 * no un texto inventado que sugiera un significado que no está confirmado.
 */
const SIN_ETIQUETAS: DiccionarioCodigos = new Map();

/** Info estructural de un bit: posición y actividad, nunca significado. */
export interface InfoBit {
  /** Posición del bit dentro de la máscara (0 = menos significativo). NO es un nombre. */
  readonly indice: number;
  /** `true` si el bit estuvo a 1 en alguna muestra de TODO el rango cargado (`dlv_core.mascaras.BitDecodificado.activo`), no solo en la vista actual. */
  readonly activo: boolean;
}

/** Un bit ya decodificado y listo para pintar: la info estructural más su serie 0/1 como `CubosEnum`. */
export interface CubosBit extends InfoBit {
  /** La serie 0/1 de este bit, con la misma forma que un carril de enum (F3-13): `moda` solo toma los códigos 0 y 1. */
  readonly cubos: CubosEnum;
}

export interface OpcionesMascaraBits {
  readonly mostrarInactivos: boolean;
}

export interface ResultadoFiltroBits {
  readonly visibles: readonly CubosBit[];
  /** Cuántos de `anchura` bits se quedan fuera de `visibles` por no haberse activado nunca (decisión 1). */
  readonly ocultos: number;
  /** Anchura TOTAL declarada de la máscara (decisión 2): `bits.length`, se muestren o no todos. */
  readonly anchura: number;
}

/**
 * Decide qué bits se enseñan. Pura -- misma partición que `canales/filtro.ts`
 * frente a `selector-canales.ts`: aquí solo la decisión, en `pintarMascaraBits`
 * la fontanería de DOM que la consume.
 */
export function filtrarBits(
  bits: readonly CubosBit[],
  opciones: OpcionesMascaraBits,
): ResultadoFiltroBits {
  if (opciones.mostrarInactivos) {
    return { visibles: bits, ocultos: 0, anchura: bits.length };
  }
  const visibles = bits.filter((bit) => bit.activo);
  return { visibles, ocultos: bits.length - visibles.length, anchura: bits.length };
}

/** El texto que resume cuántos bits quedan ocultos, o cadena vacía si no hay nada que decir (mismo patrón que `canales/selector-canales.ts#textoResumenOcultos`). */
export function textoResumenBitsOcultos(resultado: ResultadoFiltroBits, mostrarInactivos: boolean): string {
  if (mostrarInactivos || resultado.ocultos === 0) return "";
  return (
    `${t("mascaraBits.ocultosPrefijo", { n: resultado.ocultos, total: resultado.anchura })} ` +
    t("mascaraBits.ocultosSufijo")
  );
}

/** Lo que necesita `calcularGeometriaMascaraBits`/`pintarMascaraBits` para dibujar la máscara apilada. */
export interface ConfiguracionMascaraBits {
  /** TODOS los bits de la anchura declarada (activos o no): el filtrado es responsabilidad de este módulo, no de quien llama. */
  readonly bits: readonly CubosBit[];
  readonly vista: RangoTiempo;
  readonly anchoPx: number;
  /** Alto de cada fila de bit, en píxeles CSS. Por omisión `ALTO_BANDA_DEFECTO`, igual que un carril de enum suelto. */
  readonly altoPorBitPx?: number;
  readonly mostrarInactivos: boolean;
}

/** Un carril de bit ya calculado, con su desplazamiento vertical dentro de la pila. */
export interface CarrilBitPintado {
  readonly indice: number;
  readonly yPx: number;
  readonly geometria: GeometriaCarril;
}

export interface GeometriaMascaraBits {
  readonly anchoPx: number;
  readonly altoPx: number;
  readonly carriles: readonly CarrilBitPintado[];
  readonly ocultos: number;
  readonly anchura: number;
}

/** La configuración de un único carril de bit dentro de la pila, para no repetirla entre la versión pura y la que pinta DOM. */
function configuracionDelBit(
  bit: CubosBit,
  config: ConfiguracionMascaraBits,
  altoPorBitPx: number,
): { cubos: CubosEnum; etiquetas: DiccionarioCodigos; vista: RangoTiempo; anchoPx: number; altoPx: number } {
  return {
    cubos: bit.cubos,
    etiquetas: SIN_ETIQUETAS,
    vista: config.vista,
    anchoPx: config.anchoPx,
    altoPx: altoPorBitPx,
  };
}

/**
 * Calcula la geometría de toda la pila SIN tocar el DOM: qué bits se ven,
 * dónde cae cada uno en Y y la geometría de sus bandas/transiciones
 * (reutilizando `calcularGeometriaCarril` de F3-13, sin duplicarla).
 */
export function calcularGeometriaMascaraBits(config: ConfiguracionMascaraBits): GeometriaMascaraBits {
  const altoPorBitPx = config.altoPorBitPx ?? ALTO_BANDA_DEFECTO;
  const { visibles, ocultos, anchura } = filtrarBits(config.bits, {
    mostrarInactivos: config.mostrarInactivos,
  });

  const carriles: CarrilBitPintado[] = visibles.map((bit, i) => ({
    indice: bit.indice,
    yPx: i * altoPorBitPx,
    geometria: calcularGeometriaCarril(configuracionDelBit(bit, config, altoPorBitPx)),
  }));

  return {
    anchoPx: config.anchoPx,
    altoPx: carriles.length * altoPorBitPx,
    carriles,
    ocultos,
    anchura,
  };
}

/**
 * Pinta la máscara apilada en un `<svg>` ya existente: una fila por bit
 * visible, cada una con su etiqueta de índice ("bit 3") y su propio
 * `<svg>` anidado pintado con `pintarCarril` de F3-13 sin modificarlo.
 *
 * Igual que `pintarCarril`: se vacía y se repinta entero en cada llamada, y
 * devuelve la `GeometriaMascaraBits` calculada.
 */
export function pintarMascaraBits(
  svg: ElementoSvg,
  fabrica: FabricaSvg,
  config: ConfiguracionMascaraBits,
): GeometriaMascaraBits {
  const altoPorBitPx = config.altoPorBitPx ?? ALTO_BANDA_DEFECTO;
  const { visibles, ocultos, anchura } = filtrarBits(config.bits, {
    mostrarInactivos: config.mostrarInactivos,
  });
  const altoPx = visibles.length * altoPorBitPx;

  svg.setAttribute("width", String(config.anchoPx));
  svg.setAttribute("height", String(altoPx));
  svg.setAttribute("viewBox", `0 0 ${config.anchoPx} ${altoPx}`);
  svg.replaceChildren();

  const carriles: CarrilBitPintado[] = [];
  for (let i = 0; i < visibles.length; i += 1) {
    const bit = visibles[i]!;
    const yPx = i * altoPorBitPx;

    const grupoFila = fabrica.crearG();
    grupoFila.classList.add("dlv-mascara-bits-fila");
    grupoFila.setAttribute("transform", `translate(0, ${yPx})`);

    const etiqueta = fabrica.crearText();
    etiqueta.classList.add("dlv-mascara-bits-indice");
    etiqueta.setAttribute("x", "4");
    etiqueta.setAttribute("y", String(altoPorBitPx / 2));
    etiqueta.setAttribute("dominant-baseline", "middle");
    // Índice del bit, nunca un nombre: ver la cabecera del módulo.
    etiqueta.textContent = t("mascaraBits.etiquetaBit", { n: bit.indice });
    grupoFila.appendChild(etiqueta);

    // Un `<svg>` anidado por bit: su propio viewport, reutilizando
    // `pintarCarril` de F3-13 entero (bandas + transiciones) sin duplicarlo.
    const svgBit = fabrica.crearSvg();
    svgBit.setAttribute("x", "0");
    svgBit.setAttribute("y", "0");
    svgBit.classList.add("dlv-mascara-bits-carril");
    const geometria = pintarCarril(svgBit, fabrica, configuracionDelBit(bit, config, altoPorBitPx));
    grupoFila.appendChild(svgBit);

    svg.appendChild(grupoFila);
    carriles.push({ indice: bit.indice, yPx, geometria });
  }

  return { anchoPx: config.anchoPx, altoPx, carriles, ocultos, anchura };
}

export type { CubosEnum, GeometriaCarril, RangoTiempo } from "./tipos.ts";
