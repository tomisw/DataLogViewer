/**
 * Renderizado progresivo: silueta inmediata, refinamiento de fondo
 * (F2-14, E3.7 de `docs/02`).
 *
 * EL PROBLEMA
 * ===========
 * Hasta ahora, un zoom o un pan que saliera del rango cacheado dejaba el panel
 * **quieto** hasta que llegaban los cubos del nivel bueno: `#redibujarUnaVez`
 * pedía el nivel que `elegirNivel` elige y no dibujaba nada antes. Con Python
 * al otro lado de HTTP eso son hasta 120 ms (§2.6, «pan/zoom que requiere
 * cubos nuevos del backend < 120 ms p95») en los que la pantalla no responde
 * al gesto. El presupuesto se cumple y la sensación es de bloqueo, porque lo
 * que el ojo mide no es cuánto tarda el dato sino cuánto tarda el dibujo en
 * moverse.
 *
 * Casi siempre hay una respuesta aproximada YA en memoria: el nivel grueso con
 * el que se abrió el log cubre todo el rango y está en la caché de F1-24. Se
 * dibuja ese al instante y se sustituye por el bueno cuando llega.
 *
 * LA PARTICIÓN DE ESTE MÓDULO
 * ===========================
 * Igual que `escala.ts` separa la aritmética del contexto WebGL, aquí se
 * separa la DECISIÓN del dibujo: qué nivel sirve de silueta, cómo se marca y
 * cuándo se abandona una pasada son funciones puras que se prueban en Node.
 * Lo impuro —subir a la GPU y escribir la nota en el DOM— se queda en
 * `app/aplicacion.ts`.
 *
 * ADR-006 SIGUE INTACTO
 * =====================
 * El renderizador **no gana ni un método**. La silueta se dibuja con
 * `subirSerie` y un `Color` con menos alfa, que es la API que ya había; la
 * nota es un adorno de texto, y ADR-006 manda los adornos a DOM/SVG. Este
 * módulo tampoco sabe qué es un log: recibe factores de decimación, tramos de
 * tiempo y un color.
 */

import type { Color } from "./tipos.ts";

/** Un tramo del eje de tiempo, en segundos absolutos. */
export interface Tramo {
  readonly t0: number;
  readonly t1: number;
}

/**
 * Un nivel de pirámide que ya está en memoria, y el tramo que tiene cubierto.
 *
 * Se define aquí y no se importa de `datos/cache-cubos.ts` a propósito: esa
 * dependencia iría al revés (la caché ya importa de `render/tipos.ts`) y
 * ataría el renderizador a la caché, que es exactamente lo que ADR-006 no
 * quiere. Quien llama traduce.
 */
export interface NivelEnMemoria {
  readonly factor: number;
  readonly cubre: Tramo;
}

/**
 * Qué se puede dibujar en esta pasada.
 *
 * - `definitivo`: el nivel que corresponde al zoom ya está en memoria. No hay
 *   nada provisional y no hay nada que refinar.
 * - `silueta`: hay algo más grueso que sirve de sustituto. Se dibuja marcado y
 *   se pide el bueno.
 * - `a-ciegas`: no hay nada en memoria que cubra lo visible. Es lo que pasa al
 *   abrir un log, y entonces esperar es lo correcto: dibujar «lo último que
 *   había» de otro rango de tiempo sería peor que un panel vacío.
 */
export type PlanProgresivo =
  | { readonly tipo: "definitivo"; readonly factor: number }
  | { readonly tipo: "silueta"; readonly factor: number; readonly factorObjetivo: number }
  | { readonly tipo: "a-ciegas"; readonly factorObjetivo: number };

/**
 * Los factores que ya están en memoria Y cubren el tramo visible entero.
 *
 * La cobertura tiene que ser completa por la misma razón que en
 * `CacheDeCubos.consultar`: media silueta dibuja medio panel y deja la otra
 * mitad en blanco, que se lee como «aquí el log se corta» en vez de como
 * «esto todavía no ha llegado».
 */
export function nivelesUtilizables(
  enMemoria: readonly NivelEnMemoria[],
  visible: Tramo,
): number[] {
  return enMemoria
    .filter((n) => n.cubre.t0 <= visible.t0 && n.cubre.t1 >= visible.t1)
    .map((n) => n.factor)
    .sort((a, b) => a - b);
}

/**
 * Decide qué se dibuja ya y qué hay que pedir.
 *
 * POR QUÉ LA SILUETA NUNCA ES MÁS FINA QUE EL OBJETIVO
 * ====================================================
 * Entre los niveles disponibles se coge el **más fino de los que son más
 * gruesos que el objetivo**, y nunca uno más fino. No es una simplificación:
 *
 * 1. La silueta existe para ser gratis. Un nivel más fino que el objetivo
 *    tiene más cubos que píxeles hay, así que subirlo cuesta más que subir el
 *    dato bueno — se pagaría dos veces por el mismo fotograma y el
 *    presupuesto de §2.6 («sin fotograma > 20 ms») se rompe justo en el gesto
 *    que esto viene a mejorar.
 * 2. Así la marca significa siempre lo mismo: «esto está decimado MÁS de lo
 *    que corresponde». Si a veces la silueta fuera más detallada que el
 *    objetivo, el mismo aviso tendría dos lecturas opuestas y dejaría de
 *    avisar de nada.
 *
 * Y el más fino de entre los gruesos, no el más grueso disponible: pierde
 * menos, y es igual de gratis (ya está en memoria).
 */
export function planificar(
  factorObjetivo: number,
  enMemoria: readonly NivelEnMemoria[],
  visible: Tramo,
): PlanProgresivo {
  const disponibles = nivelesUtilizables(enMemoria, visible);
  if (disponibles.includes(factorObjetivo)) {
    return { tipo: "definitivo", factor: factorObjetivo };
  }
  let mejor: number | null = null;
  for (const factor of disponibles) {
    if (factor > factorObjetivo && (mejor === null || factor < mejor)) mejor = factor;
  }
  if (mejor === null) return { tipo: "a-ciegas", factorObjetivo };
  return { tipo: "silueta", factor: mejor, factorObjetivo };
}

/**
 * Opacidad del trazo provisional.
 *
 * POR QUÉ 0,45 Y POR QUÉ OPACIDAD
 * ===============================
 * El requisito es que **la silueta no se pueda confundir con el dato**. Un
 * trazo provisional idéntico al definitivo es una mentira temporal: alguien
 * puede leer un valor de una curva decimada ×256 creyendo que es la señal, y
 * en una herramienta de tuning eso llega a una decisión de mapa.
 *
 * Las alternativas y por qué no:
 *
 * - **Grosor.** `gl.lineWidth` está clavado a 1 en casi todas las
 *   implementaciones de WebGL2 (la especificación permite que el rango máximo
 *   sea 1, y en la práctica lo es). Engrosar de verdad exige generar geometría
 *   de banda, que es un cambio en el renderizador, y ADR-006 pide no
 *   ampliarlo.
 * - **Otro color.** La paleta ya reparte matiz por índice de canal
 *   (`colorPorIndice`); un color reservado para «provisional» se confundiría
 *   con el color de otro canal en un panel con varias series.
 * - **Discontinuo.** Un trazo a rayas también exige geometría, y encima se
 *   parece a cómo se dibujan los huecos de adquisición (F1-08): dos cosas
 *   distintas con el mismo aspecto.
 *
 * La opacidad, en cambio, es un uniforme: cuesta cero y no mueve ni un
 * vértice, así que la silueta cae exactamente donde caerá el dato definitivo y
 * no hay un salto de geometría al refinar. 0,45 está por debajo del umbral en
 * el que un trazo se lee como «apagado» y sigue siendo visible sobre el fondo
 * oscuro con una GPU integrada.
 *
 * Y la opacidad SOLA no basta: la diferencia entre 1,0 y 0,45 se nota al
 * compararlas, no mirando una sola curva. Por eso la marca lleva además una
 * nota de texto que dice el factor de decimación (`marcaDeSilueta`). Lo que
 * hace que nadie lea mal un número no es que la curva se vea distinta, es que
 * ponga cuánto está decimada.
 */
export const ALFA_SILUETA = 0.45;

/** Cómo se dibuja y cómo se rotula un trazo provisional. */
export interface MarcaSilueta {
  /** El color de la serie con la opacidad de silueta. */
  readonly color: Color;
  /** Texto para el adorno DOM. Vacío nunca: si hay silueta, hay aviso. */
  readonly nota: string;
}

/**
 * El color y el aviso de una silueta.
 *
 * La nota nombra los DOS factores en vez de su cociente: son potencias de 4 y
 * quien lee un log sabe lo que es un ×64, mientras que «4 veces más gruesa»
 * obliga a redondear un cociente que no siempre es entero.
 */
export function marcaDeSilueta(
  color: Color,
  factorSilueta: number,
  factorObjetivo: number,
): MarcaSilueta {
  return {
    color: { ...color, a: color.a * ALFA_SILUETA },
    nota: `silueta ×${factorSilueta} · el detalle de este zoom es ×${factorObjetivo} · refinando…`,
  };
}

/**
 * Una sola línea con las notas de todas las series de un panel, sin repetir.
 *
 * Sin repetir porque el caso normal es que todas las series del panel estén en
 * el mismo nivel: ocho copias del mismo aviso no informan más y desbordan el
 * ancho del panel.
 */
export function notaCombinada(notas: readonly string[]): string {
  return [...new Set(notas.filter((n) => n !== ""))].join("  ·  ");
}

/**
 * Por qué una pasada de refinamiento ya no vale cuando vuelve del backend.
 *
 * - `reconstruccion`: los paneles se rehicieron mientras se esperaba (marcar
 *   un canal, cambiar de unidad). El `EstadoPanel` que la pasada tiene en la
 *   mano está destruido y su `Renderizador` también.
 * - `vista-movida`: los paneles siguen vivos pero el usuario ha seguido
 *   moviéndose, así que ya hay otra pasada encolada con una vista más
 *   reciente. Los cubos que acaban de llegar no son incorrectos, solo son de
 *   otro encuadre.
 */
export type MotivoAbandono = "reconstruccion" | "vista-movida";

export interface EstadoDelRefinamiento {
  /** `#generacion` en el momento de pedir los cubos. */
  readonly generacionAlPedir: number;
  /** `#generacion` ahora, ya con los cubos en la mano. */
  readonly generacionAhora: number;
  /** ¿Hay ya otra pasada de redibujado encolada (`#pendienteOtraVuelta`)? */
  readonly hayPasadaPendiente: boolean;
}

/**
 * ¿Hay que tirar este refinamiento?
 *
 * QUÉ PASA SI EL REFINAMIENTO LLEGA TARDE
 * =======================================
 * Se tira, y **la silueta se queda en pantalla** hasta que la pasada siguiente
 * decida de nuevo. Nadie se queda mirando un hueco: lo peor que puede ocurrir
 * durante un gesto largo es que el trazo siga siendo el provisional, con su
 * aviso puesto, que es exactamente lo que la marca está para decir.
 *
 * Las dos condiciones son el mismo patrón que ya usa `#redibujarUnaVez` —
 * `#generacion` para las reconstrucciones y `#pendienteOtraVuelta` para las
 * vistas encadenadas—, no un mecanismo nuevo. Lo que este módulo añade es
 * distinguirlas, porque **no se responde igual a las dos**: con
 * `reconstruccion` no se puede tocar nada del panel, mientras que con
 * `vista-movida` los cubos recién llegados SÍ deben guardarse en la caché
 * antes de abandonar. Guardarlos es lo que hace que el gesto converja: sin eso
 * un pan continuo volvería a pedir lo mismo una y otra vez y no llegaría nunca
 * al nivel bueno, ni siquiera al parar.
 */
export function motivoDeAbandono(estado: EstadoDelRefinamiento): MotivoAbandono | null {
  if (estado.generacionAlPedir !== estado.generacionAhora) return "reconstruccion";
  if (estado.hayPasadaPendiente) return "vista-movida";
  return null;
}
