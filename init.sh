#!/usr/bin/env bash
# VESTA bootstrap: install deps -> create/verify DuckDB schema -> run tests.
# Per AGENTS.md: do NOT write feature code until this exits 0.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "[init.sh] installing pinned dependencies..."
pip install -r requirements.txt --break-system-packages -q

echo "[init.sh] bootstrapping DuckDB schema (staging, core, meta)..."
PYTHONPATH=src python3 -m etl.db

echo "[init.sh] applying schema migrations (safe no-op if already applied)..."
PYTHONPATH=src python3 -m etl.migrations

echo "[init.sh] running test suite..."
PYTHONPATH=src pytest -x

echo "[init.sh] smoke query — schemas present in db/vesta.duckdb:"
python3 -c "
import sys
sys.path.insert(0, 'src')
from etl import db
con = db.connect()
print(db.verify_schemas(con))
"

echo "[init.sh] OK — environment healthy."