/**
 * `t()`: la única función que traduce texto de interfaz en `dlv-ui` (F5-10).
 *
 * SIN DEPENDENCIAS, A PROPÓSITO
 * ===============================
 * `dlv-ui` tiene cero dependencias en tiempo de ejecución (`docs/09`); nada
 * de `i18next` ni similares. Lo que hace falta aquí es diminuto: una tabla
 * clave → texto por idioma, una sustitución de `{variable}` y una regla para
 * cuando falta una clave. `Intl` (que sí está disponible y que `numerico.ts`
 * ya usa) no ofrece nada de esto -- resuelve formato de número, fecha y
 * plural, no catálogos de cadenas -- así que no hay nada que envolver.
 *
 * DECISIÓN §1 DEL INFORME: QUÉ PASA CON UNA CLAVE QUE FALTA
 * =============================================================
 * Tres opciones sobre la mesa: caer al otro idioma, enseñar la clave cruda,
 * o que no compile. Se usan LAS TRES, en capas, no una sola:
 *
 * 1. **Primera línea de defensa, en tiempo de compilación:** `TEXTOS_EN` está
 *    tipado como `Record<ClaveTexto, string>` (ver `textos.en.ts`), así que
 *    a un catálogo con una clave de menos o de más `tsc --noEmit` ya no lo
 *    deja pasar. Es la defensa que de verdad importa: se ejecuta en cada
 *    build, no solo cuando alguien se acuerda de correr una prueba.
 * 2. **Segunda línea, en tiempo de ejecución, para lo que el tipo no puede
 *    ver:** si a pesar de eso `CATALOGOS[idioma][clave]` diera
 *    `undefined` (una clave llegada por un camino no tipado, o un desajuste
 *    real entre los dos objetos que el tipado no detectó porque alguien usó
 *    `as`), `t()` cae al español -- el catálogo CANÓNICO y siempre completo
 *    (`textos.es.ts` es de donde sale `ClaveTexto`) -- y avisa por consola.
 *    Lo que NUNCA se hace es devolver `""`: la propia tarea lo señala como
 *    el peor caso («un botón sin texto no se puede pulsar y nadie sabe por
 *    qué»), y caer al español dijo siempre algo, aunque no sea el idioma
 *    pedido.
 * 3. **Si ni siquiera el español la tiene** (la clave no existe en ningún
 *    catálogo -- un typo real): se devuelve la propia clave entre corchetes.
 *    Sigue sin ser "", y además es reconocible a simple vista como un fallo
 *    de programación, no como un texto vacío que parece intencionado.
 *
 * DECISIÓN §2: CÓMO SE PRUEBA QUE LOS DOS CATÁLOGOS COINCIDEN
 * ================================================================
 * `catalogo.test.ts` compara `Object.keys(TEXTOS_ES)` con
 * `Object.keys(TEXTOS_EN)` (mismo tamaño, mismo conjunto) además de recorrer
 * cada clave y comprobar que ninguna traducción quedó vacía. Es la prueba
 * que se pide explícitamente en el encargo: «se detecta con una prueba, no
 * con disciplina». Corre en `npm test`, junto a todo lo demás, así que un
 * catálogo que se desincroniza rompe CI y no depende de que quien lo tocó se
 * acuerde de mirar el otro fichero.
 */

import { obtenerIdiomaActual } from "./idioma.ts";
import { TEXTOS_ES } from "./textos.es.ts";
import { TEXTOS_EN } from "./textos.en.ts";

/** Las claves válidas de texto: exactamente las que declara el catálogo español (el canónico). */
export type ClaveTexto = keyof typeof TEXTOS_ES;

const CATALOGOS: Record<"es" | "en", Record<ClaveTexto, string>> = {
  es: TEXTOS_ES,
  en: TEXTOS_EN,
};

/**
 * Sustituye `{nombre}` en una plantilla por `variables.nombre`. Una
 * implementación de un `String.replace` con regex, no una librería de
 * plantillas: el catálogo entero tiene un puñado de cadenas con como mucho
 * una o dos variables (`"{n} canal(es) oculto(s)"`), y las llaves sin cerrar
 * o los `{}` literales no aparecen en ninguna cadena del catálogo -- no hace
 * falta un motor más completo que esto.
 */
function sustituir(plantilla: string, variables: Readonly<Record<string, string | number>>): string {
  return plantilla.replace(/\{(\w+)\}/g, (coincidencia, nombre: string) =>
    Object.prototype.hasOwnProperty.call(variables, nombre) ? String(variables[nombre]) : coincidencia,
  );
}

/**
 * El texto de `clave` en el idioma activo (`locale/idioma.ts#obtenerIdiomaActual`),
 * con las variables de la plantilla sustituidas si se pasan.
 *
 * Quien llama con una clave literal (`t("canales.buscarPlaceholder")`) tiene
 * la garantía de TypeScript de que existe en los dos catálogos (ver la
 * cabecera). El repliegue de abajo es para lo que el tipo no cubre.
 */
export function t(clave: ClaveTexto, variables?: Readonly<Record<string, string | number>>): string {
  const idioma = obtenerIdiomaActual();
  let plantilla: string | undefined = CATALOGOS[idioma][clave];
  if (plantilla === undefined) {
    plantilla = TEXTOS_ES[clave];
    if (plantilla === undefined) {
      // Ni siquiera el catálogo canónico la tiene: typo real en la clave.
      console.error(`locale/catalogo: clave de texto desconocida «${String(clave)}»`);
      return `[${String(clave)}]`;
    }
    console.error(
      `locale/catalogo: «${String(clave)}» no existe en el catálogo '${idioma}'; usando español`,
    );
  }
  return variables === undefined ? plantilla : sustituir(plantilla, variables);
}
