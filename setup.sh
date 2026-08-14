#!/usr/bin/env bash
# Book Manuscript Agent - first-time setup (macOS / Linux)
set -u
cd "$(dirname "$0")"

echo "== Book Manuscript Agent - first-time setup =="
echo

command -v python3 >/dev/null 2>&1 || { echo "[ERROR] Python 3.10+ is required."; exit 1; }

echo "[1/3] console env (.venv-app)"
[ -x ".venv-app/bin/python" ] || python3 -m venv .venv-app
.venv-app/bin/python -m pip install --quiet --upgrade pip
.venv-app/bin/python -m pip install --quiet -e . || { echo "[ERROR] dependency install failed."; exit 1; }

# Playwright drives the b7-check stage: it opens the manuscript in a real
# browser and measures every section against 944x507. Without it the
# manuscript still builds - it just goes out unmeasured.
echo "[2/3] headless browser (playwright, for the 944x507 measurement)"
if command -v npm >/dev/null 2>&1; then
  npm install --silent --no-audit --no-fund
  npx --yes playwright install chromium
else
  echo "       [WARN] npm not found - skipping. b7-check will be unavailable."
fi

echo "[3/3] connection check"
.venv-app/bin/python scripts/smoke_claude.py --only text || {
  echo
  echo '[WARN] Claude Code login needed. Run "claude" once in a terminal, then retry.'
}

echo
echo "Setup complete. Start with ./run.sh  (http://localhost:5187)"
