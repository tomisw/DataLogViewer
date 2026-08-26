/**
 * Pruebas de `EditorPerfil` contra el doble de DOM (`dom-falso.ts`), igual que
 * `unidades/selector-unidad.test.ts` prueba `SelectorUnidad`. Cada bloque
 * corresponde a una de las cuatro decisiones del informe de la tarea.
 */

import { describe, expect, it, vi } from "vitest";

import type { Conversion } from "../unidades/conversion.ts";
import type { UnidadInfo } from "../unidades/tipos.ts";
import { t } from "../locale/catalogo.ts";
import { buscarTodos, crearFabricaDomFalsa, hijosDe, type NodoFalso } from "./dom-falso.ts";
import type { InputDom, NodoDom } from "./dom.ts";
import { EditorPerfil } from "./editor-perfil.ts";
import { construirElementoDePanel, construirLimiteDeAlerta, construirPanel, construirPerfil, perfilATextoJson } from "./perfil.ts";

const K_A_CELSIUS: Conversion = { tipo: "afin", a: 1, b: -273.15 };
const RECIPROCA: Conversion = { tipo: "reciproca", a: 1 };

function unidadInfo(conversion: Conversion, decimales = 2): UnidadInfo {
  return { id: "u", etiqueta: "u", decimales, conversion };
}

function perfilConTope() {
  return construirPerfil({
    nombre: "Motor",
    descripcion: "panel básico",
    paneles: [
      construirPanel({ titulo: "Carga", elementos: [construirElementoDePanel({ rol: "coolant_temperature", requerido: true })] }),
    ],
    limites: [
      construirLimiteDeAlerta({
        rol: "coolant_temperature",
        topes: [
          { nivel: "aviso", direccion: "arriba", valor: 373.15 },
          { nivel: "critico", direccion: "arriba", valor: 383.15 },
        ],
      }),
    ],
  });
}

function perfilConBanda(conversionReciproca: boolean) {
  return construirPerfil({
    nombre: "Mezcla",
    paneles: [construirPanel({ titulo: "Mezcla", elementos: [construirElementoDePanel({ rol: "mixture_ratio", requerido: true })] })],
    limites: [
      construirLimiteDeAlerta({
        rol: "mixture_ratio",
        banda: { nivel: "aviso", minimo: conversionReciproca ? 0.8 : 353.15, maximo: conversionReciproca ? 0.9 : 363.15 },
      }),
    ],
  });
}

function textosVisibles(raiz: NodoDom): string[] {
  return buscarTodos(raiz, "span").map((s) => s.textContent);
}

/** El control (input/textarea) que acompaña a la etiqueta de una `fila` (ver `editor-perfil.ts#fila`). */
function controlPorEtiqueta(raiz: NodoDom, etiquetaTexto: string): NodoFalso {
  for (const div of buscarTodos(raiz, "div")) {
    const hijos = hijosDe(div) as NodoFalso[];
    const etiqueta = hijos.find((h) => h.etiquetaTag === "span" && h.textContent === etiquetaTexto);
    if (etiqueta !== undefined) {
      const control = hijos.find((h) => h !== etiqueta);
      if (control !== undefined) return control;
    }
  }
  throw new Error(`no se encontró un control con etiqueta '${etiquetaTexto}'`);
}

describe("EditorPerfil: cabecera y edición de metadatos (usuario)", () => {
  it("pinta nombre y descripción activos para un perfil propio", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "usuario",
      nombresExistentes: [],
    });
    const inputNombre = controlPorEtiqueta(editor.elemento, t("perfiles.nombre")) as unknown as InputDom;
    expect(inputNombre.value).toBe("Motor");
    expect(inputNombre.disabled).toBe(false);
  });

  it("editar el nombre actualiza el perfil y dispara onCambiar", () => {
    const doble = crearFabricaDomFalsa();
    const onCambiar = vi.fn();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "usuario",
      nombresExistentes: [],
      onCambiar,
    });
    const inputNombre = controlPorEtiqueta(editor.elemento, t("perfiles.nombre")) as unknown as InputDom;
    inputNombre.value = "Motor V2";
    doble.disparar(inputNombre, "change");
    expect(editor.perfil.nombre).toBe("Motor V2");
    expect(onCambiar).toHaveBeenCalledWith(expect.objectContaining({ nombre: "Motor V2" }));
  });

  it("un nombre vacío no se acepta: el perfil no cambia y se enseña el error real", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "usuario",
      nombresExistentes: [],
    });
    const inputNombre = controlPorEtiqueta(editor.elemento, t("perfiles.nombre")) as unknown as InputDom;
    inputNombre.value = "   ";
    doble.disparar(inputNombre, "change");
    expect(editor.perfil.nombre).toBe("Motor");
    expect(textosVisibles(editor.elemento).some((txt) => txt.includes("nombre"))).toBe(true);
  });
});

describe("EditorPerfil: decisión 3 -- un perfil de fábrica no se edita en el sitio", () => {
  it("los campos de metadatos están desactivados", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "fabrica",
      nombresExistentes: [],
    });
    const inputNombre = controlPorEtiqueta(editor.elemento, t("perfiles.nombre")) as unknown as InputDom;
    expect(inputNombre.disabled).toBe(true);
    expect(textosVisibles(editor.elemento)).toContain(t("perfiles.avisoFabrica"));
    expect(textosVisibles(editor.elemento)).toContain(t("perfiles.origenFabrica"));
  });

  it("los umbrales tampoco se editan", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "fabrica",
      nombresExistentes: [],
      unidadPorRol: new Map([["coolant_temperature", unidadInfo(K_A_CELSIUS)]]),
    });
    const inputAviso = controlPorEtiqueta(editor.elemento, t("perfiles.limiteAviso")) as unknown as InputDom;
    expect(inputAviso.disabled).toBe(true);
  });
});

describe("EditorPerfil: decisión 1 -- duplicar es la única vía de crear/editar un perfil de fábrica", () => {
  it("duplicar convierte el perfil activo en uno de usuario con nombre único", () => {
    const doble = crearFabricaDomFalsa();
    const onDuplicar = vi.fn();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "fabrica",
      nombresExistentes: ["Motor"],
      onDuplicar,
    });
    const botonDuplicar = buscarTodos(editor.elemento, "button")[0]!;
    doble.disparar(botonDuplicar, "click");

    expect(editor.origen).toBe("usuario");
    expect(editor.perfil.nombre).toBe("Motor (copia)");
    expect(onDuplicar).toHaveBeenCalledWith(expect.objectContaining({ nombre: "Motor (copia)" }));
  });

  it("después de duplicar, los campos pasan a estar activos", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "fabrica",
      nombresExistentes: [],
    });
    doble.disparar(buscarTodos(editor.elemento, "button")[0]!, "click");
    const inputNombre = controlPorEtiqueta(editor.elemento, t("perfiles.nombre")) as unknown as InputDom;
    expect(inputNombre.disabled).toBe(false);
  });

  it("duplicar dos veces seguidas no colisiona de nombre", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "usuario",
      nombresExistentes: ["Motor"],
    });
    const boton = () => buscarTodos(editor.elemento, "button")[0]!;
    doble.disparar(boton(), "click");
    expect(editor.perfil.nombre).toBe("Motor (copia)");
    doble.disparar(boton(), "click");
    expect(editor.perfil.nombre).toBe("Motor (copia) (copia)");
  });
});

describe("EditorPerfil: decisión 2 -- importar enseña el error real", () => {
  it("un .dlvprofile válido reemplaza el perfil activo y pasa a ser de usuario", () => {
    const doble = crearFabricaDomFalsa();
    const onCambiar = vi.fn();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "fabrica",
      nombresExistentes: [],
      onCambiar,
    });
    const otro = construirPerfil({
      nombre: "Importado",
      paneles: [construirPanel({ titulo: "P", elementos: [construirElementoDePanel({ rol: "engine_rpm", requerido: false })] })],
    });
    editor.importarTexto(perfilATextoJson(otro));
    expect(editor.perfil.nombre).toBe("Importado");
    expect(editor.origen).toBe("usuario");
    expect(onCambiar).toHaveBeenCalled();
  });

  it("un JSON corrupto muestra el mensaje real de perfil.ts, no uno genérico", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "usuario",
      nombresExistentes: [],
    });
    editor.importarTexto("{ esto no es json");
    const textos = textosVisibles(editor.elemento);
    expect(textos.some((txt) => txt.includes("JSON inválido"))).toBe(true);
    // El perfil activo no cambia si la importación falla.
    expect(editor.perfil.nombre).toBe("Motor");
  });

  it("una versión de esquema desconocida también muestra su mensaje específico", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "usuario",
      nombresExistentes: [],
    });
    editor.importarTexto(JSON.stringify({ version_esquema: 999, nombre: "x", paneles: [] }));
    const textos = textosVisibles(editor.elemento);
    expect(textos.some((txt) => txt.includes("versión de esquema"))).toBe(true);
  });
});

describe("EditorPerfil: exportar", () => {
  it("produce exactamente el mismo texto que perfilATextoJson", () => {
    const doble = crearFabricaDomFalsa();
    const onExportar = vi.fn();
    const perfil = perfilConTope();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfil,
      origenInicial: "usuario",
      nombresExistentes: [],
      onExportar,
    });
    const botones = buscarTodos(editor.elemento, "button");
    const botonExportar = botones.find((b) => b.textContent === t("perfiles.exportar"))!;
    doble.disparar(botonExportar, "click");

    const esperado = perfilATextoJson(perfil);
    expect(onExportar).toHaveBeenCalledWith(esperado);
    const areas = buscarTodos(editor.elemento, "textarea");
    expect(areas.some((a) => a.value === esperado)).toBe(true);
  });
});

describe("EditorPerfil: decisión 4 -- umbrales en unidad activa, guardados en canónica", () => {
  it("el tope de aviso se enseña convertido (373,15 K = 100 °C)", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "usuario",
      nombresExistentes: [],
      unidadPorRol: new Map([["coolant_temperature", unidadInfo(K_A_CELSIUS)]]),
    });
    const inputAviso = controlPorEtiqueta(editor.elemento, t("perfiles.limiteAviso")) as unknown as InputDom;
    expect(inputAviso.value).toBe("100.00");
  });

  it("editar el tope en la unidad activa se guarda en canónica", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "usuario",
      nombresExistentes: [],
      unidadPorRol: new Map([["coolant_temperature", unidadInfo(K_A_CELSIUS)]]),
    });
    const inputAviso = controlPorEtiqueta(editor.elemento, t("perfiles.limiteAviso")) as unknown as InputDom;
    inputAviso.value = "90";
    doble.disparar(inputAviso, "change");
    const tope = editor.perfil.limites[0]!.topes.find((tp) => tp.nivel === "aviso")!;
    expect(tope.valor).toBeCloseTo(363.15, 6);
  });

  it("un valor de aviso que deje el crítico por detrás muestra el error de validar_pareja y no cambia el perfil", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConTope(),
      origenInicial: "usuario",
      nombresExistentes: [],
      unidadPorRol: new Map([["coolant_temperature", unidadInfo(K_A_CELSIUS)]]),
    });
    const inputAviso = controlPorEtiqueta(editor.elemento, t("perfiles.limiteAviso")) as unknown as InputDom;
    inputAviso.value = "120"; // 393,15 K > crítico (383,15 K)
    doble.disparar(inputAviso, "change");
    expect(textosVisibles(editor.elemento).some((txt) => txt.includes("nunca avisa"))).toBe(true);
    const tope = editor.perfil.limites[0]!.topes.find((tp) => tp.nivel === "aviso")!;
    expect(tope.valor).toBeCloseTo(373.15, 6); // sin cambios
  });

  it("una banda se edita como centro/semiancho cuando la conversión lo admite, sin que el desplazamiento de origen se cuele en el ancho", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConBanda(false),
      origenInicial: "usuario",
      nombresExistentes: [],
      unidadPorRol: new Map([["mixture_ratio", unidadInfo(K_A_CELSIUS)]]),
    });
    const inputCentro = controlPorEtiqueta(editor.elemento, t("perfiles.limiteBandaCentro")) as unknown as InputDom;
    const inputAncho = controlPorEtiqueta(editor.elemento, t("perfiles.limiteBandaSemiancho")) as unknown as InputDom;
    // 353,15..363,15 K -> centro 358,15 K = 85 °C, semiancho 5 K = 5 °C (no -268,15).
    expect(inputCentro.value).toBe("85.00");
    expect(inputAncho.value).toBe("5.00");
  });

  it("una banda con conversión recíproca cae a edición mínimo/máximo", () => {
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: perfilConBanda(true),
      origenInicial: "usuario",
      nombresExistentes: [],
      unidadPorRol: new Map([["mixture_ratio", unidadInfo(RECIPROCA)]]),
    });
    const inputMinimo = controlPorEtiqueta(editor.elemento, t("perfiles.limiteBandaMinimo")) as unknown as InputDom;
    const inputMaximo = controlPorEtiqueta(editor.elemento, t("perfiles.limiteBandaMaximo")) as unknown as InputDom;
    // En phi, no en lambda: docs/06 SS6.11 dice que los umbrales se EDITAN en
    // la unidad activa (y se guardan en canonica). 1/0,90 = 1,11 y 1/0,80 =
    // 1,25 -- y ojo al orden: la reciproca lo invierte, asi que el minimo
    // mostrado sale del MAXIMO canonico. Esta prueba esperaba 0,80/0,90, es
    // decir los valores sin convertir; se corrige, y de paso fija la
    // inversion, que era un fallo real del editor.
    expect(inputMinimo.value).toBe("1.11");
    expect(inputMaximo.value).toBe("1.25");
  });

  it("un tope en curva se enseña como nota, no como campo editable", () => {
    const conCurva = construirPerfil({
      nombre: "Motor",
      paneles: [construirPanel({ titulo: "P", elementos: [construirElementoDePanel({ rol: "oil_pressure", requerido: false })] })],
      limites: [
        construirLimiteDeAlerta({
          rol: "oil_pressure",
          topes: [{ nivel: "aviso", direccion: "abajo", valor: { forma: "lineal", rolReferencia: "engine_rpm", base: 200, pendiente: 50, divisorReferencia: 1000 } }],
        }),
      ],
    });
    const doble = crearFabricaDomFalsa();
    const editor = new EditorPerfil({
      dom: doble.fabrica,
      perfilInicial: conCurva,
      origenInicial: "usuario",
      nombresExistentes: [],
    });
    expect(textosVisibles(editor.elemento)).toContain(t("perfiles.limiteCurvaNoEditable", { rol: "engine_rpm" }));
  });
});
