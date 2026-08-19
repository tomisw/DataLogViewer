/**
 * Pinta topes (líneas y bandas de alerta) en un `<svg>` que YA tiene los ejes
 * de `ejes.ts` pintados encima (F3-11, F1-25, ADR-006).
 *
 * ORDEN DE LLAMADA: DESPUÉS DE `pintarEjes`, EN EL MISMO `<svg>`
 * ==================================================================
 * `pintarTopes` no vacía el `<svg>` (a diferencia de `pintarEjes`, que sí lo
 * hace): AÑADE su propio grupo (`dlv-topes`) encima de lo que ya haya. La
 * secuencia correcta en cada repintado es:
 *
 *     const geometriaEjes = pintarEjes(svg, configuracionEjes);
 *     pintarTopes(svg, calcularGeometriaTopes({ ..., area: geometriaEjes.area }));
 *
 * `pintarEjes` ya vacía el `<svg>` entero al principio de cada llamada, así
 * que un grupo de topes del fotograma anterior desaparece con él — no hace
 * falta que este módulo lleve su propia lógica de "quitar el grupo anterior".
 * Llamar a `pintarTopes` SIN haber llamado antes a `pintarEjes` en el mismo
 * `<svg>` deja el grupo de topes huérfano encima de lo que hubiera antes.
 *
 * MISMO SISTEMA DE COORDENADAS QUE LOS EJES, A PROPÓSITO
 * ==========================================================
 * El grupo se traslada con `translate(area.x, area.y)`, el mismo `AreaDibujo`
 * que calculó `calcularGeometriaEjes` — por eso `GeometriaTopes.area` lo lleva
 * consigo. Un `<svg>` separado para los topes habría significado calcular esa
 * traducción dos veces, con el riesgo de que un cambio de márgenes
 * desalineara la línea de tope de la rejilla que la explica.
 *
 * Como `ejes.ts`, esto es fontanería sin lógica —toda la decisión (qué línea,
 * en qué píxel, plana o anclada al borde) ya la tomó `geometria.ts`, que se
 * prueba sin abrir un navegador— y por eso, igual que `ejes.ts`, no tiene
 * pruebas propias: un fallo aquí se ve en pantalla, no se esconde.
 *
 * Sin librerías (regla del proyecto): solo `document.createElementNS`.
 */

import type { BandaResuelta, GeometriaTopes, LineaResuelta, NivelTope, PuntoPixel } from "./tipos.ts";

const NS_SVG = "http://www.w3.org/2000/svg";

/** Alto y medio-ancho del triángulo que marca un tope anclado al borde (fuera de rango). */
const MARCA_ALTO = 8;
const MARCA_MEDIO_ANCHO = 5;
/** Separación desde el borde izquierdo del área para líneas, marcas y etiquetas de texto.
 *  A la izquierda y no a la derecha porque la leyenda (`ejes.ts#MARGEN_LEYENDA`) y la
 *  tabla del cursor viven las dos a la derecha del panel (arriba y abajo respectivamente,
 *  ver `app/aplicacion.ts#montarPanel`); el lado izquierdo es el único libre. */
const MARGEN_X = 4;

function crear<K extends keyof SVGElementTagNameMap>(
  svg: SVGSVGElement,
  etiqueta: K,
): SVGElementTagNameMap[K] {
  return svg.ownerDocument.createElementNS(NS_SVG, etiqueta) as SVGElementTagNameMap[K];
}

function atributos(elemento: SVGElement, valores: Readonly<Record<string, string>>): void {
  for (const [nombre, valor] of Object.entries(valores)) elemento.setAttribute(nombre, valor);
}

function puntosATexto(puntos: readonly PuntoPixel[]): string {
  return puntos.map((p) => `${p.x},${p.y}`).join(" ");
}

function pintarEtiqueta(svg: SVGSVGElement, grupo: SVGGElement, x: number, y: number, nivel: NivelTope, texto: string): void {
  if (texto === "") return;
  const nodo = crear(svg, "text");
  atributos(nodo, {
    class: `dlv-topes-etiqueta dlv-topes-etiqueta--${nivel}`,
    x: String(x),
    y: String(y),
  });
  nodo.textContent = texto;
  grupo.appendChild(nodo);
}

/** Línea horizontal a todo el ancho del área, para un tope PLANO dentro de rango. */
function pintarLineaDentro(svg: SVGSVGElement, grupo: SVGGElement, ancho: number, pixelY: number, linea: LineaResuelta): void {
  const trazo = crear(svg, "line");
  atributos(trazo, {
    class: `dlv-topes-linea dlv-topes-linea--${linea.nivel}`,
    x1: "0",
    x2: String(ancho),
    y1: String(pixelY),
    y2: String(pixelY),
  });
  grupo.appendChild(trazo);
  pintarEtiqueta(svg, grupo, MARGEN_X, pixelY - 3, linea.nivel, linea.etiqueta);
}

/**
 * Marca triangular anclada al borde superior o inferior del área, para un
 * tope PLANO fuera del rango visible (`geometria.ts`, regla 1 de su cabecera).
 *
 * Apunta hacia FUERA del área (arriba si el tope está por encima de lo
 * visible, abajo si está por debajo): es el mismo lenguaje visual que una
 * flecha de "sigue subiendo/bajando", y no necesita texto adicional para
 * decir de qué lado se ha salido — la posición del triángulo ya lo dice.
 */
function pintarMarcaFueraDeRango(
  svg: SVGSVGElement,
  grupo: SVGGElement,
  alto: number,
  direccion: "arriba" | "abajo",
  linea: LineaResuelta,
): void {
  const x = MARGEN_X + MARCA_MEDIO_ANCHO;
  const puntos =
    direccion === "arriba"
      ? // Apex en el borde (y=0), apuntando hacia fuera del panel.
        [
          { x, y: 0 },
          { x: x - MARCA_MEDIO_ANCHO, y: MARCA_ALTO },
          { x: x + MARCA_MEDIO_ANCHO, y: MARCA_ALTO },
        ]
      : [
          { x, y: alto },
          { x: x - MARCA_MEDIO_ANCHO, y: alto - MARCA_ALTO },
          { x: x + MARCA_MEDIO_ANCHO, y: alto - MARCA_ALTO },
        ];
  const marca = crear(svg, "polygon");
  atributos(marca, {
    class: `dlv-topes-marca dlv-topes-marca--${linea.nivel}`,
    points: puntosATexto(puntos),
  });
  grupo.appendChild(marca);
  const yEtiqueta = direccion === "arriba" ? MARCA_ALTO + 10 : alto - MARCA_ALTO - 4;
  pintarEtiqueta(svg, grupo, MARGEN_X + 2 * MARCA_MEDIO_ANCHO + 2, yEtiqueta, linea.nivel, linea.etiqueta);
}

function pintarCurvaDeLinea(svg: SVGSVGElement, grupo: SVGGElement, puntos: readonly PuntoPixel[], linea: LineaResuelta): void {
  if (puntos.length === 0) return; // la curva no tiene ningún punto en el tramo de tiempo visible: nada que pintar.
  const trazo = crear(svg, "polyline");
  atributos(trazo, {
    class: `dlv-topes-linea dlv-topes-linea--curva dlv-topes-linea--${linea.nivel}`,
    points: puntosATexto(puntos),
  });
  grupo.appendChild(trazo);
  const primero = puntos[0]!;
  pintarEtiqueta(svg, grupo, primero.x + MARGEN_X, primero.y - 3, linea.nivel, linea.etiqueta);
}

function pintarLinea(svg: SVGSVGElement, grupo: SVGGElement, area: GeometriaTopes["area"], linea: LineaResuelta): void {
  if (linea.forma.tipo === "curva") {
    pintarCurvaDeLinea(svg, grupo, linea.forma.puntos, linea);
    return;
  }
  const { posicion } = linea.forma;
  if (posicion.tipo === "dentro") {
    pintarLineaDentro(svg, grupo, area.ancho, posicion.pixelY, linea);
  } else {
    pintarMarcaFueraDeRango(svg, grupo, area.alto, posicion.tipo === "fuera-arriba" ? "arriba" : "abajo", linea);
  }
}

/** El polígono relleno de una banda: `bordeMinimo` de ida y `bordeMaximo` de vuelta, para cerrar la cinta sin cruzarse. */
function pintarBanda(svg: SVGSVGElement, grupo: SVGGElement, banda: BandaResuelta): void {
  if (banda.bordeMinimo.length === 0 || banda.bordeMaximo.length === 0) return;
  const contorno = [...banda.bordeMinimo, ...[...banda.bordeMaximo].reverse()];
  const relleno = crear(svg, "polygon");
  atributos(relleno, {
    class: `dlv-topes-banda dlv-topes-banda--${banda.nivel}`,
    points: puntosATexto(contorno),
  });
  grupo.appendChild(relleno);

  const primeroMin = banda.bordeMinimo[0]!;
  const primeroMax = banda.bordeMaximo[0]!;
  pintarEtiqueta(svg, grupo, MARGEN_X, (primeroMin.y + primeroMax.y) / 2, banda.nivel, banda.etiqueta);
}

/** Pinta toda la `GeometriaTopes` sobre `svg`. Ver la cabecera del módulo para el orden de llamada respecto a `pintarEjes`. */
export function pintarTopes(svg: SVGSVGElement, geometria: GeometriaTopes): void {
  if (geometria.lineas.length === 0 && geometria.bandas.length === 0) return;

  const grupo = crear(svg, "g");
  atributos(grupo, {
    class: "dlv-topes",
    transform: `translate(${geometria.area.x}, ${geometria.area.y})`,
  });
  svg.appendChild(grupo);

  // Las bandas van DEBAJO de las líneas: una banda es una región de fondo, no
  // un trazo, y una línea de aviso/crítico que cayera justo en su borde tiene
  // que seguir viéndose por encima del relleno.
  for (const banda of geometria.bandas) pintarBanda(svg, grupo, banda);
  for (const linea of geometria.lineas) pintarLinea(svg, grupo, geometria.area, linea);
}

export type {
  BandaResuelta,
  BandaTope,
  ConfiguracionTopes,
  FormaResuelta,
  GeometriaTopes,
  LimiteResuelto,
  LineaResuelta,
  LineaTope,
  NivelTope,
  PosicionLinea,
  PuntoCurvaTope,
  PuntoPixel,
} from "./tipos.ts";
export { calcularGeometriaTopes } from "./geometria.ts";
