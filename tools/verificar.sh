#!/usr/bin/env bash
# Verificación completa del repositorio (docs/08 §8.10).
#
# Envoltorio de `tools/verificar.py`, que es donde está la implementación. Se
# mantiene esta entrada porque `bash tools/verificar.sh` es lo que dice el
# protocolo y lo que hay escrito en los informes de tarea ya cerrados.
#
# En Windows sin Git Bash, usa directamente:  python tools/verificar.py
#
# Uso:  bash tools/verificar.sh
# Salida: 0 si todo está en verde, 1 si algo falla.

set -uo pipefail
cd "$(dirname "$0")/.."

if command -v python3 >/dev/null 2>&1; then
    exec python3 tools/verificar.py "$@"
fi
exec python tools/verificar.py "$@"
