@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Wysylam testowy sygnal (dane historyczne/syntetyczne) na Telegram...
python -m signalbot.main fibtest
pause
