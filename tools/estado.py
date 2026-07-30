#!/usr/bin/env python3
"""Libro de estado de ejecución del plan de DataLogViewer.

El estado vive en el repositorio (`state/tareas.json`), no en la conversación:
eso es lo que permite reanudar el trabajo en una sesión nueva cuando se agota
el límite de uso.

Uso:
    python tools/estado.py seed            # siembra tareas.json desde el backlog
    python tools/estado.py next            # tareas listas para empezar
    python tools/estado.py start F0-02 --agente sonnet
    python tools/estado.py done  F0-02 --nota "..."
    python tools/estado.py block F0-02 --nota "motivo"
    python tools/estado.py show  F0-02
    python tools/estado.py render          # regenera state/PROGRESO.md
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

if platform.system() == "Windows":
    # La consola de Windows no usa UTF-8 por omisión (cp1252), y este guion
    # imprime ≥/✔/✖ en la salida de `next`/`show`.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
BACKLOG = RAIZ / "docs" / "05-backlog-y-asignacion-modelos.md"
ESTADO = RAIZ / "state" / "tareas.json"
PROGRESO = RAIZ / "state" / "PROGRESO.md"

# Un estado G1 no lo cierra un modelo: queda esperando revisión del propietario.
ESTADOS = ("pendiente", "en_curso", "revision_humana", "hecho", "bloqueado")
CERRADOS = ("hecho", "revision_humana")

FILA = re.compile(
    r"^\|\s*((?:F\d|FG)-\d\d)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|"
    r"\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$",
    re.M,
)

# Correcciones de dependencia detectadas al arrancar la ejecución: el backlog
# declaraba F0-01 sin dependencias, pero su *spike* necesita el log sintético
# de 1 h que produce F0-05, y F0-02 no necesita los ADR firmados porque el stack
# ya está decidido en la revisión 2 de docs/03.
DEPS_CORREGIDAS = {
    "F0-01": ["F0-05"],
    "F0-02": [],
    # F0-08 dependía de F0-01 solo porque F0-01 incluía «cerrar los ADR». Los ADR
    # ya están cerrados en docs/03 rev. 2, y el catálogo de unidades está
    # especificado por completo en docs/06 §6.7: no necesita el spike de Polars.
    "F0-08": [],
}


def ahora() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def limpiar(txt: str) -> str:
    return txt.replace("**", "").replace("*", "").strip()


def sha_actual() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def cargar() -> dict:
    if not ESTADO.exists():
        sys.exit(f"No existe {ESTADO}. Ejecuta primero: python tools/estado.py seed")
    return json.loads(ESTADO.read_text(encoding="utf-8"))


def guardar(datos: dict) -> None:
    datos["meta"]["actualizado"] = ahora()
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def buscar(datos: dict, tid: str) -> dict:
    for t in datos["tareas"]:
        if t["id"] == tid:
            return t
    sys.exit(f"Tarea desconocida: {tid}")


# --------------------------------------------------------------------------- #
# seed
# --------------------------------------------------------------------------- #
def cmd_seed(args: argparse.Namespace) -> None:
    texto = BACKLOG.read_text(encoding="utf-8")
    tareas = []
    for tid, titulo, entregable, modelo, pts, deps, gate in FILA.findall(texto):
        brutas = [d.strip() for d in limpiar(deps).split(",") if d.strip()]
        dependencias = [d for d in brutas if re.fullmatch(r"(?:F\d|FG)-\d\d", d)]
        # "todo" en el backlog significa «al final, cuando el resto esté cerrado».
        dep_todo = any(b.lower() == "todo" for b in brutas)
        tareas.append(
            {
                "id": tid,
                "fase": tid.split("-")[0],
                "titulo": limpiar(titulo),
                "entregable": limpiar(entregable),
                "modelo": limpiar(modelo),
                "pts": int(pts),
                "deps": DEPS_CORREGIDAS.get(tid, dependencias),
                "deps_backlog": dependencias,
                "dep_todo": dep_todo,
                "gate": limpiar(gate),
                "estado": "pendiente",
                "agente": None,
                "commits": [],
                "notas": [],
            }
        )

    if ESTADO.exists() and not args.forzar:
        previo = {t["id"]: t for t in cargar()["tareas"]}
        conservados = 0
        for t in tareas:
            viejo = previo.get(t["id"])
            if viejo and viejo["estado"] != "pendiente":
                t.update(
                    estado=viejo["estado"],
                    agente=viejo["agente"],
                    commits=viejo["commits"],
                    notas=viejo["notas"],
                )
                conservados += 1
        print(f"Resiembra: {conservados} tareas con progreso conservadas.")

    guardar({"meta": {"version": 1, "plan_rev": 2, "actualizado": ahora()}, "tareas": tareas})
    print(
        f"{len(tareas)} tareas · {sum(t['pts'] for t in tareas)} pts → {ESTADO.relative_to(RAIZ)}"
    )
    cmd_render(args)


# --------------------------------------------------------------------------- #
# next
# --------------------------------------------------------------------------- #
def cmd_next(args: argparse.Namespace) -> None:
    datos = cargar()
    por_id = {t["id"]: t for t in datos["tareas"]}

    en_curso = [t for t in datos["tareas"] if t["estado"] == "en_curso"]
    if en_curso:
        print("EN CURSO (retomar o cerrar antes de empezar otra cosa):")
        for t in en_curso:
            print(f"  {t['id']}  [{t['modelo']}]  {t['titulo'][:70]}")
        print()

    bloqueadas = [t for t in datos["tareas"] if t["estado"] == "bloqueado"]
    if bloqueadas:
        print("BLOQUEADAS:")
        for t in bloqueadas:
            ultima = t["notas"][-1]["texto"] if t["notas"] else "sin nota"
            print(f"  {t['id']}  {ultima[:70]}")
        print()

    listas = []
    resto_abierto = any(
        t["estado"] not in CERRADOS and not t.get("dep_todo") for t in datos["tareas"]
    )
    for t in datos["tareas"]:
        if t["estado"] != "pendiente":
            continue
        if t.get("dep_todo") and resto_abierto:
            continue  # tarea de cierre: espera a que el resto esté cerrado
        faltan = [d for d in t["deps"] if por_id.get(d, {}).get("estado") not in CERRADOS]
        if faltan:
            continue
        aviso = [d for d in t["deps"] if por_id.get(d, {}).get("estado") == "revision_humana"]
        listas.append((t, aviso))

    if not listas:
        print("Nada listo para empezar.")
        return

    orden = {"F0": 0, "F1": 1, "FG": 2, "F2": 3, "F3": 4, "F4": 5, "F5": 6}
    listas.sort(key=lambda x: (orden.get(x[0]["fase"], 9), x[0]["id"]))

    print("LISTAS PARA EMPEZAR:")
    for t, aviso in listas[: args.limite]:
        marca = " ".join(f"[{g}]" for g in [t["gate"]] if g)
        print(f"  {t['id']}  [{t['modelo']:9s}] {marca:5s} {t['pts']:2d}pts  {t['titulo'][:64]}")
        if aviso:
            print(f"        ⚠ depende de {', '.join(aviso)} que espera revisión humana")


# --------------------------------------------------------------------------- #
# transiciones
# --------------------------------------------------------------------------- #
def _nota(t: dict, texto: str | None) -> None:
    if texto:
        t["notas"].append({"fecha": ahora(), "texto": texto})


def cmd_start(args: argparse.Namespace) -> None:
    datos = cargar()
    t = buscar(datos, args.id)
    por_id = {x["id"]: x for x in datos["tareas"]}
    faltan = [d for d in t["deps"] if por_id.get(d, {}).get("estado") not in CERRADOS]
    if t.get("dep_todo") and any(
        x["estado"] not in CERRADOS and not x.get("dep_todo") for x in datos["tareas"]
    ):
        faltan.append("(resto del plan)")
    if faltan and not args.forzar:
        sys.exit(f"{t['id']} tiene dependencias sin cerrar: {', '.join(faltan)} (usa --forzar)")
    t["estado"] = "en_curso"
    t["agente"] = args.agente
    _nota(t, args.nota)
    guardar(datos)
    print(f"{t['id']} → en_curso (agente: {args.agente or 'orquestador'})")
    cmd_render(args)


def cmd_done(args: argparse.Namespace) -> None:
    datos = cargar()
    t = buscar(datos, args.id)
    # Una puerta G1 no la cierra un modelo: queda esperando al propietario.
    t["estado"] = "revision_humana" if t["gate"] == "G1" else "hecho"
    sha = args.commit or sha_actual()
    if sha and sha not in t["commits"]:
        t["commits"].append(sha)
    _nota(t, args.nota)
    guardar(datos)
    print(f"{t['id']} → {t['estado']}" + (f" (commit {sha})" if sha else ""))
    if t["estado"] == "revision_humana":
        print("  ⚠ puerta G1: requiere que una persona lea el diff antes de considerarse hecha.")
    cmd_render(args)


def cmd_aprobar(args: argparse.Namespace) -> None:
    """El propietario cierra una puerta G1."""
    datos = cargar()
    t = buscar(datos, args.id)
    if t["estado"] != "revision_humana":
        sys.exit(f"{t['id']} no está en revision_humana (está en {t['estado']})")
    t["estado"] = "hecho"
    _nota(t, args.nota or "revisión humana aprobada")
    guardar(datos)
    print(f"{t['id']} → hecho (G1 aprobada)")
    cmd_render(args)


def cmd_block(args: argparse.Namespace) -> None:
    datos = cargar()
    t = buscar(datos, args.id)
    t["estado"] = "bloqueado"
    _nota(t, args.nota or "bloqueada sin motivo indicado")
    guardar(datos)
    print(f"{t['id']} → bloqueado")
    cmd_render(args)


def cmd_show(args: argparse.Namespace) -> None:
    t = buscar(cargar(), args.id)
    print(json.dumps(t, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
SIMBOLO = {
    "pendiente": "· ",
    "en_curso": "▶ ",
    "revision_humana": "⏳",
    "hecho": "✔ ",
    "bloqueado": "✖ ",
}


def cmd_render(_args: argparse.Namespace) -> None:
    datos = cargar()
    tareas = datos["tareas"]
    orden = ["F0", "F1", "FG", "F2", "F3", "F4", "F5"]
    total = sum(t["pts"] for t in tareas)
    hechos = sum(t["pts"] for t in tareas if t["estado"] == "hecho")
    revision = sum(t["pts"] for t in tareas if t["estado"] == "revision_humana")

    L: list[str] = []
    L.append("# Progreso de ejecución")
    L.append("")
    L.append("> Generado por `tools/estado.py render`. **No editar a mano**: la fuente")
    L.append("> es `state/tareas.json`. Protocolo de reanudación en")
    L.append("> [`docs/08-ejecucion-y-reanudacion.md`](../docs/08-ejecucion-y-reanudacion.md).")
    L.append("")
    L.append(f"Actualizado: {datos['meta']['actualizado']}")
    L.append("")
    pct = 100 * hechos / total if total else 0
    pct_r = 100 * (hechos + revision) / total if total else 0
    L.append(
        f"**{hechos} / {total} pts cerrados ({pct:.1f} %)** · "
        f"{revision} pts esperando revisión humana → {pct_r:.1f} % entregado"
    )
    L.append("")

    L.append("| Fase | Hecho | En revisión | En curso | Pendiente | Bloqueado | Total |")
    L.append("|---|---|---|---|---|---|---|")
    for fase in orden:
        f = [t for t in tareas if t["fase"] == fase]
        if not f:
            continue

        def s(e: str, f: list[dict] = f) -> int:  # `f` ligada: no se captura del bucle
            return sum(t["pts"] for t in f if t["estado"] == e)

        L.append(
            f"| {fase} | {s('hecho')} | {s('revision_humana')} | {s('en_curso')} "
            f"| {s('pendiente')} | {s('bloqueado')} | {sum(t['pts'] for t in f)} |"
        )
    L.append("")

    activas = [t for t in tareas if t["estado"] in ("en_curso", "bloqueado", "revision_humana")]
    if activas:
        L.append("## Requieren atención")
        L.append("")
        L.append("| Tarea | Estado | Modelo | Puerta | Última nota |")
        L.append("|---|---|---|---|---|")
        for t in activas:
            nota = t["notas"][-1]["texto"] if t["notas"] else "—"
            L.append(
                f"| `{t['id']}` {t['titulo'][:44]} | {t['estado']} | {t['modelo']} "
                f"| {t['gate']} | {nota[:70]} |"
            )
        L.append("")

    for fase in orden:
        f = [t for t in tareas if t["fase"] == fase]
        if not f:
            continue
        cerr = sum(t["pts"] for t in f if t["estado"] in CERRADOS)
        tot = sum(t["pts"] for t in f)
        L.append(f"## {fase} — {cerr}/{tot} pts")
        L.append("")
        L.append("| | ID | Tarea | Modelo | Pts | Deps | Puerta | Commits |")
        L.append("|---|---|---|---|---|---|---|---|")
        for t in f:
            L.append(
                f"| {SIMBOLO[t['estado']]} | `{t['id']}` | {t['titulo'][:62]} "
                f"| {t['modelo']} | {t['pts']} | {', '.join(t['deps']) or ('todo' if t.get('dep_todo') else '—')} "
                f"| {t['gate']} | {', '.join(f'`{c}`' for c in t['commits']) or '—'} |"
            )
        L.append("")

    L.append(
        "Leyenda: ✔ hecho · ⏳ esperando revisión humana (G1) · ▶ en curso · "
        "· pendiente · ✖ bloqueado"
    )
    L.append("")
    PROGRESO.parent.mkdir(parents=True, exist_ok=True)
    PROGRESO.write_text("\n".join(L), encoding="utf-8")
    print(f"→ {PROGRESO.relative_to(RAIZ)}")


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seed", help="siembra o resiembra tareas.json desde el backlog")
    s.add_argument("--forzar", action="store_true", help="descarta el progreso existente")
    s.set_defaults(func=cmd_seed)

    s = sub.add_parser("next", help="tareas listas para empezar")
    s.add_argument("--limite", type=int, default=12)
    s.set_defaults(func=cmd_next)

    s = sub.add_parser("start", help="marca una tarea en curso")
    s.add_argument("id")
    s.add_argument("--agente", default=None, help="opus | sonnet | haiku | orquestador")
    s.add_argument("--nota", default=None)
    s.add_argument("--forzar", action="store_true")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("done", help="cierra una tarea (G1 pasa a revision_humana)")
    s.add_argument("id")
    s.add_argument("--commit", default=None)
    s.add_argument("--nota", default=None)
    s.set_defaults(func=cmd_done)

    s = sub.add_parser("aprobar", help="el propietario cierra una puerta G1")
    s.add_argument("id")
    s.add_argument("--nota", default=None)
    s.set_defaults(func=cmd_aprobar)

    s = sub.add_parser("block", help="marca una tarea bloqueada")
    s.add_argument("id")
    s.add_argument("--nota", default=None)
    s.set_defaults(func=cmd_block)

    s = sub.add_parser("show", help="muestra una tarea en JSON")
    s.add_argument("id")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("render", help="regenera state/PROGRESO.md")
    s.set_defaults(func=cmd_render)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
