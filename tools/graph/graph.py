#!/usr/bin/env python
"""
graph.py - Grafo unificado de dependencias y estado del proyecto SIMAP.

Combina:
  * grimp               -> imports del backend Python (paquete `app`)
  * dependency-cruiser  -> imports del frontend Next.js/TS (carpeta `src`)

y produce un único snapshot en `.graph/graph.json` que después se puede consultar
sin volver a analizar el código.

Uso (desde la raíz del repo, con el venv activo):

  python tools/graph/graph.py build              # regenera .graph/graph.json + diagramas Mermaid
  python tools/graph/graph.py deps  <modulo>     # qué importa <modulo> (directo + transitivo)
  python tools/graph/graph.py rdeps <modulo>     # quién depende de <modulo> (análisis de impacto)
  python tools/graph/graph.py cycles             # ciclos de importación
  python tools/graph/graph.py orphans            # módulos que nadie importa
  python tools/graph/graph.py status             # avance del proyecto (plan + métricas del código)
  python tools/graph/graph.py check              # valida reglas de arquitectura (usado por hooks/CI)
  python tools/graph/graph.py docs               # refresca las secciones auto-generadas del README.md
  python tools/graph/graph.py view               # abre un visor interactivo del grafo en el navegador

<modulo> acepta identificadores completos ("app.services.foo", "src/lib/api.ts")
o un fragmento único ("services.foo", "lib/api").
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
GRAPH_DIR = ROOT / ".graph"
GRAPH_FILE = GRAPH_DIR / "graph.json"
DIAGRAMS_DIR = ROOT / "docs" / "diagramas"
PLAN_FILE = ROOT / "docs" / "PLAN.yaml"

TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
STUB_RE = re.compile(r"^\s*(pass|\.\.\.|raise NotImplementedError)\s*$", re.M)
IS_WIN = sys.platform.startswith("win")


# --------------------------------------------------------------------------- #
# Modelo
# --------------------------------------------------------------------------- #
@dataclass
class Node:
    id: str                     # "app.services.x"  |  "src/lib/x.ts"
    lang: str                   # "python" | "ts"
    path: str                   # ruta relativa al repo, con /
    layer: str                  # api, services, db, models, schemas, core, app, components, lib, ...
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)
    loc: int = 0
    todos: int = 0
    is_stub: bool = False
    has_test: bool = False


# --------------------------------------------------------------------------- #
# Recolección
# --------------------------------------------------------------------------- #
def _file_metrics(path: Path) -> tuple[int, int, bool]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, 0, False
    lines = [ln for ln in text.splitlines() if ln.strip()]
    loc = len(lines)
    todos = len(TODO_RE.findall(text))
    code = [ln for ln in lines if not ln.lstrip().startswith(("#", "//", '"""', "'''", "*", "/*"))]
    is_stub = loc > 0 and (len(code) <= 2 or bool(STUB_RE.search(text)) and len(code) <= 6)
    return loc, todos, is_stub


def collect_python() -> dict[str, Node]:
    sys.path.insert(0, str(BACKEND))
    import grimp  # noqa: WPS433 (import local a propósito: solo se usa aquí)

    graph = grimp.build_graph("app", cache_dir=None)
    tests_dir = BACKEND / "tests"
    test_names = {p.stem.removeprefix("test_") for p in tests_dir.glob("test_*.py")} if tests_dir.exists() else set()

    nodes: dict[str, Node] = {}
    for mod in sorted(graph.modules):
        rel = mod.replace(".", "/")
        candidate = BACKEND / f"{rel}.py"
        if not candidate.exists():
            candidate = BACKEND / rel / "__init__.py"
        loc, todos, stub = _file_metrics(candidate)
        parts = mod.split(".")
        layer = parts[1] if len(parts) > 1 else "app"
        nodes[mod] = Node(
            id=mod,
            lang="python",
            path=candidate.relative_to(ROOT).as_posix(),
            layer=layer,
            imports=sorted(graph.find_modules_directly_imported_by(mod)),
            loc=loc,
            todos=todos,
            is_stub=stub,
            has_test=parts[-1] in test_names,
        )
    return nodes


def collect_ts() -> dict[str, Node]:
    if not (FRONTEND / "node_modules" / ".bin").exists():
        print("  ! frontend/node_modules no existe; omitiendo frontend (ejecuta `npm install`)", file=sys.stderr)
        return {}
    cmd = ["npx", "depcruise", "--config", ".dependency-cruiser.cjs", "--output-type", "json", "src"]
    res = subprocess.run(cmd, cwd=FRONTEND, capture_output=True, text=True, shell=IS_WIN)
    if res.returncode not in (0, 1):  # 1 = hubo violaciones, pero el JSON sigue siendo válido
        raise SystemExit(f"depcruise falló ({res.returncode}):\n{res.stderr}")
    data = json.loads(res.stdout)

    test_stems = {
        p.name.split(".")[0]
        for p in FRONTEND.glob("src/**/*")
        if p.is_file() and re.search(r"\.(test|spec)\.[jt]sx?$", p.name)
    }

    nodes: dict[str, Node] = {}
    for m in data["modules"]:
        src = m["source"]
        if "node_modules" in src or not src.startswith("src/"):
            continue
        p = FRONTEND / src
        loc, todos, stub = _file_metrics(p)
        parts = src.split("/")
        layer = parts[1] if len(parts) > 2 else "src"
        imports = sorted(
            d["resolved"]
            for d in m["dependencies"]
            if d["resolved"].startswith("src/") and not d.get("couldNotResolve")
        )
        nodes[src] = Node(
            id=src,
            lang="ts",
            path=f"frontend/{src}",
            layer=layer,
            imports=imports,
            loc=loc,
            todos=todos,
            is_stub=stub,
            has_test=p.name.split(".")[0] in test_stems and not re.search(r"\.(test|spec)\.", p.name),
        )
    return nodes


def build() -> dict:
    print("> Analizando backend (grimp)...")
    nodes = collect_python()
    print(f"  {len(nodes)} módulos Python")
    print("> Analizando frontend (dependency-cruiser)...")
    ts = collect_ts()
    print(f"  {len(ts)} módulos TS/TSX")
    nodes.update(ts)

    for n in nodes.values():
        for dep in n.imports:
            if dep in nodes:
                nodes[dep].imported_by.append(n.id)
    for n in nodes.values():
        n.imported_by.sort()

    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "nodes": {k: asdict(v) for k, v in sorted(nodes.items())},
    }
    GRAPH_DIR.mkdir(exist_ok=True)
    GRAPH_FILE.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"> Snapshot escrito en {GRAPH_FILE.relative_to(ROOT)}")

    write_mermaid(nodes)
    return snapshot


# --------------------------------------------------------------------------- #
# Diagramas Mermaid (no requieren graphviz; se renderizan en GitHub)
# --------------------------------------------------------------------------- #
def _mermaid_id(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def write_mermaid(nodes: dict[str, Node]) -> None:
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    for lang, fname, title in (
        ("python", "dependencias-backend.md", "Backend (FastAPI)"),
        ("ts", "dependencias-frontend.md", "Frontend (Next.js)"),
    ):
        subset = {k: v for k, v in nodes.items() if v.lang == lang}
        lines = [
            f"# Grafo de dependencias - {title}",
            "",
            "> Generado automáticamente por `python tools/graph/graph.py build`. No editar a mano.",
            "",
            "```mermaid",
            "graph LR",
        ]
        by_layer: dict[str, list[Node]] = defaultdict(list)
        for n in subset.values():
            by_layer[n.layer].append(n)
        for layer, ns in sorted(by_layer.items()):
            lines.append(f"  subgraph {_mermaid_id(layer)}[{layer}]")
            for n in ns:
                label = n.id.replace("app.", "", 1) if lang == "python" else n.id.replace("src/", "", 1)
                lines.append(f'    {_mermaid_id(n.id)}["{label}"]')
            lines.append("  end")
        for n in subset.values():
            for dep in n.imports:
                if dep in subset:
                    lines.append(f"  {_mermaid_id(n.id)} --> {_mermaid_id(dep)}")
        lines += ["```", ""]
        (DIAGRAMS_DIR / fname).write_text("\n".join(lines), encoding="utf-8")
        print(f"> Diagrama escrito en docs/diagramas/{fname}")


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #
def load() -> dict[str, Node]:
    if not GRAPH_FILE.exists():
        print("No existe .graph/graph.json; ejecuta `build` primero.", file=sys.stderr)
        raise SystemExit(2)
    raw = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
    return {k: Node(**v) for k, v in raw["nodes"].items()}


def resolve(nodes: dict[str, Node], query: str) -> str:
    if query in nodes:
        return query
    q = query.replace("\\", "/")
    matches = [k for k in nodes if q in k or q.replace("/", ".") in k]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SystemExit(f"Ningún módulo coincide con '{query}'.")
    raise SystemExit("Ambiguo, coincide con:\n  " + "\n  ".join(matches))


def _walk(nodes: dict[str, Node], start: str, attr: str) -> dict[str, int]:
    """BFS devolviendo {modulo: distancia}."""
    seen = {start: 0}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for nxt in getattr(nodes[cur], attr):
            if nxt in nodes and nxt not in seen:
                seen[nxt] = seen[cur] + 1
                queue.append(nxt)
    seen.pop(start)
    return seen


def cmd_deps(nodes: dict[str, Node], query: str, reverse: bool) -> None:
    mod = resolve(nodes, query)
    attr = "imported_by" if reverse else "imports"
    direct = getattr(nodes[mod], attr)
    trans = _walk(nodes, mod, attr)
    head = "es importado por" if reverse else "importa"
    print(f"{mod}  ({nodes[mod].path})")
    print(f"  {head} directamente ({len(direct)}):")
    for d in direct:
        print(f"    - {d}")
    indirect = sorted((k for k, dist in trans.items() if dist > 1), key=lambda k: (trans[k], k))
    if indirect:
        print(f"  {head} transitivamente ({len(indirect)}):")
        for d in indirect:
            print(f"    - {d}  (dist {trans[d]})")
    if reverse:
        print(f"\n  => Cambiar {mod} puede afectar a {len(trans)} módulo(s).")


def find_cycles(nodes: dict[str, Node]) -> list[list[str]]:
    """Tarjan SCC; devuelve solo componentes con más de un nodo o auto-bucles."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    out: list[list[str]] = []
    counter = [0]

    def strong(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in nodes[v].imports:
            if w not in nodes:
                continue
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in nodes[v].imports:
                out.append(sorted(comp))

    sys.setrecursionlimit(max(10000, len(nodes) * 4))
    for v in nodes:
        if v not in index:
            strong(v)
    return out


def cmd_cycles(nodes: dict[str, Node]) -> int:
    cycles = find_cycles(nodes)
    if not cycles:
        print("Sin ciclos de importación.")
        return 0
    print(f"{len(cycles)} ciclo(s):")
    for c in cycles:
        print("  " + " -> ".join(c) + f" -> {c[0]}")
    return 1


def cmd_orphans(nodes: dict[str, Node]) -> None:
    entry_points = {"app.main"}
    next_conventions = re.compile(r"^src/app/.*(page|layout|loading|error|not-found|template|route)\.tsx?$")
    orphans = [
        n for n in nodes.values()
        if not n.imported_by
        and n.id not in entry_points
        and not next_conventions.match(n.id)
        and not n.path.endswith("__init__.py")
    ]
    if not orphans:
        print("Sin módulos huérfanos.")
        return
    print(f"{len(orphans)} módulo(s) que nadie importa (¿código muerto o punto de entrada?):")
    for n in orphans:
        print(f"  - {n.id}")


# --------------------------------------------------------------------------- #
# Estado / avance
# --------------------------------------------------------------------------- #
def _load_plan() -> dict | None:
    if not PLAN_FILE.exists():
        return None
    try:
        import yaml
    except ImportError:
        print("  ! PyYAML no instalado; no se puede leer docs/PLAN.yaml", file=sys.stderr)
        return None
    return yaml.safe_load(PLAN_FILE.read_text(encoding="utf-8")) or {}


def cmd_status(nodes: dict[str, Node]) -> None:
    py = [n for n in nodes.values() if n.lang == "python"]
    ts = [n for n in nodes.values() if n.lang == "ts"]

    def block(title: str, ns: list[Node]) -> None:
        real = [n for n in ns if not n.path.endswith("__init__.py")]
        loc = sum(n.loc for n in ns)
        stubs = [n for n in real if n.is_stub]
        todos = sum(n.todos for n in ns)
        tested = [n for n in real if n.has_test]
        print(f"\n[{title}]  módulos: {len(real)}   LOC: {loc}   TODO/FIXME: {todos}")
        print(f"  con test: {len(tested)}/{len(real)}   stubs/vacíos: {len(stubs)}")
        for n in stubs:
            print(f"    - stub: {n.id}")
        by_layer: dict[str, int] = defaultdict(int)
        for n in real:
            by_layer[n.layer] += 1
        print("  por capa: " + ", ".join(f"{k}={v}" for k, v in sorted(by_layer.items())))

    print("=== ESTADO DEL CÓDIGO ===")
    block("backend", py)
    block("frontend", ts)
    cycles = find_cycles(nodes)
    print(f"\nciclos de importación: {len(cycles)}")

    plan = _load_plan()
    if plan is None:
        print("\n(No hay docs/PLAN.yaml; crea uno para seguir hitos.)")
        return

    print("\n=== PLAN (docs/PLAN.yaml) ===")
    total = done = 0
    for ms in plan.get("milestones", []):
        tasks = ms.get("tasks", [])
        ms_done = 0
        lines = []
        for t in tasks:
            status = t.get("status", "pending")
            # Si la tarea declara módulos, se considera automáticamente hecha cuando
            # todos existen en el grafo y ninguno es un stub.
            mods = t.get("modules", [])
            if mods and status != "done":
                present = [m for m in mods if m in nodes and not nodes[m].is_stub]
                if len(present) == len(mods):
                    status = "done (auto)"
                elif present:
                    status = f"in_progress ({len(present)}/{len(mods)} módulos)"
            mark = {"done": "x", "done (auto)": "x"}.get(status, "-" if status.startswith("in_progress") else " ")
            if mark == "x":
                ms_done += 1
            lines.append(f"    [{mark}] {t['name']}  <{status}>")
        total += len(tasks)
        done += ms_done
        pct = int(100 * ms_done / len(tasks)) if tasks else 0
        print(f"\n  {ms['name']}  ({ms_done}/{len(tasks)}, {pct}%)")
        if ms.get("rf"):
            print(f"    cubre: {', '.join(ms['rf'])}")
        if ms.get("done_when"):
            print(f"    hecho cuando: {ms['done_when']}")
        print("\n".join(lines))
    if total:
        print(f"\nAVANCE GLOBAL: {done}/{total} tareas ({int(100 * done / total)}%)")


# --------------------------------------------------------------------------- #
# Validación (hooks / CI)
# --------------------------------------------------------------------------- #
def cmd_check() -> int:
    rc = 0
    # PYTHONUTF8=1: evita errores 'charmap' al leer archivos con acentos en Windows.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    print("> import-linter (backend)...")
    lint_imports = Path(sys.executable).with_name("lint-imports" + (".exe" if IS_WIN else ""))
    r = subprocess.run(
        [str(lint_imports)],
        cwd=BACKEND, text=True, capture_output=True, env=env, encoding="utf-8",
    )
    print((r.stdout + r.stderr).strip())
    rc |= r.returncode

    if (FRONTEND / "node_modules" / ".bin").exists():
        print("> dependency-cruiser (frontend)...")
        r = subprocess.run(
            ["npx", "depcruise", "--config", ".dependency-cruiser.cjs", "src"],
            cwd=FRONTEND, text=True, capture_output=True, shell=IS_WIN, env=env, encoding="utf-8",
        )
        print((r.stdout + r.stderr).strip())
        rc |= r.returncode

    print("> ciclos (grafo unificado)...")
    nodes = load()
    rc |= cmd_cycles(nodes)
    return rc


# --------------------------------------------------------------------------- #
# Documentación auto-generada (README.md entre marcadores)
# --------------------------------------------------------------------------- #
README_FILE = ROOT / "README.md"
MARK_START = "<!-- graph:auto:start -->"
MARK_END = "<!-- graph:auto:end -->"


def _module_table(nodes: dict[str, Node], lang: str) -> list[str]:
    rows = [n for n in nodes.values() if n.lang == lang and not n.path.endswith("__init__.py")]
    if not rows:
        return ["_(sin módulos todavía)_"]
    out = ["| Módulo | Capa | Importa | Importado por | LOC | Test |", "|---|---|---:|---:|---:|:---:|"]
    for n in sorted(rows, key=lambda x: (x.layer, x.id)):
        out.append(
            f"| `{n.id}` | {n.layer} | {len(n.imports)} | {len(n.imported_by)} | {n.loc} "
            f"| {'✅' if n.has_test else '—'} |"
        )
    return out


def render_auto_docs(nodes: dict[str, Node]) -> str:
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_status(nodes)
    status_txt = buf.getvalue().strip()

    lines = [
        MARK_START,
        "_Sección generada por `python tools/graph/graph.py docs`. "
        "No editar a mano; se sobrescribe en cada push a `main`._",
        "",
        f"Última actualización: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "### Estado del proyecto",
        "",
        "```text",
        status_txt,
        "```",
        "",
        "### Módulos del backend",
        "",
        *_module_table(nodes, "python"),
        "",
        "### Módulos del frontend",
        "",
        *_module_table(nodes, "ts"),
        "",
        "Diagramas: [backend](docs/diagramas/dependencias-backend.md) "
        "· [frontend](docs/diagramas/dependencias-frontend.md)",
        MARK_END,
    ]
    return "\n".join(lines)


def cmd_docs(nodes: dict[str, Node]) -> int:
    """Devuelve 1 si README.md cambió (útil para que el hook pida commit)."""
    if not README_FILE.exists():
        print("README.md no existe; nada que actualizar.", file=sys.stderr)
        return 0
    text = README_FILE.read_text(encoding="utf-8")
    if MARK_START not in text or MARK_END not in text:
        print(f"README.md no contiene los marcadores {MARK_START} / {MARK_END}.", file=sys.stderr)
        return 0
    pre, rest = text.split(MARK_START, 1)
    _, post = rest.split(MARK_END, 1)
    new_text = pre + render_auto_docs(nodes) + post
    # Ignorar cambios que solo afecten a la marca de tiempo.
    strip_ts = lambda s: re.sub(r"Última actualización: .*", "", s)  # noqa: E731
    if strip_ts(new_text) == strip_ts(text):
        print("README.md ya está actualizado.")
        return 0
    README_FILE.write_text(new_text, encoding="utf-8")
    print("README.md actualizado (sección auto-generada).")
    return 1


# --------------------------------------------------------------------------- #
# Visor interactivo (HTML autocontenido con vis-network)
# --------------------------------------------------------------------------- #
VIEWER_TEMPLATE = Path(__file__).with_name("viewer.html")
VIEWER_OUT = GRAPH_DIR / "graph.html"


def cmd_view(open_browser: bool = True) -> None:
    """Inyecta .graph/graph.json en la plantilla y abre el resultado en el navegador."""
    if not GRAPH_FILE.exists():
        build()
    template = VIEWER_TEMPLATE.read_text(encoding="utf-8")
    data = GRAPH_FILE.read_text(encoding="utf-8")
    html = template.replace("/*__GRAPH_JSON__*/{}", data, 1)
    VIEWER_OUT.write_text(html, encoding="utf-8")
    print(f"> Visor escrito en {VIEWER_OUT.relative_to(ROOT)}")
    if open_browser:
        import webbrowser

        webbrowser.open(VIEWER_OUT.resolve().as_uri())


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("deps").add_argument("module")
    sub.add_parser("rdeps").add_argument("module")
    sub.add_parser("cycles")
    sub.add_parser("orphans")
    sub.add_parser("status")
    sub.add_parser("check")
    sub.add_parser("docs")
    sub.add_parser("view").add_argument("--no-open", action="store_true", help="solo generar el HTML")
    a = ap.parse_args(argv)

    if a.cmd == "build":
        build()
        return 0
    if a.cmd == "check":
        if not GRAPH_FILE.exists():
            build()
        return cmd_check()
    if a.cmd == "view":
        cmd_view(open_browser=not a.no_open)
        return 0

    nodes = load()
    if a.cmd == "deps":
        cmd_deps(nodes, a.module, reverse=False)
    elif a.cmd == "rdeps":
        cmd_deps(nodes, a.module, reverse=True)
    elif a.cmd == "cycles":
        return cmd_cycles(nodes)
    elif a.cmd == "orphans":
        cmd_orphans(nodes)
    elif a.cmd == "status":
        cmd_status(nodes)
    elif a.cmd == "docs":
        return cmd_docs(nodes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
