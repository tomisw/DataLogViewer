/**
 * Exportación de la vista actual a PNG/SVG (F4-12, E8.2, ADR-006).
 *
 * DÓNDE VIVE ESTA MITAD, Y POR QUÉ
 * =================================
 * PNG y SVG son de la VISTA, así que van en `dlv-ui`, no en `dlv-api`: la
 * otra mitad de la tarea (CSV/Parquet, que son de los DATOS) vive en
 * `dlv_api.exportacion`, con Polars detrás, porque un navegador no escribe
 * Parquet. ADR-006 dice cómo está montada la vista y por qué exportarla no es
 * "capturar el lienzo": «se dibuja desde la pirámide con WebGL2; los adornos
 * estáticos (ejes, rejilla, leyenda, etiquetas) van en SVG/DOM». Un PNG que
 * solo capture el `<canvas>` sale sin ejes, sin leyenda y sin unidades — es
 * exactamente el defecto que este módulo existe para no tener. Las dos capas
 * viven superpuestas en el DOM con el mismo tamaño (`aplicacion.ts`:
 * `canvas` y `svg`, los dos `position: absolute; inset: 0`), así que
 * componerlas es dibujar la una encima de la otra en ese mismo orden.
 *
 * EL MOMENTO EN QUE HAY QUE LEER EL LIENZO, Y POR QUÉ IMPORTA
 * =============================================================
 * `Renderizador.desdeLienzo` (`render/renderizador.ts`) crea el contexto
 * WebGL2 SIN `preserveDrawingBuffer`, a propósito (rendimiento: conservar el
 * búfer de dibujo tiene coste en cada fotograma, y el renderizador redibuja
 * en cada uno). La consecuencia para exportar: el navegador puede vaciar el
 * búfer de dibujo justo después de componerlo en pantalla, y ese vaciado no
 * está atado a nada que este módulo controle salvo UNA cosa — ocurre entre
 * tareas del bucle de eventos, no en mitad de una. Por eso `capturarTrazoPNG`
 * hace dos cosas seguidas, en la misma vuelta de síncrono, sin ningún
 * `await` entre medias: (1) pide un fotograma nuevo con `dibujar()` y (2) lee
 * el lienzo con `toDataURL()` inmediatamente. Si se aplaza la lectura a un
 * `requestAnimationFrame`, a una promesa que ya se resolvió, o a cualquier
 * cosa que ceda el hilo antes de leer, el lienzo puede salir negro — no
 * intermitentemente en el sentido de "a veces", sino de forma consistente en
 * cuanto algo del contorno cambia (un `await` de más al refactorizar, por
 * ejemplo). Ninguna prueba de este fichero puede demostrar esto contra un
 * navegador de verdad (`vitest.config.ts` corre en Node); lo que sí prueban
 * `capturarTrazoPNG.test.ts` es el ORDEN de las llamadas —`dibujar` antes que
 * `toDataURL`, sin nada en medio— contra el doble de siempre
 * (`render/doble-gl.ts`), que es la parte de la propiedad que SÍ se puede
 * comprobar sin GPU.
 *
 * SVG: RASTER (el trazo) + VECTOR (los ejes), NO EL TRAZO VECTORIZADO
 * =====================================================================
 * "Exportar a SVG" no vectoriza el trazo: una serie de varios millones de
 * puntos como *paths* SVG no es un fichero que un lector abra, y de todas
 * formas el trazo no vive aquí sino en la GPU (ADR-006: "el renderizador
 * recibe cubos y una escala, y no sabe nada de logs, unidades ni perfiles").
 * Lo que sí es vectorial de verdad —y sigue siéndolo en el fichero
 * exportado— son los ejes, la rejilla y la leyenda, que ya son SVG en pantalla
 * (`ejes/ejes.ts`). Este módulo incrusta el PNG del trazo como una `<image>`
 * de fondo, en las MISMAS coordenadas CSS que usa `pintarEjes`
 * (`anchoPx`/`altoPx`), y deja el resto del SVG tal cual — con eso, el texto
 * de los ejes y la leyenda siguen siendo texto de verdad, seleccionable y
 * escalable, dentro de un fichero que se abre en cualquier visor de SVG.
 *
 * `insertarTrazoEnSvg` compone las dos cosas con manipulación de TEXTO, no
 * clonando el `SVGSVGElement` con `cloneNode`/`createElementNS`: así la parte
 * que decide qué texto insertar y dónde se prueba en Node sin DOM, igual que
 * `ejes/geometria.ts` prueba la aritmética sin `document`. El propio
 * `pintarEjes` (DOM real) es, como los shaders de `programa.ts`, la parte que
 * no tiene pruebas propias por el mismo motivo que ellos: un fallo se ve en
 * pantalla, no se esconde.
 */

import type { Renderizador } from "../render/renderizador.ts";
import type { Vista } from "../render/tipos.ts";

/**
 * Lo que este módulo necesita del `<canvas>` WebGL2 para capturar un
 * fotograma. `HTMLCanvasElement` lo cumple de sobra; un doble de pruebas
 * también, y por eso `capturarTrazoPNG` se puede probar en Node.
 */
export interface LienzoCaptura {
  readonly width: number;
  readonly height: number;
  toDataURL(tipo?: string): string;
}

/**
 * Redibuja y lee el trazo WebGL2 como PNG, EN LA MISMA VUELTA DE SÍNCRONO.
 *
 * Ver la sección "EL MOMENTO EN QUE HAY QUE LEER EL LIENZO" en la cabecera
 * del módulo: `renderizador.dibujar(...)` y `lienzo.toDataURL(...)` tienen
 * que ir uno detrás de otro sin ceder el hilo, o el lienzo puede leerse ya
 * vacío. Por eso esta función es síncrona y no `async`: un `async` sin
 * ningún `await` interno sigue devolviendo una `Promise` que no se resuelve
 * hasta la siguiente vuelta de micro-tareas, y aunque en la práctica eso no
 * basta para que el navegador vacíe el búfer, no hay necesidad de arriesgarlo
 * cuando la alternativa síncrona es igual de simple.
 */
export function capturarTrazoPNG(
  renderizador: Renderizador,
  lienzo: LienzoCaptura,
  vista: Vista,
  vistaPorSerie?: ReadonlyMap<string, Vista>,
): string {
  renderizador.dibujar(vista, vistaPorSerie);
  return lienzo.toDataURL("image/png");
}

/**
 * Escapa lo mínimo que un valor de atributo XML necesita. Una URL de datos
 * PNG en base64 no contiene ninguno de estos cuatro caracteres —el alfabeto
 * base64 es `A-Za-z0-9+/=`—, así que esto no debería activarse nunca en la
 * práctica; se aplica igual porque una función que compone XML a partir de
 * texto no debe fiarse de esa garantía en silencio.
 */
function escaparAtributoXml(valor: string): string {
  return valor
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Inserta el trazo (como `<image>`, en `urlTrazoPng`) al PRINCIPIO de un SVG
 * ya serializado, justo después de su etiqueta de apertura — así queda
 * DETRÁS de todo lo que `pintarEjes` ya dibujó (rejilla, ejes, leyenda), que
 * es el orden correcto: los adornos van encima del trazo, no al revés.
 *
 * Manipulación de texto y no del DOM (ver la cabecera del módulo): `svgTexto`
 * es la salida de `XMLSerializer.serializeToString` sobre el `<svg>` que ya
 * pintó `pintarEjes`, así que se asume que empieza por `<svg ...>` — es lo
 * que ese serializador produce siempre para un elemento raíz sin namespace
 * adicional.
 *
 * `ancho`/`alto` tienen que ser los mismos píxeles CSS que
 * `ConfiguracionEjes.anchoPx`/`.altoPx` (F1-25): son las unidades del
 * `viewBox` del SVG, no los píxeles de dispositivo del `<canvas>` WebGL2
 * (que ya vienen multiplicados por el DPR, `render/renderizador.ts#Viewport`)
 * — usar estos últimos aquí dibujaría el trazo varias veces más grande que
 * la rejilla que se supone que coincide con él.
 */
export function insertarTrazoEnSvg(
  svgTexto: string,
  urlTrazoPng: string,
  ancho: number,
  alto: number,
): string {
  const cierre = svgTexto.indexOf(">");
  if (cierre === -1) {
    throw new Error(
      "el texto SVG no tiene ninguna etiqueta de apertura reconocible: " +
        "¿de verdad viene de `XMLSerializer.serializeToString` sobre un `<svg>`?",
    );
  }
  const etiquetaImagen =
    `<image x="0" y="0" width="${ancho}" height="${alto}" ` +
    `preserveAspectRatio="none" href="${escaparAtributoXml(urlTrazoPng)}"/>`;
  return svgTexto.slice(0, cierre + 1) + etiquetaImagen + svgTexto.slice(cierre + 1);
}

/**
 * Lo que este módulo necesita del documento para las dos operaciones que de
 * verdad exigen DOM/Canvas 2D y no se pueden reducir a texto: componer el
 * PNG final (trazo + ejes, los dos raster) y serializar el `<svg>` de ejes a
 * texto. Superficie mínima, igual que `render/contexto.ts`
 * (`ContextoGL`) y `paneles/contexto-dom.ts`: `HTMLDocument`/`Image`/
 * `XMLSerializer` reales la cumplen sin adaptador, y un doble de pruebas
 * también, aunque aquí no hay ningún doble que sirva para comprobar que el
 * PNG compuesto "se ve bien" — eso es un juicio visual, fuera de una prueba
 * unitaria, igual que el resto de este fichero deja fuera lo que solo se
 * puede ver en pantalla.
 */
export interface EntornoExportacion {
  /** Un lienzo 2D fuera de pantalla, del tamaño pedido. */
  crearLienzoDestino(ancho: number, alto: number): LienzoDestino;
  /** Decodifica una URL de datos (PNG o SVG) a una imagen dibujable. */
  cargarImagen(urlDatos: string): Promise<ImagenCargada>;
  /** El `<svg>` de ejes, como texto XML autocontenido. */
  serializarSvg(svg: SVGSVGElement): string;
}

/** Una imagen ya decodificada, lista para `LienzoDestino.dibujarImagen`. */
export interface ImagenCargada {
  readonly width: number;
  readonly height: number;
}

/** El lienzo 2D fuera de pantalla donde se componen las dos capas. */
export interface LienzoDestino {
  dibujarImagen(imagen: ImagenCargada, x: number, y: number, ancho: number, alto: number): void;
  aBlob(tipo: string): Promise<Blob>;
}

/**
 * El entorno de verdad: `document`/`Image`/`XMLSerializer` del navegador.
 *
 * Cada método los usa dentro de su cuerpo, no en el ámbito del módulo, para
 * que `import` de este fichero no falle en un entorno sin ellos (Node, en las
 * pruebas) — mismo motivo por el que `dlv_api/__init__.py` no importa
 * `dlv_api.main` (ver el informe de F4-12).
 */
export const ENTORNO_EXPORTACION_REAL: EntornoExportacion = {
  crearLienzoDestino(ancho: number, alto: number): LienzoDestino {
    const lienzo = document.createElement("canvas");
    lienzo.width = ancho;
    lienzo.height = alto;
    const ctx = lienzo.getContext("2d");
    if (ctx === null) {
      throw new Error("no se pudo crear un contexto 2D para componer la exportación");
    }
    return {
      dibujarImagen(imagen, x, y, ancho2, alto2): void {
        // En este entorno real, `imagen` es siempre el `HTMLImageElement` que
        // devolvió `cargarImagen` de este mismo objeto: la interfaz solo
        // expone `width`/`height` porque es lo único que necesita la parte
        // de este módulo que se prueba sin navegador (ver `ImagenCargada`),
        // igual que `ContextoGL` recorta `WebGL2RenderingContext` a lo que
        // usa `renderizador.ts`.
        ctx.drawImage(imagen as unknown as CanvasImageSource, x, y, ancho2, alto2);
      },
      aBlob(tipo: string): Promise<Blob> {
        return new Promise((resolver, rechazar) => {
          lienzo.toBlob((blob) => {
            if (blob === null) {
              rechazar(new Error(`no se pudo codificar el lienzo de salida como ${tipo}`));
              return;
            }
            resolver(blob);
          }, tipo);
        });
      },
    };
  },
  cargarImagen(urlDatos: string): Promise<ImagenCargada> {
    return new Promise((resolver, rechazar) => {
      const imagen = new Image();
      imagen.onload = (): void => resolver(imagen);
      imagen.onerror = (): void =>
        rechazar(new Error("no se pudo decodificar una imagen para la exportación"));
      imagen.src = urlDatos;
    });
  },
  serializarSvg(svg: SVGSVGElement): string {
    return new XMLSerializer().serializeToString(svg);
  },
};

/** Lo que hace falta para exportar la vista actual de un panel. */
export interface ObjetivoExportacion {
  readonly renderizador: Renderizador;
  /** El `<canvas>` WebGL2 real del panel (`EstadoPanel.canvas`). */
  readonly lienzo: LienzoCaptura;
  /** El `<svg>` de ejes ya pintado por `pintarEjes` (`EstadoPanel.svg`). */
  readonly svg: SVGSVGElement;
  readonly vista: Vista;
  readonly vistaPorSerie?: ReadonlyMap<string, Vista>;
  /**
   * Las mismas dimensiones en píxeles CSS que se pasaron a `pintarEjes`
   * (`ConfiguracionEjes.anchoPx`/`.altoPx`), NO `lienzo.width`/`.height`
   * (píxeles de dispositivo, con el DPR ya multiplicado). Es la unidad del
   * `viewBox` del SVG, y `insertarTrazoEnSvg` la necesita para que el trazo
   * incrustado quede exactamente donde la rejilla lo espera.
   */
  readonly anchoPx: number;
  readonly altoPx: number;
}

function urlDatosSvg(textoSvg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(textoSvg)}`;
}

/**
 * Exporta la vista actual a SVG: el trazo incrustado como PNG de fondo, y los
 * ejes/rejilla/leyenda como el vector de verdad que ya eran en pantalla.
 *
 * Solo necesita `serializarSvg` del entorno (no `crearLienzoDestino` ni
 * `cargarImagen`): la composición es texto, no dibujo — ver
 * `insertarTrazoEnSvg` en la cabecera del módulo.
 */
export function exportarComoSVG(
  objetivo: ObjetivoExportacion,
  entorno: Pick<EntornoExportacion, "serializarSvg"> = ENTORNO_EXPORTACION_REAL,
): Blob {
  const urlTrazo = capturarTrazoPNG(
    objetivo.renderizador,
    objetivo.lienzo,
    objetivo.vista,
    objetivo.vistaPorSerie,
  );
  const textoEjes = entorno.serializarSvg(objetivo.svg);
  const textoCompuesto = insertarTrazoEnSvg(textoEjes, urlTrazo, objetivo.anchoPx, objetivo.altoPx);
  return new Blob([textoCompuesto], { type: "image/svg+xml" });
}

/**
 * Exporta la vista actual a PNG: las dos capas compuestas en un lienzo 2D
 * fuera de pantalla, a la resolución de DISPOSITIVO del `<canvas>` WebGL2
 * (`lienzo.width`/`.height`, con el DPR ya multiplicado) — es la resolución
 * más alta de las dos capas, así que componer ahí y no en píxeles CSS es lo
 * que evita que el texto de los ejes salga borroso en una pantalla de alta
 * densidad.
 *
 * El trazo se captura ANTES de cualquier `await` (ver
 * `capturarTrazoPNG`); todo lo que viene después —decodificar las dos
 * imágenes y componerlas— puede tardar lo que haga falta, porque ya no
 * depende del búfer de dibujo de WebGL2, sino de una cadena de texto (la URL
 * de datos) que ya no cambia.
 */
export async function exportarComoPNG(
  objetivo: ObjetivoExportacion,
  entorno: EntornoExportacion = ENTORNO_EXPORTACION_REAL,
): Promise<Blob> {
  const urlTrazo = capturarTrazoPNG(
    objetivo.renderizador,
    objetivo.lienzo,
    objetivo.vista,
    objetivo.vistaPorSerie,
  );
  const urlEjes = urlDatosSvg(entorno.serializarSvg(objetivo.svg));

  const [trazo, ejes] = await Promise.all([entorno.cargarImagen(urlTrazo), entorno.cargarImagen(urlEjes)]);

  const ancho = objetivo.lienzo.width;
  const alto = objetivo.lienzo.height;
  const destino = entorno.crearLienzoDestino(ancho, alto);
  destino.dibujarImagen(trazo, 0, 0, ancho, alto);
  destino.dibujarImagen(ejes, 0, 0, ancho, alto);
  return destino.aBlob("image/png");
}
