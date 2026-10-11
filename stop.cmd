@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title NOESIS Research - stop

rem ============================================================
rem  NOESIS Research one-click stop (double-click me).
rem  Kills only processes actually listening on 8100 / 8101 / 4173.
rem  ASCII-only on purpose (see start.cmd for the reason).
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
  echo [dev] Python not found. Cannot run the stop helper.
  pause
  exit /b 1
)

%PY% "%~dp0scripts\dev_serve.py" stop
echo.
pause

endlocal
