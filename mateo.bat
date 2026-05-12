@echo off
title Mateo - Intelligent Markets
cd /d "%~dp0"
python agent\im_agents.py --agente mateo %*
pause
