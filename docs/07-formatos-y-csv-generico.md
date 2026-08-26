# 07 — Extensibilidad de formatos e importación de CSV genérico

## 7.1 Requisito

El proyecto debe funcionar con **cualquier CSV**, no solo con el formato Haltech
de las muestras. Un log de MoTeC, de Link, de ECUMaster, de TunerStudio, de un
datalogger casero con un Arduino o una exportación de Excel deben poder abrirse y
analizarse con los mismos perfiles y detectores.

## 7.2 El problema real no es leer el CSV

Leer columnas separadas por comas es trivial. Lo difícil es que **los perfiles y
los detectores sigan funcionando**. Tal como estaba el plan, el perfil «Knock»
dependía del `ID 696` de Haltech; en un CSV de MoTeC ese ID no existe y el perfil
queda inservible.

La solución es una capa de indirección: **roles semánticos**. Los perfiles y
detectores no piden «el canal 696», piden «el rol `knock_count[1]`». El
importador es el responsable de decir qué columna cumple cada rol. Es el cambio
de fondo que hace el proyecto escalable, y afecta a las épicas de perfiles y de
multi-log, no solo a la de ingesta.

## 7.3 Capa de formatos en dos niveles

```
                  ┌─────────────────────────────────┐
   fichero  ──────▶  Sondeo (firma + huella)        │
                  └────────────┬────────────────────┘
                       ┌───────┴────────┐
                       ▼                ▼
        Nivel 1: FORMATO NATIVO   Nivel 2: CSV GENÉRICO
        descriptor declarativo    asistente + perfil de
        (haltech_nsp.toml, …)     importación (.dlvimport)
                       │                │
                       └───────┬────────┘
                               ▼
                   Canales + roles + dimensiones
                        (modelo común)
```

**Nivel 1 — formatos nativos.** Un fichero descriptor declarativo por formato,
no código: firma de detección, gramática de la cabecera, mapa de tipos a
dimensiones y escalas, reglas de muestreo, mapa de roles por defecto. El formato
Haltech de `01-formato-log.md` es el primer descriptor, y es la prueba de que la
capa declarativa basta: si añadir Haltech requiere código, el diseño ha fallado.

Solo se admite código Python específico cuando el formato es binario o tiene una
peculiaridad indescriptible (ganchos opcionales por descriptor).

**Nivel 2 — CSV genérico.** Cuando ninguna firma coincide, entra el importador
guiado por datos, con autodetección y un asistente de confirmación.

## 7.4 Autodetección (sondeo)

Sobre los primeros 64 kB, en este orden:

| Paso | Qué detecta | Cómo |
|---|---|---|
| 1 | Codificación | BOM; si no, validez UTF-8; si falla, latin-1 con aviso |
| 2 | Fin de línea | CRLF / LF / CR |
| 3 | **Delimitador** | candidatos `, ; \t \| espacio`; se puntúa cada uno por **consistencia del número de campos** entre líneas, no por frecuencia. `csv.Sniffer` de la biblioteca estándar es poco fiable con estos ficheros y no se usa |
| 4 | **Separador decimal** | si el delimitador es `;` y hay tokens `\d+,\d+`, el decimal es coma. Se verifica que ninguna interpretación deje campos no numéricos que la otra sí parsea |
| 5 | Comillas y escapes | `"` / `'`, doblado o barra invertida |
| 6 | Estructura | primera línea de datos = primera cuyos campos son mayoritariamente numéricos; la anterior son nombres; si entre nombres y datos hay una línea **no numérica y corta**, es fila de unidades |
| 7 | Preámbulo | líneas antes de los nombres → metadatos (clave-valor si tienen `:` o `=`) |
| 8 | Columna de tiempo | ver §7.5 |
| 9 | Tipo por columna | entero, decimal, enum de texto, booleano, constante, vacía |
| 10 | Roles | diccionario de sinónimos, ver §7.7 |

El paso 4 es el que más a menudo se hace mal y el más importante en Europa: un
CSV español típico es `;` con coma decimal, y leerlo con la configuración
anglosajona convierte `12,5` en dos columnas.

La detección es **una propuesta, no un hecho**: todo pasa por el asistente de
§7.8 antes de cargarse.

## 7.5 Columna de tiempo

Casos que hay que soportar, todos vistos en logs reales:

| Caso | Ejemplo | Tratamiento |
|---|---|---|
| Hora del día | `18:30:35.506` | como el formato nativo; fecha desde metadatos o desde el nombre del fichero |
| ISO-8601 | `2026-07-29T18:30:35.506Z` | directo, con zona horaria |
| Epoch | `1785000635.506` / `1785000635506` | se distingue s de ms por magnitud |
| Relativo | `0.000`, `0.050`, … | segundos o ms desde el inicio; la unidad se detecta por el paso |
| Contador de muestras | `0, 1, 2, …` | se convierte con la frecuencia declarada por el usuario |
| **Sin columna de tiempo** | — | el usuario declara la frecuencia de muestreo; se sintetiza el eje y se marca el log como *tiempo sintético* |
| Varias columnas | `date` + `time` | se combinan |
| Distancia en lugar de tiempo | `lap_distance` | eje X alternativo desde el principio (encaja con E2.5) |

Reglas: si el eje es sintético o el reloj no es fiable, el log se marca igual que
los logs internos de la ECU (`01-formato-log.md` §1.5) y la vista concatenada
exige desfase manual. Nunca se finge precisión temporal que no existe.

## 7.6 Unidades declaradas en el propio fichero

Muchos exportadores traen la unidad en el nombre o en una fila dedicada:

```
Time,RPM [rpm],CLT (°C),MAP (kPa),AFR
0.000,850,92.4,32.6,14.6
```

o

```
Time,RPM,CLT,MAP,AFR
s,rpm,C,kPa,ratio
0.000,850,92.4,32.6,14.6
```

El importador extrae la unidad de `[...]`, `(...)`, tras `_` o de la fila de
unidades, y la resuelve contra el catálogo de `06-sistema-de-unidades.md` §7 con
un diccionario de alias (`C`, `degC`, `Celsius`, `°C` → °C; `kph`, `km/h`, `KPH`
→ km/h). Con la unidad de origen conocida, el valor se convierte a **canónica** y
todo el sistema de unidades intercambiables funciona igual que con el formato
nativo.

Si la unidad no se puede resolver, la dimensión queda `unknown`, se muestra el
valor en crudo y el selector de unidad se desactiva: la misma regla que protege
el riesgo R1.

## 7.7 Roles semánticos: el catálogo

Un rol es un identificador estable, con **dimensión esperada** y **rango
plausible**, que los perfiles y detectores usan en lugar de un ID de fabricante.
Los roles con `[n]` admiten índice (banco, cilindro, sensor, rueda).

**Hasta dónde llega la cobertura.** Este catálogo equaliza los canales
ESTÁNDAR entre fabricantes; no aspira a cubrirlos todos. Un log de 475 canales
con 155 asignados y 320 sin rol es un resultado bueno, y un canal sin rol se
resuelve con un perfil a `id_nativo`, no añadiendo roles. El razonamiento
completo y sus tres consecuencias prácticas están en
[`04-perfiles-motorsport.md`](04-perfiles-motorsport.md) «Hasta dónde llega la
cobertura por rol»; se anota aquí porque esta es la sección que se lee al
implementar la asignación, y es donde se decide gastar esfuerzo de más.

| Grupo | Roles |
|---|---|
| Motor | `engine_speed`, `engine_load`, `throttle_position`, `throttle_pedal`, `manifold_pressure`, `manifold_temp`, `baro_pressure`, `air_mass_flow` |
| Mezcla | `lambda_measured[n]`, `lambda_target`, `stoichiometry`, `fuel_trim_short[n]`, `fuel_trim_long[n]` |
| Combustible | `injector_duty[n]`, `injector_pulsewidth[n]`, `fuel_pressure`, `fuel_pressure_differential`, `fuel_flow` |
| Encendido | `ignition_advance`, `ignition_advance_base`, `ignition_correction_total`, `dwell_time[n]` |
| Knock | `knock_level[n]`, `knock_count[n]`, `knock_threshold`, `knock_retard[n]` |
| Sobrealimentación | `boost_pressure_actual`, `boost_pressure_target`, `boost_output`, `wastegate_duty` |
| Térmico | `coolant_temp`, `oil_temp`, `intake_air_temp`, `exhaust_temp[n]`, `ecu_temp`, `gearbox_temp` |
| Presiones | `oil_pressure`, `brake_pressure`, `clutch_pressure` |
| Vehículo | `vehicle_speed`, `wheel_speed[n]`, `driven_wheel_speed`, `gear`, `distance` |
| Eléctrico | `battery_voltage`, `sensor_voltage[n]` |
| Estados | `limiter_active`, `cut_percentage`, `protection_level`, `protection_cause`, `launch_state`, `idle_state`, `boost_state`, `trigger_errors` |
| Dinámica (futuro) | `accel_lateral`, `accel_longitudinal`, `gps_lat`, `gps_lon`, `lap_number`, `lap_distance` |

Cada rol se declara así en `roles.toml`:

```toml
[roles.coolant_temp]
dimension  = "temperature"
plausible  = { min = 233.15, max = 423.15 }   # canónica: K (-40 a 150 C)
synonyms   = ["Coolant Temperature", "CLT", "ECT", "Water Temp",
              "Temp. Refrigerante", "EngineTemp", "TCoolant"]

[roles.knock_count]
dimension  = "count"
indexed    = true
monotonic  = "non_decreasing"   # es un acumulado: habilita el canal delta
synonyms   = ["Knock Count", "Knock Sensor {n} Knock Count", "KnockCount{n}"]
```

Tres cosas que este esquema habilita y que justifican el coste:

1. **Asignación automática** por sinónimos y por normalización del nombre
   (minúsculas, sin acentos, sin separadores), con emparejamiento difuso como
   último recurso y siempre confirmado por el usuario.
2. **Informe de plausibilidad**: si una columna asignada a `coolant_temp` tiene
   valores entre 0 y 1, el asistente lo señala antes de importar. Esto atrapa el
   fallo típico del importador genérico —mapear bien el nombre y mal la escala—
   antes de que llegue a una decisión de tuning.
3. **Canales derivados automáticos**: `monotonic = "non_decreasing"` es lo que
   hace que el delta de conteo de knock (`04-perfiles-motorsport.md` §4.2, P2) se
   cree solo, en cualquier formato.

`roles.toml` y los sinónimos son **datos versionados**: añadir compatibilidad con
la nomenclatura de otro fabricante es una entrada de fichero, no un cambio de
código.

## 7.8 Asistente de importación

Tres pasos, con previsualización viva en todos ellos:

1. **Formato** — delimitador, decimal, codificación, filas de cabecera y de
   unidades, todo precargado con la detección y editable. Previsualización de las
   10 primeras filas parseadas con el ajuste actual.
2. **Tiempo** — columna de tiempo detectada y su interpretación, o declaración de
   frecuencia si no hay. Muestra duración resultante, número de muestras y tasa
   media para que un valor absurdo se vea al instante.
3. **Canales** — tabla con: columna, nombre, tipo inferido, dimensión, unidad de
   origen, rol propuesto y una columna de avisos. Ordenable por «necesita
   atención». Se puede importar dejando canales sin rol: siguen siendo
   graficables, solo no participan en perfiles ni detectores.

Al terminar se ofrece **guardar como perfil de importación**.

## 7.9 Perfil de importación `.dlvimport`

Este es el fichero que produce `dlv_core/perfil_importacion.py` (FG-12), no un
boceto: está generado ejecutando `a_texto_toml()`. El boceto anterior de esta
sección usaba claves en inglés (`[fingerprint]`, `column_hash`, `[[channels]]`), y
se sustituye porque las claves de datos de este proyecto están en español, como en
`roles.toml` y `units.toml`. Que la especificación y el código se contradigan es
peor que cualquiera de las dos convenciones: el siguiente que lo implemente
seguiría el boceto.

```toml
version_esquema = 1
nombre = "MoTeC i2 export - coche 1"

[huella]
hash_columnas = "sha256:5261fc4f12e1616481782228a7f8997947db3ab83df24889f273189843dfcb36"
n_columnas = 3
delimitador = ","
codificacion = "utf-8"

[formato]
codificacion = { origen = "deducido", valor = "utf-8" }
delimitador = { origen = "deducido", valor = "," }
comilla = { origen = "deducido" }
decimal = { origen = "deducido", valor = "." }
fila_cabecera = { origen = "deducido", valor = 14 }
fila_unidades = { origen = "deducido", valor = 15 }
fila_datos = { origen = "deducido", valor = 16 }

[tiempo]
clase = { origen = "confirmado", valor = "relativo" }
columna = { origen = "deducido", valor = 0 }
columna_fecha = { origen = "deducido" }
frecuencia_hz = { origen = "deducido" }
nombre_columna = "Time"

[[canales]]
nombre = "Engine RPM"
dimension = { origen = "deducido", valor = "angular_speed" }
unidad_origen = { origen = "deducido", valor = "rpm" }
columna = 1

[[canales]]
nombre = "Coolant Temp"
dimension = { origen = "confirmado", valor = "temperature" }
unidad_origen = { origen = "confirmado", valor = "degC" }
columna = 2
```

Tres cosas que no estaban en el boceto y que la implementación necesitó:

- **`origen` en cada campo.** Un valor `deducido` se vuelve a deducir al reaplicar
  el perfil; uno `confirmado` sobrevive aunque el sondeo nuevo opine otra cosa. Sin
  esa distinción el perfil no guarda lo único que justifica guardarlo, que es el
  trabajo manual del usuario.
- **`nombre_columna` además de `columna`.** El boceto guardaba `column = 0`, un
  índice puro. Si el fichero de la semana siguiente trae una columna más al
  principio, ese índice apunta a otro canal y la columna de tiempo se reaplica
  sobre un dato cualquiera sin que nada falle. El nombre sobrevive al reordenado.
- **`version_esquema`.** Un perfil de una versión futura se rechaza con un mensaje
  en vez de leerse a medias.


La **huella de cabecera** es lo que convierte esto en una función usable: la
segunda vez que se abre un CSV con las mismas columnas, el perfil se aplica solo
y la importación es un doble clic. Sin huella, el asistente de tres pasos se
vuelve un peaje y el usuario abandona.

Si la huella coincide parcialmente (columnas añadidas o reordenadas), se aplica
lo que encaja y el asistente se abre solo con lo pendiente.

## 7.10 Robustez: casos que no deben abortar la carga

| Caso | Comportamiento |
|---|---|
| Filas de longitud variable | se rellena con vacío y se registra; no se aborta |
| Columnas duplicadas | se desambigua con sufijo y se avisa |
| Cabecera sin nombres | se nombran `col_1…col_n` |
| `NaN`, `inf`, `-inf`, `#N/A`, `NULL`, `---`, `n/a`, celda vacía | → valor ausente, **nunca 0** |
| Valor con unidad embebida (`12.5 psi`) | se extrae número y unidad |
| Separador de miles (`1 234,5` / `1,234.5`) | se normaliza según el decimal detectado |
| Columna de texto libre | → canal enum con diccionario autogenerado |
| Booleanos (`true/false`, `on/off`, `sí/no`) | → canal enum de 2 estados |
| Valores centinela de desbordamiento | según `units.toml`, marcados como no válidos |
| Marcas de tiempo no monótonas o duplicadas | se detecta, se avisa, se ofrece ordenar |
| Fichero con una sola fila de datos | se carga; los detectores se desactivan por falta de muestras |
| Fichero enorme sin columna de tiempo | se exige la frecuencia antes de cargar |

Toda anomalía va al **informe de importación** (E1.7), que se muestra sin
bloquear y queda consultable en el proyecto.

## 7.11 Cómo cambia la identidad de canal

Con formatos heterogéneos, el `ID` nativo deja de servir como clave única. La
identidad pasa a ser en capas, y el emparejamiento entre logs sigue este orden:

1. **Rol semántico** — `coolant_temp` de un Haltech empareja con `coolant_temp`
   de un MoTeC. Es el camino normal.
2. **`(formato, ID nativo)`** — para canales sin rol dentro del mismo formato;
   es lo que sigue haciendo funcionar el caso Haltech de las muestras.
3. **Nombre normalizado** — último recurso automático.
4. **Emparejamiento manual** del usuario, que se guarda en el proyecto y tiene
   prioridad sobre todo lo anterior.

Si dos logs traen el mismo rol con unidades de origen distintas (uno en °C, otro
en °F), **no hay conflicto**: ambos están en canónica y se superponen
directamente. Ese es el beneficio concreto de haber hecho primero el sistema de
unidades.

## 7.12 Impacto en los perfiles y detectores

Se reescriben las épicas E4 y E5 para operar por rol:

- Los 10 perfiles de fábrica se definen **por rol**, con reserva a ID nativo para
  los canales muy específicos de Haltech que no tienen rol universal (los cinco
  de `Transient Throttle`, los términos PID de boost).
- Los 18 detectores se definen por rol. `D1 — evento de knock` pasa a ser
  «delta de `knock_count[n]` > 0», válido en cualquier formato.
- La autosugerencia de perfil (E4.5) puntúa por **cobertura de roles**: «perfil
  Knock: 7 de 9 roles disponibles».
- Un perfil declara sus roles `requeridos` y `opcionales`, y se degrada
  elegantemente ocultando los paneles sin datos en lugar de fallar.

## 7.13 Rendimiento del camino genérico

El camino nativo es un CSV de enteros sin comillas, trivialmente paralelizable.
El genérico puede traer decimales, comillas y texto, y es más lento. Presupuestos
separados y honestos:

| Camino | Presupuesto |
|---|---|
| Nativo (enteros, sin comillas) | ≥ 100 MB/s agregado |
| Genérico numérico (decimales, sin comillas) | ≥ 60 MB/s agregado |
| Genérico con comillas o texto | ≥ 25 MB/s agregado |

Una vez pasado el sondeo, el parseo se delega a Polars con los parámetros
detectados (`separator`, `decimal_comma`, `null_values`, `schema_overrides`), así
que el camino genérico también corre en el motor compilado y no en bucles de
Python. Ver `03-arquitectura.md` §3.6.

## 7.14 Formatos previstos tras la v1.0

Añadir cada uno debería ser un descriptor y un puñado de sinónimos:

| Formato | Nivel | Nota |
|---|---|---|
| Haltech NSP CSV | 1 | implementado en v1.0 |
| CSV genérico | 2 | implementado en v1.0 |
| Link G4/G5 CSV, ECUMaster, TunerStudio/MegaSquirt `.msl` | 1 | texto; descriptor puro |
| MoTeC i2 exportación CSV | 1 | descriptor con fila de unidades |
| AiM/RaceStudio exportación CSV | 1 | descriptor |
| MoTeC `.ld` / `.ldx` | binario | necesita gancho de código; post-v1 |
| VBOX `.vbo` | 1 | texto con preámbulo largo |
| Parquet / Arrow | 1 | trivial; útil para reimportar exportaciones propias |

## 7.15 Riesgo específico del importador genérico

Un importador genérico puede **acertar en la sintaxis y equivocarse en el
significado**: mapear bien el nombre y mal la escala, y presentar un número
plausible pero falso. Es el mismo riesgo R1 con otra puerta de entrada.

Mitigaciones, todas obligatorias:

1. Ninguna importación se completa sin pasar por la previsualización del paso 3.
2. El informe de plausibilidad compara cada rol contra su rango declarado.
3. Los canales sin dimensión resuelta se muestran en crudo, sin unidad y sin
   selector.
4. Los detectores de severidad crítica **se desactivan** en un log cuyos roles
   implicados provengan de asignación difusa no confirmada por el usuario.
   Preferimos no avisar a avisar en falso, porque una alerta falsa repetida
   enseña al usuario a ignorar las alertas.

   El criterio vive en `[desactivacion_automatica]` de `data/umbrales.toml`
   (`severidades_afectadas = ["critica"]`) y lo aplica
   `dlv_core.activacion_detectores` (F3-08). **Son cuatro detectores, no tres.**
   Este párrafo enumeraba «(D4, D10, D12)», que son los que tienen
   `severidad = "critica"` fija; F3-08 añade **D13**, que no tiene `severidad`
   sino `severidad_por_nivel` con `3 = "critica"`. Se incluye a propósito: si el
   rol `protection_level` se emparejó por parecido, una crítica de nivel 3
   afirma que la ECU está protegiendo el motor sobre un canal que puede estar
   midiendo otra cosa, y ese es el aviso falso de mayor consecuencia de los 18.
   La enumeración anterior era incompleta, no incorrecta.

   Y el estado que se publica distingue **tres** casos, no dos: activo,
   desactivado por precaución (el rol está y no está confirmado — el usuario lo
   arregla con un clic) y no ejecutable (el log no trae el canal — no hay nada
   que confirmar). Colapsar los dos últimos dejaría al usuario sin saber si le
   falta un canal o le falta una confirmación, que son dos acciones distintas.
