@echo off
title IM Platform — Servidor Background
cd /d "%~dp0"

if not exist logs mkdir logs

echo.
echo  Iniciando IM Platform en background...
echo  Log: logs\server.log
echo.

start /B pythonw server\server.py > logs\server.log 2>&1

timeout /t 3 /nobreak > nul

start http://localhost:5000

echo  Servidor corriendo en http://localhost:5000
echo  Para detenerlo: ejecuta DETENER_SERVIDOR.bat
echo.
