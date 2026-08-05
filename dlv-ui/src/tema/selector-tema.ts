/**
 * Selector de tema para la barra superior (F3-21).
 *
 * POR QUÉ ESTO NO ES OPCIONAL
 * ============================
 * La primera versión de F3-21 dejó los tres temas definidos y `establecerTema`
 * exportada, pero sin nadie que la llamara y sin ningún control en la interfaz.
 * El efecto era que el tema solo podía venir de `prefers-color-scheme`, y esa
 * preferencia únicamente distingue claro de oscuro: **el modo de alto contraste
 * era inalcanzable**, que es la mitad del título de la tarea. Un tema que no se
 * puede elegir no está entregado.
 *
 * Es un `<select>` y no tres botones porque la barra ya está llena y porque un
 * `<select>` nativo se lee con lector de pantalla y se maneja con teclado sin
 * que haya que escribir nada de eso -- lo apropiado cuando el control existe
 * justamente por accesibilidad.
 */

import {
  ETIQUETA_DE_TEMA,
  TEMAS_DISPONIBLES,
  establecerTema,
  obtenerTemaActual,
  type NombreTema,
} from "./tema.ts";

/** Clase del contenedor, para que el estilo viva en la hoja y no aquí. */
export const CLASE_SELECTOR_TEMA = "dlv-barra__tema";

/**
 * Construye el selector ya cableado y con el tema activo seleccionado.
 *
 * Devuelve el elemento sin insertarlo: quien construye la barra decide dónde va,
 * igual que con el resto de sus piezas.
 */
export function montarSelectorDeTema(documento: Document = document): HTMLElement {
  const contenedor = documento.createElement("label");
  contenedor.className = CLASE_SELECTOR_TEMA;

  const rotulo = documento.createElement("span");
  rotulo.textContent = "Tema";

  const selector = documento.createElement("select");
  // El `<label>` envuelve al `<select>`, así que la asociación no depende de un
  // `id` que podría chocar si algún día hay dos barras.
  selector.setAttribute("aria-label", "Tema de la interfaz");

  for (const nombre of TEMAS_DISPONIBLES) {
    const opcion = documento.createElement("option");
    opcion.value = nombre;
    opcion.textContent = ETIQUETA_DE_TEMA[nombre];
    selector.appendChild(opcion);
  }
  selector.value = obtenerTemaActual();

  selector.addEventListener("change", () => {
    // El valor sale de las opciones que se acaban de construir a partir de
    // `TEMAS_DISPONIBLES`, así que la conversión es segura; aun así se comprueba,
    // porque `HTMLSelectElement.value` es un `string` para el tipo y una opción
    // añadida desde fuera no debería poder aplicar un tema que no existe.
    const elegido = selector.value as NombreTema;
    if (TEMAS_DISPONIBLES.includes(elegido)) establecerTema(elegido);
  });

  contenedor.append(rotulo, selector);
  return contenedor;
}
