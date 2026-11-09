@echo off
cd /d "%~dp0"
chcp 65001 >nul
call .venv\Scripts\activate.bat
python -m signalbot.setup_env check
echo.
echo Wysylam testowy sygnal (dane historyczne/syntetyczne) na Telegram...
python -m signalbot.main fibtest
pause
