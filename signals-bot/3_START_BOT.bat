@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Bot dziala. Nie zamykaj tego okna. Zatrzymanie: Ctrl+C
python -m signalbot.main run
pause
