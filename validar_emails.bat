@echo off
cd /d "%~dp0"
if "%1"=="" (
    echo Uso: validar_emails.bat data\leads.csv
) else (
    python agent\im_deliverability.py --validar --csv %1
)
pause
