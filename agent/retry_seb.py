#!/usr/bin/env python3
"""Reintenta el correo de aclaracion a Seb (King Records) desde immusicsello
cada 15 min hasta que Gmail libere el limite diario, maximo 5 horas (20 intentos).
NO reintenta en bucle rapido — evita el desastre de 105 intentos.
Cuando logra enviar, imprime OK-ENVIADO y termina. Si se acaba el tiempo, imprime AGOTADO.
"""
import smtplib, time, sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path

BASE = Path(__file__).parent.parent
PDF = Path(r"C:\Users\JOSÉ\Downloads\Music_Business_Para_Todos_Los_Humanos_IM_Music.docx.pdf")
DEST = "booking@kingrecordsusa.com"

def _env():
    env = {}
    for line in open(BASE / ".env", encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v
    return env

CUERPO = """Hola Seb,

Como quedamos, aqui te comparto el libro directo desde IM Music Sello.

Gracias por tu buena disposicion, quedamos atentos a lo que necesites.

Un abrazo,
Equipo IM Music
"""

def intentar(env):
    msg = MIMEMultipart()
    msg["From"] = env["IM_EMAIL_MUSIC"]
    msg["To"] = DEST
    msg["Subject"] = "Aclaracion: copia del libro (IM Music Sello)"
    msg.attach(MIMEText(CUERPO, "plain", "utf-8"))
    if PDF.exists():
        with open(PDF, "rb") as f:
            part = MIMEApplication(f.read(), _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=PDF.name)
        msg.attach(part)
    s = smtplib.SMTP("smtp.gmail.com", 587)
    s.starttls()
    s.login(env["IM_EMAIL_MUSIC"], env["IM_EMAIL_MUSIC_PASSWORD"])
    s.sendmail(env["IM_EMAIL_MUSIC"], [DEST], msg.as_string())
    s.quit()

def main():
    env = _env()
    for intento in range(1, 21):
        try:
            intentar(env)
            print(f"OK-ENVIADO intento {intento} a {DEST}", flush=True)
            return
        except Exception as e:
            print(f"fallo intento {intento}/20: {e}", flush=True)
            if intento < 20:
                time.sleep(900)
    print("AGOTADO: 20 intentos en 5 horas, immusicsello sigue bloqueada", flush=True)

if __name__ == "__main__":
    main()
