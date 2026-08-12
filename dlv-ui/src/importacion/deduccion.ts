/**
 * Reglas puras sobre `RolPropuesto` (`tipos.ts`): cuándo una asignación de rol
 * está pendiente de confirmar, y qué consecuencia tiene aguas abajo.
 *
 * `docs/07` §7.15, mitigación 4, es la razón de ser de este fichero entero:
 *
 *     «Los detectores de severidad crítica (D4, D10, D12) SE DESACTIVAN en un
 *     log cuyos roles implicados provengan de asignación difusa no
 *     confirmada por el usuario. Preferimos no avisar a avisar en falso…»
 *
 * `dlv_core.roles.Asignacion.requiere_confirmacion` ya calcula la mitad de
 * esto en Python (`confianza is DIFUSA`), pero esa propiedad no sabe si el
 * USUARIO ya confirmó — eso es estado de la sesión de importación, que vive
 * en el frontend mientras el asistente está abierto. `requiereConfirmacion`
 * de aquí es el espejo completo: difusa Y sin confirmar todavía.
 */

import type { RolPropuesto } from "./tipos.ts";

/**
 * Construye la propuesta inicial de rol a partir de lo que devolvería
 * `asignar_rol` (docs/10 §10.4): `EXACTA` e `INDEXADA` nacen confirmadas —son
 * firmes por construcción, no hay nada que revisar—, `DIFUSA` nace sin
 * confirmar.
 */
export function propuestaInicialDeRol(datos: {
  readonly rol: string;
  readonly confianza: RolPropuesto["confianza"];
  readonly sinonimo: string;
  readonly indice?: number | null;
  readonly parecido?: number;
}): RolPropuesto {
  return {
    rol: datos.rol,
    confianza: datos.confianza,
    sinonimo: datos.sinonimo,
    indice: datos.indice ?? null,
    parecido: datos.parecido ?? 1.0,
    confirmado: datos.confianza !== "DIFUSA",
  };
}

/** El usuario ha revisado la propuesta y la acepta tal cual (docs/10 §10.5). */
export function confirmarRol(rol: RolPropuesto): RolPropuesto {
  return { ...rol, confirmado: true };
}

/**
 * El usuario cambia el rol a mano (lo corrige, o asigna uno donde no había
 * ninguno). Un rol elegido por una persona no "requiere confirmación": ya ES
 * la confirmación.
 */
export function asignarRolManualmente(rol: string): RolPropuesto {
  return { rol, confianza: "DIFUSA", sinonimo: rol, indice: null, parecido: 1.0, confirmado: true };
}

/**
 * `true` si esta asignación es exactamente el caso que §7.15 no deja pasar:
 * difusa y todavía sin que una persona la haya mirado.
 *
 * `rol === null` (canal sin rol, docs/07 §7.8: "se puede importar dejando
 * canales sin rol") no requiere confirmación — no hay nada que confirmar, el
 * canal simplemente no participa en perfiles ni detectores, y eso no es un
 * riesgo de falso positivo.
 */
export function requiereConfirmacion(rol: RolPropuesto | null): boolean {
  return rol !== null && rol.confianza === "DIFUSA" && !rol.confirmado;
}

/**
 * La mitigación 4 de §7.15, como una función que puede llamar cualquier
 * detector crítico (D4, D10, D12) antes de activarse: si CUALQUIERA de los
 * roles que ese detector necesita viene de una difusa sin confirmar, el
 * detector no se activa en este log — todavía.
 *
 * Recibe una lista y no un solo rol porque un detector real casi siempre
 * necesita más de uno (p. ej. D12 puede necesitar `boost_pressure_actual` Y
 * `wastegate_duty`), y basta con que UNO de los implicados sea dudoso para
 * que la conclusión del detector sea dudosa.
 */
export function debeDesactivarDetectorCritico(rolesImplicados: readonly (RolPropuesto | null)[]): boolean {
  return rolesImplicados.some(requiereConfirmacion);
}

/** Resumen para el banner del paso 3: cuántos canales están en cada estado. */
export interface ResumenConfianza {
  readonly exactas: number;
  readonly indexadas: number;
  readonly difusasConfirmadas: number;
  readonly difusasPendientes: number;
  readonly sinRol: number;
}

export function resumirConfianza(
  canales: readonly { readonly rol: RolPropuesto | null }[],
): ResumenConfianza {
  const contadores = {
    exactas: 0,
    indexadas: 0,
    difusasConfirmadas: 0,
    difusasPendientes: 0,
    sinRol: 0,
  };
  for (const { rol } of canales) {
    if (rol === null) {
      contadores.sinRol += 1;
    } else if (rol.confianza === "EXACTA") {
      contadores.exactas += 1;
    } else if (rol.confianza === "INDEXADA") {
      contadores.indexadas += 1;
    } else if (rol.confirmado) {
      contadores.difusasConfirmadas += 1;
    } else {
      contadores.difusasPendientes += 1;
    }
  }
  return contadores;
}

/** Texto para el banner, o cadena vacía si no hay nada pendiente que avisar. */
export function textoPendientesDeConfirmar(resumen: ResumenConfianza): string {
  if (resumen.difusasPendientes === 0) return "";
  const plural = resumen.difusasPendientes === 1 ? "" : "s";
  return (
    `${resumen.difusasPendientes} rol${plural} propuesto${plural} por parecido, sin confirmar: ` +
    "los detectores críticos que los necesiten quedarán desactivados en este log hasta que los confirmes."
  );
}
