/**
 * Precedencia del factor de estequiometría (λ → AFR), en el frontend.
 *
 * LA REGLA, TAL COMO LA FIJÓ EL PROPIETARIO
 * ==========================================
 * 1. Se lee del log por omisión (canal de rol `stoichiometry`).
 * 2. Si el usuario lo cambia, SU ELECCIÓN GANA siempre, y se guarda en el
 *    perfil del coche — no en el log ni en el catálogo.
 * 3. Si el log no trae el canal, se asume gasolina, y esa suposición se marca
 *    de forma visible: es lo único que separa un AFR correcto de uno
 *    incorrecto con aspecto de correcto (docs/06 §6.4).
 *
 * Nótese que el orden NO es el de `unidades/resolucion.ts` (canal > perfil >
 * preset > canónica): allí las tres capas son preferencias de PRESENTACIÓN
 * intercambiables sin coste. Aquí la capa "log" no es una preferencia, es un
 * DATO medido del propio fichero, y por eso el usuario solo la reemplaza si
 * decide explícitamente que está equivocada (combustible distinto al
 * registrado, o un log sin el canal). La capa "supuesto" nunca gana sobre
 * "log": no tendría sentido ignorar un dato medido para asumir uno.
 *
 * ESTO NO CONVIERTE NINGÚN VALOR
 * ===============================
 * Igual que `unidades/resolucion.ts` no importa `Afin`/`Reciproca` de
 * `dlv_core.unidades`, este módulo no multiplica nada por la estequiometría.
 * `dlv_core.unidades.Parametrizada.desde_canonica` sigue siendo el único sitio
 * que hace `a * x`; esto solo decide qué `a` está activo y por qué.
 */

import type { CombustibleInfo, EleccionUsuario, FactorResuelto } from "./tipos.ts";
import { OrigenFactor } from "./tipos.ts";

/** Uso incorrecto del catálogo de combustible — espejo de `unidades.ErrorDeUnidad`. */
export class ErrorDeCombustible extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeCombustible";
  }
}

const EXPLICACION_POR_ORIGEN: Readonly<Record<OrigenFactor, string>> = {
  [OrigenFactor.LOG]: "leído del canal de estequiometría del log",
  [OrigenFactor.USUARIO]: "elegido por el usuario; guardado en el perfil del coche",
  [OrigenFactor.SUPUESTO]:
    "el log no trae el canal de estequiometría: se asume gasolina por omisión",
};

/** Texto en español, listo para la nota junto al selector o un tooltip. */
export function explicacionDeOrigen(origen: OrigenFactor): string {
  return EXPLICACION_POR_ORIGEN[origen];
}

/** Busca un combustible por id; lanza `ErrorDeCombustible` si no existe. */
export function buscarCombustible(
  catalogo: readonly CombustibleInfo[],
  id: string,
): CombustibleInfo {
  const combustible = catalogo.find((c) => c.id === id);
  if (combustible === undefined) {
    const disponibles = catalogo.map((c) => c.id).join(", ");
    throw new ErrorDeCombustible(
      `'${id}' no es un combustible del catálogo. Disponibles: ${disponibles}`,
    );
  }
  return combustible;
}

/**
 * El combustible que se asume cuando el log no trae el canal de rol
 * `stoichiometry`. Debe haber exactamente uno marcado `porOmision` en el
 * catálogo — lanza si no lo hay, en vez de adivinar cuál sería.
 */
export function combustiblePorOmision(catalogo: readonly CombustibleInfo[]): CombustibleInfo {
  const candidatos = catalogo.filter((c) => c.porOmision);
  if (candidatos.length === 0) {
    throw new ErrorDeCombustible(
      "el catálogo de combustibles no declara ningún combustible por omisión",
    );
  }
  if (candidatos.length > 1) {
    throw new ErrorDeCombustible(
      "el catálogo de combustibles declara más de un combustible por omisión: " +
        candidatos.map((c) => c.id).join(", "),
    );
  }
  return candidatos[0]!;
}

/** El combustible del catálogo cuya estequiometría coincide con `valor`, si alguno. */
function combustibleQueCoincide(
  catalogo: readonly CombustibleInfo[],
  valor: number,
  tolerancia = 1e-9,
): CombustibleInfo | undefined {
  return catalogo.find((c) => Math.abs(c.estequiometria - valor) <= tolerancia);
}

export interface ParametrosResolucionFactor {
  readonly catalogo: readonly CombustibleInfo[];
  /** Valor leído del canal de rol `stoichiometry` de ESTE log, si lo trae. */
  readonly estequiometriaDelLog?: number;
  /** Elección persistida en el perfil del coche. Gana siempre que exista. */
  readonly eleccionUsuario?: EleccionUsuario;
}

/**
 * Resuelve qué estequiometría usar para la conversión λ → AFR de este log, y
 * de dónde salió — la precedencia de la cabecera de este módulo.
 */
export function resolverFactorEstequiometrico(
  parametros: ParametrosResolucionFactor,
): FactorResuelto {
  const { catalogo, estequiometriaDelLog, eleccionUsuario } = parametros;

  if (eleccionUsuario !== undefined) {
    return {
      estequiometria: eleccionUsuario.estequiometria,
      origen: OrigenFactor.USUARIO,
      combustibleId:
        eleccionUsuario.combustibleId ??
        combustibleQueCoincide(catalogo, eleccionUsuario.estequiometria)?.id,
    };
  }

  if (estequiometriaDelLog !== undefined) {
    return {
      estequiometria: estequiometriaDelLog,
      origen: OrigenFactor.LOG,
      combustibleId: combustibleQueCoincide(catalogo, estequiometriaDelLog)?.id,
    };
  }

  const porOmision = combustiblePorOmision(catalogo);
  return {
    estequiometria: porOmision.estequiometria,
    origen: OrigenFactor.SUPUESTO,
    combustibleId: porOmision.id,
  };
}

/**
 * Interpreta lo que el usuario tecleó en el campo de valor manual: admite
 * coma o punto decimal (`docs/06` §6.10: el separador decimal en español es
 * la coma, pero un teclado numérico suele producir punto). Devuelve
 * `undefined` para cualquier cosa que no sea un número finito estrictamente
 * positivo — una estequiometría de 0 o negativa no es invertible (mismo
 * requisito que `Parametrizada.a_por_omision` en `dlv_core.unidades`) y no
 * hay valor "razonable" que inventar en su lugar.
 */
export function analizarEstequiometriaTecleada(texto: string): number | undefined {
  const normalizado = texto.trim().replace(",", ".");
  if (normalizado === "") return undefined;
  const valor = Number(normalizado);
  if (!Number.isFinite(valor) || valor <= 0) return undefined;
  return valor;
}
