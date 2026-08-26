/**
 * `PropuestaPerfil`: el aviso de onboarding de F5-11 (E9.6, «Onboarding:
 * propuesta de perfil en lugar de lienzo vacío»).
 *
 * SOLO PINTA -- LA DECISIÓN DE QUÉ TEXTO VA EN CADA CASO ES DE `contenido.ts`
 * =============================================================================
 * Este módulo no calcula la frase de cobertura ni decide si hay que listar
 * roles que faltan: eso es `contenido.ts#contenidoDePropuesta`, puro y
 * probado en Node sin `document` (misma partición que `malla/geometria.ts`
 * frente a `malla/mapa-de-calor.ts`, ver la cabecera de aquel fichero). Aquí
 * solo se crean los nodos con ese texto ya resuelto y se enganchan los dos
 * botones a los callbacks que quien monta el componente decida.
 *
 * QUÉ RECIBE Y QUÉ NO CALCULA
 * =============================
 * Recibe UNA `SugerenciaDePerfil` (`tipos.ts`) o `null` -- ya resuelta por
 * `dlv_core.sugerencia_perfil` (F3-04), igual que `ejes/ejes.ts#pintarEjes` o
 * `topes/topes.ts` reciben la geometría ya calculada y solo la pintan. No
 * decide qué pasa al pulsar los botones: eso son `onAceptar`/`onDescartar`,
 * que quien monta el componente (`app/aplicacion.ts`) conecta a
 * `preseleccionar` sobre el selector de canales y a
 * `onboarding/decision-guardada.ts` para no volver a preguntar.
 *
 * SE PROPONE, NO SE IMPONE (DECISIÓN 2 DEL INFORME)
 * ====================================================
 * Este componente no se autooculta ni recuerda nada: cada vez que se
 * construye, pinta. Quien decide si hace falta preguntar OTRA VEZ es `app/
 * aplicacion.ts`, consultando `onboarding/decision-guardada.ts` ANTES de
 * decidir si construye una instancia -- así este módulo se queda simple (una
 * función de datos a DOM) y la política de "no preguntes dos veces" vive en
 * un solo sitio, no repartida entre el componente y quien lo llama.
 */

import { t } from "../locale/catalogo.ts";
import { contenidoDePropuesta } from "./contenido.ts";
import type { SugerenciaDePerfil } from "./tipos.ts";

export interface OpcionesPropuestaPerfil {
  readonly contenedor: HTMLElement;
  readonly sugerencia: SugerenciaDePerfil | null;
  /** Se llama al pulsar "usar este perfil". Se ignora si `sugerencia` es `null`: no hay nada que aceptar. */
  readonly onAceptar?: () => void;
  /** Se llama al pulsar "no, gracias". Se ignora si `sugerencia` es `null`: no hay nada que descartar. */
  readonly onDescartar?: () => void;
  /**
   * Superficie mínima de `Document`. Por omisión el global -- mismo patrón y
   * mismo motivo que `canales/selector-canales.ts#OpcionesSelectorCanales`:
   * sin esto, `app/aplicacion.ts` no se podría montar en una prueba
   * (`vitest.config.ts` corre en `environment: "node"`, sin `document`).
   */
  readonly documento?: Pick<Document, "createElement">;
}

export class PropuestaPerfil {
  readonly #contenedor: HTMLElement;

  constructor(opciones: OpcionesPropuestaPerfil) {
    this.#contenedor = opciones.contenedor;
    const documento = opciones.documento ?? globalThis.document;
    const contenido = contenidoDePropuesta(opciones.sugerencia);

    const raiz = documento.createElement("div");
    raiz.className = "dlv-propuesta-perfil";
    raiz.classList.add(
      contenido.tieneAcciones ? "dlv-propuesta-perfil--propuesta" : "dlv-propuesta-perfil--sin-perfil",
    );

    const texto = documento.createElement("p");
    texto.className = "dlv-propuesta-perfil__texto";
    texto.textContent = contenido.textoPrincipal;
    raiz.append(texto);

    if (contenido.textoFaltan !== null) {
      const faltan = documento.createElement("p");
      faltan.className = "dlv-propuesta-perfil__faltan";
      faltan.textContent = contenido.textoFaltan;
      raiz.append(faltan);
    }

    if (contenido.tieneAcciones) {
      raiz.append(this.#construirAcciones(documento, opciones.onAceptar, opciones.onDescartar));
    }

    this.#contenedor.replaceChildren(raiz);
  }

  #construirAcciones(
    documento: Pick<Document, "createElement">,
    onAceptar: (() => void) | undefined,
    onDescartar: (() => void) | undefined,
  ): HTMLElement {
    const acciones = documento.createElement("div");
    acciones.className = "dlv-propuesta-perfil__acciones";

    const aceptar = documento.createElement("button");
    aceptar.type = "button";
    aceptar.className = "dlv-propuesta-perfil__aceptar";
    // El rótulo no sale de `contenido.ts`: no depende de la sugerencia (es el
    // mismo texto siempre que hay acciones que pintar), así que traducirlo
    // aquí no rompe la partición pura/DOM -- la parte "pura" de esta decisión
    // es solo `contenido.tieneAcciones`, ya resuelta antes de llegar aquí.
    aceptar.textContent = t("onboarding.propuestaAceptar");
    aceptar.addEventListener("click", () => onAceptar?.());

    const descartar = documento.createElement("button");
    descartar.type = "button";
    descartar.className = "dlv-propuesta-perfil__descartar";
    descartar.textContent = t("onboarding.propuestaDescartar");
    descartar.addEventListener("click", () => onDescartar?.());

    acciones.append(aceptar, descartar);
    return acciones;
  }

  /** Vacía el contenedor donde se montó. No se puede seguir usando la instancia tras esto. */
  destruir(): void {
    this.#contenedor.replaceChildren();
  }
}
