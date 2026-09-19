#!/usr/bin/env bash
# =============================================================================
# VESTA RUN FULL CRAWL - BASH RUNNER
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/Scripts/python.exe" ]; then
    PYTHON_EXE="$SCRIPT_DIR/.venv/Scripts/python.exe"
elif [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_EXE="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON_EXE="python"
fi

echo "======================================================================"
echo "            VESTA AUTONOMOUS TRADING - FULL CRAWL RUNNER              "
echo "======================================================================"

"$PYTHON_EXE" -m src.crawlers.run_full_crawling_pipeline "$@"
