/**
 * Precedencia de unidad activa por canal, en el frontend (F1-31).
 *
 * ESTO NO ES UNA SEGUNDA IMPLEMENTACIÓN DE F1-17
 * ===============================================
 * `dlv_core.resolucion_unidad.resolver_unidad` ya existe y es la referencia:
 * canal > dimensión del perfil > preset global > canónica (`docs/06` §6.9).
 * Ese módulo vive en Python, corre en `dlv-api`, y este frontend no puede
 * importarlo — no hay un runtime compartido entre `dlv-core` y `dlv-ui`
 * (ADR-002/ADR-007: se hablan por HTTP/Arrow, no por import). Para que el
 * SELECTOR pueda pintar «de dónde viene la unidad efectiva de cada canal»
 * antes de que el usuario suelte el ratón, la misma regla de precedencia
 * tiene que poder evaluarse también en TypeScript, sin ida y vuelta al
 * backend por cada cambio.
 *
 * La frontera que si se respeta es la de conversión de VALORES: este fichero
 * no tiene `Afin`, `Reciproca`, `Parametrizada`, ni `desde_canonica`/
 * `a_canonica`. Solo decide QUÉ id de unidad gana y expone cómo formatear un
 * número ya convertido con los decimales de esa unidad — la aritmética de la
 * conversión en sí sigue siendo exclusiva de `dlv_core.unidades`, en el
 * backend o en quien repinte los cubos (§6.11: "la conversión se aplica a los
 * cubos visibles"). Este módulo nunca ve una muestra.
 *
 * LA TRAMPA DEL DELTA, AQUÍ
 * =========================
 * Como este módulo no convierte valores, no puede reintroducir el fallo de
 * aplicar un desplazamiento a una diferencia (`docs/06` §6.2): no hay `b` en
 * ningún sitio de este fichero. `formatearValor` solo redondea y sustituye el
 * separador decimal de un número que YA llegó convertido y con su `Clase`
 * aplicada por quien hizo la conversión.
 */

import type {
  CatalogoUnidades,
  DimensionInfo,
  PresetInfo,
  UnidadInfo,
  UnidadResuelta,
} from "./tipos.ts";
import { Capa } from "./tipos.ts";
// El separador decimal lo pone `src/locale/numerico.ts` (F1-32), único sitio
// del frontend que convierte un número en texto. Aquí se decide CUÁNTOS
// decimales —los de la unidad, `data/units.toml`— y allí con qué separador.
import { formatearNumero, type Locale } from "../locale/numerico.ts";

/** Uso incorrecto del sistema de unidades — espejo de `unidades.ErrorDeUnidad`. */
export class ErrorDeUnidad extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeUnidad";
  }
}

const EXPLICACION_POR_CAPA: Readonly<Record<Capa, string>> = {
  [Capa.CANAL]: "anulación explícita de unidad para este canal",
  [Capa.PERFIL]: "preferencia de unidad de la dimensión en el perfil activo",
  [Capa.PRESET]: "preset global activo",
  [Capa.CANONICA]: "unidad canónica de la dimensión: no hay ninguna capa más específica",
};

/** Texto en español, listo para un tooltip o una nota de depuración. */
export function explicacionDeCapa(capa: Capa): string {
  return EXPLICACION_POR_CAPA[capa];
}

/** Busca una dimensión por id; lanza `ErrorDeUnidad` si no existe, igual que `Catalogo.dimension`. */
export function buscarDimension(catalogo: CatalogoUnidades, dimensionId: string): DimensionInfo {
  const dimension = catalogo.dimensiones.find((d) => d.id === dimensionId);
  if (dimension === undefined) {
    throw new ErrorDeUnidad(`dimensión desconocida: '${dimensionId}'`);
  }
  return dimension;
}

/** Busca una unidad por id o alias dentro de una dimensión; igual que `Dimension.unidad`. */
export function buscarUnidad(dimension: DimensionInfo, idOAlias: string): UnidadInfo {
  const unidad = dimension.unidades.find(
    (u) => u.id === idOAlias || (u.alias?.includes(idOAlias) ?? false),
  );
  if (unidad === undefined) {
    const disponibles = dimension.unidades.map((u) => u.id).join(", ");
    throw new ErrorDeUnidad(
      `'${idOAlias}' no es una unidad de la dimensión '${dimension.id}'. Disponibles: ${disponibles}`,
    );
  }
  return unidad;
}

function buscarPreset(catalogo: CatalogoUnidades, nombrePreset: string): PresetInfo {
  const preset = catalogo.presets.find((p) => p.id === nombrePreset);
  if (preset === undefined) {
    throw new ErrorDeUnidad(`preset desconocido: '${nombrePreset}'`);
  }
  return preset;
}

export interface ParametrosResolucion {
  readonly dimensionId: string;
  readonly catalogo: CatalogoUnidades;
  /** `undefined` = «usa el preset por omisión del catálogo», no «sin preset». */
  readonly preset?: string;
  readonly preferenciasPerfil?: Readonly<Record<string, string>>;
  readonly anulacionCanal?: string;
}

/**
 * Resuelve qué `UnidadInfo` usar para un canal de la dimensión `dimensionId`.
 *
 * Precedencia, de mayor a menor (`docs/06` §6.9, idéntica a
 * `resolucion_unidad.resolver_unidad` de F1-17):
 *
 * 1. `anulacionCanal` — si se da, gana siempre.
 * 2. `preferenciasPerfil[dimensionId]` — si el perfil activo fija una unidad
 *    para esta dimensión.
 * 3. El preset (`preset`, o `catalogo.presetPorOmision` si no se pasa
 *    ninguno) — si ese preset declara una unidad para esta dimensión.
 * 4. La unidad canónica de la dimensión — siempre existe.
 */
export function resolverUnidad(parametros: ParametrosResolucion): UnidadResuelta {
  const { dimensionId, catalogo, preset, preferenciasPerfil, anulacionCanal } = parametros;
  const dimension = buscarDimension(catalogo, dimensionId);

  if (anulacionCanal !== undefined) {
    return { unidad: buscarUnidad(dimension, anulacionCanal), capa: Capa.CANAL, dimensionId };
  }

  const idUnidadPerfil = preferenciasPerfil?.[dimensionId];
  if (idUnidadPerfil !== undefined) {
    return { unidad: buscarUnidad(dimension, idUnidadPerfil), capa: Capa.PERFIL, dimensionId };
  }

  const nombrePreset = preset ?? catalogo.presetPorOmision;
  const presetActivo = buscarPreset(catalogo, nombrePreset);
  const idUnidadPreset = presetActivo.unidades[dimensionId];
  if (idUnidadPreset !== undefined) {
    return { unidad: buscarUnidad(dimension, idUnidadPreset), capa: Capa.PRESET, dimensionId };
  }

  return {
    unidad: buscarUnidad(dimension, dimension.unidadCanonica),
    capa: Capa.CANONICA,
    dimensionId,
  };
}

/**
 * Valor ya convertido -> cadena, con los decimales de la unidad — espejo de
 * `Unidad.formatea`. Los decimales son parte del dato de entrada (`UnidadInfo
 * .decimales`), nunca una cifra elegida aquí: es la diferencia entre mostrar
 * λ 0,995 y destruir esa información como λ 1,0.
 *
 * Recibe el valor YA convertido: este módulo no convierte (ver la cabecera).
 */
export function formatearValor(
  unidad: UnidadInfo,
  valor: number,
  locale: Locale = "es",
): string {
  const texto = formatearNumero(valor, unidad.decimales, { locale });
  return unidad.etiqueta ? `${texto} ${unidad.etiqueta}` : texto;
}
