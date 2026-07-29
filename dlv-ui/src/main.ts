/**
 * Punto de entrada mínimo de dlv-ui (F0-02): llama a `/salud` de dlv-api y
 * muestra el resultado en pantalla.
 *
 * Sin librerías de gráficos (ADR-006): el lienzo WebGL2 propio y las capas
 * SVG de ejes/leyenda se añaden en fases posteriores, no aquí.
 */

interface RespuestaSalud {
  estado: string;
  version_api: string;
  version_core: string;
}

/**
 * Resuelve la URL base de dlv-api. `dlv-app` (ADR-002) abre la ventana con
 * `?puerto_api=<puerto>` en la URL una vez el servidor está escuchando en un
 * puerto efímero (ADR-007); en desarrollo suelto (`npm run dev`, sin
 * dlv-app) se usa el puerto por defecto documentado en `dlv-api/README`.
 */
function urlBaseApi(): string {
  const parametros = new URLSearchParams(window.location.search);
  const puerto = parametros.get("puerto_api") ?? "8000";
  return `http://127.0.0.1:${puerto}`;
}

async function consultarSalud(): Promise<RespuestaSalud> {
  const respuesta = await fetch(`${urlBaseApi()}/salud`);
  if (!respuesta.ok) {
    throw new Error(`dlv-api respondió ${respuesta.status}`);
  }
  return (await respuesta.json()) as RespuestaSalud;
}

function contenedorApp(): HTMLDivElement {
  const contenedor = document.querySelector<HTMLDivElement>("#app");
  if (contenedor === null) {
    throw new Error("no se encontró #app en el documento");
  }
  return contenedor;
}

function render(texto: string): void {
  contenedorApp().textContent = texto;
}

async function iniciar(): Promise<void> {
  render("Consultando dlv-api…");
  try {
    const salud = await consultarSalud();
    render(`dlv-api: ${salud.estado} · api ${salud.version_api} · core ${salud.version_core}`);
  } catch (error) {
    const mensaje = error instanceof Error ? error.message : String(error);
    render(`No se pudo contactar con dlv-api: ${mensaje}`);
  }
}

void iniciar();
