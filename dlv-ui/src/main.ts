/**
 * Punto de entrada de dlv-ui: monta el `ConmutadorDeVistas` (`app/vistas.ts`)
 * sobre `#app`, con la vista de series (`app/vista-series.ts`, que a su vez
 * envuelve `Aplicacion`) y la de incidencias (`app/vista-incidencias.ts`)
 * registradas. Antes de esta tarea este fichero montaba `Aplicacion`
 * directamente sobre `#app`: la conmutación de vistas es la costura que
 * `docs/02` §2.10 pedía y que ninguna interfaz ofrecía todavía.
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
 * tocar `app/vista-series.ts` ni `app/aplicacion.ts`, que solo conocen la
 * interfaz `FuenteDeDatos`.
 *
 * Sin librerías de gráficos (ADR-006): el lienzo WebGL2 y las capas SVG que
 * antes se limitaban al «hola, dlv-api» de F0-02 ahora los monta
 * `Aplicacion` sobre DOM directo, igual que el resto de `dlv-ui`.
 */

import { ConmutadorDeVistas, type DefinicionVista } from "./app/vistas.ts";
import { crearVistaSeries } from "./app/vista-series.ts";
import { crearVistaIncidencias } from "./app/vista-incidencias.ts";
import { FuenteApi } from "./datos/fuente-api.ts";
import type { FuenteDeDatos } from "./datos/fuente.ts";
import { FuenteSintetica } from "./datos/fuente-sintetica.ts";
import { resolverUrlBaseApi } from "./datos/resolver-api.ts";
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
 *
 * La URL de la API se resuelve con `resolverUrlBaseApi` (F5-06) a partir del
 * host desde el que se cargó ESTA página, no de una constante `127.0.0.1`
 * cableada: ver el docstring de `datos/resolver-api.ts` para por qué eso
 * importa en cuanto `dlv-ui` se sirve para otro equipo de la red y no solo
 * para `dlv-app` o `npm run dev`. `?api_host=` es el escape para cuando
 * `dlv-api` no comparte host con lo que sirve `dlv-ui`.
 */
function elegirFuente(): { fuente: FuenteDeDatos; referencia: string } {
  const parametros = new URLSearchParams(window.location.search);
  const puerto = parametros.get("puerto_api");
  const token = parametros.get("token");
  const log = parametros.get("log");
  if (puerto !== null && token !== null && log !== null) {
    const apiHost = parametros.get("api_host");
    return {
      fuente: new FuenteApi({
        urlBase: resolverUrlBaseApi(window.location.hostname, puerto, apiHost),
        tokenSesion: token,
      }),
      referencia: log,
    };
  }
  return { fuente: new FuenteSintetica(), referencia: "autolog-sintetico" };
}

/**
 * Con qué vistas arranca la aplicación, en el orden en que aparecen sus
 * pestañas. Añadir una vista nueva (docs/02 §2.10, `app/vistas.ts`) es
 * añadir una entrada aquí -nada más de este fichero necesita cambiar.
 */
function crearVistas(fuente: FuenteDeDatos, referencia: string): readonly DefinicionVista[] {
  return [crearVistaSeries(fuente, referencia), crearVistaIncidencias(document)];
}

/**
 * Ya no es `async`: antes esperaba `aplicacion.abrirLog(referencia)` para
 * poder atrapar su fallo aquí mismo. Ahora `abrirLog` la lanza
 * `crearVistaSeries#montar` -síncrono, por contrato de `DefinicionVista`- y
 * es ese módulo quien atrapa el fallo (ver su cabecera). Nada queda por
 * esperar en este punto de entrada.
 */
function iniciar(): void {
  inicializarTema();
  const { fuente, referencia } = elegirFuente();
  new ConmutadorDeVistas(contenedorApp(), document, crearVistas(fuente, referencia));
}

iniciar();
