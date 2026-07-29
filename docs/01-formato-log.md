# 01 — Formato de log: especificación por ingeniería inversa

> Fuente: análisis de los tres ficheros de muestra. Todos los números de esta
> página se han medido, no estimado. Cualquier punto marcado **(por confirmar)**
> necesita más muestras o documentación del fabricante antes de implementarse.

## 1.1 Identificación

Los tres ficheros son CSV con cabecera propietaria:

```
%DataLog%
DataLogVersion : 1.1
Software : Haltech NSP
SoftwareVersion : 999.999.999.999
DownloadDateTime : 20260729 06:58:28
```

La primera línea `%DataLog%` es la firma del formato y el discriminador de
parser. `DataLogVersion` gobierna la compatibilidad: el parser debe **rechazar
explícitamente** versiones mayores desconocidas en lugar de intentar leerlas.

## 1.2 Dos sabores del mismo formato

El análisis revela dos perfiles de fichero muy distintos que **deben tratarse
como el mismo formato con dos comportamientos de muestreo**:

| | `AutoLog_…` | `Log2768/2769` |
|---|---|---|
| Origen | Log grabado desde el PC | Descarga de memoria interna de la ECU |
| `Log Source` | `0` | `8` |
| `Log Number` | `0` | `2768`, `2769` (secuenciales) |
| Canales | **475** | **25** |
| Líneas de cabecera | 1 895 | 108 |
| Filas de datos | 2 636 | 449 / 213 |
| Duración | 245,1 s | 14,11 s / 6,75 s |
| Densidad | **densa** (0 % de celdas vacías) | **dispersa** (56,4 % / 55,9 % vacías) |
| Marca temporal | absoluta real (`18:30:35.506`) | epoch ficticia (`01:01:01.005`) |
| Muestreo | tasa variable, un único grupo | 3 grupos a 20 / 10 / 5 Hz |

Consecuencia de diseño: **el motor de datos no puede asumir una matriz densa
con una única base de tiempos**. Cada canal es una serie temporal independiente
con su propio vector de instantes.

## 1.3 Estructura de la cabecera

Bloque de metadatos globales, luego N bloques de canal, luego metadatos de log:

```
Channel : Oil Pressure
ID : 236
Type : Pressure
DisplayMaxMin : 31013,1013
```

Reglas observadas y requisitos para el parser:

- El orden de los bloques `Channel` **define el orden de las columnas** de datos
  (columna 0 = marca de tiempo, columna *i+1* = canal *i*).
- `ID` es el identificador estable del canal en el sistema del fabricante. Los
  25 canales de `Log2768/2769` tienen **los 25 IDs presentes también en el
  AutoLog**. → **`ID` es la clave de unión entre logs, nunca el nombre.**
- `DisplayMaxMin` es opcional: **13 de los 475 canales del AutoLog no la
  tienen** (p. ej. `Bootmode Reason`, `Memory Writes Pending`). El parser debe
  tolerarlo y no desalinear los bloques.
- Los nombres no están normalizados y contienen erratas del origen
  (`FuelEcomony`, `Knock Input 1 FFT.` con punto final). **No se deben
  «corregir» ni usar para la identidad del canal**; se muestran tal cual y se
  permite alias en la capa de presentación.
- No hay nombres duplicados en las muestras, pero la unicidad **no está
  garantizada por el formato**: la clave interna debe ser `ID`.
- Metadatos de cierre de cabecera: `Log Source`, `Log Number`, `Log`.

## 1.4 Trampa crítica: la hora de la cabecera está en 12 h

En `AutoLog_20260729_1830.csv`:

| Campo | Valor |
|---|---|
| `Log` (cabecera) | `20260729 06:30:35` |
| Primera fila de datos | `18:30:35.506` |
| `DownloadDateTime` | `20260729 06:58:28` |
| Última fila de datos | `18:34:40.643` |

Las horas de cabecera están en **formato 12 h sin indicador AM/PM**, mientras
que las marcas de las filas están en **24 h**. La fecha de la cabecera es
fiable; la hora, ambigua con desfase de ±12 h.

**Regla de implementación**: la fecha absoluta se toma de `Log`, la hora del día
se toma **siempre de la primera fila de datos**, y la hora de la cabecera solo
se usa para validar el desfase módulo 12 h. Si el desfase no es 0 ni 12 h, se
marca el log como *reloj no fiable* y se degrada a modo relativo.

## 1.5 Trampa crítica: epoch ficticia en los logs internos

`Log2768` y `Log2769` declaran ambos `Log : 19800101 01:01:01` y ambos empiezan
en `01:01:01.005`. La ECU no tiene reloj de tiempo real, así que **no existe
tiempo absoluto** para estos logs. Lo único que da orden es:

- `Log Number` monótono creciente (2768 → 2769).
- `DownloadDateTime` de la descarga (`06:59:01` y `06:59:00`), que además está
  **invertido respecto al número de log** → no sirve para ordenar.

**Regla de implementación**: la alineación temporal de logs internos se hace por
`Log Number`, con desfase entre segmentos **desconocido** y por tanto editable
por el usuario. Nunca se debe fingir continuidad.

## 1.6 Filas de datos y muestreo disperso multi-tasa

Formato de fila: `HH:MM:SS.mmm` seguido de N valores separados por comas.
Los valores son **enteros con escala implícita**; una celda vacía significa
«este canal no se muestreó en este instante», **no** cero ni «sin datos».

En `Log2768/2769` los canales se agrupan en tres tasas fijas. Los grupos son
idénticos en ambos ficheros:

| Grupo | Tasa medida | Canales |
|---|---|---|
| G0 | 18,9 Hz (dt mediano 53 ms → nominal 20 Hz) | Target Lambda, Vehicle Speed Drive Train Sensor, Oil Pressure, O2 Control Bank 1 Short Term Fuel Trim, Wideband O2 1, RPM, Throttle Position, Manifold Pressure, Injection Stage 1 Average Duty Cycle, Ignition Angle, Knock Sensor 1/2 Knock Count, Trigger System Errors |
| G1 | 9,8 Hz (dt mediano 102 ms → nominal 10 Hz) | Transient Throttle ×5, Boost Control Target Pressure, Boost Control Output, Boost Control Short Term Trim |
| G2 | 5,0 Hz (dt mediano 202 ms → nominal 5 Hz) | Boost Control State, Idle Control State, Coolant Temperature, Intake Air Temperature |

Las filas de distintos grupos **se intercalan**, produciendo filas donde solo
un subconjunto de columnas tiene valor. Un parser CSV ingenuo genera una matriz
con 56 % de huecos.

**Regla de implementación**: almacenamiento columnar por canal, cada uno con su
propio vector de instantes (`t[]`) y de valores (`v[]`). La reconstrucción para
tabla/cursor se hace por **retención de último valor (sample-and-hold)** con
límite de validez configurable; el trazado **no interpola entre grupos**.

## 1.7 Tasa variable y huecos en el AutoLog

El AutoLog es denso en columnas pero **irregular en el tiempo**:

| Métrica | Valor |
|---|---|
| dt mediano (p50) | 54 ms |
| dt p90 | 163 ms |
| dt p99 | 221 ms |
| dt mínimo / máximo | 35 ms / 499 ms |
| Tasa media efectiva | 10,75 Hz |
| Filas con dt > 100 ms | 1 105 (41,9 %) |
| Filas con dt > 200 ms | 42 (1,6 %) |

Es bimodal: ráfagas en torno a 41–48 ms (≈22 Hz) alternadas con pausas
>100 ms. **No se debe asumir muestreo uniforme** para ningún cálculo
(derivadas, FFT, integrales, remuestreo). Todas las operaciones deben ser
explícitamente conscientes de `dt`, y los huecos por encima de un umbral
(por defecto 3× el dt mediano) deben romper la línea en el gráfico.

## 1.8 Registro de unidades y factores de escala

34 valores distintos de `Type` en el AutoLog. Los factores se han deducido
cruzando valores crudos, `DisplayMaxMin` y plausibilidad física.

### Confirmados

| `Type` | Factor | Unidad | Evidencia |
|---|---|---|---|
| `EngineSpeed` | ×1 | rpm | `DisplayMaxMin 20000,0`; crudo 3411 en tirada |
| `Percentage` | ÷10 | % | max `1000` = 100 % |
| `Angle` | ÷10 | ° | max `600` = 60°; crudo 264 → 26,4° de avance |
| `Speed` | ÷10 | km/h | max `4000` = 400 km/h; crudo 527 → 52,7 km/h |
| `Pressure` | ÷10 | kPa **absolutos** | MAP crudo 326 → 32,6 kPa (vacío de ralentí); 1254 → 125,4 kPa (boost) |
| `Temperature` | ÷10 − 273,15 | °C | **deciKelvin**: max/min `4731,2331` → 200 °C / −40 °C; coolant 3663 → 93,2 °C |
| `BatteryVoltage` | ÷1000 | V | crudo 12531 → 12,531 V; max `18000` = 18 V |
| `AFR` | ÷1000 | **λ** | crudo 995 → λ 0,995. El nombre del tipo engaña: **es lambda, no AFR** |
| `Stoichiometry` | ÷1000 | — | crudo 14700 → 14,7 (gasolina) |
| `Density` | ÷10 | kg/m³ | crudo 7372 → 737,2 kg/m³ (gasolina) |
| `Decibel` | ÷100 | dB | umbral de knock 3400 → 34 dB; señal 903 → 9,03 dB; max `6000` = 60 dB |
| `Time_us` | ×1 | µs | inyector 1748 → 1,748 ms en ralentí |
| `Raw` | ×1 | — | contador, enum o máscara de bits |

Conversión derivada: **AFR = λ × `Fuel Tuning Current Stoichiometry`**. El
visor debe permitir elegir λ o AFR por canal, calculando AFR con el canal de
estequiometría del propio log (no con un 14,7 constante) para que los logs de
E85/metanol salgan correctos.

### Por confirmar

`AbsPressure`, `Frequency`, `Resistance`, `Time_ms`, `Time_ms_as_s`, `Time_s`,
`InjFuelVolume`, `FuelVolume`, `MassOverTime`, `MassPerCyl`, `Flow`,
`AngularVelocity`, `PercentPerRpm`, `PercentPerKPa`, `PercentPerLambda`,
`PulsesPerLongDistance`, `FuelEcomony`, `Mileage`, `EngineVolume`,
`ShortDistance`, `ByteCount`.

**Regla de implementación**: el registro de unidades es un **fichero de datos
versionado, no código**, con un campo `confidence: confirmed | inferred |
unknown`. Los canales `unknown` se muestran con su valor crudo y una marca
visual, nunca con una unidad inventada. Esto convierte la calibración
progresiva en una tarea de datos de bajo coste y evita mentir al usuario.

> Los factores de esta tabla son la **escala de origen hacia la unidad canónica**
> de cada dimensión, no la unidad que ve el usuario. El usuario elige después
> entre K, °C y °F, o entre kPa, bar y psi, sin que estos factores cambien.
> El modelo completo está en [`06-sistema-de-unidades.md`](06-sistema-de-unidades.md);
> la columna «Unidad» de arriba indica la **canónica** de cada dimensión.

## 1.9 Presión: no hay canal barométrico

No existe canal barométrico ni de presión ambiente (el único resultado de la
búsqueda es `Ambient Light Level`). Todas las presiones son **absolutas**.
Para mostrar presión relativa (bar de boost, la unidad que usa un tuner) hace
falta una referencia. Opciones, en orden de preferencia:

1. Presión de referencia declarada por el usuario en el perfil del vehículo.
2. Autodetección: mediana de `Manifold Pressure` con `RPM = 0` al inicio del log.
3. Constante 101,3 kPa como último recurso, marcada como estimada.

## 1.10 Canales de estado, enums y máscaras de bits

**75 canales** tienen `Type: Raw` con rango ≤ 20 → son casi con certeza
enumerados, no magnitudes continuas. Ejemplos y su tratamiento:

| Canal | Rango | Interpretación |
|---|---|---|
| `Boost Control State` | 0…10 | enum de estado |
| `Idle Control State` | −8…3 | enum con códigos negativos |
| `Launch Control State` | −101…1 | enum con códigos negativos amplios |
| `Engine Protection Severity Level` | 0…3 | nivel ordinal |
| `Engine Protection Cause` | 0…65535 | **máscara de bits** — hay que decodificar bits, no valores |
| `RPM Limiting Method`, `Engine Limiting Method`, `Cut Percentage Method` | 0…3 | enum |
| `Trigger System Errors` | 0…31 | probable máscara de bits de 5 flags |

Dibujar esto como líneas es inútil. **Requisito de producto**: renderizar los
canales enumerados como **carriles de estado** (bandas de color con etiqueta)
sobre el eje de tiempo compartido, y las máscaras de bits como carriles
apilados de un bit cada uno. Es una de las mejoras de legibilidad de mayor
relación valor/coste del proyecto.

El mapa código → nombre no está en el fichero. Se construye incrementalmente en
el registro versionado; los códigos sin traducir se muestran como `Estado 7`.

## 1.11 Detección de canales muertos

`Oil Temperature` vale exactamente `2531` (−20,05 °C) en todo el AutoLog, con
el motor caliente a 93 °C. Es un **sensor no instalado** que devuelve un valor
por defecto. En un fichero de 475 canales, la mitad suele ser ruido de este
tipo.

**Requisito de producto**: al indexar, clasificar cada canal como
`activo | constante | vacío | fuera de rango` y, por omisión, **ocultar los no
activos** del selector de canales, con un conmutador para verlos. Esto reduce
475 canales a unas pocas decenas relevantes y es clave para la prioridad de
facilidad de uso.

## 1.12 Volumetría y consecuencias de rendimiento

Medido: 3,57 bytes de CSV por muestra.

Extrapolación a una sesión de **1 hora** con los 475 canales del AutoLog:

| Métrica | Valor |
|---|---|
| Tamaño CSV | ≈ 66 MB |
| Muestras | ≈ 18,3 millones |
| Memoria como `i32` columnar | ≈ 73 MB |
| Memoria como `f32` | ≈ 73 MB |

Caso de diseño peor (objetivo de la fase 2): **8 logs de 30 min en paralelo**
→ ≈ 73 M muestras, ≈ 300 MB. Es manejable en memoria con almacenamiento
columnar de enteros, pero **imposible de dibujar punto a punto**: de ahí la
pirámide de decimación descrita en `03-arquitectura.md`.

Decisión derivada: **guardar los enteros crudos**, no flotantes convertidos.
Ocupa lo mismo o menos, es exacto, y la escala se aplica en el momento de
mostrar. Además permite comparación bit a bit entre logs y evita acumular
error en las agregaciones.

## 1.13 Lista de verificación del parser

- [ ] Firma `%DataLog%` y `DataLogVersion` validadas; versión mayor desconocida → error claro.
- [ ] Bloques `Channel` con `DisplayMaxMin` ausente no desalinean.
- [ ] Identidad de canal por `ID`; nombre solo para mostrar.
- [ ] Celda vacía ≠ 0 ≠ ausente.
- [ ] Serie temporal independiente por canal (multi-tasa).
- [ ] Cruce de medianoche en las marcas `HH:MM:SS.mmm` (log que pasa de 23:59 a 00:00).
- [ ] Hora de cabecera en 12 h reconciliada módulo 12 h.
- [ ] Epoch ficticia `19800101` detectada → modo relativo.
- [ ] Fila truncada o con número de columnas incorrecto → se registra y se salta, sin abortar la carga.
- [ ] Fichero sin `\n` final, CRLF y LF, BOM UTF-8. **El formato nativo es CRLF**: medido sobre `20260729_1859_Log2768.csv`, 557 CRLF y ningún LF suelto. La variante LF aparece cuando una herramienta reescribe el log en Unix (`samples/corrupt/06-lf-solo.csv`).
- [ ] Marcas de tiempo no monótonas → se detectan y se avisa.
- [ ] Enteros que desbordan `i32` (se observa `-2147483645` y `2147483647` como centinelas) → tratados como **valor no válido**, no como dato.

> El último punto es importante: en el AutoLog aparecen `2147483647`,
> `-2147483645`, `-2147483628` y `8388607` de forma repetida. Son centinelas de
> «sin dato»/saturación, no medidas. Si se promedian, contaminan cualquier
> estadística. La lista de centinelas va en el registro versionado.
