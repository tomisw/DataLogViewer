# DataLogViewer — instrucciones para modelos

Visor de logs de ECU (Haltech NSP y CSV genérico). Base Python: `dlv-core`
(biblioteca pura), `dlv-api` (FastAPI local), `dlv-ui` (TypeScript + WebGL2),
`dlv-app` (pywebview + PyInstaller).

Este fichero se carga solo, así que es corto a propósito. **Lo primero que hay que
leer es [`docs/09-instrucciones-para-modelos-locales.md`](docs/09-instrucciones-para-modelos-locales.md)**,
y para el protocolo de ejecución
[`docs/08-ejecucion-y-reanudacion.md`](docs/08-ejecucion-y-reanudacion.md).

## Antes de decir que algo está terminado

```bash
bash tools/verificar.sh          # en Windows: python tools/verificar.py
```

Seis comprobaciones (`ruff check`, `ruff format --check`, `mypy --strict`,
`pytest`, ADR-009, presupuestos) y código de salida distinto de cero si algo está
en rojo. **Úsalo en lugar de ejecutar las herramientas a mano**: `ruff check`
imprime «No fixes available…» *después* de «Found N errors», y mirar el final de
su salida ya dejó pasar dos commits con el lint en rojo.

Entorno: `uv sync --all-packages`. No `pip` ni `venv` a mano.

## Estado del trabajo

El estado vive en el repositorio, no en la conversación:

```bash
python tools/estado.py next       # qué toca ahora
python tools/estado.py show F1-04 # detalle y qué hay que revisar
```

`state/PROGRESO.md` se **genera**; no se edita a mano. Toda transición pasa por
`tools/estado.py`. Rama de trabajo: `claude/log-visualization-app-plan-5lhr8x`.

## Seis reglas que no se saltan

1. **ADR-009 — cero bucles por muestra en Python.** Polars o NumPy hacen el
   trabajo; si no se puede vectorizar, Numba, no un `for`. Son 73 M de muestras y
   4 s de presupuesto.
2. **`data/*.toml` son datos, no código.** No trasladar sus valores al código ni
   reformatear los ficheros: los comentarios son lo que hace revisable la puerta
   G1.
3. **Los umbrales son configurables.** `data/umbrales.toml` da valores por
   omisión, con precedencia canal > perfil > usuario > fichero. Un umbral cableado
   es una opinión disfrazada de física.
4. **La clase de conversión es obligatoria** (`PUNTO`/`INTERVALO`/`TASA`/
   `VARIANZA`, sin valor por omisión). Es lo que evita que un Δ de 10 K salga como
   −263,15 °C.
5. **`samples/real/` no se toca.** Son los tres logs del propietario y la
   evidencia de todo el formato.
6. **Una puerta G1 no la cierra un modelo.** Pasa a `revision_humana` con una nota
   que diga qué revisar, ordenada por consecuencia si el número está mal.

## Qué no hacer sin preguntar

Cambiar un presupuesto para que pase; rellenar un `confianza = "unknown"` con un
valor plausible; cambiar un umbral por omisión; añadir una dependencia; reescribir
la historia de la rama. El detalle y el motivo de cada uno, en `docs/09` §9.11.

## Especificación

| Documento | Contenido |
|---|---|
| `docs/01-formato-log.md` | formato Haltech, medido sobre los logs reales |
| `docs/02-alcance-y-plan.md` | objetivos, épicas, presupuestos §2.6, riesgos |
| `docs/03-arquitectura.md` | ADR-001…009, pirámide, motor de tiempo |
| `docs/04-perfiles-motorsport.md` | perfiles y los 18 detectores |
| `docs/05-backlog-y-asignacion-modelos.md` | las 155 tareas y su modelo |
| `docs/06-sistema-de-unidades.md` | canónica, clases, presión relativa |
| `docs/07-formatos-y-csv-generico.md` | CSV genérico y roles semánticos |
| `docs/08-ejecucion-y-reanudacion.md` | protocolo de ejecución |
| `docs/09-instrucciones-para-modelos-locales.md` | **ejecución en local** |
| `docs/10-guia-importar-csv-y-anadir-formato.md` | guía: importar un CSV cualquiera y añadir un formato nativo |

El código y los comentarios de este proyecto están en español.
