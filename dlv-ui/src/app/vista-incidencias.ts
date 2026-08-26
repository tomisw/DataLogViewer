/**
 * `crearVistaIncidencias`: adapta `PanelDeIncidencias`
 * (`incidencias/panel-incidencias.ts`) a `DefinicionVista` (`app/vistas.ts`).
 *
 * ES EL CABLEADO QUE `panel-incidencias.ts` PEDÍA POR SU PROPIO NOMBRE
 * ========================================================================
 * `OpcionesPanelIncidencias.alSaltarAInstante` llevaba desde F3-12 con un
 * comentario que decía, literalmente, que cablear el salto a la navegación
 * real "es tarea de quien monte el panel en `app/aplicacion.ts` — fuera de
 * mi carril". Este fichero es ESE montaje: `alSaltarAInstante` llama a
 * `contexto.irAVista(ID_VISTA_SERIES, { instanteS })`, que
 * `ConmutadorDeVistas` traduce en desmontar esta vista, montar
 * `vista-series.ts` y, en cuanto el log esté abierto,
 * `Aplicacion.irAInstante(instanteS)` — la vista de series de verdad, no una
 * simulación.
 *
 * POR QUÉ SE MONTA CON DATOS VACÍOS, Y NO SE INVENTAN
 * ======================================================
 * `incidencias/tipos.ts` ya avisa en su cabecera de que `/comandos/incidencias`
 * **no existe todavía** en `dlv-api` (comprobado contra `dlv_api/main.py`: la
 * lista de rutas registradas no lo incluye). `datos/fuente.ts#FuenteDeDatos`
 * tampoco tiene un método para pedir el catálogo de detectores, sus estados
 * ni sus incidencias — y no se le añade uno aquí adivinando una forma que el
 * backend todavía no ha fijado, mismo criterio que ya sigue
 * `datos/fuente-api.ts` con cualquier comando que `dlv-api` no sirve
 * todavía. Por eso este módulo monta el panel con
 * `DATOS_VACIOS` ("Sin incidencias.", sin banner de desactivados) en vez de
 * fingir un catálogo o una incidencia de mentira: es la respuesta honesta a
 * "todavía no hay de dónde traer esto", no un plato vacío por descuido.
 *
 * Traer datos de verdad —abrir `/comandos/incidencias`, resolver la clase de
 * conversión de cada campo de `detalle` (la propia cabecera de
 * `incidencias/tipos.ts` deja esa costura pendiente)— es trabajo aparte, a
 * abrir como tarea propia cuando ese endpoint exista. Lo que SÍ queda hecho y
 * probado aquí, y es independiente de esa tarea futura, es el cableado
 * "saltar → navegación real".
 */

import { montar as montarPanelIncidencias, type DatosPanelIncidencias } from "../incidencias/panel-incidencias.ts";
import { contextoDesdeDocumento } from "../incidencias/contexto-dom.ts";
import type { DefinicionVista, VistaMontada } from "./vistas.ts";
import { ID_VISTA_SERIES } from "./vista-series.ts";

export const ID_VISTA_INCIDENCIAS = "incidencias";

/** Ver "POR QUÉ SE MONTA CON DATOS VACÍOS" en la cabecera del módulo. */
const DATOS_VACIOS: DatosPanelIncidencias = { catalogo: [], estados: [], incidencias: [] };

export function crearVistaIncidencias(documento: Pick<Document, "createElement">): DefinicionVista {
  return {
    id: ID_VISTA_INCIDENCIAS,
    etiqueta: "Incidencias",

    montar(contenedor: HTMLElement, contexto): VistaMontada {
      const panel = montarPanelIncidencias(contenedor, {
        documento: contextoDesdeDocumento(documento),
        alSaltarAInstante: (instanteS) => {
          contexto.irAVista(ID_VISTA_SERIES, { instanteS });
        },
      });
      panel.actualizar(DATOS_VACIOS);

      return {
        desmontar(): void {
          // DOM puro: sin temporizadores, sin oyentes en `window`/`document`,
          // sin WebGL. El conmutador descarta `contenedor` entero al cambiar
          // de vista, y con él se va todo lo que `montar` puso dentro.
        },
      };
    },
  };
}
