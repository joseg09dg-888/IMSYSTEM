@echo off
title IM Platform — Intelligent Markets
color 0F
cd /d "%~dp0"

echo.
echo  ===================================================
echo   IM PLATFORM v2 — INTELLIGENT MARKETS
echo   Mateo Galvis + Jose Galvis
echo  ===================================================
echo.
echo  Instalando dependencias...
python -m pip install flask flask-cors requests beautifulsoup4 pytz -q 2>nul
echo  [OK] Dependencias instaladas
echo.
echo  Iniciando servidor en http://localhost:5000
echo  Presiona Ctrl+C para detener
echo.

timeout /t 2 /nobreak >nul
start "" "http://localhost:5000"

python server\server.py
pause
