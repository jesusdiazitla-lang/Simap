#!/usr/bin/env bash
# Prepara el entorno de desarrollo de SIMAP en Linux/macOS.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

echo "== [1/4] Python venv"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r backend/requirements-dev.txt --quiet

echo "== [2/4] Frontend npm install"
( cd frontend && npm install )

echo "== [3/4] Git hooks"
git config core.hooksPath .githooks

echo "== [4/4] Grafo inicial"
.venv/bin/python tools/graph/graph.py build

echo; echo "Listo. Activa el venv con: source .venv/bin/activate"
