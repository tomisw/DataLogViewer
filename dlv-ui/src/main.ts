/**
 * Punto de entrada de dlv-ui: monta `Aplicacion` (`app/aplicacion.ts`) sobre
 * `#app` con `FuenteSintetica` (`datos/fuente-sintetica.ts`) como fuente de
 * datos.
 *
 * POR QUÉ `FuenteSintetica` Y NO `FuenteApi` AQUÍ
 * =================================================
 * `FuenteApi` está deliberadamente esbozada y sin terminar: `dlv-api` todavía
 * no tiene sesión de log abierto ni endpoint de cubos (ver la cabecera de
 * `datos/fuente-api.ts`). `FuenteSintetica` es la que permite tener una
 * aplicación que se abre y se navega HOY. El día que el endpoint de cubos
 * exista, cablear la real es sustituir esta única línea —
 * `new FuenteSintetica()` por `new FuenteApi({urlBase, tokenSesion})`, leídos
 * de `?puerto_api=` y de lo que `dlv-app` pase por la URL (ADR-007) — sin
 * tocar `app/aplicacion.ts`, que solo conoce la interfaz `FuenteDeDatos`.
 *
 * Sin librerías de gráficos (ADR-006): el lienzo WebGL2 y las capas SVG que
 * antes se limitaban al «hola, dlv-api» de F0-02 ahora los monta
 * `Aplicacion` sobre DOM directo, igual que el resto de `dlv-ui`.
 */

import { Aplicacion } from "./app/aplicacion.ts";
import { FuenteApi } from "./datos/fuente-api.ts";
import type { FuenteDeDatos } from "./datos/fuente.ts";
import { FuenteSintetica } from "./datos/fuente-sintetica.ts";
import { inicializarTema } from "./tema/tema.ts";

function contenedorApp(): HTMLDivElement {
  const contenedor = document.querySelector<HTMLDivElement>("#app");
  if (contenedor === null) {
    throw new Error("no se encontró #app en el documento");
  }
  return contenedor;
}

/**
 * Con qué fuente y qué log arrancar, según lo que traiga la URL.
 *
 * `dlv-app` abre la ventana con `?puerto_api=<puerto>&token=<token>&log=<ruta>`
 * una vez `dlv-api` está escuchando en su puerto efímero (ADR-007). Si esos
 * parámetros están, se habla con el backend de verdad; si no —`npm run dev` a
 * pelo, sin contenedor— se cae a la fuente sintética.
 *
 * El repliegue es a datos sintéticos y NO a un error a propósito: abrir
 * `npm run dev` y ver la aplicación funcionando con datos de mentira es la
 * forma de trabajar en la interfaz sin levantar Python. Pero la fuente dice su
 * nombre («sintética» / «dlv-api») y `Aplicacion` lo enseña: un repliegue
 * silencioso a datos falsos sería justo el tipo de cosa que hace perder una
 * tarde depurando por qué «los datos no coinciden con el log».
 */
function elegirFuente(): { fuente: FuenteDeDatos; referencia: string } {
  const parametros = new URLSearchParams(window.location.search);
  const puerto = parametros.get("puerto_api");
  const token = parametros.get("token");
  const log = parametros.get("log");
  if (puerto !== null && token !== null && log !== null) {
    return {
      fuente: new FuenteApi({ urlBase: `http://127.0.0.1:${puerto}`, tokenSesion: token }),
      referencia: log,
    };
  }
  return { fuente: new FuenteSintetica(), referencia: "autolog-sintetico" };
}

async function iniciar(): Promise<void> {
  inicializarTema();
  const { fuente, referencia } = elegirFuente();
  const aplicacion = new Aplicacion(contenedorApp(), fuente);
  try {
    await aplicacion.abrirLog(referencia);
  } catch (error) {
    // Un fallo al abrir no puede dejar la ventana en blanco sin explicación:
    // es el síntoma que no se puede diagnosticar. E1.7 pide decir qué pasó.
    contenedorApp().textContent =
      `No se pudo abrir «${referencia}» con la fuente ${fuente.nombre}: ` +
      (error instanceof Error ? error.message : String(error));
  }
}

void iniciar();
