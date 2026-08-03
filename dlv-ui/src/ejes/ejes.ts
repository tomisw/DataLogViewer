/**
 * Pinta ejes, rejilla y leyenda en un `<svg>` ya existente (F1-25, ADR-006).
 *
 * ADR-006: «los adornos estáticos (ejes, rejilla, leyenda, etiquetas) van en
 * SVG/DOM, donde no hay volumen» — a diferencia de `render/renderizador.ts`,
 * aquí no hay presupuesto de fotograma que cuidar, así que este módulo
 * reconstruye el árbol SVG entero en cada llamada. Es deliberadamente la
 * fontanería sin lógica: toda la decisión —qué tick va dónde, con qué
 * etiqueta— ya la tomó `geometria.ts`, que se prueba sin abrir un navegador.
 * Este fichero solo copia esos números a atributos `x`/`y`/`x1`/`y1`… y por
 * eso, igual que los shaders de `programa.ts`, no tiene pruebas propias: un
 * fallo aquí se ve en pantalla, no se esconde.
 *
 * Sin librerías (regla de la tarea): `document.createElementNS`, como
 * `main.ts`. El color de cada serie de la leyenda es el único dato "vivo" que
 * pinta este módulo con un valor no fijo — todo lo demás son clases CSS para
 * que el modo oscuro / alto contraste (F3-21, que depende de esta tarea)
 * pueda restilar sin tocar este fichero.
 */

import type { Color } from "../render/tipos.ts";
import { calcularGeometriaEjes } from "./geometria.ts";
import type { ConfiguracionEjes, GeometriaEjes } from "./tipos.ts";

const NS_SVG = "http://www.w3.org/2000/svg";

/** Ancho/alto del cuadradito de color de cada entrada de la leyenda. */
const LADO_MUESTRA_LEYENDA = 10;
/** Alto de fila de la leyenda (muestra + texto), en píxeles CSS. */
const ALTO_FILA_LEYENDA = 16;
/** Margen desde la esquina superior derecha del SVG hasta la leyenda. */
const MARGEN_LEYENDA = 8;

function crear<K extends keyof SVGElementTagNameMap>(
  etiqueta: K,
): SVGElementTagNameMap[K] {
  return document.createElementNS(NS_SVG, etiqueta) as SVGElementTagNameMap[K];
}

function atributos(elemento: SVGElement, valores: Readonly<Record<string, string>>): void {
  for (const [nombre, valor] of Object.entries(valores)) elemento.setAttribute(nombre, valor);
}

/** `Color` (componentes 0..1, como los que sube el renderizador a la GPU) a `rgba()` CSS. */
function colorACss(color: Color): string {
  const canal = (c: number): number => Math.round(Math.max(0, Math.min(1, c)) * 255);
  return `rgba(${canal(color.r)}, ${canal(color.g)}, ${canal(color.b)}, ${color.a})`;
}

function vaciar(svg: SVGSVGElement): void {
  while (svg.firstChild !== null) svg.removeChild(svg.firstChild);
}

function pintarRejillaYEje(svg: SVGSVGElement, geometria: GeometriaEjes): void {
  const { area } = geometria;
  const grupo = crear("g");
  grupo.setAttribute("class", "dlv-ejes-area");
  grupo.setAttribute("transform", `translate(${area.x}, ${area.y})`);
  svg.appendChild(grupo);

  // Rejilla vertical (una línea por tick de tiempo) + etiqueta bajo el eje X.
  for (const tick of geometria.ticksX) {
    const linea = crear("line");
    atributos(linea, {
      class: "dlv-ejes-rejilla dlv-ejes-rejilla-x",
      x1: String(tick.pixel),
      x2: String(tick.pixel),
      y1: "0",
      y2: String(area.alto),
    });
    grupo.appendChild(linea);

    const etiqueta = crear("text");
    atributos(etiqueta, {
      class: "dlv-ejes-etiqueta dlv-ejes-etiqueta-x",
      x: String(tick.pixel),
      y: String(area.alto + 16),
      "text-anchor": "middle",
    });
    etiqueta.textContent = tick.etiqueta;
    grupo.appendChild(etiqueta);
  }

  // Rejilla horizontal (una línea por tick de valor) + etiqueta a la izquierda.
  for (const tick of geometria.ticksY) {
    const linea = crear("line");
    atributos(linea, {
      class: "dlv-ejes-rejilla dlv-ejes-rejilla-y",
      x1: "0",
      x2: String(area.ancho),
      y1: String(tick.pixel),
      y2: String(tick.pixel),
    });
    grupo.appendChild(linea);

    const etiqueta = crear("text");
    atributos(etiqueta, {
      class: "dlv-ejes-etiqueta dlv-ejes-etiqueta-y",
      x: "-8",
      y: String(tick.pixel),
      "text-anchor": "end",
      "dominant-baseline": "middle",
    });
    etiqueta.textContent = tick.etiqueta;
    grupo.appendChild(etiqueta);
  }

  // Marco del área de dibujo: los dos ejes (izquierdo y de abajo), no los
  // cuatro lados — la rejilla ya marca los otros dos bordes con su propio tick.
  const ejeX = crear("line");
  atributos(ejeX, {
    class: "dlv-ejes-eje",
    x1: "0",
    x2: String(area.ancho),
    y1: String(area.alto),
    y2: String(area.alto),
  });
  grupo.appendChild(ejeX);

  const ejeY = crear("line");
  atributos(ejeY, { class: "dlv-ejes-eje", x1: "0", x2: "0", y1: "0", y2: String(area.alto) });
  grupo.appendChild(ejeY);

  // Título del eje Y (unidad ya mostrada), girado, en el margen izquierdo.
  const tituloY = crear("text");
  atributos(tituloY, {
    class: "dlv-ejes-titulo dlv-ejes-titulo-y",
    x: "0",
    y: "0",
    transform: `translate(${-area.x + 14}, ${area.alto / 2}) rotate(-90)`,
    "text-anchor": "middle",
  });
  tituloY.textContent = geometria.tituloY;
  grupo.appendChild(tituloY);

  // Unidad del eje X, junto a la última etiqueta.
  const tituloX = crear("text");
  atributos(tituloX, {
    class: "dlv-ejes-titulo dlv-ejes-titulo-x",
    x: String(area.ancho),
    y: String(area.alto + 16),
    "text-anchor": "end",
    dx: "36",
  });
  tituloX.textContent = geometria.unidadX;
  grupo.appendChild(tituloX);
}

function pintarLeyenda(svg: SVGSVGElement, geometria: GeometriaEjes): void {
  if (geometria.leyenda.length === 0) return;

  const grupo = crear("g");
  grupo.setAttribute("class", "dlv-ejes-leyenda");
  svg.appendChild(grupo);

  const anchoEstimado = 140;
  const alto = geometria.leyenda.length * ALTO_FILA_LEYENDA;
  const xBase = Math.max(0, geometria.anchoPx - anchoEstimado - MARGEN_LEYENDA);
  const yBase = MARGEN_LEYENDA;
  grupo.setAttribute("transform", `translate(${xBase}, ${yBase})`);

  // Fondo semitransparente: sin él, la leyenda se confunde con la rejilla que
  // tiene detrás cuando el panel está lleno de canales.
  const fondo = crear("rect");
  atributos(fondo, {
    class: "dlv-ejes-leyenda-fondo",
    x: "0",
    y: "0",
    width: String(anchoEstimado),
    height: String(alto),
    rx: "3",
  });
  grupo.appendChild(fondo);

  geometria.leyenda.forEach((entrada, indice) => {
    const y = indice * ALTO_FILA_LEYENDA;

    const muestra = crear("rect");
    atributos(muestra, {
      class: "dlv-ejes-leyenda-muestra",
      x: "4",
      y: String(y + (ALTO_FILA_LEYENDA - LADO_MUESTRA_LEYENDA) / 2),
      width: String(LADO_MUESTRA_LEYENDA),
      height: String(LADO_MUESTRA_LEYENDA),
      fill: colorACss(entrada.color),
    });
    grupo.appendChild(muestra);

    const texto = crear("text");
    atributos(texto, {
      class: "dlv-ejes-leyenda-texto",
      x: String(4 + LADO_MUESTRA_LEYENDA + 4),
      y: String(y + ALTO_FILA_LEYENDA / 2),
      "dominant-baseline": "middle",
    });
    texto.textContent = `${entrada.nombre} (${entrada.unidad})`;
    grupo.appendChild(texto);
  });
}

/**
 * Reconstruye por completo los ejes, la rejilla y la leyenda de `svg`.
 *
 * Se vacía y se vuelve a pintar entero en cada llamada, no se actualiza nodo
 * a nodo: a diferencia del lienzo WebGL2, aquí no hay miles de vértices por
 * fotograma, así que el coste de reconstruir el árbol —unas decenas de
 * elementos— es irrelevante frente a la complejidad de llevar un diff manual.
 * Devuelve la `GeometriaEjes` calculada por si quien llama la necesita (por
 * ejemplo, para alinear el cursor de F1-29 con la misma rejilla).
 */
export function pintarEjes(svg: SVGSVGElement, config: ConfiguracionEjes): GeometriaEjes {
  atributos(svg, {
    width: String(config.anchoPx),
    height: String(config.altoPx),
    viewBox: `0 0 ${config.anchoPx} ${config.altoPx}`,
  });
  vaciar(svg);

  const geometria = calcularGeometriaEjes(config);
  pintarRejillaYEje(svg, geometria);
  pintarLeyenda(svg, geometria);
  return geometria;
}

export type { ConfiguracionEjes, GeometriaEjes, SerieLeyenda, TickResuelto, AreaDibujo } from "./tipos.ts";
export { calcularGeometriaEjes, MARGEN_EJES } from "./geometria.ts";
