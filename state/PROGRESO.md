# Progreso de ejecución

> Generado por `tools/estado.py render`. **No editar a mano**: la fuente
> es `state/tareas.json`. Protocolo de reanudación en
> [`docs/08-ejecucion-y-reanudacion.md`](../docs/08-ejecucion-y-reanudacion.md).

Actualizado: 2026-08-19 17:56:48Z

**346 / 775 pts cerrados (44.6 %)** · 162 pts esperando revisión humana → 65.5 % entregado

| Fase | Hecho | En revisión | En curso | Pendiente | Bloqueado | Total |
|---|---|---|---|---|---|---|
| F0 | 35 | 19 | 0 | 0 | 0 | 54 |
| F1 | 190 | 44 | 0 | 0 | 0 | 234 |
| FG | 46 | 48 | 0 | 4 | 0 | 98 |
| F2 | 9 | 12 | 5 | 54 | 0 | 80 |
| F3 | 26 | 34 | 12 | 43 | 3 | 118 |
| F4 | 9 | 0 | 4 | 50 | 0 | 63 |
| FE | 9 | 0 | 0 | 43 | 0 | 52 |
| F5 | 22 | 5 | 7 | 42 | 0 | 76 |

## Requieren atención

| Tarea | Estado | Modelo | Puerta | Última nota |
|---|---|---|---|---|
| `F0-01` Cerrar ADR-001…009 y spike de rendimiento de | revision_humana | Opus 5 | G1 | REVISAR: memoria_residente INCUMPLE 4.42x el CSV (310 MB pico / 70.13  |
| `F0-07` Log de verdad de referencia con knock y λ po | revision_humana | Opus 5 | G1 | RESUELTO el punto de REVISAR de la nota anterior: los umbrales ya no s |
| `F0-10` Catálogo `roles.toml`: roles semánticos, dim | revision_humana | Opus 5 | G1 | data/roles.toml: 58 roles con dimension, rango plausible en unidad can |
| `F0-13` Log equivalente en dos formatos (nativo + ge | revision_humana | Sonnet 5 | G1 | samples/dos-formatos/ con nativo.csv (Haltech, crudo) y generico.csv ( |
| `F1-03` Celda vacía ≠ 0, centinelas de desbordamient | revision_humana | Opus 5 | G1 | Modulo dlv_core/formatos/limpieza.py, dos reglas de docs/01 SS1.13 sob |
| `F1-04` Reconciliación de reloj: 12 h de cabecera, e | revision_humana | Opus 5 | G1 | dlv_core/reloj.py + dlv-core/tests/test_reloj.py (50 pruebas). Tres av |
| `F1-13` Motor de conversión: afín y recíproca, con c | revision_humana | Opus 5 | G1 | dlv-core/src/dlv_core/unidades.py: motor de conversion completo. Afin  |
| `F1-14` Conversiones parametrizadas por canal (λ→AFR | revision_humana | Opus 5 | G1 | resolver_parametro_de_canal(valores_canonicos, rol, tolerancia_relativ |
| `F1-15` Presión absoluta/relativa como cambio de ori | revision_humana | Opus 5 | G1 | REVISAR (G1, ordenado por consecuencia): (1) DISCREPANCIA ENTRE ESPECI |
| `F1-16` Dimensiones compuestas derivadas (`%/kPa` →  | revision_humana | Opus 5 | G1 | REVISAR (G1, ordenado por consecuencia): (1) LA ARITMETICA ES a_num/a_ |
| `F1-20` Prueba de la trampa del delta (Δ10 K = 10 °C | revision_humana | Opus 5 | G1 | data/casos_de_unidades.toml (38 filas: 22 puntos, 5 deltas, 2 varianza |
| `F1-38` Confirmar los 21 tipos `unknown` con análisi | revision_humana | Opus 5 | G1 | Cierra 2 de los 7 tipos desconocidos que quedaban y corrige la evidenc |
| `F1-47` La identidad del inyector fija tres factores | revision_humana | Opus 5 | G1 | CUARTA COMPROBACION, independiente del inyector: aritmetica de motor c |
| `FG-01` Sondeo: codificación, fin de línea, delimita | revision_humana | Opus 5 | G1 | dlv_core/formatos/sondeo.py: pasos 1,2,3 y 5 de SS7.4 (codificacion co |
| `FG-02` Separador decimal con verificación cruzada d | revision_humana | Opus 5 | G1 | dlv_core/formatos/decimal_csv.py + 32 pruebas. Verificacion cruzada de |
| `FG-03` Estructura: preámbulo de metadatos, fila de  | revision_humana | Opus 5 | G1 | dlv_core/formatos/estructura.py + 31 pruebas. Preambulo, nombres, fila |
| `FG-04` Columna de tiempo en las 8 variantes de §7.5 | revision_humana | Opus 5 | G1 | dlv_core/formatos/tiempo_csv.py + 39 pruebas. Las ocho variantes de SS |
| `FG-06` Unidad declarada en el nombre o en la fila d | revision_humana | Sonnet 5 | G1 | Entregado por agente Sonnet, revisado e integrado por Opus. Commits 45 |
| `FG-07` Valores no numéricos, unidad embebida en la  | revision_humana | Sonnet 5 | G1 | PUERTA G1: revisar (1) que caracteres cuentan como unidad embebida, (2 |
| `FG-09` Asignación automática de roles por sinónimos | revision_humana | Opus 5 | G1 | REVISAR (G1, ordenado por consecuencia): (1) LO QUE MAS IMPORTA: asign |
| `FG-10` Informe de plausibilidad por rango declarado | revision_humana | Opus 5 | G1 | dlv_core/plausibilidad.py + 46 pruebas. Contrasta los valores REALES d |
| `F2-01` Modelo de segmento y eje X virtual | en_curso | Opus 5 | G2 | CORRECCION DE MI PROPIO REGISTRO: la habia marcado 'hecho', y no lo es |
| `F2-02` Identidad de canal en capas (rol → `(formato | revision_humana | Opus 5 | G1 | dlv_core/identidad.py: las cuatro capas de SS7.11 (manual > rol > (for |
| `F2-13` Conflictos: mismo rol con unidades de origen | revision_humana | Opus 5 | G1 | Entregada por un agente Opus, revisada e integrada por Opus. dlv-core/ |
| `F3-06` Motor de detectores: las 9 primitivas de §4. | revision_humana | Opus 5 | G1 | Las 9 primitivas de docs/04 SS4.3 en dlv_core/primitivas.py (1537 line |
| `F3-07` Detectores D1–D18 por rol, como configuració | revision_humana | Opus 5 | G1 | YA ESTABA HECHA. No la he entregado yo: el libro de estado la tenia co |
| `F3-08` Desactivación de detectores críticos cuando  | revision_humana | Opus 5 | G1 | REVISAR, por orden de consecuencia: (1) LA POLITICA REAL AFECTA A CUAT |
| `F3-10` Topes de alerta: aviso, crítico, banda y cur | revision_humana | Opus 5 | G1 | REVISAR, por orden de consecuencia: (1) FUERA DEL RANGO DE UNA TABLA S |
| `F3-11` Dibujo de límites y bandas sobre los paneles | en_curso | Sonnet 5 | G3 | — |
| `F3-13` Carriles de estado para canales enumerados | en_curso | Sonnet 5 | G3 | DIVERGENCIA DETECTADA EN AUDITORIA: el trabajo esta commiteado (c9bd9a |
| `F3-15` Ampliar `enums.toml` con los códigos deducid | bloqueado | Haiku 4.5 | G3 | Intentado por un agente Haiku en segundo plano; RECHAZADO por el orque |
| `F3-19` Biblioteca de fórmulas de §4.5, cada una con | revision_humana | Sonnet 5 | G1 | data/formulas.toml con las 7 formulas puntuales de docs/04 SS4.5 + 55  |
| `F3-21` Modo oscuro y modo alto contraste | en_curso | Haiku 4.5 | G4 | CODIGO COMPLETO Y REVISADO, PENDIENTE SOLO DE LA PUERTA G4 (que CI pas |
| `F4-01` Malla RPM×MAP configurable, con los ejes mos | en_curso | Sonnet 5 | G3 | CODIGO COMPLETO Y REVISADO, PENDIENTE SOLO DE LA PUERTA G3 EN UNA MAQU |
| `F5-02` Modo portable con `portable.txt`: cero escri | revision_humana | Opus 5 | G1 | PUERTA G1: revisar (1) carpeta de solo lectura -> hoy falla con aviso  |
| `F5-09` Paleta de comandos | en_curso | Sonnet 5 | G3 | CODIGO COMPLETO Y REVISADO, PENDIENTE DE G3 (vitest en CI). Commit c61 |
| `F5-10` i18n ES/EN: extracción de cadenas y catálogo | en_curso | Haiku 4.5 | G4 | — |

## F0 — 54/54 pts

| | ID | Tarea | Modelo | Pts | Deps | Puerta | Commits |
|---|---|---|---|---|---|---|---|
| ⏳ | `F0-01` | Cerrar ADR-001…009 y spike de rendimiento de Polars sobre el A | Opus 5 | 6 | F0-05 | G1 | `4229523` |
| ✔  | `F0-02` | Andamiaje: paquetes `dlv-core`, `dlv-api`, `dlv-ui`, `dlv-app` | Sonnet 5 | 4 | — | G3 | `9c54663` |
| ✔  | `F0-03` | CI: matriz de 3 plataformas, `pytest`, `ruff`, `mypy`, `eslint | Haiku 4.5 | 2 | F0-02 | G4 | `4229523` |
| ✔  | `F0-04` | Banco de rendimiento con publicación de métricas y puertas de  | Opus 5 | 5 | F0-02 | G2 | `4229523` |
| ✔  | `F0-05` | Corpus: los 3 logs reales + generador de sintéticos (1 h/475 c | Sonnet 5 | 4 | — | G3 | `2af6150` |
| ✔  | `F0-06` | Corpus de logs corruptos (11 casos de `01-formato-log.md` §1.1 | Haiku 4.5 | 2 | F0-05 | G4 | `217d88b` |
| ⏳ | `F0-07` | Log de verdad de referencia con knock y λ pobre anotados | Opus 5 | 4 | F0-05 | G1 | `efc4f55` |
| ✔  | `F0-08` | Catálogo `units.toml`: dimensiones, canónicas, unidades altern | Opus 5 | 6 | — | G1 | `0fbe4ea` |
| ✔  | `F0-09` | `formats/haltech_nsp.toml`: los 34 tipos → dimensión + escala  | Opus 5 | 5 | F0-08 | G1 | `ed16fb5` |
| ⏳ | `F0-10` | Catálogo `roles.toml`: roles semánticos, dimensión esperada, r | Opus 5 | 6 | F0-08 | G1 | `ed16fb5` |
| ✔  | `F0-11` | Esqueleto `enums.toml` con los 75 candidatos, sin traducir | Haiku 4.5 | 2 | F0-10 | G3 | `02140f8` |
| ✔  | `F0-12` | Corpus de CSV genéricos (matriz de `02-alcance-y-plan.md` §2.9 | Haiku 4.5 | 3 | F0-05 | G4 | `4229523` |
| ⏳ | `F0-13` | Log equivalente en dos formatos (nativo + genérico) para la pr | Sonnet 5 | 3 | F0-12 | G1 | `613f5f8` |
| ✔  | `F0-14` | Guía de contribución, convenciones y ADR-009 documentado como  | Haiku 4.5 | 2 | F0-02 | G4 | `ed16fb5` |

## F1 — 234/234 pts

| | ID | Tarea | Modelo | Pts | Deps | Puerta | Commits |
|---|---|---|---|---|---|---|---|
| ✔  | `F1-01` | Parser de cabecera Haltech dirigido por descriptor, tolerante  | Opus 5 | 5 | F0-09 | G1 | `1aa0fc4` |
| ✔  | `F1-02` | Parseo del cuerpo con Polars: ≥ 100 MB/s agregado, cero bucles | Opus 5 | 8 | F1-01 | G1 | `e968ba5` |
| ⏳ | `F1-03` | Celda vacía ≠ 0, centinelas de desbordamiento, filas malformad | Opus 5 | 5 | F1-02 | G1 | `21a701f` |
| ⏳ | `F1-04` | Reconciliación de reloj: 12 h de cabecera, epoch ficticia, cru | Opus 5 | 5 | F1-01 | G1 | `ad4ada0` |
| ✔  | `F1-05` | Almacén columnar con `Storage` por canal y `t` compartido por  | Opus 5 | 8 | F1-03 | G2 | `c1296dd` |
| ✔  | `F1-06` | Detección de grupos de muestreo por patrón de nulos, vectoriza | Opus 5 | 5 | F1-05 | G2 | `e1b5cf4` |
| ✔  | `F1-07` | Indexado: mín/máx/percentiles, clasificación `activo/constante | Sonnet 5 | 4 | F1-05 | G3 | `2b24e8d` |
| ✔  | `F1-08` | Detección de huecos de muestreo y marcas de discontinuidad | Sonnet 5 | 3 | F1-05 | G3 | `062c28a` |
| ✔  | `F1-09` | Pirámide de decimación NumPy vectorizada (`min/max/first/last` | Opus 5 | 8 | F1-05 | G2 | `815a8e4` |
| ✔  | `F1-10` | Variantes de agregación: suma de delta, moda de enum, OR de bi | Opus 5 | 6 | F1-09 | G2 | `4471cbc` |
| ✔  | `F1-11` | Caché Parquet con pirámide persistida e invalidación por versi | Sonnet 5 | 5 | F1-09 | G3 | `066a396` |
| ✔  | `F1-12` | Informe de importación acumulativo, no bloqueante | Sonnet 5 | 3 | F1-03 | G3 | `d05c389` |
| ⏳ | `F1-13` | Motor de conversión: afín y recíproca, con clases punto / inte | Opus 5 | 8 | F0-08 | G1 | `0cac953` |
| ⏳ | `F1-14` | Conversiones parametrizadas por canal (λ→AFR con la estequiome | Opus 5 | 5 | F1-13 | G1 | `b15f5b9` |
| ⏳ | `F1-15` | Presión absoluta/relativa como cambio de origen combinable con | Opus 5 | 5 | F1-13 | G1 | `dcb9944` |
| ⏳ | `F1-16` | Dimensiones compuestas derivadas (`%/kPa` → `%/psi`) | Opus 5 | 4 | F1-13 | G1 | `dcb9944` |
| ✔  | `F1-17` | Precedencia canal > dimensión del perfil > preset global > can | Sonnet 5 | 4 | F1-13 | G3 | `9c80a89` |
| ✔  | `F1-18` | Presets SI / Métrico / Imperial / Motorsport EU / Motorsport U | Sonnet 5 | 3 | F1-17 | G1 | `a521091` |
| ✔  | `F1-19` | Umbrales y perfiles en canónica, editados en la unidad activa | Opus 5 | 4 | F1-13 | G1 | `dcb9944` |
| ⏳ | `F1-20` | Prueba de la trampa del delta (Δ10 K = 10 °C = 18 °F) y tabla  | Opus 5 | 4 | F1-13 | G1 | `e94094b` |
| ✔  | `F1-21` | `dlv-api`: FastAPI, `127.0.0.1`, puerto efímero, token de sesi | Opus 5 | 5 | F1-05 | G2 | `8f51688` |
| ✔  | `F1-22` | Transporte binario Arrow IPC / `TypedArray` para series; JSON  | Opus 5 | 5 | F1-21 | G2 | `3296f2e` |
| ✔  | `F1-23` | Renderizador WebGL2 de series desde la pirámide | Opus 5 | 13 | F1-09, F1-22 | G2 | `2aef6b3` |
| ✔  | `F1-24` | Caché de cubos en el frontend — es lo que hace alcanzable el c | Opus 5 | 5 | F1-23 | G2 | `fb0548d` |
| ✔  | `F1-25` | Ejes, rejilla y leyenda SVG con ticks calculados en la unidad  | Sonnet 5 | 5 | F1-23, F1-17 | G3 | `aa48667` |
| ✔  | `F1-26` | Paneles apilados con eje X compartido y arrastrar canales entr | Sonnet 5 | 5 | F1-25 | G3 | `5597b6c` |
| ✔  | `F1-27` | Múltiples ejes Y, autoescala y bloqueo de escala | Sonnet 5 | 4 | F1-25 | G3 | `cc06c82` |
| ✔  | `F1-28` | Zoom/pan por rueda, teclado y pointer events; historial de zoo | Sonnet 5 | 5 | F1-23 | G3 | `b3057b4` |
| ✔  | `F1-29` | Cursor con tabla de valores, presupuesto < 16 ms | Sonnet 5 | 4 | F1-24 | G3 | `f66226a` |
| ✔  | `F1-30` | Doble cursor con delta usando la clase intervalo | Opus 5 | 4 | F1-29, F1-13 | G1 | `33a7c27` |
| ✔  | `F1-31` | Selector de unidad a tres niveles (global, dimensión, canal) c | Sonnet 5 | 5 | F1-17 | G3 | `2f707a6` |
| ✔  | `F1-32` | Locale numérico ES/EN (separador decimal, agrupación) | Haiku 4.5 | 2 | F1-31 | G4 | `e382352` |
| ✔  | `F1-33` | Selector de canales con búsqueda difusa y ocultación de inacti | Sonnet 5 | 4 | F1-07 | G3 | `88c015d` |
| ✔  | `F1-34` | Arrastrar y soltar ficheros y carpetas; apertura múltiple | Sonnet 5 | 3 | F1-12 | G3 | `a26fb1b` |
| ✔  | `F1-35` | Contenedor `pywebview` + PyInstaller `onedir` para desarrollo | Sonnet 5 | 4 | F0-03, F1-21 | G3 | `ee4fb16` |
| ✔  | `F1-36` | Fuzzing de propiedad sobre cabecera y filas (Hypothesis) | Opus 5 | 4 | F1-03, F0-06 | G2 | `b01e52e` |
| ✔  | `F1-37` | Presupuestos de F1 como puertas de CI, incluido el de cambio d | Haiku 4.5 | 2 | F0-04, F1-23 | G4 | `2e92399` |
| ⏳ | `F1-38` | Confirmar los 21 tipos `unknown` con análisis de datos y evide | Opus 5 | 5 | F0-09 | G1 | `a504996` |
| ✔  | `F1-39` | Montaje de la aplicación: unir renderizador, ejes, paneles, es | Sonnet 5 | 8 | F1-26, F1-28, F1-29, F1-31, F1-33 | G3 | `e918085` |
| ✔  | `F1-40` | Sesión de log abierto en `dlv-api` y endpoint de cubos de pirá | Opus 5 | 8 | F1-21, F1-09, F1-11 | G2 | — |
| ✔  | `F1-41` | Selector de tipo de combustible y factores de conversión edita | Sonnet 5 | 3 | F1-14 | G3 | — |
| ✔  | `F1-42` | Apertura en < 4 s: `detectar_grupos_de_muestreo` usa `np.uniqu | Opus 5 | 5 | F1-05, F1-06, F1-40 | G2 | `501b77b` |
| ✔  | `F1-43` | La aplicación abre un log de verdad: cablear `FuenteApi`, búfe | Opus 5 | 5 | F1-39, F1-40, F1-35 | G2 | — |
| ✔  | `F1-44` | Un log real abierto enseña sus datos: CORS con `expose_headers | Opus 5 | 3 | F1-43 | G2 | `3eec0d4` |
| ✔  | `F1-45` | E13 llega a la ventana: conversiones reales por HTTP, motor de | Opus 5 | 8 | F1-13, F1-30, F1-41, F1-44 | G1 | `1fff834` |
| ✔  | `F1-46` | Los factores del catálogo, derivados de su definición: `data/d | Opus 5 | 5 | F0-08, F1-20 | G2 | `acec9a7` |
| ⏳ | `F1-47` | La identidad del inyector fija tres factores: el caudal config | Opus 5 | 3 | F0-09, FG-10 | G1 | `db56e94` |

## FG — 94/98 pts

| | ID | Tarea | Modelo | Pts | Deps | Puerta | Commits |
|---|---|---|---|---|---|---|---|
| ⏳ | `FG-01` | Sondeo: codificación, fin de línea, delimitador por consistenc | Opus 5 | 8 | F1-02 | G1 | `61af05c` |
| ⏳ | `FG-02` | Separador decimal con verificación cruzada de interpretaciones | Opus 5 | 5 | FG-01 | G1 | `e09905f` |
| ⏳ | `FG-03` | Estructura: preámbulo de metadatos, fila de nombres, fila de u | Opus 5 | 5 | FG-01 | G1 | `dadd9b6` |
| ⏳ | `FG-04` | Columna de tiempo en las 8 variantes de §7.5, incluida la ause | Opus 5 | 8 | FG-03 | G1 | `8adc47f` |
| ✔  | `FG-05` | Inferencia de tipo por columna: entero, decimal, enum de texto | Opus 5 | 5 | FG-03 | G2 | `88d1c71` |
| ⏳ | `FG-06` | Unidad declarada en el nombre o en la fila de unidades + dicci | Sonnet 5 | 5 | FG-03, F0-08 | G1 | `45a0600` |
| ⏳ | `FG-07` | Valores no numéricos, unidad embebida en la celda, separador d | Sonnet 5 | 4 | FG-05 | G1 | `90a05d4` |
| ✔  | `FG-08` | Columnas de texto y booleanas → enum con diccionario autogener | Sonnet 5 | 3 | FG-05 | G3 | `4ef462e` |
| ⏳ | `FG-09` | Asignación automática de roles por sinónimos, normalización y  | Opus 5 | 8 | F0-10 | G1 | `334a088` |
| ⏳ | `FG-10` | Informe de plausibilidad por rango declarado de cada rol | Opus 5 | 5 | FG-09 | G1 | `30666f0` |
| ✔  | `FG-11` | Asistente de importación de 3 pasos con previsualización viva | Sonnet 5 | 8 | FG-04, FG-09 | G3 | `1b76111` |
| ✔  | `FG-12` | Perfil `.dlvimport` con huella de cabecera y reaplicación parc | Sonnet 5 | 5 | FG-11 | G3 | `dbc6c77` |
| ✔  | `FG-13` | Descriptores de formato nativo declarativos; migrar Haltech a  | Opus 5 | 8 | F1-01 | G2 | `71c9f21` |
| ✔  | `FG-14` | Robustez: filas de longitud variable, columnas duplicadas, cab | Sonnet 5 | 4 | FG-05 | G3 | `682de2f` |
| ✔  | `FG-15` | Fuzzing del importador genérico sobre el corpus de CSV | Opus 5 | 4 | FG-14, F0-12 | G2 | `46d8ff6` |
| ·  | `FG-16` | Prueba de independencia de fabricante: el log de F0-13 da resu | Opus 5 | 4 | FG-09, F0-13 | G1 | — |
| ✔  | `FG-17` | Documentación: importar un CSV cualquiera y añadir un formato  | Sonnet 5 | 3 | FG-13 | G3 | `d1f559d` |
| ✔  | `FG-18` | El sondeo genérico llega a HTTP: endpoints de `dlv-api` para d | Opus 5 | 6 | FG-01, FG-03, FG-04, FG-05, FG-09, FG-11 | G2 | `24909a3` |

## F2 — 21/80 pts

| | ID | Tarea | Modelo | Pts | Deps | Puerta | Commits |
|---|---|---|---|---|---|---|---|
| ▶  | `F2-01` | Modelo de segmento y eje X virtual | Opus 5 | 5 | F1-05 | G2 | `9408b4f` |
| ⏳ | `F2-02` | Identidad de canal en capas (rol → `(formato, ID)` → nombre no | Opus 5 | 8 | FG-09 | G1 | `e6504cf` |
| ✔  | `F2-03` | Emparejamiento manual con prioridad máxima, persistido en el p | Sonnet 5 | 4 | F2-02 | G3 | `dadd9b6` |
| ·  | `F2-04` | Vista paralela: N segmentos superpuestos, color por log | Sonnet 5 | 5 | F2-01, F1-26 | G3 | — |
| ·  | `F2-05` | Alineación por reloj absoluto y por relativo | Sonnet 5 | 3 | F2-01, F1-04 | G3 | — |
| ·  | `F2-06` | Desfase manual arrastrando el segmento | Sonnet 5 | 3 | F2-04 | G3 | — |
| ·  | `F2-07` | Anclaje por evento (primer WOT, primer corte, launch) | Opus 5 | 5 | F2-01 | G2 | — |
| ·  | `F2-08` | Autoalineación por correlación cruzada en L4–L6 con refinamien | Opus 5 | 8 | F2-01, F1-09 | G2 | — |
| ·  | `F2-09` | Vista concatenada: unión por identidad, fronteras visibles, si | Opus 5 | 8 | F2-02 | G1 | — |
| ·  | `F2-10` | Orden por `Log Number` con desfase editable y auditable | Sonnet 5 | 4 | F2-09 | G3 | — |
| ·  | `F2-11` | Estadísticas y detectores que respetan las fronteras de segmen | Opus 5 | 5 | F2-09 | G2 | — |
| ·  | `F2-12` | Eje X alternativo (RPM, velocidad, distancia) con monotonía po | Opus 5 | 8 | F2-01 | G2 | — |
| ⏳ | `F2-13` | Conflictos: mismo rol con unidades de origen distintas → canón | Opus 5 | 4 | F2-02, F1-13 | G1 | `e717ffa` |
| ✔  | `F2-14` | Renderizado progresivo: silueta inmediata, refinamiento de fon | Opus 5 | 5 | F1-23 | G2 | `4a34148` |
| ·  | `F2-15` | Banco del caso peor: 8 logs × 30 min, incluido cambio de unida | Sonnet 5 | 3 | F2-04 | G3 | — |
| ·  | `F2-16` | Documentación de usuario de multi-log | Haiku 4.5 | 2 | F2-09 | G4 | — |

## F3 — 60/118 pts

| | ID | Tarea | Modelo | Pts | Deps | Puerta | Commits |
|---|---|---|---|---|---|---|---|
| ·  | `F3-01` | Modelo de perfil `.dlvprofile` por rol, con unidades por dimen | Opus 5 | 6 | F1-21, F0-10 | G1 | — |
| ·  | `F3-02` | Aplicación de perfil por rol con degradación elegante y reserv | Sonnet 5 | 5 | F3-01 | G3 | — |
| ·  | `F3-03` | Los 10 perfiles de fábrica de `04-perfiles-motorsport.md` §4.2 | Sonnet 5 | 8 | F3-02 | G1 | — |
| ·  | `F3-04` | Autosugerencia por cobertura de roles («7 de 9 disponibles») | Sonnet 5 | 4 | F3-02, F1-07 | G3 | — |
| ·  | `F3-05` | Editor de perfiles, duplicado, importación y exportación | Sonnet 5 | 5 | F3-01 | G3 | — |
| ⏳ | `F3-06` | Motor de detectores: las 9 primitivas de §4.3 con histéresis y | Opus 5 | 10 | F1-05 | G1 | `b5ab536` |
| ⏳ | `F3-07` | Detectores D1–D18 por rol, como configuración | Opus 5 | 8 | F3-06, F0-07 | G1 | — |
| ⏳ | `F3-08` | Desactivación de detectores críticos cuando su rol proviene de | Opus 5 | 4 | F3-07, FG-09 | G1 | `3505bae` |
| ·  | `F3-09` | Validación contra la verdad de referencia, en formato nativo y | Opus 5 | 5 | F3-07, F0-13 | G1 | — |
| ⏳ | `F3-10` | Topes de alerta: aviso, crítico, banda y curva en función de o | Opus 5 | 8 | F3-06, F1-19 | G1 | `f0f7b50` |
| ▶  | `F3-11` | Dibujo de límites y bandas sobre los paneles, en la unidad act | Sonnet 5 | 4 | F3-10, F1-25 | G3 | — |
| ✔  | `F3-12` | Panel de incidencias por severidad con salto al instante | Sonnet 5 | 5 | F3-07 | G3 | `6c07905` |
| ▶  | `F3-13` | Carriles de estado para canales enumerados | Sonnet 5 | 5 | F1-10, F0-11 | G3 | — |
| ·  | `F3-14` | Decodificación de máscaras de bits en carriles apilados | Opus 5 | 5 | F3-13 | G1 | — |
| ✖  | `F3-15` | Ampliar `enums.toml` con los códigos deducidos de las muestras | Haiku 4.5 | 3 | F0-11 | G3 | — |
| ✔  | `F3-16` | Segmentación automática: WOT, ralentí, arranque, deceleración, | Opus 5 | 8 | F3-06 | G2 | `24909a3` |
| ·  | `F3-17` | Panel de tiradas con resumen y superposición entre tiradas | Sonnet 5 | 5 | F3-16, F2-12 | G3 | — |
| ✔  | `F3-18` | Evaluador de expresiones en canónica, multi-tasa por retención | Opus 5 | 8 | F1-13 | G2 | `372edba` |
| ⏳ | `F3-19` | Biblioteca de fórmulas de §4.5, cada una con su clase de magni | Sonnet 5 | 4 | F3-18 | G1 | `e31b8a5` |
| ✔  | `F3-20` | Detección de marcha por agrupación de velocidad/rpm | Opus 5 | 5 | F3-18 | G2 | `468251b` |
| ▶  | `F3-21` | Modo oscuro y modo alto contraste | Haiku 4.5 | 3 | F1-25 | G4 | — |

## F4 — 9/63 pts

| | ID | Tarea | Modelo | Pts | Deps | Puerta | Commits |
|---|---|---|---|---|---|---|---|
| ▶  | `F4-01` | Malla RPM×MAP configurable, con los ejes mostrados en la unida | Sonnet 5 | 4 | F1-05 | G3 | — |
| ·  | `F4-02` | Agregación por celda: media, desviación, mín, máx, número de m | Opus 5 | 5 | F4-01 | G2 | — |
| ·  | `F4-03` | Filtros de exclusión: transitorio, corte, protección de motor, | Opus 5 | 8 | F4-02, F3-16 | G1 | — |
| ·  | `F4-04` | Mapa de calor de λ error con detalle por celda | Sonnet 5 | 5 | F4-02 | G3 | — |
| ·  | `F4-05` | Tabla de corrección de combustible, con celdas de confianza in | Opus 5 | 8 | F4-03 | G1 | — |
| ·  | `F4-06` | Exportación de tabla a CSV y portapapeles como malla pegable | Sonnet 5 | 3 | F4-05 | G3 | — |
| ·  | `F4-07` | Mapas de calor de avance de encendido y de densidad de knock | Sonnet 5 | 4 | F4-02 | G3 | — |
| ·  | `F4-08` | Comparación de dos logs celda a celda | Sonnet 5 | 5 | F4-02, F2-02 | G3 | — |
| ✔  | `F4-09` | Métricas de PID de boost: sobreoscilación, establecimiento, er | Opus 5 | 5 | F3-16 | G2 | `e3fd287` |
| ·  | `F4-10` | Estadísticas con la clase de magnitud correcta (varianza con ` | Opus 5 | 4 | F1-13, F4-02 | G1 | — |
| ·  | `F4-11` | Informe de sesión HTML autocontenido, con las unidades usadas  | Sonnet 5 | 5 | F3-12, F4-04 | G3 | — |
| ✔  | `F4-12` | Exportación de vista a PNG/SVG y de datos a CSV/Parquet con un | Sonnet 5 | 4 | F1-23 | G3 | `ec9e0d8` |
| ·  | `F4-13` | Documentación de análisis tabular con las advertencias de fiab | Opus 5 | 3 | F4-05 | G1 | — |

## FE — 9/52 pts

| | ID | Tarea | Modelo | Pts | Deps | Puerta | Commits |
|---|---|---|---|---|---|---|---|
| ✔  | `FE-01` | Recorrido de carpeta e índice con huella (ruta, tamaño, fecha  | Opus 5 | 5 | F1-11 | G2 | `d6a1d39` |
| ·  | `FE-02` | Resumen por log con columnas proyectadas: agregados exactos po | Opus 5 | 8 | FE-01, FG-09, F4-10 | G1 | — |
| ·  | `FE-03` | `data/metricas_explorador.toml`: métricas por omisión, con su  | Sonnet 5 | 3 | FE-02 | G1 | — |
| ·  | `FE-04` | Celda sin dato ≠ 0: rol ausente, canal vacío o agregado no cal | Opus 5 | 4 | FE-02 | G1 | — |
| ·  | `FE-05` | Tabla del explorador: una fila por log, orden en canónica y pr | Sonnet 5 | 5 | FE-03, F1-19 | G3 | — |
| ·  | `FE-06` | Filtros por métrica combinables («λ mín < 0,80» y «más de 5 ev | Sonnet 5 | 5 | FE-05 | G3 | — |
| ·  | `FE-07` | Personalización de columnas: añadir, quitar y reordenar métric | Sonnet 5 | 4 | FE-03, FE-05 | G3 | — |
| ✔  | `FE-08` | Escaneo incremental y cancelable, con filas apareciendo a medi | Sonnet 5 | 4 | FE-01 | G3 | `64293e7` |
| ·  | `FE-09` | Abrir la selección en el espacio de trabajo, uno o varios logs | Sonnet 5 | 3 | FE-05 | G3 | — |
| ·  | `FE-10` | Prueba de coherencia: el resumen de cada log del corpus coinci | Opus 5 | 5 | FE-02 | G1 | — |
| ·  | `FE-11` | Presupuestos de §2.6 del explorador: carpeta de 200 logs en fr | Opus 5 | 4 | FE-02 | G2 | — |
| ·  | `FE-12` | Documentación: cómo se triagea una carpeta y qué significa exa | Haiku 4.5 | 2 | FE-07 | G4 | — |

## F5 — 27/76 pts

| | ID | Tarea | Modelo | Pts | Deps | Puerta | Commits |
|---|---|---|---|---|---|---|---|
| ✔  | `F5-01` | Empaquetado `onedir` en ZIP para las 3 plataformas, con exclus | Opus 5 | 6 | F1-35 | G2 | `3d8d81d` |
| ⏳ | `F5-02` | Modo portable con `portable.txt`: cero escritura fuera de la c | Opus 5 | 5 | F5-01 | G1 | `f317f68` |
| ✔  | `F5-03` | Detección de WebView2 ausente con descarga guiada | Sonnet 5 | 3 | F5-01 | G3 | `0a990f9` |
| ·  | `F5-04` | Firma y notarización | Sonnet 5 | 4 | F5-01 | G3 | — |
| ✔  | `F5-05` | Actualizador opcional y desactivable | Sonnet 5 | 4 | F5-01 | G3 | `5e2bbb8` |
| ✔  | `F5-06` | Despliegue de la versión navegador contra un backend Python (l | Sonnet 5 | 5 | F1-21 | G3 | `5298576` |
| ·  | `F5-07` | Espacio de trabajo `.dlvproj` persistente, con emparejamientos | Sonnet 5 | 5 | F3-01, F2-03 | G3 | — |
| ·  | `F5-08` | Anotaciones y marcadores exportables | Sonnet 5 | 4 | F5-07 | G3 | — |
| ▶  | `F5-09` | Paleta de comandos | Sonnet 5 | 3 | F1-33 | G3 | — |
| ▶  | `F5-10` | i18n ES/EN: extracción de cadenas y catálogos | Haiku 4.5 | 4 | F1-32 | G4 | — |
| ·  | `F5-11` | Onboarding: propuesta de perfil en lugar de lienzo vacío | Sonnet 5 | 3 | F3-04 | G3 | — |
| ✔  | `F5-12` | Pruebas de regresión visual del renderizador (obligatorias por | Sonnet 5 | 4 | F1-23 | G3 | `0a990f9`, `712d3a3` |
| ·  | `F5-13` | Revisión de seguridad: rutas, deserialización, evaluador de ex | Opus 5 | 6 | F3-18, F5-07 | G1 | — |
| ·  | `F5-14` | Auditoría final contra los presupuestos de §2.6, incluidos tam | Opus 5 | 5 | todo | G1 | — |
| ·  | `F5-15` | Corrección de defectos y pulido | Sonnet 5 | 8 | todo | G3 | — |
| ·  | `F5-16` | Manual de usuario y notas de la versión | Haiku 4.5 | 4 | todo | G4 | — |
| ·  | `F5-17` | Asociación de extensiones opcional y reversible | Sonnet 5 | 3 | F5-01 | G3 | — |

Leyenda: ✔ hecho · ⏳ esperando revisión humana (G1) · ▶ en curso · · pendiente · ✖ bloqueado
