/**
 * Suite de regresión visual del renderizador — la parte que necesita GPU.
 * Se abre con `npm run dev`, en `/regresion-visual.html`.
 *
 * QUÉ HACE ESTE FICHERO Y QUÉ NO
 * ===============================
 * `invariantes.ts` (comparadores) y `escenas.ts` (datos sintéticos + oráculo
 * de posición) son lógica pura y se prueban sin navegador, en cada
 * `npm test`. Este fichero es la otra mitad: crea un `Renderizador` de
 * verdad sobre un `<canvas>` de verdad, sube las escenas, dibuja, lee los
 * píxeles con `gl.readPixels` y les aplica esos comparadores. Es la única
 * pieza de F5-12 que no se pudo EJECUTAR en el entorno donde se escribió
 * (sin navegador con WebGL2 ni `node_modules`) — queda dicho en el informe
 * de la tarea y aquí, en el propio código: quien la abra en un navegador de
 * verdad es quien la ejecuta por primera vez.
 *
 * QUÉ PASA SIN WEBGL2 (no puede quedarse en verde en silencio)
 * ================================================================
 * Igual que `banco-fps.ts` (F1-23): si no hay WebGL2, el veredicto es
 * NO MEDIDO, con la lista de comprobaciones que no se hicieron, nunca un
 * lienzo vacío que parezca "todo bien". Un entorno sin GPU (una VM de CI sin
 * aceleración, por ejemplo) que reportara verde estaría dando una garantía
 * que ADR-006 pide precisamente porque no existe sin mirar de verdad.
 *
 * NO SE COMPARA CONTRA UNA IMAGEN DE REFERENCIA GUARDADA
 * ==========================================================
 * No hay ningún PNG en el repositorio que esta suite compare por diferencia
 * de píxeles. El porqué está en la cabecera de `invariantes.ts`: una imagen
 * de referencia arrastra el ruido de rasterización de la GPU en la que se
 * generó, y comparar contra ella puede fallar con el renderizador perfecto o
 * pasar con el renderizador roto (dos regresiones que se cancelan por
 * casualidad de píxel). Aquí el oráculo es la geometría de la escena
 * (`escenas.ts`), no una captura anterior.
 */

import {
  colorEnPixel,
  contarPixelesNoFondo,
  hayColorCerca,
  type BufferDePixeles,
  type ColorRGB,
} from "./invariantes.ts";
import {
  colorARgb255,
  colorDeSerieParaTema,
  cubosDeControl,
  FONDO_LIENZO,
  longitudPixelesDeSerie,
  pixelEsperado,
  puntoDeFondoSeguro,
  puntoDeFondoSeguroOpuesto,
  PUNTOS_PARALELA,
  PUNTOS_RECTA,
  VISTA_PRUEBA,
  VIEWPORT_PRUEBA,
} from "./escenas.ts";
import { Renderizador } from "../renderizador.ts";
import type { NombreTema } from "../../tema/tema.ts";
import type { Color } from "../tipos.ts";

const COLOR_RECTA: Color = { r: 0.25, g: 0.55, b: 1, a: 1 };
const COLOR_PARALELA: Color = { r: 1, g: 0.45, b: 0.2, a: 1 };
const TEMAS_A_COMPROBAR: readonly NombreTema[] = ["oscuro", "claro", "altContraste"];

type Veredicto = "PASA" | "FALLA" | "NO MEDIDO";

interface ResultadoComprobacion {
  readonly nombre: string;
  readonly veredicto: Veredicto;
  readonly detalle: string;
}

/**
 * Contexto WebGL2 real, el mismo que usa el `Renderizador` internamente.
 *
 * `Renderizador.desdeLienzo` guarda su contexto en un campo privado — a
 * propósito, ADR-006 pide una superficie de API pequeña (`contexto.ts`) y
 * `readPixels` no forma parte de lo que el renderizador necesita para
 * dibujar. Esta suite sí necesita `readPixels` para leer el resultado, así
 * que pide el MISMO contexto por su cuenta: `canvas.getContext('webgl2')`
 * devuelve, por especificación, el contexto ya creado en la primera llamada
 * si los atributos coinciden en ser compatibles, no uno nuevo. No hace falta
 * tocar `contexto.ts` ni ensanchar la superficie que ADR-006 pide mantener
 * pequeña.
 */
function leerPixeles(lienzo: HTMLCanvasElement, ancho: number, alto: number): BufferDePixeles {
  const gl = lienzo.getContext("webgl2");
  if (gl === null) throw new Error("no se pudo recuperar el contexto WebGL2 ya creado");
  const datos = new Uint8Array(ancho * alto * 4);
  gl.readPixels(0, 0, ancho, alto, gl.RGBA, gl.UNSIGNED_BYTE, datos);
  return { datos, ancho, alto };
}

function limpiarSeries(renderizador: Renderizador): void {
  for (const serie of renderizador.series) renderizador.quitarSerie(serie.id);
}

/**
 * Comprobación 1 — posición y color de dos series simultáneas, más el fondo.
 *
 * Cubre los tres fallos de verdad que la tarea pide distinguir del ruido de
 * GPU: un eje desplazado (el punto no aparece donde el oráculo dice), una
 * serie que no se dibuja (ninguno de sus puntos aparece) y un color de fondo
 * equivocado (las esquinas seguras dejan de ser negras).
 */
function comprobarPosicionYColor(
  renderizador: Renderizador,
  lienzo: HTMLCanvasElement,
): ResultadoComprobacion {
  limpiarSeries(renderizador);
  renderizador.subirSerie("recta", cubosDeControl(PUNTOS_RECTA, 0), COLOR_RECTA);
  renderizador.subirSerie("paralela", cubosDeControl(PUNTOS_PARALELA, 0), COLOR_PARALELA);
  renderizador.dibujar(VISTA_PRUEBA);
  const buffer = leerPixeles(lienzo, VIEWPORT_PRUEBA.ancho, VIEWPORT_PRUEBA.alto);

  const fallos: string[] = [];
  const colorRecta255 = colorARgb255(COLOR_RECTA);
  const colorParalela255 = colorARgb255(COLOR_PARALELA);

  for (const p of PUNTOS_RECTA) {
    const px = pixelEsperado(p.tAbs, p.valor, VISTA_PRUEBA, VIEWPORT_PRUEBA);
    if (!hayColorCerca(buffer, px.columna, px.filaDesdeAbajo, colorRecta255)) {
      fallos.push(`'recta' no aparece cerca de su punto '${p.nombre}' (col=${px.columna}, fila=${px.filaDesdeAbajo})`);
    }
  }
  for (const p of PUNTOS_PARALELA) {
    const px = pixelEsperado(p.tAbs, p.valor, VISTA_PRUEBA, VIEWPORT_PRUEBA);
    if (!hayColorCerca(buffer, px.columna, px.filaDesdeAbajo, colorParalela255)) {
      fallos.push(`'paralela' no aparece cerca de su punto '${p.nombre}' (col=${px.columna}, fila=${px.filaDesdeAbajo})`);
    }
  }

  for (const [nombreEsquina, esquina] of [
    ["inferior izquierda", puntoDeFondoSeguro()],
    ["superior derecha", puntoDeFondoSeguroOpuesto(VIEWPORT_PRUEBA)],
  ] as const) {
    const color = colorEnPixel(buffer, esquina.columna, esquina.filaDesdeAbajo);
    if (color === null || !coloresIguales(color, FONDO_LIENZO)) {
      fallos.push(
        `esquina ${nombreEsquina} no es el fondo esperado (obtenido ${JSON.stringify(color)})`,
      );
    }
  }

  const esperado =
    longitudPixelesDeSerie(PUNTOS_RECTA, VISTA_PRUEBA, VIEWPORT_PRUEBA) +
    longitudPixelesDeSerie(PUNTOS_PARALELA, VISTA_PRUEBA, VIEWPORT_PRUEBA);
  const cuenta = contarPixelesNoFondo(buffer, FONDO_LIENZO);
  // Banda deliberadamente ancha (ver `longitudPixelesDeSerie`): esto es la
  // red de seguridad más basta, para "no se dibujó nada" o "se pintó de más",
  // no para el grosor exacto del trazo.
  const minimo = esperado * 0.3;
  const maximo = esperado * 3;
  if (cuenta < minimo || cuenta > maximo) {
    fallos.push(
      `cobertura fuera de rango: ${cuenta} píxeles no-fondo, esperados entre ${minimo.toFixed(0)} y ${maximo.toFixed(0)} (estimación central ${esperado})`,
    );
  }

  return fallos.length === 0
    ? { nombre: "posición y color (dos series)", veredicto: "PASA", detalle: "ok" }
    : { nombre: "posición y color (dos series)", veredicto: "FALLA", detalle: fallos.join("; ") };
}

/**
 * Comprobación 2 — color por tema, una vez por tema (F5-12 pide explícitamente
 * los dos temas de `tema.ts`; se añade alto contraste porque es el tercero
 * que ya existe y una regresión ahí es tan real como en los otros dos).
 *
 * Un segmento corto y horizontal a través del centro exacto de la vista, no
 * un único vértice: un `LINE_STRIP` con un solo punto (dos vértices
 * idénticos) es un segmento de longitud cero, y la especificación de OpenGL
 * deja sin definir si un segmento así llega a rasterizar algún píxel. Con
 * dos puntos distintos alrededor del centro hay un tramo de verdad que lo
 * atraviesa.
 */
function comprobarColorPorTema(
  renderizador: Renderizador,
  lienzo: HTMLCanvasElement,
  tema: NombreTema,
): ResultadoComprobacion {
  limpiarSeries(renderizador);
  const centroT = (VISTA_PRUEBA.t0 + VISTA_PRUEBA.t1) / 2;
  const centroV = (VISTA_PRUEBA.v0 + VISTA_PRUEBA.v1) / 2;
  const puntos = [
    { nombre: "antes-centro", tAbs: centroT - 1, valor: centroV },
    { nombre: "centro", tAbs: centroT, valor: centroV },
    { nombre: "despues-centro", tAbs: centroT + 1, valor: centroV },
  ];
  const color = colorDeSerieParaTema(tema, 0);
  renderizador.subirSerie("tema", cubosDeControl(puntos, 0), color);
  renderizador.dibujar(VISTA_PRUEBA);
  const buffer = leerPixeles(lienzo, VIEWPORT_PRUEBA.ancho, VIEWPORT_PRUEBA.alto);

  const px = pixelEsperado(centroT, centroV, VISTA_PRUEBA, VIEWPORT_PRUEBA);
  const esperado255 = colorARgb255(color);
  const pasa = hayColorCerca(buffer, px.columna, px.filaDesdeAbajo, esperado255);

  return {
    nombre: `color de tema — ${tema}`,
    veredicto: pasa ? "PASA" : "FALLA",
    detalle: pasa
      ? `color esperado ${JSON.stringify(esperado255)} encontrado cerca de (${px.columna}, ${px.filaDesdeAbajo})`
      : `color esperado ${JSON.stringify(esperado255)} NO encontrado cerca de (${px.columna}, ${px.filaDesdeAbajo})`,
  };
}

function coloresIguales(a: ColorRGB, b: ColorRGB): boolean {
  // Tolerancia mínima (no 0): el fondo es un `clear` plano sin blending, así
  // que en teoría es exacto, pero se deja un margen de 2 unidades por si el
  // navegador aplica alguna gestión de color de salida incluso sobre negro
  // puro. Deliberadamente más estricto que `TOLERANCIA_CANAL_COLOR`: un fondo
  // que no sea negro exacto (±2) es sospechoso de verdad, no ruido esperable.
  return Math.abs(a.r - b.r) <= 2 && Math.abs(a.g - b.g) <= 2 && Math.abs(a.b - b.b) <= 2;
}

function escribirResultados(resultados: readonly ResultadoComprobacion[]): void {
  const destino = document.querySelector<HTMLPreElement>("#resultado");
  if (destino === null) return;
  const hayFallo = resultados.some((r) => r.veredicto === "FALLA");
  const hayNoMedido = resultados.some((r) => r.veredicto === "NO MEDIDO");
  const veredictoGlobal = hayFallo ? "FALLA" : hayNoMedido ? "NO MEDIDO" : "PASA";
  const lineas = [
    `veredicto global: ${veredictoGlobal}`,
    "",
    ...resultados.map((r) => `[${r.veredicto.padEnd(9)}] ${r.nombre}\n            ${r.detalle}`),
  ];
  destino.textContent = lineas.join("\n");
  // También en un global explícito: útil para que, en el futuro, un
  // controlador de navegador (Playwright — ver la propuesta en el informe de
  // la tarea, NO añadida como dependencia) lea el veredicto sin tener que
  // interpretar el DOM.
  (window as unknown as { __resultadoRegresionVisual: unknown }).__resultadoRegresionVisual = {
    veredictoGlobal,
    resultados,
  };
}

function arrancar(): void {
  const lienzo = document.querySelector<HTMLCanvasElement>("#lienzo");
  if (lienzo === null) {
    escribirResultados([
      { nombre: "arranque", veredicto: "NO MEDIDO", detalle: "falta el <canvas id=lienzo> en la página" },
    ]);
    return;
  }

  // Tamaño de lienzo FIJO y NO vía `ajustarLienzo` de `renderizador.ts` (que
  // depende de la caja CSS y de `devicePixelRatio`, variables de la máquina
  // que abre la página): esta suite necesita que el tamaño en píxeles de
  // dispositivo sea EXACTAMENTE `VIEWPORT_PRUEBA`, porque el oráculo de
  // `escenas.ts::pixelEsperado` lo usa en la cuenta. Un lienzo redimensionado
  // por DPR haría que el mismo caso fallara o pasara según el monitor de
  // quien lo abre, justo el tipo de falso positivo que esta suite existe
  // para no tener.
  lienzo.width = VIEWPORT_PRUEBA.ancho;
  lienzo.height = VIEWPORT_PRUEBA.alto;

  let renderizador: Renderizador;
  try {
    renderizador = Renderizador.desdeLienzo(lienzo);
  } catch (error) {
    escribirResultados([
      {
        nombre: "creación del renderizador",
        veredicto: "NO MEDIDO",
        detalle:
          (error instanceof Error ? error.message : String(error)) +
          " — ninguna de las comprobaciones de F5-12 se pudo ejecutar en este navegador.",
      },
    ]);
    return;
  }

  renderizador.redimensionar(VIEWPORT_PRUEBA);

  const resultados: ResultadoComprobacion[] = [];
  resultados.push(comprobarPosicionYColor(renderizador, lienzo));
  for (const tema of TEMAS_A_COMPROBAR) {
    resultados.push(comprobarColorPorTema(renderizador, lienzo, tema));
  }

  renderizador.destruir();
  escribirResultados(resultados);
}

arrancar();
