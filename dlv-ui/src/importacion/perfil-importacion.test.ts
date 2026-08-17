import { describe, expect, it } from "vitest";

import type { CanalPropuesto, Campo, PropuestaFormato, PropuestaTiempo } from "./tipos.ts";
import {
  construirHuella,
  crearPerfil,
  ErrorDePerfilImportacion,
  hashColumnas,
  normalizar,
  reaplicarPerfil,
  sha256Hex,
} from "./perfil-importacion.ts";

/**
 * Pruebas de la reaplicación de `.dlvimport` en el navegador (FG-12).
 *
 * Espejo directo de `dlv-core/tests/test_perfil_importacion.py`: mismos
 * casos, mismo orden de consecuencia (ver la cabecera de ese fichero para el
 * razonamiento completo). No se repite aquí, porque sería la misma prosa dos
 * veces; lo que sí es específico de este lado es `sha256Hex`, que no existe
 * en Python (`hashlib` no necesita reimplementarse).
 *
 * NOTA DE EJECUCIÓN (ver el informe de la tarea): esta suite sigue la
 * convención `describe`/`it`/`expect` de `vitest` del resto de `dlv-ui`, pero
 * no se ha podido ejecutar con `npm test` en este entorno (`npm` da 403 al
 * intentar instalar `node_modules`, sin el cual `vitest` no está disponible).
 * La lógica que prueba SÍ se ha verificado, ejecutándola de verdad con
 * `node --experimental-strip-types` contra el módulo real (ver el informe):
 * los mismos casos que aquí, más una comprobación cruzada de `sha256Hex`
 * contra `hashlib.sha256` de Python byte a byte.
 */

function campo<T>(valor: T, origen: "deducido" | "confirmado"): Campo<T> {
  return { valor, origen };
}

function formato(delimitador: string = ";", codificacion: string = "utf-8"): PropuestaFormato {
  return {
    codificacion: campo(codificacion, "confirmado"),
    delimitador: campo(delimitador, "confirmado"),
    comilla: campo(null, "deducido"),
    decimal: campo(",", "deducido"),
    filaCabecera: campo(0, "deducido"),
    filaUnidades: campo(null, "deducido"),
    filaDatos: campo(1, "deducido"),
  };
}

function tiempo(columna: number | null = 0, confirmada = true): PropuestaTiempo {
  return {
    clase: campo("relativo", "deducido"),
    columna: campo(columna, confirmada ? "confirmado" : "deducido"),
    columnaFecha: campo(null, "deducido"),
    frecuenciaHz: campo(null, "deducido"),
    factorASegundos: 1,
  };
}

function canalDeducido(nombre: string, columna: number, dimensionId = "unknown"): CanalPropuesto {
  return {
    columna,
    nombreOriginal: nombre,
    tipoInferido: "decimal",
    dimensionId: campo(dimensionId, "deducido"),
    unidadOrigen: campo(null, "deducido"),
    rol: null,
    avisos: [],
  };
}

function canalRpm(dimensionConfirmada = true): CanalPropuesto {
  return {
    columna: 1,
    nombreOriginal: "RPM",
    tipoInferido: "entero",
    dimensionId: campo("angular_speed", dimensionConfirmada ? "confirmado" : "deducido"),
    unidadOrigen: campo("rpm", dimensionConfirmada ? "confirmado" : "deducido"),
    rol: {
      rol: "engine_speed",
      confianza: "EXACTA",
      sinonimo: "RPM",
      indice: null,
      parecido: 1.0,
      confirmado: true,
    },
    avisos: [],
  };
}

function perfilDeEjemplo() {
  return crearPerfil("Mi coche - MoTeC", ["Time", "RPM"], formato(), tiempo(), [canalRpm()]);
}

describe("sha256Hex: vectores oficiales FIPS 180-4", () => {
  it('hash de la cadena vacía es el vector estándar', () => {
    expect(sha256Hex("")).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".slice(0, 64),
    );
  });

  it('hash de "abc" es el vector estándar', () => {
    expect(sha256Hex("abc")).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad".slice(0, 64),
    );
  });

  it("hash de una cadena de más de 64 bytes (dos bloques) coincide con hashlib.sha256 de Python", () => {
    // `hashlib.sha256(("The quick brown fox jumps over the lazy dog. " * 5)
    // .encode("utf-8")).hexdigest()`, calculado aparte y pegado aquí como
    // valor de referencia — la comprobación cruzada real está en el informe.
    const larga = "The quick brown fox jumps over the lazy dog. ".repeat(5);
    expect(sha256Hex(larga)).toBe(
      "8a9eeb29b20c994c4ba92ab776d1b7aa62245dae9ca6519c41ee429fba7ed106",
    );
  });
});

describe("normalizar: espejo de dlv_core.roles.normalizar", () => {
  it("colapsa mayúsculas, acentos y separadores", () => {
    expect(normalizar("Régimen Motor")).toBe(normalizar("regimen_motor"));
    expect(normalizar("  RPM")).toBe(normalizar("rpm"));
  });
});

describe("HuellaCabecera: qué compone la huella", () => {
  it("es sensible al orden de columnas (total vs. parcial)", () => {
    const a = construirHuella(["RPM", "Temp"], ";", "utf-8");
    const b = construirHuella(["Temp", "RPM"], ";", "utf-8");
    expect(hashColumnas(a)).not.toBe(hashColumnas(b));
  });

  it("mismo coche, semana siguiente: misma huella", () => {
    const columnas = ["Time", "RPM", "Coolant Temp", "Oil Pressure"];
    expect(hashColumnas(construirHuella(columnas, ";", "utf-8"))).toBe(
      hashColumnas(construirHuella(columnas, ";", "utf-8")),
    );
  });
});

describe("reaplicarPerfil: coincidencia total", () => {
  it("se reaplica a un log del mismo formato", () => {
    const perfil = perfilDeEjemplo();
    const resultado = reaplicarPerfil(
      perfil,
      ["Time", "RPM"],
      formato(),
      tiempo(0, false),
      [canalDeducido("RPM", 0)],
    );
    expect(resultado.tipo).toBe("total");
    expect(resultado.columnasNuevasSinDecidir).toEqual([]);
    expect(resultado.canales[0]?.dimensionId).toEqual({ valor: "angular_speed", origen: "confirmado" });
    expect(resultado.tiempo.columna).toEqual({ valor: 0, origen: "confirmado" });
  });
});

describe("reaplicarPerfil: no corresponde a este fichero", () => {
  it("no se reaplica con otro delimitador, y dice por qué", () => {
    const perfil = perfilDeEjemplo();
    const canales = [canalDeducido("RPM", 0)];
    const resultado = reaplicarPerfil(perfil, ["RPM"], formato(","), tiempo(0, false), canales);
    expect(resultado.tipo).toBe("ninguna");
    expect(resultado.motivo).toContain("delimitador");
    expect(resultado.canales).toEqual(canales); // nada se toca
  });

  it("no se reaplica sin ninguna columna coincidente", () => {
    const perfil = perfilDeEjemplo();
    const canales = [canalDeducido("Boost Pressure", 0)];
    const resultado = reaplicarPerfil(perfil, ["Boost Pressure"], formato(), tiempo(0, false), canales);
    expect(resultado.tipo).toBe("ninguna");
    expect(resultado.motivo).toContain("ninguna columna");
  });
});

describe("reaplicarPerfil: reaplicación parcial", () => {
  it("marca los canales nuevos como sin decidir", () => {
    const perfil = perfilDeEjemplo();
    const canales = [canalDeducido("RPM", 0), canalDeducido("Boost", 1)];
    const resultado = reaplicarPerfil(perfil, ["RPM", "Boost"], formato(), tiempo(0, false), canales);
    expect(resultado.tipo).toBe("parcial");
    expect(resultado.columnasNuevasSinDecidir).toEqual(["Boost"]);
    const boost = resultado.canales.find((c) => c.nombreOriginal === "Boost");
    expect(boost?.dimensionId.origen).toBe("deducido");
  });

  it("reaplica la columna de tiempo por nombre pese a reordenarse", () => {
    const perfilConTiempo = crearPerfil("coche", ["Time", "RPM"], formato(), tiempo(0, true), [
      canalRpm(),
    ]);
    const resultado = reaplicarPerfil(
      perfilConTiempo,
      ["RPM", "Extra", "Time"], // "Time" ahora en la posición 2
      formato(),
      tiempo(null, false),
      [canalDeducido("RPM", 0), canalDeducido("Extra", 1)],
    );
    expect(resultado.tiempo.columna).toEqual({ valor: 2, origen: "confirmado" });
  });
});

describe("reaplicarPerfil: confirmado sobrevive, deducido se vuelve a deducir", () => {
  it("RPM conserva lo confirmado; Coolant Temp (nunca confirmado) se rededuce", () => {
    const canalTempGuardado: CanalPropuesto = {
      columna: 2,
      nombreOriginal: "Coolant Temp",
      tipoInferido: "decimal",
      dimensionId: campo("temperature", "deducido"),
      unidadOrigen: campo("degC", "deducido"),
      rol: {
        rol: "coolant_temp",
        confianza: "DIFUSA",
        sinonimo: "Coolant Temperature",
        indice: null,
        parecido: 0.86,
        confirmado: false, // nunca confirmado por el usuario
      },
      avisos: [],
    };
    const perfil = crearPerfil("coche", ["RPM", "Coolant Temp"], formato(), tiempo(0, false), [
      canalRpm(true),
      canalTempGuardado,
    ]);

    const canalTempNuevo: CanalPropuesto = {
      columna: 1,
      nombreOriginal: "Coolant Temp",
      tipoInferido: "decimal",
      dimensionId: campo("temperature", "deducido"),
      unidadOrigen: campo("degF", "deducido"), // el sondeo nuevo dedujo OTRA unidad
      rol: {
        rol: "oil_temp", // y hasta OTRO rol
        confianza: "DIFUSA",
        sinonimo: "Oil Temperature",
        indice: null,
        parecido: 0.7,
        confirmado: false,
      },
      avisos: [],
    };

    const resultado = reaplicarPerfil(
      perfil,
      ["RPM", "Coolant Temp"],
      formato(),
      tiempo(0, false),
      [canalDeducido("RPM", 0, "unknown"), canalTempNuevo],
    );

    const rpm = resultado.canales.find((c) => c.nombreOriginal === "RPM");
    expect(rpm?.dimensionId).toEqual({ valor: "angular_speed", origen: "confirmado" });

    const temp = resultado.canales.find((c) => c.nombreOriginal === "Coolant Temp");
    expect(temp?.dimensionId.origen).toBe("deducido"); // no se marcó como confirmado
    expect(temp?.unidadOrigen.valor).toBe("degF"); // se rededujo, no "degC" del perfil
    expect(temp?.rol?.rol).toBe("oil_temp"); // el rol también se rededujo
  });
});

describe("crearPerfil: entradas inválidas", () => {
  it("rechaza un nombre vacío", () => {
    expect(() => crearPerfil("   ", [], formato(), tiempo(0, false), [])).toThrow(
      ErrorDePerfilImportacion,
    );
  });

  it("rechaza guardar sin delimitador confirmado", () => {
    const sinDelimitador: PropuestaFormato = { ...formato(), delimitador: campo(null, "deducido") };
    expect(() => crearPerfil("coche", [], sinDelimitador, tiempo(0, false), [])).toThrow(
      ErrorDePerfilImportacion,
    );
  });
});
