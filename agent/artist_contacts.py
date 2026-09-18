#!/usr/bin/env python3
"""
Busca el correo publico de contacto/booking/management de cada artista del
maestro (data/MAESTRO_leads_artistas.csv) usando Gemini + Google Search
(plan gratuito). Solo guarda un correo si aparece literalmente en el texto de
la respuesta Y trae una fuente (URL). No toca Instagram.

Uso:  python agent/artist_contacts.py --max 20
"""
import argparse, csv, json, re, sys, time
from pathlib import Path

import requests

BASE = Path(__file__).parent.parent
CSV_PATH = BASE / "data" / "MAESTRO_leads_artistas.csv"
MODELOS = ("gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-flash-latest")
ESTADOS_OK = ("candidato_pagador_verificar_sello", "pendiente_verificacion_ig", "pendiente")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
BASURA = ("example.", "sentry", "wixpress", "domain.com", "email.com", "tuemail")


def _key():
    for line in open(BASE / ".env", encoding="utf-8"):
        if line.startswith("GEMINI_API_KEY="):
            return line.strip().split("=", 1)[1]
    sys.exit("Falta GEMINI_API_KEY en .env")


def buscar(nombre, generos, key):
    prompt = (
        f'Busca en Google el correo electrónico PÚBLICO de contacto, booking o management del '
        f'artista musical "{nombre}" (géneros: {generos or "música urbana latina"}). '
        f"Debe ser el correo oficial del artista o de su manager/booking, encontrado en su perfil, "
        f"página web, Facebook, Linktree, YouTube o similar. NO inventes ni adivines correos. "
        f"Si no encuentras uno real, responde exactamente NO_ENCONTRADO. "
        f"Formato de respuesta, una línea cada uno:\nCORREO: <correo>\nINSTAGRAM: <url o vacío>\nFUENTE: <url donde lo viste>"
    )
    for modelo in MODELOS:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]},
                timeout=90,
            )
            d = r.json()
            if "candidates" in d:
                return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        except Exception:
            pass
        time.sleep(2)
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=20)
    args = ap.parse_args()
    key = _key()

    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        cols = list(rows[0].keys())
    for extra in ("email_fuente",):
        if extra not in cols:
            cols.append(extra)

    hechos = con_correo = 0
    for r in rows:
        if hechos >= args.max:
            break
        if r.get("email") or r.get("status") not in ESTADOS_OK or r.get("email_fuente") == "no_encontrado":
            continue
        nombre = r["empresa"].replace("Artista Independiente — ", "").strip()
        texto = buscar(nombre, r.get("generos", ""), key)
        hechos += 1
        correos = [e for e in EMAIL_RE.findall(texto) if not any(b in e.lower() for b in BASURA)]
        fuente = re.search(r"FUENTE:\s*(\S+)", texto)
        if "NO_ENCONTRADO" in texto.upper() and not correos:
            r["email_fuente"] = "no_encontrado"
            print(f"  ✗ {nombre}: sin correo público")
        elif correos and fuente:
            r["email"] = correos[0].lower()
            r["email_fuente"] = fuente.group(1)
            ig = re.search(r"INSTAGRAM:\s*(https?://\S+)", texto)
            if ig and not r.get("instagram"):
                r["instagram"] = ig.group(1)
            con_correo += 1
            print(f"  ✓ {nombre}: {r['email']}  ({r['email_fuente'][:60]})")
        else:
            print(f"  ? {nombre}: respuesta sin correo verificable")
        time.sleep(4)  # respeta el límite gratuito

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"[contactos] {con_correo} correos nuevos de {hechos} artistas buscados")


if __name__ == "__main__":
    main()
