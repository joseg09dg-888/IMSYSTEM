@echo off
title IM Watchdog — Manteniendo sistema activo
cd /d "%~dp0"
echo.
echo  IM WATCHDOG iniciado — verificando cada 5 minutos
echo  Log: logs\watchdog.log
echo.

:loop
python -c "
import requests, subprocess, sys, os
from pathlib import Path
from datetime import datetime

BASE = Path('.')
log = BASE / 'logs' / 'watchdog.log'
log.parent.mkdir(exist_ok=True)
ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 1. Verificar servidor
try:
    r = requests.get('http://localhost:5000/api/dashboard', timeout=5)
    d = r.json()
    leads = d.get('stats',{}).get('total_leads', '?')
    emails = d.get('stats',{}).get('emails_enviados', '?')
    log.open('a', encoding='utf-8').write(f'{ts} | SERVIDOR OK | leads={leads} emails={emails}\n')
    print(f'[{ts}] SERVIDOR OK — leads={leads} emails={emails}')
except Exception as e:
    log.open('a', encoding='utf-8').write(f'{ts} | SERVIDOR CAIDO ({e}) — reiniciando...\n')
    print(f'[{ts}] SERVIDOR CAIDO — reiniciando...')
    subprocess.Popen(['python', str(BASE / 'server' / 'server.py')], cwd=str(BASE))
    import time; time.sleep(5)

# 2. Verificar schedulers (buscar procesos python con im_scheduler)
import json
try:
    procs = requests.get('http://localhost:5000/api/proceso/estado', timeout=5).json()
    activos = [k for k,v in procs.get('procesos',{}).items() if v.get('activo')]
    log.open('a', encoding='utf-8').write(f'{ts} | Procesos activos: {activos}\n')
    print(f'[{ts}] Procesos activos: {activos}')
except:
    pass
"
echo  [Watchdog] Esperando 5 minutos...
timeout /t 300 /nobreak >nul
goto loop
