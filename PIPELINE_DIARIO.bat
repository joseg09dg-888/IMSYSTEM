@echo off
title IM Pipeline Diario - Leads + Envio automatico
cd /d "%~dp0"
echo ══════════════════════════════════════════════════════════
echo   IM PIPELINE DIARIO
echo   1) Libro a equipos de artistas y agencias (immusicsello, prioridad)
echo   2) Busqueda de leads y envios de Mateo
echo   3) Seguimientos y deteccion de respuestas
echo ══════════════════════════════════════════════════════════
python agent\libro_campana.py --equipos --max 12
python agent\libro_campana.py --max 4
python agent\daily_pipeline.py --linea ambas
python agent\followup.py
echo.
echo Listo. Revisa logs\actividad_agentes.csv, logs\RESPUESTAS.txt y data\PIPELINE_ESTADO.txt
