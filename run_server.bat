@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if not exist ".env" copy .env.example .env
echo.
echo Starting EyeSpeak AI server in a separate window...
start "EyeSpeak AI Server" cmd /k ""%~dp0.venv\Scripts\python.exe" -m uvicorn server:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000"
exit /b
