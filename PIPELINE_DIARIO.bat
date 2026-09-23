@echo off
setlocal
title IM Pipeline Diario - Leads + Envio automatico
cd /d "%~dp0"
set LOGFILE=logs\pipeline_diario_%date:~-4%%date:~3,2%%date:~0,2%.log
echo ══════════════════════════════════════════════════════════ >> "%LOGFILE%" 2>&1
echo   IM PIPELINE DIARIO - inicio %date% %time% >> "%LOGFILE%" 2>&1
echo ══════════════════════════════════════════════════════════ >> "%LOGFILE%" 2>&1
python agent\libro_campana.py --equipos --max 12 >> "%LOGFILE%" 2>&1
python agent\libro_campana.py --max 4 >> "%LOGFILE%" 2>&1
python agent\daily_pipeline.py --linea ambas >> "%LOGFILE%" 2>&1
python agent\followup.py >> "%LOGFILE%" 2>&1
echo   IM PIPELINE DIARIO - fin %date% %time% >> "%LOGFILE%" 2>&1
