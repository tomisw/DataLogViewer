# Banco de rendimiento

> Generado por `tools/banco.py informe`. **No editar a mano.**
> Presupuestos: `docs/02-alcance-y-plan.md` §2.6. Historial completo en
> `state/banco/mediciones.json`.

`NO_MEDIBLE` significa que la funcionalidad que mide todavía no existe;
no falla la compilación. Solo `INCUMPLE` la falla.

| Presupuesto | Límite | Fase | Última medición | Estado |
|---|---|---|---|---|
| Apertura de log de 66 MB / 475 canales hasta el primer gráfico (p95) | `<= 4` s | F1 | — | sin medir |
| Parseo del camino nativo (enteros, sin comillas), agregado | `>= 100` MB/s | F1 | 44.87 MB/s *(línea base)* | · NO_MEDIBLE |
| Parseo genérico numérico, agregado | `>= 60` MB/s | FG | — | sin medir |
| Parseo genérico con comillas o texto, agregado | `>= 25` MB/s | FG | — | sin medir |
| Segunda apertura desde la caché Parquet | `<= 700` ms | F1 | — | sin medir |
| Pan/zoom con 16 canales x 5 M puntos | `>= 60` fps | F1 | — | sin medir |
| Cursor hasta tabla de valores actualizada | `<= 16` ms | F1 | — | sin medir |
| Pan/zoom que requiere cubos nuevos del backend (p95) | `<= 120` ms | F1 | — | sin medir |
| Cambio de unidad con 8 logs abiertos | `<= 100` ms | F1 | — | sin medir |
| Memoria residente con el log de 66 MB abierto | `<= 3.5` x CSV | F1 | — | sin medir |
| Arranque en frío hasta ventana interactiva | `<= 2.5` s | F5 | — | sin medir |
| Tamaño del paquete portable comprimido | `<= 60` MB | F5 | — | sin medir |
| Tamaño del paquete portable sin comprimir | `<= 150` MB | F5 | — | sin medir |
| Bucles por muestra en Python dentro de dlv-core (ADR-009) | `<= 0` ocurrencias | F1 | 0.00 ocurrencias | ✔ CUMPLE |

## Línea base sin dependencias

`stdlib.csv` sobre `samples/synth/autolog-1h.csv` (70.13 MB, 475 canales): **1.563 s** = 44.9 MB/s.

Para cumplir el presupuesto de parseo nativo, el motor real debe ser **2.23x más rápido** que la biblioteca estándar. Es la cifra que el *spike* de F0-01 tiene que batir.
