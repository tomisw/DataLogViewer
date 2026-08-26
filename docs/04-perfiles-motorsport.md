# 04 — Perfiles de análisis, detectores y alertas para ECU tuning y motorsport

> Todos los canales citados existen en el AutoLog de muestra con el nombre
> indicado. **Los perfiles y detectores se resuelven por rol semántico**
> (`engine_speed`, `knock_count[n]`, `coolant_temp`…), con reserva al `ID` nativo
> para los canales muy específicos de Haltech que no tienen equivalente
> universal. Los nombres de este documento son la lectura humana del rol; el
> catálogo de roles está en
> [`07-formatos-y-csv-generico.md`](07-formatos-y-csv-generico.md) §7.7.
>
> Esa indirección es lo que hace que estos diez perfiles funcionen igual sobre un
> log de Haltech, uno de MoTeC o un CSV escrito a mano. Un perfil declara sus
> roles **requeridos** y **opcionales**, y oculta los paneles sin datos en lugar
> de fallar.
>
> Las unidades de los umbrales de este documento se expresan en la unidad de
> lectura habitual del tuner, pero **se almacenan en canónica** y se muestran en
> la unidad que el usuario tenga activa
> ([`06-sistema-de-unidades.md`](06-sistema-de-unidades.md) §6.3).

## 4.1 Por qué perfiles y no gráficos a mano

El AutoLog de muestra tiene **475 canales**, de los cuales una parte importante
son sensores no instalados o diagnósticos internos (ver `01-formato-log.md`
§1.11). Pedir a un tuner que construya su vista canal a canal cada vez es la
principal razón por la que las herramientas de este tipo se abandonan.

Un **perfil** es un fichero versionable que define: paneles, canales por panel,
escalas y unidades, límites de alerta, detectores activos y eje X preferido.
Aplicar un perfil es un clic. Al abrir un log, la app propone los perfiles cuyos
canales están presentes **y activos** (E4.5).

## 4.2 Perfiles de fábrica

### P1 — Fuel / Lambda (cierre del lazo de mezcla)

El perfil más usado. Objetivo: ver de un vistazo si la mezcla sigue al objetivo.

| Panel | Canales |
|---|---|
| Carga | `RPM`, `Throttle Position`, `Manifold Pressure` |
| Mezcla | `Wideband O2 1`, `Target Lambda`, **λ error** (canal matemático), `Wideband O2 Overall` |
| Correcciones | `O2 Control Bank 1 Short Term Fuel Trim`, `O2 Control Bank 1 Long Term Fuel Trim`, `Fuel MAP Correction`, `Fuel Coolant Temperature Correction` |
| Inyección | `Injection Stage 1 Average Duty Cycle`, `Injector 1 On Time`, `Injector Pressure Differential`, `Fuel Pressure Expected` |
| Estado | carriles: `Decel Cut State`, `Engine Protection Cause` |

Alertas por omisión: λ error > ±4 % con TPS > 70 %; *duty* de inyección > 85 %;
`Injector Pressure Differential` fuera de banda.

### P2 — Knock / detonación

El perfil que evita motores rotos. Objetivo: no perder ni un evento.

| Panel | Canales |
|---|---|
| Carga | `RPM`, `Manifold Pressure`, `Throttle Position` |
| Knock | `Knock Sensor 1 Knock Level`, `Knock Sensor 2 Knock Level`, `Knock Threshold`, `Knock Sensor 1/2 Knock Signal` |
| Conteos | `Knock Sensor 1 Knock Count`, `Knock Sensor 2 Knock Count` (**delta**, no acumulado) |
| Respuesta | `Knock Control Bank 1/2 Ignition Correction`, `Knock Control Bank 1/2 Long Term Trim`, `Ignition Angle` |
| Contexto | `Intake Air Temperature`, `Coolant Temperature`, `Wideband O2 1` |
| Estado | carriles: `Knock State`, `Knock Detection Active State` |

Detalle importante: `Knock Sensor N Knock Count` es un **contador acumulado**
(rango hasta 50 000). Un gráfico de la señal cruda es una escalera ilegible. El
perfil crea automáticamente el canal matemático **delta por muestra**, que es lo
que hay que ver, y el detector se dispara sobre el delta > 0.

El renderizado del conteo debe usar decimación **por suma del delta**, no
min/max, para que el nivel de zoom no oculte eventos aislados.

### P3 — Boost control

| Panel | Canales |
|---|---|
| Presión | `Boost Control Actual Pressure`, `Boost Control Target Pressure`, `Boost Control Target Pressure (Corrected)`, `Boost Pressure Error` |
| Salida | `Boost Control Output`, `Boost Control Solenoid Duty Cycle` |
| Términos PID | `Boost Control Proportional Output`, `Boost Control Integral Output`, `Boost Control Derivative Output`, `Boost Control Closed Loop Base Output` |
| Trims | `Boost Control Short Term Trim`, `Boost Control Long Term Trim` |
| Estado | carriles: `Boost Control State`; alerta: `Overboost Cut Max Pressure` |

Métricas calculadas por tirada: **sobreoscilación** (% sobre objetivo), **tiempo
de establecimiento** al ±3 %, **error estacionario**, y saturación del actuador
(% de tiempo con salida en 0 % o 100 %). Son los cuatro números con los que se
afina un PID de boost, y hoy se sacan a ojo.

### P4 — Ignition

`Ignition Angle`, `Base Ignition Angle`, `Ignition Correction Total`,
`Coolant Temperature Ignition Correction`, `Air Temperature Ignition Correction`,
`Post Start Ignition Correction`, `Transient Throttle Ignition Correction`,
`Knock Control Bank 1 Ignition Correction`, `Ignition 1 Duty Cycle`,
`Ignition 1 On Time` (tiempo de carga de bobina), `Ignition Coil Power Supply`.

Alerta específica: **avance total distinto de base + suma de correcciones** →
indica una corrección no contemplada o un límite actuando; es un diagnóstico que
detecta configuraciones sorpresa.

### P5 — Transient / tip-in

Los logs internos de muestra dedican 5 de sus 25 canales a esto, señal de que es
un área que el usuario afina activamente.

`Throttle Position Derivative`, `Transient Throttle Load Derivative`,
`Transient Throttle Fuel Enrichment Rate`, `Transient Throttle Fuel Disenrichment Rate`,
`Transient Throttle Enrichment/Disenrichment Load Derivative`,
`Transient Throttle Enrichment Start Load`, `Transient Throttle Current Ignition Correction`,
con `Wideband O2 1` y `Target Lambda` como referencia.

Detector propio: **excursión de λ tras un tip-in**. Se localizan los flancos de
`Throttle Position Derivative` por encima de umbral y se mide la desviación
máxima de λ en la ventana siguiente. Devuelve una lista ordenada de los peores
tip-ins del log, que es exactamente el ciclo de trabajo para calibrar el
enriquecimiento transitorio.

### P6 — Idle control

`Idle Control target RPM`, `RPM`, `Idle Control RPM error`, `Idle Control Output`,
términos P/I/D, `Idle Control Short Term Trim`, `Idle Control Long Term Trim`,
`Idle Control Ignition Correction`, `Idle Control Min Output`, carril
`Idle Control State`, más `Thermofan 1 Idle Up Active` y `Air Con Idle Up Active`.

Métricas: desviación RMS respecto al objetivo, tiempo de recuperación tras
carga, oscilación (¿hay ciclo límite?).

### P7 — Trigger / salud de sincronización

Perfil de diagnóstico, el que resuelve los fallos intermitentes:
`Trigger System Errors` (máscara), `Trigger System Error Count`,
`Trigger Synchronisation Level`, `Trigger Sync Level Status`,
`Trigger Synchronisation State`, `Trigger Sync Offset`, `Trigger Tooth Count`,
`Tooth Period At Error`, `Previous Tooth Period At Error`,
`Sync Offset Difference At Error`, `Home Tooth Count At Error`,
`Trigger Voltage`, `Home Voltage`, `Home percentage of valid travel`,
`Worst Home percentage of valid travel`.

Este es el perfil que justifica la vista **concatenada**: el error aparece una
vez cada veinte logs de 10 segundos.

### P8 — Salud del motor y protecciones

`Coolant Temperature`, `Oil Temperature`, `Oil Pressure`, `Intake Air Temperature`,
`ECU Temperature`, `Battery Voltage`, `Fuel Pressure Expected`, más carriles de
`Engine Protection Severity Level`, `Engine Protection Cause` (máscara de bits),
`Engine Protection Ignition Retard`, `Engine Protection Boost Correction`,
`Engine Protection Lambda Fuel Enrichment`, `Cut Percentage`,
`RPM Limiter Active`, `Engine Limiter Active`.

Regla de negocio: **presión de aceite mínima función del régimen**, no un valor
fijo. El detector usa una curva editable (p. ej. 1 bar + 1 bar por cada 1 000 rpm)
en lugar de un umbral plano, porque un umbral plano da falsos positivos en
ralentí y falsos negativos a 7 000 rpm.

### P9 — Diagnóstico de sensores

`AVI1…AVI10 Voltage`, `Synced Pulse Input 1…4`, `Diagnostic Analogue 5V rail`,
`Diagnostic ratiometric voltage reference error`,
`Diagnostic absolute voltage reference error`,
`Diagnostic absolute-ratiometric discrepancy`, `Battery Voltage`.

Detectores: canal pegado a un valor (como `Oil Temperature` en la muestra),
saturación en el extremo del rango, ruido excesivo, valores centinela de
desbordamiento.

### P10 — Launch control

`Launch Control State` (carril, códigos −101…1), `Launch Control RPM Error`,
`Launch Control End RPM`, `Launch Control Fuel Correction`,
`Launch Control Ignition`, `Cut Percentage`, `RPM`,
`Vehicle Speed Drive Train Sensor`, `Driven Wheel Speed`.

### Hasta dónde llega la cobertura por rol
Equalizar los canales ESTÁNDAR entre fabricantes está bien y es la razón de ser
de este catálogo. Pero que queden canales sin rol **no es un drama ni un
problema a resolver**: el usuario de esta aplicación es un tuner, sabe qué es
cada canal de su ECU, y si le hace falta un panel con un canal exótico se hace
un perfil y ya está.

Consecuencia práctica, para no gastar recursos de más:

- **No se persigue el 100 % de cobertura.** Un log de 475 canales con 155
  asignados y 320 sin rol es un resultado BUENO, no uno a medias.
- **No se inventa un rol para un canal que solo existe en un fabricante.**
  P5 (transient tip-in) va al 30 % por rol porque sus canales son internos de
  Haltech y no tienen equivalente en ningún otro sitio: eso no se arregla
  añadiendo roles, se arregla con la reserva a `id_nativo`, que existe
  exactamente para esto.
- **La prioridad es el canal que un detector CRÍTICO necesita**, no el catálogo
  completo. Un rol que no alimenta ningún detector ni ningún perfil de fábrica
  es trabajo sin destinatario.

## 4.3 Detectores de eventos

Todos los detectores comparten el mismo motor y el mismo modelo de resultado
(`{ tipo, severidad, t_inicio, t_fin, valor_pico, contexto }`), así que añadir
uno nuevo es un fichero de configuración, no código.

### Los umbrales son configurables, no constantes

**Todos los números de esta sección son valores por omisión**, no límites fijos.
Viven en `data/umbrales.toml` y se sustituyen con esta precedencia, la misma que
las unidades (`06-sistema-de-unidades.md` §6.9) y por el mismo motivo:

1. **Anulación por canal** — «este canal con este límite y no otro».
2. **Perfil activo** (`.dlvprofile`) — es donde un equipo fija sus criterios y
   los comparte como un fichero suelto.
3. **Preferencias de usuario.**
4. **`data/umbrales.toml`** — por omisión.

El criterio de cuándo un motor está en problemas depende del motor, del
combustible y de para qué se usa. Un umbral cableado en el código sería una
opinión disfrazada de física, y además convertiría cada ajuste en un cambio de
código con su ciclo de revisión.

Los umbrales se guardan en **unidad canónica**, así que se pueden editar en la
unidad que el usuario tenga activa sin reescribir nada (§6.11).

### Primitivas

| Primitiva | Parámetros | Uso |
|---|---|---|
| Umbral con histéresis | entrada, salida, permanencia mínima | evita el rebote en el umbral |
| Pico local | prominencia mínima, ventana | picos reales, no ruido |
| Derivada | ventana, umbral | tip-in, caída de presión, subida de temperatura |
| Tiempo por encima | umbral, acumulado | «45 s por encima de 105 °C» |
| Conteo de cruces | umbral | oscilación |
| Delta de contador | — | conteos de knock, contadores de error |
| Banda | mín, máx | λ dentro de ventana |
| Compuesto | AND/OR de los anteriores | condicionales de contexto |
| Fuera de máscara | bits de interés | `Engine Protection Cause`, `Trigger System Errors` |

La **permanencia mínima** es la que evita el problema clásico: con un log a 20 Hz
y ruido, un umbral desnudo genera cientos de falsas alertas y el usuario apaga la
función. Por omisión, 3 muestras o 100 ms, el mayor de los dos.

### Detectores de motorsport de fábrica

| # | Detector | Condición | Severidad |
|---|---|---|---|
| D1 | Evento de knock | delta de `Knock Sensor N Knock Count` > 0 | alta; crítica si RPM>4000 y MAP>150 kPa |
| D2 | Knock sobre umbral | `Knock Level` > `Knock Threshold` con permanencia | media |
| D3 | Retardo por knock activo | `Knock Control Bank N Ignition Correction` < −1° | media |
| D4 | Mezcla pobre en carga | λ > `Target Lambda` × 1,04 AND TPS > 70 % AND RPM > 3000 | **crítica** |
| D5 | Mezcla rica sostenida | λ < objetivo × 0,93 durante > 2 s en carga | baja |
| D6 | Sobrepresión | `Boost Control Actual Pressure` > `Overboost Cut Max Pressure` × 0,97 | alta |
| D7 | Sobreoscilación de boost | pico > objetivo + 5 % tras subida | media |
| D8 | Saturación de inyectores | *duty* > 85 % | alta; crítica > 95 % |
| D9 | Sobretemperatura de refrigerante | umbral con permanencia de 3 s | alta |
| D10 | Presión de aceite baja | por debajo de la curva mínima en función de RPM | **crítica** |
| D11 | Baja tensión de batería | < 11,5 V con motor en marcha | media |
| D12 | Error de trigger | cualquier bit de `Trigger System Errors`, o incremento de `Trigger System Error Count` | **crítica** |
| D13 | Protección de motor activa | `Engine Protection Severity Level` > 0 | según nivel |
| D14 | Corte activo | `Cut Percentage` > 0 fuera de limitador esperado | media |
| D15 | Excursión de λ en tip-in | ver P5 | media |
| D16 | Canal muerto o pegado | varianza nula en todo el log con el motor en marcha | informativa |
| D17 | Valor centinela | muestra igual a un centinela de desbordamiento conocido | informativa |
| D18 | Hueco de muestreo | dt > 3× mediana | informativa |

### Topes de alerta (configuración de usuario)

Cada canal admite: **límite de aviso**, **límite crítico**, **banda objetivo** y
**curva de límite en función de otro canal** (el caso de la presión de aceite).
Los límites se dibujan como líneas y bandas sobre el panel, y se resumen en el
**panel de incidencias**: lista ordenada por severidad, con conteo, duración
total y salto al instante. Es la pantalla que responde «¿ha ido todo bien?» en
cinco segundos, que es el caso de uso más frecuente.

Los límites viven en el perfil, así que un equipo puede tener un
`limites-motor-A.dlvprofile` y compartirlo.

## 4.4 Segmentación automática

Sin segmentación, el usuario busca sus tiradas a mano en un log de 40 minutos.
Detectores de segmento:

| Segmento | Criterio |
|---|---|
| **Tirada a plena carga (WOT)** | TPS > 80 % y RPM creciente durante > 1,5 s |
| Ralentí | RPM en banda del objetivo de ralentí y TPS ≈ 0 |
| Arranque | RPM de 0 a > 500 con `Fuel Cranking` activo |
| Deceleración | `Decel Cut State` activo o TPS ≈ 0 con RPM > 2000 |
| Calentamiento | refrigerante por debajo del objetivo |

Las tiradas detectadas se listan en un panel con su resumen (RPM inicial/final,
MAP máximo, λ mínimo, eventos de knock, duración) y se pueden **superponer entre
sí con eje X = RPM**. Comparar la tirada 3 con la tirada 7 en dos clics es la
funcionalidad que más tiempo ahorra a un tuner de banco.

## 4.5 Canales matemáticos de biblioteca

| Canal | Fórmula | Nota |
|---|---|---|
| λ error | `{Wideband O2 1} / {Target Lambda} − 1` | en %, el canal central de P1 |
| AFR | `λ × {Fuel Tuning Current Stoichiometry}` | usa la estequiometría del log, no 14,7 |
| Presión de boost relativa | `{Manifold Pressure} − P_ref` | `P_ref` según `01-formato-log.md` §1.9 |
| Relación de presiones | `{Manifold Pressure} / P_ref` | carga del turbo |
| Delta de conteo de knock | `Δ{Knock Sensor N Knock Count}` | creado automáticamente por P2 |
| Marcha estimada | agrupación de `{Vehicle Speed}/{RPM}` | no existe canal `Gear` en el log |
| Deslizamiento | `{Driven Wheel Speed} − {Vehicle Speed}` | tracción |
| Error de boost | `{Boost Control Actual Pressure} − {Boost Control Target Pressure}` | |
| Delta entre logs | `{canal}@logA − {canal}@logB` | comparación antes/después, requiere alineación |

El evaluador resuelve el multi-tasa por retención del último valor, con límite de
validez: si el canal más lento tiene 200 ms de periodo y la ventana de validez es
de 100 ms, el resultado es hueco en lugar de un número inventado.

## 4.6 Análisis tabular RPM×MAP

La entrega de mayor valor para tuning. Malla con los mismos ejes que la tabla de
la ECU (configurable, y por defecto la deducida de los rangos del log):

1. **Mapa de calor de λ error**: color por desviación media, y por celda:
   número de muestras, desviación típica, mínimo y máximo.
2. **Tabla de corrección de combustible**: el porcentaje a aplicar por celda.
   Reglas duras:
   - Las celdas con menos de N muestras (por omisión 20) **no se rellenan**, se
     marcan como sin datos. Un valor calculado con 2 muestras es peor que ninguno.
   - Las celdas con desviación típica alta se marcan como poco fiables.
   - Se excluyen las muestras en transitorio, en corte, en protección de motor y
     durante el retardo de transporte del sensor de λ (configurable, por omisión
     150 ms tras un cambio brusco de carga). Sin este filtro, la tabla generada es
     basura y este es el error más común en herramientas que ofrecen esta función.
   - Exportación a CSV y al portapapeles como malla pegable.
3. **Mapa de calor de avance de encendido** y de **densidad de eventos de knock**
   sobre la misma malla → responde «¿en qué zona del mapa estoy detonando?».
4. **Comparación de dos logs celda a celda**, para verificar que el cambio hizo
   lo esperado.

## 4.7 Informe de sesión

HTML autocontenido, un fichero, sin dependencias externas: cabecera del log,
duración, tiradas detectadas con su resumen, tabla de incidencias por severidad,
gráficos de los perfiles aplicados y las tablas de calor. Es lo que un tuner
manda al cliente o el ingeniero archiva tras la sesión.

## 4.8 Ideas evaluadas y aplazadas a post-v1

Se documentan para que la decisión sea explícita y no se reabra en cada reunión:

| Idea | Por qué se aplaza |
|---|---|
| FFT del canal `Knock Input 1 FFT.` / espectrograma | el canal existe pero su formato interno es desconocido; necesita muestras y documentación. Alto valor, alta incertidumbre |
| Correlación con datos de GPS/vuelta | no hay canales de GPS en las muestras |
| Estimación de potencia en rueda | requiere masa, relaciones y coeficientes que no están en el log; sería un número con aspecto de dato y calidad de estimación |
| Alertas en vivo | depende de la telemetría de v2 |
| Detección automática de anomalías por aprendizaje | sin corpus etiquetado suficiente; los detectores por regla son explicables, y en tuning la explicabilidad importa más que la cobertura |
