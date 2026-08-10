# Corpus de CSV genéricos para prueba del importador FG

**16 ficheros de prueba** para validar la **autodetección y robustez** del importador de CSV genérico de DataLogViewer (fase FG, §7.4–§7.10 de `docs/07-formatos-y-csv-generico.md`).

Cada fichero ejercita un conjunto específico de características de detección y robustez. Son pequeños (~50 filas, 6–10 columnas) y contienen **valores físicamente plausibles** para un motor de combustión (RPM, MAP, TPS, CLT, Lambda, AFR, etc.).

## Especificaciones por fichero

| Fichero | Delimitador | Decimal | Codificación | Tiempo | Qué debe detectar el importador |
|---|---|---|---|---|---|
| **01-coma-punto.csv** | `,` | `.` | UTF-8 | Relativo (s) | Caso estándar anglosajón: delimitador coma, decimal punto |
| **02-puntoycoma-coma.csv** | `;` | `,` | UTF-8 | Relativo (s) | CSV español típico: delimitador punto y coma, decimal coma; sin un solo punto en celdas numéricas |
| **03-tabulaciones.csv** | `\t` | `.` | UTF-8 | Relativo (s) | Delimitador tabulador; tablas de copiado directo desde hojas de cálculo |
| **04-fila-de-unidades.csv** | `,` | `.` | UTF-8 | Relativo (s) | **Fila de unidades**: cabecera con nombres, segunda fila con unidades (`s`, `rpm`, `kPa`, `%`, `C`, `ratio`) antes de datos |
| **05-unidad-en-el-nombre.csv** | `,` | `.` | UTF-8 | Relativo (s) | Unidades **embebidas en el nombre**: `RPM [rpm]`, `CLT (°C)`, `MAP [kPa]`, `TPS (%)`, `Lambda [ratio]` |
| **06-sin-columna-de-tiempo.csv** | `,` | `.` | UTF-8 | **Ninguno** | **Sin columna temporal**; solo canales (RPM, MAP, TPS, CLT, Lambda, AFR). Usuario declara frecuencia de muestreo. |
| **07-epoch-segundos.csv** | `,` | `.` | UTF-8 | Época (s) | Época Unix en **segundos con decimales** (`1785000000.000`, `1785000002.500`, …) |
| **08-epoch-milisegundos.csv** | `,` | `.` | UTF-8 | Época (ms) | Época Unix en **milisegundos (entero)** (`1785000000000`, `1785000050`, …) |
| **09-iso8601.csv** | `,` | `.` | UTF-8 | ISO-8601 | Marcas de tiempo en **formato ISO-8601 con zona horaria** (`2026-07-29T18:30:35.506Z`) |
| **10-latin1.csv** | `,` | `.` | **latin-1** | Relativo (s) | **Codificación latin-1** (no UTF-8 válido); nombres con acentos: `Tiempo`, `Velocidad_motor`, `Presión_colector`, `Temperatura_refrigerante` |
| **11-valores-ausentes.csv** | `,` | `.` | UTF-8 | Relativo (s) | **Valores ausentes variados**: `NaN`, `#N/A`, `NULL`, `---`, `n/a`, celdas vacías (10 % de probabilidad por celda) |
| **12-texto-y-booleanos.csv** | `,` | `.` | UTF-8 | Relativo (s) | **Columna de texto enumerado** (`Marcha`: `N`,`1`,`2`,`3`) y **columna booleana** (`Limitador`: `true`/`false`) |
| **13-columnas-duplicadas.csv** | `,` | `.` | UTF-8 | Relativo (s) | **Dos columnas con nombre idéntico** (ambas `RPM`); el importador desambigua con sufijo y avisa |
| **14-preambulo-largo.csv** | `,` | `.` | UTF-8 | Relativo (s) | **Preámbulo de 12 líneas** de metadatos `clave: valor` antes de la fila de nombres |
| **15-filas-longitud-variable.csv** | `,` | `.` | UTF-8 | Relativo (s) | **Filas de longitud variable** (FG-14): una fila corta (le faltan `CLT` y `Lambda`) y una fila larga (un campo de sobra); no se aborta la carga, el hueco llega como ausente, nunca como 0 |
| **16-cabecera-sin-nombres.csv** | `,` | `.` | UTF-8 | Relativo (s) | **Cabecera sin nombres** (FG-14): los datos empiezan en la primera línea, sin fila de nombres; las columnas se nombran `col_1…col_n` |

## Generación

Los ficheros se generan de forma **determinista** con:

```bash
python tools/generar_genericos.py [--seed <seed>] [--output <dir>]
```

- `--seed`: Semilla RNG (default: 42)
- `--output`: Directorio destino (default: `samples/generico`)

Dos ejecuciones consecutivas producen ficheros **byte-a-byte idénticos** (verificable con `sha256sum`).

## Datos realistas

Cada fichero contiene **~50 filas de datos** con valores **físicamente plausibles**:

- **RPM**: 800–7000 rpm (rango operativo motor)
- **MAP**: 30–250 kPa (presión de admisión)
- **TPS**: 0–100 % (posición mariposa)
- **CLT**: 70–105 °C (temperatura refrigerante)
- **Lambda**: 0,75–1,05 ratio (mezcla aire-combustible)
- **AFR**: 12–16 ratio (relación aire-combustible)
- **Epoch**: 1785000000 ± segundos/milisegundos
- **ISO-8601**: 2026-07-29T18:30:00Z onwards

## Restricciones verificadas

✓ El fichero **02** no contiene **ni un solo punto** (`.`) en celdas numéricas (verificación: `grep -E '\d+\.\d+'`)  
✓ El fichero **01** no contiene **ni un solo punto y coma** (`;`) en celdas de datos (verificación: `grep ';'`)  
✓ El fichero **10** **no es UTF-8 válido** (genera `UnicodeDecodeError`)  
✓ Los otros **15 ficheros sí son UTF-8 válidos**  
✓ Determinismo verificado con `sha256sum`  
✓ Código limpio: `ruff check` y `ruff format` satisfechos

## Uso en tests

Los ficheros están listos para ser consumidos por:

1. **Sondeo (§7.4)**: Detecta delimitador, decimal, codificación, cabecera, unidades
2. **Autoasignación de roles (§7.7)**: Empareja nombres con sinónimos de `roles.toml`
3. **Informe de plausibilidad (§7.7)**: Valida rangos de valores detectados
4. **Asistente de importación (§7.8)**: Interfaz de 3 pasos con previsualización
5. **Robustez (§7.10)**: Manejo de valores ausentes, duplicados, texto, booleanos, preámbulos, filas de longitud variable y cabecera sin nombres (FG-14)

---

*Generados con `tools/generar_genericos.py` — DataLogViewer FG*
