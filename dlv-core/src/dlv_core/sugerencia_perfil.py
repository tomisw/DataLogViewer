"""Autosugerencia de perfil por cobertura de roles (tarea F3-04).

`docs/02-alcance-y-plan.md` E4.5: «perfil Knock: 7 de 9 roles disponibles».
Dado un conjunto de perfiles (F3-01) y un log ya abierto, este módulo los
ordena por cuál encaja mejor, con esa cifra literal. No aplica ningún perfil
para dibujarlo -- eso es `aplicar_perfil` (F3-02) -- y no decide nada sobre
detectores -- eso es `activacion_detectores` (F3-08). Solo responde una
pregunta, antes de que el usuario abra nada: "¿qué perfil merece la pena
proponerle primero?"

CUATRO DECISIONES
==================

1. UN CANAL VACÍO NO CUENTA COMO "DISPONIBLE"
------------------------------------------------------------------------
`almacen.IndiceCanal` distingue `vacio` de `constante`/`fuera_de_rango`
(F1-07): un canal `vacio` no tiene ni una sola muestra en este log/segmento
concreto -- ocurre de verdad cuando el log viene de una tirada sin un módulo
presente (docs/03-arquitectura.md, F1-07). `aplicar_perfil.roles_disponibles`
no lo sabe ni tiene por qué saberlo: su trabajo es decidir qué ELEMENTO se
monta, y un canal vacío sí resuelve un rol sobre el papel -- el elemento se
monta, el panel se muestra "visible" -- así que sin este filtro la
autosugerencia recomendaría con seguridad un perfil cuyo panel estrella se
abre en blanco. Eso es peor que no recomendar nada: la promesa de E4.5 es
"esto va a funcionar", y una promesa que se rompe en el primer vistazo cuesta
más confianza que la ausencia de promesa.

`constante` y `fuera_de_rango`, en cambio, SÍ cuentan como disponible aquí:
un canal constante dibuja una línea plana real (un ralentí que se mantiene a
850 rpm es un dato, no un hueco) y uno fuera de rango dibuja datos
cuestionables pero dibuja algo. Solo la ausencia total de muestras justifica
tratar el rol como si no estuviera.

2. REQUERIDO PESA MÁS QUE OPCIONAL, Y EL CORTE ES POR PANEL -- REUTILIZADO,
   NO REPETIDO
------------------------------------------------------------------------
`perfil.py` (decisión 2) ya puso `requerido` en `ElementoDePanel`, no en el
perfil: un panel se oculta ENTERO si le falta uno de sus roles requeridos
(`Panel.roles_requeridos`), y `aplicar_perfil.EstadoPanel.visible` ya hace
exactamente esa comprobación. Reimplementarla aquí sería una segunda fuente
de verdad sobre qué hace que un panel se oculte, con el riesgo de que
diverja de la primera la próxima vez que alguien la toque. En vez de eso,
este módulo filtra los canales ANTES de llamar a `aplicar_perfil` (decisiones
1 y 3) y deja que `aplicar_perfil` decida la visibilidad de cada panel sobre
ese log "más pequeño" -- así "requerido pesa más que opcional" no es una
regla nueva, es la regla de F3-02 vista desde fuera: solo los roles de un
panel VISIBLE entran en el numerador de la cobertura del perfil
(`EstadoPanel.roles_disponibles_del_panel`); los de un panel oculto por un
requerido ausente no entran NINGUNO, aunque alguno de ellos sí se hubiera
podido montar -- "pierde el panel entero" es literal.

El denominador, en cambio, es `Perfil.roles_referenciados`: una propiedad del
perfil que no depende del log. No se reduce a "solo lo de los paneles
visibles" porque la cifra de E4.5 responde "¿qué le falta a ESTE perfil para
funcionar del todo?", y esa pregunta necesita el total real, no el total ya
recortado por lo que faltó.

3. UNA ASIGNACIÓN DIFUSA NO BASTA PARA RECOMENDAR, AUNQUE SÍ BASTE PARA DIBUJAR
------------------------------------------------------------------------
`aplicar_perfil` (decisión 2) monta un elemento con rol `DIFUSA` a propósito:
el usuario ya abrió el log, ve el dato crudo al lado de la etiqueta y puede
juzgar si el parecido de nombre acertó. Aquí el usuario TODAVÍA NO ha abierto
nada -- la autosugerencia le está diciendo "abre este perfil, te va a
servir" antes de que pueda comprobar nada por su cuenta. Apostar esa
afirmación a una conjetura no confirmada (`roles.Confianza.DIFUSA`,
"parecido de nombre, no una coincidencia de catálogo") tiene un coste
distinto: si falla, no es una fila fea en un panel que ya se está mirando,
es que la propia función de sugerencia enseñó a ignorarla. Por eso un canal
con asignación `DIFUSA` se descarta aquí exactamente igual que uno vacío
(mismo filtro, ver `_canales_utiles`): `EXACTA` e `INDEXADA` son, en palabras
de `roles.py`, "igual de firmes" entre sí -- ninguna de las dos es una
suposición -- así que las dos cuentan.

Un rol `id_nativo` no pasa por `Confianza` (`aplicar_perfil.CanalDeLogResuelto`
lo dice explícito) y no se ve afectado por este filtro: coincide exacto o no
coincide, no hay parecido que descartar.

4. EMPATES Y EL CASO DE CERO
------------------------------------------------------------------------
`sugerir_perfiles` devuelve TODOS los perfiles, ordenados, no solo "el
mejor": una pantalla de selección de perfil puede querer mostrar la tabla
completa, no solo el primero. El orden es determinista sin depender del
orden de entrada -- proporción de cobertura descendente, después el número
absoluto de roles disponibles (a igual proporción, más roles resueltos es
más evidencia), y como último desempate el nombre del perfil -- así que un
empate real (misma proporción Y mismo recuento) se rompe alfabéticamente en
vez de "el primero que llegó", que sería un orden que cambia según de dónde
vinieran los perfiles y no según ningún criterio.

"Ninguno encaja" es una respuesta legítima (probablemente mejor que
recomendar el menos malo, que es exactamente lo que evita): `mejor_sugerencia`
devuelve `None` si ni el primero de la lista llega a `cobertura_minima`. Esa
cifra no se deriva de ninguna constante física -- a diferencia de
`units.toml`, aquí no hay una definición de la que salga un número exacto --
así que se deja como `COBERTURA_MINIMA_POR_OMISION`, un parámetro con nombre
y valor por omisión documentado (mismo patrón que
`roles.UMBRAL_DIFUSO_POR_OMISION`), no una comparación cableada en medio de
la función: quien integre esto puede pasar otro valor sin tocar este módulo,
y si `data/umbrales.toml` gana algún día una entrada para esto, sustituirla
es cambiar el valor por omisión de un parámetro, no reescribir la lógica.

ADR-002 / ADR-009
==================
Sin E/S: recibe perfiles y canales ya resueltos. Recorre perfiles (una
decena) y sus paneles/roles (unas decenas cada uno), nunca muestras -- ADR-009
no exige vectorizar nada aquí, igual que en `aplicar_perfil`.

Solo biblioteca estándar y `dlv_core.aplicar_perfil` / `dlv_core.perfil` /
`dlv_core.roles`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dlv_core.aplicar_perfil import CanalDeLogResuelto, aplicar_perfil, roles_disponibles
from dlv_core.perfil import Perfil
from dlv_core.roles import Confianza

__all__ = [
    "COBERTURA_MINIMA_POR_OMISION",
    "CanalParaSugerencia",
    "SugerenciaPerfil",
    "mejor_sugerencia",
    "sugerir_perfiles",
]

COBERTURA_MINIMA_POR_OMISION = 0.5
"""Proporción mínima de `roles_referenciados` para que un perfil se pueda
recomendar (decisión 4). Por debajo de la mitad, más paneles del perfil se
van a ocultar o a mostrar a medias que los que van a funcionar, y
recomendarlo de todas formas decepciona en vez de ayudar. Es un valor
redondo y conservador, no derivado de ninguna medición -- por eso es un
parámetro con nombre y no una comparación cableada: ver la decisión 4 de la
cabecera del módulo."""


@dataclass(slots=True, frozen=True)
class CanalParaSugerencia:
    """Un canal resuelto (F3-02) más si está `vacio` en ESTE log (F1-07).

    `aplicar_perfil.CanalDeLogResuelto` no lleva esta información porque
    decidir qué se DIBUJA no la necesita (decisión 2 de `aplicar_perfil`: un
    rol `DIFUSA` se monta igual). Decidir qué se RECOMIENDA sí (decisión 1 de
    este módulo): un canal vacío resuelve su rol sobre el papel y no dibuja
    nada. No se añade el campo a `CanalDeLogResuelto` porque ese tipo es de
    F3-02 -- tarea cerrada, con otro trabajo en curso sobre el mismo fichero
    a la vez que este -- y añadir aquí un campo opcional que casi nadie más
    necesita sería ensuciar un tipo ajeno por comodidad de este módulo.
    """

    canal: CanalDeLogResuelto
    vacio: bool


def _canales_utiles(canales: Sequence[CanalParaSugerencia]) -> list[CanalDeLogResuelto]:
    """Los canales que sirven para RECOMENDAR, no los que sirven para dibujar.

    Dos filtros, uno por cada una de las decisiones 1 y 3 de la cabecera:
    fuera los vacíos y fuera las asignaciones `DIFUSA`. El resultado se le
    pasa a `aplicar_perfil` como si fuera el log completo -- así el resto de
    este módulo no reimplementa ninguna regla de paneles/roles: simplemente
    ve un log más pequeño que el real, y dentro de ese log más pequeño toda
    la lógica de F3-02 ya vale tal cual.
    """
    utiles: list[CanalDeLogResuelto] = []
    for c in canales:
        if c.vacio:
            continue
        asignacion = c.canal.asignacion
        if asignacion is not None and asignacion.confianza is Confianza.DIFUSA:
            continue
        utiles.append(c.canal)
    return utiles


@dataclass(slots=True, frozen=True)
class SugerenciaPerfil:
    """La cobertura de UN perfil contra un log, ya calculada.

    `disponibles`/`total` son la cifra literal de E4.5: cuántos de los roles
    que el perfil referencia (`Perfil.roles_referenciados`, TOTAL) están
    resueltos con una confianza firme, no vacíos, Y en un panel que además
    se puede mostrar (decisión 2: un panel oculto por un requerido ausente
    no aporta ninguno de sus roles al numerador, aunque alguno se hubiera
    podido montar).
    """

    perfil: Perfil
    disponibles: int
    total: int

    def __post_init__(self) -> None:
        if self.total < 0 or self.disponibles < 0:
            raise ValueError("`disponibles` y `total` no pueden ser negativos")
        if self.disponibles > self.total:
            raise ValueError(
                f"perfil '{self.perfil.nombre}': disponibles ({self.disponibles}) no puede "
                f"superar total ({self.total})"
            )

    @property
    def proporcion(self) -> float:
        """`disponibles / total`, o `0.0` si el perfil no referencia ningún
        rol (todo por `id_nativo`): no hay cobertura de roles que contar, no
        que la cobertura sea cero -- mismo criterio que
        `EstadoPanel.cobertura` en `aplicar_perfil`."""
        return self.disponibles / self.total if self.total else 0.0

    def es_recomendable(self, *, cobertura_minima: float = COBERTURA_MINIMA_POR_OMISION) -> bool:
        """`True` si esta cobertura basta para proponer el perfil (decisión 4).

        Un perfil sin ningún rol referenciado (`total == 0`) nunca es
        recomendable por cobertura de roles: no hay nada que medir, y
        "recomendarlo siempre" sería inventar una afirmación que esta cifra
        no puede respaldar.
        """
        return self.total > 0 and self.proporcion >= cobertura_minima

    def frase(self) -> str:
        """El texto literal de E4.5: «perfil Knock: 7 de 9 roles disponibles»."""
        return f"perfil {self.perfil.nombre}: {self.disponibles} de {self.total} roles disponibles"


def _cobertura_de(perfil: Perfil, canales_utiles: Sequence[CanalDeLogResuelto]) -> SugerenciaPerfil:
    estados = aplicar_perfil(perfil, canales_utiles)

    # Numerador: solo los roles de paneles VISIBLES (decisión 2 -- "pierde el
    # panel entero" es literal, así que un panel oculto no aporta ninguno).
    desde_paneles: frozenset[str] = frozenset()
    for estado in estados:
        if estado.visible:
            desde_paneles |= estado.roles_disponibles_del_panel

    # Un rol que el perfil solo referencia en un `LimiteDeAlerta` (no en
    # ningún elemento de panel) no tiene panel que lo module ni que lo
    # oculte: se cuenta como disponible directamente contra el log filtrado,
    # en vez de quedar sin poder contarse nunca por no pertenecer a ningún
    # `EstadoPanel`.
    roles_de_paneles: frozenset[str] = frozenset()
    for panel in perfil.paneles:
        roles_de_paneles |= panel.roles_referenciados
    roles_solo_de_limites = perfil.roles_referenciados - roles_de_paneles
    if roles_solo_de_limites:
        desde_paneles |= roles_solo_de_limites & roles_disponibles(canales_utiles)

    total = perfil.roles_referenciados
    return SugerenciaPerfil(perfil=perfil, disponibles=len(desde_paneles & total), total=len(total))


def sugerir_perfiles(
    perfiles: Sequence[Perfil], canales: Sequence[CanalParaSugerencia]
) -> tuple[SugerenciaPerfil, ...]:
    """Ordena TODOS los perfiles por cobertura, de mejor a peor (decisión 4).

    Orden determinista, sin depender de en qué posición llegó cada perfil:
    proporción descendente, después recuento absoluto de roles disponibles
    descendente (a igual proporción, más evidencia es mejor evidencia), y
    como último desempate el nombre del perfil. Devuelve todos, no solo el
    mejor -- una pantalla de selección puede querer la tabla completa; para
    "solo dame uno, o nada si ninguno encaja" está `mejor_sugerencia`.
    """
    utiles = _canales_utiles(canales)
    sugerencias = [_cobertura_de(perfil, utiles) for perfil in perfiles]
    return tuple(
        sorted(
            sugerencias,
            key=lambda s: (-s.proporcion, -s.disponibles, s.perfil.nombre),
        )
    )


def mejor_sugerencia(
    perfiles: Sequence[Perfil],
    canales: Sequence[CanalParaSugerencia],
    *,
    cobertura_minima: float = COBERTURA_MINIMA_POR_OMISION,
) -> SugerenciaPerfil | None:
    """El perfil que se le propondría al usuario primero, o `None`.

    `None` es la respuesta cuando ni el mejor de la lista llega a
    `cobertura_minima` (decisión 4): "ninguno encaja" es preferible a
    recomendar el menos malo, porque el menos malo por debajo del mínimo
    sigue siendo un perfil que decepciona más de lo que ayuda.
    """
    ordenados = sugerir_perfiles(perfiles, canales)
    if not ordenados:
        return None
    primero = ordenados[0]
    return primero if primero.es_recomendable(cobertura_minima=cobertura_minima) else None
