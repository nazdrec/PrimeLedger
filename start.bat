@echo off
rem PrimeLedger launcher (from the source): starts the local app without a console window.
rem (The shortcut next to this file does the same.)
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "%~dp0app.py"
) else (
  start "" python "%~dp0app.py"
)
