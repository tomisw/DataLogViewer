# 05 — Backlog y asignación de tareas por modelo

> **Revisión 2.** Incorpora la base **Python** (`03-arquitectura.md` rev. 2), el
> **sistema de unidades intercambiables** (E13) y la **extensibilidad a cualquier
> CSV** (E14). El alcance pasa de 479 a **698 puntos** y el calendario de 18 a
> **25 semanas**. La revisión 3 añade el **explorador de logs** (E15, fase FE):
> 52 puntos y una semana más, hasta **750 puntos y 26 semanas**.

## 5.1 Criterio de asignación

El proyecto se ejecuta con asistencia de modelos de IA sobre revisión humana. La
asignación no es arbitraria: cada tarea se clasifica por **coste de un error** y
por **cuánto trabajo de razonamiento queda sin especificar**.

| Modelo | Identificador | Perfil | Se le asigna | No se le asigna |
|---|---|---|---|---|
| **Opus 5** | `claude-opus-5` | razonamiento de frontera | arquitectura, algoritmos con corrección sutil, rendimiento, seguridad, ingeniería inversa ambigua, revisión de diffs críticos | trabajo mecánico de gran volumen (coste innecesario) |
| **Sonnet 5** | `claude-sonnet-5` | caballo de batalla equilibrado | el grueso de la implementación de funcionalidad, componentes de interfaz, gestión de estado, pruebas de integración, documentación a partir de especificación | decisiones de arquitectura no cerradas, optimización de rutas calientes |
| **Haiku 4.5** | `claude-haiku-4-5-20251001` | rápido y económico | tareas mecánicas totalmente especificadas: *fixtures*, plantillas, entradas de catálogo, extracción de cadenas i18n, arreglos de lint, YAML de CI, renombrados en lote, changelog | cualquier tarea cuya especificación tenga huecos |

**Regla de oro**: si la tarea requiere *decidir* algo, no la hace Haiku. Si la
decisión ya está tomada y escrita, no la hace Opus.

**Regla de escalado**: si un modelo entrega dos intentos que no pasan la puerta de
revisión, la tarea escala al modelo superior con el diff fallido como contexto. Se
registra en el ticket, porque un patrón de escalados revela una especificación
mala, no un modelo malo.

**Nota sobre Fable 5** (`claude-fable-5`): está disponible en este entorno, pero
no tengo un perfil establecido de su rendimiento en trabajo de ingeniería de
software, así que el plan no le asigna ninguna tarea del camino crítico. Si se
quiere incorporar, la vía de menor riesgo es una tarea de prosa (documentación de
usuario, textos de la interfaz) evaluada contra la salida de Sonnet 5 antes de
ampliar su uso.

### Cómo cambia la asignación con la base Python

Dos efectos concretos, no cosméticos:

1. **El propietario puede revisar de verdad casi todo.** `dlv-core` y `dlv-api`
   son Python: las puertas G1 dejan de ser un acto de fe. Eso permite subir la
   proporción de trabajo de Sonnet 5 en el núcleo, porque la revisión humana es
   ahora un control real y no nominal.
2. **`dlv-ui` es la excepción y se trata como tal.** El renderizador WebGL2 y el
   frontend son TypeScript, la parte que el propietario menos puede auditar. Por
   eso el renderizador es de Opus 5 con puerta G2, tiene pruebas de regresión
   visual obligatorias, y su API se mantiene deliberadamente pequeña: recibe
   cubos y una escala, y no sabe nada de logs, unidades ni perfiles.

## 5.2 Puertas de revisión

| Puerta | Qué exige | Se aplica a |
|---|---|---|
| **G1 — revisión humana obligatoria** | una persona lee el diff completo antes de fusionar | parser, catálogos de unidades y roles, conversiones, generador de tablas de corrección, detectores críticos, importador genérico |
| **G2 — revisión por Opus 5 + humano en resumen** | Opus 5 revisa el diff y emite hallazgos; la persona lee el resumen y el diff de lo señalado | almacén columnar, pirámide, motor de tiempo, renderizador, capa de API |
| **G3 — pruebas verdes + revisión ligera** | CI en verde y lectura rápida | interfaz, perfiles, exportadores, documentación |
| **G4 — pruebas verdes** | solo CI | *fixtures*, lint, changelog, i18n |

Tres clases de cambio son **G1 sin excepción**, porque su fallo es silencioso,
plausible y llega a una decisión de tuning:

- cualquier cosa que toque un **factor de escala o una conversión de unidad**;
- cualquier **umbral de detector**;
- cualquier **asignación de rol** o regla del importador genérico.

Esfuerzo en **puntos**: 1 punto ≈ media jornada de trabajo asistido más su
revisión. Total: **153 tareas, 750 puntos** ≈ 375 jornadas. Con la capacidad
supuesta de **27 puntos/semana** (≈ 2,7 flujos de trabajo en paralelo), salen las
**26 semanas** del calendario de `02-alcance-y-plan.md` §2.7. Con un solo flujo,
v1.0 se va a ~67 semanas.

---

## 5.3 Fase F0 — Cimientos (semanas 1–2)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F0-01 | Cerrar ADR-001…009 y ***spike* de rendimiento de Polars** sobre el AutoLog sintético de 1 h: confirma o refuta el presupuesto de apertura antes de comprometer el resto | ADRs firmados + informe del *spike* | **Opus 5** | 6 | — | **G1** |
| F0-02 | Andamiaje: paquetes `dlv-core`, `dlv-api`, `dlv-ui`, `dlv-app`; `pyproject.toml`, tipado estricto | repo ejecutando en 3 plataformas | Sonnet 5 | 4 | F0-01 | G3 |
| F0-03 | CI: matriz de 3 plataformas, `pytest`, `ruff`, `mypy`, `eslint`, artefactos | workflows | Haiku 4.5 | 2 | F0-02 | G4 |
| F0-04 | Banco de rendimiento con publicación de métricas y puertas de presupuesto | banco + informe en CI | **Opus 5** | 5 | F0-02 | G2 |
| F0-05 | Corpus: los 3 logs reales + generador de sintéticos (1 h/475 canales, 20 logs internos) | generador + ficheros | Sonnet 5 | 4 | — | G3 |
| F0-06 | Corpus de logs corruptos (11 casos de `01-formato-log.md` §1.13) | *fixtures* | Haiku 4.5 | 2 | F0-05 | G4 |
| F0-07 | Log de verdad de referencia con knock y λ pobre anotados | *fixture* + anotaciones | **Opus 5** | 4 | F0-05 | **G1** |
| F0-08 | **Catálogo `units.toml`**: dimensiones, canónicas, unidades alternativas, conversiones afines/recíprocas, presets, decimales, centinelas | fichero de datos | **Opus 5** | 6 | F0-01 | **G1** |
| F0-09 | **`formats/haltech_nsp.toml`**: los 34 tipos → dimensión + escala a canónica, con `confidence` y evidencia | fichero de datos | **Opus 5** | 5 | F0-08 | **G1** |
| F0-10 | **Catálogo `roles.toml`**: roles semánticos, dimensión esperada, rango plausible, sinónimos ES/EN | fichero de datos | **Opus 5** | 6 | F0-08 | **G1** |
| F0-11 | Esqueleto `enums.toml` con los 75 candidatos, sin traducir | fichero de datos | Haiku 4.5 | 2 | F0-10 | G3 |
| F0-12 | **Corpus de CSV genéricos** (matriz de `02-alcance-y-plan.md` §2.9 punto 6) | *fixtures* | Haiku 4.5 | 3 | F0-05 | G4 |
| F0-13 | **Log equivalente en dos formatos** (nativo + genérico) para la prueba de independencia de fabricante | *fixture* + anotaciones | Sonnet 5 | 3 | F0-12 | **G1** |
| F0-14 | Guía de contribución, convenciones y **ADR-009 documentado como regla de revisión** | `CONTRIBUTING.md` | Haiku 4.5 | 2 | F0-02 | G4 |

**Subtotal F0: 54 pts** · Hito **M0**

## 5.4 Fase F1 — Núcleo, unidades y visor de un log (semanas 3–9)

### Ingesta y almacén

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F1-01 | Parser de cabecera Haltech dirigido por descriptor, tolerante a `DisplayMaxMin` ausente y erratas de nombre | módulo + pruebas | **Opus 5** | 5 | F0-09 | **G1** |
| F1-02 | Parseo del cuerpo con **Polars**: ≥ 100 MB/s agregado, cero bucles de Python | módulo + banco | **Opus 5** | 8 | F1-01 | **G1** |
| F1-03 | Celda vacía ≠ 0, centinelas de desbordamiento, filas malformadas | reglas + pruebas | **Opus 5** | 5 | F1-02 | **G1** |
| F1-04 | Reconciliación de reloj: 12 h de cabecera, epoch ficticia, cruce de medianoche | módulo + pruebas | **Opus 5** | 5 | F1-01 | **G1** |
| F1-05 | Almacén columnar con `Storage` por canal y `t` compartido por grupo de muestreo | módulo + pruebas | **Opus 5** | 8 | F1-03 | G2 |
| F1-06 | Detección de grupos de muestreo por patrón de nulos, vectorizada | módulo + pruebas | **Opus 5** | 5 | F1-05 | G2 |
| F1-07 | Indexado: mín/máx/percentiles, clasificación `activo/constante/vacío/fuera de rango` | módulo | Sonnet 5 | 4 | F1-05 | G3 |
| F1-08 | Detección de huecos de muestreo y marcas de discontinuidad | módulo | Sonnet 5 | 3 | F1-05 | G3 |
| F1-09 | **Pirámide de decimación** NumPy vectorizada (`min/max/first/last`, factor 4) | módulo + banco | **Opus 5** | 8 | F1-05 | G2 |
| F1-10 | Variantes de agregación: suma de delta, moda de enum, OR de bits — con Numba solo si el banco lo exige | módulo + banco | **Opus 5** | 6 | F1-09 | G2 |
| F1-11 | Caché Parquet con pirámide persistida e invalidación por versión | módulo + banco | Sonnet 5 | 5 | F1-09 | G3 |
| F1-12 | Informe de importación acumulativo, no bloqueante | módulo | Sonnet 5 | 3 | F1-03 | G3 |

### Sistema de unidades (E13)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F1-13 | **Motor de conversión**: afín y recíproca, con clases punto / intervalo / tasa / varianza obligatorias | módulo + pruebas | **Opus 5** | 8 | F0-08 | **G1** |
| F1-14 | Conversiones **parametrizadas por canal** (λ→AFR con la estequiometría del propio log) | módulo + pruebas | **Opus 5** | 5 | F1-13 | **G1** |
| F1-15 | Presión **absoluta/relativa** como cambio de origen combinable con cualquier unidad | módulo + pruebas | **Opus 5** | 5 | F1-13 | **G1** |
| F1-16 | Dimensiones **compuestas** derivadas (`%/kPa` → `%/psi`) | módulo | **Opus 5** | 4 | F1-13 | **G1** |
| F1-17 | Precedencia canal > dimensión del perfil > preset global > canónica | módulo | Sonnet 5 | 4 | F1-13 | G3 |
| F1-18 | Presets SI / Métrico / Imperial / Motorsport EU / Motorsport US + presets de usuario | datos + módulo | Sonnet 5 | 3 | F1-17 | **G1** |
| F1-19 | Umbrales y perfiles **en canónica**, editados en la unidad activa | módulo | **Opus 5** | 4 | F1-13 | **G1** |
| F1-20 | **Prueba de la trampa del delta** (Δ10 K = 10 °C = 18 °F) y tabla de casos conocidos | suite de pruebas | **Opus 5** | 4 | F1-13 | **G1** |

### API y frontend

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F1-21 | `dlv-api`: FastAPI, `127.0.0.1`, puerto efímero, token de sesión, comandos tipados | módulo | **Opus 5** | 5 | F1-05 | G2 |
| F1-22 | Transporte **binario** Arrow IPC / `TypedArray` para series; JSON solo para metadatos | módulo + banco | **Opus 5** | 5 | F1-21 | G2 |
| F1-23 | **Renderizador WebGL2** de series desde la pirámide | módulo + banco de fps | **Opus 5** | 13 | F1-09, F1-22 | G2 |
| F1-24 | **Caché de cubos en el frontend** — es lo que hace alcanzable el cursor < 16 ms con Python detrás | módulo + banco | **Opus 5** | 5 | F1-23 | G2 |
| F1-25 | Ejes, rejilla y leyenda SVG con ticks calculados **en la unidad mostrada** | componente | Sonnet 5 | 5 | F1-23, F1-17 | G3 |
| F1-26 | Paneles apilados con eje X compartido y arrastrar canales entre paneles | componente | Sonnet 5 | 5 | F1-25 | G3 |
| F1-27 | Múltiples ejes Y, autoescala y bloqueo de escala | componente | Sonnet 5 | 4 | F1-25 | G3 |
| F1-28 | Zoom/pan por rueda, teclado y *pointer events*; historial de zoom | módulo | Sonnet 5 | 5 | F1-23 | G3 |
| F1-29 | Cursor con tabla de valores, presupuesto < 16 ms | componente + banco | Sonnet 5 | 4 | F1-24 | G3 |
| F1-30 | Doble cursor con delta usando la clase **intervalo** | componente | **Opus 5** | 4 | F1-29, F1-13 | **G1** |
| F1-31 | **Selector de unidad a tres niveles** (global, dimensión, canal) con decimales por unidad | componente | Sonnet 5 | 5 | F1-17 | G3 |
| F1-32 | Locale numérico ES/EN (separador decimal, agrupación) | módulo | Haiku 4.5 | 2 | F1-31 | G4 |
| F1-33 | Selector de canales con búsqueda difusa y ocultación de inactivos | componente | Sonnet 5 | 4 | F1-07 | G3 |
| F1-34 | Arrastrar y soltar ficheros y carpetas; apertura múltiple | módulo | Sonnet 5 | 3 | F1-12 | G3 |
| F1-35 | Contenedor `pywebview` + PyInstaller `onedir` para desarrollo | módulo + CI | Sonnet 5 | 4 | F0-03, F1-21 | G3 |
| F1-36 | *Fuzzing* de propiedad sobre cabecera y filas (Hypothesis) | suite de pruebas | **Opus 5** | 4 | F1-03, F0-06 | G2 |
| F1-37 | Presupuestos de F1 como puertas de CI, incluido el de cambio de unidad | configuración del banco | Haiku 4.5 | 2 | F0-04, F1-23 | G4 |
| F1-38 | Confirmar los **21 tipos `unknown`** con análisis de datos y evidencia documentada | datos + informe | **Opus 5** | 5 | F0-09 | **G1** |
| F1-39 | **Montaje de la aplicación**: unir renderizador, ejes, paneles, escalas, cursor, navegación y selectores en algo que se abre y funciona | componente | Sonnet 5 | 8 | F1-26, F1-28, F1-29, F1-31, F1-33 | G3 |
| F1-40 | **Sesión de log abierto** en `dlv-api` y endpoint de **cubos de pirámide** por rango y nivel | módulo + pruebas | **Opus 5** | 8 | F1-21, F1-09, F1-11 | G2 |
| F1-41 | Selector de **tipo de combustible** y factores de conversión editables | componente | Sonnet 5 | 3 | F1-14 | G3 |
| F1-42 | **Apertura en < 4 s**: `detectar_grupos_de_muestreo` usa `np.unique(axis=0)` y se lleva el 98 % del tiempo de apertura | módulo + banco | **Opus 5** | 5 | F1-05, F1-06, F1-40 | G2 |
| F1-43 | **La aplicación abre un log de verdad**: cablear `FuenteApi`, búfer de tipado fijo para el navegador, catálogo de unidades por HTTP y arranque con ruta de log | módulo + pruebas | **Opus 5** | 5 | F1-39, F1-40, F1-35 | G2 |

**Subtotal F1: 215 pts** · Hito **M1**

> **F1-39, F1-40 y F1-41 no estaban en la revisión 2 del plan.** Las tres
> aparecieron al montar el MVP, y las tres son huecos reales, no trabajo extra:
>
> - **F1-39** es el hueco entre «las 38 tareas de F1 hechas» y «M1 alcanzado».
>   Cada tarea de interfaz construyó su pieza y ninguna tenía asignada la
>   costura, así que `dlv-ui/src/main.ts` seguía siendo el «hola, dlv-api» de
>   F0-02 con 343 pruebas verdes detrás. Es la lección que deja F1 para las
>   fases siguientes: **un backlog de piezas necesita una tarea de montaje**, o
>   el hito no se alcanza aunque el contador de puntos diga que sí.
> - **F1-40** salió de comparar lo que `/comandos/serie` (F1-22) devuelve con lo
>   que el renderizador (F1-23) consume: series completas frente a cubos de un
>   nivel para un rango, y un reparseo del fichero entero por petición.
> - **F1-41** la pidió el propietario al revisar F1-14 (2026-08-03): poder
>   cambiar el tipo de combustible o editar el factor a mano.
> - **F1-42** la destapó el banco de F1-40 en cuanto hubo por fin un camino
>   completo que medir: la primera apertura del log de 70 MB pasaba del
>   presupuesto de 4,0 s. F1-05 y F1-06 no incumplían nada cuando se cerraron
>   porque nadie había medido todavía la apertura entera; es el presupuesto de
>   §2.6 haciendo exactamente su trabajo.
>
>   **El primer diagnóstico era falso y conviene que quede escrito.** Se
>   atribuyó a `construir_desde_polars` (F1-05) por hacer un `filter` por canal
>   ×475. Al perfilarlo, ese `filter` costaba **0,02 s**; el 98 % del tiempo
>   estaba en `detectar_grupos_de_muestreo` (F1-06) y su `np.unique(axis=0)`
>   sobre una matriz de 475×38 698. La primera corrección, hecha sobre el
>   diagnóstico equivocado, dejó la apertura **más lenta**. Es el motivo por el
>   que un banco mide antes y después: sin el «después», el cambio se habría
>   dado por bueno.

## 5.5 Fase FG — Formatos y CSV genérico (semanas 10–12)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| FG-01 | **Sondeo**: codificación, fin de línea, delimitador por consistencia de número de campos, comillas | módulo + pruebas | **Opus 5** | 8 | F1-02 | **G1** |
| FG-02 | **Separador decimal** con verificación cruzada de interpretaciones | módulo + pruebas | **Opus 5** | 5 | FG-01 | **G1** |
| FG-03 | Estructura: preámbulo de metadatos, fila de nombres, fila de unidades, inicio de datos | módulo + pruebas | **Opus 5** | 5 | FG-01 | **G1** |
| FG-04 | **Columna de tiempo** en las 8 variantes de §7.5, incluida la ausente con frecuencia declarada | módulo + pruebas | **Opus 5** | 8 | FG-03 | **G1** |
| FG-05 | Inferencia de tipo por columna: entero, decimal, enum de texto, booleano, constante, vacía | módulo | **Opus 5** | 5 | FG-03 | G2 |
| FG-06 | Unidad declarada en el nombre o en la fila de unidades + diccionario de alias | módulo + datos | Sonnet 5 | 5 | FG-03, F0-08 | **G1** |
| FG-07 | Valores no numéricos, unidad embebida en la celda, separador de miles | módulo + pruebas | Sonnet 5 | 4 | FG-05 | **G1** |
| FG-08 | Columnas de texto y booleanas → enum con diccionario autogenerado | módulo | Sonnet 5 | 3 | FG-05 | G3 |
| FG-09 | **Asignación automática de roles** por sinónimos, normalización y difuso como último recurso | módulo + pruebas | **Opus 5** | 8 | F0-10 | **G1** |
| FG-10 | **Informe de plausibilidad** por rango declarado de cada rol | módulo | **Opus 5** | 5 | FG-09 | **G1** |
| FG-11 | **Asistente de importación** de 3 pasos con previsualización viva | componente | Sonnet 5 | 8 | FG-04, FG-09 | G3 |
| FG-12 | Perfil **`.dlvimport`** con huella de cabecera y reaplicación parcial | módulo + componente | Sonnet 5 | 5 | FG-11 | G3 |
| FG-13 | **Descriptores de formato nativo declarativos**; migrar Haltech a descriptor puro | refactor + datos | **Opus 5** | 8 | F1-01 | G2 |
| FG-14 | Robustez: filas de longitud variable, columnas duplicadas, cabecera sin nombres | módulo + pruebas | Sonnet 5 | 4 | FG-05 | G3 |
| FG-15 | *Fuzzing* del importador genérico sobre el corpus de CSV | suite de pruebas | **Opus 5** | 4 | FG-14, F0-12 | G2 |
| FG-16 | **Prueba de independencia de fabricante**: el log de F0-13 da resultados idénticos en los dos formatos | suite + informe | **Opus 5** | 4 | FG-09, F0-13 | **G1** |
| FG-17 | Documentación: importar un CSV cualquiera y añadir un formato nativo | guía | Sonnet 5 | 3 | FG-13 | G3 |

**Subtotal FG: 92 pts** · Hito **MG**

## 5.6 Fase F2 — Multi-log paralelo y concatenado (semanas 13–15)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F2-01 | Modelo de segmento y eje X virtual | módulo | **Opus 5** | 5 | F1-05 | G2 |
| F2-02 | **Identidad de canal en capas** (rol → `(formato, ID)` → nombre normalizado) y emparejamiento entre logs | módulo + pruebas | **Opus 5** | 8 | FG-09 | **G1** |
| F2-03 | Emparejamiento manual con prioridad máxima, persistido en el proyecto | componente | Sonnet 5 | 4 | F2-02 | G3 |
| F2-04 | Vista paralela: N segmentos superpuestos, color por log | componente | Sonnet 5 | 5 | F2-01, F1-26 | G3 |
| F2-05 | Alineación por reloj absoluto y por relativo | módulo | Sonnet 5 | 3 | F2-01, F1-04 | G3 |
| F2-06 | Desfase manual arrastrando el segmento | interacción | Sonnet 5 | 3 | F2-04 | G3 |
| F2-07 | Anclaje por evento (primer WOT, primer corte, launch) | módulo | **Opus 5** | 5 | F2-01 | G2 |
| F2-08 | **Autoalineación por correlación cruzada** en L4–L6 con refinamiento en L0 | módulo + pruebas | **Opus 5** | 8 | F2-01, F1-09 | G2 |
| F2-09 | **Vista concatenada**: unión por identidad, fronteras visibles, sin interpolar | módulo + componente | **Opus 5** | 8 | F2-02 | **G1** |
| F2-10 | Orden por `Log Number` con desfase editable y auditable | componente | Sonnet 5 | 4 | F2-09 | G3 |
| F2-11 | Estadísticas y detectores que respetan las fronteras de segmento | refactor | **Opus 5** | 5 | F2-09 | G2 |
| F2-12 | **Eje X alternativo** (RPM, velocidad, distancia) con monotonía por tramos | módulo | **Opus 5** | 8 | F2-01 | G2 |
| F2-13 | Conflictos: mismo rol con unidades de origen distintas → canónica común; escala incoherente → aviso | módulo | **Opus 5** | 4 | F2-02, F1-13 | **G1** |
| F2-14 | Renderizado progresivo: silueta inmediata, refinamiento de fondo | módulo | **Opus 5** | 5 | F1-23 | G2 |
| F2-15 | Banco del caso peor: 8 logs × 30 min, incluido cambio de unidad | banco + informe | Sonnet 5 | 3 | F2-04 | G3 |
| F2-16 | Documentación de usuario de multi-log | guía | Haiku 4.5 | 2 | F2-09 | G4 |

**Subtotal F2: 80 pts** · Hito **M2**

## 5.7 Fase F3 — Motorsport: perfiles, detectores, alertas (semanas 16–20)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F3-01 | Modelo de perfil `.dlvprofile` **por rol**, con unidades por dimensión y roles requeridos/opcionales | esquema + módulo | **Opus 5** | 6 | F1-21, F0-10 | **G1** |
| F3-02 | Aplicación de perfil por rol con degradación elegante y reserva a `ID` nativo | módulo | Sonnet 5 | 5 | F3-01 | G3 |
| F3-03 | Los **10 perfiles de fábrica** de `04-perfiles-motorsport.md` §4.2, definidos por rol | 10 ficheros de datos | Sonnet 5 | 8 | F3-02 | **G1** |
| F3-04 | Autosugerencia por **cobertura de roles** («7 de 9 disponibles») | módulo | Sonnet 5 | 4 | F3-02, F1-07 | G3 |
| F3-05 | Editor de perfiles, duplicado, importación y exportación | componente | Sonnet 5 | 5 | F3-01 | G3 |
| F3-06 | **Motor de detectores**: las 9 primitivas de §4.3 con histéresis y permanencia mínima (Numba donde el banco lo exija) | módulo + pruebas | **Opus 5** | 10 | F1-05 | **G1** |
| F3-07 | Detectores **D1–D18 por rol**, como configuración | ficheros de datos | **Opus 5** | 8 | F3-06, F0-07 | **G1** |
| F3-08 | **Desactivación de detectores críticos** cuando su rol proviene de asignación difusa no confirmada (mitigación de R10) | módulo | **Opus 5** | 4 | F3-07, FG-09 | **G1** |
| F3-09 | Validación contra la verdad de referencia, en formato nativo **y** en CSV genérico | informe de validación | **Opus 5** | 5 | F3-07, F0-13 | **G1** |
| F3-10 | **Topes de alerta**: aviso, crítico, banda y **curva en función de otro canal** | módulo + componente | **Opus 5** | 8 | F3-06, F1-19 | **G1** |
| F3-11 | Dibujo de límites y bandas sobre los paneles, en la unidad activa | componente | Sonnet 5 | 4 | F3-10, F1-25 | G3 |
| F3-12 | **Panel de incidencias** por severidad con salto al instante | componente | Sonnet 5 | 5 | F3-07 | G3 |
| F3-13 | **Carriles de estado** para canales enumerados | componente | Sonnet 5 | 5 | F1-10, F0-11 | G3 |
| F3-14 | Decodificación de **máscaras de bits** en carriles apilados | módulo + componente | **Opus 5** | 5 | F3-13 | **G1** |
| F3-15 | Ampliar `enums.toml` con los códigos deducidos de las muestras | datos | Haiku 4.5 | 3 | F0-11 | G3 |
| F3-16 | **Segmentación automática**: WOT, ralentí, arranque, deceleración, calentamiento | módulo + pruebas | **Opus 5** | 8 | F3-06 | G2 |
| F3-17 | Panel de tiradas con resumen y superposición entre tiradas | componente | Sonnet 5 | 5 | F3-16, F2-12 | G3 |
| F3-18 | Evaluador de expresiones **en canónica**, multi-tasa por retención con límite de validez | módulo + pruebas | **Opus 5** | 8 | F1-13 | G2 |
| F3-19 | Biblioteca de fórmulas de §4.5, cada una con su **clase de magnitud** declarada | datos | Sonnet 5 | 4 | F3-18 | **G1** |
| F3-20 | Detección de marcha por agrupación de velocidad/rpm | módulo | **Opus 5** | 5 | F3-18 | G2 |
| F3-21 | Modo oscuro y modo alto contraste | estilos | Haiku 4.5 | 3 | F1-25 | G4 |

**Subtotal F3: 118 pts** · Hito **M3**

## 5.8 Fase F4 — Análisis tabular e informes (semanas 21–22)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F4-01 | Malla RPM×MAP configurable, con los ejes mostrados en la unidad activa | módulo | Sonnet 5 | 4 | F1-05 | G3 |
| F4-02 | Agregación por celda: media, desviación, mín, máx, número de muestras | módulo | **Opus 5** | 5 | F4-01 | G2 |
| F4-03 | **Filtros de exclusión**: transitorio, corte, protección de motor, retardo de transporte del sensor λ | módulo + pruebas | **Opus 5** | 8 | F4-02, F3-16 | **G1** |
| F4-04 | Mapa de calor de λ error con detalle por celda | componente | Sonnet 5 | 5 | F4-02 | G3 |
| F4-05 | **Tabla de corrección de combustible**, con celdas de confianza insuficiente sin rellenar | módulo | **Opus 5** | 8 | F4-03 | **G1** |
| F4-06 | Exportación de tabla a CSV y portapapeles como malla pegable | módulo | Sonnet 5 | 3 | F4-05 | G3 |
| F4-07 | Mapas de calor de avance de encendido y de densidad de knock | componente | Sonnet 5 | 4 | F4-02 | G3 |
| F4-08 | Comparación de dos logs celda a celda | componente | Sonnet 5 | 5 | F4-02, F2-02 | G3 |
| F4-09 | Métricas de PID de boost: sobreoscilación, establecimiento, error, saturación | módulo | **Opus 5** | 5 | F3-16 | G2 |
| F4-10 | Estadísticas con la **clase de magnitud** correcta (varianza con `a²`, RMS lineal) | refactor + pruebas | **Opus 5** | 4 | F1-13, F4-02 | **G1** |
| F4-11 | Informe de sesión HTML autocontenido, **con las unidades usadas declaradas** | módulo + plantilla | Sonnet 5 | 5 | F3-12, F4-04 | G3 |
| F4-12 | Exportación de vista a PNG/SVG y de datos a CSV/Parquet con unidad declarada por columna | módulo | Sonnet 5 | 4 | F1-23 | G3 |
| F4-13 | Documentación de análisis tabular con las advertencias de fiabilidad | guía | **Opus 5** | 3 | F4-05 | **G1** |

**Subtotal F4: 63 pts** · Hito **M4**

## 5.9 Fase FE — Explorador de logs (semana 23)

Épica E15. Va **después de F3 y F4** y no antes, por una razón concreta: las
columnas que de verdad deciden qué log merece análisis no son el máximo de RPM,
son «12 eventos de knock» y «λ mínima 0,74», y esas las producen los detectores de
F3 y la maquinaria de estadística con clase de magnitud de F4-10. Adelantar la
fase daría una tabla que ordena por lo que es fácil de calcular en vez de por lo
que importa.

El presupuesto de indexado (§2.6) es la restricción que da forma a toda la fase:
200 logs en menos de 60 s solo sale si el resumen **proyecta las columnas que las
métricas necesitan** en vez de abrir el log entero. No se muestrea: se leen 6
columnas de 475, que es exacto y además barato.

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| FE-01 | Recorrido de carpeta e **índice con huella** (ruta, tamaño, fecha de modificación) en disco, revalidado en cada apertura | módulo + pruebas | **Opus 5** | 5 | F1-11 | G2 |
| FE-02 | **Resumen por log con columnas proyectadas**: agregados exactos por rol sin abrir el log entero, dentro del presupuesto | módulo + banco | **Opus 5** | 8 | FE-01, FG-09, F4-10 | **G1** |
| FE-03 | `data/metricas_explorador.toml`: métricas por omisión, con su rol, su agregado y su clase de magnitud | datos | Sonnet 5 | 3 | FE-02 | **G1** |
| FE-04 | **Celda sin dato ≠ 0**: rol ausente, canal vacío o agregado no calculable, distinguibles entre sí y de un cero real | módulo + pruebas | **Opus 5** | 4 | FE-02 | **G1** |
| FE-05 | Tabla del explorador: una fila por log, orden **en canónica** y presentación en la unidad activa | componente | Sonnet 5 | 5 | FE-03, F1-19 | G3 |
| FE-06 | Filtros por métrica combinables («λ mín < 0,80» y «más de 5 eventos de knock»), escritos en la unidad activa | componente | Sonnet 5 | 5 | FE-05 | G3 |
| FE-07 | Personalización de columnas: añadir, quitar y reordenar métricas, persistido en el espacio de trabajo | componente | Sonnet 5 | 4 | FE-03, FE-05 | G3 |
| FE-08 | Escaneo **incremental y cancelable**, con filas apareciendo a medida que se calculan | módulo | Sonnet 5 | 4 | FE-01 | G3 |
| FE-09 | Abrir la selección en el espacio de trabajo, uno o varios logs, conservando el perfil activo | componente | Sonnet 5 | 3 | FE-05 | G3 |
| FE-10 | **Prueba de coherencia**: el resumen de cada log del corpus coincide con abrirlo entero, agregado a agregado | suite de pruebas | **Opus 5** | 5 | FE-02 | **G1** |
| FE-11 | Presupuestos de §2.6 del explorador: carpeta de 200 logs en frío, reapertura desde índice y resumen de un log de 66 MB | banco + CI | **Opus 5** | 4 | FE-02 | G2 |
| FE-12 | Documentación: cómo se triagea una carpeta y qué significa exactamente cada agregado | guía | Haiku 4.5 | 2 | FE-07 | G4 |

**Subtotal FE: 52 pts** · Hito **ME**: una carpeta con los logs de una jornada se
abre como tabla, se ordena por λ mínima, se filtra por «tiene eventos de knock» y
los tres logs elegidos se abren juntos en el espacio de trabajo.

FE-10 es la tarea que sostiene la credibilidad de la fase entera y por eso lleva
puerta G1: si el número de la tabla no es el mismo que el del log abierto, el
explorador deja de ser una herramienta de selección y pasa a ser una fuente de
decisiones equivocadas (riesgo R14).

## 5.10 Fase F5 — Endurecimiento y v1.0 (semanas 24–26)

| ID | Tarea | Entregable | Modelo | Pts | Dep. | Puerta |
|---|---|---|---|---|---|---|
| F5-01 | Empaquetado `onedir` en ZIP para las 3 plataformas, con exclusión agresiva de módulos para el presupuesto de tamaño | artefactos + CI | **Opus 5** | 6 | F1-35 | G2 |
| F5-02 | **Modo portable** con `portable.txt`: cero escritura fuera de la carpeta | módulo + prueba | **Opus 5** | 5 | F5-01 | **G1** |
| F5-03 | Detección de WebView2 ausente con descarga guiada | módulo | Sonnet 5 | 3 | F5-01 | G3 |
| F5-04 | Firma y notarización | CI | Sonnet 5 | 4 | F5-01 | G3 |
| F5-05 | Actualizador opcional y desactivable | módulo | Sonnet 5 | 4 | F5-01 | G3 |
| F5-06 | Despliegue de la **versión navegador** contra un backend Python (local o de la red del equipo) | artefacto + CI + guía | Sonnet 5 | 5 | F1-21 | G3 |
| F5-07 | Espacio de trabajo `.dlvproj` persistente, con emparejamientos y unidades | módulo | Sonnet 5 | 5 | F3-01, F2-03 | G3 |
| F5-08 | Anotaciones y marcadores exportables | componente | Sonnet 5 | 4 | F5-07 | G3 |
| F5-09 | Paleta de comandos | componente | Sonnet 5 | 3 | F1-33 | G3 |
| F5-10 | i18n ES/EN: extracción de cadenas y catálogos | cadenas + catálogos | Haiku 4.5 | 4 | F1-32 | G4 |
| F5-11 | Onboarding: propuesta de perfil en lugar de lienzo vacío | componente | Sonnet 5 | 3 | F3-04 | G3 |
| F5-12 | Pruebas de **regresión visual** del renderizador (obligatorias por ADR-006) | suite | Sonnet 5 | 4 | F1-23 | G3 |
| F5-13 | Revisión de seguridad: rutas, deserialización, evaluador de expresiones, **token y enlace del servidor local** | informe + correcciones | **Opus 5** | 6 | F3-18, F5-07 | **G1** |
| F5-14 | Auditoría final contra los presupuestos de §2.6, incluidos tamaño y arranque en frío | informe | **Opus 5** | 5 | todo | **G1** |
| F5-15 | Corrección de defectos y pulido | varios | Sonnet 5 | 8 | todo | G3 |
| F5-16 | Manual de usuario y notas de la versión | documentación | Haiku 4.5 | 4 | todo | G4 |
| F5-17 | Asociación de extensiones opcional y reversible | módulo | Sonnet 5 | 3 | F5-01 | G3 |

**Subtotal F5: 76 pts** · Hito **M5 = v1.0**

## 5.11 Resumen de asignación

| Modelo | Puntos | % del esfuerzo | Tareas | Concentración |
|---|---|---|---|---|
| **Opus 5** | 435 | 58 % | 74 | parser, almacén, pirámide, **conversiones de unidad**, **sondeo y roles del importador genérico**, renderizador, motor de tiempo, detectores, tablas de corrección, rendimiento, seguridad |
| **Sonnet 5** | 282 | 38 % | 66 | interfaz, perfiles, asistente de importación, exportadores, empaquetado, integración |
| **Haiku 4.5** | 33 | 4 % | 13 | *fixtures*, CI, catálogos mecánicos, i18n, documentación mecánica |
| **Total** | **750** | 100 % | **153** | |

Reparto por fase: F0 54 · F1 215 · FG 92 · F2 80 · F3 118 · F4 63 · **FE 52** · F5 76.

(Las cifras anteriores de esta sección decían 669 puntos en 136 tareas y F1 186.
No cuadraban con la suma de las propias tablas desde la revisión 2 —el libro de
estado ya sembraba 698— y se corrigen aquí junto con el alcance nuevo.)

Distribución de puertas: **51 tareas en G1** (revisión humana obligatoria), 30 en
G2, 61 en G3, 11 en G4. El esfuerzo de revisión de G1 y G2 es **adicional** a los
750 puntos y se presupuesta como un 20 % de sobrecoste sobre las tareas que las
requieren.

La proporción de Opus 5 sube del 52 % al 58 % con las dos épicas nuevas, y no por
inercia: **E13 y E14 son casi enteramente trabajo de corrección sutil**. Una
conversión de unidades mal clasificada como punto en lugar de intervalo, o un rol
asignado por parecido de nombre a una columna con otra escala, produce un número
plausible y falso. Es exactamente el perfil de error que justifica el modelo más
capaz y la puerta de revisión más estricta — y es la razón de que 51 de 153 tareas
lleven revisión humana obligatoria.

## 5.12 Higiene de contexto por modelo

Lo que hace fallar estas asignaciones no es la capacidad del modelo, es el
contexto que recibe:

- **Tareas de Opus 5**: se le dan los ADRs afectados, `01-formato-log.md`
  completo, `06-sistema-de-unidades.md` o `07-formatos-y-csv-generico.md` según
  toque, y los presupuestos de rendimiento aplicables. Se espera que cuestione la
  especificación si encuentra una contradicción, y se registra cuando lo hace.
- **Tareas de Sonnet 5**: se le da el módulo aguas arriba ya terminado, el esquema
  de datos y un criterio de aceptación comprobable. Nunca una decisión de
  arquitectura pendiente.
- **Tareas de Haiku 4.5**: se le da la especificación completa y un ejemplo
  resuelto de la misma clase de tarea. Si necesita una aclaración, la
  especificación estaba mal y se corrige antes de reasignar.
- **Todas, en `dlv-core`**: la revisión pregunta siempre «¿cuántas veces se
  ejecuta esto por muestra?» (ADR-009). Un bucle de Python sobre muestras es un
  rechazo automático, no una sugerencia de mejora.
- **Todas, en unidades y roles**: no se le pide a ningún modelo inventar un factor
  de escala ni un rango plausible. Los factores salen del análisis de datos con
  evidencia (F0-08, F0-09, F1-38), los rangos del dominio (F0-10), todo pasa por
  G1, y lo no confirmado se marca `unknown` y se muestra en crudo. Esta es la
  regla que protege R1 y R10, los dos riesgos que pueden romper un motor.
