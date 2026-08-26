/**
 * `crearVistaSeries`: adapta `Aplicacion` -la vista de series, la única que
 * existía antes de esta tarea- a `DefinicionVista` (`app/vistas.ts`).
 *
 * Es deliberadamente delgado: no cambia nada de cómo funciona `Aplicacion`
 * -sigue siendo el mismo ensamblado con el mismo comportamiento, la vista
 * "de siempre"- solo describe cómo montarla y desmontarla dentro de un
 * `<div>` que el conmutador ya insertó, y cómo aplicar un salto pendiente
 * (`opciones.instanteS`) en cuanto el log esté abierto.
 *
 * `desmontar()` es literalmente `aplicacion.destruir()`: ya liberaba los
 * contextos WebGL2 de cada panel (`#reconstruir(null)`) y, desde esta misma
 * tarea, también los oyentes que puso sobre `entorno.ventana`. No hacía
 * falta nada más nuevo aquí -la costura ya estaba donde tenía que estar.
 *
 * EL FALLO AL ABRIR TIENE QUE SEGUIR VIÉNDOSE (E1.7)
 * =====================================================
 * `main.ts` escribía antes el error de `abrirLog` directamente en `#app` con
 * un `try`/`catch` alrededor del `await`. Aquí no hay nada que esperar desde
 * fuera -`montar` es síncrono, por contrato de `DefinicionVista`- así que el
 * mismo aviso se escribe en `contenedor` desde el propio `.catch`: perderlo
 * habría dejado una ventana en blanco sin explicación al fallar, justo el
 * síntoma que E1.7 prohíbe.
 */

import { Aplicacion, ENTORNO_REAL, type EntornoApp } from "./aplicacion.ts";
import type { FuenteDeDatos } from "../datos/fuente.ts";
import type { DefinicionVista, OpcionesActivacion, VistaMontada } from "./vistas.ts";

export const ID_VISTA_SERIES = "series";

export function crearVistaSeries(
  fuente: FuenteDeDatos,
  referenciaInicial: string,
  entorno: EntornoApp = ENTORNO_REAL,
): DefinicionVista {
  return {
    id: ID_VISTA_SERIES,
    etiqueta: "Series",

    montar(contenedor: HTMLElement, _contexto, opciones: OpcionesActivacion): VistaMontada {
      const aplicacion = new Aplicacion(contenedor, fuente, entorno);

      // `abrirLog` es async y `montar` no puede esperarla (el conmutador no
      // sabe de promesas): el salto pendiente se aplica en cuanto resuelve.
      // `desmontada` evita aplicar un salto -o cualquier otro efecto- sobre
      // una `Aplicacion` a la que ya se le pidió `destruir()` porque el
      // usuario volvió a cambiar de vista antes de que el log terminara de
      // abrirse; `irAInstante` sería un no-op inofensivo de todas formas
      // (`#nav` ya es `null`), pero comprobarlo aquí deja explícita la razón
      // en vez de confiar en ese detalle interno.
      let desmontada = false;
      aplicacion
        .abrirLog(referenciaInicial)
        .then(() => {
          if (!desmontada && opciones.instanteS !== undefined) {
            aplicacion.irAInstante(opciones.instanteS);
          }
        })
        .catch((error: unknown) => {
          console.error("dlv-ui: fallo al abrir el log en la vista de series", error);
          if (desmontada) return; // ya se fue de esta vista; escribir aquí no lo vería nadie
          contenedor.textContent =
            `No se pudo abrir «${referenciaInicial}» con la fuente ${fuente.nombre}: ` +
            (error instanceof Error ? error.message : String(error));
        });

      return {
        desmontar(): void {
          desmontada = true;
          aplicacion.destruir();
        },
      };
    },
  };
}
