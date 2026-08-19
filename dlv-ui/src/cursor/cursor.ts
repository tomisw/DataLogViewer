/**
 * Cursor con tabla de valores (F1-29), presupuesto de §2.6 «latencia del
 * cursor a tabla actualizada < 16 ms».
 *
 * DE DÓNDE LEE, Y POR QUÉ ESO IMPORTA
 * ===================================
 * Este componente NUNCA pide datos. Lee de la `CacheDeCubos` de F1-24 con
 * `mirar()`, no con `consultar()`: `consultar()` está pensada para quien
 * decide si hay que pedir más al backend (pan/zoom) y cuenta aciertos/fallos
 * para ESE presupuesto; el cursor solo consume lo que ya está cacheado. Si el
 * instante cae fuera de lo cargado, se enseña «sin datos», nunca un valor
 * extrapolado del cubo más cercano — mostrar un número plausible fuera de
 * rango es el error más caro posible en una tabla que se mira para decidir un
 * cambio de tuning.
 *
 * QUÉ SE ENSEÑA CUANDO "EL VALOR" ES UN RANGO, Y POR QUÉ
 * =======================================================
 * `valorEn` (F1-24) da cuatro números —`minimo`, `maximo`, `primero`,
 * `ultimo`— precisamente porque a nivel decimado "el valor" no existe. Este
 * módulo decide así (`contenidoDeCelda`):
 *
 *   - **`factor === 1` (muestra real, sin decimar):** los cuatro números
 *     coinciden por construcción (un cubo es una única muestra), así que se
 *     enseña un solo número y una columna «Nivel» que dice «muestra». No hay
 *     nada que ocultar.
 *   - **`factor > 1` (decimado):** se enseña el RANGO `mínimo – máximo` como
 *     cifra principal, no `último`. Enseñar solo `último` como si fuera "el
 *     valor" es exactamente el fallo que este módulo existe para evitar: en
 *     ese píxel pudo haber un pico de 900 °C que `último` no refleja. La
 *     columna «Nivel» muestra `×factor` y el `title` (tooltip nativo del
 *     navegador, sin dependencias) explica el rango y añade `primero→último`
 *     como pista de tendencia dentro del intervalo — información secundaria,
 *     no la cifra que se lee de un vistazo.
 *
 * Cualquier vista futura que quiera "el valor puntual de verdad" tiene que
 * subir de nivel (pedir el cubo real), no leer `último` de este nivel como si
 * fuera equivalente: no lo es, y este módulo no finge que lo sea.
 *
 * PRESUPUESTO Y EL BUCLE DE DIBUJO: `mover()` VS `aplicar()`
 * ===========================================================
 * `mover(t, x)` es barato a propósito: solo guarda el instante pendiente. NO
 * toca el DOM. Un panel puede recibir varios `mousemove` por fotograma (el
 * navegador no los alinea con `requestAnimationFrame`); si cada uno escribiera
 * la tabla, "una vez por fotograma como mucho" se rompería sin que se notara
 * en una prueba unitaria con un solo evento.
 *
 * `aplicar()` es la parte cara: busca el valor de cada canal y escribe el
 * DOM. La llama, como mucho una vez por fotograma, el bucle de dibujo del
 * panel (fuera de este módulo, igual que `Renderizador.dibujar` no se llama a
 * sí mismo — ver `render/renderizador.ts`). Así el componente no depende de
 * `requestAnimationFrame`, que no existe en el entorno `node` en el que corre
 * `npm run banco` (ver la cabecera de `vitest.banco.config.ts`), y se puede
 * medir su coste real en la prueba sin inventar un navegador.
 *
 * Dentro de `aplicar()`, cada celda se compara con lo último escrito antes de
 * tocarla: si el canal no cambió de cubo (frecuente entre dos fotogramas de un
 * cursor casi quieto, o en un canal constante), no se escribe nada. Es la
 * misma disciplina que `Renderizador`: lo caro no es tener el dato, es
 * escribirlo cuando no hace falta.
 */

import { CacheDeCubos, valorEn, type ClaveCubos } from "../datos/cache-cubos.ts";
import { formatearNumero as formatearNumeroLocale } from "../locale/numerico.ts";
import { t } from "../locale/catalogo.ts";
import type { ContextoDOM } from "./contexto-dom.ts";

/** Un canal a mostrar en la tabla del cursor. */
export interface CanalCursor {
  /** Clave con la que este canal está guardado en la caché (canal + nivel vigente). */
  readonly clave: ClaveCubos;
  /** Nombre que se ve en la tabla. */
  readonly etiqueta: string;
}

export interface OpcionesCursor {
  /** Por omisión, `document` global. Inyectable para probar sin navegador (`doble-dom.ts`). */
  readonly documento?: ContextoDOM;
  /**
   * Formato de un número para la celda. Por omisión, `formatearNumero` de
   * este módulo. El sistema de unidades (fuera del alcance de F1-29, en
   * `src/unidades/`) puede inyectar el suyo el día que exista sin tocar esta
   * clase: es la costura deliberada para no acoplar el cursor a un módulo que
   * todavía no existe.
   */
  readonly formatear?: (valor: number, clave: ClaveCubos) => string;
}

/**
 * Formato por omisión: menos decimales cuanto más grande es el número.
 * Sin esto, un RPM de 4000 saldría "4000.000" y una lambda de 0.85 saldría
 * "1" — ninguno de los dos es lo que hay que leer de un vistazo.
 */
export function formatearNumero(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  const absoluto = Math.abs(valor);
  const decimales = absoluto >= 1000 ? 0 : absoluto >= 100 ? 1 : absoluto >= 1 ? 2 : 3;
  // El separador lo pone `src/locale/numerico.ts` (F1-32). Esta función usaba
  // `toFixed`, que da SIEMPRE punto decimal: la tabla del cursor enseñaba
  // `101.2` mientras el eje de al lado, en la misma ventana, enseñaba `101,2`.
  // Lo que sigue decidiéndose aquí es cuántos decimales, y por la magnitud del
  // valor: sin eso un RPM de 4000 saldría "4000,000" y una lambda de 0,85
  // saldría "1", y ninguno de los dos es lo que hay que leer de un vistazo.
  return formatearNumeroLocale(valor, decimales);
}

/** Lo que va en la celda de valor y en la de nivel, ya decidido para un canal e instante. */
export interface ContenidoCelda {
  readonly texto: string;
  readonly nivel: string;
  readonly clase: string;
  readonly titulo: string;
}

const SIN_DATOS: ContenidoCelda = {
  texto: "—",
  nivel: "sin datos",
  clase: "cursor-valor cursor-valor--vacio",
  titulo:
    "No hay cubos cacheados que cubran este instante (fuera del tramo cargado " +
    "en memoria). No es un valor cero: es la ausencia de dato en la caché.",
};

/**
 * Decide qué enseñar para un canal en un instante. Función pura y exportada
 * a propósito: es la decisión que más le importa revisar al propietario
 * (ver la cabecera del módulo) y una función pura se revisa y se prueba sin
 * levantar ni un `HTMLElement`.
 */
export function contenidoDeCelda(
  cache: CacheDeCubos,
  clave: ClaveCubos,
  tAbsoluto: number,
  formatear: (valor: number, clave: ClaveCubos) => string,
): ContenidoCelda {
  // `formatear` recibe la CLAVE además del valor, y eso no es comodidad: la
  // conversión a la unidad mostrada depende del canal (su `to_canon` y la
  // unidad que el selector le resolvió), así que un formateador único para
  // toda la tabla convierte las filas de los demás canales con los factores
  // del primero. Con un canal por panel no se nota; en cuanto se arrastran dos
  // canales al mismo panel, uno de los dos enseña un número equivocado.
  const fmt = (valor: number): string => formatear(valor, clave);
  const entrada = cache.mirar(clave);
  if (entrada === undefined) return SIN_DATOS;
  // `mirar` no comprueba cobertura (no es su trabajo: eso es `consultar`).
  // `valorEn`/`indiceEn` tampoco rechazan un instante posterior al último cubo
  // cargado: devolverían el último cubo como si fuera el vigente, que es
  // exactamente el valor plausible y falso que este módulo tiene que evitar.
  if (tAbsoluto < entrada.cubre.t0 || tAbsoluto > entrada.cubre.t1) return SIN_DATOS;
  const valor = valorEn(entrada.cubos, tAbsoluto);
  if (valor === null) return SIN_DATOS;

  if (clave.factor <= 1) {
    // Sin decimar: los cuatro números coinciden por construcción. Un solo
    // número, y la columna «Nivel» lo deja explícito para que no haga falta
    // recordar qué factor tenía este canal para saber si lo que se ve es real.
    return {
      texto: fmt(valor.ultimo),
      nivel: "muestra",
      clase: "cursor-valor cursor-valor--real",
      titulo: "Muestra real: este nivel de pirámide no decima (factor 1).",
    };
  }

  const hayRango = valor.maximo > valor.minimo;
  const texto = hayRango ? `${fmt(valor.minimo)} – ${fmt(valor.maximo)}` : fmt(valor.ultimo);
  return {
    texto,
    nivel: `×${clave.factor}`,
    clase: "cursor-valor cursor-valor--rango",
    titulo:
      `Rango decimado ×${clave.factor}: cada cubo agrega ${clave.factor} muestras. ` +
      `«${texto}» es el mínimo–máximo real del intervalo, no "el valor": un pico puede ` +
      "estar oculto en el máximo aunque el trazo parezca plano a este zoom. " +
      `Tendencia dentro del intervalo: ${fmt(valor.primero)} → ${fmt(valor.ultimo)}.`,
  };
}

interface FilaTabla {
  readonly clave: ClaveCubos;
  readonly celdaValor: HTMLElement;
  readonly celdaNivel: HTMLElement;
  textoEscrito: string | null;
  nivelEscrito: string | null;
  claseEscrita: string | null;
}

/**
 * El componente: cursor vertical + tabla de valores. Sin framework, DOM
 * directo (`document.createElement`), tal y como pide la tarea.
 */
export class CursorDeTabla {
  readonly #documento: ContextoDOM;
  readonly #cache: CacheDeCubos;
  readonly #formatear: (valor: number, clave: ClaveCubos) => string;
  readonly #linea: HTMLElement;
  readonly #cuerpo: HTMLElement;

  #filas: FilaTabla[] = [];

  // Lo que se pidió con `mover()`/`ocultar()` desde el último `aplicar()`.
  #visiblePendiente = false;
  #tPendiente = 0;
  #xPendiente = 0;

  // Lo que ya está escrito en el DOM, para no repetir una escritura idéntica.
  #visibleEscrito = false;
  #tEscrito: number | null = null;
  #xEscrito: number | null = null;

  constructor(panel: HTMLElement, tabla: HTMLElement, cache: CacheDeCubos, opciones: OpcionesCursor = {}) {
    this.#cache = cache;
    this.#formatear = opciones.formatear ?? formatearNumero;
    // `document` global salvo que se inyecte otra cosa: el mismo patrón que
    // `Renderizador.desdeLienzo` frente al `Renderizador` que recibe un
    // `ContextoGL` ya construido.
    const documento = opciones.documento ?? document;
    this.#documento = documento;

    this.#linea = documento.createElement("div");
    this.#linea.className = "cursor-linea";
    this.#linea.style.setProperty("display", "none");
    this.#linea.style.setProperty("position", "absolute");
    this.#linea.style.setProperty("top", "0");
    this.#linea.style.setProperty("bottom", "0");
    this.#linea.style.setProperty("pointer-events", "none");
    panel.appendChild(this.#linea);

    const encabezado = documento.createElement("thead");
    const filaEncabezado = documento.createElement("tr");
    for (const texto of [t("cursor.columnaCanal"), t("cursor.columnaValor"), t("cursor.columnaNivel")]) {
      const celda = documento.createElement("th");
      celda.textContent = texto;
      filaEncabezado.appendChild(celda);
    }
    encabezado.appendChild(filaEncabezado);
    tabla.appendChild(encabezado);

    this.#cuerpo = documento.createElement("tbody");
    tabla.appendChild(this.#cuerpo);
  }

  /**
   * Reemplaza la lista de canales mostrados (cambia con el panel, no con el
   * cursor). Reconstruye el cuerpo de la tabla: es la parte que NO tiene el
   * presupuesto de 16 ms —eso solo protege `aplicar()`— porque cambiar de
   * canal es una acción explícita del usuario, no algo que pase 60 veces por
   * segundo.
   */
  actualizarCanales(canales: readonly CanalCursor[]): void {
    this.#cuerpo.textContent = ""; // Igual que en el DOM real: vacía el cuerpo.
    this.#filas = canales.map((canal) => {
      const fila = this.#documento.createElement("tr");
      const celdaCanal = this.#documento.createElement("td");
      celdaCanal.textContent = canal.etiqueta;
      celdaCanal.className = "cursor-celda cursor-celda--canal";

      const celdaValor = this.#documento.createElement("td");
      const celdaNivel = this.#documento.createElement("td");
      celdaNivel.className = "cursor-celda cursor-celda--nivel";

      fila.appendChild(celdaCanal);
      fila.appendChild(celdaValor);
      fila.appendChild(celdaNivel);
      this.#cuerpo.appendChild(fila);

      return {
        clave: canal.clave,
        celdaValor,
        celdaNivel,
        textoEscrito: null,
        nivelEscrito: null,
        claseEscrita: null,
      };
    });
    // Forzar que el próximo `aplicar()` reescriba todas las celdas: la
    // composición de canales cambió, así que lo que había escrito ya no
    // corresponde a ninguna fila.
    this.#tEscrito = null;
  }

  /**
   * Barato: registra dónde está el cursor. No toca el DOM (ver la cabecera).
   * `xPixel` es la posición horizontal ya calculada por quien gestiona el
   * panel (escala tiempo→píxel, ADR-006: este módulo no sabe de vistas ni de
   * unidades, solo coloca una línea donde se le dice).
   */
  mover(tAbsoluto: number, xPixel: number): void {
    this.#visiblePendiente = true;
    this.#tPendiente = tAbsoluto;
    this.#xPendiente = xPixel;
  }

  /** El ratón salió del panel: en el próximo `aplicar()` se oculta la línea. */
  ocultar(): void {
    this.#visiblePendiente = false;
  }

  /**
   * La parte cara. Se llama, como mucho, una vez por fotograma (ver la
   * cabecera). Devuelve si escribió algo en el DOM, útil para el banco y para
   * quien quiera saber si hizo falta repintar.
   */
  aplicar(): boolean {
    let escribio = false;

    if (!this.#visiblePendiente) {
      if (this.#visibleEscrito) {
        this.#linea.style.setProperty("display", "none");
        this.#visibleEscrito = false;
        escribio = true;
      }
      return escribio;
    }

    if (!this.#visibleEscrito) {
      this.#linea.style.setProperty("display", "");
      this.#visibleEscrito = true;
      escribio = true;
    }
    if (this.#xEscrito !== this.#xPendiente) {
      this.#linea.style.setProperty("left", `${this.#xPendiente}px`);
      this.#xEscrito = this.#xPendiente;
      escribio = true;
    }

    if (this.#tEscrito === this.#tPendiente) {
      // El cursor no cambió de instante desde el último fotograma escrito
      // (o solo cambió la posición en píxel, ya aplicada arriba): no hay
      // nada más que recalcular. Esto es lo que hace barato un cursor casi
      // quieto, que es el caso común entre dos movimientos de ratón.
      return escribio;
    }
    this.#tEscrito = this.#tPendiente;

    for (const fila of this.#filas) {
      const contenido = contenidoDeCelda(this.#cache, fila.clave, this.#tPendiente, this.#formatear);
      if (fila.textoEscrito !== contenido.texto) {
        fila.celdaValor.textContent = contenido.texto;
        fila.textoEscrito = contenido.texto;
        escribio = true;
      }
      if (fila.claseEscrita !== contenido.clase) {
        fila.celdaValor.className = contenido.clase;
        fila.celdaValor.title = contenido.titulo;
        fila.claseEscrita = contenido.clase;
        escribio = true;
      } else if (fila.celdaValor.title !== contenido.titulo) {
        // Misma clase (mismo caso: real/rango/sin-datos) pero el detalle
        // cambió (otro rango, otra tendencia): el tooltip sí hay que
        // actualizarlo aunque la clase no cambie.
        fila.celdaValor.title = contenido.titulo;
        escribio = true;
      }
      if (fila.nivelEscrito !== contenido.nivel) {
        fila.celdaNivel.textContent = contenido.nivel;
        fila.nivelEscrito = contenido.nivel;
        escribio = true;
      }
    }
    return escribio;
  }

  /** Quita la línea del panel. La tabla la gestiona quien la creó (`tabla` del constructor). */
  destruir(): void {
    this.#linea.remove();
  }
}
