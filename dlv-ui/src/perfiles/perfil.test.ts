/**
 * Pruebas del espejo de `dlv_core.perfil` (F3-05). No repiten las pruebas de
 * `perfil.py` línea a línea (viven en `dlv-core`, en Python); comprueban que
 * ESTE espejo aplica las mismas invariantes y produce errores que dicen QUÉ y
 * DÓNDE, que es justo lo que la decisión 2 de la tarea exige mostrar al
 * importar un `.dlvprofile` inválido.
 */

import { describe, expect, it } from "vitest";

import {
  construirElementoDePanel,
  construirLimiteDeAlerta,
  construirPanel,
  construirPerfil,
  ErrorDePerfil,
  ErrorDeVersionDePerfilDesconocida,
  perfilADict,
  perfilATextoJson,
  perfilDesdeDict,
  perfilDesdeTextoJson,
  rolesReferenciadosDePerfil,
  rolesRequeridosDePerfil,
  VERSION_ESQUEMA_PERFIL,
} from "./perfil.ts";

function perfilMinimo() {
  return construirPerfil({
    nombre: "Motor",
    descripcion: "Panel básico",
    unidades: { temperature: "degC" },
    paneles: [
      construirPanel({
        titulo: "Carga",
        elementos: [
          construirElementoDePanel({ rol: "coolant_temperature", requerido: true }),
          construirElementoDePanel({ rol: "engine_rpm", requerido: false }),
        ],
      }),
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

describe("perfil: ElementoDePanel", () => {
  it("rechaza rol e id_nativo a la vez", () => {
    expect(() => construirElementoDePanel({ rol: "x", idNativo: "y", requerido: false })).toThrow(ErrorDePerfil);
  });

  it("rechaza que falten los dos", () => {
    expect(() => construirElementoDePanel({ requerido: false })).toThrow(/EXACTAMENTE UNO/);
  });

  it("un id_nativo requerido se rechaza (docs/07 §7.12)", () => {
    expect(() => construirElementoDePanel({ idNativo: "haltech.boost_pid_p", requerido: true })).toThrow(
      /no puede ser `requerido`/,
    );
  });

  it("escala_min debe ser menor que escala_max", () => {
    expect(() =>
      construirElementoDePanel({ rol: "x", requerido: false, escalaMin: 10, escalaMax: 10 }),
    ).toThrow(/escala_min/);
  });

  it("índice negativo se rechaza", () => {
    expect(() => construirElementoDePanel({ rol: "x", requerido: false, indice: -1 })).toThrow(/indice/);
  });
});

describe("perfil: Panel", () => {
  it("rechaza un panel sin elementos", () => {
    expect(() => construirPanel({ titulo: "Vacío", elementos: [] })).toThrow(/no tiene ningún elemento/);
  });

  it("rechaza un elemento repetido (mismo rol e índice)", () => {
    const e = construirElementoDePanel({ rol: "knock_level", indice: 1, requerido: false });
    expect(() => construirPanel({ titulo: "Knock", elementos: [e, e] })).toThrow(/repite el elemento/);
  });

  it("el mismo rol con índices distintos NO es un duplicado (banco 1 vs banco 2)", () => {
    const p = construirPanel({
      titulo: "Knock",
      elementos: [
        construirElementoDePanel({ rol: "knock_level", indice: 1, requerido: false }),
        construirElementoDePanel({ rol: "knock_level", indice: 2, requerido: false }),
      ],
    });
    expect(p.elementos).toHaveLength(2);
  });
});

describe("perfil: LimiteDeAlerta", () => {
  it("rechaza topes Y banda a la vez", () => {
    expect(() =>
      construirLimiteDeAlerta({
        rol: "oil_pressure",
        topes: [{ nivel: "aviso", direccion: "abajo", valor: 100 }],
        banda: { nivel: "aviso", minimo: 10, maximo: 20 },
      }),
    ).toThrow(/topes unidireccionales Y una banda/);
  });

  it("rechaza un límite sin tope ni banda", () => {
    expect(() => construirLimiteDeAlerta({ rol: "oil_pressure" })).toThrow(/no declara ningún tope ni banda/);
  });

  it("el aviso detrás del crítico (dirección ARRIBA) se rechaza -- mismo error que dlv_core.topes.validar_pareja", () => {
    expect(() =>
      construirLimiteDeAlerta({
        rol: "coolant_temperature",
        topes: [
          { nivel: "aviso", direccion: "arriba", valor: 393.15 },
          { nivel: "critico", direccion: "arriba", valor: 383.15 },
        ],
      }),
    ).toThrow(/nunca avisa/);
  });

  it("dos topes en direcciones distintas se rechazan: son dos alertas, no dos niveles", () => {
    expect(() =>
      construirLimiteDeAlerta({
        rol: "x",
        topes: [
          { nivel: "aviso", direccion: "arriba", valor: 10 },
          { nivel: "critico", direccion: "abajo", valor: 5 },
        ],
      }),
    ).toThrow(/dos alertas distintas/);
  });

  it("una curva no participa en validar_pareja (no se compara, se acepta)", () => {
    const limite = construirLimiteDeAlerta({
      rol: "oil_pressure",
      topes: [
        { nivel: "aviso", direccion: "abajo", valor: { forma: "lineal", rolReferencia: "engine_rpm", base: 250, pendiente: 50, divisorReferencia: 1000 } },
        { nivel: "critico", direccion: "abajo", valor: 150 },
      ],
    });
    expect(limite.topes).toHaveLength(2);
  });
});

describe("perfil: Perfil", () => {
  it("rechaza un perfil sin paneles", () => {
    expect(() => construirPerfil({ nombre: "vacío", paneles: [] })).toThrow(/no tiene ningún panel/);
  });

  it("rechaza dos límites para el mismo rol", () => {
    const limite = construirLimiteDeAlerta({ rol: "x", topes: [{ nivel: "aviso", direccion: "arriba", valor: 1 }] });
    expect(() =>
      construirPerfil({
        nombre: "dup",
        paneles: [construirPanel({ titulo: "P", elementos: [construirElementoDePanel({ rol: "x", requerido: false })] })],
        limites: [limite, limite],
      }),
    ).toThrow(/más de un límite de alerta/);
  });

  it("rolesRequeridosDePerfil/rolesReferenciadosDePerfil: granularidad de panel, no de perfil (decisión 2)", () => {
    const perfil = perfilMinimo();
    expect(rolesRequeridosDePerfil(perfil)).toEqual(new Set(["coolant_temperature"]));
    expect(rolesReferenciadosDePerfil(perfil)).toEqual(new Set(["coolant_temperature", "engine_rpm"]));
  });
});

describe("perfil: JSON — ida y vuelta", () => {
  it("perfilDesdeDict(perfilADict(p)) reproduce el mismo perfil", () => {
    const original = perfilMinimo();
    const reconstruido = perfilDesdeDict(perfilADict(original));
    expect(perfilADict(reconstruido)).toEqual(perfilADict(original));
  });

  it("perfilDesdeTextoJson(perfilATextoJson(p)) reproduce el mismo perfil", () => {
    const original = perfilMinimo();
    const reconstruido = perfilDesdeTextoJson(perfilATextoJson(original));
    expect(reconstruido).toEqual(original);
  });

  it("el texto exportado lleva la versión de esquema actual", () => {
    const bruto = JSON.parse(perfilATextoJson(perfilMinimo())) as Record<string, unknown>;
    expect(bruto["version_esquema"]).toBe(VERSION_ESQUEMA_PERFIL);
  });
});

describe("perfil: importar un .dlvprofile inválido -- decisión 2 (enseñar el error real)", () => {
  it("falta 'version_esquema': mensaje específico, no genérico", () => {
    expect(() => perfilDesdeDict({ nombre: "x" })).toThrow(/falta la clave 'version_esquema'/);
  });

  it("versión de esquema desconocida: se rechaza ENTERO con un error distinguible", () => {
    expect(() => perfilDesdeDict({ version_esquema: 99, nombre: "x", paneles: [] })).toThrow(
      ErrorDeVersionDePerfilDesconocida,
    );
  });

  it("JSON que ni siquiera analiza: dice 'JSON inválido', no 'no se pudo importar'", () => {
    expect(() => perfilDesdeTextoJson("{ esto no es json")).toThrow(/JSON inválido/);
  });

  it("un panel corrupto señala EN QUÉ PANEL Y QUÉ CAMPO -- no un error desnudo", () => {
    const bruto = {
      version_esquema: VERSION_ESQUEMA_PERFIL,
      nombre: "x",
      paneles: [{ titulo: "", elementos: [] }],
    };
    expect(() => perfilDesdeDict(bruto)).toThrow(/paneles\[0\]/);
  });

  it("un elemento con rol e id_nativo a la vez señala la ruta completa hasta el elemento", () => {
    const bruto = {
      version_esquema: VERSION_ESQUEMA_PERFIL,
      nombre: "x",
      paneles: [
        {
          titulo: "P",
          elementos: [{ rol: "a", id_nativo: "b", requerido: false }],
        },
      ],
    };
    expect(() => perfilDesdeDict(bruto)).toThrow(/paneles\[0\]\.elementos\[0\]/);
  });

  it("un límite con topes fuera de orden señala el rol Y por qué (mensaje de dominio, no un ValueError desnudo)", () => {
    const bruto = {
      version_esquema: VERSION_ESQUEMA_PERFIL,
      nombre: "x",
      paneles: [{ titulo: "P", elementos: [{ rol: "coolant_temperature", requerido: false }] }],
      limites: [
        {
          rol: "coolant_temperature",
          topes: [
            { nivel: "aviso", direccion: "arriba", valor: 400 },
            { nivel: "critico", direccion: "arriba", valor: 380 },
          ],
        },
      ],
    };
    expect(() => perfilDesdeDict(bruto)).toThrow(/coolant_temperature/);
    expect(() => perfilDesdeDict(bruto)).toThrow(/nunca avisa/);
  });

  it("una raíz que no es un objeto se rechaza con un mensaje sobre la raíz", () => {
    expect(() => perfilDesdeDict([1, 2, 3])).toThrow(/la raíz del JSON debe ser un objeto/);
  });
});

describe("perfil: curvas", () => {
  it("una curva lineal con divisor 0 se rechaza", () => {
    expect(() =>
      construirLimiteDeAlerta({
        rol: "oil_pressure",
        topes: [
          { nivel: "aviso", direccion: "abajo", valor: { forma: "lineal", rolReferencia: "engine_rpm", base: 1, pendiente: 1, divisorReferencia: 0 } },
        ],
      }),
    ).toThrow(/divisor_referencia/);
  });

  it("una curva por puntos con menos de 2 puntos se rechaza", () => {
    const bruto = {
      version_esquema: VERSION_ESQUEMA_PERFIL,
      nombre: "x",
      paneles: [{ titulo: "P", elementos: [{ rol: "oil_pressure", requerido: false }] }],
      limites: [
        {
          rol: "oil_pressure",
          topes: [{ nivel: "aviso", direccion: "abajo", valor: { forma: "puntos", rol_referencia: "engine_rpm", puntos: [[0, 200]] } }],
        },
      ],
    };
    expect(() => perfilDesdeDict(bruto)).toThrow(/al menos 2 puntos/);
  });

  it("una curva por puntos no estrictamente creciente se rechaza", () => {
    const bruto = {
      version_esquema: VERSION_ESQUEMA_PERFIL,
      nombre: "x",
      paneles: [{ titulo: "P", elementos: [{ rol: "oil_pressure", requerido: false }] }],
      limites: [
        {
          rol: "oil_pressure",
          topes: [
            {
              nivel: "aviso",
              direccion: "abajo",
              valor: { forma: "puntos", rol_referencia: "engine_rpm", puntos: [[0, 200], [0, 500]] },
            },
          ],
        },
      ],
    };
    expect(() => perfilDesdeDict(bruto)).toThrow(/estrictamente creciente/);
  });

  it("una curva se serializa con las claves snake_case del contrato de fichero", () => {
    const perfil = construirPerfil({
      nombre: "x",
      paneles: [construirPanel({ titulo: "P", elementos: [construirElementoDePanel({ rol: "oil_pressure", requerido: false })] })],
      limites: [
        construirLimiteDeAlerta({
          rol: "oil_pressure",
          topes: [{ nivel: "aviso", direccion: "abajo", valor: { forma: "lineal", rolReferencia: "engine_rpm", base: 200, pendiente: 50, divisorReferencia: 1000 } }],
        }),
      ],
    });
    const dict = perfilADict(perfil);
    const limites = dict["limites"] as readonly Record<string, unknown>[];
    const topes = limites[0]!["topes"] as readonly Record<string, unknown>[];
    const valor = topes[0]!["valor"] as Record<string, unknown>;
    expect(valor["rol_referencia"]).toBe("engine_rpm");
    expect(valor["divisor_referencia"]).toBe(1000);
  });
});
