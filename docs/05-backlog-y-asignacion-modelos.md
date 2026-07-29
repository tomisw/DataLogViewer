# 05 — Backlog y asignación de tareas por modelo

## 5.1 Criterio de asignación

El proyecto se ejecuta con asistencia de modelos de IA sobre revisión humana. La
asignación no es arbitraria: cada tarea se clasifica por **coste de un error** y
por **cuánto trabajo de razonamiento queda sin especificar**.

| Modelo | Identificador | Perfil | Se le asigna | No se le asigna |
|---|---|---|---|---|
| **Opus 5** | `claude-opus-5` | razonamiento de frontera | arquitectura, algoritmos con corrección sutil, rendimiento, seguridad, ingeniería inversa ambigua, revisión de diffs críticos | trabajo mecánico de gran volumen (coste innecesario) |
| **Sonnet 5** | `claude-sonnet-5` | caballo de batalla equilibrado | el grueso de la implementación de funcionalidad, componentes de UI, gestión de estado, pruebas de integración, documentación a partir de especificación | decisiones de arquitectura no cerradas, optimización de bucles calientes |
| **Haiku 4.5** | `claude-haiku-4-5-20251001` | rápido y económico | tareas mecánicas totalmente especificadas: *fixtures*, plantillas, entradas del registro de unidades, extracción de cadenas i18n, arreglos de lint, YAML de CI, renombrados en lote, changelog | cualquier tarea cuya especificación tenga huecos |

**Regla de oro**: si la tarea requiere *decidir* algo, no la hace Haiku. Si la
decisión ya está tomada y escrita, no la hace Opus.

**Regla de escalado**: si un modelo entrega dos intentos que no pasan la puerta
de revisión, la tarea escala al modelo superior con el diff fallido como contexto.
Se registra en el ticket, porque un patrón de escalados revela una especificación
mala, no un modelo malo.

**Nota sobre Fable 5** (`claude-fable-5`): está disponible en este entorno, pero
no tengo un perfil establecido de su rendimiento en trabajo de ingeniería de
software, así que el plan no le asigna ninguna tarea del camino crítico. Si se
quiere incorporar, la vía de menor riesgo es una tarea de prosa (documentación de
usuario, textos de la interfaz) evaluada contra la salida de Sonnet 5 antes de
ampliar su uso.

## 5.2 Puertas de revisión

| Puerta | Qué exige | Se aplica a |
|---|---|---|
| **G1 — revisión humana obligatoria** | una persona lee el diff completo antes de fusionar | parser, registro de unidades, factores de escala, generador de tablas de corrección, detectores de severidad crítica |
| **G2 — revisión por Opus 5 + humano en resumen** | Opus 5 revisa el diff y emite hallazgos; la persona lee el resumen y el diff de lo señalado | almacén columnar, pirámide, motor de tiempo, renderizador |
| **G3 — pruebas verdes + revisión ligera** | CI en verde y lectura rápida | UI, perfiles, exportadores, documentación |
| **G4 — pruebas verdes** | solo CI | *fixtures*, lint, changelog, i18n |

Cualquier tarea que toque un factor de escala o un umbral de detector es **G1 sin
excepción**: un número mal escalado se convierte en una decisión de tuning
equivocada y en un motor roto, y ese es el único fallo de este producto que no se
puede deshacer con un «ctrl-Z».

Esfuerzo en **puntos**: 1 punto ≈ media jornada de trabajo asistido más su
revisión. Total del plan: **100 tareas, 479 puntos** ≈ 240 jornadas, lo que sobre
18 semanas (90 días laborables) supone **≈ 2,7 flujos de trabajo en paralelo**.
Ese es el dimensionamiento del equipo que hace creíble el calendario de
§2.7 del plan; con un solo flujo, v1.0 se va a ~48 semanas.

---

## 5.3 Fase 0 — Cimientos (semanas 1–2)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F0-01 | Cerrar ADRs 001–006 con prototipos desechables de Tauri 2 + WASM | ADRs firmados, dos maquetas | **Opus 5** | 5 | — | G1 |
| F0-02 | Andamiaje del monorepo: `dlv-core` (Rust), `dlv-ui` (TS), `dlv-app` (Tauri) | repo compilando en 3 plataformas | Sonnet 5 | 4 | F0-01 | G3 |
| F0-03 | CI: compilación matricial, `clippy`, `fmt`, `eslint`, artefactos | workflows | Haiku 4.5 | 2 | F0-02 | G4 |
| F0-04 | Banco de rendimiento con publicación de métricas y puertas de presupuesto | `cargo bench` + informe en CI | **Opus 5** | 5 | F0-02 | G2 |
| F0-05 | Corpus de pruebas: los 3 logs reales + generador de sintéticos (1 h/475 canales, 20 logs internos) | generador + ficheros | Sonnet 5 | 4 | — | G3 |
| F0-06 | Corpus de logs corruptos (11 casos de `01-formato-log.md` §1.13) | *fixtures* | Haiku 4.5 | 2 | F0-05 | G4 |
| F0-07 | Log de verdad de referencia con knock y λ pobre anotados | *fixture* + anotaciones | **Opus 5** | 4 | F0-05 | G1 |
| F0-08 | Esqueleto de `units.toml` con los 13 tipos confirmados y `confidence` | fichero de datos | Haiku 4.5 | 2 | F0-01 | **G1** |
| F0-09 | Esqueleto de `enums.toml` con los 75 candidatos, sin traducir | fichero de datos | Haiku 4.5 | 2 | F0-08 | G3 |
| F0-10 | Guía de contribución y convenciones de código | `CONTRIBUTING.md` | Haiku 4.5 | 1 | F0-02 | G4 |

**Subtotal F0: 31 pts** · Hito **M0**

## 5.4 Fase 1 — Núcleo de datos y visor de un log (semanas 3–6)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F1-01 | Parser de cabecera con tolerancia a `DisplayMaxMin` ausente y erratas de nombre | módulo + pruebas | **Opus 5** | 5 | F0-08 | **G1** |
| F1-02 | Parser de cuerpo paralelo por fragmentos, ≥ 40 MB/s por hilo | módulo + banco | **Opus 5** | 8 | F1-01 | **G1** |
| F1-03 | Celda vacía ≠ 0, centinelas de desbordamiento, filas malformadas | reglas + pruebas | **Opus 5** | 5 | F1-02 | **G1** |
| F1-04 | Reconciliación de reloj: 12 h de cabecera, epoch ficticia, cruce de medianoche | módulo + pruebas | **Opus 5** | 5 | F1-01 | **G1** |
| F1-05 | Aplicación del registro de unidades y del estado de confianza | módulo | Sonnet 5 | 3 | F0-08, F1-03 | **G1** |
| F1-06 | Almacén columnar por canal con `t[]` compartido por grupo de muestreo | módulo + pruebas | **Opus 5** | 8 | F1-03 | G2 |
| F1-07 | Detección de grupos de muestreo por patrón de presencia | módulo + pruebas | **Opus 5** | 5 | F1-06 | G2 |
| F1-08 | Indexado: mín/máx/percentiles, clasificación `activo/constante/vacío` | módulo | Sonnet 5 | 4 | F1-06 | G3 |
| F1-09 | Detección de huecos de muestreo y marcas de discontinuidad | módulo | Sonnet 5 | 3 | F1-06 | G3 |
| F1-10 | **Pirámide de decimación** min/max/first/last, factor 4 | módulo + banco | **Opus 5** | 10 | F1-06 | G2 |
| F1-11 | Decimación por moda para canales enumerados y por suma para contadores | módulo | **Opus 5** | 5 | F1-10 | G2 |
| F1-12 | Caché Arrow con invalidación por `(ruta,tamaño,mtime,versión)` | módulo + banco | Sonnet 5 | 5 | F1-06 | G3 |
| F1-13 | Capa de formato como *trait* + informe de importación | refactor + módulo | Sonnet 5 | 4 | F1-03 | G3 |
| F1-14 | Frontera de comandos tipados núcleo↔UI (ADR-006) | esquema + enlaces | **Opus 5** | 5 | F1-06 | G2 |
| F1-15 | Compilación WASM del núcleo con hilos degradables | objetivo de compilación | **Opus 5** | 5 | F1-02 | G2 |
| F1-16 | **Renderizador WebGL2** de series desde la pirámide | módulo + banco de fps | **Opus 5** | 13 | F1-10, F1-14 | G2 |
| F1-17 | Ejes, rejilla y leyenda en SVG sincronizados con el lienzo | componente | Sonnet 5 | 5 | F1-16 | G3 |
| F1-18 | Paneles apilados con eje X compartido y arrastrar canales entre paneles | componente | Sonnet 5 | 5 | F1-17 | G3 |
| F1-19 | Múltiples ejes Y, autoescala y bloqueo de escala | componente | Sonnet 5 | 4 | F1-17 | G3 |
| F1-20 | Zoom/pan por rueda, teclado y *pointer events*; historial de zoom | módulo | Sonnet 5 | 5 | F1-16 | G3 |
| F1-21 | Cursor con tabla de valores, presupuesto < 16 ms | componente + banco | **Opus 5** | 5 | F1-20 | G2 |
| F1-22 | Doble cursor con delta (Δt, Δvalor, pendiente) | componente | Sonnet 5 | 3 | F1-21 | G3 |
| F1-23 | Selector de canales con búsqueda difusa y ocultación de inactivos | componente | Sonnet 5 | 4 | F1-08 | G3 |
| F1-24 | Arrastrar y soltar ficheros y carpetas; apertura múltiple | módulo | Sonnet 5 | 3 | F1-13 | G3 |
| F1-25 | *Fuzzing* de propiedad sobre cabecera y filas | suite de pruebas | **Opus 5** | 4 | F1-03, F0-06 | G2 |
| F1-26 | Presupuestos de F1 como puertas de CI | configuración del banco | Haiku 4.5 | 2 | F0-04, F1-16 | G4 |
| F1-27 | Rellenar `units.toml` con los tipos por confirmar a partir de análisis | datos + justificación | **Opus 5** | 5 | F1-05 | **G1** |

**Subtotal F1: 138 pts** · Hito **M1**

## 5.5 Fase 2 — Multi-log paralelo y concatenado (semanas 7–9)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F2-01 | Modelo de segmento y eje X virtual | módulo | **Opus 5** | 5 | F1-06 | G2 |
| F2-02 | Vista paralela: N segmentos superpuestos, color por log | componente | Sonnet 5 | 5 | F2-01, F1-18 | G3 |
| F2-03 | Alineación por reloj absoluto y por relativo | módulo | Sonnet 5 | 3 | F2-01, F1-04 | G3 |
| F2-04 | Desfase manual arrastrando el segmento | interacción | Sonnet 5 | 3 | F2-02 | G3 |
| F2-05 | Anclaje por evento (primer WOT, primer corte, launch) | módulo | **Opus 5** | 5 | F2-01 | G2 |
| F2-06 | **Autoalineación por correlación cruzada** sobre niveles L4–L6 con refinamiento en L0 | módulo + pruebas | **Opus 5** | 8 | F2-01, F1-10 | G2 |
| F2-07 | Vista concatenada: unión por `ID`, fronteras visibles, sin interpolar | módulo + componente | **Opus 5** | 8 | F2-01 | **G1** |
| F2-08 | Orden por `Log Number` con desfase editable y auditable | componente | Sonnet 5 | 4 | F2-07 | G3 |
| F2-09 | Estadísticas y detectores que respetan fronteras de segmento | refactor | **Opus 5** | 5 | F2-07 | G2 |
| F2-10 | **Eje X alternativo** (RPM, velocidad, distancia) con monotonía por tramos | módulo | **Opus 5** | 8 | F2-01 | G2 |
| F2-11 | Conflicto de mismo `ID` con escala distinta → aviso, no mezcla | módulo | Sonnet 5 | 3 | F2-07 | **G1** |
| F2-12 | Renderizado progresivo: silueta inmediata, refinamiento de fondo | módulo | **Opus 5** | 5 | F1-16 | G2 |
| F2-13 | Banco del caso peor: 8 logs × 30 min | banco + informe | Sonnet 5 | 3 | F2-02 | G3 |
| F2-14 | Documentación de usuario de multi-log | guía | Haiku 4.5 | 2 | F2-07 | G4 |

**Subtotal F2: 67 pts** · Hito **M2**

## 5.6 Fase 3 — Motorsport: perfiles, detectores, alertas (semanas 10–13)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F3-01 | Modelo y esquema de perfil `.dlvprofile` | esquema + módulo | **Opus 5** | 5 | F1-14 | G2 |
| F3-02 | Aplicación de perfil por `ID` con degradación si faltan canales | módulo | Sonnet 5 | 4 | F3-01 | G3 |
| F3-03 | Los 10 perfiles de fábrica de `04-perfiles-motorsport.md` §4.2 | 10 ficheros de datos | Sonnet 5 | 8 | F3-02 | **G1** |
| F3-04 | Autosugerencia de perfil según canales presentes y activos | módulo | Sonnet 5 | 3 | F3-02, F1-08 | G3 |
| F3-05 | Editor de perfiles, duplicado, importación y exportación | componente | Sonnet 5 | 5 | F3-01 | G3 |
| F3-06 | Motor de detectores: las 9 primitivas de §4.3 con histéresis y permanencia | módulo + pruebas | **Opus 5** | 10 | F1-06 | **G1** |
| F3-07 | Detectores D1–D18 como configuración | ficheros de datos | **Opus 5** | 8 | F3-06, F0-07 | **G1** |
| F3-08 | Validación de detectores contra la verdad de referencia, 0 falsos negativos | informe de validación | **Opus 5** | 5 | F3-07 | **G1** |
| F3-09 | Topes de alerta: aviso, crítico, banda y **curva en función de otro canal** | módulo + componente | **Opus 5** | 8 | F3-06 | **G1** |
| F3-10 | Dibujo de límites y bandas sobre los paneles | componente | Sonnet 5 | 4 | F3-09, F1-17 | G3 |
| F3-11 | **Panel de incidencias** ordenado por severidad con salto al instante | componente | Sonnet 5 | 5 | F3-07 | G3 |
| F3-12 | **Carriles de estado** para canales enumerados | componente | Sonnet 5 | 5 | F1-11, F0-09 | G3 |
| F3-13 | Decodificación de máscaras de bits en carriles apilados | módulo + componente | **Opus 5** | 5 | F3-12 | **G1** |
| F3-14 | Ampliar `enums.toml` con los códigos deducidos de las muestras | datos | Haiku 4.5 | 3 | F0-09 | G3 |
| F3-15 | Segmentación automática: WOT, ralentí, arranque, decel, calentamiento | módulo + pruebas | **Opus 5** | 8 | F3-06 | G2 |
| F3-16 | Panel de tiradas con resumen y superposición entre tiradas | componente | Sonnet 5 | 5 | F3-15, F2-10 | G3 |
| F3-17 | Evaluador de expresiones de canales matemáticos con multi-tasa por retención | módulo + pruebas | **Opus 5** | 8 | F1-06 | G2 |
| F3-18 | Biblioteca de fórmulas de §4.5 | datos | Sonnet 5 | 4 | F3-17 | **G1** |
| F3-19 | Detección de marcha por agrupación de velocidad/rpm | módulo | **Opus 5** | 5 | F3-17 | G2 |
| F3-20 | Modo oscuro y modo alto contraste | estilos | Haiku 4.5 | 3 | F1-17 | G4 |

**Subtotal F3: 111 pts** · Hito **M3**

## 5.7 Fase 4 — Análisis tabular e informes (semanas 14–16)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F4-01 | Malla RPM×MAP configurable con ejes deducidos del log | módulo | Sonnet 5 | 4 | F1-06 | G3 |
| F4-02 | Agregación por celda: media, desviación, mín, máx, número de muestras | módulo | **Opus 5** | 5 | F4-01 | G2 |
| F4-03 | **Filtros de exclusión**: transitorio, corte, protección, retardo del sensor λ | módulo + pruebas | **Opus 5** | 8 | F4-02, F3-15 | **G1** |
| F4-04 | Mapa de calor de λ error con detalle por celda | componente | Sonnet 5 | 5 | F4-02 | G3 |
| F4-05 | **Tabla de corrección de combustible** con celdas de confianza insuficiente sin rellenar | módulo | **Opus 5** | 8 | F4-03 | **G1** |
| F4-06 | Exportación de tabla a CSV y portapapeles como malla pegable | módulo | Sonnet 5 | 3 | F4-05 | G3 |
| F4-07 | Mapas de calor de avance y de densidad de knock | componente | Sonnet 5 | 4 | F4-02 | G3 |
| F4-08 | Comparación de dos logs celda a celda | componente | Sonnet 5 | 5 | F4-02, F2-01 | G3 |
| F4-09 | Métricas de PID de boost: sobreoscilación, establecimiento, error, saturación | módulo | **Opus 5** | 5 | F3-15 | G2 |
| F4-10 | Informe de sesión HTML autocontenido | módulo + plantilla | Sonnet 5 | 5 | F3-11, F4-04 | G3 |
| F4-11 | Exportación de vista a PNG/SVG y de datos a CSV/Parquet | módulo | Sonnet 5 | 4 | F1-16 | G3 |
| F4-12 | Documentación de usuario de análisis tabular, con las advertencias de fiabilidad | guía | **Opus 5** | 3 | F4-05 | **G1** |

**Subtotal F4: 59 pts** · Hito **M4**

## 5.8 Fase 5 — Endurecimiento y v1.0 (semanas 17–18)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F5-01 | Empaquetado: `.exe` portable, AppImage, `.dmg` | artefactos + CI | Sonnet 5 | 5 | F0-03 | G3 |
| F5-02 | **Modo portable** con `portable.txt`: cero escritura fuera de la carpeta | módulo + prueba | **Opus 5** | 5 | F5-01 | **G1** |
| F5-03 | Detección de WebView2 ausente con descarga guiada | módulo | Sonnet 5 | 3 | F5-01 | G3 |
| F5-04 | Firma y notarización | CI | Sonnet 5 | 4 | F5-01 | G3 |
| F5-05 | Actualizador opcional y desactivable | módulo | Sonnet 5 | 4 | F5-01 | G3 |
| F5-06 | Despliegue de la PWA de solo lectura sobre WASM | artefacto + CI | Sonnet 5 | 5 | F1-15 | G3 |
| F5-07 | Espacio de trabajo persistente `.dlvproj` | módulo | Sonnet 5 | 5 | F3-01 | G3 |
| F5-08 | Anotaciones y marcadores exportables | componente | Sonnet 5 | 4 | F5-07 | G3 |
| F5-09 | Paleta de comandos | componente | Sonnet 5 | 3 | F1-23 | G3 |
| F5-10 | i18n ES/EN: extracción de cadenas y catálogos | cadenas + catálogos | Haiku 4.5 | 4 | — | G4 |
| F5-11 | Onboarding: propuesta de perfil en lugar de lienzo vacío | componente | Sonnet 5 | 3 | F3-04 | G3 |
| F5-12 | Pruebas de regresión visual del renderizador | suite | Sonnet 5 | 4 | F1-16 | G3 |
| F5-13 | Revisión de seguridad: rutas, deserialización, evaluador de expresiones | informe + correcciones | **Opus 5** | 5 | F3-17, F5-07 | **G1** |
| F5-14 | Auditoría final de rendimiento contra los presupuestos de §2.6 | informe | **Opus 5** | 4 | todo | **G1** |
| F5-15 | Corrección de defectos y pulido | varios | Sonnet 5 | 8 | todo | G3 |
| F5-16 | Manual de usuario y notas de la versión | documentación | Haiku 4.5 | 4 | todo | G4 |
| F5-17 | Asociación de extensiones opcional y reversible | módulo | Sonnet 5 | 3 | F5-01 | G3 |

**Subtotal F5: 73 pts** · Hito **M5 = v1.0**

## 5.9 Resumen de asignación

| Modelo | Puntos | % del esfuerzo | Tareas | Concentración |
|---|---|---|---|---|
| **Opus 5** | 251 | 52 % | 41 | parser, almacén, pirámide, renderizador, motor de tiempo, detectores, tablas de corrección, rendimiento, seguridad |
| **Sonnet 5** | 201 | 42 % | 48 | UI, perfiles, exportadores, empaquetado, integración |
| **Haiku 4.5** | 27 | 6 % | 11 | *fixtures*, CI, datos de registro, i18n, documentación mecánica |
| **Total** | **479** | 100 % | **100** | |

Distribución de puertas de revisión: **24 tareas en G1** (revisión humana
obligatoria), 22 en G2 (revisión por Opus 5 + humano en resumen), 46 en G3, 8 en
G4. El esfuerzo de revisión de G1 y G2 es adicional a los 479 puntos y se
presupuesta como un **20 % de sobrecoste** sobre las tareas que las requieren.

Reparto por fase: F0 31 · F1 138 · F2 67 · F3 111 · F4 59 · F5 73.

La proporción de Opus 5 es alta para un proyecto de aplicación, y es deliberada:
más de la mitad del valor de este producto está en cuatro piezas —parser,
pirámide de decimación, motor de tiempo multi-log y generación de tablas de
corrección— donde un error es silencioso, plausible y caro. El resto es
integración, donde Sonnet 5 rinde igual a menor coste.

## 5.10 Higiene de contexto por modelo

Lo que hace fallar estas asignaciones no es la capacidad del modelo, es el
contexto que recibe:

- **Tareas de Opus 5**: se le dan los ADRs afectados, `01-formato-log.md`
  completo y los presupuestos de rendimiento aplicables. Se espera que cuestione
  la especificación si encuentra una contradicción, y se registra cuando lo hace.
- **Tareas de Sonnet 5**: se le da el módulo aguas arriba ya terminado, el
  esquema de datos y un criterio de aceptación comprobable. Nunca una decisión
  de arquitectura pendiente.
- **Tareas de Haiku 4.5**: se le da la especificación completa y un ejemplo
  resuelto de la misma clase de tarea. Si la tarea necesita una aclaración, la
  especificación estaba mal y se corrige antes de reasignar.
- **Todas**: no se le pide a ningún modelo inventar un factor de escala. Los
  factores salen del análisis de datos con evidencia (F1-27), pasan por G1, y los
  no confirmados se marcan `unknown` y se muestran en crudo. Esta es la regla que
  protege el riesgo R1, que es el único de la lista que puede romper un motor.
