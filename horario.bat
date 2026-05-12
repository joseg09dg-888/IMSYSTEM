@echo off
title Horario Colombia
cd /d "%~dp0"
python agent\im_scheduler.py --estado
pause
