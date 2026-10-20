@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Otworzy sie przegladarka. Zaloguj sie do TradingView i ZAMKNIJ okno.
python -m signalbot.tvshot login
echo Teraz testowy zrzut Twojego wykresu (TV_CHART_URL z pliku .env)...
python -m signalbot.tvshot test
pause
