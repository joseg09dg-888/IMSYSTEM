@echo off
title IM Pipeline Diario - Leads + Envio automatico
cd /d "%~dp0"
echo ══════════════════════════════════════════════════════════
echo   IM PIPELINE DIARIO
echo   Busca leads nuevos (Mateo + Jose) y manda correos de Mateo
echo ══════════════════════════════════════════════════════════
python agent\daily_pipeline.py --linea ambas
python agent\followup.py
echo.
echo Listo. Revisa logs\actividad_agentes.csv y reports\ para auditar.
pause
