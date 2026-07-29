# 03 — Arquitectura

> **Revisión 2.** Esta versión sustituye la arquitectura basada en Rust/Tauri de
> la revisión 1 por una **basada en Python**, por decisión del responsable del
> proyecto: es el lenguaje que domina y por tanto el que puede mantener y revisar.
> La mantenibilidad por el dueño del código es un requisito de primer orden, no
> una preferencia estética. §3.11 documenta qué se paga por el cambio.

## 3.1 Fuerzas que determinan el diseño

Cinco requisitos que tiran en direcciones distintas:

- **Python como base** — el propietario debe poder leer y modificar el código.
- **Rendimiento con 73 M muestras** — empuja hacia código compilado.
- **Portable, sin instalación** — empuja hacia un paquete autocontenido.
- **Móvil en el futuro** — descarta las interfaces de escritorio nativas.
- **Facilidad de uso** — exige una interfaz rica.

La resolución: **Python es el lenguaje de la lógica, no el de los bucles.** Todo
el trabajo por muestra se delega a bibliotecas compiladas (Polars, NumPy) que
Python solo orquesta. La interfaz es web, lo que mantiene abierta la vía móvil y
de navegador, y se empaqueta en un contenedor local.

Esto no es un compromiso: es cómo se construyen las aplicaciones científicas de
datos en Python. El código que el propietario tiene que leer y mantener es Python
legible; el que mueve 73 millones de muestras es Rust y C compilados por otros y
probados por millones de usuarios.

## 3.2 Decisiones de arquitectura

### ADR-001 — Python 3.12+ como lenguaje base, con el motor en bibliotecas compiladas

| Componente | Biblioteca | Por qué |
|---|---|---|
| Parseo de CSV | **Polars** | motor Rust multihilo, libera el GIL, `separator`/`decimal_comma`/`null_values` parametrizables — cubre el camino nativo y el genérico |
| Almacén columnar | **Polars + NumPy** | vistas sin copia entre ambos; `to_numpy(zero_copy_only=True)` |
| Decimación, estadísticas, detectores | **NumPy** | `reshape` + `min/max(axis=1)` vectorizado |
| Núcleos no vectorizables | **Numba** (`njit`, `cache=True`) | máquinas de estado con histéresis, decimación por moda con longitud de racha |
| Caché en disco | **Polars** (`write_parquet`, `write_ipc`) | sin necesidad de PyArrow, lo que ahorra ~100 MB en el paquete |

Se evita PyArrow como dependencia directa: Polars escribe y lee Parquet y Arrow
IPC por sí mismo, y quitarlo es la mayor reducción de tamaño disponible.

Coste aceptado: se depende de que las operaciones existan vectorizadas. La
mitigación es ADR-009.

### ADR-002 — Contenedor: interfaz web en `pywebview`, no Qt

Descartado PySide6 + pyqtgraph, que habría sido más cómodo de escribir en Python
puro, porque cierra la vía de navegador y móvil que es prioridad declarada.

| Opción | Portable | Móvil | Navegador | Python puro | Veredicto |
|---|---|---|---|---|---|
| **pywebview + frontend web** | sí (carpeta zip) | **sí** | **sí** | no (UI en TS) | **Elegida** |
| PySide6 + pyqtgraph | sí | no | no | **sí** | descartada: cierra móvil y navegador |
| Dear PyGui | sí | no | no | sí | descartada: layout complejo limitado |
| Streamlit / Dash / Plotly | requiere servidor | sí | sí | sí | descartada: inviable con estos volúmenes |
| Electron / Tauri | sí | sí | sí | no | descartada: no es base Python |

`pywebview` usa el motor web del sistema (WebView2 en Windows, WebKitGTK en
Linux, WKWebView en macOS), igual que Tauri, así que el peso del paquete lo pone
Python, no el navegador.

Empaquetado con **PyInstaller en modo `onedir`**, distribuido como ZIP.
Deliberadamente **no** `onefile`: `onefile` se descomprime en un directorio
temporal en cada arranque, lo que añade segundos y escribe fuera de la carpeta,
rompiendo el modo portable. Un ZIP que se descomprime una vez y se ejecuta es
igual de portable y arranca mucho antes.

### ADR-003 — Almacén columnar con tipo de dato por canal

La revisión 1 asumía enteros crudos, algo válido solo para el formato Haltech. Con
CSV genérico hay decimales reales, texto y booleanos, así que cada canal declara
su representación:

```python
class Storage(Enum):
    INT32_SCALED = auto()   # entero crudo + (a, b) a canónica  — camino nativo
    FLOAT32      = auto()   # decimal de origen, precisión suficiente
    FLOAT64      = auto()   # decimal que necesita precisión (tiempo, GPS)
    ENUM_U16     = auto()   # estado con diccionario de códigos
    BITS_U32     = auto()   # máscara de bits
```

```python
@dataclass(slots=True)
class ChannelSeries:
    key:      ChannelKey        # (formato, id_nativo) | rol | nombre normalizado
    role:     str | None
    t:        np.ndarray        # uint32, ms desde t0 del segmento (compartido por grupo)
    v:        np.ndarray        # según Storage
    storage:  Storage
    to_canon: Affine            # (a, b) hacia la unidad canónica de la dimensión
    dimension: str | None       # None => se muestra en crudo, sin unidad
```

`INT32_SCALED` se conserva para el camino nativo porque es exacto, compacto y
permite detectar los valores centinela de desbordamiento
(`01-formato-log.md` §1.13). Un `float32` los habría redondeado y convertido en
datos de aspecto legítimo.

`t` se comparte por referencia entre canales del mismo grupo de muestreo: en las
muestras reales eso es el 100 % de los casos (un grupo en el AutoLog, tres en los
logs internos), así que el coste del eje propio por canal es nominal.

### ADR-004 — Valor canónico, conversión de unidades solo en presentación

Detallado en `06-sistema-de-unidades.md`. Resumen de la consecuencia
arquitectónica: **lo persistido está en canónica** (caché, umbrales, perfiles,
mallas, anotaciones) y la conversión a la unidad elegida se aplica **solo a los
cubos visibles**, unos miles de valores por panel y fotograma. Cambiar de °C a °F
es un repintado, no una recarga.

### ADR-005 — Caché en Parquet, escrita por Polars

Tras el primer parseo se escribe un `.dlvcache` (Parquet + un JSON de metadatos:
canales, roles, dimensiones, grupos de muestreo, pirámide). Invalidación por
`(ruta, tamaño, mtime, versión del parser, versión del descriptor de formato)`.
Presupuesto: segunda apertura < 700 ms frente a < 4 s de la primera.

La pirámide de decimación **se persiste** en la caché. Recalcularla cuesta más que
leerla.

### ADR-006 — Renderizador WebGL2 propio en TypeScript

Sin cambios respecto a la revisión 1, porque esta pieza es independiente del
lenguaje del backend. Ninguna biblioteca de gráficos de propósito general
(Chart.js, ECharts, Plotly, Recharts) sostiene 5 M puntos por serie a 60 fps.

Se dibuja desde la pirámide con WebGL2; los adornos estáticos (ejes, rejilla,
leyenda, etiquetas) van en SVG/DOM, donde no hay volumen.

Consecuencia para las revisiones: **es la única parte del código que el
propietario no puede revisar con comodidad**. Se compensa con puerta G2 (revisión
por Opus 5), pruebas de regresión visual obligatorias y una superficie de API
deliberadamente pequeña: el renderizador recibe cubos y una escala, y no sabe nada
de logs, unidades ni perfiles.

### ADR-007 — API de comandos local con carga binaria

El frontend habla con el núcleo por **HTTP sobre `127.0.0.1`** (FastAPI +
uvicorn), con puerto efímero y un token de sesión generado al arrancar.

Regla dura: **las series nunca viajan en JSON.** Los cubos visibles se envían como
**Arrow IPC** o como búfer de tipado fijo, que en el frontend se lee como
`TypedArray` sin parseo. JSON de 4 000 flotantes por panel y fotograma haría
inalcanzable cualquier presupuesto de latencia. JSON queda para los metadatos
(canales, perfiles, incidencias), donde el volumen es de kilobytes.

Corolario que hace viable el presupuesto de cursor con Python detrás: **el
frontend cachea los cubos visibles**, así que mover el cursor es una búsqueda
local en un `TypedArray` sin ida y vuelta al backend. Solo el pan/zoom que sale
del rango cacheado pide datos nuevos, y ese tiene un presupuesto distinto y más
holgado (§3.7).

Ventaja lateral: esta frontera es exactamente la que se necesita para el móvil de
la fase 6 y para probar el núcleo sin interfaz.

### ADR-008 — Capa de formatos en dos niveles y roles semánticos

Detallado en `07-formatos-y-csv-generico.md`. Consecuencia arquitectónica: la
identidad de canal deja de ser el `ID` nativo y pasa a ser en capas
(rol → `(formato, ID)` → nombre normalizado → manual), y los perfiles y
detectores se definen **por rol**. Los descriptores de formato, el catálogo de
roles y los sinónimos son **datos versionados** (TOML), no código.

### ADR-009 — Disciplina de rendimiento: cero bucles por muestra en Python

La regla que decide si esta arquitectura funciona:

> Ninguna ruta que se ejecute una vez por muestra puede estar escrita en Python
> interpretado.

Se aplica así:

- Todo cálculo sobre series es una operación de NumPy o Polars sobre el array
  completo. `for` sobre muestras, `.apply()`, `.iterrows()` y `map()` por elemento
  están prohibidos en `dlv-core`.
- Lo que no se puede vectorizar (histéresis de detectores, decimación por moda con
  longitud de racha, autómatas de estado) se implementa en **Numba** `@njit`, no
  en Python puro.
- La **revisión** de cualquier función nueva en `dlv-core` incluye la pregunta
  «¿cuántas veces se ejecuta esto por muestra?», y el **banco de rendimiento en
  CI** la responde de forma objetiva: si un presupuesto se rompe, la compilación
  falla.
- Numba solo entra **cuando el banco demuestra que hace falta**: añade ~50 MB al
  paquete y latencia de compilación en el primer uso (mitigada con `cache=True`).

Sin esta disciplina explícita, un proyecto Python con este volumen de datos se
degrada en semanas. Con ella, el rendimiento es indistinguible de un núcleo
nativo, porque el trabajo lo hace código nativo.

## 3.3 Vista de componentes

```
┌───────────────────────────────────────────────────────────────┐
│  dlv-ui  (TypeScript)                                         │
│  ┌────────────┬─────────────┬──────────────┬───────────────┐  │
│  │ Espacio de │  Selector   │  Perfiles y  │  Panel de     │  │
│  │  trabajo   │  de canales │  detectores  │  incidencias  │  │
│  ├────────────┴─────────────┴──────────────┴───────────────┤  │
│  │  Asistente de importación (3 pasos)                     │  │
│  ├─────────────────────────────────────────────────────────┤  │
│  │  Lienzo WebGL2 · ejes/leyenda SVG · caché de cubos      │  │
│  │  paneles apilados · carriles de estado · cursores        │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────┬────────────────────────────────────┘
              HTTP 127.0.0.1 · metadatos JSON · series Arrow IPC
┌──────────────────────────▼────────────────────────────────────┐
│  dlv-api  (FastAPI + uvicorn)   capa de comandos              │
├───────────────────────────────────────────────────────────────┤
│  dlv-core  (Python 3.12+)                                     │
│  ┌───────────┬────────────┬─────────────┬─────────────────┐   │
│  │ Sondeo +  │ Almacén    │ Pirámide de │ Motor de tiempo │   │
│  │ formatos  │ columnar   │ decimación  │ multi-log       │   │
│  │ (2 niv.)  │ (NumPy)    │ (NumPy)     │                 │   │
│  ├───────────┼────────────┼─────────────┼─────────────────┤   │
│  │ Unidades  │ Roles      │ Detectores  │ Canales matem.  │   │
│  │ canónicas │ semánticos │ (NumPy/     │ (expresiones)   │   │
│  │           │            │  Numba)     │                 │   │
│  ├───────────┼────────────┼─────────────┼─────────────────┤   │
│  │ Malla     │ Caché      │ Informes     │ Exportadores   │   │
│  │ RPM×MAP   │ Parquet    │              │                │   │
│  └───────────┴────────────┴─────────────┴─────────────────┘   │
│      motores compilados: Polars (Rust) · NumPy (C) · Numba    │
└───────────────────────────────────────────────────────────────┘
        ▲
        │  dlv-app: pywebview + PyInstaller onedir  → ZIP portable
```

Paquetes: `dlv-core` (biblioteca pura, sin FastAPI ni ficheros), `dlv-api`
(comandos), `dlv-ui` (frontend), `dlv-app` (contenedor y empaquetado).
`dlv-core` no importa nada de los otros tres: es la condición para poder probarlo
solo y reutilizarlo en cualquier contenedor futuro.

## 3.4 Ruta de ingesta

1. **Sondeo** — primeros 64 kB: firma de formato nativo o, si no hay, detección
   genérica (`07-formatos-y-csv-generico.md` §7.4).
2. **Cabecera / asistente** — nativo: gramática del descriptor. Genérico:
   detección propuesta y confirmada en el asistente, o perfil `.dlvimport`
   reaplicado por huella.
3. **Cuerpo** — `polars.read_csv` con los parámetros resueltos. Polars paraleliza
   internamente y libera el GIL; no hay bucle de Python.
4. **Consolidación** — grupos de muestreo por patrón de nulos por columna
   (vectorizado con `is_null()`), `t` compartido por grupo, conversión a canónica.
5. **Indexado** — mín/máx/percentiles, clasificación
   `activo/constante/vacío/fuera de rango`, centinelas, huecos.
6. **Roles** — asignación por sinónimos e informe de plausibilidad.
7. **Pirámide** — niveles de decimación (§3.5).
8. **Caché** — Parquet + metadatos JSON.
9. **Informe de importación** — avisos, sin bloquear.

Los pasos 5–8 son de fondo con progreso y cancelación: el primer gráfico se puede
dibujar tras el 4, que es lo que sostiene el presupuesto de < 4 s.

## 3.5 Pirámide de decimación

El problema: 5 M puntos por canal, ~1 800 píxeles de panel. Dibujar punto a punto
es 2 700 veces más trabajo del necesario y produce *aliasing* que **oculta los
picos**, que es justo lo que hay que ver.

Niveles con factor 4, cada cubo con `min, max, first, last`:

| Nivel | Factor | Puntos (de 5 M) |
|---|---|---|
| L0 | 1 | 5 000 000 |
| L1 | 4 | 1 250 000 |
| L2 | 16 | 312 500 |
| … | … | … |
| L9 | 262 144 | 19 |

Coste total ≈ 1/3 de la memoria del nivel base. En NumPy es una construcción de
tres líneas por nivel:

```python
n = (len(v) // 4) * 4
b = v[:n].reshape(-1, 4)
lo, hi = b.min(axis=1), b.max(axis=1)
first, last = b[:, 0], b[:, -1]
```

Vectorizado y sin bucles: procesa cientos de millones de muestras por segundo, y
es exactamente el tipo de operación que hace innecesario escribir Rust.

Al dibujar se elige el nivel cuyo número de cubos ≈ el ancho en píxeles y se traza
una columna vertical de `min` a `max` por píxel más la línea `first`→`last`.
**Es exacto en los extremos**: un pico de una sola muestra sigue visible al máximo
zoom-out. Un decimado por muestreo simple lo perdería, y un pico de knock perdido
es un motor roto.

Variantes por tipo de canal:

| Tipo | Agregación del cubo | Por qué |
|---|---|---|
| Continuo | `min, max, first, last` | preserva picos |
| Contador acumulado | **suma del delta** | un incremento aislado no se puede perder |
| Enum / estado | **moda + marca de transiciones** | evita parpadeo en los carriles |
| Máscara de bits | **OR de los bits** | un bit que se activó una vez sigue visible |

Las tres variantes no continuas necesitan longitud de racha y son los candidatos
naturales a Numba si NumPy no llega; la decisión la toma el banco de F0.

## 3.6 Motor de tiempo multi-log

Cada log cargado es un **segmento**:
`{ id, t0_absoluto: datetime | None, offset_usuario, fiabilidad_reloj, orden }`.

**Vista paralela**: eje X virtual; `x = t_local + offset_efectivo`, con
`offset_efectivo` según el modo:

| Modo | Cálculo del desfase |
|---|---|
| Reloj absoluto | de `t0_absoluto`; exige `fiabilidad_reloj = fiable` |
| Relativo | 0 para todos |
| Manual | arrastrado por el usuario |
| Por evento | posición del ancla (primer WOT, primer corte, launch) en cada segmento |
| Correlación | argmáx de la correlación cruzada del rol de referencia (`engine_speed`) |

La correlación cruzada se calcula sobre los niveles **L4–L6** de la pirámide con
`numpy.correlate` / FFT, y solo se refina en L0 alrededor del máximo encontrado:
dos órdenes de magnitud menos trabajo que sobre los datos crudos, y suficiente
precisión.

**Vista concatenada**: segmentos ordenados (por `Log Number` cuando el reloj no es
fiable) y colocados consecutivamente con hueco explícito. Los canales se unen por
la identidad en capas de ADR-008. Reglas duras:

- Nunca se dibuja una línea que cruce una frontera de segmento.
- Las fronteras se marcan siempre, no como opción.
- Las estadísticas y detectores respetan las fronteras: una derivada no cruza la
  unión, y un «tiempo por encima de umbral» no suma a través del hueco.
- Si un rol existe en un segmento y no en otro, hay hueco, no ceros.

**Eje X alternativo** (RPM, velocidad, distancia): se reindexa cada segmento por
el canal elegido, exigiendo monotonía por tramos, así que se aplica sobre
segmentos detectados (una tirada) y no sobre el log completo. Sin esto no se
pueden comparar dos tiradas de duración distinta, que es la comparación diaria de
un tuner.

## 3.7 Concurrencia y memoria

- **Parseo**: Polars paraleliza internamente y libera el GIL. No hay
  `multiprocessing`, que en un ejecutable de PyInstaller es una fuente conocida de
  problemas y duplicaría la memoria.
- **Tareas de fondo**: `asyncio` en uvicorn más un `ThreadPoolExecutor` para el
  trabajo que libera el GIL (Polars, NumPy, E/S). El GIL no es un cuello de
  botella porque el trabajo real no se ejecuta en el intérprete.
- **La interfaz no se bloquea nunca**: toda operación > 50 ms va a tarea de fondo
  con progreso y cancelación.
- **Frontera de datos**: el frontend recibe solo los cubos visibles y los cachea;
  el cursor se resuelve en local (ADR-007).
- **Presión de memoria**: L0 se puede liberar y releer de la caché Parquet bajo
  demanda; los niveles altos se mantienen siempre residentes.

## 3.8 Presupuestos revisados para la base Python

| Métrica | Rev. 1 (Rust) | **Rev. 2 (Python)** | Nota |
|---|---|---|---|
| Apertura de 66 MB / 475 canales hasta primer gráfico | < 3,0 s | **< 4,0 s** p95 | a validar con un *spike* de Polars en F0 |
| Parseo nativo | ≥ 40 MB/s por hilo | **≥ 100 MB/s agregado** | Polars multihilo |
| Parseo genérico numérico / con texto | — | **≥ 60 / ≥ 25 MB/s** | camino genérico |
| Segunda apertura (caché) | < 400 ms | **< 700 ms** | |
| Pan/zoom, 16 canales × 5 M puntos | ≥ 60 fps | **≥ 60 fps** | es el renderizador TS, no cambia |
| Latencia del cursor | < 16 ms | **< 16 ms** | local en el frontend, sin ida y vuelta |
| Pan/zoom que pide cubos nuevos | — | **< 120 ms** p95 | presupuesto nuevo de la frontera HTTP |
| Memoria residente con log de 66 MB | ≤ 3× CSV | **≤ 3,5× CSV** | sobrecoste del intérprete |
| Arranque en frío | < 1,5 s | **< 2,5 s** | Python + uvicorn + WebView |
| Tamaño del paquete | < 25 MB | **< 150 MB sin comprimir / < 60 MB en ZIP** | el coste más visible del cambio |
| 8 logs × 30 min en paralelo | sin degradación | **sin degradación** | |

Los tres presupuestos que empeoran de verdad son arranque en frío, tamaño y
apertura inicial. Los que el usuario nota en el uso continuo —fps, cursor,
navegación— **no cambian**, porque dependen del renderizador y de la pirámide, no
del lenguaje del backend.

## 3.9 Formatos de fichero de la aplicación

| Extensión | Contenido | Formato |
|---|---|---|
| `.dlvproj` | espacio de trabajo: logs, desfases, perfil activo, zoom, marcadores, emparejamientos manuales | JSON versionado |
| `.dlvprofile` | perfil de análisis: paneles, **roles**, unidades, umbrales, detectores | JSON versionado |
| `.dlvimport` | perfil de importación de CSV genérico con huella de cabecera | TOML versionado |
| `.dlvcache` | caché de parseo con pirámide | Parquet + JSON |
| `units.toml` | dimensiones, unidades, conversiones, presets, centinelas | TOML en el repositorio |
| `roles.toml` | catálogo de roles semánticos y sinónimos | TOML en el repositorio |
| `enums.toml` | diccionarios de códigos de estado y máscaras de bits | TOML en el repositorio |
| `formats/*.toml` | descriptores de formato nativo | TOML en el repositorio |

Los cinco últimos son **datos, no código**: ampliarlos no requiere recompilar ni
saber programar. Es la mitigación principal de los riesgos R1, R2 y R10.

## 3.10 Empaquetado y portabilidad

- **Windows**: carpeta PyInstaller `onedir` en ZIP. Depende de WebView2, presente
  por omisión en Windows 10/11 actualizado; se detecta y se guía la descarga si
  falta.
- **Linux**: `onedir` en `tar.gz`, y AppImage como alternativa.
- **macOS**: `.app` en `.dmg`, firmado y notarizado.
- **Modo portable**: con un `portable.txt` junto al ejecutable, la app no escribe
  nada fuera de su carpeta (ni configuración, ni caché, ni registro). Es el
  requisito de uso en pista desde un pendrive, y es la razón de rechazar
  `onefile`.
- **Web**: la interfaz ya es web; la versión navegador necesita un backend Python
  al que apuntar (local o en la red del equipo). Ver §3.11.
- Sin telemetría, sin comprobación de licencia, sin red obligatoria. El servidor
  local escucha solo en `127.0.0.1` con token de sesión.

## 3.11 Qué se paga por la base Python, y la vía móvil

Ser explícito aquí evita una decepción en la fase 6.

**Lo que cuesta:**

| Coste | Magnitud | Mitigación |
|---|---|---|
| Tamaño del paquete | 25 MB → ~150 MB | `onedir` en ZIP (~60 MB), sin PyArrow, `--exclude-module` agresivo |
| Arranque en frío | 1,5 s → 2,5 s | `onedir` (no `onefile`), importaciones diferidas, pantalla de arranque |
| Riesgo de rendimiento | vigilancia continua | ADR-009 más puertas de presupuesto en CI |
| Móvil autónomo | deja de ser directo | ver abajo |

**La vía móvil, con honestidad.** Tauri 2 habría dado una app móvil nativa
directa. Con Python las opciones son:

| Opción | Madurez | Qué permite |
|---|---|---|
| **A — teléfono como cliente del backend** | **madura, es la comprometida** | la interfaz web ya es responsive; el móvil apunta al backend Python del portátil en la red del taller o del box. Cubre el caso real: revisar el log en el móvil mientras el PC procesa |
| B — núcleo Python en el navegador con **Pyodide** | parcial | NumPy funciona en Pyodide; Polars en WASM aún no es sólido. Viable para logs pequeños (los internos de la ECU, de kilobytes) con un camino de parseo alternativo. Merece un *spike* en la fase 6, no un compromiso |
| C — empaquetar Python en móvil (BeeWare, Chaquopy) | inmadura para este conjunto de dependencias | app autónoma real; hoy no es apostable con Polars y Numba |

Por eso la fase 6 se compromete a la **opción A** y deja B como exploración. Y por
eso ADR-002 elige interfaz web pese al coste de escribir el frontend en
TypeScript: es lo que mantiene A y B posibles. Con PySide6 no habría ninguna de
las tres.

**Lo que no se pierde:** los fps, la latencia del cursor y la fluidez de
navegación son idénticos, porque los pone el renderizador WebGL y la pirámide.
Y se gana lo que motivó el cambio: el propietario puede leer, depurar y extender
el 75 % del código —todo `dlv-core` y `dlv-api`— sin aprender otro lenguaje.
