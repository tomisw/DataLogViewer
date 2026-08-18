/**
 * Dónde vive `dlv-api`, vista desde la página que carga `dlv-ui` (F5-06).
 *
 * EL DEFECTO QUE ESTO CORRIGE
 * ===========================
 * Antes de F5-06, `main.ts#elegirFuente` construía la URL de la API como
 * `` `http://127.0.0.1:${puerto}` `` **sin mirar nunca** desde qué origen se
 * había cargado la propia página. Eso es invisible en los dos casos que
 * existían hasta ahora —`dlv-app` (pywebview navega a `http://127.0.0.1:...`,
 * ADR-002) y `npm run dev` (Vite en `localhost`)— porque en los dos casos el
 * host real y el cableado coinciden.
 *
 * Deja de coincidir en el despliegue de navegador contra la red del taller
 * (F5-06, docs/02 §E10.2): la página se sirve desde la IP del equipo que hace
 * de servidor (p. ej. `http://192.168.1.50:4173/`), pero el código seguía
 * intentando hablar con `127.0.0.1` — que, desde el navegador de OTRO equipo,
 * es ESE OTRO EQUIPO, no el servidor. La petición no llega a ningún sitio con
 * `dlv-api` escuchando y el error es «no se pudo abrir el log», sin pista de
 * que la causa es la URL, no el fichero.
 *
 * QUÉ NO CAMBIA
 * =============
 * Esta función solo resuelve una dirección; no toca CORS ni el token de
 * sesión (`dlv-api/src/dlv_api/main.py`, ADR-007), que son decisiones del
 * servidor y quedan exactamente como estaban. Ver `docs/11-despliegue-
 * navegador.md` para qué hace falta decidir ahí antes de que este despliegue
 * sea seguro fuera de `127.0.0.1`.
 */

/**
 * Construye la URL base de `dlv-api` a partir de dónde se cargó la página.
 *
 * @param hostnamePagina `window.location.hostname` de la página que sirve
 *   `dlv-ui`. Es `"127.0.0.1"` en `dlv-app` (ADR-002), `"localhost"` en
 *   `npm run dev`, y la IP o nombre del servidor en el despliegue de
 *   navegador (F5-06). Cadena vacía solo en entornos sin `location` real
 *   (algún doble de pruebas): se trata igual que ausente.
 * @param puerto El puerto de `dlv-api`, tal como llega en `?puerto_api=`.
 * @param apiHost Override explícito (`?api_host=`) para el caso en que
 *   `dlv-api` no vive en el mismo host que sirve `dlv-ui` — p. ej. detrás de
 *   un proxy inverso. `null` o cadena vacía usan `hostnamePagina`.
 *
 * NO decide el esquema: siempre `http://`, porque es lo único que acepta hoy
 * `allow_origin_regex` de `dlv-api` (ver el docstring del módulo) y porque
 * ADR-007 no contempla TLS. Si `dlv-api` empezara a servir HTTPS, esta
 * función tendría que volver a mirarse junto con esa regla.
 */
export function resolverUrlBaseApi(
  hostnamePagina: string,
  puerto: string,
  apiHost: string | null,
): string {
  const elegido = apiHost !== null && apiHost.length > 0 ? apiHost : hostnamePagina;
  const host = elegido.length > 0 ? elegido : "127.0.0.1";
  return `http://${conCorchetesSiEsIpv6(host)}:${puerto}`;
}

/**
 * `[::1]` en vez de `::1`, que es lo que exige una URL con IPv6 (RFC 3986 §3.2.2).
 *
 * Hace falta porque `window.location.hostname` devuelve la dirección IPv6 SIN
 * corchetes aunque la URL de la barra los lleve, así que concatenarla con
 * `:${puerto}` da `http://::1:8000`: una URL que ningún navegador resuelve, y el
 * síntoma sería otra vez «no se pudo abrir el log» sin decir que la causa es la
 * dirección. Se detecta por los dos puntos, que no aparecen en un nombre de host
 * ni en una IPv4; si ya vienen con corchetes (un `?api_host=[::1]` escrito a
 * mano) se dejan como están en vez de anidar otros.
 */
function conCorchetesSiEsIpv6(host: string): string {
  if (!host.includes(":") || host.startsWith("[")) return host;
  return `[${host}]`;
}
