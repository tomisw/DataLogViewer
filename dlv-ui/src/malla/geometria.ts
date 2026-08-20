/**
 * Geometría del mapa de calor: a qué píxel, con qué color y con qué estado de
 * confianza cae cada celda de una `MallaResuelta` (F4-04).
 *
 * Misma frontera que `topes/geometria.ts` y `ejes/geometria.ts`: aritmética
 * pura, comprobable en Node sin abrir un navegador. `mapa-de-calor.ts` es la
 * fontanería SVG que copia esta salida a atributos `x`/`y`/`width`/`height`/
 * `fill` y no tiene pruebas propias, por la misma razón que ellos.
 *
 * REUTILIZA `xAPixel`/`yAPixel` DE `ejes/coordenadas.ts`, A PROPÓSITO
 * =====================================================================
 * Un mapa de calor es, en el fondo, una rejilla de valores sobre los mismos
 * dos ejes que ya pinta `ejes/ejes.ts` (RPM en X, MAP en Y). Reescribir la
 * conversión dato → píxel aquí —con su inversión del eje Y, que es
 * precisamente donde `ejes/coordenadas.ts` avisa que se cuela el fallo
 * silencioso de «los datos están del revés»— sería una segunda
 * implementación que se puede desincronizar de la primera. Se construye una
 * `Vista` sintética a partir de los bordes exteriores de la malla y se le
 * pide a `xAPixel`/`yAPixel` un píxel por CADA borde (no por muestra:
 * `bordesFila`/`bordesColumna` tienen `filas + 1`/`columnas + 1` elementos,
 * la resolución de la malla, nunca el número de muestras agregadas).
 *
 * LA CONVERSIÓN DE CADA ESTADÍSTICA, CLASE POR CLASE
 * =======================================================
 * `media`, `minimo` y `maximo` se convierten con `claseValor` de la
 * configuración —NO con `Clase.PUNTO` a secas, ver la cabecera de
 * `tipos.ts`—. `desviacionTipica` se convierte SIEMPRE con `Clase.INTERVALO`,
 * fija, sin parametrizar: es una dispersión sea cual sea la clase del canal
 * agregado. Una celda `NaN` (sin datos) nunca llega a `convertirValor`: si
 * `claseValor` fuera `"intervalo"` sobre una conversión recíproca,
 * `convertirValor` lanza `ErrorDeUnidad` con cualquier entrada, finita o no
 * (comprueba la clase antes que el valor) — y una celda vacía no tiene nada
 * que convertir, así que no hay motivo para arriesgarse a esa excepción por
 * un NaN que de todas formas se va a mostrar como «—».
 *
 * POCA CONFIANZA: SE ATENÚA, NO SE OCULTA
 * ============================================
 * Una celda con `0 < cuenta < umbralConfianza` SIGUE recibiendo el color de
 * su valor —ocultarla del todo perdería la tendencia que sí se puede leer—
 * pero con la opacidad reducida a una interpolación entre
 * `OPACIDAD_MINIMA_POCA_CONFIANZA` (en `cuenta === 1`) y `1` (en
 * `cuenta === umbralConfianza`). `OPACIDAD_MINIMA_POCA_CONFIANZA` es una
 * constante de PRESENTACIÓN —cuánto se atenúa un color en pantalla—, no un
 * umbral físico del motor: no es del tipo de número que `data/umbrales.toml`
 * declara (regla 3 de `CLAUDE.md`), así que vive aquí igual que
 * `topes/geometria.ts#DECIMALES_POR_OMISION` vive en su módulo.
 *
 * `"vacia"` (`cuenta === 0`) NUNCA usa `colorDeValor`: usa
 * `config.colorSinDatos` sin más, precisamente para que una celda vacía no
 * pueda coincidir por accidente con el color que `colorDeValor` daría a un
 * valor real —el caso que la cabecera de `tipos.ts` señala: «una celda vacía
 * no es una celda con error cero».
 */

import { xAPixel, yAPixel } from "../ejes/coordenadas.ts";
import { formatearNumero } from "../locale/numerico.ts";
import { convertirValor, type Clase } from "../unidades/conversion.ts";
import type { Color, Vista } from "../render/tipos.ts";
import type {
  CeldaEstadisticas,
  CeldaPintada,
  ConfiguracionMapaDeCalor,
  DetalleCelda,
  EstadoCelda,
  GeometriaMapaDeCalor,
} from "./tipos.ts";

const DECIMALES_POR_OMISION = 2;

/** Opacidad de una celda de baja confianza en `cuenta === 1`. Ver la cabecera del módulo. */
const OPACIDAD_MINIMA_POCA_CONFIANZA = 0.3;

function estadoDeCelda(cuenta: number, umbralConfianza: number): EstadoCelda {
  if (cuenta <= 0) return "vacia";
  return cuenta >= umbralConfianza ? "confiable" : "pocaConfianza";
}

/**
 * `1` en `cuenta >= umbralConfianza`, interpolado linealmente hasta
 * `OPACIDAD_MINIMA_POCA_CONFIANZA` en `cuenta === 1`. No se llama nunca con
 * `cuenta === 0` (esas celdas ni siquiera pasan por `colorDeValor`).
 */
function factorDeConfianza(cuenta: number, umbralConfianza: number): number {
  if (cuenta >= umbralConfianza) return 1;
  if (umbralConfianza <= 1) return 1; // defensivo: con este umbral toda cuenta >= 1 ya sería "confiable" arriba
  const fraccion = (cuenta - 1) / (umbralConfianza - 1);
  return (
    OPACIDAD_MINIMA_POCA_CONFIANZA +
    (1 - OPACIDAD_MINIMA_POCA_CONFIANZA) * Math.min(1, Math.max(0, fraccion))
  );
}

function atenuarOpacidad(color: Color, factor: number): Color {
  return { r: color.r, g: color.g, b: color.b, a: color.a * factor };
}

/** `NaN` se queda `NaN`: `convertirValor` no se llama con una celda vacía (ver la cabecera). */
function convertirSiFinito(
  valorCanonico: number,
  clase: Clase,
  conversion: ConfiguracionMapaDeCalor["conversion"],
  parametro: number | undefined,
): number {
  if (!Number.isFinite(valorCanonico)) return NaN;
  return convertirValor(valorCanonico, conversion, clase, parametro);
}

/** El número ya formateado, o «—» si no es finito (celda vacía). Mismo criterio que `cursor/cursor.ts#formatearNumero`. */
function formatoOTexto(valorMostrado: number, decimales: number): string {
  return Number.isFinite(valorMostrado) ? formatearNumero(valorMostrado, decimales) : "—";
}

function resolverDetalle(
  fila: number,
  columna: number,
  celda: CeldaEstadisticas,
  estado: EstadoCelda,
  config: ConfiguracionMapaDeCalor,
  decimales: number,
): { detalle: DetalleCelda; mediaMostrada: number } {
  const { conversion, claseValor, parametro } = config;
  const mediaMostrada = convertirSiFinito(celda.media, claseValor, conversion, parametro);
  const minimoMostrado = convertirSiFinito(celda.minimo, claseValor, conversion, parametro);
  const maximoMostrado = convertirSiFinito(celda.maximo, claseValor, conversion, parametro);
  // SIEMPRE "intervalo", nunca `claseValor`: una desviación típica es una
  // dispersión sea cual sea la clase del canal agregado (ver la cabecera).
  const desviacionMostrada = convertirSiFinito(celda.desviacionTipica, "intervalo", conversion, parametro);

  const detalle: DetalleCelda = {
    fila,
    columna,
    estado,
    celda,
    cuentaTexto: formatearNumero(celda.cuenta, 0),
    mediaTexto: formatoOTexto(mediaMostrada, decimales),
    desviacionTipicaTexto: formatoOTexto(desviacionMostrada, decimales),
    minimoTexto: formatoOTexto(minimoMostrado, decimales),
    maximoTexto: formatoOTexto(maximoMostrado, decimales),
  };
  return { detalle, mediaMostrada };
}

/**
 * Calcula la geometría completa del mapa de calor: un rectángulo, un color y
 * un detalle por cada celda de `config.malla`.
 *
 * Lanza si `config.malla` no coincide con `config.forma` (número de celdas,
 * o longitud de los bordes) o si `umbralConfianza` no es un número positivo:
 * son errores de configuración de quien llama, no datos del log, así que se
 * paran aquí en vez de producir una malla con celdas fantasma (regla 6 de
 * `CLAUDE.md`: parar y decir qué revisar, no inventar).
 */
export function calcularGeometriaMapaDeCalor(config: ConfiguracionMapaDeCalor): GeometriaMapaDeCalor {
  const { area, malla, forma, umbralConfianza } = config;
  const decimales = config.decimales ?? DECIMALES_POR_OMISION;

  if (!(umbralConfianza > 0)) {
    throw new RangeError(`umbralConfianza tiene que ser un número > 0, se dio ${umbralConfianza}`);
  }
  const { filas, columnas } = forma;
  if (malla.celdas.length !== filas * columnas) {
    throw new RangeError(
      `la malla tiene ${malla.celdas.length} celdas pero forma declara ${filas}×${columnas} = ${filas * columnas}`,
    );
  }
  if (malla.bordesFila.length !== filas + 1) {
    throw new RangeError(`bordesFila tiene ${malla.bordesFila.length} elementos, se esperaban ${filas + 1}`);
  }
  if (malla.bordesColumna.length !== columnas + 1) {
    throw new RangeError(
      `bordesColumna tiene ${malla.bordesColumna.length} elementos, se esperaban ${columnas + 1}`,
    );
  }

  const vista: Vista = {
    t0: malla.bordesColumna[0]!,
    t1: malla.bordesColumna[columnas]!,
    v0: malla.bordesFila[0]!,
    v1: malla.bordesFila[filas]!,
  };
  const pixelesColumna = malla.bordesColumna.map((b) => xAPixel(b, vista, area.ancho));
  const pixelesFila = malla.bordesFila.map((b) => yAPixel(b, vista, area.alto));

  const celdas: CeldaPintada[] = [];
  for (let fila = 0; fila < filas; fila += 1) {
    for (let columna = 0; columna < columnas; columna += 1) {
      const indice = fila * columnas + columna;
      const celda = malla.celdas[indice]!;
      const estado = estadoDeCelda(celda.cuenta, umbralConfianza);
      const { detalle, mediaMostrada } = resolverDetalle(fila, columna, celda, estado, config, decimales);

      const color =
        estado === "vacia"
          ? config.colorSinDatos
          : atenuarOpacidad(
              config.colorDeValor(mediaMostrada, celda),
              factorDeConfianza(celda.cuenta, umbralConfianza),
            );

      // `Math.min`/`Math.abs` en vez de asumir el orden: `yAPixel` invierte
      // (el borde MÁS ALTO cae en el píxel MÁS PEQUEÑO), `xAPixel` no — así
      // esta celda no tiene que saber cuál de las dos convenciones le toca.
      const xIzq = pixelesColumna[columna]!;
      const xDer = pixelesColumna[columna + 1]!;
      const yArriba = pixelesFila[fila + 1]!;
      const yAbajo = pixelesFila[fila]!;

      celdas.push({
        fila,
        columna,
        x: Math.min(xIzq, xDer),
        y: Math.min(yArriba, yAbajo),
        ancho: Math.abs(xDer - xIzq),
        alto: Math.abs(yAbajo - yArriba),
        estado,
        color,
        detalle,
      });
    }
  }

  return { area, celdas };
}
