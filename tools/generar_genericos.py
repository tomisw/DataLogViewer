#!/usr/bin/env python3
"""Generador de corpus de CSV genéricos para prueba del importador de FG.

Crea 16 ficheros CSV con distintas combinaciones de:
  - Delimitador (coma, punto y coma, tabulador)
  - Separador decimal (punto, coma)
  - Codificación (UTF-8, latin-1)
  - Cabecera (nombres, unidades, metadatos, sin nombres)
  - Columna de tiempo (epoch, ISO-8601, relativa, ninguna)
  - Casos de robustez (valores ausentes, duplicados, booleanos, filas de
    longitud variable -- FG-14)

Determinista: seed fijo por defecto. Los ficheros 01-14 son de FG-01..FG-13;
no se tocan al añadir los 15-16 de FG-14 porque se generan DESPUÉS en la
misma secuencia de `random.Random`, así que el estado del RNG que ven los
quince primeros generadores no cambia.
"""

import argparse
import csv
import io
import random
from datetime import datetime, timedelta
from pathlib import Path

# Realidad física del motor
CHANNELS = {
    "Time": {
        "values_epoch_s": lambda rng, i, count: (
            1785000000 + (i * 0.05)  # epoch segundos con 50 ms de intervalo
        ),
        "values_relative_s": lambda rng, i, count: i * 0.05,
        "values_iso8601": lambda rng, i, count: (
            (
                datetime(2026, 7, 29, 18, 30, 0, tzinfo=None) + timedelta(milliseconds=i * 50)
            ).isoformat()
            + "Z"
        ),
        "unit": "s",
    },
    "RPM": {
        "values": lambda rng, i, count: rng.randint(800, 7000),
        "unit": "rpm",
    },
    "MAP": {
        "values": lambda rng, i, count: round(rng.uniform(30, 250), 2),
        "unit": "kPa",
    },
    "TPS": {
        "values": lambda rng, i, count: round(rng.uniform(0, 100), 1),
        "unit": "%",
    },
    "CLT": {
        "values": lambda rng, i, count: round(rng.uniform(70, 105), 1),
        "unit": "C",
    },
    "Lambda": {
        "values": lambda rng, i, count: round(rng.uniform(0.75, 1.05), 3),
        "unit": "ratio",
    },
    "AFR": {
        "values": lambda rng, i, count: round(rng.uniform(12, 16), 2),
        "unit": "ratio",
    },
}


def format_value(value, delimiter, decimal_sep, channel=None):
    """Formatea un valor según delimitador y separador decimal."""
    if value is None:
        return ""
    if isinstance(value, float):
        s = f"{value:.3f}" if "." in str(value) else str(value)
        if decimal_sep == ",":
            s = s.replace(".", ",")
        return s
    return str(value)


def write_csv(
    filepath,
    rows,
    delimiter=",",
    decimal_sep=".",
    encoding="utf-8",
    include_bom=False,
):
    """Escribe CSV con parámetros específicos."""
    output = io.StringIO()

    if delimiter == "\t":
        # Para tabuladores, no usamos csv.writer
        for row in rows:
            formatted = [format_value(v, delimiter, decimal_sep) for v in row]
            output.write("\t".join(formatted) + "\n")
    else:
        writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
        for row in rows:
            formatted = [format_value(v, delimiter, decimal_sep) for v in row]
            writer.writerow(formatted)

    content = output.getvalue()

    # Escribir con BOM si es necesario
    with open(filepath, "w", encoding=encoding) as f:
        if include_bom and encoding == "utf-8":
            f.write("﻿")
        f.write(content)


def generate_01_coma_punto(rng, output_dir):
    """Caso fácil: delimitador , y decimal ."""
    rows = [["Time", "RPM", "MAP", "TPS", "CLT", "Lambda"]]

    for i in range(50):
        rows.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "01-coma-punto.csv", rows, delimiter=",", decimal_sep=".")


def generate_02_puntoycoma_coma(rng, output_dir):
    """Delimitador ; y decimal coma (CSV español, sin puntos en celdas)."""
    rows = [["Time", "RPM", "MAP", "TPS", "CLT", "Lambda"]]

    for i in range(50):
        rows.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "02-puntoycoma-coma.csv", rows, delimiter=";", decimal_sep=",")


def generate_03_tabulaciones(rng, output_dir):
    """Delimitador tabulador."""
    rows = [["Time", "RPM", "MAP", "TPS", "CLT", "Lambda"]]

    for i in range(50):
        rows.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "03-tabulaciones.csv", rows, delimiter="\t", decimal_sep=".")


def generate_04_fila_de_unidades(rng, output_dir):
    """Fila de nombres + fila de unidades antes de datos."""
    rows = [
        ["Time", "RPM", "MAP", "TPS", "CLT", "Lambda"],
        ["s", "rpm", "kPa", "%", "C", "ratio"],
    ]

    for i in range(50):
        rows.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "04-fila-de-unidades.csv", rows, delimiter=",", decimal_sep=".")


def generate_05_unidad_en_el_nombre(rng, output_dir):
    """Unidad dentro del nombre: RPM [rpm], CLT (°C), MAP [kPa]."""
    rows = [["Time [s]", "RPM [rpm]", "MAP [kPa]", "TPS (%)", "CLT (°C)", "Lambda [ratio]"]]

    for i in range(50):
        rows.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "05-unidad-en-el-nombre.csv", rows, delimiter=",", decimal_sep=".")


def generate_06_sin_columna_de_tiempo(rng, output_dir):
    """Sin columna temporal, solo canales."""
    rows = [["RPM", "MAP", "TPS", "CLT", "Lambda", "AFR"]]

    for _i in range(50):
        rows.append(
            [
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
                round(rng.uniform(12, 16), 2),
            ]
        )

    write_csv(output_dir / "06-sin-columna-de-tiempo.csv", rows, delimiter=",", decimal_sep=".")


def generate_07_epoch_segundos(rng, output_dir):
    """Epoch Unix en segundos con decimales."""
    rows = [["Timestamp", "RPM", "MAP", "TPS", "CLT", "Lambda"]]
    base_epoch = 1785000000

    for i in range(50):
        rows.append(
            [
                base_epoch + i * 0.05,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "07-epoch-segundos.csv", rows, delimiter=",", decimal_sep=".")


def generate_08_epoch_milisegundos(rng, output_dir):
    """Epoch Unix en milisegundos (entero)."""
    rows = [["Timestamp_ms", "RPM", "MAP", "TPS", "CLT", "Lambda"]]
    base_epoch_ms = 1785000000000

    for i in range(50):
        rows.append(
            [
                int(base_epoch_ms + i * 50),
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "08-epoch-milisegundos.csv", rows, delimiter=",", decimal_sep=".")


def generate_09_iso8601(rng, output_dir):
    """ISO-8601: 2026-07-29T18:30:35.506Z."""
    rows = [["DateTime", "RPM", "MAP", "TPS", "CLT", "Lambda"]]
    base_dt = datetime(2026, 7, 29, 18, 30, 0)

    for i in range(50):
        dt = base_dt + timedelta(milliseconds=i * 50)
        iso_str = dt.isoformat() + "Z"
        rows.append(
            [
                iso_str,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "09-iso8601.csv", rows, delimiter=",", decimal_sep=".")


def generate_10_latin1(rng, output_dir):
    """Codificado en latin-1 con acentos en nombres."""
    rows = [
        [
            "Tiempo",
            "Velocidad_motor",
            "Presión_colector",
            "Posición_mariposa",
            "Temperatura_refrigerante",
            "Lambda_medido",
        ]
    ]

    for i in range(50):
        rows.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(
        output_dir / "10-latin1.csv",
        rows,
        delimiter=",",
        decimal_sep=".",
        encoding="latin-1",
    )


def generate_11_valores_ausentes(rng, output_dir):
    """Valores ausentes: NaN, #N/A, NULL, ---, n/a, vacío."""
    rows = [["Time", "RPM", "MAP", "TPS", "CLT", "Lambda"]]
    missing_values = ["NaN", "#N/A", "NULL", "---", "n/a", ""]

    for i in range(50):
        row = [i * 0.05]
        for col_idx, _col_name in enumerate(["RPM", "MAP", "TPS", "CLT", "Lambda"]):
            if rng.random() < 0.1:  # 10% de probabilidad de ausencia
                row.append(rng.choice(missing_values))
            else:
                if col_idx == 0:  # RPM
                    row.append(rng.randint(800, 7000))
                elif col_idx == 1:  # MAP
                    row.append(round(rng.uniform(30, 250), 2))
                elif col_idx == 2:  # TPS
                    row.append(round(rng.uniform(0, 100), 1))
                elif col_idx == 3:  # CLT
                    row.append(round(rng.uniform(70, 105), 1))
                elif col_idx == 4:  # Lambda
                    row.append(round(rng.uniform(0.75, 1.05), 3))
        rows.append(row)

    write_csv(output_dir / "11-valores-ausentes.csv", rows, delimiter=",", decimal_sep=".")


def generate_12_texto_y_booleanos(rng, output_dir):
    """Columna de texto (Marcha: N,1,2,3) y booleana (Limitador: true/false)."""
    rows = [["Time", "RPM", "Marcha", "Limitador", "CLT", "Lambda"]]
    marchas = ["N", "1", "2", "3"]

    for i in range(50):
        rows.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                rng.choice(marchas),
                rng.choice(["true", "false"]),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "12-texto-y-booleanos.csv", rows, delimiter=",", decimal_sep=".")


def generate_13_columnas_duplicadas(rng, output_dir):
    """Dos columnas con el mismo nombre exacto."""
    rows = [["Time", "RPM", "RPM", "MAP", "TPS", "CLT"]]

    for i in range(50):
        rows.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
            ]
        )

    write_csv(output_dir / "13-columnas-duplicadas.csv", rows, delimiter=",", decimal_sep=".")


def generate_14_preambulo_largo(rng, output_dir):
    """12 líneas de metadatos clave: valor antes de la fila de nombres."""
    content = (
        "vehicle: Track car - GT\n"
        "engine: 2000cc turbo\n"
        "date: 2026-07-29\n"
        "driver: John Doe\n"
        "track: Spa Francorchamps\n"
        "session: Qualifying 1\n"
        "temperature: 22.5C\n"
        "weather: Cloudy\n"
        "fuel: 98 RON\n"
        "boost: 1.6 bar\n"
        "downforce: low\n"
        "notes: Practice session with setup changes\n"
    )

    rows_data = [
        ["Time", "RPM", "MAP", "TPS", "CLT", "Lambda"],
    ]

    for i in range(50):
        rows_data.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    # Escribir manualmente para incluir preámbulo
    with open(output_dir / "14-preambulo-largo.csv", "w", encoding="utf-8") as f:
        f.write(content)
        writer = csv.writer(f, delimiter=",", lineterminator="\n")
        for row in rows_data:
            formatted = [format_value(v, ",", ".") for v in row]
            writer.writerow(formatted)


def generate_15_filas_longitud_variable(rng, output_dir):
    """Filas de longitud variable (FG-14, docs/07 §7.10): una fila corta (le
    faltan CLT y Lambda) y una fila larga (un campo de sobra sin columna).

    Solo dos filas ragged, y cerca del final: con más, o repartidas de otra
    forma, la racha consistente de FG-01 (sondeo.py) baja de CONFIANZA_MINIMA
    y el delimitador deja de detectarse -- que sondeo.py avise de
    'campos_inconsistentes' está bien (es justo lo que se espera de un
    fichero con filas malformadas); que deje de proponer delimitador, no.
    """
    rows = [["Time", "RPM", "MAP", "TPS", "CLT", "Lambda"]]
    fila_corta = 45  # a esta fila le faltan los dos últimos campos
    fila_larga = 48  # a esta fila le sobra uno

    for i in range(50):
        fila = [
            i * 0.05,
            rng.randint(800, 7000),
            round(rng.uniform(30, 250), 2),
            round(rng.uniform(0, 100), 1),
            round(rng.uniform(70, 105), 1),
            round(rng.uniform(0.75, 1.05), 3),
        ]
        if i == fila_corta:
            fila = fila[:4]  # faltan CLT y Lambda: hueco, no cero (§7.10)
        elif i == fila_larga:
            fila = [*fila, round(rng.uniform(0, 5), 2)]  # campo de sobra
        rows.append(fila)

    write_csv(output_dir / "15-filas-longitud-variable.csv", rows, delimiter=",", decimal_sep=".")


def generate_16_cabecera_sin_nombres(rng, output_dir):
    """Sin fila de nombres: los datos empiezan en la primera línea del
    fichero (FG-14, docs/07 §7.10: "se nombran col_1…col_n")."""
    rows = []

    for i in range(50):
        rows.append(
            [
                i * 0.05,
                rng.randint(800, 7000),
                round(rng.uniform(30, 250), 2),
                round(rng.uniform(0, 100), 1),
                round(rng.uniform(70, 105), 1),
                round(rng.uniform(0.75, 1.05), 3),
            ]
        )

    write_csv(output_dir / "16-cabecera-sin-nombres.csv", rows, delimiter=",", decimal_sep=".")


def main():
    parser = argparse.ArgumentParser(
        description="Generador de corpus de CSV genéricos para DataLogViewer"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla para RNG determinista (default: 42)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("samples/generico"),
        help="Directorio de salida (default: samples/generico)",
    )

    args = parser.parse_args()

    # Crear directorio de salida
    args.output.mkdir(parents=True, exist_ok=True)

    # Inicializar RNG con seed
    rng = random.Random(args.seed)

    # Generar todos los ficheros
    generators = [
        generate_01_coma_punto,
        generate_02_puntoycoma_coma,
        generate_03_tabulaciones,
        generate_04_fila_de_unidades,
        generate_05_unidad_en_el_nombre,
        generate_06_sin_columna_de_tiempo,
        generate_07_epoch_segundos,
        generate_08_epoch_milisegundos,
        generate_09_iso8601,
        generate_10_latin1,
        generate_11_valores_ausentes,
        generate_12_texto_y_booleanos,
        generate_13_columnas_duplicadas,
        generate_14_preambulo_largo,
        generate_15_filas_longitud_variable,
        generate_16_cabecera_sin_nombres,
    ]

    for gen in generators:
        gen(rng, args.output)

    print(f"✓ Generados {len(generators)} ficheros CSV en {args.output}")


if __name__ == "__main__":
    main()
