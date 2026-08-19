/**
 * Panel de incidencias por severidad con salto al instante (F3-12).
 *
 * Cablea la lógica pura de `orden.ts` y `severidad.ts` sobre `ContextoDOM`
 * (`contexto-dom.ts`). Igual que `paneles/paneles.ts` y `cursor/cursor.ts`,
 * la parte que decide QUÉ mostrar y en qué orden está separada de la que
 * crea nodos, y es la primera la que llevan las pruebas de verdad
 * (`orden.test.ts`, `severidad.test.ts`); este fichero solo se prueba en lo
 * que un doble puede decir: qué nodos se crean, qué texto llevan y qué
 * instante se pidió al pulsar una fila (`panel-incidencias.test.ts`).
 *
 * TRES DECISIONES QUE VIENEN DIRECTAMENTE DEL ENCARGO
 * ====================================================
 * 1. **Orden por consecuencia, no por tiempo** (`ordenarPorConsecuencia`):
 *    la lista principal nunca se recorre en el orden de `datos.incidencias`.
 * 2. **`segun_nivel` no rompe el catálogo**: `DetectorCatalogo.severidad`
 *    puede ser ese literal (D13) y este módulo lo pinta con su propia
 *    etiqueta (`etiquetaDeSeveridadCatalogo`) en vez de asumir una de las
 *    cinco concretas.
 * 3. **Desactivado se pinta, no se oculta**: `#pintarBanner` es la única
 *    sección que aparece o no según haya detectores con `estado.activo ===
 *    false`, y punto — nunca se decide por si `incidencias` está vacío.
 *
 * SOBRE EL COLOR DE LAS SEVERIDADES
 * ==================================
 * `tema/tema.ts#PaletaTema` no tiene un color por severidad: sus ocho tokens
 * (`fondo`, `panel`, `panelBorde`, `texto`, `textoTenue`, `acento`, `rejilla`,
 * `eje`) son de CHROME, no de dominio, y no se le añade uno aquí — este
 * componente no toca `src/tema/`, está fuera de mi carril, y un literal
 * cableado (`"#e74c3c"` para crítica, etc.) es exactamente lo que la tarea
 * prohíbe («los colores de severidad salen del tema, no de literales
 * tuyos»). La distinción visual sale de `severidad.ts#marcaDeSeveridad`
 * (una cantidad de símbolos, no un matiz) pintada con los dos únicos tokens
 * que tienen sentido para eso (`--acento` lleno, `--panel-borde` vacío), más
 * el peso de fuente. Ver el informe de la tarea para el hueco que esto deja.
 */

import {
  construirFilasDeDetector,
  contarPorSeveridad,
  duracionS,
  instanteDeSalto,
  ordenarFilasDeDetector,
  ordenarPorConsecuencia,
  type FilaDetector,
} from "./orden.ts";
import { etiquetaDeSeveridad, etiquetaDeSeveridadCatalogo, marcaDeSeveridad } from "./severidad.ts";
import { formatearDuracionS, formatearInstanteS } from "./formato.ts";
import {
  contextoDesdeDocumento,
  elementoDesdeHtml,
  type ContextoDOM,
  type ElementoDOM,
} from "./contexto-dom.ts";
import { SEVERIDADES_CONCRETAS, type DetectorCatalogo, type EstadoDetector, type IncidenciaPanel } from "./tipos.ts";
import { t } from "../locale/catalogo.ts";

/** Lo que necesita `actualizar` para repintar el panel entero. */
export interface DatosPanelIncidencias {
  readonly catalogo: readonly DetectorCatalogo[];
  readonly estados: readonly EstadoDetector[];
  readonly incidencias: readonly IncidenciaPanel[];
}

export interface OpcionesPanelIncidencias {
  /** Por omisión, `document` global adaptado. Inyectable para pruebas (`doble-dom.ts`). */
  readonly documento?: ContextoDOM;
  /**
   * Se llama con el instante (segundos absolutos, la unidad de
   * `render/tipos.ts#Vista`) al pulsar «saltar» en una incidencia. Cablear
   * esto a la navegación real (`ControladorDeNavegacion`/`Vista`) es tarea
   * de quien monte el panel en `app/aplicacion.ts` — fuera de mi carril, ver
   * el informe.
   */
  readonly alSaltarAInstante?: (instanteS: number) => void;
}

function crearNodo(documento: ContextoDOM, etiqueta: string, clase: string): ElementoDOM {
  const nodo = documento.createElement(etiqueta);
  nodo.classList.add(clase);
  return nodo;
}

export class PanelDeIncidencias {
  readonly #contenedor: ElementoDOM;
  readonly #documento: ContextoDOM;
  readonly #alSaltarAInstante: (instanteS: number) => void;

  constructor(contenedor: ElementoDOM, opciones: OpcionesPanelIncidencias = {}) {
    this.#contenedor = contenedor;
    this.#documento = opciones.documento ?? contextoDesdeDocumento(document);
    this.#alSaltarAInstante = opciones.alSaltarAInstante ?? ((): void => {});
    this.#contenedor.classList.add("panel-incidencias");
    this.#contenedor.style.setProperty("display", "flex");
    this.#contenedor.style.setProperty("flex-direction", "column");
    this.#contenedor.style.setProperty("gap", "6px");
    this.#contenedor.style.setProperty("overflow-y", "auto");
  }

  /** Repinta el panel entero a partir de datos nuevos. Reemplaza todos los hijos. */
  actualizar(datos: DatosPanelIncidencias): void {
    const mapaCatalogo = new Map(datos.catalogo.map((d) => [d.id, d]));
    const filas = ordenarFilasDeDetector(
      construirFilasDeDetector(datos.catalogo, datos.estados, datos.incidencias),
    );
    const desactivados = filas.filter((f) => !f.estado.activo);
    const incidenciasOrdenadas = ordenarPorConsecuencia(datos.incidencias);

    const hijos: ElementoDOM[] = [];
    if (desactivados.length > 0) {
      hijos.push(this.#pintarBannerDesactivados(desactivados));
    }
    hijos.push(this.#pintarResumen(datos.incidencias));
    hijos.push(this.#pintarLista(incidenciasOrdenadas, mapaCatalogo));
    this.#contenedor.replaceChildren(...hijos);
  }

  #pintarBannerDesactivados(desactivados: readonly FilaDetector[]): ElementoDOM {
    const banner = crearNodo(this.#documento, "div", "panel-incidencias__banner");
    banner.style.setProperty("border", "1px solid var(--panel-borde)");
    banner.style.setProperty("border-left", "3px solid var(--acento)");
    banner.style.setProperty("padding", "4px 6px");
    banner.style.setProperty("color", "var(--texto)");

    const titulo = crearNodo(this.#documento, "div", "panel-incidencias__banner-titulo");
    titulo.textContent =
      desactivados.length === 1
        ? t("incidencias.bannerSingular")
        : t("incidencias.bannerPlural", { n: desactivados.length });
    titulo.style.setProperty("font-weight", "700");
    banner.appendChild(titulo);

    for (const fila of desactivados) {
      const estado = fila.estado;
      // El filtro de arriba ya garantiza `!estado.activo`; este `if` es lo
      // que deja que TypeScript lo sepa también (un `.filter` no reduce el
      // tipo de la unión) y sirve de guardia real si algún día ese filtro
      // cambiara.
      if (estado.activo) continue;
      const linea = crearNodo(this.#documento, "div", "panel-incidencias__banner-linea");
      linea.textContent = `${fila.detector.etiqueta}: ${estado.motivo}`;
      linea.title = estado.motivo;
      linea.style.setProperty("color", "var(--texto-tenue)");
      banner.appendChild(linea);
    }
    return banner;
  }

  #pintarResumen(incidencias: readonly IncidenciaPanel[]): ElementoDOM {
    const resumen = crearNodo(this.#documento, "div", "panel-incidencias__resumen");
    resumen.style.setProperty("color", "var(--texto-tenue)");
    resumen.style.setProperty("font-size", "11px");

    if (incidencias.length === 0) {
      resumen.textContent = t("incidencias.sinIncidencias");
      return resumen;
    }

    const conteo = contarPorSeveridad(incidencias);
    const partes = SEVERIDADES_CONCRETAS.filter((severidad) => conteo[severidad] > 0).map(
      (severidad) => `${conteo[severidad]} ${etiquetaDeSeveridad(severidad).toLowerCase()}`,
    );
    resumen.textContent = partes.join(" · ");
    return resumen;
  }

  #pintarLista(
    incidencias: readonly IncidenciaPanel[],
    mapaCatalogo: ReadonlyMap<string, DetectorCatalogo>,
  ): ElementoDOM {
    const lista = crearNodo(this.#documento, "ul", "panel-incidencias__lista");
    lista.style.setProperty("list-style", "none");
    lista.style.setProperty("margin", "0");
    lista.style.setProperty("padding", "0");
    lista.style.setProperty("display", "flex");
    lista.style.setProperty("flex-direction", "column");
    lista.style.setProperty("gap", "2px");

    if (incidencias.length === 0) {
      lista.appendChild(this.#pintarFilaVacia());
      return lista;
    }

    for (const incidencia of incidencias) {
      lista.appendChild(this.#pintarFila(incidencia, mapaCatalogo));
    }
    return lista;
  }

  #pintarFilaVacia(): ElementoDOM {
    const li = crearNodo(this.#documento, "li", "panel-incidencias__vacio");
    li.textContent = t("incidencias.sinIncidenciasActivos");
    li.style.setProperty("color", "var(--texto-tenue)");
    li.style.setProperty("font-style", "italic");
    return li;
  }

  #pintarFila(
    incidencia: IncidenciaPanel,
    mapaCatalogo: ReadonlyMap<string, DetectorCatalogo>,
  ): ElementoDOM {
    const detector = mapaCatalogo.get(incidencia.detectorId);
    const etiquetaDetector = detector?.etiqueta ?? incidencia.detectorId;

    const li = crearNodo(this.#documento, "li", "panel-incidencias__fila");
    li.style.setProperty("display", "flex");
    li.style.setProperty("align-items", "baseline");
    li.style.setProperty("gap", "8px");
    li.style.setProperty("padding", "2px 4px");
    li.style.setProperty("border-left", `3px solid ${this.#colorDeMarca(incidencia)}`);

    const marca = crearNodo(this.#documento, "span", "panel-incidencias__marca");
    const { llenos, total } = marcaDeSeveridad(incidencia.severidad);
    marca.textContent = "●".repeat(llenos) + "○".repeat(total - llenos);
    marca.style.setProperty("color", "var(--acento)");
    marca.style.setProperty("letter-spacing", "1px");
    marca.title = etiquetaDeSeveridad(incidencia.severidad);
    li.appendChild(marca);

    const cuerpo = crearNodo(this.#documento, "span", "panel-incidencias__cuerpo");
    cuerpo.style.setProperty("flex", "1 1 auto");
    cuerpo.style.setProperty("color", "var(--texto)");
    const duracion = formatearDuracionS(duracionS(incidencia));
    cuerpo.textContent = `${etiquetaDeSeveridad(incidencia.severidad)} · ${etiquetaDetector} — ${formatearInstanteS(instanteDeSalto(incidencia))} (dur. ${duracion})`;
    li.appendChild(cuerpo);

    const boton = crearNodo(this.#documento, "button", "panel-incidencias__salto");
    boton.setAttribute("type", "button");
    boton.textContent = t("incidencias.saltar");
    boton.title = t("incidencias.saltarTitulo", {
      instante: formatearInstanteS(instanteDeSalto(incidencia)),
    });
    boton.style.setProperty("background", "var(--panel)");
    boton.style.setProperty("border", "1px solid var(--panel-borde)");
    boton.style.setProperty("color", "var(--texto)");
    boton.style.setProperty("cursor", "pointer");
    boton.addEventListener("click", () => this.#alSaltarAInstante(instanteDeSalto(incidencia)));
    li.appendChild(boton);

    return li;
  }

  /**
   * Grosor/color del borde de la fila. Solo dos estados posibles —acento o
   * borde neutro— porque son los dos únicos tokens del tema con sentido
   * aquí (ver la cabecera). `critica`/`alta` llevan acento; el resto, el
   * borde neutro del panel.
   */
  #colorDeMarca(incidencia: IncidenciaPanel): string {
    return incidencia.severidad === "critica" || incidencia.severidad === "alta"
      ? "var(--acento)"
      : "var(--panel-borde)";
  }
}

/** Etiqueta de una entrada de catálogo, incluido el caso `"segun_nivel"` de D13. */
export function etiquetaCatalogo(detector: DetectorCatalogo): string {
  return `${detector.etiqueta} (${etiquetaDeSeveridadCatalogo(detector.severidad)})`;
}

/** Monta el panel sobre un `HTMLElement` real. Punto de entrada para `app/aplicacion.ts`. */
export function montar(
  elemento: HTMLElement,
  opciones: OpcionesPanelIncidencias = {},
): PanelDeIncidencias {
  return new PanelDeIncidencias(elementoDesdeHtml(elemento), opciones);
}
