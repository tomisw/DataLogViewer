/**
 * `EditorPerfil`: crear (= duplicar, ver `duplicado.ts`), importar, exportar y
 * editar un `.dlvprofile` (F3-05, E4.4 de `docs/02-alcance-y-plan.md`).
 *
 * MISMA PARTICIÓN QUE `unidades/selector-unidad.ts`
 * =====================================================
 * Este fichero es la parte IMPURA: posee un fragmento de DOM y lo mantiene
 * sincronizado a mano (ADR-006 extendido, cero framework). Toda la lógica que
 * decide algo vive en módulos puros sin DOM y por eso son los que tienen la
 * cobertura de pruebas de verdad: el esquema y su validación en `perfil.ts`,
 * duplicar en `duplicado.ts`, la política de edición en `permisos.ts`, la
 * conversión de unidad de los umbrales en `edicion-umbrales.ts`. Este
 * componente solo ORQUESTA esos cuatro módulos contra un `FabricaDom`
 * (`dom.ts`), con su doble en `dom-falso.ts` para poder probarlo sin
 * jsdom/happy-dom (`vitest.config.ts` corre en `environment: "node"`).
 *
 * LAS CUATRO DECISIONES DEL INFORME DE LA TAREA, DÓNDE VIVEN
 * ================================================================
 * 1. Duplicar es la única vía de partir de un perfil (de fábrica o propio):
 *    `#duplicar()` llama a `duplicado.ts#duplicarPerfil` y el editor pasa a
 *    mostrar la copia, ya como perfil de usuario -- es el mismo botón para
 *    "crear a partir de éste" que para "quiero editar este de fábrica".
 * 2. Importar un `.dlvprofile` inválido: `#importar()` llama a
 *    `perfil.ts#perfilDesdeTextoJson` y, si lanza, el mensaje de
 *    `ErrorDePerfil` (que dice QUÉ y DÓNDE) se enseña TAL CUAL en
 *    `#errorImportacion` -- nunca se sustituye por un "no se pudo importar"
 *    genérico.
 * 3. Editar un perfil de fábrica: `permisos.ts#puedeEditarDirectamente`
 *    decide si los campos están activos; si no, se enseña el aviso y el único
 *    control activo es "Duplicar para editar".
 * 4. Umbrales en unidad activa, guardados en canónica:
 *    `#actualizarValorDeTope`/`#actualizarBanda*` delegan en
 *    `edicion-umbrales.ts`, que aplica la clase correcta (PUNTO para el
 *    tope/centro, INTERVALO para el semiancho de una banda).
 */

import { IDENTIDAD, type Conversion } from "../unidades/conversion.ts";
import type { UnidadInfo } from "../unidades/tipos.ts";
import { t } from "../locale/catalogo.ts";
import type { BotonDom, FabricaDom, NodoDom } from "./dom.ts";
import { duplicarPerfil, sugerirNombreDuplicado } from "./duplicado.ts";
import {
  actualizarBandaCentroYAncho,
  actualizarBandaMinMax,
  actualizarValorDeTope,
  bandaACentroYAnchoMostrado,
  bandaAMinMaxMostrado,
  bandaEsEditable,
  bandaEsEditableConSemiancho,
  topeEsEditable,
  valorDeTopeMostrado,
} from "./edicion-umbrales.ts";
import type { Curva, LimiteDeAlerta, Perfil } from "./perfil.ts";
import { construirPerfil, ErrorDePerfil, esCurva, perfilATextoJson, perfilDesdeTextoJson } from "./perfil.ts";
import type { OrigenPerfil } from "./permisos.ts";
import { puedeEditarDirectamente } from "./permisos.ts";

export type UnidadPorRol = ReadonlyMap<string, UnidadInfo>;

export interface OpcionesEditorPerfil {
  readonly dom: FabricaDom;
  readonly perfilInicial: Perfil;
  readonly origenInicial: OrigenPerfil;
  /** Nombres de otros perfiles ya guardados, para que un duplicado nunca colisione. */
  readonly nombresExistentes: readonly string[];
  /** Conversión activa por rol, para enseñar/editar los límites. Un rol ausente se enseña en canónica (`IDENTIDAD`). */
  readonly unidadPorRol?: UnidadPorRol;
  /** Parámetro de una conversión `parametrizada` (p. ej. estequiometría activa), por rol. */
  readonly parametroPorRol?: ReadonlyMap<string, number>;
  readonly onCambiar?: (perfil: Perfil) => void;
  readonly onDuplicar?: (perfil: Perfil) => void;
  readonly onExportar?: (texto: string) => void;
}

export class EditorPerfil {
  readonly elemento: NodoDom;

  readonly #dom: FabricaDom;
  readonly #unidadPorRol: UnidadPorRol;
  readonly #parametroPorRol: ReadonlyMap<string, number>;
  readonly #onCambiar: ((perfil: Perfil) => void) | undefined;
  readonly #onDuplicar: ((perfil: Perfil) => void) | undefined;
  readonly #onExportar: ((texto: string) => void) | undefined;

  #perfil: Perfil;
  #origen: OrigenPerfil;
  #nombresExistentes: string[];

  #errorEdicion: string | null = null;
  #errorImportacion: string | null = null;
  #textoImportar = "";
  #textoExportado: string | null = null;

  constructor(opciones: OpcionesEditorPerfil) {
    this.#dom = opciones.dom;
    this.#perfil = opciones.perfilInicial;
    this.#origen = opciones.origenInicial;
    this.#nombresExistentes = [...opciones.nombresExistentes];
    this.#unidadPorRol = opciones.unidadPorRol ?? new Map();
    this.#parametroPorRol = opciones.parametroPorRol ?? new Map();
    this.#onCambiar = opciones.onCambiar;
    this.#onDuplicar = opciones.onDuplicar;
    this.#onExportar = opciones.onExportar;

    this.elemento = this.#dom.crearDiv();
    this.elemento.classList.add("editor-perfil");
    this.#render();
  }

  get perfil(): Perfil {
    return this.#perfil;
  }

  get origen(): OrigenPerfil {
    return this.#origen;
  }

  /** Entrada pública para "importar": el texto ya leído del fichero (o pegado). Ver la cabecera del módulo, decisión 2. */
  importarTexto(texto: string): void {
    this.#textoImportar = texto;
    this.#importar();
  }

  // --------------------------------------------------------------------- //
  // Conversión activa por rol
  // --------------------------------------------------------------------- //
  #conversionDeRol(rol: string): Conversion {
    return this.#unidadPorRol.get(rol)?.conversion ?? IDENTIDAD;
  }

  #decimalesDeRol(rol: string): number {
    return this.#unidadPorRol.get(rol)?.decimales ?? 2;
  }

  #parametroDeRol(rol: string): number | undefined {
    return this.#parametroPorRol.get(rol);
  }

  // --------------------------------------------------------------------- //
  // Mutación central: toda edición pasa por aquí para que #onCambiar y el
  // re-render sean UN solo sitio, igual que `#actualizarPerfil` no es cada
  // manejador reconstruyendo el árbol por su cuenta.
  // --------------------------------------------------------------------- //
  #actualizarPerfil(nuevo: Perfil): void {
    this.#perfil = nuevo;
    this.#errorEdicion = null;
    this.#render();
    this.#onCambiar?.(nuevo);
  }

  #conError(accion: () => void): void {
    try {
      accion();
    } catch (exc) {
      this.#errorEdicion = exc instanceof Error ? exc.message : String(exc);
      this.#render();
    }
  }

  // --------------------------------------------------------------------- //
  // Decisión 1: duplicar es la única vía de "crear" (ver duplicado.ts).
  // --------------------------------------------------------------------- //
  #duplicar(): void {
    const nombreNuevo = sugerirNombreDuplicado(this.#perfil.nombre, this.#nombresExistentes);
    const copia = duplicarPerfil(this.#perfil, this.#nombresExistentes, nombreNuevo);
    this.#nombresExistentes = [...this.#nombresExistentes, copia.nombre];
    this.#perfil = copia;
    this.#origen = "usuario";
    this.#errorEdicion = null;
    this.#errorImportacion = null;
    this.#render();
    this.#onDuplicar?.(copia);
  }

  // --------------------------------------------------------------------- //
  // Decisión 2: importar enseña el error real de `perfil.ts` tal cual.
  // --------------------------------------------------------------------- //
  #importar(): void {
    try {
      const nuevo = perfilDesdeTextoJson(this.#textoImportar);
      // Un perfil recién importado no es "de fábrica" de este bundle: es un
      // fichero suelto que alguien compartió (E4.4 "compartición como
      // fichero suelto"). Se trata como propio: se puede editar en el sitio.
      this.#perfil = nuevo;
      this.#origen = "usuario";
      this.#errorImportacion = null;
      this.#errorEdicion = null;
      this.#render();
      this.#onCambiar?.(nuevo);
    } catch (exc) {
      this.#errorImportacion = exc instanceof ErrorDePerfil ? exc.message : String(exc);
      this.#render();
    }
  }

  #exportar(): void {
    const texto = perfilATextoJson(this.#perfil);
    this.#textoExportado = texto;
    this.#render();
    this.#onExportar?.(texto);
  }

  // --------------------------------------------------------------------- //
  // Render
  // --------------------------------------------------------------------- //
  #render(): void {
    const hijos = [this.#renderCabecera(), this.#renderLimites(), this.#renderImportarExportar()];
    this.elemento.replaceChildren(...hijos);
  }

  #renderCabecera(): NodoDom {
    const editable = puedeEditarDirectamente(this.#origen);
    const cabecera = this.#dom.crearDiv();
    cabecera.classList.add("editor-perfil__cabecera");

    const badge = this.#dom.crearSpan();
    badge.classList.add("editor-perfil__origen");
    badge.textContent = this.#origen === "fabrica" ? t("perfiles.origenFabrica") : t("perfiles.origenUsuario");
    cabecera.appendChild(badge);

    if (!editable) {
      const aviso = this.#dom.crearSpan();
      aviso.classList.add("editor-perfil__aviso-fabrica");
      aviso.textContent = t("perfiles.avisoFabrica");
      cabecera.appendChild(aviso);
    }

    cabecera.appendChild(
      this.#fila(
        t("perfiles.nombre"),
        this.#campoTexto(this.#perfil.nombre, editable, (valor) =>
          this.#conError(() => this.#actualizarPerfil(construirPerfil({ ...this.#perfil, nombre: valor }))),
        ),
      ),
    );
    cabecera.appendChild(
      this.#fila(
        t("perfiles.descripcion"),
        this.#campoTextoLargo(this.#perfil.descripcion, editable, (valor) =>
          this.#conError(() => this.#actualizarPerfil(construirPerfil({ ...this.#perfil, descripcion: valor }))),
        ),
      ),
    );

    const botonDuplicar = this.#boton(editable ? t("perfiles.duplicar") : t("perfiles.duplicarParaEditar"), () =>
      this.#conError(() => this.#duplicar()),
    );
    botonDuplicar.classList.add("editor-perfil__duplicar");
    cabecera.appendChild(botonDuplicar);

    if (this.#errorEdicion !== null) {
      const error = this.#dom.crearSpan();
      error.classList.add("editor-perfil__error");
      error.textContent = this.#errorEdicion;
      cabecera.appendChild(error);
    }

    return cabecera;
  }

  #renderLimites(): NodoDom {
    const contenedor = this.#dom.crearDiv();
    contenedor.classList.add("editor-perfil__limites");
    const titulo = this.#dom.crearSpan();
    titulo.classList.add("editor-perfil__titulo-seccion");
    titulo.textContent = t("perfiles.limites");
    contenedor.appendChild(titulo);

    if (this.#perfil.limites.length === 0) {
      const vacio = this.#dom.crearSpan();
      vacio.textContent = t("perfiles.sinLimites");
      contenedor.appendChild(vacio);
      return contenedor;
    }

    for (const limite of this.#perfil.limites) contenedor.appendChild(this.#filaLimite(limite));
    return contenedor;
  }

  #filaLimite(limite: LimiteDeAlerta): NodoDom {
    const editable = puedeEditarDirectamente(this.#origen);
    const fila = this.#dom.crearDiv();
    fila.classList.add("editor-perfil__limite");

    const etiquetaRol = this.#dom.crearSpan();
    etiquetaRol.classList.add("editor-perfil__limite-rol");
    etiquetaRol.textContent = limite.rol;
    fila.appendChild(etiquetaRol);

    const conversion = this.#conversionDeRol(limite.rol);
    const decimales = this.#decimalesDeRol(limite.rol);
    const parametro = this.#parametroDeRol(limite.rol);

    for (const tope of limite.topes) {
      if (!topeEsEditable(tope)) {
        fila.appendChild(this.#notaCurvaNoEditable(tope.valor as Curva));
        continue;
      }
      const etiquetaNivel = tope.nivel === "aviso" ? t("perfiles.limiteAviso") : t("perfiles.limiteCritico");
      const valorMostrado = valorDeTopeMostrado(tope, conversion, parametro);
      fila.appendChild(
        this.#fila(
          etiquetaNivel,
          this.#campoNumero(valorMostrado, decimales, editable, (nuevoValor) =>
            this.#conError(() =>
              this.#actualizarPerfil(
                construirPerfil({
                  ...this.#perfil,
                  limites: this.#perfil.limites.map((l) =>
                    l.rol === limite.rol
                      ? actualizarValorDeTope(l, tope.nivel, nuevoValor, conversion, parametro)
                      : l,
                  ),
                }),
              ),
            ),
          ),
        ),
      );
    }

    if (limite.banda !== null) {
      fila.appendChild(this.#filaBanda(limite, limite.banda, conversion, decimales, parametro, editable));
    }

    return fila;
  }

  #filaBanda(
    limite: LimiteDeAlerta,
    banda: NonNullable<LimiteDeAlerta["banda"]>,
    conversion: Conversion,
    decimales: number,
    parametro: number | undefined,
    editable: boolean,
  ): NodoDom {
    if (!bandaEsEditable(banda)) {
      return this.#notaCurvaNoEditable(esCurva(banda.minimo) ? banda.minimo : (banda.maximo as Curva));
    }

    const contenedor = this.#dom.crearDiv();
    contenedor.classList.add("editor-perfil__banda");

    if (bandaEsEditableConSemiancho(conversion)) {
      const mostrada = bandaACentroYAnchoMostrado(banda, conversion, parametro);
      const aplicar = (centro: number, semiancho: number): void =>
        this.#conError(() =>
          this.#actualizarPerfil(
            construirPerfil({
              ...this.#perfil,
              limites: this.#perfil.limites.map((l) =>
                l.rol === limite.rol ? actualizarBandaCentroYAncho(l, { centro, semiancho }, conversion, parametro) : l,
              ),
            }),
          ),
        );
      contenedor.appendChild(
        this.#fila(
          t("perfiles.limiteBandaCentro"),
          this.#campoNumero(mostrada.centro, decimales, editable, (v) => aplicar(v, mostrada.semiancho)),
        ),
      );
      contenedor.appendChild(
        this.#fila(
          t("perfiles.limiteBandaSemiancho"),
          this.#campoNumero(mostrada.semiancho, decimales, editable, (v) => aplicar(mostrada.centro, v)),
        ),
      );
      return contenedor;
    }

    const mostrada = bandaAMinMaxMostrado(banda, conversion, parametro);
    const aplicar = (minimo: number, maximo: number): void =>
      this.#conError(() =>
        this.#actualizarPerfil(
          construirPerfil({
            ...this.#perfil,
            limites: this.#perfil.limites.map((l) =>
              l.rol === limite.rol ? actualizarBandaMinMax(l, { minimo, maximo }, conversion, parametro) : l,
            ),
          }),
        ),
      );
    contenedor.appendChild(
      this.#fila(
        t("perfiles.limiteBandaMinimo"),
        this.#campoNumero(mostrada.minimo, decimales, editable, (v) => aplicar(v, mostrada.maximo)),
      ),
    );
    contenedor.appendChild(
      this.#fila(
        t("perfiles.limiteBandaMaximo"),
        this.#campoNumero(mostrada.maximo, decimales, editable, (v) => aplicar(mostrada.minimo, v)),
      ),
    );
    return contenedor;
  }

  #notaCurvaNoEditable(curva: Curva): NodoDom {
    const nota = this.#dom.crearSpan();
    nota.classList.add("editor-perfil__curva-no-editable");
    nota.textContent = t("perfiles.limiteCurvaNoEditable", { rol: curva.rolReferencia });
    return nota;
  }

  #renderImportarExportar(): NodoDom {
    const contenedor = this.#dom.crearDiv();
    contenedor.classList.add("editor-perfil__importar-exportar");

    const areaImportar = this.#dom.crearTextarea();
    areaImportar.classList.add("editor-perfil__importar-texto");
    areaImportar.value = this.#textoImportar;
    areaImportar.addEventListener("change", (evento: Event) => {
      this.#textoImportar = (evento.target as unknown as { value: string }).value;
    });
    contenedor.appendChild(areaImportar);

    const botonImportar = this.#boton(t("perfiles.importarBoton"), () => this.#importar());
    contenedor.appendChild(botonImportar);

    if (this.#errorImportacion !== null) {
      const error = this.#dom.crearSpan();
      error.classList.add("editor-perfil__error-importacion");
      error.textContent = t("perfiles.importarError", { mensaje: this.#errorImportacion });
      contenedor.appendChild(error);
    }

    const botonExportar = this.#boton(t("perfiles.exportar"), () => this.#exportar());
    contenedor.appendChild(botonExportar);

    if (this.#textoExportado !== null) {
      const etiqueta = this.#dom.crearSpan();
      etiqueta.textContent = t("perfiles.exportarEtiqueta");
      contenedor.appendChild(etiqueta);

      const areaExportar = this.#dom.crearTextarea();
      areaExportar.classList.add("editor-perfil__exportar-texto");
      areaExportar.value = this.#textoExportado;
      areaExportar.disabled = true;
      contenedor.appendChild(areaExportar);
    }

    return contenedor;
  }

  // --------------------------------------------------------------------- //
  // Construcción de controles
  // --------------------------------------------------------------------- //
  #fila(etiquetaTexto: string, control: NodoDom): NodoDom {
    const fila = this.#dom.crearDiv();
    fila.classList.add("editor-perfil__fila");
    const etiqueta = this.#dom.crearSpan();
    etiqueta.classList.add("editor-perfil__etiqueta");
    etiqueta.textContent = etiquetaTexto;
    fila.appendChild(etiqueta);
    fila.appendChild(control);
    return fila;
  }

  #campoTexto(valor: string, editable: boolean, alCambiar: (valor: string) => void): NodoDom {
    const input = this.#dom.crearInput();
    input.type = "text";
    input.value = valor;
    input.disabled = !editable;
    input.addEventListener("change", (evento: Event) => alCambiar((evento.target as unknown as { value: string }).value));
    return input;
  }

  #campoTextoLargo(valor: string, editable: boolean, alCambiar: (valor: string) => void): NodoDom {
    const area = this.#dom.crearTextarea();
    area.value = valor;
    area.disabled = !editable;
    area.addEventListener("change", (evento: Event) => alCambiar((evento.target as unknown as { value: string }).value));
    return area;
  }

  #campoNumero(valor: number, decimales: number, editable: boolean, alCambiar: (valor: number) => void): NodoDom {
    const input = this.#dom.crearInput();
    input.type = "number";
    input.value = valor.toFixed(decimales);
    input.disabled = !editable;
    input.addEventListener("change", (evento: Event) => {
      const texto = (evento.target as unknown as { value: string }).value;
      const numero = Number(texto);
      if (Number.isFinite(numero)) alCambiar(numero);
    });
    return input;
  }

  #boton(etiqueta: string, alPulsar: () => void): BotonDom {
    const boton = this.#dom.crearBoton();
    boton.textContent = etiqueta;
    boton.addEventListener("click", () => alPulsar());
    return boton;
  }
}
