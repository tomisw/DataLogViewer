"""Pruebas del perfil de importación `.dlvimport` (FG-12).

Especificación: `docs/07-formatos-y-csv-generico.md` §7.9. Lo que protege esta
suite, por orden de consecuencia (docs/09 §9.9: "ordénala por consecuencia si
el número está mal"):

1. **Un perfil no se reaplica a un fichero que no le corresponde.** Es el
   fallo que el encargo llama "peor que no tener perfiles": mete las unidades
   de otra ECU sin decir nada. `test_no_se_reaplica_a_otro_delimitador` y
   `test_no_se_reaplica_sin_ninguna_columna_coincidente` comprueban que en ese
   caso NO se toca ni un solo campo, y que `motivo` explica por qué.
2. **Lo confirmado sobrevive; lo deducido se vuelve a deducir.** Es la regla
   central del módulo (`_fusionar_campo`) y la prueba obligatoria más
   explícita del encargo: `test_confirmado_sobrevive_y_deducido_se_rededuce`.
   Sin esto, un perfil sería indistinguible de "recordar la primera propuesta
   para siempre", que arrastra un error de la primera importación a todas.
3. **Los canales nuevos quedan visiblemente sin decidir**, no se adivinan ni
   desaparecen: `test_reaplicacion_parcial_marca_canales_nuevos`.
4. **Un perfil corrupto se rechaza con un mensaje, nunca con un `KeyError`/
   `TypeError` desnudo** (regla 5 del encargo): la sección "perfil corrupto".
5. La huella en sí: qué cambia entre dos logs del mismo coche la semana
   siguiente (nada: mismas columnas, mismo orden, mismo delimitador) y qué NO
   forma parte de ella (nombre de fichero, fecha, tamaño): la sección
   "HuellaCabecera / construir_huella".
6. **La columna de tiempo se reaplica por nombre**, no por índice, porque
   `sondear_canales` la excluye de la lista de canales: la sección
   "columna de tiempo".
7. Ida y vuelta exacta por `dict` y por texto TOML, con la distinción
   `origen`/`confirmado` intacta tras el viaje.

Solo biblioteca estándar.
"""

from __future__ import annotations

import pytest

from dlv_core.perfil_importacion import (
    VERSION_ESQUEMA_PERFIL_IMPORTACION,
    Campo,
    CanalImportado,
    ErrorDePerfilImportacion,
    ErrorDeVersionDePerfilDesconocida,
    FormatoImportado,
    PerfilImportacion,
    ResumenHuella,
    RolDeCanal,
    TiempoImportado,
    construir_huella,
    crear_perfil,
    reaplicar_perfil,
)

# --------------------------------------------------------------------------- #
# Fábricas de prueba: un "log" con columna de tiempo "Time" y canales RPM y
# Coolant Temp, tal como saldría del asistente de FG-11 (§7.8) tras sondear un
# CSV con ";" y coma decimal.
# --------------------------------------------------------------------------- #


def _formato(*, delimitador: str = ";", codificacion: str = "utf-8") -> FormatoImportado:
    return FormatoImportado(
        codificacion=Campo(valor=codificacion, origen="confirmado"),
        delimitador=Campo(valor=delimitador, origen="confirmado"),
        comilla=Campo(valor=None, origen="deducido"),
        decimal=Campo(valor=",", origen="deducido"),
        fila_cabecera=Campo(valor=0, origen="deducido"),
        fila_unidades=Campo(valor=None, origen="deducido"),
        fila_datos=Campo(valor=1, origen="deducido"),
    )


def _tiempo(
    *, columna: int | None = 0, nombre_columna: str | None = "Time", confirmada: bool = True
) -> TiempoImportado:
    return TiempoImportado(
        clase=Campo(valor="relativo", origen="deducido"),
        columna=Campo(valor=columna, origen="confirmado" if confirmada else "deducido"),
        nombre_columna=nombre_columna,
        columna_fecha=Campo(valor=None, origen="deducido"),
        nombre_columna_fecha=None,
        frecuencia_hz=Campo(valor=None, origen="deducido"),
    )


def _canal_rpm(*, dimension_confirmada: bool = True, columna: int = 1) -> CanalImportado:
    return CanalImportado(
        nombre="RPM",
        columna=columna,
        dimension_id=Campo(
            valor="angular_speed", origen="confirmado" if dimension_confirmada else "deducido"
        ),
        unidad_origen=Campo(
            valor="rpm", origen="confirmado" if dimension_confirmada else "deducido"
        ),
        rol=RolDeCanal(
            rol="engine_speed",
            confianza="EXACTA",
            sinonimo="RPM",
            indice=None,
            parecido=1.0,
            confirmado=True,
        ),
    )


def _canal_temp(*, columna: int = 2, rol_confirmado: bool = True) -> CanalImportado:
    return CanalImportado(
        nombre="Coolant Temp",
        columna=columna,
        dimension_id=Campo(valor="temperature", origen="confirmado"),
        unidad_origen=Campo(valor="degC", origen="confirmado"),
        rol=RolDeCanal(
            rol="coolant_temp",
            confianza="DIFUSA",
            sinonimo="Coolant Temperature",
            indice=None,
            parecido=0.86,
            confirmado=rol_confirmado,
        ),
    )


def _canal_deducido(nombre: str, columna: int, *, dimension_id: str = "unknown") -> CanalImportado:
    """Un canal tal como sale de un sondeo SIN que nadie lo haya tocado: todo
    `origen == "deducido"`, sin rol confirmado."""
    return CanalImportado(
        nombre=nombre,
        columna=columna,
        dimension_id=Campo(valor=dimension_id, origen="deducido"),
        unidad_origen=Campo(valor=None, origen="deducido"),
        rol=None,
    )


def _perfil_de_ejemplo() -> PerfilImportacion:
    """Time, RPM, Coolant Temp, en ese orden: la cabecera completa que
    `crear_perfil` necesita para calcular la huella (ver su docstring: incluye
    la columna de tiempo, que NO aparece en `canales`)."""
    return crear_perfil(
        "Mi coche - MoTeC",
        nombres_columnas=["Time", "RPM", "Coolant Temp"],
        formato=_formato(),
        tiempo=_tiempo(),
        canales=[_canal_rpm(), _canal_temp()],
    )


# --------------------------------------------------------------------------- #
# HuellaCabecera / construir_huella: qué compone la huella y qué no
# --------------------------------------------------------------------------- #
def test_la_huella_normaliza_mayusculas_espacios_y_acentos() -> None:
    """`RPM` y ` rpm` (con espacio) son la misma columna a efectos de huella:
    la huella normaliza, no exige coincidencia byte a byte (§7.7)."""
    a = construir_huella(["RPM", "Coolant Temp"], delimitador=";", codificacion="utf-8")
    b = construir_huella(["  rpm", "coolanttemp"], delimitador=";", codificacion="utf-8")
    assert a.hash_columnas == b.hash_columnas


def test_la_huella_es_sensible_al_orden_de_columnas() -> None:
    """El caso que docs/07 §7.9 llama "reordenadas": mismas columnas, otro
    orden, hash DISTINTO — es justo lo que separa "total" de "parcial"."""
    a = construir_huella(["RPM", "Temp"], delimitador=";", codificacion="utf-8")
    b = construir_huella(["Temp", "RPM"], delimitador=";", codificacion="utf-8")
    assert a.hash_columnas != b.hash_columnas


def test_la_huella_no_incluye_nada_del_fichero_en_si() -> None:
    """Lo que cambia de un log al de la semana siguiente del MISMO coche —
    nombre de fichero, fecha, número de sesión, tamaño— no forma parte de
    `HuellaCabecera`: solo tiene tres campos, y ninguno es ese.
    `dlv_core.huella.ClaveInvalidacion` (la huella de caché, ADR-005) SÍ lleva
    ruta/tamaño/mtime porque resuelve el problema contrario (identificar UN
    fichero); esta huella resuelve identificar un FORMATO."""
    import dataclasses

    huella = construir_huella(["RPM", "Coolant Temp"], delimitador=";", codificacion="utf-8")
    campos = {f.name for f in dataclasses.fields(huella)}
    assert campos == {"nombres_normalizados", "delimitador", "codificacion"}


def test_mismo_coche_semana_siguiente_produce_la_misma_huella() -> None:
    """El caso concreto del informe: log de hoy y log de la semana que viene,
    mismo coche, mismas columnas exportadas por la misma configuración —
    aunque la fecha y el número de sesión en el nombre del fichero cambien,
    la huella (que ni los mira) es idéntica."""
    columnas = ["Time", "RPM", "Coolant Temp", "Oil Pressure"]
    huella_hoy = construir_huella(columnas, delimitador=";", codificacion="utf-8")
    huella_semana_que_viene = construir_huella(columnas, delimitador=";", codificacion="utf-8")
    assert huella_hoy.hash_columnas == huella_semana_que_viene.hash_columnas
    assert huella_hoy.n_columnas == 4


# --------------------------------------------------------------------------- #
# Reaplicación: coincidencia total
# --------------------------------------------------------------------------- #
def test_se_reaplica_a_un_log_del_mismo_formato() -> None:
    perfil = _perfil_de_ejemplo()  # su columna de tiempo confirmada es "Time"
    canales_nuevos = [
        _canal_deducido("RPM", 0, dimension_id="unknown"),  # llega sin confirmar de nuevo
        _canal_deducido("Coolant Temp", 1, dimension_id="unknown"),
    ]
    resultado = reaplicar_perfil(
        perfil,
        nombres_columnas=["Time", "RPM", "Coolant Temp"],
        formato_actual=_formato(),
        tiempo_actual=_tiempo(confirmada=False),
        canales_actuales=canales_nuevos,
    )
    assert resultado.tipo == "total"
    assert resultado.columnas_nuevas_sin_decidir == ()
    assert resultado.avisos == ()

    rpm = next(c for c in resultado.canales if c.nombre == "RPM")
    assert rpm.dimension_id.valor == "angular_speed"
    assert rpm.dimension_id.origen == "confirmado"
    assert rpm.rol is not None and rpm.rol.confirmado

    temp = next(c for c in resultado.canales if c.nombre == "Coolant Temp")
    assert temp.dimension_id.valor == "temperature"
    assert temp.unidad_origen.valor == "degC"

    # La columna de tiempo se reaplicó buscando "Time" en la cabecera completa.
    assert resultado.tiempo.columna.valor == 0
    assert resultado.tiempo.columna.origen == "confirmado"


# --------------------------------------------------------------------------- #
# Reaplicación: no corresponde a este fichero
# --------------------------------------------------------------------------- #
def test_no_se_reaplica_a_otro_delimitador() -> None:
    """Mismos nombres de columna, pero el fichero nuevo usa "," en vez de
    ";": es casi seguro OTRO exportador, no una reconfiguración del mismo, y
    nada se reaplica."""
    perfil = _perfil_de_ejemplo()
    canales_nuevos = [_canal_deducido("RPM", 0), _canal_deducido("Coolant Temp", 1)]
    resultado = reaplicar_perfil(
        perfil,
        nombres_columnas=["RPM", "Coolant Temp"],
        formato_actual=_formato(delimitador=","),
        tiempo_actual=_tiempo(confirmada=False),
        canales_actuales=canales_nuevos,
    )
    assert resultado.tipo == "ninguna"
    assert "delimitador" in resultado.motivo
    # Nada se toca: exactamente lo que entró, sin fusionar ni un campo.
    assert resultado.canales == tuple(canales_nuevos)
    assert resultado.formato == _formato(delimitador=",")


def test_no_se_reaplica_sin_ninguna_columna_coincidente() -> None:
    """Mismo delimitador y codificación (podría ser el mismo exportador),
    pero ninguna columna del fichero nuevo aparece en el perfil: no es el
    mismo origen de datos y no se reaplica nada, en vez de reaplicar por
    coincidencia de posición."""
    perfil = _perfil_de_ejemplo()
    canales_nuevos = [_canal_deducido("Boost Pressure", 0), _canal_deducido("Wastegate Duty", 1)]
    resultado = reaplicar_perfil(
        perfil,
        nombres_columnas=["Boost Pressure", "Wastegate Duty"],
        formato_actual=_formato(),
        tiempo_actual=_tiempo(confirmada=False),
        canales_actuales=canales_nuevos,
    )
    assert resultado.tipo == "ninguna"
    assert "ninguna columna" in resultado.motivo
    assert resultado.canales == tuple(canales_nuevos)


def test_no_se_reaplica_a_otra_codificacion() -> None:
    perfil = _perfil_de_ejemplo()
    canales_nuevos = [_canal_deducido("RPM", 0)]
    resultado = reaplicar_perfil(
        perfil,
        nombres_columnas=["RPM"],
        formato_actual=_formato(codificacion="latin-1"),
        tiempo_actual=_tiempo(confirmada=False),
        canales_actuales=canales_nuevos,
    )
    assert resultado.tipo == "ninguna"
    assert "codificaci" in resultado.motivo


# --------------------------------------------------------------------------- #
# Reaplicación parcial: canales nuevos y columnas reordenadas
# --------------------------------------------------------------------------- #
def test_reaplicacion_parcial_marca_canales_nuevos() -> None:
    """El log de la semana que viene trae los mismos canales MÁS tres nuevos
    (p. ej. el usuario añadió sensores). Los que coinciden se reaplican; los
    tres nuevos quedan en `columnas_nuevas_sin_decidir`, VISIBLES."""
    perfil = _perfil_de_ejemplo()
    canales_nuevos = [
        _canal_deducido("RPM", 0),
        _canal_deducido("Coolant Temp", 1),
        _canal_deducido("Boost Pressure", 2),
        _canal_deducido("Wastegate Duty", 3),
        _canal_deducido("Lambda", 4),
    ]
    resultado = reaplicar_perfil(
        perfil,
        nombres_columnas=[c.nombre for c in canales_nuevos],
        formato_actual=_formato(),
        tiempo_actual=_tiempo(confirmada=False),
        canales_actuales=canales_nuevos,
    )
    assert resultado.tipo == "parcial"
    assert set(resultado.columnas_nuevas_sin_decidir) == {
        "Boost Pressure",
        "Wastegate Duty",
        "Lambda",
    }
    assert any("3 columna(s) nueva" in a for a in resultado.avisos)

    # Los nuevos NO se tocan: exactamente lo que entró, sin ningún campo
    # "confirmado" inventado.
    boost = next(c for c in resultado.canales if c.nombre == "Boost Pressure")
    assert boost.dimension_id.origen == "deducido"
    assert boost.rol is None

    # Los que sí coincidían se reaplicaron con normalidad.
    rpm = next(c for c in resultado.canales if c.nombre == "RPM")
    assert rpm.dimension_id.valor == "angular_speed"
    assert rpm.dimension_id.origen == "confirmado"


def test_reaplicacion_parcial_por_columnas_reordenadas() -> None:
    """Mismas columnas del perfil, pero el exportador las escribió en otro
    orden: la huella completa (order-sensible) no coincide -> "parcial", pero
    cada canal se reaplica igual porque el emparejamiento es por NOMBRE."""
    perfil = _perfil_de_ejemplo()
    canales_nuevos = [
        _canal_deducido("Coolant Temp", 0),  # antes era la columna 2
        _canal_deducido("RPM", 1),  # antes era la columna 1
    ]
    resultado = reaplicar_perfil(
        perfil,
        nombres_columnas=["Coolant Temp", "RPM"],
        formato_actual=_formato(),
        tiempo_actual=_tiempo(confirmada=False),
        canales_actuales=canales_nuevos,
    )
    assert resultado.tipo == "parcial"
    assert resultado.columnas_nuevas_sin_decidir == ()
    rpm = next(c for c in resultado.canales if c.nombre == "RPM")
    assert rpm.dimension_id.origen == "confirmado"
    assert rpm.dimension_id.valor == "angular_speed"


def test_columnas_del_perfil_ausentes_del_fichero_nuevo_se_avisan() -> None:
    """El usuario quitó un sensor: la columna del perfil que ya no aparece se
    lista en `avisos`, no se inventa ni bloquea la reaplicación del resto."""
    perfil = _perfil_de_ejemplo()  # RPM + Coolant Temp
    canales_nuevos = [_canal_deducido("RPM", 0)]  # Coolant Temp ya no está
    resultado = reaplicar_perfil(
        perfil,
        nombres_columnas=["RPM"],
        formato_actual=_formato(),
        tiempo_actual=_tiempo(confirmada=False),
        canales_actuales=canales_nuevos,
    )
    assert resultado.tipo == "parcial"
    assert any("Coolant Temp" in a and "no están en este fichero" in a for a in resultado.avisos)


# --------------------------------------------------------------------------- #
# Columna de tiempo: por nombre, no por índice
# --------------------------------------------------------------------------- #
def test_la_columna_de_tiempo_se_reaplica_por_nombre_pese_a_reordenarse() -> None:
    """El caso que motiva NO guardar solo un índice para el tiempo: si la
    columna de tiempo se mueve de la 0 a la 2, reaplicar el índice guardado
    apuntaría a un canal distinto. Buscar por nombre lo evita. "Time" no
    aparece en `canales_actuales` (se excluye, igual que en `dlv_api.
    importacion.sondear_canales`): solo en `nombres_columnas`, la cabecera
    completa."""
    perfil = crear_perfil(
        "coche",
        nombres_columnas=["Time", "RPM"],
        formato=_formato(),
        tiempo=_tiempo(columna=0, nombre_columna="Time", confirmada=True),
        canales=[_canal_rpm(columna=1)],
    )
    canales_actuales = [
        _canal_deducido("RPM", 0),
        _canal_deducido("Extra", 1),
        # "Time" no está aquí: es la columna de tiempo, excluida de "canales".
    ]
    tiempo_actual = _tiempo(columna=None, nombre_columna=None, confirmada=False)
    resultado = reaplicar_perfil(
        perfil,
        # "Time" está en la posición 2 de la cabecera completa esta vez.
        nombres_columnas=["RPM", "Extra", "Time"],
        formato_actual=_formato(),
        tiempo_actual=tiempo_actual,
        canales_actuales=canales_actuales,
    )
    assert resultado.tiempo.columna.valor == 2
    assert resultado.tiempo.columna.origen == "confirmado"


def test_columna_de_tiempo_confirmada_pero_ausente_se_avisa_y_se_rededuce() -> None:
    perfil = crear_perfil(
        "coche",
        nombres_columnas=["Time", "RPM"],
        formato=_formato(),
        tiempo=_tiempo(columna=0, nombre_columna="Time", confirmada=True),
        canales=[_canal_rpm(columna=1)],
    )
    canales_actuales = [_canal_deducido("RPM", 0)]  # "Time" ya no existe en absoluto
    tiempo_actual = _tiempo(columna=0, nombre_columna="RPM", confirmada=False)
    resultado = reaplicar_perfil(
        perfil,
        nombres_columnas=["RPM"],
        formato_actual=_formato(),
        tiempo_actual=tiempo_actual,
        canales_actuales=canales_actuales,
    )
    assert resultado.tiempo.columna.origen == "deducido"  # no se reaplicó
    assert any("columna de tiempo confirmada" in a for a in resultado.avisos)


# --------------------------------------------------------------------------- #
# LA prueba obligatoria: confirmado sobrevive, deducido se vuelve a deducir
# --------------------------------------------------------------------------- #
def test_confirmado_sobrevive_y_deducido_se_rededuce() -> None:
    """El corazón de la tarea. El perfil guarda:
    - RPM: dimensión CONFIRMADA por el usuario (`angular_speed`) y rol
      EXACTA/confirmado.
    - Coolant Temp: dimensión y rol DIFUSA SIN confirmar (el usuario nunca
      llegó a pulsar "Confirmar" en el asistente).

    Al reaplicar sobre un sondeo nuevo que dedujo cosas DISTINTAS para
    ambos, el resultado tiene que ser: RPM conserva lo confirmado (ignora lo
    recién deducido); Coolant Temp usa lo recién deducido (ignora lo que
    había en el perfil, que nunca se confirmó)."""
    canal_temp_guardado = CanalImportado(
        nombre="Coolant Temp",
        columna=2,
        # Ni la dimensión ni la unidad se llegaron a confirmar en su momento:
        dimension_id=Campo(valor="temperature", origen="deducido"),
        unidad_origen=Campo(valor="degC", origen="deducido"),
        rol=RolDeCanal(
            rol="coolant_temp",
            confianza="DIFUSA",
            sinonimo="Coolant Temperature",
            indice=None,
            parecido=0.86,
            confirmado=False,  # DIFUSA sin confirmar: no sobrevive
        ),
    )
    perfil = crear_perfil(
        "coche",
        nombres_columnas=["RPM", "Coolant Temp"],
        formato=_formato(),
        tiempo=_tiempo(confirmada=False),
        canales=[
            _canal_rpm(dimension_confirmada=True),
            canal_temp_guardado,
        ],
    )

    canal_rpm_nuevo = CanalImportado(
        nombre="RPM",
        columna=0,
        dimension_id=Campo(valor="unknown", origen="deducido"),  # el sondeo nuevo dedujo OTRA cosa
        unidad_origen=Campo(valor=None, origen="deducido"),
        rol=None,
    )
    canal_temp_nuevo = CanalImportado(
        nombre="Coolant Temp",
        columna=1,
        dimension_id=Campo(valor="temperature", origen="deducido"),
        unidad_origen=Campo(valor="degF", origen="deducido"),  # el sondeo nuevo dedujo OTRA unidad
        rol=RolDeCanal(
            rol="oil_temp",  # el sondeo nuevo propone incluso OTRO rol
            confianza="DIFUSA",
            sinonimo="Oil Temperature",
            indice=None,
            parecido=0.7,
            confirmado=False,
        ),
    )

    resultado = reaplicar_perfil(
        perfil,
        nombres_columnas=["RPM", "Coolant Temp"],
        formato_actual=_formato(),
        tiempo_actual=_tiempo(confirmada=False),
        canales_actuales=[canal_rpm_nuevo, canal_temp_nuevo],
    )

    rpm = next(c for c in resultado.canales if c.nombre == "RPM")
    assert rpm.dimension_id.valor == "angular_speed"  # lo CONFIRMADO sobrevivió
    assert rpm.dimension_id.origen == "confirmado"
    assert rpm.rol is not None and rpm.rol.rol == "engine_speed" and rpm.rol.confirmado

    temp = next(c for c in resultado.canales if c.nombre == "Coolant Temp")
    assert temp.dimension_id.valor == "temperature"  # coincide, pero por REDEDUCCIÓN
    assert temp.dimension_id.origen == "deducido"  # no se marcó como confirmado
    assert temp.unidad_origen.valor == "degF"  # se volvió a deducir, no "degC" del perfil
    assert temp.rol is not None and temp.rol.rol == "oil_temp"  # el rol también se REDEDUJO
    assert temp.rol.confirmado is False


# --------------------------------------------------------------------------- #
# Perfil corrupto: nunca un KeyError/TypeError desnudo
# --------------------------------------------------------------------------- #
def test_perfil_desde_dict_vacio_da_error_con_mensaje() -> None:
    with pytest.raises(ErrorDePerfilImportacion, match="version_esquema"):
        PerfilImportacion.desde_dict({})


def test_version_de_esquema_desconocida_se_rechaza() -> None:
    bruto = _perfil_de_ejemplo().a_dict()
    bruto["version_esquema"] = 999
    with pytest.raises(ErrorDeVersionDePerfilDesconocida):
        PerfilImportacion.desde_dict(bruto)


def test_campo_sin_origen_valido_se_rechaza() -> None:
    bruto = _perfil_de_ejemplo().a_dict()
    formato = bruto["formato"]
    assert isinstance(formato, dict)
    delimitador = formato["delimitador"]
    assert isinstance(delimitador, dict)
    delimitador["origen"] = "puede ser"  # ni deducido ni confirmado
    with pytest.raises(ErrorDePerfilImportacion, match="origen"):
        PerfilImportacion.desde_dict(bruto)


def test_tipo_equivocado_en_un_campo_se_rechaza() -> None:
    bruto = _perfil_de_ejemplo().a_dict()
    formato = bruto["formato"]
    assert isinstance(formato, dict)
    fila_datos = formato["fila_datos"]
    assert isinstance(fila_datos, dict)
    fila_datos["valor"] = "no es un entero"
    with pytest.raises(ErrorDePerfilImportacion, match="entero"):
        PerfilImportacion.desde_dict(bruto)


def test_channels_que_no_es_una_lista_se_rechaza() -> None:
    bruto = _perfil_de_ejemplo().a_dict()
    bruto["canales"] = "no es una lista"
    with pytest.raises(ErrorDePerfilImportacion, match="canales"):
        PerfilImportacion.desde_dict(bruto)


def test_toml_ilegible_se_rechaza_sin_reventar() -> None:
    with pytest.raises(ErrorDePerfilImportacion, match="TOML inválido"):
        PerfilImportacion.desde_texto_toml("esto = no es [ toml válido")


def test_confianza_de_rol_desconocida_se_rechaza() -> None:
    bruto = _perfil_de_ejemplo().a_dict()
    canales = bruto["canales"]
    assert isinstance(canales, list)
    canales[0]["rol"]["confianza"] = "MUY_SEGURA"
    with pytest.raises(ErrorDePerfilImportacion, match="confianza"):
        PerfilImportacion.desde_dict(bruto)


def test_nombre_vacio_se_rechaza_al_crear() -> None:
    with pytest.raises(ErrorDePerfilImportacion):
        crear_perfil(
            "   ",
            nombres_columnas=[],
            formato=_formato(),
            tiempo=_tiempo(confirmada=False),
            canales=[],
        )


# --------------------------------------------------------------------------- #
# Ida y vuelta: dict y texto TOML
# --------------------------------------------------------------------------- #
def test_ida_y_vuelta_por_dict_conserva_origen_y_confirmado() -> None:
    perfil = _perfil_de_ejemplo()
    reconstruido = PerfilImportacion.desde_dict(perfil.a_dict())
    assert reconstruido == perfil


def test_ida_y_vuelta_por_texto_toml_conserva_el_perfil() -> None:
    perfil = _perfil_de_ejemplo()
    texto = perfil.a_texto_toml()
    reconstruido = PerfilImportacion.desde_texto_toml(texto)
    assert reconstruido == perfil


def test_el_texto_toml_es_de_verdad_toml_y_se_puede_editar_a_mano() -> None:
    """No es una curiosidad: la regla 5 del encargo asume que un usuario
    puede abrir el `.dlvimport` y tocarlo. Si `tomllib` no lo puede volver a
    leer, esa promesa es falsa."""
    import tomllib

    perfil = _perfil_de_ejemplo()
    texto = perfil.a_texto_toml()
    bruto = tomllib.loads(texto)
    assert bruto["nombre"] == "Mi coche - MoTeC"
    assert bruto["version_esquema"] == VERSION_ESQUEMA_PERFIL_IMPORTACION
    assert bruto["huella"]["delimitador"] == ";"


def test_texto_toml_conserva_un_valor_ausente_como_ausencia_de_clave() -> None:
    """`comilla` es `None` en el perfil de ejemplo: no debe aparecer como
    ninguna forma de "null" (TOML no tiene), sino como ausencia de la clave
    'valor' dentro de la tabla en línea."""
    perfil = _perfil_de_ejemplo()
    texto = perfil.a_texto_toml()
    assert "comilla = { origen = " in texto
    linea_comilla = next(linea for linea in texto.splitlines() if linea.startswith("comilla"))
    assert "valor" not in linea_comilla


def test_resumen_huella_de_huella_y_coincide_con() -> None:
    huella = construir_huella(["RPM", "Temp"], delimitador=";", codificacion="utf-8")
    resumen = ResumenHuella.de_huella(huella)
    assert resumen.coincide_con(huella)
    otra = construir_huella(["Temp", "RPM"], delimitador=";", codificacion="utf-8")
    assert not resumen.coincide_con(otra)
