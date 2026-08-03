/**
 * Búsqueda difusa por subsecuencia con puntuación por proximidad (F1-33).
 *
 * El requisito es concreto: quien escribe `cltmp` busca "Coolant
 * Temperature", así que basta con comprobar que los caracteres del patrón
 * aparecen en el texto EN ORDEN (subsecuencia) -- no hace falta que sean
 * contiguos -- y puntuar mejor las coincidencias más "apretadas": caracteres
 * consecutivos, coincidencias al principio de una palabra y textos más
 * cortos alrededor de lo encontrado. No es el algoritmo de `fzf` ni de VS
 * Code; es la versión mínima que cumple "puntuación por proximidad basta"
 * (F1-33) y que cabe en una función que se puede revisar de una sentada.
 *
 * COMPLEJIDAD
 * ===========
 * `O(longitud_texto · longitud_patrón)` por llamada. Los nombres de canal
 * Haltech no pasan de unas pocas decenas de caracteres y una consulta de
 * usuario rara vez pasa de 20, así que esto es microsegundos por canal.
 * Filtrar los 475 canales del AutoLog real en cada pulsación es entonces
 * lineal en el número de canales (`filtro.ts` llama esto como mucho tres
 * veces por canal), no cuadrático -- que es la parte que de verdad importa
 * para el presupuesto de "no hagas trabajo cuadrático por pulsación".
 *
 * NORMALIZACIÓN
 * ==============
 * Minúsculas y sin acentos, igual de espíritu que `normalizar` en
 * `dlv_core.roles` (ADR-008) aunque con un objetivo distinto: allí se colapsan
 * separadores para comparar IGUALDAD de nombre; aquí se necesita el texto
 * completo (con espacios) para poder puntuar "principio de palabra", así que
 * los separadores NO se quitan, solo se usan como frontera.
 */

const BASE_POR_CARACTER = 1;
const BONIFICACION_CONSECUTIVO = 3;
const BONIFICACION_INICIO_DE_PALABRA = 2;
/**
 * Penalización de proximidad aplicada, al final, por cada carácter del texto
 * que no participó en la coincidencia. Pequeña a propósito: es un criterio de
 * desempate entre textos con la misma calidad de coincidencia (p. ej. "RPM"
 * por delante de "RPM Limiting Method" al buscar "rpm"), no algo que deba
 * poder invertir el orden que ya dan las bonificaciones de arriba.
 */
const PENALIZACION_POR_CARACTER_SIN_EMPAREJAR = 0.05;

const SEPARADORES = /[\s_\-./\\()[\]{}:,;+]/;

function normalizarParaBusqueda(texto: string): string {
  // NFKD separa cada letra acentuada en base + marca de combinación
  // (`á` -> `a` + U+0301); el rango U+0300-U+036F son esas marcas y se
  // eliminan, dejando solo la base. Así "Régimen" y "regimen" puntúan igual.
  const sinAcentos = texto.normalize("NFKD").replace(/[̀-ͯ]/g, "");
  return sinAcentos.toLowerCase();
}

function esInicioDePalabra(texto: string, indice: number): boolean {
  if (indice === 0) return true;
  return SEPARADORES.test(texto[indice - 1]!);
}

/**
 * ¿Es `patron` una subsecuencia de `texto` (sin distinguir mayúsculas ni
 * acentos)? Si lo es, devuelve una puntuación donde más alto es mejor
 * coincidencia; si no, `null`.
 *
 * Patrón vacío devuelve `0` (todo coincide igual de "bien": es el caso de la
 * caja de búsqueda vacía, que `filtro.ts` ni siquiera llega a invocar pero
 * que esta función deja definido en vez de indocumentado).
 *
 * PROGRAMACIÓN DINÁMICA, NO BACKTRACKING
 * =======================================
 * Un escaneo voraz (primera aparición de cada carácter) encontraría *una*
 * subsecuencia válida, pero no necesariamente la de mejor puntuación: para
 * "cltmp" en "coolant temperature", la "t" voraz cae en la posición 6 (dentro
 * de "coolant") y deja la "m" de "temperature" más lejos de lo necesario. La
 * tabla de abajo considera, en cada posición del texto, tanto seguir una
 * racha que ya empezó ADYACENTE como retomarla más adelante, y se queda con
 * lo mejor de las dos.
 */
export function coincidenciaDifusa(patronCrudo: string, textoCrudo: string): number | null {
  const patron = normalizarParaBusqueda(patronCrudo);
  const texto = normalizarParaBusqueda(textoCrudo);
  const m = patron.length;
  const n = texto.length;

  if (m === 0) return 0;
  if (m > n) return null;

  const SIN_COINCIDENCIA = Number.NEGATIVE_INFINITY;

  // `mejor[j]`: mejor puntuación para haber emparejado los primeros `j`
  // caracteres del patrón usando el texto visto hasta ahora (en cualquier
  // posición, no necesariamente la última mirada). Persiste sin tocar entre
  // iteraciones cuando el carácter actual no empareja: eso ES "saltar" este
  // carácter del texto, sin necesidad de una rama explícita para ello.
  const mejor = new Float64Array(m + 1).fill(SIN_COINCIDENCIA);
  mejor[0] = 0;

  // `mejorAdyacente[j]`: como `mejor[j]`, pero solo válido cuando el último
  // carácter emparejado fue el mirado en la iteración ANTERIOR -- es lo que
  // permite dar la bonificación de racha consecutiva sin guardar posiciones.
  // Se reconstruye entera cada iteración: si esta vuelta no amplía la racha,
  // deja de estar "adyacente" a la siguiente.
  let mejorAdyacente = new Float64Array(m + 1).fill(SIN_COINCIDENCIA);

  for (let i = 0; i < n; i += 1) {
    const caracter = texto[i]!;
    const nuevaAdyacente = new Float64Array(m + 1).fill(SIN_COINCIDENCIA);
    const bonificacionInicio = esInicioDePalabra(texto, i) ? BONIFICACION_INICIO_DE_PALABRA : 0;

    for (let j = 1; j <= m; j += 1) {
      if (patron[j - 1] !== caracter) continue;

      const previa = mejor[j - 1]!;
      const previaAdyacente = mejorAdyacente[j - 1]!;
      const desdeNoAdyacente =
        previa === SIN_COINCIDENCIA ? SIN_COINCIDENCIA : previa + BASE_POR_CARACTER + bonificacionInicio;
      const desdeAdyacente =
        previaAdyacente === SIN_COINCIDENCIA
          ? SIN_COINCIDENCIA
          : previaAdyacente + BASE_POR_CARACTER + BONIFICACION_CONSECUTIVO + bonificacionInicio;

      const puntuacion = Math.max(desdeNoAdyacente, desdeAdyacente);
      if (puntuacion === SIN_COINCIDENCIA) continue;

      nuevaAdyacente[j] = puntuacion;
      if (puntuacion > mejor[j]!) mejor[j] = puntuacion;
    }

    mejorAdyacente = nuevaAdyacente;
  }

  const puntuacionFinal = mejor[m]!;
  if (puntuacionFinal === SIN_COINCIDENCIA) return null;

  const caracteresSinEmparejar = n - m;
  return puntuacionFinal - caracteresSinEmparejar * PENALIZACION_POR_CARACTER_SIN_EMPAREJAR;
}
