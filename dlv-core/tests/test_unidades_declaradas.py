"""Pruebas de la resolución de unidades declaradas en el propio CSV (FG-06).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.6.

QUÉ PROTEGE ESTA SUITE
======================
Un importador genérico que acierta el nombre de una columna y falla la unidad
produce un número plausible pero falso — es el riesgo R1 descrito en §7.15, con
otra puerta de entrada. Cuatro reglas, por consecuencia:

1. **Las dos sintaxis del nombre** (`[...]` y `(...)`) se reconocen y el nombre
   limpio no incluye la unidad.
2. **La fila de unidades de FG-03** se resuelve columna a columna contra el
   catálogo y el diccionario de alias.
3. **Una unidad que no resuelve se queda sin resolver.** Nunca se elige "la que
   más se parece": eso es exactamente lo que R1 prohíbe.
4. **Todo alias de `data/alias_unidades.toml` apunta a una unidad real** de
   `data/units.toml`. Si alguien borra una unidad del catálogo y se olvida de
   este fichero, esta suite lo revienta con un mensaje que dice cuál.

Para leer los ficheros de muestra se usa la misma cadena FG-01 → FG-02 → FG-03
que `test_estructura.py`, porque `unidades_declaradas` consume exactamente lo
que esa cadena produce y no tiene sentido probarlo contra datos sintéticos que
ya no representan lo que de verdad le llega.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlv_core.formatos.decimal_csv import detectar_separador_decimal
from dlv_core.formatos.estructura import Estructura, analizar_estructura
from dlv_core.formatos.sondeo import sondear_csv
from dlv_core.formatos.unidades_declaradas import (
    ErrorDeAliasDeUnidad,
    OrigenUnidad,
    ResultadoUnidadesDeclaradas,
    UnidadDeColumna,
    cargar_alias,
    extraer_unidad_de_nombre,
    resolver_unidades_declaradas,
)
from dlv_core.unidades import Catalogo, cargar_catalogo

RAIZ = Path(__file__).resolve().parents[2]
GENERICOS = RAIZ / "samples" / "generico"
DOS_FORMATOS = RAIZ / "samples" / "dos-formatos"
DATA = RAIZ / "data"


def analizar(datos: bytes) -> Estructura:
    """La cadena FG-01 → FG-02 → FG-03, igual que en `test_estructura.py`."""
    s = sondear_csv(datos)
    texto = datos.decode(s.codificacion)
    d = detectar_separador_decimal(s, texto)
    return analizar_estructura(s, d, texto)


def de(ruta: Path) -> Estructura:
    return analizar(ruta.read_bytes())


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with (DATA / "units.toml").open("rb") as fh:
        return cargar_catalogo(fh)


@pytest.fixture(scope="module")
def alias() -> dict[str, tuple[str, str]]:
    with (DATA / "alias_unidades.toml").open("rb") as fh:
        return dict(cargar_alias(fh))


def resolver(
    e: Estructura, catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> ResultadoUnidadesDeclaradas:
    return resolver_unidades_declaradas(e.nombres, e.unidades_declaradas, catalogo, alias)


def por_nombre(resultado: ResultadoUnidadesDeclaradas, nombre_limpio: str) -> UnidadDeColumna:
    return next(c for c in resultado.columnas if c.nombre_limpio == nombre_limpio)


def codigos(resultado: ResultadoUnidadesDeclaradas) -> set[str]:
    return {a.codigo for a in resultado.avisos}


# --------------------------------------------------------------------------- #
# `data/alias_unidades.toml` apunta siempre a una unidad real
# --------------------------------------------------------------------------- #
def test_todos_los_alias_apuntan_a_una_unidad_que_existe(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """La prueba que exige la tarea: cada `(dimension, unidad)` del fichero de
    alias tiene que resolver contra `data/units.toml` sin lanzar."""
    assert alias, "el fichero de alias no puede estar vacío"
    for forma, (dim_id, uni_id) in alias.items():
        dimension = catalogo.dimension(dim_id)  # lanza ErrorDeUnidad si no existe
        unidad = dimension.unidad(uni_id)  # lanza ErrorDeUnidad si no existe
        assert unidad.id == uni_id, f"alias {forma!r}"


def test_el_resumen_del_fichero_de_alias_cuenta_bien_sus_grupos() -> None:
    """`[resumen] grupos` es lo que lee una persona en la puerta G1 para saber si
    el diff que tiene delante añade o quita algo. Un número que no cuadra con el
    contenido es peor que no tenerlo: decía 21 con 23 grupos escritos."""
    import tomllib

    with (DATA / "alias_unidades.toml").open("rb") as fh:
        bruto = tomllib.load(fh)
    grupos_reales = sum(len(unidades) for unidades in bruto["alias"].values())
    assert bruto["resumen"]["grupos"] == grupos_reales


def test_ningun_alias_pisa_un_id_ni_un_alias_de_units_toml(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """El fichero declara que NO repite lo que `units.toml` ya cubre. Si un día
    repitiera una forma, habría dos sitios que decidiendo lo mismo y solo uno se
    revisaría."""
    for dim_id, dim in catalogo.dimensiones.items():
        for uni_id in dim.unidades:
            assert uni_id not in alias, f"{uni_id!r} ya es un id de {dim_id} en units.toml"
        for forma in dim.alias:
            assert forma not in alias, f"{forma!r} ya es alias de {dim_id} en units.toml"


def test_las_unidades_con_barra_resuelven_escritas_con_barra(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """`acceleration` y `density` tienen la clave con `_` y la unidad real con
    `/`. Nadie exporta "m_s2": si la forma con barra no resolviera, esas dos
    dimensiones serían inalcanzables desde un CSV genérico."""
    for forma, esperado in [
        ("m/s2", ("acceleration", "m_s2")),
        ("m/s²", ("acceleration", "m_s2")),
        ("kg/m3", ("density", "kg_m3")),
        ("kg/m³", ("density", "kg_m3")),
    ]:
        r = resolver_unidades_declaradas(("Canal",), (forma,), catalogo, alias)
        col = r.columnas[0]
        assert (col.dimension_id, col.unidad_id) == esperado, forma
        assert r.avisos == (), forma


def test_cargar_alias_detecta_una_forma_contradictoria() -> None:
    """Si la misma forma cruda apuntara a dos destinos distintos, la resolución
    sería ambigua por construcción y hay que decirlo al cargar, no al usarlo."""
    import io

    toml_malo = b"""
    [alias.temperature.degC]
    formas = ["C"]

    [alias.temperature.degF]
    formas = ["C"]
    """
    with pytest.raises(ErrorDeAliasDeUnidad, match="'C'"):
        cargar_alias(io.BytesIO(toml_malo))


def test_construir_indice_rechaza_un_alias_a_una_unidad_inexistente(catalogo: Catalogo) -> None:
    """Si `alias_unidades.toml` apuntara a una unidad borrada de `units.toml`,
    la resolución tiene que fallar con un error con nombre, no con un `KeyError`
    en mitad de la importación de un fichero cualquiera."""
    alias_roto = {"birloque": ("temperature", "no_existe")}
    with pytest.raises(ErrorDeAliasDeUnidad, match="no existe"):
        resolver_unidades_declaradas(("X",), (), catalogo, alias_roto)


# --------------------------------------------------------------------------- #
# Extracción sintáctica de `[...]` y `(...)`
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("nombre", "limpio", "cruda", "origen"),
    [
        ("RPM [rpm]", "RPM", "rpm", OrigenUnidad.CORCHETE),
        ("CLT (°C)", "CLT", "°C", OrigenUnidad.PARENTESIS),
        ("MAP [kPa]", "MAP", "kPa", OrigenUnidad.CORCHETE),
        ("TPS (%)", "TPS", "%", OrigenUnidad.PARENTESIS),
        ("Time [s]", "Time", "s", OrigenUnidad.CORCHETE),
        ("Lambda [ratio]", "Lambda", "ratio", OrigenUnidad.CORCHETE),
        ("Sin unidad", "Sin unidad", None, OrigenUnidad.NINGUNA),
        ("Notas del piloto", "Notas del piloto", None, OrigenUnidad.NINGUNA),
    ],
)
def test_extraccion_sintactica(
    nombre: str, limpio: str, cruda: str | None, origen: OrigenUnidad
) -> None:
    nombre_limpio, unidad_cruda, origen_real = extraer_unidad_de_nombre(nombre)
    assert nombre_limpio == limpio
    assert unidad_cruda == cruda
    assert origen_real is origen


def test_un_corchete_vacio_no_declara_unidad() -> None:
    """`Nombre []` no es una unidad de longitud cero: es un corchete vacío, y
    tratarlo como unidad inventaría una cadena que el fichero no escribió."""
    _nombre_limpio, cruda, origen = extraer_unidad_de_nombre("Canal []")
    assert cruda is None
    assert origen is OrigenUnidad.NINGUNA


# --------------------------------------------------------------------------- #
# `05-unidad-en-el-nombre.csv`: RPM [rpm], CLT (°C), TPS (%), Lambda [ratio]
# --------------------------------------------------------------------------- #
def test_unidad_en_el_nombre_del_fichero_de_muestra(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    e = de(GENERICOS / "05-unidad-en-el-nombre.csv")
    r = resolver(e, catalogo, alias)
    assert len(r.columnas) == 6

    tiempo = por_nombre(r, "Time")
    assert tiempo.unidad_cruda == "s"
    assert tiempo.dimension_id == "time"
    assert tiempo.unidad_id == "s"
    assert tiempo.origen is OrigenUnidad.CORCHETE
    assert tiempo.nombre_original == "Time [s]"

    rpm = por_nombre(r, "RPM")
    assert (rpm.dimension_id, rpm.unidad_id) == ("angular_speed", "rpm")

    mapa = por_nombre(r, "MAP")
    assert (mapa.dimension_id, mapa.unidad_id) == ("pressure", "kPa")

    tps = por_nombre(r, "TPS")
    assert tps.unidad_cruda == "%"
    assert (tps.dimension_id, tps.unidad_id) == ("ratio", "pct")

    clt = por_nombre(r, "CLT")
    assert clt.unidad_cruda == "°C"
    assert (clt.dimension_id, clt.unidad_id) == ("temperature", "degC")

    lam = por_nombre(r, "Lambda")
    assert lam.unidad_cruda == "ratio"
    assert (lam.dimension_id, lam.unidad_id) == ("mixture_ratio", "lambda")

    assert all(c.resuelta for c in r.columnas)
    assert r.avisos == ()


# --------------------------------------------------------------------------- #
# `04-fila-de-unidades.csv`: s,rpm,kPa,%,C,ratio en la fila de unidades
# --------------------------------------------------------------------------- #
def test_fila_de_unidades_del_fichero_de_muestra(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    e = de(GENERICOS / "04-fila-de-unidades.csv")
    assert e.tiene_fila_de_unidades
    r = resolver(e, catalogo, alias)

    esperado = {
        "Time": ("time", "s"),
        "RPM": ("angular_speed", "rpm"),
        "MAP": ("pressure", "kPa"),
        "TPS": ("ratio", "pct"),
        "CLT": ("temperature", "degC"),
        "Lambda": ("mixture_ratio", "lambda"),
    }
    for nombre, (dim_id, uni_id) in esperado.items():
        col = por_nombre(r, nombre)
        assert (col.dimension_id, col.unidad_id) == (dim_id, uni_id), nombre
        assert col.origen is OrigenUnidad.FILA_DE_UNIDADES
        assert col.resuelta

    assert r.avisos == ()


# --------------------------------------------------------------------------- #
# `dos-formatos/generico.csv`: s;rpm;kPa;%;°C;°C;λ;λ;°;kPa;V
# --------------------------------------------------------------------------- #
def test_generico_con_grados_y_lambda_griega(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """El caso explícito de la tarea: ojo con `λ` y `°`."""
    e = de(DOS_FORMATOS / "generico.csv")
    assert e.tiene_fila_de_unidades
    assert e.unidades_declaradas == ("s", "rpm", "kPa", "%", "°C", "°C", "λ", "λ", "°", "kPa", "V")
    r = resolver(e, catalogo, alias)
    assert len(r.columnas) == 11

    tiempo = por_nombre(r, "Tiempo")
    assert (tiempo.dimension_id, tiempo.unidad_id) == ("time", "s")

    regimen = por_nombre(r, "Régimen")
    assert (regimen.dimension_id, regimen.unidad_id) == ("angular_speed", "rpm")

    presion = por_nombre(r, "Presión colector")
    assert (presion.dimension_id, presion.unidad_id) == ("pressure", "kPa")

    mariposa = por_nombre(r, "Mariposa")
    assert (mariposa.dimension_id, mariposa.unidad_id) == ("ratio", "pct")

    for nombre in ("Temp. refrigerante", "Temp. aire"):
        col = por_nombre(r, nombre)
        assert col.unidad_cruda == "°C"
        assert (col.dimension_id, col.unidad_id) == ("temperature", "degC"), nombre

    for nombre in ("Lambda", "Lambda objetivo"):
        col = por_nombre(r, nombre)
        assert col.unidad_cruda == "λ"
        assert (col.dimension_id, col.unidad_id) == ("mixture_ratio", "lambda"), nombre

    avance = por_nombre(r, "Avance")
    assert avance.unidad_cruda == "°"
    assert (avance.dimension_id, avance.unidad_id) == ("angle", "deg")

    presion_aceite = por_nombre(r, "Presión aceite")
    assert (presion_aceite.dimension_id, presion_aceite.unidad_id) == ("pressure", "kPa")

    tension = por_nombre(r, "Tensión batería")
    assert (tension.dimension_id, tension.unidad_id) == ("voltage", "V")

    assert all(c.resuelta for c in r.columnas)
    assert r.avisos == ()


# --------------------------------------------------------------------------- #
# La regla de R1: una unidad inventada no se resuelve nunca
# --------------------------------------------------------------------------- #
def test_una_unidad_inventada_no_se_resuelve(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """`furlong_por_quincena` no está ni en `units.toml` ni en el diccionario de
    alias: tiene que quedarse sin resolver, con aviso, nunca con una dimensión
    adivinada 'porque se parece'."""
    r = resolver_unidades_declaradas(("Canal Raro",), ("furlong_por_quincena",), catalogo, alias)
    assert len(r.columnas) == 1
    col = r.columnas[0]
    assert not col.resuelta
    assert col.dimension_id is None
    assert col.unidad_id is None
    assert col.unidad_cruda == "furlong_por_quincena"
    assert "unidad_no_resuelta" in codigos(r)


def test_una_unidad_ambigua_entre_dimensiones_no_se_resuelve(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """`g` es una unidad válida de masa, de masa por cilindro Y de aceleración,
    sin que ninguna sea SU canónica: exactamente el empate que R1 prohíbe
    desambiguar por su cuenta."""
    r = resolver_unidades_declaradas(("Peso",), ("g",), catalogo, alias)
    col = r.columnas[0]
    assert not col.resuelta
    assert "unidad_ambigua" in codigos(r)


def test_rpm_desambigua_a_angular_speed_no_a_frecuencia(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """`rpm` es unidad válida de `angular_speed` (donde es la canónica) y de
    `frequency` (donde no lo es). Gana `angular_speed`, y no por casualidad."""
    r = resolver_unidades_declaradas(("Motor",), ("rpm",), catalogo, alias)
    col = r.columnas[0]
    assert (col.dimension_id, col.unidad_id) == ("angular_speed", "rpm")


def test_hz_desambigua_a_frecuencia_no_a_angular_speed(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    r = resolver_unidades_declaradas(("Señal",), ("Hz",), catalogo, alias)
    col = r.columnas[0]
    assert (col.dimension_id, col.unidad_id) == ("frequency", "Hz")


# --------------------------------------------------------------------------- #
# El `_` es más débil que `[...]`/`(...)`: solo se acepta si resuelve
# --------------------------------------------------------------------------- #
def test_guion_bajo_se_acepta_cuando_el_sufijo_resuelve(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    r = resolver_unidades_declaradas(("Boost_bar",), (), catalogo, alias)
    col = r.columnas[0]
    assert col.nombre_limpio == "Boost"
    assert col.unidad_cruda == "bar"
    assert col.origen is OrigenUnidad.GUION_BAJO
    assert (col.dimension_id, col.unidad_id) == ("pressure", "bar")


def test_guion_bajo_no_se_acepta_cuando_el_sufijo_no_resuelve(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """`Fuel_Trim` no declara una unidad "Trim": el nombre no se toca, y la
    columna se queda simplemente sin unidad declarada (no es un error)."""
    r = resolver_unidades_declaradas(("Fuel_Trim",), (), catalogo, alias)
    col = r.columnas[0]
    assert col.nombre_limpio == "Fuel_Trim"
    assert col.unidad_cruda is None
    assert col.origen is OrigenUnidad.NINGUNA
    assert not col.resuelta
    assert r.avisos == (), "no declarar unidad no es una anomalía, no hay que avisar"


def test_guion_bajo_con_sufijo_numerico_no_se_toma_por_unidad(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """`Sensor_1`: el `1` es un índice, no una unidad."""
    r = resolver_unidades_declaradas(("Sensor_1",), (), catalogo, alias)
    col = r.columnas[0]
    assert col.nombre_limpio == "Sensor_1"
    assert col.unidad_cruda is None


# --------------------------------------------------------------------------- #
# Precedencia: nombre gana a fila de unidades cuando discrepan
# --------------------------------------------------------------------------- #
def test_el_nombre_gana_a_la_fila_de_unidades_si_discrepan(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    r = resolver_unidades_declaradas(("MAP [kPa]",), ("bar",), catalogo, alias)
    col = r.columnas[0]
    assert col.unidad_cruda == "kPa"
    assert (col.dimension_id, col.unidad_id) == ("pressure", "kPa")
    assert "unidad_declarada_dos_veces" in codigos(r)


def test_la_fila_de_unidades_se_usa_solo_si_el_nombre_no_declara_nada(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    r = resolver_unidades_declaradas(("MAP",), ("bar",), catalogo, alias)
    col = r.columnas[0]
    assert col.origen is OrigenUnidad.FILA_DE_UNIDADES
    assert (col.dimension_id, col.unidad_id) == ("pressure", "bar")
    assert r.avisos == ()


# --------------------------------------------------------------------------- #
# Un paréntesis puede ser un calificador, no una unidad
# --------------------------------------------------------------------------- #
def test_un_calificador_entre_parentesis_no_tira_la_fila_de_unidades(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """`Lambda (Sensor 1)` con `λ` en la fila de unidades. "Sensor 1" no es una
    unidad; la fila sí lo es. Quedarse en crudo aquí sería tirar una declaración
    que el fichero escribió explícitamente, y no por ambigüedad: no hay más que
    una lectura posible una vez que "Sensor 1" no resuelve."""
    r = resolver_unidades_declaradas(("Lambda (Sensor 1)",), ("λ",), catalogo, alias)
    col = r.columnas[0]
    assert (col.dimension_id, col.unidad_id) == ("mixture_ratio", "lambda")
    assert col.unidad_cruda == "λ"
    assert col.origen is OrigenUnidad.FILA_DE_UNIDADES
    assert "unidad_del_nombre_no_resuelta" in codigos(r)


def test_un_calificador_entre_parentesis_no_recorta_el_nombre(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """Dos sensores de lambda no pueden acabar rotulados los dos «Lambda»: el
    nombre solo pierde el paréntesis cuando lo de dentro era de verdad una
    unidad. Es el mismo argumento que ya justifica la regla del `_`."""
    r = resolver_unidades_declaradas(
        ("Lambda (Sensor 1)", "Lambda (Sensor 2)"), ("λ", "λ"), catalogo, alias
    )
    assert [c.nombre_limpio for c in r.columnas] == ["Lambda (Sensor 1)", "Lambda (Sensor 2)"]


def test_un_calificador_sin_fila_de_unidades_deja_la_columna_sin_resolver(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """Sin fila de unidades no hay nada que rescatar: `Boost (gauge)` se queda sin
    resolver —crudo, sin selector— y el nombre entero, porque "gauge" podría ser
    tanto una unidad que el catálogo no conoce como un calificador, y elegir una
    de las dos lecturas sería adivinar."""
    r = resolver_unidades_declaradas(("Boost (gauge)",), (), catalogo, alias)
    col = r.columnas[0]
    assert not col.resuelta
    assert col.nombre_limpio == "Boost (gauge)"
    assert col.unidad_cruda == "gauge"
    assert "unidad_no_resuelta" in codigos(r)


def test_el_nombre_gana_solo_cuando_resuelve(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """La precedencia de §7.6 sigue intacta donde importa: si las dos vías
    resuelven, gana el nombre; la fila solo entra cuando el nombre no resuelve."""
    gana_nombre = resolver_unidades_declaradas(("MAP [bar]",), ("kPa",), catalogo, alias)
    assert gana_nombre.columnas[0].unidad_id == "bar"

    gana_fila = resolver_unidades_declaradas(("MAP [absoluta]",), ("kPa",), catalogo, alias)
    assert gana_fila.columnas[0].unidad_id == "kPa"


def test_una_unidad_del_nombre_ambigua_cede_ante_una_fila_que_resuelve(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """`(g)` empata entre masa y aceleración, así que no resuelve; si la fila
    dice `m/s2`, esa columna sí se puede resolver sin adivinar nada."""
    r = resolver_unidades_declaradas(("Aceleracion (g)",), ("m/s2",), catalogo, alias)
    col = r.columnas[0]
    assert col.resuelta
    assert col.dimension_id == "acceleration"
    assert "unidad_del_nombre_no_resuelta" in codigos(r)


# --------------------------------------------------------------------------- #
# Columnas sin ninguna unidad declarada
# --------------------------------------------------------------------------- #
def test_una_columna_sin_unidad_declarada_no_se_avisa(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """No declarar unidad es legítimo (§7.8: se puede importar sin rol ni
    unidad, sigue siendo graficable). No es una anomalía y no genera aviso."""
    r = resolver_unidades_declaradas(("Notas",), (), catalogo, alias)
    col = r.columnas[0]
    assert not col.resuelta
    assert col.unidad_cruda is None
    assert col.origen is OrigenUnidad.NINGUNA
    assert r.avisos == ()


def test_unidades_declaradas_mas_corta_que_nombres_no_revienta(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """Un fichero sin fila de unidades tiene `unidades_declaradas == ()`. No
    tiene que hacer falta rellenar nada para que esto no explote."""
    r = resolver_unidades_declaradas(("A", "B", "C"), (), catalogo, alias)
    assert len(r.columnas) == 3
    assert all(c.unidad_cruda is None for c in r.columnas)


# --------------------------------------------------------------------------- #
# Alias del propio `data/units.toml` (kph/KPH) siguen funcionando aquí
# --------------------------------------------------------------------------- #
def test_los_alias_de_units_toml_tambien_resuelven(
    catalogo: Catalogo, alias: dict[str, tuple[str, str]]
) -> None:
    """`kph` es alias de `km/h` DENTRO de `units.toml` (F0-08), no de
    `alias_unidades.toml`. La resolución de esta tarea tiene que respetarlo sin
    duplicar la entrada."""
    r = resolver_unidades_declaradas(("Velocidad",), ("kph",), catalogo, alias)
    col = r.columnas[0]
    assert (col.dimension_id, col.unidad_id) == ("speed", "km/h")
    assert "kph" not in dict(alias), "kph ya está en units.toml; no hay que duplicarlo aquí"
