/**
 * `FuenteDeDatos`: la interfaz que separa "montar la aplicación" de "de dónde
 * salen los datos" (tarea del MVP, ver el encargo en el informe de la rama).
 *
 * POR QUÉ EXISTE ESTA FRONTERA
 * ============================
 * Todo lo que hay en `src/` — renderizador (F1-23), caché de cubos (F1-24),
 * ejes (F1-25), paneles (F1-26), navegación (F1-28), escalas (F1-27), cursor
 * (F1-29), unidades (F1-31) y selector de canales (F1-33) — está construido y
 * probado, pero ninguna pieza sabe abrir un fichero ni hablar con un backend:
 * todas reciben ya los datos resueltos (`CubosContinuos`, `CanalInfo`,
 * `CatalogoUnidades`...). Esta interfaz es el único sitio del frontend que
 * sabe que "abrir un log" es una operación con nombre, y es lo que permite que
 * `app/aplicacion.ts` no necesite saber si esos datos vinieron de memoria o de
 * `dlv-api`.
 *
 * Hay DOS implementaciones:
 *
 * - `FuenteSintetica` (`fuente-sintetica.ts`): genera datos en memoria, sin
 *   backend. Es la que usa `main.ts` hoy y con la que se probó esta tarea.
 * - `FuenteApi` (`fuente-api.ts`): esbozo deliberadamente incompleto. Otro
 *   agente está ampliando `dlv-api` con la sesión de log abierto y el
 *   endpoint de cubos AHORA MISMO, y su forma exacta (¿un `logId` de sesión?
 *   ¿Arrow IPC de un nivel de pirámide completo, o por rango?) no existe
 *   todavía. Adivinar ese contrato aquí sería peor que no tenerlo: alguien
 *   tendría que descubrir más tarde qué parte es real y cuál es una
 *   suposición. Por eso cada método de `FuenteApi` lanza explícitamente en vez
 *   de fingir que habla con algo que no está.
 *
 * QUÉ NO HACE ESTA INTERFAZ
 * =========================
 * No convierte unidades (eso es cosa de quien pinta los cubos, ver la
 * cabecera de `app/conversion-demo.ts`) y no decide qué nivel de pirámide
 * pedir (eso es `render/escala.ts#elegirNivel`, que ya existe y que
 * `app/aplicacion.ts` reutiliza con `nivelesDe`). Esta interfaz solo abre,
 * lista canales, entrega niveles disponibles y sirve cubos para un rango y un
 * nivel — las cuatro operaciones que dice el encargo de la tarea, más
 * `sugerirPerfil` (F5-11, ver su propia cabecera más abajo), que se añadió
 * después y por eso es la única OPCIONAL de las cinco.
 */

import type { CubosContinuos } from "../render/tipos.ts";
import type { SugerenciaDePerfil } from "../onboarding/tipos.ts";
import type { CatalogoUnidades } from "../unidades/tipos.ts";
import type { Rango } from "./cache-cubos.ts";

/** Traducción directa de `IndiceCanal.vacio`/`.constante` (F1-07, `dlv_core.almacen`). */
export interface ClasificacionCanalFuente {
  readonly vacio: boolean;
  readonly constante: boolean;
}

/**
 * Un canal tal como lo entrega la fuente: identidad + lo mínimo para que
 * `app/aplicacion.ts` pueda construir el `CanalInfo` que pide CADA módulo de
 * consumo (`canales/tipos.ts`, `unidades/tipos.ts` y `paneles/tipos.ts` tienen
 * cada uno su propio `CanalInfo`/`CanalEnPanel`, con campos distintos — ver el
 * informe de la tarea, es una de las costuras que no se han limado).
 */
export interface CanalDeFuente {
  readonly idNativo: string;
  readonly nombre: string;
  readonly rol: string | null;
  /**
   * Cómo se decidió `rol`: `"EXACTA"`, `"INDEXADA"` o `"DIFUSA"`
   * (`dlv_core.roles.Confianza`), y `null` cuando no hay rol.
   *
   * Va separado de `rol` porque docs/07 §7.15 lo exige: una coincidencia
   * `DIFUSA` es un parecido de cadenas por encima de un umbral, no un hecho, y
   * no puede activar por sí sola nada que dependa del significado del canal.
   * Opcional para que las fuentes que no lo sepan no tengan que mentir.
   */
  readonly confianzaRol?: string | null;
  /**
   * Id de dimensión del catálogo de unidades (`"unknown"` si no se pudo
   * asignar ninguna, igual que `dlv_core.unidades` — nunca `null`: "sin
   * confirmar" es una dimensión más, con su propia entrada en el catálogo,
   * no la ausencia de dimensión).
   */
  readonly dimensionId: string;
  readonly clasificacion: ClasificacionCanalFuente;
  /**
   * Conversión afín de la muestra CRUDA del canal a la unidad canónica de su
   * dimensión (`ChannelSeries.to_canon`, ADR-003): `canonica = a·crudo + b`.
   *
   * Es propia de CADA CANAL y viene del descriptor del formato, no del catálogo
   * de unidades: la temperatura de refrigerante de un Haltech llega como el
   * entero `3748` con `a = 0,1`, y son 374,8 K. Sin esto, los cubos —que la
   * pirámide construye sobre la muestra cruda— se tratarían como si ya
   * estuvieran en canónica, y la temperatura saldría multiplicada por diez con
   * su unidad correcta al lado. Ver `unidades/conversion.ts#convertirDesdeCrudo`.
   */
  readonly aCanonica: { readonly a: number; readonly b: number };
}

/** Un nivel de pirámide disponible para un canal, tal y como lo pide `elegirNivel`. */
export interface ResumenNivelFuente {
  readonly factor: number;
  readonly nCubos: number;
}

/** Lo que devuelve `abrirLog`: metadatos, nunca series (ADR-007). */
export interface LogAbierto {
  readonly logId: string;
  readonly nombre: string;
  /** Instante absoluto (segundos) del primer dato del log. */
  readonly tInicio: number;
  /** Instante absoluto (segundos) del último dato del log. */
  readonly tFin: number;
  readonly canales: readonly CanalDeFuente[];
  readonly avisos: readonly string[];
}

/**
 * Contrato único de acceso a datos. `app/aplicacion.ts` solo conoce esto.
 */
export interface FuenteDeDatos {
  /** Nombre corto para diagnóstico en la interfaz ("sintética", "dlv-api"). */
  readonly nombre: string;

  /**
   * Abre un log. `referencia` es deliberadamente opaca (una ruta para
   * `FuenteApi`, un nombre de escenario para `FuenteSintetica`): quien
   * implementa decide qué significa.
   */
  abrirLog(referencia: string): Promise<LogAbierto>;

  /** Libera lo que la fuente tenga reservado para `logId`. Nunca lanza. */
  cerrarLog(logId: string): void;

  /** El catálogo de unidades. Independiente del log (F1-13: es un fichero de datos global). */
  catalogoUnidades(): Promise<CatalogoUnidades>;

  /**
   * Los niveles de pirámide disponibles para un canal, con su `factor` y su
   * `nCubos` TOTAL (todo el log, no la vista) — la forma exacta que pide
   * `render/escala.ts#elegirNivel`.
   */
  nivelesDe(logId: string, canalId: string): Promise<readonly ResumenNivelFuente[]>;

  /**
   * Cubos de `canalId` que cubren (al menos) `rango`, al nivel `factor`.
   * Quien llama ya ha aplicado el margen de `CacheDeCubos#consultar`: esta
   * función no decide cuánto pedir de más, solo sirve lo que se le pide.
   */
  pedirCubos(
    logId: string,
    canalId: string,
    rango: Rango,
    factor: number,
  ): Promise<CubosContinuos>;

  /**
   * La sugerencia de perfil para `log`, según `dlv_core.sugerencia_perfil`
   * (F3-04): el perfil que mejor encaja, con su cobertura de roles, o `null`
   * si ninguno llega al mínimo (`mejor_sugerencia` puede devolver `None`).
   *
   * OPCIONAL A PROPÓSITO -- Y NO ES LO MISMO QUE DEVOLVER `null`
   * ================================================================
   * `dlv-api` no expone hoy ningún endpoint que combine el catálogo de
   * `data/perfiles/*.toml` con los roles resueltos de un log concreto
   * (comprobado sobre `dlv_api/main.py` para F5-11, el mismo criterio que ya
   * usa la cabecera de este fichero para `FuenteApi`: "si hace falta un
   * endpoint que no existe, dilo en vez de inventarlo"). Si este método
   * fuera obligatorio, `FuenteSintetica` -- que no tiene ningún perfil que
   * ofrecer, solo canales sintéticos -- y `FuenteApi` -- que no tiene con
   * quién hablar todavía -- tendrían que fingir un cálculo que no existe
   * detrás. Al ser opcional, `app/aplicacion.ts` distingue TRES situaciones,
   * no dos:
   *
   *   - método ausente (`undefined`): esta fuente no sabe sugerir nada -- no
   *     se muestra ningún aviso nuevo. Es el caso de HOY, con las dos
   *     fuentes existentes: F5-11 no cambia nada de lo que se ve en pantalla
   *     hasta que alguna fuente implemente esto de verdad.
   *   - método presente que resuelve a `null`: SÍ se calculó, y ningún
   *     perfil encajó -- se avisa de eso explícitamente en vez de callarlo
   *     (E9.6, decisión 1 del informe de F5-11).
   *   - método presente que resuelve a una `SugerenciaDePerfil`: se propone.
   *
   * Quien conecte `dlv-api` con F3-04 solo tiene que implementar esto en
   * `FuenteApi`; `app/aplicacion.ts` ya sabe qué hacer con cualquiera de los
   * tres casos (`#proponerPerfilSugerido`, `#mostrarPropuestaPerfil`).
   */
  sugerirPerfil?(log: LogAbierto): Promise<SugerenciaDePerfil | null>;
}
