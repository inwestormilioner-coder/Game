@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Sprawdzam polaczenie z Threads...
python -m signalbot.main threadscheck || goto end
echo.
echo Wysylam testowy sygnal [TEST] tylko na Threads...
python -m signalbot.main fibtest --only threads
:end
pause
