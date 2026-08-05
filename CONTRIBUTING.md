# Guía de contribución a DataLogViewer

Bienvenido al proyecto DataLogViewer. Esta guía explica las convenciones de código, el proceso de verificación y las reglas arquitectónicas no negociables que hacen funcionar el proyecto.

## 1. Estructura del repositorio

| Directorio | Contenido |
|---|---|
| **dlv-core** | Biblioteca pura en Python: parseo, almacén columnar, pirámide de decimación, detectores. Sin dependencias de FastAPI ni acceso directo al sistema de ficheros. |
| **dlv-api** | Capa de comandos HTTP (FastAPI + uvicorn) que expone `dlv-core` al frontend. |
| **dlv-ui** | Interfaz web (TypeScript + Vite) con renderizador WebGL2. Independiente, gestionado con `npm`. |
| **dlv-app** | Contenedor `pywebview` + PyInstaller para empaquetado portable en ZIP. |
| **data/** | Catálogos de datos versionados: `units.toml` (dimensiones y conversiones), `roles.toml` (roles semánticos), `enums.toml` (diccionarios de códigos). |
| **docs/** | Especificación: decisiones arquitectónicas (ADRs), sistema de unidades, formatos, plan ejecutivo. |
| **samples/** | Logs de ejemplo para desarrollo y validación. |
| **state/** | Libro de estado del proyecto: `tareas.json` y `PROGRESO.md` (generado). |
| **tests/** | Suite de pruebas de nivel de proyecto que validan los catálogos de `data/` y las herramientas. |
| **tools/** | Herramientas de soporte: `estado.py` (orquestación), `banco.py` (puertas de rendimiento), `pytest_minimo.py` (ejecución sin pytest instalado). |

## 2. Puesta en marcha

Instala el entorno de desarrollo:

```bash
uv sync --all-packages
```

Esto instala `dlv-core`, `dlv-api` y `dlv-app` como paquetes editables en un único entorno virtual, resolviendo las dependencias cruzadas.

`dlv-ui` es independiente; en desarrollo se ejecuta con:

```bash
cd dlv-ui
npm install
npm run dev
```

### Nota sobre entornos sin red

En un contenedor de desarrollo sin acceso a PyPI, los binarios `ruff`, `mypy` y `pytest` pueden no estar disponibles tras `uv sync`. En ese caso:

- `tools/verificar.sh` ya lo gestiona: si no encuentra `pytest`, cae en `tools/pytest_minimo.py` —un `pytest` de sustitución que solo usa biblioteca estándar— y lo marca en el resumen. Recoge los mismos ficheros de prueba que `pytest`, pero un verde con sustituto no equivale a un verde con `pytest`, y por eso se avisa.
- `ruff` y `mypy` no tienen sustituto: si faltan, la comprobación cuenta como fallo. Es deliberado.
- **PyPI está bloqueado en el contenedor remoto** y no es transitorio: `pypi.org` está en `no_proxy` y devuelve 403 en 0,06 s. `polars`, `numpy` y `fastapi` no se pueden instalar allí; lo que dependa de ellos se marca `block` con el motivo. En local no ocurre: ver `docs/09-instrucciones-para-modelos-locales.md` §9.2.

## 3. Verificación antes de proponer un cambio

Una sola orden, sobre todo el repositorio y no solo sobre lo que has tocado:

```bash
bash tools/verificar.sh        # en Windows sin Git Bash: python tools/verificar.py
```

Ejecuta las seis comprobaciones —`ruff check`, `ruff format --check`,
`mypy --strict`, `pytest`, ADR-009 y presupuestos—, las resume al final y devuelve
código de salida distinto de cero si algo está en rojo.

**No ejecutes las herramientas a mano en su lugar.** No es una preferencia de
estilo: `ruff check` imprime «No fixes available…» *después* de «Found N errors»,
así que mirar el final de su salida engaña, y ya dejó pasar dos commits con el
lint en rojo. El guion usa códigos de salida, que no admiten interpretación.

Si no encuentra una herramienta pero hay `uv`, la ejecuta con `uv run` y lo dice
en el resumen. Una herramienta ausente cuenta como **fallo**, no como
comprobación omitida: no haber podido mirar no es estar en verde.

**Todo tiene que estar en verde antes de hacer commit.**

## 4. ADR-009: Cero bucles por muestra en Python

Esta es la regla más importante del proyecto. Sin ella, un proyecto Python con 73 millones de muestras se degrada en semanas.

### La regla

**Ninguna ruta que se ejecute una vez por muestra puede estar escrita en Python interpretado.**

Esto significa: todo cálculo sobre series es una operación de NumPy o Polars sobre el array completo. Python solo orquesta el trabajo; el trabajo real lo hacen bibliotecas compiladas (Rust, C) que liberan el GIL.

### Qué está prohibido en `dlv-core`

- `iterrows()` — bucles sobre filas
- `itertuples()` — bucles sobre tuplas de filas
- `iter_rows()` — iteración de Polars sobre filas
- `applymap()` — aplicar función elemento a elemento
- `apply(lambda)` — aplicar función a columnas
- `for` sobre muestras o puntos de datos

### Qué se hace en su lugar

**Operaciones vectorizadas de NumPy o Polars sobre el array completo:**

```python
# ❌ Prohibido
for i in range(len(data)):
    result[i] = transform(data[i])

# ✅ Correcto
result = np.vectorize(transform)(data)  # o mejor aún, vectorizar el cálculo
```

**Numba `@njit` solo cuando el banco demuestra que hace falta:**

Para máquinas de estado con histéresis, decimación por moda con longitud de racha, o autómatas que no se pueden vectorizar, usa Numba:

```python
from numba import njit


@njit(cache=True)
def state_machine(samples: np.ndarray) -> np.ndarray:
    # ...
    return output
```

Numba añade ~50 MB al paquete y latencia de compilación en el primer uso (mitigada con `cache=True`). Solo lo añades si `python tools/banco.py adr009` lo exige.

### Cómo se verifica

Se comprueba automáticamente con:

```bash
python tools/banco.py adr009
```

Este comando analiza el AST de `dlv-core` buscando patrones de bucles por muestra. Si encuentra alguno:

```
❌ INCUMPLE: bucles_por_muestra: 2.00 ocurrencias
```

**Un bucle por muestra es rechazo automático en revisión, no una sugerencia de mejora.**

## 5. ADR-002: Qué puede importar qué

La arquitectura está en capas. La regla dura es:

**`dlv-core` no importa `dlv-api`, `dlv-ui` ni `dlv-app`.**

Además:

**`dlv-core` no accede al sistema de ficheros por su cuenta.**

`dlv-core` es una biblioteca pura. Recibe datos ya cargados en memoria y retorna resultados. Todo acceso a ficheros, caché y persistencia lo maneja `dlv-api` o superior.

Hay una prueba automática por AST que verifica esto. Se ejecuta como parte de la suite normal.

## 6. Convenciones de código

### Lenguaje base

- **Python 3.12+** (ver `pyproject.toml`: `python_version = "3.12"`)
- **Tipado estricto** — `mypy --strict` sin excepciones
- Todo el código y los comentarios van **en español**, salvo los identificadores de dominio del formato de log, que se dejan tal cual (p. ej. `engine_speed`, `lambda_target`)

### Lint y formato

- **Herramienta**: `ruff` (>=0.6)
  - Lint: select E, F, W, I, UP, B, C4, SIM, RUF
  - Formato: comillas dobles (`quote-style = "double"`)
- **Longitud de línea**: 100 caracteres (ver `pyproject.toml`: `line-length = 100`)
- **Modo estricto de mypy**: `strict = true` (ver `pyproject.toml`)

Ejecuta antes de hacer commit:

```bash
ruff format .
ruff check .
mypy dlv-core dlv-api
```

## 7. Catálogos de datos, no código

Los ficheros `data/units.toml`, `data/roles.toml`, `data/enums.toml` y `data/formats/*.toml` son **datos versionados, no código**:

- Ampliarlos **no requiere recompilar** ni saber programar.
- Cualquier cambio en ellos es **puerta G1** (revisión humana obligatoria) porque un factor de escala mal puesto llega a una decisión de tuning.

### Ejemplos

- Agregar una unidad: edita `data/units.toml` con la dimensión, símbolo, conversión a canónica y decimales.
- Agregar un rol: edita `data/roles.toml` con el rol semántico, dimensión esperada, rango plausible y sinónimos.
- Agregar un diccionario de códigos: edita `data/enums.toml` con los valores hexadecimales y sus significados legibles.

Todos estos cambios pasan por revisión humana antes de fusionarse.

## 8. Puertas de revisión

| Puerta | Qué exige | Cuándo se usa |
|---|---|---|
| **G1 — Revisión humana obligatoria** | Una persona lee el diff completo antes de fusionar. | Parser, catálogos (`units.toml`, `roles.toml`, `enums.toml`), conversiones, detectores críticos, asignación de roles, importador genérico. Cualquier cambio que toque un factor de escala, una conversión de unidad o un umbral de detector. |
| **G2 — Revisión por Opus 5 + humano en resumen** | Opus 5 revisa el diff y emite hallazgos; el humano lee el resumen. | Almacén columnar, pirámide, motor de tiempo, renderizador, capa API. |
| **G3 — Pruebas verdes + revisión ligera** | CI en verde y lectura rápida del diff. | Interfaz, perfiles, exportadores, documentación. |
| **G4 — Pruebas verdes** | Solo se verifica que CI pase. | *Fixtures*, lint, changelog, i18n. |

## 9. Cómo se lleva el estado del proyecto

El estado se mantiene en dos ficheros:

- **`state/tareas.json`**: descripción JSON de cada tarea con su estado, modelo asignado, dependencias y notas.
- **`state/PROGRESO.md`**: resumen markdown, **generado automáticamente** (no se edita a mano).

### Órdenes útiles

```bash
python tools/estado.py next                    # qué toca ahora
python tools/estado.py show F1-13              # detalle de una tarea
python tools/estado.py start F0-05 --agente sonnet
python tools/estado.py done F0-05 --nota "descripción de qué se hizo"
python tools/estado.py aprobar F0-08           # aprobar una tarea en revisión humana
python tools/estado.py render                  # regenerar PROGRESO.md (automático)
```

**Nunca edites `state/PROGRESO.md` a mano.** Úsalo para leer el estado, pero cualquier cambio pasa por `tools/estado.py`.

### Workflow de orquestación

Cuando se retoma el proyecto en una sesión nueva:

```bash
git pull origin claude/log-visualization-app-plan-5lhr8x
python tools/estado.py next
# ... ejecutar la tarea ...
git add -A && git commit -m "<ID> — <título>"
python tools/estado.py done <ID> --nota "<qué quedó hecho>"
git add -A && git commit --amend --no-edit  # incluir el estado
git push -u origin claude/log-visualization-app-plan-5lhr8x
```

El commit de la tarea y su registro de estado son el mismo commit, así que el historial de git y `tareas.json` nunca divergen.

## Referencias

- **Arquitectura**: [docs/03-arquitectura.md](docs/03-arquitectura.md)
- **Sistema de unidades**: [docs/06-sistema-de-unidades.md](docs/06-sistema-de-unidades.md)
- **Formatos y CSV genérico**: [docs/07-formatos-y-csv-generico.md](docs/07-formatos-y-csv-generico.md)
- **Backlog y asignación**: [docs/05-backlog-y-asignacion-modelos.md](docs/05-backlog-y-asignacion-modelos.md)
- **Ejecución y reanudación**: [docs/08-ejecucion-y-reanudacion.md](docs/08-ejecucion-y-reanudacion.md)

En particular, lee **[docs/03-arquitectura.md §3.2](docs/03-arquitectura.md)** para entender las decisiones de arquitectura (ADR-001 a ADR-009).
