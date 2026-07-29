# DataLogViewer

Visor y analizador de logs de ECU orientado a **ECU tuning** y **motorsport**.

Este repositorio contiene, por ahora, el **alcance y plan de proyecto**. Toda la
documentación está derivada del análisis de tres logs reales (Haltech NSP,
`DataLogVersion 1.1`) aportados como muestra, no de suposiciones.

## Prioridades del producto

1. **Multi-log**: visualización de varios logs en **paralelo** (superpuestos) y
   **concatenada** (como una sola sesión continua).
2. **Rendimiento**: logs de horas y cientos de canales sin degradar el pan/zoom.
3. **Portabilidad**: paquete sin instalación; el mismo núcleo sirve a la versión
   de escritorio, a la de navegador y, más adelante, al móvil.
4. **Facilidad de uso**: perfiles de análisis preconfigurados en lugar de
   construir cada gráfico a mano.
5. **Funcionalidad motorsport**: detección de picos, topes de alerta, análisis de
   knock, control de boost, tablas de corrección λ, segmentación de tiradas…
6. **Unidades intercambiables**: cada dimensión con varias unidades (K/°C/°F,
   kPa/bar/psi, λ/AFR, km/h/mph…) seleccionables a nivel global, por dimensión y
   por canal.
7. **Cualquier CSV**: el formato Haltech es el primer caso, no el único. Un CSV
   arbitrario se importa y queda analizable con los mismos perfiles y detectores.
8. **Base Python**: el lenguaje que domina el propietario, para que el código sea
   mantenible y revisable por quien lo posee.

## Base tecnológica

**Python 3.12+** con todo el trabajo por muestra delegado a **Polars** y **NumPy**
(motores compilados), interfaz web con **renderizador WebGL2** propio y contenedor
**pywebview** empaquetado como carpeta portable. La regla que sostiene el
rendimiento es *cero bucles por muestra en Python* (ADR-009); los costes y
contrapartidas de elegir Python están detallados sin adornos en
[`docs/03-arquitectura.md`](docs/03-arquitectura.md) §3.11.

## Índice de documentación

| Documento | Contenido |
|---|---|
| [`docs/01-formato-log.md`](docs/01-formato-log.md) | Especificación del formato de log obtenida por ingeniería inversa: cabecera, tipos, factores de escala, muestreo disperso multi-tasa, trampas detectadas. |
| [`docs/02-alcance-y-plan.md`](docs/02-alcance-y-plan.md) | Objetivos, KPIs, alcance funcional por épicas, fases, hitos, riesgos, QA. |
| [`docs/03-arquitectura.md`](docs/03-arquitectura.md) | Decisiones de arquitectura (ADR-001…009), stack Python, pirámide de decimación, presupuestos de rendimiento, empaquetado y vía móvil. |
| [`docs/04-perfiles-motorsport.md`](docs/04-perfiles-motorsport.md) | Perfiles de análisis, detectores de eventos, topes de alerta, canales matemáticos, informes. |
| [`docs/05-backlog-y-asignacion-modelos.md`](docs/05-backlog-y-asignacion-modelos.md) | Backlog completo tarea a tarea con **asignación de modelo de IA**, esfuerzo, dependencias y puertas de revisión. |
| [`docs/06-sistema-de-unidades.md`](docs/06-sistema-de-unidades.md) | **Unidades intercambiables**: dimensiones canónicas, conversiones afines / recíprocas / parametrizadas, semántica de punto e intervalo, presión absoluta o relativa, presets. |
| [`docs/07-formatos-y-csv-generico.md`](docs/07-formatos-y-csv-generico.md) | **Escalabilidad a cualquier CSV**: capa de formatos de dos niveles, autodetección, roles semánticos, asistente y perfiles de importación. |
| [`docs/08-ejecucion-y-reanudacion.md`](docs/08-ejecucion-y-reanudacion.md) | **Protocolo de ejecución**: bucle de orquestación, asignación de agentes, puertas de revisión y cómo reanudar en una sesión nueva cuando se agota el límite. |

## Plan en una tabla

| Fase | Semanas | Contenido |
|---|---|---|
| F0 | 1–2 | Cimientos, *spike* de rendimiento, catálogos de unidades y roles, corpus |
| F1 | 3–9 | Núcleo de datos, sistema de unidades, visor de un log |
| FG | 10–12 | Formatos declarativos e importación de CSV genérico |
| F2 | 13–15 | Multi-log paralelo y concatenado |
| F3 | 16–20 | Perfiles, detectores y alertas de motorsport |
| F4 | 21–22 | Análisis tabular RPM×MAP, tablas de corrección e informes |
| F5 | 23–25 | Endurecimiento, empaquetado portable y v1.0 |

**136 tareas · 669 puntos · 25 semanas a v1.0.**
Reparto: Opus 5 58 % · Sonnet 5 37 % · Haiku 4.5 5 %, con 47 tareas bajo revisión
humana obligatoria.

## Estado

Progreso vivo en **[`state/PROGRESO.md`](state/PROGRESO.md)** (generado; la fuente
es `state/tareas.json`).

- [x] Análisis de logs de muestra
- [x] Alcance y plan de proyecto (rev. 2: base Python, unidades intercambiables,
      CSV genérico)
- [ ] **Fase F0 — Cimientos** (en ejecución)

### Reanudar el trabajo

El estado vive en el repositorio, así que cualquier sesión nueva puede continuar.
Pegar esto:

```
Retoma la ejecución del plan de DataLogViewer en la rama
claude/log-visualization-app-plan-5lhr8x.

Lee docs/08-ejecucion-y-reanudacion.md y sigue el bucle de la sección 8.4.
Empieza ejecutando `python tools/estado.py next`.
```

## Datos de muestra analizados

| Fichero | Canales | Filas | Duración | Tamaño | Tipo |
|---|---|---|---|---|---|
| `AutoLog_20260729_1830.csv` | 475 | 2 636 | 245,1 s | 4,47 MB | Log de PC (denso, tasa variable) |
| `20260729_1859_Log2768.csv` | 25 | 449 | 14,11 s | 32,6 kB | Log interno de ECU (disperso, 3 tasas) |
| `20260729_1859_Log2769.csv` | 25 | 213 | 6,75 s | 16,7 kB | Log interno de ECU (disperso, 3 tasas) |

Los tres están en [`samples/real/`](samples/real/); el corpus sintético y el de
casos corruptos se genera en la fase F0 (ver [`samples/README.md`](samples/README.md)).
