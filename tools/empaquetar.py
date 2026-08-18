#!/usr/bin/env python3
"""Construye el ZIP portable `onedir` de `dlv-app` (tarea F5-01).

    python tools/empaquetar.py

Hace, en orden:

1. Comprueba que `dlv-ui/dist/index.html` existe (mismo requisito que ya
   impone `dlv_app.spec`; se repite aquí ANTES de invocar `pyinstaller` para
   no gastar los minutos de un build completo en un fallo que ya se sabía).
2. Ejecuta `pyinstaller dlv_app.spec` desde `dlv-app/` -- necesita
   `pyinstaller` instalado (`uv sync --all-packages` con el grupo `dev`, ya
   lo declara `pyproject.toml`).
3. Comprime `dlv-app/dist/dlv-app/` (la carpeta `onedir`, NUNCA el `.exe`
   suelto) en un ZIP determinista -- ver `_comprimir_onedir` para qué hace
   determinista y qué NO puede controlar desde aquí.
4. Compara el tamaño del ZIP y de la carpeta sin comprimir contra el
   presupuesto de `docs/02-alcance-y-plan.md` §2.6 (< 60 MB en ZIP, < 150 MB
   sin comprimir) e informa, sin inventar un aprobado si no se pudo construir
   nada.

ESTADO EN ESTE ENTORNO (informe de la tarea F5-01)
====================================================
`pyinstaller` no está instalado aquí y no se puede instalar (PyPI da 403), así
que el paso 2 no se ha ejecutado nunca en este entorno: este guion está
escrito y su paso 3 (compresión determinista) se ha probado por separado
contra una carpeta de prueba, pero el guion COMPLETO -- de verdad construyendo
`dlv-app` -- no. Quien lo ejecute con acceso a PyPI vería el paso 2 correr de
verdad; aquí solo se puede leer el código y confiar en que `pyinstaller` hace
lo que documenta.

REPRODUCIBILIDAD (qué SÍ y qué NO controla este guion)
=========================================================
`_comprimir_onedir` fija lo que está en su mano: orden de entradas (`sorted`,
no el orden de `os.walk`, que depende del sistema de ficheros), timestamp de
cada entrada (una constante, no la fecha de compilación de la máquina que
empaqueta) y permisos Unix normalizados (para que un build en Windows y uno en
Linux no difieran solo por bits de permiso que no significan nada en Windows).

Lo que NO puede controlar, y por qué el ZIP resultante puede diferir en bytes
entre dos ejecuciones de `pyinstaller dlv_app.spec` con el mismo código fuente
exacto:

- El bootloader de PyInstaller incrusta un identificador de build propio.
- Los `.pyc` que empaqueta `PYZ` pueden variar si `SOURCE_DATE_EPOCH` no está
  fijado en el entorno (el timestamp de compilación de cada módulo viaja
  dentro del `.pyc`).
- Rutas absolutas de la máquina que empaqueta pueden quedar incrustadas en
  metadatos de depuración de extensiones compiladas de terceros (Polars,
  NumPy) -- esto no lo controla `dlv-app`, lo controla cómo se construyeron
  esos paquetes.

Por eso "reproducible" aquí se limita a: el PASO DE EMPAQUETADO EN ZIP (3) es
determinista dada la misma carpeta `dist/dlv-app/` de entrada. Que la carpeta
de entrada sea bit a bit idéntica entre dos builds de PyInstaller es una
propiedad de PyInstaller/`pyproject.toml` que este guion no puede forzar por
sí solo, y no se ha podido comprobar aquí sin poder ejecutar `pyinstaller`
dos veces.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DLV_APP = RAIZ / "dlv-app"
DIST_UI = RAIZ / "dlv-ui" / "dist"
DIST_APP = DLV_APP / "dist" / "dlv-app"

# Presupuestos de docs/02-alcance-y-plan.md §2.6. NO se cambian para que
# pase una comprobación (regla del proyecto): si el paquete real los supera,
# este guion lo dice con el número, no ajusta el límite.
LIMITE_ZIP_MB = 60
LIMITE_SIN_COMPRIMIR_MB = 150

# Marca de tiempo fija para las entradas del ZIP (2026-01-01 00:00:00, en la
# tupla de 6 campos que exige `ZipInfo.date_time`): cualquier fecha fija vale,
# lo único que importa es que NO sea "ahora" (eso variaría entre builds).
_FECHA_FIJA = (2026, 1, 1, 0, 0, 0)


def _comprobar_dist_ui() -> None:
    if not (DIST_UI / "index.html").is_file():
        sys.exit(
            f"empaquetar.py: no existe {DIST_UI / 'index.html'}. "
            "Ejecuta 'npm ci && npm run build' en dlv-ui/ antes de empaquetar."
        )


def _ejecutar_pyinstaller() -> None:
    if shutil.which("pyinstaller") is None:
        sys.exit(
            "empaquetar.py: 'pyinstaller' no está en el PATH. Declarado en "
            "pyproject.toml ([dependency-groups].dev); instálalo con "
            "'uv sync --all-packages' (necesita acceso a PyPI, bloqueado en "
            "el sandbox donde se escribió este guion -- ver el informe de "
            "la tarea F5-01)."
        )
    subprocess.run(
        ["pyinstaller", "--noconfirm", "dlv_app.spec"],
        cwd=DLV_APP,
        check=True,
    )


def _comprimir_onedir(origen: Path, destino_zip: Path) -> None:
    """Comprime `origen` (la carpeta `onedir`) en `destino_zip` de forma
    determinista: mismo ZIP byte a byte para el mismo contenido de entrada,
    sin importar en qué máquina/momento se ejecute este paso.

    Determinismo de ESTE paso (no del build de PyInstaller que llena
    `origen`, ver el docstring del módulo):
    - `sorted(...)`, no el orden de iteración del sistema de ficheros.
    - Timestamp fijo por entrada (`_FECHA_FIJA`), no el de creación real.
    - `external_attr` normalizado a permisos Unix fijos (0o644 ficheros,
      0o755 directorios/ejecutables), para que el bit ejecutable del binario
      principal sobreviva sin que otros metadatos de permisos introduzcan
      diferencias entre plataformas.
    - Sin comentario de fichero ZIP ni campos "extra" dependientes del SO
      (`zipfile` no los añade por sí solo con esta API; se deja explícito
      aquí para que quede documentado, no porque haga falta código extra).
    """
    rutas = sorted(p for p in origen.rglob("*") if p.is_file())
    destino_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for ruta in rutas:
            info = zipfile.ZipInfo(
                str(Path("dlv-app") / ruta.relative_to(origen)), date_time=_FECHA_FIJA
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            es_ejecutable = ruta.name in {"dlv-app", "dlv-app.exe"}
            permisos = 0o755 if es_ejecutable else 0o644
            # `external_attr` en un ZIP creado en modo Unix codifica, en los
            # 16 bits altos, el modo `st_mode` de toda la vida: `0o100000`
            # es el bit de "fichero regular" (`S_IFREG`), y `permisos` los
            # permisos rwx. Fijarlo a mano (en vez de dejar que
            # `writestr`/`ZipInfo` adivinen algo dependiente del SO desde el
            # que se ejecuta este guion) es lo que hace que el bit ejecutable
            # del binario principal sobreviva igual en Windows/macOS/Linux.
            info.external_attr = (permisos | 0o100000) << 16
            with ruta.open("rb") as fh:
                zf.writestr(info, fh.read())


def _tamano_mb(ruta: Path) -> float:
    if ruta.is_file():
        return ruta.stat().st_size / (1024 * 1024)
    return sum(p.stat().st_size for p in ruta.rglob("*") if p.is_file()) / (1024 * 1024)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--saltar-pyinstaller",
        action="store_true",
        help=(
            "No ejecuta pyinstaller: solo comprime lo que ya haya en "
            "dlv-app/dist/dlv-app/. Para probar el paso de compresión sin "
            "un build completo."
        ),
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=RAIZ / "dist" / "dlv-app-onedir.zip",
        help="Ruta del ZIP de salida (por omisión: dist/dlv-app-onedir.zip)",
    )
    args = parser.parse_args()

    _comprobar_dist_ui()
    if not args.saltar_pyinstaller:
        _ejecutar_pyinstaller()

    if not DIST_APP.is_dir():
        sys.exit(
            f"empaquetar.py: no existe {DIST_APP} -- ¿corrió pyinstaller? "
            "(con --saltar-pyinstaller hace falta haberlo puesto ahí a mano)."
        )

    _comprimir_onedir(DIST_APP, args.salida)

    sin_comprimir_mb = _tamano_mb(DIST_APP)
    zip_mb = _tamano_mb(args.salida)
    print(f"onedir sin comprimir: {sin_comprimir_mb:.1f} MB (límite {LIMITE_SIN_COMPRIMIR_MB} MB)")
    print(f"ZIP:                  {zip_mb:.1f} MB (límite {LIMITE_ZIP_MB} MB)")

    en_rojo = sin_comprimir_mb > LIMITE_SIN_COMPRIMIR_MB or zip_mb > LIMITE_ZIP_MB
    if en_rojo:
        print("PRESUPUESTO SUPERADO (docs/02-alcance-y-plan.md §2.6). No se ajusta el límite.")
    return 1 if en_rojo else 0


if __name__ == "__main__":
    raise SystemExit(main())
