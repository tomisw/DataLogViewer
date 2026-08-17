/**
 * Perfil de importación `.dlvimport`: huella de cabecera y reaplicación
 * parcial, en el navegador (FG-12).
 *
 * Espejo TypeScript de `dlv_core.perfil_importacion` (léelo primero: ahí está
 * la explicación completa de la huella y de la regla "lo confirmado
 * sobrevive, lo deducido se vuelve a deducir"). Este fichero existe porque la
 * reaplicación de un perfil YA CARGADO contra la propuesta que el asistente
 * tiene en memoria es exactamente el tipo de lógica que `puerto.ts` describe
 * como "no necesita red": no hay ninguna decisión aquí que dependa de volver
 * a sondear el fichero. Cargar el `.dlvimport` de disco SÍ necesita red (ADR-002:
 * ni `dlv-core` ni el navegador tocan el sistema de ficheros), y ESE endpoint
 * no existe todavía — ver la nota "QUÉ FALTA" al final de este fichero, mismo
 * criterio que `PuertoImportacionApi` en `puerto.ts`.
 *
 * MISMO ÁRBOL DE TIPOS QUE EL ASISTENTE, NO UNO PARALELO
 * =========================================================
 * `PerfilImportacion.formato` es un `PropuestaFormato` de `tipos.ts`, y
 * `PerfilImportacion.canales` son `CanalPropuesto[]` — los mismos tipos que
 * ya usa `asistente-importacion.ts`, no una copia. Es literalmente lo que su
 * docstring pide: «El callback `onCompletar` recibe la asignación completa
 * ... para que quien implemente FG-12 tenga de dónde partir sin inventar de
 * nuevo esta forma». Solo el tiempo necesita un envoltorio (`TiempoDePerfil`)
 * porque además del `PropuestaTiempo` hace falta guardar el NOMBRE de la
 * columna de tiempo (ver más abajo, "por qué por nombre").
 *
 * POR QUÉ HAY UN SHA-256 ESCRITO A MANO AQUÍ
 * =============================================
 * `dlv_core.perfil_importacion.HuellaCabecera.hash_columnas` usa
 * `hashlib.sha256`. Para que el mismo perfil compare igual tanto si la
 * reaplicación la hace `dlv-core` como si la hace este módulo, hace falta el
 * MISMO algoritmo con la MISMA entrada. `crypto.subtle.digest` del navegador
 * es asíncrono (`Promise`), y esta capa entera es deliberadamente síncrona
 * (`puerto.ts`); por eso `sha256Hex` es una implementación propia de FIPS
 * 180-4, no una dependencia nueva (regla 6 del encargo) — es código de este
 * fichero, igual de "sin dependencias" que `_volcar_toml` en el lado Python.
 * Verificada contra los vectores oficiales de "" y "abc" en
 * `perfil-importacion.test.ts`.
 *
 * POR QUÉ LA COLUMNA DE TIEMPO SE BUSCA POR NOMBRE
 * ===================================================
 * `dlv_api.importacion.sondear_canales` EXCLUYE la columna de tiempo de la
 * lista de canales («la columna de tiempo confirmada en el paso 2 no sale
 * como canal»), así que su nombre no está en `canalesActuales`. Reaplicar por
 * ÍNDICE sería el fallo silencioso más caro (una columna añadida delante
 * desplaza el índice y el eje que se dibuja es el equivocado, sin ningún
 * aviso visible), así que `TiempoDePerfil` guarda el nombre y
 * `reaplicarPerfil` recibe `nombresColumnas` — la cabecera COMPLETA del
 * fichero nuevo, columna de tiempo incluida — aparte de `canalesActuales`.
 */

import { deducido } from "./campo.ts";
import type {
  CanalPropuesto,
  Campo,
  PropuestaFormato,
  PropuestaTiempo,
  RolPropuesto,
} from "./tipos.ts";

export class ErrorDePerfilImportacion extends Error {}

// --------------------------------------------------------------------------- #
// Normalización de nombres de columna: espejo de `dlv_core.roles.normalizar`
// (minúsculas, sin acentos, sin separadores). Deliberadamente NO es
// `normalizarParaBusqueda` de `canales/difuso.ts`: aquella conserva los
// espacios a propósito para puntuar "principio de palabra"; aquí hace falta
// IGUALDAD de nombre, no relevancia de búsqueda, el mismo criterio que separa
// los dos en `dlv_core.roles` (ver su cabecera).
// --------------------------------------------------------------------------- #
const SEPARADORES = /[\s_\-./\\()[\]{}:,;+]+/g;
const MARCAS_DE_COMBINACION = /[̀-ͯ]/g;

export function normalizar(nombre: string): string {
  const sinAcentos = nombre.normalize("NFKD").replace(MARCAS_DE_COMBINACION, "");
  return sinAcentos.replace(SEPARADORES, "").toLowerCase();
}

// --------------------------------------------------------------------------- #
// SHA-256 síncrono (FIPS 180-4). Ver la cabecera del módulo.
// --------------------------------------------------------------------------- #
const K: readonly number[] = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

function rotarDerecha(valor: number, bits: number): number {
  return (valor >>> bits) | (valor << (32 - bits));
}

/** SHA-256 de una cadena UTF-8, en hexadecimal minúsculas, 64 caracteres. */
export function sha256Hex(texto: string): string {
  const bytes = new TextEncoder().encode(texto);
  const bitLength = bytes.length * 8;

  // Relleno estándar: 0x80, ceros hasta 448 mod 512 bits, longitud en 64
  // bits big-endian al final.
  const trasMarcador = bytes.length + 1;
  const resto = trasMarcador % 64;
  const ceros = resto <= 56 ? 56 - resto : 120 - resto;
  const total = trasMarcador + ceros + 8;
  const buffer = new Uint8Array(total);
  buffer.set(bytes);
  buffer[bytes.length] = 0x80;
  const vista = new DataView(buffer.buffer);
  // Ningún fichero/columna real se acerca a 2^32 bits de nombres de canal, así
  // que los 32 bits altos de la longitud son siempre 0 en la práctica; se
  // calculan igualmente para no fingir un caso que no se comprueba.
  vista.setUint32(total - 4, bitLength >>> 0, false);
  vista.setUint32(total - 8, Math.floor(bitLength / 0x100000000), false);

  let h0 = 0x6a09e667;
  let h1 = 0xbb67ae85;
  let h2 = 0x3c6ef372;
  let h3 = 0xa54ff53a;
  let h4 = 0x510e527f;
  let h5 = 0x9b05688c;
  let h6 = 0x1f83d9ab;
  let h7 = 0x5be0cd19;

  const w = new Int32Array(64);
  for (let bloque = 0; bloque < total; bloque += 64) {
    for (let i = 0; i < 16; i++) {
      w[i] = vista.getUint32(bloque + i * 4, false);
    }
    for (let i = 16; i < 64; i++) {
      const w15 = w[i - 15]!;
      const w2 = w[i - 2]!;
      const s0 = rotarDerecha(w15, 7) ^ rotarDerecha(w15, 18) ^ (w15 >>> 3);
      const s1 = rotarDerecha(w2, 17) ^ rotarDerecha(w2, 19) ^ (w2 >>> 10);
      w[i] = (w[i - 16]! + s0 + w[i - 7]! + s1) | 0;
    }

    let a = h0;
    let b = h1;
    let c = h2;
    let d = h3;
    let e = h4;
    let f = h5;
    let g = h6;
    let h = h7;
    for (let i = 0; i < 64; i++) {
      const s1 = rotarDerecha(e, 6) ^ rotarDerecha(e, 11) ^ rotarDerecha(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + ch + K[i]! + w[i]!) | 0;
      const s0 = rotarDerecha(a, 2) ^ rotarDerecha(a, 13) ^ rotarDerecha(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) | 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) | 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) | 0;
    }
    h0 = (h0 + a) | 0;
    h1 = (h1 + b) | 0;
    h2 = (h2 + c) | 0;
    h3 = (h3 + d) | 0;
    h4 = (h4 + e) | 0;
    h5 = (h5 + f) | 0;
    h6 = (h6 + g) | 0;
    h7 = (h7 + h) | 0;
  }

  return [h0, h1, h2, h3, h4, h5, h6, h7]
    .map((valor) => (valor >>> 0).toString(16).padStart(8, "0"))
    .join("");
}

// --------------------------------------------------------------------------- #
// Huella: identifica el FORMATO, no el fichero. Espejo de
// `dlv_core.perfil_importacion.HuellaCabecera`/`ResumenHuella` — ver su
// docstring para el razonamiento completo (qué mira y qué no, y por qué).
// --------------------------------------------------------------------------- #
export interface HuellaCabecera {
  readonly nombresNormalizados: readonly string[];
  readonly delimitador: string;
  readonly codificacion: string;
}

export function construirHuella(
  nombres: readonly string[],
  delimitador: string,
  codificacion: string,
): HuellaCabecera {
  return { nombresNormalizados: nombres.map(normalizar), delimitador, codificacion };
}

export function nColumnas(huella: HuellaCabecera): number {
  return huella.nombresNormalizados.length;
}

export function hashColumnas(huella: HuellaCabecera): string {
  return "sha256:" + sha256Hex(huella.nombresNormalizados.join("\x1f"));
}

/** Lo que `[fingerprint]` guarda de una `HuellaCabecera` (ver su espejo
 * Python): el resumen barato, no la lista completa de nombres. */
export interface ResumenHuella {
  readonly hashColumnas: string;
  readonly nColumnas: number;
  readonly delimitador: string;
  readonly codificacion: string;
}

export function resumenDeHuella(huella: HuellaCabecera): ResumenHuella {
  return {
    hashColumnas: hashColumnas(huella),
    nColumnas: nColumnas(huella),
    delimitador: huella.delimitador,
    codificacion: huella.codificacion,
  };
}

function resumenCoincideCon(resumen: ResumenHuella, huella: HuellaCabecera): boolean {
  return (
    resumen.hashColumnas === hashColumnas(huella) &&
    resumen.nColumnas === nColumnas(huella) &&
    resumen.delimitador === huella.delimitador &&
    resumen.codificacion === huella.codificacion
  );
}

// --------------------------------------------------------------------------- #
// El perfil completo
// --------------------------------------------------------------------------- #
export interface TiempoDePerfil {
  readonly propuesta: PropuestaTiempo;
  readonly nombreColumna: string | null;
  readonly nombreColumnaFecha: string | null;
}

export interface PerfilImportacion {
  readonly nombre: string;
  readonly huella: ResumenHuella;
  readonly formato: PropuestaFormato;
  readonly tiempo: TiempoDePerfil;
  readonly canales: readonly CanalPropuesto[];
}

/**
 * Construye un `PerfilImportacion` a partir del estado terminado del
 * asistente (`ResultadoAsistenteImportacion`) y calcula su huella. Camino
 * "Guardar como perfil de importación" de §7.8.
 *
 * `nombresColumnas` es la cabecera COMPLETA del fichero (con la columna de
 * tiempo), igual que en `dlv_core.perfil_importacion.crear_perfil`: de ahí
 * saca también, automáticamente, el nombre de la columna de tiempo
 * confirmada (si la hay), así que quien llama no tiene que calcularlo aparte.
 */
export function crearPerfil(
  nombre: string,
  nombresColumnas: readonly string[],
  formato: PropuestaFormato,
  tiempo: PropuestaTiempo,
  canales: readonly CanalPropuesto[],
): PerfilImportacion {
  if (nombre.trim() === "") {
    throw new ErrorDePerfilImportacion("un perfil de importación necesita un nombre no vacío");
  }
  if (formato.delimitador.valor === null) {
    throw new ErrorDePerfilImportacion(
      "no se puede guardar un perfil de importación sin un delimitador confirmado",
    );
  }
  const huella = construirHuella(nombresColumnas, formato.delimitador.valor, formato.codificacion.valor);
  const nombreColumna =
    tiempo.columna.valor === null ? null : (nombresColumnas[tiempo.columna.valor] ?? null);
  const nombreColumnaFecha =
    tiempo.columnaFecha.valor === null ? null : (nombresColumnas[tiempo.columnaFecha.valor] ?? null);
  return {
    nombre,
    huella: resumenDeHuella(huella),
    formato,
    tiempo: { propuesta: tiempo, nombreColumna, nombreColumnaFecha },
    canales: [...canales],
  };
}

// --------------------------------------------------------------------------- #
// Reaplicación. Ver `dlv_core.perfil_importacion.reaplicar_perfil` para la
// frontera completa entre "total"/"parcial"/"ninguna": es literalmente la
// misma, línea a línea.
// --------------------------------------------------------------------------- #
export type TipoCoincidencia = "total" | "parcial" | "ninguna";

export interface ResultadoReaplicacion {
  readonly tipo: TipoCoincidencia;
  readonly motivo: string;
  readonly formato: PropuestaFormato;
  readonly tiempo: PropuestaTiempo;
  /** Misma longitud y orden que `canalesActuales`: un canal cuyo nombre no
   * estaba en el perfil sale IDÉNTICO al que entró (recién deducido) y
   * además su nombre está en `columnasNuevasSinDecidir` — la manera de que
   * el usuario lo VEA, no de que lo adivine. */
  readonly canales: readonly CanalPropuesto[];
  readonly columnasNuevasSinDecidir: readonly string[];
  readonly avisos: readonly string[];
}

function fusionarCampo<T>(actual: Campo<T>, guardado: Campo<T>): Campo<T> {
  if (guardado.origen === "confirmado") return { valor: guardado.valor, origen: "confirmado" };
  return actual;
}

function fusionarRol(actual: RolPropuesto | null, guardado: RolPropuesto | null): RolPropuesto | null {
  if (guardado !== null && guardado.confirmado) return guardado;
  return actual;
}

function fusionarCanal(actual: CanalPropuesto, guardado: CanalPropuesto): CanalPropuesto {
  return {
    ...actual,
    dimensionId: fusionarCampo(actual.dimensionId, guardado.dimensionId),
    unidadOrigen: fusionarCampo(actual.unidadOrigen, guardado.unidadOrigen),
    rol: fusionarRol(actual.rol, guardado.rol),
  };
}

function fusionarFormato(actual: PropuestaFormato, guardado: PropuestaFormato): PropuestaFormato {
  return {
    codificacion: fusionarCampo(actual.codificacion, guardado.codificacion),
    delimitador: fusionarCampo(actual.delimitador, guardado.delimitador),
    comilla: fusionarCampo(actual.comilla, guardado.comilla),
    decimal: fusionarCampo(actual.decimal, guardado.decimal),
    filaCabecera: fusionarCampo(actual.filaCabecera, guardado.filaCabecera),
    filaUnidades: fusionarCampo(actual.filaUnidades, guardado.filaUnidades),
    filaDatos: fusionarCampo(actual.filaDatos, guardado.filaDatos),
  };
}

function fusionarColumnaTiempo(
  campoActual: Campo<number | null>,
  campoGuardado: Campo<number | null>,
  nombreGuardado: string | null,
  nombresColumnas: readonly string[],
): { readonly campo: Campo<number | null>; readonly aviso: string | null } {
  if (campoGuardado.origen !== "confirmado") return { campo: campoActual, aviso: null };
  if (nombreGuardado === null) {
    return { campo: { valor: campoGuardado.valor, origen: "confirmado" }, aviso: null };
  }
  const clave = normalizar(nombreGuardado);
  const indice = nombresColumnas.findIndex((n) => normalizar(n) === clave);
  if (indice !== -1) {
    return { campo: { valor: indice, origen: "confirmado" }, aviso: null };
  }
  return {
    campo: campoActual,
    aviso: `la columna de tiempo confirmada «${nombreGuardado}» no está en este fichero: se vuelve a deducir`,
  };
}

function fusionarTiempo(
  actual: PropuestaTiempo,
  guardado: TiempoDePerfil,
  nombresColumnas: readonly string[],
): { readonly tiempo: PropuestaTiempo; readonly avisos: readonly string[] } {
  const columna = fusionarColumnaTiempo(
    actual.columna,
    guardado.propuesta.columna,
    guardado.nombreColumna,
    nombresColumnas,
  );
  const columnaFecha = fusionarColumnaTiempo(
    actual.columnaFecha,
    guardado.propuesta.columnaFecha,
    guardado.nombreColumnaFecha,
    nombresColumnas,
  );
  const avisos = [columna.aviso, columnaFecha.aviso].filter((a): a is string => a !== null);
  return {
    tiempo: {
      clase: fusionarCampo(actual.clase, guardado.propuesta.clase),
      columna: columna.campo,
      columnaFecha: columnaFecha.campo,
      frecuenciaHz: fusionarCampo(actual.frecuenciaHz, guardado.propuesta.frecuenciaHz),
      factorASegundos: actual.factorASegundos,
    },
    avisos,
  };
}

/**
 * Reaplica `perfil` sobre la propuesta YA DEDUCIDA de un fichero nuevo
 * (`formatoActual`/`tiempoActual`/`canalesActuales`, tal como los produce el
 * asistente tras sondear — todo `origen: "deducido"`). No vuelve a sondear
 * nada: fusiona campo a campo (`fusionarCampo`, la regla central: lo
 * confirmado sobrevive, lo deducido se vuelve a deducir) y canal a canal,
 * emparejados por nombre normalizado.
 */
export function reaplicarPerfil(
  perfil: PerfilImportacion,
  nombresColumnas: readonly string[],
  formatoActual: PropuestaFormato,
  tiempoActual: PropuestaTiempo,
  canalesActuales: readonly CanalPropuesto[],
): ResultadoReaplicacion {
  const sinReaplicar = (motivo: string): ResultadoReaplicacion => ({
    tipo: "ninguna",
    motivo,
    formato: formatoActual,
    tiempo: tiempoActual,
    canales: [...canalesActuales],
    columnasNuevasSinDecidir: canalesActuales.map((c) => c.nombreOriginal),
    avisos: [],
  });

  const delimitadorActual = formatoActual.delimitador.valor;
  if (delimitadorActual !== perfil.huella.delimitador) {
    return sinReaplicar(
      `el perfil «${perfil.nombre}» se guardó con el delimitador ${JSON.stringify(perfil.huella.delimitador)} ` +
        `y este fichero usa ${JSON.stringify(delimitadorActual)}: no es el mismo formato, no se reaplica nada`,
    );
  }
  const codificacionActual = formatoActual.codificacion.valor;
  if (codificacionActual !== perfil.huella.codificacion) {
    return sinReaplicar(
      `el perfil «${perfil.nombre}» se guardó con la codificación ${JSON.stringify(perfil.huella.codificacion)} ` +
        `y este fichero usa ${JSON.stringify(codificacionActual)}: no es el mismo formato, no se reaplica nada`,
    );
  }

  const porNombrePerfil = new Map(perfil.canales.map((c) => [normalizar(c.nombreOriginal), c]));
  const nCoincidencias = canalesActuales.filter((c) =>
    porNombrePerfil.has(normalizar(c.nombreOriginal)),
  ).length;
  if (nCoincidencias === 0) {
    return sinReaplicar(
      `ninguna columna de este fichero coincide con las ${perfil.canales.length} del perfil ` +
        `«${perfil.nombre}»: mismo delimitador y codificación, pero no parece el mismo origen de ` +
        "datos, no se reaplica nada",
    );
  }

  const columnasNuevas: string[] = [];
  const canalesFusionados = canalesActuales.map((canal) => {
    const guardado = porNombrePerfil.get(normalizar(canal.nombreOriginal));
    if (guardado === undefined) {
      columnasNuevas.push(canal.nombreOriginal);
      return canal;
    }
    return fusionarCanal(canal, guardado);
  });

  const nombresVistos = new Set(canalesActuales.map((c) => normalizar(c.nombreOriginal)));
  const columnasPerdidas = perfil.canales
    .filter((c) => !nombresVistos.has(normalizar(c.nombreOriginal)))
    .map((c) => c.nombreOriginal);

  const formatoFusionado = fusionarFormato(formatoActual, perfil.formato);
  const { tiempo: tiempoFusionado, avisos: avisosTiempo } = fusionarTiempo(
    tiempoActual,
    perfil.tiempo,
    nombresColumnas,
  );

  const avisos = [...avisosTiempo];
  if (columnasNuevas.length > 0) {
    avisos.push(
      `${columnasNuevas.length} columna(s) nueva(s) sin decisión del perfil «${perfil.nombre}»: ` +
        columnasNuevas.join(", "),
    );
  }
  if (columnasPerdidas.length > 0) {
    avisos.push(
      `${columnasPerdidas.length} columna(s) del perfil «${perfil.nombre}» no están en este ` +
        "fichero: " +
        columnasPerdidas.join(", "),
    );
  }

  const huellaActual = construirHuella(nombresColumnas, delimitadorActual, codificacionActual);
  const coincideTodo =
    resumenCoincideCon(perfil.huella, huellaActual) &&
    columnasNuevas.length === 0 &&
    columnasPerdidas.length === 0;

  const tipo: TipoCoincidencia = coincideTodo ? "total" : "parcial";
  const motivo = coincideTodo
    ? `huella idéntica a la del perfil «${perfil.nombre}»: se reaplica entero`
    : `huella compatible en parte con el perfil «${perfil.nombre}» (${nCoincidencias}/` +
      `${canalesActuales.length} columnas de este fichero coinciden por nombre): se reaplica lo ` +
      "que coincide";

  return {
    tipo,
    motivo,
    formato: formatoFusionado,
    tiempo: tiempoFusionado,
    canales: canalesFusionados,
    columnasNuevasSinDecidir: columnasNuevas,
    avisos,
  };
}

// Reexportado por si algún consumidor quiere construir un `Campo<T>` deducido
// a mano al montar un canal nuevo antes de reaplicar (mismo motivo que
// `puerto.ts` reexporta su único error): un import menos que recordar.
export { deducido };

/**
 * QUÉ FALTA (informe de la tarea)
 * =================================
 * Este módulo asume que YA HAY un `PerfilImportacion` en memoria. Cargarlo o
 * guardarlo de disco no está aquí a propósito: `dlv-core` no toca ficheros
 * (ADR-002) y `dlv-api` todavía no tiene ningún endpoint para `.dlvimport` —
 * ni para listar los perfiles guardados, ni para leer uno, ni para guardarlo.
 * Es el mismo hueco que `puerto.ts` documenta para el sondeo (FG-18 lo cerró
 * para sondear_formato/tiempo/canales/roles; el equivalente para
 * `.dlvimport` sigue sin cablear). Tampoco se ha tocado
 * `asistente-importacion.ts`: cablear "cargar perfil al elegir fichero" y
 * "guardar como perfil" en la UI del asistente es integración de otra tarea,
 * no lógica nueva — este módulo deja lista la única pieza que faltaba,
 * `crearPerfil`/`reaplicarPerfil`, para que esa integración no tenga que
 * inventar la fusión de campos.
 */
