/**
 * Selector del combustible / factor de estequiometría para λ → AFR.
 *
 * QUÉ HACE Y QUÉ NO HACE
 * =======================
 * Decide QUÉ estequiometría está activa para la conversión parametrizada
 * λ → AFR (`dlv_core.unidades.Parametrizada`, `docs/06` §6.4), con la
 * precedencia de `resolucion.ts`: elección del usuario (persistida en el
 * perfil del coche) > canal `stoichiometry` del log > gasolina supuesta. NO
 * convierte ningún valor: emite el factor resuelto (`CambioFactor`) y quien lo
 * use repinta con `Parametrizada.desde_canonica(..., param=factor)`, igual que
 * `SelectorUnidad` (`unidades/selector-unidad.ts`) solo decide qué unidad
 * ganó y deja la conversión de los cubos a quien pinta.
 *
 * POR QUÉ EL CASO "SUPUESTO" SE VE DISTINTO
 * ===========================================
 * Un AFR calculado con la estequiometría equivocada tiene el mismo aspecto —
 * el mismo número de decimales, la misma unidad— que uno correcto: no hay
 * forma de notar el error mirando solo el valor. Por eso, cuando el origen es
 * `OrigenFactor.SUPUESTO`, la nota no se pinta como las demás (clase
 * `selector-combustible__aviso` en vez de `…__nota`, y con el texto "SUPUESTO"
 * por delante) — es la única señal que separa un AFR correcto de uno
 * incorrecto con aspecto de correcto, tal como lo pidió el propietario.
 *
 * SIN FRAMEWORK, SIN jsdom
 * ========================
 * DOM directo (`FabricaDom` de `dom.ts`), igual que `unidades/selector-
 * unidad.ts` y `main.ts`. El constructor recibe la fábrica para que las
 * pruebas puedan pasar `dom-falso.ts` sin necesitar jsdom/happy-dom.
 */

import type { FabricaDom, NodoDom, SelectDom } from "./dom.ts";
import {
  analizarEstequiometriaTecleada,
  buscarCombustible,
  explicacionDeOrigen,
  resolverFactorEstequiometrico,
} from "./resolucion.ts";
import type { CombustibleInfo, EleccionUsuario, FactorResuelto } from "./tipos.ts";
import { OrigenFactor } from "./tipos.ts";

/** Lo que se emite tras cualquier cambio: el factor activo y de dónde vino. */
export interface CambioFactor {
  /** Listo para persistir en el perfil del coche. `undefined` = "sin elección propia: automático". */
  readonly eleccionUsuario: EleccionUsuario | undefined;
  readonly factor: FactorResuelto;
}

export interface OpcionesSelectorCombustible {
  readonly catalogo: readonly CombustibleInfo[];
  /** Valor leído del canal de rol `stoichiometry` de este log, si lo trae. */
  readonly estequiometriaDelLog?: number;
  /** Elección ya persistida en el perfil del coche (p. ej. al reabrir la app). */
  readonly eleccionInicial?: EleccionUsuario;
  readonly onCambio?: (cambio: CambioFactor) => void;
}

const VALOR_AUTOMATICO = "";
const VALOR_MANUAL = "__manual__";

export class SelectorCombustible {
  /** Raíz del componente: quien lo use la inserta donde quiera del árbol real. */
  readonly elemento: NodoDom;

  readonly #dom: FabricaDom;
  readonly #catalogo: readonly CombustibleInfo[];
  readonly #onCambio: ((cambio: CambioFactor) => void) | undefined;

  #estequiometriaDelLog: number | undefined;
  #eleccionUsuario: EleccionUsuario | undefined;
  /** Lo que hay tecleado en el campo manual, incluso si todavía no es un número válido. */
  #textoManual: string;

  constructor(dom: FabricaDom, opciones: OpcionesSelectorCombustible) {
    this.#dom = dom;
    this.#catalogo = opciones.catalogo;
    this.#onCambio = opciones.onCambio;
    this.#estequiometriaDelLog = opciones.estequiometriaDelLog;
    this.#eleccionUsuario = opciones.eleccionInicial;
    this.#textoManual =
      opciones.eleccionInicial !== undefined && opciones.eleccionInicial.combustibleId === undefined
        ? String(opciones.eleccionInicial.estequiometria)
        : "";

    this.elemento = dom.crearDiv();
    this.elemento.classList.add("selector-combustible");
    this.#render();
  }

  /** El factor activo ahora mismo, con su procedencia (`resolucion.ts`). */
  get factorResuelto(): FactorResuelto {
    return resolverFactorEstequiometrico({
      catalogo: this.#catalogo,
      estequiometriaDelLog: this.#estequiometriaDelLog,
      eleccionUsuario: this.#eleccionUsuario,
    });
  }

  /** Lo que hay que persistir en el perfil del coche. `undefined` = sigue en automático. */
  get eleccionUsuario(): EleccionUsuario | undefined {
    return this.#eleccionUsuario;
  }

  /**
   * El log terminó de analizarse (o se cambió de log) después de construir el
   * componente: actualiza el valor leído y repinta. No toca la elección del
   * usuario -- si ya había una, sigue ganando (misma precedencia de
   * `resolucion.ts`).
   */
  actualizarEstequiometriaDelLog(valor: number | undefined): void {
    this.#estequiometriaDelLog = valor;
    this.#render();
    this.#emitir();
  }

  // ------------------------------------------------------------------ //
  // Construcción del árbol. Se reconstruye entero en cada cambio: es un
  // puñado de filas, no las 73 M de muestras -- mismo argumento que
  // `SelectorUnidad.#render`.
  // ------------------------------------------------------------------ //
  #render(): void {
    const filas: NodoDom[] = [this.#filaSelector()];
    if (this.#modoActual() === VALOR_MANUAL) filas.push(this.#filaManual());
    filas.push(this.#filaOrigen());
    this.elemento.replaceChildren(...filas);
  }

  /** Qué opción del `<select>` corresponde al estado actual. */
  #modoActual(): string {
    if (this.#eleccionUsuario === undefined) return VALOR_AUTOMATICO;
    if (this.#eleccionUsuario.combustibleId !== undefined) return this.#eleccionUsuario.combustibleId;
    return VALOR_MANUAL;
  }

  #filaSelector(): NodoDom {
    const opciones = [
      { value: VALOR_AUTOMATICO, texto: "— automático (log / supuesto) —" },
      ...this.#catalogo.map((c) => ({
        value: c.id,
        texto: `${c.etiqueta} (${c.estequiometria})`,
      })),
      { value: VALOR_MANUAL, texto: "— valor manual —" },
    ];
    const select = this.#dom.crearSelect();
    select.classList.add("selector-combustible__select");
    for (const opcion of opciones) {
      const elementoOpcion = this.#dom.crearOption();
      elementoOpcion.value = opcion.value;
      elementoOpcion.textContent = opcion.texto;
      select.appendChild(elementoOpcion);
    }
    select.value = this.#modoActual();
    select.addEventListener("change", (evento: Event) => {
      const valor = (evento.target as unknown as SelectDom).value;
      this.#alCambiarSelector(valor);
    });
    return this.#construirFila("Combustible", select);
  }

  #alCambiarSelector(valor: string): void {
    if (valor === VALOR_AUTOMATICO) {
      this.#eleccionUsuario = undefined;
    } else if (valor === VALOR_MANUAL) {
      // Se arranca el campo manual con el valor activo ahora mismo, para
      // editar "desde donde estaba" en vez de desde cero -- y para que el
      // texto del campo y `#eleccionUsuario` nunca queden desincronizados
      // con un texto tecleado en una visita anterior al modo manual.
      const actual = this.factorResuelto.estequiometria;
      this.#textoManual = String(actual);
      this.#eleccionUsuario = { estequiometria: actual };
    } else {
      const combustible = buscarCombustible(this.#catalogo, valor);
      this.#eleccionUsuario = { combustibleId: combustible.id, estequiometria: combustible.estequiometria };
    }
    this.#render();
    this.#emitir();
  }

  #filaManual(): NodoDom {
    const input = this.#dom.crearInput();
    input.classList.add("selector-combustible__input");
    input.type = "text";
    input.placeholder = "p. ej. 9,77";
    input.value = this.#textoManual;
    input.addEventListener("change", (evento: Event) => {
      const texto = (evento.target as unknown as { value: string }).value;
      this.#alCambiarValorManual(texto);
    });

    const valida = analizarEstequiometriaTecleada(this.#textoManual) !== undefined;
    const nota = valida
      ? undefined
      : "no es un número válido (> 0): se mantiene el último valor manual válido";
    return this.#construirFila("Estequiometría", input, nota);
  }

  #alCambiarValorManual(texto: string): void {
    this.#textoManual = texto;
    const valor = analizarEstequiometriaTecleada(texto);
    if (valor === undefined) {
      // Se guarda lo tecleado para no borrárselo al usuario mientras corrige,
      // pero NO se toca `#eleccionUsuario`: un valor inválido no puede ganar
      // silenciosamente a lo que había antes.
      this.#render();
      return;
    }
    this.#eleccionUsuario = { estequiometria: valor };
    this.#render();
    this.#emitir();
  }

  #filaOrigen(): NodoDom {
    const factor = this.factorResuelto;
    const nodo = this.#dom.crearSpan();
    if (factor.origen === OrigenFactor.SUPUESTO) {
      // El caso que no puede pasar desapercibido: ver la cabecera del módulo.
      nodo.classList.add("selector-combustible__aviso");
      nodo.textContent = `SUPUESTO — ${explicacionDeOrigen(factor.origen)} (${factor.estequiometria})`;
    } else {
      nodo.classList.add("selector-combustible__nota");
      const origenTexto =
        factor.origen === OrigenFactor.USUARIO ? "elegido aquí" : "leído del log";
      nodo.textContent = `${origenTexto}: ${explicacionDeOrigen(factor.origen)} (${factor.estequiometria})`;
    }
    return nodo;
  }

  #construirFila(etiquetaTexto: string, control: NodoDom, notaTexto?: string): NodoDom {
    const fila = this.#dom.crearDiv();
    fila.classList.add("selector-combustible__fila");

    const etiqueta = this.#dom.crearSpan();
    etiqueta.classList.add("selector-combustible__etiqueta");
    etiqueta.textContent = etiquetaTexto;
    fila.appendChild(etiqueta);
    fila.appendChild(control);

    if (notaTexto !== undefined) {
      const nota = this.#dom.crearSpan();
      nota.classList.add("selector-combustible__error");
      nota.textContent = notaTexto;
      fila.appendChild(nota);
    }
    return fila;
  }

  #emitir(): void {
    if (this.#onCambio === undefined) return;
    this.#onCambio({ eleccionUsuario: this.#eleccionUsuario, factor: this.factorResuelto });
  }
}
