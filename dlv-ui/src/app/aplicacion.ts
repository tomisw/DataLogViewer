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
import {
  deltaDeTiempo,
  deltaEntre,
  leerEn,
  textoDeDelta,
  type FormaConversion,
} from "../cursor/doble.ts";
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
import { elegirProtagonistas } from "../canales/protagonistas.ts";
import type { CanalInfo as CanalParaSelector } from "../canales/tipos.ts";
import { fabricaDesdeDocumento } from "../unidades/dom.ts";
import { SelectorUnidad } from "../unidades/selector-unidad.ts";
import type {
  CanalInfo as CanalParaUnidad,
  CatalogoUnidades,
  UnidadResuelta,
} from "../unidades/tipos.ts";
import {
  convertirCubos,
  convertirDesdeCrudo,
  IDENTIDAD,
  type Conversion,
  type ConversionAfin,
} from "../unidades/conversion.ts";
import { SelectorCombustible } from "../combustible/selector-combustible.ts";
import { fabricaDesdeDocumento as fabricaCombustible } from "../combustible/dom.ts";
import { alCambiarTema, obtenerTemaActual, parametrosDeSerie } from "../tema/tema.ts";
import { montarSelectorDeTema } from "../tema/selector-tema.ts";

const EJE_PRINCIPAL = "principal";

const MAXIMO_PROTAGONISTAS = 8;

/**
 * Con qué canales se abre un log, por rol semántico y en orden de preferencia
 * (`#preseleccionarProtagonistas`).
 *
 * ES UN VALOR POR OMISIÓN, NO UNA AFIRMACIÓN SOBRE EL MOTOR
 * ========================================================
 * Ocho canales de entre varios cientos es una elección, y ninguna elección
 * sirve para todos los coches. Esta es la de «qué mira alguien en los primeros
 * cinco segundos de abrir una tirada»: a qué régimen iba, cuánta presión daba,
 * cuánto gas, cómo iba de mezcla, y las tres temperaturas/presiones que hacen
 * abortar una sesión. Se cambia marcando y desmarcando casillas, sin tocar
 * código.
 *
 * NO vive en `data/roles.toml` aunque nombre roles suyos: ese fichero es una
 * puerta G1 y describe QUÉ ES cada rol (dimensión, rango plausible, si algún
 * detector crítico depende de él), no cuáles se enseñan primero. Añadirle un
 * campo de presentación mezclaría las dos cosas y metería una decisión de
 * interfaz en un fichero que se revisa por sus consecuencias físicas.
 *
 * Un rol que este log no tenga simplemente no aparece; ver el repliegue a
 * «primeros canales activos» en `#preseleccionarProtagonistas`.
 */
const ORDEN_PROTAGONISTAS: readonly string[] = [
  "engine_speed",
  "manifold_pressure",
  "throttle_position",
  "lambda_measured",
  "coolant_temp",
  "oil_pressure",
  "intake_air_temp",
  "battery_voltage",
  "boost_pressure_actual",
  "ignition_advance",
  "injector_duty",
  "vehicle_speed",
];

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

/**
 * Paleta por índice de canal: matiz con separación de ángulo áureo, y saturación
 * y luz según el tema activo (F3-21).
 *
 * Los parámetros del tema salen de `tema.parametrosDeSerie`, el mismo sitio del
 * que los toma `carriles/color.ts`: son dos funciones distintas por capas —esta
 * reparte por índice de canal y aquella por código de estado— pero la respuesta
 * a «cómo se ve una serie en este tema» tiene que ser una sola.
 */
function colorPorIndice(indice: number): Color {
  const matiz = (indice * 137.508) % 360; // ángulo áureo: buena dispersión sin tabla fija
  const { saturacion, luz } = parametrosDeSerie(indice);
  const { r, g, b } = hslARgb(matiz, saturacion, luz);
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
  readonly #barraDelta: HTMLElement;
  readonly #barraLateral: HTMLElement;
  readonly #contenedorSelectorCanales: HTMLElement;
  readonly #contenedorSelectorUnidad: HTMLElement;
  readonly #contenedorSelectorCombustible: HTMLElement;
  readonly #areaPrincipal: HTMLElement;
  readonly #contenedorPaneles: HTMLElement;
  readonly #mensajeVacio: HTMLElement;

  #log: LogAbierto | null = null;
  #catalogo: CatalogoUnidades | null = null;
  #cache = new CacheDeCubos();
  #nivelesPorCanal = new Map<string, readonly ResumenNivel[]>();

  #selectorCanales: SelectorCanales | null = null;
  #selectorUnidad: SelectorUnidad | null = null;
  #selectorCombustible: SelectorCombustible | null = null;
  #resueltasUnidad = new Map<string, UnidadResuelta>();

  #paneles: PanelesApilados | null = null;
  #nav: ControladorDeNavegacion | null = null;
  #porPanel = new Map<string, EstadoPanel>();
  #colorPorCanal = new Map<string, Color>();

  /**
   * Instante del cursor móvil y del ancla del doble cursor (E3.4), en segundos
   * absolutos. `#tAncla` es `null` mientras no se haya fijado con un clic, y
   * entonces la barra de Δ está vacía: un Δ contra un ancla que el usuario no
   * ha puesto sería un número sin pregunta detrás.
   */
  #tCursor: number | null = null;
  #tAncla: number | null = null;

  #idFrameCursor: number | null = null;
  #redibujando = false;
  #pendienteOtraVuelta = false;
  /**
   * Se incrementa en cada `#reconstruir()`. `#redibujarUnaVez` la comprueba
   * tras cada `await`: si cambió mientras esperaba datos, el `EstadoPanel`
   * que tiene en la mano puede haber sido destruido entre medias (marcar un
   * canal mientras se está pidiendo el nivel de otro basta) y seguir usándolo
   * lanzaría contra un `Renderizador` ya destruido. Abortar en silencio es
   * correcto: la reconstrucción que ganó ya ha pedido su propio redibujado.
   */
  #generacion = 0;

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
    this.#barra.append(boton, montarSelectorDeTema(), this.#estadoTexto);

    this.#barraDelta = document.createElement("div");
    this.#barraDelta.className = "dlv-barra-delta";
    this.#barraDelta.title =
      "Doble cursor: haz clic sobre los paneles para fijar el ancla, y otro clic para quitarla.";

    // El color de una serie se calcula en TypeScript y se sube a la GPU, así que
    // cambiar el tema no lo toca: hay que olvidar los colores cacheados y volver
    // a pintar. Sin esto, cambiar a alto contraste reteñía la interfaz y dejaba
    // las curvas con los colores del tema anterior.
    alCambiarTema(() => {
      this.#colorPorCanal.clear();
      this.#dispararRedibujado();
    });

    const cuerpo = document.createElement("div");
    cuerpo.className = "dlv-cuerpo";

    this.#barraLateral = document.createElement("div");
    this.#barraLateral.className = "dlv-lateral";
    this.#contenedorSelectorCanales = document.createElement("div");
    this.#contenedorSelectorCanales.className = "dlv-lateral__canales";
    this.#contenedorSelectorUnidad = document.createElement("div");
    this.#contenedorSelectorUnidad.className = "dlv-lateral__unidades";
    this.#contenedorSelectorCombustible = document.createElement("div");
    this.#contenedorSelectorCombustible.className = "dlv-lateral__combustible";
    this.#barraLateral.append(
      this.#contenedorSelectorCanales,
      this.#contenedorSelectorUnidad,
      this.#contenedorSelectorCombustible,
    );

    this.#areaPrincipal = document.createElement("div");
    this.#areaPrincipal.className = "dlv-principal";
    this.#mensajeVacio = document.createElement("p");
    this.#mensajeVacio.className = "dlv-mensaje-vacio";
    this.#mensajeVacio.textContent = "Selecciona canales en la izquierda para verlos aquí.";
    this.#contenedorPaneles = document.createElement("div");
    this.#contenedorPaneles.className = "dlv-paneles";
    this.#areaPrincipal.append(this.#mensajeVacio, this.#contenedorPaneles);

    cuerpo.append(this.#barraLateral, this.#areaPrincipal);
    this.#raiz.append(this.#barra, this.#barraDelta, cuerpo);

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
      // El nombre de la FUENTE, no la palabra "sintético" cableada: con un log
      // real el selector decía "sintético" en cada una de las 475 filas, que es
      // exactamente la clase de repliegue silencioso a datos falsos que
      // `main.ts` se molesta en no hacer.
      formato: this.#fuente.nombre,
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
   * Deja marcados los canales con los que merece la pena abrir el log.
   *
   * POR QUÉ NO VALE «LOS OCHO PRIMEROS»
   * ===================================
   * Eso es lo que hacía antes, y funcionaba con `FuenteSintetica` porque esa
   * fuente pone los canales interesantes al principio de la lista. Sobre un
   * log real de Haltech es un desastre silencioso: las primeras columnas del
   * fichero son diagnósticos de arranque de la ECU —`Bootmode Reason`,
   * `Reset Required`, `Memory Writes Pending`, tres errores de referencia de
   * tensión—, y tres de los ocho son una línea recta. El log se abría
   * perfectamente y la ventana parecía vacía.
   *
   * El criterio ahora es el ROL SEMÁNTICO (`dlv_core.roles`, FG-09), que es
   * justamente la indirección que existe para no tener que nombrar «la
   * columna 197 de Haltech». `ORDEN_PROTAGONISTAS` dice en qué orden se
   * prefieren.
   *
   * LO QUE NO SE ACEPTA COMO PROTAGONISTA
   * ====================================
   * - Un rol de confianza `DIFUSA`: es un parecido de cadenas por encima de un
   *   umbral (docs/07 §7.15). Como protagonista, un falso positivo pone en
   *   pantalla un canal que no es el que dice ser, y eso es peor que enseñar
   *   uno menos.
   * - Un canal `vacio` o `constante`: dibuja una recta o nada. Que exista un
   *   rol `oil_pressure` no significa que ese sensor estuviera conectado en
   *   esta tirada.
   *
   * Si tras filtrar no quedan ocho, se rellena con los primeros canales
   * ACTIVOS de la lista. Es el mismo criterio de antes pero sin las rectas: un
   * repliegue que enseña algo real, en vez de una ventana en blanco cuando el
   * catálogo de roles no reconoce el formato (un CSV genérico, docs/07).
   */
  #preseleccionarProtagonistas(): void {
    if (this.#selectorCanales === null || this.#log === null) return;
    this.#selectorCanales.preseleccionar(
      elegirProtagonistas(this.#log.canales, ORDEN_PROTAGONISTAS, MAXIMO_PROTAGONISTAS),
    );
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

  /**
   * Monta el selector de combustible si hay algún canal cuya unidad activa use
   * una conversión `parametrizada` — hoy, λ→AFR.
   *
   * POR QUÉ APARECE Y DESAPARECE
   * ============================
   * Es el único control de la barra lateral que solo tiene sentido a veces: si
   * ningún panel muestra la sonda lambda en AFR, la estequiometría no afecta a
   * nada de lo que hay en pantalla, y un desplegable que no cambia nada invita
   * a tocarlo y a concluir que la aplicación no responde. Al cambiar la sonda a
   * AFR aparece; al volver a λ, desaparece.
   *
   * El catálogo viene de `data/combustibles.toml` por HTTP, no de este código.
   */
  #reconstruirSelectorCombustible(): void {
    const hace = this.#log?.canales.some(
      (c) => this.#conversionDe(c.idNativo).tipo === "parametrizada",
    );
    this.#contenedorSelectorCombustible.textContent = "";
    if (hace !== true || this.#catalogo === null || this.#catalogo.combustibles.length === 0) {
      this.#selectorCombustible = null;
      return;
    }
    // Fábrica de DOM propia: la de `combustible/dom.ts` expone `crearInput`,
    // que el campo de estequiometría manual necesita y la de `unidades/dom.ts`
    // no tiene. Cada componente declara la superficie mínima que usa (ese es el
    // patrón que permite probarlos sin jsdom), así que no comparten fábrica.
    this.#selectorCombustible = new SelectorCombustible(fabricaCombustible(document), {
      catalogo: this.#catalogo.combustibles,
      // Sin `estequiometriaDelLog`: leerla exige pedir la serie del canal de
      // rol `stoichiometry` para pintar OTRO canal, y ese camino (una serie que
      // alimenta la conversión de otra) es trabajo de F3. Mientras tanto el
      // selector marca el factor como SUPUESTO, que es justo la señal que
      // distingue un AFR fiable de uno que no lo es.
      onCambio: () => this.#dispararRedibujado(),
    });
    this.#contenedorSelectorCombustible.appendChild(
      this.#selectorCombustible.elemento as unknown as HTMLElement,
    );
  }

  // ------------------------------------------------------------------ //
  // Cambios de selección / arrastre entre paneles: reconstruyen los paneles
  // ------------------------------------------------------------------ //

  #onSeleccionCambia(seleccionados: ReadonlySet<string>): void {
    if (this.#log === null) return;
    const canalesVisibles = this.#log.canales.filter((c) => seleccionados.has(c.idNativo));
    this.#reconstruirSelectorUnidad(canalesVisibles);
    this.#reconstruirSelectorCombustible();
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
        // El cursor lee un valor puntual de la serie, así que clase `punto`:
        // con el desplazamiento de origen incluido. Es lo contrario del Δ del
        // doble cursor, que es `intervalo`.
        if (primerCanal === undefined) return formatearNumeroLocale(valor, 2);
        return formatearNumeroLocale(
          convertirDesdeCrudo(
            valor,
            this.#aCanonicaDe(primerCanal.id),
            this.#conversionDe(primerCanal.id),
            "punto",
            this.#parametroDe(primerCanal.id),
          ),
          unidadPanel?.unidad.decimales ?? 2,
        );
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

  /**
   * La conversión activa de un canal: la de la unidad que el selector resolvió
   * para él, tal como la sirve `data/units.toml`.
   *
   * `IDENTIDAD` cuando todavía no hay unidad resuelta (el catálogo no ha
   * llegado, o el canal es de una dimensión sin unidades). No es un repliegue
   * silencioso como el de antes: la identidad aquí significa «este canal se
   * muestra en canónica», que es lo que el selector está enseñando.
   */
  #conversionDe(canalId: string): Conversion {
    return this.#unidadDe(canalId)?.unidad.conversion ?? IDENTIDAD;
  }

  /**
   * El `to_canon` del canal: de la muestra cruda del log a canónica.
   *
   * Es el primer paso de los dos que hay que dar, y el que llevaba sin darse:
   * los cubos que sirve `/comandos/cubos` salen de la pirámide, que se
   * construye sobre `serie.v` —enteros escalados— y no sobre canónica. Ver
   * `unidades/conversion.ts#convertirDesdeCrudo`.
   */
  #aCanonicaDe(canalId: string): ConversionAfin {
    const canal = this.#log?.canales.find((c) => c.idNativo === canalId);
    if (canal === undefined) return IDENTIDAD;
    return { tipo: "afin", a: canal.aCanonica.a, b: canal.aCanonica.b };
  }

  /**
   * El parámetro de una conversión `parametrizada`, o `undefined`.
   *
   * Hoy solo existe un caso: λ→AFR necesita la estequiometría del combustible
   * (`docs/06` §6.6). Sale del selector de combustible, que es lo que el
   * propietario pidió poder cambiar a mano. Un log que traiga el canal con rol
   * `stoichiometry` lo usaría con preferencia, pero eso exige leer una serie
   * para pintar otra —trabajo de F3— así que hoy manda el selector, y su valor
   * por omisión es el del catálogo, no una cifra escrita aquí.
   */
  #parametroDe(canalId: string): number | undefined {
    const conversion = this.#conversionDe(canalId);
    if (conversion.tipo !== "parametrizada") return undefined;
    return this.#selectorCombustible?.factorResuelto.estequiometria;
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
        const conversion = this.#conversionDe(canalId);
        const parametro = this.#parametroDe(canalId);
        const aCanonica = this.#aCanonicaDe(canalId);

        // El tema entra en la clave porque el COLOR va en la misma subida a la
        // GPU que los datos: sin él, un cambio de tema no volvía a subir nada y
        // las curvas se quedaban con el color del tema anterior aunque el resto
        // de la interfaz ya hubiera cambiado. La clave tiene que nombrar todo lo
        // que `renderizadorSubir` mete en la GPU, no solo los datos — y por eso
        // el parámetro de estequiometría también entra: cambiar de gasolina a
        // E85 no cambia la unidad (sigue siendo AFR), pero sí todos los valores
        // subidos. Sin él, elegir E85 no repintaba nada.
        const claveSubida = `${factor}|${entrada.cubre.t0}|${entrada.cubre.t1}|${unidadResuelta?.unidad.id ?? ""}|${parametro ?? ""}|${obtenerTemaActual()}`;
        if (estado.ultimaSubida.get(canalId) !== claveSubida) {
          renderizadorSubir(
            estado.renderizador,
            canalId,
            entrada.cubos,
            aCanonica,
            conversion,
            parametro,
            color,
          );
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
            : rangoConvertido(rangoRaw, aCanonica, conversion, parametro),
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
      this.#tCursor = tAbsoluto;
      for (const estado of this.#porPanel.values()) estado.cursor.mover(tAbsoluto, xLocal);
    };
    this.#areaPrincipal.addEventListener("pointermove", sobreMovimiento);
    this.#areaPrincipal.addEventListener("pointerleave", () => {
      for (const estado of this.#porPanel.values()) estado.cursor.ocultar();
    });

    // Clic = poner o quitar el ancla del doble cursor (E3.4). Se elige el clic
    // y no una tecla porque el cursor ya sigue al puntero: el gesto natural es
    // «fija aquí y muévete», y no hace falta explicarlo.
    this.#contenedorPaneles.addEventListener("click", () => {
      this.#tAncla = this.#tAncla === null ? this.#tCursor : null;
      this.#pintarDeltas();
    });

    const paso = (): void => {
      for (const estado of this.#porPanel.values()) estado.cursor.aplicar();
      this.#pintarDeltas();
      this.#idFrameCursor = requestAnimationFrame(paso);
    };
    this.#idFrameCursor = requestAnimationFrame(paso);
  }

  /**
   * Escribe la barra de Δ: Δt y, por canal visible, el Δ de valor.
   *
   * TRES RESULTADOS DISTINTOS, Y NINGUNO FINGE SER OTRO
   * ===================================================
   * `deltaEntre` (F1-30) distingue un Δ exacto de un Δ que es un RANGO —porque
   * a zoom alejado cada cubo agrega muchas muestras y los dos extremos no son
   * lecturas, son intervalos— y de un Δ que no existe. Esta barra escribe los
   * tres tal cual: «Δ 10,0 °C», «Δ 8,0 … 12,0 °C» o «—» con el motivo. Redondear
   * el segundo caso a un número sería inventarse una precisión que el nivel de
   * pirámide no tiene.
   *
   * El Δ de un canal en una unidad recíproca (φ) sale indefinido, y eso es la
   * respuesta correcta: `a/x` no es lineal y la diferencia de dos valores
   * convertidos no es la conversión de la diferencia.
   */
  #pintarDeltas(): void {
    if (this.#tAncla === null || this.#tCursor === null || this.#log === null) {
      if (this.#barraDelta.textContent !== "") this.#barraDelta.textContent = "";
      return;
    }
    const partes: string[] = [
      `Δt ${formatearNumeroLocale(deltaDeTiempo(this.#tAncla, this.#tCursor), 3)} s`,
    ];
    for (const estado of this.#porPanel.values()) {
      for (const canalId of estado.canalesIds) {
        const factor = estado.ultimoFactor.get(canalId);
        if (factor === undefined) continue;
        const clave: ClaveCubos = { canal: canalId, factor };
        const conversion = this.#conversionDe(canalId);
        const parametro = this.#parametroDe(canalId);
        const unidad = this.#unidadDe(canalId)?.unidad;
        // Los dos extremos se leen en CANÓNICA y se convierten aquí como
        // `intervalo`: solo la parte lineal. Es la regla 4 aplicada donde de
        // verdad importa.
        const delta = deltaEntre(
          leerEn(this.#cache, clave, this.#tAncla, parametro),
          leerEn(this.#cache, clave, this.#tCursor, parametro),
          formaConversion(conversion),
        );
        const texto = textoDeDelta(
          delta,
          (v) =>
            formatearNumeroLocale(
              // `intervalo`: los dos desplazamientos de origen quedan fuera, el
              // del canal y el de la unidad.
              convertirDesdeCrudo(
                v,
                this.#aCanonicaDe(canalId),
                conversion,
                "intervalo",
                parametro,
              ),
              unidad?.decimales ?? 2,
            ),
          unidad?.etiqueta ?? "",
        );
        const nombre = this.#log.canales.find((c) => c.idNativo === canalId)?.nombre ?? canalId;
        partes.push(`${nombre}: ${texto.texto}${texto.nota ? " ⚠" : ""}`);
      }
    }
    const nuevo = partes.join("  ·  ");
    if (this.#barraDelta.textContent !== nuevo) this.#barraDelta.textContent = nuevo;
  }

  /** Libera temporizadores y listeners globales. Útil para pruebas manuales en la consola. */
  destruir(): void {
    if (this.#idFrameCursor !== null) cancelAnimationFrame(this.#idFrameCursor);
    this.#reconstruir(null);
  }
}

/**
 * Traduce la conversión del catálogo a lo que `cursor/doble.ts` necesita saber.
 *
 * Ese módulo pide adrede MENOS de lo que hay: de una afín recibe solo el factor
 * `a`, nunca el desplazamiento `b`. No es una simplificación, es el mecanismo:
 * si `b` no está en la estructura, no se puede aplicar a un Δ ni por descuido,
 * y la trampa del delta —convertir Δ10 K en −263,15 °C— deja de ser posible por
 * construcción en vez de por acordarse. Este adaptador es el único punto donde
 * `b` se descarta a propósito, y por eso está aquí y no dentro de `doble.ts`.
 */
function formaConversion(conversion: Conversion): FormaConversion {
  switch (conversion.tipo) {
    case "afin":
      return { tipo: "afin", factor: conversion.a };
    case "reciproca":
      return { tipo: "reciproca" };
    case "parametrizada":
      return {
        tipo: "parametrizada",
        factor: conversion.aPorOmision,
        parametroRol: conversion.parametroRol,
      };
  }
}

/** Sube una serie ya convertida a la unidad activa. Función libre para no ensuciar el método de arriba. */
function renderizadorSubir(
  renderizador: Renderizador,
  canalId: string,
  cubos: CubosContinuos,
  aCanonica: ConversionAfin,
  conversion: Conversion,
  parametro: number | undefined,
  color: Color,
): void {
  renderizador.subirSerie(
    canalId,
    convertirCubos(cubos, aCanonica, conversion, parametro),
    color,
  );
}

/**
 * El rango visible de un canal, en la unidad activa.
 *
 * Los dos extremos son valores puntuales, así que clase `punto`. El orden se
 * recompone después de convertir porque una conversión recíproca lo invierte
 * (`a/x` es decreciente): sin esto, el eje de un canal en φ saldría con `min`
 * por encima de `max` y la autoescala calcularía una altura negativa.
 */
function rangoConvertido(
  rango: RangoValor,
  aCanonica: ConversionAfin,
  conversion: Conversion,
  parametro: number | undefined,
): RangoValor {
  const a = convertirDesdeCrudo(rango.min, aCanonica, conversion, "punto", parametro);
  const b = convertirDesdeCrudo(rango.max, aCanonica, conversion, "punto", parametro);
  return { min: Math.min(a, b), max: Math.max(a, b) };
}
