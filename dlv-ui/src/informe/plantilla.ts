/**
 * Construye el documento HTML autocontenido del informe de sesión (F4-11).
 *
 * «AUTOCONTENIDO» ES COMPROBABLE, Y SE COMPRUEBA
 * ==================================================
 * Un único `.html`, sin `<script src=>`, sin `<link>` a una hoja externa, sin
 * `@import` ni `url()` de red en el CSS, sin `<img src="http...">`. Todo va
 * en línea: los estilos en un único `<style>` en el `<head>`, y cada gráfico
 * como marcado `<svg>` inline (ver `GraficoInforme` en `tipos.ts`) — que a su
 * vez ya lleva su trazo como una URL de datos PNG (`exportar/
 * exportar-imagen.ts#capturarTrazoPNG`), así que no hay ninguna imagen que
 * dependa de un fichero al lado. `plantilla.test.ts` recorre el documento
 * generado buscando `http://`, `https://`, `<script`, `<link` y `url(` para
 * que esta propiedad no dependa de que nadie se acuerde de revisarla a ojo.
 *
 * NADA DE MOTOR DE PLANTILLAS: CONCATENACIÓN DE TEXTO, COMO EL RESTO DE `dlv-ui`
 * ===================================================================================
 * `dlv-ui` tiene cero dependencias en tiempo de ejecución (`docs/09`). No hace
 * falta una librería para esto: el documento es una plantilla de cadenas de
 * JavaScript, en el mismo espíritu que `exportar-imagen.ts#insertarTrazoEnSvg`
 * compone XML con manipulación de texto y no con el DOM — aquí ni siquiera
 * hace falta el DOM, porque no hay nada que leer de él: todos los datos llegan
 * ya resueltos en `DatosInformeSesion`. Por eso este módulo se prueba entero
 * en Node, sin ningún doble de documento.
 *
 * ESCAPAR ES OBLIGATORIO, Y LA RAZÓN ES EL PROPIO LOG DEL USUARIO
 * ====================================================================
 * Los nombres de canal, las etiquetas de detector y el nombre del fichero de
 * origen vienen del log del usuario (o del catálogo que describe ese log) y
 * acaban dentro de este documento. `escaparHtml` es el único camino por el
 * que pasa cualquier texto que no sea literal de este módulo o SVG ya
 * serializado (ver más abajo). Sin él, un canal llamado
 * `<script>alert(1)</script>` no solo rompería el HTML: ejecutaría lo que
 * llevara dentro en cuanto alguien abriera el informe en un navegador.
 * `plantilla.test.ts` lo comprueba con exactamente ese nombre.
 *
 * LA EXCEPCIÓN DELIBERADA: `GraficoInforme.svgTexto` NO SE ESCAPA
 * ====================================================================
 * Es marcado, no texto: tiene que insertarse tal cual para que el navegador
 * lo dibuje como imagen vectorial, igual que `insertarTrazoEnSvg` inserta el
 * SVG de ejes sin escaparlo. La razón por la que esto sigue siendo seguro es
 * la misma que allí: `svgTexto` es la salida de
 * `XMLSerializer.serializeToString` sobre un `<svg>` real, y ese serializador
 * escapa automáticamente cualquier texto que contuviera (un nombre de canal
 * en una etiqueta de eje, por ejemplo) al convertirlo a XML — no hay ningún
 * camino por el que un nombre de canal hostil llegue a `svgTexto` sin pasar
 * antes por esa serialización seria. Lo que este módulo NO hace es generar
 * `svgTexto` él mismo: lo recibe ya hecho (ver la cabecera de `tipos.ts`).
 *
 * NINGÚN NÚMERO SE CONVIERTE AQUÍ (la trampa del delta, otra vez)
 * ====================================================================
 * Ver la cabecera de `tipos.ts`: todos los campos que representan una
 * magnitud llegan como texto ya formateado con su unidad. La única
 * excepción son las CUENTAS de `ResumenSesionInforme` (`muestras`, `canales`)
 * y las de `contarPorSeveridad` (incidencias/orden.ts) — enteros sin unidad,
 * que se formatean aquí con `String()` sin más porque un cardinal no necesita
 * separador decimal ni conversión.
 */

import {
  construirFilasDeDetector,
  contarPorSeveridad,
  duracionS,
  instanteDeSalto,
  ordenarFilasDeDetector,
  ordenarPorConsecuencia,
  type FilaDetector,
} from "../incidencias/orden.ts";
import { etiquetaDeSeveridad } from "../incidencias/severidad.ts";
import { formatearDuracionS, formatearInstanteS } from "../incidencias/formato.ts";
import { SEVERIDADES_CONCRETAS, type IncidenciaPanel } from "../incidencias/tipos.ts";
import { obtenerIdiomaActual } from "../locale/idioma.ts";
import { t, type ClaveTexto } from "../locale/catalogo.ts";
import { Capa } from "../unidades/tipos.ts";
import type { DatosInformeSesion, DimensionConUnidad, GraficoInforme, TiradaInforme } from "./tipos.ts";

/**
 * Escapa los cinco caracteres significativos de HTML/XML. Único camino de
 * texto de usuario hacia el documento — ver la cabecera del módulo.
 */
export function escaparHtml(texto: string): string {
  return texto
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Texto de la capa de precedencia (`docs/06` §6.9) que decidió una unidad, YA en el catálogo i18n.
 *
 * No reutiliza `unidades/resolucion.ts#explicacionDeCapa`: esa función devuelve
 * texto en español cableado (decisión de F1-31, fuera de mi carril), y un
 * informe bilingüe con ese texto siempre en español mientras el resto está en
 * inglés es el mismo defecto de coherencia que `incidencias/formato.ts`
 * documenta para los números («Jump to the instant... (12,345 s)»). Aquí cada
 * capa tiene su propia clave, en los dos idiomas.
 */
const CLAVE_POR_CAPA: Readonly<Record<Capa, ClaveTexto>> = {
  [Capa.CANAL]: "informe.origenCanal",
  [Capa.PERFIL]: "informe.origenPerfil",
  [Capa.PRESET]: "informe.origenPreset",
  [Capa.CANONICA]: "informe.origenCanonica",
};

function seccionResumen(datos: DatosInformeSesion): string {
  const r = datos.resumen;
  return `
    <section class="dlv-informe-seccion">
      <h2>${escaparHtml(t("informe.seccionResumen"))}</h2>
      <dl class="dlv-informe-resumen">
        <dt>${escaparHtml(t("informe.campoFormato"))}</dt><dd>${escaparHtml(r.formato)}</dd>
        <dt>${escaparHtml(t("informe.campoDuracion"))}</dt><dd>${escaparHtml(r.duracionTexto)}</dd>
        <dt>${escaparHtml(t("informe.campoMuestras"))}</dt><dd>${String(r.muestras)}</dd>
        <dt>${escaparHtml(t("informe.campoCanales"))}</dt><dd>${String(r.canales)}</dd>
      </dl>
    </section>`;
}

function filaUnidad(fila: DimensionConUnidad): string {
  return `
        <tr>
          <td>${escaparHtml(fila.dimensionEtiqueta)}</td>
          <td>${escaparHtml(fila.unidadEtiqueta)}</td>
          <td>${escaparHtml(t(CLAVE_POR_CAPA[fila.capa]))}</td>
        </tr>`;
}

function seccionUnidades(datos: DatosInformeSesion): string {
  const u = datos.unidades;
  const filas = u.porDimension.map(filaUnidad).join("");
  return `
    <section class="dlv-informe-seccion">
      <h2>${escaparHtml(t("informe.seccionUnidades"))}</h2>
      <p>${escaparHtml(t("informe.preset", { preset: u.presetEtiqueta }))}</p>
      <table class="dlv-informe-tabla">
        <thead>
          <tr>
            <th>${escaparHtml(t("informe.columnaDimension"))}</th>
            <th>${escaparHtml(t("informe.columnaUnidad"))}</th>
            <th>${escaparHtml(t("informe.columnaOrigen"))}</th>
          </tr>
        </thead>
        <tbody>${filas}</tbody>
      </table>
    </section>`;
}

/** Resumen de conteo por severidad, en el orden de consecuencia — mismo criterio que el panel en vivo. */
function resumenIncidenciasTexto(incidencias: readonly IncidenciaPanel[]): string {
  if (incidencias.length === 0) return escaparHtml(t("incidencias.sinIncidencias"));
  const conteo = contarPorSeveridad(incidencias);
  const partes = SEVERIDADES_CONCRETAS.filter((s) => conteo[s] > 0).map(
    (s) => `${conteo[s]} ${etiquetaDeSeveridad(s).toLowerCase()}`,
  );
  return escaparHtml(partes.join(" · "));
}

function filaDesactivado(fila: FilaDetector): string {
  const estado = fila.estado;
  if (estado.activo) return ""; // guardia de tipo, ver panel-incidencias.ts para el mismo patrón
  return `<li>${escaparHtml(fila.detector.etiqueta)}: ${escaparHtml(estado.motivo)}</li>`;
}

function bannerDesactivados(filas: readonly FilaDetector[]): string {
  const desactivados = filas.filter((f) => !f.estado.activo);
  if (desactivados.length === 0) return "";
  const titulo =
    desactivados.length === 1
      ? t("incidencias.bannerSingular")
      : t("incidencias.bannerPlural", { n: desactivados.length });
  const items = desactivados.map(filaDesactivado).join("");
  return `
      <div class="dlv-informe-banner">
        <p><strong>${escaparHtml(titulo)}</strong></p>
        <ul>${items}</ul>
      </div>`;
}

function filaIncidencia(incidencia: IncidenciaPanel, etiquetaDetector: string): string {
  const duracion = formatearDuracionS(duracionS(incidencia));
  const instante = formatearInstanteS(instanteDeSalto(incidencia));
  return `
        <tr>
          <td>${escaparHtml(etiquetaDeSeveridad(incidencia.severidad))}</td>
          <td>${escaparHtml(etiquetaDetector)}</td>
          <td>${escaparHtml(instante)}</td>
          <td>${escaparHtml(duracion)}</td>
        </tr>`;
}

function seccionIncidencias(datos: DatosInformeSesion): string {
  const d = datos.incidencias;
  const mapaCatalogo = new Map(d.catalogo.map((c) => [c.id, c]));
  const filas = ordenarFilasDeDetector(construirFilasDeDetector(d.catalogo, d.estados, d.incidencias));
  const incidenciasOrdenadas = ordenarPorConsecuencia(d.incidencias);

  const filasTabla = incidenciasOrdenadas
    .map((inc) => filaIncidencia(inc, mapaCatalogo.get(inc.detectorId)?.etiqueta ?? inc.detectorId))
    .join("");

  const tabla =
    incidenciasOrdenadas.length === 0
      ? ""
      : `
      <table class="dlv-informe-tabla">
        <thead>
          <tr>
            <th>${escaparHtml(t("informe.columnaSeveridad"))}</th>
            <th>${escaparHtml(t("informe.columnaDetector"))}</th>
            <th>${escaparHtml(t("informe.columnaInicioTirada"))}</th>
            <th>${escaparHtml(t("informe.columnaDuracionTirada"))}</th>
          </tr>
        </thead>
        <tbody>${filasTabla}</tbody>
      </table>`;

  return `
    <section class="dlv-informe-seccion">
      <h2>${escaparHtml(t("informe.seccionIncidencias"))}</h2>
      ${bannerDesactivados(filas)}
      <p>${resumenIncidenciasTexto(d.incidencias)}</p>
      ${tabla}
    </section>`;
}

function filaTirada(tirada: TiradaInforme): string {
  return `
        <tr>
          <td>${escaparHtml(tirada.clase)}</td>
          <td>${escaparHtml(tirada.inicioTexto)}</td>
          <td>${escaparHtml(tirada.duracionTexto)}</td>
        </tr>`;
}

function seccionTiradas(datos: DatosInformeSesion): string {
  const seccion = datos.tiradas;
  let cuerpo: string;
  if (seccion.tipo === "no_disponible") {
    cuerpo = `<p class="dlv-informe-aviso">${escaparHtml(t("informe.tiradasNoDisponibles"))}</p>`;
  } else if (seccion.tipo === "vacia") {
    cuerpo = `<p>${escaparHtml(t("informe.tiradasSinDatos"))}</p>`;
  } else {
    const filas = seccion.tiradas.map(filaTirada).join("");
    cuerpo = `
      <table class="dlv-informe-tabla">
        <thead>
          <tr>
            <th>${escaparHtml(t("informe.columnaClaseTirada"))}</th>
            <th>${escaparHtml(t("informe.columnaInicioTirada"))}</th>
            <th>${escaparHtml(t("informe.columnaDuracionTirada"))}</th>
          </tr>
        </thead>
        <tbody>${filas}</tbody>
      </table>`;
  }
  return `
    <section class="dlv-informe-seccion">
      <h2>${escaparHtml(t("informe.seccionTiradas"))}</h2>
      ${cuerpo}
    </section>`;
}

function bloqueGrafico(grafico: GraficoInforme): string {
  // `grafico.svgTexto` NO se escapa: es marcado ya serializado, no texto. Ver
  // la cabecera del módulo, sección de la excepción deliberada.
  return `
      <figure class="dlv-informe-grafico">
        <figcaption>${escaparHtml(grafico.titulo)}</figcaption>
        ${grafico.svgTexto}
      </figure>`;
}

function seccionGraficos(datos: DatosInformeSesion): string {
  const cuerpo =
    datos.graficos.length === 0
      ? `<p>${escaparHtml(t("informe.sinGraficos"))}</p>`
      : datos.graficos.map(bloqueGrafico).join("");
  return `
    <section class="dlv-informe-seccion">
      <h2>${escaparHtml(t("informe.seccionGraficos"))}</h2>
      ${cuerpo}
    </section>`;
}

/**
 * CSS en línea, sin ninguna referencia externa (ni `@import`, ni `url()` de
 * red, ni tipografía de Google Fonts): solo la pila de fuentes del sistema.
 * A propósito no reutiliza los tokens de `tema/tema.ts` (variables CSS que
 * solo existen en la aplicación en ejecución): este documento tiene que
 * verse bien abierto SOLO, meses después, sin la aplicación — así que trae su
 * propia paleta fija, neutra y de alto contraste, pensada también para
 * imprimir.
 */
const ESTILO = `
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    max-width: 960px;
    margin: 0 auto;
    padding: 24px;
    color: #1a1a1a;
    background: #ffffff;
    line-height: 1.45;
  }
  h1 { font-size: 1.4rem; margin-bottom: 4px; }
  h2 { font-size: 1.1rem; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 32px; }
  .dlv-informe-generado { color: #555555; font-size: 0.85rem; margin-top: 0; }
  .dlv-informe-seccion { margin-top: 16px; }
  .dlv-informe-resumen { display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; }
  .dlv-informe-resumen dt { font-weight: 600; }
  .dlv-informe-resumen dd { margin: 0; }
  .dlv-informe-tabla { border-collapse: collapse; width: 100%; margin-top: 8px; }
  .dlv-informe-tabla th, .dlv-informe-tabla td {
    border: 1px solid #cccccc;
    padding: 4px 8px;
    text-align: left;
    font-size: 0.9rem;
  }
  .dlv-informe-tabla th { background: #f2f2f2; }
  .dlv-informe-banner {
    border: 1px solid #cccccc;
    border-left: 3px solid #555555;
    padding: 8px 12px;
    margin: 8px 0;
  }
  .dlv-informe-aviso { font-style: italic; color: #555555; }
  .dlv-informe-grafico { margin: 16px 0; }
  .dlv-informe-grafico svg { max-width: 100%; height: auto; }
  .dlv-informe-grafico figcaption { font-weight: 600; margin-bottom: 4px; }
  .dlv-informe-pie { color: #777777; font-size: 0.8rem; margin-top: 32px; border-top: 1px solid #ccc; padding-top: 8px; }
`;

/**
 * El documento HTML completo, autocontenido, en una sola cadena. Ver la
 * cabecera del módulo para las tres propiedades que esto garantiza: sin
 * recursos externos, todo texto de usuario escapado, y ninguna conversión de
 * unidad hecha aquí.
 */
export function generarInformeSesionHtml(datos: DatosInformeSesion): string {
  const idioma = obtenerIdiomaActual();
  const titulo = t("informe.tituloDocumento", { nombre: datos.resumen.nombreFichero });
  return `<!doctype html>
<html lang="${idioma}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escaparHtml(titulo)}</title>
<style>${ESTILO}</style>
</head>
<body>
<h1>${escaparHtml(titulo)}</h1>
<p class="dlv-informe-generado">${escaparHtml(t("informe.generadoEl", { fecha: datos.resumen.generadoEnTexto }))}</p>
${seccionResumen(datos)}
${seccionUnidades(datos)}
${seccionIncidencias(datos)}
${seccionTiradas(datos)}
${seccionGraficos(datos)}
<p class="dlv-informe-pie">${escaparHtml(t("informe.pie"))}</p>
</body>
</html>
`;
}

/** El documento como `Blob` listo para descargar (`text/html`), sin tocar el disco (ver `tipos.ts`). */
export function informeComoBlob(datos: DatosInformeSesion): Blob {
  return new Blob([generarInformeSesionHtml(datos)], { type: "text/html;charset=utf-8" });
}
