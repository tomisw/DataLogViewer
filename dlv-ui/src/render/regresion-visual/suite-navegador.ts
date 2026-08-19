/**
 * Suite de regresión visual del renderizador — la parte que necesita GPU.
 * Se abre con `npm run dev`, en `/regresion-visual.html`, o sin manos con
 * `npm run regresion-visual:edge` (ver `tools/regresion-visual-edge.mjs`).
 *
 * QUÉ HACE ESTE FICHERO Y QUÉ NO
 * ===============================
 * `invariantes.ts` (comparadores) y `escenas.ts` (datos sintéticos + oráculo
 * de posición) son lógica pura y se prueban sin navegador, en cada
 * `npm test`. Este fichero es la otra mitad: crea un `Renderizador` de
 * verdad sobre un `<canvas>` de verdad, sube las escenas, dibuja, lee los
 * píxeles con `gl.readPixels` y les aplica esos comparadores.
 *
 * PRIMERA EJECUCIÓN REAL — QUÉ SE MIDIÓ Y DÓNDE
 * ==============================================
 * Esta suite se escribió en un entorno sin navegador, sin WebGL2 y sin
 * `node_modules`, así que durante un tiempo fue código plausible y no código
 * ejecutado. **Ya no.** Primera ejecución real, 2026-08-19, en la máquina del
 * propietario:
 *
 *   - Navegador  Microsoft Edge 151.0.4129.59, `--headless=new`, Windows 11
 *   - Backend    ANGLE sobre Direct3D 11 con la **GPU real** de la máquina
 *                (Intel UHD Graphics 620). No SwiftShader: el modo sin cabeza
 *                de Edge, si NO se le pasa `--disable-gpu`, encuentra la GPU
 *                del sistema y la usa.
 *   - Resultado  veredicto global PASA — las cuatro comprobaciones en verde
 *                (posición y color de dos series, y color de tema en los tres
 *                temas).
 *
 * También se ejecutó forzando el rasterizador por software
 * (`--disable-gpu --enable-unsafe-swiftshader`, backend SwiftShader/Subzero) y
 * el veredicto es el mismo. Que coincidan es la evidencia de que los tres
 * invariantes de `invariantes.ts` no dependen del rasterizador — que es
 * exactamente lo que aquel fichero razona al descartar la comparación de
 * imágenes—, pero **el resultado que vale como garantía es el de la GPU
 * real**; el de SwiftShader solo dice que la geometría y los uniformes están
 * bien, no cómo rasteriza el hardware del propietario.
 *
 * Por eso esta suite AVERIGUA Y PUBLICA su backend (`describirBackend`): un
 * PASA sin saber quién rasterizó es media respuesta, y en una máquina de CI
 * sin GPU sería un PASA de software presentado como si fuera de hardware.
 *
 * QUE PASE A LA PRIMERA NO ES PRUEBA DE QUE COMPRUEBE ALGO
 * =========================================================
 * Una suite recién escrita que sale verde puede estar viendo el fallo... o
 * puede no estar mirando. Para distinguirlo se inyectaron tres regresiones
 * REALES en el renderizador, una a una, y se comprobó que la suite las caza y
 * que el guion devuelve 1 (mismo día, misma GPU):
 *
 *   1. Eje Y invertido (`escalaY` negativo en `escala.ts::transformacion`):
 *      FALLA las cuatro comprobaciones; la de cobertura además cuenta 0
 *      píxeles no-fondo, porque la escena entera se va fuera del lienzo.
 *   2. Eje X desplazado 10 px (`+0,05` en `despX`): FALLA la comprobación de
 *      posición. Ver más abajo, que este caso enseñó algo.
 *   3. Canales R y B intercambiados al pasar el color a la GPU
 *      (`renderizador.ts::dibujar`): FALLA las cuatro.
 *
 * Las tres inyecciones se revirtieron; están aquí escritas, y no dejadas como
 * prueba automática, porque exigen editar el renderizador y no hay forma de
 * hacerlo desde fuera sin abrirle una puerta que ADR-006 quiere cerrada.
 *
 * LÍMITE DE SENSIBILIDAD QUE DESTAPÓ LA INYECCIÓN 2
 * ==================================================
 * Con el eje X desplazado 10 px, la comprobación de posición falló pero las
 * tres de color de tema siguieron en verde. No es un defecto: es geometría, y
 * conviene tenerlo escrito para no confundirse al leer un fallo parcial.
 *
 *   - Las comprobaciones de tema dibujan un segmento HORIZONTAL a través del
 *     centro. Un desplazamiento en X mueve ese segmento a lo largo de sí
 *     mismo, así que el píxel central sigue estando encima. Son comprobaciones
 *     de COLOR y no detectan desplazamientos en X por construcción; un
 *     desplazamiento en Y sí las rompería. Quien busque posición mira la
 *     comprobación 1, que es la que existe para eso.
 *   - Dentro de la comprobación 1, un desplazamiento en X se nota tanto más
 *     cuanto más inclinada sea la serie: mueve la serie `d·m/√(1+m²)` píxeles
 *     respecto al punto esperado, con `m` la pendiente en píxeles. Para
 *     `PUNTOS_RECTA` (m = 0,75) los 10 px dan 6 px de desvío y se salen de
 *     `RADIO_BUSQUEDA_PX`; para `PUNTOS_PARALELA` (m = 0,375) dan 3,5 px y
 *     cuatro de sus cinco puntos aún caían dentro de la caja de búsqueda. Que
 *     la escena tenga las DOS series, y que la comprobación exija todos los
 *     puntos de ambas, es lo que hace que el conjunto sí lo cace.
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
 * Quién rasterizó de verdad este fotograma.
 *
 * No es decoración del informe: es la diferencia entre «la serie sale donde
 * tiene que salir en la GPU del propietario» y «sale donde tiene que salir en
 * un rasterizador por software que nadie usa para mirar logs». Los tres
 * invariantes de `invariantes.ts` están elegidos para ser indiferentes al
 * rasterizador, así que un PASA con software SIGUE valiendo para lo que la
 * suite comprueba (posición, color, cobertura); lo que no vale es publicarlo
 * sin decir cuál fue, porque quien lea «PASA» va a suponer hardware.
 */
interface Backend {
  /** Cadena cruda de `UNMASKED_RENDERER_WEBGL`, o de `RENDERER` si no hay extensión. */
  readonly renderizador: string;
  readonly version: string;
  /** `true` si la cadena delata un rasterizador por software conocido. */
  readonly esSoftware: boolean;
}

/**
 * Marcas de los rasterizadores por software que se pueden encontrar aquí.
 * `SwiftShader` es el que trae Chromium/Edge; `llvmpipe`/`softpipe` son los de
 * Mesa, por si la suite acaba corriendo en una VM Linux de CI. La lista es
 * conservadora a propósito: ante una cadena desconocida se dice «hardware»
 * pero se imprime la cadena entera, así que un caso nuevo se ve a simple vista
 * en vez de esconderse tras un booleano.
 */
const MARCAS_DE_SOFTWARE = ["swiftshader", "llvmpipe", "softpipe", "software rasterizer"];

function describirBackend(lienzo: HTMLCanvasElement): Backend {
  const gl = lienzo.getContext("webgl2");
  if (gl === null) {
    return { renderizador: "desconocido", version: "desconocida", esSoftware: false };
  }
  // `WEBGL_debug_renderer_info` es la única forma de saber la GPU real: el
  // `RENDERER` estándar devuelve siempre "WebKit WebGL" por privacidad, que no
  // distingue una Intel integrada de SwiftShader.
  const ext = gl.getExtension("WEBGL_debug_renderer_info");
  const crudo =
    ext !== null
      ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL))
      : String(gl.getParameter(gl.RENDERER));
  const enMinusculas = crudo.toLowerCase();
  return {
    renderizador: crudo,
    version: String(gl.getParameter(gl.VERSION)),
    esSoftware: MARCAS_DE_SOFTWARE.some((marca) => enMinusculas.includes(marca)),
  };
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

function escribirResultados(
  resultados: readonly ResultadoComprobacion[],
  backend: Backend | null,
): void {
  const hayFallo = resultados.some((r) => r.veredicto === "FALLA");
  const hayNoMedido = resultados.some((r) => r.veredicto === "NO MEDIDO");
  const veredictoGlobal: Veredicto = hayFallo ? "FALLA" : hayNoMedido ? "NO MEDIDO" : "PASA";

  const destino = document.querySelector<HTMLPreElement>("#resultado");
  if (destino !== null) {
    const lineas = [
      `veredicto global: ${veredictoGlobal}`,
      backend === null
        ? "backend:          desconocido (no se llegó a crear el contexto)"
        : `backend:          ${backend.esSoftware ? "SOFTWARE" : "GPU"} — ${backend.renderizador}`,
      ...(backend !== null && backend.esSoftware
        ? [
            "",
            "AVISO: ha rasterizado un backend por SOFTWARE. Lo que comprueba esta",
            "suite (posición, color y cobertura) es indiferente al rasterizador, así",
            "que el PASA es válido para eso — pero NO dice nada de cómo se ve en la",
            "GPU real del propietario. Para eso, ejecútala sin `--disable-gpu`.",
          ]
        : []),
      "",
      ...resultados.map((r) => `[${r.veredicto.padEnd(9)}] ${r.nombre}\n            ${r.detalle}`),
    ];
    destino.textContent = lineas.join("\n");
  }

  const informe = { veredictoGlobal, backend, resultados };

  // El mismo informe, en JSON y dentro del DOM.
  //
  // POR QUÉ EN EL DOM Y NO SOLO EN UN GLOBAL DE `window`
  // ====================================================
  // `tools/regresion-visual-edge.mjs` conduce Edge sin cabeza con `--dump-dom`,
  // que vuelca el árbol del documento y NADA del estado de JavaScript. Un
  // veredicto que solo viva en `window.__resultadoRegresionVisual` es invisible
  // para ese modo, y leerlo exigiría un protocolo de depuración remota o una
  // dependencia de control de navegador (Playwright/Puppeteer), que este
  // proyecto no añade sin permiso. Un `<pre>` con JSON lo hace legible con lo
  // que ya hay. El global se mantiene para quien abra la página a mano y quiera
  // hurgar desde la consola.
  const json = document.querySelector<HTMLPreElement>("#resultado-json");
  if (json !== null) json.textContent = JSON.stringify(informe);
  (window as unknown as { __resultadoRegresionVisual: unknown }).__resultadoRegresionVisual =
    informe;
}

function arrancar(): void {
  const lienzo = document.querySelector<HTMLCanvasElement>("#lienzo");
  if (lienzo === null) {
    escribirResultados(
      [
        {
          nombre: "arranque",
          veredicto: "NO MEDIDO",
          detalle: "falta el <canvas id=lienzo> en la página",
        },
      ],
      null,
    );
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
    escribirResultados(
      [
        {
          nombre: "creación del renderizador",
          veredicto: "NO MEDIDO",
          detalle:
            (error instanceof Error ? error.message : String(error)) +
            " — ninguna de las comprobaciones de F5-12 se pudo ejecutar en este navegador.",
        },
      ],
      null,
    );
    return;
  }

  // Después de `desdeLienzo` y no antes: el backend se pregunta al contexto ya
  // creado, y crearlo aquí con otros atributos podría devolver otro distinto.
  const backend = describirBackend(lienzo);

  renderizador.redimensionar(VIEWPORT_PRUEBA);

  const resultados: ResultadoComprobacion[] = [];
  resultados.push(comprobarPosicionYColor(renderizador, lienzo));
  for (const tema of TEMAS_A_COMPROBAR) {
    resultados.push(comprobarColorPorTema(renderizador, lienzo, tema));
  }

  renderizador.destruir();
  escribirResultados(resultados, backend);
}

arrancar();
