/**
 * `AsistenteImportacion`: los tres pasos de `docs/07` §7.8 —formato, tiempo,
 * canales— con previsualización viva (FG-11).
 *
 * MISMA PARTICIÓN QUE `canales/selector-canales.ts`
 * ====================================================
 * Este fichero es la parte IMPURA: posee un fragmento del DOM y lo mantiene
 * sincronizado a mano (ADR-006 extendido: nada de framework nuevo). Toda la
 * lógica que decide algo —repartir una fila, convertir una celda, saber si un
 * rol necesita confirmación— vive en módulos puros sin DOM
 * (`celdas.ts`, `deduccion.ts`, `tiempo.ts`, `previsualizacion.ts`, `campo.ts`)
 * y por eso son los que tienen pruebas; `vitest.config.ts` usa
 * `environment: "node"`, así que este fichero, como `selector-canales.ts` y
 * `main.ts`, no se prueba con vitest — hace falta un navegador de verdad para
 * decir algo útil sobre él. `documento` se inyecta por la misma razón que en
 * `tema/tema.ts` y `canales/selector-canales.ts`: F3-21 costó una ronda por
 * leer `document` directamente, y no hay motivo para repetir el error aquí.
 *
 * LA DISTINCIÓN QUE NO SE PUEDE PERDER AL PINTAR
 * =================================================
 * Cada control de los tres pasos representa un `Campo<T>` o un `RolPropuesto`
 * (`tipos.ts`), y CADA fila que los pinta pasa por `#etiqueta`/`#badgeCampo`/
 * `#badgeRol`, que añaden la clase `asistente-importacion__etiqueta--deducido`
 * / `--confirmado` (o, para roles, `asistente-importacion__badge--exacta` /
 * `--indexada` / `--difusa-pendiente` / `--difusa-confirmada`) y un `title` en
 * prosa. No hay ningún camino de render que pinte un valor sin decidir primero
 * cuál de los dos es: esos tres métodos son los únicos que tocan `.valor`, y
 * siempre reciben el `Campo`/`RolPropuesto` completo, nunca `.valor` suelto.
 *
 * QUÉ NO HACE ESTE COMPONENTE
 * =============================
 * No sondea el fichero por su cuenta: todo sondeo pasa por `PuertoImportacion`
 * (`puerto.ts`), cuya implementación real contra `dlv-api` no existe todavía
 * — ver la cabecera de ese fichero. Este componente SÍ recalcula en el
 * cliente todo lo que no necesita volver a sondear (repartir una fila con un
 * delimitador distinto, convertir una celda a otra unidad, la duración al
 * cambiar la clase de tiempo): eso es la "previsualización viva" que pide
 * §7.8, y no depende de que el endpoint exista.
 *
 * No guarda el perfil `.dlvimport` (docs/07 §7.9): eso es FG-12, una tarea
 * distinta. El callback `onCompletar` recibe la asignación completa —formato,
 * tiempo y canales, cada uno con su `Campo`/`RolPropuesto`— para que quien
 * implemente FG-12 tenga de dónde partir sin inventar de nuevo esta forma.
 */

import { editar } from "./campo.ts";
import { analizarFila, dividirCampos } from "./celdas.ts";
import {
  confirmarRol,
  requiereConfirmacion,
  resumirConfianza,
  textoPendientesDeConfirmar,
} from "./deduccion.ts";
import {
  celdaMostrada,
  type CeldaMostrada,
  type ConversionDeColumna,
  type RangoPlausible,
} from "./previsualizacion.ts";
import { calcularResumenTiempo, type ResumenTiempo } from "./tiempo.ts";
import type {
  CanalPropuesto,
  Campo,
  ClaseDeTiempo,
  PropuestaFormato,
  PropuestaTiempo,
} from "./tipos.ts";
import { necesitaFrecuenciaDelUsuario } from "./tipos.ts";
import type {
  PuertoImportacion,
  PuertoImportacionSinImplementar,
  RolDeCatalogo,
} from "./puerto.ts";
import { buscarDimension, buscarUnidad, ErrorDeUnidad } from "../unidades/resolucion.ts";
import type { CatalogoUnidades } from "../unidades/tipos.ts";

/** Lo que produce el asistente al terminar: la asignación completa, lista
 * para que FG-12 la serialice como `.dlvimport` (docs/07 §7.9). */
export interface ResultadoAsistenteImportacion {
  readonly formato: PropuestaFormato;
  readonly tiempo: PropuestaTiempo;
  readonly canales: readonly CanalPropuesto[];
}

export interface OpcionesAsistenteImportacion {
  readonly contenedor: HTMLElement;
  /** Opaca, igual que `FuenteDeDatos#abrirLog`: una ruta de fichero real. */
  readonly referenciaFichero: string;
  readonly puerto: PuertoImportacion;
  readonly catalogoUnidades: CatalogoUnidades;
  readonly onCompletar: (resultado: ResultadoAsistenteImportacion) => void;
  readonly onCancelar?: () => void;
  readonly documento?: Pick<Document, "createElement" | "createTextNode">;
}

const CLASES_DE_TIEMPO: readonly ClaseDeTiempo[] = [
  "hora_del_dia",
  "iso8601",
  "epoch_segundos",
  "epoch_milisegundos",
  "relativo",
  "contador_de_muestras",
  "fecha_y_hora_separadas",
  "ausente",
];

const ETIQUETA_CLASE_DE_TIEMPO: Record<ClaseDeTiempo, string> = {
  hora_del_dia: "Hora del día (HH:MM:SS.mmm)",
  iso8601: "ISO-8601",
  epoch_segundos: "Epoch, en segundos",
  epoch_milisegundos: "Epoch, en milisegundos",
  relativo: "Relativo al inicio",
  contador_de_muestras: "Contador de muestras (necesita frecuencia)",
  fecha_y_hora_separadas: "Fecha y hora en columnas separadas",
  ausente: "Sin columna de tiempo (eje sintético)",
};

function etiquetaOrigen(origen: "deducido" | "confirmado"): string {
  return origen === "deducido" ? "detectado" : "confirmado";
}

type Paso = 1 | 2 | 3;

export class AsistenteImportacion {
  readonly #contenedor: HTMLElement;
  readonly #documento: Pick<Document, "createElement" | "createTextNode">;
  readonly #puerto: PuertoImportacion;
  readonly #referencia: string;
  readonly #catalogoUnidades: CatalogoUnidades;
  readonly #onCompletar: (resultado: ResultadoAsistenteImportacion) => void;
  readonly #onCancelar: (() => void) | undefined;

  readonly #raiz: HTMLElement;
  readonly #cabecera: HTMLElement;
  readonly #cuerpo: HTMLElement;
  readonly #pie: HTMLElement;

  #paso: Paso | "cargando" | "error" = "cargando";
  #errorMensaje = "";

  #filasPrevia: readonly string[] = [];
  #formato: PropuestaFormato | null = null;

  #tiempo: PropuestaTiempo | null = null;
  #valoresTiempoDetectados: readonly string[] = [];

  #canales: CanalPropuesto[] = [];
  #catalogoRoles: readonly RolDeCatalogo[] = [];
  #ordenarPorAtencion = false;

  constructor(opciones: OpcionesAsistenteImportacion) {
    this.#contenedor = opciones.contenedor;
    this.#documento = opciones.documento ?? globalThis.document;
    this.#puerto = opciones.puerto;
    this.#referencia = opciones.referenciaFichero;
    this.#catalogoUnidades = opciones.catalogoUnidades;
    this.#onCompletar = opciones.onCompletar;
    this.#onCancelar = opciones.onCancelar;

    this.#raiz = this.#el("div", "asistente-importacion");
    this.#cabecera = this.#el("div", "asistente-importacion__cabecera");
    this.#cuerpo = this.#el("div", "asistente-importacion__cuerpo");
    this.#pie = this.#el("div", "asistente-importacion__pie");
    this.#raiz.append(this.#cabecera, this.#cuerpo, this.#pie);
    this.#contenedor.append(this.#raiz);

    this.#renderCargando(`sondeando «${this.#referencia}»…`);
    void this.#iniciar();
  }

  /** Quita el fragmento del DOM. No se puede seguir usando la instancia tras esto. */
  destruir(): void {
    this.#contenedor.replaceChildren();
  }

  // --------------------------------------------------------------------- //
  // Orquestación de los tres pasos
  // --------------------------------------------------------------------- //

  async #iniciar(): Promise<void> {
    try {
      const resultado = await this.#puerto.sondearFormato(this.#referencia);
      this.#formato = resultado.propuesta;
      this.#filasPrevia = resultado.filasPrevia;
      try {
        this.#catalogoRoles = await this.#puerto.catalogoRoles();
      } catch {
        // El informe de plausibilidad se degrada sin rango, no se bloquea el
        // paso 3 por esto (docs/07 §7.7 punto 2 es una mejora, no un requisito).
        this.#catalogoRoles = [];
      }
      this.#paso = 1;
      this.#render();
    } catch (error) {
      this.#mostrarError(error);
    }
  }

  async #avanzar(): Promise<void> {
    if (this.#paso === 1 && this.#formato !== null) {
      this.#renderCargando("sondeando la columna de tiempo…");
      try {
        const resultado = await this.#puerto.sondearTiempo(this.#referencia, this.#formato);
        this.#tiempo = resultado.propuesta;
        this.#valoresTiempoDetectados = resultado.valoresBrutos;
        this.#paso = 2;
        this.#render();
      } catch (error) {
        this.#mostrarError(error);
      }
      return;
    }
    if (this.#paso === 2 && this.#formato !== null && this.#tiempo !== null) {
      this.#renderCargando("sondeando los canales…");
      try {
        const resultado = await this.#puerto.sondearCanales(this.#referencia, this.#formato, this.#tiempo);
        this.#canales = [...resultado.canales];
        this.#paso = 3;
        this.#render();
      } catch (error) {
        this.#mostrarError(error);
      }
      return;
    }
    if (this.#paso === 3) {
      this.#finalizar();
    }
  }

  #retroceder(): void {
    if (this.#paso === 2) this.#paso = 1;
    else if (this.#paso === 3) this.#paso = 2;
    this.#render();
  }

  #finalizar(): void {
    if (this.#formato === null || this.#tiempo === null) return;
    this.#onCompletar({ formato: this.#formato, tiempo: this.#tiempo, canales: [...this.#canales] });
  }

  // --------------------------------------------------------------------- //
  // Render
  // --------------------------------------------------------------------- //

  #render(): void {
    this.#cabecera.replaceChildren(this.#pasos());
    if (this.#paso === 1) this.#renderPaso1();
    else if (this.#paso === 2) this.#renderPaso2();
    else if (this.#paso === 3) this.#renderPaso3();
    this.#renderPie();
  }

  #pasos(): HTMLElement {
    const lista = this.#el("ol", "asistente-importacion__pasos");
    const nombres = ["Formato", "Tiempo", "Canales"];
    nombres.forEach((nombre, i) => {
      const item = this.#el("li", "asistente-importacion__paso");
      if (this.#paso === i + 1) item.classList.add("asistente-importacion__paso--activo");
      item.append(this.#texto(`${i + 1}. ${nombre}`));
      lista.append(item);
    });
    return lista;
  }

  #renderCargando(mensaje: string): void {
    this.#paso = "cargando";
    this.#cabecera.replaceChildren();
    this.#cuerpo.replaceChildren(this.#texto(mensaje));
    this.#pie.replaceChildren();
  }

  #mostrarError(error: unknown): void {
    this.#paso = "error";
    this.#errorMensaje = error instanceof Error ? error.message : String(error);
    this.#cabecera.replaceChildren();
    const panel = this.#el("div", "asistente-importacion__error");
    panel.append(
      this.#texto("No se puede continuar todavía: "),
      this.#texto(this.#errorMensaje),
    );
    this.#cuerpo.replaceChildren(panel);
    this.#pie.replaceChildren();
    if (this.#onCancelar !== undefined) {
      const boton = this.#boton("Cerrar", () => this.#onCancelar?.());
      this.#pie.append(boton);
    }
  }

  #renderPie(): void {
    this.#pie.replaceChildren();
    if (this.#paso !== 1 && this.#paso !== 2 && this.#paso !== 3) return;
    if (this.#onCancelar !== undefined) {
      this.#pie.append(this.#boton("Cancelar", () => this.#onCancelar?.()));
    }
    if (this.#paso !== 1) {
      this.#pie.append(this.#boton("Atrás", () => this.#retroceder()));
    }
    const etiquetaSiguiente = this.#paso === 3 ? "Importar" : "Siguiente";
    this.#pie.append(this.#boton(etiquetaSiguiente, () => void this.#avanzar()));
  }

  // --------------------------------------------------------------------- //
  // Paso 1 — formato
  // --------------------------------------------------------------------- //

  #renderPaso1(): void {
    if (this.#formato === null) return;
    const formato = this.#formato;
    const cuerpo = this.#el("div", "asistente-importacion__paso1");

    cuerpo.append(
      this.#filaCampoTexto("Codificación", formato.codificacion, (v) => {
        this.#formato = { ...formato, codificacion: editar(formato.codificacion, v) };
        this.#renderPaso1();
      }),
      this.#filaCampoTexto("Delimitador", formato.delimitador, (v) => {
        this.#formato = { ...formato, delimitador: editar(formato.delimitador, v === "" ? null : v) };
        this.#renderPaso1();
      }),
      this.#filaCampoTexto("Comilla", formato.comilla, (v) => {
        this.#formato = { ...formato, comilla: editar(formato.comilla, v === "" ? null : v) };
        this.#renderPaso1();
      }),
      this.#filaCampoTexto("Separador decimal", formato.decimal, (v) => {
        if (v !== "." && v !== ",") return;
        this.#formato = { ...formato, decimal: editar(formato.decimal, v) };
        this.#renderPaso1();
      }),
    );

    if (formato.delimitador.valor === null) {
      const aviso = this.#el("p", "asistente-importacion__aviso");
      aviso.append(
        this.#texto(
          "El sondeo no propone ningún delimitador con suficiente consistencia: elige uno para " +
            "poder continuar (docs/07 §7.4).",
        ),
      );
      cuerpo.append(aviso);
    }

    cuerpo.append(this.#el("h3", undefined, "Previsualización (las primeras filas, en vivo)"));
    cuerpo.append(this.#tablaPreviaCruda(formato));
    this.#cuerpo.replaceChildren(cuerpo);
  }

  /**
   * A qué papel corresponde la línea `indice` de `#filasPrevia`, según los
   * tres índices de `PropuestaFormato`. Se enseña como primera columna de la
   * tabla del paso 1 para que mover `filaCabecera`/`filaUnidades`/`filaDatos`
   * tenga un efecto visible inmediato — sin esto, la tabla de previsualización
   * confunde "todavía no sé cuál es la fila de datos" con "esto ya son datos",
   * que es precisamente la clase de error que §7.15 pide evitar.
   */
  #papelDeLinea(indice: number, formato: PropuestaFormato): string {
    if (indice === formato.filaCabecera.valor) return "cabecera";
    if (indice === formato.filaUnidades.valor) return "unidades";
    if (indice >= formato.filaDatos.valor) return "datos";
    return "preámbulo";
  }

  /**
   * Las filas de `#filasPrevia` a partir de `filaDatos`, para cualquier
   * cálculo que necesite SOLO datos (paso 2 y paso 3): sin este filtro, una
   * fila de cabecera o de unidades se cuela como un valor de columna de
   * tiempo o de canal, y el aviso que sale es un falso positivo con la forma
   * de un valor real — el efecto que este proyecto evita a propósito
   * (`docs/09` §9.10, y §7.15 en general).
   */
  #filasDeDatos(formato: PropuestaFormato): readonly string[] {
    return this.#filasPrevia.slice(formato.filaDatos.valor);
  }

  #tablaPreviaCruda(formato: PropuestaFormato): HTMLElement {
    const tabla = this.#el("table", "asistente-importacion__tabla");
    const delimitador = formato.delimitador.valor ?? ",";
    const cuerpoTabla = this.#el("tbody");
    this.#filasPrevia.forEach((linea, indice) => {
      const fila = analizarFila(linea, {
        delimitador,
        comilla: formato.comilla.valor,
        decimal: formato.decimal.valor,
      });
      const tr = this.#el("tr");
      const papel = this.#papelDeLinea(indice, formato);
      tr.classList.add(`asistente-importacion__fila--${papel}`);
      const tdPapel = this.#el("td", "asistente-importacion__papel-fila");
      tdPapel.append(this.#texto(papel));
      tr.append(tdPapel);
      for (const celda of fila) {
        const td = this.#el("td");
        if (celda.tipo === "hueco") {
          td.classList.add("asistente-importacion__hueco");
          td.title = "hueco: sin dato en el fichero (nunca se muestra como 0)";
        } else {
          td.append(this.#texto(celda.texto));
        }
        tr.append(td);
      }
      cuerpoTabla.append(tr);
    });
    tabla.append(cuerpoTabla);
    return tabla;
  }

  // --------------------------------------------------------------------- //
  // Paso 2 — tiempo
  // --------------------------------------------------------------------- //

  #renderPaso2(): void {
    if (this.#tiempo === null || this.#formato === null) return;
    const tiempo = this.#tiempo;
    const cuerpo = this.#el("div", "asistente-importacion__paso2");

    const filaClase = this.#el("div", "asistente-importacion__campo");
    filaClase.append(this.#etiqueta("Qué es la columna de tiempo", tiempo.clase.origen));
    const select = this.#el("select") as HTMLSelectElement;
    for (const clase of CLASES_DE_TIEMPO) {
      const opcion = this.#el("option") as HTMLOptionElement;
      opcion.value = clase;
      opcion.textContent = ETIQUETA_CLASE_DE_TIEMPO[clase];
      opcion.selected = clase === tiempo.clase.valor;
      select.append(opcion);
    }
    select.addEventListener("change", () => {
      const nuevaClase = select.value as ClaseDeTiempo;
      this.#tiempo = { ...tiempo, clase: editar(tiempo.clase, nuevaClase) };
      this.#renderPaso2();
    });
    filaClase.append(select);
    cuerpo.append(filaClase);

    if (necesitaFrecuenciaDelUsuario(tiempo.clase.valor)) {
      const filaFrecuencia = this.#el("div", "asistente-importacion__campo");
      filaFrecuencia.append(this.#etiqueta("Frecuencia de muestreo (Hz)", tiempo.frecuenciaHz.origen));
      const input = this.#el("input") as HTMLInputElement;
      input.type = "number";
      input.min = "0";
      input.value = tiempo.frecuenciaHz.valor === null ? "" : String(tiempo.frecuenciaHz.valor);
      input.addEventListener("change", () => {
        const valor = input.valueAsNumber;
        this.#tiempo = {
          ...tiempo,
          frecuenciaHz: editar(tiempo.frecuenciaHz, Number.isFinite(valor) && valor > 0 ? valor : null),
        };
        this.#renderPaso2();
      });
      filaFrecuencia.append(input);
      cuerpo.append(filaFrecuencia);

      const aviso = this.#el("p", "asistente-importacion__aviso");
      aviso.append(
        this.#texto(
          "Sin columna de tiempo fiable el eje será sintético (docs/07 §7.5): la vista " +
            "concatenada con otros logs exigirá desfase manual.",
        ),
      );
      cuerpo.append(aviso);
    }

    const resumen = this.#calcularResumenParaEstadoActual();
    cuerpo.append(this.#el("h3", undefined, "Efecto de esta interpretación (en vivo)"));
    const resumenEl = this.#el("dl", "asistente-importacion__resumen");
    resumenEl.append(
      ...this.#parDefinicion("Muestras", String(resumen.muestras) + (resumen.esEstimacion ? " (estimado)" : "")),
      ...this.#parDefinicion(
        "Duración",
        resumen.duracionS === null ? "—" : `${resumen.duracionS.toFixed(3)} s`,
      ),
      ...this.#parDefinicion(
        "Tasa media",
        resumen.frecuenciaHz === null ? "—" : `${resumen.frecuenciaHz.toFixed(2)} Hz`,
      ),
    );
    cuerpo.append(resumenEl);
    for (const aviso of resumen.avisos) {
      const p = this.#el("p", "asistente-importacion__aviso");
      p.append(this.#texto(aviso));
      cuerpo.append(p);
    }

    this.#cuerpo.replaceChildren(cuerpo);
  }

  /**
   * Reparte de nuevo las filas de muestra con el formato YA confirmado y
   * calcula el resumen del paso 2 sobre la columna elegida — todo en el
   * cliente, sin volver a sondear, que es lo que hace que el paso 2 sea "en
   * vivo" ante un cambio de clase o de frecuencia.
   */
  #calcularResumenParaEstadoActual(): ResumenTiempo {
    const tiempo = this.#tiempo;
    const formato = this.#formato;
    if (tiempo === null || formato === null) {
      return { muestras: 0, pasoMedianoS: null, frecuenciaHz: null, duracionS: null, esEstimacion: true, avisos: [] };
    }
    const columna = tiempo.columna.valor;
    const valores =
      columna === null
        ? this.#valoresTiempoDetectados
        : this.#filasDeDatos(formato).map(
            (linea) =>
              dividirCampos(linea, formato.delimitador.valor ?? ",", formato.comilla.valor)[columna] ?? "",
          );
    return calcularResumenTiempo({
      clase: tiempo.clase.valor,
      valoresBrutos: valores,
      decimal: formato.decimal.valor,
      factorASegundos: tiempo.factorASegundos,
      frecuenciaHz: tiempo.frecuenciaHz.valor,
    });
  }

  // --------------------------------------------------------------------- //
  // Paso 3 — canales
  // --------------------------------------------------------------------- //

  #renderPaso3(): void {
    const cuerpo = this.#el("div", "asistente-importacion__paso3");

    const resumenConfianza = resumirConfianza(this.#canales);
    const textoBanner = textoPendientesDeConfirmar(resumenConfianza);
    if (textoBanner !== "") {
      const banner = this.#el("p", "asistente-importacion__banner-difusas");
      banner.append(this.#texto(textoBanner));
      cuerpo.append(banner);
    }

    const botonOrdenar = this.#boton(
      this.#ordenarPorAtencion ? "Orden original" : "Ordenar por «necesita atención»",
      () => {
        this.#ordenarPorAtencion = !this.#ordenarPorAtencion;
        this.#renderPaso3();
      },
    );
    cuerpo.append(botonOrdenar);

    cuerpo.append(this.#tablaCanales());
    this.#cuerpo.replaceChildren(cuerpo);
  }

  /** Puntuación de "necesita atención": más alto, más urgente de revisar. */
  #puntuacionAtencion(canal: CanalPropuesto): number {
    let puntos = 0;
    if (requiereConfirmacion(canal.rol)) puntos += 100;
    if (canal.rol === null) puntos += 10;
    if (canal.dimensionId.valor === "unknown") puntos += 10;
    puntos += canal.avisos.length;
    return puntos;
  }

  #tablaCanales(): HTMLElement {
    const canales = this.#ordenarPorAtencion
      ? [...this.#canales].sort((a, b) => this.#puntuacionAtencion(b) - this.#puntuacionAtencion(a))
      : this.#canales;

    const tabla = this.#el("table", "asistente-importacion__tabla-canales");
    const encabezado = this.#el("tr");
    for (const titulo of ["Columna", "Nombre", "Tipo", "Dimensión", "Unidad de origen", "Rol", "Avisos"]) {
      const th = this.#el("th");
      th.append(this.#texto(titulo));
      encabezado.append(th);
    }
    const thead = this.#el("thead");
    thead.append(encabezado);
    tabla.append(thead);

    const tbody = this.#el("tbody");
    for (const canal of canales) {
      tbody.append(this.#filaCanal(canal));
    }
    tabla.append(tbody);

    if (this.#filasPrevia.length > 0 && this.#formato !== null) {
      tabla.append(this.#el("caption", undefined, "Previsualización con la conversión aplicada"));
      tbody.append(...this.#filasPreviaCanales(canales));
    }
    return tabla;
  }

  #filaCanal(canal: CanalPropuesto): HTMLElement {
    const tr = this.#el("tr");
    if (this.#puntuacionAtencion(canal) > 0) tr.classList.add("asistente-importacion__fila--atencion");

    tr.append(this.#celda(String(canal.columna)), this.#celda(canal.nombreOriginal), this.#celda(canal.tipoInferido));

    const tdDimension = this.#el("td");
    tdDimension.append(this.#badgeCampo(canal.dimensionId));
    tr.append(tdDimension);

    const tdUnidad = this.#el("td");
    tdUnidad.append(this.#badgeCampo(canal.unidadOrigen, (v) => v ?? "—"));
    tr.append(tdUnidad);

    const tdRol = this.#el("td");
    tdRol.append(this.#badgeRol(canal));
    tr.append(tdRol);

    const tdAvisos = this.#el("td");
    tdAvisos.append(this.#texto(canal.avisos.join("; ")));
    tr.append(tdAvisos);

    return tr;
  }

  /**
   * El badge que distingue a la vista una deducción de una confirmación, para
   * cualquier `Campo<T>`. Es EL sitio donde vive esa distinción visual: si
   * algún día se pinta un campo sin pasar por aquí, se ha roto la regla no
   * negociable de la tarea.
   */
  #badgeCampo<T>(campo: Campo<T>, formatear: (v: T) => string = (v) => String(v)): HTMLElement {
    const span = this.#el("span", `asistente-importacion__badge asistente-importacion__badge--${campo.origen}`);
    span.title =
      campo.origen === "deducido"
        ? "Propuesto por el sondeo. Revísalo: nada se ha confirmado todavía."
        : "Confirmado.";
    span.append(this.#texto(`${formatear(campo.valor)} (${etiquetaOrigen(campo.origen)})`));
    return span;
  }

  /**
   * El badge de rol: además de deducido/confirmado, distingue las TRES
   * confianzas de `dlv_core.roles.Confianza` y hace visible + accionable la
   * regla de `docs/07` §7.15 — una DIFUSA sin confirmar lleva un botón de
   * confirmación justo al lado, porque confirmarla es la única forma de que
   * los detectores críticos que la necesiten vuelvan a activarse
   * (`deduccion.ts#debeDesactivarDetectorCritico`).
   */
  #badgeRol(canal: CanalPropuesto): HTMLElement {
    const contenedor = this.#el("span", "asistente-importacion__rol");
    if (canal.rol === null) {
      contenedor.append(this.#texto("(sin rol)"));
      return contenedor;
    }
    const rol = canal.rol;
    const pendiente = requiereConfirmacion(rol);
    const claseConfianza =
      rol.confianza === "EXACTA"
        ? "exacta"
        : rol.confianza === "INDEXADA"
          ? "indexada"
          : pendiente
            ? "difusa-pendiente"
            : "difusa-confirmada";
    const badge = this.#el("span", `asistente-importacion__badge asistente-importacion__badge--${claseConfianza}`);
    const indice = rol.indice === null ? "" : `[${rol.indice}]`;
    badge.title =
      rol.confianza === "DIFUSA"
        ? `Propuesto por parecido con «${rol.sinonimo}» (${(rol.parecido * 100).toFixed(0)} %). ` +
          "Sin confirmar, los detectores críticos que dependan de este rol quedan desactivados en este log."
        : `Coincidencia ${rol.confianza.toLowerCase()} con «${rol.sinonimo}».`;
    badge.append(this.#texto(`${rol.rol}${indice} — ${rol.confianza}`));
    contenedor.append(badge);

    if (pendiente) {
      const boton = this.#boton("Confirmar", () => {
        this.#confirmarRolDelCanal(canal.columna);
        this.#renderPaso3();
      });
      boton.classList.add("asistente-importacion__confirmar-rol");
      contenedor.append(boton);
    }
    return contenedor;
  }

  /**
   * Sustituye, en `this.#canales` (la fuente de verdad; `#tablaCanales` puede
   * estar pintando una COPIA ordenada), el canal de esta columna por uno
   * nuevo con el rol confirmado. Inmutable a propósito: un `CanalPropuesto`
   * es `readonly` en sus campos, y mutarlo en el sitio rompería esa garantía
   * de tipos con un `Object.assign` que el compilador no puede vigilar.
   */
  #confirmarRolDelCanal(columna: number): void {
    this.#canales = this.#canales.map((c) =>
      c.columna === columna && c.rol !== null ? { ...c, rol: confirmarRol(c.rol) } : c,
    );
  }

  /**
   * Las filas de previsualización del paso 3, con la conversión de cada
   * canal ya aplicada (`previsualizacion.ts`). Un canal sin dimensión
   * resuelta se muestra en crudo (§7.15 mitigación 3); un hueco se muestra
   * como hueco (§7.10).
   */
  #filasPreviaCanales(canales: readonly CanalPropuesto[]): HTMLElement[] {
    const formato = this.#formato;
    if (formato === null) return [];
    const delimitador = formato.delimitador.valor ?? ",";
    const conversiones = canales.map((c) => this.#conversionDeCanal(c));
    const rangos = canales.map((c) => this.#rangoPlausibleDeCanal(c));

    return this.#filasDeDatos(formato).map((linea) => {
      const fila = analizarFila(linea, { delimitador, comilla: formato.comilla.valor, decimal: formato.decimal.valor });
      const tr = this.#el("tr", "asistente-importacion__fila-previa");
      canales.forEach((canal, i) => {
        const celdaCruda = fila[canal.columna];
        const mostrada: CeldaMostrada =
          celdaCruda === undefined
            ? { texto: "", esHueco: true, esCrudo: false, esSospechosa: false }
            : celdaMostrada(celdaCruda, conversiones[i]!, { rango: rangos[i] });
        const td = this.#el("td");
        if (mostrada.esHueco) {
          td.classList.add("asistente-importacion__hueco");
          td.title = "hueco: sin dato";
        } else {
          if (mostrada.esCrudo) td.classList.add("asistente-importacion__crudo");
          if (mostrada.esSospechosa) {
            td.classList.add("asistente-importacion__sospechosa");
            td.title = "fuera del rango plausible declarado para este rol (docs/07 §7.7)";
          }
          td.append(this.#texto(mostrada.texto));
        }
        tr.append(td);
      });
      return tr;
    });
  }

  #conversionDeCanal(canal: CanalPropuesto): ConversionDeColumna {
    if (canal.dimensionId.valor === "unknown" || canal.unidadOrigen.valor === null) {
      return { conversionDeOrigen: null, conversionDeMostrada: null, decimales: 2 };
    }
    try {
      const dimension = buscarDimension(this.#catalogoUnidades, canal.dimensionId.valor);
      const unidadOrigen = buscarUnidad(dimension, canal.unidadOrigen.valor);
      // Se muestra en la propia unidad de origen (paso 3 confirma la
      // INTERPRETACIÓN, no elige la unidad de visualización final: eso es el
      // selector de unidad de la aplicación abierta, F1-31).
      return {
        conversionDeOrigen: unidadOrigen.conversion,
        conversionDeMostrada: unidadOrigen.conversion,
        decimales: unidadOrigen.decimales,
      };
    } catch (error) {
      if (error instanceof ErrorDeUnidad) {
        return { conversionDeOrigen: null, conversionDeMostrada: null, decimales: 2 };
      }
      throw error;
    }
  }

  #rangoPlausibleDeCanal(canal: CanalPropuesto): RangoPlausible | null {
    if (canal.rol === null) return null;
    const entrada = this.#catalogoRoles.find((r) => r.id === canal.rol?.rol);
    if (entrada === undefined) return null;
    return { min: entrada.plausibleMin, max: entrada.plausibleMax };
  }

  // --------------------------------------------------------------------- //
  // Utilidades de construcción de DOM
  // --------------------------------------------------------------------- //

  #el(etiqueta: string, clase?: string, texto?: string): HTMLElement {
    const elemento = this.#documento.createElement(etiqueta) as HTMLElement;
    if (clase !== undefined) elemento.className = clase;
    if (texto !== undefined) elemento.append(this.#texto(texto));
    return elemento;
  }

  #texto(contenido: string): Text {
    return this.#documento.createTextNode(contenido);
  }

  #boton(etiqueta: string, alPulsar: () => void): HTMLButtonElement {
    const boton = this.#documento.createElement("button") as HTMLButtonElement;
    boton.type = "button";
    boton.textContent = etiqueta;
    boton.addEventListener("click", alPulsar);
    return boton;
  }

  #celda(texto: string): HTMLElement {
    const td = this.#el("td");
    td.append(this.#texto(texto));
    return td;
  }

  #etiqueta(texto: string, origen: "deducido" | "confirmado"): HTMLElement {
    const label = this.#el("label", `asistente-importacion__etiqueta asistente-importacion__etiqueta--${origen}`);
    label.append(this.#texto(`${texto} (${etiquetaOrigen(origen)})`));
    return label;
  }

  #parDefinicion(termino: string, valor: string): HTMLElement[] {
    const dt = this.#el("dt", undefined, termino);
    const dd = this.#el("dd", undefined, valor);
    return [dt, dd];
  }

  #filaCampoTexto(
    etiqueta: string,
    campo: Campo<string | null>,
    alCambiar: (valorNuevo: string) => void,
  ): HTMLElement {
    const fila = this.#el("div", "asistente-importacion__campo");
    fila.append(this.#etiqueta(etiqueta, campo.origen));
    const input = this.#documento.createElement("input") as HTMLInputElement;
    input.type = "text";
    input.value = campo.valor ?? "";
    input.addEventListener("change", () => alCambiar(input.value));
    fila.append(input);
    return fila;
  }
}

// Reexportado para que quien construya el puerto real no tenga que importar
// dos módulos para manejar el único error que puede lanzar hoy.
export type { PuertoImportacionSinImplementar };
