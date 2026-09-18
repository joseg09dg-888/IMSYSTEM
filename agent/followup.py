#!/usr/bin/env python3
"""
EMBUDO DE VENTAS AUTOMATICO (linea Mateo) — corre todos los dias.

Etapa de cada lead (se calcula de la memoria de contactos):
  NUEVO     en la base, sin contacto todavia          -> lo envia daily_pipeline (correo 1)
  FRIO      1 correo enviado, sin abrir ni responder  -> seguimiento a los 3 dias, otro angulo
  TIBIO     abrio el correo, sin responder            -> seguimiento a los 2 dias con link de agenda + brochure
  CALIENTE  respondio                                  -> ALERTA (logs/RESPUESTAS.txt), se detienen los automaticos
  SIN_RESP  3 contactos sin respuesta                  -> PERDIDO (se deja de escribir)

Cadencia: toque 1 -> +3 dias toque 2 -> +5 dias toque 3 -> +7 dias PERDIDO.
Cada corrida: (1) lee la bandeja y marca respuestas, (2) manda los seguimientos que
tocan hoy, (3) escribe el estado del embudo en data/PIPELINE_ESTADO.txt.

Uso:  python agent/followup.py                  (todo)
      python agent/followup.py --solo-estado    (solo respuestas + reporte, no envia)
"""
import argparse, csv, email, imaplib, sqlite3, subprocess, sys
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from session_memory import MemoriaAgentes, DB  # noqa: E402

BASE = Path(__file__).parent.parent
MAESTRO = BASE / "data" / "MAESTRO_leads_empresas.csv"
RESPUESTAS_TXT = BASE / "logs" / "RESPUESTAS.txt"
ESTADO_TXT = BASE / "data" / "PIPELINE_ESTADO.txt"
MAX_POR_TIPO = 25

# dias de espera desde el ultimo contacto segun cuantos toques lleva
ESPERA_DIAS = {1: 3, 2: 5}      # 1 toque -> a los 3 dias; 2 toques -> a los 5 dias
ESPERA_TIBIO = 2                # si abrio el correo, se le insiste antes
DIAS_PERDIDO = 7                # tras el 3er toque sin respuesta


def _env():
    env = {}
    for line in open(BASE / ".env", encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v
    return env


def _leads_db():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute(
        "SELECT LOWER(email) AS email, veces_contactado, ultimo_contacto, resultado, "
        "COALESCE(respondio,0) AS respondio FROM memoria_leads")]
    c.close()
    return rows


def detectar_respuestas():
    env = _env()
    mem = MemoriaAgentes()
    contactados = {r["email"] for r in _leads_db()}
    desde = (datetime.now() - timedelta(days=14)).strftime("%d-%b-%Y")
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
            respuestas.append((m.get("Date", ""), remitente, asunto))
            mem.marcar_respuesta(remitente)
    M.logout()
    with open(RESPUESTAS_TXT, "w", encoding="utf-8") as f:
        f.write(f"LEADS CALIENTES (respondieron) - revisado {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write("Atiendelos YA y mandales el link: https://cal.com/intelligent-markets-agencia/30min\n\n")
        for r in respuestas:
            f.write(" | ".join(r) + "\n")
        if not respuestas:
            f.write("(ninguno todavia)\n")
    print(f"[embudo] {len(respuestas)} leads calientes -> {RESPUESTAS_TXT}")


def _etapa(r, ahora):
    if r["respondio"]:
        return "CALIENTE"
    ult = datetime.fromisoformat(r["ultimo_contacto"]) if r["ultimo_contacto"] else ahora
    toques = r["veces_contactado"] or 0
    if toques >= 3:
        return "SIN_RESP" if (ahora - ult).days >= DIAS_PERDIDO else "FRIO"
    return "TIBIO" if r["resultado"] == "abierto" else "FRIO"


def calcular_embudo():
    ahora = datetime.now()
    filas = _leads_db()
    resumen = {"NUEVO": 0, "FRIO": 0, "TIBIO": 0, "CALIENTE": 0, "SIN_RESP": 0}
    por_enviar = {2: [], 3: []}   # tipo de correo -> emails
    for r in filas:
        et = _etapa(r, ahora)
        resumen[et] += 1
        if et not in ("FRIO", "TIBIO") or (r["veces_contactado"] or 0) >= 3:
            continue
        ult = datetime.fromisoformat(r["ultimo_contacto"])
        dias = (ahora - ult).days
        espera = ESPERA_TIBIO if et == "TIBIO" else ESPERA_DIAS.get(r["veces_contactado"], 99)
        if dias >= espera:
            por_enviar[3 if et == "TIBIO" else 2].append(r["email"])
    return resumen, por_enviar, {r["email"] for r in filas}


def enviar_seguimientos(por_enviar):
    with open(MAESTRO, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        cols = list(rows[0].keys())
    enviados = 0
    for tipo, emails in por_enviar.items():
        objetivo = set(emails[:MAX_POR_TIPO])
        elegidos = [r for r in rows if r.get("email", "").lower() in objetivo]
        if not elegidos:
            continue
        destino = BASE / "data" / f"followup_tipo{tipo}.csv"
        with open(destino, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(elegidos)
        print(f"[embudo] enviando {len(elegidos)} seguimientos tipo {tipo}")
        subprocess.run([sys.executable, str(Path(__file__).parent / "im_agents.py"),
                        "--agente", "mateo", "--csv", str(destino), "--tipo", str(tipo),
                        "--max", str(MAX_POR_TIPO)], cwd=str(Path(__file__).parent))
        enviados += len(elegidos)
    return enviados


def escribir_estado(resumen, por_enviar):
    with open(MAESTRO, encoding="utf-8") as f:
        total_base = sum(1 for _ in csv.DictReader(f))
    contactados = sum(resumen.values())
    resumen["NUEVO"] = max(0, total_base - contactados)
    with open(ESTADO_TXT, "w", encoding="utf-8") as f:
        f.write(f"ESTADO DEL EMBUDO - {datetime.now():%Y-%m-%d %H:%M}\n\n")
        f.write(f"NUEVO (sin contactar, en base) : {resumen['NUEVO']}\n")
        f.write(f"FRIO   (esperando seguimiento) : {resumen['FRIO']}\n")
        f.write(f"TIBIO  (abrieron el correo)    : {resumen['TIBIO']}\n")
        f.write(f"CALIENTE (respondieron)        : {resumen['CALIENTE']}   <- ver logs/RESPUESTAS.txt\n")
        f.write(f"PERDIDO (3 toques sin respuesta): {resumen['SIN_RESP']}\n\n")
        f.write(f"Seguimientos que tocan hoy: tipo2={len(por_enviar[2])}, tipo3(tibios)={len(por_enviar[3])}\n")
    print(open(ESTADO_TXT, encoding="utf-8").read())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--solo-estado", action="store_true")
    args = p.parse_args()

    detectar_respuestas()
    resumen, por_enviar, _ = calcular_embudo()
    escribir_estado(resumen, por_enviar)
    if args.solo_estado:
        return
    enviar_seguimientos(por_enviar)


if __name__ == "__main__":
    main()
