# 11 — Despliegue de la versión navegador (F5-06)

Este documento cubre E10.2 (`docs/02` §2.4 y línea 147): el mismo `dlv-ui` que
corre dentro de `dlv-app` (pywebview) servido en un navegador normal, contra un
`dlv-api` que puede estar en la misma máquina o en otro equipo de la red del
taller.

**No es una guía de "cómo abrir la aplicación en el navegador de esta
máquina"** — eso ya funciona hoy sin nada de lo que sigue: `npm run preview`
sirve `dist/` en `127.0.0.1` y `dlv-api` ya escucha ahí (ADR-007). Esto cubre
el caso nuevo: otro equipo de la red pidiendo `dlv-ui` por HTTP y hablando con
un `dlv-api` que no es el suyo.

## 11.1 Qué hay que ejecutar

En el equipo que hace de servidor (el que tiene los logs y `dlv-api`):

```bash
# 1. Construir dlv-ui una vez (genera dlv-ui/dist/)
cd dlv-ui && npm run build

# 2. Arrancar dlv-api escuchando en la interfaz de red, no solo en loopback.
#    `preparar_servidor`/`servir` de dlv_api.main YA aceptan `host` como
#    parámetro (dlv-api/src/dlv_api/main.py, `servir(host=...)`); no hace
#    falta tocar el código, solo invocarlo con el host correcto en vez de con
#    el valor por omisión "127.0.0.1". Sustituye 192.168.1.50 por la IP real
#    de la máquina en la red del taller.
uv run python -c "from dlv_api.main import servir; servir(host='192.168.1.50')"
# -> imprime el puerto efímero y el token de sesión (ver §11.3)

# 3. Servir dist/ para la red, en otra terminal
cd dlv-ui && npm run preview:red
# -> "vite preview --host 0.0.0.0", puerto por omisión 4173
```

En el navegador del OTRO equipo de la red:

```
http://192.168.1.50:4173/?puerto_api=<puerto-del-paso-2>&token=<token-del-paso-2>&log=<ruta-del-log-EN-EL-SERVIDOR>
```

Los tres parámetros son el mismo contrato que ya usa `dlv-app` para pasarle
credenciales a `dlv-ui` por la URL (`dlv-app/src/dlv_app/main.py`,
`_url_con_credenciales`; `dlv-ui/src/main.ts`, `elegirFuente`): no se ha
inventado un mecanismo nuevo, se reutiliza el que ya existía para el
contenedor de escritorio.

## 11.2 El fallo que esto arregla en `dlv-ui`, y el que no arregla

**Arreglado en este cambio.** `dlv-ui/src/main.ts` construía la URL de la API
como `` `http://127.0.0.1:${puerto}` `` sin mirar nunca desde qué host se
había cargado la propia página. Es invisible en `dlv-app` y en `npm run dev`
porque en los dos casos el host real ya es loopback, pero en el paso del
navegador de arriba es exactamente el error: la página se sirve desde
`192.168.1.50`, pero el código seguía intentando hablar con `127.0.0.1` — que
desde el navegador del OTRO equipo es ese otro equipo, no el servidor. La
petición no llegaba a ningún sitio con `dlv-api` escuchando, y el síntoma en
pantalla era «no se pudo abrir el log», sin ninguna pista de que la causa era
la URL y no el fichero.

La corrección (`dlv-ui/src/datos/resolver-api.ts`, `resolverUrlBaseApi`) usa
`window.location.hostname` — el host desde el que se cargó la página — salvo
que la URL traiga `?api_host=` explícito (para cuando `dlv-api` vive detrás de
un proxy con un nombre distinto al del servidor estático). Para `dlv-app` y
`npm run dev` el comportamiento no cambia: ahí `location.hostname` ya era
`127.0.0.1` o `localhost`, así que la URL resultante es la misma que antes.
Pruebas: `dlv-ui/src/datos/resolver-api.test.ts`. Verificado con
`node --experimental-transform-types` sobre la función pura, con los seis
casos del test (127.0.0.1, localhost, IP de red, `api_host` explícito,
`api_host` vacío, host de página vacío) — ver el informe de la tarea para la
salida exacta; no se ha podido ejecutar con `vitest` porque no hay
`node_modules` en este entorno (§11.6).

**NO arreglado, y no es un defecto de `dlv-ui`: es CORS en `dlv-api`.**
`dlv-api/src/dlv_api/main.py`, función `crear_app`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
    ...
)
```

Esa expresión acepta únicamente orígenes en loopback. Un navegador que cargó
`dlv-ui` desde `http://192.168.1.50:4173/` y pide datos a
`http://192.168.1.50:<puerto_api>` manda ese origen en el preflight `OPTIONS`,
y `CORSMiddleware` lo rechaza **antes de que el token se compruebe siquiera**:
la petición real nunca sale del navegador. Arreglar `resolver-api.ts` deja la
URL apuntando al sitio correcto, pero sin cambiar esta expresión regular el
navegador del otro equipo seguirá sin poder hablar con `dlv-api`.

Esto **no lo resuelvo yo**: `dlv-api/src/dlv_api/main.py` no es de mi carril
en esta tarea (F5-06 es despliegue de `dlv-ui`, no comandos de `dlv-api`), y
sobre todo porque decidir CUÁNDO un origen de red deja de ser sospechoso es
exactamente la decisión de seguridad que las instrucciones de esta tarea piden
no tomar por mi cuenta. Lo que hace falta, para que el propietario lo decida
(§11.3 explica el porqué de cada opción):

- Un origen concreto y configurable (p. ej. una variable de entorno con la IP
  o el nombre del equipo servidor), no `allow_origins=["*"]``: abrir CORS a
  cualquier origen quita la única frontera que queda una vez que el HTTP ya no
  es loopback.
- Mantener el token obligatorio en todas las rutas que ya lo exigen — CORS
  decide QUIÉN puede preguntar, no si hace falta credencial para la respuesta.

## 11.3 Inventario real del token y de CORS (leído de `dlv-api/src/dlv_api/main.py`)

Esto es lo que el código hace HOY, línea por línea, no un resumen de memoria:

**Token de sesión** (`generar_token_sesion`, `verificar_token`, líneas
219-242):
- `secrets.token_urlsafe(32)`, uno por arranque del proceso, guardado en
  `app.state.token_sesion`.
- Se exige como `Authorization: Bearer <token>` vía
  `dependencies=[Depends(verificar_token)]` en **todas** las rutas de
  `/comandos/*` — las trece que registra `crear_app` (líneas 1338-1422):
  `abrir-cabecera`, `serie`, `abrir-log`, `cubos`, `sesiones`, `cerrar-log`,
  `unidades`, `exportar-datos`, `sondear-formato`, `sondear-tiempo`,
  `sondear-canales`, `roles`.
- La única ruta sin token es `/salud` (`app.add_api_route("/salud", ...)`,
  sin `dependencies`), documentado como deliberado: es lo que un lanzador
  usa para saber si el servidor ya está listo, antes de haber leído el
  token.
- Comparación con `==` (no `secrets.compare_digest`) en `verificar_token`.
  Dentro de 127.0.0.1 esto nunca importaba; en una red no es un ataque de
  temporización *práctico* sobre HTTP con la varianza de una LAN normal, pero
  tampoco es la comparación que se recomienda para secretos que cruzan una
  red, y es exactamente el tipo de detalle que cambia de irrelevante a
  discutible en cuanto ADR-007 deja de ser "solo localhost". Lo señalo, no lo
  cambio: es código de `dlv-api`, fuera de mi carril.

**CORS** (`crear_app`, líneas 1321-1327):
- `allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$"` — solo
  loopback, cualquier puerto. Ver §11.2 para la consecuencia práctica.
- `allow_methods=["*"]`, `allow_headers=["*"]`.
- `expose_headers=[*CABECERAS_EXPUESTAS, "Content-Disposition"]` — las diez
  cabeceras `X-*` que el transporte binario necesita (`X-Factor`, `X-Nivel`,
  `X-T-Origen`, `X-Cubos`, `X-Indice-Inicio`, `X-Dimension`, `X-Storage`,
  `X-Factor-A`, `X-Factor-B`, `X-Muestras`) más `Content-Disposition` para la
  exportación (F4-12). Esta parte no depende de dónde esté el navegador: sigue
  haciendo falta igual en loopback que en red, y no cambia con el despliegue.

**Transporte** (ADR-007, sin cambios): las series nunca van en JSON.
`/comandos/serie` y `/comandos/cubos` devuelven Arrow IPC o un búfer crudo
`float32`; JSON queda para catálogos y metadatos (kilobytes). Nada de esto
depende de si el cliente es local o de red — es una propiedad del formato de
respuesta, no del transporte de red.

**Host de escucha de `dlv-api`** (`preparar_servidor`, `servir`, líneas
1455-1485): el parámetro `host` ya existe y por omisión es `"127.0.0.1"`.
`dlv-app` lo llama con `HOST_LOCAL` (loopback, sin cambios: sigue siendo
correcto para el contenedor de escritorio). Para este despliegue basta con
invocar `servir(host=<ip-del-servidor>)` como en §11.1 — no hace falta
modificar `dlv_api/main.py` para eso, el parámetro ya está.

## 11.4 Qué cambia en el manejo de rutas de log

Hoy `dlv-api` no recibe nunca los BYTES de un fichero desde el cliente: recibe
una **ruta absoluta** (`ComandoAbrirLog.ruta`, `ComandoSerie.ruta`,
`ComandoAbrirCabecera.ruta`, y las tres del sondeo genérico) y es el propio
proceso de `dlv-api` el que hace `Path(ruta).is_file()` / `.read_bytes()`
sobre el disco en el que corre (`dlv-api` sí toca el sistema de ficheros, a
diferencia de `dlv-core`, ADR-002). No existe ningún `<input type="file">` ni
selector nativo en `dlv-ui` hoy: la única forma de decirle a la aplicación qué
log abrir es la query string `?log=<ruta>` que pone `dlv-app` al arrancar la
ventana (`dlv-ui/src/main.ts`, `elegirFuente`), y el asistente de importación
trata esa misma cadena como una "referencia opaca" (`dlv-ui/src/importacion/
asistente-importacion.ts`).

Eso funciona en escritorio porque la ruta que escribe el usuario y la ruta que
lee `dlv-api` son la MISMA ruta en el MISMO disco. Deja de serlo en cuanto el
navegador está en otro equipo:

- La ruta que hay que poner en `?log=` es la ruta **en el servidor**, no en el
  equipo desde el que se abre el navegador. Un técnico del taller que ve el
  fichero en su propio escritorio no puede simplemente "elegirlo": tiene que
  saber (o que alguien le diga) dónde vive ese mismo fichero en el equipo que
  corre `dlv-api` — típicamente porque ya lo copió ahí, o porque hay una
  carpeta compartida montada con la misma ruta en los dos sitios.
- No hay ningún mecanismo de subida (`multipart/form-data`, o cualquier otro)
  que traslade el fichero del equipo del técnico al servidor. Añadir uno sería
  la forma natural de resolver esto de cara al usuario, pero es un endpoint
  nuevo de `dlv-api` (fuera de mi carril en F5-06, que es despliegue de
  `dlv-ui`) y, sobre todo, sería exactamente el tipo de "solución de
  seguridad" que las instrucciones de esta tarea piden no inventar por mi
  cuenta: quién puede escribir en el disco del servidor desde la red es una
  decisión tan del propietario como la de CORS.
- Consecuencia de seguridad, no solo de usabilidad: como `ruta` no está
  acotada a ninguna carpeta de logs — `Path(comando.ruta)` acepta cualquier
  ruta absoluta que el proceso de `dlv-api` pueda leer, y `leer_muestra`
  (`dlv-api/src/dlv_api/importacion.py`) lo dice explícitamente en su
  docstring: *"Un fichero que el usuario elige es una entrada no confiable"* —
  quien tenga el token puede pedir la cabecera, el sondeo o la serie de
  CUALQUIER fichero legible por ese proceso, no solo de los logs del
  propietario. En localhost esto es irrelevante (quien puede hablar con
  `dlv-api` ya tiene el mismo acceso al disco que el propio proceso). En red,
  con solo un token robado o filtrado, deja de serlo: es lectura arbitraria de
  ficheros del servidor, acotada por los permisos del proceso, no por ninguna
  lista de "logs permitidos". `/comandos/sondear-formato` en concreto devuelve
  las primeras líneas EN CRUDO de lo que sea que apunte `ruta` — no hace falta
  que el fichero sea un log de Haltech para que el servidor conteste algo.

## 11.5 Qué garantías pierde este despliegue y cuáles no

Para que el propietario decida con qué desplegar en su taller, no como
recomendación cerrada:

**Se mantienen, sin cambios, en este despliegue:**
- El transporte binario de las series (ADR-007): nada de esto se relaja para
  la red, y el navegador remoto sigue recibiendo Arrow IPC / `TypedArray`, no
  JSON con 73 M de floats.
- El token sigue siendo obligatorio en cada ruta de `/comandos/*` salvo
  `/salud`, tal como hoy.
- `samples/real/` sigue sin ser accesible por HTTP en ningún caso que yo haya
  comprobado: ni `dlv-api` monta ningún directorio estático (solo define
  rutas de API, `crear_app` no llama a `StaticFiles` en ningún punto de
  `main.py`), ni el servidor estático de `dlv-app`
  (`iniciar_ui_estatica_en_hilo`, `dlv-app/src/dlv_app/main.py`) sirve nada
  que no sea el directorio `dlv-ui/dist` que se le pasa explícitamente — nunca
  la raíz del repositorio. Esto es cierto independientemente del despliegue:
  no depende de si `dlv-api` escucha en loopback o en la red.

**Se pierden o se debilitan, y el motivo concreto:**
- **El token deja de estar protegido por "el atacante tiene que ser un
  proceso de esta misma máquina".** ADR-007 lo dice explícitamente: pensado
  para 127.0.0.1, donde el modelo de amenaza es un proceso local ajeno. En la
  red de un taller, cualquier equipo que vea ese tráfico (Wi-Fi abierta, un
  switch mal segmentado, otro puesto de la misma VLAN) puede leerlo, porque
  viaja en texto claro: `dlv-api` no sirve HTTPS (no hay TLS en ningún punto
  de `main.py`), así que la cabecera `Authorization: Bearer <token>` cruza la
  red sin cifrar.
- **El token viaja además en la URL** (`?token=...`), no solo en la cabecera
  `Authorization` — es el mismo contrato que ya usa `dlv-app` y que su propio
  código documenta como riesgo aceptado (`dlv-app/src/dlv_app/main.py`,
  sección "Donde va el token"): queda en el historial del navegador, en logs
  de proxies intermedios si los hay, y visible en capturas de pantalla. En
  escritorio ese riesgo se mitigaba porque la URL nunca salía de la propia
  máquina; en un navegador de red, un proxy HTTP intermedio (si el taller
  tuviera uno) vería ese token en sus propios registros.
- **Cualquiera con el token puede pedir a `dlv-api` que lea cualquier fichero
  del disco del servidor que el proceso pueda abrir**, no solo logs del
  propietario (§11.4). Esta garantía nunca existió — ni en escritorio: es una
  propiedad de cómo `dlv-api` maneja `ruta` hoy — pero en localhost el
  "atacante" ya tenía ese mismo acceso por definición (es el mismo usuario en
  la misma máquina), y en red deja de ser así.
- **CORS, tal como está hoy, en la práctica IMPIDE el despliegue en red**
  (§11.2): no es una garantía que se pierda, es un bloqueo que hay que
  resolver con una decisión del propietario antes de que esto funcione de
  extremo a extremo contra otro equipo.

**Recomendación, con esas palabras exactas:** esto solo debería exponerse en
una red de confianza (la VLAN del taller, no una Wi-Fi de invitados ni
Internet) y con el token obligatorio como está hoy — nunca desactivado para
"simplificar" el despliegue. Si el propietario quiere endurecerlo más allá de
eso, las dos palancas que señala este documento y que no he movido yo son
CORS (§11.2) y la ausencia de un directorio de logs acotado en `dlv-api`
(§11.4); las dos son decisiones suyas.

## 11.6 Qué se ha ejecutado y qué no

Este entorno no tiene `node_modules` en `dlv-ui/` (`npm install` da 403) ni
`fastapi` instalado, así que **no se ha podido**:
- Construir `dlv-ui` de verdad (`npm run build`) ni arrancar
  `npm run preview:red`.
- Arrancar `dlv-api` (`uv run python -c "from dlv_api.main import servir; ..."`)
  ni comprobar en un navegador real si el preflight CORS se rechaza como dice
  §11.2.
- Ejecutar `dlv-ui/src/datos/resolver-api.test.ts` con `vitest` (`npm test`
  falla por falta de `node_modules`, igual que el resto de la suite: es el
  mismo estado que ya describe `docs/09` §9.10 para este entorno).

**Sí se ha ejecutado**, con el `tsc` global de este contenedor y con
`node --experimental-transform-types`:
- `tsc --noEmit -p dlv-ui/tsconfig.json`: los únicos errores son los ya
  existentes en todo el repositorio por falta de `node_modules`
  (`Cannot find module 'vitest'` / `'vite'` en cada fichero de prueba y en los
  tres `vite*.config.ts`) más un error preexistente y ajeno a esta tarea en
  `dlv-ui/src/incidencias/orden.ts`. Ni `resolver-api.ts` ni `main.ts`
  aparecen en la lista de errores.
- La función pura `resolverUrlBaseApi` de `resolver-api.ts`, con
  `node --experimental-transform-types --input-type=module`, contra los seis
  casos que también cubre `resolver-api.test.ts` (127.0.0.1, localhost, IP de
  red, `api_host` explícito, `api_host` vacío, host de página vacío): los seis
  dan el resultado esperado.

**Para probarlo de punta a punta hace falta, en orden:**
1. `npm install` en `dlv-ui/` (bloqueado en este entorno, no en el del
   propietario) y `uv sync --all-packages` con `fastapi` disponible.
2. Dos máquinas reales (o dos espacios de red distintos) en la misma LAN, para
   que "el navegador de otro equipo" no sea localhost disfrazado.
3. Decidir §11.2 (CORS) antes del paso 2, porque sin eso la petición real
   nunca sale del navegador y no hay nada que observar salvo el rechazo del
   preflight.
4. Con eso resuelto: seguir §11.1 tal cual y comprobar en las herramientas de
   red del navegador del segundo equipo que `/comandos/abrir-log` responde
   200 y que `X-Cubos` llega con un número mayor que cero en la respuesta de
   `/comandos/cubos` — es la comprobación mínima de que el transporte binario
   sigue funcionando fuera de loopback.
