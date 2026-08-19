/**
 * Ejecuta la regresión visual del renderizador (F5-12, ADR-006) en un
 * navegador de verdad, sin manos y con código de salida.
 *
 *     npm run regresion-visual:edge              # GPU real de la máquina
 *     npm run regresion-visual:edge -- --software  # forzando SwiftShader
 *
 * POR QUÉ ESTE GUION EXISTE
 * =========================
 * `regresion-visual.html` se escribió para abrirse a mano con `npm run dev`, y
 * durante un tiempo esa fue la única manera de ejecutarla — es decir, nadie la
 * ejecutó. Una comprobación que ADR-006 declara OBLIGATORIA y que depende de
 * que alguien se acuerde de abrir una pestaña no es una comprobación, es una
 * intención. Esto la convierte en una orden repetible que devuelve 0 o 1.
 *
 * POR QUÉ NO PLAYWRIGHT NI PUPPETEER
 * ===================================
 * Serían más cómodos y son la respuesta estándar. No se añaden porque en este
 * proyecto una dependencia nueva no la mete un modelo (docs/09 §9.11), y
 * porque `dlv-ui` tiene cero dependencias de ejecución a propósito. Lo que hace
 * falta aquí —cargar una página y leer un veredicto— cabe en lo que ya hay:
 * Edge sin cabeza con `--dump-dom` y el `fetch`/`spawn` de Node. Si algún día
 * la suite necesita interacción de verdad (ratón, varios fotogramas, esperas),
 * eso SÍ pide un controlador de navegador y hay que pedirlo, no instalarlo.
 *
 * POR QUÉ SE LEVANTA VITE Y NO SE ABRE EL FICHERO CON `file://`
 * ==============================================================
 * La página carga `/src/render/regresion-visual/suite-navegador.ts`, una ruta
 * ABSOLUTA que solo resuelve un servidor. Con `file://` el navegador la busca
 * en la raíz del disco y no carga nada — el mismo tropiezo que ya está
 * documentado en `dlv-app/src/dlv_app/main.py` para la aplicación empaquetada.
 * Además hay que compilar TypeScript, que es justo lo que hace el servidor de
 * desarrollo de Vite al vuelo.
 *
 * EL BACKEND NO ES UN DETALLE
 * ============================
 * Edge sin cabeza usa la GPU real del sistema si no se le dice lo contrario;
 * con `--disable-gpu --enable-unsafe-swiftshader` usa SwiftShader (software).
 * Este guion NO fuerza software por omisión, precisamente para que el
 * resultado valga para la máquina del propietario, e imprime siempre quién
 * rasterizó, que es lo que la suite publica en su informe.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ_UI = fileURLToPath(new URL("..", import.meta.url));
const PUERTO_POR_OMISION = 5199;
const RUTA_PAGINA = "/regresion-visual.html";
/** Margen para que Vite compile la primera vez (transformación de TS incluida). */
const ESPERA_SERVIDOR_MS = 60_000;
/** Corte duro del navegador: la suite es síncrona, si tarda más es que se colgó. */
const ESPERA_NAVEGADOR_MS = 120_000;

/**
 * Sitios donde vive `msedge.exe` en Windows. Se prueban en orden y gana el
 * primero que exista; `DLV_EDGE` los precede a todos para que quien tenga Edge
 * en otro sitio (o quiera probar con Chrome, que acepta las mismas opciones)
 * no tenga que tocar este fichero.
 */
const CANDIDATOS_EDGE = [
  process.env.DLV_EDGE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].filter((ruta) => typeof ruta === "string" && ruta.length > 0);

function localizarEdge() {
  for (const ruta of CANDIDATOS_EDGE) {
    if (existsSync(ruta)) return ruta;
  }
  throw new Error(
    "no se encontró msedge.exe. Prueba con la variable de entorno DLV_EDGE=<ruta>. " +
      `Se miró en: ${CANDIDATOS_EDGE.join(", ")}`,
  );
}

function analizarArgumentos(argv) {
  const opciones = { software: false, puerto: PUERTO_POR_OMISION, captura: null, verboso: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--software") opciones.software = true;
    else if (arg === "--verboso") opciones.verboso = true;
    else if (arg === "--puerto") opciones.puerto = Number(argv[(i += 1)]);
    else if (arg === "--captura") opciones.captura = argv[(i += 1)];
    else throw new Error(`opción desconocida: ${arg}`);
  }
  if (!Number.isInteger(opciones.puerto) || opciones.puerto <= 0) {
    throw new Error("--puerto necesita un entero positivo");
  }
  return opciones;
}

/**
 * Levanta el servidor de desarrollo de Vite y devuelve el proceso.
 *
 * `--host 127.0.0.1` explícito: sin él Vite escucha en `localhost`, que en
 * Windows resuelve a `::1` primero, y entonces un sondeo contra `127.0.0.1`
 * falla aunque el servidor esté perfectamente arriba. Fijar la familia de
 * direcciones evita ese falso «no arranca».
 *
 * `--strictPort` para que un puerto ocupado sea un error en vez de un salto
 * silencioso a otro puerto: si Vite se mudara al 5200 y el navegador siguiera
 * yendo al 5199, el guion diría «no medido» por una razón inventada.
 */
function levantarVite(puerto, verboso) {
  const binario = join(RAIZ_UI, "node_modules", "vite", "bin", "vite.js");
  if (!existsSync(binario)) {
    throw new Error(`falta ${binario}: ejecuta \`npm install\` en dlv-ui antes que esto`);
  }
  const hijo = spawn(
    process.execPath,
    [binario, "--host", "127.0.0.1", "--port", String(puerto), "--strictPort"],
    { cwd: RAIZ_UI, stdio: verboso ? "inherit" : "ignore" },
  );
  return hijo;
}

async function esperarServidor(url, limiteMs) {
  const fin = Date.now() + limiteMs;
  let ultimoError = "sin intentos";
  while (Date.now() < fin) {
    try {
      const respuesta = await fetch(url);
      if (respuesta.ok) return;
      ultimoError = `HTTP ${respuesta.status}`;
    } catch (error) {
      ultimoError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((listo) => setTimeout(listo, 250));
  }
  throw new Error(`el servidor de Vite no respondió en ${limiteMs} ms (${ultimoError})`);
}

/**
 * Abre la página en Edge sin cabeza y devuelve el DOM ya renderizado.
 *
 * `--virtual-time-budget` hace que Chromium adelante su reloj virtual hasta que
 * la página queda quieta antes de volcar: sin él, `--dump-dom` puede volcar
 * antes de que los módulos ES terminen de cargarse por HTTP y salir un `<pre>`
 * con «Preparando…», que se leería como un fallo de la suite cuando en realidad
 * es una carrera del guion.
 *
 * `--user-data-dir` a un directorio temporal recién creado: un perfil limpio
 * cada vez descarta que un estado guardado (una lista negra de GPU, una
 * bandera de característica) cambie el resultado entre ejecuciones.
 */
function volcarDom(edge, url, opciones, perfil) {
  const argumentos = [
    "--headless=new",
    `--user-data-dir=${perfil}`,
    "--virtual-time-budget=20000",
    "--disable-extensions",
    "--no-first-run",
    "--no-default-browser-check",
  ];
  if (opciones.software) {
    // `--enable-unsafe-swiftshader` es obligatorio desde Chromium 132: sin él,
    // `--disable-gpu` ya no cae a SwiftShader, deja WebGL sin contexto y la
    // suite diría NO MEDIDO en vez de medir con software.
    argumentos.push("--disable-gpu", "--enable-unsafe-swiftshader");
  }
  if (opciones.captura !== null) argumentos.push(`--screenshot=${opciones.captura}`);
  argumentos.push("--dump-dom", url);

  return new Promise((listo, fallo) => {
    const hijo = spawn(edge, argumentos, { stdio: ["ignore", "pipe", "pipe"] });
    let salida = "";
    let error = "";
    const corte = setTimeout(() => {
      hijo.kill();
      fallo(new Error(`Edge no terminó en ${ESPERA_NAVEGADOR_MS} ms`));
    }, ESPERA_NAVEGADOR_MS);
    hijo.stdout.on("data", (trozo) => (salida += trozo));
    hijo.stderr.on("data", (trozo) => (error += trozo));
    hijo.on("error", (e) => {
      clearTimeout(corte);
      fallo(e);
    });
    hijo.on("close", (codigo) => {
      clearTimeout(corte);
      if (codigo !== 0) fallo(new Error(`Edge salió con código ${codigo}\n${error}`));
      else listo(salida);
    });
  });
}

/**
 * Deshace el escapado que `--dump-dom` aplica al texto de un nodo.
 *
 * Solo hay que deshacer tres entidades porque un nodo de texto solo escapa
 * `&`, `<` y `>`; las comillas dobles del JSON viajan tal cual. `&amp;` se
 * sustituye EL ÚLTIMO: al revés, un `&amp;lt;` literal del JSON se convertiría
 * en `<` y cambiaría el contenido.
 */
function desescapar(texto) {
  return texto.replaceAll("&lt;", "<").replaceAll("&gt;", ">").replaceAll("&amp;", "&");
}

function extraerInforme(dom) {
  const json = /<pre id="resultado-json">([\s\S]*?)<\/pre>/.exec(dom);
  if (json === null || json[1].trim() === "") {
    const texto = /<pre id="resultado">([\s\S]*?)<\/pre>/.exec(dom);
    throw new Error(
      "la página no dejó informe JSON: el módulo de la suite no llegó a ejecutarse.\n" +
        `Texto visible: ${texto === null ? "(tampoco hay <pre id=resultado>)" : desescapar(texto[1]).trim()}`,
    );
  }
  return JSON.parse(desescapar(json[1]));
}

function imprimirInforme(informe, opciones) {
  const backend = informe.backend;
  console.log(`veredicto global   ${informe.veredictoGlobal}`);
  console.log(
    `backend            ${backend === null ? "desconocido" : `${backend.esSoftware ? "SOFTWARE" : "GPU"} — ${backend.renderizador}`}`,
  );
  if (backend !== null) console.log(`webgl              ${backend.version}`);
  console.log("");
  for (const r of informe.resultados) {
    console.log(`[${String(r.veredicto).padEnd(9)}] ${r.nombre}`);
    console.log(`            ${r.detalle}`);
  }
  if (backend !== null && backend.esSoftware) {
    console.log("");
    console.log("AVISO: ha rasterizado un backend por SOFTWARE. Los tres invariantes de");
    console.log("`invariantes.ts` (posición, color, cobertura) no dependen del rasterizador,");
    console.log("así que este resultado vale para lo que la suite comprueba — pero NO");
    console.log("sustituye a una pasada con la GPU real. Repite sin `--software`.");
  }
  if (opciones.captura !== null) console.log(`\ncaptura            ${opciones.captura}`);
}

async function principal() {
  const opciones = analizarArgumentos(process.argv.slice(2));
  const edge = localizarEdge();
  const url = `http://127.0.0.1:${opciones.puerto}${RUTA_PAGINA}`;
  const perfil = await mkdtemp(join(tmpdir(), "dlv-regresion-visual-"));
  const vite = levantarVite(opciones.puerto, opciones.verboso);

  try {
    await esperarServidor(url, ESPERA_SERVIDOR_MS);
    const dom = await volcarDom(edge, url, opciones, perfil);
    const informe = extraerInforme(dom);
    console.log(`navegador          ${edge}`);
    imprimirInforme(informe, opciones);
    // NO MEDIDO también sale distinto de cero: no haber podido mirar no es
    // estar en verde (§8.10), y un guion que devolviera 0 ahí convertiría
    // «no se pudo comprobar» en «comprobado» a ojos de quien lo automatice.
    return informe.veredictoGlobal === "PASA" ? 0 : 1;
  } finally {
    vite.kill();
    await rm(perfil, { recursive: true, force: true }).catch(() => {});
  }
}

principal().then(
  (codigo) => process.exit(codigo),
  (error) => {
    console.error(`NO MEDIDO: ${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  },
);
