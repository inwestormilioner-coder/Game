@echo off
cd /d "%~dp0"
chcp 65001 >nul
call .venv\Scripts\activate.bat
python -m signalbot.setup_env status
echo.
echo Bot dziala. Nie zamykaj tego okna. Zatrzymanie: Ctrl+C
python -m signalbot.main run
pause
