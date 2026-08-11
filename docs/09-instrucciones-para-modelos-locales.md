# 09 — Instrucciones para modelos ejecutados en local

## 9.1 Para quién es este documento

Para un modelo que continúa el desarrollo de DataLogViewer **en la máquina del
propietario**, no en el contenedor remoto donde se hizo el arranque del plan.

`docs/08-ejecucion-y-reanudacion.md` describe el protocolo de ejecución y sigue
siendo la referencia: invariantes, bucle de orquestación, libro de estado y
puertas. **Este documento no lo sustituye, lo complementa** con lo que cambia
cuando la sesión corre en local, que no es poco: hay red, hay dependencias
instalables y el propietario está delante y puede aprobar una puerta G1 en el
momento.

Si solo vas a leer una sección, lee la 9.7. Son las reglas que, si se rompen, no
se nota hasta que ya ha llegado a una decisión de tuning.

## 9.2 Qué cambia respecto al entorno remoto

| | Contenedor remoto | Local |
|---|---|---|
| Red / PyPI | **bloqueado** (403 local, `pypi.org` en `no_proxy`) | disponible |
| `polars`, `numpy`, `fastapi` | no instalables | `uv sync --all-packages` |
| `pytest`, `ruff`, `mypy` | binarios aislados, si están | del entorno virtual del proyecto |
| Medir rendimiento | imposible: 13 de 14 presupuestos `NO_MEDIBLE` | **posible, y es lo que más falta** |
| Puertas G1 | quedan en `revision_humana` esperando | el propietario aprueba en la misma sesión |
| Contenedor | efímero, se recicla | persistente |
| `bash tools/verificar.sh` | funciona | funciona en Git Bash; en Windows usa `python tools/verificar.py` |

Dos consecuencias que cambian qué conviene hacer:

1. **Lo escaso en remoto era la red; en local lo escaso es la atención del
   propietario.** El trabajo con más valor en local es el que estaba bloqueado
   por dependencias (F0-01, F1-02, F1-05, F1-09 y todo lo que mide el banco), no
   más trabajo sin dependencias, que ya se ha hecho en remoto precisamente porque
   era lo único posible.
2. **La regla 3 de §8.2 sigue vigente aunque el contenedor no sea efímero.** Un
   `push` por tarea mantiene sincronizadas las dos vías de trabajo, remota y
   local. Si divergen, el libro de estado —`state/tareas.json`— es el fichero que
   más duele fusionar a mano.

## 9.3 Puesta en marcha, la primera vez

El gestor del entorno Python es **`uv`** (decisión de F0-02, razonada en
`pyproject.toml`). No uses `pip` ni `venv` a mano: el workspace resuelve las
dependencias cruzadas entre `dlv-core`, `dlv-api` y `dlv-app` con
`[tool.uv.sources]`, y un entorno montado a mano no las tendrá.

```bash
git clone <repo> && cd DataLogViewer
git checkout claude/log-visualization-app-plan-5lhr8x
uv sync --all-packages
```

Comprueba que ha entrado lo que hacía falta:

```bash
uv run python -c "import polars, numpy; print(polars.__version__, numpy.__version__)"
```

El frontend es un proyecto TypeScript independiente y **no** entra en el
workspace de `uv`:

```bash
cd dlv-ui && npm install
```

### Windows

Todo lo anterior funciona igual en PowerShell. La única diferencia real es que
`tools/verificar.sh` es bash: usa

```powershell
python tools\verificar.py
```

que ejecuta exactamente las mismas seis comprobaciones. Si tienes Git Bash, la
orden con `bash` también vale y no hay que elegir.

## 9.4 La única orden que decide si algo está terminado

```bash
bash tools/verificar.sh        # o: python tools/verificar.py
```

Seis comprobaciones —`ruff check`, `ruff format --check`, `mypy --strict`,
`pytest`, ADR-009 y presupuestos—, un resumen al final y código de salida
distinto de cero si algo está en rojo.

**Úsala en lugar de ejecutar las herramientas a mano.** No es preferencia de
estilo: se escribió después de que dos commits salieran con el lint en rojo, las
dos veces por la misma razón. `ruff check` imprime «No fixes available…»
*después* de «Found N errors», así que mirar el final de su salida engaña. El
guion usa códigos de salida, que no admiten interpretación.

Tres cosas que conviene saber de cómo encuentra las herramientas:

- Si no están en el `PATH` pero hay `uv`, las ejecuta con `uv run` y lo dice en
  el resumen. No hace falta activar el entorno virtual.
- Una herramienta que **no se encuentra cuenta como fallo**, no como
  comprobación omitida. No haber podido mirar no es estar en verde.
- Solo `pytest` tiene sustituto: `tools/pytest_minimo.py`, para entornos sin
  PyPI. Si se usa, el resumen lo marca. En local, con `uv sync` hecho, no debería
  usarse nunca; si aparece en el resumen, es que el entorno no está montado.

## 9.5 El bucle de trabajo de una sesión local

El de §8.4, con dos añadidos:

```
0. uv sync --all-packages          (por si el bloqueo de dependencias cambió)
1. git pull origin claude/log-visualization-app-plan-5lhr8x
2. python tools/estado.py next
3. ¿hay tareas en_curso? → terminarlas o `block` antes de empezar nada
4. elegir tarea, respetar el modelo asignado (§9.6)
5. python tools/estado.py start <ID> --agente <opus|sonnet|haiku>
6. implementar con el contexto de §8.6
7. bash tools/verificar.sh          ← en verde, sin excepciones
8. git add -A && git commit
9. python tools/estado.py done <ID> --nota "<qué quedó hecho y qué no>"
10. git commit --amend --no-edit
11. git push -u origin claude/log-visualization-app-plan-5lhr8x
12. ¿es una tarea G1? → enseñar al propietario QUÉ tiene que revisar (§9.9)
13. volver a 2
```

El paso 12 es el añadido que justifica trabajar en local: una puerta G1 aprobada
en el momento no acumula deuda de revisión. En remoto se acumulaban ocho.

## 9.6 Qué modelo ejecuta cada tarea

La columna `Modelo` del backlog (`docs/05`) y de `tareas.json` **no es
decorativa**: reparte 669 puntos entre tres modelos según cuánto criterio exige
cada tarea. En local:

| Modelo asignado | Cómo se ejecuta |
|---|---|
| **Opus 5** | en línea, sin delegar. Ya tiene la especificación cargada; un subagente tendría que re-derivarla |
| **Sonnet 5** | subagente en segundo plano (`model: sonnet`) |
| **Haiku 4.5** | subagente en segundo plano (`model: haiku`) |

Dos o tres subagentes en paralelo como máximo, y **solo si sus tareas no tocan
los mismos ficheros**. El libro de estado lo escribe únicamente quien orquesta:
los subagentes entregan código y no tocan `state/` ni hacen commit. Es lo que
evita conflictos de fusión en el fichero más importante del repositorio.

Si una tarea marcada Sonnet o Haiku resulta más delicada de lo que parecía —y
pasa—, súbela a Opus y **anótalo en la nota de la tarea**. Lo contrario, bajar una
tarea Opus a un modelo más pequeño para ahorrar, es lo único que no se debe hacer
sin preguntar: las tareas Opus son las que tienen puerta G1 casi siempre, y lo
tienen porque sus números llegan a decisiones de motor.

## 9.7 Reglas no negociables

Estas seis no se saltan, y ninguna es una preferencia de estilo: cada una está
puesta detrás de un fallo concreto que ya ocurrió o que se identificó como el más
probable de su subsistema.

**1. ADR-009 — cero bucles por muestra en Python.** Todo el trabajo por muestra
se expresa con Polars o NumPy. Si algo no se puede vectorizar, va a Numba, no a un
`for`. `python tools/banco.py adr009` lo comprueba con análisis del árbol
sintáctico y es una de las seis puertas. La razón es aritmética: 73 millones de
muestras a 100 ns por iteración de Python son 7 segundos, y el presupuesto entero
de primera apertura es de 4.

**2. `data/*.toml` son datos, no código.** `units.toml`, `roles.toml`,
`enums.toml`, `umbrales.toml`, `casos_de_unidades.toml` y `formats/*.toml` se
amplían sin recompilar y sin saber programar. **No traslades ninguno de esos
valores al código**, ni «de momento», ni «para que sea más rápido». Y no
reformatees los ficheros: los comentarios explican de dónde sale cada número y son
lo que hace revisable la puerta G1.

**3. Los umbrales son configurables, no constantes.** `data/umbrales.toml` da
valores **por omisión**. La precedencia, escrita en la cabecera del propio
fichero: anulación por canal > perfil activo > preferencias de usuario > este
fichero. Un umbral cableado en el código es una opinión disfrazada de física. Hay
una prueba deliberadamente literal —`test_el_generador_no_contiene_umbrales_
cableados`— que busca los números antiguos en el texto del generador, porque un
umbral cableado no rompe ninguna prueba funcional: el fixture sigue siendo
coherente consigo mismo y lo único que lo detecta es buscarlo.

**4. La clase de conversión es obligatoria.** `Clase.PUNTO`, `INTERVALO`, `TASA` o
`VARIANZA`, sin valor por omisión y solo por nombre. Es lo que evita que un Δ de
10 K se convierta en −263,15 °C. Hay una prueba que inspecciona la firma real de
las funciones para comprobar que nadie ha añadido un valor por omisión «por
comodidad»: ese es exactamente el camino por el que volvería el defecto.

**5. Nada en `samples/real/` se toca.** Son los tres logs del propietario y son la
evidencia de la que sale toda la ingeniería inversa del formato. Los ficheros
sintéticos y corruptos de `samples/synth/`, `samples/corrupt/` y
`samples/verdad/` se regeneran con las herramientas de `tools/`; los reales, no se
regeneran de ninguna manera.

**6. `state/PROGRESO.md` no se edita a mano.** Lo genera `tools/estado.py`. Toda
transición de estado pasa por esa herramienta, y una tarea con puerta G1 no la
cierra un modelo: pasa a `revision_humana` y espera a `estado.py aprobar`.

## 9.8 Lo primero que conviene hacer en local

**Desbloquear F0-01.** Es la tarea que confirma o refuta la viabilidad de la base
Python, está bloqueada desde el arranque por la política de red del contenedor
remoto, y es la única de las 136 que no puede avanzar de ninguna otra manera:

```bash
uv sync --all-packages
python tools/banco.py spike-polars      # mide sobre samples/synth/autolog-1h.csv
python tools/banco.py presupuestos      # 13 de 14 estaban NO_MEDIBLE
python tools/estado.py show F0-01
```

El presupuesto que decide es **`parseo_nativo` ≥ 100 MB/s agregado**
(`docs/02` §2.6). Si Polars lo cumple sobre el sintético de una hora, la base
Python está confirmada y el resto del plan procede tal como está escrito. Si no lo
cumple, **no ajustes el presupuesto para que pase**: es el riesgo R9 de
`docs/02` §2.8, y lo que toca es medir dónde se va el tiempo y escribirlo, porque
esa medición cambia decisiones de arquitectura y esas decisiones son del
propietario.

Cuando F0-01 esté medido y aprobado, el camino natural es F1-02 (parseo del cuerpo
con Polars), F1-03, F1-05 (almacén columnar) y F1-09 (pirámide de decimación): la
cadena que sostiene todos los presupuestos de rendimiento y que en remoto no se
podía ni empezar.

## 9.9 Aprobar puertas G1

Estas son del propietario, no del modelo. Lo que hace el modelo es **dejarle claro
qué tiene que mirar**: no «revisa el commit», sino qué números concretos y por qué
importan.

```bash
python tools/estado.py show F1-04                      # la nota dice qué revisar
python tools/estado.py aprobar F1-04 --nota "política de reloj verificada"
```

Al escribir la lista de revisión, ordénala por consecuencia si el número está mal,
no por orden de aparición en el diff. Un factor de escala equivocado en
`formats/haltech_nsp.toml` llega a una decisión de mapa; una etiqueta mal escrita
no. Las notas de las tareas ya cerradas siguen ese criterio y sirven de modelo.

Al cierre de la última sesión remota había **ocho puertas G1 esperando, 40 puntos**
(F0-07, F0-09, F0-10, F0-13, F1-01, F1-04, F1-13, F1-20). `state/PROGRESO.md`
tiene la lista viva con la última nota de cada una.

### Antes de pedir una revisión: reducirla

Pedir «revisa estos 92 números» es trasladar el trabajo, no hacerlo. La cola de
G1 llegó a 20 puertas porque cada tarea de datos añadía sus afirmaciones a un
montón indiferenciado, y un montón indiferenciado no se revisa: se posterga.

El orden de preferencia, de arriba abajo. **No se sube un escalón sin haber
agotado el de encima**:

1. **Derivar.** Si el número es una definición, no se revisa: se calcula y se
   compara. `data/definiciones_de_unidades.toml` (F1-46) declara de qué
   constantes exactas citadas sale cada factor de `units.toml`, y
   `test_definiciones_de_unidades.py` ejecuta la cuenta. Eso bajó `units.toml` de
   37 factores «solo tu criterio» a **uno**. Al añadir una unidad nueva, la
   prueba de cobertura exige derivarla o excluirla con un motivo, así que la
   cobertura no puede degradarse sin ponerse en rojo.
2. **Contrastar con el dato real.** Si el número no es una definición pero el log
   lo contradice cuando está mal, la comprobación es contra el log. Es lo que
   hace `confianza = "confirmed"` en `data/haltech_tipos.toml` («DisplayMaxMin
   4731,2331 = 473,1 K»), y lo que automatiza **FG-10** contra los rangos
   plausibles de `roles.toml`.
3. **Enseñar la consecuencia, no el dato.** `python tools/revisar.py` genera las
   afirmaciones físicas **ejecutando** el motor de conversión: si el factor de
   psi estuviera mal, la línea sale visiblemente mal («1 bar = 12,3 psi») sin
   abrir ningún TOML. Leer el número del fichero y volver a imprimirlo no
   comprueba nada.
4. **Preguntar.** Lo que sobrevive a los tres pasos anteriores son preguntas de
   dominio: «¿un consumo instantáneo de 47 L/100 km en ese canal es plausible?».
   Se hacen **contables y contestables en prosa**, nunca como un diff.

```bash
python tools/revisar.py                # el informe entero
python tools/revisar.py --solo-dudosas # solo lo que nadie respalda todavía
```

La última línea del informe es la única cifra que importa: cuántas afirmaciones
dependen solo del criterio del propietario. Si una tarea de datos la sube, la
tarea no está terminada.

### Lo que no se puede delegar

Un modelo puede derivar, contrastar y reducir. Lo que no puede es **decidir**: qué
`hp` quiere el propietario, si 14,7 es la estequiometría del combustible que usa,
si el factor deducido de un canal ajeno es el correcto. Esa frontera es la razón
de la regla, y no la mueve el hecho de que la cola sea larga. Si el propietario
delega explícitamente una aprobación, se registra **quién la delegó** en la nota
de `aprobar`, para que se pueda deshacer sabiendo qué se dio por bueno y con qué
respaldo.

## 9.10 Trampas ya pagadas

No las vuelvas a pagar. Todas salieron de este proyecto y cada una costó al menos
una ronda.

| Trampa | Qué pasó | Qué hacer |
|---|---|---|
| Leer la salida de `ruff` a ojo | «No fixes available…» sale *después* de «Found N errors»; dos commits salieron en rojo | `bash tools/verificar.sh`, códigos de salida |
| Fiarse del informe de un agente | Decía verde, y era verdad, pero `pytest` solo recogía 4 pruebas: `testpaths` no incluía `tests/` de la raíz | mirar los números, no la conclusión |
| Sustitución de texto exacta | `replace` de tres umbrales falló en silencio porque `ruff format` había realineado los comentarios | comprobar con una prueba que el número ya no está |
| Contar puntos a mano | Salieron 332 donde había 479 | calcular totales con un guion |
| Detector de patrones por regex | El detector de ADR-009 se marcaba a sí mismo: sus docstrings citan `iterrows()` para prohibirlo | AST, y una prueba negativa que inyecte una infracción real |
| `read_text()` con CRLF | Traduce CRLF a LF, así que partir por `\r\n` no encontraba nada | `open(..., newline="")` |
| Fixture que no cambia nada | «Convertir a CRLF» produjo un fichero idéntico: el log real ya es CRLF (557 CRLF, 0 LF sueltos) | comprobar que el fixture difiere del original |
| Anotar sin comprobar | Los eventos de knock del fixture estaban a 2 674 rpm, así que la severidad «crítica» anotada (exige > 4 000 rpm) era falsa | que el fixture verifique sus propias anotaciones |
| Desplazamientos relativos a bytes distintos | `offset_datos` era relativo a los bytes sin BOM, así que `datos[offset:]` fallaba por 3 bytes en silencio | que el contrato no obligue a recordar nada |

## 9.11 Qué no hacer sin preguntar

- **Cambiar un presupuesto de `docs/02` §2.6 para que pase.** Un presupuesto que
  se ajusta a lo medido no es una puerta, es un adorno.
- **Rellenar un `confianza = "unknown"`** de `formats/haltech_nsp.toml` con un
  valor plausible. Son 7 tipos sin escala deducible con las muestras
  disponibles; se muestran en crudo y sin unidad a propósito (mitigación de R1).
  Confirmarlos es la tarea F1-38 y exige evidencia, no verosimilitud.
- **Cambiar un umbral por omisión** de `data/umbrales.toml`. Configurable no
  significa arbitrario: el valor por omisión es una recomendación con la firma del
  propietario detrás.
- **Aprobar una puerta G1.** Ni siquiera cuando el trabajo es obviamente
  correcto: el sentido de la puerta es que lo mire una persona.
- **Reescribir la historia de la rama** (`rebase`, `push --force`) mientras haya
  otra vía de trabajo abierta sobre ella.
- **Meter una dependencia nueva** en `pyproject.toml`. Cada una entra en el ZIP
  portable, y el tamaño del paquete es un requisito declarado (§3.10). Se evitó
  PyArrow a propósito, y son ~100 MB.

## 9.12 Texto para empezar una sesión local

Este es el texto que el propietario pega al abrir la sesión. Lleva a propósito
más de lo estrictamente necesario —el modelo va a leer `CLAUDE.md` de todas
formas— porque las tres cosas que no puede deducir del repositorio son **qué hacer
primero**, **qué no hacer sin preguntar** y **cómo informar**.

Las cifras de «dónde está el proyecto» envejecen. Si no cuadran con
`tools/estado.py next`, gana `estado.py`: el estado vive en el repositorio y este
párrafo es solo para orientar antes de la primera orden.

```
Continúa el desarrollo de DataLogViewer en esta máquina.
Rama de trabajo: claude/log-visualization-app-plan-5lhr8x

Antes de tocar nada, lee en este orden:
  1. CLAUDE.md                                      una página: reglas y verificación
  2. docs/09-instrucciones-para-modelos-locales.md  qué cambia al ejecutar en local
  3. docs/08-ejecucion-y-reanudacion.md §8.4        el bucle de trabajo

Luego ejecuta esto y dime qué sale ANTES de empezar ninguna tarea:

    git status && git log --oneline -5
    uv sync --all-packages          (si no tienes uv: https://docs.astral.sh/uv/)
    python tools/verificar.py
    python tools/estado.py next

DÓNDE ESTÁ EL PROYECTO
136 tareas, 698 puntos, ~190 hechos. Se arrancó en un contenedor remoto SIN
acceso a PyPI, así que hay una asimetría que explica todo lo demás: está hecho lo
que no necesitaba dependencias —catálogos de datos, motor de unidades, parser de
cabecera, reconciliación de reloj, la cadena entera del importador genérico— y
está a medias lo que sí. La mayoría de los presupuestos de rendimiento siguen sin
medir, porque medirlos exige Polars y NumPy instalados. Eso es justo lo que tú
tienes y el contenedor no.

TU PRIMERA TAREA: CERRAR LAS CUATRO TAREAS QUE SOLO LES FALTA VERIFICACIÓN
    python tools/estado.py next        # las lista como EN CURSO

Hay cuatro tareas con el código completo y revisado que NO se pudieron cerrar en
remoto por falta de entorno, no por falta de trabajo. Cada una lleva en su nota
qué está verificado y qué falta exactamente. Léelas con `estado.py show <id>`.

Empieza por ejecutar `python tools/verificar.py` entero, con las seis
comprobaciones en verde de verdad. Si alguna se cae, arréglalo antes de nada:
significa que algo que en remoto no se podía ejecutar está roto.

Presta atención especial a la malla (F4-01): sus pruebas usan una implementación
del protocolo `Vectorial` hecha con biblioteca estándar, y ya se demostró que ESA
implementación puede esconder una diferencia con NumPy. Un canal con huecos daba
un resultado distinto con `numpy.min` que con el `min` de la biblioteca estándar.
Está arreglado, pero la pasada con NumPy de verdad no es una formalidad.

Cuando las cuatro estén cerradas, sigue el bucle de §8.4 con `estado.py next`. El
camino natural es la cadena de rendimiento: F1-02, F1-05 y F1-09.

REGLAS QUE NO SE SALTAN  (el motivo de cada una, en docs/09 §9.7)
  - ADR-009: cero bucles por muestra en Python. Polars o NumPy hacen el trabajo;
    si algo no se puede vectorizar, va a Numba, nunca a un `for`.
  - data/*.toml son datos, no código. No traslades sus valores al código ni
    reformatees los ficheros: los comentarios son lo que hace revisable la G1.
  - samples/real/ no se toca. Son mis tres logs y la evidencia de todo el formato.
  - state/PROGRESO.md se genera. Toda transición pasa por tools/estado.py.
  - Una puerta G1 no la cierras tú: la dejas en `revision_humana` con una nota que
    diga qué tengo que revisar, ordenada por consecuencia si el número está mal.
  - `python tools/verificar.py` en verde antes de cada commit, las seis
    comprobaciones. No ejecutes las herramientas a mano en su lugar.
  - Si un agente te entrega trabajo, su informe NO es evidencia: revísalo tú antes
    de integrarlo. En remoto salieron defectos reales en los cuatro entregables de
    agente, incluido uno donde la función principal era inalcanzable.

NO HAGAS NADA DE ESTO SIN PREGUNTARME
Ajustar un presupuesto para que pase; rellenar un `confianza = "unknown"` de
data/formats/haltech_nsp.toml con un valor plausible; cambiar un umbral por
omisión de data/umbrales.toml; añadir una dependencia a pyproject.toml;
reescribir la historia de la rama.

CÓMO QUIERO QUE ME INFORMES
Al terminar cada tarea: qué quedó hecho, qué no, y qué necesitas de mí, en dos o
tres líneas. Si es G1, dime exactamente qué números tengo que revisar y por qué
importan. Hay unas dos docenas de puertas G1 esperando (más de 130 pts, listadas
en state/PROGRESO.md); no bloquean a sus dependientes, así que sigue trabajando,
pero si te estorban sin aprobar, pídemelas por orden de cuántas desbloquean.
```

Lo demás no hace falta ponerlo: el protocolo, el estado y las especificaciones
están en el repositorio, que es justamente el motivo de que estén ahí y no en una
conversación.
