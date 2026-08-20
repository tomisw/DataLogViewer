/**
 * Pinta un mapa de calor de celdas (F4-04) en un `<svg>` que YA tiene los ejes
 * de `ejes.ts` pintados encima, mismo patrón que `topes/topes.ts` (F3-11,
 * F1-25, ADR-006).
 *
 * ORDEN DE LLAMADA, Y POR QUÉ NO ES EL MISMO QUE EL DE `topes.ts`
 * ====================================================================
 * `pintarEjes` sigue yendo primero —vacía el `<svg>` y pinta rejilla, ejes y
 * leyenda—, pero aquí el mapa de calor va DESPUÉS de los ejes y ANTES de los
 * topes, no después de los dos:
 *
 *     const geometriaEjes = pintarEjes(svg, configuracionEjes);
 *     pintarMapaDeCalor(svg, calcularGeometriaMapaDeCalor({ ..., area: geometriaEjes.area }));
 *     pintarTopes(svg, calcularGeometriaTopes({ ..., area: geometriaEjes.area }));
 *
 * La razón es que una celda de mapa de calor es un RELLENO —a diferencia de
 * una línea de tope o de la rejilla, que son trazos finos—, así que si se
 * pintara encima de todo taparía la rejilla interior por completo. La
 * solución no es reordenar para que la rejilla gane: es que este módulo NO
 * NECESITA la rejilla interior para que la malla se lea. Cada celda lleva su
 * propio contorno (`dlv-mapa-celda`, con `stroke`), que hace de rejilla —
 * célula a célula, exactamente donde tiene que estar, en vez de una rejilla
 * genérica de `ejes.ts` que no sabe dónde caen los bordes de la malla. Los
 * TICKS y ETIQUETAS de los ejes (fuera del área de celdas, en el margen) no
 * los tapa nada, y los topes (líneas de alerta, semitransparentes) siguen
 * yendo despues para que una línea crítica se vea POR ENCIMA del color de la
 * celda que atraviesa.
 *
 * DETALLE POR CELDA: `<title>` NATIVO, MÁS UN CALLBACK OPCIONAL
 * ===================================================================
 * Cada celda lleva un `<title>` hijo con las cinco estadísticas ya
 * formateadas: es el tooltip nativo del navegador, sin JavaScript adicional
 * ni una librería de UI (regla del proyecto: cero dependencias) — mismo
 * criterio que `cursor/cursor.ts` documenta para su tabla («el tooltip
 * nativo del navegador, sin dependencias»). `onSenalarCelda`, si se pasa, es
 * la costura para que quien monte la escena pinte el detalle en un panel
 * aparte (una tabla al lado del mapa, igual que la del cursor) en vez de
 * depender solo del tooltip del sistema operativo — se dispara en
 * `pointerenter`/`pointerleave`, comprobable con el doble de DOM
 * (`dom/doble-documento.ts#disparar`) sin necesitar un navegador de verdad.
 *
 * Como `ejes.ts` y `topes.ts`, esto es fontanería sin lógica —toda la
 * decisión (qué celda, en qué píxel, con qué color, con qué estado— ya la
 * tomó `geometria.ts`, que se prueba sin abrir un navegador— y por eso no
 * tiene pruebas propias: un fallo aquí se ve en pantalla, no se esconde.
 *
 * Sin librerías (regla del proyecto): solo `document.createElementNS`.
 */

import type { Color } from "../render/tipos.ts";
import { t } from "../locale/catalogo.ts";
import type { CeldaPintada, DetalleCelda, GeometriaMapaDeCalor } from "./tipos.ts";

const NS_SVG = "http://www.w3.org/2000/svg";

function crear<K extends keyof SVGElementTagNameMap>(
  svg: SVGSVGElement,
  etiqueta: K,
): SVGElementTagNameMap[K] {
  return svg.ownerDocument.createElementNS(NS_SVG, etiqueta) as SVGElementTagNameMap[K];
}

function atributos(elemento: SVGElement, valores: Readonly<Record<string, string>>): void {
  for (const [nombre, valor] of Object.entries(valores)) elemento.setAttribute(nombre, valor);
}

/** `Color` (componentes 0..1) a `rgba()` CSS. Misma fórmula que `ejes.ts#colorACss` (duplicada a propósito, ver su cabecera). */
function colorACss(color: Color): string {
  const canal = (c: number): number => Math.round(Math.max(0, Math.min(1, c)) * 255);
  return `rgba(${canal(color.r)}, ${canal(color.g)}, ${canal(color.b)}, ${color.a})`;
}

/** Texto del `<title>` nativo: las cinco estadísticas, una por línea, en el idioma activo. */
function textoDeDetalle(detalle: DetalleCelda): string {
  const lineas = [
    `${t("malla.cuenta")}: ${detalle.cuentaTexto}`,
    `${t("malla.media")}: ${detalle.mediaTexto}`,
    `${t("malla.desviacionTipica")}: ${detalle.desviacionTipicaTexto}`,
    `${t("malla.minimo")}: ${detalle.minimoTexto}`,
    `${t("malla.maximo")}: ${detalle.maximoTexto}`,
  ];
  if (detalle.estado === "vacia") lineas.push(t("malla.sinDatos"));
  else if (detalle.estado === "pocaConfianza") lineas.push(t("malla.pocaConfianza"));
  return lineas.join("\n");
}

export interface OpcionesMapaDeCalor {
  /**
   * Se dispara con el detalle de la celda señalada (`pointerenter`) o con
   * `null` al dejar de señalarla (`pointerleave`). Opcional: sin esta opción
   * el `<title>` nativo sigue funcionando por sí solo.
   */
  readonly onSenalarCelda?: (detalle: DetalleCelda | null) => void;
}

function pintarCelda(
  svg: SVGSVGElement,
  grupo: SVGGElement,
  celda: CeldaPintada,
  opciones: OpcionesMapaDeCalor,
): void {
  const rect = crear(svg, "rect");
  atributos(rect, {
    class: `dlv-mapa-celda dlv-mapa-celda--${celda.estado}`,
    x: String(celda.x),
    y: String(celda.y),
    width: String(celda.ancho),
    height: String(celda.alto),
    fill: colorACss(celda.color),
  });
  const titulo = crear(svg, "title");
  titulo.textContent = textoDeDetalle(celda.detalle);
  rect.appendChild(titulo);
  grupo.appendChild(rect);

  if (opciones.onSenalarCelda !== undefined) {
    const onSenalar = opciones.onSenalarCelda;
    rect.addEventListener("pointerenter", () => onSenalar(celda.detalle));
    rect.addEventListener("pointerleave", () => onSenalar(null));
  }
}

/** Pinta toda la `GeometriaMapaDeCalor` sobre `svg`. Ver la cabecera del módulo para el orden de llamada. */
export function pintarMapaDeCalor(
  svg: SVGSVGElement,
  geometria: GeometriaMapaDeCalor,
  opciones: OpcionesMapaDeCalor = {},
): void {
  if (geometria.celdas.length === 0) return;

  const grupo = crear(svg, "g");
  atributos(grupo, {
    class: "dlv-mapa-calor",
    transform: `translate(${geometria.area.x}, ${geometria.area.y})`,
  });
  svg.appendChild(grupo);

  for (const celda of geometria.celdas) pintarCelda(svg, grupo, celda, opciones);
}

export type {
  CeldaEstadisticas,
  CeldaPintada,
  ConfiguracionMapaDeCalor,
  DetalleCelda,
  EstadoCelda,
  GeometriaMapaDeCalor,
  MallaResuelta,
} from "./tipos.ts";
export { calcularGeometriaMapaDeCalor } from "./geometria.ts";
export { escalaDivergente, escalaMaximaDesdeDatos } from "./escala-divergente.ts";
