/**
 * `FuenteApi`: esbozo de `FuenteDeDatos` sobre `dlv-api`. **NO TERMINADA.**
 *
 * POR QUÉ ESTÁ A MEDIAS, A PROPÓSITO
 * ===================================
 * Otro agente está ampliando `dlv-api` ahora mismo con la sesión de log
 * abierto y el endpoint de cubos por rango/nivel. Hoy (ver
 * `dlv-api/src/dlv_api/main.py`) el servidor solo tiene tres rutas:
 *
 * - `GET /salud` — sin token, comprobación de que el servidor escucha.
 * - `POST /comandos/abrir-cabecera` — parsea la CABECERA de un fichero y
 *   devuelve `{formato, version, n_canales, canales: [{id, nombre, dimension,
 *   confianza}], avisos}`. Sin rango de tiempo del log, sin rol semántico,
 *   sin `IndiceCanal.vacio`/`.constante` (eso es F1-07 y no se expone
 *   todavía), y **sin sesión**: cada llamada reabre el fichero desde cero.
 * - `POST /comandos/serie` — `{ruta, canal_id}` -> la serie COMPLETA
 *   `(t, v)` de un canal en Arrow IPC. No hay pirámide (niveles de
 *   decimación) en esta respuesta, ni forma de pedir solo un rango: es la
 *   serie entera, cada vez, sin caché de log abierto entre peticiones.
 *
 * Ninguna de las dos rutas de datos encaja con lo que `FuenteDeDatos` pide
 * (`nivelesDe`/`pedirCubos` por rango y nivel de pirámide, con un `logId` de
 * sesión que sobrevive entre llamadas). Rehacer aquí una implementación
 * "aproximada" sobre `/comandos/serie` -- pidiendo la serie entera y
 * decimándola en el propio frontend -- funcionaría para la demo pero
 * mentiría sobre la arquitectura: ADR-007 existe precisamente para que la
 * decimación y el recorte por rango pasen en el backend, no en el navegador,
 * y fingir que ya está resuelto aquí es el tipo de "lo doy por bueno sin
 * comprobar" que este proyecto pide evitar (`docs/09` §9.11).
 *
 * Por eso cada método de la interfaz lanza `SinImplementar` con una nota de
 * qué falta. Cuando el endpoint de sesión + cubos exista, esta clase es
 * donde se cablea -- y lo hace el propietario, no un modelo adivinando el
 * contrato por adelantado (ver el encargo de la tarea).
 *
 * LO QUE SÍ ESTÁ CERRADO Y NO HACE FALTA REDESCUBRIR
 * =====================================================
 * El transporte HTTP con token de sesión (ADR-007: `Authorization: Bearer
 * <token>`) SÍ es un contrato ya estable (`verificar_token` en
 * `dlv-api/main.py`): cualquier método que se cablee aquí debe mandar esa
 * cabecera contra `${urlBase}${ruta}`. No se deja una función auxiliar ya
 * escrita para eso (`#pedirJson` sin usar fallaría `noUnusedLocals`, que es
 * una de las seis comprobaciones de `tools/verificar.py`) — se deja dicho
 * aquí para que quien cablee el primer método real no tenga que releer
 * `dlv-api/main.py` para encontrar el nombre de la cabecera.
 */

import type { CubosContinuos } from "../render/tipos.ts";
import type { CatalogoUnidades } from "../unidades/tipos.ts";
import type { Rango } from "./cache-cubos.ts";
import type {
  FuenteDeDatos,
  LogAbierto,
  ResumenNivelFuente,
} from "./fuente.ts";

/** Lanzada por cada método de `FuenteApi` mientras no exista su endpoint real. */
export class SinImplementar extends Error {
  constructor(operacion: string, motivo: string) {
    super(`FuenteApi.${operacion}: no implementado todavía — ${motivo}`);
    this.name = "SinImplementar";
  }
}

export interface OpcionesFuenteApi {
  /** Ej. `http://127.0.0.1:8000` (ADR-007: puerto efímero, sin `/` final). */
  readonly urlBase: string;
  /** Token de sesión (`Authorization: Bearer <token>`), generado por `dlv-api` al arrancar. */
  readonly tokenSesion: string;
}

export class FuenteApi implements FuenteDeDatos {
  readonly nombre = "dlv-api";

  readonly #urlBase: string;
  readonly #tokenSesion: string;

  constructor(opciones: OpcionesFuenteApi) {
    if (opciones.urlBase.length === 0) {
      throw new Error("FuenteApi: `urlBase` no puede estar vacía");
    }
    if (opciones.tokenSesion.length === 0) {
      throw new Error("FuenteApi: `tokenSesion` no puede estar vacío (ADR-007 lo exige siempre)");
    }
    this.#urlBase = opciones.urlBase.replace(/\/$/, "");
    this.#tokenSesion = opciones.tokenSesion;
  }

  /** Para depurar desde la consola qué instancia se cableó. Nunca imprime el token entero. */
  get diagnostico(): string {
    return `${this.#urlBase} (token …${this.#tokenSesion.slice(-4)})`;
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async abrirLog(_referencia: string): Promise<LogAbierto> {
    // `/comandos/abrir-cabecera` existe y podría darnos `canales`, pero no da
    // `tInicio`/`tFin` ni la clasificación vacío/constante (F1-07) que pide
    // `LogAbierto`, y no abre una SESIÓN con `logId` que `pedirCubos` pueda
    // reutilizar sin releer el fichero. Completar solo la mitad del contrato
    // sería peor que no completar nada: alguien tendría que descubrir más
    // tarde qué campos son reales y cuáles se rellenaron a mano.
    throw new SinImplementar(
      "abrirLog",
      "falta el endpoint de sesión de log (logId, rango temporal, clasificación de canal); " +
        "`/comandos/abrir-cabecera` solo da nombre/dimensión/confianza por canal.",
    );
  }

  cerrarLog(_logId: string): void {
    // No-op deliberado: sin sesión de servidor todavía, no hay nada que cerrar.
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async catalogoUnidades(): Promise<CatalogoUnidades> {
    throw new SinImplementar(
      "catalogoUnidades",
      "`dlv-api` carga `data/units.toml` internamente (`_catalogo_unidades`) pero no lo " +
        "expone todavía en ninguna ruta HTTP.",
    );
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async nivelesDe(_logId: string, _canalId: string): Promise<readonly ResumenNivelFuente[]> {
    throw new SinImplementar(
      "nivelesDe",
      "no hay endpoint que describa la pirámide de un canal (niveles y cubos totales); " +
        "`/comandos/serie` devuelve la serie completa sin decimar.",
    );
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async pedirCubos(
    _logId: string,
    _canalId: string,
    _rango: Rango,
    _factor: number,
  ): Promise<CubosContinuos> {
    throw new SinImplementar(
      "pedirCubos",
      "no hay endpoint de cubos por rango y nivel (ADR-007: Arrow IPC/TypedArray, nunca JSON); " +
        "esperando el trabajo en curso sobre `dlv-api`.",
    );
  }
}
