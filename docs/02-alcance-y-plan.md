# 02 — Alcance y plan de proyecto

## 2.1 Resumen ejecutivo

DataLogViewer es un visor y analizador de logs de ECU para **tuning y
motorsport**. Se distribuye como **paquete portable** (carpeta en ZIP, sin
instalación) y su **núcleo en Python** sirve tanto a la aplicación de escritorio
como a una versión de navegador y, en fase posterior, móvil.

La propuesta de valor no es «otro graficador»: es que un tuner abra dos o tres
logs —de cualquier formato CSV—, seleccione un **perfil de análisis**
(«Fuel/Lambda», «Knock», «Boost») y en menos de 30 segundos vea las señales
relevantes alineadas, en las unidades que él usa, con las tiradas a plena carga
detectadas automáticamente y una lista de incidencias enlazada al instante exacto.

- **Duración a v1.0**: 26 semanas en 8 fases.
- **Base tecnológica**: Python 3.12+ con el trabajo por muestra delegado a
  Polars y NumPy; interfaz web con renderizador WebGL2; contenedor `pywebview`.
  Justificación y costes en `03-arquitectura.md` §3.1 y §3.11.
- **Entregable v1.0**: paquete portable Windows/Linux/macOS, sin instalación
  (< 95 MB en ZIP; 176 de los ~240 MB sin comprimir son el runtime de
  Polars, ver §2.6), más una versión de navegador sobre el mismo núcleo.
- **Riesgo principal**: escalas y unidades mal interpretadas —21 de 34 tipos del
  formato nativo sin confirmar, más el riesgo equivalente en el importador
  genérico— mitigado con dimensión canónica, `confidence` explícito e informe de
  plausibilidad.

## 2.2 Objetivos

| # | Objetivo | Métrica de éxito |
|---|---|---|
| O1 | Comparar logs en paralelo y concatenados | 8 logs simultáneos con alineación por tiempo, RPM o evento |
| O2 | Rendimiento a escala real | 60 fps de pan/zoom con 16 canales y 5 M puntos/canal |
| O3 | Portabilidad | paquete portable, 0 pasos de instalación, mismo núcleo en la versión de navegador |
| O4 | Facilidad de uso | ≤ 5 clics y < 30 s desde abrir la app hasta un perfil con 2 logs superpuestos |
| O5 | Valor para tuning | tabla de corrección λ sobre malla RPM×MAP exportable, detección de knock y de tiradas |
| O6 | **Unidades intercambiables** | toda dimensión con al menos dos unidades; cambio global, por dimensión y por canal, sin recargar el log ni reescribir umbrales |
| O7 | **Cualquier CSV** | un CSV arbitrario se importa y queda analizable con los mismos perfiles y detectores, sin escribir código |
| O8 | **Mantenible por el propietario** | ≥ 70 % del código en Python; el núcleo se puede leer, depurar y extender sin tocar TypeScript |

## 2.3 No objetivos de la v1.0

Declararlos evita el desvío de alcance más habitual en herramientas de tuning:

- **No** se escribe en la ECU. Solo lectura de logs. Ninguna función de flasheo.
- **No** hay telemetría en vivo en v1.0 (se diseña la arquitectura para
  permitirla en v2, ver §2.11).
- **No** hay edición de mapas de la ECU. Se **genera** una tabla de corrección
  exportable (CSV/portapapeles) que el usuario aplica en su software de tuning.
- **No** hay cuenta de usuario, nube ni sincronización. Los ficheros de proyecto
  son locales y compartibles a mano.
- **No** se soportan otros fabricantes de forma nativa en v1.0, pero la ingesta es una
  **capa de formatos de dos niveles** con descriptores declarativos, de modo que
  añadir MoTeC, AiM, Link o MegaSquirt sea un fichero de datos y no código
  (E14, `07-formatos-y-csv-generico.md` §7.14). Lo que la v1.0 **sí** entrega es
  el formato Haltech nativo y el importador de CSV genérico.

## 2.4 Usuarios y casos de uso

| Persona | Necesidad dominante | Caso de uso guía |
|---|---|---|
| **Tuner de banco/calle** | cerrar el lazo de λ rápido | abrir log de tirada, ver λ real vs objetivo sobre RPM×MAP, exportar corrección |
| **Ingeniero de pista** | comparar vueltas y configuraciones | superponer la tirada de antes y después del cambio, alineadas por RPM |
| **Piloto/propietario** | «¿ha ido todo bien?» | abrir log, ver panel de incidencias: knock, sobretemperatura, corte, error de trigger |
| **Diagnóstico** | encontrar el fallo intermitente | concatenar 20 logs internos de la ECU y buscar el instante del error de sincronización |

El caso 4 es el que justifica la vista concatenada: los logs internos de la ECU
son fragmentos de 7–15 segundos (como las muestras 2768/2769). Analizarlos de
uno en uno es inviable.

## 2.5 Alcance funcional por épicas

### E1 — Ingesta y modelo de datos
- E1.1 Parser del formato `%DataLog% 1.1` con toda la lista de verificación de `01-formato-log.md` §1.13.
- E1.2 Registro de dimensiones y unidades versionado (dimensión, conversión a canónica, confianza, centinelas).
- E1.3 Almacenamiento columnar por canal con base de tiempos propia (multi-tasa) y **tipo de dato por canal** (entero escalado, decimal, enum, máscara).
- E1.4 Indexado: clasificación `activo/constante/vacío/fuera de rango`, mín/máx/percentiles por canal.
- E1.5 Caché en disco en Parquet, con la pirámide persistida: la segunda apertura es casi instantánea.
- E1.6 Detección de huecos y marcas de discontinuidad.
- E1.7 **Capa de formatos de dos niveles** (descriptores nativos declarativos + importador genérico) e informe de importación con avisos.

### E2 — Motor de tiempo multi-log *(prioridad del cliente)*
- E2.1 **Vista paralela**: N logs, un eje X compartido, series superpuestas con color por log.
- E2.2 Modos de alineación:
  - reloj absoluto (cuando el log lo permite, ver §1.4),
  - relativo desde t=0 de cada log,
  - desfase manual arrastrando el log,
  - **anclaje por evento** (primer WOT, primer corte, activación de launch),
  - **autoalineación por correlación cruzada** de un canal de referencia (RPM).
- E2.3 **Vista concatenada**: unión de canales por la identidad en capas de E2.6, línea de tiempo virtual con desfase por segmento, marcas de frontera visibles y **sin interpolar** sobre las uniones.
- E2.4 Reordenación de segmentos por `Log Number` con desfase editable (obligatorio con epoch ficticia).
- E2.5 Eje X alternativo: **RPM**, velocidad o distancia en lugar de tiempo — imprescindible para comparar tiradas de duración distinta.
- E2.6 **Identidad de canal en capas** (rol semántico → `(formato, ID nativo)` → nombre normalizado → emparejamiento manual), que es lo que permite superponer un log de Haltech con uno de otro fabricante.
- E2.7 Resolución de conflictos: mismo rol con unidades de origen distintas → ambos a canónica y se comparan; escala incoherente → aviso, nunca mezcla silenciosa.

### E3 — Visualización y rendimiento *(prioridad del cliente)*
- E3.1 Renderizador WebGL con pirámide de decimación mín/máx (ver `03-arquitectura.md` §3.5).
- E3.2 Paneles apilados sincronizados, con arrastrar y soltar de canales entre paneles.
- E3.3 Ejes Y múltiples por panel, autoescala y escala fija bloqueable.
- E3.4 Cursor con tabla de valores; **doble cursor con delta** (Δt, Δvalor, pendiente).
- E3.5 **Carriles de estado** para los 75 canales enumerados y decodificación de máscaras de bits.
- E3.6 Zoom/pan por rueda, teclado y gesto; historial de zoom; «ajustar a selección».
- E3.7 Renderizado progresivo: silueta de baja resolución inmediata, refinamiento en segundo plano.
- E3.8 Modo oscuro y modo alto contraste para uso en pista con sol directo.

### E4 — Perfiles de análisis *(prioridad del cliente)*
- E4.1 Modelo de perfil: paneles, **roles semánticos**, unidades por dimensión, límites de alerta y detectores, en fichero versionable.
- E4.2 Perfiles integrados de fábrica (detallados en `04-perfiles-motorsport.md`).
- E4.3 Aplicación de perfil **por rol**, con reserva a `ID` nativo y degradación elegante ocultando los paneles sin datos.
- E4.4 Editor de perfiles, duplicado, importación/exportación y compartición como fichero suelto.
- E4.5 Autosugerencia por **cobertura de roles**: «perfil Knock: 7 de 9 roles disponibles».

### E5 — Detección de eventos y alertas *(prioridad del cliente)*
- E5.1 Detección de picos con histéresis y tiempo de permanencia mínimo (evita falsos positivos por una muestra de ruido).
- E5.2 **Topes de alerta** por canal: umbral, banda, y condicionales compuestos (`λ > objetivo+5 % AND TPS > 80 % AND RPM > 4000`). **Todos los umbrales son configurables**: valores por omisión en `data/umbrales.toml`, sustituibles por canal, por perfil o por preferencia de usuario, en esa precedencia (`04-perfiles-motorsport.md` §4.3). Ningún límite va cableado en el código.
- E5.3 Detectores derivados: derivada, media móvil, tiempo por encima de umbral, conteo de cruces.
- E5.4 Detectores específicos de motorsport: knock, sobreoscilación de boost, corte, protección de motor, error de trigger, λ pobre en carga (ver `04-perfiles-motorsport.md`).
- E5.5 **Panel de incidencias**: lista ordenada por severidad con salto al instante y al contexto.
- E5.6 Segmentación automática: detección de tiradas a plena carga, ralentí, arranque, deceleración.

### E6 — Canales matemáticos
- E6.1 Evaluador de expresiones sobre canales (`{Manifold Pressure}/{Barometric}`), con multi-tasa resuelto por retención.
- E6.2 Biblioteca de fórmulas: error de λ, relación de presiones, marcha estimada por relación velocidad/rpm, potencia estimada, δ entre logs.
- E6.3 Los canales matemáticos se guardan en el perfil y se recalculan al vuelo, no se persisten como datos.

### E7 — Análisis tabular y correcciones
- E7.1 Malla RPM×MAP configurable (los mismos ejes que la tabla de la ECU).
- E7.2 Mapa de calor de λ real vs objetivo con **número de muestras y dispersión por celda**.
- E7.3 **Tabla de corrección de combustible** exportable, con celdas de confianza insuficiente marcadas y nunca rellenadas por interpolación silenciosa.
- E7.4 Mapa de calor de avance de encendido y de eventos de knock sobre la misma malla.
- E7.5 Comparación de dos logs celda a celda (antes/después del cambio).

### E8 — Informes y exportación
- E8.1 Informe de sesión HTML autocontenido: resumen, tiradas, incidencias, gráficos.
- E8.2 Exportación de la vista actual a PNG/SVG y de los datos a CSV/Parquet.
- E8.3 Exportación de tablas de corrección al portapapeles en formato de malla pegable.

### E9 — Experiencia de uso *(prioridad del cliente)*
- E9.1 Arrastrar y soltar ficheros y carpetas; apertura múltiple.
- E9.2 Espacio de trabajo persistente: al reabrir, la app recupera logs, perfil, zoom y cursores.
- E9.3 Paleta de comandos y búsqueda difusa de canales entre 475 (sin ella, el selector es inservible).
- E9.4 Anotaciones y marcadores en la línea de tiempo, exportables con el proyecto.
- E9.5 Internacionalización ES/EN desde el primer día.
- E9.6 Onboarding: al abrir un log sin perfil, la app propone uno en lugar de mostrar un lienzo vacío.

### E10 — Portabilidad y distribución *(prioridad del cliente)*
- E10.1 Binario portable único por plataforma, sin instalador y sin escribir fuera de su carpeta si se ejecuta en modo portable.
- E10.2 Versión de navegador sobre el mismo backend Python (local o en la red del equipo).
- E10.3 Firma de binarios y actualizador opcional (desactivable, nunca obligatorio).
- E10.4 Asociación de extensión `.csv`/`.dlv` opcional y reversible.

### E11 — Calidad
- E11.1 Corpus de logs de prueba, incluidos los tres de muestra y ficheros deliberadamente corruptos.
- E11.2 Pruebas de propiedad del parser (*fuzzing* sobre la cabecera y las filas).
- E11.3 Pruebas de regresión de rendimiento en CI con presupuestos que fallan la compilación.
- E11.4 Pruebas de regresión visual del renderizador.

### E12 — Fundamentos de v2 (solo diseño en v1)
- E12.1 Interfaces preparadas para telemetría en vivo (ingesta por *streaming* en el mismo almacén columnar).
- E12.2 Móvil como cliente del backend Python; validación de una maqueta táctil.

### E13 — Sistema de unidades intercambiables *(prioridad del cliente)*

Detalle completo en `06-sistema-de-unidades.md`.

- E13.1 Catálogo de **dimensiones** con unidad canónica fija y unidades alternativas, en fichero de datos versionado.
- E13.2 Conversiones **afines** (`a·x+b`, imprescindible para temperatura), **recíprocas** (λ↔φ, periodo↔frecuencia, L/100 km↔mpg) y **parametrizadas por canal** (λ→AFR con la estequiometría del propio log).
- E13.3 **Semántica de punto / intervalo / tasa / varianza**: los deltas y las desviaciones usan solo la parte lineal, para que un Δ de 10 K sea 10 °C y no −263 °C.
- E13.4 Presión **absoluta o relativa** como cambio de origen combinable con cualquier unidad, con referencia constante, por canal o autodetectada.
- E13.5 Precedencia de selección: canal > dimensión del perfil > preset global > canónica.
- E13.6 Presets: SI, Métrico, Imperial, Motorsport EU, Motorsport US, y presets de usuario.
- E13.7 Selector de unidad en la interfaz a los tres niveles, con formato numérico y decimales por unidad, y locale ES/EN.
- E13.8 Umbrales y perfiles almacenados en canónica y editados en la unidad activa; cambiar de unidad no reescribe ni invalida nada.
- E13.9 Ticks y rejilla calculados en la unidad mostrada; unidad declarada en toda exportación e informe.
- E13.10 Dimensiones **compuestas** (`%/kPa` → `%/psi`) derivadas de las unidades activas.

### E14 — Extensibilidad de formatos e importación de CSV genérico *(prioridad del cliente)*

Detalle completo en `07-formatos-y-csv-generico.md`.

- E14.1 Sondeo y autodetección: codificación, fin de línea, **delimitador**, **separador decimal**, comillas, preámbulo, fila de nombres y fila de unidades.
- E14.2 Columna de tiempo en todas sus variantes: hora del día, ISO-8601, epoch s/ms, relativa, contador de muestras, **ausente** (frecuencia declarada), fecha y hora separadas, o distancia como eje.
- E14.3 Inferencia de tipo por columna y unidad declarada en el fichero (`RPM [rpm]`, `CLT (°C)` o fila de unidades) resuelta contra el catálogo de dimensiones.
- E14.4 **Catálogo de roles semánticos** con dimensión esperada, rango plausible y sinónimos, en fichero de datos versionado.
- E14.5 Asignación automática de roles e **informe de plausibilidad** que detecta el nombre correcto con la escala equivocada.
- E14.6 **Asistente de importación** de tres pasos con previsualización viva.
- E14.7 **Perfil de importación `.dlvimport`** con huella de cabecera, para que la segunda vez la importación sea un doble clic.
- E14.8 Robustez sin abortar: filas de longitud variable, columnas duplicadas, `NaN`/`#N/A`/`---`, unidad embebida en la celda, separador de miles, texto y booleanos como enums.
- E14.9 **Descriptores de formato nativo declarativos**: añadir un fabricante es un TOML, no código. El formato Haltech es el primer descriptor y la prueba de que basta.
- E14.10 Perfiles y detectores reescritos para operar **por rol**, independientes del fabricante.

### E15 — Explorador de logs: triaje de una carpeta *(prioridad del cliente)*

El problema que resuelve: tras una jornada de pista hay decenas de logs en una
carpeta y no hay forma de saber cuáles merecen análisis sin abrirlos uno a uno.
Abrir cada uno cuesta 4 s en el mejor caso, así que revisar 200 logs son trece
minutos de espera antes de empezar a trabajar. El explorador convierte esa
carpeta en una tabla ordenable.

- E15.1 Selección de una carpeta y **tabla de los logs que contiene**, una fila por log.
- E15.2 Una columna por métrica: máximo, mínimo, media o duración según qué tenga sentido para cada rol, más los metadatos del propio log (fecha, duración, número de muestras, formato).
- E15.3 **Métricas configurables**: el conjunto por omisión vive en un fichero de datos, y el usuario añade o quita columnas y lo conserva en su espacio de trabajo.
- E15.4 **Ordenar y filtrar por cualquier métrica** («λ mínima < 0,80», «más de 5 eventos de knock», «duración > 10 min»), que es lo que convierte la tabla en una herramienta de selección y no en un listado.
- E15.5 Abrir desde la tabla los logs elegidos, uno o varios, directamente en el espacio de trabajo.
- E15.6 Índice en disco con **huella (ruta, tamaño, fecha de modificación)**: la segunda vez que se abre la misma carpeta, la tabla es inmediata; solo se recalculan los logs que cambiaron o son nuevos.
- E15.7 Escaneo **incremental y cancelable**: las filas aparecen a medida que se calculan y la carpeta se puede explorar antes de que termine.

Cuatro reglas de diseño que no son negociables, porque cada una corresponde a una
forma concreta de mandar al usuario a analizar el log equivocado:

1. **Las columnas son roles, no nombres de canal.** Una carpeta mezcla logs
   nativos y CSV genéricos; `RPM`, `Engine Speed` y `N_motor` tienen que caer en
   la misma columna o la tabla no se puede ordenar. Depende de E14.4.
2. **Los agregados son exactos, no muestreados.** El resumen no estima: proyecta
   *solo las columnas que las métricas configuradas necesitan* y agrega sobre
   ellas enteras. Leer 6 columnas de 475 es barato de verdad —es la ventaja de un
   formato columnar—, y así el número de la tabla es el mismo que el de la vista
   completa. Un resumen aproximado que discrepa del log abierto destruye la
   confianza en la herramienta entera.
3. **Se ordena en canónica y se muestra en la unidad activa.** Si la ordenación
   usara el valor mostrado, una carpeta con un log en °C y otro en °F quedaría
   ordenada por un número sin significado común. Los agregados llevan además su
   clase de magnitud (E13): un máximo es un punto, un rango es un intervalo y una
   desviación típica es una varianza.
4. **Una celda sin dato se queda vacía, nunca a cero.** Un log que no registra
   knock no tiene «0 eventos de knock»: no tiene la columna. Mostrar 0 haría que
   el log más peligroso de la carpeta pareciera el más limpio.

## 2.6 Presupuestos de rendimiento (criterios de aceptación)

Máquina de referencia: portátil de 4 núcleos, 16 GB RAM, GPU integrada.
Presupuestos ajustados a la base Python; la comparación con la revisión 1 y su
justificación están en `03-arquitectura.md` §3.8.

| Métrica | Presupuesto | Cómo se mide |
|---|---|---|
| Apertura de log de 66 MB / 475 canales hasta el primer gráfico | **< 4,0 s** p95 | banco automatizado en CI |
| Parseo del camino nativo (enteros) | **≥ 100 MB/s** agregado | banco de microtest |
| Parseo genérico numérico / con texto | **≥ 60 / ≥ 25 MB/s** agregado | banco de microtest |
| Segunda apertura (caché Parquet) | **< 1000 ms** | banco automatizado |
| Pan/zoom con 16 canales × 5 M puntos | **≥ 60 fps**, sin fotograma > 20 ms | traza de fotogramas |
| Latencia del cursor a tabla actualizada | **< 16 ms** | traza de fotogramas |
| Pan/zoom que requiere cubos nuevos del backend | **< 120 ms** p95 | traza de red |
| **Cambio de unidad con 8 logs abiertos** | **< 100 ms**, sin recarga ni invalidación de caché | banco automatizado |
| **Indexado de una carpeta de 200 logs** (primera vez, en frío) | **< 60 s**, con filas apareciendo desde la primera | banco automatizado |
| **Reapertura de una carpeta ya indexada** | **< 500 ms** hasta la tabla completa | banco automatizado |
| **Resumen de un log de 66 MB** (6 métricas proyectadas) | **< 900 ms** | banco de microtest |
| Memoria residente con el log de 66 MB abierto | **≤ 3,5×** el tamaño del CSV | medida de RSS |
| Arranque en frío hasta ventana interactiva | **< 2,5 s** | banco automatizado |
| Tamaño del paquete portable | **< 260 MB sin comprimir / < 95 MB en ZIP** | comprobación de artefacto |
| 8 logs × 30 min en paralelo | abre y navega sin degradación perceptible | prueba manual guionizada |
| **Bucles por muestra en Python** | **cero** en `dlv-core` | banco + revisión (ADR-009) |

Estos presupuestos son **puertas de CI**, no aspiraciones. La E11.3 los hace
fallar la compilación cuando se superan. El último es el que mantiene sana la
arquitectura Python a lo largo del tiempo.

## 2.7 Fases e hitos

| Fase | Semanas | Contenido | Hito de salida |
|---|---|---|---|
| **F0 — Cimientos** | 1–2 | Andamiaje del repositorio, CI, ADRs cerrados, *spike* de rendimiento de Polars, corpus de pruebas, catálogos de dimensiones y roles, banco de rendimiento funcionando | **M0**: `pytest` y `npm test` verdes en las 3 plataformas; el banco publica métricas y el *spike* confirma o refuta el presupuesto de apertura |
| **F1 — Núcleo de datos, unidades y visor de un log** | 3–8 | E1, **E13 completa**, E3.1–E3.4, E3.6, E9.1, E9.3 | **M1**: se abre el AutoLog de 475 canales, se navega a 60 fps con 8 canales, y se conmuta °C↔°F↔K y kPa↔bar↔psi sin recargar |
| **FG — Formatos y CSV genérico** | 9–11 | **E14 completa** | **MG**: un CSV con `;`, coma decimal, fila de unidades y sin columna de tiempo se importa por el asistente, se guarda como `.dlvimport` y se reabre solo |
| **F2 — Multi-log** | 12–14 | E2 completa, E3.7 | **M2**: los tres logs de muestra en paralelo con autoalineación, 2768+2769 concatenados, y un log Haltech superpuesto con un CSV genérico emparejado por rol |
| **F3 — Motorsport** | 15–19 | E4, E5, E3.5, E6 | **M3**: perfil «Knock» detecta y lista los eventos de knock del corpus con 0 falsos negativos conocidos, en formato nativo y en CSV genérico |
| **F4 — Análisis avanzado** | 20–22 | E7, E8 | **M4**: tabla de corrección λ generada y exportada desde un log de tirada |
| **FE — Explorador de logs** | 23 | E15 | **ME**: una carpeta con los logs de una jornada se abre como tabla, se ordena por λ mínima, se filtra por «tiene eventos de knock» y los tres logs elegidos se abren juntos |
| **F5 — Endurecimiento y v1.0** | 24–26 | E10, E11 completa, E9.2/E9.4/E9.5/E9.6, corrección de defectos | **M5 = v1.0**: paquetes firmados, todos los presupuestos de §2.6 en verde |
| **F6 — Post v1.0** | — | E12, móvil como cliente del backend, telemetría en vivo, más descriptores de formato | fuera del alcance comprometido |

Camino crítico: **E1.3 (almacén columnar) → E13.2 (conversiones) → E3.1
(pirámide/render) → E14.4 (roles) → E2.6 (identidad) → E4.3 (perfiles por rol)
→ E7.1 (malla)**. Los roles entran en el camino crítico porque de ellos dependen
los perfiles y los detectores; por eso FG va **antes** de F2 y F3, y no al final:
retrofitear roles sobre perfiles ya escritos costaría más que hacerlos primero.

> El calendario pasó de 18 a 26 semanas. No es holgura añadida: son **271 puntos
> de alcance nuevo** (479 → 750), repartidos entre E13 (≈44), E14 (≈92), E15 (≈52),
> el trabajo
> por rol que E14 arrastra a F2/F3/F4 (≈30) y el reajuste a la base Python (≈24).
> Y la fase FG además reordena el plan para no pagar dos veces los perfiles.
>
> Esa cuenta es la del ALCANCE: qué épicas se añadieron y cuánto pesan. El total
> vigente del plan son **761 puntos en 155 tareas**, once puntos más, y la
> diferencia no es alcance nuevo sino dos tareas de defecto (F1-44 y F1-45) que
> salieron de abrir la aplicación con un log real. Se anotan aparte a propósito:
> mezclarlas con las épicas haría creer que el alcance crece cuando lo que pasó
> fue que algo no funcionaba.

## 2.8 Riesgos

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | 11 de 34 tipos de unidad sin factor confirmado → cifras erróneas mostradas a un tuner que decide sobre ellas | Alta | **Crítico** | Registro con `confidence`; los `unknown` se muestran en crudo y marcados. Nunca se inventa una unidad. Validación con un log de referencia del fabricante |
| R2 | Enums y máscaras de bits sin diccionario (75 canales) | Alta | Medio | Carriles de estado con etiqueta genérica `Estado N`; diccionario ampliable por datos; se aceptan aportaciones del usuario |
| R3 | Rendimiento del renderizador no llega a 60 fps con 8 logs | Media | Alto | Pirámide de decimación desde F1, no como optimización posterior; presupuestos en CI desde M0 |
| R4 | El desfase real entre logs internos es indeterminable → conclusiones falsas al concatenar | Media | Alto | Fronteras de segmento siempre visibles, jamás interpolar, desfase editable y auditable; aviso permanente de «tiempo no fiable» |
| R5 | Deriva de alcance hacia escritura en la ECU o edición de mapas | Media | Alto | No objetivo explícito en §2.3; la salida es una tabla exportable |
| R6 | El contenedor de escritorio elegido resulta insuficiente | Baja | Medio | `dlv-core` no importa nada de `dlv-api`, `dlv-ui` ni `dlv-app`: cambiar de contenedor queda acotado a `dlv-app` y no toca el núcleo |
| R7 | Variedad de logs del mundo real mucho mayor que las 3 muestras | Alta | Medio | Informe de importación tolerante que nunca aborta; recolección de casos desde F1; corpus creciente |
| R8 | La complejidad de la vista multi-log daña la facilidad de uso | Media | Alto | Perfiles y autoalineación por omisión; la configuración avanzada, oculta tras un panel secundario |
| R9 | **La base Python no alcanza los presupuestos de apertura o memoria** | Media | Alto | ADR-009 (cero bucles por muestra), *spike* de Polars en F0 **antes** de comprometer el resto, puertas de presupuesto en CI desde M0, Numba como vía de escape medida. Si el *spike* falla, se renegocia el presupuesto de apertura, no la arquitectura |
| R10 | **El importador genérico acierta la sintaxis y falla el significado**: nombre bien mapeado, escala mal, número plausible pero falso | Alta | **Crítico** | Previsualización obligatoria en el asistente; informe de plausibilidad contra el rango declarado de cada rol; dimensión `unknown` → valor en crudo sin unidad; los detectores críticos se desactivan si su rol proviene de asignación difusa no confirmada |
| R11 | **Conversión de unidades aplicada a diferencias**: Δ de temperatura absurdo, desviaciones típicas corruptas | Media | Alto | Clase punto/intervalo/tasa/varianza obligatoria en cada métrica; prueba de regresión dedicada (Δ10 K = 10 °C = 18 °F) que bloquea la fusión |
| R12 | La vía móvil con Python es más indirecta de lo previsto en la revisión 1 | Media | Medio | Interfaz web desde el día uno (ADR-002) y frontera de comandos HTTP: la fase 6 se compromete al teléfono como cliente del backend, que es maduro, y deja Pyodide como exploración. Documentado sin adornos en `03-arquitectura.md` §3.11 |
| R13 | El paquete de ~150 MB genera rechazo frente a los ~25 MB prometidos antes | Baja | Bajo | `onedir` en ZIP (~60 MB), sin PyArrow, exclusión agresiva de módulos. El requisito real era «sin instalación», y se cumple |
| R14 | **El explorador manda a analizar el log equivocado**: un resumen que no coincide con lo que se ve al abrirlo, o un hueco mostrado como 0 que hace pasar por limpio el log más peligroso | Media | **Crítico** | Agregados exactos sobre columnas proyectadas, nunca muestreados, calculados con el mismo código que la vista completa; una prueba compara resumen contra apertura completa en todo el corpus; celda sin dato vacía y distinguible de un cero real |
| R15 | **El índice en disco queda obsoleto** y la tabla describe una carpeta que ya no existe: logs borrados, reescritos por la ECU o con el mismo nombre y otro contenido | Media | Medio | Huella de (ruta, tamaño, fecha de modificación) por entrada, revalidada en cada apertura; una huella que no cuadra recalcula, no avisa y sigue; el índice es una caché reconstruible y borrarlo nunca pierde datos del usuario |

## 2.9 Calidad y datasets de prueba

Corpus mínimo a construir en F0:

1. Los tres logs de muestra (caso base).
2. AutoLog sintético de **1 hora, 475 canales** generado a partir del real (caso de rendimiento).
3. 20 logs internos consecutivos sintéticos (caso de concatenación).
4. Corruptos deliberados: cabecera truncada, fila corta, `DisplayMaxMin` ausente, BOM, CRLF, sin `\n` final, marcas no monótonas, cruce de medianoche, versión `1.2` desconocida, celdas con centinelas de desbordamiento.
5. Log con λ deliberadamente pobre en carga y eventos de knock inyectados, con **verdad de referencia anotada** para validar los detectores de E5.
6. **Corpus de CSV genéricos** que cubra la matriz de la fase FG: delimitador `;` con coma decimal, tabulaciones, fila de unidades, unidad en el nombre de columna, sin columna de tiempo, epoch en segundos y en milisegundos, ISO-8601, latin-1, `#N/A` y `NaN`, columnas de texto y booleanas, columnas duplicadas, preámbulo de metadatos largo, nombres de canal en español.
7. **Log equivalente en dos formatos** (el mismo contenido como Haltech nativo y como CSV genérico) para verificar que el emparejamiento por rol produce resultados idénticos. Es la prueba que demuestra que la escalabilidad a cualquier CSV es real y no nominal.

Sin el punto 5 no se puede afirmar que los detectores funcionan, y sin el 7 no se
puede afirmar que el proyecto es independiente del fabricante. Son los dos
entregables de QA más valiosos del proyecto: el 5 se construye en F0/F3, el 6 y el
7 en F0/FG.

## 2.10 Definición de terminado

Una tarea está terminada cuando: hay pruebas automáticas que cubren el camino
feliz y al menos un caso límite; los presupuestos de rendimiento afectados
siguen en verde; la documentación del usuario afectada está actualizada; y una
persona ha revisado el diff (ver puertas de revisión en
`05-backlog-y-asignacion-modelos.md`).

## 2.11 Preparación para v2 sin coste en v1

Cuatro decisiones baratas ahora que evitan una reescritura después:

1. El almacén columnar acepta **añadidos al final** (*append*), no solo carga
   completa. La telemetría en vivo es entonces «un log que crece».
2. `dlv-core` no toca el sistema de ficheros directamente: recibe objetos de
   lectura. Eso habilita orígenes de red y, en su caso, Pyodide, sin cambios.
3. La interfaz habla con el núcleo por **HTTP local con carga binaria**. La misma
   interfaz puede apuntar a un backend local, al del portátil desde el móvil, o a
   uno remoto. Es lo que convierte la fase móvil en configuración, no en obra.
4. `dlv-core` no importa nada de `dlv-api`, `dlv-ui` ni `dlv-app`. Se puede
   probar, usar como biblioteca en un cuaderno Jupyter y reempaquetar en otro
   contenedor sin tocarlo — que es además la forma en que el propietario podrá
   explotarlo directamente desde Python.
