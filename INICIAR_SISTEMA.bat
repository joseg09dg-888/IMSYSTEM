@echo off
cd /d C:\Users\jose-\Downloads\IM-COMPLETO
echo Iniciando IM System...
start /min pythonw server\server.py
timeout /t 3 /nobreak >nul
start /min ngrok http 5000
timeout /t 6 /nobreak >nul
python setup_webhook.py
echo.
echo Sistema corriendo
echo Local:    http://localhost:5000
echo ngrok:    http://localhost:4040
echo Telegram: webhook configurado automaticamente
pause
