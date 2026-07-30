#!/usr/bin/env bash
# Verificación completa del repositorio (docs/08-ejecucion-y-reanudacion.md §8.10).
#
# Existe porque leer la salida de las herramientas «a ojo» ya ha dejado pasar dos
# commits con el lint en rojo: `ruff check` imprime «No fixes available…» DESPUÉS
# de «Found N errors», así que mirar la última línea engaña. Este guion usa
# códigos de salida, que no se pueden malinterpretar, y resume al final.
#
# Uso:  bash tools/verificar.sh
# Salida: 0 si todo está en verde, 1 si algo falla.

set -uo pipefail
cd "$(dirname "$0")/.."

fallos=0
resumen=()

ejecutar() {
    local etiqueta="$1"; shift
    printf '\n\033[1m=== %s ===\033[0m\n' "$etiqueta"
    if "$@"; then
        resumen+=("  OK   $etiqueta")
    else
        resumen+=("  FALLA $etiqueta")
        fallos=$((fallos + 1))
    fi
}

ejecutar "ruff check"          ruff check .
ejecutar "ruff format --check" ruff format --check .
ejecutar "mypy --strict"       mypy dlv-core dlv-api
ejecutar "pytest"              pytest -q
ejecutar "ADR-009"             python3 tools/banco.py adr009
ejecutar "presupuestos"        python3 tools/banco.py comprobar

printf '\n\033[1m=== RESUMEN ===\033[0m\n'
printf '%s\n' "${resumen[@]}"

if [ "$fallos" -eq 0 ]; then
    printf '\n\033[32mTodo en verde.\033[0m\n'
else
    printf '\n\033[31m%d comprobacion(es) en rojo. NO commitear.\033[0m\n' "$fallos"
fi
exit "$fallos"
