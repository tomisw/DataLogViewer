# DataLogViewer

Visor y analizador de logs de ECU orientado a **ECU tuning** y **motorsport**.

Este repositorio contiene, por ahora, el **alcance y plan de proyecto**. Toda la
documentación está derivada del análisis de tres logs reales (Haltech NSP,
`DataLogVersion 1.1`) aportados como muestra, no de suposiciones.

## Prioridades del producto

1. **Multi-log**: visualización de varios logs en **paralelo** (superpuestos) y
   **concatenada** (como una sola sesión continua).
2. **Rendimiento**: logs de horas y cientos de canales sin degradar el pan/zoom.
3. **Portabilidad**: ejecutable único sin instalación; mismo núcleo reutilizable
   en navegador y, más adelante, en móvil.
4. **Facilidad de uso**: perfiles de análisis preconfigurados en lugar de
   construir cada gráfico a mano.
5. **Funcionalidad motorsport**: detección de picos, topes de alerta, análisis de
   knock, control de boost, tablas de corrección λ, segmentación de tiradas…

## Índice de documentación

| Documento | Contenido |
|---|---|
| [`docs/01-formato-log.md`](docs/01-formato-log.md) | Especificación del formato de log obtenida por ingeniería inversa: cabecera, tipos, factores de escala, muestreo disperso multi-tasa, trampas detectadas. |
| [`docs/02-alcance-y-plan.md`](docs/02-alcance-y-plan.md) | Objetivos, KPIs, alcance funcional por épicas, fases, hitos, riesgos, QA. |
| [`docs/03-arquitectura.md`](docs/03-arquitectura.md) | Decisiones de arquitectura (ADR), stack, presupuestos de rendimiento, empaquetado y portabilidad. |
| [`docs/04-perfiles-motorsport.md`](docs/04-perfiles-motorsport.md) | Perfiles de análisis, detectores de eventos, topes de alerta, canales matemáticos, informes. |
| [`docs/05-backlog-y-asignacion-modelos.md`](docs/05-backlog-y-asignacion-modelos.md) | Backlog completo tarea a tarea con **asignación de modelo de IA**, esfuerzo, dependencias y puertas de revisión. |

## Estado

- [x] Análisis de logs de muestra
- [x] Alcance y plan de proyecto
- [ ] Fase 0 — Cimientos (pendiente de aprobación del plan)

## Datos de muestra analizados

| Fichero | Canales | Filas | Duración | Tamaño | Tipo |
|---|---|---|---|---|---|
| `AutoLog_20260729_1830.csv` | 475 | 2 636 | 245,1 s | 4,47 MB | Log de PC (denso, tasa variable) |
| `20260729_1859_Log2768.csv` | 25 | 449 | 14,11 s | 32,6 kB | Log interno de ECU (disperso, 3 tasas) |
| `20260729_1859_Log2769.csv` | 25 | 213 | 6,75 s | 16,7 kB | Log interno de ECU (disperso, 3 tasas) |
