/**
 * La aplicación ENTERA montada en Node, con el doble de `dom/doble-documento.ts`.
 *
 * QUÉ PROTEGE ESTO Y POR QUÉ NO EXISTÍA
 * =====================================
 * `Aplicacion` usaba `document`, `window` y `Renderizador.desdeLienzo`
 * globales, así que no se podía construir sin navegador y **ninguna prueba
 * ejecutaba una sola línea del ensamblado**. Los tres fallos que siguen los
 * encontró el propietario abriendo la ventana, uno detrás de otro, y los tres
 * eran del mismo tipo: un valor leído demasiado pronto y guardado en una
 * variable. `tsc` no ve eso, y `pytest` se detiene en el backend.
 *
 * Cada `it` de este fichero es uno de esos fallos.
 */

import { describe, expect, it } from "vitest";

import { Aplicacion, type EntornoApp } from "./aplicacion.ts";
import { crearDocumentoFalso, crearVentanaFalsa, type ElementoFalso } from "../dom/doble-documento.ts";
import { crearDobleGL, type DobleGL } from "../render/doble-gl.ts";
import { ALFA_SILUETA } from "../render/progresivo.ts";
import { Renderizador } from "../render/renderizador.ts";
import type { CubosContinuos } from "../render/tipos.ts";
import type { Rango } from "../datos/cache-cubos.ts";
import type {
  CanalDeFuente,
  FuenteDeDatos,
  LogAbierto,
  ResumenNivelFuente,
} from "../datos/fuente.ts";
import type { CatalogoUnidades } from "../unidades/tipos.ts";

// --------------------------------------------------------------------------- //
// Una fuente mínima con los dos canales que hacen falta para el caso real
// --------------------------------------------------------------------------- //
// `Coolant Temperature` con escalado de canal 0,1 (el del AutoLog de verdad,
// comprobado contra `/comandos/abrir-log`) y `RPM` con 1,0. Los dos devuelven
// el MISMO valor crudo, 3748, para que un número equivocado no se pueda
// confundir con otra cosa: 3748 con 0,1 son 374,8 K = 101,65 °C.
const CRUDO = 3748;

function cubos(): CubosContinuos {
  const n = 4;
  const t = new Float32Array(n);
  const v = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = i;
    v[i] = CRUDO;
  }
  return { t, tOrigen: 0, minimo: v, maximo: v, primero: v, ultimo: v, factor: 1 };
}

const CANALES: CanalDeFuente[] = [
  {
    idNativo: "705",
    nombre: "Coolant Temperature",
    rol: "coolant_temp",
    confianzaRol: "EXACTA",
    dimensionId: "temperature",
    clasificacion: { vacio: false, constante: false },
    aCanonica: { a: 0.1, b: 0 },
  },
  {
    idNativo: "0",
    nombre: "RPM",
    rol: "engine_speed",
    confianzaRol: "EXACTA",
    dimensionId: "angular_speed",
    clasificacion: { vacio: false, constante: false },
    aCanonica: { a: 1, b: 0 },
  },
];

const CATALOGO: CatalogoUnidades = {
  dimensiones: [
    {
      id: "temperature",
      etiqueta: "Temperatura",
      unidadCanonica: "K",
      convertible: true,
      unidades: [
        { id: "K", etiqueta: "K", decimales: 1, conversion: { tipo: "afin", a: 1, b: 0 } },
        { id: "degC", etiqueta: "°C", decimales: 2, conversion: { tipo: "afin", a: 1, b: -273.15 } },
      ],
    },
    {
      id: "angular_speed",
      etiqueta: "Régimen",
      unidadCanonica: "rpm",
      convertible: true,
      unidades: [
        { id: "rpm", etiqueta: "rpm", decimales: 0, conversion: { tipo: "afin", a: 1, b: 0 } },
        {
          id: "rad/s",
          etiqueta: "rad/s",
          decimales: 2,
          conversion: { tipo: "afin", a: 0.10471975512, b: 0 },
        },
      ],
    },
  ],
  presets: [{ id: "metrico", etiqueta: "Métrico", unidades: { temperature: "K" } }],
  presetPorOmision: "metrico",
  combustibles: [],
};

class FuenteDePrueba implements FuenteDeDatos {
  readonly nombre = "prueba";

  abrirLog(referencia: string): Promise<LogAbierto> {
    return Promise.resolve({
      logId: "log-1",
      nombre: referencia,
      tInicio: 0,
      tFin: 4,
      canales: CANALES,
      avisos: [],
    });
  }

  cerrarLog(): void {}

  catalogoUnidades(): Promise<CatalogoUnidades> {
    return Promise.resolve(CATALOGO);
  }

  nivelesDe(): Promise<readonly ResumenNivelFuente[]> {
    return Promise.resolve([{ factor: 1, nCubos: 4 }]);
  }

  pedirCubos(_logId: string, _canalId: string, _rango: Rango, _factor: number): Promise<CubosContinuos> {
    return Promise.resolve(cubos());
  }
}

// --------------------------------------------------------------------------- //
// Montaje
// --------------------------------------------------------------------------- //
interface Montaje {
  readonly raiz: ElementoFalso;
  readonly ventana: ReturnType<typeof crearVentanaFalsa>;
  readonly app: Aplicacion;
}

async function montar(): Promise<Montaje> {
  const documento = crearDocumentoFalso();
  const ventana = crearVentanaFalsa();
  const raiz = documento.createElement("div");
  const entorno: EntornoApp = {
    documento: documento as unknown as Pick<Document, "createElement" | "createElementNS">,
    ventana,
    // `Renderizador` acepta un `ContextoGL` por constructor justamente para
    // esto: el doble de WebGL2 ya existía (`render/doble-gl.ts`), y es el
    // motivo por el que jsdom no habría servido — no implementa WebGL.
    crearRenderizador: () => new Renderizador(crearDobleGL()),
  };
  const app = new Aplicacion(raiz as unknown as HTMLElement, new FuenteDePrueba(), entorno);
  await app.abrirLog("log-de-prueba");
  await asentar(ventana);
  // Node no calcula layout: sin geometria, `anchoContenidoPx()` es 0 y la
  // fraccion del cursor sale indefinida.
  darGeometria(raiz);
  moverCursor(raiz, 400);
  await asentar(ventana);
  return { raiz, ventana, app };
}

/**
 * Deja que el redibujado termine.
 *
 * `#dispararRedibujado` lanza una promesa que nadie espera (`void
 * this.#redibujarTodo().catch(...)`), asi que no hay nada que await-ear desde
 * fuera: se alternan vueltas de macrotarea --que vacian la cola de
 * microtareas de `pedirCubos`-- con fotogramas, que es lo que escribe la tabla
 * del cursor (`cursor.aplicar()`).
 */
async function asentar(
  ventana: ReturnType<typeof crearVentanaFalsa>,
  vueltas = 12,
): Promise<void> {
  for (let i = 0; i < vueltas; i += 1) {
    await new Promise((listo) => setTimeout(listo, 0));
    ventana.correrFotogramas(1);
  }
}

/** Un rectangulo de 800x200 a todo el arbol: Node no puede calcular layout. */
function darGeometria(nodo: ElementoFalso): void {
  nodo.fijarRectangulo({ top: 0, bottom: 200, left: 0, right: 800, width: 800, height: 200 });
  for (const h of nodo.hijos) darGeometria(h);
}

/**
 * Mueve el cursor sobre el area de paneles.
 *
 * Sin esto la tabla del cursor se queda con las celdas vacias: `aplicar()`
 * solo escribe si hay un instante pendiente de `mover()`, y `mover()` lo
 * dispara un `pointermove` de verdad. Es exactamente la parte que ninguna
 * prueba ejercitaba.
 */
function moverCursor(raiz: ElementoFalso, xPixel: number): void {
  const area = raiz.buscarPorClase("dlv-principal");
  if (area === null) throw new Error("no se encontro el area principal");
  area.disparar("pointermove", { clientX: xPixel, clientY: 50 });
}

/**
 * Lo que la tabla del cursor ensena: rotulo de canal -> valor.
 *
 * Se lee por FILAS y no buscando una subcadena en todo el arbol, porque los
 * dos canales de esta prueba comparten el valor crudo 3748 a proposito: una
 * asercion sobre el arbol entero no distinguiria «RPM ensena 3748, que es
 * correcto» de «el refrigerante ensena 3748, que es el fallo».
 */
function tablaDelCursor(raiz: ElementoFalso): Map<string, string> {
  const leido = new Map<string, string>();
  for (const tabla of raiz.buscarTodosPorClase("cursor-tabla")) {
    for (const fila of buscarTodos(tabla, "tr")) {
      const celdas = buscarTodos(fila, "td");
      const rotulo = celdas[0]?.textContent ?? "";
      const valor = celdas[1]?.textContent ?? "";
      if (rotulo !== "") leido.set(rotulo, valor);
    }
  }
  return leido;
}

/**
 * El `<select>` mas especifico que ofrece la unidad `valorOpcion`.
 *
 * No se busca por posicion: `SelectorUnidad` pinta tres capas (preset global,
 * dimension, canal) y el orden depende de cuantos canales haya, asi que un
 * indice fijo apuntaria a otro control en cuanto cambie la lista. Se coge el
 * ULTIMO que ofrezca esa unidad, que es la capa de canal — la que gana.
 */
function selectConOpcion(raiz: ElementoFalso, valorOpcion: string): ElementoFalso {
  const candidatos = buscarTodos(raiz, "select").filter((s) =>
    buscarTodos(s, "option").some((o) => o.value === valorOpcion),
  );
  const select = candidatos[candidatos.length - 1];
  if (select === undefined) {
    throw new Error(`ningun <select> ofrece la unidad «${valorOpcion}»`);
  }
  return select;
}

function buscarTodos(nodo: ElementoFalso, etiqueta: string): ElementoFalso[] {
  const encontrados: ElementoFalso[] = [];
  const visitar = (n: ElementoFalso): void => {
    if (n.etiqueta === etiqueta) encontrados.push(n);
    for (const h of n.hijos) visitar(h);
  };
  visitar(nodo);
  return encontrados;
}

// --------------------------------------------------------------------------- //
// Los tres fallos
// --------------------------------------------------------------------------- //
describe("la aplicación montada de extremo a extremo", () => {
  it("se construye y abre un log sin reventar", async () => {
    // Esta sola línea no existía: `Aplicacion` no se podía instanciar en Node,
    // así que una excepción en el montaje solo aparecía en la ventana.
    const { raiz } = await montar();
    expect(raiz.classList.contains("dlv-app")).toBe(true);
    expect(raiz.textoDelArbol()).toContain("Coolant Temperature");
  });

  it("aplica el escalado del canal: 3748 crudo son 374,8 K, no 3748", async () => {
    // El fallo del factor de diez. Con `to_canon` a=0,1 y unidad canónica K,
    // la fila del refrigerante tiene que enseñar 374,8 y no el entero crudo.
    const { raiz } = await montar();
    expect(tablaDelCursor(raiz).get("Coolant Temperature (K)")).toBe("374,8");
  });

  it("la tabla del cursor rotula con el NOMBRE del canal y su unidad, no con el id", async () => {
    const { raiz } = await montar();
    const texto = raiz.textoDelArbol();
    expect(texto).toContain("Coolant Temperature (K)");
    // «705» era el id nativo que se enseñaba antes en su lugar.
    expect(texto).not.toContain("705");
  });

  it("al cambiar de unidad cambian A LA VEZ el número y la etiqueta", async () => {
    // El fallo de la unidad congelada: la conversión se recalculaba en cada
    // repintado, pero la etiqueta se había guardado al crear el panel, así que
    // se veía «101,65» con una «K» al lado.
    const { raiz, ventana } = await montar();
    expect(tablaDelCursor(raiz).get("Coolant Temperature (K)")).toBe("374,8");

    const select = selectConOpcion(raiz, "degC");
    select.value = "degC";
    select.disparar("change", { target: select });
    // El redibujado es asíncrono (pide cubos a la fuente); dos vueltas de
    // microtareas y un par de fotogramas bastan con una fuente en memoria.
    await asentar(ventana);

    const tabla = tablaDelCursor(raiz);
    // El numero Y el rotulo, a la vez. Antes el numero cambiaba y el rotulo no.
    expect(tabla.get("Coolant Temperature (°C)")).toBe("101,65");
    expect(tabla.has("Coolant Temperature (K)")).toBe(false);
    // Y el titulo del eje, que salia del mismo valor capturado.
    expect(raiz.textoDelArbol()).toContain("°C (autoescala)");
  });

  it("dos canales con escalados distintos no se convierten con el mismo factor", async () => {
    // Los dos canales traen el mismo valor crudo (3748) y escalados 0,1 y 1,0,
    // así que tienen que salir números distintos: 374,8 K y 3748 rpm. Atrapa
    // cualquier conversión compartida entre paneles.
    //
    // LO QUE ESTA PRUEBA NO ALCANZA, Y CONVIENE SABERLO
    // ================================================
    // El tercer fallo era un `formatear` único por PANEL, atado a su primer
    // canal. Aquí no se manifiesta: la aplicación crea un panel por canal
    // seleccionado, así que «el primero del panel» y «el de la fila» son el
    // mismo. Solo se separan cuando el usuario arrastra dos canales al mismo
    // panel, y simular ese arrastre exige conducir los eventos de puntero de
    // `PanelesApilados`. Ese caso lo cubre `cursor/cursor.test.ts` («cada fila
    // se convierte con los factores de SU canal»), que ataca la misma costura
    // un nivel más abajo. Se comprobó volviendo a introducir el fallo: esta
    // prueba seguía verde y la de `cursor.test.ts` fallaba.
    const { raiz } = await montar();
    const tabla = tablaDelCursor(raiz);
    // Mismo valor crudo (3748), escalados 0,1 y 1,0: números distintos.
    expect(tabla.get("Coolant Temperature (K)")).toBe("374,8");
    expect(tabla.get("RPM (rpm)")).toBe("3748");
  });
});

// --------------------------------------------------------------------------- //
// F2-14 — renderizado progresivo: silueta inmediata, refinamiento de fondo
// --------------------------------------------------------------------------- //
// Aquí no basta con montar: hay que CONDUCIR un gesto (rueda) y retener la
// respuesta del backend, porque lo que esta tarea cambia solo existe en el
// hueco entre el gesto y la llegada de los cubos. Con una fuente que contesta
// al instante ese hueco no se puede observar, y es exactamente el hueco en el
// que antes no se dibujaba nada.

/**
 * Pirámide de cuatro niveles sobre un log de 64 s, elegida para que el zoom
 * CAMBIE de nivel con un panel de 800 px:
 *
 * - con el log entero a la vista, el nivel más barato que da un cubo por píxel
 *   es el de 1 000 cubos → ×64;
 * - al ampliar ~3,3×, ese nivel se queda en 300 cubos visibles y hay que bajar
 *   al de 4 000 → ×16.
 *
 * Sin ese salto no hay nada que refinar y la prueba pasaría sin probar nada.
 */
const NIVELES_PIRAMIDE: readonly ResumenNivelFuente[] = [
  { factor: 1, nCubos: 64_000 },
  { factor: 16, nCubos: 4_000 },
  { factor: 64, nCubos: 1_000 },
  { factor: 256, nCubos: 250 },
];

const CANAL_UNICO: CanalDeFuente[] = [
  {
    idNativo: "0",
    nombre: "RPM",
    rol: "engine_speed",
    confianzaRol: "EXACTA",
    dimensionId: "angular_speed",
    clasificacion: { vacio: false, constante: false },
    aCanonica: { a: 1, b: 0 },
  },
];

function cubosDe(rango: Rango, factor: number): CubosContinuos {
  const n = 8;
  const t = new Float32Array(n);
  const v = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    t[i] = (i * (rango.t1 - rango.t0)) / (n - 1);
    v[i] = 1000 + i * 100;
  }
  return { t, tOrigen: rango.t0, minimo: v, maximo: v, primero: v, ultimo: v, factor };
}

/** Una fuente que puede quedarse callada, que es lo que hace observable la silueta. */
class FuenteConEspera implements FuenteDeDatos {
  readonly nombre = "prueba-progresiva";
  /** Cuando está puesto, `pedirCubos` no contesta hasta `soltar()`. */
  retener = false;
  readonly pedidos: Array<{ canal: string; factor: number }> = [];
  #pendientes: Array<() => void> = [];

  abrirLog(referencia: string): Promise<LogAbierto> {
    return Promise.resolve({
      logId: "log-1",
      nombre: referencia,
      tInicio: 0,
      tFin: 64,
      canales: CANAL_UNICO,
      avisos: [],
    });
  }

  cerrarLog(): void {}

  catalogoUnidades(): Promise<CatalogoUnidades> {
    return Promise.resolve(CATALOGO);
  }

  nivelesDe(): Promise<readonly ResumenNivelFuente[]> {
    return Promise.resolve(NIVELES_PIRAMIDE);
  }

  pedirCubos(
    _logId: string,
    canalId: string,
    rango: Rango,
    factor: number,
  ): Promise<CubosContinuos> {
    this.pedidos.push({ canal: canalId, factor });
    const cubos = cubosDe(rango, factor);
    if (!this.retener) return Promise.resolve(cubos);
    return new Promise((listo) => {
      this.#pendientes.push(() => listo(cubos));
    });
  }

  /** Contesta a todo lo retenido y deja de retener. */
  soltar(): void {
    this.retener = false;
    const cola = this.#pendientes;
    this.#pendientes = [];
    for (const contestar of cola) contestar();
  }
}

interface MontajeProgresivo {
  readonly raiz: ElementoFalso;
  readonly ventana: ReturnType<typeof crearVentanaFalsa>;
  readonly fuente: FuenteConEspera;
  readonly gl: DobleGL[];
}

async function montarProgresivo(): Promise<MontajeProgresivo> {
  const documento = crearDocumentoFalso();
  const ventana = crearVentanaFalsa();
  const raiz = documento.createElement("div");
  const fuente = new FuenteConEspera();
  const gl: DobleGL[] = [];
  const entorno: EntornoApp = {
    documento: documento as unknown as Pick<Document, "createElement" | "createElementNS">,
    ventana,
    crearRenderizador: () => {
      const doble = crearDobleGL();
      gl.push(doble);
      return new Renderizador(doble);
    },
  };
  const app = new Aplicacion(raiz as unknown as HTMLElement, fuente, entorno);
  await app.abrirLog("log-de-prueba");
  await asentar(ventana);
  darGeometria(raiz);
  // El primer redibujado corrió con el panel a 0 px de ancho (Node no calcula
  // layout), así que eligió el nivel más barato de todos. Un `resize` con la
  // geometría ya puesta deja la aplicación en el estado del que parte la
  // prueba: el log entero a la vista, con SU nivel y sin nada provisional.
  ventana.disparar("resize");
  await asentar(ventana);
  return { raiz, ventana, fuente, gl };
}

/** El texto del aviso de silueta del primer (y único) panel. */
function notaDeSilueta(raiz: ElementoFalso): string {
  return raiz.buscarPorClase("dlv-nota-silueta")?.textContent ?? "(no hay nota)";
}

/** Rueda sobre el área de paneles: `deltaY` negativo amplía (`controlador.ts`). */
function rueda(raiz: ElementoFalso, deltaY: number): void {
  const paneles = raiz.buscarPorClase("dlv-paneles");
  if (paneles === null) throw new Error("no se encontró el contenedor de paneles");
  paneles.disparar("wheel", { deltaY, clientX: 400, clientY: 100, preventDefault: () => {} });
}

/**
 * Las opacidades con las que se pintó cada serie, en orden.
 *
 * El uniforme de color es el único `uniform4f` cuyos tres primeros componentes
 * están en [0, 1]: el de la transformación lleva escalas y desplazamientos de
 * recorte, que se salen de ese rango en cuanto la vista no es exactamente
 * [-1, 1] — y en estas pruebas nunca lo es.
 */
function alfasDibujadas(gl: DobleGL): number[] {
  return gl.llamadas
    .filter((l) => l.nombre === "uniform4f")
    .map((l) => l.argumentos.slice(1) as number[])
    .filter((a) => a.slice(0, 3).every((c) => c >= 0 && c <= 1))
    .map((a) => a[3]!);
}

describe("renderizado progresivo (F2-14)", () => {
  it("con el nivel bueno ya en memoria no hay ningún aviso", async () => {
    const { raiz } = await montarProgresivo();
    expect(notaDeSilueta(raiz)).toBe("");
  });

  it("al ampliar dibuja la silueta EN EL MISMO TURNO, sin esperar al backend", async () => {
    const { raiz, ventana, fuente, gl } = await montarProgresivo();
    fuente.retener = true;
    gl[0]!.olvidar();
    const pedidosAntes = fuente.pedidos.length;

    rueda(raiz, -800);
    // Un solo fotograma y ni un `await`: si la silueta necesitara una vuelta
    // del bucle de eventos, esta prueba se pondría roja, y ese aplazamiento es
    // justo lo que se ve como «la pantalla no responde al gesto».
    ventana.correrFotogramas(1);

    // Ni siquiera se ha PEDIDO nada todavía: la fase 2 vive detrás de un
    // `await`, así que a estas alturas del turno la petición del nivel bueno
    // aún no ha salido. Esa es la medida exacta de «inmediato».
    expect(fuente.pedidos).toHaveLength(pedidosAntes);
    const nota = notaDeSilueta(raiz);
    expect(nota).toContain("silueta ×64");
    expect(nota).toContain("×16");
    // Y se ha dibujado de verdad, con la opacidad de silueta: la nota sola no
    // demuestra que en el lienzo haya algo.
    expect(alfasDibujadas(gl[0]!)).toContain(ALFA_SILUETA);
  });

  it("cuando llegan los cubos buenos, el trazo se vuelve opaco y el aviso desaparece", async () => {
    const { raiz, ventana, fuente, gl } = await montarProgresivo();
    fuente.retener = true;
    rueda(raiz, -800);
    ventana.correrFotogramas(1);
    expect(notaDeSilueta(raiz)).not.toBe("");

    gl[0]!.olvidar();
    fuente.soltar();
    await asentar(ventana);

    expect(notaDeSilueta(raiz)).toBe("");
    expect(alfasDibujadas(gl[0]!)).toContain(1);
    expect(alfasDibujadas(gl[0]!)).not.toContain(ALFA_SILUETA);
    // Y lo que se pidió fue el nivel que corresponde al zoom nuevo, no otro.
    expect(fuente.pedidos.at(-1)!.factor).toBe(16);
  });

  it("un refinamiento que llega tarde no se tira: se guarda y el gesto converge", async () => {
    // El usuario sigue moviéndose mientras el backend contesta. La pasada vieja
    // se abandona (`motivoDeAbandono` → «vista-movida»), pero sus cubos quedan
    // en la caché: si se tiraran, la pasada nueva volvería a pedir lo mismo y
    // un gesto largo no llegaría nunca al nivel bueno.
    const { raiz, ventana, fuente } = await montarProgresivo();
    fuente.retener = true;

    rueda(raiz, -800);
    ventana.correrFotogramas(1);
    // Segundo gesto, más corto, mientras el primero sigue en vuelo: amplía un
    // poco más sin cambiar de nivel de pirámide.
    rueda(raiz, -100);
    ventana.correrFotogramas(1);
    // Mientras tanto se sigue viendo algo, no un hueco.
    expect(notaDeSilueta(raiz)).toContain("silueta ×64");

    fuente.soltar();
    await asentar(ventana);

    expect(notaDeSilueta(raiz)).toBe("");
    const peticionesDelNivelBueno = fuente.pedidos.filter((p) => p.factor === 16);
    expect(peticionesDelNivelBueno).toHaveLength(1);
  });
});
