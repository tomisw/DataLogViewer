# Log equivalente en dos formatos — fixture de independencia de fabricante (F0-13)

## Qué demuestra este par de ficheros

`nativo.csv` (Haltech `%DataLog% 1.1`) y `generico.csv` (CSV `;`, decimal
coma, nombres distintos, tiempo relativo) codifican el **mismo contenido
físico**: 300 filas a 20 Hz (~14.95 s) de una tirada
ralentí → plena carga → sostenido, en 10 canales.

La afirmación que este fixture pone a prueba (docs/07-formatos-y-csv-generico.md
§7.7, §7.11) es que perfiles y detectores funcionan igual sobre cualquiera de
los dos, porque el emparejamiento es por **rol semántico**, no por nombre ni
por `ID` de fabricante. `tests/test_dos_formatos.py` (fase FG-16) aplica la
escala de origen del nativo y la unidad declarada del genérico y comprueba
que ambos caminos llegan al **mismo valor canónico**, canal por canal y fila
por fila.

Los nombres del genérico son deliberadamente distintos de los de Haltech
(`Régimen` vs. `RPM`, `Mariposa` vs. `Throttle Position`...): si el
emparejamiento dependiera del nombre, este fixture lo pondría de manifiesto.

## Generación

```bash
python tools/generar_dos_formatos.py [--seed 20260729] [--output samples/dos-formatos]
```

Determinista: el `random.Random(seed)` se consume en un orden fijo (fila por
fila, canal por canal) y ningún fichero contiene la hora de generación real,
así que dos ejecuciones son **idénticas byte a byte** (verificable con
`sha256sum samples/dos-formatos/*`). Los cuatro ficheros —`nativo.csv`,
`generico.csv`, `anotaciones.json` y este `README.md`— los escribe el mismo
script, a partir de un único vector de valores canónicos: los dos CSV se
**derivan** de ahí, no se generan por separado.

## Tabla de correspondencia canal ↔ rol ↔ columna

| Rol semántico | Canal nativo | Escala nativa (docs/01 §1.8) | Canal genérico | Unidad / precisión genérica |
|---|---|---|---|---|
| `engine_speed` | RPM (ID 384, `EngineSpeed`) | col. 1 nativa: crudo÷1 | Régimen | col. 1 genérica: `rpm`, 0 dec. |
| `manifold_pressure` | Manifold Pressure (ID 224, `Pressure`) | col. 2 nativa: crudo÷10 | Presión colector | col. 2 genérica: `kPa`, 1 dec. |
| `throttle_position` | Throttle Position (ID 225, `Percentage`) | col. 3 nativa: crudo÷1000 | Mariposa | col. 3 genérica: `pct`, 1 dec. |
| `coolant_temp` | Coolant Temperature (ID 229, `Temperature`) | col. 4 nativa: crudo÷10 | Temp. refrigerante | col. 4 genérica: `degC`, 2 dec. |
| `intake_air_temp` | Intake Air Temperature (ID 228, `Temperature`) | col. 5 nativa: crudo÷10 | Temp. aire | col. 5 genérica: `degC`, 2 dec. |
| `lambda_measured` | Wideband O2 1 (ID 230, `AFR`) | col. 6 nativa: crudo÷1000 | Lambda | col. 6 genérica: `lambda`, 3 dec. |
| `lambda_target` | Target Lambda (ID 132, `AFR`) | col. 7 nativa: crudo÷1000 | Lambda objetivo | col. 7 genérica: `lambda`, 3 dec. |
| `ignition_advance` | Ignition Angle (ID 518, `Angle`) | col. 8 nativa: crudo÷10 | Avance | col. 8 genérica: `deg`, 1 dec. |
| `oil_pressure` | Oil Pressure (ID 236, `Pressure`) | col. 9 nativa: crudo÷10 | Presión aceite | col. 9 genérica: `kPa`, 1 dec. |
| `battery_voltage` | Battery Voltage (ID 258, `BatteryVoltage`) | col. 10 nativa: crudo÷1000 | Tensión batería | col. 10 genérica: `V`, 3 dec. |

Columna 0 en ambos ficheros es la marca de tiempo (nativo: `HH:MM:SS.mmm`
absoluto con epoch ficticia 19800101, igual que `samples/real/*Log276{8,9}*`;
genérico: segundos relativos `0,000`, `0,050`, ...).

## Escalas aplicadas

**Lado nativo.** `canonica = crudo_entero / divisor`, con el divisor de la
tabla «Confirmados» de docs/01-formato-log.md §1.8 (no vive en
`data/formats/<formato>.toml` porque F0-09 es tarea de otro agente; aquí está
como constante documentada, y es exactamente la tabla del enunciado de F0-13).
El tipo `AFR` de Haltech contiene lambda, no relación aire-combustible
(docs/01 §1.8): por eso `lambda_measured` y `lambda_target` llevan
`Type: AFR` pero su rol y su dimensión son `mixture_ratio`/`lambda`.

**Lado genérico.** `mostrado = a · canonica + b`, con `(a, b)` leídos de
`data/units.toml` (F0-08, catálogo ya aprobado) para la unidad declarada de
cada columna — no están re-tecleados aquí. Salvo mariposa (`pct`) y
temperatura (`degC`), todas las columnas genéricas muestran la unidad
canónica directamente (`a=1, b=0`): rpm, kPa, λ, ° y V son ya sus propias
canónicas.

## Precisión de escritura del genérico y tolerancias

El enunciado pide elegir la precisión de escritura para que la ida y vuelta
sea exacta, no simplemente redondear a los decimales por omisión del
catálogo. Hay dos canales donde eso importa:

- **Presión** (`manifold_pressure`, `oil_pressure`): `data/units.toml` fija
  `decimales = 0` para `kPa`, pero eso es una preferencia de **presentación**
  del renderizador (redondear a kPa entero es cómodo de leer), no una cota de
  precisión de un fichero fuente. La canónica del nativo ya tiene 1 decimal
  (`crudo ÷ 10`), así que el genérico escribe kPa con **1 decimal**: con 0
  decimales se perdería información real y la ida y vuelta dejaría de ser
  exacta.
- **Temperatura** (`coolant_temp`, `intake_air_temp`): `data/units.toml` fija
  `decimales = 1` para `degC`, pero `°C = K − 273,15` necesita **2
  decimales** para ser exacto cuando K solo tiene 1 (p. ej. 366,3 K − 273,15 =
  93,15 °C, no 93,2 °C — el ejemplo exacto que pone el enunciado). El
  genérico escribe temperatura con 2 decimales.

El resto de columnas (`rpm`, `pct`, `lambda`, `deg`, `V`) coincide con el
`decimales` del catálogo porque la canónica nativa ya tiene, de fábrica,
justo esa cantidad de decimales significativos.

### Canales con ida y vuelta bit-exacta incluso en coma flotante

`engine_speed`, `manifold_pressure`, `lambda_measured`, `lambda_target`, `ignition_advance`, `oil_pressure`, `battery_voltage`.

Su conversión declarada es `mostrado = 1 · canonica + 0`: la cadena escrita
en el genérico es la representación decimal más corta del mismo valor exacto
que produce `crudo / divisor` en el nativo, y tanto el parseo de una cadena
decimal como una única división son operaciones **correctamente redondeadas**
en IEEE-754 — llegan al mismo `double` más cercano por construcción.
`tolerancia_canonica = 0.0` en `anotaciones.json` para estos 7 canales, y es
literal, no un margen de seguridad.

### Canales que SÍ necesitan un margen de punto flotante

`throttle_position`, `coolant_temp`, `intake_air_temp`.

Estos tres encadenan **dos** redondeos independientes del lado genérico
(parsear la cadena decimal, y luego sumar `273,15` o dividir entre `100`),
frente a la única división del lado nativo. En aritmética decimal exacta
(`decimal.Decimal`, que es lo que usa este generador para escribir las
cadenas) el resultado es matemáticamente idéntico — por eso el fixture en sí
**sí es exacto**, es una propiedad real del contenido, no un artefacto de la
prueba. Pero una comparación hecha en `float` de doble precisión (lo que hará
en la práctica cualquier importador basado en `polars`/`numpy`, ver docs/01
§1.12) puede acumular hasta **1 ULP** de diferencia entre los dos caminos —
del orden de 1e-13 en estas magnitudes. `anotaciones.json` declara
`tolerancia_canonica = 1e-9` para estos tres canales: dos órdenes de magnitud
de margen sobre el error esperado, para blindar la prueba sin esconder que
"exacto" y "bit-exacto en float" no son la misma afirmación.

**Esto es la información que la revisión humana necesita**: la igualdad
física es exacta en los 10 canales; la igualdad *en punto flotante* solo lo
es garantizadamente en 7 de los 10, y en los otros 3 hace falta una
tolerancia (pequeñísima, pero no nula) por cómo redondea IEEE-754, no por
ningún defecto del formato ni del emparejamiento por rol.

## Restricciones de formato verificadas

- `generico.csv` no contiene ni un solo `.` en ninguna celda numérica
  (delimitador `;`, decimal `,`).
- `nativo.csv` usa CRLF (docs/01 §1.13); `generico.csv` usa LF, a propósito,
  para no dar ninguna pista de que ambos vienen del mismo fabricante.
- Denso: 300 filas × 10 canales, sin celdas vacías — la dispersión
  multi-tasa de docs/01 §1.6 es una prueba distinta, no la de esta tarea.

## Verificación sin regenerar

`anotaciones.json` incluye el vector canónico completo de 3 canales
representativos (`engine_speed`, `manifold_pressure`, `lambda_measured` — uno
de cada familia de escala: entero directo, división simple, división de
mayor precisión) y el hash `sha256` de los 10 canales completos, con la
receta exacta para recalcularlo. `hash_sha256_todos_los_roles` de esta
generación: `ab7b6c120e4dd4943968d7b3664e5798c1fe6fa2a9484aa6e747379d14b52a86`.
