@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo === Wpisz token i chat ID Telegrama (zostaja tylko w pliku .env na tym komputerze) ===
python -m signalbot.setup_env telegram
pause
