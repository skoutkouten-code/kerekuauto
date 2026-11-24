@echo off
cd /d "%~dp0"
set "PY="
for %%C in ("%LOCALAPPDATA%\Python\pythoncore-3.15-64\python.exe" "%USERPROFILE%\.local\bin\python3.15.exe" python py) do (
  if not defined PY (
    "%%~C" -c "import sys" >nul 2>&1 && set "PY=%%~C"
  )
)
if not defined PY (
  echo Python not found. Install it from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Using Python: %PY%
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment, please wait...
  "%PY%" -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo Could not create the virtual environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -q flask
echo.
echo Site:  http://127.0.0.1:5000
echo Admin: http://127.0.0.1:5000/admin/login
echo Press Ctrl+C to stop the server.
echo.
".venv\Scripts\python.exe" app.py
pause
