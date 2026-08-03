/**
 * Tipos de datos del selector de combustible.
 *
 * El caso que motiva este componente (encargo del propietario, `docs/06-sistema-
 * de-unidades.md` §6.4/§6.8): λ → AFR es una conversión PARAMETRIZADA
 * (`dlv_core.unidades.Parametrizada`) cuyo factor `a` es la estequiometría del
 * combustible en uso — 14,7 en gasolina, ~9,77 en E85, ~6,4 en metanol
 * (`data/roles.toml` [roles.stoichiometry]). Con un factor fijo, un log de E85
 * daría un AFR con aspecto correcto pero equivocado. El canal de rol
 * `stoichiometry` (`data/formats/haltech_nsp.toml` [tipos.Stoichiometry]) trae
 * ese valor en los logs que lo declaran; cuando no está, hay que asumir uno y
 * decirlo alto.
 *
 * Igual que `unidades/tipos.ts` con el catálogo de `units.toml`, este fichero
 * NO conoce `data/`: recibe el catálogo de combustibles como dato de entrada
 * (`CombustibleInfo[]`), con id/etiqueta/estequiometría y nada de lógica de
 * conversión — esa lógica (multiplicar por `a`) sigue siendo exclusiva de
 * `dlv_core.unidades.Parametrizada`. Este módulo solo decide QUÉ factor está
 * activo y de dónde vino; no convierte ningún valor.
 */

/** Un combustible del catálogo, con su estequiometría (AFR a λ = 1,000). */
export interface CombustibleInfo {
  readonly id: string;
  readonly etiqueta: string;
  /** Relación estequiométrica aire/combustible: el `a` de la conversión parametrizada. */
  readonly estequiometria: number;
  /**
   * Marca el combustible que se asume cuando el log no trae el canal de rol
   * `stoichiometry`. Debe haber exactamente uno en el catálogo (gasolina, por
   * ser el caso mayoritario de los logs del propietario); `combustiblePorOmision`
   * lanza si no lo encuentra, igual que `Catalogo.preset_por_omision` en Python.
   */
  readonly porOmision?: boolean;
}

/**
 * De dónde sale el factor de estequiometría activo. Los tres se distinguen en
 * la UI porque la regla del propietario depende de cuál es: leído del log por
 * omisión; si el usuario lo cambia, su elección gana y se guarda en el perfil
 * del coche; si el log no lo trae, se asume gasolina con un aviso visible.
 */
export enum OrigenFactor {
  /** Leído del canal de rol `stoichiometry` de este log. */
  LOG = "log",
  /** Elegido (o editado a mano) por el usuario; se persiste en el perfil del coche. */
  USUARIO = "usuario",
  /** El log no trae el canal: se asume el combustible `porOmision` del catálogo. */
  SUPUESTO = "supuesto",
}

/** Lo que el usuario ha fijado, para persistir en el perfil del coche. */
export interface EleccionUsuario {
  /** Id de un combustible del catálogo, si lo eligió de la lista. `undefined` si tecleó un valor a mano. */
  readonly combustibleId?: string;
  /** El valor a usar: el del combustible elegido, o el que el usuario tecleó. */
  readonly estequiometria: number;
}

/** El factor activo para la conversión λ → AFR, y de dónde salió. */
export interface FactorResuelto {
  readonly estequiometria: number;
  readonly origen: OrigenFactor;
  /**
   * Id del combustible del catálogo cuyo valor coincide con `estequiometria`,
   * si coincide con alguno. `undefined` para un valor editado a mano que no
   * coincide con ningún combustible catalogado (p. ej. una mezcla propia).
   */
  readonly combustibleId?: string;
}
