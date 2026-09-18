#!/usr/bin/env python3
"""
Seguimiento automatico + deteccion de respuestas (linea Mateo).

1. Lee la bandeja de Mateo (IMAP, solo lectura) de los ultimos 10 dias y marca
   como "respondio" a todo lead contactado que haya escrito de vuelta.
   Escribe esas respuestas en logs/RESPUESTAS.txt (esto es lo que hay que atender).
2. Arma la lista de leads con 1 solo contacto hace >= DIAS_SEGUIMIENTO dias y
   sin respuesta, y les manda el follow-up (tipo 2) via im_agents.py.

Uso:  python agent/followup.py            (detecta respuestas + manda follow-ups)
      python agent/followup.py --solo-respuestas
"""
import argparse, csv, email, imaplib, subprocess, sys, sqlite3
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from session_memory import MemoriaAgentes, DB  # noqa: E402

BASE = Path(__file__).parent.parent
DIAS_SEGUIMIENTO = 3
MAX_FOLLOWUPS = 30
MAESTRO = BASE / "data" / "MAESTRO_leads_empresas.csv"
SALIDA_CSV = BASE / "data" / "followup_pendientes.csv"
RESPUESTAS_TXT = BASE / "logs" / "RESPUESTAS.txt"


def _env():
    env = {}
    for line in open(BASE / ".env", encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v
    return env


def detectar_respuestas():
    env = _env()
    mem = MemoriaAgentes()
    conn = sqlite3.connect(str(DB))
    contactados = {r[0].lower() for r in conn.execute("SELECT email FROM memoria_leads")}
    conn.close()

    desde = (datetime.now() - timedelta(days=10)).strftime("%d-%b-%Y")
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(env["IM_EMAIL"], env["IM_EMAIL_PASSWORD"])
    M.select("INBOX", readonly=True)
    _, nums = M.search(None, f"SINCE {desde}")
    respuestas = []
    for n in nums[0].split():
        _, d = M.fetch(n, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        m = email.message_from_bytes(d[0][1])
        remitente = email.utils.parseaddr(m.get("From", ""))[1].lower()
        if remitente in contactados:
            asunto = str(make_header(decode_header(m.get("Subject", ""))))
            respuestas.append((remitente, asunto, m.get("Date", "")))
            mem.marcar_respuesta(remitente)
    M.logout()

    with open(RESPUESTAS_TXT, "w", encoding="utf-8") as f:
        f.write(f"RESPUESTAS DE PROSPECTOS - revisado {datetime.now():%Y-%m-%d %H:%M}\n\n")
        for r in respuestas:
            f.write(f"{r[2]} | {r[0]} | {r[1]}\n")
        if not respuestas:
            f.write("(ninguna todavia)\n")
    print(f"[followup] {len(respuestas)} respuestas de prospectos -> {RESPUESTAS_TXT}")
    return {r[0] for r in respuestas}


def armar_followups(respondieron):
    limite = (datetime.now() - timedelta(days=DIAS_SEGUIMIENTO)).isoformat()
    conn = sqlite3.connect(str(DB))
    pendientes = {
        r[0].lower() for r in conn.execute(
            "SELECT email FROM memoria_leads WHERE veces_contactado = 1 "
            "AND COALESCE(respondio,0) = 0 AND ultimo_contacto <= ?", (limite,))
    } - respondieron
    conn.close()

    with open(MAESTRO, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        cols = list(rows[0].keys())
    elegidos = [r for r in rows if r.get("email", "").lower() in pendientes][:MAX_FOLLOWUPS]
    with open(SALIDA_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(elegidos)
    print(f"[followup] {len(elegidos)} leads listos para follow-up (de {len(pendientes)} elegibles)")
    return len(elegidos)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--solo-respuestas", action="store_true")
    args = p.parse_args()

    respondieron = detectar_respuestas()
    if args.solo_respuestas:
        return
    if armar_followups(respondieron) == 0:
        return
    subprocess.run([sys.executable, str(Path(__file__).parent / "im_agents.py"),
                    "--agente", "mateo", "--csv", str(SALIDA_CSV),
                    "--tipo", "2", "--max", str(MAX_FOLLOWUPS)], cwd=str(Path(__file__).parent))


if __name__ == "__main__":
    main()
