/**
 * Idioma activo de la interfaz (ES/EN) — fuente única de verdad (F5-10).
 *
 * POR QUÉ NO ES UN SEGUNDO `Locale`
 * ==================================
 * `numerico.ts` (F1-32) ya declara `Locale = "es" | "en"` y ya resuelve el
 * separador decimal por idioma, pero como formateador PURO: cada llamada
 * recibe el locale que quiere, sin estado propio ("este módulo solo pone el
 * separador", dice su cabecera). Lo que falta -- y es lo que este fichero
 * añade -- es UN SITIO que diga cuál es el idioma activo AHORA MISMO, para que
 * el catálogo de textos (`catalogo.ts`) y el formateador de números lean el
 * mismo valor. Sin esto, cambiar el idioma de la interfaz solo cambiaría las
 * cadenas y dejaría los números en español -- «Coolant Temperature: 92,05» --
 * que es exactamente el error de coherencia que F5-10 tiene que evitar.
 *
 * Este módulo reexporta `Locale` de `numerico.ts` en vez de declarar el suyo:
 * dos tipos `"es" | "en"` con el mismo literal pero orígenes distintos
 * habrían compilado igual y habrían sido el mismo bug en potencia de
 * `NombreTema` duplicado, solo que en TypeScript estructural no habría dado
 * ni un error.
 *
 * EL MISMO PATRÓN QUE `tema/tema.ts` (F3-21), A PROPÓSITO
 * ==========================================================
 * Entorno inyectable en vez de leer `navigator`/`localStorage` globales
 * (`vitest.config.ts` corre en `environment: "node"`, sin ellos), precedencia
 * usuario-guardado > preferencia-del-sistema > valor por omisión, y un
 * conjunto de suscriptores para avisar de un cambio. Se repite el patrón en
 * vez de generalizarlo a una fábrica «estado con preferencia persistida»
 * porque tema.ts ya advierte, en su propia cabecera, del coste de una
 * abstracción compartida entre dos cosas que cambian por separado (paleta de
 * colores aquí, idioma allí) — dos sitios que llaman a la misma función son
 * más fáciles de seguir que una fábrica genérica con un solo cliente cada
 * una hoy.
 *
 * LA PRECEDENCIA, Y POR QUÉ ESPAÑOL GANA AL NAVEGADOR SI NO HAY GUARDADA
 * =========================================================================
 * 1. Preferencia del usuario guardada en `localStorage` (una elección
 *    explícita, sobrevive a recargar).
 * 2. `navigator.language`: si empieza por "en", inglés.
 * 3. Español -- el valor por omisión de `numerico.ts#formatearNumero` y de
 *    `docs/09`: el código y los comentarios de este proyecto están en
 *    español, y su dueño trabaja en español. Un `navigator.language` que no
 *    sea inequívocamente inglés (p. ej. "fr", o ausente en una prueba) cae a
 *    español y no a una tercera opción a medio traducir.
 */

import type { Locale } from "./numerico.ts";

export type { Locale };

/**
 * Lo que este módulo necesita del navegador, y nada más. Todo opcional por el
 * mismo motivo que `tema/tema.ts#EntornoTema`: tiene que seguir funcionando a
 * trozos (sin `navegador` no hay preferencia de sistema, sin `almacen` la
 * elección no sobrevive a recargar), y ninguno de los dos casos es un error.
 */
export interface EntornoIdioma {
  readonly navegador?: { readonly language: string };
  readonly almacen?: {
    getItem(clave: string): string | null;
    setItem(clave: string, valor: string): void;
  };
}

/** El entorno real del navegador, o piezas ausentes si no hay navegador. */
export function entornoDelNavegador(): EntornoIdioma {
  return {
    navegador: typeof navigator === "undefined" ? undefined : navigator,
    almacen: typeof localStorage === "undefined" ? undefined : localStorage,
  };
}

/** El entorno con el que se inicializó. `establecerIdioma` usa el mismo. */
let entorno: EntornoIdioma = {};

const CLAVE_ALMACENAMIENTO = "dlv-idioma-preferido";

/** Idioma activo (inicializado por `inicializarIdioma()`; "es" hasta entonces). */
let idiomaActual: Locale = "es";

const suscriptores = new Set<() => void>();

/**
 * Avisa de que el idioma cambió. Igual que `tema.ts#alCambiarTema`: hace
 * falta porque no todo lo que depende del idioma se repinta solo -- el
 * cursor GPU, por ejemplo, tiene sus propias etiquetas cacheadas -- y sin un
 * aviso explícito, cambiar de idioma dejaría partes de la interfaz en el
 * idioma anterior hasta el siguiente repintado por otro motivo.
 *
 * Devuelve la función para darse de baja.
 */
export function alCambiarIdioma(reaccion: () => void): () => void {
  suscriptores.add(reaccion);
  return () => suscriptores.delete(reaccion);
}

function aplicarIdioma(idioma: Locale): void {
  const cambia = idioma !== idiomaActual;
  idiomaActual = idioma;
  if (cambia) {
    for (const reaccion of suscriptores) reaccion();
  }
}

function preferenciaDelUsuario(): Locale | null {
  const almacen = entorno.almacen;
  if (almacen === undefined) return null;
  const valor = almacen.getItem(CLAVE_ALMACENAMIENTO);
  return valor === "es" || valor === "en" ? valor : null;
}

function preferenciaDelNavegador(): Locale | null {
  const navegador = entorno.navegador;
  if (navegador === undefined) return null;
  // Solo se reconoce "en" explícitamente. Cualquier otra cosa (incluido "es",
  // "fr", o una cadena vacía en un navegador headless de pruebas) cae al
  // valor por omisión más abajo: no hay un tercer catálogo a medio traducir
  // al que repliegue un "fr-FR", así que repliega a donde SIEMPRE hay texto
  // completo.
  return navegador.language.toLowerCase().startsWith("en") ? "en" : null;
}

/**
 * Inicializa el idioma al cargar la página. Misma precedencia que
 * `tema.ts#inicializarTema`: preferencia guardada, luego navegador, luego
 * español por omisión.
 */
export function inicializarIdioma(entornoNuevo: EntornoIdioma = entornoDelNavegador()): void {
  entorno = entornoNuevo;
  const preferencia = preferenciaDelUsuario();
  if (preferencia !== null) {
    aplicarIdioma(preferencia);
    return;
  }
  const delNavegador = preferenciaDelNavegador();
  if (delNavegador !== null) {
    aplicarIdioma(delNavegador);
    return;
  }
  aplicarIdioma("es");
}

/**
 * Cambia el idioma activo explícitamente y lo guarda como preferencia del
 * usuario. Esta elección prevalece sobre `navigator.language` en la próxima
 * carga.
 */
export function establecerIdioma(idioma: Locale): void {
  aplicarIdioma(idioma);
  entorno.almacen?.setItem(CLAVE_ALMACENAMIENTO, idioma);
}

/** El idioma activo ahora mismo. Es lo que `catalogo.ts#t` y quien formatee números deben leer. */
export function obtenerIdiomaActual(): Locale {
  return idiomaActual;
}

/** Los dos idiomas soportados, en el orden en que se ofrecen en la interfaz. */
export const IDIOMAS_DISPONIBLES: readonly Locale[] = ["es", "en"];

/** Rótulo de cada idioma, en SU PROPIO idioma (así se reconoce en cualquier menú). */
export const ETIQUETA_DE_IDIOMA: Record<Locale, string> = {
  es: "Español",
  en: "English",
};
