import { defineConfig } from "vite";

// Configuración mínima de Vite para dlv-ui (F0-02). Sin librerías de
// gráficos (ADR-006): el lienzo WebGL2 y las capas SVG se añaden en fases
// posteriores directamente sobre `src/`.
//
// `npm run preview:red` (F5-06, docs/11-despliegue-navegador.md) llama a
// `vite preview --host 0.0.0.0` desde la línea de comandos para escuchar en
// todas las interfaces y no solo en loopback -- es lo que hace que otro
// equipo de la red pueda cargar `dist/`. No hace falta nada aquí para eso:
// `--host` es una opción de la CLI de `vite preview`, no de este fichero. Lo
// único que SÍ importa desde aquí es que `outDir` siga siendo `dist`, porque
// es la carpeta que ese comando sirve.
export default defineConfig({
  build: {
    outDir: "dist",
  },
});
