@echo off
setlocal
cd /d "%~dp0"

echo == Book Manuscript Agent - first-time setup ==
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3.10+ is required and was not found on PATH.
  goto :fail
)

echo [1/3] console env (.venv-app)
if not exist ".venv-app\Scripts\python.exe" python -m venv .venv-app
if errorlevel 1 (echo [ERROR] venv creation failed. & goto :fail)
".venv-app\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv-app\Scripts\python.exe" -m pip install --quiet -e .
if errorlevel 1 (echo [ERROR] dependency install failed. & goto :fail)

REM Playwright drives the b7-check stage: it opens the manuscript in a real
REM browser and measures every section against 944x507. Without it the
REM manuscript still builds - it just goes out unmeasured.
echo [2/3] headless browser (playwright, for the 944x507 measurement)
where npm >nul 2>&1
if errorlevel 1 (
  echo        [WARN] npm not on PATH - skipping. b7-check will be unavailable.
) else (
  call npm install --silent --no-audit --no-fund
  call npx --yes playwright install chromium
)

echo [3/3] connection check
".venv-app\Scripts\python.exe" scripts\smoke_claude.py --only text
if errorlevel 1 (
  echo.
  echo [WARN] Claude Code login needed. Run "claude" once in a terminal, then retry.
)

echo.
echo Setup complete. Start with run.bat  ^(http://localhost:5187^)
echo.
pause
exit /b 0

:fail
echo.
echo Setup did not finish. The message above says why.
pause
exit /b 1
