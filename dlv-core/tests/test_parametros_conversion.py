"""Pruebas de la resolución de parámetros para conversiones (tarea F1-14).

El caso guía, de principio a fin: λ → AFR usando la estequiometría real del
AutoLog (no la constante 14,7 cableada), tal como exige
`docs/06-sistema-de-unidades.md` y anota `data/formats/haltech_nsp.toml
[tipos.Stoichiometry]` ("este canal es el parámetro de la conversión
λ → AFR"). Casos conocidos de docs/06 §6.12: λ 1,0 = AFR 14,7 con
estequiometría de gasolina.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dlv_core.formatos.cuerpo import columna_polars, parsear_cuerpo
from dlv_core.formatos.haltech import Descriptor, cargar_descriptor, parsear_cabecera
from dlv_core.parametros_conversion import resolver_parametro_de_canal
from dlv_core.unidades import Catalogo, Clase, cargar_catalogo, desde_canonica

RAIZ = Path(__file__).resolve().parents[2]
DESCRIPTOR_TOML = RAIZ / "data" / "formats" / "haltech_nsp.toml"
UNITS_TOML = RAIZ / "data" / "units.toml"
AUTOLOG_REAL = RAIZ / "samples" / "real" / "AutoLog_20260729_1830.csv"

ID_ESTEQUIOMETRIA = 57  # "Fuel Tuning Current Stoichiometry" (docs/04 §4.5)


@pytest.fixture(scope="module")
def desc() -> Descriptor:
    with DESCRIPTOR_TOML.open("rb") as fh:
        return cargar_descriptor(fh)


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    with UNITS_TOML.open("rb") as fh:
        return cargar_catalogo(fh)


# --------------------------------------------------------------------------- #
# resolver_parametro_de_canal: casos de juguete
# --------------------------------------------------------------------------- #
def test_valor_constante_no_produce_aviso() -> None:
    valores = np.array([14.7, 14.7, 14.7, 14.7])
    resultado = resolver_parametro_de_canal(valores, rol="stoichiometry")
    assert resultado.valor == pytest.approx(14.7)
    assert resultado.aviso is None


def test_pequeno_ruido_dentro_de_tolerancia_no_produce_aviso() -> None:
    valores = np.array([14.70, 14.701, 14.699, 14.70])
    resultado = resolver_parametro_de_canal(valores, rol="stoichiometry", tolerancia_relativa=0.01)
    assert resultado.aviso is None


def test_variacion_real_produce_aviso_pero_sigue_devolviendo_la_mediana() -> None:
    """Un cambio de combustible a mitad de log (o el canal equivocado): se
    avisa (E1.7), no se rechaza el log."""
    valores = np.array([14.7, 14.7, 9.8, 9.8, 9.8])  # gasolina -> etanol, o similar
    resultado = resolver_parametro_de_canal(valores, rol="stoichiometry")
    assert resultado.aviso is not None
    assert resultado.aviso.codigo == "parametro_no_constante"
    assert "stoichiometry" in resultado.aviso.mensaje
    assert resultado.valor == pytest.approx(float(np.median(valores)))


def test_sin_muestras_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="stoichiometry"):
        resolver_parametro_de_canal(np.array([]), rol="stoichiometry")


def test_mediana_cero_no_divide_por_cero() -> None:
    """Caso de esquina del cálculo de tolerancia relativa: mediana 0 no debe
    lanzar ZeroDivisionError ni dar un aviso espurio por ruido mínimo."""
    valores = np.array([0.0, 0.0, 0.0])
    resultado = resolver_parametro_de_canal(valores, rol="algo")
    assert resultado.valor == 0.0
    assert resultado.aviso is None


# --------------------------------------------------------------------------- #
# Integración completa: λ -> AFR con la estequiometría real del AutoLog
# --------------------------------------------------------------------------- #
def test_lambda_a_afr_con_la_estequiometria_real_del_autolog(
    desc: Descriptor, catalogo: Catalogo
) -> None:
    datos = AUTOLOG_REAL.read_bytes()
    cab = parsear_cabecera(datos, desc)
    df = parsear_cuerpo(datos, cab)

    canal_estq = cab.por_id(ID_ESTEQUIOMETRIA)
    assert canal_estq is not None
    assert canal_estq.tipo == "Stoichiometry"

    columna = columna_polars(canal_estq.columna)
    crudos = df[columna].drop_nulls().to_numpy()
    canonicos = crudos * canal_estq.a_canonica  # a_canonica = 0.001

    resultado = resolver_parametro_de_canal(canonicos, rol="stoichiometry")

    # Caso conocido de docs/01 §1.x y docs/04 §4.5: gasolina, 14700 crudo -> 14,7.
    assert resultado.valor == pytest.approx(14.7)
    assert resultado.aviso is None  # constante en todo el log real

    dim_mezcla = catalogo.dimension("mixture_ratio")

    # Caso conocido de docs/06 §6.12: λ 1,0 = AFR 14,7 con estequiometría de gasolina.
    afr = desde_canonica(
        1.0, dimension=dim_mezcla, unidad="afr", clase=Clase.PUNTO, param=resultado.valor
    )
    assert afr == pytest.approx(14.7)

    # λ 0,850 = φ 1,176 (docs/06 §6.12) usa una conversión distinta (recíproca,
    # sin parámetro); aquí solo se confirma que AFR escala linealmente con λ.
    afr_pobre = desde_canonica(
        1.2, dimension=dim_mezcla, unidad="afr", clase=Clase.PUNTO, param=resultado.valor
    )
    assert afr_pobre == pytest.approx(14.7 * 1.2)
