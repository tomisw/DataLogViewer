# 10 — Guía: importar un CSV cualquiera y añadir un formato nativo

## 10.1 Para quién es esta guía

Para dos lectores distintos, en dos partes que se pueden leer por separado.

**Parte A** es para quien tiene un log de una ECU que no es Haltech —MoTeC,
Link, TunerStudio, un datalogger casero— y quiere abrirlo sin escribir nada:
qué hace el sondeo automático, qué es un rol semántico y qué tiene que hacer
cuando el importador no reconoce una columna. Sale de
`docs/07-formatos-y-csv-generico.md`, que sigue siendo la referencia completa;
esta parte es un resumen orientado a la tarea, no la sustituye.

**Parte B** es para quien tiene un formato de texto que sí conoce —tiene la
especificación del fabricante o unas cuantas cabeceras de ejemplo— y quiere
añadirlo como formato nativo de nivel 1 (`docs/07` §7.3), es decir, sin escribir
Python. Todo lo que dice la Parte B se ha comprobado leyendo
`dlv-core/src/dlv_core/formatos/nativo.py`, el descriptor real
`data/formats/haltech_nsp.toml` y las pruebas de
`dlv-core/tests/test_formato_nativo_declarativo.py`, y cada ejemplo de
descriptor de esta guía se ha cargado de verdad con `cargar_descriptor` antes
de escribirse aquí (§10.9 y §10.10 dicen cómo y con qué resultado literal).

Esta guía es la tarea FG-17 del backlog (`docs/05` línea 259) y depende de
FG-13 (`docs/05` línea 259, dependencia), la tarea que extrajo el motor de
formatos nativos del código de Haltech a un descriptor declarativo. Sin FG-13,
la Parte B no existiría: antes de ella, añadir un formato exigía tocar
`formatos/haltech.py`.

---

# Parte A — Importar un CSV cualquiera

## 10.2 El sondeo, antes que nada

Cuando se abre un fichero, lo primero no es preguntar al usuario: es sondear.
`docs/07` §7.3 dibuja dos niveles —formato nativo con firma reconocida, o CSV
genérico— y el sondeo es lo que decide cuál de los dos toca. En código, la
firma de un formato nativo es `Descriptor.firma` (el `[deteccion].primera_linea`
del descriptor, ver §10.8) y quien compara los bytes del fichero contra todas
las firmas conocidas es `sondear_formato` en
`dlv-core/src/dlv_core/formatos/nativo.py`. Si ninguna firma coincide, **no es
un error**: es la señal de que toca el camino de CSV genérico de la fase FG.
`test_el_sondeo_distingue_los_dos_formatos` (en el fichero de pruebas de FG-13)
lo comprueba literalmente: un CSV cualquiera con cabecera `time,rpm,map` sondea
a `None` con dos descriptores cargados, Haltech y uno inventado, y ese `None`
es correcto, no un fallo.

Entrado el camino genérico, el sondeo de `docs/07` §7.4 hace, sobre los primeros
64 kB del fichero y en este orden, diez pasos: codificación (BOM, o UTF-8, o
latin-1 con aviso), fin de línea, delimitador (por consistencia del número de
campos entre líneas, no por frecuencia: `csv.Sniffer` de la biblioteca estándar
no se usa porque es poco fiable con estos ficheros), separador decimal (`;` con
coma decimal es el caso español que rompe una lectura anglosajona), comillas y
escapes, estructura (cuál es la primera fila de datos, cuál la de nombres, si
hay una fila de unidades), preámbulo (metadatos antes de la cabecera), columna
de tiempo (§10.3), tipo por columna y, al final, roles (§10.4). Los módulos que
implementan cada paso viven en `dlv-core/src/dlv_core/formatos/`:
`decimal_csv.py`, `estructura.py`, `tiempo_csv.py`, `tipos.py`,
`unidades_declaradas.py`, `enums_csv.py`, `valores_csv.py` y `robustez_csv.py`
para los casos que no deben abortar la carga (`docs/07` §7.10). El catálogo de
roles vive en `data/roles.toml` y se carga con
`dlv_core.roles.cargar_catalogo_roles`.

Una regla que atraviesa todo el sondeo y que `docs/07` §7.4 subraya: **la
detección es una propuesta, no un hecho.** Nada se importa sin pasar por el
asistente de tres pasos de §7.8 (formato, tiempo, canales), con previsualización
viva en los tres. Un sondeo que se equivoca no corrompe nada porque el usuario
lo ve antes de que se aplique.

## 10.3 La columna de tiempo

`docs/07` §7.5 enumera ocho formas de columna de tiempo que hay que soportar,
todas vistas en logs reales: hora del día (`18:30:35.506`), ISO-8601 con zona
horaria, epoch en segundos o milisegundos (se distinguen por la magnitud),
tiempo relativo desde el inicio, contador de muestras (no es tiempo hasta que
el usuario declara la frecuencia), ausencia total de columna de tiempo (se
exige la frecuencia y se sintetiza el eje, marcando el log como *tiempo
sintético*), varias columnas que hay que combinar (`date` + `time`), y
distancia en vez de tiempo como eje alternativo. El vocabulario de estas ocho
formas es el enum `ClaseDeTiempo` de `dlv_core.formatos.tiempo_csv`, y es el
mismo vocabulario que usa el descriptor de un formato nativo para declarar su
`[cuerpo].clase_de_tiempo` (§10.8): no hay dos sistemas paralelos para el mismo
problema, y por eso la Parte B puede reusarlo sin traducir nada.

La regla dura, repetida en `docs/07` §7.5: si el eje es sintético o el reloj no
es fiable, el log queda marcado igual que un log interno de la ECU sin reloj de
tiempo real (`docs/01` §1.5), y la vista concatenada de varios logs exige
desfase manual. **Nunca se finge precisión temporal que no existe.**

## 10.4 Roles semánticos

Un rol es la capa de indirección que hace que el proyecto no dependa de los ID
de un fabricante concreto (`docs/07` §7.2). En vez de que el perfil «Knock»
pida el canal `696` de Haltech, pide el rol `knock_count[1]`; el importador es
quien decide, para cada formato, qué columna cumple cada rol. `docs/07` §7.7
da el catálogo completo por grupos (motor, mezcla, combustible, encendido,
knock, sobrealimentación, térmico, presiones, vehículo, eléctrico, estados, y
un grupo «futuro» todavía sin implementar) y el formato de cada entrada en
`roles.toml`:

```toml
[roles.coolant_temp]
dimension  = "temperature"
plausible  = { min = 233.15, max = 423.15 }   # canónica: K (-40 a 150 C)
synonyms   = ["Coolant Temperature", "CLT", "ECT", "Water Temp",
              "Temp. Refrigerante", "EngineTemp", "TCoolant"]
```

El código real de esta asignación es `dlv_core.roles.asignar_rol`, y su orden
de intento —comprobado leyendo la función, no solo el docstring— es: primero
coincidencia exacta del nombre normalizado (minúsculas, sin acentos, sin
separadores: `Régimen` y `regimen` son el mismo texto) contra un sinónimo del
catálogo; si el sinónimo lleva una marca `{n}` (p. ej. `"Knock Sensor {n} Knock
Count"`), coincidencia indexada con el número capturado; y si ninguna de las
dos entra, **como último recurso** un parecido difuso con `difflib`, por
encima de un umbral. Cada asignación lleva una `Confianza`: `EXACTA` e
`INDEXADA` son firmes, `DIFUSA` no está confirmada.

## 10.5 Qué pasa cuando un rol no se reconoce

`asignar_rol` devuelve `None` cuando ningún sinónimo, ni exacto ni difuso, pasa
el umbral. **Eso no es un error de importación.** El canal se importa igual,
sin rol: `docs/07` §7.8 lo dice explícitamente para el paso 3 del asistente
(«Se puede importar dejando canales sin rol: siguen siendo graficables, solo no
participan en perfiles ni detectores»). Lo que sí cambia es lo que ese canal
puede hacer después: sin rol, no entra en ningún perfil de fábrica ni en ningún
detector, porque los 10 perfiles y los 18 detectores de motorsport se definen
por rol (`docs/07` §7.12), no por nombre de columna.

Qué tiene que hacer el usuario en ese caso, según el mismo §7.8: en la tabla
de canales del paso 3 —columna, nombre, tipo inferido, dimensión, unidad de
origen, rol propuesto y una columna de avisos, ordenable por «necesita
atención»— puede asignar el rol a mano si sabe qué mide el canal, o dejarlo sin
rol si no lo sabe o si de verdad no corresponde a ninguno del catálogo. Cuando
la asignación fue `DIFUSA` (parecido, no exacta), el asistente la muestra como
propuesta pendiente de confirmar, y esa confirmación importa de verdad:
`docs/07` §7.15, mitigación 4, obliga a que los detectores de severidad crítica
(D4, D10, D12) se desactiven en un log cuyos roles implicados vengan de una
asignación difusa que el usuario no ha confirmado todavía. El razonamiento es
explícito en el propio documento: prefieren no avisar a avisar en falso, porque
una alerta falsa repetida enseña al usuario a ignorar las alertas.

Si el rol asignado es correcto pero la magnitud no lo es —el fallo típico del
importador genérico, según `docs/07` §7.15, es «acertar en la sintaxis y
equivocarse en el significado»—, el informe de plausibilidad de §7.7 punto 2
compara el valor contra el rango `plausible` declarado en `roles.toml` y lo
señala antes de importar, sin necesidad de abrir el fichero de origen.

Una vez asignados los roles (a mano o automáticamente, confirmados o no), el
asistente ofrece guardar el resultado como un perfil de importación
`.dlvimport` (`docs/07` §7.9): delimitador, decimal, filas de cabecera,
columna de tiempo y el mapa columna→rol, más una **huella de cabecera**
(hash de los nombres de columna normalizados). La segunda vez que se abre un
CSV con las mismas columnas, la huella coincide y la importación es un doble
clic; si coincide solo en parte —columnas añadidas o reordenadas—, se aplica lo
que encaja y el asistente se abre únicamente con lo pendiente.

## 10.6 Estado real de esto en el código, a día de escribir esta guía

Para no prometer más de lo que hay: el sondeo de codificación, fin de línea,
delimitador y decimal (FG-01, FG-02), la detección de estructura y de columna
de tiempo (FG-03, FG-04), la inferencia de tipo por columna (FG-05, hecha),
la unidad declarada en el nombre o en la fila de unidades (FG-06), los casos de
robustez de §7.10 (FG-07, FG-14, hechas) y la asignación automática de roles
(FG-09) **tienen código escrito y pruebas en verde**; casi todas están en
`revision_humana` en `state/PROGRESO.md` —esperando que el propietario las
revise, no a que se escriban—, salvo FG-05, FG-08 y FG-14, ya `hecho`. Lo que
todavía no existe en código, y aparece como `pendiente` en
`python tools/estado.py show <ID>`, es el informe de plausibilidad como
entregable propio (FG-10), el asistente de importación de 3 pasos con
previsualización viva como componente (FG-11) y el perfil `.dlvimport` con su
huella (FG-12): el comportamiento que describen §10.5 y el párrafo anterior es
el que exige `docs/07`, con el módulo de roles ya construido para soportarlo,
pero la interfaz de usuario y el fichero de perfil todavía no están
implementados. Compruébalo tú mismo, no te fíes de esta lista si ha pasado
tiempo desde que se escribió: `python tools/estado.py show FG-11`.

---

# Parte B — Añadir un formato nativo nuevo

## 10.7 La frontera entre descriptor y motor

El motor que interpreta cualquier formato nativo de texto es
`dlv_core.formatos.nativo`, y su docstring de cabecera fija la frontera con una
sola pregunta: **¿otro fabricante lo haría de otra manera?** Si la respuesta es
sí, es del descriptor —la firma, la clave y las versiones de compatibilidad, el
separador de clave y valor, qué clave abre un bloque de canal, cuál es la
identidad, cuál es el tipo, cuáles son opcionales, cuál trae el rango y en qué
orden, la codificación, el delimitador de campos y la forma de la marca de
tiempo—. Si la respuesta es no, es del motor: el BOM y los tres finales de
línea, el recuento de desplazamientos en bytes, la máquina de estados que abre
y cierra bloques, qué es error y qué es aviso, la detección de nombres e
identidades repetidos, y la mecánica de leer un CSV disperso multi-tasa (que no
tiene nada de específico de un fabricante: sale del patrón de nulos,
`almacen.py` y `grupos_muestreo.py`).

Antes de la tarea FG-13 (commit `71c9f21`, rama
`claude/log-visualization-app-plan-5lhr8x`), varias de esas decisiones de
formato estaban cableadas en `formatos/haltech.py`: la clave `DataLogVersion`,
los nombres `ID`/`Type`/`DisplayMaxMin`, el `:` de separación y el orden
«máximo primero» del rango. Añadir un segundo formato nativo hubiera exigido
tocar ese código. FG-13 subió las nueve decisiones al descriptor y las
pruebas de `test_formato_nativo_declarativo.py` demuestran la promesa con un
formato inventado, «TorqueTrace TT-2», que invierte las ocho decisiones
principales de Haltech (firma distinta, `Clave= Valor` en vez de
`Clave : Valor`, versión en `Rev`, tipo en `Kind`, identidad en `Idx`, rango
`Limits` en orden mínimo-máximo, delimitador `;`, marca con coma decimal) y se
parsea entero sin una sola línea de Python nueva. Esa suite pasa hoy: 20
pruebas, comprobado con
`PYTHONPATH=dlv-core/src /root/.local/bin/pytest dlv-core/tests/test_formato_nativo_declarativo.py -q`
(«20 passed»).

El motor es estricto a propósito. `cargar_descriptor` exige toda clave cuya
ausencia se pagaría en silencio —si un descriptor no dice cuál es su clave de
tipo, adivinar «será `Type`» produce canales con la escala equivocada y un
fichero que parece haberse leído bien—, y solo deja opcionales las dos claves
que pueden significar legítimamente «este formato no tiene eso»:
`clave_version` (un formato sin línea de versión) y `clave_rango` (un formato
que no declara rangos). Un descriptor incompleto o incoherente falla **al
cargarse**, no al leer el primer fichero, y el mensaje nombra el formato y la
clave.

## 10.8 Tabla de todas las claves del descriptor

Tabla derivada leyendo `cargar_descriptor`, `_gramatica`, `_cuerpo` y
`_orden_de_rango` en `dlv_core/formatos/nativo.py`, más `PoliticaReloj.desde_mapa`
en `dlv_core/reloj.py` para `[reloj]`. «Obligatoria» significa que
`cargar_descriptor` lanza `ErrorDeDescriptor` sin ella; «opcional» que hay un
valor por omisión o que su ausencia declara «este formato no tiene eso».

| Sección | Clave | Oblig. | Qué significa | Si falta |
|---|---|---|---|---|
| `[meta]` | `formato` | **sí** | Nombre interno del formato; aparece en todos los mensajes de error posteriores y en `Descriptor.formato` | `ErrorDeDescriptor`: *"el descriptor (sin nombre) no declara [meta].formato…"* |
| `[meta]` | cualquier otra (`software`, `tarea`, `especificacion`, `version_datalog`, `fila_de_referencia`…) | no | Documentación para quien revisa la puerta G1; **no la lee el motor** | nada — no se comprueba |
| `[deteccion]` | `primera_linea` | **sí** | Los bytes de la firma; se codifican con `[deteccion].codificacion` y pasan a `Descriptor.firma`. Es lo que compara `sondear_formato` | `ErrorDeDescriptor` citando `[deteccion].primera_linea` |
| `[deteccion]` | `version_soportada` | no (lista, por omisión vacía) | Conjunto de valores aceptados de la clave de versión | si `clave_version` está declarada y el conjunto queda vacío, **toda versión se rechaza** al parsear un fichero real |
| `[deteccion]` | `clave_version` | no | Nombre de la clave de metadato que trae la versión de la cabecera. Ausente = el formato no versiona: no se exige ni se comprueba nada | ninguna comprobación de versión; cualquier fichero de ese formato se acepta sin mirar versión |
| `[deteccion]` | `codificacion` | no (por omisión `"utf-8"`) | Codificación de la cabecera; se valida con `codecs.lookup` | si el valor no es una codificación real, `ErrorDeDescriptor` citando el valor inválido (p. ej. `'utf-42'`) |
| `[deteccion]` | otras (`finales_de_linea`, …) | no | Documentación libre | no se comprueban |
| `[cabecera]` | `separador_clave_valor` | **sí** | Texto que separa clave y valor en una línea de cabecera (`:`, `=`…); se recortan los espacios de los dos lados | `ErrorDeDescriptor` citando `[cabecera].separador_clave_valor` |
| `[cabecera]` | `clave_canal` | **sí** | La clave que ABRE un bloque de canal. El orden de aparición de los bloques fija el orden de las columnas | `ErrorDeDescriptor` citando `[cabecera].clave_canal` |
| `[cabecera]` | `identidad` | **sí** | Clave del bloque que da el ID estable del canal (nunca el nombre). Debe estar en `claves_bloque` y no puede estar en `claves_opcionales` | si falta la clave: error citando `identidad`; si no está en `claves_bloque`: *"…que no está en claves_bloque"*; si está marcada opcional: *"…sin ella no se puede saber qué columna es qué canal"* |
| `[cabecera]` | `clave_tipo` | **sí** | Clave del bloque cuyo valor se resuelve contra `[tipos]`. Misma doble comprobación que `identidad` (debe estar en `claves_bloque`, no puede ser opcional) | igual que `identidad`, con el nombre `clave_tipo` en el mensaje |
| `[cabecera]` | `claves_bloque` | **sí** (lista no vacía) | Todas las claves que pertenecen a un bloque de canal; una clave que no esté aquí cierra el bloque y pasa a metadato | `ErrorDeDescriptor`: *"…no declara [cabecera].claves_bloque como una lista no vacía"* |
| `[cabecera]` | `claves_opcionales` | no (por omisión ninguna) | Subconjunto de `claves_bloque` que puede faltar sin desalinear el bloque | si contiene una clave que no está en `claves_bloque`: *"declara como opcionales claves que no son de bloque: …"* |
| `[cabecera]` | `clave_rango` | no | Clave del bloque que trae el rango declarado del canal (el `DisplayMaxMin` de Haltech). Ausente = el formato no declara rangos, y entonces `rango_separador`/`rango_orden` no se leen | ninguna comprobación; todo canal tiene `display_max = display_min = None` |
| `[cabecera]` | `rango_separador` | **sí, solo si `clave_rango` está presente** | Texto que separa los dos valores del rango dentro de la celda (`,`, `;`…) | si `clave_rango` está pero esta falta: `ErrorDeDescriptor` citando `[cabecera].rango_separador` |
| `[cabecera]` | `rango_orden` | **sí, solo si `clave_rango` está presente** | `["max","min"]` o `["min","max"]`: en qué orden vienen los dos valores. Son los ÚNICOS dos valores aceptados | cualquier otra combinación (incluida `["max","max"]`) → `ErrorDeDescriptor` listando los dos valores válidos |
| `[cabecera]` | `metadatos_cierre` | no | Presente en `haltech_nsp.toml`, documenta qué metadatos cierran el bloque final. **El motor no la lee** — ver §10.10 | nada; no tiene efecto declararla u omitirla |
| `[cuerpo]` | `delimitador` | **sí** | Separador de campos de una fila de datos. Se escapa como regex al compilar `fila_de_datos`, así que un delimitador como `\|` no crea una alternancia por accidente | `ErrorDeDescriptor` citando `[cuerpo].delimitador` |
| `[cuerpo]` | `clase_de_tiempo` | **sí** | Qué es la primera columna, con el vocabulario de `ClaseDeTiempo` (§10.3). Debe ser un valor válido del enum **y además** estar en el conjunto que el motor sabe interpretar (hoy solo `hora_del_dia`, ver §10.11) | valor no reconocido: error listando los 8 valores válidos; valor reconocido pero no soportado (p. ej. `iso8601`): error explícito de límite, ver §10.11 |
| `[cuerpo]` | `patron_marca` | **sí** | Expresión regular (sin anclas ni delimitador) que reconoce el inicio de una fila de datos y por tanto dónde acaba la cabecera. Se ancla con `^` y se le concatena el delimitador escapado al compilar | si falta: error citando `[cuerpo].patron_marca`; si no es una regex válida o no es codificable en la codificación declarada: error citando el motivo |
| `[tipos]` | (la sección en sí) | **sí** (puede estar vacía) | Mapa `Type → {dimension, a_canonica, confianza, …}` que resuelve la escala de cada canal | `ErrorDeDescriptor`: *"…no declara la sección [tipos]"* |
| `[tipos.<Tipo>]` | `dimension` | **sí** | Dimensión física del catálogo de `data/units.toml` (o `"unknown"`) | `ErrorDeDescriptor` nombrando el tipo, el descriptor y la clave que falta |
| `[tipos.<Tipo>]` | `a_canonica` | **sí** | Factor multiplicativo: `canónica = crudo * a_canonica`. No puede ser 0 (convertiría el canal en ceros) ni un booleano (`true` colaría como 1,0 y el canal saldría sin escalar) | `ErrorDeDescriptor` nombrando el tipo y la clave; mensajes propios para el 0 y para el booleano |
| `[tipos.<Tipo>]` | `confianza` | **sí** | `"confirmed"` / `"inferred"` / `"unknown"`; gobierna si el canal se muestra en crudo | `ErrorDeDescriptor` nombrando el tipo y la clave |
| `[tipos.<Tipo>]` | otras (`evidencia`, `canales`, `referencia`, `clase`, `compuesta`, `rol_sugerido`, `subtipos`…) | no | Documentación para la puerta G1 (evidencia del factor, recuento de canales…). **El motor no las lee**: `Descriptor.resuelve` solo toma `dimension`, `a_canonica` y `confianza` | nada |
| `[reloj]` | (la sección entera) | no | Nombres de clave y parámetros de la política de reloj (F1-04). Ausente o vacía = se hereda la política de Haltech al completo | ninguna comprobación en `cargar_descriptor`; ver aviso más abajo |
| `[reloj]` | `clave_inicio`, `clave_descarga`, `clave_numero`, `hora_en_12h`, `epocas_ficticias`, `tolerancia_desfase_s` | no | Cada una tiene el valor de Haltech como omisión (`PoliticaReloj`, `dlv_core/reloj.py`) | se usa el valor de Haltech; **no hay aviso de que se ha heredado en silencio** |
| `[reloj]` | `fecha_minima_plausible` | no (por omisión `2005-01-01`) | Fecha AAAAMMDD por debajo de la cual una fecha de cabecera se considera época de fábrica, no real | si el valor no tiene forma AAAAMMDD: `ErrorDeReloj` (no `ErrorDeDescriptor`) citando el valor |
| `[reloj]` | `clave_origen` | no | Presente en `haltech_nsp.toml`, documenta el origen del log. **`PoliticaReloj` no tiene ningún campo con ese nombre**, así que tampoco se lee — mismo defecto que `metadatos_cierre` | nada |
| `[resumen]` | cualquier clave | no | Auditoría del propio descriptor (recuentos de tipos confirmados/inferidos/desconocidos). **El motor no la lee** | nada |

Dos matices que la tabla no puede llevar en una celda:

1. **`identidad` y `clave_tipo` tienen una comprobación de coherencia además de
   la de existencia.** No basta con declararlas: `_gramatica` comprueba que las
   dos estén en `claves_bloque` y que ninguna esté en `claves_opcionales`. Es
   deliberado —§10.7 lo explica con la palabra «adivinar»— porque una identidad
   opcional o fuera de bloque cargaría el descriptor sin protestar y fallaría
   después, canal a canal, con la cabecera ya medio leída.
2. **Las claves de `[tipos.<Tipo>]` son la única inconsistencia real que se ha
   encontrado en este motor.** El resto de la tabla falla exactamente donde
   dice `cargar_descriptor`. Estas tres no: §10.10 lo demuestra con la
   ejecución real, no con la lectura del código.

## 10.9 Ejemplo mínimo, ejecutable de verdad

Este es el descriptor más pequeño que carga con el motor de hoy: un formato de
texto inventado, «MiniLog ML-1», con un solo tipo de canal y sin rango
declarado.

```toml
[meta]
formato = "minilog_ml1"

[deteccion]
primera_linea = "#MiniLog"
version_soportada = ["1"]
clave_version = "FormatVersion"

[cabecera]
separador_clave_valor = "="
clave_canal = "Chan"
claves_bloque = ["Id", "Kind"]
identidad = "Id"
clave_tipo = "Kind"

[cuerpo]
delimitador = ","
clase_de_tiempo = "hora_del_dia"
patron_marca = "\\d\\d:\\d\\d:\\d\\d\\.\\d\\d\\d"

[tipos.RPM]
dimension = "angular_speed"
a_canonica = 1.0
confianza = "confirmed"
```

Comprobado literalmente con:

```bash
PYTHONPATH=dlv-core/src python3.12 -c "
import io
from dlv_core.formatos.nativo import cargar_descriptor
d = cargar_descriptor(io.BytesIO(open('minilog.toml','rb').read()))
print('OK', d.formato)
"
```

Salida real: `OK minilog_ml1`. Y con un fichero de ese formato:

```
#MiniLog
FormatVersion=1
Chan=Engine RPM
Id=1
Kind=RPM
08:00:00.000,850
08:00:00.100,851
```

`parsear_cabecera` sobre esos bytes con el descriptor anterior devuelve, de
verdad: `formato='minilog_ml1'`, `version='1'`, un canal (`Engine RPM`, `id=1`,
`tipo='RPM'`, `dimension='angular_speed'`, sin `display_max`/`display_min`
porque no se declaró `clave_rango`), `offset_datos=60` (el byte donde empieza
`08:00:00.000,850`) y **cero avisos**. Comprobado con el mismo intérprete,
llamando a `parsear_cabecera(log, d)` sobre esos bytes exactos.

Para un descriptor de producción, `haltech_nsp.toml` (§10.8 lo usa como fuente
de toda la tabla) es el ejemplo completo con rango declarado, reloj y 34 tipos;
este ejemplo mínimo es deliberadamente pequeño para que se pueda copiar entero
en un editor y ver qué es indispensable y qué no.

## 10.10 Cómo falla, mensaje por mensaje

Cada línea de esta lista se ha comprobado quitando esa clave (o corrompiéndola)
del ejemplo de §10.9 o del descriptor «TorqueTrace TT-2» de
`test_formato_nativo_declarativo.py`, y volviendo a llamar a
`cargar_descriptor`. El texto entre comillas es la salida literal de
`str(excepcion)`, no una paráfrasis.

| Qué se quita o se corrompe | Excepción | Mensaje literal |
|---|---|---|
| `[meta].formato` | `ErrorDeDescriptor` | `el descriptor (sin nombre) no declara [meta].formato, y sin ella el motor tendría que adivinarla` |
| la sección `[meta]` entera | `ErrorDeDescriptor` | `el descriptor (sin nombre) no declara la sección [meta]` |
| `[deteccion].primera_linea` | `ErrorDeDescriptor` | `el descriptor minilog_ml1 no declara [deteccion].primera_linea, y sin ella el motor tendría que adivinarla` |
| la sección `[deteccion]` entera | `ErrorDeDescriptor` | `el descriptor minilog_ml1 no declara la sección [deteccion]` |
| `[cabecera].separador_clave_valor` | `ErrorDeDescriptor` | `el descriptor minilog_ml1 no declara [cabecera].separador_clave_valor, y sin ella el motor tendría que adivinarla` |
| `[cabecera].claves_bloque` | `ErrorDeDescriptor` | `el descriptor minilog_ml1 no declara [cabecera].claves_bloque como una lista no vacía` |
| `[cabecera].identidad` declarada pero fuera de `claves_bloque` | `ErrorDeDescriptor` | `el descriptor minilog_ml1 declara [cabecera].identidad = 'Serial', que no está en claves_bloque` |
| `[cabecera].identidad` metida además en `claves_opcionales` | `ErrorDeDescriptor` | `el descriptor minilog_ml1 declara [cabecera].identidad = 'Id' como opcional; sin ella no se puede saber qué columna es qué canal` |
| `[cabecera].claves_opcionales` con una clave que no es de bloque | `ErrorDeDescriptor` | `el descriptor minilog_ml1 declara como opcionales claves que no son de bloque: Extra` |
| `[cuerpo]` la sección entera | `ErrorDeDescriptor` | `el descriptor minilog_ml1 no declara la sección [cuerpo]` |
| `[cuerpo].clase_de_tiempo` con un valor inventado | `ErrorDeDescriptor` | `…declara [cuerpo].clase_de_tiempo = 'cuando_sea', que no es una clase de tiempo conocida (ausente, contador_de_muestras, epoch_milisegundos, epoch_segundos, fecha_y_hora_separadas, hora_del_dia, iso8601, relativo)` |
| `[cuerpo].clase_de_tiempo = "iso8601"` (válida pero no interpretable) | `ErrorDeDescriptor` | `…declara [cuerpo].clase_de_tiempo = 'iso8601', que la ruta nativa reconoce pero todavía no sabe interpretar (soportadas: hora_del_dia); ver FG-13/FG-17` |
| `[deteccion].codificacion = "utf-42"` | `ErrorDeDescriptor` | `el descriptor minilog_ml1 declara [deteccion].codificacion = 'utf-42', que no es una codificación conocida` |
| `[cabecera].rango_orden = ["max","max"]` | `ErrorDeDescriptor` | `el descriptor minilog_ml1 declara [cabecera].rango_orden = ['max', 'max']; los únicos valores posibles son ['max', 'min'] y ['min', 'max']` |
| `[cabecera].clave_rango` apuntando a una clave que no está en `claves_bloque` | `ErrorDeDescriptor` | `el descriptor minilog_ml1 declara [cabecera].clave_rango = 'Range', que no está en claves_bloque` |
| la sección `[tipos]` entera | `ErrorDeDescriptor` | `el descriptor minilog_ml1 no declara la sección [tipos]` |
| `Rev= 2.1` sustituida por `Rev= 3.0` (versión no soportada) en el fichero de datos | `ErrorDeFormato` | mensaje que cita `3.0` y las versiones soportadas (comprobado con el TT-2 real de la suite: `pytest.raises(ErrorDeFormato, match=r"3\.0")`) |
| `[tipos.RPM].a_canonica` | `ErrorDeDescriptor` | `[tipos.RPM] del descriptor minilog_ml1 no declara a_canonica. `a_canonica` es el factor de escala del canal: sin él no se puede convertir, y adivinarlo daría valores plausibles con la escala equivocada` |
| `[tipos.RPM].a_canonica = 0` | `ErrorDeDescriptor` | `…declara `a_canonica = 0`, que convertiría el canal entero en ceros` |

Los dos últimos casos no estaban así cuando se escribió esta guía, y merece la
pena contar por qué cambiaron. `cargar_descriptor` solo comprobaba que `[tipos]`
fuese una tabla, no que cada entrada tuviese sus tres claves: un tipo al que le
faltara `a_canonica` cargaba sin protestar y el fallo aparecía mucho más tarde, la
primera vez que `parsear_cabecera` encontraba un canal de ese tipo, como un
`KeyError: 'a_canonica'` pelado — sin nombre de descriptor, de tipo ni de clave.

Era el único sitio del motor con ese modo de fallar, justo el que el resto evita a
propósito (§10.7), y en el peor lugar posible: `a_canonica` es el factor de escala
del canal, así que el fallo no da un log ilegible sino uno con valores plausibles y
la escala equivocada. Escribir esta guía fue lo que lo destapó, y se cerró en el
mismo trabajo: ahora `[tipos]` se valida al cargar, con un mensaje que nombra el
tipo, el descriptor y la clave, y con comprobaciones propias para `a_canonica = 0`
(convertiría el canal en ceros, que se ve igual que un sensor desconectado) y para
`a_canonica = true` (`bool` es subclase de `int` en Python, así que colaría como
1,0 y el canal saldría sin escalar). Las pruebas están en
`dlv-core/tests/test_formato_nativo_declarativo.py`.

## 10.11 El límite del nivel 1: qué no se puede describir hoy

Esta sección existe porque el propio módulo la pide. El docstring de
`nativo.py` tiene una sección titulada «QUÉ SIGUE CABLEADO EN PYTHON, Y POR QUÉ
(para FG-17)», escrita para esta guía, y su contenido —comprobado leyendo el
código citado en cada punto, no solo el comentario— es este límite honesto:

1. **Solo se sabe interpretar una clase de marca de tiempo: `hora_del_dia`.**
   El descriptor puede declarar cualquiera de los 8 valores de `ClaseDeTiempo`
   en `[cuerpo].clase_de_tiempo`, pero el único intérprete que existe hoy es
   `dlv_core.reloj.parsear_marca_de_fila`, que solo entiende `HH:MM:SS.mmm`. Un
   descriptor que declare `iso8601`, `epoch_segundos` o cualquier otra clase
   válida **se rechaza al cargarse**, con el mensaje exacto de la fila
   correspondiente en §10.10, en vez de cargar y producir después un eje de
   tiempo inventado. Añadir un formato con la marca de tiempo en otra forma
   —ISO-8601, epoch, relativo— exige escribir el intérprete correspondiente en
   `dlv_core.reloj`, no solo el descriptor.
2. **La marca de tiempo tiene que estar en la primera columna.**
   `Canal.columna` se calcula como `orden + 1` (docs/01 §1.3) y toda la ruta de
   cuerpo (`cuerpo.py`, `almacen.py`) depende de esa relación. Un formato que
   ponga el tiempo en otra columna no cabe en el descriptor: necesita código.
3. **El rango declarado es una pareja de enteros**, porque es lo que exige el
   almacenamiento entero de ADR-003 y lo que trae Haltech. Un formato con
   rangos decimales perdería la parte fraccionaria; hoy eso se avisa y se
   ignora (`Aviso` `displaymaxmin_invalida`, ver `_rango_declarado` en
   `nativo.py`), no se redondea ni se trunca en silencio.
4. **Los metadatos de cabecera son planos: `clave <sep> valor`, una línea por
   entrada.** Un formato con secciones anidadas, o con toda la cabecera en una
   sola línea, no cabe en esta gramática. Es el «gancho opcional de código» que
   `docs/07` §7.3 ya prevé para lo indescriptible.
5. **La política de reloj por omisión sigue siendo la de Haltech**
   (`PoliticaReloj`, `dlv_core/reloj.py`, ver la fila `[reloj]` de §10.8). Un
   descriptor nuevo que se olvide de la sección `[reloj]` hereda en silencio
   los nombres de clave de Haltech (`Log`, `DownloadDateTime`, `Log Number`,
   hora en 12 h) porque `PoliticaReloj.desde_mapa` rellena con esos valores
   cuando la sección está vacía o ausente. **Declara siempre `[reloj]`** en un
   formato nuevo, aunque sea para repetir los mismos valores a propósito: la
   alternativa es un formato que hereda por accidente el reloj de otro
   fabricante.
6. **Descubrir los descriptores no es parte de este módulo** (`dlv-core` no
   abre ficheros, ADR-002). Hoy `dlv-api` carga un único descriptor por ruta
   fija: la función `_descriptor_haltech` de `dlv-api/src/dlv_api/main.py`
   abre `data/formats/haltech_nsp.toml` con una ruta cableada y la cachea con
   `lru_cache(maxsize=1)`. **Escribir el descriptor de un formato nuevo no
   basta para que la aplicación lo use**: hoy no hay ningún mecanismo que
   recorra `data/formats/*.toml` y construya la tupla de descriptores que
   espera `sondear_formato`; `dlv-api` solo conoce Haltech por ese nombre de
   función. Añadir un segundo formato de verdad exige además generalizar esa
   función (o su reemplazo), y eso es trabajo de `dlv-api`, no de un fichero
   TOML nuevo en `data/formats/`.

## 10.12 Receta para escribir tu propio descriptor

Con la tabla de §10.8, el ejemplo de §10.9 y la lista de fallos de §10.10
delante, el orden que menos vueltas da es:

1. Copia el ejemplo mínimo de §10.9 a un fichero en `data/formats/<tu_formato>.toml`
   (o a un fichero suelto mientras lo desarrollas: `cargar_descriptor` solo pide
   un `IO[bytes]`, no una ruta concreta).
2. Cambia `[meta].formato`, `[deteccion].primera_linea` y, si tu formato
   versiona la cabecera, `[deteccion].clave_version` y
   `[deteccion].version_soportada`.
3. Rellena `[cabecera]` con los nombres reales de tu formato:
   `clave_canal`, `claves_bloque`, `identidad`, `clave_tipo`, y
   `claves_opcionales` para lo que sepas que puede faltar sin desalinear el
   bloque (comprueba en unas cuantas cabeceras reales, como hizo F0-09 con los
   13 de 475 canales de Haltech sin `DisplayMaxMin`).
4. Si tu formato declara un rango por canal, añade `clave_rango`,
   `rango_separador` y `rango_orden` — y verifica el orden con un canal
   conocido antes de fijarlo: invertirlo no rompe nada visible, solo deja el
   máximo en el mínimo (la misma trampa que documenta `haltech_nsp.toml`).
5. Rellena `[cuerpo]`: el delimitador real, la `clase_de_tiempo` (hoy solo
   `hora_del_dia` funciona de verdad, §10.11 punto 1) y `patron_marca` como
   regex de la forma de la marca, sin ancla ni delimitador.
6. Por cada `Type`/`Kind`/lo-que-sea que use tu formato, añade una entrada
   `[tipos.<nombre>]` con `dimension` (del catálogo de `data/units.toml`, o
   `"unknown"` si no la sabes), `a_canonica` y `confianza`
   (`"confirmed"`/`"inferred"`/`"unknown"`) — y no dejes ninguna sin las tres
   claves: §10.10 muestra que el motor no te va a avisar al cargar.
7. Añade `[reloj]` aunque sea copiando los valores de Haltech a propósito
   (§10.11 punto 5): mejor explícito que heredado por accidente.
8. Carga el descriptor de verdad —no lo revises solo a ojo— con el comando de
   §10.9, y luego parsea un fichero de ejemplo real de tu formato con
   `parsear_cabecera`. Mira los avisos (`Cabecera.avisos`), no solo si lanzó
   una excepción: un tipo desconocido o una escala sin confirmar no rechazan
   la carga, pero sí dicen que ese canal se va a mostrar en crudo.
9. Recuerda el punto 6 de §10.11: el descriptor cargando no significa que la
   aplicación lo use. Hoy hace falta además tocar `dlv-api` para que
   `sondear_formato` reciba tu descriptor en la tupla que compara.

## 10.13 Qué no se puede hacer, para no perder tiempo buscándolo

- No se puede añadir un formato binario por esta vía: el nivel 1 es solo texto
  (`docs/07` §7.3); un formato binario necesita el «gancho opcional de código»
  que el mismo documento prevé, y hoy no hay ningún ejemplo de esa vía en el
  repositorio.
- No se puede declarar una marca de tiempo que no sea `hora_del_dia` y
  esperar que cargue: se rechaza, no se aproxima (§10.11 punto 1).
- No se puede poner la columna de tiempo en cualquier posición: tiene que ser
  la primera (§10.11 punto 2).
- Sí se puede confiar en que una entrada de `[tipos.<Tipo>]` incompleta falle al
  cargar el descriptor, y en que el mensaje nombre el tipo y la clave (§10.10).
  Hasta que se escribió esta guía no era así, y el hallazgo salió de escribirla.
- No se puede dar por hecho que un descriptor nuevo en `data/formats/` hace
  que la aplicación lo reconozca: falta el cableado de descubrimiento en
  `dlv-api` (§10.11 punto 6).
