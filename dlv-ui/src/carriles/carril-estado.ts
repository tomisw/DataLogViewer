/**
 * Pinta un carril de estado en un `<svg>` ya existente (F3-13).
 *
 * QUÉ ES UN CARRIL DE ESTADO Y POR QUÉ NO ES UNA CURVA
 * =====================================================
 * Un canal enumerado (marcha engranada, estado del motor, modo de mapa) no
 * tiene valores intermedios: "entre 2ª y 3ª" no existe. Dibujarlo como una
 * línea que sube y baja entre códigos numéricos sugiere que sí, y además es
 * ilegible con miles de cubos en pantalla. Un carril lo pinta como bandas de
 * color con su etiqueta — la lectura es "estuvo en 3ª de 12 s a 18 s", no
 * "aquí hay una escalera".
 *
 * Toda la aritmética (qué banda va dónde, qué cubos se fusionan, dónde caen
 * las marcas de transición) vive en `geometria.ts` y se prueba sin DOM, igual
 * que `ejes/geometria.ts` para los ejes. Este fichero es la fontanería que
 * copia esos números a nodos SVG a través de `FabricaSvg` (`dom.ts`), y por
 * eso SÍ tiene pruebas propias (`carril-estado.test.ts`, con el doble de
 * `dom-falso.ts`) — a diferencia de `ejes.ts`, que renuncia a probar su propia
 * fontanería porque un fallo "se ve en pantalla". Aquí no basta con eso: la
 * regla del enunciado es que un código sin etiqueta "se ve que le falta la
 * etiqueta, nunca en blanco", y esa es una propiedad de qué texto y qué clase
 * termina en el nodo, no algo que sea obvio con un vistazo. Fallarla en
 * silencio es exactamente lo que una prueba de este árbol atrapa.
 *
 * COLOR DATO VS. COLOR SEMÁNTICO
 * ===============================
 * El color de cada banda es el único valor "vivo" que este módulo escribe
 * como atributo (`fill`), por la misma razón que `ejes.ts` lo hace para el
 * cuadradito de la leyenda: es un dato por código, no un estilo fijo, así que
 * no hay clase CSS posible para él. La marca de transición, en cambio, es
 * puramente semántica (siempre significa lo mismo, sea cual sea el código) y
 * se deja enteramente a la clase `dlv-carril-transicion`, sin `fill` inline
 * — así el modo oscuro / alto contraste (F3-21) puede restilarla sin tocar
 * este fichero, igual que hace con la rejilla y el eje de `ejes.ts`.
 */

import { calcularGeometriaCarril } from "./geometria.ts";
import type { ElementoSvg, FabricaSvg } from "./dom.ts";
import { colorACss } from "./color.ts";
import type { ConfiguracionCarril, GeometriaCarril } from "./tipos.ts";

/**
 * Reconstruye por completo el carril de estado dentro de `svg`.
 *
 * Igual que `pintarEjes`: se vacía y se vuelve a pintar entero en cada
 * llamada (unas pocas decenas de nodos por banda visible, irrelevante frente
 * a llevar un diff manual), y devuelve la `GeometriaCarril` calculada por si
 * quien llama la necesita (p. ej. para alinear el carril con la rejilla de
 * tiempo del panel que tiene encima).
 */
export function pintarCarril(
  svg: ElementoSvg,
  fabrica: FabricaSvg,
  config: ConfiguracionCarril,
): GeometriaCarril {
  const geometria = calcularGeometriaCarril(config);

  svg.setAttribute("width", String(geometria.anchoPx));
  svg.setAttribute("height", String(geometria.altoPx));
  svg.setAttribute("viewBox", `0 0 ${geometria.anchoPx} ${geometria.altoPx}`);
  svg.replaceChildren();

  svg.appendChild(pintarBandas(fabrica, geometria));
  svg.appendChild(pintarTransiciones(fabrica, geometria));

  return geometria;
}

function pintarBandas(fabrica: FabricaSvg, geometria: GeometriaCarril): ElementoSvg {
  const grupo = fabrica.crearG();
  grupo.classList.add("dlv-carril-bandas");

  for (const banda of geometria.bandas) {
    const rect = fabrica.crearRect();
    rect.setAttribute("x", String(banda.xPx));
    rect.setAttribute("y", "0");
    rect.setAttribute("width", String(banda.anchoPx));
    rect.setAttribute("height", String(geometria.altoPx));
    // Dato por código, no estilo: ver la nota de cabecera. `fill` inline a
    // propósito, igual que la muestra de color de la leyenda en `ejes.ts`.
    rect.setAttribute("fill", colorACss(banda.color));
    rect.classList.add("dlv-carril-banda");
    if (banda.etiquetaFaltante) rect.classList.add("dlv-carril-banda--sin-etiqueta");
    grupo.appendChild(rect);

    const texto = fabrica.crearText();
    texto.setAttribute("x", String(banda.xPx + banda.anchoPx / 2));
    texto.setAttribute("y", String(geometria.altoPx / 2));
    texto.setAttribute("text-anchor", "middle");
    texto.setAttribute("dominant-baseline", "middle");
    texto.classList.add("dlv-carril-etiqueta");
    // Un código sin etiqueta en el diccionario se enseña como el código
    // crudo (ya lo resolvió `geometria.ts`: `banda.etiqueta === String(codigo)`)
    // Y con esta clase, para que se vea que falta — nunca en blanco, y nunca
    // indistinguible de una etiqueta real solo por el texto.
    if (banda.etiquetaFaltante) texto.classList.add("dlv-carril-etiqueta--sin-etiqueta");
    texto.textContent = banda.etiqueta;
    grupo.appendChild(texto);
  }

  return grupo;
}

function pintarTransiciones(fabrica: FabricaSvg, geometria: GeometriaCarril): ElementoSvg {
  const grupo = fabrica.crearG();
  grupo.classList.add("dlv-carril-transiciones");

  for (const marca of geometria.transiciones) {
    const rect = fabrica.crearRect();
    rect.setAttribute("x", String(marca.xPx));
    rect.setAttribute("y", "0");
    rect.setAttribute("width", String(marca.anchoPx));
    rect.setAttribute("height", String(geometria.altoPx));
    rect.classList.add("dlv-carril-transicion");
    grupo.appendChild(rect);
  }

  return grupo;
}

export type {
  BandaCarril,
  ConfiguracionCarril,
  CubosEnum,
  DiccionarioCodigos,
  GeometriaCarril,
  MarcaTransicion,
  RangoTiempo,
} from "./tipos.ts";
export { ALTO_BANDA_DEFECTO, ANCHO_MARCA_TRANSICION, calcularGeometriaCarril } from "./geometria.ts";
export { colorACss, colorPorCodigo } from "./color.ts";
export { elementoSvgDesdeNodo, fabricaSvgDesdeDocumento } from "./dom.ts";
export type { ElementoSvg, FabricaSvg } from "./dom.ts";
