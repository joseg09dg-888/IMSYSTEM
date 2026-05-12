#!/usr/bin/env python3
"""
IM Scheduler — Intelligent Markets
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Horario laboral colombiano (UTC-5):
  Lunes - Viernes:  6:00am → 12:00pm (pausa variable 30-90min) → retoma → 7:00pm
  Sábado:           6:00am → 12:00pm (para al mediodía)
  Domingo:          NO trabaja

La pausa del mediodía siempre varía entre 12:00 y 13:30
para evitar patrones robóticos detectables.
"""

import os, time, random, json, csv, subprocess, sys, signal
from datetime import datetime, timedelta

# Forzar UTF-8 en stdout/stderr para evitar UnicodeEncodeError en Windows
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8')
    except Exception: pass
from pathlib import Path
import pytz

# ── Cargar .env ────────────────────────────────────────────────
def _load_env():
    f = Path(__file__).parent.parent / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip()
_load_env()

# ════════════════════════════════════════════════════════════════
# ZONA HORARIA Y HORARIO
# ════════════════════════════════════════════════════════════════

TZ_COL = pytz.timezone("America/Bogota")  # UTC-5, sin cambio de horario

def ahora_colombia() -> datetime:
    return datetime.now(TZ_COL)

def es_horario_laboral() -> tuple[bool, str]:
    """
    Retorna (puede_enviar, razon)
    Lógica:
      - Domingo: nunca
      - Sábado: solo 6:00 - 12:00
      - Lunes-Viernes: 6:00-12:00 y (12:00+pausa_aleatoria)-19:00
      - Pausa del mediodía: varía entre 12:00 y 13:30 cada día
    """
    now = ahora_colombia()
    dia_semana = now.weekday()  # 0=Lunes, 6=Domingo
    hora = now.hour
    minuto = now.minute
    hora_decimal = hora + minuto / 60

    # ── Domingo: nunca ──────────────────────────────────────────
    if dia_semana == 6:
        return False, "🚫 Domingo — sistema apagado"

    # ── Sábado: solo mañana ─────────────────────────────────────
    if dia_semana == 5:
        if hora_decimal < 6.0:
            faltan = (6.0 - hora_decimal) * 60
            return False, f"⏰ Sábado — empieza a las 6:00am ({faltan:.0f} min)"
        if hora_decimal >= 12.0:
            return False, "🌙 Sábado — paró al mediodía. Vuelve el lunes"
        return True, f"✅ Sábado {now.strftime('%H:%M')} — activo hasta las 12:00pm"

    # ── Lunes a Viernes ─────────────────────────────────────────
    # Antes de las 6am
    if hora_decimal < 6.0:
        faltan = (6.0 - hora_decimal) * 60
        return False, f"⏰ Muy temprano — empieza a las 6:00am ({faltan:.0f} min)"

    # Después de las 7pm
    if hora_decimal >= 19.0:
        horas_hasta = 24 - hora_decimal + 6.0
        return False, f"🌙 Terminó por hoy — retoma mañana a las 6:00am"

    # Franja de pausa del mediodía (varía cada día)
    pausa = cargar_pausa_del_dia(now.date())
    pausa_inicio = pausa["inicio"]   # ej: 12.0 (12:00pm)
    pausa_fin    = pausa["fin"]      # ej: 12.75 (12:45pm)

    if pausa_inicio <= hora_decimal < pausa_fin:
        minutos_rest = (pausa_fin - hora_decimal) * 60
        fin_str = f"{int(pausa_fin)}:{int((pausa_fin % 1) * 60):02d}"
        return False, f"🍽️  Pausa mediodía — retoma a las {fin_str} ({minutos_rest:.0f} min)"

    return True, f"✅ {now.strftime('%A %H:%M')} — activo"

def cargar_pausa_del_dia(fecha) -> dict:
    """
    Genera (y guarda) la pausa aleatoria del día para esa fecha.
    Siempre varía entre 12:00 y 13:30.
    Se guarda para que sea consistente durante el día.
    """
    config_file = Path(__file__).parent.parent / "logs" / "scheduler_config.json"
    config_file.parent.mkdir(exist_ok=True)

    fecha_str = str(fecha)

    config = {}
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except:
            config = {}

    if config.get("fecha") == fecha_str and "pausa" in config:
        return config["pausa"]

    # Generar nueva pausa para hoy
    # Inicio: entre 12:00 y 13:00
    inicio_min = random.randint(0, 60)       # minutos después de las 12
    inicio = 12.0 + inicio_min / 60

    # Duración: entre 30 y 90 minutos
    duracion = random.randint(30, 90) / 60

    fin = min(inicio + duracion, 13.5)       # máximo hasta 13:30

    pausa = {"inicio": round(inicio, 4), "fin": round(fin, 4)}

    config = {"fecha": fecha_str, "pausa": pausa}
    config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    return pausa

def proxima_ventana() -> str:
    """Describe cuándo será la próxima ventana de envío"""
    now = ahora_colombia()
    dia = now.weekday()
    hora = now.hour + now.minute / 60

    if dia == 6:  # Domingo
        # Próximo lunes 6am
        lunes = now + timedelta(days=1)
        return f"Lunes {lunes.strftime('%d/%m')} a las 6:00am"

    if dia == 5 and hora >= 12:  # Sábado tarde
        lunes = now + timedelta(days=2)
        return f"Lunes {lunes.strftime('%d/%m')} a las 6:00am"

    if hora >= 19:  # Noche de semana
        manana = now + timedelta(days=1 if dia < 4 else (3 if dia == 4 else 2))
        return f"Mañana {manana.strftime('%d/%m')} a las 6:00am"

    pausa = cargar_pausa_del_dia(now.date())
    if pausa["inicio"] <= hora < pausa["fin"]:
        fin_str = f"{int(pausa['fin'])}:{int((pausa['fin'] % 1) * 60):02d}"
        return f"Hoy a las {fin_str} (después de la pausa)"

    return "Ahora mismo"

def segundos_hasta_proxima_ventana() -> int:
    """Calcula segundos de espera hasta que se pueda enviar"""
    now = ahora_colombia()
    dia = now.weekday()
    hora = now.hour + now.minute / 60

    puede, _ = es_horario_laboral()
    if puede:
        return 0

    # Domingo → esperar hasta lunes 6am
    if dia == 6:
        target = now.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return int((target - now).total_seconds())

    # Sábado tarde → esperar hasta lunes 6am
    if dia == 5 and hora >= 12:
        target = now.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=2)
        return int((target - now).total_seconds())

    # Noche de semana → esperar hasta 6am del siguiente día hábil
    if hora >= 19:
        dias_extra = 1
        if dia == 4:  dias_extra = 3  # Viernes → Lunes
        elif dia == 5: dias_extra = 2
        target = now.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=dias_extra)
        return int((target - now).total_seconds())

    # Antes de las 6am
    if hora < 6:
        target = now.replace(hour=6, minute=0, second=0, microsecond=0)
        return int((target - now).total_seconds())

    # En pausa del mediodía
    pausa = cargar_pausa_del_dia(now.date())
    if pausa["inicio"] <= hora < pausa["fin"]:
        fin_hora = int(pausa["fin"])
        fin_min  = int((pausa["fin"] % 1) * 60)
        target = now.replace(hour=fin_hora, minute=fin_min, second=random.randint(0,59), microsecond=0)
        return int((target - now).total_seconds())

    return 60


# ════════════════════════════════════════════════════════════════
# SCHEDULER PRINCIPAL
# ════════════════════════════════════════════════════════════════

# Variables globales para el loop
_corriendo = True

def signal_handler(sig, frame):
    global _corriendo
    print(f"\n\n  ⛔ Scheduler detenido por el usuario.")
    _corriendo = False

signal.signal(signal.SIGINT, signal_handler)

def formatear_tiempo(segundos: int) -> str:
    """Formatea segundos en texto legible"""
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos//60}min {segundos%60}s"
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    return f"{horas}h {minutos}min"

def log_scheduler(mensaje: str):
    """Log con timestamp colombiano"""
    now = ahora_colombia()
    log_file = Path(__file__).parent.parent / "logs" / "scheduler.log"
    log_file.parent.mkdir(exist_ok=True)
    linea = f"[{now.strftime('%Y-%m-%d %H:%M:%S COL')}] {mensaje}"
    print(f"  {linea}")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(linea + "\n")

def ejecutar_tarea(tarea: dict) -> bool:
    """Ejecuta una tarea programada"""
    cmd = tarea.get("comando", "")
    if not cmd:
        return False
    try:
        result = subprocess.run(
            cmd, shell=True,
            cwd=str(Path(__file__).parent.parent),
            capture_output=False,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        log_scheduler(f"Error ejecutando tarea: {e}")
        return False

def mostrar_estado():
    """Muestra el estado actual del scheduler en terminal"""
    now = ahora_colombia()
    puede, razon = es_horario_laboral()
    pausa = cargar_pausa_del_dia(now.date())

    dias = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    dia_nombre = dias[now.weekday()]

    fin_pausa_h = int(pausa["fin"])
    fin_pausa_m = int((pausa["fin"] % 1) * 60)
    ini_pausa_h = int(pausa["inicio"])
    ini_pausa_m = int((pausa["inicio"] % 1) * 60)

    print(f"""
  ┌─────────────────────────────────────────────────────┐
  │  IM SCHEDULER — HORARIO COLOMBIANO (UTC-5)          │
  ├─────────────────────────────────────────────────────┤
  │  Ahora:     {now.strftime("%A %d/%m %H:%M")} Colombia              │
  │  Estado:    {razon[:45]:45} │
  ├─────────────────────────────────────────────────────┤
  │  HORARIO HOY ({dia_nombre}):                             │""")

    if now.weekday() == 6:
        print(f"  │  Domingo — sistema apagado todo el día              │")
    elif now.weekday() == 5:
        print(f"  │  ✅ Mañana:   6:00am → 12:00pm                      │")
        print(f"  │  🌙 Tarde:    Sistema apagado desde las 12:00pm      │")
    else:
        print(f"  │  ✅ Mañana:   6:00am → {ini_pausa_h:02d}:{ini_pausa_m:02d}am               │")
        print(f"  │  🍽️  Pausa:   {ini_pausa_h:02d}:{ini_pausa_m:02d} → {fin_pausa_h:02d}:{fin_pausa_m:02d} (varía cada día)   │")
        print(f"  │  ✅ Tarde:    {fin_pausa_h:02d}:{fin_pausa_m:02d} → 7:00pm               │")

    print(f"  ├─────────────────────────────────────────────────────┤")
    print(f"  │  Próxima ventana: {proxima_ventana():<35} │")
    print(f"  └─────────────────────────────────────────────────────┘")

def run_scheduler(agente: str, csv_glob: str, tipo: int = 1,
                  max_por_sesion: int = 40, brochure: bool = False,
                  sin_informe: bool = False):
    """
    Loop principal del scheduler.
    Se ejecuta indefinidamente respetando el horario colombiano.
    """
    global _corriendo

    log_scheduler(f"Scheduler iniciado — Agente: {agente} | CSV: {csv_glob} | Tipo: {tipo}")

    mostrar_estado()
    print()

    while _corriendo:
        puede, razon = es_horario_laboral()
        now = ahora_colombia()

        if not puede:
            # ── Fuera de horario — esperar ─────────────────────
            secs = segundos_hasta_proxima_ventana()
            secs = max(secs, 30)  # mínimo 30 segundos entre checks

            # Log cada 30 minutos para no llenar el archivo
            if now.minute % 30 == 0 and now.second < 60:
                log_scheduler(f"Fuera de horario: {razon} | Próxima ventana en {formatear_tiempo(secs)}")

            # Mostrar countdown en terminal
            print(f"\r  ⏸  {razon} | Próxima ventana en {formatear_tiempo(secs)}    ", end="", flush=True)

            # Dormir en intervalos de 30s para poder capturar Ctrl+C
            for _ in range(min(secs // 30, 120)):
                if not _corriendo: break
                time.sleep(30)
                secs = segundos_hasta_proxima_ventana()
                puede2, razon2 = es_horario_laboral()
                if puede2: break
                print(f"\r  ⏸  {razon2} | Próxima ventana en {formatear_tiempo(secs)}    ", end="", flush=True)

            continue

        # ── En horario — ejecutar envíos ───────────────────────
        print()
        log_scheduler(f"▶ Iniciando envíos — {razon}")

        # Construir comando
        brochure_flag  = "--brochure" if brochure else ""
        informe_flag   = "--sin-informe" if sin_informe else ""
        python_exe     = sys.executable

        cmd = (
            f'"{python_exe}" '
            f'"{Path(__file__).parent}/im_agents.py" '
            f'--agente {agente} '
            f'--csv "{csv_glob}" '
            f'--tipo {tipo} '
            f'--max {max_por_sesion} '
            f'{brochure_flag} {informe_flag}'
        ).strip()

        log_scheduler(f"Ejecutando: {cmd[:80]}...")
        ejecutar_tarea({"comando": cmd})

        # ── Pausa entre sesiones de envío ──────────────────────
        # Para de nuevo cuando el scheduler detecte que salió del horario
        # Pero entre lotes, espera un tiempo aleatorio "humano"
        puede_ahora, _ = es_horario_laboral()
        if puede_ahora:
            # Espera humanizada entre lotes (15-45 min)
            pausa_lote = random.randint(15 * 60, 45 * 60)
            log_scheduler(f"Lote completado. Pausa de {formatear_tiempo(pausa_lote)} antes del siguiente lote...")

            for i in range(pausa_lote // 30):
                if not _corriendo: break
                time.sleep(30)
                puede2, razon2 = es_horario_laboral()
                if not puede2:
                    log_scheduler(f"Horario terminado durante pausa: {razon2}")
                    break
                restante = pausa_lote - (i * 30)
                print(f"\r  ⏳ Pausa entre lotes: {formatear_tiempo(restante)} restantes    ", end="", flush=True)

    log_scheduler("Scheduler detenido.")


# ════════════════════════════════════════════════════════════════
# MODO DAEMON (segundo plano)
# ════════════════════════════════════════════════════════════════

def crear_tarea_windows(agente: str, csv_path: str, tipo: int, max_emails: int):
    """Crea una tarea programada en Windows Task Scheduler"""
    python_exe  = sys.executable
    script_path = Path(__file__).resolve()
    base_dir    = script_path.parent.parent

    # Comando que correrá la tarea
    cmd_args = (
        f'--agente {agente} --csv "{csv_path}" '
        f'--tipo {tipo} --max {max_emails}'
    )

    # XML para Task Scheduler de Windows
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>IM System — {agente.capitalize()} Scheduler</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{datetime.now().strftime('%Y-%m-%dT')}06:00:00</StartBoundary>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek>
          <Monday /><Tuesday /><Wednesday /><Thursday /><Friday /><Saturday />
        </DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT13H</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
  </Settings>
  <Actions>
    <Exec>
      <Command>"{python_exe}"</Command>
      <Arguments>"{script_path}" run {cmd_args}</Arguments>
      <WorkingDirectory>{base_dir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

    xml_path = base_dir / "logs" / f"tarea_{agente}.xml"
    xml_path.parent.mkdir(exist_ok=True)
    xml_path.write_text(xml, encoding="utf-16")

    print(f"\n  📋 XML de tarea creado: {xml_path}")
    print(f"\n  Para registrar en Windows Task Scheduler, corre en PowerShell como Admin:")
    print(f"""
  Register-ScheduledTask `
    -TaskName "IM-{agente.capitalize()}-Scheduler" `
    -Xml (Get-Content "{xml_path}" | Out-String) `
    -Force
""")
    print(f"  O haz doble clic en: {base_dir}\\registrar_tarea_{agente}.bat")

    # Crear .bat de registro automático
    bat = f"""@echo off
echo Registrando tarea IM-{agente.capitalize()}-Scheduler en Windows...
schtasks /Create /XML "{xml_path}" /TN "IM-{agente.capitalize()}-Scheduler" /F
if %ERRORLEVEL% EQU 0 (
    echo [OK] Tarea registrada exitosamente
    echo La tarea se ejecutara automaticamente de lunes a sabado a las 6:00am
) else (
    echo [ERROR] No se pudo registrar. Ejecuta como Administrador.
)
pause
"""
    bat_path = base_dir / f"registrar_tarea_{agente}.bat"
    bat_path.write_text(bat, encoding="ascii")
    print(f"  Archivo bat creado: {bat_path}")


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(
        description="IM Scheduler — Horario laboral colombiano",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
COMANDOS:

  # Ver estado del horario ahora mismo
  python im_scheduler.py --estado

  # Correr el scheduler (loop continuo, respeta horario Colombia)
  python im_scheduler.py run --agente mateo --csv "data/leads_odonto*.csv" --tipo 1 --max 40
  python im_scheduler.py run --agente jose  --csv "data/leads_sello*.csv"  --tipo 1 --max 30

  # Crear tarea automática en Windows (corre solo cada dia a las 6am)
  python im_scheduler.py --crear-tarea-windows --agente mateo --csv "data/leads.csv" --tipo 1 --max 40

HORARIO:
  Lun-Vie:  6:00am → pausa mediodía (varía 12:00-13:30) → 7:00pm
  Sábado:   6:00am → 12:00pm (para al mediodía)
  Domingo:  APAGADO
        """
    )

    p.add_argument("modo",  nargs="?", choices=["run"], default=None)
    p.add_argument("--agente",   choices=["mateo","jose"])
    p.add_argument("--csv",      default="data/leads_*.csv")
    p.add_argument("--tipo",     type=int, default=1)
    p.add_argument("--max",      type=int, default=40)
    p.add_argument("--brochure", action="store_true")
    p.add_argument("--sin-informe", action="store_true")
    p.add_argument("--estado",   action="store_true")
    p.add_argument("--crear-tarea-windows", action="store_true")

    args = p.parse_args()

    if args.estado or (not args.modo and not args.crear_tarea_windows):
        mostrar_estado()
        # Mostrar también la pausa de hoy
        now = ahora_colombia()
        if now.weekday() < 6:
            pausa = cargar_pausa_del_dia(now.date())
            ini_h = int(pausa["inicio"])
            ini_m = int((pausa["inicio"] % 1) * 60)
            fin_h = int(pausa["fin"])
            fin_m = int((pausa["fin"] % 1) * 60)
            print(f"\n  Pausa de hoy: {ini_h:02d}:{ini_m:02d} → {fin_h:02d}:{fin_m:02d}")
        return

    if args.crear_tarea_windows:
        if not args.agente:
            print("  Falta: --agente mateo o --agente jose")
            return
        crear_tarea_windows(args.agente, args.csv, args.tipo, args.max)
        return

    if args.modo == "run":
        if not args.agente:
            print("  Falta: --agente mateo o --agente jose")
            return
        run_scheduler(
            args.agente, args.csv, args.tipo,
            args.max, args.brochure, args.sin_informe
        )

if __name__ == "__main__":
    main()
