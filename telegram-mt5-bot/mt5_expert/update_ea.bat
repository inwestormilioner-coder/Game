@echo off
REM Copies TelegramBridgeEA.mq5 into your MT5 data folder and compiles it
REM via MetaEditor's command-line mode. Run this (double-click) any time
REM the .mq5 file changes, instead of doing it by hand in MetaEditor.
REM
REM One-time setup: the two paths below are already filled in for this
REM install. If you ever reinstall MT5 or move it, update them:
REM   MT5_DATA    - from MT5: Plik -> Otworz folder danych
REM   MT5_INSTALL - folder containing terminal64.exe (and metaeditor64.exe
REM                 right next to it)

setlocal

set "REPO_DIR=%~dp0"
set "EA_SOURCE=%REPO_DIR%TelegramBridgeEA.mq5"
set "MT5_DATA=C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\AE2CC2E013FDE1E3CDF010AA51C60400"
set "MT5_INSTALL=C:\Program Files\Vantage International MT5"
set "EA_DEST=%MT5_DATA%\MQL5\Experts\TelegramBridgeEA.mq5"
set "LOG_FILE=%REPO_DIR%compile.log"

echo Kopiuje EA...
echo   z: %EA_SOURCE%
echo   do: %EA_DEST%
copy /Y "%EA_SOURCE%" "%EA_DEST%" >nul
if errorlevel 1 (
    echo.
    echo BLAD: nie udalo sie skopiowac pliku. Sprawdz czy MT5_DATA powyzej
    echo w tym pliku .bat jest poprawne ^(Plik -^> Otworz folder danych w MT5^).
    pause
    exit /b 1
)

echo Kompiluje przez MetaEditor...
"%MT5_INSTALL%\metaeditor64.exe" /compile:"%EA_DEST%" /log:"%LOG_FILE%"

echo.
echo ================== Wynik kompilacji ==================
type "%LOG_FILE%"
echo =======================================================
echo.
echo Jesli powyzej widzisz "0 error(s)" - wszystko OK.
echo ^(Jesli tekst wyglada dziwnie/rozstrzelony, otworz "compile.log"
echo w Notatniku zamiast czytac go tutaj.^)
echo.
echo W MT5 sprawdz zakladke "Eksperci" - EA czasem sam przeladowuje nowa
echo wersje, a czasem trzeba go usunac z wykresu i przeciagnac ponownie
echo z Nawigatora, zeby na pewno dzialal nowy kod.
echo.
pause
