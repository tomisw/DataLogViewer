"""Segmentación automática del log en tramos reconocibles (tarea F3-16).

`docs/04-perfiles-motorsport.md` §4.4: «Sin segmentación, el usuario busca sus
tiradas a mano en un log de 40 minutos». Este módulo parte el log en tramos en
los que el motor está haciendo UNA cosa reconocible —arranque, plena carga
(WOT), deceleración, ralentí, crucero— para que el panel de tiradas (F3-17), los
filtros de exclusión (F4-03) y las métricas de PID de boost (F4-09) trabajen
sobre tramos y no sobre 73 millones de muestras indiferenciadas.

Es el primer consumidor de verdad de `primitivas.py` (F3-06): aquí no hay ni un
umbral aplicado a mano, ni una histéresis reimplementada, ni un autómata de
estado propio. Las cinco clases son composiciones de las nueve primitivas de
§4.3, y lo que este módulo añade es lo que ninguna primitiva puede saber: **qué
significa cada composición y quién gana cuando dos se pisan**.

LO QUE HACE DIFÍCIL ESTO, Y NO ES LA DETECCIÓN
===============================================
Detectar «TPS por encima del 80 %» es una llamada a `umbral_con_histeresis`. Lo
difícil son las otras tres cosas:

1. **Los segmentos no se solapan y ningún hueco queda sin explicar.** Un
   instante está en un segmento, o está fuera con un motivo escrito. Es un
   invariante comprobado, no una intención: `Cobertura` no se puede construir si
   las cuentas no suman las muestras de la rejilla, y `InformeDeSegmentacion`
   rechaza dos segmentos que se solapen en el tiempo. Sin esa aritmética, «el
   log está cubierto al 78 %» sería una frase sin forma de saber si es verdad.

2. **La precedencia se declara, no se hereda del orden de evaluación.** Dos
   definiciones SE PISAN de verdad, y no en un caso raro: la histéresis de «TPS
   cerrada» mantiene la deceleración activa mientras la mariposa se abre un 3 %,
   y ahí la banda de crucero ya está dentro. Si ganara la clase que se evalúa
   primero, el resultado dependería del orden de un bucle y cambiaría al
   reordenar el enumerado. Aquí gana la de mayor `prioridad`, y el orden está
   argumentado abajo con la consecuencia de equivocarse.

3. **La histéresis es lo que separa un segmento de un parpadeo.** Ni una de las
   cinco clases compara un canal con un número desnudo: todas pasan por
   `umbral_con_histeresis` o por `banda`, y todas pasan por la permanencia
   mínima de `eventos`. Una mariposa que oscila un 1 % alrededor del 80 % da UN
   segmento de WOT, no doce, y eso no es una propiedad de este módulo: es la de
   F3-06, usada en vez de reinventada.

LAS CINCO CLASES, POR ROL Y POR PRIMITIVA
==========================================
Todas se definen por **rol semántico** (ADR-008, `data/roles.toml`), nunca por
nombre de canal: los mismos cinco criterios valen en un log de Haltech, uno de
MoTeC o un CSV escrito a mano. Los dos roles que aparecen son
`engine_speed` (rpm) y `throttle_position` (fracción, no porcentaje: canónica de
`ratio`).

* **`ARRANQUE`** — §4.4: «RPM de 0 a > 500 con `Fuel Cranking` activo».
  `banda(régimen, [rpm_arranque_min, rpm_motor_en_marcha])`, y la permanencia
  mínima como único separador frente a un tirón de embrague.
* **`WOT`** — §4.4: «TPS > 80 % y RPM creciente durante > 1,5 s».
  `umbral_con_histeresis(mariposa, ARRIBA)` con permanencia de 1,5 s, más la
  pendiente media del régimen comprobada sobre la tirada entera.
* **`DECELERACION`** — §4.4: «`Decel Cut State` activo o TPS ≈ 0 con RPM > 2000».
  `umbral_con_histeresis(mariposa, ABAJO)` **y**
  `umbral_con_histeresis(régimen, ARRIBA)`, esta con la salida en el techo del
  ralentí.
* **`RALENTI`** — §4.4: «RPM en banda del objetivo de ralentí y TPS ≈ 0».
  `umbral_con_histeresis(mariposa, ABAJO)` **y**
  `banda(régimen, [rpm_motor_en_marcha, rpm_ralenti_max])`.
* **`CRUCERO`** — no está en §4.4; el porqué, más abajo.
  `banda(mariposa, [tps_cerrada, tps_wot])` **y** «motor en marcha» **y**
  `banda(derivada(régimen), ±rpm_estable_max_por_s)`.

Tres decisiones de esa tabla merecen su párrafo, porque las tres son sitios
donde una implementación descuidada pierde exactamente lo que el usuario venía a
buscar.

**El criterio de régimen creciente de WOT se aplica a la TIRADA, no a la
muestra.** Es la diferencia entre encontrar las tiradas y perderlas: en el
AutoLog real, la segunda tirada tiene tres muestras con la derivada del régimen
en −1 238 rpm/s —un cambio de marcha a mariposa abierta— y una condición por
muestra la partiría en dos trozos de 1,2 s y 0,6 s que la permanencia de 1,5 s
descartaría los dos. La tirada existe, dura 2,1 s y se perdería entera. Así que
la condición por muestra es solo la mariposa, y «RPM creciente durante > 1,5 s»
se comprueba sobre el segmento ya formado: régimen al final menos régimen al
principio, dividido por la duración, contra `rpm_creciente_min_por_s`. Eso
además rechaza lo que el criterio quiere rechazar de verdad —un mantenido a
plena carga en banco, con el régimen plano— que una condición por muestra
también rechazaría, pero por casualidad.

**La deceleración sale del régimen de entrada y ENTRA en la banda de ralentí al
salir.** `umbral_con_histeresis(régimen, entrada=rpm_decel_min,
salida=rpm_ralenti_max, ARRIBA)`: una retención de 6 000 rpm sigue siendo una
deceleración mientras el régimen cae, hasta que llega al techo del ralentí. Los
dos umbrales ya existen y no hay que declarar un tercero, y lo que se evita es
un hueco: con una salida en los mismos 2 000 rpm de la entrada, la parte de la
retención por debajo de 2 000 no sería deceleración (el régimen ya no supera el
umbral) ni ralentí (todavía está por encima de su banda), y quedaría sin clase.

**`ARRANQUE` se define con el régimen solo, y esto es una carencia del catálogo
de roles, no una elección.** §4.4 pide `Fuel Cranking`, y `data/roles.toml` no
declara ningún rol de arranque; tampoco declara `Decel Cut State`, que es la
otra mitad del criterio de deceleración. Sin ellos, lo observable es la
consecuencia: el motor gira por debajo del régimen en que se sostiene solo. Eso
confunde el arranque con un motor que se cala cruzando la banda hacia abajo, y
la permanencia mínima es lo único que lo separa de un tirón de embrague -- en el
AutoLog hay dos caídas de régimen a 412 y 471 rpm que duran 0,17 s y 0,15 s
dentro de la banda, así que `duracion_minima_s.arranque` las descarta con tres
veces de margen. Los dos roles que faltan están anotados en el informe de la
tarea: son una entrada de `data/roles.toml`, no un cambio de este módulo.

POR QUÉ CRUCERO Y NO CALENTAMIENTO
===================================
§4.4 lista cinco segmentos y el quinto es «Calentamiento: refrigerante por
debajo del objetivo». **No es una clase de esta partición, y meterlo lo habría
roto**: el calentamiento se solapa con las otras cuatro por definición —un
motor frío tiene ralentí, tiene deceleraciones y puede tener una tirada— así que
no es un tramo exclusivo sino un ESTADO ortogonal que se cruza con la
segmentación. Su sitio natural es un filtro de exclusión (F4-03) o un carril de
contexto, y su primitiva es la misma `umbral_con_histeresis` sobre
`coolant_temp`. Sin esa distinción, la partición tendría un solapamiento
sistemático en todo el arranque en frío y la precedencia tendría que resolver
cientos de instantes con un criterio que no significa nada.

El hueco que deja —los tramos de mariposa parcial que no son deceleración— lo
cubre `CRUCERO`, que es el estado estacionario a carga parcial: el que alimenta
la tabla RPM×MAP de §4.6, el que hay que distinguir del transitorio, y el que
esta tarea pide por su nombre.

PRECEDENCIA: ORDENADA POR CONSECUENCIA SI SE EQUIVOCA
======================================================
`ClaseDeSegmento.prioridad`, de mayor a menor, con el motivo de cada escalón:

1. **`ARRANQUE`.** Las otras cuatro presuponen un motor en marcha. Una muestra
   de arranque etiquetada como cualquier otra cosa mete la mezcla de arranque
   —enriquecida y en lazo abierto— en un tramo que se va a usar para afinar.
2. **`WOT`.** Es el entregable de la función («el usuario busca sus tiradas a
   mano»). Perder una tirada por absorberla en otra clase deja la función sin
   valor; el error contrario se ve en cuanto se abre el resumen de la tirada
   (régimen inicial y final, MAP máximo), así que es el que se puede corregir.
3. **`DECELERACION`.** Por encima de ralentí y de crucero porque una muestra en
   deceleración —corte de inyección, mariposa cerrada, colector en vacío— dentro
   de un tramo de crucero envenena la tabla de corrección de combustible, y §4.6
   dice literalmente que hay que excluirla. Etiquetar de más como deceleración
   solo pierde datos; etiquetar de menos corrompe una tabla que llega a la ECU.
4. **`RALENTI`.** Por encima de crucero porque el ralentí tiene su propio lazo de
   control y sus propias métricas (§4.2 P6: desviación RMS respecto al objetivo,
   tiempo de recuperación), y una muestra de carga parcial dentro de un tramo de
   ralentí las falsea. Además, el solape real entre los dos ocurre en la
   histéresis de «mariposa cerrada», donde la mariposa apenas se ha movido:
   físicamente está más cerca del ralentí que del crucero.
5. **`CRUCERO`.** El último: es la definición más ancha, la que menos afirma y la
   que se define por lo que NO es. Un instante que las otras cuatro no reclaman y
   que es estacionario a carga parcial es crucero; nada más se apoya en eso.

La precedencia se aplica **por muestra y antes de formar los eventos**, no
recortando segmentos ya formados. La consecuencia hay que decirla: una
intrusión de una clase superior PARTE el tramo de la inferior en dos, y los dos
trozos pasan por su permanencia mínima por separado, así que pueden desaparecer
los dos. Es lo correcto —un crucero interrumpido por una deceleración de dos
segundos no es un crucero de treinta— y es lo que hace que la partición no tenga
solapes por construcción y no por revisión.

LO QUE SE DECIDIÓ NO USAR, Y POR QUÉ
=====================================
`manifold_pressure` y `vehicle_speed` están en `data/roles.toml` y en el
AutoLog, y no entran en ninguna de las cinco definiciones. No es un olvido:

* Definir WOT por presión de colector en vez de por mariposa es OTRA definición
  —«plena carga» contra «plena mariposa»— y en un motor sobrealimentado no dan
  el mismo tramo. §4.4 define por mariposa y esa es la que se implementa; si el
  propietario quiere la otra, es una clase nueva con su nombre, no un añadido
  silencioso a esta.
* `vehicle_speed` distinguiría «ralentí parado» de «ralentí rodando» (embrague
  pisado, coche en movimiento), que es una distinción útil para P6 pero que
  §4.4 no pide y que exigiría un rol más para poder calcular el ralentí. Un rol
  requerido de más apaga la clase entera en los logs que no lo traen.

UN ROL QUE FALTA NO SE APROXIMA CON OTRO CANAL
===============================================
Si `throttle_position` no está asignado en un log, cuatro de las cinco clases
**no se pueden calcular**, y el informe lo dice con el nombre del rol que falta
(`ClaseNoCalculable`) en vez de aproximar la mariposa con la presión de colector
o con la carga. Es la misma regla que `plausibilidad.Diagnostico.SIN_ROL`: un
resultado ausente del informe es indistinguible de un resultado que salió vacío,
y aquí la diferencia es entre «este log no tiene tiradas» y «este log no puede
decir si las tiene».

Si falta `engine_speed` no se puede calcular ninguna clase, y además no hay
rejilla de tiempo sobre la que responder: es el rol que las cinco necesitan y el
que define la rejilla de referencia. El informe sale con las cinco clases en
`no_calculables` y la cobertura sobre cero muestras.

MULTI-TASA: LA REJILLA ES LA DEL RÉGIMEN
=========================================
Las cinco clases necesitan `engine_speed`, así que su rejilla es la de
referencia y los demás roles se llevan a ella con `alinear` (retención del
último valor con `ventana_validez_ms`, `docs/04` §4.5). No se remuestrea el
régimen a nada: es el canal más rápido de los tres logs reales (grupo G0, 18,9
Hz) y el que decide, así que remuestrearlo sería perder resolución donde importa.

Fuera de la ventana de validez el valor alineado es **hueco**, y un hueco no es
un `False`: la lógica de tres valores de `Condicion` decide si el instante queda
sin clasificar (`SIN_DATOS`) o si la clase se puede descartar de todas formas
—«mariposa desconocida Y régimen de 800 rpm» no es una tirada, y no hace falta
saber la mariposa para afirmarlo—. Esa es la razón por la que este módulo no
tiene ni una comprobación de validez propia: la hereda entera de F3-06.

ADR-009 Y REGLA 4
==================
Ni un bucle por muestra: los únicos `for` de este módulo recorren las cinco
clases y los segmentos que sobreviven a la permanencia (acotados por
`Permanencia.maximo_de_eventos`), igual que el de `primitivas.eventos`. Todo el
trabajo por muestra son llamadas a las primitivas, que ya están vectorizadas.

Y la clase de conversión (regla 4 de `CLAUDE.md`) se comprueba en la entrada y
viaja en la salida: las series de canal tienen que llegar como `Clase.PUNTO`
—una derivada ya hecha no es un canal— y la derivada del régimen que usa el
crucero es `Clase.TASA`, con su umbral declarado en rpm por segundo. El
`valor_pico` de cada segmento es un régimen (`PUNTO`) y lleva su clase hasta
quien lo pinte.

LO QUE ESTE MÓDULO NO HACE
===========================
* **No abre ficheros** (ADR-002): recibe las series y los umbrales ya cargados.
* **No convierte unidades** (ADR-004): todo entra y sale en canónica.
* **No resuelve roles.** Recibe un mapa de rol a serie ya resuelto por
  `identidad.py`; no sabe de nombres de canal ni de confianza de asignación. La
  desactivación por asignación difusa es F3-08 y se aplica antes, quitando el
  rol del mapa.
* **No resume una tirada.** El resumen de §4.4 (régimen inicial y final, MAP
  máximo, λ mínimo, eventos de knock) es del panel de tiradas (F3-17), que lo
  construye con `Segmento.evento.i_inicio` y `i_fin` sobre los canales que
  quiera. Aquí solo va el pico de régimen, que es lo que nombra el tramo.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from dlv_core.primitivas import (
    Condicion,
    Direccion,
    Evento,
    Extremo,
    Permanencia,
    Pico,
    Serie,
    Vectorial,
    alinear,
    banda,
    derivada,
    eventos,
    tiempo_acumulado,
    umbral_con_histeresis,
)
from dlv_core.unidades import Clase

__all__ = [
    "ROL_MARIPOSA",
    "ROL_REGIMEN",
    "ClaseDeSegmento",
    "ClaseNoCalculable",
    "Cobertura",
    "ErrorDeSegmentacion",
    "InformeDeSegmentacion",
    "MotivoSinClasificar",
    "Segmento",
    "UmbralesDeSegmentacion",
    "segmentar",
]

ROL_REGIMEN = "engine_speed"
"""El rol del régimen del motor (`data/roles.toml`), en rpm canónicos.

No es un umbral: es el identificador con el que el catálogo de roles nombra el
canal. Lo necesitan las cinco clases y define la rejilla de referencia.
"""

ROL_MARIPOSA = "throttle_position"
"""El rol de la posición de la mariposa, en FRACCIÓN (canónica de `ratio`), no en
porcentaje. Lo necesitan cuatro de las cinco clases."""


class ErrorDeSegmentacion(ValueError):
    """Uso incorrecto del módulo, o una configuración que no se puede aplicar.

    Un log raro no produce excepciones: produce segmentos, o no los produce y el
    informe dice por qué (`ClaseNoCalculable`, `MotivoSinClasificar`). Esto otro
    —una serie que no es un canal, un umbral que falta, una duración mínima para
    una clase que no existe, dos segmentos que se solapan— es un fallo de quien
    llama o de este módulo, y callarlo produciría una partición plausible y
    falsa.
    """


# --------------------------------------------------------------------------- #
# Las cinco clases y su precedencia
# --------------------------------------------------------------------------- #
class ClaseDeSegmento(Enum):
    """Las cinco cosas reconocibles que puede estar haciendo el motor.

    El valor de cada miembro es la clave con la que `data/umbrales.toml` declara
    su duración mínima (`[segmentacion.duracion_minima_s]`), así que el fichero
    de datos y el enumerado no pueden desincronizarse sin que
    `UmbralesDeSegmentacion.desde_mapa` falle.
    """

    ARRANQUE = "arranque"
    WOT = "wot"
    DECELERACION = "deceleracion"
    RALENTI = "ralenti"
    CRUCERO = "crucero"

    @property
    def prioridad(self) -> int:
        """Quién gana cuando dos definiciones se pisan. Menor es antes.

        El orden y el motivo de cada escalón están en la cabecera del módulo
        («PRECEDENCIA: ORDENADA POR CONSECUENCIA SI SE EQUIVOCA»). Se declara
        aquí, en el enumerado, y no en el orden de un bucle: el resultado no
        puede depender de en qué orden se recorran las clases, y hay una prueba
        que lo comprueba pasándolas al revés.

        No es un umbral configurable, y es la única cosa de este módulo que no lo
        es: un umbral es «cuánto», y esto es «qué significa». Cambiar la
        precedencia cambia la taxonomía, no un límite.
        """
        return _PRECEDENCIA[self]

    @property
    def roles_requeridos(self) -> tuple[str, ...]:
        """Los roles sin los cuales esta clase NO se puede calcular.

        Requeridos de verdad: si falta uno, la clase no se aproxima con otro
        canal, se declara `ClaseNoCalculable`. Ninguna de las cinco tiene roles
        opcionales, y eso es deliberado -- una clase que cambia de definición
        según qué canales traiga el log da dos resultados distintos con el mismo
        nombre.
        """
        return _ROLES_REQUERIDOS[self]

    @property
    def extremo_del_pico(self) -> Extremo:
        """Qué extremo del régimen caracteriza al tramo.

        `primitivas.Pico` exige elegirlo y no tiene valor por omisión, porque el
        pico de un tramo de presión de aceite baja es su mínimo. Aquí:

        * `ARRANQUE` y `WOT`, el MÁXIMO: el régimen en que el motor prendió y el
          régimen final de la tirada, que es el número que la nombra.
        * `DECELERACION` y `RALENTI`, el MÍNIMO: hasta dónde bajó la retención, y
          el bache de un lazo de ralentí que no sostiene (§4.2 P6).
        * `CRUCERO`, el MÁXIMO, por coherencia con el resto de los tramos «con
          el pie puesto»; en un tramo estacionario los dos extremos distan poco
          por definición, así que la elección no decide nada y por eso no tiene
          un argumento más fuerte.
        """
        return _EXTREMO_DEL_PICO[self]


_PRECEDENCIA: dict[ClaseDeSegmento, int] = {
    ClaseDeSegmento.ARRANQUE: 1,
    ClaseDeSegmento.WOT: 2,
    ClaseDeSegmento.DECELERACION: 3,
    ClaseDeSegmento.RALENTI: 4,
    ClaseDeSegmento.CRUCERO: 5,
}

_ROLES_REQUERIDOS: dict[ClaseDeSegmento, tuple[str, ...]] = {
    ClaseDeSegmento.ARRANQUE: (ROL_REGIMEN,),
    ClaseDeSegmento.WOT: (ROL_REGIMEN, ROL_MARIPOSA),
    ClaseDeSegmento.DECELERACION: (ROL_REGIMEN, ROL_MARIPOSA),
    ClaseDeSegmento.RALENTI: (ROL_REGIMEN, ROL_MARIPOSA),
    ClaseDeSegmento.CRUCERO: (ROL_REGIMEN, ROL_MARIPOSA),
}

_EXTREMO_DEL_PICO: dict[ClaseDeSegmento, Extremo] = {
    ClaseDeSegmento.ARRANQUE: Extremo.MAXIMO,
    ClaseDeSegmento.WOT: Extremo.MAXIMO,
    ClaseDeSegmento.DECELERACION: Extremo.MINIMO,
    ClaseDeSegmento.RALENTI: Extremo.MINIMO,
    ClaseDeSegmento.CRUCERO: Extremo.MAXIMO,
}

_CLAVES_ESCALARES: tuple[str, ...] = (
    "rpm_arranque_min",
    "rpm_motor_en_marcha",
    "rpm_ralenti_max",
    "rpm_decel_min",
    "rpm_creciente_min_por_s",
    "rpm_estable_max_por_s",
    "tps_cerrada_entrada",
    "tps_cerrada_salida",
    "tps_wot_entrada",
    "tps_wot_salida",
    "ventana_derivada_s",
    "ventana_validez_ms",
    "histeresis_relativa",
)
"""Las claves escalares que `desde_mapa` exige y que `fusionar` admite. Una sola
lista para las dos: si estuvieran escritas dos veces, una anulación de una clave
nueva se aceptaría en un sitio y se rechazaría en el otro."""

_CLAVES_NO_NEGATIVAS: tuple[str, ...] = (
    "rpm_arranque_min",
    "rpm_motor_en_marcha",
    "rpm_ralenti_max",
    "rpm_decel_min",
    "rpm_creciente_min_por_s",
    "rpm_estable_max_por_s",
    "ventana_derivada_s",
    "ventana_validez_ms",
)

_CLAVES_DE_FRACCION: tuple[str, ...] = (
    "tps_cerrada_entrada",
    "tps_cerrada_salida",
    "tps_wot_entrada",
    "tps_wot_salida",
)


class MotivoSinClasificar(Enum):
    """Por qué una muestra de la rejilla no está en ningún segmento.

    Existe para que «el log está cubierto al 78 %» tenga una segunda mitad
    contable. Un 22 % sin explicar es indistinguible de un defecto de la
    segmentación; repartido en estos cinco motivos, cada trozo se puede
    contrastar con el log.
    """

    MOTOR_PARADO = "motor_parado"
    """El régimen es válido y está por debajo de `rpm_arranque_min`: el motor no
    gira. No es un defecto de la segmentación, es que no hay nada que segmentar
    —y por eso no se cuenta como hueco de cobertura sino como motivo propio."""

    SIN_DATOS = "sin_datos"
    """Alguna de las clases calculables no pudo pronunciarse ahí: falta el régimen
    en ese instante, el rol alineado quedó fuera de su ventana de validez (§4.5) o
    la derivada del régimen no tiene ninguna muestra anterior en su ventana.

    Basta con que UNA clase no haya podido decidir, no que fallen todas: sin
    haberlas podido evaluar no se puede afirmar que ninguna definición se cumple,
    y decir `NINGUNA_CLASE` sería exactamente esa afirmación. Es el hueco honesto
    de §4.5 llevado hasta la cuenta final."""

    DURACION_INSUFICIENTE = "duracion_insuficiente"
    """La condición de alguna clase se cumplió ahí, pero el tramo no llegó a la
    duración mínima de esa clase (ni al número mínimo de muestras). Es el motivo
    que hay que mirar si la cobertura parece baja: significa que las
    definiciones aciertan y las duraciones mínimas están apretadas."""

    PENDIENTE_INSUFICIENTE = "pendiente_insuficiente"
    """Solo de `WOT`: el tramo de mariposa abierta duró lo suficiente pero el
    régimen no subió lo bastante (mantenido a plena carga, no una tirada). Se
    separa de `DURACION_INSUFICIENTE` porque la acción que sugiere es otra: ahí
    se ajusta una duración, aquí se ajusta `rpm_creciente_min_por_s`."""

    NINGUNA_CLASE = "ninguna_clase"
    """El motor gira, TODAS las clases calculables pudieron decidir, y ninguna de
    sus definiciones se cumple:
    un transitorio de carga parcial, una mariposa a medio abrir con el régimen
    cambiando, el tirón de embrague que baja de 1 200 a 412 rpm y vuelve. Es el
    residuo legítimo de una partición por definiciones positivas, y su tamaño es
    un dato sobre el log, no un defecto: un log de carretera tiene mucho
    transitorio y un log de banco casi ninguno."""


# --------------------------------------------------------------------------- #
# Umbrales configurables (data/umbrales.toml [segmentacion])
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class UmbralesDeSegmentacion:
    """Los umbrales de la segmentación. **Sin valores por omisión en el código.**

    Regla 3 de `CLAUDE.md`: un umbral cableado es una opinión disfrazada de
    física. Aquí se lleva al extremo de `plausibilidad.UmbralesPlausibilidad` y
    de `primitivas.Permanencia`: no hay ni un valor por omisión, `desde_mapa`
    exige todas las claves y falla si falta alguna. Una copia en el código puede
    desincronizarse del fichero sin que nada se ponga en rojo; una excepción no.

    Su sitio es `data/umbrales.toml [segmentacion]` más dos claves que ya
    existían y que esta sección no duplica —`[motor_de_deteccion]
    .ventana_validez_ms` y `[general].histeresis_relativa`—, con la precedencia
    de siempre: anulación por canal > perfil activo > preferencias de usuario >
    fichero. Quien conoce esas capas las fusiona con `fusionar`.

    Todos los valores están en unidad CANÓNICA (ADR-004): rpm, fracción de
    mariposa (no porcentaje), segundos, rpm por segundo.
    """

    rpm_arranque_min: float
    """Por debajo de este régimen el motor no gira (`MOTOR_PARADO`)."""

    rpm_motor_en_marcha: float
    """Régimen a partir del cual el motor se sostiene solo. Es el techo de la
    banda de arranque y el suelo de la de ralentí."""

    rpm_ralenti_max: float
    """Techo de la banda de ralentí, y salida de la histéresis de deceleración:
    una retención deja de serlo cuando llega al ralentí."""

    rpm_decel_min: float
    """Régimen por encima del cual la mariposa cerrada es una deceleración y no
    un ralentí."""

    rpm_creciente_min_por_s: float
    """Pendiente media mínima del régimen para que un tramo de mariposa abierta
    sea una tirada. Se compara contra una TASA (rpm por segundo), no contra un
    punto."""

    rpm_estable_max_por_s: float
    """Cuánto puede moverse el régimen para que el tramo se considere
    estacionario (crucero). También una TASA."""

    tps_cerrada_entrada: float
    """Fracción de mariposa por debajo de la cual se considera cerrada
    («TPS ≈ 0» de §4.4)."""

    tps_cerrada_salida: float
    """Fracción a la que hay que volver para dejar de considerarla cerrada. La
    histéresis, en canónica y no como fracción del umbral: `umbral_con_histeresis`
    no acepta fracciones y explica por qué."""

    tps_wot_entrada: float
    """Fracción de mariposa que abre una tirada («TPS > 80 %» de §4.4). Es
    también el techo de la banda de crucero."""

    tps_wot_salida: float
    """Fracción a la que hay que bajar para cerrar la tirada."""

    ventana_derivada_s: float
    """Ventana de la derivada del régimen con la que se juzga si el tramo es
    estacionario. Sale de `[segmentacion]` y no de `[motor_de_deteccion]` porque
    es una decisión de esta segmentación, no del motor de detectores."""

    ventana_validez_ms: float
    """De `[motor_de_deteccion]`: cuánto sigue valiendo el último valor conocido
    de un canal al llevarlo a la rejilla del régimen. No se declara otra vez en
    `[segmentacion]` porque es la misma pregunta y una segunda copia se
    desincronizaría."""

    histeresis_relativa: float
    """De `[general]`: la fracción de la ANCHURA de una banda que hay que rebasar
    para salir de ella. `primitivas.banda` es la única primitiva que la puede
    usar sin ambigüedad, y explica el motivo."""

    duracion_minima_s: Mapping[ClaseDeSegmento, float]
    """Duración mínima de un segmento, por clase. La de `WOT` es el «> 1,5 s» de
    §4.4; las otras cuatro están derivadas en los comentarios de
    `data/umbrales.toml`. Se aplica con `Permanencia.fusionar`, así que el número
    mínimo de muestras de `[general]` sigue exigiéndose además de esta."""

    def __post_init__(self) -> None:
        for nombre in _CLAVES_NO_NEGATIVAS:
            valor = float(getattr(self, nombre))
            if valor < 0.0:
                raise ErrorDeSegmentacion(
                    f"[segmentacion].{nombre} = {valor!r} no puede ser negativo"
                )
        for nombre in _CLAVES_DE_FRACCION:
            valor = float(getattr(self, nombre))
            if not 0.0 <= valor <= 1.0:
                raise ErrorDeSegmentacion(
                    f"[segmentacion].{nombre} = {valor!r} tiene que ser una FRACCIÓN de "
                    "mariposa en [0, 1]; la canónica de `ratio` no es el porcentaje"
                )
        # Las histéresis, en el sentido correcto. Al revés, `primitivas` ya lo
        # rechazaría, pero con un mensaje sobre la primitiva y no sobre el
        # fichero de umbrales, que es donde está el error.
        if self.tps_cerrada_salida < self.tps_cerrada_entrada:
            raise ErrorDeSegmentacion(
                f"tps_cerrada_salida ({self.tps_cerrada_salida!r}) tiene que ser >= "
                f"tps_cerrada_entrada ({self.tps_cerrada_entrada!r}): se entra al bajar y se "
                "sale al subir, así que la salida está por encima"
            )
        if self.tps_wot_salida > self.tps_wot_entrada:
            raise ErrorDeSegmentacion(
                f"tps_wot_salida ({self.tps_wot_salida!r}) tiene que ser <= tps_wot_entrada "
                f"({self.tps_wot_entrada!r}): se entra al subir y se sale al bajar"
            )
        if self.tps_wot_entrada <= self.tps_cerrada_entrada:
            raise ErrorDeSegmentacion(
                f"tps_wot_entrada ({self.tps_wot_entrada!r}) no supera a tps_cerrada_entrada "
                f"({self.tps_cerrada_entrada!r}): la banda de crucero estaría vacía y no "
                "habría ninguna mariposa que fuera «parcial»"
            )
        if self.rpm_motor_en_marcha <= self.rpm_arranque_min:
            raise ErrorDeSegmentacion(
                f"rpm_motor_en_marcha ({self.rpm_motor_en_marcha!r}) no supera a "
                f"rpm_arranque_min ({self.rpm_arranque_min!r}): la banda de arranque estaría "
                "vacía y ningún log tendría arranque"
            )
        if self.rpm_ralenti_max <= self.rpm_motor_en_marcha:
            raise ErrorDeSegmentacion(
                f"rpm_ralenti_max ({self.rpm_ralenti_max!r}) no supera a rpm_motor_en_marcha "
                f"({self.rpm_motor_en_marcha!r}): la banda de ralentí estaría vacía"
            )
        if self.rpm_decel_min < self.rpm_ralenti_max:
            raise ErrorDeSegmentacion(
                f"rpm_decel_min ({self.rpm_decel_min!r}) por debajo de rpm_ralenti_max "
                f"({self.rpm_ralenti_max!r}): la deceleración usa el techo del ralentí como "
                "umbral de salida, y una histéresis al revés abre un tramo que no cierra"
            )
        if self.ventana_derivada_s <= 0.0:
            raise ErrorDeSegmentacion(
                "ventana_derivada_s tiene que ser positiva: sin ventana no hay derivada"
            )
        faltan = [c.value for c in ClaseDeSegmento if c not in self.duracion_minima_s]
        if faltan:
            raise ErrorDeSegmentacion(
                "[segmentacion.duracion_minima_s] no declara la duración mínima de: "
                + ", ".join(sorted(faltan))
                + "; una clase sin duración mínima tendría que traer un valor por omisión "
                "en el código"
            )
        for clase, duracion in self.duracion_minima_s.items():
            if float(duracion) < 0.0:
                raise ErrorDeSegmentacion(
                    f"[segmentacion.duracion_minima_s].{clase.value} = {duracion!r} no puede "
                    "ser negativa"
                )

    @classmethod
    def desde_mapa(cls, mapa: Mapping[str, Any]) -> UmbralesDeSegmentacion:
        """Construye los umbrales desde `data/umbrales.toml` ya parseado por quien
        llama (ADR-002), con las capas de precedencia ya fusionadas.

        El mapa tiene que traer las claves de `[segmentacion]`, la
        `ventana_validez_ms` de `[motor_de_deteccion]` y la
        `histeresis_relativa` de `[general]`: son las tres secciones que esta
        segmentación consume, y juntarlas es de quien lee el fichero.

        Una clave ausente es un error, no un valor por omisión. Una clave de más
        en `duracion_minima_s` también: un nombre de clase mal escrito se
        ignoraría en silencio y la duración mínima seguiría siendo la de otra
        clase.
        """
        faltan = [c for c in (*_CLAVES_ESCALARES, "duracion_minima_s") if c not in mapa]
        if faltan:
            raise ErrorDeSegmentacion(
                "data/umbrales.toml no declara: "
                + ", ".join(faltan)
                + "; son umbrales configurables y este módulo no lleva copia de ellos "
                "([segmentacion] da los suyos, [motor_de_deteccion] la ventana de validez "
                "y [general] la histéresis relativa)"
            )
        bruto = mapa["duracion_minima_s"]
        conocidas = {c.value: c for c in ClaseDeSegmento}
        desconocidas = sorted(set(bruto) - set(conocidas))
        if desconocidas:
            raise ErrorDeSegmentacion(
                f"[segmentacion.duracion_minima_s] declara clases que no existen: "
                f"{desconocidas}; las cinco son {sorted(conocidas)}"
            )
        valores = {nombre: float(mapa[nombre]) for nombre in _CLAVES_ESCALARES}
        return cls(
            duracion_minima_s={conocidas[k]: float(v) for k, v in bruto.items()},
            **valores,
        )

    def fusionar(self, anulaciones: Mapping[str, Any]) -> UmbralesDeSegmentacion:
        """Estos umbrales con las claves de `anulaciones` sustituidas.

        La pieza de la precedencia que le toca a este módulo: quien conoce el
        perfil activo, las preferencias del usuario y las anulaciones por canal
        las aplica de menor a mayor prioridad. Una clave desconocida es un error,
        porque un nombre mal escrito se ignoraría en silencio y el umbral
        seguiría siendo el de por omisión sin que nadie se enterara.
        """
        if not anulaciones:
            return self
        base: dict[str, Any] = {nombre: getattr(self, nombre) for nombre in _CLAVES_ESCALARES}
        base["duracion_minima_s"] = {c.value: d for c, d in self.duracion_minima_s.items()}
        desconocidas = set(anulaciones) - set(base)
        if desconocidas:
            raise ErrorDeSegmentacion(
                f"anulaciones de segmentación desconocidas: {sorted(desconocidas)}; "
                "un nombre mal escrito se ignoraría en silencio y el umbral seguiría "
                "siendo el de por omisión"
            )
        base.update(anulaciones)
        return UmbralesDeSegmentacion.desde_mapa(base)


# --------------------------------------------------------------------------- #
# Resultado
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class Segmento:
    """Un tramo del log en el que el motor está haciendo UNA cosa reconocible.

    Es `primitivas.Evento` más la clase, y nada más. Reutilizar `Evento` no es
    economía de código: es lo que hace que un segmento y una incidencia se
    fechen igual, con el mismo criterio de duración («lo observado entre la
    primera y la última muestra»), y que el panel de tiradas pueda pedirle a
    `Evento.i_inicio` e `i_fin` el tramo de cualquier otro canal sin volver a
    buscar nada.
    """

    clase: ClaseDeSegmento
    evento: Evento

    @property
    def t_inicio_ms(self) -> float:
        return self.evento.t_inicio_ms

    @property
    def t_fin_ms(self) -> float:
        return self.evento.t_fin_ms

    @property
    def duracion_s(self) -> float:
        return self.evento.duracion_s

    @property
    def regimen_pico(self) -> float | None:
        """El régimen extremo del tramo, en rpm canónicos (`Clase.PUNTO`).

        Qué extremo es lo dice `ClaseDeSegmento.extremo_del_pico`, y la clase de
        conversión viaja en `evento.clase_valor` para que quien lo pinte no lo
        convierta como un intervalo.
        """
        return self.evento.valor_pico


@dataclass(slots=True, frozen=True)
class ClaseNoCalculable:
    """Una clase que no se ha podido calcular, con el rol que falta.

    No es una lista vacía de segmentos: es la diferencia entre «este log no
    tiene tiradas» y «este log no puede decir si las tiene». Misma razón que
    `plausibilidad.Diagnostico.SIN_ROL`: un resultado ausente del informe es
    indistinguible de un resultado que salió vacío.
    """

    clase: ClaseDeSegmento
    roles_faltantes: tuple[str, ...]

    @property
    def motivo(self) -> str:
        """Frase lista para el informe de importación, con los roles por nombre."""
        return (
            f"la clase {self.clase.value} necesita "
            + ", ".join(self.roles_faltantes)
            + " y el log no tiene ese rol asignado; no se aproxima con otro canal"
        )


@dataclass(slots=True, frozen=True)
class Cobertura:
    """Las cuentas de la partición: cuántas muestras en cada clase y cuántas
    fuera, con el motivo de cada trozo de fuera.

    LA ARITMÉTICA ES EL CONTRATO
    ----------------------------
    `__post_init__` comprueba que las cuentas suman exactamente las muestras de
    la rejilla de referencia. No es una comprobación de cortesía: es la forma
    ejecutable de «los segmentos no se solapan ni dejan huecos sin explicar». Si
    dos clases reclamaran la misma muestra, la suma se pasaría del total y esto
    fallaría; si un trozo se perdiera por el camino, no llegaría. Las dos cosas
    son defectos de este módulo, así que la excepción es la correcta.
    """

    muestras: int
    """Muestras de la rejilla de referencia (la del régimen). Es 0 cuando el rol
    del régimen no está asignado, y entonces no hay nada que repartir."""

    por_clase: Mapping[ClaseDeSegmento, int]
    """Muestras dentro de un segmento devuelto, por clase. Solo aparecen las
    clases calculables: una clase que no se pudo calcular no tiene 0 muestras,
    tiene un `ClaseNoCalculable`."""

    sin_clasificar: Mapping[MotivoSinClasificar, int]
    """Muestras fuera de todo segmento, por motivo. Los cinco motivos están
    siempre, con 0 si no hay ninguna: un motivo ausente parecería imposible en
    vez de vacío."""

    def __post_init__(self) -> None:
        for clave, n in (*self.por_clase.items(), *self.sin_clasificar.items()):
            if n < 0:
                raise ErrorDeSegmentacion(
                    f"la cobertura de {clave.value} es {n}: una cuenta de muestras no puede "
                    "ser negativa, y si lo es hay un reparto mal restado"
                )
        total = self.muestras_en_segmento + sum(self.sin_clasificar.values())
        if total != self.muestras:
            raise ErrorDeSegmentacion(
                f"las cuentas de la cobertura suman {total} y la rejilla tiene "
                f"{self.muestras} muestras. O dos clases reclaman la misma muestra "
                "(solape) o falta un motivo por el que una quedó fuera; las dos son "
                "defectos de la segmentación, no del log"
            )

    @property
    def muestras_en_segmento(self) -> int:
        return sum(self.por_clase.values())

    @property
    def fraccion_cubierta(self) -> float:
        """Fracción de la rejilla que está dentro de algún segmento.

        Sobre una rejilla vacía es 0,0 y no un error: un log sin el rol del
        régimen tiene cobertura nula, que es la respuesta correcta.
        """
        if self.muestras == 0:
            return 0.0
        return self.muestras_en_segmento / self.muestras


@dataclass(slots=True, frozen=True)
class InformeDeSegmentacion:
    """Lo que devuelve `segmentar`: los tramos, las cuentas y lo que no se pudo.

    Los tres van juntos y no en tres funciones distintas porque las tres
    respuestas se leen a la vez: 12 tiradas no significan lo mismo si el 40 %
    del log quedó sin clasificar, y ninguna de las dos significa nada si la
    mariposa no estaba asignada.
    """

    segmentos: tuple[Segmento, ...]
    """Ordenados por instante de inicio, sin solaparse. Las dos cosas las
    comprueba `__post_init__`."""

    cobertura: Cobertura
    no_calculables: tuple[ClaseNoCalculable, ...]

    precedencia: tuple[ClaseDeSegmento, ...]
    """El orden de precedencia que se aplicó, de mayor a menor. Va en el informe
    para que la respuesta sea auditable sin leer el código: si un tramo salió
    `DECELERACION` donde se esperaba `CRUCERO`, esta tupla dice por qué."""

    def __post_init__(self) -> None:
        anterior: Segmento | None = None
        for s in self.segmentos:  # bucle sobre SEGMENTOS, no sobre muestras
            if anterior is not None and s.evento.i_inicio <= anterior.evento.i_fin:
                raise ErrorDeSegmentacion(
                    f"el segmento {s.clase.value} empieza en la muestra "
                    f"{s.evento.i_inicio} y el anterior ({anterior.clase.value}) acaba en "
                    f"{anterior.evento.i_fin}: dos segmentos se solapan, y la precedencia "
                    "existe justamente para que eso no pueda pasar"
                )
            anterior = s

    def de_clase(self, clase: ClaseDeSegmento) -> tuple[Segmento, ...]:
        """Los segmentos de una clase, en orden. Vacío si no hay ninguno; para
        saber si además no se pudo calcular, `no_calculables`."""
        return tuple(s for s in self.segmentos if s.clase is clase)

    def es_calculable(self, clase: ClaseDeSegmento) -> bool:
        return all(nc.clase is not clase for nc in self.no_calculables)

    def segundos_por_clase(self) -> Mapping[ClaseDeSegmento, float]:
        """Tiempo total observado en cada clase calculable, en segundos.

        Usa `primitivas.tiempo_acumulado` sobre los mismos eventos que están en
        `segmentos`, y no una suma propia, por el motivo que esa función
        documenta: dos números de la misma pantalla que no cuadran son peores que
        cualquiera de los dos. Un segmento de una sola muestra suma 0 s.
        """
        return {
            clase: tiempo_acumulado([s.evento for s in self.de_clase(clase)])
            for clase in ClaseDeSegmento
            if self.es_calculable(clase)
        }


# --------------------------------------------------------------------------- #
# Cálculo
# --------------------------------------------------------------------------- #
def _numpy() -> Vectorial:
    """Importa NumPy en el momento de usarlo y no al importar el módulo, igual que
    `primitivas._numpy`: así este módulo se puede importar y probar sin NumPy
    instalado, con una implementación del protocolo `Vectorial`."""
    import numpy

    return cast("Vectorial", numpy)


def _xp(xp: Vectorial | None) -> Vectorial:
    return xp if xp is not None else _numpy()


def _no(mascara: Any) -> Any:
    """Negación elemento a elemento, con el mismo recurso que `primitivas._no`:
    `== 0` en vez de `~`, para no obligar a que `Vectorial` defina el operador."""
    return mascara == 0


def _orden_de_precedencia() -> tuple[ClaseDeSegmento, ...]:
    """Las cinco clases de mayor a menor prioridad. Ordenar aquí, y una sola vez,
    es lo que impide que el orden de evaluación decida nada."""
    return tuple(sorted(ClaseDeSegmento, key=lambda c: c.prioridad))


def _condiciones_por_clase(
    regimen: Serie,
    mariposa: Serie | None,
    umbrales: UmbralesDeSegmentacion,
    *,
    xp: Vectorial,
) -> dict[ClaseDeSegmento, Condicion]:
    """Las cinco definiciones de §4.4, cada una como una `Condicion`.

    Aquí no se decide nada sobre solapes: cada clase dice dónde se cumple SU
    definición, tal cual, y la precedencia se aplica después. Separarlo es lo
    que permite contar cuántas muestras reclamaba cada definición antes de que
    otra se las quitara, y sobre todo es lo que hace que el resultado no dependa
    del orden en que se construyen.
    """
    condiciones: dict[ClaseDeSegmento, Condicion] = {}

    # ARRANQUE: el motor gira por debajo del régimen en que se sostiene solo.
    condiciones[ClaseDeSegmento.ARRANQUE] = banda(
        regimen,
        minimo=umbrales.rpm_arranque_min,
        maximo=umbrales.rpm_motor_en_marcha,
        histeresis_relativa=umbrales.histeresis_relativa,
        xp=xp,
    )
    if mariposa is None:
        return condiciones

    cerrada = umbral_con_histeresis(
        mariposa,
        entrada=umbrales.tps_cerrada_entrada,
        salida=umbrales.tps_cerrada_salida,
        direccion=Direccion.ABAJO,
        xp=xp,
    )
    # WOT: solo la mariposa. El «RPM creciente» de §4.4 se comprueba sobre el
    # segmento formado, en `_pendiente_rpm_por_s` (ver la cabecera del módulo).
    condiciones[ClaseDeSegmento.WOT] = umbral_con_histeresis(
        mariposa,
        entrada=umbrales.tps_wot_entrada,
        salida=umbrales.tps_wot_salida,
        direccion=Direccion.ARRIBA,
        xp=xp,
    )
    # DECELERACIÓN: mariposa cerrada por encima del régimen de deceleración, y
    # sigue siéndolo mientras el régimen cae hasta el techo del ralentí.
    condiciones[ClaseDeSegmento.DECELERACION] = cerrada.y(
        umbral_con_histeresis(
            regimen,
            entrada=umbrales.rpm_decel_min,
            salida=umbrales.rpm_ralenti_max,
            direccion=Direccion.ARRIBA,
            xp=xp,
        ),
        xp=xp,
    )
    # RALENTÍ: mariposa cerrada con el motor en marcha y por debajo del techo del
    # ralentí. La banda arranca en `rpm_motor_en_marcha` y no en 0: un motor que
    # gira más despacio que eso no está en ralentí, está arrancando o calándose.
    condiciones[ClaseDeSegmento.RALENTI] = cerrada.y(
        banda(
            regimen,
            minimo=umbrales.rpm_motor_en_marcha,
            maximo=umbrales.rpm_ralenti_max,
            histeresis_relativa=umbrales.histeresis_relativa,
            xp=xp,
        ),
        xp=xp,
    )
    # CRUCERO: mariposa parcial, motor en marcha y régimen estacionario. La banda
    # de mariposa usa los dos umbrales que ya existen —cerrada y WOT— así que
    # «parcial» es exactamente «ni cerrada ni a fondo» y no un tercer criterio.
    en_marcha = umbral_con_histeresis(
        regimen,
        entrada=umbrales.rpm_motor_en_marcha,
        salida=umbrales.rpm_arranque_min,
        direccion=Direccion.ARRIBA,
        xp=xp,
    )
    estacionario = banda(
        derivada(regimen, ventana_s=umbrales.ventana_derivada_s, xp=xp),
        minimo=-umbrales.rpm_estable_max_por_s,
        maximo=umbrales.rpm_estable_max_por_s,
        histeresis_relativa=umbrales.histeresis_relativa,
        xp=xp,
    )
    condiciones[ClaseDeSegmento.CRUCERO] = (
        banda(
            mariposa,
            minimo=umbrales.tps_cerrada_entrada,
            maximo=umbrales.tps_wot_entrada,
            histeresis_relativa=umbrales.histeresis_relativa,
            xp=xp,
        )
        .y(en_marcha, xp=xp)
        .y(estacionario, xp=xp)
    )
    return condiciones


def _pendiente_rpm_por_s(regimen: Serie, evento: Evento) -> float:
    """Pendiente media del régimen en un segmento, en rpm por segundo.

    Es el «RPM creciente durante > 1,5 s» de §4.4 aplicado al tramo y no a la
    muestra, y el motivo está en la cabecera del módulo: un cambio de marcha a
    mariposa abierta invierte la derivada instantánea y partiría la tirada en dos
    trozos que la permanencia descartaría.

    La magnitud es una TASA (regla 4): régimen al final menos régimen al
    principio —una diferencia de dos `PUNTO`, que es un `INTERVALO`— dividida por
    el tiempo observado. Se compara contra `rpm_creciente_min_por_s`, que está
    declarado en las mismas unidades.

    Un segmento de una sola muestra no tiene pendiente medible y devuelve 0,0,
    que lo descarta: con la duración mínima de WOT (1,5 s) no puede ocurrir, pero
    el valor por omisión de una anulación de usuario sí podría permitirlo, y
    dividir por cero para averiguarlo no es la forma.
    """
    if evento.duracion_s <= 0.0:
        return 0.0
    # Dos indexaciones por evento, no por muestra: el bucle que las llama recorre
    # los segmentos que sobrevivieron a la permanencia (ADR-009).
    inicio = float(regimen.v[evento.i_inicio])
    fin = float(regimen.v[evento.i_fin])
    return (fin - inicio) / evento.duracion_s


def _series_en_la_rejilla(
    series: Mapping[str, Serie],
    umbrales: UmbralesDeSegmentacion,
    *,
    xp: Vectorial,
) -> tuple[Serie, Serie | None]:
    """El régimen (que define la rejilla) y la mariposa llevada a esa rejilla.

    Toda serie de canal tiene que llegar como `Clase.PUNTO` (regla 4): lo que
    sale del almacén es un canal, no una derivada ni un delta. Aceptar otra clase
    aquí dejaría que una derivada ya calculada se comparara con un umbral de
    régimen, que es la trampa del delta con otro disfraz.
    """
    regimen = series[ROL_REGIMEN]
    candidatas = {ROL_REGIMEN: regimen, ROL_MARIPOSA: series.get(ROL_MARIPOSA)}
    for rol, serie in candidatas.items():
        if serie is not None and serie.clase is not Clase.PUNTO:
            raise ErrorDeSegmentacion(
                f"la serie del rol {rol} es de clase {serie.clase.value} y tiene que ser "
                "PUNTO: un canal tal como sale del almacén es un punto, y una derivada o "
                "un delta comparados con un umbral de canal son la trampa del delta"
            )
    mariposa = series.get(ROL_MARIPOSA)
    if mariposa is not None:
        mariposa = alinear(
            mariposa, regimen.t_ms, ventana_validez_ms=umbrales.ventana_validez_ms, xp=xp
        )
    return regimen, mariposa


def segmentar(
    series: Mapping[str, Serie],
    *,
    umbrales: UmbralesDeSegmentacion,
    permanencia_base: Permanencia,
    xp: Vectorial | None = None,
) -> InformeDeSegmentacion:
    """Parte el log en segmentos de las cinco clases de `ClaseDeSegmento`.

    `series` es un mapa de **rol semántico** a serie en unidad canónica, ya
    resuelto por `identidad.py`: este módulo no sabe de nombres de canal. Los
    roles que le hacen falta son `engine_speed` y `throttle_position`; cualquier
    otro que traiga el mapa se ignora, porque ninguna de las cinco definiciones
    lo usa (y la cabecera del módulo dice por qué no usa la presión de colector
    ni la velocidad).

    `permanencia_base` es la de `[general]` más `[motor_de_deteccion]`
    (`Permanencia.desde_mapa`); la duración mínima de cada clase se aplica encima
    con `Permanencia.fusionar`, así que el número mínimo de muestras y el tope de
    eventos siguen siendo los del fichero.

    Devuelve un `InformeDeSegmentacion` con los segmentos sin solapes, las
    cuentas de cobertura con el motivo de cada hueco, y las clases que no se han
    podido calcular por falta de rol. **No lanza excepción por un log raro**: un
    log sin régimen devuelve un informe vacío que lo explica.
    """
    xp = _xp(xp)
    if ROL_REGIMEN not in series:
        # Sin el régimen no hay rejilla de referencia, así que no hay ni sobre
        # qué muestras responder. Cada clase declara los roles que le faltan a
        # ella, que no son necesariamente los mismos.
        return InformeDeSegmentacion(
            segmentos=(),
            cobertura=Cobertura(
                muestras=0,
                por_clase={},
                sin_clasificar=dict.fromkeys(MotivoSinClasificar, 0),
            ),
            no_calculables=tuple(
                ClaseNoCalculable(
                    clase=c,
                    roles_faltantes=tuple(r for r in c.roles_requeridos if r not in series),
                )
                for c in ClaseDeSegmento
            ),
            precedencia=_orden_de_precedencia(),
        )

    regimen, mariposa = _series_en_la_rejilla(series, umbrales, xp=xp)
    condiciones = _condiciones_por_clase(regimen, mariposa, umbrales, xp=xp)
    no_calculables = tuple(
        ClaseNoCalculable(
            clase=c, roles_faltantes=tuple(r for r in c.roles_requeridos if r not in series)
        )
        for c in ClaseDeSegmento
        if c not in condiciones
    )

    exclusivas = _resolver_precedencia(condiciones, xp=xp)
    segmentos, por_clase, descartadas = _eventos_por_clase(
        exclusivas, regimen, umbrales, permanencia_base, xp=xp
    )
    cobertura = _cobertura(
        exclusivas, regimen, umbrales, por_clase=por_clase, descartadas=descartadas, xp=xp
    )
    return InformeDeSegmentacion(
        segmentos=segmentos,
        cobertura=cobertura,
        no_calculables=no_calculables,
        precedencia=_orden_de_precedencia(),
    )


def _resolver_precedencia(
    condiciones: Mapping[ClaseDeSegmento, Condicion], *, xp: Vectorial
) -> dict[ClaseDeSegmento, Condicion]:
    """Cada definición menos lo que ya reclamó una clase de mayor prioridad.

    La resta se hace con el «Compuesto» de §4.3 y su lógica de tres valores, no
    con máscaras a mano, y eso importa en los dos sentidos:

    * donde una clase superior está activa CON CERTEZA, la inferior queda fuera
      aunque a la superior le falte algún otro operando (Kleene: `o` es cierto
      con certeza si un operando lo es);
    * donde no se sabe si la superior estaba activa, la inferior queda en
      «no se sabe» y su instante se cuenta como `SIN_DATOS`, no como suyo.
      Reclamar el instante sería afirmar que la superior no estaba, sin haberlo
      visto.

    El bucle recorre las cinco clases, no las muestras.
    """
    exclusivas: dict[ClaseDeSegmento, Condicion] = {}
    acumulada: Condicion | None = None
    for clase in _orden_de_precedencia():
        cond = condiciones.get(clase)
        if cond is None:
            continue
        exclusivas[clase] = cond if acumulada is None else cond.y(acumulada.no(), xp=xp)
        acumulada = cond if acumulada is None else acumulada.o(cond, xp=xp)
    return exclusivas


def _eventos_por_clase(
    exclusivas: Mapping[ClaseDeSegmento, Condicion],
    regimen: Serie,
    umbrales: UmbralesDeSegmentacion,
    permanencia_base: Permanencia,
    *,
    xp: Vectorial,
) -> tuple[tuple[Segmento, ...], dict[ClaseDeSegmento, int], dict[MotivoSinClasificar, int]]:
    """Los segmentos de cada clase, con su permanencia y su pico.

    Devuelve además cuántas muestras se quedaron por el camino y por qué, que es
    la mitad de `Cobertura`: sin ese reparto, un log con el 40 % sin clasificar
    no se puede diagnosticar.
    """
    segmentos: list[Segmento] = []
    por_clase: dict[ClaseDeSegmento, int] = {}
    descartadas: dict[MotivoSinClasificar, int] = {
        MotivoSinClasificar.DURACION_INSUFICIENTE: 0,
        MotivoSinClasificar.PENDIENTE_INSUFICIENTE: 0,
    }
    for clase, cond in exclusivas.items():  # bucle sobre CLASES
        permanencia = permanencia_base.fusionar(
            {"permanencia_s": umbrales.duracion_minima_s[clase]}
        )
        lista = eventos(
            cond,
            permanencia=permanencia,
            pico=Pico(serie=regimen, extremo=clase.extremo_del_pico),
            xp=xp,
        )
        reclamadas = int(xp.sum(cond.activa & cond.valido))
        aceptadas = 0
        sin_pendiente = 0
        for evento in lista:  # bucle sobre EVENTOS (acotado por maximo_de_eventos)
            if (
                clase is ClaseDeSegmento.WOT
                and _pendiente_rpm_por_s(regimen, evento) < umbrales.rpm_creciente_min_por_s
            ):
                sin_pendiente += evento.n_muestras
                continue
            segmentos.append(Segmento(clase=clase, evento=evento))
            aceptadas += evento.n_muestras
        por_clase[clase] = aceptadas
        descartadas[MotivoSinClasificar.PENDIENTE_INSUFICIENTE] += sin_pendiente
        descartadas[MotivoSinClasificar.DURACION_INSUFICIENTE] += (
            reclamadas - aceptadas - sin_pendiente
        )
    segmentos.sort(key=lambda s: s.evento.i_inicio)
    return tuple(segmentos), por_clase, descartadas


def _cobertura(
    exclusivas: Mapping[ClaseDeSegmento, Condicion],
    regimen: Serie,
    umbrales: UmbralesDeSegmentacion,
    *,
    por_clase: Mapping[ClaseDeSegmento, int],
    descartadas: Mapping[MotivoSinClasificar, int],
    xp: Vectorial,
) -> Cobertura:
    """Reparte las muestras de la rejilla entre las clases y los cinco motivos.

    Las tres máscaras del final —motor parado, sin datos y ninguna clase— se
    construyen restando, en este orden, de modo que son disjuntas por
    construcción y cubren exactamente lo que ninguna clase reclamó:

        alguna              alguna clase activa y válida (lo reclamado)
        motor_parado        no alguna, régimen válido y por debajo del mínimo
        sin_datos           no alguna, no parado, y ALGUNA clase no pudo decidir
        ninguna_clase       no alguna, no parado, y todas pudieron decidir que no

    El orden entre los dos últimos es el que hace honesta la cuenta: si una clase
    se quedó sin datos en ese instante, no se puede afirmar que ninguna definición
    se cumplía. Ver `MotivoSinClasificar.SIN_DATOS`.

    Que la suma cuadre con las muestras de la rejilla lo comprueba `Cobertura`, y
    ahí está el contrato: si dos clases hubieran reclamado la misma muestra,
    `reclamadas` sumaría más que `alguna` y la cuenta no cerraría.
    """
    n = len(regimen)
    valido_regimen = regimen.valido if regimen.valido is not None else regimen.t_ms == regimen.t_ms
    alguna: Any = None
    alguna_invalida: Any = None
    for cond in exclusivas.values():  # bucle sobre CLASES
        activa = cond.activa & cond.valido
        hueco = _no(cond.valido)
        alguna = activa if alguna is None else alguna | activa
        alguna_invalida = hueco if alguna_invalida is None else alguna_invalida | hueco
    if alguna is None:
        # Ninguna clase calculable: nada reclamado y nadie pudo decidir. `t != t`
        # es el vector de `False` de la longitud correcta sin pedirle `zeros` al
        # protocolo (mismo recurso que `primitivas._valido_de` con el signo
        # cambiado).
        alguna = regimen.t_ms != regimen.t_ms
        alguna_invalida = _no(alguna)
    fuera = _no(alguna)
    parado = fuera & valido_regimen & (regimen.v < umbrales.rpm_arranque_min)
    resto = fuera & _no(parado)
    sin_datos = resto & alguna_invalida
    ninguna = resto & _no(alguna_invalida)

    sin_clasificar = {
        MotivoSinClasificar.MOTOR_PARADO: int(xp.sum(parado)),
        MotivoSinClasificar.SIN_DATOS: int(xp.sum(sin_datos)),
        MotivoSinClasificar.DURACION_INSUFICIENTE: int(
            descartadas[MotivoSinClasificar.DURACION_INSUFICIENTE]
        ),
        MotivoSinClasificar.PENDIENTE_INSUFICIENTE: int(
            descartadas[MotivoSinClasificar.PENDIENTE_INSUFICIENTE]
        ),
        MotivoSinClasificar.NINGUNA_CLASE: int(xp.sum(ninguna)),
    }
    return Cobertura(muestras=n, por_clase=dict(por_clase), sin_clasificar=sin_clasificar)
