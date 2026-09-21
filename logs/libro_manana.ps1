cd C:\Users\JOSÉ\Projects\IMSYSTEM
$obj = Get-Date '2026-09-22 11:30'
while ((Get-Date) -lt $obj) { Start-Sleep -Seconds 60 }
$env:PYTHONIOENCODING='utf-8'
for ($i=0; $i -lt 6; $i++) {
  if ((Get-Date).Hour -ge 19) { break }
  python agent\libro_campana.py --equipos --max 10 >> logs\run_libro_manana.log 2>&1
  Start-Sleep -Seconds 3600
}
