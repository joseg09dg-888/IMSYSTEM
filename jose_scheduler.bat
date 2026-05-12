@echo off
title Scheduler Jose (Lun-Vie 6am-7pm / Sab 6am-12pm)
cd /d "%~dp0"
echo Scheduler Jose iniciado. Ctrl+C para detener.
python agent\im_scheduler.py run --agente jose --csv "data\leads_*.csv" --tipo 1 --max 30
pause
