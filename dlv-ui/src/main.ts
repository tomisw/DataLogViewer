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
import { FuenteSintetica } from "./datos/fuente-sintetica.ts";

function contenedorApp(): HTMLDivElement {
  const contenedor = document.querySelector<HTMLDivElement>("#app");
  if (contenedor === null) {
    throw new Error("no se encontró #app en el documento");
  }
  return contenedor;
}

async function iniciar(): Promise<void> {
  const aplicacion = new Aplicacion(contenedorApp(), new FuenteSintetica());
  await aplicacion.abrirLog("autolog-sintetico");
}

void iniciar();
