#!/usr/bin/env bash
# Book Manuscript Agent - start the local console (macOS / Linux)
set -u
cd "$(dirname "$0")"

if [ ! -x ".venv-app/bin/python" ]; then
  echo "[ERROR] Not set up yet. Run ./setup.sh first."
  exit 1
fi

PORT="${BOOK2JSON_PORT:-5187}"
export BOOK2JSON_OPEN_BROWSER=1
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1

echo "Book Manuscript Agent  >  http://localhost:${PORT}"
echo "Press Ctrl+C to stop."
echo
exec .venv-app/bin/python -m uvicorn server:app --host 127.0.0.1 --port "${PORT}"
