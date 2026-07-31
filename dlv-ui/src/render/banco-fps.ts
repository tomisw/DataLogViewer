/**
 * Banco de fps con GPU de verdad (`npm run dev`, luego `/banco-fps.html`).
 *
 * Es la mitad del presupuesto de §2.6 que no se puede medir en Node: lo que
 * cuesta la GPU. La otra mitad —el trabajo de CPU en JavaScript— la mide
 * `renderizador.banco.test.ts` en cada `npm run banco`, sin navegador.
 *
 * Por qué una página y no una prueba automatizada: el número depende de la
 * máquina, y §2.6 fija una máquina de referencia («portátil de 4 núcleos,
 * 16 GB RAM, GPU integrada») que no es la de CI. Automatizar esto exigiría un
 * navegador sin cabeza con GPU, y un navegador sin cabeza mide su propio
 * renderizador por software, no el de la máquina del propietario: daría un
 * número tranquilizador y falso. Mejor una página que el propietario abre y
 * que dice CUMPLE o INCUMPLE con el número delante.
 *
 * Cuando no hay WebG2 el veredicto es **NO MEDIDO**, nunca verde: no haber
 * podido mirar no es estar en verde (§8.10).
 */

import { ajustarLienzo, Renderizador } from "./renderizador.ts";
import type { Color, CubosContinuos, Vista } from "./tipos.ts";

const CANALES = 16;
const CUBOS_POR_CANAL = 2000;
const FOTOGRAMAS_CALENTAMIENTO = 60;
const FOTOGRAMAS_MEDIDOS = 600;
const FPS_MINIMO = 60;
const PEOR_FOTOGRAMA_MS = 20;

/**
 * Serie sintética con la forma de una señal de motor: una portadora lenta
 * (aceleración) con ruido rápido encima. Importa que no sea una recta: un
 * trazo plano toca muchos menos píxeles y daría un fps optimista que no se
 * parece a un log real.
 */
function cubosSinteticos(n: number, semilla: number): CubosContinuos {
  const t = new Float32Array(n);
  const minimo = new Float32Array(n);
  const maximo = new Float32Array(n);
  const primero = new Float32Array(n);
  const ultimo = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = (i / n) * 60;
    const lento = Math.sin((i / n) * Math.PI * 6 + semilla) * 3000 + 4000;
    const rapido = Math.sin(i * 0.7 + semilla) * 400;
    minimo[i] = lento + rapido - 250;
    maximo[i] = lento + rapido + 250;
    primero[i] = lento + rapido - 80;
    ultimo[i] = lento + rapido + 80;
  }
  return { t, tOrigen: 0, minimo, maximo, primero, ultimo, factor: 64 };
}

function colorDeCanal(i: number): Color {
  const h = (i / CANALES) * Math.PI * 2;
  return {
    r: 0.5 + 0.5 * Math.sin(h),
    g: 0.5 + 0.5 * Math.sin(h + 2.1),
    b: 0.5 + 0.5 * Math.sin(h + 4.2),
    a: 0.9,
  };
}

function percentil(valores: readonly number[], p: number): number {
  const ordenados = [...valores].sort((a, b) => a - b);
  return ordenados[Math.min(ordenados.length - 1, Math.floor((p / 100) * ordenados.length))]!;
}

function escribir(texto: string): void {
  const destino = document.querySelector<HTMLDivElement>("#resultado");
  if (destino !== null) destino.textContent = texto;
}

function informar(tiempos: readonly number[], nVertices: number): void {
  const media = tiempos.reduce((a, b) => a + b, 0) / tiempos.length;
  const fps = 1000 / media;
  const p95 = percentil(tiempos, 95);
  const peor = Math.max(...tiempos);
  const cumpleFps = fps >= FPS_MINIMO;
  const cumplePeor = peor <= PEOR_FOTOGRAMA_MS;
  const veredicto = cumpleFps && cumplePeor ? "CUMPLE" : "INCUMPLE";

  escribir(
    [
      `veredicto            ${veredicto}`,
      "",
      `canales              ${CANALES}`,
      `cubos por canal      ${CUBOS_POR_CANAL}`,
      `vértices por fotograma ${nVertices.toLocaleString("es-ES")}`,
      `fotogramas medidos   ${tiempos.length}`,
      "",
      `fps medios           ${fps.toFixed(1)}   (presupuesto ≥ ${FPS_MINIMO})   ${cumpleFps ? "ok" : "ROJO"}`,
      `fotograma medio      ${media.toFixed(2)} ms`,
      `fotograma p95        ${p95.toFixed(2)} ms`,
      `peor fotograma       ${peor.toFixed(2)} ms   (presupuesto ≤ ${PEOR_FOTOGRAMA_MS})   ${cumplePeor ? "ok" : "ROJO"}`,
      "",
      "Nota: el fps que se mide aquí está limitado por la frecuencia de la",
      "pantalla (requestAnimationFrame). Un monitor a 60 Hz no puede dar más de",
      "60 fps aunque sobre GPU; lo que este banco detecta de verdad es cuándo NO",
      "se llega, y el peor fotograma, que es el número que se nota como tirón.",
    ].join("\n"),
  );
}

/**
 * Devuelve `null` —y deja escrito por qué— cuando no hay WebGL2.
 *
 * Función aparte y no un `try` dentro de `arrancar` para que el resto del banco
 * trabaje con un `Renderizador` y no con uno "posiblemente asignado": el
 * análisis de flujo de TypeScript no atraviesa un `try`/`catch` con la misma
 * confianza, y el remedio habitual (un `!`) es justo lo que no se quiere en el
 * único sitio donde el fallo es esperable.
 */
function crearRenderizador(lienzo: HTMLCanvasElement): Renderizador | null {
  try {
    return Renderizador.desdeLienzo(lienzo);
  } catch (error) {
    escribir(
      `NO MEDIDO: ${error instanceof Error ? error.message : String(error)}\n\n` +
        "No haber podido medir no es cumplir el presupuesto.",
    );
    return null;
  }
}

function arrancar(): void {
  const lienzo = document.querySelector<HTMLCanvasElement>("#lienzo");
  if (lienzo === null) {
    escribir("NO MEDIDO: falta el lienzo en la página.");
    return;
  }
  const renderizador = crearRenderizador(lienzo);
  if (renderizador === null) return;
  medir(renderizador, lienzo);
}

/**
 * El bucle de medida. Recibe el renderizador ya construido —y por tanto no
 * nulo— en vez de comprobarlo dentro: el análisis de flujo de TypeScript no
 * conserva el estrechamiento de una variable a través de la función anidada
 * que `requestAnimationFrame` necesita, y la alternativa serían cuatro `!`
 * repartidos por el bucle.
 */
function medir(renderizador: Renderizador, lienzo: HTMLCanvasElement): void {
  renderizador.redimensionar(ajustarLienzo(lienzo, window.devicePixelRatio));
  let nVertices = 0;
  for (let c = 0; c < CANALES; c += 1) {
    const cubos = cubosSinteticos(CUBOS_POR_CANAL, c * 1.37);
    renderizador.subirSerie(`canal-${c}`, cubos, colorDeCanal(c));
    nVertices += CUBOS_POR_CANAL * 4;
  }

  const tiempos: number[] = [];
  let fotograma = 0;
  let anterior = performance.now();

  function paso(): void {
    const ahora = performance.now();
    if (fotograma > FOTOGRAMAS_CALENTAMIENTO) tiempos.push(ahora - anterior);
    anterior = ahora;

    // Pan continuo sobre una ventana de 2 s: el caso que §2.6 llama "pan/zoom",
    // y el que NO debe subir datos a la GPU.
    const desplazamiento = (fotograma % 600) * 0.09;
    const vista: Vista = { t0: desplazamiento, t1: desplazamiento + 2, v0: 0, v1: 8000 };
    renderizador.dibujar(vista);

    fotograma += 1;
    if (tiempos.length < FOTOGRAMAS_MEDIDOS) {
      escribir(`Midiendo… ${tiempos.length}/${FOTOGRAMAS_MEDIDOS} fotogramas`);
      requestAnimationFrame(paso);
      return;
    }
    informar(tiempos, nVertices);
    if (renderizador.estadisticas.subidasDeBufer !== 0) {
      escribir(
        `ROJO: el pan subió ${renderizador.estadisticas.subidasDeBufer} búferes a la GPU.\n` +
          "El presupuesto de §2.6 depende de que un fotograma de pan no suba datos.",
      );
    }
    renderizador.destruir();
  }

  renderizador.reiniciarEstadisticas();
  requestAnimationFrame(paso);
}

arrancar();
