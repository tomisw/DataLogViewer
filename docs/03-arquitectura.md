# 03 — Arquitectura

## 3.1 Fuerzas que determinan el diseño

Las cuatro prioridades del cliente entran en conflicto directo y la arquitectura
existe para resolverlo:

- *Portable, sin instalación* empuja hacia web/navegador.
- *Rendimiento con 73 M muestras* empuja hacia código nativo.
- *Móvil en el futuro* descarta las soluciones de escritorio nativas puras.
- *Facilidad de uso* exige una UI rica, lo que favorece tecnologías web.

La resolución es **un núcleo en Rust compilado a dos objetivos (nativo y WASM)
con una única UI web sobre él**. El núcleo da el rendimiento, la UI web da la
riqueza y la portabilidad, y la doble compilación permite tres contenedores
—escritorio portable, navegador y móvil— sin duplicar lógica.

## 3.2 Decisiones de arquitectura

### ADR-001 — Contenedor de escritorio: Tauri 2

| Opción | Binario | Portable | Móvil | Rendimiento | Veredicto |
|---|---|---|---|---|---|
| **Tauri 2 + Rust** | ~10–20 MB | sí, un `.exe` | **sí (iOS/Android en Tauri 2)** | nativo | **Elegida** |
| Electron | 120–180 MB | con dificultad | no | JS, GC | descartada por tamaño y sin móvil |
| Qt/C++ o Python+Qt | variable | Python necesita empaquetado frágil | parcial | bueno | descartada por complejidad de empaquetado y UI |
| .NET/WPF o WinUI | medio | sí con AOT | no | bueno | descartada: solo Windows, sin móvil |
| Solo web (PWA) | 0 | máxima | sí | límite en ficheros grandes y sin acceso a carpetas | **complementaria**, no principal |

Tauri 2 usa el motor web del sistema (WebView2/WebKitGTK/WKWebView), de ahí el
binario pequeño, y soporta iOS y Android, que es exactamente el requisito de
«posibilidad de app móvil en el futuro».

Coste aceptado: hay diferencias entre motores web del sistema. Se mitiga con
matriz de pruebas en las tres plataformas desde M0 y evitando APIs de
navegador exóticas.

### ADR-002 — Núcleo compartido `dlv-core` en Rust

Un único *crate* con el parser, el almacén columnar, la pirámide de decimación,
los detectores y los canales matemáticos. Se compila a:

- **cdylib nativo** para el contenedor Tauri,
- **WASM** para la versión navegador (y para pruebas rápidas en CI),
- **biblioteca estática** para los objetivos móviles de la fase 6.

Consecuencia obligatoria: el núcleo **no accede al sistema de ficheros ni a la
red**. Recibe un `impl Read + Seek` o un búfer. Esa restricción es lo que hace
posible los tres objetivos.

### ADR-003 — Almacenamiento columnar de enteros crudos

Cada canal se guarda como `{ id, t: Vec<u32> (ms desde t0), v: Vec<i32> }`, más
metadatos de escala. Justificación en `01-formato-log.md` §1.12:

- Los datos ya vienen como enteros escalados: guardarlos así es **exacto** y no
  ocupa más que `f32`.
- La escala se aplica solo al mostrar → cambiar de λ a AFR, o de kPa a bar, es
  gratis y no rehace la carga.
- Permite comparación bit a bit entre logs y detectar centinelas de desbordamiento.
- Cada canal con su propio `t[]` resuelve el muestreo disperso multi-tasa sin
  huecos ni relleno.

Coste aceptado: el `t[]` por canal duplica memoria frente a un único eje
compartido. Se mitiga compartiendo por referencia el vector `t` entre canales del
mismo grupo de muestreo (los tres grupos de los logs internos, o el grupo único
del AutoLog), que es el caso real en el 100 % de las muestras.

### ADR-004 — Caché en Arrow/Parquet

Tras el primer parseo se escribe un fichero de caché junto al log (o en el
directorio de caché de la app en modo no portable). Presupuesto: segunda
apertura < 400 ms frente a < 3 s de la primera. La caché se invalida por
`(ruta, tamaño, mtime, versión del parser)`.

### ADR-005 — Renderizado WebGL propio, no biblioteca de gráficos

Ninguna biblioteca de gráficos de propósito general (Chart.js, ECharts, Recharts,
Plotly) sostiene 5 M puntos por serie a 60 fps: todas asumen órdenes de magnitud
menos datos y muchas crean nodos DOM o rutas SVG por punto.

Se implementa un renderizador propio en WebGL2 que dibuja desde la pirámide de
decimación. Es la pieza de mayor riesgo técnico y por eso se aborda en F1, no
al final.

Coste aceptado: hay que construir a mano ejes, rejilla, leyenda e interacción.
Se acota usando DOM/SVG para los adornos estáticos (ejes, etiquetas) y WebGL
solo para las series, que es donde está el volumen.

### ADR-006 — La UI habla con el núcleo por comandos serializables

Frontera explícita de mensajes tipados, no llamadas de función acopladas. El
mismo frontend funciona sobre el núcleo nativo (Tauri IPC), sobre WASM (llamada
directa) y, en el futuro, sobre un núcleo remoto. También hace la UI comprobable
sin núcleo real.

## 3.3 Vista de componentes

```
┌──────────────────────────────────────────────────────────────┐
│  UI (TypeScript)                                             │
│  ┌────────────┬─────────────┬──────────────┬──────────────┐  │
│  │ Espacio de │  Selector   │  Perfiles y  │  Panel de    │  │
│  │  trabajo   │  de canales │  detectores  │  incidencias │  │
│  └────────────┴─────────────┴──────────────┴──────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Lienzo WebGL2  · ejes/leyenda en SVG                  │  │
│  │  paneles apilados · carriles de estado · cursores      │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │  comandos tipados (ADR-006)
┌───────────────────────────▼──────────────────────────────────┐
│  dlv-core (Rust)  →  nativo · WASM · móvil                   │
│  ┌──────────┬────────────┬─────────────┬──────────────────┐  │
│  │ Parser   │ Almacén    │ Pirámide de │ Motor de tiempo  │  │
│  │ + unidad │ columnar   │ decimación  │ multi-log        │  │
│  ├──────────┼────────────┼─────────────┼──────────────────┤  │
│  │ Canales  │ Detectores │ Malla       │ Caché Arrow      │  │
│  │ matem.   │ de eventos │ RPM×MAP     │                  │  │
│  └──────────┴────────────┴─────────────┴──────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## 3.4 Ruta de ingesta

1. **Sondeo**: leer los primeros KB, validar `%DataLog%` y `DataLogVersion`,
   elegir implementación de formato.
2. **Cabecera**: parsear bloques `Channel` tolerando `DisplayMaxMin` ausente;
   construir el vector de canales en orden de columna.
3. **Cuerpo, en paralelo**: dividir el fichero en fragmentos por límite de línea
   y parsear con un hilo por fragmento. El CSV de enteros sin comillas es
   trivialmente paralelizable; ahí está el presupuesto de ≥ 40 MB/s por hilo.
4. **Consolidación**: unir fragmentos, detectar grupos de muestreo por patrón de
   presencia de celdas, compartir vectores `t` por grupo.
5. **Indexado**: por canal, mín/máx/percentiles, clasificación
   `activo/constante/vacío`, detección de centinelas y de huecos.
6. **Pirámide**: construir niveles de decimación (§3.5).
7. **Caché**: volcar a Arrow.
8. **Informe de importación**: avisos acumulados (filas saltadas, reloj no
   fiable, tipos de unidad desconocidos) mostrados al usuario **sin bloquear**.

Los pasos 5–7 son de fondo: el primer gráfico se puede dibujar tras el 4, lo que
sostiene el presupuesto de < 3 s.

## 3.5 Pirámide de decimación: el núcleo del rendimiento

El problema: 5 M puntos por canal, 1 800 píxeles de ancho de panel. Dibujar
punto a punto es 2 700× más trabajo del necesario y produce *aliasing* que
**oculta los picos**, precisamente lo que un tuner necesita ver.

Solución: por cada canal se precalculan niveles con factor 4:

| Nivel | Factor | Puntos (de 5 M) | Contenido por cubo |
|---|---|---|---|
| L0 | 1 | 5 000 000 | valor crudo |
| L1 | 4 | 1 250 000 | `min, max, first, last` |
| L2 | 16 | 312 500 | ídem |
| … | … | … | … |
| L9 | 262 144 | 19 | ídem |

Coste total de la pirámide: ≈ 1/3 de la memoria del nivel base (serie
geométrica de razón 1/4 con 4 valores por cubo).

Al dibujar se elige el nivel cuyo número de cubos ≈ el ancho en píxeles, y se
traza una columna vertical de `min` a `max` por píxel más la línea `first`→`last`.
Propiedad clave: **es exacto en los extremos**. Un pico de una sola muestra
sigue visible al máximo zoom-out. Un decimado por muestreo simple lo perdería, y
un pico de knock perdido es un motor roto.

Los canales enumerados no se deciman con min/max sino con **moda del cubo** y
marca de «cubo con transiciones», para que los carriles de estado no parpadeen.

## 3.6 Motor de tiempo multi-log

Modelo: cada log cargado es un **segmento** con `{ id, t0_absoluto: Option, offset_usuario, fiabilidad_reloj }`.

**Vista paralela**: se define un eje X virtual; cada segmento se proyecta con
`x = t_local + offset_efectivo`. `offset_efectivo` sale del modo de alineación:

| Modo | Cálculo del desfase |
|---|---|
| Reloj absoluto | de `t0_absoluto`; requiere `fiabilidad_reloj = fiable` |
| Relativo | 0 para todos |
| Manual | valor arrastrado por el usuario |
| Por evento | posición del evento ancla (primer WOT, primer corte) de cada segmento |
| Correlación | argmáx de la correlación cruzada del canal de referencia remuestreado |

La correlación cruzada se hace sobre el nivel L4–L6 de la pirámide, no sobre los
datos crudos: es dos órdenes de magnitud más rápido y suficientemente preciso,
con refinamiento en L0 solo alrededor del máximo encontrado.

**Vista concatenada**: los segmentos se ordenan (por `Log Number` cuando el
reloj no es fiable) y se colocan consecutivamente con un hueco explícito. Los
canales se unen por `ID`. Reglas duras:

- Nunca se dibuja una línea que cruce una frontera de segmento.
- Las fronteras se marcan visualmente siempre, no como opción.
- Las estadísticas y detectores respetan las fronteras: una derivada no cruza la
  unión, un «tiempo por encima de umbral» no suma a través del hueco.
- Si un `ID` existe en un segmento y no en otro, la serie tiene hueco, no ceros.

**Eje X alternativo (RPM, velocidad, distancia)**: se reindexa cada segmento por
el canal elegido. Requiere monotonía por tramos: se aplica solo sobre segmentos
detectados (una tirada), no sobre el log completo. Sin esto, comparar dos
tiradas de duración distinta es imposible, y es la comparación que hace un tuner
todos los días.

## 3.7 Concurrencia y memoria

- Parseo con un grupo de hilos dimensionado a los núcleos disponibles; en WASM,
  *web workers* con `SharedArrayBuffer` cuando esté disponible y hilo único como
  alternativa degradada.
- La UI nunca bloquea: toda operación > 50 ms va a tarea de fondo con progreso y
  cancelación.
- Los datos de serie viven en el núcleo. La UI recibe **solo los cubos visibles**
  del nivel elegido (unos miles de valores por panel y fotograma), lo que
  mantiene la frontera IPC barata incluso con 73 M muestras cargadas.
- Descarga de segmentos bajo presión de memoria: el nivel L0 se puede liberar y
  releer de la caché Arrow bajo demanda; los niveles altos se mantienen siempre.

## 3.8 Formatos de fichero de la aplicación

| Extensión | Contenido | Formato |
|---|---|---|
| `.dlvproj` | espacio de trabajo: referencias a logs, desfases, perfil activo, zoom, marcadores | JSON legible y versionado |
| `.dlvprofile` | perfil de análisis: paneles, canales por `ID`, escalas, alertas, detectores | JSON legible y versionado |
| `.dlvcache` | caché de parseo | Arrow IPC |
| `units.toml` | registro de unidades con `confidence` y centinelas | TOML versionado en el repositorio |
| `enums.toml` | diccionario de códigos de estado y máscaras de bits | TOML versionado en el repositorio |

Los dos últimos son **datos, no código**: ampliarlos no requiere recompilar y
puede hacerlo alguien sin conocimientos de programación. Es la mitigación
principal de los riesgos R1 y R2.

## 3.9 Empaquetado y portabilidad

- **Windows**: `.exe` único. Depende de WebView2, presente por omisión en
  Windows 10/11 actualizado; se detecta y se ofrece una descarga guiada si falta,
  y se documenta la alternativa de WebView2 embebido para el modo estrictamente
  portable.
- **Linux**: AppImage.
- **macOS**: `.app` en `.dmg`, firmado y notarizado.
- **Modo portable**: si existe un fichero `portable.txt` junto al ejecutable, la
  app no escribe nada fuera de su propia carpeta (ni configuración, ni caché, ni
  registro). Requisito de uso en pista con un pendrive.
- **Web**: PWA de solo lectura sobre el mismo núcleo en WASM, con límites
  documentados (tamaño de fichero y ausencia de acceso a carpetas).
- Sin telemetría ni comprobación de licencia. Sin conexión de red obligatoria en
  ningún flujo.

## 3.10 Preparación para móvil (fase 6, decisiones tomadas ahora)

Nada en v1.0 impide el objetivo móvil:

- El núcleo compila a `aarch64` y no depende del sistema de ficheros (ADR-002).
- La UI se diseña con puntos de ruptura y objetivos táctiles de ≥ 44 px desde el
  principio; los gestos de pan/zoom se implementan con *pointer events*, que
  cubren ratón y táctil con el mismo código.
- El renderizador usa WebGL2, disponible en iOS y Android.
- Se acota el alcance móvil esperado: **visualizar y revisar**, no analizar
  sesiones de una hora. La versión móvil abrirá logs internos de ECU (kilobytes)
  y resúmenes, no AutoLogs de 66 MB.
