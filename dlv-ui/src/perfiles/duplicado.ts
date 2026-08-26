/**
 * Duplicar un perfil: la única vía para partir de uno existente sin romperlo
 * (F3-05, decisión 1 del informe de la tarea).
 *
 * "CREAR" ES "DUPLICAR": NO HAY UN PERFIL EN BLANCO
 * ====================================================
 * `dlv_core.perfil.Panel` exige al menos un elemento, y un elemento exige un
 * `rol` (o un `id_nativo`, la reserva estrecha de docs/07 §7.12). Elegir ese
 * primer rol necesita el catálogo de `data/roles.toml` — 112 roles tras F0-10
 * — que esta tarea no trae: F3-05 depende solo de F3-01 (el esquema), no de
 * un selector de roles. Un perfil "en blanco" de verdad, con cero paneles o un
 * panel sin elementos, no es un `Perfil` válido, así que ofrecer un botón
 * "crear desde cero" sería ofrecer un botón que siempre falla al primer campo.
 *
 * Por eso el editor no distingue "crear" de "duplicar": crear un perfil nuevo
 * ES duplicar uno existente (de fábrica — E4.2/F3-03 — o propio) y darle un
 * nombre nuevo. E4.4 lista "duplicado" como su primer verbo, antes que
 * "editor" a secas, y esta es la razón concreta: sin un perfil de partida no
 * hay nada editable que siga siendo válido.
 *
 * QUÉ CAMBIA AL DUPLICAR, Y CÓMO NO SE PISA EL ORIGINAL
 * ========================================================
 * El esquema de `perfil.py` no tiene ningún campo de identidad aparte de
 * `nombre` (decisión 4 de esa cabecera: JSON versionado, sin un `id` que
 * mantener sincronizado). La identidad de un `.dlvprofile` en disco es su
 * RUTA de fichero, y esa ruta la decide quien lo guarda (`dlv-api`, cuando
 * tenga el endpoint — ver el informe de la tarea), no este módulo. Lo que SÍ
 * puede garantizar `duplicarPerfil` sin tocar ningún fichero es que el
 * `nombre` del duplicado nunca coincida con uno ya en uso: `nombresExistentes`
 * es la lista de nombres que ya existen (de fábrica + del usuario, mezclados:
 * un duplicado de un perfil de fábrica no puede llamarse igual que otro
 * perfil de usuario, ni al revés), y quien guarde el resultado puede derivar
 * de ese nombre único un nombre de fichero único sin más comprobación.
 *
 * El resto del perfil —paneles, límites, unidades, detectores, eje X— se
 * copia IDÉNTICO. No hay ninguna razón de dominio para que duplicar cambie
 * nada más: es la manera de decir "quiero este perfil, pero mío", no una
 * forma de crear una plantilla distinta.
 */

import type { Perfil } from "./perfil.ts";
import { construirPerfil } from "./perfil.ts";

const SUFIJO_COPIA = "copia";

/**
 * Un nombre derivado de `nombreOriginal` que no está en `nombresExistentes`.
 *
 * "Panel Motor" -> "Panel Motor (copia)" -> "Panel Motor (copia 2)" -> ...
 * Nunca "(copia 1)": la primera copia no lleva número, igual que un fichero
 * duplicado por un explorador de ficheros no dice "(1)" en el primer intento.
 */
export function sugerirNombreDuplicado(
  nombreOriginal: string,
  nombresExistentes: ReadonlySet<string> | readonly string[],
): string {
  const existentes = nombresExistentes instanceof Set ? nombresExistentes : new Set(nombresExistentes);
  const base = `${nombreOriginal} (${SUFIJO_COPIA})`;
  if (!existentes.has(base)) return base;
  let n = 2;
  let candidato = `${nombreOriginal} (${SUFIJO_COPIA} ${n})`;
  while (existentes.has(candidato)) {
    n += 1;
    candidato = `${nombreOriginal} (${SUFIJO_COPIA} ${n})`;
  }
  return candidato;
}

/**
 * Duplica `perfil`: mismo contenido, `nombre` nuevo y garantizado único frente
 * a `nombresExistentes`. `nombreSugerido`, si se pasa, se usa tal cual siempre
 * que no colisione (es lo que hace un usuario que teclea su propio nombre en
 * el diálogo de duplicar); si colisiona o no se pasa, se deriva uno con
 * `sugerirNombreDuplicado`.
 */
export function duplicarPerfil(
  perfil: Perfil,
  nombresExistentes: ReadonlySet<string> | readonly string[],
  nombreSugerido?: string,
): Perfil {
  const existentes = nombresExistentes instanceof Set ? nombresExistentes : new Set(nombresExistentes);
  const nombre =
    nombreSugerido !== undefined && nombreSugerido.trim() !== "" && !existentes.has(nombreSugerido)
      ? nombreSugerido
      : sugerirNombreDuplicado(perfil.nombre, existentes);
  return construirPerfil({
    nombre,
    descripcion: perfil.descripcion,
    paneles: perfil.paneles,
    unidades: perfil.unidades,
    limites: perfil.limites,
    detectoresActivos: perfil.detectoresActivos,
    ejeXPreferido: perfil.ejeXPreferido,
  });
}
