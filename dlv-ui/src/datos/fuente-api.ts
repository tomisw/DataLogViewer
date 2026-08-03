/**
 * `FuenteApi`: `FuenteDeDatos` sobre `dlv-api`. **Cableada y funcional.**
 *
 * Sustituye al esbozo que lanzaba `SinImplementar` en cada método. Aquel
 * esbozo era la respuesta correcta en su momento: cuando se escribió, `dlv-api`
 * solo tenía `/comandos/abrir-cabecera` y `/comandos/serie` —serie completa,
 * sin pirámide, sin sesión y reparseando el fichero en cada petición— y
 * adivinar el contrato que faltaba habría sido inventarlo. F1-40 lo creó; esto
 * lo cablea.
 *
 * POR QUÉ EL CUERPO BINARIO ES «CRUDO» Y NO ARROW IPC
 * ===================================================
 * ADR-007 ofrece las dos formas: «Arrow IPC **o** un búfer de tipado fijo, que
 * en el frontend se lee como `TypedArray` sin parseo». Al cablear esto resultó
 * que, para `dlv-ui`, la segunda no es una alternativa estilística sino la
 * única viable: este paquete no tiene NINGUNA dependencia, y leer Arrow IPC en
 * el navegador exige o la librería `apache-arrow` —que es una dependencia
 * nueva, y no se añade sin preguntar (docs/09 §9.11)— o escribir a mano un
 * lector del formato, que es mucho código delicado para transportar cinco
 * arrays de números.
 *
 * Con `formato_binario: "crudo"` el cuerpo son las cinco columnas de `float32`
 * little-endian una detrás de otra, y cada una se lee con un
 * `new Float32Array(buffer, i * n * 4, n)`. Cero parseo, que es literalmente
 * lo que pedía el ADR. `n` viene en la cabecera `X-Cubos`.
 *
 * DOS COSAS QUE ESTA FUENTE TODAVÍA NO SABE, Y QUE NO SE INVENTAN
 * ==============================================================
 * 1. **El rol semántico de cada canal.** La asignación automática existe
 *    (`dlv_core.roles`, FG-09) pero `dlv-api` no la expone todavía, así que
 *    aquí `rol` es `null`. Un rol inventado activaría o desactivaría
 *    detectores críticos por accidente (docs/07 §7.15), así que «no lo sé» es
 *    la única respuesta honesta.
 * 2. **La clasificación `vacío`/`constante`** de `IndiceCanal` (F1-07).
 *    Tampoco se expone. Se devuelve «ni vacío ni constante», y esa elección
 *    tiene una dirección deliberada: el selector de canales (F1-33) oculta los
 *    inactivos, así que el error por este lado es **enseñar de más**, nunca
 *    esconder un canal que sí tenía datos. Al revés, un canal desaparecería
 *    sin motivo visible.
 *
 * Las dos quedan anotadas para que quien las cablee no tenga que deducir que
 * faltaban: no son olvidos, son huecos conocidos del backend.
 */

import type { CubosContinuos } from "../render/tipos.ts";
import type { CatalogoUnidades } from "../unidades/tipos.ts";
import type { Rango } from "./cache-cubos.ts";
import type { CanalDeFuente, FuenteDeDatos, LogAbierto, ResumenNivelFuente } from "./fuente.ts";

const COLUMNAS_CUBOS = 5;
const BYTES_POR_FLOTANTE = 4;

export interface OpcionesFuenteApi {
  /** `http://127.0.0.1:<puerto>`, con el puerto efímero de ADR-007. */
  readonly urlBase: string;
  /** Token de sesión que `dlv-api` generó al arrancar (ADR-007). */
  readonly tokenSesion: string;
  /** Inyectable para probar sin servidor. Por omisión, el `fetch` global. */
  readonly fetch?: typeof globalThis.fetch;
}

/** Un canal tal como lo describe `/comandos/abrir-log`. */
interface CanalDeApi {
  readonly id: number;
  readonly nombre: string;
  readonly dimension: string | null;
  readonly niveles: readonly { readonly factor: number; readonly n_cubos: number }[];
}

interface RespuestaAbrirLog {
  readonly id_sesion: string;
  readonly ruta: string;
  readonly t_inicio: number;
  readonly t_fin: number;
  readonly canales: readonly CanalDeApi[];
  readonly avisos: readonly string[];
}

export class FuenteApi implements FuenteDeDatos {
  readonly nombre = "dlv-api";
  readonly #urlBase: string;
  readonly #token: string;
  readonly #fetch: typeof globalThis.fetch;
  /**
   * Los niveles por canal se guardan al abrir en vez de volver a pedirse.
   *
   * `nivelesDe` se llama en cada cambio de zoom para decidir qué nivel pedir
   * (`elegirNivel`), y `/comandos/abrir-log` ya los devolvió todos: volver a
   * preguntarlos metería una ida y vuelta HTTP dentro del camino que §2.6
   * quiere por debajo de 120 ms.
   */
  readonly #nivelesPorLog = new Map<string, Map<string, readonly ResumenNivelFuente[]>>();

  constructor(opciones: OpcionesFuenteApi) {
    this.#urlBase = opciones.urlBase.replace(/\/$/, "");
    this.#token = opciones.tokenSesion;
    this.#fetch = opciones.fetch ?? globalThis.fetch.bind(globalThis);
  }

  async abrirLog(referencia: string): Promise<LogAbierto> {
    const datos = await this.#pedirJson<RespuestaAbrirLog>("/comandos/abrir-log", {
      ruta: referencia,
    });

    const niveles = new Map<string, readonly ResumenNivelFuente[]>();
    const canales: CanalDeFuente[] = datos.canales.map((c) => {
      const idNativo = String(c.id);
      niveles.set(
        idNativo,
        c.niveles.map((n) => ({ factor: n.factor, nCubos: n.n_cubos })),
      );
      return {
        idNativo,
        nombre: c.nombre,
        rol: null,
        // `dimension` llega `null` cuando el tipo no está en el descriptor o su
        // escala no está confirmada. `CanalDeFuente` pide un id siempre, y
        // `unknown` ES una dimensión del catálogo —la de «se muestra en crudo,
        // sin unidad»—, no la ausencia de una.
        dimensionId: c.dimension ?? "unknown",
        clasificacion: { vacio: false, constante: false },
      };
    });
    this.#nivelesPorLog.set(datos.id_sesion, niveles);

    return {
      logId: datos.id_sesion,
      nombre: datos.ruta,
      tInicio: datos.t_inicio,
      tFin: datos.t_fin,
      canales,
      avisos: [...datos.avisos],
    };
  }

  cerrarLog(logId: string): void {
    this.#nivelesPorLog.delete(logId);
    // El contrato dice «nunca lanza»: cerrar es limpieza, y una limpieza que
    // revienta al cerrar una ventana deja al usuario sin poder cerrarla. Si el
    // servidor ya no tiene la sesión, el efecto que se buscaba ya se dio.
    void this.#pedirJson("/comandos/cerrar-log", { id_sesion: logId }).catch(() => undefined);
  }

  async catalogoUnidades(): Promise<CatalogoUnidades> {
    const respuesta = await this.#fetch(`${this.#urlBase}/comandos/unidades`, {
      headers: { Authorization: `Bearer ${this.#token}` },
    });
    if (!respuesta.ok) {
      throw new Error(`dlv-api respondió ${respuesta.status} al pedir el catálogo de unidades`);
    }
    return (await respuesta.json()) as CatalogoUnidades;
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async nivelesDe(logId: string, canalId: string): Promise<readonly ResumenNivelFuente[]> {
    const delLog = this.#nivelesPorLog.get(logId);
    if (delLog === undefined) {
      throw new Error(`el log «${logId}» no está abierto en esta fuente`);
    }
    const niveles = delLog.get(canalId);
    if (niveles === undefined) {
      throw new Error(`el log «${logId}» no tiene el canal «${canalId}»`);
    }
    return niveles;
  }

  async pedirCubos(
    logId: string,
    canalId: string,
    rango: Rango,
    factor: number,
  ): Promise<CubosContinuos> {
    const respuesta = await this.#fetch(`${this.#urlBase}/comandos/cubos`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.#token}`,
      },
      body: JSON.stringify({
        id_sesion: logId,
        canal_id: Number(canalId),
        t0: rango.t0,
        t1: rango.t1,
        factor,
        formato_binario: "crudo",
      }),
    });
    if (!respuesta.ok) {
      throw new Error(
        `dlv-api respondió ${respuesta.status} al pedir cubos del canal ${canalId}: ` +
          `${await respuesta.text()}`,
      );
    }

    const n = Number(respuesta.headers.get("X-Cubos") ?? "0");
    const tOrigen = Number(respuesta.headers.get("X-T-Origen") ?? "0");
    const factorReal = Number(respuesta.headers.get("X-Factor") ?? String(factor));
    const buffer = await respuesta.arrayBuffer();

    const esperado = n * COLUMNAS_CUBOS * BYTES_POR_FLOTANTE;
    if (buffer.byteLength !== esperado) {
      // Un búfer corto se leería como `NaN` en las últimas columnas, y un NaN
      // en WebGL no da error: da un hueco en el trazo que se acaba
      // diagnosticando mirando el lienzo. Fallar aquí, con los dos tamaños
      // delante, cuesta una comparación.
      throw new Error(
        `cubos truncados: ${buffer.byteLength} bytes recibidos y ${esperado} esperados ` +
          `para ${n} cubos`,
      );
    }

    const columna = (i: number): Float32Array =>
      new Float32Array(buffer, i * n * BYTES_POR_FLOTANTE, n);

    return {
      t: columna(0),
      tOrigen,
      minimo: columna(1),
      maximo: columna(2),
      primero: columna(3),
      ultimo: columna(4),
      factor: factorReal,
    };
  }

  async #pedirJson<T>(ruta: string, cuerpo: unknown): Promise<T> {
    const respuesta = await this.#fetch(`${this.#urlBase}${ruta}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.#token}`,
      },
      body: JSON.stringify(cuerpo),
    });
    if (!respuesta.ok) {
      throw new Error(`dlv-api respondió ${respuesta.status} en ${ruta}: ${await respuesta.text()}`);
    }
    return (await respuesta.json()) as T;
  }
}
