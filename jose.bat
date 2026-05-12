@echo off
title Jose - IM Music
cd /d "%~dp0"
python agent\im_agents.py --agente jose %*
pause
