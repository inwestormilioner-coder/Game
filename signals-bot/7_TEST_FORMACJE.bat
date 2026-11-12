@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt >nul 2>nul
echo Szukam formacji na historii (CSV z MT5 albo dane przykladowe)...
set /p CSV="Sciezka do pliku CSV (Enter = dane przykladowe): "
if "%CSV%"=="" (
  python -m signalbot.main patterns --charts 10 --post-last
) else (
  python -m signalbot.main patterns --csv "%CSV%" --charts 10 --post-last
)
echo.
echo Wykresy formacji sa w folderze data\patterns
pause
