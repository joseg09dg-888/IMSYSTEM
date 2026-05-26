@echo off
cd /d C:\Users\jose-\Downloads\IM-COMPLETO
echo Iniciando IM System...
taskkill /F /IM pythonw.exe 2>nul
taskkill /F /IM ngrok.exe 2>nul
timeout /t 2 /nobreak >nul
start /min pythonw server\server.py
timeout /t 4 /nobreak >nul
start /min ngrok http 5000
timeout /t 6 /nobreak >nul
python update_ngrok.py
echo.
echo Sistema listo
echo Local: http://localhost:5000
echo Telegram: activo
pause
