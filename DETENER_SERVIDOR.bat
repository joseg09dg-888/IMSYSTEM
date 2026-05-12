@echo off
title IM Platform — Detener Servidor
echo.
echo  Deteniendo servidor IM Platform...
echo.

taskkill /F /IM pythonw.exe > nul 2>&1

if %errorlevel% == 0 (
    echo  Servidor detenido correctamente.
) else (
    echo  No habia servidor corriendo.
)

echo.
pause
