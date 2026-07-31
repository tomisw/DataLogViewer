import { defineConfig } from "vitest/config";

/**
 * Pruebas de `dlv-ui`.
 *
 * Por qué vitest y no otra cosa: ya está Vite, así que resuelve TypeScript y
 * los mismos `import` que la aplicación sin una segunda cadena de compilación.
 * Es `devDependency` de `package.json`, no de `pyproject.toml`: la regla de
 * §9.11 («meter una dependencia nueva») protege el tamaño del ZIP portable, y
 * el ZIP lleva `dist/` ya compilado, no `node_modules`. Aun así queda dicho en
 * el informe de la tarea, porque la regla es del propietario y no mía.
 *
 * Entorno `node`, no `jsdom`: lo que se prueba aquí es aritmética (escalas,
 * elección de nivel de pirámide, formato de valores) y el contrato de llamadas
 * a WebGL contra un doble. Un DOM simulado no aporta nada a eso y añade una
 * dependencia más. Lo que sí necesita navegador de verdad —la regresión
 * visual obligatoria de ADR-006— es la tarea F5-12, con su propia herramienta.
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    // Los bancos miden tiempo y no son deterministas: se ejecutan aparte, con
    // `npm run banco`. Una suite de pruebas que a veces tarda 30 s deja de
    // ejecutarse, y una que no se ejecuta no protege nada.
    exclude: ["src/**/*.banco.test.ts", "node_modules/**"],
  },
});
