/**
 * Mapa de calor de densidad de knock (F4-07, `docs/02` §E7.4): la pieza
 * ESPECÍFICA que convierte una `MallaResuelta` de densidad de knock en una
 * `ConfiguracionMapaDeCalor` genérica (`src/malla/`). Mismo patrón que
 * `lambda/mapa-error.ts` (F4-04) y `encendido/mapa-avance.ts` (F4-07) — este
 * fichero es el tercero de la familia, léelos primero si el reparto entre
 * `malla/` (el motor) y esto (el dominio) no resulta familiar.
 *
 * LA TRAMPA: `knock_count` ES UN CONTADOR ACUMULATIVO, NO SE AGREGA EN CRUDO
 * ==============================================================================
 * `data/roles.toml` marca `knock_count` con `monotono = "no_decreciente"`: el
 * valor del canal en la muestra 50 000 no es "cuánto knock hay ahí", es
 * "cuántos eventos de knock ha habido en TODO el log hasta ahí". Agregarlo
 * en crudo en la malla —que es exactamente lo que
 * `dlv_core.malla.construir_malla` haría si se le pasara `knock_count` como
 * `valor` sin más, porque el módulo no conoce el concepto `monotono` de
 * `roles.toml`, solo ve un array de números— daría una `media` por celda que
 * es aproximadamente "en qué punto del log cayeron las muestras de esta
 * celda", no "cuánto knock hubo": una celda visitada solo al final de una
 * tirada larga saldría con una media enorme aunque no tuviera ni un evento
 * de knock, y una celda visitada solo al principio saldría con una media
 * pequeña aunque estuviera llena de eventos. Es un artefacto del ORDEN
 * temporal, no una medida de knock.
 *
 * Lo que hace falta es el INCREMENTO: `knock_count[i] - knock_count[i-1]`
 * (0 la mayoría de las muestras, un entero pequeño cuando hay un evento). Esa
 * es exactamente la razón de que `roles.toml` marque el rol como `monotono`
 * en primer lugar — el comentario de su cabecera lo dice explícito: "habilita
 * el canal delta automático" (`docs/04` §4.2, perfil P2) — y ESE delta, no el
 * contador en bruto, es el canal `valor` que este módulo espera recibir ya
 * calculado en `MallaResuelta.celdas`. Este componente NO calcula el delta:
 * "tu componente RECIBE los datos resueltos" (dlv-api no expone la malla
 * todavía), así que la resta muestra-a-muestra es responsabilidad de quien
 * construya `valor` antes de llamar a `construir_malla` — este fichero solo
 * documenta el contrato y se niega a fingir que un contador acumulativo sin
 * diferenciar significa "densidad".
 *
 * CON EL DELTA YA AGREGADO: LA MEDIA DE LA CELDA ES LA DENSIDAD, Y ES «PUNTO»
 * ================================================================================
 * Una vez que `valor` es el incremento por muestra (eventos de knock en esa
 * muestra, siempre >= 0), la `media` que `construir_malla` calcula por celda
 * es exactamente "eventos de knock por muestra en esta zona RPM×MAP" — una
 * LECTURA de tasa, no una diferencia entre dos agregados (no es del tipo
 * "medida − objetivo" que hace `Clase.INTERVALO` en `mapa-error.ts`). Por eso
 * `CLASE_VALOR_DENSIDAD` es `Clase.PUNTO`, igual que en
 * `encendido/mapa-avance.ts` y por el mismo motivo — ver su cabecera para el
 * razonamiento completo sobre por qué eso también implica que no hace falta
 * un caso "deshabilitado por unidad recíproca".
 *
 * LO QUE LA MALLA *NO* DA, Y QUE ESTE MÓDULO NO FINGE TENER
 * ================================================================
 * El encargo de la tarea sugiere otra lectura posible de "densidad": cuántas
 * MUESTRAS de la celda superan un umbral de `knock_level` (dB), en vez de la
 * media de un incremento. `dlv_core.malla.construir_malla` no ofrece esa
 * estadística — agrega `cuenta`/`media`/`desviacion_tipica`/`minimo`/`maximo`
 * de UN canal continuo, no "número de muestras que cumplen una condición"
 * sobre otro. Las dos lecturas SÍ convergen en el mismo mecanismo si "cuántas
 * muestras superan el umbral" se resuelve ANTES de la malla, convirtiendo
 * `knock_level` en un canal indicador (0/1 por muestra, ya umbralado con
 * `data/umbrales.toml`) y agregando ESE como `valor`: su `media` por celda es
 * entonces la FRACCIÓN de muestras que superaron el umbral, que sigue siendo
 * `Clase.PUNTO` y sigue siendo compatible con este mismo módulo sin cambiar
 * una línea. No se ha construido ese canal indicador aquí —fijar qué umbral
 * de `knock_level` cuenta como evento es una decisión de `data/umbrales.toml`
 * con su propia precedencia canal > perfil > usuario > fichero (regla 3 de
 * `CLAUDE.md`), y cablearla en un componente de presentación sería
 * exactamente la opinión disfrazada de física que esa regla prohíbe—, así que
 * se deja constancia aquí en vez de forzar una de las dos lecturas como si
 * fuera la única posible: quien resuelva la malla (hoy las pruebas; mañana
 * `dlv-api`) decide cuál de las dos construye, y este componente sirve a las
 * dos igual porque las dos acaban siendo "una tasa por muestra, clase punto".
 *
 * SIN CONVERSIÓN DE UNIDAD: `knock_count`/`knock_level` NO SON CONVERTIBLES
 * ================================================================================
 * `data/units.toml` marca `convertible = false` para las dimensiones `count`
 * y `sound_level` — no hay selector de unidad que mostrar ni que respetar
 * (`unidades/tipos.ts#DimensionInfo.convertible`). Por eso este módulo, a
 * diferencia de `mapa-error.ts` y `mapa-avance.ts`, no recibe un
 * `UnidadInfo`: usa `IDENTIDAD` directamente, la misma que `conversion.ts`
 * define para "no convertir nada".
 *
 * LA ESCALA: SECUENCIAL Y ROJA, A PROPÓSITO DISTINTA DE LA DE AVANCE
 * ========================================================================
 * Misma forma que `encendido/mapa-avance.ts` (`malla/escala-secuencial.ts`:
 * sin cero especial, low→high) pero con otro significado: la densidad de
 * knock SÍ es un indicador de severidad —cero eventos es inequívocamente
 * mejor que muchos—, así que usa el mismo rojo que
 * `.dlv-topes-linea--critico` de `index.html` (ya reutilizado por
 * `malla/escala-divergente.ts` para "exceso"), consistente con el lenguaje de
 * color del resto de la app. El avance de encendido, en cambio, no tiene esa
 * lectura de alarma y usa el azul neutro de `--acento` — los dos mapas de
 * F4-07 pintan la MISMA malla pero con colores deliberadamente distintos para
 * que nadie los confunda de un vistazo.
 */

import type { AreaDibujo } from "../ejes/tipos.ts";
import type { Color } from "../render/tipos.ts";
import { IDENTIDAD, type Clase } from "../unidades/conversion.ts";
import { t } from "../locale/catalogo.ts";
import { escalaSecuencial, rangoSecuencialDesdeDatos, type RangoSecuencial } from "../malla/escala-secuencial.ts";
import type { ConfiguracionMapaDeCalor, MallaResuelta } from "../malla/tipos.ts";

/** Ver la cabecera del módulo: una densidad (tasa por muestra) es una LECTURA, nunca se deja que quien llama la cambie. */
const CLASE_VALOR_DENSIDAD: Clase = "punto";

/** Blanco/gris neutro (sin knock) -> mismo rojo que `.dlv-topes-linea--critico`. Ver la cabecera: deliberadamente NO el azul de avance. */
const COLOR_DENSIDAD_BAJA: Color = { r: 0.94, g: 0.94, b: 0.94, a: 1 };
const COLOR_DENSIDAD_ALTA: Color = { r: 0.87, g: 0.29, b: 0.29, a: 1 };

export interface ConfiguracionMapaDensidadKnock {
  readonly area: AreaDibujo;
  /**
   * Malla de densidad de knock, en CANÓNICA. `celdas[].media` es la tasa de
   * eventos por muestra — el canal `valor` que se agregó tiene que ser YA el
   * incremento de `knock_count` (o un indicador de `knock_level` sobre
   * umbral), nunca el contador acumulativo en bruto. Ver la cabecera del
   * módulo: este componente no lo calcula ni lo puede comprobar, solo lo
   * documenta.
   */
  readonly malla: MallaResuelta;
  readonly forma: { readonly filas: number; readonly columnas: number };
  /** Cuenta mínima para pintar una celda como confiable. Obligatorio: ver `malla/tipos.ts`. */
  readonly umbralConfianza: number;
  readonly colorSinDatos: Color;
  /** Decimales al formatear el detalle de celda. Por omisión, el de `malla/geometria.ts` (2). */
  readonly decimales?: number;
  /**
   * Rango `[densidad mínima, densidad máxima]` de la escala secuencial. Si se
   * omite, se deduce del propio dato (`rangoSecuencialDesdeDatos` sobre las
   * medias de celda) — NUNCA un rango "típico" cableado, mismo criterio que
   * `encendido/mapa-avance.ts` y que `dlv_core.malla.bordes_por_omision`.
   */
  readonly rangoDensidad?: RangoSecuencial;
}

export type ResultadoMapaDensidadKnock =
  | { readonly tipo: "activo"; readonly configuracion: ConfiguracionMapaDeCalor }
  | { readonly tipo: "deshabilitado"; readonly motivo: string };

/**
 * Construye la configuración del mapa de calor de densidad de knock, o
 * explica por qué no se puede pintar (solo ocurre sin ninguna celda con dato
 * del que deducir el rango de la escala: sin unidad que gestionar, este mapa
 * no tiene el caso de unidad recíproca de `mapa-error.ts`, mismo motivo que
 * `mapa-avance.ts`).
 */
export function resolverMapaDensidadKnock(
  config: ConfiguracionMapaDensidadKnock,
): ResultadoMapaDensidadKnock {
  const densidades = config.malla.celdas.map((c) => c.media);
  const rango = config.rangoDensidad ?? rangoSecuencialDesdeDatos(densidades);
  if (rango === null) {
    return { tipo: "deshabilitado", motivo: t("knock.mapaDensidad.sinDatosParaEscala") };
  }

  return {
    tipo: "activo",
    configuracion: {
      area: config.area,
      malla: config.malla,
      forma: config.forma,
      conversion: IDENTIDAD,
      claseValor: CLASE_VALOR_DENSIDAD,
      umbralConfianza: config.umbralConfianza,
      decimales: config.decimales,
      colorDeValor: escalaSecuencial(COLOR_DENSIDAD_BAJA, COLOR_DENSIDAD_ALTA, rango),
      colorSinDatos: config.colorSinDatos,
    },
  };
}
