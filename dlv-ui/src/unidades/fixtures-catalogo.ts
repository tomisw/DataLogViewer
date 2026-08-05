/**
 * Catálogo de prueba para `resolucion.test.ts` y `selector-unidad.test.ts`.
 *
 * Es una pequeña muestra ILUSTRATIVA con la forma de `data/units.toml`, no una
 * copia de sus valores: solo hay id/etiqueta/decimales, nunca un factor de
 * conversión (`a`, `b`), porque este componente no convierte nada (ver la
 * cabecera de `resolucion.ts`). Sirve para probar la PRECEDENCIA y el
 * FORMATEO por decimales sin acoplar las pruebas al fichero de datos real,
 * que es del propietario y pasa por la puerta G1 de F0-08.
 */

import type { CatalogoUnidades } from "./tipos.ts";

export function catalogoDePrueba(): CatalogoUnidades {
  return {
    dimensiones: [
      {
        id: "temperature",
        etiqueta: "Temperatura",
        unidadCanonica: "K",
        convertible: true,
        unidades: [
          { id: "K", etiqueta: "K", decimales: 1, conversion: { tipo: "afin", a: 1, b: 0 } },
          { id: "degC", etiqueta: "°C", decimales: 1, conversion: { tipo: "afin", a: 1, b: -273.15 } },
          { id: "degF", etiqueta: "°F", decimales: 1, conversion: { tipo: "afin", a: 1.8, b: -459.67 } },
        ],
      },
      {
        id: "pressure",
        etiqueta: "Presión",
        unidadCanonica: "kPa",
        convertible: true,
        unidades: [
          { id: "kPa", etiqueta: "kPa", decimales: 0, conversion: { tipo: "afin", a: 1, b: 0 } },
          { id: "bar", etiqueta: "bar", decimales: 2, conversion: { tipo: "afin", a: 0.01, b: 0 } },
          { id: "psi", etiqueta: "psi", decimales: 1, conversion: { tipo: "afin", a: 0.14503773773, b: 0 } },
        ],
      },
      {
        id: "mixture_ratio",
        etiqueta: "Mezcla",
        unidadCanonica: "lambda",
        convertible: true,
        unidades: [
          { id: "lambda", etiqueta: "λ", decimales: 3, conversion: { tipo: "afin", a: 1, b: 0 } },
          { id: "afr", etiqueta: "AFR", decimales: 2, conversion: { tipo: "afin", a: 1, b: 0 } },
        ],
      },
      {
        id: "sound_level",
        etiqueta: "Nivel de sonido",
        unidadCanonica: "dB",
        convertible: false,
        unidades: [{ id: "dB", etiqueta: "dB", decimales: 1, conversion: { tipo: "afin", a: 1, b: 0 } }],
      },
      {
        id: "unknown",
        etiqueta: "Sin confirmar",
        unidadCanonica: "raw",
        convertible: false,
        mostrarEnCrudo: true,
        unidades: [{ id: "raw", etiqueta: "(crudo)", decimales: 0, conversion: { tipo: "afin", a: 1, b: 0 } }],
      },
    ],
    presets: [
      {
        id: "metrico",
        etiqueta: "Métrico",
        unidades: { temperature: "degC", pressure: "bar", mixture_ratio: "lambda" },
      },
      {
        id: "imperial",
        etiqueta: "Imperial",
        unidades: { temperature: "degF", pressure: "psi", mixture_ratio: "afr" },
      },
      {
        // A propósito no cubre `mixture_ratio`, igual que `si`/`metrico`/`imperial`
        // no cubren `angle` en `units.toml`: prueba la caída a canónica del §6.9.
        id: "si",
        etiqueta: "SI puro",
        unidades: { temperature: "K", pressure: "kPa" },
      },
    ],
    presetPorOmision: "metrico",
    combustibles: [],
  };
}
