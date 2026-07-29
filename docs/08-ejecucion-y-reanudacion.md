# 08 — Protocolo de ejecución y reanudación

## 8.1 El problema que resuelve este documento

El plan son 136 tareas y 25 semanas. Ninguna sesión de trabajo asistido llega tan
lejos: el límite de uso se agota, la sesión se cierra, el contenedor se recicla.

**Por tanto el estado no puede vivir en la conversación.** Vive en el repositorio,
y cualquier sesión nueva puede reconstruir en un minuto qué está hecho, qué está a
medias y qué toca ahora.

## 8.2 Invariantes

Seis reglas. Si se cumplen, el trabajo es siempre reanudable.

1. **El estado está en `state/tareas.json`**, versionado. La conversación es
   desechable.
2. **Una tarea = un commit** (o varios, pero ninguno a medias). No se termina un
   turno con trabajo sin commitear.
3. **Se hace `push` al terminar cada tarea**, no al final de la jornada. El
   contenedor es efímero; lo que no está en `origin` no existe.
4. **Toda transición de estado pasa por `tools/estado.py`**, que regenera
   `state/PROGRESO.md`. Nunca se edita el progreso a mano.
5. **Una tarea con puerta G1 no la cierra un modelo.** Pasa a `revision_humana` y
   espera a que el propietario ejecute `estado.py aprobar`.
6. **El trabajo de un agente se commitea en cuanto aparece en el árbol, no al
   integrarlo.** Commitear no es cerrar la tarea: un commit `WIP <ID>` con la
   tarea aún en `en_curso` protege el trabajo de que se recicle el contenedor y
   deja escrito qué falta. Esta regla se añadió tras perder por poco el
   andamiaje de F0-02, que estuvo más de quince minutos solo en el árbol local.

## 8.3 Reanudar en una sesión nueva

Pegar esto:

```
Retoma la ejecución del plan de DataLogViewer en la rama
claude/log-visualization-app-plan-5lhr8x.

Lee docs/08-ejecucion-y-reanudacion.md y sigue el bucle de la sección 8.4.
Empieza ejecutando `python tools/estado.py next`.
```

No hace falta más contexto: el protocolo, el estado y las especificaciones están
en el repositorio.

## 8.4 Bucle de orquestación

```
1. git pull origin claude/log-visualization-app-plan-5lhr8x
2. python tools/estado.py next
3. ¿Hay tareas en_curso?
      → Sí: reconstruir con `git status` y `git log` qué quedó a medias.
             Terminarlas o marcarlas `block` con motivo. No empezar nada nuevo.
      → No: seguir.
4. Elegir la primera tarea lista. Respetar el modelo asignado (§8.5).
5. python tools/estado.py start <ID> --agente <opus|sonnet|haiku>
6. Ejecutar la tarea con el contexto de §8.6.
7. Verificar: pruebas verdes y presupuestos afectados en verde.
8. git add -A && git commit   (mensaje: "<ID> — <título>")
9. python tools/estado.py done <ID> --nota "<qué quedó hecho y qué no>"
10. git add -A && git commit --amend --no-edit   (para incluir el estado)
11. git push -u origin claude/log-visualization-app-plan-5lhr8x
12. Volver a 2.
```

El paso 9 antes del 10 es deliberado: así el commit de la tarea y su registro de
estado son el mismo commit, y el historial de git y `tareas.json` no pueden
divergir.

### Si el límite se agota a media tarea

No pasa nada, siempre que se haya cumplido la regla 2. La sesión siguiente ve la
tarea en `en_curso`, mira `git log` y `git status`, y decide si continuar o
reiniciarla. Por eso el paso 3 va antes que cualquier otra cosa.

Ante la duda, es más barato **reiniciar una tarea** que heredar medio trabajo cuyo
razonamiento se ha perdido.

## 8.5 Asignación de agentes

El modelo de cada tarea está en la columna `Modelo` del backlog y en
`tareas.json`. Cómo se ejecuta cada uno:

| Modelo asignado | Cómo se ejecuta | Por qué |
|---|---|---|
| **Opus 5** | **el orquestador la hace en línea**, sin delegar | ya tiene el contexto cargado; delegar a un agente Opus lo obligaría a re-derivar la especificación y costaría más |
| **Sonnet 5** | agente en segundo plano con `model: sonnet` | trabajo de implementación con especificación cerrada; se paraleliza bien |
| **Haiku 4.5** | agente en segundo plano con `model: haiku` | mecánico y totalmente especificado |

Se pueden lanzar **hasta dos o tres agentes en paralelo**, y solo si sus tareas no
tocan los mismos ficheros. El libro de estado lo escribe **únicamente el
orquestador**: los agentes entregan código, nunca modifican `state/`. Es lo que
evita conflictos de fusión en el fichero más importante del repositorio.

## 8.6 Contexto que recibe cada agente

Un agente arranca en frío. El encargo debe llevar, siempre:

1. El **ID y el título** de la tarea, y su entregable.
2. Los **documentos concretos** que la especifican, por ruta y sección — nunca
   «lee la documentación».
3. Los **criterios de aceptación** verificables.
4. Los **ficheros que puede tocar** y los que no.
5. La instrucción de **no tocar `state/`** ni hacer commit: el orquestador
   integra, verifica y commitea.
6. Para cualquier tarea de `dlv-core`: **ADR-009** (cero bucles por muestra en
   Python) citado explícitamente.

## 8.7 Puertas de revisión en la práctica

| Puerta | Qué hace el orquestador | Estado resultante |
|---|---|---|
| **G1** | implementa o integra, verifica, commitea, y deja constancia de qué debe revisar la persona | `revision_humana` |
| **G2** | tras integrar, hace una pasada de revisión propia y registra los hallazgos en la nota | `hecho` |
| **G3** | ejecuta la verificación completa del repositorio (§8.10), no se fía del informe del agente | `hecho` |
| **G4** | comprueba que CI pasa | `hecho` |

Las tareas en `revision_humana` **no bloquean** a sus dependientes: el trabajo
sigue, pero `estado.py next` avisa de que se está construyendo sobre algo sin
aprobar. Si el propietario rechaza una G1, las tareas que dependían de ella se
revisan en cascada.

Para aprobar:

```bash
python tools/estado.py aprobar F0-08 --nota "escalas verificadas contra el log real"
```

## 8.8 Correcciones de dependencias del backlog

El backlog es un documento de planificación y tenía tres dependencias mal puestas.
Las correcciones viven en `DEPS_CORREGIDAS` dentro de `tools/estado.py`, con el
motivo, y `tareas.json` conserva la dependencia original en `deps_backlog` para
que la discrepancia sea auditable:

| Tarea | Backlog | Real | Motivo |
|---|---|---|---|
| `F0-01` | sin dependencias | `F0-05` | el *spike* de Polars necesita el log sintético de 1 h que produce F0-05 |
| `F0-02` | `F0-01` | sin dependencias | el andamiaje no necesita los ADR firmados: el stack ya está decidido en `03-arquitectura.md` rev. 2 |
| `F0-08` | `F0-01` | sin dependencias | el catálogo de unidades está especificado por completo en `06-sistema-de-unidades.md` §6.7 y no necesita el *spike* de Polars |

Además, la dependencia literal `todo` de las tareas de cierre (`F5-14`, `F5-15`,
`F5-16`) se modela con el campo `dep_todo`, que las mantiene fuera de
`estado.py next` hasta que el resto del plan está cerrado.

## 8.9 Órdenes del libro de estado

```bash
python tools/estado.py next                    # qué toca ahora
python tools/estado.py show F1-13              # detalle de una tarea en JSON
python tools/estado.py start F0-05 --agente sonnet
python tools/estado.py done  F0-05 --nota "generador y corpus; falta el de 1 h"
python tools/estado.py block F0-01 --nota "Polars no instalable sin red"
python tools/estado.py aprobar F0-08
python tools/estado.py render                  # regenera PROGRESO.md
python tools/estado.py seed                    # resiembra tras editar el backlog
```

## 8.10 Verificación completa del repositorio

Antes de cerrar cualquier tarea, y siempre sobre todo el repositorio, no solo
sobre lo tocado:

```bash
ruff check .          # lint
ruff format --check . # formato
mypy dlv-core dlv-api # tipado estricto
pytest -q             # pruebas
```

En un contenedor sin red no hay `pip`, pero `ruff`, `mypy` y `pytest` pueden
estar disponibles como binarios aislados en `~/.local/bin`. Si no lo están,
`python tools/pytest_minimo.py` ejecuta las pruebas con un `pytest` de sustitución.

**El informe de un agente no es evidencia.** Al integrar F0-02 el informe decía
—con razón— que todo estaba verde, y lo estaba; pero `pytest` solo recogía 4
pruebas, porque `testpaths` no incluía el `tests/` de la raíz y las 31 pruebas
del catálogo de unidades no se ejecutaban. Un informe correcto y una suite
incompleta son compatibles: hay que mirar los números, no leer la conclusión.

## 8.11 Órdenes útiles

`seed` sin `--forzar` **conserva el progreso** de las tareas que ya no están en
`pendiente`, así que se puede reajustar el backlog a mitad de proyecto sin perder
el estado.
