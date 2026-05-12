@echo off
title Lead Finder
cd /d "%~dp0"
python agent\lead_finder_v2.py %*
pause
