@echo off
cd /d "%~dp0"
chcp 65001 >nul
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt >nul 2>nul
python -m signalbot.setup_env check
echo.
echo Wysylam testowy sygnal (dane historyczne/syntetyczne) na Telegram...
python -m signalbot.main fibtest
pause
