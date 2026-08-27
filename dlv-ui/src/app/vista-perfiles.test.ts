/**
 * Pruebas de `crearVistaPerfiles` (docs/02 §2.10): el cableado que le
 * faltaba a `perfiles/` para dejar de ser uno de los 13 módulos construidos,
 * probados y sin sitio real donde montarse.
 *
 * QUÉ SE PRUEBA Y QUÉ NO
 * =========================
 * Lo que decide la corrección de `EditorPerfil` en sí -- validación del
 * esquema, la aritmética de `edicion-umbrales.ts`, duplicar sin colisión --
 * ya lo prueban `perfiles/*.test.ts`; repetirlo aquí sería la misma prueba
 * con más ceremonia. Lo que SÍ es de este módulo, y solo de este módulo:
 *
 * 1. Que la vista arranca con el candado de `permisos.ts` de verdad
 *    ejercitado (campos deshabilitados, "Duplicar para editar") -- no un
 *    perfil ya editable que nunca demuestra el caso de fábrica.
 * 2. Que el aviso de "esto no se guarda" está SIEMPRE en pantalla, no detrás
 *    de un clic.
 * 3. Que `desmontar()` no dejó nada colgando: como `vista-incidencias.ts`,
 *    esta vista no toca `window`/`document` fuera de crear nodos dentro de
 *    `contenedor`, así que no hay oyentes que contar (a diferencia de
 *    `app/aplicacion.test.ts`, que sí cuenta oyentes de `window` porque
 *    `Aplicacion` los pone). Lo que se prueba en su lugar es que montar y
 *    desmontar varias veces seguidas, con contenedores nuevos cada vez, ni
 *    revienta ni arrastra estado de un ciclo al siguiente (el perfil vuelve
 *    a nacer "de fábrica" cada vez, nunca ya editado por el ciclo anterior).
 */

import { describe, expect, it } from "vitest";

import { crearDocumentoFalso, type ElementoFalso } from "../dom/doble-documento.ts";
import { t } from "../locale/catalogo.ts";
import { crearVistaPerfiles, ID_VISTA_PERFILES } from "./vista-perfiles.ts";

function crearContenedor(): { documentoPick: Pick<Document, "createElement">; contenedor: ElementoFalso } {
  const documento = crearDocumentoFalso();
  const contenedor = documento.createElement("div");
  return { documentoPick: documento as unknown as Pick<Document, "createElement">, contenedor };
}

/** La fila `editor-perfil__fila` cuya etiqueta (el primer `span`) es exactamente `etiquetaTexto`. */
function filaPorEtiqueta(contenedor: ElementoFalso, etiquetaTexto: string): ElementoFalso {
  const filas = contenedor.buscarTodosPorClase("editor-perfil__fila");
  const fila = filas.find((f) => f.hijos.some((h) => h.etiqueta === "span" && h.textContent === etiquetaTexto));
  if (fila === undefined) {
    throw new Error(`no se encontró ninguna fila con etiqueta '${etiquetaTexto}'`);
  }
  return fila;
}

/** El control (no la etiqueta) de una fila de `editor-perfil.ts#fila`: exactamente dos hijos, span + control. */
function controlDeFila(fila: ElementoFalso): ElementoFalso {
  const etiqueta = fila.hijos.find((h) => h.etiqueta === "span");
  const control = fila.hijos.find((h) => h !== etiqueta);
  if (control === undefined) throw new Error("la fila no tiene control además de la etiqueta");
  return control;
}

describe("crearVistaPerfiles", () => {
  it("tiene el id ID_VISTA_PERFILES", () => {
    const { documentoPick } = crearContenedor();
    const definicion = crearVistaPerfiles(documentoPick);
    expect(definicion.id).toBe(ID_VISTA_PERFILES);
  });

  it("arranca con el perfil de muestra, de origen 'fabrica': el candado de permisos.ts se ve de verdad", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaPerfiles(documentoPick);
    definicion.montar(contenedor as unknown as HTMLElement, { irAVista: () => {} }, {});

    const badge = contenedor.buscarPorClase("editor-perfil__origen");
    expect(badge?.textContent).toBe(t("perfiles.origenFabrica"));

    const nombre = controlDeFila(filaPorEtiqueta(contenedor, t("perfiles.nombre")));
    expect(nombre.value).toBe("Perfil de muestra");
    expect(nombre.disabled).toBe(true);

    const descripcion = controlDeFila(filaPorEtiqueta(contenedor, t("perfiles.descripcion")));
    expect(descripcion.disabled).toBe(true);

    const botonDuplicar = contenedor.buscarPorClase("editor-perfil__duplicar");
    expect(botonDuplicar?.textContent).toBe(t("perfiles.duplicarParaEditar"));
  });

  it("el aviso de 'esto no se guarda' está siempre en pantalla, sin que haga falta pulsar nada", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaPerfiles(documentoPick);
    definicion.montar(contenedor as unknown as HTMLElement, { irAVista: () => {} }, {});

    expect(contenedor.textoDelArbol()).toContain(t("perfiles.avisoSinGuardar"));
  });

  it("intentar editar el nombre de un perfil de solo lectura no cambia nada (el input está deshabilitado)", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaPerfiles(documentoPick);
    definicion.montar(contenedor as unknown as HTMLElement, { irAVista: () => {} }, {});

    const nombre = controlDeFila(filaPorEtiqueta(contenedor, t("perfiles.nombre")));
    expect(nombre.disabled).toBe(true);
    // Un input real, deshabilitado, no dispara "change" en un navegador: aquí
    // se comprueba la mitad que SÍ se puede probar sin uno -- que el campo
    // sigue marcado `disabled` y con su valor original tras el montaje, nunca
    // "editable en el sitio" para un perfil de fábrica.
    expect(nombre.value).toBe("Perfil de muestra");
  });

  it("'Duplicar para editar' cambia el origen a 'usuario' y habilita los campos, en la misma pestaña", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaPerfiles(documentoPick);
    definicion.montar(contenedor as unknown as HTMLElement, { irAVista: () => {} }, {});

    const botonDuplicar = contenedor.buscarPorClase("editor-perfil__duplicar");
    expect(botonDuplicar).not.toBeNull();
    botonDuplicar!.disparar("click");

    const badge = contenedor.buscarPorClase("editor-perfil__origen");
    expect(badge?.textContent).toBe(t("perfiles.origenUsuario"));

    const nombre = controlDeFila(filaPorEtiqueta(contenedor, t("perfiles.nombre")));
    expect(nombre.disabled).toBe(false);
    expect(nombre.value).toBe("Perfil de muestra (copia)");

    // El botón ahora ofrece "Duplicar" a secas: ya es un perfil propio, editable.
    const botonTrasEditar = contenedor.buscarPorClase("editor-perfil__duplicar");
    expect(botonTrasEditar?.textContent).toBe(t("perfiles.duplicar"));
  });

  it("desmontar() no revienta (vista puramente DOM, sin WebGL ni temporizadores ni oyentes de window/document)", () => {
    const { documentoPick, contenedor } = crearContenedor();
    const definicion = crearVistaPerfiles(documentoPick);
    const montada = definicion.montar(contenedor as unknown as HTMLElement, { irAVista: () => {} }, {});
    expect(() => montada.desmontar()).not.toThrow();
  });

  it("montar/desmontar varias veces con contenedores nuevos no arrastra estado de un ciclo al siguiente", () => {
    const { documentoPick } = crearContenedor();
    const definicion = crearVistaPerfiles(documentoPick);

    for (let i = 0; i < 5; i += 1) {
      const documento = crearDocumentoFalso();
      const contenedor = documento.createElement("div");
      const montada = definicion.montar(contenedor as unknown as HTMLElement, { irAVista: () => {} }, {});

      // Si un ciclo anterior hubiera dejado el perfil ya duplicado (estado
      // compartido por error, p. ej. una constante mutada en el módulo), este
      // origen ya no sería "fabrica" a partir del segundo ciclo.
      const badge = contenedor.buscarPorClase("editor-perfil__origen");
      expect(badge?.textContent).toBe(t("perfiles.origenFabrica"));

      const botonDuplicar = contenedor.buscarPorClase("editor-perfil__duplicar");
      botonDuplicar!.disparar("click");
      expect(contenedor.buscarPorClase("editor-perfil__origen")?.textContent).toBe(t("perfiles.origenUsuario"));

      expect(() => montada.desmontar()).not.toThrow();
    }
  });
});
