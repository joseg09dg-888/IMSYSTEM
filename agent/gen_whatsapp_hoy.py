#!/usr/bin/env python3
"""Genera data/WHATSAPP_HOY.txt: links wa.me con mensaje pre-escrito para los
leads en FRIO (ya se les mando correo, cero respuesta) que tienen telefono y
no se les ha mandado WhatsApp todavia. Para que Jose abra cada link y le de
enviar el mismo, desde su WhatsApp real (no se automatiza el envio: WhatsApp
banea numeros muy facil por mensajeria automatizada)."""
import csv, sqlite3, re, sys, urllib.parse
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE / "agent"))
from session_memory import DB  # noqa: E402

MAX = 40
MENSAJE = ("Hola, buenas tardes. Soy Jose Galvis de Intelligent Markets. "
           "Le escribi hace poco por correo sobre como ayudamos a negocios "
           "como el suyo a conseguir clientes nuevos con publicidad digital. "
           "Le puedo contar en 2 minutos como lo hacemos? Sin compromiso.")


def leads_frios():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    frios = {r["email"].lower() for r in c.execute(
        "SELECT LOWER(email) AS email FROM memoria_leads "
        "WHERE veces_contactado >= 1 AND COALESCE(respondio,0) = 0")}
    c.close()
    return frios


def telefonos_ya_usados():
    usados = set()
    out = BASE / "data" / "WHATSAPP_HOY.txt"
    if out.exists():
        usados |= set(re.findall(r"wa\.me/(\d+)", out.read_text(encoding="utf-8")))
    log = BASE / "data" / "whatsapp_enviados.csv"
    if log.exists():
        with open(log, encoding="utf-8") as f:
            usados |= {row["telefono"] for row in csv.DictReader(f) if row.get("telefono")}
    return usados


def normalizar(tel):
    d = "".join(ch for ch in tel if ch.isdigit())
    if not d:
        return None
    if len(d) == 10:
        d = "57" + d
    return d


def main():
    frios = leads_frios()
    usados = telefonos_ya_usados()

    with open(BASE / "data" / "MAESTRO_leads_empresas.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    candidatos = []
    vistos = set()
    for r in rows:
        email = (r.get("email") or "").strip().lower()
        if email not in frios:
            continue
        tel = normalizar(r.get("telefono") or "")
        if not tel or tel in usados or tel in vistos:
            continue
        vistos.add(tel)
        candidatos.append({
            "empresa": r.get("empresa") or r.get("nombre") or "",
            "ciudad": r.get("ciudad", ""),
            "nicho": r.get("nicho", ""),
            "telefono": tel,
        })
        if len(candidatos) >= MAX:
            break

    out = BASE / "data" / "WHATSAPP_HOY.txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"WHATSAPP HOY - {len(candidatos)} leads en FRIO (correo enviado, sin respuesta).\n")
        f.write("Abre cada link, revisa el mensaje y dale enviar TU MISMO desde tu WhatsApp.\n")
        f.write("Sugerencia: 1 cada 1-2 minutos, no todos de golpe (para no arriesgar tu numero).\n\n")
        for i, c in enumerate(candidatos, 1):
            texto = urllib.parse.quote(MENSAJE)
            f.write(f"{i}. {c['empresa']} ({c['ciudad']}, {c['nicho']})\n")
            f.write(f"   https://wa.me/{c['telefono']}?text={texto}\n\n")

    print(f"[whatsapp] {len(candidatos)} links nuevos escritos en {out}")


if __name__ == "__main__":
    main()
