@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt requests pyttsx3 opencv-python mediapipe
if errorlevel 1 goto error
if not exist ".env" copy .env.example .env
start "EyeSpeak AI Server" /min "%~dp0.venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000
 timeout /t 3 /nobreak >nul
".venv\Scripts\python.exe" desktop_app.py
exit /b 0
:error
echo Setup failed. Check that Python 3.12 is installed and internet is available.
pause
exit /b 1
