import { defineConfig } from "vitest/config";

/**
 * Bancos de rendimiento de `dlv-ui` (`npm run banco`).
 *
 * Separados de `npm test` a propósito: miden tiempo, tardan, y algunos
 * necesitan una GPU de verdad. Mezclarlos con las pruebas haría que la suite
 * fuese lenta y ocasionalmente roja por motivos que no son defectos, y una
 * suite así se acaba ignorando.
 *
 * Los presupuestos que estos bancos comprueban están en `docs/02` §2.6 y son
 * puertas, no aspiraciones. Cuando un banco no puede medir (sin GPU, sin
 * WebGL2) **no da verde**: da "no medido", que es lo que exige la lección de
 * §8.10 —no haber podido mirar no es estar en verde—.
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.banco.test.ts"],
    // Un banco que compite por CPU con otro banco mide ruido.
    fileParallelism: false,
    testTimeout: 120_000,
  },
});
