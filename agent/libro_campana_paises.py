#!/usr/bin/env python3
"""
Ronda diaria de volumen mundial para el libro: 1 lead por país (de los países
ya verificados en MAESTRO_leads_musica.csv), para no concentrar todo en un
solo país y construir volumen parejo día a día, tal como pidió José
(2026-11-24): "trabajar consiguiendo clientes a nivel mundial... 1 de cada
país... vamos haciendo volumen".

No repite países/empresas ya mandados (data/libro_paises_enviados.csv).
Reutiliza las mismas plantillas, límites de envío y chequeos de
deliverability que agent/libro_campana.py — no se salta nada de eso.

Uso: python agent/libro_campana_paises.py [--dry-run] [--excluir PAIS,PAIS]
"""
import argparse, csv, re, sys
from pathlib import Path
import random

sys.path.insert(0, str(Path(__file__).parent))
import libro_campana as lc  # reutiliza CUERPO, ASUNTOS, _enviar, EMAIL_OK, etc.

BASE = Path(__file__).parent.parent
MUSICA = BASE / "data" / "MAESTRO_leads_musica.csv"
ENVIADOS_PAISES = BASE / "data" / "libro_paises_enviados.csv"


def _ya_enviados_paises():
    if not ENVIADOS_PAISES.exists():
        return set()
    return {r["email"].lower() for r in csv.DictReader(open(ENVIADOS_PAISES, encoding="utf-8"))}


def _paises_ya_hoy():
    """Países que ya recibieron un envío HOY (sin importar a qué empresa) —
    evita duplicar cobertura del mismo país el mismo día (bug 2026-11-24:
    antes solo evitaba repetir el mismo correo exacto, no el país)."""
    if not ENVIADOS_PAISES.exists():
        return set()
    from datetime import date
    hoy = date.today().isoformat()
    return {r["pais"] for r in csv.DictReader(open(ENVIADOS_PAISES, encoding="utf-8"))
            if r.get("fecha", "").startswith(hoy)}


def _guardar_pais(email_to, empresa, pais):
    nuevo = not ENVIADOS_PAISES.exists()
    with open(ENVIADOS_PAISES, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["email", "empresa", "pais", "fecha"])
        from datetime import datetime
        w.writerow([email_to, empresa, pais, datetime.now().isoformat()])


def candidatos_por_pais(excluir_paises):
    ya_libro = {r["email"].lower() for r in lc._leer_enviados()}
    ya_pais = _ya_enviados_paises()
    ya_hoy = _paises_ya_hoy()
    por_pais = {}
    for r in csv.DictReader(open(MUSICA, encoding="utf-8")):
        pais = r.get("pais", "").strip()
        if not pais or "http" in pais.lower() or pais in excluir_paises or pais in ya_hoy:
            continue
        if r.get("status", "").strip().lower() != "pendiente":
            continue
        e = re.sub(r"%20|\s|;", "", r.get("email", "")).lower()
        empresa = r.get("empresa", "").strip()
        if not e or not lc.EMAIL_OK.match(e) or any(m in e for m in lc.MAL_DOMINIO):
            continue
        if any(x in empresa.lower() for x in lc.EXCLUIR_NOMBRE):
            continue
        if e in ya_libro or e in ya_pais:
            continue
        por_pais.setdefault(pais, []).append((e, empresa))
    return por_pais


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--excluir", default="", help="países separados por coma a saltar hoy")
    args = ap.parse_args()
    excluir = {p.strip() for p in args.excluir.split(",") if p.strip()}

    por_pais = candidatos_por_pais(excluir)
    enviados_hoy = []
    for pais in sorted(por_pais.keys()):
        candidatos = por_pais[pais]
        random.shuffle(candidatos)
        e, empresa = candidatos[0]
        asunto = random.choice(lc.ASUNTOS).format(empresa=empresa)
        cuerpo = lc.CUERPO.format(empresa=empresa)
        ok = lc._enviar(e, asunto, cuerpo, args.dry_run)
        if ok is None:
            print(f"[libro_paises] parado por límite de envío antes de llegar a {pais}")
            break
        if ok:
            print(f"[libro_paises] OK -> {pais}: {empresa} <{e}>")
            if not args.dry_run:
                _guardar_pais(e, empresa, pais)
                lc._guardar_enviados(lc._leer_enviados() + [
                    {"email": e, "empresa": empresa, "fecha": __import__("datetime").datetime.now().isoformat(), "seguimiento": ""}
                ])
            enviados_hoy.append((pais, empresa, e))
        else:
            print(f"[libro_paises] FALLO -> {pais}: {empresa} <{e}>")

    print(f"\n[libro_paises] Resumen: {len(enviados_hoy)} países contactados hoy.")
    for pais, empresa, e in enviados_hoy:
        print(f"  - {pais}: {empresa} <{e}>")


if __name__ == "__main__":
    main()
