/**
 * Prueba del propio andamiaje de pruebas.
 *
 * Lo que protege es una sola cosa, y es la misma lección que
 * `tests/test_verificar.py` en el lado Python: **una suite que no recoge un
 * fichero da verde sin haber mirado**. Aquí el riesgo concreto es la partición
 * en dos configuraciones (`vitest.config.ts` para pruebas, `vitest.banco.config.ts`
 * para bancos): si los patrones `include`/`exclude` se solapan mal, o los
 * bancos se ejecutan en cada `npm test` —y la suite se vuelve lenta y se deja
 * de ejecutar— o se quedan fuera de las dos y no los ejecuta nadie.
 */

import { describe, expect, it } from "vitest";

import bancoConfig from "../vitest.banco.config.ts";
import pruebasConfig from "../vitest.config.ts";

function patrones(config: unknown, campo: "include" | "exclude"): string[] {
  const test = (config as { test?: Record<string, unknown> }).test;
  return (test?.[campo] as string[] | undefined) ?? [];
}

describe("las dos configuraciones de vitest se reparten los ficheros sin huecos", () => {
  it("`npm test` no ejecuta bancos", () => {
    expect(patrones(pruebasConfig, "exclude")).toContain("src/**/*.banco.test.ts");
  });

  it("`npm run banco` ejecuta exactamente los bancos", () => {
    expect(patrones(bancoConfig, "include")).toEqual(["src/**/*.banco.test.ts"]);
  });

  it("todo `*.test.ts` cae en una de las dos", () => {
    // `src/**/*.test.ts` incluye a `src/**/*.banco.test.ts`, así que la unión
    // de los dos `include` cubre cualquier fichero de prueba que se añada.
    expect(patrones(pruebasConfig, "include")).toContain("src/**/*.test.ts");
  });
});
