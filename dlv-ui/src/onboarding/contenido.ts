/**
 * Qué texto enseña `PropuestaPerfil`, sin tocar el DOM (F5-11).
 *
 * MISMA PARTICIÓN QUE `malla/geometria.ts` FRENTE A `malla/mapa-de-calor.ts`
 * =============================================================================
 * Decidir QUÉ dice el aviso -- la frase de cobertura, si hay que listar roles
 * que faltan, si hay botones que pintar -- es aritmética y una llamada a
 * `t()` (F5-10): no necesita `document` y por eso se prueba en Node sin
 * ningún doble (`contenido.test.ts`). Crear los nodos y engancharles
 * `addEventListener` sí lo necesita, y vive en `propuesta-perfil.ts`, que solo
 * pinta lo que esta función ya decidió. Un fallo de redacción (falta la cifra,
 * sobra una coma) se ve en una prueba que no abre un navegador; un fallo de
 * DOM (el botón no dispara `onAceptar`) se ve en la prueba de
 * `propuesta-perfil.ts`, que sí usa el doble de `dom/doble-documento.ts`. Las
 * dos cosas a la vez, en el mismo fichero, es lo que hoy no se puede probar
 * sin bifurcar la prueba en decisión y en pintado -- exactamente el problema
 * que esta partición evita.
 */

import { t } from "../locale/catalogo.ts";
import { validarSugerencia, type SugerenciaDePerfil } from "./tipos.ts";

/** Lo que hace falta para pintar el aviso, ya traducido y listo para meter en un nodo de texto. */
export interface ContenidoPropuesta {
  readonly textoPrincipal: string;
  /** `null` si no falta ningún rol (perfil al 100%) o si no hubo sugerencia: no hay nada que listar. */
  readonly textoFaltan: string | null;
  /** `false` cuando `sugerencia` es `null`: no hay nada que aceptar ni que descartar (decisión 1). */
  readonly tieneAcciones: boolean;
}

/**
 * Traduce una `SugerenciaDePerfil | null` al texto que hay que pintar.
 *
 * `sugerencia === null` es la respuesta legítima de `mejor_sugerencia`
 * (F3-04) cuando ningún perfil llega al mínimo de cobertura: la decisión 1
 * del informe pide "enseña algo Y di que no hubo perfil", así que este caso
 * también produce un `textoPrincipal` -- nunca cadena vacía -- y
 * `tieneAcciones: false`, porque no hay ninguna propuesta que aceptar o
 * rechazar.
 */
export function contenidoDePropuesta(sugerencia: SugerenciaDePerfil | null): ContenidoPropuesta {
  if (sugerencia === null) {
    return { textoPrincipal: t("onboarding.sinPerfilAviso"), textoFaltan: null, tieneAcciones: false };
  }
  validarSugerencia(sugerencia);
  const textoPrincipal = t("onboarding.propuestaAviso", {
    perfil: sugerencia.nombrePerfil,
    disponibles: sugerencia.disponibles,
    total: sugerencia.total,
  });
  // Solo si falta algo: un perfil al 100% no tiene nada que listar, y una
  // línea a medio rellenar ("Faltan: ") sería peor que omitirla (decisión 3
  // del informe: enseñar la cobertura no es enseñar una frase vacía).
  const textoFaltan =
    sugerencia.rolesFaltantes.length > 0
      ? t("onboarding.propuestaFaltan", { roles: sugerencia.rolesFaltantes.join(", ") })
      : null;
  return { textoPrincipal, textoFaltan, tieneAcciones: true };
}
