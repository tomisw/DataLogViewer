/**
 * Selector de unidad a tres niveles: global, dimensión, canal (F1-31).
 *
 * QUÉ HACE Y QUÉ NO HACE
 * =======================
 * Decide QUÉ unidad se muestra para cada canal, con la precedencia de
 * `docs/06-sistema-de-unidades.md` §6.9 (canal > dimensión del perfil >
 * preset global > canónica, resuelta por `resolucion.ts`, espejo de F1-17).
 * NO convierte ningún valor: cambiar de unidad es un repintado, no una
 * reescritura (§6.3 regla 3), así que este componente solo emite QUÉ unidad
 * ganó por canal (`CambioUnidad.resueltas`) y quien pinte los cubos hace la
 * conversión y el repintado. Por la misma razón, este módulo no importa
 * `datos/cache-cubos.ts`: `invalidar()` no se llama nunca desde aquí, y no
 * llamarla es precisamente lo que hace alcanzable el presupuesto de §2.6
 * («cambio de unidad con 8 logs abiertos < 100 ms, sin recarga ni
 * invalidación de caché») — este componente no toca datos, así que ese
 * presupuesto no depende de nada que él haga.
 *
 * POR QUÉ SE VE «HEREDADO» FRENTE A «FIJADO AQUÍ»
 * ================================================
 * Un selector que solo enseña la unidad activa, sin decir de qué capa vino,
 * hace imposible deshacer una elección: si un canal está en psi y no se sabe
 * si es porque alguien lo fijó ahí o porque el perfil entero está en psi, no
 * hay forma de saber qué desactivar para volver a "seguir al perfil". Por
 * eso cada fila de canal muestra `explicacionDeCapa` de su `UnidadResuelta`,
 * y la opción "— heredar —" existe explícitamente en vez de dejar el
 * desplegable vacío: seleccionarla borra la anulación en vez de fijarla a un
 * valor concreto que coincida por casualidad con lo heredado.
 *
 * SIN FRAMEWORK, SIN jsdom
 * ========================
 * DOM directo (`FabricaDom` de `dom.ts`), igual que `main.ts`. El
 * constructor recibe la fábrica en vez de usar el `document` global para que
 * las pruebas puedan pasar `dom-falso.ts` sin necesitar jsdom/happy-dom, que
 * no están instalados (`vitest.config.ts` corre en `environment: "node"`).
 * `fabricaDesdeDocumento(document)` es el puente hacia el DOM real.
 */

import type { FabricaDom, NodoDom, SelectDom } from "./dom.ts";
import { buscarDimension, explicacionDeCapa, resolverUnidad } from "./resolucion.ts";
import type {
  CanalInfo,
  CatalogoUnidades,
  DimensionInfo,
  UnidadResuelta,
} from "./tipos.ts";
import { Capa } from "./tipos.ts";

/** Lo que el usuario ha elegido en los tres niveles, en un momento dado. */
export interface EstadoUnidades {
  readonly preset: string;
  readonly preferenciasPerfil: Readonly<Record<string, string>>;
  readonly anulacionesCanal: Readonly<Record<string, string>>;
}

/** Lo que se emite tras cualquier cambio en cualquiera de los tres niveles. */
export interface CambioUnidad {
  readonly estado: EstadoUnidades;
  /** Unidad resuelta para cada canal declarado en `canales`, tras el cambio. */
  readonly resueltas: ReadonlyMap<string, UnidadResuelta>;
}

export interface OpcionesSelectorUnidad {
  readonly catalogo: CatalogoUnidades;
  /** Los canales que el nivel «canal» puede anular. Los decide quien llama. */
  readonly canales: readonly CanalInfo[];
  readonly estadoInicial?: {
    readonly preset?: string;
    readonly preferenciasPerfil?: Readonly<Record<string, string>>;
    readonly anulacionesCanal?: Readonly<Record<string, string>>;
  };
  readonly onCambio?: (cambio: CambioUnidad) => void;
}

const VALOR_HEREDAR = "";

export class SelectorUnidad {
  /** Raíz del componente: quien lo use la inserta donde quiera del árbol real. */
  readonly elemento: NodoDom;

  readonly #dom: FabricaDom;
  readonly #catalogo: CatalogoUnidades;
  readonly #canales: readonly CanalInfo[];
  readonly #onCambio: ((cambio: CambioUnidad) => void) | undefined;

  #preset: string;
  #preferenciasPerfil: Record<string, string>;
  #anulacionesCanal: Record<string, string>;

  constructor(dom: FabricaDom, opciones: OpcionesSelectorUnidad) {
    this.#dom = dom;
    this.#catalogo = opciones.catalogo;
    this.#canales = opciones.canales;
    this.#onCambio = opciones.onCambio;
    this.#preset = opciones.estadoInicial?.preset ?? this.#catalogo.presetPorOmision;
    this.#preferenciasPerfil = { ...opciones.estadoInicial?.preferenciasPerfil };
    this.#anulacionesCanal = { ...opciones.estadoInicial?.anulacionesCanal };

    this.elemento = dom.crearDiv();
    this.elemento.classList.add("selector-unidad");
    this.#render();
  }

  /** Copia inmutable de lo elegido en los tres niveles ahora mismo. */
  get estado(): EstadoUnidades {
    return {
      preset: this.#preset,
      preferenciasPerfil: { ...this.#preferenciasPerfil },
      anulacionesCanal: { ...this.#anulacionesCanal },
    };
  }

  /** La unidad activa para un canal concreto, con la capa que la decidió. */
  unidadResueltaDe(canalId: string): UnidadResuelta {
    const canal = this.#canales.find((c) => c.id === canalId);
    if (canal === undefined) {
      throw new Error(`unidadResueltaDe: '${canalId}' no está entre los canales del selector`);
    }
    return resolverUnidad({
      dimensionId: canal.dimensionId,
      catalogo: this.#catalogo,
      preset: this.#preset,
      preferenciasPerfil: this.#preferenciasPerfil,
      anulacionCanal: this.#anulacionesCanal[canal.id],
    });
  }

  // ------------------------------------------------------------------ //
  // Construcción del árbol. Se reconstruye entero en cada cambio: son unas
  // pocas decenas de filas (dimensiones + canales activos), no las 73 M de
  // muestras — el coste de este componente no compite con el presupuesto de
  // §2.6, que es sobre repintar los cubos, no sobre este árbol de controles.
  // ------------------------------------------------------------------ //
  #render(): void {
    const filas: NodoDom[] = [this.#filaPreset()];
    for (const dimension of this.#catalogo.dimensiones) {
      if (!dimension.convertible) continue;
      filas.push(this.#filaDimension(dimension));
    }
    for (const canal of this.#canales) {
      filas.push(this.#filaCanal(canal));
    }
    this.elemento.replaceChildren(...filas);
  }

  #filaPreset(): NodoDom {
    const opciones = this.#catalogo.presets.map((p) => ({ value: p.id, texto: p.etiqueta }));
    const select = this.#construirSelect(opciones, this.#preset, (valor) => {
      this.#preset = valor;
      this.#render();
      this.#emitir();
    });
    return this.#construirFila("Global", select);
  }

  #filaDimension(dimension: DimensionInfo): NodoDom {
    const opciones = [
      { value: VALOR_HEREDAR, texto: "— heredar del preset —" },
      ...dimension.unidades.map((u) => ({ value: u.id, texto: u.etiqueta || u.id })),
    ];
    const valorActual = this.#preferenciasPerfil[dimension.id] ?? VALOR_HEREDAR;
    const select = this.#construirSelect(opciones, valorActual, (valor) => {
      if (valor === VALOR_HEREDAR) delete this.#preferenciasPerfil[dimension.id];
      else this.#preferenciasPerfil[dimension.id] = valor;
      this.#render();
      this.#emitir();
    });
    const resuelta = resolverUnidad({
      dimensionId: dimension.id,
      catalogo: this.#catalogo,
      preset: this.#preset,
      // A nivel de dimensión, "lo heredado" es lo que vendría del preset, sin
      // contar la propia preferencia de perfil que esta fila edita.
    });
    const nota = `${this.#notaDecimales(resuelta.unidad.decimales)} · si no se fija aquí, ${explicacionDeCapa(resuelta.capa)}`;
    return this.#construirFila(dimension.etiqueta, select, nota);
  }

  #filaCanal(canal: CanalInfo): NodoDom {
    const dimension = buscarDimension(this.#catalogo, canal.dimensionId);
    if (!dimension.convertible) {
      const aviso = this.#dom.crearSpan();
      aviso.classList.add("selector-unidad__aviso");
      aviso.textContent = dimension.mostrarEnCrudo
        ? "sin confirmar: se muestra en crudo, sin unidad"
        : "sin conversión de unidad (escala logarítmica o adimensional)";
      return this.#construirFila(canal.etiqueta, aviso);
    }

    const opciones = [
      { value: VALOR_HEREDAR, texto: "— heredar —" },
      ...dimension.unidades.map((u) => ({ value: u.id, texto: u.etiqueta || u.id })),
    ];
    const valorActual = this.#anulacionesCanal[canal.id] ?? VALOR_HEREDAR;
    const select = this.#construirSelect(opciones, valorActual, (valor) => {
      if (valor === VALOR_HEREDAR) delete this.#anulacionesCanal[canal.id];
      else this.#anulacionesCanal[canal.id] = valor;
      this.#render();
      this.#emitir();
    });

    const resuelta = this.unidadResueltaDe(canal.id);
    const origen =
      resuelta.capa === Capa.CANAL ? "fijado aquí" : `heredado: ${explicacionDeCapa(resuelta.capa)}`;
    const nota = `${this.#notaDecimales(resuelta.unidad.decimales)} · ${origen}`;
    return this.#construirFila(canal.etiqueta, select, nota);
  }

  #notaDecimales(decimales: number): string {
    return `${decimales} decimal${decimales === 1 ? "" : "es"}`;
  }

  #construirSelect(
    opciones: readonly { readonly value: string; readonly texto: string }[],
    valorActual: string,
    alCambiar: (valor: string) => void,
  ): SelectDom {
    const select = this.#dom.crearSelect();
    select.classList.add("selector-unidad__select");
    for (const opcion of opciones) {
      const elementoOpcion = this.#dom.crearOption();
      elementoOpcion.value = opcion.value;
      elementoOpcion.textContent = opcion.texto;
      select.appendChild(elementoOpcion);
    }
    select.value = valorActual;
    select.addEventListener("change", (evento: Event) => {
      const objetivo = evento.target as unknown as SelectDom;
      alCambiar(objetivo.value);
    });
    return select;
  }

  #construirFila(etiquetaTexto: string, control: NodoDom, notaTexto?: string): NodoDom {
    const fila = this.#dom.crearDiv();
    fila.classList.add("selector-unidad__fila");

    const etiqueta = this.#dom.crearSpan();
    etiqueta.classList.add("selector-unidad__etiqueta");
    etiqueta.textContent = etiquetaTexto;
    fila.appendChild(etiqueta);
    fila.appendChild(control);

    if (notaTexto !== undefined) {
      const nota = this.#dom.crearSpan();
      nota.classList.add("selector-unidad__nota");
      nota.textContent = notaTexto;
      fila.appendChild(nota);
    }
    return fila;
  }

  #emitir(): void {
    if (this.#onCambio === undefined) return;
    const resueltas = new Map<string, UnidadResuelta>();
    for (const canal of this.#canales) resueltas.set(canal.id, this.unidadResueltaDe(canal.id));
    this.#onCambio({ estado: this.estado, resueltas });
  }
}
