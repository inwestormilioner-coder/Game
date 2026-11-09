@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo === Przenosze ustawienia (token Telegrama, chat ID, klucze) ze starego bota ===
python -m signalbot.setup_env migrate
echo.
echo Teraz uruchom 1_INSTALUJ.bat (jesli jeszcze nie), a potem 3_START_BOT.bat
pause
