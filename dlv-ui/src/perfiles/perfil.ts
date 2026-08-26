/**
 * Espejo TypeScript de `dlv_core.perfil` (F3-01): el esquema del `.dlvprofile`
 * y su (de)serializador JSON, sin ningún E/S (igual que el original: quien lee
 * o escribe el fichero de disco es `dlv-api`/el navegador, nunca este módulo).
 *
 * POR QUÉ HAY UN ESPEJO EN VEZ DE LLAMAR A `dlv-api`
 * =====================================================
 * `dlv-api` no tiene hoy ninguna ruta `/comandos/perfil*` (comprobado sobre
 * `dlv_api/main.py`, mismo criterio que `importacion/puerto.ts` documenta para
 * el sondeo de CSV: "si hace falta un endpoint que no existe, dilo en vez de
 * inventarlo"). Pedirle red a este editor para una validación que
 * `perfil.py` ya hace sin ningún E/S habría añadido una dependencia que hoy no
 * se puede satisfacer, cuando la validación en sí es aritmética/estructural
 * pura y se puede espejar exactamente como ya hace `importacion/
 * perfil-importacion.ts` con `dlv_core.perfil_importacion`. El precedente es
 * literal: ese fichero reimplementa la fusión y el hash de `.dlvimport` en vez
 * de pedirle a un backend que no existe que lo haga.
 *
 * RIESGO ACEPTADO Y POR QUÉ ES EL MISMO QUE YA EXISTE
 * =====================================================
 * Este espejo puede desincronizarse de `perfil.py` si alguien cambia una regla
 * allí y no aquí — el mismo riesgo que ya acepta `unidades/conversion.ts`
 * frente a `dlv_core.unidades` (su cabecera lo dice: "las dos implementaciones
 * tienen que coincidir o los ejes dirán una cosa y el informe otra"). No hay
 * ningún mecanismo de sincronización automática en `dlv-ui` hoy; no se
 * inventa uno solo para este módulo. Si `dlv-api` gana una ruta de validación
 * de perfiles, el sitio natural para relevarla es
 * `perfilDesdeTextoJson`/`perfilATextoJson` de este fichero, sin tocar el
 * resto del editor.
 *
 * QUÉ SE MIRA PARA MANTENER EL MISMO CONTRATO DE FICHERO
 * =========================================================
 * Los nombres de clave JSON (`version_esquema`, `id_nativo`, `rol_referencia`,
 * `detectores_activos`...) son los que escribe `Perfil.a_dict()` en
 * `dlv-core/src/dlv_core/perfil.py`, leído entero antes de escribir esto. Los
 * tipos de TypeScript usan camelCase (convención del resto de `dlv-ui`); la
 * traducción entre las dos formas vive SOLO en `...ADict`/`...DesdeDict`,
 * nunca dispersa.
 */

// Ningún tipo de `unidades/conversion.ts` se necesita aquí: la clase de
// conversión de un límite es siempre PUNTO (dlv_core.topes, ver su cabecera)
// y este módulo no convierte nada, solo (de)serializa. La conversión activa
// vive en `edicion-umbrales.ts`.

/** Sube solo si cambia la FORMA del esquema (misma regla que el original). */
export const VERSION_ESQUEMA_PERFIL = 1;

export class ErrorDePerfil extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDePerfil";
  }
}

export class ErrorDeVersionDePerfilDesconocida extends ErrorDePerfil {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeVersionDePerfilDesconocida";
  }
}

// --------------------------------------------------------------------------- //
// Nivel de tope y dirección: espejo de `dlv_core.primitivas.Direccion` y
// `dlv_core.topes.NivelDeTope`. Solo los valores por cadena: la aritmética de
// histéresis/comparación no vive aquí (es de F3-06 en el backend), solo la
// forma del dato tal como se guarda en el `.dlvprofile`.
// --------------------------------------------------------------------------- //
export type NivelDeTope = "aviso" | "critico";
export type Direccion = "arriba" | "abajo";

// --------------------------------------------------------------------------- //
// Curva: espejo de `dlv_core.topes.Curva` (`CurvaLineal` | `CurvaPorPuntos`).
// --------------------------------------------------------------------------- //
export interface CurvaLineal {
  readonly forma: "lineal";
  readonly rolReferencia: string;
  readonly base: number;
  readonly pendiente: number;
  readonly divisorReferencia: number;
}

export interface CurvaPorPuntos {
  readonly forma: "puntos";
  readonly rolReferencia: string;
  readonly puntos: readonly (readonly [number, number])[];
}

export type Curva = CurvaLineal | CurvaPorPuntos;

export function esCurva(valor: number | Curva): valor is Curva {
  return typeof valor !== "number";
}

/**
 * Las invariantes de una curva, aplicadas SIEMPRE que aparece una — venga de
 * `curvaDesdeDict` (un `.dlvprofile` importado) o de construir un `Tope`/
 * `TopeDeBanda` a mano en el editor (`construirTope`,
 * `construirLimiteDeAlerta`). Un objeto `Curva` construido con un literal de
 * TypeScript no pasa por `construirCurvaLineal`/`construirCurvaPorPuntos`, así
 * que validar solo ahí dejaría un agujero: un divisor a 0 tecleado en el
 * editor pasaría sin avisar hasta que alguien intentara evaluar la curva
 * mucho más tarde, en F3-06. Mismo criterio que
 * `dlv_core.topes.CurvaLineal.__post_init__`: se comprueba en cuanto el valor
 * existe, no cuando se usa.
 */
export function validarCurva(curva: Curva): void {
  if (curva.forma === "lineal") {
    if (curva.divisorReferencia === 0) {
      throw new ErrorDePerfil("divisor_referencia no puede ser 0");
    }
    return;
  }
  if (curva.puntos.length < 2) {
    throw new ErrorDePerfil(
      `una curva por puntos necesita al menos 2 puntos, y tiene ${curva.puntos.length}: ` +
        "con uno solo no hay nada que interpolar (y si el tope es constante, declara un " +
        "número y no una curva)",
    );
  }
  for (let i = 1; i < curva.puntos.length; i += 1) {
    const anterior = curva.puntos[i - 1]![0];
    const siguiente = curva.puntos[i]![0];
    if (siguiente <= anterior) {
      throw new ErrorDePerfil(
        "los puntos tienen que ir en orden estrictamente creciente de referencia, y " +
          `${siguiente} no es mayor que ${anterior}`,
      );
    }
  }
}

function construirCurvaLineal(datos: Omit<CurvaLineal, "forma">): CurvaLineal {
  const curva: CurvaLineal = { forma: "lineal", ...datos };
  validarCurva(curva);
  return curva;
}

function construirCurvaPorPuntos(datos: Omit<CurvaPorPuntos, "forma">): CurvaPorPuntos {
  const curva: CurvaPorPuntos = { forma: "puntos", ...datos };
  validarCurva(curva);
  return curva;
}

function curvaADict(curva: Curva): Record<string, unknown> {
  if (curva.forma === "lineal") {
    return {
      forma: "lineal",
      rol_referencia: curva.rolReferencia,
      base: curva.base,
      pendiente: curva.pendiente,
      divisor_referencia: curva.divisorReferencia,
    };
  }
  return {
    forma: "puntos",
    rol_referencia: curva.rolReferencia,
    puntos: curva.puntos.map(([x, y]) => [x, y]),
  };
}

function esRegistro(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function numeroDesde(valor: unknown, clave: string, contexto: string): number {
  if (typeof valor !== "number" || !Number.isFinite(valor)) {
    throw new ErrorDePerfil(`${contexto}: '${clave}' debe ser un número`);
  }
  return valor;
}

function curvaDesdeDict(bruto: unknown, contexto: string): Curva {
  if (!esRegistro(bruto)) {
    throw new ErrorDePerfil(`${contexto}: debe ser una tabla/objeto`);
  }
  const rolReferencia = bruto["rol_referencia"];
  if (typeof rolReferencia !== "string" || rolReferencia.trim() === "") {
    throw new ErrorDePerfil(`${contexto}: 'rol_referencia' debe ser texto no vacío`);
  }
  const forma = bruto["forma"];
  if (forma === "lineal") {
    return construirCurvaLineal({
      rolReferencia,
      base: numeroDesde(bruto["base"], "base", contexto),
      pendiente: numeroDesde(bruto["pendiente"], "pendiente", contexto),
      divisorReferencia: numeroDesde(bruto["divisor_referencia"], "divisor_referencia", contexto),
    });
  }
  if (forma === "puntos") {
    const puntosBrutos = bruto["puntos"];
    if (!Array.isArray(puntosBrutos)) {
      throw new ErrorDePerfil(`${contexto}: 'puntos' debe ser una lista de pares [referencia, valor]`);
    }
    const puntos = puntosBrutos.map((p, i): readonly [number, number] => {
      if (!Array.isArray(p) || p.length !== 2) {
        throw new ErrorDePerfil(`${contexto}.puntos[${i}]: debe ser un par [referencia, valor]`);
      }
      return [
        numeroDesde(p[0], "0", `${contexto}.puntos[${i}]`),
        numeroDesde(p[1], "1", `${contexto}.puntos[${i}]`),
      ];
    });
    return construirCurvaPorPuntos({ rolReferencia, puntos });
  }
  throw new ErrorDePerfil(
    `${contexto}: 'forma' de curva desconocida: ${JSON.stringify(forma)} (válidas: 'lineal', 'puntos')`,
  );
}

function valorOCurvaADict(valor: number | Curva): unknown {
  return esCurva(valor) ? curvaADict(valor) : valor;
}

function valorOCurvaDesdeDict(bruto: unknown, contexto: string): number | Curva {
  if (esRegistro(bruto)) return curvaDesdeDict(bruto, contexto);
  if (typeof bruto !== "number" || !Number.isFinite(bruto)) {
    throw new ErrorDePerfil(`${contexto}: debe ser un número o una curva, y aquí es ${JSON.stringify(bruto)}`);
  }
  return bruto;
}

// --------------------------------------------------------------------------- //
// Tope y TopeDeBanda: espejo de `dlv_core.topes.Tope`/`TopeDeBanda`.
// --------------------------------------------------------------------------- //
export interface Tope {
  readonly nivel: NivelDeTope;
  readonly direccion: Direccion;
  readonly valor: number | Curva;
}

export interface TopeDeBanda {
  readonly nivel: NivelDeTope;
  readonly minimo: number | Curva;
  readonly maximo: number | Curva;
}

const NIVELES: readonly NivelDeTope[] = ["aviso", "critico"];
const DIRECCIONES: readonly Direccion[] = ["arriba", "abajo"];

function nivelDesdeBruto(bruto: unknown, contexto: string): NivelDeTope {
  if (typeof bruto !== "string" || !NIVELES.includes(bruto as NivelDeTope)) {
    throw new ErrorDePerfil(`${contexto}: 'nivel' desconocido ${JSON.stringify(bruto)}; válidos: ${JSON.stringify(NIVELES)}`);
  }
  return bruto as NivelDeTope;
}

function direccionDesdeBruto(bruto: unknown, contexto: string): Direccion {
  if (typeof bruto !== "string" || !DIRECCIONES.includes(bruto as Direccion)) {
    throw new ErrorDePerfil(`${contexto}: 'direccion' desconocida ${JSON.stringify(bruto)}; válidas: ${JSON.stringify(DIRECCIONES)}`);
  }
  return bruto as Direccion;
}

/**
 * Comprueba que el aviso se alcanza antes que el crítico (espejo de
 * `dlv_core.topes.validar_pareja`). Solo entre topes planos: dos curvas
 * pueden cruzarse, y esa comparación no es de este módulo (F3-06).
 */
function validarPareja(aviso: Tope, critico: Tope, contexto: string): void {
  if (aviso.direccion !== critico.direccion) {
    throw new ErrorDePerfil(
      `${contexto}: el tope de aviso va ${aviso.direccion} y el crítico ${critico.direccion}: ` +
        "son dos alertas distintas, no dos niveles de la misma",
    );
  }
  if (esCurva(aviso.valor) || esCurva(critico.valor)) return;
  const a = aviso.valor;
  const c = critico.valor;
  if (aviso.direccion === "arriba" && a > c) {
    throw new ErrorDePerfil(
      `${contexto}: con dirección arriba el aviso (${a}) tiene que ser menor o igual que el ` +
        `crítico (${c}); así el crítico salta primero y el aviso nunca avisa`,
    );
  }
  if (aviso.direccion === "abajo" && a < c) {
    throw new ErrorDePerfil(
      `${contexto}: con dirección abajo el aviso (${a}) tiene que ser mayor o igual que el ` +
        `crítico (${c}); así el crítico salta primero y el aviso nunca avisa`,
    );
  }
}

export function construirTope(datos: Tope): Tope {
  if (esCurva(datos.valor)) validarCurva(datos.valor);
  return { ...datos };
}

function topeADict(tope: Tope): Record<string, unknown> {
  return { nivel: tope.nivel, direccion: tope.direccion, valor: valorOCurvaADict(tope.valor) };
}

function topeDesdeDict(bruto: unknown, contexto: string): Tope {
  if (!esRegistro(bruto)) throw new ErrorDePerfil(`${contexto}: debe ser una tabla/objeto`);
  const nivel = nivelDesdeBruto(bruto["nivel"], contexto);
  const direccion = direccionDesdeBruto(bruto["direccion"], contexto);
  if (!("valor" in bruto)) throw new ErrorDePerfil(`${contexto}: falta 'valor'`);
  const valor = valorOCurvaDesdeDict(bruto["valor"], `${contexto}.valor`);
  return { nivel, direccion, valor };
}

function bandaADict(banda: TopeDeBanda): Record<string, unknown> {
  return {
    nivel: banda.nivel,
    minimo: valorOCurvaADict(banda.minimo),
    maximo: valorOCurvaADict(banda.maximo),
  };
}

function bandaDesdeDict(bruto: unknown, contexto: string): TopeDeBanda {
  if (!esRegistro(bruto)) throw new ErrorDePerfil(`${contexto}: debe ser una tabla/objeto`);
  if (!("minimo" in bruto) || !("maximo" in bruto)) {
    throw new ErrorDePerfil(`${contexto}: una banda necesita 'minimo' y 'maximo'`);
  }
  const nivel = nivelDesdeBruto(bruto["nivel"], contexto);
  const minimo = valorOCurvaDesdeDict(bruto["minimo"], `${contexto}.minimo`);
  const maximo = valorOCurvaDesdeDict(bruto["maximo"], `${contexto}.maximo`);
  return { nivel, minimo, maximo };
}

// --------------------------------------------------------------------------- //
// LimiteDeAlerta: espejo de `dlv_core.perfil.LimiteDeAlerta`.
// --------------------------------------------------------------------------- //
export interface LimiteDeAlerta {
  readonly rol: string;
  readonly topes: readonly Tope[];
  readonly banda: TopeDeBanda | null;
}

export function construirLimiteDeAlerta(datos: {
  readonly rol: string;
  readonly topes?: readonly Tope[];
  readonly banda?: TopeDeBanda | null;
}): LimiteDeAlerta {
  const rol = datos.rol;
  const topes = datos.topes ?? [];
  const banda = datos.banda ?? null;
  const contexto = `el límite del rol '${rol}'`;
  if (rol.trim() === "") throw new ErrorDePerfil("un límite de alerta necesita un `rol` no vacío");
  for (const tope of topes) if (esCurva(tope.valor)) validarCurva(tope.valor);
  if (banda !== null) {
    if (esCurva(banda.minimo)) validarCurva(banda.minimo);
    if (esCurva(banda.maximo)) validarCurva(banda.maximo);
  }
  if (topes.length > 0 && banda !== null) {
    throw new ErrorDePerfil(
      `${contexto} declara topes unidireccionales Y una banda: son dos formas de expresar el ` +
        "límite y no se combinan para el mismo rol",
    );
  }
  if (topes.length === 0 && banda === null) {
    throw new ErrorDePerfil(
      `${contexto} no declara ningún tope ni banda: quita la entrada de \`limites\` en vez de dejarla vacía`,
    );
  }
  if (topes.length > 2) {
    throw new ErrorDePerfil(`${contexto} declara ${topes.length} topes: solo hay dos niveles posibles, aviso y crítico`);
  }
  const niveles = topes.map((t) => t.nivel);
  if (new Set(niveles).size !== niveles.length) {
    throw new ErrorDePerfil(
      `${contexto} declara más de un tope del mismo nivel (${JSON.stringify(niveles)}): un aviso y ` +
        "un crítico, no dos del mismo",
    );
  }
  if (topes.length === 2) {
    const aviso = topes.find((t) => t.nivel === "aviso");
    const critico = topes.find((t) => t.nivel === "critico");
    if (aviso !== undefined && critico !== undefined) validarPareja(aviso, critico, contexto);
  }
  return { rol, topes: [...topes], banda };
}

function limiteADict(limite: LimiteDeAlerta): Record<string, unknown> {
  const bruto: Record<string, unknown> = { rol: limite.rol };
  if (limite.topes.length > 0) bruto["topes"] = limite.topes.map(topeADict);
  if (limite.banda !== null) bruto["banda"] = bandaADict(limite.banda);
  return bruto;
}

function limiteDesdeDict(bruto: unknown, indice: number): LimiteDeAlerta {
  const contexto = `limites[${indice}]`;
  if (!esRegistro(bruto)) throw new ErrorDePerfil(`${contexto}: debe ser una tabla/objeto`);
  const rol = bruto["rol"];
  if (typeof rol !== "string" || rol.trim() === "") {
    throw new ErrorDePerfil(`${contexto}: 'rol' debe ser texto no vacío`);
  }
  const topesBrutos = bruto["topes"] ?? [];
  if (!Array.isArray(topesBrutos)) throw new ErrorDePerfil(`${contexto}: 'topes' debe ser una lista`);
  const topes = topesBrutos.map((t, i) => topeDesdeDict(t, `${contexto}.topes[${i}]`));
  const bandaBruto = bruto["banda"];
  if (bandaBruto !== undefined && bandaBruto !== null && !esRegistro(bandaBruto)) {
    throw new ErrorDePerfil(`${contexto}.banda: debe ser una tabla/objeto`);
  }
  const banda = bandaBruto ? bandaDesdeDict(bandaBruto, `${contexto}.banda`) : null;
  try {
    return construirLimiteDeAlerta({ rol, topes, banda });
  } catch (exc) {
    if (exc instanceof ErrorDePerfil) throw new ErrorDePerfil(`${contexto}: ${exc.message}`);
    throw exc;
  }
}

// --------------------------------------------------------------------------- //
// ElementoDePanel: espejo de `dlv_core.perfil.ElementoDePanel`. `rol` e
// `idNativo` son mutuamente excluyentes (docs/07 §7.12); un `idNativo` no
// puede ser `requerido` (rompería el perfil en cualquier otro formato).
// --------------------------------------------------------------------------- //
export interface ElementoDePanel {
  readonly rol: string | null;
  readonly idNativo: string | null;
  readonly requerido: boolean;
  readonly indice: number | null;
  readonly escalaMin: number | null;
  readonly escalaMax: number | null;
}

export function construirElementoDePanel(datos: {
  readonly rol?: string | null;
  readonly idNativo?: string | null;
  readonly requerido: boolean;
  readonly indice?: number | null;
  readonly escalaMin?: number | null;
  readonly escalaMax?: number | null;
}): ElementoDePanel {
  const rol = datos.rol ?? null;
  const idNativo = datos.idNativo ?? null;
  const indice = datos.indice ?? null;
  const escalaMin = datos.escalaMin ?? null;
  const escalaMax = datos.escalaMax ?? null;
  if ((rol === null) === (idNativo === null)) {
    throw new ErrorDePerfil(
      "un elemento de panel necesita EXACTAMENTE UNO de `rol` o `id_nativo`: el rol es la " +
        "identidad normal e independiente de fabricante; `id_nativo` es la reserva explícita " +
        "para un canal muy específico de un formato que no tiene rol universal (docs/07 §7.12). " +
        "Los dos a la vez, o ninguno, dejan sin decidir qué canal dibuja este elemento",
    );
  }
  if (rol !== null && rol.trim() === "") {
    throw new ErrorDePerfil("`rol` no puede ser una cadena vacía");
  }
  if (idNativo !== null) {
    if (idNativo.trim() === "") throw new ErrorDePerfil("`id_nativo` no puede ser una cadena vacía");
    if (datos.requerido) {
      throw new ErrorDePerfil(
        `el elemento con id_nativo '${idNativo}' no puede ser \`requerido\`: un ID nativo solo ` +
          "existe en el formato que lo declaró, así que exigirlo bloquearía este panel en " +
          "cualquier otro formato -- la independencia de fabricante que E4.1 exige (docs/07 §7.12)",
      );
    }
  }
  if (indice !== null && indice < 0) {
    throw new ErrorDePerfil(`\`indice\` no puede ser negativo, y aquí es ${indice}`);
  }
  if (escalaMin !== null && escalaMax !== null && escalaMin >= escalaMax) {
    throw new ErrorDePerfil(`escala_min (${escalaMin}) debe ser menor que escala_max (${escalaMax})`);
  }
  return { rol, idNativo, requerido: datos.requerido, indice, escalaMin, escalaMax };
}

/** `(rol, indice)` o `(id_nativo, indice)`: la clave de unicidad dentro de un panel. */
export function claveDeElemento(elemento: ElementoDePanel): string {
  const identidad = elemento.rol ?? elemento.idNativo;
  return `${identidad} ${elemento.indice ?? ""}`;
}

function elementoADict(elemento: ElementoDePanel): Record<string, unknown> {
  const bruto: Record<string, unknown> = { requerido: elemento.requerido };
  if (elemento.rol !== null) bruto["rol"] = elemento.rol;
  if (elemento.idNativo !== null) bruto["id_nativo"] = elemento.idNativo;
  if (elemento.indice !== null) bruto["indice"] = elemento.indice;
  if (elemento.escalaMin !== null) bruto["escala_min"] = elemento.escalaMin;
  if (elemento.escalaMax !== null) bruto["escala_max"] = elemento.escalaMax;
  return bruto;
}

function textoONulo(bruto: Record<string, unknown>, clave: string, contexto: string): string | null {
  const valor = bruto[clave];
  if (valor === undefined || valor === null) return null;
  if (typeof valor !== "string") throw new ErrorDePerfil(`${contexto}: '${clave}' debe ser texto o estar ausente`);
  return valor;
}

function numeroONulo(bruto: Record<string, unknown>, clave: string, contexto: string): number | null {
  const valor = bruto[clave];
  if (valor === undefined || valor === null) return null;
  if (typeof valor !== "number" || !Number.isFinite(valor)) {
    throw new ErrorDePerfil(`${contexto}: '${clave}' debe ser un número o estar ausente`);
  }
  return valor;
}

function elementoDesdeDict(bruto: unknown, contexto: string): ElementoDePanel {
  if (!esRegistro(bruto)) throw new ErrorDePerfil(`${contexto}: debe ser una tabla/objeto`);
  const rol = textoONulo(bruto, "rol", contexto);
  const idNativo = textoONulo(bruto, "id_nativo", contexto);
  const requerido = bruto["requerido"];
  if (typeof requerido !== "boolean") throw new ErrorDePerfil(`${contexto}: 'requerido' debe ser verdadero/falso`);
  const indiceBruto = bruto["indice"];
  if (
    indiceBruto !== undefined &&
    indiceBruto !== null &&
    (typeof indiceBruto !== "number" || !Number.isInteger(indiceBruto))
  ) {
    throw new ErrorDePerfil(`${contexto}: 'indice' debe ser un entero o estar ausente`);
  }
  try {
    return construirElementoDePanel({
      rol,
      idNativo,
      requerido,
      indice: (indiceBruto as number | null | undefined) ?? null,
      escalaMin: numeroONulo(bruto, "escala_min", contexto),
      escalaMax: numeroONulo(bruto, "escala_max", contexto),
    });
  } catch (exc) {
    if (exc instanceof ErrorDePerfil) throw new ErrorDePerfil(`${contexto}: ${exc.message}`);
    throw exc;
  }
}

// --------------------------------------------------------------------------- //
// Panel: espejo de `dlv_core.perfil.Panel`.
// --------------------------------------------------------------------------- //
export interface Panel {
  readonly titulo: string;
  readonly elementos: readonly ElementoDePanel[];
}

export function construirPanel(datos: { readonly titulo: string; readonly elementos: readonly ElementoDePanel[] }): Panel {
  if (datos.titulo.trim() === "") throw new ErrorDePerfil("un panel necesita un `titulo` no vacío");
  if (datos.elementos.length === 0) {
    throw new ErrorDePerfil(`el panel '${datos.titulo}' no tiene ningún elemento`);
  }
  const claves = new Set<string>();
  for (const elemento of datos.elementos) {
    const clave = claveDeElemento(elemento);
    if (claves.has(clave)) {
      throw new ErrorDePerfil(
        `el panel '${datos.titulo}' repite el elemento (${elemento.rol ?? elemento.idNativo}, ` +
          `${elemento.indice ?? "sin índice"}): cada rol (con su índice, si lo tiene) o cada ` +
          "id_nativo aparece una sola vez por panel",
      );
    }
    claves.add(clave);
  }
  return { titulo: datos.titulo, elementos: [...datos.elementos] };
}

/** Roles cuya ausencia oculta este panel entero (granularidad de panel, no de perfil). */
export function rolesRequeridosDePanel(panel: Panel): ReadonlySet<string> {
  const salida = new Set<string>();
  for (const e of panel.elementos) if (e.requerido && e.rol !== null) salida.add(e.rol);
  return salida;
}

export function rolesOpcionalesDePanel(panel: Panel): ReadonlySet<string> {
  const salida = new Set<string>();
  for (const e of panel.elementos) if (!e.requerido && e.rol !== null) salida.add(e.rol);
  return salida;
}

export function rolesReferenciadosDePanel(panel: Panel): ReadonlySet<string> {
  return new Set([...rolesRequeridosDePanel(panel), ...rolesOpcionalesDePanel(panel)]);
}

function panelADict(panel: Panel): Record<string, unknown> {
  return { titulo: panel.titulo, elementos: panel.elementos.map(elementoADict) };
}

function panelDesdeDict(bruto: unknown, indice: number): Panel {
  const contexto = `paneles[${indice}]`;
  if (!esRegistro(bruto)) throw new ErrorDePerfil(`${contexto}: debe ser una tabla/objeto`);
  const titulo = bruto["titulo"];
  if (typeof titulo !== "string" || titulo.trim() === "") {
    throw new ErrorDePerfil(`${contexto}: 'titulo' debe ser texto no vacío`);
  }
  const elementosBrutos = bruto["elementos"];
  if (!Array.isArray(elementosBrutos) || elementosBrutos.length === 0) {
    throw new ErrorDePerfil(`${contexto}: 'elementos' debe ser una lista no vacía`);
  }
  const elementos = elementosBrutos.map((e, i) => elementoDesdeDict(e, `${contexto}.elementos[${i}]`));
  try {
    return construirPanel({ titulo, elementos });
  } catch (exc) {
    if (exc instanceof ErrorDePerfil) throw new ErrorDePerfil(`${contexto}: ${exc.message}`);
    throw exc;
  }
}

// --------------------------------------------------------------------------- //
// Perfil: espejo de `dlv_core.perfil.Perfil`.
// --------------------------------------------------------------------------- //
export interface Perfil {
  readonly nombre: string;
  readonly descripcion: string;
  readonly paneles: readonly Panel[];
  /** `dimension_id -> unidad_id` (decisión 3 de `perfil.py`: forma exacta de `preferencias_perfil`). */
  readonly unidades: Readonly<Record<string, string>>;
  readonly limites: readonly LimiteDeAlerta[];
  readonly detectoresActivos: readonly string[];
  readonly ejeXPreferido: string | null;
}

export function construirPerfil(datos: {
  readonly nombre: string;
  readonly descripcion?: string;
  readonly paneles: readonly Panel[];
  readonly unidades?: Readonly<Record<string, string>>;
  readonly limites?: readonly LimiteDeAlerta[];
  readonly detectoresActivos?: readonly string[];
  readonly ejeXPreferido?: string | null;
}): Perfil {
  const nombre = datos.nombre;
  const descripcion = datos.descripcion ?? "";
  const unidades = datos.unidades ?? {};
  const limites = datos.limites ?? [];
  const detectoresActivos = datos.detectoresActivos ?? [];
  const ejeXPreferido = datos.ejeXPreferido ?? null;

  if (nombre.trim() === "") throw new ErrorDePerfil("un perfil necesita un `nombre` no vacío");
  if (datos.paneles.length === 0) throw new ErrorDePerfil(`el perfil '${nombre}' no tiene ningún panel`);
  for (const [dimensionId, idUnidad] of Object.entries(unidades)) {
    if (dimensionId.trim() === "" || idUnidad.trim() === "") {
      throw new ErrorDePerfil(
        `el perfil '${nombre}': 'unidades' tiene una entrada vacía (${JSON.stringify(dimensionId)} -> ${JSON.stringify(idUnidad)})`,
      );
    }
  }
  const rolesConLimite = new Set<string>();
  for (const limite of limites) {
    if (rolesConLimite.has(limite.rol)) {
      throw new ErrorDePerfil(
        `el perfil '${nombre}' declara más de un límite de alerta para el rol '${limite.rol}': ` +
          "solo puede haber uno, con su tope o su banda, por rol",
      );
    }
    rolesConLimite.add(limite.rol);
  }
  if (new Set(detectoresActivos).size !== detectoresActivos.length) {
    throw new ErrorDePerfil(
      `el perfil '${nombre}' repite un detector en \`detectores_activos\`: ${JSON.stringify(detectoresActivos)}`,
    );
  }
  if (ejeXPreferido !== null && ejeXPreferido.trim() === "") {
    throw new ErrorDePerfil("`eje_x_preferido` no puede ser una cadena vacía");
  }

  return {
    nombre,
    descripcion,
    paneles: [...datos.paneles],
    unidades: { ...unidades },
    limites: [...limites],
    detectoresActivos: [...detectoresActivos],
    ejeXPreferido,
  };
}

export function rolesRequeridosDePerfil(perfil: Perfil): ReadonlySet<string> {
  const salida = new Set<string>();
  for (const panel of perfil.paneles) for (const rol of rolesRequeridosDePanel(panel)) salida.add(rol);
  return salida;
}

function rolesReferenciadosPorCurva(valor: number | Curva, salida: Set<string>): void {
  if (esCurva(valor)) salida.add(valor.rolReferencia);
}

/** Todos los roles que el perfil menciona: en paneles y en límites (denominador de E4.5). */
export function rolesReferenciadosDePerfil(perfil: Perfil): ReadonlySet<string> {
  const salida = new Set<string>();
  for (const panel of perfil.paneles) for (const rol of rolesReferenciadosDePanel(panel)) salida.add(rol);
  for (const limite of perfil.limites) {
    salida.add(limite.rol);
    for (const tope of limite.topes) rolesReferenciadosPorCurva(tope.valor, salida);
    if (limite.banda !== null) {
      rolesReferenciadosPorCurva(limite.banda.minimo, salida);
      rolesReferenciadosPorCurva(limite.banda.maximo, salida);
    }
  }
  return salida;
}

/** Forma exacta que espera `resolucion_unidad.resolver_unidad(..., preferencias_perfil=...)`. */
export function aPreferenciasDeUnidad(perfil: Perfil): Readonly<Record<string, string>> {
  return perfil.unidades;
}

// --------------------------------------------------------------------------- //
// dict <-> JSON
// --------------------------------------------------------------------------- //
export function perfilADict(perfil: Perfil): Record<string, unknown> {
  return {
    version_esquema: VERSION_ESQUEMA_PERFIL,
    nombre: perfil.nombre,
    descripcion: perfil.descripcion,
    eje_x_preferido: perfil.ejeXPreferido,
    unidades: { ...perfil.unidades },
    paneles: perfil.paneles.map(panelADict),
    limites: perfil.limites.map(limiteADict),
    detectores_activos: [...perfil.detectoresActivos],
  };
}

/**
 * El texto JSON completo del `.dlvprofile`, con las claves ordenadas — mismo
 * criterio que `Perfil.a_texto_json()` (`sort_keys=True, indent=2`), para que
 * un perfil exportado desde aquí y otro desde `dlv-core` sean
 * byte-comparables si contienen los mismos datos.
 */
export function perfilATextoJson(perfil: Perfil): string {
  return JSON.stringify(ordenarClavesProfundo(perfilADict(perfil)), null, 2);
}

/** Reordena las claves de un objeto (y de los objetos anidados) alfabéticamente. */
function ordenarClavesProfundo(valor: unknown): unknown {
  if (Array.isArray(valor)) return valor.map(ordenarClavesProfundo);
  if (esRegistro(valor)) {
    const salida: Record<string, unknown> = {};
    for (const clave of Object.keys(valor).sort()) salida[clave] = ordenarClavesProfundo(valor[clave]);
    return salida;
  }
  return valor;
}

export function perfilDesdeDict(bruto: unknown): Perfil {
  if (!esRegistro(bruto)) throw new ErrorDePerfil("perfil de análisis: la raíz del JSON debe ser un objeto");

  if (!("version_esquema" in bruto)) {
    throw new ErrorDePerfil("perfil de análisis incompleto: falta la clave 'version_esquema'");
  }
  const version = bruto["version_esquema"];
  if (version !== VERSION_ESQUEMA_PERFIL) {
    throw new ErrorDeVersionDePerfilDesconocida(
      `este .dlvprofile declara la versión de esquema ${JSON.stringify(version)} y este DataLogViewer ` +
        `solo sabe leer la versión ${VERSION_ESQUEMA_PERFIL}. Ábrelo con una versión que la reconozca`,
    );
  }

  const nombre = bruto["nombre"];
  if (typeof nombre !== "string" || nombre.trim() === "") {
    throw new ErrorDePerfil("perfil de análisis: 'nombre' debe ser texto no vacío");
  }
  const descripcion = bruto["descripcion"] ?? "";
  if (typeof descripcion !== "string") throw new ErrorDePerfil("perfil de análisis: 'descripcion' debe ser texto");
  const ejeXPreferido = bruto["eje_x_preferido"] ?? null;
  if (ejeXPreferido !== null && typeof ejeXPreferido !== "string") {
    throw new ErrorDePerfil("perfil de análisis: 'eje_x_preferido' debe ser texto o estar ausente/null");
  }

  const unidadesBrutas = bruto["unidades"] ?? {};
  if (!esRegistro(unidadesBrutas)) {
    throw new ErrorDePerfil("perfil de análisis: 'unidades' debe ser un objeto dimension_id -> unidad_id");
  }
  const unidades: Record<string, string> = {};
  for (const [k, v] of Object.entries(unidadesBrutas)) unidades[k] = String(v);

  const panelesBrutos = bruto["paneles"];
  if (!Array.isArray(panelesBrutos) || panelesBrutos.length === 0) {
    throw new ErrorDePerfil("perfil de análisis: 'paneles' debe ser una lista no vacía");
  }
  const paneles = panelesBrutos.map((p, i) => panelDesdeDict(p, i));

  const limitesBrutos = bruto["limites"] ?? [];
  if (!Array.isArray(limitesBrutos)) throw new ErrorDePerfil("perfil de análisis: 'limites' debe ser una lista");
  const limites = limitesBrutos.map((l, i) => limiteDesdeDict(l, i));

  const detectoresBrutos = bruto["detectores_activos"] ?? [];
  if (!Array.isArray(detectoresBrutos) || !detectoresBrutos.every((d) => typeof d === "string" && d.trim() !== "")) {
    throw new ErrorDePerfil("perfil de análisis: 'detectores_activos' debe ser una lista de cadenas no vacías");
  }

  try {
    return construirPerfil({
      nombre,
      descripcion,
      paneles,
      unidades,
      limites,
      detectoresActivos: detectoresBrutos as string[],
      ejeXPreferido,
    });
  } catch (exc) {
    if (exc instanceof ErrorDePerfil) throw new ErrorDePerfil(`perfil de análisis: ${exc.message}`);
    throw exc;
  }
}

export function perfilDesdeTextoJson(texto: string): Perfil {
  let bruto: unknown;
  try {
    bruto = JSON.parse(texto);
  } catch (exc) {
    const detalle = exc instanceof Error ? exc.message : String(exc);
    throw new ErrorDePerfil(`perfil de análisis: JSON inválido: ${detalle}`);
  }
  return perfilDesdeDict(bruto);
}
