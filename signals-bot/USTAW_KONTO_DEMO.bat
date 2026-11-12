@echo off
cd /d "%~dp0"
chcp 65001 >nul
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt >nul 2>nul
python -m signalbot.setup_env trade
echo.
echo Test: pokaze konto i lot, postawi zlecenie daleko od ceny i od razu je usunie...
python -m signalbot.main tradecheck
echo.
echo Jesli test przeszedl, uruchom ponownie 3_START_BOT.bat - bot bedzie gral sygnaly na demo.
pause
