/**
 * `crearVistaPerfiles`: adapta `EditorPerfil` (`perfiles/editor-perfil.ts`) a
 * `DefinicionVista` (`app/vistas.ts`) — el cableado que le faltaba al módulo
 * `perfiles/` para dejar de ser uno de los 13 «construidos, probados y sin
 * ningún sitio real donde montarse» de docs/02 §2.10.
 *
 * DE DÓNDE SALE EL PERFIL QUE SE VE AL ABRIR LA PESTAÑA
 * ========================================================
 * `EditorPerfil` exige un `perfilInicial: Perfil` ya construido -- no hay
 * "perfil en blanco" (ver la cabecera de `perfiles/duplicado.ts`: un panel
 * necesita al menos un elemento con un rol, y elegir ESE primer rol sin el
 * catálogo de `data/roles.toml` no es tarea de F3-05). Y no hay de dónde
 * traer uno de verdad: comprobado sobre `dlv_api/main.py`, no existe ninguna
 * ruta `/comandos/perfil*` que liste el catálogo de fábrica ni los perfiles
 * del usuario, y `datos/fuente.ts#FuenteDeDatos` no tiene ningún método para
 * pedirlo (su único miembro relacionado, `sugerirPerfil`, sugiere UN perfil
 * ya cargado para un log concreto -- no lista el catálogo). Mismo criterio
 * que seguía `app/vista-incidencias.ts` con `DATOS_VACIOS` para
 * `/comandos/incidencias`, pero aquí no vale un catálogo vacío: `EditorPerfil`
 * no tiene un estado "sin perfil montado".
 *
 * Por eso este módulo monta con `PERFIL_DE_MUESTRA`, un perfil sintético
 * -mismo espíritu que `main.ts#elegirFuente` cayendo a `FuenteSintetica`
 * cuando no hay `dlv-api`- construido con `perfil.ts#construirPerfil` (así
 * que pasa las mismas validaciones que un `.dlvprofile` real) y marcado
 * `origenInicial: "fabrica"` a propósito: así la pestaña, en el primer
 * pintado, ENSEÑA de verdad el candado de `permisos.ts` (campos
 * deshabilitados, "Duplicar para editar") en vez de arrancar ya editable y
 * dejar esa ruta sin ejercitar hasta que exista un perfil de fábrica real.
 * Su `descripcion` lo dice también en la propia interfaz, no solo en este
 * comentario: no es una promesa de que haya más perfiles detrás.
 *
 * Traer el catálogo real -de fábrica y de usuario- es tarea aparte, a abrir
 * cuando `dlv-api` tenga esa ruta; el día que exista, el sitio para cablearla
 * es el `montar()` de este fichero (sustituir `PERFIL_DE_MUESTRA` por lo que
 * devuelva esa ruta), sin tocar `perfiles/editor-perfil.ts`.
 *
 * NADA DE ESTO SE GUARDA, Y LA PESTAÑA LO DICE SIN QUE HAYA QUE PREGUNTAR
 * ==========================================================================
 * Sin endpoint de persistencia (mismo `dlv_api/main.py`, misma comprobación:
 * no hay ninguna ruta para escribir un `.dlvprofile`), ni `FuenteDeDatos` con
 * un método para guardarlo, cualquier edición -- incluida la de duplicar --
 * vive solo en memoria de esta pestaña y desaparece al cambiar de vista o
 * cerrar la aplicación. `montar()` pone ese aviso FIJO, siempre visible,
 * antes del editor -- no un tooltip ni una nota que haya que ir a buscar--
 * porque una vista que parece guardar y no guarda es, según el propio
 * encargo, la peor salida posible. Lo único que sí es real hoy es
 * "Exportar" (ya lo hace `EditorPerfil`, sin tocarlo): copia el `.dlvprofile`
 * resultante como texto para que el usuario lo guarde él mismo como fichero
 * suelto -- el aviso lo señala como la vía de escape que existe de verdad.
 *
 * POR QUÉ NO HAY OYENTES QUE LIBERAR EN `desmontar()`
 * ======================================================
 * Igual que `vista-incidencias.ts`: DOM puro, sin WebGL, sin temporizador,
 * sin ningún `addEventListener` sobre `window`/`document` (todos los de
 * `EditorPerfil` -- clic de botón, `change` de un campo -- cuelgan de nodos
 * que viven DENTRO de `contenedor`, y ese `<div>` se lo lleva el conmutador
 * entero al conmutar). `vista-perfiles.test.ts` lo comprueba montando y
 * desmontando varias veces seguidas sobre el mismo `documento` y
 * comprobando que no revienta -- ver esa cabecera para qué SÍ y qué NO se
 * pudo probar en `environment: "node"`, sin `window` de verdad.
 */

import { fabricaDesdeDocumento } from "../perfiles/dom.ts";
import { EditorPerfil } from "../perfiles/editor-perfil.ts";
import {
  construirElementoDePanel,
  construirLimiteDeAlerta,
  construirPanel,
  construirPerfil,
  type Perfil,
} from "../perfiles/perfil.ts";
import { t } from "../locale/catalogo.ts";
import type { DefinicionVista, VistaMontada } from "./vistas.ts";

export const ID_VISTA_PERFILES = "perfiles";

/**
 * Ver "DE DÓNDE SALE EL PERFIL..." en la cabecera del módulo: una semilla
 * sintética, no un perfil de fábrica real, construida con las mismas
 * funciones de validación que un `.dlvprofile` importado (`construirPerfil`,
 * `construirPanel`, `construirElementoDePanel`, `construirLimiteDeAlerta`).
 * Los roles (`coolant_temp`, `oil_pressure`) y los umbrales de aviso/crítico
 * de refrigerante (373,15 K / 383,15 K = 100 °C / 110 °C) son los mismos que
 * usa el perfil real `data/perfiles/p08_salud_motor.dlvprofile` para ese
 * mismo rol -- no un número inventado por este módulo (regla 3 de
 * `CLAUDE.md`), sino un valor plausible tomado de un perfil de fábrica de
 * verdad para que la demostración no sea absurda.
 */
const PERFIL_DE_MUESTRA: Perfil = construirPerfil({
  nombre: "Perfil de muestra",
  descripcion:
    "Semilla de demostración: dlv-api todavía no tiene un endpoint que liste el catálogo de perfiles (de fábrica ni de usuario), así que esta pestaña arranca con este único perfil en memoria en vez de fingir que hay más. Duplícalo para editarlo, o pega un .dlvprofile propio en «Cargar» más abajo.",
  paneles: [
    construirPanel({
      titulo: "Térmico",
      elementos: [
        construirElementoDePanel({ rol: "coolant_temp", requerido: true }),
        construirElementoDePanel({ rol: "oil_pressure", requerido: false }),
      ],
    }),
  ],
  limites: [
    construirLimiteDeAlerta({
      rol: "coolant_temp",
      topes: [
        { nivel: "aviso", direccion: "arriba", valor: 373.15 },
        { nivel: "critico", direccion: "arriba", valor: 383.15 },
      ],
    }),
  ],
});

export function crearVistaPerfiles(documento: Pick<Document, "createElement">): DefinicionVista {
  return {
    id: ID_VISTA_PERFILES,
    etiqueta: "Perfiles",

    montar(contenedor: HTMLElement): VistaMontada {
      const fabrica = fabricaDesdeDocumento(documento);

      const aviso = fabrica.crearDiv();
      aviso.classList.add("vista-perfiles__aviso-persistencia");
      aviso.textContent = t("perfiles.avisoSinGuardar");
      contenedor.appendChild(aviso as unknown as Node);

      const editor = new EditorPerfil({
        dom: fabrica,
        perfilInicial: PERFIL_DE_MUESTRA,
        origenInicial: "fabrica",
        nombresExistentes: [PERFIL_DE_MUESTRA.nombre],
      });
      contenedor.appendChild(editor.elemento as unknown as Node);

      return {
        desmontar(): void {
          // DOM puro: sin oyentes en `window`/`document`, sin temporizadores,
          // sin WebGL. El conmutador descarta `contenedor` entero al cambiar
          // de vista, y con él se va todo lo que `montar` puso dentro (ver la
          // cabecera del módulo).
        },
      };
    },
  };
}
