cd C:\Users\JOSÉ\Projects\IMSYSTEM\agent
while (Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'im_agents.py' -and $_.CommandLine -match 'mateo' }) { Start-Sleep -Seconds 30 }
for ($i=0; $i -lt 9; $i++) {
  if ((Get-Date).Hour -ge 19) { break }
  $env:PYTHONIOENCODING='utf-8'
  python im_agents.py --agente mateo --csv ..\data\MAESTRO_leads_empresas.csv --tipo 1 --max 20 >> ..\logs\run_mateo_dia.log 2>&1
  Start-Sleep -Seconds 1500
}
