@echo off
title Scheduler Mateo (Lun-Vie 6am-7pm / Sab 6am-12pm)
cd /d "%~dp0"
echo Scheduler Mateo iniciado. Ctrl+C para detener.
python agent\im_scheduler.py run --agente mateo --csv "data\leads_*.csv" --tipo 1 --max 40
pause
