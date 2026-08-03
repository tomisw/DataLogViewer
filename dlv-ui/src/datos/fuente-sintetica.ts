/**
 * `FuenteSintetica`: implementación de `FuenteDeDatos` que genera datos en
 * memoria, sin backend (tarea del MVP).
 *
 * PARA QUÉ ES Y PARA QUÉ NO
 * ==========================
 * Es con lo que se desarrolla y se prueba la aplicación mientras `dlv-api` no
 * tiene todavía sesión de log abierto ni endpoint de cubos (ver la cabecera
 * de `fuente.ts`). No pretende imitar el formato Haltech ni el AutoLog real
 * byte a byte — eso ya lo hace `dlv-core` y sus pruebas de propiedad — solo
 * generar algo con la FORMA correcta (475 canales, un puñado con nombre y
 * dimensión reconocibles y el resto sin confirmar, algunos constantes o
 * vacíos) para que el selector de canales, los ejes, la caché y el
 * renderizador tengan algo real que dibujar.
 *
 * `data/units.toml` y `data/umbrales.toml` NO se leen ni se copian aquí
 * (regla 2 de `CLAUDE.md`): el catálogo de unidades de este módulo es
 * ILUSTRATIVO, con la misma idea que `unidades/fixtures-catalogo.ts` ya usa
 * para las pruebas — id/etiqueta/decimales de mentira, nunca los valores
 * reales del propietario.
 *
 * LA CONVERSIÓN DE UNIDADES NO VIVE AQUÍ
 * =======================================
 * `pedirCubos` devuelve los cubos SIEMPRE en la unidad canónica de su
 * dimensión (K, kPa...), igual que haría `dlv-api` de verdad (ADR-007: el
 * backend entrega canónica, el frontend convierte para pintar). La tabla de
 * factores afines que usa `app/aplicacion.ts` para mostrarlos convertidos
 * vive en `app/conversion-demo.ts`, marcada como un sustituto temporal de
 * `dlv_core.unidades` — ver esa cabecera para el porqué.
 *
 * GENERACIÓN PEREZOSA
 * ====================
 * `abrirLog` solo construye METADATOS (nombre, dimensión, clasificación) para
 * los 475 canales: barato, así que abrir es instantáneo. Las muestras crudas
 * y la pirámide de un canal concreto se generan la PRIMERA vez que se pide un
 * cubo suyo (`pedirCubos`) y se quedan cacheadas en `#datosPorCanal` — igual
 * que un log de verdad no se decodifica canal a canal hasta que hace falta.
 */

import type { CubosContinuos } from "../render/tipos.ts";
import type { CatalogoUnidades } from "../unidades/tipos.ts";
import type { Rango } from "./cache-cubos.ts";
import type {
  CanalDeFuente,
  FuenteDeDatos,
  LogAbierto,
  ResumenNivelFuente,
} from "./fuente.ts";

/** Duración del log sintético: 1 hora, la misma escala que docs/02 §2.9 pide para el AutoLog. */
const DURACION_S = 3600;
/** 10 Hz: suave para el ojo y ligero en memoria (36 000 muestras/canal generado). */
const FRECUENCIA_HZ = 10;
const N_MUESTRAS = DURACION_S * FRECUENCIA_HZ;
const DT = 1 / FRECUENCIA_HZ;
/** Factores de decimación de la pirámide sintética: ×4 por nivel, cinco niveles. */
const FACTORES_PIRAMIDE = [1, 4, 16, 64, 256] as const;
/** Total de canales del AutoLog sintético (docs/02 §2.9: "1 hora, 475 canales"). */
const N_CANALES = 475;

/** Generador determinista (mismo `referencia` -> mismos datos, útil para depurar). */
function crearPrng(semilla: number): () => number {
  let estado = semilla >>> 0;
  return (): number => {
    estado = (estado + 0x6d2b79f5) >>> 0;
    let t = estado;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function semillaDeTexto(texto: string): number {
  let h = 2166136261;
  for (let i = 0; i < texto.length; i += 1) {
    h = Math.imul(h ^ texto.charCodeAt(i), 16777619);
  }
  return h >>> 0;
}

/** Descriptor de cómo generar la forma de onda de un canal "protagonista". */
interface PlantillaCanal {
  readonly nombre: string;
  readonly rol: string | null;
  readonly dimensionId: string;
  /** Valor base (unidad canónica) alrededor del que oscila. */
  readonly base: number;
  /** Amplitud de la oscilación principal (unidad canónica). */
  readonly amplitud: number;
  /** Periodo de la oscilación principal, en segundos. */
  readonly periodoS: number;
  /** Ruido añadido, como fracción de la amplitud. */
  readonly ruido: number;
}

const PLANTILLAS: readonly PlantillaCanal[] = [
  { nombre: "Engine Speed", rol: "rpm", dimensionId: "rpm", base: 3200, amplitud: 2400, periodoS: 47, ruido: 0.03 },
  { nombre: "Coolant Temperature", rol: "coolant_temp", dimensionId: "temperature", base: 363, amplitud: 8, periodoS: 900, ruido: 0.01 },
  { nombre: "Intake Air Temperature", rol: "iat", dimensionId: "temperature", base: 308, amplitud: 6, periodoS: 300, ruido: 0.02 },
  { nombre: "Manifold Pressure", rol: "map", dimensionId: "pressure", base: 95, amplitud: 90, periodoS: 41, ruido: 0.05 },
  { nombre: "Barometric Pressure", rol: "baro", dimensionId: "pressure", base: 101, amplitud: 1, periodoS: 1800, ruido: 0.005 },
  { nombre: "Fuel Pressure", rol: "fuel_pressure", dimensionId: "pressure", base: 380, amplitud: 15, periodoS: 53, ruido: 0.02 },
  { nombre: "Oil Pressure", rol: "oil_pressure", dimensionId: "pressure", base: 320, amplitud: 40, periodoS: 47, ruido: 0.03 },
  { nombre: "Throttle Position", rol: "tps", dimensionId: "percentage", base: 45, amplitud: 45, periodoS: 23, ruido: 0.04 },
  { nombre: "Lambda", rol: "lambda", dimensionId: "mixture_ratio", base: 0.95, amplitud: 0.08, periodoS: 37, ruido: 0.02 },
  { nombre: "Battery Voltage", rol: "battery_voltage", dimensionId: "voltage", base: 13.8, amplitud: 0.4, periodoS: 600, ruido: 0.01 },
  { nombre: "Vehicle Speed", rol: "vehicle_speed", dimensionId: "speed", base: 60, amplitud: 55, periodoS: 71, ruido: 0.02 },
  { nombre: "Ignition Advance", rol: null, dimensionId: "angle", base: 18, amplitud: 12, periodoS: 43, ruido: 0.05 },
  { nombre: "Knock Level", rol: "knock_level", dimensionId: "unknown", base: 2, amplitud: 6, periodoS: 13, ruido: 0.3 },
  { nombre: "Injector Duty Cycle", rol: null, dimensionId: "percentage", base: 30, amplitud: 25, periodoS: 29, ruido: 0.03 },
];

/** Canales EGT 1..8: mismo patrón, distinta fase, para llenar huecos con algo con sentido. */
function plantillasEgt(): PlantillaCanal[] {
  return Array.from({ length: 8 }, (_v, i) => ({
    nombre: `Exhaust Gas Temperature ${i + 1}`,
    rol: null,
    dimensionId: "temperature",
    base: 900 - i * 8,
    amplitud: 60,
    periodoS: 39 + i * 3,
    ruido: 0.02,
  }));
}

interface DatosCanal {
  readonly niveles: ReadonlyMap<number, CubosContinuos>;
}

/**
 * Construye la serie base (36 000 muestras) de un canal a partir de su
 * plantilla y una fase aleatoria propia, y luego decima en cascada para
 * montar los cinco niveles de la pirámide.
 *
 * Vectorizado con `Float32Array` y un único `for` por nivel (sobre cubos, no
 * sobre "una vez por combinación de canal y muestra"): no es `dlv-core`, así
 * que ADR-009 no le aplica en sentido estricto, pero la misma disciplina
 * (nada de trabajo por muestra que se pueda evitar) es la que mantiene
 * `abrirLog` instantáneo con 475 canales en cartera.
 */
function generarCanal(plantilla: PlantillaCanal, rng: () => number): DatosCanal {
  const base = new Float32Array(N_MUESTRAS);
  const fase = rng() * Math.PI * 2;
  const omega = (Math.PI * 2) / Math.max(1, plantilla.periodoS);
  for (let i = 0; i < N_MUESTRAS; i += 1) {
    const t = i * DT;
    const oscilacion = Math.sin(omega * t + fase) * plantilla.amplitud;
    const ruido = (rng() - 0.5) * 2 * plantilla.amplitud * plantilla.ruido;
    base[i] = plantilla.base + oscilacion + ruido;
  }
  return { niveles: construirPiramide(base) };
}

/** Canal "de relleno" sin confirmar: constante, vacío, o ruido plano de baja amplitud. */
function generarCanalRelleno(indice: number, rng: () => number): DatosCanal {
  const base = new Float32Array(N_MUESTRAS);
  const variante = indice % 5;
  if (variante === 0) {
    // Vacío: nada de datos (todo NaN), igual que "el canal no se activó en este log".
    base.fill(NaN);
  } else if (variante === 1) {
    // Constante: un valor fijo, con la variación de indice para que no todos coincidan.
    base.fill((indice % 97) - 48);
  } else {
    const valorBase = ((indice * 31) % 200) - 100;
    const amplitud = 1 + (indice % 7);
    for (let i = 0; i < N_MUESTRAS; i += 1) {
      base[i] = valorBase + (rng() - 0.5) * 2 * amplitud;
    }
  }
  return { niveles: construirPiramide(base) };
}

/**
 * Decima `base` en cascada según `FACTORES_PIRAMIDE`. Cada nivel agrupa
 * `factor` muestras consecutivas del nivel BASE (no del nivel anterior): más
 * simple de revisar que decimar en cadena, y a esta escala (36 000 muestras)
 * el coste es irrelevante.
 */
function construirPiramide(base: Float32Array): Map<number, CubosContinuos> {
  const niveles = new Map<number, CubosContinuos>();
  for (const factor of FACTORES_PIRAMIDE) {
    const nCubos = Math.ceil(N_MUESTRAS / factor);
    const t = new Float32Array(nCubos);
    const minimo = new Float32Array(nCubos);
    const maximo = new Float32Array(nCubos);
    const primero = new Float32Array(nCubos);
    const ultimo = new Float32Array(nCubos);
    for (let c = 0; c < nCubos; c += 1) {
      const inicio = c * factor;
      const fin = Math.min(inicio + factor, N_MUESTRAS);
      t[c] = inicio * DT;
      let min = Number.POSITIVE_INFINITY;
      let max = Number.NEGATIVE_INFINITY;
      for (let i = inicio; i < fin; i += 1) {
        const v = base[i]!;
        if (Number.isNaN(v)) continue;
        if (v < min) min = v;
        if (v > max) max = v;
      }
      if (min === Number.POSITIVE_INFINITY) {
        // Todo el grupo es NaN (canal vacío): se propaga como NaN, no como 0.
        minimo[c] = NaN;
        maximo[c] = NaN;
        primero[c] = NaN;
        ultimo[c] = NaN;
      } else {
        minimo[c] = min;
        maximo[c] = max;
        primero[c] = base[inicio]!;
        ultimo[c] = base[fin - 1]!;
      }
    }
    niveles.set(factor, { t, tOrigen: 0, minimo, maximo, primero, ultimo, factor });
  }
  return niveles;
}

/** Recorta un nivel de pirámide ya generado al tramo que cubre `rango` (con margen ya aplicado por quien llama). */
function recortar(nivel: CubosContinuos, tInicioLog: number, rango: Rango): CubosContinuos {
  const relInicio = rango.t0 - tInicioLog;
  const relFin = rango.t1 - tInicioLog;
  let desde = 0;
  while (desde < nivel.t.length && nivel.t[desde]! < relInicio) desde += 1;
  if (desde > 0) desde -= 1; // un cubo de margen a la izquierda: cosido con el vecino
  let hasta = desde;
  while (hasta < nivel.t.length && nivel.t[hasta]! <= relFin) hasta += 1;
  hasta = Math.min(hasta + 1, nivel.t.length); // y uno a la derecha

  return {
    t: nivel.t.slice(desde, hasta),
    tOrigen: tInicioLog,
    minimo: nivel.minimo.slice(desde, hasta),
    maximo: nivel.maximo.slice(desde, hasta),
    primero: nivel.primero.slice(desde, hasta),
    ultimo: nivel.ultimo.slice(desde, hasta),
    factor: nivel.factor,
  };
}

/** Catálogo ilustrativo (ver la cabecera del módulo: no son los valores de `data/units.toml`). */
function catalogoIlustrativo(): CatalogoUnidades {
  return {
    dimensiones: [
      {
        id: "temperature",
        etiqueta: "Temperatura",
        unidadCanonica: "K",
        convertible: true,
        unidades: [
          { id: "K", etiqueta: "K", decimales: 1 },
          { id: "degC", etiqueta: "°C", decimales: 1 },
          { id: "degF", etiqueta: "°F", decimales: 1 },
        ],
      },
      {
        id: "pressure",
        etiqueta: "Presión",
        unidadCanonica: "kPa",
        convertible: true,
        unidades: [
          { id: "kPa", etiqueta: "kPa", decimales: 0 },
          { id: "bar", etiqueta: "bar", decimales: 2 },
          { id: "psi", etiqueta: "psi", decimales: 1 },
        ],
      },
      {
        id: "percentage",
        etiqueta: "Porcentaje",
        unidadCanonica: "percent",
        convertible: false,
        unidades: [{ id: "percent", etiqueta: "%", decimales: 1 }],
      },
      {
        id: "mixture_ratio",
        etiqueta: "Mezcla",
        unidadCanonica: "lambda",
        convertible: false,
        unidades: [{ id: "lambda", etiqueta: "λ", decimales: 3 }],
      },
      {
        id: "rpm",
        etiqueta: "Régimen de giro",
        unidadCanonica: "rpm",
        convertible: false,
        unidades: [{ id: "rpm", etiqueta: "rpm", decimales: 0 }],
      },
      {
        id: "voltage",
        etiqueta: "Tensión",
        unidadCanonica: "V",
        convertible: false,
        unidades: [{ id: "V", etiqueta: "V", decimales: 2 }],
      },
      {
        id: "speed",
        etiqueta: "Velocidad",
        unidadCanonica: "km/h",
        convertible: true,
        unidades: [
          { id: "km/h", etiqueta: "km/h", decimales: 0 },
          { id: "mph", etiqueta: "mph", decimales: 0 },
        ],
      },
      {
        id: "angle",
        etiqueta: "Ángulo",
        unidadCanonica: "deg",
        convertible: false,
        unidades: [{ id: "deg", etiqueta: "°", decimales: 1 }],
      },
      {
        id: "unknown",
        etiqueta: "Sin confirmar",
        unidadCanonica: "raw",
        convertible: false,
        mostrarEnCrudo: true,
        unidades: [{ id: "raw", etiqueta: "(crudo)", decimales: 1 }],
      },
    ],
    presets: [
      {
        id: "metrico",
        etiqueta: "Métrico",
        unidades: { temperature: "degC", pressure: "bar", speed: "km/h" },
      },
      {
        id: "imperial",
        etiqueta: "Imperial",
        unidades: { temperature: "degF", pressure: "psi", speed: "mph" },
      },
      {
        id: "si",
        etiqueta: "SI puro",
        unidades: { temperature: "K", pressure: "kPa", speed: "km/h" },
      },
    ],
    presetPorOmision: "metrico",
  };
}

export class FuenteSintetica implements FuenteDeDatos {
  readonly nombre = "sintética";

  readonly #canalesPorLog = new Map<string, readonly CanalDeFuente[]>();
  readonly #datosPorCanal = new Map<string, DatosCanal>();
  readonly #rngPorLog = new Map<string, () => number>();

  // eslint-disable-next-line @typescript-eslint/require-await
  async abrirLog(referencia: string): Promise<LogAbierto> {
    const logId = referencia || "autolog-sintetico";
    const rng = crearPrng(semillaDeTexto(logId));
    this.#rngPorLog.set(logId, rng);

    const canales: CanalDeFuente[] = [];
    for (const plantilla of [...PLANTILLAS, ...plantillasEgt()]) {
      canales.push({
        idNativo: plantilla.nombre,
        nombre: plantilla.nombre,
        rol: plantilla.rol,
        dimensionId: plantilla.dimensionId,
        clasificacion: { vacio: false, constante: false },
      });
    }
    for (let i = canales.length; i < N_CANALES; i += 1) {
      const variante = i % 5;
      canales.push({
        idNativo: `Aux Input ${i}`,
        nombre: `Aux Input ${i}`,
        rol: null,
        dimensionId: "unknown",
        clasificacion: { vacio: variante === 0, constante: variante === 1 },
      });
    }

    this.#canalesPorLog.set(logId, canales);

    return {
      logId,
      nombre: logId,
      tInicio: 0,
      tFin: DURACION_S,
      canales,
      avisos: [
        `Datos sintéticos (${this.nombre}): ${canales.length} canales generados en memoria, ` +
          "sin relación con ningún log real del propietario.",
      ],
    };
  }

  cerrarLog(logId: string): void {
    this.#canalesPorLog.delete(logId);
    this.#rngPorLog.delete(logId);
    // Los datos por canal se comparten por nombre de plantilla entre "logs"
    // sintéticos (mismo generador determinista): no hace falta tirarlos.
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async catalogoUnidades(): Promise<CatalogoUnidades> {
    return catalogoIlustrativo();
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async nivelesDe(logId: string, canalId: string): Promise<readonly ResumenNivelFuente[]> {
    const datos = this.#datosDe(logId, canalId);
    return FACTORES_PIRAMIDE.map((factor) => ({
      factor,
      nCubos: datos.niveles.get(factor)!.t.length,
    }));
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async pedirCubos(
    logId: string,
    canalId: string,
    rango: Rango,
    factor: number,
  ): Promise<CubosContinuos> {
    const datos = this.#datosDe(logId, canalId);
    const nivel = datos.niveles.get(factor);
    if (nivel === undefined) {
      throw new Error(
        `FuenteSintetica: el canal «${canalId}» no tiene un nivel de pirámide con factor ${factor}`,
      );
    }
    return recortar(nivel, 0, rango);
  }

  #datosDe(logId: string, canalId: string): DatosCanal {
    const clave = `${logId}::${canalId}`;
    let datos = this.#datosPorCanal.get(clave);
    if (datos !== undefined) return datos;

    const canales = this.#canalesPorLog.get(logId);
    if (canales === undefined) {
      throw new Error(`FuenteSintetica: no hay ningún log abierto con id «${logId}»`);
    }
    const indice = canales.findIndex((c) => c.idNativo === canalId);
    if (indice === -1) {
      throw new Error(`FuenteSintetica: el log «${logId}» no tiene el canal «${canalId}»`);
    }
    const rng = this.#rngPorLog.get(logId) ?? crearPrng(semillaDeTexto(logId));

    const todasLasPlantillas = [...PLANTILLAS, ...plantillasEgt()];
    const plantilla = todasLasPlantillas[indice];
    datos = plantilla !== undefined ? generarCanal(plantilla, rng) : generarCanalRelleno(indice, rng);
    this.#datosPorCanal.set(clave, datos);
    return datos;
  }
}
