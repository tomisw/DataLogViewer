#!/usr/bin/env python3
"""
Extrae canales enum del log real y genera data/enums.toml.

Criterio (docs/01-formato-log.md §1.10):
- 75 canales con Type: Raw, DisplayMaxMin presente, abs(max) <= 20
- Más 2 máscaras de bits: Engine Protection Cause y Trigger System Errors

Los valores observados se extraen de las filas de datos, ignorando celdas vacías.
"""

import re
from collections import defaultdict
from pathlib import Path


def parse_csv_header(csv_path):
    """Parsea la cabecera del CSV y retorna lista de canales con metadatos."""
    channels = []
    current_channel = {}

    with open(csv_path, encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        line = line.rstrip("\r\n")

        # Fin de cabecera: detecta la línea "Log Source" o similar
        if line.startswith("Log Source"):
            break

        # Bloques de canal: Channel, ID, Type, DisplayMaxMin
        if line.startswith("Channel : "):
            if current_channel and "id" in current_channel:
                channels.append(current_channel)
            current_channel = {
                "name": line.replace("Channel : ", "", 1),
                "has_display_max_min": False,
                "display_max": None,
                "display_min": None,
            }
        elif line.startswith("ID : "):
            current_channel["id"] = int(line.replace("ID : ", "", 1))
        elif line.startswith("Type : "):
            current_channel["type"] = line.replace("Type : ", "", 1)
        elif line.startswith("DisplayMaxMin : "):
            display_max_min = line.replace("DisplayMaxMin : ", "", 1)
            parts = display_max_min.split(",")
            if len(parts) == 2:
                try:
                    current_channel["display_max"] = float(parts[0])
                    current_channel["display_min"] = float(parts[1])
                    current_channel["has_display_max_min"] = True
                except ValueError:
                    pass

    # Añade el último canal si existe
    if current_channel and "id" in current_channel:
        channels.append(current_channel)

    return channels


def find_data_start(csv_path):
    """Encuentra la línea donde comienzan los datos (primera marca de tiempo)."""
    with open(csv_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\r\n")
            # Las marcas de tiempo empiezan con HH:MM:SS
            if re.match(r"^\d{2}:\d{2}:\d{2}", line):
                return i
    return None


def extract_column_order(csv_path, channels):
    """
    Extrae el orden de columnas del CSV.
    Los canales aparecen en el orden en que se declaran en la cabecera.
    Retorna {canal_id: column_index}.
    """
    col_map = {channels[i]["id"]: i + 1 for i in range(len(channels))}
    return col_map


def extract_observed_values(csv_path, channels, col_map):
    """
    Lee las filas de datos y extrae los valores observados para cada canal.
    Retorna {canal_id: sorted_list_of_unique_values}.
    """
    observed = defaultdict(set)
    data_start = find_data_start(csv_path)

    if data_start is None:
        return {}

    with open(csv_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < data_start:
                continue
            line = line.rstrip("\r\n")
            parts = line.split(",")

            # Primera columna es la marca de tiempo (la saltamos)
            for canal_id, col_idx in col_map.items():
                if col_idx < len(parts):
                    value_str = parts[col_idx].strip()
                    if value_str:  # Ignora celdas vacías
                        try:
                            value = float(value_str)
                            observed[canal_id].add(value)
                        except ValueError:
                            pass

    # Convierte a listas ordenadas
    return {k: sorted(v) for k, v in observed.items()}


def filter_candidates(channels, observed_values):
    """
    Filtra los candidatos según criterio: Type=Raw, DisplayMaxMin <= 20.
    Retorna lista de canales candidatos.
    """
    candidates = []

    for ch in channels:
        # Saltar si no tiene Type
        if "type" not in ch:
            continue

        # Solo Type: Raw
        if ch["type"] != "Raw":
            continue

        # DisplayMaxMin debe estar presente
        if not ch["has_display_max_min"]:
            continue

        # abs(max) <= 20
        if ch["display_max"] is None or abs(ch["display_max"]) > 20:
            continue

        candidates.append(ch)

    return candidates


def get_channel_class(channel, observed_values):
    """
    Determina la clase del canal: enum, booleano, bitmask, contador.
    """
    channel_id = channel["id"]
    name = channel["name"]

    # Bitmask: solo para dos canales específicos
    if name == "Engine Protection Cause" or name == "Trigger System Errors":
        return "bitmask"

    # Contador: contiene "Count" o "Counter"
    if "Count" in name or "Counter" in name:
        return "contador"

    # Booleano: rango exactamente [0,1] o [0,2] y valores observados son 0 y/o 1
    display_max = channel["display_max"]
    display_min = channel["display_min"]

    if (display_max == 1 or display_max == 2) and display_min == 0:
        observed = observed_values.get(channel_id, [])
        if all(v in [0, 1] for v in observed):
            return "booleano"

    # Por defecto: enum
    return "enum"


def get_channel_role(channel_name):
    """
    Asigna el rol del canal si existe en data/roles.toml.
    Basado en los nombres de canales que ya aparecen en roles.toml.
    """
    role_map = {
        "RPM Limiter Active": "limiter_active",
        "Engine Limiter Active": "limiter_active",
        "Rev Limiter": "limiter_active",
        "Engine Protection Severity Level": "protection_level",
        "Protection Level": "protection_level",
        "Engine Protection Cause": "protection_cause",
        "Protection Cause": "protection_cause",
        "Trigger System Errors": "trigger_errors",
        "Trigger Errors": "trigger_errors",
        "Sync Errors": "trigger_errors",
        "Launch Control State": "launch_state",
        "Launch State": "launch_state",
        "Idle Control State": "idle_state",
        "Idle State": "idle_state",
        "Boost Control State": "boost_state",
        "Boost State": "boost_state",
    }
    return role_map.get(channel_name)


def generate_toml(candidates, observed_values, output_path):
    """
    Genera el archivo TOML con los canales enumerados.
    """
    lines = []

    # Cabecera con comentarios
    lines.append("# DataLogViewer — Catálogo de canales enumerados (enums)")
    lines.append("#")
    lines.append("# Tarea F0-11. Especificación: docs/01-formato-log.md §1.10")
    lines.append("#")
    lines.append("# Este archivo contiene los 75 canales candidatos a enumeración")
    lines.append("# (Type: Raw con rango ≤ 20) más las 2 máscaras de bits especiales:")
    lines.append("# Engine Protection Cause (0…65535) y Trigger System Errors (0…31).")
    lines.append("#")
    lines.append("# IMPORTANTE: Los códigos están SIN TRADUCIR a propósito. La asignación")
    lines.append("# código → nombre requiere documentación del fabricante (tarea F3-15).")
    lines.append("# Hasta entonces, los códigos desconocidos se muestran como «Estado N».")
    lines.append("#")
    lines.append("# Los canales bitmask (Protection Cause, Trigger Errors) no son líneas")
    lines.append("# continuas: se decodifican bit a bit y se dibujan como carriles apilados.")
    lines.append("#")
    lines.append("")

    # Metadatos
    lines.append("[meta]")
    lines.append("version = 1")
    lines.append('tarea = "F0-11"')
    lines.append('especificacion = "docs/01-formato-log.md §1.10"')
    lines.append("")
    lines.append("[canales]")
    lines.append("")

    # Entradas por canal
    for ch in candidates:
        channel_id = ch["id"]
        name = ch["name"]
        display_max = ch["display_max"]
        display_min = ch["display_min"]

        class_name = get_channel_class(ch, observed_values)
        role = get_channel_role(name)
        obs_values = observed_values.get(channel_id, [])

        # Formato de entrada
        lines.append(f'[canales."{name}"]')
        lines.append(f"id = {int(channel_id)}")
        lines.append(f"rango = {{ min = {int(display_min)}, max = {int(display_max)} }}")
        lines.append(f'clase = "{class_name}"')

        if role:
            lines.append(f'rol = "{role}"')

        # Valores observados
        values_str = "[" + ", ".join(str(int(v)) for v in obs_values) + "]"
        lines.append(f"valores_observados = {values_str}")

        # Códigos vacíos
        lines.append("codigos = {}")
        lines.append("")

    # Escribe el archivo
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Escrito: {output_path}")
    print(f"Canales totales: {len(candidates)}")


def main():
    csv_path = Path("samples/real/AutoLog_20260729_1830.csv")
    output_path = Path("data/enums.toml")

    if not csv_path.exists():
        print(f"Error: {csv_path} no existe")
        return 1

    # Parsea cabecera
    print("Parseando cabecera...")
    channels = parse_csv_header(csv_path)
    print(f"  Total de canales en cabecera: {len(channels)}")

    # Extrae orden de columnas
    col_map = extract_column_order(csv_path, channels)

    # Extrae valores observados
    print("Extrayendo valores observados...")
    observed_values = extract_observed_values(csv_path, channels, col_map)
    print(f"  Canales con datos: {len(observed_values)}")

    # Filtra candidatos
    print("Filtrando candidatos (Type=Raw, DisplayMaxMin <= 20)...")
    candidates = filter_candidates(channels, observed_values)
    print(f"  Candidatos encontrados: {len(candidates)}")

    # Añade las dos máscaras de bits si existen
    print("Buscando máscaras de bits...")
    bitmasks = [
        ch
        for ch in channels
        if ch.get("name") in ["Engine Protection Cause", "Trigger System Errors"]
    ]
    print(f"  Máscaras de bits encontradas: {len(bitmasks)}")

    all_candidates = candidates + bitmasks
    print(f"  Total (candidatos + bitmasks): {len(all_candidates)}")

    # Ordena por ID para reproducibilidad
    all_candidates.sort(key=lambda x: x["id"])

    # Genera TOML
    print("\nGenerando TOML...")
    generate_toml(all_candidates, observed_values, output_path)

    return 0


if __name__ == "__main__":
    exit(main())
