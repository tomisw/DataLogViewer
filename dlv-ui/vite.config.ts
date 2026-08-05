import { defineConfig } from "vite";

// Configuración mínima de Vite para dlv-ui (F0-02). Sin librerías de
// gráficos (ADR-006): el lienzo WebGL2 y las capas SVG se añaden en fases
// posteriores directamente sobre `src/`.
export default defineConfig({
  build: {
    outDir: "dist",
  },
});
