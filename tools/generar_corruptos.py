#!/usr/bin/env python3
"""
Generador de corpus de logs corruptos para tests del parser.
Crea 11 ficheros con anomalías específicas a partir del log real.
"""

import argparse
import re
from pathlib import Path


def read_original():
    """Lee el fichero original preservando line endings."""
    original_path = Path(__file__).parent.parent / "samples" / "real" / "20260729_1859_Log2768.csv"
    with open(original_path, "rb") as f:
        content = f.read()

    # Detecta el separador de línea
    line_sep = b"\r\n" if b"\r\n" in content else b"\n"

    # Verifica si el archivo termina con el separador
    has_final_sep = content.endswith(line_sep)

    # Divide preservando el separador
    lines = content.split(line_sep)
    # Remove empty last element if file ends with separator
    if lines and not lines[-1]:
        lines = lines[:-1]

    # Busca el inicio de data
    data_start = 0
    for i, line in enumerate(lines):
        if re.match(rb"^\d{2}:\d{2}:\d{2}\.\d{3},", line):
            data_start = i
            break

    header_lines = lines[:data_start]
    data_lines = lines[data_start:]

    return header_lines, data_lines, line_sep, has_final_sep


def ensure_corrupt_dir():
    """Crea el directorio samples/corrupt si no existe."""
    corrupt_dir = Path(__file__).parent.parent / "samples" / "corrupt"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    return corrupt_dir


def write_file(content, filename, corrupt_dir):
    """Escribe el fichero con el contenido especificado (bytes)."""
    filepath = corrupt_dir / filename
    with open(filepath, "wb") as f:
        f.write(content)


def create_01_cabecera_truncada(header_lines, line_sep, corrupt_dir):
    """01: Corta el fichero a mitad de un bloque Channel/ID/Type sin filas de datos."""
    truncated = line_sep.join(header_lines[:55])
    write_file(truncated, "01-cabecera-truncada.csv", corrupt_dir)


def create_02_fila_corta(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir):
    """02: Una fila de datos en el medio con menos campos que toca."""
    header = line_sep.join(header_lines)
    # Toma primeras 10 filas de datos, corta una en el medio
    data = []
    for i, line in enumerate(data_lines[:20]):
        if i == 10:
            # Corta esta fila: toma solo los primeros 5 campos
            parts = line.split(b",")
            line = b",".join(parts[:5])
        data.append(line)

    content = header + line_sep + line_sep.join(data)
    if has_final_sep:
        content += line_sep
    write_file(content, "02-fila-corta.csv", corrupt_dir)


def create_03_fila_larga(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir):
    """03: Una fila de datos en el medio con más campos que toca."""
    header = line_sep.join(header_lines)
    data = []
    for i, line in enumerate(data_lines[:20]):
        if i == 10:
            # Añade campos extra
            line = line + b",999,888,777"
        data.append(line)

    content = header + line_sep + line_sep.join(data)
    if has_final_sep:
        content += line_sep
    write_file(content, "03-fila-larga.csv", corrupt_dir)


def create_04_sin_displaymaxmin(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir):
    """04: Quita líneas DisplayMaxMin de 3 canales (sigue siendo válido)."""
    header = []
    remove_count = 0
    for line in header_lines:
        # Elimina DisplayMaxMin de los primeros 3 canales que la tengan
        if line.startswith(b"DisplayMaxMin") and remove_count < 3:
            remove_count += 1
            continue
        header.append(line)

    full_content = line_sep.join(header) + line_sep + line_sep.join(data_lines)
    if has_final_sep:
        full_content += line_sep
    write_file(full_content, "04-sin-displaymaxmin.csv", corrupt_dir)


def create_05_bom_utf8(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir):
    """05: Idéntico pero con BOM UTF-8 al principio."""
    content = line_sep.join(header_lines) + line_sep + line_sep.join(data_lines)
    if has_final_sep:
        content += line_sep
    # Prepend UTF-8 BOM
    bom_content = b"\xef\xbb\xbf" + content
    write_file(bom_content, "05-bom-utf8.csv", corrupt_dir)


def create_06_lf_solo(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir):
    """06: Todos los finales de línea en LF, sin CR.

    El caso original de la especificación era «todos los finales en CRLF», pero
    al verificar el corpus se descubrió que **el log real ya es CRLF nativo**
    (557 CRLF y ningún LF suelto en `20260729_1859_Log2768.csv`). Es decir: los
    otros diez ficheros de este corpus ya cubren CRLF, y el fichero CRLF era
    byte a byte idéntico al original, así que no probaba nada.

    La variante que de verdad falta es la contraria: LF solo, que es lo que
    produce cualquier herramienta que reescriba el log en Unix. Ese es el caso
    que este fichero ejercita.
    """
    content = line_sep.join(header_lines) + line_sep + line_sep.join(data_lines)
    if has_final_sep:
        content += line_sep
    content = content.replace(b"\r\n", b"\n")
    write_file(content, "06-lf-solo.csv", corrupt_dir)


def create_07_sin_salto_final(header_lines, data_lines, line_sep, corrupt_dir):
    """07: Idéntico al original pero sin newline al final."""
    content = line_sep.join(header_lines) + line_sep + line_sep.join(data_lines)
    # No añade separador final
    write_file(content, "07-sin-salto-final.csv", corrupt_dir)


def create_08_marcas_no_monotonas(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir):
    """08: Dos filas en el medio con marca de tiempo invertida."""
    header = line_sep.join(header_lines)
    data = list(data_lines)

    # Invierte los timestamps de las filas 100 y 101
    if len(data) > 101:
        parts_100 = data[100].split(b",", 1)
        parts_101 = data[101].split(b",", 1)
        ts_100 = parts_100[0]
        ts_101 = parts_101[0]
        rest_100 = parts_100[1] if len(parts_100) > 1 else b""
        rest_101 = parts_101[1] if len(parts_101) > 1 else b""
        # Intercambia los timestamps
        data[100] = ts_101 + b"," + rest_100
        data[101] = ts_100 + b"," + rest_101

    content = header + line_sep + line_sep.join(data)
    if has_final_sep:
        content += line_sep
    write_file(content, "08-marcas-no-monotonas.csv", corrupt_dir)


def create_09_cruce_medianoche(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir):
    """09: Reescribe marcas para pasar de 23:59:58.xxx a 00:00:01.xxx."""
    header = line_sep.join(header_lines)
    data = []

    for i, line in enumerate(data_lines):
        # A partir de la fila 400, reescribe los timestamps
        if i >= 400:
            parts = line.split(b",", 1)
            ts = parts[0]
            rest = parts[1] if len(parts) > 1 else b""

            # Convierte a minutos desde medianoche
            try:
                ts_str = ts.decode("utf-8")
                h, m_s = ts_str.split(":", 1)
                m, s_ms = m_s.split(":", 1)
                minutes = int(h) * 60 + int(m)

                # Si está después del minuto 80, ajusta para cruzar medianoche
                if minutes > 80:
                    new_minutes = 1439 + (i - 400) % 2
                    new_h = new_minutes // 60
                    new_m = new_minutes % 60
                    ts = f"{new_h:02d}:{new_m:02d}:{s_ms}".encode()
            except (ValueError, AttributeError):
                pass

            line = ts + b"," + rest

        data.append(line)

    content = header + line_sep + line_sep.join(data)
    if has_final_sep:
        content += line_sep
    write_file(content, "09-cruce-medianoche.csv", corrupt_dir)


def create_10_version_desconocida(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir):
    """10: Cambia DataLogVersion a 2.0 (debe rechazarse)."""
    header = []
    for line in header_lines:
        if line.startswith(b"DataLogVersion"):
            line = b"DataLogVersion : 2.0"
        header.append(line)

    content = line_sep.join(header) + line_sep + line_sep.join(data_lines)
    if has_final_sep:
        content += line_sep
    write_file(content, "10-version-desconocida.csv", corrupt_dir)


def create_11_centinelas(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir):
    """11: Mete valores centinela en varias celdas numéricas del medio."""
    header = line_sep.join(header_lines)
    data = list(data_lines)

    sentinels = [2147483647, -2147483645, 8388607]
    sentinel_idx = 0

    # Inyecta centinelas en filas del medio
    for i in range(100, min(150, len(data))):
        parts = data[i].split(b",")
        if len(parts) > 5:
            # Reemplaza algunos campos con centinelas
            sentinel = sentinels[sentinel_idx % len(sentinels)]
            parts[3] = str(sentinel).encode()
            parts[7] = str(sentinels[(sentinel_idx + 1) % len(sentinels)]).encode()
            sentinel_idx += 1
            data[i] = b",".join(parts)

    content = header + line_sep + line_sep.join(data)
    if has_final_sep:
        content += line_sep
    write_file(content, "11-centinelas.csv", corrupt_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Genera 11 ficheros de logs corruptos para tests del parser"
    )
    parser.parse_args()

    # Lee el original
    header_lines, data_lines, line_sep, has_final_sep = read_original()
    corrupt_dir = ensure_corrupt_dir()

    # Crea los 11 ficheros
    create_01_cabecera_truncada(header_lines, line_sep, corrupt_dir)
    create_02_fila_corta(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir)
    create_03_fila_larga(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir)
    create_04_sin_displaymaxmin(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir)
    create_05_bom_utf8(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir)
    create_06_lf_solo(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir)
    create_07_sin_salto_final(header_lines, data_lines, line_sep, corrupt_dir)
    create_08_marcas_no_monotonas(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir)
    create_09_cruce_medianoche(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir)
    create_10_version_desconocida(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir)
    create_11_centinelas(header_lines, data_lines, line_sep, has_final_sep, corrupt_dir)

    print(f"✓ Generados 11 ficheros corruptos en {corrupt_dir}")


if __name__ == "__main__":
    main()
