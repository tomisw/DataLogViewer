/**
 * Orden y presentación de las cinco severidades concretas (F3-12).
 *
 * El orden es el dato importante de este fichero, y no se inventa: es
 * literalmente `SEVERIDADES_CONCRETAS` de `tipos.ts`, que a su vez mira a
 * `dlv_core.plausibilidad.SEVERIDADES` (ver la cabecera de ese fichero
 * Python: «el orden de la tupla ES el orden de consecuencia»). Este módulo
 * solo le da forma de comparador y de rango numérico para que `orden.ts`
 * pueda ordenar sin repetir el `if/else` de cinco ramas en cada sitio que
 * necesite saber cuál pesa más.
 */

import { SEVERIDADES_CONCRETAS, type SeveridadCatalogo, type SeveridadConcreta } from "./tipos.ts";

/**
 * Rango de cada severidad: 0 es la más grave (`"critica"`), 4 la menos
 * (`"informativa"`). Construido a partir de `SEVERIDADES_CONCRETAS` y no
 * escrito a mano, para que las dos listas no puedan desincronizarse — si
 * `tipos.ts` cambiara el orden, este mapa cambiaría con él en vez de quedarse
 * con un rango que ya no coincide con la lista.
 */
const RANGO: Readonly<Record<SeveridadConcreta, number>> = Object.fromEntries(
  SEVERIDADES_CONCRETAS.map((severidad, indice) => [severidad, indice]),
) as Readonly<Record<SeveridadConcreta, number>>;

/** Menor rango = más grave. Útil para ordenar o para una barra de progreso. */
export function rangoDeSeveridad(severidad: SeveridadConcreta): number {
  return RANGO[severidad];
}

/**
 * Comparador de consecuencia: negativo si `a` es más grave que `b`, positivo
 * si es al revés, cero si son la misma severidad.
 *
 * Es el criterio #1 de la tarea: «una incidencia crítica de hace 200 s va
 * antes que una informativa de hace 2 s». Este comparador no mira el tiempo
 * en absoluto — eso es aposta, lo añade `orden.ts` como criterio de segundo
 * nivel, dentro de la misma severidad.
 */
export function compararSeveridad(a: SeveridadConcreta, b: SeveridadConcreta): number {
  return rangoDeSeveridad(a) - rangoDeSeveridad(b);
}

/**
 * Etiqueta legible («Crítica», «Informativa», ...) a partir del vocabulario
 * en minúsculas. Es una capitalización pura del propio literal, no una
 * traducción cableada: no hay una tabla de cinco cadenas que pueda
 * desincronizarse de `SEVERIDADES_CONCRETAS` si algún día se añade o se
 * renombra una severidad ahí.
 */
export function etiquetaDeSeveridad(severidad: SeveridadConcreta): string {
  return severidad.charAt(0).toUpperCase() + severidad.slice(1);
}

/**
 * Etiqueta para una entrada de CATÁLOGO, que además de las cinco concretas
 * admite `"segun_nivel"` (D13). No se puede capitalizar sin más — el literal
 * lleva un guion bajo que no es presentable — así que este caso se traduce a
 * mano y las cinco concretas reutilizan `etiquetaDeSeveridad`, en vez de
 * llevar una segunda tabla completa que podría divergir de la de arriba.
 */
export function etiquetaDeSeveridadCatalogo(severidad: SeveridadCatalogo): string {
  if (severidad === "segun_nivel") return "Según nivel";
  return etiquetaDeSeveridad(severidad);
}

/**
 * Marca de severidad sin depender del color: tantos símbolos llenos como
 * grave es la severidad (5 para `"critica"`, 1 para `"informativa"`), sobre
 * un total fijo de 5.
 *
 * Existe porque `tema/tema.ts#PaletaTema` no tiene un color por severidad —
 * sus ocho tokens son de CHROME (fondo, panel, texto, acento...), no de
 * dominio— y la tarea prohíbe explícitamente inventar un color literal aquí
 * («los colores de severidad salen del tema, no de literales tuyos»). En vez
 * de eso, la distinción es la misma que `tema.ts` ya aplica a las series
 * bajo daltonismo (ver su cabecera, «distinguibles por algo más que el
 * tono»): una cantidad, no un matiz. `panel-incidencias.ts` pinta los
 * símbolos llenos con `var(--acento)` y los vacíos con `var(--panel-borde)`
 * — los dos únicos tokens del tema que tienen sentido aquí — así que el
 * color en sí sigue viniendo del tema activo, solo que aplicado a una
 * cantidad variable de símbolos en vez de a cinco colores distintos que el
 * tema no declara. Ver el informe de la tarea, sección de colores.
 */
export function marcaDeSeveridad(severidad: SeveridadConcreta): { llenos: number; total: number } {
  const total = SEVERIDADES_CONCRETAS.length;
  return { llenos: total - rangoDeSeveridad(severidad), total };
}
