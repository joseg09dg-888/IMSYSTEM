@echo off
title IM Platform — Intelligent Markets
cd /d "%~dp0"
echo.
echo   IM Platform arrancando...
echo   Abriendo http://localhost:5000
echo.
start http://localhost:5000
python server/server.py
pause
