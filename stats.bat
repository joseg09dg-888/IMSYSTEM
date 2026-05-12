@echo off
title IM Stats
cd /d "%~dp0"
python agent\im_deliverability.py --stats
pause
