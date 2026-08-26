/**
 * Editar un `LimiteDeAlerta` en la unidad ACTIVA, guardándolo en CANÓNICA
 * (F3-05, decisión 4 del informe de la tarea; `docs/06` §6.11).
 *
 * DOS CAMPOS, DOS CLASES, Y ES FÁCIL CONFUNDIRLAS
 * ==================================================
 * Un tope (`Tope.valor`) es un valor ABSOLUTO del canal — 120 °C, 900 kPa — y
 * se convierte como `Clase.PUNTO`: la conversión completa, con el
 * desplazamiento de origen incluido si la unidad lo tiene (°C/K).
 *
 * El ANCHO de una banda es otra cosa. Cuando este editor presenta una banda
 * como "centro ± semiancho" (más cómodo de teclear que "mínimo" y "máximo"
 * sueltos, y es como se piensa una banda de λ objetivo: "0,85 ± 0,05"), el
 * CENTRO es un valor absoluto (PUNTO, con desplazamiento) pero el SEMIANCHO es
 * una DIFERENCIA entre dos valores absolutos (INTERVALO, sin desplazamiento).
 * Convertir el semiancho como PUNTO sería la misma trampa que
 * `unidades/conversion.ts` ya documenta para un Δ de temperatura: un
 * desplazamiento de origen que no debería aplicarse se cuela y el ancho sale
 * mal en cualquier unidad con `b != 0`. Por eso `bandaAMostrada`/
 * `bandaDesdeMostrada` llaman a `convertirValor`/`aCanonica` con
 * `"punto"` para el centro y `"intervalo"` para el semiancho — dos llamadas
 * con dos clases, nunca una conversión reutilizada para las dos.
 *
 * SOLO SE EDITAN TOPES Y BANDAS PLANOS
 * ========================================
 * Un tope en curva (D10: presión de aceite mínima en función del régimen) no
 * tiene un único "valor" que mostrar en un campo numérico — depende de una
 * serie de otro rol que este editor no lee (eso es F3-06/F3-07, el motor de
 * detectores). Editarlo aquí sería inventar una interacción a medias; se
 * enseña de forma legible pero no editable, con `topeEsEditable`/
 * `bandaEsEditable` decidiendo qué controles pinta `editor-perfil.ts`.
 */

import { admiteClase, aCanonica, convertirValor, type Conversion } from "../unidades/conversion.ts";
import type { LimiteDeAlerta, NivelDeTope, Tope, TopeDeBanda } from "./perfil.ts";
import { construirLimiteDeAlerta, construirTope, esCurva } from "./perfil.ts";

export class ErrorDeEdicionDeUmbral extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeEdicionDeUmbral";
  }
}

/** Un tope en curva no tiene un valor plano que editar en un campo numérico. */
export function topeEsEditable(tope: Tope): boolean {
  return !esCurva(tope.valor);
}

export function bandaEsEditable(banda: TopeDeBanda): boolean {
  return !esCurva(banda.minimo) && !esCurva(banda.maximo);
}

/** El valor de un tope plano, convertido a la unidad activa. Clase PUNTO: es absoluto. */
export function valorDeTopeMostrado(tope: Tope, conversion: Conversion, parametro?: number): number {
  if (esCurva(tope.valor)) {
    throw new ErrorDeEdicionDeUmbral(
      "este tope es una curva en función de otro rol: no tiene un valor único que mostrar " +
        "(edítalo en el fichero .dlvprofile; este editor todavía no representa curvas)",
    );
  }
  return convertirValor(tope.valor, conversion, "punto", parametro);
}

/**
 * Un `LimiteDeAlerta` con el tope de `nivel` sustituido por `valorMostrado`
 * (en la unidad activa, ya convertida a canónica). Vuelve a construir el
 * límite entero con `construirLimiteDeAlerta`, así que si el nuevo valor deja
 * el aviso por detrás del crítico, el error real de `perfil.py`
 * (`validar_pareja`, mismo mensaje que el mirror de este proyecto) sale tal
 * cual — no se silencia ni se sustituye por uno genérico, mismo criterio que
 * la decisión 2 de esta tarea para la importación.
 */
export function actualizarValorDeTope(
  limite: LimiteDeAlerta,
  nivel: NivelDeTope,
  valorMostrado: number,
  conversion: Conversion,
  parametro?: number,
): LimiteDeAlerta {
  const actual = limite.topes.find((t) => t.nivel === nivel);
  if (actual === undefined) {
    throw new ErrorDeEdicionDeUmbral(`el límite del rol '${limite.rol}' no tiene un tope de nivel '${nivel}'`);
  }
  if (esCurva(actual.valor)) {
    throw new ErrorDeEdicionDeUmbral(
      `el tope '${nivel}' del rol '${limite.rol}' es una curva: no se edita con un valor plano`,
    );
  }
  const nuevoValor = aCanonica(valorMostrado, conversion, "punto", parametro);
  const nuevoTope = construirTope({ ...actual, valor: nuevoValor });
  const topes = limite.topes.map((t) => (t.nivel === nivel ? nuevoTope : t));
  return construirLimiteDeAlerta({ rol: limite.rol, topes, banda: limite.banda });
}

/** Una banda en la unidad activa, como par mínimo/máximo. Los dos son PUNTO: valores absolutos. */
export interface BandaMinMaxMostrada {
  readonly minimo: number;
  readonly maximo: number;
}

export function bandaAMinMaxMostrado(banda: TopeDeBanda, conversion: Conversion, parametro?: number): BandaMinMaxMostrada {
  if (esCurva(banda.minimo) || esCurva(banda.maximo)) {
    throw new ErrorDeEdicionDeUmbral("esta banda tiene un borde en curva: no se edita con valores planos");
  }
  const a = convertirValor(banda.minimo, conversion, "punto", parametro);
  const b = convertirValor(banda.maximo, conversion, "punto", parametro);
  // UNA RECIPROCA INVIERTE EL ORDEN: `a/x` es decreciente, asi que el minimo
  // en canonica es el MAXIMO en la unidad mostrada. Con lambda 0,80..0,90, en
  // phi salen 1,25 y 1,11 -- devolverlos en el mismo orden pondria un minimo
  // MAYOR que su maximo en los dos campos del editor, y el usuario estaria
  // corrigiendo una banda invertida sin que nada se lo dijera.
  //
  // Es la misma inversion que `malla/geometria.ts` ya resuelve al pintar cubos
  // con una unidad reciproca (F4-04). Se ordena aqui, y no en quien pinta,
  // porque estos dos numeros van directos a dos campos rotulados «minimo» y
  // «maximo»: el rotulo tiene que ser cierto.
  return { minimo: Math.min(a, b), maximo: Math.max(a, b) };
}

/**
 * Actualiza una banda editando mínimo y máximo por separado, cada uno como
 * PUNTO. Es el camino que funciona SIEMPRE, incluida una dimensión con
 * conversión recíproca (λ↔φ): `admiteClase` prohíbe convertir un INTERVALO en
 * una recíproca porque no es lineal, así que "centro y semiancho" no está
 * disponible ahí y este es el único modo (`bandaEsEditableConSemiancho`
 * decide cuál ofrecer).
 */
export function actualizarBandaMinMax(
  limite: LimiteDeAlerta,
  mostrada: BandaMinMaxMostrada,
  conversion: Conversion,
  parametro?: number,
): LimiteDeAlerta {
  if (limite.banda === null) {
    throw new ErrorDeEdicionDeUmbral(`el límite del rol '${limite.rol}' no tiene banda`);
  }
  const minimo = aCanonica(mostrada.minimo, conversion, "punto", parametro);
  const maximo = aCanonica(mostrada.maximo, conversion, "punto", parametro);
  if (minimo >= maximo) {
    throw new ErrorDeEdicionDeUmbral(
      `el mínimo de la banda (${mostrada.minimo}) debe ser menor que el máximo (${mostrada.maximo})`,
    );
  }
  return construirLimiteDeAlerta({
    rol: limite.rol,
    topes: [],
    banda: { nivel: limite.banda.nivel, minimo, maximo },
  });
}

/** Centro y semiancho de una banda, en la unidad activa. Ver la cabecera del módulo. */
export interface BandaCentroYAnchoMostrada {
  readonly centro: number;
  readonly semiancho: number;
}

/** `true` si esta conversión admite editar la banda como centro/semiancho (necesita INTERVALO). */
export function bandaEsEditableConSemiancho(conversion: Conversion): boolean {
  return admiteClase(conversion, "intervalo");
}

export function bandaACentroYAnchoMostrado(
  banda: TopeDeBanda,
  conversion: Conversion,
  parametro?: number,
): BandaCentroYAnchoMostrada {
  if (esCurva(banda.minimo) || esCurva(banda.maximo)) {
    throw new ErrorDeEdicionDeUmbral("esta banda tiene un borde en curva: no se edita con valores planos");
  }
  if (!bandaEsEditableConSemiancho(conversion)) {
    throw new ErrorDeEdicionDeUmbral(
      "esta unidad usa una conversión recíproca: un ancho no es una diferencia lineal en esa " +
        "unidad, edita mínimo y máximo por separado (`actualizarBandaMinMax`)",
    );
  }
  // Se calcula el centro y el semiancho EN CANÓNICA primero y CADA UNO se
  // convierte con su propia clase — no se resta después de convertir los dos
  // extremos como PUNTO, aunque para una conversión afín daría el mismo
  // número: para una `parametrizada` cuyo factor futuro dejara de ser
  // constante en `x` esto seguiría siendo correcto y lo otro no, así que se
  // hace de la forma que generaliza.
  const centroCanonico = (banda.minimo + banda.maximo) / 2;
  const semianchoCanonico = (banda.maximo - banda.minimo) / 2;
  return {
    centro: convertirValor(centroCanonico, conversion, "punto", parametro),
    semiancho: convertirValor(semianchoCanonico, conversion, "intervalo", parametro),
  };
}

export function actualizarBandaCentroYAncho(
  limite: LimiteDeAlerta,
  mostrada: BandaCentroYAnchoMostrada,
  conversion: Conversion,
  parametro?: number,
): LimiteDeAlerta {
  if (limite.banda === null) {
    throw new ErrorDeEdicionDeUmbral(`el límite del rol '${limite.rol}' no tiene banda`);
  }
  if (!bandaEsEditableConSemiancho(conversion)) {
    throw new ErrorDeEdicionDeUmbral(
      "esta unidad usa una conversión recíproca: edita mínimo y máximo por separado " +
        "(`actualizarBandaMinMax`)",
    );
  }
  if (mostrada.semiancho <= 0) {
    throw new ErrorDeEdicionDeUmbral(`el semiancho de la banda tiene que ser positivo, y es ${mostrada.semiancho}`);
  }
  const centroCanonico = aCanonica(mostrada.centro, conversion, "punto", parametro);
  const semianchoCanonico = aCanonica(mostrada.semiancho, conversion, "intervalo", parametro);
  return construirLimiteDeAlerta({
    rol: limite.rol,
    topes: [],
    banda: {
      nivel: limite.banda.nivel,
      minimo: centroCanonico - Math.abs(semianchoCanonico),
      maximo: centroCanonico + Math.abs(semianchoCanonico),
    },
  });
}
