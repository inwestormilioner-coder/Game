@echo off
cd /d "%~dp0"
echo === Przenosze ustawienia ze starego folderu bota ===
echo Podaj sciezke do STAREGO folderu bota (tam gdzie jest Twoj plik .env), np. C:\SignalBot
set /p OLD="Stary folder: "
if not exist "%OLD%\.env" (
  echo Nie ma pliku .env w "%OLD%". Sprawdz sciezke i uruchom ponownie.
  pause
  exit /b 1
)
copy /y "%OLD%\.env" .env >nul
if exist "%OLD%\zones.json" copy /y "%OLD%\zones.json" zones.json >nul
if exist "%OLD%\data" xcopy /e /i /y /q "%OLD%\data" data >nul
if exist "%OLD%\tv_profile" xcopy /e /i /y /q "%OLD%\tv_profile" tv_profile >nul
findstr /b "PATTERNS_ENABLED" .env >nul || (
  echo.>> .env
  echo # ===== Nowe: bot formacji + SL/TP z ATR =====>> .env
  echo PATTERNS_ENABLED=true>> .env
  echo PATTERN_KINDS=all>> .env
  echo PATTERN_DEPTHS=2,4>> .env
  echo PATTERN_MIN_SCORE=2>> .env
  echo PATTERN_AI_FILTER=true>> .env
  echo PATTERN_MIN_CONFIDENCE=60>> .env
  echo ZONES_FILE=zones.json>> .env
)
findstr /b "RISK_MODE" .env >nul || (
  echo RISK_MODE=atr>> .env
  echo SL_ATR=2.0>> .env
  echo TP_R=1,2,3,4,5>> .env
)
echo.
echo Gotowe: .env, strefy, historia sygnalow i logowanie TradingView przeniesione.
echo Teraz uruchom 1_INSTALUJ.bat, a potem 3_START_BOT.bat
pause
