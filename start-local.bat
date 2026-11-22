@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv-local\Scripts\python.exe" (
  py -3 -m venv .venv-local
  if errorlevel 1 goto failed
)
".venv-local\Scripts\python.exe" -c "import flask, PIL, fsrs, jsonschema, waitress, bs4, mdict_utils, nltk" >nul 2>&1
if errorlevel 1 (
  ".venv-local\Scripts\python.exe" -c "import subprocess, sys; from pathlib import Path; app=next(Path.cwd().glob('*/web_server.py')).parent; sys.exit(subprocess.call([sys.executable, '-m', 'pip', 'install', '-r', str(app / 'requirements.txt')]))"
  if errorlevel 1 goto failed
)
echo Open http://127.0.0.1:5050 in your browser.
".venv-local\Scripts\python.exe" -u -c "import runpy,sys; from pathlib import Path; app=next(Path.cwd().glob('*/web_server.py')); sys.path.insert(0,str(app.parent)); runpy.run_path(str(app),run_name='__main__')"
if errorlevel 1 goto failed
exit /b 0
:failed
echo Startup failed. Check that Python 3.11 or later is installed.
pause
exit /b 1
