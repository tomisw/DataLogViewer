# 02 — Alcance y plan de proyecto

## 2.1 Resumen ejecutivo

DataLogViewer es un visor y analizador de logs de ECU para **tuning y
motorsport**. Se distribuye como **ejecutable portable único** y comparte un
**núcleo en Rust** con una versión web y, en fase posterior, móvil.

La propuesta de valor no es «otro graficador»: es que un tuner abra dos o tres
logs, seleccione un **perfil de análisis** («Fuel/Lambda», «Knock», «Boost») y
en menos de 30 segundos vea las señales relevantes alineadas, las tiradas a
plena carga detectadas automáticamente y una lista de incidencias con enlace al
instante exacto.

- **Duración a v1.0**: 18 semanas en 6 fases.
- **Entregable v1.0**: binario portable Windows/Linux/macOS < 25 MB, sin
  instalación, sin dependencias de runtime.
- **Riesgo principal**: escalas de unidades no confirmadas (11 de 34 tipos) →
  mitigado con registro de unidades versionado y estado de confianza explícito.

## 2.2 Objetivos

| # | Objetivo | Métrica de éxito |
|---|---|---|
| O1 | Comparar logs en paralelo y concatenados | 8 logs simultáneos con alineación por tiempo, RPM o evento |
| O2 | Rendimiento a escala real | 60 fps de pan/zoom con 16 canales y 5 M puntos/canal |
| O3 | Portabilidad | ejecutable único, 0 pasos de instalación, mismo núcleo en web |
| O4 | Facilidad de uso | ≤ 5 clics y < 30 s desde abrir la app hasta un perfil con 2 logs superpuestos |
| O5 | Valor para tuning | tabla de corrección λ sobre malla RPM×MAP exportable, detección de knock y de tiradas |

## 2.3 No objetivos de la v1.0

Declararlos evita el desvío de alcance más habitual en herramientas de tuning:

- **No** se escribe en la ECU. Solo lectura de logs. Ninguna función de flasheo.
- **No** hay telemetría en vivo en v1.0 (se diseña la arquitectura para
  permitirla en v2, ver §2.11).
- **No** hay edición de mapas de la ECU. Se **genera** una tabla de corrección
  exportable (CSV/portapapeles) que el usuario aplica en su software de tuning.
- **No** hay cuenta de usuario, nube ni sincronización. Los ficheros de proyecto
  son locales y compartibles a mano.
- **No** se soportan otros fabricantes en v1.0, pero la capa de formato es un
  *trait* con un solo implementador para que añadir MoTeC i2/ld, AiM, Link o
  MegaSquirt sea una tarea aislada.

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
- E1.2 Registro de unidades versionado (factor, unidad, confianza, centinelas).
- E1.3 Almacenamiento columnar por canal con base de tiempos propia (multi-tasa).
- E1.4 Indexado: clasificación `activo/constante/vacío/fuera de rango`, mín/máx/percentiles por canal.
- E1.5 Caché en disco en Arrow/Parquet: la segunda apertura del mismo fichero es instantánea.
- E1.6 Detección de huecos y marcas de discontinuidad.
- E1.7 Capa de formato como *trait* extensible; informe de importación con avisos.

### E2 — Motor de tiempo multi-log *(prioridad del cliente)*
- E2.1 **Vista paralela**: N logs, un eje X compartido, series superpuestas con color por log.
- E2.2 Modos de alineación:
  - reloj absoluto (cuando el log lo permite, ver §1.4),
  - relativo desde t=0 de cada log,
  - desfase manual arrastrando el log,
  - **anclaje por evento** (primer WOT, primer corte, activación de launch),
  - **autoalineación por correlación cruzada** de un canal de referencia (RPM).
- E2.3 **Vista concatenada**: unión de canales por `ID`, línea de tiempo virtual con desfase por segmento, marcas de frontera visibles y **sin interpolar** sobre las uniones.
- E2.4 Reordenación de segmentos por `Log Number` con desfase editable (obligatorio con epoch ficticia).
- E2.5 Eje X alternativo: **RPM**, velocidad o distancia en lugar de tiempo — imprescindible para comparar tiradas de duración distinta.
- E2.6 Resolución de conflictos de canal: mismo `ID` con escala distinta entre logs → aviso, no mezcla silenciosa.

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
- E4.1 Modelo de perfil: conjunto de paneles, canales, escalas, límites de alerta y detectores, en fichero versionable.
- E4.2 Perfiles integrados de fábrica (detallados en `04-perfiles-motorsport.md`).
- E4.3 Aplicación de perfil por `ID` de canal con degradación elegante si faltan canales.
- E4.4 Editor de perfiles, duplicado, importación/exportación y compartición como fichero suelto.
- E4.5 Autosugerencia: al abrir un log, proponer los perfiles cuyos canales están presentes y activos.

### E5 — Detección de eventos y alertas *(prioridad del cliente)*
- E5.1 Detección de picos con histéresis y tiempo de permanencia mínimo (evita falsos positivos por una muestra de ruido).
- E5.2 **Topes de alerta** por canal: umbral, banda, y condicionales compuestos (`λ > objetivo+5 % AND TPS > 80 % AND RPM > 4000`).
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
- E10.2 Compilación WASM del núcleo y despliegue web de solo lectura.
- E10.3 Firma de binarios y actualizador opcional (desactivable, nunca obligatorio).
- E10.4 Asociación de extensión `.csv`/`.dlv` opcional y reversible.

### E11 — Calidad
- E11.1 Corpus de logs de prueba, incluidos los tres de muestra y ficheros deliberadamente corruptos.
- E11.2 Pruebas de propiedad del parser (*fuzzing* sobre la cabecera y las filas).
- E11.3 Pruebas de regresión de rendimiento en CI con presupuestos que fallan la compilación.
- E11.4 Pruebas de regresión visual del renderizador.

### E12 — Fundamentos de v2 (solo diseño en v1)
- E12.1 Interfaces preparadas para telemetría en vivo (ingesta por *streaming* en el mismo almacén columnar).
- E12.2 Núcleo compilable a móvil; validación de una maqueta táctil.

## 2.6 Presupuestos de rendimiento (criterios de aceptación)

Máquina de referencia: portátil de 4 núcleos, 16 GB RAM, GPU integrada.

| Métrica | Presupuesto | Cómo se mide |
|---|---|---|
| Apertura de log de 66 MB / 475 canales hasta el primer gráfico | **< 3,0 s** p95 | banco automatizado en CI |
| Rendimiento sostenido del parser | **≥ 40 MB/s** por hilo | banco de microtest |
| Segunda apertura (caché Arrow) | **< 400 ms** | banco automatizado |
| Pan/zoom con 16 canales × 5 M puntos | **≥ 60 fps**, sin fotograma > 20 ms | traza de fotogramas |
| Latencia del cursor a tabla actualizada | **< 16 ms** | traza de fotogramas |
| Memoria residente con el log de 66 MB abierto | **≤ 3×** el tamaño del CSV | medida de RSS |
| Arranque en frío hasta ventana interactiva | **< 1,5 s** | banco automatizado |
| Tamaño del binario portable | **< 25 MB** | comprobación de artefacto |
| 8 logs × 30 min en paralelo | abre y navega sin degradación perceptible | prueba manual guionizada |

Estos presupuestos son **puertas de CI**, no aspiraciones. La E11.3 los hace
fallar la compilación cuando se superan.

## 2.7 Fases e hitos

| Fase | Semanas | Contenido | Hito de salida |
|---|---|---|---|
| **F0 — Cimientos** | 1–2 | Andamiaje del repositorio, CI, ADRs cerrados, corpus de pruebas, banco de rendimiento vacío pero funcionando | **M0**: `cargo test` y `npm test` verdes en las 3 plataformas; banco publica métricas |
| **F1 — Núcleo de datos y visor de un log** | 3–6 | E1 completa, E3.1–E3.4, E3.6, E9.1, E9.3 | **M1**: se abre el AutoLog de 475 canales y se navega a 60 fps con 8 canales |
| **F2 — Multi-log** | 7–9 | E2 completa, E3.7 | **M2**: los tres logs de muestra en paralelo con autoalineación, y 2768+2769 concatenados |
| **F3 — Motorsport** | 10–13 | E4, E5, E3.5, E6 | **M3**: perfil «Knock» detecta y lista los eventos de knock del corpus con 0 falsos negativos conocidos |
| **F4 — Análisis avanzado** | 14–16 | E7, E8 | **M4**: tabla de corrección λ generada y exportada desde un log de tirada |
| **F5 — Endurecimiento y v1.0** | 17–18 | E10, E11 completa, E9.2/E9.4/E9.5/E9.6, corrección de defectos | **M5 = v1.0**: binarios firmados, todos los presupuestos de §2.6 en verde |
| **F6 — Post v1.0** | — | E12, móvil, telemetría en vivo, otros fabricantes | fuera del alcance comprometido |

Camino crítico: **E1.3 (almacén columnar) → E3.1 (pirámide/render) → E2.1
(paralelo) → E7.1 (malla)**. Todo lo demás puede paralelizarse alrededor.

## 2.8 Riesgos

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | 11 de 34 tipos de unidad sin factor confirmado → cifras erróneas mostradas a un tuner que decide sobre ellas | Alta | **Crítico** | Registro con `confidence`; los `unknown` se muestran en crudo y marcados. Nunca se inventa una unidad. Validación con un log de referencia del fabricante |
| R2 | Enums y máscaras de bits sin diccionario (75 canales) | Alta | Medio | Carriles de estado con etiqueta genérica `Estado N`; diccionario ampliable por datos; se aceptan aportaciones del usuario |
| R3 | Rendimiento del renderizador no llega a 60 fps con 8 logs | Media | Alto | Pirámide de decimación desde F1, no como optimización posterior; presupuestos en CI desde M0 |
| R4 | El desfase real entre logs internos es indeterminable → conclusiones falsas al concatenar | Media | Alto | Fronteras de segmento siempre visibles, jamás interpolar, desfase editable y auditable; aviso permanente de «tiempo no fiable» |
| R5 | Deriva de alcance hacia escritura en la ECU o edición de mapas | Media | Alto | No objetivo explícito en §2.3; la salida es una tabla exportable |
| R6 | Tauri en móvil resulta insuficiente para la fase 6 | Baja | Medio | El núcleo Rust es independiente de la capa de presentación; el coste de cambiar de contenedor móvil queda acotado a la UI |
| R7 | Variedad de logs del mundo real mucho mayor que las 3 muestras | Alta | Medio | Informe de importación tolerante que nunca aborta; recolección de casos desde F1; corpus creciente |
| R8 | La complejidad de la vista multi-log daña la facilidad de uso | Media | Alto | Perfiles y autoalineación por omisión; la configuración avanzada, oculta tras un panel secundario |

## 2.9 Calidad y datasets de prueba

Corpus mínimo a construir en F0:

1. Los tres logs de muestra (caso base).
2. AutoLog sintético de **1 hora, 475 canales** generado a partir del real (caso de rendimiento).
3. 20 logs internos consecutivos sintéticos (caso de concatenación).
4. Corruptos deliberados: cabecera truncada, fila corta, `DisplayMaxMin` ausente, BOM, CRLF, sin `\n` final, marcas no monótonas, cruce de medianoche, versión `1.2` desconocida, celdas con centinelas de desbordamiento.
5. Log con λ deliberadamente pobre en carga y eventos de knock inyectados, con **verdad de referencia anotada** para validar los detectores de E5.

Sin el punto 5 no se puede afirmar que los detectores funcionan; es el
entregable de QA más valioso del proyecto y se construye en F0/F3.

## 2.10 Definición de terminado

Una tarea está terminada cuando: hay pruebas automáticas que cubren el camino
feliz y al menos un caso límite; los presupuestos de rendimiento afectados
siguen en verde; la documentación del usuario afectada está actualizada; y una
persona ha revisado el diff (ver puertas de revisión en
`05-backlog-y-asignacion-modelos.md`).

## 2.11 Preparación para v2 sin coste en v1

Tres decisiones baratas ahora que evitan una reescritura después:

1. El almacén columnar acepta **añadidos al final** (*append*), no solo carga
   completa. La telemetría en vivo es entonces «un log que crece».
2. El núcleo no toca el sistema de ficheros directamente: recibe *readers*. Eso
   habilita WASM, móvil y, más adelante, orígenes de red sin cambios.
3. La UI se comunica con el núcleo por comandos serializables. La misma UI puede
   hablar con un núcleo local, WASM o remoto.
