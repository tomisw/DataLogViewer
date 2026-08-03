/**
 * `Aplicacion`: el ensamblado que une todo lo que F1 construyó por separado.
 *
 * QUÉ ES ESTE FICHERO Y QUÉ NO ES
 * =================================
 * Ningún módulo de `src/` sabía, hasta esta tarea, abrir un log ni pintar uno
 * de verdad: cada uno recibe ya los datos resueltos (ADR-006 lo dice para el
 * renderizador, y el mismo criterio se repite en paneles, ejes, escalas,
 * cursor, navegación, unidades y selector de canales — cada cabecera de
 * módulo lo explica por separado). Este fichero es el pegamento: abre un log
 * a través de una `FuenteDeDatos`, decide qué nivel de pirámide pedir, aplica
 * la conversión de unidad de mentira de `conversion-demo.ts` y llama a cada
 * módulo con la forma exacta que su propio contrato pide. No añade lógica de
 * negocio nueva — si algo aquí parece "una decisión de diseño", es porque
 * está describiendo una costura entre dos módulos que no se habían tocado
 * todavía, no porque este fichero decida cómo se hace zoom o cómo se decima.
 *
 * UN EJE DE TIEMPO COMPARTIDO, UN GESTOR DE ESCALA POR PANEL
 * =============================================================
 * Solo hay UN `ControladorDeNavegacion`, colgado del contenedor raíz de
 * `PanelesApilados` (no uno por panel): es lo que garantiza que el eje X sea
 * el mismo en todos los paneles sin duplicar historial de deshacer/rehacer
 * por panel. La rueda y el arrastre solo tocan el eje temporal en la práctica
 * (`aritmetica.ts` ya lo dice: "el eje Y todavía no tiene autoescala ni
 * bloqueo" es la razón por la que la rueda no lo toca) — el eje de valores de
 * cada panel lo decide su propio `GestorEscalas`, con autoescala por
 * omisión, y `vistaPorSerie()` de cada gestor pisa el `v0`/`v1` que traiga el
 * controlador. Ver el informe de la tarea para las costuras que esto deja
 * (un único eje Y por panel, no uno por canal).
 */

import { CacheDeCubos, type ClaveCubos, type Rango } from "../datos/cache-cubos.ts";
import type { CanalDeFuente, FuenteDeDatos, LogAbierto } from "../datos/fuente.ts";
import { pintarEjes } from "../ejes/ejes.ts";
import { CursorDeTabla, type CanalCursor } from "../cursor/cursor.ts";
import { formatearNumero as formatearNumeroLocale } from "../locale/numerico.ts";
import { ControladorDeNavegacion } from "../navegacion/controlador.ts";
import type { DefinicionPanel } from "../paneles/paneles.ts";
import { PanelesApilados } from "../paneles/paneles.ts";
import { ajustarLienzo, Renderizador } from "../render/renderizador.ts";
import { elegirNivel, type ResumenNivel } from "../render/escala.ts";
import type { Color, CubosContinuos, Vista, Viewport } from "../render/tipos.ts";
import { GestorEscalas, tituloConModo } from "../escalas/gestor.ts";
import type { RangoValor } from "../escalas/rango.ts";
import { SelectorCanales } from "../canales/selector-canales.ts";
import type { CanalInfo as CanalParaSelector } from "../canales/tipos.ts";
import { fabricaDesdeDocumento } from "../unidades/dom.ts";
import { SelectorUnidad } from "../unidades/selector-unidad.ts";
import type {
  CanalInfo as CanalParaUnidad,
  CatalogoUnidades,
  UnidadResuelta,
} from "../unidades/tipos.ts";
import { convertirCubos, convertirValor, factorDe } from "./conversion-demo.ts";

const EJE_PRINCIPAL = "principal";

interface EstadoPanel {
  readonly panelId: string;
  canalesIds: string[];
  readonly canvas: HTMLCanvasElement;
  readonly svg: SVGSVGElement;
  readonly tablaCursor: HTMLTableElement;
  readonly renderizador: Renderizador;
  gestor: GestorEscalas;
  cursor: CursorDeTabla;
  /** `${canalId}` -> clave textual de lo último subido a la GPU, para no repetir `subirSerie`. */
  readonly ultimaSubida: Map<string, string>;
  /** Factor de pirámide vigente por canal, para saber cuándo `actualizarCanales` del cursor. */
  ultimoFactor: Map<string, number>;
}

const NS_SVG = "http://www.w3.org/2000/svg";

/** Paleta fija por índice: HSL con separación uniforme de matiz, saturación y luz altas para fondo oscuro. */
function colorPorIndice(indice: number): Color {
  const matiz = (indice * 137.508) % 360; // ángulo áureo: buena dispersión sin tabla fija
  const { r, g, b } = hslARgb(matiz, 0.65, 0.6);
  return { r, g, b, a: 1 };
}

function hslARgb(h: number, s: number, l: number): { r: number; g: number; b: number } {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = h / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let r1 = 0;
  let g1 = 0;
  let b1 = 0;
  if (hp < 1) [r1, g1, b1] = [c, x, 0];
  else if (hp < 2) [r1, g1, b1] = [x, c, 0];
  else if (hp < 3) [r1, g1, b1] = [0, c, x];
  else if (hp < 4) [r1, g1, b1] = [0, x, c];
  else if (hp < 5) [r1, g1, b1] = [x, 0, c];
  else [r1, g1, b1] = [c, 0, x];
  const m = l - c / 2;
  return { r: r1 + m, g: g1 + m, b: b1 + m };
}

/** Rango min/max de un cubo dentro de `[vista.t0, vista.t1]`, o `null` si nada cae dentro. */
function rangoVisibleDeCubos(cubos: CubosContinuos, vista: Pick<Vista, "t0" | "t1">): RangoValor | null {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < cubos.t.length; i += 1) {
    const tAbs = cubos.t[i]! + cubos.tOrigen;
    if (tAbs < vista.t0 || tAbs > vista.t1) continue;
    const mn = cubos.minimo[i]!;
    const mx = cubos.maximo[i]!;
    if (Number.isNaN(mn) || Number.isNaN(mx)) continue;
    if (mn < min) min = mn;
    if (mx > max) max = mx;
  }
  return Number.isFinite(min) ? { min, max } : null;
}

export class Aplicacion {
  readonly #raiz: HTMLElement;
  readonly #fuente: FuenteDeDatos;

  readonly #barra: HTMLElement;
  readonly #estadoTexto: HTMLElement;
  readonly #barraLateral: HTMLElement;
  readonly #contenedorSelectorCanales: HTMLElement;
  readonly #contenedorSelectorUnidad: HTMLElement;
  readonly #areaPrincipal: HTMLElement;
  readonly #contenedorPaneles: HTMLElement;
  readonly #mensajeVacio: HTMLElement;

  #log: LogAbierto | null = null;
  #catalogo: CatalogoUnidades | null = null;
  #cache = new CacheDeCubos();
  #nivelesPorCanal = new Map<string, readonly ResumenNivel[]>();

  #selectorCanales: SelectorCanales | null = null;
  #selectorUnidad: SelectorUnidad | null = null;
  #resueltasUnidad = new Map<string, UnidadResuelta>();

  #paneles: PanelesApilados | null = null;
  #nav: ControladorDeNavegacion | null = null;
  #porPanel = new Map<string, EstadoPanel>();
  #colorPorCanal = new Map<string, Color>();

  #idFrameCursor: number | null = null;
  #redibujando = false;
  #pendienteOtraVuelta = false;
  /**
   * Se incrementa en cada `#reconstruir()`. `#redibujarUnaVez` la comprueba
   * tras cada `await`: si cambió mientras esperaba datos, el `EstadoPanel`
   * que tiene en la mano puede haber sido destruido entre medias (p. ej. la
   * preselección inicial dispara varias reconstrucciones seguidas, una por
   * canal marcado) y seguir usándolo lanzaría contra un `Renderizador` ya
   * destruido. Abortar en silencio es correcto: la reconstrucción que ganó
   * ya ha pedido su propio redibujado.
   */
  #generacion = 0;
  /** Ver la cabecera de `#preseleccionarProtagonistas`: silencia `#onSeleccionCambia` mientras dura. */
  #reconstruccionSuprimida = false;

  constructor(raiz: HTMLElement, fuente: FuenteDeDatos) {
    this.#raiz = raiz;
    this.#fuente = fuente;

    this.#raiz.textContent = "";
    this.#raiz.classList.add("dlv-app");

    this.#barra = document.createElement("div");
    this.#barra.className = "dlv-barra";
    const boton = document.createElement("button");
    boton.textContent = "Abrir log sintético";
    boton.addEventListener("click", () => void this.abrirLog("autolog-sintetico"));
    this.#estadoTexto = document.createElement("span");
    this.#estadoTexto.className = "dlv-barra__estado";
    this.#estadoTexto.textContent = `fuente: ${fuente.nombre}`;
    this.#barra.append(boton, this.#estadoTexto);

    const cuerpo = document.createElement("div");
    cuerpo.className = "dlv-cuerpo";

    this.#barraLateral = document.createElement("div");
    this.#barraLateral.className = "dlv-lateral";
    this.#contenedorSelectorCanales = document.createElement("div");
    this.#contenedorSelectorCanales.className = "dlv-lateral__canales";
    this.#contenedorSelectorUnidad = document.createElement("div");
    this.#contenedorSelectorUnidad.className = "dlv-lateral__unidades";
    this.#barraLateral.append(this.#contenedorSelectorCanales, this.#contenedorSelectorUnidad);

    this.#areaPrincipal = document.createElement("div");
    this.#areaPrincipal.className = "dlv-principal";
    this.#mensajeVacio = document.createElement("p");
    this.#mensajeVacio.className = "dlv-mensaje-vacio";
    this.#mensajeVacio.textContent = "Selecciona canales en la izquierda para verlos aquí.";
    this.#contenedorPaneles = document.createElement("div");
    this.#contenedorPaneles.className = "dlv-paneles";
    this.#areaPrincipal.append(this.#mensajeVacio, this.#contenedorPaneles);

    cuerpo.append(this.#barraLateral, this.#areaPrincipal);
    this.#raiz.append(this.#barra, cuerpo);

    window.addEventListener("resize", () => {
      this.#paneles?.redimensionarContenedor();
      for (const estado of this.#porPanel.values()) this.#reajustarLienzo(estado);
      this.#dispararRedibujado();
    });

    this.#iniciarCicloCursor();
  }

  /** Abre (o reabre) un log a través de la fuente configurada y reconstruye toda la interfaz. */
  async abrirLog(referencia: string): Promise<void> {
    this.#estadoTexto.textContent = `fuente: ${this.#fuente.nombre} · abriendo…`;
    const [log, catalogo] = await Promise.all([
      this.#fuente.abrirLog(referencia),
      this.#fuente.catalogoUnidades(),
    ]);
    this.#log = log;
    this.#catalogo = catalogo;
    this.#cache = new CacheDeCubos();
    this.#nivelesPorCanal.clear();
    this.#colorPorCanal.clear();

    this.#estadoTexto.textContent =
      `fuente: ${this.#fuente.nombre} · ${log.nombre} · ${log.canales.length} canales` +
      (log.avisos.length > 0 ? ` · ${log.avisos[0]}` : "");

    this.#construirSelectorCanales(log);
    this.#reconstruirSelectorUnidad([]);
    this.#reconstruir(null);
    this.#preseleccionarProtagonistas();
  }

  // ------------------------------------------------------------------ //
  // Selector de canales
  // ------------------------------------------------------------------ //

  #construirSelectorCanales(log: LogAbierto): void {
    this.#selectorCanales?.destruir();
    this.#contenedorSelectorCanales.textContent = "";
    const canales: CanalParaSelector[] = log.canales.map((c) => ({
      idNativo: c.idNativo,
      formato: "sintético",
      nombre: c.nombre,
      rol: c.rol,
      clasificacion: c.clasificacion,
    }));
    this.#selectorCanales = new SelectorCanales({
      contenedor: this.#contenedorSelectorCanales,
      canales,
      onSeleccionCambia: (seleccionados) => this.#onSeleccionCambia(seleccionados),
    });
  }

  /**
   * `SelectorCanales` no ofrece una forma de preseleccionar canales por
   * programa (ni `estadoInicial`, ni un atributo `data-*` por fila que
   * permita encontrar una casilla concreta desde fuera — ver el informe de
   * la tarea). Como paliativo NO invasivo (no se toca `selector-canales.ts`),
   * esto simula clics reales sobre las primeras filas: son las primeras N
   * entradas de `log.canales`, que `fuente-sintetica.ts` rellena con los
   * canales "protagonistas" en primer lugar, así que la posición es estable
   * mientras no haya filtro de búsqueda activo ni "mostrar inactivos".
   *
   * `#reconstruccionSuprimida` evita que los 8 clics disparen 8
   * reconstrucciones completas de `PanelesApilados` (una por clic, con 1, 2,
   * 3… canales): además de lento, cada reconstrucción crea un
   * `WebGL2RenderingContext` por panel y un navegador solo garantiza un
   * puñado de contextos vivos a la vez (Chrome/Edge: 16) — encadenar 8
   * reconstrucciones de tamaño creciente llegó a pedir 36 contextos y el
   * navegador empezó a descartar los más antiguos («Too many active WebGL
   * contexts», visto al verificar esta tarea con `npm run dev`). Con la
   * supresión, los 8 clics solo actualizan el estado interno de
   * `SelectorCanales`; la reconstrucción real se dispara UNA vez al final,
   * ya con los 8 canales.
   */
  #preseleccionarProtagonistas(): void {
    if (this.#selectorCanales === null) return;
    const filas = this.#contenedorSelectorCanales.querySelectorAll<HTMLLIElement>(
      ".selector-canales__fila",
    );
    const objetivo = Math.min(8, filas.length);
    this.#reconstruccionSuprimida = true;
    for (let i = 0; i < objetivo; i += 1) {
      filas[i]?.querySelector<HTMLInputElement>("input[type=checkbox]")?.click();
    }
    this.#reconstruccionSuprimida = false;
    this.#onSeleccionCambia(this.#selectorCanales.seleccionados);
  }

  // ------------------------------------------------------------------ //
  // Selector de unidad
  // ------------------------------------------------------------------ //

  #reconstruirSelectorUnidad(canalesVisibles: readonly CanalDeFuente[]): void {
    this.#contenedorSelectorUnidad.textContent = "";
    this.#resueltasUnidad.clear();
    if (this.#catalogo === null || canalesVisibles.length === 0) {
      this.#selectorUnidad = null;
      return;
    }
    const canales: CanalParaUnidad[] = canalesVisibles.map((c) => ({
      id: c.idNativo,
      etiqueta: c.nombre,
      dimensionId: c.dimensionId,
    }));
    this.#selectorUnidad = new SelectorUnidad(fabricaDesdeDocumento(document), {
      catalogo: this.#catalogo,
      canales,
      onCambio: (cambio) => {
        this.#resueltasUnidad = new Map(cambio.resueltas);
        this.#dispararRedibujado();
      },
    });
    for (const canal of canales) {
      this.#resueltasUnidad.set(canal.id, this.#selectorUnidad.unidadResueltaDe(canal.id));
    }
    (this.#selectorUnidad.elemento as unknown as HTMLElement).classList.add("selector-unidad-raiz");
    this.#contenedorSelectorUnidad.appendChild(
      this.#selectorUnidad.elemento as unknown as HTMLElement,
    );
  }

  // ------------------------------------------------------------------ //
  // Cambios de selección / arrastre entre paneles: reconstruyen los paneles
  // ------------------------------------------------------------------ //

  #onSeleccionCambia(seleccionados: ReadonlySet<string>): void {
    if (this.#reconstruccionSuprimida || this.#log === null) return;
    const canalesVisibles = this.#log.canales.filter((c) => seleccionados.has(c.idNativo));
    this.#reconstruirSelectorUnidad(canalesVisibles);
    const definiciones: DefinicionPanel[] = canalesVisibles.map((c) => ({
      id: `panel-${c.idNativo}`,
      canales: [{ id: c.idNativo, etiqueta: c.nombre }],
    }));
    this.#reconstruir(definiciones.length > 0 ? definiciones : null);
  }

  #alCambiarAsignacion(): void {
    // El arrastre ya movió el canal DENTRO de `this.#paneles`; se capturan
    // las definiciones resultantes antes de nada más, porque `#reconstruir`
    // destruye la instancia actual.
    if (this.#paneles === null) return;
    const definiciones: DefinicionPanel[] = this.#paneles
      .ordenPaneles()
      .map((id) => ({ id, canales: this.#paneles!.canalesDe(id) }))
      .filter((d) => d.canales.length > 0);
    this.#reconstruir(definiciones.length > 0 ? definiciones : null);
  }

  /**
   * Reconstruye `PanelesApilados` entera junto con el renderizador, el SVG de
   * ejes, el `GestorEscalas` y el cursor de cada panel.
   *
   * `PanelesApilados` no admite añadir ni quitar paneles tras construirse
   * (solo mover canales entre los que ya existen) y `GestorEscalas` no tiene
   * forma de renombrar la unidad de un eje ya creado — dos costuras que el
   * informe de la tarea documenta. Reconstruir entero en cada cambio de
   * selección o de unidad es la forma más simple de no pelear contra esas dos
   * API tal como están, a costa de recrear los `WebGL2RenderingContext` de
   * cada panel (barato con 8 canales, y ningún dato se vuelve a pedir: la
   * caché de cubos sobrevive a esta función porque vive en `this.#cache`, no
   * en `this.#porPanel`).
   */
  #reconstruir(definiciones: DefinicionPanel[] | null): void {
    this.#generacion += 1;
    for (const estado of this.#porPanel.values()) {
      estado.renderizador.destruir();
      estado.cursor.destruir();
      // `Renderizador.destruir()` libera programa/búferes pero no el propio
      // `WebGL2RenderingContext` (no es suyo: lo recibió ya creado, ver la
      // cabecera de `render/contexto.ts`). Un navegador solo garantiza un
      // puñado de contextos WebGL vivos a la vez (Chrome/Edge: 16); perderlo
      // explícitamente aquí es lo que evita agotarlos en una sesión con
      // muchos cambios de selección o de unidad (cada uno reconstruye todos
      // los paneles — ver el porqué más abajo).
      estado.canvas.getContext("webgl2")?.getExtension("WEBGL_lose_context")?.loseContext();
    }
    this.#porPanel.clear();
    this.#nav?.destruir();
    this.#nav = null;
    this.#paneles?.destruir();
    this.#paneles = null;
    this.#contenedorPaneles.textContent = "";

    if (definiciones === null || definiciones.length === 0 || this.#log === null) {
      this.#mensajeVacio.style.removeProperty("display");
      this.#contenedorPaneles.style.setProperty("display", "none");
      return;
    }
    this.#mensajeVacio.style.setProperty("display", "none");
    this.#contenedorPaneles.style.removeProperty("display");

    this.#paneles = PanelesApilados.montar(this.#contenedorPaneles, definiciones, {
      alCambiarAsignacion: () => this.#alCambiarAsignacion(),
      alRedimensionar: () => this.#dispararRedibujado(),
    });

    for (const definicion of definiciones) {
      this.#porPanel.set(definicion.id, this.#montarPanel(definicion));
    }

    const log = this.#log;
    this.#nav = new ControladorDeNavegacion(
      this.#contenedorPaneles,
      { t0: log.tInicio, t1: log.tFin, v0: 0, v1: 1 },
      () => this.#dispararRedibujado(),
      { limites: { t0: log.tInicio, t1: log.tFin, v0: 0, v1: 1 } },
    );

    this.#dispararRedibujado();
  }

  /** `#redibujarTodo` sin dejar una promesa suelta sin `.catch`: un fallo se avisa por consola, no se pierde en silencio. */
  #dispararRedibujado(): void {
    this.#redibujarTodo().catch((error: unknown) => {
      console.error("dlv-ui: fallo al redibujar", error);
    });
  }

  #montarPanel(definicion: DefinicionPanel): EstadoPanel {
    const contenido = this.#paneles!.contenidoDe(definicion.id) as unknown as HTMLElement;

    const canvas = document.createElement("canvas");
    canvas.style.setProperty("position", "absolute");
    canvas.style.setProperty("inset", "0");
    canvas.style.setProperty("width", "100%");
    canvas.style.setProperty("height", "100%");
    contenido.appendChild(canvas);

    const svg = document.createElementNS(NS_SVG, "svg") as SVGSVGElement;
    svg.style.setProperty("position", "absolute");
    svg.style.setProperty("inset", "0");
    svg.style.setProperty("width", "100%");
    svg.style.setProperty("height", "100%");
    svg.style.setProperty("pointer-events", "none");
    contenido.appendChild(svg);

    const tablaCursor = document.createElement("table");
    tablaCursor.className = "cursor-tabla";
    tablaCursor.style.setProperty("position", "absolute");
    // Esquina opuesta a la leyenda de `ejes.ts` (arriba-derecha, `MARGEN_LEYENDA`
    // en `ejes/ejes.ts`): las dos comparten el mismo panel y arriba-derecha ya
    // está ocupado.
    tablaCursor.style.setProperty("bottom", "4px");
    tablaCursor.style.setProperty("right", "4px");
    contenido.appendChild(tablaCursor);

    const renderizador = Renderizador.desdeLienzo(canvas);
    const gestor = new GestorEscalas();
    const primerCanal = definicion.canales[0];
    const unidadPanel = primerCanal !== undefined ? this.#unidadDe(primerCanal.id) : undefined;
    gestor.crearEje(EJE_PRINCIPAL, unidadPanel?.unidad.etiqueta ?? "");
    for (const canal of definicion.canales) gestor.asignarSerie(canal.id, EJE_PRINCIPAL);

    const cursor = new CursorDeTabla(contenido, tablaCursor, this.#cache, {
      formatear: (valor) => {
        const factor = primerCanal !== undefined ? this.#factorDeCanal(primerCanal.id) : { a: 1, b: 0 };
        return formatearNumeroLocale(convertirValor(valor, factor), unidadPanel?.unidad.decimales ?? 2);
      },
    });

    return {
      panelId: definicion.id,
      canalesIds: definicion.canales.map((c) => c.id),
      canvas,
      svg,
      tablaCursor,
      renderizador,
      gestor,
      cursor,
      ultimaSubida: new Map(),
      ultimoFactor: new Map(),
    };
  }

  #reajustarLienzo(estado: EstadoPanel): void {
    const viewport: Viewport = ajustarLienzo(estado.canvas, window.devicePixelRatio || 1);
    estado.renderizador.redimensionar(viewport);
  }

  #unidadDe(canalId: string): UnidadResuelta | undefined {
    return this.#resueltasUnidad.get(canalId);
  }

  #factorDeCanal(canalId: string): { a: number; b: number } {
    const canal = this.#log?.canales.find((c) => c.idNativo === canalId);
    const unidad = this.#unidadDe(canalId);
    if (canal === undefined || unidad === undefined) return { a: 1, b: 0 };
    return factorDe(canal.dimensionId, unidad.unidad.id);
  }

  async #nivelesDe(canalId: string): Promise<readonly ResumenNivel[]> {
    const existentes = this.#nivelesPorCanal.get(canalId);
    if (existentes !== undefined) return existentes;
    if (this.#log === null) return [];
    const niveles = await this.#fuente.nivelesDe(this.#log.logId, canalId);
    const resumen = niveles.map((n) => ({ factor: n.factor, nCubos: n.nCubos }));
    this.#nivelesPorCanal.set(canalId, resumen);
    return resumen;
  }

  // ------------------------------------------------------------------ //
  // El ciclo de dibujo
  // ------------------------------------------------------------------ //

  /**
   * Vuelve a pedir (si hace falta), subir y dibujar cada panel para la vista
   * actual del controlador de navegación. Se llama desde `alCambiar` del
   * controlador (ya limitado a un fotograma, `controlador.ts`), desde
   * `alRedimensionar` de `PanelesApilados` y tras cambiar de unidad — nunca
   * en un bucle propio, así que no hace falta otro límite de frecuencia aquí.
   *
   * `#redibujando`/`#pendienteOtraVuelta` evitan que dos llamadas
   * concurrentes (p. ej. un cambio de unidad mientras una petición de cubos
   * todavía está en vuelo) pisen el resultado la una de la otra: si llega una
   * petición nueva mientras la anterior sigue esperando datos, se anota y se
   * repite al terminar, en vez de lanzar una segunda pasada en paralelo.
   */
  async #redibujarTodo(): Promise<void> {
    if (this.#redibujando) {
      this.#pendienteOtraVuelta = true;
      return;
    }
    this.#redibujando = true;
    try {
      await this.#redibujarUnaVez();
      while (this.#pendienteOtraVuelta) {
        this.#pendienteOtraVuelta = false;
        await this.#redibujarUnaVez();
      }
    } finally {
      this.#redibujando = false;
    }
  }

  async #redibujarUnaVez(): Promise<void> {
    if (this.#nav === null || this.#paneles === null || this.#log === null) return;
    const generacion = this.#generacion;
    const log = this.#log;
    const vista = this.#nav.vista;
    const duracionLog = Math.max(log.tFin - log.tInicio, Number.MIN_VALUE);
    const fraccionVisible = (vista.t1 - vista.t0) / duracionLog;
    const anchoPx = this.#paneles.anchoContenidoPx();
    const alturasPx = this.#paneles.alturasPx();

    for (const estado of this.#porPanel.values()) {
      this.#reajustarLienzo(estado);
      const rangosVisibles = new Map<string, RangoValor | null>();
      const canalesCursor: CanalCursor[] = [];
      let factorCambio = false;

      for (const canalId of estado.canalesIds) {
        if (!this.#colorPorCanal.has(canalId)) {
          this.#colorPorCanal.set(canalId, colorPorIndice(this.#colorPorCanal.size));
        }
        const color = this.#colorPorCanal.get(canalId)!;

        const niveles = await this.#nivelesDe(canalId);
        // Una reconstrucción (`#reconstruir`) más reciente pudo destruir este
        // `estado` mientras se esperaba `nivelesDe`/`pedirCubos` (ver la nota
        // de `#generacion`): seguir usándolo lanzaría contra un renderizador
        // ya destruido, así que se abandona esta pasada entera en silencio.
        if (generacion !== this.#generacion) return;
        if (niveles.length === 0) continue;
        // `elegirNivel` devuelve un ÍNDICE dentro de `niveles`, no un factor
        // (ver `render/escala.ts`): el factor de verdad es
        // `niveles[indice].factor`. Pasar el índice directamente a
        // `pedirCubos` pedía un nivel de pirámide que no existe.
        const factor = niveles[elegirNivel(niveles, fraccionVisible, anchoPx)]!.factor;

        const rangoPedido: Rango = { t0: vista.t0, t1: vista.t1 };
        const clave: ClaveCubos = { canal: canalId, factor };
        const resultado = this.#cache.consultar(clave, rangoPedido);
        let entrada = resultado.estado === "acierto" ? resultado.entrada : undefined;
        if (entrada === undefined) {
          const pedir = resultado.estado === "fallo" ? resultado.pedir : rangoPedido;
          const cubos = await this.#fuente.pedirCubos(log.logId, canalId, pedir, factor);
          if (generacion !== this.#generacion) return;
          entrada = { cubos, cubre: pedir };
          this.#cache.guardar(clave, entrada);
        }

        const unidadResuelta = this.#unidadDe(canalId);
        const factorConv = unidadResuelta === undefined
          ? { a: 1, b: 0 }
          : factorDe(this.#dimensionDe(canalId), unidadResuelta.unidad.id);

        const claveSubida = `${factor}|${entrada.cubre.t0}|${entrada.cubre.t1}|${unidadResuelta?.unidad.id ?? ""}`;
        if (estado.ultimaSubida.get(canalId) !== claveSubida) {
          renderizadorSubir(estado.renderizador, canalId, entrada.cubos, factorConv, color);
          estado.ultimaSubida.set(canalId, claveSubida);
        }
        if (estado.ultimoFactor.get(canalId) !== factor) {
          estado.ultimoFactor.set(canalId, factor);
          factorCambio = true;
        }

        const rangoRaw = rangoVisibleDeCubos(entrada.cubos, vista);
        rangosVisibles.set(
          canalId,
          rangoRaw === null
            ? null
            : {
                min: convertirValor(rangoRaw.min, factorConv),
                max: convertirValor(rangoRaw.max, factorConv),
              },
        );

        canalesCursor.push({ clave, etiqueta: canalId });
      }

      estado.gestor.actualizar(rangosVisibles);
      const vistaPorSerie = estado.gestor.vistaPorSerie({ t0: vista.t0, t1: vista.t1 });
      estado.renderizador.dibujar({ t0: vista.t0, t1: vista.t1, v0: 0, v1: 1 }, vistaPorSerie);

      if (factorCambio) estado.cursor.actualizarCanales(canalesCursor);

      const ejeEstado = estado.gestor.eje(EJE_PRINCIPAL);
      const altoPanel = alturasPx.get(estado.panelId) ?? 0;
      pintarEjes(estado.svg, {
        vista: { t0: vista.t0, t1: vista.t1, v0: ejeEstado.rango.min, v1: ejeEstado.rango.max },
        anchoPx,
        altoPx: altoPanel,
        unidadY: ejeEstado.unidad,
        tituloY: tituloConModo(ejeEstado),
        series: estado.canalesIds.map((id) => ({
          id,
          nombre: id,
          color: this.#colorPorCanal.get(id) ?? { r: 1, g: 1, b: 1, a: 1 },
          unidad: ejeEstado.unidad,
        })),
      });
    }
  }

  #dimensionDe(canalId: string): string {
    return this.#log?.canales.find((c) => c.idNativo === canalId)?.dimensionId ?? "unknown";
  }

  // ------------------------------------------------------------------ //
  // Cursor: `mover()` es barato (cursor.ts lo pide así), `aplicar()` se llama
  // desde un bucle propio de `requestAnimationFrame`, separado del redibujado
  // por navegación — es exactamente la separación que `cursor.ts` documenta
  // en su cabecera («mover() no toca el DOM; aplicar() lo hace, como mucho
  // una vez por fotograma, y lo llama el bucle de dibujo del panel»).
  // ------------------------------------------------------------------ //

  /**
   * El cursor se mueve en TODOS los paneles a la vez, a la misma `x`, no solo
   * en el que está bajo el ratón: es lo que permite leer causa y efecto entre
   * canales apilados (un pico de detonación contra la posición del
   * acelerador, en el ejemplo de `paneles.ts`) — un cursor que solo aparece
   * en el panel bajo el puntero no sirve para comparar dos canales a la vez.
   * Como todos los paneles comparten el mismo `anchoContenidoPx` y arrancan
   * en el mismo borde izquierdo (la garantía central de `PanelesApilados`,
   * ver su cabecera), la `x` se calcula una sola vez contra el contenedor
   * raíz y vale para todos.
   */
  #iniciarCicloCursor(): void {
    const sobreMovimiento = (evento: PointerEvent): void => {
      if (this.#paneles === null || this.#nav === null) return;
      const rect = this.#contenedorPaneles.getBoundingClientRect();
      const xLocal = evento.clientX - rect.left;
      if (xLocal < 0 || xLocal > rect.width) {
        for (const estado of this.#porPanel.values()) estado.cursor.ocultar();
        return;
      }
      const vista = this.#nav.vista;
      const anchoPx = this.#paneles.anchoContenidoPx();
      const fraccion = anchoPx > 0 ? xLocal / anchoPx : 0;
      const tAbsoluto = vista.t0 + fraccion * (vista.t1 - vista.t0);
      for (const estado of this.#porPanel.values()) estado.cursor.mover(tAbsoluto, xLocal);
    };
    this.#areaPrincipal.addEventListener("pointermove", sobreMovimiento);
    this.#areaPrincipal.addEventListener("pointerleave", () => {
      for (const estado of this.#porPanel.values()) estado.cursor.ocultar();
    });

    const paso = (): void => {
      for (const estado of this.#porPanel.values()) estado.cursor.aplicar();
      this.#idFrameCursor = requestAnimationFrame(paso);
    };
    this.#idFrameCursor = requestAnimationFrame(paso);
  }

  /** Libera temporizadores y listeners globales. Útil para pruebas manuales en la consola. */
  destruir(): void {
    if (this.#idFrameCursor !== null) cancelAnimationFrame(this.#idFrameCursor);
    this.#reconstruir(null);
  }
}

/** Sube una serie ya convertida a la unidad activa. Función libre para no ensuciar el método de arriba. */
function renderizadorSubir(
  renderizador: Renderizador,
  canalId: string,
  cubos: CubosContinuos,
  factor: { a: number; b: number },
  color: Color,
): void {
  renderizador.subirSerie(canalId, convertirCubos(cubos, factor), color);
}
