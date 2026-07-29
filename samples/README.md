# Corpus de logs de muestra

Este directorio es el corpus de pruebas del proyecto (tarea **F0-05** del
backlog). Está **vacío a propósito**: los logs de un vehículo son datos del
propietario y, una vez subidos, quedan en el historial de git de forma
permanente. La decisión de versionarlos es del dueño del repositorio.

## Ficheros esperados

Los tres logs analizados para redactar la especificación de
[`../docs/01-formato-log.md`](../docs/01-formato-log.md) son:

| Fichero | Canales | Filas | Duración | Tamaño | Papel en el corpus |
|---|---|---|---|---|---|
| `AutoLog_20260729_1830.csv` | 475 | 2 636 | 245,1 s | 4,47 MB | caso denso de tasa variable; base de la extrapolación de rendimiento |
| `20260729_1859_Log2768.csv` | 25 | 449 | 14,11 s | 32,6 kB | caso disperso multi-tasa; segmento 1 de concatenación |
| `20260729_1859_Log2769.csv` | 25 | 213 | 6,75 s | 16,7 kB | caso disperso multi-tasa; segmento 2 de concatenación |

Los dos últimos son consecutivos (`Log Number` 2768 y 2769) y comparten los 25
`ID` de canal, así que son el caso de prueba natural para la vista concatenada.

## Corpus a generar (F0-05, F0-06, F0-07)

1. `synth/autolog-1h.csv` — sintético de 1 hora y 475 canales derivado del real.
   Caso de rendimiento: ≈ 66 MB, ≈ 18,3 M muestras.
2. `synth/internal-x20/` — 20 logs internos consecutivos sintéticos. Caso de
   concatenación a escala.
3. `corrupt/` — los 11 casos de la lista de verificación del parser
   (`docs/01-formato-log.md` §1.13): cabecera truncada, fila corta,
   `DisplayMaxMin` ausente, BOM, CRLF, sin `\n` final, marcas no monótonas,
   cruce de medianoche, versión `1.2` desconocida, celdas con centinelas de
   desbordamiento, número de columnas incorrecto.
4. `truth/` — log con eventos de knock y λ pobre en carga **anotados**, para
   validar los detectores de la fase 3 (F3-08). Sin este fichero no se puede
   afirmar que los detectores funcionan.

## Si se decide versionar los logs reales

Son ficheros de texto muy compresibles y de tamaño moderado; git los maneja sin
problema. Para el sintético de 1 hora conviene **no** versionarlo y generarlo
con el guion de F0-05 en su lugar, o usar Git LFS.
