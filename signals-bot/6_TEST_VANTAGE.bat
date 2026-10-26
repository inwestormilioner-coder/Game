@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Test auto-tradingu na MT5 (konto demo)...
python -m signalbot.main tradecheck
pause
