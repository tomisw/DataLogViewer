"""Pruebas de la resolución de conflictos de unidad entre logs (F2-13).

Especificación: `docs/02-alcance-y-plan.md` §2.5 **E2.7** y
`docs/06-sistema-de-unidades.md` §6.5, §6.6 y §6.8.

QUÉ PROTEGE ESTA SUITE, ORDENADA POR LA CONSECUENCIA DE ROMPER CADA REGLA
=========================================================================
1. **Nunca mezcla silenciosa.** Todo resultado que no sea `COMPARABLE` lleva al
   menos un aviso que nombra los logs, el rol y el motivo. Un conflicto sin aviso
   es el peor resultado posible de esta tarea: el usuario ve dos curvas que
   parecen comparables y no lo son, y no hay nada en la pantalla que lo delate.
2. **Dos dimensiones distintas no se resuelven convirtiendo, ni por mayoría.**
   Superponer una presión y una temperatura porque «cuatro logs de cinco decían
   presión» esconde el error que hay que corregir.
3. **El caso normal no lleva aviso.** °C contra °F se compara en K y en silencio.
   Avisar de lo normal enseña a ignorar los avisos, y entonces el aviso de la
   regla 1 tampoco se lee.
4. **Los factores distintos NO son un conflicto.** deciKelvin contra Kelvin es un
   factor 10 y las dos escalas son correctas: `to_canon` absorbe la escala de
   almacenamiento. Un criterio que compare factores es un generador de falsos
   positivos sobre datos sanos, y esta suite lo fija con un caso explícito.
5. **La amplitud declarada se convierte como INTERVALO.** Con la clase PUNTO, un
   canal en °C tendría 283 K de amplitud en lugar de 10 y se le acusaría de
   incoherente. Es la trampa del delta de F1-20 en un sitio nuevo.
6. **Sin valor canónico no se compara, y no se inventa uno.** `confianza =
   "unknown"` y presión relativa sin referencia quedan fuera con su aviso, no
   dentro con una suposición plausible.

Solo biblioteca estándar (no hay NumPy ni Polars en juego: esto son metadatos).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlv_core.conflictos import (
    RAZON_DE_AMPLITUD_MAXIMA,
    Comparabilidad,
    DeclaracionDeCanal,
    ErrorDeConflicto,
    Motivo,
    OrigenDePresion,
    RangoDeclarado,
    ResolucionDeRol,
    resolver_conflictos,
    resolver_conflictos_de_rol,
)
from dlv_core.unidades import Afin, Catalogo, Clase, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
CATALOGO_TOML = RAIZ / "data" / "units.toml"


@pytest.fixture(scope="module")
def cat() -> Catalogo:
    with CATALOGO_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


def decl(
    segmento: str,
    *,
    dimension: str | None = "temperature",
    a: float = 0.1,
    b: float = 0.0,
    confianza: str = "confirmed",
    unidad_origen: str | None = None,
    rango: tuple[float, float] | None = None,
    origen: OrigenDePresion | None = None,
    referencia_kpa: float | None = None,
    id_canal: str | None = None,
) -> DeclaracionDeCanal:
    """Una declaración de canal con los valores por omisión del caso Haltech.

    `a = 0,1` es la escala real del tipo `Temperature` (deciKelvin -> K, docs/01
    §1.8), para que los casos se lean como los datos de verdad.
    """
    return DeclaracionDeCanal(
        id_segmento=segmento,
        id_canal=id_canal or f"c{segmento}",
        dimension=dimension,
        escala=Afin(a, b),
        confianza=confianza,
        unidad_origen=unidad_origen,
        rango_declarado=None if rango is None else RangoDeclarado(rango[0], rango[1]),
        origen_presion=origen,
        referencia_kpa=referencia_kpa,
    )


def codigos(r: ResolucionDeRol) -> list[str]:
    return [a.codigo for a in r.avisos]


# --------------------------------------------------------------------------- #
# 1. Nunca mezcla silenciosa: el invariante del módulo
# --------------------------------------------------------------------------- #
CASOS_DEL_INVARIANTE = {
    "dimensiones_distintas": [decl("a"), decl("b", dimension="pressure")],
    "sin_dimension": [decl("a"), decl("b", dimension=None)],
    "dimension_desconocida": [decl("a"), decl("b", dimension="no_existe")],
    "escala_sin_confirmar": [decl("a"), decl("b", confianza="unknown")],
    "unidad_ajena": [decl("a"), decl("b", unidad_origen="psi")],
    "amplitud_incoherente": [
        decl("a", dimension="pressure", a=0.1, rango=(0.0, 4000.0)),
        decl("b", dimension="pressure", a=0.1, rango=(0.0, 4000000.0)),
    ],
    "rangos_disjuntos": [
        decl("a", a=0.1, b=0.0, rango=(2331.0, 4731.0)),
        decl("b", a=0.1, b=273.15, rango=(2331.0, 4731.0)),
    ],
    "presion_relativa_sin_referencia": [
        decl("a", dimension="pressure", origen=OrigenDePresion.ABSOLUTA),
        decl("b", dimension="pressure", origen=OrigenDePresion.RELATIVA),
    ],
    "presion_llevada_a_absoluta": [
        decl("a", dimension="pressure", origen=OrigenDePresion.ABSOLUTA),
        decl("b", dimension="pressure", origen=OrigenDePresion.RELATIVA, referencia_kpa=101.325),
    ],
    "origen_de_presion_sin_declarar": [
        decl("a", dimension="pressure", origen=OrigenDePresion.ABSOLUTA),
        decl("b", dimension="pressure"),
    ],
    "ningun_origen_declarado": [decl("a", dimension="pressure"), decl("b", dimension="pressure")],
}


@pytest.mark.parametrize("caso", sorted(CASOS_DEL_INVARIANTE))
def test_todo_lo_que_no_es_comparable_lleva_aviso(cat: Catalogo, caso: str) -> None:
    """La regla 1, sobre todos los casos que el módulo sabe detectar.

    Y al revés: el aviso tiene que nombrar el rol y los logs, porque un aviso que
    solo dice «hay un conflicto de unidades» no se puede accionar.
    """
    r = resolver_conflictos_de_rol("rol:x", CASOS_DEL_INVARIANTE[caso], catalogo=cat)
    assert r.comparabilidad is not Comparabilidad.COMPARABLE, caso
    assert r.avisos, f"{caso}: conflicto sin aviso, que es el peor resultado posible"
    for aviso in r.avisos:
        assert "rol:x" in aviso.mensaje, f"{caso}: el aviso no dice de qué rol habla"
        assert any(log in aviso.mensaje for log in ("'a'", "'b'")), (
            f"{caso}: el aviso no nombra ningún log"
        )
    assert r.hay_conflicto


def test_no_comparable_nunca_ofrece_media_comparacion(cat: Catalogo) -> None:
    """Si no se puede comparar, `comparables` está vacío.

    Devolver un log «comparable» consigo mismo invitaría a la interfaz a dibujar
    la superposición de todas formas.
    """
    r = resolver_conflictos_de_rol(
        "rol:x", [decl("a"), decl("b", dimension="pressure")], catalogo=cat
    )
    assert r.comparabilidad is Comparabilidad.NO_COMPARABLE
    assert r.comparables == ()
    assert r.unidad_canonica is None


# --------------------------------------------------------------------------- #
# 2. El caso normal de E2.7: mismas dimensiones, unidades de origen distintas
# --------------------------------------------------------------------------- #
def test_celsius_contra_fahrenheit_se_comparan_en_kelvin_y_sin_aviso(cat: Catalogo) -> None:
    """E2.7 literal: «ambos a canónica y se comparan». Y en silencio.

    Los dos logs traen la misma magnitud declarada en unidades distintas y con
    escalas de origen distintas (uno °C en décimas, otro °F en centésimas). No hay
    nada que advertir: para eso existe la canónica (§6.11, fila «Multi-log»).
    """
    r = resolver_conflictos_de_rol(
        "rol:coolant_temp",
        [
            decl("a", a=0.1, b=273.15, unidad_origen="degC", rango=(-400.0, 2000.0)),
            decl("b", a=0.01, b=255.372_222, unidad_origen="degF", rango=(-4000.0, 39200.0)),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.COMPARABLE
    assert r.avisos == ()
    assert r.dimension == "temperature"
    assert r.unidad_canonica == "K"
    assert r.comparables == ("a", "b")
    assert r.unidades_de_origen == ("degC", "degF")
    assert r.escala_comprobada


def test_los_alias_no_cuentan_como_unidades_distintas(cat: Catalogo) -> None:
    """«mbar» y «hPa» son la misma unidad: anunciar dos sería inventar una
    diferencia que no existe."""
    r = resolver_conflictos_de_rol(
        "rol:map",
        [
            decl("a", dimension="pressure", unidad_origen="mbar", origen=OrigenDePresion.ABSOLUTA),
            decl("b", dimension="pressure", unidad_origen="hPa", origen=OrigenDePresion.ABSOLUTA),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.COMPARABLE
    assert r.unidades_de_origen == ("hPa",)


def test_factores_muy_distintos_no_son_un_conflicto(cat: Catalogo) -> None:
    """La regla 4, y el falso positivo que el criterio obvio habría producido.

    Un Haltech guarda deciKelvin (`a = 0,1`) y un CSV genérico Kelvin flotantes
    (`a = 1,0`): un factor 10 entre las dos escalas, las dos correctas. Un
    criterio que comparara `to_canon` marcaría esto como incoherente y dejaría de
    poder superponer dos logs perfectamente sanos.
    """
    r = resolver_conflictos_de_rol(
        "rol:coolant_temp",
        [
            decl("a", a=0.1, rango=(2331.0, 4731.0)),
            decl("b", a=1.0, rango=(233.1, 473.1)),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.COMPARABLE
    assert r.avisos == ()
    assert r.escala_comprobada


def test_rangos_de_presentacion_distintos_no_son_un_conflicto(cat: Catalogo) -> None:
    """Un atmosférico 0–100 kPa contra un sobrealimentado 0–400 kPa es un 4.

    Está muy por debajo del orden de magnitud: fijar el umbral por debajo de esto
    convertiría el aviso en ruido y el usuario lo apagaría.
    """
    r = resolver_conflictos_de_rol(
        "rol:map",
        [
            decl(
                "a",
                dimension="pressure",
                a=0.1,
                rango=(0.0, 1000.0),
                origen=OrigenDePresion.ABSOLUTA,
            ),
            decl(
                "b",
                dimension="pressure",
                a=0.1,
                rango=(0.0, 4000.0),
                origen=OrigenDePresion.ABSOLUTA,
            ),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.COMPARABLE
    assert r.escala_comprobada


# --------------------------------------------------------------------------- #
# 3. Dimensiones distintas: el conflicto que no se resuelve convirtiendo
# --------------------------------------------------------------------------- #
def test_dimensiones_distintas_no_se_mezclan(cat: Catalogo) -> None:
    r = resolver_conflictos_de_rol(
        "rol:x",
        [decl("a", dimension="pressure"), decl("b", dimension="temperature")],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.NO_COMPARABLE
    assert r.motivos == (Motivo.DIMENSIONES_DISTINTAS,)
    assert r.dimension is None
    (aviso,) = r.avisos
    # El aviso tiene que decir QUÉ log declara QUÉ, o no se puede corregir.
    assert "pressure" in aviso.mensaje and "temperature" in aviso.mensaje
    assert "'a'" in aviso.mensaje and "'b'" in aviso.mensaje


def test_la_dimension_no_se_decide_por_mayoria(cat: Catalogo) -> None:
    """Cuatro logs en `pressure` y uno en `temperature` siguen sin comparar.

    Quedarse con los cuatro sería decidir por popularidad qué mide el rol y
    esconder el error de verdad, que está en el quinto.
    """
    r = resolver_conflictos_de_rol(
        "rol:x",
        [
            *(decl(s, dimension="pressure", origen=OrigenDePresion.ABSOLUTA) for s in "abcd"),
            decl("e", dimension="temperature"),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.NO_COMPARABLE
    assert r.comparables == ()
    assert r.segmentos == ("a", "b", "c", "d", "e")


# --------------------------------------------------------------------------- #
# 4. Escala incoherente
# --------------------------------------------------------------------------- #
def test_kpa_contra_pa_mal_declarado_no_se_mezcla(cat: Catalogo) -> None:
    """El caso de la especificación: un factor mil en la magnitud declarada.

    Los dos logs declaran presión y su rango de presentación en crudo es el mismo,
    pero uno lleva la escala mil veces mayor: en canónica uno vive entre 0 y 400
    kPa y el otro entre 0 y 400 000 kPa. Superponerlos daría una curva pegada al
    cero y otra ocupando todo el panel, o —con autoescala por eje— dos curvas de
    aspecto comparable con un factor mil de por medio.
    """
    r = resolver_conflictos_de_rol(
        "rol:map",
        [
            decl(
                "a",
                dimension="pressure",
                a=0.1,
                rango=(0.0, 4000.0),
                origen=OrigenDePresion.ABSOLUTA,
            ),
            decl(
                "b",
                dimension="pressure",
                a=100.0,
                rango=(0.0, 4000.0),
                origen=OrigenDePresion.ABSOLUTA,
            ),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.NO_COMPARABLE
    assert Motivo.AMPLITUD_INCOHERENTE in r.motivos
    assert r.comparables == ()
    # La escala SÍ se comprobó: aquí `escala_comprobada` no puede ser lo mismo que
    # en un rol sin rango declarado, donde no se sabe.
    assert r.escala_comprobada
    (aviso,) = r.avisos
    assert "kPa" in aviso.mensaje


def test_grados_celsius_tomados_por_kelvin_se_detectan_por_el_rango(cat: Catalogo) -> None:
    """El error de desplazamiento, que la amplitud NO ve.

    Los dos rangos tienen la misma amplitud (240 K), así que el criterio del
    factor no dice nada; están desplazados 273,15 K, que es exactamente el error
    de tomar °C por K, y sus rangos canónicos no se solapan.
    """
    r = resolver_conflictos_de_rol(
        "rol:coolant_temp",
        [
            decl("a", a=0.1, b=0.0, rango=(2331.0, 4731.0)),
            decl("b", a=0.1, b=273.15, rango=(2331.0, 4731.0)),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.NO_COMPARABLE
    assert Motivo.RANGOS_DISJUNTOS in r.motivos


def test_el_umbral_de_amplitud_es_un_parametro(cat: Catalogo) -> None:
    """Regla 3 del proyecto: un umbral cableado es una opinión disfrazada de
    física. El mismo caso cambia de resultado si cambia el criterio."""
    caso = [
        decl(
            "a", dimension="pressure", a=0.1, rango=(0.0, 1000.0), origen=OrigenDePresion.ABSOLUTA
        ),
        decl(
            "b", dimension="pressure", a=0.5, rango=(0.0, 1000.0), origen=OrigenDePresion.ABSOLUTA
        ),
    ]
    assert RAZON_DE_AMPLITUD_MAXIMA == 10.0
    laxo = resolver_conflictos_de_rol("rol:map", caso, catalogo=cat)
    assert laxo.comparabilidad is Comparabilidad.COMPARABLE
    estricto = resolver_conflictos_de_rol(
        "rol:map", caso, catalogo=cat, razon_de_amplitud_maxima=5.0
    )
    assert estricto.comparabilidad is Comparabilidad.NO_COMPARABLE
    assert Motivo.AMPLITUD_INCOHERENTE in estricto.motivos


def test_sin_rango_declarado_la_escala_no_esta_comprobada(cat: Catalogo) -> None:
    """13 de los 475 canales del AutoLog no traen `DisplayMaxMin`.

    Ahí la coherencia de escala no se puede comprobar, y `escala_comprobada`
    tiene que decirlo: «no se sabe» no es «está bien». Se sigue comparando —es lo
    único que se puede hacer con dos declaraciones coherentes entre sí— pero sin
    afirmar que la escala se ha verificado.
    """
    r = resolver_conflictos_de_rol("rol:x", [decl("a"), decl("b", a=1.0)], catalogo=cat)
    assert r.comparabilidad is Comparabilidad.COMPARABLE
    assert r.escala_comprobada is False

    con_uno = resolver_conflictos_de_rol(
        "rol:x", [decl("a", rango=(0.0, 1000.0)), decl("b")], catalogo=cat
    )
    assert con_uno.escala_comprobada is False


# --------------------------------------------------------------------------- #
# 5. La clase de magnitud: la trampa del delta, aquí
# --------------------------------------------------------------------------- #
def test_la_amplitud_declarada_se_convierte_como_intervalo() -> None:
    """§6.5 sobre el rango declarado: los extremos son puntos, la amplitud no.

    Con `Clase.PUNTO`, la amplitud de este canal —declarado en °C, `b = 273,15`—
    saldría 283,15 en lugar de 10. Es la trampa del delta de F1-20 en un sitio
    nuevo, y con una consecuencia nueva: no un número raro en pantalla, sino un
    canal sano acusado de tener la escala incoherente.
    """
    rango = RangoDeclarado(20.0, 30.0)
    escala = Afin(1.0, 273.15)
    assert rango.amplitud_canonica(escala) == pytest.approx(10.0)
    assert rango.en_canonica(escala) == pytest.approx((293.15, 303.15))
    # Lo que NO se hace, escrito para que se vea la diferencia.
    assert escala.desde_canonica(30.0 - 20.0, Clase.PUNTO) == pytest.approx(283.15)


def test_la_trampa_del_delta_no_acusa_a_un_canal_sano(cat: Catalogo) -> None:
    """El mismo error, visto desde el resultado del módulo.

    Dos logs con 10 K de amplitud, uno declarado en °C. Con la amplitud convertida
    como punto, la razón sería 28,3 y el módulo declararía incoherente la escala
    de un canal correcto: un falso positivo que impide comparar.
    """
    r = resolver_conflictos_de_rol(
        "rol:x",
        [
            decl("a", a=1.0, b=273.15, rango=(20.0, 30.0)),
            decl("b", a=1.0, b=0.0, rango=(293.15, 303.15)),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.COMPARABLE
    assert r.escala_comprobada


def test_una_escala_negativa_no_invierte_el_rango() -> None:
    """Un sensor invertido intercambia mínimo y máximo al convertir.

    Si el rango canónico saliera al revés, la comprobación de solapamiento
    compararía intervalos vacíos y denunciaría cualquier pareja.
    """
    rango = RangoDeclarado(0.0, 100.0)
    lo, hi = rango.en_canonica(Afin(-1.0, 500.0))
    assert (lo, hi) == pytest.approx((400.0, 500.0))
    assert rango.amplitud_canonica(Afin(-1.0, 500.0)) == pytest.approx(100.0)


def test_un_rango_al_reves_es_un_error_de_quien_llama() -> None:
    """`DisplayMaxMin` viene como «max,min» (docs/01 §1.3) y hay que repartirlo.

    Aceptarlo al revés en silencio daría amplitudes negativas y un criterio de
    coherencia que no significa nada.
    """
    with pytest.raises(ErrorDeConflicto, match="al revés"):
        RangoDeclarado(100.0, 0.0)


# --------------------------------------------------------------------------- #
# 6. Sin valor canónico no se compara: `unknown` y presión relativa
# --------------------------------------------------------------------------- #
def test_la_escala_sin_confirmar_queda_fuera_y_los_demas_siguen(cat: Catalogo) -> None:
    """§6.8, R1: con `confianza = "unknown"` el canal se muestra en crudo.

    En crudo no hay valor canónico, así que no hay nada que superponer con él. Se
    excluye ese log —no se le supone una escala plausible, que es lo que prohíbe
    `CLAUDE.md`— y los otros dos siguen comparándose: es lo útil, y el aviso dice
    quién se ha quedado fuera.
    """
    r = resolver_conflictos_de_rol(
        "rol:x",
        [decl("a"), decl("b"), decl("c", confianza="unknown")],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.CON_RESERVA
    assert r.comparables == ("a", "b")
    assert r.excluidos == {"c": Motivo.ESCALA_SIN_CONFIRMAR}
    assert codigos(r) == ["escala_sin_confirmar"]
    assert r.unidad_canonica == "K"


def test_dos_logs_y_uno_sin_confirmar_no_dejan_comparacion(cat: Catalogo) -> None:
    """Excluido el dudoso queda uno solo: no hay comparación, y se dice por qué."""
    r = resolver_conflictos_de_rol(
        "rol:x", [decl("a"), decl("b", confianza="unknown")], catalogo=cat
    )
    assert r.comparabilidad is Comparabilidad.NO_COMPARABLE
    assert r.comparables == ()
    assert r.excluidos == {"b": Motivo.ESCALA_SIN_CONFIRMAR}
    assert r.avisos


def test_inferred_no_es_unknown(cat: Catalogo) -> None:
    """11 de los 34 tipos del AutoLog tienen la escala deducida (`inferred`).

    `formatos/haltech.py` ya las trata como usables; tratarlas aquí como
    sospechosas llenaría de avisos la comparación normal.
    """
    r = resolver_conflictos_de_rol(
        "rol:x", [decl("a", confianza="inferred"), decl("b", confianza="confirmed")], catalogo=cat
    )
    assert r.comparabilidad is Comparabilidad.COMPARABLE
    assert r.avisos == ()


def test_un_canal_sin_dimension_queda_fuera(cat: Catalogo) -> None:
    r = resolver_conflictos_de_rol(
        "rol:x", [decl("a"), decl("b"), decl("c", dimension=None)], catalogo=cat
    )
    assert r.comparabilidad is Comparabilidad.CON_RESERVA
    assert r.excluidos == {"c": Motivo.SIN_DIMENSION}
    assert r.comparables == ("a", "b")


def test_una_unidad_de_origen_ajena_a_la_dimension_queda_fuera(cat: Catalogo) -> None:
    """`dimension = temperature` con `unidad_origen = psi`: las dos declaraciones
    no pueden ser ciertas y no se puede saber cuál corregir."""
    r = resolver_conflictos_de_rol(
        "rol:x", [decl("a"), decl("b"), decl("c", unidad_origen="psi")], catalogo=cat
    )
    assert r.excluidos == {"c": Motivo.UNIDAD_DE_ORIGEN_AJENA}
    assert r.comparabilidad is Comparabilidad.CON_RESERVA


# --------------------------------------------------------------------------- #
# 7. Presión absoluta contra relativa: cambio de ORIGEN (§6.6)
# --------------------------------------------------------------------------- #
def test_absoluta_contra_relativa_sin_referencia_no_se_mezcla(cat: Catalogo) -> None:
    """§6.6: no es un cambio de unidad, es un cambio de origen.

    Sin referencia resuelta el canal relativo no está en canónica —la canónica es
    kPa ABSOLUTOS— y no se le inventa una: el aviso remite al perfil del vehículo
    y a `presion_referencia.resolver_referencia`.
    """
    r = resolver_conflictos_de_rol(
        "rol:map",
        [
            decl("a", dimension="pressure", origen=OrigenDePresion.ABSOLUTA),
            decl("b", dimension="pressure", origen=OrigenDePresion.RELATIVA),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.NO_COMPARABLE
    assert r.excluidos == {"b": Motivo.PRESION_RELATIVA_SIN_REFERENCIA}
    (aviso,) = r.avisos
    assert "presion_referencia" in aviso.mensaje
    assert r.referencias_kpa == {}


def test_con_referencia_resuelta_se_comparan_con_reserva(cat: Catalogo) -> None:
    """Resuelta la referencia sí hay canónica común, y se dice de dónde sale.

    El módulo no la aplica: devuelve el número que hay que SUMAR, porque sumarlo
    es una operación sobre muestras y solo sobre las de `Clase.PUNTO` (§6.6).
    """
    r = resolver_conflictos_de_rol(
        "rol:map",
        [
            decl("a", dimension="pressure", origen=OrigenDePresion.ABSOLUTA),
            decl(
                "b",
                dimension="pressure",
                origen=OrigenDePresion.RELATIVA,
                referencia_kpa=101.325,
            ),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.CON_RESERVA
    assert r.comparables == ("a", "b")
    assert r.referencias_kpa == {"b": 101.325}
    assert Motivo.REFERENCIA_DE_PRESION_APLICADA in r.motivos
    assert "101,325".replace(",", ".") in r.avisos[0].mensaje


def test_la_referencia_se_aplica_al_rango_antes_de_juzgar_la_escala(cat: Catalogo) -> None:
    """Un log de boost (0–200 kPa relativos) contra uno absoluto (101–301 kPa).

    Sin sumar la referencia antes de comparar, los rangos canónicos saldrían
    desplazados 101 kPa por un motivo ya resuelto y el criterio de solapamiento
    los denunciaría por un motivo falso.
    """
    r = resolver_conflictos_de_rol(
        "rol:map",
        [
            decl(
                "a",
                dimension="pressure",
                a=0.1,
                rango=(1013.0, 3013.0),
                origen=OrigenDePresion.ABSOLUTA,
            ),
            decl(
                "b",
                dimension="pressure",
                a=0.1,
                rango=(0.0, 2000.0),
                origen=OrigenDePresion.RELATIVA,
                referencia_kpa=101.3,
            ),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.CON_RESERVA
    assert r.motivos == (Motivo.REFERENCIA_DE_PRESION_APLICADA,)
    assert r.escala_comprobada


def test_un_origen_sin_declarar_frente_a_uno_declarado_lleva_reserva(cat: Catalogo) -> None:
    """«2 bar» sin más es la fuente de error más común entre herramientas (§6.6).

    Se compara —bloquear cada CSV genérico que no declare el origen sería un falso
    positivo constante— pero el aviso dice que la diferencia podría ser de 101 kPa,
    que es un bar de boost.
    """
    r = resolver_conflictos_de_rol(
        "rol:map",
        [
            decl("a", dimension="pressure", origen=OrigenDePresion.ABSOLUTA),
            decl("b", dimension="pressure"),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.CON_RESERVA
    assert r.comparables == ("a", "b")
    assert Motivo.ORIGEN_DE_PRESION_SIN_DECLARAR in r.motivos
    assert "101" in r.avisos[0].mensaje


def test_si_nadie_declara_el_origen_tambien_se_avisa(cat: Catalogo) -> None:
    """No hay contradicción, pero la etiqueta del eje no puede afirmar abs ni rel."""
    r = resolver_conflictos_de_rol(
        "rol:map",
        [decl("a", dimension="pressure"), decl("b", dimension="pressure")],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.CON_RESERVA
    assert r.motivos == (Motivo.ORIGEN_DE_PRESION_SIN_DECLARAR,)


def test_dos_presiones_absolutas_se_comparan_sin_aviso(cat: Catalogo) -> None:
    r = resolver_conflictos_de_rol(
        "rol:map",
        [
            decl("a", dimension="pressure", origen=OrigenDePresion.ABSOLUTA),
            decl("b", dimension="pressure", origen=OrigenDePresion.ABSOLUTA),
        ],
        catalogo=cat,
    )
    assert r.comparabilidad is Comparabilidad.COMPARABLE
    assert r.avisos == ()


def test_declarar_origen_en_una_dimension_sin_referencia_es_error_de_uso(cat: Catalogo) -> None:
    """Solo la presión admite referencia de origen: el mismo error que rechaza
    `unidades.desde_canonica`, rechazado aquí igual."""
    with pytest.raises(ErrorDeConflicto, match="no admite referencia"):
        resolver_conflictos_de_rol(
            "rol:x",
            [decl("a"), decl("b", dimension="temperature", origen=OrigenDePresion.RELATIVA)],
            catalogo=cat,
        )


# --------------------------------------------------------------------------- #
# 8. Un rol en un solo log es un hueco, no un conflicto
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cuantos", [0, 1])
def test_menos_de_dos_logs_no_es_un_conflicto(cat: Catalogo, cuantos: int) -> None:
    """§3.6: un log de 25 canales y otro de 475 no traen lo mismo.

    Eso es un hueco y lo resuelve `identidad.GrupoDeCanales.ausentes`. Avisar aquí
    de cada canal que no está en todos los logs enterraría los avisos de verdad.
    """
    r = resolver_conflictos_de_rol("rol:x", [decl("a")][:cuantos], catalogo=cat)
    assert r.comparabilidad is Comparabilidad.NADA_QUE_COMPARAR
    assert r.avisos == ()
    assert r.comparables == ()
    assert r.hay_conflicto is False


def test_dos_canales_del_mismo_log_son_error_de_quien_llama(cat: Catalogo) -> None:
    """`identidad.emparejar` garantiza un canal por segmento y por grupo."""
    with pytest.raises(ErrorDeConflicto, match="dos canales"):
        resolver_conflictos_de_rol(
            "rol:x", [decl("a", id_canal="1"), decl("a", id_canal="2")], catalogo=cat
        )


# --------------------------------------------------------------------------- #
# 9. El informe completo
# --------------------------------------------------------------------------- #
def test_el_informe_recorre_los_roles_en_orden_y_junta_los_avisos(cat: Catalogo) -> None:
    """El informe de importación tiene que ser reproducible entre ejecuciones."""
    informe = resolver_conflictos(
        {
            "rol:map": [
                decl("a", dimension="pressure", origen=OrigenDePresion.ABSOLUTA),
                decl("b", dimension="temperature"),
            ],
            "rol:coolant_temp": [decl("a"), decl("b", a=1.0)],
            "rol:solo_en_uno": [decl("a")],
        },
        catalogo=cat,
    )
    assert [r.id_rol for r in informe.resoluciones] == [
        "rol:coolant_temp",
        "rol:map",
        "rol:solo_en_uno",
    ]
    assert [r.id_rol for r in informe.en_conflicto] == ["rol:map"]
    assert [r.id_rol for r in informe.comparables] == ["rol:coolant_temp"]
    assert [a.codigo for a in informe.avisos] == ["rol_con_dimensiones_distintas"]
    assert informe.por_rol("rol:map").comparabilidad is Comparabilidad.NO_COMPARABLE
    with pytest.raises(ErrorDeConflicto, match="rol:no_existe"):
        informe.por_rol("rol:no_existe")


def test_el_codigo_del_aviso_es_el_valor_del_motivo() -> None:
    """Un motivo nuevo no puede llegar al informe con un código inventado a mano.

    Es lo que permite que la interfaz y el informe HTML reaccionen a un `Motivo` y
    no a una cadena copiada.
    """
    assert len({m.value for m in Motivo}) == len(list(Motivo))
    assert Motivo.DIMENSIONES_DISTINTAS.value == "rol_con_dimensiones_distintas"
