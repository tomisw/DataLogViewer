/**
 * Pruebas del doble cursor y el Δ (F1-30). **Puerta G1.**
 *
 * La prueba que justifica el fichero entero es «un Δ de 10 K son 10 °C, nunca
 * −263,15 °C». Es la regresión probable del subsistema de unidades (docs/06
 * §6.6) porque la conversión de un punto y la de una diferencia se escriben
 * casi igual y solo una lleva el `+ b`; y es silenciosa, porque un Δ desplazado
 * 273 grados entre dos temperaturas cercanas sale plausible en pantalla.
 *
 * El resto de las pruebas cubren los tres casos en los que un Δ NO existe
 * —unidad recíproca, parámetro que cambia entre cursores, hueco— porque la
 * alternativa a decir «no se puede» es enseñar un número inventado, y esa es
 * exactamente la clase de fallo que E1.7 prohíbe.
 */

import { describe, expect, it } from "vitest";

import { CacheDeCubos } from "../datos/cache-cubos.ts";
import type { CubosContinuos } from "../render/tipos.ts";
import {
  Clase,
  convertirDelta,
  deltaDeTiempo,
  deltaEntre,
  leerEn,
  textoDeDelta,
  type Delta,
  type FormaConversion,
  type LecturaCursor,
} from "./doble.ts";

const CELSIUS: FormaConversion = { tipo: "afin", factor: 1 };
const LAMBDA_A_PHI: FormaConversion = { tipo: "reciproca" };
const LAMBDA_A_AFR: FormaConversion = {
  tipo: "parametrizada",
  factor: 14.7,
  parametroRol: "fuel_stoich_ratio",
};

function muestra(valor: number, parametro?: number): LecturaCursor {
  return {
    hay: true,
    esMuestra: true,
    minimo: valor,
    maximo: valor,
    ...(parametro === undefined ? {} : { parametro }),
  };
}

function cubo(minimo: number, maximo: number): LecturaCursor {
  return { hay: true, esMuestra: false, minimo, maximo };
}

function exigirDefinido(d: Delta): Extract<Delta, { definido: true }> {
  expect(d.definido).toBe(true);
  if (!d.definido) throw new Error("inalcanzable");
  return d;
}

describe("la trampa del delta (docs/06 §6.6)", () => {
  it("un Δ de 10 K son 10 °C, no −263,15 °C", () => {
    // La prueba que da nombre al módulo. 293,15 K y 303,15 K son 20 °C y 30 °C;
    // en la unidad mostrada la resta da 10 en las dos, porque el `+ b` se
    // cancela. Lo que NUNCA puede pasar es que aparezca el desplazamiento.
    const enKelvin = exigirDefinido(deltaEntre(muestra(293.15), muestra(303.15), CELSIUS));
    const enCelsius = exigirDefinido(deltaEntre(muestra(20), muestra(30), CELSIUS));
    expect(enKelvin.minimo).toBeCloseTo(10, 10);
    expect(enCelsius.minimo).toBeCloseTo(10, 10);
    expect(enKelvin.minimo).not.toBeCloseTo(-263.15, 1);
  });

  it("y en °F son 18, que es solo el factor", () => {
    const delta = exigirDefinido(deltaEntre(muestra(20), muestra(30), CELSIUS));
    const enF = exigirDefinido(convertirDelta(delta, 1, 1.8));
    expect(enF.minimo).toBeCloseTo(18, 10);
    // El desplazamiento de °C a °F es 32. Si se hubiera aplicado, saldría 50.
    expect(enF.minimo).not.toBeCloseTo(50, 1);
  });

  it("convertir un Δ de K a °C no lo cambia, y eso es lo correcto", () => {
    // Es el resultado que parece sospechoso —«no ha hecho nada»— y es
    // precisamente el que demuestra que no se aplicó el desplazamiento.
    const delta = exigirDefinido(deltaEntre(muestra(293.15), muestra(303.15), CELSIUS));
    const convertido = exigirDefinido(convertirDelta(delta, 1, 1));
    expect(convertido.minimo).toBeCloseTo(delta.minimo, 12);
  });

  it("un Δ siempre se declara como INTERVALO, nunca como PUNTO", () => {
    // La clase es lo que aguas abajo decide si se aplica el desplazamiento.
    // Si algún día alguien pasa este Δ a un conversor, tiene que llevar escrito
    // lo que es.
    expect(exigirDefinido(deltaEntre(muestra(1), muestra(2), CELSIUS)).clase).toBe(
      Clase.INTERVALO,
    );
  });

  it("el signo es b − a, no el valor absoluto", () => {
    // Un Δ de temperatura que baja es información: −15 °C no es 15 °C.
    const bajando = exigirDefinido(deltaEntre(muestra(30), muestra(15), CELSIUS));
    expect(bajando.minimo).toBeCloseTo(-15, 10);
  });

  it("convertir con un factor no invierte el rango aunque sea negativo", () => {
    const delta = exigirDefinido(deltaEntre(cubo(0, 10), cubo(20, 30), CELSIUS));
    const invertido = exigirDefinido(convertirDelta(delta, 1, -2));
    expect(invertido.minimo).toBeLessThanOrEqual(invertido.maximo);
  });
});

describe("los tres casos en los que un Δ no existe", () => {
  it("unidad recíproca: un Δ en λ no es un Δ en φ por ningún factor", () => {
    const d = deltaEntre(muestra(0.9), muestra(1.1), LAMBDA_A_PHI);
    expect(d.definido).toBe(false);
    if (d.definido) return;
    expect(d.motivo).toMatch(/recíproca/);
    expect(d.motivo).toMatch(/no es lineal/);
  });

  it("parámetro que cambia entre los dos cursores", () => {
    // Pasa de verdad: un log con cambio de mezcla de combustible. La conversión
    // λ→AFR es lineal pero con OTRO factor en cada extremo, así que restar los
    // dos valores mostrados da un número que no es el Δ de nada.
    const d = deltaEntre(muestra(0.95, 14.7), muestra(1.0, 9.8), LAMBDA_A_AFR);
    expect(d.definido).toBe(false);
    if (d.definido) return;
    expect(d.motivo).toMatch(/fuel_stoich_ratio/);
  });

  it("pero con el mismo parámetro en los dos, el Δ sí existe", () => {
    const d = exigirDefinido(deltaEntre(muestra(0.95, 14.7), muestra(1.0, 14.7), LAMBDA_A_AFR));
    expect(d.minimo).toBeCloseTo(0.05, 10);
  });

  it("un hueco no es un cero", () => {
    const d = deltaEntre({ hay: false }, muestra(30), CELSIUS);
    expect(d.definido).toBe(false);
    if (d.definido) return;
    expect(d.motivo).toMatch(/hueco/);
    // Lo que NO puede pasar es que el Δ salga 30 tratando el hueco como 0.
    expect(d.motivo).not.toBe("");
  });

  it("los dos cursores en un hueco tampoco dan un Δ de cero", () => {
    expect(deltaEntre({ hay: false }, { hay: false }, CELSIUS).definido).toBe(false);
  });
});

describe("a nivel decimado el Δ es un rango, no un número", () => {
  it("aritmética de intervalos: [b0 − a1, b1 − a0]", () => {
    const d = exigirDefinido(deltaEntre(cubo(10, 20), cubo(50, 60), CELSIUS));
    expect(d.minimo).toBe(30); // 50 − 20
    expect(d.maximo).toBe(50); // 60 − 10
    expect(d.exacto).toBe(false);
  });

  it("avisa cuando el rango del Δ incluye el cero", () => {
    // Dos cubos que «se ven» distintos pueden no serlo: sus rangos se solapan.
    // Sin este aviso, el usuario lee una diferencia que el dato no garantiza.
    const d = exigirDefinido(deltaEntre(cubo(10, 30), cubo(20, 40), CELSIUS));
    expect(d.incluyeCero).toBe(true);
    const { texto, nota } = textoDeDelta(d, (v) => v.toFixed(0));
    expect(texto).toContain("…");
    expect(nota).toMatch(/incluye el cero|puede no haber diferencia/);
  });

  it("con dos muestras reales el rango degenera en un número", () => {
    const d = exigirDefinido(deltaEntre(muestra(20), muestra(30), CELSIUS));
    expect(d.minimo).toBe(d.maximo);
    expect(d.exacto).toBe(true);
    expect(textoDeDelta(d, (v) => v.toFixed(1), "°C").texto).toBe("Δ 10.0 °C");
  });

  it("una muestra real contra un cubo decimado no es exacto", () => {
    // El eslabón más débil manda: si uno de los dos viene decimado, el Δ lo está.
    const d = exigirDefinido(deltaEntre(muestra(20), cubo(28, 32), CELSIUS));
    expect(d.exacto).toBe(false);
    expect(d.minimo).toBe(8);
    expect(d.maximo).toBe(12);
  });

  it("un Δ que no existe se escribe como raya, con el motivo al lado", () => {
    const { texto, nota } = textoDeDelta(
      deltaEntre(muestra(0.9), muestra(1.1), LAMBDA_A_PHI),
      (v) => v.toFixed(2),
    );
    expect(texto).toBe("—");
    expect(nota).toMatch(/recíproca/);
  });
});

describe("Δt", () => {
  it("es siempre positivo: arrastrar el segundo cursor a la izquierda no es un dato", () => {
    expect(deltaDeTiempo(10, 4)).toBe(6);
    expect(deltaDeTiempo(4, 10)).toBe(6);
  });

  it("dos cursores en el mismo instante dan cero, no un error", () => {
    expect(deltaDeTiempo(7.5, 7.5)).toBe(0);
  });
});

describe("leerEn contra la caché de F1-24", () => {
  function cubosDe(n: number): CubosContinuos {
    const t = new Float32Array(n);
    const minimo = new Float32Array(n);
    const maximo = new Float32Array(n);
    for (let i = 0; i < n; i += 1) {
      t[i] = i;
      minimo[i] = i * 10;
      maximo[i] = i * 10 + 4;
    }
    return { t, tOrigen: 0, minimo, maximo, primero: minimo, ultimo: maximo, factor: 1 };
  }

  it("fuera del tramo cargado no inventa el último cubo", () => {
    // `valorEn` no tiene cota superior: sin la comprobación de cobertura, un
    // cursor más allá del final leería el último cubo como si siguiera vigente,
    // y el Δ contra él sería un número plausible y falso.
    const cache = new CacheDeCubos();
    cache.guardar({ canal: "egt", factor: 1 }, { cubos: cubosDe(10), cubre: { t0: 0, t1: 9 } });
    expect(leerEn(cache, { canal: "egt", factor: 1 }, 5).hay).toBe(true);
    expect(leerEn(cache, { canal: "egt", factor: 1 }, 100).hay).toBe(false);
    expect(leerEn(cache, { canal: "egt", factor: 1 }, -1).hay).toBe(false);
  });

  it("un canal que no está en la caché es un hueco, no un cero", () => {
    expect(leerEn(new CacheDeCubos(), { canal: "no-esta", factor: 1 }, 1).hay).toBe(false);
  });

  it("marca como muestra solo el nivel sin decimar", () => {
    const cache = new CacheDeCubos();
    cache.guardar({ canal: "a", factor: 1 }, { cubos: cubosDe(10), cubre: { t0: 0, t1: 9 } });
    cache.guardar({ canal: "a", factor: 64 }, { cubos: cubosDe(10), cubre: { t0: 0, t1: 9 } });
    const fina = leerEn(cache, { canal: "a", factor: 1 }, 5);
    const gruesa = leerEn(cache, { canal: "a", factor: 64 }, 5);
    expect(fina.hay && fina.esMuestra).toBe(true);
    expect(gruesa.hay && gruesa.esMuestra).toBe(false);
  });

  it("leer no cuenta como consulta: mover el cursor no pide datos al backend", () => {
    // Es el presupuesto de §2.6. `mirar()` no incrementa aciertos ni fallos;
    // si esto cambiara a `consultar()`, un fallo dispararía una petición HTTP
    // por movimiento de cursor.
    const cache = new CacheDeCubos();
    cache.guardar({ canal: "a", factor: 1 }, { cubos: cubosDe(10), cubre: { t0: 0, t1: 9 } });
    cache.reiniciarEstadisticas();
    for (let i = 0; i < 50; i += 1) leerEn(cache, { canal: "a", factor: 1 }, i / 10);
    expect(cache.estadisticas.fallos).toBe(0);
    expect(cache.estadisticas.aciertos).toBe(0);
  });
});
