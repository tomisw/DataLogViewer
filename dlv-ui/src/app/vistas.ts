/**
 * `ConmutadorDeVistas`: el punto de extensión que le faltaba a `app/`
 * (docs/02 §2.10, "Y que se pueda llegar a ello desde la aplicación").
 *
 * EL PROBLEMA QUE ESTO RESUELVE
 * ==============================
 * Hasta esta tarea, `main.ts` montaba `Aplicacion` -la vista de series- YA
 * COMO SI FUERA la aplicación entera: sin barra de pestañas, sin sitio donde
 * enchufar otra vista, y con TODA la lógica de abrir un log y pintar cubos
 * mezclada con la de "esto es lo único que se puede mirar". Trece módulos de
 * `dlv-ui` —`carriles`, `comparacion`, `encendido`, `exportar`,
 * `importacion`, `incidencias`, `informe`, `knock`, `lambda`, `malla`,
 * `paralela`, `perfiles`, `topes`— quedaron construidos, probados y sin
 * ningún sitio real donde montarse. Este fichero es ESE sitio.
 *
 * CÓMO SE AÑADE LA SIGUIENTE VISTA
 * ==================================
 * 1. Escribe una `DefinicionVista`: un `id` estable (no se repite con
 *    ninguna otra), una `etiqueta` para el botón de la pestaña, y
 *    `montar(contenedor, contexto, opciones)`, que construye tu módulo
 *    DENTRO de `contenedor` (un `<div>` vacío que este fichero ya insertó en
 *    el DOM) y devuelve un `VistaMontada`.
 * 2. `VistaMontada.desmontar()` tiene que liberar TODO lo que `montar`
 *    reservó: oyentes puestos en `window`/`document` (no en `contenedor` ni
 *    en sus hijos: esos se los lleva el conmutador al descartar el `<div>`),
 *    temporizadores (`setInterval`/`requestAnimationFrame` propios) y, si tu
 *    vista usa WebGL, sus contextos. `vista-series.ts#crearVistaSeries` es el
 *    ejemplo de referencia: su `desmontar()` es literalmente
 *    `aplicacion.destruir()`.
 * 3. Registra tu `DefinicionVista` en la lista que arma `main.ts`
 *    (`crearConmutador`). El conmutador no necesita saber nada más de tu
 *    vista: ni su tipo, ni de dónde saca sus datos, ni si usa WebGL.
 * 4. Si tu vista necesita llevar la de series a un instante concreto -como
 *    hace `incidencias` con el botón "Saltar", ver `vista-incidencias.ts`-
 *    usa el `ContextoDeVistas` que te llega como segundo argumento de
 *    `montar`: `contexto.irAVista(ID_VISTA_SERIES, { instanteS })`.
 *
 * POR QUÉ MONTAR/DESMONTAR POR COMPLETO, Y NO OCULTAR CON CSS
 * ================================================================
 * Un navegador solo garantiza un puñado de contextos WebGL2 vivos a la vez
 * (`app/aplicacion.ts` ya lo documentaba para sus paneles: Chrome/Edge, 16).
 * Si la vista de series se limitara a esconderse con `display: none` al
 * conmutar, sus contextos seguirían vivos y contando para ese tope aunque no
 * se vieran — exactamente el problema que tendría una futura vista de mapas
 * (`malla` + `lambda` + `knock` + `encendido` + `comparacion`, docs/02) si
 * quisiera abrir los suyos propios mientras la de series sigue "viva" de
 * fondo sin que nadie la mire. Por eso el ciclo es siempre MONTAR -> usar ->
 * DESMONTAR POR COMPLETO, nunca ocultar; y por eso cada conmutación crea un
 * `<div>` contenedor nuevo y descarta el anterior entero, en vez de
 * reutilizarlo.
 *
 * OJO CON `?.` Y UN MÉTODO AUSENTE
 * ===================================
 * `app/aplicacion.ts` libera sus contextos con
 * `canvas.getContext("webgl2")?.getExtension("WEBGL_lose_context")?.loseContext()`.
 * Ese `?.` protege el OBJETO que devuelve `getContext` (que sí puede ser
 * `null`), NO un método que ese objeto no tenga: un doble de pruebas sin
 * `getExtension` (como era `render/doble-gl.ts` antes de esta tarea) hace
 * que esa línea lance `TypeError` en cuanto se ejecuta bajo `vitest`, no
 * bajo un navegador. `doble-gl.ts` ya lo implementa ahora (ver su cabecera);
 * cualquier vista nueva que use WebGL y quiera un doble de pruebas para su
 * propio ciclo de desmontaje puede apoyarse en el mismo.
 *
 * QUÉ SE PIERDE AL CONMUTAR, A PROPÓSITO
 * =========================================
 * Un desmontaje de verdad de la vista de series significa que, al volver a
 * ella, se abre desde cero: mismo log y misma fuente, pero selección de
 * canales por omisión, unidades por omisión y encuadre completo — no
 * conserva el zoom ni la selección de la visita anterior. No es un descuido:
 * "pausar y reanudar" el MISMO contexto WebGL2 (en vez de crear uno nuevo)
 * no es lo que ofrece `WEBGL_lose_context` -pensada para perder un contexto
 * para siempre, no para congelarlo- y forzarlo habría significado inventar
 * un mecanismo de restauración que este proyecto no tiene en ningún otro
 * sitio y que no se puede probar sin GPU. Conservar el encuadre entre
 * visitas, si hace falta, es una tarea aparte.
 */

export interface OpcionesActivacion {
  /**
   * Segundos absolutos (`render/tipos.ts#Vista`) a los que debe saltar la
   * vista de series al activarse. Hoy es el único caso de uso
   * (`vista-incidencias.ts`); una vista que no lo entienda simplemente lo
   * ignora.
   */
  readonly instanteS?: number;
}

export interface VistaMontada {
  /**
   * Libera TODO lo que `montar` reservó fuera de `contenedor` mismo: ver la
   * cabecera del módulo, sección 2.
   */
  desmontar(): void;
}

/** Lo que una vista puede pedirle al conmutador. Hoy solo cambiar de vista activa. */
export interface ContextoDeVistas {
  /**
   * Cambia la vista activa a `id`. No-op si `id` ya es la activa y no se
   * pasan `opciones` (evita remontar sin motivo si el usuario pulsa la
   * pestaña en la que ya está).
   */
  irAVista(id: string, opciones?: OpcionesActivacion): void;
}

export interface DefinicionVista {
  readonly id: string;
  readonly etiqueta: string;
  montar(
    contenedor: HTMLElement,
    contexto: ContextoDeVistas,
    opciones: OpcionesActivacion,
  ): VistaMontada;
}

/**
 * Construye un `<div>` de relleno flexible: lo usan tanto el contenedor de
 * contenido como el `<div>` de cada vista montada, que siempre tienen que
 * ocupar el resto del alto disponible bajo la barra de pestañas.
 */
function crearRelleno(documento: Pick<Document, "createElement">): HTMLElement {
  const div = documento.createElement("div");
  div.style.setProperty("flex", "1 1 auto");
  div.style.setProperty("min-height", "0");
  div.style.setProperty("display", "flex");
  div.style.setProperty("flex-direction", "column");
  return div;
}

/**
 * La barra de pestañas y el contenedor de contenido, con el ciclo de
 * montar/desmontar de la cabecera del módulo.
 *
 * Nunca hay dos vistas montadas a la vez: `irAVista` desmonta la activa
 * ANTES de montar la nueva, así que el peor caso de contextos WebGL vivos
 * simultáneos es el de UNA vista, nunca la suma de todas las registradas.
 */
export class ConmutadorDeVistas implements ContextoDeVistas {
  readonly #documento: Pick<Document, "createElement">;
  readonly #vistas: readonly DefinicionVista[];
  readonly #contenido: HTMLElement;
  readonly #botones = new Map<string, HTMLButtonElement>();
  #activa: { readonly id: string; readonly montada: VistaMontada } | null = null;

  constructor(
    raiz: HTMLElement,
    documento: Pick<Document, "createElement">,
    vistas: readonly DefinicionVista[],
  ) {
    if (vistas.length === 0) {
      throw new Error("ConmutadorDeVistas: hace falta al menos una vista registrada");
    }
    this.#documento = documento;
    this.#vistas = vistas;

    const barra = documento.createElement("div");
    barra.className = "dlv-vistas";
    barra.style.setProperty("display", "flex");
    barra.style.setProperty("gap", "4px");
    barra.style.setProperty("padding", "6px 12px");
    barra.style.setProperty("background", "var(--panel)");
    barra.style.setProperty("border-bottom", "1px solid var(--panel-borde)");

    for (const vista of vistas) {
      const boton = documento.createElement("button");
      boton.type = "button";
      boton.textContent = vista.etiqueta;
      boton.className = "dlv-vistas__boton";
      boton.style.setProperty("background", "transparent");
      boton.style.setProperty("color", "var(--texto)");
      boton.style.setProperty("border", "1px solid var(--panel-borde)");
      boton.style.setProperty("border-radius", "4px");
      boton.style.setProperty("padding", "4px 10px");
      boton.style.setProperty("cursor", "pointer");
      boton.addEventListener("click", () => this.irAVista(vista.id));
      this.#botones.set(vista.id, boton);
      barra.appendChild(boton);
    }

    this.#contenido = crearRelleno(documento);
    this.#contenido.className = "dlv-vistas__contenido";

    raiz.append(barra, this.#contenido);

    this.irAVista(vistas[0]!.id);
  }

  irAVista(id: string, opciones: OpcionesActivacion = {}): void {
    if (this.#activa !== null && this.#activa.id === id && opciones.instanteS === undefined) {
      return;
    }
    const definicion = this.#vistas.find((v) => v.id === id);
    if (definicion === undefined) {
      throw new Error(`ConmutadorDeVistas: vista desconocida «${id}»`);
    }

    // Desmontar ANTES de montar: es lo que garantiza que nunca hay dos
    // vistas vivas a la vez (ver la cabecera del módulo).
    this.#activa?.montada.desmontar();
    this.#contenido.textContent = "";

    const contenedor = crearRelleno(this.#documento);
    this.#contenido.appendChild(contenedor);
    const montada = definicion.montar(contenedor, this, opciones);
    this.#activa = { id, montada };
    this.#actualizarBotones(id);
  }

  #actualizarBotones(idActiva: string): void {
    for (const [id, boton] of this.#botones) {
      boton.classList.toggle("dlv-vistas__boton--activo", id === idActiva);
      boton.style.setProperty("background", id === idActiva ? "var(--acento)" : "transparent");
      boton.style.setProperty("color", id === idActiva ? "#06141f" : "var(--texto)");
    }
  }

  /** Desmonta la vista activa. Para cuando se destruye el ensamblado entero (pruebas, sobre todo). */
  destruir(): void {
    this.#activa?.montada.desmontar();
    this.#activa = null;
  }
}
