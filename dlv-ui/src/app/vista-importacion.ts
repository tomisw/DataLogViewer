/**
 * `crearVistaImportacion`: adapta `AsistenteImportacion`
 * (`importacion/asistente-importacion.ts`) a `DefinicionVista` (`app/vistas.ts`)
 * — el cableado que docs/02 §2.10 pedía para FG-11: trece módulos verdes y
 * probados (`importacion/*`, 14 677 líneas medidas contra `app/`) sin ningún
 * sitio real donde montarse. Este fichero es ESE sitio, mismo papel que
 * `vista-incidencias.ts` para `panel-incidencias.ts`.
 *
 * DOS PANTALLAS, NO UNA
 * ======================
 * `AsistenteImportacion` exige una `referenciaFichero` ya elegida en su
 * constructor (`OpcionesAsistenteImportacion.referenciaFichero`) y no hay,
 * en ningún sitio de `dlv-ui`, un selector de fichero nativo: ni `dlv-api` ni
 * `datos/fuente.ts#FuenteDeDatos` ofrecen uno, y esta tarea no inventa un
 * diálogo del sistema de ficheros que no existe. Por eso esta vista tiene un
 * primer paso propio y minúsculo —un campo de texto con la ruta y un botón—
 * antes de montar el asistente de verdad. Es opaco a propósito, mismo
 * criterio que `FuenteDeDatos#abrirLog`: una ruta real para `PuertoImportacionApi`
 * el día que exista, lo que sea para una fuente de pruebas.
 *
 * POR QUÉ SE MONTA CON `PuertoImportacionApi`, Y QUÉ SE VE CUANDO FALLA
 * ========================================================================
 * `importacion/puerto.ts` deja dicho, tras leer `dlv-api/src/dlv_api/main.py`
 * entero, que HOY no existe ningún endpoint de sondeo de CSV genérico:
 * `PuertoImportacionApi` no es un ESBOZO que aquí se rellene con datos de
 * mentira, es la implementación real y su comportamiento real es lanzar
 * `PuertoImportacionSinImplementar` con el endpoint que falta. No se sustituye
 * por un doble sintético en esta vista (eso ocultaría justo la información que
 * el usuario necesita: que nada se ha importado todavía). El aviso completo se
 * ve dos veces, a propósito:
 *
 *   1. Antes de pulsar nada, esta pantalla ya dice en prosa que el sondeo no
 *      existe todavía en `dlv-api`.
 *   2. Si aun así se pulsa "Sondear", `AsistenteImportacion#iniciar` llama a
 *      `sondearFormato`, la promesa rechaza, y el propio asistente entra en su
 *      paso "error" (`#mostrarError`) mostrando el mensaje literal de
 *      `PuertoImportacionSinImplementar` — que nombra el endpoint exacto que
 *      falta cablear en `dlv_api.main.crear_app`.
 *
 * El día que `dlv-api` sirva esas cuatro rutas, esta vista no cambia una
 * línea: `PuertoImportacionApi` deja de lanzar y el asistente avanza de
 * verdad, con la misma pantalla de selección de fichero de hoy.
 *
 * QUÉ PASA CON EL RESULTADO, SI ALGUNA VEZ SE LLEGA A ÉL
 * =========================================================
 * `onCompletar` recibe la asignación completa (formato, tiempo, canales) tal
 * como la deja el asistente. No hay ningún endpoint que aplique esa asignación
 * a un log real ni ningún perfil `.dlvimport` que guardarla (FG-12, tarea
 * aparte según la propia cabecera de `asistente-importacion.ts`): por eso el
 * panel de resultado dice explícitamente que la asignación queda en memoria de
 * la vista y no en ningún sitio, en vez de fingir que "se importó".
 *
 * DESMONTAJE
 * ==========
 * Ni la pantalla de selección ni `AsistenteImportacion` tocan `window` ni
 * `document` fuera de `contenedor`, y ninguno de los dos usa temporizadores ni
 * WebGL: es DOM puro sobre el `<div>` que el conmutador entrega y descarta
 * entero al cambiar de vista (`app/vistas.ts`, "QUÉ SE PIERDE AL CONMUTAR").
 * `desmontar()` solo tiene que evitar que una `catalogoUnidades()` en vuelo
 * toque un `contenedor` ya abandonado -- mismo patrón que la bandera
 * `desmontada` de `vista-series.ts`.
 */

import {
  AsistenteImportacion,
  type ResultadoAsistenteImportacion,
} from "../importacion/asistente-importacion.ts";
import { PuertoImportacionApi } from "../importacion/puerto.ts";
import type { FuenteDeDatos } from "../datos/fuente.ts";
import type { DefinicionVista, VistaMontada } from "./vistas.ts";

export const ID_VISTA_IMPORTACION = "importacion";

type DocumentoImportacion = Pick<Document, "createElement" | "createTextNode">;

export function crearVistaImportacion(
  fuente: FuenteDeDatos,
  documento: DocumentoImportacion,
): DefinicionVista {
  return {
    id: ID_VISTA_IMPORTACION,
    etiqueta: "Importar",

    montar(contenedor: HTMLElement): VistaMontada {
      let desmontada = false;
      let asistente: AsistenteImportacion | null = null;

      function el(etiqueta: string, clase?: string): HTMLElement {
        const e = documento.createElement(etiqueta) as HTMLElement;
        if (clase !== undefined) e.className = clase;
        return e;
      }

      function texto(contenido: string): Text {
        return documento.createTextNode(contenido);
      }

      function mostrarSelector(): void {
        if (desmontada) return;
        asistente = null;
        contenedor.replaceChildren();

        const raiz = el("div", "vista-importacion__selector");

        const titulo = el("h2");
        titulo.append(texto("Importar un CSV genérico"));
        raiz.append(titulo);

        // Ver la cabecera del módulo, "POR QUÉ SE MONTA CON PuertoImportacionApi":
        // este aviso es la primera de las dos veces que se dice la verdad.
        const aviso = el("p", "vista-importacion__aviso");
        aviso.append(
          texto(
            "dlv-api todavía no expone el sondeo de CSV genérico (docs/10 §10.6; " +
              "importacion/puerto.ts#PuertoImportacionApi). El asistente se abre " +
              "igual, pero se detiene en el primer paso mostrando qué endpoint " +
              "falta. Nada se importa todavía de verdad.",
          ),
        );
        raiz.append(aviso);

        const campo = el("div", "vista-importacion__campo");
        const etiqueta = el("label");
        etiqueta.append(texto("Ruta del fichero"));
        campo.append(etiqueta);

        const input = documento.createElement("input") as HTMLInputElement;
        input.type = "text";
        input.placeholder = "p. ej. C:\\logs\\sesion-2026-08-20.csv";
        campo.append(input);
        raiz.append(campo);

        const boton = documento.createElement("button") as HTMLButtonElement;
        boton.type = "button";
        boton.textContent = "Sondear";
        boton.addEventListener("click", () => {
          const referencia = input.value.trim();
          if (referencia === "") return;
          iniciarAsistente(referencia);
        });
        raiz.append(boton);

        contenedor.append(raiz);
      }

      function iniciarAsistente(referencia: string): void {
        contenedor.replaceChildren();
        const cargando = el("p", "vista-importacion__cargando");
        cargando.append(texto(`preparando el asistente de importación para «${referencia}»…`));
        contenedor.append(cargando);

        fuente
          .catalogoUnidades()
          .then((catalogo) => {
            if (desmontada) return;
            contenedor.replaceChildren();
            asistente = new AsistenteImportacion({
              contenedor,
              referenciaFichero: referencia,
              puerto: new PuertoImportacionApi(),
              catalogoUnidades: catalogo,
              documento,
              onCancelar: () => {
                asistente?.destruir();
                mostrarSelector();
              },
              onCompletar: (resultado) => {
                asistente?.destruir();
                mostrarResultado(resultado);
              },
            });
          })
          .catch((error: unknown) => {
            if (desmontada) return;
            contenedor.replaceChildren();
            const p = el("p", "vista-importacion__error");
            p.append(
              texto(
                `No se pudo preparar el asistente para «${referencia}»: ` +
                  (error instanceof Error ? error.message : String(error)),
              ),
            );
            contenedor.append(p);
            const reintentar = documento.createElement("button") as HTMLButtonElement;
            reintentar.type = "button";
            reintentar.textContent = "Volver";
            reintentar.addEventListener("click", () => mostrarSelector());
            contenedor.append(reintentar);
          });
      }

      function mostrarResultado(resultado: ResultadoAsistenteImportacion): void {
        if (desmontada) return;
        asistente = null;
        contenedor.replaceChildren();

        const raiz = el("div", "vista-importacion__resultado");
        const titulo = el("h3");
        titulo.append(texto("Asignación completa — todavía no importada"));
        raiz.append(titulo);

        // Ver la cabecera del módulo, "QUÉ PASA CON EL RESULTADO": no hay
        // endpoint que la aplique ni perfil .dlvimport que la guarde (FG-12).
        const nota = el("p", "vista-importacion__aviso");
        nota.append(
          texto(
            `${resultado.canales.length} canal(es) revisados. Esta asignación queda ` +
              "solo en memoria de esta vista: no hay todavía ningún endpoint en " +
              "dlv-api que la aplique a un log real, ni un perfil «.dlvimport» " +
              "(FG-12) que la guarde en disco. Cuando ese cableado exista, esta es " +
              "exactamente la forma que necesita (`ResultadoAsistenteImportacion`).",
          ),
        );
        raiz.append(nota);

        const boton = documento.createElement("button") as HTMLButtonElement;
        boton.type = "button";
        boton.textContent = "Importar otro fichero";
        boton.addEventListener("click", () => mostrarSelector());
        raiz.append(boton);

        contenedor.append(raiz);
      }

      mostrarSelector();

      return {
        desmontar(): void {
          desmontada = true;
          asistente?.destruir();
          asistente = null;
        },
      };
    },
  };
}
