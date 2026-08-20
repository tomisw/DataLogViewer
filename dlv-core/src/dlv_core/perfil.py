"""Modelo del perfil de análisis `.dlvprofile` (F3-01).

`docs/02-alcance-y-plan.md` E4.1: «Modelo de perfil: paneles, roles semánticos,
unidades por dimensión, límites de alerta y detectores, en fichero
versionable.» `docs/04-perfiles-motorsport.md` §4.2 es la especificación viva:
los diez perfiles de fábrica que F3-03 va a escribir CON este módulo. Este
fichero es el esquema y el (de)serializador; no aplica un perfil a un log
(F3-02), no define los diez perfiles de fábrica (F3-03) ni el editor (F3-05).

Sigue el precedente de `dlv_core.perfil_importacion` (`.dlvimport`, FG-12) en
estructura y en criterio de rechazo, con las diferencias que exige un fichero
distinto: `.dlvprofile` es JSON versionado (`docs/03-arquitectura.md` §3.9),
no TOML, así que no hace falta un volcador propio como `_volcar_toml`.

LAS CUATRO DECISIONES DE ESTA TAREA
====================================

1. POR ROL, NUNCA POR ID NATIVO — CON UNA RESERVA EXPLÍCITA Y ESTRECHA
------------------------------------------------------------------------
`docs/07-formatos-y-csv-generico.md` §7.12: «Los 10 perfiles de fábrica se
definen por rol, con reserva a ID nativo para los canales muy específicos de
Haltech que no tienen rol universal (los cinco de `Transient Throttle`, los
términos PID de boost).» La independencia de fabricante —el motivo de que
exista un perfil en vez de una lista de canales— se pierde en cuanto un ID
nativo puede colarse como identidad primaria de un elemento sin que se note.

`ElementoDePanel` lo hace estructuralmente imposible de mezclar: `rol` e
`id_nativo` son mutuamente EXCLUYENTES (`__post_init__` lo comprueba, no un
comentario), y un elemento identificado por `id_nativo` **no puede ser
`requerido`**: un ID nativo solo existe en el formato que lo declaró, así que
exigirlo rompería la aplicación del perfil en cualquier otro formato — justo
lo que la reserva existe para no hacer. Comprobado contra §4.2: además de los
cinco de `Transient Throttle` (P5) y los términos PID de boost (P3), la
mayoría de P7 (trigger) y buena parte de P4/P6/P9 no tienen rol universal en
`data/roles.toml` — se anota en el informe de la tarea, no se inventa un rol
nuevo aquí (eso es competencia de F0-10, ya cerrada con puerta G1).

2. REQUERIDO VS OPCIONAL: GRANULARIDAD DE PANEL, NO DE PERFIL
------------------------------------------------------------------------
E4.3 pide «degradación elegante ocultando los paneles sin datos», no
«perfiles que se activan o no en bloque». Por eso `requerido` vive en
`ElementoDePanel`, no en el perfil: un panel se oculta si le falta alguno de
SUS roles requeridos (`Panel.roles_requeridos`), y un perfil con paneles
parcialmente disponibles se sigue aplicando — los paneles que sí tienen sus
roles se muestran, los que no, se ocultan. No hay un fallo "todo o nada" a
nivel de perfil: E4.5 («perfil Knock: 7 de 9 roles disponibles») presupone
justamente que un perfil parcialmente cubierto es un perfil utilizable con un
número de cobertura, no uno rechazado. La aplicación real de esa regla —qué
panel se oculta, cómo se calcula la cobertura contra un log concreto— es
F3-02/F3-04; este módulo solo expone lo que hace falta para calcularla:
`Panel.roles_requeridos`, `Panel.roles_opcionales`, `Perfil.roles_requeridos`,
`Perfil.roles_referenciados`.

Los `limites` (topes de alerta) y `detectores_activos` no tienen su propio
`requerido`: no bloquean nada por construcción. Un límite sobre un rol ausente
simplemente no se dibuja; un detector activo cuyos roles falten simplemente no
se ejecuta (esa desactivación ya la resuelve `dlv_core.activacion_detectores`,
F3-08, con su propio catálogo). Darles un `requerido` aquí sería inventar una
segunda noción de "requerido" con semántica distinta a la de los paneles, sin
que E4 la pida en ningún sitio.

3. LAS UNIDADES VAN POR DIMENSIÓN Y TODO SE GUARDA EN CANÓNICA
------------------------------------------------------------------------
`docs/06-sistema-de-unidades.md` §6.11: «Umbrales y alertas: se guardan en
canónica y se editan en la unidad activa.» Dos consecuencias en este esquema:

- `Perfil.unidades` es un `Mapping[str, str]` de `dimension_id -> unidad_id`,
  la MISMA forma que `resolucion_unidad.resolver_unidad` ya declara como su
  parámetro `preferencias_perfil` — su propio módulo (F1-17) lo deja escrito:
  «Cuando exista un modelo de perfil de verdad (F3-01), su capa de dimensiones
  puede pasarse aquí tal cual.» `Perfil.a_preferencias_unidad()` es
  exactamente ese "tal cual": sin traducción, mismo criterio que
  `PresetUsuario.a_mapeo()`. Elegir una forma distinta habría obligado a
  escribir una función de adaptación que no aporta nada y que podría divergir.
- `LimiteDeAlerta` reutiliza `dlv_core.topes.Tope` / `TopeDeBanda` (F3-10) en
  vez de reinventarlos: esos tipos ya declaran, en su propia cabecera, que se
  comparan en CANÓNICA («Los topes se declaran y se comparan en canónica, así
  que ... es directamente comparable con el canal»). El esquema no vuelve a
  tomar esa decisión, la hereda del módulo que ya la tomó y la tiene probada.
  Cambiar la unidad activa es, para un `.dlvprofile` ya guardado, exactamente
  lo que dice §6.11: un repintado, cero bytes reescritos en el fichero.

4. VERSIONADO: MISMO CRITERIO QUE `.dlvimport`, RECHAZO ENTERO
------------------------------------------------------------------------
`VERSION_ESQUEMA_PERFIL` sigue el precedente de
`perfil_importacion.VERSION_ESQUEMA_PERFIL_IMPORTACION` y de
`proyecto.VERSION_ESQUEMA_EMPAREJAMIENTOS`: sube solo si cambia la FORMA
(clave renombrada o movida), nunca por un campo opcional nuevo con valor por
omisión. Una versión desconocida se rechaza ENTERA
(`ErrorDeVersionDePerfilDesconocida`) en vez de leerse a medias — la misma
razón que dan los otros dos: un campo reinterpretado con las claves de hoy
produce un perfil que PARECE válido y no lo es, justo el error silencioso que
una puerta G1 no puede dejar pasar. Se decidió no apartarse del precedente
porque no hay ningún motivo nuevo en `.dlvprofile` que lo justifique.

ADR-002: NADA DE E/S AQUÍ
==========================
Igual que `perfil_importacion.py`: este módulo no abre ningún fichero.
`Perfil.a_texto_json()` / `.desde_texto_json()` trabajan sobre texto ya en
memoria; quien lee/escribe el `.dlvprofile` de disco es `dlv-api`.
`.a_dict()` / `.desde_dict()` son la forma intermedia sin fichero de por
medio, para pruebas y para quien prefiera componer el `dict` en otro sitio
(p. ej. dentro de un `.dlvproj` que embeba un perfil).

Solo biblioteca estándar (`json`, `dataclasses`, `typing`) más los tipos ya
existentes de `dlv_core.primitivas` y `dlv_core.topes`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dlv_core.primitivas import Direccion
from dlv_core.topes import (
    Curva,
    CurvaLineal,
    CurvaPorPuntos,
    ErrorDeTope,
    NivelDeTope,
    Tope,
    TopeDeBanda,
    validar_pareja,
)

__all__ = [
    "VERSION_ESQUEMA_PERFIL",
    "ElementoDePanel",
    "ErrorDePerfil",
    "ErrorDeVersionDePerfilDesconocida",
    "LimiteDeAlerta",
    "Panel",
    "Perfil",
]

VERSION_ESQUEMA_PERFIL = 1
"""Versión del bloque completo de `Perfil.a_dict()`. Sube solo si cambia la
FORMA (clave renombrada o movida), no por un campo opcional nuevo con valor
por omisión. Ver la decisión 4 en la cabecera del módulo."""


class ErrorDePerfil(ValueError):
    """Un `.dlvprofile` que no se puede leer sin que una persona lo corrija, o
    un perfil que se intenta construir en un estado que el esquema prohíbe
    (un ID nativo requerido, un límite sin ningún tope, dos paneles con el
    mismo rol duplicado dentro del mismo panel...). Se rechaza con un mensaje
    que dice QUÉ está mal y, cuando viene de `desde_dict`, DÓNDE — nunca con
    un `KeyError`/`TypeError` desnudo (mismo criterio que
    `ErrorDePerfilImportacion`)."""


class ErrorDeVersionDePerfilDesconocida(ErrorDePerfil):
    """`version_esquema` no es la que este `dlv-core` sabe leer. Deliberadamente
    no se intenta "leer lo que se pueda": ver la decisión 4 en la cabecera."""


# --------------------------------------------------------------------------- #
# Elemento de panel: identidad por ROL, con reserva explícita a ID nativo
# (decisión 1 de la cabecera del módulo).
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class ElementoDePanel:
    """Un canal dentro de un panel.

    `rol` y `id_nativo` son mutuamente excluyentes: exactamente uno de los dos
    tiene que estar presente. `rol` es el camino normal — independiente de
    fabricante — y `id_nativo` es la reserva explícita de §7.12 para un canal
    muy específico de un formato que no tiene rol universal. Marcarlo con
    `id_nativo` en vez de disfrazarlo de rol es lo que permite que la
    aplicación del perfil (F3-02) sepa que ese elemento SOLO funciona en el
    formato que lo declaró.

    `indice` es el número de instancia para un rol indexado (banco, cilindro,
    sensor, rueda — `data/roles.toml` campo `indexado`): por ejemplo
    `knock_level` con `indice=1` y otro elemento con `indice=2` para los dos
    sensores de knock de P2. No se valida contra `data/roles.toml` aquí
    (ADR-002, y este esquema no depende del catálogo de roles para construirse
    ni para leerse): esa validación semántica —¿existe el rol?, ¿admite
    índice?— es de quien aplica el perfil contra un catálogo cargado.

    `escala_min`/`escala_max` son un rango de eje Y opcional, en unidad
    CANÓNICA de la dimensión del rol (decisión 3): son límites ABSOLUTOS del
    canal, así que no necesitan `Clase` como los umbrales de `unidades.py` —
    un rango de eje siempre es un par de valores PUNTO, nunca una diferencia.
    `None` en cualquiera de los dos dice "escala automática", que es el caso
    de la inmensa mayoría de los elementos.
    """

    rol: str | None
    id_nativo: str | None
    requerido: bool
    indice: int | None = None
    escala_min: float | None = None
    escala_max: float | None = None

    def __post_init__(self) -> None:
        if (self.rol is None) == (self.id_nativo is None):
            raise ErrorDePerfil(
                "un elemento de panel necesita EXACTAMENTE UNO de `rol` o "
                "`id_nativo`: el rol es la identidad normal e independiente de "
                "fabricante; `id_nativo` es la reserva explícita para un canal muy "
                "específico de un formato que no tiene rol universal (docs/07 "
                "§7.12). Los dos a la vez, o ninguno, dejan sin decidir qué canal "
                "dibuja este elemento"
            )
        if self.rol is not None and not self.rol.strip():
            raise ErrorDePerfil("`rol` no puede ser una cadena vacía")
        if self.id_nativo is not None:
            if not self.id_nativo.strip():
                raise ErrorDePerfil("`id_nativo` no puede ser una cadena vacía")
            if self.requerido:
                raise ErrorDePerfil(
                    f"el elemento con id_nativo '{self.id_nativo}' no puede ser "
                    "`requerido`: un ID nativo solo existe en el formato que lo "
                    "declaró, así que exigirlo bloquearía este panel en cualquier "
                    "otro formato -- la independencia de fabricante que E4.1 exige "
                    "(docs/07 §7.12)"
                )
        if self.indice is not None and self.indice < 0:
            raise ErrorDePerfil(f"`indice` no puede ser negativo, y aquí es {self.indice}")
        if (
            self.escala_min is not None
            and self.escala_max is not None
            and self.escala_min >= self.escala_max
        ):
            raise ErrorDePerfil(
                f"escala_min ({self.escala_min}) debe ser menor que escala_max ({self.escala_max})"
            )

    @property
    def clave(self) -> tuple[str, int | None]:
        """`(rol, indice)` o `(id_nativo, indice)`: lo que distingue este
        elemento de otro dentro del mismo panel. Útil para detectar
        duplicados sin repetir la lógica en cada sitio que lo necesite."""
        identidad = self.rol if self.rol is not None else self.id_nativo
        assert identidad is not None  # garantizado por __post_init__
        return (identidad, self.indice)


def _elemento_a_dict(elemento: ElementoDePanel) -> dict[str, Any]:
    bruto: dict[str, Any] = {"requerido": elemento.requerido}
    if elemento.rol is not None:
        bruto["rol"] = elemento.rol
    if elemento.id_nativo is not None:
        bruto["id_nativo"] = elemento.id_nativo
    if elemento.indice is not None:
        bruto["indice"] = elemento.indice
    if elemento.escala_min is not None:
        bruto["escala_min"] = elemento.escala_min
    if elemento.escala_max is not None:
        bruto["escala_max"] = elemento.escala_max
    return bruto


def _texto_o_none(bruto: Any, clave: str, *, contexto: str) -> str | None:
    valor = bruto.get(clave)
    if valor is not None and not isinstance(valor, str):
        raise ErrorDePerfil(f"{contexto}: '{clave}' debe ser texto o estar ausente")
    return valor


def _float_o_none(bruto: Any, clave: str, *, contexto: str) -> float | None:
    valor = bruto.get(clave)
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorDePerfil(f"{contexto}: '{clave}' debe ser un número o estar ausente")
    return float(valor)


def _elemento_desde_dict(bruto: Mapping[str, Any], *, contexto: str) -> ElementoDePanel:
    rol = _texto_o_none(bruto, "rol", contexto=contexto)
    id_nativo = _texto_o_none(bruto, "id_nativo", contexto=contexto)
    requerido = bruto.get("requerido")
    if not isinstance(requerido, bool):
        raise ErrorDePerfil(f"{contexto}: 'requerido' debe ser verdadero/falso")
    indice = bruto.get("indice")
    if indice is not None and (isinstance(indice, bool) or not isinstance(indice, int)):
        raise ErrorDePerfil(f"{contexto}: 'indice' debe ser un entero o estar ausente")
    try:
        return ElementoDePanel(
            rol=rol,
            id_nativo=id_nativo,
            requerido=requerido,
            indice=indice,
            escala_min=_float_o_none(bruto, "escala_min", contexto=contexto),
            escala_max=_float_o_none(bruto, "escala_max", contexto=contexto),
        )
    except ErrorDePerfil as exc:
        raise ErrorDePerfil(f"{contexto}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Panel: un título y sus elementos (decisión 2 de la cabecera del módulo).
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class Panel:
    """Un panel del perfil: un título y sus elementos, en el orden en que se
    dibujan. Corresponde a una fila de la tabla de `docs/04` §4.2 (p. ej.
    «Carga», «Mezcla», «Estado» de P1), incluidos los paneles de "carriles"
    para canales enumerados o de máscara de bits — no llevan una marca
    especial en el esquema porque esa distinción ya la da la `dimension`
    (`enum`/`bitmask`) del rol en `data/roles.toml`; repetirla aquí sería una
    segunda fuente de verdad que podría desincronizarse de la primera.
    """

    titulo: str
    elementos: tuple[ElementoDePanel, ...]

    def __post_init__(self) -> None:
        if not self.titulo.strip():
            raise ErrorDePerfil("un panel necesita un `titulo` no vacío")
        if not self.elementos:
            raise ErrorDePerfil(f"el panel '{self.titulo}' no tiene ningún elemento")
        claves_vistas: set[tuple[str, int | None]] = set()
        for elemento in self.elementos:
            if elemento.clave in claves_vistas:
                raise ErrorDePerfil(
                    f"el panel '{self.titulo}' repite el elemento {elemento.clave}: "
                    "cada rol (con su índice, si lo tiene) o cada id_nativo aparece "
                    "una sola vez por panel"
                )
            claves_vistas.add(elemento.clave)

    @property
    def roles_requeridos(self) -> frozenset[str]:
        """Los roles cuya ausencia oculta este panel entero (decisión 2)."""
        return frozenset(e.rol for e in self.elementos if e.requerido and e.rol is not None)

    @property
    def roles_opcionales(self) -> frozenset[str]:
        """Los roles del panel que, si faltan, solo dejan ese elemento sin
        dibujar -- el panel se sigue mostrando con el resto."""
        return frozenset(e.rol for e in self.elementos if not e.requerido and e.rol is not None)

    @property
    def roles_referenciados(self) -> frozenset[str]:
        return self.roles_requeridos | self.roles_opcionales


def _panel_a_dict(panel: Panel) -> dict[str, Any]:
    return {
        "titulo": panel.titulo,
        "elementos": [_elemento_a_dict(e) for e in panel.elementos],
    }


def _panel_desde_dict(bruto: Any, *, indice: int) -> Panel:
    contexto = f"paneles[{indice}]"
    if not isinstance(bruto, Mapping):
        raise ErrorDePerfil(f"{contexto}: debe ser una tabla/objeto")
    titulo = bruto.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        raise ErrorDePerfil(f"{contexto}: 'titulo' debe ser texto no vacío")
    elementos_brutos = bruto.get("elementos")
    if not isinstance(elementos_brutos, list) or not elementos_brutos:
        raise ErrorDePerfil(f"{contexto}: 'elementos' debe ser una lista no vacía")
    elementos: list[ElementoDePanel] = []
    for i, elemento_bruto in enumerate(elementos_brutos):
        if not isinstance(elemento_bruto, Mapping):
            raise ErrorDePerfil(f"{contexto}.elementos[{i}]: debe ser una tabla/objeto")
        elementos.append(
            _elemento_desde_dict(elemento_bruto, contexto=f"{contexto}.elementos[{i}]")
        )
    try:
        return Panel(titulo=titulo, elementos=tuple(elementos))
    except ErrorDePerfil as exc:
        raise ErrorDePerfil(f"{contexto}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Límites de alerta por rol: reutiliza `dlv_core.topes` (decisión 3).
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class LimiteDeAlerta:
    """Los topes de alerta de UN rol dentro del perfil (`docs/04` §4.3: «Los
    límites viven en el perfil, así que un equipo puede tener un
    `limites-motor-A.dlvprofile` y compartirlo»).

    Reutiliza `dlv_core.topes.Tope` / `TopeDeBanda` (F3-10) en vez de
    duplicarlos: ya saben expresar un valor plano o una curva en función de
    otro rol, y ya se declaran y comparan en CANÓNICA (decisión 3 de la
    cabecera del módulo). Exactamente una de las dos formas describe el
    límite de un rol:

    - `topes`: cero, uno o dos `Tope` unidireccionales (aviso y/o crítico, en
      la misma dirección). Es el caso de D9 (sobretemperatura) o D6
      (sobrepresión).
    - `banda`: una `TopeDeBanda` de dos lados, cada lado opcionalmente una
      curva. Es el caso de la banda de λ objetivo, que se mueve con la carga.

    Las dos a la vez para el mismo rol serían dos afirmaciones distintas sobre
    el mismo canal, así que se rechazan.
    """

    rol: str
    topes: tuple[Tope, ...] = ()
    banda: TopeDeBanda | None = None

    def __post_init__(self) -> None:
        if not self.rol.strip():
            raise ErrorDePerfil("un límite de alerta necesita un `rol` no vacío")
        if self.topes and self.banda is not None:
            raise ErrorDePerfil(
                f"el rol '{self.rol}' declara topes unidireccionales Y una banda: son "
                "dos formas de expresar el límite y no se combinan para el mismo rol"
            )
        if not self.topes and self.banda is None:
            raise ErrorDePerfil(
                f"el rol '{self.rol}' no declara ningún tope ni banda: quita la "
                "entrada de `limites` en vez de dejarla vacía"
            )
        if len(self.topes) > 2:
            raise ErrorDePerfil(
                f"el rol '{self.rol}' declara {len(self.topes)} topes: solo hay dos "
                "niveles posibles, aviso y crítico"
            )
        niveles = [t.nivel for t in self.topes]
        if len(niveles) != len(set(niveles)):
            raise ErrorDePerfil(
                f"el rol '{self.rol}' declara más de un tope del mismo nivel "
                f"({[n.value for n in niveles]}): un aviso y un crítico, no dos "
                "del mismo"
            )
        if len(self.topes) == 2:
            por_nivel = {t.nivel: t for t in self.topes}
            aviso = por_nivel.get(NivelDeTope.AVISO)
            critico = por_nivel.get(NivelDeTope.CRITICO)
            if aviso is not None and critico is not None:
                try:
                    validar_pareja(aviso, critico)
                except ErrorDeTope as exc:
                    raise ErrorDePerfil(f"el rol '{self.rol}': {exc}") from exc


def _curva_a_dict(curva: Curva) -> dict[str, Any]:
    if isinstance(curva, CurvaLineal):
        return {
            "forma": "lineal",
            "rol_referencia": curva.rol_referencia,
            "base": curva.base,
            "pendiente": curva.pendiente,
            "divisor_referencia": curva.divisor_referencia,
        }
    return {
        "forma": "puntos",
        "rol_referencia": curva.rol_referencia,
        "puntos": [[x, y] for x, y in curva.puntos],
    }


def _curva_desde_dict(bruto: Mapping[str, Any], *, contexto: str) -> Curva:
    rol_referencia = bruto.get("rol_referencia")
    if not isinstance(rol_referencia, str) or not rol_referencia.strip():
        raise ErrorDePerfil(f"{contexto}: 'rol_referencia' debe ser texto no vacío")
    forma = bruto.get("forma")
    try:
        if forma == "lineal":
            curva: Curva = CurvaLineal(
                rol_referencia=rol_referencia,
                base=float(bruto["base"]),
                pendiente=float(bruto["pendiente"]),
                divisor_referencia=float(bruto["divisor_referencia"]),
            )
            return curva
        if forma == "puntos":
            puntos_brutos = bruto.get("puntos")
            if not isinstance(puntos_brutos, list):
                raise ErrorDePerfil(
                    f"{contexto}: 'puntos' debe ser una lista de pares [referencia, valor]"
                )
            puntos = tuple((float(p[0]), float(p[1])) for p in puntos_brutos)
            return CurvaPorPuntos(rol_referencia=rol_referencia, puntos=puntos)
    except KeyError as exc:
        raise ErrorDePerfil(f"{contexto}: falta la clave {exc} en una curva '{forma}'") from None
    except (TypeError, ValueError, IndexError) as exc:
        raise ErrorDePerfil(f"{contexto}: valores no numéricos en la curva: {exc}") from None
    except ErrorDeTope as exc:
        raise ErrorDePerfil(f"{contexto}: {exc}") from exc
    raise ErrorDePerfil(
        f"{contexto}: 'forma' de curva desconocida: {forma!r} (válidas: 'lineal', 'puntos')"
    )


def _valor_o_curva_a_dict(valor: float | Curva) -> Any:
    if isinstance(valor, (CurvaLineal, CurvaPorPuntos)):
        return _curva_a_dict(valor)
    return valor


def _valor_o_curva_desde_dict(bruto: Any, *, contexto: str) -> float | Curva:
    if isinstance(bruto, Mapping):
        return _curva_desde_dict(bruto, contexto=contexto)
    if isinstance(bruto, bool) or not isinstance(bruto, (int, float)):
        raise ErrorDePerfil(f"{contexto}: debe ser un número o una curva, y aquí es {bruto!r}")
    return float(bruto)


def _nivel_desde_bruto(bruto: Any, *, contexto: str) -> NivelDeTope:
    if not isinstance(bruto, str):
        raise ErrorDePerfil(f"{contexto}: 'nivel' debe ser texto")
    try:
        return NivelDeTope(bruto)
    except ValueError:
        validos = [n.value for n in NivelDeTope]
        raise ErrorDePerfil(
            f"{contexto}: 'nivel' desconocido {bruto!r}; válidos: {validos}"
        ) from None


def _direccion_desde_bruto(bruto: Any, *, contexto: str) -> Direccion:
    if not isinstance(bruto, str):
        raise ErrorDePerfil(f"{contexto}: 'direccion' debe ser texto")
    try:
        return Direccion(bruto)
    except ValueError:
        validas = [d.value for d in Direccion]
        raise ErrorDePerfil(
            f"{contexto}: 'direccion' desconocida {bruto!r}; válidas: {validas}"
        ) from None


def _tope_a_dict(tope: Tope) -> dict[str, Any]:
    return {
        "nivel": tope.nivel.value,
        "direccion": tope.direccion.value,
        "valor": _valor_o_curva_a_dict(tope.valor),
    }


def _tope_desde_dict(bruto: Mapping[str, Any], *, contexto: str) -> Tope:
    nivel = _nivel_desde_bruto(bruto.get("nivel"), contexto=contexto)
    direccion = _direccion_desde_bruto(bruto.get("direccion"), contexto=contexto)
    if "valor" not in bruto:
        raise ErrorDePerfil(f"{contexto}: falta 'valor'")
    valor = _valor_o_curva_desde_dict(bruto["valor"], contexto=f"{contexto}.valor")
    return Tope(nivel=nivel, direccion=direccion, valor=valor)


def _banda_a_dict(banda: TopeDeBanda) -> dict[str, Any]:
    return {
        "nivel": banda.nivel.value,
        "minimo": _valor_o_curva_a_dict(banda.minimo),
        "maximo": _valor_o_curva_a_dict(banda.maximo),
    }


def _banda_desde_dict(bruto: Mapping[str, Any], *, contexto: str) -> TopeDeBanda:
    nivel = _nivel_desde_bruto(bruto.get("nivel"), contexto=contexto)
    if "minimo" not in bruto or "maximo" not in bruto:
        raise ErrorDePerfil(f"{contexto}: una banda necesita 'minimo' y 'maximo'")
    minimo = _valor_o_curva_desde_dict(bruto["minimo"], contexto=f"{contexto}.minimo")
    maximo = _valor_o_curva_desde_dict(bruto["maximo"], contexto=f"{contexto}.maximo")
    return TopeDeBanda(nivel=nivel, minimo=minimo, maximo=maximo)


def _limite_a_dict(limite: LimiteDeAlerta) -> dict[str, Any]:
    bruto: dict[str, Any] = {"rol": limite.rol}
    if limite.topes:
        bruto["topes"] = [_tope_a_dict(t) for t in limite.topes]
    if limite.banda is not None:
        bruto["banda"] = _banda_a_dict(limite.banda)
    return bruto


def _limite_desde_dict(bruto: Any, *, indice: int) -> LimiteDeAlerta:
    contexto = f"limites[{indice}]"
    if not isinstance(bruto, Mapping):
        raise ErrorDePerfil(f"{contexto}: debe ser una tabla/objeto")
    rol = bruto.get("rol")
    if not isinstance(rol, str) or not rol.strip():
        raise ErrorDePerfil(f"{contexto}: 'rol' debe ser texto no vacío")
    topes_brutos = bruto.get("topes", [])
    if not isinstance(topes_brutos, list):
        raise ErrorDePerfil(f"{contexto}: 'topes' debe ser una lista")
    topes: list[Tope] = []
    for i, tope_bruto in enumerate(topes_brutos):
        if not isinstance(tope_bruto, Mapping):
            raise ErrorDePerfil(f"{contexto}.topes[{i}]: debe ser una tabla/objeto")
        topes.append(_tope_desde_dict(tope_bruto, contexto=f"{contexto}.topes[{i}]"))
    banda_bruto = bruto.get("banda")
    if banda_bruto is not None and not isinstance(banda_bruto, Mapping):
        raise ErrorDePerfil(f"{contexto}.banda: debe ser una tabla/objeto")
    banda = _banda_desde_dict(banda_bruto, contexto=f"{contexto}.banda") if banda_bruto else None
    try:
        return LimiteDeAlerta(rol=rol, topes=tuple(topes), banda=banda)
    except ErrorDePerfil as exc:
        raise ErrorDePerfil(f"{contexto}: {exc}") from exc


# --------------------------------------------------------------------------- #
# El perfil completo
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class Perfil:
    """Un `.dlvprofile` en memoria.

    `unidades` es `dimension_id -> unidad_id`, la misma forma que
    `resolucion_unidad.resolver_unidad` espera en `preferencias_perfil`
    (decisión 3 de la cabecera del módulo): `a_preferencias_unidad()` la
    entrega tal cual, sin conversión.

    `eje_x_preferido` es `None` (tiempo, el eje por omisión de los diez
    perfiles de fábrica) o el id de un rol a usar como eje X — el caso de un
    perfil pensado para la malla RPM×MAP (`docs/04` §4.4/§4.6). Es un campo de
    todo el perfil, no de cada panel: `docs/02` E4.1 lo enumera en singular
    junto a paneles/unidades/límites/detectores como un atributo del perfil.

    `detectores_activos` son identificadores del catálogo de `data/umbrales.toml`
    (`[detectores.DN]`, F3-07) que este perfil activa -- referencias por
    cadena, no la definición del detector: la definición es del catálogo
    factory, compartida entre todos los perfiles; el perfil solo dice CUÁLES
    quiere encendidos, igual que `docs/04` §4.1 lo describe («detectores
    activos»).
    """

    nombre: str
    descripcion: str
    paneles: tuple[Panel, ...]
    unidades: Mapping[str, str]
    limites: tuple[LimiteDeAlerta, ...] = ()
    detectores_activos: tuple[str, ...] = ()
    eje_x_preferido: str | None = None

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise ErrorDePerfil("un perfil necesita un `nombre` no vacío")
        if not self.paneles:
            raise ErrorDePerfil(f"el perfil '{self.nombre}' no tiene ningún panel")
        for dimension_id, id_unidad in self.unidades.items():
            if not dimension_id.strip() or not id_unidad.strip():
                raise ErrorDePerfil(
                    f"el perfil '{self.nombre}': 'unidades' tiene una entrada vacía "
                    f"({dimension_id!r} -> {id_unidad!r})"
                )
        roles_con_limite: set[str] = set()
        for limite in self.limites:
            if limite.rol in roles_con_limite:
                raise ErrorDePerfil(
                    f"el perfil '{self.nombre}' declara más de un límite de alerta "
                    f"para el rol '{limite.rol}': solo puede haber uno, con su tope o "
                    "su banda, por rol"
                )
            roles_con_limite.add(limite.rol)
        if len(self.detectores_activos) != len(set(self.detectores_activos)):
            raise ErrorDePerfil(
                f"el perfil '{self.nombre}' repite un detector en `detectores_activos`: "
                f"{self.detectores_activos}"
            )
        if self.eje_x_preferido is not None and not self.eje_x_preferido.strip():
            raise ErrorDePerfil("`eje_x_preferido` no puede ser una cadena vacía")

    # ----------------------------------------------------------------- #
    # Cobertura de roles (decisión 2): lo que necesita F3-04 para calcular
    # «perfil Knock: 7 de 9 roles disponibles» (E4.5). Este módulo solo
    # agrega lo que ya sabe cada panel; no compara contra ningún log.
    # ----------------------------------------------------------------- #
    @property
    def roles_requeridos(self) -> frozenset[str]:
        salida: set[str] = set()
        for panel in self.paneles:
            salida |= panel.roles_requeridos
        return frozenset(salida)

    @property
    def roles_referenciados(self) -> frozenset[str]:
        """Todos los roles que este perfil menciona: en paneles y en límites
        de alerta (incluida la referencia de una curva). Es el denominador de
        la cobertura de E4.5; `roles_requeridos` es el subconjunto que además
        controla si un panel se oculta."""
        salida: set[str] = set()
        for panel in self.paneles:
            salida |= panel.roles_referenciados
        for limite in self.limites:
            salida.add(limite.rol)
            for tope in limite.topes:
                if isinstance(tope.valor, (CurvaLineal, CurvaPorPuntos)):
                    salida.add(tope.valor.rol_referencia)
            if limite.banda is not None:
                for lado in (limite.banda.minimo, limite.banda.maximo):
                    if isinstance(lado, (CurvaLineal, CurvaPorPuntos)):
                        salida.add(lado.rol_referencia)
        return frozenset(salida)

    def a_preferencias_unidad(self) -> Mapping[str, str]:
        """La forma exacta que espera
        `resolucion_unidad.resolver_unidad(..., preferencias_perfil=...)`.
        Sin conversión: `unidades` YA ES esa forma (mismo motivo que
        `PresetUsuario.a_mapeo()`)."""
        return self.unidades

    # ----------------------------------------------------------------- #
    # dict <-> JSON
    # ----------------------------------------------------------------- #
    def a_dict(self) -> dict[str, Any]:
        return {
            "version_esquema": VERSION_ESQUEMA_PERFIL,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "eje_x_preferido": self.eje_x_preferido,
            "unidades": dict(self.unidades),
            "paneles": [_panel_a_dict(p) for p in self.paneles],
            "limites": [_limite_a_dict(limite) for limite in self.limites],
            "detectores_activos": list(self.detectores_activos),
        }

    def a_texto_json(self) -> str:
        """El texto JSON completo del `.dlvprofile`. Quien lo escribe a disco
        es `dlv-api` (ADR-002): esta función solo produce el texto."""
        return json.dumps(self.a_dict(), ensure_ascii=False, sort_keys=True, indent=2)

    @staticmethod
    def desde_dict(bruto: Mapping[str, Any]) -> Perfil:
        try:
            version = bruto["version_esquema"]
        except KeyError as exc:
            raise ErrorDePerfil(f"perfil de análisis incompleto: falta la clave {exc}") from None
        if version != VERSION_ESQUEMA_PERFIL:
            raise ErrorDeVersionDePerfilDesconocida(
                f"este .dlvprofile declara la versión de esquema {version!r} y este "
                f"dlv-core solo sabe leer la versión {VERSION_ESQUEMA_PERFIL}. Ábrelo "
                "con una versión de DataLogViewer que la reconozca"
            )

        nombre = bruto.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            raise ErrorDePerfil("perfil de análisis: 'nombre' debe ser texto no vacío")
        descripcion = bruto.get("descripcion", "")
        if not isinstance(descripcion, str):
            raise ErrorDePerfil("perfil de análisis: 'descripcion' debe ser texto")
        eje_x_preferido = bruto.get("eje_x_preferido")
        if eje_x_preferido is not None and not isinstance(eje_x_preferido, str):
            raise ErrorDePerfil(
                "perfil de análisis: 'eje_x_preferido' debe ser texto o estar ausente/null"
            )

        unidades_brutas = bruto.get("unidades", {})
        if not isinstance(unidades_brutas, Mapping):
            raise ErrorDePerfil(
                "perfil de análisis: 'unidades' debe ser un objeto dimension_id -> unidad_id"
            )
        unidades = {str(k): str(v) for k, v in unidades_brutas.items()}

        paneles_brutos = bruto.get("paneles")
        if not isinstance(paneles_brutos, list) or not paneles_brutos:
            raise ErrorDePerfil("perfil de análisis: 'paneles' debe ser una lista no vacía")
        paneles = tuple(_panel_desde_dict(p, indice=i) for i, p in enumerate(paneles_brutos))

        limites_brutos = bruto.get("limites", [])
        if not isinstance(limites_brutos, list):
            raise ErrorDePerfil("perfil de análisis: 'limites' debe ser una lista")
        limites = tuple(
            _limite_desde_dict(limite, indice=i) for i, limite in enumerate(limites_brutos)
        )

        detectores_brutos = bruto.get("detectores_activos", [])
        if not isinstance(detectores_brutos, list) or not all(
            isinstance(d, str) and d.strip() for d in detectores_brutos
        ):
            raise ErrorDePerfil(
                "perfil de análisis: 'detectores_activos' debe ser una lista de cadenas no vacías"
            )

        try:
            return Perfil(
                nombre=nombre,
                descripcion=descripcion,
                paneles=paneles,
                unidades=unidades,
                limites=limites,
                detectores_activos=tuple(detectores_brutos),
                eje_x_preferido=eje_x_preferido,
            )
        except ErrorDePerfil as exc:
            raise ErrorDePerfil(f"perfil de análisis: {exc}") from exc

    @staticmethod
    def desde_texto_json(texto: str) -> Perfil:
        try:
            bruto = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise ErrorDePerfil(f"perfil de análisis: JSON inválido: {exc}") from None
        if not isinstance(bruto, Mapping):
            raise ErrorDePerfil("perfil de análisis: la raíz del JSON debe ser un objeto")
        return Perfil.desde_dict(bruto)
