@echo off
cd /d "%~dp0"
echo === Instalacja XAUUSD Signal Bot ===
where python >nul 2>nul
if errorlevel 1 (
  echo Nie znaleziono Pythona. Zainstaluj Python 3.12 z python.org
  echo i zaznacz "Add Python to PATH", potem uruchom ten plik ponownie.
  start https://www.python.org/downloads/release/python-3128/
  pause
  exit /b 1
)
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Instalacja bibliotek nie powiodla sie. Skopiuj komunikat bledu i wyslij go.
  pause
  exit /b 1
)
pip install MetaTrader5 >nul 2>nul || echo (MetaTrader5 niedostepny - potrzebny tylko przy DATA_SOURCE=mt5)
if not exist .env copy .env.example .env >nul
echo.
echo Gotowe. Otwieram plik .env - uzupelnij token Telegrama, chat ID i zrodlo danych, zapisz i zamknij.
notepad .env
pause
