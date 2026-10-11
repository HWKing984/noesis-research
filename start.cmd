@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title NOESIS Research - dev (8100 / 8101 / 4173)

rem ============================================================
rem  NOESIS Research one-click dev launcher (double-click me).
rem  Starts API(8100) + research Agent(8101) + Web preview(4173),
rem  waits until ready, then opens the browser.
rem  Stop: close this window (Ctrl+C) or double-click stop.cmd.
rem
rem  NOTE: this file is intentionally ASCII-only. cmd.exe parses
rem  batch files using the OEM codepage (GBK on zh-CN Windows),
rem  so non-ASCII bytes here get mis-decoded and break parsing.
rem  All Chinese user-facing output comes from the Python launcher.
rem ============================================================

set "PYTHONIOENCODING=utf-8"

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [dev] Python not found. Create a venv first, or add python to PATH.
  echo [dev]   python -m venv .venv
  pause
  exit /b 1
)

echo [dev] repo:   %~dp0
echo [dev] python: %PY%
echo.

%PY% "%~dp0scripts\dev_serve.py" start %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo [dev] startup failed ^(exit %RC%^). logs: %TEMP%\noesis_dev
  pause
)

endlocal & exit /b %RC%
