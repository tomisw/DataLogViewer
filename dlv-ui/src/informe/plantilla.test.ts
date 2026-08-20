/**
 * Pruebas de `plantilla.ts` (F4-11). Todo en Node, sin DOM: el módulo entero
 * es concatenación de texto (ver su cabecera), así que no hace falta ningún
 * doble.
 *
 * TRES PROPIEDADES QUE NO SE PUEDEN DEJAR A LA VISTA A OJO
 * =============================================================
 * 1. Autocontenido de verdad: ninguna referencia de red en todo el documento.
 * 2. Un nombre de canal hostil no rompe el HTML ni se ejecuta.
 * 3. Ninguna magnitud se convierte aquí — todo llega ya formateado (ver
 *    `tipos.ts`); estas pruebas comprueban que el texto pasado llega intacto,
 *    no que se recalcule nada.
 */

import { beforeEach, describe, expect, it } from "vitest";

import { establecerIdioma, inicializarIdioma } from "../locale/idioma.ts";
import type { DetectorCatalogo, EstadoDetector, IncidenciaPanel } from "../incidencias/tipos.ts";
import { Capa } from "../unidades/tipos.ts";
import { escaparHtml, generarInformeSesionHtml, informeComoBlob } from "./plantilla.ts";
import type { DatosInformeSesion, DimensionConUnidad, GraficoInforme, TiradaInforme } from "./tipos.ts";

function incidencia(parcial: Partial<IncidenciaPanel> & Pick<IncidenciaPanel, "id">): IncidenciaPanel {
  return {
    detectorId: "D1",
    severidad: "media",
    tInicioMs: 0,
    tFinMs: 1000,
    detalle: {},
    ...parcial,
  };
}

const CATALOGO: readonly DetectorCatalogo[] = [
  { id: "D1", etiqueta: "Detonación", severidad: "critica" },
  { id: "D9", etiqueta: "Sobretemperatura", severidad: "alta" },
];

function datos(parcial: Partial<DatosInformeSesion> = {}): DatosInformeSesion {
  return {
    resumen: {
      nombreFichero: "AutoLog1.csv",
      formato: "Haltech NSP",
      duracionTexto: "245,100 s",
      muestras: 1_234_567,
      canales: 42,
      generadoEnTexto: "2026-08-20 10:00",
    },
    unidades: {
      presetEtiqueta: "SI",
      porDimension: [
        { dimensionEtiqueta: "Temperatura", unidadEtiqueta: "°C", capa: Capa.PRESET },
        { dimensionEtiqueta: "Presión de sobrealimentación", unidadEtiqueta: "bar (rel)", capa: Capa.CANAL },
      ],
    },
    incidencias: { catalogo: CATALOGO, estados: [], incidencias: [] },
    tiradas: { tipo: "no_disponible" },
    graficos: [],
    ...parcial,
  };
}

beforeEach(() => {
  inicializarIdioma({});
});

describe("escaparHtml", () => {
  it("escapa los cinco caracteres significativos", () => {
    expect(escaparHtml(`<script>alert("x") & 'y'</script>`)).toBe(
      "&lt;script&gt;alert(&quot;x&quot;) &amp; &#39;y&#39;&lt;/script&gt;",
    );
  });
});

describe("generarInformeSesionHtml — autocontenido: cero referencias de red", () => {
  it("no contiene <script>, <link>, ni un src/href/url()/@import http(s)", () => {
    const grafico: GraficoInforme = {
      titulo: "RPM vs tiempo",
      svgTexto:
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">' +
        '<image href="data:image/png;base64,AAAA"/></svg>',
    };
    const html = generarInformeSesionHtml(datos({ graficos: [grafico] }));

    // El namespace de SVG («xmlns="http://www.w3.org/2000/svg"») es texto
    // obligatorio de cualquier SVG y NUNCA se resuelve por red — por eso las
    // comprobaciones de abajo buscan patrones de CARGA de recurso concretos
    // (script, link, src=, href=, url(), @import), no la subcadena "http"
    // suelta, que daría un falso positivo con ese propio namespace.
    expect(html).not.toMatch(/<script[\s>]/i);
    expect(html).not.toMatch(/<link[\s>]/i);
    expect(html).not.toMatch(/\bsrc\s*=\s*["']https?:/i);
    expect(html).not.toMatch(/\bhref\s*=\s*["']https?:/i);
    expect(html).not.toMatch(/@import/i);
    expect(html).not.toMatch(/url\(\s*["']?https?:/i);
    // Y el propio namespace SÍ sigue ahí: no se ha filtrado por accidente.
    expect(html).toContain("http://www.w3.org/2000/svg");
    // La imagen del gráfico es una URL de datos, no un fichero externo.
    expect(html).toContain("data:image/png;base64,AAAA");
  });

  it("empieza por <!doctype html> y es un único documento", () => {
    const html = generarInformeSesionHtml(datos());
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain("<style>");
    expect(html).toContain("</html>");
  });
});

describe("generarInformeSesionHtml — escapa el HTML de datos hostiles", () => {
  it("un nombre de canal/detector hostil no rompe el documento ni se ejecuta", () => {
    const catalogoHostil: readonly DetectorCatalogo[] = [
      { id: "D1", etiqueta: `<script>alert(1)</script> & "citado"`, severidad: "critica" },
    ];
    const html = generarInformeSesionHtml(
      datos({
        incidencias: {
          catalogo: catalogoHostil,
          estados: [],
          incidencias: [incidencia({ id: "i1", detectorId: "D1" })],
        },
      }),
    );
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;citado&quot;");
  });

  it("el motivo de un detector desactivado también se escapa", () => {
    const catalogoHostil: readonly DetectorCatalogo[] = [
      { id: "D1", etiqueta: "Detonación", severidad: "critica" },
    ];
    const estados: readonly EstadoDetector[] = [
      { detectorId: "D1", activo: false, motivo: `rol "knock_level" <sin confirmar>` },
    ];
    const html = generarInformeSesionHtml(
      datos({ incidencias: { catalogo: catalogoHostil, estados, incidencias: [] } }),
    );
    expect(html).toContain("&lt;sin confirmar&gt;");
    expect(html).toContain("&quot;knock_level&quot;");
    expect(html).not.toContain("<sin confirmar>");
  });

  it("el nombre de fichero de la sesión se escapa en el título", () => {
    const html = generarInformeSesionHtml(
      datos({ resumen: { ...datos().resumen, nombreFichero: `log"><b>x</b>.csv` } }),
    );
    expect(html).not.toContain(`log"><b>x</b>.csv`);
    expect(html).toContain("&quot;&gt;&lt;b&gt;x&lt;/b&gt;");
  });
});

describe("generarInformeSesionHtml — resumen: cuentas sin conversión", () => {
  it("muestra las cuentas de muestras y canales tal cual, y la duración ya formateada", () => {
    const html = generarInformeSesionHtml(datos());
    expect(html).toContain("1234567");
    expect(html).toContain(">42<");
    expect(html).toContain("245,100 s");
    expect(html).toContain("Haltech NSP");
  });
});

describe("generarInformeSesionHtml — unidades usadas declaradas", () => {
  it("declara el preset y cada dimensión con su unidad y su origen", () => {
    const html = generarInformeSesionHtml(datos());
    expect(html).toContain("SI");
    expect(html).toContain("Temperatura");
    expect(html).toContain("°C");
    expect(html).toContain("bar (rel)");
  });

  it("el origen de cada capa sale del catálogo i18n, no de un literal cableado en español", () => {
    establecerIdioma("en");
    const dim: DimensionConUnidad = { dimensionEtiqueta: "Boost", unidadEtiqueta: "bar (rel)", capa: Capa.PRESET };
    const html = generarInformeSesionHtml(
      datos({ unidades: { presetEtiqueta: "SI", porDimension: [dim] } }),
    );
    expect(html).toContain("active preset");
    expect(html).not.toContain("preset activo");
  });
});

describe("generarInformeSesionHtml — incidencias: orden por consecuencia, banner de desactivados", () => {
  it("una incidencia crítica aparece antes que una informativa en el marcado, aunque sea más tardía", () => {
    const html = generarInformeSesionHtml(
      datos({
        incidencias: {
          catalogo: CATALOGO,
          estados: [],
          incidencias: [
            incidencia({ id: "tardia", detectorId: "D9", severidad: "informativa", tInicioMs: 900_000 }),
            incidencia({ id: "temprana", detectorId: "D1", severidad: "critica", tInicioMs: 1_000 }),
          ],
        },
      }),
    );
    const posCritica = html.indexOf("Critica");
    const posInformativa = html.indexOf("Informativa");
    expect(posCritica).toBeGreaterThan(-1);
    expect(posInformativa).toBeGreaterThan(-1);
    expect(posCritica).toBeLessThan(posInformativa);
  });

  it("un detector desactivado se anuncia con su motivo, no se oculta", () => {
    const estados: readonly EstadoDetector[] = [{ detectorId: "D1", activo: false, motivo: "sin confirmar" }];
    const html = generarInformeSesionHtml(
      datos({ incidencias: { catalogo: CATALOGO, estados, incidencias: [] } }),
    );
    expect(html).toContain("sin confirmar");
    expect(html).toContain("Detonación");
  });

  it("sin incidencias, dice que no hay incidencias en vez de una tabla vacía", () => {
    const html = generarInformeSesionHtml(datos());
    expect(html).toContain("Sin incidencias.");
  });
});

describe("generarInformeSesionHtml — tiradas: las tres respuestas honestas, nunca inventadas", () => {
  it("no_disponible: dice explícitamente que la segmentación no está conectada, no omite la sección en silencio", () => {
    const html = generarInformeSesionHtml(datos({ tiradas: { tipo: "no_disponible" } }));
    expect(html).toContain("F3-16");
    expect(html).toContain("no está conectada");
  });

  it("vacia: dice que no se detectó ninguna tirada, distinto de «no disponible»", () => {
    const html = generarInformeSesionHtml(datos({ tiradas: { tipo: "vacia" } }));
    expect(html).toContain("No se detectó ninguna tirada");
    expect(html).not.toContain("F3-16");
  });

  it("con_datos: lista cada tirada con su clase/inicio/duración YA formateados, sin recalcular nada", () => {
    const tirada: TiradaInforme = { clase: "Plena carga", inicioTexto: "12,500 s", duracionTexto: "3,200 s" };
    const html = generarInformeSesionHtml(datos({ tiradas: { tipo: "con_datos", tiradas: [tirada] } }));
    expect(html).toContain("Plena carga");
    expect(html).toContain("12,500 s");
    expect(html).toContain("3,200 s");
  });
});

describe("generarInformeSesionHtml — gráficos", () => {
  it("sin gráficos, lo dice en vez de dejar una sección vacía sin explicación", () => {
    const html = generarInformeSesionHtml(datos({ graficos: [] }));
    expect(html).toContain("no incluye gráficos");
  });

  it("incrusta el SVG ya compuesto tal cual (sin escapar el marcado) bajo un título escapado", () => {
    const grafico: GraficoInforme = {
      titulo: `RPM & Boost <canal>`,
      svgTexto: '<svg xmlns="http://www.w3.org/2000/svg"><rect x="0" y="0"/></svg>',
    };
    const html = generarInformeSesionHtml(datos({ graficos: [grafico] }));
    expect(html).toContain('<svg xmlns="http://www.w3.org/2000/svg"><rect x="0" y="0"/></svg>');
    expect(html).toContain("RPM &amp; Boost &lt;canal&gt;");
  });
});

describe("informeComoBlob", () => {
  it("devuelve un Blob de tipo text/html con el mismo contenido que la cadena", async () => {
    const blob = informeComoBlob(datos());
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.type).toContain("text/html");
    const texto = await blob.text();
    expect(texto).toContain("<!doctype html>");
  });
});
