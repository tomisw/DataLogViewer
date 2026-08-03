/**
 * Aritmética pura del reparto de alto entre paneles (F1-26).
 *
 * Separado de `paneles.ts` por la misma razón que `ejes/geometria.ts` está
 * separado de `ejes/ejes.ts`: esto se prueba en Node sin abrir un navegador,
 * y `paneles.ts` es la fontanería de `document.createElement` que solo copia
 * estos números a `style.height`. Ninguna función de aquí mide el DOM: reciben
 * y devuelven píxeles ya conocidos.
 *
 * Invariante que protegen las pruebas de este módulo, y que es la mitad
 * "vertical" del requisito de la tarea (redimensionable, mínimo por panel):
 * la suma de las alturas devueltas es exactamente la altura total pedida, sin
 * huecos ni solapes por redondeo — un céntimo de píxel perdido en cada
 * arrastre no se nota en una sesión, pero sí en cien.
 */

/**
 * Reparte `alturaTotalPx` a partes iguales entre `ids.length` paneles.
 *
 * Igual y no proporcional a algo más porque F1-26 no pide pesos por panel —
 * si algún día hiciera falta un reparto inicial distinto, es una tarea nueva,
 * no un parámetro oculto aquí. El resto de la división entera se lo lleva el
 * último panel: así la suma da exactamente `alturaTotalPx` sin depender de
 * qué tan bien divida `ids.length`.
 *
 * Si `alturaTotalPx` no alcanza para dar `alturaMinimaPx` a cada panel, se
 * reparte igual y se deja que el llamador decida (el contenedor es más
 * pequeño que `ids.length * alturaMinimaPx`, un problema de configuración de
 * quien monta el componente, no de esta función — ver la nota de
 * `arrastrarDivisor` sobre el mismo límite).
 */
export function repartirAlturasIniciales(
  ids: readonly string[],
  alturaTotalPx: number,
  alturaMinimaPx: number,
): Map<string, number> {
  const resultado = new Map<string, number>();
  if (ids.length === 0) return resultado;

  const totalUtil = Math.max(alturaTotalPx, alturaMinimaPx * ids.length);
  const base = Math.floor(totalUtil / ids.length);
  let acumulado = 0;
  ids.forEach((id, indice) => {
    if (indice === ids.length - 1) {
      resultado.set(id, totalUtil - acumulado);
    } else {
      resultado.set(id, base);
      acumulado += base;
    }
  });
  return resultado;
}

/** Resultado de arrastrar el divisor entre dos paneles adyacentes. */
export interface ResultadoArrastreDivisor {
  readonly alturaSuperiorPx: number;
  readonly alturaInferiorPx: number;
}

/**
 * Recalcula el alto de dos paneles adyacentes al arrastrar `deltaPx` el
 * divisor que los separa (positivo = hacia abajo, crece el superior).
 *
 * El total de los dos se conserva siempre — `alturaSuperiorPx +
 * alturaInferiorPx` de la entrada es igual a la suma de la salida — porque un
 * divisor solo redistribuye entre sus dos vecinos: cambiar el alto de un
 * tercer panel sin que el usuario lo haya tocado sería la clase de sorpresa
 * que rompe la confianza en "lo que arrastro es lo que cambia".
 *
 * Si el conjunto de los dos paneles es menor que `2 * alturaMinimaPx` (el
 * contenedor es demasiado pequeño para el número de paneles configurado), no
 * hay forma de dar el mínimo a los dos a la vez; se le da el mínimo al
 * superior y el resto —posiblemente por debajo del mínimo— al inferior. Es un
 * límite físico, no un defecto de esta función.
 */
export function arrastrarDivisor(
  alturaSuperiorPx: number,
  alturaInferiorPx: number,
  deltaPx: number,
  alturaMinimaPx: number,
): ResultadoArrastreDivisor {
  const total = alturaSuperiorPx + alturaInferiorPx;
  const superiorSinClamp = alturaSuperiorPx + deltaPx;
  const superior = Math.min(Math.max(superiorSinClamp, alturaMinimaPx), Math.max(total - alturaMinimaPx, alturaMinimaPx));
  return {
    alturaSuperiorPx: superior,
    alturaInferiorPx: total - superior,
  };
}

/**
 * Reescala todas las alturas a un nuevo total (el contenedor cambió de
 * tamaño), conservando las proporciones relativas y garantizando que:
 *
 *   1. la suma exacta es `nuevoTotalPx` (sin resto perdido: se lo lleva el
 *      último panel del orden dado), y
 *   2. ningún panel queda por debajo de `alturaMinimaPx` salvo que
 *      `nuevoTotalPx` sea físicamente insuficiente para todos (mismo límite
 *      que en `arrastrarDivisor`).
 *
 * `orden` fija qué panel se lleva el resto de redondeo; tiene que ser el
 * mismo orden en cada llamada para que el reparto no "salte" de panel al
 * repetir el cálculo con números casi iguales.
 */
export function reescalarAlturas(
  alturasPx: ReadonlyMap<string, number>,
  orden: readonly string[],
  nuevoTotalPx: number,
  alturaMinimaPx: number,
): Map<string, number> {
  if (orden.length === 0) return new Map();

  const totalUtil = Math.max(nuevoTotalPx, alturaMinimaPx * orden.length);
  const pesos = new Map(orden.map((id) => [id, Math.max(0, alturasPx.get(id) ?? 0)] as const));

  // "Water-filling": el reparto proporcional simple (peso / pesoTotal *
  // total) puede dejar a un panel con mucho peso por debajo del mínimo si
  // otro se llevó casi todo el alto original. Corregirlo con un "último
  // panel absorbe el resto" (como en `repartirAlturasIniciales`) no basta
  // aquí porque ese resto puede ser negativo y tirar a ESE panel por debajo
  // del mínimo — es justo el caso que hizo falta esta función en vez de la
  // fórmula de una línea. En su lugar: se fija en el mínimo a quien no
  // llegue a él y se reparte el resto, proporcionalmente, solo entre los que
  // quedan libres; se repite hasta que nadie más quede por debajo. Como
  // mucho `orden.length` pasadas —cada una fija al menos un panel más—, y
  // termina en el peor caso con todos fijados al mínimo (el límite físico
  // que documenta la cabecera del módulo).
  const fijados = new Map<string, number>();
  let libres = [...orden];

  for (;;) {
    const totalFijado = [...fijados.values()].reduce((suma, valor) => suma + valor, 0);
    const restante = totalUtil - totalFijado;
    const pesoRestante = libres.reduce((suma, id) => suma + (pesos.get(id) ?? 0), 0);

    const compartidoDe = (id: string): number => {
      const peso = pesos.get(id) ?? 0;
      return pesoRestante > 0 ? (peso / pesoRestante) * restante : restante / libres.length;
    };

    const bajoMinimo = libres.filter((id) => compartidoDe(id) < alturaMinimaPx);
    if (bajoMinimo.length === 0) {
      // Todos los libres caben con su reparto proporcional: se les asigna, y
      // el último (en el orden original) se lleva el resto de redondeo para
      // que la suma cuadre exacta con `totalUtil`.
      let asignado = 0;
      libres.forEach((id, indice) => {
        const valor = indice === libres.length - 1 ? restante - asignado : compartidoDe(id);
        fijados.set(id, valor);
        asignado += valor;
      });
      break;
    }

    for (const id of bajoMinimo) fijados.set(id, alturaMinimaPx);
    libres = libres.filter((id) => !bajoMinimo.includes(id));
    if (libres.length === 0) break;
  }

  const resultado = new Map<string, number>();
  for (const id of orden) resultado.set(id, fijados.get(id) ?? alturaMinimaPx);
  return resultado;
}

/** Suma de un conjunto de alturas. Utilidad pequeña, pero repetida en pruebas y en `paneles.ts`. */
export function alturaTotal(alturasPx: ReadonlyMap<string, number>): number {
  let suma = 0;
  for (const valor of alturasPx.values()) suma += valor;
  return suma;
}
