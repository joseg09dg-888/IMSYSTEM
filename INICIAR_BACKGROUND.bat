@echo off
cd /d C:\Users\jose-\Downloads\IM-COMPLETO
start /min pythonw server\server.py
echo Servidor iniciado en background
echo Abre: http://localhost:5000
timeout /t 3
